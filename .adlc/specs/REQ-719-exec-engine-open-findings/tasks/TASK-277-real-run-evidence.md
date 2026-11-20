---
id: TASK-277
title: "Evidence: one whole pipeline on real Codex past Phase 7 against the mock forge, and one real GitHub read"
status: draft
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: [TASK-274, TASK-275]
---

## Description

Record the two measurements BR-26 asks for. Both are operator-requested runs: the Codex launch spends the operator's plan, and the orchestrator runs them itself after asking, not a subagent.

## Files to Create/Modify

- `.adlc/research/harness-probes/codex-exec-manual.md` — a new launch row, and a section with the output of `adlc_forge_pr_checks` against a real GitHub PR.
- `tools/adlc/tests/test_req719_evidence.py` — new: the note holds both records, and the suite's `HOME`, `ADLC_HOME` and `XDG_STATE_HOME` are throwaway directories.

## Acceptance Criteria

- [ ] One `/sprint --exec` launch of a lite REQ with a real `codex exec`, in a throwaway clone with a local bare origin and the stateful mock forge, reaches the merge gate with Phase 7 passed and no `answer` given. The row records the date, the Codex version, the commit of this branch, what Phase 7 read, and how the run ended.
- [ ] `adlc_forge_pr_checks` is run once against a real PR of this repository on GitHub, and its stdout and return status are recorded.
- [ ] The staging follows the recipe already in the note (throwaway `ADLC_HOME`, `XDG_STATE_HOME` and outcomes log; pushes only to the local bare origin; `~/.codex/config.toml` checksummed before and after; no recovery marker left).
- [ ] The whole suite passes with `HOME` pointed at an empty throwaway directory, and leaves no file under the operator's real home.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-26 | test-case | `tools/adlc/tests/test_req719_evidence.py::test_req719_the_note_records_both_real_runs` | no |
| BR-29 | test-case | `tools/adlc/tests/test_req719_evidence.py::test_req719_the_suite_runs_under_a_throwaway_home` | yes |
| AC-20 | test-case | `tools/adlc/tests/test_req719_evidence.py::test_req719_the_note_records_both_real_runs` | no |
| AC-23 | test-case | `tools/adlc/tests/test_req719_evidence.py::test_req719_the_suite_runs_under_a_throwaway_home` | yes |

## Technical Notes

- The evidence is the run and its record. No test can stand for it (LESSON-891): the test only checks that the note carries the two records.
- Never pass `--dangerously-skip-permissions`. Never read or print a credential. `approve` only on the operator's literal instruction naming the REQ.
- If the launch finds a defect in this requirement's code, fix it under this requirement and launch again; record every launch, as BUG-287 did.
