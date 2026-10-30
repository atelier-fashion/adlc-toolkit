# REQ-661 — Architecture

## Approach

Measured on `d2eadd7` (REQ-666's close-out; its skill text equals the AC-3 baseline
`7d3bf2c`): `proceed/SKILL.md` 764 lines, `spec/SKILL.md` 622, `template-drift/SKILL.md`
572, `wrapup/SKILL.md` 475, every other `SKILL.md` at or below 429. Three skills are
split; `wrapup` is not (Phase-1 amendment). Each split moves whole sections, or for
`/spec` whole numbered sub-steps, into companion files with their text unchanged, and
leaves a pointer at the old position. `tools/lint-skills` learns the skill unit
(`SKILL.md` plus its companions), walks every companion with the per-file checks,
resolves the cross-fence checks and `canonical-helper` across the unit, gains
`skill-line-budget` and `companion-templating`, and makes every per-root site list
follow its content.

| Skill | Before | Moves | Companion | After (approx.) |
|---|---|---|---|---|
| `proceed` | 764 | `## Pipeline State Tracking` (117), `## Run-outcome telemetry (REQ-648)` (75), `### Step 0` (150) | `proceed/phases-state.md`, `proceed/phases-telemetry.md`, `proceed/phase-0-setup.md` | ~431 |
| `spec` | 622 | Step 1.4 step 3 (87), Step 1.6 sub-step 7 (79) | `spec/references/intake-source-read.md`, `spec/references/retrieval-body-read.md` | ~462 |
| `template-drift` | 572 | `### Step 5` (74), `### Step 6` (74) | `template-drift/references/drift-report.md`, `template-drift/references/reconciliation.md` | ~430 |

What stays put, and why, is the load-bearing part of this design: every location below
is read by a harness this REQ may not edit (BR-11: `partials/`, `workflows/`,
`templates/`), by `space/build.mjs`, or by BR-6.

- `/spec` Step 1.4 steps 1–2 hold the two `'<request>'` fences (BR-6). Steps 4–5 hold the
  `<!-- intake-gap-rules -->` block `space/build.mjs` reads from `spec/SKILL.md`.
- `/spec` Step 1.6 sub-steps 3 (the five scoring lines), 7a (the `LC_ALL=C find` lookup)
  and 8 (`superseded by LESSON-`), and Step 3, are read from `spec/SKILL.md` by
  `partials/tests/lesson-check.test.sh`. Sub-step 1 holds the `spec-exclude` block.
- `/template-drift` Step 0a is extracted from `template-drift/SKILL.md` by
  `partials/tests/plugin-route.test.sh` and `tools/adlc/tests/e2e/plugin-sandbox.sh`; its
  `<!-- sync-surfaces -->` block is BR-11's; Step 0 is a `branches.integration` resolution
  site and carries the repo-name line `test_skill_text_portability` pins; Step 3f's fence
  is extracted by the same test.
- `/proceed` Phase 5 stays inline (OQ-1). `proceed/phases-lite.md` keeps its path:
  `partials/lane-check.md` and `tools/adlc/lane_check.py` name it.

## ADR-1: The split set is re-measured, and `wrapup` is not split (BR-1)

The spec's figures were the 2026-10-27 tree's. REQ-647/648/669/666 pushed `proceed` to
764 and `template-drift` to 572, and BUG-253 brought `wrapup` to 475. BR-2 has one
threshold and no allowlist, so `template-drift` must come under 500 or AC-1 fails; the
Out-of-Scope exclusion was conditioned on it being inside the budget. `wrapup` already
meets BR-1, and moving Step 4 would be the largest lint change in the REQ for no budget
gain. Its rules still bind: the lesson checks are made unit-aware (ADR-9) and tested on
a `wrapup/references/` fixture, so a later split of `wrapup` is covered. **OQ-2** is moot.

## ADR-2: `/proceed` keeps its `phase*.md` layout (BR-12) and moves three whole sections

`references/` would mean moving `proceed/phases-lite.md`, which `partials/lane-check.md`
names (BR-11 forbids that edit) and `tools/adlc/lane_check.py` blocks by path. So the new
companions follow the existing glob: `proceed/phase-0-setup.md` (Step 0),
`proceed/phases-state.md` (Pipeline State Tracking) and `proceed/phases-telemetry.md`
(Run-outcome telemetry). All three keep their `##`/`###` heading as a stub in `SKILL.md`,
so every "Step 0", "**Gate**" and "**Run-outcome telemetry** R*n*" reference in the skill
still lands on a heading, and the stub sends the agent to the file.

**OQ-1 — Phase 5 stays inline**, as proposed: REQ-416 ADR-3 is not reopened (Out of Scope),
and the budget is met without it.

**OQ-3 — the three summary companions are not promoted.** Recorded alternative: promotion
deletes about 125 lines of summary text (a rewrite, which BR-3 and Out of Scope exclude),
and `tools/lint-skills/tests/test_lite_lane_contract.py` pins two of those summary lines
in `SKILL.md`. Three pure moves clear the budget with ~70 lines to spare. After this REQ
`/proceed` has two contracts, both recorded in `architecture.md` (ADR-5): the three
`<!-- companion: … -->` summaries stay as they are, and the three new files plus
`phases-lite.md` (which `SKILL.md` already tells the agent to run) are read-and-follow.

