---
id: TASK-258
title: "Launch and resume argv from the adapter's templates, with the closed-world check"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-256]
---

## Description

Implement architecture ADR-7. The engine builds its launch and resume argv from the adapter's templates and placeholders, checks the result against the template, and sets the child environment from the adapter. Output parsing and the fake's second profile are TASK-269.

## Files to Create/Modify

- `tools/adlc/exec_adapter.py` — placeholder substitution as whole tokens; `closed_world`; `launch_argv` and a `resume_argv` built from `resume`.
- `tools/adlc/sprint_exec.py` — `_argv`, `_spawn`, `close_out` and the answer relaunch use the new builders; the `{last_message}` path is a file in the run directory; `operator_flags` filters `--harness-flag`; `ADLC_DISABLE_DELEGATE=1` in the child environment when `shell_timeout_s.delegate` is `unsupported`.
- `tools/adlc/tests/test_exec_adapter.py`, `tools/adlc/tests/test_exec_launch.py` — the tests below.

## Acceptance Criteria

- [ ] The final argv equals the template with only declared placeholders, the renderer's flag pairs, the declared isolation and resume tokens, and `operator_flags` entries. One extra token, one changed token and one reordered token are each refused at launch and at resume. A placeholder substituted as part of a token is refused.
- [ ] A `--harness-flag` outside `operator_flags` is refused. One inside it launches (the must-not-refuse case).
- [ ] A `-c`, `--config`, `-p` or `--profile` token absent from the template is refused on the file-render fixture.
- [ ] `delegate: unsupported` launches with `ADLC_DISABLE_DELEGATE=1` and nothing beyond `env_passthrough`, `auth_env` and `ADLC_EXEC_RUN`; a supported adapter launches without it.
- [ ] Claude's launch, resume and parsing are unchanged: every existing exec test passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_placeholders_are_whole_tokens` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_closed_world_argv` | yes |
| AC-19 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_closed_world_argv` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_launch_argv_snapshot` | no |
| BR-10 | test-case | `tools/adlc/tests/test_exec_launch.py::test_delegate_unsupported_sets_the_env` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_exec_launch.py::test_delegate_unsupported_sets_the_env` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_exec_modules_import_only_stdlib` | no |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- Lessons in play: LESSON-663 (allowlist what may run; forbidding one flag at a time never converges).
