---
id: TASK-002
title: "adlc_recheck_id: consume two-token contract, reachable degraded branch, shared artifact probe"
status: draft
parent: REQ-523
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Update `adlc_recheck_id` in `partials/id-recheck.sh` to consume the new
`<high_water> <degraded>` stdout contract from `adlc_remote_high`, making its
degraded short-circuit reachable (it was dead code under the broken env-var
contract), and route its exact-id presence probe through the same forge-aware
artifact-scan path so ADO and gh-absent artifacts are seen (BR-6 — no
recheck-only copy of the derivation logic).

## Files to Create/Modify

- `partials/id-recheck.sh` — parse the two-token `adlc_remote_high` output;
  derive `degraded` from the second token (not the removed `ADLC_ALLOC_DEGRADED`
  env var); never compute a renumber suggestion from a degraded/zero high-water;
  reuse the shared artifact-scan helper for the exact-id probe.

## Acceptance Criteria

- [ ] BR-2: `adlc_recheck_id` reads degraded from the `adlc_remote_high` stdout
      payload; the degraded branch (warn + return 0) is reachable and taken when
      the derivation degraded.
- [ ] BR-2: renumber suggestion is never derived from a degraded high-water (a
      degraded derivation takes the degraded branch BEFORE the collision/probe
      path, so no `renumber … REQ-001`-from-zero is emitted).
- [ ] BR-6: the exact-id probe uses the same forge-aware artifact scan as
      `adlc_remote_high` (gh fast-path + git-transport fallback + ADO), not a
      gh-only copy.
- [ ] AC: under a degraded derivation, recheck returns 0 (cannot find a collision
      from absence of data) and emits no zero-derived renumber suggestion.
- [ ] BR-7: POSIX/BSD/zsh-safe; multi-element-safe probe.

## Technical Notes

- Replace the `ADLC_ALLOC_DEGRADED=""` reset + `adlc_rc_high=$(adlc_remote_high …)`
  + post-hoc `[ -n "$ADLC_ALLOC_DEGRADED" ]` check with: capture the two-token
  output, split into `adlc_rc_high` (token 1) and `adlc_rc_degraded` (token 2),
  validate token 1 numeric (loud-fail guard updated for the space), then branch on
  `adlc_rc_degraded`.
- The existing inline gh-only artifact probe in the exact-id walk
  (lines ~135–155) should call the shared `adlc_remote_artifact_nums` helper from
  TASK-001 so ADO/git-fallback artifacts are matched, rather than duplicating the
  gh-api block.
- Keep the branch (ls-remote) exact-id probe as is; it is the req/bug source.
- Degraded short-circuit must run BEFORE the exact-id walk so a degraded
  derivation never produces a renumber suggestion (the M1 dead-code bug).
