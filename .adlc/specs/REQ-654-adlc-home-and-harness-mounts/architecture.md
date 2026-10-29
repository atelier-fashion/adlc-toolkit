# REQ-654 Architecture — ADLC_HOME, the skills view and `~/.agents/skills`, `adlc harness detect`, `consumer-sync`

## Approach

Four additive surfaces, one rule underneath them: **machine state lives under
`ADLC_HOME`, default `$HOME/.claude`, and nothing else moves.** With the default every
resolved path is byte-identical to today's literal, so the change is a seam, not a
migration.

The work splits along three readers of that rule:

1. **Resolvers.** One shell partial (`partials/adlc-home.sh`) and one Python module
   (`tools/adlc/adlc_home.py`), plus a mirror in `tools/delegate/_machine_config.py`
   because the delegation tools are self-contained. A parity test drives all three over
   one input vector.
2. **Callers.** Every partial, tool, installer and hook that derives a machine-state path
   reads it from a resolver: `id-alloc.sh` (counters, locks, ledger), `forge.sh`
   (machine config, venv), `install.sh` (homes, venv, shim, view, mount),
   `tools/delegate/install.sh` (venv, launchctl helper), `scripts/session-start.sh`
   (config scaffold), and the Python doctor, forge config and agents render.
3. **New surfaces.** `install.sh` builds a skills-only view under `<adlc_home>` and mounts
   it at `~/.agents/skills`. `adlc harness detect` probes the five harnesses. Doctor gains
   `skills-view`, `agents-skills-mount`, `consumer-sync`, and one `harness:<name>` per
   harness. `tools/lint-skills` gains `adlc-home`, which keeps the seam open.

REQ-669 landed first, so this REQ reconciles with it (REQ-669 BR-18). The ToolkitRoot root
line and the ADR-2 default-expansion spelling are unchanged. Their two `.claude` literals
are the compatibility aliases this REQ names, and toolkit reads stay on ToolkitRoot.

## ADR-1: path taxonomy

Every `.claude` path in toolkit code belongs to exactly one of three kinds:

