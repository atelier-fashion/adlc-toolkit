---
id: TASK-218
title: "Run the probe and record the compatibility note"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-216, TASK-217]
repo: adlc-toolkit
---

## Description

Run `--dry-run`, then the probe on the real `agy`. Write every CompatibilityNote row and the route. Check each row against the architecture, and amend the architecture before TASK-219 if a row disagrees.

## Files to Create/Modify

- `.adlc/research/antigravity-compatibility.md` — new: the note
- `.adlc/research/harness-probes/antigravity.json` — new: the result
- `.adlc/research/harness-probes/fixtures/antigravity.jsonl` — new: the transcript fixture

## Acceptance Criteria

- [ ] Every row names how it was established, the version and the path or key, and no row reads `usable` from `docs` alone
- [ ] The result holds a verdict or `n/a` with a reason per probe, and no email, login or account id
- [ ] User files are byte-identical after the run

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_note_has_every_row | no |
| AC-1 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_usable_row_from_docs_alone | no |
| BR-3 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_result_is_scrubbed | no |

## Technical Notes

BR-1, LESSON-765, LESSON-766. A row nothing could establish reads `unverified`, and goes to `## Deferred`.
