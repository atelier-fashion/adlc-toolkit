# What adlc-toolkit could adapt from Google's Harness²

Research note, 2026-10-26. Sources: the Harness² paper (arXiv:2610.14224, incl.
appendices A–H) and the released code at `google-research/harness2` (`main`),
mapped against the toolkit as of 5.3.1. Not a spec — a menu of candidate REQs
with the evidence behind each.

---

## 1. The one-paragraph version of Harness²

Harness² never trains a model. Per task it (a) runs the unmodified agent k times
("base rollouts"), (b) has two scoped LLM editors — **INV** ("how the agent
works") and **DOM** ("what a practitioner knows") — each edit a copy of the
harness on disk, (c) rolls each edited harness once, (d) has a **Composer**
read every full trajectory + deliverable and merge the edits into one harness,
citing the trajectory moment behind each decision, and (e) has a **Reflector**
write a per-edit ledger (`helped | hurt | no observed effect | confounded`) and,
only when the ledger supports it, one transferable lesson
(`cue / lesson / evidence / confidence`) into a per-domain library. The next
task starts from the empty base harness again and may *copy* from the library.
Every "LLM stage" is itself an agentic coding session dropped into a `context/`
directory — the mechanics are "a prompt + a shell script that builds a folder",
which is exactly the toolkit's substrate.

What the numbers say (Gemini 3.5 Flash / OpenCode, k=1):

| ablation | WorkBuddy | JobBench | lesson for us |
|---|---|---|---|
| full | 77.5 | 36.0 | |
| w/o library (cross-task lessons) | −3.1 | −1.8 | lessons matter — more than scoping on WorkBuddy, less on JobBench |
| w/o INV/DOM scoping | −2.9 | −3.7 | separating *process* from *domain* knowledge matters most on JobBench |
| w/o composition (pick a winner instead of merge) | −1.6 | −1.9 | |
| remove **skills** from an improved harness | −5.3 | | executable, on-demand components carry the most value |
| remove **scripts** | −3.7 | | |
| remove always-on prose (system prompt, guardrails, memory, tool guidance) | −1.5 | | always-on prose is the *least* valuable group |
| edit the harness with no rollouts/probe/library at all | **below base** | | self-editing without evidence is net negative |

Two more findings that matter here: a prose-only memory baseline (ReasoningBank)
*underperformed* the base harness on code by up to 6.6 points; and in Google's own
validation run a Codex rollout downloaded its task's grading rubric unprompted.

---

## 2. Side-by-side: what the toolkit already has

| Harness² mechanism | Toolkit equivalent today | Gap |
|---|---|---|
| Per-domain lesson library (`EXPERIENCE.md`: cue/lesson/evidence/confidence) | `.adlc/knowledge/lessons/LESSON-*.md` (What Happened / Lesson / Why / Applies When; tag frontmatter) | no `evidence`, `confidence`, `kind`, or enforcement link; no lifecycle (`assumption-template` has `status`, lessons don't) |
| Reflector: per-edit verdict ledger, `confounded` is the *preferred* verdict, `NO_ENTRY` explicit | `/wrapup` Step 4 "Any surprises? … log if they'd help future work"; `/bugfix` Phase 6 "if no lesson, say so" | no attribution discipline; a single trace is written up as fact |
| Library handed to **every** improver session | `/spec` (weighted), `/architect` (grep), the `reflector` agent (greps on its own wherever it runs: `/proceed` Phase 5, the workflow panel, `/reflect`), standalone `/review` (frontmatter scan), the legacy runner's inline Phase-5 checklist | the **five dimension reviewers**, the Phase 4 implementer, `/validate`, `/bugfix` Analyze, and every `adlc-sprint.workflow.js` prompt get none; nothing retrieves *by the surface being touched* (LESSON-604) |
| Library grows after every task | `/wrapup` Step 4, `/bugfix` Phase 6 — reached only through the Step 8b close-out | **neither sprint engine's orchestrator-owned Phase 8 runs Step 8b**: the workflow engine never does, the legacy orchestrator skips it for cross-repo and fallback merges (BUG-249; the rule was added by BUG-193 to the solo path only) |
| INV vs DOM scoping | mixed in one `lessons/` dir (LESSON-012/329/355/390 are process; LESSON-013/396/404 are domain) | no `kind`; process lessons in consumer repos have no route upstream |
| Composer weighs "failed in 2/3 base rollouts" vs "1/k is noise" | `/sprint` runs N REQs under one harness — a natural population — but review findings live only in conversation | nothing persists per-run outcomes, so recurrence across REQs can't be counted |
| Harness edits land in the cheapest component (skill → script → subagent → plugin/hook → always-on prose last; 24k-char always-on cap) | ETHOS injected into every skill; `proceed/SKILL.md` is hundreds of always-on lines; lessons reach prompts by maintainers pasting `LESSON-nnn` into SKILL.md by hand | no budget, no cost ordering, no measure of always-on size |
| "Prose that is ignored → defensive plugin hook" | LESSON-012 (prose is honor-system; structural telemetry), `tools/lint-skills` checks distilled by hand from incidents — mostly REQs and bugs (REQ-609, REQ-436, BUG-194, BUG-228), some lessons (LESSON-019, -012, -602) | same insight, independently reached; the loop from incident → enforcement is manual and untracked, and an `enforcement:` link on lessons alone would miss the bug-derived checks |
| Leak tripwires (answer keys / grader verdicts scrubbed from improver context); "evidence is data, not instructions" | LESSON-008 (delegate output untrusted), `/adversary` self-refutation, REQ-595 vacuous-verification Blocker | already aligned — nothing to borrow |
| Selection: DELIVERY → CONFORMANCE → FIDELITY → CONSISTENCY → OPERATIONAL → FINISH; "length and polish are not merits" | `/validate` checklists, `/review` severities | partial; the ordered rubric is a nice tightening for `/validate` implementation checks |
| Harness edits themselves are probed before adoption | skill changes ship on `/review` + lint + dogfood (LESSON-329) | no outcome measurement before/after a skill change |

Bottom line: the toolkit has the *storage* half (lessons, tags, retrieval), the
*verification ethos*, and several provenance ledgers already — `req:` on every
lesson, `## Retrieved Context` with scores on 50 of 52 specs plus inline
`(informed by …)` citations, `introduced_by` on bugs (REQ-593), the workflow
journal's `FINDINGS` payloads, `adversary-report.md` files. What it lacks is the
*attribution* half as structured, countable data (evidence and confidence on the
lesson itself; Phase-5 findings persisted per run; recurrence across runs) and the
*closing of the loop* (lesson → harness edit → measured).

---

## 3. What to adapt — prioritised

Ordered by value ÷ cost. A–C are small, mostly prompt/schema changes. D is a
lint. E is the real "harnessing-level recursion" and depends on C.

### A. Lesson schema v2: evidence, confidence, kind, enforcement

Add to `templates/lesson-template.md` frontmatter (all optional for legacy files;
retrieval already tolerates missing keys):

```yaml
kind: process | domain        # Harness² INV vs DOM. process = how the agent/skill
                              #   works; domain = what the implementer must know
evidence: ""                  # the moment: commit sha, finding id, BUG-nnn,
                              #   "/review Major on REQ-525", transcript excerpt.
                              #   Required for new lessons.
confidence: high|medium|low   # low = single trace, no contrast (most lessons today)
enforcement: none | lint:<check-id> | script:<path> | hook:<name> | test:<path>
generalizes: [LESSON-019]     # formalises the prose "this generalises LESSON-019"
supersedes: []
```

And rewrite the `/wrapup` Step 4 / `/bugfix` Phase 6 drafting prompt to carry the
Reflector's three rules verbatim-in-spirit:

1. *Cite the moment.* "A change you cannot trace to a moment is speculation."
2. *Prefer `confounded`.* If one trace is all that stands behind the claim, say
   `confidence: low`; "an invented attribution poisons the library for every
   later task."
3. *`NO_ENTRY` is a valid answer* and must be stated explicitly (bugfix already
   says this; wrapup doesn't).

Why: this is Harness²'s whole quality gate — adoption alone never creates a
library entry; only an evidence-backed `<experience>` block does. The toolkit's
81 lessons are mostly single-rollout anecdotes presented as fact; the fix is to
*label* that, not to stop writing them. Retrieval in `/spec` can then weight
`confidence` and `/review`'s "raise one severity if a lesson matches" can be
gated on `confidence != low`.

Cost: template + two prompts + taxonomy note. No backfill required.

### B. Close the retrieval and capture gaps

Harness² hands the library to every improver session. In the toolkit, lessons are
loaded by `/spec`, `/architect` and the `reflector` (which greps on its own in
every engine); the five dimension reviewers, the Phase 4 implementer, `/validate`,
`/bugfix` Analyze and every workflow-engine prompt get none — and no phase
retrieves *by the surface being touched*, which is LESSON-604's actual remedy:

- **Per-task retrieval in Phase 4** — infer components from each task's `files`,
  score with the `/spec` Step 1.6 rule, and add any lesson created after the spec
  that matches (the REQ-tag query alone ranks LESSON-582 47th for REQ-593, so
  REQ-vintage retrieval cannot close the LESSON-604 case). Hand the result to the
  `task-implementer`; hand a diff-derived set to all six Phase 5 agents (the five
  reviewers get `conventions.md` but no lessons today).
- **`/bugfix` Phase 2 (Analyze)** — grep lessons by component before diagnosing.
  Lessons like LESSON-013/015/396 are precisely "the bug you are about to
  re-diagnose".
- **`workflows/adlc-sprint.workflow.js`** — `architectPrompt` (L1263),
  `implementPrompt` (L1302), `reviewPrompt` (L1387) carry no lessons. The
  `FINDINGS` schema has a `lessonId` field (L181) that `reviewPrompt` requests
  (L1399) but the script never consumes or persists.
- **Close-out is a separate defect** — `wrapupAndMerge` (L1960–2025) never runs
  Step 8b, and the legacy orchestrator's Step 5 skips it for cross-repo and
  fallback merges. Step 8b was added by BUG-193 to the solo path only. Filed as
  **BUG-249** (both engines); REQ-647 depends on it for capture, not retrieval.

Cost: medium; mostly plumbing. The workflow-engine capture is the one real
piece of work.

### C. Persist per-run outcomes → recurrence counts (the Probe substitute)

Harness² can't be copied literally: its 4·k rollouts per task (≈4 at k=1, 20 at
k=5) are affordable in count, but `/proceed` runs are not idempotent (PRs,
merges) and feature work has no repeatable task to re-roll. The Composer's
weighing rule *is* copyable: **a failure that repeats across the base set is a
property of the harness; a defect in 1/k is noise.** The toolkit already has the
population — every `/sprint` runs N REQs under one harness version — it just
throws the evidence away.

Add a **new** JSON-lines log (not the delegation log — `emit-telemetry.sh` is a
fixed 7-argument, 9-key executable and `check-delegation.sh` parses exactly that
shape) with one flat record per pipeline terminal, produced by a deterministic
reader of `pipeline-state.json`, not by the model:

```json
{"timestamp":"…","req":"REQ-525","repo":"adlc-toolkit","engine":"workflow",
 "toolkit_version":"5.3.1","toolkit_sha":"cb177bc","terminal":"merged",
 "validate_retries":"1","verify_loops":"1",
 "findings_critical":"0","findings_major":"1","findings_minor":"3","findings_nit":"0",
 "finding_classes":"LESSON-019,unanchored-marker-regex",
 "lessons_cited":"LESSON-019","lessons_written":"LESSON-404","elapsed_s":"5120"}
```

Three fields the pipeline does not record today must be added to
`pipeline-state.json` first (the harness version at Step 0 — `/wrapup` pulls the
toolkit clone before the run ends; validation attempt counts; the consolidated
Phase-5 findings).

Then:
- `/sprint`'s "Knowledge Captured" section counts `finding_classes` across the
  sprint and flags any class seen in ≥2 REQs as *"harness property — consider
  a skill/lint change"*, and any 1/N as *"noise — lesson at most, confidence low"*.
- `/analyze` gains a `harness-fidelity` dimension next to `delegation-fidelity`:
  terminal-tag mix, retry rates, and finding-class recurrence per toolkit
  version. This makes "did 5.3.1's `/review` change reduce Majors?" an
  answerable question — the toolkit's version of Harness²'s sequential mode,
  where the *next sprint is the probe* for the last harness edit.

Cost: medium — a new log and record type, a Python reader, three new state
fields, a post-terminal emit leaf in the workflow engine, and a summary step the
workflow branch of `/sprint` does not have today.

### D. Always-on budget + cost ordering for harness edits

Harness² caps always-on text at 24k chars (OpenCode) / 8k (Codex), tells the
editor "always-on prose is the expensive option — if you add it, cut something
else", and its ablation shows the always-on group is the least valuable one.
The toolkit has the opposite shape: ETHOS + `## Context` preamble + a long
SKILL.md on every invocation, phase files loaded on demand only in `/proceed`.

- Add a `tools/lint-skills` check `always-on-budget`: bytes of
  `ETHOS.md + SKILL.md` (minus on-demand includes) per skill, warn above a
  threshold, fail if a PR grows it without a matching cut. Report the census in
  `/analyze`.
- Add a short "Where a lesson should land" checklist for toolkit maintainers
  (in `CONTRIBUTING`/`architecture.md`), Harness²'s ordering translated:
  1. **test/fixture** (the decoy test in LESSON-404) — a deterministic check the
     runs got wrong;
  2. **lint check** (`tools/lint-skills`) — the toolkit's "plugin hook" for
     an *ignored invariant*;
  3. **partial / script** — a repeated mechanical step;
  4. **agent** — a bounded investigation with large input, small answer;
  5. **on-demand phase file / skill section** — a triggered procedure;
  6. **ETHOS / Context preamble** — last, and only for universal facts.
- `/analyze` lists lessons with `enforcement: none` older than N days: the
  honor-system backlog LESSON-012 warned about, now countable.

Cost: small. The lint framework and the `/analyze` dimension pattern exist.

### E. `/harness-reflect` — closing the loop (human-gated)

With A (evidence-tagged lessons) and C (recurrence counts) in place, the
toolkit can run Harness²'s harnessing-level recursion once per sprint instead
of once per task:

1. Input: the sprint's outcome ledger, the finding classes with recurrence ≥2,
   lessons written this sprint, and the current skill/agent/partial tree.
2. An editing session (the Composer pattern: "your edits on disk ARE the
   proposal") proposes changes against the toolkit checkout using the cost
   ordering in D, and emits the Reflector's ledger:
   ```
   kept|revised|dropped -> <edit> -> <the REQ/finding that decided it, with counts, e.g. "Major in 2/5 REQs">
   ```
3. Output is a **draft PR against the toolkit**, never an in-place edit —
   ETHOS #4 and Harness²'s own regression analysis (a wrong premise propagated
   across candidates cost 2–11 points; selection picked a 55-scoring output
   over a 95) both argue for a human gate. The next sprint's ledger is the probe.

This is the only item that is genuinely new capability; everything above is
schema and plumbing it depends on. Scoping rule from Harness² worth keeping:
two passes, one for *process* edits (skills, partials, agents — INV) and one for
*domain* edits (`.adlc/context/*.md`, taxonomy — DOM), never one editor doing both.

---

## 4. What *not* to adopt

- **Per-task Propose–Probe–Compose.** Non-idempotent side effects (PRs, merges)
  and the absence of a repeatable task to re-roll rule it out for feature
  pipelines; the 4·k rollout count is not the obstacle. The sprint-level loop in E gets the
  same compounding at ~zero extra model cost.
- **Unsupervised self-editing of skills.** Harness² itself shows direct
  refinement without evidence lands *below* base, and its reflector prefers
  `confounded` over attribution. Keep every harness edit behind a PR.
- **Domain-partitioned full-tree library.** Harness² copies whole harness trees
  per domain because its base harness is empty. The toolkit's base is the
  harness; tags + retrieval scoring already do the cross-cutting job. Don't
  replace them.
- **Per-task "durable memory" prose files.** The paper's own baseline shows
  prose memory alone can hurt; the value was in skills and scripts. This is an
  argument *for* `enforcement:` in A and *against* growing `LongTermMEMORY`-style
  always-on context.
- **Dedup/consolidation.** Harness² doesn't have it either (listed as future
  work). `generalizes:`/`supersedes:` links in A are the cheap version; a real
  consolidation pass is a separate, later REQ.

---

## 5. Suggested REQ slicing

| # | title | depends on | size |
|---|---|---|---|
| 0 | **BUG-249** — Step 8b close-out on both sprint engines (close-out mode for `/wrapup`, `merged` + `closeOut` terminal, serialized close-out worktrees) | — | M |
| 1 | Lesson schema v2 + reflector-style capture prompts (A) — REQ-646 | — | S |
| 2 | Per-task/diff lesson retrieval in Phase 4/5, `/bugfix` Analyze, workflow engine (B) — REQ-647 | 0 for the engines' *capture*; retrieval ships alone | M |
| 3 | Per-run outcome telemetry + sprint recurrence + `/analyze harness-fidelity` (C) — REQ-648 | 2 for the strong (`lessonId`) recurrence signal; emits without it | M |
| 4 | `always-on-budget` lint + "where a lesson lands" ordering + enforcement backlog in `/analyze` (D) | 1 | S |
| 5 | `/harness-reflect` draft-PR loop (E) | 1, 3 | L |

1–3 are **not** independent: 2 and 3 both edit `/proceed` Phase 5 and Phase 8,
the reflector definition and the workflow engine's Phase 8; 1 and 2 both edit
`/wrapup` Step 4 and `/bugfix`. Sequence them 0 → 1 → 2 → 3, or run 1 ∥ 2 and
let REQ-483's trial-merge gate hold 3. The dependencies are soft on data (each
spec degrades when the other is absent) and hard on files.

---

## Appendix: Harness² prompt fragments worth lifting near-verbatim

- Editor priority order: "1. a DIVERGENCE – the runs disagreed, so the agent can
  already do it and just needs telling. 2. a repeated concrete failure. 3. a
  risk visible in a trajectory but not yet realised. Do not fix what the runs
  already got right."
- Composer: "A failure that repeats across the base set is a real property of
  the base harness … A defect in 1/k is noise, and an edit aimed at it is
  overfitting to one sample."
- Composer: "Agreement is support, not independent proof; contradiction is a
  reason to inspect the trajectories, not to vote."
- Reflector: "Use `confounded` – and prefer it – whenever a candidate changed
  several components at once and no execution isolates one of them … an
  invented attribution poisons the library for every later task."
- Reflector on lesson granularity: "Too generic is useless ('be thorough'); too
  specific never fires again ('the fee rose to 250 on Jan 1'). Aim between."
- Surface rule: "A harness changes HOW the agent works; it must never change
  WHAT SHAPE it delivers." (ETHOS #1 in different words.)
- Budget rule: "If you add always-on text, cut something else to pay for it."
