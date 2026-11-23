# Antigravity CLI compatibility note

Recorded on 2026-10-31 from `agy` 1.4.12 on darwin arm64, for REQ-658. This note decides
what `harness/antigravity.yml` declares. A row established only from docs or from the
binary's text reads `unverified`, never `usable`.

The probe result file was rewritten on 2026-11-23 by a run during which `agy` updated itself
to 1.5.15. "Reading the probe result" below says what that file now holds. The Compatibility
table is still the 1.4.12 evidence, and the adapter still states 1.4.12.

## How the evidence was gathered

Free inspection came first (LESSON-766): `agy --help`, `agy plugin validate --json`, and
the print-mode commands `/skills`, `/agents`, `/hooks`, `/permissions` and `/config`. Those
report `num_turns: 0` and zero tokens under `--output-format json`, so they start no model
session, and they read the workspace they run in. `/hooks` was the inventory checked before
any hook reading (LESSON-765).

Model sessions went to what inspection could not answer. They are `adlc harness probe
antigravity` (`.adlc/research/harness-probes/antigravity.json`) and these hand cases, each
in a throwaway repository, on `gemini-3.8-flash-low`:

| Case | What it asked | What it showed |
|---|---|---|
| H1 | a project `SessionStart` hook, no trust record, `-p` | the hook ran in `<repo>/.agents`, and its `injectSteps` system message reached the model |
| H2 | a linked worktree: a JSON hook, a plain-stdout hook, an `AGENTS.md` rule, and `/big-probe`, a skill of 38,625 bytes | the JSON hook and the rule reached the model. The plain hook failed with `failed to unmarshal result`. The skill body was cut, and the text past the cut never arrived |
| H3 | a skill whose `SKILL.md` says to read a companion file outside the workspace | `read_file` auto-denied. Exit 0, `status: SUCCESS`, empty response, a notice on stderr |
| H4 | H3 with `read_file(<dir>)` allowed, and a step that invokes a subagent | the companion read succeeded. `SessionStart` fired again for the subagent's own conversation, and its transcript holds the hook's system message at step 0 |
| H5 | `--agent` with `tools: [view_file]`, `command(touch)` allowed, told to run `touch` | it replied `NOTOOL` and the sentinel stayed absent |
| H6 | allow `command(touch)`, ask `command(touch <target>)`, run a witness then the target | the model chained both, and the whole line was refused. A chain is judged part by part. Nothing here shows the allow matched a chain, so this is consistent with `ask` beating `allow`, and it does not prove it |
| H7 | list your tools | `read_file`, `run_command`, `manage_task`, `send_message`, `schedule`, `invoke_subagent`, `define_subagent`, `manage_subagents`, `write_file`, `edit_file`, `search_web`, `ask_question` |
| H8 | H7 under `--agent` with current and legacy names in `tools:` | every listed name resolved, `grep_search` and `find_by_name` included, and the agent did not hang |
| H9 | the adapter's own render in a throwaway project: `.agents/hooks.json` as `adlc harness render` wrote it, partials vendored, `.adlc/ETHOS.md` holding a marker, one subagent | the marker reached the main session and the subagent, and `.adlc/.session/` holds one sidecar for each, `harness=antigravity`, with `cwd` the project root |

A `PreInvocation` hook that returned `terminationBehavior: "terminate"` made no model call
(zero tokens), and gave the exit code in the last row of the table below.

Four user-level paths have no throwaway form, so each was written, read with one
inspection command, and removed, with the directory listed before and after:
`~/.gemini/config/skills.json`, `~/.gemini/config/hooks.json`,
`~/.gemini/config/agents/<probe>.md` and `~/.gemini/antigravity-cli/settings.json`. `agy
plugin install` ran only under a throwaway `HOME`, which it allows signed out. The real
`~/.gemini/config/plugins` was never created.

### Reading the probe result

The file was rewritten on 2026-11-23 by one full run of the current probe tool
(`5.4.0+1d40f47`): 31 planned launches, 40 made, 9 of them retries, 39 of them model
sessions. One fact comes before any reading of it.

**`agy` updated itself during the run, so the file's `harness_version` is wrong for all but
the first launch.** `agy --version` read 1.4.12 before the run, and the tool reads the
version once, at the start. The binary on disk was replaced at 11:35:25 local, four seconds
into the first launch, and has read 1.5.15 since. `trust-then-headless` (`l01`) started on
1.4.12 and shows that version's behaviour: an un-allowed `touch` was auto-denied with the
stderr notice. Every later launch started after the replacement. Nothing in the file says
so. It is therefore not a full run for 1.4.12, and it is not labelled as a run for 1.5.15.
REQ-662 opens a stage only on a full run for the installed binary version, and this is not
one.

