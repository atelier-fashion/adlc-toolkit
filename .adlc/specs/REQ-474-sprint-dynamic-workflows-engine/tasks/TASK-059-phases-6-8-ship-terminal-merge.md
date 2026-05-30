---
id: TASK-059
title: "Phases 6–8 (ship) + TERMINAL gh-verify + cross-REQ merge sequencing"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-30
dependencies: [TASK-057]
---

## Description

Complete `runReq`: Phase 6 (PR creation), Phase 7 (PR cleanup + CI watch), Phase 8 (wrapup/merge). Add the `TERMINAL` schema return, the `gh pr view` verification of merge claims, and cross-REQ merge sequencing per ADR-12. (ADR-7, ADR-12)

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — MODIFY. Add Phases 6–8 agents + the merge-sequencing logic.

## Acceptance Criteria

- [ ] Phase 6 agent opens PR(s) based on the resolved integration branch (returns `PRS`).
- [ ] Phase 7 agent runs the per-PR sanity check + watches CI (no re-review).
- [ ] Phase 8: single-repo REQs self-merge and return `{terminal:'merged'}`; cross-repo REQs stop and return `{terminal:'pr-ready'}` for orchestrator sequencing.
- [ ] Every `merged`/`pr-ready` claim is re-verified with `gh pr view --json state,mergedAt` before acceptance; a false `merged` is corrected (BR-6).
- [ ] A merge conflict returns `{terminal:'blocked', reason:'merge-conflict'}` (halt).
- [ ] Concurrent cross-repo REQs touching a shared sibling serialize their merges via the ADR-12 barrier; independent REQs stay parallel.
- [ ] `pipeline-state.json.repos[*].merged` is set immediately after each successful merge (resumable, no double-merge).

## Technical Notes

- Mirror the legacy Phase-8 topology rules from `pipeline-runner.md` (single-repo self-merge from parent path; cross-repo `mergeOrder`) — but executed by the script via agents, not a monolithic pipeline-runner.
- The `gh` verification is the "claim ≠ truth" gate (ADR-7); keep it even when the agent claims success.
