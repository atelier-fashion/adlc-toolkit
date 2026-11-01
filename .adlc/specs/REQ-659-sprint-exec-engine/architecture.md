# Architecture — REQ-659: the `/sprint` exec engine

The spec's `## Reconciliation (2026-10-31)` table is binding over its older text, and this
document builds on that table. Live facts are in
`.adlc/research/harness-probes/claude-exec-manual.md`.

## Approach

A third engine whose orchestrator is a program. One long-lived **supervisor** per batch
launches one headless harness per REQ, reads what each leaves behind as data, and performs
every one-way move itself after an operator approves. Everything else (`status`, `approve`,
`reject`, `answer`, `abort`) is a short client of that supervisor, callable from a plain
shell, which is what makes the engine usable without a Claude Code session.

```
/sprint --exec REQ-a REQ-b            adlc sprint-exec run REQ-a REQ-b   (plain shell)
        └──────── thin dispatcher ──────────┘
                        │
              pre-flight (all or nothing)
                        │
   supervisor ──── per REQ ────► run directory (0700, random name, outside every tree)
      │                          snapshots, resolved tools, manifest, gitdir checksums
      │                          worktree, prompt bytes, ledger, logs
      │
      ├─ launch ──► harness process group ──► pipeline-state.json (model-owned while alive)
      ├─ exit ────► reap group, sweep stragglers, BR-15 checks, BR-16 plan, ledger, tokens
      ├─ socket ◄── approve | reject | answer | abort | reissue
      └─ worker ──► BR-11 verify → trial merge → merge → deploy → close-out → cleanup
```

### New modules (`tools/adlc/`, stdlib only, Python 3.9)

| Module | Holds | Rules |
|---|---|---|
| `exec_adapter.py` | the view of the `exec` block: argv, rules, env, exit class, result parsing | BR-3, BR-8, BR-21, BR-22, BR-25 |
| `exec_prompt.py` | prompt assembly, the anchor table, the scan | BR-6, BR-7, BR-14, BR-24 |
| `exec_safety.py` | validators, resolved tools, the neutral environment, snapshots, the manifest, gitdir checksums, the action log | BR-17, BR-23 |
| `exec_ledger.py` | run directories, atomic writes, the ledger, tokens | BR-10 |
| `exec_gates.py` | exit checks, the plan, deploy surface, PR verification, the chore-PR gate, rebase | BR-11 to BR-16 |
| `sprint_exec.py` | the supervisor, its clients, the dashboard | BR-1, BR-2, BR-4, BR-5, BR-9, BR-15, BR-16, BR-20 |
| `forge_mock.py` | the stateful offline forge | BR-18, BR-26(g) |
| `forge_protection.py` | the closed verdict over rules and classic protection | BR-8, BR-26(c) |

`harness_adapter.py` validates the `exec` block. `adlc.py` gains one `SUBCOMMANDS` row.
`partials/forge.sh` gains the BR-26 ops. `tools/delegate/run_outcome.py` gains engine `exec`.

### Who owns which file

| File | Written by | When |
|---|---|---|
| `<wc>/.adlc/specs/REQ-x-*/pipeline-state.json` | the harness | while `exec.pid` is alive; the orchestrator never touches it then (BR-9) |
| `<run>/run.json` | the orchestrator | always; holds `exec.*`, the frozen config, `launchTip`, the working copies |
| `<run>/approval.json` | the orchestrator | at the halt and at each decision, wholesale |
| `<primary>/.adlc/specs/REQ-x-*/pipeline-state.json` | the orchestrator after exit; the close-out model for the terminal record | after exit it is authoritative |

## Decisions

### ADR-1: a Python supervisor, with clients over a Unix socket

**Decision.** `tools/adlc/sprint_exec.py`, reached as `adlc sprint-exec <verb>`. `run` does the
pre-flight, launches, and stays in the foreground as the supervisor until every REQ is terminal
(`merged`, `rejected`, `failed`). `resume` starts a new supervisor over existing run
directories. The other verbs talk JSON lines over `AF_UNIX`.

