---
id: TASK-211
title: "Codex renderers, the adapter and its goldens"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-210]
repo: adlc-toolkit
---

## Description

Register the four formats, close the restoration path in render and lint, write `harness/codex.yml` and its goldens.

## Files to Create/Modify

- `harness/codex.yml` — new adapter
- `harness/codex/README.md` — new
- `harness/codex/rendered/adlc.rules` — new golden
- `harness/codex/rendered/hooks.json` — new golden
- `harness/codex/rendered/config.toml` — new golden
- `harness/codex/rendered/agents.json` — new golden
- `harness/claude.yml` — the one added line
- `tools/adlc/harness_adapter.py` — format registry
- `tools/adlc/harness_render.py` — formats, restoration, shapes, drift, parity, copies
- `tools/adlc/agents_render.py` — TOML copies
- `tools/adlc/tests/test_harness_codex.py` — new

## Acceptance Criteria

- [ ] The rules render has no `git push`, `git branch` or `git -C` allow, no `forbidden`, and every deny entry as `prompt`
- [ ] A fixture `allow ["git", "push"]` fails the lint even with a `pass` record and `strictest-wins`
- [ ] A same-position fixture entry restores
- [ ] Claude's golden is byte-identical

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | tools/adlc/tests/test_harness_codex.py::test_no_codex_path_outside_the_adapter | yes |
| BR-2 | test-case | tools/adlc/tests/test_harness_codex.py::test_agent_render_restraint_and_ethos | yes |
| BR-3 | test-case | tools/adlc/tests/test_harness_codex.py::test_lint_refuses_a_restored_git_push | yes |
| BR-4 | test-case | tools/adlc/tests/test_harness_codex.py::test_removing_a_declared_loss_fails_the_lint | no |
| BR-6 | test-case | tools/adlc/tests/test_harness_codex.py::test_hooks_render | yes |
| BR-7 | test-case | tools/adlc/tests/test_harness_codex.py::test_lane_check_blocks_the_codex_layer | yes |
| BR-13 | test-case | tools/adlc/tests/test_harness_codex.py::test_claude_golden_and_adapter_unmoved | yes |
| AC-1 | test-case | tools/adlc/tests/test_harness_codex.py::test_no_codex_path_outside_the_adapter | yes |
| AC-2 | test-case | tools/adlc/tests/test_harness_codex.py::test_agent_render_restraint_and_ethos | yes |
| AC-3 | test-case | tools/adlc/tests/test_harness_codex.py::test_rules_render | yes |
| AC-4 | test-case | tools/adlc/tests/test_harness_codex.py::test_removing_a_declared_loss_fails_the_lint | no |
| AC-6 | test-case | tools/adlc/tests/test_harness_codex.py::test_hooks_render | yes |
| AC-7 | test-case | tools/adlc/tests/test_harness_codex.py::test_lane_check_blocks_the_codex_layer | yes |
| AC-13 | test-case | tools/adlc/tests/test_harness_codex.py::test_claude_golden_and_adapter_unmoved | yes |

## Technical Notes

ADR-1, ADR-2, ADR-3, ADR-4, ADR-9. Goldens by `adlc harness render --write-goldens`.
