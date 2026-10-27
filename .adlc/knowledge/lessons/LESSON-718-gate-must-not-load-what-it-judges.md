---
id: LESSON-718
title: "A gate that judges a change must not load anything the change can edit — not its code, its config, its partials, or a path that differs only in letter case"
component: "adlc/proceed"
domain: "adlc"
stack: ["sh", "python", "git"]
concerns: ["security", "structural-enforcement", "silent-failure"]
tags: ["lane-check", "gate", "trust-boundary", "self-certification", "config-from-base", "icase", "pathspec", "REQ-652"]
req: REQ-652
created: 2026-10-27
updated: 2026-10-27
kind: "process"
evidence: "REQ-652 Phase 5 security audit: a branch-planted .adlc/tools/adlc/lane_check.py printing lane_check=pass was run by partials/lane-check.sh, and a skip-worktree .adlc/config.yml with max_files: 99 passed ten source files; fixed by running only the installed engine and reading the config with git ls-tree/cat-file at the base ref. The confirmation pass then got a pass through .ADLC/partials/lane-check.sh, because the guard's git pathspec is case-sensitive while macOS resolves the source path case-insensitively; fixed with ':(icase)' pathspecs in proceed/phases-lite.md and pinned by tools/lint-skills/tests/test_lite_lane_contract.py"
confidence: "high"
enforcement: "test:tools/lint-skills/tests/test_lite_lane_contract.py"
generalizes: []
supersedes: []
---

## What Happened

REQ-652's lane check is a mechanical gate: it decides from the diff whether a
lite-lane change stayed small and out of risky paths. The first version looked
for its engine in the worktree first (`tools/adlc/lane_check.py`, then the
vendored `.adlc/tools/`), read `.adlc/config.yml` from disk, and was sourced
from the worktree's `.adlc/partials/`. Every one of those is a file the branch
under check can change. The security audit reproduced two bypasses: a planted
engine that printed a pass, and a local config marked skip-worktree that raised
`max_files` without appearing in the diff. After the fix, the confirmation pass
found a third: the guard refusing branches that edit `.adlc/partials` used a
case-sensitive git pathspec, but the shell sourced `.ADLC/partials/...` happily
on a case-insensitive filesystem.

## Lesson

When a check certifies a change, list everything the check executes or reads,
and take each one from somewhere the change cannot write:

- the checker's code from the installed toolkit, never the tree under check;
- its configuration from the base ref (`git ls-tree`/`cat-file`), never the disk;
- anything sourced before the check runs only after guards prove the tree is
  clean, pushed, and has not touched those files;
- path comparisons in those guards with the same case rules as the filesystem
  that will resolve them (`:(icase)` pathspecs on macOS).

A check that the change can rewrite is not a gate; it is the change certifying
itself.

## Why It Matters

The lane check is what lets the lite lane skip architecture and the review
panel. If a lite change can make it pass, every risky change can enter through
the cheap lane: the pipeline's own agent "fixing" a failing check is enough, no
attacker required. Each bypass above was a one-file edit that the check itself
did not count.

## Applies When

Writing or reviewing any gate, lint or verifier that runs against a branch,
worktree or PR and decides whether it may proceed: lane checks, trial merges,
policy checks, or vendored copies of toolkit code that run inside the project
being checked.
