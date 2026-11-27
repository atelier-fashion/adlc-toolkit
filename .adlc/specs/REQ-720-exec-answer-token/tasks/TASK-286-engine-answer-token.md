---
id: TASK-286
title: "The engine mints an answer token when a run blocks, and `answer` spends it"
status: draft
parent: REQ-720
repo: adlc-toolkit
created: 2026-11-27
updated: 2026-11-27
dependencies: []
---

## Description

Implement architecture ADR-1, ADR-3 and ADR-4 in `tools/adlc/sprint_exec.py`: the status
observer that mints and discards, the blocked row with its `answer` line, the token check in
`answer`, the single commit point in `_relaunch`, the `answers` and `answerRefusals` keys,
`reissue` and `resume` for blocked runs, the four events, the `VERBS` constant and the `ping`
capability field. Move every existing test that calls `answer` without a token onto a helper
that reads the token from the dashboard.

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — `Run.on_status` and the `status` setter; the run registry that binds the observer; `Orchestrator.answer_tokens` and `unannounced`; `_status_changed`, `_mint_answer`, `_announce_blocked`; `_terminal` and `_hold` announce; `answer` (token check, refusal count, `answer_refused`); `_relaunch` (the commit point, `answers`, `answer_accepted`); the `reissue` arm of `dispatch`; `resume`; `render_row` (the `answer` line, the refusal count, the last answer); `status_lines`; `VERBS` and `_parser`; the `ping` reply.
- `tools/adlc/tests/exec_helpers.py` — `Sandbox.answer_token(req)`, `Sandbox.answer(orch, req, text, **kw)`; `ways_out` if the row's line needs it.
- `tools/adlc/tests/test_req720_answer_token.py` — new: the cases below.
- `tools/adlc/tests/test_exec_approve.py` — the token-less `orch.answer(...)` calls move to `box.answer(...)`; pins that name the old `answer` line.
- `tools/adlc/tests/test_exec_launch.py` — the same, and the `dispatch` request for `answer`.
- `tools/adlc/tests/test_exec_surfaces.py` — the same.
- `tools/adlc/tests/test_bug290_refused_chained_line.py` — the same.
- `tools/adlc/tests/test_bug291_exec_launch_11_gaps.py` — the same.

## Acceptance Criteria

- [ ] A run that ends `blocked` on a question prints, on the orchestrator's `out`, its row, an `answer it:` line of the form `echo '<32 hex>' | adlc sprint-exec answer --channel skill '<REQ>' '<reply>'`, and the unchanged `abort` line, which holds no token. The same for a protocol violation at exit, a denied harness, a refused halt write, a rebase conflict after `approve` and a trial merge at the retry limit.
- [ ] Setting `run.status = "blocked"` on any run the orchestrator holds leaves a digest in `answer_tokens`; setting any other status afterwards removes it and the run record's `answerRefusals`.
- [ ] The token text and its digest are in no file under the run directory, the working copy, the primary path's spec directory, the supervisor's directory or the run-outcome log, and not in `status_lines`. `status_lines` prints the blocked row with `<token>` in the `answer` line, then the line naming the dashboard and `reissue`.
- [ ] `answer` with no token, a wrong token, another blocked run's token and the run's token from before a `reissue` each raises `Refused`; the run stays `blocked`, `launches` is unchanged, no new prompt file exists, no trust grant is recorded, no child was started. The right token still works after three refusals; the row then showed `3`, the log holds three `answer_refused` events without the value presented, and `violations.jsonl` gained nothing. When the relaunched run blocks again the row shows `0`.
- [ ] With an unverified adapter, the right token without `allow_unverified` is refused and unspent, and the same token with it relaunches. A second `answer` with a spent token is refused whatever the status.
- [ ] After an accepted `answer` the run record holds one `answers` entry (`launch`, `answeredAt`, `answeredBy`, `channel`, `callerPid`) with no token and no reply text, the row names it, the log holds `answer_accepted`, and the new prompt file holds the reply and not the token.
- [ ] The merge worker's own relaunch of a held run needs no token, records no `answers` entry and drops the token; the token printed before it is refused afterwards. When that relaunch is refused for an unverified adapter the run stays `blocked` and the earlier token relaunches it with `allow_unverified`.
- [ ] `reissue` on a blocked run prints a new `answer` line, returns a result holding no token, invalidates the earlier token, and the new one works. `reissue` on a `failed` run is refused naming the status.
- [ ] `resume` over a blocked run prints its row and an `answer` line, that token works, and the stopped supervisor's token is refused. The same for a fixture run record with none of the new keys.
- [ ] `abort` with no token ends a blocked run `failed` with and without a supervisor; the token printed for it is then refused naming `failed`. `reject` with no token still ends a run at the gate, and `reject` on a blocked run is refused naming the status.
- [ ] `ping` returns `answerTokens: true`.
- [ ] `python3 -m pytest tools/adlc/tests/test_req720_answer_token.py tools/adlc/tests/test_exec_approve.py tools/adlc/tests/test_exec_launch.py tools/adlc/tests/test_exec_surfaces.py tools/adlc/tests/test_bug290_refused_chained_line.py tools/adlc/tests/test_bug291_exec_launch_11_gaps.py -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_every_path_into_blocked_mints_and_prints` | no |
| BR-1 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_status_change_to_blocked_holds_a_token` | no |
| BR-2 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_token_is_on_no_disk_and_in_no_status` | no |
| BR-3 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_one_live_token_per_blocked_episode` | no |
| BR-4 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_every_path_into_blocked_mints_and_prints` | no |
| BR-5 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_answer_without_the_current_token_is_refused` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_refusal_that_leaves_the_run_blocked_leaves_the_token` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_three_refusals_then_the_right_token` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_accepted_answer_is_recorded` | no |
| BR-9 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_refusal_that_leaves_the_run_blocked_leaves_the_token` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_engines_own_relaunch_needs_no_token` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_reissue_on_a_blocked_run` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_resume_mints_for_a_blocked_run` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_abort_and_reject_take_no_token` | yes |
| BR-15 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_abort_and_reject_take_no_token` | yes |
| BR-19 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_resume_mints_for_a_blocked_run` | yes |
| BR-21 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_answer_without_the_current_token_is_refused` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_every_path_into_blocked_mints_and_prints` | no |
| AC-2 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_token_is_on_no_disk_and_in_no_status` | no |
| AC-4 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_answer_without_the_current_token_is_refused` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_refusal_that_leaves_the_run_blocked_leaves_the_token` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_three_refusals_then_the_right_token` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_accepted_answer_is_recorded` | no |
| AC-8 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_engines_own_relaunch_needs_no_token` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_reissue_on_a_blocked_run` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_resume_mints_for_a_blocked_run` | yes |
| AC-12 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_abort_and_reject_take_no_token` | yes |

