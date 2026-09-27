#!/usr/bin/env python3
"""PreToolUse hook for Bash: require the user's approval for risky commands.

Matches each simple command against checkpoints.json. On a match it returns
"ask", which prompts the user (also in auto mode). In bypassPermissions and
dontAsk mode a prompt is not guaranteed, so it returns "deny" instead.

Fails closed: an internal error produces a deny decision.
"""

import json
import os
import re
import sys

sys.dont_write_bytecode = True  # keep the installed plugin directory unchanged
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_guard import segments, strip_prefixes, tokenize  # noqa: E402

NO_PROMPT_MODES = {"bypassPermissions", "dontAsk"}


def load_checkpoints():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoints.json")
    with open(path, encoding="utf-8") as fh:
        return [(re.compile(c["pattern"]), c["reason"]) for c in json.load(fh)["checkpoints"]]


def match(command, checkpoints):
    for seg in segments(tokenize(command)):
        cmd = strip_prefixes([t for t in seg if not (set(t) <= set("<>&|0123456789") and ">" in t)])
        if not cmd:
            continue
        cmd[0] = os.path.basename(cmd[0])
        simple = " ".join(cmd)
        for pattern, reason in checkpoints:
            if pattern.search(simple):
                return reason
    return None


def decision(kind, reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": reason,
        }
    }


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        command = (data.get("tool_input") or {}).get("command", "")
        reason = match(command, load_checkpoints())
        if not reason:
            return 0
        mode = data.get("permission_mode", "default")
        if mode in NO_PROMPT_MODES:
            out = decision("deny", f"checkpoint: this command {reason} and needs the user's approval, "
                                   f"which {mode} mode cannot ask for. Ask the user to run it or to switch modes.")
        else:
            out = decision("ask", f"checkpoint: this command {reason}.")
    except Exception as exc:  # fail closed
        out = decision("deny", f"checkpoint: internal error ({type(exc).__name__}: {exc}); denying to be safe")
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
