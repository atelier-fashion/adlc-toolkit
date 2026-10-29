"""Subprocess-based regression tests for `partials/delegate-tools-path.sh`.

Exercises the resolver's three resolution paths (REQ-433 ADR-2) and its
non-fatal/silent contract (ADR-1, BR-1, LESSON-008/-012/-013). Mirrors the
harness conventions of `test_partials.py`: shell out via `subprocess` with
`sh -c '. <partial>; printf %s "$VAR"'` under a controlled `cwd`/`env`, and
override `HOME` so the real `~/.claude` is never read or mutated.

Resolution contract under test (`partials/delegate-tools-path.sh`, sourced):
  1. `tools/delegate/emit-telemetry.sh` executable rel. CWD → DELEGATE_TOOLS=tools/delegate
  2. elif `<ToolkitRoot>/tools/delegate/emit-telemetry.sh` executable →
     DELEGATE_TOOLS=<ToolkitRoot>/tools/delegate, where ToolkitRoot is
     `${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}` (REQ-669 ADR-2): the exported
     root when set, else the symlink install under HOME. A set root is the
     install, so HOME's copy is then never consulted.
  3. else → DELEGATE_TOOLS=tools/delegate  (non-fatal degrade; emits nothing; rc 0)
It must never write to stdout/stderr and must not abort a `set -eu` caller.
"""

import subprocess
from pathlib import Path

# Absolute path to the partial, resolved from this test file's location so the
# test is location-independent — never hardcode /Users/... . This file lives at
# <repo>/tools/delegate/tests/, i.e. 3 dirs deep, so parents[3] is the repo root
# (parents[0]=tests, [1]=delegate, [2]=tools, [3]=<repo>).
PARTIAL = Path(__file__).resolve().parents[3] / "partials" / "delegate-tools-path.sh"

# Print DELEGATE_TOOLS with no trailing newline so stdout is *exactly* the resolved
# value — lets the "silent" assertions prove the partial itself adds nothing.
_PROBE = f'. "{PARTIAL}"; printf "%s" "$DELEGATE_TOOLS"'

# Minimal PATH so `sh` builtins / `[ -x ]` / `printf` work without leaking the
# host environment into the subprocess.
_BASE_PATH = "/usr/bin:/bin"


def _run(script, env, cwd, posix_flags=False):
    """Run `script` under POSIX `sh` (not bash) with a controlled env/cwd.

    posix_flags=True runs `sh -eu -c` to prove the sourced partial does not
    abort a strict-mode caller (unset var / nonzero command would `exit`).
    """
    argv = ["sh", "-eu", "-c", script] if posix_flags else ["sh", "-c", script]
    return subprocess.run(
        argv, env=env, cwd=str(cwd),
        capture_output=True, text=True,
    )


def _make_emit(parent):
    """Create `<parent>/emit-telemetry.sh` as an executable stub and return it."""
    parent.mkdir(parents=True, exist_ok=True)
    f = parent / "emit-telemetry.sh"
    f.write_text("#!/bin/sh\nexit 0\n")
    f.chmod(0o755)
    return f


# ---------------------------------------------------------------------------
# Resolution path 1: project-local tools/delegate present (canonical / dogfooding)
# ---------------------------------------------------------------------------

def test_local_present_resolves_to_tools_delegate(tmp_path):
    """CWD has executable `tools/delegate/emit-telemetry.sh` → DELEGATE_TOOLS=tools/delegate.

    HOME points at an empty dir so the local branch is unambiguously the one
    that fires (not the global fallback).
    """
    _make_emit(tmp_path / "tools" / "delegate")
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, tmp_path)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/delegate", repr(r.stdout)
    # silent: stdout is exactly our printf, partial added nothing; stderr empty.
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Resolution path 2: no local, global symlink target present
# ---------------------------------------------------------------------------

def test_global_only_resolves_to_home_skills_path(tmp_path):
    """No local `tools/delegate`, but `$HOME/.claude/skills/tools/delegate/emit-telemetry.sh`
    is executable → DELEGATE_TOOLS resolves to that absolute `$HOME/...` path.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()  # deliberately NO tools/delegate here
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "delegate")

    expected = str(fake_home / ".claude" / "skills" / "tools" / "delegate")
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == expected, repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Resolution path 3: neither present → non-fatal degrade to tools/delegate (ADR-2)
# ---------------------------------------------------------------------------

def test_neither_present_degrades_to_tools_delegate(tmp_path):
    """Neither local nor global probe resolves → DELEGATE_TOOLS=tools/delegate, rc 0.

    ADR-2 degrade target: behaves exactly as today under the existing
    `2>/dev/null`/`|| true` call-site guards (LESSON-008 BR-4).
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()  # empty: no .claude/skills/tools/delegate

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Non-fatal under `set -eu`: sourcing must not abort a strict-mode caller
# ---------------------------------------------------------------------------

