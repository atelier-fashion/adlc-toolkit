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

## What these do not show

- Whether Codex re-reads a rule file edited during a session (`rules_reload: unknown`).
- A full pipeline run under the engine. These are single turns; the approval protocol is
  tested against the block through the test harness.
- A push to a remote over the network. The origin is a local bare repository outside the
  sandbox's writable area, so the row shows the runner left the sandbox, not that a
  credential reached a forge.
- Whether a sandboxed `git commit` can write a linked worktree's common git directory:
  `git commit` is a routine allow, so in an engine run it does not run sandboxed.
