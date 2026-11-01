---
id: LESSON-781
title: "A verb that mints or prints a secret is approval surface, however the spec counted the guarded verbs"
component: "adlc/sprint"
domain: "adlc"
stack: ["python", "sh"]
concerns: ["security", "orchestration", "structural-enforcement"]
tags: ["exec-engine", "approval", "token", "enumeration", "same-uid", "resume", "census"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: process
evidence: "REQ-659 Phase-5 finding 'resume or run from inside a run could mint tokens to the caller': BR-10 guards four sub-commands, and implementing added reissue and resume, so resume from inside a run printed fresh approve tokens to whoever ran it. tools/adlc/sprint_exec.py now refuses on ADLC_EXEC_RUN and on a live supervisor, and harness/claude.yml denies all seven verbs, commit 562ebff. The guard was found by reading the code and has no test."
confidence: medium
enforcement: none
generalizes: [LESSON-712]
supersedes: []
---

## What Happened

The spec named the four sub-commands a run must not reach, and the guards were written to that
list. The supervisor design then needed `resume` and `reissue`, which the list predated. `resume`
mints fresh tokens and prints them to its caller, which is the whole of what `approve` protects.

## Lesson

A guarded-verb list is a census taken on the day it was written. Each time you add a verb, ask
what it can produce, not what it is called: anything that mints, prints or replaces a credential
gets the same guards as the verb that spends it. Prefer guarding the whole command, then opening
the read-only verbs, so a new verb starts refused.

## Why It Matters

A token check is only as strong as the weakest path to a token, and the bypass was in new code
written to serve the same feature.

## Applies When

Adding a subcommand, recovery path or operator convenience to anything with an approval, token
or one-way gate, or when a spec enumerates what is guarded.
