---
id: TASK-004
title: "Add the read-only incident-attribution line to /status"
status: draft
parent: REQ-593
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-001]
---

## Description

BR-9: `/status` gains a read-only section reporting bugs-with-attribution and the REQs they
point at, derived per BR-4 by scanning `.adlc/bugs/`. No new skill directory.

## Files to Create/Modify

- `status/SKILL.md` — modify; new `#### Incident Attribution` subsection after `#### Open Bugs`,
  and a matching Step 1 scan note

## Acceptance Criteria

- [ ] Section is derived by scanning `.adlc/bugs/*.md` frontmatter at read time (BR-4)
- [ ] Running `/status` modifies no file — in particular no `.adlc/specs/**` file (AC-11, AC-14)
- [ ] Bugs with no attribution are simply absent from the section; an empty section degrades
      to a "no attributed incidents" line rather than an error
- [ ] Partial sourced with two-level fallback, called in the same fenced block
- [ ] `python3 tools/lint-skills/check.py` exits 0

## Technical Notes

`/status` is a read-only dashboard — keep it that way. The reverse index is derived, never
stored (ADR-4).
