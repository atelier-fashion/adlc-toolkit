"""Approval, the one-way moves and the close-out (REQ-659)."""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_gates as eg  # noqa: E402
import exec_helpers as eh  # noqa: E402
import exec_ledger as el  # noqa: E402
import exec_prompt as ep  # noqa: E402
import exec_safety as es  # noqa: E402
import exec_trust as et  # noqa: E402
import sprint_exec as se  # noqa: E402

REQ = "REQ-901"


@pytest.fixture
def box(tmp_path):
    return eh.Sandbox(tmp_path)


def merged_count(box):
    return len(box.calls("pr_merge"))


def contains(argv, part):
    """Whether ``part`` is a contiguous run of ``argv`` (an empty one always is)."""
    return any(argv[i:i + len(part)] == part for i in range(len(argv) - len(part) + 1))


@pytest.mark.parametrize("harness", eh.EXEC_ADAPTERS)
def test_approval_protocol_per_adapter(tmp_path, harness):
    """REQ-659's approval protocol against each exec-capable adapter as shipped, read with its
    committed result file, and the fake in that adapter's profile (REQ-662 BR-12, AC-12):
    launch from the adapter's template, `awaiting_approval`, approve, the orchestrator's pinned
    merge through the forge mock, the close-out's resume from the resume template with the
    session id the launch printed, done; and the reject path, which merges nothing and leaves
    the working copy. Trust is granted and revoked on both paths, and the operator's user
    config and user policy folder end as they began."""
    (tmp_path / "approve").mkdir()
    box = eh.adapter_sandbox(tmp_path / "approve", harness)
    adapter = box.adapter()
    before = box.user_files()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "awaiting_approval" and run.exec["exitClass"] == "ok"
    [launch] = box.argvs()
    assert launch[:len(adapter.template("launch"))] == ea.substitute(adapter.template("launch"), {
        "worktree": run.wc, "last_message": run.last_message("stdout.json"),
        "branch": run.doc["branch"]})
    assert eh.read_text(box.home / "prompt-REQ-901.txt") == eh.read_text(run.file("prompt.txt"))
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
    assert not run.doc.get("trustGrants") and box.user_files() == before
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
    resume = [i for i, (k, a) in enumerate(names) if k == "exec_launch"][1]
    assert verify < trial < merge < resume
    trial_cwd = [r for r in log if r["kind"] == "git" and "worktree" in r["argv"]
                 and "--detach" in r["argv"]]
    assert trial_cwd and all(run.path in " ".join(r["argv"]) for r in trial_cwd)
    close = os.path.join(os.path.realpath(str(box.repo)), ".worktrees", "REQ-901-close-out")
    _launch, resumed = box.argvs()
    assert resumed[:len(adapter.template("resume"))] == ea.substitute(
        adapter.template("resume"), {"session_id": "session-REQ-901", "worktree": close,
                                     "last_message": run.last_message("close-out.json"),
                                     "branch": "chore/REQ-901-close-out"})
    # The engine's settings file, and the isolation tokens that make it the only one read
    # (BUG-260), on the resume as on the launch: none on an adapter that declares none.
    isolation = ea.substitute(adapter.block.get("config_isolation", []),
                              {"settings": run.file("settings.json")})
    assert contains(launch, isolation) and contains(resumed, isolation)
    assert "hooks" not in json.load(open(run.file("settings.json")))
    assert run.exec["closeOutPid"]
    prompt = eh.read_text(box.home / "closeout-prompt-REQ-901.txt")
    assert prompt == eh.read_text(run.file("close-out-prompt.txt"))
    assert "WORKTREE PATH (mandatory): %s" % close in prompt
    assert "chore/REQ-901-close-out" in prompt
    merge_commit = run.doc["recordedMerges"][0]
    assert merge_commit in prompt
    assert not ep.scan(prompt, "close-out")
    assert "merged" in box.out.getvalue()
    assert "exec" in open(box.environ["ADLC_RUN_OUTCOMES_LOG"]).read()
    assert "1" == eh.git(box.repo, "branch", "--list", "feat/REQ-901-thing").strip() or \
        eh.git(box.repo, "branch", "--list", "feat/REQ-901-thing").strip() == ""

    (tmp_path / "reject").mkdir()
    box = eh.adapter_sandbox(tmp_path / "reject", harness)
    before = box.user_files()
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
    assert run.exec["trustGrantedAt"] and run.exec["trustRevokedAt"]
    assert not run.doc.get("trustGrants") and box.user_files() == before
    assert len(box.argvs()) == 1
    with pytest.raises(se.Refused, match="not awaiting_approval"):
        orch.reject(REQ, "again", decided_by="operator")


