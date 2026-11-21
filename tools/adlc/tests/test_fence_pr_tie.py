"""The PR tie (REQ-719 ADR-3; BR-9 to BR-12, BR-14; AC-8 to AC-10): a PR number bound to a
placeholder with the PR mark must be the open, same-repository PR of the branch checked out
where the runner was called, and the runner reads it back through the forge adapter after its
value and sandbox checks and before any command of the fence.

Every case runs offline against the stateful mock forge (``tools/adlc/forge_mock.py``) in a
throwaway store, or against stub ``gh`` and ``az`` on the GitHub and Azure DevOps backends. The
mock writes ``calls.log`` only for a call it answers, not for an error-class scenario, so forge
calls are counted under a scenario that is not one.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402
from test_fence_run import (PR_BRANCH, _git, forge_env, memo_census, mock_pr,  # noqa: E402
                            pr_store, repo_wc)

TOOLKIT = toolkit_root.toolkit_root()
OTHER_BRANCH = "feat/REQ-902-other"
#: The argv the runner's read of one value hands the forge after the value itself.
TIE_ARGV = ["--fields", ",".join(fc.PR_TIE_FIELDS)]


@pytest.fixture(scope="module")
def records():
    """The merged census: what fence-run accepts, whichever harness calls."""
    return fc.census(TOOLKIT)


@pytest.fixture
def cached(monkeypatch, records):
    memo_census(monkeypatch)
    return records


def _fence(records, rel, *args):
    """The one runner record of ``rel`` that binds every one of ``args``."""
    hits = [r for r in records if r["route"] == "runner" and r["id"].startswith(rel + "#")
            and set(args) <= set(r["placeholders"])]
    assert len(hits) == 1, [r["id"] for r in hits]
    return hits[0]


def _write(path, text):
    with open(str(path), "w", encoding="utf-8") as fh:
        fh.write(text)


class Forge(object):
    """A working copy with :data:`PR_BRANCH` checked out, and a mock store holding PR 101 open
    on that branch and PR 102 open on :data:`OTHER_BRANCH`."""

    def __init__(self, tmp_path, prs=None, wc=None):
        self.wc = wc if wc is not None else repo_wc(tmp_path / "wc", commit=True)
        self.store = pr_store(tmp_path / "store", prs if prs is not None else
                              [mock_pr(101, PR_BRANCH), mock_pr(102, OTHER_BRANCH)])
        self.env = forge_env(self.store)

    def scenario(self, value):
        _write(os.path.join(self.store, "scenario"), value)

    def prs_bytes(self):
        with open(os.path.join(self.store, "prs.json"), "rb") as fh:
            return fh.read()

    def pr(self, number):
        with open(os.path.join(self.store, "prs.json"), encoding="utf-8") as fh:
            return next(p for p in json.load(fh)["prs"] if p["number"] == number)

    def calls(self):
        """``[(op, argv)]`` the mock answered, then forgets them."""
        path = os.path.join(self.store, "calls.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            out = [(c["op"], c["argv"]) for c in map(json.loads, fh) if c]
        os.remove(path)
        return out

    def run(self, rec, argv, env=None, cwd=None):
        err = io.StringIO()
        rc = fr.run(rec["id"], argv, TOOLKIT, environ=dict(env or self.env),
                    cwd=str(cwd or self.wc), err=err)
        return rc, err.getvalue()


def _phase6(records):
    return _fence(records, "proceed/phases-6-8-ship.md", "prNumber", "NEW_BODY")


def _lite(records):
    return _fence(records, "proceed/phases-lite.md", "pr", "lane_escalated")


def _argv(rec, wc, pr):
    """A well-formed call of the Phase 6 fence or the lite escalation fence with ``pr``."""
    if "NEW_BODY" in rec["placeholders"]:
        _write(os.path.join(str(wc), "body.txt"), "The final body.\n")
        return ["--arg", "prNumber=%s" % pr, "--arg-file", "NEW_BODY=body.txt",
                "--arg", "FINAL_TITLE=The final title"]
    _write(os.path.join(str(wc), "reason.txt"), "a reason")
    return ["--arg", "pr=%s" % pr, "--arg-file", "lane_escalated=reason.txt"]


def _one_line(err, prefix):
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith(prefix), err
    return lines[0]


@pytest.fixture
def no_fence(monkeypatch):
    """Records each fence script the runner starts (its PR read is not one): ``[script]``."""
    started = []
    real = subprocess.run

    def run(args, *a, **kw):
        if list(args[:2]) == ["/bin/sh", "-c"]:
            started.append(args[2])
        return real(args, *a, **kw)
    monkeypatch.setattr(fr.subprocess, "run", run)
    return started


# ------------------------------------------------------------------------ BR-9, BR-11
def test_req719_only_the_callers_open_pr_passes(cached, tmp_path):
    """Benign path: with the caller's PR (open, on the checked-out branch, same repository)
    each tied fence runs. The runner's one read of the value comes first, in the `--fields`
    form `fence_census.pr_tie_text` spells, and the fence's own forge calls follow."""
    forge = Forge(tmp_path)
    p6, lite = _phase6(cached), _lite(cached)
    assert p6["tied"] == ["prNumber"] and lite["tied"] == ["pr"]
    assert fc.pr_tie_text("pr") == \
        'adlc_forge_pr_view "$ADLC_ARG_pr" --fields number,state,headRefName,isCrossRepository'
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"))
    assert rc == 0 and "fence_run_" not in err and "opaque_entry_refused" not in err, err
    calls = forge.calls()
    assert calls[0] == ("pr_view", ["101"] + TIE_ARGV), calls
    assert [c for c in calls[1:] if c[1][1:] == TIE_ARGV] == [], calls
    assert [op for op, _argv in calls[1:]] == ["pr_view", "pr_edit", "pr_ready"], calls
    pr = forge.pr(101)
    assert pr["title"] == "The final title" and pr["isDraft"] is False
    assert pr["body"].startswith("The final body.")
    rc, err = forge.run(lite, _argv(lite, forge.wc, "101"))
    assert rc == 0 and "fence_run_" not in err, err
    calls = forge.calls()
    assert calls[0] == ("pr_view", ["101"] + TIE_ARGV)
    assert [op for op, _argv in calls[1:]] == ["pr_view", "pr_edit"], calls
    assert "**Escalated to the full lane**: a reason" in forge.pr(101)["body"]
    assert forge.pr(102) == mock_pr(102, OTHER_BRANCH)


