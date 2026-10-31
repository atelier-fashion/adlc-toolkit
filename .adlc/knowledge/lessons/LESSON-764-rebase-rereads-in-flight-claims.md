---
id: LESSON-764
title: "A parallel REQ landing turns \"in flight\" and \"not shipped yet\" into false statements, and a clean rebase will not tell you"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown"]
concerns: ["documentation", "harness-agnostic", "developer-experience"]
tags: ["rebase", "in-flight", "parallel-reqs", "readme", "spec-drift", "stale-claim"]
req: REQ-665
created: 2026-10-30
updated: 2026-10-30
kind: process
evidence: "REQ-665 Phase 5 finding stale-in-flight-dependency-claim: README said Copilot renders have not shipped and no hook render exists, and BR-4 said REQ-656 is in flight, after REQ-656 merged as #228. The rebase conflicted only on CHANGELOG, so nothing textual pointed at those lines. The fix named the shipped commands, and test_docs_name_the_new_check still passed before and after, so no test caught it."
confidence: high
enforcement: none
generalizes: [LESSON-751]
supersedes: []
---

## What Happened

REQ-665 and REQ-656 ran in parallel. REQ-665's README and spec truthfully said REQ-656's
Copilot and Cursor renders had not shipped. REQ-656 merged during Phase 5. The rebase
touched only one conflict, in `CHANGELOG.md`, and every gate passed, while the README told
users that things on `main` did not exist. A reviewer found it by reading `origin/main`.

## Lesson

Before the final rebase, list every sentence in the diff that states another REQ's status
in time: "in flight", "not shipped", "yet", "will come from", "until". For each REQ named,
check whether it landed, and rewrite the sentence to what is now true. Prefer writing such
a sentence so it does not expire: name the REQ and the owner of the surface, not its
progress.

## Why It Matters

A rebase merges text, not claims, so these lines survive it silently, and tests that pin
document wording can freeze the stale version. The cost lands on a reader following a
README that contradicts itself a hundred lines later.

## Applies When

A REQ's docs or spec describe the state of another REQ running at the same time,
especially one named in the task brief as in flight.