What 1.5.15 changed, as these launches show it: **`agy -p` ran commands no rule allowed.**
On 1.4.12 such a command ended the run. Here the `baseline` controls ran an un-allowed
`touch` and an un-allowed `git -C <repo> push --force`, `runner-baseline` ran the stub with
no runner allow, and no launch after the first was refused on stderr. One transcript shows
the commands running in a terminal sandbox: a listing under `~/.gemini/antigravity-cli/brain`
came back `Operation not permitted`, with an offer to retry with `BypassSandbox` "to request
explicit user permission". Nothing here measured what that sandbox confines. A push to the
bare remote beside the repository went through it.

| Probe | Reads | Ran on | Means |
|---|---|---|---|
| `trust-then-headless` | `pass` | 1.4.12 | `hooks-loaded` is `pass`. `allowlist-loaded` is `n/a`: no project-local allow form. The only launch on 1.4.12 |
| `git-write-main` | `pass` | 1.5.15 | the bare remote's `main` advanced to a commit holding the nonce file. No longer an artifact. `prep_allow` did not decide it, because nothing was refused |
| `git-write-worktree` | `pass` | 1.5.15 | the same from the linked worktree. The adapter's `sandbox_can_reach_common_gitdir` was read from the 2026-10-31 `pass`, on 1.4.12 with the sandbox off |
| `shell-timeout` | `pass` | 1.5.15 | the sentinel appeared 125 s after the start marker, so one shell call outlived the sleep. No longer an artifact |
| `ask-tier-deny` | `unknown`, `ask-not-reached` | 1.5.15 | not the old artifact. Two limits of the probe keep it there: see the next table |
| `skill-activation` | `pass` | 1.5.15 | the skill activated and its `touch` ran |
| `session-start-context` | `pass` | 1.5.15 | the hook's nonce came back |
| `stdin-prompt` | `pass` | 1.5.15 | `without-prompt-flag` returned the nonce. `with-prompt-flag` is `agy -p ""`, which exits 1 before the model with `empty prompt`, so it reads `unknown`, `binary-exit-1` |
| `fence-vs-allowlist` | `pass` | 1.5.15 | the reverse of 2026-10-31's `fail`, and not because a rule matched: all three fence variants ran because nothing is refused. `runner-prefix` reads `pass` on its positive half with `boundary: none`. `runner-baseline` ran with no allow, and all eleven refusal controls were admitted. The runner allow is no boundary on this version |
| `transcript-locate` | `pass` | 1.5.15 | 164 session files newer than the first launch |
| `arg-substitution` | `n/a` | | a Claude question |

`ask-tier-deny`, launch by launch:

| Launch | Reads | What it showed |
|---|---|---|
| `baseline` | `pass` | the un-allowed `touch` ran |
| `allow-only` | `pass` | the `touch` ran under `command(touch)` |
| `baseline-git-c` | `pass`, 2 attempts | the un-allowed `git -C <repo> push --force` created the ref. The first attempt spanned a sleep: see below |
| `allow-only-git-c` | `pass` | the push ran under `command(git -C)` |
| `lone-deny` | `unknown`, `ask-not-reached`, 5 attempts | target absent and witness present on every attempt. Four read `not-attempted`, and the fifth returned no nonce |
| `deny-under-allow` | `unknown`, `precondition-unmet: allow not required (baseline ran the command)`, 5 attempts | target absent and witness present on every attempt |
| `wrapped-allow` | `unknown`, `precondition-unmet: allow not required (baseline-git-c ran the command)` | the ref is present: the push ran under a deny of the plain spelling |

Two limits of the probe keep `ask-tier-deny` at `unknown`, and a re-run on 1.5.15 would meet
both again:

1. **The probe cannot see a hard deny on `agy`.** Its proof that a command was submitted is
   a `command` field in the harness's stdout records, or a refusal line on stderr. `agy`'s
   JSON carries no command record, and a hard deny prints nothing on stderr while the run
   goes on. So `lone-deny` and `deny-under-allow` read `not-attempted` and are retried to
   the cap, which is 8 of the 9 retries. The session transcript does hold the proof:
   `tool_calls[].args.CommandLine`, then an `ERROR` step.
