---
id: LESSON-753
title: "A test that walks skills by glob loses moved text silently — pin a floor per file family, not a nonzero total"
component: "partials/tests"
domain: "adlc"
stack: ["posix-sh"]
concerns: ["testing", "test-coverage"]
tags: ["corpus-walk", "companions", "references", "progressive-disclosure", "fence-count", "source-guard"]
req: BUG-255
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "BUG-255: after REQ-661 (c4e119a) moved /spec Step 1.4 step 3 and Step 1.6 sub-step 7 into spec/references/, partials/tests/source-guard.test.sh still passed with 60 fences extracted; walking <skill>/references/*.md raised it to 69. The new fence_extraction_reaches_companions and fence_extraction_walks_companions checks fail when the references/ leg of skill_unit_files is deleted and pass with it."
confidence: high
enforcement: "test:partials/tests/source-guard.test.sh"
generalizes: []
supersedes: []
---

## What Happened

REQ-661 split oversized `SKILL.md` files into `<skill>/references/*.md` companions and
taught `tools/lint-skills/check.py` to walk a skill and its companions as one unit.
`partials/tests/source-guard.test.sh` kept its own three `find -name SKILL.md` lists.
Nine sourcing fences left its run, and the suite stayed green, because its only guard
on the corpus was "more than zero fences extracted". LESSON-752's reader inventory
(`grep -rl '<skill>/SKILL.md'`) cannot find this kind of reader: it names no skill, it
matches every `SKILL.md` by glob.

## Lesson

When text moves between files, look for two kinds of reader: those that name the file
(LESSON-752), and those that select files by a glob or `find -name`. A glob reader does
not break when text leaves the files it matches. It just reads less. Give every such
walk one shared helper that mirrors the lint's definition of the corpus, so a new file
family gets added in one place. Then pin a floor on what each family contributes (here,
fences extracted from `references/`), not only on the total, so losing one family turns
the test red.

## Why It Matters

A coverage test that loses part of its corpus keeps passing, so nobody notices the gap.
The moved fences ran under no shell until someone read the spec's Deferred list.

## Applies When

- Moving skill or doc text into a new file family (companions, phase files, partials).
- Writing or reviewing a test whose corpus is "every file matching X".
- A coverage test's only non-vacuity guard is a nonzero count.
