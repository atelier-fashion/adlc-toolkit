---
name: sprint
description: Parallel pipeline orchestrator — launch multiple /proceed sessions concurrently across REQs, monitor progress, and report status. Use when the user says "sprint", "run these REQs in parallel", "proceed with all approved REQs", "launch a sprint", or wants to advance multiple requirements simultaneously.
argument-hint: REQ IDs to sprint (e.g., "REQ-091 REQ-092 REQ-093") or "all" for all approved specs
---

# /sprint — Parallel Pipeline Orchestrator

You are a sprint orchestrator that launches multiple `/proceed` pipelines in parallel, monitors their progress, and reports a unified dashboard. Each pipeline runs in its own worktree with full isolation.

## Ethos

!`cat ~/.claude/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current directory: !`pwd`
- Existing worktrees: !`git worktree list 2>/dev/null || echo "Not a git repo"`
- Available specs: !`ls .sdlc/specs/ 2>/dev/null || echo "No specs found"`
- Pipeline states: !`find .sdlc/specs -name "pipeline-state.json" -exec echo {} \; -exec cat {} \; 2>/dev/null || echo "No active pipelines"`

## Input

Target REQs: $ARGUMENTS

## Prerequisites

Before proceeding, verify:
1. `.sdlc/context/project-overview.md` exists — run `/init` if missing
2. `.sdlc/context/architecture.md` exists — run `/init` if missing
3. `.sdlc/context/conventions.md` exists — run `/init` if missing

## Instructions

### Step 1: Identify Sprint REQs

1. If given specific REQ IDs (e.g., `REQ-091 REQ-092`), normalize each to `REQ-xxx` format
2. If given `all`, scan `.sdlc/specs/REQ-*/requirement.md` for all specs with `status: approved` or `status: draft`
3. If no argument, scan for all `status: approved` specs
4. Exclude any REQ that already has `pipeline-state.json` with `"completed": true`
5. Exclude any REQ that already has an active worktree (check `git worktree list`)

If no eligible REQs found, report "No eligible REQs for sprint" and stop.

### Step 2: Validate Sprint Eligibility

For each REQ, verify:
1. The spec file exists at `.sdlc/specs/REQ-xxx-*/requirement.md`
2. Read the spec — confirm it has: Description, Acceptance Criteria (at least 1), and no unresolved Questions marked as blockers
3. Context files exist (project-overview, architecture, conventions)

Report a pre-flight checklist:
```
## Sprint Pre-Flight

| REQ | Title | Status | Eligible | Issue |
|-----|-------|--------|----------|-------|
| REQ-091 | Feature A | approved | Yes | — |
| REQ-092 | Feature B | draft | No | Status is draft, not approved |
| REQ-093 | Feature C | approved | Yes | — |
```

Remove ineligible REQs. If no REQs remain, stop.

**Max concurrent pipelines**: 5. If more than 5 are eligible, prioritize by:
1. REQs explicitly listed in arguments (first priority)
2. REQs with `status: approved` over `status: draft`
3. Lower REQ numbers first (older specs)

Ask the user to confirm the sprint lineup before proceeding.

### Step 3: Launch Parallel Pipelines

For each eligible REQ, launch a background agent:

**Agent prompt for each REQ**:
```
Run the /proceed skill for REQ-xxx in the repository at [current repo path].
This is part of a parallel sprint — other REQs are running concurrently in separate worktrees.
Follow all /proceed phases (0-9) exactly as documented.
If you encounter a blocker that requires human input, update pipeline-state.json with the blocker details and stop gracefully.
Do not attempt to merge if other pipelines are still running — the sprint orchestrator will handle merge sequencing.
```

Launch all agents in a single message to maximize parallelism. Each agent:
- Works in its own worktree (`.worktrees/REQ-xxx`) — isolation is handled by `/proceed` Phase 0
- Maintains its own `pipeline-state.json`
- Operates independently — failure in one does not affect others

### Step 4: Monitor Progress

After launching, enter a monitoring loop:

1. Every 60 seconds (or when an agent completes), read all `pipeline-state.json` files
2. Display the sprint dashboard:

```
## Sprint Dashboard — [timestamp]

