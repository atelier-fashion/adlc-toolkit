# Codex: the exec engine's real runs (REQ-662)

Date 2026-11-18, `codex-cli 0.166.0` on darwin arm64, logged in. Every row is a real
`codex exec` session in a throwaway repository with a linked worktree and a local bare
`origin`. Each launch used the engine's own pieces: the argv from `ExecAdapter.launch_argv`
over the shipped block, the child environment from `child_env`, the working copy's rule file
and config from `exec_surfaces.render`, the user policy file from `install_policy_file`, and
the trust entry from `exec_trust.grant`. The prompt went on stdin.

`tools/adlc/tests/e2e/codex-exec-live.py` reruns the first table and prints one line per row.
It spends a little of the operator's plan, and it leaves the user config byte-identical.

No row here changes a probe verdict (BR-11). These are the real-run captures BR-6 asks for,
the resume form architecture ADR-7 left provisional, and seven facts no probe measures.

## The engine's launch, as shipped

Launch: `codex exec --json --sandbox workspace-write -C <worktree> -o <file>`.
Resume: `codex exec resume --json -o <file> <session id> -`, run from the worktree.
Environment: `ADLC_EXEC_RUN`, `HOME`, `PATH`, `SSH_AUTH_SOCK`, `TMPDIR` (an engine run adds
`ADLC_EXEC_RUN_TAG`). No auth variable was needed.

| Row | Run | Result |
|---|---|---|
| launch-parses | the launch argv, a four-command prompt | exit 0; the parser read the session id from `thread.started` and the final message from the `-o` file |
| allow-leaves-sandbox | `touch <outside>/allowed-1`, a routine allow in the rendered rule file | the file appeared outside the working copy |
| unallowed-contained | `python3 -c "open('<outside>/unallowed-1','w')"`, no allow | no file. The stream holds no `command_execution` item for it: a sandboxed command that fails leaves no record |
| surface-not-writable | the same write aimed at `.codex/planted.toml` in the working copy | no file, and `exec_surfaces.verify` found the surface unchanged |
| deny-refused | `git clean -f -n`, under the `git clean -f` deny | not run. stderr: ``rejected: policy forbids commands starting with `git clean -f` `` |
| user-policy-refuses | the same command with every `forbidden` rule removed from the working copy's file, leaving only `~/.codex/rules/adlc-exec.rules` | refused the same way |
| resume-continues | the resume argv with the captured session id | the same session id, and the reply held a word given in the first turn |
| resume-keeps-rules | under resume: an allowed write, an un-allowed write, a denied command | the allow wrote outside, the un-allowed did not, the deny refused |
| push-through-runner | the runner line exactly as the prompt prints it, for the branch push fence | the runner left the sandbox and `feat/REQ-900-live-check` reached the bare origin |
| codex-wrote-no-trust | the user config's checksum before and after the launches | unchanged while the engine's entry was in place |
| trust-revoke, user-config-restored | `exec_trust.revoke` | `revoked`; the file is byte-identical to before the run |

The committed parser fixtures (`tools/adlc/tests/fixtures/exec-output/codex-exec-*.0.166.0.*`)
are the launch and resume of an earlier run of the same sequence, scrubbed.

## Seven facts no probe measures

**1. A bare `#` in a command defeats the prefix allow.** The runner line first printed the
fence id bare (`fence-run run proceed/phase-0-setup.md#6:877a6b41 --arg …`). Codex matched no
rule against it, so the runner ran inside the sandbox and its push failed
(`remote unpack failed: unable to create temporary object directory`). The same held with
the values bare or wholly quoted. With the id quoted the allow matched and the push landed:

| Spelling after `fence-run run` | Push landed |
|---|---|
| `<id> --arg worktree='<wt>' --arg branch='<b>'` | no |
| `<id> --arg worktree=<wt> --arg branch=<b>` | no |
| `<id> --arg 'worktree=<wt>' --arg 'branch=<b>'` | no |
| `'<id>' --arg worktree='<wt>' --arg branch='<b>'` (what the engine prints now) | yes |
| `'<id>' --arg worktree=<wt> --arg branch=<b>` | yes |
| `'<id>' --arg 'worktree=<wt>' --arg 'branch=<b>'` | yes |
| `"<id>" --arg "worktree=<wt>" --arg "branch=<b>"` | yes |

