---
req: REQ-258
created: 2026-04-19
updated: 2026-04-19
status: approved
---

# Architecture — Unified Tag-Based Retrieval for /spec (Pilot)

## Approach

The feature is **pure markdown choreography**. No application code, no services, no state beyond the artifacts themselves. The implementation layers are:

1. **Schema layer**: extend frontmatter on three templates (requirement, bug, lesson) with tag dimensions (`component`, `domain`, `stack`, `concerns`, `tags`). Additive — existing documents without these fields still parse.
2. **Skill-instruction layer**: upgrade `/spec`'s SKILL.md body with new steps (query derivation, unified retriever, citation + self-tagging + Retrieved Context section requirements). The "scorer" is rendered as natural-language instructions the agent executes at invocation time — no bash helper, no Python function.
3. **Scaffold layer**: extend `/init` to create `.adlc/context/taxonomy.md` in consumer projects on initialization. A canonical taxonomy template provides the stub content.

## Key Design Decisions

### D-1: Agent-executed scoring (no new runtime)

**Decision**: The weighted-score retrieval runs as instructions in spec/SKILL.md that the agent follows literally at invocation time. No bash script, no Python module, no external service.

**Rationale**:
- Honors BR-13 (no new bash dependencies, no embedding infrastructure, no vector store).
- Matches the existing skill idiom — every other ADLC skill is pure markdown + minimal bash for deterministic ops.
- Scoring is simple enough to fit in agent instructions: "for each candidate doc, read its frontmatter; compute weighted sum per the rules below; filter zero-score; sort desc; take top 15."
- Minor scoring variance run-to-run is acceptable per the spec's Assumption section — citations persist, scoring logs don't.

**Alternative considered**: Bash script with `jq` to parse frontmatter and compute scores deterministically. Rejected because it would introduce a new runtime dependency, duplicate logic the agent is already good at, and produce output the agent would re-interpret anyway.

### D-2: Retrieval via Grep + Read, no separate index

**Decision**: At retrieval time, use the Grep tool to enumerate candidate files matching status filters, then Read each candidate's frontmatter (first ~15 lines) to compute scores. After ranking, Read full bodies of the top 15 only.

**Rationale**:
- No index file to maintain or invalidate. Corpus is whatever exists in `.adlc/knowledge/lessons/`, `.adlc/specs/*/requirement.md`, `.adlc/bugs/*.md` at invocation time.
- Grep is cheap; reading frontmatter of ~100 files is tractable. Reading full bodies of only the top 15 keeps token budget bounded.
- Graceful for cold-start: empty directory yields zero candidates, skill proceeds with the cold-start note per BR-9.

