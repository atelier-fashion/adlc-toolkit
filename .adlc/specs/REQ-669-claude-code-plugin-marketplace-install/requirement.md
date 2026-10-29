---
id: REQ-669
title: "Self-sufficient Claude Code plugin install, published through a self-hosted marketplace and submitted to the Claude directory"
status: approved
deployable: false
created: 2026-10-28
updated: 2026-10-28
component: "adlc/toolkit"
domain: "adlc"
stack: ["markdown", "bash", "python", "json", "claude-code", "claude-skills"]
concerns: ["developer-experience", "portability", "reliability"]
tags: ["install", "plugin", "marketplace", "distribution", "doctor", "release", "path-resolution", "init", "template-drift"]
lane: "full"
lane_reason: "changes install infrastructure (criterion 2) across skills, partials, tools, agents and doctor, far above max_files (criterion 5), and reverses the project-overview decision of no versioning at the install layer (criterion 6)"
lane_forced: false
---

## Description

Getting ADLC today means cloning the repo and running `install.sh`, which points
the whole of `~/.claude/skills` and `~/.claude/agents` at the clone. That works
for the maintainer. For a stranger trying the toolkit, it is a heavy first step:
it replaces their own skills directory, and nothing about it is one command.
Every distribution channel (README, Hugging Face, the Claude directory, a launch
post) sends people to that step, so it is the step that decides how many of them
stay.

Claude Code has a plugin system with marketplaces. A git repo can be both the
marketplace and the plugin, and a user installs it with two commands. Anthropic
also runs a directory at claude.ai/directory that third parties submit to. Neither
is used today.

The multi-harness work on the unmerged branch
`claude/toolkit-non-claude-users-13f6cf` covers part of this. Draft REQ-665 adds a
`.claude-plugin/plugin.json`, but it puts "Publishing to any marketplace or
registry" out of scope. Its BR-8 also accepts that a plugin install is not
self-sufficient until REQ-666's `no-harness-path` work lands. REQ-665 sits in the
plan's optional last phase, P7, after about a dozen full-lane REQs.

This REQ pulls the Claude Code part forward and finishes it. It adds a plugin that
works on a machine that has never run `install.sh`. It lists that plugin in a
marketplace hosted in this repo and submits it to the Claude directory. The
symlink live install stays as the route for contributors and the maintainer.

The work is self-sufficiency, not the manifest file. Today skills, partials, tools,
agents, workflows and templates name toolkit files by the literal path
`~/.claude/skills/...`.

| Area | Literal `~/.claude/skills` or `~/.claude/agents` references |
|---|---|
| `*/SKILL.md` (11 files) | 128 |
| `tools/` | 98 |
| `partials/` | 47 |
| `agents/` | 4 |
| `workflows/` | 4 |
| `templates/` | 2 |