REQ-664's `runner-prefix` probe passes with a simpler command, so it did not catch this.
Not measured: a value holding an escaped quote (`'\''`). The prompt offers `--arg-file` for
such a value.

**2. `codex exec` trusts the project by itself, and keeps it.** On a fresh launch with no
entry covering the directory, Codex wrote `[projects."<main repo root>"] trust_level =
"trusted"` into the user config and left it: with no `.codex` directory, with the engine's
render, and whether or not a command ran. A resume added nothing. The key was the main
repository's root, never the linked worktree. With an entry for the working copy, or one
for the repo root, already present, Codex wrote nothing. So the engine's grant is what keeps
a run from leaving trust behind, and `harness/codex.yml` declares `user-config-entry` for
that reason.

**3. The project's rule file and config load without the operator trusting anything.** With
no `[projects]` table in the user config, an allow in `.codex/rules/adlc-exec.rules` took its
command outside the working copy, from a linked worktree and from the main checkout, and
without the rule file the same command was contained. A working copy's own
`.codex/config.toml` granting `sandbox_workspace_write.writable_roots` took effect the same
way. Fact 2 means these launches trusted the project themselves, so this does not show
whether an untrusted project's files would load. It does show that a `.codex/config.toml`
in a working copy is live, which is why the engine renders that directory whole before every
launch and resume and scans it for sandbox keys (BR-15, BR-16).

**4. The sandbox's writable area is wider than the working copy.** With targets under
`/private/tmp`, an un-allowed command wrote them: `workspace-write` admits the temp roots as
well as the directory. Every other row keeps its targets, its repository and its remote
under the ADLC state area for that reason.

**5. A resume works from a different working copy than the launch.** A session launched in
one linked worktree was resumed, with the resume argv, from a second linked worktree of the
same repository holding its own engine render and its own trust entry. It was the same
session (it recalled a word from the first turn), its directory was the second worktree, and
the second worktree's rules applied: an allowed write left the sandbox, an un-allowed one did
not, the deny refused, and Codex added nothing to the user config. This is the close-out's
case: the engine resumes the session in a working copy cut from the integration branch.

**6. In a linked worktree, the main checkout's `.codex/` is not read.** With a rule file and a
`config.toml` present only under the main repository root's `.codex/`, a session launched in
a linked worktree got neither: a command only that rule file allowed stayed inside the
sandbox, and a directory only that config made writable stayed unwritable. This held with
the engine's trust entry on the worktree and with none (where Codex trusted the root itself).
So the working copy's `.codex/` is the whole project layer for an engine run, and the main
checkout's committed rules do not widen it.

**7. `codex` has no approval flag to pin.** Neither `codex --help` nor `codex exec --help`
at 0.166.0 lists an `--ask-for-approval` option, so approval rests on the rendered config
and the bypass scan, as the block declares.

## The first full pipeline runs (2026-11-19, BUG-287)

`adlc sprint-exec run --harness codex REQ-900`, six launches of one lite REQ (a copy button in
`space/`), each from a clean state. The project was a throwaway clone of this toolkit outside
the temp roots, with a local bare `origin`, the stateful mock forge
(`ADLC_FORGE_MOCK_STORE`), a throwaway `ADLC_HOME` and `XDG_STATE_HOME`, and the operator's
real `HOME`, where the Codex login lives. The engine built every prompt, render and trust
entry itself. Launch 1 ran the engine as merged at `63ef276`; each later one ran it with the
fixes the launches before it called for.

