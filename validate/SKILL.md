---
name: validate
description: Validate any SDLC phase output before advancing
argument-hint: REQ-xxx ID or phase name (spec, architecture, tasks, implementation)
---

# /validate — SDLC Phase Validation

You are validating SDLC artifacts to ensure quality before advancing to the next phase.

## Context

- Existing specs: !`ls .sdlc/specs/ 2>/dev/null || echo "No specs directory found"`

## Input

Target: $ARGUMENTS

## Instructions

### Step 1: Identify What to Validate
1. If given a REQ ID, locate all artifacts under `.sdlc/specs/REQ-xxx-*/`
2. If given a phase name, validate the most recently modified artifacts for that phase
3. Determine the current phase based on what artifacts exist:
   - **Spec phase**: Only `requirement.md` exists
   - **Architecture phase**: `architecture.md` exists alongside requirement
   - **Task phase**: `tasks/` directory with task files exists
   - **Implementation phase**: Tasks have status `complete` or code changes exist

### Step 2: Validate Based on Phase

#### Validating a Requirement Spec
- [ ] Frontmatter has valid id, title, status, created, updated fields
- [ ] Description clearly explains what AND why
- [ ] Acceptance criteria are specific, testable, and use checkbox format
- [ ] No implementation details in the requirement (belongs in architecture)
- [ ] Assumptions are explicitly stated
- [ ] Out of scope items are defined to prevent scope creep
- [ ] External dependencies are identified
- [ ] No duplicate or overlapping requirements with existing specs

#### Validating Architecture
- [ ] Architecture follows existing patterns from `.sdlc/context/architecture.md`
- [ ] New ADRs include rationale (not just decisions)
- [ ] Data model changes are compatible with existing Firestore schema
- [ ] API endpoint design follows REST conventions from `.sdlc/context/conventions.md`
- [ ] Service layer follows the layered pattern (routes → services → repositories)
- [ ] No architectural conflicts with other in-progress requirements

#### Validating Tasks
- [ ] Every task has valid frontmatter (id, title, status, parent, created, updated, dependencies)
- [ ] Tasks form a valid DAG — no circular dependencies
- [ ] Every acceptance criterion from the requirement is covered by at least one task
- [ ] Each task lists specific files to create/modify
- [ ] Tasks are appropriately scoped (not too large, not too granular)
- [ ] Test requirements are included in task acceptance criteria
- [ ] Dependencies reference valid task IDs

#### Validating Implementation
- [ ] All task acceptance criteria are met
- [ ] Tests pass (`npm test` or equivalent)
- [ ] Code follows conventions from `.sdlc/context/conventions.md`
- [ ] No new lint warnings or errors
- [ ] All requirement acceptance criteria are satisfied
- [ ] SDLC artifacts are updated (task statuses set to `complete`)

### Step 3: Report Results
1. Display validation results as a checklist with pass/fail for each item
2. Categorize issues by severity:
   - **Blocker**: Must fix before advancing (e.g., missing acceptance criteria, circular deps)
   - **Warning**: Should fix but won't block (e.g., vague wording, missing edge case)
   - **Info**: Suggestions for improvement
3. If all checks pass, confirm the artifact is ready to advance
4. If blockers exist, list specific fixes needed

### Step 4: Recommend Next Action
- Spec validated → "Ready for `/architect`"
- Architecture validated → "Ready for implementation"
- Tasks validated → "Ready for implementation"
- Implementation validated → "Ready for `/review`"
