---
id: TASK-202
title: "Framework gaps: schema v2, formats, deny clash, printed scope"
status: complete
parent: REQ-656
created: 2026-10-30
updated: 2026-10-30
dependencies: []
repo: adlc-toolkit
---

## Description

Close the gaps REQ-657 could not see with one adapter: optional schema fields, the Copilot and Cursor formats, the deny-clash fix, the printed scope through fidelity, `.agent.md` copies, the `via:` line, goldens, drift and the doctor.

## Files to Create/Modify

- `tools/adlc/harness_adapter.py` — schema 2, `also`, `hook_output`, `fidelity_notes`, `fact`, formats
- `tools/adlc/harness_render.py` — formats, clash, withheld and first-token rules, printed scope, summary, parity, drift
- `tools/adlc/harness_cli.py` — `--write-goldens`, `--opted-in`, user-scope copies, report
- `tools/adlc/harness_doctor.py`, `tools/adlc/checks.py` — fact rows, deny_under_allow recompute
- `tools/adlc/agents_render.py` — suffix, `via:` line

## Acceptance Criteria

- [ ] `harness/claude.yml` still loads at version 1 and its goldens are byte-identical
- [ ] A field of schema 2 under version 1 is a loud error naming it

## Verification

| rule | kind | artifact | benign_path |
|---|---|---|---|
| BR-1 | test-case | tools/adlc/tests/test_harness_adapters.py::test_loader_rejects_a_missing_field | no |
| BR-9 | test-case | tools/adlc/tests/test_harness_adapters.py::test_cursor_agents_render_is_a_noop | yes |
| BR-10 | test-case | tools/adlc/tests/test_harness_adapters.py::test_doctor_rows_and_currency | yes |
| BR-15 | test-case | tools/adlc/tests/test_harness_adapters.py | no |
| AC-9 | test-case | tools/adlc/tests/test_harness_adapters.py::test_cursor_agents_render_is_a_noop | yes |
| AC-10 | test-case | tools/adlc/tests/test_harness_adapters.py::test_doctor_rows_and_currency | yes |

## Technical Notes

ADR-3, ADR-4, ADR-7, ADR-8, ADR-9, ADR-10, ADR-12, ADR-14. Nothing compares a harness name (`test_no_renderer_branches_on_a_harness_name`).
