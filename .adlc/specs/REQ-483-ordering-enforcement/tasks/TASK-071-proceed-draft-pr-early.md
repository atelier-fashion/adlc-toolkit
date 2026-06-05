---
id: TASK-071
title: "/proceed: draft-PR-early — open draft PR at Step 0, ready it at Phase 6 (BR-1, BR-2)"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: []
---

## Description

Move PR creation from Phase 6 to Step 0 as a *draft*, so intent + (later) footprint publish early. Phase 6 transitions the existing draft to ready instead of creating a new PR.

## Files to Create/Modify

- `proceed/SKILL.md` — Step 0: open draft PR + record state
- `proceed/phases-6-8-ship.md` — Phase 6: `gh pr create` → `gh pr ready`

## Acceptance Criteria

- [ ] `/proceed` Step 0, after the worktree is created and the branch pushed, opens a **draft** PR (`gh pr create --draft --base <integrationBranch>`) and records `repos[<id>].prUrl`, `prNumber`, and `prCreatedAt` in `pipeline-state.json`.
- [ ] Phase 6 (`phases-6-8-ship.md`) transitions the existing draft to ready via `gh pr ready <prNumber>` and does NOT create a second PR; it still applies the full PR body (summary/tasks/etc.) via `gh pr edit`, preserving the `adlc-footprint` block.
- [ ] The base branch is read from `integrationBranch` in state (never hardcoded `main`) — LESSON-036.
- [ ] Resume-safe: if Step 0 finds a draft PR already recorded for this REQ (re-run), it reuses it rather than opening another.
- [ ] Subagent mode (`/sprint` pipeline-runner): draft-PR-early still opens the per-REQ draft PR (so its footprint publishes), consistent with the runner contract.
- [ ] `python3 tools/lint-skills/check.py` passes; new shell sh/zsh-portable + balanced.

## Technical Notes

- Push the branch before `gh pr create` (a PR needs a remote branch). This is new at Step 0 — today the branch is pushed at Phase 6.
- The draft PR's `createdAt` is the deterministic ordering basis (BR-8) — opening it at Step 0 (not Phase 6) is what makes ordering meaningful.
- Ship the Phase-6 ready-path together with the Step-0 create so Phase 6 always has a draft to ready (LESSON-004 — replacement before removal).
- Anchor the Step 0 addition near the existing "Step 4 advisory — in-flight manifest" block.
