---
id: REQ-435
title: "lint-skills worktree-root scan — supplementary regression coverage (core superseded by REQ-436)"
status: complete
deployable: true
created: 2026-05-16
updated: 2026-05-16
component: "adlc/tools/lint-skills"
domain: "adlc/lint"
stack: ["python", "bash"]
concerns: ["correctness", "testing", "verify"]
tags: ["lint-skills", "worktree", "directory-walk", "skip-list", "silent-failure", "analyze-step-1.9", "regression-test", "superseded"]
supersededBy: REQ-436
---

## Description

**Originally:** `tools/lint-skills/check.py` `find_skill_files()` evaluated
the `SKIP_DIR_PARTS = {.git,.worktrees,node_modules}` exclusion against the
**absolute** path's parts. Because `--root` is resolved to an absolute path
and `/proceed` runs every phase inside `.worktrees/REQ-xxx`, the
`.worktrees` segment in the root prefix matched and **every** `SKILL.md`
was skipped — the linter scanned zero files and exited 0, making
`/analyze` Step 1.9 silently vacuous in every `/proceed` run. Discovered
during REQ-433 (architecture.md ADR-3b) and deferred there.

**What actually happened:** while this REQ's pipeline was running, **REQ-436
(PR #53) merged to `main` and fixed the identical defect** — REQ-436 ADR-5
explicitly "executes REQ-433 ADR-3b's deferred follow-up" (the same
deferral cited above). REQ-436 made `find_skill_files()` root-relative
(`if any(part in SKIP_DIR_PARTS for part in rel.parts[:-1])`), added
`test_root_under_worktrees_still_scanned` +
`test_descendant_worktrees_still_skipped`, and the generalization is
captured on `main` as `LESSON-019-presence-guards-rot-when-indirection-moves`
(point #2). Separately, BUG-054 (PR #55) fixed the absolute-path
info-disclosure this REQ's verify phase had flagged.

The core fix, equivalent regression tests, and the lesson are therefore
**already on `main`**. To avoid shipping a duplicate/competing
implementation, REQ-435's scope was reduced (with explicit user approval
during the pipeline's merge-conflict halt) to the two regression tests that
REQ-436 did **not** include and that have standalone value.

## System Model

_No data model — CLI linter. The deliverable is two supplementary pytest
cases against the already-fixed `find_skill_files()`._

## Business Rules

- [x] BR-4 (residual): `/analyze` Step 1.9 invokes
  `tools/lint-skills/check.sh` with CWD inside the worktree and **no
  `--root`**. A regression test must exercise that exact wrapper + CWD-default
  entrypoint (REQ-436's test only exercises `check.py` via `_run` with an
  explicit `--root`).
- [x] BR-5 (residual): the symlink-escape defense
  (`resolved.relative_to(root_resolved)` guard) must stay in force; a
  regression test must fail if it is removed (REQ-436 added no symlink test).

## Acceptance Criteria

- [x] `test_check_sh_wrapper_nonvacuous_from_worktree_cwd` added — runs
  `sh check.sh` with CWD inside a `.worktrees/REQ-xxx`-shaped tree, no
  `--root`, asserts non-vacuous (the exact Step 1.9 path).
- [x] `test_symlink_outside_root_is_excluded` added — load-bearing BR-5
  guard (real in-root skill found; symlink escaping root excluded).
- [x] No duplicate fix, no duplicate lesson, no `.next-lesson` bump — branch
  is `main` + these two tests only.
- [x] `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/
  tools/lint-skills/tests/ -q` fully green (93 passed).

## External Dependencies

- None.

## Assumptions

- REQ-436's root-relative `find_skill_files()` is the canonical fix; this
  REQ builds regression coverage on top of it, not a competing fix.

## Open Questions

- None (resolved at the pipeline merge-conflict halt: user chose to salvage
  the two net-new tests and abandon the duplicated fix/lesson/core-tests).

## Out of Scope

- The `find_skill_files()` fix itself (shipped by REQ-436).
- A skip-list/worktree-root LESSON (captured by `main`'s LESSON-019 #2).
- The io-error absolute-path leak (fixed by BUG-054, PR #55).
- Any change to `check.py` production code.

## Retrieved Context

- LESSON-016 (lesson): regression-guard fixture for the defended failure
  mode is load-bearing — applied to the residual BR-5 symlink test.
- LESSON-013 (lesson): silent-failure class (tool runs, matches nothing) —
  the original defect; now fixed upstream by REQ-436.
- REQ-436 / REQ-433 (specs, on `main`): the superseding fix and its
  deferred-follow-up origin.
