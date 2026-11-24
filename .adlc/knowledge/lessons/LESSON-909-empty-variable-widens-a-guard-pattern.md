---
id: LESSON-909
title: "A guard pattern built from a variable and a literal becomes the literal when the variable is empty, and a test that inherits that variable passes wherever it is set"
component: "adlc/partials/intake"
domain: "adlc"
stack: ["shell"]
concerns: ["safety", "data-loss", "testing", "portability"]
tags: ["case-pattern", "parameter-expansion", "tmpdir", "empty-variable", "deletion-guard", "rm-rf", "inherited-environment", "env-i", "false-green"]
req: BUG-293
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-293: partials/tests/intake.test.sh case `BUG-293 cleanup: non-temp dir refused with TMPDIR unset` fails against main at 78500a2 with `(expected '0', got '1')` under bash, zsh, sh and dash, and passes at 9585651. The arm was `\"${TMPDIR%/}\"/*` in adlc_intake_cleanup (partials/intake.sh), which is `/*` when TMPDIR is unset, empty or `/`. The older case `cleanup: non-temp dir refused even with matching basename` passed at 78500a2 with TMPDIR set and failed under `env -i` without it."
confidence: high
enforcement: test:partials/tests/intake.test.sh
generalizes: []
supersedes: []
---

## What Happened

`adlc_intake_cleanup` removes a directory only when it sits under a temp root. The check
was a `case` arm, `"${TMPDIR%/}"/*|/tmp/*|/var/folders/*`. With `TMPDIR` unset, empty or
`/`, the first alternative is `/*`, which matches every absolute path, and the function
ran `rm -rf` on any absolute directory holding an `inline-request.txt`. `TMPDIR` is unset
in an ordinary Linux session.

The function had four refusals for the path being deleted (`''`, `.`, `/`, `$HOME`) and a
header saying why. Nothing checked the variable the pattern was built from.

The suite had a case for exactly this, a non-temp directory with the right basename, and
it passed for nearly three months. It never set `TMPDIR`. It was run from sessions where the
variable is set, under four shells, and all four agreed. It failed the first time the
suite ran under `env -i` for an unrelated bug.

## Lesson

1. **Check the variable a pattern is built from, not only the value matched against it.**
   `"$VAR"/*`, `"$VAR"*`, `"${VAR%/}"/*` and `"$VAR"-*` each become their literal part when
   the variable is empty, and the literal part alone is usually the widest match there
   is. Before a pattern built this way decides anything destructive, test the variable
   for the shape it must have (here `/?*`: absolute, and more than `/`), and skip the arm
   when it does not. A suffix strip such as `%/` can empty a value that was not empty.
2. **Fail closed in the direction that costs less.** Skipping the arm leaks a temp
   directory. Admitting it deletes a user's one.
3. **A test sets every environment variable the code under test reads.** Each case sets
   it in a subshell: unset, empty, and one ordinary value at least. A case that inherits
   the variable certifies only the environments it happened to run in, and more shells do
   not help: the shell was never the axis.
4. **Run a suite once under `env -i` when it guards something destructive.** That one
   run found this. Pass through only what the harness needs (`PATH`, a throwaway `HOME`,
   and here `USER`, `LOGNAME` and `SHELL`).

## Why It Matters

The failure is silent and its cost is a deleted directory. The guard reads as correct, the
comment above it says it is, and the test named for the case is green. On the author's
machine nothing can show the defect, because the variable that hides it is always set
there.

## Applies When

Writing or reviewing a shell `case` pattern, a glob or a prefix test that interpolates a
variable, above all one that decides whether an `rm`, a `mv` or an overwrite runs; code
that reads `TMPDIR`, `HOME`, `XDG_*` or any variable that is set on one platform and unset
on another; a test for such code; a suite that has only ever been run from an interactive
session.
