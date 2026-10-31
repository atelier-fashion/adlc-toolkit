---
id: REQ-658
title: "Antigravity CLI adapter: `agy` as a harness, evidence first, then `harness/antigravity.yml` and the route the evidence supports"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-31
component: "adlc/harness"
domain: "adlc"
stack: ["python", "sh", "json", "markdown", "yaml"]
concerns: ["portability", "harness-agnostic", "developer-experience", "security"]
tags: ["antigravity", "agy", "harness", "multi-harness", "adapter", "probe", "plugin", "hooks", "allowlist", "agents", "doctor", "install", "ethos", "permissions", "deny", "trust", "skills", "gemini"]
lane: "full"
lane_reason: "adds a harness to the detect and probe tables, renders or installs hook and allowlist configuration (security/infrastructure config), and the footprint spans harness/, tools/adlc, doctor, README and research notes, far above max_files"
lane_forced: false
---

## Description

This is Phase 4 of `.adlc/research/multi-harness-plan.md` (revision 2), rewritten
on 2026-10-31. It was the Gemini CLI adapter. Gemini CLI is no longer available to
individuals, Google moved those accounts to Antigravity CLI (`agy`), and the
operator's machine has `agy` signed in and `gemini` unusable. The spec required
the intersection of the two CLIs from a real install of each, which can no longer
be met, and a read of `agy` 1.4.12 showed its surfaces are not Gemini CLI's. So
this REQ now targets Antigravity CLI alone.

What a read of the binary, its `--help` and its changelog showed on 2026-10-31.
None of this has been tested, and BR-1 replaces it with evidence:

- **Settings** live in `~/.gemini/antigravity-cli/settings.json`. Permissions are
  rules such as `command(git status)`, `read_file(…)`, `write_file(…)`, `read_url(…)`,
  `mcp(…)` and `execute_url(…)` under `permission.allow`, with `ask` and `deny` lists
  referred to. Project permissions appear to live at
  `~/.gemini/config/projects/`, outside the repository, so a committed project
  allowlist may not exist on this harness.
- **Workspace customizations** live under `.agents/` (`skills/`, `rules/`,
  `agents/`, workflows), and user ones under `~/.gemini/config/`. `AGENTS.md` and
  `GEMINI.md` are read as rules.
- **Hooks** are shipped in a plugin's `hooks.json`. The changelog names
  `PreInvocation`, `PostInvocation`, `PostToolUse` and `Stop`, and `SessionStart`
  is in the binary.
- **Plugins** have `plugin.json`, `skills/`, `agents/`, `rules/AGENTS.md` and
  `hooks.json`. `agy plugin import` reads Gemini and Claude Code extensions, and
  `agy plugin validate --strict` exists. Rules in a plugin's `rules/AGENTS.md` are
  always on while it is enabled.
- **Headless** is `agy -p`, with `--mode`, `--sandbox`, `--settings` and
  `--output-format`. `--dangerously-skip-permissions` also exists. A failed
  headless run exits `3`.

