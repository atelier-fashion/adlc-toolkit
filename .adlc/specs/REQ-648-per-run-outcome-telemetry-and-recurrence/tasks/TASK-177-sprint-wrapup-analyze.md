---
id: TASK-177
title: "/sprint Recurrence and orchestrator emit, /wrapup lessonsWritten, /analyze Step 1.10"
status: draft
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171, TASK-172]
repo: adlc-toolkit
---

## Description

`/sprint`: the legacy orchestrator emits (engine `legacy`) after the Step 5
close-out of a REQ it merged; Step 6 gains a **Recurrence** section built by
`check-run-outcomes.sh --recurrence`; the workflow branch gains a summary step
after `{results}`. `/wrapup` Step 5 records `lessonsWritten`. `/analyze` gains
Step 1.10 `harness-fidelity`, mirroring Step 1.8.

## Files to Create/Modify

- `sprint/SKILL.md` — Step 0 workflow branch summary step; Step 5 orchestrator emit; Step 6 Recurrence section
- `wrapup/SKILL.md` — Step 5 `record-lessons-written`
- `analyze/SKILL.md` — Step 1.10

## Acceptance Criteria

- [ ] Rows with `k ≥ 2` render under `harness property — consider a skill/lint/partial change`, rows with `k = 1` under `single occurrence — lesson at most (confidence: low)`, `no-record` rows listed
- [ ] `/analyze` Step 1.10 skips silently when the script or log is absent, prints the `no runs` line, the unavailable line on rc 1, and a block grouped by `toolkit_version` otherwise; BUG-230 skip line present
- [ ] `/wrapup` Step 5 records the `### Lessons captured` outcome in both modes into the primary-path copy
- [ ] `tools/lint-skills/check.sh` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | structural-check | `tools/lint-skills`: harness-skip over the sprint Step 5 emit fence | no |
| BR-7 | structural-check | `tools/lint-skills`: toolkit-root-line, unguarded-source over the sprint Recurrence fence | no |
| BR-8 | structural-check | `tools/lint-skills`: toolkit-root-line, posix-fence over the analyze Step 1.10 fence | yes |
| AC-9 | structural-check | `tools/lint-skills`: full run over analyze/SKILL.md | no |

## Technical Notes

- Step 1.10 runs `check-run-outcomes.sh --window 7d`; rc 1 → `/analyze: harness-fidelity audit unavailable`.
- The `lessonsWritten` fence also needs the BUG-228 line (it invokes `emit-run-outcome.sh`).
