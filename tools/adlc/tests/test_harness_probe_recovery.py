"""REQ-664 BR-4, BR-11 / AC-4: user-level files, the recovery marker, `--recover`.

The trust entry (codex, gemini) and gemini's policy file are the only user-level
files a run edits. Each is backed up and covered by a marker before the edit,
restored byte for byte on every exit path, and the marker survives only a run
that died before restoring.
"""

import hashlib
import json
import os
import re
import signal
import time

import pytest

from probe_helpers import Sandbox, statuses

USER_CONFIG = "model = \"some-model\"\n[projects.\"/elsewhere\"]\ntrust_level = \"trusted\"\n"


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _codex_config(sb):
    return os.path.join(sb.home, ".codex", "config.toml")


def _gemini_trust(sb):
    return os.path.join(sb.home, ".gemini", "trustedFolders.json")


def _wait(predicate, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _kill_fakes(sb):
    if os.path.exists(sb.pidfile):
        for pid in open(sb.pidfile).read().split():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass


def test_trust_file_backup_and_restore(tmp_path):
    """codex: the entry covers exactly repo and wt by realpath, the file is
    byte-identical afterwards; absent beforehand, it is deleted afterwards."""
    sb = Sandbox(tmp_path / "present")
    with open(_codex_config(sb), "w") as fh:
        fh.write(USER_CONFIG)
    before = _sha(_codex_config(sb))
    out = sb.run("codex", "--only", "shell-timeout")
    assert out.returncode == 0, out.stderr[-2000:]
    assert _sha(_codex_config(sb)) == before
    seen = [r["trust_file"] for r in sb.log_records("config")]
    assert seen and all(t.startswith(USER_CONFIG) for t in seen)   # backup before the entry
    tables = re.findall(r'\[projects\."([^"]+)"\]', seen[0][len(USER_CONFIG):])
    assert len(tables) == 2
    assert tables[0].endswith("/repo") and tables[1].endswith("/wt")
    assert all(t == os.path.realpath(t) for t in tables)
    assert os.path.dirname(tables[0]) == os.path.dirname(tables[1])
    assert os.path.realpath(os.path.dirname(tables[0])).startswith(os.path.realpath(sb.tmp))
    sb = Sandbox(tmp_path / "absent")
    out = sb.run("codex", "--only", "shell-timeout")
    assert out.returncode == 0, out.stderr[-2000:]
    assert not os.path.exists(_codex_config(sb))
    assert "sha256=absent" in out.stderr


def test_gemini_policy_file_lifecycle(tmp_path):
    """The policy file is written at run start beside the trust entry, under one
    marker, and deleted afterwards with the policies directory the run created."""
    sb = Sandbox(tmp_path)
    out = sb.run("gemini", "--only", "ask-tier-deny")
    assert out.returncode == 0, out.stderr[-2000:]
    configs = sb.log_records("config")
    assert configs[0]["policies"]                      # present from the first launch
    assert "trust-then-headless" not in configs[0]["prompt"]
    assert not os.path.exists(os.path.join(sb.home, ".gemini", "policies"))
    assert not os.path.exists(_gemini_trust(sb))
    assert os.listdir(os.path.join(sb.home, ".gemini")) == ["tmp"]   # session records only
    assert out.stderr.count("user_file_backed_up") == 2
    assert out.stderr.count("marker_cleared") == 1


def test_surgical_restore_when_the_user_file_changes(tmp_path):
    sb = Sandbox(tmp_path / "codex", flags=("mutate-trust-file",))
    with open(_codex_config(sb), "w") as fh:
        fh.write(USER_CONFIG)
    out = sb.run("codex", "--only", "shell-timeout")
    assert out.returncode == 1
    assert sb.result("codex")["cleanup"]["user_files_restored"] == "surgical"
    text = open(_codex_config(sb)).read()
    assert "a change the user made during the run" in text
    assert "adlc harness probe" not in text and text.startswith(USER_CONFIG)
    state = os.path.join(sb.adlc_home, "adlc", "harness-probe")
    kept = [n for n in os.listdir(state) if n.endswith(".pre-surgery")]
    assert len(kept) == 1
    assert not os.path.exists(sb.marker("codex"))
    assert "--recover" in out.stderr or "CLEANUP INCOMPLETE" in out.stderr
    sb = Sandbox(tmp_path / "gemini", flags=("mutate-policy-file",))
    out = sb.run("gemini", "--only", "ask-tier-deny")
    assert out.returncode == 1
    assert sb.result("gemini")["cleanup"]["user_files_restored"] == "surgical"
    assert not os.path.exists(os.path.join(sb.home, ".gemini", "policies"))
    state = os.path.join(sb.adlc_home, "adlc", "harness-probe")
    assert any(n.startswith("gemini-adlc-probe-") and n.endswith(".pre-surgery")
               for n in os.listdir(state))


def _crash_mid_run(sb, harness, sig):
    """Start a hanging run, wait for the edit, then signal the probe."""
    proc = sb.popen(harness)
    marker = sb.marker(harness)
    edited = (lambda: os.path.exists(_codex_config(sb)) and "adlc harness probe"
              in open(_codex_config(sb)).read()) if harness == "codex" else \
        (lambda: os.path.exists(_gemini_trust(sb)))
    try:
        assert _wait(lambda: os.path.exists(marker) and edited() and os.path.exists(
            sb.pidfile)), "the run never reached its first launch"
        os.kill(proc.pid, sig)
        proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
        _kill_fakes(sb)
    return proc


def test_marker_refuses_then_recover(tmp_path):
    sb = Sandbox(tmp_path, scenario="hang")
    with open(_codex_config(sb), "w") as fh:
        fh.write(USER_CONFIG)
    original = _sha(_codex_config(sb))
    _crash_mid_run(sb, "codex", signal.SIGKILL)
    marker = json.load(open(sb.marker("codex")))
    assert [f["path"] for f in marker["files"]] == [_codex_config(sb)]
    assert marker["files"][0]["post_edit_sha256"] == _sha(_codex_config(sb))
    assert marker["outside_dirs"] and os.path.isdir(marker["outside_dirs"][0])
    sb.scenario = "perform"
    out = sb.run("codex")
    assert out.returncode == 1
    assert "codex.marker.json" in out.stderr and "adlc harness probe codex --recover" in out.stderr
    sb.uninstall("codex")
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    out = sb.run("codex", "--recover", cwd=str(nowhere))
    assert out.returncode == 0, out.stderr
    assert _sha(_codex_config(sb)) == original
    assert not os.path.exists(sb.marker("codex"))
    assert not os.path.exists(marker["outside_dirs"][0])
    assert not os.path.exists(marker["run_dir"])
    sb.install("codex")
    out = sb.run("codex", "--only", "shell-timeout")
    assert out.returncode == 0, out.stderr[-2000:]


def test_catchable_signal_restores_and_leaves_no_marker(tmp_path):
    sb = Sandbox(tmp_path, scenario="hang")
    with open(_codex_config(sb), "w") as fh:
        fh.write(USER_CONFIG)
    original = _sha(_codex_config(sb))
    proc = _crash_mid_run(sb, "codex", signal.SIGTERM)
    assert proc.returncode == 1
    assert _sha(_codex_config(sb)) == original
    assert not os.path.exists(sb.marker("codex"))
    assert os.listdir(sb.tmp) == []
    assert not os.path.exists(sb.result_path("codex"))


def test_recover_gemini_created_dirs_and_nonempty_dir(tmp_path):
    """The marker covers both gemini files and lists the created policies dir;
    --recover deletes the policy file and rmdirs the dir only when it is empty."""
    sb = Sandbox(tmp_path, scenario="hang")
    _crash_mid_run(sb, "gemini", signal.SIGKILL)
    marker = json.load(open(sb.marker("gemini")))
    assert [f["kind"] for f in marker["files"]] == ["trust-entry", "policy-file"]
    assert all(f["backup_sha256"] == "absent" for f in marker["files"])
    policies = os.path.join(sb.home, ".gemini", "policies")
    assert marker["created_dirs"] == [policies]
    with open(os.path.join(policies, "users-own.toml"), "w") as fh:
        fh.write("# not the probe's\n")
    out = sb.run("gemini", "--recover", cwd=str(tmp_path))
    assert out.returncode == 1
    assert "policies" in out.stderr
    assert os.listdir(policies) == ["users-own.toml"]
    assert not os.path.exists(_gemini_trust(sb))


def test_noop_restore_when_the_edit_never_landed(tmp_path):
    """A crash between the marker and the edit: the file equals its backup."""
    sb = Sandbox(tmp_path)
    with open(_codex_config(sb), "w") as fh:
        fh.write(USER_CONFIG)
    state = os.path.join(sb.adlc_home, "adlc", "harness-probe")
    os.makedirs(state)
    marker = {"schema": 1, "harness": "codex", "run_id": "codex-x", "run_dir": "",
              "temp_root": "", "state_root": state, "created_dirs": [], "marker_dirs": [],
              "outside_dirs": [], "files": [{
                  "path": _codex_config(sb), "kind": "trust-entry", "flavor": "codex-toml",
                  "backup": os.path.join(str(tmp_path), "gone"),
                  "backup_sha256": _sha(_codex_config(sb)), "post_edit_sha256": None,
                  "added": {"text": "x"}}]}
    with open(sb.marker("codex"), "w") as fh:
        json.dump(marker, fh)
    out = sb.run("codex", "--recover", cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert open(_codex_config(sb)).read() == USER_CONFIG
    assert not os.path.exists(sb.marker("codex"))


def test_symlinked_user_file_stays_a_symlink(tmp_path):
    sb = Sandbox(tmp_path)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "codex-config.toml"
    target.write_text(USER_CONFIG)
    os.symlink(str(target), _codex_config(sb))
    before = _sha(str(target))
    out = sb.run("codex", "--only", "shell-timeout")
    assert out.returncode == 0, out.stderr[-2000:]
    assert os.path.islink(_codex_config(sb))
    assert os.path.realpath(_codex_config(sb)) == os.path.realpath(str(target))
    assert _sha(str(target)) == before


@pytest.mark.parametrize("field,value", [
    ("files", [{"path": "/etc/hosts", "kind": "trust-entry", "flavor": "codex-toml",
                "backup": "x", "backup_sha256": "absent", "post_edit_sha256": None,
                "added": {}}]),
    ("outside_dirs", ["/tmp/outside-codex-x"]),
    ("created_dirs", ["/usr"]),
    ("run_dir", "/tmp/not-a-probe-dir"),
])
def test_recover_refuses_a_marker_naming_foreign_paths(tmp_path, field, value):
    """--recover deletes what a marker names, so it acts only on what a run on that
    harness can create (BR-4)."""
    sb = Sandbox(tmp_path)
    state = os.path.join(sb.adlc_home, "adlc", "harness-probe")
    os.makedirs(state)
    marker = {"schema": 1, "harness": "codex", "run_id": "codex-x", "run_dir": "",
              "temp_root": "", "state_root": state, "created_dirs": [], "marker_dirs": [],
              "outside_dirs": [], "files": []}
    marker[field] = value
    with open(sb.marker("codex"), "w") as fh:
        json.dump(marker, fh)
    out = sb.run("codex", "--recover", cwd=str(tmp_path))
    assert out.returncode == 1 and "refusing to act on the recovery marker" in out.stderr
    assert os.path.exists(sb.marker("codex"))
