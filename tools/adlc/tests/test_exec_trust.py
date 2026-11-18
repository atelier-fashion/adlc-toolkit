"""REQ-662 BR-5, ADR-5: the per-run trust grant — additive, surgical, serialized.

Every case runs under conftest's sandbox ``HOME``; the user config is the one the real
adapter names (``paths.config.user``), so the file under test is the file the harness
reads (LESSON-777), never the operator's own. No credential file is read.
"""

import json
import os
import re
import stat
import subprocess
import sys

import pytest

import adlc_home
import exec_trust as et
import harness_adapter as ha
import harness_probe as hp
import toml_merge as tm
from conftest import TOOLKIT

ADLC_DIR = os.path.join(TOOLKIT, "tools", "adlc")
M = et.USER_CONFIG_ENTRY

HOOK_TABLE = ('[hooks.state."/srv/other/hooks.json:session_start:0"]\n'
              'trusted_hash = "sha256:%s"\n' % ("0" * 64))
FIXTURE = ('# the operator\'s own config\n'
           'model = "some-model"\n'
           'approval_policy = "on-request"\n'
           '\n'
           '[tui]\n'
           'theme = "dark"   # a trailing comment\n'
           '\n'
           '[projects."/srv/other"]\n'
           'trust_level = "trusted"\n'
           '\n' + HOOK_TABLE)


@pytest.fixture
def adapter():
    return ha.load_adapter(os.path.join(TOOLKIT, "harness", "codex.yml"))


@pytest.fixture
def env(tmp_path, monkeypatch, adapter):
    """The adapter's user config under the sandbox HOME, a working-copy root holding
    a working copy, and the probe marker path under a sandbox ADLC_HOME."""
    monkeypatch.setenv("ADLC_HOME", str(tmp_path / "adlc-home"))
    root = tmp_path / "primary" / ".worktrees"
    wc = root / "REQ-001"
    wc.mkdir(parents=True)
    config = et.user_config_path(adapter)
    assert config.startswith(os.environ["HOME"] + os.sep)
    marker = et.probe_marker(adlc_home.adlc_home(), adapter["name"])

    class Env(object):
        pass

    e = Env()
    e.root, e.wc, e.config, e.marker = str(root), str(wc), config, marker
    e.real_wc = os.path.realpath(str(wc))
    e.lock = config + et.LOCK_SUFFIX
    return e


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


def read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def grant(e, path=None, **kw):
    return et.grant(M, e.config, path or e.wc, e.root, e.marker, **kw)


# --------------------------------------------------------------------------- BR-5, AC-5
def test_grant_is_additive_and_revoke_is_surgical(env):
    put(env.config, FIXTURE)
    os.chmod(env.config, 0o644)
    g = grant(env)
    after = read(env.config)
    # Exactly one block, appended; every byte of the original unchanged.
    assert after == FIXTURE + et.trust_block(env.real_wc)
    assert after.count("[projects.") == FIXTURE.count("[projects.") + 1
    found = tm.scan(after)
    assert found.headers == tm.scan(FIXTURE).headers + ["projects." + env.real_wc]
    keys = found.table_keys["projects." + env.real_wc]
    assert list(keys) == ["trust_level"] and keys["trust_level"][0] == '"trusted"'
    assert (g.path, g.pre_existing, g.adopted, g.created, g.newline_added) == (
        env.real_wc, False, False, False, False)
    assert g.written and g.granted_at
    assert not os.path.lexists(env.lock), "the lock is released"
    # Surgical: the original bytes come back, and so does the mode.
    r = et.revoke(g)
    assert (r.status, r.warning) == (et.REVOKED, "") and r.revoked_at
    assert read(env.config) == FIXTURE
    assert stat.S_IMODE(os.stat(env.config).st_mode) == 0o644
    assert not os.path.lexists(env.lock)


