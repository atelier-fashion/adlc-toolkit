---
id: TASK-003
title: "Extend lesson-template.md with stack, concerns, updated fields"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: []
---

## Description

Align the lesson template with the unified schema. The lesson template already has `component`, `domain`, and `tags`; this task adds the three missing fields (`stack`, `concerns`, `updated`) so all three retrievable document types share the same frontmatter vocabulary.

## Files to Create/Modify

- `templates/lesson-template.md` — add `stack`, `concerns`, `updated` to the frontmatter block. Preserve existing fields (`component`, `domain`, `tags`, `req`, `created`, `id`, `title`) unchanged.

## Acceptance Criteria

- [ ] The frontmatter block in `templates/lesson-template.md` contains the three new fields: `stack`, `concerns`, `updated`.
- [ ] Existing fields are preserved: `id`, `title`, `component`, `domain`, `tags`, `req`, `created`.
- [ ] `stack` and `concerns` default to empty arrays `[]` with inline comments matching TASK-001 and TASK-002.
- [ ] `updated` is a required date field, placeholder `YYYY-MM-DD`, positioned next to `created` in the frontmatter block.
- [ ] The filename-naming comment at the top of the template (wrapped in `<!-- ... -->`) is preserved.
- [ ] Template parses as valid YAML frontmatter.
- [ ] Satisfies REQ-258 AC-11.

## Technical Notes

Current lesson template (abbreviated) has:

```yaml
---
id: LESSON-xxx
title: "Lesson Title"
domain: "area this applies to (e.g., testing, iOS, API, deployment, architecture)"
component: "specific component (e.g., iOS/memory, API/auth, API/caching, iOS/SwiftUI, testing/mocks)"
tags: []
req: REQ-xxx
created: YYYY-MM-DD
---
```

Target after this task:

```yaml
---
id: LESSON-xxx
title: "Lesson Title"
domain: ""          # broad area, e.g., "auth", "testing", "iOS"
component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI"
stack: []           # tech layers touched, e.g., ["swift", "firestore"]
concerns: []        # cross-cutting dimensions, e.g., ["security", "perf"]
tags: []            # free-form keywords, e.g., ["timer-cleanup", "snapshot-testing"]
req: REQ-xxx
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

**Backwards compatibility**: existing lessons without `stack`, `concerns`, or `updated` must still be valid. Per BR-1 they get the +1 foundational floor when retrieved (if none of the five tag fields are populated). Per BR-8 the tiebreak fallback uses `created` when `updated` is absent.

**Do NOT modify** the existing in-body sections (`## What Happened`, `## Lesson`, `## Why It Matters`, `## Applies When`). Only the frontmatter changes.

**The descriptive in-quotes defaults on `domain` and `component`** (e.g., `domain: "area this applies to..."`) should be replaced with empty strings `""` + inline comments, matching the convention established in TASK-001. This is a format change only — the guidance moves from value to comment, which is more parseable and matches the other templates.
