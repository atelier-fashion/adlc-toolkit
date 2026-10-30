---
id: LESSON-756
title: "A framework proven on one adapter has only proven that adapter's branches — audit what the second one reaches first, because those paths have never run"
component: "adlc/harness"
domain: "adlc"
stack: ["python", "yaml", "json"]
concerns: ["testing", "correctness", "harness-agnostic", "silent-failure"]
tags: ["multi-harness", "adapter", "framework", "fixture", "second-consumer", "golden", "lint", "fail-closed"]
req: REQ-656
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-656 Phase 5 and architecture ADR-4, commit e0b0e7f: REQ-657 shipped with the claude adapter and fixtures, and the first real second adapters found a deny clash read after the omission pass, so Shell(git) would have denied all of git (test_clash_reads_candidates_not_survivors); render-parity failing on any clone with a local .cursor directory (test_a_local_cursor_dir_does_not_fail_parity); unguarded-source blind to Copilot's flat hook entries (test_unguarded_source_walks_the_copilot_render); and body rewriting that turned 'Write tests' into 'edit tests' once Write mapped to another word (test_agent_body_rewrites_tool_names_only). Each failed or was absent before its fix, and passed on re-verify."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_adapters.py
generalizes: []
supersedes: []
---

## What Happened

REQ-657's framework passed every gate with `claude` plus two fixture adapters. The first
real adapters reached code neither had: a hard deny under a shared base, a second file
on one surface, a report-only row, a printed surface, a tool map that renames. Four
defects sat on those paths, and none could have failed before, because nothing ran there.
A fixture written beside the framework shares the framework's assumptions: it exercised
the branches its author had in mind.

## Lesson

When the second consumer of a framework arrives, list what it reaches that the first
never did, and treat each as unproven code rather than as a dependency. Look for checks
that read a post-processed list (the omission had already emptied what the clash check
tested), validators that walk one consumer's shape, and "the toolkit's own copy"
assumptions that hold for one consumer alone. Then render the real output and read it:
"edit tests" was visible in the first rendered agent, and no test of the framework would
have asked.

## Why It Matters

These failures are silent in the first consumer's gates. Two would have shipped green: a
render denying all of git, and a hook file no lint was reading.

## Applies When

Adding a second implementation behind an interface or a data-driven framework, or
trusting a framework's test suite to cover a consumer it has not met.
