---
id: LESSON-355
title: "Background pipeline-runner agents cannot execute gh pr merge — orchestrator must own the final merge"
component: "adlc/sprint"
domain: "adlc"
stack: ["gh-cli", "git"]
concerns: ["orchestration", "permissions", "automation"]
tags: ["sprint", "proceed", "pipeline-runner", "sandbox", "merge", "terminal-state", "background-agent"]
req: REQ-476
created: 2026-06-09
updated: 2026-06-09
---

## What Happened

During a parallel `/sprint` (REQ-476, REQ-452, REQ-366), each REQ ran as a
background `pipeline-runner` agent via `/proceed`. Two runners (REQ-476,
REQ-366) drove the full pipeline successfully — implementation, verify, PR
creation, and green CI — but were **killed at the Phase 8 merge step**: the
sandboxed background agent's `gh pr merge` was denied by the permission
system (a write/outward operation), with no alternative tool that
accomplishes the merge. The runners correctly checkpointed
`pipeline-state.json` at `currentPhase: 8` with the PR URL recorded, then
stopped. The orchestrator (main loop, which can prompt for permissions)
verified each PR was `OPEN / MERGEABLE / CLEAN` and performed the merges
itself in the correct cross-repo order.

## Lesson

Treat the final `gh pr merge` as an **orchestrator-owned** action, not a
runner action, for any pipeline launched as a background/sandboxed agent. A
background `pipeline-runner` should drive through Phase 7 (green CI), ensure
the PR is ready, and report `pr-ready` with the PR URL — even for
single-repo REQs where it would normally self-merge. The parent loop owns
the merge (it has the permission surface). When dispatching, instruct the
runner explicitly: "complete through Phase 7, then report `pr-ready`; do not
fail the run over the merge-permission wall." A killed-at-merge runner is
**not** a failure — verify its PR state and merge from the orchestrator.

## Why It Matters

Without this, every background-agent pipeline burns a full implementation +
CI cycle and then dies at the last step, surfacing as a scary "agent killed"
notification that looks like lost work. It also wastes a re-dispatch (the
resumed runner hits the same wall again — observed twice on REQ-476). The
checkpointed `pipeline-state.json` makes the work recoverable, but only if
the orchestrator knows to verify-then-merge rather than relaunch.

## Applies When

Running `/sprint` or `/proceed` where the pipeline executes as a
`run_in_background` agent under a permission sandbox that blocks `gh pr merge`
(and similar write/outward ops). Especially relevant for single-repo REQs,
whose runners would otherwise attempt to self-merge in Phase 8.
