"""Pre-flight, launch, supervision and the halt (REQ-659)."""

import json
import os
import stat
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
        # BUG-260: the first launch reads no settings file but the engine's own, so a
        # user or project `Bash(git push:*)` cannot widen the tiers.
        assert argv[argv.index("--setting-sources") + 1] == ""
        assert "--strict-mcp-config" in argv
        doc = json.load(open(argv[argv.index("--settings") + 1]))
        assert doc["permissions"]["allow"] == argv[argv.index("--allowedTools") + 1:
                                                   argv.index("--disallowedTools")]
        assert "Bash(git push --force:*)" in doc["permissions"]["deny"]
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



def test_launch_scopes_file_tools(box):
    """BUG-265: the file tools reach the working copy and read the toolkit, nothing else."""
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    argv = json.loads(open(str(box.home / "argv-REQ-901.json")).readline())
    allow = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
    for bare in ("Read", "Write", "Edit", "Glob", "Grep"):
        assert bare not in allow
    assert "Edit(/%s/**)" % run.wc in allow and "Read(/%s/**)" % run.wc in allow
    assert "Read(/%s/**)" % os.path.realpath(orch.toolkit) in allow
    assert [a for a in allow if a.startswith("Edit(")] == ["Edit(/%s/**)" % run.wc]
    doc = json.load(open(argv[argv.index("--settings") + 1]))
    assert doc["permissions"]["allow"] == allow

def test_launch_refused_without_config_isolation(box):
    """BUG-260: a harness that cannot read only the engine's settings would let the
    operator's or the project's allowlist widen the tiers, so nothing launches."""
    box.write_scenario(help="--setting-sources <s>\n--settings <f>\n")
    with pytest.raises(se.Refused, match="config-isolation flags"):
        box.start()
    assert not (box.home / "argv-REQ-901.json").exists()


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


def test_exec_prompt_refused_launches_nothing(box, monkeypatch):
    """REQ-682 BR-8, BR-9: an unrouted fence in the delivered text stops the launch, said as
    `exec_prompt_refused` with the fence and the statement, and no harness process starts."""
    import fence_census as fc
    real = fc.census

    def one_unrouted(root, adapter=None):
        records = [dict(r) for r in real(root, adapter)]
        rec = next(r for r in records if r["id"].startswith("proceed/phase-4-implementation.md#"))
        rec.update(route="unrouted", reason="a fixture fence with no route",
                   refused=["scp .adlc host:/tmp", "no allow matches"])
        return records
    monkeypatch.setattr(fc, "census", one_unrouted)
    with pytest.raises(se.Refused, match="exec_prompt_refused: proceed/phase-4-implementation"):
        box.start(shared=True)
    assert "exec_prompt_refused" in box.out.getvalue()
    assert "scp .adlc host:/tmp" in box.out.getvalue()
    assert not (box.home / "argv-REQ-901.json").exists()


def test_child_env_adds_no_delegation_opt_in(box):
    """REQ-682 BR-11, AC-8: the engine passes nothing that turns delegation on: an opt-in in
    the operator's environment does not reach the child, and the child's opt-out does."""
    orch = box.orch(ADLC_DELEGATE_ENABLED="1", KIMI_API_KEY="k", MOONSHOT_API_KEY="m")
    box.go(orch=orch, shared=True)
    lines = open(str(box.home / "env-raw-REQ-901.txt")).read().splitlines()
    env = dict(line.split("=", 1) for line in lines if "=" in line)
    assert not [k for k in env if k.startswith("ADLC_DELEGATE") or k in ("KIMI_API_KEY",
                                                                         "MOONSHOT_API_KEY")]
    assert env.get("ADLC_DISABLE_DELEGATE") == "1"
    assert "ADLC_DELEGATE_ENABLED" not in orch.adapter(orch.runs["REQ-901"]).block[
        "env_passthrough"]


