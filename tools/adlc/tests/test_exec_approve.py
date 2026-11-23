"""Approval, the one-way moves and the close-out (REQ-659)."""

import json
import os
import signal
import subprocess
import sys
import threading
import time

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


def _protocol_fake(box, adapter):
    """Script the fake for the per-adapter protocol, from the adapter's data, and return its
    ``exec.rule_file`` (None when it declares none). The sandbox holds a user config exactly
    when the block's grant writes one; the fake then trusts the repository itself, as `codex
    exec` does, unless an entry covers its launch, and records the rule file it starts with."""
    assert bool(box.user_config) == (adapter.trust_grant not in et.NO_FILE)
    rule = adapter.block.get("rule_file")
    script = {"saw": [rule]} if rule else {}
    if box.user_config:
        script["trust_itself"] = box.user_config
    box.req(**script)
    return rule


def _seen_rule_files(box, rule):
    """The rule-file text the fake found at each launch, the close-out's included."""
    path = box.home / ("saw-%s.jsonl" % REQ)
    if not rule or not path.exists():
        return []
    seen = [json.loads(line)["saw"].get(rule) for line in path.read_text().splitlines()]
    return [text for text in seen if text]


@pytest.mark.parametrize("harness", eh.EXEC_ADAPTERS)
def test_approval_protocol_per_adapter(tmp_path, harness):
    """REQ-659's approval protocol against each exec-capable adapter as shipped, read with its
    committed result file, and the fake in that adapter's profile (REQ-662 BR-12, AC-12):
    launch from the adapter's template, `awaiting_approval`, approve, the orchestrator's pinned
    merge through the forge mock, the close-out's resume from the resume template with the
    session id the launch printed, done; and the reject path, which merges nothing and leaves
    the working copy. Trust is granted and revoked on both paths, and the operator's user
    config and user policy folder end as they began. Where the block's grant writes the user
    config, the fake writes its own trust entry there as `codex exec` does at a launch no entry
    covers, so the user config ending byte-identical shows the grant covered the launch. Where
    the block declares a rule file, the fake records the rendered one it started with."""
    (tmp_path / "approve").mkdir()
    box = eh.adapter_sandbox(tmp_path / "approve", harness)
    adapter = box.adapter()
    rule = _protocol_fake(box, adapter)
    before = box.user_files()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "awaiting_approval" and run.exec["exitClass"] == "ok"
    assert bool(_seen_rule_files(box, rule)) == bool(rule)
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
    # BUG-287: the test harness opens both PRs as drafts, as a session does, and a forge
    # refuses to merge a draft. The engine flips each to ready just before its merge.
    ops = [(r["op"], r["argv"][0]) for r in box.calls() if r["op"] in ("pr_ready", "pr_merge")]
    for i, (op, ref) in enumerate(ops):
        if op == "pr_merge":
            assert i > 0 and ops[i - 1] == ("pr_ready", ref), ops
    assert [r["argv"][0] for r in box.log(run) if r["kind"] == "pr_ready"] \
        == [m["argv"][0] for m in merges]
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
    rule = _protocol_fake(box, box.adapter())
    before = box.user_files()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert bool(_seen_rule_files(box, rule)) == bool(rule)
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
    # The recorded harness, still alive: this process, started when the record says.
    run.exec.update({"pid": os.getpid(), "pidStart": se.process_start(os.getpid())})
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


#: A start time no live process has: a recorded pid the OS has since given another process.
NOT_ITS_START = "Thu Jan  1 00:00:00 1970"


def test_a_pid_the_os_gave_another_process_is_not_the_harness(box):
    """REQ-662 BR-18: a recorded harness pid is the harness only while the process holding it
    started when the engine recorded (`pidStart`, `closeOutPidStart`), whatever the run's
    status. A pid the OS has since given an unrelated live process refuses nothing at
    `approve`, fails no caller guard for a caller that descends from it, and `abort` never
    signals it. A harness that really is still alive is still refused at `approve` and at the
    caller guard, and `abort` still kills it."""
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    token, _ = box.tokens(REQ)
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    harness = subprocess.Popen(sleeper, start_new_session=True)
    other = subprocess.Popen(sleeper, start_new_session=True)
    try:
        started = eh.until(lambda: se.process_start(harness.pid), what="the harness to start")
        eh.until(lambda: se.process_start(other.pid), what="the other process to start")
        run.exec.update({"pid": harness.pid, "pidStart": started})
        with pytest.raises(se.Refused, match="still alive"):
            orch.approve(REQ, token, decided_by="op")
        with pytest.raises(se.Refused, match="Rule B"):
            orch.approve(REQ, token, decided_by="op", caller_pid=harness.pid)
        run.exec.update({"pid": other.pid, "pidStart": NOT_ITS_START, "closeOutPid": other.pid,
                         "closeOutPidStart": NOT_ITS_START})
        with pytest.raises(se.Refused, match="no live process"):
            orch.abort(REQ, by="operator")
        assert other.poll() is None and run.status == "awaiting_approval"
        assert orch.approve(REQ, token, decided_by="op", caller_pid=other.pid) == "approved"
        assert other.poll() is None
        run.exec.update({"pid": harness.pid, "pidStart": started, "closeOutPid": None,
                         "closeOutPidStart": None})
        orch.abort(REQ, by="operator")
        eh.until(lambda: harness.poll() is not None, timeout=10, what="the harness to be killed")
        assert run.status == "failed" and run.exec["abortedBy"] == "operator"
        assert other.poll() is None
    finally:
        for proc in (harness, other):
            if proc.poll() is None:
                proc.kill()
            proc.wait()


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
#: The run-outcome keys the primary path's copy holds before the close-out (REQ-648), written
#: there by `emit-run-outcome.sh record-*`, and what a close-out's copy sets them to.
PRIMARY_KEPT = {"harness": {"version": "5.4.0", "sha": "c013262"},
                "validateAttempts": {"phase1": 2}, "verify": {"findings": [], "loops": 1},
                "lessons": {"acknowledged": {"ids": ["LESSON-012"]}}, "lessonsWritten": []}
CLOSE_OUT_SETS = {"harness": {"version": "9.9.9", "sha": "0000000"},
                  "validateAttempts": {"phase1": 9}, "verify": {"findings": [], "loops": 9},
                  "lessons": {"acknowledged": {"ids": ["LESSON-999"]}},
                  "lessonsWritten": ["LESSON-9001"]}


def test_a_carried_close_out_state_is_data(tmp_path):
    """REQ-662 ADR-7: on the shipped Codex block, which declares no add_dir_flag, the close-out's
    copy of the state is model-written data. A copy that also sets `status`, `exec` and
    `approval` changes none of them in the primary path's state, and its other keys are
    carried. Of the run-outcome keys the primary path's copy already holds, `lessonsWritten`,
    which the close-out itself produces, is taken from the close-out's copy, and `lessons`,
    `harness`, `validateAttempts` and `verify` are kept. A copy that is not one JSON object, is
    gone, does not parse, nests too deep for the parser, is over the state-file size cap, or is a
    link or a special file is no record: nothing is carried, the linked file's content included,
    and the close-out ends failed with the merge standing. A chore PR that commits the copy is
    out of bounds and needs review, never merged."""
    (tmp_path / "hostile").mkdir()
    box = eh.adapter_sandbox(tmp_path / "hostile", "codex")
    box.req(closeout={"state_extra": dict(HOSTILE, **CLOSE_OUT_SETS)})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    run.write_primary_state(dict(run.read_primary_state(), **PRIMARY_KEPT))
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["status"] == "merged" and state["exec"] == run.public_exec()
    assert state["exec"]["exitClass"] == "ok"
    assert state["approval"]["decision"] == "approved"
    assert state["approval"]["decidedBy"] == "operator" and state["approval"]["action"] == "merge"
    assert state["closeOut"]["status"] == "ok" and state["completed"] is True
    assert state["notes"] == ["from the close-out"]
    assert state["lessonsWritten"] == ["LESSON-9001"]
    for key in ("lessons", "harness", "validateAttempts", "verify"):
        assert state[key] == PRIMARY_KEPT[key], key
    [carried] = eh.events(box, run, "close_out_state_carried")
    assert carried["record"] is True
    assert carried["ignored"] == ["approval", "exec", "harness", "lessons", "status",
                                  "validateAttempts", "verify"]
    assert {"closeOut", "completed", "notes", "lessonsWritten"} <= set(carried["taken"])
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
            # Nested past the parser's recursion limit: a `RecursionError`, read as unreadable.
            ("deep", lambda f: f.write_text("[" * 100000 + "]" * 100000), "not one JSON object"),
            ("large", lambda f: f.write_text(json.dumps(
                {"closeOut": {"status": "ok"}, "pad": "x" * 600000})), "over the"),
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