def test_a_file_with_no_final_newline_gets_its_bytes_back(env):
    text = FIXTURE.rstrip("\n")
    put(env.config, text)
    g = grant(env)
    assert g.newline_added
    assert read(env.config) == text + "\n" + et.trust_block(env.real_wc)
    et.revoke(g)
    assert read(env.config) == text


def test_an_absent_config_is_created_and_revoke_removes_it(env):
    assert not os.path.lexists(env.config)
    g = grant(env)
    assert g.created and read(env.config) == et.trust_block(env.real_wc)
    assert et.revoke(g).status == et.REVOKED
    assert not os.path.lexists(env.config)


# --------------------------------------------------------------------------- pre_existing
@pytest.mark.parametrize("entry", [
    '[projects."{p}"]\ntrust_level = "trusted"\n',
    '[projects]\n"{p}".trust_level = "trusted"\n',
])
def test_pre_existing_is_reported_and_survives_revoke(env, entry):
    text = FIXTURE + "\n" + entry.format(p=env.real_wc)
    put(env.config, text)
    g = grant(env)
    assert g.pre_existing and not g.adopted and not g.written
    assert read(env.config) == text, "a pre-existing entry is not written again"
    assert et.revoke(g).status == et.PRE_EXISTING
    assert read(env.config) == text, "and survives revoke"


@pytest.mark.parametrize("entry", [
    '[projects."{p}"]\ntrust_level = "untrusted"\n',
    '[projects."{p}"]\nnote = "the operator\'s"\n',
])
def test_an_operator_entry_that_does_not_trust_is_left_and_refused(env, entry):
    text = FIXTURE + "\n" + entry.format(p=env.real_wc)
    put(env.config, text)
    with pytest.raises(et.TrustRefused, match="does not edit an operator's entry"):
        grant(env)
    assert read(env.config) == text


# --------------------------------------------------------------------------- crash path
def test_revoke_after_a_kill_is_idempotent(env):
    put(env.config, FIXTURE)
    g = grant(env)
    # The engine is killed; the next process reads the grant back from its run record.
    record = json.loads(json.dumps(g.to_doc()))
    back = et.Grant.from_doc(record)
    assert back.to_doc() == g.to_doc()
    assert et.revoke(back).status == et.REVOKED
    assert read(env.config) == FIXTURE
    again = et.revoke(back)
    assert again.status == et.GONE and "already gone" in again.warning
    assert read(env.config) == FIXTURE


def test_a_kill_before_the_record_is_written_is_still_revocable(env):
    put(env.config, FIXTURE)
    grant(env)
    # No record survived: a grant built from the path alone finds the same block.
    rebuilt = et.Grant(M, env.config, env.real_wc, marker=env.marker)
    assert et.revoke(rebuilt).status == et.REVOKED
    assert read(env.config) == FIXTURE


def test_a_killed_runs_block_is_adopted_and_removed(env):
    put(env.config, FIXTURE + et.trust_block(env.real_wc))   # left by a killed run
    g = grant(env)
    assert g.adopted and not g.pre_existing and g.written
    assert read(env.config) == FIXTURE + et.trust_block(env.real_wc)
    assert et.revoke(g).status == et.REVOKED
    assert read(env.config) == FIXTURE


@pytest.mark.parametrize("change", [
    lambda d: {k: v for k, v in d.items() if k != "created"},
    lambda d: dict(d, created="no"),
    lambda d: dict(d, path='/srv/a"b'),
    lambda d: dict(d, config="relative/config.toml"),
])
def test_a_grant_record_is_checked_when_read_back(env, change):
    put(env.config, FIXTURE)
    doc = grant(env).to_doc()
    with pytest.raises(et.TrustRefused):
        et.Grant.from_doc(change(doc))


# --------------------------------------------------------------------------- the operator's edits
def test_revoke_keeps_the_operators_edits(env):
    put(env.config, FIXTURE)
    g = grant(env)
    edited = read(env.config).replace('theme = "dark"', 'theme = "light"')
    put(env.config, edited + '\n[later]\nadded = "by the operator"\n')
    assert et.revoke(g).status == et.REVOKED
    assert read(env.config) == (FIXTURE.replace('theme = "dark"', 'theme = "light"')
                                + '\n[later]\nadded = "by the operator"\n')


