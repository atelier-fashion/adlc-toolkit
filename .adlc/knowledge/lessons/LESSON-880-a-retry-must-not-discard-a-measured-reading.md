---
id: LESSON-880
title: "A retry rule must read the harness's record before the model's reply: retrying a launch that already measured a refusal selects samples toward the answer the retry waits for"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "retry", "sample-selection", "proof-of-submission", "codex", "audit"]
req: BUG-285
created: 2026-11-17
updated: 2026-11-17
kind: domain
evidence: "BUG-285: an /adversary audit of the probe on 55ea774 found that read_runner_launch and read_atd_launch checked the nonce reply before proof of submission, so a submitted, blocked command read ask-not-reached and was retried; the saved run logs held more than 25 such discards. Fixed in af5551d; test_a_measured_reading_is_never_retried and test_proof_of_submission_is_exact fail against the code before it and pass after."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_unit.py
generalizes: [LESSON-870]
supersedes: []
---

## What Happened

LESSON-870 gave the probe retries for launches that "measured nothing". BUG-279 to BUG-283 then each added a rule at the place a live codex run failed. No one attacked the rules as a whole until an `/adversary` audit did.

The audit found that "measured nothing" was decided from the model's reply. A launch reads a nonce back to show the session reached the end. The probe checked that nonce before it checked the harness's record. So when codex blocked a submitted command and the model then skipped its reply, the launch read `ask-not-reached` and ran again. The refusal was a real measurement, and the retry threw it away.

The retry stops at the first attempt that measures something. On a row where the command should run (`runner-positive`, `runner-baseline`, the `allow-only` controls), discarding refusals means the loop keeps drawing until it sees the command run. That biases the row toward `pass`.

The same audit found the proof of submission was a substring match, so a quoted or chained command counted as the asked one.

## Lesson

**Decide "measured" from what the harness recorded, and only then look at the model's reply.** A submitted command that left no effect is a measured refusal even when the session never finishes its reply. Retry only a launch with no proof that the command was submitted.

**A retry that stops on the first measured attempt is sample selection.** It is unbiased only if every measured outcome stops it. Check each outcome a row can read, and confirm none of them is sent back for another draw.

**Proof that a command was submitted is an exact match.** Strip the one wrapper the harness adds, then compare the whole command. A substring also matches a quotation, or a longer chain that the harness judged as a different command.

**After a run of point fixes to one decision engine, attack the engine as a whole.** Each fix here was correct where it was placed. The gaps were in how the rules combined.

## Applies When

Adding or changing retries in a probe, test harness or flaky-test wrapper where an actor outside your control (a model, a network, a user) can fail after the system under test has already answered. Also when a "did it try?" check matches recorded commands by pattern.
