---
id: TASK-073
title: "Wire the trial-merge hard gate + verdict into /proceed, /sprint, pipeline-runner (BR-7,9,10,16)"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-069, TASK-070, TASK-072]
---

## Description

Connect the pieces into actual enforcement: the trial-merge gate (TASK-069) plus the deterministic verdict (TASK-072) drive a `/proceed` halt and `/sprint` merge serialization. Footprint overlap remains advisory; only a real trial-merge conflict blocks.

## Files to Create/Modify

- `proceed/SKILL.md` — Phase 3→4: precise trial-merge gate (advisory footprint already shown at Step 0)
- `proceed/phases-6-8-ship.md` — Phase 8: pre-merge trial-merge gate
- `sprint/SKILL.md` — Step 5: deterministic merge order + per-merge trial-merge gate (serialize merges, not implementation)
- `agents/pipeline-runner.md` — Phase 8 single-repo merge: trial-merge gate

## Acceptance Criteria

- [ ] `/proceed` sources `partials/trial-merge.sh` and runs `adlc_trial_merge <worktree> origin/<integrationBranch>` at the Phase 3→4 boundary (early) and again pre-merge in Phase 8. A **real conflict** with work ahead (per the TASK-072 verdict) returns the `blocked` terminal (NOT a throw) naming the conflicting REQ, conflicting files, and unblock condition ("resume after REQ-A merges, then rebase"). (BR-9)
- [ ] A footprint overlap that trial-merges **cleanly** does NOT halt — it is shown as advisory and the pipeline continues. (BR-7)
- [ ] `/sprint` Step 5 walks the deterministic merge order (TASK-072 verdict) and gates each merge with `adlc_trial_merge`; a real conflict halts the later REQ (`blocked`) for rebase; clean overlaps merge with no intervention. REQs run in parallel; only **merges** serialize. Sequencing computed in orchestrator/script code, not by an agent. (BR-10)
- [ ] `agents/pipeline-runner.md` Phase 8 runs the same trial-merge gate before a single-repo merge.
- [ ] The `blocked` terminal is the existing one (REQ-474 contract); `pipeline-state.json.blockers` is populated `{blockedBy, conflictFiles, unblockCondition}`.
- [ ] No "merge anyway" path that would land a conflicted tree (ethos #6); resolution is rebase via resume. (BR-12)
- [ ] `python3 tools/lint-skills/check.py` passes across all four files; the sourced `adlc_trial_merge` is invoked within the same fenced block it is sourced in (no cross-fence-fn); sh/zsh-portable.

## Technical Notes

- Source the partial with the two-level fallback in the SAME fence as the call.
- `/proceed`'s Phase 3→4 early gate is best-effort (an overlapping branch may not have code yet → trial-merge clean); the Phase 8 pre-merge gate against the updated integration tip is the authoritative one (OQ-7 default: integration-tip).
- Reuse the `mergeOrder` walk pattern (phases-6-8-ship.md Phase 8) for the per-merge gate.
- This is the security-sensitive + delicate task (changes blocking behavior) — keep halts as returned terminals, never thrown.
