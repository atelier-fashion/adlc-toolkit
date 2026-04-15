---
name: proceed
description: End-to-end ADLC pipeline that takes a requirement from spec through to deployed. Takes a REQ number as argument and runs validate → fix → architect → fix → implement → verify (reflect + review) → create PR → wrapup (merge, deploy, knowledge capture). Use when the user says "proceed", "proceed with REQ-xxx", "run the pipeline", "take REQ-xxx to completion", "implement REQ-xxx end to end", or wants to advance a drafted requirement all the way through to deployment in one shot.
---

# Proceed — Full ADLC Pipeline

You are an autonomous ADLC orchestrator. Given a requirement number (REQ-xxx), you drive it from validated spec all the way to a pull request — validating at each gate, fixing issues automatically, and only pausing when you're stuck or need human input.

## Execution Mode

This skill supports two modes:

1. **Main conversation mode** (default): Dispatches formal agents (defined in `~/.claude/agents/`) for parallelism at Phase 4 (task implementation) and Phase 5 (verify). Use this mode when running `/proceed` directly.
2. **Subagent mode** (when running as a `pipeline-runner` agent inside `/sprint`): Execute ALL phases sequentially in-context. Do NOT dispatch sub-agents. At Phase 4, implement tasks one at a time. At Phase 5, run the reflector + reviewer checklists sequentially in your own context using the criteria from the agent definitions. Subagents cannot spawn other subagents.

You are in subagent mode if you were explicitly told so in your launch prompt.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Arguments

The user provides a requirement ID, e.g., `/proceed REQ-023` or `/proceed 23`.

- Normalize to `REQ-xxx` format (zero-pad to 3 digits if needed)
- Locate the spec at `.adlc/specs/REQ-xxx-*/requirement.md`
- If the spec doesn't exist, stop and tell the user to run `/spec` first

## The Pipeline

Execute these phases in order. Each phase has a validation gate — if validation fails, fix the issues and re-validate. Loop up to 3 times per gate; if still failing after 3 attempts, stop and present the remaining issues to the user.

## Pipeline State Tracking

**CRITICAL**: You MUST maintain a state file to track pipeline progress. This prevents phases from being skipped during long-running pipelines.

