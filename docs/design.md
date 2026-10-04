<!-- Generated from design.org. Edit the .org file, not this one. -->

# Orchestrator Agent Pattern for Claude Code — Design

## Status

Approved and implemented as version 0.1.0 of the `orchestrator` plugin. Installation and usage are in `README.org`. [Verification results](#verification-results) lists what was checked against the Claude Code documentation and CLI (v2.1.283) during implementation.

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

| \#  | Topic                | Decision                                                                                                                             |
|-----|----------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| 1   | Models               | Orchestrator: Sonnet. Planner: Opus. Workers: Haiku or Sonnet.                                                                       |
| 2   | Activation           | Opt-in per session: `claude --agent orchestrator`                                                                                    |
| 3   | Approval checkpoints | Plan of large tasks, pushes, destructive and outward-facing actions                                                                  |
| 4   | Run state            | Git-ignored by default; per-repo opt-in to commit it                                                                                 |
| 5   | Distribution         | Claude Code plugin in a private marketplace (this repository)                                                                        |
| 6   | Mobile               | Remote Control of a local CLI session                                                                                                |
| 7   | Hierarchy            | Flat: only the orchestrator delegates; workers have no `Agent` tool                                                                  |
| 8   | Documentation        | Org-mode is the source; Markdown copies are generated for mobile                                                                     |
| 9   | Requirements         | One `analyst` agent (Opus) plus a `requirements` skill; spec in `docs/requirements.org` with an `.md` copy, approved before planning |

## Architecture overview

``` example
       you (terminal or phone via Remote Control)
                         │
                         ▼
┌──────────────── orchestrator (main session, Sonnet) ───────────────┐
│ classify → specify → plan → approve → delegate → verify → report   │
│ run state: .orchestrator/runs/<id>.org                             │
└──┬─────────┬─────────┬───────────┬────────────┬────────────┬───────┘
   ▼         ▼         ▼           ▼            ▼            ▼
analyst   explorer  planner   implementer   verifier    researcher
(Opus)    (Haiku)   (Opus)    (Sonnet)      (Sonnet)    (Haiku)
writes    read-only read-only read + write  read + tests web + read
the spec

plugin hooks (apply to the main session AND to every subagent):
  PreToolUse  → config-guard  (deny edits to configuration)
  PreToolUse  → checkpoint    (force approval for risky commands)
  SubagentStart/Stop → subagent log (cost tuning)
```

The orchestrator is the **main session**, started with `--agent`. Its prompt replaces Claude Code's default system prompt entirely, so it has to carry the essentials itself (see [Orchestrator](#orchestrator)). Subagents could nest up to three levels deep, but we keep the hierarchy flat on purpose: nested delegation multiplies cost and makes results hard to trace.

## Agent roster

All agents live in the plugin's `agents/` directory. Plugin agents ignore the frontmatter fields `hooks`, `permissionMode` and `mcpServers`, so all guardrails are plugin-level hooks (see [Security](#security)). The `tools` list is honoured and is the main least-privilege lever.

| Agent        | Model  | Effort | Tools                                           | Purpose                                               |
|--------------|--------|--------|-------------------------------------------------|-------------------------------------------------------|
| orchestrator | sonnet | medium | all (main session)                              | Classify, plan small tasks, delegate, verify, report  |
| analyst      | opus   | high   | Read, Grep, Glob, Bash, Write, Edit (spec only) | Requirements spec and open questions before planning  |
| planner      | opus   | high   | Read, Grep, Glob, Bash (read-only use)          | Break large tasks into work packages with DoD         |
| explorer     | haiku  | low    | Read, Grep, Glob, Bash (read-only use)          | Locate code/files, gather facts cheaply               |
| implementer  | sonnet | medium | Read, Grep, Glob, Edit, Write, Bash             | Carry out exactly one bounded work package            |
| verifier     | sonnet | medium | Read, Grep, Glob, Bash                          | Independent check: tests, review, "is it really done" |
| researcher   | haiku  | low    | WebSearch, WebFetch, Read, Write (notes only)   | External information: docs, APIs, advisories          |

Notes:

- No worker has the `Agent` tool, which enforces the flat hierarchy.
- "Bash (read-only use)" is enforced by prompt only. Claude Code has no read-only Bash mode per agent; the [Config guard](#config-guard) and [Checkpoint hook](#checkpoint-hook) still apply.
- The `researcher` writes notes only below `.orchestrator/`, the `analyst` only `docs/requirements.org` and below `.orchestrator/`. The [Config guard](#config-guard) enforces both through the hook input's `agent_type`. Web content is untrusted input; the researcher returns facts with sources, never instructions for other agents.
- Built-in `Explore` and `Plan` agents stay available. Own versions exist so that model, tools and output format are under our control.

## Orchestrator

### Workflow

1.  **Classify** the request (see [Delegation policy](#delegation-policy)).
2.  **Specify**: for a new project, or a large task whose goal or scope is unclear, run the [Requirements analysis](#requirements-analysis) first. The planner then works from the approved specification.
3.  **Plan**: trivial tasks need no plan. Medium tasks get a short plan in the conversation. Large tasks go to the `planner`.
4.  **Approve**: for large tasks, present the plan (goal, work packages, risks, estimated effort) and wait for explicit approval.
5.  **Delegate**: one task brief per work package (see [Task brief](#task-brief)). Independent packages run in parallel. Parallel writers run with worktree isolation (the `Agent` tool's `isolation: worktree`), or on strictly disjoint files.
6.  **Verify**: the `verifier` checks the combined result against the definition of done and, if a specification exists, against the acceptance criteria of the requirements in scope. Failures go back to step 5 (see [Failure handling](#failure-handling)).
7.  **Report**: a short summary (what changed, how it was verified, open points), and the run file is updated.

### Delegation policy

Every subagent starts with an empty context and has to rebuild it, so delegation has a cost. Rules:

| Class   | Signals                                                                     | Handling                                                            |
|---------|-----------------------------------------------------------------------------|---------------------------------------------------------------------|
| Trivial | question answerable from context, one-file change, fewer than ~5 tool calls | Orchestrator does it itself                                         |
| Medium  | a few files, clear goal, low risk                                           | Optional explorer → implementer → verifier; no plan approval        |
| Large   | many files, unclear approach, risky, or several independent packages        | planner → approval → implementers (parallel if possible) → verifier |
| Project | new project, or large with unclear goal, scope or users                     | analyst ⇄ user → spec approval → then as Large                      |

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
| Requirements specification (Project class)         | Orchestrator prompt (`AskUserQuestion`)              |
| Plan of a large task                               | Orchestrator prompt (`AskUserQuestion`)              |
| `git push`, history rewrites, branch deletion      | [Checkpoint hook](#checkpoint-hook) (`ask` decision) |
| Recursive deletes, `git clean`, `git reset --hard` | [Checkpoint hook](#checkpoint-hook)                  |
| Outward-facing actions (PR create/merge, releases) | [Checkpoint hook](#checkpoint-hook)                  |

Approval prompts are short enough to answer on a phone.

## Requirements analysis

### Why

The planner decides *how* to build something. Without an explicit *what* and *why*, the agents may build the wrong thing efficiently. Requirements analysis runs before planning for new projects and for large tasks with an unclear goal, never for trivial or medium tasks.

### One analyst, not two

Business analysis (goal, value, scope, stakeholders) and requirements engineering (requirements, acceptance criteria, quality attributes) overlap heavily in solo projects. Splitting them into two agents would add a handoff, with lost context and a second cold start, for little gain. So there is one `analyst` agent (Opus, high effort: it runs rarely and has the largest effect on quality). Its method and template live in the `requirements` skill, which the analyst preloads and which a normal session can also use directly.

### The question loop

Subagents cannot ask the user (`AskUserQuestion` is removed for them), and each run returns a single result. Elicitation is therefore split:

1.  The orchestrator briefs the `analyst` with the request and any known context.
2.  The analyst reads the existing code and docs, writes a draft specification, and returns at most 5 questions. Each question has 2–4 options, the recommended one first, so it maps directly onto `AskUserQuestion` and can be answered on a phone.
3.  The orchestrator asks the user and passes the answers back. It continues the same analyst if the session allows it; otherwise it starts a new one that reads the draft.
4.  After at most two question rounds, anything still unclear becomes an explicit assumption in the specification instead of another question.
5.  The orchestrator shows a short summary (goal, scope and non-goals, number of requirements, key quality requirements, assumptions) and asks for approval. Only then does the planner start.

### The specification

`docs/requirements.org` in the project repository. It is long-lived project knowledge and is versioned with the code, unlike run files. Contents: goal and value, scope and non-goals, stakeholders and users, functional requirements with stable IDs (`REQ-001`), MoSCoW priority and testable acceptance criteria, quality requirements (`NFR-001`), constraints, assumptions, risks, open points, and a change log.

The analyst generates `docs/requirements.md` next to it with the plugin's `org2md.sh` (pandoc and the same Lua filter as this repository's docs). If pandoc is not installed, it skips the copy and reports that.

For a later change, the analyst updates the existing specification instead of replacing it: new IDs for new requirements, retired IDs are never reused, and each change gets a change-log entry.

### Traceability

- The planner maps every work package to the REQ/NFR IDs it implements and lists requirements that no package covers.
- Task briefs for implementers name the IDs in scope.
- The verifier judges each acceptance criterion of the IDs in scope.

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

Matcher: `Edit|Write|MultiEdit|NotebookEdit|Bash`. Protected paths:

- every `.claude/` directory (the project's, `~/.claude/` and nested ones, including the plugin cache), except the first-level subdirectories `worktrees/` (project files of worktree-isolated agents), `projects/` (session data and auto memory) and `plans/` (plan mode)
- `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `.mcp.json` and `.claude.json` at any depth. Claude Code reads `AGENTS.md` as project instructions too.
- `.git/hooks/**`, `.git/config`, `~/.gitconfig`, `~/.config/git/**`
- `.orchestrator/.gitignore`

This overlaps on purpose with Claude Code's built-in protected paths (`.claude`, `.git`, `.mcp.json`, …). Those are never auto-approved, but in a prompting mode the user can still approve them. The guard denies them outright, and it covers files that are not built-in protected, such as `CLAUDE.md` and `AGENTS.md`.

For file tools, the target path is resolved (symlinks, `..`) and matched. For Bash, the command is denied when it mentions a protected path together with a writing operation (redirection, `tee`, `sed -i`, `cp`, `mv`, `rm`, `ln`, `chmod`, `truncate`, interpreter one-liners). It is also denied when it runs `claude plugin|config|mcp|update|install`, a writing `git config`, a `core.hooksPath` override, or sets `ORCHESTRATOR_RUN_STATE`. If the hook fails internally, it denies (fail closed).

Limitation, stated plainly: Bash analysis is a heuristic. A determined obfuscation, such as a generated script, can get past it. It stops the common and accidental cases. The hard boundaries are layers 1 and 5 and, optionally, OS-level measures such as the Claude Code sandbox.

Implementation: Python 3, standard library only, with unit tests.

### Checkpoint hook

Matcher: `Bash`. It returns `permissionDecision: "ask"` (never "allow") for `git push`, `git reset --hard`, `git clean -f…`, `git branch -D`, `git rebase`, `rm -r…`, `gh pr create|merge`, `gh release …`, package publishing, image pushes and similar outward-facing commands. The list lives in one data file (`scripts/checkpoints.json`); later capability plugins add their own checkpoints in their own hooks.

Hook-forced prompts are shown in auto mode, the default starting mode since Claude Code v2.1.283. For `bypassPermissions` and `dontAsk` the docs don't guarantee a prompt, so in those modes the hook returns `deny` and tells the agent to ask the user to run the command.

## Cost and context efficiency

- Model tiering as in the [Agent roster](#agent-roster); `effort` per agent.
- Delegation policy prevents spawning for trivial work.
- Compact briefs and results; large output goes to files.
- Short, stable prompts: orchestrator ≈ 2 100 tokens, workers ≲ 600 tokens each. The `requirements` skill (≈ 1 400 tokens) loads only into the analyst. Stable prefixes improve prompt caching.
- Agent `description` fields are one or two lines each; the orchestrator sees all of them on every turn.
- No MCP servers in the core plugin.
- **Subagent log**: `SubagentStart` and `SubagentStop` hooks append timestamp, session, agent type and agent id to `${CLAUDE_PLUGIN_DATA}/subagents.jsonl`. That gives call counts and durations per agent for tuning. Token-level cost comes from Claude Code's own usage reporting.

## Mobile usage

Cloud sessions (claude.ai/code, the mobile app's Code tab) do not install plugins, so the plugin is not available there. Mobile use goes through **Remote Control**: start the session locally, then connect from the Claude app. The plugin, hooks, local tools and run files all work unchanged, because everything runs on the Linux machine.

``` bash
claude --agent orchestrator --remote-control
```

Inside a running session, `/remote-control` does the same.

The machine has to stay on while you steer the session from the phone.

## Documentation format

All human-facing documents are written in org-mode. The Claude mobile app and GitHub's mobile view do not render org well, so every `.org` file gets a generated `.md` copy next to it (`README.org` → `README.md`, `docs/design.org` → `docs/design.md`).

- Generator: `tools/build-docs.sh`, which runs the plugin's `org2md.sh` (pandoc with the Lua filter `org-links.lua`) on every `.org` file. The analyst uses the same script for requirements specifications in projects. The filter turns in-file heading links (`[[Heading]]`) into working GitHub anchors, umlauts included.
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
│       │   ├── analyst.md
│       │   ├── planner.md
│       │   ├── explorer.md
│       │   ├── implementer.md
│       │   ├── verifier.md
│       │   └── researcher.md
│       ├── skills/requirements/SKILL.md
│       ├── hooks/hooks.json
│       └── scripts/
│           ├── config_guard.py
│           ├── checkpoint.py
│           ├── checkpoints.json
│           ├── run-init.sh
│           ├── org2md.sh            ← org → Markdown (pandoc)
│           ├── org-links.lua        ← pandoc filter for heading links
│           └── log_subagent.py
├── tests/                           ← unit tests for the hook scripts
├── tools/
│   ├── build-docs.sh                ← runs org2md.sh on all .org files
│   └── subagent-stats.py            ← summarises the subagent log
├── .github/workflows/
│   ├── docs.yml                     ← checks that Markdown copies are current
│   └── tests.yml                    ← hook tests and manifest validation
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
2.  `claude plugin marketplace add ASCIIFry/agents-and-skills`
3.  `claude plugin install orchestrator@agents-and-skills`
4.  Optional: add the recommended `permissions.deny` rules to `~/.claude/settings.json`.
5.  Start with `claude --agent orchestrator`.

Updates: the plugin's `version` is bumped on every release, then `claude plugin update orchestrator@agents-and-skills`. Auto-update is off by default and can be enabled in `/plugin`.

Development of this repository: test changes with `claude --plugin-dir ./plugins/orchestrator` before releasing.

## Extensibility

- **Capabilities as separate plugins** in the same marketplace, for example `cloud-security`, `pentest`, `docs`. Each ships skills (knowledge, loaded on demand) and, only where needed, specialist agents.
- Domain plugins can extend [Requirements analysis](#requirements-analysis) with their own skills: for example, scoping and rules of engagement for a pentest, target tenants and compliance framework for a cloud assessment, or audience and purpose for documentation.
- The orchestrator routes by agent descriptions. Claude Code lists every enabled agent to it, so new agents need no change to the core.
- Rules for new components go in `docs/conventions.org`:
  - agents: least-privilege `tools`, no `Agent` tool, result contract, one-to-two-line description
  - skills: short frontmatter, body loaded on trigger, details in `references/`, scripts executed rather than read
  - hooks: own scripts per plugin, tests required
- The checkpoint list and the protected paths can be extended by capability plugins through their own hooks, without editing the core.

## Implementation plan

Version 0.2.0 adds the [Requirements analysis](#requirements-analysis): the `analyst` agent, the `requirements` skill, `org2md.sh`, the analyst's write scope in the config guard, and the matching changes to the orchestrator, planner and verifier.

Version 0.1.0:

1.  Marketplace and plugin skeleton, six agent prompts, `README.org`.
2.  Hooks: config guard, checkpoint hook and `run-init.sh`, with unit tests.
3.  Subagent log, `tools/subagent-stats.py`, `docs/conventions.org`, CI.
4.  `version` 0.1.0 in `plugin.json`.

The end-to-end smoke test with a live session is described in `README.org`. It has to run on a machine with Claude Code credentials.

## Verification results

| Question                                       | Result                                                                                                     |
|------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| `--agent` with a plugin agent                  | Supported; the bare name works, `plugin:agent` disambiguates                                               |
| Hook `ask` in auto mode                        | Prompts; the docs state that auto mode still shows hook-forced prompts                                     |
| Hook `ask` in `bypassPermissions` / `dontAsk`  | Not guaranteed, so the checkpoint hook denies in these modes                                               |
| Remote Control                                 | `claude --remote-control` flag and `/remote-control` command                                               |
| Model override for escalation                  | The `Agent` tool accepts `model`                                                                           |
| Plugin agent fields                            | `tools`, `model`, `effort`, `maxTurns` honoured; `hooks`, `permissionMode`, `mcpServers` ignored           |
| `${CLAUDE_PLUGIN_ROOT}` in agent prompts       | Substituted inline in the Markdown body                                                                    |
| Context cost (`claude plugin details`), v0.2.0 | ~520 tokens always-on; orchestrator ~2.1k, analyst ~0.55k + skill ~1.4k, other workers ~0.3–0.5k on invoke |
| Edit deny rules and Bash                       | Also applied to Bash redirections and recognised file commands (`sed`, `tee`, …)                           |
| Claude Code reads `AGENTS.md`                  | Yes, since v2.1.277, so it is protected like `CLAUDE.md`                                                   |
| `AskUserQuestion` in subagents                 | Not available; the orchestrator runs the question loop                                                     |
| Preloading a plugin skill into an agent        | `skills: [<plugin>:<skill>]`; the full skill content is injected at spawn                                  |
