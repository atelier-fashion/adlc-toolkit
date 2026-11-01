"""Pre-flight, launch, supervision and the halt (REQ-659)."""

import json
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_helpers as eh  # noqa: E402
import exec_ledger as el  # noqa: E402
import exec_prompt as ep  # noqa: E402
import sprint_exec as se  # noqa: E402


@pytest.fixture
def box(tmp_path):
    return eh.Sandbox(tmp_path)


@pytest.fixture
def two(tmp_path):
    return eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))


def test_two_reqs(two):
    orch = two.go(shared=True)
    for req in ("REQ-901", "REQ-902"):
        run = orch.runs[req]
        assert run.status == "awaiting_approval"
        assert run.wc == os.path.join(os.path.realpath(str(two.repo)), ".worktrees", req)
        data = open(run.file("prompt.txt"), encoding="utf-8").read()
        assert "WORKTREE PATH (mandatory): %s\n" % run.wc in data
        delivered = open(str(two.home / ("prompt-%s.txt" % req)), encoding="utf-8").read()
        assert delivered == data
        assert not ep.scan(data, "pipeline")
        argv = json.loads(open(str(two.home / ("argv-%s.json" % req))).readline())
        assert "--allowedTools" in argv and "--disallowedTools" in argv
        assert "--dangerously-skip-permissions" not in argv
        assert "Bash(adlc sprint-exec approve:*)" in argv
        state = run.read_primary_state()
        assert state["status"] == "awaiting_approval" and state["approval"]["action"] == "merge"
        assert 8 not in state["completedPhases"] and state["completed"] is False
        assert not state["repos"]["widgets"].get("merged")
        assert run.doc["finalReport"].startswith("Terminal state: awaiting_approval")
        branch = "feat/%s-thing" % req
        assert run.doc["branch"] == branch
        assert subprocess.call(["git", "-C", str(two.repo), "merge-base", "--is-ancestor",
                                run.doc["branch"], "origin/main"]) == 1
    assert len(eh.git(two.bare, "log", "--format=%H", "main").split()) == 1
    assert not two.calls("pr_merge")
    assert os.path.isdir(orch.runs["REQ-901"].wc)
    text = two.out.getvalue()
    assert "Awaiting approval" in text and "/sprint reject REQ-902" in text


def test_halt_record(box):
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    plan = run.ledger().read()["plan"]
    assert plan["prs"][0]["number"] == 101 and plan["deployPlan"] is None
    assert plan["changedPaths"] == ["src/REQ-901.txt"]
    assert plan["sharedCredentials"] is True and plan["protection"] == "protected"
    assert run.read_primary_state()["exec"]["promptPath"] == "prompt.txt"
    assert run.path not in json.dumps(run.read_primary_state())


def test_forbidden_flag_refused(tmp_path):
    box = eh.Sandbox(tmp_path, config="sprint:\n  exec:\n    harness_flags: "
                                      "[--dangerously-skip-permissions]\n")
    with pytest.raises(se.Refused, match="--dangerously-skip-permissions.*Rule B"):
        box.start(shared=True)
    assert not (box.home / "argv-REQ-901.json").exists()


def test_forbidden_flag_on_the_cli(box):
    with pytest.raises(se.Refused, match="--yolo"):
        box.start(shared=True, flags=["--yolo"])


def test_engine_selection(box, monkeypatch):
    with pytest.raises(se.Refused, match="REQ-662"):
        box.start(harness="codex", shared=True)
    orch = box.orch(PATH="/usr/bin:/bin")
    with pytest.raises(se.Refused, match="not on PATH"):
        box.start(orch=orch, shared=True)
    with pytest.raises(se.Refused, match="req failed validation"):
        box.start(reqs=["REQ-1; rm"], shared=True)


def test_azure_devops_refused(box):
    orch = box.orch(ADLC_FORGE_MOCK_PROVIDER="azure-devops")
    with pytest.raises(se.Refused, match="azure-devops"):
        box.start(orch=orch, shared=True)


