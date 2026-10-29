---
id: TASK-173
title: "adlc_lessons ack-check --record: write lessons.acknowledged"
status: complete
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Give `tools/adlc/lessons.py ack-check` a `--record` flag that writes the
acknowledged lesson ids it computed into `lessons.acknowledged` of the `--state`
file (atomic, merge-preserving), the deterministic source of RunOutcome's
`lessons_cited`. Document it in `partials/lessons.md`.

## Files to Create/Modify

- `tools/adlc/lessons.py` — `ack-check --record`; `write_acknowledged(path, ids, now)`
- `tools/adlc/tests/test_lessons.py` — record case and the no-flag benign case
- `partials/lessons.md` — the flag and the key

## Acceptance Criteria

- [ ] With `--record`, `lessons.acknowledged.ids` holds the sorted acknowledged ids and every other key survives
- [ ] Without `--record`, stdout and the state file are byte-identical to today
- [ ] `--record` without `--state` is a usage error (rc 2)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | test-case | `tools/adlc/tests/test_lessons.py::test_ack_check_record_writes_acknowledged` | no |
| BR-12 | test-case | `tools/adlc/tests/test_lessons.py::test_ack_check_without_record_leaves_state_alone` | yes |

## Technical Notes

- Reuse the atomic tempfile + `os.replace` from `write_state`; factor a small `_atomic_write_json(path, data)` both call.
