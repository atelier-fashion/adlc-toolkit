---
id: LESSON-768
title: "A probe's fail names an outcome, not its cause: read what the launch actually ran before reading the verdict"
component: "adlc/harness"
domain: "adlc"
stack: ["antigravity-cli"]
concerns: ["harness-agnostic", "testing", "silent-failure"]
tags: ["multi-harness", "probe", "evidence", "transcript", "verdict", "capability"]
req: REQ-658
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-658 .adlc/research/harness-probes/antigravity.json and the note's table Reading the probe result, commit 31bc467: fence-vs-allowlist and git-write-main both read fail. The transcripts' tool_calls showed the fence run as written and refused, which is real, and git status refused before git commit was ever tried, which is an artifact. Hand case H6 first read as ask beating allow, and the allow-only control's record left that unproven."
confidence: low
enforcement: none
generalizes: [LESSON-765]
supersedes: []
---

## What Happened

The first `agy` probe run printed a column of `fail`s, and several were on commands the launch had allowed. Taken at face value, that said `command(...)` allow rules do not work. The session transcripts showed each launch's own tool calls and the exact refusal: a different command had been refused first. The same word was true for one probe and meaningless for another, and only the transcript told them apart. A hand case read the same way needed correcting: a refused chain looked like `ask` beating `allow` until the control was read.

## Lesson

Before a `fail` decides anything, read the launch's own record and confirm the command under test was the one that ran and was refused. Record the reading next to the verdict, in the note the adapter cites. A verdict string is the start of an investigation: an oracle sees that an effect is absent, and cannot say why. LESSON-765 asks this of a hook, and it holds for any probe.

## Why It Matters

Declaring a capability from a bare `fail` would have shipped an adapter saying allow rules do nothing, and a bare `pass` can mislead the same way. A wrong capability decides what gets rendered and what the README promises, and nothing later re-checks it.

## Applies When

Reading any probe result, declaring a capability from one, or concluding anything from a single hand run that has no control.
