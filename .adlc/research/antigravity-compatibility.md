# Antigravity CLI compatibility note

Recorded on 2026-10-31 from `agy` 1.4.12 on darwin arm64, for REQ-658. This note decides
what `harness/antigravity.yml` declares. A row established only from docs or from the
binary's text reads `unverified`, never `usable`.

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

`agy -p` cannot prompt, so a tool that needs a permission **ends the run**: exit 0, empty
response, a notice on stderr. Only a hard `deny` leaves the run going: the model sees the
error and carries on. The first full run allowed only the commands under test, and the
model often looked around first (`git status`, `ls -la`, `mkdir -p`), so many launches died
before reaching the command. The result file records that as it happened, and these
readings are what it means:

| Probe | Reads | Means |
|---|---|---|
| `git-write-worktree` | `pass` | decided by the bare remote's ref, re-run once with `prep_allow` in the profile. This is the REQ-655 BR-10 gate. The file's `launches` field reads 1 because `--only` rewrites it: the two runs made 19 launches |
| `git-write-main` | `fail` | an artifact: the model ran `git status` first, and the launch ended. Owed |
| `shell-timeout` | `fail` | an artifact: `ls -la` first. Owed |
| `ask-tier-deny` | `unknown` | the `allow-only` controls died the same way, so the variants stay `unknown`. `lone-deny`'s launch and `deny-under-allow`'s are still evidence: see `permissions` below |
| `fence-vs-allowlist` | `fail` | real. The model ran the fence as written, and it was refused in all three variants |
| `skill-activation` | `pass` | the skill activated from its description, and the `touch` ran under `command(touch)` |
| `session-start-context` | `pass` | real |
| `trust-then-headless` | `pass` | real, on `hooks-loaded`. `allowlist-loaded` is `n/a`: no project-local allow form |
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

Re-running `adlc harness probe antigravity`, now that the profile carries `prep_allow`, needs
17 more launches. This run stopped at the launch budget. What it should settle:
`git-write-main`, `shell-timeout`, and `ask-tier-deny`, which is the record
`deny_under_allow` reads.

Also owed, with no quota cost beyond the session itself: the TUI's trust dialog, a deny-tier
spelling at a prompt, and `~/.agents/skills`. Each needs the operator: the first two need
onboarding finished, and the third writes to `~/.agents`.