def test_unverified_gitdir_reach_refused(box, monkeypatch, tmp_path):
    orch = box.orch()
    import exec_adapter as ea
    real = ea.load

    def tampered(name, toolkit=None, adapter_path=None):
        loaded = real(name, toolkit, adapter_path)
        loaded.adapter = dict(loaded.adapter, sandbox_can_reach_common_gitdir="unverified")
        return loaded
    monkeypatch.setattr(ea, "load", tampered)
    with pytest.raises(se.Refused, match="sandbox_can_reach_common_gitdir"):
        box.start(orch=orch, shared=True)


def test_sandbox_setting_refused(box, monkeypatch):
    settings = box.repo / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text('{"sandbox": {"enabled": true}}')
    with pytest.raises(se.Refused, match="sandbox is on"):
        box.start(shared=True)


def test_scoped_token_or_shared(box):
    with pytest.raises(se.Refused, match="--shared-credentials"):
        box.start(orch=box.orch(CHILD_GH=""))


def test_child_env_and_denied(box):
    box.req(exit_early=0, denials=[{"tool_name": "Bash"}], text="")
    orch = box.go()
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    assert run.exec["exitClass"] == "denied" and run.exec["exitCode"] == 0
    assert "denied" in json.dumps(run.read_primary_state()["blockers"])
    lines = open(str(box.home / "env-raw-REQ-901.txt")).read().splitlines()
    env = dict(line.split("=", 1) for line in lines if "=" in line)
    assert env["GH_TOKEN"] == "scoped-token"
    assert env["ADLC_EXEC_RUN"] == "REQ-901"
    assert env["GH_CONFIG_DIR"] == run.file("gh-empty") and os.listdir(env["GH_CONFIG_DIR"]) == []
    for name in ("GITHUB_TOKEN", "ADLC_FORGE_MOCK_STORE", "XDG_STATE_HOME", "CHILD_GH"):
        assert name not in env
    adapter = orch.adapter(run)
    allowed = set(adapter.block["env_passthrough"]) | set(adapter.block["auth_env"]) | {
        "ADLC_EXEC_RUN", "GH_TOKEN", "GH_CONFIG_DIR"}
    # /bin/sh sets these four itself; the engine passed none of them.
    assert set(env) - allowed <= {"PWD", "OLDPWD", "SHLVL", "_"}


def test_protection_preflight(tmp_path):
    for value, word in (("protection-no-pr", "unprotected"), ("protection-lookup-fail", "unknown")):
        sub = tmp_path / word
        sub.mkdir()
        box = eh.Sandbox(sub, mock_scenario=value)
        with pytest.raises(se.Refused, match="Rule B") as exc:
            box.start(shared=True)
        assert word in str(exc.value)
        assert not (box.home / "argv-REQ-901.json").exists()
    box = eh.Sandbox(tmp_path, mock_scenario="protection-bypass")
    orch = box.go(shared=True, allow_unprotected=True)
    run = orch.runs["REQ-901"]
    assert run.ledger().read()["plan"]["allowUnprotected"] is True
    assert "WARNING" in box.out.getvalue() and "Rule B" in box.out.getvalue()
    assert "allowUnprotected" in box.out.getvalue()


def test_protection_config_off(tmp_path):
    box = eh.Sandbox(tmp_path, mock_scenario="protection-no-pr", config=(
        "sprint:\n  exec:\n    child_gh_token: CHILD_GH\n    require_branch_protection: false\n"))
    orch = box.go()
    assert orch.runs["REQ-901"].status == "awaiting_approval"
    assert "WARNING" in box.out.getvalue()


def test_frozen_config(box):
    orch = box.start(shared=True)
    (box.repo / ".adlc" / "config.yml").write_text("sprint:\n  exec:\n    stall_minutes: 1\n")
    box.wait(orch)
    assert orch.runs["REQ-901"].doc["config"]["stall_minutes"] == 20


def test_exit_classification(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    box.req(exit_early=1, is_error=True, text="it broke")
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "failed" and run.exec["exitClass"] == "error"
    assert "it broke" in json.dumps(run.read_primary_state()["notes"])

    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b)
    box.req(claim="merged")
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    assert "claimed merged" in "\n".join(se.violations_of(run))
    assert se.PROTOCOL in box.out.getvalue()

    c = tmp_path / "c"
    c.mkdir()
    box = eh.Sandbox(c)
    box.req(claim="merged", status=None)
    orch = box.go(shared=True)
    assert orch.runs["REQ-901"].status == "failed"

    d = tmp_path / "d"
    d.mkdir()
    box = eh.Sandbox(d)
    box.req(exit_early=0, text="")
    orch = box.go(shared=True)
    assert orch.runs["REQ-901"].status == "failed", "ok with no terminal claim is failed"


