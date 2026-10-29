---
id: TASK-178
title: "lint-skills harness-skip covers the run-outcome fence; architecture.md and CHANGELOG entries"
status: draft
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171]
repo: adlc-toolkit
---

## Description

Extend `tools/lint-skills/check.py`'s `harness-skip` check so a fence that invokes
`emit-run-outcome.sh` needs the BUG-228 line within 30 lines above it, as an
`adlc_delegate_gate_check` fence does. Add fixtures and tests. Add the run-outcome
telemetry entry to `.adlc/context/architecture.md` "Key cross-cutting
dependencies" and a CHANGELOG `[Unreleased]` entry.

## Files to Create/Modify

- `tools/lint-skills/check.py` — `HARNESS_SKIP_RUN_OUTCOME_RE`; `check_harness_skip` matches either call
- `tools/lint-skills/tests/test_check.py` — run-outcome fence without the line fires; with it, clean; a commented-out call does not count
- `tools/lint-skills/tests/fixtures/harness-skip-run-outcome-missing/SKILL.md` — new fixture
- `tools/lint-skills/tests/fixtures/harness-skip-run-outcome-ok/SKILL.md` — new fixture
- `.adlc/context/architecture.md` — "Key cross-cutting dependencies" entry beside the delegation telemetry one
- `CHANGELOG.md` — `[Unreleased]` entry

## Acceptance Criteria

- [ ] A fence calling `emit-run-outcome.sh` without the line draws exactly one `harness-skip` finding; with it, none
- [ ] `tools/lint-skills/check.sh` passes over the repo and reports `scanned N` with N > 0
- [ ] `pytest tools/lint-skills/tests` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/lint-skills/tests/test_check.py::test_harness_skip_run_outcome_fires` | no |
| BR-3 | test-case | `tools/lint-skills/tests/test_check.py::test_harness_skip_run_outcome_clean` | yes |
| AC-12 | test-case | `tools/lint-skills/tests/test_check.py::test_harness_skip_run_outcome_fires` | yes |
| AC-14 | test-case | `tools/lint-skills/check.sh` over the repo (scanned > 0) | no |
| BR-12 | structural-check | `tools/lint-skills`: full run | no |

## Technical Notes

- Match on non-comment fence lines only, as the gate regex does.
