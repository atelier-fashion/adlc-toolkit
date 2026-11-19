---
id: LESSON-892
title: "An agent told to stop on a refusal will stop on a typo: give a correctable input error its own channel"
component: "adlc/tools/adlc/fence-run"
domain: "adlc"
stack: ["python"]
concerns: ["reliability", "unattended", "developer-experience"]
tags: ["fence-run", "exit-codes", "refusal", "validation", "agent-protocol", "exec-engine"]
bug: BUG-287
created: 2026-11-19
updated: 2026-11-19
kind: process
evidence: "BUG-287: launches 1, 2 and 4 in .adlc/research/harness-probes/codex-exec-manual.md ended on opaque_entry_refused for a repo id, a body file under /tmp and a relative path. After fence_run.BAD_VALUE (15b5cbc) the close-out of launch 5 passed four wrong values to wrapup/SKILL.md#12 and went on, and tools/adlc/tests/test_fence_run.py::test_bug287_a_wrong_shaped_value_is_not_a_refusal holds it."
confidence: high
enforcement: test:tools/adlc/tests/test_fence_run.py
generalizes: []
supersedes: []
---

## What Happened

The fence runner answered every problem the same way: exit 3 and `opaque_entry_refused:`. The prompt told the session that a refusal means report it and stop, which is right for a command the runner will not run. But a value of the wrong shape got the same answer, and the session obeyed: three of the first four real launches ended on an argument it knew how to fix. In one, its final report named the fix.

## Lesson

When a tool polices an unattended agent, separate "this is not allowed" from "you passed it wrong". The first should end the attempt. The second should say which value is wrong, state that nothing ran, and invite a corrected call, which meets the same checks. Put the two on different exit statuses and different message prefixes, keep the numbers clear of what the wrapped commands return, and bound any "try again" instruction so a persistent failure ends in a report, not a loop.

## Why It Matters

Each launch that died on a typo cost a whole session, and the stricter the tool's patterns, the more often it happens. Making the error correctable weakens nothing: no value passes that would not have passed on the first try.

## Applies When

Writing a validator, wrapper or gate an agent calls; writing the prompt rule for what a refusal means; choosing exit codes for a tool that passes its child's status through.
