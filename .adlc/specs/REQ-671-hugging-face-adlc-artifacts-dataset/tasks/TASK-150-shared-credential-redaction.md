---
id: TASK-150
title: "Shared credential redaction module pinned to both shell chains"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: []
---

## Description

Add `tools/adlc/credential_redact.py`, the one Python home for the credential pattern
chains (architecture ADR-3). The dataset scrub uses it for BR-3(a), and REQ-670's Space
uses it for its own BR-7 instead of writing a second copy.

## Files to Create/Modify

- `tools/adlc/credential_redact.py` — `INTAKE_PATTERN`, `WIDE_PATTERN`, `REPLACEMENT = "[REDACTED]"`, `redact(text, patterns=(INTAKE_PATTERN,)) -> (text, count)`, `find(text, patterns) -> bool` (detection only)
- `tools/adlc/tests/test_credential_redact.py` — parity and differential tests

## Acceptance Criteria

- [ ] `INTAKE_PATTERN.pattern` equals the regex inside `partials/intake.sh`'s `adlc_intake_redact` sed line after `[[:space:]]` is translated to `\s`; the test reads the shell file, it does not carry a copy.
- [ ] `WIDE_PATTERN.pattern` equals `_alc_cred` from `partials/lesson-check.sh` under the same translation.
- [ ] A differential test runs the real `adlc_intake_redact` (sourced from `partials/intake.sh` under `sh`) over a sample corpus of positive and negative lines and gets byte-identical output to `redact(..., (INTAKE_PATTERN,))`.
- [ ] `redact` counts each replacement; prose that only names a variable (`GITHUB_TOKEN was unset`) is unchanged under `WIDE_PATTERN`.
- [ ] Stdlib only, Python 3.9; no literal `skills` path string (the `test_toolkit_root.py` scan).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_credential_redact.py::test_intake_pattern_matches_shell_chain` | no |
| BR-3 | test-case | `tools/adlc/tests/test_credential_redact.py::test_differential_against_adlc_intake_redact` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_credential_redact.py::test_module_is_stdlib_only` | no |

## Technical Notes

Extract the shell regex with a Python regex over the file text (the sed `s/(…)/[REDACTED]/g`
argument and the `_alc_cred='…'` assignment), so the test fails loudly, naming the file,
if either line moves. Translate only `[[:space:]]`; any other POSIX class appearing later
should fail the test rather than be silently mistranslated. The `sed -E` alternation is
leftmost-longest while Python's is leftmost-first: the differential corpus must include a
line where two arms overlap (`MOONSHOT_API_KEY=sk-…`) to prove the outputs still agree.
