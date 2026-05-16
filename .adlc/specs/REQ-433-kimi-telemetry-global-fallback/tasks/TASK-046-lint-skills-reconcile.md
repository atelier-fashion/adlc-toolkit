---
id: TASK-046
title: "Reconcile the REQ-425 lint-skills linter, tests, fixtures, and docs"
status: complete
parent: REQ-433
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-043, TASK-044]
repo: adlc-toolkit
---

## Description

Update the REQ-425 SKILL.md-corruption linter so its `CANONICAL_LITERALS` track
REQ-433's new canonical telemetry shape, and add the resolver-source line as a
new required literal so corruption that strips it is caught (ADR-3). Cascade the
change to the linter's tests, fixtures, and README so the suite stays green and
the anti-corruption guarantee is strengthened, not merely preserved.

## Files to Create/Modify

- `tools/lint-skills/check.py` — in `CANONICAL_LITERALS`: replace `"tools/kimi/emit-telemetry.sh "` with `'"$KIMI_TOOLS"/emit-telemetry.sh '`; add a 5th entry: the exact resolver-source line `'. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh'`.
- `tools/lint-skills/tests/test_check.py` — `test_missing_canonical_reports_per_rule`: bump `count("canonical-helper") == 4` → `== 5`, update the emit-literal assertion string, add an assertion for the new resolver-source literal; ensure `test_kimi_gate_happy_path_is_clean` still asserts zero findings.
- `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` — update to the new canonical-good shape: include the resolver-source line AND `"$KIMI_TOOLS"/emit-telemetry.sh …` so it contains all 5 literals and stays clean.
- `tools/lint-skills/tests/fixtures/missing-canonical.md` — verify it still contains the gate anchor (`ADLC_DISABLE_KIMI`) but **none** of the 5 literals (so the 5-finding assertion holds). Adjust only if it currently contains one of the new literal substrings.
- `tools/lint-skills/README.md` — update the documented canonical-literal list (the `tools/kimi/emit-telemetry.sh ` line and its "trailing space" note) to the new pair.

## Acceptance Criteria

- [ ] `CANONICAL_LITERALS` contains the new emit literal `'"$KIMI_TOOLS"/emit-telemetry.sh '` (trailing space) and the resolver-source literal; the old `"tools/kimi/emit-telemetry.sh "` entry is gone.
- [ ] The resolver-source literal in `check.py` is **byte-identical** to the line TASK-044 inserted into the skills (copy, don't retype).
- [ ] `pytest tools/lint-skills/tests/ -q` passes fully.
- [ ] Running the linter (`tools/lint-skills/check.py` / `check.sh`) over the 4 edited skills produces **zero** `canonical-helper` findings (AC-5) — i.e. REQ-433's own `/analyze` Step 1.9 would pass.
- [ ] `kimi-gate-ok.md` → 0 findings; `missing-canonical.md` → exactly 5 `canonical-helper` findings.
- [ ] README canonical-literal documentation matches `CANONICAL_LITERALS` exactly.

## Technical Notes

- Depends on TASK-044 so the resolver-source literal is copied verbatim from the
  actually-inserted skill text (whitespace/quoting must match exactly or the
  linter will false-flag every skill — the precise failure ADR-3 prevents).
- `check_canonical()` gates on `KIMI_GATE_ANCHOR = "ADLC_DISABLE_KIMI"`; fixtures
  that contain that anchor are subject to the full literal set. Keep
  `clean.md`, `corrupt-sentinel.md`, `unbalanced-parens.md` untouched unless they
  contain `ADLC_DISABLE_KIMI` (they should not — verify with grep).
- The Python literal for the emit string must be single-quoted because it
  contains `"` (match the existing `'command -v ask-kimi …'` entry's style).
- Re-run BOTH suites at the end: `pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` (per README) to confirm no cross-suite regression.

## Addendum — scope extension (architecture.md ADR-3a / ADR-3b), reopened in Phase 4

The first pass (commits `343ebd2`/`639d85e`) handled the emit + resolver
literals but its AC-5 verification was a **false negative**: it ran the linter
`--root` *inside* `.worktrees`, where `SKIP_DIR_PARTS` makes the linter scan
zero files. Re-verified correctly (skills staged outside `.worktrees`): the
linter emits **4 `canonical-helper` findings** because the 4 skills do not
contain the stale literal `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`
(REQ-416 moved that into `partials/kimi-gate.sh`). AC-5 is therefore unmet.

**Additional required changes (ADR-3a):**
- `tools/lint-skills/check.py`: in `CANONICAL_LITERALS`, REPLACE
  `'command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]'`
  with `". .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh"`
  (byte-exact; extract from a real skill: `grep -hn 'kimi-gate.sh' spec/SKILL.md`).
  Tuple remains 5 entries.
- `tools/lint-skills/tests/fixtures/kimi-gate-ok.md`: rewrite the `sh` block to
  the faithful post-REQ-416 shape so it contains ALL 5 literals AND the
  `ADLC_DISABLE_KIMI` anchor — i.e. both source lines (`kimi-gate.sh`,
  `kimi-tools-path.sh`), then `start_s` / `duration_ms` / `"$KIMI_TOOLS"/emit-telemetry.sh …`,
  with an `ADLC_DISABLE_KIMI` token retained (e.g. a `# … ADLC_DISABLE_KIMI=1`
  gate-case comment). Remove the obsolete inline `if command -v ask-kimi … ADLC_DISABLE_KIMI` form.
- `tools/lint-skills/tests/test_check.py`: in `test_missing_canonical_reports_per_rule`,
  change the asserted literal string from the `command -v ask-kimi …` text to the
  kimi-gate source line; **count stays `== 5`** (replacement, not addition);
  ensure `test_kimi_gate_happy_path_is_clean` still asserts zero findings with
  the rewritten fixture.
- `tools/lint-skills/tests/fixtures/missing-canonical.md`: re-verify it contains
  `ADLC_DISABLE_KIMI` but NONE of the (final) 5 literals → exactly 5 findings.
- `tools/lint-skills/README.md`: replace the documented `command -v ask-kimi`
  canonical literal with the kimi-gate source line.

**Corrected AC-5 verification (mandatory method):** stage the 4 worktree skills
into `<skilldir>/SKILL.md` layout in a tmp dir OUTSIDE any `.worktrees` path,
then `python3 tools/lint-skills/check.py --root <tmpdir>` → MUST report **0
`canonical-helper` findings**, EXIT 0. Running `--root` inside the worktree is
not a valid check (vacuous — ADR-3b).

**Out of scope (filed separately, ADR-3b):** fixing `SKIP_DIR_PARTS` so the
linter / `/analyze` Step 1.9 is not vacuous inside `.worktrees`. Do NOT change
`SKIP_DIR_PARTS` in this task.
