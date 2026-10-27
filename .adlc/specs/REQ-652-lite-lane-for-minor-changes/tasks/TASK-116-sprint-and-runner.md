---
id: TASK-116
title: "pipeline-runner and /sprint: lite under the legacy engine, full under the workflow engine"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-115]
---

## Description

Unattended runs follow the lite lane through `pipeline-runner`, and the workflow engine runs lite REQs on the full lane with a log line (BR-8, BR-16; architecture ADR-9, ADR-11).

## Files to Create/Modify

- `agents/pipeline-runner.md` — lite phase list beside the full one; the lite review checklist inline; the lane check before PR and merge; a forced-lite failure escalates and never ends `blocked`; terminal report includes the lane and any escalations.
- `sprint/SKILL.md` — the legacy launch prompt states the runner is unattended; the workflow path documents the full-lane fallback for lite REQs.
- `workflows/adlc-sprint.workflow.js` — eligibility schema gains `lane` (enum `lite`/`full`, optional); preflight prompt asks for it; a pure `liteFallbackNotice(reqs)` builder; one `log()` line per lite REQ after `selectEligible`.
- `workflows/tests/helpers.test.js` — tests for `liteFallbackNotice` (lite REQs listed, none when all full or lane absent).
- `workflows/tests/README.md` — table row for the new helper.

## Acceptance Criteria

- [ ] `node --test 'workflows/tests/*.test.js'` passes, including a case where no notice is produced.
- [ ] The workflow writes no `lane` object to `pipeline-state.json`.
- [ ] The runner's halt list states that a forced-lite failure escalates in subagent mode.
- [ ] `sh tools/lint-skills/check.sh --root .` is clean for `sprint/SKILL.md` and `agents/pipeline-runner.md`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-16 | test-case | `workflows/tests/helpers.test.js`: liteFallbackNotice lists lite REQs | yes |
| AC-13 | test-case | `workflows/tests/helpers.test.js`: liteFallbackNotice empty when no lite REQ | yes |

## Technical Notes

- The eligibility schema is closed (`additionalProperties:false`); add `lane` as an optional property, do not open the schema.
- Put `liteFallbackNotice` inside the script's pure block so the test can import it.
- Consumer copies of the workflow go stale until re-init; that is expected and `/template-drift` reports it.
