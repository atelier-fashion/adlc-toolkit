---
id: TASK-281
title: "Quickstart end-to-end driver and outcome checks"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-278]
repo: adlc-toolkit
---

## Description

Write the driver that runs the quickstart page's own steps in a sandbox `HOME`, and the
checker that judges the BR-9 outcomes from the disk and the forge (architecture ADR-5).
The real run needs a model session and a throwaway GitHub repo and is the maintainer's;
this task proves the driver and the checks with fake `claude` and `gh` binaries and
fixtures, and makes no real `claude` call.

## Files to Create/Modify

- `tools/launch/quickstart_check.py` — the five outcome checks, each returning PASS or FAIL with a reason
- `tools/launch/quickstart_e2e.py` — the driver: options, sandbox, environment allowlist, step execution with the three `e2e` substitutions, `--demo` output, exit contract
- `tools/launch/tests/test_quickstart_check.py` — the checker over one complete fixture and five that each lack one outcome
- `tools/launch/tests/test_quickstart_e2e.py` — the driver with fake binaries on `PATH`
- `tools/launch/tests/fakes.py` — helpers that write the fake `claude` and `gh` executables

## Acceptance Criteria

- [x] The checks are `plugin-installed`, `adlc-scaffold`, `lite-req`, `pr-merged` and `lesson-or-no-entry`; each reads the sandbox, the project directory or `gh`, and none reads model prose except the `NO_ENTRY:` line of the final result
- [x] A fixture holding every outcome passes all five; each of five fixtures lacking one outcome fails exactly that check
- [x] `lite-req` requires a `.adlc/specs/REQ-*/requirement.md` whose frontmatter has `lane: "lite"`; a REQ with `lane: "full"` or no lane fails it
- [x] The driver takes its steps from `docs/quickstart.md` through `quickstart_steps.py` and holds no copy of a command or prompt
- [x] Without `--with-model`, or without `--throwaway-repo`, the driver runs no step, prints why, and exits 2
- [x] `--throwaway-repo` is refused unless it is `OWNER/NAME` and the name contains `e2e`
- [x] The sandbox is a fresh temp directory that is not the real home and not inside a git tree, and it is removed on exit unless `--keep`
- [x] The child environment holds only the allowlisted names; a canary variable set in the test process does not reach the fake `claude`, and the model credential and `GH_TOKEN` are passed by name and appear in no output of the driver
- [x] With fake binaries that produce every outcome, the driver runs the eight steps in order, applies `existing-repo`, `init-prompt` and `req-id`, resumes the session for the `answer` step, and exits 0
- [x] With a fake `claude` that leaves one outcome out, the driver exits 1 and names the failed check
- [x] `--demo` prints each step as typed, then its output, and nothing that contains the sandbox path's parent or an environment value
- [x] `--marketplace <path>` replaces only the source in step 1

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | test-case | `tools/launch/tests/test_quickstart_check.py::test_each_missing_outcome_fails_its_own_check` | yes |
| AC-2 | test-case | `tools/launch/tests/test_quickstart_e2e.py::test_driver_runs_the_page_steps_and_passes_with_every_outcome` | yes |

Lessons: LESSON-581, LESSON-019, LESSON-572, LESSON-899

## Technical Notes

- `tools/adlc/tests/e2e/plugin-sandbox.sh` is the policy this mirrors: read its sandbox guards, its environment handling (`helpers.py`, written by heredoc near line 190) and `e2e_claude` (near line 850). Do not edit that file and do not source it.
- The headless call is `claude -p <prompt> --session-id <uuid> --output-format stream-json --verbose --max-budget-usd <n> --permission-mode acceptEdits --allowedTools <list>`; an answer is `claude -p <answer> --resume <uuid>` with the same flags. Do not append a "do not ask questions" system prompt: the page's own answer step is what is under test.
- Name the model credential variables in one constant. Never read, print, log or compare their values; pass them by copying the mapping entry.
- `plugin-installed` reads `claude plugin list --json` in the sandbox; `pr-merged` reads `gh pr list --state merged --json number,headRefName` for the throwaway repo; `lesson-or-no-entry` accepts a `LESSON-*.md` under `.adlc/knowledge/lessons/` or a line beginning `NO_ENTRY:` in the last run's result text.
- The fake `claude` is a script that, given the prompt it receives, writes the artifacts a real run would (`.adlc/`, a lite REQ, a lesson) into its working directory, and logs its argv and environment names for the tests. A switch in an environment variable tells it which outcome to leave out.
- No literal harness home path under `tools/` (`no-harness-path` walks it): derive every path from the sandbox `HOME` argument.
- Do not name the file `test_*` unless pytest should collect it. Python 3.9, stdlib only.
- **No real binary may answer a test.** Every test that runs a script or driver builds `PATH` from the fake-binary directory plus `/usr/bin:/bin` only (`tools/adlc/tests/exec_helpers.py` `offline_path` is the precedent), and asserts from the fake's own log that the fake was what ran. A test must never reach a real `claude`, `gh`, `asciinema` or `agg`, nor the network.
