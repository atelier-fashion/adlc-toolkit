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
| `claude plugin validate . --strict` and `claude plugin validate .claude-plugin/plugin.json --strict` both pass. A `CLAUDE.md` at the plugin root fails the second, so the toolkit keeps its own at `.claude/CLAUDE.md`, which Claude Code loads as project instructions from a checkout | verified, 2.1.258 |
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
| `/sprint` | Parallel pipeline orchestrator — launch multiple `/proceed` sessions across REQs. Has an exec engine (`--exec`, a program that runs one headless harness per REQ and merges only after an operator approves), a workflow engine (`--workflow`, the deterministic `adlc-sprint` Dynamic Workflows script that restores per-REQ fan-out while keeping cross-REQ concurrency) with the legacy background-runner engine as an always-available fallback. The workflow engine runs lite-lane REQs on the full lane and logs that it did |
| `/reflect` | Post-implementation self-review before formal review |
| `/review` | Multi-agent code review (correctness, quality, architecture, tests, security) |
| `/adversary` | Adversarial review of any artifact (spec, plan, diff/PR, README, or prose claim) — assumes it is wrong and tries to prove it, then reports only findings that survive self-refutation. Read-only; hunts omissions, not just bugs in what was written |
| `/canary` | Canary deployment with smoke tests — deploy zero-traffic revision and promote on success |
| `/wrapup` | Close out a feature — commit, merge, deploy, update artifacts |
| `/bugfix` | Streamlined bug fix workflow. With `bugfix.regression_test: required` in `.adlc/config.yml` it writes a regression test that cites the bug id and watches it fail before writing the fix, records the test (or a waiver) in the bug report, and runs `adlc regression-check` on the bug before merging. An absent key means `off` (REQ-691) |
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
| Regression tests (`/bugfix`, `adlc regression-check`) | `bugfix.regression_test` | `required` or `off`; an absent key means `off`, so a project that never sets it keeps today's `/bugfix`. With `required`, every fix gets a test that fails without it and passes with it, or a recorded waiver, and `adlc regression-check check` (which a CI job can run) confirms that every resolved bug still has its test (`partials/regression-check.md`) |

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
- `adlc harness detect` (`--json` for scripts) prints, for each known harness, whether its binary is on `PATH`, the version it reports, and whether its skills directory reaches this toolkit. Nothing about discovery on the non-Claude harnesses has been verified yet; the mount is the structural half of that.
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

### The `/sprint` exec engine

`/sprint --exec REQ-a REQ-b` runs each REQ in a headless harness and keeps every one-way move
out of the model's hands. The orchestrator is a program, `adlc sprint-exec`, so a plain shell
can do all of it:

```sh
adlc sprint-exec run REQ-a REQ-b      # foreground: pre-flight, launch, supervise; its stdout is the dashboard
adlc sprint-exec status               # the dashboard, without tokens
adlc sprint-exec approve REQ-a --token <token>
adlc sprint-exec reject REQ-b "not this sprint"
adlc sprint-exec answer REQ-c "use the second option"
adlc sprint-exec abort REQ-d
adlc sprint-exec resume               # a new supervisor, with fresh tokens
```

The model runs Phases 0 to 7 and stops at the merge gate. On approval the orchestrator verifies
the PR is the one the dashboard showed, trial-merges in a detached worktree of its own, merges
pinned to the recorded head, runs the declared deploy, resumes the harness session once for
lesson drafting, gates and merges the chore PR, and cleans up. Two adapters ship: `claude`, the
default, and `codex` (`--harness codex`), the first stage of REQ-662, described in "Codex CLI
under `/sprint --exec`" below. Copilot CLI, Cursor and Antigravity CLI are later stages of
REQ-662: their adapters have no exec block yet, and the engine refuses each by name. A GitHub
repo only: `--exec` on Azure DevOps is refused until a merge can be pinned there.

What follows in this section is the engine and its Claude adapter. The approval protocol and
the gates hold on every harness. What changes per harness is the adapter's `exec:` block in
`harness/<name>.yml`, and with it what the allow and deny rules leave open: the residuals
below are Claude's, and the Codex section lists Codex's.

Keys, all under `sprint.exec` in `.adlc/config.yml` and read once at launch:
`child_gh_token` (the **name** of a variable holding a token without `contents: write`),
`stall_minutes` (20), `require_branch_protection` (true), `auto_rebase_max_attempts` (1),
`deploy` (`{target, command}`), `harness_flags`, and `allow_extra` (argv lists of further routine
entries, each refused if it wraps a deny or shares a command base with one, such as `git push`). Without a scoped token, launch needs
`--shared-credentials`. Against an unprotected branch it needs `--allow-unprotected`.

The model's file tools write only inside the run's working copies (and a close-out's added
spec directory) and read only those plus the toolkit: each is a path-scoped rule, never a bare
`Write` or `Read`, which reached every path and let a model rewrite the toolkit the orchestrator
sources at approve (BUG-265). Claude's own path check keeps shell reads and writes inside the
same directories.

**What this does not stop.** The allow and deny lists are defense in depth, not the gate. The
gates are the approval ledger, the pinned merge, the detached-worktree trial merge and rebase,
the local diff gates, the child credentials, branch protection and the exit checks. These
residuals stand, and `harness/claude.yml` declares them too:

- **Fences.** No allow can admit a fence that sources a partial: Claude refuses `.` and
  `source` whatever the allow says (REQ-682). So under `--exec` every toolkit fence runs through
  one executable, `<ToolkitRoot>/tools/adlc/fence-run`, admitted by its absolute path and by
  nothing broader. It runs only fences it reads from the toolkit install, binds every value as
  data, and resolves every partial from the install, so **a consumer's vendored
  `.adlc/partials/` do not run under `--exec`**. The code it runs is still opaque to the
  permission check: a CI audit of each fence's reach (`tools/adlc/tests/test_exec_reach.py`),
  not the allowlist, keeps a deny-tier command out of it. Toolkit skills and agents are not
  loaded under the engine's isolation flags either, so they reach an exec model only through
  `fence-run show`, and an agent's checklist runs inline. Whether that one allow is a boundary
  on a given harness is what `adlc harness probe`'s `fence-vs-allowlist` measures in its
  `runner-prefix` variant (REQ-707). A stub runner gets one absolute-path allow; it must run,
  and eleven controls (a sibling path, an env prefix, `$(…)`, a backtick, a redirect, `;`,
  `&&`, `||`, `|`, `&` and a newline) must not carry anything past it. REQ-662 gates every
  other harness's exec adapter on it.
