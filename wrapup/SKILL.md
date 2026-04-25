---
name: wrapup
description: Close out a completed feature — update ADLC artifacts, log knowledge, and summarize
argument-hint: REQ-xxx ID to wrap up
---

# /wrapup — Feature Completion Wrap-Up

You are closing out a completed feature after it has been merged. This skill ensures ADLC artifacts are finalized, knowledge is captured, and the team has a clear summary of what shipped.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

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
4. **Detect repository mode** — read `.adlc/config.yml` in the primary repo. If it declares more than one entry under `repos:`, this is **cross-repo mode**; otherwise **single-repo mode**. In cross-repo mode also read `pipeline-state.json` from the spec directory — it holds the per-repo branch/worktree/PR/merge state.

### Step 2: Commit, Push, and Merge

**Determine the repo set to operate on**:
- **Single-repo mode**: operate on the current repo only. Skip to the single-repo steps below.
- **Cross-repo mode from `/proceed`**: `pipeline-state.json` already lists touched repos; each `repos[<id>].merged` reflects whether `/proceed` Phase 8 already merged that PR. Walk `mergeOrder` and for each repo either confirm it's merged (no-op) or run the single-repo merge sequence inside that repo's worktree.
- **Cross-repo mode standalone**: no `pipeline-state.json` — fall back to detecting touched repos from the config and checking for feature branches/open PRs in each. Proceed with the single-repo merge sequence in each repo that has pending work, in `merge_order` from the config.

**Single-repo merge sequence** — run this block inside each target repo's worktree (same mechanics as before):

1. **Branch check FIRST** — never commit on `main`. Run `git -C <worktree> branch --show-current`. If it reports `main` (or `master`), stop: create a feature branch (e.g., `agent/REQ-xxx-slug` or `feat/REQ-xxx-slug`) and switch to it with `git checkout -b <branch>` BEFORE touching any files. If you're already on a worktree branch from `/proceed` Phase 0, continue.
2. Check `git -C <worktree> status` and `git -C <worktree> diff` for any uncommitted changes related to the feature
3. If there are uncommitted changes:
   - Stage all relevant files (avoid secrets, `.env`, credentials)
   - Create a commit with message: `feat(REQ-xxx): <summary of changes>`
   - Include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
4. Push the branch to remote with `git -C <worktree> push -u origin <branch>`
5. If no PR exists for this branch, create one using `gh pr create` (from inside the worktree, or with `gh -R <owner/repo>`) with a summary of what shipped
6. If CI checks exist, monitor the pipeline with `gh run watch` and report the result
7. **Rebase onto current main before merging** — in a sprint or long-running pipeline, upstream `main` may have advanced since the branch was cut. Run `git -C <worktree> fetch origin main` and check whether the branch is behind: `git -C <worktree> merge-base --is-ancestor origin/main HEAD`. If that command fails (exit 1), the branch is behind main and must be updated:
   - `git -C <worktree> rebase origin/main`
   - If there are conflicts, STOP and surface them to the user — do not try to resolve semantic conflicts blindly
   - On clean rebase, force-push with lease: `git -C <worktree> push --force-with-lease`
   - Re-run `gh pr checks <prUrl>` and wait for CI to re-pass before merging
8. Verify PR status is mergeable: `gh pr view <prUrl> --json mergeable,mergeStateStatus` should report `MERGEABLE` and a clean merge state. If not, stop and surface the reason.
9. Merge the PR using `gh pr merge <prUrl> --squash --delete-branch`. In cross-repo mode, update `pipeline-state.json` — set `repos[<id>].merged = true`.
10. **Capture cleanup state BEFORE leaving the branch**. You must record three things while you are still on the feature branch in the feature worktree, because the subsequent `git checkout main` may only work in the main worktree and you will lose the ability to look these up afterwards:
    - Branch name: `BRANCH=$(git -C <worktree> branch --show-current)`
    - Current working-tree path: `WT_PATH=<worktree>`
    - Main worktree path: `MAIN_WT=$(git -C <worktree> worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`
11. Move to the main worktree and update it: `git -C "$MAIN_WT" checkout main && git -C "$MAIN_WT" pull`
12. **Clean up local branch and worktree** (run from `$MAIN_WT`):
    - If `"$WT_PATH"` differs from `"$MAIN_WT"` (i.e., the work happened in a separate worktree), remove it: `git -C "$MAIN_WT" worktree remove "$WT_PATH"`. This handles BOTH the `/proceed` pattern (`.worktrees/REQ-xxx`) and the Claude Code harness pattern (`.claude/worktrees/<slug>`) without hardcoding either path.
    - If the feature branch still exists locally after the squash-merge (git does not recognize squash-merges as merged, so `git branch --merged` will miss it), delete it: `git -C "$MAIN_WT" branch -D "$BRANCH"`. Squash-merge is the default, so expect this to be the common case.
    - Prune any lingering remote-tracking refs: `git -C "$MAIN_WT" fetch --prune`
13. Verify cleanup: `git -C "$MAIN_WT" worktree list` should no longer include `$WT_PATH`, and `git -C "$MAIN_WT" branch` should no longer include `$BRANCH`. If either is still present, stop and surface the reason rather than silently moving on.