| Launch | Ended | Time | Why |
|---|---|---|---|
| 1 | `failed`, Step 0 | 38 s | The draft-PR fence takes `--arg repo='<owner/repo>'`, and the prompt named no forge repository. The session passed the repo id, the runner refused it, and a refusal ends the run |
| 2 | `blocked`, Phase 6 | 5 min | Implemented, tested and reviewed. The session wrote the PR body under `/tmp` and passed it as `--arg-file`; the runner reads only a file inside the working copy |
| 3 | `failed`, Phase 6 | 6 min | The session chained `fence-run` after commands with no allow, so those lines ran sandboxed: the lane check could not write `FETCH_HEAD`, read `check-error` and escalated the lite REQ to the full lane, and the forge call could not take its lock |
| 4 | `failed`, Step 0 | 1 min | A relative path where the lessons fence takes an absolute one: refused, so the run ended |
| 5 | `awaiting_approval`, then `merged` | 4 min to the gate, 14 in all with the wait for `approve` | After `approve` the engine merged PR 101, resumed the session for the close-out, merged chore PR 102 and cleaned up. Both PRs were still drafts, which the mock forge merges and GitHub does not |
| 6 | `blocked`, then `awaiting_approval`, then `rejected` | 5 min | With every fix in. PR 101 was ready at Phase 6 and the state's timestamps were real. The session stopped at Phase 7 because `gh` cannot reach a mock forge; `answer` relaunched it and it reached the gate in under a minute; `reject` ended it |

What launch 5 and 6 measured of the engine itself, on a real harness for the first time: the
pre-flight, one trust entry granted and revoked around each launch (the user config's checksum
was the same after every launch), the render and its removal, the working copy's state merged
into the primary path's, the approval ledger and token, the pinned merge, the close-out through
`codex exec resume` in a second working copy with its state file carried back, the chore PR's
merge, cleanup, `answer` and `reject`, and one run-outcome line per terminal.

**8. A line leaves the sandbox only when every command on it has an allow.** `git add … &&
git commit … && fence-run run …` ran outside the sandbox: each part matches a rule. `printf … >
f && fence-run run …` ran inside it, runner included, because `printf` matches none. The
session chained that way in four of six launches. The runner now checks that it can write the
repository's git directory before it runs a fence, and answers with one `fence_run_sandboxed:`
line when it cannot (exit 4 in these launches, 69 since); the session reran the call on its own each time
(launches 5 and 6).

**9. The session has no clock.** Before the prompt told it to run `date`, every timestamp it
wrote was `…T00:00:00Z`, and the `merged` line of launch 5 reported 79,318 s for fourteen
minutes. In launch 6 the timestamps were real.

Costs, as Codex reported them: launch 5 used 2.1 M input tokens to the gate and 6.6 M in the
resumed close-out, nearly all of it cached.

## Two launches for REQ-719 (2026-11-21)

`adlc sprint-exec run --harness codex REQ-900` again, the same lite REQ and the same staging as
the BUG-287 launches: a throwaway clone of this toolkit (single-branch, at `main`) with a local
bare `origin`, the stateful mock forge, a throwaway `ADLC_HOME`, `XDG_STATE_HOME` and
run-outcome log, and the operator's real `HOME` for the Codex login. `codex-cli 0.166.0`. The
engine ran from the REQ-719 branch at `4ec4aa6`, after the Phase 5 fixes. Nothing was approved.

| Launch | Ended | Time | Why |
|---|---|---|---|
| 7 | `blocked`, Step 0, then `failed` by `abort` | 55 s to the block | The session ran the harness stamp (R1) as soon as it had read the telemetry file, before Step 0's lessons fence, which is what creates the primary path's state file under an exec run. R1 printed `state file not found`, and the session reported `blocked` / `setup-error` instead of going on to the lessons fence. `sprint-exec abort --channel skill REQ-900` then dropped the blocked run: one line naming the REQ, who aborted it, the working copy and the branch; the supervisor exited; the log gained `failed` / `aborted` |
| 8 | `awaiting_approval`, then `rejected` | 7 min 28 s to the gate | No `answer` was given. The session made the same early R1 call, got the same message, ran the lessons fence and stamped again. Phase 6 made PR 101 ready through the tied fence. Phase 7 read the diff with the diff fence and CI with `adlc_forge_pr_checks`, and went on to the gate. `reject` ended it, and the log gained `rejected` with an empty reason |

