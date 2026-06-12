---
id: TASK-001
title: "Correct every 'five principles' claim to not hardcode the count"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: []
repo: adlc-toolkit
---

## Description

ETHOS.md has seven numbered principles, but four context-doc claims still say "five".
Rephrase each to drop the hardcoded count (BR-1, informed by LESSON-019: counts are
presence-guards that rot). Use "the ETHOS principles" rather than substituting "seven",
so the claim never rots again. At most one place may state a number, and none chosen here.

## Files to Create/Modify

- `.adlc/context/architecture.md:7` — `# 5 principles — injected into every skill` → drop count
- `.adlc/context/architecture.md:25` — `inlines the five principles at invocation time` → `the ETHOS principles`
- `.adlc/context/conventions.md:144` — `the five principles (especially #4 … #5 …)` → `the ETHOS principles (especially …)`
- `.adlc/context/project-overview.md:25` — `Five principles injected into every skill` → `ETHOS principles injected …`

## Acceptance Criteria

- [ ] `grep -rn 'five principles\|5 principles' .adlc/context/ README.md` returns nothing
- [ ] The `#4`/`#5` parenthetical in conventions.md:144 still makes sense after rephrase
- [ ] No claim now hardcodes "seven" either (count-free phrasing)

## Technical Notes

Keep the surrounding sentence meaning intact — only the count phrasing changes. The
conventions.md line references specific principle numbers (#4, #5) as examples; those are
fine to keep since they point at stable principles, but the leading "the five principles"
must become "the ETHOS principles".
