---
id: ASSUME-005
title: "Every install has ~/.claude/skills/partials/, so the final canonical source arm may stay unguarded"
status: validated
req: REQ-610
created: 2026-09-02
resolved: 2026-09-02
---

## Assumption

The toolkit is installed by symlinking the repo at `~/.claude/skills/`, so on every
machine that runs a skill the canonical partials directory exists and
`~/.claude/skills/partials/<name>.sh` resolves. The guarded spelling therefore tests
only the repo-local copy with `[ -f ]` and dot-sources the canonical copy unguarded;
its absence is "the toolkit is not installed", which no fallback can recover, and
the right behaviour is a loud failure (fatal under `sh`, an error line under
bash/zsh), not a silent skip.

## Context

REQ-610 BR-1 was amended during reflect to state this explicitly after the reflector
showed the original wording contradicted the mandated spelling. Two things depend on
it: `adlc_recheck_id`'s "cannot source id-alloc.sh" `return 2` is reachable only
under bash/zsh (under `sh` the same condition is the fatal exit), and the
`id-alloc.test.sh` sandboxes had to grow the canonical sibling link so the dash pass
models a real install. `partials/tests/source-guard.test.sh` case (c) encodes the
accepted behaviour: both copies absent must leave a non-empty stderr naming the path.

## Resolution

Validated for the symlink install model on 2026-09-02: `install.sh` creates the
symlink, every skill's ethos macro already depends on the same directory, and the
harness proves the loud-failure behaviour under all four shells. It is **not** true
for a hypothetical vendored-only consumer (a CI box that copied `.adlc/partials/` but
never installed the toolkit); on such a box a fence whose repo-local copy is missing
exits under `sh` with the path on stderr, which is the intended signal. Revisit if a
non-symlink install path is ever added.
