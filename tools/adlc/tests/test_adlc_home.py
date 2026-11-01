"""REQ-654 BR-1/BR-2: one ADLC_HOME rule, three implementations, one vector.

The rule is written out three times (architecture ADR-2): ``partials/adlc-home.sh``
for shell, ``tools/adlc/adlc_home.py`` for the adlc tools, and
``tools/delegate/_machine_config.py::adlc_home`` for the self-contained delegation
tools. Three copies of a rule drift unless something drives them over the same
inputs, so this file does exactly that and fails on any disagreement — about
whether a value is accepted, what home it yields, or which config path follows.

It also pins AC-11's compatibility claim: a consumer whose vendored partial
predates REQ-654 resolves its counter exactly where the new resolver does under
the default home, so the stale copy keeps working until it is re-synced.
"""

import importlib.util
import os
import shutil
import subprocess

import pytest

import adlc_home

#: The toolkit tree these tests belong to, from this file's real location (not
#: ``conftest``: several suites run in one pytest process share that module name).
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))

PARTIAL = os.path.join(TOOLKIT, "partials", "adlc-home.sh")

#: This branch's base on main: the last commit whose partials predate REQ-654.
_PRE_REQ_654 = "3206532"


def _load_mirror():
    path = os.path.join(TOOLKIT, "tools", "delegate", "_machine_config.py")
    spec = importlib.util.spec_from_file_location("_machine_config_for_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIRROR = _load_mirror()

#: (label, ADLC_HOME or None for unset, ADLC_CONFIG or None for unset)
VECTOR = [
    ("unset", None, None),
    ("absolute", "/opt/adlc home", None),
    ("absolute-trailing-slash", "/opt/adlc/", None),
    ("filesystem-root", "/", None),
    ("double-slash", "//", None),
    ("empty", "", None),
    ("relative", "rel/home", None),
    ("dot-relative", "./rel", None),
    ("literal-tilde", "~/x", None),
    ("config-wins", "/opt/adlc", "/etc/adlc.yml"),
    ("config-with-invalid-home", "rel/home", "/etc/adlc.yml"),
    ("config-empty-is-unset", "/opt/adlc", ""),
]

#: REQ-663 BR-8. (label, pointer bytes, ADLC_HOME or None). ``{home}`` is a real directory
#: inside the sandbox, ``{other}`` another. Every row is driven through all three sites.
POINTER_VECTOR = [
    ("pointer", "{home}\n", None),
    ("pointer-no-newline", "{home}", None),
    ("pointer-trailing-slash", "{home}/\n", None),
    ("pointer-second-line-ignored", "{home}\nignored\n", None),
    ("pointer-env-agrees", "{home}\n", "{home}"),
    ("pointer-env-agrees-after-trim", "{home}\n", "{home}/"),
    ("pointer-env-conflict", "{home}\n", "{other}"),
    ("pointer-empty", "", None),
    ("pointer-relative", "rel/home\n", None),
    ("pointer-missing-dir", "{home}/gone\n", None),
    ("pointer-missing-dir-env-agrees", "{home}/gone\n", "{home}/gone"),
]

#: The rows that resolve, and what to. Everything else is an error at all three sites.
POINTER_RESOLVES = {"pointer", "pointer-no-newline", "pointer-trailing-slash",
                    "pointer-second-line-ignored", "pointer-env-agrees",
                    "pointer-env-agrees-after-trim"}


def _env(home_dir, value, config):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home_dir}
    if value is not None:
        env["ADLC_HOME"] = value
    if config is not None:
        env["ADLC_CONFIG"] = config
    return env


