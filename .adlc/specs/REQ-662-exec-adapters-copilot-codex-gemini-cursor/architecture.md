# Architecture — REQ-662 stage 1: the Codex exec adapter and the shared exec parts

This is the design for **stage 1** of REQ-662 (Amendments, 2026-11-17). Later stages (Antigravity, Cursor, Copilot) get their own `/architect` pass, each from that harness's probe result.

## Where it lands

The exec engine (REQ-659) is a program, `tools/adlc/sprint_exec.py`, driven by one adapter block, `exec:` in `harness/<name>.yml`. Only `harness/claude.yml` has a real block today. The engine is built around Claude in about ten places, so stage 1 is a widening of the engine as much as a new adapter file.

| What Claude does | What Codex does | Where the engine assumes Claude today |
|---|---|---|
| Rules travel as flags (`--allowedTools`) | Rules are files: `.codex/rules/*.rules`, working copy and user level | `exec_adapter.launch_argv`, `settings_document` |
| One JSON result object on stdout | JSONL events on stdout; the last message in the `-o` file | `exec_adapter.parse_result` |
| Trust is not needed per run | `[projects."<path>"]` in the user config, per run | `sprint_exec.preflight` refuses any grant but `none` |
| Config is isolated by flags | `.codex/` in the working copy is read once the folder is trusted | `config_isolation` only |
| `--resume <id>` flag | `codex exec resume <id>`, with no `--sandbox` and no `-C` | `resume_flag` |
| The matcher is modelled (`exec_matcher`) | No pinned matcher | `vet_extra`, the census's `direct` route |

Nothing in `tools/adlc` may branch on a harness name (conventions, "Harness adapters are data"). Every difference above becomes an adapter field.

Files, by layer:

- **Adapter data:** `harness/claude.yml` (migration), `harness/codex.yml` (the block, and its stale facts), `harness/codex/exec-fence-census.json` (new), `harness/codex/rendered/*` if a render changes.
- **Loader:** `tools/adlc/harness_adapter.py` (`_exec_block`, schema 2).
- **Engine:** `exec_adapter.py`, `sprint_exec.py`, `exec_safety.py`, `exec_gates.py`, `exec_ledger.py`, and three new modules: `exec_verify.py` (BR-11), `exec_trust.py` (BR-5), `exec_surfaces.py` (BR-4, BR-15, BR-16, BR-17).
- **Renderer:** `harness_render.py` (the exec-scope file render).
- **Fences:** `fence_census.py`, `fence_run.py`, `exec_prompt.py`.
- **Doctor and CLI:** `harness_doctor.py`, `harness_cli.py` (`install --exec`).
- **Lints:** `tools/lint-skills/check.py` (`exec-no-bypass`, `exit-class-vocabulary`).
- **Fake and tests:** `tools/adlc/tests/fake_harness/exec_harness.py`, `exec_helpers.py`, the `test_exec_*.py` modules.
- **Docs:** `README.md`, `harness/codex/README.md`, `tools/adlc/README.md`, `.adlc/context/architecture.md`, `CHANGELOG.md`, `sprint/references/exec-engine.md`.

## Decisions

### ADR-1: exec schema 2 keeps schema 1's keys and adds the ExecBlock's

`EXEC_SCHEMA_VERSION` becomes 2. The loader refuses version 1 and any unknown version.

- **Keys that keep their name and meaning:** `launch`, `allow_flag`, `deny_flag`, `add_dir_flag`, `shell_rule`, `shell_rule_exact`, `allow_tools`, `file_rules`, `fence_runner`, `allow_extra_exact`, `engine_deny`, `forbidden_flags`, `exit_codes`, `env_passthrough`, `auth_env`, `config_isolation`, `config_isolation_help`, `settings_keys`, `sandbox_refuse`, `residuals`, `trust_grant`, `trust_notice`.
- **Keys that change shape, as the ExecBlock entity states them:** `working_copy` becomes `{strategy}`; `resume_flag` becomes `resume`, an argv template holding `{session_id}`; `result_keys` and `denied_result_key` become `output`.
- **New keys:** `harness_version`, `verification`, `status`, `probes`, `prompt_delivery`, `prompt_variant`, `context_delivery`, `allow_render`, `deny_render`, `rule_file`, `user_policy_file`, `config_surfaces`, `rules_reload`, `bypass_config_keys`, `shell_timeout_s`, `matcher`, `operator_flags`, `denied_stderr`.

