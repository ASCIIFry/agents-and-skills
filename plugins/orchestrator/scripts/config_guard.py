#!/usr/bin/env python3
"""PreToolUse hook: deny writes to Claude Code configuration.

Reads the hook input (JSON) on stdin. Prints a deny decision when a file
tool targets a protected path, or when a Bash command writes to one or
changes configuration through a CLI. Prints nothing (no decision) otherwise.

The Bash analysis is a heuristic: it catches common and accidental writes,
not deliberate obfuscation. Permission deny rules and the plugin cache are
the hard boundaries; see docs/design.org.

Fails closed: an internal error produces a deny decision.
"""

import json
import os
import re
import shlex
import sys

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Below a ".claude" directory everything is protected except these
# first-level subdirectories (worktrees hold project files; projects and
# plans hold Claude Code's own session data and memory).
CLAUDE_DIR_EXEMPT = {"worktrees", "projects", "plans"}

PROTECTED_BASENAMES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".mcp.json", ".claude.json", ".gitconfig"}

# Commands whose arguments are all write targets.
WRITE_ALL_ARGS = {"tee", "rm", "rmdir", "unlink", "truncate", "touch", "mkdir",
                  "chmod", "chown", "chgrp", "ln", "mv", "shred", "patch"}
# Commands whose last non-option argument is the write target.
WRITE_LAST_ARG = {"cp", "install", "rsync", "scp"}
# Commands that edit in place when given -i / --in-place.
IN_PLACE_EDITORS = {"sed", "perl", "ruby"}
# Interpreters whose inline code cannot be analysed.
INLINE_CODE = {"python": "-c", "python3": "-c", "perl": "-e", "ruby": "-e",
               "node": "-e", "bash": "-c", "sh": "-c", "zsh": "-c", "dash": "-c"}
# Prefixes that run another command.
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "nice", "xargs", "exec", "timeout", "stdbuf"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "\n"}
GIT_CONFIG_READ_FLAGS = {"--get", "--get-all", "--get-regexp", "--list", "-l",
                         "--show-origin", "--show-scope", "--name-only"}


def decide(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"config-guard: {reason}",
        }
    }


def resolve(path, cwd):
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def is_protected(path):
    """Return a reason string if the resolved absolute path is protected."""
    parts = [p for p in path.split(os.sep) if p]
    for i, part in enumerate(parts):
        if part == ".claude":
            nxt = parts[i + 1] if i + 1 < len(parts) else None
            if nxt not in CLAUDE_DIR_EXEMPT:
                return "Claude Code configuration directory (.claude)"
        if part == ".git":
            rest = parts[i + 1:]
            if rest[:1] == ["hooks"] or rest == ["config"]:
                return "git hooks or git config"
        if part == ".config" and parts[i + 1:i + 2] == ["git"]:
            return "git configuration"
        if part == ".orchestrator" and parts[i + 1:] == [".gitignore"]:
            return "run-state switch (.orchestrator/.gitignore)"
    if parts and parts[-1] in PROTECTED_BASENAMES:
        return f"instruction or configuration file ({parts[-1]})"
    return None


def check_file_tool(tool_name, tool_input, cwd, agent_type):
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return None
    path = resolve(target, cwd)
    reason = is_protected(path)
    if reason:
        return f"{tool_name} on {target} is not allowed: {reason}. Propose the change to the user instead."
    if agent_type and agent_type.split(":")[-1] == "researcher":
        allowed = resolve(".orchestrator", project_dir(cwd))
        if not (path == allowed or path.startswith(allowed + os.sep)):
            return f"the researcher may write only below .orchestrator/, not {target}."
    return None


def project_dir(cwd):
    return os.environ.get("CLAUDE_PROJECT_DIR") or cwd