**Why.** Something has to `wait()` on each harness and must outlive it; the same process is the
natural holder of the token hash, and one single writer removes every race between approvals.
A shell program could not hold a hash in memory across clients. Foreground, because the
dashboard is its stdout, the only place a token is printed.

**Mechanics.** The socket lives in the supervisor's own random directory and is bound by a
relative name from inside it, because `sun_path` is 104 bytes on macOS and a state path under a
test's temp root is longer. A client finds it from `run.json`. If the supervisor is dead,
`reject` and `abort` run in the client, `approve` and `answer` refuse and name `resume`.
`resume` issues fresh tokens for every REQ at the gate: a token dies with its supervisor.

### ADR-2: process supervision

**Decision.** `subprocess.Popen(..., start_new_session=True)`, so the harness leads its own
session and process group. The supervisor polls `waitpid` once a second. At exit it sends TERM
then KILL to the group, then sweeps: `ps eww -axo pid=,command=` finds any process still carrying
`ADLC_EXEC_RUN=<REQ>`, which reaches a double-forked `setsid` child the group kill cannot. A
straggler that survives is surfaced in the dashboard and blocks the plan. Only after that does
the orchestrator read anything the harness wrote.

**The one kill rule (BR-20).** A live harness is killed only by `abort`. The reap above runs
after the leader has exited. A stall is a flag.

**A dead supervisor.** Children keep running, in their own sessions. `resume` cannot `wait()`
on them, so it polls `kill(pid, 0)` and classifies from the JSON result with the raw exit code
absent, which reads class `error` unless a terminal claim and the forge confirm otherwise.

### ADR-3: log capture

