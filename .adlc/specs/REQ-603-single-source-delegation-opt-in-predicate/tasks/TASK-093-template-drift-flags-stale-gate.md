---
id: TASK-093
title: "Ensure /template-drift flags a vendored gate predating this REQ"
status: draft
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

- `tools/adlc/tests/test_template_drift.py` — fixture case carrying the old authorizing arms
- `template-drift/SKILL.md` — only if the existing partial-drift reporting does not already cover the case; prefer asserting existing behaviour over adding machinery

## Acceptance Criteria

- [ ] A fixture vendored `delegate-gate.sh` containing the removed authorizing arms is reported `stale`
- [ ] A fixture matching the current canonical copy is **not** reported stale
- [ ] No new drift-detection machinery is added if the existing partial reporting already satisfies the rule — the task then asserts existing behaviour and says so explicitly
- [ ] The check does not depend on line numbers or file length, which change with every edit

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/adlc/tests/test_template_drift.py::test_stale_vendored_gate_reported` | no |
| BR-13 | test-case | `tools/adlc/tests/test_template_drift.py::test_current_gate_not_reported_stale` | yes |
| AC-18 | test-case | `tools/adlc/tests/test_template_drift.py::test_prereq_gate_fixture_is_stale` | yes |

## Technical Notes

Check first whether `/template-drift` already reports any partial differing from canonical as
stale — REQ-603 BR-13 asks for an assertion, not new tooling, and building a second detection
path would duplicate the surface this REQ is consolidating.

The benign-path case matters more than usual here: a drift check that flags everything is
indistinguishable from one that works, and would train consumers to ignore it.
