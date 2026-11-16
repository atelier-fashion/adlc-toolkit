---
id: LESSON-870
title: "A probe that asks a model to run commands measures the model first: say what an unfamiliar command does, retry launches that measured nothing, and record a shape the model always refuses as unmeasured"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "codex", "runner-prefix", "model-behaviour", "retry", "live-run"]
req: BUG-279
created: 2026-11-16
updated: 2026-11-16
kind: domain
evidence: "BUG-279: live codex-cli 0.166.0 runs of fence-vs-allowlist decided 3 of 13 runner launches with the original prompt, 9 when the prompt asked the model to run both commands whatever it expected, 7 with reasoning effort pinned to medium as well, 11 with up to 3 or 5 attempts, and 12 once the prompt said the stubs only append to a marker file (the model had called the $(...) line 'an opaque command block'). runner-redirect was never submitted in 13 attempts over three runs. Fixed in 2f79f48 (#270); test_runner_launch_that_measured_nothing_is_retried and test_runner_retries_are_bounded_and_never_decide fail against the code before it."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-847, LESSON-768]
supersedes: []
---

## What Happened

REQ-707's `runner-prefix` asks a model to run a witness and then one fenced line, and reads
whether the harness admitted the line or refused it. On codex the model skipped the work on
about half its launches. It replied with the nonce and ran nothing, or said the paths were
outside its workspace. The probe correctly read those launches as `unknown`. But each
launch was a single sample, so the variant could never be decided, however many times the
probe ran.

Two other things showed up only in the model's own messages. It refused a `$(…)` line as
"an opaque command block" until the prompt said what the stubs do. It never submitted a
line that redirects into a file outside the workspace. Pinning a higher reasoning effort
made things worse, not better.

## Lesson

**A model-driven probe has two gates: the model, then the harness.** Only the second one is
the subject.

**Get the model through the first gate on purpose:**
- Say plainly what an unfamiliar command does.
- Say that the harness's rules, not the model, decide what runs.
- Retry a launch that measured nothing, from fresh state and under its own id.
- Never retry a launch that produced a decided reading. Then a retry can only replace "no
  data", and can never move a verdict.

**Read the model's messages before choosing a lever.** Here each "refusal" had a different
cause. One shape was refused for being opaque, one for writing outside the workspace, and
the rest were plain skipping.

**A shape the model refuses every time is unmeasured, not refused.** Record it as `unknown`,
and say why.

## Applies When

Writing or reviewing a probe, eval or live test that asks a model to run a command, so it
can observe what a harness or sandbox does with it. It matters most when the command
touches paths outside the model's workspace, or uses shell constructs a model treats as
risky.
