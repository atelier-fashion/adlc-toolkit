---
id: TASK-189
title: "Split /proceed: Step 0, Pipeline State Tracking and Run-outcome telemetry into phase companions"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-188]
repo: adlc-toolkit
---

## Description

Architecture ADR-2, ADR-5: move three whole sections verbatim, leave a heading and the
read-and-follow sentence at each, retarget `LIFECYCLE_WRITE_SITES` and `LANE_SITES`, and
update the in-unit and contract-test references.

## Files to Create/Modify

- `proceed/SKILL.md` — three stubs; the R*n* references name the telemetry file
- `proceed/phase-0-setup.md` — new: Step 0, verbatim
- `proceed/phases-state.md` — new: Pipeline State Tracking, verbatim
- `proceed/phases-telemetry.md` — new: Run-outcome telemetry, verbatim
- `proceed/phases-1-3-validation.md` — R2 reference names the telemetry file
- `proceed/phases-6-8-ship.md` — R4/R5 references name the telemetry file
- `proceed/phases-lite.md` — R3 reference names the telemetry file
- `tools/lint-skills/check.py` — `LIFECYCLE_WRITE_SITES`, `LANE_SITES`
- `tools/lint-skills/tests/test_lessons_contract.py` — read the moved sections from their files
- `tools/lint-skills/tests/test_integration_branch_key.py` — the Step 0 resolution site
- `tools/lint-skills/tests/test_lite_lane_contract.py` — the state-schema override shape
- `tools/lint-skills/tests/test_retrieval_status_parity.py` — the new write site

## Acceptance Criteria

- [ ] `wc -l proceed/SKILL.md` below 500; the lint is clean
- [ ] Every fence, marker block and stderr literal of the unit is unchanged as a multiset
- [ ] Each stub names its companion with the read-and-follow sentence
- [ ] `pytest tools/lint-skills/tests` and `sh partials/tests/run.sh` pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: skill-line-budget | no |
| BR-3 | structural-check | AC-3 equivalence script over the `proceed` unit | no |
| BR-4 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_shipped_companions_are_named_by_their_skill` | no |
| BR-12 | structural-check | `find proceed -mindepth 2 -name '*.md'` empty; no `proceed/references/` | no |
| AC-1 | structural-check | `tools/lint-skills`: skill-line-budget, full run | no |
| AC-4 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_shipped_companions_are_named_by_their_skill` | no |
| AC-12 | structural-check | `find spec proceed template-drift wrapup -mindepth 3 -name '*.md'` | no |

## Technical Notes

- Fences move byte for byte; only prose cross-references change (BR-13).
- `test_lessons_contract.py` and `test_lite_lane_contract.py` read content that moves;
  point them at the new file rather than loosening them (LESSON-742).
