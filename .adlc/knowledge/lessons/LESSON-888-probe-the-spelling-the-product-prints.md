---
id: LESSON-888
title: "A probe passes on the command it ran, not the one the product prints: measure the shipped spelling, character for character"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python", "sh"]
concerns: ["correctness", "testing", "harness-agnostic"]
tags: ["codex", "fence-run", "prefix-rule", "runner-prefix", "probe", "quoting", "exec-engine"]
req: REQ-662
created: 2026-11-18
updated: 2026-11-18
kind: domain
evidence: "REQ-662: .adlc/research/harness-probes/codex-exec-manual.md:42 (the table of seven spellings: the runner line with a bare fence id never matched Codex's prefix allow and its push failed inside the sandbox, every spelling with the id quoted landed), with REQ-664's `runner-prefix` reading pass throughout; fixed in 81af28f, held by test_matcher_none_prompt_routes_the_push_through_the_runner."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_prompt.py
generalizes: [LESSON-870]
supersedes: []
---

## What Happened

REQ-664's `runner-prefix` probe read `pass` on Codex: a stub runner, allowed by an absolute-path prefix rule, ran outside the sandbox. The engine was accepted on that reading. The first real launch then failed: the runner line the prompt prints carries a fence id such as `proceed/phase-0-setup.md#6:877a6b41`, and Codex matches no prefix rule against a command holding a bare `#`. The runner ran inside the sandbox and its push could not reach the remote. Quoting the id fixed it. The probe's command had no `#`, so it could not have caught this.

## Lesson

When a probe stands for a command the product will emit, build the probe's command with the product's own code, or copy it character for character, including quoting, punctuation and argument shapes. A probe of a simpler command proves the mechanism exists, not that the shipped line reaches it. After any gate reads `pass`, run the real line once before relying on it.

## Why It Matters

The gate said yes, every offline test passed, and the first unattended run would have failed at Step 0 on every REQ. A harness's command parser is the least documented part of it.

## Applies When

Writing or accepting a probe, a fake, or a fixture that stands in for a generated command line; changing how a prompt spells a command the harness must match against a rule.
