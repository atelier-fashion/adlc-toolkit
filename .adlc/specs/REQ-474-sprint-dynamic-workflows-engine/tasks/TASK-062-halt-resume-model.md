---
id: TASK-062
title: "Halt/resume model — blocked-as-value + args.answers + resumeFromRunId"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-30
dependencies: [TASK-058, TASK-059]
---

## Description

Wire the cross-cutting halt/resume model (the agreed design's load-bearing piece): every halt returns a `blocked` value, the user's reply threads through `args.answers`, and a `resumeFromRunId` relaunch advances only the blocked REQ while everything else replays from cache. (ADR-6, BR-4, BR-5)

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — MODIFY. Ensure all three halt sites (validate ≤3 fail, reflector question, merge conflict) return `blocked`; thread `args.answers?.[id]` into ONLY the halt-prone agent prompts (`gate`, the Phase-5 fix).
- `sprint/SKILL.md` — MODIFY. After a workflow run, surface `{terminal:'blocked'}` REQs with their questions; on user reply, relaunch `Workflow({scriptPath, resumeFromRunId, args:{…, answers:{id:reply}}})`.

## Acceptance Criteria

- [ ] No halt path throws; each returns `{terminal:'blocked', reason, detail}` (a thrown error would null the item and lose the question).
- [ ] `args.answers[reqId]` is referenced only inside halt-prone prompts, so on resume only the blocked REQ's prompts diverge from cache.
- [ ] A resumed run recreates no existing worktree, re-implements no completed task, and re-merges no already-`merged` REQ (cache replay).
- [ ] The dispatcher surfaces blocked questions to the user and performs the `resumeFromRunId` relaunch with the answer.
- [ ] AC-3 of the requirement passes end-to-end (halt → surface → answer → advance only that REQ).

## Technical Notes

- Resume matches cached calls by `(prompt, opts)`; the `args.answers` injection is the mechanism that makes resume surgical (ADR-6).
- This task depends on the halt sites existing (Phase 5 in TASK-058, merge in TASK-059) and the validate gate in TASK-057.
