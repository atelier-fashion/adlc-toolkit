# REQ-720 architecture: the answer token and the verified dispatch

Parent: `requirement.md`. Engine read at `913cae3`. Everything here lands in
`tools/adlc/sprint_exec.py`, its tests and the documents BR-24 names. No new module, no new
dependency, no change to `exec_trust.py`, `exec_surfaces.py`, `exec_prompt.py`, any adapter or
any rendered file.

## Approach

The approve token already has the shape this requirement needs: `exec_ledger.mint_token()`
makes 128 random bits, `token_digest()` hashes them, the digest sits in the supervisor's memory
and the token is printed once by `Orchestrator.say`. The answer token reuses both functions and
adds a second in-memory map beside `self.tokens`. What is new is *where the mint is attached*
(the status change, ADR-1), *how the client hands the token over* (standard input, ADR-2) and
*what `dispatch` does when the kernel names no caller* (ADR-5, ADR-6).

## Measurements the spec asked for

The spec's Assumptions hand two measurements to this phase. What was run on 2026-11-27, on the
development host (macOS 27.2, Python 3.9.6), and what was not:

| Question | Measured | Result |
|---|---|---|
| Does `LOCAL_PEERPID` report the client's pid for a live peer? | A listener on an `AF_UNIX` stream socket, three clients (a direct child, a backgrounded subshell, a `sh -c` child), each sending its own `os.getpid()` | The kernel's pid equalled the client's in all three |
| Does it hold between two separate commands of the operator's harness (the `/sprint` skill channel, where the supervisor is one background command and each client another)? | The listener started as one background shell-tool command of a Claude Code session, the clients from a later, separate command | Same result: the pids matched |
| Does BR-18's self-connect read the supervisor's own pid? | The listener connected to its own socket | `own == kernel` |
| Does a stdin form keep the token out of every argument list? | Three forms (a here-document, `printf … \|`, `echo … \|`), each fed to `sh`, `bash`, `zsh`, `dash` (and `echo` also to `ksh`, `csh`, `tcsh`) on the shell's standard input, with a client that lists every process's arguments | No process showed the token under any shell; the control (the token as an argument) was visible |

**Not measured, and why.** (1) Linux: no Linux host was available and no container runtime was
running; `SO_PEERCRED`'s behaviour (the pid in the reader's namespace, 0 when it is not visible
there) is taken from the kernel's documentation. (2) The Codex skill channel: no Codex launch is
permitted before 2026-11-30. Neither is a finding that "a supported launch reports no pid for
the operator's own client", which is the spec's condition for returning BR-17 and BR-18 to it,
so the design proceeds. Both gaps are declared in the README (BR-23), and the failure they could
hide is closed, not open: a supervisor whose clients are in another pid namespace refuses every
dispatched operation, names `dispatch_unverified_peer`, and `reject` and `abort` still work with
the supervisor stopped.

## ADR-1: the mint is an observer on the run's status, not a line per path

