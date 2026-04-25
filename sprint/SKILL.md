---
name: sprint
description: Parallel pipeline orchestrator — launch multiple /proceed sessions concurrently across REQs, monitor progress, and report status. Use when the user says "sprint", "run these REQs in parallel", "proceed with all approved REQs", "launch a sprint", or wants to advance multiple requirements simultaneously.
argument-hint: REQ IDs to sprint (e.g., "REQ-091 REQ-092 REQ-093") or "all" for all approved specs
---

# /sprint — Parallel Pipeline Orchestrator

You are a sprint orchestrator that launches multiple `/proceed` pipelines in parallel, monitors their progress, and reports a unified dashboard. Each pipeline runs in its own worktree with full isolation.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current directory: !`pwd`
- Existing worktrees: !`git worktree list 2>/dev/null || echo "Not a git repo"`
- Available specs: !`ls .adlc/specs/ 2>/dev/null || echo "No specs found"`
- Pipeline states: !`find .adlc/specs -name "pipeline-state.json" -exec echo {} \; -exec cat {} \; 2>/dev/null || echo "No active pipelines"`

## Input

Target REQs: $ARGUMENTS

## Prerequisites

Before proceeding, verify:
1. `.adlc/context/project-overview.md` exists — run `/init` if missing
2. `.adlc/context/architecture.md` exists — run `/init` if missing
3. `.adlc/context/conventions.md` exists — run `/init` if missing

## Instructions

### Step 1: Identify Sprint REQs

1. If given specific REQ IDs (e.g., `REQ-091 REQ-092`), normalize each to `REQ-xxx` format
2. If given `all`, scan `.adlc/specs/REQ-*/requirement.md` for all specs with `status: approved` or `status: draft`
3. If no argument, scan for all `status: approved` specs
4. Exclude any REQ that already has `pipeline-state.json` with `"completed": true`
5. Exclude any REQ that already has an active pipeline-runner — i.e., a worktree on its `feat/REQ-xxx-...` branch AND a `pipeline-state.json` whose `completed` is `false` and whose phase has advanced recently. (A stale same-branch worktree from a crashed prior run is **not** an active pipeline; it falls through to Step 2 item 4 below, which surfaces it with a cleanup recipe rather than silently excluding the REQ.)

If no eligible REQs found, report "No eligible REQs for sprint" and stop.

### Step 2: Validate Sprint Eligibility

For each REQ, verify:
1. The spec file exists at `.adlc/specs/REQ-xxx-*/requirement.md`
2. Read the spec — confirm it has: Description, Acceptance Criteria (at least 1), and no unresolved Questions marked as blockers
3. Context files exist (project-overview, architecture, conventions)
4. **Worktree path collision check**: parse `git worktree list --porcelain` in the primary repo and intersect each candidate's target path `<repo-path>/.worktrees/REQ-xxx` against registered worktrees. If the path is already registered to a different branch (i.e., not the candidate's own `feat/REQ-xxx-...` branch), mark the REQ ineligible with the issue text `worktree path in use by branch <name>`. The surfaced message MUST name the cleanup commands the user can run to clear the stale worktree. **Quote the substituted `<branch>` and `<path>` values with single quotes** so a copy-paste cannot execute injected shell from a hostile branch name:
   ```
   git -C '<repo>' worktree remove '<path>'      # add --force if the worktree has uncommitted work you intend to discard
   git -C '<repo>' branch -D '<branch>'          # -D already forces deletion regardless of merge status; verify with `git log main..'<branch>'` first if you may have unmerged work to keep
   ```
   **Scope (OQ-2 default)**: this collision check scans only the **primary repo**. Sibling-repo collisions are caught at `/proceed` Step 0 by the per-repo `git worktree add` validation gate, so do not extend this pre-flight to siblings without a deliberate decision — see REQ-263 architecture.md ("Cross-repo behavior") for why.

