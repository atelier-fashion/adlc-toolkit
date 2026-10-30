---
id: LESSON-748
title: "Fit skill text to one harness's restriction by keeping the portable rule apart from the harness-specific spelling, so only the portable half outlives the harness"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "sh", "python"]
concerns: ["portability", "harness-agnostic", "maintainability", "structural-enforcement"]
tags: ["multi-harness", "teton", "dispatch", "inline-fallback", "lint-skills", "retirement", "harness-specific"]
req: REQ-666
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-666 (7d3bf2c, TASK-179, TASK-180): retiring the Teton Code provenance surface meant deleting harness-skip, provenance-safe-fence and missing-harness-line with their fixtures plus every BUG-228/BUG-230 line in skill and lint text, while BUG-230's portable halves (a dispatch says what to do without subagents; an inline audit is read-only) survived as the dispatch paragraph and dispatch-has-fallback."
confidence: low
enforcement: none
generalizes: []
supersedes: [LESSON-662, LESSON-663]
---

## What Happened

REQ-666 retired the surface BUG-218 to BUG-230 fitted to Teton Code's shell
classifier, because none of the five harnesses the toolkit now targets
classifies shell provenance. The classifier-specific half (a grammar allowlist,
a skip line keyed on the harness, two lint checks) was woven through every
delegating skill and the lint, so removing it took a REQ of its own. The two
rules BUG-230 found underneath it were worth keeping on every harness, and they
had to be lifted out of the Teton prose before the rest could go.

## Lesson

When a skill must accommodate one harness's restriction, write two things
separately:

- the **portable rule** that every harness benefits from (say what to do with
  no agent tool; keep an inline audit read-only), as plain skill text with its
  own lint check;
- the **harness-specific spelling** (a command grammar, a skip line, a
  provenance marker) in one place that names the harness, so it can be found
  and deleted in one change, lint and text together.

When the harness is dropped, delete the second and keep the first. LESSON-662's
"route around the classifier in the skill text" and LESSON-663's "allowlist the
classifier's grammar" no longer apply: there is no classifier to route around.

## Applies When

Adapting skills, partials or lint to a specific agent harness's limits, or
retiring support for one.
