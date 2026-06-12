# tools/adlc — the `adlc` umbrella CLI

`adlc` is the toolkit's user-facing command-line entry point. It is a
**pure-standard-library** Python CLI (no third-party deps, no venv) so it runs
on any machine that has cloned the toolkit — including one that has never opted
into delegation. Subcommands are registered in a data-driven table
(`SUBCOMMANDS` in `adlc.py`), so future REQs add commands without touching
dispatch logic.

Installed on your PATH by the root [`install.sh`](../../install.sh) (it writes a
shim at `~/bin/adlc`). You can also run it directly:

```bash
python3 tools/adlc/adlc.py doctor
adlc --version
```

## Subcommands

| Command | Purpose |
|---------|---------|
| `doctor` | Read-only environment health check (below). |
| `agents render` | Render `agents/*.md` `model:` frontmatter from tier classes + config (below). |

(`renumber` — REQ-518 — is the next designated home; it slots into the same
`SUBCOMMANDS` table.)

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
and re-run doctor; it should turn green.

### Checks

| id | passes when | fails → remediation | skip when |
|----|-------------|---------------------|-----------|
| `skills-symlink` | `~/.claude/skills` is a symlink into a git checkout | `ln -sfn <root> ~/.claude/skills` | — |
| `agents-symlink` | `~/.claude/agents` resolves to `<root>/agents` | `ln -sfn <root>/agents ~/.claude/agents` | — |
| `toolkit-clean` | clone is on a branch and not dirty | `git -C <root> checkout main` / `git status` | — |
| `path-shims` | `adlc` is on PATH and `adlc --version` runs | `./install.sh --repair`, restart shell | — |
| `gh-present` | `gh` (GitHub CLI) is on PATH | per-OS install line (`brew install gh`, …) | — |
| `forge` | resolved forge provider's backend CLI present + auth valid + read-only API probe (github: `gh auth status`; azure-devops: `az account show` or PAT env var). **Supersedes the former `gh-auth` check** (REQ-520). | provider-specific (`gh auth login`; `az login` / set the PAT env var; or install `az`) | repo has no git remote |
| `git-identity` | `user.name` and `user.email` set | `git config --global user.email …` | — |
| `delegate-gate` | delegation enabled and reachable | (see below) | delegation not opted in (default) |
| `counters` | each `~/.claude/.global-next-{req,bug,lesson}` is numeric, no stale lock | `printf <n> > …` / `rmdir …lock.d` | a counter that doesn't exist yet (first run) |
| `launchctl` | (macOS) delegate setenv LaunchAgent loaded *when delegation is on* | `launchctl bootstrap gui/$(id -u) <plist>` | Linux (macOS-only); delegation off |
| `template-version` | project `.adlc/` scaffold present | run `/template-drift` to compare | run outside a consumer project |
| `claude-code` | (report-only) `claude` on PATH | never fails the verdict | `claude` not detected |

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
| 1 (`not-opted-in` / `disabled-via-env`) | opt-in off | **SKIP** (reason shown) |
| 2 (`no-binary`) + config `enabled: false`/absent | not installed, not requested | **SKIP** |
| 2 (`no-binary`) + config `enabled: true` | **misconfigured** | **FAIL** → `./install.sh --with-delegation`, or set `delegate.enabled: false` |

## `adlc agents render` (REQ-516)

Every agent in [`agents/`](../../agents) declares a stable **tier class** in its
frontmatter (`tier:`); the `model:` line is **rendered output**, not hand-edited
(each agent carries a `<!-- ... do not hand-edit -->` comment saying so). This
command stamps the resolved `model:` into each agent file so an adopter can
re-tier every agent from one config block instead of editing 18 files (whose
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

A pure-standard-library helper module (not a subcommand) that backs the forge
adapter (`partials/forge.sh`) and the `forge` doctor check. It reads the `forge:`
block of the shared ADLC config (a minimal flat-YAML reader mirroring
`tools/delegate/_common.parse_delegate_config`), resolves the provider with precedence
per-project `.adlc/config.yml` > machine config > `auto` (origin-URL detection,
fail-loud on an unrecognized host), and refuses a key-shaped `forge.auth` value
(BR-6). CLI surface used by the partial and the check:

```bash
python3 tools/adlc/forge_config.py resolve-provider [<repo-dir>]   # prints github|azure-devops
python3 tools/adlc/forge_config.py validate-auth <value>           # exit 2 if key-shaped
```

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
