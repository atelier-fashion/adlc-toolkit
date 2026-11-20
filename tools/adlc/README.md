# tools/adlc — the `adlc` umbrella CLI

`adlc` is the toolkit's user-facing command-line entry point. It is a
**pure-standard-library** Python CLI (no third-party deps, no venv) so it runs
on any machine that has the toolkit, cloned or installed as the Claude Code
plugin — including one that has never opted into delegation. Subcommands are
registered in a data-driven table (`SUBCOMMANDS` in `adlc.py`), so future REQs
add commands without touching dispatch logic.

How it reaches your PATH depends on the install route (REQ-669):

- **Plugin route.** The plugin's SessionStart hook appends `<plugin root>/scripts`
  to the PATH of the Claude Code session, after your own entries.
  [`scripts/adlc`](../../scripts/adlc) is a POSIX shim that runs
  `python3 <plugin root>/tools/adlc/adlc.py`. Outside a Claude Code session, run the
  shim by path; the hook records the plugin root in `~/.claude/adlc/plugin-root`:

  ```bash
  "$(cat ~/.claude/adlc/plugin-root)/scripts/adlc" doctor
  ```

- **Symlink route.** The root [`install.sh`](../../install.sh) writes a shim at
  `~/bin/adlc`.

On either route you can also run it directly from the toolkit root:

```bash
python3 tools/adlc/adlc.py doctor
adlc --version
```

## Subcommands

| Command | Purpose |
|---------|---------|
| `doctor` | Read-only environment health check (below). |
| `agents render` | Render `agents/*.md` `model:` frontmatter from tier classes + config (below). |
| `renumber` | Rename an artifact id repo-wide, collision-safe, dry-run by default (REQ-518). |
| `harness detect` | Read-only: which agent harnesses are installed, and whether each one's skills directory reaches this toolkit (REQ-654, below). |
| `harness probe` | The plan's §6 experiments against one installed harness, with one committed JSON result per harness (REQ-664, below). |
| `sprint-exec run \| resume \| status \| approve \| reject \| answer \| abort \| reissue` | The `/sprint` exec engine, a program that runs one headless harness per REQ and performs every one-way move itself (REQ-659, below). |
| `harness render \| install \| doctor \| drift` | The adapter framework: render any surface through `harness/<name>.yml`, write a harness's user-level surfaces, `render-currency:<name>`, and the project layer's template-posture drift (REQ-657, below). |
| `regression-check mode \| check` | Read-only: the project's `bugfix.regression_test` setting, and whether every resolved bug still has its regression test or a waiver (REQ-691, `regression_check.py` below). |

Each is one entry in the data-driven `SUBCOMMANDS` table (REQ-519 BR-11).

## Machine state: `ADLC_HOME` (REQ-654)

Every machine-state path this CLI reads — the id counters and their locks, the
machine config, the delegate venv, the skills view — is under `ADLC_HOME`,
default `~/.claude`, resolved by [`adlc_home.py`](adlc_home.py). With it unset
every path is the one it always was. `ADLC_CONFIG` still names the config file
outright. A set `ADLC_HOME` that is empty or not absolute stops `adlc doctor`
before any check, with exit 2 and a message naming the variable.

The rule is `$ADLC_HOME`, else the pointer `~/.claude/.adlc-home`, else `~/.claude`
(REQ-663 BR-8). `install.sh --migrate-home` writes the pointer, so a session that
never sourced the rc file resolves a migrated home. A set `ADLC_HOME` that differs
from the pointer, and a pointer that is not a regular file, holds no absolute path,
or names a directory that does not exist, are errors at every resolver, never a
fall-through. Doctor reports those two states through `home-layout` alone, with exit 1,
because every other check reads the home that did not resolve. Its `profile:` line
names the home and what decided it.

The rule is written out three times — `adlc_home.py`,
[`partials/adlc-home.sh`](../../partials/adlc-home.sh) and
`tools/delegate/_machine_config.py::adlc_home` — because a partial cannot import
Python and the delegation tools import nothing from here;
[`tests/test_adlc_home.py`](tests/test_adlc_home.py) drives all three over one
input vector. Paths Claude Code owns (its config dir and plugin cache, the
`~/.claude/skills` and `~/.claude/agents` mounts) are not machine state and stay
where Claude Code reads them; the `adlc-home` lint keeps the two apart.

## `adlc doctor`

A **strictly read-only** diagnostic. It mutates nothing. It exits **non-zero iff
any non-skip check fails** — `skip` (a macOS-only check on Linux, a delegation
check when delegation is off) never contributes to failure, so the verdict stays
honest on every machine.

```bash
adlc doctor                              # run every check
adlc doctor --checks forge,delegate-gate     # run only the named checks
```

Each failing check prints a **copy-pasteable** remediation — a literal command or
exact file edit, never "see the docs". Run the printed `-> fix:` line verbatim
and re-run doctor; it should turn green. Every path, interpreter and install key
a fix carries is quoted with `shlex.quote`, so a `'`, `$(` or `;` in a home
directory or a cache path stays text when the line is pasted into a shell. The
tables below show placeholders such as `<root>` unquoted.

### Checks