def test_channel_is_recorded(box):
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch, drain=False, channel="skill")
    decision = run.ledger().read()["decision"]
    assert decision["channel"] == "skill" and decision["decidedBy"] == "operator"
    assert run.read_primary_state()["approval"]["channel"] == "skill"


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


def test_an_argv_refused_at_relaunch_ends_the_run(tmp_path, monkeypatch):
    """REQ-662 BR-16, BR-5: a relaunch whose argv the closed-world check refuses after its trust
    is granted ends the run failed (setup-error) with the refusal in its notes and its trust
    revoked, and the answer is refused with it. Nothing is launched. On claude (`none`) the
    revoke is recorded; on a `user-config-entry` adapter the user config is byte-identical."""
    for name in ("claude", "trust"):
        (tmp_path / name).mkdir()
        if name == "claude":
            box = eh.Sandbox(tmp_path / name)
        else:
            box = eh.trust_sandbox(tmp_path / name, monkeypatch)
        box.req(status="blocked", claim="blocked", add=["src"],
                blockers=[{"reason": "reflector-questions", "question": "which?"}],
                after_answer={"status": "awaiting_approval", "claim": "awaiting_approval"})
        orch = box.go(shared=True)
        run = orch.runs[REQ]
        assert run.status == "blocked", name
        run.doc["flags"] = ["--not-an-operator-flag"]
        with pytest.raises(se.Refused, match="--not-an-operator-flag is not in harness"):
            orch.answer(REQ, "the second option")
        assert run.status == "failed" and not orch.children, name
        assert len((box.home / "argv-REQ-901.json").read_text().splitlines()) == 1
        assert "operator_flags" in json.dumps(run.read_primary_state()["notes"])
        assert run.exec["trustRevokedAt"], name
        if name == "trust":
            assert run.doc["trustGrants"] == {}
            assert len(eh.events(box, run, "trust_granted")) == 2
            assert [e["status"] for e in eh.events(box, run, "trust_revoked")] == [
                et.REVOKED] * 2
            assert eh.read_text(box.user_config) == eh.USER_CONFIG


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


@pytest.mark.parametrize("harness", eh.EXEC_ADAPTERS)
def test_no_session_means_no_close_out(tmp_path, harness):
    box = eh.adapter_sandbox(tmp_path, harness)
    box.req(no_session=True)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    state = run.read_primary_state()
    assert state["closeOut"]["reason"] == "no session id" and state["repos"]["widgets"]["merged"]
    assert run.status == "merged" and len(box.argvs()) == 1


def test_config_isolation(tmp_path):
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    # The flags vanish after launch (a harness upgraded mid-run): preflight passed, and the
    # close-out still checks for itself.
    box.write_scenario(help="--setting-sources <s>\n--settings <f>\n")
    box.approve(orch)
    state = run.read_primary_state()
    assert state["closeOut"] == {"status": "failed", "at": state["closeOut"]["at"],
                                 "reason": "harness config isolation unavailable"}
    assert run.status == "merged"
    assert not (box.home / "closeout-argv-REQ-901.json").exists()



def test_close_out_scopes_file_tools(tmp_path):
    """BUG-265: the close-out writes its own working copy and, through --add-dir, the primary
    repo's spec dir (close-out rule 3), and nothing else."""
    box = eh.Sandbox(tmp_path)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch)
    argv = json.loads(open(str(box.home / ("closeout-argv-%s.json" % REQ))).read())
    allow = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
    added = argv[argv.index("--add-dir") + 1]
    wc = run.doc["closeOutWorkingCopy"]
    assert sorted(a for a in allow if a.startswith("Edit(")) == sorted(
        ["Edit(/%s/**)" % wc, "Edit(/%s/**)" % added])
    for bare in ("Read", "Write", "Edit", "Glob", "Grep"):
        assert bare not in allow


