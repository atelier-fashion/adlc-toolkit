---
id: BUG-283
title: "`ask-tier-deny` decides a variant on a baseline control that was never measured, so \"the allow was necessary\" can rest on nothing"
status: open
severity: low
created: 2026-11-17
updated: 2026-11-17
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "ask-tier-deny", "codex", "gate", "proof-of-submission", "baseline"]
introduced_by: ["REQ-664"]
attribution: derived
---

## Description

The codex result recorded in #284 (`1e1fe5c`, codex-cli 0.166.0) reads `ask-tier-deny` `pass`, with `deny-under-allow` `pass`. Its `baseline` control read `unknown / not-attempted` on all five attempts: the model never tried the no-allow command.

A variant is meant to be decided only when its `allow-only` control ran the command and its `baseline` control did not, which shows the allow was necessary. But `decide_ask_tier_deny` checked the baseline through `effect()`, the raw "the target appeared". Since BUG-280 that bypasses the control's proof-checked reading. So an unattempted baseline counted as "did not run".

The `pass` itself is sound: codex rejected the command, citing the rule. Only the gate's premise was unmeasured.

## Reproduction Steps

1. In #284's `codex.json`, `ask-tier-deny.sub_results.baseline` is `unknown`, with reason `not-attempted`, while `deny-under-allow` is `pass`.

## Expected Behavior

A variant is decided only on a baseline whose "did not run" is itself proven.

## Actual Behavior

An unattempted baseline let the variant be decided.

## Environment

- codex-cli 0.166.0, toolkit `main` at `1e1fe5c`.

## Root Cause

Prior lessons consulted:
- LESSON-875 — When one oracle gets a proof-of-submission rule, sweep every oracle of the same shape
- LESSON-847 — A probe reads `refused` only with proof the command was submitted
- LESSON-870 — A probe that asks a model to run commands measures the model first

BUG-280 held each control's own reading to proof of submission. It left the variant gate in `decide_ask_tier_deny` reading `effect(baseline)`, which is the site LESSON-875's sweep missed. The `ask-tier-deny` prompts also lacked the "run it whatever you expect" wording that got codex's model attempting the runner commands (BUG-279). So codex's model never attempted the baseline, an outside-workspace write with no allow.

Attribution: REQ-664, which built the gate.

## Resolution

- **The gate:** a variant's gate now needs `subs[baseline]` to read `fail`, the proof-checked "did not run". Otherwise the variant is `precondition-unmet: <baseline> control not measured (<reason>)`. A baseline that ran the command still reads `allow not required`.
- **The prompts:** every `ask-tier-deny` prompt now tells the model to run the command even where a path is outside the workspace or it expects a block, since the project's rules decide what runs.

## Files Changed

- `tools/adlc/harness_probe.py`: `decide_ask_tier_deny`'s gate; `_prepare_atd`'s reply wording.
- `tools/adlc/tests/test_harness_probe_unit.py`: `test_ask_tier_deny_gate_needs_a_measured_baseline`.
- `tools/adlc/README.md`, `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

A failing-first test was still written: `test_ask_tier_deny_gate_needs_a_measured_baseline` fails against `main`'s `harness_probe.py` and passes with the fix.
