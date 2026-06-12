---
id: LESSON-391
title: "Review and cleanup must diff against origin/<integration>, not local main — a stale local main attributes other REQs' work to yours"
component: "adlc/proceed"
domain: "adlc"
stack: ["git"]
concerns: ["review", "correctness"]
tags: ["diff-base", "stale-main", "worktree", "origin-main", "review-scope", "lesson-036"]
req: REQ-519
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

During the portability sprint, pipeline worktrees were (correctly) branched
from `origin/main` while the parent checkout's local `main` sat several merges
behind. Both REQ-519 and REQ-520 runners observed that `git diff main...HEAD`
inside the worktree reported files changed by *previously merged* sprint waves
(REQ-515/517 SKILL.md edits) as if they were part of the current REQ — because
local `main` predated those merges. Review scoping and the Phase-7 cleanup
diff were both at risk of auditing (or "cleaning up") other REQs' shipped work.

## Lesson

Every diff whose purpose is "what did THIS REQ change" must use the actual
branch base: `git fetch origin && git diff origin/<integrationBranch>...HEAD`.
Local `main` is never authoritative in a worktree-based pipeline — the parent
checkout may legitimately lag for days (symlink-install repos are pulled
manually). This is the review-side completion of LESSON-036, which already
established the same rule for eligibility checks.

## Why It Matters

A wrong diff base poisons everything downstream that consumes the diff:
reviewers burn attention on code they didn't write, BR→diff coverage checks
(LESSON-330) cross-match against the wrong change set, and cleanup steps can
flag or revert another REQ's merged work.
