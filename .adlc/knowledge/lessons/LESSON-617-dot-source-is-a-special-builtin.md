---
id: LESSON-617
title: "`.` is a POSIX special built-in — `. A || . B` exits sh at the first arm, and both it and `[ -f A ] && . A || . B` double-source when A ends non-zero"
component: "adlc/partials"
domain: "adlc"
stack: ["sh", "dash", "bash", "zsh"]
concerns: ["portability", "correctness", "silent-degradation"]
tags: ["dot-source", "special-builtin", "posix-sh", "two-level-fallback", "double-source", "shell-portability"]
req: REQ-610
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

Every partial call site in the toolkit was written
`. .adlc/partials/x.sh 2>/dev/null || . ~/.claude/skills/partials/x.sh`. On
2026-09-01 the `/architect` Step 5 footprint block, run under `sh` in a checkout with
no `.adlc/partials/`, died at that first line and published nothing; the same block
under zsh worked. `.` is a POSIX *special built-in*, and XCU 2.8.1 requires a
non-interactive shell to **exit** when one fails — so under `dash` and under macOS
`/bin/sh` (bash in posix mode) the `||` arm never runs, and `2>/dev/null` made the
exit silent. Under bash and zsh a failed `.` is an ordinary non-zero status, which is
why the pattern survived for a year across 60 executable sites.

A sandbox matrix of four candidate fixes then showed two more surprises. `command .`
rescues dash but macOS `/bin/sh` still exits. And `[ -f A ] && . A || . B` — the
obvious guard — sources **both** copies whenever A exists and its last statement
returns non-zero, because `.` returns the sourced file's final status and the `||`
arm fires on it. The harness proved today's `. A || . B` form has the same defect
under bash and zsh, so the canonical copy was being loaded on top of a vendored one
in exactly the case LESSON-441's repo-local-first rule exists for.

## Lesson

Never apply `.` to a path that has not been proven to exist, and never let a
sourcing line's success be decided by the sourced file's last status. The one
spelling correct under `/bin/sh`, `dash`, `bash`, `bash --posix`, and `zsh` is a
single-line `if [ -f A ]; then . A; else . B; fi` with no stderr suppression; the
final canonical arm stays unguarded on purpose so a missing toolkit fails loudly
(ASSUME-005). Enforce it structurally — `tools/lint-skills`'s `unguarded-source`
check — not by prose (LESSON-012).

## Why It Matters

The failure is silent, shell-dependent, and invisible under the executor shell
(LESSON-329): a fence looks fine, runs fine in every interactive session, and
publishes nothing the first time a CI job or a consumer runs it under `sh`. The
double-source variant is worse because it does not fail at all; it quietly
overrides a vendored customisation with the canonical copy.

## Applies When

Writing or reviewing any shell that dot-sources a file behind a fallback (`||`),
any `&&`/`||` chain whose left arm is a special built-in (`.`, `eval`, `exec`,
`export`, `set`, `unset`, `readonly`, `:`), or any script that must run under
`/bin/sh` on macOS or Debian-family Linux.