`Run.status` already has a setter. It gains an optional observer: `Run.on_status`, called as
`on_status(run, before, after)` when the value changes. The orchestrator installs its observer on
every run it holds, by making `self.runs` a small `dict` subclass whose `__setitem__` binds it,
so the three sites that add a run (`_prepare`, `_run`'s lazy load, `resume`) cannot forget.

- Entering `blocked` from any other status mints a token, stores its digest in
  `self.answer_tokens[req]` and parks the token text in `self.unannounced[req]`.
- Leaving `blocked` for any status drops both entries and removes `answerRefusals` from the run
  record. This is the structural backstop for BR-3; the relaunch also spends the token
  explicitly at its commit point (ADR-3), before the status moves.

**Why an observer.** BR-1 asks that a path added later starts minted. Two functions set
`blocked` today (`_terminal`, reached through `_block` from eleven call sites, and `_hold`). A
mint written in those two would be a census taken on the day it was written (LESSON-781,
LESSON-712). The setter is the one place every path goes through. The alternative, a
`_set_blocked()` helper that every site must call, was rejected: a new `run.status = "blocked"`
would compile and skip it.

**Printing stays explicit.** The row must be printed after `_carry` has written the blockers,
which is after the status changes. `_announce_blocked(run)` pops the parked token and prints
the row; `_terminal` calls it when the status is `blocked`, and `_hold` calls it. A path that
set `blocked` and forgot to announce would hold a token nobody saw, and `reissue` recovers it;
the test for BR-1 asserts the digest, and a second asserts that nothing is left in
`self.unannounced` after each of the blocked paths AC-1 lists.

The digest is bound to its purpose and run: `token_digest(token, "answer:" + req)`. An approve
token is never an answer token, and one run's token never answers another, by construction
rather than by the odds.

## ADR-2: the token reaches the client on standard input, as one line

The dashboard's `answer` line becomes:

```
  answer it: echo '<32 hex>' | adlc sprint-exec answer --channel skill 'REQ-xxx' '<reply>'
```

`adlc sprint-exec status` prints the same line with `<token>` in place of the hex digits,
followed by the line it already prints for a run at the gate.

**Why `echo … |` and not the here-document the spec named as the candidate.** A row is its
`| REQ |` line and the *indented* lines under it; `status_rows` and the skill's relay both read
it that way. A here-document's terminator cannot be indented, so its three lines would have to
be printed flush left, which ends the row for every reader, and an operator who copied the
indentation would be left at a `heredoc>` prompt. `echo` is a builtin of `sh`, `bash`, `zsh`,
`dash`, `ksh`, `csh` and `tcsh` (measured above), so the token is an argument of no process,
and the line stays one line that the CLI's parser reads from `sprint-exec` on, as REQ-719 BR-5
requires of every way out. `printf` was rejected because it is not a builtin of `csh`/`tcsh`.
A shell whose `echo` is an external program would show the token for the life of that `echo`;
none of the seven does, and the README says so.

**The client.** `answer` reads one line from standard input and strips it. When standard input
is a terminal it prompts on stderr and reads without echo (`getpass`), so an operator may also
type the token. When it is a pipe that never delivers a line, the client waits ten seconds and
sends the empty token, which the supervisor refuses like any other wrong one. `answer` accepts
`--token` only to refuse it: nothing is sent, exit 2, and the message says the process list has
shown the token and names `reissue` (BR-5).

**The skill.** `sprint/references/exec-engine.md` documents the same one-line form inline, as it
documents `answer` today, and adds no fence, so neither adapter's fence census changes (BR-25).

## ADR-3: one commit point in `_relaunch`

`_relaunch` runs, in order: the adapter gate, the prompt build, the prompt file write,
`prepare_surfaces`, `grant_trust`, `_launch_first`. Today a `Refused` from any of the first five
leaves the run `blocked`, and only a failure inside `_launch_first` ends it `failed`.

The commit point is immediately before `_launch_first`. There, and only there:

1. the run's answer token is dropped from `self.answer_tokens` (BR-6, BR-10);
2. when the relaunch came from `answer`, the entry is appended to the run record's `answers`
   and `answer_accepted` is logged (BR-8).

So every refusal that leaves the run `blocked` leaves the token unspent, including a surface or
trust refusal, and a start failure ends the run `failed` with the token already gone. The engine's
own relaunch (`_rebase_and_relaunch`, `text is None`) goes through the same point with no
`answers` entry. It is not reachable from `dispatch`: the `answer` op always carries a string
reply and always passes the token check first.

`Orchestrator.answer` gains `token`, `answered_by` and `channel`, keyword-only in practice
(appended after the existing parameters). The check sits under the lock, after `caller_guard`,
`_rebasing_guard` and the status check, exactly where BR-5 puts it. On a mismatch it increments
`answerRefusals` in the run record, logs `answer_refused` (req, channel, the kernel's pid) and
raises `Refused` with approve's wording plus `reissue`. It records no Rule B violation.

## ADR-4: `reissue`, `resume` and `abort`

- `reissue` accepts `awaiting_approval` and `blocked`. For a blocked run it mints (replacing the
  digest), announces the row, and returns `fresh tokens are on the supervisor's dashboard` as
  its result. Any other status is refused naming it, as today.
- `resume` mints and announces for every `blocked` run it takes over, after the self-check of
  ADR-6. A run record with none of the new keys loads as it is (BR-19).
- `abort` needs no code for the token: `_aborted` sets `failed`, and the observer drops it.
- Each mint logs `answer_token_minted` with its cause (`blocked`, `resume`, `reissue`).

## ADR-5: `dispatch` trusts the kernel's pid and nothing else

`pid = pid or request.get("callerPid")` is removed, and `_op_allowance` records `pid`, never
`inv.get("pid")`. `ping` is answered first. For every other op, a `pid` that is not an integer
greater than zero is refused before anything is read from the run:

```
dispatch_unverified_peer: <op> refused: the kernel reported no process id for the caller
```

`abort`'s refusal adds the way round (stop the supervisor, run `abort` again). The event is
logged in the named run when the request names one this supervisor holds, with the request's
own `callerPid` under `claimedPid`. No violation is written and no token is touched.

`ping` now returns `{"ok": true, "pid": …, "answerTokens": true}`. `answerTokens` is the
capability field BR-20 leaves to this document. The client reads it before `answer`, and before
`reissue` when the run record says `blocked`; a live supervisor without it is refused naming
`resume`, and nothing else is sent.

## ADR-6: the supervisor proves its own read before it holds anything

`Orchestrator.self_check(server)` connects to the socket `bind()` just made, accepts, and
requires `peer_pid()` to return this process's pid. `_dispatch` calls it for `run` and `resume`
directly after `bind()`, inside the existing `try`, so a failure closes the socket and removes
the supervisor's directory by the code that already does both. It runs before `preflight` and
before `resume()`, so no run directory is prepared, no run is taken over and no token is minted.

## The run record (additive)

| Key | Type | Written by | Absent means |
|---|---|---|---|
| `answers` | list of `{launch, answeredAt, answeredBy, channel, callerPid}` | `_relaunch`'s commit point | none |
| `answerRefusals` | int | a refused token; removed when the run leaves `blocked` | 0 |

Neither is carried into `pipeline-state.json`. `render_row` shows, for a blocked run,
`refused answers since it blocked: <n>`, and for any run with an `answers` entry the last one.
`answeredBy` and `channel` come from the client's request, so both pass through `_one_line`.

## The verb census (BR-13)

The engine gets one constant, `VERBS`, that `_parser()` is built from. A test classifies each
verb as minting, spending or neither, and checks every minting or spending verb against each
shipped adapter's `engine_deny`. The check is a function of `(verbs, engine_deny)`, so the two
failing fixtures AC-11 names are plain arguments to it.

## What does not change (BR-25)

The pipeline prompt and the relaunch prompt's text, `.claude/settings.json`, both census
goldens, every adapter file, the allow and deny tiers, and `approve`'s `--token`. The token
never reaches `exec_prompt.pipeline_prompt`: `_relaunch` passes it nothing but the reply.

## Task graph

```
TASK-286 engine: mint, row, answer, reissue, resume   ──┬─> TASK-287 dispatch + self-check ─> TASK-288 client + residual test
                                                        ├─> TASK-289 verb census and no-widening tests
                                                        └─> TASK-290 documents and amendments
```

TASK-287 and TASK-288 follow TASK-286 in sequence because all three edit `sprint_exec.py`.
TASK-289 and TASK-290 touch no file the others do and can run beside TASK-287.

## Lessons applied

- LESSON-781, LESSON-712: the mint is on the status change, and the verb list is a constant a
  test classifies, so a new verb or a new blocking path cannot arrive unguarded.
- LESSON-403: no hand-kept count of verbs or paths is written into a document.
- LESSON-891: AC-3 and AC-17 run the printed line and the real client as subprocesses against a
  real supervisor process, not only in-process calls.
