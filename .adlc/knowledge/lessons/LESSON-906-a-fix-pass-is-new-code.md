---
id: LESSON-906
title: "A fix pass is new code: narrowing a detector to drop one false positive opened false negatives that only the confirmation review saw"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "python"]
concerns: ["verify-quality", "false-negative", "process-compliance"]
tags: ["phase-5", "fix-pass", "re-verify", "detector", "false-negative", "parallel-agents", "regression"]
req: REQ-672
created: 2026-11-23
updated: 2026-11-23
kind: process
evidence: "REQ-672 Phase 5, merged as f58b13d. The first fix pass narrowed the home-path check in tools/launch/recording_check.py so a URL no longer matched, and the confirmation review found it then missed a home path nested in a longer path; the same pass let a failed fetch pass the lite-req check in tools/launch/quickstart_check.py. Each new test failed before its second fix and passes after: tools/launch/tests/test_recording_check.py::test_a_home_path_nested_in_a_path_or_beside_a_url_is_found and tools/launch/tests/test_quickstart_e2e.py::test_a_failed_fetch_of_origin_fails_the_checks_that_read_origin_main."
confidence: high
enforcement: none
generalizes: [LESSON-440]
supersedes: []
---

## What Happened

Phase 5 of REQ-672 found 33 issues, and five agents fixed them in parallel. Every agent's
own tests passed. The confirmation review then found that the fixes had made new defects:

- A check for home-directory paths matched inside a URL. The fix excluded any match
  preceded by a letter, digit, dot, underscore or hyphen. That also excluded a home path
  nested in a longer path, which the check had caught before.
- A check was changed to read a spec from `origin/main`. Nothing looked at the fetch's
  exit status, so a failed fetch fell back to the stale copy and passed.
- A lint was taught to read the prompt inside `claude "…"`. It read the first argument,
  so a flag before the prompt hid the prompt.

Two more failures came from the agents' boundaries, not their code. A test in one agent's
file pinned a sentence in a document another agent reworded, and a tightened guard
flagged comments in a third agent's files. Each agent ran only its own tests, so nobody
saw either until the suites ran together.

## Lesson

1. A fix that narrows a detector needs must-fire tests for the neighbours of what it now
   excludes, written in the same change. State the exclusion as a property of the benign
   input ("inside a URL: a scheme and a host come before it"), not as a property of the
   character before the match.
2. A fix that adds a new input (a fetch, a second copy, an argument position) adds that
   input's failure. Ask what the code does when the new read fails, and make that a
   refusal, never a fallback to the old source.
3. Brief the confirmation reviewers to hunt regressions in the fix diff, not only to
   confirm the list of fixes. The Step D loop exists for this, and it is where all of
   these were found.
4. When fix agents work in parallel on disjoint files, run the combined suite before
   committing any of their work. A test that pins another file's text and a guard that
   scans another agent's files are both couplings that file ownership does not show.

## Why It Matters

The first review's findings were all marked fixed, and every fix came with a passing
test. Without the second pass, the branch would have merged with a recording check that
missed real home paths, which is the leak that check exists to stop, and an end-to-end
gate that could pass on a stale ref.

## Applies When

Running a fix pass after a review, above all one that changes a detector, a guard or a
lint; deciding whether a confirmation re-verify is worth its cost; dispatching several
fix agents into one working tree.
