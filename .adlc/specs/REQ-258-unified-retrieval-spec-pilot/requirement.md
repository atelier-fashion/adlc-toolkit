---
id: REQ-258
title: "Unified Tag-Based Retrieval for /spec (Pilot)"
status: complete
deployable: true
created: 2026-04-19
updated: 2026-04-19
component: adlc/spec
domain: adlc
stack: [markdown, claude-skills, bash]
concerns: [retrieval, context-management, knowledge-compounding, developer-experience]
tags: [rag, retrieval, tagging, spec-skill, atelier-pattern, frontmatter-schema]
---

## Description

Upgrade the `/spec` skill's context-loading step from the current 3-tier binary lesson grep to a unified weighted-score retriever that ranks relevance across three corpora simultaneously: lessons, prior specs (approved / in-progress / deployed), and resolved bugs. Adopt the scoring shape used by Atelier Fashion's style RAG (`knowledgeService.js` in the atelier-fashion repo): weighted-sum over multi-dimensional frontmatter tags with a foundational-doc baseline.

**Why this change exists.** Today the `/spec` skill retrieves lessons via a 3-tier matching rule (component exact > domain + prefix > tag). Specs and bugs are not retrievable by semantic area at all — only by ID. This leaves three gaps:

1. A new REQ drafted in an area with historical bugs does not inherit those bugs as context. Agents regenerate previously-fixed edge cases.
2. Prior REQs that already contracted behavior in the same area are invisible during new-spec authoring. Contracts silently diverge.
3. The 3-tier rule has cliff effects — a bug matching `component + tags` ranks equal to one matching only `component`, even though the first is materially more relevant.

**What success looks like.** After this REQ ships, `/spec` invocations draw on the most-relevant prior context across all three corpora, surface what was retrieved (transparency), cite sources inline where they informed a rule, and persist tags into the new REQ so it becomes a first-class member of the retrieval corpus for future invocations. The spec library compounds: every new REQ inherits the area's full history, every new bug's learnings propagate without manual reference chains.

**Scope discipline.** This REQ pilots the pattern inside `/spec` only. Rolling it out to `/architect`, `/bugfix`, and `/review` happens in follow-up REQs once the primitive is validated.

## System Model

_The retrieval feature does not introduce user-facing entities or events. The "data model" is the frontmatter schema and the retrieval query/response shape. Permissions sub-section omitted — no user roles involved._

### Entities

**Frontmatter tag schema** (applied to requirement, bug, and lesson templates):

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Document frontmatter | `component` | string (single) | optional; narrow area, e.g. `API/auth` or `adlc/spec` |
| Document frontmatter | `domain` | string (single) | optional; broad area, e.g. `auth`, `payments`, `adlc` |
| Document frontmatter | `stack` | string[] | optional; tech layers touched, e.g. `["express", "firestore"]` |
| Document frontmatter | `concerns` | string[] | optional; cross-cutting dimensions, e.g. `["security", "perf"]` |
| Document frontmatter | `tags` | string[] | optional; free-form keywords, e.g. `["password-reset", "email"]` |

**Retrieval query** (agent-derived from the feature request + user confirmation):

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Query | `component` | string | proposed by agent, confirmed by user |
| Query | `domain` | string | proposed by agent, confirmed by user |
| Query | `stack` | string[] | inferred from project context |
| Query | `concerns` | string[] | inferred from feature description |
| Query | `tags` | string[] | inferred keywords from feature description |

**Retrieval result** (internal structure, surfaced to user as summary):

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| RetrievedDoc | `id` | string | document ID (LESSON-xxx / REQ-xxx / BUG-xxx) |
| RetrievedDoc | `corpus` | enum | `lesson` \| `spec` \| `bug` |
| RetrievedDoc | `score` | number | from weighted scorer |
| RetrievedDoc | `path` | string | absolute file path |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `query_proposed` | `/spec` Step 1.5 — agent derives tags from feature request | query object shown to user |
| `retrieval_run` | After user confirms query | scored pool + top-15 selection |
| `retrieval_summary_shown` | Before authoring begins | Retrieved docs with scores surfaced to user |
| `source_cited` | Agent references a retrieved doc while drafting a rule | inline citation `(informed by BUG-012)` written into spec |
| `req_self_tagged` | Spec persistence | new REQ's frontmatter populated with query tags |

## Business Rules

_Explicit testable constraints. Each BR must be checkable against the implementation or the output artifact._

- [ ] BR-1: The scoring function computes the following weighted sum per candidate doc:
  - `+3` if `doc.component == query.component`
  - `+2` if `doc.domain == query.domain`
  - `+2` per element in `doc.concerns ∩ query.concerns`
  - `+1` per element in `doc.stack ∩ query.stack`
  - `+1` per element in `doc.tags ∩ query.tags`
  - `+1` baseline **only for lessons** with none of the five tag fields populated (foundational floor). Specs and bugs with zero tag overlap score `0` and are filtered out — untagged bugs/specs are more likely stale than foundational, whereas untagged lessons plausibly represent cross-cutting wisdom.
