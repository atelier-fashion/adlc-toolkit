---
id: REQ-657
title: "Harness adapter framework — shipping the `claude` adapter only"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/toolkit"
domain: "adlc"
stack: ["python", "yaml", "sh", "markdown", "json"]
concerns: ["portability", "harness-agnostic", "developer-experience", "security", "configurability", "structural-enforcement"]
tags: ["harness", "multi-harness", "adapter", "agents", "render", "permissions", "allowlist", "hooks", "ethos", "init", "template-drift", "agents-md", "claude-md", "lint", "ci", "doctor", "install", "render-parity", "tier", "settings"]
lane: "full"
lane_reason: "changes the permissions and hooks surface (allowlists, deny tier, ETHOS injection) and the toolkit's lint gates, and the footprint spans tools/adlc, templates, init and template-drift skills, agents render and lint — far above max_files"
lane_forced: false
---

## Description

This is Phase 2a of `.adlc/research/multi-harness-plan.md` (revision 2): the
**harness adapter framework** — `harness/<name>.yml` adapters and their
loader, `adlc harness install | render | doctor`, per-harness agent,
allowlist and hook rendering with the `allowlist-fidelity` lint,
`/init --harness`, and `AGENTS.md` as the canonical instruction file — the
layer every non-Claude harness adapter (Copilot CLI, Cursor, Codex, Gemini
CLI) will plug into. It builds directly on REQ-654 (P0: `ADLC_HOME`, the
`~/.agents/skills` skills-only view, `adlc harness detect`, the
`harness:<name>` doctor checks) and does not repeat any of it. The two design
rules the adversary pass forced on the plan carry through unchanged: **Rule A
— nothing that works today moves** (Claude Code's mounts, counters, config and
the in-place `model:` stamp stay exactly as they are), and **Rule B — a
one-way move is never delegated to an unattended model** (an allowlist is a
convenience for the routine tier; the deny tier names the one-way moves, is
rendered on an interactive harness into whatever makes a human confirm in
session, and only ever removes capability, never grants it).

