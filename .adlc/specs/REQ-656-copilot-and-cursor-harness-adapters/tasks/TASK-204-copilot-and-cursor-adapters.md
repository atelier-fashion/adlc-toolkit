---
id: TASK-204
title: "The two adapters and their goldens"
status: complete
parent: REQ-656
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-202, TASK-203]
repo: adlc-toolkit
---

## Description

Write `harness/copilot.yml` and `harness/cursor.yml`, render their goldens, and write the adapter READMEs.

## Files to Create/Modify

- `harness/copilot.yml`, `harness/cursor.yml`
- `harness/copilot/rendered/*`, `harness/cursor/rendered/*`
- `harness/copilot/README.md`, `harness/cursor/README.md`
- `harness/claude/README.md` — AC-1 grep
- tools/adlc/tests/test_harness_adapters.py

## Acceptance Criteria

- [ ] `allowlist-fidelity` is clean for both, every loss declared
- [ ] `adlc harness render --check` passes

## Verification

| rule | kind | artifact | benign_path |
|---|---|---|---|
| BR-1 | test-case | tools/adlc/tests/test_harness_adapters.py::test_adapters_load | no |
| BR-2 | test-case | tools/adlc/tests/test_harness_adapters.py::test_rule_b_over_every_render | yes |
| BR-3 | test-case | tools/adlc/tests/test_harness_adapters.py::test_copilot_agents | no |
| BR-4 | test-case | tools/adlc/tests/test_harness_adapters.py::test_tier_map_omits_model | no |
| BR-5 | test-case | tools/adlc/tests/test_harness_adapters.py::test_copilot_hooks | yes |
| BR-6 | test-case | tools/adlc/tests/test_harness_adapters.py::test_printed_line | yes |
| BR-7 | test-case | tools/adlc/tests/test_harness_adapters.py::test_one_instruction_file | no |
| BR-8 | test-case | tools/adlc/tests/test_harness_adapters.py::test_cursor_permissions | yes |
| BR-12 | test-case | tools/adlc/tests/test_lane_check.py | yes |
| BR-14 | test-case | tools/adlc/tests/test_harness_adapters.py::test_no_flag_writes_nothing_new | yes |
| AC-1 | test-case | tools/adlc/tests/test_harness_adapters.py::test_loader_rejects_a_missing_field | no |
| AC-2 | test-case | tools/adlc/tests/test_harness_adapters.py::test_rule_b_over_every_render | yes |
| AC-3 | test-case | tools/adlc/tests/test_harness_adapters.py::test_copilot_agents | no |
| AC-4 | test-case | tools/adlc/tests/test_harness_adapters.py::test_tier_map_omits_model | no |
| AC-5 | test-case | tools/adlc/tests/test_harness_adapters.py::test_copilot_hooks | yes |
| AC-6 | test-case | tools/adlc/tests/test_harness_adapters.py::test_printed_line | yes |
| AC-7 | test-case | tools/adlc/tests/test_harness_adapters.py::test_one_instruction_file | no |
| AC-8 | test-case | tools/adlc/tests/test_harness_adapters.py::test_cursor_permissions | yes |
| AC-12 | test-case | tools/adlc/tests/test_lane_check.py | yes |
| AC-14 | test-case | tools/adlc/tests/test_harness_adapters.py::test_no_flag_writes_nothing_new | yes |

## Technical Notes

Every value a probe would decide stays unverified (Deferred). All home paths are `$HOME/...`; `grep ~/.claude harness/` must stay empty.