So the adapter's shape is not known yet, and this spec does not guess it. A plugin
install may deliver skills, agents, rules and hooks with little rendering, or it
may not. The REQ first teaches the toolkit that `agy` exists, then gathers evidence,
and then builds the route that evidence supports. Everything stays additive, and
nothing that works on Claude Code moves (plan Rule A).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| HarnessEntry | name | string | `antigravity`, in the `adlc harness detect` table and the probe table; `NAMES` in both gains it |
| HarnessEntry | binaries | list | `("agy",)`; the installer's default location `~/.local/bin` is reached through PATH, never a literal path in code |
| HarnessEntry | mount | enum | decided by the note: `agents` only if `agy` is shown to read `~/.agents/skills`; otherwise a value the note records |
| ProbeProfile | harness | string | `antigravity`, one `Profile` in `tools/adlc/harness_probe.py` beside the five that ship |
| ProbeResult | path | path | `.adlc/research/harness-probes/antigravity.json`, plus a transcript fixture where one is captured, scrubbed of email, login name and account ids |
| CompatibilityNote | path | path | `.adlc/research/antigravity-compatibility.md` |
| CompatibilityNote | row | tuple | surface (`settings`, `permissions`, `project-config`, `hooks`, `hook-output`, `skills`, `agents`, `rules`, `plugins`, `trust`, `transcripts`, `exit-codes`) × (how it was established: `inspection`, `docs` or `probe`; the `agy` version; the path or key observed; the verdict `usable`, `unusable` or `unverified`) |
| CompatibilityNote | route | enum | `plugin`, `render` or `mixed`, with the reason |
| AntigravityAdapter | file | path | `harness/antigravity.yml`, validated by REQ-657's loader at the next `schema_version`; a field the schema does not know is a load error |
| AntigravityAdapter | sandbox_can_reach_common_gitdir | enum | required at this schema version: `true` or `false` from `git-write-worktree`; `unverified` is refused by `adlc harness doctor` (REQ-655 BR-10) |
| AntigravityAdapter | capabilities | struct | `deny` per the note; `subagent_start_hook: no` unless a recorded run shows otherwise; `compact_rehook` per the note; `agent_tool_restriction`, `allowlist_granularity` and `committable_allowlist` per the note; `deny_under_allow` read from the probe, never hand-set |
| AntigravityAdapter | hook_events, hook_payload, hook_output, hook_timeout_unit | map | canonical events mapped from what the note shows; an event `agy` lacks is `unsupported`; `hook_output` is declared from a recorded run, and plain stdout is not assumed (LESSON-757) |
| AntigravityAdapter | trust | struct | `{mechanism, detail}` per the note; declared, not exercised |
| AntigravityAdapter | tool_map, tier_map | map | canonical tool → `agy` tool name, or `unsupported`; alias → model id, or `unverified` |
| AntigravityAdapter | accepted_fidelity | map | every `widened:<spelling>`, `inexpressible` and `deny-unsupported` verdict the render produces; a verdict not in the map fails `allowlist-fidelity` |
| AntigravityAdapter | doctor_rows | list | data only; a trust row exists only if the note finds a trust record doctor can read |
| AntigravityAdapter | exec | map | opaque; its keys are REQ-659's and REQ-662's |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| harness_detected | `adlc harness detect` | `antigravity`'s state, path, version and mount |
| probe_recorded | `adlc harness probe antigravity` | the result file; `n/a` with a reason for a probe that does not apply |
| compatibility_recorded | the note lands in `.adlc/research/` | per-surface verdicts and the chosen route |
| antigravity_installed | `adlc harness install --harness antigravity` | surfaces written or the install command printed; never run by `/init` |
| fidelity_reported | `allowlist-fidelity` over the render | per-entry verdicts, each matched against `accepted_fidelity` |
| doctor_antigravity | `adlc doctor` | `harness:antigravity`, `render-currency:antigravity` and any `doctor_rows` entry |

_Permissions: not applicable — single-user machine tooling. Section omitted deliberately._

## Business Rules

