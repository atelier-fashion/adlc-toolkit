---
name: proceed
description: End-to-end SDLC pipeline that takes a requirement from spec through to PR. Takes a REQ number as argument and runs validate → fix → architect → fix → implement → reflect → fix → create PR. Use when the user says "proceed", "proceed with REQ-xxx", "run the pipeline", "take REQ-xxx to completion", "implement REQ-xxx end to end", or wants to advance a drafted requirement all the way through architecture, implementation, and PR creation in one shot.
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

### Step 0: Create Worktree (ALWAYS FIRST)

**Before doing anything else**, isolate this work in a git worktree so parallel sessions don't collide:

1. Ensure main is up to date: `git checkout main && git pull`
2. Create a worktree with a dedicated branch:
   ```bash
   git worktree add .worktrees/REQ-xxx feat/REQ-xxx-short-description
   ```
3. Change your working directory to `.worktrees/REQ-xxx` — **all subsequent work happens there**
4. When the pipeline completes (PR merged), clean up:
   ```bash
   git worktree remove .worktrees/REQ-xxx
   ```

This ensures multiple `/proceed` sessions on different REQs never touch each other's files.

---

### Phase 1: Validate the Requirement Spec

**Goal**: Ensure the requirement is complete and well-formed before designing architecture.

1. Read `.sdlc/specs/REQ-xxx-*/requirement.md`
2. Run requirement validation (the checks from `/validate`):
   - Completeness: all template sections present, YAML frontmatter correct
   - AC quality: each AC independently testable, checkbox format, 5-10 ACs
   - Scope hygiene: Out of Scope is specific, assumptions explicit, questions formatted
   - Cross-references: no overlap with other specs in `.sdlc/specs/`
3. If **APPROVED**: set requirement status to `approved` and move to Phase 2
4. If **NEEDS REVISION**: fix all FAIL items, then re-validate (up to 3 loops)

**Status update**: After this phase, report "Spec validated and approved" before continuing.

---

### Phase 2: Architect & Break Into Tasks

**Goal**: Design the technical approach and create implementation tasks.

1. Read context files:
   - `.sdlc/context/architecture.md`
   - `.sdlc/context/conventions.md`
   - `.sdlc/knowledge/assumptions/` for prior decisions that may affect design
   - `.sdlc/knowledge/lessons/` — scan titles and read any relevant to this requirement's domain, patterns, or tech. Apply applicable lessons to architecture decisions and implementation approach.
   - Relevant source files to understand current implementation
2. Design the architecture:
   - Create `.sdlc/specs/REQ-xxx-*/architecture.md` if architectural decisions are needed
   - Document approach, affected components, ADRs, data model changes, API contracts, trade-offs
3. Break into tasks:
   - Create task files at `.sdlc/specs/REQ-xxx-*/tasks/TASK-xxx-description.md`
   - Each task: frontmatter (id, title, status: draft, parent, dependencies), description, files to modify, ACs, technical notes
   - Respect sizing: 3-5 files per task, tests with their code, infra separate from features
   - Respect ordering: data layer → service → route → client
   - Ensure every requirement AC maps to at least one task AC

**Status update**: Summarize the architecture approach and list all tasks with dependency graph.

---

### Phase 3: Validate Architecture & Tasks

**Goal**: Ensure the architecture and task breakdown are solid before implementation.

1. Run architecture validation:
   - Every requirement AC addressable by the architecture
   - ADRs documented with decision, rationale, alternatives
   - File paths reference real files or are marked "new file"
   - Data model changes backward-compatible or migration noted
2. Run task breakdown validation:
   - AC traceability: every requirement AC covered by at least one task
   - Dependency graph is acyclic, no task has >2 dependencies
   - Sizing within limits, file paths verified
   - Frontmatter complete and consistent
3. If **APPROVED**: move to Phase 4
4. If **NEEDS REVISION**: fix all FAIL items, then re-validate (up to 3 loops)

**Status update**: Report "Architecture and tasks validated" before continuing.

---

### Phase 4: Implement

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

**Goal**: Self-assess the implementation and address any concerns.

1. Review all changes made during implementation:
   - What went well, what's fragile, what you'd do differently
   - Assumptions made, edge cases that might not be covered
   - Test gaps, hidden coupling, production risks
2. If the reflection surfaces concrete issues (not just observations):
   - Fix them immediately
   - Run tests again to verify
   - Commit fixes with message: `fix(scope): address reflection finding [REQ-xxx]`
3. Loop: re-reflect on fixes, fix again if needed (up to 3 loops, stop if only observations remain)

**Status update**: Share the reflection summary and note any fixes applied.

---

### Phase 6: Code Review & Fix

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

## Error Handling

- **Test failures during implementation**: Stop the current task, diagnose the failure, fix it, and re-run tests before continuing. If you can't fix it after 2 attempts, pause and ask the user.
- **Validation stuck after 3 loops**: Present the remaining FAIL items and ask the user how to proceed (fix manually, skip validation, or abort).
- **Missing context files**: If `.sdlc/context/` files don't exist, suggest the user run `/init` first.
- **Merge conflicts**: If the feature branch has conflicts with the base branch, stop and ask the user how to resolve.

## What This Skill Does NOT Do

- It does not create the initial spec — run `/spec` first
- It does not deploy — run `/wrapup` after the PR is merged if you want deployment
