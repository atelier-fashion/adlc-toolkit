---
id: ASSUME-029
title: "A recorded regression test is one the project's test runner actually collects"
status: unresolved
req: REQ-691
created: 2026-11-05
resolved:
---

## Assumption

A test file that `/bugfix` records in `regression_tests` is one the project's own test runner picks up. The check confirms the file exists, is tracked and committed as a regular file, and cites its bug id. It does not confirm the runner's include globs reach it.

## Context

REQ-691's check is deliberately stack-agnostic, so it cannot ask a runner what it collects. `/bugfix` mitigates this by running the test without and with the fix (Write and contrast), and both runs must use the project's test command. A file outside the runner's globs fails that contrast step, though not the later check. So the gap is a hand-recorded or later-moved test file. The first consumer, embolden-website, is wiring the check into `gates` as a follow-up REQ.

## Resolution

Unresolved. Check it when the first project runs `adlc regression-check check` in CI: compare the recorded paths against the runner's collected-file list once, and if a recorded test is not collected, spec a runner-aware check.
