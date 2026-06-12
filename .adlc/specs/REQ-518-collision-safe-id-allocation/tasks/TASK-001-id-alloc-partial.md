---
id: TASK-001
title: "Shared allocation partial (partials/id-alloc.sh) with remote high-water"
status: draft
parent: REQ-518
created: 2026-06-11
updated: 2026-06-11
dependencies: []
---

## Description

Create the single parameterized allocation helper that replaces the three
inline blocks (BR-5), extended with remote high-water derivation (BR-2) and the
`max(local, remote) + 1` rule (BR-1). The local counter becomes a cache.

## Files to Create/Modify

- `partials/id-alloc.sh` (NEW) — the sourceable helper.

## Acceptance Criteria

- [ ] Exports kind-mapper functions for `req|bug|lesson` → counter path, lock
      dir, id prefix, scan glob/type (one table; no copy-paste per kind).
- [ ] `adlc_remote_high <kind>` derives the remote high-water from `git ls-remote`
      branch patterns + merged artifact dirs (gh-api when available, ref-scan
      fallback), reading the REMOTE not local clones; stale local checkouts never
      lower the result (BR-2). Prints 0 when nothing/unreachable.
- [ ] `adlc_alloc_id <kind>` acquires the existing mkdir lock with the symlink
      pre-check + fail-loud guards ported VERBATIM with rationale comments
      (BR-1, LESSON-014/023), reads local_high (bootstrap-scan if counter
      absent), computes `max(local, remote) + 1`, fast-forwards the counter,
      releases the lock, prints the allocated number.
- [ ] On an unreachable remote, sets `ADLC_ALLOC_DEGRADED=1` and emits a warning
      naming the unreachable remote; allocation still succeeds from local state
      (BR-3). Never blocks on network.
- [ ] Single-machine parity: when the remote has no higher allocation,
      `adlc_alloc_id` yields exactly the value today's inline block would (BR-7).
- [ ] BSD/zsh-safe: prefixed globals (no `local`), no `\b` in `grep -E`, no bare
      `$<digit>`, no `[0]` indexing, no `status=` var; runs under `bash -c` AND
      `zsh -c` (BR-6). Modeled on `partials/trial-merge.sh` style.
- [ ] Documented contract header (usage example + return codes), matching the
      `trial-merge.sh` documentation standard.

## Technical Notes

Model the file on `partials/trial-merge.sh`: prefixed globals (`adlc_alloc_*`),
fail-loud, fully-documented contract header. Port the lock block from
`spec/SKILL.md` Step 2 verbatim (including its REQ-416 verify rationale comments)
rather than reimplementing (BR-1). Remote derivation reuses the `/manifest`
derive-don't-store model (ADR-2). Participating repos come from
`$ADLC_REPOS_ROOT` checkouts that have a remote (Assumptions). Keep
`adlc_remote_high` resilient to absent `gh` (degrade to `git ls-remote`).