Report a pre-flight checklist:
```
## Sprint Pre-Flight

| REQ | Title | Status | Eligible | Issue |
|-----|-------|--------|----------|-------|
| REQ-091 | Feature A | approved | Yes | — |
| REQ-092 | Feature B | draft | No | Status is draft, not approved |
| REQ-093 | Feature C | approved | Yes | — |
| REQ-094 | Feature D | approved | No | worktree path in use by branch feat/REQ-094-old-attempt |
```

Remove ineligible REQs. If no REQs remain, stop.

**Max concurrent pipelines**: 5. If more than 5 are eligible, prioritize by:
1. REQs explicitly listed in arguments (first priority)
2. REQs with `status: approved` over `status: draft`
3. Lower REQ numbers first (older specs)

Ask the user to confirm the sprint lineup before proceeding.

### Step 3: Launch Parallel Pipelines

For each eligible REQ, launch a **pipeline-runner** agent (defined in `~/.claude/agents/`) using the Agent tool with `run_in_background: true`.

**Agent prompt for each REQ** (the orchestrator computes `<absolute-path>` as `<repo-path>/.worktrees/REQ-xxx` and substitutes it verbatim):

> **BEFORE dispatching, substitute `<absolute-path>` and `REQ-xxx` and `[current repo path]` with the actual computed values.** Do **NOT** emit any of these placeholders literally — `/proceed` Step 0 will use the captured WORKTREE PATH verbatim, and a literal `<absolute-path>` would cause `git worktree add` to fail with an unhelpful error. The agent definition for `pipeline-runner` (canonical source for worktree-isolation rules) takes precedence over the in-prompt reminder below if they ever diverge.

```
WORKTREE PATH (mandatory): <absolute-path>

Run the /proceed skill for REQ-xxx in the repository at [current repo path].
You are in SUBAGENT MODE — execute all phases sequentially, do not dispatch sub-agents.
This is part of a parallel sprint — other REQs are running concurrently in separate worktrees.
Use the WORKTREE PATH above verbatim for `git worktree add` in Phase 0. All later phases MUST read the worktree path from `pipeline-state.json.repos[<id>].worktree` (set by Phase 0 from this contract line) — do not re-derive it. The only sanctioned operation against the parent repo path is `gh pr merge` in Phase 8 single-repo topology; every other read/write/cd belongs inside the worktree. (See `agents/pipeline-runner.md` "Worktree Isolation" section for the canonical rules.)
Follow all /proceed phases (0-8) exactly as documented.
If you encounter a blocker that requires human input, update pipeline-state.json with the blocker details and stop gracefully.
Phase 8 merge ownership follows REQ topology: single-repo REQs — you own the merge and report `merged`. Cross-repo REQs — stop after Phase 7 and report `pr-ready` so the orchestrator can sequence merges per `mergeOrder`. Your final report MUST lead with one of `{merged, pr-ready, blocked, failed}`.
```

The `WORKTREE PATH (mandatory): <absolute-path>` line is a contract fixed in REQ-263 architecture.md — **exactly one space after `WORKTREE PATH` (before the opening parenthesis), exactly one space after `(mandatory):`**, POSIX absolute path, no quoting, no trailing slash, line stands alone. `/proceed` Step 0 parses it with regex `^WORKTREE PATH \(mandatory\): (.+)$` and uses the **first** match if the prompt accidentally contains multiple. Do not reformat. The orchestrator MUST emit this line for every dispatched pipeline-runner; it is the producer side of the dispatch-line contract (BR-1, BR-7).

Launch all agents in a single message to maximize parallelism. Each pipeline-runner agent:
- Runs in subagent mode (all phases sequential, no nested sub-agent dispatch)
- Works in its own worktree (the absolute path declared in the `WORKTREE PATH (mandatory):` line — typically `<repo-path>/.worktrees/REQ-xxx` by convention) — isolation is handled by `/proceed` Phase 0
- Maintains its own `pipeline-state.json`
- Operates independently — failure in one does not affect others

### Step 4: Monitor Progress (Notification-Driven)

