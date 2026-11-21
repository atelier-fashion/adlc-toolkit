---
id: TASK-271
title: "`adlc_forge_pr_checks`: one CI read through the forge adapter, on GitHub, Azure DevOps and the mock"
status: complete
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: []
---

## Description

Add the operation `adlc_forge_pr_checks <pr>` to `partials/forge.sh` with its three backends, and the mock's `pr_checks` op and scenarios (architecture ADR-6). It makes one read and never waits.

## Files to Create/Modify

- `partials/forge.sh` — `adlc_forge_pr_checks`, the GitHub and Azure DevOps arms, the mock dispatch (`pr_checks` always goes to the Python mock; the `checks-*` scenario names are accepted), the header's operation list.
- `tools/adlc/forge_mock.py` — `op_pr_checks`, the `checks` list on a PR record, the five `checks-*` scenarios, the `set-checks` helper op, `OPS`, the docstring.
- `tools/adlc/forge_config.py` — only if the Azure DevOps normalizer lives beside the adapter's other ADO readers there.
- `partials/forge.md` — the operation's row, its output contract, the scenarios.
- `partials/tests/forge.test.sh` — stubbed `gh` and stubbed `az` cases, and the mock cases.
- `tools/adlc/tests/test_forge_mock.py` — scenario and store cases.

## Acceptance Criteria

- [ ] Output contract: the first stdout line is `checks=<pass|fail|pending|none>`, then one `check=<pass|fail|pending|skipped>` TAB `<name>` line per check. The return is 0 on every successful read.
- [ ] Verdict: `fail` when any check failed, else `pending` when any is in flight, else `pass` when at least one check is reported, else `none`. A PR whose only checks are skipped reads `pass`.
- [ ] GitHub, with a stubbed `gh`: all passing (exit 0), one failing (exit 1 with rows), one in flight (exit 8 with rows), a cancelled check (reads `fail`), and `no checks reported` on stderr with exit 1 (reads `none`, return 0). An unknown PR returns non-zero with `error_class=pr-not-found`. The command run is `gh pr checks <pr> --json name,bucket` with a `--jq` filter.
- [ ] Azure DevOps, with a stubbed `az`: `Build` and `Status` policy evaluations map `approved`, `rejected`, `broken`, `queued`, `running` and `notApplicable` as ADR-6 says; a reviewer policy is not listed; no evaluations reads `none`.
- [ ] Mock: each of `checks-pass`, `checks-fail`, `checks-pending`, `checks-none` prints its verdict; `checks-pending-then-pass` prints `pending` on a PR's first read and `pass` afterwards, and is an error without a store; an error-class scenario returns non-zero with that class; a PR with no `checks` recorded reads `none`; `set-checks` then a read prints the stored list.
- [ ] A check name holding a tab or a newline is printed on one line with spaces.
- [ ] Every other operation behaves as before under a `checks-*` scenario.
- [ ] `sh partials/tests/run.sh` passes under every installed shell, and `sh tools/lint-skills/check.sh` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-22 | test-case | `partials/tests/forge.test.sh`: the `pr_checks` GitHub and Azure DevOps cases | yes |
| BR-23 | test-case | `tools/adlc/tests/test_forge_mock.py::test_req719_pr_checks_scenarios` | yes |
| AC-17 | test-case | `partials/tests/forge.test.sh`: the `pr_checks` mock, GitHub and Azure DevOps cases | yes |
| AC-17 | test-case | `tools/adlc/tests/test_forge_mock.py::test_req719_pr_checks_from_the_store` | yes |

## Technical Notes

- Measured on `gh` 2.103.3 (architecture, "Evidence first"): no checks is exit 1 with `no checks reported on the '<branch>' branch` on stderr; pending is exit 8. Decide the verdict from the rows when there are any, and from stderr only when there are none.
- `_adlc_forge_run` treats a non-zero status as a failure and classifies stderr. This operation needs its own capture, because 1 and 8 are answers.
- POSIX shell only, no `local`, the adapter's variable prefix convention (`adlc_fc_*`).
- The mock's error scenarios return before `calls.log` is written. Do not change that here.
- No fence anywhere calls the operation yet (TASK-274 adds it), so no census golden changes in this task. If `python3 tools/adlc/fence_census.py --check` or `tools/adlc/tests/test_exec_reach.py` fails because a partial gained reach, stop and report it: the goldens belong to TASK-273.
