"""Reach audit: what every `runner` fence can run, proven two ways (REQ-682 BR-2, BR-4, AC-4).

The **static** check takes each runner fence's transitive function closure over
``partials/*.sh`` and reads what runs, command by command: a deny-tier spelling, a construct
that runs data as code, or a command neither the function index nor ``EXTERNAL`` names fails.
It covers branches a run does not take.

The **dynamic** check runs every runner fence through ``fence-run`` with recording stubs for
``git``, ``gh``, ``az`` and ``curl`` first on ``PATH``. Stubs return canned success, so it
proves the paths it reaches, not every branch: that residual is the static check's. It runs
in the throwaway ``HOME`` the conftest gives every test, with no network, because every
forge and git call stops at a stub.

Both read the **union** of every exec-capable adapter's deny tier and ``engine_deny``, so a
route ``fence-run`` accepts reaches nothing any adapter denies (REQ-662 ADR-8). The pushes a
runner fence may make are the two kinds BR-2 excepts: the id reservation, and the exact branch
push of REQ-662 ADR-9.
"""

import io
import os
import shutil
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
from test_fence_run import _sample_argv  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
FIX = os.path.join(HERE, "fixtures", "exec-fence", "partials")
MATCHER_NONE = os.path.join(HERE, "fixtures", "harness", "fake-exec-file.yml")
PUSH_KEY = "proceed/phase-0-setup.md#6"


@pytest.fixture(scope="module")
def adapter():
    return ea.load("claude", TOOLKIT)


@pytest.fixture(scope="module")
def records(adapter):
    return fc.census(TOOLKIT, adapter)


def _memo(monkeypatch):
    memo = {}
    real = fc.census

    def census(root, a=None):
        key = (root, a.name if a is not None else None)
        if key not in memo:
            memo[key] = real(root, a)
        return memo[key]
    monkeypatch.setattr(fc, "census", census)


def _fixture_line(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return [ln for ln in fh.read().split("\n") if ln.strip() and not ln.startswith("#")][0]


def _inject(root, rel, func, line):
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    head = "%s() {\n" % func
    assert text.count(head) == 1, (rel, func)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(head, head + line + "\n"))


def test_no_runner_fence_reaches_deny_tier(records, adapter):
    """BR-2: no runner fence's closure holds a deny-tier spelling, an eval, an `sh -c "$…"`
    or a `.` of a non-literal operand; every push it holds is the id reservation."""
    index = fc.function_index(TOOLKIT)
    runners = [r for r in records if r["route"] == "runner"]
    assert runners, "the census has no runner fences: the audit would be vacuous"
    for rec in runners:
        rel, ordinal = rec["id"].split(":")[0].split("#")
        fence = fc.fences(fc.view(TOOLKIT, rel), rel)[int(ordinal) - 1]
        found, _sources = fc.plan(fence.code)
        # A tied fence's reach includes the runner's own PR read (REQ-719 BR-12).
        code = fc.reach_text(fence.code, found)
        assert (fc.pr_tie_text("pr") in code) is ("pr" in rec.get("tied", [])), rec["id"]
        externals, problems, _funcs = fc.reach(code, index, adapter, TOOLKIT)
        assert problems == [], (rec["id"], problems)
        assert externals == rec["reach"], rec["id"]