# ------------------------------------------------------------------------ BR-10, AC-8
#: ``(case, value, scenario, the PR records, text of the read PR the line must not hold)``.
OTHERS = [
    ("another PR", "102", None, None,
     ("title of 102", "body of 102", "/pull/102", OTHER_BRANCH)),
    ("cross-repo", "101", "cross-repo", None, ("title of 101", "body of 101", "/pull/101")),
    ("head-other", "101", "head-other", None,
     ("title of 101", "body of 101", PR_BRANCH + "-other")),
    ("merged", "101", "merged", None, ("title of 101", "MERGED")),
    ("closed on the caller's branch", "101", None,
     [mock_pr(101, PR_BRANCH, state="CLOSED"), mock_pr(102, OTHER_BRANCH)],
     ("title of 101", "CLOSED")),
    ("unknown to the forge", "999", None, None, ("mock: no such PR", "error_class")),
]


@pytest.mark.parametrize("case,value,scenario,prs,hidden", OTHERS, ids=[o[0] for o in OTHERS])
def test_req719_another_pr_is_a_bad_value_and_is_untouched(cached, tmp_path, case, value,
                                                          scenario, prs, hidden):
    """A PR number that is not the caller's PR is the caller's value to correct: exit 65 and
    one `fence_run_bad_value:` line naming the value and the checked-out branch, with no
    title, body, URL or head of the PR read. The forge records the runner's one read and
    nothing else, and no PR is changed. The same for the Phase 6 fence and the lite one."""
    forge = Forge(tmp_path, prs=prs)
    if scenario:
        forge.scenario(scenario)
    before = forge.prs_bytes()
    for rec in (_phase6(cached), _lite(cached)):
        rc, err = forge.run(rec, _argv(rec, forge.wc, value))
        assert rc == fr.BAD_VALUE == 65, (case, rec["id"], rc, err)
        line = _one_line(err, "fence_run_bad_value: %s: " % rec["id"])
        arg = rec["tied"][0]
        assert "value for %s, %s, is not the open PR" % (arg, value) in line, line
        assert "(%s)" % PR_BRANCH in line and "Nothing ran" in line, line
        for text in hidden:
            assert text not in line, (case, text, line)
        assert forge.calls() == [("pr_view", [value] + TIE_ARGV)], case
        assert forge.prs_bytes() == before, case


