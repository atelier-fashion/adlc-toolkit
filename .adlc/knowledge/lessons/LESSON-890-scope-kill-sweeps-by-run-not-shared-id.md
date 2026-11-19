---
id: LESSON-890
title: "A kill sweep keyed on an id two runs can share kills the other run: tag processes with something only this run has"
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing", "unattended"]
tags: ["exec-engine", "process-sweep", "concurrency", "test-isolation", "parallel-agents", "pid-reuse"]
req: REQ-662
created: 2026-11-18
updated: 2026-11-18
kind: domain
evidence: "REQ-662: the straggler sweep matched every process carrying ADLC_EXEC_RUN=<req>, so two test runs of the exec suites killed each other's fake harnesses and tasks had to run one at a time; after the sweep also matched a digest of the run directory, several agents ran those suites at once. Held by test_straggler_sweep_is_scoped_to_its_own_run. The Phase-5 correctness finding on reused pids (a recorded pid read without its start time) is the same shape. Merged in 81af28f."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_launch.py
generalizes: []
supersedes: []
---

## What Happened

The exec engine ends a run by killing every process whose environment carries `ADLC_EXEC_RUN=<REQ id>`. A REQ id is not unique on a machine: two projects number alike, and every test uses `REQ-901`. Two test runs at once killed each other's processes, which showed up as random failures and forced the implementation tasks to run serially. The same engine also treated any recorded process id that answered a signal as its own harness, so a reused pid could refuse the operator or be signalled by `abort`.

## Lesson

Anything that finds processes to kill, refuse or wait on must match on an identity only this run has: a per-run token in the environment, or a pid together with its start time. An id that names the work (a REQ, a branch, a port) names every run of that work. When tests "cannot run in parallel", look for a machine-wide key before accepting the limit.

## Why It Matters

In production two projects with the same REQ number would have killed each other's harness sessions. In development the limit cost hours of serial task runs until the cause was found.

## Applies When

Writing a process sweep, a liveness check, a lock or a cleanup keyed on an id; diagnosing tests that fail only when another run is in flight.
