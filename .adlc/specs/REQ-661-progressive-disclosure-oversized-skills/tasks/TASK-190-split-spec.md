---
id: TASK-190
title: "Split /spec: Step 1.4 step 3 and Step 1.6 sub-step 7 into spec/references/"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-187]
repo: adlc-toolkit
---

## Description

Architecture ADR-3, ADR-5: move the two delegated-read sub-steps verbatim into
`spec/references/`, leave each sub-step's numbered title and the read-and-follow
sentence, keep Step 1.4 steps 1–2 (the `'<request>'` fences) in `SKILL.md`, and replace
the line-number citation in Step 1.4 step 6 with section names (BR-13).

## Files to Create/Modify

- `spec/SKILL.md` — two pointers; step 6's citation becomes section names
- `spec/references/intake-source-read.md` — new: Step 1.4 step 3, verbatim
- `spec/references/retrieval-body-read.md` — new: Step 1.6 sub-step 7, verbatim
- `tools/lint-skills/tests/test_read_bin_fences.py` — the read-bin fence counts move with the fences

## Acceptance Criteria

- [ ] `wc -l spec/SKILL.md` below 500; the lint is clean, no `companion-templating` finding
- [ ] Both `'<request>'` fences are still in `spec/SKILL.md`
- [ ] `sh partials/tests/run.sh` passes unchanged (its `spec/SKILL.md` cases) and `node space/build.mjs --check` passes
- [ ] The executed gate fence prints `intake_gate=0` for a readable file and `intake_gate=1` for a one-line request

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: skill-line-budget | no |
| BR-3 | structural-check | AC-3 equivalence script over the `spec` unit | no |
| BR-5 | structural-check | each moved block is one whole numbered sub-step | no |
| BR-6 | structural-check | `tools/lint-skills`: companion-templating over `spec/references/` | yes |
| BR-16 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_spec_intake_gate_takes_a_hostile_literal` | yes |
| AC-6 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_spec_intake_gate_takes_a_hostile_literal` | yes |
| AC-17 | structural-check | `tools/lint-skills`: arg-templating, posix-fence, unguarded-source on companions | no |

## Technical Notes

- Keep the moved lines' three-space list indentation: fence bodies must stay byte-identical.
- `space/build.mjs` reads `<!-- intake-gap-rules -->` (steps 4–5), which does not move.