def test_a_close_out_state_nested_too_deep_fails_only_the_close_out(tmp_path):
    """A close-out copy of the state nested past the JSON parser's recursion limit is no
    record, as one that does not parse is: the close-out ends failed, the merge stands and the
    run ends merged, never stuck in `merging` with the merge worker gone."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    box.req(closeout={"state_text": "[" * 100000 + "]" * 100000})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["status"] == "merged" and state["repos"]["widgets"]["merged"]
    assert state["closeOut"]["status"] == "failed"
    assert state["closeOut"]["reason"] == "the close-out wrote no terminal record"
    [carried] = eh.events(box, run, "close_out_state_carried")
    assert carried["record"] is False


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
#: What a case's fake does after its commit when its commands left the config surface in its
#: working copy unlike the render: it puts the surface back, so its exit is clean and the
#: halt-time gate is what finds the path in its PR. A surface left changed at exit blocks the
#: run before any halt (`test_exec_launch.test_surface_edited_mid_run_blocks_the_run`).
EXEC_PATH_PUT_BACK = {
    "REQ-905": ["rm .fake-exec-file/README.md"],
    "REQ-906": ["cp docs/config.toml %s" % eh.FILE_CONFIG],
    "REQ-908": ["rm -r .fake-exec-file/prompts"],
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
    re-halted, and the restore runs before the merge. The fakes run as many at a time as the
    engine allows on the one repository, each run's own gitdir writes carried past the others'
    checksums."""
    benign = "REQ-909"
    box = eh.file_sandbox(tmp_path, monkeypatch, reqs=tuple(sorted(EXEC_PATH_CASES)) + (benign,))
    eh.commit_on_main(box, {eh.FILE_CONFIG: 'model = "operator"\n',
                            eh.FILE_HOOKS: '{"hooks": {}}\n'})
    for req, (commands, _hit) in EXEC_PATH_CASES.items():
        box.req(req, add=["src"], commands=commands,
                late_commands=EXEC_PATH_PUT_BACK.get(req, []))
    box.req(benign, closeout={"add": [".adlc"]})
    before = eh.git(box.repo, "status", "--porcelain", "-uall")
    orch = box.go(shared=True)
    for req, (_commands, (status, path)) in sorted(EXEC_PATH_CASES.items()):
        run = orch.runs[req]
        assert run.status == "awaiting_approval", (req, se.violations_of(run))
        assert not eh.events(box, run, "config_surface_violation"), req
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
    eh.until(lambda: se.pid_alive(run.exec.get("closeOutPid")), what="the close-out to start")
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
    # After the merge, which reads the verdict again (`test_the_verdict_is_read_again_before_
    # the_merge`), and before the close-out: the binary is upgraded during the deploy step.
    deploy = orch._deploy

    def upgraded_meanwhile(*args, **kw):
        box.write_scenario(version=UPGRADED)
        return deploy(*args, **kw)

    monkeypatch.setattr(orch, "_deploy", upgraded_meanwhile)
    orch.drain()
    closing = run.read_primary_state()["closeOut"]
    assert closing["status"] == "failed", closing
    assert "close-out is refused" in closing["reason"] and "installed-version" in \
        closing["reason"]
    assert run.status == "merged" and merged_count(box) == 1
    assert [launch["opts"]["resume"] for launch in box.launches()] == [False]