Background `pipeline-runner` agents send an automatic notification when they finish (complete, blocked, or failed). The orchestrator does **not** actively poll on a timer — attempting to `sleep`/loop mid-turn would block the conversation without any benefit. Instead, the orchestrator reacts to agent-completion notifications and refreshes state whenever the user takes a turn.

1. **Immediately after launch**: read every `pipeline-state.json` that was just initialized and print the initial sprint dashboard (see below). This confirms all agents launched and shows their starting phase.

2. **When an agent-completion notification arrives** (the platform delivers one per background agent): re-read every `pipeline-state.json` under `.adlc/specs/REQ-*/` and update the dashboard. Only redraw when state has actually changed — don't spam the user with identical dashboards.

   **Verify the agent's terminal-state claim before accepting it.** A pipeline-runner's final report MUST lead with one of `{merged, pr-ready, blocked, failed}` (see `~/.claude/agents/pipeline-runner.md` Terminal state contract). The orchestrator MUST NOT trust the claim at face value:
   - For `merged` and `pr-ready` claims: run `gh pr view <prUrl> --json state,mergedAt` against every touched-repo PR before updating the dashboard.
     - If the agent claimed `merged` but the PR is `OPEN`: treat the claim as `pr-ready` and merge the PR per Step 5.
     - If the agent claimed `pr-ready` but the PR is `MERGED`: just move on (agent was conservative, no harm done).
     - If the PR is `CLOSED` (not merged) or in any other unexpected state: surface as a blocker.
   - For `blocked` and `failed`: read `pipeline-state.json.blockers` / `notes` and surface to the user per the existing blocker-handling flow (Step 4.6).
   - **Untagged claims** (e.g., a vague "Pipeline complete" without one of the four tags) are protocol violations. Treat as `blocked` and surface to the user — do not assume the agent finished cleanly.

3. **When the user takes a turn during the sprint** (asks a question, issues a command): re-read all `pipeline-state.json` files first, so any answer reflects current pipeline state rather than a stale snapshot from launch.

4. **Dashboard format**:

```
## Sprint Dashboard — [timestamp]

| REQ | Phase | Status | Duration | Last Update |
|-----|-------|--------|----------|-------------|
| REQ-091 | 4/8 Implement | Running | 12m | Tier 1 tasks in progress |
| REQ-092 | 5/8 Verify | Running | 18m | 2 findings, fixing |
| REQ-093 | 2/8 Architect | Running | 5m | Creating tasks |

Completed: 0/3 | Blocked: 0 | Running: 3
```

5. **Stall detection**: stalls are detected on dashboard refreshes (triggered by notifications or user turns), not on a timer. If a pipeline's `pipeline-state.json` has not advanced between two consecutive refreshes AND the gap between refreshes is >10 minutes of wall clock, flag it as potentially stalled in the next dashboard and check whether its background agent is still alive.

6. **Blocker handling**: if a pipeline's state file reports a blocker (e.g. `phase4.failedTasks` is non-empty, or validation has failed 3 times), surface it immediately on the next refresh:
   ```
   BLOCKER: REQ-091 is stuck at Phase 5 (Verify) — validation failed 3 times.
   Remaining issues: [list from pipeline-state.json]
   Options: (1) Fix manually, (2) Skip validation, (3) Abort this REQ
   ```
   Wait for the user's choice before taking action on that pipeline. Other pipelines continue running.

### Step 5: Handle Merge Sequencing

**Default policy: merge as each pipeline completes.** When a pipeline finishes Phase 7 and is marked merge-ready, merge it immediately — don't wait for the batch. Faster feedback, less idle time, and the rebase cost on subsequent pipelines is paid as they reach merge-ready anyway (each one runs its own `/wrapup` Step 2 rebase-onto-main guard, so main drift is handled automatically).

**Who actually performs the merge depends on REQ topology** (see `~/.claude/agents/pipeline-runner.md` Phase 8):

