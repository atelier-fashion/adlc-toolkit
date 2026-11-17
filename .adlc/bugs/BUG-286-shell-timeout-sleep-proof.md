---
id: BUG-286
title: "`shell-timeout` passes on a sentinel written without the sleep, and fails on a command that never ran"
status: open
severity: medium
created: 2026-11-17
updated: 2026-11-17
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "shell-timeout", "proof-of-submission", "fake-harness", "antigravity", "audit"]
introduced_by: ["REQ-664", "REQ-658"]
attribution: derived
---

## Description

The `/adversary` audit behind BUG-285 noted that `shell-timeout` never checks that the sleep ran. BUG-285 deferred it, because the fake harness skips sleeps and a check needed a test seam first.

The row asked for `sleep 125 && touch <sentinel>` and read the sentinel alone:

1. **`pass` did not prove the sleep.** A model that drops the sleep and runs only the `touch` writes the same sentinel. The row would then say the harness's shell timeout is at least 120 s when nothing ran for longer than a moment.
2. **`fail` did not prove the command began.** An absent sentinel with a reply read `fail`, meaning "the shell call was cut short". A model that declined the command, or a harness that refused it, left the same evidence.

The second defect is in a committed result. `.adlc/research/harness-probes/antigravity.json` reads `shell-timeout` `fail` with a 10 s launch whose stderr says the command was auto-denied for want of an allow rule. That is a refused command, not a timeout. REQ-664's Open Questions had resolved this case as `unknown / precondition-unmet`.

The committed `claude` and `codex` passes are not in doubt: both launches took about 133 s, and codex's record shows the whole command completing.

## Reproduction Steps

1. `git show d9b6322:.adlc/research/harness-probes/antigravity.json`: `shell-timeout` is `fail`, `wall_s` is 10.0, and `stderr_tail` holds the auto-deny message.
2. The new tests named below, run against `main`'s `harness_probe.py`.

## Expected Behavior

`pass` only when a shell call outlived the sleep. `fail` only when the call began and was cut short. Anything else `unknown`, with a reason.

## Actual Behavior

A sentinel alone read `pass`, and a command that never ran read `fail`.

## Environment

- Toolkit `main` at `d9b6322`. Antigravity CLI 1.4.12 for the committed `fail`.

## Root Cause

Prior lessons consulted:
- LESSON-847 — A probe reads `refused` only with proof the command was submitted
- LESSON-875 — When one oracle gets a proof-of-submission rule, sweep every oracle of the same shape
- LESSON-870 — A probe that asks a model to run commands measures the model first
- LESSON-873 — A probe effect built from two side effects can be met by two separate commands
- LESSON-880 — A retry rule must read the harness's record before the model's reply

`_prepare`'s `shell-timeout` ask stamped one file, after the sleep, so nothing on disk showed when the command began. `decide_exit_exempt` then decided the row from that one file and the reply. BUG-281's sweep left the row out on purpose, on the reading that its `fail` means "the command ran with the wrong result". The antigravity result shows that reading was wrong: `Obs.reached()` counts a harness refusal as reaching the ask, so a refused command read `fail`.

## Resolution

- **The ask** is now `touch <start> && sleep 125 && touch <sentinel>`, run as one command. Both files are stamped by the command itself.
- **`decide_shell_timeout`** replaces `decide_exit_exempt` for this row:
  - `pass`: the sentinel's mtime is at least 125 s after the start marker's (with 1 s of slack for a file system that rounds to whole seconds).
  - `unknown / precondition-unmet`: the sentinel is there without that gap.
  - `fail`: the start marker is there, the sentinel is not, and the model replied.
  - `unknown / not-attempted`: neither file, and the model replied.
  - `unknown / precondition-unmet`: the harness refused the command.
- **The fake** no longer only skips a `sleep`. It moves the clock: a file a later `touch` writes is stamped that many seconds on. Two new flags: `drop-sleep` (a model that tidies the sleep away) and `shell-cut-short` (a harness that kills the call at the sleep).

Not fixed here:
- **The row is not retried.** Each attempt costs over two minutes, and no live run has shown a model skipping this command.
- **One limit remains.** A model that runs the first `touch` alone and then replies reads `fail`. Closing it needs the whole command on the harness's record, which not every profile prints.
- **`antigravity.json` still holds the old `fail`.** A result file changes only by a run. The REQ-662 antigravity adapter work needs a fresh run before it reads this row.

## Files Changed

- `tools/adlc/harness_probe.py`: the ask, `shell_elapsed`, `shell_slept`, `decide_shell_timeout`, the observation.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: `skip_sleeps`, `drop-sleep`, `shell-cut-short`.
- `tools/adlc/tests/test_harness_probe_unit.py`: `test_shell_timeout_needs_the_sleep_and_a_started_command`, `test_shell_elapsed_reads_the_two_markers`.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_shell_timeout_measures_the_sleep`. One expectation changed in `test_scenario_verdicts`: a declined `shell-timeout` reads `unknown / not-attempted`, where it read `fail`.
- `tools/adlc/README.md`, `CHANGELOG.md`, REQ-664 `requirement.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written. The three new tests fail against `main`'s `harness_probe.py` and pass with the fix.