**State file location**: `.adlc/specs/REQ-xxx-*/pipeline-state.json`

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
  ],
  "phase4": {
    "currentTask": null,
    "completedTasks": [],
    "failedTasks": []
  }
}
```

The `phase4` block tracks task-level progress during implementation so that a mid-Phase-4 context compression can resume from the exact task in progress rather than restarting the phase. `currentTask` holds the TASK-xxx ID being worked on right now; `completedTasks` holds IDs of tasks whose status is `complete` and whose commit has landed; `failedTasks` holds IDs that hit unrecoverable errors and were surfaced to the user. Other phases do not need sub-state.

**Gate Protocol — follow exactly**:

1. **Initialize** the state file at the start of Step 0 with `currentPhase: 0, completedPhases: [], completed: false, phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`
2. **Before starting any phase**: read `pipeline-state.json`. Verify `currentPhase` equals the phase you're about to start AND the previous phase is in `completedPhases`. If either check fails, **STOP** — you skipped a phase. Go back and complete it.
3. **After completing any phase**: append the phase number to `completedPhases`, append an entry to `phaseHistory` with the completion timestamp, set `currentPhase` to the next phase number.
4. **Phase 4 task-level writes**: When starting a task, set `phase4.currentTask` to its TASK-xxx ID. When its commit lands, append the ID to `phase4.completedTasks` and clear `currentTask`. On unrecoverable failure surfaced to the user, append to `phase4.failedTasks` instead.
5. **Resume from interruption**: If the state file already exists when you start, read it and resume from `currentPhase`. If `currentPhase` is 4 and `phase4.currentTask` is non-null, resume that specific task (re-read its file, re-check whether its commit already landed, continue or restart as appropriate) before moving to the next task in the dependency graph. Never replay tasks already in `completedTasks`.
6. **If context has been compressed**: re-read `pipeline-state.json` before doing anything and treat it as the source of truth for `currentPhase` and `phase4`. Do not rely on memory of which phase or task you're in.
7. **On completion**: After Phase 8 (Wrapup) finishes, set `"completed": true` in the state file.

Each phase below has a one-line **Gate** reminder. The full protocol above applies to every gate.

---

### Step 0: Create Worktree + Preflight + Load Shared Context (ALWAYS FIRST)

**Before doing anything else**, isolate this work in a git worktree and prime the shared context so subskills don't re-read the same files:

1. **Preflight** — verify all prerequisite files exist (stop with a clear message if any are missing):
   - `.adlc/context/project-overview.md` — run `/init` if missing
   - `.adlc/context/architecture.md` — run `/init` if missing
   - `.adlc/context/conventions.md` — run `/init` if missing
   - `.adlc/specs/REQ-xxx-*/requirement.md` — run `/spec` if missing
2. Ensure main is up to date: `git checkout main && git pull`
3. Create a worktree with a dedicated branch:
   ```bash
   git worktree add .worktrees/REQ-xxx feat/REQ-xxx-short-description
   ```
4. Change your working directory to `.worktrees/REQ-xxx` — **all subsequent work happens there**
5. **Load shared context ONCE** — use the Read tool to load these into conversation context so every subskill can reference them without re-reading:
   - `.adlc/context/architecture.md`
   - `.adlc/context/conventions.md`
   - `.adlc/context/project-overview.md`
   - `.adlc/specs/REQ-xxx-*/requirement.md`
6. **Initialize `pipeline-state.json`** in the spec directory with `currentPhase: 0, completedPhases: [], completed: false, startedAt: <now>, phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`. If the file already exists, read it and resume from `currentPhase` (and from `phase4.currentTask` if mid-Phase-4).
7. When the pipeline completes (PR merged), clean up:
   ```bash
   git worktree remove .worktrees/REQ-xxx
   ```

**Preflight verified** — when you invoke subskills in later phases, they may skip their own prerequisite checks (already validated here) AND they may skip re-reading `architecture.md` / `conventions.md` / `project-overview.md` (already in context). Treat the Step 0 loads as authoritative for the rest of the pipeline.

**After completing Step 0**: Update `pipeline-state.json` — add `0` to `completedPhases`, add Step 0 to `phaseHistory`, set `currentPhase` to `1`.

---

### Phase 1: Validate the Requirement Spec

**Gate**: `currentPhase` must be `1`. After completion: append `1`, set `currentPhase=2`.

**Goal**: Ensure the requirement is complete and well-formed before designing architecture.

1. Invoke the `/validate` skill with the REQ ID
2. If **APPROVED**: set requirement status to `approved` and move to Phase 2
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**Status update**: After this phase, report "Spec validated and approved" before continuing.

---

### Phase 2: Architect & Break Into Tasks

**Gate**: `currentPhase` must be `2`. After completion: append `2`, set `currentPhase=3`.

**Goal**: Design the technical approach and create implementation tasks.

1. Invoke the `/architect` skill with the REQ ID
2. This handles: reading context, designing architecture, creating task files with dependencies, and updating requirement status

**Status update**: Summarize the architecture approach and list all tasks with dependency graph.

---

### Phase 3: Validate Architecture & Tasks

**Gate**: `currentPhase` must be `3`. After completion: append `3`, set `currentPhase=4`.

**Goal**: Ensure the architecture and task breakdown are solid before implementation.

1. Invoke the `/validate` skill with the REQ ID (it will auto-detect the architecture+tasks phase)
2. If **APPROVED**: move to Phase 4
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**Status update**: Report "Architecture and tasks validated" before continuing.

---

### Phase 4: Implement

**Gate**: `currentPhase` must be `4`. After completion: append `4`, set `currentPhase=5`.

**Goal**: Execute all tasks, producing working code with tests.

1. Build the dependency graph from task frontmatter
2. Identify independent tasks (no unmet dependencies) — these can run in parallel
3. On resume: read `pipeline-state.json`. Skip any task in `phase4.completedTasks`. If `phase4.currentTask` is non-null, start there (not at the dependency root).
4. For each task (or batch of independent tasks):
   - Write `phase4.currentTask` to the TASK-xxx ID before starting work
   - Read the task file for requirements, files to modify, ACs, technical notes
   - Implement the changes following project conventions (from `.adlc/context/conventions.md`)
   - Write tests as specified in the task
   - Run the project's test suite to verify nothing is broken
   - Mark the task status as `complete` in its frontmatter
   - Commit with message format: `feat(scope): description [TASK-xxx]`
   - After the commit lands, append the TASK-xxx ID to `phase4.completedTasks` and clear `phase4.currentTask`
5. If a task hits an unrecoverable failure surfaced to the user: append its ID to `phase4.failedTasks`, clear `phase4.currentTask`, and stop the phase.

**Main conversation mode** — parallel execution:
- Group tasks into tiers based on the dependency graph
- Tier 0: tasks with no dependencies — launch a **task-implementer** agent for each
- Tier 1: tasks depending only on Tier 0 — launch after Tier 0 completes
- Continue until all tiers complete
- Each task-implementer agent (defined in `~/.claude/agents/`) receives: the full task file, conventions.md, and architecture.md

**Subagent mode** — sequential execution:
- Execute tasks one at a time in dependency order
- Implement each task directly in your own context (do not dispatch agents)

**Status update**: After each tier completes, report which tasks finished and any issues encountered.

---

### Phase 5: Verify (Reflect + Review in Parallel)

**Gate**: `currentPhase` must be `5`. After completion: append `5`, set `currentPhase=6`.

**Goal**: Self-assess AND multi-agent review the implementation, then fix all findings in a single consolidated pass.

**Main conversation mode** — parallel agents:

**Step A — Launch 6 READ-ONLY agents in parallel**. In a single message, dispatch six Agent tool calls using the formal agent definitions from `~/.claude/agents/`. This matches the dimensions covered by `/review` (correctness, quality, architecture, test coverage, security) plus the reflector self-assessment, so that feature work shipped via `/proceed` gets the same gate coverage as work shipped via `/review`:

1. **reflector** agent — provide REQ-xxx, changed files, diff, conventions.md, architecture.md. Tell it: "Report findings only. The parent pipeline will apply fixes."
2. **correctness-reviewer** agent — provide changed files, diff, conventions.md. Tell it: "Report findings only. Do not apply fixes."
3. **quality-reviewer** agent — provide changed files, diff, conventions.md. Tell it: "Report findings only. Do not apply fixes."
4. **architecture-reviewer** agent — provide changed files, diff, architecture.md. Tell it: "Report findings only. Do not apply fixes."
5. **test-auditor** agent — provide changed files, diff, conventions.md. Tell it: "Audit test coverage only for the diff under review. Report findings only. Do not apply fixes."
6. **security-auditor** agent — provide changed files, diff, conventions.md. Tell it: "Audit security posture only for the diff under review. Report findings only. Do not apply fixes."

**Subagent mode** — sequential inline review:
Run the reflector checklist, then the correctness, quality, architecture, test-auditor, and security-auditor checklists sequentially in your own context. Use the criteria from the agent definitions in `~/.claude/agents/`. Do NOT dispatch sub-agents.

**Step B — Consolidate**: When all 6 agents return (or all checklists complete in subagent mode), dedupe overlapping findings (reflector and reviewers often catch the same convention/architecture issues; test-auditor and security-auditor can overlap on missing input validation tests). Produce a single ranked list by severity.

**Step C — Fix in one pass**:
1. **Critical + must-fix Major** (bugs, security, convention violations, missing tests): fix immediately, run the test suite after each related cluster of fixes, commit with `fix(scope): address verify finding [REQ-xxx]`.
2. **Should-fix Minor** (code quality, naming): fix unless doing so would be a significant refactor — note those as follow-ups.
3. **Nit / observation**: fix trivial ones inline, skip the rest.
4. **User-facing questions from reflector**: if any, surface them to the user as a numbered list and wait for answers before continuing.

**Step D — Re-verify (conditional)**: Re-run ONLY the 5 reviewer agents (**correctness-reviewer**, **quality-reviewer**, **architecture-reviewer**, **test-auditor**, **security-auditor** — not reflector) if Critical or must-fix Major items were fixed — up to 1 confirmation loop. Skip if only minor fixes were applied. Scope re-verify to the dimensions that had fixes: e.g., if only correctness fixes landed, rerun correctness + any other dimensions whose findings overlapped. In subagent mode, re-run the corresponding reviewer checklists inline.

**Status update**: Report the combined verify summary — reflect observations, review findings, dedupe count, how many fixed, any deferred, any outstanding user questions.

---

### Phase 6: Create Pull Request

**Gate**: `currentPhase` must be `6`. After completion: append `6`, set `currentPhase=7`.

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

### Phase 7: PR Cleanup & CI

**Gate**: `currentPhase` must be `7`. After completion: append `7`, set `currentPhase=8` (or `7.5` if canary will run).

**Goal**: Lightweight sanity check on the PR — the full code review already happened in Phase 5. Do NOT re-run `/review`.

1. Review the full PR diff using `gh pr diff`
2. Check for:
   - Stray debug logs, TODOs, or commented-out code
   - Files that shouldn't have been included (secrets, generated files, unrelated changes)
   - Commit message consistency and cleanliness
   - That the PR description accurately reflects the changes
3. If issues are found:
   - Fix them, commit with message: `fix(scope): PR cleanup [REQ-xxx]`
   - Push to the feature branch
4. If CI checks are configured, verify they pass: `gh pr checks`

**Status update**: Report "PR is clean and ready for merge" or list any remaining concerns.

---

### Phase 7.5: Canary Deploy (Optional)

**Gate**: `7` must be in `completedPhases`. After completion: append `7.5`, set `currentPhase=8`. This phase is **optional** — only run it if the requirement's frontmatter includes `deployable: true`, OR if no `deployable` field exists and the changes include deployable API or web service code (`api/`, `admin-api/`, or web app files). Skip when `deployable: false` or for iOS-only, documentation-only, or infrastructure-only changes.

**Goal**: Deploy to a canary revision with zero traffic, run smoke tests, and promote only on success — ensuring the deploy works before merging.

1. Determine which service(s) were changed (fashion-api, admin-api, atelier-web)
2. For each affected service, invoke the `/canary` skill
3. If canary passes: proceed to Phase 8
4. If canary fails: stop and present the failure to the user. Options:
   - Fix the issue and re-run `/canary`
   - Skip canary and proceed to merge (user must explicitly confirm)
   - Abort the pipeline

**Status update**: Report canary results — service, revision, smoke test pass/fail.

---

### Phase 8: Wrapup

**Gate**: `currentPhase` must be `8` and `7` (or `7.5`) must be in `completedPhases`. After completion: append `8`, set `"completed": true`.

**Goal**: Merge, deploy, capture knowledge, and close out the feature.

1. Run the `/wrapup` skill with the REQ ID
   - This handles: merge, ADLC artifact updates, knowledge capture, deployment, cleanup, and ship summary
2. Update `pipeline-state.json` with `"completed": true`
3. The pipeline is now complete

**Status update**: Report the ship summary from wrapup and confirm deployment status.

---

## Error Handling

- **Test failures during implementation**: Stop the current task, diagnose the failure, fix it, and re-run tests before continuing. If you can't fix it after 2 attempts, pause and ask the user.
- **Validation stuck after 3 loops**: Present the remaining FAIL items and ask the user how to proceed (fix manually, skip validation, or abort).
- **Missing context files**: If `.adlc/context/` files don't exist, stop and tell the user to run `/init` first. Do not proceed without context files.
- **Merge conflicts**: If the feature branch has conflicts with the base branch, stop and ask the user how to resolve.

## Prerequisites

Verified by Phase 0 Preflight — see Step 0 above.

## What This Skill Does NOT Do

- It does not create the initial spec — run `/spec` first
