---
id: TASK-004
title: "adlc renumber reserves the new id before mutating"
status: draft
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001]
---

## Description

`adlc renumber` must atomically reserve the new id via the same mechanism before
it mutates files, leaving the old id's reservation in place (BR-8).

## Files to Create/Modify

- `tools/adlc/renumber.py`

## Acceptance Criteria

- [ ] After the new-id remote-collision refusal and before applying the rename, renumber reserves `new_id` by shelling out to `adlc_reserve_id` in `id-alloc.sh` (mirrors `remote_collision`'s shell-out to id-recheck.sh — one authority).
- [ ] A won reservation proceeds; a degraded reservation does NOT block the renumber (parity with the degraded posture elsewhere) — it warns.
- [ ] A race-lost reservation (the new id got taken between recheck and reserve) aborts with a clear message pointing at the recheck's next-free suggestion, rather than renaming into a colliding id.
- [ ] The old id's reservation is never deleted.
- [ ] `tools/adlc/tests/test_renumber.py` covers the reserve-before-mutate path.

## Technical Notes

- Reuse `_find_partial("id-alloc.sh")` (add if absent) and the `sh -c '. "$1"; adlc_reserve_id "$2" "$3" "$4"'` shape.
- Kind token for the reservation is the lowercase kind (`req`/`bug`/`lesson`).
- The reserve runs in dry-run? No — only on `--yes` (apply). Dry-run must not push. Guard so the reservation happens only in the apply branch.
