---
id: TASK-047
title: "Append two supplementary lint-skills regression tests (reframed)"
status: complete
parent: REQ-435
created: 2026-05-16
updated: 2026-05-16
dependencies: []
repo: adlc-toolkit
---

## Description

Reframed after REQ-436 (PR #53) merged the root-relative `find_skill_files()`
fix to `main` mid-pipeline. The original scope (rewrite `find_skill_files`)
is dropped — REQ-436 ADR-5 is canonical. This task now only appends the two
regression tests REQ-436 did not include.

## Files to Create/Modify

- `tools/lint-skills/tests/test_check.py` — append
  `test_check_sh_wrapper_nonvacuous_from_worktree_cwd` (the exact
  `sh check.sh` / no-`--root` / worktree-CWD Step 1.9 entrypoint) and
  `test_symlink_outside_root_is_excluded` (BR-5 symlink-escape guard,
  load-bearing). No `check.py` change.

## Acceptance Criteria

- [x] Both tests appended and passing against `main`'s REQ-436 `check.py`.
- [x] No production-code change; no LESSON; no `.adlc/.next-lesson` bump.
- [x] `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/
  tools/lint-skills/tests/ -q` fully green (93 passed).

## Technical Notes

- REQ-436's `test_root_under_worktrees_still_scanned` already covers the
  defect via `_run(--root)`; these two tests cover the wrapper/CWD-default
  path and the symlink-escape guard, both untested by REQ-436.
