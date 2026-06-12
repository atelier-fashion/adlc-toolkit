---
id: TASK-002
title: "Rewrite project-overview.md to describe the current tree truthfully"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

`project-overview.md` is frozen two epochs back (BR-3). Correct the false claims:
the toolkit DOES track its own lessons (`.adlc/knowledge/lessons/`, ~40 files) and bugs
(`.adlc/bugs/`); numbering is remote-derived per REQ-518 (the "local high-water REQ-263"
anchor is historical, not current policy); the 4.x delegation and 5.0 portability epochs
exist (VERSION is 5.0.0). Tag claims that will date with an as-of marker or replace them
with a pointer to the authoritative artifact (CHANGELOG, VERSION).

Depends on TASK-001 (both edit project-overview.md) to avoid a same-file edit collision —
TASK-001 fixes line 25's "Five principles"; this task touches lines 7, 32, 34–46.

## Files to Create/Modify

- `.adlc/context/project-overview.md:7` — drop "No `.adlc/knowledge/lessons/`, `.adlc/bugs/` … inside this repo"; the repo now has both
- `.adlc/context/project-overview.md:32` — "The toolkit doesn't track lessons or bugs for itself yet" → state it tracks both, pointing at the dirs
- `.adlc/context/project-overview.md:34–36` ("Current scope") — refresh; add as-of marker or point at CHANGELOG/VERSION rather than a frozen date
- `.adlc/context/project-overview.md:38–46` ("REQ-numbering policy") — reframe as remote-derived per REQ-518; mark "REQ-263 local high-water" and the `.global-next-req` file anchor as historical; note the 5.0 portability epoch

## Acceptance Criteria

- [ ] `grep -rn "doesn't track lessons\|don't track lessons\|track lessons or bugs for itself yet" .adlc/context/` returns nothing
- [ ] project-overview.md states the toolkit tracks lessons and bugs, with correct dir paths
- [ ] Numbering section reflects REQ-518 remote-derived allocation; REQ-263 anchor framed as historical
- [ ] No claim is contradicted by the tree (spot-check: lessons/bugs tracking, numbering policy, epoch list)
- [ ] Dating-prone claims carry an as-of marker or point at CHANGELOG/VERSION

## Technical Notes

Reference REQ-518 (collision-safe remote-derived id allocation) and the 5.0 portability
epoch (REQ-515/517/519/516/518/520) per CHANGELOG. Don't enumerate epoch contents inline
(that re-creates rot — LESSON-019); point at CHANGELOG as authoritative. Keep the
"Primary surface areas" table's row count consistent with TASK-001's principle-count edit.
