---
id: LESSON-821
title: "A pre-merge gate must never source code from the tree, even behind guards, and must judge the commits that merge, not the disk"
component: "adlc/bugfix"
domain: "adlc"
stack: ["sh", "python", "git"]
concerns: ["security", "structural-enforcement", "silent-failure"]
tags: ["gate", "trust-boundary", "self-certification", "skip-worktree", "symlink", "gitignore", "match-head-commit", "REQ-691"]
req: REQ-691
created: 2026-11-05
updated: 2026-11-05
kind: "process"
evidence: "REQ-691 Phase 5, three passes before merge 9973c66. The first fix followed LESSON-718's third bullet: it sourced the vendored partial after guards for a clean tree, a pushed HEAD and no diff under .adlc/partials. The re-verify got a forged partial run past those guards through a symlinked .adlc, a gitignored file and a skip-worktree entry. The redesign sources only $ADLC_TOOLKIT_ROOT partials, and test_gate_never_runs_code_from_the_tree fails on the old fence and passes on the new. The second re-check found that a skip-worktree bug report could carry a waiver the PR lacked (test_require_recorded_needs_the_report_committed_as_on_disk fails before the fix), and that the merge was not pinned to the head the gate checked."
confidence: "high"
enforcement: "test:tools/lint-skills/tests/test_bugfix_regression_contract.py"
generalizes: [LESSON-718]
supersedes: []
---

## What Happened

REQ-691 added a regression-test gate to `/bugfix` Phase 6 and hardened it three times.

1. **First pass.** It sourced the vendored `.adlc/partials/regression-check.sh` and read the setting from the worktree.
2. **Guards.** The fix added LESSON-718's guards: a clean tree, `HEAD` equal to the pushed branch, and no diff under `.adlc/partials`. The re-verify still ran a forged partial. A symlinked `.adlc`, a gitignored partial and a `skip-worktree` partial are each invisible to `git status` and to `git diff`, because git reports only what it tracks, the way it records it.
3. **Redesign.** The gate now sources nothing from the tree. The next re-check found two more gaps:
   - A `skip-worktree` bug report could carry a waiver that existed only on disk.
   - Phase 6 merged the PR without `--match-head-commit`, so a later push would merge a head nobody checked.

## Lesson

Guards cannot make tree code safe to run, because the guards are built on git's view of the tree, and the tree can hide from git. So:

- **Code.** Source and execute only the installed toolkit. The branch supplies data, never code. Drop "source after guards" from the design entirely; don't add more guards to it.
- **Data.** Judge it as committed. Read the data the gate certifies (here the bug report and the test files) at `HEAD` or compare it to `HEAD`. `git status` says nothing about `skip-worktree`, `assume-unchanged` or ignored paths.
- **The merge.** Pin it to what was certified. Have the gate print the oid it checked, merge with `--match-head-commit <oid>`, and send any rebase back through the gate.
- **Git calls.** Turn off branch-supplied hooks and monitors on the gate's own git calls: `-c core.hooksPath=/dev/null` and `-c core.fsmonitor=false`.
- **Mode first.** Read the mode before any guard, so an opted-out project gets no new stop.

## Why It Matters

Each gap was a one-file change the gate didn't count, and each produced a pass for a bug with no recorded test. Adding guards turned each review pass into a new bypass; making the design structural ended the loop. `proceed/phases-lite.md`'s lane-check fence still uses the guard design LESSON-718 recommended, and has the same gaps.

## Applies When

When writing or reviewing any check that runs against a branch, worktree or PR and decides whether it may merge or advance: lane checks, regression gates, trial merges, verifiers. Especially when the design says "source X only after the guards pass", or when the check reads files from disk that the merge will take from commits.
