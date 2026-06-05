---
id: TASK-002
title: "Legacy /sprint Step 5 post-merge unblock pass (auto-rebase + resume)"
status: draft
parent: REQ-485
created: 2026-06-05
updated: 2026-06-05
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Add the auto-rebase/resume trigger to the LEGACY `/sprint` engine's merge
sequencing (Step 5 in `sprint/SKILL.md`). Immediately after the orchestrator
merges REQ-A (and writes `repos[A].merged = true`), run an **unblock pass** for
every held BlockHold with `blockedBy == A`:

1. `git -C <held-worktree> fetch origin <integrationBranch>` then
   `git -C <held-worktree> rebase origin/<integrationBranch>` (BR-2).
2. **Clean** → auto-resume the held REQ from its recorded `currentPhase` by
   re-dispatching a fresh `pipeline-runner` (which re-runs the now-passing
   trial-merge gate at Phase 8 and proceeds to merge) (BR-3). Where the legacy
   engine cannot cleanly re-dispatch-from-phase, degrade to surface-to-human
   (BR-7, OQ-1 default).
3. **Conflict** → `git -C <held-worktree> rebase --abort` (non-mutating),
   increment `rebaseAttempts`; if under the retry bound re-halt `held`; if at the
   bound mark `needs-manual-rebase` and surface for human resolution. Never
   auto-resolve / force / merge-anyway (BR-4, BR-10, ethos #6).
4. Mutate ONLY the held REQ's own worktree/branch (BR-5).
5. Multiple REQs blocked on the same blocker unblock in REQ-483's deterministic
   order (earliest-published PR, lower REQ tiebreak), processed ONE AT A TIME
   (serialized) (BR-6).
6. **OQ-5 / ADR-8**: when REQ-A ends `failed`/abandoned within the run, release
   every REQ held SOLELY on A (run the same rebase+resume path treating the dead
   blocker as cleared); a REQ with other live blockers stays held.

## Files to Create/Modify

- `sprint/SKILL.md` — Step 5 (Handle Merge Sequencing): add the post-merge unblock pass + Step 4.6/terminal-handling blocker-failed release

## Acceptance Criteria

- [ ] After the orchestrator merges REQ-A in legacy Step 5, the skill runs an unblock pass over held REQs with `blockedBy == A` (BR-2).
- [ ] A clean rebase auto-resumes the held REQ by re-dispatching a pipeline-runner from its recorded `currentPhase`; no human input on the happy path (BR-3).
- [ ] A conflicting rebase aborts (worktree unchanged), re-halts with materialized conflict files, and surfaces a human-resolution prompt; nothing is force-merged (BR-4).
- [ ] The unblock pass mutates only the held REQ's own worktree/branch — never the blocker's or any third REQ's (BR-5).
- [ ] Multiple REQs on one blocker unblock in deterministic order, serialized one at a time (BR-6).
- [ ] A held REQ with a torn-down worktree or missing `currentPhase` is skipped with a "manual resume needed for REQ-x" advisory, not an error or batch crash (BR-7).
- [ ] A persistently-conflicting rebase stops after the retry bound (default 1, config-overridable) and surfaces for manual handling — no infinite loop (BR-10).
- [ ] When a sole blocker ends `failed`/abandoned, the solely-dependent held REQ is released and re-attempted (OQ-5 / ADR-8).
- [ ] Any added bash is split-free and POSIX/zsh-safe (LESSON-329): held REQs iterated over newlines via `printf '%s\n' | while read -r`, every path quoted, `git -C <worktree>` form (no cwd inference).

## Technical Notes

- Retry bound default 1, overridable via `.adlc/config.yml` key
  `auto_rebase_max_attempts` (OQ-3 default). Read it degrade-safe (missing → 1).
- The unblock pass is deterministic + idempotent: with nothing newly merged it is
  a no-op; it considers ONLY REQs whose `blockers` entry is still present
  (the BR-11 anchor from TASK-001).
- Worktree path comes from `repos[<held-id>].worktree` in the held REQ's
  `pipeline-state.json` — never re-derived.
- Express the rebase loop as prose + a minimal fenced bash example consistent with
  REQ-483's trial-merge gate style; keep it auditable and split-free.
