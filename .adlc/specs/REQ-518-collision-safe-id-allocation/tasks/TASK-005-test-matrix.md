---
id: TASK-005
title: "Test matrix: pytest for renumber + bash/zsh harness for the alloc/recheck partials"
status: draft
parent: REQ-518
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001, TASK-002, TASK-003]
---

## Description

Cover the acceptance-criteria test matrix: the partials' allocation/recheck
behavior under lock contention, symlink refusal, empty counter, remote-ahead,
local-ahead, and remote-unreachable; plus the renumber helper end-to-end. Run
the shell harness under BOTH bash and zsh (BR-6, Linux-parity AC).

## Files to Create/Modify

- `tools/adlc/tests/test_renumber.py` (NEW) — pytest, offline, sandbox tmp repo.
- `partials/tests/id-alloc.test.sh` (NEW) — POSIX harness, runnable under
  `bash -c` and `zsh -c`.

## Acceptance Criteria

- [ ] pytest: id-regex validation (accept valid, reject garbage/traversal);
      dry-run-then-apply renames dir, rewrites frontmatter + both references;
      repo-wide grep finds zero remaining old id; collision-refusal when the new
      id collides on the (stubbed) remote; `adlc renumber` is registered in
      `SUBCOMMANDS` (dispatch test).
- [ ] Shell harness covers: lock contention (two concurrent allocators get
      distinct ids), symlink-swap refusal, empty-counter refusal, remote-ahead
      (machine-B-lags scenario → id strictly above remote `feat/REQ-*`),
      local-ahead (remote has no higher → unchanged id, BR-7), remote-unreachable
      (degraded warning + local-only success, BR-3).
- [ ] The shell harness uses fixture `~/.claude` counters (sandbox HOME) and a
      local bare-repo "remote" — no network, no real `~/.claude` mutation
      (mirrors the tools/adlc offline-test discipline).
- [ ] The harness passes under `bash -c '...'` AND `zsh -c '...'` (BR-6,
      Linux-parity AC) — the runner invokes both.
- [ ] `python3 -m pytest tools/adlc/tests` is green.

## Technical Notes

Mirror `tools/adlc/tests/conftest.py` + `test_doctor.py`/`test_dispatch.py`
conventions for the pytest side (sys.path insert, offline fixtures,
`monkeypatch` for the remote-collision shell-out). The two-machine AC is
simulated with two clones of one local bare repo + two independent counter
fixtures. Blackholed-network is simulated by pointing the remote at an
unreachable URL (or a non-existent path) and asserting the degraded warning +
local-only success.