def test_a_key_added_to_the_blocks_table_is_left_with_a_warning(env):
    put(env.config, FIXTURE)
    g = grant(env)
    # Below the block's blank line, but still inside its table: removing the header
    # would move the key into the table above.
    text = read(env.config) + 'model_override = "x"\n'
    put(env.config, text)
    r = et.revoke(g)
    assert r.status == et.EDITED
    assert '[projects."%s"]' % env.real_wc in r.warning and "by hand" in r.warning
    assert read(env.config) == text


def test_a_block_the_operator_removed_is_a_warning(env):
    put(env.config, FIXTURE)
    g = grant(env)
    put(env.config, FIXTURE)
    r = et.revoke(g)
    assert r.status == et.GONE and r.warning
    assert read(env.config) == FIXTURE


# --------------------------------------------------------------------------- AC-15: the lock
_WORKER = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import exec_trust as et
config, path, root, marker, rounds = sys.argv[2:7]
for _ in range(int(rounds)):
    g = et.grant(et.USER_CONFIG_ENTRY, config, path, root, marker)
    with open(config, encoding="utf-8") as fh:
        assert et.trust_block(g.path) in fh.read()
    r = et.revoke(g)
    assert r.status == et.REVOKED, (r.status, r.warning)
print(json.dumps(et.grant(et.USER_CONFIG_ENTRY, config, path, root, marker).to_doc()))
"""


def test_trust_file_writes_are_serialized(env):
    """Two processes, each grant-and-revoke in a loop on one file: neither loses the
    other's block, and both revoke to the original bytes."""
    put(env.config, FIXTURE)
    other = os.path.join(env.root, "REQ-002")
    os.mkdir(other)
    procs = [subprocess.Popen([sys.executable, "-c", _WORKER, ADLC_DIR, env.config, wc,
                               env.root, env.marker, "25"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
             for wc in (env.wc, other)]
    docs = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        docs.append(json.loads(out))
    text = read(env.config)
    blocks = [et.trust_block(d["path"]) for d in docs]
    assert [text.count(b) for b in blocks] == [1, 1]
    rest = text
    for b in blocks:
        rest = rest.replace(b, "")
    assert rest == FIXTURE
    assert not os.path.lexists(env.lock)
    for d in docs:
        assert et.revoke(et.Grant.from_doc(d)).status == et.REVOKED
    assert read(env.config) == FIXTURE


def test_a_held_lock_refuses_and_writes_nothing(env):
    put(env.config, FIXTURE)
    os.mkdir(env.lock)
    try:
        with pytest.raises(et.TrustRefused, match=re.escape(env.lock)):
            grant(env, timeout=0.2)
        assert read(env.config) == FIXTURE
    finally:
        os.rmdir(env.lock)
    assert grant(env).written, "once released, the grant goes on"


def test_a_symlinked_lock_is_refused(env, tmp_path):
    put(env.config, FIXTURE)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(str(elsewhere), env.lock)
    with pytest.raises(et.TrustRefused, match="symlink"):
        grant(env)
    assert read(env.config) == FIXTURE
    assert os.path.islink(env.lock) and elsewhere.is_dir()


# --------------------------------------------------------------------------- BR-5: the probe's marker
def test_recovery_marker_refuses_and_its_absence_does_not(env, adapter):
    put(env.marker, "{}\n")
    for call in (lambda: et.preflight(M, env.config, env.marker), lambda: grant(env)):
        with pytest.raises(et.TrustRefused) as info:
            call()
        assert env.marker in str(info.value)
        assert "adlc harness probe %s --recover" % adapter["name"] in str(info.value)
    assert not os.path.lexists(os.path.dirname(env.config)), "nothing was written"
    # The must-not-refuse case: no marker, so pre-flight passes and the grant writes.
    os.remove(env.marker)
    assert et.preflight(M, env.config, env.marker) is None
    assert grant(env).written
    # Another harness's marker is another probe's file, not this one's.
    other = et.probe_marker(adlc_home.adlc_home(), "another-harness")
    put(other, "{}\n")
    assert et.preflight(M, env.config, env.marker) is None


def test_a_marker_that_appears_mid_run_is_named_at_revoke(env):
    put(env.config, FIXTURE)
    g = grant(env)
    put(env.marker, "{}\n")
    r = et.revoke(g)
    assert r.status == et.REVOKED and env.marker in r.warning
    assert read(env.config) == FIXTURE


# --------------------------------------------------------------------------- refused paths
def _shapes(e, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = os.path.join(e.root, "escape")
    os.symlink(str(outside), escape)
    quoted = os.path.join(e.root, 'a"b')
    os.mkdir(quoted)
    to_quoted = os.path.join(e.root, "to-quoted")
    os.symlink(quoted, to_quoted)
    return {
        "relative": "primary/.worktrees/REQ-001",
        "empty": "",
        "none": None,
        "quote": quoted,
        "backslash": os.path.join(e.root, "a\\b"),
        "newline": os.path.join(e.root, "a\nb"),
        "symlink-escapes-root": escape,
        "symlink-to-a-quote": to_quoted,
        "missing": os.path.join(e.root, "REQ-404"),
        "dotdot-escapes-root": os.path.join(e.root, "..", ".."),
    }


@pytest.mark.parametrize("shape", ["relative", "empty", "none", "quote", "backslash",
                                   "newline", "symlink-escapes-root", "symlink-to-a-quote",
                                   "missing", "dotdot-escapes-root"])
@pytest.mark.parametrize("config_exists", [True, False])
def test_refused_path_shapes_write_nothing(env, tmp_path, shape, config_exists):
    path = _shapes(env, tmp_path)[shape]
    if config_exists:
        put(env.config, FIXTURE)
    with pytest.raises(et.TrustRefused):
        et.grant(M, env.config, path, env.root, env.marker)
    if config_exists:
        assert read(env.config) == FIXTURE
        assert not os.path.lexists(env.lock)
    else:
        assert not os.path.lexists(os.path.dirname(env.config)), "not even its directory"


@pytest.mark.parametrize("root,why", [("", "is empty"), ("relative/root", "is relative"),
                                      ("/", "is the filesystem root")])
def test_a_bad_working_copy_root_is_refused(env, root, why):
    with pytest.raises(et.TrustRefused, match=why):
        et.grant(M, env.config, env.wc, root, env.marker)
    assert not os.path.lexists(os.path.dirname(env.config))


def test_a_symlink_inside_the_root_is_trusted_at_its_resolved_path(env):
    link = os.path.join(env.root, "link")
    os.symlink(env.wc, link)
    g = grant(env, path=link)
    assert g.path == env.real_wc
    assert read(env.config) == et.trust_block(env.real_wc)


# --------------------------------------------------------------------------- AC-25
def test_no_write_touches_hook_review_state(env):
    """The hook-review table is the file's last, so the block lands right after it."""
    put(env.config, FIXTURE)
    assert FIXTURE.endswith(HOOK_TABLE)
    name = "hooks.state./srv/other/hooks.json:session_start:0"
    before = tm.scan(FIXTURE).table_keys[name]
    g = grant(env)
    after = read(env.config)
    assert after[:len(FIXTURE)] == FIXTURE and HOOK_TABLE in after
    assert tm.scan(after).table_keys[name] == before
    et.revoke(g)
    assert read(env.config) == FIXTURE


# --------------------------------------------------------------------------- held equal to the probe
def test_spelling_equals_the_probes_trust_edit(env):
    edit = hp.codex_trust_edit(os.environ["HOME"], "run-1", [env.real_wc])
    probe = edit.added["text"]
    assert et.trust_table(env.real_wc) in probe

    def uncommented(text):
        return [ln for ln in text.split("\n") if not ln.startswith("#")]

    assert uncommented(probe) == uncommented(et.trust_block(env.real_wc))
    # Both append to the end of the file the adapter names.
    assert edit.path == env.config
    assert edit.build(FIXTURE.encode("utf-8")).decode("utf-8") == FIXTURE + probe
    put(env.config, FIXTURE)
    grant(env)
    assert read(env.config) == FIXTURE + et.trust_block(env.real_wc)


def test_marker_location_equals_the_probes(env):
    assert et.PROBE_STATE_SUBDIR == hp.STATE_SUBDIR
    home = adlc_home.adlc_home()
    for name in ("one", "another-harness"):
        assert et.probe_marker(home, name) == hp.marker_path(home, name)


# --------------------------------------------------------------------------- mechanisms, pre-flight
@pytest.mark.parametrize("mechanism", ["none", "flag"])
def test_a_mechanism_with_no_file_writes_nothing(env, mechanism):
    g = et.grant(mechanism, None, env.wc, env.root, env.marker)
    assert g.config is None and not g.written and g.path == env.real_wc
    assert et.revoke(g).status == et.NO_FILE_STATUS
    assert et.preflight(mechanism, None, env.marker) is None
    assert not os.path.lexists(os.path.dirname(env.config))


@pytest.mark.parametrize("mechanism", ["trusted-folders-file", "bogus"])
def test_a_mechanism_with_no_arm_is_refused(env, mechanism):
    with pytest.raises(et.TrustRefused, match="no engine arm"):
        et.grant(mechanism, env.config, env.wc, env.root, env.marker)
    with pytest.raises(et.TrustRefused, match="no engine arm"):
        et.preflight(mechanism, env.config, env.marker)
    assert not os.path.lexists(os.path.dirname(env.config))


def test_preflight_refuses_a_file_the_grant_could_not_edit(env, tmp_path):
    put(env.config, 'x = """\nmulti\n"""\n')
    with pytest.raises(et.TrustRefused, match="multi-line string"):
        et.preflight(M, env.config, env.marker)
    with pytest.raises(et.TrustRefused, match="multi-line string"):
        grant(env)
    assert read(env.config) == 'x = """\nmulti\n"""\n'
    os.remove(env.config)
    target = tmp_path / "dotfiles-config.toml"
    target.write_text(FIXTURE)
    os.symlink(str(target), env.config)
    with pytest.raises(et.TrustRefused, match="symlink"):
        et.preflight(M, env.config, env.marker)
    with pytest.raises(et.TrustRefused, match="symlink"):
        grant(env)
    assert target.read_text() == FIXTURE and os.path.islink(env.config)
    # The benign case: a classifiable file, and an absent one, pass.
    os.remove(env.config)
    assert et.preflight(M, env.config, env.marker) is None
    put(env.config, FIXTURE)
    assert et.preflight(M, env.config, env.marker) is None
    assert read(env.config) == FIXTURE


def test_the_user_config_comes_from_the_adapter(env, adapter):
    assert env.config == os.path.join(os.environ["HOME"], ".codex", "config.toml")
    fake = {"name": "test-only", "paths": {"config": {"user": "$HOME/elsewhere/c.toml"}}}
    assert et.user_config_path(fake) == os.path.join(os.environ["HOME"], "elsewhere", "c.toml")
    with pytest.raises(et.TrustRefused, match="paths.config.user"):
        et.user_config_path({"name": "test-only", "paths": {}})


def test_the_module_names_no_harness():
    with open(os.path.join(ADLC_DIR, "exec_trust.py"), encoding="utf-8") as fh:
        source = fh.read()
    assert not re.search(r"(?i)claude|codex|gemini|copilot|cursor|antigravity|\bagy\b",
                         source)
    assert not re.search(r"~/\.codex|\.codex/|~/\.agents", source)
