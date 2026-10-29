---
id: LESSON-732
title: "Concurrent sprint runners share one session scratchpad — a fixed log filename there is a race, so name every scratch file by REQ before you read a verdict from it"
component: "adlc/sprint"
domain: "adlc"
stack: ["bash", "claude-code"]
concerns: ["concurrency", "verification", "false-positive", "orchestration"]
tags: ["scratchpad", "parallel-runners", "pipeline-runner", "test-log", "shared-state", "sprint"]
req: REQ-647
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-647 Phase 5: the four-shell partials/tests/run.sh output was redirected to scratchpad/run2.log; the concurrent REQ-654 runner wrote the same file name, so the log read back carried 2 FAIL lines for adlc-home.sh (a REQ-654 partial) while this run's own background task output said run.sh rc=0. Re-running lessons, source-guard and set-u-home into a scratchpad/req-647/ subdirectory passed 12 of 12."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-647 ran as one of two `pipeline-runner` agents in a `/sprint`. Both runners
were subagents of the same orchestrator session, so both were handed the **same**
scratchpad directory. REQ-647 redirected its partial-harness run to
`scratchpad/run2.log`; REQ-654 happened to pick the same name. Reading the log
back showed two failures in a partial REQ-647 never touched, next to a
`run.sh rc=0` in REQ-647's own task output file. The log was REQ-654's.

## Lesson

**The scratchpad is per orchestrator session, not per runner.** Under `/sprint`,
every runner writes into one directory, so a fixed name (`run.log`, `lint.log`,
`prbody.md`) is a shared global. Give every scratch file a REQ-scoped path
(`scratchpad/req-xxx/…`) from the first write, and take a verdict from the
command's own exit code or its per-task output file. A log another process can
overwrite is not evidence of anything. When a log disagrees with its own exit
code, suspect the file before the code.

## Why It Matters

The collision fails in both directions. A foreign failure can halt or "fix" a
healthy run. A foreign pass can certify a broken one, which is worse, because
nothing looks wrong. The same race corrupts anything handed across fences
through the scratchpad: a PR body, a commit message, an extracted diff.

## Applies When

- Running as a `pipeline-runner`, or any subagent, under `/sprint` or another
  orchestrator that runs several agents at once.
- Writing test output, a PR body, a commit message or a delegate corpus to the
  scratchpad and reading it back in a later call.
- A log shows failures in files this REQ did not change.