## Technical Notes

- Read `architecture.md` in this directory first; ADR-1, ADR-3 and ADR-4 are the design. Do not edit `exec_trust.py`, `exec_surfaces.py`, `exec_prompt.py`, `harness/*.yml` or any rendered file: a sibling requirement owns the first two.
- `Run.status` setter (`sprint_exec.py` near line 164): call `self.on_status(self, before, value)` only when the value changes and an observer is set. `Run.__init__` sets `self.on_status = None`.
- The registry: `self.runs` becomes a `dict` subclass whose `__setitem__` sets `run.on_status`. `_run()` (near line 2402) loads a run lazily into `self.runs`; a client process that loads a run this way must not print or mint anything by loading it, and it does not, because loading sets no status.
- `self.answer_tokens[req]` holds `el.token_digest(token, "answer:" + req)`. `self.unannounced[req]` holds the token text until `_announce_blocked(run)` prints `render_row(run, violations_of(run), answer_token=token)`.
- `_terminal` announces after its `say("%s %s")` when the status is `blocked`; `_hold` after its own `say`. `_block` already takes the lock around `_terminal`.
- `answer(self, req, text, caller_pid=None, caller_env=None, allow_unverified=False, invocation=None, token=None, answered_by="", channel="shell")`. Order under the lock: `caller_guard`, `_rebasing_guard`, the status check, then the token check. A token that is not a non-empty `str`, or whose digest differs, is one refusal: `run.doc["answerRefusals"] += 1`, `run.save()`, `Toolbox(...).log("answer_refused", ["answer"], None, None, detail={"req", "channel", "callerPid"})`, then `Refused("%s: the answer token is wrong or already spent; the dashboard prints the current one, and `adlc sprint-exec reissue %s` prints a fresh one")`. No `run.violation`.
- `_relaunch(self, run, text, allow_unverified=False, invocation=None, answered=None)`: immediately before `self._launch_first(run, name)`, pop `answer_tokens` and `unannounced` for the run, and when `answered` is given append `dict(answered, launch=run.doc["launches"] + 1, answeredAt=el.now())` to `run.doc["answers"]`, save, and log `answer_accepted`. Nothing earlier in `_relaunch` touches the token.
- `render_row(run, violations=(), answer_token=None)`: for `blocked`, after the blockers, `  refused answers since it blocked: <n>`; the `answer it:` line with the token, or `<token>` when none is passed; the `abort` line unchanged. For any status with `answers`, `  last answer: launch <n> by <who> via <channel>, pid <pid>, at <when>`, the who and channel through `_one_line(value, 80)`.
- `status_lines`: the line naming the dashboard and `reissue` is appended for `blocked` as it is for `awaiting_approval`.
- `reissue` in `dispatch`: accept `blocked`; mint with cause `reissue`, announce, return `{"ok": True, "result": "<REQ>: fresh tokens are on the supervisor's dashboard"}` for both statuses.
- `resume`: for each `blocked` run, mint with cause `resume` and announce.
- `VERBS = ("run", "resume", "status", "approve", "reject", "answer", "abort", "reissue")`, and `_parser()` builds its sub-commands from it. TASK-289's census test reads it.
- Tests run under the `Sandbox` of `tools/adlc/tests/exec_helpers.py` (`box.blocked()`, `box.go()`, `box.orch()`, `box.out`, `eh.events(box, run, kind)`), which already points `HOME`, `ADLC_HOME` and `XDG_STATE_HOME` at throwaway directories. `box.answer_token(req)` reads the last `answer it: echo '<hex>'` for the REQ from `box.out`; `box.answer(orch, req, text, **kw)` passes it as `token=`.
- Existing token-less call sites to move: 10 in `test_exec_approve.py`, 4 plus one `dispatch` in `test_exec_launch.py`, 4 in `test_exec_surfaces.py`, 3 in `test_bug291_exec_launch_11_gaps.py`, 1 in `test_bug290_refused_chained_line.py`. A test that asserts a refusal for a reason that comes before the token check (status, rebasing, the caller guard) keeps its meaning; give it the real token where one exists so the refusal it pins is the one it names.
- TASK-287 changes `dispatch` to refuse a `None` pid. Leave the `dispatch(request, None)` call sites for it, except the `answer` one, which needs a token now: give it `os.getpid()`.
- Do not commit. The orchestrating session reviews and commits.
