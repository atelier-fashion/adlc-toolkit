---
id: TASK-066
title: "Wire /manifest advisory display into /proceed Step 0 pre-flight"
status: draft
parent: REQ-482
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-065]
---

## Description

Add an advisory, non-blocking in-flight-manifest display to `/proceed` Step 0, so a session sees what other work is in flight (and any coarse overlap with the REQ it's about to start) before creating the worktree.

## Files to Create/Modify

- `proceed/SKILL.md` — add a Step 0 sub-step that invokes `/manifest` (or its derivation) advisorily

## Acceptance Criteria

- [ ] `/proceed` Step 0 invokes `/manifest` (or its derivation) and displays the in-flight list + any coarse overlap involving the target REQ, before work begins. (BR-9)
- [ ] The display reuses the `git fetch origin` already performed earlier in Step 0 (no extra fetch). (BR-14)
- [ ] The current REQ is passed so it is marked as self in the output. (BR-13)
- [ ] A manifest-build failure here MUST NOT block, halt, or fail the pipeline — it is purely informational and does NOT count as one of the three legitimate halt points. (BR-7)
- [ ] The existing worktree-collision gate and all other Step 0 behavior are unchanged.
- [ ] `python3 tools/lint-skills/check.py` passes clean.

## Technical Notes

- Insertion point (architecture-mapper): within Step 0, after the `git fetch origin` (proceed/SKILL.md ~L193) and around the "Preflight verified" summary (~L244). Keep it clearly labeled advisory.
- Do NOT introduce a new halt or a new gate — Step 0's only halts remain the worktree-collision precondition error.
- Word it so the autonomous-execution contract is preserved: this is an "emit and continue" log step, not a question.
