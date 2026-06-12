---
id: BUG-116
title: "adlc_remote_high silently degrades under zsh — unquoted for-loop word-split breaks candidate-id iteration"
status: resolved
severity: high
created: 2026-06-11
updated: 2026-06-11
component: "partials/id-alloc"
domain: "id-allocation"
stack: ["sh", "bash", "zsh"]
concerns: ["portability", "reliability"]
tags: ["REQ-518", "zsh", "word-splitting", "SH_WORD_SPLIT", "collision-safety", "octal"]
---

## Description

`adlc_remote_high` (partials/id-alloc.sh, shipped in REQ-518 / PR #84) iterates its
candidate-id lists with `for adlc_rh_n in $adlc_rh_nums` (and the same pattern for
`$adlc_rh_artifact_nums`). That relies on word-splitting of an unquoted parameter
expansion — which zsh does NOT perform by default (no `SH_WORD_SPLIT`). Under the zsh
executor a multi-line candidate list reaches the `[ "$n" -gt "$max" ]` integer test as
ONE newline-joined string, the test errors with `integer expression expected`, the max
never updates, and `adlc_remote_high` returns 0. Allocation then silently degrades to
the local-counter-only path — REQ-518 BR-2 (remote high-water derivation, the core of
collision safety) is non-functional, and the degradation is silent, which BR-3
prohibits.

The shipped 9/9 bash/zsh test matrix passes because every remote fixture creates
exactly ONE matching branch: a single-number list is a single word, so the broken loop
accidentally works. The multi-candidate case (any real repo) was never exercised.

`adlc_recheck_id` (partials/id-recheck.sh) inherits the defect through its
`adlc_remote_high` call (under zsh the renumber suggestion `high + 1` is computed from
a bogus 0) AND has a defect of its own, found during fix verification: its
`while read; do adlc_id_dec; done` normalize loops concatenate multiple candidates
(no trailing newline from `adlc_id_dec`), so with ≥2 remote branches the exact-id
collision probe never matches — on EITHER shell. A third latent issue (zsh aborts the
repo-enumeration glob on an empty root, NOMATCH) was exposed by the new loud-fail
guard. All three are covered in Resolution.

## Reproduction Steps

1. Create a bare repo with ≥2 matching branches (e.g. `feat/REQ-600-x`, `feat/REQ-650-y`), clone it under `$ADLC_REPOS_ROOT`, set the local counter to 100.
2. Under zsh: `. partials/id-alloc.sh; adlc_remote_high req; adlc_alloc_id req`

## Expected Behavior

`adlc_remote_high req` prints 650; `adlc_alloc_id req` prints 651 — identically under sh, bash, and zsh (BR-6).

## Actual Behavior

Under zsh: `adlc_remote_high:[:42: integer expression expected: 600\n610\n650`, prints 0, and `adlc_alloc_id` allocates 100 (local-counter-only) with no degradation warning. Under bash: correct (650 / 651).

## Environment

- Platform: macOS (Darwin 25.5.0), zsh executor
- Version: toolkit @ e6a90e7 (REQ-518, PR #84)

## Root Cause

`for x in $var` is not portable iteration: POSIX sh and bash word-split the unquoted
expansion, zsh does not (`SH_WORD_SPLIT` off by default). Two sites in
`adlc_remote_high` used it on newline-separated candidate lists. The BR-6 portability
checklist in the partial header (prefixed globals, no `\b`, no bare `$<digit>`…) did
not include the word-split rule, and the test fixture's single-branch remotes meant
the lists were always single-element, so both shells passed. Additionally, nothing
guarded the `[ -gt ]` integer tests against non-numeric input, so the failure mode was
per-candidate stderr spam plus a silent 0 return instead of a loud abort.

## Resolution

Three related fixes (the regression tests written for the reported defect exposed two
more in the same surface):

1. **Newline-safe candidate reduction** (the reported defect): added
   `adlc_id_list_max` — max of a newline-separated number list via a
   `printf '%s\n' | sed | sort -n | tail -1` pipeline (LESSON-329), with per-line
   decimal normalization (octal trap) and a loud failure (ERROR + rc 2) on any
   non-numeric line. Both `for x in $list` loops in `adlc_remote_high` now use it.
   `adlc_alloc_id` and `adlc_recheck_id` guard `adlc_remote_high`'s output: empty or
   non-numeric aborts loudly instead of silently allocating local-only. The
   unreachable-remote DEGRADED path (prints 0 + warns, never blocks) is unchanged
   per BR-3.
2. **`adlc_recheck_id` multi-candidate collision miss** (both shells, found by the
   new tests): its normalize loops ran `while read; do adlc_id_dec "$n"; done`, but
   `adlc_id_dec` prints no trailing newline, so ≥2 candidates concatenated into one
   bogus number ("600650") and the `grep -qx` exact-id probe never matched — real
   collisions returned 0. Replaced with per-line `sed` normalization.
3. **zsh NOMATCH glob abort** (latent, exposed by the new loud-fail guard): with an
   empty repos root, zsh aborts `for repo in "$root"/*` ("no matches found"), so
   `adlc_remote_high` died mid-function and previously its empty output was silently
   coerced to 0. Added `setopt localoptions nullglob` scoped to the function, zsh-only,
   in both partials.

Regression tests added (run under bash AND zsh via `sh partials/tests/run.sh`):
multi-branch real-bare-repo fixture (the zsh killer), leading-zero branch names,
lesson allocation against a stubbed multi-entry `gh api` artifact listing,
`adlc_id_list_max` unit cases incl. loud garbage rejection, and a multi-branch recheck
collision asserting the renumber suggestion uses the real high-water (REQ-651, not
REQ-001). Matrix: 178 PASS / 0 FAIL.

## Files Changed

- `partials/id-alloc.sh` — `adlc_id_list_max` helper; zsh-safe reduction in `adlc_remote_high` (both loops); nullglob guard; loud non-numeric guard in `adlc_alloc_id`; BR-6 header rule updated
- `partials/id-recheck.sh` — per-line sed normalization (concatenation fix); nullglob guard; loud non-numeric guard on `adlc_remote_high` output
- `partials/tests/id-alloc.test.sh` — multi-branch fixture helper + 6 new regression cases (14 new assertions)

## Deployment

Merged to main via PR #88 (squash, 36eb6ab) on 2026-06-11. Toolkit deploys via the
symlink install — main checkout pulled to 36eb6ab, so `~/.claude/skills/partials/`
serves the fix immediately. Live-verified post-merge: `adlc_alloc_id lesson` under
the zsh executor (the exact incident invocation) allocated LESSON-399 cleanly —
no integer-test spam, no degradation warning. No Cloud Run / iOS targets (n/a).
