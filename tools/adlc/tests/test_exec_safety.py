"""Validators, the neutral environment, the manifest, the checksums (REQ-659 BR-17, BR-23)."""

import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_safety as es  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()


def git(cwd, *args, env=None):
    subprocess.check_call(["git", "-C", str(cwd)] + list(args), env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text('[user]\n\tname = op\n\temail = op@example.invalid\n'
                                     '[filter "lfs"]\n\tclean = cat\n[core]\n\tpager = cat\n'
                                     '[credential]\n\thelper = store\n')
    (home / ".ssh").mkdir()
    (home / ".ssh" / "config").write_text("Host x\n  HostName y\n")
    bare = tmp_path / "acme" / "w.git"
    bare.parent.mkdir()
    subprocess.check_call(["git", "init", "-q", "--bare", "-b", "main", str(bare)])
    work = tmp_path / "repo"
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(work)])
    (work / "a.txt").write_text("a\n")
    git(work, "add", "-A")
    git(work, "-c", "user.email=t@e.st", "-c", "user.name=t", "commit", "-qm", "seed")
    git(work, "remote", "add", "origin", str(bare))
    git(work, "push", "-q", "origin", "main")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    environ = {"HOME": str(home), "PATH": os.environ["PATH"], "GIT_SSH_COMMAND": "evil",
               "PYTHONPATH": "/evil", "GIT_DIR": "/evil", "ADLC_FORGE_MOCK": "1"}
    box = es.Toolbox(str(run_dir), TOOLKIT, environ)
    box.prepare()
    box.register_tree(str(work))
    return box, work, home


def test_validators():
    assert es.valid_req("REQ-659") == "REQ-659"
    assert es.valid_branch("feat/REQ-659-exec") == "feat/REQ-659-exec"
    for bad in ("REQ-1", "REQ-659; rm", "../REQ-659", "", None):
        with pytest.raises(es.SafetyError):
            es.valid_req(bad)
    for bad in ("feat/../x", "-x", "feat/x; rm", "x/", "$(touch y)"):
        with pytest.raises(es.SafetyError):
            es.valid_branch(bad)
    assert es.parse_pr_url("https://github.com/acme/w/pull/12", "github.com") == ("acme", "w", 12)
    with pytest.raises(es.SafetyError, match="prUrl"):
        es.parse_pr_url("https://evil.example/acme/w/pull/12", "github.com")
    with pytest.raises(es.SafetyError, match="prUrl"):
        es.parse_pr_url("https://github.com/acme/w/pull/12;rm", "github.com")


def test_origin_parts():
    assert es.origin_parts("git@github.com:acme/w.git") == ("github.com", "acme", "w")
    assert es.origin_parts("https://github.com/acme/w") == ("github.com", "acme", "w")
    assert es.origin_parts("ssh://git@host.example/acme/w.git") == ("host.example", "acme", "w")
    assert es.origin_parts("/tmp/x/acme/w.git") == ("", "acme", "w")


def test_env_is_neutral(repo):
    box, _, _ = repo
    env = box.env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.path.join(box.run_dir, "gitconfig")
    keys = [env["GIT_CONFIG_KEY_%d" % i] for i in range(int(env["GIT_CONFIG_COUNT"]))]
    for key in ("core.hooksPath", "core.fsmonitor", "core.sshCommand", "credential.helper",
                "core.attributesFile", "commit.gpgsign", "log.showSignature",
                "protocol.ext.allow"):
        assert key in keys
    assert "GIT_SSH_COMMAND" not in env and "PYTHONPATH" not in env and "GIT_DIR" not in env
    assert env["PATH"].startswith(os.path.join(box.run_dir, "bin"))
    assert env["GH_CONFIG_DIR"] == os.path.join(box.run_dir, "gh")


def test_gitconfig_snapshot_drops_drivers(repo):
    box, _, _ = repo
    text = open(os.path.join(box.run_dir, "gitconfig")).read()
    assert "op@example.invalid" in text
    assert "filter" not in text and "pager" not in text
    assert box.helpers == ["store"]


def test_planted_hook_and_config(repo, tmp_path):
    box, work, _ = repo
    sentinel = tmp_path / "sentinel"
    hook = work / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\ntouch %s\n" % sentinel)
    hook.chmod(0o755)
    with pytest.raises(es.RuleBViolation, match="hooks/pre-push"):
        box.git(str(work), ["push", "origin", "HEAD:refs/heads/x"])
    assert not sentinel.exists()
    assert box.halted
    with pytest.raises(es.RuleBViolation):
        box.git(str(work), ["status"])
    box.halted = False
    box.check_gitdir = lambda repo: True
    git(work, "config", "core.sshCommand", "touch %s" % sentinel)
    git(work, "config", "credential.helper", "!touch %s" % sentinel)
    git(work, "config", "core.hooksPath", str(work / ".git" / "hooks"))
    res = box.git(str(work), ["push", "origin", "HEAD:refs/heads/x"])
    assert res.returncode == 0, res.stderr
    assert not sentinel.exists()
    helpers = box.git(str(work), ["config", "--get-all", "credential.helper"]).stdout
    assert helpers.strip().splitlines()[-1] == "store"
    records = [ln for ln in open(box.log_path) if '"git"' in ln and "push" in ln]
    assert records and all("GIT_CONFIG_GLOBAL" in r and "GIT_CONFIG_COUNT" in r for r in records)


