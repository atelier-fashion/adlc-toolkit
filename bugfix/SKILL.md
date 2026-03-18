---
name: bugfix
description: Streamlined bug fix workflow — report, analyze, fix, verify
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug in the Atelier Fashion project using a streamlined workflow that skips the full spec ceremony.

## Context

- Bug template: !`cat .sdlc/templates/bug-template.md 2>/dev/null || echo "No bug template found"`
- Conventions: !`cat .sdlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
- Existing bugs: !`ls .sdlc/bugs/ 2>/dev/null || echo "No bugs directory found"`

## Input

Bug report: $ARGUMENTS

## Instructions

### Phase 1: Report
1. If given a bug description (not a BUG ID), create a bug report:
   - Determine the next BUG ID by scanning `.sdlc/bugs/`
   - Create `.sdlc/bugs/BUG-xxx-slug.md` using the template from `.sdlc/templates/bug-template.md`
   - Fill in: description, reproduction steps (if known), expected vs actual behavior, environment
   - Set status to `open`, severity based on impact
2. If given a BUG ID, read the existing bug report

### Phase 2: Analyze
1. Launch Explore agents to trace the bug:
   - Search for relevant code paths based on the bug description
   - Trace the execution flow that triggers the bug
   - Identify the root cause (not just symptoms)
2. Read the identified files to understand the context
3. Document the root cause in the bug report's "Root Cause" section
4. Present findings to the user:
   - What's happening and why
   - Which files are affected
   - Proposed fix approach

### Phase 3: Fix
1. Wait for user confirmation of the fix approach
2. Implement the fix following project conventions
3. Ensure the fix addresses the root cause, not just symptoms
4. Update related test files if the fix changes behavior
5. Track progress with TodoWrite

### Phase 4: Verify
1. Run the test suite: `npm test` (or appropriate test command)
2. If tests fail, fix and re-run
3. Update the bug report:
   - Set status to `resolved`
   - Fill in "Resolution" section with what was changed and why
   - Fill in "Files Changed" section with specific file paths
   - Update the `updated` date
4. Present a summary:
   - Root cause
   - What was fixed
   - Files changed
   - Test results

## Branch Naming
Use `fix/bug-xxx-slug` for the branch name.

## Commit Message Format
```
fix(BUG-xxx): short description of the fix
```
