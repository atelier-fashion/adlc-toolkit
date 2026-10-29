---
id: LESSON-742
title: "A skill-text edit is input to the harnesses that parse skill text — a clean lint is not the gate; run partials/tests/run.sh on the final tree"
component: "adlc/partials/tests"
domain: "adlc"
stack: ["markdown", "bash", "claude-skills"]
concerns: ["verify-quality", "structural-enforcement", "testing"]
tags: ["lint-skills", "partials-tests", "lesson-check", "wrapup", "skill-md", "fence", "four-shell-suite", "gate-scope"]
req: REQ-648
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-648 commit fc7632f added a record-lessons-written sh fence inside /wrapup Step 5. tools/lint-skills/check.sh exited 0, but partials/tests/lesson-check.test.sh case wrapup_templates_carry_lessons_captured failed under bash, zsh, sh and dash (templates=3 headings=2), because it counts every fence in Step 5 as a ship-summary template. Commit ebf56c2 moved the fence to the end of Step 4 and the case passed in all four shells. All squashed into f3e8f05 (PR #211)."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-648 added a shell fence to `/wrapup` Step 5. The skill linter passed it, and the task was committed on that basis. The four-shell partial suite, run only after the last task, failed in every shell. One of its harnesses reads `wrapup/SKILL.md` and asserts that every fenced block in Step 5 is a summary template carrying `### Lessons captured`. The new fence was a fourth block with no heading.

## Lesson

In this toolkit the markdown is executable *and* it is data: harnesses under `partials/tests/` (and tests under `tools/*/tests/`) extract sections, fences and markers from SKILL.md files and assert their shape. So `tools/lint-skills` passing on a skill edit proves only the lint's own checks. Before committing a skill-text change, run the suites that read that file. `grep -rl '<skill>/SKILL.md' partials/tests tools/*/tests` names them. Run the full `partials/tests/run.sh` on the final tree before the PR, not only after the task that last touched shell code. When such a guard fails, move the new text out of the section the guard enumerates rather than loosening the guard (LESSON-019).

## Why It Matters

The failure surfaced one task late and cost a rerun of the ten-minute four-shell suite. Had the suite been skipped because "only markdown changed", the guard that keeps every ship summary's `### Lessons captured` slot well-formed would have been red on `main`.

## Applies When

- Adding a fence, heading, marker or numbered item to a SKILL.md, a `proceed/phase*.md` companion or an agent file.
- Deciding which tests a "markdown-only" change needs.
- A structural guard fails on a section you extended: move your addition, do not widen the guard.