# ------------------------------------------------------------------------ BR-11, AC-9
def _gh_backend(tmp_path, forge, body):
    """``forge``'s caller environment on the GitHub backend, whose `gh` logs its argv and
    then runs ``body``: ``(env, log)``."""
    bin_dir = tmp_path / "gh-bin"
    bin_dir.mkdir(parents=True)
    log = str(tmp_path / "gh.log")
    _write(bin_dir / "gh", "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\n%s\n" % (log, body))
    os.chmod(str(bin_dir / "gh"), 0o755)
    env = dict(forge.env, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
               ADLC_FORGE_PROVIDER_OVERRIDE="github")
    env.pop("ADLC_FORGE_MOCK")
    return env, log


def test_req719_an_unreadable_forge_is_unverified_not_a_pass(cached, tmp_path, monkeypatch,
                                                            no_fence):
    """A forge the runner cannot read for its check is neither a pass nor a refusal: exit 75
    and one `fence_run_unverified:` line with the reason, and the fence never starts. That is
    the mock's error classes, an answer that does not parse, and no answer in the time."""
    forge = Forge(tmp_path)
    before = forge.prs_bytes()
    for scenario in ("network", "auth-missing"):
        forge.scenario(scenario)
        for rec in (_phase6(cached), _lite(cached)):
            rc, err = forge.run(rec, _argv(rec, forge.wc, "101"))
            assert rc == fr.UNVERIFIED == 75, (scenario, rc, err)
            line = _one_line(err, "fence_run_unverified: %s: " % rec["id"])
            assert "error_class=%s" % scenario in line, line
            assert "run the same line once more" in line and "blocker" in line, line
    assert no_fence == [] and forge.prs_bytes() == before
    p6 = _phase6(cached)
    # An answer with no fields: `gh` prints what is not JSON, and exits 0.
    env, log = _gh_backend(tmp_path / "garbled", forge, "echo 'not json'")
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"), env=env)
    assert rc == fr.UNVERIFIED, err
    assert "its answer did not parse" in _one_line(err, "fence_run_unverified: ")
    with open(log, encoding="utf-8") as fh:
        assert fh.read().splitlines() == ["pr view 101 --json %s" % ",".join(fc.PR_TIE_FIELDS)]
    # No answer: a `gh` that hangs is killed with its process group, and the call ends.
    monkeypatch.setattr(fr, "PR_TIE_TIMEOUT", 1)
    env, _log = _gh_backend(tmp_path / "hung", forge, "sleep 30")
    start = time.monotonic()
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"), env=env)
    assert rc == fr.UNVERIFIED and time.monotonic() - start < 15, err
    assert "no answer in 1 s" in _one_line(err, "fence_run_unverified: ")
    assert no_fence == []