| id | passes when | fails → remediation | skip when |
|----|-------------|---------------------|-----------|
| `plugin-route` | symlink route: always (reports the root and `VERSION`). Plugin route: this copy is the one Claude Code loads, `~/.claude/adlc/plugin-root` names it, `scripts/adlc` is executable, and inside a Claude Code session `adlc` is on PATH (REQ-669 ADR-7). Fails on either route when route detection itself failed | `CLAUDE_PLUGIN_ROOT=<root> sh <root>/scripts/session-start.sh` (the SessionStart hook's own command); `chmod +x <root>/scripts/adlc`; `export PATH="$PATH":<root>/scripts`; `<live root>/scripts/adlc doctor` for an older cached copy; `claude plugin uninstall <key> && claude plugin install <key>` (reinstall) when the copy has no `plugin.json` naming `adlc` or no `scripts/adlc`; `claude plugin details adlc` when the install record cannot be read, the running cache copy is not installed, or route detection failed | — |
| `skills-symlink` | `~/.claude/skills` is a symlink into a git checkout, and so is `<ADLC_HOME>/skills` when `ADLC_HOME` names another directory (REQ-654) | `ln -sfn <root> <link>`, one line per bad link | plugin route |
| `agents-symlink` | `~/.claude/agents` resolves to `<root>/agents`, and so does `<ADLC_HOME>/agents` when `ADLC_HOME` names another directory | `ln -sfn <root>/agents <link>`, one line per bad link | plugin route |
| `doubled-install` | not both installs at once: no symlink install, or no adlc plugin install. Cache copies an uninstall left behind are not an install | one fix per way out: `claude plugin uninstall adlc@adlc-toolkit` (keep the symlink install), or `rm` of the two links, plus `~/bin/adlc` when it runs the clone (keep the plugin) | — |
| `skills-view` | `<ADLC_HOME>/adlc/skills-view` holds a link to `<clone>/<name>` for every `<clone>/<name>/SKILL.md`, nothing dangles, and nothing else is linked (REQ-654). A skill added to the clone shows up there at the next `install.sh` run | `'<root>/install.sh'` | plugin route |
| `agents-skills-mount` | `~/.agents/skills` is a link to the view, or a directory of yours holding a link to every toolkit skill (names your own entries already use are listed, not failed) | `'<root>/install.sh'`; for a foreign dangling link or a file there, `mv` it aside first | plugin route |
| `toolkit-clean` | clone is on a branch and not dirty | `git -C <root> checkout main` / `git status` | plugin route |
| `path-shims` | `adlc` is on PATH and `adlc --version` runs | `./install.sh --repair`, restart shell | plugin route |
| `gh-present` | `gh` (GitHub CLI) is on PATH | per-OS install line (`brew install gh`, …) | — |
| `forge` | resolved forge provider's backend CLI present + auth valid + read-only API probe (github: `gh auth status`; azure-devops: `az account show` or PAT env var). **Supersedes the former `gh-auth` check** (REQ-520). | provider-specific (`gh auth login`; `az login` / set the PAT env var; or install `az`) | repo has no git remote |
| `git-identity` | `user.name` and `user.email` set | `git config --global user.email …` | — |
| `delegate-gate` | delegation enabled and reachable | (see below) | delegation not opted in (default) |
| `pyyaml` | PyYAML imports in the interpreter `adlc` runs under — the one that parses `~/.claude/adlc/config.yml` (REQ-609). Says so when the delegate venv is being bypassed because it has no PyYAML of its own | symlink route: `<root>/install.sh --with-delegation` (creates/refreshes the venv, which pins the version). Plugin route: `'<interpreter>' -m pip install --user '<the pyyaml line of tools/delegate/requirements.txt>'`. For a venv that exists without PyYAML, either route: `~/.claude/delegate-venv/bin/pip install -r <root>/tools/delegate/requirements.txt` | no venv and no project config, **and** either no machine config or one that is byte for byte the delegation-off scaffold install.sh and the SessionStart hook write — nothing PyYAML would read changes a setting |
| `counters` | each `<ADLC_HOME>/.global-next-{req,bug,lesson}` is numeric, no stale lock | `printf <n> > …` / `rmdir …lock.d` | a counter that doesn't exist yet (first run) |
| `launchctl` | (macOS) delegate setenv LaunchAgent loaded *when delegation is on* | `launchctl bootstrap gui/$(id -u) <plist>` | Linux (macOS-only); delegation off |
| `template-version` | project `.adlc/` scaffold present | run `/template-drift` to compare | run outside a consumer project |
| `home-layout` | **REQ-663 BR-12.** On a migrated machine, that the pointer, the rc line and any `ADLC_HOME` agree; every moved file is under the home; each old counter and config path is a symlink to it and no regular file remains; each old lock path is a tombstone, not a directory; the shim, wrappers, plist and any harness `skills` surface carry the home; the venv passes the interpreter probe; the view, `~/.agents/skills`, `<home>/skills` and `<home>/agents` resolve; `~/.claude/skills` still resolves to the clone; and nothing the migration retires is left behind. [`home_layout.py`](home_layout.py) is the one statement of this, and `migrate_home.py` reads the same findings as its plan | `<clone>/install.sh --migrate-home <home>`, a repair, or `--back`; `unset ADLC_HOME` when only the environment disagrees | no pointer and nothing a migration leaves at the old paths, which includes a REQ-654 `ADLC_HOME` override |
| `consumer-sync` | every consumer repo under `$ADLC_REPOS_ROOT` (default: the parent of the current repo's main worktree, as id-alloc reads it) whose `.adlc/partials/` matches the canonical partials by content (REQ-654 BR-8), and whose project layer `adlc harness drift --harness claude --opted-in` finds neither `stale` nor `missing`. The baseline is named first (branch, `partials/` dirty or not, distance behind `origin/<default>` as of the last fetch); a checkout that is not clean-and-current is compared through `origin/<default>`, the plugin route against `adlc plugin <version>`. It never fetches and writes to no repo. A repo with something stale is looked up read-only with `gh repo view`: one GitHub reports archived is skipped by name and needs no fix; any other outcome (no `gh`, no network, not on github.com) leaves it stale and says the archive state is unknown | one line per stale repo: `cd '<repo>' && claude -p /template-drift` (`/adlc:template-drift` on the plugin route), which re-renders the project layer only with your approval because `--force` drops project additions | no consumer under the root; **unverified-baseline** (no `origin/<default>` ref, or no readable plugin version) is a SKIP that names the repos that differ and asserts nothing; a project layer that could not be compared (the toolkit's `harness/` or render templates differ from the baseline ref, or a file cannot be read as settings) is a SKIP that names why when nothing else is stale; so is every consumer being archived |
| `harness:claude`, `harness:copilot`, `harness:codex`, `harness:gemini`, `harness:cursor` | (report-only) the binary is on PATH; reports its version and whether its skills directory reaches this toolkit. Replaces the former `claude-code` check (REQ-654) | never fails the verdict | the binary is not on PATH |

### The `delegate-gate` check (reuses REQ-515)

This check does **not** reinvent delegation config resolution — it builds on the
shipped REQ-515 surface:

- It sources [`partials/delegate-gate.sh`](../../partials/delegate-gate.sh) for
  the 0/1/2 gate verdict and reads `ADLC_DELEGATE_GATE_REASON`.
- It reads delegation config via
  [`tools/delegate/_common.parse_delegate_config`](../delegate/_common.py) (through a
  subprocess probe, so `adlc` keeps no hard import dependency on the delegate
  module).

Mapping:

| gate rc | meaning | doctor result |
|---------|---------|---------------|
| 0 (`ok`) | delegated path live | **PASS** |
| 1 (`not-opted-in` / `disabled-via-config` / `disabled-via-env`) | opt-in off | **SKIP** (reason shown) |
| 2 (`no-binary`) + config `enabled: false`/absent | not installed, not requested | **SKIP** |
| 2 (`no-binary`) + config `enabled: true` | **misconfigured** | **FAIL** → `./install.sh --with-delegation`, or set `delegate.enabled: false`. On the plugin route only the config edit: the plugin ships no delegation CLIs |

### Install routes (REQ-669 ADR-7)

Doctor runs on one of two routes, and `Profile.route` records which. It is
derived once, from the real path of the running copy, and printed on the
`profile:` line:

- **`plugin`** when that copy is inside `~/.claude/plugins/cache/`, or is a root
  `~/.claude/plugins/installed_plugins.json` records for `adlc@<marketplace>`. A
  local-path marketplace runs the plugin from its source directory, not the
  cache, so its root is read from `known_marketplaces.json` and the
  marketplace's own `marketplace.json`.
- **`symlink`** otherwise. This is the route whose checks all run, so a machine
  doctor cannot place is never spared a check. That includes a contributor's
  clone that `~/.claude/skills` links *and* a local-path marketplace installs:
  it stays `symlink`, so the symlink health checks still run on it, and
  `doubled-install` reports the doubling.

When `CLAUDE_CONFIG_DIR` is set to an absolute path, Claude Code keeps its
plugins there, so the doctor reads `plugins/cache/`, `installed_plugins.json`
and `known_marketplaces.json` under it instead of `~/.claude` (details name it
as `$CLAUDE_CONFIG_DIR/...`). The pointer, the machine config and the symlink
install stay under `~/.claude`, where the hook and `install.sh` write them. A
relative value is ignored.

`git rev-parse` plays no part: a cache copy has no `.git`, and `~/.claude` can
sit inside a dotfiles repo. The root itself comes from `toolkit_root.py`.

The adlc plugin install is read from two signals: the install record and the
cache (`~/.claude/plugins/cache/*/adlc/*/` with a `plugin.json` naming `adlc`,
skipping a version that carries Claude Code's `.orphaned_at` marker). The
record wins when it exists, and its `installPath` names the live copy, since
older versions stay in the cache after an update. A well-formed version-2
record with no adlc entry is **absent** whatever the cache holds: that is what
`claude plugin uninstall` leaves, and any copies still in the cache are named in
the detail as leftovers Claude Code does not load, not as a conflict. A record
that cannot be read, has a schema other than version 2, names an `installPath`
without the plugin's manifest, or holds an install key that is not
`adlc@<marketplace>` (`^adlc@[a-z0-9][a-z0-9-]*$`) makes the install
**unknown**. Unknown is a FAIL wherever it matters: `plugin-route` cannot
confirm the running copy, and `doubled-install` cannot rule out a doubling next
to a live symlink install (LESSON-581). The plugin install is read once per run
and carried on the profile, so the route and both route checks see the same
reading.

If route detection itself raises, the route falls back to `symlink`, so every
check runs, and `plugin-route` FAILs saying detection failed, with
`claude plugin details adlc` as the fix. The `profile:` line then reads
`route=symlink (route detection failed)`.

A remediation that runs `install.sh` is printed on the symlink route only, and
not at all when route detection failed. Run from the plugin's copy,
`install.sh` would symlink that copy into `~/.claude` and double the install.
A check with more than one way out prints one `-> fix:` line per way.

Two gaps are known:

- The doctor does not read `enabledPlugins` in `~/.claude/settings.json`. A
  plugin disabled there still counts as installed, so `doubled-install` can
  report a doubling that Claude Code is not loading.
- On a plugin-only machine whose `python3` has no PyYAML (a fresh Mac's system
  Python), `pyyaml` SKIPs while `~/.claude/adlc/config.yml` is still the
  SessionStart hook's unedited scaffold, which reads the same without PyYAML.
  The scaffold text is read off `scripts/session-start.sh`, not copied
  (`test_config_scaffold_parity.py` pins it to both writers). Once that file is
  edited, or a project `.adlc/config.yml` exists, `pyyaml` FAILs there, and the
  fix it prints is the pinned `pip install --user` for that interpreter.

### Which interpreter parses the config (REQ-609 BR-8 / ADR-2)

The ADLC config is parsed with PyYAML behind a strict schema
([`tools/delegate/_machine_config.py`](../delegate/_machine_config.py)), and both
consumers — the delegation opt-in and `forge_config.py` — read it through that one
loader. So *which* interpreter runs it matters, and there is exactly **one rule**:

> Prefer `$HOME/.claude/delegate-venv/bin/python3` when it is a regular
> executable file **and** that venv carries a `yaml` package directory under
> `lib/python*/site-packages/`; otherwise `python3` from `$PATH`.

Both halves earn their place. The venv exists only after `--with-delegation`, and
a shim that `exec`s a missing interpreter would break `adlc doctor` on exactly the
machine that most needs it (LESSON-395) — hence the fallback. And a venv created
*before* REQ-609 carries `openai` and no PyYAML, while a plain `./install.sh`
rewrites the shim and refreshes no venv — so "the file exists" is not enough:
preferring such a venv points every config read at the one interpreter on the
machine that cannot parse the file, and `forge_config.py`'s `dependency-missing`
carve-out then silently overrides a written `forge.provider` with origin-URL
auto-detection.

The rule is written out at **three** sites, because a shell partial cannot import
Python and a Python module cannot be sourced by `sh`. Change one, change all three:

| Site | What it selects for |
|------|---------------------|
| `ensure_adlc_shim` in the root [`install.sh`](../../install.sh) | every `adlc` invocation |
| `checks._delegate_interpreter()` | the two config probes and the `pyyaml` check |
| `_adlc_forge_python` in [`partials/forge.sh`](../../partials/forge.sh) | every `/proceed` PR operation |

`install.sh` also reports, on every run, whether an existing venv has PyYAML, and
prints the one-line fix when it does not — it never installs into a venv the
operator did not ask to touch, and never aborts over it.

Where PyYAML is missing there, the loader returns `malformed / dependency-missing`:
the delegation consumer refuses (fail-closed, REQ-609 BR-9) and `forge_config.py`
proceeds *unconfigured* after the same single stderr line — the one carve-out, and
only for that reason class. Every **file** defect (unreadable, undecodable,
over-cap, a duplicated key anywhere in the document, a top level that is not a
mapping) refuses for both consumers.

## `adlc harness detect` (REQ-654)

```bash
adlc harness detect            # one row per harness
adlc harness detect --json     # [{name, binary, state, path, version, mount, last_probe, probe_file}, ...]
```

Read-only and pure stdlib ([`harness.py`](harness.py)). For each of `claude`,
`copilot`, `codex`, `gemini` and `cursor` (whose CLI is `agent`, or the
`cursor-agent` alias):

- **state**: `present` when the binary is on `PATH`, else `absent`;
- **version**: the first line of `<binary> --version`, run with stdin closed in
  its own process group under a 3-second timeout. A non-zero exit, a timeout or
  empty output is `unknown`, never an error;
- **mount**: `n/a` when absent; otherwise `mounted` when the harness's skills
  directory reaches this toolkit — for Claude, `~/.claude/skills` is the
  symlink install or the adlc plugin is installed; for the other four, a skill
  under `~/.agents/skills` resolves into the toolkit — else `not-mounted`.

- **last_probe** (REQ-664): the `date` of this repository's
  `.adlc/research/harness-probes/<name>.json`, `never` when there is none or the
  cwd is not in a repository, `unreadable` when it does not parse; `--json` adds
  `probe_file`, its path or `null`.

It exits 0 whenever it ran: no harness at all is a result. `adlc harness` with no
verb, or another one, prints usage and exits 2.

## `adlc harness probe` (REQ-664)

```bash
adlc harness probe --list                       # the catalogue; works anywhere
adlc harness probe codex --dry-run              # the plan and the files it would edit; launches nothing
adlc harness probe codex [--only <probe>]... [--keep] [--timeout <s>]
adlc harness probe codex --recover              # restore user files after a crashed run
```

The scripted, repeatable form of `.adlc/research/multi-harness-plan.md` §6
([`harness_probe.py`](harness_probe.py), pure standard library). Against the
harness binary already installed, it builds a throwaway git repository under the
temp root (a bare `origin` and a linked worktree), writes the project-local hook,
allowlist, skill and trust fixtures a probe needs, launches the harness headlessly
with a short single-purpose prompt, and decides the verdict from a side effect it
checks itself: a ref in the bare remote, a sentinel file, or the nonce reversed in
the final assistant message. What the model says it did is never evidence. Then
it removes the repository, restores every user-level file byte for byte, and
writes `<repo root>/.adlc/research/harness-probes/<harness>.json`, which is meant
to be committed (credentials and email addresses redacted, `$HOME` written as `~`). The probes need
nothing from `harness/`, no renderer and no mount in any harness: the per-harness
facts are one table in the module (`PROFILES`).

**Every launch is a model session on your account.** The command prints the
launch count before the first one (a full run is 17 or 18 launches; `ask-tier-deny`
alone is seven), and `--dry-run` shows the plan without paying. There is no
confirmation prompt: invoking the command is the consent.

### The catalogue

| id | §6 item | harnesses | decided by |
|---|---|---|---|
| `git-write-main` | 6.1a (headless half), 6.3 (allow half) | all | `main` in the bare remote advanced to a commit holding the staged nonce file |
| `git-write-worktree` | 6.1b | all; on codex two sub-variants, `root-is-worktree` and `writable-roots-repo` | the same, for `probe-wt` pushed from the linked worktree |
| `ask-tier-deny` | 6.3 | all | the deny held: its effect absent, a config witness present, the reversed nonce in the reply; gated on four controls (below) |
| `skill-activation` | 6.4 | gemini | the skill's sentinel |
| `shell-timeout` | 6.6 | all | `touch <start> && sleep 125 && touch <sentinel>` left its sentinel at least 125 s after the start marker (default shell timeout ≥ 120 s) |
| `trust-then-headless` | 6.8 (trust + load) | all | two halves: `hooks-loaded` (a session-start hook's sentinel) and `allowlist-loaded` (a project-only allow worked); copilot has no project-local allow form, so its status is `hooks-loaded` alone |
| `session-start-context` | 6.8 (injection) | all | the reversed nonce a session-start hook added to the context |
| `stdin-prompt` | 6.12 | all | a 420-line prompt on stdin, nonce on line 250; with and without the prompt flag |
| `fence-vs-allowlist` | 6.11 | all | partials/README.md's sourcing fence, byte for byte, under `routine-only`, `broad-sh` and `broad-first-token` allowlists; plus the `runner-prefix` variant's thirteen launches (below), decided apart |
| `transcript-locate` | 6.9 | all | a session file under the harness's transcript root naming the run; its first 20 records, redacted, become `fixtures/<harness>.jsonl` |
| `arg-substitution` | 6.10 | claude | a skill with no `$ARGUMENTS` whose fence writes `"$1"` to a sentinel: `hello` passes, empty or a literal `$1` fails |

Not probed, and recorded as such in the result's `coverage`: 6.2 (a documentation
question), 6.5 (answered by `.adlc/research/antigravity-compatibility.md`, REQ-658) and 6.7 (answered by REQ-654's skills-only
view). 6.1a is recorded as `headless only`; the interactive half is REQ-655's.

#### `runner-prefix` (REQ-707)

`/sprint --exec` runs every toolkit fence through one program, `<ToolkitRoot>/tools/adlc/fence-run`,
admitted by one absolute-path prefix allow (REQ-682). `runner-prefix` asks whether that allow is
a boundary on this harness: it admits the runner with its arguments, and nothing past it.
REQ-662 BR-11 makes it a hard probe for every non-Claude exec adapter.

The probe writes a stub runner at `<run_dir>/tk/fence-run`, outside the probe repo the way
ToolkitRoot sits outside a working copy, and a sibling `fence-run-x` that no allow names. The
stub records its `$0`, its arguments and `X`; `fence-run fail` exits 1. Each launch runs
`touch <witness>` on its own, then one fenced line, then replies with the reversed nonce:

| launch | allow | the fenced line |
|---|---|---|
| `runner-positive` | routine + the runner | `<stub> run probe` |
| `runner-baseline` | routine only | `<stub> run probe` |
| `runner-sibling` | routine + the runner | `<stub>-x run probe` |
| `runner-env-prefix` | routine + the runner | `X=1 <stub> run probe` |
| `runner-subst`, `runner-backtick` | routine + the runner | `<stub> run "$(<stub>-x)"`, ``<stub> run `<stub>-x` `` |
| `runner-redirect` | routine + the runner | `<stub> run probe > <target>`, `<target>` = `<repo>/.probe/redirect-<launch>` |
| `runner-semicolon`, `runner-and`, `runner-pipe`, `runner-background` | routine + the runner | `<stub> run probe` then `;`, `&&`, `\|` or `&`, then `<stub>-x` |
| `runner-or` | routine + the runner | `<stub> fail \|\| <stub>-x` |
| `runner-newline` | routine + the runner | `<stub> run probe`, a newline, `<stub>-x` |

Every tail runs `<stub>-x`, never a routine command: a `touch` tail would be admitted on its
own by a harness that checks each statement, and fail the very harness that should pass.

Each launch reads **admitted** (its effect appeared), **refused**, or `unknown`. Refused needs
more than an absent effect: the witness ran, the ask was reached, and the asked line was
submitted. That means the line is in a `command` field of the harness's own JSON tool-call or
denial records (model text, such as the reply or a Codex `agent_message`, is never read), or
the harness's refusal on stderr names the stub while nothing of the line ran. Otherwise the launch is `unknown`:
`ask-split` when the runner ran but the rest did not, `not-attempted` when nothing ran. A
model that tidies or skips the command therefore never turns a control into a refusal.

`runner-redirect`'s target sits in the working copy's `.probe/` on every harness, and its
effect is the target **holding the runner's own output**. The stub prints a marker line once
its sentinel is written, and the redirect carries it into the target; a model that forges the
marker can only make the control read admitted, the safe side. A target that is a directory
or a symlink, or holds anything else, reads `ask-split`: the shell could not open it, so the
stub never ran either way. Codex runs a command no allow names inside its sandbox, so the shell can create a
working-copy target for a line it refused, while the stub cannot write its sentinel outside
the sandbox: an empty target is no admission. A runner sentinel without the marked target
(the stub run apart from the line, or the target removed) reads `ask-split` and is retried,
never `refused`, because a stub whose redirect failed never runs. The fake's
`sandboxed-refusal` flag (codex only) plays that sandbox, and `fallback-run` a model that then
runs the stub on its own.

The prompt says what the stubs are (test stubs that only append their arguments to a marker
file) and tells the model to run both commands even where a path is outside the workspace
or it expects a block, because the project's rules decide what runs. A launch that still
measured nothing (the witness absent, the line never submitted or tidied, or no reversed
nonce) is launched again from fresh state, as `<launch>r2` to `<launch>r5`, at most five
attempts; `evidence.attempts` records how many it took, and each attempt counts as a launch.
A measured reading is never retried, so a retry cannot turn an admission into a refusal. That
includes a line that was submitted and left no effect when the model then skipped its reply:
it reads refused, not "ask not reached" (BUG-285).
codex-cli 0.166.0's model skipped the commands on about half its launches without these
(BUG-279). With them it ran every shape but `runner-redirect`, whose target then sat outside
the workspace with codex's other sentinels; it never submitted a redirect there. The target
now sits in the working copy (REQ-707, amended 2026-11-16), and codex's model submits it there:
the live runs since read it refused.

`runner-prefix` is then decided in this order:

1. **Positive.** `runner-positive` refused is `fail`; `unknown` is `unknown`.
2. **Baseline.** `unknown` is `unknown`. Admitted means the harness runs the stub with no allow,
   so the allow is no boundary there: the variant passes on the positive half alone, with
   `evidence.boundary: none`, and the controls are recorded only.
3. **Refusal half.** Any control admitted is `fail`, named in `evidence.admitted`; otherwise any
   control `unknown` is `unknown`; otherwise `pass`, with `evidence.boundary: measured`.

The variant and its thirteen launches sit in `sub_results` beside the three fence variants and
outside their disjunction, so the probe's own `status` means what it always meant. A
`fence-vs-allowlist` run is sixteen launches; the pre-launch count shows them.

The record shapes are known for `claude` (`permission_denials`) and Codex
(`command_execution` items) only. Codex prints those items only as `codex exec --json`
events, so the probe launches codex with `--json` and reads the final message from `-o`
(BUG-278: without it no codex refusal was ever on record). The fake harness's denial records for the other profiles
are invented. On a real harness whose output names no command, every refusal reads `unknown`
until a live run shows where it records one.

`broad-first-token` allows the fence's first word as it is written today. That is
the ToolkitRoot root line's `ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}";`, not the
guarded `if` the plan names, because REQ-669 put the root line first.

### Verdicts

`pass` and `fail` mean the harness exited 0 and the oracle was positive or
negative. `unknown` is anything else, always with a reason: `binary-exit-<n>`,
`timeout`, `launch-refused` (the harness rejected the command line — itself a §6
finding about the profile's facts), `ask-not-reached`, `precondition-unmet: …`.
`n/a` means the probe does not apply to that harness. A model that exits 0 having
declined the ask records `fail`: the probe cannot tell a sandbox that blocked an
action from a model that refused it, so read the evidence before citing a result.

**What counts as submitted (BUG-285).** A record's command is compared with the asked command
exactly, after the one shell wrapper a harness adds (`/bin/zsh -lc '…'`) is stripped. A command
that only quotes the asked line, or carries it inside a longer one, is not a submission of it.
For `git-write-*` the proof is a recorded line whose every statement starts with `git commit`
or `git push` and that pushes, or one that commits when the commit did not land: `git status &&
git push` is judged by its un-allowed head, so its failure says nothing about the push. A stderr
refusal counts only when it names the asked command itself.

**Nonce rows retry a miss.** `stdin-prompt` and `session-start-context` are decided by a nonce
only the probe's own channel carries, so a returned nonce cannot be forged and a `pass` is proof
on any attempt. A miss may be the model mis-copying eight characters, so the launch runs again,
up to five attempts.

**Sentinels sit where only an admitted command can write.** That now includes the three older
`fence-vs-allowlist` variants: on codex their sentinel is outside the sandbox, so a fence no
allow names, run sandboxed, no longer reads `pass`.

**Fresh state includes the checkout's remote-tracking refs**, which a push in one launch moves.

A row whose `fail` means "the harness refused the asked command" (`trust-then-headless`'s
`allowlist-loaded`, `git-write-main`, `git-write-worktree` and the three older
`fence-vs-allowlist` variants) reads `fail` only when the command was submitted: it is in a
`command` field of the harness's own records, or the harness's refusal on stderr names it.
Otherwise the launch is `unknown / not-attempted` and is retried, up to five attempts (BUG-281).
`arg-substitution`, whose `fail` means the command ran with the wrong result, and the rows
that ask no command (the hook rows, `stdin-prompt`) are unchanged.

**`shell-timeout` is decided from two files the one command stamps** (BUG-286): a start
marker before the sleep and the sentinel after it.

| what the launch left | reading |
|---|---|
| the sentinel, at least 125 s younger than the start marker | `pass` |
| the sentinel, without that gap | `unknown`: the sleep did not run for its length |
| the start marker only, and the model replied | `fail`: the shell call began and was cut short |
| neither file, and the model replied | `unknown / not-attempted`: the command never began |
| the harness refused the command | `unknown / precondition-unmet` |

The launch is not retried. One limit remains: a model that runs the first `touch` alone and
then replies reads `fail`.

On codex and gemini, whose trust is a user-level file, `trust-then-headless` is
the run's first launch and its `allowlist-loaded` half gates every other probe:
when it is not `pass` they record `unknown / precondition-unmet:
trust-then-headless <status>` and are not launched.

`ask-tier-deny` runs three variants and four controls. `lone-deny` installs a
deny alone; `deny-under-allow` installs the same deny while the base command is
allowed; `wrapped-allow` denies `git push --force origin …` and asks the
`git -C <repo>` form. The controls `baseline`, `allow-only`, `baseline-git-c` and
`allow-only-git-c` show whether the allow was necessary and effective: a variant
is decided only when its `allow-only*` control ran the command and its
`baseline*` control did not, read with proof of submission: a baseline the model never
tried leaves the variant `precondition-unmet: <control> not measured` (BUG-283). On a profile
with `allow_required_path` (codex), un-allowed commands run sandboxed and cannot write there, so
an unattempted `baseline*` control reads `fail`, marked `inferred`, when the same run's
`runner-baseline` was refused with its command on record (REQ-664 BR-17(e)). That needs a run
that includes `fence-vs-allowlist`. A headless ask is already a deny on most harnesses,
so `lone-deny` is `n/a` unless `baseline` ran its command.

A variant whose command did not run reads `pass` (the deny held), and a control whose command
did not run reads `fail`, only when the command was submitted: it is in a `command` field of the
harness's own records, or the harness's refusal on stderr names its target. Otherwise the launch
is `unknown / not-attempted`, and, like a launch that never reached the ask or lost its witness,
it is launched again from fresh state, up to five attempts. codex-cli 0.166.0's model ran the
witness and skipped the denied command, which read as a deny that held (BUG-280). Codex
writes no record for a command a `forbidden` rule rejects; its stderr line `rejected: policy
forbids commands starting with <command>` is the record instead (BUG-282).

**Consumer mapping.** REQ-655, REQ-656 and REQ-662 read `sub_results` for which
configuration passed. The `git-c` wrapper shape is read from `wrapped-allow` and
the `prefix` shape from `deny-under-allow`. The `env-prefix` and `shell-opener`
shapes have no sub-variant here, so they stay `unverified`: no result file from
this tool lifts REQ-657's `capabilities.deny_under_allow` for them. REQ-662 reads
`unknown` and `n/a` alike as `unverified`.

**Residual: a `pass` is one sample.** Each launch is a single model sample, so a
one-off hollow `pass` stays possible, for example a model that runs the witness
and then declines the denied command for reasons of its own. The byte-identical
controls and the witness bound that and do not remove it. Any `pass` cited to
lift an omission carries this residual.

### What a run touches

- A `mkdtemp` directory under the temp root (validated before any recursive
  removal), removed at the end; `--keep` keeps it and prints its path.
- On codex, `~/.codex/config.toml` gains a `[projects."<realpath>"]` trust table
  for the throwaway repo and its worktree; on gemini, `~/.gemini/trustedFolders.json`
  gains the two paths and `~/.gemini/policies/adlc-probe-<run_id>.toml` holds
  `ask-tier-deny`'s variant denies. Copilot and cursor get a trust flag; claude
  needs nothing. Codex also gets a probe-named directory outside its sandbox's
  writable roots, `<ADLC_HOME>/adlc/harness-probe/outside-<run_id>/`, holding the
  bare `origin` and the sentinels whose commands need an allow.
- The harness's own state, which is left in place: its session records, and on
  Claude Code a `projects["<throwaway repo>"]` entry it adds to `~/.claude.json`
  for each new cwd (seen on 2.1.258).

Claude runs with `--setting-sources project,local`, so your user settings are never
read. Claude Code (2.1.258 and 2.1.316 alike) ignores a project's `permissions.allow`
in a workspace it has not been told to trust (it names `~/.claude.json`
`projects["<path>"].hasTrustDialogAccepted`), and the probe does not write that file:
open sessions write it too, so a byte-for-byte restore could erase their writes. A
`--settings` file is not gated. So each launch's rules, with
`permissions.defaultMode: "default"`, go in `<run_dir>/captures/<launch>.settings.json`,
passed with `--settings`, the way `/sprint --exec` launches claude (BUG-267). Hooks stay
in the project's `.claude/settings.json`, which loads untrusted. One launch keeps its
allow in the project file: `trust-then-headless`'s `allowlist-loaded` asks whether a
project-only allow loads headlessly, and on claude it records `fail`, with Claude's
message in its evidence. That half is the finding, not a probe fault.

A user-level file that is a symlink (a dotfiles setup) is edited and restored
through its target, so the link survives.

### Exit codes

| code | meaning |
|---|---|
| 0 | every applicable probe ran to a verdict (a run full of `fail` still exits 0) |
| 1 | the tool failed or refused: something was left behind, a restore did not match its checksum (including a `surgical` one), the result could not be written, a recovery marker exists, or the cwd is outside a git repository. Every leftover path and the `--recover` command are printed |
| 2 | a usage error, an unknown probe id, a cap under 180 s with `shell-timeout` selected, or the harness binary is not on `PATH` (no result file is written) |

### Recovery

Before the first user-level edit the run backs the file up and writes a marker,
`<ADLC_HOME>/adlc/harness-probe/<harness>.marker.json`, naming each backup, its
checksum and every directory the run created. The marker is cleared only after a
checksum-verified restore. A run killed in between (SIGKILL, a power cut) leaves
it behind, and the next run on that harness refuses:

```bash
adlc harness probe codex --recover   # needs no repository and no harness binary
```

`--recover` restores each covered file from its backup, deletes files the run
created, removes the probe's directories (a created directory is `rmdir`-ed only
when empty; a non-empty one is listed and left), and clears the marker. If
something else changed a covered file during the run, the restore is
**surgical**: only the probe's own entry is removed, a copy of the file as it was
sits beside the marker, and the exit is 1. SIGINT, SIGTERM and SIGHUP restore
before exiting, leave no marker and write no result.

### `--only` and the result file

`--only <probe>` (repeatable) runs those probes and carries the others forward
from the existing result file only when its `harness_version` and
`probe_tool_version` both match this run; otherwise they become
`unknown / not-run-this-version`, and stderr says how many were dropped and why.
Each probe keeps its own `ran_at`. `adlc harness detect` shows the file's `date`
as `last_probe`.


## The harness adapter framework (REQ-657)

A harness is data: `harness/<name>.yml`, validated by one loader
(`harness_adapter.py`) and rendered by one module (`harness_render.py`). Three
canonical sources go through it: `agents/*.md`, `templates/permissions.yml` (the
**routine** tier and the **deny** tier, the one-way moves) and `templates/hooks.yml`
(`ethos-inject`, `session-record`). `harness/claude.yml`, `harness/codex.yml`, `harness/copilot.yml`,
`harness/cursor.yml` and `harness/antigravity.yml` ship. Nothing in `tools/adlc` branches on a harness name; a new
harness is an adapter file, golden renders under `harness/<name>/rendered/`, its
`accepted_fidelity`, and, only for a new file format, one renderer in
`harness_render.FORMATS`.

`schema_version` 4 (REQ-658) adds optional fields any adapter can use, each refused under an
older version: `hook_cwd`, a path of `..` segments a rendered hook changes to first, for a
harness that runs a hook where its config file sits; `hook_output_envelope`, the JSON around
`--context-key`'s output, one `%s`, for a harness that wants context nested; a `rendered`
`skills` surface, one file naming the directory that holds the skills; and
`capabilities.fence_unmatchable`, for a harness where no rule matches a partial-sourcing
fence, which renders no rule and prints no remedy. At schema 4 and later, `render-currency`
and `doctor_rows` SKIP when none of the adapter's user-level files exists, so an installed
harness nobody rendered for is not a defect. A format can also set `agent_tools_list`, which
spells `tools:` as a YAML list and writes every mapped tool for an agent with no `tools:`
line, and `agent_header`, which marks a rendered agent and refuses a target without the mark.

| Command | Does | Writes |
|---|---|---|
| `adlc harness render --harness <name> [--surface S] [--scope project\|user\|exec] [--dry-run] [--force]` | renders any surface of an adapter; `project` is the caller's git top level (LESSON-397) | only the paths the adapter declares for that scope, atomically; a second run reports `zero actions`. `--scope exec` prints structured entries and writes nothing |
| `adlc harness render --check` | the toolkit's parity check: every golden and every in-tree render (agents' `model:` lines, the toolkit's own `.claude/settings.json`) against a fresh render, with a unified diff | nothing |
| `adlc harness render --write-goldens [--harness <name>]` | rewrites `harness/<name>/rendered/` from a fresh render, after a change to `templates/permissions.yml`, `templates/hooks.yml` or an adapter | the goldens only |
| `adlc harness install --harness <name>` / `--all` | a harness's **user-level** surfaces only; `--all` iterates the harnesses `detect` reports present | `claude`: nothing (agents are the mount, the allowlist and hooks travel in the project layer) |
| `adlc harness doctor [--harness <name>]` | `harness:<name>` and `render-currency:<name>` | nothing |
| `adlc harness drift [--harness <name>] [--opted-in] [--json]` | `/template-drift`'s `harness-config` step: the project's rendered files against a fresh render, with template posture (`synced` / `customized` / `stale` / `missing`), naming every missing deny-tier rule. `--opted-in` adds each shipped adapter the project already has a file of | nothing; exit 1 on `stale` or `missing` |

`--adapter-path <file>` is accepted by every `adlc harness` verb and by `adlc agents
render`, and is the only way a test-only adapter loads; `install --all` refuses it
and `/init` cannot pass it.

**The YAML subset** (`harness_yaml.py`, pure stdlib because the doctor loads
adapters without the venv, LESSON-395): block mappings and sequences, one-line flow
sequences and mappings, plain / single- / double-quoted scalars, integers, `|` and
`|-` block scalars, `#` comments. Tabs, anchors, aliases, tags, `>` folding,
document markers, `?` keys and a key given twice (in any spelling) are loud errors
naming the line (LESSON-716).

**The Codex CLI adapter (REQ-655).** Its facts are `codex-cli 0.166.0` as run on 2026-10-31.

| Verb | What `--harness codex` does |
|---|---|
| `adlc agents render` | writes `$HOME/.codex/agents/<name>.toml`; `developer_instructions` opens with the ETHOS read line, then the restraint sentence when `tools:` omits Edit and Write; `model` omitted while `tier_map` reads `unverified` |
| `adlc harness render` | writes `.codex/rules/adlc.rules`, `.codex/hooks.json`, `AGENTS.md`, and merges `.codex/config.toml` (TOML `write_mode: merge`, `tools/adlc/toml_merge.py`). A construct it cannot classify, or `danger-full-access` / `approval_policy = "never"` already there, leaves the file and exits non-zero |
| `adlc harness render --check` | the parity check, plus the rendered agent copies once any exist, so a hand edit fails it naming the file |
| `adlc harness install` | the agent copies; with the delegation CLIs present, also the routing block in `$HOME/.codex/AGENTS.md` and the three delegation rules in `$HOME/.codex/rules/adlc.rules`. `--only-if-detected` writes nothing without the binary, which is how `tools/delegate/install.sh` calls it. `--writable-root <path>` unions one absolute path into `writable_roots` in the user config, prints the diff, and is the only thing that writes that file |
| `adlc harness install --exec` | writes `$HOME/.codex/rules/adlc-exec.rules`, the exec engine's deny-tier file beside the operator's own rules (REQ-662; "The exec adapter contract", below) |
| `adlc harness doctor` | also refuses a shipped adapter whose `sandbox_can_reach_common_gitdir` reads `unverified`, and prints `exec: verified` or `exec: unverified (<probe ids>)` |

| Doctor row | Kind | Meaning |
|---|---|---|
| `codex-rules` | `equals-render` | the user-level rules equal a fresh render; SKIP when delegation is not installed |
| `codex-routing` | `marker-present` | the routing block is in `$HOME/.codex/AGENTS.md` (the legacy marker counts); SKIP when delegation is not installed |

Each row an adapter declares without a `fact` is a check of its own in `adlc doctor`, by the row's id, and SKIPs without the binary. Schema 3 adds `paths.config`, `capabilities.unmatched_shapes` and `unmatched_default`, `deny_under_allow.<shape>.by_hand`, `doctor_rows[].requires` and a marker row's `legacy_marker`, each refused under an older `schema_version`.

**The Copilot CLI and Cursor adapters (REQ-656).** Their facts are the vendor docs as read
on 2026-10-30; no run has happened, and the end-to-end check is owed (the spec's
Deferred section). Every value a probe would decide is unverified.

| | `copilot` | `cursor` |
|---|---|---|
| `adlc agents render --harness <name>` | writes `$HOME/.copilot/agents/<name>.agent.md`, tools through `tool_map`, `model:` omitted while `tier_map` reads `unverified` | a no-op: exit 0, and one line naming `~/.claude/agents` (`via:claude`) |
| `adlc harness render --harness <name>` | writes `.github/hooks/adlc.json` and `AGENTS.md`, and prints the `--allow-tool … --deny-tool …` line; `--scope user` writes the agent copies too | writes `.cursor/cli.json`, `.cursor/permissions.json` and `AGENTS.md` |
| `adlc harness install --harness <name>` | the agent copies | nothing to write |
| `harness:<name>` (report-only) | the `~/.agents/skills` view | `~/.claude/skills` and `~/.claude/agents` as sources, and the double skill discovery |
| `render-currency:<name>` | FAILs when a copy is missing or differs; fix: `adlc agents render --harness copilot` | no user-level surface, so it passes |

Both checks SKIP without the binary. Both report the `deny_under_allow` shapes, recomputed
against the REQ-664 result file: a hand-set `pass` with no matching result reads
`unverified`. Schema version 2 adds four optional fields: `paths.<surface>.also` (a further
file on a surface, with its own format), `hook_output` (a hook whose output a harness
takes only as JSON), `fidelity_notes` (sentences the report prints) and
`doctor_rows[].fact` (a row reported under `harness:<name>`, never judged).

**Write modes.** `create` (the default) keeps an existing file unless `--force`;
`merge` (JSON only) refreshes the surface's `owned_keys`, unions their lists, and
keeps every other key. `CLAUDE.md` is never rewritten: it gains one `@AGENTS.md`
line when it has none.

**`render-currency:<name>`** (one framework check, registered for every detect name)
loads the adapter, compares every user-level surface it renders with a fresh render
(for a `mounted` agents surface, the canonical `model:` stamp), and evaluates the
adapter's `doctor_rows` (`path-exists`, `marker-present`, `equals-render`) from the
data. A FAIL names a remediation to run verbatim; an absent binary SKIPs.
`adlc doctor --checks render-currency:<name>` and `adlc harness doctor` call the same
function. It does not read a consumer's project layer: `consumer-sync` does, machine-wide.

**Per-harness tier columns.** `agents.harness.<name>.classes` / `.overrides` sit
beside `agents.classes` / `.overrides`; H's override > H's class > default override
> default class > shipped default, then the adapter's `tier_map` (`unverified`
omits `model:` with one stderr notice). An unknown sub-key under `agents:` is an
error. A `mounted` agents surface (Claude's) is the in-place stamp and resolves
through the default column, so a `claude` column, present or absent, changes nothing.

<!-- declared-residuals -->
**Declared residuals (REQ-657 BR-18).** Allowlist and prefix-deny matching cannot be made a gate, and the adapter framework does not pretend it can. `allowlist-fidelity` closes spellings, not this list:

- Allowlist matching is spelling-level. The lint evaluates a closed set of spellings; a deny-tier command reached in any other spelling is not seen.
- Allows that execute their arguments (`find -exec`, `awk`, `sed e`, `npx`, `npm run` / `npm exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents of a deny-tier command (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- This is the same exposure Claude's template has today (Rule A grandfathers it); no adapter makes it worse, and none claims to close it.
- The allowlist is never the gate (Rule B). The orchestrator's structural gates (REQ-659) are.
<!-- /declared-residuals -->

## The exec adapter contract (REQ-659, REQ-662)

A harness joins `/sprint --exec` by adding an `exec` block to its adapter. `harness_adapter.py`
validates it when `exec_schema_version` is present, and `exec_adapter.py` is the engine's view
of it. Nothing branches on a harness name: every difference between harnesses is a key here.
Which adapters carry a block, and the value each declares, are in `harness/*.yml`, and
`adlc harness doctor` prints `exec: verified` or `exec: unverified (<probe ids>)` for each
installed harness that has one. An adapter whose `exec` is the placeholder
`{flags: unverified}` has no `exec_schema_version`, so the loader leaves it opaque and the
engine refuses it by name, naming REQ-662, which adds one harness per stage.

**Schema 2 (REQ-662 ADR-1).** `exec_schema_version` is 2. The loader refuses version 1, REQ-659's
shape, and any other version, and refuses the whole adapter on an unknown key, a missing
required key or a wrong type, never half-reading it. Schema 2 keeps schema 1's keys, reshapes
three (`working_copy`, `resume`, `output`) and adds the ExecBlock's. Keys one render form reads
are required on that form and refused on any other, so a block carries no field the engine
never reads: `allow_flag`, `shell_rule` and `settings_keys` (and optionally
`shell_rule_exact`) with `allow_render: flags`, `rule_file` with `allow_render: file`, and
`deny_flag` with `deny_render: flags`.

| Key | Meaning |
|---|---|
| `harness_version`, `verification`, `status`, `probes` | the harness version the block was written against; `probes` (the REQ-664 result file decides) or `recorded` (a block that predates the probe gate and stands on REQ-659's recorded evidence); the cached BR-11 verdict; and, under `probes`, one `{id, ran_at, harness_version, status}` row per required probe, copied from `.adlc/research/harness-probes/<name>.json`. `status` and `probes` are caches: `exec_verify` recomputes the verdict (below) |
| `working_copy` | `{strategy: worktree \| clone \| orchestrator-git}`. `worktree` needs the top-level `sandbox_can_reach_common_gitdir: true`, and `exec_verify` binds it to `git-write-worktree`. Only `worktree` runs today: the other two are pre-flight refusals until an adapter ships one |
| `trust_grant` | What the **engine** does per run: `none`, `flag`, `user-config-entry`, `trusted-folders-file`. Not the top-level `trust`, which is what the harness reads. `none` and `user-config-entry` (through `exec_trust.py`) run; the other two refuse at pre-flight until an adapter ships one. `user-config-entry` appends a TOML `[projects."<path>"]` table to `paths.config.user`, so the loader refuses it when that user config's format (`formats.config`) is not one the registry marks `trust_entry`, and the grant refuses at launch when there is no user config |
| `launch`, `resume` | argv templates after the binary, each placeholder one whole token: `{worktree}`, `{last_message}`, `{session_id}`, `{settings}`, `{branch}`. `resume` must hold `{session_id}`. A block without `resume` cannot resume, and the halt says so before approval is asked for. A block without `add_dir_flag` resumes its close-out with no second directory: the engine copies the primary's `pipeline-state.json` into the close-out working copy and carries the session's changes back as data, never its `status`, `exec` or `approval`, nor `lessons`, `harness`, `validateAttempts` or `verify` where the primary copy holds them, and a REQ spanning more than one repository is refused at the pre-flight |
| `prompt_delivery`, `prompt_flag`, `prompt_variant` | `stdin`, always. `prompt_flag` is the token run that makes a launch `stdin-prompt`'s `with-prompt-flag` variant, and the loader holds `prompt_variant` to whether `launch` carries it |
| `context_delivery` | `hooks`: the engine relies on the harness's session-start hooks. `prompt`: it relies on none, ETHOS is in the prompt, the hook file is a surface rendered absent, and BR-11 needs only `trust-then-headless`'s `allowlist-loaded` half |
| `allow_render`, `deny_render` | how the two tiers travel: `flags` on the argv, or `file`, a rule file in the working copy (`rule_file`) and, for the deny tier, the user policy file too. `deny_render` may be `none`; `flags` and `file` need `capabilities.deny: yes` |
| `allow_flag`, `deny_flag`, `add_dir_flag`, `shell_rule`, `shell_rule_exact`, `settings_keys` | the `flags` form: how the two tiers reach the argv |
| `rule_file`, `user_policy_file` | the `file` form: the working-copy rule file, rendered for each run, and the toolkit-owned user-level deny file (`$HOME/...`), or `none`. The user file holds the deny tier only, never an allow |
| `allow_tools` | the non-shell tools that touch no file. A bare file tool (`Read`, `Write`, `Edit`, `Glob`, `Grep`, `MultiEdit`, `NotebookEdit`) is refused by the loader, because a bare name admits every path (BUG-265) |
| `file_rules` | the file tools, as rules with a `{root}` in each: `write` rules per write root (every repo's working copy, plus a close-out's `--add-dir`), `read` rules per read root (ToolkitRoot). A root is a plain absolute path, emitted under its given and its real spelling, because Claude matches a rule against the path as written (BUG-265) |
| `allow_extra`, `allow_extra_exact` | routine spellings the exec-scope render cannot give, `{branch}` substituted in both. Each is vetted like an operator's `sprint.exec.allow_extra`: no token that runs its arguments, nothing that wraps a deny, and no prefix entry that shares a command base with a deny (`git push`, `git branch`, `rm`): those go in `allow_extra_exact` (BUG-260). Both stay empty under `matcher: none`, where nothing can vet them |
| `engine_deny` | denies that belong to this engine, never in `templates/permissions.yml`: among them the orchestrator's own verbs, `approve` included, so the model cannot clear the gate itself |
| `forbidden_flags`, `operator_flags` | the engine-wide vocabulary plus the harness's own bypass flags, a lint backstop (`exec-no-bypass`) to the closed-world argv check; and the flag names an operator's `--harness-flag` may add |
| `exit_codes`, `output`, `denied_stderr` | raw code to `ok`, `denied`, `timeout`, `error`, an unmapped code being `error` with the code kept. `output` is `{format: json \| jsonl-stream, source: stdout \| file, final_message, session_id}`, plus `terminal_event`, required under `jsonl-stream` and refused under `json`: a truncated stream, a line that is not JSON or an empty final message is `error` with the parser's message in `notes`. A run with no terminal claim is `denied` on the result's denial list or on a stderr line matching `denied_stderr`, read from the harness's own output and never from the model's text |
| `env_passthrough`, `auth_env` | the only variables a child inherits, beside the ones the engine sets (`ADLC_EXEC_RUN`, `ADLC_EXEC_RUN_TAG`, the child's forge credentials) |
| `config_surfaces`, `bypass_config_keys`, `rules_reload` | every working-copy path the harness reads once trusted, each rendered whole or absent; the keys, per config file, that relax approval or sandboxing; and whether the harness re-reads a rule file mid-run (`startup`, `live`, or `unknown`, read as `live`) |
| `shell_timeout_s` | `{value, verified, delegate}`. `delegate: supported` needs a verified value of at least 120 s; otherwise the engine sets `ADLC_DISABLE_DELEGATE=1` in the child |
| `matcher` | `claude`, whose statement matching `exec_matcher` models, or `none`, on which no fence routes `direct` |
| `config_isolation`, `config_isolation_help`, `sandbox_refuse`, `residuals`, `trust_notice` | how a `flags` harness's resumed close-out ignores working-copy config and the flag names looked for in `<binary> --help`; a setting that refuses at pre-flight; and what the two tiers do not stop, stated |
| `fence_runner` | the toolkit-relative path of the fence runner (REQ-682), `tools/adlc/fence-run`. `tiers()` resolves it once under ToolkitRoot and spells it in the adapter's allow form (a `Bash(<root>/<fence_runner>:*)` flag under `allow_render: flags`, a prefix rule in the rule file under `file`), refusing the launch unless the path is absolute, plain (`^/[A-Za-z0-9_./-]+$`, because a quoted path does not match a prefix rule), a regular file and still under the root after `realpath`. With it set, the exec render carries no fence rule and reports `fence.partial-source` as `inexpressible` (runner), and `capabilities.fence_broad_spelling` is not required |

**The modules REQ-662 adds.**

- **`exec_verify.py` (BR-11, ADR-2).** `verdict(adapter, result, installed_version)` is the one
  answer to whether an adapter may launch. It reads `verified` when every hard probe reads
  `pass`, every declaration-bound probe reads `pass` or `fail` and agrees with what the block
  declares, and the result's version, `exec.harness_version` and the installed binary's
  version are equal. The result is read from
  `<ToolkitRoot>/.adlc/research/harness-probes/<name>.json` only, never from a working copy,
  and a missing file reads `unverified`. The engine calls it at launch, before a relaunch, at
  the close-out and in `approve` before the merge; `adlc harness doctor` prints `exec:
  verified` or `exec: unverified (<probe ids>)` from the same call. `verification: recorded`
  skips the gate.
- **`exec_trust.py` (BR-5, ADR-5).** For `user-config-entry`: one commented block,
  `[projects."<working copy>"] trust_level = "trusted"`, appended to the adapter's
  `paths.config.user` before a launch and removed byte for byte when the harness exits. The path
  must be absolute and under the run's working-copy root, or nothing is written. An entry
  already there is `pre_existing` and survives; a block already gone is a warning. Writes are
  serialized by a `mkdir` lock beside the file, a grant refuses while REQ-664's probe
  recovery marker exists, and no write touches `hooks.state`.
- **`exec_surfaces.py` (BR-4, BR-15, BR-16, ADR-4).** Everything the engine writes for a run
  outside its run directory. Each `config_surfaces` entry is rendered whole or absent, and a
  stray file in a directory surface is deleted. Every path component is `lstat`ed: a
  symlink, a hardlink or a non-regular file refuses. One sha256 manifest is checked before
  launch and before resume, where a mismatch is repaired and logged
  `rule_file_rerendered`, and when the harness exits, where it is a
  `config_surface_violation` that blocks the run. It runs the `bypass_config_keys` scan (TOML through
  `toml_merge.scan`; a file it cannot read refuses), and writes the user policy file whole
  and atomically under a lock, checking its folder against the engine's record at launch and
  resume. The halt-time exec-path gate is `exec_gates.check_exec_path`: a PR touching a
  rendered path or a surface refuses `approve`, and `--ack-gate-change` does not reach it.

| Command | Does |
|---|---|
| `adlc harness install --exec --harness <name>` | writes the adapter's `exec.user_policy_file` whole and atomically under the lock, and records its folder; a run's pre-flight writes it too when it was never installed. The file is user-level, so it persists across runs and projects and applies to the operator's own sessions |
| `adlc harness render --harness <name> --scope exec` | prints the structured exec-scope entries and the fidelity findings; writes nothing |
| `adlc sprint-exec run --harness <name> [--allow-unverified] <REQ>...` | launches. `--allow-unverified` launches an adapter the verdict reads `unverified`, with a loud line on every launch, and the ledger records it. It is read from the command line only, applies only to the launches of the invocation that received it, never covers `approve`, and bypasses nothing else |

**The fence runner (REQ-682).** No allow admits a fence that sources a partial: Claude refuses `.`
and `source` whatever the allow says, and judges a compound command one statement at a time
(`exec_matcher.py` holds the measured rules). So an exec model runs toolkit fences through one
executable:

- `fence-run run <id> [--arg NAME=VALUE]... [--arg-file NAME=PATH]...` runs the census fence
  `<id>` (`<toolkit-relative path>#<ordinal>:<sha8>`). It recomputes the census
  (`fence_census.py`) from its own real path on every call, so it trusts no cache, manifest or
  environment variable. It refuses an id whose fence changed or whose route is `direct`,
  `engine` or `excised`, checks each value against its placeholder's full-match pattern, binds it
  as an `ADLC_ARG_*` variable expanded once inside double quotes, and runs the fence under
  `/bin/sh` after sourcing `adlc-home.sh` and `forge.sh` from the install, with
  `ADLC_FENCE_TOOLKIT_ONLY=1` set last, so no partial takes a working-copy arm.
- `fence-run show <file>` prints a file of the exec set with each fence in its route's form: a
  runner call, the fence unchanged (`direct`), or one line naming why it does not run. A
  runner call single-quotes its id: Codex matches no prefix rule against a command holding a
  bare `#`, so a bare id ran the runner inside the sandbox (measured on codex-cli 0.166.0,
  2026-11-18).
- Exit codes: a fence's own status is passed through; **3** is the runner's refusal, always one
  stderr line `opaque_entry_refused: <id>: <reason>`, with nothing run. Three more statuses
  mean nothing ran and the caller can put it right (BUG-287, REQ-719). **65**, with one
  `fence_run_bad_value:` line, is a value to correct: a value of the wrong shape (a relative
  path where the fence takes an absolute one, an `--arg-file` outside the working copy, a name
  the fence does not take), or a PR number that is not the caller's PR (below). **69**, with
  one `fence_run_sandboxed:` line, is a call that cannot write the repository's git directory,
  which on Codex means it was chained after a command with no allow and the whole line ran
  inside the sandbox: run it again as a command of its own. The check is skipped where the git
  directory is inside the working copy. **75**, with one `fence_run_unverified:` line, is a PR
  number the runner could not check because the forge could not be read: run the same line
  once more, then report it as a blocker. The three numbers sit above what a fence's own
  commands return, and the stderr line is what names the case.
- **The PR tie (REQ-719 ADR-3).** A value bound to a placeholder whose value is a PR number
  (`prNumber`, which carries the PR mark in `fence_census`'s closed tables) must be the
  caller's PR: the open, same-repository PR whose head is the branch checked out where the
  runner was called. After the value checks and the sandbox check, and before any command of
  the fence, the runner reads each such value once, with `adlc_forge_pr_view <n> --fields
  number,state,headRefName,isCrossRepository` under the fence's own preload and environment, so
  it reads the forge repository of the calling directory and the mock forge answers it. Any
  field that differs, or `error_class=pr-not-found`, is 65, and the line names the value and
  the branch and no field of the PR it read. No branch checked out is 3, decided before any
  read. The adapter's own `opaque_entry_refused:` (its Azure DevOps arm under the runner) is
  passed through as 3. Any other error class, an answer that does not parse, or no answer in
  60 s is 75. A tied fence's census record names its values under `tied`, and its reach
  includes the read. A runner fence that hands an unmarked placeholder to an `adlc_forge_pr_*`
  operation as its PR does not route, and `fence_census.py --check` fails naming it.
- **`--arg-file`** is opened from a handle on the working directory, one path component at a
  time, following no symlink at any component, the last included. The path is relative with
  no `..` segment, or absolute under the working directory in its given spelling (`$PWD`) or
  its real one (`/var` and `/private/var` on macOS); the file's own path is never resolved.
  The regular-file check, the 1 MiB cap and the UTF-8 check are made on the opened
  descriptor, and the text is read from it. A FIFO or a device is refused without blocking.
  Every failure is 65. A symlink inside the working copy that points inside it is refused too,
  and a hard link is not detected (the README's declared residuals).
- **Its git environment.** No caller `GIT_*` variable reaches a fence, so neither does a
  caller's `GIT_SSH_COMMAND`, and every git call it makes is pinned to `core.fsmonitor=false`
  and `core.hooksPath=/dev/null` through `GIT_CONFIG_COUNT`, over the repository's own config.
  Those are two of the keys the orchestrator pins for its own git calls; its ssh and credential
  pins point at its run directory and would break an operator's push credentials, so the
  runner does not take them. The rest of that config is honoured, and a model can write it, so
  the two pins are defense in depth (the README's declared residual (f)).

**One census per adapter (REQ-662 ADR-8).** Each exec-capable adapter has its committed census,
`harness/<name>/exec-fence-census.json`: every fence, its route, its values and its reach. On
`matcher: claude` a fence may route `direct`; on `matcher: none` none does. The engine's
The census's `routes_direct` is `ExecAdapter.has_matcher`, which reads the modelled-matcher list in `harness_adapter`, so the two read one answer. The runner
accepts a fence that is `runner` in the census of any exec-capable adapter under its own root,
and the reach of every `runner` route is audited against the union of every such adapter's deny
tier and `engine_deny`, so whichever harness calls, no accepted route reaches a command any
adapter denies. `test_exec_reach.py` audits that reach statically over the function closure and
dynamically under recording stubs, and fails on any deny-tier command, so a new fence or
partial function starts refused until it is checked (BR-4). `fence_census.py --check` holds
each golden fresh.

**The branch push through the runner (REQ-662 ADR-9).** Codex's prefix rules have no exact form,
so no `git push` allow is rendered there, and a push left unmatched runs inside the sandbox,
without network. Step 0's push fence is therefore a `runner` fence on `matcher: none`, audited
as a second push kind: its argv must be exactly `git -C $ADLC_ARG_worktree push -u origin
$ADLC_ARG_branch`. At run time `worktree` must be the directory the runner was called from,
`branch` must match `^(feat|fix|chore)/[A-Za-z0-9][A-Za-z0-9._-]*$` and be the branch checked
out there, and under an exec run (`ADLC_EXEC_RUN` set to the run's REQ id) it must be that REQ's
branch. On `matcher: claude` the fence stays `direct`, under Claude's exact rule.

**Trust, for an adapter whose grant is real.** Grant before launch, per working copy, the
close-out copy included. Revoke on every exit path: merge, reject, abort, crash. Remove exactly
what the run added, and never leave an entry for a path that is gone. A `user-config-entry` or
`trusted-folders-file` grant edits a file the harness may rewrite while it runs, so re-read
before writing, replace atomically, and verify after. On Codex the grant is not what loads the
rules: `codex exec` writes a lasting trust entry for the main repository root by itself when
no entry covers its directory, and the engine's entry for the working copy is what keeps it
from doing so (`.adlc/research/harness-probes/codex-exec-manual.md`).

**What REQ-662 carried from REQ-659.** Codex's `sandbox_can_reach_common_gitdir: true` holds
because an allowed `git commit` runs outside the sandbox, while a sandboxed command stops at
`index.lock` (REQ-655). A Codex hook's review key contains the absolute path, so every working
copy starts unreviewed and `codex exec` skips the hook silently, which is why the Codex block
declares `context_delivery: prompt`. `agy -p` ends at the first tool it would need to prompt
for, with exit 0 and an empty response, and a failed run exits 3 (REQ-658), which is why `ok`
with no terminal claim is `failed` for every harness.

**What REQ-719 adds to the engine.** `abort` has a second arm: a `blocked` run whose recorded
`exec.pid` and `exec.closeOutPid` are not live is dropped. It ends `failed`, nothing is
signalled, no forge call is made, and the branch, the PR and the working copy are left for a
person. What the engine rendered is restored, trust is revoked, any approval token is
discarded, the run leaves the merge queue, and approvals held behind it are released. On
`awaiting_approval` with no live process `abort` is refused, naming `reject`. Both arms record
`exec.abortedFrom`, the status `abort` found (`running`, `stalled` or `blocked`), beside
`exec.abortedBy` and `exec.abortedAt`, and print one line naming the REQ, who aborted it, the
working copy, the branch and the PR. In the run-outcome log `reject` writes the terminal
`rejected` with an empty reason, which only engine `exec` may write, and `abort` writes
`failed` with the reason `aborted`. The mock forge (`forge_mock.py`) answers `pr_checks`, the
op behind `adlc_forge_pr_checks`, from a PR's `checks` list in its store, which the unrecorded
helper `set-checks` writes, and from the scenarios `checks-pass`, `checks-fail`,
`checks-pending`, `checks-none` and `checks-pending-then-pass`. A PR with no list reads `none`.

## `adlc agents render` (REQ-516)

Every agent in [`agents/`](../../agents) declares a stable **tier class** in its
frontmatter (`tier:`); the `model:` line is **rendered output**, not hand-edited
(each agent carries a `<!-- ... do not hand-edit -->` comment saying so). This
command stamps the resolved `model:` into each agent file so an adopter can
re-tier every agent from one config block instead of editing 19 files (whose
edits a toolkit pull would clobber).

```bash
adlc agents render            # stamp model: into every agents/*.md from config
adlc agents render --check    # report drift only; write nothing (non-zero exit on drift)
adlc agents render --config /path/to/config.yml   # use a specific config file
```

With **no config**, rendering reproduces today's exact per-agent assignments —
**zero behavior change** for existing installs. The render is idempotent (a second
run produces an empty `git diff`) and atomic per file (temp-write + rename); it
rewrites only the `model:` line and never reflows other frontmatter or body.

### The `agents:` config block

Lives in the shared `~/.claude/adlc/config.yml` (the same file REQ-515 uses for
its `delegate:` block — the two coexist). Two optional sub-maps:

```yaml
agents:
  classes:
    reviewer: sonnet        # move every reviewer-class agent to sonnet
    scanner: haiku
    # explorer / implementer / orchestrator omitted -> shipped defaults
  overrides:
    correctness-reviewer: opus    # per-agent override beats the class mapping
    pipeline-runner: inherit      # drop the model: line -> inherit session model
```

**Resolution precedence (highest wins):** per-agent `overrides` > class `classes`
mapping > the shipped per-agent default. The value `inherit` removes the `model:`
line entirely so the agent inherits the session model. The five tier classes are
`reviewer`, `scanner`, `explorer`, `implementer`, `orchestrator`.

### Allowed values & fail-loud validation

Allowed aliases: `opus`, `sonnet`, `haiku`, `inherit`. Escape hatch: a full model
id (lowercase with a hyphen and a digit, e.g. `claude-opus-4-8`) is passed through
verbatim. **Anything else fails loud** — `adlc agents render` exits non-zero with a
message naming the bad key, the bad value, and the allowed set; no silent
fall-through to a default. Validation runs over the whole config before any file is
written, so an invalid config never half-renders.

### Drift detection

`adlc agents render --check` (read-only) reports any agent whose on-disk `model:`
differs from what the current config would render, exiting non-zero if any drift
exists. The toolkit's `tools/lint-skills` linter calls the **same** `check_drift`
code path, so a hand-edited `model:` is surfaced as staleness in normal linting —
mirroring the `/template-drift` rationale.

### Linux/macOS parity

The engine is pure Python (`os.replace` for atomic writes, no shell), so it behaves
identically under Ubuntu bash and macOS zsh — there is no shell-portability surface
to diverge. The CLI is dogfooded under both `bash -c` and `zsh -c`.

## The `--checks` pre-flight contract (BR-8)

`adlc doctor --checks id1,id2` runs only the named checks (an unknown id is a
hard error listing the valid ids — never a silent no-op). This is the
**skill pre-flight primitive**: a skill that needs to know "is the forge backend
authed?" or "is delegation reachable?" before dispatching work calls
`adlc doctor --checks forge` (or `delegate-gate`) and reads the exit code,
rather than maintaining its own probe shell.

### Sibling-skill audit (BR-8)

REQ-519 audited the existing skills (`/sprint`, `/proceed`, `/wrapup`) for
duplicated environment-probe shell that should converge on doctor. Finding: those
skills currently express their preflight expectations in **prose**, not as
concrete duplicated executable probe code, so there is **no duplicated probe
shell to delete** in this REQ. The `--checks` contract is now available for them
to converge on going forward (e.g. a future REQ replacing a prose "ensure the
forge backend is authed" step with `adlc doctor --checks forge`).

## `forge_config.py` (REQ-520)

A helper module (not a subcommand) whose *imports* are pure standard library — the
YAML parse happens inside the loader, lazily, so importing this module never drags
PyYAML into an import closure that has to work without it (LESSON-395) — backing the forge
adapter (`partials/forge.sh`) and the `forge` doctor check. It reads the `forge:`
block of the shared ADLC config through
[`load_machine_config()`](../delegate/_machine_config.py) — the one loader, the same
call `_common.parse_delegate_config` uses (REQ-609 BR-8); a malformed config is a
non-zero exit naming the path and the reason class, not a silent `{}`. It resolves
the provider with precedence
per-project `.adlc/config.yml` > machine config > `auto` (origin-URL detection,
fail-loud on an unrecognized host), and refuses a key-shaped `forge.auth` value
(BR-6). The loader is taken from this file's own toolkit root. A copy vendored
without `tools/delegate/` beside it (`.adlc/tools/adlc/forge_config.py`) falls
back to `$ADLC_TOOLKIT_ROOT/tools/delegate/_machine_config.py`, accepted only
when that root's own `toolkit_root.py` derives the same root; `lane_check.py`
does the same. With neither, the one stderr line names the paths searched and
the route's fix: `install.sh` on the symlink route, a plugin reinstall on the
plugin route. CLI surface used by the partial and the check:

```bash
python3 tools/adlc/forge_config.py resolve-provider [<repo-dir>]   # prints github|azure-devops
python3 tools/adlc/forge_config.py validate-auth <value>           # exit 2 if key-shaped
```

## `lane_check.py` (REQ-652)

The lite lane's mechanical check (REQ-652 BR-6, architecture ADR-3). It is a
helper module, not a subcommand. `partials/lane-check.sh` (`adlc_lane_check
<worktree> <base-ref>`) is the entry point the skills call. It runs this file by
path, and only the installed toolkit's copy
(`$ADLC_TOOLKIT_ROOT/tools/adlc/lane_check.py`: the clone behind
`~/.claude/skills` on the symlink route, the plugin's cache copy on the plugin
route), never one in the tree under check:

```bash
python3 tools/adlc/lane_check.py --worktree <path> --base origin/<integration-branch>
```

The caller fetches the base first. The check diffs
`git diff --raw -z --no-renames --ignore-submodules=none <base>...HEAD` in the
worktree (which must be a worktree's top level) and evaluates every rule on the
changed files and their file modes.

| Exit | `lane_check=` | Meaning |
|------|---------------|---------|
| 0 | `pass` | no rule failed |
| 1 | `escalate` | at least one rule failed; the REQ leaves the lite lane |
| 2 | `error` | the check could not decide. Callers treat this as an escalation, never a pass (LESSON-581) |

Stdout has one fact per line:

```
lane_check=escalate
files_counted=4
trigger=blocked-path
detail=infra/main.tf
trigger=max-files
detail=4 > 3
```

- `files_counted` is printed on `pass` and `escalate`. It is omitted on `error`,
  because no count was made and a `0` would read as a fact about the diff.
- Each failing fact is one `trigger=` / `detail=` pair. Every rule is evaluated,
  and each blocked or dependency path gets its own pair.
- A `detail` is always one line that `str.splitlines()` cannot split. A
  backslash is written `\\`. Control characters, the Unicode line and paragraph
  separators (U+2028, U+2029), zero-width and bidi marks (U+200B-U+200F, U+061C,
  U+202A-U+202E, U+2066-U+2069), the BOM and undecodable bytes are written as
  `\xNN` / `\uNNNN` escapes.
- An error prints exactly `lane_check=error`, `trigger=check-error` and
  `detail=<reason>`.

These all produce an error:

- a dirty worktree (tracked changes or untracked files)
- a base ref that does not resolve to a commit, or that starts with `-`
- an empty diff against the base (`detail=empty diff against <base>`): a lite REQ
  always has commits, so the base is wrong
- any git failure
- a worktree path that is not a worktree's top level
- a config at the base that cannot be read or fails the schema
- bad arguments. There is no `--help`, because an exit 0 that printed usage would
  read as a pass.
- any exception the module did not plan for

| Trigger | Fails when |
|---------|------------|
| `blocked-path` | a changed file matches `blocked_paths`, case-insensitively. Files excluded from the count are checked too. Also any change whose old or new mode is a symlink (`120000`), as `detail=symlink: <path>`. |
| `dependency` | a changed file's basename is a lockfile or manifest, case-insensitively, anywhere in the tree (`apps/web/package.json`, `requirements-dev.txt`, `build.gradle.kts`). Also any change whose old or new mode is a submodule (`160000`), as `detail=submodule: <path>`. |
| `deploy-units` | the counted files fall in more than one `deploy_units` unit. Each file takes the first glob it matches, and files matching none are ignored. Evaluated only when `deploy_units` is declared. |
| `max-files` | more files are counted than `max_files`. Files matching `count_exclude` are not counted. |

A rename is two changed files, the deletion and the addition. Both are checked
and both are counted. With rename detection on, a move out of a blocked
directory would list only the new path. `--ignore-submodules=none` overrides a
`.gitmodules` `ignore = all`, which would otherwise hide a gitlink change from
the diff.

**Globs** are repo-relative POSIX paths, anchored at the root:

- `*`, `?` and `[...]` stay within one path segment
- `**/` matches zero or more directories
- a trailing `/**` matches everything beneath that directory
- every pattern (defaults and project, all three lists and the `deploy_units`
  keys) is normalized first by `normalize_pattern()`: a leading `./` or `/` is
  dropped, runs of `/` collapse, a trailing `/` becomes `/**`, and a pattern with
  no glob character also matches everything beneath it (`infra` is `infra` or
  `infra/**`). An empty pattern is a schema error.
- `blocked_paths` and the dependency names match case-insensitively;
  `count_exclude` and `deploy_units` are case-sensitive

`fnmatch` alone lets `*` cross `/`, so `glob_match()` matches segment by segment.

**Defaults.** `DEFAULT_BLOCKED_PATHS`, `DEPENDENCY_LOCKFILES`,
`DEPENDENCY_MANIFESTS`, `DEFAULT_COUNT_EXCLUDE` and `DEFAULT_MAX_FILES` are the
source of truth. `partials/lane-check.md` lists them between
`<!-- lane-defaults <name> -->` markers, and a test fails when the two disagree.

**Config.** The check reads `lanes.lite` from `.adlc/config.yml` **as committed
at the base ref** (`git ls-tree` / `git cat-file`), never from the worktree's
disk, so the branch under check cannot loosen its own limits, by a commit,
`skip-worktree`, or a gitignored local copy. The shape is documented in
[`templates/config-template.yml`](../../templates/config-template.yml) and
`partials/lane-check.md`.

- Absent at the base, the defaults apply. A symlink, a directory or a submodule
  in its place, or a file over 64 KiB, is an error.
- A file whose bytes contain no `lanes` (nor a backslash or NUL, through which a
  YAML escape or a UTF-16 encoding could spell it) is never parsed, so the
  defaults apply even on an interpreter without PyYAML. Mentions on whole-line
  comments are skipped, so a copy of the config template, whose example block is
  commented out, is not parsed either. Every other file is parsed.
- Parsing goes through the shared loader,
  [`load_machine_config()`](../delegate/_machine_config.py), located and executed
  by path the way `forge_config.py` does it, and handed the bytes in a private
  temporary file. That loader refuses duplicate keys, aliases and merge keys
  anywhere in the document.
- Every loader refusal is an error here, `dependency-missing` included. Unlike
  `forge_config.py`, the lane check does not treat a missing PyYAML as
  "unconfigured".
- The section is then checked against a closed schema. `max_files` must be an
  integer >= 1 (a boolean is refused). `blocked_paths` and `count_exclude` must
  be lists of strings. `deploy_units` must map strings to strings. An unknown
  key, a wrong type or an empty pattern is an error.
- A key written with no value counts as unwritten, the same rule the forge reader
  follows.
- `blocked_paths` and `count_exclude` extend the defaults. `max_files` replaces
  the default.

**Git hardening.** Every git run drops `GIT_DIR`, `GIT_WORK_TREE`,
`GIT_INDEX_FILE` and the other repository-redirecting variables, the
config-injecting ones (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`,
`GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_GLOBAL`,
`GIT_CONFIG_SYSTEM`) and the history-rewriting ones (`GIT_GRAFT_FILE`,
`GIT_SHALLOW_FILE`, `GIT_REPLACE_REF_BASE`). It sets `GIT_NO_REPLACE_OBJECTS=1`
and passes `--no-replace-objects`, `--no-optional-locks` and
`-c core.fsmonitor=false`.

**Tests.** `tools/adlc/tests/test_lane_check.py`. The config cases need PyYAML
and skip without it, so the authoritative run is under the delegate venv, with
`ADLC_REQUIRE_PYYAML=1` turning any such skip into a failure:

```bash
ADLC_REQUIRE_PYYAML=1 ~/.claude/delegate-venv/bin/python3 -m pytest tools/adlc/tests/test_lane_check.py
```

## `lessons.py` (REQ-647)

LessonSet selection for the phases that act on lessons: `/proceed` Step 0,
each Phase-4 task, Phase 5, `/bugfix` Phase 2, and the sprint workflow engine's
retrieval leaves. A helper module, not a subcommand. `partials/lessons.sh`
(`adlc_lessons <subcommand> …`) is the entry point the skills call; it runs the
installed toolkit's copy (`$ADLC_TOOLKIT_ROOT/tools/adlc/lessons.py`).
Standard library only.

```bash
python3 tools/adlc/lessons.py select --set step0|task|phase5|bugfix --root <dir> \
    --spec <requirement.md> [--component <c>]... [--task-id TASK-nnn] \
    [--state-out <pipeline-state.json>] [--fresh|--reuse] [--format text|json] [--with-text]
python3 tools/adlc/lessons.py text <LESSON-nnn-slug.md>
python3 tools/adlc/lessons.py log-line --state <file> --key step0|phase5|tasks.TASK-nnn --root <dir>
python3 tools/adlc/lessons.py ack-check --state <file> --root <dir> --worktree <dir> --base <ref>
```

The caller passes the components of the paths being touched (the `/review`
Step 1.7a inference); the engine adds their ancestors and does the rest: the
`/spec` Step 1.6 score, the per-task recency rule, the caps, the 40-line loaded
text, the `pipeline-state.json` `lessons` record, the BR-10 log line and the
BR-4 acknowledgement check. Exit 0 on success; any usage or I/O error is exit 2
with one `lessons: unavailable — <reason>` line, which callers log before
carrying on without lessons. Contract: `partials/lessons.md`.

**Tests.** `tools/adlc/tests/test_lessons.py`. The corpus cases (the LESSON-604
reproduction, the 40-line cap over every lesson) read this repo's own
`.adlc/knowledge/lessons`.

## `regression_check.py` (REQ-691)

The regression-test check: it reads a project's `bugfix.regression_test`
setting and sorts its bug reports into passed, waived, legacy and failed
(REQ-691 architecture ADR-691-A to ADR-691-D). People and CI run it as
`adlc regression-check`; skill fences reach it through
`partials/regression-check.sh`, which runs the installed toolkit's copy. It
reads `.adlc/` under `--root`, which defaults to the current directory, and
writes nothing. Standard library only, plus the sibling `harness_yaml.py`.

```bash
adlc regression-check mode  [--root DIR] [--base REF]
adlc regression-check check [--root DIR] [--base REF] [--require-recorded] [BUG-nnn ...]
```

| Verb | First line | rc |
|---|---|---|
| `mode` | `regression-test: required` or `off`, then a line saying whether the key was set, absent, or there is no config | 0; 2 with `regression-test: error` |
| `check` | `regression-check: pass` / `fail`, then `passed=N waived=N legacy=N failed=N`, then one `BUG-nnn: <reason>` line per failed bug | 0 pass, 1 fail |
| `check`, off project | `regression-check: off`, then a line saying regression tests are off; no bug report is opened | 0 |
| either, error | `regression-check: error` (or `regression-test: error`), then the reason; no counts line, because none was made | 2 |

**The setting.** Read from `.adlc/config.yml` in the working tree, or, with
`--base REF`, from the copy committed at `REF` and never from the disk. A gate
that reads the tree under check lets the fix branch switch its own gate off or
re-point a sibling, so `/bugfix`'s Gate passes
`--base refs/remotes/origin/<integration-branch>` (the rule `lane_check.py`
follows). The setting and `repos:` both come from `REF`, read with
`git ls-tree` and `git cat-file` at the root's repo-relative prefix, so a
project in a subdirectory reads its own config. The bug reports and test files
still come from the working tree and the index. `REF` must be a full ref,
`refs/remotes/<remote>/<branch>` or `refs/heads/<branch>`, in
`A-Z a-z 0-9 . _ / -`, with no `..`, no empty or dot-led component and no
`.lock`. A short name is a usage error because git resolves `origin/main` to a
tag of that name before the remote-tracking branch, so a tag could choose the
config the gate reads; `HEAD`, `FETCH_HEAD`, `ORIG_HEAD` and a bare sha are
usage errors too. `REF` is resolved with `git show-ref --verify`, which takes
it exactly as written: a missing `refs/remotes/origin/main` is rc 2, never
`refs/tags/refs/remotes/origin/main`, where plain `rev-parse` would fall
through. A config that is a symlink, a directory or a submodule at `REF` is rc
2. No config at `REF` is `off`, and the line says `does not exist at REF`.

A missing config is `off`. So is one that names neither `regression_test` nor
`bugfix` outside whole-line comments, and it is not parsed (the `lane_check.py`
byte prefilter: a backslash or a NUL on a non-comment line also forces a
parse). Otherwise the file is parsed with `harness_yaml.loads`, so no PyYAML is
needed. If the YAML subset refuses the file, it stops the caller only when the
file may still define the setting. That means `regression_test` written as a
key anywhere, `bugfix` as a top-level or flow key, or a double-quoted key
holding a backslash (an escape could spell either). Otherwise the parse
failure came from something else, such as a backslash in a value, a `>` block
or an anchor, and the setting is `off`. A parsed `bugfix` must be a mapping
whose only key is `regression_test`, set to `required` or `off`. Anything
else is rc 2, naming the key, the value and the two allowed values. That
includes a typo such as `regresion_test`, and a `bugfix:` whose every child is
commented out. To turn the check off, delete the block or set `off`. A config
that is not UTF-8, or whose path resolves outside the root through a symlink,
is rc 2. An unreadable setting is never read as `off`.

**The bugs.** Without ids, every `.adlc/bugs/BUG-*.md` whose status is
`resolved` or `closed`; with ids, exactly those reports, whatever their status,
and an id with no report fails. Frontmatter is read by the engine's own strict
one-line reader, not `lessons.py`'s lenient one. A key given twice, a block
list, an unclosed quote or flow list, a misspelt key and a wrong type each fail
the report. `regression_tests` is a flow list of paths. `regression_waiver` is
a quoted string, because readers type a plain `false`, `0` or `reason: x`
differently, and some cut it at ` #`. An unquoted waiver fails as the wrong
type. An empty list, an empty string (`""`) and an empty value all count as
absent, so a report copied from the bug template and never filled reads as
legacy. An indented line that names a read key is a misspelling only when no
block is open above it. Under `deploy:` or inside a `notes: |` block, a line
such as `  status: live` is not the report's status. A bug report that is a
symlink fails without being read. A `.adlc` or `.adlc/bugs` that resolves
outside the root is rc 2. When two reports carry one id, an unnamed run fails
each one in scope with the same reason a named run gives.

| Result | When |
|---|---|
| passed | `regression_tests` lists at least one path, and every path passes the rules below |
| waived | `regression_waiver` is non-blank and `regression_tests` is empty |
| legacy | neither is present. Reported, never failed, unless `--require-recorded` (which `/bugfix` Phase 6 passes) |
| failed | anything else: both set, a whitespace-only waiver with no tests, a bad path, a malformed field |

**The path rules.** A path is relative to its repository: no leading `/`, no
`..` segment. It must exist, not be a symlink, resolve inside the repository,
be a regular file, be tracked (`git ls-files --error-unmatch` with literal
pathspecs), and its working-tree bytes must cite the bug id as `BUG-<n>` with
no digit after it, so `BUG-26` never matches `BUG-261`. With
`--require-recorded` it must also be committed in its repository's `HEAD`
(`git cat-file` at `HEAD:./<path>`, relative to the project's or the sibling's
directory), as a regular file (a committed symlink fails with `is not committed
as a regular file (HEAD)`), and that committed copy must cite the id too. A test that is only
staged fails with `is not committed (not in HEAD)`, and one whose citation is
only in the working tree with `does not cite BUG-nnn in its committed copy
(HEAD)`: what merges is the commits, and `/bugfix`'s clean-tree guard covers
only the primary checkout, not a sibling's. A cross-repo entry is
`<repo-id>:<path>`, resolved through `repos.<repo-id>.path` in the same config.
An absolute path is used as written. A relative path resolves from the
project's directory in its repository's main worktree, the way `/proceed`
resolves it from the primary checkout. The main worktree is the parent of
`git rev-parse --git-common-dir`, the rule `partials/id-alloc.sh` uses for
BUG-210, plus the root's repo-relative prefix. So `../api` finds the same
sibling from `/bugfix`'s fix worktree under `.worktrees/` as from the primary.
A root that is its repository's main checkout, or is in no git work tree,
resolves from itself. The primary's own id (`primary: true`) and no prefix both
mean this repo. An undeclared id or a sibling that isn't cloned fails, naming
it.

Under `--require-recorded` the bug report itself must also be committed as it
stands: its bytes on disk must equal a regular file at `HEAD`, or it fails with
`the bug report is not committed (not in HEAD); commit it` or `the bug report
differs from its committed copy (HEAD); commit it`. The report is read from the
working tree, and `git status`, which `/bugfix`'s clean-tree guard trusts, says
nothing about a file marked `skip-worktree` or `assume-unchanged`, so a waiver
written only on disk would otherwise be judged though the PR merges the commits.

The verdict on each bug depends only on the working tree, git's index and,
under `--require-recorded`, each repository's own `HEAD`. The engine never
fetches and never diffs. The only other ref it reads is the one a caller names
with `--base`, and only for the config, so two branches with the same bugs and
tests get the same answer. Output names bug ids, the paths a report
lists and reasons. It never names a file's contents, a symlink's target or the
root's absolute path.

**Tests.** `tools/adlc/tests/test_regression_check.py`. Every case builds its
repository, `.adlc/bugs/` and config under `tmp_path`, because a fixture bug
report in this tree would become a real BUG record.

## Running the tests

```bash
python3 -m pytest tools/adlc/tests
```

Fully offline (no network, no real `~/.claude` mutation) — checks are driven with
`tmp_path` fixtures and injected `Profile`s, so the same suite runs identically on
macOS and Linux.

## install.sh test notes (the ACs, dogfooded)

`install.sh`'s idempotency / dry-run / repair behavior is validated by
dogfooding against a sandbox `HOME` so the real machine is never touched:

```bash
SB="$(mktemp -d)"                       # sandbox HOME
HOME="$SB" ./install.sh                 # first run: N actions
HOME="$SB" ./install.sh                 # second run: 0 actions (idempotent, BR-1)
HOME="$SB" ./install.sh --dry-run       # plan only, no change (AC-7)
# Move the clone, then: ./install.sh --repair re-stamps the shim with the new
# path; `grep -c <old-path> ~/bin/adlc` returns 0 (AC-4, no stale paths).
```

Since REQ-654 the whole installer also runs in sandbox clones under pytest:
[`tests/test_install_home.py`](tests/test_install_home.py) builds a throwaway clone
with **no git remote** (so the closing doctor's `reservations` check SKIPs rather
than pushing) and covers the first and second run on a healthy install, an
overridden `ADLC_HOME`, the skills view tracking an added and a removed skill, a
pre-existing `~/.agents/skills` of the user's own, `--dry-run`, and `--repair`
after a clone move.
