---
id: TASK-004
title: "Upgrade /spec skill with unified retriever, query derivation, citations, self-tagging"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: [TASK-001, TASK-002, TASK-003]
---

## Description

Rewrite `/spec`'s context-loading and authoring instructions to implement the unified tag-based retriever. This is the core implementation task — the templates (TASK-001/002/003) are the schema; this task is the behavior.

Four changes to `spec/SKILL.md`:

1. **NEW Step 0.5** — Query Derivation: agent proposes tags from feature description; interactive-confirm or inherit-from-/proceed.
2. **REPLACE Step 1.3** — unified retriever over lessons + specs + bugs, weighted scoring, global top-15.
3. **REPORT retrieval summary** — the agent surfaces every retrieved doc with its score before authoring begins.
4. **EXTEND Step 3** — spec authoring now requires inline citations, `## Retrieved Context` section, self-tagged frontmatter.

## Files to Create/Modify

- `spec/SKILL.md` — multi-section edit per the detailed spec below.

## Acceptance Criteria

- [ ] `/spec`'s Step 0.5 (new) instructs the agent to derive a query tag object `{component, domain, stack, concerns, tags}` from the feature request, surface it to the user, and wait for confirmation in interactive mode; in pipeline mode (invoked from `/proceed`), proceed autonomously with proposed tags.
- [ ] `/spec`'s Step 1.3 (replaced) implements the unified retriever per REQ-258 BR-1 through BR-11. Specifically: Grep candidates across `.adlc/knowledge/lessons/*.md`, `.adlc/specs/*/requirement.md` (filter status ∈ {approved, in-progress, deployed}), `.adlc/bugs/*.md` (filter status == resolved); Read frontmatter of each; compute weighted score; filter zero-score; sort desc; tiebreak by `updated` → `created` → mtime → stable alphabetical; take top 15 globally; Read full bodies.
- [ ] The retrieval summary output (before authoring) lists every retrieved doc with `id`, corpus, and score. Default always-shown (no `--verbose` gate).
- [ ] `/spec`'s Step 3 (extended) instructs the agent to:
  - Write the query tags into the new REQ's frontmatter (component, domain, stack, concerns, tags) — self-tagging.
  - Add inline citations `(informed by BUG-xxx)` or `(informed by REQ-xxx, LESSON-xxx)` on Business Rules / Assumptions / Acceptance Criteria that drew on a specific retrieved doc.
  - Append a `## Retrieved Context` section listing every retrieved source with ID, corpus, score, regardless of whether cited inline.
- [ ] Cold-start handling: when zero candidates score above zero, the skill writes the cold-start note (`"No prior context retrieved — first REQ in this area."`) in the Retrieved Context section and proceeds without retrieved bodies.
- [ ] The old 3-tier grep logic at Step 1.3 is removed (not left as fallback). Per REQ-258 AC-10.
- [ ] The skill still passes the preflight check for `.adlc/context/project-overview.md`.
- [ ] The modified skill's SKILL.md file is valid markdown and its frontmatter parses.

## Technical Notes

### Current state of spec/SKILL.md (reference — from toolkit HEAD)

The current `spec/SKILL.md` has four steps (Understand the Request, Determine Next REQ ID, Create the Requirement Spec, Present for Review) plus Prerequisites, Quality Checklist. Step 1 has sub-steps including the lesson grep at 1.3. Step 2 is the atomic REQ ID counter logic (must be preserved). Step 3 is the template-based spec authoring.

### Step 0.5 — Query Derivation (NEW, insert before current Step 1)

Draft language:

```markdown
### Step 0.5: Derive Query Tags for Retrieval

1. Read the feature request in `$ARGUMENTS`. Extract likely area signals:
   - Which narrow component does this touch? (e.g., `API/auth`, `iOS/SwiftUI`, `adlc/spec`)
   - Which broad domain? (e.g., `auth`, `payments`, `ui`)
   - Which tech stack layers? (e.g., `express`, `firestore`, `swiftui`)
   - Which cross-cutting concerns? (e.g., `security`, `perf`, `a11y`, `retrieval`)
   - Which free-form keywords? (e.g., `password-reset`, `pagination`, `caching`)
2. Construct a query object:
   ```
   query = {
     component: "<proposed>",
     domain: "<proposed>",
     stack: [<proposed>],
     concerns: [<proposed>],
     tags: [<proposed>]
   }
   ```
3. **Interactive mode** (manual `/spec` invocation): Surface the proposed query to the user and ask:
   "Proposed retrieval query for this feature:
     component: ...
     domain: ...
     stack: [...]
     concerns: [...]
     tags: [...]
   Confirm or edit any field before retrieval fires."
   Wait for confirmation or edits.
4. **Pipeline mode** (invoked from `/proceed`): Do NOT block for user input. Use the proposed tags directly. If `/proceed` passed inherited tags in the invocation context, use those instead.
5. Retain the confirmed `query` object — it is used by Step 1.3 (retrieval) and Step 3 (self-tagging the new REQ).
```

