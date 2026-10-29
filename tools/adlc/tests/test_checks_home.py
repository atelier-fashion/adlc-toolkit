"""REQ-654 TASK-138: the doctor checks for the view, the mount and consumers.

`skills-view` and `agents-skills-mount` run against a sandbox clone that the
real install.sh built (test_install_home.make_clone), through the real CLI, so
a remediation is proven by running it verbatim (AC-8). `consumer-sync` runs
against sandbox repos with a local bare "origin", so every baseline case
(clean-and-current, a feature branch, no remote, the plugin route) is built,
not mocked (AC-7).
"""

import os
import shutil
import subprocess
import sys

import pytest

import checks
import doctor
from doctor import ROUTE_PLUGIN, ROUTE_SYMLINK, Profile, Result

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_install_home as inst  # noqa: E402  (the sandbox clone builder)

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "init.defaultBranch=main"]


def _doctor(clone, home, checks_arg, **extra):
    env = {"HOME": home, "PATH": inst.SYSTEM_PATH}
    env.update(extra)
    return subprocess.run([sys.executable, os.path.join(clone, "tools", "adlc", "adlc.py"),
                           "doctor", "--checks", checks_arg],
                          cwd=home, env=env, capture_output=True, text=True, timeout=120)


def _row(out, cid):
    rows = [l for l in out.stdout.splitlines() if l.startswith("[") and "] %s " % cid in l]
    assert len(rows) == 1, out.stdout
    return rows[0]


def _fixes(out):
    return [l.split("-> fix: ", 1)[1] for l in out.stdout.splitlines() if "-> fix: " in l]


@pytest.fixture
def installed(tmp_path):
    clone = inst.make_clone(str(tmp_path / "clone dir"))
    home = inst.make_home(str(tmp_path / "home"))
    assert inst.run_install(clone, home).returncode == 0
    return clone, home, tmp_path


# --- AC-8: the registry and the view ---------------------------------------

def test_registry_lists_new_checks():
    ids = [c.id for c in checks.REGISTRY]
    for cid in ("skills-view", "agents-skills-mount", "consumer-sync"):
        assert cid in ids
    assert [i for i in ids if i.startswith("harness:")] == [
        "harness:claude", "harness:copilot", "harness:codex", "harness:gemini",
        "harness:cursor"]
    assert "claude-code" not in ids