2. **Where the baseline runs the command, the tool reads `deny-under-allow` and
   `wrapped-allow` as `precondition-unmet`, whatever the launch showed.** REQ-662 BR-11 makes
   `deny-under-allow` a hard probe on exactly such a harness, so the two rules cannot both
   be met as written.

Read by hand from the transcripts of the last attempts. This is evidence, and it is not a
probe verdict:

| Launch | The transcript |
|---|---|
| `lone-deny` (`l04r5`) | `touch <target>` was submitted and refused: `Permission denied for command(touch <target>). Matches user-configured deny rule.` |
| `deny-under-allow` (`l05r5`) | the same refusal, under a matching `command(touch)` allow |
| `wrapped-allow` (`l06`) | `git -C <repo> push --force origin HEAD:<ref>` ran and created the ref, under a deny of `git push --force origin HEAD:<ref>` |

So on 1.5.15 a hard deny held alone and under a prefix allow, and a deny of the plain
spelling did not reach the `git -C` spelling. `never_restore` already omits `git -C`.

Three things about the run itself:

- **A sleep.** The machine slept with its lid closed from 11:44:05 to 11:59:44 local, with
  `baseline-git-c`'s first attempt (`l09`) in flight. The tool's 300 s cap counts awake time,
  so the launch was not cut. It returned without pushing, read `not-attempted`, and the
  retry measured. No other launch overlapped the sleep.
- **The model read the probe's own captures.** In `l09r2` it listed `<run_dir>/captures`,
  read earlier launches' settings and output files, and tried to list a session directory
  under `~/.gemini/antigravity-cli/brain`, which the sandbox refused. Those files hold
  earlier launches' nonces and replies, never the current launch's, and no verdict here
  turned on them. The run directory is still readable from the repository the model works
  in.
- **User-level files.** The probe edits none on this harness, and none of
  `~/.gemini/settings.json`, `trustedFolders.json`, `projects.json`, `state.json` or
  `~/.gemini/config/` changed: each was compared byte for byte after the last launch, and no
  recovery marker was written. `agy`'s own update is what changed the machine: the binary,
  `~/.gemini/antigravity-cli/jetski_state.pbtxt` (rewritten once, at the first launch), and
  three new directories, `~/.gemini/sandbox/`, `~/.gemini/antigravity-cli/daemon/` and
  `~/.gemini/antigravity-cli/persistent_terminals/`. None of that was reverted.

#### The 2026-10-31 readings, on 1.4.12

The file no longer holds these. They are in git history at `523ce76`, and they are what the
Compatibility table below and the adapter cite. `agy -p` could not prompt, so a tool that
needed a permission **ended the run**: exit 0, empty response, a notice on stderr. Only a
hard `deny` left the run going. That run allowed only the commands under test, and the model
often looked around first (`git status`, `ls -la`, `mkdir -p`), so many launches died before
reaching the command.

| Probe | Read | Meant |
|---|---|---|
| `git-write-worktree` | `pass` | decided by the bare remote's ref, re-run once with `prep_allow` in the profile. This is the REQ-655 BR-10 gate |
| `git-write-main` | `fail` | an artifact: the model ran `git status` first, and the launch ended |
| `shell-timeout` | `fail` | an artifact: `ls -la` first |
| `ask-tier-deny` | `unknown` | the `allow-only` controls died the same way. `lone-deny`'s launch and `deny-under-allow`'s were still evidence: see `permissions` below |
| `fence-vs-allowlist` | `fail` | real on 1.4.12. The model ran the fence as written, and it was refused in all three variants |
| `skill-activation` | `pass` | the skill activated from its description, and the `touch` ran under `command(touch)` |
| `session-start-context` | `pass` | real |
| `trust-then-headless` | `pass` | real, on `hooks-loaded`. `allowlist-loaded` was `n/a` |
| `stdin-prompt` | `pass` | `agy` with no `-p` takes stdin as the prompt. `agy -p ""` exits 1 |
| `transcript-locate` | `pass` | real |

## Compatibility

