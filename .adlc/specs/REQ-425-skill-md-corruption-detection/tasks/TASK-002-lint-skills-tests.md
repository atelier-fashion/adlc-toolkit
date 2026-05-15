---
id: TASK-002
title: "Write pytest cases for tools/lint-skills/"
status: draft
parent: REQ-425
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-001]
---

## Description

Add pytest coverage for the three check classes plus the CLI exit-code
contract. Synthetic SKILL.md fixtures cover clean, sentinel hit,
unbalanced parens, missing canonical helper, and a happy-path Kimi gate.

## Files to Create/Modify

- `tools/lint-skills/tests/__init__.py` — empty, makes pytest see it as a
  package and avoids name collision with `tools/kimi/tests/`.
- `tools/lint-skills/tests/test_check.py` — pytest cases.
- `tools/lint-skills/tests/fixtures/clean.md`
- `tools/lint-skills/tests/fixtures/corrupt-sentinel.md` — contains
  `20 20 12 61 80 33 98 100`.
- `tools/lint-skills/tests/fixtures/unbalanced-parens.md` — `sh` fence with
  `$(echo hello` (one `$(` no closing `)`).
- `tools/lint-skills/tests/fixtures/missing-canonical.md` — contains
  `ADLC_DISABLE_KIMI` but missing one or more required literals.
- `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` — contains
  `ADLC_DISABLE_KIMI` AND all 3 required literals (canonical happy path).

## Acceptance Criteria

- [ ] `pytest tools/lint-skills/tests/ -q` reports >= 5 tests, all passing.
- [ ] `pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` runs the
      combined suite cleanly (no module name collision).
- [ ] Each of BR-2/3/4/5/10 has at least one corresponding test:
      - sentinel-from-file (sentinels.txt loaded) — BR-2
      - sentinel hit reports correct `<file>:<line>` — BR-3
      - unbalanced parens reports balance finding with fence line — BR-4
      - missing canonical helper reports per-rule findings — BR-5
      - linter run against synthetic corrupt fixture exits non-zero — BR-10
- [ ] One additional test asserts the happy-path kimi-gate fixture is
      reported clean (proof the canonical rule doesn't false-positive).
- [ ] Tests invoke the linter via `subprocess.run([sys.executable,
      'tools/lint-skills/check.py', '--root', fixtures_dir])`, NOT by
      importing internals — exercises the CLI contract.

## Technical Notes

- Use `tmp_path` fixture from pytest where useful to assemble per-test
  fixture roots if a test needs an isolated set.
- The static fixtures under `fixtures/` are the "default" corpus that
  most tests scan; isolated tests can copy a single fixture into
  `tmp_path` to control what the linter sees.
- Parse the linter's stdout to assert specific check-name and file-name
  occur in the expected combinations. Avoid over-tight assertions on
  line numbers for the balance test (regex on `fence at line \d+`).
- Capture-and-assert exit code via `subprocess.CompletedProcess.returncode`.
