---
id: LESSON-750
title: "A scan root can hold other checkouts that the CI and runner worktrees never have — skip them in the walk, never by filtering a test's output"
component: "tools/lint-skills"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["lint", "worktrees", "desktop-app", "scan-root", "skip-list", "masked-finding"]
req: BUG-254
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "BUG-254: sh tools/lint-skills/check.sh on the primary checkout exited 125 with 125 findings, all under .claude/worktrees/<name>/, while every .worktrees/REQ-xxx runner lint was clean. tools/lint-skills/tests/test_check.py::test_nested_session_worktree_skipped fails on the old find_skill_files and passes once it skips the (.claude, worktrees) pair below the root; test_repo_root_unguarded_source_and_root_line_clean had been dropping lines starting with .claude/ instead."
confidence: high
enforcement: "test:tools/lint-skills/tests/test_check.py"
generalizes: []
supersedes: []
---

## What Happened

The lint walked `.claude/worktrees/<name>/`, where the Claude desktop app keeps
whole checkouts of other branches, and reported their stale skills. No runner
saw it: `/proceed` lints inside `.worktrees/REQ-xxx`, which has no
`.claude/worktrees/`. An earlier test met the symptom and filtered out output
lines starting with `.claude/`, so the walk bug stayed in the linter.

## Lesson

A recursive walk over a developer's primary checkout meets more nested checkouts
than the ones the code was written for: `.worktrees/` from `/proceed`,
`.claude/worktrees/` from the desktop app, and whatever the next tool adds. Put
each of them in the walk's skip list, tested only on the components below the
scan root (LESSON-019), and add a test that plants a violation inside one. When
a test runs into findings from such a tree, fix the walk; a filter on the test's
output hides the bug from the test and leaves it in the tool.

## Why It Matters

The lint fails only on the machine that has the nested checkouts, so it looks
flaky or environment-specific. Meanwhile CI, runners and every session worktree
stay green, and the real failure surfaces at the worst moment, in the human's
own checkout.

## Applies When

- Writing or changing a recursive walk (`rglob`, `os.walk`, `find`) in a lint,
  doctor or report that runs from a repo root.
- A test or reviewer filters a class of paths out of a tool's output to make an
  assertion pass.
