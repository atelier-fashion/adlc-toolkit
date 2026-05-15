---
name: validate
description: Validate any ADLC phase output before advancing
argument-hint: REQ-xxx ID or phase name (spec, architecture, tasks, implementation)
---

# /validate — ADLC Phase Validation

You are validating ADLC artifacts to ensure quality before advancing to the next phase.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .adlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

## Input

Target: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/specs/` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first."

## Instructions

### Step 1: Identify What to Validate
1. If given a REQ ID, locate all artifacts under `.adlc/specs/REQ-xxx-*/`
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
- [ ] Architecture follows existing patterns from `.adlc/context/architecture.md`
- [ ] New ADRs include rationale (not just decisions)
- [ ] Data model changes are compatible with existing Firestore schema
- [ ] API endpoint design follows REST conventions from `.adlc/context/conventions.md`
- [ ] Service layer follows the layered pattern (routes → services → repositories)
- [ ] No architectural conflicts with other in-progress requirements

#### Validating Tasks
- [ ] Every task has valid frontmatter (id, title, status, parent, created, updated, dependencies)
- [ ] Tasks form a valid DAG — no circular dependencies (including cross-repo dependencies)
- [ ] Every acceptance criterion from the requirement is covered by at least one task
- [ ] Each task lists specific files to create/modify
- [ ] Tasks are appropriately scoped (not too large, not too granular)
- [ ] Test requirements are included in task acceptance criteria
- [ ] Dependencies reference valid task IDs

**Cross-repo tasks** — only applies if `.adlc/config.yml` in the primary repo declares more than one entry under `repos:`. Skip these checks in single-repo mode.
- [ ] Every task has a `repo:` field in its frontmatter
- [ ] Every `repo:` value matches an id declared in `.adlc/config.yml` under `repos:`
- [ ] No task modifies files outside its declared `repo:` — all paths under "Files to Create/Modify" live in that repo
- [ ] At least one task targets the primary repo (even if just spec/doc updates) OR a follow-up confirms the primary needs no code changes
- [ ] Cross-repo dependencies make sense (e.g., a frontend task depending on a backend task, not the reverse)

#### Validating Implementation
- [ ] All task acceptance criteria are met
- [ ] Tests pass (`npm test` or equivalent)
- [ ] Code follows conventions from `.adlc/context/conventions.md`
- [ ] No new lint warnings or errors
- [ ] All requirement acceptance criteria are satisfied
- [ ] ADLC artifacts are updated (task statuses set to `complete`)

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
