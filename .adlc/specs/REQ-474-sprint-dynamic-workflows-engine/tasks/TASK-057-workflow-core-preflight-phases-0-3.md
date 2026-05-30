---
id: TASK-057
title: "Workflow core — meta + Preflight + REQ pipeline + runReq Phases 0–3"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-29
dependencies: [TASK-055]
---

## Description

Build the `adlc-sprint` workflow skeleton: the `meta` block, the Preflight eligibility stage, the REQ-level `pipeline`, and `runReq`'s first half — Phase 0 (worktree + state), Phases 1/3 (validate gates with the ≤3 fix loop), and Phase 2 (parallel explore trio → architect/tasks agent). (ADR-3, ADR-4, ADR-6)

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — CREATE. `meta` (pure literal), `phase('Preflight')` eligibility `agent()` → `ELIGIBILITY`, `slice(0,5)`, `pipeline(todo, r => runReq(r.id))`; `runReq` Phases 0–3 + helpers `gate()`, `scoreEligibility`-fed preflight, `blocked()`.

## Acceptance Criteria

- [ ] `meta` is a pure literal (no computed values); phases declared.
- [ ] Preflight returns eligibility per REQ; the max-5 bound is applied after eligibility; truncation beyond 5 is `log()`-ed (BR-12).
- [ ] Phase 0 agent creates the worktree from `origin/<integrationBranch>` and records the absolute path in `pipeline-state.json.repos[*].worktree` (returns `REPOS`); idempotent if the worktree already exists.
- [ ] `gate()` runs ≤3 validate→fix iterations for Phases 1 and 3; 3× fail returns `blocked` (never throws).
- [ ] Phase 2 fans out `feature-tracer`/`architecture-mapper`/`integration-explorer` via `parallel()` then dispatches the architect agent (returns `TASKS`).
- [ ] Per-REQ agents use `opts.phase = id` (not global `phase()`) to avoid the concurrent-pipeline race.

## Technical Notes

- Every git/state op runs inside an `agent()` call — the script has no shell/fs (ADR-3).
- Worktree path obeys the REQ-263 dispatch-line/absolute-path contract; base is the resolved integration branch, never hardcoded `main` (LESSON-002, BUG-060).
- `blocked(id, reason, detail)` returns `{terminal:'blocked', ...}`; halts are values, not exceptions (ADR-6).
