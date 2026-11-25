---
id: TASK-280
title: "`cross_family.py`: skip decision, output validation, decline and disposition checks, PR section"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-278]
---
## Description

The stdlib-only core every engine calls. It owns each decision with a right answer:
whether the review runs and why not, which delegate lines become findings, whether a
decline qualifies, whether any cross-family finding lacks a disposition, and the PR body
section (architecture "`tools/delegate/cross_family.py`", ADR-4, ADR-5).

## Files to Create/Modify

- `tools/delegate/cross_family.py` — new: subcommands `decide`, `validate`, `check-decline`, `check-dispositions`, `pr-section`; `SKIP_REASONS` closed tuple; the fixed reviewer question text as a constant
- `tools/delegate/tests/test_cross_family.py` — new: one test class per subcommand

## Acceptance Criteria

- [ ] `decide` returns exactly one reason in the documented precedence order, and `run` only when no condition holds; every combination of the five inputs is covered by a parametrised test
- [ ] `validate` drops, and counts, a line citing `../etc/passwd`, a path outside the changed-files list, a line past the file's end, a severity outside `Critical|Major|Minor|Nit`, or a class failing the pattern shared with `FINDING_CLASS_PATTERN`
- [ ] `validate` exits 3 when the output is unparseable or every FINDING and RULE line is dropped, and ignores (does not count) non-grammar lines
- [ ] A `RULE` line marked `unmet` becomes a Major, must-fix `omitted-requirement` finding on the spec; `partial` becomes Minor; a rule id absent from the spec is dropped
- [ ] `check-decline` accepts a reason citing an existing tracked `path:line` or a listable `test:<id>`, and rejects one with no citation, a `..` path, or an out-of-range line
- [ ] `check-dispositions` exits 1 listing each undisposed or badly declined `cross-family` finding, and exits 0 on a state file with none (including a pre-REQ state file)
- [ ] `pr-section` output is byte-stable for a given state and names every repo, its status, reason and both families

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/delegate/tests/test_cross_family.py::TestDecide::test_equal_families_skip_same_family` | no |
| BR-3 | test-case | `tools/delegate/tests/test_cross_family.py::TestDecide::test_unknown_family_skips_family_unknown` | no |
| BR-4 | test-case | `tools/delegate/tests/test_cross_family.py::TestDecide::test_precedence_one_reason` | no |
| BR-4 | test-case | `tools/delegate/tests/test_cross_family.py::TestDecide::test_runs_when_nothing_skips` | yes |
| BR-6 | test-case | `tools/delegate/tests/test_cross_family.py::TestValidate::test_each_bad_field_dropped_and_counted` | yes |
| BR-6 | test-case | `tools/delegate/tests/test_cross_family.py::TestValidate::test_all_dropped_is_invalid_output` | no |
| BR-8 | test-case | `tools/delegate/tests/test_cross_family.py::TestCheckDecline::test_reason_needs_checkable_citation` | yes |
| BR-8 | test-case | `tools/delegate/tests/test_cross_family.py::TestCheckDispositions::test_undisposed_finding_fails` | yes |
| AC-4 | test-case | `tools/delegate/tests/test_cross_family.py::TestDecide::test_equal_families_skip_same_family` | no |
| AC-8 | test-case | `tools/delegate/tests/test_cross_family.py::TestValidate::test_each_bad_field_dropped_and_counted` | no |
| AC-9 | test-case | `tools/delegate/tests/test_cross_family.py::TestCheckDispositions::test_decline_without_reason_is_undisposed` | no |

## Technical Notes

- Read the class pattern from one place: assert in a test that it equals the JS `FINDING_CLASS_PATTERN` and Python `CLASS_RE` (`helpers.test.js:1082-1090` already pins those two).
- Path rules match the pre-pass: charset `^[A-Za-z0-9_./-]+$`, reject any `..` segment before the charset check (LESSON-008).
- Line range: count lines of the file in the worktree with `git -C <wt> show HEAD:<path>`, not the disk, so an uncommitted edit cannot widen the range.
- Free text (`title`, `note`, `declineReason`): cut to the pre-pass description charset `[A-Za-z0-9 .,:;()/_'"-]` and 200 chars. Constrained fields are validated, never redacted (LESSON-744).
- `test:<id>` listing: accept an injected lister in tests; in production, call the runner named by the repo's `.adlc/config.yml` `stack:`, and treat "cannot list" as not checkable (the citation fails).
