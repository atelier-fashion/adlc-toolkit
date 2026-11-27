---
id: TASK-287
title: "`dispatch` uses the kernel's pid alone, and the supervisor proves the read before it starts"
status: draft
parent: REQ-720
repo: adlc-toolkit
created: 2026-11-27
updated: 2026-11-27
dependencies: [TASK-286]
---

## Description

Implement architecture ADR-5 (the supervisor side) and ADR-6 in `tools/adlc/sprint_exec.py`:
the request's `callerPid` is never used, an unreadable or non-positive peer pid refuses every
op but `ping`, and `run` and `resume` self-check the read before they prepare or take over
anything.

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — `dispatch` (the `ping` arm first, the unverified-peer refusal, no `request.get("callerPid")` fallback, `answer` passed `token`, `decidedBy` and `channel`); `_op_allowance` (the kernel's pid only); `_unverified_peer`; `Orchestrator.self_check`; `_dispatch` (the call after `bind()` for `run` and `resume`).
- `tools/adlc/tests/test_req720_answer_token.py` — the cases below, appended.
- `tools/adlc/tests/test_exec_approve.py` — the `dispatch(request, None)` call site passes a real pid.
- `tools/adlc/tests/test_exec_launch.py` — the same.

## Acceptance Criteria

- [ ] A request whose `callerPid` names another live process: an accepted `approve` writes the pid passed to `dispatch` as `callerPid` in the ledger, an accepted `answer` writes it in the run record's `answers` entry, and a request with `callerPid` absent or wrong is not refused for that. Run once through a real socket (`bind`, `serve_once`, `client_call`) so the pid is the kernel's.
- [ ] With `sprint_exec.peer_pid` stubbed to return `None`, and again `0`, each of `approve`, `answer`, `reject`, `abort` and `reissue` sent through the socket is refused with one line starting `dispatch_unverified_peer: <op> refused`. Status, ledger and `launches` are unchanged, the log of the named run holds one `dispatch_unverified_peer` event per attempt with the request's `callerPid` under `claimedPid`, `violations.jsonl` gained nothing, and `ping` still answers. With the stub removed, the tokens printed before still work.
- [ ] The refusal of `abort` names stopping the supervisor and running `abort` again; with a blocked run and the supervisor closed, the CLI's `abort` then ends it `failed`.
- [ ] With the peer pid readable, every one of those operations from a process outside every run proceeds.
- [ ] With the self-check's read stubbed to fail, `main(["run", ...])` and `main(["resume"])` each return 2 with a message naming the reason; no run directory was prepared, no harness launched, no token printed, and the supervisor's directory is gone. Without the stub both get past the check.
- [ ] `python3 -m pytest tools/adlc/tests/test_req720_answer_token.py tools/adlc/tests/test_exec_approve.py tools/adlc/tests/test_exec_launch.py -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-16 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_recorded_pid_is_the_kernels` | yes |
| BR-17 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_unverified_peer_is_refused_every_op_but_ping` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_supervisor_that_cannot_read_a_peer_pid_does_not_start` | yes |
| AC-13 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_recorded_pid_is_the_kernels` | yes |
| AC-14 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_unverified_peer_is_refused_every_op_but_ping` | no |
| AC-15 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_verified_peer_is_refused_nothing` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_supervisor_that_cannot_read_a_peer_pid_does_not_start` | yes |

## Technical Notes

- Read `architecture.md` ADR-5 and ADR-6 first. `serve_once` already passes `peer_pid(conn)` to `dispatch`; tests stub the module-level `peer_pid` with `monkeypatch.setattr`.
- `dispatch`: `ping` returns first. Then `if type(pid) is not int or pid <= 0: self._unverified_peer(op, request)`, before `nested_guard` and before any run is read. A `bool` is not a pid.
- `_unverified_peer(op, request)`: resolve `request.get("req")` only against `self.runs` (a run this supervisor holds); when found, `Toolbox(run.path, self.toolkit, self.environ).log("dispatch_unverified_peer", [str(op)], None, None, detail={"op": op, "req": req, "claimedPid": request.get("callerPid")})`. Raise `Refused("dispatch_unverified_peer: %s refused: the kernel reported no process id for the caller, so it cannot be shown to be outside a run")`, and for `abort` append `; to end the run, stop the supervisor and run `adlc sprint-exec abort <REQ>` again: with no supervisor it acts in your own process`. The message must not start with `PROTOCOL`, and no `run.violation` is written.
- `_op_allowance`: `"pid": pid`, with no `inv.get("pid")` fallback.
- `self_check(self, server)`: `conn = unix_connect(self.sup_dir, 5)`; `peer, _ = server.accept()`; read `peer_pid(peer)`; close both; when it is not `os.getpid()`, raise `Refused("peer_pid_unreadable: the kernel reported %r for this supervisor's own connection, not its pid %d, so no caller could be verified: nothing was prepared and nothing launched")`. `_dispatch` calls it as the first statement inside the existing `try` after `orch.bind()`, for `run` and for `resume`, so the existing `except BaseException` closes the socket and removes the directory.
- For the `main([...])` cases use `monkeypatch.chdir` into the sandbox repo and `monkeypatch.setenv` for each key of `box.environ`; `Orchestrator(primary)` reads `os.environ`.
- Do not edit `exec_trust.py`, `exec_surfaces.py` or `harness/*.yml`. Do not commit.
