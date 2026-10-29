---
id: REQ-647
title: "Lessons reach every pipeline phase: per-task retrieval in /proceed Phase 4, the full Phase 5 panel, /bugfix Analyze, and the sprint workflow engine"
status: complete
deployable: true
created: 2026-10-26
updated: 2026-10-29
component: "adlc/proceed"
domain: "adlc"
stack: [markdown, javascript, bash, claude-skills]
concerns: [retrieval, knowledge-compounding, orchestration, process-compliance]
tags: [lessons, retrieval, workflow-engine, sprint, validate, bugfix, review, phase-5, knowledge-capture, harness2]
---

## Description

The toolkit retrieves lessons at spec time and architecture time and then mostly drops
them. `/spec` Step 1.6 runs the weighted retriever and freezes the result into
`## Retrieved Context`; `/architect` Step 1 greps lessons by component; the `reflector`
agent greps on its own wherever it runs (Phase 5 of `/proceed`, the workflow engine's
panel, `/reflect`); the legacy `pipeline-runner`'s inline Phase-5 checklist says "check
lessons for applicable pitfalls". Nothing else sees a lesson: the Phase 4
`task-implementer` receives the task file, `conventions.md` and `architecture.md` only
(`proceed/phase-4-implementation.md:46`); the **five dimension reviewers** in Phase 5
receive `conventions.md` but no lessons (`proceed/SKILL.md` Step A); `/validate` never
reads `.adlc/knowledge/`; `/bugfix` Phase 2 (Analyze) diagnoses from scratch; and the
`adlc-sprint.workflow.js` engine's `architectPrompt`, `implementPrompt` and
`reviewPrompt` carry no lessons — its `FINDINGS` schema has a `lessonId` field (L181)
that `reviewPrompt` *requests* (L1618) and that the BUG-249 close-out digest only prints
(L793): nothing escalates on it, and nothing checks it against a set the run retrieved.

The consequence is in the corpus. LESSON-604: a bash `case`-inside-`$()` pitfall was
captured one day after a spec froze its retrieval and was rediscovered during
implementation — and its remedy is "search **by surface**, not by spec vintage".
LESSON-390: three sprint runners re-derived the same draft-PR workaround in one sprint.
LESSON-330: the Phase-5 catch is *omitted* requirements, and the countermeasure is a
checklist in front of the reviewers — which lessons are. REQ-258 listed `/architect`,
`/bugfix` Phase 2 and `/review` integration as follow-ups that were never scheduled.