Keys that only one render form needs are required only for that form: `allow_flag`, `shell_rule` and `settings_keys` when `allow_render: flags`; `rule_file` when `allow_render: file`. A key given for the wrong form is refused, so a block cannot carry dead fields.

**`harness/claude.yml` migrates mechanically.** Its three reshaped keys take the new shape and it gains the new required keys with the values that describe today's behaviour (`allow_render: flags`, `context_delivery: prompt`, `matcher: claude`, `verification: recorded`). Claude declares `prompt` because an exec run of it loads no hook: its isolation flags leave none, and ETHOS reaches it through the prompt. No engine behaviour changes for it, and REQ-659's, BUG-265's and REQ-682's tests re-run unchanged in what they assert.

**An unstaged adapter** keeps `exec: {flags: unverified}`. It has no `exec_schema_version`, so the loader leaves it opaque, as it does today, and `exec_adapter.load` refuses it by name.

*Why not a second block type per harness family?* One closed schema with form-dependent keys is what the loader already does for `paths` and `formats`, and it keeps "an unknown key refuses the whole adapter" true.

### ADR-2: BR-11 is one function, `exec_verify.verdict`, read by the engine and by doctor

```
verdict(adapter, result, installed_version) -> Verdict(status, problems)
```

- `status` is `verified` or `unverified`. `problems` names each failing probe, version mismatch or declaration that disagrees with its verdict.
- **Hard probes** must read `pass`: `trust-then-headless` and `session-start-context` under `context_delivery: hooks`, only `trust-then-headless`'s `allowlist-loaded` variant under `prompt`; `stdin-prompt`'s variant named by `prompt_variant`; `fence-vs-allowlist`'s `runner-prefix` variant; and `ask-tier-deny`'s `deny-under-allow` where the `baseline` control's sentinel is present.
- **Declaration-bound probes** must read `pass` or `fail` and agree: `git-write-worktree` and `git-write-main` with `working_copy.strategy`; `ask-tier-deny` with `deny_render`; `shell-timeout` with `shell_timeout_s.delegate`.
- **Versions.** The result's `harness_version`, `exec.harness_version` and the installed binary's version (REQ-654's lookup, `harness._version`) must be equal.
- **`verification: recorded`** (Claude) skips the BR-11 gate, version equality included: BR-1 puts that gate on the four harnesses, and Claude's block stands on REQ-659's recorded evidence. A binary newer than the recorded version is shown in the doctor line and does not refuse the run. Gating it would stop every Claude exec run at the next Claude update, with no probe to re-run.

**Where the result is read from.** `<ToolkitRoot>/.adlc/research/harness-probes/<name>.json`, the install the orchestrator already holds a sha256 manifest of. ToolkitRoot is never a run's working copy, so this is BR-11's "the primary checkout, never a working copy". When the project under run is the toolkit itself, the working copy's own copy of the file is not read. A missing file reads `unverified`.

**Who calls it.** `preflight` (launch), the resume path, the close-out, and `approve` before the merge. `adlc harness doctor` prints `exec: verified` or `exec: unverified (<probe ids>)` from the same call. The yml's `status` and `probes` are caches: a `status` that disagrees with the verdict reads `unverified`.

**`--allow-unverified`** is a CLI flag of `sprint-exec run` only. It is never read from config, state or the environment. It applies to launches made by the invocation that received it, the ledger records it, and `approve` re-checks the verdict before the forge sees a merge call. It bypasses nothing else.

### ADR-3: rules are rendered to files for an `allow_render: file` adapter

`harness_render.exec_entries` already produces the exec-scope rule set. A new `render_exec_files(adapter, toolkit, result, values)` turns that set into file content through the adapter's own format renderer (`starlark-prefix-rule` for Codex):

- **The working-copy rule file** (`exec.rule_file`, Codex `.codex/rules/adlc-exec.rules`) holds the routine-tier allows that BR-3 keeps, the fence-runner allow as an absolute path, and a `forbidden` decision for every deny-tier entry and every `engine_deny` entry.
- **The user policy file** (`exec.user_policy_file`, a file of its own beside the operator's rules) holds the deny tier only. No allow is ever written at user level.

The render receives the probe result, which `exec_adapter.tiers` passes as `None` today, so a wrapper allow is restored only on a valid `deny_under_allow` pass. The run's `allowlist-fidelity` findings are compared with `accepted_fidelity` at `exec` scope in the pre-flight (BR-3): an undeclared loss refuses the run. A deny-tier entry with no deny spelling is `deny_unsupported`: a loud pre-flight line always, and a refusal for a local destructive move, or when branch protection is required and absent (BR-4).

Every path comes from the adapter. No `.codex` or `~/.codex` string appears under `tools/` (`test_no_codex_path_outside_the_adapter`).

### ADR-4: config surfaces are owned files with a manifest, in one module

`exec_surfaces.py` owns everything the engine writes into a working copy or a user policy folder for a run.

- **A surface** is a working-copy path from `exec.config_surfaces`. Each is rendered whole-file or made absent. A directory surface is compared with a manifest of sha256 per file, and a stray file is deleted. Under `context_delivery: prompt` the harness's hook file is a surface rendered absent.
- **Writes are guarded.** Every path component is `lstat`ed. A symlink, a hardlink (`st_nlink > 1`) or a non-regular file is refused, and the resolved path must be under the working-copy root.
- **Four checks.** Before launch and before resume a mismatch is repaired by re-render and logged as `rule_file_rerendered` with `checksum_matched: false`. At exit and at the halt a mismatch is `config_surface_violation`, a Rule B protocol violation that REQ-659's halt reports.
- **Tracked and untracked paths (BR-17).** A tracked surface is overwritten for the run, marked `skip-worktree`, and restored from the blob oid recorded at launch before the final push and at cleanup. An untracked one is hidden through `git config --worktree core.excludesFile`, which needs `extensions.worktreeConfig`. (Amended 2026-11-18, as built: the pre-flight sets the key in the main repository when it is absent, says so, and leaves it set, because concurrent runs' gitdir checksums cover that file; it refuses when the key is `false`, when `core.worktree` or `core.bare` is set, or when the write fails. The engine's own writes into a working copy's gitdir go through one lock that the gitdir checksum also takes.) The shared `info/exclude` is never written.
- **The PR-diff gate** runs once at the halt against `headRefOid` and the local `--no-renames` diff, case-folded, with directory surfaces as prefixes. Hits go to `ExecRun.plan.execPathTouched`. A non-empty list refuses `approve`, and `--ack-gate-change` does not cover it.
- **`bypass_config_keys`** is scanned in the user config and the working-copy config before launch and before resume. A hit refuses the run, and so does a file that cannot be parsed. Codex's TOML is read with `toml_merge.scan`, the reader the renderer already uses.
- **The user policy folder** is checked against a manifest at launch and resume: a missing or drifted toolkit-owned file, or a stray file, refuses the run. The file is written whole and atomically by `adlc harness install --exec` or the pre-flight.

*Why one module?* The same checksum, guard and manifest code serves rule files, config surfaces and the policy folder, and `sprint_exec.py` is already 1,900 lines.

### ADR-5: trust is written by the engine, in its own module, under one lock

`exec.trust_grant` gains `user-config-entry`. `exec_trust.py` writes `[projects."<working copy>"] trust_level = "trusted"` into the adapter's user config path before launch and removes exactly that block afterwards.

- The path must be absolute and resolve under the run's working-copy root. A relative path, an empty one or a symlink that escapes is refused before any write.
- The write is additive: every other byte is unchanged. A path already trusted is recorded `pre_existing` and survives revoke.
- Revoke runs on success, on failure and on the crash path, through REQ-659's cleanup. A revoke that finds its block gone is a warning.
- Concurrent runs are serialized by a lock directory beside the file (`mkdir`, the allocator's pattern).
- While REQ-664's recovery marker exists the engine refuses to launch, naming it: the probe edits the same file.
- The close-out working copy gets its own grant and revoke.
- No write touches `hooks.state` or any hook-review key.

**Why the grant exists on Codex (amended 2026-11-18).** As first written, this ADR took the grant to be what lets Codex load the working copy's rules. The real runs showed otherwise (`.adlc/research/harness-probes/codex-exec-manual.md`, facts 2 and 3). On a launch that no entry covers, `codex exec` writes `[projects."<main repo root>"] trust_level = "trusted"` into the user config by itself and keeps it. The key is the main repository's root, even from a linked worktree, so an unattended run would leave the whole repository trusted for every later session of the operator's. The rule file and the working copy's config took effect either way. With the engine's entry for the working copy in place first, Codex wrote nothing, and the revoke left the file byte-identical. So the grant stays, for that reason: it keeps a run from leaving trust behind, and it is not what loads the rules. The key a harness writes was wider than the run, as LESSON-777 warns.

The probe has its own trust edit (`harness_probe.codex_trust_edit`). The engine does not import it: the probe module is pinned to import only the standard library, and its backup-and-restore model is whole-file, which is wrong for a file two runs may edit at once. The block format is the same, so a test holds the two spellings equal.

### ADR-6: output is parsed by declared format, and Codex's launch carries `--json`

`exec.output` is `{format, source, final_message, session_id}`.

- `format: json` (Claude) is today's parser: one object, or the last JSON object line.
- `format: jsonl-stream` (Codex) reads every line as an event. `session_id` is `{event: thread.started, key: thread_id}`. `final_message` with `source: file` reads the `-o` file, whose path the engine substitutes as the `{last_message}` placeholder inside the run directory.
- A truncated stream, a line that is not JSON, or an empty final message is a parse failure: `exec.exitClass: error` with the parser's message in `notes`.
- `denied_stderr` is a pattern for the harness's own refusal line. A run with no claim and a matching line is `denied`. It never reads the model's text.

**This departs from the plan's §2f template** (`codex exec --sandbox workspace-write -C <wt> --output-schema … -o …`) in two tokens, and BR-2 is amended to say so:

- `--json` is added. The session id is on the JSON stream only, and without it there is no resume.
- `--output-schema` is dropped. The engine reads its claim from `pipeline-state.json`, not from the final message, so a schema for that message buys nothing.

The launch is then the argv REQ-664 measured: `codex exec --json --sandbox workspace-write -C <wt> -o <file>`, prompt on stdin with no positional (`prompt_variant: without-prompt-flag`).

### ADR-7: the final argv is checked against the template (closed world)

`ExecAdapter.launch_argv` builds the argv, then `closed_world(argv, template, pairs)` rebuilds what the template allows and compares for equality. The only accepted additions are:

- declared placeholders, each substituted as one whole token (`{worktree}`, `{last_message}`, `{session_id}`, `{settings}`, `{branch}`);
- the renderer's allow and deny flag pairs, for `allow_render: flags`;
- the adapter's declared isolation and resume tokens;
- an operator's `--harness-flag` whose flag name is in `exec.operator_flags`.

Anything else refuses the launch or the resume. `forbidden_flags` stays, as the lint backstop BR-16 calls it, and gains Codex's entries from the installed CLI's help: `--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`, `--approve-for-me`, `--full-auto`, `danger-full-access`, `--ask-for-approval never`, `--ignore-rules`, `--ignore-user-config`, `-c`, `--config`, `--profile`, `--enable` and `--disable`.

**`-p` is not in Codex's list.** BR-2 says Codex forbids every `-p` absent from its template, and AC-2 says no adapter's `launch` token may appear in any adapter's `forbidden_flags`. Claude's launch holds `-p`, its print flag, so listing it for Codex would fail AC-2. The closed-world check already refuses a `-p` the Codex template does not hold, which is the control BR-16 names, so the list leaves it out. An entry is spelled as separate tokens (`--approval-mode yolo`), never with `=`: the matcher splits `--flag=value` in the argv, not in the entry.

**Resume on Codex.** `codex exec resume` takes no `--sandbox` and no `-C`. The resume template is `exec resume --json -o {last_message} {session_id} -`, run with the working copy as the process directory, and its sandbox comes from the rendered `.codex/config.toml`. That form is not measured by any probe, so TASK-266 records one real launch and resume before the block is written as final. If the record shows resume does not hold the sandbox or the rules, the block declares no `resume`, and BR-7's halt message ("resume is impossible") is the behaviour. (Amended 2026-11-18: the record holds it. The resume continued the same session, and under it an allowed write left the sandbox, an un-allowed one did not, and a deny refused, so the block keeps `resume`; `codex-exec-manual.md`, rows `resume-continues` and `resume-keeps-rules`.)

### ADR-8: one census per adapter, and the runner accepts the union

`fence_census.census(root, adapter)` already takes an adapter. Stage 1 removes its `claude` defaults and adds `matcher`:

- `matcher: claude` keeps `exec_matcher` and the `direct` route.
- `matcher: none` (Codex) never routes `direct` (BR-3: no fence is `direct` until a measurement pins that harness's matching). `allow_extra` and `allow_extra_exact` must be empty there, because nothing can vet them.

Each exec-capable adapter has a golden, `harness/<name>/exec-fence-census.json`, and `fence_census --check` holds each one fresh.

**How `fence-run` knows which census applies** (the spec's open question). It does not need to. The runner accepts a fence when it is `runner`-routed in the census of **any** exec-capable adapter under its own ToolkitRoot, and the reach audit of every `runner` route is run against the **union** of every such adapter's deny tier and `engine_deny`. So no route the runner accepts reaches a command any adapter denies, whichever harness is calling. This needs no environment variable, argument or working-copy file, which ADR-2 of REQ-682 forbids.

*Rejected: a per-adapter entry point.* BR-3 names one path, `tools/adlc/fence-run`, for all four blocks.

### ADR-9: on Codex the branch push runs through the fence runner

With `direct` off, 59 of the 60 fences route. One does not: the Step 0 branch push, `git -C <worktree> push -u origin <branch>`. The reach audit refuses it with "a runner fence never pushes a branch", which is REQ-682 BR-2.

The push cannot be allowed by rule on Codex. A prefix rule has no exact form, so `["git","push","-u","origin","<branch>"]` also admits `<branch> --force`, and `never_restore` rightly holds `git push` out. An unallowed push runs inside the sandbox, with no network. So without a route the model can never push, and the pipeline cannot open its PR (LESSON-779).

REQ-682 BR-2 already excepts two pushes from the deny tier: the id-reservation push, and "the exact branch push `allow_extra_exact` names". Claude takes the second through an exact rule. **Codex takes the same exception through the runner**, which is exact by construction: it runs one argv and binds each value as data.

- The fence is audited as a second `PUSH_REACH` kind. It is accepted only when its push argv is exactly `git -C $ADLC_ARG_worktree push -u origin $ADLC_ARG_branch`.
- The `branch` placeholder's pattern is `^(feat|fix|chore)/[A-Za-z0-9][A-Za-z0-9._-]*$`. It cannot spell the integration branch, a refspec, a `+` prefix or an option.
- The `worktree` value must be the directory the runner was called from.
- The `branch` value must be the branch checked out in that directory. The runner accepts the union of `runner` routes (ADR-8), so this fence is also runnable on Claude; holding it to the checked-out branch keeps what a model can push there to what Claude's exact rule already allows, the run's own branch.
- On `matcher: claude` the fence stays `direct`, so Claude's behaviour does not change.
- The prompt for a `matcher: none` adapter carries one added sentence at that fence: a plain `git push` is refused on this harness, and the model re-runs this line whenever it needs to push.

REQ-682 BR-2 is amended to name the mechanism. This is the one change stage 1 makes to another REQ's rule, and it is flagged in the PR.

*Rejected: the `orchestrator-git` strategy.* The engine has the enum and no implementation, and one headless session runs every phase, so "push after each phase" has no place to happen. *Rejected: allowing `git push` at exec scope.* It admits a force-push by spelling.

What the allow list still cannot stop is unchanged and declared (BR-19): the structural gates are branch protection, the pinned merge and the halt.

**Amended 2026-11-18: two more bindings, and the runner's git environment.**

- **The push is bound to the run's REQ id.** Under an exec run `ADLC_EXEC_RUN` holds the run's REQ id, and the runner pushes only a branch `<type>/<REQ id>-<rest>`; a value of `ADLC_EXEC_RUN` that is not a REQ id refuses the push. So a model that checks out another REQ's branch in its working copy still cannot push it. Outside an exec run the variable is unset, and the checked-out-branch binding is the only one.
- **The runner's git environment.** The runner drops every caller `GIT_*` variable before the branch check and the fence, keeping only `GIT_TERMINAL_PROMPT=0`, and pins `core.fsmonitor=false` and `core.hooksPath=/dev/null` through `GIT_CONFIG_COUNT`, which outranks every config file (`fence_run.GIT_PINS`). A caller's `GIT_DIR` or `GIT_WORK_TREE` would point the branch check and the push at different repositories, and a `GIT_CONFIG_*` or `GIT_SSH_COMMAND` would run a program of the caller's choosing. A fsmonitor program or a hook would run model-written code outside the sandbox. So the `GIT_SSH_COMMAND` the Codex block passes through to the child never reaches the push, and an operator who needs a custom ssh command sets it in ssh config. The rest of the repository's config is honoured, and a model can write it, so `core.sshCommand`, a credential helper and `url.<base>.insteadOf` stay open: BR-19 (f), declared in the README.
- **Measured** on 2026-11-18 (`codex-exec-manual.md`, row `push-through-runner`): the runner line, exactly as the prompt prints it, pushed the branch to a local bare origin outside the sandbox's writable area. A push over the network to a forge was not part of the record.

### ADR-10: the exec fake gains a Codex profile

`tools/adlc/tests/fake_harness/exec_harness.py` stays the engine's double and becomes profile-driven by the name it is installed under: `claude` (today's behaviour) and `codex`. The Codex profile:

- parses `exec [--json] --sandbox … -C … -o …` and `exec resume …`, reads the whole prompt from stdin and records its line count, argv and environment;
- prints `thread.started`, `item.completed` and `turn.completed` events and writes the last message to the `-o` file, in the shape the committed probe captures show;
- fails loudly on any `forbidden_flags` token;
- can be scripted to exit with any code, write `awaiting_approval`, run an un-allowed command, edit a config surface mid-run, write to the user policy folder, and spawn a nested launch.

`exec_helpers.Sandbox` takes the harness name. Shared behaviours that Codex does not exercise are tested with fixture adapters under `tools/adlc/tests/fixtures/harness/`.

BR-12 says the exec scenarios extend REQ-664's probe double. REQ-659 already shipped a separate exec double, and the two fakes answer different questions: the probe fake models how a harness judges a command, the exec fake models a pipeline run. Stage 1 keeps them apart and holds their Codex output shapes equal with a test.

### ADR-11: what the Codex block declares, and why

| Key | Value | Evidence |
|---|---|---|
| `harness_version` | `codex-cli 0.166.0` | `codex.json` |
| `launch` | `exec --json --sandbox workspace-write -C {worktree} -o {last_message}` | the argv the probe measured |
| `prompt_variant` | `without-prompt-flag` | `stdin-prompt` `pass` |
| `context_delivery` | `prompt` | `hooks-loaded` `fail`; REQ-655's hook review cannot be granted headlessly |
| `working_copy.strategy` | `worktree` | `git-write-worktree` `pass`, both variants |
| `allow_render`, `deny_render` | `file`, `file` | `ask-tier-deny` `pass`, `deny-under-allow` `pass` |
| `matcher` | `none` | no measurement pins Codex's statement matching |
| `trust_grant` | `user-config-entry` | `codex-exec-manual.md`, facts 2 and 3: `codex exec` writes a lasting entry for the main repo root by itself when none covers it, and the engine's entry prevents that (amended 2026-11-18; first written as `allowlist-loaded` `pass`, which shows the rules load, not why the grant is needed) |
| `shell_timeout_s` | `{value: 125, verified: true, delegate: supported}` | `shell-timeout` `pass` |
| `rules_reload` | `unknown` | no probe variant yet; treated as `live` |
| `config_surfaces` | the `.codex` directory | REQ-655: read once the folder is trusted |
| `exit_codes` | `{"0": ok, "1": error}` | the committed captures; an unmapped code is `error` |

`deny_under_allow` in `harness/codex.yml` moves to what the result measures: `prefix` is a `pass` with mechanism `deny`, and `git-c` is a `fail`, so the `git -C` allow stays omitted and a deny-tier `git -C` spelling is `deny_unsupported`. `env-prefix` and `shell-opener` stay `unverified`. The project render uses mechanism `confirm`, which these records do not match, so the committed goldens do not change.

### Review note, 2026-11-18: the routine allows leave the sandbox on Codex

The review of 2026-11-18 found that on Codex the exec-scope routine allows leave the sandbox. A matched `allow` runs outside `workspace-write`, so `ls` and `git status` do, and so do the allows that execute their arguments (`npx`, `npm run`, `find -exec`, `awk`, `git rebase -x`, `git fetch --upload-pack`, `gh api`), which then run arbitrary code with the operator's filesystem and network. Only some routine commands need an escape: a commit writes the common git dir, and `gh`, a fetch and the runner's push need the network. Every allowed one takes it.

Stage 1 records this and does not close it. It is a declared residual in the README's Codex exec section (BR-19 b, with the sandbox named), and keeping in the sandbox the routine commands that need no escape is an input to a follow-up requirement. Nothing in this design depends on the sandbox: the gate is the approval halt (Rule B).

## Testing

- **Unit:** the loader's refusals (AC-1), `exec_verify` over fixture result files (AC-11, AC-16, AC-17, AC-25), the closed-world check (AC-19), the parsers over committed fixtures (AC-6), the surfaces guard (AC-18), trust edits under a sandbox `HOME` (AC-5).
- **End to end, offline:** the approval-protocol suite against the Codex fake: launch, `awaiting_approval`, approve, merge through the forge mock, resume, done; and the reject path with trust revoked (AC-8, AC-12).
- **Lints:** `exec-no-bypass` and `exit-class-vocabulary`, each firing on its fixture (AC-2, AC-12).
- **Shells:** `sh partials/tests/run.sh` under bash, zsh, `/bin/sh` and dash (AC-12).
- **Real runs:** one recorded Codex launch and resume in a throwaway repository, `.adlc/research/harness-probes/codex-exec-manual.md`, following `claude-exec-manual.md`. It supplies the parser fixtures (BR-6) and checks what no probe measures: the resume form, and the exec-named rule file loading in a linked worktree.
- **No test writes outside a sandbox `HOME` and `ADLC_HOME`.**
