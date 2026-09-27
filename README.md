<!-- Generated from README.org by tools/build-docs.sh. Do not edit. -->

# agents-and-skills

A private Claude Code plugin marketplace. It currently holds one plugin, `orchestrator`, which implements the orchestrator agent pattern: a Sonnet main session classifies each task, plans it, delegates work packages to cheap worker agents, verifies the result and reports back.

The design and its reasoning are in `docs/design.org`. Rules for adding agents, skills and plugins are in `docs/conventions.org`.

## What you get

| Agent        | Model  | Can write             | Job                                                  |
|--------------|--------|-----------------------|------------------------------------------------------|
| orchestrator | Sonnet | yes (main session)    | Classify, plan, delegate, verify, report             |
| planner      | Opus   | no                    | Work packages with done criteria for large tasks     |
| explorer     | Haiku  | no                    | Cheap code search, returns facts with `path:line`    |
| implementer  | Sonnet | yes                   | Exactly one work package                             |
| verifier     | Sonnet | no                    | Independent check: tests, diff review, done criteria |
| researcher   | Haiku  | only `.orchestrator/` | Web research with sources                            |

Plus hooks that protect your configuration, turn risky commands into approval prompts, and log subagent runs. With the plugin enabled, every session pays about 340 tokens for the agent descriptions. The orchestrator's prompt (about 1 600 tokens) loads only when you start it.

## Installation

### Prerequisites

- Claude Code on Linux, `git`, `python3` (standard library only).
- Git access to this private repository without a prompt. Claude Code clones it non-interactively. Either:
  - an SSH key loaded in `ssh-agent` (host already in `known_hosts`), or
  - HTTPS with a stored credential: `gh auth login` and then `gh auth setup-git`.

### Install the plugin

``` bash
claude plugin marketplace add ASCIIFry/agents-and-skills
claude plugin install orchestrator@agents-and-skills
```

