---
id: TASK-238
title: "Regression-check engine and `adlc regression-check` subcommand"
status: draft
parent: REQ-691
created: 2026-11-04
updated: 2026-11-04
dependencies: []
repo: adlc-toolkit
---

## Description

Build `tools/adlc/regression_check.py`, the stdlib-only engine that reads the project's `bugfix.regression_test` setting and classifies bug reports, and register it as `adlc regression-check`. This is the one place every deterministic REQ-691 rule is decided (architecture ADR-691-A to ADR-691-D).

## Files to Create/Modify

- `tools/adlc/regression_check.py` — new. `mode` and `check` verbs, the output contract in architecture.md, `main(argv)` returning the rc.
- `tools/adlc/adlc.py` — add `_cmd_regression_check(argv)` (lazy import, as the other handlers) and a `regression-check` entry in `SUBCOMMANDS`.
- `tools/adlc/tests/test_regression_check.py` — new. Every case builds its repo, `.adlc/bugs/` and config in `tmp_path` (never in the toolkit tree: a fixture there would become a real BUG record).
- `tools/adlc/README.md` — a Subcommands-table row and a `regression_check.py` section after `lessons.py`.

## Acceptance Criteria

- [ ] `mode` returns `off` for a missing config, a config without the key, and a config whose only mention of the key is in a whole-line comment, without parsing in those cases.
- [ ] `mode` returns `required` / `off` for those values and rc 2, with a message naming the key, the value and the allowed values, for any other value, a non-mapping `bugfix`, an unknown key under `bugfix`, and a file `harness_yaml` refuses.
- [ ] `check` classifies passed, waived, legacy and every failed cause in BR-9, plus a duplicate key, a block-form list and an unclosed quote. It prints the verdict line, the counts line and one line per failure, with rc 0/1/2 as specified.
- [ ] `check BUG-nnn` checks that bug whatever its status, and fails an id with no report. `--require-recorded` turns legacy into failed.
- [ ] Path rules: an absolute path, a `..` segment, a symlink, an untracked file, and a file without the id each fail. `BUG-26` doesn't match a file citing only `BUG-261`.
- [ ] A `<repo-id>:` path resolves through `repos.<id>.path`, and a missing clone or undeclared id fails, naming it.
- [ ] The engine imports nothing outside the standard library and `tools/adlc`, and never calls `git fetch`, a remote ref or `git diff`.
- [ ] `python3 -m pytest tools/adlc/tests/test_regression_check.py` passes and collects at least one case per row below.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_regression_check.py::test_mode_values_and_absent_means_off` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_regression_check.py::test_waiver_needs_a_reason` | no |
| BR-7 | test-case | `tools/adlc/tests/test_regression_check.py::test_both_fields_set_fails` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_regression_check.py::test_classification_table` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_regression_check.py::test_exit_codes_and_counts` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_regression_check.py::test_off_reads_no_bug_report` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_regression_check.py::test_same_verdict_on_two_branches` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_regression_check.py::test_named_ids_and_require_recorded` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_regression_check.py::test_cross_repo_paths` | yes |
| BR-17 | test-case | `tools/adlc/tests/test_regression_check.py::test_unreadable_config_is_an_error_not_off` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_regression_check.py::test_classification_table` | no |
| AC-6 | test-case | `tools/adlc/tests/test_regression_check.py::test_benign_fixture_exits_zero` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_regression_check.py::test_empty_and_missing_bugs_dir` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_regression_check.py::test_off_reads_no_bug_report` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_regression_check.py::test_same_verdict_on_two_branches` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_regression_check.py::test_cross_repo_paths` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_regression_check.py::test_legacy_never_fails_unflagged` | yes |
| AC-15 | test-case | `tools/adlc/tests/test_regression_check.py::test_named_ids_and_require_recorded` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_regression_check.py::test_unreadable_config_is_an_error_not_off` | yes |

## Technical Notes

- Config: byte prefilter as `lane_check.may_carry_lanes` (skip whole-line comments; a NUL or backslash in the bytes forces a parse), then `harness_yaml.loads`. Read `repos:` from the same parse for ADR-691-D. Never fall back to `off` on an error.
- Frontmatter: own strict reader (ADR-691-B). Only `id`, `status`, `regression_tests` and `regression_waiver` are read; other keys are ignored, but a repeated key of any name fails, as the dataset recognizer would.
- Status scope for the unnamed run: `resolved` or `closed`, the set `/spec` Step 1.6 already uses.
- `git -C <repo> ls-files --error-unmatch -- <path>` for tracked; run git with a fixed argv, never through a shell.
- The AC-9 test creates two branches in a temp repo with identical `.adlc/bugs/` and tests, and a bare `origin` whose default branch differs. It asserts equal stdout. It never compares against the toolkit's own `origin/main` (LESSON-782).
- Output lines carry no home path and no file contents, only ids, repo-relative paths and reasons.
