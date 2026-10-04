#!/usr/bin/env bash
# Writes a GitHub-flavoured Markdown copy next to each given .org file, for
# reading on GitHub and on mobile. The .org file stays the source.
#
# Usage: org2md.sh [--check] FILE.org...
#   --check  write nothing; exit 1 if a .md copy is missing or out of date
# Exit 69 if pandoc is not installed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
check=false
if [[ "${1:-}" == "--check" ]]; then
  check=true
  shift
fi
if [[ $# -eq 0 ]]; then
  echo "usage: org2md.sh [--check] FILE.org..." >&2
  exit 64
fi
if ! command -v pandoc >/dev/null 2>&1; then
  echo "org2md: pandoc is not installed; no Markdown copy written" >&2
  exit 69
fi

status=0
for org in "$@"; do
  if [[ "$org" != *.org || ! -f "$org" ]]; then
    echo "org2md: not an .org file: $org" >&2
    exit 64
  fi
  md="${org%.org}.md"
  tmp="$(mktemp)"
  {
    printf '<!-- Generated from %s. Edit the .org file, not this one. -->\n\n' "$(basename "$org")"
    pandoc --from org --to gfm --wrap=none --shift-heading-level-by=1 \
      --lua-filter "$here/org-links.lua" "$org"
  } >"$tmp"
  if $check; then
    if ! cmp -s "$tmp" "$md"; then
      echo "out of date: $md" >&2
      status=1
    fi
    rm -f "$tmp"
  else
    mv "$tmp" "$md"
    echo "wrote $md"
  fi
done
exit "$status"
