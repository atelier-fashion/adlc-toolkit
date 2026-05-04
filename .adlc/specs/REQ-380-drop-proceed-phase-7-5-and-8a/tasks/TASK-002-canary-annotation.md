---
id: TASK-002
title: "Annotate canary/SKILL.md to reflect manual-only invocation"
req: REQ-380
status: pending
created: 2026-05-04
updated: 2026-05-04
dependencies: []
repo: adlc-toolkit
---

## Files to Modify
- `canary/SKILL.md`

## Acceptance Criteria

- [ ] Line 63 (`**Operating worktree**` paragraph): the parenthetical "(usually `/proceed` Phase 7.5)" is removed. Sentence reads: "The caller can also pass the worktree path explicitly." (BR-7)
- [ ] No other `Phase 7.5` or `/proceed` Phase-7.5-as-caller references remain. Verify with `grep -n "Phase 7\.5" canary/SKILL.md` returning zero hits.
- [ ] Step 7 ("Update Pipeline State (if in /proceed context)") is **kept as-is** — it's general "if a pipeline-state.json exists" wording, not Phase-7.5-specific. A manual operator running `/canary` while a parallel `/proceed` is open for some unrelated REQ may still legitimately update phaseHistory.
- [ ] Frontmatter `description` field is unchanged — the skill remains usable as a standalone command.
- [ ] No other behavior changes to the skill.

## Technical Notes

- One-line surgical edit. Use `Edit` tool with the exact old/new strings.
