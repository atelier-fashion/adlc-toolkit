---
id: LESSON-845
title: "A reach audit of code the permission check cannot see must follow every executable a fence runs through a variable; a stubbed run is what finds the one the static reading missed"
component: "adlc/tools/adlc/fence-census"
domain: "adlc"
stack: ["python", "sh"]
concerns: ["security", "correctness", "structural-enforcement"]
tags: ["exec-engine", "fence-run", "reach-audit", "opaque-code", "recording-stubs", "static-analysis"]
req: REQ-682
created: 2026-11-09
updated: 2026-11-09
kind: domain
evidence: "REQ-682 TASK-247: test_exec_reach.py::test_real_tree_reach_matches_golden failed on proceed/SKILL.md#4, whose recorded `git rev-parse` was absent from its static reach, because the closure scan read `\"$DELEGATE_TOOLS\"/emit-telemetry.sh` as an opaque external; fence_census.py TOOLKIT_EXECUTABLES and script_reach now read each executable a fence runs, and the test passes. Phase 5 then found the same blind spot for `find -exec` and awk program text (fixture gains-find-exec-merge.sh)."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_reach.py
generalizes: [LESSON-781]
supersedes: []
---

## What Happened

REQ-682 admits one runner, `fence-run`, through which an exec model runs toolkit fences. Its
safety rests on an audit of what each fence can run, because the harness's per-command check
never sees inside it. The static audit indexed shell functions over `partials/*.sh` and treated
anything else at command position as an external. The dynamic audit, every runner fence under
recording stubs, then recorded a `git rev-parse` no static reach named: the telemetry fence runs
`"$DELEGATE_TOOLS"/emit-telemetry.sh`, a script whose own commands the function index never
read. Phase 5 found two more routes of the same kind: a command after `find -exec`, and a
program string handed to awk or sed.

## Lesson

An audit of opaque code is only as wide as what it reads. List every way code runs code (a
function, an executable reached through a variable, `find -exec`, `xargs`, `trap`, an
interpreter's program text), read each one, and make an unknown name a failure rather than an
external. Name each executable a fence runs through a variable in a closed table with every
file it runs. Keep a stubbed run beside the static scan and require each recorded call to be in
the static reach: the static reading proves branches, and the stubbed run proves the reading.

## Why It Matters

A deny-tier call added to a script a fence runs, or hidden behind `find -exec`, would pass a
function-only audit and reach an unattended model's runner with the operator's credentials.

## Applies When

Auditing what an admitted entry point (a runner, a wrapper CLI, a sourced partial) can run,
or adding a script, interpreter call or `-exec` to code such an entry point reaches.
