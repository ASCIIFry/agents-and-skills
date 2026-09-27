# agents-and-skills

Claude Code plugin marketplace for the orchestrator agent pattern. The design is in `docs/design.org`.

## Documentation

- Human-facing documents are written in org-mode (`*.org`). Link to headings in the same file with `[[Heading]]`.
- Every `.org` file has a generated `.md` copy for reading on mobile. Never edit the `.md` files by hand.
- After changing any `.org` file, run `tools/build-docs.sh` and commit the `.org` and `.md` files together. CI fails if they are out of sync (`tools/build-docs.sh --check`).

## Checks before committing

- `python3 -m unittest discover -s tests` for the hook scripts.
- `claude plugin validate .` and `claude plugin validate ./plugins/orchestrator` after manifest or agent changes.
- Bump `version` in `plugins/orchestrator/.claude-plugin/plugin.json` for changes that should reach installed copies.
- Follow `docs/conventions.org` when adding agents, skills, hooks or plugins.
