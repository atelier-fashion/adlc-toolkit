---
id: TASK-043
title: "Reconcile canonical-helper gate literal with REQ-416 ADR-2 (5-site lockstep)"
status: complete
parent: REQ-437
created: 2026-05-16
updated: 2026-05-16
dependencies: []
---

## Description

Replace `CANONICAL_LITERALS` literal #4 (the obsolete inline gate predicate) in `tools/lint-skills/check.py` with the byte-exact gate-source line the four migrated Kimi-aware skills now share, and cascade that single change in lockstep to the rule's test, two fixtures, and README. The five edits land in ONE commit (REQ-437 architecture ADR-2: a half-applied cascade breaks the suite — the exact drift this rule detects). No `SKILL.md` is modified (REQ-437 BR-3).

Exact strings:

- OLD #4: `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`
- NEW #4: `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`

## Files to Create/Modify

- `tools/lint-skills/check.py` — in `CANONICAL_LITERALS`, replace the 4th tuple element (currently the single-quoted `'command -v ask-kimi …'`) with the double-quoted NEW #4 string (no quotes inside it, so `"..."` matches the style of literals #1–#3). Tuple length stays 4; literals #1–#3 byte-identical.
- `tools/lint-skills/tests/test_check.py` — in `test_missing_canonical_reports_per_rule`: keep `assert result.returncode >= 4` and `assert result.stdout.count("canonical-helper") == 4`; keep the `start_s` / `duration_ms` / `tools/kimi/emit-telemetry.sh ` assertions; replace `assert 'command -v ask-kimi' in result.stdout` with `assert ". .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh" in result.stdout`. Update the adjacent comment if it names the old literal. `test_kimi_gate_happy_path_is_clean` body unchanged (depends on the fixture below).
- `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` — rewrite the `sh` fenced block to a faithful post-REQ-416 skill shape: the NEW #4 gate-source line, then the documented `adlc_kimi_gate_check; gate=$?` + `case $gate in … esac` idiom (keep an `ADLC_DISABLE_KIMI` token in a case-arm comment so the anchor survives), then the three unchanged telemetry literals (`start_s=$(date -u +%s)`, `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`, a `tools/kimi/emit-telemetry.sh ` invocation with the trailing space). Update the intro prose accordingly. Result must be: anchor present AND all four literals present ⇒ zero findings.
- `tools/lint-skills/tests/fixtures/missing-canonical.md` — keep the `ADLC_DISABLE_KIMI` anchor in prose, keep zero canonical literals; change the prose "three required literals" → "four required literals" (documentation consistency only — behavior already yields 4 findings).
- `tools/lint-skills/README.md` — in "What it checks" §3, replace the `` `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` `` bullet with a `` `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh` `` bullet; leave the "four exact literals" framing intact.

## Acceptance Criteria

- [ ] `~/.claude/kimi-venv/bin/pytest tools/lint-skills/tests/ -q` exits 0, all tests pass.
- [ ] `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` exits 0, all tests pass (no kimi-suite regression).
- [ ] `python3 tools/lint-skills/check.py --root <tmp dir with copies of analyze/proceed/spec/wrapup SKILL.md>` prints nothing and exits 0 (zero `canonical-helper` findings, zero findings total).
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 from the toolkit root (repo-wide clean).
- [ ] `grep -F 'command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]' tools/lint-skills/check.py` → no match.
- [ ] `grep -F '. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh'` matches in each of `check.py`, `tests/test_check.py`, `tests/fixtures/kimi-gate-ok.md`, `README.md`.
- [ ] `git diff --name-only` lists only files under `tools/lint-skills/` and `.adlc/specs/REQ-437-*/` — no `SKILL.md`, no `partials/`, nothing else.

## Technical Notes

- Match semantics are substring (`literal not in text`) — do NOT introduce regex/anchoring (REQ-437 ADR-3, LESSON-016). Indentation differences across skills are irrelevant by construction.
- The balance check only flags *deficits* (opens > closes); the `case` arms' extra `)` in the rewritten `kimi-gate-ok.md` fence are explicitly fine (check.py's own comment notes case-arm `)` is common and not flagged). The real skills carry the same case block and lint clean — mirror their shape.
- Keep the trailing space in `tools/kimi/emit-telemetry.sh ` (literal #3) — it is part of the canonical literal.
- Do NOT touch `.adlc/context/conventions.md`, any historical `.adlc/specs/REQ-414|416|417|425/**`, `partials/kimi-gate.sh`, `sentinels.txt`, `check.sh`, or scan/`find_skill_files` logic (REQ-435's area — REQ-437 BR-10).
- Single commit, message: `fix(lint-skills): reconcile canonical-helper gate literal with REQ-416 ADR-2 [TASK-043]`.
