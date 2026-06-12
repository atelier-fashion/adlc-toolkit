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

(`renumber` — REQ-518 — and the tier render — REQ-516 — are the designated next
homes; they slot into the same `SUBCOMMANDS` table.)

## `adlc doctor`

A **strictly read-only** diagnostic. It mutates nothing. It exits **non-zero iff
any non-skip check fails** — `skip` (a macOS-only check on Linux, a delegation
check when delegation is off) never contributes to failure, so the verdict stays
honest on every machine.

```bash
adlc doctor                              # run every check
adlc doctor --checks gh-auth,delegate-gate   # run only the named checks
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
| `gh-auth` | `gh auth status` exits 0 | `gh auth login` | `gh` not installed |
| `git-identity` | `user.name` and `user.email` set | `git config --global user.email …` | — |
| `delegate-gate` | delegation enabled and reachable | (see below) | delegation not opted in (default) |
| `counters` | each `~/.claude/.global-next-{req,bug,lesson}` is numeric, no stale lock | `printf <n> > …` / `rmdir …lock.d` | a counter that doesn't exist yet (first run) |
| `launchctl` | (macOS) kimi setenv LaunchAgent loaded *when delegation is on* | `launchctl bootstrap gui/$(id -u) <plist>` | Linux (macOS-only); delegation off |
| `template-version` | project `.adlc/` scaffold present | run `/template-drift` to compare | run outside a consumer project |
| `claude-code` | (report-only) `claude` on PATH | never fails the verdict | `claude` not detected |

### The `delegate-gate` check (reuses REQ-515)

This check does **not** reinvent delegation config resolution — it builds on the
shipped REQ-515 surface:

- It sources [`partials/delegate-gate.sh`](../../partials/delegate-gate.sh) for
  the 0/1/2 gate verdict and reads `ADLC_DELEGATE_GATE_REASON`.
- It reads delegation config via
  [`tools/kimi/_common.parse_delegate_config`](../kimi/_common.py) (through a
  subprocess probe, so `adlc` keeps no hard import dependency on the kimi
  module).

Mapping:

| gate rc | meaning | doctor result |
|---------|---------|---------------|
| 0 (`ok`) | delegated path live | **PASS** |
| 1 (`not-opted-in` / `disabled-via-env`) | opt-in off | **SKIP** (reason shown) |
| 2 (`no-binary`) + config `enabled: false`/absent | not installed, not requested | **SKIP** |
| 2 (`no-binary`) + config `enabled: true` | **misconfigured** | **FAIL** → `./install.sh --with-delegation`, or set `delegate.enabled: false` |

## The `--checks` pre-flight contract (BR-8)

`adlc doctor --checks id1,id2` runs only the named checks (an unknown id is a
hard error listing the valid ids — never a silent no-op). This is the
**skill pre-flight primitive**: a skill that needs to know "is `gh` authed?" or
"is delegation reachable?" before dispatching work calls
`adlc doctor --checks gh-auth` (or `delegate-gate`) and reads the exit code,
rather than maintaining its own probe shell.

### Sibling-skill audit (BR-8)

REQ-519 audited the existing skills (`/sprint`, `/proceed`, `/wrapup`) for
duplicated environment-probe shell that should converge on doctor. Finding: those
skills currently express their preflight expectations in **prose**, not as
concrete duplicated executable probe code, so there is **no duplicated probe
shell to delete** in this REQ. The `--checks` contract is now available for them
to converge on going forward (e.g. a future REQ replacing a prose "ensure gh is
authed" step with `adlc doctor --checks gh-auth`).

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
