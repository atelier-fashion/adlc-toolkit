---
id: TASK-115
title: "/proceed: the lite branch, escalation, --full and the fourth halt"
status: complete
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-112, TASK-113]
---

## Description

The pipeline half of the REQ: `/proceed` reads the lane and runs the lite branch, the lane check, escalation and `--full` (BR-5–BR-11, BR-13, BR-18; architecture ADR-4–ADR-10).

## Files to Create/Modify

- `proceed/SKILL.md` — new `argument-hint` and `--full` handling under Arguments; Autonomous Execution Contract becomes four halts; state schema and an additive `lane` paragraph (absent ⇒ full); Gate Protocol note on skipped phases; Step 0 reads the lane, initializes `lane`, writes `approved` on lite with a `lifecycle-write` declaration; short lite pointers at Phases 1–5 and 6–8 to the companion.
- `proceed/phases-lite.md` — new companion (named `phase*` so the `unguarded-source` walk covers it): the lite step list, fresh retrieval (ADR-8), implementation from ACs with `[REQ-xxx]` commits, the gates, the `lite-reviewer` dispatch or inline checklist, the lane check call, escalation procedure, the forced-lite halt and `lane.overrides`.
- `proceed/phases-1-3-validation.md` — lite skip note per phase.
- `proceed/phase-4-implementation.md` — lite variant pointer (no task files).
- `proceed/phases-6-8-ship.md` — PR body `Lane:` line with `lane_reason` and no Architecture/Reflection sections on lite; lane re-check after Phase 7 fixups and before the Phase 8 trial merge.
- `architect/SKILL.md` — one note in Step 2: on an escalation resume, code already on the branch is the baseline to design around.

## Acceptance Criteria

- [ ] A lite run records phases 1–3 in `completedPhases` with `skipped: "lite"` history entries and `lane.skippedPhases`, and the Gate Protocol's previous-phase rule still holds at Phase 4.
- [ ] The lane check runs on the diff after the review fixes, again after any Phase 7 commit, and again before merge, always against `origin/<integrationBranch>`.
- [ ] Escalation writes the spec frontmatter and `lane.escalations` before continuing, trims `completedPhases` to `[0]`, keeps `repos`, and resumes at Phase 1.
- [ ] A forced-lite failure halts in main mode and escalates in subagent mode; "keep lite" appends `lane.overrides` and the same triggers do not halt again.
- [ ] `--full` on a lite REQ escalates with `actor: operator`; on a full REQ it logs and does nothing.
- [ ] The halt count reads four everywhere it is stated (SKILL.md contract, Step 0 note, ship companion).
- [ ] `sh tools/lint-skills/check.sh --root .` is clean, including `forge-direct-gh`, `cross-fence-fn`, `cross-fence-var`, `unguarded-source` and `retrieval-status-parity`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | structural-check | `tools/lint-skills`: lane-vocabulary over `proceed/phases-lite.md` | no |
| BR-6 | structural-check | `tools/lint-skills`: cross-fence-fn, unguarded-source over the lane-check call sites | no |
| BR-7 | structural-check | `tools/lint-skills`: lane-vocabulary (trigger set) | no |
| BR-8 | structural-check | `tools/lint-skills`: lane-vocabulary (actor set); halt text names both the halting and the non-halting actor | yes |
| BR-9 | structural-check | `tools/lint-skills`: lane-vocabulary (`implementer` trigger) | no |
| BR-10 | structural-check | `tools/lint-skills`: balance over `proceed/phases-lite.md` | no |
| BR-11 | structural-check | `tools/lint-skills`: lane-vocabulary (`operator` trigger) | no |
| BR-13 | structural-check | `tools/lint-skills`: balance over `proceed/phases-6-8-ship.md` | no |
| BR-18 | structural-check | `tools/lint-skills`: retrieval-status-parity (proceed lifecycle-write site) | no |
| AC-3 | structural-check | `tools/lint-skills`: lane-vocabulary | no |
| AC-5 | structural-check | `tools/lint-skills`: lane-vocabulary | no |
| AC-6 | structural-check | `tools/lint-skills`: lane-vocabulary (actor set) | yes |
| AC-7 | structural-check | `tools/lint-skills`: lane-vocabulary | no |
| AC-8 | structural-check | `tools/lint-skills`: lane-vocabulary (absent ⇒ full stated in every reader) | yes |
| AC-9 | structural-check | `tools/lint-skills`: lane-vocabulary over `proceed/phases-lite.md` (lite-reviewer handed the fresh retrieval set; `reversal` trigger) | no |
| AC-10 | structural-check | `tools/lint-skills`: balance over `proceed/phases-6-8-ship.md` | no |
| AC-16 | structural-check | `tools/lint-skills`: cross-fence-fn over the three re-check sites | yes |

## Technical Notes

- Keep `proceed/SKILL.md` additions short; the detail goes in `proceed/phases-lite.md` (the companion-file pattern, architecture.md "ADLC pipeline shape").
- Every lane-check call sources `partials/lane-check.sh` in the same fence as the call (cross-fence-fn).
- The forced-lite halt question is a numbered list per Brett's convention; the two answers are "escalate" and "keep lite".
- Do not fix the full lane's `main...HEAD` diff sites here (architecture follow-ups); the lite path uses `origin/<integrationBranch>` from state.
- Subagent-mode detection is the existing "you are in subagent mode if told so in your launch prompt" sentence; reuse it, do not invent a second predicate.
