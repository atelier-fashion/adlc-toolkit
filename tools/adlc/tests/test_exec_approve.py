"""Approval, the one-way moves and the close-out (REQ-659)."""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_gates as eg  # noqa: E402
import exec_helpers as eh  # noqa: E402
import exec_ledger as el  # noqa: E402
import exec_prompt as ep  # noqa: E402
import exec_safety as es  # noqa: E402
import sprint_exec as se  # noqa: E402

REQ = "REQ-901"


@pytest.fixture
def box(tmp_path):
    return eh.Sandbox(tmp_path)


def merged_count(box):
    return len(box.calls("pr_merge"))


def test_happy_path(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    token, _ = box.tokens(REQ)
    assert token
    assert box.approve(orch) == "approved"
    assert run.status == "merged"
    state = run.read_primary_state()
    assert state["status"] == "merged" and state["completed"] is True
    assert 8 in state["completedPhases"] and state["currentPhase"] == 8
    assert state["closeOut"]["status"] == "ok" and state["repos"]["widgets"]["merged"] is True
    assert state["approval"]["decision"] == "approved" and state["approval"]["channel"] == "shell"
    assert run.exec["trustGrantedAt"] and run.exec["trustRevokedAt"]
    assert not os.path.exists(run.wc)
    assert not os.path.exists(os.path.join(str(box.repo), ".worktrees", "REQ-901-close-out"))
    merges = box.calls("pr_merge")
    assert len(merges) == 2
    assert merges[0]["argv"][1:3] == ["--squash", "--delete-branch"]
    assert "--match-head-commit" in merges[0]["argv"] and "--match-head-commit" in merges[1]["argv"]
    log = box.log(run)
    names = [(r["kind"], " ".join(r["argv"])) for r in log]
    trial = next(i for i, (k, a) in enumerate(names) if "adlc_trial_merge" in a)
    merge = next(i for i, (k, a) in enumerate(names) if "adlc_forge_pr_merge" in a)
    verify = next(i for i, (k, a) in enumerate(names) if "adlc_forge_pr_view" in a and i > 0 and
                  "headRefOid" in a)
    resume = next(i for i, (k, a) in enumerate(names) if k == "exec_launch" and "--resume" in a)
    assert verify < trial < merge < resume
    trial_cwd = [r for r in log if r["kind"] == "git" and "worktree" in r["argv"]
                 and "--detach" in r["argv"]]
    assert trial_cwd and all(run.path in " ".join(r["argv"]) for r in trial_cwd)
    argv = json.load(open(str(box.home / "closeout-argv-REQ-901.json")))
    assert argv[argv.index("--resume") + 1] == "session-REQ-901"
    assert "--strict-mcp-config" in argv and argv[argv.index("--setting-sources") + 1] == "user"
    settings = argv[argv.index("--settings") + 1]
    assert settings == run.file("settings.json")
    assert "hooks" not in json.load(open(settings))
    assert argv[argv.index("--add-dir") + 1].endswith(box.spec_dirs[REQ])
    assert run.exec["closeOutPid"]
    prompt = open(str(box.home / "closeout-prompt-REQ-901.txt")).read()
    assert "WORKTREE PATH (mandatory): %s" % os.path.join(os.path.realpath(str(box.repo)),
                                                          ".worktrees", "REQ-901-close-out") in prompt
    assert "chore/REQ-901-close-out" in prompt
    assert merges and state["repos"]["widgets"]["merged"]
    merge_commit = run.doc["recordedMerges"][0]
    assert merge_commit in prompt
    assert not ep.scan(prompt, "close-out")
    assert "merged" in box.out.getvalue()
    assert "exec" in open(box.environ["ADLC_RUN_OUTCOMES_LOG"]).read()
    assert "1" == eh.git(box.repo, "branch", "--list", "feat/REQ-901-thing").strip() or \
        eh.git(box.repo, "branch", "--list", "feat/REQ-901-thing").strip() == ""


def test_channel_is_recorded(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch, drain=False, channel="skill")
    decision = run.ledger().read()["decision"]
    assert decision["channel"] == "skill" and decision["decidedBy"] == "operator"
    assert run.read_primary_state()["approval"]["channel"] == "skill"


def test_reject(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    orch.reject(REQ, "not this sprint", decided_by="operator", channel="skill", caller_pid=7)
    assert run.status == "rejected"
    assert run.ledger().read()["decision"]["reason"] == "not this sprint"
    state = run.read_primary_state()
    assert state["status"] == "rejected" and state["approval"]["reason"] == "not this sprint"
    assert state["approval"]["decidedBy"] == "operator" and state["approval"]["channel"] == "skill"
    assert merged_count(box) == 0 and os.path.isdir(run.wc)
    assert eh.git(box.bare, "rev-parse", "--verify", "feat/REQ-901-thing")
    assert run.exec["trustRevokedAt"]
    with pytest.raises(se.Refused, match="not awaiting_approval"):
        orch.reject(REQ, "again", decided_by="operator")


def test_queue(tmp_path):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"shared/a.txt": "901\n"})
    # REQ-483's rank is the earliest-published PR, so REQ-902 publishes second.
    box.req("REQ-902", files={"shared/a.txt": "901\n", "b.txt": "902\n"}, sleep_first=1.5)
    orch = box.go(shared=True)
    second = orch.runs["REQ-902"]
    first = orch.runs[REQ]
    assert box.approve(orch, "REQ-902", drain=False) == "approved (queued behind REQ-901)"
    assert "approved (queued behind REQ-901)" in "\n".join(se.render_row(second))
    assert second.read_primary_state()["approval"]["holdBehind"] == "REQ-901"
    orch.drain()
    assert second.status == "approved", "nothing merges ahead of the REQ it overlaps"
    box.approve(orch, REQ)
    assert first.status == "merged"
    assert second.status in ("merged", "blocked")
    assert second.doc.get("holdBehind") is None


