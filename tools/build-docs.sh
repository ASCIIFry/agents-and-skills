#!/usr/bin/env bash
# Generates Markdown copies of all org documents in this repository, using
# the plugin's org2md.sh. The .org files are the source; never edit the
# generated .md files.
# Usage: tools/build-docs.sh [--check]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

mapfile -d '' files < <(find . -name '*.org' -not -path './.git/*' -print0 | sort -z)
exec plugins/orchestrator/scripts/org2md.sh "$@" "${files[@]}"
