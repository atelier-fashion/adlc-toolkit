---
id: TASK-185
title: "Vendor agents into .adlc/agents/, the agents drift surface, and the lane-check defaults"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-180]
repo: adlc-toolkit
---

## Description

`/init` copies `agents/*.md` into `.adlc/agents/` and lists `agents` in its
sync-surfaces block; `/template-drift` gains Step 3f in partials posture and
lists `agents`; `SYNC_SURFACES` and `INIT_COPIED_SURFACES` gain `agents`.
`lane_check.py` gains `.adlc/agents/**`, `.github/agents/**`,
`.github/hooks/**`; tests pin all eight BR-10 globs; `partials/lane-check.md`
lists them (ADR-6, ADR-8).

## Files to Create/Modify

- `init/SKILL.md` — copy step, tree diagram, rationale paragraph, sync-surfaces block
- `template-drift/SKILL.md` — Step 3f, sync-surfaces block, report and /status line
- `tools/lint-skills/check.py` — surface sets
- `tools/lint-skills/tests/test_sync_surface_parity.py` — agents surface case
- `tools/lint-skills/tests/test_skill_text_portability.py` — AC-8 sandbox run
- `tools/adlc/lane_check.py` — three globs
- `tools/adlc/tests/test_lane_check.py` — examples and the BR-10 pin test
- `partials/lane-check.md` — defaults list

## Acceptance Criteria

- [ ] in a sandbox consumer, `/init`'s copy creates one `.adlc/agents/` file per `agents/*.md`; Step 3f reports synced, then stale after an edit, then missing after deletion
- [ ] `sync-surface-parity` passes with both lists updated and fires when either drops `agents`
- [ ] `pytest tools/adlc/tests/test_lane_check.py` asserts `blocked-path` for `.github/agents/x.md`, `.github/hooks/adlc.json`, `.adlc/agents/reflector.md` and the five existing globs

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_init_vendors_agents_and_drift_reports_them` | yes |
| BR-9 | test-case | `tools/lint-skills/tests/test_sync_surface_parity.py::test_agents_surface_parity` | yes |
| AC-8 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_init_vendors_agents_and_drift_reports_them` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_lane_check.py::test_req666_blocked_globs` (must-not-fire: `test_default_blocked_paths_leave_ordinary_files_alone`) | yes |
| AC-9 | test-case | `tools/adlc/tests/test_lane_check.py::test_req666_blocked_globs` | no |

## Technical Notes

The lane-check examples list must keep `test_every_default_blocked_pattern_has_an_example` green.