- **Wrappers and runners.** A command wrapped in `sh -c`, `env`, `xargs`, `python -c`, `npx`,
  `npm run` or `find -exec` is not seen by a prefix rule.
- **`gh api`** reaches merge and ref-update endpoints without a `gh pr merge` prefix.
- **Flag positions and equivalents.** `gh -R <repo> pr merge` does not match, and a semantic
  equivalent of a denied move under another spelling is not denied.
- **Azure DevOps flag routes**, narrowed for the `partials/forge.sh` wrappers only.
- **Direct pushes.** Nothing local fully stops `git push origin HEAD:<integration branch>`.
  Branch protection does, which is why pre-flight refuses without it, and the first-parent exit
  check reports one that got through.
- **Credentials.** `SSH_AUTH_SOCK` and `GIT_SSH_COMMAND` give a child a push credential whatever
  its forge token is. The controls are branch protection and the exit checks.
- **Merge bots.** A bot on the forge that merges on a label or a comment is reachable by anything
  that can write one.
- **Same-user processes.** A process that escapes the sweep and reads the operator's terminal, or
  the session transcript when `/sprint` carries the dashboard, can read a token. Approval is held
  by a supervisor-side token, not by file permissions: anything on disk in a run directory is
  writable by the same user, so the digest is in memory only. Once the supervisor has exited,
  an escapee can start its own with `resume`, which prints fresh tokens to whoever runs it.
  `decidedBy`, `channel` and `callerPid` are recorded on every decision, as evidence.
- **Skills stay discoverable.** A `claude -p` session can still find `/wrapup` and `/sprint` through
  ordinary skill loading, even though the delivered prompts name neither's merge steps.
- **A harness without `capabilities.deny`** gets no deny flags at all.

**Verified, and not.** `.adlc/research/harness-probes/claude-exec-manual.md` records what a
logged-out `claude` 2.1.258 shows. Owed to a logged-in run: that `--allowedTools` holds in an
untrusted workspace, that a deny beats a matching allow, whether a multi-statement fence matches
any entry, and a `--resume` that continues a real conversation. A miss shows as a `denied` halt,
not silently.

### Harness adapters: one allowlist and one hook set, rendered per harness

Three things the toolkit depends on have no cross-harness standard: agent definitions, command allowlists and hooks. Each now has one semantic source, rendered per harness through a data file, `harness/<name>.yml` (REQ-657). `/init` renders a project's layer with `adlc harness render`, never by copying a static file:

| Source | What it holds | What `claude` renders it into |
|---|---|---|
| `templates/permissions.yml` | the **routine** tier (what may be pre-approved) and the **deny** tier (the one-way moves: force-push, `gh pr merge`, `rm -rf`, deploys, `terraform`) | `.claude/settings.json` `allow`, and `ask` for the deny tier, so a person confirms each one-way move |
| `templates/hooks.yml` | `ethos-inject` (prints `.adlc/ETHOS.md` at session start and after compaction) and `session-record` (writes the gitignored session sidecar `.adlc/.session/<id>`, which `/wrapup` reads first when it finds the session transcript, then flattens with `extract-chat --format <harness>`) | the `hooks` block of `.claude/settings.json`, which Copilot CLI and Cursor also read |
| `agents/*.md` | the agent checklists | stamped in place (`model:`); copy harnesses get rendered copies |
| `templates/instructions/` | `AGENTS.md`, the instruction file every harness reads | `CLAUDE.md` gains an `@AGENTS.md` import and keeps its own lines |

The `claude`, `copilot`, `cursor`, `codex` and `antigravity` adapters ship; Gemini CLI has none. What a harness cannot express is reported, never silently widened: `allowlist-fidelity` lists every entry per harness, and an adapter has to accept each gap in writing. On Claude Code, the partial-sourcing fence is not pre-approved in a committed file, and the allowlist applies only in a trusted workspace. The allowlist is a convenience for the routine tier, not a gate: the structural gates are the orchestrator's (`tools/lint-skills/README.md`, "Declared residuals"). `adlc harness render --check` and the `render-parity` lint keep the committed renders equal to what the renderer writes; `/template-drift` reports a project whose rendered settings are behind as `harness-config` drift.

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

### Codex CLI

The adapter is `harness/codex.yml` (REQ-655). Its facts are `codex-cli 0.166.0` as run on 2026-10-31: `adlc harness probe codex`, and a by-hand gate through the real TUI, recorded in the REQ-655 spec. No lite REQ has been run end to end on Codex yet, and that dogfood is owed.

```bash
./install.sh                              # mounts the skills at ~/.agents/skills
adlc harness install --harness codex      # renders ~/.codex/agents/<name>.toml
```

Then run `/init --harness codex` (`/adlc:init --harness codex` on the plugin install) in a project. It writes `.codex/rules/adlc.rules`, `.codex/hooks.json`, `.codex/config.toml` (`sandbox_mode = "workspace-write"` and `approval_policy = "on-request"`, merged into a file you already have) and `AGENTS.md`. Commit them. Two steps are yours, and neither is optional:

1. **Trust the project.** Codex ignores `.codex/` until your user config holds `[projects."<absolute path>"]` with `trust_level = "trusted"`. A `-c` override does not load a project layer.
2. **Review the hooks.** Trust loads `.codex/hooks.json`, but each hook stays `untrusted` until you approve it with `/hooks` in the TUI, or at the "Hooks need review" prompt at startup. The approval is stored per hook, by absolute path and content hash, so a fresh clone, a linked worktree or a changed hook needs it again. `codex exec` has no review step: it skips an unreviewed hook and says nothing. Nothing here writes that approval for you.

**The gate, recorded on 2026-10-31.** `git add` and `git commit` in a main checkout ran with no prompt in the TUI under the rendered rules, and `git commit` ran headless under a probe's `allow` rule in a main checkout and in a linked worktree. A commit runs because a matched `allow` runs outside the sandbox; the sandbox itself cannot write `.git` (`git branch -D x`, unmatched, failed at `refs/heads/x.lock`). When an `allow` and a `prompt` rule both match, the stricter wins: `git -C <path> push --force` and `git push --force` each stopped at `requires approval by policy` with `allow` rules for their shorter prefixes loaded, in the TUI and in `codex execpolicy check`. So `/proceed` commits on Codex without asking, and does not push on its own: `git push` is unmatched and needs a person.

