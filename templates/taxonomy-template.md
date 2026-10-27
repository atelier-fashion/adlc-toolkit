# Taxonomy — Retrieval Tag Vocabulary

This project's legal values for retrieval tag dimensions. Currently used by `/spec` when retrieving relevant prior context via the unified tag-based retriever. Integration into `/architect`, `/bugfix`, and `/review` is planned in follow-up REQs.

**This file is project-local.** Different projects have different taxonomies. Extend it as new areas emerge. Values are advisory — the retrieval system does not currently enforce them, but consistent vocabulary improves retrieval quality.

**Note on `tags`:** the `tags` dimension is intentionally free-form and is NOT enumerated here. Authors add whatever keywords feel descriptive at the time of writing. See the `tags (free-form)` section at the bottom for guidance.

## component (narrow area)

Single string. Hierarchical if helpful (e.g., `API/auth` or `iOS/SwiftUI/WardrobeView`).

Values are project-local — extend this list as new components emerge.

Examples (customize for this project):
- `API/auth`
- `API/payments`
- `iOS/SwiftUI`
- `iOS/networking`
- `infra/terraform`
- `adlc/spec`

## domain (broad area)

Single string. Higher-level than `component`.

Values are project-local — extend this list as new domains emerge.

Examples:
- `auth`
- `payments`
- `ui`
- `data`
- `infra`
- `adlc`

## stack (tech layers)

Array. One entry per technology touched.

Values are project-local — extend this list as new technologies are adopted.

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

Values are project-local — extend this list as new concerns emerge.

Examples:
- `security`
- `performance`
- `reliability`
- `a11y`
- `observability`
- `developer-experience`
- `cost`

## kind (lesson scope)

Single string. Fixed vocabulary — `adlc_lesson_check` rejects any other value; not project-extensible.

Required on every lesson the capture steps write; absent on legacy lessons.

Values:
- `process` — how a skill, agent, partial or pipeline phase behaves
- `domain` — what an implementer must know about the codebase or stack

## confidence (lesson evidence strength)

Single string. Fixed vocabulary — `adlc_lesson_check` rejects any other value; not project-extensible.

Required on every lesson the capture steps write; absent on legacy lessons (absent is "not stated", never `low`).

Decided by whether `evidence` holds a *contrast* — a bug reproduced then fixed, a test failing then passing, a Phase-5 finding confirmed by its fix and re-verify, or two approaches/runs compared:
- `high` — a contrast was observed **and** the evidence names the mechanism (a specific line, command or finding)
- `medium` — a contrast was observed but the mechanism is inferred
- `low` — a single observation with no contrast

## enforcement (lesson structural guard)

Single string. Fixed vocabulary — `adlc_lesson_check` rejects any other value; not project-extensible.

Optional; absent means `none`. Either `none` (honor-system — nothing structural guards the lesson) or one of four patterns naming the guard:
- `lint:<check-id>` — a lint check catches a violation
- `test:<path>` — a test at that path fails on a violation
- `script:<path>` — a script at that path refuses a violation
- `hook:<name>` — a harness hook with that name blocks a violation

## tags (free-form)

Array of any keywords. Intentionally NOT enumerated — authors add whatever feels descriptive. Examples: `password-reset`, `rate-limiting`, `snapshot-testing`, `canary-deploy`.

The `tags` dimension is the lowest-weight signal in retrieval (+1 per match vs +2 for concerns/domain, +3 for component) but provides useful lexical signal.