**Performance note**: At ~300 total docs (atelier-fashion's projected corpus after backfill), the frontmatter peek is ~300 × ~15 lines = ~4500 lines of metadata, well within context budget. Beyond ~1000 docs this approach needs revisiting, but we're nowhere near that ceiling.

### D-3: Template changes are additive, no migration

**Decision**: New tag fields are added to templates with optional semantics. Existing documents without these fields continue to parse and work — they simply score according to their present metadata (lessons get the +1 foundational floor; bugs/specs filter to 0 and are excluded from retrieval until tagged).

**Rationale**:
- Lazy migration policy (Assumption #4 in spec).
- Zero-risk rollout: no document needs to be rewritten for the feature to ship.
- The separate `/retag` follow-up REQ handles retroactive backfill when the user is ready.

### D-4: Taxonomy doc is project-local, not toolkit-canonical

**Decision**: `.adlc/context/taxonomy.md` is scaffolded by `/init` in each consumer project. Each project defines its own legal values for `component`, `domain`, `stack`, `concerns`. The toolkit provides a canonical *template* (`templates/taxonomy-template.md`) with example dimensions but NOT prescribed values.

**Rationale**:
- `component: API/auth` makes sense for atelier-fashion; it's meaningless for a different project.
- Avoids the toolkit enforcing a vocabulary that doesn't match every codebase.
- Matches the existing pattern where templates live at toolkit root, copies live in consumer projects.

### D-5: Query confirmation default per invocation mode

**Decision**: When `/spec` is invoked manually, the agent proposes query tags, surfaces them, and waits for user confirmation before retrieval fires. When `/spec` is invoked from `/proceed` (i.e., inside a pipeline), the agent proceeds autonomously using its own proposed tags and relies on later review phases to catch misfires.

**Rationale**:
- Honors OQ-4 resolution.
- Interactive mode: one confirmation round adds seconds, prevents wrong-area retrieval which would waste real authoring cycles.
- Pipeline mode: /proceed's downstream validation and review phases catch anomalies; blocking for user input breaks automation.

### D-6: Exploration agents skipped for this REQ

**Decision**: The three exploration agents normally dispatched by `/architect` (feature-tracer, architecture-mapper, integration-explorer) are NOT run for REQ-258.

**Rationale**:
- The REQ's BR-1–14 and AC-1–12 name every affected file explicitly: three template files, one skill file, one new taxonomy template, one update to `/init`. Six files total, exhaustively enumerated.
- The adlc-toolkit repo contains no application code, no test suite, no integration surfaces to discover. The entire feature surface is markdown.
- Running three parallel agents to re-enumerate the file list already in the spec would be ceremony without discovery. ETHOS #5 permits explicit skip when a step "truly doesn't apply."
- If `/architect`'s quality checklist requires evidence of an exploration pass, this document's D-6 captures the reasoning.

**Risk**: An unnamed affected file could be missed. Mitigation: Phase 5 reviewers (architecture-reviewer, correctness-reviewer) will catch it during verify. If a gap emerges, a follow-up task is added.

## Data Model Changes

None in the application sense. The "data model" is the markdown frontmatter schema on three template files. See REQ-258 System Model section for the five-field schema.

## API Changes

None. No HTTP surface.

## Service Layer Changes

None. No backend services.

## Affected Files

| File | Change Type | Task |
|---|---|---|
| `templates/requirement-template.md` | Extend frontmatter | TASK-001 |
| `templates/bug-template.md` | Extend frontmatter | TASK-002 |
| `templates/lesson-template.md` | Extend frontmatter | TASK-003 |
| `spec/SKILL.md` | Add Step 1.5 (Query Derivation); add Step 1.6 (Unified Retrieval, replacing the old 3-tier grep); extend Step 3 (deployable field, citations, self-tagging, Retrieved Context section) | TASK-004 |
| `init/SKILL.md` | Add taxonomy.md scaffolding step | TASK-005 |
| `templates/taxonomy-template.md` | New file (canonical stub) | TASK-005 |
| (verification pass — no file change) | Dogfood `/spec` on synthetic REQ | TASK-006 |

## Testing Approach

The adlc-toolkit has no traditional test suite. Verification is dogfooding:

1. Invoke the upgraded `/spec` on a synthetic feature request (e.g., `/spec "add SSO for admin users"` in a scratch directory).
2. Verify against the ACs:
   - Query tags proposed (AC-1 mode)
   - Retrieved context listed with scores (AC-1, AC-3)
   - Cold-start note appears if no corpus (AC-5)
   - Generated REQ frontmatter includes tags (AC-2)
   - Inline citations appear when a retrieved doc informed a rule (AC-4)
3. Score-ranking behavior is verified against the fixture described in AC-6 and AC-7 (can be constructed as two synthetic bug files).

Test-auditor agent will likely flag "no test coverage" during Phase 5 verify. Response: toolkit has no unit test framework; verification is dogfood-based, documented here, and the explicit AC-7 fixture test is the closest thing to a unit test. This is consistent with how every other toolkit REQ has historically been verified (by PR diff review + manual invocation).

## Rollout

Merge lands in main. Symlink install means the upgraded `/spec` is live immediately for every consumer project. No build, no publish, no version bump.

Consumer projects that have already run `/init`:
- Existing `.adlc/templates/requirement-template.md` and `.adlc/templates/bug-template.md` copies **will not** auto-update. Users must re-run `/init` or manually update their local copies. `/template-drift` will flag the divergence.
- Missing `.adlc/context/taxonomy.md` is handled by running `/init` again (idempotent — skips existing files, adds new ones).

## Deferred Work (for downstream REQs)

- Integration into `/architect`, `/bugfix`, `/review` — each a separate REQ.
- Retroactive tagging via `/retag` — separate REQ; user has queued ~290 files of atelier-fashion corpus.
- Assumption / decision corpora extension — separate REQ when deemed valuable.
- Telemetry ("which retrieved docs were cited") — v2.
- Embedding-based retrieval — only if tag ceiling becomes limiting.

## Open Questions During Implementation

None at architecture time. All spec-level open questions were resolved during spec authoring.

## Dependencies on Prior Work

None. REQ-258 is the toolkit's first tracked REQ.
