"""The lite lane check's fetch names both destinations (REQ-719 BR-6 to BR-8, AC-6, AC-7).

In a `--single-branch` clone `remote.origin.fetch` maps the cloned branch only, so neither
`git push -u origin <branch>` nor `git fetch origin <integrationBranch> <branch>` writes
`refs/remotes/origin/<branch>`, and the fence's `rev-parse "origin/$br"` failed: the check
read `check-error` on a change that was inside the lite lane (BUG-287). The fence now fetches
`+refs/heads/<name>:refs/remotes/origin/<name>` for both branches.

Every case runs the real fence of `proceed/phases-lite.md` through the real `fence-run` shim,
in a clone of a throwaway bare origin under ``tmp_path``. Nothing reaches a network: the only
remote is that bare repository.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import toolkit_root  # noqa: E402
from test_fence_run import _git  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
SHIM = os.path.join(TOOLKIT, "tools", "adlc", "fence-run")
LITE = "proceed/phases-lite.md"
#: The REQ's branch every case pushes.
BRANCH = "feat/REQ-900-lane-fetch"
#: ADR-2's line: the lane check fence, Phase 7's diff fence and the partial's docs carry it.
EXPLICIT_FETCH = ('git -C "$wt" fetch origin "+refs/heads/$ib:refs/remotes/origin/$ib" '
                  '"+refs/heads/$br:refs/remotes/origin/$br"')
#: The fetch the lane check fence ran before REQ-719, and that fence's id then.
OLD_FETCH = 'git -C "$wt" fetch origin "$ib" "$br"'
OLD_LANE_ID_SHA = "a75800ba"


# ------------------------------------------------------------------------ the repositories
def origin_repo(tmp_path):
    """A throwaway bare origin under ``tmp_path`` whose `main` holds a README and
    `src/keep.py`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin.git"
    _git("init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git("init", "-q", "-b", "main", str(seed))
    (seed / "src").mkdir()
    (seed / "README.md").write_text("seed\n")
    (seed / "src" / "keep.py").write_text("".join("line %d = %d\n" % (i, i) for i in range(20)))
    _git("-C", str(seed), "add", "-A")
    _git("-C", str(seed), "commit", "-q", "-m", "seed")
    _git("-C", str(seed), "push", "-q", str(origin), "main")
    return origin


def branch_clone(tmp_path, origin, name="wc", single=True, change=None):
    """A clone of ``origin`` (``--single-branch`` unless ``single`` is false) with
    :data:`BRANCH` checked out, one commit on it made by ``change(wc)`` (by default a new
    `src/a.py`, which the default lite-lane rules pass), and that branch pushed with `-u`."""
    wc = tmp_path / name
    extra = ["--single-branch", "--branch", "main"] if single else []
    _git(*(["clone", "-q"] + extra + [str(origin), str(wc)]))
    _git("-C", str(wc), "checkout", "-q", "-b", BRANCH)
    if change is None:
        (wc / "src" / "a.py").write_text("a = 1\n")
        _git("-C", str(wc), "add", "src/a.py")
    else:
        change(wc)
    _git("-C", str(wc), "commit", "-q", "-m", "a change inside the lite lane")
    _git("-C", str(wc), "push", "-q", "-u", "origin", BRANCH)
    return wc


def tracking_ref(wc, branch=BRANCH):
    """The sha `refs/remotes/origin/<branch>` names in ``wc``, or None when it does not exist."""
    proc = subprocess.run(["git", "-C", str(wc), "rev-parse", "--verify", "--quiet",
                           "refs/remotes/origin/%s" % branch],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def head(wc):
    return _git("-C", str(wc), "rev-parse", "HEAD").strip()


def caller_env(**extra):
    """The caller's environment: the conftest's sandboxed HOME, no exec run, no mock forge."""
    env = dict(os.environ, ADLC_DISABLE_DELEGATE="1", **extra)
    for key in ("ADLC_EXEC_RUN", "ADLC_FORGE_MOCK", "ADLC_FORGE_MOCK_STORE",
                "ADLC_FORGE_MOCK_SCENARIO", "ADLC_FORGE_PROVIDER_OVERRIDE"):
        env.pop(key, None)
    return env


def fence_run(fid, wc, args, env=None):
    """``(status, stdout, stderr)`` of `fence-run run <fid> <args>` called from ``wc``."""
    proc = subprocess.run([SHIM, "run", fid] + list(args), cwd=str(wc),
                          env=env if env is not None else caller_env(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


def branch_args(wc, integration="main", branch=BRANCH):
    return ["--arg", "worktree=%s" % wc, "--arg", "integrationBranch=%s" % integration,
            "--arg", "branch=%s" % branch]


@pytest.fixture(scope="module")
def records():
    """The merged census: what fence-run accepts, whichever harness calls."""
    return fc.census(TOOLKIT)


def lane_fence():
    """The one lane check fence of the lite companion, as the exec view holds it."""
    hits = [f for f in fc.fences(fc.view(TOOLKIT, LITE), LITE)
            if "adlc_lane_check " in f.code]
    assert len(hits) == 1, [f.id for f in hits]
    return hits[0]


def lane_record(records):
    fence = lane_fence()
    rec = next(r for r in records if r["id"] == fence.id)
    assert rec["route"] == "runner" and rec["sources"] == ["lane-check"], rec
    return rec


def _lines(out):
    return out.splitlines()


# ------------------------------------------------------------------------ BR-6, BR-7, AC-6
def test_req719_single_branch_clone_reaches_the_engine_verdict(records, tmp_path):
    """Benign path: in a `--single-branch` clone whose branch is pushed, the fence fetches both
    refs with their destinations named, reaches `adlc_lane_check`, and prints the engine's
    verdict, `lane_check=pass` for one new source file. `refs/remotes/origin/<branch>` exists
    afterwards, at the pushed head. Before the call it does not: the clone and the push left it
    unwritten, and so does the plain fetch the fence used to run, which is the failure BR-6
    measured. On an ordinary clone the verdict is the same pass."""
    rec = lane_record(records)
    origin = origin_repo(tmp_path)
    wc = branch_clone(tmp_path, origin)
    assert _git("-C", str(wc), "config", "--get-all", "remote.origin.fetch").split() == \
        ["+refs/heads/main:refs/remotes/origin/main"]
    assert tracking_ref(wc) is None, "the push wrote the ref: no single-branch case to test"
    # The old fetch leaves the ref unwritten, so the old fence's rev-parse could never match.
    _git("-C", str(wc), "fetch", "-q", "origin", "main", BRANCH)
    assert tracking_ref(wc) is None
    rc, out, err = fence_run(rec["id"], wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    lines = _lines(out)
    assert lines[0] == "lane_check=pass", out
    assert "files_counted=1" in lines and lines[-1] == "lane_check_rc=0", out
    assert not [ln for ln in lines if ln.startswith("trigger=")], out
    assert tracking_ref(wc) == head(wc)
    assert tracking_ref(wc, "main") == _git("-C", str(origin), "rev-parse", "main").strip()
    # An ordinary clone, of an origin of its own: the verdict is what it was.
    plain_root = tmp_path / "ordinary"
    plain = branch_clone(plain_root, origin_repo(plain_root), single=False)
    rc, out, err = fence_run(rec["id"], plain, branch_args(plain))
    assert rc == 0, (rc, out, err)
    assert _lines(out)[0] == "lane_check=pass" and _lines(out)[-1] == "lane_check_rc=0", out
    assert tracking_ref(plain) == head(plain)


def test_req719_errors_are_still_errors(records, tmp_path):
    """BR-7: no verdict changes and no pass is added. With the remote unreachable the fetch
    fails and the fence prints `trigger=check-error` with the fetch detail; with a commit that
    was not pushed it prints the `HEAD is not origin/<branch>` detail. Neither reaches the
    engine, and each is `lane_check=error`, rc 2."""
    rec = lane_record(records)
    origin = origin_repo(tmp_path)
    wc = branch_clone(tmp_path, origin)
    # An unpushed commit: the fetch writes origin/<branch> at the pushed head, HEAD is ahead.
    (wc / "src" / "b.py").write_text("b = 1\n")
    _git("-C", str(wc), "add", "src/b.py")
    _git("-C", str(wc), "commit", "-q", "-m", "not pushed")
    rc, out, err = fence_run(rec["id"], wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    assert _lines(out) == [
        "lane_check=error", "trigger=check-error",
        "detail=HEAD is not origin/%s, push first: the PR merges the remote head" % BRANCH,
        "lane_check_rc=2"], out
    assert tracking_ref(wc) is not None and tracking_ref(wc) != head(wc)
    # The remote made unreachable: the fetch fails, and that is an error, never a pass.
    _git("-C", str(wc), "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    rc, out, err = fence_run(rec["id"], wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    assert _lines(out) == [
        "lane_check=error", "trigger=check-error",
        "detail=fetch of origin/main or origin/%s failed" % BRANCH, "lane_check_rc=2"], out
    assert "gone.git" in err, err


# ------------------------------------------------------------------------ BR-8, AC-7
def test_req719_partial_and_goldens_name_the_explicit_fetch(records):
    """BR-8: the fence fetches with ADR-2's line, and nothing else in it changed: putting the
    old fetch back gives the old fence's id. The partial's header and its call protocol name
    the same line as the caller's fetch. Both adapters' census files hold the new id, route it
    `runner`, and no longer hold the old one, and `fence-run show` prints a runner call for
    it."""
    fence = lane_fence()
    code = fence.code
    assert code.count(EXPLICIT_FETCH) == 1 and OLD_FETCH not in code
    assert "elif ! %s; then\n" % EXPLICIT_FETCH in code
    old_body = fence.body.replace(EXPLICIT_FETCH, OLD_FETCH)
    assert hashlib.sha256(old_body.encode("utf-8")).hexdigest()[:8] == OLD_LANE_ID_SHA
    assert fence.sha8 != OLD_LANE_ID_SHA
    with open(os.path.join(TOOLKIT, "partials", "lane-check.sh"), encoding="utf-8") as fh:
        header = fh.read().split("\nadlc_lane_check() {", 1)[0]
    assert "#   %s\n" % EXPLICIT_FETCH in header
    assert "caller's fetch is the" in header and "explicit form above" in header
    with open(os.path.join(TOOLKIT, "partials", "lane-check.md"), encoding="utf-8") as fh:
        doc = fh.read()
    protocol = doc[doc.index("## Call protocol"):doc.index("## Return contract")]
    assert "```sh\n%s\n```" % EXPLICIT_FETCH in protocol
    assert "The caller's fetch names each ref's destination" in protocol
    for name in ("claude", "codex"):
        with open(os.path.join(TOOLKIT, fc.golden_path(name)), encoding="utf-8") as fh:
            golden = json.load(fh)["fences"]
        ids = {r["id"]: r for r in golden}
        assert ids[fence.id]["route"] == "runner", name
        assert ids[fence.id]["sources"] == ["lane-check"], name
        assert "git fetch" in ids[fence.id]["reach"], name
        assert "%s#2:%s" % (LITE, OLD_LANE_ID_SHA) not in ids, name
    assert lane_record(records)["id"] == fence.id
    proc = subprocess.run([SHIM, "show", LITE], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    call = fr.runner_call(lane_record(records), TOOLKIT, fr._placeholders_for(fence))
    assert proc.stdout.count(call) == 1, call
    assert "'%s'" % fence.id in call and "--arg worktree='<worktree>'" in call