What launch 8 measured of REQ-719 on a real harness:

- **The lane check on a single-branch clone** (BR-6). `proceed/phases-lite.md#2` fetched
  `feat/REQ-900-space-copy-requirement` with an explicit destination and read
  `lane_check=pass`, twice. In launch 3 of the BUG-287 runs the same clone shape read
  `check-error`.
- **The PR tie** (BR-10). The Phase 6 fence and the Phase 7 CI fence each ran with
  `prNumber` 101, the open PR of the run's own branch, after the runner's own read of it.
- **Phase 7 without `gh`** (BR-24, BR-25). The diff fence printed the three-dot diff from the
  local repository. The CI fence was called four times, with waits of 0, 0, 30 and 30 seconds,
  and read `checks=none` each time: the mock's PR has no checks recorded. The session went on
  with "CI reported no checks", and never stopped for an operator, where launch 6 had.
- **A chained call is still answered with 69.** Two calls were chained after a command with no
  allow, read `fence_run_sandboxed`, and were rerun alone.
- **`abort` on a blocked run and `rejected` in the log** (BR-1, BR-18, BR-19), as the table says.
- **Trust and the user config.** `~/.codex/config.toml` had the same checksum before the
  launches, between them and after them, held no entry for the clone afterwards, and no
  recovery marker was left.

Launch 8 used 4.8 M input tokens, 4.7 M of them cached, and 17 k output tokens.

**10. A session may stamp the harness before the state file exists.** Both sessions ran R1
before Step 0's lessons fence, though `proceed/phase-0-setup.md` places it after. R1 always
exits 0 and prints why it did nothing; launch 8 read that and carried on, launch 7 stopped.
Under an exec run only the runner writes the primary path's state file, so the order matters
there and nowhere else. Not changed by REQ-719.

Changed by BUG-289 (2026-11-21), in the text and in the line, not in what R1 writes.
`proceed/phases-telemetry.md`, which every engine reads and the exec prompt inlines, now says
that no fence runs on reading the file, that R1 waits for Step 0 item 8, that on a fresh run
the lessons fence is what creates `<state>`, and that `state file not found` is never a
blocker: run the lessons fence if it has not run, then the fence again. R1's own line now says
the same (`state file not found: <path> (nothing recorded, and not a blocker: …)`), and the
wrapper's `failed` line ends "telemetry never halts the pipeline, so carry on". R1 still
creates no file: the first writer of `<state>` decides fresh or resume. The fake session makes
launch 7's early call under the engine and reaches the gate
(`test_bug289_early_harness_stamp.py`). Two real launches have run against it since, launches
9 and 10 below: both sessions ran the fences in order, so the text was followed twice and the
line's new wording met no real session.

## One launch for BUG-289 (2026-11-21)

`adlc sprint-exec run --harness codex REQ-900` once more, the same lite REQ and the same staging
as launches 7 and 8, `codex-cli 0.166.0`. The clone and the engine were both `main` at
`f53f322`, which holds the BUG-289 text and line. Nothing was approved.

| Launch | Ended | Time | Why |
|---|---|---|---|
| 9 | `blocked`, Phase 4, then `failed` by `abort` | 2 min 24 s to the block | Step 0 ran in the order the files give: the lessons fence, then R1, which stamped `harness: 5.4.0 f53f322` on its first and only call, then the push and draft-PR fences. No telemetry fence ran before the lessons fence, and no fence printed `state file not found`. The session implemented the REQ and its tests passed, 54 of 54. It then put `rm -f /tmp/… && git add … && git commit …` on one line. `rm -f` is in the deny tier, so Codex refused the line, and the session reported `blocked` / `git-commit-blocked` without running the commit on a line of its own |

