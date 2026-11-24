"""Tests for ``tools/launch/adoption_snapshot.py`` (REQ-672 TASK-279, ADR-7, BR-6, BR-7).

No test reaches GitHub, the Hugging Face Hub or any network host. ``gh`` is a fake on a
PATH of the fake's directory plus ``/usr/bin:/bin`` only, answering from a directory keyed
by the API path and logging every argv; each test asserts from that log that the fake is
what ran. The Hub is a stub opener handed to ``main``. An autouse fixture puts PATH at
``/usr/bin:/bin`` (where no ``gh`` lives, which it asserts) and replaces the module's real
opener with one that records any call, failing the test at teardown if one was made.
"""
import ast
import datetime
import email.message
import errno
import fcntl
import http.client
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import sysconfig
import threading
import time
import types
import urllib.error

import pytest

import adoption_snapshot as snap

import credential_redact  # noqa: E402  (on sys.path through adoption_snapshot)

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "adoption_snapshot.py")
SYSTEM_PATH = "/usr/bin:/bin"
NOW = datetime.datetime(2026, 11, 23, 9, 30, 5, tzinfo=datetime.timezone.utc)

REPO = "example-org/example-repo"
DATASET = "example-org/example-dataset"
SPACE = "example-org/example-space"
DATASET_URL = snap.HUB_API + "datasets/" + DATASET
SPACE_URL = snap.HUB_API + "spaces/" + SPACE
#: Obviously fake: no live credential format's prefix.
CANARY_GH = "canary-token-not-real-123"
CANARY_HF = "canary-hf-token-not-real-456"

GH_PATHS = ("repos/%s" % REPO, "repos/%s/traffic/views" % REPO,
            "repos/%s/traffic/clones" % REPO, "repos/%s/traffic/popular/referrers" % REPO)
GITHUB_FIELDS = ("github_stars", "github_forks")
TRAFFIC_FIELDS = ("github_views_14d", "github_clones_14d", "top_referrers")
ROW_KEYS = ["date", "recorded_at", "repo", "github_stars", "github_forks",
            "github_views_14d", "github_clones_14d", "top_referrers",
            "hf_dataset_downloads", "hf_space_likes", "hf_space_runs", "sources"]

# What GitHub and the Hub answer, cut to realistic shapes.
REPO_BODY = {"full_name": REPO, "private": False, "stargazers_count": 42, "forks_count": 7,
             "watchers_count": 42, "open_issues_count": 3}
VIEWS_BODY = {"count": 310, "uniques": 120,
              "views": [{"timestamp": "2026-11-10T00:00:00Z", "count": 20, "uniques": 9}]}
CLONES_BODY = {"count": 55, "uniques": 30,
               "clones": [{"timestamp": "2026-11-10T00:00:00Z", "count": 4, "uniques": 2}]}
REFERRERS_BODY = [{"referrer": "news.ycombinator.com", "count": 90, "uniques": 60},
                  {"referrer": "github.com", "count": 12, "uniques": 8, "kind": "a key GitHub "
                                                                           "may add later"}]
DATASET_BODY = {"_id": "0123456789abcdef", "id": DATASET, "author": "example-org",
                "downloads": 1234, "likes": 5, "private": False, "tags": ["text"]}
SPACE_BODY = {"_id": "fedcba9876543210", "id": SPACE, "author": "example-org", "likes": 17,
              "sdk": "gradio", "runtime": {"stage": "RUNNING"}}

GH_NO_LOGIN = ("To get started with GitHub CLI, please run:  gh auth login\n"
               "Alternatively, populate the GH_TOKEN environment variable with a GitHub API "
               "authentication token.\n")

FAKE_GH = """#!/bin/sh
# A stand-in for gh: logs its argv, answers from a directory keyed by the API path.
printf '%%s\\n' "$*" >> %(log)s
dir=%(answers)s
key=$(printf '%%s' "$2" | tr '/' '_')
if [ -f "$dir/echo-tokens" ]; then
  line="gh: debug:"
  for name in $(cat "$dir/echo-tokens"); do line="$line $name $(printenv "$name")"; done
  printf '%%s\\n' "$line" >&2
fi
if [ -f "$dir/$key.sleep" ]; then exec sleep "$(cat "$dir/$key.sleep")"; fi
if [ -f "$dir/$key.out" ]; then cat "$dir/$key.out"; fi
if [ -f "$dir/$key.err" ]; then cat "$dir/$key.err" >&2; fi
if [ -f "$dir/$key.rc" ]; then exit "$(cat "$dir/$key.rc")"; fi
if [ -f "$dir/$key.out" ]; then exit 0; fi
printf 'gh: Not Found (HTTP 404)\\n' >&2
exit 1
"""


# --- fixtures ------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_real_platform(monkeypatch):
    """No real ``gh`` on PATH, no real Hub opener, no inherited snapshot settings."""
    assert shutil.which("gh", path=SYSTEM_PATH) is None, "a real gh would answer these tests"
    monkeypatch.setenv("PATH", SYSTEM_PATH)
    for name in (snap.ENV_FILE, snap.ENV_HF_DATASET, snap.ENV_HF_SPACE) + snap.SECRET_ENV:
        monkeypatch.delenv(name, raising=False)
    reached = []

    def real_opener_is_off(request, timeout):
        reached.append(request.full_url)
        raise urllib.error.URLError("the real opener is off in tests")

    monkeypatch.setattr(snap, "default_opener", real_opener_is_off)
    yield
    assert reached == [], "a test reached the real Hub opener: %r" % reached


@pytest.fixture
def gh(tmp_path, monkeypatch):
    """A fake ``gh`` first on PATH, before ``/usr/bin:/bin`` and nothing else."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    answers = tmp_path / "gh-answers"
    answers.mkdir()
    script = bin_dir / "gh"
    script.write_text(FAKE_GH % {"log": shlex.quote(str(log)),
                                 "answers": shlex.quote(str(answers))})
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + SYSTEM_PATH)

    def answer(path, out=None, err=None, rc=None, sleep=None):
        key = path.replace("/", "_")
        if out is not None:
            (answers / (key + ".out")).write_text(out if isinstance(out, str)
                                                  else json.dumps(out))
        if err is not None:
            (answers / (key + ".err")).write_text(err)
        if rc is not None:
            (answers / (key + ".rc")).write_text(str(rc))
        if sleep is not None:
            (answers / (key + ".sleep")).write_text(str(sleep))

    def all_ok():
        for path, body in zip(GH_PATHS, (REPO_BODY, VIEWS_BODY, CLONES_BODY, REFERRERS_BODY)):
            answer(path, out=body)

    def fail_all(err, rc=1, out=None):
        for path in GH_PATHS:
            answer(path, out=out, err=err, rc=rc)

    def calls():
        return [line.split(" ") for line in log.read_text().splitlines()] if log.exists() else []

    def echo_tokens(*names):
        """Make the fake print each named variable's value on one stderr line first."""
        (answers / "echo-tokens").write_text("\n".join(names or ("GH_TOKEN", "HF_TOKEN")))

    return types.SimpleNamespace(answer=answer, all_ok=all_ok, fail_all=fail_all,
                                 calls=calls, echo_tokens=echo_tokens, script=script)


