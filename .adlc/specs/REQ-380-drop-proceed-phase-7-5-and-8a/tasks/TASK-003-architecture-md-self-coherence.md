---
id: TASK-003
title: "Update .adlc/context/architecture.md pipeline diagram"
req: REQ-380
status: pending
created: 2026-05-04
updated: 2026-05-04
dependencies: []
repo: adlc-toolkit
---

## Files to Modify
- `.adlc/context/architecture.md`

## Acceptance Criteria

- [ ] The "ADLC pipeline shape (consumer-project view)" diagram (lines ~58–78) no longer contains a `/canary (optional, if deployable)` step. The flow goes: Create PR → PR cleanup + CI → `/wrapup`. (Self-coherence with BR-1.)
- [ ] No other content changes.

## Technical Notes

- One-line removal in the ASCII flow block. Operators who need a manual canary still invoke `/canary` directly (the skill is preserved); it's just no longer part of the auto pipeline.
