---
id: LESSON-745
title: "A test of a command that reads the caller's repository must run outside the checkout — a committed result the command reads flips it"
component: "adlc/tools/adlc/tests"
domain: "adlc"
stack: ["python", "pytest", "git"]
concerns: ["testing", "reliability", "test-isolation"]
tags: ["cwd", "sandbox", "subprocess", "git-rev-parse", "committed-artifact", "harness-detect"]
req: REQ-664
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-664 Phase-5 finding (test-isolation, Major): tools/adlc/tests/test_harness.py::test_only_claude_on_path passed until the live run committed .adlc/research/harness-probes/claude.json, then failed because its _run helper inherited the checkout as cwd and adlc harness detect read that file for its last_probe column; passing cwd=tmp_path made it pass again (squashed into 62079e9, PR #210)."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-664 gave `adlc harness detect` a `last_probe` column that reads
`<git toplevel of cwd>/.adlc/research/harness-probes/<name>.json`. The existing
detect tests spawned the CLI with a sandbox HOME and PATH but no `cwd`, so they ran
from the toolkit checkout. They passed until the same branch committed a real
`claude.json`; from then on the claude row read `2026-10-29` instead of `never`.

## Lesson

When a command derives anything from the caller's repository (`git rev-parse
--show-toplevel`, a relative `.adlc/...` path, a config walk), every test that runs
it must pass an explicit `cwd` inside its sandbox. Sandboxing HOME and PATH is not
enough: the checkout is the third input. The trap springs late, on the commit that
adds the first real artifact the command reads, which is usually the same change.

## Why It Matters

The failure looks like a regression in the feature, not in the test, and it depends
on what else happens to be committed. A fixture planted by the test hides it; only
a real artifact landing in the checkout reveals it.

## Applies When

Adding a read of the caller's repository to an existing CLI, or writing a test that
spawns a repo-aware command: give every such subprocess an explicit sandbox `cwd`.
