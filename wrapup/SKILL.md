---
name: wrapup
description: Close out a completed feature — update SDLC artifacts, log knowledge, and summarize
argument-hint: REQ-xxx ID to wrap up
---

# /wrapup — Feature Completion Wrap-Up

You are closing out a completed feature after it has been merged. This skill ensures SDLC artifacts are finalized, knowledge is captured, and the team has a clear summary of what shipped.

## Ethos

!`cat ~/.claude/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Active specs: !`grep -rl 'status: approved\|status: in-progress\|status: complete' .sdlc/specs/*/requirement.md 2>/dev/null | tail -20 || echo "No specs found"`
- Knowledge directory: !`ls .sdlc/knowledge/ 2>/dev/null || echo "No knowledge directory"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent merges: !`git log --oneline --merges -10 2>/dev/null || echo "No merge history"`

## Input

Target: $ARGUMENTS

## Instructions

### Step 1: Identify the Feature
1. If given a REQ ID, locate all artifacts under `.sdlc/specs/REQ-xxx-*/`
2. If no REQ ID given, infer from the current branch name or recent merge commits
3. Read the requirement spec, architecture doc, and all task files

### Step 2: Commit, Push, and Merge
1. Check `git status` and `git diff` for any uncommitted changes related to the feature
2. If there are uncommitted changes:
   - Stage all relevant files (avoid secrets, `.env`, credentials)
   - Create a commit with message: `feat(REQ-xxx): <summary of changes>`
   - Include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
3. Ensure a feature branch exists (e.g., `agent/REQ-xxx-slug`). If on `main`, create one and switch to it before committing.
4. Push the branch to remote with `git push -u origin <branch>`
5. If no PR exists for this branch, create one using `gh pr create` with a summary of what shipped
6. If CI checks exist, monitor the pipeline with `gh run watch` and report the result
7. Merge the PR using `gh pr merge --squash --delete-branch`
8. Pull main locally: `git checkout main && git pull`

### Step 3: Update SDLC Artifact Statuses
1. Set the requirement's frontmatter status to `complete`
2. Set all task statuses to `complete`
3. Update the `updated` date on all modified artifacts to today's date
4. If any tasks were deferred or descoped, note them in the requirement file under a "Deferred" section
5. If `pipeline-state.json` exists in the spec directory, update it: set `"completed": true` and add a final entry to `phaseHistory`

### Step 4: Capture Knowledge
Evaluate whether any decisions, patterns, or lessons should be persisted:

#### Architectural Decisions
- Were any new patterns introduced? If so, propose an update to `.sdlc/context/architecture.md`
- Were any existing patterns modified or deprecated?

#### Assumptions Validated or Invalidated
- Review assumptions from the requirement spec
- Log any that were validated, invalidated, or still unresolved to `.sdlc/knowledge/assumptions/`
- Use the assumption template (check `.sdlc/templates/assumption-template.md` first, fall back to `~/.claude/skills/templates/assumption-template.md`)
- Name files: `ASSUME-xxx-slug.md` (scan existing files for next ID)

#### Lessons Learned
- Any surprises during implementation?
- Approaches that didn't work and why?
- Things that worked particularly well?
- Log notable lessons to `.sdlc/knowledge/lessons/` if they'd help future work
- Use the lesson template (check `.sdlc/templates/lesson-template.md` first, fall back to `~/.claude/skills/templates/lesson-template.md`)
- Name files: `LESSON-xxx-slug.md` (scan existing files for next ID)
- Include `domain`, `component`, and `tags` so that `/spec`, `/architect`, and `/reflect` can filter by relevance. The `component` field should be more specific than `domain` (e.g., `domain: API`, `component: API/auth` or `domain: iOS`, `component: iOS/SwiftUI`)

#### Convention Updates
- Were any new conventions established? Propose updates to `.sdlc/context/conventions.md`
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
2. If no deployable changes exist (e.g., only SDLC docs changed), skip this step.

### Step 7: Clean Up
1. If a worktree was used (`.worktrees/REQ-xxx` exists), remove it:
   ```bash
   git worktree remove .worktrees/REQ-xxx
   ```
2. If the feature branch still exists locally (it shouldn't after squash-merge with --delete-branch), clean it up: `git branch -d feat/REQ-xxx-slug`
3. Check for any temporary files, debug logging, or feature flags that should be removed
4. Verify CLAUDE.md or other docs don't need updates based on what shipped

### Step 8: Recommend Next Steps
- If deferred items exist: "Consider creating `/spec` for deferred items: [list]"
- If follow-up monitoring is needed: "Monitor [what] for [how long]"
- If conventions were updated: "Review `.sdlc/context/conventions.md` changes"
- Otherwise: "Feature complete. No follow-up needed."
