---
id: LESSON-898
title: "A Python pattern that ends in $ admits a trailing newline: end a validating pattern in \\Z or use fullmatch"
component: "adlc/tools/adlc/exec-safety"
domain: "adlc"
stack: ["python"]
concerns: ["security", "reliability"]
tags: ["regex", "validation", "newline", "log-injection", "operator-output", "exec-engine"]
req: REQ-719
created: 2026-11-21
updated: 2026-11-21
kind: domain
evidence: "REQ-719: a prUrl in session-written state that ended in a newline passed exec_safety.PR_URL and split the abort line in two; tools/adlc/tests/test_exec_approve.py::test_req719_abort_prints_only_a_well_formed_pr_url failed on it and passes since the pattern ends in \\Z, and tools/adlc/tests/test_exec_safety.py::test_req719_no_identifier_pattern_admits_a_trailing_newline holds the five other identifier patterns that had the same ending."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_safety.py
generalizes: []
supersedes: []
---

## What Happened

The exec engine validates a PR URL from the session's state file before it prints it in the line an operator reads after `abort`. A test fed it hostile values, and one printed: a well-formed URL followed by `\n`. In Python, `$` matches at the end of the string and also just before a newline that ends it, so `^…/pull/([0-9]{1,10})$` accepted the value and the printed line became two lines. The same ending was on the patterns for a REQ id, a repo id, a branch, an oid and a slug, and on a copy of the REQ id pattern the fence runner keeps for itself.

## Lesson

A pattern that decides whether untrusted text is safe to print, log or pass on must end in `\Z`, or be applied with `fullmatch`. `$` is for matching lines, not for validating values. When fixing one such pattern, search the module and its copies for the same ending, and add a test that feeds each pattern its own good value with `\n` appended.

## Why It Matters

One trailing newline is enough to forge a second line in output a person or a parser trusts. The dashboard row in the same change prints commands an operator copies, so a forged line there is an instruction.

## Applies When

Writing or reviewing a regular expression in Python that validates an identifier, URL, path or token from a file or a process the code does not control, and whose result is printed, logged or interpolated into a line.
