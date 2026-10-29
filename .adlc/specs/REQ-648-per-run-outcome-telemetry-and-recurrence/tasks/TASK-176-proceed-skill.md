---
id: TASK-176
title: "/proceed and pipeline-runner: record harness, validateAttempts and verify; emit at every terminal and halt"
status: complete
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171, TASK-173, TASK-178]
repo: adlc-toolkit
---

## Description

Add a "Run-outcome telemetry (REQ-648)" section to `proceed/SKILL.md` holding the
canonical fences (record-harness, record-validate, record-verify, emit), each
behind the BUG-228 provenance line, and wire it into Step 0 item 8, Phases 1/3,
Phase 5 Step B/C/D (plus `ack-check --record`), every halt point, and Phase 8.
Document the new state keys in the schema. Mirror into the companions, the lite
lane's Phase 5, and `agents/pipeline-runner.md`'s terminal contract.

## Files to Create/Modify

- `proceed/SKILL.md` — schema keys + paragraphs; the run-outcome section; Step 0, Phase 1/3, Phase 5, halt and Phase 8 hooks
- `proceed/phases-1-3-validation.md` — record-validate before each `/validate`; validation-exhausted emit
- `proceed/phases-6-8-ship.md` — Step 8b emit after the terminal record; Step 8c pr-ready emit; merge-conflict halt emit
- `proceed/phases-lite.md` — Phase 5 (lite) persists `verify` after the `lite-reviewer` pass
- `agents/pipeline-runner.md` — the runner's emit (engine `legacy`) at its terminal; `verify`/`validateAttempts` in subagent mode
- `tools/delegate/run_outcome.py` — `record-carry` (Step 8b keeps the primary-path copy complete before teardown) and `record-harness --fresh` (LESSON-719: fresh vs resume from the progress record)
- `tools/delegate/emit-run-outcome.sh` — passes `record-carry` through
- `tools/delegate/tests/test_run_outcome.py` — the two new cases

## Acceptance Criteria

- [ ] Every fence that calls `emit-run-outcome.sh` has the BUG-228 provenance line within 30 lines above it, with the `run-outcome skipped: provenance-classifying harness` reply
- [ ] Step 0 records `harness` before the draft-PR push; resume keeps it
- [ ] Phase 5 Step B writes `verify` to the primary-path copy before Step C and runs `ack-check --record`
- [ ] Solo emits after Step 8b for `merged`/`pr-ready` and at each halt for `blocked`; the runner emits at its own terminal
- [ ] `tools/lint-skills/check.sh` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | structural-check | `tools/lint-skills`: harness-skip (every emit fence in proceed/SKILL.md, proceed/phase*.md, agents/pipeline-runner.md) | no |
| BR-3 | structural-check | `tools/lint-skills`: harness-skip, toolkit-root-line, unguarded-source, cross-fence-fn | yes |
| BR-4 | structural-check | `tools/lint-skills`: posix-fence, toolkit-root-line over the Phase 5 record fence | no |
| BR-10 | structural-check | `tools/lint-skills`: toolkit-root-line over the Step 0 record-harness fence | no |
| BR-12 | structural-check | `tools/lint-skills`: full run (sentinels, balance, dispatch-fallback) | no |
| AC-1 | structural-check | `tools/lint-skills`: harness-skip over the Step 8b emit fence | no |
| AC-2 | structural-check | `tools/lint-skills`: harness-skip over the halt-point emit fence | no |
| AC-3 | structural-check | `tools/lint-skills`: posix-fence over the record-verify fence | no |

## Technical Notes

- `engine` is `solo` for a direct `/proceed`, `legacy` in subagent mode.
- The Phase 5 findings JSON goes to `record-verify --findings -` through a heredoc in the same fence.
- AC-1/AC-2/AC-3 are also manual dogfood on the toolkit itself; this REQ's own run records `harness`, `verify` and its line by hand where the skill text it is adding does not yet exist at its own Step 0.
