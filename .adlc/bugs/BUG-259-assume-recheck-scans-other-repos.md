---
id: BUG-259
title: "`adlc_recheck_id assume` scans other repos, so a sibling's ASSUME reads as a collision"
status: resolved
severity: low
created: 2026-10-31
updated: 2026-10-31
component: "adlc/partials/id-recheck"
domain: "adlc"
stack: ["sh"]
concerns: ["correctness"]
tags: ["id-recheck", "assume", "per-repo", "collision", "false-positive", "br-12", "renumber"]
introduced_by: ["REQ-518"]
attribution: derived
---

## Description

`adlc_recheck_id assume <ID>` walks every repo under the repos root, so a sibling repo's
same-numbered ASSUME reads as a collision. ASSUME ids are per-repo (REQ-546 BR-12). REQ-658's
close-out saw ASSUME-018 and ASSUME-019 reported against `embolden-website`, although neither
id existed in this repo. No skill makes this call today; the runner made it by hand.

## Reproduction Steps

1. Reserve `refs/adlc/ids/assume/18` in a sibling under the repos root.
2. Run `adlc_recheck_id assume ASSUME-018` from a repo that has no such id.

## Expected Behavior

Return 0: another repo's ASSUME is another namespace. A reservation in this repo's own origin
is still a collision.

## Actual Behavior

Return 1, with a `COLLISION` line naming the sibling and an `adlc renumber` command that refuses
ASSUME ids.

## Environment

macOS, the symlink install, 9 participating repos under `~/GitHub`.

## Root Cause

Prior lessons consulted:
- LESSON-716 — A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see (score 8)
- LESSON-717 — The executor shell can replace a coreutil with a function whose exit codes differ — a partial that branches on grep's status must call command grep, and the dogfood must run in that shell (score 8)
- LESSON-617 — `.` is a POSIX special built-in — `. A || . B` exits sh at the first arm, and both it and `[ -f A ] && . A || . B` double-source when A ends non-zero (score 8)
- LESSON-618 — One more shell in the test loop found a multi-line source chain that three exploration agents, the mapper, and a line-anchored extraction all missed (score 8)
- LESSON-605 — The octal-arithmetic trap is shell-divergent — zsh accepts what bash rejects, so dogfooding under the executor shell alone certifies the bug (score 8)

`adlc_remote_high` scopes `assume` to the current repo (BR-12), but the exact-id probe in
`adlc_recheck_id` kept its own walk over the repos root. The kind's `case` also had no `assume`
arm, so `adlc_rc_branch_grep` could carry over from an earlier recheck in the same shell. The
walk dates from REQ-518, before `assume` existed; REQ-546 added the kind and changed only
the allocator's walk.

## Resolution

`adlc_recheck_id` now walks the current repo for `assume`, as `adlc_remote_high` does, and every
other kind as before. `assume` joins `lesson` in the `case`. An assume collision names a by-hand
rename, because `adlc renumber` refuses ASSUME ids. Tests in `partials/tests/id-alloc.test.sh`
failed before the fix on the sibling case and the carried-over pattern, and now cover a real
collision in this repo's own origin and the remedy text.

## Files Changed

- `partials/id-recheck.sh` — scope, `case` arm, assume remedy, contract comment.
- `partials/tests/id-alloc.test.sh` — the regression cases.
- `partials/README.md`, `CHANGELOG.md` — behaviour notes.
- `.adlc/knowledge/lessons/` — LESSON-773.

## Deployment

None: the toolkit has no deploy targets. Vendored copies of `id-recheck.sh` in consumer repos
pick this up at the next `/template-drift` re-sync.
