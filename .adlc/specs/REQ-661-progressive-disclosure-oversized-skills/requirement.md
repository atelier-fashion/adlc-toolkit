---
id: REQ-661
title: "Progressive disclosure for oversized skills: spec, proceed and template-drift SKILL.md under the 500-line budget, detail in a references/ layer the linter walks, and a budget check that stops regrowth"
status: complete
deployable: false
created: 2026-10-27
updated: 2026-10-29
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "python", "sh", "claude-skills"]
concerns: ["portability", "maintainability", "structural-enforcement", "developer-experience"]
tags: ["progressive-disclosure", "skill-md", "lint-skills", "proceed", "spec", "wrapup", "template-drift", "multi-harness", "references", "line-budget", "phase-removal", "harness-agnostic", "skill-design", "linter"]
lane: "full"
lane_reason: "footprint far above max_files (three SKILL.md files, new references files, tools/lint-skills/check.py, its tests and README, architecture.md, conventions.md) and it changes a validator: tools/lint-skills gains checks and widens every walk set"
lane_forced: false
---

## Description

This is Phase 1b of `.adlc/research/multi-harness-plan.md` (§2c, last bullet;
§3 P1), with REQ-654 (Phase 0, `ADLC_HOME` and the `~/.agents/skills` mount)
as the prior art for shape and posture. The Agent Skills specification that
Copilot CLI, Codex, Gemini CLI and Cursor all read keeps `SKILL.md` under 500
lines (and its body under roughly 5 000 tokens), with detail moved into a
`references/` directory one level deep that the agent reads when it reaches
the step that needs it. Three toolkit skills are over that line on the tree
REQ-666 left (`d2eadd7`): `spec/SKILL.md` at 622 lines, `proceed/SKILL.md` at
764 and `template-drift/SKILL.md` at 572. `wrapup/SKILL.md` is at 475 and is
not split here, but it is inside the budget the new check enforces.

> **Amended at `/proceed` Phase 1 (2026-10-29).** This spec was written against
> the 2026-10-27 tree, where the figures were `spec` 605, `proceed` 600, `wrapup`
> 561 and `template-drift` 477. REQ-647, REQ-648, REQ-669 and REQ-666 landed in
> between: `proceed` and `template-drift` grew past the budget, `wrapup` shrank
> under it. So the split set is now `spec`, `proceed` and `template-drift`, and
> `wrapup` is not split. BR-1 and BR-2 (one threshold, no allowlist) decide this:
> the Out of Scope exclusion of `template-drift` was conditioned on it being
> "inside the budget", and it no longer is. The rules that would have governed a
> `wrapup` split (BR-5's lesson-fence sentence, BR-10's lesson sites, AC-10)
> still hold, and the lint still has to apply them to a future
> `wrapup/references/` file.

The split is a **move, not a rewrite**. Every step, fence, marker block and
stderr line each skill carries today exists afterwards with identical text,
either still in `SKILL.md` or in a references file that `SKILL.md` tells the
agent to read at the point the step is reached. That is the difference from
`/proceed`'s existing companion files (`proceed/phase*.md`), whose marker is
documentation-only — `architecture.md` records that the inline summary is
"sufficient to execute each extracted phase". Content this REQ moves is
**load-bearing**: the `SKILL.md` pointer is an instruction to read and follow,
not a cross-reference, because on a harness that honours the spec the
references file is the only place the procedure lives.

Three facts found while grounding this REQ shape its rules, and none of them
is visible from the plan's one-line bullet:

1. **The existing phase files are mostly outside the linter.** Today
   `tools/lint-skills/check.py` walks `proceed/phase*.md` in exactly two
   places: `check_unguarded_source` (`find_phase_files`, REQ-610 ADR-3) and
   the `lane-vocabulary` glob. Every other per-file check — `sentinel`,
   `balance`, `canonical-helper`, `posix-fence`, `arg-templating`,
   `cross-fence-fn`, `cross-fence-var`, `forge-direct-gh`,
   `read-bin-fallback`, and the five REQ-666 adds (`skills-ref`,
   `dispatch-has-fallback`, `description-budget`, `no-harness-path`,
   `ethos-line`) — walks no phase file (`read-bin-fallback` also walks
   `agents/*.md` via `find_read_bin_extra_files`; the rest walk `SKILL.md`
   only). (Phase-1 correction: on `d2eadd7` `find_phase_files` also feeds
   `toolkit-root-line` and `dispatch-has-fallback`, REQ-669 ADR-6, and
   `no-harness-path` scans `proceed/phase*.md` as one of its per-root
   surfaces; none of the three reaches a `references/` file.)
   `proceed/phases-lite.md` already holds three shell fences that no
   cross-fence check has ever seen, and `proceed/phases-6-8-ship.md:41-48`
   holds one more (the Phase 6 PR-body fence). Moving
   two or three hundred more lines of fences into that kind of file without
   widening the walk would be the LESSON-019 shape: the guard stays green
   because the thing it guards moved out from under it.
