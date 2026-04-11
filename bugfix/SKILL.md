---
name: bugfix
description: Streamlined bug fix workflow — report, analyze, fix, verify
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug in the Atelier Fashion project using a streamlined workflow that skips the full spec ceremony.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Bug template: !`cat .sdlc/templates/bug-template.md 2>/dev/null || cat ~/.claude/skills/templates/bug-template.md 2>/dev/null || echo "No bug template found"`
- Conventions: !`cat .sdlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
- Existing bugs: !`ls .sdlc/bugs/ 2>/dev/null || echo "No bugs directory found"`

## Input

Bug report: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.sdlc/bugs/` exists. If it doesn't, stop and tell the user: "The `.sdlc/` structure hasn't been initialized. Run `/init` first."

## Instructions

### Phase 1: Report
1. If given a bug description (not a BUG ID), create a bug report:
   - Determine the next BUG ID using the atomic counter at `.sdlc/.next-bug`. Read the number, use it, and immediately write the incremented value back:
     ```bash
     BUG_NUM=$(cat .sdlc/.next-bug 2>/dev/null || echo "1")
     echo $((BUG_NUM + 1)) > .sdlc/.next-bug
     ```
     If `.sdlc/.next-bug` doesn't exist, scan `.sdlc/bugs/` for the highest BUG-xxx number, use the next one, and write the number after that.
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
4. Validate the analysis:
   - Re-read the affected code paths to confirm the root cause is correct
   - Check for secondary issues or edge cases related to the bug
   - Adjust the root cause and fix approach if validation reveals inaccuracies
5. Update the bug report with the validated findings

### Phase 3: Fix
1. Proceed directly with the validated fix approach — do not pause for user confirmation
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