@pytest.mark.parametrize("answer,status", [
    ((0, "number=101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=false\n" % PR_BRANCH, ""),
     None),
    ((0, "number=101\nnumber=101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=false\n"
      % PR_BRANCH, ""), fr.UNVERIFIED),
    ((0, "number=1o1\nstate=OPEN\nheadRefName=%s\nisCrossRepository=false\n" % PR_BRANCH, ""),
     fr.UNVERIFIED),
    ((0, "number=101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=no\n" % PR_BRANCH, ""),
     fr.UNVERIFIED),
    ((0, "number=101\nstate=OPEN\nisCrossRepository=false\n", ""), fr.UNVERIFIED),
    ((0, "number=101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=false\nwarning\n"
      % PR_BRANCH, ""), fr.UNVERIFIED),
    ((0, "number=0101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=false\n" % PR_BRANCH, ""),
     None),
    ((0, "number=101\nstate=OPEN\nheadRefName=%s\nisCrossRepository=true\n" % PR_BRANCH, ""),
     fr.BAD_VALUE),
    ((1, "error_class=pr-not-found\nraw=x\n", ""), fr.BAD_VALUE),
    ((1, "error_class=merge-blocked-by-policy\n", ""), fr.UNVERIFIED),
    ((2, "", "forge: cannot auto-detect provider"), fr.UNVERIFIED),
    ((3, "", "no refusal line"), fr.UNVERIFIED),
    ((1, "", "opaque_entry_refused: forge: x"), fr.UNVERIFIED),
    ((3, "\n", "opaque_entry_refused: forge: the Azure DevOps backend"), fr.REFUSED),
    (None, fr.UNVERIFIED),
    # A backend the shell could not run, or that was killed, is unverified whatever class the
    # adapter printed for it (REQ-719 review: `gh: command not found` read as not found).
    ((127, "error_class=pr-not-found\nraw=sh: gh: command not found\n", ""), fr.UNVERIFIED),
    ((126, "error_class=pr-not-found\n", ""), fr.UNVERIFIED),
    ((137, "error_class=pr-not-found\n", ""), fr.UNVERIFIED),
    ((-9, "", ""), fr.UNVERIFIED),
])
def test_req719_the_verdict_reads_four_fields_and_fails_closed(answer, status):
    """ADR-3's table, on the answer alone: all four fields right runs; a field that differs,
    or a number the forge does not know, is 65; the adapter's own refusal is 3; anything else,
    an answer that does not parse included, is 75."""
    assert fr.pr_verdict("101", PR_BRANCH, answer)[0] == status


def test_req719_a_detached_head_is_a_refusal(cached, tmp_path, no_fence):
    """With no branch checked out no PR is the caller's: exit 3 and one
    `opaque_entry_refused:` line, decided before any forge read, so none is recorded. A
    directory that is not a repository is refused the same way."""
    forge = Forge(tmp_path)
    _git("-C", str(forge.wc), "checkout", "-q", "--detach")
    plain = tmp_path / "plain"
    plain.mkdir()
    for cwd in (forge.wc, plain):
        for rec in (_phase6(cached), _lite(cached)):
            rc, err = forge.run(rec, _argv(rec, cwd, "101"), cwd=cwd)
            assert rc == fr.REFUSED == 3, (cwd, rc, err)
            line = _one_line(err, "opaque_entry_refused: %s: " % rec["id"])
            assert "no branch is checked out here" in line, line
            assert forge.calls() == []
    assert no_fence == []


def test_req719_the_adapters_own_refusal_is_passed_through(cached, tmp_path, no_fence):
    """Under the runner the adapter refuses its Azure DevOps backend with status 3 and one
    `opaque_entry_refused:` line: the runner passes that line through as its own refusal, as
    the fence would be refused the same way, and `az` never runs."""
    forge = Forge(tmp_path)
    log = str(tmp_path / "stubs.jsonl")
    bin_dir = rs.install(str(tmp_path / "bin"), log)
    for name in ("git", "sh"):
        os.remove(os.path.join(bin_dir, name))   # the runner's own branch read is real here
    env = dict(forge.env, PATH=bin_dir + os.pathsep + os.environ["PATH"],
               ADLC_FORGE_PROVIDER_OVERRIDE="azure-devops")
    env.pop("ADLC_FORGE_MOCK")
    p6 = _phase6(cached)
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"), env=env)
    assert rc == fr.REFUSED, err
    line = _one_line(err, "opaque_entry_refused: forge: the Azure DevOps backend")
    assert "not admitted under fence-run" in line
    assert rs.calls(log) == [] and no_fence == []


