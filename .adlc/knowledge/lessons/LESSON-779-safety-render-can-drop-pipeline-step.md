---
id: LESSON-779
title: "A rule that withholds an allow can withhold a step the pipeline cannot run without: compare the render with the calls the pipeline makes"
component: "adlc/harness"
domain: "adlc"
stack: ["claude-code", "yaml", "python"]
concerns: ["harness-agnostic", "portability", "verification"]
tags: ["exec-scope", "shared-base", "allowlist", "render", "git-push", "fence", "multi-harness"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: process
evidence: "REQ-659 Reconciliation, commit 562ebff: adlc harness render --scope exec omitted git push, git branch and, once git worktree remove was an engine deny, git worktree, and test_scope_vectors pinned that omission as correct, while proceed Step 0 and Phase 6 push. exec.allow_extra in harness/claude.yml adds spellings that wrap no deny. fence_broad_spelling still spells if [ -f, an opening no fence has had since REQ-669."
confidence: low
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

Each rule in the exec-scope render was right on its own terms, and a test held it. Read against
the pipeline, the same render could not push a branch, so no run could open a PR, and the broad
entry for a partial-sourcing fence described a fence that no longer exists.

## Lesson

An allowlist render has two reviews: what it lets through, and what it stops that the workload
needs. Take the commands the pipeline actually issues and run them through the matcher before
launch. Where a safety rule removes one, add a narrower spelling that wraps no deny rather than
relaxing the rule. Passing tests here only prove the rule, not that the pipeline can run under it.

## Why It Matters

The failure appears only in the first real headless run, as a stop at a tool call, after every
render test has passed.

## Applies When

Rendering a permission tier for an unattended run, adding a deny that shares a base with a
routine command, or changing how skill fences open.