class HubStub:
    """Stands in for ``urllib.request.urlopen``: answers by URL, records every request."""

    def __init__(self):
        self.answers = {}
        self.requests = []

    def answer(self, url, body=None, error=None):
        self.answers[url] = error if error is not None else (
            body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))

    def all_ok(self):
        self.answer(DATASET_URL, DATASET_BODY)
        self.answer(SPACE_URL, SPACE_BODY)

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        answer = self.answers[request.full_url]
        if isinstance(answer, BaseException):
            raise answer
        return io.BytesIO(answer)


@pytest.fixture
def hub():
    return HubStub()


@pytest.fixture
def cli(capsys, hub):
    """``main`` in process, with the Hub stub and the pinned clock."""
    def run(*argv):
        code = snap.main(list(argv), opener=hub, now=NOW)
        out, err = capsys.readouterr()
        return types.SimpleNamespace(code=code, out=out, err=err)
    return run


def http_error(code, error_code=None):
    headers = email.message.Message()
    if error_code:
        headers["X-Error-Code"] = error_code
    return urllib.error.HTTPError(DATASET_URL, code, "status %d" % code, headers,
                                  io.BytesIO(b'{"error": "status"}'))


def rows(path):
    with open(str(path), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.read().splitlines()]


def failed(err):
    return [line for line in err.splitlines() if line.startswith("adoption_snapshot_failed ")]


def every_id(out):
    return ["--repo", REPO, "--hf-dataset", DATASET, "--hf-space", SPACE, "--out", str(out)]


# --- the happy path (AC-1, AC-2) -----------------------------------------------------

def test_every_source_answering_appends_one_row_with_the_stubbed_values(tmp_path, gh, hub,
                                                                       cli):
    gh.all_ok()
    hub.all_ok()
    out = tmp_path / "snapshots" / "adoption.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_OK, result.err
    assert result.out == "adoption_snapshot_recorded file=%s\n" % out
    assert failed(result.err) == []
    [row] = rows(out)
    assert list(row) == ROW_KEYS
    assert row == {
        "date": "2026-11-23", "recorded_at": "2026-11-23T09:30:05Z", "repo": REPO,
        "github_stars": 42, "github_forks": 7, "github_views_14d": 310,
        "github_clones_14d": 55,
        "top_referrers": [{"referrer": "news.ycombinator.com", "count": 90, "uniques": 60},
                          {"referrer": "github.com", "count": 12, "uniques": 8}],
        "hf_dataset_downloads": 1234, "hf_space_likes": 17, "hf_space_runs": None,
        "sources": {"github": "ok", "github_traffic": "ok", "hf_dataset": "ok",
                    "hf_space": "ok", "hf_space_runs": "no-source"}}
    assert sorted(" ".join(call) for call in gh.calls()) == sorted("api " + p for p in GH_PATHS)

    assert cli(*every_id(out)).code == snap.EXIT_OK
    assert len(rows(out)) == 2, "a second run appends a second line"


def test_a_genuine_zero_is_a_value_and_is_recorded_as_zero_not_null(tmp_path, gh, hub, cli):
    """BR-7's other half: an ``ok`` source that read 0, or no referrers, records that."""
    gh.answer(GH_PATHS[0], out=dict(REPO_BODY, stargazers_count=0, forks_count=0))
    gh.answer(GH_PATHS[1], out=dict(VIEWS_BODY, count=0, uniques=0, views=[]))
    gh.answer(GH_PATHS[2], out=dict(CLONES_BODY, count=0, uniques=0, clones=[]))
    gh.answer(GH_PATHS[3], out=[])
    hub.answer(DATASET_URL, dict(DATASET_BODY, downloads=0))
    hub.answer(SPACE_URL, dict(SPACE_BODY, likes=0))
    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_OK, result.err
    [row] = rows(out)
    assert row["sources"] == {"github": "ok", "github_traffic": "ok", "hf_dataset": "ok",
                              "hf_space": "ok", "hf_space_runs": "no-source"}
    counts = ("github_stars", "github_forks", "github_views_14d", "github_clones_14d",
              "hf_dataset_downloads", "hf_space_likes")
    for field in counts:
        assert row[field] == 0 and type(row[field]) is int, (field, row[field])
        assert '"%s": 0' % field in out.read_text()
    assert row["top_referrers"] == []
    assert '"top_referrers": []' in out.read_text()
    assert sorted(" ".join(call) for call in gh.calls()) == sorted("api " + p for p in GH_PATHS)


def test_default_file_is_under_adlc_home_created_0600_with_0700_parents(gh, hub, cli):
    import adlc_home
    gh.all_ok()
    home = os.environ["ADLC_HOME"]
    assert not os.path.exists(home)
    result = cli("--repo", REPO)
    assert result.code == snap.EXIT_OK, result.err
    target = os.path.join(adlc_home.adlc_home(), "adlc", "adoption-snapshots.jsonl")
    assert target == os.path.join(home, "adlc", "adoption-snapshots.jsonl")
    assert result.out == "adoption_snapshot_recorded file=%s\n" % target
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.dirname(target)).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(home).st_mode) == 0o700
    assert len(rows(target)) == 1
    assert gh.calls(), "the fake gh answered"


def test_out_flag_and_env_override_the_default(tmp_path, monkeypatch, gh, cli):
    import adlc_home
    gh.all_ok()
    from_env = tmp_path / "env" / "snap.jsonl"
    from_flag = tmp_path / "flag" / "snap.jsonl"
    monkeypatch.setenv(snap.ENV_FILE, str(from_env))
    assert cli("--repo", REPO).code == snap.EXIT_OK
    assert len(rows(from_env)) == 1
    assert cli("--repo", REPO, "--out", str(from_flag)).code == snap.EXIT_OK
    assert len(rows(from_flag)) == 1 and len(rows(from_env)) == 1
    assert not os.path.exists(os.path.join(adlc_home.adlc_home(), *snap.DEFAULT_FILE))
    assert len(gh.calls()) == 8


# --- target refusals, each with its must-not-fire case (AC-3) ------------------------

def test_symlinked_target_is_refused_and_a_regular_file_beside_it_is_not(tmp_path, gh, cli):
    gh.all_ok()
    folder = tmp_path / "home"
    folder.mkdir()
    pointee = tmp_path / "elsewhere.jsonl"
    pointee.write_text("")
    link = folder / "snap.jsonl"
    os.symlink(str(pointee), str(link))
    dangling = folder / "dangling.jsonl"
    os.symlink(str(tmp_path / "missing.jsonl"), str(dangling))
    for target in (link, dangling):
        result = cli("--repo", REPO, "--out", str(target))
        assert result.code == snap.EXIT_USAGE
        assert "adoption-snapshot: refused file=%s" % target in result.err
        assert "symlink" in result.err
    assert pointee.read_text() == ""
    assert not (tmp_path / "missing.jsonl").exists()
    assert gh.calls() == [], "a refused target makes no call"

    regular = folder / "regular.jsonl"
    assert cli("--repo", REPO, "--out", str(regular)).code == snap.EXIT_OK
    assert len(rows(regular)) == 1
    assert gh.calls(), "the fake gh answered the accepted run"


