---
id: TASK-002
title: "Add optional introduced_by and attribution fields to the bug template"
status: draft
parent: REQ-593
created: 2026-08-31
updated: 2026-08-31
dependencies: []
---

## Description

BR-1: purely additive frontmatter on `templates/bug-template.md`. No existing field is
renamed or reordered; a bug carrying neither new field stays valid.

## Files to Create/Modify

- `templates/bug-template.md` — modify; append two optional frontmatter fields

## Acceptance Criteria

- [ ] `introduced_by: []` and `attribution: none` appear in the frontmatter with inline
      comments documenting the enum (`derived | manual | none`) and the id format
- [ ] No existing field is renamed, reordered, or removed
- [ ] All 15 existing `.adlc/bugs/*.md` files still parse with neither field present (AC-15)

## Technical Notes

The toolkit deliberately has no vendored `.adlc/templates/` copy — the root `templates/`
directory is authoritative (project-overview.md). Do not create one.

Template changes propagate to consumer projects via `/template-drift` detection, not
auto-update. `partials` and `templates` are already registered sync surfaces, so no
`init/SKILL.md` or `template-drift/SKILL.md` sync-surface edit is needed for this REQ.
