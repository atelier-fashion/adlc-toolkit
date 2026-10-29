---
id: LESSON-738
title: "A shared list kept on one line makes every concurrent addition a same-line conflict that keep-both cannot resolve — back out your own append, merge, re-apply"
component: "adlc/sprint"
domain: "adlc"
stack: ["sh", "git"]
concerns: ["merge-conflicts", "parallel-work"]
tags: ["harness-list", "run-sh", "append-point", "same-line-conflict", "trial-merge", "sprint", "keep-both"]
req: REQ-654
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-654: partials/tests/run.sh:43 keeps every harness on one run_all line. REQ-647 (6600dd6) and then BUG-253 each appended to that line while REQ-654 was in flight, and adlc_trial_merge against origin/main returned rc=1 naming partials/tests/run.sh both times. Backing out the branch's own append, merging, and re-adding the harness after main's entries made each merge clean (rc=0) with no conflict resolved."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

Three pieces of work landed on `main` within a day: REQ-647, BUG-253 and REQ-654.
Each added a test harness to `partials/tests/run.sh`, which lists every harness as
arguments on a single `run_all` line. Each addition therefore modified that line.
Each time REQ-654 integrated `main`, the trial merge returned rc=1 on `run.sh`.
`partials/README.md` collided the same way once, at an entry list where both sides
appended after the same item. The bounded keep-both rule (`partials/conflict-bound.sh`,
BUG-207) resolves only pure line additions, so the `run.sh` hunk was outside it:
both sides changed one existing line, which halts a `/sprint` runner as `blocked`.
Instead, the branch reverted its own edit at each shared point, merged `main`
cleanly, and re-applied the edit after `main`'s entries. That took two commits
and resolved no conflict.

## Lesson

When your branch and the integration branch both touched a shared append point
and the conflict is entirely your own addition, do not resolve it. Back out your
addition, merge, and re-add it on top. The merge then has nothing to resolve,
nothing needs a judgment, and `conflictsResolved` correctly stays empty. Watch for
the case where the hold-back itself deletes context, such as a trailing blank
line. That re-creates a conflict, and the fix is to restore the base bytes before
merging. When you own the list's format, put one entry per line: concurrent
additions then become pure appends, which keep-both can resolve.

## Why It Matters

Under `/sprint`, a same-line conflict at Phase 8 is a `blocked` terminal for
something no human needs to decide. Every REQ that adds a harness, a partial or a
README entry makes the next one conflict, so the cost compounds with parallelism.

## Applies When

Integrating the base branch into a long-running REQ branch, or reaching a Phase 7
or 8 trial merge, where the conflicted files are registries, harness lists,
changelog sections or README entry lists that other in-flight work also extends.
Also applies when designing such a list in the first place.
