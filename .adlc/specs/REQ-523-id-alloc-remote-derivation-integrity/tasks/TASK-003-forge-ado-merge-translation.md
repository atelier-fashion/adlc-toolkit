---
id: TASK-003
title: "adlc_forge_pr_merge: translate gh-shaped merge flags to az equivalents on the ADO branch (BR-9)"
status: draft
parent: REQ-523
created: 2026-06-12
updated: 2026-06-12
dependencies: []
repo: adlc-toolkit
---

## Description

Fix `adlc_forge_pr_merge` in `partials/forge.sh` so the `azure-devops` branch
translates the gh-shaped `--squash` / `--delete-branch` arguments into their
`az repos pr update` equivalents instead of forwarding `"$@"` verbatim. Today a
caller invoking `adlc_forge_pr_merge <ref> --squash --delete-branch` makes the
ADO branch issue `az repos pr update --id <ref> --squash --delete-branch --status
completed --squash true --delete-source-branch true`, where `--squash` (no value)
and `--delete-branch` (unknown flag) are rejected by `az`.

Independent of TASK-001/002 (different file, different surface) — parallel-eligible.

## Files to Create/Modify

- `partials/forge.sh` — rework the `azure-devops` arm of `adlc_forge_pr_merge`:
  split the PR ref (first positional) from the option flags, translate
  `--squash` → `--squash true`, `--delete-branch` → `--delete-source-branch true`,
  drop/ignore any other gh-only flag, and never forward `--squash`/`--delete-branch`
  verbatim to `az`.

## Acceptance Criteria

- [ ] BR-9: ADO branch issues `az`-correct arguments for a squash-merge-with-
      branch-delete call; no gh-shaped flag (`--squash` bare, `--delete-branch`)
      reaches `az`.
- [ ] The PR ref positional is preserved and passed as `--id <ref>`.
- [ ] GitHub branch is byte-unchanged (BR-3 of REQ-520 preserved — existing
      `gh merge byte-compat` test still passes).
- [ ] POSIX/BSD/zsh-safe (no `local`, no bare `$<digit>`, no `[0]` indexing).

## Technical Notes

- Parse `"$@"` into: `ref` (first non-flag positional) and a translated flag list.
  Use a portable loop building a positional set (set -- rebuild) or accumulate into
  a prefixed variable; do NOT rely on arrays (zsh/bash differ). The current call
  shape from `/proceed` Phase 8 is `adlc_forge_pr_merge <prUrl|n> --squash
  --delete-branch`.
- Translation table: `--squash` → emit `--squash true`; `--delete-branch` → emit
  `--delete-source-branch true`. Always include `--status completed`. Unknown
  gh-only flags (e.g. `--merge`, `--rebase`, `--admin`) are dropped with no error
  for v1 (or mapped if trivial) — but `--squash`/`--delete-branch` MUST be
  translated, never forwarded.
- Keep the `_adlc_forge_run -- az repos pr update --id <ref> …` invocation shape and
  the `state=MERGED` normalization + classifier error surface unchanged.
- Mirror the ADO arg shape used elsewhere in forge.sh (`az repos pr update --id`).
