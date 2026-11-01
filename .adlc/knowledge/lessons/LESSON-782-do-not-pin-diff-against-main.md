---
id: LESSON-782
title: "Do not commit a test that says a file is unchanged against origin/main: it passes on main and fails the next REQ that may edit it"
component: "adlc/tools/adlc"
domain: "adlc"
stack: ["python", "git", "pytest"]
concerns: ["testing", "maintainability"]
tags: ["scope-check", "origin-main", "brittle-test", "branch-only-failure", "sprint"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-659 final run: test_other_adapters_are_not_edited in tools/adlc/tests/test_harness_antigravity.py, REQ-658's scope check, failed with harness/claude.yml in the diff, because this REQ adds the exec block; dropping that path from the list passed, commit 562ebff. copilot, cursor and codex stay listed, so REQ-662 will meet the same failure."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-658 pinned its own scope with a test: no other adapter differs from `origin/main`. It held
for that REQ, passed on `main` after the merge, and then failed on the next branch that had every
right to edit one of those files.

## Lesson

"This REQ did not touch X" is a fact about one diff, so check it once, in the REQ's verification
or its PR, not in a test that outlives the REQ. A committed test should state a property of the
tree. If a change must not touch a surface, say why as an invariant that a test can check on any
commit.

## Why It Matters

Such a test is green on `main` and fails only on feature branches, so it costs each later REQ a
diagnosis, and the fix is always to weaken a test that was never protecting anything.

## Applies When

Writing a test that compares against `origin/main`, or any test whose result depends on the
branch it runs on rather than on the tree.