Install from GitHub, not from a local clone. A marketplace added from a local directory loads plugins in place, so an agent editing that clone would be editing its own live configuration. See [Security](#security).

### Recommended: permission deny rules

Add these rules to `~/.claude/settings.json` yourself; don't ask an agent to do it. They are a second layer that works without the plugin's hooks. Claude Code also applies them to Bash redirections and to file commands such as `sed` and `tee`.

``` json
{
  "permissions": {
    "deny": [
      "Edit(//**/.claude/settings*.json)",
      "Edit(//**/.claude/agents/**)",
      "Edit(//**/.claude/skills/**)",
      "Edit(//**/.claude/commands/**)",
      "Edit(//**/.claude/hooks/**)",
      "Edit(//**/.claude/rules/**)",
      "Edit(//**/.claude/output-styles/**)",
      "Edit(//**/.claude/plugins/**)",
      "Edit(//**/CLAUDE.md)",
      "Edit(//**/CLAUDE.local.md)",
      "Edit(//**/AGENTS.md)",
      "Edit(//**/.mcp.json)",
      "Edit(//**/.git/hooks/**)",
      "Edit(//**/.git/config)",
      "Edit(//**/.orchestrator/.gitignore)"
    ]
  }
}
```

If the file already has a `permissions.deny` list, merge the entries into it. The rules leave `.claude/worktrees/` editable on purpose: parallel implementers work there.

## Usage

### Start the orchestrator

``` bash
cd ~/src/some-repo
claude --agent orchestrator
```

If another plugin also ships an agent called `orchestrator`, use `claude --agent orchestrator:orchestrator`. A normal `claude` session is not affected. Only the hooks and the six agent descriptions are active there.

### Use it from your phone

Start the session with Remote Control, then open it in the Claude app:

``` bash
claude --agent orchestrator --remote-control
```

In a running session, `/remote-control` does the same. Everything still runs on your machine, so it has to stay on. Cloud sessions (claude.ai/code without Remote Control) don't install plugins, so the orchestrator is not available there.

### How it handles tasks

| Task size | Example                                  | What happens                                                   |
|-----------|------------------------------------------|----------------------------------------------------------------|
| Trivial   | "What does this function return?"        | The orchestrator answers or edits directly                     |
| Medium    | "Add input validation to the login form" | explorer → implementer → verifier, short plan in the reply     |
| Large     | "Migrate the API client to v2"           | planner → **your approval** → implementers → verifier → report |

You are also asked before any `git push`, history rewrite, recursive delete, PR or release action, or package publish.

## Run state

For medium and large tasks the orchestrator keeps a run file in the repository: `.orchestrator/runs/<date>-<slug>.org`. It holds the plan, the status of each work package, decisions, and short worker results. Large outputs go to `.orchestrator/artifacts/<run-id>/`. After a context compaction, or in a new session, the orchestrator reads the run file to continue.

### Default: not committed

The plugin writes `.orchestrator/.gitignore` with the content `*`, so nothing below `.orchestrator/` shows up in `git status`. Your repository's own `.gitignore` is not touched.

### Committing run state in a repository

Use this when you want the plan and its history to travel with the branch, for example to continue on another machine.

1.  Add the setting to the repository. For everyone who works in it, put it in `.claude/settings.json` and commit that file. For yourself only, use `.claude/settings.local.json`, which Claude Code keeps out of git:

    ``` json
    {
      "env": {
        "ORCHESTRATOR_RUN_STATE": "commit"
      }
    }
    ```

    If the file already exists, add the `env` key to it instead of replacing it.

2.  Start a new session with `claude --agent orchestrator`. If Claude Code asks whether you trust the folder, confirm; project `env` values apply only in trusted folders.

3.  On the next run the plugin removes its own `.orchestrator/.gitignore` (only if the plugin created it), and run files are committed with the work.

To switch back, remove the key and start a new session; the ignore file comes back on the next run. Run files that were already committed stay in git history. Check them for confidential content before you push.

Agents can't change this switch. The settings files and `.orchestrator/.gitignore` are protected, and commands that set `ORCHESTRATOR_RUN_STATE` are denied.

## Security

- **Live configuration is the installed copy.** Claude Code runs the plugin from `~/.claude/plugins/`. Changing this repository has no effect until **you** run `claude plugin update`.
- **Config guard hook** (`scripts/config_guard.py`) denies file-tool writes and common Bash writes to:
  - `.claude/` (except `worktrees/`, `projects/` and `plans/`) in the project and in `~`
  - `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `.mcp.json` and `.claude.json`, at any depth
  - `.git/hooks/`, `.git/config`, `~/.gitconfig`, `~/.config/git/`
  - `.orchestrator/.gitignore`

  It also denies `claude plugin|config|mcp|update|install`, `git config` changes, `core.hooksPath` overrides and changes to `ORCHESTRATOR_RUN_STATE`. It applies to the main session and to every subagent. If the hook itself fails, it denies.
- **Checkpoint hook** (`scripts/checkpoint.py`, patterns in `scripts/checkpoints.json`) turns risky commands into approval prompts, auto mode included. In `bypassPermissions` and `dontAsk` mode it **denies** them instead, because a prompt is not guaranteed there.
- **Least privilege**: only the orchestrator and the implementer can edit files. The researcher can write only below `.orchestrator/`.

Known limits:

- The Bash analysis is a heuristic. It stops common and accidental writes, not a deliberately obfuscated script. The hard boundaries are the installed plugin copy, your deny rules and, if you want OS-level enforcement, the Claude Code sandbox.
- Claude Code's auto memory (`~/.claude/projects/*/memory/`) stays writable, so memory keeps working. Memory is loaded into later sessions; turn it off with `autoMemoryEnabled: false` (or in `/memory`) if you don't want that.
- Agents can't edit any `CLAUDE.md` or `AGENTS.md`. Commands such as `/init` that write one need to be run in a session without the plugin, or you edit the file yourself.

## Updating

1.  Change the plugin in this repository and bump `version` in `plugins/orchestrator/.claude-plugin/plugin.json`. Without a version bump, installed copies don't update.

2.  Push, then on each machine:

    ``` bash
    claude plugin marketplace update agents-and-skills
    claude plugin update orchestrator@agents-and-skills
    ```

Automatic updates are off by default. You can turn them on in `/plugin` → Marketplaces → agents-and-skills → Enable auto-update.

## Cost monitoring

Every subagent start and stop is logged to `~/.claude/plugins/data/orchestrator-agents-and-skills/subagents.jsonl`. Summarise it with:

``` bash
tools/subagent-stats.py
```

It prints runs, total and median duration per agent. For token usage, use Claude Code's own `/cost` and `/usage`.

## Development

- Try changes without installing them: `claude --plugin-dir ./plugins/orchestrator --agent orchestrator`. In this mode the plugin loads from your working copy, so the "installed copy" protection doesn't apply.
- Hook tests: `python3 -m unittest discover -s tests`
- Manifest checks: `claude plugin validate .` and `claude plugin validate ./plugins/orchestrator`
- Documentation: edit the `.org` files only, then run `tools/build-docs.sh` to regenerate the `.md` copies. CI checks that they are in sync.

### Smoke test after installing or updating

1.  In a scratch repository, start `claude --agent orchestrator` and ask a trivial question. It should answer directly, without subagents.
2.  Ask for a medium change. You should see `explorer`, `implementer` and `verifier` runs, and a run file under `.orchestrator/runs/` that `git status` doesn't list.
3.  Ask it to "add a deny rule to .claude/settings.json". The config guard should block the edit, and the orchestrator should propose a diff instead.
4.  Ask it to push. You should get an approval prompt.
5.  Run `tools/subagent-stats.py` and check that the runs from step 2 appear.
