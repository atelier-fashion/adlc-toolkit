---
id: TASK-002
title: "Extend bug-template.md with tag frontmatter fields"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: []
---

## Description

Add the five new tag fields to the canonical bug template so every bug report created via `/bugfix` after this change carries the unified retrieval schema, matching the requirement template.

## Files to Create/Modify

- `templates/bug-template.md` — add `component`, `domain`, `stack`, `concerns`, `tags` to the frontmatter block with inline comments.

## Acceptance Criteria

- [ ] The frontmatter block in `templates/bug-template.md` contains all five new fields: `component`, `domain`, `stack`, `concerns`, `tags`.
- [ ] Each field has an inline comment (YAML `#` syntax) explaining purpose + example, identical in shape to the requirement-template fields.
- [ ] Field defaults match the requirement template convention: `component: ""`, `domain: ""`, `stack: []`, `concerns: []`, `tags: []`.
- [ ] Existing bug-template fields (`id`, `title`, `status`, `severity`, `created`, `updated`) are preserved unchanged.
- [ ] Template parses as valid YAML frontmatter.
- [ ] Satisfies REQ-258 AC-8 for the bug template.

## Technical Notes

Target frontmatter shape — mirrors requirement template exactly on tag fields:

```yaml
---
id: BUG-xxx
title: "Bug Title"
status: open
severity: critical | high | medium | low
created: YYYY-MM-DD
updated: YYYY-MM-DD
component: ""       # narrow area, e.g., "API/auth"
domain: ""          # broad area, e.g., "auth"
stack: []           # tech layers touched, e.g., ["express", "firestore"]
concerns: []        # cross-cutting dimensions, e.g., ["security", "perf"]
tags: []            # free-form keywords, e.g., ["token-reuse", "rate-limit"]
---
```

**Important**: per REQ-258 BR-6, only bugs with `status: resolved` are retrievable. The tag fields apply regardless of status, but retrieval filters them out until resolved. This is a retrieval concern, not a template concern — the template does not enforce or depend on status.

**Consistency**: the inline comments should use the same format and wording as TASK-001's requirement template, so the three templates (after TASK-003) read as a coherent schema. If TASK-001 uses "narrow area, e.g., ..." then TASK-002 uses the same phrasing.
