---
id: TASK-281
title: "Record the review at the event, keep dispositions through R3, and report counts"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-280]
---
## Description

Write `crossFamilyReview` to the primary-path state file at the moment the review runs or
skips, keep `source`, `disposition` and `declineReason` on findings through every R3
re-record, and carry the counts into the run-outcome record and the recurrence report
(BR-5, BR-8, BR-13).

## Files to Create/Modify

- `tools/delegate/run_outcome.py` — `record-cross-family` subcommand via `_update`; `normalize_findings` keeps `source`, `disposition`, `declineReason` (redacted); `record-verify` carries dispositions forward by dedupe key; optional `crossFamily` object appended to `KEYS`
- `tools/delegate/check-run-outcomes.sh` — a separate `Cross-family:` block after the table, printed only when a record has the object; the 14 columns unchanged
- `tools/adlc/sprint_exec.py` — `crossFamilyReview` joins `PRIMARY_OWNED`
- `proceed/phases-state.md` — document `crossFamilyReview` and the three finding fields beside `verify`
- `proceed/phases-telemetry.md` — R3 passes the new finding fields; R5 carries the cross-family object
- `tools/delegate/tests/test_run_outcome.py` — record-cross-family writes at once; reason vocabulary enforced; `KEYS` structural test updated
- `tools/delegate/tests/test_check_run_outcomes.py` — pre-REQ log output byte-identical; block appears with new records
- `partials/tests/run-outcome.test.sh` — pre-REQ compatibility case
- `tools/adlc/tests/test_sprint_exec.py` — close-out keeps `crossFamilyReview`

## Acceptance Criteria

- [ ] `record-cross-family` writes the repo's record in one atomic write, rejects a reason outside `SKIP_REASONS`, and requires `reason` exactly when `status` is `skipped`
- [ ] An R3 re-record that omits `disposition` does not erase a decline recorded earlier for the same dedupe key
- [ ] The run-outcome record carries the cross-family status, reason and finding, fix and decline counts, read from state, not from the model
- [ ] `check-run-outcomes.sh` on a pre-REQ log is byte-identical to its output before this task
- [ ] A close-out under the exec engine keeps the primary path's `crossFamilyReview`
- [ ] `/status` on a pre-REQ state file is unchanged (it reads optional keys with `.get()`)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/delegate/tests/test_run_outcome.py::test_record_cross_family_written_at_event` | no |
| BR-8 | test-case | `tools/delegate/tests/test_run_outcome.py::test_rerecord_keeps_decline` | no |
| BR-13 | test-case | `tools/delegate/tests/test_run_outcome.py::test_cross_family_counts_from_state` | no |
| BR-13 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_pre_req_log_output_unchanged` | yes |
| AC-13 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_cross_family_block_reports_counts` | no |
| AC-15 | test-case | `tools/delegate/tests/test_run_outcome.py::test_pre_req_state_reports_unchanged` | yes |

The close-out case lives in `tools/adlc/tests/test_exec_approve.py::test_a_carried_close_out_state_is_data`
(there is no `test_sprint_exec.py`; that file is where `PRIMARY_OWNED` is exercised).

Lessons: LESSON-744, LESSON-719, LESSON-729, LESSON-742, LESSON-906

## Technical Notes

- `cmd_record_verify` (`run_outcome.py:521-550`) replaces `verify.findings` wholesale; merge the prior list's `disposition`/`declineReason` by the same key `dedupeAndRank` uses (file + normalised title).
- `test_run_outcome.py:59-66` asserts `list(record) == list(RO.KEYS)`; append the new key last and update that test.
- Import `SKIP_REASONS` from `cross_family.py` by path; do not copy the tuple.
- Sole-writer note (LESSON-729): this task owns the state writer and `phases-state.md` documents it; TASK-283's skill text only calls it.
