"""Phase 7 without `gh` (REQ-719 ADR-6 "Phase 7"; BR-24, BR-25; AC-18, AC-19).

Phase 7 reads a PR's diff from the local repository, with a fence that fetches both refs with
their destinations named (ADR-2) and refuses a local `HEAD` that is not the pushed head, and
reads CI through `adlc_forge_pr_checks`, one read per call, in a fence that binds the PR number
(so the runner ties it to the caller's PR, ADR-3) and waits `<ciWait>` seconds, 0 to 90, first.
The wait between reads, the read count and what each verdict means are the text's.

The fences run through the real `fence-run` shim: the diff fence in a `--single-branch` clone
of a throwaway bare origin, the CI fence against the stateful mock forge in a throwaway store.
"""

import json
import os
import re
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import toolkit_root  # noqa: E402
from test_fence_run import PR_BRANCH, _git, forge_env, mock_pr, pr_store, repo_wc  # noqa: E402
from test_lane_fence_single_branch import (BRANCH, EXPLICIT_FETCH, SHIM,  # noqa: E402
                                           branch_args, branch_clone, fence_run, head,
                                           origin_repo, tracking_ref)

TOOLKIT = toolkit_root.toolkit_root()
SHIP = "proceed/phases-6-8-ship.md"
OTHER_BRANCH = "feat/REQ-902-other"
SOURCE_FORGE = ('if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; '
                'else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi')


def _read(rel):
    with open(os.path.join(TOOLKIT, rel), encoding="utf-8") as fh:
        return fh.read()


def phase7(text):
    """Phase 7 of the ship companion: from its heading to Phase 8's."""
    start = text.index("### Phase 7: PR Cleanup & CI\n")
    return text[start:text.index("### Phase 8: Wrapup\n", start)]


def skill_phase7():
    """The Phase 7 paragraph of `proceed/SKILL.md`: its heading to the next delimiter."""
    text = _read("proceed/SKILL.md")
    start = text.index("### Phase 7: PR Cleanup & CI\n")
    return text[start:text.index("\n---\n", start)]


def ship_fences():
    """``(diff fence, CI fence)`` of Phase 7, as the exec view holds them."""
    view = fc.view(TOOLKIT, SHIP)
    section = phase7(_read(SHIP))
    found = [f for f in fc.fences(view, SHIP) if f.body in section]
    diff = [f for f in found if "diff -M" in f.code]
    checks = [f for f in found if "adlc_forge_pr_checks" in f.code]
    assert len(found) == 2 and len(diff) == 1 and len(checks) == 1, [f.id for f in found]
    return diff[0], checks[0]


@pytest.fixture(scope="module")
def records():
    """The merged census: what fence-run accepts, whichever harness calls."""
    return fc.census(TOOLKIT)


def _record(records, fence):
    return next(r for r in records if r["id"] == fence.id)


# ------------------------------------------------------------------------ BR-24, AC-18
#: A `gh` command word: `gh` as a whole word, as a fence or the prose would name one.
GH_WORD = re.compile(r"(?<![\w/.-])gh(?![\w-])")


def test_req719_phase_7_names_no_gh_command():
    """BR-24: no `gh` command in Phase 7 of the companion or in the Phase 7 paragraph of
    `proceed/SKILL.md`. Both name the adapter's CI read instead, and the companion's diff
    step names the local three-dot diff."""
    ship = phase7(_read(SHIP))
    skill = skill_phase7()
    for name, text in (("phases-6-8-ship.md", ship), ("SKILL.md", skill)):
        assert GH_WORD.findall(text) == [], (name, GH_WORD.findall(text))
        assert "gh pr" not in text and "adlc_forge_pr_checks" in text, name
    assert "`origin/<integrationBranch>` to `HEAD`" in ship
    assert "the local diff from `origin/<integrationBranch>` to the pushed `HEAD`" in skill
    assert "re-run the lane check before leaving it" in _read("proceed/SKILL.md")
    assert sum(1 for _ in open(os.path.join(TOOLKIT, "proceed", "SKILL.md"),
                               encoding="utf-8")) < 500