**Cross-repo aggregate log**: after walking every touched repo, emit a one-line summary per repo: `<repo-id>: merged <prUrl>, worktree cleaned` or `<repo-id>: already merged (from /proceed Phase 8)`.

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
- Name files: `ASSUME-xxx-slug.md`. Determine the next ID using the atomic counter at `.adlc/.next-assume` (LESSON-110):
  ```bash
  ASSUME_NUM=$(cat .adlc/.next-assume 2>/dev/null || echo "1")
  echo $((ASSUME_NUM + 1)) > .adlc/.next-assume
  ```
  If `.adlc/.next-assume` doesn't exist, scan `.adlc/knowledge/assumptions/` for the highest existing `ASSUME-xxx-` file, use the next one, and write the value after that to the counter. Use the counter ONLY — never re-scan after the counter exists. The counter prevents collisions when concurrent `/sprint` pipelines wrap up at the same time.

#### Lessons Learned
- Any surprises during implementation?
- Approaches that didn't work and why?
- Things that worked particularly well?
- Log notable lessons to `.adlc/knowledge/lessons/` if they'd help future work
- Use the lesson template (check `.adlc/templates/lesson-template.md` first, fall back to `~/.claude/skills/templates/lesson-template.md`)
- **Filename format is `LESSON-xxx-slug.md`** (e.g., `LESSON-041-signed-url-ttl-mismatch.md`). This is the ONLY permitted naming scheme — do not use date-prefixed names (`2026-MM-DD-…md`) or bare numeric prefixes (`034-…md`). Slugs are lowercase kebab-case, ≤6 words.
- **Allocate the next ID atomically via `.adlc/.next-lesson`** (LESSON-110 — directory scans race against concurrent `/sprint` pipelines):
  ```bash
  LESSON_NUM=$(cat .adlc/.next-lesson 2>/dev/null || echo "1")
  echo $((LESSON_NUM + 1)) > .adlc/.next-lesson
  ```
  If `.adlc/.next-lesson` doesn't exist, scan `.adlc/knowledge/lessons/` for the highest existing `LESSON-xxx-` file, use the next one, and write the value after that to the counter. Use the counter ONLY thereafter — never re-scan after the counter exists.
- **Legacy files**: older projects may still have date-prefixed or bare-numeric lessons from before this convention was locked. Do not rename them in a wrapup PR — migration is a separate, dedicated operation. When scanning for the next ID, only count files matching `LESSON-*.md`; treat the legacy files as read-only history.
- Include `domain`, `component`, and `tags` so that `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance. The `component` field should be more specific than `domain` (e.g., `domain: API`, `component: API/auth` or `domain: iOS`, `component: iOS/SwiftUI`)

#### Convention Updates
- Were any new conventions established? Propose updates to `.adlc/context/conventions.md`
- Were any existing conventions found to be problematic?

### Step 5: Generate Ship Summary
Create a concise summary suitable for sharing with the team. In cross-repo mode, list each repo/PR under a Repos section.

**Single-repo template**:
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

**Cross-repo template** (replace the single `PR`/`Branch` lines with a Repos table):
```
## REQ-xxx: Feature Title

**Status**: Shipped
**Merged**: YYYY-MM-DD

### Repos
| Repo | Branch | PR | Files | +/- |
|------|--------|----|-------|-----|
| admin-api | feat/REQ-xxx-... | #12 | 7 | +320 / -15 |
| admin-app | feat/REQ-xxx-... | #45 | 3 | +88 / -2 |
| admin-web | feat/REQ-xxx-... | #31 | 5 | +210 / -40 |

### What shipped
- Bullet points (call out cross-repo changes like new API contracts explicitly)

### Key decisions
### Metrics (aggregate across repos)
### Deferred items
### Follow-up needed
```

### Step 6: Deploy
Walk the touched repos and deploy each deployable service.

1. Determine which components were changed by examining each touched repo's PR/commits. Deploy decisions per repo:
   - **API/backend services** (Cloud Run-deployed services): Already deployed via CI/CD when their PR merged. Confirm each deploy succeeded (`gcloud run services describe ...`).
   - **iOS changes**: Deploy to both devices via WiFi using `cd <ios-repo-worktree-or-checkout> && ./deploy.sh`.
   - **Web frontend**: Confirm CI/CD deploy succeeded.
   - **Infrastructure changes**: Note that Terraform apply is needed and confirm with user.
2. If no touched repo has deployable changes (e.g., only ADLC docs changed), skip this step.
3. In cross-repo mode, emit a one-line deploy status per touched repo in the ship summary.

### Step 7: Clean Up
1. Check for any temporary files, debug logging, or feature flags that should be removed
2. Verify CLAUDE.md or other docs don't need updates based on what shipped

### Step 8: Recommend Next Steps
- If deferred items exist: "Consider creating `/spec` for deferred items: [list]"
- If follow-up monitoring is needed: "Monitor [what] for [how long]"
- If conventions were updated: "Review `.adlc/context/conventions.md` changes"
- Otherwise: "Feature complete. No follow-up needed."
