---
id: LESSON-751
title: "A spec's measured figures go stale while sibling REQs land — re-measure at Phase 1, and treat any rule conditioned on a measurement as void once the measurement no longer holds"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown"]
concerns: ["correctness", "maintainability", "verify-quality"]
tags: ["spec-validation", "stale-figures", "line-budget", "phase-1", "out-of-scope", "sprint", "re-measure"]
req: REQ-661
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-661 Phase 1: the spec, written 2026-10-27, put template-drift/SKILL.md at 477 lines and wrapup/SKILL.md at 561; on d2eadd7, after REQ-669 and REQ-666 landed, they were 572 and 475, so the Out of Scope exclusion of template-drift ('inside the budget') contradicted BR-1/BR-2 and wrapup no longer needed the split the spec designed around. The spec was amended before architecture (c4e119a)."
confidence: high
enforcement: none
generalizes: [LESSON-604]
supersedes: []
---

## What Happened

REQ-661 was specified against one tree and run against another. Between the two,
three REQs touched the files it measured: `/proceed` grew from 600 to 764 lines,
`/template-drift` from 477 to 572 and past the 500-line budget the REQ enforces,
and `/wrapup` shrank from 561 to 475. The spec's Out of Scope said not to split
`/template-drift` "(477 lines, inside the budget)", its BR-2 said the budget has no
allowlist, and its budget arithmetic for each skill was wrong. Taken literally, the
spec could not pass its own AC-1.

## Lesson

Every number a spec measures on the tree (line counts, section sizes, file counts,
call-site counts) is a snapshot, like its Retrieved Context (LESSON-604). Re-measure
them at Phase 1 before validating, and look for rules whose force depends on a
measurement ("inside the budget", "the only caller", "under max_files"): when the
measurement has moved, the rule that depended on it lapses and the rules it was
balanced against (here BR-1 and BR-2) decide. Amend the spec in Phase 1, recording
the old and new figures and which rule now governs, rather than carrying the
contradiction into architecture.

## Why It Matters

A stale figure produces a plan that cannot meet its own acceptance criteria (a split
set that leaves a skill over the budget), or effort spent where it is no longer
needed (a `/wrapup` split that the tree no longer required). In a sprint the gap
between spec and run is exactly when sibling REQs land.

## Applies When

Validating a spec whose rules or plan rest on measurements of the current tree,
especially when the spec is more than a day old or other REQs touched the same files
since it was written.