## ADR-3: `/spec` moves two whole numbered sub-steps (BR-5's sub-step form)

Neither Step 1.4 nor Step 1.6 can move whole (see Approach), and the whole steps that
could (1.5, 1.7, 2, 4: 90 lines) do not clear the budget. The two sub-steps that move are
the two delegated reads, each a self-contained block from the telemetry-flag create to
the `_adlc_emit_step_telemetry` emit, with its stderr lines and its post-validation
rules: Step 1.4 step 3 (`spec/references/intake-source-read.md`) and Step 1.6 sub-step 7
(`spec/references/retrieval-body-read.md`). Neither consumes the argument: step 3 reads
the literals step 2 echoed. The moved lines keep their list indentation byte for byte, so
every fence body is identical. Step 1.4 step 3 runs only when intake activates, which is
the progressive disclosure the Agent Skills layout exists for.

Known gap, outside this REQ: `partials/tests/source-guard.test.sh` walks `*/SKILL.md`,
`agents/*.md` and `proceed/phase*.md`, so its per-fence corpus run (section 7) no longer
executes the four moved `/spec` fences. Every sourcing *line* they carry still occurs in
a walked file, so cases (a)–(c) still cover the spellings. Widening that walk is a
`partials/` change (BR-11); it is a follow-up.

## ADR-4: `/template-drift` moves Steps 5 and 6

Step 5 (the report) and Step 6 (the reconciliation actions) are the two largest steps
that no harness reads from `template-drift/SKILL.md` and that hold no comparison fence:
`template-drift/references/drift-report.md` and `template-drift/references/reconciliation.md`.
Steps 0a, 0, 1–3f, 4 and 7, the `<!-- sync-surfaces -->` block, and every comparison
fence stay, so `/template-drift` compares exactly what it did (BR-11).

## ADR-5: The pointer contract (BR-4)

