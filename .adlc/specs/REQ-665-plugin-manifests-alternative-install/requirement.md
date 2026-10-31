---
id: REQ-665
title: "Plugin manifests as an alternative install, kept in step by a manifest-parity lint"
status: complete
deployable: false
created: 2026-10-27
updated: 2026-10-30
component: "adlc/install"
domain: "adlc"
stack: ["json", "python", "markdown", "sh"]
concerns: ["portability", "harness-agnostic", "developer-experience", "lint"]
tags: ["plugin", "manifest", "install", "harness", "multi-harness", "lint-skills", "version", "symlink", "readme", "agents", "hooks", "mcp", "cursor", "gemini", "copilot", "claude-plugin", "parity"]
lane: "full"
lane_reason: "footprint far above max_files (two new manifests, the plugin-manifest lint absorbed into manifest-parity with fixtures and tests, README, project-overview, CHANGELOG) and it adds install surfaces for the toolkit's distribution"
lane_forced: false
---

## Description

This REQ adds plugin manifests for Cursor and Copilot CLI beside the Claude Code
manifests REQ-669 shipped, and folds REQ-669's `plugin-manifest` lint into one
`manifest-parity` check that keeps every manifest in step with the skill set, the
agent set and `VERSION`. It is P7a of `.adlc/research/multi-harness-plan.md`
(revision 2), the first half of the plan's optional P7.

**Revised 2026-10-30, at Phase 1.** The spec was written on 2026-10-27, before
REQ-669 and REQ-657 landed, and before the schemas were read. What changed:

- REQ-669 already ships `.claude-plugin/plugin.json` (plugin `adlc`),
  `.claude-plugin/marketplace.json` (marketplace `adlc-toolkit`), `hooks/hooks.json`
  and the Claude Code plugin route, and its BR-18 ruled that this REQ drops its
  Claude Code manifest, that BR-6's "symlink primary" yields to REQ-669 BR-19
  (plugin first for users), and that `manifest-parity` absorbs `plugin-manifest`.
  So the plugin name across the set is `adlc`, not `adlc-toolkit`.
- Claude Code's plugin route is self-sufficient. Cursor's and Copilot's are not:
  neither documents `CLAUDE_PLUGIN_ROOT` for a skill's shell, so a skill fence resolves
  ToolkitRoot through `~/.claude/skills` or the plugin-root pointer, and a machine
  needs one of the Claude Code install routes behind it. That is what "catalog mount" means below.
- Copilot's schema is documented (Open Question 1, answered), so it enters the set.
- Gemini leaves the set under BR-2's own removal rule (Open Questions 3 and 4,
  answered). `gemini-extension.json` is not shipped by this REQ.

What the symlink route cannot offer on Cursor or Copilot is a **pinned** catalog.
Each has a plugin mechanism whose unit is a directory with a manifest; a manifest
lets the harness's own install load the toolkit at a chosen ref as one unit. This
REQ adds those manifests, each pointing at the toolkit's **existing** skill
directories (`<name>/SKILL.md` at the root; nothing moves), adds the
`manifest-parity` check (LESSON-012: a structural guard, not a prose promise), and
adds a README section per harness that states the trade-off honestly.

**Why Gemini left the set.** Read on 2026-10-30 from the Gemini extension reference
and `packages/cli/src/config/extension-manager.ts`:

1. Skills load only from `<extension>/skills`; the manifest has no skills key. A
   clone-root `gemini-extension.json` therefore needs a root `skills/` directory.
2. That root `skills/` breaks another harness: Claude Code's `skills` key "adds to
   the default `skills/` scan" (plugin reference), so REQ-669's plugin would scan
   every skill twice.
3. Install copies with `fs.promises.cp(source, destination, { recursive: true })`.
   Node rewrites a relative symlink to an absolute path into the source
   (`verification.md` carries the local proof), so a symlink view dangles after a
   git install, whose source is a temporary clone, and points back at the clone
   after a local-path install, which is not a pin. That is BR-2's removal case.
4. `agents/` and `hooks/hooks.json` are read from fixed locations with no opt-out,
   so a clone-root extension would feed Gemini the Claude-format agents and
   Claude's hook, which BR-3 and BR-4 forbid.

