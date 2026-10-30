---
id: BUG-255
title: "source-guard.test.sh does not walk skill companions, so the moved /spec fences no longer run"
status: resolved
severity: medium
created: 2026-10-29
updated: 2026-10-30
component: "partials/tests"
domain: "adlc"
stack: ["posix-sh"]
concerns: ["test-coverage"]
tags: ["source-guard", "companions", "references", "progressive-disclosure", "corpus-walk"]
introduced_by: [REQ-661]
attribution: manual
---

## Description

REQ-661 (PR #220, `c4e119a`) moved two `/spec` steps out of `spec/SKILL.md` into
companion files: Step 1.4 step 3 into `spec/references/intake-source-read.md` and
Step 1.6 sub-step 7 into `spec/references/retrieval-body-read.md`.
`tools/lint-skills/check.py` walks a skill and its companions as one unit
(`skill_companions`: `<skill>/references/*.md`, plus `proceed/phase*.md`), but
`partials/tests/source-guard.test.sh` was left untouched (REQ-661 BR-11 kept
`partials/` out of scope). Its three corpus walks list `*/SKILL.md`,
`agents/*.md` and `proceed/phase*.md` only, so every sourcing fence in a
`references/*.md` companion silently dropped out of the per-fence run and the
per-line sourcing checks, and the companions left the retired-literal surface.

A comment in `partials/tests/intake.test.sh` also still places the delegation
contract and the citation regexes in `spec/SKILL.md` Step 1.4 sub-step 3.5.

## Reproduction Steps

1. `sh partials/tests/source-guard.test.sh | grep fence_extraction_nonvacuous`
2. Note the count (60 on `main` at `5afc2a8`).
3. `grep -c 'partials/.*\.sh' spec/references/*.md` — the companions hold sourcing
   fences that are not in that count.

## Expected Behavior

Every sourcing fence the toolkit ships, in a `SKILL.md` or any companion the lint
treats as part of the skill, is executed by the per-fence run, and the test fails
if the walk stops reaching them.

## Actual Behavior

The `spec/references/` fences are never extracted or executed; the suite stays
green because no assertion ties the fence count to the companion files.

## Environment

- Platform: macOS, `/bin/sh`, bash, zsh via `sh partials/tests/run.sh`
- Version: `main` at `5afc2a8`

## Root Cause

Prior lessons consulted:
- LESSON-750 — A scan root can hold other checkouts that the CI and runner worktrees never have — skip them in the walk, never by filtering a test's output (score 12)
- LESSON-737 — `git status` and `git diff` refresh the index, so a check that promises to write nothing must run git with --no-optional-locks (score 5)
- LESSON-743 — git -C <dir> answers for the nearest enclosing repository, not for <dir> — test <dir>/.git before asking git whether a directory is a checkout (score 5)
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them (score 5)
- LESSON-749 — When two checks split one pattern, hand a line over only where the receiving check reads the file, or the receiver's exceptions become lines nobody checks (score 5)

`source-guard.test.sh` enumerates its markdown corpus in three separate places,
each a hand-written `find` list: `extract_markdown_leg` (per-line extraction),
`surface_files` (retired-literal surface) and `extract_fences` (per-fence run).
None of them lists `<skill>/references/*.md`, because companions did not exist
when the lists were written (REQ-610, REQ-669). REQ-661 added the companion
directory and taught `check.py` to walk it, but the test's lists are an
independent copy of the corpus definition and nothing forced them to follow.
The per-fence run's only floor is "more than zero fences", so losing nine fences
(5 in `intake-source-read.md`, 4 in `retrieval-body-read.md`) passed.

The fix walks companions from each skill directory found at depth 1 — the same
`<skill>/references/*.md` shape `check.py`'s `skill_companions` uses — in one
helper all three walks share. Listing companions per skill, never by a deep
`find`, keeps the walk out of `.claude/worktrees/` and `.worktrees/` checkouts
(LESSON-750, BUG-254). A regression check pins the number of fences extracted
from `references/` companions, so the count drops and the test fails if the walk
stops reaching them.

Attribution: `git blame` on the root-cause ranges names three REQs — REQ-610 and
REQ-669 (the walk lines) and REQ-661 (the moved fences). Per `/bugfix` Phase 2
step 7, nothing was written until the operator chose: REQ-661, recorded as
`attribution: manual` (2026-10-30). The walk lines were correct for the corpus
they were written against; the defect appeared when REQ-661 moved fences out of
it.

## Resolution

`source-guard.test.sh` gains `skill_unit_files`, which lists each depth-1
`SKILL.md`, that skill's `references/*.md`, and `proceed/phase*.md` — the unit
`check.py`'s `skill_companions` defines — and `markdown_corpus`, which adds
`agents/*.md`. `extract_markdown_leg`, `extract_fences` and `surface_files` all go
through them, so the three corpus lists can no longer drift apart.

Two checks prove it:
- `fence_extraction_walks_companions` builds a fixture whose skill has one
  sourcing fence in `references/c.md`, plus the same skill inside
  `.claude/worktrees/x/` and `.worktrees/x/`. Exactly `sk/references/c.md:3` must
  be extracted.
- `fence_extraction_reaches_companions` requires at least 9 real-corpus fences
  from `references/` companions.

Verified: fences extracted went from 60 to 69, all 69 run clean on both routes.
Deleting the `references/` leg of `skill_unit_files` makes both new checks fail
(`got ''`; `only 0 ... (floor 9)`). `sh partials/tests/run.sh` exits 0 on
`/bin/sh`, bash, dash and zsh; `sh tools/lint-skills/check.sh` exits 0.

The `intake.test.sh` header and section-7 COUPLING NOTE now place the delegation
contract and the citation regexes in `spec/references/intake-source-read.md`
(Step 1.4 step 3, item 5).

## Files Changed

- `partials/tests/source-guard.test.sh` — `skill_unit_files` / `markdown_corpus` shared by all three corpus walks; the companion probe and the companion fence floor; header names `*/references/*.md`.
- `partials/tests/intake.test.sh` — header and COUPLING NOTE point at `spec/references/intake-source-read.md`.
- `.adlc/specs/REQ-661-progressive-disclosure-oversized-skills/requirement.md` — the Deferred item notes BUG-255 resolved it.
- `.adlc/bugs/BUG-255-source-guard-misses-skill-companions.md` — this report.
- `.adlc/knowledge/lessons/LESSON-753-glob-walkers-lose-moved-text-silently.md` — lesson.

## Deployment

No deploy target: the toolkit is live on merge, through the `~/.claude/skills`
symlink to the primary checkout. Lesson captured: LESSON-753.
