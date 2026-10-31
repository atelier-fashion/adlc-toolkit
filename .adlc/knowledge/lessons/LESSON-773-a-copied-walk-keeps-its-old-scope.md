---
id: LESSON-773
title: "A second copy of a repo walk keeps its old scope when a new kind arrives — a comment saying 'the same set' is not a link"
component: "adlc/partials/id-recheck"
domain: "adlc"
stack: ["sh"]
concerns: ["correctness"]
tags: ["id-recheck", "id-alloc", "per-repo", "scope", "duplication", "case-statement", "global-state"]
req: REQ-546
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "BUG-259: partials/id-alloc.sh adlc_remote_high scoped assume to the current repo for REQ-546 BR-12, while partials/id-recheck.sh said it re-walked 'the same repo set' and still looped over the repos root. partials/tests/id-alloc.test.sh failed on ASSUME-018 before the fix and passed after. Its case statement also had no assume arm, so a bug recheck's branch pattern carried into the next assume recheck in the same shell."
confidence: high
enforcement: test:partials/tests/id-alloc.test.sh
generalizes: []
supersedes: []
---

## What Happened

REQ-546 added a kind with a narrower scope than the others. The allocator's walk learned it,
but the recheck kept its own copy of the walk, under a comment saying it used the same set, and
kept scanning every repo. The recheck's `case` on the kind also missed the new value, so a
global from an earlier call survived. Its collision message then named a command that refuses
the new kind.

## Lesson

When a new kind or scope arrives, grep for every site that switches on the old kinds, not just
the one you are changing. Two walks over "the same set" should share one definition, and a
`case` that assigns a global needs an arm for every value, or a reset, because it won't fail
when a value is missing. Check that the remedy a message prints accepts the new kind too.

## Why It Matters

The copy kept working for every existing kind, so nothing failed until the new kind reached a
path no test had crossed.

## Applies When

Adding a kind, scope or enum value to code with parallel walks, `case` statements or printed
remediation commands, especially in shell, where a missing arm is silent.
