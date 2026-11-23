---
id: REQ-720
title: "A blocked exec run is answered with a one-time token from the operator's dashboard, and a dispatch whose caller the kernel cannot name is refused"
status: draft
deployable: false
created: 2026-11-23
updated: 2026-11-23
component: "adlc/sprint"
domain: "adlc"
stack: ["python", "markdown"]
concerns: ["security", "orchestration", "unattended"]
tags: ["exec-engine", "sprint-exec", "answer", "approve", "token", "blocked", "abort", "reject", "reissue", "resume", "same-uid", "approval", "rule-b", "dashboard", "supervisor", "peer-pid", "dispatch"]
lane: "full"
lane_reason: "changes how the exec engine authenticates an operator verb and what its supervisor's dispatch guard does (criterion 2, auth and security), and adds a field to the supervisor's request contract (criterion 1)"
lane_forced: false
---

## Description

The exec engine (`tools/adlc/sprint_exec.py`, REQ-659) stops a run in two places where it
waits for a person. At the merge gate the run is `awaiting_approval`, and `approve` needs a
one-time token that the supervisor prints only on its own stdout, the dashboard. When the
session stops on a question the run is `blocked`, and `answer` relaunches the harness with the
operator's reply. `answer` needs nothing.

The security review of REQ-662 stage 1 confirmed what that leaves open. A process the model
starts can clear `ADLC_EXEC_RUN` and detach: re-parented to pid 1 and out of the process
group, it is found by neither the caller guard, the nested-launch guard, the process-group
kill nor the straggler sweep. Once its run blocks there is no live exec pid for its ancestry
to reach, so `adlc sprint-exec answer <REQ> "<text>"` from that process is accepted, and the
supervisor starts a new harness whose prompt presents text the model wrote as the operator's
answer. REQ-662 BR-19 and the README declare this as a residual on every harness and name an
answer token as the follow-up. This requirement is that follow-up.

What was read in the engine at `1d40f47`, and what each finding means here:

- `answer` checks the caller guard, the rebasing guard and the status, then relaunches. It
  takes no token, and it records nothing about who answered: the `decidedBy` and `channel`
  the client sends are dropped.
- Tokens are minted at the halt, at a re-halt, by `resume` and by `reissue`, for runs at the
  gate only. Their digests live in the supervisor's memory and nowhere else.
- A run that becomes `blocked` prints one line, `<REQ> blocked`. The row with the two ways
  out is printed by `status`.
- `reissue` refuses a run that is not `awaiting_approval`, and `resume` mints nothing for a
  blocked run.
- In `dispatch`, when the kernel's peer pid cannot be read, the ancestry walk is skipped, and
  the pid the request itself claims is then used for the caller guard and written to the
  ledger as `callerPid`. REQ-662 left this open as "a dispatch with no peer process id".
- `abort` already drops a blocked run. REQ-719 BR-1 added that arm and it shipped in pull
  request #304, so an operator does have a command to end a blocked run. REQ-719 BR-4 left
  one thing to this requirement: whether an operator verb other than `approve` needs a token.

**What this requirement decides.**

1. A run entering `blocked` mints an answer token the way the halt mints an approve token. It
   is printed only on the supervisor's dashboard, and `answer` is refused without it.
2. `reissue` and `resume` cover a blocked run as they cover a run at the gate.
3. `reject` and `abort` take no token. They start nothing and move nothing, and `abort` must
   work when no supervisor is alive to hold a digest.
4. `abort` stays the operator's command to end a blocked run, unchanged.
5. The supervisor uses only the pid the kernel reports. A dispatch whose peer pid cannot be
   read is refused, and a supervisor on a platform that cannot report one does not start.
6. Nothing is migrated. A run blocked under the older engine gets its first token from a new
   supervisor's `resume`.

