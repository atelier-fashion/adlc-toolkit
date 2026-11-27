---
id: TASK-289
title: "The verb census test, and the checks that nothing was widened"
status: draft
parent: REQ-720
repo: adlc-toolkit
created: 2026-11-27
updated: 2026-11-27
dependencies: [TASK-286]
---

## Description

Add the BR-13 census as a test over the engine's `VERBS` and each shipped adapter's
`engine_deny`, and the tests that hold BR-25 and BR-26: the relaunch prompt for a reply is what
`exec_prompt.pipeline_prompt` builds from the reply alone, and the new suite leaves nothing
under the real home.

## Files to Create/Modify

- `tools/adlc/tests/test_req720_verb_census.py` — new.

## Acceptance Criteria

- [ ] `classify(verbs)` in the test module maps every verb of `sprint_exec.VERBS` to `mints`, `spends` or `neither` from one table (`run`, `resume`, `reissue` mint; `approve`, `answer` spend; `reject`, `abort`, `status` neither) and raises on a verb the table lacks.
- [ ] `missing_from_deny(verbs, engine_deny)` returns the minting and spending verbs with no `[adlc, sprint-exec, <verb>]` entry. It returns nothing for `harness/claude.yml` and `harness/codex.yml`, read with the repository's own YAML loader, and the test iterates every `harness/*.yml` that has an `exec` block, so a new adapter is covered without an edit.
- [ ] A fixture `engine_deny` without `reissue` yields `["reissue"]`, and a fixture verb list holding `frobnicate` makes `classify` raise naming it.
- [ ] The test asserts that `sprint_exec._parser()`'s sub-commands are exactly `VERBS`.
- [ ] After a blocked run is answered with a reply, `prompt.2.txt` in the run directory equals, byte for byte, `exec_prompt.pipeline_prompt(...)` called with that reply and the arguments `_relaunch` passes, and holds neither the token nor its digest.
- [ ] A test walks the sandbox's throwaway home after a blocked-answered run and finds every file the engine wrote under the sandbox's temporary root; the real home's path appears in no path the engine recorded in the run record.
- [ ] `python3 -m pytest tools/adlc/tests/test_req720_verb_census.py tools/adlc/tests/test_fence_census.py tools/adlc/tests/test_exec_reach.py tools/adlc/tests/test_exec_prompt.py -q` passes, and `python3 tools/adlc/adlc.py harness render --check` exits 0.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_every_minting_or_spending_verb_is_denied_by_each_adapter` | yes |
| BR-25 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_the_relaunch_prompt_is_the_reply_and_nothing_new` | no |
| BR-25 | test-case | `tools/adlc/tests/test_fence_census.py` (both census goldens), `adlc harness render --check` (the interactive render) | no |
| BR-26 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_the_suite_writes_nothing_under_the_real_home` | no |
| AC-11 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_the_census_fails_on_a_missing_deny_and_on_an_unclassified_verb` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_the_relaunch_prompt_is_the_reply_and_nothing_new` | no |
| AC-22 | test-case | `tools/adlc/tests/test_req720_verb_census.py::test_the_suite_writes_nothing_under_the_real_home` | no |

## Technical Notes

- `sprint_exec.VERBS` is added by TASK-286. If it is not there yet when you start, stop and say so.
- Existing readers of `engine_deny` to copy the loading from: `tools/adlc/tests/test_exec_launch.py` near line 1957, `tools/adlc/tests/test_exec_reach.py` near line 247.
- The byte-identity of `.claude/settings.json` and of `harness/claude/exec-fence-census.json` and `harness/codex/exec-fence-census.json` with `origin/main` is checked by the pipeline on the final diff (`git diff --quiet origin/main...HEAD -- <those paths>`), not by a pinned hash in a test: a hash would fail on the next requirement that legitimately changes one (LESSON-403).
- Use `box.answer(orch, req, text)` from `exec_helpers.py` (TASK-286) to answer.
- This task edits no engine file. Another task is editing `tools/adlc/sprint_exec.py` at the same time: if an import of it fails with a syntax error that is not yours, wait a minute and run again. Do not commit.