def tokenize(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return command.split()


def segments(tokens):
    """Split tokens into simple commands; keep redirections inside them."""
    current = []
    for tok in tokens:
        if tok in SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(tok)
    if current:
        yield current


def strip_prefixes(seg):
    """Drop env assignments and wrapper commands; return the real command."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1
        elif os.path.basename(tok) in WRAPPERS:
            i += 1
            # Skip the wrapper's options and numeric arguments (timeout 10, nice -n 5).
            while i < len(seg) and (seg[i].startswith("-") or re.fullmatch(r"\d+[smhd]?", seg[i])):
                i += 1
        else:
            break
    return seg[i:]


def path_candidates(token):
    """A token may carry a path after '=' (e.g. --output=FILE, of=FILE)."""
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]


def protected_token(token, cwd):
    for cand in path_candidates(token):
        if not cand or cand.startswith("-") and "=" not in cand:
            continue
        reason = is_protected(resolve(cand, cwd))
        if reason:
            return reason
    return None


def check_segment(seg, cwd):
    # Redirections anywhere in the segment: the token after '>' is a target.
    plain = []
    i = 0
    while i < len(seg):
        tok = seg[i]
        if set(tok) <= set("<>&|0123456789") and ">" in tok:
            target = seg[i + 1] if i + 1 < len(seg) else ""
            if not (tok.endswith("&") and target.isdigit()):
                reason = protected_token(target, cwd)
                if reason:
                    return f"redirection into a protected path ({reason})"
            i += 2
            continue
        if re.fullmatch(r"\d", tok) and i + 1 < len(seg) and ">" in seg[i + 1]:
            i += 1
            continue
        plain.append(tok)
        i += 1

    cmd = strip_prefixes(plain)
    if not cmd:
        return None
    name = os.path.basename(cmd[0])
    args = cmd[1:]
    joined = " ".join(cmd)

    if re.search(r"ORCHESTRATOR_RUN_STATE", " ".join(plain)):
        return "ORCHESTRATOR_RUN_STATE is reserved for the user; run-init.sh reports the active mode"
    if re.search(r"core\.hookspath", joined, re.IGNORECASE):
        return "changing git's hooks path is not allowed"
    if name == "claude" and args[:1] and args[0] in {"plugin", "plugins", "config", "mcp", "update", "install"}:
        return f"'claude {args[0]}' changes Claude Code configuration; ask the user to run it"
    if name == "git" and "config" in args[:3]:
        if not GIT_CONFIG_READ_FLAGS.intersection(args):
            return "git config changes are not allowed; ask the user to run it"
    if name in INLINE_CODE and INLINE_CODE[name] in args:
        for tok in args:
            if re.search(r"\.claude\b|CLAUDE(\.local)?\.md|AGENTS\.md|\.mcp\.json|\.git/(hooks|config)|\.orchestrator/\.gitignore", tok):
                return "inline script touching a protected path"

    operands = [a for a in args if not a.startswith("-")]
    if name in WRITE_ALL_ARGS:
        for tok in args:
            reason = protected_token(tok, cwd)
            if reason:
                return f"'{name}' on a protected path ({reason})"
    if name in WRITE_LAST_ARG and operands:
        reason = protected_token(operands[-1], cwd)
        if reason:
            return f"'{name}' into a protected path ({reason})"
    if name == "dd":
        for tok in args:
            if tok.startswith("of="):
                reason = protected_token(tok, cwd)
                if reason:
                    return f"'dd' into a protected path ({reason})"
    if name in IN_PLACE_EDITORS and any(re.match(r"-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args):
        for tok in operands:
            reason = protected_token(tok, cwd)
            if reason:
                return f"in-place edit of a protected path ({reason})"
    if name == "git" and args[:1] and args[0] in {"checkout", "restore", "rm", "mv"}:
        for tok in args[1:]:
            reason = protected_token(tok, cwd)
            if reason:
                return f"'git {args[0]}' on a protected path ({reason})"
    return None


def check_bash(command, cwd):
    for seg in segments(tokenize(command)):
        reason = check_segment(seg, cwd)
        if reason:
            return f"{reason}. Command: {command[:200]}"
    return None


def evaluate(data):
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    agent_type = data.get("agent_type")
    if tool_name in FILE_TOOLS:
        return check_file_tool(tool_name, tool_input, cwd, agent_type)
    if tool_name == "Bash":
        return check_bash(tool_input.get("command", ""), cwd)
    return None


def main():
    try:
        data = json.load(sys.stdin)
        reason = evaluate(data)
    except Exception as exc:  # fail closed
        reason = f"internal error ({type(exc).__name__}: {exc}); denying to be safe"
    if reason:
        json.dump(decide(reason), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
