---
name: architect
description: Design architecture and break requirement into tasks
argument-hint: REQ-xxx ID or requirement description
---

# /architect — Architecture & Task Breakdown

You are designing architecture and breaking a requirement into implementable tasks for the Atelier Fashion project.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Task template: !`cat .sdlc/templates/task-template.md 2>/dev/null || cat ~/.claude/skills/templates/task-template.md 2>/dev/null || echo "No task template found"`
- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .sdlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

**Context files loaded on demand**: `.sdlc/context/architecture.md` and `.sdlc/context/conventions.md` are loaded by Step 1 below — **skip the Read if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads them at Phase 0).

## Input

Requirement: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.sdlc/context/architecture.md` and `.sdlc/context/conventions.md` exist. If either is missing, stop and tell the user: "The `.sdlc/` structure hasn't been fully initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Locate and Read the Requirement
1. If given a REQ ID, read `.sdlc/specs/REQ-xxx-*/requirement.md`
2. If given a description, search `.sdlc/specs/` for the matching requirement
3. Verify the requirement status is `draft` or `approved` (not already `complete`)
4. **Context files**: if `.sdlc/context/architecture.md` and `.sdlc/context/conventions.md` are NOT already in your conversation context (e.g., this skill is being run standalone, not from `/proceed`), Read them now. Otherwise skip — they're already loaded.
5. Check `.sdlc/knowledge/assumptions/` for prior decisions that may affect design
6. **Lessons — grep first, then read only matches**: use the Grep tool on `.sdlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` to identify matching files. Then Read ONLY those matched files. Do NOT read all lessons. Note applicable lessons in your architecture rationale so past mistakes aren't repeated and proven patterns are reused.

### Step 2: Explore the Codebase
1. Launch 2-3 Explore agents in parallel to understand the relevant parts of the codebase:
   - One agent to trace similar existing features and their implementation patterns
   - One agent to map the architecture and files that will be affected
   - One agent to identify extension points, tests, and integration surfaces
2. Read the key files identified by agents

### Step 3: Design Architecture (if needed)
1. If the requirement involves new architectural decisions, create `.sdlc/specs/REQ-xxx-*/architecture.md`
2. Document:
   - **Approach**: High-level design and rationale
   - **Data model changes**: New Firestore collections/fields, GCS metadata
   - **API changes**: New or modified endpoints
   - **Service layer**: New or modified services
   - **Key decisions**: ADRs with rationale (follow the style in `.sdlc/context/architecture.md`)
3. Propose any additions to `.sdlc/context/architecture.md` with rationale

### Step 4: Break Into Tasks
1. Create `.sdlc/specs/REQ-xxx-*/tasks/` directory
2. Determine the next TASK ID by checking existing tasks across ALL specs (not just this one)
3. Create `TASK-xxx-description.md` for each task using the template from `.sdlc/templates/task-template.md`
4. Each task must specify:
   - **Frontmatter**: id, title, status (`draft`), parent REQ, created/updated dates, dependencies
   - **Description**: What this task accomplishes
   - **Files to Create/Modify**: Specific file paths with descriptions of changes
   - **Acceptance Criteria**: Concrete, testable criteria
   - **Technical Notes**: Implementation details, patterns to follow, edge cases
   - **Dependencies**: Other tasks that must complete first
5. Tasks must form a valid dependency graph (no cycles)
6. Order tasks so foundational work comes first (data layer → service → routes → UI)

### Step 5: Update Requirement Status
1. Update the requirement's frontmatter status from `draft` to `approved`
2. Update the `updated` date

### Step 6: Present for Review
1. Display the architecture decisions (if any)
2. Display the task breakdown as a dependency graph
3. Summarize the implementation plan
4. Remind the user to run `/validate` before starting implementation

## Quality Checklist
- [ ] Architecture follows existing patterns (layered: routes → services → repositories)
- [ ] Tasks are small enough to implement in a single session
- [ ] Task dependencies form a valid DAG (no cycles)
- [ ] Every file to be modified is listed in at least one task
- [ ] Tests are included in task acceptance criteria
- [ ] No task has more than 3 dependencies
