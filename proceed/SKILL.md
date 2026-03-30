---
name: proceed
description: End-to-end SDLC pipeline that takes a requirement from spec through to deployed. Takes a REQ number as argument and runs validate → fix → architect → fix → implement → reflect → fix → create PR → review/fix → wrapup (merge, deploy, knowledge capture). Use when the user says "proceed", "proceed with REQ-xxx", "run the pipeline", "take REQ-xxx to completion", "implement REQ-xxx end to end", or wants to advance a drafted requirement all the way through to deployment in one shot.
---

# Proceed — Full SDLC Pipeline

You are an autonomous SDLC orchestrator. Given a requirement number (REQ-xxx), you drive it from validated spec all the way to a pull request — validating at each gate, fixing issues automatically, and only pausing when you're stuck or need human input.

## Arguments

The user provides a requirement ID, e.g., `/proceed REQ-023` or `/proceed 23`.

- Normalize to `REQ-xxx` format (zero-pad to 3 digits if needed)
- Locate the spec at `.sdlc/specs/REQ-xxx-*/requirement.md`
- If the spec doesn't exist, stop and tell the user to run `/spec` first

## The Pipeline

Execute these phases in order. Each phase has a validation gate — if validation fails, fix the issues and re-validate. Loop up to 3 times per gate; if still failing after 3 attempts, stop and present the remaining issues to the user.

## Pipeline State Tracking

**CRITICAL**: You MUST maintain a state file to track pipeline progress. This prevents phases from being skipped during long-running pipelines.

**State file location**: `.sdlc/specs/REQ-xxx-*/pipeline-state.json`

**Schema**:
```json
{
  "req": "REQ-xxx",
  "branch": "feat/REQ-xxx-short-description",
  "startedAt": "2026-03-27T10:00:00Z",
  "completed": false,
  "currentPhase": 0,
  "completedPhases": [],
  "phaseHistory": [
    { "phase": 0, "name": "Create Worktree", "completedAt": "2026-03-27T10:01:00Z" }
  ]
}
```

**Rules — follow these exactly**:

1. **Initialize** the state file at the start of Step 0 with `currentPhase: 0, completedPhases: [], completed: false`
2. **After completing each phase**: append the phase number to `completedPhases`, add an entry to `phaseHistory` with the completion timestamp, and set `currentPhase` to the next phase number
3. **BEFORE starting any phase (Phases 1–9)**: read `pipeline-state.json` and verify:
   - The previous phase number is in `completedPhases`
   - `currentPhase` equals the phase you are about to start
   - If either check fails, **STOP** — you have skipped a phase. Go back and complete the missing phase before continuing.
4. **Resume from interruption**: If the state file already exists when you start the pipeline, read it and resume from `currentPhase` instead of starting over
5. **On completion**: After Phase 9 (Wrapup) finishes, set `"completed": true` in the state file

---

### Step 0: Create Worktree (ALWAYS FIRST)

**Before doing anything else**, isolate this work in a git worktree so parallel sessions don't collide:

1. Ensure main is up to date: `git checkout main && git pull`
2. Create a worktree with a dedicated branch:
   ```bash
   git worktree add .worktrees/REQ-xxx feat/REQ-xxx-short-description
   ```
3. Change your working directory to `.worktrees/REQ-xxx` — **all subsequent work happens there**
4. **Initialize `pipeline-state.json`** in the spec directory (`.sdlc/specs/REQ-xxx-*/pipeline-state.json`) with `currentPhase: 0, completedPhases: [], completed: false, startedAt: <now>`. If the file already exists, read it and resume from `currentPhase`.
5. When the pipeline completes (PR merged), clean up:
   ```bash
   git worktree remove .worktrees/REQ-xxx
   ```

This ensures multiple `/proceed` sessions on different REQs never touch each other's files.

**After completing Step 0**: Update `pipeline-state.json` — add `0` to `completedPhases`, add Step 0 to `phaseHistory`, set `currentPhase` to `1`.

---

### Phase 1: Validate the Requirement Spec

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `1` and `0` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `1` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `2`.

**Goal**: Ensure the requirement is complete and well-formed before designing architecture.

1. Invoke the `/validate` skill with the REQ ID
2. If **APPROVED**: set requirement status to `approved` and move to Phase 2
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**Status update**: After this phase, report "Spec validated and approved" before continuing.

---

### Phase 2: Architect & Break Into Tasks

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `2` and `1` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `2` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `3`.

**Goal**: Design the technical approach and create implementation tasks.

1. Invoke the `/architect` skill with the REQ ID
2. This handles: reading context, designing architecture, creating task files with dependencies, and updating requirement status

**Status update**: Summarize the architecture approach and list all tasks with dependency graph.

---

### Phase 3: Validate Architecture & Tasks

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `3` and `2` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `3` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `4`.

**Goal**: Ensure the architecture and task breakdown are solid before implementation.

1. Invoke the `/validate` skill with the REQ ID (it will auto-detect the architecture+tasks phase)
2. If **APPROVED**: move to Phase 4
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**Status update**: Report "Architecture and tasks validated" before continuing.

---

### Phase 4: Implement

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `4` and `3` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `4` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `5`.

**Goal**: Execute all tasks, producing working code with tests.

1. Build the dependency graph from task frontmatter
2. Identify independent tasks (no unmet dependencies) — these can run in parallel
3. For each task (or batch of independent tasks):
   - Read the task file for requirements, files to modify, ACs, technical notes
   - Implement the changes following project conventions (from `.sdlc/context/conventions.md`)
   - Write tests as specified in the task
   - Run the project's test suite to verify nothing is broken
   - Mark the task status as `complete` in its frontmatter
   - Commit with message format: `feat(scope): description [TASK-xxx]`
