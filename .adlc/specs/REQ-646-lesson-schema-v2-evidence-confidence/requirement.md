---
id: REQ-646
title: "Lesson schema v2: evidence, confidence, kind, enforcement — and reflector-style capture prompts"
status: complete
deployable: true
created: 2026-10-26
updated: 2026-10-27
component: "adlc/wrapup"
domain: "adlc"
stack: [markdown, bash, claude-skills]
concerns: [knowledge-compounding, knowledge-quality, retrieval, structural-enforcement]
tags: [lesson-template, evidence, confidence, enforcement, wrapup, bugfix, knowledge-capture, harness2, lessons]
---

## Description

Every lesson in `.adlc/knowledge/lessons/` is written from a single pipeline run and
presented as fact. The template has four prose sections (What Happened / Lesson / Why It
Matters / Applies When) and five retrieval tags, but no field says *what evidence* the
lesson rests on, *how confident* the author is, whether it is a lesson about *how the
pipeline works* (a process defect in a skill) or about *what the implementer must know*
(a domain pitfall), or whether anything *enforces* it. `/wrapup` Step 4's drafting
prompt asks "Any surprises? Approaches that didn't work?" and `/bugfix` Phase 6 asks "did
this bug reveal something a future implementer should know?" — neither asks the author
to name the moment that proves the claim, and `/wrapup` has no explicit "no lesson this
time" outcome (`/bugfix` does).

