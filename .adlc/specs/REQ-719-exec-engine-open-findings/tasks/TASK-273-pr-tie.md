---
id: TASK-273
title: "The PR tie: a mark on the placeholder, the runner checks a PR number is its caller's PR, and an unmarked PR argument does not route"
status: complete
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: [TASK-272]
---

## Description

Implement architecture ADR-3. A value bound to a placeholder that carries the PR mark is checked, through the forge adapter, to be the PR of the branch checked out where the runner was called, before any command of the fence runs.

## Files to Create/Modify

- `tools/adlc/fence_census.py` — the `pr` slot on `Placeholder`; the mark on `prNumber` in `PLACEHOLDERS` and in `VAR_PLACEHOLDERS`; the function that returns the check's shell text for one value; that text added to what a tied fence's reach is computed from; `"tied"` in a runner record; the routing rule in `plan` for an unmarked PR argument.
- `tools/adlc/fence_run.py` — `UNVERIFIED = 75`; the check in `run()`, after `sandboxed` and before the fence; the docstring's status table.
- `tools/adlc/exec_prompt.py` — one sentence added to `_EXEC_NOTES` for exit 75, after the existing sentences, which stay byte-identical.
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json` — regenerated.
- `tools/adlc/tests/test_fence_pr_tie.py` — new.
- `tools/adlc/tests/fixtures/exec-fence/` — a fixture fence that passes an unmarked placeholder as the PR argument of `adlc_forge_pr_edit`.
- `tools/adlc/tests/test_fence_run.py`, `tools/adlc/tests/test_exec_reach.py`, `tools/adlc/tests/test_fence_census.py`, `tools/adlc/tests/test_exec_prompt.py` — the existing suites that run every runner fence with `pr=101`, and the pins that move.
- `tools/adlc/fence_run.py` (`run`, `parse_values`, `read_arg_file`'s optional third parameter) and `tools/adlc/tests/test_fence_arg_file.py` — added at implementation: `run()` passed `os.getcwd()`, always the real spelling, so an absolute `--arg-file` path in the shell's spelling (`$PWD`, macOS's `/var`) was refused against BR-16. `$PWD` is now accepted as a spelling when it names the same directory.

## Acceptance Criteria

- [x] With the mock store holding the caller's PR on the checked-out branch and a second PR on another branch: the Phase 6 fence (`proceed/phases-6-8-ship.md#1`) called with the second PR's number exits 65 with one `fence_run_bad_value:` line, and the second PR's title, body and `isDraft` are unchanged; called with the caller's PR number it runs. The same two results hold for the lite escalation fence (`proceed/phases-lite.md#3`).
- [x] Exit 65 as well for: the mock's `cross-repo` scenario, its `head-other` scenario, a closed PR on the caller's own branch, and a number the forge does not know. The line names the value and the checked-out branch and holds no title, body, URL or head of the PR that was read.
- [x] With an error-class scenario (`network`, `auth-missing`) the fence exits 75 with one `fence_run_unverified:` line and nothing is changed. On a detached `HEAD` it exits 3 with one `opaque_entry_refused:` line and no forge call is recorded.
- [x] A call that reads `fence_run_sandboxed` (69) records no forge call, and a call whose value fails its pattern (65) records none.
- [x] Step 0's draft-PR fence (`proceed/phase-0-setup.md`, `adlc_forge_pr_create`) runs with no `pr_view` recorded before its own calls.
- [x] The fixture fence is unrouted: the census check fails and its message names the fence and the placeholder. `/architect` Step 5's `$prnum`, read by the fence from a command's output, still routes as it does today.
- [x] Every entry of `PLACEHOLDERS` and `VAR_PLACEHOLDERS` whose pattern is the PR-number pattern carries the mark (a test walks both tables).
- [x] The delivered exec prompt holds the sentence for 75: nothing ran, run the line once more, and if it answers the same way report it as a blocker. The prompt scan passes, and `test_bug287_prompt_says_how_to_call_the_runner`'s substrings are still present.
- [x] `python3 tools/adlc/fence_census.py --check` passes, and the reach audit passes with the runner's read recorded in the stubbed run of each tied fence.
- [x] `templates/permissions.yml` and every file under `harness/*/rendered/` are unchanged, and `tools/adlc/tests/test_harness_adapters.py` passes.
- [ ] `python3 -m pytest tools/adlc/tests` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_only_the_callers_open_pr_passes` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_another_pr_is_a_bad_value_and_is_untouched` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_an_unreadable_forge_is_unverified_not_a_pass` | no |
| BR-11 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_a_detached_head_is_a_refusal` | no |
| BR-11 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_only_the_callers_open_pr_passes` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_the_verdict_reads_four_fields_and_fails_closed` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_the_adapters_own_refusal_is_passed_through` | no |
| BR-12 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_no_forge_call_before_the_value_and_sandbox_checks` | no |
| BR-12 | test-case | `tools/adlc/tests/test_exec_reach.py::test_real_tree_reach_matches_golden` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_an_unmarked_pr_argument_does_not_route` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_every_pr_number_placeholder_carries_the_mark` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_an_unmarked_pr_argument_is_unroutable` | no |
| BR-13 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_every_operation_but_create_and_list_takes_a_pr` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_a_fence_that_takes_no_pr_number_reads_no_pr` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_a_marked_or_fence_made_pr_argument_routes` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_an_absolute_path_in_the_shells_spelling_is_read` | yes |
| BR-27 | test-case | `tools/adlc/tests/test_harness_adapters.py::test_no_flag_writes_nothing_new` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_another_pr_is_a_bad_value_and_is_untouched` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_req719_prompt_says_what_75_means` | no |
| AC-10 | test-case | `tools/adlc/tests/test_fence_pr_tie.py::test_req719_no_forge_call_before_the_value_and_sandbox_checks` | no |
| AC-11 | test-case | `tools/adlc/tests/test_fence_census.py::test_req719_an_unmarked_pr_argument_does_not_route` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_harness_adapters.py::test_no_flag_writes_nothing_new` | yes |

