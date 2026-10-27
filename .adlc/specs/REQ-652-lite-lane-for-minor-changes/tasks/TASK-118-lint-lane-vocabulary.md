---
id: TASK-118
title: "tools/lint-skills: lane-vocabulary check and the proceed lifecycle-write site"
status: complete
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-114, TASK-116, TASK-117]
---

## Description

Structural enforcement of the vocabulary (BR-17, architecture ADR-13) and of the new `approved` writer (BR-18, ADR-4).

## Files to Create/Modify

- `tools/lint-skills/check.py` — `LANE_VALUES`, `LANE_TRIGGERS`, `LANE_ACTORS` read from the `<!-- lane-vocabulary -->` block in `partials/lane-check.md`; `LANE_SITES` explicit tuple (spec, proceed + `proceed/phase*.md`, wrapup, status, sprint SKILL.md, `agents/pipeline-runner.md`, `workflows/adlc-sprint.workflow.js`, `templates/requirement-template.md`); `check_lane_vocabulary(root)` registered in `run()` with the per-root checks; `LIFECYCLE_WRITE_SITES` gains `proceed/SKILL.md`.
- `tools/lint-skills/tests/test_lane_vocabulary.py` — new, direct-import style on tmp roots plus a real-tree clean assertion.
- `tools/lint-skills/README.md` — document the check in "What it checks".

## Acceptance Criteria

- [ ] A site writing `lane: "medium"` or naming an unknown trigger fails; the shipped tree passes.
- [ ] A missing vocabulary block is a finding; an empty one is a finding; a prose mention not at line start is ignored (LESSON-404 decoy test).
- [ ] Deleting a site from disk that `LANE_SITES` names is a finding.
- [ ] `python3 -m pytest tools/lint-skills/tests -q` passes and `sh tools/lint-skills/check.sh --root .` exits 0 having scanned at least 17 SKILL.md files.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-17 | test-case | `tools/lint-skills/tests/test_lane_vocabulary.py::test_unknown_lane_value_fails` | no |
| AC-14 | test-case | `tools/lint-skills/tests/test_lane_vocabulary.py::test_shipped_tree_is_clean` | yes |
| BR-18 | test-case | `tools/lint-skills/tests/test_retrieval_status_parity.py::test_proceed_is_a_lifecycle_write_site` | no |

## Technical Notes

- Model on `check_retrieval_status_parity` (`parse_*_block` returns `None` when absent and `set()` when empty, and the caller reports both).
- Value detection: match `lane:`/`"lane":`/`trigger=`/`trigger:` followed by a quoted or bare token; keep the regex narrow so prose does not trip it.