# ---- review fixes, 2026-11-18 ------------------------------------------------------------------
def test_the_verdict_is_read_again_before_the_merge(tmp_path, monkeypatch):
    """REQ-662 BR-11, BR-18: `execute` reads the adapter's verdict again before anything merges,
    so a run approved while the adapter read verified, then queued, does not merge once it
    reads unverified: it is re-halted with a fresh plan and nothing merges, and approve then
    refuses it as it refuses any unverified adapter. Verified again, it merges."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    token, _gate = box.tokens(REQ)
    assert box.approve(orch, drain=False) == "approved"
    box.write_scenario(version=UPGRADED)
    orch.drain()
    assert merged_count(box) == 0 and run.status == "awaiting_approval"
    assert "harness fake-exec-file is unverified, so the approve is refused" in \
        box.out.getvalue()
    assert box.tokens(REQ)[0] != token and run.ledger().read()["decision"] is None
    with pytest.raises(se.Refused, match="unverified, so the approve is refused"):
        box.approve(orch)
    assert merged_count(box) == 0
    box.write_scenario(version=eh.PROBED_VERSION)
    assert box.approve(orch) == "approved"
    assert run.status == "merged" and merged_count(box) == 2


def test_a_harness_that_cannot_start_at_relaunch_or_close_out_revokes(tmp_path, monkeypatch):
    """REQ-662 BR-5: `Popen` raising `OSError` (the binary gone, or no longer executable) once
    trust is granted. At an `answer`'s relaunch the run ends failed (setup-error) naming why,
    its trust revoked and its render restored, and the answer is refused with it. At the
    close-out, the close-out fails naming why, its own grant revoked; the merge stands. Each
    user config ends byte-identical."""
    (tmp_path / "answer").mkdir()
    box = eh.trust_sandbox(tmp_path / "answer", monkeypatch)
    box.req(status="blocked", claim="blocked", add=["src"],
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval"})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    with monkeypatch.context() as patch:
        eh.popen_fails(patch, run.doc["binary"], lambda argv, env: True)
        with pytest.raises(se.Refused, match="could not be started.*No such file or directory"):
            orch.answer(REQ, "the second option")
    assert run.status == "failed" and not orch.children and len(box.launches()) == 1
    assert "could not be started" in json.dumps(run.read_primary_state()["notes"])
    assert run.doc["trustGrants"] == {}
    assert [e["status"] for e in eh.events(box, run, "trust_revoked")] == [et.REVOKED] * 2
    assert not os.path.lexists(os.path.join(run.wc, eh.FILE_RULE))
    assert eh.read_text(box.user_config) == eh.USER_CONFIG

    (tmp_path / "close-out").mkdir()
    box = eh.trust_sandbox(tmp_path / "close-out", monkeypatch)
    box.req(add=["src"], closeout={"add": [".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    with monkeypatch.context() as patch:
        eh.popen_fails(patch, run.doc["binary"], lambda argv, env: "resume" in argv)
        assert box.approve(orch) == "approved"
    assert run.status == "merged" and merged_count(box) == 1
    closing = run.read_primary_state()["closeOut"]
    assert closing["status"] == "failed"
    assert "the close-out's harness could not be started" in closing["reason"]
    assert "No such file or directory" in closing["reason"]
    close = os.path.realpath(run.doc["closeOutWorkingCopy"])
    assert [(e["path"], e["status"]) for e in eh.events(box, run, "trust_revoked")][-1] == (
        close, et.REVOKED)
    assert run.doc["trustGrants"] == {} and eh.read_text(box.user_config) == eh.USER_CONFIG


def _held(tmp_path, monkeypatch, files):
    """A file-rendering sandbox whose REQ-901 merges cleanly and whose REQ-902, writing
    ``files``, is held behind it, with a tracked rendered path on main."""
    box = eh.file_sandbox(tmp_path, monkeypatch, reqs=("REQ-901", "REQ-902"))
    eh.commit_on_main(box, {eh.FILE_CONFIG: 'model = "operator"\n'})
    box.req("REQ-901", add=["src"], files={"src/a.txt": "901\n"}, closeout={"add": [".adlc"]})
    box.req("REQ-902", add=sorted({p.split("/")[0] for p in files}), files=files,
            status="blocked", claim="blocked",
            blockers=[{"blockedBy": "REQ-901", "conflictFiles": ["src/a.txt"],
                       "holdState": "held", "rebaseAttempts": 0}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "blockers": None, "files": {"src/c.txt": "902 again\n"},
                          "add": ["src"]})
    return box


def _upstream(box, files):
    """``files`` committed to main and pushed, behind the runs' backs: a PR the forge knows of
    (the mock's ``commit_prs``), so no exit check reads it as a direct push."""
    eh.commit_on_main(box, files)
    head = eh.git(box.bare, "rev-parse", "main").strip()
    (box.store / "commit_prs.json").write_text(json.dumps({head: [55]}))


def test_a_held_reqs_rebase_takes_the_upstream_render_base(tmp_path, monkeypatch):
    """REQ-662 BR-17: the unblock pass restores a held REQ's working copy, rebases it onto the
    integration branch the blocker merged into, and relaunches it. When the rebase brings an
    upstream change to a tracked path the engine renders, the relaunch records the rebased
    blob as the launch state, so the restore that leaves the working copy to a person writes
    the upstream content and `git status` is clean, never the pre-rebase blob over it."""
    box = _held(tmp_path, monkeypatch, {"src/b.txt": "902\n"})
    orch = box.go(shared=True)
    held = orch.runs["REQ-902"]
    assert held.status == "blocked"
    before = held.doc["hidden"][held.wc]["launchBlobs"][eh.FILE_CONFIG]["oid"]
    upstream = 'model = "upstream"\n'
    _upstream(box, {eh.FILE_CONFIG: upstream})
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    box.wait(orch)
    assert held.status == "awaiting_approval" and held.doc["launches"] == 2
    assert eh.git(held.wc, "show", "HEAD:" + eh.FILE_CONFIG) == upstream
    after = held.doc["hidden"][held.wc]["launchBlobs"][eh.FILE_CONFIG]["oid"]
    assert after != before and after == eh.git(box.bare, "rev-parse",
                                                "main:" + eh.FILE_CONFIG).strip()
    orch.reject("REQ-902", "enough", decided_by="operator")
    assert eh.read_text(os.path.join(held.wc, eh.FILE_CONFIG)) == upstream
    assert eh.git(held.wc, "status", "--porcelain", "--untracked-files=all") == ""
    assert "S" not in [ln.split()[0] for ln in eh.git(held.wc, "ls-files", "-t").splitlines()]


def test_a_held_reqs_rebase_conflict_leaves_no_skip_worktree_bit(tmp_path, monkeypatch):
    """REQ-662 BR-17, REQ-659 BR-12: a held REQ whose rebase onto the merged integration branch
    conflicts ends needs-manual-rebase, the rebase aborted, with its working copy restored
    and no `skip-worktree` bit left for a person to trip over."""
    box = _held(tmp_path, monkeypatch, {"README.md": "BBB\nline two\nline three\n"})
    orch = box.go(shared=True)
    held = orch.runs["REQ-902"]
    assert held.status == "blocked"
    _upstream(box, {"README.md": "CCC\nline two\nline three\n"})
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    [entry] = held.read_primary_state()["blockers"]
    assert entry["holdState"] == "needs-manual-rebase" and entry["conflictFiles"] == ["README.md"]
    assert held.doc["launches"] == 1 and held.status == "blocked"
    assert "S" not in [ln.split()[0] for ln in eh.git(held.wc, "ls-files", "-t").splitlines()]
    assert held.doc["hidden"][held.wc]["skipWorktree"] == []
    assert eh.read_text(os.path.join(held.wc, eh.FILE_CONFIG)) == 'model = "operator"\n'


@pytest.mark.parametrize("stream,words", [("cut", "last line is cut"),
                                          ("no-terminal", "no turn.completed event")])
def test_a_close_out_whose_output_did_not_parse_fails(tmp_path, stream, words):
    """REQ-662 BR-6: the close-out's output is held to the parser as a launch's is. A stream that
    did not parse (its last line cut, or no `turn.completed`) fails the close-out with the
    parser's message even though the last-message file reads as a good close-out, so its chore
    PR is not merged; the run's own merge stands."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    box.req(closeout={"stream": stream})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved"
    assert run.status == "merged" and merged_count(box) == 1
    closing = run.read_primary_state()["closeOut"]
    assert closing["status"] == "failed", closing
    assert "did not parse" in closing["reason"] and words in closing["reason"], closing
    assert "Chore PR:" in eh.read_text(run.last_message("close-out.json"))


def test_abort_of_a_close_out_revokes_its_trust_grant(tmp_path, monkeypatch):
    """REQ-662 BR-5, BR-20: an abort of a close-out in flight on a `user-config-entry` adapter
    revokes the close-out's grant: the merge stands, the close-out is failed, no grant is
    recorded and the user config is byte-identical."""
    box = eh.trust_sandbox(tmp_path, monkeypatch)
    box.req(add=["src"], closeout={"sleep": 30})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    worker = se.threading.Thread(target=lambda: box.approve(orch))
    worker.start()
    eh.until(lambda: se.pid_alive(run.exec.get("closeOutPid")), what="the close-out to start")
    close = os.path.realpath(run.doc["closeOutWorkingCopy"])
    assert et.trust_block(close) in eh.read_text(box.user_config)
    orch.abort(REQ, by="operator")
    worker.join(60)
    assert not worker.is_alive()
    assert run.status == "merged"
    assert run.read_primary_state()["closeOut"]["status"] == "failed"
    assert run.doc["trustGrants"] == {} and eh.read_text(box.user_config) == eh.USER_CONFIG


@pytest.mark.parametrize("harness", eh.EXEC_ADAPTERS)
def test_a_nested_launch_from_the_close_out_is_refused(tmp_path, harness):
    """REQ-662 BR-18: the resumed close-out session is a live exec process too. A `run` and a
    `resume` it starts through the engine's entry point, its environment scrubbed, are refused
    through its pid ancestry, which holds the close-out's pid, logged `nested_launch_refused`
    in its run; nothing is launched, and the close-out goes on."""
    box = eh.adapter_sandbox(tmp_path, harness, reqs=("REQ-901", "REQ-903"))
    del box.environ["XDG_STATE_HOME"]
    box.req("REQ-901", closeout={"nested": [
        ["run", "REQ-903", "--shared-credentials", "--harness", harness], ["resume"]]})
    orch = box.go(["REQ-901"], shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved"
    assert run.status == "merged" and run.read_primary_state()["closeOut"]["status"] == "ok"
    tried = [json.loads(ln) for ln in (box.home / "nested-REQ-901.jsonl").read_text().splitlines()]
    assert [t["argv"][0] for t in tried] == ["run", "resume"]
    refused = eh.events(box, run, "nested_launch_refused")
    assert len(refused) == 2
    for attempt, detail in zip(tried, refused):
        assert attempt["rc"] == 2 and "Rule B" in attempt["stderr"], attempt
        assert ("pid %d descends from the live exec pid %d of REQ-901"
                % (attempt["pid"], run.exec["closeOutPid"])) in attempt["stderr"], attempt
        assert detail["execPid"] == run.exec["closeOutPid"] and detail["pid"] == attempt["pid"]
    assert el.find_run(str(box.repo), "REQ-903", box.environ) is None
    assert not (box.repo / ".worktrees" / "REQ-903").exists()


# ---- confirmation pass, 2026-11-18: the close-out's exit check, its state copy, the rebase -----
def test_a_surface_changed_during_the_close_out_fails_it(tmp_path, monkeypatch):
    """REQ-662 BR-15: a config surface the close-out session edits (here its rule file, after
    its commit) is a `config_surface_violation` at its exit, recorded as a Rule B violation, and
    it fails the close-out with that text before the state is carried back and before the chore
    gate, so the chore PR is not merged. The REQ's own merge stands, and the close-out's trust
    grant is revoked."""
    box = eh.trust_sandbox(tmp_path, monkeypatch)
    box.req(add=["src"], closeout={"add": [".adlc"],
                                   "surface_writes": {eh.FILE_RULE: "# tampered\n"}})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["repos"]["widgets"]["merged"] and state["closeOut"]["status"] == "failed"
    reason = state["closeOut"]["reason"]
    assert reason.startswith(se.PROTOCOL) and "config_surface_violation at exit" in reason
    assert eh.FILE_RULE in reason
    assert merged_count(box) == 1
    assert not eh.events(box, run, "close_out_state_carried")
    close = run.doc["closeOutWorkingCopy"]
    assert [e["path"] for e in eh.events(box, run, "config_surface_violation")] == [eh.FILE_RULE]
    assert any(eh.FILE_RULE in v for v in se.violations_of(run))
    assert (os.path.realpath(close), et.REVOKED) in [
        (e["path"], e["status"]) for e in eh.events(box, run, "trust_revoked")]
    assert run.doc["trustGrants"] == {} and eh.read_text(box.user_config) == eh.USER_CONFIG


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_a_link_at_the_close_out_state_path_fails_the_close_out(tmp_path, monkeypatch, link):
    """REQ-662 ADR-7, BR-5: on a harness that cannot add the primary repo's spec directory, the
    engine copies the state into the close-out working copy through the guarded write. A link
    already at that path (put there between the close-out's render and the copy) refuses the
    copy: the close-out fails before any session starts, its trust grant is revoked, the linked
    file is untouched and the merge stands."""
    box = eh.trust_sandbox(tmp_path, monkeypatch)
    box.req(add=["src"], closeout={"add": [".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    target = tmp_path / "elsewhere.json"
    target.write_text('{"kept": true}\n')
    prepare = orch.prepare_surfaces

    def then_link(run_, wcs, branch, where):
        prepare(run_, wcs, branch, where)
        if where == "resume":
            spot = os.path.join(wcs[0], box.spec_dirs[REQ], "pipeline-state.json")
            os.makedirs(os.path.dirname(spot), exist_ok=True)
            (os.symlink if link == "symlink" else os.link)(str(target), spot)

    monkeypatch.setattr(orch, "prepare_surfaces", then_link)
    assert box.approve(orch) == "approved" and run.status == "merged"
    state = run.read_primary_state()
    assert state["repos"]["widgets"]["merged"] and state["closeOut"]["status"] == "failed"
    assert "the close-out's state file" in state["closeOut"]["reason"]
    assert "is a %s" % link in state["closeOut"]["reason"]
    assert merged_count(box) == 1 and len(box.argvs()) == 1
    assert target.read_text() == '{"kept": true}\n'
    close = os.path.realpath(run.doc["closeOutWorkingCopy"])
    assert (close, et.REVOKED) in [(e["path"], e["status"])
                                   for e in eh.events(box, run, "trust_revoked")]
    assert run.doc["trustGrants"] == {} and eh.read_text(box.user_config) == eh.USER_CONFIG


def test_a_failure_after_the_engine_rebase_restores_the_rebased_content(tmp_path, monkeypatch):
    """REQ-662 BR-17: once the unblock pass has rebased a held REQ's working copy, the run
    record holds the rebased index's blob for each tracked rendered path, saved before the
    push and the relaunch. So a failure between the rebase and the relaunch's own hiding (here
    the hiding refused after the relaunch's render wrote the working copy) leaves a working
    copy whose rendered paths restore to the rebased content, with `git status` clean."""
    box = _held(tmp_path, monkeypatch, {"src/b.txt": "902\n"})
    orch = box.go(shared=True)
    held = orch.runs["REQ-902"]
    assert held.status == "blocked"
    upstream = 'model = "upstream"\n'
    _upstream(box, {eh.FILE_CONFIG: upstream})
    hide = orch._hide

    def refused(run, wc, manifest, where):
        if run.req == "REQ-902":
            raise se.Refused("injected: the relaunch's hiding failed")
        return hide(run, wc, manifest, where)

    monkeypatch.setattr(orch, "_hide", refused)
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    assert "manual resume needed for REQ-902 (injected" in box.out.getvalue()
    assert held.status == "blocked" and held.doc["launches"] == 1
    assert eh.git(held.wc, "show", "HEAD:" + eh.FILE_CONFIG) == upstream
    rendered = os.path.join(held.wc, eh.FILE_CONFIG)
    assert eh.read_text(rendered) != upstream          # the relaunch's render, not hidden
    blobs = se.Run.load(held.path).doc["hidden"][held.wc]["launchBlobs"]
    assert blobs[eh.FILE_CONFIG] == {"mode": "100644", "oid": eh.git(
        box.bare, "rev-parse", "main:" + eh.FILE_CONFIG).strip()}
    orch.restore_surfaces(held)
    assert eh.read_text(rendered) == upstream
    assert eh.git(held.wc, "status", "--porcelain", "--untracked-files=all") == ""


# --------------------------------------------------------------------------- BUG-287
def test_bug287_the_mock_refuses_to_merge_a_draft(box):
    """The contrast behind the engine's flip to ready: a draft PR does not merge, on the mock
    as on GitHub, and the same PR merges once it is ready. Before BUG-287 the mock merged a
    draft, so no test saw that nothing under `--exec` could call `adlc_forge_pr_ready`."""
    mock = os.path.join(box.toolkit, "tools", "adlc", "forge_mock.py")
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_FORGE_MOCK_STORE=str(box.store),
               HOME=str(box.home))

    def forge(*argv):
        res = subprocess.run([sys.executable, mock] + list(argv), cwd=str(box.repo), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        return res.returncode, res.stdout

    def git(*args):
        # The sandbox HOME carries the identity a commit needs.
        subprocess.run(["git", "-C", str(box.repo)] + list(args), env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    git("checkout", "-q", "-b", "feat/REQ-901-thing")
    with open(os.path.join(str(box.repo), "README.md"), "a") as fh:
        fh.write("line four\n")
    git("commit", "-qam", "change")
    git("push", "-q", "origin", "feat/REQ-901-thing")
    rc, out = forge("pr_create", "--draft", "--base", "main", "--head", "feat/REQ-901-thing",
                    "--title", "t", "--body", "b")
    assert rc == 0, out
    number = dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)["number"]
    rc, out = forge("pr_merge", number, "--squash")
    assert rc != 0 and "error_class=merge-blocked-by-policy" in out and "still a draft" in out
    rc, out = forge("pr_ready", number)
    assert rc == 0, out
    rc, out = forge("pr_merge", number, "--squash")
    assert rc == 0 and "state=MERGED" in out, out


def test_bug287_the_launch_and_the_relaunch_name_the_forge_repo_and_the_state_file(box):
    """Run 1 of the first real pipeline run ended at Step 0: the session had no forge
    repository to pass, and had been told nothing about which state file a fence takes. The
    engine knows both, and both prompts it builds now say them: the launch's, and the one an
    `answer` relaunches with."""
    box.req(status="blocked", claim="blocked",
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "sid": "session-two", "blockers": None, "files": {"z.txt": "z\n"}})
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    orch.answer(REQ, "the second option")
    box.wait(orch)
    assert run.status == "awaiting_approval"
    state = os.path.join(os.path.realpath(str(box.repo)), ".adlc", "specs", "REQ-901-thing",
                         "pipeline-state.json")
    assert run.primary_state_path() == state
    for name in ("prompt.txt", "prompt.2.txt"):
        text = open(run.file(name), encoding="utf-8").read()
        # The sandbox's origin is <tmp>/acme/widgets.git, which the mock forge knows by
        # the same owner and name.
        assert "primary repo is `acme/widgets`." in text, name
        assert "Wherever a fence takes `<state>`, pass `%s`" % state in text, name
        assert "You have no clock." in text, name


# ---- REQ-719: `abort` drops a blocked run; `reject` and `abort` in the run-outcome log ---------
@pytest.fixture
def reaped():
    """Register an orchestrator (``reaped(orch)`` returns it); at teardown every fake harness it
    still holds is killed, by its process group: a child it started, and a recorded pid that is
    still the process recorded (`same_process`). A test that fails before its own `abort`
    leaves no 30-second sleeper behind."""
    held = []

    def register(orch):
        held.append(orch)
        return orch

    yield register
    pids = set()
    for orch in held:
        pids.update(proc.pid for proc in orch.children.values() if proc.poll() is None)
        pids.update(run.exec["pid"] for run in orch.all_runs()
                    if run.exec.get("pid") and se.same_process(run.exec["pid"],
                                                               run.exec.get("pidStart")))
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    for orch in held:
        for proc in orch.children.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


def _aborted_line(run, urls):
    """The one line `abort` prints (REQ-719 BR-2)."""
    return "%s aborted by operator; working copy left at %s, branch %s, PR %s" % (
        run.req, run.wc, run.doc["branch"], ", ".join(urls))


def _recording_signals(mp, signalled):
    """Record every signal `os.kill` and `os.killpg` would send, through ``mp``, sending none; a
    liveness probe (signal 0) still runs."""
    real_kill = os.kill

    def kill(pid, sig):
        if sig == 0:                            # a liveness probe, not a signal
            return real_kill(pid, sig)
        signalled.append(("kill", pid, sig))

    mp.setattr(os, "kill", kill)
    mp.setattr(os, "killpg", lambda pid, sig: signalled.append(("killpg", pid, sig)))


def test_req719_abort_drops_a_blocked_run(box, tmp_path):
    """REQ-719 BR-1, BR-29: `abort` takes a run at `blocked` whose recorded harness and
    close-out pids are not live. Nothing is signalled. The run ends `failed` with who aborted
    it, when, and `abortedFrom: blocked`, in the run record and the primary path's state; the
    token held for it is discarded; and it prints one line naming the REQ, who aborted it, the
    working copy, the branch and the PR. Offline: the mock forge, and every directory the run
    writes under a throwaway one. The signal patch ends in its own context, so conftest's HOME
    sandbox stays in place for the rest of the test."""
    for key in ("HOME", "ADLC_HOME", "XDG_STATE_HOME", "ADLC_FORGE_MOCK_STORE",
                "ADLC_RUN_OUTCOMES_LOG"):
        assert os.path.realpath(box.environ[key]).startswith(os.path.realpath(str(tmp_path))), key
    assert box.environ["ADLC_FORGE_MOCK"] == "1"
    box.blocked()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked" and REQ not in orch.children
    assert not se.recorded_harness_pids(run.doc)
    assert os.path.realpath(run.path).startswith(os.path.realpath(str(tmp_path)))
    url = run.read_primary_state()["repos"]["widgets"]["prUrl"]
    # A token held for the run: the drop discards it, as `reject` does.
    orch.tokens[REQ] = {"approve": el.token_digest(el.mint_token()), "gate": None}
    signalled = []
    said = len(box.out.getvalue())
    with pytest.MonkeyPatch.context() as mp:
        _recording_signals(mp, signalled)
        line = orch.abort(REQ, by="operator")
    assert signalled == []
    assert run.status == "failed"
    assert run.exec["abortedBy"] == "operator" and run.exec["abortedAt"]
    assert run.exec["abortedFrom"] == "blocked"
    assert REQ not in orch.tokens
    state = run.read_primary_state()
    assert state["status"] == "failed" and state["exec"]["abortedFrom"] == "blocked"
    # Why it blocked stays on the record a person reads.
    assert state["blockers"] == [{"reason": "reflector-questions", "question": "which?"}]
    assert se.Run.load(run.path).exec["abortedFrom"] == "blocked"
    assert line == _aborted_line(run, [url])
    assert box.out.getvalue()[said:] == line + "\n"


def test_req719_the_drop_makes_no_one_way_move_and_no_forge_call(tmp_path, monkeypatch):
    """REQ-719 BR-2, AC-1: the drop leaves the local and the remote branch, the PR and the
    working copy as they were, for a person. It restores what the engine rendered and hid in
    the working copy, holds no trust grant and leaves the user config as it found it, logs no
    `one_way_move`, and makes no forge call: `calls.log` gains no line. On a file-rendering
    adapter whose trust grant writes the user config."""
    box = eh.trust_sandbox(tmp_path, monkeypatch)
    base = 'model = "operator"\n'
    eh.commit_on_main(box, {eh.FILE_CONFIG: base})
    box.blocked(add=["src"])
    user = box.user_files()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    wc = run.wc
    assert run.status == "blocked"
    # At the block the render is still in the working copy, and hidden.
    assert eh.read_text(os.path.join(wc, eh.FILE_CONFIG)) != base
    assert os.path.exists(os.path.join(wc, eh.FILE_RULE))
    branch = run.doc["branch"]
    remote = eh.git(box.bare, "rev-parse", "refs/heads/" + branch).strip()
    local = eh.git(box.repo, "rev-parse", "refs/heads/" + branch).strip()
    prs = (box.store / "prs.json").read_text()
    calls = (box.store / "calls.log").read_text()
    logged = len(box.log(run))
    orch.abort(REQ, by="operator")
    assert run.status == "failed" and run.exec["abortedFrom"] == "blocked"
    assert eh.git(box.bare, "rev-parse", "refs/heads/" + branch).strip() == remote
    assert eh.git(box.repo, "rev-parse", "refs/heads/" + branch).strip() == local
    assert eh.git(wc, "rev-parse", "HEAD").strip() == local
    assert (box.store / "prs.json").read_text() == prs
    [pr] = json.loads(prs)["prs"]
    assert (pr["state"], pr["isDraft"], pr["title"], pr["body"]) == (
        "OPEN", False, "%s: thing" % REQ, "body")
    assert (box.store / "calls.log").read_text() == calls
    assert os.path.isdir(wc)
    assert eh.read_text(os.path.join(wc, eh.FILE_CONFIG)) == base
    assert not os.path.lexists(os.path.join(wc, eh.FILE_RULE))
    assert "S" not in [ln.split()[0] for ln in eh.git(wc, "ls-files", "-t").splitlines()]
    assert subprocess.run(["git", "-C", wc, "config", "--worktree", "--get",
                           "core.excludesFile"], stdout=subprocess.PIPE).returncode != 0
    assert eh.git(wc, "status", "--porcelain", "-uall") == ""
    assert not run.doc.get("trustGrants") and run.exec["trustRevokedAt"]
    assert box.user_files() == user
    assert not [r for r in box.log(run) if r["kind"] == "one_way_move"]
    dropped = box.log(run)[logged:]
    assert not [r for r in dropped if r["kind"] == "partial" and r["argv"][0] == "forge.sh"]
    assert not [r for r in dropped if r["kind"] == "git"
                and ({"push", "fetch"} & set(r["argv"]))]


def _queued_behind_a_conflict(tmp_path, **second):
    """REQ-901 merged; REQ-902 approved and then blocked by a rebase conflict on README.md,
    its approval recorded; REQ-903 approved and queued behind REQ-902. ``second`` adds to
    REQ-902's script. Returns the sandbox, the orchestrator, REQ-902's and REQ-903's runs and
    REQ-902's PR URL."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902", "REQ-903"))
    box.req("REQ-901", files={"README.md": "AAA\nline two\nline three\n"})
    box.req("REQ-902", files={"README.md": "BBB\nline two\nline three\n", "c.txt": "902\n"},
            sleep_first=1.5, **second)
    box.req("REQ-903", files={"c.txt": "903\n"}, sleep_first=3)
    orch = box.go(shared=True)
    blocked, queued = orch.runs["REQ-902"], orch.runs["REQ-903"]
    box.approve(orch, REQ)                      # REQ-901 merges: main moves under REQ-902
    assert orch.runs[REQ].status == "merged"
    assert box.approve(orch, "REQ-902", drain=False) == "approved"
    assert box.approve(orch, "REQ-903", drain=False) == "approved (queued behind REQ-902)"
    orch.drain()
    assert blocked.status == "blocked" and queued.status == "approved"
    assert blocked.read_primary_state()["blockers"][0]["conflictFiles"] == ["README.md"]
    assert blocked.ledger().read()["decision"]["decision"] == "approved"
    return box, orch, blocked, queued, blocked.ledger().read()["plan"]["prs"][0]["url"]


def test_req719_an_approved_then_conflicted_run_is_never_merged_after_the_drop(tmp_path):
    """REQ-719 BR-2, AC-3: a run approved and then blocked by a rebase conflict holds a
    recorded approval. After the drop it is never executed, by the three paths that could reach
    it: it is out of the merge queue, `answer` refuses it, and a later `resume` skips it. The
    REQ whose approval was queued behind it is released and merges."""
    box, orch, second, third, url = _queued_behind_a_conflict(tmp_path)
    line = orch.abort("REQ-902", by="operator")
    assert line == _aborted_line(second, [url])
    assert second.status == "failed" and second.exec["abortedFrom"] == "blocked"
    # The queue: `execute` is reached from it alone, and the run is not in it.
    assert "REQ-902" not in orch.queue and orch.queue == ["REQ-903"]
    assert third.doc["holdBehind"] is None
    assert se.Run.load(third.path).doc["holdBehind"] is None
    # `answer` refuses a status that is not `blocked`.
    with pytest.raises(se.Refused, match="REQ-902 is failed, not blocked"):
        orch.answer("REQ-902", "go on")
    assert len(box.argvs("REQ-902")) == 1
    # A later supervisor skips a terminal run, and drains the one queued behind it.
    later = box.orch()
    later.resume()
    assert sorted(later.runs) == ["REQ-903"] and later.queue == ["REQ-903"]
    later.drain()
    assert later.runs["REQ-903"].status == "merged"
    assert se.Run.load(second.path).status == "failed"
    merged = [c["argv"][0] for c in box.calls("pr_merge")]
    assert url not in merged
    assert later.runs["REQ-903"].ledger().read()["plan"]["prs"][0]["url"] in merged


def test_req719_answer_after_the_drop_is_refused(tmp_path, reaped):
    """REQ-719 BR-3: `answer` after the drop is refused naming `failed`, and nothing is
    launched. The other order is not a refusal: an `abort` after an `answer` finds the
    relaunched harness live and kills it, as REQ-659 BR-20 has it."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.blocked("REQ-901")
    box.blocked("REQ-902", after_answer={"status": "awaiting_approval",
                                         "claim": "awaiting_approval", "blockers": None,
                                         "sleep_first": 30})
    orch = reaped(box.go(shared=True))
    first, second = orch.runs["REQ-901"], orch.runs["REQ-902"]
    assert first.status == second.status == "blocked"
    orch.abort("REQ-901", by="operator")
    with pytest.raises(se.Refused, match="REQ-901 is failed, not blocked"):
        orch.answer("REQ-901", "too late")
    assert first.status == "failed" and "REQ-901" not in orch.children
    assert len(box.argvs("REQ-901")) == 1
    orch.answer("REQ-902", "the second option")
    pid = second.exec["pid"]
    assert second.status == "running" and se.same_process(pid, second.exec["pidStart"])
    eh.until(lambda: len(box.argvs("REQ-902")) == 2, what="the relaunch to start")
    orch.abort("REQ-902", by="operator")
    eh.until(lambda: not se.pid_alive(pid), timeout=10, what="the relaunched harness to be gone")
    assert second.status == "failed" and second.exec["abortedFrom"] == "running"
    assert "REQ-902" not in orch.children


def test_req719_abort_is_still_refused_elsewhere(tmp_path):
    """REQ-719 BR-4, AC-4: every refusal but the blocked one stands, with nothing changed. At
    `awaiting_approval` with no live process the message names `reject`; on `approved`,
    `merged` and `rejected` it names the status; from inside a run (`ADLC_EXEC_RUN`) the caller
    guard refuses even a blocked run, in process and through the client. `abort` mints and
    prints no token (LESSON-781)."""
    reqs = ("REQ-901", "REQ-902", "REQ-903", "REQ-904")
    box = eh.Sandbox(tmp_path, reqs=reqs)
    box.blocked("REQ-904")
    orch = box.go(shared=True)
    runs = [orch.runs[req] for req in reqs]
    merged, rejected, gate, blocked = runs
    box.approve(orch, "REQ-901")
    orch.reject("REQ-902", "no", decided_by="operator")
    assert [r.status for r in runs] == ["merged", "rejected", "awaiting_approval", "blocked"]

    def snapshot(run):
        return (json.dumps(run.doc, sort_keys=True),
                json.dumps(run.read_primary_state(), sort_keys=True), len(box.outcomes()),
                run.req in orch.tokens, (box.store / "calls.log").read_text(),
                box.out.getvalue())

    def refused(run, match, **kw):
        before = snapshot(run)
        with pytest.raises(se.Refused, match=match):
            orch.abort(run.req, by="operator", **kw)
        assert snapshot(run) == before

    refused(gate, r"REQ-903 has no live process; its last status is awaiting_approval, .*"
                  r"`reject`")
    assert "REQ-903" in orch.tokens
    refused(merged, r"REQ-901 has no live process; its last status is merged$")
    refused(rejected, r"REQ-902 has no live process; its last status is rejected$")
    refused(blocked, "Rule B", caller_env={"ADLC_EXEC_RUN": "REQ-904"})
    inside = box.orch(ADLC_EXEC_RUN="REQ-904")
    before = snapshot(blocked)
    with pytest.raises(se.Refused, match="Rule B"):
        se._client(inside, se._parser().parse_args(["abort", "--channel", "skill", "REQ-904"]))
    assert se.Run.load(blocked.path).status == "blocked" and snapshot(blocked) == before
    box.approve(orch, "REQ-903", drain=False)
    refused(gate, r"REQ-903 has no live process; its last status is approved$")
    assert orch.queue == ["REQ-903"]
    # The guard was all that stood in the way of the blocked run.
    orch.abort("REQ-904", by="operator")
    assert blocked.status == "failed"


def test_req719_reject_records_rejected(box):
    """REQ-719 BR-18, AC-14: `reject` appends exactly one run-outcome line: `terminal`
    `rejected`, `engine` `exec` and an empty `blocked_reason`. The operator's reason is the
    ledger's alone: it is nowhere in the log."""
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    before = box.outcomes()
    reason = "not this sprint, see thread 5c1e9"
    orch.reject(REQ, reason, decided_by="operator")
    assert run.ledger().read()["decision"]["reason"] == reason
    [line] = box.outcomes()[len(before):]
    assert (line["terminal"], line["engine"], line["blocked_reason"], line["req"]) == (
        "rejected", "exec", "", REQ)
    text = eh.read_text(box.environ["ADLC_RUN_OUTCOMES_LOG"])
    assert reason not in text and "5c1e9" not in text


def test_req719_abort_records_aborted_from_both_arms(tmp_path, reaped):
    """REQ-719 BR-19, AC-15: the kill of a running harness and the drop of a blocked run each
    append one run-outcome line, `failed` / `aborted`, and record the status found in
    `exec.abortedFrom`. A run that blocked and was dropped has two lines, `blocked` then
    `failed`."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", sleep_first=30)
    box.blocked("REQ-902")
    orch = reaped(box.start(shared=True))
    running, blocked = orch.runs["REQ-901"], orch.runs["REQ-902"]
    eh.until(lambda: os.path.exists(running.wc_state_path()), what="REQ-901's harness to start")

    def settled():
        orch.poll_once()
        return blocked.status == "blocked"

    eh.until(settled, what="REQ-902 to block")
    assert running.status == "running"
    pid = running.exec["pid"]
    orch.abort("REQ-901", by="operator")
    orch.abort("REQ-902", by="operator")
    eh.until(lambda: not se.pid_alive(pid), timeout=10, what="REQ-901's harness to be gone")
    box.wait(orch)
    assert running.exec["abortedFrom"] == "running" and blocked.exec["abortedFrom"] == "blocked"
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes("REQ-901")] == [
        ("failed", "aborted")]
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes("REQ-902")] == [
        ("blocked", "reflector-questions"), ("failed", "aborted")]
    assert {o["engine"] for o in box.outcomes()} == {"exec"}


# ---- REQ-719 Phase 5: the hold, the unblock pass and the abort's line ---------------------------
def _offline(box, argv):
    """`adlc sprint-exec <argv>` with no supervisor running, as the client makes it: a fresh
    orchestrator that loads only the run named (`_client`)."""
    orch = box.orch()
    assert se._client(orch, se._parser().parse_args(argv)) == 0
    return orch


def test_req719_an_offline_abort_releases_the_hold_queued_behind_it(tmp_path):
    """REQ-719 BR-2, BR-3: the drop of a blocked run made with no supervisor running releases
    the approval queued behind it. The client's orchestrator loads only the run it drops, and a
    later `resume` skips that terminal run, so the hold is read from disk: REQ-903 merges, the
    run it was held behind is never merged, and the new supervisor is done."""
    box, _orch, second, third, url = _queued_behind_a_conflict(tmp_path)
    offline = _offline(box, ["abort", "--channel", "skill", "REQ-902"])
    assert sorted(offline.runs) == ["REQ-902"]
    assert se.Run.load(second.path).status == "failed"
    assert _aborted_line(second, [url]) + "\n" in box.out.getvalue()
    later = box.orch()
    later.resume()
    assert sorted(later.runs) == ["REQ-903"] and later.queue == ["REQ-903"]
    later.drain()
    resumed = later.runs["REQ-903"]
    assert resumed.doc["holdBehind"] is None and se.Run.load(third.path).doc["holdBehind"] is None
    assert resumed.status == "merged"
    merged = [c["argv"][0] for c in box.calls("pr_merge")]
    assert url not in merged and resumed.ledger().read()["plan"]["prs"][0]["url"] in merged
    assert se.Run.load(second.path).status == "failed"
    assert later.done()


def test_req719_an_offline_reject_releases_the_hold_queued_behind_it(tmp_path):
    """REQ-659 BR-10, REQ-719 BR-2: the same for a `reject` made with no supervisor running.
    REQ-902's approval is queued behind REQ-901, which is rejected through the client; a later
    `resume` reads REQ-901's rejection from disk, and REQ-902 merges."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"shared/a.txt": "901\n"})
    box.req("REQ-902", files={"shared/a.txt": "902\n"}, sleep_first=1.5)
    orch = box.go(shared=True)
    first, second = orch.runs[REQ], orch.runs["REQ-902"]
    url = first.ledger().read()["plan"]["prs"][0]["url"]
    assert box.approve(orch, "REQ-902", drain=False) == "approved (queued behind REQ-901)"
    offline = _offline(box, ["reject", "--channel", "skill", REQ, "not this sprint"])
    assert sorted(offline.runs) == [REQ] and se.Run.load(first.path).status == "rejected"
    later = box.orch()
    later.resume()
    assert sorted(later.runs) == ["REQ-902"] and later.queue == ["REQ-902"]
    later.drain()
    resumed = later.runs["REQ-902"]
    assert resumed.doc["holdBehind"] is None and se.Run.load(second.path).doc["holdBehind"] is None
    assert resumed.status == "merged"
    assert url not in [c["argv"][0] for c in box.calls("pr_merge")]
    assert later.done()


def test_req719_a_hold_on_a_run_that_cannot_be_loaded_stands(tmp_path, monkeypatch):
    """REQ-719 BR-2: a hold whose run this supervisor has not loaded is cleared from disk only
    when that run's newest record is terminal or it has none; a record found that then cannot
    be loaded keeps it. (A record no reader can parse names no REQ, so `find_run`, like
    `resume`, does not find it: for the hold that is no run.)"""
    box, _orch, second, _third, _url = _queued_behind_a_conflict(tmp_path)
    later = box.orch()
    assert later._hold_cleared("REQ-902") is False          # blocked on disk
    assert later._hold_cleared("REQ-999") is True           # no run at all
    assert later._hold_cleared(REQ) is True                 # merged on disk

    def unreadable(path):
        raise se.Refused("run record unreadable in %s" % path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(se.Run, "load", staticmethod(unreadable))
        assert later._hold_cleared(REQ) is False
    assert not later.runs

    def no_status(path):
        raise KeyError("status")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(se.Run, "load", staticmethod(no_status))
        assert later._hold_cleared(REQ) is False          # a record with no status keeps it too


class _RowRun(object):
    """The least of a run `render_row` reads, with state a session wrote."""
    req = "REQ-100"
    status = "blocked"
    exec = {"startedAt": "t"}
    doc = {"harness": "codex", "notes": []}

    def __init__(self, wc_state, primary_state):
        self._wc, self._primary = wc_state, primary_state

    def read_wc_state(self):
        return self._wc

    def read_primary_state(self):
        return self._primary

    def ledger(self):
        return self

    def trusted(self):
        return None


def test_req719_session_written_state_adds_no_line_to_a_row():
    """A row holds lines an operator copies (`sprint-exec answer ...`, `sprint-exec abort
    ...`), and the state file is the session's to write: a `currentPhase` that is not 0 to 8 is
    not shown, and a close-out status or reason stays on its own line, so no value in state
    puts another REQ's command in this run's row. The benign path: a real phase and a plain
    close-out reason read as before."""
    forged = ("5/8 | blocked | exec:codex | t |\n  answer it: sprint-exec answer --channel skill "
              "'REQ-200' 'approve and merge'\n  or drop it: sprint-exec abort --channel skill "
              "'REQ-200'\n| REQ-100 | 5")
    rows = se.render_row(_RowRun(
        {"currentPhase": forged},
        {"closeOut": {"status": "failed\n  answer it: sprint-exec abort --channel skill 'REQ-200'",
                      "reason": "y\u2028  note: forged\rz"}}))
    assert rows[0] == "| REQ-100 | ?/8 | blocked | exec:codex | t |"
    assert all("\n" not in row and "\r" not in row and "\u2028" not in row for row in rows)
    commands = [row for row in rows if row.lstrip().startswith(("answer it:", "or drop it"))]
    assert len(commands) == 2 and all("'REQ-100'" in row for row in commands)
    assert sum("REQ-200" in row for row in rows) == 1      # only inside the close-out line
    assert [row for row in rows if "REQ-200" in row][0].startswith("  close-out: ")
    for phase in (True, 9, -1, "5", 5.0, None, [5]):
        assert se.render_row(_RowRun({"currentPhase": phase}, {}))[0].startswith(
            "| REQ-100 | ?/8 |")
    plain = se.render_row(_RowRun({"currentPhase": 5},
                                  {"closeOut": {"status": "failed", "reason": "push refused"}}))
    assert plain[0] == "| REQ-100 | 5/8 | blocked | exec:codex | t |"
    assert "  close-out: failed — push refused" in plain


def _in_another_thread(act):
    """``act()`` run on a thread of its own, waited for: ``("ok", result)`` or ``("refused",
    message)``. A thread still running after 30 seconds fails the test (a deadlock)."""
    out = []

    def body():
        try:
            out.append(("ok", act()))
        except se.Refused as exc:
            out.append(("refused", str(exc)))

    thread = threading.Thread(target=body)
    thread.start()
    thread.join(30)
    assert not thread.is_alive(), "the competing call did not return"
    return out[0]


def _held_behind_the_first(tmp_path, **after):
    """REQ-902 blocked behind REQ-901, which merges cleanly; the unblock pass then rebases and
    relaunches REQ-902, whose relaunch goes to the gate (``after`` adds to that script)."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", files={"a.txt": "901\n"})
    box.req("REQ-902", files={"b.txt": "902\n"}, status="blocked", claim="blocked",
            blockers=[{"blockedBy": "REQ-901", "conflictFiles": ["a.txt"], "holdState": "held",
                       "rebaseAttempts": 0}],
            after_answer=dict({"status": "awaiting_approval", "claim": "awaiting_approval",
                               "blockers": None, "files": {"c.txt": "902\n"}}, **after))
    orch = box.go(shared=True)
    held = orch.runs["REQ-902"]
    assert held.status == "blocked"
    return box, orch, held


def _during_the_unblock_pass(monkeypatch, orch, act):
    """Run ``act`` on another thread at the point the merge worker's unblock pass fetches the
    integration branch for the held REQ, once REQ-901 has merged, and wait for it. Returns the
    list its one outcome is appended to (:func:`_in_another_thread`)."""
    real = eg.fetch_integration
    seen = []

    def fetch(toolbox, repo, ib):
        if not seen and orch.runs[REQ].status == "merged":
            seen.append(_in_another_thread(act))
        return real(toolbox, repo, ib)

    monkeypatch.setattr(eg, "fetch_integration", fetch)
    return seen


BEING_REBASED = ("REQ-902 is being rebased after REQ-901 merged; run the command again in a "
                 "moment")


def test_req719_abort_during_the_unblock_pass_is_refused(tmp_path, monkeypatch, reaped):
    """REQ-719 BR-3: an `abort` that arrives while the merge worker rebases and relaunches a held
    REQ is refused, saying so and to run it again; nothing is signalled and nothing changes. The
    run is relaunched once and is not `failed`. Once the pass is over the run is `running`, and
    the same `abort` kills its harness as before (REQ-659 BR-20)."""
    box, orch, held = _held_behind_the_first(tmp_path, sleep_first=30)
    reaped(orch)
    seen = _during_the_unblock_pass(monkeypatch, orch,
                                    lambda: orch.abort("REQ-902", by="operator"))
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    assert seen == [("refused", BEING_REBASED)]
    assert held.status == "running" and held.doc["launches"] == 2
    assert held.exec["abortedBy"] is None
    assert [o["terminal"] for o in box.outcomes("REQ-902")] == ["blocked"]
    eh.until(lambda: len(box.argvs("REQ-902")) == 2, what="the relaunch to start")
    pid = held.exec["pid"]
    assert se.same_process(pid, held.exec["pidStart"])
    orch.abort("REQ-902", by="operator")
    eh.until(lambda: not se.pid_alive(pid), timeout=10, what="the relaunched harness to be gone")
    assert held.status == "failed" and held.exec["abortedFrom"] == "running"
    assert len(box.argvs("REQ-902")) == 2


def test_req719_answer_during_the_unblock_pass_is_refused(tmp_path, monkeypatch):
    """REQ-719 BR-3: an `answer` that arrives while the merge worker rebases and relaunches a
    held REQ is refused the same way, so the run is launched once more, not twice, and the
    refused reply reaches no prompt."""
    box, orch, held = _held_behind_the_first(tmp_path)
    seen = _during_the_unblock_pass(monkeypatch, orch,
                                    lambda: orch.answer("REQ-902", "the second option"))
    box.approve(orch, REQ)
    assert seen == [("refused", BEING_REBASED)]
    box.wait(orch)
    assert held.status == "awaiting_approval" and held.doc["launches"] == 2
    assert len(box.argvs("REQ-902")) == 2
    assert "the second option" not in eh.read_text(held.file("prompt.2.txt"))


def test_req719_a_blocked_run_dropped_with_no_unblock_pass_in_flight_is_not_relaunched(
        tmp_path):
    """REQ-719 BR-1, BR-3: the benign path. A held REQ dropped while nothing rebases it drops,
    and the unblock pass after its blocker merges leaves it alone: no relaunch, no rebase."""
    box, orch, held = _held_behind_the_first(tmp_path)
    orch.abort("REQ-902", by="operator")
    assert held.status == "failed" and held.exec["abortedFrom"] == "blocked"
    logged = len(box.log(held))
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    assert held.status == "failed" and held.doc["launches"] == 1
    assert len(box.argvs("REQ-902")) == 1
    assert not [r for r in box.log(held)[logged:] if r["kind"] == "git" and "rebase" in r["argv"]]


def test_req719_a_drop_between_the_scan_and_the_rebase_stops_the_unblock_pass(tmp_path,
                                                                              monkeypatch):
    """REQ-719 BR-3: the unblock pass reads a held REQ's status again under the lock before it
    acts. An `abort` that drops the run after the pass found it `blocked` and before the rebase
    leaves it dropped: the worker rebases nothing, pushes nothing, grants no trust and
    relaunches nothing."""
    box, orch, held = _held_behind_the_first(tmp_path)
    real = se.Orchestrator.rank
    seen = []

    def rank(run):
        # The pass ranks what it found just before it rebases each one.
        if run is held and orch.runs[REQ].status == "merged" and not seen:
            seen.append(_in_another_thread(lambda: orch.abort("REQ-902", by="operator")))
        return real(run)

    monkeypatch.setattr(orch, "rank", rank)
    logged = len(box.log(held))
    box.approve(orch, REQ)
    assert orch.runs[REQ].status == "merged"
    assert seen and seen[0][0] == "ok" and held.exec["abortedFrom"] == "blocked"
    assert held.status == "failed" and held.doc["launches"] == 1
    assert len(box.argvs("REQ-902")) == 1
    after = [r for r in box.log(held)[logged:] if r["kind"] == "git"]
    assert not [r for r in after if {"rebase", "push"} & set(r["argv"])]
    assert not held.doc.get("trustGrants")


def _held_by_another_thread(lock):
    """Whether some other thread holds ``lock`` now: a thread of its own cannot take it without
    waiting."""
    got = []

    def probe():
        took = lock.acquire(blocking=False)
        got.append(took)
        if took:
            lock.release()

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join(10)
    return got == [False]


@pytest.mark.parametrize("how,reason", [("conflict", "merge-conflict"), ("mismatch", "other")])
def test_req719_an_abort_waits_until_the_block_is_recorded(tmp_path, monkeypatch, how, reason):
    """REQ-719 BR-3, BR-19: the merge worker's `blocked` (a rebase conflict's hold, a rebase
    whose changed paths moved) is one step under the supervisor's lock: the status, the carry
    and the run-outcome line. An `abort` that arrives in that step waits for it, so the REQ's
    run-outcome lines read `blocked` and then `failed` / `aborted`, never the other order."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    if how == "conflict":
        box.req("REQ-901", files={"README.md": "AAA\nline two\nline three\n"})
        box.req("REQ-902", files={"README.md": "BBB\nline two\nline three\n"}, sleep_first=1.5)
    else:
        box.req("REQ-901", files={"a.txt": "901\n"})
        box.req("REQ-902", files={"b.txt": "902\n"})
    orch = box.go(shared=True)
    second = orch.runs["REQ-902"]
    box.approve(orch, REQ)
    if how == "mismatch":
        monkeypatch.setattr(eg, "trial_merge", lambda *a: (1, ["b.txt"]))
        monkeypatch.setattr(eg, "changed_paths", lambda *a: [["A", "other.txt"]])
    held_at = []
    aborts = []
    threads = []

    def seam(real):
        def call(run, *args, **kw):
            if run is second and run.status == "blocked" and not run.exec.get("abortedBy"):
                held_at.append((real.__name__, _held_by_another_thread(orch.lock)))
                if not threads:
                    thread = threading.Thread(target=lambda: aborts.append(
                        orch.abort("REQ-902", by="operator")))
                    thread.start()
                    threads.append(thread)
            return real(run, *args, **kw)
        return call

    monkeypatch.setattr(orch, "_carry", seam(orch._carry))
    monkeypatch.setattr(orch, "_emit", seam(orch._emit))
    box.approve(orch, "REQ-902")
    threads[0].join(30)
    assert not threads[0].is_alive() and len(aborts) == 1
    assert ("_carry", True) in held_at and ("_emit", True) in held_at
    assert all(held for _name, held in held_at), held_at
    assert second.status == "failed" and second.exec["abortedFrom"] == "blocked"
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes("REQ-902")] == [
        ("blocked", reason), ("failed", "aborted")]
    assert merged_count(box) == 2, "REQ-902 was not merged"


def test_req719_a_run_ended_after_it_left_the_queue_is_not_merged(box, monkeypatch):
    """REQ-719 BR-2: `execute` does not act on a terminal run. A run that ends between leaving
    the merge queue and `execute` gets one line and nothing else: no forge call, no merge, no
    ledger write."""
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    box.approve(orch, drain=False)
    real = orch.next_ready

    def next_ready():
        ready = real()
        if ready is not None:
            ready.status = "failed"             # an ending landing after the dequeue
        return ready

    monkeypatch.setattr(orch, "next_ready", next_ready)
    calls = (box.store / "calls.log").read_text()
    ledger = eh.read_text(run.ledger().path)
    logged = len(box.log(run))
    said = len(box.out.getvalue())
    orch.drain()
    assert box.out.getvalue()[said:] == "REQ-901 is failed: nothing is merged for it\n"
    assert (box.store / "calls.log").read_text() == calls and merged_count(box) == 0
    assert eh.read_text(run.ledger().path) == ledger
    assert box.log(run)[logged:] == []
    assert run.status == "failed"


def test_req719_abort_prints_only_a_well_formed_pr_url(box):
    """REQ-719 BR-2: a blocked run before the gate has no plan, so the PR URL `abort` prints is
    read from the state the model writes. A `prUrl` on another host, one holding a newline or
    another control character, one that is not a string, and a run with no PR at all each
    print no URL; a well-formed one on the run's host does. The printed line stays one line."""
    box.blocked()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    good = run.read_primary_state()["repos"]["widgets"]["prUrl"]
    assert good.startswith("https://mock.forge/acme/widgets/pull/")

    def recorded(repos):
        state = run.read_primary_state()
        if repos is None:
            state.pop("repos", None)
        else:
            state["repos"] = repos
        run.write_primary_state(state)
        return orch._pr_urls(run)

    hostile = [good.replace("mock.forge", "evil.example"), good + "\n", good + "\r\n",
               good.replace("/pull/", "/pull/\n"), good + "\x1b[2J", "\x07" + good,
               good + "\t", 102, [good], {"url": good}, None, ""]
    for value in hostile:
        assert recorded({"widgets": {"prUrl": value}}) == [], repr(value)
    for repos in ({"widgets": {}}, {"widgets": "x"}, {}, "not a map", None):
        assert recorded(repos) == [], repr(repos)
    assert recorded({"widgets": {"prUrl": good}}) == [good]
    recorded({"widgets": {"prUrl": good + "\n"}})
    said = len(box.out.getvalue())
    line = orch.abort(REQ, by="operator")
    assert line == "%s aborted by operator; working copy left at %s, branch %s" % (
        REQ, run.wc, run.doc["branch"])
    assert box.out.getvalue()[said:] == line + "\n"


def test_req719_a_pid_the_os_gave_another_process_does_not_stop_the_drop(box):
    """REQ-719 BR-1, REQ-662 BR-18: a blocked run whose recorded harness and close-out pids are
    alive but are other processes (`same_process` is false) is dropped, and neither process is
    signalled."""
    box.blocked()
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             start_new_session=True)
    try:
        eh.until(lambda: se.process_start(other.pid), what="the other process to start")
        run.exec.update({"pid": other.pid, "pidStart": NOT_ITS_START, "closeOutPid": other.pid,
                         "closeOutPidStart": NOT_ITS_START})
        assert se.pid_alive(other.pid) and not se.same_process(other.pid, NOT_ITS_START)
        signalled = []
        with pytest.MonkeyPatch.context() as mp:
            _recording_signals(mp, signalled)
            orch.abort(REQ, by="operator")
        assert signalled == []
        assert run.status == "failed" and run.exec["abortedFrom"] == "blocked"
        assert other.poll() is None
    finally:
        if other.poll() is None:
            other.kill()
        other.wait()


