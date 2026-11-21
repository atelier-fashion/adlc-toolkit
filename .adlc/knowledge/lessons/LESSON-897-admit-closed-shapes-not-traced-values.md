---
id: LESSON-897
title: "A static check that traces values through shell fails open: admit a closed set of shapes and refuse the rest"
component: "adlc/tools/adlc/fence-census"
domain: "adlc"
stack: ["python", "shell"]
concerns: ["security", "reliability"]
tags: ["fence-census", "static-analysis", "taint", "allowlist", "fail-closed", "exec-engine", "review"]
req: REQ-719
created: 2026-11-21
updated: 2026-11-21
kind: domain
evidence: "REQ-719: two versions of the BR-13 census check traced where a PR argument came from, and both were bypassed in review (a command substitution, a pipe into read and $1 in the Phase 5 pass; a fence-defined function, a file written and read back, printenv, $? and an unquoted $opt in the re-verification). The third version admits a closed set of argument spellings, and tools/adlc/tests/test_fence_census.py::test_req719_a_call_that_is_not_a_closed_shape_is_refused holds every bypass as a refused case."
confidence: high
enforcement: test:tools/adlc/tests/test_fence_census.py
generalizes: []
supersedes: []
---

## What Happened

REQ-719 needed a check that no fence hands an unverified PR number to a forge operation. The first version looked at the first argument and at variables assigned from a placeholder. Review got a value past it through a command substitution, a pipe into `read`, a here-string and `$1`. The second version was a real data-flow tracer over the shell text, and it refused all of those. The next review pass got past it again: the output of a function the fence defined, a file written with `tee` and read back with `cat`, `printenv`, an exit status, a redefined adapter function, and an unquoted variable that word splitting turned into `-R other/repo`. The third version stopped tracing. It lists the few spellings a PR argument may take and the few things that may follow it, and refuses every other word. It is shorter than the tracer it replaced, and the same probes plus a further set found one gap, a bash-only syntax the reader mis-split.

## Lesson

When a check must guarantee that only certain values reach a sensitive call, do not try to follow values through a general-purpose language. Write down the exact forms the call may take and refuse everything else, including forms that are harmless. Each bypass of a tracer is a construct the tracer did not model, and shell has more constructs than a tracer will ever model. A closed set has no such tail: a new construct is refused because nobody listed it. If the check is on code the team writes, say so, and let it be strict: the author can always spell the call the listed way.

## Why It Matters

A tracer that fails open looks finished. Its tests cover the bypasses someone thought of, and the next reviewer finds the ones nobody did. Here that cost two fix rounds and two review rounds, and each round ended with a check that still let an unverified value through.

## Applies When

Writing or reviewing a lint, census rule or gate that decides whether text in a shell fence, a config or a template may reach a privileged operation; any time a fix for "value X got through" is to teach the checker one more construct.