**What the token buys, stated plainly.** It raises `answer` to the bar `approve` already has,
and no higher. One command from a detached process no longer relaunches a run. A process
running as the operator's own user can still attack the operator's surfaces: stop the
supervisor and start one of its own, read a captured dashboard, read a command line. Those
limits hold for the approve token today. This requirement declares them (BR-23) and does not
close them.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| AnswerToken | value | string | 128 random bits from the OS source, minted by the function that mints an approve token; printed once, on the supervisor's stdout; never written to disk by the engine |
| AnswerToken | digest | string | held in the supervisor's memory only, beside the approve digests; never in the run record, the ledger, state or a log |
| AnswerToken | run | REQ id | one live token per blocked run; a new mint replaces it; it answers no other run |
| AnswerToken | lifetime | — | from a mint (the run becomes `blocked`, `resume`, `reissue`) until it is spent by an accepted `answer`, replaced, or discarded when the run leaves `blocked` or the supervisor exits |
| ExecRun (run record, additive) | answers | list | one entry per accepted `answer`: `{ launch, answeredAt, answeredBy, channel, callerPid }`; optional, absent reads as none; never the token, its digest or the reply text |
| ExecRun (run record, additive) | answerRefusals | int | how many `answer` requests for the current blocked episode were refused for a missing or wrong token; reset when the run leaves `blocked`; optional, absent reads as 0 |
| SupervisorReply (`ping`) | answer-token capability | boolean | present and true on a supervisor that holds answer tokens; absent on an older one. The field's name is an architecture decision |
| DispatchRequest (`answer`) | token | string | the token the operator typed; checked by the supervisor, never by the client alone |
| DispatchRequest (any op) | callerPid | int | the client's own claim; never used for a guard and never recorded as the caller's pid (BR-16) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| answer_token_minted | a run becomes `blocked`, or `resume` or `reissue` mints for a blocked run | req, cause (`blocked` \| `resume` \| `reissue`); never the token or its digest |
| answer_accepted | an `answer` with the current token passes every check | req, launch number, answeredBy, channel, callerPid as the kernel reported it |
| answer_refused | an `answer` is refused for a missing, wrong, spent or replaced token | req, channel, callerPid as the kernel reported it; never the value presented |
| dispatch_unverified_peer | the supervisor cannot read the peer pid of a connection | op, req when the request names one that resolves; the pid the request claimed, marked as a claim |

### Permissions

| Action | Allowed |
|--------|---------|
| Relaunch a blocked run with a reply | whoever presents the run's current answer token to its supervisor from outside every exec run; the engine itself, with no reply text, when the run's blocker has merged (BR-10) |
| Read an answer token | whoever reads the supervisor's stdout. No engine verb returns one to its caller |
| Drop a blocked run (`abort`) or decline a run at the gate (`reject`) | any caller outside the run, with no token (BR-14) |
| Have a dispatched operation performed | a caller whose pid the kernel reports to the supervisor (BR-17) |

## Business Rules

_The token_

