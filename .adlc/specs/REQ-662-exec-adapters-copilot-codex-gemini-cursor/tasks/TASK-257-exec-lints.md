---
id: TASK-257
title: "The `exec-no-bypass` and `exit-class-vocabulary` lints"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-256]
---

## Description

Add the two lints BR-2 and BR-8 name. `exec-no-bypass` fails when a `launch` or `resume` template, or a rendered argv fixture, holds a `forbidden_flags` entry. `exit-class-vocabulary` holds every `exit_codes` value in every adapter to REQ-659's closed ExitClass set.

## Files to Create/Modify

- `tools/lint-skills/check.py` — `check_exec_no_bypass` and `check_exit_class_vocabulary`, registered in the per-root block beside `check_allowlist_fidelity`.
- `tools/lint-skills/README.md` — one paragraph per lint, beside `allowlist-fidelity`.
- `tools/lint-skills/tests/` — fixtures and tests for both lints.

## Acceptance Criteria

- [ ] A fixture template holding `--yolo`, `--force` or `--dangerously-skip-permissions` fails `exec-no-bypass`.
- [ ] A two-token violation (`--ask-for-approval never`), an `=`-spelled one (`--ask-for-approval=never`, `--approval-mode=yolo`) and a Codex `-c` override of a sandbox key each fail it. The matcher is `exec_adapter.forbidden_in`'s rule: a contiguous token subsequence after splitting `--flag=value` at the first `=`.
- [ ] The union of every `exec.launch` and `exec.resume` token across `harness/*.yml` shares nothing with the union of `forbidden_flags`.
- [ ] An `exit_codes` value outside `ok|denied|timeout|error` fails `exit-class-vocabulary`.
- [ ] Both lints pass on the repository as it stands (the must-not-fire case), and `bash tools/lint-skills/check.sh` is clean.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/lint-skills/tests/test_exec_lints.py::test_exec_no_bypass_fires_on_each_spelling` | yes |
| AC-2 | test-case | `tools/lint-skills/tests/test_exec_lints.py::test_exec_no_bypass_fires_on_each_spelling` | yes |
| BR-8 | test-case | `tools/lint-skills/tests/test_exec_lints.py::test_exit_class_vocabulary_is_closed` | yes |
| AC-12 | test-case | `tools/lint-skills/tests/test_exec_lints.py::test_both_lints_pass_on_the_tree` | yes |

## Technical Notes

- The lint is a backstop: the control is TASK-258's closed-world argv check (BR-16). Say so in the README paragraph and never cite the lint as the gate (LESSON-619).
- Reuse the engine's matcher by importing `exec_adapter` the way other checks import `tools/adlc` modules; do not write a second matcher.
- The check must report how many adapters it scanned and fail on zero, so a vacuous run is not a pass.