def test_skills_view_fail_then_fix(installed):
    """Deleting one view link FAILs skills-view; its remediation, run verbatim,
    returns it to PASS. agents-skills-mount passes alongside."""
    clone, home, _tmp = installed
    ok = _doctor(clone, home, "skills-view,agents-skills-mount")
    assert _row(ok, "skills-view").startswith("[PASS]"), ok.stdout
    assert "after the next install.sh run" in _row(ok, "skills-view")
    assert _row(ok, "agents-skills-mount").startswith("[PASS]"), ok.stdout
    os.remove(os.path.join(home, ".claude", "adlc", "skills-view", "review"))
    bad = _doctor(clone, home, "skills-view")
    assert _row(bad, "skills-view").startswith("[FAIL]"), bad.stdout
    assert "review: no link" in bad.stdout
    assert bad.returncode == 1
    fixes = _fixes(bad)
    assert len(fixes) == 1
    # The fix as an operator pastes it: any directory, their own HOME and USER.
    run = subprocess.run(["sh", "-c", fixes[0]], cwd="/",
                         env={"HOME": home, "PATH": inst.SYSTEM_PATH,
                              "USER": os.environ.get("USER", "u")},
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    again = _doctor(clone, home, "skills-view")
    assert _row(again, "skills-view").startswith("[PASS]"), again.stdout


def test_skills_view_flags_a_dangling_and_a_stale_link(installed):
    clone, home, _tmp = installed
    view = os.path.join(home, ".claude", "adlc", "skills-view")
    os.remove(os.path.join(view, "spec"))
    os.symlink(os.path.join(clone, "gone"), os.path.join(view, "spec"))
    os.symlink(os.path.join(clone, "tools"), os.path.join(view, "tools"))
    out = _doctor(clone, home, "skills-view")
    row = _row(out, "skills-view")
    assert row.startswith("[FAIL]") and "spec: dangling" in row and "tools: not a skill" in row


def test_agents_mount_fails_when_absent_and_names_user_entries(installed):
    clone, home, _tmp = installed
    mount = os.path.join(home, ".agents", "skills")
    os.remove(mount)
    absent = _doctor(clone, home, "agents-skills-mount")
    assert _row(absent, "agents-skills-mount").startswith("[FAIL]")
    assert "is absent" in absent.stdout
    # A directory the user owns, with their own `spec`: PASS once install.sh has
    # linked the rest, and `spec` is listed, not failed.
    os.makedirs(os.path.join(mount, "spec"))
    assert inst.run_install(clone, home).returncode == 0
    mine = _doctor(clone, home, "agents-skills-mount")
    row = _row(mine, "agents-skills-mount")
    assert row.startswith("[PASS]") and "left alone: spec" in row


def test_symlink_checks_cover_both_homes(tmp_path):
    """BR-6 / ADR-6: under an overridden ADLC_HOME, skills-symlink and
    agents-symlink check Claude Code's mount AND the home's pair. The benign
    default (one location) is the rest of the suite."""
    clone = inst.make_clone(str(tmp_path / "clone dir"))
    home = inst.make_home(str(tmp_path / "home"))
    x = str(tmp_path / "x home")
    assert inst.run_install(clone, home, adlc_home=x).returncode == 0
    ok = _doctor(clone, home, "skills-symlink,agents-symlink,skills-view,agents-skills-mount,counters",
                 ADLC_HOME=x)
    assert ok.returncode == 0, ok.stdout
    assert os.path.join(home, ".claude", "skills") in _row(ok, "skills-symlink")
    assert os.path.join(x, "skills") in _row(ok, "skills-symlink")
    os.remove(os.path.join(x, "agents"))
    bad = _doctor(clone, home, "agents-symlink", ADLC_HOME=x)
    row = _row(bad, "agents-symlink")
    assert row.startswith("[FAIL]") and os.path.join(x, "agents") in row
    assert os.path.join(home, ".claude", "agents") + " does not" not in row


def test_view_checks_skip_on_the_plugin_route(tmp_path):
    profile = Profile(os="Darwin", login_shell="/bin/zsh", repo_root=str(tmp_path),
                      route=ROUTE_PLUGIN)
    outcomes = doctor.run_checks(profile, only=["skills-view", "agents-skills-mount"])
    assert [o.result for o in outcomes] == [Result.SKIP, Result.SKIP]
    assert all("plugin route" in o.detail for o in outcomes)


# --- AC-7: consumer-sync ----------------------------------------------------

def _git(cwd, *args):
    subprocess.run(GIT + ["-C", str(cwd)] + list(args), check=True,
                   capture_output=True, text=True)


def _toolkit(tmp_path, remote=True):
    """A toolkit checkout whose partials/ holds forge.sh and id-alloc.sh, cloned
    from a local bare origin (or with no remote at all)."""
    src = tmp_path / "toolkit-src"
    (src / "partials").mkdir(parents=True)
    (src / "partials" / "forge.sh").write_text("forge v2\n")
    (src / "partials" / "id-alloc.sh").write_text("alloc v1\n")
    _git(src, "init", "-q")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "toolkit")
    if not remote:
        return src
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(bare)], check=True)
    clone = tmp_path / "toolkit"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    return clone


def _consumer(root, name, forge="forge v2\n", alloc="alloc v1\n"):
    repo = root / name
    (repo / ".adlc" / "partials").mkdir(parents=True)
    (repo / ".adlc" / "partials" / "forge.sh").write_text(forge)
    (repo / ".adlc" / "partials" / "id-alloc.sh").write_text(alloc)
    _git(repo, "init", "-q")
    return repo


def _profile(root, route=ROUTE_SYMLINK):
    return Profile(os="Darwin", login_shell="/bin/zsh", repo_root=str(root), route=route)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    root = tmp_path / "repos"
    root.mkdir()
    monkeypatch.setenv("ADLC_REPOS_ROOT", str(root))
    return root


