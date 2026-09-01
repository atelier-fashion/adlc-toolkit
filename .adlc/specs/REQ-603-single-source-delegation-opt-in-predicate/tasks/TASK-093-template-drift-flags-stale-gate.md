---
id: TASK-093
title: "Ensure /template-drift flags a vendored gate predating this REQ"
status: complete
parent: REQ-603
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-090]
---

## Description

Assert that a consumer repo carrying the pre-REQ `delegate-gate.sh` is reported as stale. The
hazard is future-conditional rather than immediate: an old gate agrees with current Python on
every input today, so nothing diverges — but the next authorizing arm added to Python is
bypassed by a stale gate that still short-circuits on `ADLC_DELEGATE_ENABLED`.

## Files to Create/Modify

- `tools/lint-skills/tests/test_sync_surface_parity.py` — assertions that the existing drift chain covers `delegate-gate.sh`

**No machinery added, and no `template-drift/SKILL.md` change.** The task's own
criterion said to assert existing behaviour if it already satisfies the rule, and it
does: `/template-drift` classifies **any** partial diff as `stale` (partials-posture —
shared executable code, no customization classification), and `partials` is a surface
both `/init` and `/template-drift` declare. A vendored `delegate-gate.sh` predating this
REQ therefore differs from canonical and is already reported.

The artifact named at architecture time (`tools/adlc/tests/test_template_drift.py`) does
not exist and would have been the wrong thing to build: `/template-drift` is a markdown
skill with no Python implementation, so creating a Python test surface for it is exactly
the "new drift-detection tooling" this task and the REQ's Out of Scope forbid.

## Acceptance Criteria

- [ ] A fixture vendored `delegate-gate.sh` containing the removed authorizing arms is reported `stale`
- [ ] A fixture matching the current canonical copy is **not** reported stale
- [ ] No new drift-detection machinery is added if the existing partial reporting already satisfies the rule — the task then asserts existing behaviour and says so explicitly
- [ ] The check does not depend on line numbers or file length, which change with every edit

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/lint-skills/tests/test_sync_surface_parity.py::test_partials_surface_declared_by_both_skills` | no |
| BR-13 | test-case | `tools/lint-skills/tests/test_sync_surface_parity.py::test_partials_drift_is_classified_stale_not_customizable` | yes |
| AC-18 | test-case | `tools/lint-skills/tests/test_sync_surface_parity.py::test_delegate_gate_is_a_vendored_partial` | yes |

## Technical Notes

Check first whether `/template-drift` already reports any partial differing from canonical as
stale — REQ-603 BR-13 asks for an assertion, not new tooling, and building a second detection
path would duplicate the surface this REQ is consolidating.

The benign-path case matters more than usual here: a drift check that flags everything is
indistinguishable from one that works, and would train consumers to ignore it.