# ------------------------------------------------------------------------ BR-12, AC-10
def test_req719_no_forge_call_before_the_value_and_sandbox_checks(cached, tmp_path,
                                                                  monkeypatch):
    """The read comes after the value checks and the sandbox check: a call whose value fails
    its pattern (65) and a call that finds itself inside a harness sandbox (69) each record
    no forge call. Out of the sandbox, the same call reads the PR and runs."""
    main = tmp_path / "main"
    repo_wc(main, branch="main", commit=True)
    work = main / ".worktrees" / "REQ-901"
    _git("-C", str(main), "worktree", "add", "-q", "-b", PR_BRANCH, str(work))
    forge = Forge(tmp_path, wc=work)
    p6, lite = _phase6(cached), _lite(cached)
    for rec, argv in ((p6, ["--arg", "prNumber=1x"]), (p6, ["--arg", "prNumber=-1"]),
                      (lite, ["--arg", "pr=101; true"])):
        argv = _argv(rec, work, "101")[2:] + argv
        rc, err = forge.run(rec, argv)
        assert rc == fr.BAD_VALUE, err
        assert "does not match" in _one_line(err, "fence_run_bad_value: ")
        assert forge.calls() == []
    argv = _argv(p6, work, "101")
    argv[argv.index("FINAL_TITLE=The final title")] = "FINAL_TITLE=two\nlines"
    rc, err = forge.run(p6, argv)
    assert rc == fr.BAD_VALUE and "value for FINAL_TITLE" in err and forge.calls() == []
    # The linked worktree's git directory is the main checkout's: deny writing it, as the
    # harness sandbox does to a chained call (BUG-287's measured case).
    common = os.path.realpath(str(main / ".git"))
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda path, mode, **kw: False if (
        os.path.realpath(path) == common and mode == os.W_OK) else real_access(path, mode, **kw))
    for rec in (p6, lite):
        rc, err = forge.run(rec, _argv(rec, work, "101"))
        assert rc == fr.SANDBOXED == 69, err
        _one_line(err, "fence_run_sandboxed: %s: " % rec["id"])
        assert forge.calls() == []
    monkeypatch.setattr(os, "access", real_access)
    rc, err = forge.run(p6, _argv(p6, work, "101"))
    assert rc == 0, err
    assert forge.calls()[0] == ("pr_view", ["101"] + TIE_ARGV)


# ------------------------------------------------------------------------ BR-14, AC-8
def test_req719_a_fence_that_takes_no_pr_number_reads_no_pr(cached, tmp_path):
    """Only a value bound to a marked placeholder is read: Step 0's draft-PR fence takes no PR
    number and runs with no PR read before its own calls, and `/architect` Step 5's `$prnum`,
    read from a command's output, ties nothing. Every runner record is tied on exactly its
    marked values."""
    forge = Forge(tmp_path, prs=[])
    draft = _fence(cached, "proceed/phase-0-setup.md", "repo", "title")
    assert "tied" not in draft
    rc, err = forge.run(draft, ["--arg", "repo=acme/widgets", "--arg", "integrationBranch=main",
                                "--arg", "branch=%s" % PR_BRANCH, "--arg", "req=REQ-901",
                                "--arg", "title=A title"])
    assert rc == 0 and "fence_run_" not in err and "opaque_entry_refused" not in err, err
    assert [op for op, _argv in forge.calls()] == ["pr_create"]
    assert forge.pr(101)["headRefName"] == PR_BRANCH
    architect = _fence(cached, "architect/SKILL.md", "MAPPER_PATHS")
    assert "tied" not in architect
    marked = {ph.arg for table in (fc.PLACEHOLDERS, fc.VAR_PLACEHOLDERS)
              for ph in table.values() if ph.pr}
    for rec in cached:
        if rec["route"] == "runner":
            assert rec.get("tied", []) == sorted(set(rec["placeholders"]) & marked), rec["id"]


