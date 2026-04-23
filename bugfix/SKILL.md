---
name: bugfix
description: Streamlined bug fix workflow — report, analyze, fix, verify
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug in the Atelier Fashion project using a streamlined workflow that skips the full spec ceremony.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Bug template: !`cat .adlc/templates/bug-template.md 2>/dev/null || cat ~/.claude/skills/templates/bug-template.md 2>/dev/null || echo "No bug template found"`
- Conventions: !`cat .adlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
- Existing bugs: !`ls .adlc/bugs/ 2>/dev/null || echo "No bugs directory found"`

## Input

Bug report: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/bugs/` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first."

## Instructions

### Phase 1: Report
1. If given a bug description (not a BUG ID), create a bug report:
   - Determine the next BUG ID using the atomic counter at `.adlc/.next-bug`. Read the number, use it, and immediately write the incremented value back:
     ```bash
     BUG_NUM=$(cat .adlc/.next-bug 2>/dev/null || echo "1")
     echo $((BUG_NUM + 1)) > .adlc/.next-bug
     ```
     If `.adlc/.next-bug` doesn't exist, scan `.adlc/bugs/` for the highest BUG-xxx number, use the next one, and write the number after that.
   - Create `.adlc/bugs/BUG-xxx-slug.md` (always in the current repo — this becomes the "primary" for the bug) using the template from `.adlc/templates/bug-template.md`
   - Fill in: description, reproduction steps (if known), expected vs actual behavior, environment
   - Set status to `open`, severity based on impact
   - **Cross-repo**: if `.adlc/config.yml` declares siblings AND the bug's fix likely lives in a sibling (e.g., a frontend symptom whose root cause is in a backend repo), add a `repo: <sibling-id>` field to the bug frontmatter. If the fix spans multiple repos, add a `touched_repos: [<id>, <id>]` field. The `repo:` field determines where Phase 3's commit and Phase 4's PR land.
2. If given a BUG ID, read the existing bug report — note any `repo:` or `touched_repos:` field for routing.

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
1. **Determine target repo**: if the bug's frontmatter has `repo:` and it names a sibling (not this repo), cd into that sibling's path from `.adlc/config.yml` and do all fix work there. For `touched_repos: [...]`, cd into each in turn — one commit per repo, on a shared branch name. Otherwise fix in the current repo.
2. Proceed directly with the validated fix approach — do not pause for user confirmation
3. Implement the fix following project conventions
4. Ensure the fix addresses the root cause, not just symptoms
5. Update related test files if the fix changes behavior
6. Track progress with TodoWrite

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
Use `fix/bug-xxx-slug` for the branch name. In cross-repo bugs, use the same branch name in every touched repo so PRs can be linked visually.

## Commit Message Format
```
fix(BUG-xxx): short description of the fix
```

## Cross-Repo Bugs (brief)
When a bug's fix spans repos (via `touched_repos:` in the bug frontmatter):
- The bug report itself always lives in the repo `/bugfix` was invoked from (the "primary" for this bug).
- Phase 3 makes one commit per touched repo, each on a branch with the same name (`fix/bug-xxx-slug`).
- Phase 4 opens one PR per touched repo, cross-linking them in PR bodies (similar to `/proceed` Phase 6).
- Merges land in the order the repos are listed in `touched_repos:`. If the bug report doesn't specify an order, use the `merge_order` from `.adlc/config.yml`.
- If this gets complicated (more than 2 touched repos, or ordering matters), consider promoting the bug into a full REQ and using `/proceed` instead.
