---
id: LESSON-615
title: "One interpreter rule must check the package, not the interpreter, and must reach every call site"
component: "tools/adlc"
domain: "adlc"
stack: [python, shell]
concerns: [correctness, install, fail-closed]
tags: [venv, interpreter-selection, pyyaml, forge, doctor, lesson-392, three-sites]
req: REQ-609
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

REQ-609 added PyYAML as a dependency and asked for one managed interpreter.
The first implementation preferred `~/.claude/delegate-venv/bin/python3`
wherever it was executable — at the `adlc` shim and in `adlc doctor`'s probes —
and left `partials/forge.sh`, the path `/proceed` uses for every PR operation,
on bare `python3`. Three reviewers converged on the consequence: a venv created
before the REQ has `openai` and no PyYAML, a fresh Mac has PyYAML only in the
venv, and the reference machine's `$PATH` `python3` had it only from a user-site
`pip install --user` (the spec had said "Apple ships it"; it does not). Whichever
way the rule fell, forge read the config under an interpreter that could not
parse it, took the dependency-missing carve-out, and silently overrode a written
`forge.provider` — with the stderr line discarded by a `2>/dev/null`. The doctor
reported PASS on the interpreter forge was not using (LESSON-392's shape, one
layer over). The confirmation pass then found the three copies of the rule
disagreed on a symlinked `site-packages/yaml` and on a `$HOME` containing glob
characters.

## Lesson

When a behaviour depends on which interpreter runs, write the selection rule
once in words, apply it at **every** site that spawns an interpreter (grep for
`python3` before declaring "all sites"), and make the predicate test the thing
you actually need — the package's presence — not a proxy for it (the venv
existing). Where the rule must live in more than one language, put a comment at
each copy naming the others and add one test that stages the tricky inputs
(symlink, metacharacters in the path, a non-`python*` layout) and asserts all
copies agree. Never suppress the diagnostic that would reveal the split.

## Why It Matters

An interpreter split is invisible in every per-site test and in a green
doctor; it shows up as a silently wrong provider or a config read as
unconfigured, on exactly the machine that just upgraded.

## Applies When

Adding a runtime dependency to a tool that has both a managed venv and a bare
`python3` path; any shim, doctor, or partial that picks an interpreter; any
"install ordering" change; any `2>/dev/null` on a config reader.