def test_stall(box):
    box.req(sleep_first=5)
    orch = box.start(shared=True)
    run = orch.runs["REQ-901"]
    for _ in range(100):
        if os.path.exists(run.wc_state_path()):
            break
        time.sleep(0.05)
    run.doc["config"]["stall_minutes"] = 1
    old = time.time() - 120
    os.utime(run.wc_state_path(), (old, old))
    orch.poll_once()
    assert run.status == "stalled"
    assert "stalled" in box.out.getvalue() and "pid %s alive" % run.exec["pid"] in box.out.getvalue()
    assert se.pid_alive(run.exec["pid"]), "a stall is flagged, never killed"
    orch.abort("REQ-901", by="operator")
    assert run.status == "failed"


def test_abort(box):
    box.req(sleep_first=30)
    orch = box.start(shared=True)
    run = orch.runs["REQ-901"]
    pid = run.exec["pid"]
    time.sleep(0.2)
    orch.abort("REQ-901", by="operator")
    time.sleep(0.1)
    assert not se.pid_alive(pid)
    assert run.status == "failed" and run.exec["abortedBy"] == "operator"
    assert run.exec["trustRevokedAt"] and os.path.isdir(run.wc)
    with pytest.raises(se.Refused, match="no live process"):
        orch.abort("REQ-901", by="operator")


def test_trust_recorded(box):
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.exec["trustMechanism"] == "none" and run.exec["trustGrantedAt"]
    assert not (box.home / ".claude.json").exists()
    assert "trust_granted" in [r["kind"] for r in box.log(run)]


def test_no_session_id(box):
    box.req(no_session=True)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    assert "resume: impossible" in box.out.getvalue()


def test_state_ownership(box):
    box.req(sleep_first=1)
    orch = box.start(shared=True)
    run = orch.runs["REQ-901"]
    for _ in range(100):
        if os.path.exists(run.wc_state_path()):
            break
        time.sleep(0.02)
    stamp = os.stat(run.wc_state_path()).st_mtime_ns
    orch.poll_once()
    orch.poll_once()
    assert os.stat(run.wc_state_path()).st_mtime_ns == stamp
    box.wait(orch)


def test_direct_push_detection(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    box.req(push_direct=True)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    assert "already an ancestor" in "\n".join(se.violations_of(run))
    assert se.PROTOCOL in json.dumps(run.read_primary_state()["blockers"])

    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b)
    box.req(squash_push=True)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    assert "patch-id" in "\n".join(se.violations_of(run))


def test_first_parent_check(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    box.req(push_unrelated=True)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    head = eh.git(box.bare, "rev-parse", "main").strip()
    assert head in "\n".join(se.violations_of(run))

    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b)
    box.req(push_unrelated=True)
    head_map = box.store / "commit_prs.json"
    orch = box.start(shared=True)
    while "REQ-901" in orch.children:
        if orch.children["REQ-901"].poll() is not None:
            break
        time.sleep(0.05)
    head = eh.git(box.bare, "rev-parse", "main").strip()
    head_map.write_text(json.dumps({head: [55]}))
    box.wait(orch)
    assert orch.runs["REQ-901"].status == "awaiting_approval"


def test_straggler_sweep(box):
    box.req(double_fork=30)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    time.sleep(0.2)
    assert se.stragglers("REQ-901") == []
    assert run.status == "awaiting_approval"


def test_a_straggler_that_survives_is_surfaced(box, monkeypatch):
    monkeypatch.setattr(se, "stragglers", lambda req: [999999])
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    assert "stragglers survived" in json.dumps(run.read_primary_state()["blockers"])


def test_bad_exec_config_is_refused(tmp_path):
    for text, word in (("    child_gh_token: ghp_not-a-name!\n", "NAME of a variable"),
                       ("    allow_extra: [pytest]\n", "argv lists"),
                       ("    surprise: 1\n", "unknown keys")):
        sub = tmp_path / word.split()[0]
        sub.mkdir()
        box = eh.Sandbox(sub, config="sprint:\n  exec:\n" + text)
        with pytest.raises(se.Refused, match=word):
            box.start(shared=True)