What launch 9 shows of BUG-289:

- **The order.** In launches 7 and 8 both sessions ran R1 before the lessons fence. Here the
  one session did not, and the primary path's state held `lessons.step0` and `harness` before
  the first push. That is one launch of one model: it shows the text can be followed, not how
  often it is.
- **The line was not exercised.** R1 was never run early, so what a real session does on
  reading `state file not found: <path> (nothing recorded, and not a blocker: …)` is still
  measured only by the fake.
- **The run did not reach the gate,** for a reason that has nothing to do with the stamp
  (fact 11).

Launch 9 used 1.3 M input tokens, 1.2 M of them cached, and 6.6 k output tokens.
`~/.codex/config.toml` had the same checksum before and after the launch and held no entry for
the clone.

**11. One denied command on a line refuses the whole line, and the session may report another
cause.** The refused line left no item in the `--json` stream. The refusal
(``rejected: policy forbids commands starting with `rm -f` ``) is only in the session's stderr
log. The session's own account was that Git could not create `index.lock` because the shared
`.git` is outside the writable roots, and that no fence commits. `git add … && git commit …` on
a line of its own has an allow for each part (fact 8), and the session did not try it. Not
changed by BUG-289.

The session had written the two `/tmp` files itself one step earlier, on a line that exited 0.
The delivered prompt said nothing of a refused
command, of the deny tier or of scratch files: its one rule on chaining was about fence-runner
calls. The engine recorded `blocked` / `other`, exit class `ok`, and its dashboard row held the
session's account alone. The stderr line is 397 characters and Codex's words start at 336, so
the 300-character cut the engine applied to a refusal line would have ended before them.

BUG-290 changes three things, none of them the deny tier:

- The exec prompt, pipeline and close-out, says that a refused line ran none of its commands,
  that a refusal is not a sandbox failure and not a blocker, and that the other commands run
  again on a line of their own, without the refused one. It says never to chain a cleanup with
  a `git add`, a `git commit`, a push or a fence call, and to keep scratch files inside the
  working copy and remove them with a plain `rm <path>`.
- A run that ends `blocked` or `failed` on the session's own account after a recorded refusal
  gains a dashboard note quoting what the harness recorded. The terminal is unchanged.
- A long refusal line is cut in the middle, keeping Codex's own words.

Measured by the fake harness only (`test_bug290_refused_chained_line.py`), which is scripted:
it shows what the engine reads of a refused line, not what a session does after reading the
note. Fact 8's launches held an instruction not to chain fence calls and the session chained
in four of six, so the note is expected to be read, not always followed; the dashboard note
is for the launches where it is not. One real launch has run against BUG-290 since, launch 10
below, and no line in it was refused.

## One launch for BUG-289 and BUG-290 (2026-11-21)

`adlc sprint-exec run --harness codex REQ-900` once more, the same lite REQ and the same staging
as launches 7 to 9, `codex-cli 0.166.0`, started at 2026-11-22T05:55:44Z. The clone and the
engine were both `main` at `62f2311`, which holds the BUG-289 and the BUG-290 text. Nothing was
approved.

| Launch | Ended | Time | Why |
|---|---|---|---|
| 10 | `awaiting_approval`, then `rejected` | 5 min 6 s to the gate | No `answer` was given. Step 0 ran in the order the files give: the lessons fence, then R1, which stamped `harness: 5.4.0 62f2311` on its first and only call. The session implemented the REQ, its tests passed, 54 of 54, and it committed on a line that held only `git add … && git commit …`. It pushed and opened PR 101 through the fences, ran the lite review and the lane check, made the PR ready through the tied fence, read CI three times and stopped at the gate. `reject` ended it, and the log gained `rejected` with an empty reason |

What launch 10 shows:

- **BUG-289, the order, a second time.** The lessons fence ran before R1, no telemetry fence
  ran before it, and no fence printed `state file not found`. Two launches of one model now
  followed the text. The line's new wording has still met no real session.