def test_target_inside_the_toolkit_tree_is_refused(tmp_path, gh, cli):
    gh.all_ok()
    probe = os.path.join(snap.TOOLKIT, ".adoption-snapshot-test-%s" % tmp_path.name)
    link = tmp_path / "into-toolkit"
    os.symlink(snap.TOOLKIT, str(link))
    try:
        for out in (os.path.join(probe, "snap.jsonl"),
                    os.path.join(str(link), os.path.basename(probe), "snap.jsonl"),
                    os.path.join(snap.TOOLKIT, "snap.jsonl")):
            result = cli("--repo", REPO, "--out", out)
            assert result.code == snap.EXIT_USAGE, out
            assert "inside the toolkit's working tree" in result.err
            assert not os.path.lexists(probe)
            assert not os.path.lexists(os.path.join(snap.TOOLKIT, "snap.jsonl"))
    finally:
        if os.path.isdir(probe):
            shutil.rmtree(probe)
    assert gh.calls() == []
    snap.check_target(str(tmp_path / "outside.jsonl"))


def test_the_toolkit_is_matched_by_identity_not_by_a_name_prefix(tmp_path, monkeypatch):
    """A toolkit with no ``.git`` under tmp_path, so only the identity match can fire."""
    toolkit = tmp_path / "toolkit"
    (toolkit / "tools").mkdir(parents=True)
    monkeypatch.setattr(snap, "TOOLKIT", str(toolkit))
    for out in (toolkit / "snap.jsonl", toolkit / "tools" / "not-made" / "snap.jsonl"):
        with pytest.raises(snap.Refused, match="inside the toolkit's working tree"):
            snap.check_target(str(out))
    # Must not fire: a sibling that only shares the toolkit's name as a prefix.
    (tmp_path / "toolkit-sibling").mkdir()
    snap.check_target(str(tmp_path / "toolkit-sibling" / "snap.jsonl"))
    snap.check_target(str(tmp_path / "toolkit-not-made" / "snap.jsonl"))


def test_a_case_flipped_spelling_inside_the_toolkit_is_refused(tmp_path, monkeypatch):
    if not os.path.exists(str(tmp_path).swapcase()):
        pytest.skip("the filesystem is case-sensitive: a case-flipped path names another "
                    "folder, so there is no second spelling to refuse")
    flipped = os.path.join(snap.TOOLKIT, "snap.jsonl").swapcase()
    assert flipped != os.path.join(snap.TOOLKIT, "snap.jsonl")
    with pytest.raises(snap.Refused, match="inside the toolkit's working tree"):
        snap.check_target(flipped)
    # And with no .git to fall back on, by identity alone.
    toolkit = tmp_path / "toolkit"
    toolkit.mkdir()
    monkeypatch.setattr(snap, "TOOLKIT", str(toolkit))
    with pytest.raises(snap.Refused, match="inside the toolkit's working tree"):
        snap.check_target(os.path.join(str(toolkit).swapcase(), "snap.jsonl"))
    assert not os.path.lexists(str(toolkit / "snap.jsonl"))


def test_a_target_inside_any_git_work_tree_is_refused(tmp_path, gh, cli):
    gh.all_ok()
    clone = tmp_path / "some-clone"
    (clone / ".git").mkdir(parents=True)
    (clone / "docs").mkdir()
    worktree = tmp_path / "some-worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /nowhere/.git/worktrees/some-worktree\n")
    link = tmp_path / "into-clone"
    os.symlink(str(clone / "docs"), str(link))
    for out in (clone / "snap.jsonl", clone / "docs" / "snap.jsonl",
                clone / "not-made" / "deeper" / "snap.jsonl", worktree / "snap.jsonl",
                link / "snap.jsonl"):
        result = cli("--repo", REPO, "--out", str(out))
        assert result.code == snap.EXIT_USAGE, out
        assert "inside a git working tree" in result.err, result.err
        assert not os.path.lexists(str(out))
    assert not (clone / "not-made").exists()
    assert gh.calls() == [], "a refused target makes no call"

    # Must not fire: a folder beside the clone, and the default file under the temp home.
    beside = tmp_path / "beside" / "snap.jsonl"
    assert cli("--repo", REPO, "--out", str(beside)).code == snap.EXIT_OK
    assert len(rows(beside)) == 1
    home_file = os.path.join(os.environ["ADLC_HOME"], *snap.DEFAULT_FILE)
    result = cli("--repo", REPO)
    assert result.code == snap.EXIT_OK, result.err
    assert len(rows(home_file)) == 1
    assert gh.calls(), "the fake gh answered the accepted runs"


def test_a_refusal_names_the_target_as_given_and_not_the_work_tree_it_found(tmp_path,
                                                                            monkeypatch, gh, cli):
    """The flag's, the variable's or the default's spelling; never the resolved work tree."""
    gh.all_ok()
    clone = tmp_path / "planted-clone"
    (clone / ".git").mkdir(parents=True)
    (clone / "docs").mkdir()
    (tmp_path / "elsewhere").mkdir()
    link = tmp_path / "elsewhere" / "into-it"
    os.symlink(str(clone / "docs"), str(link))
    resolved = os.path.realpath(str(clone))
    given = os.path.join(str(link), "snap.jsonl")
    why = ' reason="the target is inside a git working tree, and no snapshot row is committed"'

    def refused(result, shown):
        assert result.code == snap.EXIT_USAGE
        assert result.err.splitlines() == ["adoption-snapshot: refused file=%s%s" % (shown, why)]
        assert resolved not in result.err and "planted-clone" not in result.err, result.err

    refused(cli("--repo", REPO, "--out", given), given)
    monkeypatch.chdir(str(link))
    refused(cli("--repo", REPO, "--out", "snap.jsonl"), "snap.jsonl")
    monkeypatch.setenv(snap.ENV_FILE, given)
    refused(cli("--repo", REPO), given)
    monkeypatch.delenv(snap.ENV_FILE)
    monkeypatch.setenv("ADLC_HOME", os.path.join(str(link), "state"))
    refused(cli("--repo", REPO), "<ADLC_HOME>/adlc/adoption-snapshots.jsonl")
    assert not os.path.lexists(str(clone / "docs" / "snap.jsonl"))
    assert not os.path.lexists(str(clone / "docs" / "state"))
    assert gh.calls() == [], "a refused target makes no call"


def test_a_target_that_is_a_directory_or_unwritable_is_refused(tmp_path, gh, cli):
    gh.all_ok()
    folder = tmp_path / "a-directory"
    folder.mkdir()
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    for out, why in ((folder, "not a regular file"),
                     (blocker / "snap.jsonl", "cannot be opened")):
        result = cli("--repo", REPO, "--out", str(out))
        assert result.code == snap.EXIT_USAGE
        assert why in result.err
    assert cli("--repo", REPO, "--out", "").code == snap.EXIT_USAGE
    assert gh.calls() == []