<!-- harness-loss: codex -->
**What is lost on Codex CLI**

| What | On Codex CLI |
|---|---|
| Committed allowlist | yes: `.codex/rules/adlc.rules`, once the project is trusted |
| Allowlist granularity | subcommand prefix (`token-prefix` in the adapter): a `prefix_rule` admits every argument after its tokens, and an exact entry widens (`git config user.email`, `npm ci`, `pwd`) |
| Deny-tier rendering | the `deny` tier renders as `prompt` in the committed file, so a one-way move is a human confirmation for plain invocations; `forbidden` is the exec engine's (REQ-662) |
| Shared-base fail-closed | `git push:*`, `git branch:*` and the `git -C` prefix are omitted unconditionally and no result restores them, because a token prefix cannot name `--force`, `+refspec` or `-D` at any position. Omitted does not mean a prompt here: see the unmatched row |
| Read-only reviewers | honour-system: Codex has no per-agent tool list, so seventeen rendered agents carry a restraint sentence and nothing enforces it |
| ETHOS in subagents | the ETHOS read line in every rendered agent, plus `SubagentStart`, which reaches a subagent once reviewed (recorded) |
| Subagent nesting depth | undocumented; the pipeline runner stays flat |
| `/sprint` workflow engine | unavailable |
| Transcript schema | undocumented; `~/.codex/sessions/**/rollout-*.jsonl` is located, not parsed (REQ-660) |
| Explicit skill invocation | `$name`; the catalog lists each skill as `adlc:<name>` |
| Headless deny status | `ask-tier-deny` reads `pass` at `codex-cli 0.166.0` (2026-11-17): a `forbidden` rule refused its command with an allow on a shorter prefix loaded (`deny-under-allow`), and Codex logged the refusal on stderr. Under a `git -C` allow a deny on the plain spelling did not hold (`wrapped-allow` `fail`), so no `git -C` allow is rendered. The committed file's `prompt` decision is not what the probe measured |
| Fences, not commands | `fence.partial-source` is omitted. `fence-vs-allowlist` reads `fail` on `routine-only`, `broad-first-token` and `broad-sh` at `codex-cli 0.166.0`: in none did the fence's sentinel appear. Its `runner-prefix` variant reads `pass`, and that is how the exec engine runs a fence (REQ-682) |
| `git -C` | no rule of any decision; every `git -C <path> <sub>` is unmatched (see the shared-base and unmatched rows) |
| Hook review | no ETHOS reaches a session until a person reviews the hooks, per checkout, and again when a hook changes (see above). Codex has no load-time `!` line, so an unreviewed session has no ETHOS unless a rendered agent's read line supplies it |
| ETHOS after compaction | not re-injected: `PostCompact` has no context channel, and a manual compaction fires no `SessionStart` (recorded); automatic compaction is unmeasured |
| Skills catalog budget | 2 % of context or 8 000 chars, past which Codex shortens descriptions and drops skills with a warning. All 17 skills listed, none shortened, 6,107 characters: read from `codex debug prompt-input` in a sandbox home, not from a live mount. Run that command to see what your session lists |
| Unmatched git commands | measured with no rule loaded under `on-request` + `workspace-write`: `git push --force`, `git push --force-with-lease`, `git push origin +HEAD:refs/heads/x`, `git push origin --force`, `git branch -D x` and `git -C <path> push --force` each read `sandbox-failed`, which this table counts as prompts: the command fails in the sandbox, and it reaches a person only if the model asks to retry outside it. No spelling was recorded `ran`, so none reads "may run". That holds only where the sandbox reaches: `/tmp` and `$TMPDIR` are writable, so a remote there is not stopped |
| Wrapped invocations | deny-tier `prompt` rules match plain argv only. Inside shell control flow, a substitution, an env-assignment prefix or `bash -lc '<script>'` a deny-tier command is unmatched, and what stops it is the sandbox, only while `network_access` is off |
| Allow rules and the sandbox | a matched routine `allow` runs outside the sandbox (recorded), and the lint checks prefix and wrapper relations only: `gh api`, `npx`, `npm run`, `find -delete`, `sed -i` and `cp` residuals are the same exposure as Claude Code's |
| `--writable-root` | `adlc harness install --harness codex --writable-root <path>` widens every Codex session's writable area to include that repo's `.git`. The gate does not need it: `root-is-worktree` passed, and `writable-roots-repo` read `fail` |
| Trust step | without the `projects.<path>.trust_level` entry, `.codex/` is ignored |

**Declared residuals.** What no allowlist or prompt rule closes. They are declared, not chased:

