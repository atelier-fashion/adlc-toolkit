---
id: LESSON-883
title: "A check that something waited needs two stamps from the same command: one file written after the wait proves nothing, and a fake that skips the wait hides the gap"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "shell-timeout", "timing", "fake-harness", "fake-clock", "proof-of-submission"]
req: BUG-286
created: 2026-11-17
updated: 2026-11-17
kind: domain
evidence: "BUG-286: the shell-timeout row asked for `sleep 125 && touch <sentinel>` and read the sentinel alone, so a model that dropped the sleep would pass, and a refused command read fail (the committed antigravity.json entry, a 10 s launch). Fixed in e8595ce by a start marker and an mtime gap; test_shell_timeout_needs_the_sleep_and_a_started_command and test_shell_timeout_measures_the_sleep fail against the code before it and pass after."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-873]
supersedes: []
---

## What Happened

The `shell-timeout` probe row decides whether a harness lets one shell call run for two minutes. It asked the model to run `sleep 125 && touch <sentinel>` and passed when the sentinel existed.

The sentinel shows that a `touch` ran. It does not show that the sleep ran first. A model that tidies the sleep away writes the same file in a moment.

The other reading was wrong too. An absent sentinel with a reply read `fail`, meaning the call was cut short. A command the model never ran, or one the harness refused, leaves the same evidence. The committed Antigravity result was such a refusal, recorded as a timeout.

The fake harness hid both. It dropped every `sleep` from a command to keep the suite fast, so no test could tell a run that waited from one that did not.

## Lesson

**To prove a wait, stamp before it and after it in the same command, and measure the gap.** `touch <start> && sleep N && touch <done>` leaves two mtimes. The second being N seconds after the first shows one call outlived the wait. The start marker also proves the command began, so an absent `<done>` can be read as "cut short" only when `<start>` is there.

**A wall-clock time for the whole launch is weaker.** It also counts a stalled network or a slow model.

**A fake that skips time must move the clock, not drop the step.** When the double skips `sleep N`, it stamps the later files N seconds on. Then the timing check runs in the suite, and a flag can model the actor that drops the wait.

## Applies When

Writing a probe, test or health check whose claim is about duration: a timeout floor, a retry backoff, a cache expiry or a rate limit. Also when a test double shortens or skips a sleep to keep a suite fast.
