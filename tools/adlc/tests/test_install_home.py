"""REQ-654 TASK-136: the root install.sh, run whole, in a sandbox clone and HOME.

Every case runs the real installer — not a slice — against a throwaway clone
that has **no git remote**, so the closing `adlc doctor` cannot push anything:
its `reservations` check SKIPs on a remote-less repo (the reason
test_install_shim.py slices instead). PATH is the system directories only, so
no harness binary and no `gh` on the developer's machine decides an outcome.

Covered: AC-1 (default home, first and second run, byte-identical state),
AC-2 (an overridden ADLC_HOME, plus Claude Code's mount and the fence
fallback), AC-4 (the view tracks an added and a removed skill), AC-5 (a
pre-existing real ~/.agents/skills with a user skill and a decoy, and
--dry-run), AC-9 (moving the clone and running --repair), and the BR-2
refusal of an unusable ADLC_HOME before any mutation.
"""

import hashlib
import os
import shutil
import subprocess

import pytest

TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))

#: The skills the sandbox clone carries. `spec` is the doctor's sample skill.
SKILLS = ("spec", "review", "proceed")
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _copy(rel, dest_root):
    src = os.path.join(TOOLKIT, rel)
    dest = os.path.join(dest_root, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)


def make_clone(path):
    """A minimal toolkit clone: the installer, the partials, the Python tools,
    three skills and one agent, committed, with no remote."""
    os.makedirs(path)
    _copy("install.sh", path)
    _copy("VERSION", path)
    for name in os.listdir(os.path.join(TOOLKIT, "partials")):
        if name.endswith(".sh"):
            _copy("partials/" + name, path)
    for sub in ("tools/adlc", "tools/delegate"):
        for name in os.listdir(os.path.join(TOOLKIT, sub)):
            if os.path.isfile(os.path.join(TOOLKIT, sub, name)):
                _copy(sub + "/" + name, path)
    for name in os.listdir(os.path.join(TOOLKIT, ".claude-plugin")):
        _copy(".claude-plugin/" + name, path)
    _copy(".cursor-plugin/plugin.json", path)
    _copy(".github/plugin/plugin.json", path)
    for skill in SKILLS:
        os.makedirs(os.path.join(path, skill))
        with open(os.path.join(path, skill, "SKILL.md"), "w") as fh:
            fh.write("---\nname: %s\ndescription: d\n---\n" % skill)
    os.makedirs(os.path.join(path, "agents"))
    with open(os.path.join(path, "agents", "reflector.md"), "w") as fh:
        fh.write("---\nname: reflector\n---\n")
    git = ["git", "-C", path, "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "clone"], check=True)
    return path


def make_home(path):
    os.makedirs(path)
    # The PATH marker in every rc file install.sh might pick, so ensure_path is
    # a no-op whatever the login shell of the user running the tests.
    marker = "# >>> adlc-toolkit (REQ-519) >>>\nexport PATH=\"$HOME/bin:$PATH\"\n# <<< adlc-toolkit (REQ-519) <<<\n"
    for rc in (".zshrc", ".bash_profile", ".profile"):
        with open(os.path.join(path, rc), "w") as fh:
            fh.write(marker)
    return path


def run_install(clone, home, *args, adlc_home=None):
    env = {"HOME": home, "PATH": SYSTEM_PATH, "USER": os.environ.get("USER", "u")}
    if adlc_home is not None:
        env["ADLC_HOME"] = adlc_home
    if "TMPDIR" in os.environ:
        env["TMPDIR"] = os.environ["TMPDIR"]
    out = subprocess.run(["bash", os.path.join(clone, "install.sh")] + list(args),
                         cwd=home, env=env, capture_output=True, text=True, timeout=300)
    return out


def done_lines(out):
    return [l.strip() for l in out.stdout.splitlines() if l.strip().startswith("done:")]


def would_lines(out):
    return [l.strip() for l in out.stdout.splitlines() if l.strip().startswith("would:")]


def snapshot(*paths):
    """{path: ('link', target) | ('file', sha, mtime) | ('dir', mtime) | None}."""
    out = {}
    for p in paths:
        if os.path.islink(p):
            out[p] = ("link", os.readlink(p))
        elif os.path.isfile(p):
            with open(p, "rb") as fh:
                out[p] = ("file", hashlib.sha256(fh.read()).hexdigest(), os.stat(p).st_mtime_ns)
        elif os.path.isdir(p):
            out[p] = ("dir", os.stat(p).st_mtime_ns)
        else:
            out[p] = None
    return out


@pytest.fixture
def box(tmp_path):
    clone = make_clone(str(tmp_path / "clone dir"))
    home = make_home(str(tmp_path / "home"))
    return clone, home, tmp_path


def _pre_req_install(clone, home):
    """A healthy install as a pre-REQ-654 install.sh left it."""
    cl = os.path.join(home, ".claude")
    os.makedirs(os.path.join(cl, "adlc"))
    os.symlink(clone, os.path.join(cl, "skills"))
    os.symlink(os.path.join(clone, "agents"), os.path.join(cl, "agents"))
    with open(os.path.join(cl, "adlc", "config.yml"), "w") as fh:
        fh.write("delegate:\n  enabled: false\n")
    for kind in ("req", "bug", "lesson"):
        with open(os.path.join(cl, ".global-next-" + kind), "w") as fh:
            fh.write("100\n")
    venv_py = os.path.join(cl, "delegate-venv", "bin", "python3")
    os.makedirs(os.path.dirname(venv_py))
    with open(venv_py, "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.chmod(venv_py, 0o755)
    os.makedirs(os.path.join(home, "bin"))
    with open(os.path.join(home, "bin", "adlc"), "w") as fh:
        fh.write("#!/usr/bin/env bash\nexec python3 old-shim\n")
    os.chmod(os.path.join(home, "bin", "adlc"), 0o755)
    return [os.path.join(cl, "skills"), os.path.join(cl, "agents"),
            os.path.join(cl, "adlc", "config.yml"),
            os.path.join(cl, ".global-next-req"), os.path.join(cl, ".global-next-bug"),
            os.path.join(cl, ".global-next-lesson"), venv_py]


def test_default_home_is_byte_identical(box):
    """AC-1: unset ADLC_HOME on a healthy pre-REQ install. The first run acts
    only on the view, the mount and the shim; the second run acts on nothing;
    every pre-existing path is byte-identical (content and mtime)."""
    clone, home, _tmp = box
    paths = _pre_req_install(clone, home)
    before = snapshot(*paths)
    first = run_install(clone, home)
    assert first.returncode == 0, first.stdout + first.stderr
    view = os.path.join(home, ".claude", "adlc", "skills-view")
    for line in done_lines(first):
        assert (view in line or os.path.join(home, ".agents", "skills") in line
                or os.path.join(home, "bin", "adlc") in line), line
    assert any("skills-view" in l for l in done_lines(first))
    assert snapshot(*paths) == before
    second = run_install(clone, home)
    assert second.returncode == 0, second.stderr
    assert done_lines(second) == []
    assert "Install summary: 0 action(s) taken" in second.stdout
    assert snapshot(*paths) == before
    dry = run_install(clone, home, "--dry-run")
    assert would_lines(dry) == [], dry.stdout


def test_override_home_keeps_claude_mount(box):
    """AC-2 / BR-3 / BR-6: ADLC_HOME=<x> puts skills, agents, the config and the
    view under <x>, AND keeps Claude Code's mount at ~/.claude, and a fence with
    no .adlc/partials/ still sources the canonical copy through
    ~/.claude/skills/partials/ (ToolkitRoot arm 2), under /bin/sh."""
    clone, home, tmp = box
    x = str(tmp / "x home")
    out = run_install(clone, home, adlc_home=x)
    assert out.returncode == 0, out.stdout + out.stderr
    assert os.readlink(os.path.join(x, "skills")) == clone
    assert os.readlink(os.path.join(x, "agents")) == os.path.join(clone, "agents")
    assert os.path.isfile(os.path.join(x, "adlc", "config.yml"))
    for skill in SKILLS:
        assert os.readlink(os.path.join(x, "adlc", "skills-view", skill)) == os.path.join(clone, skill)
    assert os.readlink(os.path.join(home, ".claude", "skills")) == clone
    assert os.readlink(os.path.join(home, ".claude", "agents")) == os.path.join(clone, "agents")
    assert not os.path.exists(os.path.join(home, ".claude", "adlc", "config.yml"))
    assert os.readlink(os.path.join(home, ".agents", "skills")) == os.path.join(x, "adlc", "skills-view")

    root_line = next(l for l in open(os.path.join(TOOLKIT, ".adlc", "context", "conventions.md"),
                                     encoding="utf-8")
                     if l.startswith("ADLC_TOOLKIT_ROOT=")).rstrip("\n")
    fence = "\n".join([
        root_line,
        'if [ -f .adlc/partials/adlc-home.sh ]; then . .adlc/partials/adlc-home.sh; '
        'else . "$ADLC_TOOLKIT_ROOT/partials/adlc-home.sh"; fi',
        'echo "root=$ADLC_TOOLKIT_ROOT"',
        'echo "home=$(adlc_home)"',
    ])
    bare = tmp / "bare-project"
    bare.mkdir()
    run = subprocess.run(["/bin/sh", "-c", fence], cwd=str(bare),
                         env={"HOME": home, "PATH": SYSTEM_PATH, "ADLC_HOME": x},
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "root=%s/.claude/skills" % home in run.stdout
    assert "home=%s" % x in run.stdout


@pytest.mark.parametrize("bad", ["", "relative/home"])
def test_invalid_home_changes_nothing(box, bad):
    """BR-2 / LESSON-017: an unusable ADLC_HOME stops the installer before its
    first mutation, naming the variable."""
    clone, home, _tmp = box
    before = sorted(os.listdir(home))
    out = run_install(clone, home, adlc_home=bad)
    assert out.returncode != 0
    assert "ADLC_HOME" in out.stderr
    assert sorted(os.listdir(home)) == before
    assert done_lines(out) == []


def test_view_tracks_added_and_removed_skill(box):
    """AC-4 / BR-4: ~/.agents/skills lists exactly the clone's skill directories,
    each a link into the clone, and a skill added or removed in the clone adds
    or removes exactly one link on the next run."""
    clone, home, _tmp = box
    assert run_install(clone, home).returncode == 0
    mount = os.path.join(home, ".agents", "skills")
    assert sorted(os.listdir(mount)) == sorted(SKILLS)
    for name in os.listdir(mount):
        entry = os.path.join(mount, name)
        assert os.path.islink(entry)
        assert os.path.realpath(entry) == os.path.realpath(os.path.join(clone, name))
    # Directories without a SKILL.md are not skills, and never shown.
    for hidden in ("tools", "partials", "agents", ".claude-plugin", ".cursor-plugin", ".github"):
        assert not os.path.lexists(os.path.join(mount, hidden))

    os.makedirs(os.path.join(clone, "zzz-test"))
    with open(os.path.join(clone, "zzz-test", "SKILL.md"), "w") as fh:
        fh.write("---\nname: zzz-test\n---\n")
    added = run_install(clone, home)
    assert added.returncode == 0
    assert [l for l in done_lines(added) if "zzz-test" in l] == done_lines(added)
    assert len(done_lines(added)) == 1
    assert sorted(os.listdir(mount)) == sorted(SKILLS + ("zzz-test",))

    shutil.rmtree(os.path.join(clone, "zzz-test"))
    removed = run_install(clone, home)
    assert removed.returncode == 0
    assert len(done_lines(removed)) == 1 and "zzz-test" in done_lines(removed)[0]
    assert sorted(os.listdir(mount)) == sorted(SKILLS)
    assert done_lines(run_install(clone, home)) == []


def test_existing_real_dir_keeps_user_entries(box):
    """AC-5 / BR-5 / BR-10: a real ~/.agents/skills/ holding the user's own
    `mine/` and a decoy `spec/` directory: --dry-run names the state and the
    plan and changes nothing; the real run links every other toolkit skill,
    reports `spec` skipped, and leaves `mine/` and `spec/` untouched."""
    clone, home, _tmp = box
    mount = os.path.join(home, ".agents", "skills")
    os.makedirs(os.path.join(mount, "mine"))
    with open(os.path.join(mount, "mine", "SKILL.md"), "w") as fh:
        fh.write("mine\n")
    os.makedirs(os.path.join(mount, "spec"))
    with open(os.path.join(mount, "spec", "notes.txt"), "w") as fh:
        fh.write("decoy\n")
    user_state = snapshot(os.path.join(mount, "mine", "SKILL.md"),
                          os.path.join(mount, "spec", "notes.txt"))

    dry = run_install(clone, home, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert "is a directory you own" in dry.stdout
    planned = [l for l in would_lines(dry) if mount in l]
    assert sorted(l.split(mount + "/")[1].split(" ")[0] for l in planned) == ["proceed", "review"]
    assert "skipped (name taken by a non-toolkit entry, left untouched): spec" in dry.stdout
    assert sorted(os.listdir(mount)) == ["mine", "spec"]
    assert not os.path.exists(os.path.join(home, ".claude"))

    real = run_install(clone, home)
    assert real.returncode == 0, real.stderr
    assert "skipped (name taken by a non-toolkit entry, left untouched): spec" in real.stdout
    assert sorted(os.listdir(mount)) == ["mine", "proceed", "review", "spec"]
    assert not os.path.islink(os.path.join(mount, "spec"))
    for name in ("proceed", "review"):
        assert os.path.realpath(os.path.join(mount, name)) == os.path.realpath(
            os.path.join(clone, name))
    assert snapshot(os.path.join(mount, "mine", "SKILL.md"),
                    os.path.join(mount, "spec", "notes.txt")) == user_state
    assert done_lines(run_install(clone, home)) == []


def test_repair_after_clone_move(box):
    """AC-9 / BR-10: move the clone, run --repair from the new place. Every link
    is repointed, and nothing under ~/.claude, ~/.agents or ~/bin names the old
    path — not a link target, not a file's contents."""
    clone, home, tmp = box
    assert run_install(clone, home).returncode == 0
    moved = str(tmp / "moved clone")
    shutil.move(clone, moved)
    out = run_install(moved, home, "--repair")
    assert out.returncode == 0, out.stdout + out.stderr
    assert os.readlink(os.path.join(home, ".claude", "skills")) == moved
    assert os.readlink(os.path.join(home, ".claude", "agents")) == os.path.join(moved, "agents")
    for skill in SKILLS:
        assert os.readlink(os.path.join(home, ".claude", "adlc", "skills-view", skill)) \
            == os.path.join(moved, skill)
    hits = []
    for top in (".claude", ".agents", "bin"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(home, top)):
            for name in dirnames + filenames:
                p = os.path.join(dirpath, name)
                if os.path.islink(p):
                    if clone in os.readlink(p):
                        hits.append(p)
                elif os.path.isfile(p):
                    with open(p, "rb") as fh:
                        if clone.encode() in fh.read():
                            hits.append(p)
    assert hits == []
    assert done_lines(run_install(moved, home)) == []
