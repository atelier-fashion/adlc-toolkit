---
name: status
description: Show current state of all ADLC work across the project
argument-hint: Optional filter (e.g., REQ-xxx, "in-progress", "bugs")
---

# /status — ADLC Status Dashboard

You are generating a status report of all ADLC work in the current project.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Specs directory: !`ls .adlc/specs/ 2>/dev/null || echo "No specs found"`
- Bugs directory: !`ls .adlc/bugs/ 2>/dev/null || echo "No bugs found"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`

## Input

Filter: $ARGUMENTS

## Instructions

### Step 1: Scan All ADLC Artifacts
1. Read all `requirement.md` files under `.adlc/specs/REQ-*/`
2. Read all task files under `.adlc/specs/REQ-*/tasks/`
3. Read all bug reports under `.adlc/bugs/`
4. Read all `pipeline-state.json` files under `.adlc/specs/REQ-*/` for live pipeline progress
5. Also check for nested `.adlc/` directories (e.g., `api/.adlc/`)
6. Extract frontmatter (id, title, status, updated) from each artifact

### Step 2: Build Status Report
Organize the report as follows:

#### Requirements Summary Table
| ID | Title | Status | Tasks | Progress |
|----|-------|--------|-------|----------|

For each requirement:
- Count total tasks and completed tasks
- Calculate progress percentage
- Show status from frontmatter

#### Active Pipelines
If any `pipeline-state.json` files exist with `"completed": false`, show:
| REQ | Branch | Current Phase | Started | Last Phase Completed |
|-----|--------|---------------|---------|---------------------|

Phase names: 0=Worktree, 1=Validate Spec, 2=Architect, 3=Validate Tasks, 4=Implement, 5=Verify, 6=Create PR, 7=PR Cleanup, 7.5=Canary, 8=Wrapup

#### In-Progress Work
List any artifacts with status `in-review`, `approved`, or in-progress tasks:
- Which requirement they belong to
- What phase they're in (spec, architecture, tasks, implementation)
- What's blocking progress (if any)

#### Open Bugs
| ID | Title | Severity | Status | Updated |
|----|-------|----------|--------|---------|

#### Recently Completed
List artifacts completed in the last 7 days (by `updated` date).

### Step 3: Apply Filters (if provided)
- If a REQ ID is given, show detailed status for just that requirement and its tasks
- If "in-progress" is given, show only non-complete work
- If "bugs" is given, show only bug reports
- If no filter, show the full dashboard

### Step 4: Highlight Action Items
At the bottom, list recommended next actions:
- Specs that are `draft` and need validation
- Approved specs that need architecture/tasks
- Tasks that are ready to implement (dependencies met)
- Bugs that are `open` and unassigned
