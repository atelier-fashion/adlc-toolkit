---
id: LESSON-752
title: "Before moving text out of a SKILL.md, list every harness that reads it by path — the readers you may not edit decide what stays"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "sh", "python", "claude-skills"]
concerns: ["maintainability", "structural-enforcement", "testing"]
tags: ["progressive-disclosure", "references", "skill-split", "partials-tests", "space-build", "text-readers", "refactor-planning"]
req: REQ-661
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-661 architecture ADR-3: the spec's budget arithmetic proposed moving /spec Step 1.6 whole, but partials/tests/lesson-check.test.sh:1291 reads its five scoring lines (and sub-step 8, the 7a lookup line and Step 3) from spec/SKILL.md, space/build.mjs:224 reads Step 1.4's intake-gap-rules block from it, and BR-11 forbade editing partials/; the split moved two whole numbered sub-steps instead and run.sh passed unchanged (c4e119a)."
confidence: medium
enforcement: none
generalizes: [LESSON-742]
supersedes: []
---

## What Happened

REQ-661 split three oversized skills into `SKILL.md` plus companion files. The spec
offered the largest steps as the obvious candidates. A grep for every reader of
`spec/SKILL.md` showed that the shell test harness, the Space build and three lint
contract tests extract specific lines and sections from that exact path. Moving the
largest step would have broken a harness the REQ was not allowed to edit, and some of
those readers would have failed in a way a clean lint run does not show.

## Lesson

Treat "which text moves" as constrained by its readers, and inventory them before the
design, not after the edit (LESSON-742 says to run them afterwards). Run
`grep -rl '<skill>/SKILL.md' partials/tests tools space workflows` and read what each
hit extracts: a heading range, a marker block, a verbatim line. Then sort the readers
into those you may change in this REQ (point them at the new file) and those you may
not (their text stays where it is). Choose the moved units from what is left, as whole
sections or whole numbered sub-steps, and record which reader pinned each part that
stayed.

## Why It Matters

A move that breaks a reader you cannot edit either blocks the REQ late, after the
split is built, or pushes an out-of-scope edit into it. A reader that degrades
quietly (a build that reads an empty block, a coupling comment that names the old
file) can pass every gate and rot.

## Applies When

Splitting, moving or renaming sections of a skill, an agent file or any markdown that
tests, builds or lints extract by path, especially when some of those readers are
outside the change's allowed footprint.
