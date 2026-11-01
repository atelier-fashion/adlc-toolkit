---
id: TASK-231
title: "Split consumer-sync into a report and a formatter"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

Separate gathering from formatting in `check_consumer_sync`, with its output unchanged, so the migration gate can read which consumers have a stale partial.

## Files to Create/Modify

- `tools/adlc/checks.py` — `consumer_sync_report` and a formatter
- `tools/adlc/tests/test_checks_home.py` — the report's shape, and every existing result still byte-identical

## Acceptance Criteria

- [ ] Every existing `consumer-sync` test passes unchanged
- [ ] The report separates stale partials from a stale project layer, archived repos and unknown archive state

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | tools/adlc/tests/test_checks_home.py::test_consumer_sync_report_separates_partials_from_layers | yes |

## Technical Notes

No new behaviour here. `check_consumer_sync` stays the only formatter, so doctor's text cannot move.
