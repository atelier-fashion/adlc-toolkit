"""Subprocess-based regression tests for `partials/kimi-tools-path.sh`.

Exercises the resolver's three resolution paths (REQ-433 ADR-2) and its
non-fatal/silent contract (ADR-1, BR-1, LESSON-008/-012/-013). Mirrors the
harness conventions of `test_partials.py`: shell out via `subprocess` with
`sh -c '. <partial>; printf %s "$VAR"'` under a controlled `cwd`/`env`, and
override `HOME` so the real `~/.claude` is never read or mutated.

Resolution contract under test (`partials/kimi-tools-path.sh`, sourced):
  1. `tools/kimi/emit-telemetry.sh` executable rel. CWD → KIMI_TOOLS=tools/kimi
  2. elif `$HOME/.claude/skills/tools/kimi/emit-telemetry.sh` executable →
     KIMI_TOOLS=$HOME/.claude/skills/tools/kimi
  3. else → KIMI_TOOLS=tools/kimi  (non-fatal degrade; emits nothing; rc 0)
It must never write to stdout/stderr and must not abort a `set -eu` caller.
"""

import subprocess
from pathlib import Path

# Absolute path to the partial, resolved from this test file's location so the
# test is location-independent — never hardcode /Users/... . This file lives at
# <repo>/tools/kimi/tests/, i.e. 3 dirs deep, so parents[3] is the repo root
# (parents[0]=tests, [1]=kimi, [2]=tools, [3]=<repo>).
PARTIAL = Path(__file__).resolve().parents[3] / "partials" / "kimi-tools-path.sh"

# Print KIMI_TOOLS with no trailing newline so stdout is *exactly* the resolved
# value — lets the "silent" assertions prove the partial itself adds nothing.
_PROBE = f'. "{PARTIAL}"; printf "%s" "$KIMI_TOOLS"'

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
# Resolution path 1: project-local tools/kimi present (canonical / dogfooding)
# ---------------------------------------------------------------------------

def test_local_present_resolves_to_tools_kimi(tmp_path):
    """CWD has executable `tools/kimi/emit-telemetry.sh` → KIMI_TOOLS=tools/kimi.

    HOME points at an empty dir so the local branch is unambiguously the one
    that fires (not the global fallback).
    """
    _make_emit(tmp_path / "tools" / "kimi")
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, tmp_path)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/kimi", repr(r.stdout)
    # silent: stdout is exactly our printf, partial added nothing; stderr empty.
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Resolution path 2: no local, global symlink target present
# ---------------------------------------------------------------------------

def test_global_only_resolves_to_home_skills_path(tmp_path):
    """No local `tools/kimi`, but `$HOME/.claude/skills/tools/kimi/emit-telemetry.sh`
    is executable → KIMI_TOOLS resolves to that absolute `$HOME/...` path.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()  # deliberately NO tools/kimi here
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "kimi")

    expected = str(fake_home / ".claude" / "skills" / "tools" / "kimi")
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == expected, repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Resolution path 3: neither present → non-fatal degrade to tools/kimi (ADR-2)
# ---------------------------------------------------------------------------

def test_neither_present_degrades_to_tools_kimi(tmp_path):
    """Neither local nor global probe resolves → KIMI_TOOLS=tools/kimi, rc 0.

    ADR-2 degrade target: behaves exactly as today under the existing
    `2>/dev/null`/`|| true` call-site guards (LESSON-008 BR-4).
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()  # empty: no .claude/skills/tools/kimi

    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/kimi", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# Non-fatal under `set -eu`: sourcing must not abort a strict-mode caller
# ---------------------------------------------------------------------------

def test_non_fatal_under_set_eu(tmp_path):
    """`sh -eu -c '. partial; printf "%s" "$KIMI_TOOLS"'` for the degrade case:
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
    assert r.stdout == "tools/kimi", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_set_eu_local_and_global_paths_also_non_fatal(tmp_path):
    """The non-fatal contract also holds on the local-present and global-only
    paths under `set -eu` (every branch is strict-mode safe + silent).
    """
    # local-present under -eu
    local_cwd = tmp_path / "local"
    _make_emit(local_cwd / "tools" / "kimi")
    empty_home = tmp_path / "emptyhome"
    empty_home.mkdir()
    env = {"HOME": str(empty_home), "PATH": _BASE_PATH}
    r = _run(_PROBE, env, local_cwd, posix_flags=True)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == "tools/kimi", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)

    # global-only under -eu
    global_cwd = tmp_path / "global"
    global_cwd.mkdir()
    global_home = tmp_path / "globalhome"
    _make_emit(global_home / ".claude" / "skills" / "tools" / "kimi")
    expected = str(global_home / ".claude" / "skills" / "tools" / "kimi")
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
    """`tools/kimi/emit-telemetry.sh` exists but is mode 0o644 → branch 1's
    `[ -x ]` fails; with an executable global copy, KIMI_TOOLS must resolve to
    the global path (NOT the non-executable local one)."""
    local_kimi = tmp_path / "tools" / "kimi"
    local_kimi.mkdir(parents=True)
    non_exec = local_kimi / "emit-telemetry.sh"
    non_exec.write_text("#!/bin/sh\nexit 0\n")
    non_exec.chmod(0o644)  # deliberately NOT executable
    fake_home = tmp_path / "home"
    _make_emit(fake_home / ".claude" / "skills" / "tools" / "kimi")

    expected = str(fake_home / ".claude" / "skills" / "tools" / "kimi")
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
    With `${HOME:-}` the partial degrades to tools/kimi, rc 0, silent."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()  # no local tools/kimi

    env = {"PATH": _BASE_PATH}  # intentionally NO "HOME"
    r = _run(_PROBE, env, cwd, posix_flags=True)

    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout == "tools/kimi", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


# ---------------------------------------------------------------------------
# `export` contract (BR-1): KIMI_TOOLS must be visible to a CHILD process,
# not merely set in the sourcing shell.
# ---------------------------------------------------------------------------

def test_kimi_tools_is_exported_to_child(tmp_path):
    """Source the partial, then read $KIMI_TOOLS from a *child* `sh -c` — it is
    only visible there if `export` actually took effect. Guards against a
    future refactor that drops `export` (the same-shell probe wouldn't catch)."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()  # degrade path → KIMI_TOOLS=tools/kimi

    child_probe = f'. "{PARTIAL}"; sh -c \'printf "%s" "$KIMI_TOOLS"\''
    env = {"HOME": str(fake_home), "PATH": _BASE_PATH}
    r = _run(child_probe, env, cwd)

    assert r.returncode == 0, r.stderr
    assert r.stdout == "tools/kimi", repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)
