---
id: TASK-002
title: "Pre-push / PR-time recheck partial (partials/id-recheck.sh)"
status: draft
parent: REQ-518
created: 2026-06-11
updated: 2026-06-11
dependencies: []
---

## Description

Create the pre-push/PR-time recheck helper (BR-4, BR-8): re-verify a
locally-allocated id against the remote just before a branch is created or an
artifact file is committed for push, halting with a renumber instruction on
collision rather than pushing a duplicate.

## Files to Create/Modify

- `partials/id-recheck.sh` (NEW) — exports `adlc_recheck_id <kind> <id>`.

## Acceptance Criteria

- [ ] `adlc_recheck_id <kind> <id>` returns 0 when `<id>` is NOT present on the
      remote, non-zero (collision) when it IS (a pushed `feat/REQ-<id>` /
      `fix/bug-<id>` branch or a merged artifact dir/file).
- [ ] On collision it prints a halt message naming the exact
      `adlc renumber <KIND-old> <KIND-new>` command to run (BR-4 → BR-9 handoff).
- [ ] Applies to all three kinds via the shared kind mappers (BR-8): REQ at
      branch creation, BUG and LESSON at commit-for-push.
- [ ] Unreachable remote degrades to a loud warning and returns
      "no collision found" (it can only find a collision, never invent one from
      absence of data) — never blocks on network (BR-3).
- [ ] BSD/zsh-safe; runs under `bash -c` AND `zsh -c` (BR-6); documented contract
      header matching `trial-merge.sh`.

## Technical Notes

Reuse `adlc_remote_high` derivation surface conceptually but answer a different
question (is THIS id taken?). May source `id-alloc.sh` for the kind mappers, or
duplicate only the tiny mapper — keep it lightweight (ADR-3: don't load the full
allocation machinery at recheck time). The renumber-command string it prints is
the single place that wires BR-4 to BR-9.
