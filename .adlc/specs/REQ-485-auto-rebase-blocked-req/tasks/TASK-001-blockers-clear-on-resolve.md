---
id: TASK-001
title: "BR-11 clear-on-resolve + held-runner-no-self-resume in the merge/blocker path"
status: draft
parent: REQ-485
created: 2026-06-05
updated: 2026-06-05
dependencies: []
repo: adlc-toolkit
---

## Description

Establish the state-contract foundation REQ-485 builds on: the `blockers` entry
schema additions and the BR-11 clear-on-resolve rule, in the merge/blocker path
where `pipeline-state.json.blockers` is populated. This task is dependency-free
because every later task references the BlockHold state shape it defines.

Two edits:
1. **`agents/pipeline-runner.md`** — Phase 8 + Blocker Handling: add BR-11 (on a
   successful resume that reaches merge, clear the REQ's `blockers` entry — today
   only `repos[<id>].merged = true` is set, never the clear) and the explicit
   note that the held pipeline-runner does NOT self-resume (BR-8 — it already
   reported `blocked` and exited; the orchestrator drives resume).
2. **`proceed/phases-6-8-ship.md`** — Phase 8 pre-merge trial-merge gate:
   document the `blockers` entry schema additions (`holdState`, `rebaseAttempts`,
   `resolvedBlocker`) and the BR-11 clear-on-resolve at the merge step.

## Files to Create/Modify

- `agents/pipeline-runner.md` — Phase 8 / Blocker Handling sections: BR-11 clear, BR-8 no-self-resume note
- `proceed/phases-6-8-ship.md` — Phase 8 trial-merge gate: blockers schema additions + clear-on-resolve

## Acceptance Criteria

- [ ] `agents/pipeline-runner.md` Phase 8 single-repo merge step states: after a resume reaches merge, the orchestrator clears the REQ's `pipeline-state.json.blockers` entry (BR-11), distinct from setting `repos[<id>].merged = true`.
- [ ] `agents/pipeline-runner.md` states the held runner does NOT self-resume after returning `blocked` (BR-8); resume is orchestrator-driven.
- [ ] `proceed/phases-6-8-ship.md` Phase 8 documents the `blockers` entry fields `{blockedBy, conflictFiles, unblockCondition, holdState, rebaseAttempts, resolvedBlocker}` and the BR-11 clear-on-resolve.
- [ ] No existing behavior is removed; edits are additive to the trial-merge gate prose (REQ-483 wording preserved).

## Technical Notes

- BR-11 quote from spec: "Today the code sets `repos[<id>].merged = true` but
  never clears `blockers`; this REQ adds the clear." The clear is the idempotency
  anchor for BR-6 — the unblock pass considers ONLY REQs with a still-present
  `blockers` entry.
- `holdState` enum: `held | rebasing | resumed | re-halted | needs-manual-rebase`
  (System Model BlockHold.state, extended by ADR-6/ADR-7).
- Keep REQ-483's existing rc=1/rc=2/rc=3 branching prose intact; this is purely
  additive schema + clear-on-resolve documentation.
