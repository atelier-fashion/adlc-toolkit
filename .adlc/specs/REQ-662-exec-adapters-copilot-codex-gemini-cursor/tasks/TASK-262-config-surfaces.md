---
id: TASK-262
title: "Config surfaces: guarded writes, manifests, the four checks, the bypass scan and the user policy folder"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-261]
---

## Description

Implement architecture ADR-4, except the PR-diff gate and the hiding of exec-rendered paths (TASK-264). `exec_surfaces.py` owns every file the engine writes into a working copy or a user policy folder for a run.

## Files to Create/Modify

- `tools/adlc/exec_surfaces.py` (new) — the guarded write, the surface manifest, render-or-absent, stray-file deletion, the launch and resume re-render check, the exit and halt verification, the `bypass_config_keys` scan, and the user policy folder's manifest and atomic write.
- `tools/adlc/sprint_exec.py` — calls at pre-flight, before resume, at exit and at the halt; `rule_file_rerendered` and `config_surface_violation` events.
- `tools/adlc/exec_safety.py` — the surface manifest joins what is verified before each exec, if the existing manifest code is the right home.
- `tools/adlc/tests/test_exec_surfaces.py` (new), `tools/adlc/tests/test_exec_launch.py`.

## Acceptance Criteria

- [ ] Every `config_surfaces` entry is rendered whole-file or absent, a stray file in a directory surface is deleted, and the manifest matches after render.
- [ ] A symlink, a hardlink and a FIFO at any path component are each refused, as is a resolved path outside the working-copy root. A plain file and a plain directory are written (the must-not-refuse case).
- [ ] After a test mutates a rendered rule file, the next launch and the next resume each log `rule_file_rerendered` with `checksum_matched: false`, and the file is byte-equal to a fresh render. One changed byte is caught.
- [ ] A fake that edits a surface mid-run produces `config_surface_violation` at exit and at the halt, and the surface is repaired at the next launch or resume. An untouched run produces none.
- [ ] `rules_reload: unknown` is handled exactly as `live`.
- [ ] Under `context_delivery: prompt` the working copy at launch holds no hook file; one the fake writes mid-run is a surface violation at exit.
- [ ] A fixture user config and a fixture working-copy config each carrying a `bypass_config_keys` key refuse the run at launch and at resume. An unparsable config file refuses it. A clean pair does not.
- [ ] Under a sandbox `HOME` holding an operator-authored rules file, the engine writes only its toolkit-owned policy file, leaves the operator's content byte-identical, and writes no allow at user level. A missing or drifted toolkit-owned file, or a stray file in the policy folder, refuses the run before launch and before resume, naming the file.
- [ ] Two concurrent writers of the policy file leave one intact file.
- [ ] The exec render of the working-copy config equals the project render.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-15 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_surfaces_are_rendered_or_absent_and_strays_deleted` | yes |
| AC-18 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_guarded_write_refuses_links_and_fifos` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_exec_launch.py::test_mutated_rule_file_is_rerendered` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_launch.py::test_mutated_rule_file_is_rerendered` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_bypass_config_keys_refuse` | yes |
| AC-19 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_bypass_config_keys_refuse` | yes |
| AC-14 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_user_policy_folder_manifest` | yes |
| AC-22 | test-case | `tools/adlc/tests/test_exec_surfaces.py::test_user_policy_file_is_whole_file_and_atomic` | yes |
| AC-25 | test-case | `tools/adlc/tests/test_exec_launch.py::test_prompt_delivery_renders_the_hook_file_absent` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- Every path comes from the adapter. `test_harness_codex.py::test_no_codex_path_outside_the_adapter` fails on any `~/.codex` or `.codex/` string under `tools/`.
- Read TOML with `toml_merge.scan`, the reader the renderer uses, so the scan parses the way the harness does (LESSON-716).
- The orchestrator must run nothing a harness could write, and must read no file the model can edit to decide a check (LESSON-718). Compare case-folded paths.
- REQ-659 owns what a Rule B protocol violation does; this task reports it.