# ------------------------------------------------------------------------ REQ-719 review
def _path_without(tmp_path, missing):
    """A PATH directory holding what the runner and its PR read call, less ``missing``."""
    bin_dir = tmp_path / ("no-" + "-".join(missing))
    bin_dir.mkdir(parents=True)
    for name in ("git", "gh", "dirname", "basename", "mktemp", "cat", "rm", "sed", "awk", "grep",
                 "tr", "head", "tail", "uname", "env", "python3"):
        real = shutil.which(name)
        if real and name not in missing:
            os.symlink(real, str(bin_dir / name))
    return str(bin_dir)


def test_req719_a_backend_that_is_not_there_is_unverified(cached, tmp_path, no_fence):
    """F2: with no `gh` on PATH the adapter's read exits 127, and its classifier used to read the
    shell's `gh: command not found` as `pr-not-found`, which the runner turned into 65, "correct
    that value". It is 75, `fence_run_unverified:`, and the fence never starts."""
    forge = Forge(tmp_path)
    env = dict(forge.env, PATH=_path_without(tmp_path, ["gh"]),
               ADLC_FORGE_PROVIDER_OVERRIDE="github")
    env.pop("ADLC_FORGE_MOCK")
    for rec in (_phase6(cached), _lite(cached)):
        rc, err = forge.run(rec, _argv(rec, forge.wc, "101"), env=env)
        assert rc == fr.UNVERIFIED, (rec["id"], rc, err)
        line = _one_line(err, "fence_run_unverified: %s: " % rec["id"])
        assert "status 127" in line, line
    assert no_fence == []


def test_req719_a_branch_that_cannot_be_read_is_unverified(cached, tmp_path, no_fence):
    """F3: a git failure that is not a detached HEAD (a config git refuses, or no git at all)
    says nothing about which branch is checked out: 75, `fence_run_unverified:`, before any
    forge read. A detached HEAD is still 3."""
    forge = Forge(tmp_path)
    with open(os.path.join(str(forge.wc), ".git", "config"), "a", encoding="utf-8") as fh:
        fh.write("[[[ not a section\n")
    with pytest.raises(fr.BranchUnread, match="exited 128"):
        fr.checked_out_branch(str(forge.wc), forge.env)
    p6 = _phase6(cached)
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"))
    assert rc == fr.UNVERIFIED, err
    line = _one_line(err, "fence_run_unverified: %s: " % p6["id"])
    assert "could not be read" in line and "bad config" in line, line
    assert forge.calls() == [] and no_fence == []
    good = Forge(tmp_path / "nogit")
    env = dict(good.env, PATH=_path_without(tmp_path, ["git"]))
    rc, err = good.run(p6, _argv(p6, good.wc, "101"), env=env)
    assert rc == fr.UNVERIFIED and "git could not be run" in err, err
    assert good.calls() == [] and no_fence == []
    _git("-C", str(good.wc), "checkout", "-q", "--detach")
    assert fr.checked_out_branch(str(good.wc), good.env) == ""
    rc, err = good.run(p6, _argv(p6, good.wc, "101"))
    assert rc == fr.REFUSED and "no branch is checked out here" in err, err
    assert good.calls() == [] and no_fence == []


OWN, SIBLING = "feat/REQ-100-own", "feat/REQ-200-sibling"


def _sibling_forge(tmp_path):
    """REQ-100's exec run: PR 101 open on its branch and PR 202 open on REQ-200's, and the
    session has made a local branch named after REQ-200's head, never pushed."""
    forge = Forge(tmp_path, prs=[mock_pr(101, OWN), mock_pr(202, SIBLING)],
                  wc=repo_wc(tmp_path / "wc", branch=OWN, commit=True))
    _git("-C", str(forge.wc), "checkout", "-q", "-b", SIBLING)
    forge.env = dict(forge.env, ADLC_EXEC_RUN="REQ-100")
    return forge