def test_req719_phase_7_fences_route_runner(records):
    """AC-18: the diff fence takes `<worktree>`, `<integrationBranch>` and `<branch>` and
    fetches with ADR-2's line; the CI fence is `sleep '<ciWait>'` then
    `adlc_forge_pr_checks '<prNumber>'`, after the root line and the guarded source of
    `forge.sh`. Both goldens route both `runner`, the CI fence's record is `tied`, and
    `fence-run show` prints a runner call for each."""
    diff, checks = ship_fences()
    assert diff.code.startswith("wt='<worktree>'; ib='<integrationBranch>'; br='<branch>'\n")
    assert "if ! %s; then\n" % EXPLICIT_FETCH in diff.code
    assert 'rev-parse "origin/$br"' in diff.code
    assert 'git -C "$wt" diff -M "origin/$ib...HEAD"' in diff.code
    assert checks.code.split("\n") == [fc.ROOT_LINE, SOURCE_FORGE, "sleep '<ciWait>'",
                                       "adlc_forge_pr_checks '<prNumber>'"]
    for name in ("claude", "codex"):
        with open(os.path.join(TOOLKIT, fc.golden_path(name)), encoding="utf-8") as fh:
            golden = {r["id"]: r for r in json.load(fh)["fences"]}
        d, c = golden[diff.id], golden[checks.id]
        assert d["route"] == "runner" and c["route"] == "runner", name
        assert d["placeholders"] == ["branch", "integrationBranch", "worktree"], name
        assert "tied" not in d and d["reach"] == ["git diff", "git fetch", "git rev-parse"], name
        assert c["placeholders"] == ["ciWait", "pr"] and c["tied"] == ["pr"], name
        assert c["sources"] == ["forge"] and "gh pr checks" in c["reach"], name
        assert "sleep" in c["reach"], name
    for fence in (diff, checks):
        assert _record(records, fence)["route"] == "runner"
    assert _record(records, checks)["tied"] == ["pr"]
    proc = subprocess.run([SHIM, "show", SHIP], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    for fence in (diff, checks):
        call = fr.runner_call(_record(records, fence), TOOLKIT, fr._placeholders_for(fence))
        assert proc.stdout.count(call) == 1, call
    assert "--arg ciWait='<ciWait>' --arg pr='<prNumber>'" in proc.stdout


@pytest.mark.parametrize("value,ok", [
    ("0", True), ("1", True), ("9", True), ("10", True), ("30", True), ("89", True),
    ("90", True), ("91", False), ("99", False), ("100", False), ("900", False),
    ("05", False), ("00", False), ("-1", False), ("", False), (" 5", False), ("5\n", False),
    ("1.5", False), ("1e1", False), ("$(sleep 999)", False),
])
def test_req719_ci_wait_admits_0_to_90_only(value, ok):
    """`ciWait` admits the integers 0 to 90 and nothing else, so one call lasts at most one
    interval plus one forge read."""
    ph = fc.PLACEHOLDERS["ciWait"]
    assert ph.arg == "ciWait" and not ph.pr
    assert (ph.check(value) is None) is ok, (value, ph.check(value))


def test_req719_diff_fence_refuses_an_unpushed_head(records, tmp_path):
    """BR-24: in a `--single-branch` clone whose branch is pushed, the diff fence fetches both
    refs and prints the three-dot, rename-aware diff from `origin/<integrationBranch>` to
    `HEAD`: a rename reads as one, and a commit that reached `main` after the branch was cut
    is not in it. With a commit not pushed it prints an error and no diff, and with the remote
    unreachable it prints the fetch error and no diff."""
    diff, _checks = ship_fences()
    fid = _record(records, diff)["id"]
    origin = origin_repo(tmp_path)

    def rename(wc):
        _git("-C", str(wc), "mv", "src/keep.py", "src/kept.py")
        with open(str(wc / "src" / "kept.py"), "a", encoding="utf-8") as fh:
            fh.write("added = 1\n")
        _git("-C", str(wc), "add", "-A")
    wc = branch_clone(tmp_path, origin, change=rename)
    # main moves on after the branch was cut: a two-dot diff would show this file removed.
    seed = tmp_path / "seed"
    (seed / "main_only.txt").write_text("main moved on\n")
    _git("-C", str(seed), "add", "main_only.txt")
    _git("-C", str(seed), "commit", "-q", "-m", "main moves on")
    _git("-C", str(seed), "push", "-q", str(origin), "main")
    assert tracking_ref(wc) is None
    rc, out, err = fence_run(fid, wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    assert "rename from src/keep.py" in out and "rename to src/kept.py" in out, out
    assert "+added = 1" in out and "main_only.txt" not in out, out
    assert "pr_diff=error" not in out and out.splitlines()[-1] == "pr_diff_rc=0", out
    assert tracking_ref(wc) == head(wc)
    # A commit that was not pushed: an error, and no diff.
    (wc / "src" / "b.py").write_text("b = 1\n")
    _git("-C", str(wc), "add", "src/b.py")
    _git("-C", str(wc), "commit", "-q", "-m", "not pushed")
    rc, out, err = fence_run(fid, wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    assert out.splitlines() == [
        "pr_diff=error",
        "detail=HEAD is not origin/%s, push first: the PR shows the remote head" % BRANCH,
        "pr_diff_rc=2"], out
    # The remote unreachable: the fetch error, and no diff.
    _git("-C", str(wc), "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    rc, out, err = fence_run(fid, wc, branch_args(wc))
    assert rc == 0, (rc, out, err)
    assert out.splitlines() == [
        "pr_diff=error", "detail=fetch of origin/main or origin/%s failed" % BRANCH,
        "pr_diff_rc=2"], out


# ------------------------------------------------------------------------ the CI fence
def _ci_wc(tmp_path, checks):
    """A working copy on :data:`PR_BRANCH` and a mock store where PR 101 is open on it with
    ``checks`` and PR 102 is open on another branch: ``(wc, store, env)``."""
    wc = repo_wc(tmp_path / "wc", commit=True)
    store = pr_store(tmp_path / "store", [mock_pr(101, PR_BRANCH, checks=checks),
                                          mock_pr(102, OTHER_BRANCH)])
    return wc, store, forge_env(store)


def _mock_calls(store):
    """``[op]`` the mock answered, then forgets them."""
    path = os.path.join(store, "calls.log")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        ops = [json.loads(ln)["op"] for ln in fh if ln.strip()]
    os.remove(path)
    return ops


def test_req719_ci_fence_reads_only_the_callers_pr_after_a_bounded_wait(records, tmp_path):
    """AC-18's CI fence, run: for the caller's PR it waits `ciWait` seconds and prints one
    read, verdict first. Another PR's number exits 65 (the tie) after the runner's one read
    and before any CI read, and a `ciWait` of 91 exits 65 (the pattern) before any forge
    call."""
    _diff, checks = ship_fences()
    fid = _record(records, checks)["id"]
    wc, store, env = _ci_wc(tmp_path, [{"name": "build", "state": "pass"},
                                       {"name": "docs", "state": "skipped"}])
    start = time.monotonic()
    rc, out, err = fence_run(fid, wc, ["--arg", "ciWait=1", "--arg", "pr=101"], env=env)
    assert rc == 0, (rc, out, err)
    assert time.monotonic() - start >= 1
    assert out.splitlines() == ["checks=pass", "check=pass\tbuild", "check=skipped\tdocs"], out
    assert _mock_calls(store) == ["pr_view", "pr_checks"]
    # Another PR's number: the runner's tie refuses it as a bad value; nothing of the fence ran.
    rc, out, err = fence_run(fid, wc, ["--arg", "ciWait=0", "--arg", "pr=102"], env=env)
    assert rc == fr.BAD_VALUE == 65, (rc, out, err)
    assert out == "" and err.startswith("fence_run_bad_value: %s: value for pr, 102" % fid), err
    assert _mock_calls(store) == ["pr_view"]
    # A wait above 90: the pattern refuses it before any forge call.
    rc, out, err = fence_run(fid, wc, ["--arg", "ciWait=91", "--arg", "pr=101"], env=env)
    assert rc == fr.BAD_VALUE, (rc, out, err)
    assert out == "" and err.startswith("fence_run_bad_value: %s: " % fid) and "ciWait" in err
    assert _mock_calls(store) == []


@pytest.mark.parametrize("checks,first", [
    ([{"name": "build", "state": "fail"}, {"name": "lint", "state": "pass"}], "checks=fail"),
    ([{"name": "build", "state": "pending"}], "checks=pending"),
    ([], "checks=none"),
])
def test_req719_ci_fence_prints_each_verdict(records, tmp_path, checks, first):
    """Each verdict the text acts on reaches the session as the first line of one call."""
    _diff, ci = ship_fences()
    wc, _store, env = _ci_wc(tmp_path, checks)
    rc, out, err = fence_run(_record(records, ci)["id"], wc,
                             ["--arg", "ciWait=0", "--arg", "pr=101"], env=env)
    assert rc == 0, (rc, out, err)
    lines = out.splitlines()
    assert lines[0] == first and lines[1:] == ["check=%s\t%s" % (c["state"], c["name"])
                                               for c in checks], out


# ------------------------------------------------------------------------ BR-25, AC-19
#: The statements BR-25 requires of Phase 7's text, each as the companion words it.
VERDICT_STATEMENTS = (
    "- `pass`: CI is green, and the end-of-phase line says so.",
    "- `none`: no CI checks are reported. The end-of-phase line says so, and the phase "
    "continues.",
    "- `fail`: name the failing checks (the `check=fail` lines) and handle them as a Phase 7 "
    "issue: fix, commit and push as in step 3, then read again as for `pending`.",
    "- `pending`: read again with `<ciWait>` set to `proceed.ci.interval_s`, at most "
    "`proceed.ci.max_reads` reads in all.",
    "`proceed.ci.max_reads` (default 20)",
    "`proceed.ci.interval_s` (default 30)",
    "An interval above 90 is read as 90.",
    "Pass `0` as `<ciWait>` on the first read and the interval on every later one, so no call "
    "lasts longer than one interval plus one forge read.",
    "with your file tool",
    "On the last read still `pending`, the phase never reports green.",
    "A solo run asks the operator whether to keep waiting, naming the pending checks.",
    "An unattended run (no operator present) stops and reports `blocked`, naming the pending "
    "checks in a `blockers` entry",
    '"reason": "ci-pending"',
    '"<repo-id>: clean, CI green" on `pass`',
    '"<repo-id>: clean, no CI checks reported" on `none`',
)
STEP_5 = ("5. **Lite lane:** if steps 3–4 added any commit, re-run the lane check "
          "(`proceed/phases-lite.md` \"The lane check\") before leaving this phase "
          "(REQ-652 AC-16).")
#: The template's commented `proceed:` block, after the commented `sprint:` one.
TEMPLATE_BLOCK = "# proceed:\n#   ci:\n#     max_reads: 20\n#     interval_s: 30\n"


def test_req719_phase_7_states_each_verdict_and_the_wait():
    """BR-25, AC-19: Phase 7 states each verdict's handling, the two config keys with their
    defaults and the cap on the interval, and that a wait that runs out never reports green:
    a solo run asks, an unattended run reports `blocked` naming the pending checks. Step 5 and
    the end-of-phase line's `Continue to Phase 8 immediately.` stay as they were, the
    template documents both keys in a commented block, and `proceed/SKILL.md` names them."""
    text = _read(SHIP)
    ship = phase7(text)
    for statement in VERDICT_STATEMENTS:
        assert ship.count(statement) == 1, statement
    assert STEP_5 in ship
    assert text.count("Continue to Phase 8 immediately.") == 1
    end = [ln for ln in ship.splitlines() if ln.startswith("**End-of-phase log**")]
    assert len(end) == 1 and end[0].endswith("Continue to Phase 8 immediately."), end
    skill = skill_phase7()
    for key in ("`proceed.ci.interval_s`", "`proceed.ci.max_reads`", "never green",
                "solo: ask the operator", "unattended: `blocked`"):
        assert key in skill, key
    template = _read("templates/config-template.yml")
    assert template.count(TEMPLATE_BLOCK) == 1
    assert template.index("\n# sprint:\n") < template.index(TEMPLATE_BLOCK)
    assert template.index(TEMPLATE_BLOCK) < template.index("\ngcp:\n")
    block = template[template.rindex("# ----", 0, template.index(TEMPLATE_BLOCK)):]
    block = block[:block.index(TEMPLATE_BLOCK)]
    assert "Defaults: `max_reads` 20 and `interval_s` 30. An interval above 90 is read" in block
    assert not [ln for ln in TEMPLATE_BLOCK.splitlines() if not ln.startswith("#")]


def test_req719_phase_7_survives_the_exec_prompt():
    """The exec view keeps Phase 7 whole, with the merge-gate rewrite of its last sentence,
    and the prompt scan finds no refused token in it."""
    view = ep.companion_view(TOOLKIT, SHIP)
    section = view[view.index("### Phase 7: PR Cleanup & CI\n"):]
    assert "Continue to the merge gate immediately." in section
    assert "Continue to Phase 8 immediately." not in view
    assert "adlc_forge_pr_checks '<prNumber>'" in section and "On the last read" in section
    assert ep.scan(section) == []
