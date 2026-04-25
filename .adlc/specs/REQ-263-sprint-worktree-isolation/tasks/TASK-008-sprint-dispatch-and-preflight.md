---
id: TASK-008
title: "Add dispatch-line contract and pre-flight collision check to /sprint"
status: complete
parent: REQ-263
created: 2026-04-25
updated: 2026-04-25
dependencies: []
---

## Description

Update `sprint/SKILL.md` so that:

1. **Step 3 (dispatch)** emits a contract line declaring each pipeline-runner's absolute worktree path, per the format fixed in `architecture.md`. Producer side of the dispatch-line contract.
2. **Step 2 (pre-flight)** runs a collision check against `git worktree list --porcelain` for each candidate REQ and refuses to dispatch any REQ whose target `.worktrees/REQ-xxx` is already owned by a different branch.

This is independent of TASK-007 — both can ship in parallel. The contract is fixed in architecture.md; both files reference the same format.

Covers BR-1 (orchestrator declares, agent obeys), BR-5 (pre-flight collision check), BR-7 (dispatch prompt is the contract), and BR-9 (failure messages name the cleanup commands).

## Files to Create/Modify

- `sprint/SKILL.md` — Step 2 gets a new pre-flight check (added to the existing pre-flight table) and a new "Issue" reason. Step 3 dispatch prompt template gets the `WORKTREE PATH (mandatory): <abs-path>` line plus a one-line reminder of the worktree-isolation rules for the receiving agent.

## Acceptance Criteria

- [ ] `sprint/SKILL.md` Step 3 dispatch prompt includes the contract line `WORKTREE PATH (mandatory): <absolute-path>` exactly as fixed in `architecture.md`. (Covers BR-1, BR-7.) The orchestrator computes `<absolute-path>` as `<repo-path>/.worktrees/<REQ-id>` for each dispatched agent.
- [ ] The Step 3 prompt template additionally tells the agent (a) to use the path verbatim for `git worktree add`, (b) that all later phases read the path from `pipeline-state.json.repos[<id>].worktree`, and (c) that the only sanctioned operation against the parent repo path is `gh pr merge` in Phase 8 single-repo topology. (Reinforces BR-1; complements TASK-009.)
- [ ] `sprint/SKILL.md` Step 2 adds the pre-flight collision check: for each candidate REQ, parse `git worktree list --porcelain` in the primary repo and intersect against the candidate's target path `<repo-path>/.worktrees/<REQ-id>`. Any conflict marks the REQ ineligible with the issue reason `worktree path in use by branch <name>`. (Covers BR-5.)
- [ ] The example pre-flight table in Step 2 is updated to show the new "Issue" reason text in at least one example row, so future readers see the expected format.
- [ ] When the pre-flight check halts a REQ from dispatch, the surfaced message names the cleanup commands the user must run: `git -C <repo> worktree remove <path>` then `git -C <repo> branch -D <branch>` (with `--force` flagged as available). (Covers BR-9.)
- [ ] Cross-repo REQs: the Step 2 pre-flight scans only the **primary repo** for collisions (per OQ-2 default — sibling collisions are caught at `/proceed` Step 0 by TASK-007's gate). The skill documentation is explicit about this scope so future maintainers don't extend the pre-flight to siblings without a deliberate decision.
- [ ] No behavior change when zero candidate REQs collide: the dispatch proceeds with the new contract line in place but no pre-flight halts.

## Technical Notes

- The dispatch line format is normative in `architecture.md`. Match it byte-for-byte. If implementation surfaces an issue with the format, update architecture.md first, then both this task and TASK-007 in lockstep.
- The pre-flight check parses the same `git worktree list --porcelain` output that TASK-007 parses. Wording the parse step in both tasks consistently aids maintainability — reuse the same prose if practical.
- Existing Step 2 pre-flight already produces a markdown table with columns `REQ | Title | Status | Eligible | Issue`. The new check just adds rows with `Eligible: No` and the new `Issue` text — no schema change to the table.
- Step 3 currently dispatches "all agents in a single message to maximize parallelism." Preserve that; the contract line is per-agent in each agent's prompt, not a one-time emission.
- The worktree-isolation reminder in the dispatch prompt should be terse — this is reinforcement of TASK-009's contract, not the canonical statement of it. The agent definition is the source of truth for isolation rules.
- After editing, re-read Step 2 and Step 3 end-to-end and confirm the happy path (no collisions, all REQs eligible) still flows naturally.
