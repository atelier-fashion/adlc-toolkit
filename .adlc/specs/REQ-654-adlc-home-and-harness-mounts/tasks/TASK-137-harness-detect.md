---
id: TASK-137
title: "`adlc harness detect` and the five harness:<name> report-only doctor checks"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-134]
repo: adlc-toolkit
---

## Description

A pure-stdlib probe table for the five harnesses (ADR-7), a read-only `adlc harness detect`
subcommand with `--json`, and five `harness:<name>` doctor checks replacing `claude-code`.

## Files to Create/Modify

- `tools/adlc/harness.py` — new: `HARNESSES`, `probe(name)`, `probe_all()`, `main(argv)`
- `tools/adlc/adlc.py` — register `harness` in `SUBCOMMANDS`
- `tools/adlc/checks.py` — replace `check_claude_code` with `harness:<name>` checks built from the table
- `tools/adlc/tests/test_harness.py` — new: AC-6 (only `claude`, a hanging `codex`, `--json` round-trip, exit 0)
- `tools/adlc/tests/test_checks.py` — remove the `claude-code` cases; harness checks SKIP when absent, PASS when present

## Acceptance Criteria

- [ ] With only `claude` on PATH: five rows, `claude` present with a version and `mounted` (sandbox mount), four `absent` / `n/a`, exit 0
- [ ] `--json` output parses with `python3 -m json.tool` and has one object per harness
- [ ] A fake `codex` that hangs on `--version` reports `present` / `unknown` within the timeout, exit still 0
- [ ] `harness:<name>` checks never FAIL; absent binaries SKIP

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-7 | test-case | `tools/adlc/tests/test_harness.py::test_only_claude_on_path` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_harness.py::test_hanging_version_is_unknown` | no |
| BR-9 | test-case | `tools/adlc/tests/test_checks.py::test_harness_checks_skip_when_absent` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_harness.py::test_json_round_trips` | yes |

## Technical Notes

- Version probe: `subprocess.Popen([...,'--version'], stdin=DEVNULL, start_new_session=True)`,
  `communicate(timeout=3)`, on timeout `os.killpg` then reap. Strip control characters.
- `mount` for Claude reuses `checks._symlink_install()`'s tree test and
  `doctor.detect_plugin_install()`; never raises (a failure is `not-mounted`).
- `--checks claude-code` becomes an unknown id; the CHANGELOG says so.
