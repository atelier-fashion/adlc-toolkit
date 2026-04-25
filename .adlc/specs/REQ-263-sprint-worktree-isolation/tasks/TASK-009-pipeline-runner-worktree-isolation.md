---
id: TASK-009
title: "Add Worktree Isolation contract to pipeline-runner agent definition"
status: draft
parent: REQ-263
created: 2026-04-25
updated: 2026-04-25
dependencies: []
---

## Description

Add a top-level "Worktree Isolation" section to `agents/pipeline-runner.md` that codifies the agent-side rules of the dispatch-line contract: read the declared path from the launch prompt, read it from `pipeline-state.json` for every later phase, use absolute paths or `git -C <worktree>` for every Bash call, and never write to the parent repo's working tree (except the one sanctioned `gh pr merge` in Phase 8 single-repo topology).

This is the agent-definition source-of-truth for the worktree-isolation rules. TASK-008's dispatch prompt reinforces these rules but defers to this section for the canonical statement.

Independent of TASK-007 and TASK-008. Covers BR-6.

## Files to Create/Modify

- `agents/pipeline-runner.md` — Insert a new "Worktree Isolation" H2 section between the existing "CRITICAL: Subagent Mode" and "Pipeline Phases" sections.

## Acceptance Criteria

- [ ] `agents/pipeline-runner.md` contains a new `## Worktree Isolation` section positioned between `## CRITICAL: Subagent Mode` and `## Pipeline Phases`. (Covers BR-6.)
- [ ] The section states: the agent's first action after reading state in any phase is `cd <worktree>` (using the absolute path from `pipeline-state.json.repos[<id>].worktree`).
- [ ] The section states: every Bash call MUST use absolute paths or `git -C <worktree>` form. Shell cwd does not persist between Bash calls; the agent MUST NOT rely on it.
- [ ] The section states: the agent MUST NOT re-derive the worktree path from cwd, from the REQ id, or from any source other than `pipeline-state.json.repos[<id>].worktree`. The path is set once in Step 0 and is immutable for the rest of the run.
- [ ] The section explicitly carves out the one sanctioned exception: `gh pr merge` in Phase 8 single-repo topology runs from the parent repo path (`repos[<id>].path`), because git refuses to delete a branch that is checked out by a worktree. This exception is already documented in the existing "Worktree gotchas" subsection under Phase 8 — the new section cross-references it rather than duplicating.
- [ ] The existing "Worktree gotchas" subsection under Phase 8 stays in place. The new top-level section does not duplicate the gotchas — it states the agent-level isolation rule; the gotchas remain the operational detail for that one phase.
- [ ] After the edit, re-read the agent definition end-to-end and confirm the new section reads as a natural agent-level contract (rules the agent obeys throughout its lifetime), not a duplicate of phase-specific gotchas.

## Technical Notes

- The new section is short — a contract, not a tutorial. Three or four numbered rules plus the cross-reference to Phase 8 gotchas is the right shape. Don't pad.
- Position matters: putting it before "Pipeline Phases" makes it a top-level rule the agent reads before starting any phase. Burying it under one phase would weaken its scope.
- Tone should match the existing agent definition (terse, imperative, "you MUST" / "you MUST NOT" where appropriate).
- This task has no producer-consumer relationship with TASK-007 or TASK-008. It can be implemented and committed independently.
- If the editor is tempted to also update the "Worktree gotchas" Phase 8 subsection, resist — that subsection is already correct. The only addition under Phase 8 is the cross-reference *from* the new section *to* the gotchas, not the other way around.
