---
id: TASK-264
title: "The halt-time exec-path PR-diff gate, and hiding and restoring exec-rendered paths"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-263]
---

## Description

Implement BR-17 (architecture ADR-4, last three bullets but one). Exec-rendered paths never reach the REQ's PR: tracked ones are restored from the blob recorded at launch, untracked ones are hidden per working copy, and one gate at the halt refuses `approve` when the PR touches any of them.

## Files to Create/Modify

- `tools/adlc/exec_gates.py` — the exec-path gate over `headRefOid` and the local `--no-renames` diff, case-folded, directory surfaces as prefixes; `ExecRun.plan.execPathTouched`.
- `tools/adlc/exec_surfaces.py` — record each tracked surface's blob oid at launch, overwrite it, mark it `skip-worktree`, restore it before the final push and at cleanup; hide untracked ones through `git config --worktree core.excludesFile`.
- `tools/adlc/sprint_exec.py` — the pre-flight check for `extensions.worktreeConfig`; the gate in `compute_plan` and `_halt`; `approve` refuses on a non-empty list; restore at cleanup.
- `tools/adlc/tests/test_exec_gates.py` (new or extended), `tools/adlc/tests/test_exec_approve.py`.

## Acceptance Criteria

- [ ] Fixtures that add, modify, delete, rename into and rename out of an exec-rendered path or a `config_surfaces` directory prefix, and a case-variant spelling of such a path, each populate `execPathTouched` and make `approve` refuse. `--ack-gate-change` does not override it.
- [ ] A PR that touches none of them leaves the list empty and `approve` proceeds (the must-not-refuse case).
- [ ] A tracked path the fake edited, and one whose HEAD moved since launch, are both restored from the blob oid recorded at launch, not from HEAD.
- [ ] Run against a tracked and an untracked exec-rendered fixture path, the main checkout's `git status` is unchanged, and the shared `info/exclude` is never written.
- [ ] The pre-flight refuses when `extensions.worktreeConfig` is unavailable.
- [ ] A fixture that runs `git add --sparse` or `git update-index --no-skip-worktree` on a hidden path is caught by the gate.
- [ ] REQ-659's "changes the gate" list reports a PR fixture touching a config surface.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-17 | test-case | `tools/adlc/tests/test_exec_gates.py::test_exec_path_gate_fixtures` | yes |
| AC-20 | test-case | `tools/adlc/tests/test_exec_gates.py::test_exec_path_gate_fixtures` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_gates.py::test_tracked_restored_from_launch_blob_and_untracked_hidden` | yes |
| AC-18 | test-case | `tools/adlc/tests/test_exec_gates.py::test_surface_change_is_on_the_changes_the_gate_list` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- The `clone` strategy's private `info/exclude` is out of stage 1: no staged adapter declares `clone`, and the engine does not implement it (spec Amendments, "Working copy").
- `skip-worktree` is best-effort hiding and a declared residual; the gate is the control.
- The gate must compute its paths from the adapter and the run record, never from a file in the working copy (LESSON-718).
- Git runs with hooks and fsmonitor disabled, as every orchestrator git call does (REQ-659 BR-23).