- [ ] BR-2: Docs with final score of `0` are filtered out of the result pool.
- [ ] BR-3: The retriever takes the **top 15 globally** across all corpora. Per-corpus quotas are explicitly forbidden — no minimum-lesson floor, no maximum-bug cap. Pure relevance ranking (option A from design discussion).
- [ ] BR-4: Lessons are retrievable regardless of metadata. No status filter.
- [ ] BR-5: Specs are retrievable only if `status ∈ {approved, in-progress, deployed}`. Drafts are excluded.
- [ ] BR-6: Bugs are retrievable only if `status == resolved`. Open and in-progress bugs are excluded.
- [ ] BR-7: The generated REQ persists the query tags (`component`, `domain`, `stack`, `concerns`, `tags`) into its own frontmatter on creation. This makes the REQ itself retrievable for future `/spec` invocations (self-tagging mandate).
- [ ] BR-8: Tiebreak policy when two docs score equal: newer `updated` date wins; if still tied, corpus priority `lesson > bug > spec`. Fallback chain when `updated` is missing or malformed on legacy docs: `updated` → `created` → file mtime → stable alphabetical by ID. Missing dates do not cause retrieval failures.
- [ ] BR-9: On cold-start (no docs score above zero, either from empty corpus or from legacy untagged corpus), the skill proceeds without retrieved context and writes an explicit note into the spec's `## Retrieved Context` section: `"No prior context retrieved — no tagged documents matched this area."`
- [ ] BR-10: The retrieval summary surfaced to the user before authoring lists every retrieved doc with its ID, corpus, and score. Default verbosity: always shown (no `--verbose` flag required).
- [ ] BR-11: The generated spec includes a `## Retrieved Context` section at the end listing every retrieved source (ID + corpus + score), regardless of whether each was cited inline. This is the auditable trail.
- [ ] BR-12: When a retrieved doc directly informs a Business Rule, Assumption, or Acceptance Criterion, the agent adds an inline citation in the form `(informed by BUG-012)` or `(informed by REQ-019, LESSON-034)`. Citations are required when the retrieved doc is load-bearing for the rule; optional when the retrieved doc was background reading only.
- [ ] BR-13: Scoring runs as agent-executed logic during skill invocation. No new bash dependencies, no embedding infrastructure, no vector store.
- [ ] BR-14: Legacy documents (pre-schema) without tag frontmatter are not migrated eagerly. They either receive the `+1` foundational floor (if they also have no tags at all) or are skipped with score `0`. Lazy migration: authors backfill tags on next touch.

## Acceptance Criteria

- [ ] AC-1: A `/spec` invocation in an area with prior lessons, specs, or bugs retrieves the top 15 most-relevant docs, displays them with scores before authoring, and reads their bodies into agent context.
- [ ] AC-2: The generated REQ's frontmatter includes non-empty values for `component`, `domain`, and at least one of `stack` / `concerns` / `tags` (when the feature area supports them). Verifiable via grep.
- [ ] AC-3: The generated REQ contains a `## Retrieved Context` section enumerating every retrieved source.
- [ ] AC-4: When a retrieved doc was load-bearing for a Business Rule, an inline citation `(informed by <ID>)` appears on that BR line.
- [ ] AC-5: On a fresh project with empty `.adlc/knowledge/lessons/`, `.adlc/specs/`, and `.adlc/bugs/`, `/spec` produces a REQ with `## Retrieved Context` containing `"No prior context retrieved — no tagged documents matched this area."`
- [ ] AC-6: Given two bug files with identical `component`, one with matching `concerns` and `tags` and one without, the retrieval summary shows the matching one ranked strictly higher (score at least 3 greater).
- [ ] AC-7: Given a corpus where 12 bugs and 6 lessons all score above zero, the top-15 result contains bugs and lessons proportional to their scores — no per-corpus caps enforce a minimum lesson count. Verifiable by constructing a test fixture where all 15 top-scoring docs happen to be bugs and confirming the result is 15 bugs, 0 lessons.
- [ ] AC-8: The `templates/requirement-template.md` and `templates/bug-template.md` files expose the new tag fields with inline comments explaining each dimension's purpose.
- [ ] AC-9: A new file `.adlc/context/taxonomy.md` exists in consumer projects after `/init` runs, documenting legal values per dimension with examples. The taxonomy is project-local (different codebases have different component hierarchies).
- [ ] AC-10: The `/spec` skill's Step 1.3 is replaced by a new sub-step implementing the unified retriever as specified. The old 3-tier grep logic is removed — not left as a fallback.
- [ ] AC-11: The lesson template at [templates/lesson-template.md](templates/lesson-template.md) is extended with the missing fields: `stack` (array), `concerns` (array), and `updated` (date, required for tiebreak). Existing fields (`component`, `domain`, `tags`) are preserved. The three templates (requirement, bug, lesson) share the same tag schema.
- [ ] AC-12: Assumption and task templates ([templates/assumption-template.md](templates/assumption-template.md), [templates/task-template.md](templates/task-template.md)) are NOT modified by this REQ. They remain untouched.

