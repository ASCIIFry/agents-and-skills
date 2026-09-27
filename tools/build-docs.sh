#!/usr/bin/env bash
# Generates Markdown copies of all org documents for reading on GitHub and
# mobile. The .org files are the source; never edit the generated .md files.
# Usage: tools/build-docs.sh [--check]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

check=false
[[ "${1:-}" == "--check" ]] && check=true

status=0
while IFS= read -r -d '' org; do
  md="${org%.org}.md"
  tmp="$(mktemp)"
  {
    printf '<!-- Generated from %s by tools/build-docs.sh. Do not edit. -->\n\n' "$(basename "$org")"
    pandoc --from org --to gfm --wrap=none --shift-heading-level-by=1 \
      --lua-filter tools/org-links.lua "$org"
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
done < <(find . -name '*.org' -not -path './.git/*' -print0 | sort -z)

exit "$status"