**Decision.** Per REQ under the run directory: `prompt.txt` (the exact bytes on stdin, opened as
the child's stdin so scanned, delivered and recorded bytes are one file), `stdout.json`,
`stderr.log`, and `orchestrator.log`, a JSON-lines record of every git, forge and tool call with
its argv, cwd, the `GIT_CONFIG*` environment, rc and any violation. A relaunch appends a
numbered suffix rather than overwriting. Tokens and child credentials never enter it. State holds
file names only.

### ADR-4: the approval protocol

**Decision.** At the halt the supervisor mints a 128-bit token, prints it to its own stdout, and
keeps only its sha256 in memory. A plan with a 'changes the gate' line gets a second token whose
hash is bound to that line's text. `approve` presents them over the socket; the first use spends
them. Order: caller checks (no `ADLC_EXEC_RUN`, no live recorded pid in the ancestry), state
validation, then token, then ledger (temp file, `mv`), then the display mirror in state, then the
queue.

**Why a live process, not a file.** A same-UID process that finds the run directory can rewrite
any file in it, so a hash on disk proves nothing against the escapee BR-10 assumes. It cannot read
another process's memory, and a socket client without the token is refused. What remains is
stated in the README: an escapee that survives the sweep and reads the operator's terminal output,
or the operator's session transcript when `/sprint` carries the dashboard.

**Ledger accounting.** `run.json` records each ledger write's sha256. A file present before the
halt write, or differing from the recorded hash, is a protocol violation.

### ADR-5: trust is what the launch needs, not what the harness can read

**Decision.** `trust.mechanism` keeps saying what Claude reads. New `exec.trust_grant` says what
the engine does per run: `none` for `claude`. `exec.trustGrantedAt` and `trustRevokedAt` are
written on every path, with `trustMechanism: none`.

**Why.** Three live facts. A linked worktree resolves its trust at the main repo root, so a
per-working-copy entry is inert, and an entry on the root would be a repo-wide grant shared with
the operator's interactive sessions and with every other REQ of the batch: not per run, and
revocable only by a reference count. `~/.claude.json` is rewritten by every running Claude Code,
so a read-modify-write can drop a concurrent write. And the only thing the notice says trust gates
is the project's `permissions.allow`, which this engine does not use: both tiers go on the
command line. Whether the CLI allow holds in an untrusted workspace needs a logged-in run. If it
does not, the first tool call is denied and the run halts `denied`, which is loud.

**For REQ-662.** A harness whose grant is real declares `flag`, `user-config-entry` or
`trusted-folders-file`; pre-flight refuses each until its arm ships. The contract, in `tools/adlc/README.md`:
grant before launch, per working copy, close-out copy included; revoke on every exit path; remove
exactly what was added; never leave an entry for a path that is gone. Three things REQ-662 must
carry: Codex's `sandbox_can_reach_common_gitdir: true` holds only for an allowed `git commit`
outside the sandbox, and its hooks stay untrusted per absolute path (REQ-655); `agy -p` exits 0
with an empty response at the first refused tool and 3 on failure, so `ok` with no terminal claim
must stay `failed` (BR-15 does this for every harness); a Codex hook review key contains the path,
so every working copy starts unreviewed.

### ADR-6: the allow set

**Decision.** The exec-scope render, plus `exec.allow_extra` (argv lists with a `{branch}`
placeholder), plus vetted `sprint.exec.allow_extra` from the frozen config. Every extra passes the
render's own `forbidden_first_token` and `deny_forms` tests, so an extra that wraps a deny is
refused at pre-flight. `exec.allow_tools` names the non-shell tools. Rules are spelled by
`harness_render._claude_spelling`'s format, one argv element each.

**Why.** The shared-base rule removes `git push`, and a pipeline that cannot push cannot open a
PR. Per-branch spellings wrap no deny, and refuse a plain push to the integration branch, which
narrows a residual BR-8 had declared.

### ADR-7: the prompt is assembled by section, and fails closed

**Decision.** Sources are read from ToolkitRoot and the primary path, never a working copy. Each
excision is a heading-to-delimiter cut; each rewrite an `(file, old, new)` triple whose `old` must
occur exactly once, else `PromptBuildError` and no launch. The scan runs on the final bytes.
Allowlists are full-line regexes in one table. Tokens with an empty allowlist always refuse.

**Why.** The prompt is a derived artifact of skills that change every week. A rewrite that
silently stops matching would put a merge instruction in front of an unattended model, so a
changed sentence must stop the launch and fail the test, which names the anchor.

### ADR-8: a stateful mock forge

**Decision.** `ADLC_FORGE_MOCK_STORE=<dir>` sends `ADLC_FORGE_MOCK=1` calls to
`tools/adlc/forge_mock.py`: PRs as JSON, a call log, `merge` as a real squash into the fixture's
bare remote, so the local diff gates and `git log origin/<ib>` see what a forge would leave.
Without a store the shell mock is unchanged, and the new fields and ops reach the helper with
in-memory defaults.

### ADR-9: `sprint.exec.deploy`

**Decision.** A deploy the engine runs is declared as `sprint.exec.deploy: {target, command}` on
the integration branch, because nothing generic exists to read. The command is stored verbatim at
the halt, run by `sh -c` from the parent path, and never recomputed.

### ADR-10: `denied` from the result

**Decision.** `exec.denied_result_key: permission_denials`. An exit class comes from `exit_codes`;
then, with no terminal claim, a non-empty value at that key makes it `denied`. It never overrides
a claim the state and the forge confirm.

## Sequence at the halt

1. Harness exits. Reap and sweep.
2. Parse the result; validate `session_id`, claim, and state values (BR-17).
3. BR-15 checks against a fresh `origin/<ib>`.
4. Classify. On a clean `awaiting_approval`: compute the plan from the run record, look PRs up by
   the branch the orchestrator created, cross-check the model's `approval`.
5. Ledger, then carry state to the primary path, then mint tokens, then print the row.

## Sequence on approval

Fetch, re-run BR-15, then per repo in plan order: PR verify, detached-worktree trial merge, pinned
merge, state write, unblock pass. Then stored deploy, resumed close-out, chore-PR gate and pinned
merge, cleanup, `status: merged`, run-outcome line.

## Testing

`tools/adlc/tests/test_exec_*.py` drive `Orchestrator` synchronously against a real throwaway repo,
a bare `origin`, `forge_mock.py` and a fake harness on `PATH`. `partials/tests/exec-engine.test.sh`
runs the CLI end to end under bash, zsh, `/bin/sh` and dash. `tools/adlc/tests/e2e/claude-exec-manual.sh`
reproduces the logged-out live table.