Under a plugin install those paths do not exist. Claude Code copies the plugin to
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. Per the plugin docs
read on 2026-10-28, `${CLAUDE_PLUGIN_ROOT}` is substituted in skill and agent
markdown bodies, but it is not set in the environment of commands run through the
Bash tool. Plugin skills are invoked as `/<plugin>:<skill>`, and a plugin's `bin/`
directory is put on the Bash tool's PATH.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| PluginManifest (`.claude-plugin/plugin.json`) | name | string | `adlc`; kebab-case; must not start with `claude-`, `anthropic-`, `anthropics-` or `cc-plugin-` |
| PluginManifest | version | string | equals the trimmed content of `VERSION` |
| PluginManifest | skills / agents | path list | relative, `./`-prefixed, inside the repo; exposes every toolkit skill and agent |
| MarketplaceManifest (`.claude-plugin/marketplace.json`) | name | string | the marketplace name users type; required |
| MarketplaceManifest | owner | object | required |
| MarketplaceManifest | plugins | list | exactly one entry, `{ name: "adlc", source: "./" }`; entry name equals manifest name |
| InstallRoute | value | enum | `symlink` (today's `install.sh` route) or `plugin` |
| ToolkitRoot | path | absolute path | the directory toolkit-owned files are read from for the running install: the clone for `symlink`, the plugin cache copy for `plugin` |
| MachineState | counters, `~/.claude/adlc/config.yml`, locks, telemetry log | files | shared by both routes; never inside the plugin cache |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| plugin_installed | user runs the marketplace add and plugin install commands | plugin version |
| plugin_updated | user runs the plugin update command after a release | old and new version |
| doubled_install_detected | `adlc doctor` finds both routes active on one machine | which copy each skill name resolves to |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| install or update the plugin | any Claude Code user |
| publish a release to the marketplace (tag on `main`) | maintainer |
| submit or update the Claude directory listing | maintainer, on a paid claude.ai plan |

## Business Rules

- [ ] BR-1: This repo is both the marketplace and the plugin. A user installs with exactly two commands, a marketplace add of `atelier-fashion/adlc-toolkit` and a plugin install of `adlc` from it. The README prints both commands verbatim.
- [ ] BR-2: Under the `plugin` route, on a machine with no `~/.claude/skills` and no `~/.claude/agents` from this toolkit, every skill completes its documented happy path. Every toolkit-owned file that a skill, partial, agent, workflow or tool reads resolves from the plugin's own ToolkitRoot. No code path reachable under the `plugin` route reads a toolkit-owned file from `~/.claude/skills` or `~/.claude/agents`.
- [ ] BR-3: The `symlink` route behaves exactly as it does today. On a symlink-only machine every existing test suite passes unchanged, `./install.sh` on a healthy machine reports zero actions, and no SKILL.md instruction changes meaning for that user.
- [ ] BR-4: One skill text serves both routes. The toolkit does not keep a second copy of any SKILL.md, partial, agent or template for the plugin. Which mechanism resolves ToolkitRoot is an architecture decision. It must hold in fenced shell the model runs, where `${CLAUDE_PLUGIN_ROOT}` arrives as already-substituted text under `plugin` and is absent under `symlink`.
- [ ] BR-5: Vendored copies keep priority. A consumer project's `.adlc/partials/`, `.adlc/templates/` and `.adlc/workflows/` are still read first on both routes, as REQ-610's guarded two-level spelling reads them today. ToolkitRoot replaces only the fallback level.
- [ ] BR-6: Machine state stays where it is and is shared by both routes. That covers the REQ, BUG and LESSON counters, the lock directories, `~/.claude/adlc/config.yml` and the telemetry log. A machine that switches routes keeps allocating collision-free ids (informed by REQ-546). When `install.sh` never ran, no skill fails for lack of its state. State is created lazily with the same defaults `install.sh` writes, including delegation off (informed by REQ-519, REQ-515).
- [ ] BR-7: Under the `plugin` route, the `adlc` CLI, including `adlc doctor`, is on the Bash tool's PATH without `install.sh`. The delegation CLIs stay opt-in exactly as today. Installing the plugin never enables delegation, and an explicit `enabled: false` still wins (informed by BUG-205, REQ-515). `adlc doctor` stays pure stdlib (informed by LESSON-395).
- [ ] BR-8: `/init` and `/template-drift` treat the running install's ToolkitRoot as the canonical source. Under the `plugin` route, `/template-drift` names the plugin version it compares against as its baseline (informed by BUG-204).
- [ ] BR-9: Agents dispatched by a skill resolve under both routes by the name the skill text uses, or the skill text uses a name valid on both. This is verified on a real plugin install. If it cannot be resolved, a skill names the failure and runs its inline fallback rather than silently skipping the agent.
- [ ] BR-10: Every instruction a skill prints for the user or for another skill, such as "run `/validate`", is runnable as printed on the route in use. That includes the 267 skill-to-skill references in SKILL.md text.
- [ ] BR-11: When both routes are active on one machine, `adlc doctor` reports a doubled install. It names which copy Claude Code resolves for a sample skill and prints a copy-pasteable fix for each way out.
- [ ] BR-12: A `tools/lint-skills` check fails when `plugin.json`'s `version` differs from `VERSION`, or when a skill directory or agent file in the repo is not exposed by the manifest (informed by LESSON-012, LESSON-019). If REQ-665 lands, its `manifest-parity` check absorbs this one, so there is one check, not two.
- [ ] BR-13: A lint check fails on any literal `~/.claude/skills` or `~/.claude/agents` read path reachable under the `plugin` route, outside a stated exception list. If REQ-666 lands, its `no-harness-path` check absorbs this one with the same exceptions.
- [ ] BR-14: A release is a `VERSION` bump merged to `main` and tagged. After it, `claude plugin update adlc@<marketplace>` installs the new version. The CHANGELOG entry for the release states the plugin version.
- [ ] BR-15: Submitting to the Claude directory is a documented maintainer release step, performed through claude.ai/directory/manage. This REQ is complete when the submission is filed and its reference is recorded, not when Anthropic accepts it.
- [ ] BR-16: Every claim the README makes about plugin loader behavior is verified on a real install of the current Claude Code release before it ships. The Claude Code version it was verified on is recorded beside the claim. Three behaviors are unverified at spec time: whether a `skills` path of `"./"` picks up the root-level `<skill>/SKILL.md` directories, how plugin agents are named for dispatch, and whether relative symlinks inside the repo survive the copy into the cache.
- [ ] BR-17: New and changed shell is POSIX-sh, bash 3.2, zsh and dash safe. That means no `case` inside `$( )`, no `\b` in `grep -E`, no `[[`, and no `local`. New Python is stdlib only (informed by LESSON-582, LESSON-013, LESSON-395).
- [ ] BR-18: This REQ lands on `main` without depending on REQ-654 through REQ-666. Whichever of this REQ and those REQs lands second reconciles. Four known conflicts are settled this way:
  - REQ-665 drops its Claude Code manifest in favour of this one.
  - REQ-665 BR-6 keeps the symlink install primary in the README, which yields to BR-19 here.
  - REQ-654 BR-3 says the REQ-610 fence spelling, with its literal `~/.claude/skills` fallback, is not changed. That yields to BR-5 and BR-13 here, which change only the fallback level.
  - REQ-666's `no-harness-path` keeps the ToolkitRoot mechanism this REQ chose, or replaces it in one change that updates both routes. Its vendoring of agents into `.adlc/agents/` must satisfy BR-9 here.
- [ ] BR-19: Documentation that states the install model is updated in the same change. That covers the README (plugin first for users, symlink for contributors, coordinated with REQ-672), `.adlc/context/project-overview.md` ("Install model" no longer says there is no versioning at the install layer), `.adlc/context/architecture.md` and the CHANGELOG.
- [ ] BR-20: The submitted plugin meets the directory's own acceptance rules, and a directory install works as well as a marketplace install. The plugin docs say directory listings reach Claude Code users through the claude.ai sync path, and that path rejects a plugin with a top-level `bin/`. So the BR-7 CLI exposure must use a mechanism that path accepts, or the spec must record that directory installs lack the CLI and what `adlc doctor` says about it.

## Acceptance Criteria

- [ ] On macOS, a sandbox HOME with no toolkit symlinks and no machine state can run the two BR-1 commands. After them, `/adlc:init` scaffolds `.adlc/` in a throwaway repo, `/adlc:spec` writes a REQ, `/adlc:status` lists it, and `adlc doctor` reports no failures for the plugin route.
- [ ] In that sandbox, a lite REQ runs end to end through `/adlc:proceed` in a throwaway GitHub repo: spec, implement, review, PR and wrapup. No step reads from `~/.claude/skills`, checked with filesystem access logging or a guard that fails on the read.
- [ ] On a symlink-only machine, `partials/tests/run.sh`, the `tools/` test suites and `tools/lint-skills` pass. `./install.sh` reports zero actions.
- [ ] On a machine with both routes active, `adlc doctor` prints the doubled-install finding with a fix. On a symlink-only machine and on a plugin-only machine, it prints no such finding.
- [ ] New and changed shell passes `partials/tests/run.sh` under bash 3.2, zsh and dash.
- [ ] The README, `.adlc/context/project-overview.md`, `.adlc/context/architecture.md` and the CHANGELOG describe both install routes, and no sentence in them still says the install layer has no versioning.
- [ ] A fixture with `plugin.json` version different from `VERSION` fails the BR-12 lint, and so does a fixture with a skill missing from the manifest. A fixture with a literal `~/.claude/skills/partials/x.sh` read in a new partial fails the BR-13 lint.
- [ ] After a test release bumps `VERSION`, `claude plugin update` in the sandbox installs the new version, and `/adlc:template-drift` names it as the baseline.
- [ ] The Claude directory submission is filed, and its reference is recorded in the CHANGELOG entry for the release.
- [ ] Each BR-16 behavior is recorded as verified, with the Claude Code version, or the README marks it unverified.

## External Dependencies

- Claude Code plugin and marketplace system (`claude plugin marketplace add`, `claude plugin install`, `claude plugin update`).
- The Claude directory developer portal at claude.ai/directory/manage, which needs a paid claude.ai plan.
- GitHub, hosting the marketplace at `atelier-fashion/adlc-toolkit`.

## Assumptions

- The plugin system facts in the Description come from the official Claude Code plugin docs as read on 2026-10-28 through a summarizing fetch. BR-16 exists because some of them must be checked on a real install.
- The plugin name `adlc` is available and valid, and the marketplace name is `adlc-toolkit`. Users accept namespaced commands such as `/adlc:spec` on the plugin route.
- Org-managed distribution through claude.ai or Cowork, where an admin pushes plugins to a team, is not needed for this REQ. The public directory listing is needed, and BR-20 covers what it requires.
- Consumer projects that already ran `/init` keep working on the plugin route mostly through their vendored `.adlc/partials/`. The fallback level matters most before `/init` and for `tools/`.

## Open Questions

- [ ] Should REQ-665 be narrowed now, removing its Claude Code manifest, so the two specs do not both claim `.claude-plugin/plugin.json`? Or should BR-18's land-second reconciliation stand?
- [ ] Should the README lead with the plugin route for everyone once this ships, with the symlink route for contributors only? This REQ assumes yes. REQ-672 owns the README layout.
- [ ] Should the plugin pin `version`, so users stay on it until a release, or track commits, so users get every merge to `main`? This REQ assumes pinned to `VERSION`, per BR-14.
- [ ] Does a plugin installed from the Claude directory go through the same claude.ai sync path that rejects a top-level `bin/`? The answer decides how BR-20 is met, and only a real submission settles it.

## Out of Scope

- Manifests or installs for Cursor, Gemini CLI, Copilot CLI or Codex, which belong to REQ-665, REQ-656, REQ-658 and REQ-655.
- Moving machine state out of `~/.claude`, which is REQ-663.
- Distribution through claude.ai or Cowork org plugin sync.
- Changing auto-update defaults for users.
- Any usage telemetry from installed plugins.
- Windows.

## Retrieved Context

- REQ-519 (spec, score 12): One-Command Installer and `adlc doctor` Health Check
- LESSON-395 (lesson, score 9): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up
- REQ-520 (spec, score 9): Forge Adapter — Configurable GitHub / Azure DevOps PR Operations
- LESSON-626 (lesson, score 8): A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event
- BUG-207 (bug, score 8): The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint
- BUG-204 (bug, score 8): /template-drift treats the toolkit working checkout as canonical without checking which branch it is on — a stale baseline inverts every verdict and proposes regressions
- LESSON-572 (lesson, score 8): A remediation is only real if its audience can execute it. Handing a human-readable instruction into a machine-consumed channel is not a fix — it is a fix-shaped comment. When an operation half-succeeds, give each fact its own normalized field and finish the half you are able to finish.
- BUG-195 (bug, score 8): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts — the remote branch survives and no caller acts on the warning
- REQ-546 (spec, score 8): Atomic remote id reservation at allocation time (close the allocation-to-visibility window)
- LESSON-013 (lesson, score 8): BSD grep \\b word-boundary in -E silently fails on macOS — use -wF instead
- REQ-263 (spec, score 8): Enforce per-REQ unique worktree paths in /sprint dispatch and /proceed Phase 0
- LESSON-620 (lesson, score 7): A guard that degrades only on failure cannot see a narrowed input — when the scan root defines the namespace, resolving it wrongly redefines the question instead of failing to answer it
- BUG-210 (bug, score 7): An allocation running inside a git worktree collapses the machine-global id namespace to one checkout, and never reports it as degraded
- REQ-594 (spec, score 7): Spec intake: turn raw human input into a draft REQ plus an explicit gap list
- LESSON-582 (lesson, score 7): bash 3.2 cannot parse a `case` statement inside `$( )` — the shell that rejects your script is the oldest one a user has, not the newest one CI runs
