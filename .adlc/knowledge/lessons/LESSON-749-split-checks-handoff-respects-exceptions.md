---
id: LESSON-749
title: "When two checks split one pattern, hand a line over only where the receiving check reads the file, or the receiver's exceptions become lines nobody checks"
component: "adlc/tools/lint-skills"
domain: "adlc"
stack: ["python"]
concerns: ["structural-enforcement", "false-negative", "correctness"]
tags: ["lint-skills", "no-harness-path", "adlc-home", "exceptions", "handoff", "dedup", "coverage-gap"]
req: REQ-666
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-666 Phase 5 Major (TASK-184): adlc-home skipped every .claude/skills line as no-harness-path's, but no-harness-path sets aside install.sh, tools/adlc/checks.py and tools/adlc/harness_probe.py whole, so an unmarked line there was read by neither; fixed by deferring only when the file is not excepted, pinned by tools/lint-skills/tests/test_no_harness_path.py::test_adlc_home_keeps_toolkit_lines_in_files_no_harness_path_sets_aside (7d3bf2c)."
confidence: high
enforcement: test:tools/lint-skills/tests/test_no_harness_path.py
generalizes: []
supersedes: []
---

## What Happened

REQ-666 widened `toolkit-path` into `no-harness-path` and, so that one line is
not reported twice, made REQ-654's `adlc-home` skip any code line holding a
toolkit spelling. The first version skipped it everywhere. But
`no-harness-path` excepts three files whole, so in those files the line was
skipped by one check and never read by the other. The Phase 5 review caught it;
the fix defers only where the receiving check reads the file.

## Lesson

When two checks split responsibility for one pattern so each line is reported
once, the handoff condition must include the receiver's exceptions: defer a line
only where the receiving check will actually read it. Every file, tree or line
the receiver sets aside is otherwise a blind spot neither check covers, and a
clean run proves nothing about it. Test the handoff on each excepted file, not
only on an ordinary one.

## Applies When

Merging, splitting or de-duplicating lint checks, validators or review rules
that overlap on one pattern, or adding an exception list to one of two
cooperating checks.