def test_consumer_sync_stale_then_pass(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "fresh")
    stale = _consumer(repos, "older", forge="forge v1\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "%s is stale (1 file: forge.sh)" % stale in detail
    assert "fresh" not in detail
    assert fix == "cd %s && claude -p /template-drift" % stale
    assert "the working tree" in detail          # clean and current: the working tree
    (stale / ".adlc" / "partials" / "forge.sh").write_text("forge v2\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS, detail
    assert "2 consumer(s)" in detail and fix == ""


def test_consumer_sync_counts_a_missing_partial(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "partial")
    os.remove(repo / ".adlc" / "partials" / "id-alloc.sh")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL and "id-alloc.sh (missing)" in detail


def test_consumer_sync_feature_branch_baseline(tmp_path, repos):
    """A clone on a feature branch that changes partials/ is named, and the
    consumers are compared against origin/main, not the branch: the consumer
    that matches origin is in sync, and one that matches the branch is stale."""
    toolkit = _toolkit(tmp_path)
    _git(toolkit, "checkout", "-q", "-b", "feat/x")
    (toolkit / "partials" / "forge.sh").write_text("forge v3 (unmerged)\n")
    _git(toolkit, "commit", "-q", "-am", "branch work")
    _consumer(repos, "matches-origin")
    branchy = _consumer(repos, "matches-branch", forge="forge v3 (unmerged)\n")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "Compared against origin/main" in detail
    assert "baseline feat/x" in detail
    assert "%s is stale (1 file: forge.sh)" % branchy in detail
    assert "matches-origin is stale" not in detail


def test_consumer_sync_unverified_baseline(tmp_path, repos):
    """No origin ref: unverified-baseline, a SKIP that asserts no stale."""
    toolkit = _toolkit(tmp_path, remote=False)
    _consumer(repos, "older", forge="forge v1\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP
    assert detail.startswith("unverified-baseline:")
    assert "is stale" not in detail and fix == ""


def test_consumer_sync_skips_with_no_consumer(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    (repos / "not-a-repo" / ".adlc" / "partials").mkdir(parents=True)
    no_partials = repos / "plain"
    no_partials.mkdir()
    _git(no_partials, "init", "-q")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP and "no consumer under" in detail


def test_consumer_sync_never_counts_the_toolkit(tmp_path, monkeypatch):
    """Benign: the toolkit itself sits under the repos root and is not a consumer."""
    toolkit = _toolkit(tmp_path)
    (toolkit / ".adlc" / "partials").mkdir(parents=True)
    (toolkit / ".adlc" / "partials" / "forge.sh").write_text("anything\n")
    monkeypatch.setenv("ADLC_REPOS_ROOT", str(tmp_path))
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP, detail


def test_consumer_sync_plugin_route_baseline(tmp_path, repos):
    """No .git: the baseline is `adlc plugin <version>`, the copy compared directly,
    and the remediation names /adlc:template-drift."""
    copy = tmp_path / "cache-copy"
    (copy / "partials").mkdir(parents=True)
    (copy / "partials" / "forge.sh").write_text("forge v2\n")
    (copy / ".claude-plugin").mkdir()
    (copy / ".claude-plugin" / "plugin.json").write_text('{"name": "adlc", "version": "9.9.9"}')
    stale = _consumer(repos, "older", forge="forge v1\n")
    result, detail, fix = checks.check_consumer_sync(_profile(copy, route=ROUTE_PLUGIN))
    assert result is Result.FAIL
    assert "adlc plugin 9.9.9" in detail
    assert fix == "cd %s && claude -p /adlc:template-drift" % stale


def test_consumer_sync_writes_nothing(tmp_path, repos):
    """Read-only: no consumer file and no .git of the toolkit changes."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "older", forge="forge v1\n")
    def tree(p):
        return sorted((os.path.relpath(os.path.join(d, f), p), os.stat(os.path.join(d, f)).st_mtime_ns)
                      for d, _dirs, files in os.walk(p) for f in files)
    before = (tree(repo), tree(toolkit))
    checks.check_consumer_sync(_profile(toolkit))
    assert (tree(repo), tree(toolkit)) == before
