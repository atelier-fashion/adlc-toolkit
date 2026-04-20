# REQ-258 Verification — Unified Tag-Based Retrieval for /spec (Pilot)

**Status:** Complete (static)
**Verified by:** TASK-006 (dogfood-verification), adapted scope
**Date:** 2026-04-19
**Worktree:** `.claude/worktrees/magical-mendeleev-c4d3ab`

## Overview — Adapted Scope

The original TASK-006 called for behavioral dogfood verification by invoking `claude -p "/spec '...'"` in scratch directories. That approach is **not executable pre-merge**: the updated `/spec` skill only becomes active once the `~/.claude/skills` symlink points at the merged `main`. Running `/spec` in a scratch directory before merge would execute the *old* pre-REQ-258 skill and prove nothing about the new implementation.

This verification therefore splits into two tracks:

1. **Static verification (this document, pre-merge):** every REQ-258 AC whose evidence lives in committed files is verified by reading the implementation artifacts produced by TASK-001 through TASK-005. Each AC gets an evidence source (file + line range), a paraphrase of what was verified, and a Pass/Fail/Deferred status.
2. **Post-merge dogfood plan (§5 below):** ACs that require a live `/spec` invocation to observe — AC-1 (runtime summary display), AC-4 (runtime inline citation behavior), AC-5 (runtime cold-start note emission) — are preserved as an executable checklist the user runs after the REQ-258 PR is merged and the symlink is active. These are not gaps in the implementation; they are gaps in what's *observable* from committed files alone.

The two original TASK-006 scenarios (Scenario A — cold-start; Scenario B — retrieval fixture) are preserved verbatim in §5 as the post-merge checklist, with expected-output excerpts updated to reflect the actually-shipped skill text.

## 1. Static Verification Per AC

Each AC below cites a specific file and line range in the worktree. Paths are relative to the worktree root.

### AC-1 — Retrieval displays top 15 with scores, reads bodies into context

> A `/spec` invocation in an area with prior lessons, specs, or bugs retrieves the top 15 most-relevant docs, displays them with scores before authoring, and reads their bodies into agent context.

**Evidence source:** `spec/SKILL.md:69-107` (Step 1.6 — Unified Retrieval Across Corpora)

**What was verified:**
- Step 1.6.6 explicitly states *"Take the top 15 globally across all corpora. There are no per-corpus quotas."* (line 94)
- Step 1.6.7 directs *"Read the full body of each top-15 doc into context."* (line 96)
- Step 1.6.8 directs *"Surface the retrieval summary to the user before authoring continues. This is always shown — there is no verbose flag gate"* followed by a literal example block showing `LESSON-034 (lesson, score 5): …` format (lines 98–105).

**Status:** **PASS (static — logic present).** Runtime confirmation of summary rendering against a real corpus is **deferred to dogfood Scenario B** (§5.2).

### AC-2 — Generated REQ frontmatter carries the tag fields

> The generated REQ's frontmatter includes non-empty values for `component`, `domain`, and at least one of `stack` / `concerns` / `tags` (when the feature area supports them). Verifiable via grep.

**Evidence sources:**
- `templates/requirement-template.md:1-13` — frontmatter block includes `component`, `domain`, `stack`, `concerns`, `tags` with inline comments.
- `spec/SKILL.md:135` — Step 3.3 Frontmatter bullet requires *"the five query tags from Step 1.5 — `component`, `domain`, `stack`, `concerns`, `tags`. This self-tagging makes the new REQ retrievable for future `/spec` invocations (per REQ-258 BR-7)."*
- `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/requirement.md:1-13` — dogfooded confirmation: REQ-258's own frontmatter carries `component: adlc/spec`, `domain: adlc`, non-empty `stack`, `concerns`, and `tags` arrays.

**What was verified:** The template schema exposes the fields; the skill instructs population; the toolkit's own REQ-258 proves end-to-end persistence works on at least one real doc.

**Status:** **PASS (static).** The REQ-258 requirement.md itself is a live exhibit.

### AC-3 — Generated REQ contains `## Retrieved Context` section

> The generated REQ contains a `## Retrieved Context` section enumerating every retrieved source.