@pytest.mark.parametrize("how", ["raises", "short-count"])
def test_a_partial_write_is_cut_back_and_nothing_is_appended(tmp_path, monkeypatch, gh, cli,
                                                             how):
    gh.all_ok()
    out = tmp_path / "snap.jsonl"
    out.write_text('{"date": "2026-11-22", "repo": "%s"}\n' % REPO)
    out.chmod(0o600)
    before = out.read_bytes()
    target = os.stat(str(out))
    real_write = os.write
    cut = []

    def half_write(fd, data):
        """Write half the row, then fail or report the short count: once, on the target."""
        try:
            ours = not cut and os.path.samestat(os.fstat(fd), target)
        except OSError:
            ours = False
        if not ours:
            return real_write(fd, data)
        cut.append(len(data))
        written = real_write(fd, data[:len(data) // 2])
        if how == "raises":
            raise OSError(errno.ENOSPC, "No space left on device")
        return written

    monkeypatch.setattr(os, "write", half_write)
    result = cli("--repo", REPO, "--out", str(out))
    assert cut and cut[0] > 1, "the row went through the half-writing stub"
    assert out.read_bytes() == before, "the half line was cut back off"
    assert result.code == snap.EXIT_USAGE
    assert "nothing was appended" in result.err
    assert "adoption_snapshot_recorded" not in result.out


@pytest.mark.parametrize("whole", [True, False], ids=["whole-row", "short-row"])
def test_the_lock_is_taken_before_the_size_is_read_and_held_across_write_and_rollback(
        tmp_path, monkeypatch, whole):
    """Writers are serialized, so a rollback cannot truncate another writer's row away."""
    out = tmp_path / "snap.jsonl"
    out.write_text('{"date": "2026-11-22", "repo": "%s"}\n' % REPO)
    out.chmod(0o600)
    before = out.read_bytes()
    fd = snap.open_target(str(out))
    other = os.open(str(out), os.O_RDONLY)  # a second open file, as another writer has
    real_flock, real_fstat = fcntl.flock, os.fstat
    real_write, real_ftruncate = os.write, os.ftruncate
    events = []

    def held():
        """True while another open file of the target cannot take the lock."""
        try:
            real_flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            assert exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN), exc
            return True
        real_flock(other, fcntl.LOCK_UN)
        return False

    def flock(on, operation):
        if on == fd:
            events.append(("flock", operation))
        return real_flock(on, operation)

    def fstat(on):
        if on == fd:
            events.append(("fstat", held()))
        return real_fstat(on)

    def write(on, data):
        if on != fd:
            return real_write(on, data)
        events.append(("write", held()))
        return real_write(on, data if whole else data[:len(data) // 2])

    def ftruncate(on, size):
        if on == fd:
            events.append(("ftruncate", held()))
        return real_ftruncate(on, size)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(snap, "fcntl", types.SimpleNamespace(
                flock=flock, LOCK_EX=fcntl.LOCK_EX, LOCK_UN=fcntl.LOCK_UN))
            for name, stub in (("fstat", fstat), ("write", write), ("ftruncate", ftruncate)):
                patch.setattr(os, name, stub)
            if whole:
                snap.append_line(str(out), fd, '{"row": 1}\n')
            else:
                with pytest.raises(snap.Refused, match="nothing was appended"):
                    snap.append_line(str(out), fd, '{"row": 1}\n')
        assert not held(), "the lock is released once the row is written or rolled back"
    finally:
        os.close(other)
        os.close(fd)
    middle = [("ftruncate", True)] if not whole else []
    assert events == ([("flock", fcntl.LOCK_EX), ("fstat", True), ("write", True)] + middle
                      + [("flock", fcntl.LOCK_UN)]), events
    assert out.read_bytes() == (before + b'{"row": 1}\n' if whole else before)


@pytest.mark.parametrize("lock", ["flock-fails", "no-fcntl"])
@pytest.mark.parametrize("how", ["raises", "short-count"])
def test_without_the_lock_a_partial_write_is_left_not_cut_back_and_said(tmp_path, monkeypatch,
                                                                        gh, cli, lock, how):
    """With no lock, truncating could cut another writer's row: the run says what it left."""
    gh.all_ok()
    out = tmp_path / "snap.jsonl"
    out.write_text('{"date": "2026-11-22", "repo": "%s"}\n' % REPO)
    out.chmod(0o600)
    before = out.read_bytes()
    target = os.stat(str(out))
    real_write, real_ftruncate = os.write, os.ftruncate
    cut, truncated = [], []

    def no_locks(fd, operation):
        raise OSError(errno.ENOLCK, "No locks available")

    def half_write(fd, data):
        try:
            ours = not cut and os.path.samestat(os.fstat(fd), target)
        except OSError:
            ours = False
        if not ours:
            return real_write(fd, data)
        cut.append(len(data))
        written = real_write(fd, data[:len(data) // 2])
        if how == "raises":
            raise OSError(errno.ENOSPC, "No space left on device")
        return written

    def ftruncate(fd, size):
        truncated.append(size)
        return real_ftruncate(fd, size)

    with monkeypatch.context() as patch:
        patch.setattr(snap, "fcntl", None if lock == "no-fcntl" else types.SimpleNamespace(
            flock=no_locks, LOCK_EX=fcntl.LOCK_EX, LOCK_UN=fcntl.LOCK_UN))
        patch.setattr(os, "write", half_write)
        patch.setattr(os, "ftruncate", ftruncate)
        result = cli("--repo", REPO, "--out", str(out))
    assert cut and cut[0] > 1, "the row went through the half-writing stub"
    assert truncated == [], "no rollback by truncation without the lock"
    after = out.read_bytes()
    assert after.startswith(before) and len(after) == len(before) + cut[0] // 2
    assert result.code == snap.EXIT_USAGE
    [line] = result.err.splitlines()
    assert line.startswith("adoption-snapshot: refused file=%s reason=" % out), line
    assert "a partial row may have been left in %s" % out in line
    assert "nothing was appended" not in line
    assert "adoption_snapshot_recorded" not in result.out


def test_a_looser_existing_file_is_made_0600_with_one_note(tmp_path, gh, cli):
    gh.all_ok()
    loose = tmp_path / "loose.jsonl"
    loose.write_text("")
    loose.chmod(0o644)
    result = cli("--repo", REPO, "--out", str(loose))
    assert result.code == snap.EXIT_OK, result.err
    assert stat.S_IMODE(os.stat(str(loose)).st_mode) == 0o600
    assert result.err.splitlines() == [
        "adoption-snapshot: tightened %s from 0644 to 0600" % loose]
    assert len(rows(loose)) == 1
    # Must not fire: a file already 0600 is left as it is, with no note.
    result = cli("--repo", REPO, "--out", str(loose))
    assert result.code == snap.EXIT_OK and result.err == ""
    assert len(rows(loose)) == 2
    assert gh.calls()


def test_a_fifo_swapped_in_after_the_check_is_refused_without_blocking(tmp_path):
    """``open_target`` alone: ``check_target`` already refuses a FIFO that is there first."""
    fifo = tmp_path / "snap.jsonl"
    os.mkfifo(str(fifo))
    outcome = []

    def attempt():
        try:
            outcome.append(snap.open_target(str(fifo)))
        except snap.Refused as exc:
            outcome.append(exc)

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(5)
    if worker.is_alive():
        reader = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)  # release the blocked open
        worker.join(5)
        os.close(reader)
        pytest.fail("opening a FIFO with no reader blocked")
    [refused] = outcome
    assert isinstance(refused, snap.Refused) and "cannot be opened" in refused.reason

    # With a reader present the open succeeds, and fstat refuses what it opened.
    reader = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)
    try:
        with pytest.raises(snap.Refused, match="not a regular file"):
            snap.open_target(str(fifo))
    finally:
        os.close(reader)


# --- failures: honest classes, null never zero (BR-7, AC-4, AC-5, AC-6) --------------

def test_unauthenticated_gh_reports_failed_and_prints_no_token(tmp_path, monkeypatch, gh, hub,
                                                              cli):
    monkeypatch.setenv("GH_TOKEN", CANARY_GH)
    monkeypatch.setenv("HF_TOKEN", CANARY_HF)
    gh.fail_all(GH_NO_LOGIN, rc=4)
    gh.echo_tokens()
    hub.all_ok()
    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))

    assert result.code == snap.EXIT_FAILED
    assert [line.split(" ")[1:3] for line in failed(result.err)] == [
        ["source=github", "class=auth-missing"], ["source=github_traffic", "class=auth-missing"]]
    [row] = rows(out)
    assert row["sources"]["github"] == row["sources"]["github_traffic"] == "auth-missing"
    for field in GITHUB_FIELDS + TRAFFIC_FIELDS:
        assert row[field] is None, field
    assert row["hf_dataset_downloads"] == 1234 and row["hf_space_likes"] == 17
    assert result.out == "adoption_snapshot_recorded file=%s\n" % out

    # The fake inherited both tokens and echoed them; what reached the output was scrubbed.
    assert "GH_TOKEN [REDACTED] HF_TOKEN [REDACTED]" in result.err
    for canary in (CANARY_GH, CANARY_HF):
        assert canary not in result.out
        assert canary not in result.err
        assert canary not in out.read_text()
    assert gh.calls() == [["api", GH_PATHS[0]], ["api", GH_PATHS[1]]], \
        "the fake ran, and the traffic source stopped at its first failed read"


@pytest.mark.parametrize("cls", [
    snap.AUTH_MISSING, snap.FORBIDDEN, snap.NOT_FOUND, snap.RATE_LIMITED, snap.NETWORK,
    snap.TOOL_MISSING, snap.BAD_RESPONSE, "bad-response-partial", snap.UNCLASSIFIED])
def test_failed_source_leaves_fields_null_never_zero(tmp_path, gh, hub, cli, monkeypatch, cls):
    gh_err = {
        snap.AUTH_MISSING: "gh: Bad credentials (HTTP 401)\n",
        snap.FORBIDDEN: "HTTP 403: Must have push access to repository "
                        "(https://api.github.com/repos/%s/traffic/views)\n" % REPO,
        snap.NOT_FOUND: "gh: Not Found (HTTP 404)\n",
        snap.RATE_LIMITED: "gh: API rate limit exceeded for user ID 1000001. (HTTP 403)\n",
        snap.NETWORK: "error connecting to api.github.com\n"
                      "check your internet connection or https://githubstatus.com\n",
        snap.UNCLASSIFIED: "gh: Server Error (HTTP 500)\n",
    }
    hub_error = {
        snap.AUTH_MISSING: http_error(401), snap.FORBIDDEN: http_error(403),
        snap.NOT_FOUND: http_error(404), snap.RATE_LIMITED: http_error(429),
        snap.NETWORK: urllib.error.URLError(socket.gaierror(8, "nodename nor servname "
                                                              "provided, or not known")),
        snap.TOOL_MISSING: http_error(404), snap.UNCLASSIFIED: http_error(502),
    }
    expect_gh = expect_hub = cls
    if cls == snap.TOOL_MISSING:
        monkeypatch.setenv("PATH", str(tmp_path / "empty") + os.pathsep + SYSTEM_PATH)
        expect_hub = snap.NOT_FOUND
    elif cls == snap.BAD_RESPONSE:
        gh.fail_all(None, rc=0, out="<html>not json</html>")
        hub.answer(DATASET_URL, b"<html>not json</html>")
    elif cls == "bad-response-partial":
        # Part of each answer is there: still nothing of the source is recorded.
        gh.all_ok()
        gh.answer(GH_PATHS[0], out={"stargazers_count": 5})
        gh.answer(GH_PATHS[2], out={"uniques": 3})
        hub.answer(DATASET_URL, {"id": DATASET, "downloads": "1234"})
        expect_gh = expect_hub = snap.BAD_RESPONSE
    else:
        gh.fail_all(gh_err[cls])
    if cls in hub_error:
        hub.answer(DATASET_URL, error=hub_error[cls])
    # Must not fire: an ok source that read a zero records the zero.
    hub.answer(SPACE_URL, dict(SPACE_BODY, likes=0))

    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_FAILED
    [row] = rows(out)
    assert row["sources"] == {"github": expect_gh, "github_traffic": expect_gh,
                              "hf_dataset": expect_hub, "hf_space": "ok",
                              "hf_space_runs": "no-source"}
    for field in GITHUB_FIELDS + TRAFFIC_FIELDS + ("hf_dataset_downloads", "hf_space_runs"):
        assert row[field] is None, (field, row[field])
        assert '"%s": null' % field in out.read_text()
    assert row["hf_space_likes"] == 0 and row["hf_space_likes"] is not None
    assert [line.split(" ")[1:3] for line in failed(result.err)] == [
        ["source=github", "class=" + expect_gh], ["source=github_traffic", "class=" + expect_gh],
        ["source=hf_dataset", "class=" + expect_hub]]
    if cls == snap.TOOL_MISSING:
        assert gh.calls() == [], "no gh was on PATH, so none ran"
    else:
        assert gh.calls(), "the fake gh answered"


def test_hf_space_runs_is_no_source_and_unconfigured_hub_ids_are_not_failures(tmp_path, gh,
                                                                             hub, cli):
    gh.all_ok()
    out = tmp_path / "snap.jsonl"
    result = cli("--repo", REPO, "--out", str(out))
    assert result.code == snap.EXIT_OK, result.err
    assert failed(result.err) == []
    [row] = rows(out)
    assert row["sources"]["hf_dataset"] == row["sources"]["hf_space"] == "not-configured"
    assert row["sources"]["hf_space_runs"] == "no-source"
    assert row["hf_dataset_downloads"] is None and row["hf_space_likes"] is None
    assert row["hf_space_runs"] is None
    assert hub.requests == []
    assert len(gh.calls()) == 4


def test_hub_ids_come_from_the_environment(tmp_path, monkeypatch, gh, hub, cli):
    gh.all_ok()
    hub.all_ok()
    monkeypatch.setenv(snap.ENV_HF_DATASET, DATASET)
    monkeypatch.setenv(snap.ENV_HF_SPACE, SPACE)
    out = tmp_path / "snap.jsonl"
    assert cli("--repo", REPO, "--out", str(out)).code == snap.EXIT_OK
    assert [request.full_url for request, _ in hub.requests] == [DATASET_URL, SPACE_URL]
    assert rows(out)[0]["hf_space_likes"] == 17
    assert gh.calls()


def test_traffic_source_takes_the_class_of_any_failed_read(tmp_path, gh, hub, cli):
    gh.all_ok()
    gh.answer(GH_PATHS[3], err="HTTP 403: Must have push access to repository\n", rc=1)
    out = tmp_path / "snap.jsonl"
    result = cli("--repo", REPO, "--out", str(out))
    assert result.code == snap.EXIT_FAILED
    [row] = rows(out)
    assert row["sources"]["github"] == "ok" and row["github_stars"] == 42
    assert row["sources"]["github_traffic"] == "forbidden"
    for field in TRAFFIC_FIELDS:
        assert row[field] is None, "views and clones were read, but the source failed"
    assert [line.split(" ")[1:3] for line in failed(result.err)] == [
        ["source=github_traffic", "class=forbidden"]]
    assert len(gh.calls()) == 4


def test_gh_missing_from_path_is_tool_missing(tmp_path, cli):
    assert shutil.which("gh") is None
    out = tmp_path / "snap.jsonl"
    result = cli("--repo", REPO, "--out", str(out))
    assert result.code == snap.EXIT_FAILED
    [row] = rows(out)
    assert row["sources"]["github"] == row["sources"]["github_traffic"] == "tool-missing"
    assert 'reason="gh is not on PATH"' in result.err


def test_timeouts_are_network(tmp_path, monkeypatch, gh, hub, cli):
    monkeypatch.setattr(snap, "GH_TIMEOUT", 0.5)
    gh.all_ok()
    gh.answer(GH_PATHS[0], sleep=10)
    hub.answer(DATASET_URL, error=socket.timeout("timed out"))
    hub.answer(SPACE_URL, error=urllib.error.URLError(socket.timeout("timed out")))
    out = tmp_path / "snap.jsonl"
    started = time.monotonic()
    result = cli(*every_id(out))
    assert time.monotonic() - started < 8, "the timeout cut the hung gh short"
    assert result.code == snap.EXIT_FAILED
    sources = rows(out)[0]["sources"]
    assert sources["github"] == sources["hf_dataset"] == sources["hf_space"] == "network"
    assert sources["github_traffic"] == "ok"
    assert [request_timeout for _, request_timeout in hub.requests] == [snap.HUB_TIMEOUT] * 2
    assert ["api", GH_PATHS[0]] in gh.calls()


# --- the classifier (AC-7, LESSON-581) -----------------------------------------------

#: Real ``gh`` stderr and the class each must take.
GH_TABLE = [
    ("gh: Not Found (HTTP 404)", snap.NOT_FOUND),
    ("HTTP 404: Not Found (https://api.github.com/repos/example-org/missing)", snap.NOT_FOUND),
    ("GraphQL: Could not resolve to a Repository with the name 'example-org/missing'. "
     "(repository)", snap.NOT_FOUND),
    ("HTTP 403: Must have push access to repository "
     "(https://api.github.com/repos/example-org/example-repo/traffic/views)", snap.FORBIDDEN),
    ("gh: Resource not accessible by integration (HTTP 403)", snap.FORBIDDEN),
    (GH_NO_LOGIN, snap.AUTH_MISSING),
    ("gh: Bad credentials (HTTP 401)", snap.AUTH_MISSING),
    ("HTTP 401: Bad credentials (https://api.github.com/repos/example-org/example-repo)",
     snap.AUTH_MISSING),
    ("gh: Requires authentication (HTTP 401)", snap.AUTH_MISSING),
    ("You are not logged into any GitHub hosts. Run gh auth login to authenticate.",
     snap.AUTH_MISSING),
    ("gh: API rate limit exceeded for user ID 1000001. (HTTP 403)", snap.RATE_LIMITED),
    ("gh: You have exceeded a secondary rate limit. Please wait a few minutes before you try "
     "again. (HTTP 403)", snap.RATE_LIMITED),
    ("HTTP 429: Too Many Requests", snap.RATE_LIMITED),
    ("error connecting to api.github.com\n"
     "check your internet connection or https://githubstatus.com", snap.NETWORK),
    ('Get "https://api.github.com/repos/example-org/example-repo": dial tcp: lookup '
     'api.github.com: no such host', snap.NETWORK),
    ("curl: (6) Could not resolve host: api.github.com", snap.NETWORK),
    ('Get "https://api.github.com/": net/http: TLS handshake timeout', snap.NETWORK),
    ("gh: Server Error (HTTP 500)", snap.UNCLASSIFIED),
    ("HTTP 502: Bad Gateway", snap.UNCLASSIFIED),
    ("something no backend has said before", snap.UNCLASSIFIED),
    ("", snap.UNCLASSIFIED),
]

#: A text one pattern must not take from another class's pattern.
GH_NEGATIVE = [
    ("gh: API rate limit exceeded for user ID 1000001. (HTTP 403)", snap.FORBIDDEN),
    ("HTTP 403: Must have push access to repository", snap.RATE_LIMITED),
    ("HTTP 403: Must have push access to repository", snap.AUTH_MISSING),
    ("curl: (6) Could not resolve host: api.github.com", snap.NOT_FOUND),
    ("GraphQL: Could not resolve to a Repository with the name 'x/y'.", snap.NETWORK),
    ("gh: Not Found (HTTP 404)", snap.AUTH_MISSING),
    ("gh: Bad credentials (HTTP 401)", snap.FORBIDDEN),
    ("gh: Server Error (HTTP 500)", snap.NETWORK),
    ("HTTP 502: Bad Gateway", snap.NETWORK),
]


@pytest.mark.parametrize("text,cls", GH_TABLE)
def test_gh_error_texts_map_to_their_class(text, cls):
    assert snap.classify_gh(text, 1) == cls


@pytest.mark.parametrize("text,not_cls", GH_NEGATIVE)
def test_gh_patterns_do_not_take_another_class_text(text, not_cls):
    assert snap.classify_gh(text, 1) != not_cls


def test_classifier_default_is_unclassified_and_exit_4_is_auth():
    assert snap.classify_gh("an error text nobody taught it", 1) == snap.UNCLASSIFIED
    assert snap.classify_gh("", None) == snap.UNCLASSIFIED
    assert snap.classify_gh("", snap.GH_EXIT_AUTH) == snap.AUTH_MISSING
    assert snap.classify_gh("gh: Not Found (HTTP 404)", snap.GH_EXIT_AUTH) == snap.NOT_FOUND
    assert snap.classify_hub_status(418) == snap.UNCLASSIFIED


@pytest.mark.parametrize("status,error_code,cls", [
    (401, None, snap.AUTH_MISSING), (401, "RepoNotFound", snap.NOT_FOUND),
    (403, None, snap.FORBIDDEN), (404, None, snap.NOT_FOUND),
    (404, "RepoNotFound", snap.NOT_FOUND), (429, None, snap.RATE_LIMITED),
    (400, None, snap.UNCLASSIFIED), (500, None, snap.UNCLASSIFIED),
    (502, None, snap.UNCLASSIFIED), (503, None, snap.UNCLASSIFIED),
    (403, "SomeCodeNotTaught", snap.FORBIDDEN),
])
def test_hub_statuses_map_to_their_class(status, error_code, cls):
    assert snap.classify_hub_status(status, error_code) == cls


def test_hub_status_negatives():
    assert snap.classify_hub_status(500) != snap.NETWORK, "a 5xx is not taught as transient"
    assert snap.classify_hub_status(401, "RepoNotFound") != snap.AUTH_MISSING
    assert snap.classify_hub_status(429) != snap.FORBIDDEN


@pytest.mark.parametrize("answer,cls", [
    (http_error(404), snap.NOT_FOUND),
    (http_error(401, "RepoNotFound"), snap.NOT_FOUND),
    (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), snap.NETWORK),
    (urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")), snap.NETWORK),
    (socket.timeout("timed out"), snap.NETWORK),
    (ConnectionResetError(54, "Connection reset by peer"), snap.NETWORK),
    (http.client.IncompleteRead(b"{"), snap.BAD_RESPONSE),
    (b"<html>not json</html>", snap.BAD_RESPONSE),
    (b"\xff\xfe not utf-8", snap.BAD_RESPONSE),
    (b'{"id": "x"}', snap.BAD_RESPONSE),
    (b'{"downloads": -1}', snap.BAD_RESPONSE),
    (b'{"downloads": true}', snap.BAD_RESPONSE),
    (b'{"downloads": "12"}', snap.BAD_RESPONSE),
    (b'["downloads", 12]', snap.BAD_RESPONSE),
    (b'{"downloads": 0}', snap.OK),
])
def test_hub_answers_map_to_their_class(hub, answer, cls):
    if isinstance(answer, bytes):
        hub.answer(DATASET_URL, answer)
    else:
        hub.answer(DATASET_URL, error=answer)
    outcome = snap.read_hf_dataset(hub, DATASET)
    assert outcome.cls == cls
    assert outcome.values == ({"hf_dataset_downloads": 0} if cls == snap.OK else {})


def test_an_oversized_hub_answer_is_bad_response(monkeypatch, hub):
    monkeypatch.setattr(snap, "HUB_MAX_BYTES", 16)
    hub.answer(DATASET_URL, dict(DATASET_BODY))
    assert snap.read_hf_dataset(hub, DATASET).cls == snap.BAD_RESPONSE


def test_a_surprise_in_one_source_is_unclassified_and_keeps_the_others(tmp_path, gh, hub, cli):
    gh.all_ok()
    hub.answer(DATASET_URL, error=ValueError("a stub surprise"))
    hub.answer(SPACE_URL, SPACE_BODY)
    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_FAILED
    [row] = rows(out)
    assert row["sources"]["hf_dataset"] == "unclassified"
    assert row["hf_dataset_downloads"] is None
    assert row["hf_space_likes"] == 17 and row["github_stars"] == 42
    assert gh.calls()


def test_class_set_is_adr_7s_and_every_rule_emits_a_member():
    assert snap.CLASSES == ("ok", "auth-missing", "forbidden", "not-found", "rate-limited",
                            "network", "tool-missing", "bad-response", "not-configured",
                            "no-source", "unclassified")
    emitted = ({cls for _, cls in snap.GH_RULES} | set(snap.HUB_ERROR_CODES.values())
               | set(snap.HUB_STATUSES.values()))
    assert emitted <= set(snap.CLASSES)
    assert set(snap.NOT_FAILURES) == {"ok", "not-configured", "no-source"}


def test_class_and_field_names_are_fixed_identifiers_never_redacted(tmp_path, gh, cli):
    """LESSON-744: identifiers are checked by format and printed as they are."""
    fields = [field for _, names in snap.SOURCE_FIELDS for field in names]
    sources = [source for source, _ in snap.SOURCE_FIELDS]
    assert all(snap.CLASS_RE.match(cls) for cls in snap.CLASSES)
    assert all(snap.FIELD_RE.match(name) for name in fields + sources)
    for name in list(snap.CLASSES) + fields + sources:
        assert not credential_redact.find(name), name
    gh.fail_all("gh: Bad credentials (HTTP 401)\n")
    result = cli("--repo", REPO, "--out", str(tmp_path / "snap.jsonl"))
    assert "source=github_traffic class=auth-missing " in result.err
    assert gh.calls()


# --- read-only, and no token anywhere (BR-6, AC-8, AC-9) -----------------------------

def _string_constants(tree):
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def test_every_platform_call_is_a_read(tmp_path, gh, hub, cli):
    gh.all_ok()
    hub.all_ok()
    assert cli(*every_id(tmp_path / "snap.jsonl")).code == snap.EXIT_OK

    calls = gh.calls()
    assert sorted(calls) == sorted(["api", path] for path in GH_PATHS)
    for call in calls:
        assert len(call) == 2 and call[0] == "api" and not call[1].startswith("-"), call

    assert [request.full_url for request, _ in hub.requests] == [DATASET_URL, SPACE_URL]
    for request, _ in hub.requests:
        assert request.get_method() == "GET"
        assert request.data is None
        assert request.full_url.startswith(snap.HUB_API)

    # And in the source: no write flag or method is spelled, the one gh argv is
    # [gh, "api", path], and the one Request is a GET with no body.
    with open(snap.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    write_words = {"--method", "-X", "-f", "-F", "--field", "--raw-field", "--input",
                   "POST", "PUT", "PATCH", "DELETE"}
    assert not write_words & _string_constants(tree)
    runs = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == "run"]
    assert len(runs) == 1
    argv = runs[0].args[0]
    assert isinstance(argv, ast.List) and len(argv.elts) == 3
    assert isinstance(argv.elts[1], ast.Constant) and argv.elts[1].value == "api"
    requests = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "Request"]
    assert len(requests) == 1
    keywords = {kw.arg: kw.value for kw in requests[0].keywords}
    assert len(requests[0].args) == 1 and "data" not in keywords
    assert isinstance(keywords["method"], ast.Constant) and keywords["method"].value == "GET"


