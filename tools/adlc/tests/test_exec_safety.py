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


# ---- REQ-662 review fix 7: the engine's own gitdir writes are not tampering ------------------
def _engine_writes(box, work, tmp_path):
    """What a file-rendering batch writes into the common gitdir: the extension in the main
    config, and a working copy whose ``config.worktree`` names an excludes file under the
    engine's state root. Returns ``(working copy, excludes file)``."""
    import exec_ledger as el
    git(work, "config", "--local", "extensions.worktreeConfig", "true")
    wt = tmp_path / "wt"
    git(work, "worktree", "add", "-q", "-b", "fx", str(wt))
    excludes = os.path.join(el.exec_root(box.environ), "0" * 32, "excludes-000000000000")
    git(wt, "config", "--worktree", "core.excludesFile", excludes)
    return wt, excludes


def test_the_gitdir_digest_ignores_the_engines_own_writes(repo, tmp_path):
    """A second supervisor's box on the same repository: the extension the pre-flight sets,
    a working copy's core.excludesFile under the engine's state root, the empty
    config.worktree a restore leaves, and the removal of such a working copy each leave its
    checksum unchanged, so its run is not blocked. Without a state root the digest is
    today's, which counts every byte."""
    import exec_ledger as el
    box, work, _ = repo
    common = str(work / ".git")
    state = el.exec_root(box.environ)
    before = es.gitdir_digest(common, state)
    assert before == es.gitdir_digest(common)       # nothing to ignore yet: the same digest
    wt, excludes = _engine_writes(box, work, tmp_path)
    assert es.gitdir_digest(common, state) == before
    assert es.gitdir_digest(common) != before       # the default keeps today's digest
    box.verify_gitdir(str(work))
    assert box.tree_digest(common) == before
    git(wt, "config", "--worktree", "--unset", "core.excludesFile")
    assert es.gitdir_digest(common, state) == before
    box.verify_gitdir(str(work))
    git(wt, "config", "--worktree", "core.excludesFile", excludes)
    git(work, "worktree", "remove", "--force", str(wt))
    assert es.gitdir_digest(common, state) == before
    box.verify_gitdir(str(work))
    again = es.Toolbox.load(box.run_dir, TOOLKIT, box.environ)
    again.verify_gitdir(str(work))


@pytest.mark.parametrize("change", ["excludes-elsewhere", "excludes-dotdot", "second-key",
                                    "comment", "hooks-path", "other-extension"])
def test_the_gitdir_digest_still_sees_what_the_engine_does_not_write(repo, tmp_path, change):
    """Anything but the engine's own writes still changes the digest: core.excludesFile
    pointing outside the state root, a second key in config.worktree, core.hooksPath in the
    main config, and any other extensions.* key."""
    import exec_ledger as el
    box, work, _ = repo
    common = str(work / ".git")
    state = el.exec_root(box.environ)
    wt, excludes = _engine_writes(box, work, tmp_path)
    before = es.gitdir_digest(common, state)
    config_wt = os.path.join(common, "worktrees", os.path.basename(str(wt)), "config.worktree")
    if change == "excludes-elsewhere":
        git(wt, "config", "--worktree", "core.excludesFile", str(tmp_path / "elsewhere"))
    elif change == "excludes-dotdot":
        git(wt, "config", "--worktree", "core.excludesFile",
            os.path.join(state, "..", "..", "elsewhere"))
    elif change == "second-key":
        git(wt, "config", "--worktree", "core.hooksPath", str(tmp_path / "hooks"))
    elif change == "comment":
        with open(config_wt, "a", encoding="utf-8") as fh:
            fh.write("# planted\n")
    elif change == "hooks-path":
        git(work, "config", "--local", "core.hooksPath", str(tmp_path / "hooks"))
    else:
        git(work, "config", "--local", "extensions.preciousObjects", "true")
    assert es.gitdir_digest(common, state) != before
    with pytest.raises(es.RuleBViolation, match="common gitdir checksum mismatch"):
        box.verify_gitdir(str(work))


# ---- confirmation pass: what git itself rejects, or what is not the engine's, still counts ----
#: What `git config --local extensions.worktreeConfig true` writes, the one form left out.
ENGINE_EXTENSION = "[extensions]\n\tworktreeConfig = true\n"