4. Use parallel subagents for tasks that have no dependency relationship with each other. Wait for all tasks in a dependency tier to complete before starting the next tier.

**Parallelization strategy**:
- Group tasks into tiers based on the dependency graph
- Tier 0: tasks with no dependencies (launch all in parallel)
- Tier 1: tasks depending only on Tier 0 tasks (launch after Tier 0 completes)
- Continue until all tiers complete
- Each subagent gets the full task file, conventions, and architecture context

**Status update**: After each tier completes, report which tasks finished and any issues encountered.

---

### Phase 5: Reflect & Fix

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `5` and `4` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `5` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `6`.

**Goal**: Self-assess the implementation and address any concerns.

1. Invoke the `/reflect` skill with the REQ ID
2. If the reflection surfaces concrete issues (not just observations):
   - Fix them immediately
   - Run tests again to verify
   - Commit fixes with message: `fix(scope): address reflection finding [REQ-xxx]`
3. Loop: re-invoke `/reflect` on fixes, fix again if needed (up to 3 loops, stop if only observations remain)

**Status update**: Share the reflection summary and note any fixes applied.

---

### Phase 6: Code Review & Fix

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `6` and `5` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `6` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `7`.

**Goal**: Run a multi-agent code review and address all findings before creating the PR.

1. Run the `/review` skill against all changes on the feature branch
2. For each finding categorized as **must-fix** (bugs, security issues, convention violations, missing tests):
   - Fix the issue
   - Run the test suite to verify the fix doesn't break anything
   - Commit with message: `fix(scope): address review finding [REQ-xxx]`
3. For findings categorized as **should-fix** (code quality, naming, minor improvements):
   - Fix them unless doing so would be a significant refactor — in that case, note them as follow-ups
4. For findings categorized as **nit** or **observation**:
   - Fix trivial ones inline; skip the rest
5. Re-run `/review` after fixes to confirm all must-fix items are resolved (up to 2 loops)
6. If findings remain unresolvable after 2 loops, list them for the user and ask how to proceed

**Status update**: Report the review summary — total findings, how many fixed, any deferred.

---

### Phase 7: Create Pull Request

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `7` and `6` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `7` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `8`.

**Goal**: Package everything into a reviewable PR.

1. Ensure all changes are committed and pushed to the feature branch
2. Set the requirement status to `complete` in its frontmatter
3. Create the PR using `gh pr create` with:
   - **Title**: Short description referencing the REQ (e.g., `feat: world outfits data extraction [REQ-023]`)
   - **Body**:
     ```
     ## Summary
     [2-3 bullet points describing what was built]

     ## Requirement
     REQ-xxx: [requirement title]

     ## Tasks Completed
     - [x] TASK-001: [title]
     - [x] TASK-002: [title]
     ...

     ## Architecture Decisions
     [Key ADRs or "No architectural changes needed"]

     ## Test Coverage
     [Summary of tests added/modified]

     ## Reflection Notes
     [Key observations from the reflect phase — risks, assumptions, follow-ups]
     ```
4. Report the PR URL to the user

---

### Phase 8: PR Review & Fix

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `8` and `7` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `8` to `completedPhases`, log in `phaseHistory`, set `currentPhase` to `9`.

**Goal**: Review the PR as a whole, catch anything the earlier review missed, and ensure it's merge-ready.

1. Review the full PR diff using `gh pr diff`
2. Check for:
   - Stray debug logs, TODOs, or commented-out code
   - Files that shouldn't have been included (secrets, generated files, unrelated changes)
   - Commit message consistency and cleanliness
   - That the PR description accurately reflects the changes
3. If issues are found:
   - Fix them, commit with message: `fix(scope): PR cleanup [REQ-xxx]`
   - Push to the feature branch
   - Re-invoke `/review` after fixes to confirm all issues resolved (up to 2 loops)
4. If CI checks are configured, verify they pass: `gh pr checks`

**Status update**: Report "PR is clean and ready for merge" or list any remaining concerns.

---

### Phase 9: Wrapup

**Gate**: Read `pipeline-state.json`. Confirm `currentPhase` is `9` and `8` is in `completedPhases`. If not, stop and complete the missing phase first. After completing this phase, update the state file: add `9` to `completedPhases`, log in `phaseHistory`, set `"completed": true`.

**Goal**: Merge, deploy, capture knowledge, and close out the feature.

1. Run the `/wrapup` skill with the REQ ID
   - This handles: merge, SDLC artifact updates, knowledge capture, deployment, cleanup, and ship summary
2. Update `pipeline-state.json` with `"completed": true`
3. The pipeline is now complete

**Status update**: Report the ship summary from wrapup and confirm deployment status.

---

## Error Handling

- **Test failures during implementation**: Stop the current task, diagnose the failure, fix it, and re-run tests before continuing. If you can't fix it after 2 attempts, pause and ask the user.
- **Validation stuck after 3 loops**: Present the remaining FAIL items and ask the user how to proceed (fix manually, skip validation, or abort).
- **Missing context files**: If `.sdlc/context/` files don't exist, stop and tell the user to run `/init` first. Do not proceed without context files.
- **Merge conflicts**: If the feature branch has conflicts with the base branch, stop and ask the user how to resolve.

## Prerequisites

Before starting the pipeline, verify these exist (stop with a clear message if any are missing):
1. `.sdlc/context/project-overview.md` — run `/init` if missing
2. `.sdlc/context/architecture.md` — run `/init` if missing
3. `.sdlc/context/conventions.md` — run `/init` if missing
4. `.sdlc/specs/REQ-xxx-*/requirement.md` — run `/spec` if missing

## What This Skill Does NOT Do

- It does not create the initial spec — run `/spec` first
