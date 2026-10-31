---
id: TASK-214
title: "Skills, documentation and the Codex loss table"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-213]
repo: adlc-toolkit
---

## Description

Write the Codex README section from the gate record, hold it with `harness-loss-table`, and update the skills and context docs.

## Files to Create/Modify

- `README.md` — Codex section
- `init/SKILL.md` — Step 8 Codex text
- `template-drift/SKILL.md` — the Codex files
- `tools/lint-skills/check.py` — `LOSS_TABLE_HARNESSES`, Codex rows
- `tools/lint-skills/tests/test_harness_loss_table.py` — cases
- `tools/adlc/README.md` — rows and render target
- `.adlc/context/architecture.md` — the adapter as the single Codex authority
- `.adlc/context/conventions.md` — why the deny tier renders as `prompt`
- `CHANGELOG.md` — entry

## Acceptance Criteria

- [ ] `harness-loss-table` passes for codex and fails on a row that says "prompts" for a spelling not recorded so
- [ ] `/init` names the trust step and the per-hook review

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py::test_codex_section_holds | yes |
| BR-14 | structural-check | `tools/lint-skills`: harness-loss-table, render-parity | no |
| AC-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py::test_codex_section_holds | yes |
| AC-14 | structural-check | `tools/lint-skills`: harness-loss-table; the dogfood half is owed to the operator | no |

## Technical Notes

AC-14's dogfood is out of bounds for this run and stays unmet.