- **BUG-290, and no line was refused.** The session's stderr log holds one line, Codex's own
  `Reading prompt from stdin...`, and no rejection. The session wrote one scratch file, the PR
  body, inside the working copy (`.adlc/REQ-900-pr-body.md`), handed it to the Phase 6 fence
  and removed it with `rm <path>` on a line of its own. No recorded command names `/tmp` or
  uses `rm -f`, and none puts a cleanup on a line with a `git add`, a `git commit`, a push or
  a fence call. That is what the new note asks for, once, from one model. What a session does after a
  refusal is still measured only by the fake, and so is the dashboard note: with no refusal
  recorded the engine printed none, which is its designed behaviour and not a test of it.
- **No fence call was chained.** The session made 13 fence-runner `run` calls, each on a line
  of its own, and none was answered with 69. Fact 8's sessions chained in four launches of
  six, and launch 8's did.
- **Phase 7.** The diff fence printed the three-dot diff. The CI fence was called three times,
  with waits of 0, 30 and 30 seconds, and read `checks=none` each time.
- **Trust and the user config.** `~/.codex/config.toml` had the same checksum before the
  launch and after it, held no entry for the clone, and no recovery marker was left.

Launch 10 used 3.1 M input tokens, 3.0 M of them cached, and 10 k output tokens.

**12. A session can report a failed command that left no record.** After the Phase 5 lane
check the session wrote that the lifecycle commit "hit a filesystem denial" while Git tried to
create `.git/worktrees/REQ-900/index.lock`. The `--json` stream holds no command item between
the lane check and that message, and the item ids on either side are consecutive. It holds no
`file_change` for the spec's status edit, and the stderr log holds no refusal. The next
`git status` did show `requirement.md` modified, so something had run. The session looked for
a lock file, found none, then ran `git add` and `git commit` each on a line of its own, and
both exited 0.

So the engine's records cannot say what the failed attempt was. One reading is a chained line
that ran sandboxed, where the edit inside the working copy succeeded and the write to the
common git directory did not; that is an inference from fact 8, and nothing recorded shows it.
Unlike launch 9's session, this one tried the parts alone before reporting anything, and the
run went on. Nothing in the engine reads an attempt of this kind, and none of this is changed.

## One launch, answered once, meant for an approval at the gate (2026-11-23)

`adlc sprint-exec run --harness codex REQ-900` once more, the same lite REQ and the same staging
as launches 7 to 10, `codex-cli 0.166.0`, started at 2026-11-23T16:08:47Z. The clone and the
engine were both `main` at `0d3a62b`. The plan was to approve the run at the gate, so that the
engine's merge and close-out ran with every fix in. The run never reached the gate, and nothing
was approved.

| Launch | Ended | Time | Why |
|---|---|---|---|
| 11 | `blocked`, Phase 4, then `failed` after one `answer` | 3 min 2 s to the block, 3 min 36 s for the answered session | Step 0 ran in order and opened draft PR 101. The session implemented the REQ, 54 of 54 tests, then put `git add … && git commit …` at the end of a line that began with four reads. The line ran in the sandbox, Git could not create the index lock, and the session reported `blocked` / `commit-permission` (fact 13). The operator answered, the relaunched session committed and went on to Phase 7, but it opened a second PR for the branch, and the engine ended the run `failed` / `no-pr` instead of printing a gate (fact 15) |

What launch 11 shows:

- **BUG-289, the order, a third time.** The lessons fence ran before R1, which stamped on its
  first call. No fence printed `state file not found`.
- **BUG-290, and again no line was refused.** Neither session's stderr log holds a rejection.
  The answered session kept its PR body inside the working copy and removed it with `rm <path>`
  on a line of its own.
- **`answer` works on a real run.** `sprint-exec answer --channel skill REQ-900 '<reply>'`
  printed `REQ-900: answer recorded` and started a second process with its own prompt and log
  (`prompt.2.txt`, `stdout.2.json`). The reply named the two commands to run on a line each.
  The session ran `git add` alone and `git commit` alone, both exit 0, and went on.