Harness² hands its lessons library to *every* improver session, and its ablation puts
the library at +1.8–3.1 points (research note §1). The toolkit already pays the capture
cost (ETHOS #2 "Knowledge Compounds"); this REQ makes the stored knowledge reach the
phases that act on it, retrieved **by the surface being touched** (per task, per diff),
not only by the REQ's tags.

The matching *capture* gap — neither sprint engine's orchestrator-owned Phase 8 ran the
Step 8b close-out, so lessons were never written on those paths — was **BUG-249**, fixed
on its own through `/bugfix` and merged on 2026-10-27 (#187). Both engines now capture.
This REQ does not touch close-out (BR-9).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| LessonQuery | `components` | string[] | one or more `component` values; the Step 1.6 `+3` fires when `doc.component ∈ components` |
| LessonQuery | `domain`, `stack`, `concerns`, `tags` | as `/spec` Step 1.6 | |
| LessonSet | `query` | LessonQuery | |
| LessonSet | `lessons` | array | entries `{id, title, path, score?, confidence?, kind?, newerThanSpec?: bool}`; `score` present when the set was scored, absent on a top-up entry |
| LessonSet | `cap` | integer | **step0: 10**, **task: 5 (+3 recency)**, **phase5: 15**, **bugfix: 5** |
| LessonSet | `retrievedAt` | timestamp | written when computed; **stale** ⇔ a lesson file newer than `retrievedAt` exists — used only by BR-10's log line |
| Loaded text | per lesson | string | frontmatter + `## Lesson` + `## Applies When`, **hard cap 40 lines** with a trailing `[… truncated — read LESSON-xxx for the rest]`; a lesson with no `## Lesson` section contributes its first body section instead (3 of 88 today); a lesson with no `## Applies When` contributes its title in its place (25 of 88) |
| pipeline-state.json | `lessons` | object | **optional, additive**: `{ step0: LessonSet, tasks: { "TASK-xxx": LessonSet }, phase5: LessonSet }`, written **to the primary repo path's copy** (`<repos[primary].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json`, the same target as Step 8b's terminal record) at the moment each set is computed; read by nothing for control flow (informed by LESSON-626, BUG-212; the worktree copy is deleted at teardown) |
| Workflow `LESSONS` schema | — | JSON-Schema literal | the retrieval leaf's output: `{query, lessons[], retrievedAt}`, closed (`additionalProperties:false`), `score` optional, `maxItems: 15`; a pure structural test validates a 15-entry unscored payload and a 10-entry scored one (informed by LESSON-331) |
| Acknowledgement | commit trailer / task block | string | a lesson is *acknowledged* by `Lessons: LESSON-xxx[, LESSON-yyy]` in a commit message, or by its id in the task's `## Verification` block |
| Phase-5 finding | `lesson-unacknowledged` | Info | `Applicable lesson not acknowledged: LESSON-xxx — <title>`; never blocks |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `lessons_loaded_step0` | `/proceed` Step 0 item 7 | LessonSet from REQ tags (background context) |
| `lessons_loaded_task` | Phase 4, before each task's implementer dispatch | per-task LessonSet from the task's `files` components + recency rule |
| `lessons_loaded_phase5` | `/proceed` Phase 5 before Step A | LessonSet from diff components |
| `lessons_handed_to_agent` | implementer dispatch; six-agent Phase-5 dispatch; workflow `architectPrompt`/`implementPrompt`/`reviewPrompt` | loaded text, with ids |
| `lesson_unacknowledged` | Phase 5 Step B consolidation | Info findings, ≤5 |

_Permissions: not applicable._

## Business Rules

- [ ] BR-1 (**Step-0 set — background**): `/proceed` Step 0 item 7 computes a LessonSet by running the `/spec` Step 1.6 scoring rule over `.adlc/knowledge/lessons/*.md` only, with the REQ's own frontmatter tags as the query. Top 10, score-0 dropped, same sort key. Recorded as `lessons.step0`. This set is *REQ-vintage* context; it is **not** the LESSON-604 mechanism (BR-1a is) — on the recorded LESSON-604 case (REQ-593 / LESSON-582) the REQ-tag query ranks LESSON-582 far outside the top 10 (47th of 79 when this spec was drafted), which is why a per-surface set exists. On resume, an existing `lessons.step0` is reused, not recomputed (informed by LESSON-604, REQ-258).
- [ ] BR-1a (**per-task sets — the LESSON-604 mechanism**): in Phase 4, before each task's implementer is dispatched, compute that task's LessonSet: infer `components` from the task's `files` paths with the `/review` Step 1.7a inference, each path contributing its most specific component **and that component's ancestors** short of a one-segment root (`partials/forge.sh` → `adlc/partials/forge`, `adlc/partials`; `tools/lint-skills/check.py` → `adlc/tools/lint-skills`, `adlc/tools`). The other query fields are the REQ's own frontmatter `domain`, `stack`, `concerns` and `tags`. Score with the Step 1.6 rule and take the top 5; then apply the **recency rule**: any lesson not already in the set whose `created` is later than the REQ spec's `created` and whose `component ∈ components` (or whose `domain` matches and `component` is a prefix of one of them) is added even if outside the top 5, up to 3 more, **most specific first** — a lesson whose `component` is some path's most specific component before one matched only through an ancestor or the prefix arm — and otherwise in the Step 1.6 sort order. Every member whose `created` is later than the spec's carries `newerThanSpec: true`, however it was admitted. Then add every `kind: process` lesson from the Step-0 set not already present (REQ-646; absent `kind` ⇒ none qualify, stated degrade), stopping at 15 members in all. Recorded as `lessons.tasks["TASK-xxx"]`. A `domain`-only match adds nothing on its own (72 of 88 toolkit lessons share `domain: adlc`, so domain is not a discriminator here). On today's corpus the specificity order is what keeps LESSON-582 in the set: several `adlc/partials` lessons newer than REQ-593 outscore it.
- [ ] BR-1b (**context budget**): for every LessonSet the loaded text per lesson is the frontmatter plus the `## Lesson` and `## Applies When` sections, **hard-capped at 40 lines** with the truncation marker (measured today: median 30, p90 47, max 66 lines uncapped), with the section fallbacks in the Entities table. Worst case per prompt: implementer ≤ 8 × 40 = 320 lines, plus 40 per `kind: process` lesson carried from the Step-0 set, never past 15 × 40 = 600; each Phase-5 agent ≤ 15 × 40 = 600 lines; the orchestrator's Step-0 load ≤ 400. An agent that cites a lesson may read the full file on demand. The Phase-5 set follows the same budget, overriding `/review` Step 1.7d's "read their bodies in full" for the in-pipeline case only; standalone `/review` is unchanged.
- [ ] BR-2 (**implementer**): Phase 4's `task-implementer` dispatch passes, in addition to the task file, `conventions.md`, `architecture.md` and the worktree path, the task's LessonSet loaded text. `agents/task-implementer.md` gains: "Read the supplied lessons before writing code. When one applies to a change you make, **acknowledge it**: add `Lessons: LESSON-xxx` as a commit-message trailer, or cite the id in the task's `## Verification` block." Acknowledgement lives where BR-4 looks — never only in the agent's report.
- [ ] BR-3 (**Phase-5 set**): Phase 5 computes a LessonSet from the diff: `components` from the changed paths via `/review` Step 1.7a, **scored with the Step 1.6 rule** (not 1.7b's inclusion filter), top 15, with 1.7c's top-up retained (fewer than 5 ⇒ add the most recently modified, unscored, until 10). Recorded as `lessons.phase5`. Its loaded text goes to **all six** Step A agents — the reflector's own grep (`agents/reflector.md:24`) is **replaced** by the supplied set, with the reflector told the set was pre-computed; the five reviewers receive it alongside `conventions.md` — in both main-conversation and subagent mode. `/review` Step 4's escalation rule (including REQ-646 BR-6's `low`/superseded exemptions, shipped) applies inside Phase 5 exactly as in standalone `/review` (informed by LESSON-330, LESSON-441 — one canonical matcher).
- [ ] BR-4 (**acknowledgement check — runs in Phase 5**): at Phase 5 Step B (consolidation), for each lesson in `lessons.phase5` that either has `component ∈ components` or carries `kind: process`, and whose id appears in no commit trailer on the branch and no task `## Verification` block, emit one **Info** finding `Applicable lesson not acknowledged: LESSON-xxx — <title>` — **at most 5**, highest score first, with a trailing `(+N more applicable lessons not listed)` line. `domain`- or `tags`-only matches are never reported. Info never blocks (REQ-595's epoch-1 posture). Standalone `/validate`, when a human invokes it on an implementation, runs the same check from `lessons.phase5` (or computes a Phase-5-style set from the diff); no pipeline invokes implementation-mode `/validate` today (`/proceed` calls `/validate` at Phases 1 and 3 only), and this REQ does not add one.
- [ ] BR-5 (**/bugfix Analyze**): `/bugfix` Phase 2 gains a first step: build a LessonQuery from the bug's frontmatter tags plus `components` inferred from the reproduction's file paths, score with the Step 1.6 rule, take the **top 5** under the BR-1b budget, and list them under `Prior lessons consulted:` before the root-cause analysis. (`/architect` Step 1's grep is `component`/`domain` only and uncapped; with `domain: adlc` on 72 of 88 lessons an uncapped grep reads the corpus.) This closes the `/bugfix Phase 2` follow-up REQ-258 named (informed by REQ-258 Out of Scope).
- [ ] BR-6 (**workflow engine**): because the script has no shell of its own (REQ-474), LessonSets are produced by a **retrieval leaf** dispatched (a) after Phase 0 for the Step-0 set, (b) after Phase 2 for every task's set in one call (task files exist then; Phase 4 is serial), and (c) before Phase 5 fan-out for the Phase-5 set, each validated against the `LESSONS` schema. The leaf is read-only except for one write: `lessons.<set>` into the primary-path state copy. `architectPrompt`, `implementPrompt` and `reviewPrompt` carry the loaded text. In Phase 5 the script applies the escalation rule in code: a finding's `lessonId` escalates **only if it is a member of the Phase-5 set's ids** (an agent-written id is untrusted — informed by LESSON-008); escalation runs **before** `dedupeAndRank`, and dedupe **unions** `lessonId` across duplicates rather than keeping the first. **Resume**: LessonSets are pinned to the run and replayed from the journal on `resumeFromRunId` — "the corpus as it is now" means at first computation; a replayed prompt must stay byte-identical (informed by REQ-474 BR-7, LESSON-331).
- [ ] BR-7: every `lessons.*` record is additive and optional: a state file without it parses and processes unchanged, `/status` treats absent as "none", nothing reads it for control flow. Written at the moment the set is computed, to the primary-path copy named in Entities (informed by LESSON-626, BUG-212, BUG-193).
- [ ] BR-8: solo `/proceed` and the legacy `pipeline-runner` gain BR-1–BR-5 with no other behaviour change; the runner's line "Check `.adlc/knowledge/lessons/` for applicable pitfalls" (`agents/pipeline-runner.md:75`) is replaced by "use the Step-0 and per-task LessonSets recorded in `pipeline-state.json.lessons`" (informed by REQ-263 BR-10).
- [ ] BR-9 (**BUG-249, resolved**): this REQ makes the workflow engine *retrieve* lessons (BR-6). *Capturing* them on the workflow engine and on the legacy orchestrator's merge paths is the Step 8b close-out BUG-249 added (#187, 2026-10-27), so those paths now retrieve, acknowledge and capture. This REQ changes no capture path, and the `knowledge capture: unavailable — BUG-249` notice an earlier draft planned for an unfixed BUG-249 is not added.
- [ ] BR-10: each phase's end-of-phase log names the lessons it loaded (`Lessons loaded (task TASK-012): LESSON-013, LESSON-335 [newer-than-spec: LESSON-582]`) and, when the set is stale per Entities, appends `(stale: N lessons newer than this set)` — a transcript then shows *which* lessons were read, not merely that retrieval ran (informed by LESSON-571, LESSON-604).
- [ ] BR-11: no new skill directory. Touches `proceed/SKILL.md`, `proceed/phase-4-implementation.md`, `validate/SKILL.md`, `bugfix/SKILL.md`, `agents/task-implementer.md`, `agents/reflector.md`, `agents/pipeline-runner.md`, `workflows/adlc-sprint.workflow.js` (+ `workflows/README.md`, `workflows/tests/`), and `.adlc/context/architecture.md` (the "Knowledge retrieval" paragraph), plus the sourced partial BR-12 requires and its harness and engine tests.
- [ ] BR-12: all shell is BSD- and zsh-safe and every shared function is a sourced partial re-sourced in the same fence (informed by LESSON-013, LESSON-020, LESSON-329, LESSON-335, REQ-610).

## Acceptance Criteria

- [ ] Running `/proceed` on a REQ whose tags match ≥1 lesson records `lessons.step0` in the **primary-path** state copy before Phase 1 starts, and the Step 0 log names it. (manual dogfood)
- [ ] **LESSON-604 reproduction**: with today's corpus, for the REQ-593 spec, the Step-0 set does *not* contain LESSON-582, and the per-task set for a task whose `files` include the partial LESSON-582 describes *does* contain it, flagged `newerThanSpec: true` when its `created` is later than REQ-593's. (scripted against the corpus; no agent)
- [ ] The Phase 4 implementer prompt for a task touching `partials/*.sh` contains the `## Lesson` and `## Applies When` sections of a lesson tagged `component: adlc/partials`, every `kind: process` lesson in the Step-0 set, and no `## What Happened` section. (manual dogfood)
- [ ] For every lesson in the corpus, the loaded text is ≤ 40 lines; LESSON-571 (124 lines) loads exactly 40 with the truncation marker; LESSON-013 (no `## Lesson` section) loads its first body section. (scripted)
- [ ] Phase 5's six-agent dispatch includes the Phase-5 set; the reflector's prompt says the set was pre-computed and the reflector performs no grep of its own. (manual dogfood)
- [ ] With 12 qualifying unacknowledged lessons in a fixture `lessons.phase5`, Phase 5 Step B emits exactly 5 Info findings plus `(+7 more applicable lessons not listed)`; a lesson matched only by `tags` is not among the 12; a lesson whose id appears in a `Lessons:` commit trailer is excluded. (pure-function test on the consolidation helper)
- [ ] `/bugfix` Phase 2 on a bug tagged `component: adlc/partials` lists ≤5 lessons under `Prior lessons consulted:` before the root-cause analysis. (manual dogfood)
- [ ] A 15-entry unscored `LESSONS` payload and a 10-entry scored one validate against the exported schema; a 16-entry payload and one with an unknown key are rejected. (pure structural test, `workflows/tests`)
- [ ] In pure-JS tests: a `FINDINGS` entry with `lessonId` outside the set ids is *not* escalated; one inside is escalated by one level; two duplicate findings where only the second carries `lessonId` dedupe to one finding that keeps the `lessonId` and the escalation.
- [ ] `agents/pipeline-runner.md` no longer contains "Check `.adlc/knowledge/lessons/` for applicable pitfalls" and does reference `pipeline-state.json.lessons`. (grep)
- [ ] A Phase-4 end-of-phase log for a task names the lessons loaded; with a lesson file touched after `retrievedAt`, the line carries `(stale: 1 lessons newer than this set)`. (manual dogfood)
- [ ] A state file with no `lessons` key is processed by `/status`, `/proceed` resume and both sprint engines without error. (benign path — scripted for `/status`, manual for the engines)
- [ ] `tools/lint-skills` passes; `workflows/tests` pass with collected > 0; `partials/tests/run.sh` lists any new harness and it reports executed cases > 0.

## External Dependencies

- None.

## Assumptions

- The Step 1.6 scoring rule is cheap enough to run at Step 0, once per task, and at Phase 5 (frontmatter-only, ≤30 lines per file). Selection — scoring, the recency rule, caps and loaded text — is deterministic over the corpus's frontmatter and sections, so it can be scripted (AC 2, AC 4, AC 6) and shared by every call site; the path → component inference stays model judgment, as in `/review` Step 1.7a. For the workflow engine it runs inside one leaf per call site.
- REQ-646 has shipped: the lesson schema carries `kind`, `confidence` and `supersedes`, but existing lessons were not backfilled (6 of 88 carry `kind`, 4 of them `process`). `kind: process` inclusion and the `confidence`/`supersedes` escalation exemptions degrade to "none qualify" / "today's behaviour" when the fields are absent.
- BUG-249 has shipped (BR-9), so no part of this REQ waits on it.
- The `Lessons:` commit trailer is a new convention, so acknowledgement starts at zero; BR-2's instruction to the implementer and BR-4's cap are what keep the Info findings from being noise while it is adopted.

## Open Questions

- [ ] Should BR-4's Info finding be promoted to Warning once the corpus carries REQ-646 `confidence`, so only `high` lessons warn? Defer with REQ-646's own open question.
- [ ] Should the recency rule in BR-1a also consider `updated` (a lesson revised after the spec), or only `created`? Default: `created` only — `updated` is bumped by tag backfills (REQ-262 BR-12) and would over-include.

## Out of Scope

- The Step 8b close-out on the sprint engines (knowledge capture, spec status, terminal record) — **BUG-249**, fixed through `/bugfix` for both engines.
- Changing what lessons *say* or how they are captured — REQ-646.
- Persisting Phase-5 findings and counting recurrence across a sprint — REQ-648.
- Lesson retrieval for `/analyze`, `/optimize`, `/canary`, `/manifest` (no implementation surface to apply them to).
- Changing `/spec` or `/architect` retrieval (already present; untouched).
- The lite lane (REQ-652): its Phase 4 fresh retrieval and its single `lite-reviewer` pass keep their own retrieval set, unchanged. A lite REQ has no task files, so BR-1a and BR-2 have nothing to attach to; after an escalation the run is on the full lane and gets every rule here.
- A pipeline call to implementation-mode `/validate` (none exists today; BR-4 runs in Phase 5 instead).
- A second retrieval implementation — every new call site references the `/spec` Step 1.6 rule by name; the only new code is the multi-component `+3` and the recency rule.

## Retrieved Context

- LESSON-626 (lesson, score 11): A rule written about one actor does not settle the case for another — bound machine conflict resolution to a checkable property
- BUG-207 (bug, score 11): The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint
- BUG-212 (bug, score 11): A conflict resolved during a pipeline run leaves no machine-readable trace
- LESSON-604 (lesson, score 11): A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time
- REQ-483 (spec, score 10): Hard ordering enforcement for concurrent ADLC REQs
- REQ-258 (spec, score 10): Unified Tag-Based Retrieval for /spec (Pilot)
- LESSON-571 (lesson, score 9): A retrieval filter is half of a read/write contract with whatever writes the field it filters on
- BUG-194 (bug, score 9): /spec Step 1.6 spec-corpus status filter admits no status the pipeline ever writes
- REQ-262 (spec, score 9): Backfill tag frontmatter across 4 consumer repos
- REQ-474 (spec, score 8): Re-platform /sprint orchestration onto Claude Code Dynamic Workflows
- REQ-594 (spec, score 7): Spec intake: turn raw human input into a draft REQ plus an explicit gap list
- LESSON-390 (lesson, score 7): Draft-PR-early cannot open on a zero-commit branch
- REQ-484 (spec, score 7): Cross-repo footprint publishing
- REQ-485 (spec, score 7): Auto-rebase and resume a blocked REQ after its blocker merges
- LESSON-330 (lesson, score 7): The Phase-5 review catches OMITTED requirements, not just bugs
