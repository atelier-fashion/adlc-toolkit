"""fence-run: the one admitted entry point (REQ-682 BR-3, BR-5, BR-6, BR-9, BR-11, AC-5, AC-6),
accepting the union of every exec-capable adapter's runner routes (REQ-662 ADR-8, ADR-9)."""

import io
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_adapter as ea  # noqa: E402
import exec_matcher as em  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
SHIM = os.path.join(TOOLKIT, "tools", "adlc", "fence-run")

#: A value for every argument a runner fence takes: what a well-behaved model would pass.
SAMPLES = {
    "worktree": "{cwd}", "root": "{cwd}", "spec": "{cwd}/spec.md", "state": "{cwd}/state.json",
    "tasks": "{cwd}/tasks", "integrationBranch": "main", "branch": "feat/REQ-901-thing",
    "component": "adlc/proceed", "task": "TASK-901", "mode": "", "phase": "1", "attempt": "1",
    "loops": "0", "terminal": "blocked", "reason": "", "repo": "o/r", "title": "A title",
    "pr": "101", "prNumber": "101", "id": "REQ-901", "slug": "a-slug",
    "mark": "adlc-transcript-mark-0123456789abcdef", "ids": "NO_ENTRY", "req": "REQ-901",
    "req_ids": "", "flag": "{cwd}/adlc-skill-flag.abc123", "REQ": "REQ-901", "LESSON_NUM": "901",
    "FINAL_TITLE": "A title",
}
FILE_SAMPLES = {"NEW_BODY": "A body.\n", "lane_escalated": "a reason", "MAPPER_PATHS": "a/b.py\n"}
HOSTILE = ("$(touch {s})", "`touch {s}`", "x;touch {s}", "x\ntouch {s}", "--force", "main",
           "HEAD:main", "../x", "-x")


MATCHER_NONE = os.path.join(HERE, "fixtures", "harness", "fake-exec-file.yml")
PUSH_KEY = "proceed/phase-0-setup.md#6"


@pytest.fixture(scope="module")
def records():
    return fc.census(TOOLKIT, ea.load("claude", TOOLKIT))


def memo_census(monkeypatch):
    """Memoize ``fc.census`` per root and adapter: every fence-run call recomputes it otherwise,
    which is the property ``test_census_recomputed_every_call`` holds; here it only costs
    time."""
    real = fc.census
    memo = {}

    def census(root, adapter=None):
        key = (root, adapter.name if adapter is not None else None)
        if key not in memo:
            memo[key] = real(root, adapter)
        return memo[key]
    monkeypatch.setattr(fc, "census", census)


@pytest.fixture
def cached(monkeypatch, records):
    memo_census(monkeypatch)
    return records


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """A toolkit copy with two exec-capable adapters: ``claude`` (matcher modelled) and
    ``fake-exec-file`` (``matcher: none``), and each one's census."""
    root = rs.toolkit_copy(str(tmp_path_factory.mktemp("two") / "tk"))
    shutil.copy(MATCHER_NONE, os.path.join(root, "harness"))
    return root, {a.name: fc.census(root, a) for a in fc.exec_adapters(root)}


@pytest.fixture(scope="module")
def claude_only(tmp_path_factory):
    """A toolkit copy whose one exec-capable adapter is ``claude``. In the real tree codex is
    exec-capable too (REQ-662 stage 1), routes every fence claude runs `direct` through the
    runner, and the runner accepts the union (ADR-8), so no real-tree fence reads `direct`
    to fence-run. Here one does."""
    root = rs.toolkit_copy(str(tmp_path_factory.mktemp("claude-only") / "tk"))
    os.remove(os.path.join(root, "harness", "codex.yml"))
    os.remove(os.path.join(root, fc.golden_path("codex")))
    assert [a.name for a in fc.exec_adapters(root)] == ["claude"]
    return root


def _by_route(records, route):
    return [r for r in records if r["route"] == route]


def _run(fid, argv, cwd, environ=None, root=TOOLKIT):
    err = io.StringIO()
    env = dict(os.environ if environ is None else environ)
    rc = fr.run(fid, argv, root, environ=env, cwd=str(cwd), err=err)
    return rc, err.getvalue()


def _sample_argv(rec, cwd, hostile=None, target=None):
    argv = []
    for arg in rec["placeholders"]:
        if arg in FILE_SAMPLES:
            path = os.path.join(str(cwd), "arg-%s.txt" % arg)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(hostile if arg == target and hostile is not None else FILE_SAMPLES[arg])
            argv += ["--arg-file", "%s=%s" % (arg, os.path.basename(path))]
        else:
            value = hostile if arg == target and hostile is not None else SAMPLES[arg]
            argv += ["--arg", "%s=%s" % (arg, value.replace("{cwd}", str(cwd)))]
    return argv


@pytest.fixture
def wc(tmp_path):
    path = tmp_path / "wc"
    (path / ".adlc" / "specs").mkdir(parents=True)
    return path


#: The branch a forge-running test's working copy has checked out. PR 101, the PR every
#: sample call passes, is open on it in that test's mock store: a fence that binds a PR number
#: runs only for the PR of the branch checked out where the runner is called (REQ-719 ADR-3).
PR_BRANCH = SAMPLES["branch"]


def mock_pr(number, head, **fields):
    """One PR record of the stateful mock forge's store (``tools/adlc/forge_mock.py``)."""
    pr = {"number": number, "url": "https://mock.forge/acme/widgets/pull/%d" % number,
          "state": "OPEN", "mergedAt": "", "body": "body of %d" % number,
          "title": "title of %d" % number, "isDraft": True,
          "createdAt": "2026-11-20T00:00:00Z", "headRefName": head, "baseRefName": "main",
          "isCrossRepository": False, "mergeCommit": ""}
    pr.update(fields)
    return pr