A stub is the original heading (for `/spec`, the sub-step's numbered title line) followed
by one sentence of this form:

> Read `<companion path>` and follow it before you continue. <What it holds, in one
> clause.> Nothing in this file replaces it.

The clause names what the file holds; it is not a summary that can be executed. No new
HTML marker is added: AC-3 compares the `<!-- companion: … -->` markers by count, and
the sentence is what AC-4's grep finds. Each companion opens with a `parent:` frontmatter
line (the shape the phase files already use) and a "Companion to …" paragraph naming the
step it belongs to and where the agent returns. A contract test asserts every companion
is named by its `SKILL.md` with the sentence, so an orphaned companion fails (LESSON-012).

## ADR-6: The skill unit and the companion walk (BR-7, BR-9, BR-12)

`find_skill_units(root)` is derived from `find_skill_files(root)`, so a companion is
walked exactly when its `SKILL.md` is, with the same pruning (`SKIP_DIR_PARTS`, the
root-relative rule, the symlink-escape guard, and whatever a concurrent fix adds to
`find_skill_files` for nested `.claude/worktrees/`). A unit's companions are
`<skill>/references/*.md`, plus `phase*.md` beside `SKILL.md` for the root's `proceed/`.
`<root>/proceed/phase*.md` stays walked when the root has no `proceed/SKILL.md` (the
existing fixtures stage phase files alone), as a unit with no `SKILL.md`. Nesting below
`references/` is not walked (BR-12 forbids it).

In `run()`, each companion gets every per-file check a `SKILL.md` gets: `sentinel`,
`balance`, `posix-fence`, `arg-templating`, `forge-direct-gh`, `read-bin-fallback`,
`unguarded-source`, `toolkit-root-line`, `dispatch-has-fallback`; the unit-scoped
`canonical-helper`, `cross-fence-fn`, `cross-fence-var` and lesson checks (ADR-7, ADR-9);
and `companion-templating` (ADR-8). `skill-line-budget` reads `SKILL.md` only. `scanned`
still counts `SKILL.md` only (BR-9).

`partials/*.md` keeps its three checks (`unguarded-source`, `toolkit-root-line`,
`dispatch-has-fallback`) — the spec's open assumption. Those files are documentation the
Skill loader never templates, the widened checks report false positives on them today
(`arg-templating` on `emit-step-telemetry.md`'s `$1` examples, `canonical-helper` on
`delegate-gate.md`), and BR-11 forbids editing them.

The per-root checks reach companions through the same helper: `ethos-line` walks each
plugin-root skill's companions in companion mode (ADR-8), `skills-ref` stages the
companions beside the `SKILL.md` it validates, and `TOOLKIT_PATH_SURFACES` (and so
`BUILTIN_COLLISION_SURFACES`) gains `*/references/*.md`, read through the same helper.
`tools/adlc/tests/e2e/plugin-sandbox.sh`'s `SHIPPED` list gains it too, so the lint and
that audit keep agreeing. `description-budget` has nothing to read in a companion.

## ADR-7: Unit scope for `cross-fence-fn`, `cross-fence-var` and `canonical-helper` (BR-8)

The fences of every file in a unit are numbered in one sequence (`SKILL.md` first, then
the companions in walk order). A function defined in one fence and invoked only in
others, or a non-exported variable read in a fence that does not assign it while another
fence of the unit does, is a finding, as it is within one file today. A within-file case
is reported exactly as before (same file, line and message). A cross-file case is
reported at the call or read site, and its message names the defining file and line.
`canonical-helper` fires when any file of the unit carries the gate anchor, and a literal
anywhere in the unit — or in the telemetry partial when any file of the unit sources it —
satisfies it; the finding goes on the first file carrying the anchor.

## ADR-8: The two new checks

**`skill-line-budget`** (BR-2): `SKILL_LINE_BUDGET = 500`; the count is the newline count
(`wc -l`); a `SKILL.md` at 500 or more is one finding at line 1 naming the count and the
budget. It is not a `skills-ref` check surfaced through `check.py`: the reference
validator checks frontmatter (name, description, allowed fields), not body length, and it
is optional — `check_skills_ref` SKIPs when it is not on `PATH`, as on this machine — so
the budget must be a count of its own or it would be enforced nowhere here. (The claim
about the validator's rules is from its published description; it is not installed here.)

**`companion-templating`** (BR-6): `ARGUMENT_PLACEHOLDERS = ("<request>", "<req-ids>")`,
the two tokens REQ-666 ADR-1 fixed (`/spec` Step 1.4 and `/manifest`), matched as literal
substrings anywhere in a companion, fence or prose; and `INLINE_BANG_RE` on any line
outside a fence. `test_skill_text_portability.py` reads the placeholder from the constant.
`ethos-line` in companion mode reports an ETHOS line (it belongs to `SKILL.md` only), a
near-ETHOS line and any other inline bang command, and never "no ETHOS line".

## ADR-9: Per-root site lists follow the content (BR-10)

- **`retrieval-status-parity`**: `LIFECYCLE_WRITE_SITES` replaces `proceed/SKILL.md` with
  `proceed/phase-0-setup.md`, where Step 0's `lifecycle-write` block now lives. A listed
  site that exists but has no block, while another file of its unit has one, is a finding
  naming that file and the constant. The gate stays `spec/SKILL.md`; when it lacks the
  `spec-exclude` block but a `spec` companion has it, the finding names the companion and
  `RETRIEVAL_READER_SITE` instead of degrading silently.
- **`lane-vocabulary`**: `LANE_SITES` gains the three new `proceed` files (already reached by
  its `proceed/phase*.md` glob), and every listed `<skill>/SKILL.md` also scans its unit's
  `references/` companions.
- **`lesson-rules-parity`**: armed when `wrapup/SKILL.md` and `bugfix/SKILL.md` both exist;
  a listed site that is missing is then a finding naming `LESSON_RULES_PARITY_SITES`, and a
  listed site whose unit holds the block in another file is a finding naming that file.
- **`lesson-check-order`, `lesson-question-coverage`**: gated on the unit's name
  (`wrapup`, `bugfix`), not the file's parent directory, and run on the unit's capture file
  — the first file of the unit holding a write point, either fence, or a rules block — with
  today's rules. Any of those constructs in a second file of the unit is
  `lesson-check-order: capture-step-split` (BR-5). With no construct anywhere, the
  `missing-*` findings go on `SKILL.md`, as today.
- **`sync-surface-parity`**: unchanged by construction.

## ADR-10: Equivalence evidence (BR-3, AC-3) and dogfood (BR-16)

A script extracts, per unit, on `7d3bf2c` and on the branch: every shell-fence body (the
info string and body lines byte for byte, list indentation included) as a sorted
multiset; every HTML-comment marker line, with `<!-- companion: … -->` compared by count;
and the set of stderr-line literals (each fence line that writes to `>&2`, and each
literal that prose tells the agent to emit to stderr). The PR body records the script
and its output. Dogfood executes the moved fences rather than reading them (LESSON-329):
the `/spec` gate, segment and moved step-3 fences on a sandbox repo with a file-path
argument and with a one-line request, the moved `/template-drift` fences, and the moved
`/proceed` Step 0 fences, under `sh` and `zsh`, comparing stderr and telemetry with the
same fences taken from `7d3bf2c`. A full `/spec` run is not used: Step 2 would burn a
real REQ id and push a reservation ref.

## ADR-11: OQ-4 — no CI job

Out of scope, as the orchestrator directed: the toolkit has no hosted CI. `skill-line-budget`
runs wherever `tools/lint-skills/check.sh` runs (`/analyze` Step 1.9, by hand).

## Task graph

```
TASK-187 lint: units, companion walk, unit scope, two new checks
   ├─► TASK-188 lint: per-root site lists follow the content
   │      └─► TASK-189 split /proceed
   ├─► TASK-190 split /spec
   └─► TASK-191 split /template-drift
TASK-189, TASK-190, TASK-191 ─► TASK-192 docs, cross-references, equivalence and dogfood
```

All tasks are in the one repo (`adlc-toolkit`).