def test_req719_a_branch_named_after_another_reqs_head_is_refused(cached, tmp_path, no_fence):
    """F8: under an exec run the PR tie takes only a branch of the run's own REQ (BR-9). A
    local branch named after a sibling REQ's head, with the sibling's PR number, is refused
    with 3 before any forge read, and the sibling's PR keeps its title, body and draft state.
    The same for the Phase 6 fence and the lite escalation fence."""
    forge = _sibling_forge(tmp_path)
    before = forge.pr(202)
    for rec in (_phase6(cached), _lite(cached)):
        rc, err = forge.run(rec, _argv(rec, forge.wc, "202"))
        assert rc == fr.REFUSED, (rec["id"], rc, err)
        line = _one_line(err, "opaque_entry_refused: %s: " % rec["id"])
        assert "%s, is not this exec run's" % SIBLING in line and "REQ-100" in line, line
        assert forge.calls() == []
    after = forge.pr(202)
    assert (after["title"], after["body"], after["isDraft"]) == \
        (before["title"], before["body"], before["isDraft"]) == \
        ("title of 202", "body of 202", True)
    assert no_fence == []


def test_req719_the_runs_own_branch_and_pr_still_run(cached, tmp_path):
    """F8's benign twin: with the run's own branch checked out and its own PR, each tied fence
    runs under ADLC_EXEC_RUN as it does outside one."""
    forge = _sibling_forge(tmp_path)
    _git("-C", str(forge.wc), "checkout", "-q", OWN)
    p6, lite = _phase6(cached), _lite(cached)
    rc, err = forge.run(p6, _argv(p6, forge.wc, "101"))
    assert rc == 0 and "fence_run_" not in err and "opaque_entry_refused" not in err, err
    assert forge.pr(101)["title"] == "The final title" and forge.pr(101)["isDraft"] is False
    rc, err = forge.run(lite, _argv(lite, forge.wc, "101"))
    assert rc == 0 and "fence_run_" not in err, err
    assert "**Escalated to the full lane**: a reason" in forge.pr(101)["body"]
    assert forge.pr(202) == mock_pr(202, SIBLING)


def test_req719_a_bound_value_cannot_be_replaced_by_the_fence(tmp_path):
    """The runner makes every bound value readonly before the fence body runs, so a value it
    checked, and a PR number it tied, cannot be replaced afterwards by any spelling of its name
    (`read` or `printf -v` into a computed name), which the census's text check cannot see."""
    pr = fc.PLACEHOLDERS["prNumber"]
    component = fc.PLACEHOLDERS["component"]
    values = {"pr": ["101"], "component": ["a", "b"]}
    assert fr.bound_names([pr, component], values) == \
        ["ADLC_ARG_pr", "ADLC_ARG_component_0", "ADLC_ARG_component_1"]
    body = ('v=ADLC_\nread "${v}ARG_pr" 2>/dev/null <<EOF\n6\nEOF\n'
            'printf -v "${v}ARG_pr" 7 2>/dev/null\necho "pr=$ADLC_ARG_pr"\n')
    fence = fc.Fence("x.md", 1, "sh", body, "", 0, 0)
    script = fr.script_for(fence, {"pr": ["101"]}, TOOLKIT, [pr])
    assert "\nreadonly ADLC_ARG_pr\n" in script
    env = fr.child_env(dict(os.environ), [pr], {"pr": ["101"]}, TOOLKIT)
    proc = subprocess.run(["/bin/sh", "-c", script], cwd=str(tmp_path), env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    assert "pr=6" not in proc.stdout and "pr=7" not in proc.stdout, proc.stdout
    assert proc.stdout.strip() in ("pr=101", ""), (proc.stdout, proc.stderr)
