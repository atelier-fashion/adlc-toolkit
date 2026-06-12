---
name: bugfix
description: End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + merge + deploy + knowledge capture)
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug using a streamlined workflow that skips the full spec ceremony but follows the **same deployment strategy as a feature**: changes land via PR, ride the project's CI/CD pipeline (staging-first if the project has one), and aren't marked resolved until every declared deploy target is confirmed.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Project config: !`cat .adlc/config.yml 2>/dev/null || echo "No config — single-repo legacy mode"`
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
   - Determine the next BUG ID using the **global** atomic counter file `~/.claude/.global-next-bug` (shared across all repos for unique IDs, mirroring the REQ counter — see LESSON-004). The counter is now a **cache, not the authority** — the remote is the source of truth (REQ-518): allocation derives the remote high-water, takes `max(remote, local) + 1`, and fast-forwards the local counter, all inside the existing `mkdir` lock. Allocate via the shared `partials/id-alloc.sh` helper (BR-5 — the lock block + its REQ-416/LESSON-014 rationale live in the partial). Source it and call `adlc_alloc_id` **in the same fenced block** (the cross-fence-fn rule — see conventions.md "Bash in skills"):
     ```bash
     . .adlc/partials/id-alloc.sh 2>/dev/null || . ~/.claude/skills/partials/id-alloc.sh
     BUG_NUM=$(adlc_alloc_id bug)
     # `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — BUG_NUM
     # would be silently empty. Guard the parent context (REQ-416 verify D-pass).
     [ -n "$BUG_NUM" ] || { echo "ERROR: failed to allocate BUG number — aborting before writing malformed bug report" >&2; exit 1; }
     # If ADLC_ALLOC_DEGRADED=1 (remote unreachable), the helper warned on stderr — note
     # "id allocated without remote verification — verify before PR" (BR-3). Never block.
     ```
     `adlc_alloc_id bug` handles the absent-counter bootstrap scan internally (highest `BUG-xxx` under `$ADLC_REPOS_ROOT`; bug reports are `.md` files so the scan uses `-type f`), the `mkdir` lock that serializes concurrent sessions, and the remote high-water max. Single-machine behavior is unchanged when the remote has no higher allocation (BR-7).
     Note: the legacy per-repo `.adlc/.next-bug` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.
   - **Pre-push recheck (BR-4, BR-8).** Before the bug file is committed on a branch for push, re-verify `BUG-<id>` against the remote — a colleague on another machine may have pushed the same id since allocation. Source `partials/id-recheck.sh` and call `adlc_recheck_id` **in the same fenced block**; a collision halts with the renumber instruction rather than pushing a duplicate:
     ```bash
     . .adlc/partials/id-recheck.sh 2>/dev/null || . ~/.claude/skills/partials/id-recheck.sh
     BUG_ID=$(printf 'BUG-%03d' "$BUG_NUM")
     if ! adlc_recheck_id bug "$BUG_ID"; then
       echo "Halting: $BUG_ID collides on the remote — renumber before pushing (see message above)." >&2
       exit 1
     fi
     ```
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
3. Update the bug report (do NOT mark `resolved` yet — that happens in Phase 6 after the fix is merged and deployed):
   - Leave status as `open` (or set to `in-review` if your project uses that value)
   - Fill in "Resolution" section with what was changed and why
   - Fill in "Files Changed" section with specific file paths
   - Update the `updated` date
4. Present an interim summary:
   - Root cause
   - What was fixed
   - Files changed
   - Test results
   - Then continue to Phase 5

### Phase 5: Ship — Create Pull Request(s)

For each touched repo (just the current repo in single-repo mode; each entry in `touched_repos:` in cross-repo mode):

1. Push the fix branch: `git -C <worktree> push -u origin fix/bug-xxx-slug`
2. Create the PR with `adlc_forge_pr_create` (source `partials/forge.sh` in the same fence; run from inside the worktree, or pass `-R <owner/repo>`). All PR ops route through the forge adapter, never direct `gh` (REQ-520 BR-1). In cross-repo mode, create the **primary** repo's PR **last** so its body can link every sibling.
   - **Title**: `fix(BUG-xxx): short description` — when cross-repo, scope to the repo (e.g., `fix(api): null deref in user serializer [BUG-042]`).
   - **Body**:
     ```
     ## Summary
     [1-2 lines describing what broke and what was fixed in THIS repo]

     ## Bug
     BUG-xxx: [bug title]
     Severity: [critical | high | medium | low]
     Primary repo: <primary-repo-id>

     ## Root Cause
     [Pulled from the bug report's Root Cause section]

     ## Files Changed (this repo)
     - `path/to/file.ts` — what changed and why

     ## Related PRs (cross-repo)
     [Omit in single-repo mode. Otherwise list each sibling PR URL — back-fill
      sibling bodies via `adlc_forge_pr_edit` once every URL is known.]

     ## Test Plan
     - [ ] Unit/integration tests pass locally
     - [ ] CI green on this PR
     - [ ] Staging deploy succeeded (verified in Phase 6)
     - [ ] Production deploy succeeded (verified in Phase 6)
     ```
3. After all sibling PRs exist, edit each one (`adlc_forge_pr_edit <prUrl> --body ...`) to fill in the Related PRs section.
4. Wait for CI to pass on every PR: `gh pr checks <prUrl>`. If CI fails, diagnose and re-push — never bypass with `--no-verify` or admin-merge.
5. Report all PR URLs to the user, grouped by repo.

### Phase 6: Wrapup — Merge, Deploy, Knowledge Capture

This is the equivalent of `/proceed`'s Phase 8 / `/wrapup` steps, condensed for bugs.

**Step 1 — Merge each PR.**
1. Verify the PR is mergeable: `adlc_forge_pr_view <prUrl> --json mergeable,mergeStateStatus` should report `MERGEABLE` (on GitHub; ADO normalizes via `pr_view`). If main has advanced, rebase the fix branch onto `origin/main`, force-push with lease, and wait for CI to re-pass.
2. Merge with squash + branch delete: `adlc_forge_pr_merge <prUrl> --squash --delete-branch`. In cross-repo mode, walk `touched_repos:` order (or `merge_order:` from `.adlc/config.yml` if not specified on the bug).

**Step 2 — Confirm deploys** (this is the staging-first gate when the project has one — same model as features).

Skip this step entirely if the project doesn't deploy via Cloud Run (i.e., `stack.backends` in `.adlc/config.yml` doesn't include `cloud-run` and there's no `gcp:` block).

Otherwise, for each touched service that has a `services:` entry in `.adlc/config.yml`, look up `gcp.staging_project` and `gcp.production_project` from the config and confirm both:

```bash
# Staging
gcloud run services describe <service> \
  --project=<gcp.staging_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"

# Production
gcloud run services describe <service> \
  --project=<gcp.production_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"
```

Confirm the merge SHA's revision is serving 100% traffic in each. If `gcp.production_project` is omitted (no separate prod project), only confirm staging.

If staging deployed but production has NOT yet been promoted, wait — the pipeline runs them sequentially. If either fails, surface to the user with the failed deploy log link before claiming the bug resolved.

**iOS deploy** (only when `stack.frontends` in `.adlc/config.yml` includes `ios` AND the fix touched the iOS repo):
1. Read `ios.deploy_targets`, `ios.derived_data_clean`, and `ios.deploy_command` from `.adlc/config.yml`.
2. If `ios.derived_data_clean` is true: `rm -rf ~/Library/Developer/Xcode/DerivedData/*`
3. From the iOS repo's worktree, run `<ios.deploy_command>` and deploy to **every** device in `ios.deploy_targets` — never skip one. Don't leave this as a follow-up for the user.

If `stack.frontends` doesn't include `ios`, skip this section entirely.

**Step 3 — Update the bug report.**
- Set status to `resolved`
- Update the `updated` date
- Confirm Resolution and Files Changed sections are filled in (from Phase 4)
- Add a Deployment section noting the staging + production revisions

**Step 4 — Capture knowledge** (NEVER skip — per memory `feedback_wrapup_knowledge_capture.md`).

Evaluate honestly: did this bug reveal something a future implementer should know?
- A surprising failure mode (race condition, schema mismatch, mocked-vs-real divergence, etc.)?
- A pattern or anti-pattern worth recording?
- A check that would have caught this earlier?
- An assumption from a prior REQ that turned out false?

If yes, write a lesson to `.adlc/knowledge/lessons/LESSON-xxx-slug.md` using the **global** atomic counter `~/.claude/.global-next-lesson` (shared across all repos for unique IDs, mirroring the REQ/BUG counters — see LESSON-004). The counter is now a **cache, not the authority** — the remote is the source of truth (REQ-518): allocation derives the remote high-water, takes `max(remote, local) + 1`, and fast-forwards the local counter, all inside the shared `mkdir`-lock (`~/.claude/.global-next-lesson.lock.d`, shared with `/wrapup` so concurrent `/bugfix` and `/wrapup` runs mutually exclude). Allocate via the shared `partials/id-alloc.sh` helper (BR-5 — the lock block + its LESSON-014 symlink pre-check live in the partial). Source it and call `adlc_alloc_id` **in the same fenced block** (the cross-fence-fn rule — see conventions.md "Bash in skills"):
```bash
. .adlc/partials/id-alloc.sh 2>/dev/null || . ~/.claude/skills/partials/id-alloc.sh
LESSON_NUM=$(adlc_alloc_id lesson)
# `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — LESSON_NUM
# would be silently empty. Guard the parent context (REQ-416 verify D-pass).
[ -n "$LESSON_NUM" ] || { echo "ERROR: failed to allocate LESSON number — aborting before writing malformed lesson" >&2; exit 1; }
```
`adlc_alloc_id lesson` handles the absent-counter bootstrap scan internally (highest `LESSON-xxx` under `$ADLC_REPOS_ROOT`; lessons are `.md` files so the scan uses `-type f`), the shared `mkdir` lock, and the remote high-water max. Single-machine behavior is unchanged when the remote has no higher allocation (BR-7). Note: the legacy per-repo `.adlc/.next-lesson` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.

**Pre-push recheck (BR-4, BR-8).** Before the lesson file is committed on a branch for push, re-verify `LESSON-<id>` against the remote — a colleague on another machine may have pushed the same id since allocation. Source `partials/id-recheck.sh` and call `adlc_recheck_id` **in the same fenced block**; a collision halts with the renumber instruction rather than pushing a duplicate:
```bash
. .adlc/partials/id-recheck.sh 2>/dev/null || . ~/.claude/skills/partials/id-recheck.sh
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote — renumber before pushing (see message above)." >&2
  exit 1
fi
```

Use the lesson template (`.adlc/templates/lesson-template.md`, fall back to `~/.claude/skills/templates/lesson-template.md`). Filename format is `LESSON-xxx-slug.md` only — no date prefixes, no bare-numeric prefixes. Include `domain`, `component`, and `tags` so future runs of `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance.

If the bug genuinely produced no useful lesson (one-line typo, etc.), say so explicitly in the final summary — don't silently skip.

**Step 5 — Clean up.**
1. Switch the local checkout to main and pull: `git -C <main-worktree> checkout main && git -C <main-worktree> pull`
2. If the fix was done in a separate worktree, remove it: `git -C <main-worktree> worktree remove <fix-worktree-path>`
3. If the fix branch still exists locally after squash-merge, delete it: `git branch -D fix/bug-xxx-slug`
4. Prune remote-tracking refs: `git fetch --prune`

**Step 6 — Final ship summary.**

```
## BUG-xxx: Bug Title — Resolved

**Severity**: <severity>
**PR(s)**: #nn (and siblings if cross-repo)
**Merged**: YYYY-MM-DD

### Root cause
- 1-2 lines

### Fix
- 1-2 lines

### Deployment
- Staging: <service> revision <hash> @ 100% traffic
- Production: <service> revision <hash> @ 100% traffic
- iOS: deployed to <list of ios.deploy_targets from config> (or "n/a — backend-only fix")

### Lessons captured
- `.adlc/knowledge/lessons/LESSON-xxx-slug.md` — one-line hook
  (or "None — fix was straightforward and revealed no new pattern")
```

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
- Phase 5 opens one PR per touched repo and cross-links them (primary PR's body is created last so it can reference every sibling URL).
- Phase 6 merges in the order the repos are listed in `touched_repos:`. If the bug report doesn't specify an order, use the `merge_order` from `.adlc/config.yml`.
- If this gets complicated (more than 2 touched repos, or ordering matters), consider promoting the bug into a full REQ and using `/proceed` instead.
