"""The doctor on both install routes (REQ-669 TASK-128: ADR-7, BR-3, BR-7, BR-11, AC-1, AC-4).

Three sandbox machine shapes, each on a sandbox HOME and never the real one:

- **symlink-only**: ``~/.claude/skills`` and ``~/.claude/agents`` link a clone;
- **plugin-only**: a copy under ``~/.claude/plugins/cache/adlc-toolkit/adlc/<v>/``
  recorded in ``installed_plugins.json``, as Claude Code 2.1.258 lays it out
  (verification.md rows 11 to 13), with the pointer the SessionStart hook writes;
- **doubled**: both.

In-process cases reach the sandbox through the ``expanduser`` pattern of
test_checks.py. Child-process cases get a scrubbed environment whose ``HOME`` is
the sandbox. Every detector has must-not-fire twins on the other shapes
(LESSON-440), and every signal the doctor cannot read is a FAIL, never a PASS
(LESSON-581).
"""

import ast
import glob
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import sysconfig
import types

import pytest

import checks
import doctor
from doctor import CheckOutcome, Profile, Result

_q = shlex.quote

_TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))
with open(os.path.join(_TOOLKIT, "VERSION"), encoding="utf-8") as _fh:
    _VERSION = _fh.read().strip()

with open(os.path.join(_TOOLKIT, "tools", "delegate", "requirements.txt"),
          encoding="utf-8") as _fh:
    #: The pinned PyYAML requirement the plugin-route fix must name.
    _PYYAML_PIN = [ln.strip() for ln in _fh if ln.lower().startswith("pyyaml")][0]

#: The four checks of the install.sh symlink install (ADR-7).
_SYMLINK_CHECKS = ("skills-symlink", "agents-symlink", "toolkit-clean", "path-shims")

#: What a toolkit copy needs for every doctor check to run from it.
_COPY = (".claude-plugin/*.json", "hooks/hooks.json", "scripts/*", "VERSION",
         "spec/SKILL.md", "partials/*.sh", "tools/adlc/*.py", "tools/delegate/*.py",
         "tools/delegate/requirements.txt", "agents/*.md")


# --- sandbox builders --------------------------------------------------------

def _copy_toolkit(dest):
    """Copy the files ``_COPY`` names, modes kept, as the plugin cache does (row 12)."""
    for pattern in _COPY:
        matches = [p for p in glob.glob(os.path.join(glob.escape(_TOOLKIT), pattern))
                   if os.path.isfile(p)]
        assert matches, "non-vacuity: %s matched nothing" % pattern
        for src in matches:
            out = os.path.join(str(dest), os.path.relpath(src, _TOOLKIT))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(src, out)
    return str(dest)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _home(tmp_path, monkeypatch):
    """Point ``~`` at a sandbox HOME, as test_checks.py does."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    return home


def _record(home, plugins):
    _write_json(home / ".claude" / "plugins" / "installed_plugins.json",
                {"version": 2, "plugins": plugins})


def _entry(path, version=_VERSION):
    return {"scope": "user", "installPath": str(path), "version": version,
            "installedAt": "2026-10-28T00:00:00.000Z",
            "lastUpdated": "2026-10-28T00:00:00.000Z", "gitCommitSha": "0" * 40}


def _plugin(home, version=_VERSION, record=True, pointer=True):
    """An adlc install from the GitHub marketplace; returns its real root."""
    root = home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / version
    _copy_toolkit(root)
    if record:
        _record(home, {"adlc@adlc-toolkit": [_entry(root, version)]})
        _write_json(home / ".claude" / "plugins" / "known_marketplaces.json", {
            "adlc-toolkit": {
                "source": {"source": "github", "repo": "atelier-fashion/adlc-toolkit"},
                "installLocation": str(home / ".claude" / "plugins" / "marketplaces"
                                       / "adlc-toolkit"),
                "lastUpdated": "2026-10-28T00:00:00.000Z"}})
    if pointer:
        _pointer(home, root)
    return os.path.realpath(str(root))


def _pointer(home, root):
    """What the SessionStart hook writes: the root and one newline (ADR-4)."""
    path = home / ".claude" / "adlc" / "plugin-root"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(root) + "\n")


def _clone(tmp_path):
    return os.path.realpath(_copy_toolkit(tmp_path / "clone"))


def _symlinks(home, clone):
    """What install.sh's ensure_symlink makes."""
    (home / ".claude" / "skills").symlink_to(clone)
    (home / ".claude" / "agents").symlink_to(os.path.join(clone, "agents"))


def _profile(root, route):
    return Profile(os="Darwin", login_shell="/bin/zsh", repo_root=str(root), route=route)


