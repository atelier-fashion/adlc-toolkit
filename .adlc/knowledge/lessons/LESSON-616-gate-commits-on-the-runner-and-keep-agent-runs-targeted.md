---
id: LESSON-616
title: "Gate commits on the runner's exit code, and keep agent verification runs targeted"
component: "adlc/proceed"
domain: "adlc"
stack: [shell, python]
concerns: [process, reliability]
tags: [commit-gating, exit-code, mutation-testing, agent-stall, cpu-contention, orchestration]
req: REQ-609
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

Orchestrating REQ-609, I committed with a failing test three times: I read the
pytest tail, saw "1 failed", and ran the commit anyway because the commit line
was not conditioned on the runner's result. Separately, the TASK-094
implementing agent stalled for ten minutes and was killed: its mutation
re-runs executed the whole `tools/` suite in a scratch copy while other agents
ran suites in the same worktree, and under that CPU contention each run
overran the tool's two-minute limit; the suite itself took thirty seconds when
run alone. A third agent could not exit non-zero by contract, and a guard
written as `exit 1` for skills had to become a degrade path for it.

## Lesson

Chain `commit` behind the test command's exit status — `pytest ... && git
commit` or an explicit `if` — never behind a human reading of the tail; the
tail is a claim, the exit code is the evidence (LESSON-478, applied to
oneself). When several agents share a machine, give each mutation or
confirmation run the *targeted* test files that can kill its mutations, run
the whole suite once at the end in the background, and tell agents the
suite's normal wall time so they can tell "slow" from "hung". Read an agent's
contract (may it exit non-zero? may it commit?) before prescribing a fix shape
to it.

## Why It Matters

A commit with a red test poisons bisects and forces amends; a stalled agent
loses its context and its unreported findings, and the orchestrator has to
reconstruct what it did from the worktree.

## Applies When

Any orchestrator committing on an agent's behalf; any prompt that asks an
agent to mutation-test; any pipeline with more than one agent running suites
concurrently; any fix applied to a file that declares its own error contract.
