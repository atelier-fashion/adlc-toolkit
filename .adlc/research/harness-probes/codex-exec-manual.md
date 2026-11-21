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
  ready, and launch 6 was rejected at the gate.
- Whether a session chains fence calls on a harness with no sandbox. There the chained call
  simply works.
- A push to a remote over the network. The origin is a local bare repository outside the
  sandbox's writable area, so the row shows the runner left the sandbox, not that a
  credential reached a forge.
- Whether a sandboxed `git commit` can write a linked worktree's common git directory:
  `git commit` is a routine allow, so in an engine run it does not run sandboxed.
