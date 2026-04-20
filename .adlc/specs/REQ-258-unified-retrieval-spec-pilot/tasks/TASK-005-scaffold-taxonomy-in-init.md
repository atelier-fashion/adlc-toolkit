---
id: TASK-005
title: "Scaffold .adlc/context/taxonomy.md in /init, add canonical taxonomy template"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: []
---

## Description

Create a canonical `templates/taxonomy-template.md` stub and update `init/SKILL.md` to copy it into consumer projects as `.adlc/context/taxonomy.md`. This gives consumer projects a starter taxonomy document with example dimension values that can be customized per-codebase.

## Files to Create/Modify

- `templates/taxonomy-template.md` — NEW file. Stub with example `component`, `domain`, `stack`, `concerns` values, tailored to be broadly illustrative rather than prescriptive.
- `init/SKILL.md` — add a step that copies `templates/taxonomy-template.md` to `.adlc/context/taxonomy.md` during initialization, idempotent (skip if already exists).

## Acceptance Criteria

- [x] `templates/taxonomy-template.md` exists at the toolkit root.
- [x] The taxonomy template contains four dimension sections: `component`, `domain`, `stack`, `concerns`. (`tags` is free-form by design — no enumeration needed in taxonomy.)
- [x] Each dimension has a short description, example values (as a bullet list or table), and explicit guidance that values are project-local and can be extended.
- [x] The template includes a top-of-file note that `tags` is intentionally free-form (not enumerated).
- [x] `init/SKILL.md` has an instruction step that copies the taxonomy template to `.adlc/context/taxonomy.md` in the consumer project.
- [x] The `/init` step is idempotent: if `.adlc/context/taxonomy.md` already exists in the consumer project, it is NOT overwritten.
- [x] Satisfies REQ-258 AC-9.

## Technical Notes

### Canonical taxonomy template content (draft)

```markdown
# Taxonomy — Retrieval Tag Vocabulary

This project's legal values for retrieval tag dimensions. Used by `/spec`, `/architect`, `/bugfix`, and `/review` when retrieving relevant prior context via the unified tag-based retriever.

**This file is project-local.** Different projects have different taxonomies. Extend it as new areas emerge. Values are advisory — the retrieval system does not currently enforce them, but consistent vocabulary improves retrieval quality.

## component (narrow area)

Single string. Hierarchical if helpful (e.g., `API/auth` or `iOS/SwiftUI/WardrobeView`).

Examples (customize for this project):
- `API/auth`
- `API/payments`
- `iOS/SwiftUI`
- `iOS/networking`
- `admin-api/users`
- `infra/terraform`
- `adlc/spec`

## domain (broad area)

Single string. Higher-level than `component`.

Examples:
- `auth`
- `payments`
- `ui`
- `data`
- `infra`
- `adlc`

## stack (tech layers)

Array. One entry per technology touched.

Examples:
- `express`
- `firestore`
- `swift`
- `swiftui`
- `react`
- `terraform`
- `bash`
- `markdown`

## concerns (cross-cutting dimensions)

Array. Identifies quality attributes or aspects the work touches.

Examples:
- `security`
- `performance`
- `reliability`
- `a11y`
- `observability`
- `developer-experience`
- `cost`

## tags (free-form)

Array of any keywords. Intentionally NOT enumerated — authors add whatever feels descriptive. Examples: `password-reset`, `rate-limiting`, `snapshot-testing`, `canary-deploy`.

The `tags` dimension is the lowest-weight signal in retrieval (+1 per match vs +2 for concerns/domain, +3 for component) but provides useful lexical signal.
```

### /init skill modification

The current `/init` skill (at `init/SKILL.md`) scaffolds `.adlc/context/project-overview.md`, `architecture.md`, `conventions.md`. Add a step immediately after these that copies `taxonomy-template.md` to `.adlc/context/taxonomy.md`.

Rough draft for the /init instruction step:

```markdown
### Step X: Scaffold Retrieval Taxonomy

1. Check if `.adlc/context/taxonomy.md` already exists in the consumer project. If it does, skip (idempotent) and note to the user that the existing file is preserved.
2. Otherwise, copy the canonical template: `cp <toolkit-root>/templates/taxonomy-template.md .adlc/context/taxonomy.md`.
3. Advise the user: "Open `.adlc/context/taxonomy.md` and customize the example values for this codebase. Authors of new REQs, bugs, and lessons will reference this file when choosing tag values."
```

**Important**: the copy source path in `/init` must resolve from the toolkit install location. If `/init` runs inside a consumer project, it needs to resolve `~/.claude/skills/templates/taxonomy-template.md` (symlinked to the toolkit root). Use the same path pattern `/init` already uses for `project-overview`, `architecture`, etc.

### Why this is not dependent on TASK-001/002/003

This task creates a new file + adds one step to `/init`. It does not touch any of the three main templates and has no schema dependency on the other template updates. It can run in Tier 0 alongside TASK-001/002/003.

### Out of scope for this task

- Validating the consumer project's existing taxonomy.md against the canonical template — that's for a future `/template-drift` enhancement.
- Enforcing taxonomy values during spec creation — explicitly deferred per REQ-258 Out of Scope.
