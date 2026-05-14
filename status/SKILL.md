---
name: status
description: Show current state of all ADLC work across the project
argument-hint: Optional filter (e.g., REQ-xxx, "in-progress", "bugs")
---

# /status — ADLC Status Dashboard

You are generating a status report of all ADLC work in the current project.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Specs directory: !`ls .adlc/specs/ 2>/dev/null || echo "No specs found"`
- Bugs directory: !`ls .adlc/bugs/ 2>/dev/null || echo "No bugs found"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`

## Input

Filter: $ARGUMENTS

## Prerequisites

Before proceeding, verify that the `.adlc/specs/` directory exists (this skill reads requirement and task files from there, plus `.adlc/bugs/` and any `pipeline-state.json` files). If any of these files are missing, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Scan All ADLC Artifacts

**Detect repository mode** — read `.adlc/config.yml`. If it declares more than one entry under `repos:`, this is **cross-repo mode**; otherwise **single-repo mode**.

1. Read all `requirement.md` files under `.adlc/specs/REQ-*/` (this repo)
2. Read all task files under `.adlc/specs/REQ-*/tasks/`
3. Read all bug reports under `.adlc/bugs/`
4. Read all `pipeline-state.json` files under `.adlc/specs/REQ-*/` for live pipeline progress
5. Also check for nested `.adlc/` directories (e.g., `api/.adlc/`)
6. Extract frontmatter (id, title, status, updated) from each artifact

**Cross-repo scan** (only in cross-repo mode): for every sibling declared in `.adlc/config.yml`:
- Resolve the sibling's absolute path from `repos[<id>].path`
- Read `<sibling-path>/.adlc/specs/REQ-*/pipeline-state.json` to find REQs where the sibling was primary. Any of those that have a `repos` block listing the current repo as `touched: true` represents cross-repo work that affects us but originates elsewhere.
- Capture REQ id, primary repo id, state file path, and current phase for the cross-repo report section (Step 2).

Cross-repo scan is read-only — `/status` never modifies sibling repos.

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
| REQ | Primary | Branch | Current Phase | Started | Last Phase Completed | Touched Repos |
|-----|---------|--------|---------------|---------|----------------------|---------------|

- **Primary** column: which repo the REQ originates from (the repo holding the state file). In single-repo mode this is always the current repo; omit the column if no cross-repo config exists.
- **Touched Repos** column: only populated in cross-repo mode — list every repo id from the state file's `repos` block where `touched: true`, with a ✓ for merged and a clock for in-progress.

Phase names: 0=Worktree, 1=Validate Spec, 2=Architect, 3=Validate Tasks, 4=Implement, 5=Verify, 6=Create PR, 7=PR Cleanup, 7.5=Canary, 8=Wrapup

#### Cross-Repo Activity (cross-repo mode only)
If the cross-repo scan found REQs originating elsewhere that touch this repo, surface them separately so the user sees inbound cross-repo work without losing context on local REQs:

| REQ | Primary (origin) | Current Phase | This Repo's Role | Branch Here |
|-----|------------------|---------------|------------------|-------------|
| REQ-091 | api       | 4/8 Implement | sibling (touched) | feat/REQ-091-... |

"Branch Here" is detected by checking `git -C <this-repo> branch --list feat/REQ-xxx-*`. If absent, the REQ hasn't reached Phase 4 yet or this repo isn't touched after all.

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
