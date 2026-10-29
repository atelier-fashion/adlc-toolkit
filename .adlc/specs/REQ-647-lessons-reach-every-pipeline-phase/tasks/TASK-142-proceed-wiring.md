---
id: TASK-142
title: "Wire LessonSets into /proceed (Step 0, Phase 4, Phase 5), the implementer, the reflector, the pipeline-runner and /validate"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-141]
repo: adlc-toolkit
---

## Description

The `/proceed` call sites (BR-1–BR-4, BR-7, BR-8, BR-10): compute the Step-0
set at Step 0 item 7, a task set before each Phase-4 task, and the Phase-5 set
before Step A; pass the loaded text to the implementer and to all six Phase-5
agents; run the acknowledgement check at Step B; document the `lessons` state
key. The agents learn to read and acknowledge lessons, and the reflector uses a
supplied set instead of grepping.

## Files to Create/Modify

- `proceed/SKILL.md` — modify; state schema `lessons` key, Step 0 item 7 fence, Phase 4 summary, Phase 5 set + Step A inputs + Step B ack check, subagent mode
- `proceed/phase-4-implementation.md` — modify; per-task retrieval step, implementer inputs, end-of-phase log line
- `agents/task-implementer.md` — modify; read supplied lessons, acknowledge with a `Lessons:` trailer or the task's `## Verification` block
- `agents/reflector.md` — modify; use a supplied pre-computed set and do not grep, grep only when none is supplied
- `agents/pipeline-runner.md` — modify; replace the "Check `.adlc/knowledge/lessons/` …" line, name the primary-path state copy as a sanctioned write
- `validate/SKILL.md` — modify; Validating Implementation runs the acknowledgement check (standalone only)

## Acceptance Criteria

- [ ] Step 0 item 7 computes `lessons.step0` with `--fresh` on a fresh run and `--reuse` on a resume, into the primary-path copy, and logs the line
- [ ] Phase 4 computes the task set before each task and passes its loaded text to the implementer in both modes
- [ ] Phase 5 hands the Phase-5 set to all six agents; the reflector is told it was pre-computed; Step B runs `ack-check` and lists its lines as Info
- [ ] A non-zero `adlc_lessons` return is logged and the pipeline continues
- [ ] `agents/pipeline-runner.md` no longer contains "Check `.adlc/knowledge/lessons/` for applicable pitfalls" and references `pipeline-state.json.lessons`
- [ ] `tools/lint-skills` passes (root line, guarded source, same-fence calls, dispatch sentence)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: toolkit-root-line, unguarded-source, cross-fence-fn; `tools/lint-skills/tests/test_lessons_contract.py::test_proceed_step0_computes_step0_set` | no |
| BR-1a | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_phase4_computes_task_set_before_dispatch` | no |
| BR-2 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_implementer_acknowledges_lessons` | no |
| BR-3 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_phase5_set_reaches_all_six_agents` | no |
| BR-4 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_step_b_ack_check_is_info_only` | yes |
| BR-7 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_lessons_state_key_is_additive` | yes |
| BR-8 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_pipeline_runner_uses_state_lessons` | no |
| BR-10 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_end_of_phase_logs_name_lessons` | no |
| AC-1 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_proceed_step0_computes_step0_set` | no |
| AC-3 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_phase4_computes_task_set_before_dispatch` | no |
| AC-5 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_phase5_set_reaches_all_six_agents` | no |
| AC-10 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_pipeline_runner_uses_state_lessons` | no |

## Technical Notes

- Every fence: the canonical root line, then the guarded source of `forge.sh` is NOT needed — `lessons.sh` sources it itself — then the guarded source of `lessons.sh`, then the call, all in one fence.
- Keep SKILL.md Phase 5 inline (ADR-3 of REQ-416); put the step detail where the phase already lives.
- The primary-path state file is `<repos[primary].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json`; pass it with `--state-out` and `--state`.
- BR-1b's override of `/review` Step 1.7d ("read their bodies in full") applies only inside `/proceed`; say so where Phase 5 hands over the set.