- [ ] BR-1: **Evidence comes first.** Before any adapter file or renderer is written, `.adlc/research/antigravity-compatibility.md` records every CompatibilityNote row and the route, from the `agy` version installed. Free inspection comes first: `agy --help`, `agy plugin validate`, read-only print-mode slash commands, `https://antigravity.google/docs/cli/reference`, and any other command that starts no model session (LESSON-766). Model sessions go to questions inspection cannot answer. A row established only from docs or the binary's text reads `unverified`, never `usable`. Before a hook probe's `fail` is read as a format defect, the note checks the harness's own hook inventory and trust state (LESSON-765). The architecture's task list orders the BR-2 and BR-3 work, then the note, before any adapter task.
- [ ] BR-2: **`agy` is a harness the toolkit knows.** `antigravity` joins the `adlc harness detect` table with binary `agy`, and `harness:antigravity` joins doctor as report-only, SKIP when absent. Its `mount` is reported from what the note establishes, not assumed to be the `~/.agents/skills` mount.
- [ ] BR-3: **`agy` can be probed.** `adlc harness probe antigravity` runs REQ-664's catalogue through a new profile. Every probe that applies runs, and a probe that does not apply is `n/a` with a reason. `--dry-run` names every launch and every user file touched. A user file is backed up and restored byte for byte, as for every other harness. The result file and any fixture hold no email, login name or account id, and a scrubber gap found here is fixed in the scrubber. `tools/adlc/harness_probe.py` remains the one exempt place that branches on a harness name.
- [ ] BR-4: **The route follows the note.** The note compares installing the toolkit as an `agy` plugin (`agy plugin install`, or `agy plugin import claude` on a Claude Code plugin install) with rendering into `agy`'s surfaces. The plugin route is preferred where it delivers a surface with no new renderer. Each surface uses one route, and the adapter says which. If a manifest is added, REQ-665's `manifest-parity` covers it and `agy plugin validate --strict` passes on the clone. `agy plugin` runs only from an explicit `adlc harness install --harness antigravity`, never from `/init`, and a route that needs a user step prints that step.
- [ ] BR-5: **`harness/antigravity.yml` is data, not a branch.** Every Antigravity-specific fact lives in that file through REQ-657's loader, at a bumped `schema_version`. A schema addition is documented for every adapter and is never an Antigravity branch. Outside the adapter, the detect and probe tables, tests and prose, `grep -rn -e antigravity -e '\bagy\b' tools/adlc --include='*.py'` finds nothing. `harness/copilot.yml`, `harness/cursor.yml` and `harness/codex.yml` are not edited, and `harness/claude.yml` is not edited.
- [ ] BR-6: **Permissions render narrowly, and Rule B holds.** The routine tier renders as `agy` permission rules at the narrowest scope the note shows is honoured. An entry that is a prefix of, or equal to, a deny-tier spelling is omitted and reported through REQ-657 BR-8's shared-base rule, computed rather than enumerated. No deny-tier entry is ever rendered as an allow, and no first-token fence entry is rendered. The deny tier renders as `deny` where the note shows a hard deny holds, as `ask` where only that holds, and otherwise is declared `deny-unsupported` and named in the README. If permissions cannot be committed to the repository, `committable_allowlist: no`, the project render writes no permission file, and the user-level rule set is printed or installed explicitly. Nothing in the toolkit passes `--dangerously-skip-permissions` or sets an auto-approve mode, and the README says a user's own use of them is outside the toolkit.
- [ ] BR-7: **A merge never loses the user's settings.** If the adapter writes into a settings file it does not own, it declares `write_mode: merge`, and this REQ carries the framework change that needs. REQ-657 shipped `merge_json` as a union over literal top-level keys, so this REQ amends it to replace-not-union over a stated candidate set and adds dotted owned keys. An owned key the render does not produce is an error, never a silent skip. A file that does not parse is a refusal naming the path, and nothing is written. No shipped adapter declares `write_mode: merge`, so this path is tested directly (LESSON-756). If no surface needs a merge, this rule is recorded as not applicable and the code stays as it is.
- [ ] BR-8: **ETHOS reaches the session, and the README says how far it was shown to.** The canonical hooks render or install through the route BR-4 chose, with events mapped through `hook_events`, timeouts converted through `hook_timeout_unit`, output through `hook_output`, and `--harness antigravity` passed to the session-record partial. The hook commands stay the canonical commands in `templates/hooks.yml`. If session-start hooks do not reach the model, the note records the alternative, such as an always-on rule, and the adapter uses it only if a recorded run shows ETHOS reached the model. `subagent_start_hook` stays `no` until a recorded run shows otherwise, so rendered agents carry the ETHOS read line (REQ-657 BR-4). If nothing reaches the model, the README says so.
- [ ] BR-9: **Agents reach `agy` in its own format.** Each canonical `agents/*.md` reaches `agy` through the chosen route, at user level unless the note shows otherwise, with tools through `tool_map` and the model through `tier_map`, where `unverified` omits `model`. An unmapped tool is an error naming the agent and the tool. If tools cannot be restricted, `agent_tool_restriction: none` and the framework's restraint sentence is rendered. A rendered file is derived, carries the REQ-516 BR-1 header, and is never written over a file without it. Claude Code's `~/.claude/agents` handling is untouched.
- [ ] BR-10: **Doctor stays data.** `render-currency:antigravity` is REQ-657's check. A row in `doctor_rows` is added only where the note shows doctor can read the fact. Every row SKIPs when `agy` is absent or nothing has been rendered for this harness, and a row's remediation is printed so it can be run verbatim. Doctor stays pure stdlib.
- [ ] BR-11: **The README states what is lost.** An "Antigravity CLI" section states how skills are invoked, what `agy` does not get from the toolkit, the deny tier's real form, whether permissions are committable, whether ETHOS reaches sessions and subagents, what prompts, what `--dangerously-skip-permissions` bypasses, and which rows the note left `unverified`. A test holds the section to the adapter: every `unsupported`, `inexpressible` or `widened` fact has its sentence, and the section claims no loss the adapter does not declare. The section also says the toolkit has no Gemini CLI adapter and why, and that `gemini-extension.json` does not exist (REQ-665 BR-14).
- [ ] BR-12: **Nothing that works today changes.** With no `antigravity` command used, every byte on disk, every Claude Code render and every partial is unchanged, and `adlc doctor` differs only by the new SKIP rows. `gemini` stays in the detect and probe tables as it is. Every path the adapter makes a harness read from the project is a default blocked path in `tools/adlc/lane_check.py`: `.gemini/**` already is, and `.agents/**` is added unless the note shows `agy` reads nothing there.
- [ ] BR-13: **Portability and tests.** New shell is POSIX sh, bash 3.2, zsh and dash safe. New Python is stdlib only where doctor or `adlc` run it. Every rendered surface has a committed golden under `harness/antigravity/rendered/`, held by `render-parity`. Tests use a throwaway `HOME` and `ADLC_HOME`, and a fake `agy` for detect, doctor and render paths.
- [ ] BR-14: **Documentation ships in the same change.** `README.md` (BR-11), `.adlc/context/architecture.md`, `tools/adlc/README.md`, `CHANGELOG.md` and the note of BR-1. REQ-662's spec records what its Antigravity exec block must read from the result file.
- [ ] BR-15: **Claims stay honest, and the dogfood is the operator's.** A capability is declared from a recorded run, never from docs alone, and whatever stays unverified is listed in the spec's `## Deferred` section. The dogfood gate, `/spec` → `/proceed` (lite) → `/wrapup` on one lite REQ in `atelier-fashion`, is run by the operator. Until it is recorded, the REQ may merge on the operator's decision, and its spec stays `in-progress`, as REQ-655's and REQ-656's do.

