---
id: LESSON-335
title: "Four zsh-executor/templating hazards in SKILL.md scripts: bare $<digit>, [0] arrays, unmatched globs, status= assignments"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "zsh", "sh", "awk", "claude-skills"]
concerns: ["portability", "correctness", "silent-degradation"]
tags: ["zsh", "arg-templating", "positional-parameters", "awk-fields", "array-indexing", "nomatch-glob", "read-only-status", "shell-portability", "lint-skills"]
req: BUG-OBSERVED-2026-06-10
created: 2026-06-10
updated: 2026-06-10
---

## What Happened

A live `/proceed` run on 2026-06-10 surfaced three failure shapes in skill
fenced scripts, all silent or near-silent:

1. **Skill argument templating clobbers bare `$<digit>` across the WHOLE
   SKILL.md body** — prose, inline code, and fences alike — before any script
   reaches a shell. In `/manifest`, awk's `index($0,k)` became
   `index(MANIFEST_SELF=REQ-508,k)` and the ORDER awk lost its `$5`/`$1`
   fields entirely (replaced with empty). Shell positionals in helper
   functions (`awk -v k="$1"`) are hit the same way.
2. **zsh arrays are 1-indexed**, so `/wrapup`'s `${CANDIDATES[0]}` was
   silently empty under zsh — the JSONL fallback picked nothing and Kimi
   delegation degraded without an error.
3. **zsh errors on unmatched globs** ("no matches found") instead of passing
   the pattern through, so `ls .adlc/specs/$req-*/requirement.md` and
   `for tf in "$specdir"/tasks/TASK-*.md` emit noise or abort where sh/bash
   degrade quietly.
4. **`status` is a read-only special parameter in zsh** (`= $?`), so any
   ad-hoc monitor snippet doing `status=$(...)` dies with "read-only
   variable: status". (No skill file contained this — it bit hand-written
   monitor loops — but the rule belongs in the same portability set.)

## Lesson

The executor shell is zsh (LESSON-329) AND the Skill loader templates the
file before execution. Write skill shell to survive both:

1. **Never write bare `$<digit>`** anywhere in a SKILL.md. Use `${1}` for
   shell positionals and `$(0)`/`$(1)`/`$(5)` for awk fields — neither
   contains a `$<digit>` substring, so both survive templating and are
   valid shell/awk. Enforced by `tools/lint-skills` check 5
   (`arg-templating`).
2. **Never index arrays with `[0]`.** First element portably:
   `"${ARR[@]:0:1}"` (slice form works in bash and zsh).
3. **Never let a glob run unmatched.** Use `find ... 2>/dev/null | sort |
   head -1` for path discovery and `while read` over `find` output (heredoc,
   not pipe, when accumulating variables) instead of `for x in pattern-*`.
4. **Never name a variable `status`** in skill or monitor shell — use `st`,
   `rc`, or similar.

## Why It Matters

All four shapes pass lint-by-reading and run fine under `bash -c`; three of
the four degrade *silently* under the real executor (wrong data, empty
fallback, skipped enrichment) rather than failing loudly. The guard is the
same as LESSON-329 — execute fenced blocks under both `zsh` and `bash` when
dogfooding — plus the new structural linter check for the templating class,
which no runtime test can catch because the corruption happens before the
shell ever runs.
