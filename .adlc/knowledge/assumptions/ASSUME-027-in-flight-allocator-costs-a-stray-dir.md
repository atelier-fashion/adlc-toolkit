---
id: ASSUME-027
title: "An allocator in flight across `--back` costs a stray directory, not a duplicate id"
status: unresolved
req: REQ-663
created: 2026-11-01
resolved:
---

## Assumption

`id-alloc.sh` resolves its paths, spends seconds on the network, then takes the lock. One that
resolved `<dir>` before `--back` can wake after `<dir>` is gone, recreate it, and write a counter
there. The assumption is that the remote reservation still prevents a duplicate id, so the cost is
an orphan directory.

## Context

Forward, the same allocator hits a tombstone and fails loud. Reverse, nothing stops it, because
`<dir>` has to go. A migration is one operator's act on a quiet machine, so the race should be rare,
and the reservation push is first-wins. No test has exercised this race: the suite covers failure at
every flip step, not an allocator that wakes after one.

## Resolution

Open. A residual risk in REQ-663's architecture and `## Owed`.