## Acceptance Criteria

- [ ] AC-1: `.adlc/research/antigravity-compatibility.md` carries every CompatibilityNote row, each naming how it was established, the `agy` version and the path or key observed, plus the route and its reason. No row reads `usable` from `docs` alone. The architecture cites the note, and its task list orders the BR-2 and BR-3 work and the note before any adapter task. (BR-1)
- [ ] AC-2: With a fake `agy` on a sandbox PATH, `adlc harness detect --json` lists `antigravity` as `present`, and without it as `absent`. `adlc doctor` shows `harness:antigravity` as report-only, and SKIP when absent. The `gemini` row is byte-identical to before. (BR-2, BR-12)
- [ ] AC-3: `adlc harness probe antigravity --dry-run` lists every launch and every user file it would edit, and launches nothing. `.adlc/research/harness-probes/antigravity.json` exists from a real run with `harness_version` set, and each probe reads a verdict or `n/a` with a reason. A grep of the result file and any fixture for the operator's email, login name and account ids finds nothing, and `cmp` shows each user file restored byte for byte. (BR-3)
- [ ] AC-4: The route is recorded per surface. If a plugin route is used, `agy plugin validate --strict` exits 0 on the clone and `manifest-parity` covers any new manifest. `/init --harness antigravity` never runs `agy plugin`, and `adlc harness install --harness antigravity` is what does, or it prints the step. `gemini-extension.json` is not added. (BR-4)
- [ ] AC-5: `harness/antigravity.yml` loads through the framework's loader with no Antigravity code path, and an added unknown key is refused naming the key. Removing `sandbox_can_reach_common_gitdir` is refused, and `unverified` is refused by `adlc harness doctor`. The BR-5 grep, excluding `harness.py`'s name table, `harness_probe.py`, `lane_check.py` and tests, finds nothing, and `git diff` shows `harness/claude.yml`, `harness/copilot.yml`, `harness/cursor.yml` and `harness/codex.yml` untouched. (BR-5)
- [ ] AC-6: The Antigravity render contains no deny-tier spelling as an allow and no first-token fence entry. Every routine entry that prefixes a deny spelling is omitted and keyed in `accepted_fidelity`, a fixture routine entry `rm` is omitted the same way, and removing one key fails `allowlist-fidelity` naming it. `grep -rn 'dangerously-skip-permissions' tools/adlc harness/antigravity.yml` finds only text that says never to use it. If `committable_allowlist: no`, a project render writes no permission file and the README row says so. (BR-6)
- [ ] AC-7: If a merge surface exists: on a sandbox settings file holding a user key and a user permission rule, a render keeps both, refreshes its owned keys inside their parent objects, removes a toolkit entry the render no longer emits, and a second run changes nothing. A file truncated to invalid JSON is refused naming the path, with nothing written, and an owned key the render does not produce is an error naming the key. If no merge surface exists, the architecture says so and `merge_json` is unchanged. (BR-7)
- [ ] AC-8: The canonical hooks reach `agy` through the chosen route, each with a timeout from `timeout_s`, and the session-record command carries `--harness antigravity`. A recorded run names whether ETHOS reached the model in a session and in a subagent, and `.adlc/.session/<id>` records `harness=antigravity` if the hook ran. `subagent_start_hook` is `no` unless that run shows otherwise. (BR-8)
- [ ] AC-9: On a sandbox `HOME`, every `agents/*.md` reaches `agy`'s agent location with mapped tools. Every file opens with the ETHOS read line while `subagent_start_hook: no`. A fixture agent with an unmapped tool exits non-zero naming the tool and writes nothing. A headerless file at a target path is refused, and `~/.claude/agents` and the `model:` lines in `agents/*.md` are unchanged. (BR-9)
- [ ] AC-10: `adlc doctor` lists `render-currency:antigravity`, and it and every `doctor_rows` row SKIP when `agy` is absent or nothing is rendered. A deleted rendered file FAILs naming it, and its remediation, run verbatim, returns it to PASS. Removing a `doctor_rows` entry removes its row with no code change. (BR-10)
- [ ] AC-11: `README.md` has an Antigravity CLI section carrying every BR-11 item, and the agreement test passes, failing when one loss sentence or one `unsupported` fact is removed. The section names `gemini-extension.json` as absent per REQ-665 BR-14. (BR-11)
- [ ] AC-12: With no `antigravity` command used, a checksum of `~/.claude/**`, `~/.agents/**`, `agents/*.md` and a consumer project's `.claude/settings.json` is unchanged, and with `agy` absent `adlc doctor` differs only by the new SKIP rows. A fixture diff touching a project-layer path reports `lane_check=escalate` with `trigger=blocked-path`, and `.agents/**` is in `DEFAULT_BLOCKED_PATHS` unless the note shows `agy` reads nothing there. (BR-12)
- [ ] AC-13: `sh partials/tests/run.sh` exits 0 under bash 3.2, zsh, `/bin/sh` and dash. `pytest tools/adlc/tests tools/lint-skills/tests` passes. `render-parity` passes against the committed goldens and fails when one golden changes by one byte. `sh tools/lint-skills/check.sh` is clean. (BR-13)
- [ ] AC-14: `README.md`, `.adlc/context/architecture.md`, `tools/adlc/README.md`, `CHANGELOG.md` and REQ-662's spec carry the new surfaces. (BR-14)
- [ ] AC-15: The spec's `## Deferred` section lists every row left `unverified` and every owed step. The dogfood run, once recorded, names the `agy` version, a session id or transcript path, the lite REQ and its merged PR, and whether ETHOS was injected. Until then the spec stays `in-progress`. (BR-15)

