---
id: TASK-288
title: "The client reads the answer token from standard input and asks the supervisor what it holds"
status: draft
parent: REQ-720
repo: adlc-toolkit
created: 2026-11-27
updated: 2026-11-27
dependencies: [TASK-287]
---

## Description

Implement architecture ADR-2's client and ADR-5's capability read in `_client` and `_parser`,
and add the three tests that run real processes: the printed `answer` line run by a shell, the
older-supervisor fixture, and the declared residual of BR-23(a).

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — `_parser` (`answer --token`, accepted only to be refused); `_read_answer_token`; `_client` (the argument refusal, the `ping` capability read before `answer` and before `reissue` of a blocked run, the token read, the request's `token`).
- `tools/adlc/tests/test_req720_answer_token.py` — the cases below, appended.

## Acceptance Criteria

- [ ] `answer` with `--token <value>` exits 2, sends no request (the supervisor's refusal count stays 0 and no `answer_refused` is logged), and its message says the process list has shown the token and names `reissue`.
- [ ] `_read_answer_token` returns the first line of a pipe, stripped; the empty string at end of file; the empty string after its timeout when a pipe never delivers a line; and on a terminal it reads through `getpass` with a prompt on stderr.
- [ ] Subprocess: a supervisor process (`sprint-exec run`, stdout to a file) whose fake-harness run blocks. The `answer it:` line is read from that file, `<reply>` replaced, the text after `answer it: ` written to a script file and run as `sh < script` with a throwaway `adlc` shim first on `PATH`. The run relaunches: a new harness pid, `exec.pid` and `sessionId` overwritten, the reply in the new prompt file. While the client ran, a process listing showed the token in no argument list (the client is held open with a hook the test controls, or the listing is taken by a wrapper the shim calls). The same relaunch works with `--channel skill` and with the default channel.
- [ ] Subprocess: `answer` with standard input from `/dev/null` exits 2 and the run stays `blocked`.
- [ ] Against a fixture supervisor (a thread on a real `AF_UNIX` socket) whose `ping` reply is `{"ok": true, "pid": n}`, the client's `answer` exits 2, names `resume`, and the fixture received no `answer` request; `reissue` of a blocked run likewise; `approve`, `reject` and `abort` are sent as before. Against this engine's supervisor the capability read refuses nothing.
- [ ] `test_a_detached_process_can_stop_the_supervisor_and_resume` (docstring cites BR-23(a)): with a blocked run under a supervisor process, a second process started with `ADLC_EXEC_RUN` and `ADLC_EXEC_RUN_TAG` removed from its environment and with `start_new_session=True` sends the supervisor SIGTERM, waits for it to exit, runs `sprint-exec resume` with stdout to a file, reads the `answer it:` token from it, and relaunches the run with `answer`. The test asserts the relaunch happened. It measures the residual as it stands; it is expected to pass.
- [ ] `python3 -m pytest tools/adlc/tests/test_req720_answer_token.py -q` passes, and every process a test started is gone when the test ends.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_printed_answer_line_relaunches_the_run` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_token_given_as_an_argument_is_refused_unsent` | yes |
| BR-20 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_older_supervisor_is_not_sent_an_answer` | yes |
| BR-21 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_answer_without_the_current_token_is_refused` | yes |
| BR-23 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_detached_process_can_stop_the_supervisor_and_resume` | no |
| AC-3 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_the_printed_answer_line_relaunches_the_run` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_token_given_as_an_argument_is_refused_unsent` | yes |
| AC-17 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_a_detached_process_can_stop_the_supervisor_and_resume` | no |
| AC-18 | test-case | `tools/adlc/tests/test_req720_answer_token.py::test_an_older_supervisor_is_not_sent_an_answer` | yes |

## Technical Notes

- Read `architecture.md` ADR-2 and ADR-5 first.
- `_parser`: `answer` gains `cmd.add_argument("--token", default=None, help=argparse.SUPPRESS)`.
- `_client`, for `answer`, in this order: the `--token` refusal (`Refused("%s: the token was given as an argument, so the process list has shown it. Run `adlc sprint-exec reissue %s` for a fresh one, and hand it to `answer` on standard input, as the dashboard's line does")`); the existing `caller_guard`; the capability read; the token read; then the request with `"token": token`.
- The capability read: `pong = client_call(run, {"op": "ping"})`. `None` falls through to the existing "no live supervisor" refusal. A reply whose `answerTokens` is not `True` raises `Refused("%s: the supervisor holding it was started by an older engine and holds no answer token. Stop that supervisor, then run `adlc sprint-exec resume`, which prints fresh tokens")`. It runs for `answer`, and for `reissue` when `run.status == "blocked"`.
- `_read_answer_token(stream=None, timeout=10)`: `stream = sys.stdin`. A terminal: `getpass.getpass("answer token: ", stream=sys.stderr)`. Otherwise `select.select([stream], [], [], timeout)` then `readline()`, capped at 256 characters, stripped. Never echo the value, and never put it in an exception.
- The supervisor subprocess pattern is at `tools/adlc/tests/test_exec_launch.py` near line 2851 (`subprocess.Popen([sys.executable, ENTRY, "sprint-exec", "run", ...], env=dict(box.environ, PYTHONPATH=""), stdout=fh)`), and `eh.until(predicate, timeout, what=...)` waits. Every `Popen` goes in a `try`/`finally` that terminates it.
- The `adlc` shim is two lines written into a throwaway directory: `#!/bin/sh` and `exec "<sys.executable>" "<ENTRY>" "$@"`.
- A test's tokens are the ones its own supervisor printed (BR-26). No test reads a credential or anything under the real home.
- Do not commit.
