---
id: TASK-267
title: "The approval protocol end to end against the Codex adapter, and the shell loop"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
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

- [ ] Against the Codex adapter: launch, `awaiting_approval`, `/sprint approve`, the orchestrator's merge through `ADLC_FORGE_MOCK=1`, resume, done. And the reject path, with trust revoked in both.
- [ ] After `approve` with model work remaining, the engine prepares the close-out working copy by the declared strategy, grants and later revokes trust for it, and launches the resume template with the parsed session id and the same rules, which the fake asserts.
- [ ] With a 600-line prompt on stdin the Codex fake records exactly 600 lines, and `prompt_variant` names the `stdin-prompt` variant that passed in `codex.json`.
- [ ] The Codex scenario exercises every declared exit code and the parse-failure path.
- [ ] A fake that spawns a nested orchestrator launch is refused through pid ancestry, and `nested_launch_refused` is logged. With `ADLC_EXEC_RUN` set, a launch, a dispatch and a resume are each refused.
- [ ] The fake fails the test loudly if launched with any `forbidden_flags` token.
- [ ] `pytest tools/adlc/tests` passes apart from the known Python 3.9 `test_module_imports_only_stdlib` failure, and `sh partials/tests/run.sh` exits 0 under bash, zsh, `/bin/sh` and dash.
- [ ] The suite passes offline: the fake never shells out to a real harness.

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

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- Parameterize, do not copy: a second copy of the suite for Codex would drift (LESSON-756).
- The fake's Codex event shape is held equal to the probe fake's by TASK-258's test; do not fork it here.
- Lessons in play: LESSON-329 and LESSON-605 (run new shell under the operator's shell, and under more than one).
