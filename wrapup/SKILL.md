---
name: wrapup
description: Close out a completed feature — update ADLC artifacts, log knowledge, and summarize
argument-hint: REQ-xxx ID to wrap up
---

# /wrapup — Feature Completion Wrap-Up

You are closing out a completed feature after it has been merged. This skill ensures ADLC artifacts are finalized, knowledge is captured, and the team has a clear summary of what shipped.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Active specs: !`grep -rl 'status: approved\|status: in-progress\|status: complete' .adlc/specs/*/requirement.md 2>/dev/null | tail -20 || echo "No specs found"`
- Knowledge directory: !`ls .adlc/knowledge/ 2>/dev/null || echo "No knowledge directory"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent merges: !`git log --oneline --merges -10 2>/dev/null || echo "No merge history"`

## Input

Target: $ARGUMENTS

## Instructions

### Step 1: Identify the Feature
1. If given a REQ ID, locate all artifacts under `.adlc/specs/REQ-xxx-*/`
2. If no REQ ID given, infer from the current branch name or recent merge commits
3. Read the requirement spec, architecture doc, and all task files

### Step 2: Commit, Push, and Merge
1. **Branch check FIRST** — never commit on `main`. Run `git branch --show-current`. If it reports `main` (or `master`), stop: create a feature branch (e.g., `agent/REQ-xxx-slug` or `feat/REQ-xxx-slug`) and switch to it with `git checkout -b <branch>` BEFORE touching any files. If you're already on a worktree branch from `/proceed` Phase 0, continue.
2. Check `git status` and `git diff` for any uncommitted changes related to the feature
3. If there are uncommitted changes:
   - Stage all relevant files (avoid secrets, `.env`, credentials)
   - Create a commit with message: `feat(REQ-xxx): <summary of changes>`
   - Include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
4. Push the branch to remote with `git push -u origin <branch>`
5. If no PR exists for this branch, create one using `gh pr create` with a summary of what shipped
6. If CI checks exist, monitor the pipeline with `gh run watch` and report the result
7. **Rebase onto current main before merging** — in a sprint or long-running pipeline, upstream `main` may have advanced since the branch was cut. Run `git fetch origin main` and check whether the branch is behind: `git merge-base --is-ancestor origin/main HEAD`. If that command fails (exit 1), the branch is behind main and must be updated:
   - `git rebase origin/main`
   - If there are conflicts, STOP and surface them to the user — do not try to resolve semantic conflicts blindly
   - On clean rebase, force-push with lease: `git push --force-with-lease`
   - Re-run `gh pr checks` and wait for CI to re-pass before merging
8. Verify PR status is mergeable: `gh pr view --json mergeable,mergeStateStatus` should report `MERGEABLE` and a clean merge state. If not, stop and surface the reason.
9. Merge the PR using `gh pr merge --squash --delete-branch`
10. Pull main locally: `git checkout main && git pull`
11. Clean up local branch and worktree immediately after merge:
    - If the feature branch still exists locally, delete it: `git branch -D <branch>`
    - If a worktree was used (`.worktrees/REQ-xxx` exists), remove it: `git worktree remove .worktrees/REQ-xxx`

### Step 3: Update ADLC Artifact Statuses
1. Set the requirement's frontmatter status to `complete`
2. Set all task statuses to `complete`
3. Update the `updated` date on all modified artifacts to today's date
4. If any tasks were deferred or descoped, note them in the requirement file under a "Deferred" section
5. If `pipeline-state.json` exists in the spec directory, update it: set `"completed": true` and add a final entry to `phaseHistory`

### Step 4: Capture Knowledge
Evaluate whether any decisions, patterns, or lessons should be persisted:

#### Architectural Decisions
- Were any new patterns introduced? If so, propose an update to `.adlc/context/architecture.md`
- Were any existing patterns modified or deprecated?

#### Assumptions Validated or Invalidated
- Review assumptions from the requirement spec
- Log any that were validated, invalidated, or still unresolved to `.adlc/knowledge/assumptions/`
- Use the assumption template (check `.adlc/templates/assumption-template.md` first, fall back to `~/.claude/skills/templates/assumption-template.md`)
- Name files: `ASSUME-xxx-slug.md` (scan existing files for next ID)

#### Lessons Learned
- Any surprises during implementation?
- Approaches that didn't work and why?
- Things that worked particularly well?
- Log notable lessons to `.adlc/knowledge/lessons/` if they'd help future work
- Use the lesson template (check `.adlc/templates/lesson-template.md` first, fall back to `~/.claude/skills/templates/lesson-template.md`)
- **Filename format is `LESSON-xxx-slug.md`** (e.g., `LESSON-041-signed-url-ttl-mismatch.md`). This is the ONLY permitted naming scheme — do not use date-prefixed names (`2026-MM-DD-…md`) or bare numeric prefixes (`034-…md`). To find the next ID, scan the directory for the highest existing `LESSON-xxx-` file and increment. Slugs are lowercase kebab-case, ≤6 words.
- **Legacy files**: older projects may still have date-prefixed or bare-numeric lessons from before this convention was locked. Do not rename them in a wrapup PR — migration is a separate, dedicated operation. When scanning for the next ID, only count files matching `LESSON-*.md`; treat the legacy files as read-only history.
- Include `domain`, `component`, and `tags` so that `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance. The `component` field should be more specific than `domain` (e.g., `domain: API`, `component: API/auth` or `domain: iOS`, `component: iOS/SwiftUI`)

#### Convention Updates
- Were any new conventions established? Propose updates to `.adlc/context/conventions.md`
- Were any existing conventions found to be problematic?

### Step 5: Generate Ship Summary
Create a concise summary suitable for sharing with the team:

```
## REQ-xxx: Feature Title

**Status**: Shipped
**Branch**: agent/REQ-xxx-slug
**PR**: #nn
**Merged**: YYYY-MM-DD

### What shipped
- Bullet points of user-facing or developer-facing changes

### Key decisions
- Notable architectural or design decisions made during implementation

### Metrics
- Files changed: N
- Lines added/removed: +N / -N
- Tests added: N
- Coverage impact: X% -> Y% (if measurable)

### Deferred items
- Any work explicitly postponed for future

### Follow-up needed
- Any remaining work, monitoring, or verification required
```

### Step 6: Deploy
1. Determine which components were changed by examining the files in the PR/commits:
   - **API changes** (`api/` files modified): Already deployed via CI/CD pipeline in Step 2. Confirm the deploy succeeded.
   - **iOS changes** (`app/` files modified): Deploy to both devices via WiFi using `cd app && ./deploy.sh`. Deploy to both unless told otherwise.
   - **Infrastructure changes** (`infrastructure/` files): Note that Terraform apply is needed and confirm with user.
2. If no deployable changes exist (e.g., only ADLC docs changed), skip this step.

### Step 7: Clean Up
1. Check for any temporary files, debug logging, or feature flags that should be removed
2. Verify CLAUDE.md or other docs don't need updates based on what shipped

### Step 8: Recommend Next Steps
- If deferred items exist: "Consider creating `/spec` for deferred items: [list]"
- If follow-up monitoring is needed: "Monitor [what] for [how long]"
- If conventions were updated: "Review `.adlc/context/conventions.md` changes"
- Otherwise: "Feature complete. No follow-up needed."
