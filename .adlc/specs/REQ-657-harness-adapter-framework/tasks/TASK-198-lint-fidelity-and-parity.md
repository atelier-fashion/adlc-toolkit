---
id: TASK-198
title: "allowlist-fidelity and render-parity lint checks; unguarded-source walk; harness-config surface"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-194, TASK-195, TASK-196]
repo: adlc-toolkit
---

## Description

The two new `tools/lint-skills` checks and the widened `unguarded-source` walk
(BR-9, BR-13, BR-16, BR-18).

## Files to Create/Modify

- `tools/lint-skills/check.py` — allowlist-fidelity, render-parity, hooks walk, SYNC_SURFACES
- `tools/lint-skills/tests/test_harness_lints.py` — new
- `tools/lint-skills/tests/test_sync_surface_parity.py` — harness-config

## Acceptance Criteria

- [ ] `check.sh` runs both checks and is clean on the shipped tree
- [ ] A drifted golden is reported by render-parity; a mis-spelled hook source by unguarded-source

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_allowlist_fidelity_clean_on_tree` | yes |
| BR-13 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_render_parity_reports_drift` | yes |
| BR-16 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_unguarded_source_walks_hooks` | yes |
| AC-7 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_allowlist_fidelity_clean_on_tree` | yes |
| AC-11 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_render_parity_reports_drift` | yes |
| AC-14 | structural-check | `tools/lint-skills`: unguarded-source, allowlist-fidelity, render-parity | yes |

## Technical Notes

The lint imports the engine from `tools/adlc`, as `agent-model-drift` does.
