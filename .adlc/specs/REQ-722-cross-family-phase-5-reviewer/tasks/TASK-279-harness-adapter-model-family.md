---
id: TASK-279
title: "Harness adapters declare `model_family`; `adlc harness family` resolves the implementer"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-278]
---
## Description

Give each harness adapter an optional `model_family` key, validated against the shared
enum, and add `adlc harness family`, which prints the implementer family for the current
process from sources the session cannot write (architecture ADR-2).

## Files to Create/Modify

- `tools/adlc/harness_adapter.py` — `model_family` in `_TOP_KEYS`, validated with `parse_family`; schema version bump per the loader's version gate (`KNOWN_SCHEMA_VERSIONS`)
- `tools/adlc/harness_cli.py` — `family` subcommand: exec run record `harness` (when `ADLC_EXEC_RUN` is set) → adapter `model_family`; else `CLAUDECODE=1` → `claude`; else `unknown`
- `harness/claude.yml` — `model_family: anthropic`
- `harness/codex.yml` — `model_family: openai`
- `harness/copilot.yml` — `model_family: unknown`
- `harness/cursor.yml` — `model_family: unknown`
- `harness/antigravity.yml` — `model_family: unknown`
- `tools/adlc/tests/test_harness_adapters.py` — key accepted, unknown value rejected, absent means `unknown`, version gate
- `tools/adlc/tests/test_harness_family.py` — new: the three resolution arms and their order; a forged `ADLC_EXEC_RUN` with no run record resolves `unknown`
- `tests/fixtures/harness/` — fixture adapters updated for the schema bump where the tests load them

## Acceptance Criteria

- [ ] Every shipped adapter loads, and each declares the value in the architecture's table
- [ ] An adapter with `model_family: gpt-5` fails to load with the field named
- [ ] Under a seeded exec run record naming `codex`, `adlc harness family` prints `openai` even with `CLAUDECODE=1` set
- [ ] With `CLAUDECODE=1` and no exec run, it prints `anthropic`; with neither, `unknown`
- [ ] The command never reads a file under the current worktree's `.adlc/` (LESSON-718)
- [ ] `tools/adlc/tests` for the adapter, render and doctor surfaces pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_harness_family.py::test_unestablished_implementer_is_unknown` | no |
| BR-3 | test-case | `tools/adlc/tests/test_harness_adapters.py::test_multi_family_adapters_declare_unknown` | no |
| BR-2 | test-case | `tools/adlc/tests/test_harness_family.py::test_family_never_inferred_from_harness_name_alone` | no |

Lessons: LESSON-756, LESSON-906

## Technical Notes

- `load_adapter` (`harness_adapter.py:861`) uses the stdlib `harness_yaml`, so import `tools/delegate/model_family.py` by path (as `forge_config.py` imports from `tools/delegate`), not through `_machine_config` (which may pull PyYAML).
- `tools/adlc/checks.py:233-237` marks `CLAUDECODE` unverified. It was observed set (`CLAUDECODE=1`) in a Claude Code desktop shell on 2026-11-24; record the version in the code comment when implementing.
- The exec run record lookup reuses the run-directory helpers in `tools/adlc/sprint_exec.py`; the record's `harness` field is written at `sprint_exec.py:885`.
- Run `adlc harness render --check` after the schema bump; rendered surfaces must not change.