def test_non_fatal_under_set_eu(tmp_path):
    """`sh -eu -c '. partial; printf "%s" "$DELEGATE_TOOLS"'` for the degrade case:
    the process must exit 0 (not aborted by -e/-u), stdout is the resolved
    value, stderr empty. Proves the partial never trips `set -eu` (no unset
    var read, no command returning nonzero) — BR-1 / LESSON-012.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, cwd, posix_flags=True)

    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_set_eu_local_and_global_paths_also_non_fatal(tmp_path):
    """The non-fatal contract also holds on the local-present and global-only
    paths under `set -eu` (every branch is strict-mode safe + silent).
    """
    # local-present under -eu
    local_cwd = tmp_path / "local"
    _make_emit(local_cwd / "tools" / "delegate")
    empty_home = tmp_path / "emptyhome"
    empty_home.mkdir()
    env = {"HOME": str(empty_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, local_cwd, posix_flags=True)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)

    # global-only under -eu
    global_cwd = tmp_path / "global"
    global_cwd.mkdir()
    global_home = tmp_path / "globalhome"
    _make_emit(global_home / ".claude" / "skills" / "tools" / "delegate")
    expected = str(global_home / ".claude" / "skills" / "tools" / "delegate")
    env = {"HOME": str(global_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, global_cwd, posix_flags=True)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == expected, repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Probe is `[ -x ]`: a present-but-NOT-executable emit-telemetry.sh must NOT
# satisfy branch 1 — resolution falls through to global / degrade.
# ---------------------------------------------------------------------------

def test_local_present_but_not_executable_falls_through(tmp_path):
    """`tools/delegate/emit-telemetry.sh` exists but is mode 0o644 → branch 1's
    `[ -x ]` fails; with an executable global copy, DELEGATE_TOOLS must resolve to
    the global path (NOT the non-executable local one)."""
    local_delegate = tmp_path / "tools" / "delegate"
    local_delegate.mkdir(parents=True)
    non_exec = local_delegate / "emit-telemetry.sh"
    non_exec.write_text("#!/bin/sh\nexit 0\n")
    non_exec.chmod(0o644)  # deliberately NOT executable
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "delegate")

    expected = str(fake_home / ".claude" / "skills" / "tools" / "delegate")
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, tmp_path)

    assert r.returncode == 0, r.stderr
    assert r.stdout == expected, repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# HOME unset entirely (not just empty) under `set -eu`: the `${HOME:-}` guard
# must keep the partial non-fatal (a bare `$HOME` would trip `-u` and abort).
# ---------------------------------------------------------------------------

def test_home_unset_under_set_eu_is_non_fatal(tmp_path):
    """env has NO `HOME` key at all; `sh -eu` would abort on a bare `$HOME`.
    With `${HOME:-}` the partial degrades to tools/delegate, rc 0, silent."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()  # no local tools/delegate

    env = {"PATH": _BASE_PATH}  # intentionally NO "HOME"
    r = _run(_PROBE, env, cwd, posix_flags=True)

    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# `export` contract (BR-1): DELEGATE_TOOLS must be visible to a CHILD process,
# not merely set in the sourcing shell.
# ---------------------------------------------------------------------------

def test_delegate_tools_is_exported_to_child(tmp_path):
    """Source the partial, then read $DELEGATE_TOOLS from a *child* `sh -c` — it is
    only visible there if `export` actually took effect. Guards against a
    future refactor that drops `export` (the same-shell probe wouldn't catch)."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()  # degrade path → DELEGATE_TOOLS=tools/delegate

    child_probe = f'. "{PARTIAL}"; sh -c \'printf "%s" "$DELEGATE_TOOLS"\''
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(child_probe, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# REQ-669 ADR-2: tier 2 reads ToolkitRoot. With ADLC_TOOLKIT_ROOT exported (the
# plugin route), the root's copy is used and HOME's ~/.claude/skills is not.
# ---------------------------------------------------------------------------

def test_toolkit_root_resolves_without_home_skills(tmp_path):
    """Plugin route: ADLC_TOOLKIT_ROOT names a cache-shaped root, HOME has no
    `.claude/skills` at all → DELEGATE_TOOLS=<root>/tools/delegate."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    root = tmp_path / "plugins" / "cache" / "mkt" / "adlc" / "1.0.0"
    _make_emit(root / "tools" / "delegate")
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)  # no skills/ beneath it

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH, "ADLC_TOOLKIT_ROOT": str(root)}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == str(root / "tools" / "delegate"), repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_toolkit_root_wins_over_home_skills(tmp_path):
    """Both installs present (a doubled machine whose fence resolved the plugin
    root): the exported root wins; HOME's copy is not read."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    root = tmp_path / "root"
    _make_emit(root / "tools" / "delegate")
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "delegate")

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH, "ADLC_TOOLKIT_ROOT": str(root)}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == str(root / "tools" / "delegate"), repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_toolkit_root_without_tools_degrades_not_falls_back_to_home(tmp_path):
    """A set root with no `tools/delegate` degrades to tier 3. It does NOT fall
    back to HOME's copy: ToolkitRoot is the install, and two installs never mix."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "delegate")

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH, "ADLC_TOOLKIT_ROOT": str(root)}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/delegate", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_empty_toolkit_root_uses_home_symlink_install(tmp_path):
    """An empty ADLC_TOOLKIT_ROOT is the same as unset (`:-`): the symlink
    install under HOME answers, exactly as before REQ-669 (BR-3)."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "delegate")

    expected = str(fake_home / ".claude" / "skills" / "tools" / "delegate")
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH, "ADLC_TOOLKIT_ROOT": ""}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == expected, repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_home_unset_with_toolkit_root_under_set_eu(tmp_path):
    """HOME unset, ADLC_TOOLKIT_ROOT set, `sh -eu`: the root's copy resolves and
    the default arm's bare `$HOME` is never expanded, so `-u` does not abort."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    root = tmp_path / "root"
    _make_emit(root / "tools" / "delegate")

    env = {"PATH": _BASE_PATH, "ADLC_TOOLKIT_ROOT": str(root)}  # NO "HOME"
    r = _run(_PROBE, env, cwd, posix_flags=True)

    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == str(root / "tools" / "delegate"), repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)
