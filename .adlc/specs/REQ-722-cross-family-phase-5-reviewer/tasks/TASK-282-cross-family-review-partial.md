---
id: TASK-282
title: "`partials/cross-family-review.sh`: gate, redact, call, validate, record"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-279, TASK-280, TASK-281]
---
## Description

The sourced shell partial that runs one repo's review end to end, in the step order the
architecture fixes, with every decision delegated to the Python from TASK-278 to TASK-281.
Its test harness stubs `adlc-read` and counts calls.

## Files to Create/Modify

- `partials/cross-family-review.sh` — new: `adlc_cross_family_review <repo> <worktree> <base> <spec> <state>`; `mktemp -t adlc-xfam.XXXXXX` + `EXIT` trap; five-arm `sed` redaction, fail closed; call spelled with `$CORPUS`; one stderr line per skip; prints the findings block
- `partials/cross-family-review.md` — new: companion doc in the style of `partials/delegate-gate.md`
- `partials/tests/cross-family-review.test.sh` — new: stub `adlc-read` on `PATH` recording calls (pattern of `delegate-gate.test.sh:53-78`)
- `partials/tests/run.sh` — one `run_all` line for the new harness (LESSON-738)
- `partials/README.md` — index entry
- `tools/delegate/tests/test_redaction_parity.py` — the partial's chain against `credential_redact.py` `INTAKE_PATTERN` (ASSUME-009)
- `tools/adlc/exec_safety.py` — `INSTALL_FILES` gains `partials/cross-family-review.sh`, `tools/delegate/cross_family.py` and `tools/delegate/model_family.py`, so the exec engine's tamper check covers what the review runs (raised by TASK-281)
- `tools/delegate/run_outcome.py` — `normalize_findings` keeps an integer `line`, so the PR section and `check-dispositions` can name it (raised by TASK-281)

## Acceptance Criteria

- [ ] Authorized, `anthropic` vs `moonshot`, stub returning one valid finding: one call, record `ran`, findings block holds it with `source: ["cross-family"]`
- [ ] Equal families: record `same-family`, one stderr line, zero calls
- [ ] No `family` key: record `family-unknown`, zero calls
- [ ] `ADLC_DISABLE_DELEGATE=1`: record `delegation-disabled`, zero calls, asserted from the stub's call log
- [ ] Forced redaction failure: record `redaction-failed`, zero calls, and the temp file is gone after return
- [ ] Stub exit non-zero: `api-error`; stub output all invalid: `invalid-output`
- [ ] No case returns non-zero to the caller, and no case leaves a temp file behind
- [ ] The partial is BSD- and zsh-safe (runs under `sh` and `zsh` in the harness) and passes `tools/lint-skills`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | `partials/tests/cross-family-review.test.sh::skip_never_fails_caller` | yes |
| BR-5 | test-case | `partials/tests/cross-family-review.test.sh::skip_prints_one_stderr_line_and_records` | no |
| BR-6 | test-case | `partials/tests/cross-family-review.test.sh::invalid_output_recorded` | no |
| BR-9 | test-case | `partials/tests/cross-family-review.test.sh::disable_env_zero_calls` | no |
| BR-9 | test-case | `tools/delegate/tests/test_redaction_parity.py::test_partial_chain_matches_intake_pattern` | yes |
| BR-15 | test-case | `partials/tests/cross-family-review.test.sh::runs_under_sh_and_zsh` | no |
| AC-1 | test-case | `partials/tests/cross-family-review.test.sh::authorized_cross_family_runs` | yes |
| AC-4 | test-case | `partials/tests/cross-family-review.test.sh::same_family_zero_calls` | no |
| AC-5 | test-case | `partials/tests/cross-family-review.test.sh::no_family_key_zero_calls` | no |
| AC-6 | test-case | `partials/tests/cross-family-review.test.sh::disable_env_zero_calls` | no |
| AC-7 | test-case | `partials/tests/cross-family-review.test.sh::redaction_failure_never_sent` | no |
| AC-8 | test-case | `partials/tests/cross-family-review.test.sh::invalid_output_recorded` | no |

Lessons: LESSON-008, LESSON-441, LESSON-743, LESSON-744, LESSON-742 — LESSON-008: post-validated output in a delimited block, mktemp + EXIT trap, one stderr line written after the record; LESSON-441: a full-path `mktemp "$TMPDIR/adlc-xfam.XXXXXX"` template instead of `mktemp -t`; LESSON-743: `<worktree>/.git` is tested before any `git -C`; LESSON-744: the parity test pins the chain's over-match of a kebab id in both engines; LESSON-742: the full `partials/tests/run.sh` ran on the final tree.

## Technical Notes

- Spell the call `"$ADLC_READ_BIN" --no-warn --paths "$CORPUS" --question ...`; `partials/tests/redact-fence.test.sh:61-72` must keep finding exactly one fence with the `$TMPFILE` spelling.
- Source `partials/delegate-gate.sh` and `partials/delegate-tools-path.sh` inside the function's file, from `$ADLC_TOOLKIT_ROOT` only (LESSON-718). Never from `.adlc/partials` in the worktree under review.
- The Bash tool is zsh: keep only paths in variables, quote every expansion, no word splitting (memory: bash-tool-is-zsh).
- Diff base is `origin/<integrationBranch>` passed in by the caller (LESSON-391), never `main`.
