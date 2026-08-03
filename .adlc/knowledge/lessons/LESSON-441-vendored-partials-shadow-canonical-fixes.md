---
id: LESSON-441
title: "Repo-local-first sourcing means a canonical partial fix is not deployed until every vendored copy is re-synced — stale vendored partials shadow the fix and keep crashing"
component: "adlc/partials"
domain: "adlc"
stack: ["bash", "zsh", "markdown"]
concerns: ["correctness", "retrieval"]
tags: ["template-drift", "vendored-partials", "sourcing-order", "empty-operand", "arithmetic-expansion", "mktemp", "posix", "telemetry"]
req: PR-107
created: 2026-08-03
updated: 2026-08-03
---

## What Happened

`_adlc_emit_step_telemetry spec Step-1.6` crashed in zsh with `bad math
expression: operand expected at ') * 1000'` on the gate-fail fallback path —
in three downstream repos, months after the canonical partial had been fixed.
REQ-522 rewrote `emit-step-telemetry.sh` to read telemetry state from the
flag-file sidecar and to guard a missing `start_s`, but every skill fence
sources the partial repo-local-first:

    . .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh

Three repos (admin-api, atelier-fashion, infrastructure) still vendored the
pre-REQ-522 Kimi-era copy, which computed
`$(( ($(date -u +%s) - $start_s) * 1000 ))` from a caller SHELL variable —
always empty in a fresh fenced block, and an empty operand inside `$(( ))` is
fatal in zsh. The `||` fallback to the fixed canonical never fired, because
the stale copy sourced successfully and then crashed. The same report
surfaced a second latent bug: `mktemp -t adlc-skill-flag.XXXXXX` on BSD/macOS
treats the `-t` argument as a literal prefix and never expands its X's,
producing flag paths with a literal `XXXXXX` — confusing for any agent that
must re-thread the path across fences. Fixed in PR #107 (numeric-validating
`case` guard + `${TMPDIR:-/tmp}/`-anchored mktemp template) plus a re-sync of
all five repos that vendor the partial.

## Lesson

Vendored partials are shared executable code with repo-local-first sourcing
precedence, so fixing the canonical is only half a fix: the bug remains live
in every downstream repo until its `.adlc/partials/` copy is re-synced. A
partial bugfix is not "shipped" at canonical merge — its deployment step is
the vendored-copy sweep (`/template-drift` across repos, or a direct sync).
When a partial crash is reported, diagnose against the copy the failing repo
actually sourced, not the canonical — the canonical may already be correct.
Two hardening corollaries from the same incident: (1) guard arithmetic
expansions with numeric validation (`case "$v" in ''|*[!0-9]*)`), not just
`[ -n ]` — zsh aborts on empty or garbage operands where a "-" sentinel was
intended; (2) never use `mktemp -t <name>` in portable scripts — BSD and GNU
disagree on whether the argument is a template; use a full-path template
`${TMPDIR:-/tmp}/<name>.XXXXXX`, which both expand identically.

## Why It Matters

The repo-local-first `||` chain is designed for resilience (a repo works
without the global toolkit installed), but it silently inverts after a
canonical fix: the mechanism meant as a fallback becomes a shadow that pins
every downstream repo to the buggy version. The greener the canonical repo's
suite, the more misleading the field crash looks — the code under test was
never the code that ran.

## Applies When

- Fixing any bug in `partials/*.sh` or another vendored sync surface: the fix
  plan must include the downstream re-sync, not just the canonical merge.
- Diagnosing a crash whose stack points into a partial: first check which
  copy was sourced (`.adlc/partials/` vs `~/.claude/skills/partials/`) and
  diff it against canonical before reading the canonical source.
- Writing POSIX partials that do arithmetic on values read from files or
  sidecars: validate numeric before `$(( ))`.
- Calling mktemp in anything that runs on both macOS and Linux.
