---
id: LESSON-916
title: "An exemption from credential redaction must be checked against what the repository holds, never against a grammar: a credential can always be shaped to fit the grammar"
component: "adlc/tools/delegate"
domain: "adlc"
stack: ["python"]
concerns: ["security", "privacy", "correctness"]
tags: ["redaction", "credentials", "citation", "exemption", "decline-reason", "fix-pass", "phase-5"]
req: REQ-722
created: 2026-11-25
updated: 2026-11-25
kind: domain
evidence: "REQ-722 Phase 5, merged as b327ffd: the first fix kept a credential match whole whenever it sat inside a token cross_family.citation_tokens parsed as a citation; the Step D security re-check reproduced test:a/b::sk-<24> and AKIA<16>/x.py:3 surviving unredacted into the PR body; the second fix keeps only spans DeclineChecker.confirmed_spans verifies at HEAD (a tracked file with the line in range, or a test the tracked file defines). tools/delegate/tests/test_run_outcome.py::test_decline_reason_keeps_citations_whole pins each shape."
confidence: high
enforcement: "test:tools/delegate/tests/test_run_outcome.py"
generalizes: [LESSON-744]
supersedes: []
---

## What Happened

REQ-722 stores a declined finding's `declineReason`, which must cite code (`path:line` or
`test:<path>::<name>`). The five-arm credential chain over-matches kebab paths
(`tools/risk-assessment-<20 chars>.py` holds an `sk-` run, LESSON-744), so redaction broke
the citation and the Phase-6 check could never pass. The first fix exempted any chain match
lying inside a token the citation grammar accepted. The Step D security re-check then wrote
credentials in citation shape (`AKIA…/x.py:3`, `test:a/b::sk-…`, `q/OPENAI_API_KEY:1234`):
every one came back unredacted and would have been printed in the PR body. The second fix
keeps a match only when the citation checks out against `HEAD`, and redacts everything when
no checkout is available.

## Lesson

A grammar describes what a value *looks like*; an attacker, or a model echoing one,
controls what a value looks like. So never let "it parses as a citation, a path, an id" be
the reason to skip redaction or validation. Exempt a span only when it is confirmed against
ground truth the text cannot forge: here, the repository at `HEAD` holds that file with that
line, or that test. When the ground truth is unavailable, fail toward redaction. Write the
must-fire tests for the exemption by building credentials *in the exempted shape*, not only
plain credentials.

## Why It Matters

Each exempted match was a credential passed straight to a PR body, a log, or a state file
that is copied off the machine. It also passed every existing test, because those tests only
checked that real citations survive and that plain keys are redacted; none asked whether a
key could pass as a citation.

## Applies When

- Adding an allow-list, exemption or "keep whole" rule to redaction, sanitisation or
  validation, especially one keyed on a token's format.
- A fix that makes a redactor preserve structured text (paths, ids, URLs, test names) so a
  later check can still read it.
- Reviewing such a fix: write credentials shaped like the exempted format and assert they
  are still removed.