2. **Several checks pin the three files by path or by directory name.**
   `RETRIEVAL_READER_SITE` is `spec/SKILL.md` (the `retrieval-status:
   spec-exclude` block at Step 1.6); `LIFECYCLE_WRITE_SITES` names
   `wrapup/SKILL.md` and `proceed/SKILL.md`; `LANE_SITES` names all three;
   `LESSON_RULES_PARITY_SITES` names `wrapup/SKILL.md` (with
   `bugfix/SKILL.md`); and the lesson checks gate on the file's **parent
   directory name** — `check_lesson_check_order` on it being `wrapup` or
   `bugfix` (`LESSON_CHECK_ORDER_SKILLS`), `check_lesson_question_coverage` on
   it being `wrapup` only — so a `wrapup/references/capture-knowledge.md` has
   parent `references` and both checks silently stop running. `/wrapup` Step 4 is 251 of the file's 475
   lines and carries every lesson-check site; the lifecycle-write block is in
   Step 3.
3. **Two kinds of Claude Code preprocessing happen only in `SKILL.md`.**
   After REQ-666 the body carries no `$ARGUMENTS`: the skill argument reaches
   the two `/spec` Step 1.4 intake fences and the `/sprint` fence as a
   placeholder the agent fills with a single-quoted literal (`'\''` escaping)
   under instruction from the surrounding `SKILL.md` prose, the loader still
   substitutes `$0`–`$9` (LESSON-335), and the ETHOS `` !`…` `` line is the
   one context macro left (every other `!` line is a run-and-read fence). A
   references file read with a file tool gets neither the prose that fills
   the placeholder nor the macro expansion. `spec/SKILL.md` Step 1.4 — the
   198-line block that is the obvious candidate to move — holds the two
   intake fences. Moved away from the prose that fills them, those fences
   would pass the placeholder (or nothing) to `adlc_intake_detect`, it would
   return 1, and intake would never activate again, with no error (the
   LESSON-012 silent-failure class, and the exact "no behaviour change" this
   REQ promises to keep).

So the deliverable is four things, all shipping together because each of the
last three exists to keep the first honest:

1. **The split.** `spec/SKILL.md`, `proceed/SKILL.md` and `template-drift/SKILL.md`
   each end under 500 lines, with moved content in `<skill>/references/*.md`
   (or, for `/proceed`, the existing `phase*.md` layer — one layout per
   skill) and an explicit read-and-follow instruction in `SKILL.md` at each
   moved step's boundary. Which sections move is an architecture decision;
   the budget arithmetic and the constraints that bound it are in the
   Assumptions and Open Questions.
2. **The walk sets follow the content.** Every per-file lint check walks a
   skill's references and phase files with the same rules it applies to
   `SKILL.md`; the two cross-fence checks and `canonical-helper` treat the
   skill unit (`SKILL.md` plus its companions) as one scope; every per-root
   site list and directory-name gate finds its marker block at the new
   location or fails loudly. The REQ-595 scanned count keeps counting
   `SKILL.md` only.
3. **Claude-only preprocessing stays in `SKILL.md`.** No references file
   carries the argument placeholder or a `` !`…` `` line, and a lint check
   says so.
4. **The budget is a lint check**, `skill-line-budget`, on every `SKILL.md`
   under the scan root, so none of the three files — nor `wrapup` at
   475 — can regrow past the line quietly.

