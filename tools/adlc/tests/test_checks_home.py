"""REQ-654 TASK-138: the doctor checks for the view, the mount and consumers.

`skills-view` and `agents-skills-mount` run against a sandbox clone that the
real install.sh built (test_install_home.make_clone), through the real CLI, so
a remediation is proven by running it verbatim (AC-8). `consumer-sync` runs
against sandbox repos with a local bare "origin", so every baseline case
(clean-and-current, a feature branch, no remote, the plugin route) is built,
not mocked (AC-7).
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import types

import pytest

import checks
import doctor
import harness_adapter as ha
import harness_render as hr
from doctor import ROUTE_PLUGIN, ROUTE_SYMLINK, Profile, Result

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_install_home as inst  # noqa: E402  (the sandbox clone builder)
from conftest import TOOLKIT  # noqa: E402

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
        "harness:cursor", "harness:antigravity"]
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
    """A toolkit checkout whose partials/ holds forge.sh and id-alloc.sh, with the
    real adapters and render templates, cloned from a local bare origin (or with no
    remote at all)."""
    src = tmp_path / "toolkit-src"
    (src / "partials").mkdir(parents=True)
    (src / "partials" / "forge.sh").write_text("forge v2\n")
    (src / "partials" / "id-alloc.sh").write_text("alloc v1\n")
    shutil.copytree(os.path.join(TOOLKIT, "harness"), src / "harness")
    (src / "templates").mkdir()
    for name in ("permissions.yml", "hooks.yml"):
        shutil.copy2(os.path.join(TOOLKIT, "templates", name), src / "templates" / name)
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


def _settings():
    """The current render of the claude project layer."""
    adapter = ha.resolve_adapter("claude", None, TOOLKIT)
    plans, _printed = hr.plan_surfaces(adapter, "project", "/unused", TOOLKIT,
                                       surfaces=("permissions", "hooks"))
    return plans[0].content


def _consumer(root, name, forge="forge v2\n", alloc="alloc v1\n", origin=None):
    repo = root / name
    (repo / ".adlc" / "partials").mkdir(parents=True)
    (repo / ".adlc" / "partials" / "forge.sh").write_text(forge)
    (repo / ".adlc" / "partials" / "id-alloc.sh").write_text(alloc)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(_settings())
    _git(repo, "init", "-q")
    if origin:
        _git(repo, "remote", "add", "origin", origin)
    return repo


def _profile(root, route=ROUTE_SYMLINK):
    return Profile(os="Darwin", login_shell="/bin/zsh", repo_root=str(root), route=route)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    root = tmp_path / "repos"
    root.mkdir()
    monkeypatch.setenv("ADLC_REPOS_ROOT", str(root))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ADLC_HOME", str(tmp_path / "adlc-home"))
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


# --- consumer-sync: the project layer ----------------------------------------

def _no_hooks_settings():
    """The state every consumer was found in: the allowlist, no hooks block."""
    doc = json.loads(_settings())
    del doc["hooks"]
    return json.dumps(doc)


def test_consumer_sync_flags_a_settings_file_with_no_hooks(tmp_path, repos):
    """The gap render-currency:claude passes: current partials, no hooks block.
    The verdict is `adlc harness drift`'s, and fixing the file clears it."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "hookless")
    settings = repo / ".claude" / "settings.json"
    settings.write_text(_no_hooks_settings())
    assert [c for _r, c, _d in hr.drift(ha.resolve_adapter("claude", None, TOOLKIT),
                                        str(repo), TOOLKIT)] == ["stale"]
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "project layer claude .claude/settings.json stale: missing hooks block" in detail
    assert fix == "cd %s && claude -p /template-drift" % repo
    settings.write_text(_settings())
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS, detail


def test_consumer_sync_names_partials_and_project_layer_together(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "both", forge="forge v1\n")
    (repo / ".claude" / "settings.json").write_text(_no_hooks_settings())
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "1 file: forge.sh; project layer claude" in detail
    assert fix.count("\n") == 0                  # one repo, one line