A pinned Gemini install needs an artifact with real copies under `skills/`, such as
a generated release branch or archive. That is a publishing step, which is Out of
Scope. Gemini keeps the `~/.agents/skills` mount, and REQ-658 is told so (BR-14).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Manifest | harness | enum | the registry's entries: `claude`, `cursor`, `copilot`. The set is defined in exactly one place (the lint's registry, BR-1/BR-7) and the README subsections follow it |
| Manifest | path | path | clone-root-relative: `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.github/plugin/plugin.json` |
| Manifest | companions | list of paths | files the harness's install route requires beside the manifest: `.claude-plugin/marketplace.json` for `claude`; part of the registry entry, covered by BR-7(b), (g) |
| Manifest | name | string | `adlc` in every manifest; identical across the set (REQ-669) |
| Manifest | version | string | byte-equal to the trimmed content of `VERSION` |
| Manifest | skills_ref | path or list | `"./"`, or an array of `./<skill>` entries; resolves to exactly the SkillSet |
| Manifest | agents_ref | path or list | `claude`: absent, or lists every `agents/*.md` (REQ-669). `cursor`, `copilot`: present and `[]` (BR-3) |
| Manifest | hooks_ref | object | `claude`: no shape rule beyond `execution-key`; `hooks/hooks.json` is read by default, so an inline definition is refused. `cursor`, `copilot`: present and `{}` (BR-4) |
| Manifest | mcp_ref | path | absent, enforced by `execution-key`; the toolkit ships no MCP server (BR-4) |
| Manifest | content | JSON | stdlib-parseable; contains no absolute path, no `$HOME`, no user-specific value |
| SkillSet | entries | set of names | every directory `<name>` at the clone root holding a `SKILL.md`, the loader's rule that `plugin-manifest` already uses (17 skills on 2026-10-30) |
| AgentSet | entries | set of files | `agents/*.md` (19 agents on 2026-10-30) |
| ParityFinding | rule | enum | `set-incomplete`, `unparseable`, `name-mismatch`, `version-mismatch`, `skill-missing`, `skill-extra`, `dangling-entry`, `agents-ref-invalid`, `hooks-ref-invalid`, `path-missing`, `unknown-key`, `machine-path`, `execution-key`, plus the REQ-669 rules kept under their own wording (reserved name, marketplace entry, top-level `bin`) |
| ParityFinding | remediation | string | a copy-pasteable command or exact edit naming the file (REQ-519 BR-5, LESSON-572) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| manifest_parity_run | `bash tools/lint-skills/check.sh`, pytest | one ParityFinding per violation; zero findings in a root `is_plugin_root` does not arm (consumer repos) |
| version_bumped | a release commit changes `VERSION` | every manifest's `version` changes in the same commit, or the next lint run fails with `version-mismatch` |
| skill_added_or_removed | a `<name>/SKILL.md` appears or disappears at the clone root | a manifest that enumerates skills changes in the same commit, or the next lint run fails with `skill-missing` / `dangling-entry`; a `"./"` manifest needs no change |

_Permissions: not applicable — repository files and a developer-machine lint. Section omitted deliberately._

## Business Rules

