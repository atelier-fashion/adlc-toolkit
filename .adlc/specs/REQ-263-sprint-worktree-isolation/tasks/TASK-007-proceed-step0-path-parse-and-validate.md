---
id: TASK-007
title: "Add path-parse + worktree validation to /proceed Step 0"
status: complete
parent: REQ-263
created: 2026-04-25
updated: 2026-04-25
dependencies: []
---

## Description

Update `proceed/SKILL.md` Step 0 so that the worktree path is **declared by the caller** (when present) and **validated against `git worktree list --porcelain`** before `git worktree add` runs. Treat the path stored in `pipeline-state.json.repos[<id>].worktree` as immutable for the rest of the run.

This is the consumer side of the dispatch-line contract documented in `architecture.md`. The producer side (TASK-008) and this task can ship in parallel because the contract format is fixed in architecture.md, not in either skill file.

Covers BR-2 (fallback derivation), BR-3 (validation gate is mandatory), BR-4 (state is source of truth), BR-8 (cross-repo coverage), BR-9 (error message names cleanup commands), BR-10 (no behavior change for direct invocations on a clean repo).

## Files to Create/Modify

- `proceed/SKILL.md` — Step 0 receives a new sub-step inserted between current 0.4 and 0.5 covering path declaration + validation. The "Pipeline State Tracking" section gets a brief addendum noting that `repos[<id>].worktree` is immutable post-Step-0.

## Acceptance Criteria

- [ ] `proceed/SKILL.md` Step 0 documents the parse-declared-path step: scan the launch prompt for the line matching the format declared in `architecture.md` (`^WORKTREE PATH \(mandatory\): (.+)$`); use the captured path verbatim; if absent, fall back to `<repo-path>/.worktrees/REQ-xxx`. (Covers BR-2.)
- [ ] `proceed/SKILL.md` Step 0 documents the validation gate: before `git worktree add`, run `git -C <repo-path> worktree list --porcelain`; parse `worktree <path>` / `branch <ref>` pairs; if the target path is registered to a different branch than `feat/REQ-xxx-...`, halt with a clear error. (Covers BR-3.)
- [ ] The error message names the cleanup commands the user must run: `git -C <repo> worktree remove <path>` then `git -C <repo> branch -D <branch>` (with `--force` flagged as available). (Covers BR-9.)
- [ ] If the target path is already registered to the **correct** branch (resume scenario per ADR-2 in architecture.md), Step 0 records the path in state and skips the `git worktree add` — no halt, no re-add.
- [ ] The "Pipeline State Tracking" section (or Step 0.5 wording) is updated to note that `repos[<id>].worktree` is immutable post-Step-0; later phases MUST read the path from state and MUST NOT re-derive from cwd. (Covers BR-4.)
- [ ] Cross-repo coverage: the validation gate applies to **every** `git worktree add` Step 0 performs, primary or sibling. (Covers BR-8.) A sibling collision halts with the same error format.
- [ ] Behavior on a clean repo with no contract line and no existing worktree is identical to current behavior — same path, same `git worktree add` command, same state initialization. (Covers BR-10.) Verify by reading the diff: the new sub-step short-circuits to the existing flow when no contract line is present and no collision exists.

## Technical Notes

- The contract line format is normative in `architecture.md`. Do not invent a different format here. If implementation reveals the format is impractical (e.g., escaping issues with paths containing spaces), flag it and update architecture.md first.
- The fallback path derivation already exists in current Step 0.5 (`git -C <repo-path> worktree add .worktrees/REQ-xxx ...`). The new sub-step prefers the declared path when present; the fallback is the existing derivation.
- The `git worktree list --porcelain` output is line-oriented: blocks separated by blank lines, each block has `worktree <abs-path>`, `HEAD <sha>`, and either `branch <ref>` or `detached`. Parse line-by-line; no special tooling needed.
- Insert the new sub-step **before** `git worktree add`, after `git checkout main && git pull`. Numbering: keep current 0.4 as-is; insert "0.4a Parse declared path" and "0.4b Validate against worktree list" before current 0.5.
- The state-immutability addendum belongs near rule 5 of the Gate Protocol ("Resume from interruption — Trust `repos` as the source of truth for worktree paths — do not re-derive from cwd"). That sentence already exists; the change is to strengthen it: extend it to cover non-resume scenarios too (post-Step-0, every phase reads from state, not just resumes).
- This task does NOT touch the `pipeline-state.json` schema. The `repos[<id>].worktree` field already holds the absolute path.
- Run a sanity check after editing: re-read the updated Step 0 end-to-end and confirm the happy path (clean repo, no contract line, no existing worktree) still flows naturally without the new sub-steps adding friction.
