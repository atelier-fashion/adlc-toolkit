---
id: TASK-134
title: "ADLC_HOME resolvers: partials/adlc-home.sh, tools/adlc/adlc_home.py, the _machine_config mirror, and their parity test"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Implement the one home-resolution rule (architecture ADR-2) three times — shell, the
`tools/adlc` Python module, the self-contained `tools/delegate` mirror — and prove the three
agree. Keep the runner's own `ADLC_HOME` out of every test harness.

## Files to Create/Modify

- `partials/adlc-home.sh` — new: `adlc_home`, `adlc_home_source`, `adlc_machine_config`
- `tools/adlc/adlc_home.py` — new: `adlc_home()`, `adlc_home_source()`, `machine_config_path()`, `AdlcHomeError`
- `tools/delegate/_machine_config.py` — `adlc_home()` mirror; `default_config_path()` built on it; `load_machine_config` maps an invalid home to `malformed`
- `partials/tests/adlc-home.test.sh` — new harness: default, override, empty, relative, `set -u` with HOME unset, ADLC_CONFIG precedence
- `partials/tests/run.sh` — register the harness; unset `ADLC_HOME` and `ADLC_CONFIG` for every harness
- `tools/adlc/tests/test_adlc_home.py` — new: cross-layer parity over one vector; stale-vendored-copy cases (AC-11)
- `tools/adlc/tests/conftest.py` — autouse fixture also removes `ADLC_HOME`, `ADLC_CONFIG`, `ADLC_REPOS_ROOT`
- `tools/delegate/tests/test_machine_config_home.py` — new: mirror unit cases and the malformed mapping
- `tools/delegate/_common.py` — `parse_delegate_config` lets the loader resolve the default path; refusal messages name the resolved path (`_config_path_label`)
- `tools/delegate/tests/conftest.py`, `tools/delegate/tests/test_machine_config.py` — scrub `ADLC_HOME`; `home-invalid` joins the not-from-a-file classes

## Acceptance Criteria

- [ ] Unset `ADLC_HOME` resolves to `$HOME/.claude` byte-for-byte in all three resolvers
- [ ] Empty and non-absolute `ADLC_HOME` are errors naming `ADLC_HOME` in all three; none falls through
- [ ] `ADLC_CONFIG` outranks `<adlc_home>/adlc/config.yml` and short-circuits an invalid home for the config path
- [ ] The parity test drives the shell partial, `adlc_home.py` and the mirror over the same vector and asserts identical results
- [ ] `sh partials/tests/run.sh` passes under bash, zsh, `/bin/sh` and dash with the new harness
- [ ] A pre-REQ vendored `id-alloc.sh` sourced through a fence under `/bin/sh` and zsh still resolves its counter (AC-11)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_adlc_home.py::test_parity_vector` | yes |
| BR-2 | test-case | `partials/tests/adlc-home.test.sh::rejects_empty_and_relative` | yes |
| BR-11 | test-case | `partials/tests/run.sh` (bash, zsh, /bin/sh, dash) | no |
| AC-3 | test-case | `tools/adlc/tests/test_adlc_home.py::test_rejects_invalid_home` | yes |
| AC-10 | test-case | `partials/tests/run.sh` with `adlc-home.test.sh` | no |
| AC-11 | test-case | `tools/adlc/tests/test_adlc_home.py::test_stale_vendored_partial_still_works` | yes |

## Technical Notes

- Shell: `${ADLC_HOME+x}` distinguishes unset from empty and is `set -u` safe. No `local`,
  no `case` in `$( )`, prefixed globals (`adlc_ah_*`).
- With `ADLC_HOME` unset and `HOME` not absolute, the shell resolver errors naming `HOME`
  (the lane-check posture); Python keeps `os.path.expanduser("~")`, today's spelling.
- `_machine_config` must not import `tools/adlc`; its header names the other two sites.
- The AC-11 case reads the pre-REQ partial with `git show 3206532:partials/id-alloc.sh` (this
  branch's base) and skips when that commit is unavailable (a shallow clone).
