---
id: TASK-031
title: "tools/kimi/ telemetry helpers — emit-telemetry.sh, skill-flag.sh, check-delegation.sh + tests"
status: draft
parent: REQ-424
created: 2026-05-14
updated: 2026-05-14
dependencies: []
---

## Description

Three small POSIX shell helpers + a pytest fixture suite. All three helpers are
positional-arg-only (no flags), portable to macOS + Linux, and stdlib-only.

## Files to Create/Modify

### CREATE: `tools/kimi/emit-telemetry.sh`
Positional args: `<skill> <step> <req> <gate> <mode> <reason> <duration_ms>`. Composes
one JSON-line and appends to `~/Library/Logs/adlc-skill-telemetry.log` (or
`$ADLC_TELEMETRY_LOG` if set, for tests). Sets `umask 077` before first write. Emits the
9-key flat schema from ADR-3: timestamp (UTC ISO-8601), skill, step, req, gate, mode,
reason, duration_ms, repo (cwd basename). Each value sanitized through the REQ-415
5-pattern sed redaction (sk-, AKIA, ghp_, Bearer, [A-Z_]+_(API_KEY|TOKEN)) before JSON
composition. Quoting handled with naive double-quote-string-escape (`\"`); script does
not use `jq`.

### CREATE: `tools/kimi/skill-flag.sh`
Three commands via positional arg 1:
- `create` — prints a fresh `mktemp -t adlc-skill-flag.XXXXXX` path, creates the file
- `clear <path>` — `rm -f <path>` (idempotent)
- `check <path>` — exits 0 if path exists (flag still set → ghost-skip), exits 1 otherwise

### CREATE: `tools/kimi/check-delegation.sh`
Reads the log (or `$ADLC_TELEMETRY_LOG`). Default window: last 7 days (configurable via
`--window 30d` / `--window 1d` parsed as N days). Output: TSV with header row
`skill\tdelegated\tfallback\tghost_skip\ttotal`, then one row per distinct skill seen
in-window. Plus a footer line `TOTAL\t<sum>\t<sum>\t<sum>\t<sum>`. Exits 0 always (empty
log is valid → zero rows + footer with zeros).

### CREATE: `tools/kimi/tests/test_telemetry.py`
Pytest cases driving each helper via subprocess against a synthetic log file:
- emit + read back: one event of each `mode`, asserts JSON line shape (9 keys, no
  unescaped quotes in `reason`)
- flag create/check/clear lifecycle
- check-delegation.sh on fixture with 3 events (1 delegated, 1 fallback, 1 ghost-skip)
  → TSV has 1 skill row, totals match
- check-delegation.sh on empty log → header + zero footer
- check-delegation.sh respects `--window 1d` (entries older than 1 day excluded)
- emit-telemetry.sh redacts `sk-XXXXX` patterns in `reason` arg → JSON contains
  `[REDACTED]` not the literal

## Acceptance Criteria

- [ ] Three new sh files exist under `tools/kimi/`, all executable, `bash -n` passes on all.
- [ ] `emit-telemetry.sh` invoked with full positional args produces one valid JSON
      line in `$ADLC_TELEMETRY_LOG` (test mode).
- [ ] `skill-flag.sh create` returns a tmp path; the path exists; `skill-flag.sh check
      <path>` exits 0; `skill-flag.sh clear <path>` removes it; check exits 1 after.
- [ ] `check-delegation.sh` on a 3-event synthetic fixture produces TSV with the
      expected counts (1/1/1, total=3).
- [ ] `pytest tools/kimi/tests/test_telemetry.py -q` reports all tests passing — at
      minimum the 6 cases above.
- [ ] No helper script touches `~/.zshrc`, `~/.claude/CLAUDE.md`, or `~/.claude/settings.json`.
- [ ] `~/Library/Logs/adlc-skill-telemetry.log` is created with mode 600 on first write
      (verified by `stat -f '%Lp'` on macOS or equivalent in the test).
- [ ] No script contains `eval` or `source`. No `jq` dependency. No GNU-only flags.
- [ ] REQ-413's existing pytest suite still reports 36/36 passing — the new
      `test_telemetry.py` brings the total to 42+.

## Technical Notes

- The redaction sed in `emit-telemetry.sh` reuses the exact 5-pattern chain from REQ-415's
  `wrapup/SKILL.md`. Copy verbatim, not approximate.
- For the test suite, use `$ADLC_TELEMETRY_LOG` override pointing to `tmp_path / "telemetry.log"`.
  Never write to the real log file from tests.
- `check-delegation.sh`'s window filter: parse timestamps with `date -d` (GNU) or
  `date -j -f` (BSD/macOS). Helper function chooses based on `uname` or first-availability
  check. POSIX-compliant.
- Use `mktemp -t adlc-skill-flag.XXXXXX` — note the `.XXXXXX` template (six X's) for both
  macOS and Linux compatibility.
- All three helpers shipped under `tools/kimi/` — invoked by SKILL.md prose via their
  full path. No new entries to `~/bin/`.
