---
id: TASK-170
title: "run_outcome.py: the deterministic RunOutcome emitter and the pipeline-state record writers"
status: draft
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Add `tools/delegate/run_outcome.py`, a stdlib-only Python module that derives a
flat RunOutcome JSON line from a primary-path `pipeline-state.json`, and the
`record-*` subcommands that write the additive state keys (`harness`,
`validateAttempts`, `verify`, `lessonsWritten`). See architecture.md
"`tools/delegate/run_outcome.py`" for the subcommand contract and the field
derivation table.

## Files to Create/Modify

- `tools/delegate/run_outcome.py` — new: `emit`, `record-harness`, `record-validate`, `record-verify`, `record-lessons-written`; pure helpers `normalize_severity`, `finding_class`, `class_tier`, `title_slug`, `redact`, `normalize_blocked_reason`, `validate_retries`, `build_record`
- `tools/delegate/tests/test_run_outcome.py` — new: structural test of an emitted line, derivation, tolerance of absent keys, class tiers and redaction survival, redaction parity with `emit-telemetry.sh`'s `sed` chain, record writers (atomic, merge-preserving, monotone)

## Acceptance Criteria

- [ ] `emit` prints exactly one line that `json.loads` to a dict with every documented key, every value a string, no nested object or array; counts are quoted decimals or `-`; enums in vocabulary
- [ ] A state with none of `harness`, `validateAttempts`, `verify`, `lessons.acknowledged`, `lessonsWritten` emits `-`/`0` for the derived fields, rc 0
- [ ] `validate_retries` is `"2"` for `phase1: 3` with no `phase3`; non-integer attempts count 0
- [ ] A finding classed `task-ordering-race-in-fixture` keeps that exact slug in `finding_classes`; a `ghp_` + 36-char value in `repo` or `toolkit_version` is written `[REDACTED]`
- [ ] The Python chain and `emit-telemetry.sh`'s `sed` chain produce identical output on a fixture of credential-shaped strings
- [ ] `record-harness` keeps an existing `harness`; `record-validate` is monotone; `record-verify` normalises severity (High→Major, Medium→Minor, Low→Nit) and class (lessonId > reviewer class > title-slug) and sets `fixed` booleans; every record write preserves every other key and is atomic
- [ ] `normalize_blocked_reason` maps the workflow's reasons onto the closed enum; a merged terminal with `closeOut.status: failed` gets `close-out-failed`
- [ ] `pytest tools/delegate/tests/test_run_outcome.py` collects > 0 and passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/delegate/tests/test_run_outcome.py::test_emitted_line_is_flat_and_complete` | no |
| BR-1 | test-case | `tools/delegate/tests/test_run_outcome.py::test_redaction_parity_with_emit_telemetry_sed_chain` | no |
| BR-5 | test-case | `tools/delegate/tests/test_run_outcome.py::test_normalize_blocked_reason_maps_workflow_reasons` | no |
| BR-6 | test-case | `tools/delegate/tests/test_run_outcome.py::test_finding_class_tiers` | no |
| BR-9 | test-case | `tools/delegate/tests/test_run_outcome.py::test_emitted_line_is_flat_and_complete` | no |
| BR-10 | test-case | `tools/delegate/tests/test_run_outcome.py::test_record_harness_written_once` | yes |
| BR-4 | test-case | `tools/delegate/tests/test_run_outcome.py::test_record_verify_normalises_and_marks_fixed` | yes |
| AC-1 | test-case | `tools/delegate/tests/test_run_outcome.py::test_toolkit_sha_comes_from_state_not_disk` | no |
| AC-2 | test-case | `tools/delegate/tests/test_run_outcome.py::test_validation_exhausted_line` | yes |
| AC-3 | test-case | `tools/delegate/tests/test_run_outcome.py::test_record_verify_normalises_and_marks_fixed` | no |
| AC-4 | test-case | `tools/delegate/tests/test_run_outcome.py::test_absent_keys_emit_dash_and_zero` | yes |
| AC-8 | test-case | `tools/delegate/tests/test_run_outcome.py::test_class_slug_survives_redaction` | no |
| AC-11 | test-case | `tools/delegate/tests/test_run_outcome.py::test_free_text_credential_is_redacted` | no |

## Technical Notes

- Stdlib only; runs under the system `python3` (the plugin route has no venv).
- Atomic write: `tempfile.NamedTemporaryFile(dir=<state dir>, delete=False)` + `os.replace`, as `tools/adlc/lessons.py::write_state`.
- Class regex: `^([a-z0-9]+(-[a-z0-9]+){0,5}|LESSON-[0-9]{3,6}|title-slug:[a-z0-9-]+)$`. The reviewer tier alone is `^[a-z0-9]+(-[a-z0-9]+){0,5}$`; `title_slug` lowercases, maps runs of non-`[a-z0-9]` to `-`, trims, caps at 6 words.
- Every numeric read is `int()`-guarded (BR-10, LESSON-441).
- The parity test reads the `sed -E 's/…/[REDACTED]/g'` expression out of `emit-telemetry.sh` and runs it through `sed`; it does not retype the regex.