| Surface | How | `agy` | Path or key | Verdict | Evidence |
|---|---|---|---|---|---|
| settings | inspection | 1.4.12 | `~/.gemini/antigravity-cli/settings.json` | usable | a written file reached `/permissions` and `/config`, then was removed |
| settings | probe | 1.4.12 | `agy --settings <json or file>` | usable | every probe launch; session-only; an unknown key is refused by name |
| permissions | inspection | 1.4.12 | `permissions.allow`, `.ask`, `.deny` | usable | `/permissions`; the singular `permission` is `unknown setting` |
| permissions | probe | 1.4.12 | `command(<words>)`: word-by-word prefix | usable | `skill-activation`: `command(touch)` ran `touch <path>`; `git-write-worktree`: `command(git commit)` and `command(git push)` |
| permissions | probe | 1.4.12 | `permissions.deny`, headless | usable | `lone-deny` launch: target absent, witness present, the model saw `Permission denied` and replied. `deny-under-allow` launch: target absent under a matching `command(touch)` allow, witness present |
| permissions | inspection | 1.4.12 | `permissions.ask` over `allow` | unverified | H6 is consistent with it, and the docs say Deny > Ask > Allow. The probe does not measure it |
| permissions | docs | 1.4.12 | `permissions.deny`, interactive | unverified | the TUI stopped at first-run onboarding |
| permissions | probe | 1.4.12 | a partial-sourcing fence | unusable | `fence-vs-allowlist`: refused in every variant, because a compound line is judged part by part |
| project-config | inspection | 1.4.12 | a permission file in the repository | unusable | a rule in `.agents/settings.json`, `.agents/permissions.json`, `.agents/config.json` or `.gemini/settings.json` reached no `/permissions` scope |
| project-config | inspection | 1.4.12 | `.agents/hooks.json`, `.agents/skills.json`, `.agents/agents/`, `.agents/skills/` | usable | `/hooks`, `/skills`, `/agents` |
| hooks | probe | 1.4.12 | `.agents/hooks.json`, a map of named hooks | usable | `session-start-context`, H1, H2; `/hooks` lists the file |
| hooks | probe | 1.4.12 | a hook's working directory is `.agents/` | usable | H1 and H2 recorded `pwd` |
| hooks | inspection | 1.4.12 | `~/.gemini/config/hooks.json` | usable | written, listed by `/hooks`, removed |
| hooks | probe | 1.4.12 | payload `conversationId`, `transcriptPath`, `workspacePaths` | usable | H1 recorded the payload. `workspacePaths` is a list, so there is no `cwd` string |
| hooks | inspection | 1.4.12 | timeout in seconds | usable | `/hooks --output-format json` reports `timeout_seconds` |
| hooks | docs | 1.4.12 | a compaction event | unverified | the event list names none, and `SessionStart` is documented as once per session |
| hook-output | probe | 1.4.12 | `{"injectSteps":[{"systemMessage":{"systemMessage":…}}]}` | usable | H1, H2, H4, H9, `session-start-context` |
| hook-output | probe | 1.4.12 | plain stdout | unusable | H2: `failed to unmarshal result`, logged, and the other hook still ran |
| skills | inspection | 1.4.12 | `~/.gemini/config/skills.json`, `entries[].path` | usable | written, listed by `/skills`, removed; a directory of symlinks also loads |
| skills | probe | 1.4.12 | `.agents/skills/<name>/SKILL.md` | usable | `skill-activation`, `/skills` |
| skills | docs | 1.4.12 | `~/.agents/skills` | unverified | not in `agy`'s documented locations. The only test writes to `~/.agents`, and this run may not. A home with `.gemini` linked in does not sign in |
| skills | probe | 1.4.12 | a body past 24,000 bytes, when invoked | unusable | H2: replaced by `<truncated N bytes>`, and no path is given. `agy plugin validate` warns of the same cap. Nine toolkit skills are past it |
| skills | probe | 1.4.12 | a companion file outside the workspace | usable | H3 refused, H4 read it under `read_file(<dir>)` |
| agents | inspection | 1.4.12 | `~/.gemini/config/agents/<name>.md` | usable | written, listed by `/agents`, removed |
| agents | probe | 1.4.12 | `tools:` as a YAML list, enforced | usable | H5; H8 for the names |
| agents | docs | 1.4.12 | an agent with no `tools:` | unverified | the docs give a default of `[]` and do not say what that means, so the render writes the full mapped list for `pipeline-runner` and `task-implementer`, the form H8 showed working |
| agents | inspection | 1.4.12 | `model: inherit`, `flash` or `pro` | unverified | `agy plugin validate` loads these and refuses `opus` and every model id. No run shows what they resolve to on this account |
| agents | probe | 1.4.12 | `SessionStart` in a subagent | usable | H4. It needs the project hook file, and agent copies are user-level |
| rules | probe | 1.4.12 | `AGENTS.md` at the project root | usable | H2, in a linked worktree |
| plugins | inspection | 1.4.12 | `agy plugin install` on the Claude Code manifest | unusable | staged under a throwaway `HOME`. `agy plugin validate` on the result: 0 skills, 19 agent errors, `hooks.json` skipped |
| plugins | inspection | 1.4.12 | a native manifest with `"skills": ["./"]` | unusable | loads 17 skills, as `adlc:..:review`. `--strict` cannot pass: 9 over the cap, and `AGENTS.md`, `hooks/hooks.json` and `workflows/` warn, and none of them can move |
| trust | probe | 1.4.12 | none needed under `-p` | usable | `trust-then-headless`, H1, H2: hooks, skills and agents loaded with no record, in a repository and a linked worktree |
| trust | docs | 1.4.12 | the TUI's dialog, `trustedWorkspaces` | unverified | first-run onboarding came first, and finishing it writes user settings. The key is accepted by `--settings` and appears in `/config` |
| transcripts | probe | 1.4.12 | `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript_full.jsonl` | usable | `transcript-locate`; the hook payload names it. JSONL with `step_index`, `source`, `type`, `status`, `content`. Located, not parsed (REQ-660) |
| exit-codes | probe | 1.4.12 | `0`, also on an auto-deny, with an empty response | usable | H3, H6, and most probe launches. `denied_actions` in the JSON names the tool |
| exit-codes | inspection | 1.4.12 | `1` before the model, `2` a bad flag, `3` a hook terminated | usable | an unknown model and a signed-out run read 1; `--no-such-flag` read 2; the `terminate` hook read 3 |

