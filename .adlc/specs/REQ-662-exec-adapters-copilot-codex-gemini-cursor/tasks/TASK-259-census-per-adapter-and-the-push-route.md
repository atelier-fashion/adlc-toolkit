---
id: TASK-259
title: "One fence census per adapter, a runner that accepts the union, and the branch push through the runner"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-256]
---

## Description

Implement architecture ADR-8 and ADR-9. Remove the census's `claude` defaults, add the `matcher` field's effect on the `direct` route, make `fence-run` accept the union of `runner` routes audited against the union of deny tiers, and give the Step 0 branch push a `runner` route on a `matcher: none` adapter. Amend REQ-682 BR-2 to name the mechanism.

## Files to Create/Modify

- `tools/adlc/fence_census.py` — `census(root, adapter)` with no harness default; `matcher: none` never routes `direct`; the golden path is per adapter; `--check` and `--write` cover every exec-capable adapter; a second `PUSH_REACH` kind for the exact branch push; the reach audit runs against the union of deny tiers; the `branch` placeholder pattern of ADR-9.
- `tools/adlc/fence_run.py` — `find` accepts a fence that is `runner` in any exec-capable adapter's census; the push fence's `worktree` value must be the calling directory.
- `tools/adlc/exec_prompt.py` — the fence rewrite takes the run's adapter; the one added sentence at the push fence for a `matcher: none` adapter, anchored and matched exactly once like every other rewrite.
- `tools/adlc/exec_adapter.py` — `vet_extra` refuses any `allow_extra` or `allow_extra_exact` on `matcher: none`.
- `harness/claude/exec-fence-census.json` — regenerated only if the file's format changes; its routes must not.
- `.adlc/specs/REQ-682-exec-fences-run-without-widening/requirement.md` — BR-2's first push exception names both mechanisms, with a dated amendment entry.
- `tools/adlc/tests/test_fence_census.py`, `tools/adlc/tests/test_fence_run.py`, `tools/adlc/tests/test_exec_reach.py`, `tools/adlc/tests/test_exec_prompt.py`.

## Acceptance Criteria

- [ ] On the `matcher: none` fixture adapter no fence is `direct` and none is `unrouted`; the Step 0 push is `runner`.
- [ ] On `claude` every route is what the committed golden says.
- [ ] The push fence is refused by the audit if its argv is anything but `git -C $ADLC_ARG_worktree push -u origin $ADLC_ARG_branch`: a `--force`, a second refspec and an option before `push` each fail.
- [ ] `fence-run run` of the push fence refuses a branch value of `main`, `+feat/x`, `feat/x:main`, `--force` and an empty string, and a `worktree` value that is not the calling directory, each with exit 3 and `opaque_entry_refused`. A well-formed call pushes to a throwaway local bare remote (the must-not-refuse case).
- [ ] An unrouted fixture fence refuses the prompt build with `exec_prompt_refused`.
- [ ] A fence that is `runner` on one adapter and `direct` on another is accepted by `fence-run`; a fence that is `runner` on none is refused.
- [ ] `fence_census --check` fails when any adapter's golden is stale.
- [ ] A decoy at the working copy's `.adlc/partials/` writes no sentinel (REQ-682 ADR-4).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_fence_census.py::test_matcher_none_routes_nothing_direct` | yes |
| AC-24 | test-case | `tools/adlc/tests/test_fence_run.py::test_runner_accepts_the_union_of_runner_routes` | yes |
| BR-19 | test-case | `tools/adlc/tests/test_exec_reach.py::test_reach_runs_against_the_union_of_deny_tiers` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_fence_run.py::test_branch_push_refuses_every_other_spelling` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- Pushes in tests go only to a throwaway local bare remote.
- The runner trusts only its own real path and the toolkit files under it (REQ-682 ADR-2). Discover exec-capable adapters from `harness/*.yml` under that root; read no environment variable, argument or working-copy file to choose a census.
- The reach audit follows every executable a fence runs through a variable (LESSON-845).
- Measured on 2026-11-17 with `direct` disabled: 59 of 60 fences route, and the one that does not is `proceed/phase-0-setup.md#6`, the branch push.
- Lessons in play: LESSON-779 (a rule that withholds an allow can withhold a step the pipeline cannot run without), LESSON-718 (a gate must not load anything the change can edit).
