---
id: TASK-232
title: "Installer seams the engine calls"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-230]
repo: adlc-toolkit
---

## Description

Give both installers the entry points the engine needs, each reusing the one spelling already there: arg parsing, `--migrate-internal`, `--render`, `--venv-only`, and an `~/.agents/skills` that repoints from an earlier view that still exists.

## Files to Create/Modify

- `install.sh` — `--migrate-home`, `--back`, `--prune-backup`, `--migrate-internal`; `adlc_shim_text`; `login_rc_file`; the shim's pointer step; `ensure_agents_mount` repoints a live earlier view; the header
- `tools/delegate/install.sh` — `--venv-only <home>`, `--render <home> <outdir>`, wrapper and plist rendering in one function each
- `tools/adlc/tests/test_install_home.py` — the new modes, and a mount that repoints
- `tools/adlc/tests/test_install_shim.py` — the shim's pointer step, run for real

## Acceptance Criteria

- [ ] `install.sh` with no migrate flag behaves as before
- [ ] `--render` output equals what a full `tools/delegate/install.sh` writes
- [ ] `--venv-only` touches no rc file, CLAUDE.md, settings.json or launchd

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | tools/adlc/tests/test_install_home.py::test_venv_only_touches_nothing_else | yes |
| BR-7 | test-case | tools/adlc/tests/test_install_home.py::test_render_matches_full_install | yes |
| BR-8 | test-case | tools/adlc/tests/test_install_shim.py::test_shim_reads_the_pointer | yes |
| BR-13 | structural-check | `tools/lint-skills` adlc-home; `dash -n tools/delegate/install.sh` | no |

## Technical Notes

`install.sh` tolerates an unresolvable home on the migrate paths only: `--migrate-home` is the remediation for a dangling pointer, so it cannot die at the resolver. `exec` the engine so its exit code is the command's.