## Technical Notes

- The check's shell text lives once, in `fence_census`, and `fence_run` runs exactly that text with the fence's own preload and `child_env`. The reach computation reads the same text, so the two cannot drift (LESSON-845).
- Compare `number` (as an integer), `state` (`OPEN`), `headRefName` (the output of `checked_out_branch`) and `isCrossRepository` (`false`). Read the `key=value` lines the `--fields` form prints.
- Status mapping: `error_class=pr-not-found` is 65. A status 3 from the adapter with an `opaque_entry_refused:` line (Azure DevOps under the runner) is passed through as 3. Any other failure, output that does not parse, or no answer in 60 seconds is 75.
- The mock's error scenarios are not written to `calls.log`. Count forge calls with a scenario that is not an error class.
- Several existing tests run every runner fence with `pr=101` in a directory that is not a repository (`test_safe_forge_fences_run_under_mock`, `test_real_tree_reach_matches_golden`, the hostile-value loops). Give them a working copy with a branch and a mock store whose PR 101 is on that branch. Do not stub the check out of the reach test: its record of the read is the evidence for BR-12.
- Regenerate the goldens with `python3 tools/adlc/fence_census.py --write`. No fence body changes in this task, so no fence id changes; only the `tied` key appears.
- Message for 65 follows the existing shape: `fence_run_bad_value: <id>: value for <name> is not the PR of the branch checked out here (<branch>). Nothing ran: correct that value and run the line again.`
- The 75 sentence must hold none of `exec_prompt.EMPTY_ALLOWLIST`'s tokens.
- As implemented, BR-13's "a variable the fence assigns from text that holds one" (`fence_census.tainted_vars`): a variable is tainted when the fence gives it a value from text holding an unmarked placeholder, an unmarked free variable a table names, or an already tainted variable, computed to a fixed point. The text is the value of an assignment word (`x=…`), the words of a `for x in …` header, and, for every variable a `read` sets, each here-document body in the fence. Command substitutions (`$(…)`, backticks) are taken out of that text first: what a command prints is not a value the model supplied (BR-14), which is how `pr=$(adlc_forge_pr_create …)` and `/architect` Step 5's `$prnum`, read from a pipe, stay untainted. `$((…))` stays. The PR argument itself is held more strictly: every positional word of the call (options, their values and redirections skipped; an unknown option is read as taking none) is checked, substitutions included. The operations checked are every `adlc_forge_pr_*` but `pr_create` and `pr_list` (`fence_census.is_pr_operation`), a superset of BR-13's six, so an operation the adapter gains later starts checked (LESSON-781).
