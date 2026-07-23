---
id: TASK-006
title: "Reservation test matrix (shell AC cases + doctor + renumber)"
status: draft
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001, TASK-002, TASK-003, TASK-004, TASK-005]
---

## Description

Extend the offline test harnesses to cover every REQ-546 acceptance criterion.

## Files to Create/Modify

- `partials/tests/id-alloc.test.sh`
- `tools/adlc/tests/test_checks.py`
- `tools/adlc/tests/test_renumber.py` (reserve-before-mutate — may live in TASK-004)

## Acceptance Criteria

- [ ] Two-clone race: two clones sharing one bare remote allocate concurrently; exactly one wins N, the other gets N+1; the remote shows two reservation refs. (BR-1, BR-2, BR-5)
- [ ] Same-object hazard: two pushes of an identical object to the same new ref both "succeed"; the distinct-payload (nonce) rule is shown to prevent that shape. (BR-2)
- [ ] Cross-machine visibility: clone A reserves (no branch, no merge); clone B's next allocation derives high-water ≥ A's number from the reservation namespace alone. (BR-3)
- [ ] Recheck reservation collision: `adlc_recheck_id` detects an id that exists only as a reservation ref and halts with the renumber instruction. (BR-3)
- [ ] Network-blackholed allocation succeeds, emits the degraded warning, and no reservation ref exists. (BR-4)
- [ ] Namespace-rejecting remote (pre-receive hook) degrades loudly rather than failing/looping. (BR-4)
- [ ] Existing single-machine matrix (lock contention, symlink refusal, empty counter, remote-ahead, local-ahead, unreachable, multi-branch, leading-zero, lesson listing, recheck) still passes. (BR-9)
- [ ] ASSUME two-clone race: two clones of the SAME repo concurrently allocate an ASSUME id; exactly one wins N, the other N+1; a sibling repo's assume namespace is never consulted. (BR-12)
- [ ] ASSUME historical high-water: a repo with merged `ASSUME-040-*` and zero reservation refs, allocated from a clone whose stale counter reads 5, allocates ≥ 041. (BR-12)
- [ ] Doctor reservations check: PASS against a writable remote, FAIL naming the layer against a push-rejecting remote, SKIP on a repo with no origin; probe ref absent afterward. (BR-13)
- [ ] The whole harness passes under both `zsh -c` and `bash -c` via `partials/tests/run.sh`; `python3 -m pytest tools/adlc/tests` green; `tools/lint-skills/check.py` clean.

## Technical Notes

- Reuse the existing sandbox helpers (`new_sandbox`, `make_remote_with_branch`,
  `make_remote_with_artifacts`). Add a two-clone helper sharing one bare remote.
- The two-clone race: launch both allocators with `&`, `wait`, assert distinct
  ids and two reservation refs via `git ls-remote`.
- The pre-receive-decline fixture: install an `exit 1` `pre-receive` hook in the
  bare remote's `hooks/`.