| Kind | Paths | Resolved by |
|---|---|---|
| **Machine state** | counters `.global-next-{req,bug,lesson}`, their `.lock.d` dirs, `.adlc-own-reservations`, `adlc/config.yml` (unless `ADLC_CONFIG`), `delegate-venv`, legacy `kimi-venv`, the launchctl helpers, the skills view, `<adlc_home>/skills` and `<adlc_home>/agents` | `ADLC_HOME` |
| **Compatibility alias** (BR-3) | `~/.claude/skills` (root line arms 2 and 4, the partials' `${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}`), `~/.claude/adlc/plugin-root` (root line arm 3) | literal, kept |
| **Claude Code-owned** | `$CLAUDE_CONFIG_DIR` / `~/.claude` as Claude Code's config dir, its `plugins/` cache, `settings.json`, `CLAUDE.md`, the `~/.claude/skills` and `~/.claude/agents` mounts | literal, kept |

Rationale: the three kinds have three different owners. The toolkit owns machine state,
so it can move it. Skill text and vendored partials, which this REQ does not change, read
the aliases. Claude Code reads the Claude Code paths, and moving them breaks Claude Code,
not the toolkit. Collapsing any two of the kinds is how the seam silently closes again,
which is why the lint (ADR-9) makes every exemption name its kind at its line.

With the default, the machine-state paths resolve to exactly today's literals:
`$HOME/.claude/.global-next-req`, `$HOME/.claude/adlc/config.yml`,
`$HOME/.claude/delegate-venv`, and so on.

## ADR-2: one rule, three resolvers, one parity test

The rule (BR-1, BR-2):

- `ADLC_HOME` unset → `$HOME/.claude` (shell: `$HOME`, which must be absolute, else an
  error naming `HOME`; Python: `os.path.expanduser("~")`, today's spelling).
- `ADLC_HOME` set and absolute (starts with `/`) → used with trailing slashes removed (a
  bare `/` stays `/`), so no derived path carries `//` and the shell and Python agree.
- `ADLC_HOME` set and empty, or set and not absolute → an **error naming `ADLC_HOME`**.
  Never a fall-through to the default.
- `machine_config` = `$ADLC_CONFIG` when set and non-empty (today's precedence), else
  `<adlc_home>/adlc/config.yml`. A set `ADLC_CONFIG` means the home is not consulted for
  the config at all, so an invalid `ADLC_HOME` does not break a caller that only needs the
  config and has `ADLC_CONFIG`.

Implementations:

- `partials/adlc-home.sh`: `adlc_home` prints the home or returns 1 with one stderr line;
  `adlc_home_source` prints `env` or `default`; `adlc_machine_config` prints the config
  path. POSIX, dash-clean, no `local`, `set -u` safe (`${ADLC_HOME+x}`).
- `tools/adlc/adlc_home.py`: `adlc_home()`, `adlc_home_source()`,
  `machine_config_path()`, raising `AdlcHomeError(ValueError)`; pure stdlib (LESSON-395).
- `tools/delegate/_machine_config.py`: an `adlc_home()` mirror, and `default_config_path()`
  built on it. `load_machine_config` turns an `AdlcHomeError` into a `malformed` result,
  so the loader keeps its never-raises contract and delegation fails closed.

Why three: a partial cannot import Python, a Python module cannot be sourced, and the
delegate tools import nothing from `tools/adlc` (they run from `~/bin` links with their own
directory on `sys.path`). This is the REQ-609 "one interpreter rule" precedent, and it gets
the same defence: `tools/adlc/tests/test_adlc_home.py` drives the shell partial, the
`adlc_home` module and the `_machine_config` mirror over one input vector (unset, absolute,
absolute with a space, empty, relative, `./rel`, a literal `~/x`) and asserts identical
accept/reject and identical values. Each implementation's header names the other two.

`install.sh` and `tools/delegate/install.sh` source `partials/adlc-home.sh` from their own
checkout. `scripts/session-start.sh` inlines the check instead: the hook sources nothing
(README "What the hook does"), and `session-start.test.sh` pins its behavior. The
`~/bin/adlc` shim text inlines it too, because it runs with no partials at hand. Both
inline copies name the partial.

## ADR-3: the interpreter rule gains the home

THE ONE INTERPRETER RULE (REQ-609 BR-8) names `$HOME/.claude/delegate-venv`. It becomes
`<adlc_home>/delegate-venv` at all three sites: the shim text in `install.sh`,
`checks.py::_delegate_interpreter`, `forge.sh::_adlc_forge_python`. When the home cannot be
resolved, all three answer `python3` from `$PATH` (checks.py: `sys.executable`), and the
caller that needs the home reports the error. The shim resolves the home **at run time**
(`$ADLC_HOME` when set and absolute, else `$HOME/.claude`), so its text changes once, on
the first `install.sh` run after this REQ, which AC-1 allows.

## ADR-4: the skills view

- **Location**: `<adlc_home>/adlc/skills-view/`, next to the machine config. It is
  machine state, owned entirely by `install.sh`.
- **Shape**: a real directory holding one absolute symlink per skill:
  `<view>/<name>` → `<clone>/<name>` for every `<clone>/<name>/SKILL.md` at depth one
  (hidden directories excluded, the rule `lint-skills`' `_plugin_root_skill_dirs` uses).
  Names are checked against `^[A-Za-z0-9][A-Za-z0-9._-]*$` before use.
- **Maintenance** (`ensure_skills_view`, every run, idempotent): create the directory when
  absent; create a missing link; repoint a link whose target differs (the view is ours,
  so repointing is safe, and it is what `--repair` after a clone move needs); remove a
  view symlink whose name is no longer a skill; leave any non-symlink entry in the view
  alone, with a warning. A view path that is itself a symlink or a non-directory is
  refused before any mutation, with a "move it aside" message (LESSON-017).
- **Not a Claude Code mount**: `~/.claude/skills` stays a link to the clone root. The
  root line's arm 2 tests `~/.claude/skills/partials`, which a skills-only view would not
  have.

Rationale: a directory of links is the smallest structure that exposes only skills and
still tracks the live clone, so an edit to an existing skill reaches every harness without
a rebuild. Only adding or removing a skill directory needs an `install.sh` run (BR-6).

## ADR-5: the `~/.agents/skills` mount

`ensure_agents_mount` classifies `$HOME/.agents/skills` before mutating, prints the state
it found (BR-5, so `--dry-run` names it), then acts:

| Starting state | Action |
|---|---|
| absent | `mkdir -p ~/.agents`; symlink `~/.agents/skills` → `<view>` |
| symlink → `<view>` | nothing |
| symlink, dangling, target ending `/adlc/skills-view` | a view from an earlier `ADLC_HOME`: repoint to `<view>` |
| symlink → a directory | per-skill mode inside the directory it resolves to |
| real directory | per-skill mode |
| anything else (a dangling foreign link, a file) | warn, change nothing |

**Per-skill mode** writes `<dir>/<name>` → `<view>/<name>` for each toolkit skill:

- absent → create the link;
- a symlink whose target is `<view>/<name>` → nothing;
- a symlink whose target ends `/adlc/skills-view/<name>` (ours, from an earlier home) →
  repoint;
- anything else → **skipped and reported** as "name taken by a non-toolkit entry", never
  overwritten;
- a symlink whose target is `<view>/<x>` or `…/adlc/skills-view/<x>` for an `<x>` that is
  no longer a skill → removed (ours, stale).

Ownership is recognised by the target, never by the name, so a user's `spec/` directory
or their own `spec` link is never touched (AC-5). Per-skill links go through the view
rather than straight into the clone, so a clone move repoints only the view.

## ADR-6: homes and mounts under an overridden `ADLC_HOME`

`install.sh` installs Claude Code's mount (`~/.claude/skills` → clone,
`~/.claude/agents` → `<clone>/agents`) on every run, whatever `ADLC_HOME` says (BR-3,
BR-6). When `ADLC_HOME` differs from `$HOME/.claude` it also installs
`<adlc_home>/skills` and `<adlc_home>/agents` with the same targets, and scaffolds the
config at `<adlc_home>/adlc/config.yml`. `skills-symlink` and `agents-symlink` check every
location `install.sh` maintains: one when the home is the default, two when it is not.
Rationale: the fence fallback needs `~/.claude/skills` everywhere, and Claude Code needs
both of its mounts on any machine that runs it. An override that dropped `~/.claude/agents`
would quietly turn every dispatched agent into a generic one on a Claude Code machine.

## ADR-7: `adlc harness detect` and `harness:<name>`

`tools/adlc/harness.py` (pure stdlib) holds the probe table:

| name | binaries tried, in order | user-level skills dir |
|---|---|---|
| `claude` | `claude` | `~/.claude/skills` (Claude Code's own mount), or the adlc plugin installed |
| `copilot` | `copilot` | `$HOME/.agents/skills` |
| `codex` | `codex` | `$HOME/.agents/skills` |
| `gemini` | `gemini` | `$HOME/.agents/skills` |
| `cursor` | `agent`, `cursor-agent` | `$HOME/.agents/skills` |

- **binary**: the first name `shutil.which` finds; `present` / `absent`.
- **version**: `<binary> --version` with stdin closed, in its own process group, under a
  3-second timeout that kills the group. The first non-empty output line, control
  characters stripped, at most 120 characters. A non-zero exit, a timeout, an OS error or
  empty output is `unknown`, never an error (BR-7, open question 2 as resolved).
- **mount**: `n/a` when the binary is absent. Otherwise `mounted` when the harness's skills
  dir reaches this toolkit: for Claude, `~/.claude/skills` resolves to a tree with
  `partials/` and the sample skill (the doubled-install test), or the plugin is installed;
  for the other four, at least one toolkit skill under `$HOME/.agents/skills/<name>`
  resolves to `<toolkit>/<name>`. Else `not-mounted`.

The System Model row names Claude's dir as `<adlc_home>/skills`. With the default that is
the same directory. With an override it is not, and Claude Code reads `~/.claude/skills`,
which ADR-6 keeps, so the probe reads where Claude Code reads. The spec row is amended to
match.

`adlc harness detect` prints one row per harness and exits 0 whenever it ran. `--json`
prints a JSON array of `{name, binary, state, path, version, mount}`. It is registered in
`adlc.py`'s `SUBCOMMANDS` (REQ-519 BR-11); `adlc harness` with no verb or another verb
prints usage and exits 2.

Doctor's `claude-code` check is replaced by five `harness:<name>` checks built from the
same table: PASS (report-only) with path, version and mount when present, SKIP when absent.
They never FAIL.

## ADR-8: doctor checks `skills-view`, `agents-skills-mount`, `consumer-sync`

Both mount checks are `applies_to=_on_symlink_route` with the existing
`_SYMLINK_ROUTE_ONLY` notice: the plugin route never runs `install.sh`. Their fixes print
`<clone>/install.sh` (quoted, absolute), so the line runs verbatim from any directory, and
only when `_install_sh_ok` (REQ-669 BR-11).

- **`skills-view`**: FAIL when the view is missing; when a skill has no link, or a link
  dangles or points anywhere but `<clone>/<name>`; when a view link names a directory that
  is not a skill. The detail says a new skill reaches the four harnesses only after
  `install.sh` runs (BR-6).
- **`agents-skills-mount`**: PASS when `~/.agents/skills` resolves to the view, or when it
  is a directory in which every toolkit skill not taken by a non-toolkit entry has a link
  resolving to `<clone>/<name>`. Taken names are listed in the detail, not failed: the
  user owns them. FAIL otherwise.
- **`consumer-sync`** (both routes):
  1. **Root**: `$ADLC_REPOS_ROOT` when set; else the parent of the main worktree of the
     repo holding the working directory (id-alloc's default); else, outside any repo, the
     parent of the toolkit clone's main worktree.
  2. **Consumers**: each non-hidden child of the root that is a git checkout (a `.git` file
     or directory), has a `.adlc/partials/` directory, and is not the toolkit itself. None
     → SKIP.
  3. **Baseline** (BUG-204): on a checkout (the root has `.git`), name the branch, whether
     `partials/` is dirty, the default branch (`origin/HEAD`, else `main`) and the distance
     behind `origin/<default>` **as of the last fetch**. Doctor never fetches: it writes to
     no repo, `.git` included. Clean, on the default branch and 0 behind → compare against
     the working tree. Otherwise, when `origin/<default>` exists → compare against
     `git show origin/<default>:partials/<name>`. Neither → `unverified-baseline`. On the
     plugin route (no `.git`) the baseline is `adlc plugin <version>` from the copy's
     manifest, compared directly; an unreadable version is `unverified-baseline`.
  4. **Verdict per consumer**: every canonical `*.sh` compared by content; a differing or
     absent vendored copy counts as stale (`forge.sh`, `adlc-home.sh (missing)`); a
     consumer-only partial is not this check's business (`/template-drift` reports it).
  5. **Result**: FAIL when any consumer is stale, one line per repo with its files, and
     one fix per repo: `cd '<repo>' && claude -p '/template-drift'` (`/adlc:template-drift`
     on the plugin route). SKIP when the baseline is unverified: it names the reason and
     the repos that differ from what is on disk, and asserts nothing. PASS otherwise.

## ADR-9: the `adlc-home` lint

A per-root check in `tools/lint-skills/check.py`, armed like `toolkit-path`
(`is_plugin_root`) and walked by the same `_scan_surfaces`:

- **Surfaces**: `partials/*.sh`, `tools/**` (code files), `install.sh`, `scripts/*`.
- **Spellings**: `~/.claude`; `$HOME/.claude`, `${HOME}/.claude`, `${HOME:-…}/.claude`,
  `"$HOME"/.claude` and the escaped `\"\$HOME\"/.claude` a generated script carries;
  `$<var>/.claude` for any variable whose name contains `home` (case-insensitive); and in
  Python, `expanduser("~")`, `Path.home()` or a `*home*` name joined with `".claude"`.
  `.claude` must end the path component (`.claude-plugin`, `.claude.json` do not match).
- **Not checked**: full-line comments (`#`); Python docstrings (found with `ast`); files
  under `tests/` or `fixtures/`; `tools/lint-skills/check.py`, which spells the patterns;
  the canonical root line; the ADR-2 token `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/`.
- **The marker**: a line carrying `adlc-home: claude-code`, `adlc-home: alias` or
  `adlc-home: default` is exempt. `default` is for display text that names the default
  location to a human where no resolved path exists (the rendered agent header). Any other
  `adlc-home:` value is itself a finding, so a typo cannot exempt a line.

It is distinct from `toolkit-path` (toolkit *reads* on the plugin surface, REQ-669) and
from REQ-666's planned `no-harness-path` (skill text). Each finding names the ways out:
read the resolver, or mark the line with its kind.

## Data model and API changes

- `pipeline-state` and spec schemas: none.
- Machine config schema: none. `ADLC_HOME` is an environment variable only.
- New CLI surface: `adlc harness detect [--json]`.
- Doctor: `claude-code` is removed and replaced by
  `harness:{claude,copilot,codex,gemini,cursor}`; new `skills-view`,
  `agents-skills-mount`, `consumer-sync`. `--checks claude-code` now errors as an unknown
  id, which the CHANGELOG says.

## Applicable lessons

- LESSON-441 — stale vendored partials keep working only because every literal they carry
  still resolves (the aliases); `consumer-sync` makes the stale copies visible.
- LESSON-395 — `adlc_home.py`, `harness.py` and the new checks are pure stdlib.
- LESSON-017 — `install.sh` resolves and validates `ADLC_HOME`, the view path and the
  mount state before its first mutation.
- LESSON-019 — the lint changes in the same change as the code it guards.
- LESSON-392 — one resolver per language, parity-tested, not a probe that re-implements
  half the rule.
- LESSON-440 — every detector (lint, `consumer-sync`, mount checks) has a benign-path case.
- LESSON-581 — an unverified baseline is `unverified-baseline`, never a plausible
  `stale` or `in-sync`.
- LESSON-572 — every remediation is a command its reader can run verbatim.
- LESSON-582 / LESSON-335 — no `case` in `$( )`, no unmatched globs under zsh.

## Proposed additions to `.adlc/context/architecture.md`

An `ADLC_HOME` bullet under "Key cross-cutting dependencies" carrying the ADR-1 taxonomy,
the counters' paths restated as `<adlc_home>/…`, and the install-route bullet's "machine
state stays where it is" extended to "under `ADLC_HOME`, default `~/.claude`".
conventions.md gets the one-sentence rule BR-12 asks for, in "Bash in skills".
