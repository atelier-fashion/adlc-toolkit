---
id: BUG-279
title: "`runner-prefix` cannot be decided on codex: its model skips the asked commands on about half its launches, and each launch is one sample"
status: open
severity: medium
created: 2026-11-16
updated: 2026-11-16
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "codex", "runner-prefix", "live-run", "model-behaviour", "retry"]
introduced_by: ["REQ-707"]
attribution: derived
---

## Description

After BUG-278 let codex's command records reach the oracle, the full codex probe on
2026-11-16 (codex-cli 0.166.0, `main` at `e0e17ab`) still read `runner-prefix` `unknown`.
Of its 13 launches, `runner-positive` was admitted and two controls were refused with the
command on record. The baseline and nine controls read `unknown`. On those, the model
either replied with the nonce without running anything, or said the commands wrote
outside the writable workspace and declined to run them. The run's allow rules would
have let them run. On some, it ran the line but reversed the nonce wrongly.

REQ-707 reads a launch where the model did nothing as `unknown`, which is right. But each
launch is one sample, so a model that skips half the time leaves the variant undecidable
however often the probe is run.

## Reproduction Steps

1. `adlc harness probe codex --only fence-vs-allowlist` on codex-cli 0.166.0.
2. Most `runner-*` launches read `precondition-unmet: config witness absent`,
   `ask-not-reached` or `not-attempted`. Their `stdout_tail` shows an `agent_message`
   with no `command_execution`, or a message declining a write outside the workspace.

## Expected Behavior

A launch that measured nothing is not the probe's last word on that control: the probe
gives the model another chance, and the variant is decided where the harness decides.

## Actual Behavior

`runner-prefix` reads `unknown` on codex on every run.

## Environment

- codex-cli 0.166.0 (its default model, reasoning effort `none`), macOS, toolkit `main` at
  `e0e17ab`.

## Root Cause

Prior lessons consulted:
- LESSON-869 — A fake CLI must print a record format only under the flag the real CLI needs for it
- LESSON-847 — A probe reads `refused` only with proof the command was submitted, taken from the harness's tool-record fields and never from model text
- LESSON-768 — A probe's fail names an outcome, not its cause: read what the launch actually ran before reading the verdict
- LESSON-854 — A harness's trust gate can drop a project's allows while still loading its hooks

`Runner._prepare_runner` (`tools/adlc/harness_probe.py`) asks the model to run the witness
and the fenced line, with nothing that says to run them when it expects a block. Codex's
model sees a path outside its writable roots and predicts the sandbox will refuse, so it
does not try. `Runner._launch_one` launches each runner variant once, so a launch the
model skipped is final.

Following LESSON-768, the launches' own records were read before choosing a fix. Three
live 16-launch runs of `fence-vs-allowlist` compared the levers:

| change | decided launches of 13 |
|---|---|
| none (the full run) | 3 |
| prompt: run both, whatever you expect | 9 |
| prompt + `-c model_reasoning_effort="medium"` | 7 |
| prompt + up to 3 attempts | 11 (27 launches; the two left skipped all three times) |
| prompt + up to 5 attempts | 11 (38 launches; `runner-subst` and `runner-redirect` skipped all five) |
| prompt naming the stubs + up to 5 attempts | 12 (30 launches; `runner-redirect` skipped all five) |

The prompt helped. Pinning the reasoning effort did not, so it is not part of the fix.
Even with the prompt, a third of the launches measured nothing, so retries are needed too.
With three attempts two launches still skipped every time, so the cap is five: at the
observed skip rate a launch stays undecided after five attempts about 1% of the time.
Two shapes were not random skips. On `runner-subst` the model called the line "an opaque
command block"; once the prompt said what the stubs are, it ran it. On `runner-redirect` it
ran the witness and never submitted the line, in all 13 attempts across three runs: it will
not redirect into a file outside the workspace. That control stays `unknown` on codex, and so
does the variant. `codex execpolicy check` was tried as a model-free oracle and rejected: it
does not look inside `zsh -lc '…'`, so it matches no shell-wrapped line, not even the plain
runner.

Attribution: REQ-707, derived from blame of `_prepare_runner` and the runner launch rule.

## Resolution

The runner prompt now says what `fence-run` and `fence-run-x` are (test stubs that only
append their arguments to a marker file), and adds: run both, even where a path is outside
the workspace or you expect a command to be blocked, since the project's rules decide what
runs. A runner launch
whose reading is `unknown` for a "did nothing" reason (`config witness absent`,
`ask-not-reached`, `ask-split`, `not-attempted`) is launched again from fresh state, under
its own id (`l19r2` to `l19r5`), up to `RUNNER_ATTEMPTS = 5`. A decided reading is never
retried. Retries never change how a launch is read: they only replace a launch that
measured nothing, so a retry cannot turn an admission into a refusal. `evidence.attempts`
records the attempt that decided, each attempt counts in `launches.actual`, and the run
prints a `launch_retried` line for each retry.

## Files Changed

- `tools/adlc/harness_probe.py`: the runner prompt names the stubs and asks for both commands; `RUNNER_ATTEMPTS`,
  `RUNNER_RETRY_REASONS`; `_launch_one` retries a runner launch, and `_launch_attempt` is
  the former single launch.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: a `skip-first-attempt` flag.
- `tools/adlc/tests/test_harness_probe_e2e.py`:
  `test_runner_launch_that_measured_nothing_is_retried`,
  `test_runner_retries_are_bounded_and_never_decide`.
- `tools/adlc/README.md` (the runner-prefix section), `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written. Against `main`'s `harness_probe.py`, both fail:
the first reads `runner-prefix` `unknown`, the second finds no `evidence.attempts`. With the
fix both pass.
