---
id: LESSON-397
title: "Toolkit commands that mutate project artifacts must resolve the repo root from the caller's cwd, not the script's own location"
component: "adlc/toolkit"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "portability"]
tags: ["repo-root", "cwd", "renumber", "toolkit-vs-project", "symlink-install"]
req: REQ-518
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

`adlc renumber` lives in the toolkit repo (`tools/adlc/`), but the colliding
artifact it must rewrite lives in whatever *project* the user runs it from.
A natural implementation — `git rev-parse --show-toplevel` relative to the
script's own path — resolves to the TOOLKIT repo, so the rename would search
(and "fix") the toolkit instead of the user's project. REQ-518 split
resolution deliberately: project artifacts follow the caller's cwd; toolkit
assets (partials, templates) follow the script location.

## Lesson

In a symlink-installed toolkit, every command has two candidate roots and
they are usually different directories. Make the split explicit in code and
docs: cwd-derived root for anything user/project-owned, script-derived root
for anything toolkit-owned, and never let one default silently stand in for
the other. A smoke test that runs the command from a foreign project
directory catches the inversion immediately.

## Why It Matters

The failure mode is a mutating command operating on the wrong repository —
worst case, "renumbering" toolkit history while reporting success for the
user's collision. The same two-roots trap awaits every future `adlc`
subcommand, doctor check, and partial that touches files.
