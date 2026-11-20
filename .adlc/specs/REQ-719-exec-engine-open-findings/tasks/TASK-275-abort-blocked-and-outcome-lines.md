---
id: TASK-275
title: "The exec engine: `abort` drops a blocked run, `reject` records `rejected`, `abort` records `aborted`"
status: draft
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: [TASK-270]
---

## Description

Implement architecture ADR-1 in `tools/adlc/sprint_exec.py`, and make the engine write the two new run-outcome values TASK-270 added.

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — `abort` (the `blocked` arm, the `awaiting_approval` refusal that names `reject`, `exec.abortedFrom` in both arms, `aborted` as the emitted reason, the printed line, `_release_holds()`); `reject` (emits `rejected` with an empty reason); `_prepare`'s initial `exec` keys (`abortedFrom`); `render_row` (a blocked run's row names `answer` and `abort`).
- `tools/adlc/tests/test_exec_approve.py`, `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_exec_gates.py` — new cases, and the pins that move (`match="no live process"`, the `failed` / `other` lines).
- `tools/adlc/tests/exec_helpers.py` — a helper for a blocked run, if the suites need one.

## Acceptance Criteria

- [ ] With a fake-harness run at `blocked` and no live process, `abort` returns normally. The run reads `failed` with `exec.abortedBy`, `exec.abortedAt` and `exec.abortedFrom: blocked`. The remote branch's oid is unchanged; the mock's PR is unchanged (`state`, `isDraft`, title, body); the working copy's directory exists with every engine-rendered path restored; no trust grant is recorded; the run's command log holds no `one_way_move` entry; the mock's `calls.log` gains no line from the abort.
- [ ] The command prints one line naming the REQ, who aborted it, the working copy's path, the branch, and the PR URL when one is recorded.
- [ ] The same result through the CLI with no supervisor running. With a live supervisor whose last open run is the blocked one, the supervisor's loop ends after the `abort` with no signal sent.
- [ ] A run approved and then blocked by a rebase conflict is aborted; a following `resume` performs no merge for it (no `pr_merge` in `calls.log`), and a second REQ whose approval was queued behind it proceeds to its merge.
- [ ] After the drop, `answer` on that run is refused naming `failed`. An `abort` after an `answer` finds the relaunched harness and kills it, as before.
- [ ] `abort` is refused with nothing changed: on `awaiting_approval` with no live process (the message names `reject`), on a `merged` run and on a `rejected` run (the message names the status), and when called with `ADLC_EXEC_RUN` set.
- [ ] The token held for a dropped run is discarded.
- [ ] `adlc sprint-exec status` shows both `answer` and `abort` on a blocked run's row, each as a line that parses (`--channel` before the REQ id), and neither on a row of another status.
- [ ] After `reject`, the run-outcome log holds exactly one new line: `terminal` `rejected`, `engine` `exec`, an empty `blocked_reason`, and the reason text given to `reject` nowhere in it.
- [ ] `abort` of a running fake harness and `abort` of a blocked run each append one line with `terminal` `failed` and `blocked_reason` `aborted`. A run that blocked and was dropped has two lines, `blocked` then `failed`.
- [ ] A fake-harness scenario whose session reports the exhausted CI wait (`status: blocked`, a blocker naming the pending checks) ends `blocked`, not `awaiting_approval`, and its row shows the two ways out.
- [ ] `python3 -m pytest tools/adlc/tests` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_drops_a_blocked_run` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_the_drop_makes_no_one_way_move_and_no_forge_call` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_an_approved_then_conflicted_run_is_never_merged_after_the_drop` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_the_supervisor_exits_after_its_last_blocked_run_is_dropped` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_answer_after_the_drop_is_refused` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_is_still_refused_elsewhere` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_a_blocked_row_names_answer_and_abort` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_reject_records_rejected` | no |
| BR-19 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_records_aborted_from_both_arms` | no |
| BR-25 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_an_exhausted_ci_wait_ends_blocked` | yes |
| BR-29 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_drops_a_blocked_run` | no |
| AC-1 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_the_drop_makes_no_one_way_move_and_no_forge_call` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_the_supervisor_exits_after_its_last_blocked_run_is_dropped` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_an_approved_then_conflicted_run_is_never_merged_after_the_drop` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_is_still_refused_elsewhere` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_a_blocked_row_names_answer_and_abort` | yes |
| AC-14 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_reject_records_rejected` | no |
| AC-15 | test-case | `tools/adlc/tests/test_exec_approve.py::test_req719_abort_records_aborted_from_both_arms` | no |
| AC-19 | test-case | `tools/adlc/tests/test_exec_launch.py::test_req719_an_exhausted_ci_wait_ends_blocked` | yes |

## Technical Notes

- Order of the drop is in ADR-1. It makes no forge call: `_carry`, `revoke_trust` and `restore_surfaces` are local.
- `reject` already pops the token and releases holds; mirror it. `resume` skips a terminal status and `answer` refuses one, so no ledger write is needed. Do not add one.
- The existing conflict staging is `test_exec_approve.py` 211-238 (`conflicting()`), and the queue tests are `test_queue` and `test_queue_released_by_reject`.
- `_terminal`'s mapping of other statuses is unchanged: only `reject` passes `rejected`.
- The dashboard lines follow `sprint/references/exec-engine.md`'s shapes: `sprint-exec answer --channel skill '<REQ-id>' '<text>'` and `sprint-exec abort --channel skill '<REQ-id>'`, with the real REQ id.
- The mock's error scenarios are not written to `calls.log`; these tests use the default scenario.
- `abort` mints and prints no token (LESSON-781).
- Do not edit `sprint/SKILL.md`, `sprint/references/exec-engine.md` or the READMEs: TASK-276 owns them.