`/template-drift` has no skills surface (skills are symlinked, never
vendored), so its comparisons are untouched by construction; the rule here is
that the split changes nothing it *does* compare. That holds for the split of
`template-drift/SKILL.md` itself: its `<!-- sync-surfaces: template-drift -->`
block and every comparison fence keep their text. (informed by REQ-610,
REQ-425, REQ-436, LESSON-020, LESSON-335)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SkillUnit | skill_md | path | `<skill>/SKILL.md`; frontmatter `name` and `description` unchanged by this REQ |
| SkillUnit | companions | list of paths | `<skill>/references/*.md` and, for `proceed`, `proceed/phase*.md`; exactly one level below the skill directory, no nesting; every lint walk sees the same set of companions, so the two file families cannot widen separately |
| SkillUnit | line_count | number | newline count of `SKILL.md` (`wc -l`); must be **below 500** |
| MovedSection | source | string | the `##`/`###` section of `SKILL.md` it came from, or one whole numbered sub-step of such a section, moved whole: a step's prose, its fences and its marker blocks stay together |
| MovedSection | pointer | string | the instruction left in `SKILL.md` at the step boundary: names the companion path and says to read it and follow it before continuing; never a summary the agent could execute instead |
| MovedSection | templating | boolean | `false` always: no argument placeholder, no bare `$<digit>` (`arg-templating` already covers this once BR-7 widens the walk), no `` !`…` `` line in a companion |
| LintCheck | `skill-line-budget` | per-file | fires on any `SKILL.md` whose line_count is 500 or more; message names the count and the budget; one threshold for every `SKILL.md`, no per-file exception |
| LintCheck | `companion-templating` | per-file (companions only) | fires on the argument placeholder REQ-666 BR-1 leaves in `SKILL.md` or on a `` !`…` `` macro line in a companion file |
| LintCheck | existing per-file checks | per-file | a construct that is a finding in `SKILL.md` is the same finding in a companion (BR-7 states the companion rule for REQ-666's `ethos-line`, `description-budget` and `skills-ref`); a function, variable or canonical literal is resolved across the SkillUnit, not per file |
| LintCheck | per-root site lists | per-root | `RETRIEVAL_READER_SITE`, `LIFECYCLE_WRITE_SITES`, `LANE_SITES`, `LESSON_RULES_PARITY_SITES` and the lesson parent-directory gate resolve to wherever the marker block lives after the split; a site that stops existing is a finding, not a skip; `sync-surface-parity` reads no split file and is unchanged by construction |
| Finding | label | string | `<file>:<line>: <check>: <message>`, root-relative, for every file including companions (BUG-054 no-leak posture) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `step_reached` | the agent reaches a moved step while running a split skill | it reads the named companion and follows it; the step's observable behaviour (fences run, stderr lines, telemetry, files written) is what it was before the split |
| `budget_exceeded` | `check.py` walks a `SKILL.md` of 500 or more lines | `skill-line-budget` finding; non-zero exit |
| `companion_templating` | a companion carries the argument placeholder or a `` !`…` `` line | `companion-templating` finding |
| `site_moved` | a per-root check's marker block is not at the listed path | a finding naming the path and the constant to update, never a silent pass |

_Permissions: not applicable — no runtime actors. Section omitted deliberately._

## Business Rules

- [ ] BR-1: After this REQ, `spec/SKILL.md`, `proceed/SKILL.md` and `template-drift/SKILL.md` are each below 500 lines, and every other `*/SKILL.md` in the toolkit is also below 500 lines (on `d2eadd7` no other is above; `wrapup` at 475 is the nearest).
- [ ] BR-2: `tools/lint-skills` gains `skill-line-budget`: a per-file check in the main `SKILL.md` walk that reports any `SKILL.md` of 500 or more lines, naming the count and the budget. There is one threshold for every `SKILL.md`, no per-file allowlist or override, and the check counts in no other way than lines (the Agent Skills token guidance is advisory — see Assumptions). A fixture pins both sides: a 500-line fixture fires, a 499-line one does not. `/architect` checks whether REQ-666's `skills-ref validate` already enforces the 500-line rule; if it does, `skill-line-budget` is that check surfaced through `check.py`, not a second count (informed by REQ-425, LESSON-012).
- [ ] BR-3: **No behaviour change**, stated so it can be checked: the multiset of shell fences across each skill unit is byte-identical before and after the split (extract every fence body from `SKILL.md` plus companions on both trees; the sorted lists are equal — a multiset comparison, so a fence present twice before is present twice after); every marker block (`<!-- retrieval-status … -->`, `<!-- lesson-capture-rules -->`, `<!-- lesson-write-point -->` and the rest; the `<!-- companion: … -->` markers are exempt from byte-identity because BR-12 may change the path they name — one marker per extracted phase must still exist), every stderr line and every telemetry emit exists with identical text; and the order in which an agent reaches the steps is unchanged.
- [ ] BR-4: Moved content is load-bearing. At each moved step's boundary `SKILL.md` carries an instruction naming the companion path and saying to read it and follow it before continuing. It does not carry an inline summary that could be executed instead of the companion. This is a different contract from `/proceed`'s existing `<!-- companion: … -->` marker, which `architecture.md` records as documentation-only; `architecture.md`'s Skill-anatomy section states the contract(s) in force after the split and which files are under which.
- [ ] BR-5: A section moves whole, or, where a section cannot move whole, one whole numbered sub-step of it does. The sub-step form exists for `/spec`: BR-6 keeps Step 1.4's two argument fences in `SKILL.md`, and test harnesses this REQ may not edit read Step 1.6 and Step 3 text from `spec/SKILL.md` (BR-11, AC-14), so neither large step can move whole. A step's prose, its fences and its marker blocks stay in one file together, so no check that reasons about lines near a fence loses its context. The three fences `lesson-check-order` orders (`<!-- lesson-write-point -->`, the `adlc_lesson_check` fence, the `adlc_recheck_id lesson` fence) stay in one file in that order.
- [ ] BR-6: **Claude-only preprocessing stays in `SKILL.md`.** No companion contains the argument placeholder REQ-666 BR-1 leaves in `SKILL.md` or a `` !`…` `` context-macro line (after REQ-666 that is the ETHOS line; a non-ETHOS `!` line is a run-and-read fence and moves like any fence). A fence or sentence that consumes the skill argument stays in `SKILL.md`; it is not moved and not re-spelled (after REQ-666 those are the two placeholder fences its BR-1 leaves in `/spec` Step 1.4). Moved away from the prose that fills them, they would pass the placeholder unfilled and intake would silently never activate. `tools/lint-skills` gains `companion-templating`, which reports either shape in a companion. After both REQs land, `companion-templating` is the only check that guards companions for argument tokens: REQ-666 retires the `$ARGUMENTS` surface and `arg-templating` covers only `$<digit>`. `companion-templating` matches the placeholder by the exact token REQ-666's architecture fixes — one constant in `check.py`, shared with REQ-666's fixtures — never a generic angle-bracket pattern (informed by LESSON-335, LESSON-012).
- [ ] BR-7: **Every per-file lint check walks the companions.** The checks that run only over `SKILL.md` once REQ-666 has landed — `sentinel`, `balance`, `canonical-helper`, `posix-fence`, `arg-templating`, `cross-fence-fn`, `cross-fence-var`, `forge-direct-gh`, `read-bin-fallback`, and REQ-666's `dispatch-has-fallback` and `no-harness-path` — run over `<skill>/references/*.md` and `proceed/phase*.md` with the same rules, in addition to `unguarded-source`, which already does. REQ-666's other three are in the companion walk with a companion rule stated here: `ethos-line` requires **zero** ETHOS lines in a companion (the line belongs to `SKILL.md` only; a companion occurrence is an `ethos-line` finding as well as a `companion-templating` one); `description-budget` has nothing to read in a companion and reports nothing there; `skills-ref` validates the skill directory once, which now includes `references/`, and is not run per companion. This also closes the pre-existing gap on `proceed/phases-lite.md` and on the Phase 6 fence in `proceed/phases-6-8-ship.md`. Every walk sees the same companion set, so the two file families cannot widen separately (informed by REQ-610 BR-5, LESSON-019).
- [ ] BR-8: `cross-fence-fn` and `cross-fence-var` evaluate a skill unit as one scope: a function defined in one file of the unit and invoked at statement position in a different file, or a non-exported variable assigned in one file and read in another, is a finding exactly as a within-file split is today. `canonical-helper` is satisfied by a literal anywhere in the unit, with its existing partial rescue and gate unchanged. Findings keep the `<file>:<line>` of the offending site (informed by LESSON-020, REQ-436).
- [ ] BR-9: The REQ-595 vacuous-scan figure keeps meaning "`SKILL.md` files walked". Companions are never added to `scanned`; a dead skill walk is not maskable by companion files (REQ-610 ADR-3 posture, unchanged).
- [ ] BR-10: **Per-root site lists follow the content.** After the split, `retrieval-status-parity`, `lane-vocabulary`, `lesson-rules-parity`, `lesson-check-order` and `lesson-question-coverage` each find their marker block or fence sequence where it now lives; `sync-surface-parity` reads `init/SKILL.md` and `template-drift/SKILL.md` only and is unchanged by construction. Where a block moved, the site list that names it (`RETRIEVAL_READER_SITE`, `LIFECYCLE_WRITE_SITES`, `LANE_SITES`, `LESSON_RULES_PARITY_SITES`) is updated in the same change, and the lesson checks run on `wrapup/`'s companions exactly as they run on `wrapup/SKILL.md` today. A listed site that no longer exists is a finding naming the path and the list to fix **once the check is armed** (its gate file exists); the inert-outside-the-toolkit gates of `lesson-rules-parity` and `retrieval-status-parity` are unchanged — the `LANE_SITES` posture today, extended to every list. `lesson-rules-parity` is armed when `wrapup/SKILL.md` and `bugfix/SKILL.md` both exist; then a listed `/wrapup` companion site that is missing is a finding naming `LESSON_RULES_PARITY_SITES` (informed by LESSON-019, REQ-652 ADR-13).
- [ ] BR-11: No vendored surface changes. Nothing under `partials/`, `templates/`, `ETHOS.md` or `workflows/` is modified; the `<!-- sync-surfaces: init -->` and `<!-- sync-surfaces: template-drift -->` blocks are unchanged and stay in `init/SKILL.md` and `template-drift/SKILL.md`; `/template-drift` run in a consumer after this REQ reports no drift it did not report before. Skills and their companions reach every session through the symlink install, and REQ-654's skills-only view links the skill directory, so `references/` rides along without an installer change.
- [ ] BR-12: Layout per the Agent Skills specification: companions live directly in `<skill>/references/` (one level below the skill directory, no nesting) as Markdown; `SKILL.md` frontmatter is not changed. `/proceed` ends with **one** companion layout — either its existing `phase*.md` files, or `references/` with the phase files moved there and `<!-- companion: … -->` markers and `LANE_SITES` updated to match — not both. Architecture decides which.
- [ ] BR-13: **Cross-references follow the content.** Every live reference to a moved section — other skills, `agents/*.md`, `workflows/adlc-sprint.workflow.js`, `README.md`, `.adlc/context/architecture.md`, `.adlc/context/conventions.md`, `tools/lint-skills/README.md` and `check.py`'s docstring — names the file and section where the content now lives. Line-number citations into the three skills on the live surface are replaced by section names (`spec/SKILL.md` Step 1.4 cites `proceed/SKILL.md:41` and `:538`). Historical records (`.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/`, `CHANGELOG.md`) are not rewritten.
- [ ] BR-14: No new partial and no new skill directory. The references files are the only new files outside `tools/lint-skills/`.
- [ ] BR-15: All new or moved shell is BSD- and zsh-safe and is not re-spelled by the move: no `\b` in `grep -E` (LESSON-013), no bare `$<digit>` (LESSON-335), no unquoted word-splitting (LESSON-329). The guarded two-level source spelling of REQ-610 BR-3 is untouched.
- [ ] BR-16: Each split skill is dogfooded by execution, not by reading (LESSON-329): `/spec` is run once with an argument that activates intake and once with an ordinary request; `/template-drift` is run once in a consumer repo through its moved steps; `/proceed` is run once through Step 0 and one moved phase. `/wrapup` is dogfooded only if it is split. The run transcripts are the evidence for BR-3's "identical stderr lines and telemetry".
- [ ] BR-17: `tools/lint-skills/README.md` and the `check.py` docstring document `skill-line-budget`, `companion-templating`, the widened walk, the unit scope of BR-8 and the site-following rule of BR-10; `.adlc/context/architecture.md` records the load-bearing companion contract of BR-4; `.adlc/context/conventions.md` "Bash in skills" says that a fence may live in a companion and that the cross-fence rules apply across the unit.

## Acceptance Criteria

- [ ] AC-1: `wc -l spec/SKILL.md proceed/SKILL.md template-drift/SKILL.md wrapup/SKILL.md` reports each below 500, and `python3 tools/lint-skills/check.py --root .` is clean with a scanned count above zero. (BR-1, BR-2)
- [ ] AC-2: Against a 500-line `SKILL.md` fixture the linter reports `skill-line-budget` naming the count; against a 499-line fixture it reports nothing. (BR-2)
- [ ] AC-3: A script that extracts every shell-fence body from each skill unit on the pre-split and post-split trees — the pre-split baseline is the commit at which REQ-666 merged — produces equal sorted lists (a multiset comparison) for each of the three split skills; the diff of each unit's marker blocks (companion markers compared by count, not path) is empty; and the set of stderr-line literals is equal (a set comparison: a duplicated literal may collapse, but no literal present only once before may be absent after). The PR records the script and its output. (BR-3)
- [ ] AC-4: Every moved step has, at its former position in `SKILL.md`, an instruction to read the named companion and follow it; a grep over the three `SKILL.md` files for each companion path finds that instruction, and `architecture.md` states the companion contract(s) in force. (BR-4)
- [ ] AC-5: A fixture companion containing the argument placeholder, and one containing a `` !`…` `` line, each produce a `companion-templating` finding; the shipped companions produce none. (BR-6)
- [ ] AC-6: `/spec` invoked after the split with a readable file path as its argument runs Step 1.4 (the intake stderr line is emitted and a `## Provenance` section is written); invoked with a one-line request it runs no intake, exactly as before. (BR-3, BR-6, BR-16)
- [ ] AC-7: For the nine surviving per-file checks and REQ-666's `dispatch-has-fallback` and `no-harness-path`, a fixture in `<skill>/references/*.md` shape that carries the check's known-bad construct produces that check's finding, and the same fixture in `proceed/phase*.md` shape does too; a companion fixture carrying the ETHOS line produces an `ethos-line` finding; a clean companion fixture produces no `description-budget` or `skills-ref` finding; the `scanned` figure counts only `SKILL.md`. (BR-7, BR-9)
- [ ] AC-8: A fixture unit whose `SKILL.md` defines a function and whose `references/x.md` invokes it produces a `cross-fence-fn` finding at the call site; the same for a variable and `cross-fence-var`; a canonical literal that lives only in a companion satisfies `canonical-helper` for that unit. (BR-8)
- [ ] AC-9: For each per-root check in BR-10, a fixture of the post-split layout proves the check still fires on its known-bad input (an excluded status a writer writes; a lane value outside the vocabulary; capture-rules blocks that differ; a lesson fence out of order) and a fixture with a listed site missing produces a finding naming the path. (BR-10)
- [ ] AC-10: `grep -rn 'lesson-write-point\|adlc_lesson_check\|adlc_recheck_id lesson' wrapup/` shows the three in one file in that order. (BR-5)
- [ ] AC-11: `git diff --name-only` for the PR lists no file under `partials/`, `templates/`, `workflows/`, nor `ETHOS.md`; `/template-drift` in a consumer repo reports the same result before and after. (BR-11)
- [ ] AC-12: `find spec proceed template-drift wrapup -mindepth 3 -name '*.md'` returns nothing (no nesting), and `/proceed` has either `phase*.md` or `references/`, not both. (BR-12)
- [ ] AC-13: `grep -rnE '(SKILL|phases?-[a-z0-9-]+)\.md:[0-9]+' --include='*.md' --include='*.js' --include='*.py'` over the live surface (excluding `.adlc/`, `CHANGELOG.md` and lint test strings) returns no match naming `spec/`, `proceed/`, `template-drift/` or `wrapup/`. (BR-13)
- [ ] AC-14: `pytest tools/lint-skills/tests` passes with the new fixtures, and `sh partials/tests/run.sh` passes unchanged. (BR-7, BR-8, BR-10, BR-11)
- [ ] AC-15: The dogfood runs of BR-16 are recorded in the PR with the stderr and telemetry lines each produced, matching the pre-split lines. (BR-16)
- [ ] AC-16: `git diff --name-only --diff-filter=A` for the PR lists only files under `spec/references/`, `proceed/references/` or matching `proceed/phase*.md`, `template-drift/references/`, `wrapup/references/`, and `tools/lint-skills/`; no new `partials/*` and no new top-level skill directory. (BR-14)
- [ ] AC-17: The lint run of AC-1 reports no `arg-templating`, `posix-fence` or `unguarded-source` finding on any companion, and AC-3's byte-identical fence sets show no fence was re-spelled by the move. (BR-15)
- [ ] AC-18: `tools/lint-skills/README.md` and the `check.py` docstring name `skill-line-budget` and `companion-templating` and describe the companion walk, the unit scope and the site-following rule; `architecture.md`'s Skill-anatomy section and `conventions.md` "Bash in skills" carry the sentences BR-17 names (a grep for `references/` finds each). (BR-17)

## External Dependencies

- REQ-666 (P1a) edits the same three `SKILL.md` files. **Order: REQ-666 lands first; this REQ is rebased on its text.** Consequences already applied in this spec: BR-5 no longer pins the BUG-228 line, BR-7 and AC-7 no longer list `harness-skip` or `provenance-safe-fence`, and AC-10 no longer checks the BUG-228 distance, because REQ-666 BR-5 retires that surface; BR-6 and `companion-templating` guard the ETHOS `` !`…` `` line and the argument placeholder REQ-666 BR-1 leaves in `/spec` Step 1.4 and `/sprint`, not `$ARGUMENTS`; BR-7's companion walk includes REQ-666's `dispatch-has-fallback` and `no-harness-path` with the same rules, and states the companion rule for the other three (`ethos-line`: zero ETHOS lines in a companion; `description-budget`: nothing to read there, nothing reported; `skills-ref`: the skill directory validated once, `references/` included, not per companion).
- REQ-654 (P0): the skills-only view links whole skill directories, which is what BR-11 relies on for `references/` reaching `~/.agents/skills`.
- The Agent Skills specification is a published document the plan cites, not a dependency at run time; no harness other than Claude Code is required to verify this REQ.

## Assumptions

- The Agent Skills figures — `SKILL.md` under 500 lines, body under about 5 000 tokens, detail in `references/` one level deep — are as the plan cites them. The line budget is the one enforced; tokens cannot be counted offline without a tokenizer and are not a lint concern here.
- Every harness that honours the specification reads a `references/` file with its own file tool when the skill text tells it to. That is what makes BR-4's read-and-follow instruction sufficient and BR-6 necessary: the file is read, not preprocessed.
- Budget arithmetic for the architect. **Superseded by the Phase-1 amendment in the Description**: the figures in the rest of this bullet are the 2026-10-27 tree's, and `/architect` re-measures on `d2eadd7`. `spec/SKILL.md` (605): Step 1.4 is 187 lines and Step 1.6 is 222; moving either clears the budget, and Step 1.4 is the one with the argument-placeholder fences (BR-6). `proceed/SKILL.md` (600): Step 0 is 134 (it holds the `<!-- retrieval-status: lifecycle-write -->` block at item 8, `proceed/SKILL.md:309` today — a `LIFECYCLE_WRITE_SITES` site BR-10 retargets if Step 0 moves), Pipeline State Tracking 96 (alone short of the 101 needed before the pointer lines are counted; it clears the budget only together with another section), Phase 5 139, or the 113 lines of inline phase summaries if OQ-3 promotes the phase files; REQ-416 ADR-3 keeps Phase 5 inline because the delegate pre-pass gate handoff is load-bearing (see OQ-1). `wrapup/SKILL.md` (561): Step 4 is 346 and carries every lesson-check site (see OQ-2); Step 2 (41), Step 3 (35), the two ship-summary templates (about 70) and Close-out mode (16) are the alternatives that together clear the budget without moving Step 4.
- `/init` copies nothing from a skill directory, so companions need no vendoring and no `/template-drift` surface.
- A lint fixture can be a directory (a `SKILL.md` plus a `references/` file), not only a single file; `tools/lint-skills/tests/test_check.py` already stages a `proceed/phases-real.md` companion fixture that way.
- `find_phase_files` also enumerates `partials/*.md` (the companion docs whose copy-paste fences are where a call-site spelling originates). `/architect` decides whether the per-file checks BR-7 widens extend to those files as well or `unguarded-source` stays the only check there, and how a check that reads frontmatter (`description-budget`) applies to a companion, which has none.
- The id was allocated with remote verification (9 participating repos, not degraded); no allocation caveat applies.

## Open Questions

- [ ] OQ-1: `/proceed` Phase 5 — REQ-416 ADR-3 keeps it inline because the delegate pre-pass gate handoff is load-bearing. Under BR-4's read-and-follow contract, is that decision still binding, so the 101-plus lines come from Step 0 (134), the inline summaries (113, OQ-3), or Pipeline State Tracking (96) together with one of those — 96 alone is short of 101 before the pointer lines are counted — instead? Proposed: yes, binding; do not move Phase 5 in this REQ.
- [ ] OQ-2: `/wrapup` Step 4 (346 lines) carries the `lesson-check-order`, `lesson-question-coverage` and `lesson-rules-parity` sites. Move it and retarget those sites (BR-10), or keep it and move Steps 2, 3, 5 and Close-out mode (about 160 lines)? Either satisfies the budget; the first is the larger lint change, the second leaves the biggest step where it is.
- [ ] OQ-3: Should `/proceed`'s existing documentation-only companions (`phases-1-3-validation.md`, `phase-4-implementation.md`, `phases-6-8-ship.md`, `phases-lite.md`) be promoted to the load-bearing contract of BR-4, deleting the duplicated inline summaries? Promotion frees lines and removes two copies of each phase; leaving them means `proceed/SKILL.md` carries both a summary and a pointer per phase. Proposed: promote, since the summaries are what the budget is spent on.
- [ ] OQ-4: Should `skill-line-budget` run in CI for the toolkit (the lint runs today from `/analyze` Step 1.9 and by hand)? REQ-425 OQ-1 declined a git hook; a CI job is a separate question. Proposed: out of scope here; note it as a follow-up.

## Out of Scope

- The rest of P1 of the plan. REQ-666, which lands first: the argument placeholder in place of `$ARGUMENTS`, the dispatch-paragraph wording, its five checks, and the retirement of `harness-skip` and `provenance-safe-fence`. Separately: `/init` vendoring `agents/` and the `agents` drift surface, `lane_check.py` blocked paths. REQ-666's checks must keep passing after this REQ; it widens their walk and states the companion rule for `ethos-line`, `description-budget` and `skills-ref` (BR-7), and changes nothing else about them.
- Splitting `wrapup/SKILL.md` (475 lines on `d2eadd7`, inside the budget) or any skill other than `spec`, `proceed` and `template-drift`. (Amended at Phase 1: this line excluded `template-drift` while it was at 477; it is now at 572, and BR-1 brings it into the split set.)
- A token-count budget, a `scripts/` or `assets/` layer, or any change to `SKILL.md` frontmatter.
- Any change to what a step does: no fence is rewritten, no stderr line reworded, no telemetry field added.
- Reconsidering REQ-416 ADR-3's reasoning about Phase 5 beyond OQ-1's yes-or-no.
- Rewriting historical records that cite line numbers in the three skills.
- Running the split skills on a non-Claude harness; that is P2 and later.

## Retrieved Context

- REQ-652 (spec, score 11): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- LESSON-020 (lesson, score 11): A shell function shared across SKILL.md steps must be a sourced partial, not a cross-block definition — fenced blocks don't share shell state; and the presence-guard protecting it must follow the same indirection or it rots
- REQ-610 (spec, score 10): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- LESSON-335 (lesson, score 10): Four zsh-executor/templating hazards in SKILL.md scripts: bare $<digit>, [0] arrays, unmatched globs, status= assignments
- LESSON-329 (lesson, score 9): Skill bash runs under the operator's shell (zsh) — dogfood by executing it, don't trust lint or an sh-only run
- LESSON-662 (lesson, score 8): Some shell cannot be respelled past a provenance classifier — the skill text has to route around it
- REQ-594 (spec, score 8): Spec intake: turn raw human input into a draft REQ plus an explicit gap list
- LESSON-572 (lesson, score 8): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 8): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts
- REQ-546 (spec, score 8): Atomic remote id reservation at allocation time (close the allocation-to-visibility window)
- REQ-518 (spec, score 8): Collision-Safe ID Allocation Across Users and Machines
- REQ-433 (spec, score 8): Kimi telemetry global-fallback resolver — make delegation telemetry work in downstream repos
- REQ-436 (spec, score 8): Extract analyze telemetry helper to a sourceable POSIX partial (fix cross-block + local defects)
- LESSON-013 (lesson, score 8): BSD grep \b word-boundary in -E silently fails on macOS — use -wF instead
- REQ-425 (spec, score 8): Pre-merge detection of corrupted shell constructs in SKILL.md files (catches REQ-424-style substitution disasters before they ship)

