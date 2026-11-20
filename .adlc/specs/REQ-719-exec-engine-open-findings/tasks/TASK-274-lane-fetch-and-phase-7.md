---
id: TASK-274
title: "Skill text: the lane check fetches with explicit destinations, and Phase 7 reads its diff locally and its CI through the adapter"
status: complete
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: [TASK-271, TASK-273]
---

## Description

Change the two skill files' fences and text (architecture ADR-2 and ADR-6, Phase 7), and regenerate the census goldens for the new fence ids.

## Files to Create/Modify

- `proceed/phases-lite.md` — the lane check fence's fetch line becomes the explicit-destination form. Nothing else in the fence changes.
- `partials/lane-check.sh` — header comment: the caller's fetch is the explicit form. No code change.
- `partials/lane-check.md` — the same, in the call protocol's prose.
- `proceed/phases-6-8-ship.md` — Phase 7: the diff fence, the CI fence, the verdict handling, the two config keys, the end-of-phase line. No `gh` command remains in Phase 7.
- `proceed/SKILL.md` — the Phase 7 paragraph: no `gh` command; one sentence on the verdicts.
- `tools/adlc/fence_census.py` — the `ciWait` placeholder (0 to 90). Nothing else.
- `templates/config-template.yml` — a commented `proceed:` block with `ci.max_reads` (20) and `ci.interval_s` (30).
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json` — regenerated.
- `tools/adlc/tests/test_lane_fence_single_branch.py` — new: the real fence on a `--single-branch` clone.
- `tools/adlc/tests/test_phase7_text.py` — new: Phase 7's text and fences.
- `tools/lint-skills/tests/test_lite_lane_contract.py`, `tools/adlc/tests/test_lane_check.py`, `tools/adlc/tests/test_fence_run.py`, `tools/adlc/tests/test_exec_prompt.py` — pins that move, if any.

## Acceptance Criteria

- [x] The lane check fence fetches with `git -C "$wt" fetch origin "+refs/heads/$ib:refs/remotes/origin/$ib" "+refs/heads/$br:refs/remotes/origin/$br"`. Every guard before it and every line after it is unchanged.
- [x] In a throwaway `--single-branch` clone with the REQ's branch pushed, the fence run through `fence-run` prints `lane_check=pass` for a change inside the lite lane, and `refs/remotes/origin/<branch>` exists afterwards. With the remote made unreachable it prints `trigger=check-error` and the fetch detail. With an unpushed commit it prints the `HEAD is not origin/<branch>` detail. On an ordinary clone the verdict is what it was.
- [x] `fence-run show proceed/phases-lite.md` prints a runner call for the lane check fence under its new id, and both goldens hold that id.
- [x] `partials/lane-check.sh`'s header and `partials/lane-check.md` show the explicit fetch.
- [x] Phase 7's diff fence takes `<worktree>`, `<integrationBranch>` and `<branch>`, fetches with the same form, prints an error and no diff when `HEAD` is not the remote branch's head, and otherwise prints the three-dot, rename-aware diff from `origin/<integrationBranch>` to `HEAD`.
- [x] Phase 7's CI fence is `sleep '<ciWait>'` then `adlc_forge_pr_checks '<prNumber>'`, with the canonical root line and the guarded source of `forge.sh`. Both goldens route both new fences `runner`, the CI fence's record is `tied`, and `fence-run show proceed/phases-6-8-ship.md` prints a runner call for each.
- [x] The CI fence called with another PR's number exits 65 (the tie), and with `ciWait=91` exits 65 (the pattern).
- [x] Phase 7's text states: `pass` (the end-of-phase line says CI is green), `none` (it says no CI checks are reported, and the phase continues), `fail` (the failing checks are named and handled as a Phase 7 issue: fix, commit, push, read again), `pending` (read again with `ciWait` set to `proceed.ci.interval_s`, at most `proceed.ci.max_reads` reads in all); the two keys with their defaults 20 and 30, and that an interval above 90 is read as 90; that on the last read still `pending` the phase never reports green, a solo run asks the operator, and an unattended run reports `blocked` naming the pending checks.
- [x] No `gh` command appears in Phase 7 of `proceed/phases-6-8-ship.md` or in the Phase 7 paragraph of `proceed/SKILL.md`; a test asserts both.
- [x] `exec_prompt.py`'s anchors still match exactly once: `Continue to Phase 8 immediately.` stays in Phase 7's end-of-phase line, and every `_LITE_PAIRS` anchor is untouched. The prompt scan passes on the new text.
- [x] `templates/config-template.yml` documents both keys in a commented block, and `test_lane_check.py`'s template tests pass.
- [x] `proceed/SKILL.md` stays under 500 lines. `sh tools/lint-skills/check.sh`, `python3 tools/adlc/fence_census.py --check`, `python3 -m pytest tools/adlc/tests` and `pytest tools/lint-skills/tests` pass.
- [x] `templates/permissions.yml` and every file under `harness/*/rendered/` are unchanged.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_lane_fence_single_branch.py::test_req719_single_branch_clone_reaches_the_engine_verdict` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_lane_fence_single_branch.py::test_req719_errors_are_still_errors` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_lane_fence_single_branch.py::test_req719_partial_and_goldens_name_the_explicit_fetch` | no |
| BR-24 | test-case | `tools/adlc/tests/test_phase7_text.py::test_req719_phase_7_names_no_gh_command` | no |
| BR-24 | test-case | `tools/adlc/tests/test_phase7_text.py::test_req719_diff_fence_refuses_an_unpushed_head` | yes |
| BR-25 | test-case | `tools/adlc/tests/test_phase7_text.py::test_req719_phase_7_states_each_verdict_and_the_wait` | no |
| BR-27 | structural-check | `tools/lint-skills`: `allowlist-fidelity`, `render-parity`, `toolkit-root-line`, `unguarded-source`, `skill-line-budget` | no |
| AC-6 | test-case | `tools/adlc/tests/test_lane_fence_single_branch.py::test_req719_single_branch_clone_reaches_the_engine_verdict` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_lane_fence_single_branch.py::test_req719_partial_and_goldens_name_the_explicit_fetch` | no |
| AC-18 | test-case | `tools/adlc/tests/test_phase7_text.py::test_req719_phase_7_fences_route_runner` | yes |
| AC-19 | test-case | `tools/adlc/tests/test_phase7_text.py::test_req719_phase_7_states_each_verdict_and_the_wait` | no |

## Technical Notes

- A fence's id is a hash of its body: the lane check fence gets a new id, and Phase 7's fences are new ordinals in `proceed/phases-6-8-ship.md`. Regenerate with `python3 tools/adlc/fence_census.py --write` and commit both goldens.
- New fences follow conventions.md "Bash in skills": the byte-exact root line, the guarded two-level source, POSIX shell, placeholders inside single quotes.
- `tools/lint-skills/tests/test_lite_lane_contract.py` requires `fetch origin` before the partial is sourced in the lane fence, and `adlc_lane_check ` exactly once in the file. The explicit form keeps both.
- Phase 7 has no fence today. Check each new fence routes `runner` on both adapters: the diff fence's reach is `git fetch`, `git rev-parse`, `git diff`; the CI fence's is the adapter's.
- `ciWait`'s pattern admits 0 to 90 and nothing else.
- The fence does not read `.adlc/config.yml`: the text tells `/proceed` to read the two keys with its file tool, as it reads `branches.integration`.
- Keep Phase 7 step 5 (the lite lane's re-run of the lane check) as it is.
