---
id: TASK-230
title: "The pointer step in every home resolver"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

Add `$ADLC_HOME`, else the pointer, else `$HOME/.claude` to all five sites, with the conflict and bad-pointer errors of ADR-2, and name the default through one helper.

## Files to Create/Modify

- `partials/adlc-home.sh` — `adlc_default_home`, the pointer read, the conflict error, `adlc_home_source` gains `pointer`
- `tools/adlc/adlc_home.py` — the same rule, `default_home`, `pointer_path`, `pointer_error`
- `tools/delegate/_machine_config.py` — the third copy of the rule
- `scripts/session-start.sh` — the inlined rule reads the pointer
- `tools/adlc/tests/test_adlc_home.py` — the parity vector gains a pointer column
- `partials/tests/adlc-home.test.sh` — pointer, conflict, dangling and symlinked-pointer cases
- `partials/tests/session-start.test.sh` — the config lands under the pointer's home

## Acceptance Criteria

- [ ] With no pointer every existing vector answer is unchanged
- [ ] A pointer resolves with `ADLC_HOME` unset; a set `ADLC_HOME` equal to it resolves; a different one is an error naming both
- [ ] A pointer that is a symlink, empty, relative or names a missing directory is an error naming the pointer

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | tools/adlc/tests/test_adlc_home.py::test_parity_vector | yes |
| BR-8 | test-case | partials/tests/adlc-home.test.sh::pointer_cases | yes |
| BR-13 | test-case | partials/tests/run.sh under bash, zsh, /bin/sh and dash | yes |

## Technical Notes

Keep the partial POSIX and `set -u` safe: `${HOME:-}`, prefixed globals, no `case` inside `$( )`. `read` returns non-zero on a line with no newline and still sets the variable, so end it with `|| :`. The pointer read is skipped when HOME is not absolute, so `ADLC_HOME=/x` with HOME unset behaves as it did.
