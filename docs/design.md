<!-- Generated from design.org by tools/build-docs.sh. Do not edit. -->

# Orchestrator Agent Pattern for Claude Code — Design

## Status

Draft for review. Nothing in this document is implemented yet. The implementation starts after the design is approved; see [Implementation plan](#implementation-plan).

## Goals and non-goals

### Goals

- Task orchestration in Claude Code: one orchestrator that classifies a task, plans it, delegates work packages to cheap specialised workers, checks the results and reports back.
- Cost efficiency through model tiering and a strict delegation policy.
- Context efficiency: small prompts, compact results, large output in files.
- Security: agents must not be able to change their own configuration.
- Extensibility: new capabilities (cloud security, pentesting, documentation, …) can be added later as separate plugins without touching the core.
- Usable on Linux (CLI) and from the Claude mobile app via Remote Control.

### Non-goals (for now)

- Portability to other harnesses (OpenCode etc.).
- Domain capabilities (Azure, AWS, pentest, documentation skills). They come later as separate plugins; see [Extensibility](#extensibility).
- Pure cloud sessions (claude.ai/code without a local machine). Cloud sessions do not install plugins; see [Mobile usage](#mobile-usage).

## Decisions

| \#  | Topic                | Decision                                                            |
|-----|----------------------|---------------------------------------------------------------------|
| 1   | Models               | Orchestrator: Sonnet. Planner: Opus. Workers: Haiku or Sonnet.      |
| 2   | Activation           | Opt-in per session: `claude --agent orchestrator`                   |
| 3   | Approval checkpoints | Plan of large tasks, pushes, destructive and outward-facing actions |
| 4   | Run state            | Git-ignored by default; per-repo opt-in to commit it                |
| 5   | Distribution         | Claude Code plugin in a private marketplace (this repository)       |
| 6   | Mobile               | Remote Control of a local CLI session                               |
| 7   | Hierarchy            | Flat: only the orchestrator delegates; workers have no `Agent` tool |
| 8   | Documentation        | Org-mode is the source; Markdown copies are generated for mobile    |

## Architecture overview

``` example
       you (terminal or phone via Remote Control)
                         │
                         ▼
┌──────────────── orchestrator (main session, Sonnet) ───────────────┐
│ classify → plan → approve → delegate → verify → report             │
│ run state: .orchestrator/runs/<id>.org                             │
└───┬──────────┬──────────────┬──────────────┬──────────────┬────────┘
    ▼          ▼              ▼              ▼              ▼
explorer    planner       implementer     verifier      researcher
(Haiku)     (Opus)        (Sonnet)        (Sonnet)      (Haiku)
read-only   read-only     read + write    read + tests  web + read

plugin hooks (apply to the main session AND to every subagent):
  PreToolUse  → config-guard  (deny edits to configuration)
  PreToolUse  → checkpoint    (force approval for risky commands)
  SubagentStart/Stop → subagent log (cost tuning)
```

The orchestrator is the **main session**, started with `--agent`. Its prompt replaces Claude Code's default system prompt entirely, so it has to carry the essentials itself (see [Orchestrator](#orchestrator)). Subagents could nest up to three levels deep, but we keep the hierarchy flat on purpose: nested delegation multiplies cost and makes results hard to trace.

## Agent roster

All agents live in the plugin's `agents/` directory. Plugin agents ignore the frontmatter fields `hooks`, `permissionMode` and `mcpServers`, so all guardrails are plugin-level hooks (see [Security](#security)). The `tools` list is honoured and is the main least-privilege lever.

| Agent        | Model  | Effort | Tools                                         | Purpose                                               |
|--------------|--------|--------|-----------------------------------------------|-------------------------------------------------------|
| orchestrator | sonnet | medium | all (main session)                            | Classify, plan small tasks, delegate, verify, report  |
| planner      | opus   | high   | Read, Grep, Glob, Bash (read-only use)        | Break large tasks into work packages with DoD         |
| explorer     | haiku  | low    | Read, Grep, Glob, Bash (read-only use)        | Locate code/files, gather facts cheaply               |
| implementer  | sonnet | medium | Read, Grep, Glob, Edit, Write, Bash           | Carry out exactly one bounded work package            |
| verifier     | sonnet | medium | Read, Grep, Glob, Bash                        | Independent check: tests, review, "is it really done" |
| researcher   | haiku  | low    | WebSearch, WebFetch, Read, Write (notes only) | External information: docs, APIs, advisories          |

Notes:

- No worker has the `Agent` tool, which enforces the flat hierarchy.
- "Bash (read-only use)" is enforced by prompt only. Claude Code has no read-only Bash mode per agent; the [Config guard](#config-guard) and [Checkpoint hook](#checkpoint-hook) still apply.
- The `researcher` writes notes only below `.orchestrator/`. Web content is untrusted input; the researcher returns facts with sources, never instructions for other agents.
- Built-in `Explore` and `Plan` agents stay available. Own versions exist so that model, tools and output format are under our control.

## Orchestrator

### Workflow

1.  **Classify** the request (see [Delegation policy](#delegation-policy)).
2.  **Plan**: trivial tasks need no plan. Medium tasks get a short plan in the conversation. Large tasks go to the `planner`.
3.  **Approve**: for large tasks, present the plan (goal, work packages, risks, estimated effort) and wait for explicit approval.
4.  **Delegate**: one task brief per work package (see [Task brief](#task-brief)). Independent packages run in parallel. Parallel writers run with worktree isolation (the `Agent` tool's `isolation: worktree`), or on strictly disjoint files.
5.  **Verify**: the `verifier` checks the combined result against the definition of done. Failures go back to step 4 (see [Failure handling](#failure-handling)).
6.  **Report**: a short summary (what changed, how it was verified, open points), and the run file is updated.

### Delegation policy

Every subagent starts with an empty context and has to rebuild it, so delegation has a cost. Rules:

| Class   | Signals                                                                     | Handling                                                            |
|---------|-----------------------------------------------------------------------------|---------------------------------------------------------------------|
| Trivial | question answerable from context, one-file change, fewer than ~5 tool calls | Orchestrator does it itself                                         |
| Medium  | a few files, clear goal, low risk                                           | Optional explorer → implementer → verifier; no plan approval        |
| Large   | many files, unclear approach, risky, or several independent packages        | planner → approval → implementers (parallel if possible) → verifier |

Additional rules:

- Broad searches ("where is X used", "how does Y work") always go to the `explorer`, so search results never flood the orchestrator's context.
- Never delegate the same question twice. Reuse earlier results from the run file.
- The orchestrator reads raw files only when it needs them to write a brief or to judge a result.

### Task brief

Fixed structure passed to each subagent:

``` example
GOAL:        one sentence
CONTEXT:     relevant facts, file paths, earlier results (no raw dumps)
CONSTRAINTS: what must not change; tools and paths in scope
DONE WHEN:   verifiable criteria
OUTPUT:      the result contract (below) plus anything task-specific
```

### Result contract

Every worker ends with this block and nothing else of substance:

``` example
STATUS:   done | partial | blocked
SUMMARY:  ≤ 5 lines
CHANGES:  files touched (implementer only)
EVIDENCE: commands run and their outcome (tests, checks)
OPEN:     questions, risks, follow-ups
ARTIFACTS: paths to large outputs written under .orchestrator/
```

Large outputs (logs, long search results, research notes) are written to `.orchestrator/artifacts/<run-id>/` and referenced by path.

### Failure handling

- At most 2 attempts per work package with the same agent and model.
- Then escalate once: Sonnet → Opus (`model` override on the `Agent` call).
- Then stop and ask the user, with a short diagnosis.
- Each worker gets `maxTurns` in its frontmatter as a runaway guard. `maxTurns` leaves the subagent resumable, so a hit limit is not lost work.

### Approval checkpoints

| Checkpoint                                         | Enforced by                                          |
|----------------------------------------------------|------------------------------------------------------|
| Plan of a large task                               | Orchestrator prompt (`AskUserQuestion`)              |
| `git push`, history rewrites, branch deletion      | [Checkpoint hook](#checkpoint-hook) (`ask` decision) |
| Recursive deletes, `git clean`, `git reset --hard` | [Checkpoint hook](#checkpoint-hook)                  |
| Outward-facing actions (PR create/merge, releases) | [Checkpoint hook](#checkpoint-hook)                  |

Approval prompts are short enough to answer on a phone.

## Run state

### What it is

For medium and large tasks, the orchestrator keeps one file per run: `.orchestrator/runs/<YYYY-MM-DD>-<slug>.org`. It holds the goal, the approved plan, the work packages with their status, decisions, and the workers' result summaries. It lets a plan survive context compaction, lets a new session resume a run, and records what happened.

Layout in a project repository:

``` example
.orchestrator/
├── .gitignore      ← managed by the plugin; contains "*" in ignore mode
├── runs/           ← one .org file per run
└── artifacts/      ← large outputs, one subdirectory per run
```

### Default: ignored

When it creates its first run file, the orchestrator calls `${CLAUDE_PLUGIN_ROOT}/scripts/run-init.sh`. The script creates `.orchestrator/` and writes `.orchestrator/.gitignore` with the content `*`, plus a marker comment. Because the ignore file sits inside the directory, the repository's own `.gitignore` is never touched.

### Enabling commit mode for a repository

1.  In that repository, add to `.claude/settings.json` (shared, committed) or `.claude/settings.local.json` (only you, not committed):

    ``` json
    {
      "env": {
        "ORCHESTRATOR_RUN_STATE": "commit"
      }
    }
    ```

2.  Start a new session, and trust the folder when prompted. Claude Code applies project `env` values only after workspace trust.

3.  On the next run, `run-init.sh` removes the plugin-managed `.orchestrator/.gitignore` (only if it carries the plugin marker), and run files are committed together with the work on the branch.

To switch back, remove the key and start a new session; the script recreates the ignore file. Files that are already committed stay in git history. Check them for confidential content before pushing.

Agents cannot flip this switch: `.claude/settings*.json` and `.orchestrator/.gitignore` are protected by the [Config guard](#config-guard), and Bash commands that set `ORCHESTRATOR_RUN_STATE` are denied.

## Security

### Threat model

- An agent edits its own prompt, settings or hooks, for example to widen its tools or to disable a guard, or does so because prompt-injected content told it to.
- An agent reaches the same effect indirectly: via Bash (`sed -i`, `>`, `cp`, `mv`), via git config (`core.hooksPath`, aliases), via git hooks, or by updating the plugin itself.
- An agent performs irreversible or outward-facing actions without approval.

### Layers

1.  **Plugin cache**: Claude Code runs the installed copy in `~/.claude/plugins/`, not the files in this repository. Editing this repository does not change the live configuration until the user runs a plugin update. Consequence: for daily use, add the marketplace from GitHub, not from a local directory, because a local-directory marketplace loads plugins in place.
2.  **Least privilege** through each agent's `tools` list.
3.  **[Config guard](#config-guard)**: a plugin `PreToolUse` hook that denies writes to configuration paths. It applies to the main session and to every subagent.
4.  **[Checkpoint hook](#checkpoint-hook)**: forces an approval prompt for risky commands.
5.  **Recommended user settings** (documented in the README, installed by the user and not by an agent): `permissions.deny` rules for `Edit=/=Write` on the protected paths, as a second, hook-independent layer.

### Config guard

Matcher: `Edit|Write|NotebookEdit|Bash`. Protected paths:

- `~/.claude/**` (user settings, agents, skills, plugin cache, the plugin itself)
- `<project>/.claude/**`, `CLAUDE.md`, `CLAUDE.local.md`, `.mcp.json`
- `<project>/.git/hooks/**`, `<project>/.git/config`
- `<project>/.orchestrator/.gitignore`

For file tools, the target path is resolved (symlinks, `..`) and matched. For Bash, the command is denied when it mentions a protected path together with a writing operation (redirection, `tee`, `sed -i`, `cp`, `mv`, `rm`, `ln`, `chmod`, `truncate`, interpreter one-liners). It is also denied when it runs `claude plugin …`, `claude config …`, `git config`, or sets `ORCHESTRATOR_RUN_STATE`.

Limitation, stated plainly: Bash analysis is a heuristic. A determined obfuscation, such as a generated script, can get past it. It stops the common and accidental cases. The hard boundaries are layers 1 and 5 and, optionally, OS-level measures such as the Claude Code sandbox.

Implementation: Python 3, standard library only, with unit tests.

### Checkpoint hook

Matcher: `Bash`. It returns `permissionDecision: "ask"` (never "allow") for `git push`, `git reset --hard`, `git clean -f…`, `git branch -D`, `git rebase`, `rm -r…`, `gh pr create|merge`, `gh release …`, and similar outward-facing commands. The list lives in one data file so that later capability plugins can add their own checkpoints in their own hooks. Whether `ask` still prompts in `bypassPermissions` mode has to be verified (see [Open points to verify](#open-points-to-verify)).

## Cost and context efficiency

- Model tiering as in the [Agent roster](#agent-roster); `effort` per agent.
- Delegation policy prevents spawning for trivial work.
- Compact briefs and results; large output goes to files.
- Short, stable prompts: orchestrator ≲ 2 000 tokens, workers ≲ 600 tokens each. Stable prefixes improve prompt caching.
- Agent `description` fields are one or two lines each; the orchestrator sees all of them on every turn.
- No MCP servers in the core plugin.
- **Subagent log**: `SubagentStart` and `SubagentStop` hooks append timestamp, session, agent type and agent id to `${CLAUDE_PLUGIN_DATA}/subagents.jsonl`. That gives call counts and durations per agent for tuning. Token-level cost comes from Claude Code's own usage reporting.

## Mobile usage

Cloud sessions (claude.ai/code, the mobile app's Code tab) do not install plugins, so the plugin is not available there. Mobile use goes through **Remote Control**: start the session locally, then connect from the Claude app. The plugin, hooks, local tools and run files all work unchanged, because everything runs on the Linux machine.

``` bash
claude --agent orchestrator     # then run /remote-control in the session
```

The machine has to stay on while you steer the session from the phone.

## Documentation format

All human-facing documents are written in org-mode. The Claude mobile app and GitHub's mobile view do not render org well, so every `.org` file gets a generated `.md` copy next to it (`README.org` → `README.md`, `docs/design.org` → `docs/design.md`).

- Generator: `tools/build-docs.sh`, which runs pandoc with the Lua filter `tools/org-links.lua`. The filter turns in-file heading links (`[[Heading]]`) into working GitHub anchors, umlauts included.
- The `.md` files carry a "Generated … Do not edit" header. Changes are always made in the `.org` file, then `tools/build-docs.sh` is run and both files are committed together.
- CI (`.github/workflows/docs.yml`) runs `tools/build-docs.sh --check` and fails if a Markdown copy is out of date.
- The repository's `CLAUDE.md` states this rule, so agents working on this repository follow it too.
- Run files (see [Run state](#run-state)) are working files, not documentation, and stay org-only.

## Repository layout

``` example
agents-and-skills/                   ← this repo = the marketplace
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   └── orchestrator/
│       ├── .claude-plugin/plugin.json
│       ├── agents/
│       │   ├── orchestrator.md
│       │   ├── planner.md
│       │   ├── explorer.md
│       │   ├── implementer.md
│       │   ├── verifier.md
│       │   └── researcher.md
│       ├── hooks/hooks.json
│       └── scripts/
│           ├── config_guard.py
│           ├── checkpoint.py
│           ├── checkpoints.json
│           ├── run-init.sh
│           └── log_subagent.py
├── tests/                           ← unit tests for the hook scripts
├── tools/
│   ├── build-docs.sh                ← org → Markdown generator
│   └── org-links.lua                ← pandoc filter for heading links
├── .github/workflows/docs.yml       ← checks that Markdown copies are current
├── docs/
│   ├── design.org / design.md       ← this document (.md is generated)
│   └── conventions.org / .md        ← how to write agents, skills, plugins
├── CLAUDE.md                        ← rules for agents working on this repo
└── README.org / README.md           ← installation and usage
```

Executables go into `scripts/` and not `bin/`, because claude.ai refuses plugins that contain a top-level `bin/`.

## Installation (summary)

Full steps go into `README.org`.

1.  Make sure git can reach the private repository without prompting: an SSH key loaded in `ssh-agent`, or `gh auth login && gh auth setup-git`.
2.  `claude plugin marketplace add asciifry/agents-and-skills`
3.  `claude plugin install orchestrator@<marketplace-name>`
4.  Optional: add the recommended `permissions.deny` rules to `~/.claude/settings.json`.
5.  Start with `claude --agent orchestrator`.

Updates: the plugin's `version` is bumped on every release, then `claude plugin update orchestrator@<marketplace-name>`. Auto-update is off by default and can be enabled in `/plugin`.

Development of this repository: test changes with `claude --plugin-dir ./plugins/orchestrator` before releasing.

## Extensibility

- **Capabilities as separate plugins** in the same marketplace, for example `cloud-security`, `pentest`, `docs`. Each ships skills (knowledge, loaded on demand) and, only where needed, specialist agents.
- The orchestrator routes by agent descriptions. Claude Code lists every enabled agent to it, so new agents need no change to the core.
- Rules for new components go in `docs/conventions.org`:
  - agents: least-privilege `tools`, no `Agent` tool, result contract, one-to-two-line description
  - skills: short frontmatter, body loaded on trigger, details in `references/`, scripts executed rather than read
  - hooks: own scripts per plugin, tests required
- The checkpoint list and the protected paths can be extended by capability plugins through their own hooks, without editing the core.

## Implementation plan

1.  Marketplace and plugin skeleton, six agent prompts, `README.org` (with its generated `README.md`).
2.  Hooks: config guard, checkpoint hook and `run-init.sh`, with unit tests.
3.  Subagent log, `docs/conventions.org`, and an end-to-end smoke test with `--plugin-dir` (medium and large sample tasks).
4.  Tag the first release (`version` 0.1.0).

## Open points to verify

Verify these during implementation; the design adapts if needed.

- `claude --agent orchestrator` resolves a plugin agent by its bare name (the docs say it does, with `plugin:agent` to disambiguate).
- Whether `permissionDecision: "ask"` still prompts under `bypassPermissions` and `auto` mode.
- The exact command to enable Remote Control from within a session.
- Whether the `Agent` tool's `model` override is available for escalation.
