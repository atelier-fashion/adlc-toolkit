---
id: TASK-174
title: "Reviewer finding format: a required class field and the severity mapping"
status: complete
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Define the canonical `<!-- finding-class -->` block once in `review/SKILL.md`
Step 3 and copy it byte-for-byte into the five reviewer agents,
`agents/reflector.md` and `agents/lite-reviewer.md`. Each agent's output template
gains a `**Class**:` line per finding. A pytest pins presence and byte equality.

## Files to Create/Modify

- `review/SKILL.md` — the canonical block in Step 3; Step 4 consolidation keeps `class` and prefers a matched lesson id
- `agents/correctness-reviewer.md` — block + `**Class**:` in the template
- `agents/quality-reviewer.md` — same
- `agents/architecture-reviewer.md` — same
- `agents/test-auditor.md` — same (gaps default `Major`)
- `agents/security-auditor.md` — same (`High→Major`, `Medium→Minor`, `Low→Nit`)
- `agents/reflector.md` — same
- `agents/lite-reviewer.md` — same
- `tools/delegate/tests/test_run_outcome_docs.py` — new: every copy carries the canonical block byte-for-byte

## Acceptance Criteria

- [ ] All eight files carry the identical block, which states the class regex, the reuse-within-run rule and the severity mapping
- [ ] Each agent template shows a `**Class**:` line
- [ ] The test fails when one copy drifts (checked by mutating a copy in `tmp_path`)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/delegate/tests/test_run_outcome_docs.py::test_finding_class_block_in_every_reviewer` | no |
| AC-13 | test-case | `tools/delegate/tests/test_run_outcome_docs.py::test_finding_class_block_in_every_reviewer` | no |
| AC-13 | test-case | `tools/delegate/tests/test_run_outcome_docs.py::test_drifted_copy_is_caught` | yes |

## Technical Notes

- Out of scope: what reviewers look for. Only the class field and the severity vocabulary change.