@pytest.mark.parametrize("fixture,rel,func,deny", [
    ("gains-gh-pr-merge.sh", "partials/forge.sh", "adlc_forge_pr_create", "gh pr merge"),
    ("gains-force-push.sh", "partials/lessons.sh", "adlc_lessons", "git push --force"),
    ("gains-find-exec-merge.sh", "partials/lessons.sh", "adlc_lessons", "gh pr merge"),
    ("gains-awk-system-merge.sh", "partials/lessons.sh", "adlc_lessons", "gh pr merge"),
])
def test_fixture_deny_call_fails_audit(tmp_path, fixture, rel, func, deny):
    """AC-4: an admitted function that gains a deny-tier call fails the audit, naming the fence,
    the function and the file:line, and its fences stop being runner."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    _inject(root, rel, func, _fixture_line(fixture))
    bad = fc.unrouted(fc.census(root, ea.load("claude", root)))
    assert bad, "the injected %s was not found" % deny
    hits = [r for r in bad if deny in " ".join(r.get("problems", []))]
    assert hits, [r["reason"] for r in bad]
    assert any("%s (%s:" % (func, rel) in p for r in hits for p in r["problems"]), hits[0]


def test_unindexed_function_starts_refused(tmp_path):
    """BR-4: a fence calling a function no partial defines, and no EXTERNAL entry names, is
    refused: a new verb starts refused until it is checked."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    with open(os.path.join(FIX, "unindexed-call.md"), encoding="utf-8") as fh:
        extra = fh.read()
    with open(os.path.join(root, "validate", "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write("\n" + extra)
    bad = fc.unrouted(fc.census(root, ea.load("claude", root)))
    assert [r["id"].split("#")[0] for r in bad] == ["validate/SKILL.md"], bad
    assert "adlc_forge_pr_land" in bad[0]["reason"]
    assert "neither the function index nor EXTERNAL" in bad[0]["reason"]


def test_function_index_refuses_another_definition_form(tmp_path):
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    with open(os.path.join(root, "partials", "zz-odd.sh"), "w", encoding="utf-8") as fh:
        fh.write("function odd_one {\n  :\n}\nodd_two ()\n{\n  :\n}\n")
    with pytest.raises(fc.CensusError, match="zz-odd.sh"):
        fc.function_index(root)


#: A ``gh`` that records like :mod:`recording_stubs` and answers the runner's PR read of PR
#: 101 as an open, same-repository PR on :data:`TIE_BRANCH`; it prints nothing for any other
#: call. ``%(log)s`` and ``%(branch)s`` are filled in.
_ANSWERING_GH = r"""import json, os, sys
argv = sys.argv[1:]
with open(%(log)r, "a") as fh:
    fh.write(json.dumps({"cmd": "gh", "argv": argv, "cwd": os.getcwd()}) + "\n")
if argv[:2] == ["pr", "view"] and argv[3:] == ["--json", %(fields)r]:
    print(json.dumps({"number": int(argv[2]), "state": "OPEN", "headRefName": %(branch)r,
                      "isCrossRepository": False}))
"""
TIE_BRANCH = "feat/REQ-901-thing"


def _answering_gh(bin_dir, log):
    """Replace the recording ``gh`` in ``bin_dir`` with :data:`_ANSWERING_GH`."""
    script = os.path.join(bin_dir, "gh.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(_ANSWERING_GH % {"log": log, "branch": TIE_BRANCH,
                                  "fields": ",".join(fc.PR_TIE_FIELDS)})
    with open(os.path.join(bin_dir, "gh"), "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\nexec python3 -I %s "$@"\n' % rs._sh_quote(script))


def test_real_tree_reach_matches_golden(records, adapter, tmp_path, monkeypatch):
    """Benign path, dynamic: every runner fence runs under stubs with sample values; each
    recorded command is in its fence's static reach, none is a deny, and every push is the id
    reservation. At least one case runs per runner fence.

    A tied fence (REQ-719 BR-12) runs on the GitHub backend instead of the mock, so the
    runner's own PR read reaches the recording `gh`: its first recorded call is that read, and
    the rule that every recorded call is in the static reach covers it (LESSON-845)."""
    _memo(monkeypatch)
    policy = fc.exec_policy(TOOLKIT, adapter)
    wc = tmp_path / "wc"
    (wc / ".adlc" / "specs").mkdir(parents=True)
    ran = tied = 0
    for rec in [r for r in records if r["route"] == "runner"]:
        log = str(tmp_path / ("calls-%d.jsonl" % ran))
        stubs = rs.install(str(tmp_path / ("bin-%d" % ran)), log)
        # ADLC_REPOS_ROOT bounds the id allocator's repo walk to this test's tree: with git
        # stubbed, the main worktree does not resolve, and the walk would start at `/`.
        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"],
                   ADLC_FORGE_MOCK="1", ADLC_DISABLE_DELEGATE="1", ADLC_REPOS_ROOT=str(tmp_path))
        if rec.get("tied"):
            _answering_gh(stubs, log)
            env.pop("ADLC_FORGE_MOCK")
            env["ADLC_FORGE_PROVIDER_OVERRIDE"] = "github"
        err = io.StringIO()
        # `git` is a stub here, so the runner's own sandbox check (BUG-287), which asks git
        # where the repository's git directory is, is switched off, and its read of the
        # checked-out branch is given one: this test audits the calls each fence's script,
        # and the runner's PR read, make.
        monkeypatch.setattr(fr, "sandboxed", lambda cwd, environ: None)
        monkeypatch.setattr(fr, "checked_out_branch", lambda cwd, environ: TIE_BRANCH)
        fr.run(rec["id"], _sample_argv(rec, wc), TOOLKIT, environ=env, cwd=str(wc), err=err)
        assert "opaque_entry_refused" not in err.getvalue(), (rec["id"], err.getvalue())
        assert "fence_run_bad_value" not in err.getvalue(), (rec["id"], err.getvalue())
        assert "fence_run_unverified" not in err.getvalue(), (rec["id"], err.getvalue())
        ran += 1
        calls = rs.calls(log)
        reads = [c for c in calls if c["cmd"] == "gh" and
                 c["argv"][3:] == ["--json", ",".join(fc.PR_TIE_FIELDS)]]
        if rec.get("tied"):
            # One read per tied value, made before any command of the fence.
            assert len(reads) == len(rec["tied"]) and calls[:len(reads)] == reads, \
                (rec["id"], calls)
            assert all(c["argv"][:3] == ["pr", "view", "101"] for c in reads), reads
            assert len(calls) > len(reads), (rec["id"], "the fence did not run", calls)
            tied += 1
        else:
            assert reads == [], (rec["id"], reads)
        for call in calls:
            text = rs.command_text(call)
            assert not em.deny_hits(policy, text), (rec["id"], text)
            shape = fc._external_shape([call["cmd"]] + call["argv"])
            assert _covered(shape, call["cmd"], rec["reach"]), (rec["id"], shape, rec["reach"])
        assert fc.push_problems([[c["cmd"]] + c["argv"] for c in calls]) == [], rec["id"]
    assert ran == len([r for r in records if r["route"] == "runner"]) and ran > 0
    assert tied == len([r for r in records if r.get("tied")]) >= 2


def _covered(shape, cmd, reach):
    """Whether a recorded call is in a static reach: its shape, its bare command, or a shape
    the static reading could only spell to a prefix (a verb held in a variable)."""
    return shape in reach or cmd in reach or any(shape.startswith(s + " ") for s in reach)


def test_id_reservation_push_is_reach_of_the_allocation_fences(records):
    """Amended BR-2: the close-out's allocation fences are runner, and their reach names the
    id-reservation push."""
    alloc = [r for r in records if r["id"].startswith("wrapup/SKILL.md#") and
             r["sources"] == ["id-alloc"]]
    assert len(alloc) == 2
    for rec in alloc:
        assert rec["route"] == "runner" and "git push" in rec["reach"], rec


def _with_engine_deny(root, entry):
    """Ship the matcher-none fixture adapter under ``root`` with one more ``engine_deny``."""
    with open(MATCHER_NONE, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("  engine_deny:\n") == 1
    text = text.replace("  engine_deny:\n", "  engine_deny:\n    - %s\n" % entry)
    with open(os.path.join(root, "harness", "fake-exec-file.yml"), "w", encoding="utf-8") as fh:
        fh.write(text)


def test_reach_runs_against_the_union_of_deny_tiers(tmp_path, records):
    """BR-19, ADR-8: an `engine_deny` entry of one exec-capable adapter is a deny for every
    adapter's runner routes. Shipping a second adapter that denies `gh pr view` unroutes the
    fences that reach it on `claude` too, so fence-run, which accepts the union of runner
    routes, never runs a command any adapter denies."""
    reaching = sorted(r["id"] for r in records if r["route"] == "runner" and
                      "gh pr view" in r["reach"])
    assert reaching, "no runner fence reaches `gh pr view`: pick another command"
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    _with_engine_deny(root, "[gh, pr, view]")
    adapters = {a.name: a for a in fc.exec_adapters(root)}
    assert sorted(adapters) == ["claude", "codex", "fake-exec-file"]
    assert "gh pr view" in fc.union_deny_texts(list(adapters.values()), root)
    assert "gh pr view" not in fc.union_deny_texts(adapters["claude"], root)
    for name, adapter in adapters.items():
        bad = fc.unrouted(fc.census(root, adapter))
        hit = sorted(r["id"] for r in bad if "gh pr view" in " ".join(r.get("problems", [])))
        assert hit == reaching, (name, hit)
    merged = {r["id"]: r for r in fc.census(root)}
    assert all(merged[i]["route"] == "unrouted" for i in reaching)
    wc = tmp_path / "wc"
    wc.mkdir()
    err = io.StringIO()
    assert fr.run(reaching[0], [], root, cwd=str(wc), err=err) == fr.REFUSED
    assert "not runner" in err.getvalue(), err.getvalue()


@pytest.mark.parametrize("body,ok", [
    ("git -C <worktree> push -u origin <branch-name>", True),
    ("git -C <worktree> push --force -u origin <branch-name>", False),
    ("git -C <worktree> push -u --force origin <branch-name>", False),
    ("git -C <worktree> push -u origin <branch-name> <branch-name>", False),
    ("git -C <worktree> push -u origin <branch-name>:main", False),
    ("git -c push.default=current -C <worktree> push -u origin <branch-name>", False),
    ("git -C <worktree> -c x=y push -u origin <branch-name>", False),
    ("git -C <worktree> push origin <branch-name>", False),
    ("git -C <worktree> push -u upstream <branch-name>", False),
    ("git push -u origin <branch-name>", False),
    ("git -C <primary worktree> push -u origin <branch-name>", False),
    ("git -C <worktree> push -u origin <integration-branch>", False),
])
def test_branch_push_audit_accepts_only_the_exact_argv(adapter, body, ok):
    """ADR-9: a fence's push is the branch-push kind only as exactly `git -C $ADLC_ARG_worktree
    push -u origin $ADLC_ARG_branch`; a `--force`, a second refspec and an option before
    `push` each fail the audit, as does any other spelling."""
    found, _sources = fc.plan(body)
    code = fc.transform(body, {ph.arg: ["x"] for ph in found}, root="/abs/tk")
    _ext, problems, _funcs = fc.reach(code, fc.function_index(TOOLKIT), adapter, TOOLKIT)
    assert (problems == []) is ok, problems
    if not ok:
        assert any("push" in p for p in problems), problems


def test_branch_push_runs_what_the_audit_read(tmp_path, monkeypatch):
    """The dynamic half for the branch push: under stubs, the one recorded call is in the
    fence's static reach and is the branch-push kind, with `-C` the calling directory."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    shutil.copy(MATCHER_NONE, os.path.join(root, "harness"))
    other = next(a for a in fc.exec_adapters(root) if not fc.routes_direct(a))
    rec = next(r for r in fc.census(root, other) if r["id"].startswith(PUSH_KEY + ":"))
    assert rec["route"] == "runner" and rec["push"] == fc.BRANCH_PUSH
    _memo(monkeypatch)
    wc = tmp_path / "wc"
    wc.mkdir()
    log = str(tmp_path / "calls.jsonl")
    stubs = rs.install(str(tmp_path / "bin"), log)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"])
    err = io.StringIO()
    # `git` is a stub here, so the runner's read of the checked-out branch is given its
    # answer: this test is about the calls the fence's own script makes.
    monkeypatch.setattr(fr, "checked_out_branch", lambda cwd, environ: "feat/REQ-901-x")
    monkeypatch.setattr(fr, "sandboxed", lambda cwd, environ: None)
    rc = fr.run(rec["id"], ["--arg", "worktree=%s" % wc, "--arg", "branch=feat/REQ-901-x"],
                root, environ=env, cwd=str(wc), err=err)
    assert rc == 0, err.getvalue()
    calls = [[c["cmd"]] + c["argv"] for c in rs.calls(log)]
    assert calls == [["git", "-C", str(wc), "push", "-u", "origin", "feat/REQ-901-x"]]
    assert fc._external_shape(calls[0]) in rec["reach"]
    assert fc.push_problems(calls) == []


@pytest.mark.parametrize("argv,ok", [
    (["git", "-C", "/wc", "push", "-u", "origin", "feat/REQ-901-thing"], True),
    (["git", "-C", "/wc", "push", "-u", "origin", "main"], False),
    (["git", "-C", "/wc", "push", "-u", "--force", "origin", "feat/x"], False),
    (["git", "-C", "/wc", "push", "-u", "origin", "feat/x", "feat/y"], False),
    (["git", "-C", "/wc", "push", "-u", "origin", "+feat/x"], False),
    (["git", "-C", "/wc", "push", "-u", "origin", "feat/x:main"], False),
    (["git", "-c", "a=b", "-C", "/wc", "push", "-u", "origin", "feat/x"], False),
    (["git", "-C", "wc", "push", "-u", "origin", "feat/x"], False),
    (["git", "-C", "/wc", "push", "origin", "0123abcd:refs/adlc/ids/lesson/901"], True),
    (["git", "push", "origin", "deadbeef:refs/adlc/ids/assume/031"], True),
    (["git", "push", "origin", "HEAD:refs/heads/main"], False),
    (["git", "push", "origin", "+0123abcd:refs/adlc/ids/lesson/901"], False),
    (["git", "push", "--force", "origin", "0123abcd:refs/adlc/ids/lesson/901"], False),
    (["git", "push", "origin", "main"], False),
    (["git", "push"], False),
    (["git", "status"], True),
])
def test_every_recorded_push_is_checked(argv, ok):
    assert (fc.push_problems([argv]) == []) is ok, argv
