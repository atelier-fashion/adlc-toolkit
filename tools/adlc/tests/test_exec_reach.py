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
"""

import io
import os
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


@pytest.fixture(scope="module")
def adapter():
    return ea.load("claude", TOOLKIT)


@pytest.fixture(scope="module")
def records():
    return fc.census(TOOLKIT)


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
        code = fc.transform(fence.code, {ph.arg: ["x"] for ph in found}, root="/abs/tk")
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
    bad = fc.unrouted(fc.census(root))
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
    bad = fc.unrouted(fc.census(root))
    assert [r["id"].split("#")[0] for r in bad] == ["validate/SKILL.md"], bad
    assert "adlc_forge_pr_land" in bad[0]["reason"]
    assert "neither the function index nor EXTERNAL" in bad[0]["reason"]


def test_function_index_refuses_another_definition_form(tmp_path):
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    with open(os.path.join(root, "partials", "zz-odd.sh"), "w", encoding="utf-8") as fh:
        fh.write("function odd_one {\n  :\n}\nodd_two ()\n{\n  :\n}\n")
    with pytest.raises(fc.CensusError, match="zz-odd.sh"):
        fc.function_index(root)


def test_real_tree_reach_matches_golden(records, adapter, tmp_path, monkeypatch):
    """Benign path, dynamic: every runner fence runs under stubs with sample values; each
    recorded command is in its fence's static reach, none is a deny, and every push is the id
    reservation. At least one case runs per runner fence."""
    memo = {}
    real = fc.census
    def census(root, a=None):
        if root not in memo:
            memo[root] = real(root, a)
        return memo[root]
    monkeypatch.setattr(fc, "census", census)
    policy = fc.exec_policy(TOOLKIT, adapter)
    wc = tmp_path / "wc"
    (wc / ".adlc" / "specs").mkdir(parents=True)
    ran = 0
    for rec in [r for r in records if r["route"] == "runner"]:
        log = str(tmp_path / ("calls-%d.jsonl" % ran))
        stubs = rs.install(str(tmp_path / ("bin-%d" % ran)), log)
        # ADLC_REPOS_ROOT bounds the id allocator's repo walk to this test's tree: with git
        # stubbed, the main worktree does not resolve, and the walk would start at `/`.
        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"],
                   ADLC_FORGE_MOCK="1", ADLC_DISABLE_DELEGATE="1", ADLC_REPOS_ROOT=str(tmp_path))
        err = io.StringIO()
        fr.run(rec["id"], _sample_argv(rec, wc), TOOLKIT, environ=env, cwd=str(wc), err=err)
        assert "opaque_entry_refused" not in err.getvalue(), (rec["id"], err.getvalue())
        ran += 1
        calls = rs.calls(log)
        for call in calls:
            text = rs.command_text(call)
            assert not em.deny_hits(policy, text), (rec["id"], text)
            shape = fc._external_shape([call["cmd"]] + call["argv"])
            assert _covered(shape, call["cmd"], rec["reach"]), (rec["id"], shape, rec["reach"])
        assert fc.push_problems([[c["cmd"]] + c["argv"] for c in calls]) == [], rec["id"]
    assert ran == len([r for r in records if r["route"] == "runner"]) and ran > 0


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


@pytest.mark.parametrize("argv,ok", [
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
