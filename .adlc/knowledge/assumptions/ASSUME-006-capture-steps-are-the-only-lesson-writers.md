---
id: ASSUME-006
title: "The /wrapup and /bugfix capture steps are the only writers of LESSON-* files, so a writer-side check covers every lesson"
status: validated
req: REQ-646
created: 2026-10-27
resolved: 2026-10-27
---

## Assumption

Every `LESSON-*.md` the toolkit produces is written by exactly two code paths —
`/wrapup` Step 4 and `/bugfix` Phase 6 Step 4 — so a structural check placed at
those two write points (`adlc_lesson_check`) validates every lesson without a
corpus-wide scan, and "new lesson" can be defined by *who writes it* rather than
by a ship-date cutoff (REQ-646 BR-2, after the `/adversary` pass dropped the
cutoff).

## Context

REQ-646's enforcement posture rests on this: if a third writer existed (an agent,
the workflow engine's close-out leaf, a sprint summary step), lessons could land
unchecked and the "new by construction" rule would have a hole. LESSON-712
(BUG-249) had just shown that an ownership rule reaches only the sites you
enumerate, so the census mattered.

## Resolution

Validated during REQ-646 `/architect` Step 2 and the Phase-5 architecture
review: the only `adlc_alloc_id lesson` call sites in the tree are
`wrapup/SKILL.md` and `bugfix/SKILL.md`; `agents/pipeline-runner.md` and the
workflow engine's close-out leaf both route through `/wrapup` (BUG-249 close-out
mode), and `agents/reflector.md`, `/architect` and `/spec` only read lessons.
Hand-written lessons outside those steps remain unvalidated by design (REQ-646
Assumptions); a corpus-wide run of `adlc_lesson_check` is a possible follow-up,
not a gap in this assumption.