## The route

`render` on every surface. REQ-658 BR-4 prefers the plugin route where it delivers a surface
with no new renderer, and it delivers none: see the `plugins` rows.

| Surface | Route | Reason |
|---|---|---|
| skills | render | one user-level `skills.json`; skills keep bare names |
| agents | render | a comma `tools:` line and `model: opus` both fail the loader, so copies are needed |
| hooks | render | the Claude Code plugin's hook shape fails to parse |
| permissions | printed | `project-config` shows no file in a repository supplies them |
| instructions | render | `AGENTS.md`, as for every harness |

## What this decides in the adapter

| Field | Value | From |
|---|---|---|
| `capabilities.committable_allowlist` | `no` | `project-config` |
| `capabilities.allowlist_granularity` | `token-prefix` | `permissions` |
| `capabilities.deny` | `yes` | `permissions.deny`, headless |
| `deny_tier_render` | `{user: deny}` | the same; interactive is owed |
| `capabilities.deny_under_allow.*` | `unverified` | the probe reads `unknown`, and this field is read from the probe, never hand-set |
| `capabilities.agent_tool_restriction` | `enforced` | H5 |
| `capabilities.subagent_start_hook` | `no` | H4 shows it fires, but it needs a project file an agent copy cannot rely on |
| `capabilities.compact_rehook` | `no` | no compaction event |
| `sandbox_can_reach_common_gitdir` | `true` | `git-write-worktree` `pass`, in the default mode with `enableTerminalSandbox` off |
| `tier_map` | every alias `unverified` | `agents`, so `model` is omitted |
| `trust.mechanism` | `none` | `trust` under `-p`; the TUI is owed |
| `mount` (detect) | `skills-config` | `skills` |

## Owed

**A full probe run on one `agy` version.** The 2026-11-23 run straddled the update, so no
result exists for 1.5.15, the installed version, and none can be made for 1.4.12. A full run
is 31 planned launches, and this one took 40. Four things should come first, or the next run
repeats this one:

1. **The adapter states 1.4.12.** On 1.5.15 an un-allowed command ran under `agy -p`, so the
   adapter's notes on a headless run ending at the first prompt, on fences, and on
   `fence_unmatchable` need re-deriving, with the README section that follows them.
2. **`ask-tier-deny` cannot read better than `unknown` on `agy`** until the probe takes
   proof of submission from the session transcript, and until the rule for a harness whose
   baseline runs the command is settled against REQ-662 BR-11.
3. **The probe reads the version once.** It should read it again at the end and refuse to
   write a result whose version moved.
4. **Whether `agy`'s self-update can be held off for a run** is not known.

Also owed, with no quota cost beyond the session itself: the TUI's trust dialog, a deny-tier
spelling at a prompt, and `~/.agents/skills`. Each needs the operator: the first two need
onboarding finished, and the third writes to `~/.agents`.