def test_a_refused_prepare_leaves_no_run_directory(box):
    eh.git(box.repo, "worktree", "add", "-q", "-b", "other", str(box.repo / ".worktrees" / "REQ-901"))
    with pytest.raises(se.Refused):
        box.start(shared=True)
    assert el.run_dirs(box.environ) == []


def test_unaccounted_ledger_at_the_halt(box):
    box.req(sleep_first=1)
    orch = box.start(shared=True)
    run = orch.runs["REQ-901"]
    with open(run.file(el.LEDGER), "w") as fh:
        fh.write('{"plan": {}, "decision": {"decision": "approved"}}')
    box.wait(orch)
    assert run.status == "blocked"
    assert "does not account" in "\n".join(se.violations_of(run))


def test_cross_repo(tmp_path):
    sib_bare = tmp_path / "acme" / "side.git"
    box = eh.Sandbox(tmp_path, config=(
        "sprint:\n  exec:\n    child_gh_token: CHILD_GH\n"
        "repos:\n  widgets:\n    primary: true\n  side:\n    path: ../side\n"
        "merge_order:\n  - side\n  - widgets\n"))
    subprocess.check_call(["git", "init", "-q", "--bare", "-b", "main", str(sib_bare)])
    side = tmp_path / "side"
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(side)])
    (side / "x.txt").write_text("x\n")
    env = dict(os.environ, HOME=str(box.home))
    for args in (["add", "-A"], ["commit", "-qm", "seed"],
                 ["remote", "add", "origin", str(sib_bare)], ["push", "-q", "origin", "main"]):
        subprocess.check_call(["git", "-C", str(side)] + args, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    box.req(siblings={"side": False})
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    sibling = os.path.join(os.path.realpath(str(side)), ".worktrees", "REQ-901")
    assert run.doc["repos"]["side"]["workingCopy"] == sibling and os.path.isdir(sibling)
    assert run.status == "awaiting_approval" and run.exec["exitClass"] == "ok"
    assert [p["repo"] for p in run.ledger().read()["plan"]["prs"]] == ["widgets"]
    data = open(run.file("prompt.txt"), encoding="utf-8").read()
    assert "leave the working copy in place" in data
    box.approve(orch)
    assert run.status == "merged"
    assert not os.path.exists(sibling), "the orchestrator removes it at cleanup"
    removed = [r for r in box.log(run) if r["kind"] == "git" and "remove" in r["argv"]]
    assert any(sibling in r["argv"] for r in removed)


def test_plan(box):
    box.req(approval={"prs": ["https://evil.example/x/y/pull/1"], "deploy": True})
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    plan = run.ledger().read()["plan"]
    assert plan["prs"][0]["url"] == "https://mock.forge/acme/widgets/pull/101"
    assert plan["deployPlan"] is None
    assert "orchestrator's plan wins" in "\n".join(run.doc["notes"])


def test_plain_shell_verbs(box):
    env = dict(box.environ, PYTHONPATH="")
    env["PATH"] = box.environ["PATH"]
    out = subprocess.run([sys.executable, os.path.join(eh.TOOLKIT, "tools", "adlc", "adlc.py"),
                          "sprint-exec", "status"], cwd=str(box.repo), env=env,
                         stdout=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 0 and "| REQ | Phase |" in out.stdout


def test_worktree_collision_refused(box):
    eh.git(box.repo, "worktree", "add", "-q", "-b", "other", str(box.repo / ".worktrees" / "REQ-901"))
    with pytest.raises(se.Refused, match="worktree path in use"):
        box.start(shared=True)


def test_draft_spec_refused_lite_draft_runs(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    path = box.repo / box.spec_dirs["REQ-901"] / "requirement.md"
    path.write_text(path.read_text().replace("status: approved", "status: draft"))
    eh.git(box.repo, "add", "-A")
    subprocess.check_call(["git", "-C", str(box.repo), "commit", "-qm", "d"],
                          env=dict(os.environ, HOME=str(box.home)))
    subprocess.check_call(["git", "-C", str(box.repo), "push", "-q", "origin", "main"])
    with pytest.raises(se.Refused, match="not approved"):
        box.start(shared=True)
