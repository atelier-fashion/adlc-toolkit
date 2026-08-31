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
concerns: []        # cross-cutting dimensions, e.g., ["security", "performance", "a11y"]
tags: []            # free-form keywords, e.g., ["password-reset", "tokens"]
---

## Description

What the feature does and why.

## System Model

_Define the structured data model for this feature. Remove sections that don't apply._

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| [EntityName] | [field] | [string/number/boolean/timestamp] | [required, unique, max length, etc.] |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| [event_name] | [What causes it] | [Key data included] |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| [action_name] | [authenticated, owner, admin, etc.] |

## Business Rules

_Explicit, testable constraints governing this feature's behavior._

- [ ] BR-1: [Rule statement — e.g., "Only item owner can delete wardrobe items"]
- [ ] BR-2: [Rule statement]

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## External Dependencies

- None

## Assumptions

- None

## Open Questions

- [ ] Open question 1

## Out of Scope

- Items explicitly excluded

<!--
OPTIONAL — intake only (REQ-594). When /spec Step 1.4 drafts a REQ from an
unstructured source (a transcript, meeting notes, a ticket dump), it appends a
`## Provenance` section here recording what the spec was derived from and what the
source did not answer:

## Provenance

- Source: `<basename>` (kind: transcript | notes | ticket | prose)
- Intake date: YYYY-MM-DD

| Section | Severity | Gap | Disposition |
|---|---|---|---|
| System Model | blocking | Who is allowed to archive a project? | answered |
| Business Rules | assumption | Does archiving cascade to child items? | assumed |

OMIT this section entirely for a spec written without intake — do not emit an empty
heading or a placeholder. The section is additive, which is why existing specs stay
valid without migration.
-->

<!--
OPTIONAL — appended by /spec Step 1.6. Lists every retrieved prior-art document as
`ID (corpus, score): title`. Omitted only when the skill has not run retrieval.

## Retrieved Context
-->

