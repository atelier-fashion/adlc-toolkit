"""BUG-288: `/architect` Step 5's footprint fence is held to the caller's PR.

The fence read `prNumber` from `pipeline-state.json`, a file the session writes, and handed it
to `adlc_forge_pr_view` and `adlc_forge_pr_edit`. Under `/sprint --exec` the fence runs outside
the sandbox with the run's forge credential, and it was the one routed fence outside the PR tie
(`fence_census.DECLARED_UNTIED`), so a session that wrote another PR's number into its state
file had that PR's body rewritten.

The fence now takes the PR as the marked `$prNumber`, so the runner reads it back from the
forge before any command of the fence runs (REQ-719 ADR-3), and it publishes one repo's
footprint to that one PR.

Every case runs offline against the stateful mock forge (``tools/adlc/forge_mock.py``) in a
throwaway store, through ``fence_run.run``. The argv is built from the record's own
placeholders, so the same cases run against the fence as it was: there they fail on the first
assertion, that PR 202 is untouched.
"""

import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import toolkit_root  # noqa: E402
from test_fence_run import PR_BRANCH, forge_env, memo_census, mock_pr, pr_store, repo_wc  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
RUN_REQ = "REQ-901"
OTHER_BRANCH = "feat/REQ-902-other"
OWN_PR = 101
OTHER_PR = 202
TIE_ARGV = ["--fields", ",".join(fc.PR_TIE_FIELDS)]
TICK = "`" * 3


@pytest.fixture(scope="module")
def records():
    return fc.census(TOOLKIT)


@pytest.fixture
def cached(monkeypatch, records):
    memo_census(monkeypatch)
    return records


def _footprint(records):
    hits = [r for r in records if r["route"] == "runner" and
            r["id"].startswith("architect/SKILL.md#") and "MAPPER_PATHS" in r["placeholders"]]
    assert len(hits) == 1, [r["id"] for r in hits]
    return hits[0]