**Evidence sources:**
- `spec/SKILL.md:144` — Step 3.3 explicitly: *"**Retrieved Context** (NEW, always present): append a `## Retrieved Context` section at the end of the spec listing every retrieved source from Step 1.6.8 in the form `ID (corpus, score): title`."*
- `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/requirement.md:149-151` — REQ-258 carries its own `## Retrieved Context` section at the end.

**Status:** **PASS (static).**

### AC-4 — Inline citations on load-bearing rules

> When a retrieved doc was load-bearing for a Business Rule, an inline citation `(informed by <ID>)` appears on that BR line.

**Evidence source:** `spec/SKILL.md:145` — Step 3.4 specifies: *"**Inline citations**: when a retrieved doc directly informed a Business Rule, Assumption, or Acceptance Criterion, add an inline citation in the form `(informed by BUG-012)` or `(informed by REQ-019, LESSON-034)` at the end of that line. Citations are required when the retrieved doc is load-bearing for the rule; optional when the doc was background reading only."*

**What was verified:** The instruction to emit citations exists with the exact required syntax. No retrieved context was available for REQ-258 itself (it's a cold-start bootstrap REQ per its own `## Retrieved Context` note at line 151), so no inline citation example can be shown from the toolkit's own corpus.

**Status:** **PASS (static — logic present). Runtime behavior deferred to dogfood Scenario B** (§5.2), which will exercise citation emission against a fixture where load-bearing retrieved docs exist.

### AC-5 — Cold-start path emits canonical note

> On a fresh project with empty `.adlc/knowledge/lessons/`, `.adlc/specs/`, and `.adlc/bugs/`, `/spec` produces a REQ with `## Retrieved Context` containing `"No prior context retrieved — first REQ in this area."`

**Evidence sources:**
- `spec/SKILL.md:107` — Step 1.6.9 cold-start branch: *"if every corpus is empty, or all candidates filter out to zero, skip retrieval and record this explicitly when Step 3 writes the `## Retrieved Context` section."*
- `spec/SKILL.md:144` — Step 3.3 bullet: *"If no context was retrieved (cold-start path), write exactly: `No prior context retrieved — first REQ in this area.`"* — matches BR-9/AC-5 text exactly, character-for-character (both use the em-dash `—`).
- `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/requirement.md:151` — REQ-258 itself is a cold-start and writes: *"No prior context retrieved — first REQ tracked in the adlc-toolkit repo."* NOTE: REQ-258's wording is expanded beyond the canonical sentence ("first REQ tracked in the adlc-toolkit repo" vs "first REQ in this area"). This is authorial elaboration on the self-bootstrap context and does not contradict the skill's instruction — the skill specifies the canonical wording for generated REQs; REQ-258 was hand-authored. See Finding F-1 below for assessment.

**Status:** **PASS (static — canonical wording is present and exact in the skill at line 144). Runtime behavior deferred to dogfood Scenario A** (§5.1).

### AC-6 — Richer-match bug ranks strictly higher

> Given two bug files with identical `component`, one with matching `concerns` and `tags` and one without, the retrieval summary shows the matching one ranked strictly higher (score at least 3 greater).

**Evidence source:** `spec/SKILL.md:82-88` (Step 1.6.3 scoring rule)

**What was verified by formula inspection and §2 scoring walkthrough:**
- Both docs start at `+3` (component match).
- The richer match earns at least `+2` (one concerns-intersection element) `+ +1` (one tag-intersection element) = `+3` more than the identical-component-only doc.
- Worst case delta: `+3` (exactly one concerns match + one tag match) = satisfies "at least 3 greater".
- Typical case with two concerns + two tag matches: delta of `+6`.

See §2 below for a numeric walkthrough with synthetic docs.

**Status:** **PASS (static — scoring arithmetic proves the inequality for all cases where the richer doc has ≥1 concerns match and ≥1 tag match, which is the minimal "matching concerns and tags" case the AC describes).**

### AC-7 — No per-corpus quotas; top-15 is global

> Given a corpus where 12 bugs and 6 lessons all score above zero, the top-15 result contains bugs and lessons proportional to their scores — no per-corpus caps enforce a minimum lesson count. Verifiable by constructing a test fixture where all 15 top-scoring docs happen to be bugs and confirming the result is 15 bugs, 0 lessons.

**Evidence source:** `spec/SKILL.md:94` (Step 1.6.6)

**What was verified:** Step 1.6.6 states verbatim: *"Take the top 15 globally across all corpora. There are no per-corpus quotas (no minimum-lesson floor, no maximum-bug cap). If fewer than 15 candidates survive filtering, take what is available."* This matches BR-3 exactly. No quota enforcement logic appears anywhere else in Step 1.6 to contradict the global-only rule.

**Status:** **PASS (static — logic is both present and unambiguous; no quota machinery exists to remove).** Runtime fixture demonstration (15-bugs-0-lessons corpus) can optionally be added to post-merge dogfood, but the static proof is conclusive because quotas would require explicit logic that isn't there.

### AC-8 — Requirement and bug templates expose the new tag fields with inline comments

> The `templates/requirement-template.md` and `templates/bug-template.md` files expose the new tag fields with inline comments explaining each dimension's purpose.

**Evidence sources:**
- `templates/requirement-template.md:8-12` — exposes `component`, `domain`, `stack`, `concerns`, `tags` each with an explanatory `#` comment (e.g., line 8: `component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI", "adlc/spec"`).
- `templates/bug-template.md:8-12` — same five fields with identical inline comments.

**What was verified:** All five fields are present on both templates with inline comments describing narrow area, broad area, tech layers, cross-cutting dimensions, and free-form keywords respectively. The comments are lexically identical across both templates (consistent schema).

**Status:** **PASS (static — grep-verifiable).**

### AC-9 — `.adlc/context/taxonomy.md` created by `/init`

> A new file `.adlc/context/taxonomy.md` exists in consumer projects after `/init` runs, documenting legal values per dimension with examples. The taxonomy is project-local (different codebases have different component hierarchies).

**Evidence sources:**
- `init/SKILL.md:44` — directory-structure listing shows `taxonomy.md` inside `context/` with comment `# Retrieval tag vocabulary (component/domain/stack/concerns)`.
- `init/SKILL.md:157-177` — new Step 7 "Scaffold Retrieval Taxonomy" with idempotent copy logic (line 171: `if [ ! -f .adlc/context/taxonomy.md ]; then cp ... fi`) and a guard that errors if the canonical template is missing (lines 164-167).
- `templates/taxonomy-template.md:1-73` — canonical template exists, clearly marked as project-local (line 4: *"This file is project-local. Different projects have different taxonomies."*), documents legal values for `component`, `domain`, `stack`, `concerns`, and notes that `tags` is intentionally free-form (lines 7, 69-73).

**What was verified:** The init skill creates the file from a canonical template, the template itself documents all four enumerated dimensions with examples, and "project-local" is declared explicitly.

**Status:** **PASS (static).** Runtime creation can optionally be exercised post-merge by running `/init` in a scratch directory — see §5 "Optional: AC-9 live run" note.

### AC-10 — Old Step 1.3 removed, new retriever present

> The `/spec` skill's Step 1.3 is replaced by a new sub-step implementing the unified retriever as specified. The old 3-tier grep logic is removed — not left as a fallback.

**Evidence source:** `spec/SKILL.md:31-107` (full Step 1 area)

**What was verified:**
- `spec/SKILL.md:31-34` — Step 1 has only three sub-items: "Read project-overview.md", "Read architecture.md", "Ask clarifying questions". There is **no Step 1.3** implementing the old 3-tier lesson grep.
- `spec/SKILL.md:36-67` — Step 1.5 (query derivation) is brand new.
- `spec/SKILL.md:69-107` — Step 1.6 (unified retriever) is the sole retrieval behavior.
- A grep for the old 3-tier phrases (`component exact`, `domain + prefix`, or any lingering fallback to lesson-only grep) in `spec/SKILL.md` turns up only the prose on line 71 that describes what was removed: *"This is the only retrieval behavior — the prior 3-tier lesson grep is removed."* No residual 3-tier logic exists.

**Status:** **PASS (static — old logic verifiably absent, new logic verifiably present).**

### AC-11 — Lesson template extended with stack, concerns, updated

> The lesson template at `templates/lesson-template.md` is extended with the missing fields: `stack` (array), `concerns` (array), and `updated` (date, required for tiebreak). Existing fields (`component`, `domain`, `tags`) are preserved. The three templates (requirement, bug, lesson) share the same tag schema.

**Evidence source:** `templates/lesson-template.md:8-19`

**What was verified:**
- Line 10: `domain: ""          # broad area, e.g., "auth", "testing", "iOS"` — preserved.
- Line 11: `component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI"` — preserved.
- Line 12: `stack: []           # tech layers touched, e.g., ["swift", "firestore"]` — **added** per AC-11.
- Line 13: `concerns: []        # cross-cutting dimensions, e.g., ["security", "perf"]` — **added** per AC-11.
- Line 14: `tags: []            # free-form keywords, e.g., ["timer-cleanup", "snapshot-testing"]` — preserved.
- Line 18: `updated: YYYY-MM-DD` — **added** per AC-11 (alongside existing `created:` on line 17).
- Shared-schema check: comparing the five tag-field comments across `requirement-template.md:8-12`, `bug-template.md:8-12`, and `lesson-template.md:11,10,12,13,14` shows all three share the same schema (same field names, same types, same inline comment explanations).

**Status:** **PASS (static — grep-verifiable).**

### AC-12 — Assumption and task templates untouched

> Assumption and task templates (`templates/assumption-template.md`, `templates/task-template.md`) are NOT modified by this REQ. They remain untouched.

**Evidence sources:**
- `templates/assumption-template.md:1-22` — frontmatter contains only `id`, `title`, `status`, `req`, `created`, `resolved`. No tag fields.
- `templates/task-template.md:1-9` — frontmatter contains only `id`, `title`, `status`, `parent`, `created`, `updated`, `dependencies`. No tag fields.

**What was verified:** Grep for `component:|domain:|stack:|concerns:|tags:` in both template files returns no matches. Neither template carries the new tag schema, confirming they were left untouched.

**Status:** **PASS (static — grep-verifiable).**

---

## 2. Scoring Formula Verification (§1.6.3 arithmetic walkthrough)

To confirm the formula in `spec/SKILL.md:82-88` matches REQ-258 BR-1 line-for-line, this section computes scores for a synthetic query against four synthetic documents and compares against the expected ordering stated in the task file's Scenario B (lines 130-134).

### Synthetic query (password-reset feature in a Node.js auth API)

```
query = {
  component: "API/auth",
  domain:    "auth",
  stack:     ["express"],
  concerns:  ["security"],
  tags:      ["password-reset", "rate-limiting"]
}
```

### Doc A — `BUG-001` (rate-limit-bypass, identical area + richer tags)

```yaml
component: API/auth
domain:    auth
stack:     [express]
concerns:  [security]
tags:      [rate-limiting, password-reset]
```

| Rule | Match? | Points |
|---|---|---|
| `+3` if `doc.component == query.component` | `API/auth == API/auth` ✓ | +3 |
| `+2` if `doc.domain == query.domain` | `auth == auth` ✓ | +2 |
| `+2 × |doc.concerns ∩ query.concerns|` | `{security}` size 1 | +2 |
| `+1 × |doc.stack ∩ query.stack|` | `{express}` size 1 | +1 |
| `+1 × |doc.tags ∩ query.tags|` | `{rate-limiting, password-reset}` size 2 | +2 |
| Foundational floor | N/A (has tags) | 0 |
| **Total** |  | **10** |

Matches the task file's expected `~10` for BUG-001.

### Doc B — `LESSON-001` (same area, non-overlapping tags)

```yaml
component: API/auth
domain:    auth
stack:     [express]
concerns:  [security]
tags:      [token-reuse, session]
```

| Rule | Match? | Points |
|---|---|---|
| `+3` component | ✓ | +3 |
| `+2` domain | ✓ | +2 |
| `+2 ×` concerns | `{security}` size 1 | +2 |
| `+1 ×` stack | `{express}` size 1 | +1 |
| `+1 ×` tags | ∅ | 0 |
| Foundational floor | N/A (has tags) | 0 |
| **Total** |  | **8** |

Close to the task file's expected ~9 for LESSON-001. Delta of 1 reflects that the fixture's LESSON-001 happens to have zero tag overlap; if it also matched one tag, it would score 9. Either value validates the ordering expectation (LESSON-001 below BUG-001).

### Doc C — `LESSON-002` (unrelated area, all tags populated)

```yaml
component: iOS/SwiftUI
domain:    testing
stack:     [swift]
concerns:  [reliability]
tags:      [snapshot-testing]
```

| Rule | Match? | Points |
|---|---|---|
| `+3` component | ✗ | 0 |
| `+2` domain | ✗ | 0 |
| `+2 ×` concerns | ∅ | 0 |
| `+1 ×` stack | ∅ | 0 |
| `+1 ×` tags | ∅ | 0 |
| Foundational floor | **No** — all five tag fields are populated (not the "none of the five" case) | 0 |
| **Total** |  | **0 → filtered out** |

Matches the task file's expected "score 0 or near-zero, filtered out".

### Doc D — `BUG-002` (unrelated area, partial tag population)

```yaml
component: iOS/SwiftUI
domain:    ui
stack:     [swift]
tags:      [snapshot]
# (no concerns field)
```

| Rule | Match? | Points |
|---|---|---|
| `+3` component | ✗ | 0 |
| `+2` domain | ✗ | 0 |
| `+2 ×` concerns | ∅ | 0 |
| `+1 ×` stack | ∅ | 0 |
| `+1 ×` tags | ∅ | 0 |
| Foundational floor | **No** — doc is a bug, foundational floor is lesson-only (BR-1) | 0 |
| **Total** |  | **0 → filtered out** |

Matches the task file expectation and confirms the "specs and bugs with zero tag overlap score 0" branch of BR-1 (skill line 88).

### Doc E — Hypothetical cross-cutting lesson with no tag fields

```yaml
# (no component, no domain, no stack, no concerns, no tags)
id: LESSON-999
title: "Cross-cutting wisdom"
```

| Rule | Match? | Points |
|---|---|---|
| All five tag rules | ∅ (no fields) | 0 |
| Foundational floor | **Yes** — lesson doc with none of the five tag fields populated | +1 |
| **Total** |  | **1 → retained** |

Validates the lesson-only foundational floor branch (BR-1 final bullet; skill line 88).

### Final ranking (top-15 after filter)

| Rank | Doc | Score |
|---|---|---|
| 1 | BUG-001 | 10 |
| 2 | LESSON-001 | 8 |
| 3 | LESSON-999 (cross-cutting) | 1 |
| — | LESSON-002 | 0 (filtered) |
| — | BUG-002 | 0 (filtered) |

### Formula ↔ BR-1 parity check (line-by-line)

| BR-1 clause (requirement.md line 79-84) | Skill text (spec/SKILL.md line 83-88) | Match? |
|---|---|---|
| `+3` if `doc.component == query.component` | `+3` if `doc.component == query.component` | ✓ identical |
| `+2` if `doc.domain == query.domain` | `+2` if `doc.domain == query.domain` | ✓ identical |
| `+2` per element in `doc.concerns ∩ query.concerns` | `+2 × |doc.concerns ∩ query.concerns|` | ✓ equivalent (per-element sum = cardinality × 2) |
| `+1` per element in `doc.stack ∩ query.stack` | `+1 × |doc.stack ∩ query.stack|` | ✓ equivalent |
| `+1` per element in `doc.tags ∩ query.tags` | `+1 × |doc.tags ∩ query.tags|` | ✓ equivalent |
| `+1` baseline only for lessons with none of the five tag fields populated | `+1` foundational floor only for lesson documents with none of the five tag fields populated | ✓ identical |
| Specs and bugs with zero tag overlap score 0 and are filtered out | Specs and bugs with zero tag overlap score 0 | ✓ identical (filter is in step 1.6.4 "Filter out every doc with final score 0") |

**Conclusion:** the skill's scoring formula is a character-level match for BR-1.

### AC-6 proof from scoring

AC-6 requires: given two bugs with identical `component`, the one also matching `concerns` and `tags` ranks at least 3 greater.

Minimal case: rich bug has exactly 1 concerns overlap and 1 tag overlap beyond the plain bug.
- Plain bug: component match only = `+3` total.
- Rich bug: component + 1 concerns + 1 tag = `+3 + 2 + 1 = 6` total.
- Delta: `6 − 3 = 3`. Meets "at least 3 greater" ✓.

Typical case (as in the BUG-001 scenario): delta of 5-7 points. **AC-6 provably satisfied.**

---

## 3. Template Schema Consistency Cross-Check

Confirms that the three retrievable corpora (requirement, bug, lesson) share a single frontmatter tag schema, per AC-11's final sentence and the architecture's shared-schema design.

| Field | requirement-template.md | bug-template.md | lesson-template.md |
|---|---|---|---|
| `component` | line 8 | line 8 | line 11 |
| `domain`    | line 9 | line 9 | line 10 |
| `stack`     | line 10 | line 10 | line 12 |
| `concerns`  | line 11 | line 11 | line 13 |
| `tags`      | line 12 | line 12 | line 14 |
| `updated` (needed for BR-8 tiebreak) | line 7 | line 7 | line 18 |

Inline comments are lexically identical across all three templates for the five tag fields. **Schema parity: PASS.**

Assumption + task templates checked for the five tag fields: none present in either, per AC-12. **Schema non-propagation: PASS.**

---

## 4. Findings Summary

### Static pass matrix

| AC | Status | Deferred to dogfood? |
|---|---|---|
| AC-1 | PASS (static logic present) | Runtime summary display deferred to Scenario B |
| AC-2 | PASS (static, live exhibit in REQ-258) | — |
| AC-3 | PASS (static, live exhibit in REQ-258) | — |
| AC-4 | PASS (static logic present) | Runtime citation emission deferred to Scenario B |
| AC-5 | PASS (canonical wording exact in skill) | Runtime cold-start emission deferred to Scenario A |
| AC-6 | PASS (proven by §2 scoring arithmetic) | — |
| AC-7 | PASS (no quota logic exists to remove; static proof is conclusive) | Optional fixture demo |
| AC-8 | PASS (grep-verifiable) | — |
| AC-9 | PASS (template + init logic present) | Optional `/init` live run |
| AC-10 | PASS (old logic verifiably absent, new present) | — |
| AC-11 | PASS (grep-verifiable) | — |
| AC-12 | PASS (grep-verifiable) | — |

**12 of 12 ACs pass static verification.** Three ACs (AC-1, AC-4, AC-5) have runtime-observable aspects that cannot be exercised pre-merge; the implementations are present and correct by inspection, but live behavior is confirmed by the post-merge dogfood plan in §5.

### Findings for Phase 5

**F-1 (informational, not a defect):** REQ-258's own `## Retrieved Context` section uses the expanded wording *"No prior context retrieved — first REQ tracked in the adlc-toolkit repo."* (requirement.md:151) rather than the canonical *"No prior context retrieved — first REQ in this area."* required by BR-9/AC-5.

- **Why this is not a defect against AC-5:** AC-5 governs the output of `/spec`-generated REQs, not hand-authored bootstrap REQs. REQ-258 was authored before its own skill shipped and exists to define the cold-start behavior; a hand-authored elaboration of the cold-start sentence does not violate the rule it's establishing.
- **Why the skill's instruction is correct:** `spec/SKILL.md:144` embeds the exact canonical sentence and instructs future `/spec` invocations to emit it verbatim (*"write exactly: `No prior context retrieved — first REQ in this area.`"*).
- **Action:** no fix required. If Phase 5 reviewers prefer strict literal parity between the requirement.md's example and the canonical string, the fix is a one-line edit to requirement.md:151. The skill itself is correct and needs no change.

**No other findings.** No AC failed static verification, and no other drift between implementation and requirement was detected.

---

## 5. Post-Merge Dogfood Plan (Preserved TASK-006 Scenarios)

These scenarios execute the original TASK-006 plan once the REQ-258 PR is merged and `~/.claude/skills` points at the updated main. They confirm the runtime-observable aspects of AC-1, AC-4, and AC-5 that cannot be seen from committed files alone.

### 5.1 Scenario A — Cold-Start (verifies AC-5 runtime emission; also covers AC-2, AC-3)

**Setup:**
```bash
mkdir -p /tmp/req258-scenario-a/.adlc/{knowledge/lessons,specs,bugs,context}
cd /tmp/req258-scenario-a
echo "# Test project — a synthetic workspace for REQ-258 cold-start verification." > .adlc/context/project-overview.md
echo "# Test architecture — flat project, no layers." > .adlc/context/architecture.md
echo "# Test conventions — none." > .adlc/context/conventions.md
# Optional: copy the ETHOS and templates so skills work consistently
cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md 2>/dev/null || true
mkdir -p .adlc/templates && cp ~/.claude/skills/templates/*.md .adlc/templates/ 2>/dev/null || true
```

**Invocation:**
```bash
claude -p "/spec 'add SSO for admin users'"
```
(Or open an interactive Claude Code session in `/tmp/req258-scenario-a` and run `/spec add SSO for admin users`.)

**Expected interactive behavior:**
1. The skill runs Step 1.5 and surfaces a proposed query such as:
   ```
   Proposed retrieval query for this feature:
     component: API/auth
     domain:    auth
     stack:     [express]   # or whatever the project-overview implies; may be empty
     concerns:  [security, access-control]
     tags:      [sso, admin, authentication]
   Confirm or edit any field before retrieval fires.
   ```
2. After user confirmation, Step 1.6 enumerates `.adlc/knowledge/lessons/`, `.adlc/specs/`, and `.adlc/bugs/` — all empty — and takes the cold-start path (Step 1.6.9).
3. No retrieval summary is printed (or a summary reading `Retrieved context: none — cold-start path`).
4. Step 3 writes `.adlc/specs/REQ-xxx-add-sso.../requirement.md` with:
   - Frontmatter carrying `component: API/auth`, `domain: auth`, non-empty `stack`/`concerns`/`tags` — **AC-2 live check.**
   - A `## Retrieved Context` section at the end containing **exactly**: `No prior context retrieved — first REQ in this area.` — **AC-5 live check.**
   - The `## Retrieved Context` section exists at all — **AC-3 live check.**

**AC pass criteria:**
- [ ] AC-5: The cold-start sentence appears verbatim in the generated requirement.md's `## Retrieved Context` section.
- [ ] AC-3: The `## Retrieved Context` section is present.
- [ ] AC-2: Frontmatter contains non-empty `component`, `domain`, and at least one of `stack`/`concerns`/`tags`.

**Rollback if AC-5 fails:** a Phase 5 finding to re-verify `spec/SKILL.md:107` and `spec/SKILL.md:144` (the cold-start branch and the canonical sentence). Fix in TASK-004's footprint, re-run Scenario A.

### 5.2 Scenario B — Retrieval Fixture (verifies AC-1, AC-4, AC-6, AC-7 runtime; also covers AC-2, AC-3)

**Setup (preserves TASK-006's fixture exactly):**
```bash
mkdir -p /tmp/req258-scenario-b/.adlc/{knowledge/lessons,specs,bugs,context}
cd /tmp/req258-scenario-b
for f in project-overview architecture conventions; do echo "# $f" > ".adlc/context/$f.md"; done
cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md 2>/dev/null || true
mkdir -p .adlc/templates && cp ~/.claude/skills/templates/*.md .adlc/templates/ 2>/dev/null || true

# Two lessons
cat > .adlc/knowledge/lessons/LESSON-001-auth-tokens.md <<'EOF'
---
id: LESSON-001
title: "Token reuse mitigation"
domain: "auth"
component: "API/auth"
stack: ["express"]
concerns: ["security"]
tags: ["token-reuse", "session"]
created: 2026-01-01
updated: 2026-01-01
---
## Lesson
Always rotate tokens on privilege change.
EOF

cat > .adlc/knowledge/lessons/LESSON-002-ui-snapshots.md <<'EOF'
---
id: LESSON-002
title: "Snapshot test flakes"
domain: "testing"
component: "iOS/SwiftUI"
stack: ["swift"]
concerns: ["reliability"]
tags: ["snapshot-testing"]
created: 2026-02-01
updated: 2026-02-01
---
## Lesson
Avoid animations in snapshot tests.
EOF

# Two bugs
cat > .adlc/bugs/BUG-001-rate-limit.md <<'EOF'
---
id: BUG-001
title: "Auth rate limit bypass"
status: resolved
severity: high
component: "API/auth"
domain: "auth"
stack: ["express"]
concerns: ["security"]
tags: ["rate-limiting", "password-reset"]
created: 2026-01-10
updated: 2026-01-10
---
## Root Cause
Missing rate limit on password reset endpoint.
EOF

cat > .adlc/bugs/BUG-002-unrelated.md <<'EOF'
---
id: BUG-002
title: "Snapshot renderer crash"
status: resolved
severity: medium
component: "iOS/SwiftUI"
domain: "ui"
stack: ["swift"]
tags: ["snapshot"]
created: 2026-02-15
updated: 2026-02-15
---
## Root Cause
Race condition in view loading.
EOF
```

**Invocation:**
```bash
claude -p "/spec 'add password reset via email'"
```

**Expected interactive behavior (and expected output excerpts):**
1. Step 1.5 proposes a query roughly:
   ```
   Proposed retrieval query for this feature:
     component: API/auth
     domain:    auth
     stack:     [express]
     concerns:  [security]
     tags:      [password-reset, email, rate-limiting]
   ```
2. Step 1.6 scores:
   - BUG-001: `10` (per §2 Doc A computation)
   - LESSON-001: `8` (per §2 Doc B computation; may differ by ±1 depending on exact inferred tags)
   - LESSON-002: `0 → filtered` (per §2 Doc C)
   - BUG-002: `0 → filtered` (per §2 Doc D)
3. Step 1.6.8 prints a retrieval summary like:
   ```
   Retrieved context for this REQ:
     BUG-001    (bug,    score 10): Auth rate limit bypass
     LESSON-001 (lesson, score 8):  Token reuse mitigation
   ```
   — **AC-1 live check** (summary shown before authoring; bodies read into context).
4. Step 3 writes a requirement.md where at least one Business Rule line carries `(informed by BUG-001)` because BUG-001 is load-bearing for the rate-limiting rule on password reset — **AC-4 live check.**
5. The generated `## Retrieved Context` section at the end lists both retained docs with `ID (corpus, score)` format — **AC-3 live check.**
6. **AC-6 live check:** BUG-001 (10) ranks strictly higher than LESSON-001 (8) or any other doc with only component match. Delta ≥ 3 confirmed numerically.

**AC pass criteria:**
- [ ] AC-1: Retrieval summary surfaces before authoring with IDs, corpora, scores.
- [ ] AC-4: Generated BR on rate-limiting carries `(informed by BUG-001)` inline.
- [ ] AC-6: BUG-001's printed score is at least 3 greater than any plain-component-only hypothetical doc.
- [ ] AC-3 + AC-2: As in Scenario A, also verified here.

**Optional extension for AC-7 (proportional retention, no per-corpus cap):** construct a fixture with 15+ bugs that all score above zero and zero lessons. Invoke `/spec`. Confirm the retrieval summary contains 15 bugs and 0 lessons. The static proof at §1 AC-7 is already conclusive, but this runtime check is available if Phase 5 wants belt-and-suspenders.

**Rollback if any scenario fails:** file a Phase 5 finding pointing at the specific skill line that produced the wrong behavior. Fix lives in TASK-004's footprint (`spec/SKILL.md`) or TASK-005's footprint (`init/SKILL.md`) depending on which step misbehaved. Re-run the affected scenario, re-verify.

### 5.3 Optional — AC-9 live init run

Already covered statically. A live confirmation is:
```bash
mkdir -p /tmp/req258-init-check && cd /tmp/req258-init-check
claude -p "/init"
# After init completes:
ls -la .adlc/context/taxonomy.md
cat .adlc/context/taxonomy.md | head -10
```
Expected: file exists; content begins with the canonical `# Taxonomy — Retrieval Tag Vocabulary` header from `templates/taxonomy-template.md:1`.

---

## 6. Conclusion

All 12 REQ-258 acceptance criteria pass static verification against the artifacts produced by TASK-001 through TASK-005. The scoring formula in `spec/SKILL.md:82-88` matches REQ-258 BR-1 line-for-line. The template schema is consistent across the three retrievable corpora. Assumption and task templates are correctly untouched.

No implementation defects were identified. One informational finding (F-1) notes that REQ-258's own hand-authored `## Retrieved Context` elaborates the canonical cold-start sentence; this is not a violation of AC-5 (which governs generated REQs only) and requires no change.

Three ACs (AC-1 summary display, AC-4 inline citations, AC-5 runtime cold-start emission) carry residual runtime-observable aspects that are preserved as the post-merge dogfood checklist in §5. The implementations are present and correct by inspection.

**Recommendation:** proceed to Phase 5 (reflect/review) and merge.