def test_req719_abort_of_a_stalled_run_records_aborted_from_stalled(box, reaped):
    """REQ-719 BR-19: the kill of a stalled harness records `abortedFrom: stalled` and appends
    one run-outcome line, `failed` / `aborted`."""
    box.req(sleep_first=30)
    orch = reaped(box.start(shared=True))
    run = orch.runs[REQ]
    eh.until(lambda: os.path.exists(run.wc_state_path()), what="the harness to write state")
    run.doc["config"]["stall_minutes"] = 1
    old = time.time() - 120
    os.utime(run.wc_state_path(), (old, old))
    # Idle time runs from the later of the last state write and this launch's start (BUG-291).
    run.exec["launchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(old))
    orch.poll_once()
    assert run.status == "stalled"
    pid = run.exec["pid"]
    orch.abort(REQ, by="operator")
    eh.until(lambda: not se.pid_alive(pid), timeout=10, what="the harness to be gone")
    assert run.status == "failed" and run.exec["abortedFrom"] == "stalled"
    assert se.Run.load(run.path).exec["abortedFrom"] == "stalled"
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes(REQ)] == [
        ("failed", "aborted")]


def test_req719_the_kill_discards_the_token_leaves_the_queue_and_releases_the_hold(
        tmp_path, reaped):
    """REQ-719 BR-2: the kill arm ends a run as the drop does. REQ-902, approved and then blocked
    by a rebase conflict, is answered and its relaunch is killed: any token held for it is
    discarded, it leaves the merge queue, and REQ-903's approval queued behind it is released
    and merges, while REQ-902's PR is never merged."""
    box, orch, second, third, url = _queued_behind_a_conflict(
        tmp_path, after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                                "blockers": None, "sleep_first": 30})
    reaped(orch)
    orch.answer("REQ-902", "the second option")
    eh.until(lambda: len(box.argvs("REQ-902")) == 2, what="the relaunch to start")
    pid = second.exec["pid"]
    assert second.status == "running" and se.same_process(pid, second.exec["pidStart"])
    # What the drop's test holds the kill arm to as well: a token and a queue entry for it.
    orch.tokens["REQ-902"] = {"approve": el.token_digest(el.mint_token()), "gate": None}
    orch.queue.insert(0, "REQ-902")
    assert third.doc["holdBehind"] == "REQ-902"
    line = orch.abort("REQ-902", by="operator")
    eh.until(lambda: not se.pid_alive(pid), timeout=10, what="the relaunched harness to be gone")
    assert line == _aborted_line(second, [url])
    assert second.status == "failed" and second.exec["abortedFrom"] == "running"
    assert "REQ-902" not in orch.tokens and orch.queue == ["REQ-903"]
    assert third.doc["holdBehind"] is None and se.Run.load(third.path).doc["holdBehind"] is None
    orch.drain()
    assert third.status == "merged"
    assert url not in [c["argv"][0] for c in box.calls("pr_merge")]
