---
id: TASK-002
title: "Reservation exact-id probe in id-recheck.sh"
status: complete
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001]
---

## Description

Make `adlc_recheck_id` detect a collision that exists only as a reservation ref
(BR-3), so the /proceed recheck and `adlc renumber` halt on a reservation-only
duplicate.

## Files to Create/Modify

- `partials/id-recheck.sh`

## Acceptance Criteria

- [ ] The exact-id presence probe checks `git ls-remote origin "refs/adlc/ids/<kind>/<num>"` (exact ref path, prefix-sibling safe) in addition to the branch and merged-artifact probes.
- [ ] A reservation-only collision returns 1 with the `adlc renumber <old> <new>` instruction; the suggested new id uses the real high-water + 1 (which now includes reservations).
- [ ] No-collision and degraded paths are unchanged (degraded still returns 0 without a zero-derived renumber).
- [ ] Passes under both `bash -c` and `zsh -c`.

## Technical Notes

- `adlc_remote_high` already contributes the reservation source to the
  high-water/degraded tokens after TASK-001; only the exact-id probe needs the
  reservation branch.
- `$num` is the decimal-normalized number; reservation refs are stored with no
  leading zeros, so the exact ref-path match is correct.
