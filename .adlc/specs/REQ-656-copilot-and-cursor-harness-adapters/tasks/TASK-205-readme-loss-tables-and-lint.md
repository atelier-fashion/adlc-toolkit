---
id: TASK-205
title: "README sections and the harness-loss-table lint"
status: complete
parent: REQ-656
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-204]
repo: adlc-toolkit
---

## Description

Per-harness README sections with install steps, the loss table and the declared residuals, held to the adapters by a lint.

## Files to Create/Modify

- `README.md`
- `tools/lint-skills/check.py` — `harness-loss-table`
- tools/lint-skills/tests/test_harness_loss_table.py
- `tools/lint-skills/README.md`

## Acceptance Criteria

- [ ] The lint passes on the real README and fails on each fixture AC-11 and AC-16 name

## Verification

| rule | kind | artifact | benign_path |
|---|---|---|---|
| BR-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py | yes |
| BR-17 | test-case | tools/lint-skills/tests/test_harness_loss_table.py | yes |
| AC-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py | yes |
| AC-16 | test-case | tools/lint-skills/tests/test_harness_loss_table.py | yes |

## Technical Notes

ADR-11. The facts come from the adapter and a fresh render, so the lint holds no copy of them.