def test_consumer_sync_report_separates_partials_from_layers(tmp_path, repos):
    """REQ-663 ADR-6: the migration gate needs the two kinds apart, and the doctor row
    needs them together. One walk serves both."""
    toolkit = _toolkit(tmp_path)
    fresh = _consumer(repos, "fresh")
    partial = _consumer(repos, "partial", forge="forge v1\n")
    layer = _consumer(repos, "layer")
    (layer / ".claude" / "settings.json").write_text(_no_hooks_settings())
    report = checks.consumer_sync_report(_profile(toolkit))
    by_repo = {c: (files, bool(found)) for c, files, found, _note in report.stale}
    assert by_repo[str(partial)] == (["forge.sh"], False)
    assert by_repo[str(layer)] == ([], True)
    assert str(fresh) not in by_repo
    assert not report.base.unverified
    assert sorted(report.consumers) == sorted(str(c) for c in (fresh, partial, layer))


def test_consumer_sync_report_with_no_consumer_needs_no_baseline(tmp_path, repos):
    toolkit = _toolkit(tmp_path, remote=False)
    report = checks.consumer_sync_report(_profile(toolkit))
    assert report.consumers == [] and report.base is None and report.stale == []


def test_consumer_sync_flags_a_missing_settings_file(tmp_path, repos):
    """`adlc harness drift --harness claude` exits 1 on `missing`, so this does too."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "unrendered")
    os.remove(repo / ".claude" / "settings.json")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL and ".claude/settings.json missing" in detail


def test_consumer_sync_keeps_project_additions(tmp_path, repos):
    """A customized file is a project's own choice, not stale."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "customized")
    doc = json.loads(_settings())
    doc["permissions"]["allow"].append("Bash(make deploy-preview:*)")
    (repo / ".claude" / "settings.json").write_text(json.dumps(doc))
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS, detail


def test_consumer_sync_compares_other_harnesses_only_when_opted_in(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "copilot-user")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS, detail         # no copilot file: no copilot row
    (repo / ".github" / "hooks").mkdir(parents=True)
    (repo / ".github" / "hooks" / "adlc.json").write_text("{}")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "project layer copilot .github/hooks/adlc.json stale" in detail


@pytest.mark.parametrize("worktree_only", [False, True])
def test_consumer_sync_withholds_on_a_template_off_the_baseline(tmp_path, repos, worktree_only):
    """BUG-204: a render from an unmerged template must not call consumers stale.
    The current settings match origin/main, so no verdict on them is the honest one."""
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "current")
    if not worktree_only:
        _git(toolkit, "checkout", "-q", "-b", "feat/x")
    with open(toolkit / "templates" / "hooks.yml", "a") as fh:
        fh.write("# an unmerged change\n")
    if not worktree_only:
        _git(toolkit, "commit", "-q", "-am", "branch work")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP, detail
    assert "Project layer not compared" in detail and "differ from origin/main" in detail
    assert "is stale" not in detail and fix == ""


def test_consumer_sync_still_fails_partials_when_the_layer_is_withheld(tmp_path, repos):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "older", forge="forge v1\n")
    with open(toolkit / "templates" / "hooks.yml", "a") as fh:
        fh.write("# an unmerged change\n")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "forge.sh" in detail and "Project layer not compared" in detail


def test_consumer_sync_compares_a_branch_that_leaves_the_render_alone(tmp_path, repos):
    """Off the baseline but with the same render inputs: the verdict stands."""
    toolkit = _toolkit(tmp_path)
    _git(toolkit, "checkout", "-q", "-b", "feat/x")
    (toolkit / "notes.md").write_text("unrelated\n")
    _git(toolkit, "add", "-A")
    _git(toolkit, "commit", "-q", "-m", "branch work")
    repo = _consumer(repos, "hookless")
    (repo / ".claude" / "settings.json").write_text(_no_hooks_settings())
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL and "missing hooks block" in detail