## External Dependencies

- REQ-657 (harness adapter framework), REQ-655 (schema 3, `sandbox_can_reach_common_gitdir` required from that version, `toml_merge.py`) and REQ-656 (`hook_output`, schema 2): this adapter builds on all three.
- REQ-664 (`adlc harness probe`): this REQ adds a profile to its catalogue. Its two open follow-ups apply here too: `ask-tier-deny`'s control can be refused by the model, and `trust-then-headless` cannot tell an unreviewed hook from an unread hook file.
- REQ-660 (`session-record`, `extract-chat --format`): `agy`'s transcripts are not a supported format. `/wrapup` falls back as it does for any unproven format.
- REQ-665 (`manifest-parity`): covers any manifest this REQ adds. **2026-10-30, REQ-665 BR-14:** `gemini-extension.json` does not exist, and with Gemini CLI out of scope this REQ adds no Gemini manifest and no `gemini:extension` or `gemini:dual-install` doctor row.
- REQ-662 (exec adapters): consumes this adapter; it was written against Gemini CLI and must re-derive its Antigravity exec block from `antigravity.json`.
- A real Antigravity CLI install, signed in: present on the operator's machine (`agy` 1.4.12 on 2026-10-31). Never required by a test. Probes and live runs use the operator's Antigravity quota.
- No new Python packages.

