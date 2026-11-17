---
id: LESSON-874
title: "A retry under a new id must be covered by every rule rendered before the run, or it escapes the rule it was meant to test"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "retry", "gemini", "deny-policy", "ask-tier-deny", "pre-rendered-config"]
req: BUG-280
created: 2026-11-16
updated: 2026-11-16
kind: domain
evidence: "BUG-280: the first version of the ask-tier-deny retries ran a retried deny-under-allow as <lid>r2 on gemini, whose deny policy (written once before the run, keyed by launch id) did not name it, so the command ran and read fail; test_final_message_rules (abort-on-deny) caught it, and attempt_lids in 46a64bc fixed it; test_gemini_deny_policy_covers_retries fails without the fix."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-870]
supersedes: []
---

## What Happened

BUG-280 added retries to `ask-tier-deny`'s launches. Each retry runs under its own id, `<lid>r2` and on, so its sentinels, refs and captures are its own. Most of a launch's rules are written per attempt, so they followed the new id.

Gemini's deny rules are different. They live in one user-level policy file written once, before the run, and keyed by each planned launch's id. A retried `deny-under-allow` therefore ran under an id the policy never named. Its command went through and read `fail`, as if gemini's deny did not hold. A probe test caught it, before any live run.

## Lesson

**When a launch can be retried under a new id, every rule rendered before the run must name every id a retry can take.** Rules written per attempt follow the id automatically. Rules written once, such as user-level policy files and pre-flight renders, do not. Generate both the attempt ids and the pre-rendered rules from one helper (`attempt_lids`), so the two cannot drift apart.

**A retry that "worked" when the first attempt was denied is a warning sign, not a result.** Check whether the retry escaped the rule before believing it.

## Applies When

Adding retries, or any per-attempt naming, to a probe or test harness whose configuration is partly rendered before the run and partly per launch. It matters most where the pre-rendered part is the rule under test, such as a deny policy.
