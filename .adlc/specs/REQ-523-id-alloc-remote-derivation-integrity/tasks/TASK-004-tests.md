---
id: TASK-004
title: "AC test matrix: degraded-via-cmd-sub, lesson-no-gh, independent sources, ADO/git fallback, BR-9 translation"
status: draft
parent: REQ-523
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001, TASK-002, TASK-003]
repo: adlc-toolkit
---

## Description

Extend the offline test matrix to cover every REQ-523 acceptance criterion, with
multi-element fixtures throughout (BR-7), runnable under both bash and zsh.

## Files to Create/Modify

- `partials/tests/id-alloc.test.sh` — add cases for BR-1, BR-2, BR-3, BR-4, BR-5,
  and the recheck-degraded case.
- `partials/tests/forge.test.sh` — add the BR-9 ADO arg-translation case.
- `partials/tests/run.sh` — already runs both harnesses under both shells; verify
  no change needed.

## Acceptance Criteria

- [ ] Test (BR-1/C3): `ls-remote` fails but `gh api` shows merged `REQ-800` →
      allocation returns ≥ 801 AND result flagged degraded (branch source failed).
- [ ] Test (BR-3/C2): `kind=lesson`, `gh` absent (and no git fallback) → degraded
      with a stderr warning; never a clean 0.
- [ ] Test (BR-2/M1): `adlc_recheck_id` under a degraded derivation takes the
      degraded branch (observable in output) and emits no zero-derived renumber
      suggestion.
- [ ] Test (BR-2 cmd-sub): a caller using `$(adlc_remote_high …)` observes the
      degraded signal — channel survives command substitution under sh/bash/zsh.
- [ ] Test (BR-4): `gh` absent, GitHub remote reachable over git transport →
      merged artifact ids still derived (via the bare git fixture remote).
- [ ] Test (BR-5): Azure DevOps origin URL → merged artifact ids derived via the
      git-transport path (parity); `az`/transport genuinely unavailable → degraded
      with a forge-naming warning; never silent skip.
- [ ] Test (BR-9): `adlc_forge_pr_merge` on the `azure-devops` branch issues
      `az`-correct args for squash-merge-with-branch-delete; no gh-shaped flag
      reaches `az` (assert via a recording `az` shim, mirroring the `gh` shim).
- [ ] Suite passes under bash AND zsh; multi-element candidate lists in every new
      fixture.
- [ ] Happy-path regression: existing cases still produce identical allocations.

## Technical Notes

- Reuse the existing harness helpers (`new_sandbox`, `make_remote_with_branch`,
  `check`, the `gh` stub pattern). For BR-1, combine a bad-origin repo (ls-remote
  fails) with a `gh` stub returning a merged `REQ-800` listing — then assert both
  the >=801 allocation and a degraded marker (stderr warning text).
- For BR-4/BR-5, the existing `make_remote_with_branch` already builds a real
  **bare git remote** with a pushed `main`; push artifact dirs/files into it and
  assert the git-transport scan derives them with `gh` forced absent (empty PATH
  or a `gh` stub that exits non-zero). For ADO, point a repo's origin at the bare
  remote but assert the host-classifier still runs the git-transport scan (use an
  ADO-shaped URL only where the classifier branch matters; the bare-remote
  transport is forge-agnostic).
- For BR-9, add a recording `az` shim on PATH (like the `gh` shim in
  forge.test.sh) with `ADLC_FORGE_PROVIDER_OVERRIDE=azure-devops`; invoke
  `adlc_forge_pr_merge 9 --squash --delete-branch`; assert the recorded argv
  contains `--squash true` and `--delete-source-branch true` and NOT a bare
  `--delete-branch`.
- Keep every new fixture multi-element (>=2 matching branches/artifacts) per the
  BUG-116 regression discipline.
