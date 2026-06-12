---
id: BUG-118
title: "partials/tests/run.sh breaks under zsh: TESTS string not word-split, every harness fails"
status: resolved
severity: high
created: 2026-06-12
updated: 2026-06-12
component: "adlc/partials-tests"
domain: "tooling"
stack: ["sh", "bash", "zsh"]
concerns: ["portability", "ci"]
tags: ["zsh", "word-splitting", "test-harness", "run.sh"]
---

## Description

`partials/tests/run.sh` builds its harness list as a single space-joined string
(`TESTS="$HERE/id-alloc.test.sh $HERE/forge.test.sh"`) and iterates it with
`for t in $TESTS`. That iteration relies on sh/bash field-splitting of the
unquoted expansion. zsh does not field-split unquoted parameter expansions
(no `SH_WORD_SPLIT` by default), so when the runner itself is invoked as
`zsh run.sh` — the macOS Claude executor shell, per LESSON-329/LESSON-335 —
the whole string is treated as one filename and every harness fails with
"no such file or directory".

The bug was latent while `TESTS` had a single element (a one-element list is
identical whether split or not — the masking class recorded in LESSON-399)
and surfaced when REQ-523 added `forge.test.sh` as a second element. Same
defect class as BUG-116 (zsh word-split in `id-alloc.sh` remote-high scan).

## Reproduction Steps

1. `zsh partials/tests/run.sh`
2. Observe both the bash pass and the zsh pass attempt to execute a single
   path `"$HERE/id-alloc.test.sh $HERE/forge.test.sh"` and fail with
   "no such file".

## Expected Behavior

`run.sh` runs each harness (`id-alloc.test.sh`, `forge.test.sh`) under both
bash and zsh regardless of which shell invokes `run.sh` itself.

## Actual Behavior

Under `zsh run.sh`, `$TESTS` expands as one word; every harness invocation
fails with "no such file or directory" in both the bash and zsh passes.
Under `sh run.sh` / `bash run.sh` it works, which masks the bug locally.

## Environment

- Platform: macOS (Claude Code executor invokes scripts with zsh — LESSON-329, LESSON-335)
- Version: adlc-toolkit main @ REQ-523 (9cca0e4)

## Root Cause

The harness list is stored as a flat string and iterated via unquoted
expansion (`for t in $TESTS`), an sh/bash-ism that depends on field
splitting. zsh's default is no word-splitting of unquoted expansions, so the
list degenerates to one bogus path. The list should be held in the
positional parameters (`set -- file1 file2; for t in "$@"`), which iterates
element-wise identically in sh, bash, and zsh.

## Resolution

Replaced the space-joined `TESTS` string with the positional parameters:
`run_all` now takes the harness paths as arguments and iterates `for t in "$@"`,
which is element-wise in sh, bash, and zsh alike. Additionally, the outer pass
now re-execs `run.sh` itself under each shell (`"$shell" "$0" --inner "$shell"`)
instead of merely running the harnesses with that shell — so every CI run
exercises run.sh's own list handling under zsh, and a regression of this class
fails immediately rather than lying latent (the LESSON-399 masking class).

Verified: `sh run.sh`, `bash run.sh`, and `zsh run.sh` each execute all
4 harness runs (2 harnesses × 2 shells) green; a synthetically failing harness
propagates exit 1 through the re-exec layer.

## Files Changed

- `partials/tests/run.sh` — harness list moved to positional params (no
  word-splitting); outer pass re-execs run.sh under bash and zsh so the
  runner's own zsh invocation is exercised on every run

## Deployment

- Merged via PR #97 (squash) on 2026-06-12. No deploy targets — adlc-toolkit
  is a symlink-install skills repo (no Cloud Run / iOS surfaces).
