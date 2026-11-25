---
id: TASK-284
title: "Workflow engine: `source` on FINDINGS, a cross-family leaf per repo, and recorded skips"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-282]
---
## Description

Give the `/sprint --workflow` engine the same reviewer: extend the closed `FINDINGS`
schema in the same change as its new emitter (LESSON-331), union `source` on merge, add a
closed `CROSS_FAMILY` schema and a pass-through leaf agent that runs the partial, and
record a null result as `invalid-output` rather than omitting it.

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — `FINDINGS` gains `source`, `disposition`, `declineReason`; `dedupeAndRank` unions `source`; `CROSS_FAMILY` schema; `runCrossFamily` per touched repo beside `runPrePass`; findings joined before `dedupeAndRank`; skip records
- `agents/cross-family-reviewer.md` — new: `tools: Bash`; sources the partial and returns its JSON; canonical fallback paragraph
- `tools/adlc/agents_render.py` — `_SHIPPED_DEFAULTS` entry for the new agent
- `workflows/README.md` — `FINDINGS` and `CROSS_FAMILY` documented
- `workflows/tests/helpers.test.js` — schema accept/reject; merge unions `source`; `panelMembers()` still six; null leaf records `invalid-output`
- `tools/adlc/tests/test_agents_render.py` — parity test includes the new agent

## Acceptance Criteria

- [ ] `FINDINGS` accepts `source: ["cross-family"]` and `["panel","cross-family"]`, and rejects `["kimi"]` and `[]`
- [ ] Two findings under one dedupe key from different sources merge into one with both sources, sorted
- [ ] `panelMembers()` returns the same six members; `REVIEWER_DIMENSIONS` is unchanged
- [ ] A null or schema-failing leaf result records `skipped` / `invalid-output` for that repo
- [ ] A cross-family finding that is Critical or `mustFix` enters `blocking` exactly as a panel finding does
- [ ] `workflows/tests` and `tools/adlc/tests/test_agents_render.py` pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-7 | test-case | `workflows/tests/helpers.test.js::dedupeAndRank unions source on merge` | no |
| BR-12 | test-case | `workflows/tests/helpers.test.js::cross-family null leaf records invalid-output` | no |
| BR-12 | test-case | `workflows/tests/helpers.test.js::panelMembers unchanged with cross-family leaf` | yes |
| AC-2 | test-case | `workflows/tests/helpers.test.js::dedupeAndRank unions source on merge` | no |
| AC-14 | test-case | `workflows/tests/helpers.test.js::FINDINGS source accepts known and rejects unknown` | yes |

Lessons: LESSON-008, LESSON-393, LESSON-729, LESSON-742, LESSON-906

## Technical Notes

- Do not reuse the `CANDIDATES.gateReason` enum: it omits `disabled-via-config` and `not-opted-in` (pre-existing defect, architecture "Pre-existing defects"). The leaf returns this REQ's skip reason, already mapped by `cross_family.py decide`.
- `dimension` is set per reviewer result (`FINDINGS.dimension`, `workflow.js:176`), and `dedupeAndRank` unions it into `dimensions`. Cross-family findings join with an empty `dimensions` list, never a `PANEL_DIMENSIONS` value, so `fixedPairs` cannot schedule a Step D re-run for them (BR-1) and `mergeReverified` (`workflow.js:654-667`), which replaces re-checked dimensions wholesale, cannot drop them. Add a test for each.
- The `agentType` and `agent_model_drift` checks walk `agents/*.md` (`check.py:3242`).