# ---- REQ-662 ADR-7: launch and resume from the adapter's templates ---------------------------
def _adapter_with(monkeypatch, tmp_path, *swaps):
    """`ea.load` answering with claude's block with each ``(old, new)`` swapped in, read
    through the loader, so the engine meets a block the loader accepts."""
    import exec_adapter as ea
    import harness_adapter as ha
    text = open(os.path.join(eh.TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    for old, new in swaps:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path = tmp_path / "adapter" / "claude.yml"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    loaded = ea.ExecAdapter(ha.load_adapter(str(path), toolkit=eh.TOOLKIT), eh.TOOLKIT)
    monkeypatch.setattr(ea, "load", lambda name, toolkit=None, adapter_path=None: loaded)
    return loaded


def _child_env(box):
    lines = open(str(box.home / "env-raw-REQ-901.txt")).read().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def test_delegate_unsupported_sets_the_env(tmp_path, monkeypatch):
    """REQ-662 BR-10, AC-10: an adapter whose shell timeout cannot hold a delegated read
    launches its fake with ADLC_DISABLE_DELEGATE=1 and nothing from the operator's environment
    beyond its own lists and ADLC_EXEC_RUN; a verified >= 120 s adapter launches without it."""
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    environ = {k: v for k, v in box.environ.items() if k != "ADLC_DISABLE_DELEGATE"}
    orch = box.go(orch=se.Orchestrator(str(box.repo), environ, box.out, eh.TOOLKIT), shared=True)
    assert orch.adapter(orch.runs["REQ-901"]).delegate_supported
    assert "ADLC_DISABLE_DELEGATE" not in _child_env(box)

    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b)
    adapter = _adapter_with(
        monkeypatch, b,
        ("shell_timeout_s: {value: 125, verified: true, delegate: supported}",
         "shell_timeout_s: {value: 60, verified: true, delegate: unsupported}"),
        ("ADLC_HOME, ADLC_DISABLE_DELEGATE, ADLC_FORGE_MOCK", "ADLC_HOME, ADLC_FORGE_MOCK"))
    environ = {k: v for k, v in box.environ.items() if k != "ADLC_DISABLE_DELEGATE"}
    environ["OPERATOR_ONLY"] = "x"
    orch = box.go(orch=se.Orchestrator(str(box.repo), environ, box.out, eh.TOOLKIT), shared=True)
    assert orch.runs["REQ-901"].status == "awaiting_approval"
    env = _child_env(box)
    assert env["ADLC_DISABLE_DELEGATE"] == "1"
    assert "ADLC_DISABLE_DELEGATE" not in adapter.block["env_passthrough"]
    allowed = set(adapter.block["env_passthrough"]) | set(adapter.block["auth_env"]) | {
        "ADLC_EXEC_RUN", "ADLC_DISABLE_DELEGATE"}
    # /bin/sh sets these four itself; the engine passed none of them.
    assert set(env) - allowed <= {"PWD", "OLDPWD", "SHLVL", "_"}
    assert "OPERATOR_ONLY" not in env and "GH_TOKEN" not in env


def test_harness_flag_outside_operator_flags_is_refused(tmp_path):
    """REQ-662 ADR-7: a --harness-flag whose flag `operator_flags` does not name is refused
    before anything starts; one it names launches, with its value, after the template (the
    must-not-refuse case), whether it came from the command line or from the config."""
    a = tmp_path / "a"
    a.mkdir()
    box = eh.Sandbox(a)
    for flags in (["--add-dir", "/"], ["--permission-mode", "acceptEdits"],
                  ["--settings", "/tmp/x.json"], ["--setting-sources", "user"],
                  ["a prompt"]):
        with pytest.raises(se.Refused, match="operator_flags|neither"):
            box.start(shared=True, flags=flags)
        assert not (box.home / "argv-REQ-901.json").exists()
        assert el.run_dirs(box.environ) == []
    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b, config="sprint:\n  exec:\n    harness_flags: [--model, fake-model]\n")
    orch = box.go(shared=True, flags=["--max-turns", "40"])
    assert orch.runs["REQ-901"].status == "awaiting_approval"
    argv = json.loads(open(str(box.home / "argv-REQ-901.json")).readline())
    # The fake records the argv after the binary.
    assert argv[:7] == ["-p", "--output-format", "json", "--model", "fake-model",
                        "--max-turns", "40"]
    assert argv[7] == "--setting-sources"


