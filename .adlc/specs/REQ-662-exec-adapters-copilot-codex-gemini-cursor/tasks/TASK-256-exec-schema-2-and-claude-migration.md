---
id: TASK-256
title: "Exec schema 2, its loader checks, and the mechanical migration of the claude block"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: []
---

## Description

Implement architecture ADR-1. Bump the exec sub-schema to version 2, add the ExecBlock keys with their validation, reshape the three keys the entity table reshapes, and migrate `harness/claude.yml` to the new shape with no change in engine behaviour. An adapter that keeps `exec: {flags: unverified}` must still load and must still be refused by name.

## Files to Create/Modify

- `tools/adlc/harness_adapter.py` — `EXEC_SCHEMA_VERSION = 2`; `_EXEC_KEYS`, `_EXEC_REQUIRED` and `_exec_block`: the new keys, their enums and types, form-dependent requirements (ADR-1), `prompt_variant` checked against the `launch` tokens, `exit_codes` holding `"0": ok` and only ExitClass values, `output` and `working_copy` as objects, `resume` as an argv template holding `{session_id}`, `forbidden_flags` non-empty and holding the six engine tokens.
- `tools/adlc/exec_adapter.py` — read the reshaped keys (`working_copy.strategy`, `resume`, `output`) through accessors, so every caller keeps working. No new behaviour here.
- `harness/claude.yml` — the exec block at schema 2: the three reshaped keys, plus `harness_version`, `verification: recorded`, `status: verified`, `prompt_delivery: stdin`, `prompt_variant`, `context_delivery: hooks`, `allow_render: flags`, `deny_render: flags`, `matcher: claude`, `operator_flags`, `config_surfaces`, `rules_reload`, `bypass_config_keys`, `shell_timeout_s`, `user_policy_file: none`.
- `tools/adlc/tests/fixtures/harness/` — exec fixture adapters: one `allow_render: flags`, one `allow_render: file`, each a full schema-2 block.
- `tools/adlc/tests/test_exec_adapter.py`, `tools/adlc/tests/test_harness_framework.py` — the refusal table of AC-1 and the migration.

## Acceptance Criteria

- [ ] Every one of AC-1's malformed fixtures refuses the whole adapter and names the key or probe: an unknown `exec` key, a missing `exit_codes`, an exit map without `0`, an unknown `exec_schema_version`, a block without `forbidden_flags`, and a block missing `config_surfaces`, `rules_reload`, `bypass_config_keys` or `prompt_variant`, or with a `rules_reload` outside `startup|live|unknown`.
- [ ] A `prompt_variant` that disagrees with the `launch` tokens refuses the adapter. A block with no `context_delivery` refuses.
- [ ] A key given for the wrong render form is refused (for example `allow_flag` with `allow_render: file`).
- [ ] `harness/claude.yml` loads at schema 2, and every existing `test_exec_*.py`, `test_fence_*.py` and `test_harness_*.py` test passes with no change to what it asserts.
- [ ] `harness/codex.yml`, `harness/copilot.yml`, `harness/cursor.yml` and `harness/antigravity.yml` load unchanged, and `exec_adapter.load` refuses each by name.
- [ ] A well-formed fixture of each render form loads (the must-not-refuse case).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_schema_2_refusals_name_the_key` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_schema_2_refusals_name_the_key` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_working_copy_strategy_is_an_object` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_exit_map_needs_zero_and_the_closed_vocabulary` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- The loader validates only when `exec_schema_version` is present (`harness_adapter.py:657-662`); keep that, it is what keeps the placeholder block opaque.
- The `worktree`-needs-a-`pass` check of AC-1 belongs to TASK-260 (`exec_verify`), because the loader does not read result files.
- Claude's `forbidden_flags`, `engine_deny`, `file_rules`, `fence_runner` and `config_isolation` carry over as they are (BR-1).
- Lessons in play: LESSON-716 (a validator must parse the way its reader does, and fail closed), LESSON-756 (a framework proven on one adapter has only proven that adapter's branches).