### Step 1.3 — Unified Retriever (REPLACES current 3-tier lesson grep)

Draft language:

```markdown
3. **Unified retrieval across corpora** — perform weighted-score retrieval over three corpora using the query from Step 0.5. **Remove** the prior 3-tier grep logic; this step is the only retrieval behavior.

   a. **Enumerate candidate files** with three Grep passes (paths relative to project root):
      - `.adlc/knowledge/lessons/*.md` — no status filter
      - `.adlc/specs/*/requirement.md` — include only where frontmatter `status` is `approved`, `in-progress`, or `deployed`
      - `.adlc/bugs/*.md` — include only where frontmatter `status` is `resolved`
      If any directory is empty or missing, skip it (cold-start path).

   b. **Read the frontmatter of every candidate** (Read with `limit: 20` usually suffices). Parse the fields `component`, `domain`, `stack`, `concerns`, `tags`, `updated`, `created`, and `status`.

   c. **Compute score per candidate** using the weighted-sum rule:
      - `+3` if `doc.component == query.component`
      - `+2` if `doc.domain == query.domain`
      - `+2 × |doc.concerns ∩ query.concerns|`
      - `+1 × |doc.stack ∩ query.stack|`
      - `+1 × |doc.tags ∩ query.tags|`
      - `+1` foundational floor **only for lesson documents** with none of the five tag fields populated. Specs and bugs with zero tag overlap score `0`.

   d. **Filter** docs with final score `0`.

   e. **Sort** descending by score. **Tiebreak**: newer `updated` wins; fallback chain when `updated` is missing: `created` → file mtime → stable alphabetical by `id`. Same-date tiebreak: corpus priority `lesson > bug > spec`.

   f. **Take top 15 globally** across all corpora. No per-corpus quotas. If fewer than 15 candidates survive filtering, take what's available.

   g. **Read the full body** of each top-15 doc into context.

   h. **Surface the retrieval summary** to the user before authoring continues:
      ```
      Retrieved context for this REQ:
        LESSON-034 (lesson, score 5): Silent failure remediation
        BUG-012    (bug,    score 5): Auth rate-limit bypass
        REQ-019    (spec,   score 3): Prior login redesign
        ... (etc.)
      ```

   i. **Cold-start path**: if every corpus is empty or all candidates filter to zero, skip retrieval and note this explicitly when Step 3 writes the `## Retrieved Context` section.
```

### Step 3 — Extended Authoring Requirements

Add three sub-requirements to the existing Step 3:

```markdown
### Step 3: Create the Requirement Spec (updated)

... (existing sub-steps 1 and 2 unchanged) ...

3. Fill in all sections:
   - **Frontmatter**: id, title, status (`draft`), deployable, created/updated dates, AND the five query tags from Step 0.5: `component`, `domain`, `stack`, `concerns`, `tags`. This self-tagging makes the new REQ retrievable for future `/spec` invocations (per REQ-258 BR-7).
   - (existing sections — Description, System Model, Business Rules, Acceptance Criteria, External Dependencies, Assumptions, Open Questions, Out of Scope — unchanged)
   - **NEW**: add a `## Retrieved Context` section at the end listing every retrieved source from Step 1.3.h with `ID (corpus, score): title`. If no context was retrieved (cold-start path), write `"No prior context retrieved — first REQ in this area."`

4. **Citations** — when a retrieved doc directly informed a Business Rule, Assumption, or Acceptance Criterion, add an inline citation in the form `(informed by BUG-012)` or `(informed by REQ-019, LESSON-034)` at the end of that line. Citations are required when the retrieved doc is load-bearing for the rule; optional for background reading.
```

### Do NOT change

- Step 2 (REQ ID atomic counter) — untouched.
- The Ethos injection macro — untouched.
- The `Prerequisites` block — untouched.
- The Quality Checklist — may be extended with one line if it cleanly fits ("Retrieved Context section present"), otherwise leave alone.

### Edge cases to handle in the instructions

- Very large corpora (>500 candidates): the frontmatter-peek approach still works but is slower. Not a blocker at current scale.
- Malformed frontmatter on a candidate (missing `---` delimiters): skip the doc, continue. Do not crash.
- Query tags can be empty-ish (e.g., `stack: []`) — scoring still works; just fewer matches, more candidates filter to zero. Acceptable.

### Dogfooding reference

REQ-258's own requirement.md at `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/requirement.md` demonstrates the expected output shape (self-tagged frontmatter + `## Retrieved Context` section at the end with cold-start note). Use it as a reference for what a Step 3 output should look like.