def test_close_out_gets_its_own_trust_grant(tmp_path, monkeypatch):
    """REQ-662 BR-5, AC-5: after a successful run the close-out's working copy is granted before
    its launch and revoked after, apart from the run's own grant, which went at the halt. Once
    merged the user config is byte-identical and `exec.trustGrantedAt` and `trustRevokedAt` are
    set. A close-out that stops between its grant and its revoke is cleaned by cleanup."""
    a = tmp_path / "a"
    a.mkdir()
    box = eh.trust_sandbox(a, monkeypatch)
    config = box.user_config
    box.req(add=["src"], saw=[config], closeout={"saw": [config], "add": [".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "awaiting_approval" and eh.read_text(config) == eh.USER_CONFIG
    assert box.approve(orch) == "approved"
    assert run.status == "merged" and run.read_primary_state()["closeOut"]["status"] == "ok"
    paths = [os.path.realpath(p) for p in (run.wc, run.doc["closeOutWorkingCopy"])]
    saw = [json.loads(ln)["saw"][config]
           for ln in (box.home / "saw-REQ-901.jsonl").read_text().splitlines()]
    assert saw == [eh.USER_CONFIG + et.trust_block(p) for p in paths]
    assert [e["path"] for e in eh.events(box, run, "trust_granted")] == paths
    assert [(e["path"], e["status"]) for e in eh.events(box, run, "trust_revoked")] == [
        (p, et.REVOKED) for p in paths]
    assert run.exec["trustGrantedAt"] and run.exec["trustRevokedAt"]
    assert run.doc["trustGrants"] == {} and eh.read_text(config) == eh.USER_CONFIG

    b = tmp_path / "b"
    b.mkdir()
    box = eh.trust_sandbox(b, monkeypatch)
    box.req(add=["src"])
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    argv = orch._argv

    def refused_at_resume(*args, **kw):
        if kw.get("resume"):
            raise ea.ExecRefused("closed world: the resume argv is refused")
        return argv(*args, **kw)

    monkeypatch.setattr(orch, "_argv", refused_at_resume)
    assert box.approve(orch) == "approved"
    assert run.status == "merged"
    assert "the resume argv is refused" in run.read_primary_state()["closeOut"]["reason"]
    close = os.path.realpath(run.doc["closeOutWorkingCopy"])
    assert [(e["path"], e["status"]) for e in eh.events(box, run, "trust_revoked")][-1] == (
        close, et.REVOKED)
    assert run.doc["trustGrants"] == {} and eh.read_text(box.user_config) == eh.USER_CONFIG

def without(argv, part):
    """``argv`` with the first contiguous run of ``part`` taken out (none for an empty one)."""
    for i in range(len(argv) - len(part) + 1):
        if part and argv[i:i + len(part)] == part:
            return argv[:i] + argv[i + len(part):]
    return list(argv)


@pytest.mark.parametrize("harness", eh.EXEC_ADAPTERS)
def test_close_out_resumes_with_the_same_rules(tmp_path, harness):
    """REQ-662 BR-7, AC-8, ADR-7: after approve with model work remaining, the engine makes the
    close-out working copy by the adapter's declared strategy (a linked worktree on
    `chore/<REQ>-close-out` from the integration branch), grants trust for it before the
    resume and revokes it after, and launches the adapter's resume template there with the
    session id the launch printed, which the fake checks, and the launch's rules: the same deny
    tier and isolation, the allow tier moved to the close-out's working copy and branch, and
    any rule file and user policy file in place as the engine renders them, which the fake
    records. The close-out also writes the primary repo path's pipeline-state.json: through the
    spec directory the adapter adds with its add_dir_flag (Claude), and with none (Codex)
    through a copy in its own working copy that its prompt names and the engine carries back."""
    box = eh.adapter_sandbox(tmp_path, harness)
    adapter = box.adapter()
    before = box.user_files()
    seen = [p for p in (adapter.block.get("rule_file"), box.policy_file) if p]
    box.req(saw=seen, closeout={"saw": seen})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["closeOut"]["status"] == "ok" and state["completed"] is True
    root = os.path.realpath(str(box.repo))
    close, chore = os.path.join(root, ".worktrees", "REQ-901-close-out"), "chore/REQ-901-close-out"
    assert adapter.strategy == "worktree" and run.doc["closeOutWorkingCopy"] == close
    log = box.log(run)
    assert any(r["kind"] == "git" and contains(r["argv"], [
        "worktree", "add", "--no-track", "-b", chore, close, "refs/remotes/origin/main"])
        for r in log)
    rows = [(r["kind"], r["cwd"]) for r in log
            if r["kind"] in ("trust_granted", "exec_launch", "trust_revoked")]
    assert [cwd for kind, cwd in rows if kind == "exec_launch"] == [run.wc, close]
    assert [cwd for kind, cwd in rows if kind == "trust_granted"] == [run.wc, close]
    assert sorted(cwd for kind, cwd in rows if kind == "trust_revoked") == sorted([run.wc, close])
    assert rows.index(("trust_granted", close)) < rows.index(("exec_launch", close)) < \
        rows.index(("trust_revoked", close))
    assert not run.doc.get("trustGrants") and box.user_files() == before
    # The resume template, filled with the launch's session id, then the launch's rules.
    launch, resumed = box.argvs()
    first, again = len(adapter.template("launch")), len(adapter.template("resume"))
    assert resumed[:again] == ea.substitute(adapter.template("resume"), {
        "session_id": "session-REQ-901", "worktree": close, "branch": chore,
        "last_message": run.last_message("close-out.json")})
    added = os.path.join(root, box.spec_dirs[REQ])
    second = [adapter.block["add_dir_flag"], added] if adapter.can_add_dir else []
    assert contains(resumed[again:], second)
    assert any(added in t for t in resumed[again:]) is adapter.can_add_dir
    moved = [t.replace(run.wc, close).replace(run.doc["branch"], chore) for t in launch[first:]]
    assert [t for t in without(resumed[again:], second) if added not in t] == moved
    # The files the rules travel in, as each launch found them on starting.
    saws = [json.loads(ln) for ln in (box.home / "saw-REQ-901.jsonl").read_text().splitlines()
            ] if seen else []
    assert [s["cwd"] for s in saws] == ([run.wc, close] if seen else [])
    rendered = {}
    if seen:
        fresh, ours = eh.fresh_files(box, chore), eh.fresh_files(box, run.doc["branch"])
        rendered = {adapter.block["rule_file"]: (ours.rule_file, fresh.rule_file),
                    box.policy_file: (ours.user_policy_file, fresh.user_policy_file)}
    for path in seen:
        assert (saws[0]["saw"][path], saws[1]["saw"][path]) == rendered[path], path
    if box.policy_file:
        assert saws[1]["saw"][box.policy_file] == eh.read_text(box.policy_file)
    # Where the close-out wrote the primary repo path's state.
    prompt = eh.read_text(run.file("close-out-prompt.txt"))
    copy = os.path.join(close, box.spec_dirs[REQ], "pipeline-state.json")
    assert prompt.startswith(ep.STATE_FILE_NOTE % copy) is not adapter.can_add_dir
    assert prompt.startswith("WORKTREE PATH (mandatory): ") is adapter.can_add_dir
    assert eh.read_text(box.home / "closeout-state-REQ-901.txt") == (
        run.primary_state_path() if adapter.can_add_dir else copy)
    carried = eh.events(box, run, "close_out_state_carried")
    assert len(carried) == (0 if adapter.can_add_dir else 1)
    for detail in carried:
        assert detail["record"] is True and {"closeOut", "completed"} <= set(detail["taken"])


#: What a close-out session writes into its copy of the state on top of its terminal record:
#: the keys the engine owns, set by the model, and one of its own.
HOSTILE = {"status": "approved", "exec": {"exitClass": "denied", "pid": 1},
           "approval": {"decision": "rejected", "decidedBy": "the model", "action": "deploy"},
           "notes": ["from the close-out"]}


def test_a_carried_close_out_state_is_data(tmp_path):
    """REQ-662 ADR-7: on the shipped Codex block, which declares no add_dir_flag, the close-out's
    copy of the state is model-written data. A copy that also sets `status`, `exec` and
    `approval` changes none of them in the primary path's state, and its other keys are
    carried. A copy that is not one JSON object, is gone, does not parse, or is a link or a
    special file is no record: nothing is carried, the linked file's content included, and the
    close-out ends failed with the merge standing. A chore PR that commits the copy is out of
    bounds and needs review, never merged."""
    (tmp_path / "hostile").mkdir()
    box = eh.adapter_sandbox(tmp_path / "hostile", "codex")
    box.req(closeout={"state_extra": HOSTILE})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["status"] == "merged" and state["exec"] == run.public_exec()
    assert state["exec"]["exitClass"] == "ok"
    assert state["approval"]["decision"] == "approved"
    assert state["approval"]["decidedBy"] == "operator" and state["approval"]["action"] == "merge"
    assert state["closeOut"]["status"] == "ok" and state["completed"] is True
    assert state["notes"] == ["from the close-out"]
    [carried] = eh.events(box, run, "close_out_state_carried")
    assert carried["record"] is True and carried["ignored"] == ["approval", "exec", "status"]
    assert {"closeOut", "completed", "notes"} <= set(carried["taken"])
    assert merged_count(box) == 2

    (tmp_path / "list").mkdir()
    box = eh.adapter_sandbox(tmp_path / "list", "codex")
    box.req(closeout={"state_text": "[1, 2]\n"})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    before = run.read_primary_state()
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["closeOut"]["status"] == "failed" and state["repos"]["widgets"]["merged"]
    assert state["closeOut"]["reason"] == "the close-out wrote no terminal record"
    assert "completed" not in state or state["completed"] == before.get("completed")
    [carried] = eh.events(box, run, "close_out_state_carried")
    assert carried["record"] is False and "not one JSON object" in carried["why"]
    # The same read on a copy that is gone, does not parse, or is a link or a special file.
    secret = tmp_path / "list" / "elsewhere.json"
    secret.write_text('{"token": "not-a-real-token", "closeOut": {"status": "ok"}}\n')
    rel = os.path.join(box.spec_dirs[REQ], "pipeline-state.json")
    for name, make, why in (
            ("gone", lambda f: None, "not one JSON object"),
            ("cut", lambda f: f.write_text('{"closeOut": {"status": "o'), "not one JSON object"),
            ("link", lambda f: f.symlink_to(secret), "is a symlink"),
            ("hardlink", lambda f: os.link(str(secret), str(f)), "is a hardlink"),
            ("fifo", lambda f: os.mkfifo(str(f)), "not a regular file"),
            ("dir", lambda f: f.mkdir(), "is a directory")):
        wc = tmp_path / "list" / name
        (wc / box.spec_dirs[REQ]).mkdir(parents=True)
        make(wc / rel)
        before = run.read_primary_state()
        orch._carry_close_out(run, str(wc))
        assert run.read_primary_state() == before, name
        detail = eh.events(box, run, "close_out_state_carried")[-1]
        assert detail["record"] is False and why in detail["why"], (name, detail)
    assert "not-a-real-token" not in eh.read_text(run.primary_state_path())

    (tmp_path / "committed").mkdir()
    box = eh.adapter_sandbox(tmp_path / "committed", "codex")
    box.req(closeout={"add": ["-f", rel, ".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["closeOut"]["status"] == "needs-review"
    assert "A %s" % rel in state["closeOut"]["reason"]
    assert merged_count(box) == 1


def test_a_refused_close_out_argv_revokes_its_trust(tmp_path, monkeypatch):
    """REQ-662 BR-5, BR-16, ADR-7: on the shipped Codex block, a resume argv the closed-world
    check refuses fails the close-out with the refusal, the merge standing, and the close-out's
    own trust grant is revoked there, before the cleanup runs; nothing is resumed and the user
    config ends as it began."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    before = box.user_files()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    argv = orch._argv

    def refused_at_resume(*args, **kw):
        if kw.get("resume"):
            raise ea.ExecRefused("closed world: the resume argv is refused")
        return argv(*args, **kw)
    monkeypatch.setattr(orch, "_argv", refused_at_resume)
    held = []
    cleanup = orch.cleanup

    def watched(a_run):
        held.append(sorted(a_run.doc.get("trustGrants") or {}))
        return cleanup(a_run)
    monkeypatch.setattr(orch, "cleanup", watched)
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["closeOut"]["status"] == "failed" and state["repos"]["widgets"]["merged"]
    assert state["closeOut"]["reason"] == "closed world: the resume argv is refused"
    assert held == [[]]
    close = os.path.realpath(run.doc["closeOutWorkingCopy"])
    assert [(e["path"], e["status"]) for e in eh.events(box, run, "trust_revoked")][-1] == (
        close, et.REVOKED)
    assert len(box.argvs()) == 1 and box.user_files() == before


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


#: Each way a PR reaches an exec-rendered path or a config surface (REQ-662 BR-17): the shell
#: commands the fake runs in its working copy before its commit, which defeat the engine's
#: best-effort hiding, and the one ``[status, path]`` hit the halt-time gate must find.
EXEC_PATH_CASES = {
    "REQ-901": (["git add -f %s" % eh.FILE_RULE], ["A", eh.FILE_RULE]),
    "REQ-902": (["git update-index --no-skip-worktree %s" % eh.FILE_CONFIG,
                 "git add %s" % eh.FILE_CONFIG], ["M", eh.FILE_CONFIG]),
    "REQ-903": (["git add --sparse --renormalize %s" % eh.FILE_CONFIG], ["M", eh.FILE_CONFIG]),
    "REQ-904": (["git update-index --force-remove %s" % eh.FILE_HOOKS], ["D", eh.FILE_HOOKS]),
    "REQ-905": (["git mv README.md .fake-exec-file/README.md"],
                ["A", ".fake-exec-file/README.md"]),
    "REQ-906": (["git update-index --no-skip-worktree %s" % eh.FILE_CONFIG, "mkdir -p docs",
                 "git mv %s docs/config.toml" % eh.FILE_CONFIG], ["D", eh.FILE_CONFIG]),
    "REQ-907": (["git update-index --add --cacheinfo 100644,$(printf 'x\\n' | git hash-object "
                 "-w --stdin),.FAKE-EXEC-FILE/Config.TOML"], ["A", ".FAKE-EXEC-FILE/Config.TOML"]),
    "REQ-908": (["mkdir -p .fake-exec-file/prompts", "printf 'new\\n' > .fake-exec-file/prompts/"
                 "new.md", "git add .fake-exec-file/prompts/new.md"],
                ["A", ".fake-exec-file/prompts/new.md"]),
}


def test_exec_path_touched_refuses_approve(tmp_path, monkeypatch):
    """REQ-662 BR-17, AC-20: a PR that adds (past the excludes file), modifies (through
    `--no-skip-worktree` or `add --sparse`), deletes, renames into or out of an exec-rendered
    path or the config-surface directory, or adds a case variant of one, puts that path in the
    plan's execPathTouched at the halt, one `exec_path_touched` event and a dashboard line;
    approve refuses it with --ack-gate-change and its gate token or without, and the token
    stays unspent. REQ-659's "changes the gate" list names each at the halt (AC-18). The PR
    that touches none, committed with `git add -A` over the hidden renders, leaves the list
    empty and merges (the must-not-refuse case); a plan without the gate result is refused and
    re-halted, and the restore runs before the merge."""
    monkeypatch.setattr(se, "MAX_CONCURRENT", 1)        # one fake at a time on the repo
    benign = "REQ-909"
    box = eh.file_sandbox(tmp_path, monkeypatch, reqs=tuple(sorted(EXEC_PATH_CASES)) + (benign,))
    eh.commit_on_main(box, {eh.FILE_CONFIG: 'model = "operator"\n',
                            eh.FILE_HOOKS: '{"hooks": {}}\n'})
    for req, (commands, _hit) in EXEC_PATH_CASES.items():
        box.req(req, add=["src"], commands=commands)
    box.req(benign, closeout={"add": [".adlc"]})
    before = eh.git(box.repo, "status", "--porcelain", "-uall")
    orch = box.go(shared=True)
    for req, (_commands, (status, path)) in sorted(EXEC_PATH_CASES.items()):
        run = orch.runs[req]
        assert run.status == "awaiting_approval", req
        plan = run.ledger().read()["plan"]
        assert plan[eg.EXEC_PATH_KEY] == [path], (req, plan["changedPaths"])
        assert [(e["status"], e["path"]) for e in eh.events(box, run, "exec_path_touched")] == [
            (status, path)], req
        assert "changes the gate: touches a config surface: %s" % path in plan["changesGate"]
        assert "exec path touched: %s; approve will refuse" % path in box.out.getvalue()
        token, gate = box.tokens(req)
        assert token and gate, req
        for ack, gate_token in ((True, gate), (False, None), (True, gate)):
            with pytest.raises(se.Refused, match="--ack-gate-change does not cover it") as caught:
                orch.approve(req, token, gate_token, ack=ack, decided_by="operator")
            assert path in str(caught.value) and "BR-17" in str(caught.value)
        assert run.status == "awaiting_approval" and req in orch.tokens
        assert run.ledger().read()["decision"] is None
    assert merged_count(box) == 0
    run = orch.runs[benign]
    plan = run.ledger().read()["plan"]
    assert plan[eg.EXEC_PATH_KEY] == [] and plan["changesGate"] == []
    assert plan["changedPaths"] == ["src/%s.txt" % benign]
    # A plan an engine without the gate wrote: refused, and re-halted with the gate's result.
    stale = dict(plan)
    del stale[eg.EXEC_PATH_KEY]
    run.ledger().update_plan(stale)
    run.save()
    token, _gate = box.tokens(benign)
    with pytest.raises(se.Refused, match="records no exec-path gate result.*re-halted"):
        orch.approve(benign, token, decided_by="operator")
    assert run.ledger().read()["plan"][eg.EXEC_PATH_KEY] == []
    assert box.tokens(benign)[0] != token
    assert box.approve(orch, benign) == "approved"
    assert run.status == "merged" and merged_count(box) == 2
    names = [(r["kind"], " ".join(r["argv"])) for r in box.log(run)]
    restored = next(i for i, (kind, _a) in enumerate(names) if kind == "exec_paths_restored")
    merge = next(i for i, (_k, argv) in enumerate(names) if "adlc_forge_pr_merge" in argv)
    assert restored < merge
    assert not os.path.exists(run.wc)
    assert eh.git(box.repo, "status", "--porcelain", "-uall") == before


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


# ---- REQ-662 BR-11 / BR-18 -------------------------------------------------------------------
#: What the fake answers to `--version` once "upgraded": not the adapter's declared version.
UPGRADED = "0.0.0 (an upgraded binary)"


def test_allow_unverified_is_per_invocation(tmp_path, monkeypatch):
    """REQ-662 AC-21: --allow-unverified covers the launches of the invocation that received
    it. The ledger names that invocation; approve re-checks and refuses before the forge sees a
    merge, in that invocation and in a later one; a later launch is refused. The adapter is a
    `verification: probes` block; the fake reports a version other than the one it declares."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    box.write_scenario(version=UPGRADED)
    first = box.go(shared=True, allow_unverified=True)
    run = first.runs[REQ]
    assert run.status == "awaiting_approval"
    [entry] = run.ledger().read()["plan"]["allowUnverified"]
    assert entry["invocation"] == first.invocation and entry["invocation"]["pid"] == os.getpid()
    assert entry["launch"] == "launch" and entry["unverified"] == ["installed-version"]
    assert ("allowUnverified: the launch by invocation %s" % first.invocation["id"]) in \
        "\n".join(se.render_row(run))
    token, _ = box.tokens(REQ)
    with pytest.raises(se.Refused, match="approve is refused.*installed-version"):
        first.approve(REQ, token, decided_by="operator")
    assert REQ in first.tokens and run.ledger().read()["decision"] is None
    assert run.status == "awaiting_approval" and merged_count(box) == 0
    # A later invocation (`resume`) received no flag; the ledger's record is not one.
    later = box.orch()
    later.resume()
    assert later.allow_unverified is False and later.invocation["id"] != first.invocation["id"]
    with pytest.raises(se.Refused, match="approve is refused.*installed-version"):
        box.approve(later, drain=False)
    assert merged_count(box) == 0 and not box.calls("pr_merge")
    with pytest.raises(se.Refused, match="launch is refused.*installed-version"):
        box.orch().preflight([REQ], harness=box.harness, shared=True)
    # The verdict was the only thing in the way: with the declared version back, it merges.
    box.write_scenario(version=later.adapter(later.runs[REQ]).block["harness_version"])
    assert box.approve(later) == "approved"
    assert later.runs[REQ].status == "merged"


def test_allow_unverified_on_answer_is_the_answering_invocations(tmp_path, monkeypatch):
    """REQ-662 BR-18, AC-15, AC-21: the live supervisor that `run --allow-unverified` started
    does not lend its flag to a later `answer` it serves: without the flag the relaunch is
    refused naming the unverified adapter, and nothing is launched; `answer --allow-unverified`
    relaunches, for that relaunch alone, and the ledger names the answering invocation beside
    the launching one."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    box.req(status="blocked", claim="blocked",
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "files": {"src/two.txt": "two\n"}})
    box.write_scenario(version=UPGRADED)
    live = box.go(shared=True, allow_unverified=True)
    run = live.runs[REQ]
    assert run.status == "blocked" and live.allow_unverified is True

    def served(_run, request):
        # What the live supervisor's socket answers: its own dispatch (`serve_once`).
        try:
            return live.dispatch(request, None)
        except se.Refused as exc:
            return {"ok": False, "error": str(exc)}

    monkeypatch.setattr(se, "client_call", served)
    answering = box.orch()
    plain = se._parser().parse_args(["answer", REQ, "the second option"])
    with pytest.raises(se.Refused, match="harness fake-exec-file is unverified, so the "
                                         "relaunch is refused.*installed-version"):
        se._client(answering, plain)
    assert run.status == "blocked" and not live.children and len(box.launches()) == 1
    assert [e["launch"] for e in run.doc["allowUnverified"]] == ["launch"]
    flagged = se._parser().parse_args(["answer", REQ, "the second option",
                                       "--allow-unverified"])
    assert se._client(answering, flagged) == 0
    box.wait(live)
    assert run.status == "awaiting_approval" and len(box.launches()) == 2
    entries = run.ledger().read()["plan"]["allowUnverified"]
    assert [(e["launch"], e["invocation"]["id"]) for e in entries] == [
        ("launch", live.invocation["id"]), ("relaunch", answering.invocation["id"])]
    assert entries[1]["invocation"]["pid"] == os.getpid()
    assert ("the relaunch by invocation %s" % answering.invocation["id"]) in \
        "\n".join(se.render_row(run))


def test_version_mismatch_refused_at_launch_relaunch_and_close_out(tmp_path, monkeypatch):
    """REQ-662 AC-17: on a `verification: probes` block the binary's version is compared at the
    launch, before a relaunch and at the close-out (the session resume); without
    --allow-unverified each is refused."""
    for name in ("launch", "relaunch", "close-out"):
        (tmp_path / name).mkdir()
    box = eh.probes_sandbox(tmp_path / "launch", monkeypatch)
    box.write_scenario(version=UPGRADED)
    with pytest.raises(se.Refused, match="launch is refused.*installed-version"):
        box.start(shared=True)
    assert not box.launches()

    box = eh.probes_sandbox(tmp_path / "relaunch", monkeypatch)
    box.req(status="blocked", claim="blocked",
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval"})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    box.write_scenario(version=UPGRADED)
    with pytest.raises(se.Refused, match="relaunch is refused.*installed-version"):
        orch.answer(REQ, "the second option")
    assert run.status == "blocked" and not orch.children and len(box.launches()) == 1

    box = eh.probes_sandbox(tmp_path / "close-out", monkeypatch)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch, drain=False)
    box.write_scenario(version=UPGRADED)
    orch.drain()
    closing = run.read_primary_state()["closeOut"]
    assert closing["status"] == "failed", closing
    assert "close-out is refused" in closing["reason"] and "installed-version" in \
        closing["reason"]
    assert run.status == "merged" and merged_count(box) == 1
    assert [launch["opts"]["resume"] for launch in box.launches()] == [False]
