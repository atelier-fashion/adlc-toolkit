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

Each is one entry in the data-driven `SUBCOMMANDS` table (REQ-519 BR-11).

## Machine state: `ADLC_HOME` (REQ-654)

Every machine-state path this CLI reads — the id counters and their locks, the
machine config, the delegate venv, the skills view — is under `ADLC_HOME`,
default `~/.claude`, resolved by [`adlc_home.py`](adlc_home.py). With it unset
every path is the one it always was. `ADLC_CONFIG` still names the config file
outright. A set `ADLC_HOME` that is empty or not absolute stops `adlc doctor`
before any check, with exit 2 and a message naming the variable.

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
| `consumer-sync` | every consumer repo under `$ADLC_REPOS_ROOT` (default: the parent of the current repo's main worktree, as id-alloc reads it) whose `.adlc/partials/` matches the canonical partials by content (REQ-654 BR-8). The baseline is named first (branch, `partials/` dirty or not, distance behind `origin/<default>` as of the last fetch); a checkout that is not clean-and-current is compared through `origin/<default>`, the plugin route against `adlc plugin <version>`. It never fetches and writes to no repo | one line per stale repo: `cd '<repo>' && claude -p /template-drift` (`/adlc:template-drift` on the plugin route) | no consumer under the root; **unverified-baseline** (no `origin/<default>` ref, or no readable plugin version) is a SKIP that names the repos that differ and asserts nothing |
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
to be committed (credentials redacted, `$HOME` written as `~`). The probes need
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
| `shell-timeout` | 6.6 | all | `sleep 125 && touch` left its sentinel (default shell timeout ≥ 120 s) |
| `trust-then-headless` | 6.8 (trust + load) | all | two halves: `hooks-loaded` (a session-start hook's sentinel) and `allowlist-loaded` (a project-only allow worked); copilot has no project-local allow form, so its status is `hooks-loaded` alone |
| `session-start-context` | 6.8 (injection) | all | the reversed nonce a session-start hook added to the context |
| `stdin-prompt` | 6.12 | all | a 420-line prompt on stdin, nonce on line 250; with and without the prompt flag |
| `fence-vs-allowlist` | 6.11 | all | partials/README.md's sourcing fence, byte for byte, under `routine-only`, `broad-sh` and `broad-first-token` allowlists |
| `transcript-locate` | 6.9 | all | a session file under the harness's transcript root naming the run; its first 20 records, redacted, become `fixtures/<harness>.jsonl` |
| `arg-substitution` | 6.10 | claude | a skill with no `$ARGUMENTS` whose fence writes `"$1"` to a sentinel: `hello` passes, empty or a literal `$1` fails |

Not probed, and recorded as such in the result's `coverage`: 6.2 (a documentation
question), 6.5 (a product-scope survey) and 6.7 (answered by REQ-654's skills-only
view). 6.1a is recorded as `headless only`; the interactive half is REQ-655's.

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
`baseline*` control did not. A headless ask is already a deny on most harnesses,
so `lone-deny` is `n/a` unless `baseline` ran its command.

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
- The harness's own session records, which are left in place.

Claude runs with `--setting-sources project,local` and the project pins
`permissions.defaultMode: "default"`, so a project-local allow or deny is what is
measured, not your user settings.

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
