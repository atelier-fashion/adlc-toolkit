---
id: TASK-269
title: "Output parsing by declared format, exit classes, and the JSONL profile of the exec fake"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-258]
---

## Description

Implement architecture ADR-6 and ADR-10. The engine parses a run's output by the adapter's declared format and source, and classifies the exit from the adapter's map and its refusal pattern. The exec fake becomes profile-driven, so a harness that prints JSONL and writes its last message to a file can be tested end to end.

## Files to Create/Modify

- `tools/adlc/exec_adapter.py` — `vet_extra` refuses any `allow_extra` or `allow_extra_exact` on `matcher: none`, because nothing can vet them there (architecture ADR-8; moved here from TASK-259 so the two tasks touch separate files); `parse_result` by `output.format` (`json`, `jsonl-stream`) and `output.source` (`stdout`, `file`); `denied_stderr`; `exit_class` unchanged in vocabulary.
- `tools/adlc/sprint_exec.py` — `on_exit` and `_read_result` read the declared source; a missing session id is reported at the halt as "resume is impossible".
- `tools/adlc/tests/fake_harness/exec_harness.py` — profiles chosen by the name the fake is installed under: `claude` (unchanged) and a JSONL profile that parses `exec … -o <file>` and `exec resume`, records argv, environment and the stdin line count, prints `thread.started`, `item.completed`, `turn.completed`, writes the last message to the `-o` file, and fails loudly on a forbidden flag.
- `tools/adlc/tests/exec_helpers.py` — `Sandbox(harness=…)`; the fake binary takes the adapter's `binary` name.
- `tools/adlc/tests/fixtures/exec-output/` — synthetic parser fixtures, each marked synthetic.
- `tools/adlc/tests/test_exec_adapter.py`, `tools/adlc/tests/test_exec_launch.py` — the tests below.

## Acceptance Criteria

- [ ] The JSONL parser returns the session id from `thread.started` and the final message from the `-o` file. A truncated stream, non-JSON stdout and an empty final message each give `exec.exitClass: error` with the parser's message in `notes` and no `reason` key under `exec`. A well-formed capture parses (the must-not-fail case).
- [ ] `stdout` and `stderr` files exist under `exec.logPath` after every run, failures included, and none is in the working copy.
- [ ] Each declared exit code maps to its class in `pipeline-state.json`; an undeclared `99` is `error` with `exec.exitCode: 99`; a `denied` exit leaves the REQ `status: blocked` with the last message in `blockers`, never `completed` or `merged`.
- [ ] A run with no claim whose stderr matches `denied_stderr` is `denied`. The pattern is applied to the harness's stderr only, never to the model's message.
- [ ] With a 600-line prompt on stdin the JSONL fake records 600 lines.
- [ ] A run whose output carried no session id halts with the "resume is impossible" line before approval is asked for. A run with one does not print it.
- [ ] The JSONL fake's event shape equals what `tools/adlc/tests/fake_harness/fake_harness_impl.py` prints for codex under `--json`, held by a test.
- [ ] Claude's parsing is unchanged: every existing exec test passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_jsonl_parser_and_its_failures` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_jsonl_parser_and_its_failures` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_missing_session_id_reports_resume_impossible` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_codes_map_to_classes` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_codes_map_to_classes` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_exec_launch.py::test_jsonl_fake_records_the_prompt_and_argv` | no |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field. The fake may key on the name it is installed under, because that is how a real binary is found.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures).
- `timeout` is in the ExitClass vocabulary and no engine code produces it today; leave that as it is.
- The parser never treats the model's text as instructions, and never reads a claim from it.
- Lessons in play: LESSON-869 (a fake prints a record format only under the flag the real CLI needs for it), LESSON-716 (parse the way the consumer does, and fail closed).