def test_hf_token_is_a_bearer_header_only_when_set(tmp_path, monkeypatch, gh, hub, cli):
    gh.all_ok()
    hub.all_ok()
    out = tmp_path / "snap.jsonl"
    assert cli(*every_id(out)).code == snap.EXIT_OK
    for request, _ in hub.requests:
        assert request.get_header("Authorization") is None

    monkeypatch.setenv("HF_TOKEN", CANARY_HF)
    hub.requests.clear()
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_OK
    for request, _ in hub.requests:
        assert request.get_header("Authorization") == "Bearer " + CANARY_HF
        assert "Authorization" in request.unredirected_hdrs, "a redirect does not carry it"
    assert CANARY_HF not in result.out + result.err + out.read_text()
    assert gh.calls()


def test_backend_text_holding_a_token_is_scrubbed_before_it_is_printed(tmp_path, monkeypatch,
                                                                      gh, hub, cli):
    monkeypatch.setenv("GH_TOKEN", CANARY_GH)
    monkeypatch.setenv("HF_TOKEN", CANARY_HF)
    # The token by value, and a credential shape no variable here holds.
    gh.fail_all("gh: Bad credentials (HTTP 401)\nAuthorization: Bearer %s\n"
                "retrying with EXAMPLE_API_KEY=not-a-real-value-789\n" % CANARY_GH)
    hub.answer(DATASET_URL, error=urllib.error.URLError("proxy refused " + CANARY_HF))
    hub.answer(SPACE_URL, SPACE_BODY)
    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_FAILED
    assert 'reason="proxy refused [REDACTED]"' in result.err
    assert "Authorization: Bearer [REDACTED] | retrying with [REDACTED]" in result.err
    assert "not-a-real-value-789" not in result.err
    for canary in (CANARY_GH, CANARY_HF):
        assert canary not in result.out + result.err + out.read_text()
    assert gh.calls()