- [ ] BR-1: The toolkit ships one manifest per harness in the set: `.claude-plugin/plugin.json` (REQ-669's, unchanged), `.cursor-plugin/plugin.json` and `.github/plugin/plugin.json`. The set is the harnesses whose manifest schema can meet BR-2, BR-3 and BR-4 at the clone root, and is defined once, in the lint's registry (BR-7), and nowhere else. A harness outside the set gets a README subsection that says so and why; adding it later is one registry entry plus one file. A companion file an install route requires (`.claude-plugin/marketplace.json`) is part of that harness's registry entry. Every manifest is valid JSON that `python3 -m json.tool` accepts, carries `name: adlc` and the `version` of BR-5, uses only keys its harness documents (BR-7(h)), and contains no absolute path, no `$HOME`, and no user- or machine-specific value, so the committed file is the file every installer reads. (informed by REQ-519, REQ-669 BR-18)
- [ ] BR-2: Each manifest points at the toolkit's **existing** skill directories. No `SKILL.md` moves, no `SKILL.md` is edited, and no `skills/` directory is added at the root, of copies or of symlinks: Claude Code scans a root `skills/` in addition to its `skills` key, so one would double REQ-669's catalog. A harness whose schema cannot redirect its skills directory, or whose installer does not preserve a committed relative symlink, is removed from the registry for this REQ rather than served copies. Gemini CLI is removed on this rule (Description). (informed by REQ-654's plan Rule A, LESSON-441)
- [ ] BR-3: A manifest references the canonical `agents/` directory only for a harness that reads that format as-is: Claude Code. Omitting the key is not enough on Cursor or Copilot, because each scans `agents/` by default, and an override replaces the default scan (Cursor reference). Their manifests therefore carry an explicit `"agents": []`, and their README subsections say agents are not loaded from the plugin. Agents reach Cursor through `~/.claude/agents` from the symlink install (REQ-656: `paths.agents: via:claude`) and reach Copilot through REQ-656's renders. A manifest never points a harness at a format it cannot read, because a half-parsed agent definition is worse than none. If a harness treats the empty override as absent, the outcome is the same as omitting the key, so on that reading the override is no worse. If a harness rejects the empty value, the install fails or the plugin does not load, which is louder than omitting the key; that is unverified (Deferred). (revised 2026-10-30)
- [ ] BR-4: The Claude Code hook `hooks/hooks.json` is REQ-669's and stays. It is Claude-format and calls `${CLAUDE_PLUGIN_ROOT}`, and both Cursor and Copilot name `hooks/hooks.json` as their default location, so their manifests carry an explicit `"hooks": {}`. No per-harness render is bundled: REQ-656 shipped Copilot's (`.github/hooks/adlc.json`, written into a project by `/init --harness copilot`) and Cursor reads a project's `.claude/settings.json`, so neither is plugin content, and `templates/hooks.yml` is not harness-readable and is never referenced. The README's what-does-not-load line says so. Because nothing is bundled, `lane_check.py` `DEFAULT_BLOCKED_PATHS` and `render-parity` are unchanged. The toolkit ships no MCP server; no manifest references one, and no manifest defines a hook, a command or a server inline, because a manifest is what a harness acts on at install and BR-7(j) is what holds that. (revised 2026-10-30)
- [ ] BR-5: `version` in every manifest equals the trimmed content of `VERSION`. A release that bumps `VERSION` updates every manifest in the same commit, by hand, and `RELEASING.md` names all three. The lint (BR-7) fails on any drift, so a release cannot ship a plugin that announces the previous version. (informed by LESSON-019 — the version is read from `VERSION`, never hardcoded)
- [ ] BR-6: The install order stays as REQ-669 BR-19 left it: the Claude Code plugin first for users, the symlink live install for contributors and the maintainer. `install.sh` is not changed by this REQ; `~/.claude/skills`, `~/.claude/agents` and the REQ-654 mounts keep their targets. The README's new section is titled as an **alternative** for harnesses other than Claude Code and states, once per harness, that a plugin install pins what that harness lists but does not replace a Claude Code install route on a machine that runs the skills, because a skill resolves ToolkitRoot, the installed engines and the `adlc` CLI through it. (informed by REQ-669 BR-19, LESSON-441; revised 2026-10-30)
- [ ] BR-7: `tools/lint-skills` replaces `plugin-manifest` with a `manifest-parity` check (REQ-669 BR-18: it absorbs `plugin-manifest`, keeping every rule and its arming), per-root (stdlib only, LESSON-395). Rules, each a ParityFinding with a copy-pasteable remediation: (a) **set-incomplete** — in an armed root every manifest in the registry exists; (b) **unparseable** — each is strict JSON (repeated keys rejected, LESSON-716); (c) **name-mismatch** — `name` is `adlc` in every manifest, so a set renamed in step still fails; (d) **version-mismatch** — `version` equals `VERSION`; (e) **skill-missing / skill-extra / dangling-entry** — the skills a manifest resolves to are exactly the SkillSet; (f) **agents-ref-invalid / hooks-ref-invalid** — the BR-3 and BR-4 shape per harness; (g) **path-missing** — every path any manifest references is a `./` path, with no `..` segment, that exists inside the checkout with symlinks resolved, only an image key (`logo`, `icon`) may hold an `https` URL instead, and every companion file exists; (h) **unknown-key** — a manifest carries only keys the registry lists as documented for its harness (BR-1); (i) **machine-path** — no string value starts with `/` or `~/`, names `$HOME`, holds a home path such as `/Users/` in any case, or is a URL form other than `https` with a host and no userinfo; (j) **execution-key** — no manifest carries a key that can run or install something or prompt for a value (`mcpServers`, `lspServers`, `extensions`, `experimental`, `settings`, `dependencies`, `userConfig`, `channels`, `variables`), no path key holds an inline definition, and no file of that kind sits at a harness's default location; `marketplace.json` holds only its listed keys, at the top level and in its entry. A root `is_plugin_root` does not arm yields zero findings, so the check is inert in consumer repos; a lint run that scans zero files remains a failure (REQ-610 BR-12). The check runs from `check.sh` and is covered by pytest fixtures for every rule. (informed by REQ-610, REQ-519 BR-5, LESSON-572, LESSON-012)
- [ ] BR-8: Until a plugin install is self-sufficient on Cursor and Copilot, the plugin coexists with the `~/.agents/skills` mount on the same harness, and the README names the cost plainly, per harness. On Copilot the documented order is first-found-wins with personal skills ahead of plugin skills, so the mount **wins** and a same-named plugin skill is silently ignored: the pin does nothing while the mount exists. On Cursor the order is undocumented: the README says each skill may be listed twice and marks the precedence unverified. Detecting or de-duplicating the doubled catalog is Out of Scope. On Claude Code a doubled install stays what REQ-669 made it: `adlc doctor`'s `doubled-install` failure, with a fix for each way out. (revised 2026-10-30)
- [ ] BR-9: The README gains a short "Install as a plugin on other harnesses (alternative)" section with one subsection per harness in the set other than Claude Code, plus one for Gemini CLI saying no manifest ships and why. Each set subsection states: the install command (Cursor: copy, not symlink, a clone at a tag into `~/.cursor/plugins/local/adlc`; update = re-copy. Copilot: `copilot plugin install <path>` from a clone at a tag; update = check out the new tag and install again); what loads (skills); what does not (MCP, none; hooks, per BR-4; agents, per BR-3; the runtime of BR-6); the BR-8 coexistence note; how to update a pinned copy; and the trade-off in one sentence: a pinned copy is reproducible and changes only when you update it, and can therefore be behind the clone; the live clone shows every commit instantly and cannot be pinned. Marketplace publishing is not documented, because none is offered (Out of Scope). (plan §4: say what is lost per harness)
- [ ] BR-10: Nothing moves (plan Rule A). `git diff --stat` for this REQ touches no `<name>/SKILL.md`, no file under `agents/`, no `partials/`, no `install.sh`, and no byte of `.claude-plugin/` or `hooks/`; `./install.sh` on a healthy machine still reports zero actions after the change; `readlink ~/.claude/skills` is unchanged. The new manifests are additive files under `.cursor-plugin/` and `.github/plugin/`.
- [ ] BR-11: New Python is stdlib only (LESSON-395). Any new or changed shell is POSIX-sh, bash 3.2, zsh and dash safe: no `case` inside `$( )`, no `\b` in `grep -E`, no bare `$<digit>`, no `[[`, no `local`, no `status` variable (informed by LESSON-582, LESSON-335, LESSON-013).
- [ ] BR-12: Documentation that states the install model is updated in the same change: `README.md` (BR-6, BR-9), `.adlc/context/project-overview.md` ("Install model"), `.adlc/context/architecture.md` (top-level layout and "Reconciliation with unmerged REQs"), `tools/lint-skills/README.md` (the renamed check and its rules), `RELEASING.md` (BR-5, and its two `plugin-manifest` mentions), `CHANGELOG.md`. (informed by LESSON-019)
- [ ] BR-13: Every claim the README makes about what a harness loads from the plugin is verified on a real install of that harness before the claim ships, or is marked unverified in the README, citing the harness's vendor doc and `.adlc/research/harness-probes/<harness>.json` or its absence. `.adlc/specs/REQ-665-*/verification.md` records which harnesses were exercised and what was read from where, and the PR says so. A README that asserts "Cursor loads the skills" from reading docs alone is the plan's own anti-pattern. (informed by BUG-204 — a baseline nobody checked inverts every verdict)
- [ ] BR-14: REQ-658's spec is told, in the same change, that `gemini-extension.json` does not exist: its `gemini:extension` and `gemini:dual-install` rows and its cross-reference to a Gemini install route have no shipped manifest behind them, and it decides what they become when it runs. This REQ adds no doctor row. (added 2026-10-30)

## Acceptance Criteria

- [ ] AC-1: The manifest set exists; each file passes `python3 -m json.tool`; `name` is `adlc` in every one; each `version` equals `cat VERSION`; `grep -n '/Users\|/home\|\$HOME' <manifests>` returns nothing. (BR-1, BR-5)
- [ ] AC-2: `bash tools/lint-skills/check.sh` is clean on the checkout. On a manifest that enumerates skills, adding `zzz-test/SKILL.md` fires `skill-missing` naming the skill and the manifest, with a remediation; applying it verbatim returns it to clean. Removing a skill directory while a manifest still names it fires `dangling-entry`. A `"./"` manifest stays clean through both. (BR-2, BR-7)
- [ ] AC-3: In a sandbox copy, changing `VERSION` to `9.9.9` makes the lint fire one `version-mismatch` per manifest naming the file and the expected value; restoring `VERSION` returns it to clean. (BR-5, BR-7)
- [ ] AC-4: Deleting one manifest from the sandbox copy fires `set-incomplete` naming it. Deleting every manifest from a versioned skills root fires `set-incomplete` once per manifest, never a silent pass (LESSON-019, REQ-669's arming), and a consumer-repo fixture that never had manifests scans clean. Pointing a manifest key at a path that does not exist fires `path-missing`; so does a missing companion file named in the registry. (BR-1, BR-4, BR-7)
- [ ] AC-5: `pytest tools/lint-skills/tests` passes with a fixture per BR-7 rule; `check.sh`'s exit-code contract is unchanged, including `255` for a vacuous scan; every REQ-669 rule still fires under `manifest-parity`. (BR-7, BR-11)
- [ ] AC-6: On Claude Code, `claude plugin validate . --strict` passes, `claude plugin validate .claude-plugin/plugin.json` passes with no warning about the manifest itself (its `--strict` form fails on the root `CLAUDE.md`, which predates this REQ; see Deferred), `partials/tests/plugin-route.test.sh` passes, and the REQ-669 install route is unchanged. On Cursor and Copilot, installing through the README's commands lists every toolkit skill and no agents, or the subsection is marked unverified and the gap is in Deferred. (BR-3, BR-8, BR-13)
- [ ] AC-7: `README.md`'s Gemini subsection says no manifest ships, gives the reason, and names the `~/.agents/skills` mount as what Gemini uses. No `gemini-extension.json` and no root `skills/` exists. (BR-2, BR-9)
- [ ] AC-8: On each harness in the set whose install route pins, with the plugin installed at a git ref, committing a throwaway skill to the clone does not change that harness's plugin catalog until its update step runs, while the mount shows the new skill immediately; the README's update step, run verbatim, brings the pinned copy forward. For a harness whose binary is unavailable the subsection is marked unverified and the gap is in Deferred. (BR-6, BR-8, BR-9)
- [ ] AC-9: `git diff --stat <base>..HEAD` for the REQ shows no change to any `*/SKILL.md`, `agents/*`, `partials/*.sh`, `install.sh`, `.claude-plugin/*` or `hooks/*`; `./install.sh` on a healthy machine reports zero actions; `readlink ~/.claude/skills` and `readlink ~/.claude/agents` are unchanged. (BR-10)
- [ ] AC-10: `README.md` has the alternative section with one subsection per harness in BR-9, each set subsection containing an install command, a what-loads line, a what-does-not line that names the BR-6 dependency, a BR-8 coexistence note, an update step, and the one-sentence trade-off; a test pins those parts. No sentence calls a plugin on these harnesses a replacement for a Claude Code install route. (BR-6, BR-8, BR-9)
- [ ] AC-11: `.adlc/context/project-overview.md`, `.adlc/context/architecture.md`, `tools/lint-skills/README.md`, `RELEASING.md` and `CHANGELOG.md` carry the new surfaces, and `plugin-manifest` no longer names a live check anywhere outside history. (BR-12)
- [ ] AC-12: In a sandbox copy, adding a key the registry does not list for that harness (e.g. `"adlcExtra": true`) to any one manifest makes `manifest-parity` fire `unknown-key` naming the file and the key, with a remediation that removes it; the pytest fixture set includes one such manifest per harness in the registry, and every committed manifest passes. (BR-1, BR-7)
- [ ] AC-13: REQ-658's spec names the absence of `gemini-extension.json`. (BR-14)

## External Dependencies

- None new to the toolchain. The harness binaries (`claude`, `agent`, `copilot`) are used only to verify BR-13 on a real install; none is required to build, lint or test. `python3` (stdlib) for the lint.
- REQ-669 (the Claude Code manifests, `plugin-manifest`, `doubled-install`), REQ-657 (hook renders: none bundled, BR-4), REQ-664 (the probe results BR-13 cites), REQ-658 (owns the Gemini doctor rows, told by BR-14), REQ-654 (the `~/.agents/skills` mount the plugin coexists with), REQ-656 (shipped: Cursor reads `~/.claude/agents`, Copilot agent and hook renders; none is bundled, BR-4).

## Assumptions

- The packaging facts are those of the vendor docs read on 2026-10-30, unverified until BR-13: Cursor `cursor.com/docs/reference/plugins`, Copilot CLI `docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference` (legacy manifest format), Gemini `geminicli.com/docs/extensions/reference` and `extension-manager.ts` on `main`, Claude Code `code.claude.com/docs/en/plugins-reference`.
- `"skills": "./"` is the container form on Cursor and Copilot, as it is on Claude Code: both docs and every found example give a directory of `<name>/SKILL.md` folders, none gives the root. Unverified on either harness (Deferred).
- Copilot's lookup order is `.plugin/plugin.json`, `plugin.json`, `.github/plugin/plugin.json`, `.claude-plugin/plugin.json`, so `.github/plugin/plugin.json` takes precedence over the Claude manifest. A legacy manifest (no `$schema`) is the right format: Agent Plugins 1.0 fixes skills at `skills/`, which BR-2 rules out.
- A git-based or local-path plugin install takes the whole clone (tools, partials, `.adlc/`), and that is acceptable: the manifest names what the harness loads, so the extra directories cost disk, not catalog budget.
- Canonical agents in the toolkit's frontmatter form are read by Claude Code; whether Cursor reads their `tools:` is unverified (BR-3).
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [x] What is the Copilot CLI plugin manifest's file name and schema? Resolved 2026-10-30: `.github/plugin/plugin.json` in the legacy format, install `copilot plugin install <path>`; see Assumptions. Copilot enters the set.
- [x] On Claude Code, does a git install need `marketplace.json`? Resolved by REQ-669: it ships one, and the route is `claude plugin marketplace add` then `claude plugin install`.
- [x] Which schemas allow redirecting the skills directory? Resolved 2026-10-30: Claude Code, Cursor and Copilot (legacy) yes; Gemini no. No RepoSkillsView is needed for the set, so the entity and BR-7's coverage of it are gone.
- [x] For a harness that pins by copying, does the copy preserve a committed relative symlink? Resolved 2026-10-30 for Gemini: no, by its source and a local Node 26 run (`verification.md`). Moot for Cursor and Copilot, which ship no symlink.
- [x] Should `adlc doctor` gain a per-harness report that a plugin-installed copy exists, names its pinned version against `VERSION`, and flags a doubled mount (BR-8)? Resolved: not here. BR-8 documents coexistence and per-harness precedence instead of a check; detection on any harness other than Claude Code stays Out of Scope.
- [x] Should `gemini-extension.json` set `contextFileName`? Moot: no Gemini manifest ships.

## Out of Scope

- Publishing to any marketplace or registry (Cursor's marketplace, a Copilot marketplace, a Gemini extension registry), and any generated release artifact, such as the branch or archive a pinned Gemini install would need; the manifests support local-path and git-URL installs only.
- `install.sh --migrate-home <dir>` and its `--back` inverse — the plan's P7b, a separate REQ.
- Authoring hook configuration, MCP servers, `AGENTS.md`/`GEMINI.md` context files, allowlist rendering — REQ-657 onward.
- Rendering agents into Gemini's or Copilot's formats — P2/P4.
- Codex: it has no plugin or extension manifest; its install stays the REQ-654 `~/.agents/skills` mount.
- Any change to SKILL.md text, to where skills or agents live, to `install.sh`, to `.claude-plugin/`, to `hooks/`, or to the REQ-654 mounts.
- Making a plugin install self-sufficient on Cursor or Copilot.
- Doctor checks for plugin installs, including REQ-658's rows and detecting or de-duplicating a doubled catalog (BR-8).
- Windows.

## Deferred

Owed, because `agent`, `copilot` and `gemini` are not on PATH on the verifier's machine and no `cursor.json`, `copilot.json` or `gemini.json` probe result exists. None was installed for this REQ.

- **BR-13 / AC-6 / AC-8 on Cursor:** a real install, confirming the harness accepts the empty values at all, `"skills": "./"` lists all 17 skills, `"agents": []` and `"hooks": {}` load nothing, the pin holds, the precedence against `~/.agents/skills`, how a plugin skill is named at invocation, and what happens when that name collides with a built-in command (LESSON-728). Whether Cursor's agent `tools:` handling lets a later REQ carry an agents reference (BR-3).
- **BR-13 / AC-6 / AC-8 on Copilot:** the same, including the empty values, invocation naming and built-in collisions, plus that `.github/plugin/plugin.json` wins over `.claude-plugin/plugin.json`, and whether a direct local-path install pins.
- **Root `CLAUDE.md`:** REQ-657 (108db1f) added it, and `claude plugin validate .claude-plugin/plugin.json --strict` has failed on it since, on `origin/main` too, which also fails `RELEASING.md` step 3. Moving it is REQ-657's surface, not this REQ's, so it is a follow-up fix.
- **Gemini:** a real install would confirm the source reading in Description. A pinned route needs a generated artifact (Out of Scope); REQ-658 decides its rows (BR-14).

## Retrieved Context

- REQ-610 (spec, score 8): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- REQ-519 (spec, score 8): One-Command Installer and `adlc doctor` Health Check
- LESSON-663 (lesson, score 7): To keep a model's shell inside a classifier's grammar, allowlist what it may run — forbidding commands one at a time never converges
- LESSON-662 (lesson, score 7): Some shell cannot be respelled past a provenance classifier — the skill text has to route around it
- LESSON-582 (lesson, score 7): bash 3.2 cannot parse a `case` statement inside `$( )` — the shell that rejects your script is the oldest one a user has, not the newest one CI runs
- REQ-652 (spec, score 6): A lite lane for minor changes
- BUG-230 (bug, score 6): /analyze Step 2 assumes an agent-dispatch tool Teton Code does not have, and Step 2a's hygiene shell would pin
- BUG-201 (bug, score 6): The forge classifier has no pattern for branch-protection merge refusals, so both backends report them as error_class=network
- BUG-204 (bug, score 6): /template-drift treats the toolkit working checkout as canonical without checking which branch it is on — a stale baseline inverts every verdict and proposes regressions
- LESSON-572 (lesson, score 6): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 6): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts
- LESSON-395 (lesson, score 6): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up
- REQ-522 (spec, score 6): De-brand the delegation surface and make skill telemetry single-fence-safe
- REQ-515 (spec, score 6): Provider-Agnostic Delegation Layer — de-Kimi the Tooling
- LESSON-335 (lesson, score 6): Four zsh-executor/templating hazards in SKILL.md scripts: bare $<digit>, [0] arrays, unmatched globs, status= assignments
