#!/usr/bin/env bash
# Creates the run file for an orchestrator run and applies the run-state mode.
#
# Usage: run-init.sh <slug>
# Prints the run id and the path of the run file.
#
# Run-state mode comes from ORCHESTRATOR_RUN_STATE, which the user sets per
# repository in .claude/settings.json or .claude/settings.local.json:
#   ignore (default)  .orchestrator/ is git-ignored via its own .gitignore
#   commit            run files are committed with the work
set -euo pipefail

marker="# managed by the orchestrator plugin"

slug="${1:-}"
if [[ ! "$slug" =~ ^[a-z0-9][a-z0-9-]{0,48}$ ]]; then
  echo "usage: run-init.sh <slug>  (lowercase letters, digits and dashes, max 49 chars)" >&2
  exit 64
fi

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
dir="$root/.orchestrator"
mode="${ORCHESTRATOR_RUN_STATE:-ignore}"
mkdir -p "$dir/runs"

case "$mode" in
  ignore)
    printf '%s (run state: ignore)\n*\n' "$marker" >"$dir/.gitignore"
    ;;
  commit)
    if [[ -f "$dir/.gitignore" ]]; then
      if head -n 1 "$dir/.gitignore" | grep -qF "$marker"; then
        rm -f "$dir/.gitignore"
      else
        echo "warning: $dir/.gitignore was not created by the plugin; left unchanged" >&2
      fi
    fi
    ;;
  *)
    echo "error: ORCHESTRATOR_RUN_STATE must be 'ignore' or 'commit', not '$mode'" >&2
    exit 64
    ;;
esac

id="$(date +%Y-%m-%d)-$slug"
run="$dir/runs/$id.org"
mkdir -p "$dir/artifacts/$id"

if [[ ! -e "$run" ]]; then
  cat >"$run" <<ORG
#+TITLE: $slug
#+DATE: $(date +%Y-%m-%d)

* Goal
* Plan
* Work packages
* Decisions
* Log
ORG
  echo "created run $id"
else
  echo "resumed run $id"
fi
echo "run id:    $id"
echo "run file:  $run"
echo "artifacts: $dir/artifacts/$id/"
echo "run state: $mode"
