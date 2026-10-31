# ADLC Toolkit

Skills, agents, and templates for spec-driven development with [Claude Code](https://claude.com/claude-code). Stack-agnostic at the core, with optional preset configs for common stacks (iOS+Firebase+Cloud Run, etc.).

## Install

Two commands, run in your own terminal:

```bash
claude plugin marketplace add atelier-fashion/adlc-toolkit
claude plugin install adlc@adlc-toolkit
```

This repo is both the marketplace (`adlc-toolkit`) and the plugin (`adlc`). Start a new Claude Code session after installing. On this route every skill is namespaced: type `/adlc:<skill>`, for example `/adlc:init`, `/adlc:spec` or `/adlc:proceed`. The toolkit's agents are registered as `adlc:<name>`. The skill table below uses the bare names; add the `adlc:` prefix on the plugin route.

The plugin's version is pinned to this repo's `VERSION`, so it changes only when a release is cut, not on every merge; you get a new release when you update (see [Updating](#updating)). Contributors and the maintainer use a symlink live install instead, described under [Contributing and live install](#contributing-and-live-install). Use one route per machine, not both (see [Known limitations](#known-limitations)).

**Did it work?** `adlc doctor` checks every dependency end to end and prints a copy-pasteable fix for anything that fails. On the plugin route, run it by path from any terminal once a Claude Code session has started (the session's start hook writes the pointer file this line reads):

```bash
"$(cat ~/.claude/adlc/plugin-root)/scripts/adlc" doctor
```

Inside a Claude Code session the same hook also appends the plugin's `scripts/` directory to the shell's PATH, so skills can run plain `adlc` (see the loader table below for how far that is verified).

On the plugin route, the four checks that inspect the symlink install (`skills-symlink`, `agents-symlink`, `toolkit-clean`, `path-shims`) print SKIP with a notice. Two checks cover the routes themselves:

- **`plugin-route`** reports which route the doctor runs on and its version. On the plugin route it checks that this is the copy Claude Code loads, that `~/.claude/adlc/plugin-root` names it, and that `scripts/adlc` is executable and, inside a Claude Code session, on PATH. Its fixes re-run what the hook does (`CLAUDE_PLUGIN_ROOT='<root>' sh '<root>/scripts/session-start.sh'`, or just start a new session), `chmod +x '<root>/scripts/adlc'`, or reinstall (`claude plugin uninstall adlc@adlc-toolkit && claude plugin install adlc@adlc-toolkit`). When the doctor cannot read the install record, it fails and points at `claude plugin details adlc`.
- **`doubled-install`** fails when the symlink install and the plugin are both installed. It prints one fix for each way out: `claude plugin uninstall adlc@adlc-toolkit` keeps the symlink install, and an `rm` of the `~/.claude/skills` and `~/.claude/agents` links (plus `~/bin/adlc` when it runs the clone) keeps the plugin. The `rm` removes the links, not the clone.

See [`tools/adlc/README.md`](tools/adlc/README.md) for the full check list.

### What the plugin runs and writes

This paragraph is for anyone reviewing what the plugin does to a machine, including the Claude directory's security scan. The plugin registers one hook, in [`hooks/hooks.json`](hooks/hooks.json). At session start Claude Code runs `sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"`. [`scripts/session-start.sh`](scripts/session-start.sh) is POSIX `sh`. It uses no network and no Python. It writes nothing until `CLAUDE_PLUGIN_ROOT` passes a check: the path must be absolute, must hold no newline, `..` or shell metacharacter, and must contain a `.claude-plugin/plugin.json` naming `adlc` and a `partials/` directory. Then it does three things:

1. **Pointer file.** It writes the plugin root, one line, to `~/.claude/adlc/plugin-root`. The write goes through a temp file and `mv`, and happens only when the content changed. Skill text that Claude Code did not substitute reads this file to find the plugin (the third arm of the ToolkitRoot line, see `.adlc/context/architecture.md`).
2. **Config scaffold.** It writes `~/.claude/adlc/config.yml` only when nothing exists at that path. The file sets `delegate: enabled: false`, so installing the plugin never turns delegation on. Its bytes are identical to the scaffold `install.sh` writes, and a test pins the two copies equal. That is why its comment says "scaffolded by install.sh" and suggests `./install.sh --with-delegation`. On the plugin route, ignore that line. The plugin does not ship the delegation CLIs, and `install.sh` run from the plugin's copy would link that copy into `~/.claude` and double the install. `adlc doctor` on the plugin route never prints `install.sh` as a fix: its `pyyaml` and `delegate-gate` checks print a pinned `pip install` and a config edit instead. To use delegation, install by the symlink route with `./install.sh --with-delegation`.
3. **PATH line.** When Claude Code provides `CLAUDE_ENV_FILE`, the session's environment file, the hook appends one marked line, `export PATH="$PATH:<plugin root>/scripts" # adlc-plugin-path`, and only once. The plugin's directory goes after your own PATH, so a `~/bin/adlc` you already have still wins. [`scripts/adlc`](scripts/adlc) is a POSIX shim that runs `python3 <plugin root>/tools/adlc/adlc.py`. That CLI uses only the Python standard library.

The hook writes nothing else. It writes nothing into the plugin cache, and it edits no shell rc file, no `settings.json` and no `CLAUDE.md`. Every path exits 0, nothing goes to stdout, and at most one `adlc:` line goes to stderr, so a hook problem never costs you the session. The skills themselves keep machine state where the symlink install keeps it, shared by both routes. That covers the id counters `~/.claude/.global-next-{req,bug,lesson}`, their lock directories, the reservations ledger `~/.claude/.adlc-own-reservations`, and the telemetry log `~/Library/Logs/adlc-skill-telemetry.log`. Their commands run through Claude Code's Bash tool under your permission settings.

### Loader behavior, and what is verified

The plugin's design rests on how Claude Code loads plugins. A claim marked **verified** was observed directly on a real install of **Claude Code 2.1.258** on 2026-10-28, using sandbox `HOME`s. Anything else is marked **unverified**, including behavior seen only in the shell Claude Code runs a skill's `!` lines in, which is a proxy for the Bash tool and not the same thing. The full record is [`.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md`](.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md).

| Claim | Status |
|---|---|
| `"skills": "./"` in `plugin.json` exposes all 17 root-level `<skill>/SKILL.md` directories | verified, 2.1.258 |
| With no `agents` field, the default `agents/` scan exposes all 19 agents | verified, 2.1.258 |
| `claude plugin validate . --strict` passes. `claude plugin validate .claude-plugin/plugin.json` passes with one warning, about the root `CLAUDE.md`, so its `--strict` form fails | verified, 2.1.258 |
| An install copies the plugin to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, with no `.git`. Earlier versions stay on disk after `claude plugin update` | verified, 2.1.258, through a git marketplace (the clone-then-cache path a GitHub source takes). The two commands above against this GitHub repo are **unverified** until the first release check |
| `${CLAUDE_PLUGIN_ROOT}` is substituted in skill text: prose, fenced shell and `!` lines, before a `!` line runs. The `${CLAUDE_PLUGIN_ROOT:-…}` default form is **not** substituted | verified, 2.1.258 |
| `${CLAUDE_PLUGIN_ROOT}` is substituted in an agent body | **unverified** (needs a model turn) |
| A file read through the Read tool is not substituted | **unverified**. On 2.1.258 the install was seen not to rewrite files, but no Read tool call was made |
| `CLAUDE_PLUGIN_ROOT` is not set in the Bash tool's environment | **unverified**. On 2.1.258 it was empty in the shell that runs `!` lines; a model-issued Bash tool call was not made |
| The plugin's SessionStart hook runs and receives `CLAUDE_ENV_FILE` | verified, 2.1.258, at `claude -p` startup. Interactive sessions and the resume, clear and compact starts are **unverified** |
| The hook's PATH line reaches the Bash tool, so plain `adlc` resolves | **unverified**. On 2.1.258 it reached the shell that runs `!` lines; a model-issued Bash tool call was not made. Running `scripts/adlc` by path, as above, does not depend on it |
| A typed bare `/<skill>` reaches the plugin skill when nothing else owns that name | verified, 2.1.258, on a plugin-only `HOME`. The Skill tool given a bare name is **unverified**. Names Claude Code's own commands own were not measured, which is why this README prints `/adlc:<skill>` |
| Plugin agents are registered as `adlc:<name>`, and a bare or unknown name on the fork path silently becomes a generic agent | verified, 2.1.258 |
| The Agent tool's `subagent_type` and the Workflow tool's `agentType` take `adlc:<name>` | **unverified** (needs a model turn) |
| A local-path marketplace (`claude plugin marketplace add ./` from a clone) runs the plugin from the source directory, not the cache | verified, 2.1.258 |
| A Claude directory install goes through the claude.ai sync path that rejects a top-level `bin/` | **unverified**. The plugin ships no top-level `bin/`, so either answer works |

### Known limitations

- **Agent dispatch spelling.** Whether the Agent tool's `subagent_type` and the Workflow tool's `agentType` accept `adlc:<name>` has not been probed. The `/sprint` workflow engine prefixes agent names with `adlc:` on the plugin route, inferred from the agent registry. Every skill that dispatches an agent says to use the spelling the Agent tool lists and, when neither spelling is listed, to name the missing agent and run its checklist inline from the agent file. A wrong spelling does not fail loudly.
- **Skill names Claude Code also owns.** Skill text prints bare next steps such as "run `/validate`", and on a plugin-only machine a typed bare name reached the plugin skill in the probe. Three skill names are Claude Code's own as well. `/init` and `/status` are built-in commands, and `/review` is an alias of the bundled `code-review` skill. The Claude Code 2.1.258 binary resolves a bare name to an exact command-name match first, so on the plugin route a bare `/init` runs Claude Code's CLAUDE.md generator, not this toolkit's `/init` (read from the binary; a typed command was not measured). Wherever skill text tells you to run one of these three, it prints both spellings on the same line, such as "`/init` (`/adlc:init` on the plugin install)". On the plugin route, type the `/adlc:` spelling. The `tools/lint-skills` `builtin-collision` check fails a bare instruction for any of the three, so the text stays that way. Which command a bare `/review` reaches on the plugin route depends on Claude Code's command order and is **unverified**. The other skill names are not Claude Code commands, and their bare spelling works on both routes.
- **PyYAML.** The ADLC config is parsed with PyYAML, which a fresh Mac's system `python3` lacks. On a plugin-only machine that is not a failure for the setup the plugin leaves you with: when there is no delegate venv and no project `.adlc/config.yml`, and the machine config is byte for byte the delegation-off scaffold the hook writes, the doctor's `pyyaml` check SKIPs, because read without PyYAML that file sets nothing. A project config or an edited machine config makes the check live, and on such a `python3` it then FAILs. The printed fix is a pinned `pip install --user` for that interpreter. Until it is installed, a `forge.provider` written in a config is not read, and the provider comes from the origin URL instead.
- **A disabled plugin still counts.** The doctor reads `~/.claude/plugins/installed_plugins.json` and the plugin cache, not `enabledPlugins` in `~/.claude/settings.json`. A plugin disabled there still counts as installed, so `doubled-install` can report a doubling that Claude Code is not loading.
- **Both routes at once.** With the symlink install and the plugin both active, bare `/spec` reaches the symlink copy and `/adlc:spec` the plugin, per the Claude Code skills docs (**unverified**: not measured on a doubled machine). The `doubled-install` check above reports it, with a fix for each way out.
- **Delegation** is not part of the plugin route (see the config scaffold above).

## What's Included

### Skills

| Skill | Description |
|-------|-------------|
| `/init` | Bootstrap `.adlc/` structure in a new repo |
| `/spec` | Write requirement specs from feature requests. Pass `--intake` (or a source file path, or over 25 lines of input) to run **intake** on unstructured material — a transcript, meeting notes, a ticket dump — producing a draft REQ plus an explicit gap list naming what the source does not answer (REQ-594). Triages every request into the **lite** or **full** lane and records why; `--lite` / `--full` force it (REQ-652) |
| `/architect` | Design architecture and break requirements into tasks |
| `/validate` | Validate any ADLC phase output before advancing |
| `/proceed` | End-to-end pipeline: validate → architect → implement → reflect → review → PR → wrapup. Opens a draft PR early and trial-merge-gates the merge to enforce ordering (REQ-483). On a **lite** REQ it skips validation, architecture and tasks, reviews with one `lite-reviewer` pass, and runs a mechanical lane check of the diff that escalates to the full lane when the change crosses a line; `--full` escalates by hand (REQ-652) |
| `/sprint` | Parallel pipeline orchestrator — launch multiple `/proceed` sessions across REQs. Has a workflow engine (`--workflow`, the deterministic `adlc-sprint` Dynamic Workflows script that restores per-REQ fan-out while keeping cross-REQ concurrency) with the legacy background-runner engine as an always-available fallback. The workflow engine runs lite-lane REQs on the full lane and logs that it did |
| `/reflect` | Post-implementation self-review before formal review |
| `/review` | Multi-agent code review (correctness, quality, architecture, tests, security) |
| `/adversary` | Adversarial review of any artifact (spec, plan, diff/PR, README, or prose claim) — assumes it is wrong and tries to prove it, then reports only findings that survive self-refutation. Read-only; hunts omissions, not just bugs in what was written |
| `/canary` | Canary deployment with smoke tests — deploy zero-traffic revision and promote on success |
| `/wrapup` | Close out a feature — commit, merge, deploy, update artifacts |
| `/bugfix` | Streamlined bug fix workflow |
| `/status` | Show current state of all ADLC work, including each REQ's lane and any escalations |
| `/manifest` | Remote-derived view of all in-flight ADLC work — open PRs + pushed `feat/REQ-*` branches, with advisory component/domain + file-footprint overlap and a deterministic merge order (REQ-483) |
| `/analyze` | Codebase health audit |
| `/optimize` | API cost & performance scanner |
| `/template-drift` | Detect drift between the copies `/init` vendored into a project's `.adlc/` (templates, partials, agent checklists, ETHOS, workflow runtime) and the canonical toolkit copies. On the plugin route it names the plugin version it compares against (`adlc plugin <version>`) |

On the plugin route each skill is `/adlc:<skill>`.

### Templates

- `requirement-template.md` — Requirement spec template
- `task-template.md` — Technical task template
- `bug-template.md` — Bug report template
- `assumption-template.md` — Validated-assumption knowledge entry
- `lesson-template.md` — Lesson-learned knowledge entry
- `taxonomy-template.md` — Tag/taxonomy reference for retrieval tagging

See [`templates/`](templates/) for the authoritative set (also includes the non-`.md` `config-template.yml`, and `permissions.yml` and `hooks.yml`, the semantic allowlist and hook set `adlc harness render` turns into each harness's project settings).

### Presets

Stack-shaped starter configs that seed `.adlc/config.yml` for common stacks. See [`presets/`](presets/) for the current list.

### Workflows

Deterministic Dynamic-Workflow scripts + the JSON-Schema literals they validate agent output against. See [`workflows/`](workflows/README.md). They are read from the installed toolkit on either route and vendored into a consumer's `.adlc/workflows/` by `/init`, with the same two-level path resolution as `templates/` and `partials/`.

### Tools

Standalone command-line utilities (not skills). See:

- [`tools/adlc/`](tools/adlc/README.md) — the `adlc` umbrella CLI. Its first subcommand, `adlc doctor`, is a read-only health check that diagnoses every install dependency and prints a copy-pasteable fix for each failure. On the plugin route the SessionStart hook puts [`scripts/adlc`](scripts/adlc) on the session's PATH; on the symlink route the root [`install.sh`](#symlink-install) writes `~/bin/adlc`.
- [`tools/delegate/`](tools/delegate/README.md) — provider-agnostic delegation CLIs (`adlc-read`, `adlc-write`, `extract-chat`) for offloading token-heavy I/O. **Off by default.** Symlink route only: opt in with `./install.sh --with-delegation`.
- [`tools/dataset/`](tools/dataset/README.md) — Dataset export. A maintainer tool that exports this repo's own `.adlc/` artifacts, scrubbed, as a Hugging Face dataset. Publishing is a separate step the maintainer runs after reading the export's report.

## How it works

The toolkit is split into two layers:

1. **The toolkit** (this repo) — generic skills, agents, and templates that work for any stack. It reaches Claude Code by one of two routes: the plugin, a pinned copy under `~/.claude/plugins/cache/`, or the symlink install, this clone linked at `~/.claude/skills/`. Either way every Claude Code session on the machine sees it. One skill text serves both routes: a skill finds the toolkit's own files through one variable, `$ADLC_TOOLKIT_ROOT`, set by a canonical line at the top of each shell block.
2. **Per-project `.adlc/` directory** — lives in each code repo. Holds the project's specs, architecture, conventions, and a `config.yml` that declares the project's stack, deploy targets, and repo layout. **All project-specific values live here**, never in the toolkit.

Skills read `.adlc/config.yml` at runtime to resolve project-specific things (GCP project IDs, iOS device names, Cloud Run service names, etc.) — nothing is hardcoded in the skills themselves.

## Setup

### Initialize a project

In any code repo:

```bash
claude
> /adlc:init        # plugin route; /init on the symlink route
```

This bootstraps the `.adlc/` directory with project-specific context, specs, and copies of the templates, partials and workflow engine.

### Configure for your stack

Pick a preset that matches your stack and copy it to `.adlc/config.yml`. The presets live in the installed toolkit, whose root depends on the route:

```bash
ADLC_TOOLKIT_ROOT="$(cat ~/.claude/adlc/plugin-root)"   # plugin route, after a session has started
# ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"              # symlink route
ls "$ADLC_TOOLKIT_ROOT/presets/"
cp "$ADLC_TOOLKIT_ROOT/presets/ios-firebase-cloudrun.yml" .adlc/config.yml
$EDITOR .adlc/config.yml  # replace every <placeholder> with a real value
```

[`presets/README.md`](presets/README.md) has the one-line resolver that works on both routes. If no preset matches, copy the bare template instead and fill it out from scratch:

```bash
cp "$ADLC_TOOLKIT_ROOT/templates/config-template.yml" .adlc/config.yml
```

Single-repo projects without a backend can leave the file absent — every skill falls back to legacy single-repo behavior in that case.

## Workflow

```
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup
```

For bugs: `/bugfix` (report → analyze → fix → verify → ship)

For multi-REQ batches: `/sprint` (parallel `/proceed` runners)

On the plugin route, prefix each with `adlc:` (`/adlc:spec`, `/adlc:proceed`, …).

## Project Structure

After `/init`, each code repo will have:

```
.adlc/
  config.yml         # Project's stack, deploy config, and (optional) sibling repo layout
  context/           # Project-specific architecture, conventions, overview
  specs/             # Requirement docs, architecture docs, tasks
  knowledge/         # Assumptions validated, lessons learned
  templates/         # Copies of templates (from this toolkit)
  partials/          # Copies of the shared shell partials (from this toolkit)
  workflows/         # Copies of Dynamic Workflow scripts + schemas (from this toolkit)
```

The toolkit repo contains the **process** (skills + templates). Each code repo contains the **artifacts** (specs, architecture, knowledge).

## Cross-Repo REQs

Some features span multiple repos (e.g., a feature that touches a backend API, a web frontend, and a mobile app at the same time). The toolkit supports these via the optional `repos:` block in `.adlc/config.yml`.

### Key concept: "primary" is per-REQ

There is no fixed "primary repo." Whichever repo you invoke `/proceed` (or `/bugfix`) from becomes the primary for that REQ — it holds the spec, tasks, and `pipeline-state.json` for that work. A different REQ that originates in a sibling repo makes that sibling the primary. Every repo that may originate REQs gets its own `.adlc/` structure and its own `config.yml`; the configs are **mirror images** of each other (each repo marks itself `primary: true` and lists the others as siblings).

### config.yml shape

```yaml
repos:
  api:
    primary: true       # only in this repo's config
  infrastructure:
    path: ../infrastructure
  app:
    path: ../app
  web:
    path: ../web

merge_order:            # default Phase 8 merge sequence
  - infrastructure
  - api
  - app
  - web

services:               # consumed by /canary, keyed by repo id
  api:
    cloud_run_service: api
    region: us-central1
    image_path: us-central1-docker.pkg.dev/<gcp-project>/api/api
  # (infrastructure has no service entry — it deploys via Terraform)
```

See [`templates/config-template.yml`](templates/config-template.yml) for the full annotated template (including `project:`, `stack:`, `gcp:`, and `ios:` sections).

### What changes when cross-repo is configured

- `/proceed` creates a worktree in every touched sibling, routes tasks by `repo:` frontmatter, opens one PR per repo, and merges in `merge_order`
- `/architect` requires a `repo:` field on every task it generates
- `/validate` checks that `repo:` values resolve to configured repo ids and that task files stay in their declared repo
- `/wrapup` walks `mergeOrder` to land PRs in order and cleans up worktrees across every touched repo
- `/canary` resolves service metadata from `services:` instead of a hardcoded table
- `/status` reports cross-repo activity (REQs originating elsewhere that touch this repo)
- `/sprint` delegates cross-repo mechanics to each `/proceed`; one sprint still originates all REQs from the invoking repo
- `/bugfix` supports cross-repo bugs via `repo:` or `touched_repos:` on the bug frontmatter

### Single-repo mode (default)

If no `config.yml` exists or it has only a single `repos:` entry, every skill falls back to legacy single-repo behavior. Existing projects are unaffected until they opt in by creating `config.yml`.

## Stack support

The toolkit's workflow is stack-agnostic. Skills that need to do stack-specific things (deploy a Cloud Run service, push a build to an iOS device, etc.) read `.adlc/config.yml` to learn what your stack is and what concrete values to use.

| Capability | Where the skill checks | What you fill in |
|---|---|---|
| Integration branch (`/proceed`, `/sprint`, `/bugfix`, `/wrapup`, `/template-drift`) | `branches.integration` | the branch feature branches are cut from and PRs target — `dev`, `staging`, `main`, … |
| Deploy confirmation (`/bugfix`, `/wrapup`) | `stack.backends` includes `cloud-run` | `gcp.staging_project`, `gcp.production_project` |
| Canary deploys (`/canary`) | `services:` block | service name, region, image path per repo |
| iOS device deploys (`/bugfix`, `/wrapup`) | `stack.frontends` includes `ios` | `ios.deploy_targets`, `ios.deploy_command` |
| Convention checking (`/review`, `/reflect`) | `.adlc/context/conventions.md` | declare your project's naming, logging, and API conventions |
| Lite-lane limits (`/proceed`, `/spec`) | `lanes.lite` | `max_files`; globs added to the default `blocked_paths` and `count_exclude`; and a `deploy_units` glob → unit map, for the lane check (`partials/lane-check.md`) |

`branches.integration` is optional. When it is declared, `/proceed` step 4 takes it as the integration branch outright; when it is absent, the skills detect the branch model as before — a declared `gcp.staging_project`, a `verify-head-ref` workflow, or staging-first wording in `CLAUDE.md` means `staging`, otherwise `main`. Set it whenever that detection would pick the wrong branch, e.g. a `dev` → `staging` → `main` promotion pipeline, where feature work integrates into `dev` although a staging project is declared. Repos without the key behave exactly as before.

If you want to add support for a new stack (e.g., AWS Lambda backends, Android device deploys), edit the relevant skill to handle the new `stack.*` value and document it in [`templates/config-template.yml`](templates/config-template.yml). PRs welcome.

## Updating

**Plugin route.** A new version reaches you when a release is tagged and you update:

```bash
claude plugin marketplace update adlc-toolkit
claude plugin update adlc@adlc-toolkit
```

Restart Claude Code to load it. The steps behind a release are in [`RELEASING.md`](RELEASING.md).

**Symlink route.** Pull the clone. This command works only on the symlink route, where `~/.claude/skills` is a link to the clone:

```bash
git -C "$(readlink ~/.claude/skills)" pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.

On either route, the copies `/init` vendored into each project's `.adlc/` do not update themselves. Run `/template-drift` (`/adlc:template-drift` on the plugin route) in a project to see which are stale, and re-run `/init` (`/adlc:init` on the plugin install) to refresh them.

## Contributing and live install

This is published as a generic toolkit you can fork or contribute back to. Patches that add presets, support new stacks, or sharpen workflows for stacks already supported are all welcome.

Contributors and the maintainer run the toolkit from a git clone with a **symlink-based live install**. There is one clone on disk, exposed to Claude Code at `~/.claude/skills/` through an absolute-path symlink. There is no separate installed copy and no sync step: edits you commit to the clone are visible to every Claude Code session on the machine at once. Skills keep their bare names (`/spec`, not `/adlc:spec`). If the plugin is installed too, uninstall it first (`claude plugin uninstall adlc@adlc-toolkit`), or `adlc doctor` will report a doubled install.

### Symlink install

```bash
git clone https://github.com/atelier-fashion/adlc-toolkit.git   # or your fork
cd adlc-toolkit && ./install.sh
```

`install.sh` is idempotent and repair-capable: it symlinks `~/.claude/skills` and `~/.claude/agents` to this clone, builds a skills-only view of the clone and mounts it at `~/.agents/skills` for the other agent harnesses (below), puts the `adlc` CLI on your PATH (`~/bin/adlc`), scaffolds `~/.claude/adlc/config.yml` (delegation **off** by default), and finishes by running `adlc doctor`. Run it again any time — a healthy machine reports zero actions; a broken one is repaired. Moved the clone? `./install.sh --repair` re-stamps everything to the new location, the view links included.

```bash
adlc doctor                          # full health check
adlc doctor --checks forge           # just one check (skills use this as a pre-flight)
adlc harness detect                  # which agent harnesses are installed, and mounted
```

### Other agent harnesses: `~/.agents/skills`

Copilot CLI, Codex, Gemini CLI and Cursor read user-level skills from `~/.agents/skills`. `install.sh` mounts a **skills-only view** of the clone there: a directory under `~/.claude/adlc/skills-view/` holding one link per directory that has a `SKILL.md`, so those harnesses never see `tools/`, `partials/`, `templates/` or `.adlc/`. Claude Code's own mount, `~/.claude/skills`, stays a link to the whole clone.

- An edit to an existing skill reaches every harness at once, as it always has. A skill directory you **add or remove** reaches the four other harnesses at the next `./install.sh` run; `adlc doctor`'s `skills-view` check says when the view is behind.
- If `~/.agents/skills` is absent, it becomes a link to the view. If it is already a directory of your own, `install.sh` adds one link per toolkit skill inside it and touches nothing else: a skill name you already use there is skipped and reported, never overwritten. `--dry-run` names what it found and what it would do.
- `adlc harness detect` (`--json` for scripts) prints, for each of the five harnesses, whether its binary is on `PATH`, the version it reports, and whether its skills directory reaches this toolkit. Nothing about discovery on the non-Claude harnesses has been verified yet; the mount is the structural half of that.
- The skill **text** is written for all five (REQ-666): the argument is described in prose rather than as `$ARGUMENTS`, context loads through one fence the model runs first, every agent dispatch says what to do on a harness without subagents (run the checklist inline from the project's `.adlc/agents/`, which `/init` vendors), and no skill names a harness home path. What is lost until the per-harness adapters ship:

  | On a non-Claude harness | Effect |
  |---|---|
  | the ETHOS `!` line | shown as literal text; the model may run its command or skip it, so the ethos can be missing from the skill's context |
  | agent dispatch | runs inline, one checklist at a time, where the harness has no subagents |
  | the plugin route's `adlc:` names | not applicable on this mount: the skills view has no namespace. The plugin installs below are a separate route, and their naming is unverified |

### Install as a plugin on other harnesses (alternative)

This is an alternative for harnesses other than Claude Code. On Claude Code, use the [plugin route](#install) or the symlink install above.

The `~/.agents/skills` mount follows the clone, so a harness lists every commit at once. Cursor and Copilot CLI can instead list the toolkit at a tag you choose, through their own manifests, [`.cursor-plugin/plugin.json`](.cursor-plugin/plugin.json) and [`.github/plugin/plugin.json`](.github/plugin/plugin.json). Both point at the same skill directories, so nothing moves. Use a tag cut after these manifests landed: `v5.4.0` and older have none.

Each one is a **catalog mount**, not a third install route. It pins what the harness lists, and a skill's shell still needs a Claude Code install route on the same machine. So the pin covers the skill text only: the partials, engines and `adlc` CLI a skill runs are whatever that route has installed, at its version. A tag can also be moved, so note `git -C adlc-toolkit rev-parse HEAD` if you need the exact commit. Neither vendor documents `CLAUDE_PLUGIN_ROOT` for a skill's shell, so a skill finds ToolkitRoot through `~/.claude/skills` or `~/.claude/adlc/plugin-root`.

Every claim below about Cursor, Copilot CLI and Gemini CLI is **unverified**. None of their binaries was available, so nothing here has run on a real install, and `.adlc/research/harness-probes/` holds no `cursor.json`, `copilot.json` or `gemini.json` probe result. Each subsection names the vendor docs its claims come from, read on 2026-10-30. The full record is [`.adlc/specs/REQ-665-plugin-manifests-alternative-install/verification.md`](.adlc/specs/REQ-665-plugin-manifests-alternative-install/verification.md).

#### Cursor (pinned plugin)

**Unverified.** Source: [Cursor plugins](https://cursor.com/docs/plugins) and the [plugin reference](https://cursor.com/docs/reference/plugins). No probe result: `cursor.json` does not exist.

- **Install.** Clone at a tag, copy the clone into Cursor's local plugin directory, then run **Developer: Reload Window**. Copy it, do not symlink it: Cursor skips a symlink that resolves outside that directory. On Enterprise accounts the admin setting **Allow Local Plugin Imports** has to be on, and it is off by default.

  ```bash
  git clone --branch <tag> https://github.com/atelier-fashion/adlc-toolkit
  mkdir -p ~/.cursor/plugins/local
  cp -R adlc-toolkit ~/.cursor/plugins/local/adlc
  ```

- **What loads.** The skills, through `"skills": "./"`. How a plugin's skill is named when you invoke it, and what happens when that name is also a built-in command, is **unverified**.
- **What does not load.** Agents: `"agents": []` switches off the default `agents/` scan, because the toolkit's agents are in Claude Code's format. On the symlink install Cursor reads them through `~/.claude/agents` instead (see [Cursor](#cursor)). Hooks: `"hooks": {}` keeps Claude Code's `hooks/hooks.json` out, and Cursor has no hook render of its own: it reads a project's `.claude/settings.json`. Neither agents nor hooks are bundled in the plugin manifest. MCP: the toolkit ships no server. The runtime: this install pins what Cursor lists but does not replace a Claude Code install route on a machine that runs the skills, because a skill resolves ToolkitRoot, the installed engines and the `adlc` CLI through it.
- **Coexistence.** With the `~/.agents/skills` mount on the same machine, each skill may be listed twice. Which copy answers is undocumented and **unverified**.
- **Update.** Check out the new tag and copy again, then reload the window:

  ```bash
  git -C adlc-toolkit fetch --tags
  git -C adlc-toolkit checkout <new-tag>
  rm -rf ~/.cursor/plugins/local/adlc
  cp -R adlc-toolkit ~/.cursor/plugins/local/adlc
  ```

- **Trade-off.** A pinned copy is reproducible and changes only when you update it, and can therefore be behind the clone; the live clone shows every commit instantly and cannot be pinned.

#### Copilot CLI (pinned plugin)

**Unverified.** Source: the [Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference). No probe result: `copilot.json` does not exist.

- **Install.** Clone at a tag, then install the clone by path. Copilot's lookup order reaches `.github/plugin/plugin.json` before `.claude-plugin/plugin.json`. Whether this install copies the clone or reads it in place is undocumented, so keep the clone at the tag.

  ```bash
  git clone --branch <tag> https://github.com/atelier-fashion/adlc-toolkit
  copilot plugin install ./adlc-toolkit
  ```

- **What loads.** The skills, through `"skills": "./"`. How a plugin's skill is named when you invoke it, and what happens when that name is also a built-in command, is **unverified**.
- **What does not load.** Agents: `"agents": []` switches off the default `agents/` scan, because the toolkit's agents are in Claude Code's format. Copilot gets its agents from `adlc harness install --harness copilot`, which is separate from this plugin (see [Copilot CLI](#copilot-cli)). Hooks: `"hooks": {}` keeps Claude Code's `hooks/hooks.json` out, and Copilot's hook render is `.github/hooks/adlc.json`, which `/init --harness copilot` writes into a project. Neither is bundled in the plugin manifest. MCP: the toolkit ships no server. The runtime: this install pins what Copilot lists but does not replace a Claude Code install route on a machine that runs the skills, because a skill resolves ToolkitRoot, the installed engines and the `adlc` CLI through it.
- **Coexistence.** Copilot resolves skills first-found-wins, with `~/.agents/skills` ahead of plugin skills, so the mount **wins**: a same-named plugin skill is silently ignored, and the pin has no effect while the mount exists. `install.sh` creates that mount; the Claude Code plugin route does not.
- **Update.** Check out the new tag and install again. The vendor doc does not describe updating a direct local-path install:

  ```bash
  git -C adlc-toolkit fetch --tags
  git -C adlc-toolkit checkout <new-tag>
  copilot plugin install ./adlc-toolkit
  ```

- **Trade-off.** A pinned copy is reproducible and changes only when you update it, and can therefore be behind the clone; the live clone shows every commit instantly and cannot be pinned.

#### Gemini CLI

No manifest ships for Gemini CLI: there is no `gemini-extension.json`. Gemini CLI uses the `~/.agents/skills` mount above.

**Unverified.** Source: the [extension reference](https://geminicli.com/docs/extensions/reference) and `packages/cli/src/config/extension-manager.ts` on `main`. No probe result: `gemini.json` does not exist. Why no manifest ships:

- Gemini CLI loads an extension's skills only from `<extension>/skills`, and its manifest has no skills key, so a manifest at the clone root would need a root `skills/` directory.
- A root `skills/` would double the Claude Code plugin's catalog, because Claude Code scans it in addition to the manifest's `skills` key.
- A root `skills/` of symlinks would not survive an install. Install copies with `fs.promises.cp`, which rewrites a relative symlink to an absolute path into the source. The copy then dangles once a git install's temporary clone is gone, and after a local-path install it still reads the clone, which is no pin. The rewrite is **verified** on Node 26.7.0; the install itself is not.
- `agents/` and `hooks/hooks.json` are read from fixed locations, with no opt-out short of disabling the extension, so a clone-root extension would feed Gemini CLI Claude-format agents and Claude Code's hook.

A pinned install would need an artifact with real copies under `skills/`, such as a generated release branch, and none is published. geminicli.com also says Gemini CLI was replaced by Antigravity CLI for unpaid and Google One users on 2026-06-18.

### Harness adapters: one allowlist and one hook set, rendered per harness

Three things the toolkit depends on have no cross-harness standard: agent definitions, command allowlists and hooks. Each now has one semantic source, rendered per harness through a data file, `harness/<name>.yml` (REQ-657). `/init` renders a project's layer with `adlc harness render`, never by copying a static file:

| Source | What it holds | What `claude` renders it into |
|---|---|---|
| `templates/permissions.yml` | the **routine** tier (what may be pre-approved) and the **deny** tier (the one-way moves: force-push, `gh pr merge`, `rm -rf`, deploys, `terraform`) | `.claude/settings.json` `allow`, and `ask` for the deny tier, so a person confirms each one-way move |
| `templates/hooks.yml` | `ethos-inject` (prints `.adlc/ETHOS.md` at session start and after compaction) and `session-record` (writes the gitignored session sidecar `.adlc/.session/<id>`, which `/wrapup` reads first when it finds the session transcript, then flattens with `extract-chat --format <harness>`) | the `hooks` block of `.claude/settings.json`, which Copilot CLI and Cursor also read |
| `agents/*.md` | the agent checklists | stamped in place (`model:`); copy harnesses get rendered copies |
| `templates/instructions/` | `AGENTS.md`, the instruction file every harness reads | `CLAUDE.md` gains an `@AGENTS.md` import and keeps its own lines |

The `claude`, `copilot` and `cursor` adapters ship; Codex and Gemini CLI follow as data files. What a harness cannot express is reported, never silently widened: `allowlist-fidelity` lists every entry per harness, and an adapter has to accept each gap in writing. On Claude Code, the partial-sourcing fence is not pre-approved in a committed file, and the allowlist applies only in a trusted workspace. The allowlist is a convenience for the routine tier, not a gate: the structural gates are the orchestrator's (`tools/lint-skills/README.md`, "Declared residuals"). `adlc harness render --check` and the `render-parity` lint keep the committed renders equal to what the renderer writes; `/template-drift` reports a project whose rendered settings are behind as `harness-config` drift.

### Copilot CLI

The adapter is `harness/copilot.yml` (REQ-656). Its facts are the vendor docs as read on 2026-10-30: no run has happened yet, and the end-to-end check on this harness is owed (see the REQ-656 spec, Deferred).

```bash
./install.sh                                # mounts the skills at ~/.agents/skills
adlc harness install --harness copilot      # renders ~/.copilot/agents/<name>.agent.md
```

Then run `/init --harness copilot` (`/adlc:init --harness copilot` on the plugin install) in a project. It writes `.github/hooks/adlc.json` (`sessionStart` runs `ethos-inject` and `session-record`, `subagentStart` runs `ethos-inject`) and `AGENTS.md`, and it **prints** one line, because Copilot has no committed allowlist. Paste that line into a shell alias or your profile:

```bash
alias copilot="copilot --allow-tool 'shell(git status:*)' --allow-tool 'shell(gh pr view:*)' … --deny-tool 'shell(git push --force:*)' --deny-tool 'shell(gh pr merge:*)' …"
```

The full line and its fidelity report come from `adlc harness render --harness copilot`. That render writes nothing under `~/.copilot`, and the line carries no auto-approve flag. No event marks a compaction, so ETHOS is not re-injected after one.

<!-- harness-loss: copilot -->
**What is lost on Copilot CLI**

| What | On Copilot CLI |
|---|---|
| Committed allowlist | no: session flags on the printed line |
| Allowlist granularity | subcommand prefix (`token-prefix` in the adapter): `shell(<prefix>:*)` admits every argument after the prefix |
| Deny-tier rendering | a hard `--deny-tool` on the printed line, one per argv prefix of the deny tier, re-rendered at `exec` scope by REQ-662 |
| Shared-base fail-closed | `git push:*`, `git branch:*` and the `git -C` prefix are omitted and prompt, so every `git -C …` call prompts, until REQ-664 clears OQ-8 and OQ-9 |
| Read-only reviewers | `tools:` is rendered and the docs say it is enforced; unverified on a real run |
| ETHOS in subagents | the `subagentStart` hook plus an ETHOS-first line in every rendered agent; unverified |
| Subagent nesting depth | 6 |
| `/sprint` workflow engine | unavailable |
| Transcript schema | undocumented |
| Explicit skill invocation | `/name` |
| Headless deny status | unverified until a REQ-664 result exists for this harness |
| Fences, not commands | `fence.partial-source` is not on the line, so a partial-sourcing fence prompts; the broad spelling is a separate remedy labelled "WIDENING, not applied" |
| `git -C` | the bare prefix would cover every git subcommand, so it is omitted (see the shared-base row) |

**Declared residuals.** What no allowlist or prefix deny closes, on either harness. They are declared, not chased:

- Matching is spelling-level.
- Allows that execute their arguments (`find -exec`, `awk system()`, `sed e`, `npx`, `npm run`/`exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- Copilot's matching of chained commands (`;`, `&&`, `$()`) is unverified, and every Copilot allow is untrustworthy against deny-tier commands until REQ-664 shows it.
- The `env-prefix` and `shell-opener` wrapper shapes are `unverified`, and no REQ-664 result lifts an omission resting on them.
- The dogfood notes record the prompt count (REQ-656 BR-13).
- The allowlist is not the gate: REQ-659's structural halt is.
<!-- /harness-loss: copilot -->

### Cursor

The adapter is `harness/cursor.yml` (REQ-656). Its facts are the vendor docs as read on 2026-10-30: no run has happened yet, and the end-to-end check on this harness is owed (see the REQ-656 spec, Deferred).

Cursor reads `.claude/settings*.json` hooks, `~/.claude/agents` and `~/.claude/skills` itself, so it gets no agent render and no hook render. Prepare a project with both layers, because `/init --harness cursor` alone leaves `.claude/settings.json` without the hooks Cursor would read:

```bash
./install.sh                                # mounts the skills at ~/.agents/skills
```

Then run `/init --harness claude,cursor` (`/adlc:init --harness claude,cursor` on the plugin install) in the project, or `/template-drift` on one already initialised. It writes `.cursor/cli.json`, `.cursor/permissions.json` and `AGENTS.md`. `adlc agents render --harness cursor` is a no-op that says so. The hooks reach a Cursor session only while "Include Third-Party Plugins, Skills, and Other Configs" stays on in Cursor Settings (the default), and how Cursor delivers a `SessionStart` hook's output as context is undocumented, so ETHOS by hook is unverified.

<!-- harness-loss: cursor -->
**What is lost on Cursor**

| What | On Cursor |
|---|---|
| Committed allowlist | yes: `.cursor/cli.json` and `.cursor/permissions.json` |
| Allowlist granularity | command base: an entry names one command and everything under it |
| Deny-tier rendering | a hard `deny` in `.cursor/cli.json`, so you run a denied one-way move from your own shell (the REQ-655 trade). A shared-base move is approved at Cursor's prompt instead |
| Shared-base fail-closed | `Shell(git)` and `Shell(gh)` are omitted, so `git` and `gh` prompt, and their deny-tier entries are `deny-unsupported`, until REQ-664 clears OQ-8 and OQ-9 |
| Read-only reviewers | unverified: whether Cursor honours the `tools:` line of a `~/.claude/agents` file is open (OQ-2) |
| ETHOS in subagents | no hook path: Cursor's reader of Claude-format hooks does not map `SubagentStart` |
| Subagent nesting depth | 1 |
| `/sprint` workflow engine | unavailable |
| Transcript schema | Claude Code-compatible JSONL |
| Explicit skill invocation | `/name`, `@name` |
| Headless deny status | unverified: whether `agent -p` honours `deny` waits on plan §6.3 and REQ-664's `ask-tier-deny` (OQ-6) |
| Fences, not commands | `fence.partial-source` is omitted, because a first-token `Shell(if)` would allow every line that opens that way, so a partial-sourcing fence prompts |
| `git -C` | `Shell(git)` would cover it; with that entry omitted, `git -C …` prompts like the rest of git |
| Deny width | all `rm` and all `terraform` subcommands are denied; run them from your own shell |
| `Shell(npm)` width | one entry for all of npm, which admits `npm publish` |
| Double skill discovery | Cursor reads `~/.agents/skills` and `~/.claude/skills`, so every toolkit skill is discovered twice and the clone root's non-skill directories are exposed through the second |
| IDE permissions file | `.cursor/permissions.json` has no deny key, so the deny tier reaches the `agent` CLI only, and a committed `terminalAllowlist` overrides the matching allowlist in the IDE's settings |

**Declared residuals.** What no allowlist or prefix deny closes, on either harness. They are declared, not chased:

- Matching is spelling-level.
- Allows that execute their arguments (`find -exec`, `awk system()`, `sed e`, `npx`, `npm run`/`exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- Copilot's matching of chained commands (`;`, `&&`, `$()`) is unverified, and every Copilot allow is untrustworthy against deny-tier commands until REQ-664 shows it.
- The `env-prefix` and `shell-opener` wrapper shapes are `unverified`, and no REQ-664 result lifts an omission resting on them.
- The dogfood notes record the prompt count (REQ-656 BR-13).
- The allowlist is not the gate: REQ-659's structural halt is.
<!-- /harness-loss: cursor -->

### `ADLC_HOME`

The toolkit's machine state (the id counters and their locks, the reservations ledger, the machine config, the delegate venv, the skills view) lives under one directory, `ADLC_HOME`, which defaults to `~/.claude`. With it unset, every path is exactly where it has always been: nothing moves. Set it to an absolute path to keep the toolkit's state somewhere else:

```bash
ADLC_HOME="$HOME/.adlc" ./install.sh     # set it in your shell profile too, so every session sees it
```

`install.sh` then creates `skills`, `agents`, `adlc/config.yml` and the skills view under that directory, and still links `~/.claude/skills` and `~/.claude/agents` to the clone, because Claude Code reads those and every skill's shell falls back through `~/.claude/skills`. A set `ADLC_HOME` that is empty or relative is an error that names it; nothing falls back to `~/.claude` silently. `ADLC_CONFIG`, when set, still names the config file outright. No migration tool ships: moving existing counters or the venv is a follow-up, not this release.

Other install options:

```bash
./install.sh --dry-run           # print the action plan, change nothing
./install.sh --with-delegation   # also install the (opt-in) delegation CLIs
```

### Manual install (under the hood)

`./install.sh` is the supported path for the symlink route; this section documents what it does so you can reproduce it by hand or debug a failure. (`adlc doctor` checks each of these.) The `~/.claude/skills` and `~/.claude/agents` paths below are the symlink route's own; the plugin route uses neither.

```bash
# 1. Back up any existing directories (rename is safe and reversible)
[ -e ~/.claude/skills ] && mv ~/.claude/skills ~/.claude/skills.bak
[ -e ~/.claude/agents ] && mv ~/.claude/agents ~/.claude/agents.bak

# 2. Symlink to Claude Code's skills and agents directories.
#    Use ABSOLUTE paths so they resolve from any cwd.
TOOLKIT="$PWD"                       # run from the toolkit clone root
ln -sfn "$TOOLKIT" "$HOME/.claude/skills"
ln -sfn "$TOOLKIT/agents" "$HOME/.claude/agents"

# 3. Put the adlc CLI on your PATH (install.sh writes a shim in ~/bin).
#    Either add ~/bin to PATH, or run the CLI directly:
python3 "$TOOLKIT/tools/adlc/adlc.py" doctor

# 4. Verify
readlink ~/.claude/skills            # → absolute path to your adlc-toolkit clone
ls ~/.claude/skills/review/SKILL.md  # should resolve through the symlink

# 5. Optional: the skills-only view for the other harnesses (see above).
#    One link per skill directory, then the mount.
VIEW="$HOME/.claude/adlc/skills-view"
mkdir -p "$VIEW"
for d in "$TOOLKIT"/*/; do n=$(basename "$d"); [ -f "$TOOLKIT/$n/SKILL.md" ] && ln -sfn "$TOOLKIT/$n" "$VIEW/$n"; done
mkdir -p ~/.agents && [ ! -e ~/.agents/skills ] && ln -s "$VIEW" ~/.agents/skills
```

Git commands run from inside `~/.claude/skills/` transparently operate on the clone's `.git` directory, so you can use either path interchangeably. Delegation (the `tools/delegate/` CLIs) is a separate opt-in — `./install.sh --with-delegation` or run `tools/delegate/install.sh` directly.

### Trying the plugin from a clone

To test the plugin route from a checkout, add the clone as a local-path marketplace in a sandbox `HOME`, not your own: `claude plugin marketplace add ./` then `claude plugin install adlc@adlc-toolkit`. A local-path marketplace runs the plugin from the source directory rather than a cache copy, and `adlc doctor` recognises that as the plugin route. Releases are cut per [`RELEASING.md`](RELEASING.md).
