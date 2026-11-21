---
id: BUG-289
title: "An exec session that stamps the harness before the state file exists can report `blocked` and lose the launch"
status: open
severity: medium
created: 2026-11-21
updated: 2026-11-21
component: "adlc/proceed/telemetry"
domain: "adlc"
stack: ["markdown", "python"]
concerns: ["reliability", "developer-experience"]
tags: ["sprint-exec", "exec-prompt", "run-outcome", "telemetry", "codex", "step-0", "pipeline-state"]
introduced_by: []
attribution: none
---

## Description

`proceed/SKILL.md` sends the reader to `proceed/phases-telemetry.md` before Step 0. The file
holds the five run-outcome fences, R1 to R5, each with its text ready to run, and says they are
run "where that step says". R1, the harness stamp, belongs to Step 0 item 8, after item 7's
lessons fence.

In two real `adlc sprint-exec run --harness codex REQ-900` launches on 2026-11-21 (launches 7
and 8, fact 10, in `.adlc/research/harness-probes/codex-exec-manual.md`) both sessions ran R1
as soon as they had read the telemetry file. Under an exec run the session cannot write the
primary path's `pipeline-state.json`: only a fence the runner runs can, and the first one that
creates that file is the lessons fence. So R1 found no file, printed
`run-outcome: state file not found: <path>` and
`run-outcome: record-harness failed (rc 1) — state not updated`, and exited 0.

Launch 8 read that, ran the lessons fence and stamped again. Launch 7 reported `blocked` with
`setup-error` and stopped 55 seconds in. The operator had to `abort` it and launch again.

## Reproduction Steps

A real launch is the only full reproduction, and it depends on the model. The parts that do
not:

1. In a working copy with an approved REQ and no `pipeline-state.json` at the primary path,
   run the delivered R1 line:
   `fence-run run 'proceed/phases-telemetry.md#1:…' --arg state='<primary state>' --arg mode='--fresh'`.
2. Read the output: exit 0, the two `run-outcome:` lines above, no file written.
3. Read the delivered prompt (`exec_prompt.pipeline_prompt`) for a sentence saying that R1
   waits for the lessons fence, or what `state file not found` means. There is none.

## Expected Behavior

A session that runs a telemetry fence too early is told, by the text and by the line the fence
prints, that the state file does not exist yet, which fence creates it, and that this is never
a reason to stop. The run goes on to the lessons fence and the stamp.

## Actual Behavior

The text says only "each is run where that step says" and, in general terms, that telemetry
never halts the pipeline. The fence's output says `state file not found` and `failed`. One
session of two read that as a failed setup and ended the run.

## Environment

- Platform: darwin arm64
- Version: toolkit at `4ec4aa6` on the REQ-719 branch, `codex-cli 0.166.0`

## Root Cause

Prior lessons consulted:
- LESSON-729 — Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them (score 9)
- LESSON-626 — A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event (score 9)
- LESSON-764 — A parallel REQ landing turns "in flight" and "not shipped yet" into false statements, and a clean rebase will not tell you (score 8)
- LESSON-616 — Gate commits on the runner's exit code, and keep agent verification runs targeted (score 8)
- LESSON-604 — A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time or you will rediscover a lesson captured in the gap (score 8)

None of these describes the failure. LESSON-626's first point is the nearest: the ordering
rule was written for a reader that can create the state file itself, and was silent for one
that cannot.

Two gaps, one in the text and one in the line the fence prints.

1. **Nothing says a fence must not run when the file is read.** `proceed/phases-telemetry.md`
   is read whole before Step 0 and holds each fence as a ready call. Its only ordering
   statement was "each is run where that step says", in the opening line, and R1's own
   heading names its step in parentheses. Nothing said what creates `<state>`, so nothing told
   a reader that R1 cannot work before item 7. In a solo run that never mattered: Claude runs
   the steps in order, and can write the state file itself. Under exec only a fence the runner
   runs writes the primary path's copy (REQ-659 BR-9), so the lessons fence is the file's
   first writer and the order is load-bearing.
2. **The line read as a failure.** `run_outcome.read_state` raised `state file not found:
   <path>` and `emit-run-outcome.sh` added `record-harness failed (rc 1) — state not updated`.
   The file's general rule, "relay the one line it prints and continue, because telemetry
   never halts the pipeline", was already in the prompt, and one session of two still stopped:
   the same file lists `setup-error` as the token for a `failed` terminal, and the line in
   front of the session said `failed`.

`record-harness` creating the file was weighed and not done. The file's first writer decides
fresh or resume (LESSON-719: from the progress record, never from whether a key exists), and
Step 0 treats a state file that already exists as a resume. A stamp that left a file behind
would turn "absent" into "present with one key" for every engine, solo included, to help a
call that should not have been made. An exec-only note was also weighed: the telemetry file
is what every engine reads, the sentence is true for all of them, and it changes nothing a
solo run does, so it went there.

`introduced_by` is left empty. `git blame` on the root-cause lines returns two candidates,
REQ-661 for the telemetry file's opening and REQ-648 for `read_state` and the wrapper's line.
With more than one, the choice is the operator's.

## Resolution

- **The text** (`proceed/phases-telemetry.md`): one paragraph before R1. No fence runs on
  reading the file; R1, the first, waits for Step 0 item 8; on a fresh run `<state>` does not
  exist until item 7's lessons fence has created it; a `run-outcome: state file not found`
  line means only that, and is never a blocker, a `setup-error` or a reason to stop; run the
  lessons fence if it has not run, then the fence again, and if the line prints a second time,
  relay it and continue. The exec prompt inlines the file, so every exec adapter's prompt
  holds the paragraph, ahead of R1's call. No fence changed, so no fence id did.
- **The line** (`tools/delegate/run_outcome.py`, `emit-run-outcome.sh`): the message is now
  `state file not found: <path> (nothing recorded, and not a blocker: Step 0's lessons fence
  creates this file, so if that fence has not run, run it, then this one again)`, and the
  wrapper's `failed` line ends "telemetry never halts the pipeline, so carry on". Exit codes
  are as before, and nothing is created.
- **Not verified by a real launch.** The tests drive the fake harness: its session makes
  launch 7's early call through the fence runner under the engine, on the shipped Codex block,
  and the run reaches the gate with the stamp and the lessons in the primary path's state.
  Whether a real model now carries on where launch 7 stopped is not measured.

## Regression Test

Regression tests are off for this project (`.adlc/config.yml` does not exist). The tests
written anyway, each citing this bug:

- `tools/adlc/tests/test_bug289_early_harness_stamp.py`: the paragraph is in the file and in
  every exec adapter's delivered prompt; the fake session's early R1 costs the run nothing.
  Without the fix both failed, the first on the missing sentence, the second on the fence's
  output: `run-outcome: record-harness failed (rc 1) — state not updated`.
- `tools/delegate/tests/test_run_outcome.py`
  (`test_bug289_a_stamp_with_no_state_file_writes_nothing_and_says_what_to_do`): the absent
  file, and the benign path where the file exists.

## Files Changed

- `proceed/phases-telemetry.md` — the paragraph before R1
- `tools/delegate/run_outcome.py` — the `state file not found` message
- `tools/delegate/emit-run-outcome.sh` — the record commands' `failed` line
- `tools/adlc/tests/test_bug289_early_harness_stamp.py` — new
- `tools/delegate/tests/test_run_outcome.py` — one test
- `.adlc/research/harness-probes/codex-exec-manual.md` — fact 10
- `CHANGELOG.md` — Unreleased, Fixed
