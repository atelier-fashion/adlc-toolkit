---
id: ASSUME-028
title: "`$ADLC_REPOS_ROOT` holds every allocator on the machine"
status: unresolved
req: REQ-663
created: 2026-11-01
resolved:
---

## Assumption

The consumer gate walks the checkouts under `$ADLC_REPOS_ROOT` (default: the clone's parent), and
assumes those are all the repos that allocate ids on this machine.

## Context

A repo elsewhere is invisible to the gate, so its stale `id-alloc.sh` would not refuse the
migration. BR-6's tombstone still stops it, loudly, at its first allocation, so the failure mode is
a confusing error after the move rather than a split lock. REQ-654 and `partials/id-alloc.sh` make
the same assumption.

## Resolution

Open. Holds on the reference machine as far as the walk can tell, which is what it assumes.