Google's Harness² (arXiv:2610.14224) gates its cross-task library on exactly this: a
library entry is written only when a reflector can produce `cue / lesson / evidence /
confidence`, the reflector is told to *prefer* `confounded` when a single execution is
all that stands behind a claim ("an invented attribution poisons the library for every
later task"), and `NO_ENTRY` is a first-class answer. Its ablation shows the library is
worth +1.8–3.1 points, and that a library without evidence discipline can land *below*
baseline (see `.adlc/research/harness2-adaptation.md` §1, §3.A).

This REQ adds the attribution half to the toolkit's lesson schema — **additively**, so
the existing lessons stay valid byte-for-byte (informed by REQ-262) — and rewrites the
two capture prompts so a new lesson must cite its evidence, declare its confidence and
kind, and state `NO_ENTRY` explicitly when there is nothing transferable. Two of the new
fields reach an executor in this REQ: `confidence` and `supersedes` change `/review`'s
severity escalation (BR-6); `kind` gets its consumer in REQ-647. `enforcement`,
`generalizes` and the rest of `supersedes`'s semantics have **no reader here** and are
recorded for the follow-ups named in Out of Scope — the Description does not claim
otherwise (informed by LESSON-572: a field no executor reads is documentation). The
schema rule is enforced by a sourced partial run on the file just written, not by prose
(informed by LESSON-012).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Lesson (frontmatter) | `kind` | string | enum `process` \| `domain`. Absent on legacy files; **required on every lesson the capture steps write** (BR-2). `process` = how a skill/agent/pipeline works; `domain` = what an implementer must know about the codebase or stack. |
| Lesson (frontmatter) | `evidence` | string | **Required on every lesson the capture steps write.** Must contain at least one **citation token** (BR-3): a 7–40 hex commit sha, a `BUG-`/`REQ-`/`LESSON-`/`TASK-nnn` id, a `path:line`, or a test name. **No home-directory path** (BR-12) and **no credential-shaped substring** (BR-13). |
| Lesson (frontmatter) | `confidence` | string | enum `high` \| `medium` \| `low`, per the contrast rule in BR-4. **Required on every lesson the capture steps write.** |
| Lesson (frontmatter) | `enforcement` | string | enum `none` \| `lint:<check-id>` \| `test:<path>` \| `script:<path>` \| `hook:<name>`. Optional; absent ⇒ `none`. **No reader in this REQ** (Out of Scope). |
| Lesson (frontmatter) | `generalizes` | string[] | Optional. Lesson ids this one generalizes (today only prose, e.g. LESSON-404 "generalizes LESSON-019"). Each `^LESSON-[0-9]{3,6}$`. **No reader in this REQ.** |
| Lesson (frontmatter) | `supersedes` | string[] | Optional. Lesson ids this one replaces. Same regex. Read by `/review` (BR-6) and surfaced by `/spec` (BR-7); scoring unchanged. |
| Lesson (body) | `## Lesson`, `## Applies When` | sections | Both **required non-empty** on every lesson the capture steps write (BR-3). `## Applies When` is the cue. |
| Capture outcome | `NO_ENTRY` | literal | Each capture step ends with exactly one of: a written `LESSON-xxx`, or the literal line `NO_ENTRY: <one-sentence reason>` in the skill's summary slot (BR-14). |

All six frontmatter fields are added **immediately before the closing `---`**; existing
fields are never modified or reordered (informed by REQ-262 BR-7). Absent is a meaningful
"not stated", never coerced to `low` or `none` by a reader except where this spec says so
(`enforcement` absent ⇒ `none`). A reader that treated *absent* and *low* as the same
value would recreate the BUG-194 class of silent mismatch (informed by LESSON-571,
BUG-194). The template's frontmatter, including its naming-convention HTML comment, must
close within the first 25 lines so `/spec` Step 1.6's `Read limit: 30` frontmatter pass
still sees every field.

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `lesson_written` | `/wrapup` Step 4 or `/bugfix` Phase 6 Step 4 writes a `LESSON-xxx` file and `adlc_lesson_check` passes | id, kind, confidence, evidence, enforcement |
| `lesson_no_entry` | the capture step concludes nothing transferable exists, **or** the schema check still fails after the bounded repair (BR-3) | `NO_ENTRY: <reason>` line in the summary slot |
| `lesson_schema_rejected` | `adlc_lesson_check` refuses a draft | field, reason — triggers the repair loop, never a pipeline halt |

_Permissions: not applicable — no runtime actors or roles._

## Business Rules

- [ ] BR-1: `templates/lesson-template.md` gains `kind`, `evidence`, `confidence`, `enforcement`, `generalizes`, `supersedes` with inline comments, placed immediately before the closing `---`, with the whole frontmatter block (comment included) closing by line 25; `templates/taxonomy-template.md` documents the three enums (`kind`, `confidence`, `enforcement`). No existing field changes. Every existing lesson parses unchanged under the retriever (fields matched by name, not position — informed by REQ-258, REQ-262 BR-11).
- [ ] BR-2: every lesson written by `/wrapup` Step 4 or `/bugfix` Phase 6 Step 4 MUST carry a valid `kind`, a valid `confidence`, and an `evidence` value satisfying BR-3, BR-12 and BR-13. "New" is defined by *who writes it*, not by a date: the capture steps are the only writers, so the file they just wrote is new by construction and no ship-date cutoff exists anywhere (a date literal in a SKILL.md is a guard that rots — informed by LESSON-019). **Capture steps never edit an existing lesson**: a refinement of LESSON-A is a new lesson carrying `generalizes: [LESSON-A]` or `supersedes: [LESSON-A]`. Existing lessons are untouched and no backfill is performed (informed by REQ-262 BR-3).
- [ ] BR-3: BR-2 is enforced structurally by a new sourced partial `partials/lesson-check.sh` exposing `adlc_lesson_check <path>`, which validates the file the capture step just wrote: required keys present; enum membership; `^LESSON-[0-9]{3,6}$` for every `generalizes`/`supersedes` entry; `evidence` non-empty and containing at least one citation token (`[0-9a-f]{7,40}`, `(BUG|REQ|LESSON|TASK)-[0-9]{3,6}`, `[A-Za-z0-9_./-]+:[0-9]+`, or `test[_A-Za-z0-9]*`); BR-12 and BR-13 clean; `## Lesson` and `## Applies When` present and non-empty. It takes no cutoff argument and is never run over the historical corpus by this REQ. **Placement**: it runs in its own fenced block that *follows* the instruction that writes the file (the file is written by the model's file tool, not by a fence) and *precedes* the `adlc_recheck_id` fence; `/bugfix` Phase 6 Step 4 is reordered so the write instruction precedes its recheck fence (today the recheck fence comes first). **Repair loop**: on a non-zero exit the drafter repairs the named field (frontmatter only; the body is not regenerated) and re-runs the check, at most **2** retries; after that it deletes the draft file and writes `NO_ENTRY: schema check failed — <field>` to the summary slot (BR-14). This is **not** a pipeline halt and adds no halt point to `/proceed`'s three; `/wrapup` Steps 5–8 always run. The partial is POSIX `sh`, sourced with the canonical guarded spelling, and tested under `partials/tests/` on bash, zsh, sh and dash (informed by REQ-610 BR-3/BR-5, LESSON-020, LESSON-441, LESSON-012).
- [ ] BR-4: both capture prompts (`/wrapup` Step 4 "Lessons Learned" — the delegated `adlc-read --question` text AND the fallback drafting bullets — and `/bugfix` Phase 6 Step 4) are rewritten to carry four rules, in this order: (0) **declare `kind`** — `process` if the lesson is about how a skill, agent, partial or pipeline phase behaves; `domain` if it is about the codebase or stack the implementer works in; (1) **cite the moment** — "a lesson you cannot trace to a specific commit, finding, bug, test or transcript line is speculation; put that moment in `evidence`"; (2) **declare the contrast** — `confidence` is decided by whether the evidence contains a *contrast*: a bug reproduced then fixed, a test failing then passing, a Phase-5 finding confirmed by its fix and re-verify, or two approaches/runs compared. `high` = a contrast was observed **and** the evidence names the mechanism (a specific line, command or finding); `medium` = a contrast was observed but the mechanism is inferred; `low` = a single observation with no contrast. A `/bugfix` lesson almost always has a contrast (reproduce → fix); a `/wrapup` lesson has one only when a Phase-5 finding or a failing test backs it. "An invented attribution poisons retrieval for every later REQ"; (3) **NO_ENTRY is a valid answer** — "if nothing transferable survived, write `NO_ENTRY: <reason>`; never pad". The delegated prompt's "400 words max" and template-section requirements stay. `/wrapup` and `/bugfix` carry the same four rules verbatim; the two steps otherwise differ (only `/wrapup` has a delegated path) and that difference is preserved (informed by REQ-473 BR-8 — the two capture steps move in lockstep).
- [ ] BR-5: the lesson's four prose sections are unchanged in shape. `## Applies When` remains the *cue*; the prompts add one sentence of granularity guidance: "too generic never changes behaviour ('be thorough'); too specific never fires again ('the fee rose on Jan 1') — aim between". BR-3 makes the section mandatory for new lessons (25 of 81 today lack it; prose alone did not hold).
- [ ] BR-6: `/review` Step 4's severity escalation ("a finding that matches a known pitfall is escalated by one level") does NOT fire when the matched lesson carries `confidence: low` **or** is named in another lesson's `supersedes`; the finding still cites the lesson id and the report says `(matched LESSON-xxx, confidence low — not escalated)` or `(matched LESSON-xxx, superseded by LESSON-yyy — not escalated)`. Absent `confidence` (legacy) behaves as today (escalates). The contrast rule in BR-4 keeps this from switching escalation off wholesale: lessons backed by a finding-plus-fix or a reproduce-plus-fix are `medium`/`high` and still escalate (informed by LESSON-572).
- [ ] BR-7: `/spec` Step 1.6 **scoring is unchanged** by this REQ. The only retrieval-side change is presentational: when a retrieved lesson is named in another lesson's `supersedes`, the retrieval summary and `## Retrieved Context` annotate it `(superseded by LESSON-yyy)`. Weighting or filtering by `confidence`/`supersedes` is deferred (Out of Scope) — a scoring change must be designed against the writer vocabulary it reads, and nothing writes these fields until BR-4 ships (informed by LESSON-571).
- [ ] BR-8: the `adlc-read` delegate draft is untrusted data; every `generalizes`/`supersedes` id it proposes is sanitised with the strict regex and an `ls` existence check before being written, exactly as citations are today (informed by LESSON-008, REQ-594 BR-6).
- [ ] BR-9: `/init` already vendors `templates/*.md` and `partials/*.sh`; the new template fields and partial ship through those existing sync surfaces, so `/template-drift` reports consumer copies as `stale` until re-synced. No new sync surface. Because a consumer whose template is stale may still draft without `kind`, BR-4 rule (0) — not the template — is what carries the field to the drafter (informed by LESSON-441).
- [ ] BR-10: all shell is BSD- and zsh-safe: no `\b` in `grep -E`, no `mktemp -t`, numeric validation via `case "$v" in ''|*[!0-9]*)` before arithmetic (informed by LESSON-013, LESSON-441, LESSON-329, LESSON-335).
- [ ] BR-11: `.adlc/context/architecture.md`'s "Knowledge retrieval" paragraph and the `Template anatomy` row for `lesson-template.md` are updated to name the new fields and the `NO_ENTRY` contract (the paragraph currently still describes the pre-REQ-258 3-tier grep).
- [ ] BR-12: `evidence` carries no **home-directory path**. The rule is scoped to what leaks identity: a whitespace- or backtick-delimited token beginning `/Users/`, `/home/`, `/root/`, `$HOME/`, or `~<name>/` is rejected; `/dev/null`, `/bin/sh`, `/tmp/…`, `~/.claude/…`, `~/Library/…`, `https://…` and repo-relative `partials/forge.sh:42` all pass. The capture prompts tell the drafter to replace the home prefix with `~/` rather than drop the citation (informed by REQ-594 BR-7 — basename only; LESSON-007 — privacy of paths). The corpus today cites `/dev/null` in 11 lessons and `~/.claude/…` in 13; those are legitimate evidence and must not be rejected.
- [ ] BR-13: `evidence` (and every other new string field) must not match the REQ-415 five-pattern credential chain (`sk-…`, `AKIA…`, `ghp_…`, `Bearer …`, `*_API_KEY=`/`*_TOKEN=`). `adlc_lesson_check` rejects a match, naming the field. The field solicits verbatim transcript quotes, and the `/bugfix` path and the `/wrapup` fallback path have no redaction step at all; the delegated path redacts only the delegate's *input* (informed by REQ-415, REQ-413).
- [ ] BR-14: the **summary slot**. `/wrapup` Step 5's single-repo and cross-repo summary templates already carry a `### Lessons captured` section (added by BUG-249, with `NO_ENTRY: close-out had no run evidence` as its first defined reason); this REQ keeps that shape — one `LESSON-xxx — <title>` line per lesson or exactly one `NO_ENTRY: <reason>` line — and brings `/bugfix` Step 6's template to it, replacing `(or "None — fix was straightforward and revealed no new pattern")` with the same `NO_ENTRY: <reason>` form. The `NO_ENTRY` literal then has a defined home in both skills.
- [ ] BR-15: on a provenance-classifying harness (BUG-228/BUG-230 class, e.g. Teton Code) the partial cannot run without pinning the session. There, the drafter validates the draft **in-model** against the same rule list and the summary slot states `lesson check: in-model (provenance-classifying harness)`. This is honor-system enforcement on that harness and the spec says so rather than claiming structural coverage it does not have.

## Acceptance Criteria

- [ ] `templates/lesson-template.md` contains the six new fields before the closing `---`, the frontmatter closes by line 25, and `git diff` of the template shows only additions. `templates/taxonomy-template.md` documents the `kind`, `confidence` and `enforcement` enums.
- [ ] A fixture lesson carrying all six new fields, with the template's HTML comment, is parsed by the `/spec` Step 1.6 frontmatter pass (`Read limit: 30`) with every field visible, and scores under the Step 1.6 rule identically to the same fixture without the new fields.
- [ ] `adlc_lesson_check` exits non-zero and names the field on each of: missing `evidence`; `evidence` with no citation token ("we should be careful"); `confidence: maybe`; missing `kind`; `evidence` containing `/Users/x/repo/file.sh`; `evidence` containing `ghp_` + 36 alphanumerics; a missing `## Applies When` section. It exits 0 on a well-formed lesson whose `evidence` is `partials/forge.sh:42 — exit 0 under /bin/sh, redirected to /dev/null; see ~/.claude/skills/partials/tests/run.sh` (benign path, informed by LESSON-440 via REQ-595 BR-4).
- [ ] In both `wrapup/SKILL.md` and `bugfix/SKILL.md`, the `adlc_lesson_check` fence appears textually after the instruction that writes the lesson file and before the `adlc_recheck_id` fence, and the repair-loop text names the retry bound (2) and the `NO_ENTRY: schema check failed — <field>` fallback.
- [ ] `grep -rn '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' partials/lesson-check.sh wrapup/SKILL.md bugfix/SKILL.md` finds no ship-date cutoff literal introduced by this REQ.
- [ ] The four BR-4 rules appear, in order, in all three prompt sites (the `/wrapup` delegated question, the `/wrapup` fallback bullets, the `/bugfix` Step 4 text); a `diff` of the rule text between the two skills is empty.
- [ ] The new harness is listed in `partials/tests/run.sh`'s harness list, the test prints its executed-case count, and the count is non-zero under bash, zsh, sh and dash (`run.sh` itself prints no file count — LESSON-019: a green that scanned nothing is worse than a red).
- [ ] Running `/wrapup` on a REQ whose session produced nothing transferable ends with `### Lessons captured` containing one `NO_ENTRY: …` line and writes no `LESSON-*` file (manual dogfood).
- [ ] Running `/wrapup` on a REQ that did produce a lesson writes a file carrying `kind`, `evidence` with a citation token, and `confidence`; the summary slot lists it (manual dogfood).
- [ ] `/review` on a diff matching a `confidence: low` lesson reports the match without escalating; on a lesson named in another's `supersedes`, likewise with the superseded annotation; on a legacy lesson with no `confidence` it escalates as today.
- [ ] `/spec` Step 1.6's retrieval summary annotates a superseded lesson `(superseded by LESSON-yyy)` and its score is unchanged.
- [ ] On a fixture consumer repo with a stale vendored `lesson-template.md`, `/template-drift` reports the template `stale`.
- [ ] `.adlc/context/architecture.md` names the six fields and the `NO_ENTRY` contract.
- [ ] `tools/lint-skills` passes (no `cross-fence-fn`, `unguarded-source` or `sync-surface-parity` findings from the new partial and prompt edits).

## External Dependencies

- None. (`adlc-read` is already optional via the delegate gate.)

## Assumptions

- The `kind` dichotomy (`process` | `domain`) is sufficient for this epoch; a third value can be added to the enum additively. Harness² found scoping its two editors worth +2.9/+3.7 points, which is the reason to introduce the split now rather than after a routing consumer exists.
- `evidence` is a single free-form string, not a structured object — JSON-lines telemetry constraints do not apply to lesson frontmatter, and a string keeps the delegate draft and the human edit path simple. The citation-token check is the structural floor; it does not prove the citation is *relevant*, only that one exists.
- The capture steps in `/wrapup` and `/bugfix` are the only writers of `LESSON-*` files; a lesson hand-written by a human outside those steps is not validated by this REQ (it would be caught only if a later REQ runs `adlc_lesson_check` over the corpus).
- The repair loop's bound of 2 is enough: the check names the field, and frontmatter repair is a one-line edit. If two repairs do not fix it, the draft is malformed in a way the drafter cannot see, and `NO_ENTRY` is the honest outcome.

## Open Questions

- [ ] Should `/spec` Step 1.6 eventually weight `confidence`, or skip lessons named in a `supersedes`? Deferred until the corpus carries the fields (BR-7).
- [ ] Should `enforcement: none` lessons older than N days be surfaced by `/analyze` as an "honor-system backlog" finding? This is item D in the research note and belongs with the always-on-budget lint, not here.
- [ ] Should `enforcement:` also exist on bug files? Most `tools/lint-skills` checks were distilled from REQs and bugs, not lessons (research note §2, corrected), so a lessons-only field leaves those unlinked.

## Out of Scope

- Backfilling the six fields onto existing lessons (REQ-262 established lessons as insert-only history; a backfill would be guessing `evidence` after the fact).
- Changing `/spec` retrieval scoring (BR-7).
- Readers for `enforcement` and `generalizes` (research note item D; a consolidation pass).
- A per-edit verdict ledger (`helped | hurt | confounded`) across candidate harness edits — Harness²'s task-level loop; the `/harness-reflect` follow-up (research note item E).
- Deduplication or consolidation of overlapping lessons; `generalizes`/`supersedes` links are the cheap version.
- Redaction of secrets in the four prose sections — pre-existing exposure, same as today; BR-13 covers only the fields this REQ adds.
- Lesson *retrieval* inside `/proceed` phases and the workflow engine — REQ-647.
- Per-run outcome telemetry and recurrence counting — REQ-648.

## Retrieved Context

- LESSON-571 (lesson, score 10): A retrieval filter is half of a read/write contract with whatever writes the field it filters on
- BUG-194 (bug, score 10): /spec Step 1.6 spec-corpus status filter admits no status the pipeline ever writes
- REQ-262 (spec, score 9): Backfill tag frontmatter across 4 consumer repos
- REQ-258 (spec, score 9): Unified Tag-Based Retrieval for /spec (Pilot)
- LESSON-604 (lesson, score 7): A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time
- REQ-594 (spec, score 7): Spec intake: turn raw human input into a draft REQ plus an explicit gap list
- LESSON-313 (lesson, score 7): A global counter's namespace is its bootstrap scan root
- REQ-473 (spec, score 7): Global cross-repo LESSON-ID counter
- REQ-610 (spec, score 6): Guard the two-level partial-sourcing pattern
- REQ-603 (spec, score 6): Single-source the delegation authorization arms
- REQ-593 (spec, score 6): Incident→REQ backlink
- LESSON-572 (lesson, score 6): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 6): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion
- LESSON-441 (lesson, score 6): Repo-local-first sourcing means a canonical partial fix is not deployed until every vendored copy re-syncs
- REQ-483 (spec, score 6): Hard ordering enforcement for concurrent ADLC REQs
