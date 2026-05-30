---
id: TASK-058
title: "Phase 4 (serial implement) + Phase 5 (parallel panel + deterministic consolidation)"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-29
dependencies: [TASK-057, TASK-055]
---

## Description

Implement the heart of the engine: serial Phase 4 in the single REQ worktree, then the restored parallel Phase-5 review panel (reflector + 5 reviewers) with deterministic JS consolidation. This is the quality lift the legacy `/sprint` sacrifices. (ADR-5, ADR-7)

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — MODIFY. Add Phase 4 (`for tier: for task: await agent(task-implementer)` — serial, one writer) and `verify()` (Phase 5).
- `workflows/schemas.js` — MODIFY only if `FINDINGS` needs adjustment during integration.

## Acceptance Criteria

- [ ] Phase 4 runs task-implementers in dependency-tier order, **serially within the REQ worktree** (no concurrent writers); `pipeline-state.json.phase4` updated per task.
- [ ] Phase 5 dispatches reflector + 5 reviewers (single fan-out per touched repo), each told "Report findings only", returning `FINDINGS`.
- [ ] `dedupeAndRank()` (pure JS) dedupes within repo, tags cross-repo issues, ranks by severity; a `Critical` (or `mustFix`) finding blocks merge.
- [ ] A reflector `userFacing` finding returns `{terminal:'blocked', reason:'reflector-questions'}` (halt).
- [ ] Conditional re-verify reruns ONLY the 5 reviewers (not reflector) for the `(repo,dimension)` pairs that had fixes, ≤1 loop.
- [ ] The architecture-reviewer receives the cross-repo change manifest (from Phase-4 state, computed once — no barrier).

## Technical Notes

- `task-implementer` is unchanged; serial execution is what keeps the shared worktree safe (ADR-5).
- Consolidation is deterministic JS, not an agent (ADR-7, BR-7). Gate rule mirrors `/review`: any `Critical` ⇒ not merge-ready.
- Pre-pass candidates are NOT wired here — that is TASK-060 (v1 runs the panel candidate-less per BR-8).
