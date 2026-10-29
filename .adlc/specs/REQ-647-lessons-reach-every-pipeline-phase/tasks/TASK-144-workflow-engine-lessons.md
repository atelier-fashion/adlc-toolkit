---
id: TASK-144
title: "Workflow engine: LESSONS schemas, retrieval leaves, lessons in the architect/implement/review prompts, set-gated escalation and lessonId union"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-141]
repo: adlc-toolkit
---

## Description

BR-6. The PURE block gains the `LESSON_ENTRY`, `LESSONS` and `TASK_LESSONS`
schemas and the pure helpers `escalateByLessons`, `lessonsBlock` and
`lessonsLogLine`; `dedupeAndRank` unions lesson ids. The orchestration
dispatches three retrieval leaves and threads the loaded text into the three
prompts. Resume stays byte-identical.

## Files to Create/Modify

- `workflows/adlc-sprint.workflow.js` — modify; schemas, helpers, exports, retrieval prompts and leaves, prompt wiring, escalation before consolidation
- `workflows/tests/helpers.test.js` — modify; schema and helper tests
- `workflows/tests/README.md` — modify; coverage table
- `workflows/README.md` — modify; describe the retrieval leaves

## Acceptance Criteria

- [ ] A 15-entry unscored and a 10-entry scored `LESSONS` payload validate; a 16-entry payload and one with an unknown key are rejected (test-local validator over the exported literal)
- [ ] `escalateByLessons`: an id outside the set is not escalated and is dropped; an id inside escalates one level; a `confidence: "low"` or superseded entry does not escalate
- [ ] Two duplicates where only the second has `lessonId` dedupe to one that keeps the id and the escalation
- [ ] `node --test 'workflows/tests/*.test.js'` passes with collected > 0, including the agentType source check

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `workflows/tests/helpers.test.js` "escalateByLessons" and "LESSONS" tests | yes |
| AC-8 | test-case | `workflows/tests/helpers.test.js` "LESSONS: 15 unscored and 10 scored validate; 16 entries and an unknown key are rejected" | yes |
| AC-9 | test-case | `workflows/tests/helpers.test.js` "escalateByLessons" + "dedupeAndRank: unions lessonId" | yes |
| AC-13 | test-case | `node --test 'workflows/tests/*.test.js'` collected > 0 | no |

## Technical Notes

- No `Date.now()`/`new Date()`: `retrievedAt` comes from the leaf.
- Retrieval prompts never read `args.answers`; their bytes depend only on id, worktree and task ids (REQ-474 BR-7, LESSON-331).
- Every new `agent()` call uses the default subagent (no `agentType`), so the agentType source check is unchanged.
- The leaves run the same `adlc_lessons select … --format json --with-text` fence `/proceed` runs, and write `lessons.<set>` to the primary-path state copy.