def test_queue_released_by_reject(tmp_path):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"shared/a.txt": "901\n"})
    box.req("REQ-902", files={"shared/a.txt": "902\n"}, sleep_first=1.5)
    orch = box.go(shared=True)
    box.approve(orch, "REQ-902", drain=False)
    orch.reject(REQ, "no", decided_by="operator")
    orch.drain()
    assert orch.runs["REQ-902"].status == "merged"


def conflicting(tmp_path):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"README.md": "AAA\nline two\nline three\n"})
    box.req("REQ-902", files={"README.md": "BBB\nline two\nline three\n"}, sleep_first=1.5)
    return box


def test_rebase_conflict(tmp_path):
    box = conflicting(tmp_path)
    orch = box.go(shared=True)
    second = orch.runs["REQ-902"]
    before = {}
    for name in os.listdir(second.wc):
        before[name] = os.path.getmtime(os.path.join(second.wc, name))
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    assert box.approve(orch, "REQ-902", drain=False) == "approved"
    orch.drain()
    assert second.status == "blocked"
    state = second.read_primary_state()
    entry = state["blockers"][0]
    assert entry["conflictFiles"] == ["README.md"] and entry["rebaseAttempts"] == 1
    assert "a person must resolve README.md" in box.out.getvalue()
    assert merged_count(box) == 2, "REQ-902 was not merged anyway"
    assert {n: os.path.getmtime(os.path.join(second.wc, n)) for n in before} == before
    log = [r for r in box.log(second) if r["kind"] == "git" and "rebase" in r["argv"]]
    assert log and all(r["cwd"].startswith(second.path) for r in log)
    assert any("--abort" in r["argv"] for r in log)