class Run(object):
    """An exec run of :data:`RUN_REQ`: a working copy on :data:`PR_BRANCH`, a mock store with
    PR 101 open on that branch and PR 202 open on another REQ's, and the REQ's spec directory
    with one task and a ``pipeline-state.json`` that names ``state_pr`` as the repo's PR."""

    def __init__(self, tmp_path, state_pr):
        self.wc = repo_wc(tmp_path / "wc", commit=True)
        self.store = pr_store(tmp_path / "store", [mock_pr(OWN_PR, PR_BRANCH),
                                                   mock_pr(OTHER_PR, OTHER_BRANCH)])
        self.env = forge_env(self.store)
        self.env["ADLC_EXEC_RUN"] = RUN_REQ
        spec = os.path.join(str(self.wc), ".adlc", "specs", "%s-thing" % RUN_REQ)
        os.makedirs(os.path.join(spec, "tasks"))
        with open(os.path.join(spec, "pipeline-state.json"), "w", encoding="utf-8") as fh:
            json.dump({"req": RUN_REQ, "repos": {"solo": {"primary": True,
                                                          "prNumber": state_pr}}}, fh, indent=2)
        with open(os.path.join(spec, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nid: TASK-001\n---\n## Files to Create/Modify\n"
                     "- `src/thing.py` — the file\n## Notes\n")
        with open(os.path.join(str(self.wc), "mapper.txt"), "w", encoding="utf-8") as fh:
            fh.write("src/mapped.py\n")

    def argv(self, rec, pr):
        """The call a session makes: the REQ, the mapper list, and ``pr`` as the PR number
        when the fence takes one (``None`` leaves it out)."""
        out = ["--arg", "REQ=%s" % RUN_REQ, "--arg-file", "MAPPER_PATHS=mapper.txt"]
        if pr is not None and "prNumber" in rec["placeholders"]:
            out += ["--arg", "prNumber=%s" % pr]
        return out

    def run(self, rec, argv, **env):
        err = io.StringIO()
        rc = fr.run(rec["id"], argv, TOOLKIT, environ=dict(self.env, **env),
                    cwd=str(self.wc), err=err)
        return rc, err.getvalue()

    def pr(self, number):
        with open(os.path.join(self.store, "prs.json"), encoding="utf-8") as fh:
            return next(p for p in json.load(fh)["prs"] if p["number"] == number)

    def calls(self):
        path = os.path.join(self.store, "calls.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [(c["op"], c["argv"]) for c in map(json.loads, fh) if c]


def _untouched(run, number):
    assert run.pr(number)["body"] == "body of %d" % number, \
        "BUG-288: PR %d was rewritten: %r" % (number, run.pr(number)["body"])


def test_bug288_a_state_file_naming_another_pr_cannot_rewrite_it(cached, tmp_path):
    """The reproduction: the session writes PR 202 into its own state file and passes 202.
    PR 202 is another branch's, so the runner answers 65 before any command of the fence, and
    the only forge call is its own read."""
    run = Run(tmp_path, state_pr=OTHER_PR)
    rec = _footprint(cached)
    rc, err = run.run(rec, run.argv(rec, OTHER_PR))
    _untouched(run, OTHER_PR)
    _untouched(run, OWN_PR)
    assert rc == fr.BAD_VALUE == 65, (rc, err)
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith("fence_run_bad_value: %s: " % rec["id"]), err
    assert "prNumber" in lines[0] and str(OTHER_PR) in lines[0] and PR_BRANCH in lines[0]
    assert run.calls() == [("pr_view", [str(OTHER_PR)] + TIE_ARGV)]


def test_bug288_the_state_file_alone_chooses_no_pr(cached, tmp_path):
    """The state file still names PR 202, and the session gives no PR number, or its own: the
    fence has no PR number but the bound one, so no PR is edited that the caller did not name
    and the runner did not tie. With its own PR the fence finds the state file disagrees and
    publishes nothing."""
    run = Run(tmp_path, state_pr=OTHER_PR)
    rec = _footprint(cached)
    rc, err = run.run(rec, run.argv(rec, None))
    _untouched(run, OTHER_PR)
    assert rc == fr.BAD_VALUE, (rc, err)
    assert "no value for prNumber" in err, err
    assert run.calls() == []
    rc, err = run.run(rec, run.argv(rec, OWN_PR))
    _untouched(run, OTHER_PR)
    _untouched(run, OWN_PR)
    assert rc != 0 and "fence_run_" not in err and "opaque_entry_refused" not in err, (rc, err)
    assert [op for op, _argv in run.calls()] == ["pr_view"], run.calls()


def test_bug288_the_runs_own_pr_still_gets_its_footprint(cached, tmp_path):
    """Benign path: the state file names the run's own PR and the session passes it. The
    runner's read comes first, then the fence reads the body and writes it back with the
    footprint block; PR 202 is untouched."""
    run = Run(tmp_path, state_pr=OWN_PR)
    rec = _footprint(cached)
    rc, err = run.run(rec, run.argv(rec, OWN_PR))
    assert rc == 0 and err == "", (rc, err)
    _untouched(run, OTHER_PR)
    block = "%sadlc-footprint\nsolo:src/thing.py\n%s\n" % (TICK, TICK)
    assert run.pr(OWN_PR)["body"] == "body of %d\n\n%s" % (OWN_PR, block), run.pr(OWN_PR)["body"]
    calls = run.calls()
    assert calls[0] == ("pr_view", [str(OWN_PR)] + TIE_ARGV), calls
    assert [op for op, _argv in calls] == ["pr_view", "pr_view", "pr_edit"], calls
    assert all(argv[0] == str(OWN_PR) for _op, argv in calls), calls
    # A second run replaces the block instead of adding one: the body round trip is exact.
    with open(os.path.join(str(run.wc), ".adlc", "specs", "%s-thing" % RUN_REQ, "tasks",
                           "TASK-002.md"), "w", encoding="utf-8") as fh:
        fh.write("## Files to Create/Modify\n- `src/more.py` — another\n")
    rc, err = run.run(rec, run.argv(rec, OWN_PR))
    assert rc == 0 and err == "", (rc, err)
    block = "%sadlc-footprint\nsolo:src/more.py\nsolo:src/thing.py\n%s\n" % (TICK, TICK)
    assert run.pr(OWN_PR)["body"] == "body of %d\n\n%s" % (OWN_PR, block), run.pr(OWN_PR)["body"]
    _untouched(run, OTHER_PR)


def test_bug288_another_runs_branch_is_refused_before_any_read(cached, tmp_path):
    """Under an exec run the branch checked out must be the run's own, so a session of
    another REQ on this branch is refused with no forge call (REQ-719 BR-9)."""
    run = Run(tmp_path, state_pr=OWN_PR)
    rec = _footprint(cached)
    rc, err = run.run(rec, run.argv(rec, OWN_PR), ADLC_EXEC_RUN="REQ-777")
    _untouched(run, OWN_PR)
    assert rc == fr.REFUSED == 3, (rc, err)
    assert err.startswith("opaque_entry_refused: %s: " % rec["id"]), err
    assert run.calls() == []


def test_bug288_the_spec_is_not_read_from_outside_the_calling_directory(cached, tmp_path):
    """`PRIMARY_WORKTREE` names where the spec is looked for when the fence runs in a sibling
    repo's worktree. Under the runner the value must name the calling directory or one under
    it, so a session cannot point the fence at another checkout by this value: 65 with no
    forge call. `.` and the calling directory itself are the same run as none. The check holds
    the value only; a symlink inside the working copy is not followed up (a declared
    residual, older than this bug)."""
    run = Run(tmp_path, state_pr=OWN_PR)
    rec = _footprint(cached)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    rc, err = run.run(rec, run.argv(rec, OWN_PR) + ["--arg", "PRIMARY_WORKTREE=%s" % outside])
    assert rc == fr.BAD_VALUE, (rc, err)
    assert "PRIMARY_WORKTREE" in err and "outside the working directory" in err, err
    assert run.calls() == []
    _untouched(run, OWN_PR)
    for value in (".", str(run.wc)):
        rc, err = run.run(rec, run.argv(rec, OWN_PR) + ["--arg", "PRIMARY_WORKTREE=%s" % value,
                                                        "--arg", "REPO_ID=solo"])
        assert rc == 0 and err == "", (value, rc, err)
    assert "solo:src/thing.py" in run.pr(OWN_PR)["body"]
    rc, err = run.run(rec, run.argv(rec, OWN_PR) + ["--arg", "REPO_ID=../x"])
    assert rc == fr.BAD_VALUE and "REPO_ID" in err, (rc, err)


def test_bug288_the_footprint_fence_is_tied_and_no_fence_is_exempt(records):
    """The fence binds the marked `prNumber`, its record names it under `tied`, every PR
    operation in it is a closed shape, and the census holds no `untied` record and no
    exemption table."""
    rec = _footprint(records)
    assert rec.get("tied") == ["prNumber"], rec
    assert not hasattr(fc, "DECLARED_UNTIED")
    assert [r["id"] for r in records if "untied" in r] == []
    index = int(rec["id"].split("#")[1].split(":")[0]) - 1
    code = fc.fences(fc.view(TOOLKIT, "architect/SKILL.md"), "architect/SKILL.md")[index].code
    assert fc.unmarked_pr_arguments(code) == [] and fc.pr_operation_problems(code) == []
    for adapter in fc.exec_adapters(TOOLKIT):
        with open(os.path.join(TOOLKIT, fc.golden_path(adapter.name)), encoding="utf-8") as fh:
            golden = {r["id"]: r for r in json.load(fh)["fences"]}
        assert golden[rec["id"]].get("tied") == ["prNumber"], adapter.name
        assert not [r for r in golden.values() if "untied" in r], adapter.name
