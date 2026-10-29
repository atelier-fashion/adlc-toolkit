---
id: TASK-135
title: "Rewire machine-state callers onto ADLC_HOME: id-alloc, forge, doctor, forge_config, agents_render, delegate CLIs and installer, session-start hook"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-134]
repo: adlc-toolkit
---

## Description

Every partial, tool and hook that derives a machine-state path (architecture ADR-1) reads
it from the TASK-134 resolvers. Claude Code-owned paths and the two aliases stay literal.
`adlc doctor` refuses an invalid `ADLC_HOME` before running any check (AC-3).

## Files to Create/Modify

- `partials/id-alloc.sh` — counters, lock dirs, ledger and the pre-lock `mkdir` via `adlc_home`; sources `adlc-home.sh` with the guarded spelling
- `partials/forge.sh` — machine config via `adlc_machine_config`; venv via `adlc_home` in `_adlc_forge_python`
- `tools/adlc/checks.py` — `_adlc_home()` for counters, venv and machine config; `_claude_home()` kept for Claude Code's mounts
- `tools/adlc/doctor.py` — validate `ADLC_HOME` in `main` before the profile; exit 2 naming it
- `tools/adlc/forge_config.py` — no-loader fallback config path via `adlc_home`
- `tools/adlc/agents_render.py` — `_config_path` via `adlc_home.machine_config_path`
- `tools/delegate/_common.py` — the not-enabled message names the resolved config path
- `tools/delegate/install.sh` — venv, legacy venv and launchctl helpers under `ADLC_HOME`; `CLAUDE.md` and `settings.json` stay Claude Code's
- `tools/delegate/com.adlc-toolkit.delegate-setenv.plist.in` — the helper path is `__ADLC_HOME__/…`
- `scripts/session-start.sh` — config scaffold under `ADLC_HOME` (inline check naming the partial); the pointer stays at the alias
- `partials/tests/id-alloc.test.sh` — counter and ledger under an overridden home
- `partials/tests/forge.test.sh` — machine config read from `<adlc_home>/adlc/config.yml`
- `partials/tests/session-start.test.sh` — scaffold under an overridden home; invalid home writes no config
- `tools/adlc/tests/test_doctor.py` — AC-3 cases
- `tools/adlc/tests/test_checks.py` — counters and venv read from an overridden home

## Acceptance Criteria

- [ ] With `ADLC_HOME` unset every path is unchanged (existing suites pass untouched)
- [ ] With `ADLC_HOME=/x` id allocation writes `/x/.global-next-req`, forge reads `/x/adlc/config.yml`, the doctor reads `/x` counters and venv
- [ ] `ADLC_HOME=relative adlc doctor` and `ADLC_HOME= adlc doctor` exit 2 with a message naming `ADLC_HOME`
- [ ] The hook scaffolds `<adlc_home>/adlc/config.yml` and still writes the pointer to `~/.claude/adlc/plugin-root`
- [ ] The interpreter rule names `<adlc_home>/delegate-venv` at `checks.py` and `forge.sh` (the shim is TASK-136)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `partials/tests/id-alloc.test.sh::adlc_home_override` | yes |
| BR-1 | test-case | `partials/tests/forge.test.sh::machine_config_under_adlc_home` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_doctor.py::test_invalid_adlc_home_exits_naming_it` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_doctor.py::test_invalid_adlc_home_exits_naming_it` | yes |
| BR-11 | test-case | `partials/tests/run.sh` (four shells) | no |

## Technical Notes

- `adlc_id_kind_counter`/`_lockdir`/`adlc_id_own_ledger` propagate a resolver failure as a
  non-zero return; `adlc_alloc_id` already checks it (`|| return 2`).
- The in-lock `mkdir -p` becomes `mkdir -p "$(dirname "$LOCK")"`: no second resolution in
  the subshell.
- `forge.sh`: when `ADLC_CONFIG` is unset and the home is invalid, provider resolution fails
  loud (rc 2) with the resolver's message.
- Doctor validates before `build_profile`, so no check ever runs against an unresolvable home.