| REQ | Phase | Status | Duration | Last Update |
|-----|-------|--------|----------|-------------|
| REQ-091 | 4/8 Implement | Running | 12m | Tier 1 tasks in progress |
| REQ-092 | 5/8 Verify | Running | 18m | 2 findings, fixing |
| REQ-093 | 2/8 Architect | Running | 5m | Creating tasks |

Completed: 0/3 | Blocked: 0 | Running: 3
```

3. If a pipeline's `pipeline-state.json` shows it hasn't advanced in 10+ minutes, check if its agent is still running
4. If a pipeline reports a blocker, surface it to the user immediately:
   ```
   BLOCKER: REQ-091 is stuck at Phase 5 (Verify) — validation failed 3 times.
   Remaining issues: [list from pipeline-state.json]
   Options: (1) Fix manually, (2) Skip validation, (3) Abort this REQ
   ```

### Step 5: Handle Merge Sequencing

When pipelines reach Phase 8 (Wrapup), batch-merge to minimize rebase churn:

1. **Wait for all pipelines to reach merge-ready state** (Phase 7 complete, or blocked/stopped). Do not merge one-by-one as they finish — wait for the batch.
2. Once all running pipelines have completed (or are blocked), sort merge-ready pipelines by:
   - Independent changes first (no overlapping files), then
   - Lower REQ numbers first (tie-breaker)
3. Merge sequentially from the sorted list:
   - Merge the first pipeline: `gh pr merge --squash --delete-branch`
   - Pull main: `git checkout main && git pull`
   - For the next pipeline: rebase onto updated main, force-push, then merge
   - If rebase has conflicts, skip that pipeline and surface to user — continue with the rest
4. **Exception**: If only 1-2 pipelines are in the sprint, merge immediately as each completes (no batching benefit).

This reduces the total number of rebases from N-1 (sequential) to at most N-1 (batch) but eliminates the idle wait where completed pipelines sit while others are still running.

### Step 6: Sprint Summary

After all pipelines complete (or are stopped), produce a sprint summary:

```
## Sprint Summary — [date]

### Completed
| REQ | Title | PR | Duration | Tasks | Lessons |
|-----|-------|----|----------|-------|---------|
| REQ-091 | Feature A | #42 | 25m | 4/4 | 2 |
| REQ-093 | Feature C | #44 | 18m | 3/3 | 1 |

### Blocked / Stopped
| REQ | Title | Phase | Blocker |
|-----|-------|-------|---------|
| REQ-092 | Feature B | 5/9 | Test failure in auth middleware |

### Knowledge Captured
- LESSON-048: [title from REQ-091 wrapup]
- LESSON-049: [title from REQ-091 wrapup]
- LESSON-050: [title from REQ-093 wrapup]

### Metrics
- Total duration: 32 minutes
- REQs shipped: 2/3
- Tasks completed: 7
- Lines changed: +420 / -85
- Lessons captured: 3
```

## Error Handling

- **Agent crash**: If a background agent stops unexpectedly, check its last `pipeline-state.json` state. Report the failure and offer to relaunch from the last completed phase.
- **Worktree conflict**: If a worktree already exists for a REQ, check if there's an active pipeline. If abandoned (no recent state update), offer to clean up and restart.
- **Resource exhaustion**: If the system is slow or agents are timing out, reduce concurrency — pause lower-priority pipelines and let active ones finish first.
- **Merge conflict during sequencing**: Stop the conflicting pipeline, surface the conflict to the user, and continue merging other completed pipelines.

## What This Skill Does NOT Do

- It does not create specs — run `/spec` first for each REQ
- It does not replace `/proceed` — it orchestrates multiple `/proceed` sessions
- It does not handle cross-repo REQs (e.g., REQ spanning atelier-fashion + atelier-web) — each sprint runs within a single repo