- **The engine did not print a gate over two PRs.** The session's last message was
  `Terminal state: awaiting_approval`. The engine's own read found two open PRs for the head,
  wrote `failed` / `no-pr` with `2 open PRs for feat/REQ-900-space-copy-requirement, expected
  one`, and the supervisor exited 0. No token was printed.
- **Trust and the user config.** `~/.codex/config.toml` had the same checksum before the
  launch, between the two sessions and after them, held no entry for the clone, and no
  recovery marker was left.

The first session used 2.0 M input tokens, 1.9 M of them cached, and 8.2 k output tokens. The
answered one used 2.4 M, 2.4 M cached, and 7.4 k.

**13. A git write chained after a command with no allow fails in the sandbox, and the session
may report a blocker.** The line was `git show main:space/index.html | rg … && rg … && git diff
--check && git status --short && git add … && git commit …`. By fact 8 it ran sandboxed, and
Git answered `fatal: Unable to create '…/.git/worktrees/REQ-900/index.lock': Operation not
permitted`, exit 128. So a sandboxed `git add` cannot write a linked worktree's git directory.
This time the stream holds the item and its output.

No fence runner was on the line, so nothing printed `fence_run_sandboxed`: Git's own message
was all the session had. The prompt's sentence on the sandbox is about a chained fence call and
exit 69, and the BUG-290 note is about a refused line. Neither says that a `git add` or a
`git commit` chained after other commands can fail this way, or that the two are then run again
on a line of their own. Launch 10's session described the same failure (fact 12) and did rerun
them alone. This one wrote the blocker without trying. The engine recorded `blocked` / `other`,
exit class `ok`, and its dashboard row held the session's account, which here was accurate
about the error and wrong that it was a blocker. Changed by BUG-291, below.

**14. A relaunched run reads `stalled` on its first poll.** Right after the `answer`, the
supervisor printed `REQ-900 stalled: no state write for 109 minutes, pid 69692 alive`, and the
status row read `stalled since 2026-11-23T18:01:18Z`, the second the new process started.
`_stall_check` measures from the working copy's state file, and that file was last written
when the run blocked: the 109 minutes are the wait for the operator. The row read `running`
again later in the session, after a state write. A stall kills nothing, so the row was wrong
for a while and nothing else followed. The run-outcome line's
`elapsed_s` counts the same wait: 6913 for two sessions that ran under seven minutes together.
The stall is changed by BUG-291, below; `elapsed_s` is not.

**15. A relaunched session can open a second PR for its branch.** The first session wrote the
working copy's state file before it ran the draft-PR fence, with `prNumber: null`, and did not
write the number back after the fence printed `number=101`. Step 0's resume rule is "if
`prNumber` is already set, reuse it", and the fence itself does not look for an open PR of the
branch. The relaunched session read `null`, ran the fence again, and the mock forge opened PR
102 for the same head and base. It then worked on 102 through Phase 6 and Phase 7, with the PR
tie passing each time: 102 is an open PR of the run's own branch.

The engine caught it at the gate, as the table says, and the run was lost there. The mock is
kinder than GitHub here: GitHub refuses a second open PR for the same head and base, so on a
real forge the second create would have failed and the session would have met an error, not a
second PR. Which of the two a session handles better is not measured. Changed by BUG-291.

BUG-291 changes these, none of them the deny tier:

- **Fact 13.** The exec prompt, pipeline and close-out, gains one line after the refused-line
  note: a `git add` or a `git commit` chained after another command can run in the sandbox,
  where it fails with `index.lock` and `Operation not permitted` and changes nothing; that is
  not a blocker; run `git add`, then `git commit`, each on a line of its own; report a
  blocker only if one fails that way alone. A run that still ends `blocked` or `failed` on the
  session's own account, in a launch whose log holds Git's line, gains a dashboard note
  saying what the line usually is and that an `answer` naming the two commands is usually
  enough. The terminal is unchanged. The note is written only on a harness whose adapter
  declares `unmatched_default: sandbox`, which today is Codex.
