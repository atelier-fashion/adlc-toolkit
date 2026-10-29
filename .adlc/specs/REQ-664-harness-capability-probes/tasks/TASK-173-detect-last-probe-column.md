---
id: TASK-173
title: "adlc harness detect: last_probe column"
status: complete
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171]
repo: adlc-toolkit
---

## Description

Extend REQ-654's `adlc harness detect` (BR-13, ADR-13): a `last_probe` column per
harness (the result file's `date`, `never`, or `unreadable`) and `last_probe` and
`probe_file` in `--json`. Read-only; never fails the command; `never` outside a
git repo.

## Files to Create/Modify

- `tools/adlc/harness.py` — `last_probe` lookup, table column, JSON keys
- `tools/adlc/tests/test_harness.py` — JSON key set gains the two keys; AC-11 cases

## Acceptance Criteria

- [ ] a sandbox repo with `codex.json` dated `2026-10-27` shows `2026-10-27` on codex and `never` elsewhere
- [ ] a file holding `{` shows `unreadable`; outside a repo every row is `never`
- [ ] `--json` carries `last_probe` and `probe_file`; exit 0 in every case

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/adlc/tests/test_harness.py::test_last_probe_column` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_harness.py::test_last_probe_column` | yes |

## Technical Notes

Resolve the repo root with `git rev-parse --show-toplevel` from the cwd under a
short timeout; any failure is `never`.