- Matching is spelling-level.
- Allows that execute their arguments (`find -exec`, `awk system()`, `sed e`, `npx`, `npm run`/`exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the rule does not match.
- Semantic equivalents (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- Codex parses a chain of plain commands (`;`, `&&`) into its parts; a `$()` substitution or shell control flow is not matched.
- The `env-prefix` and `shell-opener` wrapper shapes stay `unverified`, and no REQ-664 result lifts an omission resting on them.
- A hook review pins the command in `.codex/hooks.json`, not the `.adlc/partials/` file it sources, so a change to a vendored partial runs under an approval already given.
- The dogfood notes record the prompt count (REQ-655 BR-14).
- The allowlist is not the gate: the sandbox is, and REQ-659's structural halt under the exec engine.
<!-- /harness-loss: codex -->

### Codex CLI under `/sprint --exec`

```bash
adlc harness install --exec --harness codex       # writes ~/.codex/rules/adlc-exec.rules (below)
adlc sprint-exec run --harness codex REQ-a REQ-b  # or /sprint --exec --harness codex REQ-a REQ-b
```

Each REQ gets one headless `codex exec` session in a linked worktree, under the approval protocol of "The `/sprint` exec engine" above: the model runs Phases 0 to 7 and stops at the merge gate, and the orchestrator merges, deploys and cleans up after an operator's `approve`. This section says what the engine does on Codex and what is lost there. Its source is the `exec:` block of `harness/codex.yml` (REQ-662, stage 1), and `tools/adlc/tests/test_exec_docs.py` holds the two equal.

**Probe status: `verified` for `codex-cli 0.166.0`, from `adlc harness probe codex` run at `2026-11-17T23:49:29Z`** (`.adlc/research/harness-probes/codex.json`). Probe readings: `git-write-worktree` `pass`, `git-write-main` `pass`, `trust-then-headless` `fail`, `session-start-context` `fail`, `stdin-prompt` `pass`, `fence-vs-allowlist` `fail`, `shell-timeout` `pass`, `ask-tier-deny` `pass`. None of the three failures holds the adapter back. The block declares `context_delivery: prompt`, so of `trust-then-headless` only the `allowlist-loaded` half is required, and it reads `pass`; `session-start-context` is not required. `fence-vs-allowlist` is read from its `runner-prefix` variant, which reads `pass`; its three older variants measure fence rules the engine no longer renders. The engine recomputes this verdict from the result file in the toolkit install at every launch, resume and close-out, and in `approve` before the merge, so neither this line nor the yml's `status` is the verdict. It reads `unverified` whenever the installed `codex --version` is not `codex-cli 0.166.0`, and `adlc harness doctor` prints the same recomputation. The real launches and resumes of 2026-11-18, recorded in `.adlc/research/harness-probes/codex-exec-manual.md`, check what no probe measures, among them seven facts the rows below cite: a bare `#` in a command defeats a prefix allow; `codex exec` writes a lasting trust entry for the main repository by itself; the working copy's rule file and config load without any trust of yours; the sandbox's writable area includes the temp roots; a resume works from a different working copy than the launch; in a linked worktree the main checkout's `.codex/` is not read; and `codex` has no approval flag to pin.

| What | On Codex CLI under `--exec` |
|---|---|
| Launch | `codex exec --json --sandbox workspace-write -C <worktree> -o <file>`. The prompt arrives on stdin, with no positional prompt and no `-` (`stdin-prompt`'s `without-prompt-flag` variant). `--sandbox` pins the sandbox. `codex exec` has no approval flag (neither `codex --help` nor `codex exec --help` at 0.166.0 lists one), so approval cannot be pinned on the argv: it comes from the working copy's `.codex/config.toml`, which the engine renders (`approval_policy = "on-request"`). `--json` prints the event stream that carries the session id, and `-o` names a file in the run directory for the last message. The final argv must be this template with its placeholders filled and nothing else; an operator's `--harness-flag` may add only `--model`. `forbidden_flags` is a lint backstop to that check, and lists, beyond the engine-wide six, `--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`, `--approve-for-me`, `--full-auto`, `danger-full-access`, `--ask-for-approval never`, `--ignore-rules`, `--ignore-user-config`, `-c`, `--config`, `--profile`, `--enable`, `--disable`. |
| Output | One JSON event per line on stdout. The session id is the `thread_id` of the `thread.started` event, a complete stream ends with `turn.completed`, and the final message is read from the `-o` file. A stream without `turn.completed`, a line that is not JSON or an empty final message is a parse failure, recorded as `error` with the parser's message, never `ok`. Raw stdout and stderr stay in the run directory. |
| Resume | `codex exec resume --json -o <file> <session id> -`, run with the working copy as its directory and the follow-up prompt on stdin. It takes no `--sandbox` and no `-C`, so its sandbox and rules come from the working copy's rendered `.codex/`, which the engine re-renders and checks first. Measured on 2026-11-18: the resume continued the same session, and under it an allowed write left the sandbox, an un-allowed write did not, and a denied command was refused. The same held when the session was resumed from a second linked worktree, with its own render and trust entry, under that worktree's rules: the close-out's case. A run whose output carried no session id is reported at the halt as one that cannot resume, before approval is asked for. |
| Close-out | After the merge, the engine resumes the session in a close-out working copy cut from the integration branch, with its own trust grant and revoke. `codex exec resume` takes no extra directory (the block declares no `add_dir_flag`), so the session cannot write the primary checkout's `pipeline-state.json`. The engine copies that file into the close-out working copy before the resume, the session edits it there, and the engine carries the changes back to the primary copy afterwards, never taking `status`, `exec` or `approval` from the session's copy. |
| Exit codes | `0` → `ok`, `1` → `error`. Any other code is `error`, with the raw code kept. A run with no terminal claim whose stderr holds Codex's own refusal line, `rejected: policy forbids commands starting with`, is `denied`, and the REQ is `blocked`. Only the harness's stderr is read for that line, never the model's text. |
| Shell timeout and delegation | 125 s, verified: in `shell-timeout` a `sleep 125` in one shell call completed. A delegated `adlc-read` may take 120 s, so delegation is `supported` and the engine does not set `ADLC_DISABLE_DELEGATE`. |
| Working copy | `worktree`, a linked worktree under `.worktrees/` as on Claude. `git-write-worktree` reads `pass` on `root-is-worktree` and `writable-roots-repo`. `git commit` is a routine allow, so in an engine run it runs outside the sandbox; whether a sandboxed commit could write the common git dir is not measured. A REQ that spans more than one repository is refused on Codex at the pre-flight, because the session has one working copy. |
| Routine tier (allowlisted) | Rendered as `prefix_rule(…, decision="allow")` lines into `.codex/rules/adlc-exec.rules` in the working copy, written for the run and never committed, plus one allow for the fence runner by its absolute path. It is a convenience for the routine tier: an allowed command runs outside the sandbox, which is what lets `git commit` reach the common git dir and `gh` reach the network. A prefix rule admits every argument after its tokens, so the exact entries widen: `git config user.email`, `git config user.name`, `npm ci`, `pwd`. A token prefix cannot name `-D`, `--force` or a `+refspec` at another position, and `wrapped-allow` reads `fail`, so these are omitted: `git branch`, `git push`, `git -C`. An omitted command matches no rule and runs inside the sandbox. No rule admits a fence that sources a partial: every toolkit fence runs through the fence runner. A project that sets `sprint.exec.allow_extra` in `.adlc/config.yml` is refused on Codex: the block declares `matcher: none`, and with no model of how Codex matches a rule the engine cannot judge an extra allow against the deny tier. Remove the entries for a Codex run. |
| Deny tier | Rendered `decision="forbidden"`, in the working copy's rule file and in the user policy file (next row). It holds the deny tier of `templates/permissions.yml` and the engine's own denies (`engine_deny`), which are `az repos pr`, `git push --force-with-lease`, `git worktree remove`, `git worktree prune`, `rm -r`, `rm -fr`, `adlc sprint-exec approve`, `adlc sprint-exec reject`, `adlc sprint-exec answer`, `adlc sprint-exec abort`, `adlc sprint-exec reissue`, `adlc sprint-exec resume`, `adlc sprint-exec run`. `ask-tier-deny` reads `pass`: a `forbidden` rule refused its command with an allow for a shorter prefix loaded (`deny-under-allow`), and on the measured runs the user policy file alone refused a denied command. No deny-tier entry is `deny_unsupported` at this result. Claude's `engine_deny` has three glob entries this one leaves out (`git push origin +*`, `git -C * push --force`, `git -C * push -f`): a prefix rule reads `*` as itself, so each would deny nothing. No allow matches `git push` or `git -C`, so those spellings run inside the sandbox. A `forbidden` rule is defense in depth: the gate on a one-way move is the approval halt. |
| User policy file | `~/.codex/rules/adlc-exec.rules`, the toolkit's own file beside your rule files. It holds the deny tier and `engine_deny` as `forbidden`, and never an allow. `adlc harness install --exec --harness codex` writes it, whole and atomically, under a lock, and a run's pre-flight writes it the same way when you have not installed it. **It persists across runs and projects, and it applies to your own Codex use too.** Measured under `codex exec`: with this file alone, a deny-tier command was refused. Codex reads the same folder for interactive sessions, so expect a deny-tier move such as `gh pr merge` or `rm -rf`, and `adlc sprint-exec approve`, to be refused there too, in any project (not measured interactively). Run those from your own shell. The engine checks the folder against its last record of it at launch and at resume: a missing or changed toolkit file, or a file added to the folder since, refuses the run, and `adlc harness install --exec --harness codex` records the folder again after a change of yours. A change to the folder found when the harness exits, or before a relaunch, blocks the run as a Rule B protocol violation and marks the engine's record of the folder, so every later run is refused until you have looked at the files and recorded the folder again with `adlc harness install --exec --harness codex`. It never edits your own rule files. |
| Trust | `trust_grant: user-config-entry`. Before each launch, the close-out's included, the engine appends one block, `[projects."<working copy>"]` with `trust_level = "trusted"`, to your user config `~/.codex/config.toml`, under a lock. It removes exactly that block when the harness exits, so none is held while a run waits for approval, and again through cleanup on failure, on abort and on the crash path. A revoke that could not finish stays recorded, and the next pre-flight or `resume` removes the entries of runs that have ended. After each revoke the engine compares the file with how it found it and logs `trust_file_changed`, naming any `[projects]` table that appeared, so an entry Codex wrote by itself does not pass unnoticed. Every other byte of the file stays as it was, and an entry that already trusted the path is recorded `pre_existing` and left. The reason is measured: when no entry covers its directory, `codex exec` writes `[projects."<main repo root>"] trust_level = "trusted"` into the user config by itself and keeps it, so an unattended run would leave the whole repository trusted for your later sessions. With the engine's entry in place Codex wrote nothing, and after the revoke the file was byte-identical to before. The grant is not what makes the rules load: on the measured runs the rule file and the working copy's config took effect either way. No engine write touches `hooks.state` or any other hook review. While a REQ-664 probe's recovery marker exists the engine refuses to launch, because the probe edits the same file. |
| Config surfaces | `.codex/` in the working copy. On the measured runs, with no trust entry of yours, both the rule file and a working copy's own `.codex/config.toml` widening `writable_roots` took effect (Codex had trusted the project by itself), so the engine treats the directory as live. In a linked worktree Codex did not read the main checkout's `.codex/`, so the working copy's `.codex/` is the whole project layer for a run, and the main checkout's committed rules do not widen it. Before every launch and every resume the engine renders the directory whole: the exec rule file and the project render of `.codex/config.toml`, nothing else. `.codex/hooks.json` and the committed `.codex/rules/adlc.rules` are made absent, and a stray file is deleted. Every write refuses a symlink, a hardlink or a non-regular file at any path component. A mismatch found before a launch or resume is repaired and logged (`rule_file_rerendered`). One found when the harness exits is a `config_surface_violation`: a Rule B protocol violation that blocks the run, and so does a directory the engine cannot verify. You relaunch a blocked run with `answer`, which renders the directory again. A sandboxed command could not write the directory on the measured runs; an allowed one can. |
| Bypass keys | Scanned before every launch and resume. A key set to a value the toolkit's own render does not set refuses the run, and so does a file that cannot be parsed. In `~/.codex/config.toml`: `sandbox_mode`, `approval_policy`, `profile`, `sandbox_permissions`, `sandbox_workspace_write.writable_roots`, `sandbox_workspace_write.network_access`. In the working copy's `.codex/config.toml`: `profile`, `sandbox_permissions`, `sandbox_workspace_write.writable_roots`, `sandbox_workspace_write.network_access`. Its `sandbox_mode` and `approval_policy` are the engine's own render, which the surface checksum holds. `sandbox_permissions` is listed because it widens what the sandbox admits: `codex exec --help` gives `-c 'sandbox_permissions=["disk-full-read-access"]'` as its own example of an override. A `writable_roots` entry that `adlc harness install --harness codex --writable-root` wrote also refuses an exec run, which does not need it. The engine reads your user config with a strict line reader, so a multi-line array or string, a top-level inline table or a top-level dotted key refuses the run, with a message naming the line: put such a value on one line, and a table under its own `[table]` header. |
| PR hygiene | No file the engine renders reaches the REQ's PR. A tracked one is restored from the blob recorded at launch, not from `HEAD`, before the final push and at cleanup; after the engine's own rebase of a held run, from the blob recorded at the relaunch. An untracked one is hidden through a per-worktree `core.excludesFile`. That needs git's `extensions.worktreeConfig`: **the pre-flight sets it to `true` in your repository's `.git/config` when it is absent, says so in one line, and leaves it set afterwards**, because other runs may depend on it. It refuses the run when the key is set `false`, when the repository sets `core.worktree` or is bare, or when the write fails. The shared `info/exclude` is never written. Tracked paths are also marked `skip-worktree`, which only hides them on a best-effort basis. The control is one gate at the halt: when the PR touches a rendered path or anything under `.codex/`, under any spelling, rename or letter case, `approve` is refused, and `--ack-gate-change` does not cover it. |
| Branch push | Through `fence-run`, not a rule (architecture ADR-9). A Codex prefix rule has no exact form: an allow for `git push -u origin <branch>` would also admit `<branch> --force`, so no `git push` allow is rendered, and an unmatched push runs inside the sandbox, which has no network. So Step 0's push is a `runner` fence on Codex. The runner runs exactly `git -C <worktree> push -u origin <branch>`, and only when `worktree` is the directory it was called from and `branch` is the branch checked out there, is a `feat/`, `fix/` or `chore/` branch, and carries the run's REQ id. The prompt says at that fence that a plain `git push` is refused on this harness and tells the model to re-run the runner line. Measured on 2026-11-18: the runner line, exactly as the prompt prints it, pushed the branch to a local bare origin. |
| ETHOS and hooks | `context_delivery: prompt`. Codex runs a project hook only after a person reviews it, keyed by its absolute path, and `codex exec` has no review step, so a working copy's hooks would be skipped silently. The engine makes `.codex/hooks.json` absent and puts ETHOS at the top of the prompt it builds. So the `session-record` sidecar is not written, and `/wrapup` finds the transcript by scanning Codex's session root (REQ-660). |
| Child environment | Passed through from your environment: `HOME`, `PATH`, `ADLC_HOME`, `ADLC_DISABLE_DELEGATE`, `ADLC_FORGE_MOCK`, `SSH_AUTH_SOCK`, `GIT_SSH_COMMAND`, `XDG_CONFIG_HOME`, `TMPDIR`, `LANG`, `TERM`. The engine adds `ADLC_EXEC_RUN` (the REQ id), `ADLC_EXEC_RUN_TAG` and the child's forge credentials. `CODEX_HOME` is not passed: the trust entry and the policy file are under `~/.codex`, and the run must read them there. No auth variable is needed, because a stored Codex login lives under `~/.codex`. The fence runner drops every `GIT_*` variable before it runs a fence, so `GIT_SSH_COMMAND` never reaches the branch push: if your push needs a custom ssh command, set it in your ssh config. |
| Nested runs | A launch, a dispatched operation or a resume started from inside a run is refused, by `ADLC_EXEC_RUN` in its environment and by its process ancestry, which still reaches a live exec process when the variable was cleared. A recorded process counts as live only while its run's harness or close-out is running and its start time still matches, so a reused process id refuses nobody. Where the caller's ancestry cannot be read at all, the launch is refused while any exec process is live. For `run`, the live runs are read from the state directory the caller's own environment names, so a process that also changes `HOME` or `XDG_STATE_HOME` is not caught by ancestry. `XDG_STATE_HOME` is deliberately not passed to the child, so where you set it, a nested `run` reads a different state directory even when the process changes nothing. A dispatched `approve` or `answer` is checked by the supervisor against its own records. The straggler sweep kills only its own run's processes, matched by `ADLC_EXEC_RUN_TAG` (REQ-659's amendment of 2026-11-18). Process ancestry does not hold against a process that detaches, and `answer` takes no token: both are declared residuals below. |
| `--allow-unverified` | Not needed while the verdict reads `verified`. When it does not, `adlc sprint-exec run --allow-unverified` launches anyway, with a loud line on every launch naming the probes, and the ledger records the invocation that received the flag. It is read from the command line only, never from config, state or the environment. It applies only to launches made by the invocation that received it, so a later `answer` needs its own flag, and never to `approve`, which re-checks the verdict, as the merge does again when it runs: a run approved behind a hold is halted again if the verdict changed meanwhile. It bypasses nothing else. Under it, with `ask-tier-deny` not `pass`, every deny-tier entry counts as `deny_unsupported`, and a local destructive one refuses the run. |

**What is lost on Codex, against Claude.** The sandbox contains only what no rule matches, so every allowed command, the fence runner and every fence it runs reach your filesystem and network (the residuals below). Approval cannot be pinned on the argv; it rests on the rendered config and the bypass scan. ETHOS reaches the model only in the prompt, and no session sidecar is written. `GIT_SSH_COMMAND` does not reach the branch push, and a user config with `writable_roots` refuses the run. The measured runs were single turns: a full pipeline run under the engine is not among them (the approval protocol is tested against this block through the fake harness), nor is a push over the network to a forge.

<!-- exec-residuals: codex -->
**Declared residuals under `--exec` on Codex.** The allow and deny rules are defense in depth for the routine tier, never the gate (Rule B). The gate is REQ-659's structural halt: the approval ledger, the pinned merge, the trial merge, the local diff gates, the child credentials, branch protection and the exit checks. What no rule here closes is declared, not chased:

- **Matching is spelling-level.** A rule is a token prefix matched against the command as Codex parses it. A deny-tier command in another spelling, behind `$()`, inside shell control flow or after an env-assignment prefix matches no `forbidden` rule: it runs inside the sandbox when no allow matches it either, and outside when one does.
- **On Codex an allowed command runs outside the sandbox.** So do the fence runner and every fence it runs. The sandbox contains only commands no allow matches. An allow that executes its arguments (`npx`, `npm run`, `find -exec`, `awk`, `git rebase -x`, `git fetch --upload-pack`, `gh api`) therefore runs arbitrary code with your filesystem and network, as it does on Claude, where there is no sandbox. The sandbox is not what stops a deny-tier move; the approval halt is.
- **Your own Codex config applies to every exec run.** Your rule files in `~/.codex/rules/` and your user config `~/.codex/config.toml` are read by each exec session as by your own, and a command one of your rules allows runs outside the sandbox. The engine records your rule files for drift during a run, and scans the user config for the bypass keys above, but it does not judge what your rules allow.
- **The sandbox's writable area includes the temp roots** (`/tmp`, `$TMPDIR`) as well as the working copy: on the measured runs an un-allowed command wrote under `/private/tmp`.
- **Semantic equivalents are outside the deny tier:** `git restore` and `git checkout -f`, both under routine allows, a `gcloud` deploy, `npm publish`.
- **`skip-worktree` hiding is defeatable:** `git add --sparse` and `git update-index --no-skip-worktree` undo it. The halt's exec-path gate is the control.
- **`rules_reload` is `unknown`, treated as live.** No probe measures whether Codex re-reads a rule file mid-session, so an edit to `.codex/` that an allowed command makes mid-run may take effect. The engine re-renders the directory before every launch and resume, and a change found when the harness exits blocks the run.
- **A fence run through `fence-run` is bounded by the reach audit** (REQ-682 ADR-7, `tools/adlc/tests/test_exec_reach.py`), **not by the allowlist or the sandbox.** Its git calls honour the repository's own config apart from the two pins, `core.fsmonitor` and `core.hooksPath`, which are defense in depth, and a model can write that config. So what a fence's push runs and where it goes stay open: `core.sshCommand`, a credential helper, `url.<base>.insteadOf`, `remote.origin.pushurl` and `remote.origin.push`. The runner pins no more because the orchestrator's own ssh and credential pins would break your push credentials. The branch push is bound to the run's REQ id through `ADLC_EXEC_RUN`, which a command can clear for itself, so that binding adds to the directory and checked-out-branch checks and does not replace them.
- **The nested-launch refusal reads the caller's own state directory for `run`.** A process inside a run that clears `ADLC_EXEC_RUN` and points `HOME` or `XDG_STATE_HOME` elsewhere finds no live run to descend from. Where you set `XDG_STATE_HOME`, the process need not point anything elsewhere: the child is not given that variable, so a nested `run` already reads a different state directory. What it then starts is a separate engine with its own pre-flight and its own approval gate; it cannot approve the run it came from.
- **Process ancestry does not hold against a process that detaches.** A process the model starts can detach: re-parented, out of the process group and with the run variables cleared, it is found by neither the nested-launch guard nor the straggler sweep. `answer` takes no token, so such a process can answer a blocked run's question in your name, and the run relaunches with that reply. That is REQ-659's design and holds on Claude as well; an answer token is proposed as a follow-up.
- **A runner line must keep its fence id quoted.** Codex matches no prefix rule against a command with a bare `#`, so a bare id runs the runner inside the sandbox, where its push fails. The engine prints the id quoted; REQ-664's `runner-prefix` probe does not exercise a `#`.
<!-- /exec-residuals: codex -->

### Antigravity CLI

The adapter is `harness/antigravity.yml` (REQ-658). Its facts are `agy` 1.4.12 as run on 2026-10-31, row by row in `.adlc/research/antigravity-compatibility.md`, from `adlc harness probe antigravity` and a set of recorded sessions. The render ran end to end against the real binary: ETHOS reached a session and a subagent, and the session sidecar recorded `harness=antigravity`. No lite REQ has been run end to end on `agy` yet, and that dogfood is the operator's to run.

```bash
./install.sh                                # builds the skills view
adlc harness install --harness antigravity  # renders ~/.gemini/config/agents/<name>.md and ~/.gemini/config/skills.json
```

Then run `/init --harness antigravity` (`/adlc:init --harness antigravity` on the plugin install) in a project. It writes `.agents/hooks.json` and `AGENTS.md`, and nothing runs `agy plugin`. `adlc harness render --harness antigravity --surface permissions` prints the rule set. No file in a repository supplies permissions, so that block goes in `~/.gemini/antigravity-cli/settings.json`, or `agy --settings <file>` for one session. Skills are slash commands under their bare names, such as `/proceed`. If you already have a `~/.gemini/config/skills.json`, install keeps it and prints the entry to add.

The toolkit has no Gemini CLI adapter. Gemini CLI is no longer available to individual accounts, Google moved them to Antigravity CLI, and the `gemini` row stays in `adlc harness detect` as it was. `gemini-extension.json` does not exist (REQ-665 BR-14).

**Nine skills are cut when you invoke them.** `agy` loads the first 24,000 bytes of a skill body and replaces the rest with `<truncated N bytes>`. The steps at the end of those skills do not reach the model, and nothing in the text says where the file is. Tell the model to read the whole `SKILL.md` before it starts.

<!-- harness-loss: antigravity -->
**What is lost on Antigravity CLI**

| What | On Antigravity CLI |
|---|---|
| Committed allowlist | no: no file in a repository supplies permissions (four candidate paths tested), so the rule set is printed for your own settings |
| Allowlist granularity | subcommand prefix (`token-prefix` in the adapter): `command(…)` is a word-by-word prefix, with no exact form, so `git config user.email`, `git config user.name`, `npm ci` and `pwd` take arguments |
| Deny-tier rendering | a hard `deny` in the printed block. It held headless, the model saw the refusal and carried on, and a person in a session cannot approve it: run a denied one-way move, `gh pr merge` included, from your own shell. It is user-level, so it applies in every project. Interactive is unverified |
| Shared-base fail-closed | `git push:*`, `git branch:*` and the `git -C` prefix are omitted and never restored, because a word prefix cannot name `--force`, `+refspec` or `-D` at any position, so each one prompts |
| Read-only reviewers | enforced: an agent's `tools:` list held on a recorded run, and a reviewer without Edit or Write has no tool for them |
| ETHOS in subagents | the ETHOS read line in every rendered agent, plus `SessionStart`, which fires again for a subagent's conversation and reached it on a recorded run. That needs the project's `.agents/hooks.json`, and an agent copy is user-level, so the read line stays |
| Subagent nesting depth | undocumented; the pipeline runner stays flat |
| `/sprint` workflow engine | unavailable |
| Transcript schema | `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript_full.jsonl`, reported by the hook payload; located, not parsed (REQ-660). `/wrapup` drafts from the conversation |
| Explicit skill invocation | `/name`, or by naming the skill in your prompt; a skill also activates from its description (recorded). No skill name collides with a slash command in `agy`'s reference, as read on 2026-10-31, and a built-in added later would shadow a skill of the same name |
| Headless deny status | a hard `deny` held in the `lone-deny` and `deny-under-allow` launches, but `ask-tier-deny` itself reads `unknown`: its `allow-only` controls ended early, so the probe's record is unverified. A re-run is owed |
| Fences, not commands | no rule matches a partial-sourcing fence, in any variant tried, because a compound line is judged part by part. `fence.partial-source` is omitted, so each fence prompts in a session and ends a headless run |
| `git -C` | omitted (see the shared-base row): every `git -C <path> <sub>` prompts |
| Skill body cap | a body past 24,000 bytes is cut when invoked. `agy` cuts `analyze`, `architect`, `bugfix`, `init`, `proceed`, `spec`, `sprint`, `template-drift` and `wrapup` |
| Skill companions | a skill's companion files, such as `proceed/phases-state.md`, sit outside the workspace. They prompt in a session, and a headless run ends at the first one, unless your settings allow `read_file(<toolkit root>)` |
| ETHOS after compaction | not re-injected: `agy` has no compaction event, and `SessionStart` is documented as once per session. Unverified |
| Headless exit status | `agy -p` ends at the first tool that would need a prompt, and exits 0 with an empty response and `status: SUCCESS`. Only a hard `deny` leaves the run going. Read stderr or `denied_actions` in the JSON, not the exit code. `3` is a run a hook terminated, `1` an error before the model, `2` a bad flag |
| Trust | `agy -p` loaded project hooks, skills and agents with no trust record, in a repository and in a linked worktree, so a `.agents/hooks.json` in a repository you open runs. The TUI's trust dialog is unverified |
| Default mode | the printed block carries no `agentMode`, because it is user-level and would auto-approve edits in every project. Pass `agy --mode accept-edits` for a session that should |
| Model tiers | `tier:` does not reach `agy`: an agent loads only with `inherit`, `flash` or `pro`, and no run showed what those resolve to, so `model:` is omitted and the session's model runs |
| Plugin route | none. `agy plugin install` on this repo loads no skill, no agent and no hook, and a native manifest names skills `adlc:..:<name>` and cannot pass `--strict` |
| `--dangerously-skip-permissions` | auto-approves every tool prompt. `agy`'s docs say deny rules apply in every mode, and no run tested that. Nothing in the toolkit passes it or sets an auto-approve mode, and your own use of it is outside the toolkit |
| Gemini CLI | no adapter: see above |

`unverified` in this table, and also: whether `agy` reads `~/.agents/skills`. The adapter does not depend on that.

**Declared residuals.** What no allowlist or deny rule closes. They are declared, not chased:

- Matching is spelling-level.
- Allows that execute their arguments (`find -exec`, `awk system()`, `sed e`, `npx`, `npm run`/`exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the rule does not match.
- Semantic equivalents (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- `agy` judges a compound line part by part, so `;`, `&&` and `$()` are parsed, and how far that goes is unverified.
- The `env-prefix` and `shell-opener` wrapper shapes stay `unverified`, and no REQ-664 result lifts an omission resting on them.
- The dogfood notes record the prompt count (REQ-658 BR-15).
- The allowlist is not the gate: REQ-659's structural halt is, under the exec engine.
<!-- /harness-loss: antigravity -->

### `ADLC_HOME`

The toolkit's machine state (the id counters and their locks, the reservations ledger, the machine config, the delegate venv, the skills view) lives under one directory, `ADLC_HOME`, which defaults to `~/.claude`. With it unset, every path is exactly where it has always been: nothing moves. Set it to an absolute path to keep the toolkit's state somewhere else:

```bash
ADLC_HOME="$HOME/.adlc" ./install.sh     # set it in your shell profile too, so every session sees it
```

`install.sh` then creates `skills`, `agents`, `adlc/config.yml` and the skills view under that directory, and still links `~/.claude/skills` and `~/.claude/agents` to the clone, because Claude Code reads those and every skill's shell falls back through `~/.claude/skills`. A set `ADLC_HOME` that is empty or relative is an error that names it; nothing falls back to `~/.claude` silently. `ADLC_CONFIG`, when set, still names the config file outright. That override is for a machine starting fresh there; to move an existing install, use `--migrate-home` below.

### Moving an existing home: `--migrate-home`

`install.sh --migrate-home <dir>` moves the toolkit's machine state out of `~/.claude` and `--back` reverses it. It is opt-in, and a plain `./install.sh` never migrates. Read the plan first:

```bash
./install.sh --migrate-home "$HOME/adlc-home" --dry-run    # every check and action; changes nothing
./install.sh --migrate-home "$HOME/adlc-home"              # do it
./install.sh --migrate-home "$HOME/adlc-home"              # run again: zero actions, or a repair
./install.sh --migrate-home --back                     # reverse it
./install.sh --migrate-home "$HOME/adlc-home" --prune-backup   # drop the backup
```

- **What moves**: the machine config, the three id counters, the reservations ledger, the delegate venv (rebuilt at the new home, which needs network access to the package index), the skills view and the launchd helper. `<dir>/skills` and `<dir>/agents` are created as links to the clone. The `~/bin` wrappers, the launchd plist, a harness `skills.json` that names the view, and `~/.agents/skills` are re-stamped to the new home.
- **What never moves**: `~/.claude/skills`, `~/.claude/agents`, `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/adlc/plugin-root`, the logs under `~/Library/Logs`, and anything under `~/.claude` the toolkit did not create.
- **What stays behind at the old paths**: a symlink at each counter and at the config, so anything reading the old path still sees the one value, and a file at each old lock path, so an out-of-date `id-alloc.sh` fails loud within its own five-second budget instead of allocating under a second lock. The ledger gets neither: every shipped reader refuses a symlinked ledger.
- **How a session finds the home**: `export ADLC_HOME="<dir>"` in the REQ-519 block of your login shell's rc file, and a pointer file, `~/.claude/.adlc-home`, for a session that never sourced it (a GUI-launched Claude Code, launchd, a `/bin/sh` fence). A set `ADLC_HOME` that disagrees with the pointer is refused everywhere, and a pointer naming a directory that does not exist is an error, never a fall-through to `~/.claude`.
- **When it refuses**: while a consumer repo's vendored partials are behind (run the `/template-drift` line it prints in that repo), when consumer currency cannot be proven, when an allocation lock is held, when `<dir>` holds anything that is not a toolkit home, when `ADLC_HOME` or the pointer names another home, while an earlier migration's backup is in the way, while a `harness probe` left a recovery marker, or when the venv cannot be rebuilt. Each refusal prints its evidence and a fix, and nothing on disk changes.
- **The backup**: `~/.claude/.adlc-home-backup-<time>/` holds a copy of every moved file and every stamped file. `--back` removes it, `--prune-backup` removes it, and nothing else does. A failed flip is undone from it before the command exits. `--back` works after a prune: it reads the live files.

`adlc doctor`'s `home-layout` check verifies the result end to end. After `--back`, open a new shell: one opened before it still exports the old `ADLC_HOME`.

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
