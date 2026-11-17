---
id: BUG-282
title: "`adlc harness probe codex` cannot see codex refuse a command: a `forbidden` rule's rejection leaves no record and only a stderr line the profile does not name"
status: resolved
severity: medium
created: 2026-11-17
updated: 2026-11-17
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "codex", "ask-tier-deny", "refusal", "stderr", "fake-harness", "proof-of-submission"]
introduced_by: ["REQ-664"]
attribution: derived
---

## Description

On 2026-11-17 a full `adlc harness probe codex` on `main` (`4d1ec8c`, codex-cli 0.166.0) read `ask-tier-deny` `deny-under-allow` `unknown / not-attempted` on all five attempts. Codex's stderr showed it had refused each one:

> `rejected: policy forbids commands starting with touch …/target-l06r5`

Codex rejects a command a `forbidden` prefix rule matches before running it, and writes no `command_execution` item for it. The rejection line on stderr is codex's only record. BUG-280 and BUG-281 accept "the harness's refusal on stderr names the command" as proof of submission, but only when the profile declares the refusal's shape in `refusal_stderr`. The codex profile declared none, so the deny that held read as a model that never tried. The result was discarded.

The fake codex hid it. It printed a `command_execution` item even for a command its `forbidden` rule denied, which real codex does not (LESSON-869).

## Reproduction Steps

1. In the discarded run's `deny-under-allow` evidence, `stdout_tail` holds only the witness `touch`. `stderr_tail` holds the `rejected: policy forbids commands starting with …/target-…` line.
2. The observation reads `asked command on record: no` and the status `unknown / not-attempted`.

## Expected Behavior

A command codex refuses by policy counts as a submitted, refused command.

## Actual Behavior

It reads as one the model never tried.

## Environment

- codex-cli 0.166.0, toolkit `main` at `4d1ec8c`.

## Root Cause

Prior lessons consulted:
- LESSON-847 — A probe reads `refused` only with proof the command was submitted
- LESSON-869 — A fake CLI must print a record format only under the flag the real CLI needs for it
- LESSON-875 — When one oracle gets a proof-of-submission rule, sweep every oracle of the same shape

`PROFILES["codex"]` (`tools/adlc/harness_probe.py`) sets no `refusal_stderr`, so `obs.denied` is never true on codex and `denied_here` cannot prove a refusal. The fake codex's `--json` branch printed a `command_execution` item for every record, `denied` included, so the suite saw a record that real codex never writes.

Attribution: REQ-664, derived from blame of the codex profile and the fake's codex output.

## Resolution

The codex profile declares `refusal_stderr=r"rejected: policy forbids commands starting with"`. A held deny now reads `pass` through `denied_here`, the stderr line naming the command's target. The fake codex now writes that line on stderr for a denied command instead of a `command_execution` item.

## Files Changed

- `tools/adlc/harness_probe.py`: the codex profile's `refusal_stderr`, and the field's comment.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: the fake codex rejects a denied command on stderr, with no record.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_codex_policy_rejection_is_proof_of_refusal`.
- `tools/adlc/README.md`, `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

A failing-first test was still written: `test_codex_policy_rejection_is_proof_of_refusal` fails against `main`'s `harness_probe.py`, with the corrected fake, and passes with the fix.

## Deployment

Merged as `ff2af44` ([#282](https://github.com/atelier-fashion/adlc-toolkit/pull/282)) on 2026-11-17. Nothing to deploy, since this is toolkit code. A full codex probe on the merged commit records the result.

## Lessons

- NO_ENTRY: covered by LESSON-869 (a fake must model the real CLI's output, here a rejection that leaves no record) and LESSON-847 (a stderr refusal naming the command is proof of submission).
