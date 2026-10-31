---
id: TASK-215
title: "Probe scrubber: a bare username and account ids"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

The committed `codex.json` needed a by-hand redaction of the login name from an `ls -l` line, and the transcript fixture of two account ids. Both belong in the tool that writes them.

## Files to Create/Modify

- `tools/adlc/harness_probe.py` — `scrub`
- `tools/adlc/tests/test_harness_probe_unit.py` — cases

## Acceptance Criteria

- [ ] A bare login name and `creator_*_id` values are redacted; a word containing the name is not

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | test-case | tools/adlc/tests/test_harness_probe_unit.py::test_scrub_takes_the_login_name_and_account_ids | yes |

## Technical Notes

A REQ-664 finding, fixed here because the fix is small and this REQ's evidence found it.