def test_consumer_sync_never_passes_a_settings_file_it_cannot_compare(tmp_path, repos):
    """Valid JSON of the wrong shape names the repo; it is not a PASS and not a crash."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "odd")
    (repo / ".claude" / "settings.json").write_text('{"permissions": ["not", "a", "map"]}')
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP, detail
    assert "Project layer not compared: %s" % repo in detail


def test_consumer_sync_never_passes_without_an_adapter(tmp_path, repos):
    """A toolkit copy with no harness/ can render nothing, so it asserts nothing."""
    toolkit = _toolkit(tmp_path)
    shutil.rmtree(toolkit / "harness")
    _git(toolkit, "add", "-A")
    _git(toolkit, "commit", "-q", "-m", "drop harness")
    _git(toolkit, "push", "-q", "origin", "HEAD")
    _consumer(repos, "fresh")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP, detail
    assert "Project layer not compared" in detail


def test_stale_project_layer_is_what_drift_exits_on(tmp_path):
    """`adlc harness drift --opted-in` and consumer-sync share the one comparison."""
    repo = tmp_path / "project"
    (repo / ".claude").mkdir(parents=True)
    settings = repo / ".claude" / "settings.json"
    settings.write_text(_settings())
    assert hr.stale_project_layer(str(repo), TOOLKIT) == []
    settings.write_text(_no_hooks_settings())
    [(name, rel, cls, details)] = hr.stale_project_layer(str(repo), TOOLKIT)
    assert (name, rel, cls) == ("claude", ".claude/settings.json", "stale")
    assert "missing hooks block" in details


# --- consumer-sync: archived repos -------------------------------------------

@pytest.fixture
def gh(tmp_path, monkeypatch):
    """A stand-in `gh` first on PATH: it logs its argv and answers from a file."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    answers = tmp_path / "gh-answers"
    answers.mkdir()
    script = bin_dir / "gh"
    script.write_text('#!/bin/sh\n'
                      'echo "$*" >> %s\n'
                      'slug=$(echo "$3" | tr / _)\n'
                      'if [ -f %s/"$slug" ]; then cat %s/"$slug"; exit 0; fi\n'
                      'echo "could not resolve to a Repository" >&2\n'
                      'exit 1\n' % (shlex.quote(str(log)), shlex.quote(str(answers)),
                                    shlex.quote(str(answers))))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]))

    def answer(slug, text):
        (answers / slug.replace("/", "_")).write_text(text)
    return types.SimpleNamespace(answer=answer, log=log, script=script)


def test_consumer_sync_skips_an_archived_repo_with_the_reason(tmp_path, repos, gh):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "fresh")
    old = _consumer(repos, "shelved", forge="forge v1\n",
                    origin="https://github.com/acme/shelved.git")
    gh.answer("acme/shelved", "true\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS, detail
    assert "1 consumer(s)" in detail
    assert "skipped %s (acme/shelved is archived on GitHub and cannot take a PR)" % old in detail
    assert fix == "" and "is stale" not in detail
    assert gh.log.read_text() == "repo view acme/shelved --json isArchived --jq .isArchived\n"


def test_consumer_sync_archive_skip_covers_the_project_layer(tmp_path, repos, gh):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "fresh")
    old = _consumer(repos, "shelved", origin="git@github.com:acme/shelved.git")
    (old / ".claude" / "settings.json").write_text(_no_hooks_settings())
    gh.answer("acme/shelved", "true\n")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS and "skipped %s" % old in detail


def test_consumer_sync_archived_repo_leaves_others_failing(tmp_path, repos, gh):
    """The skip is per repo: a live stale repo FAILs, and only it gets a fix line."""
    toolkit = _toolkit(tmp_path)
    live = _consumer(repos, "live", forge="forge v1\n", origin="https://github.com/acme/live")
    old = _consumer(repos, "shelved", forge="forge v1\n", origin="https://github.com/acme/shelved")
    gh.answer("acme/live", "false\n")
    gh.answer("acme/shelved", "true\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert fix == "cd %s && claude -p /template-drift" % live
    assert "%s is stale" % live in detail and "%s is stale" % old not in detail
    assert "skipped %s" % old in detail
    assert "archive state unknown" not in detail  # false is an answer


def test_consumer_sync_skips_when_every_consumer_is_archived(tmp_path, repos, gh):
    """Nothing was compared and found good, so the check does not read as PASS."""
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "shelved", forge="forge v1\n", origin="https://github.com/acme/shelved")
    gh.answer("acme/shelved", "true\n")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP, detail
    assert "0 consumer(s)" in detail and "archived on GitHub" in detail and fix == ""


def test_consumer_sync_asks_nothing_of_a_repo_in_sync(tmp_path, repos, gh):
    """A healthy machine makes no request; an in-sync archived repo counts as in sync."""
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "fresh", origin="https://github.com/acme/fresh")
    result, _detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.PASS
    assert not gh.log.exists()


def _unknown_gh_failure(gh, monkeypatch):
    pass                                         # no answer filed: gh exits 1


def _unknown_gh_garbage(gh, monkeypatch):
    gh.answer("acme/shelved", "maybe\n")


