---
id: TASK-001
title: "Core reservation mechanism + assume kind in id-alloc.sh"
status: draft
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: []
---

## Description

Add the atomic-reservation mechanism to `partials/id-alloc.sh`: a distinct-object
reservation push, the reservation namespace as a derivation source, the bounded
race-retry loop inside `adlc_alloc_id`, and `assume` as a per-repo-scoped fourth
kind.

## Files to Create/Modify

- `partials/id-alloc.sh`

## Acceptance Criteria

- [ ] `adlc_reservation_nonce` produces a distinct value per call (urandom hex + date + pid).
- [ ] `adlc_reserve_id <repo> <kind> <num>` builds a distinct commit object and pushes `"${obj}:refs/adlc/ids/${kind}/${num}"`; returns 0=won, 1=race-lost, 2=degraded per the classifier table (brace-form refspec — no bare `$obj:refs`).
- [ ] `adlc_remote_reservation_nums <repo> <kind>` lists `refs/adlc/ids/<kind>/*` and extracts the trailing numbers; rc 0 iff the scan ran.
- [ ] `adlc_remote_high` includes the reservation namespace as an independent source; participating-repo set is the current repo only for `assume`, all repos under `$ADLC_REPOS_ROOT` for req/bug/lesson; no branch source for assume.
- [ ] `adlc_alloc_id` runs the bounded reservation retry loop (default 10, `ADLC_RESERVE_MAX_TRIES`) inside the existing lock; won → fast-forward + return; race-lost → next number; degraded → warn + proceed unreserved (non-blocking); exhausted → fail loud.
- [ ] Kind mappers gain `assume`: prefix ASSUME, per-repo counter/lockdir (`git rev-parse --show-toplevel`), artifact path `.adlc/knowledge/assumptions`, scan glob.
- [ ] `adlc_local_scan_high assume` scans only the current repo.
- [ ] All existing kind-mapper/derivation behavior for req/bug/lesson is preserved; the ported lock block (symlink pre-check, 50-retry acquire, empty/absent counter guards, guarded rmdir) is unchanged.
- [ ] Passes under both `bash -c` and `zsh -c`.

## Technical Notes

- Classifier order: `[remote rejected]`/`pre-receive hook declined` → degraded FIRST, then `[rejected]` → race, else degraded.
- Reservation push target is always the current repo's `origin` (`git rev-parse --show-toplevel`), for every kind (BR-11/BR-12).
- The reservation loop lives INSIDE the `$(...)` critical-section subshell (it inherits sourced functions). Push output captured with `2>&1`; only the final `echo "$ALLOC"` is stdout.
- Iterate the participating-repo set via `set --` + `for x in "$@"` (zsh-safe).