@pytest.mark.parametrize("name", snap.SECRET_ENV)
def test_every_token_variable_is_scrubbed_from_every_output(tmp_path, monkeypatch, gh, hub,
                                                            cli, name):
    canary = "canary-%s-not-real" % name.lower().replace("_", "-")
    assert len(canary) >= snap.SECRET_MIN
    monkeypatch.setenv(name, canary)
    gh.fail_all(GH_NO_LOGIN, rc=4)
    gh.echo_tokens(name)
    hub.answer(DATASET_URL, error=urllib.error.URLError("proxy refused " + canary))
    hub.answer(SPACE_URL, SPACE_BODY)
    out = tmp_path / "snap.jsonl"
    result = cli(*every_id(out))
    assert result.code == snap.EXIT_FAILED
    # The fake echoed the value and the Hub stub carried it: both reached a reason, scrubbed.
    assert "gh: debug: %s [REDACTED]" % name in result.err, result.err
    assert 'reason="proxy refused [REDACTED]"' in result.err
    for text in (result.out, result.err, out.read_text()):
        assert canary not in text
    assert gh.calls()


# --- the CLI -------------------------------------------------------------------------

@pytest.mark.parametrize("flag,value", [
    ("--repo", "noslash"), ("--repo", "a/b/c"), ("--repo", "../x"), ("--repo", "a/.."),
    ("--repo", "a b/c"), ("--repo", "owner/name?per_page=1"), ("--repo", ""),
    ("--hf-dataset", "https://huggingface.co/datasets/a/b"), ("--hf-dataset", "a/b#c"),
    ("--hf-space", "a/b/../c"), ("--hf-space", "./x"),
])
def test_an_id_out_of_format_is_refused_before_any_call(tmp_path, gh, hub, cli, flag, value):
    gh.all_ok()
    hub.all_ok()
    argv = ["--repo", REPO, "--out", str(tmp_path / "snap.jsonl")]
    argv += [flag, value]
    result = cli(*argv)
    assert result.code == snap.EXIT_USAGE
    assert "adoption-snapshot: %s must be OWNER/NAME" % flag in result.err
    assert value not in result.err or value == ""
    assert gh.calls() == [] and hub.requests == []
    assert not (tmp_path / "snap.jsonl").exists()


