---
id: TASK-172
title: "check-run-outcomes.sh: the Recurrence and harness-fidelity reader"
status: draft
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-170]
repo: adlc-toolkit
---

## Description

Add `tools/delegate/check-run-outcomes.sh`, a POSIX `sh` + `awk` reader of the
run-outcome log with two modes: `--recurrence --reqs …` (per-class `k` of `N`,
tiered, then `no-record` rows) and the default `--window <N>d` summary grouped
by `toolkit_version`, with the exit contract in architecture.md.

## Files to Create/Modify

- `tools/delegate/check-run-outcomes.sh` — new reader (mode 0755)
- `tools/delegate/tests/test_check_run_outcomes.py` — new fixture tests

## Acceptance Criteria

- [ ] Recurrence on a fixture where two of three REQs carry `LESSON-390` and one has no line prints `LESSON-390\t2\t3\tlesson`, then the unique classes with `1`, then `REQ-3\tno-record`
- [ ] Two REQs carrying `cross-fence-shell-state` print `cross-fence-shell-state\t2\t3\treviewer`; a legacy finding prints as `title-slug:…` with tier `title-slug`
- [ ] Only the latest line per REQ counts
- [ ] Summary mode: absent log → rc 0, no output; no line in window → `no runs in <N>d window`; corrupt log → rc 1; data → TSV grouped by `toolkit_version`
- [ ] Works under `sh` (dash where installed); no `jq`, no `mktemp -t`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-7 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_recurrence_lesson_tier_and_no_record` | no |
| BR-7 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_latest_line_per_req_wins` | yes |
| BR-8 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_summary_exit_contract` | yes |
| BR-2 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_recurrence_lesson_tier_and_no_record` | no |
| BR-2 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_latest_line_per_req_wins` (a resumed run's earlier `blocked` line is not counted once it reaches `merged`) | yes |
| AC-5 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_recurrence_lesson_tier_and_no_record` | no |
| AC-6 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_recurrence_reviewer_and_title_slug_tiers` | no |
| AC-9 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_summary_exit_contract` | yes |

## Technical Notes

- Parse each line in `awk` with `index()`/`substr()` on `"key":"`; every field the reader uses is regex-validated by the emitter and holds no `"`.
- Cutoff: BSD `date -u -r <epoch> +%Y-%m-%dT%H:%M:%SZ`, GNU `date -u -d @<epoch> …`; compare strings.
- Validate `--window` as digits with `case` before arithmetic (BR-10).
