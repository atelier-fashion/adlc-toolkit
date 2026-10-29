---
id: LESSON-740
title: "A safety net that reuses the first pass's detectors cannot catch the first pass's blind spots — write the residue check separately, then run both over the real corpus"
component: "tools/dataset/residue"
domain: "privacy"
stack: ["python"]
concerns: ["privacy", "security", "data-governance"]
tags: ["redaction", "scrub", "defense-in-depth", "residue", "differential", "fail-closed"]
req: REQ-671
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-671 Phase-5 reflector Critical: infrastructure#50 shipped past tools/dataset/scrub.py and the residue pass, which imported the same detectors.py; fixed by rewriting tools/dataset/residue.py as an independent Checker and re-verified"
confidence: high
enforcement: test:tools/dataset/tests/test_dataset_scrub.py
generalizes: [LESSON-614]
supersedes: []
---

## What Happened

REQ-671's export scrubs private repo names, then runs a "residue" pass over the output
that refuses the export on any hit. The first design had the residue pass import the
scrub's own detectors and skip only the replacement code. The reasoning was that a
replacement bug could not hide from it. The Phase-5 reflector exported the real tree
and found `admin-api#82, infrastructure#50` published as
`consumer-repo-1#82, infrastructure#50`. The scrub's `repo-context` rule did not count
`#` after a name as a repository context, and the residue pass asked the same function
the same question and got the same wrong answer. The test that "searched the export for
DenyList names" shared that grammar too, so all three layers passed.

## Lesson

A second pass guards only against the failure modes it does not share with the first.
Reusing the detectors makes it a check of the *replacement* code, not of the
*detection*. To catch detection gaps:

1. Write the residue checks again, without importing the scrub's detector module. Make
   them broader wherever that is cheap (a name next to any non-prose character, not a
   list of contexts; text after Unicode normalization; a name in a record that also
   holds its own placeholder).
2. Run both passes over the real corpus, not only over fixtures one author wrote. The
   leak, and the later `tetond` alias leak, showed up only in real artifacts.
3. When the two passes disagree, the scrub is wrong, or the residue pass is too broad.
   Either way, fix the disagreement. Do not just make them agree.

## Why It Matters

A defense-in-depth layer that shares code with the layer it guards reports "clean" in
exactly the cases that matter. Here that meant a private repository's name and PR
numbers in a public dataset, with every check green.

## Applies When

You build a redaction, scrub or sanitizer step and add a verification pass after it.
That covers a residue scan, a "search the output" test or a post-export audit. It also
covers any detector whose answer gates what leaves the machine.