- [ ] BR-1: Every entry of an exec run into `blocked` mints one answer token for that run. This holds for every path: a harness that exits with `blocked` in state or as its terminal claim, a protocol violation or stragglers found at exit, a harness the adapter reads as denied, a halt whose plan or ledger write is refused, a re-halt to `blocked` by the merge worker after an approval, and a held run whose rebase conflicts. The mint happens at the one place the engine sets the status, not once per path, so a path added later starts minted, and a test fails when a run reaches `blocked` with no token held. (informed by LESSON-781, LESSON-712)
- [ ] BR-2: The token is printed once, on the supervisor's stdout, and only its digest is kept, in the supervisor's memory. Neither the token nor its digest is written to the run record, the approval ledger, either copy of `pipeline-state.json`, the command log, an event, a harness log, the run-outcome log, or any prompt, the relaunch prompt included. No verb returns it to its caller: not `status`, not `reissue`, not a refusal message. (informed by REQ-659)
- [ ] BR-3: A run holds at most one live answer token. A new mint replaces the one before it. The token is discarded when the run leaves `blocked` by any route (an accepted `answer`, the engine's own relaunch of BR-10, `abort`) and when the supervisor exits. A token minted for one run never answers another, and a token printed for one blocked episode is not valid for a later one.
- [ ] BR-4: When a run becomes `blocked`, the supervisor's dashboard prints that run's row: its blockers, its notes, and both ways out. The `answer` line carries the token as `--token <token>`, placed before the REQ id as `--channel` is (REQ-719 BR-5). The `abort` line carries none. `adlc sprint-exec status` prints the same row with no token, followed by the line it prints for a run at the gate: tokens are on the supervisor's dashboard, and `reissue` prints fresh ones. (informed by REQ-719)

_`answer`_

- [ ] BR-5: `answer` requires the run's current answer token. The supervisor makes the check itself, under its lock, after the existing caller guards and the status check, so a request written straight to its socket is held to it as the client's is. A missing, wrong, spent or replaced token is a refusal: no relaunch, no prompt file, no trust grant, no rendered surface, no status change. The message uses the wording `approve` uses, without saying which of the four it was, and names the dashboard and `reissue`. (informed by REQ-659)
- [ ] BR-6: The token is spent when the relaunch is committed: after the adapter gate and the prompt build have passed, and before a harness is started. A refusal that leaves the run `blocked` leaves the token unspent, so the operator can run the command again: an adapter that reads unverified with no `--allow-unverified`, a prompt the build refuses, a run the merge worker is rebasing. A relaunch that fails to start ends the run `failed`, as today, and the token is discarded. No token relaunches a run twice. (informed by REQ-662)
- [ ] BR-7: A refused token neither spends nor replaces the token held, so the right one still works afterwards. A refusal is not by itself a Rule B protocol violation: an operator's mistyped token is not one. Each refusal logs `answer_refused` with the caller's pid as the kernel reported it, and the run's row shows the count for the current blocked episode, so an operator sees attempts they did not make.
- [ ] BR-8: Every accepted `answer` is recorded in the run record: the launch it started, when, `answeredBy`, `channel` and the caller's pid as the kernel reported it. The run's row names the last one. Before this requirement nothing recorded who answered. The reply text stays where it is today, in that launch's prompt file in the run directory. (informed by REQ-659)
- [ ] BR-9: `--allow-unverified` on `answer` is unchanged (REQ-662 BR-18). It belongs to the answering invocation, covers that one relaunch, and is recorded as today. It does not stand in for the token, and the token does not stand in for it. (informed by REQ-662)
- [ ] BR-10: One relaunch needs no token: the engine's own, of a run held behind a REQ that has merged, after a clean rebase (REQ-485). It carries the engine's fixed sentence and no text from outside the engine, and no dispatched operation reaches it. It discards the run's answer token. (informed by REQ-485)

_`reissue` and `resume`_

- [ ] BR-11: `reissue <REQ>` accepts a `blocked` run as it accepts one at the gate. It mints a fresh answer token, which invalidates the one before it, and prints the run's row and `answer` line on the supervisor's dashboard. Its reply to the caller says only that fresh tokens were printed there. On any status other than `awaiting_approval` and `blocked` it is refused naming the status, and with no live supervisor it is refused naming `resume`, both as today.
- [ ] BR-12: `resume` mints an answer token for every `blocked` run it takes over and prints each row, as it mints approve tokens for runs at the gate. Its refusals are unchanged: from inside a run, and for a run a live supervisor still holds.
- [ ] BR-13: The verbs that mint a token are the block itself, `resume` and `reissue`, and each prints to the supervisor's stdout alone. The verb that spends one is `answer`. A test reads the engine's verb list and each shipped adapter's `engine_deny`, and fails when a verb that mints or spends a token is missing from an adapter's deny tier, or when a verb is added that the test does not classify as minting, spending or neither. Today both shipped adapters deny all seven verbs. (informed by LESSON-781)

_`reject` and `abort`_

- [ ] BR-14: `reject` and `abort` take no token, on any status. A token guards a verb that starts a harness or commits a one-way move in the operator's name. These two start nothing, call no forge and leave the branch, the PR and the working copy for a person. `abort` is also the stop, and it must work when no supervisor is alive, where no digest exists to check against (REQ-719 BR-3). This settles the question REQ-719 BR-4 deferred here. `reject` on a `blocked` run stays refused naming the status. (informed by REQ-719, LESSON-781)
- [ ] BR-15: `abort` remains the operator's command to end a blocked run, exactly as REQ-719 BR-1 to BR-4 define it, with and without a live supervisor. One thing is added: it discards the run's answer token. An `abort` and an `answer` on the same run stay serialized by the supervisor's lock (REQ-719 BR-3). (informed by REQ-719)

_A dispatch whose caller the kernel cannot name_

- [ ] BR-16: For every dispatched operation the supervisor uses the pid the kernel reports for the connection, and no other, for the caller guard, for the nested-launch guard and as the `callerPid` it records. The pid a request claims is never used for a guard and never recorded as the caller's. (informed by REQ-662)
- [ ] BR-17: When the peer pid cannot be read, every dispatched operation except `ping` is refused. Nothing changes, no token is spent or replaced, and the refusal is one line naming `dispatch_unverified_peer` and the operation. The supervisor logs that event in the named run when the request names one that resolves. It is not a Rule B protocol violation: nothing showed the caller came from a run.
- [ ] BR-18: A supervisor that cannot learn a peer's pid does not start. Before `run` prepares or launches anything, and before `resume` takes over a run or mints a token, the supervisor connects once to its own socket and requires the kernel to report its own pid for that connection. When it does not, the command is refused naming the reason, with no run directory prepared and no harness launched. So no run reaches a gate or a question that no command can then clear. `reject` and `abort` made with no supervisor are unchanged: they act in the caller's own process.

_Runs blocked under the older engine_

- [ ] BR-19: Nothing is migrated. No token or digest was ever on disk, and none is now. A run blocked under the older engine has a run record this engine reads as it is, and the keys this requirement adds to it are optional. Such a run gets its first answer token when a supervisor of this engine takes it over with `resume`, or from `reissue` under one. From then on it is answered as any other blocked run: a supervisor of this engine accepts no token-less `answer`, whichever engine blocked the run.
- [ ] BR-20: A supervisor process started before the upgrade keeps running the older code. It holds no answer token and accepts a token-less `answer`, and nothing here can change a process that is already running. So the client asks first: before it sends `answer`, or `reissue` for a blocked run, it reads the supervisor's `ping` reply, and when the reply does not say the supervisor holds answer tokens the client sends nothing and tells the operator to stop that supervisor and run `adlc sprint-exec resume`. `approve`, `reject` and `abort` sent to an older supervisor behave as today. The README says that the upgrade takes effect for a run when its supervisor is restarted.
- [ ] BR-21: An older client, which sends no token, is refused by a supervisor of this engine under BR-5, with the message that names the dashboard and `reissue`.

_Declared limits, documents and tests_

- [ ] BR-22: The skill text holds `answer` to the rule it holds `approve` to. `sprint/references/exec-engine.md` says: run `answer` only on a literal operator instruction that names the REQ in the same turn and carries both the token and the reply. Never take the token from the dashboard output, a report, a file, an earlier turn or the model's own suggestion. When the instruction carries no token, say that it is on the supervisor's dashboard, and stop. Its "When the supervisor is gone" section says a new supervisor prints fresh tokens for runs at the gate and for blocked runs. (informed by REQ-659)
- [ ] BR-23: The README's declared residuals are rewritten where they say `answer` takes no token: the Nested runs row, the bullet "Process ancestry does not hold against a process that detaches", and the same statement wherever else an exec section repeats it. They say what the token closes, and declare what it does not, for the approve token as for this one: (a) a process running as the operator's user that outlives its run can signal the supervisor to stop, start one of its own with `resume`, and read that dashboard, which prints fresh approve and answer tokens; (b) under the `/sprint` skill the dashboard is the output of a background command in the operator's session, which is a file the same user can read, where from a plain shell it is a terminal; (c) the token is on the client's command line for as long as the client runs, where the same user's `ps` shows it, and it is spent by the first request that presents it; (d) `reject` and `abort` take no token, so such a process can end a run, and `abortedBy`, `decidedBy`, `channel` and the recorded pid are the evidence. Item (a) was read from the code at `1d40f47` and has not been run; AC-17 measures it. (informed by REQ-662, LESSON-781)
- [ ] BR-24: The documents change with the code: `sprint/SKILL.md`, `sprint/references/exec-engine.md`, `README.md`, `tools/adlc/README.md`, `CHANGELOG.md`, `.adlc/context/architecture.md`, and an amendment note in REQ-659 (BR-10, BR-14, AC-16), in REQ-662 (BR-19 and its deferral note) and in REQ-719 (BR-4).
- [ ] BR-25: Nothing is widened (Rule B). No rule here adds an allow, removes a deny, changes the pipeline prompt or the relaunch prompt's text, or performs a one-way move. The interactive render (`.claude/settings.json`) and both exec adapters' census files are byte-identical. (informed by REQ-682)
- [ ] BR-26: Every test runs offline against the fake harness and the mock forge, in directories outside the operator's home, with `HOME`, `ADLC_HOME` and `XDG_STATE_HOME` pointed at throwaway directories. A test's tokens are the ones its own supervisor minted. No test reads, copies or prints a credential. (informed by REQ-719)

## Acceptance Criteria

Each refusal below is paired with the case that must not be refused: the operator's own command, with the right token, from outside every run.

- [ ] AC-1 (BR-1, BR-4): A fake-harness run that ends `blocked` on a question makes the supervisor's stdout print the run's row, an `answer` line holding a 32-hex-digit token, and an `abort` line holding none. The same holds for a run blocked by a protocol violation at exit, by a denied harness, and by a rebase conflict after `approve`.
- [ ] AC-2 (BR-2): After that run blocks, the token's text and its digest appear in no file under the run directory, the working copy, the primary path's spec directory, the supervisor's directory or the run-outcome log, and not in the output of `adlc sprint-exec status` or `status --json`. After an accepted `answer`, the new launch's prompt file holds the reply and not the token.
- [ ] AC-3 (BR-5, must not refuse): `adlc sprint-exec answer --token <the printed token> <REQ> '<reply>'` from a process outside every run relaunches the run: a new harness process, `exec.pid` and `sessionId` overwritten, the reply in the prompt. The same holds with `--channel skill`.
- [ ] AC-4 (BR-3, BR-5): `answer` with no `--token`, with a wrong token, with another blocked run's token, and with the run's own token from before a `reissue`, is each refused with exit 2. After each, the run is still `blocked`, the launch count is unchanged, no new prompt file exists, no trust grant is recorded and no harness process was started. A request with no token written straight to the supervisor's socket is refused the same way.
- [ ] AC-5 (BR-6, BR-9): With an adapter that reads unverified, `answer` with the right token and no `--allow-unverified` is refused, the run stays `blocked`, and the same token with `--allow-unverified` then relaunches it. A second `answer` with a token that already relaunched the run is refused, whatever the run's status by then.
- [ ] AC-6 (BR-7, must not refuse): After three refused attempts with wrong tokens, the token the dashboard printed still relaunches the run. Before that `answer`, the run's row shows a count of three, the command log holds three `answer_refused` events with no token text in them, and no Rule B violation was recorded for them.
- [ ] AC-7 (BR-8): After an accepted `answer`, the run record holds one `answers` entry with the launch number, a timestamp, `answeredBy`, `channel` and the pid of the client process as the kernel reported it, and the row names it. The entry holds no token and no reply text.
- [ ] AC-8 (BR-10, must not refuse): A run held behind a REQ that then merges is rebased and relaunched by the merge worker with no token presented. A token printed for that run before the relaunch is refused afterwards. A dispatched request cannot reach that path: an `answer` with no reply text and no token is refused under BR-5.
- [ ] AC-9 (BR-11): `reissue` on a blocked run prints a new `answer` line on the supervisor's stdout, and its own stdout holds no token. The earlier token is refused and the new one relaunches the run. `reissue` on a `failed` run is refused naming the status.
- [ ] AC-10 (BR-3, BR-12, BR-19): With a run left `blocked` and its supervisor stopped, `adlc sprint-exec resume` prints that run's row and an `answer` line with a token, and that token relaunches it. The token the stopped supervisor printed is refused by the new one. The same holds for a fixture run record written in the older engine's shape, with no key this requirement adds.
- [ ] AC-11 (BR-13): The verb census test passes for both shipped adapters, and fails on a fixture adapter whose `engine_deny` omits `reissue`, and on a fixture verb list holding a verb the test does not classify.
- [ ] AC-12 (BR-14, BR-15, must not refuse): `abort` with no token ends a blocked run `failed`, with a live supervisor and with none, exactly as REQ-719 AC-1 and AC-2 state. The token printed for that run is refused afterwards, naming the run's status. `reject` with no token still ends a run at the gate. `reject` on a blocked run is refused naming the status.
- [ ] AC-13 (BR-16): With a client request whose `callerPid` field names another live process, an accepted `approve` records the kernel-reported pid of the client in the ledger, and an accepted `answer` records it in the run record. A request whose `callerPid` field is absent or wrong is not refused for that.
- [ ] AC-14 (BR-17): With the supervisor's peer-pid read stubbed to fail, `approve`, `answer`, `reject`, `abort` and `reissue` are each refused with one line naming `dispatch_unverified_peer`. The run's status, ledger and launch count are unchanged, the held tokens still work once the stub is removed, the command log holds the event, and no Rule B violation was recorded. `ping` still answers.
- [ ] AC-15 (BR-17, must not refuse): With the peer pid readable, every one of those operations made by a process outside every run proceeds as it does today, on the test host's platform.
- [ ] AC-16 (BR-18): With the self-check's read stubbed to fail, `run` and `resume` are each refused naming the reason: no run directory is prepared, no harness is launched, no token is printed, and the supervisor's directory is removed. Without the stub, both start (must not refuse).
- [ ] AC-17 (BR-23): A test named for the declared residual shows it as it stands: a process with the run variables cleared and outside the harness's ancestry stops the supervisor of a blocked run, runs `resume`, reads a token from that supervisor's stdout and relaunches the run with it. The test's docstring cites BR-23(a), so a later requirement that closes the route flips one test.
- [ ] AC-18 (BR-20, BR-21): Against a fixture supervisor whose `ping` reply lacks the capability, the client's `answer` exits 2, names `resume`, and sends no `answer` request; its `approve`, `reject` and `abort` are sent as today. Against a supervisor of this engine the capability check refuses nothing (must not refuse). A request shaped as the older client sends it, with no token, is refused by a supervisor of this engine.
- [ ] AC-19 (BR-22): The docs test pins, in `sprint/references/exec-engine.md`, the rule that `answer` runs only on an operator instruction carrying the token, and the sentence that a new supervisor prints fresh tokens for blocked runs.
- [ ] AC-20 (BR-23, BR-24): The README's exec sections no longer say `answer` takes no token, and hold the four declared limits. Each file BR-24 names carries its change, and the three amendment notes are present.
- [ ] AC-21 (BR-25): The interactive `.claude/settings.json` render and both census files are byte-identical to those before this change. `allowlist-fidelity`, the reach audit and the prompt scan pass, and the relaunch prompt for a given reply is byte-identical to the older engine's.
- [ ] AC-22 (BR-26): The suite passes with `HOME` pointed at an empty throwaway directory and leaves no file under the operator's real home.

## External Dependencies

- None. The token, its digest and the peer-pid read use the Python standard library the engine already uses.

## Assumptions

- A supervisor stays up while a run it holds is `blocked`, because `blocked` is not a terminal status. Read in the engine at `1d40f47` (`TERMINAL`, `Orchestrator.done`).
- `abort` already drops a blocked run with no token, with and without a supervisor. Read in `Orchestrator.abort`; REQ-719 is `complete`. The brief for this requirement said an operator had no such command, which was true before pull request #304.
- On macOS (`LOCAL_PEERPID`) and on Linux (`SO_PEERCRED`) the kernel reports the peer pid of a connected `AF_UNIX` stream socket while the peer is alive, so BR-17 refuses no operator on either. Not measured here; `/architect` confirms it on both before BR-18's self-check is designed.
- An older supervisor's `ping` reply carries no field a new client could mistake for the capability. Read at `1d40f47`: it returns `ok` and `pid` only.
- The operator can read the supervisor's stdout. Under the `/sprint` skill that is a background command's output, which the skill relays; BR-22 keeps the skill from spending a token it read there.

## Open Questions

- [ ] BR-23(a) is declared, not closed. Should a follow-up requirement harden `resume` so that a process which stops the supervisor cannot mint tokens to itself, and is there any check that holds against the operator's own user? Recommendation: its own requirement, after AC-17 has measured the route. It weakens the approve token as much as this one.
- [ ] BR-17 refuses `abort` along with the rest when the peer pid cannot be read. `abort` is the stop for a running harness, and the way round is to stop the supervisor and run `abort` with none. Is that acceptable, or should `abort` alone be let through unverified? Recommendation: refuse it, since BR-18 means a supervisor that started could read a peer pid, so the case is a fault and not a platform.
- [ ] Should `answer` and `approve` also accept the token on stdin, so that it never sits on a command line (BR-23(c))? Recommendation: not here. It changes `approve`'s interface and the skill's dispatch for both verbs.

## Out of Scope

- Hardening `resume`, or any other defense against a process running as the operator's user that attacks the supervisor itself (BR-23(a)).
- Hiding the dashboard from the operator's own session under the `/sprint` skill (BR-23(b)).
- A token for `reject` or `abort` (BR-14), and any change to the approve token or the gate-bound token.
- Binding the answer token to the text of the question shown beside it.
- The workflow and legacy engines' answer paths (`args.answers`, the legacy re-dispatch). They are driven by the operator's own session and have no supervisor.
- Splitting `sprint_exec.py`, and the other items REQ-662 deferred: the sandbox and the fence runner's git environment, and the tolerant user-config reader.
- Engine code. This requirement is a draft; nothing is implemented by it.

## Retrieved Context

- REQ-659 (spec, score 19): /sprint exec engine — a shell orchestrator that runs one headless harness process per REQ, stops at the merge gate, and performs every one-way move itself after `/sprint approve`
- REQ-719 (spec, score 15): The exec engine's open findings from its first real run: `abort` drops a blocked run, the lane check works on a single-branch clone, a fence is held to its caller's PR, an arg file is opened without a window, a rejected run records `rejected`, and Phase 7 reads CI through the forge adapter
- LESSON-781 (lesson, score 15): A verb that mints or prints a secret is approval surface, however the spec counted the guarded verbs
- REQ-682 (spec, score 13): Skill fences run under `/sprint --exec` without widening what the model can run
- REQ-662 (spec, score 11): Exec adapters for Copilot CLI, Codex, Gemini CLI and Cursor, accepted only on passing REQ-664 probes
- REQ-474 (spec, score 10): Re-platform /sprint orchestration onto Claude Code Dynamic Workflows
- LESSON-403 (lesson, score 9): Hand-maintained counts and enumerations in shared registry files are sprint conflict magnets — derive them from the registry, and expect parallel REQs that extend the same extensibility point to race at merge
- REQ-485 (spec, score 9): Auto-rebase and resume a blocked REQ after its blocker merges (/sprint self-healing serialization)
- LESSON-887 (lesson, score 8): On a sandboxed harness an allow rule is an exit from the sandbox, not a pre-approval: render only what has to leave
- LESSON-712 (lesson, score 8): A rule phrased 'whoever performs X owns Y' reaches only the sites you edit — take a census of every X site when you write it, and keep the evidence Y will need
- BUG-249 (bug, score 8): Neither sprint engine's orchestrator-owned Phase 8 runs the Step 8b close-out: the workflow engine never does, and the legacy orchestrator skips it for cross-repo and fallback merges — no lessons, status stays approved, terminal record never written
- LESSON-356 (lesson, score 8): Probe gcloud auth up-front before dispatching GCP-dependent REQs in a sprint
- LESSON-899 (lesson, score 7): A model runs a fence where it reads it, not where a later step names it: put the precondition and the meaning of its failure line beside the fence
- LESSON-900 (lesson, score 7): A runner fence loses a bound value silently: `name=` or `for name` in a string unbinds it, and `${NAME:-default}` loses its default
- LESSON-902 (lesson, score 7): An agent's account of why it stopped is a guess when the harness refused its line: show the harness's own record beside the account, whatever the agent claims
