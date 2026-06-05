---
id: REQ-485
title: "Auto-rebase and resume a blocked REQ after its blocker merges (/sprint self-healing serialization)"
status: complete
deployable: true
created: 2026-06-05
updated: 2026-06-05
component: "adlc/sprint"
domain: "adlc"
stack: ["bash", "markdown", "claude-skills"]
concerns: ["concurrency", "coordination", "orchestration"]
tags: ["auto-rebase", "auto-resume", "blocked", "serialize", "ordering", "trial-merge", "multi-human", "self-healing"]
---

## Description

REQ-483's enforcement halts a REQ with a `blocked` terminal when its pre-merge trial-merge against an ahead REQ reports a real conflict (rc=1). Today the held REQ is **surfaced to a human** (sprint/SKILL.md L216: "hold that REQ — `blocked`, surfaced for rebase"); a person must wait for the blocker to merge, rebase the held branch, and resume the pipeline. For interactive `/proceed` that is appropriate — the human is present. For unattended `/sprint` batches it is a gap: a blocked REQ sits idle until a human nudges it, partially defeating "launch a batch and walk away."

This REQ makes a `/sprint` batch **self-heal**: after the orchestrator merges REQ-A, it automatically rebases any REQ held with `blockedBy == A` onto the refreshed integration branch and resumes it. A **clean** rebase resumes the held REQ from its recorded `currentPhase` (re-running the now-passing trial-merge gate, which proceeds to merge); a **conflicting** rebase aborts (non-mutating), re-halts the REQ with the now-materialized conflict files, and surfaces it for human resolution — never auto-resolving.

The machinery already exists and is being **composed, not invented**: workflow `resumeFromRunId` (sprint L78–90), the `/wrapup` Step 2 rebase-onto-main guard (sprint L236), and `pipeline-state.json.blockers.{blockedBy, conflictFiles, unblockCondition}` + `currentPhase` (phases-6-8-ship L114, proceed L161). The missing piece is the **automatic trigger**: blocker-merged → rebase-held-REQ → resume, in place of parking the held REQ for a human.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| BlockHold | req | string | the held REQ |
| BlockHold | blockedBy | string | the REQ it waits on (from `pipeline-state.blockers`) |
| BlockHold | resumePhase | int | the `currentPhase` to resume from (from `pipeline-state`) |
| BlockHold | conflictFiles | list[string] | files reported by the original trial-merge rc=1 |
| BlockHold | state | enum | `held` \| `rebasing` \| `resumed` \| `re-halted` |

### Events

| Event | Trigger | Effect |
|-------|---------|--------|
| blocker-merged | orchestrator merges REQ-A | trigger an unblock attempt for every BlockHold with `blockedBy == A` |
| rebase-clean | `git rebase origin/<integ>` succeeds in held worktree | auto-resume the held REQ from `resumePhase` |
| rebase-conflict | the rebase fails | `git rebase --abort`; re-halt `blocked` with materialized conflicts; surface to human |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Auto-rebase a held REQ's OWN branch/worktree | the `/sprint` orchestrator |
| Mutate the blocker's or any third REQ's branch | **none** |
| Auto-RESOLVE a rebase conflict | **none** (human only) |

## Business Rules

