---
id: TASK-267
title: "The approval protocol end to end against the Codex adapter, and the shell loop"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-18
dependencies: [TASK-265]
---

## Description

Run REQ-659's approval-protocol suite against `harness/codex.yml` through the Codex profile of the exec fake, and close the acceptance criteria that need the real adapter file end to end.

## Files to Create/Modify

- `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_exec_approve.py` — the suites parameterized over the exec-capable adapters.
- `tools/adlc/tests/fake_harness/exec_harness.py` — whatever the Codex profile still lacks: scripted un-allowed commands, a mid-run surface edit, a write to the user policy folder, a nested launch.
- `tools/adlc/sprint_exec.py` — the nested-launch refusal by process ancestry for `run`, a dispatch and a resume, logging `nested_launch_refused` (BR-18). TASK-260 found that only decisions are checked that way today (`caller_guard`); `run` and `resume` check `ADLC_EXEC_RUN` alone.
- `partials/tests/exec-engine.test.sh` — any new shell, under every shell `partials/tests/run.sh` loops over.

## Acceptance Criteria

- [x] Against the Codex adapter: launch, `awaiting_approval`, `/sprint approve`, the orchestrator's merge through `ADLC_FORGE_MOCK=1`, resume, done. And the reject path, with trust revoked in both.
- [x] After `approve` with model work remaining, the engine prepares the close-out working copy by the declared strategy, grants and later revokes trust for it, and launches the resume template with the parsed session id and the same rules, which the fake asserts.
- [x] With a 600-line prompt on stdin the Codex fake records exactly 600 lines, and `prompt_variant` names the `stdin-prompt` variant that passed in `codex.json`.
- [x] The Codex scenario exercises every declared exit code and the parse-failure path.
- [x] A fake that spawns a nested orchestrator launch is refused through pid ancestry, and `nested_launch_refused` is logged. With `ADLC_EXEC_RUN` set, a launch, a dispatch and a resume are each refused.
- [x] The fake fails the test loudly if launched with any `forbidden_flags` token.
- [ ] `pytest tools/adlc/tests` passes apart from the known Python 3.9 `test_module_imports_only_stdlib` failure, and `sh partials/tests/run.sh` exits 0 under bash, zsh, `/bin/sh` and dash.
  Every test this task adds or changes passes, and `sh partials/tests/run.sh` exits 0; the full `tools/adlc/tests` run is the integration branch's. Four failures there predate this task, each also failing at `db8dd9b`:
  - `test_exec_launch.py::test_two_engine_runs_share_the_user_config` and `test_a_supervisor_that_dies_after_the_grant_is_cleaned_up`: two supervisors on one repo with a file-rendering adapter. One run's `git config --worktree` write (`worktrees/<REQ>/config.worktree`, the BR-17 hiding) changes the common gitdir that the other run checksummed, and the other run reads it as a Rule B `common gitdir checksum mismatch`.
  - `test_exec_reach.py::test_reach_runs_against_the_union_of_deny_tiers` expects `claude` and the fixture as the only exec-capable adapters; `codex` has been one since TASK-265.
  - `test_exec_trust.py::test_install_exec_writes_the_policy_file` reads `capsys`. `harness_cli` binds its `out=sys.stdout` default when `test_exec_verify.py` imports it at collection, so the test fails whenever the two modules are collected together.
- [x] The suite passes offline: the fake never shells out to a real harness.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | test-case | `tools/adlc/tests/test_exec_approve.py::test_approval_protocol_per_adapter` | yes |
| AC-12 | test-case | `tools/adlc/tests/test_exec_approve.py::test_approval_protocol_per_adapter` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_exec_approve.py::test_close_out_resumes_with_the_same_rules` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_exec_launch.py::test_codex_prompt_arrives_whole_on_stdin` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_approve.py::test_close_out_resumes_with_the_same_rules` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_exec_launch.py::test_nested_launch_is_refused` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_exec_launch.py::test_nested_launch_is_refused` | yes |
| BR-13 | test-case | `partials/tests/exec-engine.test.sh` | no |
| AC-6 | test-case | `tools/adlc/tests/test_exec_launch.py::test_parse_failures_are_error_with_the_message_in_notes` | no |
| AC-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_codes_map_to_classes` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_exec_launch.py::test_denied_stderr_marks_a_claimless_run_denied` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_exec_launch.py::test_jsonl_fake_records_the_prompt_and_argv` | no |
| BR-12 | test-case | `tools/adlc/tests/test_exec_launch.py::test_the_sandbox_path_reaches_no_real_harness` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_exec_launch.py::test_the_run_tag_refuses_a_launch_a_dispatch_and_a_resume` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_approve.py::test_no_session_means_no_close_out` | no |
| AC-8 | test-case | `tools/adlc/tests/test_exec_approve.py::test_a_carried_close_out_state_is_data` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_approve.py::test_a_refused_close_out_argv_revokes_its_trust` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_closeout_state_file_note_is_the_only_difference` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_exec_launch.py::test_a_multi_repo_run_needs_an_add_dir_flag` | no |

Each protocol test that holds for every adapter runs once per exec-capable adapter as shipped, read from a toolkit copy with its committed result file (`exec_helpers.adapter_sandbox`, `EXEC_ADAPTERS`), and the adapter differences live in the helper and the fake's profile: `test_approval_protocol_per_adapter` (which replaces `test_happy_path` and `test_reject`), `test_close_out_resumes_with_the_same_rules`, `test_no_session_means_no_close_out`, `test_halt_record`, `test_forbidden_flag_refused`, `test_forbidden_flag_on_the_cli`, `test_no_session_id`, `test_nested_launch_is_refused` and `test_the_run_tag_refuses_a_launch_a_dispatch_and_a_resume`. The parse, exit-code and refusal-line tests run over the Codex-shaped fixture and the shipped Codex block (LESSON-756). The first run on the shipped block found what the fixture hid: the fixture had an `add_dir_flag` that Codex lacks, so the close-out could never launch on Codex. It now closes out through its own working copy (architecture ADR-7, as amended), and the fixture declares no `add_dir_flag`. Trust is checked against the user config the adapter names under the sandbox HOME, the file the harness reads (LESSON-777).

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- Parameterize, do not copy: a second copy of the suite for Codex would drift (LESSON-756).
- The fake's Codex event shape is held equal to the probe fake's by TASK-258's test; do not fork it here.
- Lessons in play: LESSON-329 and LESSON-605 (run new shell under the operator's shell, and under more than one).
