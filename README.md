<!-- Generated from README.org. Edit the .org file, not this one. -->

# agents-and-skills

A private Claude Code plugin marketplace. It currently holds one plugin, `orchestrator`, which implements the orchestrator agent pattern: a Sonnet main session classifies each task, plans it, delegates work packages to cheap worker agents, verifies the result and reports back.

The design and its reasoning are in `docs/design.org`. Rules for adding agents, skills and plugins are in `docs/conventions.org`.

## What you get

| Agent        | Model  | Can write             | Job                                                  |
|--------------|--------|-----------------------|------------------------------------------------------|
| orchestrator | Sonnet | yes (main session)    | Classify, plan, delegate, verify, report             |
| analyst      | Opus   | only the spec         | Requirements spec and questions before planning      |
| planner      | Opus   | no                    | Work packages with done criteria for large tasks     |
| explorer     | Haiku  | no                    | Cheap code search, returns facts with `path:line`    |
| implementer  | Sonnet | yes                   | Exactly one work package                             |
| verifier     | Sonnet | no                    | Independent check: tests, diff review, done criteria |
| researcher   | Haiku  | only `.orchestrator/` | Web research with sources                            |

Plus the `requirements` skill (method and template for specifications), and hooks that protect your configuration, turn risky commands into approval prompts, and log subagent runs. With the plugin enabled, every session pays about 520 tokens for the agent and skill descriptions. The orchestrator's prompt (about 2 100 tokens) loads only when you start it, and a requirements analysis adds about 2 000 tokens per analyst run.

## Installation

### Prerequisites

- Claude Code on Linux, `git`, `python3` (standard library only).
- Optional: `pandoc`, for the Markdown copy of requirements specifications.
- Git access to this private repository without a prompt. Claude Code runs `git` non-interactively: a credential git would have to ask for makes the clone fail. Set up one of the two options in [Install the plugin](#install-the-plugin).

### Install the plugin

#### Over HTTPS

1.  Store a GitHub credential that git can use without prompting. Either use the GitHub CLI:

    ``` bash
    gh auth login          # choose HTTPS
    gh auth setup-git      # makes gh git's credential helper for github.com
    ```

    or a fine-grained personal access token limited to this repository with *Contents: Read-only*, stored in a credential helper. `libsecret` keeps it encrypted in your keyring, but the helper may need installing first (Fedora: `git-credential-libsecret`; Debian/Ubuntu: build it from `/usr/share/doc/git/contrib/credential/libsecret`). `store` needs nothing extra but keeps the token in plain text in `~/.git-credentials`.

    ``` bash
    git config --global credential.helper libsecret   # or: store
    printf 'protocol=https\nhost=github.com\nusername=ASCIIFry\npassword=%s\n' "$TOKEN" \
      | git credential approve
    ```

2.  Check that the clone works without a prompt:

    ``` bash
    GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/ASCIIFry/agents-and-skills.git HEAD
    ```

3.  Add the marketplace with the full HTTPS URL and install the plugin:

    ``` bash
    claude plugin marketplace add https://github.com/ASCIIFry/agents-and-skills.git
    claude plugin install orchestrator@agents-and-skills
    ```

The `owner/repo` shorthand tries SSH first and falls back to HTTPS. The full URL uses HTTPS directly. To keep the shorthand but skip the SSH probe, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`. To install from a branch other than the default branch, append `#<branch>` to the URL.

#### Over SSH

With a key loaded in `ssh-agent` and `github.com` in `known_hosts`:

``` bash
claude plugin marketplace add ASCIIFry/agents-and-skills
claude plugin install orchestrator@agents-and-skills
```

#### Either way

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
| Project   | "Build a tool that tracks my findings"   | analyst ⇄ you → **spec approval** → then as Large              |

You are also asked before any `git push`, history rewrite, recursive delete, PR or release action, or package publish.

## Requirements specification

For a new project, or a large task whose goal or scope is unclear, the orchestrator runs a requirements analysis before planning:

1.  The `analyst` (Opus) reads the existing code and docs and writes a draft of `docs/requirements.org`.
2.  You get at most 5 questions per round, each with a recommended answer, easy to answer on the phone. Everything that doesn't change scope, effort, risk or architecture becomes a documented assumption instead of a question. There are at most two rounds.
3.  You see a short summary and approve the specification. Only then does the `planner` start. It maps every work package to the requirement IDs (`REQ-001`, `NFR-001`), and the `verifier` checks their acceptance criteria.

The specification lives in the project and is committed with the code, unlike run files. The analyst also writes `docs/requirements.md` for reading on your phone; this needs `pandoc`. Later changes update the same file: new IDs for new requirements, retired IDs are never reused, and a change log records what changed. The method alone is also available in any session as the `requirements` skill.

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

Automatic updates are off by default. You can turn them on in `/plugin` → Marketplaces → agents-and-skills → Enable auto-update. Over HTTPS they need the stored credential from [Over HTTPS](#over-https). If git would have to prompt, the background update fails quietly and the installed copy stays as it is.

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
5.  Describe a small new project in two sentences. The `analyst` should return questions, the orchestrator should ask them with options, and `docs/requirements.org` and `.md` should appear for your approval.
6.  Run `tools/subagent-stats.py` and check that the runs from steps 2 and 5 appear.
