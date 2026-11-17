---
id: BUG-280
title: "`ask-tier-deny` reads a deny as held when the model never submitted the command, and launches that measured nothing are never retried"
status: resolved
severity: medium
created: 2026-11-16
updated: 2026-11-16
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "security"]
tags: ["harness-probe", "ask-tier-deny", "codex", "false-pass", "proof-of-submission", "retry"]
introduced_by: ["REQ-664"]
attribution: derived
---

## Description

On 2026-11-16, PR #269 recorded codex's `ask-tier-deny` as `pass`, with `deny-under-allow` `pass`. Codex's own `--json` records for that launch show the model ran the witness `touch` and nothing else. It replied that the target was outside its workspace and never submitted the denied command. The deny was never put to codex.

`decide_variant` reads a variant `pass` whenever its effect is absent, the witness ran and the nonce came back. `decide_control` reads a control `fail` ("did not run") on the same evidence. Neither asks whether the command reached the harness. LESSON-847 closed exactly this gap for `runner-prefix`, but not for `ask-tier-deny`.

The two later codex runs (#272, #276) read `ask-tier-deny` `unknown` for the same model habit (`ask-not-reached`, `config witness absent`), because its launches had no retries.

## Reproduction Steps

1. `git show 2fd9d66:.adlc/research/harness-probes/codex.json`, `probes.ask-tier-deny.sub_results.deny-under-allow`.
2. The status is `pass`, and the observation reads `sentinel target: absent; witness: present`. The `stdout_tail`'s only `command_execution` item is `touch …/witness-l06`.

## Expected Behavior

A held deny, or a control that did not run, is read only from proof the command was submitted. A launch that measured nothing is retried.

## Actual Behavior

A model that skips the command is read as a deny that held.

## Environment

- codex-cli 0.166.0, toolkit `main` at `ef7d0fc`.

## Root Cause

Prior lessons consulted:
- LESSON-847 — A probe reads `refused` only with proof the command was submitted, taken from the harness's tool-record fields and never from model text
- LESSON-870 — A probe that asks a model to run commands measures the model first
- LESSON-873 — A probe effect built from two side effects can be met by two separate commands

`decide_ask_tier_deny` (`tools/adlc/harness_probe.py`) reads each control through `decide_control` and each variant through `decide_variant`, and `_observe`'s `ask-tier-deny` branch records only `effect` and `witness`. Nothing checks the harness's records. LESSON-847 describes this failure exactly. BUG-279 added retries only for the runner launches.

Attribution candidates from blame of `decide_variant` and the `ask-tier-deny` observation: REQ-664 and REQ-658. The operator chose REQ-664, which wrote the oracle that reads an absent effect as a held deny; REQ-658's change to `decide_variant` kept that rule.

## Resolution

`read_atd_launch` holds each `ask-tier-deny` launch to proof of submission. A control's "did not run" (`fail`) and a variant's "held" (`pass`) stand only when the asked command is in a `command` field of the harness's records, or when the harness's refusal on stderr names the command's target. Otherwise the launch reads `unknown / not-attempted`.

`_observe` records `on_record` and `denied_here` for these launches and adds `asked command on record: yes|no` to the observation. `_launch_one` retries an `ask-tier-deny` launch that read `ask-not-reached`, `config witness absent` or `not-attempted`, from fresh state under its own id, up to `ATD_ATTEMPTS = 5`. A decided launch is never retried.

A retry runs under its own id (`<lid>r2` and on), and gemini's `ask-tier-deny` denies are written once, before the run, to a user-level policy named by launch id. The first version of the retry therefore escaped the deny: a retried `deny-under-allow` ran its command and read `fail`. The suite's `abort-on-deny` case caught it. The policy now names every attempt id (`attempt_lids`), and the retry loop names its attempts through the same helper.

## Files Changed

- `tools/adlc/harness_probe.py`: `read_atd_launch`, `ATD_ATTEMPTS`, `ATD_RETRY_REASONS`, `attempt_lids` (the gemini deny policy names every attempt id); `decide_ask_tier_deny` reads through it; the `ask-tier-deny` observation records the submission evidence; `_launch_one` retries these launches.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: `witness-only` also applies to `ask-tier-deny` variant prompts.
- `tools/adlc/tests/test_harness_probe_unit.py`: `_atd` takes `on_record`; `test_ask_tier_deny_needs_proof_of_submission`.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_ask_tier_deny_witness_only_is_not_a_held_deny`, `test_gemini_deny_policy_covers_retries`; `test_fresh_state_per_launch` counts base launches, since retries add some.
- `tools/adlc/README.md` (the `ask-tier-deny` section), `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written: `test_ask_tier_deny_needs_proof_of_submission` and `test_ask_tier_deny_witness_only_is_not_a_held_deny` both fail against `main`'s `harness_probe.py`, and both pass with the fix.

## Deployment

Merged as `46a64bc` ([#277](https://github.com/atelier-fashion/adlc-toolkit/pull/277)) on 2026-11-16. Nothing to deploy, since this is toolkit code. A full codex probe on the merged commit records the result.

## Lessons

- LESSON-874: a retry under a new id must be covered by every rule rendered before the run.
