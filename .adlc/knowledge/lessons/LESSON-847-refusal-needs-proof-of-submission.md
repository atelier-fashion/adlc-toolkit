---
id: LESSON-847
title: "A probe reads `refused` only with proof the command was submitted, taken from the harness's tool-record fields and never from model text"
component: "adlc/harness"
domain: "adlc"
stack: ["python"]
concerns: ["security", "testing", "harness-agnostic"]
tags: ["probes", "refusal", "tool-record", "model-output", "fake-harness", "fence-runner"]
req: REQ-707
created: 2026-11-09
updated: 2026-11-09
kind: domain
evidence: "REQ-707 BR-4 amendment, commit 62ac436; tests test_runner_prefix_ask_split_never_passes and test_runner_evidence_names_what_ran"
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-768]
supersedes: []
---

## What Happened

REQ-707's `runner-prefix` probe variant decides a hard gate (REQ-662 BR-11): it passes only when eleven refusal controls each read `refused`. The first design read a control as refused when its effect was absent, the witness ran and the nonce came back.

A fake-harness run in which the model ran only the witness turned every control into `refused`. Nothing had been attempted, but the variant was one passing positive launch away from `pass`.

The first fix searched the launch's whole stdout for the asked line, as proof of submission. The reflector then reproduced, on the Codex profile, an intermediate `agent_message` that quoted the command the model declined to run. That read `on_record: true`, and so `refused`.

The fix that shipped reads only strings under a `command` key in the harness's parsed JSON records (`record_commands`). It never descends into `result`, `response`, `text`, `reasoning` or `agent_message`. A stderr refusal counts only when it names the stub. Anything else reads `unknown` (`not-attempted` or `ask-split`).

## Lesson

An absent effect is not a refusal. Before a probe records `refused`, it needs proof that the command reached the harness, and that proof must come from the harness's own structured tool-call or denial records. Never take it from text the model wrote: a reply, a reasoning item or an intermediate message can quote a command the model never submitted.

A refusal signal on stderr is proof only when it names the command under test. When the record format is unknown, read `unknown`, never `refused`.

## Why It Matters

On a gate, a false `refused` is a false `pass`. A model that skips, tidies or merely discusses the command would certify a boundary that was never tested.

## Applies When

Writing or changing a probe, test or validator that decides from side effects whether a harness refused a command. This matters most where `refused` is the passing outcome (deny rules, allow boundaries, refusal controls), and where the harness's output mixes structured tool records with model text.
