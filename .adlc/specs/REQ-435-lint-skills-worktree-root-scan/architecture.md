# Architecture — REQ-435 (reframed: supplementary coverage; core superseded by REQ-436)

## Context

This REQ originally designed a root-relative `find_skill_files()` fix
(ADR-1: `path.relative_to(root).parts`). During the pipeline's Phase 7,
`origin/main` was found to have advanced: **REQ-436 (PR #53)** had merged
the equivalent fix (ADR-5: `rel.parts[:-1]` on the resolved path, executing
REQ-433 ADR-3b's deferred follow-up), its regression tests
(`test_root_under_worktrees_still_scanned`,
`test_descendant_worktrees_still_skipped`), and the lesson
(`LESSON-019-presence-guards-rot-when-indirection-moves`, point #2).
**BUG-054 (PR #55)** had separately fixed the absolute-path info-disclosure
this REQ's verify flagged.

At the sanctioned merge-conflict halt the user chose to **salvage only the
two tests REQ-436 left out** and abandon the now-duplicate
fix/lesson/core-tests. The branch was reset to `origin/main` and rebuilt as
`main` + those two tests (no `check.py` production change).

## Key Decisions

### ADR-1 (reframed): No production-code change — defer entirely to REQ-436 ADR-5

REQ-436's `find_skill_files()` is canonical. Shipping REQ-435's independent
rewrite would create a competing implementation and risk regressing
REQ-436's more comprehensive `check.py` (which added `check_posix_fence`,
`check_cross_fence_fn`, partial-aware `check_canonical`). REQ-435 adds
**tests only**.

### ADR-2: Salvage exactly two tests with standalone value

- `test_check_sh_wrapper_nonvacuous_from_worktree_cwd`: REQ-436's test calls
  `check.py` via `_run` with an explicit `--root`. The real `/analyze`
  Step 1.9 path is `sh check.sh` with **no `--root`** and CWD = the
  worktree. This test exercises the wrapper + CWD-default surface REQ-436
  left untested — a genuine regression gap, and the exact thing the
  original task description asked to "verify" stays guarded permanently.
- `test_symlink_outside_root_is_excluded`: REQ-436 added no symlink-escape
  regression test. This locks BR-5 (the `resolved.relative_to(root_resolved)`
  guard) — load-bearing: a positive control (`realskill` found) proves the
  walker runs while the escaping symlink is excluded; removing the guard
  makes it fail.

## Applicable Lessons

- LESSON-013 — the original silent-failure class (now fixed upstream).
- LESSON-016 — regression-guard fixture for the defended failure mode is
  load-bearing → applied to the BR-5 symlink test's positive control.
- `main`'s LESSON-019 #2 — the worktree-root-skip generalization (already
  captured; this REQ does not duplicate it).

## Task Graph

```
TASK-047 (append the two supplementary regression tests to test_check.py)
```

TASK-048 (capture LESSON) is **cancelled** — superseded by `main`'s
LESSON-019. No `.adlc/.next-lesson` mutation.
