---
id: TASK-003
title: "Toolkit-side parity check: /init copy list vs /template-drift surface list (lint + tests)"
status: complete
parent: REQ-525
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001, TASK-002]
---

## Description

Add the automated AC4 enforcement: a per-root lint check in `tools/lint-skills/check.py` that parses the
vendored-surface list from `init/SKILL.md` and the checked-surface list from `template-drift/SKILL.md`
and emits a finding when they disagree, plus a pytest module proving it. Mirrors the existing per-root
`check_agent_model_drift` precedent (ADR-3).

## Files to Create/Modify

- `tools/lint-skills/check.py` — add `SYNC_SURFACES` constant (the five-surface vocabulary, single source
  of truth), add `check_sync_surface_parity(root)`, register it in `run()` after the per-file loop next to
  `check_agent_model_drift`.
- `tools/lint-skills/tests/test_sync_surface_parity.py` — new pytest module.

## Acceptance Criteria

- [ ] AC4: a toolkit-side check verifies `/init`'s copy list and `/template-drift`'s surface list agree.
- [ ] `check_sync_surface_parity(root)` parses both SKILL.md surface-marker blocks, compares against the
      canonical `SYNC_SURFACES` set, and emits a `Finding(check="sync-surface-parity", ...)` on any
      mismatch (a surface in one list but not the expected place in the other).
- [ ] The check is registered in `run()` and degrades gracefully (zero findings, no crash) when a SKILL.md
      or its marker block is absent — same posture as `check_agent_model_drift`.
- [ ] New test module covers: (a) parity holds on the real post-change toolkit tree → zero findings;
      (b) a synthetic root with a surface dropped from one list → a `sync-surface-parity` finding;
      (c) absent SKILL.md → zero findings, no crash.
- [ ] `pytest tools/lint-skills/tests/ -q` is green (all prior 33 tests + the new ones).
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 on the final tree.

## Technical Notes

- Mirror `check_agent_model_drift`: per-root signature `(root: Path) -> list[Finding]`, guard on file
  presence, `try/except` degrade, append in `run()`.
- Parse the marker block deterministically (a stable `<!-- sync-surfaces: ... -->` marker + a fenced or
  bulleted list), NOT by prose-scanning — ADR-3 / LESSON-012 / LESSON-019.
- `/init` copies four physical surfaces (templates, partials, ethos, workflow-runtime);
  `workflow-test-landmine` is a `/template-drift`-only check (a drift symptom, not a copied file). The
  parity rule: every surface `/init` copies must appear in `/template-drift`'s checked list; the
  template-drift-only `workflow-test-landmine` is allowed to be in template-drift without an init entry.
  Encode this asymmetry explicitly so the check is correct, not just symmetric.
- Findings print to stdout / CI logs — use the non-leaking-label posture already in the file (no absolute
  paths in messages).
- Depends on TASK-001 and TASK-002 because the marker blocks they add are the check's inputs.