- [ ] BR-1: Auto-rebase/resume lives in the `/sprint` orchestrator only. Solo `/proceed` (not under `/sprint`) keeps today's manual-resume behavior — the human is present. (informed by REQ-483 BR-3; sprint/SKILL.md L216)
- [ ] BR-2: Immediately after the orchestrator merges REQ-A, for EACH REQ currently held with `blockedBy == A` (read from `pipeline-state.json.blockers`), `/sprint` MUST `git -C <held-worktree> fetch origin <integrationBranch>` then attempt `git rebase origin/<integrationBranch>` in the held REQ's worktree. (informed by REQ-483 trial-merge gate; sprint L216, L236)
- [ ] BR-3: A CLEAN rebase MUST auto-resume the held REQ from its recorded `currentPhase` — workflow engine: relaunch `resumeFromRunId` with an orchestrator "blocker-cleared" signal; legacy engine: re-dispatch the pipeline-runner — which re-runs the now-passing trial-merge gate and proceeds to merge. (informed by sprint L78–90 `resumeFromRunId`, proceed L161 resume-from-`currentPhase`)
- [ ] BR-4: A CONFLICTING rebase MUST `git rebase --abort` (leaving the worktree unchanged), re-halt the REQ with the `blocked` terminal carrying the NOW-materialized conflict files, and surface it for human resolution. It MUST NOT auto-resolve, force, or "merge anyway." (informed by REQ-483 trial-merge philosophy; ethos #6)
- [ ] BR-5: Auto-rebase MUST mutate ONLY the held REQ's own branch/worktree. It MUST NOT touch the blocker's branch/PR or any other REQ's worktree. (informed by REQ-483 permissions — ordering is derived, never asserted by mutation)
- [ ] BR-6: The unblock pass MUST be deterministic and idempotent: with nothing newly merged it is a no-op; when multiple REQs are blocked on the same blocker they unblock in REQ-483's deterministic order (earliest-published PR, lower REQ tiebreak) and are processed ONE AT A TIME (serialized), since the held REQs may themselves overlap. (informed by REQ-483 BR-8 ordering)
- [ ] BR-7: Degrade-safe: a held REQ whose `currentPhase` is unrecorded, or whose worktree has been torn down, MUST be skipped with a "manual resume needed for REQ-x" advisory — never an error or a crash of the batch. (informed by REQ-483 degrade-safe; REQ-482 advisory-never-block)
- [ ] BR-8: The auto-resume trigger MUST be distinguishable from a user-answer resume. The workflow resume contract (today keyed on `args.answers[<REQ-id>]`) MUST be extended so an orchestrator-generated "blocker-cleared" signal can drive the resume of a merge-blocked REQ; the held pipeline-runner does NOT self-resume (it already reported `blocked` and exited). (informed by sprint L78–90; agents/pipeline-runner L111)
- [ ] BR-9 (scope guard): v1 auto-resumes ONLY when THIS `/sprint` run merged the blocker. A blocker merged by a DIFFERENT session (cross-session) stays manual — no cross-session watch/poll in v1. (informed by REQ-482 cross-session-visibility scope; sprint L172 no-timer-poll)
- [ ] BR-10: A retry bound MUST prevent an auto-rebase loop: if a held REQ's rebase conflicts across the configured max attempts, stop auto-retrying and surface for manual resolution. (informed by ethos #6 — don't paper over a persistent conflict)
- [ ] BR-11: On a successful resume that reaches merge, the orchestrator MUST transition the BlockHold to `resumed` (terminal) and clear the REQ's `pipeline-state.json.blockers` entry, so subsequent blocker-merged events do not re-process an already-merged REQ. The unblock pass (BR-2) considers ONLY REQs whose `blockers` entry is still present — this is the idempotency anchor for BR-6. (Today the code sets `repos[<id>].merged = true` but never clears `blockers`; this REQ adds the clear.) (informed by REQ-483 blockers schema; ethos #4 — verify state transitions)

## Acceptance Criteria

- [ ] In a `/sprint` batch where REQ-B is held behind REQ-A, merging REQ-A automatically rebases REQ-B; a clean rebase resumes REQ-B and it proceeds to merge with no human input.
- [ ] A conflicting rebase aborts (worktree unchanged), re-halts REQ-B with the materialized conflict files, and surfaces a human-resolution prompt; nothing is force-merged.
- [ ] Solo `/proceed` (not under `/sprint`) is unchanged — manual resume.
- [ ] Multiple REQs blocked on one blocker unblock in REQ-483's deterministic order, serialized one at a time.
- [ ] Auto-rebase never modifies the blocker's branch or any third REQ's worktree (verified).
- [ ] A held REQ with a torn-down worktree or missing `currentPhase` degrades to an advisory, not an error.
- [ ] A persistently-conflicting rebase stops after the retry bound and surfaces for manual handling (no infinite loop).

