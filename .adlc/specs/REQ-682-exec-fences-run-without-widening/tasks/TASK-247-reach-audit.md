---
id: TASK-247
title: "Reach audit in CI: a static closure scan and a stubbed hostile run of every `runner` fence"
status: draft
parent: REQ-682
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-246]
---

## Description

Add `tools/adlc/tests/test_exec_reach.py` (architecture ADR-7). It proves what every `runner` fence can run in two ways. The **static** check takes the transitive function closure over `partials/*.sh` from each fence, and scans it for deny-tier spellings and for code-from-data constructs. The **dynamic** check runs every fence through `fence-run` with recording stubs and hostile values, and matches each recorded argv against the deny tier. Each fence's observed reach is recorded in the census golden, so a change in reach shows in review.

## Files to Create/Modify

- `tools/adlc/fence_census.py` — a `reach` field per `runner` record, plus `EXTERNAL` (the closed table of external commands a fence may call).
- `harness/claude/exec-fence-census.json` — regenerated with reach.
- `tools/adlc/tests/test_exec_reach.py` — new.
- `tools/adlc/tests/fixtures/exec-fence/partials/` — new fixture partials: one admitted function that gains `gh pr merge`, one that gains `git push --force`, and one `runner` fence that calls a function with no index entry.

## Acceptance Criteria

- [ ] Over the real tree, no `runner` fence's closure holds a BR-2 deny-tier spelling, an `eval`, an `sh -c "$…"`, or a `.` of a non-literal operand. The static check names the fence, the function and the `file:line` of any hit.
- [ ] Each fixture function that gains `gh pr merge` or `git push --force` fails the audit. So does a fence calling a function that neither the index nor `EXTERNAL` lists.
- [ ] Every `runner` fence × placeholder × BR-6 value runs under `ADLC_FORGE_MOCK=1` with recording stubs. No recorded argv is matched by `exec_matcher.deny_hits`.
- [ ] The run is not vacuous: the test asserts it executed at least one case per `runner` fence, and fails if the census has no `runner` fences.
- [ ] Benign path: each fence's observed reach equals its golden reach record, and the real tree passes.
- [ ] The id-reservation push (`id-alloc.sh:397`) is reported as reach in the close-out's allocation fences, which are `runner` (amended BR-2).
- [ ] Every recorded push is checked. It must be non-force, its destination must match `^refs/adlc/ids/(req|bug|lesson|assume|task)/[0-9]{3,6}$`, and its source must be an object id. A fixture that records a push to `refs/heads/main`, or a `+` refspec, fails the audit.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_exec_reach.py::test_no_runner_fence_reaches_deny_tier` | no |
| BR-4 | test-case | `tools/adlc/tests/test_exec_reach.py::test_fixture_deny_call_fails_audit` | no |
| BR-4 | test-case | `tools/adlc/tests/test_exec_reach.py::test_unindexed_function_starts_refused` | no |
| BR-4 | test-case | `tools/adlc/tests/test_exec_reach.py::test_real_tree_reach_matches_golden` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_reach.py::test_fixture_deny_call_fails_audit` | no |

## Technical Notes

- The function index is a parse of `name() {` … matching `}` at column 0, which is the style every partial uses. A partial that defines a function another way fails the index build loudly. It is never skipped.
- Stubs return canned success, so the dynamic check proves the paths it reaches, not every branch. The static check is what covers branches. State this residual in the test's docstring.
- Run the dynamic pass in a throwaway `HOME` and `ADLC_HOME` (conftest `_sandbox_home`). No home-directory writes, and no network, because the stubs exit before any `curl` or `gh` call leaves the machine.
