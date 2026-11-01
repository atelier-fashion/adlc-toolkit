---
id: LESSON-777
title: "Test a per-path grant against the key the harness actually reads: Claude keys a linked worktree's trust at the main repo root"
component: "adlc/harness"
domain: "adlc"
stack: ["claude-code", "git"]
concerns: ["portability", "harness-agnostic", "security"]
tags: ["workspace-trust", "worktree", "headless", "claude-json", "multi-harness", "exec-engine"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-659 .adlc/research/harness-probes/claude-exec-manual.md rows trust-key-worktree and trust-key-root: projects[<worktree>].hasTrustDialogAccepted in a throwaway .claude.json left 'Ignoring 2 permissions.allow entries' on stderr and the notice named the main repo root as the key; the same entry on the root silenced it, from the same linked worktree. tools/adlc/tests/e2e/claude-exec-manual.sh reruns both."
confidence: low
enforcement: none
generalizes: [LESSON-747]
supersedes: []
---

## What Happened

REQ-659 planned a per-run trust entry for each working copy. Writing one on the worktree's own
path changed nothing, and the harness's notice named the main repo root instead. An entry there
would have been a repo-wide grant, shared with the operator's sessions and every REQ in a batch.

## Lesson

Before designing a per-run or per-path grant, make the harness show you the key it reads: run it
with the grant on the path you expect, then on the path its own message names. A grant on the
wrong key is inert and reads as done. Where the real key is wider than the run, ask whether the
run needs the grant at all, because the honest answer may be to stop depending on it.

## Why It Matters

A per-worktree trust write would have passed every test, edited a file each running Claude Code
rewrites, and protected nothing.

## Applies When

Designing trust, approval or review state for a harness that runs in a linked worktree or a
clone, or any setting keyed by a path the harness computes.
