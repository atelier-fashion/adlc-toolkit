---
id: TASK-114
title: "/spec: strip --lite/--full, Step 1.7 triage, lane frontmatter"
status: complete
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: []
---

## Description

`/spec` assigns every new REQ a lane (BR-1–BR-4, architecture ADR-2) and the requirement template carries the fields.

## Files to Create/Modify

- `spec/SKILL.md` — `argument-hint` gains `[--lite|--full]`; **Input** strips both flags before Step 1.4 and errors on both before anything else; new **Step 1.7: Triage the lane** between Step 1.6 and Step 2 (BR-2 list, uncertain ⇒ lite, forced flags set `lane_forced`); Step 3 frontmatter writes quoted `lane`, `lane_reason`, `lane_forced`; Step 4 shows the lane; Quality checklist gains a lane item.
- `templates/requirement-template.md` — frontmatter gains `lane: "full"`-style commented guidance (no default value that would make every new spec lite), `lane_reason`, `lane_forced`, and `lane_escalated` as a comment only.

## Acceptance Criteria

- [ ] Step 1.7 runs after retrieval and before `adlc_alloc_id`; `--lite --full` together stops before Step 2.
- [ ] The intake gate in Step 1.4 receives the argument with the flags removed.
- [ ] Every lane string value in the Step 3 example is quoted.
- [ ] The triage criteria are BR-2's list, referenced not paraphrased, and the uncertain case is stated.
- [ ] `sh tools/lint-skills/check.sh --root .` is clean for `spec/SKILL.md` (`arg-templating`, `cross-fence-var`, `balance`).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: lane-vocabulary over `spec/SKILL.md` | no |
| BR-2 | structural-check | `tools/lint-skills`: lane-vocabulary, balance | no |
| BR-3 | structural-check | `tools/lint-skills`: lane-vocabulary | no |
| BR-4 | structural-check | `tools/lint-skills`: balance, arg-templating | no |
| BR-12 | structural-check | `tools/lint-skills`: lane-vocabulary over `templates/requirement-template.md` | no |
| AC-1 | structural-check | `tools/lint-skills`: lane-vocabulary | no |
| AC-2 | structural-check | `tools/lint-skills`: lane-vocabulary, balance | no |

## Technical Notes

- Flag handling is the model reading `$ARGUMENTS` (the `/sprint --workflow` precedent), not shell; do not add flag parsing to `partials/intake.sh`.
- Do not add a `##` section to the requirement template — the intake checklist is derived from its headings (partials/README.md).
- The template change makes consumer copies drift; `/template-drift` reports it, which is expected.
