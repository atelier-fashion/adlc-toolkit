---
parent: proceed
phases: "6-8"
---

# /proceed — Phases 6–8: Ship

Companion to `proceed/SKILL.md`. These three phases package verified work
into PRs (one per touched repo), sanity-check each PR, then merge in
configured order, deploy, and capture knowledge via `/wrapup`. SKILL.md
keeps a one-paragraph summary of each; the per-step PR body templates,
merge sequencing, and terminal-state contract live here.

---

### Phase 6: Create Pull Request(s)

**Gate**: `currentPhase` must be `6`. After completion: append `6`, set `currentPhase=7`.

**Goal**: Package the work into reviewable PRs — one PR per touched repo.

1. For each touched repo:
   - Inside that repo's worktree, ensure all changes are committed and push the feature branch: `git -C <worktree> push -u origin feat/REQ-xxx-short-description`
2. Set the requirement status to `complete` in its frontmatter (primary repo only).
3. **Flip each touched repo's draft PR (opened at Step 0, step 8a) to ready** with `gh pr ready <prNumber>` (read `prNumber`/`prUrl` from `pipeline-state.json`) — do **NOT** create a new PR (REQ-483 BR-2). **Fallback (LESSON-004):** if `prNumber` is absent (a pipeline started before draft-PR-early), `gh pr create --base <integrationBranch>` instead (never default base to `main`). Then set the full body **preserving the `adlc-footprint` block** `/architect` published — read the current body, extract the fenced footprint block, and re-append it to the new body, and drop the Step-0 `[WIP]` title prefix:
   ```sh
   tick=$(printf '\140\140\140')
   tmp=$(mktemp "${TMPDIR:-/tmp}/prbody.XXXXXX"); trap 'rm -f "$tmp"' EXIT
   fp=$(gh pr view "$prNumber" --json body -q .body 2>/dev/null | sed -n "/^${tick}adlc-footprint/,/^${tick}/{ /^${tick}/d; p; }")
   { printf '%s\n' "$NEW_BODY"; [ -n "$fp" ] && printf '\n%sadlc-footprint\n%s\n%s\n' "$tick" "$fp" "$tick"; } > "$tmp"
   gh pr edit "$prNumber" --body-file "$tmp" --title "$FINAL_TITLE"
   ```
   `$NEW_BODY` is the template below; `$FINAL_TITLE` drops the `[WIP]` prefix. In cross-repo mode, ready the primary repo's PR **last** so its body can link to all sibling PRs.
   - **Title (per repo)**: Short description referencing the REQ, tagged with the repo id when cross-repo (e.g., `feat(api): new endpoint [REQ-023]`).
   - **Body (per repo)**:
     ```
     ## Summary
     [2-3 bullet points describing what was built in THIS repo]

     ## Requirement
     REQ-xxx: [requirement title]
     Primary repo: <primary-repo-id>

     ## Related PRs (cross-repo)
     [Populated for siblings and also in the primary once its PR is created last.
      Omit entirely in single-repo mode.]
     - api: <url>
     - web: <url>

     ## Tasks Completed (this repo)
     - [x] TASK-001: [title]
     - [x] TASK-002: [title]

     ## Architecture Decisions
     [Key ADRs or "No architectural changes needed"]

     ## Test Coverage
     [Summary of tests added/modified in THIS repo]

     ## Reflection Notes
     [Key observations from the reflect phase — risks, assumptions, follow-ups]

     ## Merge Order
     [Only when cross-repo. List the mergeOrder from pipeline-state.json so
      reviewers know which PR merges first.]
     ```
4. The PR URL was recorded at Step 0 (step 8a); confirm `repos[<id>].prUrl` is set (record it now only if absent — old-format state).
5. After the last PR is **readied**, go back and edit sibling PRs' bodies (`gh pr edit`) to add the cross-repo "Related PRs" section now that every URL is known (preserve each PR's `adlc-footprint` block as in step 3).
6. Report all PR URLs to the user, grouped by repo and in `mergeOrder` sequence.

---

### Phase 7: PR Cleanup & CI

**Gate**: `currentPhase` must be `7`. After completion: append `7`, set `currentPhase=8`.

**Goal**: Lightweight sanity check on each PR — the full code review already happened in Phase 5. Do NOT re-run `/review`.

Do all the steps below **for every touched repo's PR**:

1. Review the full PR diff using `gh pr diff <prUrl>` (use the URL stored in `repos[<id>].prUrl`).
2. Check for:
   - Stray debug logs, TODOs, or commented-out code
   - Files that shouldn't have been included (secrets, generated files, unrelated changes)
   - Commit message consistency and cleanliness
   - That the PR description accurately reflects the changes
   - Cross-repo consistency: if a sibling PR changes an API contract, verify this PR's corresponding consumer/producer code matches
3. If issues are found:
   - Fix inside the owning repo's worktree, commit with message: `fix(scope): PR cleanup [REQ-xxx]`
   - Push that worktree's branch: `git -C <worktree> push`
4. If CI checks are configured, verify each PR passes: `gh pr checks <prUrl>`. Wait for in-flight checks before moving on.

**End-of-phase log**: Emit one line per PR — "<repo-id>: clean, CI green" — followed by an aggregate "All N PRs ready for merge" or list any remaining concerns. Continue to Phase 8 immediately.

---

### Phase 8: Wrapup