Today three things the toolkit depends on have **no cross-harness standard and
no single source**: agent definitions (`agents/*.md`, Claude's format),
command allowlists (`templates/claude-settings-template.json`, a static copy
of Claude's `permissions` block with 57 `allow` and 16 `ask` prefixes), and
hooks (none shipped; ETHOS reaches a session only through each skill's `!`
macro, which no other harness has and which a plain Claude subagent dispatch
does not run either). Each of these would otherwise be hand-ported per harness
and drift apart (the LESSON-005/LESSON-019 shape). This REQ makes each one a
**semantic canonical source rendered per harness through a declarative
adapter**, and proves the framework on the only harness in use today by making
the `claude` adapter reproduce the current behaviour byte-for-byte where a file
already exists.

Nine deliverables:

1. **Adapter schema and loader.** `harness/<name>.yml` declares, per harness:
   its `schema_version`, the binary, the user-level and project-level paths each surface is written
   to (with each surface's `mode` and `write_mode`), the file format of each
   surface, the canonical-tool → harness-tool name map, the alias → model-id
   `tier_map`, the `accepted_fidelity` map, the `deny_tier_render` mechanism,
   the opaque `exec` block (consumed by REQ-659/REQ-662, declared here), the
   trust mechanism, the `hook_events` and `hook_payload` maps, the optional
   `doctor_rows`, and a capability block (deny syntax, `subagent_start_hook`, `compact_rehook`, per-agent tool
   restriction, allowlist granularity, committable allowlist). A stdlib-only
   loader validates an adapter against that schema and fails loud on anything
   it cannot parse (LESSON-716 posture).
2. **`adlc harness install | render | doctor`.** Three data-driven `adlc`
   subcommands (REQ-519 BR-11): `install` writes a harness's **user-level**
   surfaces, `render` writes any surface for any adapter (and `--check`
   reports parity instead of writing), `doctor` runs the harness-scoped checks.
3. **`adlc agents render --harness <name>`** extends REQ-516's renderer: the
   canonical `agents/*.md` are rendered through the adapter's tool-name map
   and `tier_map` into the harness's user-level agents directory, and the tier
   config (`agents.classes`) gains a per-harness column so a harness whose
   model names differ resolves its own aliases. On `claude` it keeps doing
   exactly what it does today: stamp `model:` in place.
4. **`templates/permissions.yml`**, a semantic allowlist: the routine tier
   (`git.read`, `git.write`, `gh.read`, `gh.pr.create`, test runners, shell
   utilities) plus a **deny tier** naming the one-way moves (`gh.merge`,
   `deploy`, `terraform`, `git push --force`, `rm -rf`, …). It replaces
   `templates/claude-settings-template.json` as the source `/init` renders
   from; the first `claude` render reproduces today's `allow` set and renders
   the deny tier as today's `ask` set (`deny_tier_render: {project: confirm}`).
5. **`allowlist-fidelity`**, a lint that renders `permissions.yml` through
   every shipped adapter and reports, per entry and per harness, what that
   harness cannot express (fence matching, `git -C`, granularity collapse,
   deny-tier support) — the three honest limits in plan §2e, made structural
   instead of a README promise (LESSON-012).
6. **`templates/hooks.yml`**, the canonical hook set: `ethos-inject` on
   session start (re-fired after compaction where the harness distinguishes
   it) and on subagent start where the harness has that event, and
   `session-record`, whose command names the partial REQ-660 ships and whose
   sidecar contract REQ-660 owns. Rendered per harness into the file that
   harness reads.
7. **`/init --harness <name>[,<name>…]`** writes each named harness's project
   layer (default: `claude` only; a non-Claude harness's project layer is
   written only when named explicitly, never because `adlc harness detect`
   found its binary) by rendering, not by copying a static template, and registers
   `harness-config` as a `/template-drift` sync surface in both
   `<!-- sync-surfaces -->` blocks so the `sync-surface-parity` lint keeps
   them aligned.
8. **`AGENTS.md` canonicalisation.** `AGENTS.md` becomes the project
   instruction file every harness reads; `CLAUDE.md` is reduced to its
   Claude-specific lines plus an `@AGENTS.md` import, never silently rewritten.
9. **`render-parity --check`** as a toolkit lint check backed by
   `adlc harness render --check`, so a committed render can never drift from
   what the renderer would write (REQ-516 BR-5 pattern).

Ships with the `claude` adapter **only**. The Copilot and Cursor adapters are
a sibling REQ (REQ-656, P2b); Codex (REQ-655, P3) and Gemini (REQ-658, P4)
follow. The dogfood for this REQ is therefore Claude Code with zero behaviour
change, which is what makes every later adapter a data file, golden fixtures
and, for a new file format, one format renderer; never a branch on the harness
name.

### Vocabulary this REQ fixes for its siblings

Every sibling spec (REQ-655, 656, 658, 659, 660, 661, 662, 663, 664, 665, 666)
uses these spellings and meanings; where a sibling differs, this REQ wins.

- **Tiers:** `templates/permissions.yml` has exactly two tiers, `routine` and
  `deny`; "the deny tier" is the name for the one-way moves. There is no "ask
  tier" anywhere in the file or in sibling prose (BR-6).
- **`deny_tier_render`:** per adapter, a per-scope map: scope (`project` /
  `user`) → `confirm` (the harness's human-confirm list — Claude `ask`) /
  `deny` (a hard deny in the harness's own syntax) / `unsupported`; a scope
  absent from the map is `unsupported`; the `claude` adapter declares
  `{project: confirm}`. The `exec` scope's deny rendering is REQ-662's
  `exec.deny_render`, keyed on `capabilities.deny: yes` and independent of
  this map. A committed render never widens a deny-tier entry into an allow
  (BR-6).
- **Fence scope rule:** the permissions render takes a scope. At `project`
  (committed) scope and in every `printed` render (a printed per-harness line
  such as REQ-656's Copilot line included — printed follows the committed-scope
  rules, so it carries no broad fence entry) `fence.partial-source` is never a
  first-token entry (`if`, `sh`, `bash`, `zsh` — that is a wildcard allow) and
  never a broad spelling; it is rendered only as an opening-token prefix that
  includes the partial path literal, else omitted and reported `inexpressible`
  with the user-level remedy printed (advisory text for the operator, itself
  bound by these rules). A written `user`-scope surface carries the deny tier
  only (scope rule below), so the fence is never written there. The single
  exception is `exec` scope: `fence.partial-source` there emits the adapter's
  `capabilities.fence_broad_spelling`, reported `widened`, because the gate at
  exec is REQ-659's structural halt, not the allowlist; `fence_broad_spelling`
  is never a bare `if` / `sh` / `bash` / `zsh` token (BR-8). On `claude` at
  `project` scope the entry is declared `inexpressible` in `accepted_fidelity`
  and omitted — a committed opening-token prefix would be a new pre-approval,
  withheld by Rule A (BR-7).
- **Scope rule:** the shared-base rule and the fence rules apply to every
  render at every scope (`project`, `printed`, written `user`, `exec`). A
  written `user`-scope surface renders the deny tier only; the routine tier is
  never written at user scope, and any user-level allow is a `printed`
  advisory under the committed-scope rules (BR-8).
- **Shared-base rule:** applies to every render at every scope. A routine
  allow entry is omitted, and reported `inexpressible` in `accepted_fidelity`,
  whenever the adapter's matcher (BR-9) says it is a proper prefix of, or can
  wrap, a deny-tier spelling. The wrappers evaluated are the closed set
  `git -C . <rest>`, `NAME=1 <C>` and `bash -lc '<C>'`; every other wrapper is
  a declared residual (below), not evaluated. An entry is restored only when
  `capabilities.deny_under_allow[<shape>]` is a `pass` that is valid for the
  scope being rendered: its `mechanism` is the one `deny_tier_render` declares
  at that scope, it covers the allow/deny scope pairing actually rendered, its
  `harness_version` is the one in use, and its `source` verifies (a `probe`
  value equals REQ-664's recorded result; `grandfathered` is `claude`'s
  `prefix` only; BR-8, BR-9). An adapter may declare
  `capabilities.never_restore` for a shape, and then the entry is never
  restored whatever `deny_under_allow` says (REQ-655 drops `["git","-C"]`
  unconditionally). `capabilities.git_c_spelling` is therefore emitted only
  where no deny-tier spelling shares its prefix; for a prefix-matching harness
  whose `git -C` spelling is a bare prefix, it is never emitted at committed or
  printed scope (BR-8, BR-9).
- **`PermissionEntry.match` and the file header:** `match` is `prefix`
  (default) or `exact`; an `exact` entry renders as the command with no
  prefix wildcard where the format can express that (`claude`: `Bash(pwd)`,
  not `Bash(pwd:*)`), and as a prefix match at `exec` scope regardless of
  `match`. `templates/permissions.yml` also carries top-level `default_mode`
  and `comment`. `comment` is spelled by the adapter's format (`claude`:
  `_comment`); `default_mode` is rendered only through the adapter's explicit
  `default_mode_map` (`claude`: `permissions.defaultMode`), and an adapter with
  no mapping omits it and reports it `inexpressible` — the lint treats
  `default_mode` as a routine entry (BR-6, BR-7, BR-9).
- **`accepted_fidelity`:** adapter map keyed by `(entry, command)` — a
  PermissionEntry id (every command of that entry) or `"<id>:<argv prefix
  joined by single spaces>"` (one command; the narrower key wins), since an
  omission is per argv prefix and an entry's commands can differ — to the
  `widened:<spelling>` / `inexpressible` / `deny-unsupported` /
  `residual:exact-deny` verdict the `allowlist-fidelity` lint accepts for that
  harness; absent means nothing is accepted; there is no `narrowed` verdict. It
  is per scope: a bare verdict applies at `project`; a `{project, user, exec}`
  map of verdicts is also allowed, and an absent scope key accepts nothing at
  that scope. `allowlist-fidelity` gates `project`; REQ-662's pre-flight
  compares at `exec` (BR-9).
- **`tier_map`:** adapter map, alias (`opus` / `sonnet` / `haiku`) → harness
  model id or `unverified`; `claude`'s is identity; `unverified` or a missing
  entry omits `model:` (BR-5).
- **`agent_tool_restriction`:** `enforced` writes the mapped `tools:` list;
  `readonly-only` writes the harness's read-only marker for an agent whose
  canonical `tools:` omits Edit and Write; `none` writes no list and one
  restraint sentence. An agent with no `tools:` line has all tools (the two
  such agents are `task-implementer` and `pipeline-runner`); no agent uses
  `*`; a tool mapped `unsupported` is dropped and never by itself produces a
  restraint line (BR-4).
- **CLI spelling:** `adlc harness install | render | doctor --harness <name>`;
  `adlc agents render --harness <name>`; `/init --harness <name>[,<name>…]`
  (default: `claude` only — a non-Claude project layer is written only when
  named explicitly, never because detect found its binary). Every `adlc
  harness` subcommand and `adlc agents render` accept `--adapter-path
  <file>`, the only way a non-detect adapter name loads; `install --all` and
  `/init` do not accept it. `adlc harness render` accepts `--surface` and
  `--scope project|user|exec` (defaults: `project` for render, `user` for
  install, `exec` never a default; a `printed` surface renders at user scope
  under the committed-scope rules of BR-8) (BR-2, BR-3, BR-4, BR-11).
- **Doctor check names:** `harness:<name>` (REQ-654, report-only) and
  `render-currency:<name>` (this REQ, one framework check); a sibling
  adapter's agent check is an instance of `render-currency:<name>`, never new
  check code (BR-15).
- **Hooks:** canonical events are `session-start`, `session-compact`,
  `subagent-start`; every adapter carries a `hook_events` map in which every
  canonical event appears, mapped to the harness's own event name or
  `unsupported`; every HookEntry carries `timeout_s`, and the renderer
  converts it through the adapter's `hook_timeout_unit` (`s` / `ms`, default
  `s`); every adapter carries a `hook_payload` map naming its payload fields
  for the session id, cwd and transcript path. The `claude` hooks render is
  the one Copilot and Cursor read as-is, so it passes no harness argument;
  an adapter that renders its own hook file passes `--harness <name>`
  (BR-10).
- **Trust enum:** `trust` is a struct `{mechanism, detail}`; `mechanism` is
  `none` / `flag` / `user-config-entry` / `trusted-folders-file` and is
  canonical for every sibling; `detail` is the mechanism's free-text
  specifics (flag name, config key, file path). The working-copy enum
  (`worktree` / `clone` / `orchestrator-git`) is REQ-659's, not this REQ's
  (System Model).
- **`exec`:** an opaque, schema-versioned sub-block whose keys REQ-659
  (engine) and REQ-662 (adapters) own; this REQ validates map-or-absent only
  (System Model). Engine-only denies (the orchestrator's approve sub-command)
  live under `exec` and never in `templates/permissions.yml` (BR-6).
- **`schema_version`:** the adapter's top-level integer; the loader accepts
  only versions it knows. A bump adds optional fields; a field required of
  every adapter is added to `claude.yml` and its goldens by the bumping REQ
  (BR-1, Assumptions).
- **`sandbox_can_reach_common_gitdir`:** top-level adapter enum `true` /
  `false` / `unverified`; optional until REQ-655 adds it (REQ-655 adds the
  `true` line to `harness/claude.yml`; it is the value REQ-659 reads);
  `worktree` working copies require exactly `true` (BR-1).
- **`doctor_rows`:** optional adapter list of data-driven doctor rows, each
  `{id, kind, target, remediation}` with `kind` one of `path-exists` /
  `marker-present` / `equals-render`; a sibling adds doctor rows as data,
  never as a per-harness branch in framework check code (BR-15).
- **`formats` and scope:** a surface's format names a renderer; the `exec`
  scope of the permissions surface yields structured entries the engine
  spells into argv (REQ-659 BR-8), and a `printed` surface renders at `user`
  scope under the committed-scope rules (shared-base and fence rules apply;
  BR-8, BR-11).
- **Surface `mode` and `write_mode`:** per surface, `mode` is `rendered` /
  `via:<harness>` / `printed` / `mounted` / `unsupported`, where `mounted`
  means served by REQ-654's install — path declared, nothing rendered — and
  the `skills` surface of every shipped adapter declares it; `write_mode` is
  `create` (default; preserve-unless-`--force`) or `merge` (the top-level
  keys the adapter lists as toolkit-owned in that surface's `owned_keys`
  are added or refreshed, list-valued owned keys are unioned, every other
  key preserved; JSON only in this REQ) (BR-11).
- **`session-record` ownership split:** this REQ owns the `hooks.yml` entry
  and every render of it; REQ-660 owns the partial, the sidecar's fields,
  line format, mode 600, write conditions, pruning, the gitignore line and
  its lint (BR-10).

### Declared residuals every adapter's README states

Allowlist and prefix-deny matching cannot be made a gate, and this REQ does not
pretend it can. Every adapter's README and `tools/lint-skills/README.md` state
the following residuals (BR-18); `allowlist-fidelity` closes spellings, not
this list:

- Allowlist matching is spelling-level. The lint evaluates a closed set of
  spellings (BR-9); a deny-tier command reached in any other spelling is not
  seen.
- Allows that execute their arguments (`find -exec`, `awk`, `sed e`, `npx`,
  `npm run` / `npm exec`, `git rebase --exec`, `git fetch --upload-pack`) and
  `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents of a deny-tier command (`git restore`, `git checkout
  -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are
  outside the deny tier.
- This is the same exposure Claude's template has today (Rule A grandfathers
  it); no adapter makes it worse, and none claims to close it.
- The allowlist is never the gate (Rule B). The orchestrator's structural gates
  (REQ-659) are.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| HarnessAdapter | name | string | file `harness/<name>.yml`; `name` equals the basename; one of the five names `adlc harness detect` knows (REQ-654 BR-7) for any adapter under `harness/`; a test-only adapter is loaded only from an explicit fixture path passed as `--adapter-path <file>`, which `install --all`, `/init --harness` and the shipped lints never accept or scan |
| HarnessAdapter | schema_version | integer | required; the loader accepts only versions it knows |
| HarnessAdapter | binary | string | the executable `adlc harness detect` probes for this harness; `adlc harness detect` (REQ-654) stays authoritative and the loader cross-checks the adapter's `binary` against detect's table, failing loud on disagreement; the cross-check applies only to adapters whose `name` is one of the five detect names — a fixture-path adapter with another name skips it (BR-1) |
| HarnessAdapter | paths | map | per surface (`agents`, `permissions`, `hooks`, `instructions`, `skills`): a `user` path (under `$HOME`, expressed with `$ADLC_HOME`/`$HOME`, never a literal home) and/or a `project` path (repo-relative); a surface whose `mode` is `unsupported` or `via:<harness>` declares no path |
| HarnessAdapter | paths.\<surface\>.mode | enum | `rendered` (this adapter writes the file) / `via:<harness>` (the named harness's render serves it — Cursor and Copilot read `.claude/settings.json` hooks) / `printed` (no file; the remedy is printed for the user to apply) / `mounted` (served by REQ-654's install; path declared, nothing rendered; the `skills` surface of every shipped adapter declares it) / `unsupported` |
| HarnessAdapter | paths.\<surface\>.write_mode | enum | `create` (default) or `merge`; only a JSON surface may declare `merge` in this REQ (TOML merge needs a parser and is the Codex adapter's to add with its schema bump); semantics in BR-11 |
| HarnessAdapter | paths.\<surface\>.owned_keys | list | required when `write_mode` is `merge`: the top-level keys the toolkit owns in that surface; list-valued owned keys are unioned on merge, every other key is preserved (BR-11) |
| HarnessAdapter | formats | map | per surface: the file format the harness reads (`claude-agent-md`, `claude-settings-json`, …); every format named must have a renderer registered, or the loader fails; the `exec` scope of the permissions surface yields structured entries the engine spells into argv (REQ-659 BR-8), and a `printed` surface renders at `user` scope under the committed-scope rules of BR-8 |
| HarnessAdapter | tool_map | map | canonical tool name (`Read`, `Grep`, `Glob`, `Bash`, `Write`, `Edit`, `Agent`, …) → harness tool name, or `unsupported`; every tool used by any `agents/*.md` `tools:` line must appear |
| HarnessAdapter | tier_map | map | alias (`opus` / `sonnet` / `haiku`) → harness model id, or `unverified`; `claude`'s is identity |
| HarnessAdapter | accepted_fidelity | map | keyed by `(entry, command)`: a PermissionEntry id (every command of the entry) or `"<id>:<argv prefix joined by single spaces>"` (one command; the narrower key wins) → the verdict (`widened:<spelling>` / `inexpressible` / `deny-unsupported` / `residual:exact-deny`) the `allowlist-fidelity` lint accepts for this harness, or a `{project, user, exec}` map of such verdicts; a bare verdict applies at `project`; an absent scope key accepts nothing at that scope; an absent key accepts nothing; there is no `narrowed` verdict. `allowlist-fidelity` gates `project`; REQ-662's pre-flight compares at `exec` |
| HarnessAdapter | deny_tier_render | map | scope (`project` / `user`) → `confirm` (the harness's human-confirm list — Claude `ask`) / `deny` (a hard deny in the harness's own syntax) / `unsupported`; the `claude` adapter declares `{project: confirm}`; a scope absent from the map is `unsupported`; the `exec` scope's deny rendering is REQ-662's `exec.deny_render`, keyed on `capabilities.deny: yes` and independent of this map |
| HarnessAdapter | default_mode_map | map | optional; `{key: <the harness's settings key>, values: {<canonical default_mode value>: <harness value>}}` (`claude`: key `permissions.defaultMode`, `acceptEdits` → `acceptEdits`). `default_mode` is rendered only through this map; absent mapping omits it and reports it `inexpressible` (id `default_mode`, treated as a routine entry by the lint; BR-6, BR-9) |
| HarnessAdapter | hook_events |
| HarnessAdapter | hook_timeout_unit | enum | `s` / `ms`, default `s`; the unit of the harness's per-hook timeout field; the renderer converts each HookEntry's `timeout_s` into it (BR-10) |
| HarnessAdapter | hook_payload | map | per canonical payload item (`session_id`, `cwd`, `transcript_path`): the harness's own payload field name, or `unsupported`; the renderer spells each hook command's argument lookup from it |
| HarnessAdapter | exec | map | an opaque, schema-versioned sub-block whose keys REQ-659 (engine) and REQ-662 (adapters) own; this REQ validates only that it is a map or absent, and nothing in this REQ reads a key of it or executes anything |
| HarnessAdapter | trust | struct | `{mechanism, detail}`: `mechanism` is `none` / `flag` / `user-config-entry` / `trusted-folders-file`; `detail` is the mechanism's specifics (flag name, config key or file path); declared, not exercised. The `mechanism` enum is canonical for every sibling; the working-copy enum (`worktree` / `clone` / `orchestrator-git`) is REQ-659's and is not an adapter field here |
| HarnessAdapter | sandbox_can_reach_common_gitdir | enum | `true` / `false` / `unverified`; top-level; optional until REQ-655 adds it (REQ-655 adds the `true` line to `harness/claude.yml`, the value REQ-659 reads); `worktree` working copies require exactly `true` |
| HarnessAdapter | capabilities | struct | `deny` (yes/no), `subagent_start_hook` (yes/no), `compact_rehook` (yes/no), `agent_tool_restriction` (`enforced` / `readonly-only` / `none`; semantics in BR-4), `allowlist_granularity` (`subcommand` / `token-prefix` / `prefix` / `command-base`; the matcher each value fixes is BR-9's; `fence-prefix` is not a granularity, the fence being `fence.partial-source` under BR-8's scope rules; `claude` declares `prefix`), `committable_allowlist` (yes/no), `git_c_spelling` (list of extra argv prefixes, each a token list, the renderer emits alongside the plain `git` spelling only where no deny-tier spelling shares its prefix; for a prefix-matching harness whose `git -C` spelling is a bare prefix it is never emitted at committed or printed scope — shared-base rule, BR-8), `never_restore` (optional list, each item a spelling shape or an argv-prefix token list: the shared-base rule never restores a matching omitted entry whatever `deny_under_allow` says), `deny_under_allow` (map, spelling shape `prefix` / `git-c` / `env-prefix` / `shell-opener` → record `{mechanism, result, harness_version, source}`: `mechanism` is `confirm` or `deny`, `result` is `pass` or `unverified`, `source` is `probe` or `grandfathered`; an absent shape is `unverified`; a `pass` counts only for the mechanism `deny_tier_render` declares at the scope being rendered and for the scope pairing actually rendered, otherwise it is treated as `unverified`; a `source: probe` record must equal REQ-664's result-file entry (`sub_results` for the specific variant) at the same `harness_version`, else the lint fails; `git-c` is sourced from REQ-664's `wrapped-allow`, `prefix` from `deny-under-allow`, and `env-prefix` and `shell-opener` have no producer and stay `unverified`; `claude` declares `prefix: {mechanism: confirm, result: pass, harness_version: n/a, source: grandfathered}`, Rule A's grandfathering of the precedence today's template already relies on — an `ask` of `git push --force` under an allow of `git push:*` — not a probe result; `grandfathered` is accepted only for that record; BR-8, BR-9) |
| HarnessAdapter | capabilities.fence_broad_spelling | token list | the broad spelling emitted for `fence.partial-source` at `exec` scope only, reported `widened` (BR-8); never a bare `if` / `sh` / `bash` / `zsh` token; required when `allowlist_granularity` is not `command-base`. `claude` declares `[if, "[", -f, .adlc/partials/]` (the opening-token prefix through the partial path literal) |
| HarnessAdapter | doctor_rows | list | optional; each `{id, kind: path-exists\|marker-present\|equals-render, target, remediation}`; evaluated by the framework doctor as data, never by a per-harness branch (BR-15) |
| PermissionEntry | id | string | dotted semantic id, e.g. `git.read`, `gh.pr.create`, `fence.partial-source`; unique in `templates/permissions.yml` |
| PermissionEntry | tier | enum | `routine` / `deny`; no third tier — there is no ask tier in the file (Rule B); on an interactive harness the deny tier renders through `deny_tier_render` |
| PermissionEntry | commands | list | argv prefixes (token lists), never shell text; the renderer spells each per harness |
| PermissionEntry | match | enum | `prefix` (default) / `exact`; `exact` renders the command with no prefix wildcard where the format can (`claude`: `Bash(git config user.email)`, `Bash(npm ci)`, `Bash(pwd)`, `Bash(git push --force)`, `Bash(git push -f)`), is compared by equality only if the adapter's format renders it exact (a format that collapses it to a prefix is evaluated with the adapter's granularity matcher; BR-9), and is rendered as a prefix match at `exec` scope regardless of `match` |
| PermissionEntry | note | string | why the entry exists; carried into rendered output where the format allows comments |
| PermissionsFile | default_mode | string | top-level key of `templates/permissions.yml`; the harness's default permission mode, rendered only through the adapter's `default_mode_map` (`claude`: `permissions.defaultMode`, `acceptEdits`); absent mapping: omitted and reported `inexpressible` |
| PermissionsFile | comment | string | top-level key; carried into rendered output where the format allows comments (`claude`: `_comment`) |
| HookEntry | id | enum | `ethos-inject`, `session-record` |
| HookEntry | events | list | canonical event names (`session-start`, `session-compact`, `subagent-start`); the adapter maps each to its own event name or marks it `unsupported` |
| HookEntry | command | string | a partial-backed command resolved through the two-level fallback; `ethos-inject` emits the project `.adlc/ETHOS.md` and is a silent no-op when the project has none; `session-record` names the partial REQ-660 ships (BR-10) |
| HookEntry | timeout_s | integer | seconds, required; rendered into the harness's per-hook timeout field where one exists, converted through the adapter's `hook_timeout_unit` (`s` → as-is, `ms` → ×1000), else reported `unsupported` |
| TierConfig | `agents.classes.<class>` | alias | unchanged default column (REQ-516) |
| TierConfig | `agents.harness.<name>.classes.<class>` | alias or model id | per-harness column; absent column → the default column; `claude` column present or absent resolves identically to today; the resolved alias feeds the adapter's `tier_map` (BR-5) |
| RenderedSurface | (harness, surface, scope) | tuple | scope `user`, `project` or `exec` (the last only for the permissions surface, consumed by REQ-659); the output path comes from the adapter, the content from the renderer; written atomically (temp + rename), idempotent (second run: zero changes) |
| FidelityFinding | (harness, entry, command, verdict) | tuple | verdict `exact` / `widened:<spelling>` / `inexpressible` / `deny-unsupported` / `residual:exact-deny`; no `narrowed` verdict exists; emitted by `allowlist-fidelity`, keyed by `(entry, command)` because omission is per argv prefix. For a routine entry `exact` means every argv prefix rendered as the harness's prefix match of the same tokens; for a deny-tier entry `exact` means rendered into the mechanism `deny_tier_render` declares for that scope, so `claude`'s project-scope `ask` render is `exact`; `deny-unsupported` is emitted for every deny-tier entry the render at that scope does not carry; `residual:exact-deny` is emitted when a deny entry is `match: exact` and a rendered routine allow matches its extension (BR-9) |
| ParityResult | (harness, surface, path) | tuple | `in-parity` / `drifted` (with a unified diff) / `missing-golden`; emitted by `render-parity --check` |
| DriftSurface | name | enum | existing five plus `harness-config`; posture: template-posture (`synced` / `stale` / `customized` / `missing`), with every deny-tier rule absent from the project copy named explicitly regardless of classification (the REQ-525 BR-1 "missing principle" rule applied to allowlists) |
| InstructionFile | AGENTS.md | file | canonical project instruction file; written by `/init`; harness-neutral content only |
| InstructionFile | CLAUDE.md | file | Claude-specific lines plus `@AGENTS.md`; never reduced without the operator seeing the removed lines |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| adapter_loaded | any `adlc harness` subcommand, `adlc agents render --harness`, `/init --harness`, the lints | adapter name, schema version, validation verdict (loud failure names the field) |
| surface_rendered | `adlc harness render`, `adlc harness install`, `/init --harness` | harness, surface, scope, path, `written` / `unchanged` / `would-write` (dry-run) |
| fidelity_reported | `allowlist-fidelity` lint, `adlc harness render --surface permissions` | one FidelityFinding per (harness, entry); summary count per verdict per harness |
| parity_checked | `render-parity --check`, `adlc harness render --check` | one ParityResult per (harness, surface); non-zero exit on any `drifted` or `missing-golden` |
| harness_config_drift | `/template-drift` | per harness: per rendered file, classification plus the named list of missing deny-tier rules |
| instruction_file_written | `/init --harness` | `AGENTS.md` created/unchanged; `CLAUDE.md` created / reduced-with-approval / left-untouched-with-notice |

_Permissions: not applicable — single-user machine tooling and project files. Section omitted deliberately._

## Business Rules

- [ ] BR-1: **Adapter schema, one loader, fail-loud.** Every harness adapter is a data file `harness/<name>.yml` validated by one loader against a schema that names every field in the HarnessAdapter entity; doctor and `adlc harness` load adapters without the venv (LESSON-395), so the loader has no third-party dependency. The schema names, besides the fields already listed, the top-level integer `schema_version` (required; the loader accepts only versions it knows), the `hook_events` map (every canonical event present, mapped to the harness's event name or `unsupported`), `capabilities.fence_broad_spelling` (a token list; required when `allowlist_granularity` is not `command-base`), the optional top-level `sandbox_can_reach_common_gitdir` (`true` / `false` / `unverified`; optional until REQ-655 adds it), `capabilities.deny_under_allow` (the per-shape record `{mechanism, result, harness_version, source}`, BR-8), `capabilities.never_restore` (BR-8), `default_mode_map` (BR-6), per-scope `accepted_fidelity` keyed by `(entry, command)` (BR-9), the optional `doctor_rows` list (BR-15), `hook_timeout_unit` (BR-10), per-surface `owned_keys` (BR-11), and the `mounted` surface mode (served by REQ-654's install; path declared, nothing rendered; the `skills` surface of every shipped adapter declares it). The loader rejects, naming the field: an unknown key, a missing required key, a `schema_version` it does not know, a format with no registered renderer, a tool-map that omits a tool some `agents/*.md` uses, a literal home-directory path in `paths`, a `binary` that disagrees with `adlc harness detect`'s table, an `exec` value that is neither a map nor absent, a `hook_events` map missing a canonical event, an `allowlist_granularity` outside `subcommand` / `token-prefix` / `prefix` / `command-base` (`fence-prefix` is not one), a `deny_under_allow` record missing a field or with a value outside its enum, a `source: grandfathered` record anywhere but `claude`'s `prefix` shape, a `fence_broad_spelling` that is a bare `if` / `sh` / `bash` / `zsh` token, and a duplicate or alternatively spelled key its reader would resolve differently (LESSON-716: model the reader). The `binary` cross-check applies only to adapters whose `name` is one of the five detect names; a fixture-path adapter with another name skips it. `harness/claude.yml` declares `allowlist_granularity: prefix` (`Bash(<prefix>:*)` matches the command text by word-boundary prefix), `fence_broad_spelling: [if, "[", -f, .adlc/partials/]` (consumed at `exec` scope only, BR-8), `deny_tier_render: {project: confirm}`, a `default_mode_map` for `permissions.defaultMode`, `deny_under_allow: {prefix: {mechanism: confirm, result: pass, harness_version: n/a, source: grandfathered}}`, and an `accepted_fidelity` that declares `fence.partial-source` as `{project: inexpressible, exec: widened:<fence_broad_spelling>}` plus the `residual:exact-deny` findings BR-9 names. The YAML subset the adapter files may use is whatever the loader parses — the schema doc states it, and a file outside it is a loud error, never a silently ignored key. Every `adlc harness` subcommand, `adlc agents render --harness`, `/init --harness` and both new lints go through this one loader. Adapters under `harness/` carry one of the five detect names; a test-only adapter is loaded only from an explicit fixture path passed as `--adapter-path <file>` (accepted by every `adlc harness` subcommand and by `adlc agents render`, and the only way a non-detect adapter name loads), which `install --all`, `/init --harness` (neither accepts the flag) and the shipped lints never scan. (informed by LESSON-716, LESSON-395, REQ-520)
- [ ] BR-2: **Data-driven subcommands, read-only where they say so.** `adlc harness install`, `render` and `doctor` are added to the `adlc` `SUBCOMMANDS` table (REQ-519 BR-11) and resolve the project root from the caller's cwd and toolkit assets from the script location, never one for the other (LESSON-397). Every `adlc harness` subcommand and `adlc agents render` accept `--adapter-path <file>` (BR-1). `adlc harness render` accepts `--surface <agents|permissions|hooks|instructions>` and `--scope project|user|exec`: the default scope is `project` for `render` and `user` for `install` (always user scope, BR-3); `exec` is never a default and applies to the permissions surface only; a `printed` surface renders at user scope under the committed-scope rules of BR-8. `render --check`, `doctor`, and every lint are strictly read-only. `install` and `render` without `--check` write only the paths the adapter declares for the requested scope, atomically, and are idempotent: a second run on an unchanged tree reports zero actions (REQ-519 BR-1). `--dry-run` prints the plan and writes nothing. (informed by REQ-519, LESSON-397, LESSON-006)
- [ ] BR-3: **`install` is user-scope only and honest about no-ops.** `adlc harness install --harness <name>` writes exactly that harness's user-level surfaces (its rendered agents directory, its user-level deny-tier entries where the adapter declares a `permissions.user` path (the routine tier is never written at user scope, BR-8) — Copilot declares none, its user-level hooks where that is where hooks live) and nothing project-level. For `claude`, whose user-level agents are already the `~/.claude/agents` symlink (REQ-654 BR-6) and whose hooks and allowlist travel in the project layer, `install` reports that there is nothing to write and exits 0 — it never creates a parallel copy of the agents under `$ADLC_HOME` (Rule A). `--all` iterates the harnesses `adlc harness detect` reports present. (informed by REQ-654)
- [ ] BR-4: **Agent rendering through the tool map, user-level only.** `adlc agents render --harness <name>` renders every canonical `agents/*.md` into the adapter's user-level agents path in the adapter's declared format, mapping each `tools:` entry through `tool_map`; the mapped `tools:` list is deduplicated (two canonical tools that map to one harness tool yield one entry), and canonical tool names in the agent body are rewritten through `tool_map` too. `agent_tool_restriction` drives the rendered restriction: `enforced` — the mapped `tools:` list is written; `readonly-only` — an agent whose canonical `tools:` omits Edit and Write is rendered with the harness's read-only marker and no list; `none` — no list is written, and such an agent gets one restraint sentence (identical in every file) as its first body line (after the ETHOS prepend when one is rendered). A tool mapped `unsupported` is dropped from the list and never by itself produces a restraint line. An agent with no `tools:` line has all tools and renders no list and no restraint; no agent uses `*`. For every harness rendered to a copy (never the in-place `claude` stamp), each rendered body opens with the instruction to read `.adlc/ETHOS.md` first (plan §2d) unless the adapter declares `subagent_start_hook: yes`, in which case no prepend is rendered because the hook carries ETHOS. Project-level agent files are never written by this command (plan §2b M7). With `--harness claude` (and with no `--harness`), the command is byte-for-byte today's in-place `model:` stamp on the canonical files: no copy, no body change, no new file — REQ-516 BR-3/BR-4 hold unchanged. (informed by REQ-516, LESSON-441)
- [ ] BR-5: **Tier config gains a per-harness column, default column unchanged.** The flat config reader accepts `agents.harness.<name>.classes.<class>` and `agents.harness.<name>.overrides.<agent>` alongside the existing `agents.classes` / `agents.overrides`. Resolution for harness H: H's override > H's class > default override > default class > shipped per-agent default. Validation of every column follows REQ-516 BR-7 (known aliases plus the documented full-model-id escape hatch; unknown class key rejected); an unknown sub-key under `agents.*` — anything other than `classes`, `overrides`, `harness.<name>.classes` and `harness.<name>.overrides` — is rejected naming the key, never silently ignored; the `agent-model-drift` lint and `check_drift` keep sharing the resolution code path with render (REQ-516 BR-5). A config with no `harness:` block resolves every agent to exactly what it resolves to today. A resolved value that is an alias is mapped through the adapter's `tier_map` before rendering; `unverified` or a missing entry omits `model:` and says so once on stderr; `inherit` omits it; a full model id from the escape hatch is written as-is. On `claude` the mapping is identity, so today's stamp is unchanged. (informed by REQ-516)
- [ ] BR-6: **`templates/permissions.yml` is semantic and two-tiered.** Each entry carries a dotted id, a tier, argv-prefix command lists, a note and a `match` (`prefix` default / `exact`); the file carries top-level `default_mode` (today's `acceptEdits`) and `comment` (today's `_comment`), of which `default_mode` is rendered only through the adapter's explicit `default_mode_map` (absent mapping: omitted and reported `inexpressible`; the lint treats it as a routine entry, id `default_mode`) and `comment` is spelled by the format (`claude`: `permissions.defaultMode` via the map, and `_comment`). The routine tier holds exactly what today's template pre-approves, plus the entries REQ-666 adds to the template before this REQ lands (`cat`, `grep`, `gcloud` for the run-and-read context blocks), plus `fence.partial-source` (BR-8); the deny tier holds exactly what today's template puts on `ask` (the one-way moves) and nothing else. Engine-only denies (the orchestrator's approve sub-command) live under `exec` (REQ-659) and never in `templates/permissions.yml`. Each adapter declares `deny_tier_render` as a per-scope map, scope (`project` / `user`) → `confirm` (the harness's human-confirm list — Claude `ask`), `deny` (a hard deny in the harness's own syntax), or `unsupported`; a scope absent from the map is `unsupported`; the `claude` adapter declares `{project: confirm}`; the `exec` scope's deny rendering is REQ-662's `exec.deny_render`, keyed on `capabilities.deny: yes` and independent of this map; a committed render never widens a deny-tier entry into an allow. At `exec` scope a deny-tier spelling is rendered as a hard deny whenever `capabilities.deny` is `yes` and the syntax can express it without matching a routine entry that stays rendered, otherwise `deny-unsupported`. The exec deny set is the deny tier plus `exec.engine_deny`. `deny_render: none` is permitted only with a `fail` ask-tier-deny verdict (REQ-662 BR-11). Deny-tier entries render as prefix matches at exec scope regardless of `match`. There is no ask tier in `templates/permissions.yml`: the tiers are `routine` and `deny`, and "the deny tier" is the name every sibling spec uses. Entries are commands, never shell text; the renderer, not the author, spells fences and `git -C` per harness (BR-8). `templates/claude-settings-template.json` is deleted in the same change and every reference to it (`init/SKILL.md`, docs, lint fixtures) is moved to the render path; a lint fixture that still carries the old path must fail (REQ-610 BR-6 precedent). (informed by REQ-610, LESSON-019, LESSON-663)
- [ ] BR-7: **The `claude` permissions render is byte-equivalent to today.** Rendering `permissions.yml` through the `claude` adapter yields a `.claude/settings.json` whose `permissions.defaultMode`, `permissions.allow` set and `permissions.ask` set are equal, as sets, to the deleted template's (as it stands after REQ-666's additions), the comparison made after rendering `match: exact` entries (`Bash(git config user.email)`, `Bash(git config user.name)`, `Bash(npm ci)`, `Bash(pwd)` and the exact `ask` entries render without the `:*` wildcard) and `default_mode` / `comment` rendered from `permissions.yml`, `fence.partial-source` excepted: on `claude` at `project` scope that entry is declared `inexpressible` in `accepted_fidelity` (a committed opening-token prefix would be a new pre-approval, withheld by Rule A) and omitted; at `exec` scope the entry is `capabilities.fence_broad_spelling`, reported `widened`, and nothing is written for it at user scope (BR-8). The equality holds only because `claude` declares `deny_under_allow.prefix` as `pass` (grandfathered, BR-8): the `git push:*` and `git branch:*` allows wrap exact-or-prefix deny spellings, and with `prefix` set to `unverified` the shared-base rule omits them and the pinned set fails. The `_comment` key is reproduced; the only addition is the `hooks` block from BR-10. A consumer whose `.claude/settings.json` came from the old template therefore reports in `/template-drift` as `stale` **only** for the missing `hooks` block, and that is said in the CHANGELOG as the expected re-sync (REQ-610 BR-10 precedent). No existing consumer gains or loses a pre-approved command. (informed by REQ-610, LESSON-441)
- [ ] BR-8: **Honest allowlist limits, rendered narrowly and reported.** Each adapter's `allowlist_granularity` and `git_c_spelling` drive the renderer: where a harness needs both `git` and `git -C` spellings it emits both, subject to the shared-base rule below; where granularity collapses (command-base, token-prefix, subcommand) it emits the narrowest expressible rule. **Scope rule:** the shared-base rule and the fence rules below apply to every render at every scope: `project`, `printed`, written `user` and `exec`. A written `user`-scope surface renders the deny tier only; the routine tier is never written at user scope, and any user-level allow is a `printed` advisory under the committed-scope rules. **Shared-base rule (framework-level, every adapter, every scope):** a routine allow entry is omitted from a render, and reported `inexpressible` in `accepted_fidelity` (keyed by `(entry, command)`), whenever BR-9's matcher says it is a proper prefix of, or can wrap, a deny-tier spelling. The wrappers are the closed set of BR-9 (`git -C . <rest>`, `NAME=1 <C>`, `bash -lc '<C>'`); other wrappers are declared residuals. An entry is restored only when `capabilities.deny_under_allow[<shape>]` is a valid `pass`: `result: pass`; `mechanism` equal to the mechanism `deny_tier_render` declares at the scope being rendered (a `confirm` pass does not carry to a `deny` render or to `exec` scope); the allow/deny scope pairing actually rendered is the one the record covers; `harness_version` equal to the version in use; and `source` verified by BR-9 (`probe` must equal REQ-664's result file at that version; `grandfathered` exists only for `claude`'s `prefix`, Rule A's grandfathering of the ask-over-allow precedence BR-7's pinned set already relies on, not a probe result). Anything else is `unverified`. `capabilities.never_restore` names a shape or an argv prefix the rule never restores whatever `deny_under_allow` says, so an adapter can declare an unconditional omission (REQ-655: `["git","-C"]`). `git_c_spelling` is therefore emitted only where no deny-tier spelling shares its prefix; for a prefix-matching harness whose `git -C` spelling is a bare prefix, it is never emitted at committed or printed scope. **Fence:** the partial-sourcing fence (`if [ -f .adlc/partials/…`) is a first-class routine entry (`fence.partial-source`). At `project` (committed) scope and in every `printed` render, including a printed per-harness line (REQ-656's Copilot line carries no broad fence entry), `fence.partial-source` is never rendered as a first-token entry (`if`, `sh`, `bash`, `zsh`) or a broad spelling, because that is a wildcard allow; it is rendered only as an opening-token prefix that includes the partial path literal, else omitted and reported `inexpressible` with the user-level remedy printed (advisory text for the operator; it never contains a `sh:*`-style broad entry). A written `user`-scope surface never carries it (scope rule). The single exception is `exec` scope: there the entry is the adapter's `capabilities.fence_broad_spelling`, reported `widened`, because the gate at exec is REQ-659's structural halt, not the allowlist; `fence_broad_spelling` is never a bare `if` / `sh` / `bash` / `zsh` token. The `exec` scope yields structured entries the engine spells into argv (REQ-659 BR-8). **Exact deny entries:** a `match: exact` deny entry protects only its own spelling; its extension is reported by BR-9 as `residual:exact-deny`. Widening is always reported (BR-9), never silent. (informed by LESSON-663, LESSON-619)
- [ ] BR-9: **`allowlist-fidelity` lint.** A `tools/lint-skills` check renders `permissions.yml` at `project` scope through every adapter it is given and emits one FidelityFinding per (harness, entry, command). The lint function takes an explicit adapter-path list and an explicit REQ-664 result-file path; the shipped check passes `harness/*.yml` and the recorded result file, tests pass fixture paths. **Matcher:** `allow_matches(A, C)` is fixed per granularity. `command-base`: A is one token and equals the first token of C after stripping leading `NAME=value` tokens (a harness that does not strip is conservatively treated as stripping). `token-prefix` and `subcommand`: A is a token-list prefix of C; `subcommand` also caps rendered A at two tokens, a render-side collapse reported `widened`. `prefix`: A is a character prefix of C at a word boundary. An entry whose `match` is `exact` is compared by equality only if the adapter's format renders it exact; where the format collapses it to a prefix, the rendered form is evaluated with the adapter's granularity matcher. The wrapped forms are a closed set: `git -C . <rest>` (for a C whose first token is `git`), `NAME=1 <C>` and `bash -lc '<C>'`, evaluated literally by the same matcher. Other wrappers (`find -exec`, `xargs`, `npx`, `npm run`, `gh api`) are declared residuals, not evaluated. Each match is classified by shape: plain → `prefix`, `git -C` → `git-c`, assignment → `env-prefix`, shell opener → `shell-opener`. **Failures:** the lint fails when a rendered allow matches a deny-tier command in a shape whose `capabilities.deny_under_allow` record is not a valid `pass` (BR-8), whatever `accepted_fidelity` says (an accepted `inexpressible` is an omission, not a rendered allow); it fails when a `source: probe` record differs from REQ-664's result-file entry (`sub_results` for the specific variant) at the same `harness_version`, or is absent from it; it fails when a `source: grandfathered` record is anywhere but `claude`'s `prefix`; and it fails any rendered `fence.partial-source` that is a first-token wildcard (BR-8). **Exact deny entries:** for each deny-tier command the lint also evaluates `<command> <sample-arg>` (a fixed sample tail, `origin feature`); where the deny entry is `match: exact` and a rendered routine allow matches the extension, it reports `residual:exact-deny` and requires it in `accepted_fidelity` (this grandfathers `claude`'s `git push --force origin feature` exposure, Rule A). **`default_mode`** is evaluated as a routine entry: rendered through `default_mode_map`, else `inexpressible`. The verdicts are `exact`, `widened:<spelling>`, `inexpressible`, `deny-unsupported` and `residual:exact-deny`; there is no `narrowed` verdict. It fails on any `widened`, `inexpressible` or `residual:exact-deny` verdict not listed, at `project` scope, in that adapter's declared `accepted_fidelity` map under `(entry, command)` (a bare verdict applies at `project`; an absent scope key accepts nothing at that scope), so the Cursor all-git-or-nothing collapse is a declared, visible acceptance, not a surprise. `exact` for a deny-tier entry means rendered into the mechanism `deny_tier_render` declares for that scope, so `claude`'s project-scope `ask` render is `exact`. `deny-unsupported` is emitted for every deny-tier entry the render at that scope does not carry, whatever `capabilities.deny` says; it fails unless listed in `accepted_fidelity`. It passes on `claude` with every routine and deny entry `exact` except `fence.partial-source`, declared `inexpressible` at `project` scope in `harness/claude.yml` `accepted_fidelity` (BR-7), and the grandfathered `residual:exact-deny` findings declared there. The report ends with the declared-residuals notice (BR-18). It is distinct from `sync-surface-parity`, which stays unchanged. (informed by LESSON-012, LESSON-440)
- [ ] BR-10: **Hooks: one canonical set, rendered per harness, structural ETHOS.** `templates/hooks.yml` carries `ethos-inject` (events `session-start`, `session-compact`, `subagent-start`) and `session-record` (`session-start`); every entry carries `timeout_s`. Each adapter maps every canonical event to its own name or `unsupported` in `hook_events`, declares `hook_timeout_unit` (`s` / `ms`, default `s`) so the renderer converts `timeout_s` into the harness's per-hook timeout field, and names its payload fields in `hook_payload`; the renderer emits only supported events and reports the rest. For the `claude` render, which Copilot and Cursor read as-is, the renderer passes no harness argument; the partial REQ-660 ships detects the harness from the payload with a table embedded in the partial; an adapter that renders its own hook file passes `--harness <name>`. The `claude` render emits a `hooks` block in `.claude/settings.json` with `SessionStart` (including the `compact` matcher) carrying both hooks, and `SubagentStart` only if the adapter declares it (Open Question 1). Hook commands resolve their partial through the canonical two-level guarded spelling (REQ-610 BR-3), add no third spelling, and the hook commands are never loaded by `lane_check.py` (LESSON-718); the `ethos-inject` command exits 0 with no output when the project has no `.adlc/ETHOS.md`. `session-record`'s `command` names the partial REQ-660 ships, resolved through the REQ-610 BR-3 spelling; the sidecar's fields, line format, mode 600, write conditions, pruning, the gitignore line and its lint are REQ-660 BR-5–BR-7 and are not restated here. Until REQ-660 lands the entry resolves to a stub partial that writes `.adlc/.session/<id>` with `harness=` and `session_id=` only, which REQ-660 replaces under the same name. The existing `!` ETHOS macro in every SKILL.md stays — the hook is additive (plan §2c M6). (informed by REQ-610, LESSON-718, REQ-525)
- [ ] BR-11: **`/init --harness` renders the project layer and registers the drift surface.** `/init --harness <names>` (default: `claude` only; a non-Claude harness's project layer is written only when named explicitly, never because `adlc harness detect` found its binary — REQ-656 BR-14) renders, per named harness, every surface the adapter declares at project scope with `mode: rendered`, through `adlc harness render`, never by `cp` of a static file; a `printed` surface has its remedy printed (rendered at `user` scope under the committed-scope rules of BR-8), a `via:<harness>` surface is served by the named harness's render, a `mounted` surface is served by REQ-654's install and nothing is rendered. Under `write_mode: create` (the default) existing files are preserved unless `--force` (REQ-519 BR-1 idempotence, today's `/init` posture); under `write_mode: merge` the merge granularity is the top-level keys declared toolkit-owned in the adapter (the surface's `owned_keys` list): those keys are added or refreshed, list-valued owned keys are unioned with what the file already holds, and every other key is preserved, so a project's own entries survive a re-render; `merge` is JSON only in this REQ — TOML merge needs a parser and is the Codex adapter's to add with its schema bump. `harness-config` is added to the `<!-- sync-surfaces: init -->` and `<!-- sync-surfaces: template-drift -->` blocks in the same change, so `sync-surface-parity` enforces the pair (REQ-525 BR-4). `/template-drift`'s `harness-config` step re-renders from canonical through the adapter and compares with template posture (projects may legitimately add commands), always naming any deny-tier rule the project copy lacks, and respecting the Step 0a baseline rules (BUG-204, BUG-203). (informed by REQ-525, BUG-204, BUG-203)
- [ ] BR-12: **AGENTS.md canonical, CLAUDE.md reduced with consent.** `/init` writes `AGENTS.md` as the project instruction file (harness-neutral: the ADLC workflow pointer, the skill list, the project-context pointers `/init` Step 10 today suggests adding to `CLAUDE.md`). When no `CLAUDE.md` exists it writes one containing `@AGENTS.md` plus the Claude-specific lines (today's settings/permissions note). When a `CLAUDE.md` exists, `/init` never deletes or moves a line from it unattended: in an interactive session it shows the proposed `AGENTS.md` and the lines it would leave in `CLAUDE.md` and waits for approval; in non-interactive mode it writes `AGENTS.md`, prepends `@AGENTS.md` to `CLAUDE.md` only if absent, and prints the manual reduction as the follow-up. The toolkit's own repo gets the same treatment at dogfood time: `AGENTS.md` is written at the clone root, which is harmless because harnesses read `AGENTS.md` from the project cwd, not from a skills mount. The user-level `~/.claude/CLAUDE.md` routing block (REQ-426) is untouched. (informed by REQ-426, LESSON-572)
- [ ] BR-13: **`render-parity --check` in toolkit CI, one code path.** `adlc harness render --check` renders every adapter's every surface to memory and compares against (a) the committed golden renders under `harness/<name>/rendered/` next to each adapter (for `claude`: `harness/claude/rendered/settings.json`, the file REQ-655 BR-13 and REQ-666 BR-15 point at in place of the deleted template) and (b) in-tree committed renders (the canonical agents' `model:` lines; the toolkit's own `.claude/settings.json`), exiting non-zero with a unified diff on any mismatch. A `tools/lint-skills` check `render-parity` calls that same function (REQ-516 BR-5 / LESSON-006: drift and render share one path). "Toolkit CI" here means the gates `/proceed` runs on this repo — `bash tools/lint-skills/check.sh`, `pytest tools/adlc/tests tools/lint-skills/tests`, `sh partials/tests/run.sh` — since the toolkit has no hosted workflow; a consumer repo is covered by `/template-drift`, not by parity. (informed by REQ-516, LESSON-006)
- [ ] BR-14: **A lite PR cannot widen an allowlist or soften a hook.** `lane_check.py`'s `DEFAULT_BLOCKED_PATHS` gains `harness/**`, `templates/permissions.yml`, `templates/hooks.yml` and `.claude/settings*.json`, so any change to the permission or hook sources, to an adapter, or to a committed golden render escalates a lite-lane REQ to the full lane (`.claude/**` already matches `.claude/settings*.json` today, so the fourth entry is explicit, not new coverage). `.cursor/**`, `.codex/**`, `.gemini/**`, `.github/**` and `.adlc/partials/**` are already in the defaults today and are pinned by `test_lane_check.py`; the remaining P1 additions (`.github/agents/**`, `.github/hooks/**`, `.adlc/agents/**`) are REQ-666's; this REQ adds only the four paths it creates. `**/AGENTS.md` and `**/CLAUDE.md` are already in the defaults, so BR-12's writes to either file escalate a lite REQ to the full lane in consumers without any addition here. (informed by LESSON-718, REQ-652)
- [ ] BR-15: **Doctor.** `adlc harness doctor [--harness <name>]` runs, for each installed harness (REQ-654's `harness:<name>` probe says present), the adapter validation (BR-1), the mount check REQ-654 already provides, and `render-currency:<name>`: the user-level rendered surfaces for that harness match a fresh render (FAIL with remediation `adlc harness render --harness <name>` or `adlc agents render --harness <name>`, copy-pasteable, REQ-519 BR-5). `harness:<name>` itself stays report-only (REQ-654's posture); `render-currency:<name>` is one framework check driven by adapter data, and a sibling adapter's agent or config check is an instance of it, never new check code. Adapter REQs may add doctor rows of three data-driven kinds — `path-exists`, `marker-present`, `equals-render` — declared in the adapter under `doctor_rows` as `{id, kind, target, remediation}`; the framework evaluates them from the data and holds no per-harness branch in check code. An absent binary SKIPs, never FAILs (REQ-654 BR-9). The same checks are reachable through `adlc doctor --checks harness:<name>,render-currency:<name>`; the two must not hold separate check code. (informed by REQ-519, REQ-654, LESSON-572)
- [ ] BR-16: **Shell and Python discipline.** New Python is stdlib only; new or changed shell (hook commands, `/init` fences, partial changes) is POSIX-sh, bash 3.2, zsh and dash safe and is executed under each by `partials/tests/run.sh`: no `case` inside `$( )`, no `\b` in `grep -E`, no bare `$<digit>`, no `local`, no `[[`, no reliance on `set -e` across a fence, decimal normalization before arithmetic; every partial-sourcing line uses the single REQ-610 BR-3 spelling and nothing else, and the `unguarded-source` walk gains `templates/hooks.yml` and the committed `claude` render. (informed by REQ-610, LESSON-582, LESSON-395, LESSON-013, LESSON-335)
- [ ] BR-17: **Documentation moves with the code.** `README.md` (install model: per-harness install and what each harness cannot express, plan §4 table reduced to the shipped adapter plus the framework's promise), `.adlc/context/architecture.md` (adapter layer, the two-tier permissions model and Rule B, the hook set), `conventions.md` (an adapter is data; a new harness is a data file, golden fixtures and, for a new file format, one format renderer; never a branch on the harness name), `tools/adlc/README.md` (subcommands, checks), `tools/lint-skills/README.md` (two new checks), `init/SKILL.md`, `template-drift/SKILL.md`, `CHANGELOG.md` (with the BR-7 re-sync note). (informed by LESSON-019)
- [ ] BR-18: **Declared residuals are stated, and the allowlist is never the gate.** The section "Declared residuals every adapter's README states" (Description) is carried, in the same words, in `tools/lint-skills/README.md`, `tools/adlc/README.md` and the README of every shipped adapter, and the `allowlist-fidelity` report ends with it. No README, skill text or lint message describes the allowlist, `deny_tier_render` or `allowlist-fidelity` as preventing a deny-tier command from running unattended; the structural gates are REQ-659's (Rule B). (informed by LESSON-619, LESSON-012)

## Acceptance Criteria

- [ ] AC-1: `harness/claude.yml` loads; a copy with an unknown key, a `schema_version` the loader does not know, a `hook_events` map missing `session-compact`, a missing `tool_map` entry for a tool some `agents/*.md` uses, a `paths.agents.user` spelled with a literal `/Users/…`, a `binary` that disagrees with `adlc harness detect`'s table, an `exec` that is a scalar, and a duplicated `binary:` key each fail the loader with a message naming the field, and no `adlc harness` subcommand proceeds past that failure. A fixture adapter at a path outside `harness/` loads only when that path is passed as `--adapter-path <file>`; `adlc harness install --all` and `/init --harness` neither accept the flag nor list it. (BR-1)
- [ ] AC-2: `adlc harness render --harness claude --dry-run` in a sandbox project prints the plan and `git status` is unchanged; without `--dry-run` it writes `.claude/settings.json`; a second run reports zero actions and the file is byte-identical. `adlc harness install --harness claude` on a healthy REQ-654 install writes nothing under `$ADLC_HOME`, says so, and exits 0. (BR-2, BR-3)
- [ ] AC-3: `adlc agents render` and `adlc agents render --harness claude` on a fresh checkout leave `git diff -- agents/` empty; `pytest tools/adlc/tests/test_agents_render.py` passes unchanged. With a test-only fixture adapter `fake` (loaded with `--adapter-path <fixture>`; tool map `Read→read_file`, `Grep→grep`, `Glob→glob`, `Bash→unsupported`, `subagent_start_hook: no`, `agent_tool_restriction: enforced`), `adlc agents render --harness fake --adapter-path <fixture>` with `HOME`/`ADLC_HOME` pointed at a sandbox (`--root` keeps its meaning of toolkit root) writes one file per canonical agent under the fake user-level path and no file under the sandbox project; the `fake` fixture's name is not a detect name, so the `binary` cross-check is skipped: the 17 agents with a `tools:` line carry the mapped list with `Bash` dropped and no restraint line, every body opens with the ETHOS-first line, and `task-implementer` and `pipeline-runner` carry no list. With the fixture's `agent_tool_restriction` changed to `none`, the 17 carry no list and one restraint sentence (byte-identical across the 17) as the line after the ETHOS line, and the two without `tools:` carry none; with `readonly-only`, the 17 (all of whose canonical `tools:` omit Edit and Write) carry the fixture's read-only marker and no list. With the fixture's `subagent_start_hook` changed to `yes`, no ETHOS line is prepended. (BR-4)
- [ ] AC-4: The `fake` fixture (loaded with `--adapter-path <fixture>`, as in AC-3) declares `tier_map: {opus: fake-large-1, sonnet: fake-mid-1, haiku: unverified}`. A config with `agents.harness.fake.classes.scanner: sonnet` and no `agents.classes` renders the fake harness's scanner agents with `model: fake-mid-1`, its explorer agents (shipped default `haiku`) with no `model:` line and one stderr notice naming `haiku` as `unverified`, and the default (`claude`) render unchanged; a full model id `fake-x-9` in the fake column is written as-is; `agents.harness.fake.classes.bogus: x` fails naming the class; `adlc agents render --check` and the `agent-model-drift` lint agree with render on both columns. (BR-5)
- [ ] AC-5: `templates/claude-settings-template.json` no longer exists; `grep -rn claude-settings-template` over the distribution surface (`*/SKILL.md`, `agents/`, `partials/`, `tools/`, `templates/`, `README.md`) returns nothing; a lint fixture carrying the old `cp ~/.claude/skills/templates/claude-settings-template.json` line fails. (BR-6)
- [ ] AC-6: The `claude` render of `permissions.yml`, loaded with `json`, has `defaultMode`, and `allow` / `ask` **sets** equal to those of the template as it stood at `origin/main` before this REQ — after REQ-666's additions, which are part of the pinned baseline — `fence.partial-source` excepted (compared by a pytest that pins the old sets as a fixture, the comparison made after rendering `match: exact` entries, with `default_mode` and `comment` rendered from `permissions.yml`): on `claude` at `project` scope that entry is declared `inexpressible` in `accepted_fidelity` and omitted, and the test asserts no fence-shaped entry is present; the render reproduces the `_comment` key; the only top-level difference is the `hooks` key. In a sandbox consumer initialised from the old template, `/template-drift` reports `harness-config` as `stale` naming only the missing `hooks` block and no deny-tier rule as missing. (BR-7, BR-11)
- [ ] AC-7: `bash tools/lint-skills/check.sh` runs `allowlist-fidelity` and is clean on the shipped tree; the report lists every (claude, entry, command) as `exact` — the deny-tier entries included, since `claude` declares `deny_tier_render: {project: confirm}` — except `fence.partial-source`, whose `claude` verdict is `inexpressible` at `project` scope (declared in `harness/claude.yml` `accepted_fidelity`) and `widened:<fence_broad_spelling>` at `exec` scope, and except the `residual:exact-deny` findings (for example the `git push` allow against `git push --force origin feature`) declared in the same map. `claude` with `capabilities.deny_under_allow.prefix` set to `unverified` omits `git push:*` and `git branch:*` (reported `inexpressible`) and fails BR-7's pinned set (AC-6). Against the fixture `fake` adapter (loaded with `--adapter-path`) with `allowlist_granularity: command-base`, `deny_tier_render: {project: unsupported}` and no `accepted_fidelity`, the check fails naming each `widened` routine entry and each deny-tier entry as `deny-unsupported`, each failing because `accepted_fidelity` is absent; in the same run the `git` and `gh` routine entries (whose command base wraps `git push --force` and `gh pr merge`) are omitted and reported `inexpressible`, not rendered as a bare `git` / `gh` allow (shared-base vector, command-base). A second fixture adapter `fake-prefix` (prefix-matching, `allowlist_granularity: prefix`, `deny_tier_render: {project: confirm}`, `git_c_spelling: [[git, -C]]`, `capabilities.deny_under_allow` empty) has its `git -C` entry omitted from the project-scope render and reported `inexpressible` (shared-base vector, prefix-matching), and `git_c_spelling` is not emitted at project scope; setting `capabilities.deny_under_allow: {git-c: {mechanism: confirm, result: pass, harness_version: <v>, source: probe}}` with a matching entry in the fixture result file passed to the lint restores the entry, which is then reported `exact` and needs no `accepted_fidelity` listing; the same record with `mechanism: deny`, a different `harness_version`, or a result-file entry that differs or is absent leaves it omitted or fails the lint, and `never_restore: [git-c]` omits it whatever the record says. A hand-written fixture render that does contain an allow `git -C` (or an env-prefixed or `bash -lc` allow wrapping a deny-tier spelling) makes the lint fail naming the deny-tier command it matches and the shape (`git -C . push --force`, plain and wrapped forms both evaluated, each classified `prefix` / `git-c` / `env-prefix` / `shell-opener`). A fixture whose rendered `fence.partial-source` is a first-token wildcard (`if`, `sh`, `bash` or `zsh`) fails the lint, and the renderer's output for the same fixture is either an opening-token prefix containing the partial path literal or an omission reported `inexpressible` with the user-level remedy printed (first-token-wildcard vector). `accepted_fidelity` given as a bare verdict gates `project` only; a `{project, user, exec}` map accepts per scope, and an absent scope key accepts nothing at that scope. No finding carries a `narrowed` verdict. The committed `claude` render at `project` scope contains no `Bash(sh:*)`-style entry (grep-verified), and the same entry rendered at `exec` scope is the adapter's `capabilities.fence_broad_spelling` and is reported `widened`. (BR-8, BR-9)
- [ ] AC-8: The `claude` render's `hooks` block carries `SessionStart` with the `compact` matcher for `ethos-inject` and `session-record`, each with a `timeout` taken from the entry's `timeout_s` (the `claude` adapter's `hook_timeout_unit` is `s`, so the value is written as-is; the `fake` fixture with `hook_timeout_unit: ms`, rendered with `adlc harness render --harness fake --adapter-path <fixture> --surface hooks`, renders `timeout_s: 10` as `10000`); in a sandbox project that creates `.adlc/ETHOS.md` with known content, running the rendered `ethos-inject` command under `/bin/sh`, bash and zsh prints that content; with the file absent it prints nothing and exits 0; the rendered `session-record` entry's command resolves through the two-level spelling and, with the partial absent at both levels, exits 0 silently. (BR-10)
- [ ] AC-9: `/init --harness claude` in a fresh sandbox repo creates `.claude/settings.json` (rendered, equal to AC-6's), `AGENTS.md`, and a `CLAUDE.md` containing `@AGENTS.md`; re-running leaves every file byte-identical. `/init` with no `--harness` does the same (default `claude` only) on a machine where detect finds only `claude` and on one where detect also finds a non-Claude binary: no non-Claude project file is written unless that harness is named. Both `<!-- sync-surfaces -->` blocks list `harness-config`, and `pytest tools/lint-skills/tests/test_sync_surface_parity.py` passes; removing it from one block fails that test. A fixture adapter whose permissions surface declares `write_mode: merge` with `owned_keys: [permissions, hooks]`, rendered with `adlc harness render --harness <fixture-name> --adapter-path <fixture> --surface permissions` (`/init` accepts no `--adapter-path`) over a settings file carrying a project-added top-level key and a project-added entry in the `permissions.allow` list, leaves the project key in place, refreshes the owned keys and keeps the project's list entry (list-valued owned keys are unioned). (BR-11)
- [ ] AC-10: In a sandbox repo with an existing 40-line `CLAUDE.md`, `/init --harness claude` in non-interactive mode writes `AGENTS.md`, prepends exactly one `@AGENTS.md` line to `CLAUDE.md`, changes nothing else in it, and prints the reduction as a follow-up; `diff` against the original shows only the one added line. (BR-12)
- [ ] AC-11: `adlc harness render --check` exits 0 on the shipped tree; after editing `harness/claude/rendered/settings.json`, or hand-editing `model:` in one agent, or editing the toolkit's own `.claude/settings.json` allow list, it exits non-zero with a unified diff naming the file, and the `render-parity` lint reports the same finding in the same run of `check.sh`; re-rendering clears both. (BR-13)
- [ ] AC-12: `pytest tools/adlc/tests/test_lane_check.py` gains cases: a diff touching `harness/claude.yml`, `harness/claude/rendered/settings.json`, `templates/permissions.yml`, `templates/hooks.yml` or `.claude/settings.json` reports `blocked-path`; the four paths above are added by this REQ's diff and `DEFAULT_BLOCKED_PATHS` gains no other path from it; `.cursor/**`, `.codex/**`, `.gemini/**` and `.github/**` are present already and the test pins them as present regardless of this REQ. (BR-14)
- [ ] AC-13: `adlc harness doctor` on a healthy machine PASSes `harness:claude` and `render-currency:claude`; with the canonical agents' `model:` hand-edited it FAILs `render-currency:claude` with a remediation that, run verbatim, returns it to PASS; `adlc doctor --checks harness:claude,render-currency:claude` prints the same results; on a sandbox PATH with no harness binary every harness check SKIPs. The `fake` fixture (run as `adlc harness doctor --harness fake --adapter-path <fixture>`) declaring one `doctor_rows` entry of each kind (`path-exists`, `marker-present`, `equals-render`) PASSes each when its target holds and FAILs it with the declared remediation when it does not, and `grep -rn 'fake' tools/adlc/*.py` returns nothing — the rows are evaluated from adapter data. (BR-15)
- [ ] AC-14: `sh partials/tests/run.sh` exits 0 under bash 3.2, zsh, `/bin/sh` and dash (when installed) including new cases for the hook commands; `pytest tools/adlc/tests tools/lint-skills/tests` passes; `bash tools/lint-skills/check.sh` is clean with a scanned count above zero, and `unguarded-source` reports a hook command in `templates/hooks.yml` or in the committed `claude` render that spells its partial source any other way. (BR-16)
- [ ] AC-15: README, architecture, conventions, tools/adlc README, lint-skills README, init and template-drift skills and CHANGELOG carry the new surfaces; `conventions.md` states in one paragraph what adding a harness consists of (adapter file, golden fixtures, `accepted_fidelity`, and a format renderer only for a new file format), and `grep -rn 'if harness == ' tools/adlc` returns nothing — no renderer branches on a harness name. (BR-17)
- [ ] AC-16: Matcher vectors, each a fixture adapter run through the lint with one deny-tier command `git push --force` (`match: exact`) and one routine allow. `command-base` `git` equals the first token of `FOO=1 git push --force` after stripping and matches; `subcommand` renders a three-token routine prefix capped at two tokens and reports `widened`; `token-prefix` `git push` matches `git push --force` and does not match its `git -C . push --force` wrapped form, which only a `git -C` allow matches (shape `git-c`); `prefix` `git pu` does not match (word boundary) while `git push` does. An `exact` deny rendered exact by the format is compared by equality, and a format that collapses it to a prefix is evaluated with the granularity matcher. `find . -exec git push --force {} ;`, `xargs`, `npx`, `npm run` and `gh api` allows are not evaluated and produce no finding. A routine allow matching `git push --force origin feature` while the deny is exact reports `residual:exact-deny` and fails unless listed under that `(entry, command)` in `accepted_fidelity`; `claude` lists it (Rule A). An accepted verdict keyed by the entry id covers all its commands, and an `"<id>:<argv>"` key covers one command, the narrower winning. An adapter with no `default_mode_map` omits `default_mode` and the lint reports `default_mode` as `inexpressible`, failing unless accepted; `claude`'s mapped value renders to `permissions.defaultMode`. A `source: probe` record that does not equal the fixture result file's `sub_results` entry at the same `harness_version` fails the lint, a `source: grandfathered` record on any adapter other than `claude`'s `prefix` fails the loader, `fence-prefix` as a granularity fails the loader, and `env-prefix` and `shell-opener` records stay `unverified` for `claude`. (BR-1, BR-8, BR-9)
- [ ] AC-17: Scope vectors. `adlc harness render --harness claude --scope user` writes the deny tier only and no routine entry, the fence included; any user-level allow appears only as printed advisory text, and a printed render for a fixture adapter standing in for Copilot carries no first-token or broad fence entry. The shared-base rule omits a wrapping routine entry at `project`, `printed`, written `user` and `exec` scope (a fixture whose `deny_under_allow` is a `confirm` pass omits it at `exec`, where the mechanism is a hard deny, and keeps it at `project`). At `exec` scope `fence.partial-source` renders as the adapter's `fence_broad_spelling` and is reported `widened`; a fixture `fence_broad_spelling` of `[if]`, `[sh]`, `[bash]` or `[zsh]` fails the loader. At `exec` scope a deny-tier spelling renders as a hard deny when `capabilities.deny` is `yes` and the syntax can express it without matching a routine entry that stays rendered, else `deny-unsupported`, `exec.engine_deny` entries join the exec deny set, and a `match: exact` deny entry renders as a prefix match. A fixture `exec.deny_render: none` is accepted only alongside a `fail` ask-tier-deny verdict. `grep` shows the declared-residuals section, with the same wording, in `tools/lint-skills/README.md`, `tools/adlc/README.md` and the README of the `claude` adapter, and at the end of the lint report. (BR-6, BR-8, BR-18)

## External Dependencies

- None new. `python3` stdlib for the loader, renderers, lints and doctor; `git` for `/template-drift` baselines; harness binaries are probed by REQ-654's detect and never required.
- REQ-654 (P0) provides `adlc harness detect --json` and the `harness:<name>` doctor checks this REQ consumes.
- REQ-660 ships the `session-record` partial and owns the sidecar contract (BR-10); until it lands the stub partial named in BR-10 stands in under the same name.
- This REQ deletes `templates/claude-settings-template.json` (BR-6); REQ-655 BR-13 and REQ-666 BR-15 must re-point to the committed `claude` golden render at `harness/claude/rendered/settings.json`.

## Assumptions

- REQ-654 (P0) has landed before this REQ's implementation starts: `ADLC_HOME`, `adlc harness detect --json`, the skills-only view and the `harness:<name>` doctor checks are the primitives this REQ calls. If REQ-654 is still in flight, this REQ's architecture names the exact detect fields it consumes and the two are sequenced in the sprint.
- P1 (REQ-666 skill-text portability, `.adlc/agents/` vendoring, the `agents` drift surface, the `no-harness-path` lint) lands before this REQ; its template additions (`cat`, `grep`, `gcloud` for the run-and-read context blocks) are part of the baseline BR-7 pins. This REQ writes no SKILL.md body changes beyond `init` and `template-drift`, adds no `.adlc/agents/` surface, and its blocked-path additions are disjoint from P1's.
- The five harness names, binaries and capability facts come from the plan's docs-verified survey of 2026-10-27 (§1, §2e, §2g); only the `claude` adapter's facts are exercised here. The other four adapters are data files written by their own REQs against this schema. REQ-656 (P2b), REQ-655 (P3) and REQ-658 (P4) each may add adapter fields with a schema version bump; the loader rejects an adapter whose schema version it does not know. Schema-bump contract: a bump adds optional fields; a field required of every adapter is added to `claude.yml` and its goldens by the bumping REQ; `schema_version` is the top-level integer.
- Claude Code reads `@AGENTS.md` imports in `CLAUDE.md`, matches `Bash(...)` permission rules by prefix on the command text, and supports a `SessionStart` hook with a `compact` matcher, as the plan's matrix records.
- "Toolkit CI" is the lint, pytest and partials-test gates `/proceed` runs on this repo; there is no hosted CI workflow in the toolkit, and adding one is not implied.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] Does the Claude Code version in use expose a `SubagentStart` hook event? The plan's matrix treats it as absent (subagents on Claude rely on the skill `!` line and the prompt prepend); if present, `harness/claude.yml` declares `subagent_start_hook: yes` and the `claude` render emits it. Proposed: verify on the installed binary during architecture and set the capability from the result, never from the docs alone.
- [x] Where do the golden renders live? Resolved: next to the adapter, under `harness/<name>/rendered/` (for `claude`: `harness/claude/rendered/settings.json`), so a reviewer sees an allowlist change as a diff of the rendered file, not only of the semantic source; BR-13 and the External Dependencies name that location.
- [x] Should the `claude` adapter render the deny tier as `ask` only, or also offer a `--deny` render option now? Resolved by BR-6: `claude` declares `deny_tier_render: {project: confirm}`, so its committed render is `ask`; the exec-scope deny rendering is REQ-662's `exec.deny_render`, independent of this map; the `deny` capability is declared for REQ-659 and no render option is added until an engine consumes it (Rule B — nothing here should make an unattended run cheaper to approve).
- [x] Does `/init --harness` on the toolkit's own repo write `AGENTS.md` at the clone root, given the clone is also what `~/.claude/skills` points at? Resolved by BR-12: yes, and it is harmless — harnesses read `AGENTS.md` from the project cwd, not from a skills mount; the architecture phase confirms against §6.7's skills-view behaviour before the dogfood write.

## Out of Scope

- The Copilot and Cursor adapters (REQ-656, P2b), Codex (REQ-655, P3), Gemini (REQ-658, P4): no `harness/<name>.yml` other than `claude` ships here; the fixture `fake` adapter is test-only and lives outside `harness/`.
- Executing any harness headlessly, per-run trust, approval state, `/sprint approve` — the exec engine (REQ-659) and its adapters (REQ-662). The `exec` and `trust` adapter fields are declared so they read data, not code; the keys inside `exec` are theirs.
- The sidecar contract, its partial and the knowledge-loop consumers — REQ-660.
- Any SKILL.md body change outside `init` and `template-drift` (the `$ARGUMENTS` prose, `!` lines other than ETHOS, dispatch fallbacks, Teton retirement, description trims) — REQ-666 / REQ-661.
- Vendoring `agents/` into `.adlc/agents/` and the `agents` drift surface — REQ-666.
- Project-level agent files for any harness (`--project-agents`) — deferred with the Copilot cloud-agent case that needs it.
- Plugin manifests at the clone root (REQ-665) and `install.sh --migrate-home` (REQ-663).
- Changing the user-level `~/.claude/CLAUDE.md` routing block or writing `~/.codex/AGENTS.md` — REQ-655.
- Verifying skill discovery, trust, sandbox or allowlist behaviour on any non-Claude harness — the plan's §6 experiments, owned by REQ-664 and the adapter REQs.
- Windows.

## Retrieved Context

- REQ-519 (spec, score 11): One-Command Installer and `adlc doctor` Health Check
- REQ-520 (spec, score 11): Forge Adapter — Configurable GitHub / Azure DevOps PR Operations
- LESSON-395 (lesson, score 10): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up
- REQ-416 (spec, score 10): Toolkit refactor: DRY ethos macro and Kimi gate, shrink /proceed, lock-symlink TOCTOU review, requirements.txt pinning
- LESSON-716 (lesson, score 9): A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see
- REQ-610 (spec, score 9): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- REQ-525 (spec, score 9): /template-drift covers all vendored sync surfaces: ETHOS.md and the workflow runtime
- REQ-426 (spec, score 9): REQ-416 follow-ups bundle: install.sh integrity, reason-string DRY, partials drift, partials tests
- LESSON-718 (lesson, score 8): A gate that judges a change must not load anything the change can edit — not its code, its config, its partials, or a path that differs only in letter case
- REQ-652 (spec, score 8): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- LESSON-619 (lesson, score 8): A harness that executes lines extracted from markdown is an execution surface — gate on a token allowlist, and never cite the lint as the control
- LESSON-572 (lesson, score 8): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 8): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts
- LESSON-397 (lesson, score 8): Toolkit commands that mutate project artifacts must resolve the repo root from the caller's cwd, not the script's own location
- REQ-522 (spec, score 8): De-brand the delegation surface (no Kimi naming) and make skill telemetry single-fence-safe
