"""The `adlc` shim the ROOT install.sh writes (REQ-609 BR-8, ADR-2, AC-5).

Since REQ-609 the ADLC config is parsed with PyYAML, which `install.sh` pins in
`~/.claude/delegate-venv`. So the shim has to prefer that interpreter when it
exists — otherwise `adlc` runs under whatever `python3` `$PATH` happens to
resolve, which on the reference machine carries PyYAML only because Apple ships
it with the system interpreter (REQ-609 BR-8's verification note).

It has to fall back too: the venv exists only after `install.sh
--with-delegation`, and a shim that `exec`s a missing interpreter would break
`adlc doctor` on exactly the machine that most needs it (LESSON-395).

Both halves are asserted by RUNNING the generated shim with a fake venv
interpreter present and absent, and reading which one got the arguments — not by
matching the text we just wrote against itself (LESSON-478: the artifact is the
evidence).
"""

import os
import stat
import subprocess

# The slice of install.sh under test: the output helpers, `atomic_write`, and
# `ensure_adlc_shim`, evaluated verbatim.
_SLICE_START = "note()"
_SLICE_END = "# --- PATH wiring"


def _shim_functions(repo_root):
    """The real text of install.sh's shim mutator, or a loud failure.

    Why a slice rather than a run of the whole installer: `install.sh` ends by
    running a full `adlc doctor`, whose `reservations` check PUSHES a probe ref
    to `origin` — a network mutation no unit test may make. The alternative,
    sourcing the script behind a "library mode" env var, would give the
    installer a switch that silently turns it into a no-op if it ever leaked
    into a real shell, which is the failure LESSON-006 tells installers not to
    have. So the functions are evaluated as written, and the anchors are
    asserted: if install.sh is restructured, this test fails loudly instead of
    quietly testing nothing.
    """
    with open(os.path.join(repo_root, "install.sh"), encoding="utf-8") as fh:
        text = fh.read()
    # The main body must still CALL the function this test drives directly.
    assert "\nensure_adlc_shim\n" in text, \
        "install.sh no longer calls ensure_adlc_shim — this test drives a dead function"
    assert text.count(_SLICE_START) == 1 and text.count(_SLICE_END) == 1
    block = text[text.index(_SLICE_START):text.index(_SLICE_END)]
    for needed in ("atomic_write() {", "ensure_adlc_shim() {"):
        assert needed in block, f"install.sh restructured: '{needed}' left the slice"
    return block


def _write_exec(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _sandbox(tmp_path, repo_root, with_venv, dry=False):
    """Generate a shim with install.sh's own function in a sandbox HOME.

    Returns (shim_path, home, marker_path, generator_output). `marker_path` is
    written by the fake venv interpreter when — and only when — it is the one
    that runs.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    fake_repo = tmp_path / "repo"
    (fake_repo / "tools" / "adlc").mkdir(parents=True, exist_ok=True)
    (fake_repo / "tools" / "adlc" / "adlc.py").write_text(
        "import sys\nprint('ADLC_MAIN', sys.argv[1:])\n")
    marker = tmp_path / "venv-interpreter-ran"
    if with_venv:
        _write_exec(
            home / ".claude" / "delegate-venv" / "bin" / "python3",
            '#!/bin/sh\nprintf \'%%s\\n\' "$*" > "%s"\nexec /usr/bin/env python3 "$@"\n'
            % marker,
        )
    driver = tmp_path / "drive.sh"
    driver.write_text(
        "set -eu\n"
        'DRY="%d"\n'
        "ACTIONS=0\n"
        'BIN_DIR="%s"\n'
        'REPO_ROOT="%s"\n'
        "%s\n"
        "ensure_adlc_shim\n"
        "echo '--- second run ---'\n"
        "ensure_adlc_shim\n"
        % (1 if dry else 0, home / "bin", fake_repo, _shim_functions(repo_root))
    )
    out = subprocess.run(
        ["bash", str(driver)], capture_output=True, text=True,
        env=dict(os.environ, HOME=str(home)),
    )
    assert out.returncode == 0, out.stderr
    return home / "bin" / "adlc", home, marker, out


def _run_shim(shim, home):
    """Run the generated shim the way a user would: `adlc` with their own HOME."""
    return subprocess.run(
        [str(shim), "doctor"], capture_output=True, text=True,
        env=dict(os.environ, HOME=str(home)),
    )


def test_shim_prefers_venv_when_present(tmp_path, repo_root):
    """With the delegate venv installed, the shim runs the venv's python3."""
    shim, home, marker, _gen = _sandbox(tmp_path, repo_root, with_venv=True)
    run = _run_shim(shim, home)
    assert run.returncode == 0, run.stderr
    assert marker.exists(), "the venv interpreter was not the one that ran"
    assert "adlc.py" in marker.read_text()
    assert "ADLC_MAIN ['doctor']" in run.stdout


def test_shim_falls_back_to_python3_when_venv_absent(tmp_path, repo_root):
    """Benign twin: no venv -> `python3` from $PATH, and adlc still runs."""
    shim, home, marker, _gen = _sandbox(tmp_path, repo_root, with_venv=False)
    run = _run_shim(shim, home)
    assert run.returncode == 0, run.stderr
    assert not marker.exists()
    assert "ADLC_MAIN ['doctor']" in run.stdout


def test_shim_expands_home_at_run_time_not_install_time(tmp_path, repo_root):
    """The venv path is `$HOME/...`, unexpanded, so the shim follows its runner.

    BR-3 allows no hardcoded user-specific absolute path beyond the derived
    $REPO_ROOT; a stamped-in home would also make the shim wrong for anyone but
    the installing user.
    """
    shim, home, _marker, _gen = _sandbox(tmp_path, repo_root, with_venv=True)
    text = shim.read_text()
    assert '_v="$HOME/.claude/delegate-venv/bin/python3"' in text
    assert str(home) not in text
    assert text.count("tools/adlc/adlc.py") == 2   # venv branch + fallback


def test_shim_write_is_idempotent(tmp_path, repo_root):
    """A second run reports `ok` and rewrites nothing (BR-1, LESSON-017).

    Idempotency is keyed on the shim's CONTENT, so the whole new text — venv
    branch included — has to match, and a machine carrying the old single-line
    shim is re-stamped rather than reported current.
    """
    _shim, _home, _marker, gen = _sandbox(tmp_path, repo_root, with_venv=True)
    first, second = gen.stdout.split("--- second run ---")
    assert "done: wrote" in first, gen.stdout
    assert "already current" in second and "done: wrote" not in second, gen.stdout


def test_dry_run_writes_no_shim(tmp_path, repo_root):
    """--dry-run plans the write and changes nothing (AC-7 of REQ-519)."""
    shim, _home, _marker, gen = _sandbox(tmp_path, repo_root, with_venv=True, dry=True)
    assert "would: write adlc shim" in gen.stdout
    assert "done: wrote" not in gen.stdout
    assert not shim.exists()