def _main_config(work, text):
    """The main config with the engine's extension block swapped for ``text``."""
    path = os.path.join(str(work), ".git", "config")
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    assert body.count(ENGINE_EXTENSION) == 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body.replace(ENGINE_EXTENSION, text))


@pytest.mark.parametrize("change", [
    "worktree-symlink", "state-sibling", "trailing-comment", "unknown-escape",
    "unterminated-quote", "relative-path", "two-excludes", "core-then-section", "spaced-core",
    "key-on-header", "continuation", "worktree-config-false", "spaced-header",
    "spaced-header-right", "unterminated-extension", "extension-comment"])
def test_the_gitdir_digest_counts_every_spelling_the_engine_does_not_write(repo, tmp_path,
                                                                          change):
    """Each of these is a spelling the engine never writes: some git refuses outright (a spaced
    section header, an unterminated quote, an unknown escape), so a model could break every git
    call on the repository; others turn the engine's hiding off (`worktreeConfig = false`) or
    name an excludes file that is not the engine's. Each still changes the digest."""
    import exec_ledger as el
    box, work, _ = repo
    common = str(work / ".git")
    state = el.exec_root(box.environ)
    wt, excludes = _engine_writes(box, work, tmp_path)
    before = es.gitdir_digest(common, state)
    config_wt = os.path.join(common, "worktrees", os.path.basename(str(wt)), "config.worktree")
    worktree = {
        "trailing-comment": "[core]\n\texcludesFile = %s # mine\n" % excludes,
        "unknown-escape": "[core]\n\texcludesFile = %s\\q\n" % excludes,
        "unterminated-quote": '[core]\n\texcludesFile = "%s\n' % excludes,
        "relative-path": "[core]\n\texcludesFile = adlc/exec/excludes\n",
        "two-excludes": "[core]\n\texcludesFile = %s\n\texcludesFile = %s\n" % (excludes,
                                                                                excludes),
        "core-then-section": "[core]\n\texcludesFile = %s\n[user]\n\tname = x\n" % excludes,
        "spaced-core": "[ core ]\n\texcludesFile = %s\n" % excludes,
        "state-sibling": "[core]\n\texcludesFile = %s-evil/excludes\n" % state,
    }
    main = {
        "key-on-header": "[extensions] worktreeConfig = true\n",
        "continuation": "[extensions]\n\tworktreeConfig = tr\\\nue\n",
        "worktree-config-false": "[extensions]\n\tworktreeConfig = false\n",
        "spaced-header": "[ extensions ]\n\tworktreeConfig = true\n",
        "spaced-header-right": "[extensions ]\n\tworktreeConfig = true\n",
        "unterminated-extension": '[extensions]\n\tworktreeConfig = "true\n',
        "extension-comment": "[extensions]\n\tworktreeConfig = true # mine\n",
    }
    if change == "worktree-symlink":
        # The engine's own bytes, but through a link the engine never writes.
        target = tmp_path / "elsewhere.worktree"
        with open(config_wt, encoding="utf-8") as fh:
            target.write_text(fh.read())
        os.unlink(config_wt)
        os.symlink(str(target), config_wt)
    elif change in worktree:
        with open(config_wt, "w", encoding="utf-8") as fh:
            fh.write(worktree[change])
    else:
        _main_config(work, main[change])
    assert es.gitdir_digest(common, state) != before, change
    with pytest.raises(es.RuleBViolation, match="common gitdir checksum mismatch"):
        box.verify_gitdir(str(work))


@pytest.mark.parametrize("value", ["", " = yes", " = on", " = 1", ' = "true"', " = TRUE",
                                   "=true", " = true  "])
def test_the_gitdir_digest_leaves_out_any_true_spelling_of_the_extension(repo, tmp_path,
                                                                          value):
    """The must-not-fire half: `worktreeConfig` with a value git reads as boolean true, in any
    of its spellings (a bare key is true), under an `[extensions]` header in any case, is the
    engine's setting, and leaves the digest as it was without it."""
    import exec_ledger as el
    box, work, _ = repo
    common = str(work / ".git")
    state = el.exec_root(box.environ)
    _engine_writes(box, work, tmp_path)
    before = es.gitdir_digest(common, state)
    _main_config(work, "[Extensions]\n\tWorktreeConfig%s\n" % value)
    assert es.gitdir_digest(common, state) == before
    assert es.gitdir_digest(common) != before
