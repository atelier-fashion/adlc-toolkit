---
id: TASK-004
title: "Mirror global REQ-counter policy in .adlc/context/project-overview.md"
req: REQ-380
status: pending
created: 2026-05-04
updated: 2026-05-04
dependencies: []
repo: adlc-toolkit
---

## Files to Modify
- `.adlc/context/project-overview.md`

## Acceptance Criteria

- [ ] A new section is added (after "Current scope") that declares: future REQ allocations from this repo MUST take the next slot above the **global** counter (currently anchored by atelier-fashion's high-water REQ-380), not above adlc-toolkit's local high-water (REQ-263). Rationale: cross-project ID uniqueness so a single REQ id resolves to one work item across repos. (BR-8)
- [ ] The intentional REQ-264-through-REQ-379 gap is documented as the price of fast-forwarding to the global counter. Existing toolkit specs (REQ-258, REQ-262, REQ-263) keep their numbers.
- [ ] Cross-references: name atelier-fashion's `CLAUDE.md` "Cross-Project Considerations" as the paired doc on the consumer side.
- [ ] No other content changes; existing sections preserved verbatim.

## Technical Notes

- Pure additive — append a new H2 section near the bottom. Keeps existing scope/intro/install-model copy untouched.
- The atelier-fashion side of this policy was shipped in REQ-379 (PR #774, merged 2026-05-04).