## Deferred

Recorded at `/wrapup` (2026-10-29), from REQ-661's Phase 5:

- **BR-16 / AC-6 / AC-15, in part.** The dogfood executed every moved fence under `sh` and `zsh` from the split text and from `7d3bf2c`, and confirmed each skill reaches the same fences in the same order (PR #220). It did not run each split skill end to end: a full `/spec` run allocates a real REQ id and pushes a reservation ref, `/proceed` Step 0 creates worktrees and PRs, and `/template-drift` Step 0 fetches in the consumer repo. A full `/spec` intake run (a file-path argument, through the `## Provenance` section) and a full `/template-drift` run in a consumer, on the split text, remain to be recorded. ASSUME-012 tracks the assumption this rests on.
- **`partials/tests/source-guard.test.sh` does not walk `<skill>/references/*.md`**, so its per-fence corpus run no longer executes the four moved `/spec` fences, and the COUPLING NOTE in `partials/tests/intake.test.sh` still names `spec/SKILL.md` Step 1.4 sub-step 3.5, now in `spec/references/intake-source-read.md`. Both need a `partials/` edit, which BR-11 kept out of this REQ. Resolved by BUG-255: the test walks `<skill>/references/*.md` and pins a floor of 9 companion fences (there were 9, not 4), and the COUPLING NOTE names the companion.
- **OQ-4**: a CI job for `skill-line-budget`; the toolkit has no hosted CI.