**Gate**: `currentPhase` must be `8` and `7` must be in `completedPhases`. After completion: append `8`, set `"completed": true`.

**Goal**: Merge, deploy, capture knowledge, and close out the feature.

**Completion claim** (terminal state contract): the run's final report MUST lead with **exactly one** tag from `{merged, pr-ready, blocked, failed}`:

| Tag | Required preconditions |
|---|---|
| `merged` | All touched-repo PRs are `MERGED` (verifiable via `gh pr view --json state,mergedAt`). `repos[<id>].merged == true` for every touched repo. |
| `pr-ready` | All touched-repo PRs are `OPEN`, `MERGEABLE`, all required CI green. Used in cross-repo mode when the orchestrator owns merge sequencing, or in single-repo mode when the run is explicitly told not to merge. |
| `blocked` | Blocker requires human input. `pipeline-state.json.blockers` populated. |
| `failed` | Pipeline failed past automatic recovery. Failure details in `pipeline-state.json.notes`. |

A vague "Pipeline complete" claim without one of these tags is a protocol violation. When dispatched by `/sprint`, the orchestrator will reject untagged claims and treat them as `blocked`.

**Pre-merge trial-merge gate (REQ-483, BR-9/BR-16 — authoritative).** Before merging, first **`git -C <repos[<id>].worktree> fetch origin <integrationBranch>`** — the gate MUST test the *current* tip; a stale local ref gives a false pass (LESSON-036). Then source `partials/trial-merge.sh` and run `adlc_trial_merge "<repos[<id>].worktree>" origin/<integrationBranch>`, branching on the return code: **rc=1** (real conflict, files on stdout) → do NOT merge: return the `blocked` terminal, populate `pipeline-state.json.blockers` with `{blockedBy, conflictFiles, unblockCondition}` ("resume after <blocker> merges, then rebase") — legitimate halt #3. **rc=0** → proceed to the merge below. **rc=2/3** (uncommitted worktree / unfetched-or-bad ref) → surface as `failed`, NOT `blocked` (it is a setup error, not a conflict). A footprint overlap alone never blocks — only rc=1 does (resolution is rebase, never a "merge anyway" — ethos #6).

**`blockers` entry shape (REQ-485 additions).** The entry written on rc=1 carries, beyond `{blockedBy, conflictFiles, unblockCondition}`, three fields the `/sprint` orchestrator's auto-rebase/resume pass reads and updates: `holdState` (`held` \| `rebasing` \| `resumed` \| `re-halted` \| `needs-manual-rebase`), `rebaseAttempts` (capped at the retry bound — default 1, config `auto_rebase_max_attempts`), and `resolvedBlocker` (the now-merged blocker id after a post-merge materialized conflict). On a rc=1 halt set `holdState: "held"` and `rebaseAttempts: 0`. See `agents/pipeline-runner.md` "Blocker Handling" for the full table.

**Clear-on-resolve (REQ-485 BR-11).** When this merge is the resume of a previously-held REQ (the orchestrator auto-rebased it cleanly after its blocker merged), the same write that sets `repos[<id>].merged = true` MUST also **clear this REQ's `blockers` entry** (transition `holdState` to `resumed`, then remove the entry). Setting `merged = true` and clearing `blockers` are distinct writes; historically only the former was done. The clear is the idempotency anchor for the unblock pass (it considers ONLY REQs whose `blockers` entry is still present), so a later blocker-merged event does not re-process an already-merged REQ.

**Topology-driven merge actor**:
- **Single-repo REQ** (one touched repo): the pipeline owns the merge in this phase. Run `gh pr merge <prUrl> --squash --delete-branch` from the parent repo path (`repos[<id>].path`), NOT from the worktree. Terminal claim is `merged`.
- **Cross-repo REQ** (multiple touched repos): use the cross-repo merge sequencing block below. Terminal claim is `merged` after all repos land, or `pr-ready` if dispatched by an orchestrator that owns merge sequencing.

**Cross-repo merge sequencing**:

1. Walk `mergeOrder` from `pipeline-state.json`. For each repo id in order:
   - Skip if `repos[<id>].merged == true` (already merged — recovering from an interrupted run).
   - Merge that repo's PR (`gh pr merge <prUrl> --squash` or the project's configured merge strategy).
   - Wait for the merge to land, then set `repos[<id>].merged = true` in state.
   - If the next repo's PR was opened against `main` and depends on the just-merged changes being present, trigger a rebase/retarget before merging it. When siblings were developed in parallel worktrees against the same pre-REQ main, this is usually a no-op — but surface any auto-merge failure to the user as a conflict halt (legitimate halt #3).
2. After all PRs are merged, run `/wrapup` with the REQ ID from the primary repo. In cross-repo mode, pass the list of touched repos so `/wrapup` can:
   - Update ADLC artifacts (spec, decisions, knowledge) in the primary
   - Trigger deploys for each deployable touched repo
   - Emit a ship summary spanning all repos
3. Remove the worktree in each touched repo using the absolute path from state: `git -C <repo-path> worktree remove <repos[<id>].worktree>`. Do NOT use the relative `.worktrees/REQ-xxx` form here.
4. Update `pipeline-state.json` with `"completed": true`.
5. The pipeline is now complete.

**End-of-phase log**: Emit the ship summary from wrapup including per-repo merge confirmations and deployment status. Pipeline complete.