def test_upstream_write_does_not_trip_the_checksum(repo):
    box, work, _ = repo
    git(work, "checkout", "-q", "-b", "feat/x")
    git(work, "push", "-q", "-u", "origin", "feat/x")
    box.verify_gitdir(str(work))


def test_every_push_and_fetch_names_a_refspec(repo):
    box, work, _ = repo
    with pytest.raises(ValueError, match="refspec"):
        box.git(str(work), ["fetch", "origin"])
    with pytest.raises(ValueError, match="refspec"):
        box.git(str(work), ["push", "--force"])


def test_filters_and_snapshots(repo, tmp_path):
    box, work, home = repo
    sentinel = tmp_path / "leak"
    with open(str(home / ".gitconfig"), "a") as fh:
        fh.write('[filter "leak"]\n\tclean = touch %s\n[core]\n\tfsmonitor = touch %s\n'
                 % (sentinel, sentinel))
    with open(str(home / ".ssh" / "config"), "a") as fh:
        fh.write("Host *\n  ProxyCommand touch %s\n" % sentinel)
    (work / ".git" / "info" / "attributes").write_text("* filter=leak\n")
    with pytest.raises(es.RuleBViolation, match="info/attributes"):
        box.git(str(work), ["status"])
    box.halted = False
    box.check_gitdir = lambda repo: True
    (work / "a.txt").write_text("changed\n")
    assert box.git(str(work), ["add", "-A"]).returncode == 0
    assert not sentinel.exists()
    assert "ProxyCommand" not in open(os.path.join(box.run_dir, "ssh_config")).read()
    assert "leak" not in open(os.path.join(box.run_dir, "gitconfig")).read()


def install_copy(tmp_path):
    root = tmp_path / "install"
    for tree in es.INSTALL_TREES:
        shutil.copytree(os.path.join(TOOLKIT, tree), str(root / tree),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (root / "sprint").mkdir()
    shutil.copy(os.path.join(TOOLKIT, "sprint", "SKILL.md"), str(root / "sprint" / "SKILL.md"))
    return root


def test_manifest_catches_edits(tmp_path):
    root = install_copy(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    bindir = tmp_path / "shim"
    bindir.mkdir()
    fake_git = bindir / "gh"
    fake_git.write_text("#!/bin/sh\nexit 0\n")
    fake_git.chmod(0o755)
    environ = {"HOME": str(tmp_path), "PATH": "%s:%s" % (bindir, os.environ["PATH"])}
    box = es.Toolbox(str(run_dir), str(root), environ)
    box.prepare()
    box.verify_manifest()
    assert box.tools["gh"] == str(fake_git)
    target = root / "partials" / "forge.sh"
    keep = target.read_text()
    target.write_text(keep + "\n# planted\n")
    with pytest.raises(es.RuleBViolation, match="partials/forge.sh"):
        box.verify_manifest()
    box.halted = False
    target.write_text(keep)
    box.verify_manifest()
    planted = root / "tools" / "adlc" / "extra.py"
    planted.write_text("print(1)\n")
    with pytest.raises(es.RuleBViolation, match="extra.py"):
        box.verify_manifest()
    planted.unlink()
    box.halted = False
    fake_git.write_text("#!/bin/sh\nexit 1\n")
    with pytest.raises(es.RuleBViolation, match="resolved binary gh"):
        box.verify_manifest()


def test_toolbox_round_trips(repo):
    box, work, _ = repo
    again = es.Toolbox.load(box.run_dir, TOOLKIT, box.environ)
    assert again.tools == box.tools and again.helpers == box.helpers
    assert again.git(str(work), ["status", "--short"]).returncode == 0


def test_partial_is_sourced_from_the_install(repo):
    box, work, _ = repo
    planted = work / ".adlc" / "partials"
    planted.mkdir(parents=True)
    (planted / "forge.sh").write_text("adlc_forge_pr_view() { echo PLANTED; }\n")
    (planted / "adlc-home.sh").write_text("echo PLANTED\n")
    res = box.forge("adlc_forge_branch_protection", ["main"], str(work))
    assert res.stdout.strip() == "protected", res.stderr
    assert "PLANTED" not in res.stdout + res.stderr