## Assumptions

- The Description's facts are as read from `agy` 1.4.12's help, changelog and embedded docs on 2026-10-31. None was tested, and BR-1 re-establishes each one.
- Gemini CLI is unavailable to individual accounts, on the operator's report. Search results suggest paid API keys and Vertex AI still work with the `gemini` binary. That case is out of scope here, and a later REQ can add it.
- The harness name is `antigravity` and the binary `agy`. `gemini` stays in the tables, so the detect output keeps its existing row.
- The directory stays `REQ-658-gemini-cli-adapter`, because REQ-665's verification and `test_req658_names_the_absent_manifest` read that path.
- REQ-657's framework can express `agy`'s surfaces with schema additions. If a surface needs more, the architecture says so before any code.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] Does the plugin route deliver skills, agents, rules and hooks, and does `agy plugin import claude` work on a symlink install, or only on a Claude Code plugin install? BR-1's note answers this and BR-4 follows it.
- [ ] Can permissions be committed to the repository at all, or only at `~/.gemini/config/projects/`? This decides `committable_allowlist` and whether a project render writes any permission file.
- [ ] Does `permission.deny` hold, and does it hold under a matching allow, interactively and headless? This decides `deny_tier_render`.
- [ ] Does `SessionStart` output reach the model, in what form, and in `-p` runs as well as interactive ones? If not, is an always-on rule enough? This decides `hook_output` and BR-8's route.
- [ ] Does `agy` read `~/.agents/skills`, or only `.agents/skills/` and `~/.gemini/config/skills/`? This decides the `mount` value and whether REQ-654's mount helps.
- [ ] What is the granularity of a `command(…)` rule: token prefix, exact, or something else? This decides `allowlist_granularity`.
- [ ] What is `agy`'s trust model for a workspace, and does a linked worktree start untrusted, as Codex's hooks do (LESSON-765)?
- [ ] Which model ids fill `tier_map`? Until confirmed, each is `unverified` and `model` is omitted.
- [x] ~~Which of Gemini CLI and Antigravity CLI does the adapter target?~~ Resolved 2026-10-31: Antigravity CLI alone, because Gemini CLI is no longer available to individuals.

## Out of Scope

- A Gemini CLI adapter, `harness/gemini.yml`, `.gemini/settings.json` renders and `~/.gemini/policies/` files. The earlier draft is in git history.
- A Gemini extension or `gemini-extension.json`: REQ-665 BR-14 removed Gemini from the manifest set.
- `agy`'s desktop app, its Remote Control, and its MCP surfaces.
- Transcript parsing for `agy` (`extract-chat --format antigravity`): REQ-660 can add it once its format is proven.
- The exec engine and its adapters (REQ-659, REQ-662), including the `exec` block's keys.
- The framework beyond the schema additions this adapter needs and the merge change of BR-7.
- Any change to `SKILL.md` body text or to Claude Code's install, renders or agents.
- Running the `atelier-fashion` dogfood from a pipeline run.
- Windows.

## Retrieved Context

- LESSON-751 (lesson): Re-measure a spec's figures at Phase 1
- LESSON-756 (lesson): A framework proven on one adapter has only proven that adapter's branches
- LESSON-757 (lesson): A rendered config can pass every gate and do nothing
- LESSON-765 (lesson): A hook can be well-formed and still never run; read the harness's hook inventory first
- LESSON-766 (lesson): Ask a harness's own inspection commands before spending model sessions
- LESSON-619 (lesson): A harness that executes lines extracted from markdown is an execution surface
- LESSON-663 (lesson): Allowlist what a model may run; forbidding commands one at a time never converges
- LESSON-716 (lesson): A validator for a format another reader consumes must parse the way that reader does
- REQ-655 (spec): Codex CLI harness adapter
- REQ-656 (spec): Copilot CLI and Cursor harness adapters
- REQ-664 (spec): Harness capability probes