def test_placeholders_at_the_launch_and_the_close_out(tmp_path, monkeypatch):
    """REQ-662 ADR-6, ADR-7: {worktree} and {last_message} are filled as whole tokens at the
    launch and at the close-out's resume: the working copy each runs in, and a file in the run
    directory (mode 0700), never in a working copy."""
    box = eh.Sandbox(tmp_path)
    _adapter_with(
        monkeypatch, tmp_path,
        ("  launch: [-p, --output-format, json]\n",
         '  launch: [-p, --output-format, json, --cwd, "{worktree}", --last, "{last_message}"]\n'),
        ('  resume: [-p, --output-format, json, --resume, "{session_id}"]\n',
         '  resume: [-p, --output-format, json, --resume, "{session_id}", --cwd, "{worktree}", '
         '--last, "{last_message}"]\n'))
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    argv = json.loads(open(str(box.home / "argv-REQ-901.json")).readline())
    last = run.file("stdout.last-message.txt")
    assert argv[3:7] == ["--cwd", run.wc, "--last", last]     # the argv after the binary
    assert last == run.last_message("stdout.json")
    assert os.path.dirname(last) == run.path
    assert stat.S_IMODE(os.stat(run.path).st_mode) == 0o700
    for spec in run.doc["repos"].values():
        assert not last.startswith(spec["workingCopy"] + os.sep)
    assert box.approve(orch) == "approved"
    assert run.read_primary_state()["closeOut"]["status"] == "ok"
    closeout = json.load(open(str(box.home / "closeout-argv-REQ-901.json")))
    at = closeout.index("--resume")
    assert closeout[at:at + 6] == [
        "--resume", "session-REQ-901", "--cwd", run.doc["closeOutWorkingCopy"], "--last",
        run.file("close-out.last-message.txt")]
    assert closeout[at + 6:at + 8] == ["--setting-sources", ""]


# ---- REQ-662 TASK-269: output by declared format, exit classes, the jsonl fake ----------------
REQS = ("REQ-901", "REQ-902", "REQ-903", "REQ-904", "REQ-905")


def _block(out, req):
    """The lines one REQ's halt printed: its dashboard row through its reject line."""
    text = out.getvalue()
    start = text.index("| %s |" % req)
    return text[start:text.index("/sprint reject %s" % req, start)]


def _logs_outside_the_working_copy(run):
    """REQ-662 AC-6: stdout and stderr are on disk in the run directory, never in a working
    copy."""
    assert os.path.isfile(run.file(run.exec["logPath"]))
    assert os.path.isfile(run.file(run.exec["logPath"].replace(".json", ".stderr.log")))
    for spec in run.doc["repos"].values():
        assert not run.path.startswith(spec["workingCopy"] + os.sep)
        for _root, _dirs, files in os.walk(spec["workingCopy"]):
            for name in files:
                assert not name.endswith((".stderr.log", ".last-message.txt")), name
                assert not name.startswith("stdout"), name


def test_codex_shaped_launch_follows_the_fixture(tmp_path):
    """The launch the engine runs the jsonl fake under today holds the Codex-shaped fixture's
    binary, templates and output, so it cannot drift from the fixture it stands in for."""
    import harness_adapter as ha
    shaped = ha.load_adapter(eh.codex_shaped_adapter(tmp_path), toolkit=eh.TOOLKIT)
    fixture = ha.load_adapter(eh.CODEX_SHAPED_FIXTURE, toolkit=eh.TOOLKIT)
    assert shaped["binary"] == fixture["binary"]
    for key in ("launch", "resume", "output", "prompt_variant"):
        assert shaped["exec"][key] == fixture["exec"][key], key


def test_parse_failures_are_error_with_the_message_in_notes(tmp_path, monkeypatch):
    """REQ-662 BR-6, AC-6: a truncated stream, a cut last line, non-JSON stdout, an empty final
    message and a missing -o file each record `exec.exitClass: error` with the parser's message
    in `notes`, and no `reason` key under `exec`; stdout and stderr are kept in the run
    directory, failures included, and none is in the working copy."""
    box = eh.jsonl_sandbox(tmp_path, monkeypatch, reqs=REQS)
    scripts = {"REQ-901": ({"stream": "no-terminal"}, "no turn.completed event"),
               "REQ-902": ({"stream": "cut"}, "last line is cut"),
               "REQ-903": ({"stream": "not-json"}, "is not JSON"),
               "REQ-904": ({"text": ""}, "final message is empty"),
               "REQ-905": ({"no_last_message": True}, "no last-message file")}
    for req, (script, _words) in scripts.items():
        box.req(req, exit_early=0, **script)
    orch = box.go(shared=True)
    for req, (_script, words) in scripts.items():
        run = orch.runs[req]
        state = run.read_primary_state()
        assert run.exec["exitClass"] == "error" and run.exec["exitCode"] == 0, req
        assert state["exec"]["exitClass"] == "error" and "reason" not in state["exec"], req
        notes = [n for n in state["notes"] if "did not parse" in n]
        assert notes and words in notes[0], (req, state["notes"])
        assert run.status == "failed", req
        _logs_outside_the_working_copy(run)


