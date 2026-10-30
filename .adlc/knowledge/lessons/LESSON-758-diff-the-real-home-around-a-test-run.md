---
id: LESSON-758
title: "A suite sandboxed by convention leaks through the one test that forgot — diff the real home around a run instead of trusting the fixture"
component: "adlc/tools/adlc/tests"
domain: "adlc"
stack: ["python", "pytest", "sh"]
concerns: ["testing", "test-isolation", "silent-failure"]
tags: ["sandbox", "home-directory", "ledger", "test-isolation", "reservations", "pytest", "interpreter-shim"]
req: REQ-656
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-656: tools/adlc/tests/test_renumber.py sets no HOME and calls renumber.reserve_new_id, so each unsandboxed run appended two `req 700` lines to the real .adlc-own-reservations ledger; 502 had accumulated. Run under a sandbox HOME, the ledger's count stayed 502 and the two lines landed in the sandbox instead."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

A run under an explicit "sandbox every home-directory write" rule still wrote to the real
home, through a test the run did not change and that sat in a suite whose other files
sandbox `HOME` carefully. It surfaced only because a modification-time check of the home
directory listed the ledger, and its last lines were not real ids. The entries are advisory
and keyed on exact shas, so this one is harmless, which is why it had grown to 502 lines
unnoticed.

## Lesson

A sandbox rule held by per-test fixtures is only as strong as the test that forgot. Make it
the suite's default (an autouse fixture), and when a task forbids home writes, verify rather
than assume: snapshot the home directory's modification times before a run and compare after.
When you run under a sandbox `HOME`, pin the interpreter by absolute path and carry the user
site on `PYTHONPATH`: `HOME` can change which `python3` resolves, and a missing-module error
then reads like a clean run that wrote nothing.

## Why It Matters

Test runs happen constantly, in every session, so a small leak into machine state compounds.
A leak into something less forgiving, such as an id counter, would corrupt shared state.

## Applies When

Writing or running tests that reach real allocators, counters or config, or claiming a run
left the machine's state untouched.