def test_an_env_id_out_of_format_is_refused_and_named(tmp_path, monkeypatch, gh, cli):
    monkeypatch.setenv(snap.ENV_HF_SPACE, "not an id")
    result = cli("--repo", REPO, "--out", str(tmp_path / "snap.jsonl"))
    assert result.code == snap.EXIT_USAGE
    assert snap.ENV_HF_SPACE in result.err
    assert gh.calls() == []


def test_usage_errors_exit_2_and_help_exits_0(monkeypatch, gh, cli):
    assert cli("--no-such-flag").code == snap.EXIT_USAGE
    assert cli("--help").code == snap.EXIT_OK
    monkeypatch.setenv("ADLC_HOME", "relative/home")
    result = cli("--repo", REPO)
    assert result.code == snap.EXIT_USAGE and "ADLC_HOME" in result.err
    assert gh.calls() == []


#: The two event lines keep the spec's names; every other diagnostic has one prefix.
EVENT_PREFIXES = ("adoption_snapshot_recorded ", "adoption_snapshot_failed ")
PREFIX = "adoption-snapshot: "


def test_every_diagnostic_line_is_an_event_line_or_has_the_one_prefix(tmp_path, monkeypatch,
                                                                     gh, hub, cli):
    gh.all_ok()
    hub.answer(DATASET_URL, error=http_error(404))
    link = tmp_path / "link.jsonl"
    os.symlink(str(tmp_path / "missing.jsonl"), str(link))
    loose = tmp_path / "loose.jsonl"
    loose.write_text("")
    loose.chmod(0o644)
    results = [cli("--no-such-flag"), cli("--repo", "noslash"),
               cli("--repo", REPO, "--out", str(link)),
               cli("--repo", REPO, "--hf-dataset", DATASET, "--out", str(loose))]
    monkeypatch.setenv("ADLC_HOME", "relative/home")
    results.append(cli("--repo", REPO))
    lines = [line for result in results for line in (result.out + result.err).splitlines()]
    for line in lines:
        assert line.startswith(EVENT_PREFIXES + (PREFIX,)), line
    shapes = {line.split(" ")[0] for line in lines}
    assert shapes == {"adoption-snapshot:", "adoption_snapshot_recorded",
                      "adoption_snapshot_failed"}, shapes
    assert len([line for line in lines if line.startswith(PREFIX)]) == len(results), \
        "one line each: argparse, a bad id, a refused target, the 0600 note, ADLC_HOME"

    # And in the source: no other ``adoption_snapshot_<word>`` line shape is spelled.
    with open(snap.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    spelled = {match for text in _string_constants(tree)
               for match in re.findall(r"adoption_snapshot_[a-z_]+", text)}
    assert spelled == {"adoption_snapshot_recorded", "adoption_snapshot_failed"}, spelled


def test_the_tools_adlc_folder_is_appended_once_and_shadows_nothing(monkeypatch):
    adlc_dir = os.path.join(snap.TOOLKIT, "tools", "adlc")
    without = [entry for entry in sys.path if entry != adlc_dir]
    for start in (without, without + [adlc_dir], [adlc_dir] + without):
        monkeypatch.setattr(sys, "path", list(start))
        spec = importlib.util.spec_from_file_location("adoption_snapshot_again", SCRIPT)
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
        expected = start if adlc_dir in start else start + [adlc_dir]
        assert sys.path == expected, "sys.path[:2] = %r" % sys.path[:2]


def test_dry_run_prints_the_row_and_appends_nothing(tmp_path, gh, hub, cli):
    gh.all_ok()
    hub.all_ok()
    out = tmp_path / "not-made" / "snap.jsonl"
    result = cli(*(every_id(out) + ["--dry-run"]))
    assert result.code == snap.EXIT_OK
    row = json.loads(result.out)
    assert row["github_stars"] == 42 and row["date"] == "2026-11-23"
    assert "adoption_snapshot_recorded" not in result.out
    assert not (tmp_path / "not-made").exists()
    assert len(gh.calls()) == 4


def test_runs_by_path_with_the_fake_gh(tmp_path, gh):
    gh.all_ok()
    out = tmp_path / "snap.jsonl"
    proc = subprocess.run([sys.executable, SCRIPT, "--repo", REPO, "--out", str(out)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, env=dict(os.environ), timeout=60)
    assert proc.returncode == snap.EXIT_OK, proc.stderr
    assert proc.stdout == "adoption_snapshot_recorded file=%s\n" % out
    [row] = rows(out)
    assert row["sources"]["hf_dataset"] == "not-configured"
    assert row["github_views_14d"] == 310
    assert len(gh.calls()) == 4


def test_module_imports_only_the_standard_library_and_named_siblings():
    with open(snap.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            names.add(node.module.split(".")[0])
    siblings = {"adlc_home", "credential_redact"}
    assert siblings <= names
    adlc_dir = os.path.realpath(os.path.join(snap.TOOLKIT, "tools", "adlc"))
    for name in siblings:
        origin = os.path.realpath(importlib.util.find_spec(name).origin)
        assert origin == os.path.join(adlc_dir, name + ".py")
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    for name in sorted(names - siblings):
        origin = importlib.util.find_spec(name).origin
        assert origin in ("built-in", "frozen") or (
            os.path.realpath(origin).startswith(stdlib + os.sep)
            and "site-packages" not in origin), (name, origin)