def _shell(env):
    script = ('. "%s"\n'
              'if h=$(adlc_home 2>/dev/null); then echo "home=$h"; else echo "home=ERR"; fi\n'
              'if c=$(adlc_machine_config 2>/dev/null); then echo "cfg=$c"; else echo "cfg=ERR"; fi\n'
              % PARTIAL)
    out = subprocess.run(["/bin/sh", "-c", script], env=env, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    vals = dict(line.split("=", 1) for line in out)
    return (None if vals["home"] == "ERR" else vals["home"],
            None if vals["cfg"] == "ERR" else vals["cfg"])


def _python(monkeypatch, env, home_fn, config_fn, error):
    for key in ("HOME", "ADLC_HOME", "ADLC_CONFIG"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if key != "PATH":
            monkeypatch.setenv(key, value)
    try:
        home = home_fn()
    except error:
        home = None
    try:
        cfg = config_fn()
    except error:
        cfg = None
    return home, cfg


@pytest.mark.parametrize("label,value,config", VECTOR, ids=[v[0] for v in VECTOR])
def test_parity_vector(tmp_path, monkeypatch, label, value, config):
    home_dir = str(tmp_path / "home dir")
    env = _env(home_dir, value, config)
    sh = _shell(env)
    py = _python(monkeypatch, env, adlc_home.adlc_home, adlc_home.machine_config_path,
                 adlc_home.AdlcHomeError)
    mirror = _python(monkeypatch, env, MIRROR.adlc_home, MIRROR.default_config_path,
                     MIRROR.AdlcHomeError)
    assert sh == py == mirror, (label, sh, py, mirror)


def test_parity_vector_expectations(tmp_path, monkeypatch):
    """The vector is only a specification if its answers are the rule's answers."""
    home_dir = str(tmp_path / "home dir")
    got = {}
    for label, value, config in VECTOR:
        got[label] = _shell(_env(home_dir, value, config))
    claude = os.path.join(home_dir, ".claude")
    assert got["unset"] == (claude, os.path.join(claude, "adlc", "config.yml"))
    assert got["absolute"] == ("/opt/adlc home", "/opt/adlc home/adlc/config.yml")
    assert got["absolute-trailing-slash"] == ("/opt/adlc", "/opt/adlc/adlc/config.yml")
    assert got["filesystem-root"] == ("/", "/adlc/config.yml")
    for bad in ("empty", "relative", "dot-relative", "literal-tilde"):
        assert got[bad] == (None, None), bad
    assert got["config-wins"] == ("/opt/adlc", "/etc/adlc.yml")
    assert got["config-with-invalid-home"] == (None, "/etc/adlc.yml")
    assert got["config-empty-is-unset"] == ("/opt/adlc", "/opt/adlc/adlc/config.yml")


@pytest.mark.parametrize("label,pointer,value", POINTER_VECTOR,
                         ids=[v[0] for v in POINTER_VECTOR])
def test_pointer_vector(tmp_path, monkeypatch, label, pointer, value):
    home_dir = tmp_path / "home dir"
    (home_dir / ".claude").mkdir(parents=True)
    target = tmp_path / "moved home"
    target.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    fill = {"home": str(target), "other": str(other)}
    (home_dir / ".claude" / ".adlc-home").write_text(pointer.format(**fill))
    env = _env(str(home_dir), value.format(**fill) if value else None, None)
    sh = _shell(env)
    py = _python(monkeypatch, env, adlc_home.adlc_home, adlc_home.machine_config_path,
                 adlc_home.AdlcHomeError)
    mirror = _python(monkeypatch, env, MIRROR.adlc_home, MIRROR.default_config_path,
                     MIRROR.AdlcHomeError)
    assert sh == py == mirror, (label, sh, py, mirror)
    if label in POINTER_RESOLVES:
        assert sh == (str(target), str(target / "adlc" / "config.yml")), label
    else:
        assert sh == (None, None), label


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_pointer_of_the_wrong_kind_is_refused_everywhere(tmp_path, monkeypatch, kind):
    """A pointer that is not a regular file refuses at all three sites (LESSON-014)."""
    home_dir = tmp_path / "h"
    (home_dir / ".claude").mkdir(parents=True)
    target = tmp_path / "moved"
    target.mkdir()
    real = tmp_path / "real-pointer"
    real.write_text(str(target) + "\n")
    path = home_dir / ".claude" / ".adlc-home"
    if kind == "symlink":
        path.symlink_to(real)
    else:
        path.mkdir()
    env = _env(str(home_dir), None, None)
    sh = _shell(env)
    py = _python(monkeypatch, env, adlc_home.adlc_home, adlc_home.machine_config_path,
                 adlc_home.AdlcHomeError)
    mirror = _python(monkeypatch, env, MIRROR.adlc_home, MIRROR.default_config_path,
                     MIRROR.AdlcHomeError)
    assert sh == py == mirror == (None, None)


def test_no_pointer_is_rule_a(tmp_path, monkeypatch):
    """With neither a pointer nor the variable, the answer is the literal default."""
    home_dir = tmp_path / "h"
    (home_dir / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_dir))
    assert adlc_home.adlc_home() == str(home_dir / ".claude")
    assert adlc_home.adlc_home_source() == "default"


def test_pointer_error_tells_a_pointer_from_a_bad_variable(tmp_path, monkeypatch):
    home_dir = tmp_path / "h"
    (home_dir / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("ADLC_HOME", "rel")
    assert adlc_home.validate() and not adlc_home.pointer_error()
    monkeypatch.delenv("ADLC_HOME")
    (home_dir / ".claude" / ".adlc-home").write_text(str(tmp_path / "gone") + "\n")
    assert adlc_home.pointer_error() and "does not exist" in adlc_home.pointer_error()


def test_source_says_pointer(tmp_path, monkeypatch):
    home_dir = tmp_path / "h"
    (home_dir / ".claude").mkdir(parents=True)
    target = tmp_path / "moved"
    target.mkdir()
    (home_dir / ".claude" / ".adlc-home").write_text(str(target) + "\n")
    monkeypatch.setenv("HOME", str(home_dir))
    assert adlc_home.adlc_home_source() == "pointer"
    script = '. "%s"; adlc_home_source' % PARTIAL
    out = subprocess.run(["/bin/sh", "-c", script], env={"HOME": str(home_dir),
                                                         "PATH": "/usr/bin:/bin"},
                         capture_output=True, text=True)
    assert out.stdout.strip() == "pointer"


@pytest.mark.parametrize("bad", ["", "rel/home"])
def test_rejects_invalid_home(monkeypatch, bad):
    monkeypatch.setenv("ADLC_HOME", bad)
    with pytest.raises(adlc_home.AdlcHomeError, match="ADLC_HOME"):
        adlc_home.adlc_home()
    assert "ADLC_HOME" in adlc_home.validate()


def test_validate_is_none_for_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert adlc_home.validate() is None
    assert adlc_home.adlc_home_source() == "default"
    monkeypatch.setenv("ADLC_HOME", str(tmp_path / "x"))
    assert adlc_home.adlc_home_source() == "env"


def _pre_req_partial(name):
    if not os.path.isdir(os.path.join(TOOLKIT, ".git")) and not os.path.isfile(
            os.path.join(TOOLKIT, ".git")):
        pytest.skip("no git checkout: the pre-REQ-654 partial cannot be read")
    out = subprocess.run(["git", "-C", TOOLKIT, "show", "%s:partials/%s" % (_PRE_REQ_654, name)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("commit %s is not in this clone (shallow?)" % _PRE_REQ_654)
    return out.stdout


@pytest.mark.parametrize("shell", ["/bin/sh", "zsh"])
def test_stale_vendored_partial_still_works(tmp_path, shell):
    """AC-11: a consumer still carrying the pre-REQ-654 ``id-alloc.sh`` sources it
    through a skill fence and gets the counter the new resolver names under the
    default home. That is what makes the stale copy safe until it is re-synced."""
    if shutil.which(shell) is None:
        pytest.skip("%s not installed" % shell)
    old = _pre_req_partial("id-alloc.sh")
    assert "adlc_home" not in old, "the pinned commit already has the REQ-654 resolver"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    os.symlink(TOOLKIT, str(home / ".claude" / "skills"))
    consumer = tmp_path / "consumer"
    (consumer / ".adlc" / "partials").mkdir(parents=True)
    (consumer / ".adlc" / "partials" / "id-alloc.sh").write_text(old)
    root_line = next(
        line for line in open(os.path.join(TOOLKIT, ".adlc", "context", "conventions.md"),
                              encoding="utf-8")
        if line.startswith("ADLC_TOOLKIT_ROOT=")).rstrip("\n")
    fence = "\n".join([
        root_line,
        'if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; '
        'else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi',
        'adlc_id_kind_counter req',
        'adlc_id_own_ledger',
        'echo completed',
    ])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    stale = subprocess.run([shell, "-c", fence], cwd=str(consumer), env=env,
                           capture_output=True, text=True)
    assert stale.returncode == 0, stale.stderr
    lines = stale.stdout.splitlines()
    assert lines[-1] == "completed"
    new = subprocess.run(
        ["/bin/sh", "-c", '. "%s"; h=$(adlc_home) && echo "$h/.global-next-req" && '
         'echo "$h/.adlc-own-reservations"' % PARTIAL],
        env=env, capture_output=True, text=True, check=True).stdout.splitlines()
    assert lines[:2] == new
