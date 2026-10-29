---
id: TASK-175
title: "Workflow engine: required FINDINGS.class, verify state-write leaves, validateAttempts, post-terminal emit leaf"
status: complete
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171, TASK-174]
repo: adlc-toolkit
---

## Description

Extend `workflows/adlc-sprint.workflow.js`: `FINDING_CLASS_PATTERN` and a required
`class` (with `pattern`) on `FINDINGS.findings[]`; `reviewPrompt` asks for it and
states the severity scale; pure `verifyEntry`, `markWorkflowFixed` and `runOutcomeArgs`;
a state-write leaf after consolidation and after re-verify; the attempt number in
the gate's validate prompt; `emitRunOutcomes(closed, todo)` after
`closeOutMerged`, one leaf per REQ, never throwing. Update the README and tests.

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — schema, prompts, pure helpers, leaves, top-level emit pass
- `workflows/tests/helpers.test.js` — `schemaErrors` learns `pattern`; class schema cases; `markWorkflowFixed`; `verifyEntry`; `runOutcomeArgs`; the Python-regex parity; leaf wiring order
- `workflows/README.md` — the run-outcome leaves and the `class` field

## Acceptance Criteria

- [ ] A FINDINGS payload with `class: "task-ordering-race"` validates; one missing `class`, or with `class: "Task Ordering"`, is rejected
- [ ] `markWorkflowFixed` marks a blocking finding absent after re-verify `fixed: true`, keeps a still-present one `false`, and marks every non-blocking finding `false`
- [ ] `verify()` dispatches the state-write leaf after consolidation and, when the fix loop ran, after the re-verify; a leaf throw is logged and the return contract is unchanged
- [ ] `emitRunOutcomes` runs after `closeOutMerged` for every REQ, passes `TERMINAL.state` verbatim and the raw reason, and never throws; `{results}` is unchanged
- [ ] `node --test 'workflows/tests/*.test.js'` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `workflows/tests/helpers.test.js`: the run-outcome leaves are wired after the close-out pass and never read args | no |
| BR-4 | test-case | `workflows/tests/helpers.test.js`: markWorkflowFixed: only a blocking finding absent after re-verify is fixed | yes |
| BR-5 | test-case | `workflows/tests/helpers.test.js`: runOutcomeArgs: TERMINAL.state verbatim, the raw reason made shell-inert | no |
| BR-6 | test-case | `workflows/tests/helpers.test.js`: FINDINGS class is required and pattern-checked | yes |
| AC-7 | test-case | `workflows/tests/helpers.test.js`: FINDINGS class is required and pattern-checked | yes |

## Technical Notes

- The PURE block may not use `Date.now`; the leaf stamps `consolidatedAt` through `record-verify`.
- Prompts embed `JSON.stringify` of the record so a replay rebuilds byte-identical text (REQ-474 BR-7).
- The leaf locates the primary-path state with `lessonsStatePath(id, worktree, repos)`; with no Phase-0 records it passes `--req <id>` and the glob under the session repo.