@pytest.fixture
def symlink_only(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    return types.SimpleNamespace(home=home, clone=clone, root=None)


@pytest.fixture
def plugin_only(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    return types.SimpleNamespace(home=home, clone=None, root=_plugin(home))


@pytest.fixture
def doubled(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    return types.SimpleNamespace(home=home, clone=clone, root=_plugin(home))


def _script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def _sandbox_bin(tmp_path):
    """``python3`` (this interpreter) and a stub ``gh``, ahead of /usr/bin:/bin."""
    bindir = tmp_path / "sandbox-bin"
    _script(bindir / "python3", '#!/bin/sh\nexec "%s" "$@"\n' % sys.executable)
    _script(bindir / "gh", "#!/bin/sh\nexit 0\n")
    return "%s:/usr/bin:/bin" % bindir


def _scrubbed_env(home, path, **extra):
    """HOME is the sandbox and PATH is given; nothing else leaks in."""
    env = {"HOME": str(home), "PATH": path}
    for key in ("LANG", "LC_ALL", "TMPDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update({k: str(v) for k, v in extra.items()})
    return env


def _git_identity(home):
    (home / ".gitconfig").write_text("[user]\n\tname = Sandbox\n\temail = sandbox@example.com\n")


# --- BR-11 / AC-4: the doubled install ---------------------------------------

@pytest.mark.parametrize("route", ["symlink", "plugin"])
def test_doubled_install_reported_with_fixes(doubled, route):
    """Both installs: FAIL, naming each spelling's copy, with one fix per way out.

    Either route's doctor reports it, since either can find the other.
    """
    root = doubled.clone if route == "symlink" else doubled.root
    result, detail, remediation = checks.check_doubled_install(_profile(root, route))
    assert result is Result.FAIL
    assert "Bare /spec reaches the personal copy at ~/.claude/skills" in detail
    assert os.path.join(doubled.clone, "spec", "SKILL.md") in detail
    assert "/adlc:spec reaches the plugin (adlc@adlc-toolkit)" in detail
    assert os.path.join(doubled.root, "spec", "SKILL.md") in detail
    # The bare-name claim cites what TASK-120 measured (Technical Notes).
    assert "verification.md row 6" in detail

    lines = remediation.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("claude plugin uninstall adlc@adlc-toolkit   #")
    claude_dir = os.path.join(str(doubled.home), ".claude")
    assert lines[1].startswith("rm %s && rm %s   #" % (
        _q(os.path.join(claude_dir, "skills")), _q(os.path.join(claude_dir, "agents"))))

    # Each way out is its own copy-pasteable `-> fix:` line in the report.
    report = doctor.format_report(
        [CheckOutcome("doubled-install", result, detail, remediation)],
        _profile(root, route))
    assert report.count("    -> fix: ") == 2
    assert "    -> fix: claude plugin uninstall adlc@adlc-toolkit" in report


def test_doubled_install_printed_by_the_doctor(tmp_path):
    """The same finding end to end: `adlc doctor` run from the clone prints it.

    The sandbox install.sh shim runs the clone, so the keep-the-plugin fix
    removes it too; without that, `adlc` would keep running the clone.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    _plugin(home)
    shim = _script(home / "bin" / "adlc", '#!/bin/sh\nexec python3 "%s" "$@"\n'
                   % os.path.join(clone, "tools", "adlc", "adlc.py"))
    work = tmp_path / "elsewhere"
    work.mkdir()
    out = subprocess.run(
        [sys.executable, os.path.join(clone, "tools", "adlc", "adlc.py"),
         "doctor", "--checks", "doubled-install"],
        capture_output=True, text=True, cwd=str(work),
        env=_scrubbed_env(home, _sandbox_bin(tmp_path)))
    assert "Traceback" not in out.stderr, out.stderr
    assert out.returncode == 1, out.stdout
    assert "[FAIL] doubled-install — both installs are active." in out.stdout
    assert "Bare /spec reaches the personal copy at ~/.claude/skills" in out.stdout
    fixes = [ln for ln in out.stdout.splitlines() if ln.startswith("    -> fix: ")]
    claude_dir = os.path.join(str(home), ".claude")
    assert fixes[0].startswith("    -> fix: claude plugin uninstall adlc@adlc-toolkit")
    assert fixes[1].startswith("    -> fix: rm %s && rm %s && rm %s   #" % (
        _q(os.path.join(claude_dir, "skills")), _q(os.path.join(claude_dir, "agents")),
        _q(shim)))
    assert "route=symlink" in out.stdout


def test_doubled_finding_on_one_directory_loaded_both_ways(tmp_path, monkeypatch):
    """A local-path marketplace from the very clone the symlink names.

    The plugin runs from its source directory (verification.md row 12, E4), so
    both spellings reach the same files, and it is still two installs.
    """
    home = _home(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    cache = home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / _VERSION
    _copy_toolkit(cache)
    _record(home, {"adlc@adlc-toolkit": [_entry(cache)]})
    _write_json(home / ".claude" / "plugins" / "known_marketplaces.json", {
        "adlc-toolkit": {"source": {"source": "directory", "path": clone},
                         "installLocation": clone,
                         "lastUpdated": "2026-10-28T00:00:00.000Z"}})
    plugin = doctor.detect_plugin_install()
    assert (plugin.state, plugin.roots) == ("present", [clone])
    # The contributor flow: the recorded root is also the symlink target, so the
    # route stays symlink and the symlink health checks still run on it.
    assert doctor.detect_route(clone, plugin, clone) == doctor.ROUTE_SYMLINK
    assert doctor.detect_route(clone, plugin, doctor._symlink_target()) == doctor.ROUTE_SYMLINK
    # Twin: with no symlink install naming it, the recorded root is the plugin.
    assert doctor.detect_route(clone, plugin) == doctor.ROUTE_PLUGIN
    for route in ("symlink", "plugin"):
        result, detail, _rem = checks.check_doubled_install(_profile(clone, route))
        assert result is Result.FAIL
        assert "(the same directory, loaded through both routes)" in detail


def _contributor_machine(tmp_path):
    """A clone linked as ~/.claude/skills AND installed from a directory marketplace on itself."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    cache = home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / _VERSION
    _copy_toolkit(cache)
    _record(home, {"adlc@adlc-toolkit": [_entry(cache)]})
    _write_json(home / ".claude" / "plugins" / "known_marketplaces.json", {
        "adlc-toolkit": {"source": {"source": "directory", "path": clone},
                         "installLocation": clone,
                         "lastUpdated": "2026-10-28T00:00:00.000Z"}})
    return home, clone


def test_contributor_clone_keeps_the_symlink_route_end_to_end(tmp_path):
    """`adlc doctor` from that clone: route=symlink, the symlink checks run, doubling FAILs."""
    home, clone = _contributor_machine(tmp_path)
    work = tmp_path / "elsewhere"
    work.mkdir()
    out = subprocess.run(
        [sys.executable, os.path.join(clone, "tools", "adlc", "adlc.py"), "doctor",
         "--checks", "plugin-route,agents-symlink,doubled-install"],
        capture_output=True, text=True, cwd=str(work),
        env=_scrubbed_env(home, _sandbox_bin(tmp_path)))
    assert "Traceback" not in out.stderr, out.stderr
    assert "route=symlink" in out.stdout and "route detection failed" not in out.stdout
    assert "[PASS] plugin-route — symlink route: %s" % clone in out.stdout, out.stdout
    assert "[PASS] agents-symlink" in out.stdout, out.stdout   # ran, not SKIPped
    assert "[FAIL] doubled-install — both installs are active (the same directory" \
        in out.stdout, out.stdout


# --- BR-11 benign paths: one install alone prints no finding ------------------

def _assert_no_finding(result, detail, remediation):
    assert result is Result.PASS, detail
    assert remediation == ""
    for word in ("both installs", "/adlc:", "uninstall", "rm '", "cannot be told"):
        assert word not in detail, (word, detail)


@pytest.mark.parametrize("others", ["none", "other-plugins"])
def test_no_doubled_finding_symlink_only(symlink_only, others):
    """A symlink-only machine, with or without other plugins installed.

    Other plugins are the common case: their record and cache entries must not
    read as an adlc install.
    """
    if others == "other-plugins":
        home = symlink_only.home
        other = home / ".claude" / "plugins" / "cache" / "claude-plugins-official" / "superpowers" / "1.0.0"
        other.mkdir(parents=True)
        _write_json(other / ".claude-plugin" / "plugin.json", {"name": "superpowers"})
        _record(home, {"superpowers@claude-plugins-official": [_entry(other, "1.0.0")]})
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "absent"
    assert doctor.detect_route(symlink_only.clone, plugin) == doctor.ROUTE_SYMLINK
    _assert_no_finding(*checks.check_doubled_install(_profile(symlink_only.clone, "symlink")))


@pytest.mark.parametrize("shape", ["plain", "no-record", "personal-skills-dir",
                                   "link-to-personal-skills"])
def test_no_doubled_finding_plugin_only(tmp_path, monkeypatch, shape):
    """A plugin-only machine, including a ``~/.claude/skills`` that is not the toolkit.

    Claude Code users keep personal skills in ``~/.claude/skills``, even one
    named ``spec``. Without the toolkit's ``partials/`` it is not a symlink
    install, as a directory or as a link to one.
    """
    home = _home(tmp_path, monkeypatch)
    root = _plugin(home, record=(shape != "no-record"))
    personal = tmp_path / "personal-skills"
    (personal / "spec").mkdir(parents=True)
    (personal / "spec" / "SKILL.md").write_text("---\nname: spec\n---\nmine\n")
    if shape == "personal-skills-dir":
        shutil.copytree(str(personal), str(home / ".claude" / "skills"))
    elif shape == "link-to-personal-skills":
        (home / ".claude" / "skills").symlink_to(personal)
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "present" and plugin.roots == [root]
    _assert_no_finding(*checks.check_doubled_install(_profile(root, "plugin")))


# --- LESSON-581: an unreadable plugin install is never a reassuring pass -------

def _unknown_shapes(home):
    """Each shape gives an adlc cache copy plus a record this doctor cannot trust."""
    root = _plugin(home, record=False)
    record = home / ".claude" / "plugins" / "installed_plugins.json"
    empty = home / "empty-dir"
    empty.mkdir()
    return root, {
        "not-json": lambda: record.write_text("{"),
        "schema-3": lambda: _write_json(record, {"version": 3, "plugins": {}}),
        "entry-not-a-list": lambda: _write_json(
            record, {"version": 2, "plugins": {"adlc@adlc-toolkit": _entry(root)}}),
        "no-install-path": lambda: _record(home, {"adlc@adlc-toolkit": [{"scope": "user"}]}),
        "path-without-manifest": lambda: _record(home, {"adlc@adlc-toolkit": [_entry(empty)]}),
        "record-is-a-directory": lambda: record.mkdir(parents=True),
        # A key that would reach a fix command: refused, never quoted into one.
        "hostile-install-key": lambda: _record(
            home, {_HOSTILE_KEY: [_entry(root)]}),
        "key-with-trailing-newline": lambda: _record(
            home, {"adlc@adlc-toolkit\n": [_entry(root)]}),
    }


#: An install key carrying a quote, a command substitution and a separator.
_HOSTILE_KEY = "adlc@x'; touch pwned-key; $(touch pwned-key2)"

_UNKNOWN = ["not-json", "schema-3", "entry-not-a-list", "no-install-path",
            "path-without-manifest", "record-is-a-directory", "hostile-install-key",
            "key-with-trailing-newline"]


@pytest.mark.parametrize("shape", _UNKNOWN)
def test_unreadable_plugin_install_is_unknown_and_fails(tmp_path, monkeypatch, shape):
    home = _home(tmp_path, monkeypatch)
    root, shapes = _unknown_shapes(home)
    shapes[shape]()
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "unknown", plugin
    assert plugin.detail

    # plugin route: this copy cannot be confirmed as the one Claude Code loads.
    result, detail, remediation = checks.check_plugin_route(_profile(root, "plugin"))
    assert result is Result.FAIL
    assert "cannot confirm" in detail and remediation.startswith("claude plugin details adlc")

    # next to a live symlink install: the doubling cannot be ruled out.
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    result, detail, remediation = checks.check_doubled_install(_profile(clone, "symlink"))
    assert result is Result.FAIL
    assert "cannot be told" in detail
    lines = remediation.splitlines()
    assert lines[0].startswith("claude plugin details adlc")
    assert lines[1].startswith("claude plugin uninstall adlc@adlc-toolkit")
    assert lines[2].startswith("rm ")
    assert "pwned" not in remediation


def test_unknown_plugin_state_without_a_symlink_install_still_passes(tmp_path, monkeypatch):
    """With no symlink install there is nothing to double, whatever the record says."""
    home = _home(tmp_path, monkeypatch)
    root, shapes = _unknown_shapes(home)
    shapes["schema-3"]()
    result, detail, remediation = checks.check_doubled_install(_profile(root, "plugin"))
    assert result is Result.PASS and remediation == ""
    assert "adlc plugin: unknown" in detail


def test_plugin_install_absent_and_present(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    assert doctor.detect_plugin_install().state == "absent"
    root = _plugin(home, record=False)
    cache_only = doctor.detect_plugin_install()
    assert (cache_only.state, cache_only.roots, cache_only.keys) == (
        "present", [root], ["adlc@adlc-toolkit"])
    _record(home, {"adlc@adlc-toolkit": [_entry(root)]})
    recorded = doctor.detect_plugin_install()
    assert (recorded.state, recorded.roots) == ("present", [root])


def test_record_names_the_live_copy_among_older_versions(tmp_path, monkeypatch):
    """Older versions stay in the cache after an update (verification.md row 12).

    The record's installPath is the live one; an older copy run by path is
    told so, with the command that runs the live copy.
    """
    home = _home(tmp_path, monkeypatch)
    old = _plugin(home, version="0.0.1", record=False, pointer=False)
    new = _plugin(home)
    plugin = doctor.detect_plugin_install()
    assert plugin.roots == [new]
    assert doctor.detect_route(old, plugin) == doctor.ROUTE_PLUGIN
    result, detail, remediation = checks.check_plugin_route(_profile(old, "plugin"))
    assert result is Result.FAIL
    assert "not the copy Claude Code loads" in detail
    assert remediation == "%s doctor" % _q(os.path.join(new, "scripts", "adlc"))


# --- after `claude plugin uninstall`: leftovers, not a conflict ---------------

def _uninstalled(home, others):
    """What an uninstall leaves: a v2 record with no adlc entry, cache copies kept.

    One leftover copy carries Claude Code's ``.orphaned_at`` marker and one
    does not, so both kinds of leftover are in the cache.
    """
    old = _plugin(home, version="0.0.1", record=False, pointer=False)
    live = _plugin(home, record=False, pointer=False)
    (home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / "0.0.1"
     / ".orphaned_at").write_text("1761696000000\n")
    plugins = {}
    if others:
        other = home / ".claude" / "plugins" / "cache" / "claude-plugins-official" / "superpowers" / "1.0.0"
        _write_json(other / ".claude-plugin" / "plugin.json", {"name": "superpowers"})
        plugins["superpowers@claude-plugins-official"] = [_entry(other, "1.0.0")]
    _record(home, plugins)
    return old, live


@pytest.mark.parametrize("others", [False, True])
def test_leftover_cache_copies_on_a_symlink_machine_are_absent_not_unknown(
        tmp_path, monkeypatch, others):
    """A well-formed record with no adlc entry is `absent`, whatever the cache holds.

    Before, the leftover copies read as a record/cache conflict: `unknown`,
    so `doubled-install` FAILed on every symlink machine that had ever tried
    the plugin, and its fix said to uninstall again.
    """
    home = _home(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    old, live = _uninstalled(home, others)
    plugin = doctor.detect_plugin_install()
    assert (plugin.state, plugin.roots, plugin.keys) == ("absent", [], [])
    assert "leftover adlc copies in the plugin cache at %s are not loaded" % live in plugin.detail
    assert old not in plugin.detail   # the orphan-marked copy is not even a leftover install
    assert doctor.detect_route(clone, plugin, doctor._symlink_target()) == doctor.ROUTE_SYMLINK
    _assert_no_finding(*checks.check_doubled_install(_profile(clone, "symlink")))
    assert checks.check_plugin_route(_profile(clone, "symlink"))[0] is Result.PASS


def test_leftover_cache_copies_end_to_end_doctor_passes(tmp_path):
    """The same machine through `adlc doctor`: no FAIL on either route check."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    _uninstalled(home, others=True)
    work = tmp_path / "elsewhere"
    work.mkdir()
    out = subprocess.run(
        [sys.executable, os.path.join(clone, "tools", "adlc", "adlc.py"), "doctor",
         "--checks", "plugin-route,doubled-install"],
        capture_output=True, text=True, cwd=str(work),
        env=_scrubbed_env(home, _sandbox_bin(tmp_path)))
    assert "Traceback" not in out.stderr, out.stderr
    assert out.returncode == 0, out.stdout
    assert "[PASS] doubled-install — symlink install only" in out.stdout
    assert "leftover adlc copies" in out.stdout
    assert "-> fix:" not in out.stdout and "route=symlink" in out.stdout


def test_orphan_marked_cache_copy_is_not_an_install(tmp_path, monkeypatch):
    """With no record at all, a copy carrying `.orphaned_at` does not count."""
    home = _home(tmp_path, monkeypatch)
    root = _plugin(home, record=False, pointer=False)
    assert doctor.detect_plugin_install().state == "present"   # twin: unmarked counts
    with open(os.path.join(root, ".orphaned_at"), "w", encoding="utf-8") as fh:
        fh.write("1761696000000\n")
    assert doctor.detect_plugin_install().state == "absent"


def test_running_a_leftover_cache_copy_says_it_is_not_installed(tmp_path, monkeypatch):
    """The plugin route from a copy the record does not name: not installed, not "no manifest"."""
    home = _home(tmp_path, monkeypatch)
    _old, live = _uninstalled(home, others=False)
    result, detail, remediation = checks.check_plugin_route(_profile(live, "plugin"))
    assert result is Result.FAIL
    assert "the adlc plugin is not installed" in detail
    assert "has no .claude-plugin/plugin.json" not in detail
    assert remediation.startswith("claude plugin details adlc")


# --- CLAUDE_CONFIG_DIR: where Claude Code keeps its plugins ----------------------

def _moved_config(tmp_path, monkeypatch):
    """A plugin install under CLAUDE_CONFIG_DIR, and nothing in ~/.claude/plugins."""
    home = _home(tmp_path, monkeypatch)
    alt = tmp_path / "alt"
    root = _plugin(alt, pointer=False)
    _pointer(home, root)   # the hook writes the pointer under $HOME either way
    return home, alt / ".claude", root


def test_claude_config_dir_is_where_the_plugin_is_read(tmp_path, monkeypatch):
    _home_dir, config, root = _moved_config(tmp_path, monkeypatch)
    # Twin first: without the variable, ~/.claude has no plugin and the copy,
    # outside ~/.claude/plugins/cache, reads as the symlink route.
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "absent"
    assert doctor.detect_route(root, plugin) == doctor.ROUTE_SYMLINK

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    plugin = doctor.detect_plugin_install()
    assert (plugin.state, plugin.roots) == ("present", [root])
    assert doctor.detect_route(root, plugin) == doctor.ROUTE_PLUGIN
    assert doctor.under_plugin_cache(root)

    # A relative value is ignored: it would depend on the working directory.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", os.path.relpath(str(config)))
    assert doctor.detect_plugin_install().state == "absent"


def test_claude_config_dir_names_itself_in_the_detail(tmp_path, monkeypatch):
    _home_dir, config, _root = _moved_config(tmp_path, monkeypatch)
    (config / "plugins" / "installed_plugins.json").write_text("{")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "unknown"
    assert plugin.detail.startswith("$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json")


def test_claude_config_dir_plugin_doctor_reports_the_plugin_route(tmp_path):
    """End to end: the plugin copy's own doctor, with the variable set, is route=plugin."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    alt = tmp_path / "alt"
    root = _plugin(alt, pointer=False)
    _pointer(home, root)
    out = subprocess.run(
        [os.path.join(root, "scripts", "adlc"), "doctor", "--checks", "plugin-route,doubled-install"],
        capture_output=True, text=True, cwd=str(tmp_path),
        env=_scrubbed_env(home, _sandbox_bin(tmp_path), CLAUDE_CONFIG_DIR=alt / ".claude"))
    assert "Traceback" not in out.stderr, out.stderr
    assert "route=plugin" in out.stdout, out.stdout
    assert "[PASS] plugin-route — plugin route: %s" % root in out.stdout, out.stdout
    assert "-> fix:" not in out.stdout and "verdict: OK" in out.stdout


# --- Profile.route (ADR-7) ---------------------------------------------------

def test_route_follows_the_running_copy(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    root = _plugin(home)
    plugin = doctor.detect_plugin_install()
    assert doctor.detect_route(root, plugin) == doctor.ROUTE_PLUGIN
    assert doctor.detect_route(clone, plugin) == doctor.ROUTE_SYMLINK
    # realpath on both sides (ASSUME-001): a link into the cache is the plugin.
    link = tmp_path / "link-to-plugin"
    link.symlink_to(root)
    assert doctor.detect_route(str(link), plugin) == doctor.ROUTE_PLUGIN


def test_route_and_root_from_a_cache_copy_inside_a_dotfiles_repo(cache_shaped_tree):
    """The cache copy reports itself, not the git repo that encloses ``~/.claude``.

    ``doctor._detect_repo_root`` and ``adlc._repo_root`` used ``git rev-parse
    --show-toplevel``, which names the sandbox HOME here (TASK-132's fixture).
    """
    tree = cache_shaped_tree
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import adlc, doctor\n"
            "print(doctor._detect_repo_root()); print(adlc._repo_root())\n"
            "print(adlc._version()); print(doctor.build_profile().route)\n")
    out = subprocess.run(
        [sys.executable, "-I", "-c", code, os.path.join(tree.root, "tools", "adlc")],
        capture_output=True, text=True, env=tree.env, cwd=tree.home)
    assert out.returncode == 0, out.stderr
    real = os.path.realpath(tree.root)
    assert out.stdout.splitlines() == [real, real, _VERSION, "plugin"]


def test_registry_order_and_route_gating():
    ids = [c.id for c in checks.REGISTRY]
    assert ids[0] == "plugin-route"
    assert ids.index("doubled-install") == ids.index("agents-symlink") + 1
    plugin, symlink = _profile("/r", "plugin"), _profile("/r", "symlink")
    for check in checks.REGISTRY:
        assert check.applies_to(symlink), check.id
        if check.id in _SYMLINK_CHECKS:
            assert not check.applies_to(plugin), check.id
            assert check.skip_notice.startswith("plugin route:"), check.id
    # Darwin profiles, so launchctl applies on both; only the four are gated.
    assert sorted(c.id for c in checks.REGISTRY if not c.applies_to(plugin)) \
        == sorted(_SYMLINK_CHECKS)


def test_symlink_checks_skip_with_a_plugin_route_notice(plugin_only):
    registry = [c for c in checks.REGISTRY if c.id in _SYMLINK_CHECKS]
    outcomes = doctor.run_checks(_profile(plugin_only.root, "plugin"), registry=registry)
    assert [o.id for o in outcomes] == list(_SYMLINK_CHECKS)
    for o in outcomes:
        assert o.result is Result.SKIP, o
        assert "plugin route" in o.detail


# --- plugin-route ------------------------------------------------------------

def test_plugin_route_reports_the_symlink_route(symlink_only):
    result, detail, _rem = checks.check_plugin_route(_profile(symlink_only.clone, "symlink"))
    assert result is Result.PASS
    assert detail == "symlink route: %s, version %s" % (symlink_only.clone, _VERSION)


def test_plugin_route_passes_when_wired(plugin_only, monkeypatch):
    shim = os.path.join(plugin_only.root, "scripts", "adlc")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setattr(checks.shutil, "which", lambda name: shim)
    result, detail, _rem = checks.check_plugin_route(_profile(plugin_only.root, "plugin"))
    assert result is Result.PASS, detail
    assert detail.startswith("plugin route: %s, version %s (adlc@adlc-toolkit)"
                             % (plugin_only.root, _VERSION))
    assert "adlc on PATH is this copy's scripts/adlc" in detail


@pytest.mark.parametrize("content", [None, "", "relative/path\n", "/elsewhere\n", "two\nlines\n"])
def test_plugin_route_fails_without_a_current_pointer(plugin_only, monkeypatch, content):
    """A missing, empty, relative or foreign pointer is a FAIL with the hook's command.

    The working directory is the plugin root, so an empty pointer, whose
    ``realpath`` is the working directory, cannot pass by accident.
    """
    pointer = plugin_only.home / ".claude" / "adlc" / "plugin-root"
    if content is None:
        pointer.unlink()
    else:
        pointer.write_text(content)
    monkeypatch.chdir(plugin_only.root)
    monkeypatch.setattr(checks.shutil, "which",
                        lambda name: os.path.join(plugin_only.root, "scripts", "adlc"))
    result, detail, remediation = checks.check_plugin_route(_profile(plugin_only.root, "plugin"))
    assert result is Result.FAIL
    assert "~/.claude/adlc/plugin-root" in detail
    assert remediation.startswith("CLAUDE_PLUGIN_ROOT=%s sh %s" % (
        _q(plugin_only.root), _q(os.path.join(plugin_only.root, "scripts", "session-start.sh"))))


def test_plugin_route_pointer_fix_is_copy_pasteable(plugin_only, monkeypatch):
    """Running the printed fix writes the pointer, and the check then passes."""
    (plugin_only.home / ".claude" / "adlc" / "plugin-root").unlink()
    monkeypatch.setattr(checks.shutil, "which",
                        lambda name: os.path.join(plugin_only.root, "scripts", "adlc"))
    profile = _profile(plugin_only.root, "plugin")
    _r, _d, remediation = checks.check_plugin_route(profile)
    run = subprocess.run(["sh", "-c", remediation], capture_output=True, text=True,
                         env=_scrubbed_env(plugin_only.home, "/usr/bin:/bin"))
    assert run.returncode == 0, run.stderr
    assert checks.check_plugin_route(profile)[0] is Result.PASS


def _local_path_plugin(tmp_path, monkeypatch):
    """A local-path marketplace with no symlink install: the plugin runs from its source.

    Claude Code sets ``CLAUDE_PLUGIN_ROOT`` to the source directory (verification.md
    row 12), which is outside the plugin cache, so the SessionStart hook never
    records it in ``~/.claude/adlc/plugin-root`` (ADR-4).
    """
    home = _home(tmp_path, monkeypatch)
    src = os.path.realpath(_copy_toolkit(tmp_path / "src"))
    cache = home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / _VERSION
    _copy_toolkit(cache)
    _record(home, {"adlc@adlc-toolkit": [_entry(cache)]})
    _write_json(home / ".claude" / "plugins" / "known_marketplaces.json", {
        "adlc-toolkit": {"source": {"source": "directory", "path": src},
                         "installLocation": src,
                         "lastUpdated": "2026-10-28T00:00:00.000Z"}})
    monkeypatch.setattr(checks.shutil, "which",
                        lambda name: os.path.join(src, "scripts", "adlc"))
    return home, src, os.path.realpath(str(cache))


@pytest.mark.parametrize("pointer", ["absent", "cache"])
def test_plugin_route_local_path_root_is_not_failed_on_the_pointer(tmp_path, monkeypatch,
                                                                   pointer):
    """The hook never records a local-path root, so the pointer is reported, not FAILed.

    Re-running the hook for such a root writes nothing, so a FAIL here would
    print a fix that cannot fix it.
    """
    home, src, cache = _local_path_plugin(tmp_path, monkeypatch)
    if pointer == "cache":
        _pointer(home, cache)
    plugin = doctor.detect_plugin_install()
    assert doctor.detect_route(src, plugin) == doctor.ROUTE_PLUGIN
    result, detail, remediation = checks.check_plugin_route(_profile(src, "plugin"))
    assert result is Result.PASS, detail
    assert remediation == ""
    assert "records only a plugin-cache copy" in detail
    assert "(%s)" % (cache if pointer == "cache" else "absent") in detail
    assert "names this copy" not in detail


def test_plugin_route_cache_root_still_fails_on_a_foreign_pointer(plugin_only, monkeypatch):
    """Twin: a cache root the pointer does not name is still a FAIL with the hook's fix."""
    _pointer(plugin_only.home, "/elsewhere")
    monkeypatch.setattr(checks.shutil, "which",
                        lambda name: os.path.join(plugin_only.root, "scripts", "adlc"))
    result, detail, remediation = checks.check_plugin_route(_profile(plugin_only.root, "plugin"))
    assert result is Result.FAIL
    assert "names /elsewhere, not this copy" in detail
    assert remediation.startswith("CLAUDE_PLUGIN_ROOT=")


def test_plugin_route_path_inside_and_outside_a_session(plugin_only, monkeypatch):
    """Not on PATH: a FAIL inside a Claude Code session (BR-7), a note outside one."""
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    profile = _profile(plugin_only.root, "plugin")
    monkeypatch.setenv("CLAUDECODE", "1")
    result, detail, remediation = checks.check_plugin_route(profile)
    assert result is Result.FAIL
    assert "not on this Claude Code session's PATH" in detail
    assert remediation.startswith('export PATH="$PATH":%s'
                                  % _q(os.path.join(plugin_only.root, "scripts")))
    monkeypatch.delenv("CLAUDECODE")
    result, detail, _rem = checks.check_plugin_route(profile)
    assert result is Result.PASS
    assert "not on this shell's PATH" in detail


def test_plugin_route_fails_on_a_shim_that_cannot_run(plugin_only, monkeypatch):
    shim = os.path.join(plugin_only.root, "scripts", "adlc")
    os.chmod(shim, 0o644)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    result, detail, remediation = checks.check_plugin_route(_profile(plugin_only.root, "plugin"))
    assert result is Result.FAIL
    assert "scripts/adlc is not executable" in detail
    assert remediation == "chmod +x %s" % _q(shim)


# --- route-aware remediations: no install.sh on the plugin route --------------

def _no_pyyaml_interpreter(tmp_path):
    poison = tmp_path / "poison" / "yaml"
    poison.mkdir(parents=True)
    (poison / "__init__.py").write_text("raise ImportError('no yaml (test poison)')\n")
    return _script(tmp_path / "nopyyaml" / "python3", '#!/bin/sh\nPYTHONPATH="%s" exec "%s" "$@"\n'
                   % (tmp_path / "poison", sys.executable))


@pytest.mark.parametrize("route", ["plugin", "symlink"])
def test_pyyaml_fix_is_route_aware(plugin_only, tmp_path, monkeypatch, route):
    """install.sh on the plugin route would symlink the plugin copy: a doubled install."""
    cfg = plugin_only.home / ".claude" / "adlc" / "config.yml"
    cfg.write_text("delegate:\n  enabled: false\n")
    monkeypatch.delenv("ADLC_CONFIG", raising=False)
    interp = _no_pyyaml_interpreter(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    result, _detail, remediation = checks.check_pyyaml(_profile(plugin_only.root, route))
    assert result is Result.FAIL
    if route == "plugin":
        assert "install.sh" not in remediation
        assert remediation == "%s -m pip install --user %s" % (_q(interp), _q(_PYYAML_PIN))
    else:
        assert remediation == _q(os.path.join(plugin_only.root, "install.sh")) \
            + " --with-delegation"


@pytest.mark.parametrize("route", ["plugin", "symlink"])
def test_delegate_gate_fix_is_route_aware(monkeypatch, route):
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (2, "no-binary"))
    monkeypatch.setattr(checks, "_config_enabled", lambda p: True)
    result, _detail, remediation = checks.check_delegate_gate(_profile("/r", route))
    assert result is Result.FAIL
    assert "delegate.enabled: false" in remediation
    assert ("install.sh" in remediation) is (route == "symlink")


# --- AC-1: a plugin-only machine runs the whole doctor with no FAIL ------------

def _plugin_machine(tmp_path):
    """A plugin-only sandbox after a real SessionStart: hook run, env file written."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _git_identity(home)
    root = _plugin(home, pointer=False)
    env_file = home / ".claude" / "session-env" / "s1" / "sessionstart-hook-0.sh"
    env_file.parent.mkdir(parents=True)
    path = _sandbox_bin(tmp_path)
    hook = subprocess.run(
        ["sh", os.path.join(root, "scripts", "session-start.sh")],
        capture_output=True, text=True, cwd=str(tmp_path),
        env=_scrubbed_env(home, path, CLAUDE_PLUGIN_ROOT=root, CLAUDE_ENV_FILE=env_file))
    assert hook.returncode == 0 and hook.stderr == "", hook.stderr
    assert (home / ".claude" / "adlc" / "plugin-root").read_text() == root + "\n"
    assert (home / ".claude" / "adlc" / "config.yml").is_file()
    assert not (home / ".claude" / "skills").exists()
    assert not (home / "bin" / "adlc").exists()
    work = tmp_path / "elsewhere"   # not a git repo: forge and reservations SKIP
    work.mkdir()
    return types.SimpleNamespace(home=home, root=root, env_file=str(env_file), path=path,
                                 work=str(work))


def _doctor_in_session(machine, **extra):
    """`adlc doctor` as a Claude Code Bash call runs it: env file sourced, CLI from PATH."""
    return subprocess.run(
        ["sh", "-c", '. "$1" && exec adlc doctor', "sh", machine.env_file],
        capture_output=True, text=True, cwd=machine.work,
        env=_scrubbed_env(machine.home, machine.path, CLAUDECODE=1, **extra))


def _no_pyyaml_env(tmp_path):
    """What makes every interpreter in the sandbox PyYAML-less, as a fresh Mac's is.

    The poison package is first on ``PYTHONPATH``, so ``import yaml`` raises
    there before any site-packages is searched, and ``PYTHONNOUSERSITE`` keeps
    a user-site install out as well.
    """
    poison = tmp_path / "poison" / "yaml"
    poison.mkdir(parents=True, exist_ok=True)
    (poison / "__init__.py").write_text("raise ImportError('no yaml (test poison)')\n")
    return {"PYTHONPATH": tmp_path / "poison", "PYTHONNOUSERSITE": 1}


def test_plugin_only_doctor_no_failures(tmp_path):
    """AC-1 on a python3 with no PyYAML: exit 0, no FAIL, the symlink checks SKIP.

    The hook scaffolds config.yml, which is exactly what a fresh Mac has after
    its first session. The `pyyaml` check SKIPs on that unedited scaffold, so
    the whole doctor passes without PyYAML anywhere. The sandbox's python3 is
    first shown to be unable to import yaml, so the pass cannot come from an
    interpreter that has it.
    """
    machine = _plugin_machine(tmp_path)
    no_yaml = _no_pyyaml_env(tmp_path)
    probe = subprocess.run(
        ["python3", "-c", "import yaml"], capture_output=True, text=True,
        cwd=machine.work, env=_scrubbed_env(machine.home, machine.path, **no_yaml))
    assert probe.returncode != 0 and "test poison" in probe.stderr, probe.stderr

    out = _doctor_in_session(machine, **no_yaml)
    assert "Traceback" not in out.stderr, out.stderr
    assert out.returncode == 0, out.stdout
    rows = {ln.split(" — ", 1)[0]: ln for ln in out.stdout.splitlines() if ln.startswith("[")}
    assert not [r for r in rows if r.startswith("[FAIL]")], out.stdout
    for cid in _SYMLINK_CHECKS:
        assert rows["[SKIP] %s" % cid].endswith(checks._SYMLINK_ROUTE_ONLY), out.stdout
    assert rows["[PASS] plugin-route"].startswith(
        "[PASS] plugin-route — plugin route: %s, version %s (adlc@adlc-toolkit)"
        % (machine.root, _VERSION))
    assert "adlc on PATH is this copy's scripts/adlc" in rows["[PASS] plugin-route"]
    assert "[PASS] doubled-install" in rows
    assert "unedited delegation-off scaffold" in rows["[SKIP] pyyaml"], out.stdout
    assert "--repair" not in out.stdout and "--with-delegation" not in out.stdout
    assert "route=plugin" in out.stdout
    assert "verdict: OK" in out.stdout


@pytest.mark.parametrize("config", ["project-config", "edited-machine-config"])
def test_plugin_only_doctor_without_pyyaml_never_prints_install_sh(tmp_path, config):
    """A config PyYAML must read, and no PyYAML: `pyyaml` FAILs with a plugin-route fix.

    A project config, or a machine config edited away from the scaffold, says
    something only PyYAML can read, so the SKIP above does not apply. That FAIL
    is the machine's real state, not a route mistake. Its fix must not be
    install.sh, which would symlink the plugin copy and double the install.
    """
    machine = _plugin_machine(tmp_path)
    if config == "project-config":
        proj = os.path.join(machine.work, ".adlc", "config.yml")
        os.makedirs(os.path.dirname(proj))
        with open(proj, "w", encoding="utf-8") as fh:
            fh.write("forge:\n  provider: github\n")
    else:
        with open(machine.home / ".claude" / "adlc" / "config.yml", "a", encoding="utf-8") as fh:
            fh.write("# edited by hand\n")
    out = _doctor_in_session(machine, **_no_pyyaml_env(tmp_path))
    assert "Traceback" not in out.stderr, out.stderr
    fails = [ln for ln in out.stdout.splitlines() if ln.startswith("[FAIL]")]
    assert [f.split(" — ", 1)[0] for f in fails] == ["[FAIL] pyyaml"], out.stdout
    assert "-m pip install --user %s" % _q(_PYYAML_PIN) in out.stdout
    assert "install.sh --" not in out.stdout


# --- a failed route detection is a fallback, not a finding ----------------------

def test_failed_route_detection_says_so_and_prints_no_install_sh(tmp_path, monkeypatch):
    """`build_profile` falls back to symlink; `plugin-route` FAILs naming the failure.

    Every check still runs, but none prints install.sh as a fix: the machine
    may be a plugin install, where install.sh doubles it (BR-11).
    """
    home = _home(tmp_path, monkeypatch)
    cfg = home / ".claude" / "adlc" / "config.yml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("delegate:\n  enabled: true\n")
    monkeypatch.chdir(tmp_path)

    def broken():
        raise OSError(13, "Permission denied", str(home / "secret-path"))

    monkeypatch.setattr(doctor, "detect_plugin_install", broken)
    profile = doctor.build_profile()
    assert profile.route == doctor.ROUTE_SYMLINK
    assert profile.route_error == "PermissionError: Permission denied"
    assert profile.plugin.state == "unknown"

    interp = _no_pyyaml_interpreter(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (2, "no-binary"))
    monkeypatch.setattr(checks, "_config_enabled", lambda p: True)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    ids = ("plugin-route", "doubled-install", "path-shims", "delegate-gate", "pyyaml")
    outcomes = doctor.run_checks(profile, registry=[c for c in checks.REGISTRY if c.id in ids])
    by_id = {o.id: o for o in outcomes}
    assert by_id["plugin-route"].result is Result.FAIL
    assert by_id["plugin-route"].detail.startswith("route detection failed (PermissionError")
    assert "secret-path" not in by_id["plugin-route"].detail   # LESSON-021
    for cid in ("path-shims", "delegate-gate", "pyyaml"):
        assert by_id[cid].result is Result.FAIL, by_id[cid]
    report = doctor.format_report(outcomes, profile)
    fixes = [ln for ln in report.splitlines() if ln.startswith("    -> fix: ")]
    assert len(fixes) >= 4, report
    assert not [f for f in fixes if "install.sh" in f], report
    assert "route=symlink (route detection failed)" in report

    # Twin: the same checks on a profile whose route was detected do print it.
    ok = doctor.Profile(os="Darwin", login_shell="", repo_root=profile.repo_root)
    report = doctor.format_report(
        doctor.run_checks(ok, registry=[c for c in checks.REGISTRY if c.id in ids[2:]]), ok)
    assert "install.sh" in report


def test_plugin_install_is_read_once_per_doctor_run(plugin_only, monkeypatch):
    """`build_profile` reads it, and the two route checks reuse that reading."""
    real = doctor.detect_plugin_install
    calls = []

    def counted():
        calls.append(1)
        return real()

    monkeypatch.setattr(doctor, "detect_plugin_install", counted)
    monkeypatch.setattr(checks, "detect_plugin_install", counted)
    monkeypatch.setattr(doctor, "_detect_repo_root", lambda: plugin_only.root)
    profile = doctor.build_profile()
    assert profile.route == doctor.ROUTE_PLUGIN and profile.plugin.state == "present"
    doctor.run_checks(profile, registry=[c for c in checks.REGISTRY
                                         if c.id in ("plugin-route", "doubled-install")])
    assert len(calls) == 1
    # A profile built by hand has no reading, and a check makes its own.
    checks.check_doubled_install(_profile(plugin_only.root, "plugin"))
    assert len(calls) == 2


# --- fix commands quote what they carry ----------------------------------------

#: A HOME whose name carries a quote, a separator and a command substitution.
_HOSTILE_DIR = "h'q;$(touch pwned)"


def _run_fix(fix, cwd, home, **extra):
    """Run one printed fix line, comment and all, as an operator would paste it."""
    return subprocess.run(["sh", "-c", fix], capture_output=True, text=True, cwd=str(cwd),
                          env=_scrubbed_env(home, "/usr/bin:/bin", **extra))


def test_plugin_route_fixes_quote_a_hostile_path(tmp_path, monkeypatch):
    """Every path in the plugin-route fixes is one shell word, and `$PATH` still expands."""
    home = tmp_path / _HOSTILE_DIR
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    root = _plugin(home, pointer=False)
    shim = os.path.join(root, "scripts", "adlc")
    os.chmod(shim, 0o644)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    monkeypatch.setenv("CLAUDECODE", "1")
    result, _detail, remediation = checks.check_plugin_route(_profile(root, "plugin"))
    assert result is Result.FAIL
    pointer_fix, chmod_fix, path_fix = remediation.splitlines()

    assert shlex.split(pointer_fix, comments=True) == [
        "CLAUDE_PLUGIN_ROOT=" + root, "sh", os.path.join(root, "scripts", "session-start.sh")]
    assert shlex.split(chmod_fix, comments=True) == ["chmod", "+x", shim]
    work = tmp_path / "work"
    work.mkdir()
    for fix in (pointer_fix, chmod_fix):
        assert _run_fix(fix, work, home).returncode == 0
    assert os.access(shim, os.X_OK)
    shown = _run_fix(path_fix.split("   #", 1)[0] + '; printf "%s" "$PATH"', work, home)
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout == "/usr/bin:/bin:" + os.path.join(root, "scripts")
    assert os.listdir(str(work)) == [], "a fix ran an injected command"


def test_doubled_install_fixes_quote_a_hostile_path(tmp_path, monkeypatch):
    """The `rm` way out removes exactly the links, in a HOME no shell may split."""
    home = tmp_path / _HOSTILE_DIR
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    clone = _clone(tmp_path)
    _symlinks(home, clone)
    _plugin(home)
    result, _detail, remediation = checks.check_doubled_install(_profile(clone, "symlink"))
    assert result is Result.FAIL
    _uninstall, removal = remediation.splitlines()
    claude_dir = os.path.join(str(home), ".claude")
    assert shlex.split(removal, comments=True) == [
        "rm", os.path.join(claude_dir, "skills"), "&&", "rm", os.path.join(claude_dir, "agents")]
    work = tmp_path / "work"
    work.mkdir()
    assert _run_fix(removal, work, home).returncode == 0
    assert not os.path.lexists(os.path.join(claude_dir, "skills"))
    assert not os.path.lexists(os.path.join(claude_dir, "agents"))
    assert os.path.isdir(clone), "the clone is never removed"
    assert os.listdir(str(work)) == [], "a fix ran an injected command"


def test_hostile_marketplace_directory_is_not_a_key(tmp_path, monkeypatch):
    """A cache directory named like an injection is unknown, never a printed key."""
    home = _home(tmp_path, monkeypatch)
    root = home / ".claude" / "plugins" / "cache" / "x;$(touch pwned)" / "adlc" / _VERSION
    _copy_toolkit(root)
    plugin = doctor.detect_plugin_install()
    assert plugin.state == "unknown"
    assert checks._install_key(str(root)) == "adlc@adlc-toolkit"
    assert doctor.valid_install_key("adlc@adlc-toolkit")
    for bad in ("adlc@", "adlc@-x", "adlc@X", "adlc@x y", "adlc@x\n", "other@x", None):
        assert not doctor.valid_install_key(bad), bad


# --- BR-7 / LESSON-395: the doctor imports only the standard library -----------

def _imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in %s" % path
            names.add(node.module.split(".")[0])
    return names


def test_doctor_imports_stdlib_only():
    """checks.py and doctor.py, and every sibling they import, use only the stdlib.

    Function-level imports count too (`ast.walk` sees them), so a lazy import
    of a third-party package cannot hide. A sibling module is followed, not
    trusted.
    """
    adlc_dir = os.path.dirname(os.path.realpath(checks.__file__))
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    seen, todo, external = set(), ["checks", "doctor"], set()
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        for name in _imports(os.path.join(adlc_dir, mod + ".py")):
            if os.path.isfile(os.path.join(adlc_dir, name + ".py")):
                todo.append(name)
            else:
                external.add(name)
    assert {"checks", "doctor", "toolkit_root"} <= seen
    assert {"json", "glob", "os"} <= external, "non-vacuity"
    for name in sorted(external):
        if name in sys.builtin_module_names:
            continue
        spec = importlib.util.find_spec(name)
        assert spec is not None and spec.origin, name
        if spec.origin in ("built-in", "frozen"):   # 3.11+ freezes os, among others
            continue
        origin = os.path.realpath(spec.origin)
        assert origin.startswith(stdlib + os.sep), (name, origin)
        assert "site-packages" not in origin, (name, origin)


# --- the report: one `-> fix:` line per way out --------------------------------

def test_report_prints_each_fix_line_and_keeps_single_fixes_unchanged():
    profile = _profile("/r", "symlink")
    one = doctor.format_report([CheckOutcome("x", Result.FAIL, "broken", "run this")], profile)
    assert "    -> fix: run this" in one and one.count("-> fix:") == 1
    two = doctor.format_report([CheckOutcome("x", Result.FAIL, "broken", "a\nb")], profile)
    assert "    -> fix: a\n    -> fix: b" in two
    assert "profile: os=Darwin login_shell=/bin/zsh route=symlink" in two