## External Dependencies

- None (uses `git rebase`, `gh`, and the existing sprint resume + `/wrapup`-rebase machinery).

## Assumptions

- The workflow engine supports resuming a halted REQ from its recorded phase via `resumeFromRunId` (confirmed: sprint L78–90), and `pipeline-state.json` carries `currentPhase` + `blockers.{blockedBy, conflictFiles, unblockCondition}` (confirmed: proceed L161, phases-6-8 L114).
- The orchestrator merges blockers itself within a run, so "blocker-merged" is a known local event, not something to poll for (confirmed: sprint L214–237).

## Open Questions

- [ ] OQ-1: Does the LEGACY (non-workflow) `/sprint` engine have a re-dispatch-from-phase path equivalent to `resumeFromRunId`? If not, v1 auto-resume is workflow-engine-only and the legacy engine degrades to today's surface-to-human (BR-7). (Default: workflow-engine first; legacy degrades.)
- [ ] OQ-2: Resume granularity — resume from `currentPhase` wholesale, or a fast path that re-runs only the Phase-8 gate+merge when the halt was at the pre-merge gate (the common case per REQ-483)? (Default: resume from `currentPhase`; optimize later.)
- [ ] OQ-3: Retry-bound default for BR-10 (max conflicting-rebase attempts before manual) — 1? Configurable via `.adlc/config.yml`? (Default: 1, config-overridable.)
- [ ] OQ-4: Cross-session blocker auto-resume (a different human's session merges the blocker) — confirmed OUT of scope for v1 (BR-9)?
- [ ] OQ-5: If a blocker ends `failed`/abandoned **within the run** (its PR will never merge — `failed` is a real terminal, sprint/SKILL.md L68), what happens to a REQ held solely on it? No merge event will ever fire BR-2, so it would sit `blocked` silently to batch-end. Its ordering constraint has dissolved, so the sensible default is **release + re-attempt** (a REQ with *other* live blockers stays held). This is the in-run analogue of REQ-483's cross-session stale-PR safety (BR-11). (Default: release solely-dependent held REQs on blocker failure; confirm vs. surface-for-manual.)
- [ ] OQ-6: After a conflicting rebase whose blocker has **already merged** (BR-4 re-halt), the REQ needs **manual conflict resolution** — semantically distinct from "waiting for a blocker to merge." How should `blockedBy` read in that state (a `manual`/`self` sentinel vs. the now-merged blocker id), and what counts as an "attempt" for BR-10's retry bound (per blocker-merged event vs. per unblock pass)? (Default: mark `needs-manual-rebase`, not auto-re-triggered by future merges; BR-10 counts attempts per blocker-merged event.)

## Out of Scope

- Auto-RESOLVING rebase conflicts (a real conflict is always human-resolved).
- Cross-session auto-resume (when another session merges the blocker) — v1 is within-`/sprint`-run only.
- Solo `/proceed` auto-resume (stays manual).
- Cross-repo footprint publishing (REQ-484, the sibling follow-up).

## Retrieved Context

_Retrieved in-context this session (REQ-482/REQ-483 initiative); not re-delegated to Kimi — the matched corpus was already fully loaded and is architectural-decision material._

- REQ-483 (spec, score ~12): ordering enforcement — blocked terminal, `blockers` field, trial-merge, deterministic order (direct parent)
- REQ-482 (spec, score ~7): `/manifest` — the deterministic order this auto-resume serializes on
- LESSON-330 (lesson, score ~3): Phase-5 review catches omitted requirements — informs BR completeness
- LESSON-329 (lesson, score ~3): dogfood under the executor shell — informs the rebase/resume dogfood
