---
id: LESSON-390
title: "Draft-PR-early cannot open on a zero-commit branch — defer to the first commit, by design"
component: "adlc/proceed"
domain: "adlc"
stack: ["gh", "git"]
concerns: ["orchestration", "pr-lifecycle"]
tags: ["draft-pr", "proceed", "step-0", "zero-commit", "gh-pr-create", "lesson-004"]
req: REQ-517
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

Three of the six portability-sprint pipelines (REQ-517, REQ-519, REQ-520)
independently hit the same Step-0 failure: `gh pr create --draft` on a branch
freshly cut from the `origin/main` tip fails with `No commits between main and
<branch>` — GitHub rejects an empty-diff PR. Each runner independently
rediscovered the resolution: defer the draft PR to the moment the first Phase-4
commit lands (the LESSON-004 Phase-6 fallback applied earlier).

## Lesson

A branch cut from the base tip has no diff, so draft-PR-early is structurally
impossible at branch-creation time. `/proceed` Step 0's draft-PR step should
document the deferral explicitly: record "draft PR pending first commit" in
pipeline-state, open it on the first commit, and treat the Phase-6 `gh pr
create` fallback as the load-bearing path, not legacy. Three runners
re-deriving the same workaround in one sprint is the signal that the skill
text, not the runners, owns this knowledge.

## Why It Matters

Draft-PR-early exists for cross-session visibility (REQ-483 ordering). Every
run that silently improvises around its failure delays footprint publication
and re-spends tokens rediscovering a deterministic fact of the platform.
