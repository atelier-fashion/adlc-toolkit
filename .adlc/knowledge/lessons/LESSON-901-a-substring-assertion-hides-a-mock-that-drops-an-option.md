---
id: LESSON-901
title: "A substring assertion on a round-tripped value hides a mock that drops an option: assert the whole value, and make the mock honor the option the code relies on"
component: "adlc/tools/adlc/forge-mock"
domain: "adlc"
stack: ["python", "shell"]
concerns: ["testing", "correctness"]
tags: ["forge-mock", "mock-fidelity", "round-trip", "pr-body", "footprint", "adversarial-review", "test-oracle"]
bug: BUG-288
created: 2026-11-21
updated: 2026-11-21
kind: domain
evidence: "BUG-288, adversarial review of the fix: tools/adlc/forge_mock.py printed the JSON document for `pr_view --json body -q .body`, so the footprint fence wrote back '{\"body\": \"body of 101\"}' followed by the block, and test_bug288_the_runs_own_pr_still_gets_its_footprint passed on it because it asserted `\"body of 101\" in body`. With the mock printing the field (test_forge_mock.py::test_bug288_view_with_a_one_field_query_prints_the_field) the test asserts the exact body after one run and after a second, which replaces the block."
confidence: high
enforcement: test:tools/adlc/tests/test_forge_mock.py
generalizes: []
supersedes: []
---

## What Happened

The footprint fence reads a PR body with `adlc_forge_pr_view "$prNumber" --json body -q .body`,
removes any earlier footprint block, appends a new one and writes the body back. The mock
forge accepted `-q` and ignored it: it printed `{"body": "…"}`. Under the mock the fence
therefore wrapped the body in JSON on every run, and its `sed` never found the earlier block,
because the block sat inside one JSON line.

The benign-path test for BUG-288 checked that the original text was in the new body and that
the block was there. Both held for the wrapped body, so the test passed. The bug report even
quoted the wrapped body as the unfixed tree's output without anyone reading it as wrong. An
adversarial review of the diff pointed it out.

## Lesson

When code reads a value, changes it and writes it back, assert the whole written value, not
that a piece of the original is in it. Then run the round trip twice and assert again, so
replacement is told apart from addition.

When a mock takes an option the code under test depends on, the mock must do what the real
tool does with it, or refuse it. Accepting and ignoring it is the one behaviour that makes
every test of that code path pass for the wrong reason. Model the exact shape the code uses
and leave the rest as it was.

## Why It Matters

The test was the only one that ran the fence's body handling through the real adapter. With
a substring assertion and a mock that drops `-q`, any change that corrupted a PR body would
have passed. Phase 6's fence reads the footprint back with the same call, so under the mock
it had never seen a real body either.

## Applies When

Writing a test that drives a read-modify-write of forge data through `forge_mock.py` or any
other stand-in; adding an option to a call the mock answers; reviewing a test whose oracle is
`in` on text the code is supposed to preserve.
