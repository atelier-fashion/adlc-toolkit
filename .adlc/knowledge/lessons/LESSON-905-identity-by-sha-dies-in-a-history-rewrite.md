---
id: LESSON-905
title: "An identity recorded as an object SHA dies in a history rewrite: the own-reservation ledger called its own REQ a collision"
component: "adlc/partials/id-recheck"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["reliability", "process-compliance", "developer-experience"]
tags: ["id-recheck", "own-reservation", "ledger", "history-rewrite", "reservation-ref", "false-collision", "proceed-step-0"]
req: REQ-672
created: 2026-11-23
updated: 2026-11-23
kind: domain
evidence: "REQ-672 Step 0: partials/id-recheck.sh:264 matches the remote reservation ref's SHA against the own-reservation ledger line. The ledger held the SHA written when the id was allocated, the ref carried another SHA since the repository's history rewrite, and adlc_recheck_id returned 1 (COLLISION) for the pipeline's own REQ. With the ref's current SHA appended to the ledger, the same call returned 0."
confidence: high
enforcement: none
generalizes: [LESSON-435]
supersedes: []
---

## What Happened

`/proceed REQ-672` halted at Step 0. `adlc_recheck_id` found the reservation ref for the
id on the remote, looked for `req 672 <sha>` in the machine's own-reservation ledger, and
found the line with a different SHA. It reported a collision and printed a renumber
command for a REQ whose spec was already merged under that number.

The id was this machine's own. The ref's commit carried the allocation's date and nonce,
and the ledger had an entry for the same kind and number. Between the allocation and the
run, every commit and ref in the repository had been rewritten to remove an address from
commit metadata. The rewrite changed the SHA of each reservation commit. The ledger, a
file outside the repository, still held the old ones. The maintainer had the new SHA
appended, and the recheck passed.

## Lesson

A record that proves "this is mine" by an object SHA is only as stable as the object. A
history rewrite, a rebase of a ref namespace or a re-created ref changes the SHA and
leaves the claim behind.

- When a self-identity check keys on a SHA, record something the rewrite does not touch
  beside it: here the nonce in the reservation commit's subject, which the rewrite kept.
  Match on that first and treat the SHA as a cache.
- A rewrite of a repository that has out-of-tree ledgers is not finished until those
  ledgers are rewritten too. List them before the rewrite: anything under the machine's
  state home that holds a SHA of this repository.
- When this check fires on an id whose spec is already merged under that number, read the
  ref's commit before renumbering. Its date, its subject and a ledger line for the same
  kind and number are the evidence that the reservation is the machine's own. Renumbering
  a merged spec is the expensive wrong answer.
- Every id reserved before the rewrite and not yet run through `/proceed` will halt the
  same way, once each.

## Why It Matters

The halt is a precondition error, so the pipeline stops before any work, and its message
tells the operator to renumber. Followed literally, that renames a merged spec, its
branch and every reference to it, to fix a collision that does not exist. Not followed,
it trains the operator to step past the one check that stops a real duplicate id.

## Applies When

Rewriting history or refs in a repository whose tools keep SHAs in files outside it;
designing a self-identification record for a collision probe; `/proceed` Step 0 or
`/wrapup` reporting a reservation-ref collision on an id this machine allocated.
