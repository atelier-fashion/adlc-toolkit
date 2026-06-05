---
id: TASK-003
title: "Workflow engine blocker-cleared resume contract + unblock pass"
status: draft
parent: REQ-485
created: 2026-06-05
updated: 2026-06-05
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Extend the WORKFLOW engine (the primary engine per OQ-1 default) so a
merge-blocked REQ can be auto-resumed by an orchestrator-generated
**`blocker-cleared`** signal — distinguishable from a user-answer resume (BR-8).

Two edits:
1. **`sprint/SKILL.md`** Step 0 (workflow-engine resume contract, L78–90): extend
   the resume description so that, in addition to user replies threaded via
   `args.answers[<REQ-id>]`, the orchestrator can thread a `blocker-cleared`
   signal for a merge-blocked REQ to drive its auto-resume after the blocker
   merges within the run. The held pipeline does NOT self-resume; the
   orchestrator relaunches the SAME script via `resumeFromRunId` with the
   cleared signal.
2. **`workflows/adlc-sprint.workflow.js`** — wire the orchestrator unblock pass
   into the cross-REQ merge barrier / post-merge path: after REQ-A merges and
   `repos[A].merged` is written, rebase held REQs (`blockedBy == A`) in their
   worktree (via an IO leaf agent, since the script has no shell), and on a clean
   rebase relaunch the held REQ's pipeline tail from its recorded phase carrying
   the `blocker-cleared` signal; on conflict abort + re-halt (BR-4). Keep the
   change minimal and routed through `agent()` leaves (the script owns only
   control flow). Honor the same deterministic order + serialization (BR-6) and
   retry bound (BR-10) as the legacy pass.

## Files to Create/Modify

- `sprint/SKILL.md` — Step 0 workflow resume contract: add the `blocker-cleared` orchestrator signal channel (BR-8)
- `workflows/adlc-sprint.workflow.js` — post-merge unblock pass via IO leaves; thread the blocker-cleared signal through the resume path

## Acceptance Criteria

- [ ] `sprint/SKILL.md` workflow resume contract documents an orchestrator-generated `blocker-cleared` signal, distinct from `args.answers[<REQ-id>]` user replies (BR-8).
- [ ] The held pipeline-runner / workflow REQ does NOT self-resume — resume is orchestrator-driven via `resumeFromRunId` (BR-8).
- [ ] `workflows/adlc-sprint.workflow.js` runs an unblock pass after a blocker merges within the run: rebase held REQs in their own worktree (IO leaf), clean → resume from recorded phase, conflict → abort + re-halt (BR-2/3/4/5).
- [ ] The workflow unblock pass honors deterministic order + one-at-a-time serialization (BR-6) and the retry bound (BR-10).
- [ ] All git/state I/O is performed inside `agent()` leaves; the script body owns only control flow (workflows architecture invariant: agents are leaves, script is orchestrator).
- [ ] Any existing `workflows/tests/` node:test suite still passes if touched; pure helpers added (if any) are unit-testable and deterministic (no Date.now/Math.random).

## Technical Notes

- The resume signal must be surgical (mirror the existing `args.answers[id]`
  pattern): inject the `blocker-cleared` marker ONLY into the held REQ's
  halt-prone / Phase-8 path so every untouched + already-merged REQ replays
  byte-identical from the journal cache (no recreated worktree, no double-merge).
- Per OQ-1 default this is the PRIMARY engine for auto-resume; the legacy engine
  (TASK-002) degrades to surface-to-human where it can't re-dispatch cleanly.
- Keep the JS edit small and routed through leaves; do NOT add a shell/fs to the
  script. The rebase commands live inside an IO leaf agent's prompt.
- Reuse the existing `blocked()` terminal constructor for the conflict re-halt;
  carry the materialized conflict files + `holdState` in its detail.
