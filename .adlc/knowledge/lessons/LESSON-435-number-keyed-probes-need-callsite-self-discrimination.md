---
id: LESSON-435
title: "A number-keyed collision probe cannot self-identify — consumers that may see their own footprint must add exact-full-name discrimination at the call site"
component: "adlc/skills"
domain: "adlc"
stack: ["bash"]
concerns: ["correctness", "concurrency"]
tags: ["recheck", "self-collision", "slug", "false-positive", "resume", "crash-recovery"]
req: REQ-545
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

`adlc_recheck_id` matches remote footprints by **number** (`feat/REQ-xxx-*`
extracted to the numeric id, exact-equality compared). That is correct for its
job — "is this number taken anywhere?" — but a consumer that may have already
pushed its OWN footprint (a `/proceed` resume, or a fresh run after a crashed
session that had pushed the branch) gets a true-by-number, false-by-intent
hit: the probe finds `feat/REQ-545-<slug>` and the naive wiring would tell
the user to renumber their own in-flight REQ. REQ-545's call site added an
exact-full-branch-name `git ls-remote` probe first: a remote branch whose
FULL name equals the branch this run would itself create is self (reuse
semantics); same number with a different slug remains a true collision.

## Lesson

A collision probe keyed on an identifier can never distinguish "taken by
someone else" from "taken by me" — self-identity lives in data the partial
does not have (the caller's own would-be footprint name). Do not push slug
awareness into the shared partial (it would couple it to every consumer's
naming); instead, every consumer whose own footprint can pre-exist MUST wrap
the probe with an exact-full-name self-check before treating a hit as a
collision. Document this at the partial's contract header so the next
consumer wiring knows the pattern is theirs to add.

## Why It Matters

A false self-collision converts the guard into an outage: the user is halted
and instructed to renumber work that is not colliding with anything, which is
worse than no guard at the exact moment (crash recovery) they are most
confused. Guards that cry wolf get disabled.

## Applies When

- Wiring `adlc_recheck_id` (or any id/collision probe) into a skill that can
  legitimately re-encounter its own pushed branch, PR, or artifact.
- Designing shared probes: decide explicitly which side of the self/other
  distinction the partial owns, and write it into the contract comment.