def test_exit_codes_map_to_classes(tmp_path, monkeypatch):
    """REQ-662 BR-8, AC-7: each declared code lands in pipeline-state.json as its class with the
    raw code; an undeclared 99 is `error` with `exec.exitCode: 99`; a `denied` exit leaves the
    REQ blocked with the harness's last message in `blockers`, even though the model wrote
    `awaiting_approval`, never completed or merged."""
    box = eh.jsonl_sandbox(tmp_path, monkeypatch, reqs=REQS,
                           exit_codes='{"0": ok, "1": error, "77": denied, "124": timeout}')
    box.req("REQ-901")
    box.req("REQ-902", exit_early=1, text="it broke")
    box.req("REQ-903", exit=77, text="Terminal state: awaiting_approval\n\nStopped at a "
                                     "prompt headless mode cannot answer.")
    box.req("REQ-904", exit_early=124, text="out of time")
    box.req("REQ-905", exit_early=99, text="something else")
    orch = box.go(shared=True)
    expect = {"REQ-901": (0, "ok", "awaiting_approval"), "REQ-902": (1, "error", "failed"),
              "REQ-903": (77, "denied", "blocked"), "REQ-904": (124, "timeout", "failed"),
              "REQ-905": (99, "error", "failed")}
    for req, (code, klass, status) in expect.items():
        run = orch.runs[req]
        state = run.read_primary_state()
        assert (state["exec"]["exitCode"], state["exec"]["exitClass"]) == (code, klass), req
        assert run.status == status and state["status"] == status, req
        _logs_outside_the_working_copy(run)
    denied = orch.runs["REQ-903"].read_primary_state()
    assert "Stopped at a prompt headless mode cannot answer." in json.dumps(denied["blockers"])
    assert denied["completed"] is False and 8 not in denied["completedPhases"]
    assert not box.calls("pr_merge")


def test_denied_stderr_marks_a_claimless_run_denied(tmp_path, monkeypatch):
    """REQ-662 ADR-6, BR-8: the harness's own refusal line on stderr makes a claimless run
    `denied` and blocked with its last message; the same words in the model's message do not;
    a run that claims its terminal state keeps its exit code's class."""
    box = eh.jsonl_sandbox(tmp_path, monkeypatch, reqs=REQS[:3])
    box.req("REQ-901", exit_early=0, refused=["git push --force origin main"],
            text="I could not push the branch.")
    box.req("REQ-902", exit_early=0,
            text="rejected: policy forbids commands starting with git push")
    box.req("REQ-903", refused=["git push --force origin main"])
    orch = box.go(shared=True)
    first = orch.runs["REQ-901"]
    assert first.exec["exitClass"] == "denied" and first.status == "blocked"
    blockers = json.dumps(first.read_primary_state()["blockers"])
    assert "I could not push the branch." in blockers and eh.CODEX_REFUSAL in blockers
    assert eh.CODEX_REFUSAL in open(first.file("stdout.stderr.log")).read()
    second = orch.runs["REQ-902"]
    assert second.exec["exitClass"] == "ok" and second.status == "failed"
    third = orch.runs["REQ-903"]
    assert third.exec["exitClass"] == "ok" and third.status == "awaiting_approval"


