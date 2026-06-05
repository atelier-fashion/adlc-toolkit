---
id: LESSON-330
title: "The Phase-5 review catches OMITTED requirements, not just bugs — cross-check every BR against the diff"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "claude-skills"]
concerns: ["process", "testing", "correctness", "completeness"]
tags: ["phase-5-review", "business-rules", "omitted-requirement", "br-coverage", "reflector", "test-auditor"]
req: REQ-483
created: 2026-06-04
updated: 2026-06-04
---

## What Happened

REQ-483 had 16 Business Rules. During implementation, **BR-11 (stale-blocker safety) was implemented-as-zero** — there was no stale detection anywhere in the diff. Lint passed clean, and the happy-path dogfood never exercised the missing rule, so nothing flagged it. The Phase-5 6-agent review caught it: the **reflector** and the **test-auditor** *independently* reported BR-11 as a Critical "entirely unimplemented" finding. The same review also caught fetch-before-trial-merge (a stale-tip false pass), a missing LESSON-004 ready/create fallback, and a footprint-clobber — gaps a confident implementer had not self-surfaced.

## Lesson

A multi-BR spec can have an **entire business rule silently skipped**: the implementer believes the work is done, lint is green, and no happy-path check touches the missing rule. The Phase-5 reviewer panel is the structural backstop that catches **omitted requirements**, not just bugs in code that *was* written — but only if it is pointed at coverage. Two practices:

1. **Before Phase 5, do an explicit BR → diff coverage cross-check.** Map every numbered BR to the file/line that implements it; a BR with no mapping is a red flag. (Catching a missing BR at architecture/implement is far cheaper than at review, and orders of magnitude cheaper than in production.)
2. **Treat the reflector + test-auditor as requirement-coverage auditors**, not only bug-finders. Their highest-value output is often "what's missing." Prompt them to enumerate each BR/AC and mark met / partial / unmet, because the implementer who skipped a rule is exactly the one who won't notice they did.

## Why It Matters

"Verify, Don't Trust" (ethos #4) applies to **completeness**, not just correctness. The odds of dropping a rule scale with BR count — the more rules a spec has, the more likely one is implemented-as-zero. Here the missing rule was a teammate-safety feature (a stale PR would otherwise present as an indefinite blocker); shipping it silently absent would have surfaced only when a real human hit the deadlock. The multi-agent review earned its cost on this REQ precisely because it audited *coverage*, catching an omission no single-pass self-check did.