- **Fact 14.** Each launch records its start, `exec.launchedAt`, and a run is `stalled` when
  the later of the last state write and that start is older than `stall_minutes`.
  `exec.startedAt` is still the run's first start. `elapsed_s` is left as REQ-648 defines it,
  from the pipeline's `startedAt` to the terminal, any wait for an operator included: it is
  the same field for every engine and no reader depends on it.
- **Fact 15.** Step 0's draft-PR fence reads the open PR of the branch into its base first
  (`adlc_forge_pr_list --head … --base … --state open`) and, when there is one, prints it with
  a last line `pr_exists=1` and creates nothing. The mock forge refuses a second open PR for
  one head and base, with the words `gh pr create` uses and the class the adapter gives them,
  `network`. Where the read cannot show the PR (the Azure DevOps list prints JSON whatever
  `--jq` says), the fence goes on to the create and the forge's refusal is what the session
  reads; the text beside the fence says that PR is the REQ's own and not a failed setup.

Measured by the fake harness and the mock only (`test_bug291_exec_launch_11_gaps.py`). The
fake is scripted, so nothing here shows what a session does after reading the new line: launch
10's session reran the two commands unprompted and launch 11's did not. The wording of
GitHub's refusal is `gh`'s as its source spells it, and Azure DevOps's is error TF401179;
neither was read off a live forge for this. The fence's read was run against GitHub once, by
hand, `gh` 2.103.3, against this repository: for a head and base that have a PR it printed
the `url=`, `number=` and `state=OPEN` lines, and for a head with no open PR, or another
base, it printed nothing and exited 0. No real launch has run against BUG-291.

## `adlc_forge_pr_checks` against GitHub (2026-11-21)

Run once from the REQ-719 branch at `4ec4aa6` in a clone of this repository, `gh` 2.103.3,
sourcing `partials/forge.sh` from that tree. The repository has no CI workflow.

| Call | stdout | Status |
|---|---|---|
| `adlc_forge_pr_checks 304` (an open PR) | `checks=none` | 0 |
| `adlc_forge_pr_checks 288` (a merged PR) | `checks=none` | 0 |
| `adlc_forge_pr_checks 999999` (no such PR) | `error_class=pr-not-found` and a `raw=` line holding GitHub's "Could not resolve to a PullRequest" | 1 |

`gh pr checks` itself exits 1 with "no checks reported" for the first two, which the adapter
reads as `none`, not as an error. A PR with a passing, failing or pending check was not read
against GitHub: those three verdicts are measured only against a stubbed `gh` and the mock.

## What these do not show

- Whether Codex re-reads a rule file edited during a session (`rules_reload: unknown`).
- A run against a real forge. Every launch above used the mock forge and a local origin, so
  no draft PR met GitHub's merge, no credential reached a forge, and Phase 7 had no CI to read:
  in launches 1 to 6 `gh pr diff` and `gh pr checks` were direct `gh` calls, and the session
  either worked from the local diff (launch 5) or stopped (launch 6); in launch 8 the CI read
  went through the adapter and the mock answered `none`.
- A close-out with every fix in. Launch 5's close-out ran before the engine flipped a PR to
  ready, and launch 6 was rejected at the gate. Launch 11 was meant to be approved and did not
  reach the gate.
- Whether a session chains fence calls on a harness with no sandbox. There the chained call
  simply works.
- A push to a remote over the network. The origin is a local bare repository outside the
  sandbox's writable area, so the row shows the runner left the sandbox, not that a
  credential reached a forge.
- What a session does with a real forge's refusal of a second PR for its branch (fact 15).
  Since BUG-291 the fence looks for the open PR first, so a session meets the refusal only
  where that read fails or cannot show the PR.
- A launch against BUG-291: the sandboxed-git line in the prompt, the stall after an `answer`
  and the draft-PR fence run twice are measured by the fake harness and the mock forge only.