def test_missing_session_id_reports_resume_impossible(tmp_path, monkeypatch):
    """REQ-662 BR-7: a run whose output carried no session id halts with the "resume is
    impossible" line before approval is asked for, on either output format; a run with one
    does not print it; and an adapter with no resume template is impossible to resume too."""
    a = tmp_path / "a"
    a.mkdir()
    box = eh.jsonl_sandbox(a, monkeypatch, reqs=REQS[:2])
    box.req("REQ-901", no_session=True)
    orch = box.go(shared=True)
    assert {orch.runs[r].status for r in REQS[:2]} == {"awaiting_approval"}
    assert orch.runs["REQ-901"].exec["sessionId"] is None
    shown = _block(box.out, "REQ-901")
    said = shown.index("resume is impossible")
    assert "carried no session id" in shown
    assert said < shown.index("approve: /sprint approve REQ-901")
    assert "resume is impossible" not in _block(box.out, "REQ-902")

    b = tmp_path / "b"
    b.mkdir()
    box = eh.Sandbox(b)
    box.req(no_session=True)
    box.go(shared=True)
    assert "resume is impossible" in _block(box.out, "REQ-901")

    c = tmp_path / "c"
    c.mkdir()
    box = eh.Sandbox(c)
    _adapter_with(monkeypatch, c,
                  ('  resume: [-p, --output-format, json, --resume, "{session_id}"]\n', ""))
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.exec["sessionId"] == "session-REQ-901"
    shown = _block(box.out, "REQ-901")
    assert "declares no resume" in shown and "resume is impossible" in shown
    assert box.approve(orch) == "approved"
    assert "resume is impossible" in run.read_primary_state()["closeOut"]["reason"]


def test_jsonl_launch_resumes_from_the_last_message_file(tmp_path, monkeypatch):
    """REQ-662 ADR-6, ADR-10: through the engine the jsonl fake launches with the Codex-shaped
    argv, halts on the session id `thread.started` carried and the -o file's message, and the
    close-out resumes it with `exec resume` and reads its own -o file."""
    box = eh.jsonl_sandbox(tmp_path, monkeypatch)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval" and run.exec["sessionId"] == "session-REQ-901"
    assert run.doc["finalReport"].startswith("Terminal state: awaiting_approval")
    first = box.launches()[0]
    assert first["installed_as"] == "fake-exec-file" and first["opts"]["json"] is True
    assert first["argv"][:8] == ["exec", "--json", "--sandbox", "workspace-write", "-C", run.wc,
                                 "-o", run.last_message("stdout.json")]
    assert first["cwd"] == run.wc and first["opts"]["resume"] is False
    assert box.approve(orch) == "approved"
    assert run.read_primary_state()["closeOut"]["status"] == "ok"
    resumed = box.launches()[1]
    assert resumed["argv"][:6] == ["exec", "resume", "--json", "-o",
                                   run.file("close-out.last-message.txt"), "session-REQ-901"]
    assert resumed["opts"]["session"] == "session-REQ-901"


def _jsonl_fake(box, *args, prompt="", env=None):
    """The jsonl fake run by hand, as the engine would run it, under the sandbox HOME."""
    full = {"HOME": str(box.home), "PATH": box.environ["PATH"], "ADLC_EXEC_RUN": "REQ-901",
            "LANG": "C"}
    full.update(env or {})
    return subprocess.run([str(box.bin / box.binary)] + list(args), input=prompt,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, cwd=str(box.repo), env=full)


