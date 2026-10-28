---
id: REQ-665
title: "Plugin manifests as an alternative install, kept in step by a manifest-parity lint"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/install"
domain: "adlc"
stack: ["json", "python", "markdown", "sh"]
concerns: ["portability", "harness-agnostic", "developer-experience", "lint"]
tags: ["plugin", "manifest", "install", "harness", "multi-harness", "lint-skills", "version", "symlink", "readme", "agents", "hooks", "mcp", "cursor", "gemini", "copilot", "claude-plugin", "parity"]
lane: "full"
lane_reason: "footprint far above max_files (four manifests, a new lint-skills check with fixtures and tests, README, project-overview, CHANGELOG) and it adds a second install surface for the toolkit's distribution"
lane_forced: false
---

## Description

This REQ adds plugin manifests at the clone root — `.claude-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `gemini-extension.json`, and a Copilot plugin
manifest once its schema is known (Open Question 1) — kept in step with the
skill set, the agent set and `VERSION` by a `manifest-parity` lint; the symlink
live install stays primary. It is P7a of
`.adlc/research/multi-harness-plan.md` (revision 2), the first half of the
plan's optional P7. Today the toolkit has exactly one install: a
symlink-based live install (`./install.sh` points `~/.claude/skills` and
`~/.claude/agents` at the clone; REQ-654 adds the `~/.agents/skills` mount for
the four non-Claude harnesses). That model is deliberate and stays primary: an
edit committed to the clone is visible to every session on the machine with no
publish step, and every skill's own fallbacks (the REQ-610 partial-sourcing
spelling, the installed-engine lookups, the `adlc` CLI shim) resolve through it.

What it cannot offer is a **pinned** install. Per the plan's §7 sources (Cursor `reference/plugins`, Gemini
`extensions/reference`, surveyed 2026-10-27; the §1 table carries no plugin
row — every packaging fact in this paragraph is unverified until BR-13),
three of the four target harnesses have a first-class plugin or extension
mechanism whose unit is a directory with a manifest at its root: Claude Code
reads `.claude-plugin/plugin.json`, Cursor
reads `.cursor-plugin/plugin.json` (default directories `skills/`, `rules/`,
`agents/`, `commands/`, `hooks/hooks.json`, `mcp.json`, each overridable from
the manifest; local testing through `~/.cursor/plugins/local`), Gemini CLI reads
`gemini-extension.json` (`name` and `version` required; `contextFileName`,
`mcpServers`; `commands/`, `skills/`, `agents/`, `hooks/hooks.json`, `policies/`
beside it; installed with `gemini extensions install <git-url|path>` or
`link <path>`), and Copilot CLI plugins bundle skills with a `hooks.json`. All
four read `SKILL.md` skills. A manifest lets a harness's **own** install command
fetch the toolkit at a git ref and load it as one unit: reproducible across a
team and updated only when someone says so.

This REQ adds those manifests at the clone root, each pointing at the toolkit's
**existing** skill directories (`<name>/SKILL.md` at the root, not under a
`skills/` directory — nothing moves) and, where the harness reads the format
as-is, at the canonical `agents/`. It adds a `manifest-parity` check to
`tools/lint-skills` so the manifests cannot drift from the skill set, the agent
set or `VERSION` (LESSON-012: a structural guard, not a prose promise), and a
short "install as a plugin" README section per harness that states the
trade-off honestly: a pinned copy versus the live clone, and what each harness
does and does not get from its plugin.

Ownership with REQ-658: this REQ owns `gemini-extension.json`, its version and
skill-set rules under `manifest-parity`, and the Gemini README subsection;
REQ-658 owns only the `gemini:extension` / `gemini:dual-install` doctor checks
and cites this REQ for the file.

Two facts about the repo shape the scope. First, as of the P0 baseline the
toolkit ships **no hook configuration and no MCP server** — the committed
settings files are permission allowlists. REQ-657 (before this REQ in plan
order) introduces the canonical `templates/hooks.yml`, which no harness reads,
plus per-harness hook renders; a manifest may reference only a render its
harness's plugin loader reads, and only if the file exists (BR-4) — a key
pointed at a placeholder file is a dangling reference that breaks the install
it exists to enable. No MCP server exists, so no manifest references one. Second, a plugin install is **not
self-sufficient**: a skill fence that finds no `.adlc/partials/<name>.sh` sources
`~/.claude/skills/partials/<name>.sh` (REQ-610 BR-3, kept by REQ-654 BR-3), the
lane-check and forge engines are looked up under the toolkit's home, and the
`adlc` CLI is a shim `install.sh` writes. Until the plan's P1 (`no-harness-path`)
makes skill text location-independent, the plugin is a pinned **catalog mount**
layered on a machine that has run `./install.sh`, and the README says exactly
that rather than implying a replacement. (informed by REQ-610, LESSON-441)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Manifest | harness | enum | the registry's entries — at minimum `claude` and `gemini`, plus `cursor` unless BR-2's symlink rule removes it; `copilot` only once Open Question 1 is answered — the set is defined in exactly one place (the lint's registry, BR-1/BR-7) and the README subsections follow it |
| Manifest | path | path | clone-root-relative: `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`; the Copilot path is absent until Open Question 1 is answered |
| Manifest | companions | list of paths | files the harness's documented unpublished-install route requires beside the manifest (e.g. a single-plugin `marketplace.json`); part of the registry entry, covered by BR-7(b), (d), (g) |
| Manifest | name | string | `adlc-toolkit` in every manifest; identical across the set |
| Manifest | version | string | byte-equal to the trimmed content of `VERSION` |
| Manifest | skills_ref | path or list | resolves to exactly the SkillSet; uses the schema's path override where one exists, otherwise the RepoSkillsView (architecture decision) |
| Manifest | agents_ref | path | present only for a harness that reads `agents/*.md` in its canonical form: Claude Code (plan §1); Cursor (plan §1) only if BR-13 confirms its `tools:` handling, otherwise omitted, with agents reaching Cursor through `~/.claude/agents` from the symlink install (REQ-656 ships no Cursor agent render, `paths.agents: via:claude`); absent for every other harness |
| Manifest | hooks_ref | path | present only when it names an existing, harness-readable hook render of REQ-657 bundled under the plugin's hooks path (BR-4); never `templates/hooks.yml`; never a placeholder |
| Manifest | mcp_ref | path | absent — the toolkit ships no MCP server (BR-4) |
| Manifest | content | JSON | stdlib-parseable; contains no absolute path, no `$HOME`, no user-specific value |
| SkillSet | entries | set of names | every directory `<name>` at the clone root holding a `SKILL.md`; `<name>` equals the file's `name:` field (today 17 skills) |
| AgentSet | entries | set of files | `agents/*.md` (today 19 agents) |
| RepoSkillsView | location | path | in-repo, committed, only where a manifest schema cannot redirect its skills directory; one entry per SkillSet member, no copies, no moved files; shape is an architecture decision |
| ParityFinding | rule | enum | `set-incomplete`, `unparseable`, `name-mismatch`, `version-mismatch`, `skill-missing`, `skill-extra`, `dangling-entry`, `agents-ref-invalid`, `path-missing`, `unknown-key` |
| ParityFinding | remediation | string | a copy-pasteable command or exact edit naming the file (REQ-519 BR-5, LESSON-572) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| manifest_parity_run | `bash tools/lint-skills/check.sh`, toolkit CI, pytest | one ParityFinding per violation; zero findings when no manifest of the set exists in the walked root (consumer repos) |
| version_bumped | a release commit changes `VERSION` | every manifest's `version` changes in the same commit, or the next lint run fails with `version-mismatch` |
| skill_added_or_removed | a `<name>/SKILL.md` appears or disappears at the clone root | every manifest or RepoSkillsView that enumerates skills changes in the same commit, or the next lint run fails with `skill-missing` / `dangling-entry` |

_Permissions: not applicable — repository files and a developer-machine lint. Section omitted deliberately._

## Business Rules

- [ ] BR-1: The toolkit ships one manifest per harness in the set at the clone root: today `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. The set is the harnesses whose plugin manifest schema is documented at architecture time — at minimum Claude Code and Gemini CLI, plus Cursor unless BR-2's symlink rule removes it — and is defined once, in the lint's registry (BR-7), and nowhere else. A harness whose schema is not yet known (Copilot, Open Question 1) is absent from the registry, gets no manifest, and gets a README subsection that says so; adding it later is one registry entry plus one file. Any companion file a harness's documented unpublished-install route requires (e.g. a single-plugin `marketplace.json`) is part of that harness's manifest entry in the registry and is covered by BR-7(b), (d) and (g). Every manifest is valid JSON that `python3 -m json.tool` accepts, carries `name: adlc-toolkit` and the `version` of BR-5, uses only keys its harness documents (BR-7(h) enforces it against the registry's documented-key list), and contains no absolute path, no `$HOME`, and no user- or machine-specific value, so the committed file is the file every installer reads. (informed by REQ-519)
- [ ] BR-2: Each manifest points at the toolkit's **existing** skill directories. No `SKILL.md` moves, no `SKILL.md` is edited, and no `skills/` directory of copies is added. Where a harness's manifest schema can redirect its skills directory, the manifest does so and names the root-level directories. Where a schema offers no override (Open Question 3), the repo gains a committed, in-repo RepoSkillsView that satisfies the expected directory with one entry per skill and no copies; its shape is an architecture decision, and it is covered by the parity lint exactly as the REQ-654 skills-only view is covered by doctor (every `*/SKILL.md` has an entry, no entry dangles). The REQ-654 view under `<adlc_home>` lives outside the clone and is therefore never what a manifest references. If BR-13 shows a harness's installer drops committed symlinks, that harness is removed from the registry for this REQ (BR-1's set rule) rather than served copies. (informed by REQ-654's plan Rule A, LESSON-441)
- [ ] BR-3: A manifest references the canonical `agents/` directory only for a harness that reads that format as-is (plan §1: Claude Code; Cursor reads `.claude/agents`-format definitions per plan §1, but its manifest carries the reference only if BR-13 confirms Cursor's `tools:` handling — otherwise it is omitted and the Cursor README subsection says agents reach Cursor through `~/.claude/agents` from the symlink install (REQ-656: Cursor needs no agent render, `paths.agents: via:claude`)). A harness that needs rendered agents (Gemini's own tool names, Copilot's `.agent.md`) gets no agents reference until the plan's P2/P4 renderer exists, and its README subsection says so. A manifest never points a harness at a format it cannot read, because a half-parsed agent definition is worse than none.
- [ ] BR-4: A manifest references a hooks or MCP file only if that file exists in the checkout at implementation time and is in the format the harness's plugin loader reads (Cursor `hooks/hooks.json`, Gemini `hooks/hooks.json`, Claude Code hooks per its plugin schema). The canonical `templates/hooks.yml` of REQ-657 is not harness-readable and is never referenced; whether REQ-657's per-harness hook renders are bundled into the plugin (a copy committed under the plugin's hooks path) or omitted is an architecture decision recorded in the README's what-does-not-load line; if a render is bundled, the plugin's hooks path is added to `lane_check.py` `DEFAULT_BLOCKED_PATHS` and pinned by test (REQ-657 BR-14 posture), and `render-parity` gains that copy as a surface. A Gemini extension `hooks/hooks.json` is a distinct render target, not a copy of the `.gemini/settings.json` render (REQ-658 renders Gemini hooks there); until a renderer produces that file, `gemini-extension.json` carries no hooks reference. No manifest key points at an empty or placeholder file; BR-7's `path-missing` rule enforces it. The toolkit ships no MCP server; no manifest references one.
- [ ] BR-5: `version` in every manifest equals the trimmed content of `VERSION`. A release that bumps `VERSION` updates every manifest in the same commit; whether the update is a hand edit or an `adlc` render in the `adlc agents render --check` mould is an architecture decision. What this REQ requires is that the lint (BR-7) fails on any drift, so a release cannot ship a plugin that announces the previous version. (informed by LESSON-019 — the version is read from `VERSION`, never hardcoded)
- [ ] BR-6: The symlink live install stays primary and documented as such. `install.sh` is not changed by this REQ; the README's Setup section still leads with the two-command symlink install; `~/.claude/skills`, `~/.claude/agents` and the REQ-654 mounts keep their targets. The README's new section is titled as an **alternative** and states, once per harness, that a plugin install pins what that harness loads but does not replace `./install.sh` on a machine that runs the skills, because the skills' own partial fallback (`~/.claude/skills/partials/`), the installed engines and the `adlc` CLI resolve through the symlink install. (informed by REQ-610 BR-3, LESSON-441)
- [ ] BR-7: `tools/lint-skills` gains a `manifest-parity` check, per-root in the mould of REQ-657's `sync-surface-parity` and `agent-model-drift` (stdlib only, LESSON-395). Rules, each a ParityFinding with a copy-pasteable remediation: (a) **set-incomplete** — every manifest named in the registry exists if any does; (b) **unparseable** — each is valid JSON; (c) **name-mismatch** — `name` is identical across the set; (d) **version-mismatch** — `version` equals `VERSION`; (e) **skill-missing / skill-extra / dangling-entry** — the skills a manifest or RepoSkillsView resolves to are exactly the SkillSet; (f) **agents-ref-invalid** — an agents reference, when present, resolves to `agents/`; (g) **path-missing** — every path any manifest or companion file references exists in the checkout; (h) **unknown-key** — a manifest carries only keys the registry lists as documented for its harness (BR-1). In a root with no manifest of the set the check yields zero findings, so it is inert in consumer repos; a lint run that scans zero files remains a failure (REQ-610 BR-12). The check runs from `check.sh` and is covered by pytest fixtures for every rule. (informed by REQ-610, REQ-519 BR-5, LESSON-572, LESSON-012)
- [ ] BR-8: Until the plan's P1 (`no-harness-path`) makes a plugin install self-sufficient, the plugin coexists with the symlink catalog mount on the same harness, and the README names the cost plainly: on that harness every toolkit skill is listed twice (once pinned, once live) and the harness's own precedence decides which copy answers a `/name` invocation; the README records that precedence per harness from the BR-13 verification. Detecting or de-duplicating the doubled catalog is Out of Scope (Open Question 5). On Gemini CLI the doubled state is the one REQ-658 BR-9's `gemini:dual-install` observes; that row reports (never FAILs) when the mount and an extension are both present, naming both paths and the precedence BR-13 recorded, because `./install.sh` (REQ-654 BR-5) recreates the mount on every run and BR-6 requires `./install.sh`; REQ-658 BR-9/BR-11/AC-10/AC-11 say "coexist, listed twice" in place of "alternatives".
- [ ] BR-9: The README gains a short "Install as a plugin (alternative)" section with one subsection per harness in the set. Each states: the harness's own install command for the clone (Cursor: copy (not symlink) the clone at a tag into `~/.cursor/plugins/local/adlc-toolkit`; update = re-copy; Gemini `gemini extensions install <git-url|path>`, with `gemini extensions link <path>` named as the live, unpinned option on that harness; Claude Code and Copilot per Open Questions 1 and 2); what loads (skills; agents where BR-3 permits); what does not (MCP, none; hooks unless BR-4's architecture decision bundles a render; agents where BR-3 forbids; the runtime of BR-6); the BR-8 coexistence note with that harness's verified precedence; how to update a pinned copy; and the trade-off in one sentence — a pinned copy is reproducible and changes only when you update it, and can therefore be behind the clone; the live clone shows every commit instantly and cannot be pinned. Marketplace publishing is not documented, because none is offered (Out of Scope). (plan §4: say what is lost per harness)
- [ ] BR-10: Nothing moves (plan Rule A). `git diff --stat` for this REQ touches no `<name>/SKILL.md`, no file under `agents/`, no `partials/`, no `install.sh`; `./install.sh` on a healthy machine still reports zero actions after the change; `readlink ~/.claude/skills` is unchanged. The manifests are additive files at the root and under two new dot-directories; the existing `.claude/` directory (settings, worktrees) is untouched.
- [ ] BR-11: New Python is stdlib only (LESSON-395). Any new or changed shell is POSIX-sh, bash 3.2, zsh and dash safe: no `case` inside `$( )`, no `\b` in `grep -E`, no bare `$<digit>`, no `[[`, no `local`, no `status` variable (informed by LESSON-582, LESSON-335, LESSON-013).
- [ ] BR-12: Documentation that states the install model is updated in the same change: `README.md` (BR-6, BR-9), `.adlc/context/project-overview.md` ("Install model": symlink primary, plugin manifests as the pinned alternative, no versioning claim left that the manifests contradict), `.adlc/context/architecture.md` (top-level layout gains the manifests and, if BR-2 needs it, the RepoSkillsView), `tools/lint-skills/README.md` (the new check and its rules), `CHANGELOG.md`. (informed by LESSON-019: the overview points at VERSION/CHANGELOG rather than re-enumerating)
- [ ] BR-13: Every claim the README makes about what a harness loads from the plugin is verified on a real install of that harness before the claim ships, or is marked unverified in the README citing the REQ-664 probe result for that harness (`.adlc/research/harness-probes/<harness>.json`) or its absence; the PR records which harnesses were exercised. A README that asserts "Gemini loads the agents" from reading docs alone is the plan's own anti-pattern. (informed by BUG-204 — a baseline nobody checked inverts every verdict)

## Acceptance Criteria

- [ ] AC-1: The manifest set exists at the clone root; each file passes `python3 -m json.tool`; `name` is `adlc-toolkit` in every one; each `version` equals `cat VERSION`; `grep -n '/Users\|/home\|\$HOME' <manifests>` returns nothing. (BR-1, BR-5)
- [ ] AC-2: `bash tools/lint-skills/check.sh` is clean on the checkout. In a sandbox copy, adding `zzz-test/SKILL.md` makes `manifest-parity` fire `skill-missing` naming the skill and each manifest or view that lacks it, with a remediation; applying the remediation verbatim returns it to clean. Removing a skill directory while a manifest or view still names it fires `dangling-entry`. (BR-2, BR-7)
- [ ] AC-3: In a sandbox copy, changing `VERSION` to `9.9.9` makes the lint fire one `version-mismatch` per manifest naming the file and the expected value; restoring `VERSION` (or updating the manifests) returns it to clean. (BR-5, BR-7)
- [ ] AC-4: Deleting one manifest from the sandbox copy fires `set-incomplete`; deleting every manifest yields zero findings from the check, and a consumer-repo fixture that never had manifests scans clean. Pointing any manifest key at a path that does not exist fires `path-missing`; so does a missing companion file named in the registry. (BR-1, BR-4, BR-7)
- [ ] AC-5: `pytest tools/lint-skills/tests` passes with a fixture per BR-7 rule; `check.sh`'s exit-code contract is unchanged, including `255` for a vacuous scan. (BR-7, BR-11)
- [ ] AC-6: On Claude Code, installing the clone through the README's Claude Code install command lists every toolkit skill and every agent from the plugin; on Cursor, installing by copying the clone into `~/.cursor/plugins/local/adlc-toolkit` lists every toolkit skill and, if BR-13 confirmed the `tools:` handling, every agent. In both, with `./install.sh` also run, the catalog shows each skill twice and the README's precedence note for that harness matches what the harness actually invokes. (BR-3, BR-8, BR-13)
- [ ] AC-7: On Gemini CLI, `gemini extensions install <clone>` and `gemini extensions link <clone>` each list every toolkit skill and no agents, and the README's Gemini subsection says agents are not loaded. For any harness in the set whose binary is not available to the verifier, the README marks that subsection unverified citing the REQ-664 probe result or its absence, and the PR says so. (BR-3, BR-9, BR-13)
- [ ] AC-8: On each harness in the registry whose install route pins — Claude Code through the README's install command, Cursor through the copied `~/.cursor/plugins/local/adlc-toolkit`, Gemini CLI through `gemini extensions install` (not `link`, which is live) — with the plugin installed at a git ref, committing a throwaway skill to the clone does not change that harness's plugin catalog until its update command runs, while the symlink install on the same machine shows the new skill immediately; the README subsection's update step, run verbatim, brings the pinned copy forward (on Gemini, `adlc doctor` reports, and does not FAIL, `gemini:dual-install` in this state). (BR-6, BR-8, BR-9)
- [ ] AC-9: `git diff --stat <base>..HEAD` for the REQ shows no change to any `*/SKILL.md`, `agents/*`, `partials/*` or `install.sh`; `./install.sh` on a healthy machine reports zero actions; `readlink ~/.claude/skills` and `readlink ~/.claude/agents` are unchanged. (BR-10)
- [ ] AC-10: `README.md` has an "Install as a plugin" section with one subsection per harness in the set, each containing an install command, a what-loads line, a what-does-not line that names the BR-6 runtime dependency, a BR-8 coexistence note recording that harness's precedence, an update step, and the one-sentence trade-off; the Setup section still opens with the two-command symlink install, and no sentence in the README calls the plugin a replacement for `./install.sh`. (BR-6, BR-8, BR-9)
- [ ] AC-11: `.adlc/context/project-overview.md` "Install model", `.adlc/context/architecture.md`'s layout, `tools/lint-skills/README.md` and `CHANGELOG.md` carry the new surfaces; the overview no longer states that there is no versioning at the install layer without qualifying it with the pinned alternative. (BR-12)
- [ ] AC-12: In a sandbox copy, adding a key the registry does not list for that harness (e.g. `"adlcExtra": true`) to any one manifest makes `manifest-parity` fire `unknown-key` naming the file and the key, with a remediation that removes it; the pytest fixture set includes one such manifest per harness in the registry, and every committed manifest passes. (BR-1, BR-7)

## External Dependencies

- None new to the toolchain. The harness binaries (`claude`, `agent`, `gemini`, `copilot`) are used only to verify BR-13 on a real install; none is required to build, lint or test. `python3` (stdlib) for the lint.
- REQ-657 (ships before this REQ: its per-harness hook renders are the only hook source BR-4 may name), REQ-664 (the probe results BR-13 cites), REQ-658 (owns the `gemini:extension` / `gemini:dual-install` doctor rows), REQ-654 (the `~/.agents/skills` mount the plugin coexists with), REQ-656 (establishes that Cursor reads `~/.claude/agents` natively and ships no Cursor agent render, which is why BR-3's Cursor agents reference is conditional on BR-13 rather than on a render).

## Assumptions

- The packaging facts are those of the plan's §7 sources (Cursor `reference/plugins`, Gemini `extensions/reference`) surveyed 2026-10-27, unverified until BR-13; the plan's §1 table carries no plugin row: Claude Code `.claude-plugin/plugin.json`; Cursor `.cursor-plugin/plugin.json` with overridable default directories and `~/.cursor/plugins/local` for local testing; Gemini `gemini-extension.json` with `name` and `version` required and `install`/`link` subcommands; Copilot CLI plugins bundling skills and a `hooks.json`. A schema change on any harness after that date is re-verified at architecture time (BR-13).
- REQ-657 has shipped before this REQ (plan order); its hook renders exist and are the only hook source a manifest may name (BR-4). The toolkit ships no MCP server.
- Claude Code and Cursor read `agents/*.md` in the toolkit's canonical frontmatter form; Gemini CLI and Copilot CLI do not (plan §1, §2g). The Cursor claim is verified under BR-13 before the README states it or a manifest carries the reference (BR-3).
- The plugin name `adlc-toolkit` is acceptable on every harness and does not collide with a reserved or marketplace name.
- The REQ-654 skills-only view under `<adlc_home>` is outside the clone and plays no part here; any in-repo RepoSkillsView BR-2 needs is a separate, committed artifact.
- A git-based plugin install fetches the whole clone (tools, partials, `.adlc/`), and that is acceptable: the manifest enumerates what the harness loads, so the extra directories cost disk, not catalog budget.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] What is the Copilot CLI plugin manifest's file name and schema? The grounding says only that Copilot plugins bundle skills and a `hooks.json`; which file declares the plugin's name, version and skill paths, and what is the install command? Until answered the Copilot manifest cannot be written and the README subsection cannot name a command; the lint's manifest set is defined in one place so adding it is one entry. Not blocking: BR-1's set excludes Copilot until answered.
- [ ] On Claude Code, does installing from a git URL require a `.claude-plugin/marketplace.json` alongside `plugin.json` (a self-hosted single-plugin marketplace), or is a local-path route (`--plugin-dir <clone>` or equivalent) the documented install for an unpublished plugin? The README's Claude Code command and AC-6 depend on the answer. Proposed: ship whichever the Claude Code docs document for an unpublished plugin; a `marketplace.json` that lists the toolkit as its only plugin is in scope if it is the only route.
- [ ] Which of the four manifest schemas allow redirecting the skills directory to the clone root's `<name>/` directories (Cursor: yes per the survey; Claude Code `plugin.json`, Gemini, Copilot: unknown)? This decides for which harnesses BR-2's in-repo RepoSkillsView is needed at all; the Gemini extension-layout half of this question is this REQ's, not REQ-658's.
- [ ] For a harness that pins by copying rather than by `git clone`, does the copy preserve a committed relative symlink, dereference it (acceptable), or drop it (not acceptable)? Decides whether BR-2's RepoSkillsView may be symlink-shaped; to be answered on a real install under BR-13, and a harness that drops symlinks leaves the registry (BR-2). Cursor's schema redirect (Open Question 3: yes per the survey) means the symlink question applies to Cursor only if that override fails on a real install — with the override working, Cursor's manifest names the root-level directories and no RepoSkillsView, symlink-shaped or otherwise, is ever copied.
- [x] Should `adlc doctor` gain a per-harness report that a plugin-installed copy exists, names its pinned version against `VERSION`, and flags a doubled mount (BR-8)? Resolved: not here. BR-8 documents coexistence and per-harness precedence instead of a check; REQ-658 BR-9's `gemini:extension` / `gemini:dual-install` are the only doctor rows and are REQ-658's, with `gemini:dual-install` a report row per BR-8; detection on any other harness stays Out of Scope.
- [x] Should `gemini-extension.json` set `contextFileName`, given the clone has no `GEMINI.md` and `AGENTS.md` canonicalisation is P2? Resolved: omit it. Context files are Out of Scope here and `context.fileName` is REQ-658's render; an extension without a context file is valid.

## Out of Scope

- Publishing to any marketplace or registry (Cursor's marketplace, a Claude Code marketplace listing, a Gemini extension registry); the manifests support local-path and git-URL installs only.
- `install.sh --migrate-home <dir>` and its `--back` inverse — the plan's P7b, a separate REQ.
- Authoring hook configuration, MCP servers, `AGENTS.md`/`GEMINI.md` context files, allowlist rendering — REQ-657 onward; this REQ authors none of them and at most bundles REQ-657's existing per-harness hook renders (BR-4).
- Rendering agents into Gemini's or Copilot's formats — P2/P4.
- Codex: it has no plugin or extension manifest; its install stays the REQ-654 `~/.agents/skills` mount.
- Any change to SKILL.md text, to where skills or agents live, to `install.sh`, or to the REQ-654 mounts.
- Making a plugin install self-sufficient (skill fences and engine lookups that do not depend on `~/.claude/skills`) — the plan's P1 `no-harness-path` work and later.
- Doctor checks for plugin installs, including detecting or de-duplicating a doubled catalog (BR-8, Open Question 5); REQ-658 BR-9's `gemini:extension` / `gemini:dual-install` rows are REQ-658's.
- Windows.

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
