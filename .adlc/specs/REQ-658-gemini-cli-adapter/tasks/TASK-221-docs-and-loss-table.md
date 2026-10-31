---
id: TASK-221
title: "README section, loss table and the rest of BR-14"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-219, TASK-220]
repo: adlc-toolkit
---

## Description

Write the Antigravity CLI section and hold it to the adapter, then update the other documents. Fill in `## Deferred`.

## Files to Create/Modify

- `README.md` — the section
- `tools/lint-skills/check.py` — `LOSS_TABLE_HARNESSES`, this harness's rows, and the printed-JSON deny wording
- `tools/lint-skills/tests/` — the agreement test
- `.adlc/context/architecture.md`, `tools/adlc/README.md`, `CHANGELOG.md` — the new surfaces
- `.adlc/specs/REQ-662-exec-adapters-copilot-codex-gemini-cursor/requirement.md` — what its block must read
- `.adlc/specs/REQ-658-gemini-cli-adapter/requirement.md` — `## Deferred`

## Acceptance Criteria

- [ ] The section carries every BR-11 item, and removing one loss sentence or one `unsupported` fact fails the test
- [ ] It says the toolkit has no Gemini CLI adapter and why, and that `gemini-extension.json` does not exist
- [ ] `## Deferred` lists every `unverified` row and every owed step

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py::test_antigravity_section | yes |
| AC-11 | test-case | tools/lint-skills/tests/test_harness_loss_table.py::test_antigravity_section | yes |
| BR-14 | structural-check | tools/lint-skills: harness-loss-table, manifest-parity | no |
| AC-14 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_documents_name_the_surfaces | no |
| BR-15 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_deferred_lists_every_unverified_row | no |
| AC-15 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_deferred_lists_every_unverified_row | no |
| AC-13 | structural-check | sh partials/tests/run.sh; sh tools/lint-skills/check.sh | no |

## Technical Notes

The README states what is lost without weakening it (BR-11). Nine skills over 24,000 bytes are named, computed in a test rather than copied by hand.