def test_jsonl_fake_records_the_prompt_and_argv(tmp_path):
    """REQ-662 BR-12, ADR-10: installed as `codex`, the fake reads the whole prompt from stdin
    and records its line count, argv and environment; prints its events only under --json
    (LESSON-869); writes the last message to the -o file; honours a scripted exit code and
    stderr; refuses an option codex does not take; and fails the test loudly when launched
    with a forbidden flag."""
    box = eh.Sandbox(tmp_path, harness="codex")
    assert box.binary == "codex" and (box.bin / "codex").exists()
    box.req(exit_early=3, text="Terminal state: blocked", stderr="scripted stderr\n",
            commands=["printf hi"])
    last = tmp_path / "last.txt"
    prompt = "".join("prompt line %d\n" % i for i in range(600))
    argv = ["exec", "--json", "--sandbox", "workspace-write", "-C", str(box.repo), "-o",
            str(last)]
    res = _jsonl_fake(box, *argv, prompt=prompt)
    assert res.returncode == 3 and res.stderr == "scripted stderr\n"
    events = [json.loads(line) for line in res.stdout.splitlines()]
    assert [e["type"] for e in events] == ["thread.started", "item.completed", "turn.completed"]
    assert events[0]["thread_id"] == "session-REQ-901"
    assert events[1]["item"] == {"type": "command_execution", "command": "printf hi",
                                 "aggregated_output": "hi"}
    assert last.read_text() == "Terminal state: blocked\n"
    record = box.launches()[0]
    assert record["prompt_lines"] == 600 and record["argv"] == argv
    assert record["installed_as"] == "codex" and record["opts"]["sandbox"] == "workspace-write"
    assert record["opts"]["cd"] == str(box.repo) and record["opts"]["last"] == str(last)
    assert record["env"]["HOME"] == str(box.home) and "EXEC_FAKE_AS" not in record["env"]
    assert (box.home / "env-raw-REQ-901.txt").exists()
    assert (box.home / "prompt-REQ-901.txt").read_text() == prompt
    # Without --json the real CLI prints plain text and its session id on stderr.
    plain = _jsonl_fake(box, *[a for a in argv if a != "--json"], prompt="x\n")
    assert plain.stdout == "Terminal state: blocked\n" and "session id:" in plain.stderr
    # An option codex does not take is a usage error, and resume takes no --sandbox or -C.
    for bad in (argv + ["--allowedTools", "Bash(ls:*)"],
                ["exec", "resume", "--json", "-C", str(box.repo), "S-1", "-"],
                ["run", "--json"], argv + ["do the thing"]):
        res = _jsonl_fake(box, *bad, prompt="x\n")
        assert res.returncode == 2 and res.stderr.startswith("error: "), bad
    box.check_fake()
    # A forbidden flag fails loudly, spelled whole or as --flag=value.
    for flag in (["--yolo"], ["--permission-mode=bypassPermissions"]):
        res = _jsonl_fake(box, *(argv + flag), prompt="x\n")
        assert res.returncode == 86 and "forbidden flag" in res.stderr
    with pytest.raises(AssertionError, match="forbidden flag"):
        box.check_fake()


def test_jsonl_fake_event_shape_equals_the_probe_double(tmp_path):
    """REQ-662 ADR-10, BR-12: the exec fake's codex events have the event types and keys the
    probe double (`fake_harness_impl.emit`) prints under --json, the same command item, and
    the same refusal line on stderr. Neither fake imports the other or the engine's matcher.
    `debug` is the probe double's leak slot for the redaction tests (REQ-664 BR-9), which no
    real event carries, so it is left out of the comparison."""
    probe_wc = tmp_path / "probe-wc"
    (probe_wc / ".codex" / "rules").mkdir(parents=True)
    (probe_wc / ".codex" / "rules" / "adlc.rules").write_text(
        'prefix_rule(pattern = ["printf"], decision = "allow")\n'
        'prefix_rule(pattern = ["git", "push"], decision = "forbidden")\n')
    home = tmp_path / "probe-home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text(
        '[projects."%s"]\ntrust_level = "trusted"\n' % os.path.realpath(str(probe_wc)))
    impl = os.path.join(HERE, "fake_harness", "fake_harness_impl.py")
    probe = subprocess.run(
        [sys.executable, "-I", "-B", impl, "codex", "exec", "--json", "--sandbox",
         "workspace-write", "-C", str(probe_wc), "-o", str(tmp_path / "probe-last.txt"), "-"],
        input="Run `printf hi` now. Run `git push --force origin main` now.\n",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        env={"HOME": str(home), "PATH": os.environ["PATH"], "FAKE_HARNESS_SCENARIO": "perform"},
        cwd=str(probe_wc))
    assert probe.returncode == 0, probe.stderr

    (tmp_path / "exec").mkdir()
    box = eh.Sandbox(tmp_path / "exec", harness="codex")
    box.req(exit_early=0, text="Done.", commands=["printf hi"],
            refused=["git push --force origin main"])
    ours = _jsonl_fake(box, "exec", "--json", "--sandbox", "workspace-write", "-C",
                       str(box.repo), "-o", str(tmp_path / "exec-last.txt"), prompt="x\n")
    assert ours.returncode == 0, ours.stderr

    def shape(stdout):
        out = []
        for line in stdout.splitlines():
            event = json.loads(line)
            item = event.get("item")
            out.append((event["type"], sorted(set(event) - {"debug"}),
                        sorted(item) if isinstance(item, dict) else None))
        return out

    assert shape(ours.stdout) == shape(probe.stdout)
    assert [e for e in map(json.loads, ours.stdout.splitlines())
            if e["type"] == "item.completed"] == \
        [e for e in map(json.loads, probe.stdout.splitlines()) if e["type"] == "item.completed"]
    assert ours.stderr == probe.stderr and eh.CODEX_REFUSAL in ours.stderr