- **Single-repo REQ** (one touched repo in `pipeline-state.repos`): the pipeline-runner agent already merged its own PR in its Phase 8 and reports `merged`. The orchestrator's job here is to **verify** (per Step 4 verify gate) and move on — do NOT re-merge. If verification shows the PR is still `OPEN` despite the `merged` claim, fall through to the cross-repo flow below and merge it yourself.
- **Cross-repo REQ** (multiple touched repos): the pipeline-runner stops at Phase 7 and reports `pr-ready`. The orchestrator owns merge sequencing and walks the per-REQ `mergeOrder` itself.

The sequential flow when the orchestrator is the merge actor (cross-repo, or single-repo fallback after a failed agent merge):
1. Merge the PR: `gh pr merge --squash --delete-branch`
2. Pull main: `git checkout main && git pull`
3. Move on — other pipelines keep running in the background

**Batch mode (only when N ≥ 3)**: when the sprint has 3 or more pipelines AND the orchestrator has strong prior knowledge that their diffs overlap (same files, same modules), switch to batching:
1. Wait for all pipelines to reach merge-ready state (Phase 7 complete, blocked, or stopped)
2. Sort merge-ready pipelines by:
   - Independent changes first (no overlapping files), then
   - Lower REQ numbers first (tie-breaker)
3. Merge sequentially from the sorted list:
   - Merge the first PR
   - Pull main
   - For each subsequent pipeline, its `/wrapup` Step 2 will re-fetch and rebase onto the new main before merging
   - If any rebase hits conflicts, skip that pipeline and surface to the user — continue with the rest

Batch mode is the exception, not the rule. If you're uncertain whether diffs overlap, default to merging as each completes.

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

## Cross-Repo Sprints

`/sprint` supports sprints that include cross-repo REQs. Cross-repo handling is delegated entirely to each `/proceed` pipeline — `/sprint` itself still originates every pipeline from the same repo (the one it was invoked in), but each `/proceed` reads `.adlc/config.yml` and may create worktrees in sibling repos as needed.

**Collision avoidance**: concurrent cross-repo REQs that share a sibling each create their own worktree at `<sibling-path>/.worktrees/REQ-xxx` (different REQ numbers → different paths → no collision). If two REQs accidentally try to use the same REQ number, `git worktree add` fails loudly on the second — surface that in the pre-flight report.

**Pre-flight check for cross-repo sprints**: for each REQ whose frontmatter or tasks declare sibling repos (via `repo:` values from `.adlc/config.yml`), verify in Step 2:
- Every declared sibling is present on disk and is a git repo
- Each touched sibling's `main` is clean or has no conflicting branch

**Sibling-repo worktree collisions are deferred to `/proceed` Step 0** (per REQ-263 architecture.md "Cross-repo behavior" + OQ-2 default). The `/sprint` Step 2 collision check (item 4 above) intentionally scans **only the primary repo**; sibling collisions are caught by `/proceed` Step 0's per-repo `git worktree add` validation gate, which runs the same fail-loud halt with the same error format. Do not extend Step 2 to scan siblings without a deliberate decision — it would duplicate the validation logic ADR-1 was designed to keep in one place.

If any check fails, mark the REQ ineligible with a specific issue in the pre-flight table. The user may choose to clean up and retry, or exclude that REQ from the sprint.

**Dashboard**: the sprint dashboard's per-REQ row should show "primary repo → N touched" when a REQ is cross-repo (e.g., `admin-api → 3 touched`) so the user sees fleet-wide activity at a glance, not just local work.

**Merge sequencing**: cross-repo REQs produce multiple PRs, merged in the REQ's own `mergeOrder` (by its `/proceed` Phase 8). `/sprint` still merges REQs "as each pipeline completes" — a completed cross-repo pipeline means all its per-repo PRs have landed. Only the next REQ's pipelines need to re-fetch main.

## What This Skill Does NOT Do

- It does not create specs — run `/spec` first for each REQ
- It does not replace `/proceed` — it orchestrates multiple `/proceed` sessions
- It does not originate REQs from different primary repos in a single sprint — every REQ in one `/sprint` invocation is assumed to originate from the repo the command was run in. Cross-repo REQs whose primary is a sibling must be sprinted from that sibling instead.
