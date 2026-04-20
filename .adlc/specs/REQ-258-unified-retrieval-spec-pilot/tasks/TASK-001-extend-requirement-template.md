---
id: TASK-001
title: "Extend requirement-template.md with tag frontmatter fields"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: []
---

## Description

Add the five new tag fields to the canonical requirement template so every REQ created via `/spec` after this change inherits the unified retrieval schema.

## Files to Create/Modify

- `templates/requirement-template.md` — add `component`, `domain`, `stack`, `concerns`, `tags` to the frontmatter block with inline comments explaining each dimension's purpose.

## Acceptance Criteria

- [ ] The frontmatter block in `templates/requirement-template.md` contains all five new fields: `component`, `domain`, `stack`, `concerns`, `tags`.
- [ ] Each field has an inline comment (using `#` YAML comment syntax) documenting its purpose and citing a representative example, e.g. `component: ""  # narrow area, e.g., "API/auth" or "adlc/spec"`.
- [ ] `stack`, `concerns`, `tags` default to empty arrays `[]`, not omitted.
- [ ] `component` and `domain` default to empty strings `""`, not omitted.
- [ ] Existing fields (`id`, `title`, `status`, `deployable`, `created`, `updated`) are preserved unchanged.
- [ ] The resulting template parses as valid YAML frontmatter (can be verified by attempting to parse with Python's `yaml.safe_load` or equivalent).
- [ ] Satisfies REQ-258 AC-8 for the requirement template.

## Technical Notes

Target frontmatter shape:

```yaml
---
id: REQ-xxx
title: "Feature Title"
status: draft
deployable: true
created: YYYY-MM-DD
updated: YYYY-MM-DD
component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI", "adlc/spec"
domain: ""          # broad area, e.g., "auth", "payments", "ui"
stack: []           # tech layers touched, e.g., ["express", "firestore"]
concerns: []        # cross-cutting dimensions, e.g., ["security", "perf", "a11y"]
tags: []            # free-form keywords, e.g., ["password-reset", "tokens"]
---
```

**Inline comment format**: YAML supports `#` line-end comments. Keep comments concise (one line per field), example-first.

**Do NOT** make the new fields required (no validation enforcement yet). Empty strings and empty arrays are valid — retrieval will naturally score them lower per the spec's scoring rules. Validation enforcement is out of scope (see REQ-258 Out of Scope section).

**Dogfooding already present**: `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/requirement.md` already uses this shape (with populated values) as a reference. Do not confuse dogfooded values for template defaults.