def pr_store(path, prs=None):
    """A mock forge store whose PR 101 is open on :data:`PR_BRANCH`, or holding ``prs``."""
    os.makedirs(str(path), exist_ok=True)
    prs = [mock_pr(101, PR_BRANCH)] if prs is None else prs
    with open(os.path.join(str(path), "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"remote": "", "owner": "acme", "name": "widgets"}, fh)
    with open(os.path.join(str(path), "prs.json"), "w", encoding="utf-8") as fh:
        json.dump({"next": max([p["number"] for p in prs] + [100]) + 1, "prs": prs}, fh)
    return str(path)


def repo_wc(path, branch=PR_BRANCH, commit=False):
    """``path`` made a git working copy with ``branch`` checked out (unborn unless
    ``commit``): what the runner's branch read and PR read need of it."""
    os.makedirs(str(path), exist_ok=True)
    _git("init", "-q", str(path))
    _git("-C", str(path), "symbolic-ref", "HEAD", "refs/heads/%s" % branch)
    if commit:
        _git("-C", str(path), "commit", "-q", "--allow-empty", "-m", "a")
    return path


def forge_env(store, **extra):
    """The caller's environment for a run against the stateful mock forge in ``store``."""
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_FORGE_MOCK_STORE=str(store),
               ADLC_DISABLE_DELEGATE="1", **extra)
    for key in ("ADLC_FORGE_MOCK_SCENARIO", "ADLC_EXEC_RUN", "ADLC_FORGE_PROVIDER_OVERRIDE"):
        env.pop(key, None)
    return env


# ------------------------------------------------------------------------ refusals (BR-9)
def test_refusal_is_one_loud_line_exit_3(cached, wc, tmp_path, claude_only):
    sentinel = tmp_path / "S"
    direct = _by_route(cached, "direct")[0]["id"]
    engine = _by_route(cached, "engine")[0]["id"]
    excised = _by_route(cached, "excised")[0]["id"]
    runner = _by_route(cached, "runner")[0]["id"]
    stale = runner.rsplit(":", 1)[0] + ":00000000"
    for fid, why, root in ((direct, "route is direct", claude_only),
                           (engine, "route is engine", TOOLKIT),
                           (excised, "route is excised", TOOLKIT),
                           (stale, "changed since it was shown", TOOLKIT),
                           ("validate/SKILL.md#99:00000000", "unknown fence", TOOLKIT),
                           ("README.md#1:00000000", "not in the exec file set", TOOLKIT),
                           ("x; touch %s" % sentinel, "not a fence id", TOOLKIT)):
        rc, err = _run(fid, [], wc, root=root)
        assert rc == fr.REFUSED, (fid, rc)
        lines = err.splitlines()
        assert len(lines) == 1 and lines[0].startswith("opaque_entry_refused: "), err
        assert why in lines[0], (fid, lines[0])
    assert not sentinel.exists()
    out = subprocess.run([SHIM, "run", excised], cwd=str(wc), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 3 and out.stderr.startswith("opaque_entry_refused: "), out.stderr


def test_valid_run_exits_with_fence_status(cached, wc):
    """Benign path: a valid run is the fence's own exit status, 0 or not."""
    ctx = next(r for r in cached if r["id"].startswith("validate/SKILL.md#1:"))
    rc, err = _run(ctx["id"], [], wc)
    assert rc == 0 and "opaque_entry_refused" not in err
    check = next(r for r in cached if r["id"].startswith("wrapup/SKILL.md#") and
                 r["sources"] == ["lesson-check"])
    rc, err = _run(check["id"], ["--arg", "id=901", "--arg", "slug=missing"], wc)
    assert rc not in (0, fr.REFUSED) and "opaque_entry_refused" not in err


def test_census_recomputed_every_call(monkeypatch, wc):
    """Each call recomputes every exec-capable adapter's census: nothing is cached (ADR-2)."""
    calls = []
    real = fc.census

    def counting(root, adapter=None):
        calls.append((root, adapter.name))
        return real(root, adapter)
    monkeypatch.setattr(fc, "census", counting)
    fid = next(r["id"] for r in real(TOOLKIT) if r["route"] == "excised")
    _run(fid, [], wc)
    _run(fid, [], wc)
    names = [a.name for a in fc.exec_adapters(TOOLKIT)]
    assert calls == [(TOOLKIT, n) for n in names] * 2


# ------------------------------------------------------------------------ REQ-662 ADR-8
def test_runner_accepts_the_union_of_runner_routes(two, wc, monkeypatch, claude_only):
    """AC-24: a fence `runner` on one adapter and `direct` on another is accepted; a fence
    `runner` on none is refused, naming its route. Nothing but the root chooses: no variable
    or working-copy file changes the answer."""
    root, censuses = two
    memo_census(monkeypatch)
    claude = {r["id"]: r for r in censuses["claude"]}
    other = {r["id"]: r for r in censuses["fake-exec-file"]}
    split = [i for i in claude if claude[i]["route"] == "direct" and
             other[i]["route"] == "runner"]
    assert any(i.startswith(PUSH_KEY + ":") for i in split), split
    for fid in split:
        fence, rec = fr.find(fid, root)
        assert fence.id == fid and rec["route"] == "runner"
    none = [i for i in claude if claude[i]["route"] in ("excised", "engine")]
    assert none
    for fid in none:
        assert other[fid]["route"] == claude[fid]["route"]
        rc, err = _run(fid, [], wc, root=root,
                       environ=dict(os.environ, ADLC_EXEC_HARNESS="fake-exec-file"))
        assert rc == fr.REFUSED and "its route is %s, not runner" % claude[fid]["route"] in err
    (wc / "harness").mkdir()
    shutil.copy(MATCHER_NONE, str(wc / "harness"))
    push = next(i for i in split if i.startswith(PUSH_KEY + ":"))
    # A root where the push is direct on its one adapter: the working copy's harness/ does not
    # make it runnable.
    rc, err = _run(push, [], wc, root=claude_only)
    assert rc == fr.REFUSED and "its route is direct, not runner" in err, err
    # The real tree: codex routes the push through the runner (ADR-9), so it is accepted there
    # and goes on to its values.
    _fence, rec = fr.find(push, TOOLKIT)
    assert rec["route"] == "runner" and rec["push"] == fc.BRANCH_PUSH
    # A missing value is the caller's to supply, not a refusal (BUG-287).
    rc, err = _run(push, [], wc)
    assert rc == fr.BAD_VALUE and "no value for worktree" in err, err


def test_split_routes_are_named_when_none_is_runner(monkeypatch, tmp_path):
    """A refusal names each adapter's route when they differ and none is `runner`."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    shutil.copy(MATCHER_NONE, os.path.join(root, "harness"))
    real = fc.census

    def no_runner(r, adapter=None):
        out = [dict(rec) for rec in real(r, adapter)]
        for rec in out:
            if rec["route"] == "runner":
                rec["route"] = "unrouted"
        return out
    monkeypatch.setattr(fc, "census", no_runner)
    push = next(rec["id"] for rec in real(root, None) if rec["id"].startswith(PUSH_KEY + ":"))
    with pytest.raises(fr.Refusal, match="direct on claude, unrouted on codex, unrouted on "
                                         "fake-exec-file"):
        fr.find(push, root)


# ------------------------------------------------------------------------ REQ-662 ADR-9
def _git(*args, **kw):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_COMMITTER_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git"] + list(args), env=env, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, **kw).stdout


@pytest.fixture
def pushable(tmp_path):
    """A working copy on `feat/REQ-901-thing` whose origin is a throwaway local bare repo,
    with a decoy at every vendored partial (REQ-682 ADR-4)."""
    remote = tmp_path / "origin.git"
    _git("init", "-q", "--bare", str(remote))
    work = tmp_path / "wc"
    _git("init", "-q", "-b", "main", str(work))
    _git("-C", str(work), "commit", "-q", "--allow-empty", "-m", "a")
    _git("-C", str(work), "remote", "add", "origin", str(remote))
    _git("-C", str(work), "checkout", "-q", "-b", "feat/REQ-901-thing")
    _git("-C", str(work), "commit", "-q", "--allow-empty", "-m", "b")
    sentinel = tmp_path / "S"
    (work / ".adlc" / "partials").mkdir(parents=True)
    for name in os.listdir(os.path.join(TOOLKIT, "partials")):
        if name.endswith(".sh"):
            (work / ".adlc" / "partials" / name).write_text("touch '%s'\n" % sentinel)
    return work, remote, sentinel


def _heads(remote):
    return _git("--git-dir", str(remote), "for-each-ref", "--format=%(refname)").split()


def test_branch_push_refuses_every_other_spelling(two, pushable, tmp_path, monkeypatch):
    """BR-3, ADR-9: the push fence refuses every branch value but a REQ's own branch, and a
    worktree value that is not the calling directory, each with exit 3 and one
    `opaque_entry_refused` line, pushing nothing. A well-formed call pushes the branch to the
    throwaway bare remote, and no decoy partial in the working copy runs."""
    root, censuses = two
    memo_census(monkeypatch)
    work, remote, sentinel = pushable
    push = next(r for r in censuses["fake-exec-file"] if r["id"].startswith(PUSH_KEY + ":"))
    assert fr.same_dir_args(push) == ("worktree",)
    assert fr.head_args(push) == ("branch",)
    _git("-C", str(work), "branch", "feat/REQ-901-other")   # exists, but is not checked out
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", ADLC_DISABLE_DELEGATE="1")
    sub = work / "sub"
    sub.mkdir()
    (tmp_path / "elsewhere").mkdir()
    bad = [["--arg", "worktree=%s" % work, "--arg", "branch=%s" % b]
           for b in ("main", "+feat/x", "feat/x:main", "--force", "", "feat/REQ-901-thing\n",
                     "HEAD:refs/heads/main", "refs/heads/main",
                     # A well-formed branch that is not the one checked out here.
                     "feat/REQ-901-other", "feat/REQ-901-thing-2")]
    bad += [["--arg", "worktree=%s" % w, "--arg", "branch=feat/REQ-901-thing"]
            for w in (str(sub), str(tmp_path / "elsewhere"), str(tmp_path), "sub", ".")]
    bad += [["--arg", "branch=feat/REQ-901-thing"],
            ["--arg", "worktree=%s" % work, "--arg", "branch=feat/a", "--arg", "branch=feat/b"]]
    for argv in bad:
        rc, err = _run(push["id"], argv, work, environ=env, root=root)
        lines = err.splitlines()
        # Nothing runs either way. A value of the wrong shape, or a worktree that is not the
        # directory the runner was called from, is exit 65, which the caller corrects
        # (BUG-287); a well-formed branch that is not the one checked out here is what the
        # runner will not push, and stays a refusal.
        assert rc in (fr.REFUSED, fr.BAD_VALUE), (argv, rc, err)
        prefix = "opaque_entry_refused: " if rc == fr.REFUSED else "fence_run_bad_value: "
        assert len(lines) == 1 and lines[0].startswith(prefix), (argv, err)
        other_branch = any(a in ("branch=feat/REQ-901-other", "branch=feat/REQ-901-thing-2")
                           for a in argv)
        assert (rc == fr.REFUSED) == other_branch, (argv, rc, err)
    assert _heads(remote) == []
    rc, err = _run(push["id"], ["--arg", "worktree=%s" % work, "--arg",
                                "branch=feat/REQ-901-thing"], work, environ=env, root=root)
    assert rc == 0, err
    assert _heads(remote) == ["refs/heads/feat/REQ-901-thing"]
    assert _git("-C", str(work), "rev-parse", "--abbrev-ref", "@{upstream}").strip() == \
        "origin/feat/REQ-901-thing"
    assert not sentinel.exists()
    link = tmp_path / "link"
    link.symlink_to(work)
    rc, err = _run(push["id"], ["--arg", "worktree=%s" % link, "--arg",
                                "branch=feat/REQ-901-thing"], work, environ=env, root=root)
    assert rc == 0, err                  # the same directory by real path


def _push_env():
    """The caller's environment for a push test: no caller git state, no run binding."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.pop("ADLC_EXEC_RUN", None)
    env.update(GIT_CONFIG_NOSYSTEM="1", ADLC_DISABLE_DELEGATE="1")
    return env


def _push_fence(censuses):
    return next(r for r in censuses["fake-exec-file"] if r["id"].startswith(PUSH_KEY + ":"))


def _pins(env):
    return {env["GIT_CONFIG_KEY_%d" % i]: env["GIT_CONFIG_VALUE_%d" % i]
            for i in range(int(env["GIT_CONFIG_COUNT"]))}


def test_the_fence_git_environment_is_the_runners():
    """REQ-662 ADR-9: no caller `GIT_*` variable reaches the fence or the branch check, so both
    see the one repository the runner was called in, and the fence's git calls are pinned to
    run no fsmonitor program and no repository hook, whatever the repository's config says.
    `GIT_TERMINAL_PROMPT=0` only makes git fail sooner, so that one value stays."""
    hostile = dict(os.environ, GIT_DIR="/evil/.git", GIT_WORK_TREE="/evil",
                   GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.fsmonitor",
                   GIT_CONFIG_VALUE_0="/evil/fsmonitor", GIT_CONFIG_GLOBAL="/evil/gitconfig",
                   GIT_CONFIG_PARAMETERS="'core.hooksPath'='/evil'", GIT_EXEC_PATH="/evil",
                   GIT_SSH_COMMAND="/evil/ssh", GIT_TERMINAL_PROMPT="1")
    want = {"core.fsmonitor": "false", "core.hooksPath": "/dev/null"}
    for env in (fr.child_env(hostile, [], {}, TOOLKIT), fr.git_env(hostile)):
        assert sorted(k for k in env if k.startswith("GIT_")) == [
            "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_KEY_1", "GIT_CONFIG_VALUE_0",
            "GIT_CONFIG_VALUE_1"], env
        assert _pins(env) == want
        assert env["HOME"] == os.environ["HOME"]
    prompt = fr.child_env(dict(hostile, GIT_TERMINAL_PROMPT="0"), [], {}, TOOLKIT)
    assert prompt["GIT_TERMINAL_PROMPT"] == "0" and _pins(prompt) == want


def _arm(work, tmp_path):
    """Set ``work``'s own config to run a fsmonitor program and its own pre-push hook, each
    writing a sentinel: what a model that can write the repository's config could plant."""
    fsmonitor, hook = tmp_path / "fsmonitor-ran", tmp_path / "pre-push-ran"
    program = tmp_path / "fsmonitor.sh"
    program.write_text("#!/bin/sh\ntouch '%s'\nexit 1\n" % fsmonitor)
    program.chmod(0o755)
    pre_push = work / ".git" / "hooks" / "pre-push"
    pre_push.parent.mkdir(exist_ok=True)
    pre_push.write_text("#!/bin/sh\ntouch '%s'\nexit 0\n" % hook)
    pre_push.chmod(0o755)
    (work / "tracked.txt").write_text("x\n")
    _git("-C", str(work), "add", "tracked.txt")
    _git("-C", str(work), "commit", "-q", "-m", "c")
    with open(str(work / ".git" / "config"), "a") as fh:
        fh.write("[core]\n\tfsmonitor = %s\n" % program)
    return fsmonitor, hook


def test_no_repository_hook_or_fsmonitor_runs_in_a_fence(two, pushable, tmp_path,
                                                         monkeypatch):
    """REQ-662 ADR-9: a fence that reads git status and the branch push each run with the
    repository's fsmonitor program and pre-push hook pinned off, and the push still lands
    (the must-not-refuse case). The controls show both traps fire under the caller's own
    environment, so their absence is the pin's doing."""
    root, censuses = two
    memo_census(monkeypatch)
    work, remote, _sentinel = pushable
    fsmonitor, hook = _arm(work, tmp_path)
    env = _push_env()
    # Controls: under the caller's environment git runs both.
    subprocess.run(["git", "-C", str(work), "status", "--short"], env=env, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    control = tmp_path / "control.git"
    _git("init", "-q", "--bare", str(control))
    subprocess.run(["git", "-C", str(work), "push", "-q", str(control), "HEAD"], env=env,
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert fsmonitor.exists() and hook.exists()
    fsmonitor.unlink()
    hook.unlink()
    status = next(r for r in censuses["claude"] if r["id"].startswith("review/SKILL.md#1:"))
    assert status["route"] == "runner" and "git status" in fr.find(status["id"], root)[0].code
    rc, err = _run(status["id"], [], work, environ=env, root=root)
    assert rc == 0, err
    assert fr.checked_out_branch(str(work), env) == "feat/REQ-901-thing"
    rc, err = _run(_push_fence(censuses)["id"], ["--arg", "worktree=%s" % work, "--arg",
                                                 "branch=feat/REQ-901-thing"], work,
                   environ=env, root=root)
    assert rc == 0, err
    assert _heads(remote) == ["refs/heads/feat/REQ-901-thing"]
    assert not fsmonitor.exists() and not hook.exists()


def test_a_callers_git_dir_cannot_move_the_push(two, pushable, tmp_path, monkeypatch):
    """REQ-662 ADR-9: the branch check reads the calling directory's repository, and so does
    the push: a caller's `GIT_DIR` naming another repository, on the same branch with its own
    origin, reaches neither."""
    root, censuses = two
    memo_census(monkeypatch)
    work, remote, _sentinel = pushable
    other_remote = tmp_path / "other-origin.git"
    _git("init", "-q", "--bare", str(other_remote))
    other = tmp_path / "other"
    _git("init", "-q", "-b", "feat/REQ-901-thing", str(other))
    _git("-C", str(other), "commit", "-q", "--allow-empty", "-m", "elsewhere")
    _git("-C", str(other), "remote", "add", "origin", str(other_remote))
    env = dict(_push_env(), GIT_DIR=str(other / ".git"))
    rc, err = _run(_push_fence(censuses)["id"], ["--arg", "worktree=%s" % work, "--arg",
                                                 "branch=feat/REQ-901-thing"], work,
                   environ=env, root=root)
    assert rc == 0, err
    assert _heads(other_remote) == []
    assert _heads(remote) == ["refs/heads/feat/REQ-901-thing"]


def test_branch_push_is_bound_to_the_runs_req(two, pushable, monkeypatch):
    """REQ-662 ADR-9: under an exec run (`ADLC_EXEC_RUN` names its REQ) the push takes only
    `<type>/<that id>-<rest>`, checked out here; an id that is not `REQ-` and 3 to 6 digits
    refuses the push. Without the variable, or with it empty (the orchestrator reads an
    empty one as "not in a run" too), any checked-out feature branch is pushed, as before
    (the must-not-refuse case of a plain /proceed)."""
    root, censuses = two
    memo_census(monkeypatch)
    work, remote, _sentinel = pushable
    fid = _push_fence(censuses)["id"]
    base = _push_env()

    def push(branch, run):
        _git("-C", str(work), "checkout", "-q", "-B", branch)
        env = dict(base) if run is None else dict(base, ADLC_EXEC_RUN=run)
        return _run(fid, ["--arg", "worktree=%s" % work, "--arg", "branch=%s" % branch], work,
                    environ=env, root=root)

    for branch, run in (("feat/REQ-902-other", "REQ-901"), ("feat/REQ-66-x", "REQ-662"),
                        ("feat/REQ-662-x", "REQ-66"), ("feat/REQ-6620-x", "REQ-662"),
                        ("feat/REQ-662-x", "REQ-6620"), ("feat/REQ-901", "REQ-901"),
                        ("feat/xREQ-901-thing", "REQ-901"),
                        ("feat/REQ-901-thing", "req-901"), ("feat/REQ-901-thing", "REQ-901\n"),
                        ("feat/REQ-901-thing", "REQ-901 "), ("feat/REQ-901-thing", "REQ-1234567")):
        rc, err = push(branch, run)
        lines = err.splitlines()
        assert rc == fr.REFUSED, (branch, run, err)
        assert len(lines) == 1 and lines[0].startswith("opaque_entry_refused: "), (branch, err)
        assert "ADLC_EXEC_RUN" in err, err
    assert _heads(remote) == []
    rc, err = push("feat/REQ-902-other", "REQ-901")
    assert "feat/REQ-902-other" in err and "REQ-901" in err, err
    for branch, run in (("feat/REQ-901-thing", "REQ-901"), ("fix/REQ-662-x", "REQ-662"),
                        ("chore/REQ-123456-y", "REQ-123456"), ("feat/REQ-902-other", None),
                        ("feat/REQ-903-empty", "")):
        rc, err = push(branch, run)
        assert rc == 0, (branch, run, err)
        assert "refs/heads/" + branch in _heads(remote)


# ------------------------------------------------------------------------ BR-3, BR-5
def test_run_reads_only_toolkit_text(cached, wc, tmp_path):
    """A working copy's vendored partials and forge_config.py never run under the runner, nor
    under its own PR read: the working copy owns PR 101, so a fence that binds it gets past
    that read and runs."""
    sentinel = tmp_path / "S"
    repo_wc(wc)
    (wc / ".adlc" / "partials").mkdir(parents=True)
    for name in os.listdir(os.path.join(TOOLKIT, "partials")):
        if name.endswith(".sh"):
            (wc / ".adlc" / "partials" / name).write_text("touch '%s'\n" % sentinel)
    for rel in ("tools/adlc/forge_config.py", ".adlc/tools/adlc/forge_config.py"):
        (wc / rel).parent.mkdir(parents=True, exist_ok=True)
        (wc / rel).write_text("open(%r, 'w').write('x')\n" % str(sentinel))
    env = forge_env(pr_store(tmp_path / "store"), ADLC_REPOS_ROOT=str(tmp_path))
    ran = tied = 0
    for rec in _by_route(cached, "runner"):
        if not set(rec["sources"]) & {"forge", "lessons", "delegate-gate", "id-recheck"}:
            continue
        _rc, err = _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
        ran += 1
        if rec.get("tied"):
            assert "fence_run_" not in err and "opaque_entry_refused" not in err, err
            tied += 1
    assert ran >= 5 and tied >= 2
    assert not sentinel.exists()


def test_one_way_fences_refused_whatever_the_env(cached, wc):
    """No fence that reaches a one-way move is `runner`, and the refusal reads toolkit text
    only: the same under every value of ADLC_EXEC_RUN, or with it gone."""
    excised = _by_route(cached, "excised")
    assert excised
    base = dict(os.environ)
    base.pop("ADLC_EXEC_RUN", None)
    for rec in excised:
        seen = set()
        for env in (base, dict(base, ADLC_EXEC_RUN="REQ-901"), dict(base, ADLC_EXEC_RUN="other"),
                    dict(base, ADLC_EXEC_RUN="", ADLC_FENCE_TOOLKIT_ONLY="0")):
            rc, err = _run(rec["id"], [], wc, environ=env)
            assert rc == fr.REFUSED
            seen.add(err)
        assert len(seen) == 1, rec["id"]
    for rec in cached:
        assert not (rec["route"] == "runner" and "adlc_forge_pr_merge" in " ".join(
            rec.get("reach", []))), rec["id"]


def test_refusal_holds_against_env_defeats(cached, wc):
    """AC-6, runner side: nothing a caller sets survives into the fence's environment, so an
    earlier `unset`, an env prefix or a second source cannot change what the runner does.
    Claude refuses the model's side of each defeat (TASK-243's matcher, probe rows 2, 9, 13)."""
    hostile = dict(os.environ, ADLC_FENCE_TOOLKIT_ONLY="0", ADLC_TOOLKIT_ROOT="/evil",
                   ADLC_ARG_state="/evil", ADLC_ARG_x="1", CLAUDE_PLUGIN_ROOT="/evil")
    phs = [fc.PLACEHOLDERS["state"]]
    env = fr.child_env(hostile, phs, {"state": ["/ok"]}, TOOLKIT)
    assert env["ADLC_FENCE_TOOLKIT_ONLY"] == "1" and env["ADLC_TOOLKIT_ROOT"] == TOOLKIT
    assert env["ADLC_ARG_state"] == "/ok" and "ADLC_ARG_x" not in env
    echo = next(r for r in cached if r["id"].startswith("agents/pipeline-runner.md#") or
                r["id"].startswith("validate/SKILL.md#1:"))
    rc, _err = _run(echo["id"], [], wc, environ=hostile)
    assert rc == 0
    for defeat in ("unset ADLC_FENCE_TOOLKIT_ONLY; %s run x" % fr.runner_path(TOOLKIT),
                   "ADLC_FENCE_TOOLKIT_ONLY=0 %s run x" % fr.runner_path(TOOLKIT),
                   ". %s/partials/forge.sh; adlc_forge_pr_merge 1" % TOOLKIT):
        assert not em.admits({"allow": ["Bash(%s:*)" % fr.runner_path(TOOLKIT)]}, defeat)


def test_safe_forge_fences_run_under_mock(cached, wc, tmp_path):
    """Benign path: pr_create, pr_view and pr_edit fences run against the forge mock and
    refuse nothing, from a working copy whose branch owns PR 101 (REQ-719 ADR-3)."""
    repo_wc(wc)
    env = forge_env(pr_store(tmp_path / "store"))
    forge = [r for r in _by_route(cached, "runner") if "forge" in r["sources"] and
             r["id"].split("#")[0] in fc.PIPELINE_FILES]
    assert len(forge) >= 2 and len([r for r in forge if r.get("tied")]) >= 2
    for rec in forge:
        rc, err = _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
        assert "opaque_entry_refused" not in err, (rec["id"], err)
        assert rc == 0, (rec["id"], rc, err)


def test_azure_devops_backend_refused_under_the_runner(cached, wc, tmp_path):
    """BR-5: `az repos pr` is an exec deny, and the forge's ADO arm refuses under the flag."""
    log = str(tmp_path / "calls.jsonl")
    stubs = rs.install(str(tmp_path / "bin"), log)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"],
               ADLC_FORGE_PROVIDER_OVERRIDE="azure-devops", ADLC_DISABLE_DELEGATE="1")
    env.pop("ADLC_FORGE_MOCK", None)
    rec = next(r for r in _by_route(cached, "runner")
               if r["id"].startswith("proceed/phase-0-setup.md#") and "forge" in r["sources"])
    rc, _err = _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
    assert rc != 0
    assert not [c for c in rs.calls(log) if c["cmd"] == "az"]


# ------------------------------------------------------------------------ BR-6, AC-5
def test_hostile_values_never_run_code(cached, wc, tmp_path, monkeypatch):
    """Every runner fence x every value it takes x every BR-6 hostile value: refused by its
    pattern, or bound as data. No sentinel, and no recorded argv a deny-tier rule matches."""
    sentinel = str(tmp_path / "S")
    log = str(tmp_path / "calls.jsonl")
    stubs = rs.install(str(tmp_path / "bin"), log)
    env = forge_env(pr_store(tmp_path / "store"), ADLC_REPOS_ROOT=str(tmp_path),
                    PATH=stubs + os.pathsep + os.environ["PATH"])
    # `git` is a stub here, so the runner's read of the checked-out branch is given the branch
    # that owns PR 101 in the store: a fence that binds a PR number then gets past the
    # runner's PR read, which still runs, and its other values reach the fence.
    monkeypatch.setattr(fr, "checked_out_branch", lambda cwd, environ: PR_BRANCH)
    adapter = ea.load("claude", TOOLKIT)
    policy = fc.exec_policy(TOOLKIT, adapter)
    cases = refused = 0
    for rec in _by_route(cached, "runner"):
        for arg in rec["placeholders"]:
            for raw in HOSTILE:
                value = raw.replace("{s}", sentinel)
                rc, err = _run(rec["id"], _sample_argv(rec, wc, value, arg), wc, environ=env)
                cases += 1
                # A hostile value fails its pattern, which is exit 65 since BUG-287: still
                # nothing run, as the sentinel below shows.
                refused += rc == fr.BAD_VALUE and "fence_run_bad_value" in err
    assert cases > 50 and refused > 0
    assert not os.path.exists(sentinel)
    for call in rs.calls(log):
        assert not em.deny_hits(policy, rs.command_text(call)), call


def test_value_reaches_the_fence_only_as_data(tmp_path):
    """A value full of shell syntax reaches the fence byte for byte, never run."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    path = os.path.join(root, "validate", "SKILL.md")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('\n```sh\nprintf \'%s\' "$NEW_BODY"\n```\n')
    fid = [r for r in fc.census(root, ea.load("claude", root))
           if r["id"].startswith("validate/SKILL.md#")][-1]["id"]
    wc = tmp_path / "wc"
    wc.mkdir()
    sentinel = tmp_path / "S"
    value = "$(touch %s) `touch %s` ; touch %s\n'\"\\ end" % (sentinel, sentinel, sentinel)
    (wc / "body.txt").write_text(value, encoding="utf-8")
    out = subprocess.run([os.path.join(root, "tools", "adlc", "fence-run"), "run", fid,
                          "--arg-file", "NEW_BODY=body.txt"], cwd=str(wc),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout == value
    assert not sentinel.exists()


def test_arg_file_bounds(tmp_path):
    wc = tmp_path / "wc"
    wc.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    (wc / "link").symlink_to(outside)
    (wc / "dir").mkdir()
    (wc / "big").write_bytes(b"x" * (fr.MAX_ARG_FILE + 1))
    (wc / "ok").write_text("a 'quoted'\nvalue $(x)\n")
    for bad in ("../outside.txt", "link", "dir", "big", ""):
        with pytest.raises(fr.Refusal):
            fr.read_arg_file(bad, str(wc))
    assert fr.read_arg_file("ok", str(wc)) == "a 'quoted'\nvalue $(x)\n"


# ------------------------------------------------------------------------ BR-11, AC-8
def test_delegation_off_takes_fallback(tmp_path, monkeypatch):
    """With ADLC_DISABLE_DELEGATE=1, or no opt-in, a delegating fence takes its fallback,
    and the runner adds no ADLC_DELEGATE_* variable to the fence's environment."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    path = os.path.join(root, "validate", "SKILL.md")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n```sh\n" + fc.ROOT_LINE + "\nif [ -f .adlc/partials/delegate-gate.sh ]; then "
                 ". .adlc/partials/delegate-gate.sh; else . \"$ADLC_TOOLKIT_ROOT/partials/"
                 "delegate-gate.sh\"; fi\nadlc_delegate_gate_check; printf 'gate=%s\\n' \"$?\"\n```\n")
    fid = [r for r in fc.census(root, ea.load("claude", root))
           if r["id"].startswith("validate/SKILL.md#")][-1]["id"]
    wc = tmp_path / "wc"
    wc.mkdir()
    base = {k: v for k, v in os.environ.items()
            if not k.startswith("ADLC_DELEGATE") and k not in ("KIMI_API_KEY", "MOONSHOT_API_KEY")}
    shim = os.path.join(root, "tools", "adlc", "fence-run")
    for env in (dict(base, ADLC_DISABLE_DELEGATE="1"), base):
        out = subprocess.run([shim, "run", fid], cwd=str(wc), env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() in ("gate=1", "gate=2"), out.stdout
    env = fr.child_env(base, [], {}, root)
    assert not [k for k in env if k.startswith("ADLC_DELEGATE")]


# ------------------------------------------------------------------------ show
def test_show_refuses_outside_the_set_and_rewrites_fences(cached, capsys, claude_only):
    err = io.StringIO()
    assert fr.show("README.md", TOOLKIT, err=err) == fr.REFUSED
    assert err.getvalue().startswith("opaque_entry_refused: show README.md:")
    assert fr.show("validate/SKILL.md", TOOLKIT) == 0
    out = capsys.readouterr().out
    for rec in cached:
        if rec["id"].startswith("validate/SKILL.md#") and rec["route"] == "runner":
            # The id is quoted: Codex matches no prefix rule against a bare `#`.
            assert "%s run '%s'" % (fr.runner_path(TOOLKIT), rec["id"]) in out
    assert "\n" + fr.runner_path(TOOLKIT) + " run " in out          # unquoted absolute root
    assert "if [ -f .adlc/partials/" not in out
    assert not [ln for ln in out.split("\n") if ln.startswith("!")]
    # A fence direct on every exec-capable adapter is shown as written ...
    assert fr.show("proceed/phases-lite.md", claude_only) == 0
    assert "     ls -t .adlc/knowledge/lessons\n" in capsys.readouterr().out
    # ... and one runner on any of them as its runner line: show prints the union (ADR-8).
    assert fr.show("proceed/phases-lite.md", TOOLKIT) == 0
    out = capsys.readouterr().out
    assert "     ls -t .adlc/knowledge/lessons\n" not in out
    assert "%s run 'proceed/phases-lite.md#" % fr.runner_path(TOOLKIT) in out


def test_root_outside_the_charset_refuses_to_start(monkeypatch):
    monkeypatch.setattr(fr.tkr, "toolkit_root", lambda: "/a b/tk")
    err = io.StringIO()
    assert fr.main(["show", "validate/SKILL.md"], err=err) == fr.REFUSED
    assert "cannot match" in err.getvalue()


def test_path_values_stay_in_the_working_copy_or_a_spec_dir(cached, wc, tmp_path):
    """A path value cannot aim a fence's write or read outside the working copy (BUG-265):
    a state file must sit under it, or be a REQ spec directory's pipeline-state.json."""
    r2 = next(r for r in cached if r["id"].startswith("proceed/phases-telemetry.md#2:"))
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n")
    for bad in (str(outside), "/etc/hosts", str(tmp_path / "x" / ".adlc" / "specs" / "REQ-901-a"
                                                 / "settings.json")):
        rc, err = _run(r2["id"], ["--arg", "state=%s" % bad, "--arg", "phase=1",
                                  "--arg", "attempt=1"], wc)
        assert rc == fr.BAD_VALUE and "outside the working directory" in err, (bad, err)
    assert outside.read_text() == "{}\n"
    spec_dir = tmp_path / "primary" / ".adlc" / "specs" / "REQ-901-a-thing"
    spec_dir.mkdir(parents=True)
    (spec_dir / "pipeline-state.json").write_text("{}\n")
    rc, err = _run(r2["id"], ["--arg", "state=%s" % (spec_dir / "pipeline-state.json"),
                              "--arg", "phase=1", "--arg", "attempt=1"], wc)
    assert rc == 0, err
    assert "validateAttempts" in (spec_dir / "pipeline-state.json").read_text()


def test_patterns_the_runner_keeps_its_own_copy_of_stay_equal():
    """fence-run runs under `python3 -I` and keeps its imports to what it needs, so it holds its
    own copy of two patterns rather than importing them: the run's REQ id (`ADLC_EXEC_RUN`, as
    the orchestrator validates it) and the plain absolute path a prefix rule matches unquoted
    (as the renderer spells the runner allow). Nothing else holds the copies equal."""
    import exec_safety as es
    import harness_render as hr
    for mine, theirs in ((fr._RUN_ID_RE, es.VALID_REQ), (fr.ROOT_RE, hr.RUNNER_PATH_RE)):
        assert (mine.pattern, mine.flags) == (theirs.pattern, theirs.flags)


def test_push_args_reads_one_key_of_the_push_kind():
    """REQ-662 ADR-9: the values a push fence binds, read by key from the push kind it makes:
    `same_dir` (the calling directory) and `head` (the branch checked out there). A fence that
    makes no push binds none. On `matcher: none` the branch push is a runner fence."""
    records = fc.census(TOOLKIT, ea.load("codex", TOOLKIT))
    push = next(r for r in records if r.get("push") == "branch")
    assert fr.push_args(push, "same_dir") == fr.same_dir_args(push) == ("worktree",)
    assert fr.push_args(push, "head") == fr.head_args(push) == ("branch",)
    plain = next(r for r in records if r["route"] == "runner" and not r.get("push"))
    assert fr.push_args(plain, "same_dir") == fr.push_args(plain, "head") == ()


# --------------------------------------------------------------------------- BUG-287
# The first real pipeline run: a fence call chained after a command with no allow ran inside
# Codex's sandbox, and a value of the wrong shape ended three launches as a refusal.

@pytest.fixture
def linked(tmp_path):
    """A linked worktree on `feat/REQ-901-thing`, as the engine makes one: its git directory
    is the main checkout's, outside the working copy. The origin is a local bare repo."""
    remote = tmp_path / "origin.git"
    _git("init", "-q", "--bare", str(remote))
    main = tmp_path / "main"
    _git("init", "-q", "-b", "main", str(main))
    _git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "a")
    _git("-C", str(main), "remote", "add", "origin", str(remote))
    work = main / ".worktrees" / "REQ-901"
    _git("-C", str(main), "worktree", "add", "-q", "-b", "feat/REQ-901-thing", str(work))
    _git("-C", str(work), "commit", "-q", "--allow-empty", "-m", "b")
    return main, work, remote


def test_bug287_no_sandbox_no_refusal(linked, tmp_path):
    """The benign path: where the git directory is writable, inside the working copy, or
    absent, the check says nothing and the call goes on."""
    main, work, _remote = linked
    env = _push_env()
    assert fr.sandboxed(str(work), env) is None       # a linked worktree, writable
    assert fr.sandboxed(str(main), env) is None       # the git directory is inside cwd
    plain = tmp_path / "plain"
    plain.mkdir()
    assert fr.sandboxed(str(plain), env) is None      # no repository at all


def test_bug287_an_unwritable_git_dir_outside_the_working_copy_is_named(linked, monkeypatch):
    main, work, _remote = linked
    common = os.path.realpath(str(main / ".git"))
    real = os.access
    asked = []

    def access(path, mode, **kw):
        asked.append((os.path.realpath(path), mode))
        if os.path.realpath(path) == common and mode == os.W_OK:
            return False
        return real(path, mode, **kw)

    monkeypatch.setattr(os, "access", access)
    why = fr.sandboxed(str(work), _push_env())
    assert why and "inside the harness's sandbox" in why and "command of its own" in why
    assert (common, os.W_OK) in asked
    # The main checkout holds its own git directory: the same denial is never consulted.
    del asked[:]
    assert fr.sandboxed(str(main), _push_env()) is None and not asked


def test_bug287_a_sandboxed_call_runs_nothing_and_says_how_to_rerun(two, linked, monkeypatch):
    """Exit 69 and one `fence_run_sandboxed:` line, never `opaque_entry_refused:`: the prompt
    tells a session to stop on a refusal and to rerun this."""
    root, censuses = two
    memo_census(monkeypatch)
    _main, work, remote = linked
    argv = ["--arg", "worktree=%s" % work, "--arg", "branch=feat/REQ-901-thing"]
    monkeypatch.setattr(fr, "sandboxed", lambda cwd, environ: "it is sandboxed")
    rc, err = _run(_push_fence(censuses)["id"], argv, work, environ=_push_env(), root=root)
    assert rc == fr.SANDBOXED == 69, err
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("fence_run_sandboxed: " + PUSH_KEY), err
    assert "opaque_entry_refused" not in err
    assert _heads(remote) == []
    # A value of the wrong shape is reported first: there is nothing to rerun until it is right.
    rc, err = _run(_push_fence(censuses)["id"], ["--arg", "worktree=%s" % work], work,
                   environ=_push_env(), root=root)
    assert rc == fr.BAD_VALUE and err.startswith("fence_run_bad_value: "), err
    monkeypatch.undo()
    memo_census(monkeypatch)
    rc, err = _run(_push_fence(censuses)["id"], argv, work, environ=_push_env(), root=root)
    assert rc == 0, err
    assert _heads(remote) == ["refs/heads/feat/REQ-901-thing"]


def _sandbox_exec_works():
    if sys.platform != "darwin" or not os.path.exists("/usr/bin/sandbox-exec"):
        return False
    try:
        return subprocess.run(["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)",
                               "/usr/bin/true"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(not _sandbox_exec_works(), reason="needs macOS sandbox-exec")
def test_bug287_a_real_sandbox_is_detected_through_the_cli(two, linked):
    """The real thing, not a stand-in: `fence-run` run under a macOS sandbox that denies
    writes to the main checkout's git directory, which is what Codex's `workspace-write`
    does to a line it runs sandboxed. Exit 69, nothing pushed; the same line outside the
    sandbox pushes."""
    root, censuses = two
    main, work, remote = linked
    runner = os.path.join(root, "tools", "adlc", "fence-run")
    call = [runner, "run", _push_fence(censuses)["id"], "--arg", "worktree=%s" % work,
            "--arg", "branch=feat/REQ-901-thing"]
    profile = '(version 1)(allow default)(deny file-write* (subpath "%s"))' \
        % os.path.realpath(str(main / ".git"))
    env = _push_env()
    boxed = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile] + call, cwd=str(work),
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
    assert boxed.returncode == fr.SANDBOXED, (boxed.returncode, boxed.stderr)
    assert boxed.stderr.startswith("fence_run_sandboxed: "), boxed.stderr
    assert _heads(remote) == []
    free = subprocess.run(call, cwd=str(work), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    assert free.returncode == 0, free.stderr
    assert _heads(remote) == ["refs/heads/feat/REQ-901-thing"]


def test_bug287_a_wrong_shaped_value_is_not_a_refusal(cached, wc):
    """Exit 65, one line naming the value, and the corrected call runs: a relative path where
    the fence takes an absolute one ended a real run at Step 0."""
    r1 = next(r for r in cached if r["id"].startswith("proceed/phases-telemetry.md#2:"))
    state = os.path.join(str(wc), ".adlc", "specs", "REQ-901-a", "pipeline-state.json")
    os.makedirs(os.path.dirname(state), exist_ok=True)
    with open(state, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    relative = os.path.relpath(state, str(wc))
    rc, err = _run(r1["id"], ["--arg", "state=%s" % relative, "--arg", "phase=1",
                              "--arg", "attempt=1"], wc)
    assert rc == fr.BAD_VALUE == 65, err
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("fence_run_bad_value: " + r1["id"]), err
    assert "value for state" in err and "correct that value and run the line again" in err
    with open(state, encoding="utf-8") as fh:
        assert fh.read() == "{}\n"                  # nothing ran
    # What the runner will not run at all is still a refusal.
    rc, err = _run("proceed/SKILL.md#999:deadbeef", [], wc)
    assert rc == fr.REFUSED and err.startswith("opaque_entry_refused: "), err
