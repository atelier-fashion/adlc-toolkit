---
id: TASK-216
title: "Teach detect and doctor that agy exists"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

Add `antigravity` to the detect table with its `skills-config` mount kind, so `harness:antigravity` joins doctor as report-only. `gemini` keeps its row unchanged.

## Files to Create/Modify

- `tools/adlc/harness.py` — the table row, `skills-config`, and the mount reader
- `tools/adlc/tests/test_harness.py` — six harnesses; present, absent, mounted
- `tools/adlc/tests/test_checks.py` — the doctor row

## Acceptance Criteria

- [ ] `adlc harness detect --json` lists `antigravity` present with a fake `agy`, absent without it
- [ ] `mount` reads `mounted` only when an `entries` path in the adapter's `skills.json` reaches this toolkit
- [ ] The `gemini` row is byte-identical to before, and doctor shows `harness:antigravity` report-only

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | tools/adlc/tests/test_harness.py::test_antigravity_present_and_absent | yes |
| AC-2 | test-case | tools/adlc/tests/test_harness.py::test_gemini_row_unchanged | yes |
| BR-2 | test-case | tools/adlc/tests/test_harness.py::test_skills_config_mount | yes |

## Technical Notes

The name appears only in the table (BR-5). The mount reader takes the path from the adapter, so it fails soft while the adapter does not exist yet.
