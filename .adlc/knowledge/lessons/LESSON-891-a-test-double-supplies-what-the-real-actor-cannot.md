---
id: LESSON-891
title: "A test double written from the system's side supplies what the real actor cannot: run the whole flow once with the real actor, against a double no kinder than the real service"
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python", "markdown"]
concerns: ["testing", "correctness", "unattended"]
tags: ["exec-engine", "fake-harness", "mock-forge", "dogfood", "end-to-end", "draft-pr", "test-double"]
bug: BUG-287
created: 2026-11-19
updated: 2026-11-19
kind: process
evidence: "BUG-287: launches 1 to 4 of .adlc/research/harness-probes/codex-exec-manual.md ended before the merge gate and launch 5 merged two draft PRs, on an engine whose suite passed against tools/adlc/tests/fake_harness/exec_harness.py; after 15b5cbc launch 6 reached the gate with the PR ready. tools/adlc/tests/test_forge_mock.py::test_stateful_flow_and_pin now fails a draft merge that the mock used to accept."
confidence: high
enforcement: test:tools/adlc/tests/test_forge_mock.py
generalizes: [LESSON-888]
supersedes: []
---

## What Happened

The exec engine shipped with every acceptance criterion passing against a fake harness, and with real `codex exec` sessions that each ran one fence. The first real session to run the whole pipeline needed five launches to reach the merge gate. The fake had been written by the engine's author, from the engine's side: it read the forge repository and the mock's store from its scenario file, called the mock forge directly, wrote state where the engine reads it, never chained a shell line, never passed a malformed value and had a clock. A model has none of those. The mock forge also merged a draft PR, which GitHub refuses, so a pipeline that never marked its PR ready passed every test.

## Lesson

A double for the actor you are building for encodes what you already know the system needs, so it cannot find what you forgot to tell the actor. Before calling an agent-facing flow done, run the whole flow once with the real actor, end to end, and read every command it ran. Single steps run for real do not stand in for it: each gap here sat between two steps. And give that run a service double that refuses whatever the real service refuses. Where the double is kinder than the real thing, the missing step is invisible.

## Why It Matters

As merged, a real `/sprint --exec` run on GitHub would have reached the gate and then failed to merge, on every harness. Nothing in a suite of 3,952 passing tests said so.

## Applies When

Shipping a pipeline, prompt or protocol an agent or outside system must follow, on tests that drive a fake of that agent; writing or extending a mock of a forge, API or CLI; deciding whether "each piece was run for real" is enough evidence.
