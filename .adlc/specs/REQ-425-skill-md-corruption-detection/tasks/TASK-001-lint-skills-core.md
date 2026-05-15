---
id: TASK-001
title: "Implement tools/lint-skills/ core (check.py, check.sh, sentinels.txt, README)"
status: complete
parent: REQ-425
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Create the `tools/lint-skills/` directory housing the three-check linter:
sentinel detector, shell-construct balance check, canonical-helper presence
check. Pure Python 3 stdlib; POSIX shell wrapper; offline.

## Files to Create/Modify

- `tools/lint-skills/check.py` — main script. ~200 LOC. Three pure check
  functions, a `find_skill_files()` walker, a CLI entry point.
- `tools/lint-skills/check.sh` — `exec python3 .../check.py "$@"` wrapper
  (one line of substance plus a shebang).
- `tools/lint-skills/sentinels.txt` — initial sentinel: the REQ-424
  corruption literal `20 20 12 61 80 33 98 100`. Comment header explaining
  the format.
- `tools/lint-skills/README.md` — usage + how to add a new sentinel.

## Acceptance Criteria

- [ ] `python3 tools/lint-skills/check.py` exits 0 on `main` (toolkit is
      clean post-REQ-424).
- [ ] `python3 tools/lint-skills/check.py --root /tmp/<fixture-dir>` works
      (--root flag honored).
- [ ] Sentinel check uses substring match (not regex) per BR-3.
- [ ] Balance check counts `$(` vs `)` AND `$((` vs `))` separately within
      each `sh`/`bash`/`shell` fence; outside-fence text ignored.
- [ ] Canonical-helper check fires only when the file contains the literal
      string `ADLC_DISABLE_KIMI`. Each of the 3 required literals
      (per ADR-3) is a separate finding when missing.
- [ ] Output format exactly: `<file>:<line>: <check-name>: <message>`.
      `<check-name>` is one of `sentinel`, `balance`, `canonical-helper`.
- [ ] Exit code 0 on clean, otherwise `min(num_findings, 255)`.
- [ ] `tools/lint-skills/check.sh` exists, is executable, and is a thin
      wrapper.
- [ ] No side effects: no temp files persisted, no log writes, no network.
- [ ] Recursive scan (`Path('.').rglob('SKILL.md')`) filtered to skip
      `.git/`, `.worktrees/`, `node_modules/` (ADR-4).

## Technical Notes

- Use `argparse` for `--root`; default to `.`.
- Read files as UTF-8 with `errors='replace'` to survive any oddball bytes.
- Fence detection: regex `^\s*```(sh|bash|shell)\b` opens, `^\s*```\s*$`
  closes. Track line number of the opening fence for finding output.
- Balance counter: iterate characters within each fence, counting `$((`
  (advance 3, increment `dollar_double`), then `$(` (advance 2, increment
  `dollar_single`), then `))` (advance 2, decrement `dollar_double`), then
  `)` (advance 1, decrement `dollar_single`). Report imbalance per fence.
  An end-state of `dollar_single != 0` OR `dollar_double != 0` is the
  finding.
- Canonical-helper literals are matched as raw substrings (BR-5: exact
  literals). Include a trailing space on `tools/kimi/emit-telemetry.sh `
  per the spec to defend against unintentional concatenation.
- Use `Path('.').rglob('SKILL.md')` then filter via parent-part inspection.