def test_rebase_clean(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"), lane="full")
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"})
    orch = box.go(shared=True)
    box.approve(orch, REQ)
    second = orch.runs["REQ-902"]
    recorded = second.ledger().read()["plan"]["prs"][0]["headRefOid"]
    real = eg.trial_merge
    seen = []

    def trial(toolbox, repo, path, ib):
        seen.append(path)
        if len(seen) == 1:
            return 1, ["b.txt"]
        return real(toolbox, repo, path, ib)
    monkeypatch.setattr(eg, "trial_merge", trial)
    box.approve(orch, "REQ-902")
    assert second.status == "merged"
    push = [r for r in box.log(second) if r["kind"] == "git" and "push" in r["argv"]]
    assert push[0]["argv"][4 + 0:] and "--force-with-lease=feat/REQ-902-thing:%s" % recorded in \
        push[0]["argv"]
    assert "HEAD:refs/heads/feat/REQ-902-thing" in push[0]["argv"]
    assert push[0]["cwd"].startswith(second.path)
    assert len(seen) == 2
    pin = box.calls("pr_merge")[2]["argv"]
    assert recorded not in pin, "the merge pins the rebased head, which the ledger now holds"


def test_rebase_mismatch_pushes_nothing(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"})
    orch = box.go(shared=True)
    box.approve(orch, REQ)
    second = orch.runs["REQ-902"]
    monkeypatch.setattr(eg, "trial_merge", lambda *a: (1, ["b.txt"]))
    monkeypatch.setattr(eg, "changed_paths", lambda *a: [["A", "other.txt"]])
    box.approve(orch, "REQ-902")
    assert second.status == "blocked"
    assert "changed-path set" in json.dumps(second.read_primary_state()["blockers"])
    assert not [r for r in box.log(second) if r["kind"] == "git" and "push" in r["argv"]
                and "--force-with-lease" in " ".join(r["argv"])]


def test_rebase_that_changes_a_patch_is_refused(tmp_path, monkeypatch):
    """The two edits sit in one hunk's context, so the patch differs and range-diff says `!`."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"README.md": "AAA\nline two\nline three\n"})
    box.req("REQ-902", files={"README.md": "line one\nline two\nCCC\n"}, sleep_first=1.5)
    orch = box.go(shared=True)
    box.approve(orch, REQ)
    second = orch.runs["REQ-902"]
    monkeypatch.setattr(eg, "trial_merge", lambda *a: (1, ["README.md"]))
    box.approve(orch, "REQ-902")
    assert second.status == "blocked"
    assert "range-diff" in json.dumps(second.read_primary_state()["blockers"])
    assert not [r for r in box.log(second) if r["kind"] == "git"
                and "--force-with-lease" in " ".join(r["argv"])]


def test_rebase_moved_branch_rehalts(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"})
    orch = box.go(shared=True)
    box.approve(orch, REQ)
    second = orch.runs["REQ-902"]
    monkeypatch.setattr(eg, "trial_merge", lambda *a: (1, ["b.txt"]))
    real = eg.fetch_branch
    calls = []

    def moved(toolbox, repo, branch):
        calls.append(branch)
        return "0" * 40 if len(calls) == 3 else real(toolbox, repo, branch)
    monkeypatch.setattr(eg, "fetch_branch", moved)
    box.approve(orch, "REQ-902")
    assert "re-halted" in box.out.getvalue()
    assert not [r for r in box.log(second) if r["kind"] == "git"
                and "--force-with-lease" in " ".join(r["argv"])]


def test_answer(box):
    box.req(status="blocked", claim="blocked",
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "sid": "session-two", "blockers": None, "files": {"z.txt": "z\n"}})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    first_pid = run.exec["pid"]
    assert run.status == "blocked"
    assert run.read_primary_state()["blockers"][0]["question"] == "which?"
    orch.answer(REQ, "the second option")
    box.wait(orch)
    assert run.exec["pid"] != first_pid and run.exec["sessionId"] == "session-two"
    assert run.status == "awaiting_approval"
    argv = open(str(box.home / "argv-REQ-901.json")).read().splitlines()
    assert len(argv) == 2 and "--resume" not in json.loads(argv[1])
    assert "the second option" in open(run.file("prompt.2.txt")).read()
    assert run.exec["promptPath"] == "prompt.2.txt"


def test_doctored_state(box, tmp_path):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    pristine = run.read_primary_state()
    sentinel = tmp_path / "pwned"
    bad = dict(pristine, approval={"action": "merge; rm -rf /",
                                   "command": "$(touch %s)" % sentinel})
    run.write_primary_state(bad)
    with pytest.raises(se.Refused, match="approval.action"):
        box.approve(orch)
    bad = json.loads(json.dumps(pristine))
    bad["repos"]["widgets"]["prUrl"] = "https://evil.example/acme/widgets/pull/101"
    run.write_primary_state(bad)
    with pytest.raises(se.Refused, match="prUrl"):
        box.approve(orch)
    bad = dict(pristine, approval=dict(pristine["approval"], decision="approved",
                                       decidedBy="$USER"))
    run.write_primary_state(bad)
    with pytest.raises(se.Refused, match="no ledger entry"):
        box.approve(orch)
    assert "no ledger entry" in "\n".join(se.violations_of(run))
    assert not sentinel.exists() and merged_count(box) == 0
    assert run.ledger().read()["decision"] is None


def test_model_written_decision_is_a_violation_at_exit(box):
    box.req(approval={"decision": "approved", "decidedBy": "model"})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert "no ledger entry" in "\n".join(se.violations_of(run))
    assert "decision" not in run.read_primary_state()["approval"]


def test_approval_guards(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    token, _ = box.tokens(REQ)
    with pytest.raises(se.Refused, match="Rule B"):
        orch.approve(REQ, token, decided_by="op", caller_env={"ADLC_EXEC_RUN": REQ})
    assert run.ledger().read()["decision"] is None
    assert "inside a run" in "\n".join(se.render_row(run, se.violations_of(run)))
    run.exec["pid"] = os.getpid()
    with pytest.raises(se.Refused, match="Rule B"):
        orch.approve(REQ, token, decided_by="op", caller_pid=os.getpid())
    with pytest.raises(se.Refused, match="still alive"):
        orch.approve(REQ, token, decided_by="op")
    run.exec["pid"] = None
    with pytest.raises(se.Refused, match="token"):
        orch.approve(REQ, "0" * 32, decided_by="op")
    with pytest.raises(se.Refused, match="token"):
        orch.approve(REQ, "", decided_by="op")
    assert orch.approve(REQ, token, decided_by="op") == "approved"
    with pytest.raises(se.Refused, match="not awaiting_approval"):
        orch.approve(REQ, token, decided_by="op")


def test_token_is_spent_and_never_on_disk(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    token, _ = box.tokens(REQ)
    for base, _dirs, files in os.walk(run.path):
        for name in files:
            with open(os.path.join(base, name), "rb") as fh:
                assert token.encode() not in fh.read(), name
    assert token not in json.dumps(orch.tokens)
    box.approve(orch)
    assert REQ not in orch.tokens


def test_prompt_never_names_the_run_directory(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    data = open(run.file("prompt.txt")).read()
    assert run.path not in data and os.path.basename(run.path) not in data
    assert run.path not in json.dumps(run.read_primary_state())


def test_unaccounted_ledger_after_the_halt(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    doc = run.ledger().read()
    doc["plan"]["deployPlan"] = {"target": "x", "command": "touch y"}
    with open(run.file(el.LEDGER), "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(se.Refused, match="does not match"):
        box.approve(orch)
    assert "does not account" in "\n".join(se.violations_of(run))


@pytest.mark.parametrize("scenario,field", [
    ("pr-replaced", "number"), ("pr-other-repo", "repo"), ("cross-repo", "isCrossRepository"),
    ("base-other", "baseRefName"), ("second-open-pr", "number")])
def test_binding(tmp_path, scenario, field):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.scenario_file(scenario)
    box.approve(orch)
    assert run.status == "awaiting_approval", field
    assert merged_count(box) == 0
    doc = run.ledger().read()
    assert doc["decision"] is None
    assert doc["superseded"][0]["supersededBecause"] == field
    assert "re-halted: %s" % field in box.out.getvalue()


def test_head_advanced_after_the_halt(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    env = dict(box.environ)
    subprocess.check_call([sys.executable, os.path.join(eh.TOOLKIT, "tools", "adlc",
                                                        "forge_mock.py"), "make-head",
                           "feat/REQ-901-thing", "main", "--commit-on-branch", "n.txt=n\n"],
                          env=env, stdout=subprocess.DEVNULL)
    old = run.ledger().read()["plan"]["prs"][0]["headRefOid"]
    box.approve(orch)
    assert merged_count(box) == 0 and run.status == "awaiting_approval"
    doc = run.ledger().read()
    assert doc["superseded"][0]["supersededBecause"] == "headRefOid"
    assert doc["plan"]["prs"][0]["headRefOid"] != old
    new_token, _ = box.tokens(REQ)
    box.approve(orch, token=new_token)
    assert run.status == "merged"


def test_head_advanced_between_check_and_merge(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    real = orch._merge_pinned

    def racing(a_run, rid, pr):
        box.scenario_file("head-advances")
        return real(a_run, rid, pr)
    monkeypatch.setattr(orch, "_merge_pinned", racing)
    box.approve(orch)
    argv = box.calls("pr_merge")[0]["argv"]
    assert "--match-head-commit" in argv
    assert run.status == "awaiting_approval", "a refused merge waits for a fresh approve"
    assert eh.git(box.bare, "log", "--format=%s", "main").count("\n") == 1
    assert "merge refused by policy" in run.ledger().read()["superseded"][0]["supersededBecause"]


def test_merged_pr_on_exit_is_a_violation(box):
    box.req(merge_itself=True)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    assert se.violations_of(run)


def test_merged_pr_at_approval_still_closes_out(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    pr = run.ledger().read()["plan"]["prs"][0]
    env = dict(box.environ)
    subprocess.check_call([sys.executable, os.path.join(eh.TOOLKIT, "tools", "adlc",
                                                        "forge_mock.py"), "pr_merge",
                           str(pr["number"]), "--squash"], env=env, stdout=subprocess.DEVNULL)
    commit = eh.git(box.bare, "rev-parse", "main").strip()
    orch.recorded_merges = lambda: {commit}
    box.approve(orch)
    assert "already MERGED" in "\n".join(se.violations_of(run))
    assert run.status == "merged"
    assert run.read_primary_state()["repos"]["widgets"]["merged"] is True
    assert merged_count(box) == 2, "the mock call above, then the chore PR"


def test_push_after_exit_before_approve(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    eh.git(box.repo, "fetch", "-q", "origin")
    clone = box.tmp / "late"
    eh.git(box.tmp, "clone", "-q", str(box.bare), str(clone))
    (clone / "late.txt").write_text("late\n")
    env = dict(os.environ, HOME=str(box.home))
    subprocess.check_call(["git", "-C", str(clone), "add", "-A"], env=env)
    subprocess.check_call(["git", "-C", str(clone), "commit", "-qm", "late"], env=env)
    subprocess.check_call(["git", "-C", str(clone), "push", "-q", "origin", "main"], env=env)
    box.approve(orch)
    assert merged_count(box) == 0
    assert run.status == "blocked"
    assert "neither a recorded orchestrator merge" in "\n".join(se.violations_of(run))


def chore_case(tmp_path, closeout, **behaviour):
    box = eh.Sandbox(tmp_path)
    box.req(closeout=closeout, **behaviour)
    orch = box.go(shared=True)
    return box, orch, orch.runs[REQ]


@pytest.mark.parametrize("scenario,field", [
    ("merged", "state"), ("head-other", "headRefName"), ("base-other", "baseRefName"),
    ("cross-repo", "isCrossRepository"), ("pr-other-repo", "repo")])
def test_chore_gate_fields(tmp_path, monkeypatch, scenario, field):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    real = orch._chore_gate

    def gate(a_run, url, branch):
        box.scenario_file(scenario)
        try:
            return real(a_run, url, branch)
        finally:
            box.scenario_file("ok")
    monkeypatch.setattr(orch, "_chore_gate", gate)
    box.approve(orch)
    closing = run.read_primary_state()["closeOut"]
    assert closing == {"status": "failed", "reason": "chore PR out of bounds: %s" % field,
                       "at": closing["at"]}
    assert merged_count(box) == 1, "only the feature PR merged"
    assert run.status == "merged"


def test_chore_gate_ignores_the_forge_files_list(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path)
    box.req(closeout={"files": {".github/workflows/ci.yml": "x\n"}})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    real = orch._chore_gate

    def gate(a_run, url, branch):
        doc = json.load(open(str(box.store / "prs.json")))
        doc["prs"][-1]["filesOverride"] = [".adlc/knowledge/lessons/LESSON-9001-thing.md"]
        (box.store / "prs.json").write_text(json.dumps(doc))
        return real(a_run, url, branch)
    monkeypatch.setattr(orch, "_chore_gate", gate)
    box.approve(orch)
    assert run.read_primary_state()["closeOut"]["status"] == "needs-review"
    assert merged_count(box) == 1


def lesson_path(n=9002):
    return ".adlc/knowledge/lessons/LESSON-%d-other.md" % n


@pytest.mark.parametrize("files", [
    {".github/workflows/ci.yml": "x\n"},
    {".adlc/context/architecture.md": "x\n"},
    {"src/code.py": "x\n"},
    {lesson_path(): "no frontmatter\n"},
])
def test_chore_gate_paths(tmp_path, files):
    box, orch, run = chore_case(tmp_path, {"files": files})
    box.approve(orch)
    state = run.read_primary_state()
    assert state["closeOut"]["status"] == "needs-review", files
    assert merged_count(box) == 1 and run.status == "merged"


@pytest.mark.parametrize("spec,label", [
    (["mv:.adlc/specs/REQ-901-thing/requirement.md=.github/workflows/ci.yml"], "rename"),
    (["link:.adlc/knowledge/lessons/LESSON-1-a.md=/etc/passwd"], "symlink"),
    (["gitlink:.adlc/knowledge/lessons/sub=" + "a" * 40], "submodule"),
    ([".adlc/knowledge/lessons/LESSON-1-a.md:100755=x\n"], "mode"),
    (["rm:.adlc/specs/REQ-901-thing/requirement.md"], "delete-spec"),
])
def test_chore_gate_plumbing(tmp_path, monkeypatch, spec, label):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    real = orch._chore_gate

    def gate(a_run, url, branch):
        subprocess.check_call([sys.executable, os.path.join(eh.TOOLKIT, "tools", "adlc",
                                                            "forge_mock.py"), "make-head", branch,
                               "main", "--commit-on-branch"] + spec, env=dict(box.environ),
                              stdout=subprocess.DEVNULL)
        return real(a_run, url, branch)
    monkeypatch.setattr(orch, "_chore_gate", gate)
    box.approve(orch)
    assert run.read_primary_state()["closeOut"]["status"] == "needs-review", label
    assert merged_count(box) == 1


def test_chore_gate_refuses_a_modified_lesson(tmp_path):
    box = eh.Sandbox(tmp_path)
    path = ".adlc/knowledge/lessons/LESSON-9000-old.md"
    os.makedirs(str(box.repo / ".adlc" / "knowledge" / "lessons"))
    (box.repo / path).write_text(eh.LESSON)
    env = dict(os.environ, HOME=str(box.home))
    subprocess.check_call(["git", "-C", str(box.repo), "add", "-A"], env=env)
    subprocess.check_call(["git", "-C", str(box.repo), "commit", "-qm", "l"], env=env)
    subprocess.check_call(["git", "-C", str(box.repo), "push", "-q", "origin", "main"], env=env)
    box.req(closeout={"files": {path: eh.LESSON + "\nchanged\n"}})
    orch = box.go(shared=True)
    box.approve(orch)
    assert orch.runs[REQ].read_primary_state()["closeOut"]["status"] == "needs-review"


def test_clean_chore_pr_may_touch_spec_and_tasks(tmp_path):
    spec = ".adlc/specs/REQ-901-thing/requirement.md"
    task = ".adlc/specs/REQ-901-thing/tasks/TASK-1-x.md"
    box, orch, run = chore_case(tmp_path, {"files": {
        spec: "---\nstatus: complete\n---\n", task: "x\n",
        ".adlc/knowledge/assumptions/ASSUME-9-x.md": "x\n",
        ".adlc/knowledge/lessons/LESSON-9001-thing.md": eh.LESSON}})
    box.approve(orch)
    assert run.read_primary_state()["closeOut"]["status"] == "ok"
    assert merged_count(box) == 2


def test_close_out_crash_records_failed(tmp_path):
    box, orch, run = chore_case(tmp_path, {"crash": True})
    box.approve(orch)
    assert run.read_primary_state()["closeOut"]["status"] == "failed"
    assert run.status == "merged" and merged_count(box) == 1


def test_no_session_means_no_close_out(tmp_path):
    box = eh.Sandbox(tmp_path)
    box.req(no_session=True)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    state = run.read_primary_state()
    assert state["closeOut"]["reason"] == "no session id" and state["repos"]["widgets"]["merged"]
    assert run.status == "merged"


def test_config_isolation(tmp_path):
    box = eh.Sandbox(tmp_path)
    box.write_scenario(help="--setting-sources <s>\n--settings <f>\n")
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    state = run.read_primary_state()
    assert state["closeOut"] == {"status": "failed", "at": state["closeOut"]["at"],
                                 "reason": "harness config isolation unavailable"}
    assert run.status == "merged"
    assert not (box.home / "closeout-argv-REQ-901.json").exists()


DEPLOY = ("sprint:\n  exec:\n    child_gh_token: CHILD_GH\n    deploy:\n      target: prod\n"
          "      command: \"touch %s\"\n")


def test_deploy(tmp_path):
    sentinel = tmp_path / "deployed"
    box = eh.Sandbox(tmp_path, deployable="true", config=DEPLOY % sentinel)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    plan = run.ledger().read()["plan"]
    assert plan["deployPlan"]["command"] == "touch %s" % sentinel
    assert "touch %s" % sentinel in box.out.getvalue()
    (box.repo / ".adlc" / "config.yml").write_text("sprint:\n  exec:\n    deploy:\n      target: x\n"
                                                   "      command: \"touch /tmp/never\"\n")
    box.approve(orch)
    assert sentinel.exists()
    assert not os.path.exists("/tmp/never")
    assert run.status == "merged"


@pytest.mark.parametrize("path", [".adlc/config.yml", ".github/workflows/ci.yml", "infra/m.tf",
                                  "deploy.sh"])
def test_deploy_surface(tmp_path, path):
    sentinel = tmp_path / "deployed"
    box = eh.Sandbox(tmp_path, deployable="true",
                     config=DEPLOY.replace("touch %s", "./deploy.sh") % ())
    box.req(files={path: "changed\n"})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    plan = run.ledger().read()["plan"]
    assert plan["deployPlan"] is None
    assert plan["deploySkipped"] == "PR modifies deploy surface"
    assert "deploy skipped: PR modifies deploy surface" in box.out.getvalue()
    assert plan["changesGate"]
    token, gate = box.tokens(REQ)
    box.approve(orch, ack=True)
    assert not sentinel.exists()
    assert run.status == "merged"


def test_deployable_refs(tmp_path):
    sentinel = tmp_path / "deployed"
    spec = ".adlc/specs/REQ-901-thing/requirement.md"
    box = eh.Sandbox(tmp_path, deployable="false", config=DEPLOY % sentinel)
    text = (box.repo / spec).read_text().replace("deployable: false", "deployable: true")
    box.req(files={spec: text})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    plan = run.ledger().read()["plan"]
    assert plan["deployPlan"] is None and "differs" in plan["deploySkipped"]
    box.approve(orch)
    assert not sentinel.exists()


def test_deployable_absent_at_a_ref(tmp_path):
    box = eh.Sandbox(tmp_path, deployable="true", config=DEPLOY % "/tmp/x")
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    os.unlink(str(box.repo / box.spec_dirs[REQ] / "requirement.md"))
    assert eg.deploy_plan(orch.box(run), str(box.repo), "main", "HEAD~0",
                          "no/such/spec.md", [])[0] is None
    assert run.ledger().read()["plan"]["deployPlan"]["target"] == "prod"


def test_planted_partials_and_gate_change(tmp_path):
    sentinel = tmp_path / "planted"
    box = eh.Sandbox(tmp_path)
    body = "#!/bin/sh\ntouch %s\n" % sentinel
    box.req(files={".adlc/partials/forge.sh": body, ".adlc/tools/adlc/forge_config.py": body})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    plan = run.ledger().read()["plan"]
    assert any("changes the gate" in line for line in plan["changesGate"])
    assert "changes the gate" in box.out.getvalue()
    token, gate = box.tokens(REQ)
    assert gate
    with pytest.raises(se.Refused, match="--ack-gate-change"):
        orch.approve(REQ, token, decided_by="op")
    with pytest.raises(se.Refused, match="bound to that line"):
        orch.approve(REQ, token, "0" * 32, ack=True, decided_by="op")
    with pytest.raises(se.Refused, match="bound to that line"):
        orch.approve(REQ, token, token, ack=True, decided_by="op")
    box.approve(orch, ack=True)
    assert run.status == "merged"
    assert run.ledger().read()["decision"]["ackGateChange"] is True
    assert not sentinel.exists()
    assert all(r["argv"][0] != ".adlc/partials/forge.sh" for r in box.log(run))


def test_planted_hook_stops_everything(tmp_path):
    sentinel = tmp_path / "sentinel"
    box = eh.Sandbox(tmp_path)
    box.req(plant_late={os.path.join(str(box.repo), ".git", "hooks", "pre-push"):
                        "#!/bin/sh\ntouch %s\n" % sentinel})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    assert "hooks/pre-push" in "\n".join(se.violations_of(run))
    assert not sentinel.exists() and merged_count(box) == 0


def test_planted_config_after_the_halt(tmp_path):
    sentinel = tmp_path / "sentinel"
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    with open(str(box.repo / ".git" / "config"), "a") as fh:
        fh.write('[core]\n\tsshCommand = touch %s\n' % sentinel)
    box.approve(orch)
    assert run.status == "blocked" and merged_count(box) == 0
    assert "common gitdir checksum mismatch" in "\n".join(se.violations_of(run))
    assert not sentinel.exists()


def test_install_edit_after_launch_stops_the_run(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    toolbox = orch.box(run)
    toolbox.manifest["files"]["partials/forge.sh"] = "0" * 64
    box.approve(orch)
    assert run.status == "blocked" and merged_count(box) == 0
    assert "sha256 manifest mismatch" in "\n".join(se.violations_of(run))


def test_git_commands_carry_the_neutral_env(tmp_path):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    rows = [r for r in box.log(run) if r["kind"] in ("git", "partial")]
    assert rows
    for row in rows:
        assert row["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
        assert row["env"]["GIT_CONFIG_GLOBAL"] == run.file("gitconfig")
    for row in rows:
        if row["kind"] == "git" and row["argv"][3] in ("push", "fetch"):
            assert "origin" in row["argv"] and any(":" in a for a in row["argv"])


def test_lite_lane_rebase_reruns_the_lane_check(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"), lane="lite")
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"})
    orch = box.go(shared=True)
    box.approve(orch, REQ)
    second = orch.runs["REQ-902"]
    real = eg.trial_merge
    seen = []

    def trial(toolbox, repo, path, ib):
        seen.append(path)
        return (1, ["b.txt"]) if len(seen) == 1 else real(toolbox, repo, path, ib)
    monkeypatch.setattr(eg, "trial_merge", trial)
    ran = []
    monkeypatch.setattr(eg, "lane_check_rerun", lambda *a: (ran.append(a), (1, "lane_check=escalate"))[1])
    box.approve(orch, "REQ-902")
    assert ran and second.status == "blocked"
    assert "lane check failed" in json.dumps(second.read_primary_state()["blockers"])


def test_unblock_pass_relaunches_a_held_req(tmp_path):
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"}, status="blocked", claim="blocked",
            blockers=[{"blockedBy": "REQ-901", "conflictFiles": ["a.txt"], "holdState": "held",
                       "rebaseAttempts": 0}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "blockers": None, "files": {"c.txt": "902\n"}})
    orch = box.go(shared=True)
    assert orch.runs["REQ-902"].status == "blocked"
    box.approve(orch, REQ)
    box.wait(orch)
    assert orch.runs["REQ-902"].status == "awaiting_approval"
    assert orch.runs["REQ-902"].doc["launches"] == 2


def test_deploy_failure_is_recorded_and_the_merge_stands(tmp_path):
    box = eh.Sandbox(tmp_path, deployable="true", config=DEPLOY.replace("touch %s", "exit 3") % ())
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    assert run.status == "merged"
    closing = run.read_primary_state()["closeOut"]
    assert closing["status"] == "failed" and "deploy prod failed" in closing["reason"]


def test_abort_of_a_close_out(tmp_path, monkeypatch):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.scenarios[REQ]["closeout"] = {"sleep": 30}
    box.write_scenario()
    worker = se.threading.Thread(target=lambda: box.approve(orch))
    worker.start()
    for _ in range(600):
        if se.pid_alive(run.exec.get("closeOutPid")):
            break
        se.time.sleep(0.05)
    orch.abort(REQ, by="operator")
    worker.join(30)
    assert not worker.is_alive()
    assert run.read_primary_state()["closeOut"]["status"] == "failed"
    assert run.status == "merged"


def test_ledger_tampered_between_approve_and_merge(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch, drain=False)
    with open(run.file(el.LEDGER), "a") as fh:
        fh.write(" ")
    orch.drain()
    assert run.status == "blocked" and merged_count(box) == 0


def test_es_kv():
    assert es.kv("a=1\nb=c=d\nnoise") == {"a": "1", "b": "c=d"}