def _unknown_gh_empty(gh, monkeypatch):
    gh.answer("acme/shelved", "")


def _unknown_gh_absent(gh, monkeypatch):
    real = shutil.which
    monkeypatch.setattr(checks.shutil, "which",
                        lambda name, *a, **k: None if name == "gh" else real(name, *a, **k))


def _unknown_gh_hangs(gh, monkeypatch):
    gh.script.write_text("#!/bin/sh\nexec sleep 30\n")
    monkeypatch.setattr(checks, "_PROBE_TIMEOUT_SECONDS", 1)


def _unknown_gh_unstartable(gh, monkeypatch):
    gh.script.write_text("not a program")


@pytest.mark.parametrize("arrange,reason", [
    (_unknown_gh_failure, "gave no answer (exit 1)"),
    (_unknown_gh_garbage, "gave no answer (exit 0)"),
    (_unknown_gh_empty, "gave no answer (exit 0)"),
    (_unknown_gh_absent, "gh is not on PATH"),
    (_unknown_gh_hangs, "did not answer"),
    (_unknown_gh_unstartable, "did not answer"),
])
def test_consumer_sync_stays_stale_when_gh_cannot_say(tmp_path, repos, gh, monkeypatch,
                                                      arrange, reason):
    """A failed lookup is no answer: the repo FAILs and the check says why it asked."""
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "shelved", forge="forge v1\n",
                     origin="https://github.com/acme/shelved")
    arrange(gh, monkeypatch)
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL
    assert "%s is stale" % repo in detail and "archive state unknown" in detail
    assert reason in detail
    assert fix == "cd %s && claude -p /template-drift" % repo


@pytest.mark.parametrize("origin,reason", [
    (None, "no origin remote"),
    ("https://gitlab.com/acme/shelved.git", "origin is not on github.com"),
    ("https://dev.azure.com/acme/proj/_git/shelved", "origin is not on github.com"),
    ("https://notgithub.com/acme/shelved", "origin is not on github.com"),
    ("https://github.com.evil.example/acme/shelved", "origin is not on github.com"),
    ("https://github.com/--help/x", "origin is not on github.com"),
])
def test_consumer_sync_never_asks_gh_about_a_repo_it_cannot_name(tmp_path, repos, gh,
                                                                 origin, reason):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "shelved", forge="forge v1\n", origin=origin)
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL and reason in detail
    assert not gh.log.exists()


@pytest.mark.parametrize("origin,slug", [
    ("https://github.com/acme/shelved", "acme/shelved"),
    ("https://github.com/acme/shelved.git", "acme/shelved"),
    ("https://github.com/acme/shelved/", "acme/shelved"),
    ("git@github.com:acme/shelved.git", "acme/shelved"),
    ("ssh://git@github.com/acme/shelved.git", "acme/shelved"),
    ("https://github.com/acme/dotted.name.git", "acme/dotted.name"),
])
def test_consumer_sync_reads_each_origin_spelling(tmp_path, repos, gh, origin, slug):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "shelved", forge="forge v1\n", origin=origin)
    gh.answer(slug, "true\n")
    result, detail, _fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.SKIP and "%s is archived" % slug in detail


def test_consumer_sync_never_prints_a_token_from_the_origin_url(tmp_path, repos, gh):
    toolkit = _toolkit(tmp_path)
    _consumer(repos, "shelved", forge="forge v1\n",
              origin="https://x-access-token:s3cret@github.com/acme/shelved.git")
    result, detail, fix = checks.check_consumer_sync(_profile(toolkit))
    assert result is Result.FAIL and "acme/shelved" in detail
    assert "s3cret" not in detail + fix + gh.log.read_text()


def test_consumer_sync_writes_nothing_when_it_consults_gh(tmp_path, repos, gh):
    toolkit = _toolkit(tmp_path)
    repo = _consumer(repos, "shelved", forge="forge v1\n",
                     origin="https://github.com/acme/shelved")
    gh.answer("acme/shelved", "true\n")
    def tree(p):
        return sorted((os.path.relpath(os.path.join(d, f), p), os.stat(os.path.join(d, f)).st_mtime_ns)
                      for d, _dirs, files in os.walk(p) for f in files)
    before = (tree(repo), tree(toolkit))
    checks.check_consumer_sync(_profile(toolkit))
    assert (tree(repo), tree(toolkit)) == before
