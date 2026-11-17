---
id: TASK-258
title: "Launch, resume and result parsing driven by adapter data, with the closed-world argv check"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-256]
---

## Description

Implement architecture ADR-6, ADR-7 and ADR-10. The engine builds its launch and resume argv from the adapter's templates and placeholders, checks the result against the template, parses output by the declared format, and classifies the exit from the adapter's map. The exec fake becomes profile-driven so a JSONL harness can be tested.

## Files to Create/Modify

- `tools/adlc/exec_adapter.py` — placeholder substitution as whole tokens; `closed_world`; `launch_argv` and a `resume_argv` built from `resume`; `parse_result` by `output.format` (`json`, `jsonl-stream`) and `output.source` (`stdout`, `file`); `denied_stderr`; `exit_class` unchanged in vocabulary.
- `tools/adlc/sprint_exec.py` — `_argv`, `_spawn`, `on_exit`, `close_out` and the answer relaunch use the new builders; the `{last_message}` file lives in the run directory; `operator_flags` filters `--harness-flag`; `ADLC_DISABLE_DELEGATE=1` in the child environment when `shell_timeout_s.delegate` is `unsupported`; a missing session id is reported at the halt as "resume is impossible".
- `tools/adlc/tests/fake_harness/exec_harness.py` — profiles chosen by the name the fake is installed under: `claude` (unchanged) and a JSONL profile that parses `exec … -o <file>` and `exec resume`, records argv, environment and the stdin line count, prints `thread.started`, `item.completed`, `turn.completed`, writes the last message to the `-o` file, and fails loudly on a forbidden flag.
- `tools/adlc/tests/exec_helpers.py` — `Sandbox(harness=…)`; the fake binary takes the adapter's `binary` name.
- `tools/adlc/tests/test_exec_adapter.py`, `tools/adlc/tests/test_exec_launch.py` — the tests below; `tools/adlc/tests/fixtures/exec-output/` — synthetic parser fixtures, each marked synthetic.

## Acceptance Criteria

- [ ] The final argv equals the template with only declared placeholders, the renderer's flag pairs, the declared isolation and resume tokens, and `operator_flags` entries. One extra token, one changed token and one reordered token are each refused at launch and at resume. A placeholder substituted as part of a token is refused.
- [ ] A `--harness-flag` outside `operator_flags` is refused. One inside it launches (the must-not-refuse case).
- [ ] A `-c`, `--config`, `-p` or `--profile` token absent from the template is refused on the file-render fixture.
- [ ] The JSONL parser returns the session id from `thread.started` and the final message from the `-o` file. A truncated stream, non-JSON stdout and an empty final message each give `exec.exitClass: error` with the parser's message in `notes` and no `reason` key under `exec`.
- [ ] `stdout` and `stderr` files exist under `exec.logPath` after every run, failures included, and none is in the working copy.
- [ ] Each declared exit code maps to its class in `pipeline-state.json`; an undeclared `99` is `error` with `exec.exitCode: 99`; a `denied` exit leaves the REQ `status: blocked` with the last message in `blockers`.
- [ ] With a 600-line prompt on stdin the JSONL fake records 600 lines.
- [ ] `delegate: unsupported` launches with `ADLC_DISABLE_DELEGATE=1` and nothing beyond `env_passthrough`, `auth_env` and `ADLC_EXEC_RUN`; a supported adapter launches without it.
- [ ] A run whose output carried no session id halts with the "resume is impossible" line before approval is asked for.
- [ ] Claude's launch, resume and parsing are unchanged: every existing exec test passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_placeholders_are_whole_tokens` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_closed_world_argv` | yes |
| AC-19 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_closed_world_argv` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_launch_argv_snapshot` | no |
| BR-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_jsonl_parser_and_its_failures` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_jsonl_parser_and_its_failures` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_missing_session_id_reports_resume_impossible` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_codes_map_to_classes` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_codes_map_to_classes` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_exec_launch.py::test_delegate_unsupported_sets_the_env` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_exec_launch.py::test_delegate_unsupported_sets_the_env` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_exec_launch.py::test_jsonl_fake_records_the_prompt_and_argv` | no |
| BR-13 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_exec_modules_import_only_stdlib` | no |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- `timeout` is in the ExitClass vocabulary and no engine code produces it today; leave that as it is.
- The fake's JSONL shape must match what `tools/adlc/tests/fake_harness/fake_harness_impl.py` prints for codex under `--json` (BUG-278); add a test that holds the two event shapes equal.
- Lessons in play: LESSON-869 (a fake prints a record format only under the flag the real CLI needs for it), LESSON-663 (allowlist what may run; forbidding one flag at a time never converges).