## External Dependencies

- None. The feature is markdown frontmatter + agent-executed scoring. No new libraries, services, or APIs.

## Assumptions

- The Atelier style RAG scoring shape adapts cleanly to ADLC: weighted sum, zero-score filter, foundational floor, top-N cap. Differences (3 corpora instead of 1; markdown instead of Firestore; agent-executed instead of service-executed) do not change the scoring model itself.
- Opus 4.7 1M context comfortably handles ~50KB of retrieved context per invocation. If future usage pushes this above 100KB, the top-15 cap may need revision, but current target is well within budget.
- Agent-executed scoring is reliable enough that deterministic output is not required. For the pilot, minor scoring variance across runs is acceptable — citations in the final REQ are what persist, not the score log.
- Legacy REQs and bugs without tag frontmatter are rare enough that lazy migration (tag on next touch) is acceptable. If a specific project has hundreds of legacy artifacts, a one-shot backfill script can be added later as a follow-up REQ.
- The toolkit repo itself does not need to dogfood the full `/init` scaffold for this REQ to ship — this spec is persisted to `.adlc/specs/REQ-258-*/requirement.md` as a minimal artifact.

## Open Questions

_All open questions from the initial draft have been resolved. Preserved here with resolutions for traceability._

- [x] OQ-1 — **RESOLVED**: Lesson template exists at [templates/lesson-template.md](templates/lesson-template.md) with `component`, `domain`, and `tags` already defined. Missing fields to add per AC-11: `stack`, `concerns`, `updated`. Alignment is additive — will not break existing `LESSON-xxx.md` files.
- [x] OQ-2 — **RESOLVED**: The `+1` foundational floor applies to lessons only (see updated BR-1). Untagged specs and bugs score 0 and are filtered out. Rationale: untagged lessons plausibly represent cross-cutting wisdom authored deliberately without area tags; untagged bugs and specs are more likely just stale or incompletely authored.
- [x] OQ-3 — **RESOLVED**: Tiebreak uses `updated` date as primary key (see updated BR-8). Fallback chain for legacy docs: `updated` → `created` → file mtime → stable alphabetical by ID. Missing dates never cause retrieval failures.
- [x] OQ-4 — **RESOLVED**: Query-tag confirmation default is synchronous-interactive for manual `/spec` invocations, autonomous with inherited tags when invoked from `/proceed`. The agent proposes tags, surfaces them, and for interactive mode waits for user confirmation or edit before proceeding to retrieval.
- [x] OQ-5 — **RESOLVED**: Concurrent `/spec` invocations via `/sprint` are safe because retrieval is read-only over the corpus. No locking or coordination required for retrieval itself. The existing atomic counter lock on `~/.claude/.global-next-req` remains the only concurrency mechanism needed.

## Out of Scope

- `/architect` integration. Follow-up REQ will re-retrieve with task-granular queries and inherit already-loaded context when invoked via `/proceed`.
- `/bugfix` Phase 2 integration. Follow-up REQ will retrieve similar resolved bugs during root-cause analysis.
- `/review` integration. Follow-up REQ will upgrade the existing Step 1.7 lesson retrieval to the unified retriever across all three corpora, so reviewers catch regressions of previously-fixed bugs.
- **Retroactive tagging of legacy docs (`/retag` skill).** A follow-up REQ will add an agent-assisted retag skill supporting both on-demand (tag a specific doc) and bulk (walk the corpus) modes. The agent reads each doc's body, proposes tags, and either applies them (bulk, with spot-check review) or presents them to the user (on-demand, confirm-then-write). Out of scope here so the pilot stays focused on the retriever itself; lazy migration remains the default until the `/retag` REQ ships.
- Assumption and decision corpora (`.adlc/knowledge/{assumptions,decisions}/`). This REQ scopes retrieval to lessons, specs, and bugs. Atelier's broader knowledge taxonomy (`assumptions`, `decisions`) is a clean future extension — a follow-up REQ can add them to the retriever with minimal incremental logic.
- Modifications to [templates/assumption-template.md](templates/assumption-template.md) and [templates/task-template.md](templates/task-template.md). Only requirement, bug, and lesson templates are touched by this REQ.
- Telemetry loop. "Which retrieved docs were actually cited?" feedback for retriever improvement is deferred to a v2 REQ.
- Embedding-based semantic retrieval. This REQ is tag-based only. Embeddings may be added later if the tag-based ceiling becomes limiting at scale.
- Automated enforcement of taxonomy vocabulary (e.g., "reject REQs with `component: some-unknown-area`"). The taxonomy doc is advisory in v1; validation tooling can follow later.
- UI or reporting changes for retrieval logs. The skill output is the UI.

## Retrieved Context

No prior context retrieved — no tagged documents matched this area. This REQ bootstraps the retrieval corpus for the toolkit's own development (first REQ tracked in the adlc-toolkit repo). Future REQs in `component: adlc/*` will retrieve REQ-258 automatically once the feature ships.
