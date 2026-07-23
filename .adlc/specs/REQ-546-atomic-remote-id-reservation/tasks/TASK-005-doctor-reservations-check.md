---
id: TASK-005
title: "adlc doctor reservations pushability check"
status: draft
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001]
---

## Description

`adlc doctor` gains a `reservations` check that probes whether the reservation
ref namespace is readable and writable, so a machine that silently cannot push
reservations is caught rather than allocating permanently degraded (BR-13).

## Files to Create/Modify

- `tools/adlc/checks.py`

## Acceptance Criteria

- [ ] `check_reservations` resolves `origin`, probes readability (`ls-remote refs/adlc/ids/*`) and writability via an ephemeral probe ref that is ACTUALLY pushed and deleted on success (`refs/adlc/ids/_probe/<nonce>`) — NOT `--dry-run`.
- [ ] Reports PASS (readable + writable), FAIL naming the failing layer (transport | auth | server policy), SKIP-with-reason on a remote-less repo.
- [ ] The probe ref is absent from the remote after the check (the one sanctioned deletion).
- [ ] Registered in `REGISTRY` after `forge`.
- [ ] Pure stdlib + subprocess (no dependency on the thing it diagnoses).
- [ ] Covered by `tools/adlc/tests/test_checks.py` (PASS, FAIL-with-layer, SKIP).

## Technical Notes

- Probe object: prefer the remote HEAD tip (`git ls-remote origin HEAD`) so the
  push is a pure ref-create with no object upload; fall back to `commit-tree`
  (identity) then empty-tree; SKIP if the remote has no ref to probe with.
- Failure classifier from stderr: `auth` (Authentication failed / Permission /
  403), `server policy` (pre-receive hook declined / [remote rejected]),
  `transport` (Could not read from remote / does not appear to be a git repo),
  else `unknown`.
- Cleanup delete: `git push origin --delete refs/adlc/ids/_probe/<nonce>`.
