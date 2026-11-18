"""Pre-flight, launch, supervision and the halt (REQ-659)."""

import hashlib
import json
import os
import signal
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
        box.start(harness="copilot", shared=True)
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


def _local_config(root, key):
    """``key`` in the repository's own git config, or None when it is unset."""
    res = subprocess.run(["git", "-C", str(root), "config", "--local", "--get", key],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return res.stdout.strip() if res.returncode == 0 else None


def test_preflight_needs_worktree_config(tmp_path, monkeypatch):
    """REQ-662 BR-17, AC-20: a file-rendering adapter hides its untracked renders through
    `git config --worktree`, so the pre-flight refuses when extensions.worktreeConfig is
    unavailable, naming it and launching nothing: a git too old for it, a config that sets it
    false, one that sets core.worktree (enabling it would make every working copy read that),
    and a write git refuses. Otherwise it sets it once, says so and leaves it set. A
    flags-only adapter never reaches the check (BR-1)."""
    import exec_surfaces as esf
    (tmp_path / "claude").mkdir()
    claude = eh.Sandbox(tmp_path / "claude")
    claude.orch().preflight(claude.reqs, shared=True)
    assert _local_config(claude.repo, esf.WORKTREE_CONFIG) is None
    box = eh.file_sandbox(tmp_path / "file", monkeypatch)
    key = "extensions.worktreeConfig"

    def refused(match):
        with pytest.raises(se.Refused, match=match) as caught:
            box.orch().preflight(box.reqs, harness=box.harness, shared=True)
        assert key in str(caught.value) and "nothing is launched" in str(caught.value)
        assert _local_config(box.repo, key) in (None, "false") and not box.launches()

    floor = esf.WORKTREE_CONFIG_GIT
    monkeypatch.setattr(esf, "WORKTREE_CONFIG_GIT", (99, 0))
    refused(r"needs git 99\.0 or newer")
    monkeypatch.setattr(esf, "WORKTREE_CONFIG_GIT", floor)
    lock = box.repo / ".git" / "config.lock"
    lock.write_text("")
    refused(r"enabling extensions\.worktreeConfig in .* was refused")
    lock.unlink()
    eh.git(box.repo, "config", key, "false")
    refused(r"extensions\.worktreeConfig is false")
    eh.git(box.repo, "config", "--unset", key)
    eh.git(box.repo, "config", "core.worktree", os.path.realpath(str(box.repo)))
    refused(r"its git config sets core\.worktree")
    eh.git(box.repo, "config", "--unset", "core.worktree")
    note = "NOTE: set extensions.worktreeConfig = true in "
    batch = box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    assert set(batch.worktree_config.values()) == {"enabled"} and batch.worktree_config
    assert _local_config(box.repo, key) == "true"
    batch = box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    assert set(batch.worktree_config.values()) == {"present"}
    assert box.out.getvalue().count(note) == 1


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
        "ADLC_EXEC_RUN", "ADLC_EXEC_RUN_TAG", "GH_TOKEN", "GH_CONFIG_DIR"}
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
    assert se.stragglers("REQ-901", se.run_tag(run.path)) == []
    assert run.status == "awaiting_approval"


def test_straggler_sweep_is_scoped_to_its_own_run(tmp_path):
    """Two runs of one REQ id on one machine (two projects number alike): the sweep names the
    run's tag beside the id, so it finds its own run's processes and never the other's. The tag
    is a digest: the run directory's path stays out of the child's environment (AC-33)."""
    req = "REQ-977"
    mine, other = str(tmp_path / "run a"), str(tmp_path / "run-b")
    assert se.run_tag(mine) != se.run_tag(other) and mine not in se.run_tag(mine)
    procs = []
    try:
        for run_dir in (mine, other, None):
            env = {"PATH": os.environ["PATH"], "ADLC_EXEC_RUN": req}
            if run_dir:
                env[se.RUN_TAG_ENV] = se.run_tag(run_dir)
            # Not /bin/sleep: ps does not show a platform binary's environment on macOS.
            procs.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                          env=env))
        time.sleep(0.3)
        assert se.stragglers(req, se.run_tag(mine)) == [procs[0].pid]
        assert se.stragglers(req, se.run_tag(other)) == [procs[1].pid]
        assert se.stragglers(req, se.run_tag(mine)[:-1]) == []
        assert sorted(se.stragglers(req)) == sorted(p.pid for p in procs)
    finally:
        for proc in procs:
            proc.kill()
            proc.wait()


def test_a_straggler_that_survives_is_surfaced(box, monkeypatch):
    monkeypatch.setattr(se, "stragglers", lambda req, tag=None: [999999])
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


ENTRY = os.path.join(eh.TOOLKIT, "tools", "adlc", "adlc.py")


def _engine(box, argv, **env):
    """`adlc sprint-exec <argv>` through the engine's own entry point, from an operator's shell
    in the primary repo."""
    return subprocess.run([sys.executable, ENTRY, "sprint-exec"] + argv, cwd=str(box.repo),
                          env=dict(box.environ, PYTHONPATH="", **env), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=120)


def test_nested_launch_is_refused(tmp_path, monkeypatch):
    """REQ-662 BR-18, AC-21: a process the model started runs the engine's own entry point with
    ADLC_EXEC_RUN and its tag scrubbed from its environment: a `run` of a REQ nothing holds, a
    `resume`, and an `approve` of another run, which reaches the supervisor over its socket.
    Each is refused through its pid ancestry, which holds the live exec pid the engine state
    records (for the dispatch, the kernel's peer pid's), names Rule B and is logged
    `nested_launch_refused` in the run it came from. Nothing is launched or decided and no run
    directory is made."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902", "REQ-903"))
    # The engine state under the HOME a harness is given, as on a machine with no
    # XDG_STATE_HOME: a child's environment carries no such variable.
    del box.environ["XDG_STATE_HOME"]
    box.req("REQ-901", nested=[["run", "REQ-903", "--shared-credentials"], ["resume"],
                               ["approve", "REQ-902", "--token", "0" * 32]])
    orch = box.orch()
    monkeypatch.chdir(str(box.repo))            # bind() moves this process into its directory
    server = orch.bind()
    try:
        box.start(["REQ-901", "REQ-902"], orch=orch, shared=True)
        end = time.time() + 120
        while orch.children and time.time() < end:
            orch.poll_once()
            orch.serve_once(server, 0.05)
    finally:
        server.close()
    box.wait(orch)
    run, other = orch.runs["REQ-901"], orch.runs["REQ-902"]
    path = box.home / "nested-REQ-901.jsonl"
    tried = [json.loads(ln) for ln in path.read_text().splitlines()]
    assert [t["argv"][0] for t in tried] == ["run", "resume", "approve"]
    refused = eh.events(box, run, "nested_launch_refused")
    assert len(refused) == 3
    for attempt, detail in zip(tried, refused):
        assert attempt["rc"] == 2 and "Rule B" in attempt["stderr"], attempt
        assert ("nested_launch_refused: %s attempted from inside a run: pid %d descends from the "
                "live exec pid %d of REQ-901" % (attempt["argv"][0], attempt["pid"],
                                                 run.exec["pid"])) in attempt["stderr"], attempt
        assert detail["pid"] == attempt["pid"] and detail["execPid"] == run.exec["pid"]
        assert run.exec["pid"] in detail["ancestry"] and detail["execRun"] is None
    assert [r["argv"] for r in box.log(run) if r["kind"] == "nested_launch_refused"] == [
        ["run"], ["resume"], ["approve"]]
    assert sum("nested_launch_refused" in v for v in se.violations_of(run)) == 3
    assert run.status == other.status == "awaiting_approval"
    assert other.ledger().read()["decision"] is None and "REQ-902" in orch.tokens
    assert el.find_run(str(box.repo), "REQ-903", box.environ) is None
    assert not (box.repo / ".worktrees" / "REQ-903").exists()
    assert sorted(os.listdir(el.exec_root(box.environ))) == sorted(
        os.path.basename(p) for p in (run.path, other.path, orch.sup_dir))


def test_an_operator_launch_is_not_refused_by_another_runs_harness(tmp_path):
    """REQ-662 BR-18, the must-not-refuse half: a shell that descends from no exec pid launches
    through the engine's entry point while another run's harness is alive, on the claude
    adapter as before (BR-1). A recorded exec pid that is dead, or alive in an unrelated
    process that is not an ancestor, refuses nothing; a descendant of that process is
    refused."""
    box = eh.Sandbox(tmp_path, reqs=("REQ-901", "REQ-902"))
    box.req("REQ-901", sleep_first=60)
    orch = box.start(["REQ-901"], shared=True)
    run = orch.runs["REQ-901"]
    assert run.exec["pid"] in orch.live_exec_pids()
    out = tmp_path / "operator.out"
    with open(str(out), "w") as fh:
        sup = subprocess.Popen([sys.executable, ENTRY, "sprint-exec", "run", "REQ-902",
                                "--shared-credentials"], cwd=str(box.repo),
                               env=dict(box.environ, PYTHONPATH=""), stdout=fh,
                               stderr=subprocess.STDOUT)
    try:
        end = time.time() + 120
        while "Awaiting approval" not in out.read_text() and sup.poll() is None \
                and time.time() < end:
            time.sleep(0.1)
    finally:
        sup.terminate()
        sup.wait(timeout=30)
    text = out.read_text()
    assert "REQ-902 launched, pid" in text and "Awaiting approval" in text, text
    assert "refused" not in text and se.pid_alive(run.exec["pid"])
    assert not eh.events(box, run, "nested_launch_refused")
    orch.abort("REQ-901", by="operator")
    assert not se.pid_alive(run.exec["pid"])
    assert box.orch().nested_guard("run", {}, os.getpid()) is None
    # The recorded pid reused by a process that is not this one's ancestor.
    holder = subprocess.Popen(
        [sys.executable, "-c", "import subprocess, sys, time\nchild = subprocess.Popen("
         "[sys.executable, '-c', 'import time; time.sleep(30)'])\nprint(child.pid, flush=True)\n"
         "time.sleep(30)\n"], stdout=subprocess.PIPE, universal_newlines=True,
        start_new_session=True)
    try:
        child = int(holder.stdout.readline())
        record = se.Run.load(run.path)
        record.exec["pid"] = holder.pid
        record.save()
        later = box.orch()
        assert later.live_exec_pids()[holder.pid].req == "REQ-901"
        assert later.nested_guard("run", {}, os.getpid()) is None
        with pytest.raises(se.Refused, match="Rule B.*pid %d descends from the live exec pid %d "
                                             "of REQ-901" % (child, holder.pid)):
            later.nested_guard("run", {}, child)
    finally:
        os.killpg(holder.pid, signal.SIGKILL)
        holder.wait()
        holder.stdout.close()


def test_the_run_tag_refuses_a_launch_a_dispatch_and_a_resume(box):
    """REQ-662 AC-21: with ADLC_EXEC_RUN set, a `run` and a `resume` through the engine's entry
    point, and a dispatched `approve` and `answer`, are each refused naming Rule B and logged
    `nested_launch_refused`, before anything is made or decided."""
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    token, _ = box.tokens("REQ-901")
    root = el.exec_root(box.environ)
    before = sorted(os.listdir(root))
    for argv in (["run", "REQ-901", "--shared-credentials"], ["resume"]):
        res = _engine(box, argv, ADLC_EXEC_RUN="REQ-901")
        assert res.returncode == 2, res.stderr
        assert ("Rule B protocol violation: nested_launch_refused: %s attempted from inside a "
                "run: ADLC_EXEC_RUN=REQ-901 is set" % argv[0]) in res.stderr, res.stderr
    for op in se.LAUNCH_OPS:
        request = {"op": op, "req": "REQ-901", "token": token, "text": "go",
                   "execRun": "REQ-901"}
        with pytest.raises(se.Refused, match="Rule B.*%s attempted from inside a run" % op):
            orch.dispatch(request, os.getpid())
    assert sorted(os.listdir(root)) == before
    assert [r["argv"] for r in box.log(run) if r["kind"] == "nested_launch_refused"] == [
        ["run"], ["resume"], ["approve"], ["answer"]]
    assert all(d["execRun"] == "REQ-901" and d["execPid"] is None
               for d in eh.events(box, run, "nested_launch_refused"))
    assert run.status == "awaiting_approval" and run.ledger().read()["decision"] is None
    assert "REQ-901" in orch.tokens


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
        "ADLC_EXEC_RUN", "ADLC_EXEC_RUN_TAG", "ADLC_DISABLE_DELEGATE"}
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


# ---- REQ-662 BR-11 / BR-18: the verdict at launch, and --allow-unverified --------------------
#: What the fake answers to `--version` once "upgraded": not the adapter's declared version.
UPGRADED = "0.0.0 (an upgraded binary)"


def test_allow_unverified_is_cli_only(tmp_path, monkeypatch):
    """REQ-662 AC-15: the flag reaches the engine from `run`'s command line alone. Config,
    state and the environment do nothing; on the command line it lets every launch on with a
    loud line, and a forbidden flag, a failed pre-flight and the approval gate still stand.
    The adapter is a `verification: probes` block whose result file, under the sandbox
    ToolkitRoot, reads `fail` for fence-vs-allowlist's runner-prefix variant."""
    box = eh.probes_sandbox(tmp_path, monkeypatch, reqs=("REQ-901", "REQ-902"))
    assert box.orch().preflight(box.reqs, harness=box.harness, shared=True).verdict.verified
    box.write_result(eh.with_reading(box.result, "fence-vs-allowlist/runner-prefix", "fail"))
    orch = box.orch(ADLC_ALLOW_UNVERIFIED="1", ALLOW_UNVERIFIED="1",
                    ADLC_SPRINT_EXEC_ALLOW_UNVERIFIED="1")
    with pytest.raises(se.Refused, match="launch is refused.*fence-vs-allowlist"):
        box.start(orch=orch, shared=True)
    config = box.repo / ".adlc" / "config.yml"
    base = config.read_text()
    config.write_text(base + "    allow_unverified: true\n    allow-unverified: true\n")
    with pytest.raises(se.Refused, match="launch is refused.*fence-vs-allowlist"):
        box.start(shared=True)
    config.write_text(base)
    states = [box.repo / box.spec_dirs[req] / "pipeline-state.json" for req in box.reqs]
    for path in states:
        path.write_text(json.dumps({"allowUnverified": True, "allow_unverified": True}))
    with pytest.raises(se.Refused, match="launch is refused.*fence-vs-allowlist"):
        box.start(shared=True)
    for path in states:
        path.unlink()
    assert not box.launches()
    parser = se._parser()
    assert parser.parse_args(["run", "REQ-901", "--allow-unverified"]).allow_unverified is True
    assert parser.parse_args(["run", "REQ-901"]).allow_unverified is False
    for argv in (["approve", "REQ-901", "--allow-unverified"], ["resume", "--allow-unverified"],
                 ["answer", "REQ-901", "--allow-unverified"]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
    # Passed on the command line, it bypasses nothing else.
    with pytest.raises(se.Refused, match="--yolo"):
        box.start(shared=True, flags=["--yolo"], allow_unverified=True)
    box.write_scenario(help="--setting-sources <s>\n--settings <f>\n")
    with pytest.raises(se.Refused, match="config-isolation flags"):
        box.start(shared=True, allow_unverified=True)
    box.write_scenario(help=eh.ISOLATION_HELP)
    assert not box.launches()
    orch = box.go(shared=True, allow_unverified=True)
    text = box.out.getvalue()
    for req in box.reqs:
        assert ("WARNING: --allow-unverified: %s launch on harness fake-exec-file, which is "
                "UNVERIFIED: fence-vs-allowlist\n" % req) in text
        run = orch.runs[req]
        # The approval gate stands: the run halts there and nothing merges.
        assert run.status == "awaiting_approval"
        [entry] = run.ledger().read()["plan"]["allowUnverified"]
        assert entry["invocation"] == orch.invocation and entry["launch"] == "launch"
        assert entry["unverified"] == ["fence-vs-allowlist"]
    assert text.count("WARNING: --allow-unverified:") == 2
    orch.drain()
    assert not box.calls("pr_merge")


def test_recorded_block_launches_under_another_version_and_says_so(box):
    """BR-1: the BR-11 gate, version equality included, is on the probed harnesses. Claude's
    `recorded` block launches under a binary reporting another version, with no
    --allow-unverified, and the pre-flight prints the difference once."""
    import harness_adapter as ha
    declared = ha.load_adapter(os.path.join(eh.TOOLKIT, "harness", "claude.yml"),
                               toolkit=eh.TOOLKIT)["exec"]["harness_version"]
    box.write_scenario(version=UPGRADED)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    text = box.out.getvalue()
    line = ("NOTE: harness claude: recorded for %s, installed reports '%s'; verification: "
            "recorded, so the launch goes on\n" % (declared, UPGRADED))
    assert text.count(line) == 1 and text.count("NOTE: harness") == 1, text
    assert "--allow-unverified" not in text
    assert orch.verdicts["claude"].verified and orch.verdicts["claude"].notes
    assert "allowUnverified" not in run.doc
    assert run.ledger().read()["plan"]["allowUnverified"] == []
    assert box.approve(orch) == "approved"
    assert run.status == "merged" and run.read_primary_state()["closeOut"]["status"] == "ok"


def test_hand_set_status_without_a_result_file_refuses_launch(tmp_path, monkeypatch):
    """REQ-662 AC-11: a `verification: probes` block whose yml says `status: verified`, with
    no result file under ToolkitRoot, is unverified, and nothing launches."""
    import exec_verify as ev
    import harness_adapter as ha
    path = eh.codex_shaped_adapter(tmp_path / "adapter")
    version = ha.load_adapter(path, toolkit=eh.TOOLKIT)["exec"]["harness_version"]
    text = open(path, encoding="utf-8").read()
    old = "  verification: recorded\n"
    assert text.count(old) == 1
    text = text.replace(old, '  verification: probes\n  probes:\n    - id: stdin-prompt\n'
                        '      ran_at: "2026-11-17T00:00:00Z"\n      harness_version: "%s"\n'
                        '      status: pass\n' % version)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    adapter = eh.use_adapter(monkeypatch, path)
    assert adapter.block["status"] == "verified" and adapter.block["verification"] == "probes"
    assert not os.path.exists(ev.result_path(adapter, eh.TOOLKIT))
    box = eh.Sandbox(tmp_path, harness="fake-exec-file", adapter_path=path)
    with pytest.raises(se.Refused, match="unverified.*result-file"):
        box.start(shared=True)
    assert not box.launches()


def test_each_launch_rechecks_the_verdict(tmp_path, monkeypatch):
    """A verdict that changes between the pre-flight and the spawn starts nothing: the result
    file is read again at every launch."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    orch = box.orch()
    batch = orch.preflight(box.reqs, harness=box.harness, shared=True)
    assert batch.verdict.verified and batch.allow_unverified is False
    box.write_result(eh.with_reading(box.result, "stdin-prompt/without-prompt-flag", "fail"))
    orch.launch_batch(box.reqs, batch)
    run = orch.runs["REQ-901"]
    assert run.status == "failed" and not orch.children
    assert not box.launches()
    assert "stdin-prompt" in json.dumps(run.read_primary_state()["notes"])


# ---- REQ-662 BR-3 / BR-4: the fidelity and deny pre-flight -----------------------------------
TEMPLATE = os.path.join(eh.TOOLKIT, "templates", "permissions.yml")


def _template(box, *routine):
    """The sandbox ToolkitRoot's templates/permissions.yml: this toolkit's, with ``routine``
    added as one routine entry. A routine command that extends a deny-tier spelling leaves that
    deny one the harness cannot tell apart from an allow, so it is deny_unsupported."""
    text = open(TEMPLATE, encoding="utf-8").read()
    if routine:
        entry = ("  - id: fixture.extends\n    tier: routine\n    note: a test entry\n"
                 "    commands:\n" + "".join("      - [%s]\n" % ", ".join(c) for c in routine))
        assert text.count("  - id: shell.pwd\n") == 1
        text = text.replace("  - id: shell.pwd\n", entry + "  - id: shell.pwd\n")
    with open(os.path.join(box.toolkit, "templates", "permissions.yml"), "w",
              encoding="utf-8") as fh:
        fh.write(text)


def _rewritten(box, monkeypatch, tmp_path, old, new):
    """The sandbox's adapter with ``old`` replaced by ``new``, loaded in its place."""
    text = open(box.adapter_path, encoding="utf-8").read()
    assert text.count(old) == 1, old
    directory = tmp_path / ("adapter-%d" % len(list(tmp_path.glob("adapter-*"))))
    directory.mkdir()
    path = directory / "fake-exec-file.yml"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return eh.use_adapter(monkeypatch, str(path), box.toolkit)


def _said_since(box, mark):
    return box.out.getvalue()[mark:]


def test_undeclared_exec_loss_refuses_the_preflight(tmp_path, monkeypatch):
    """BR-3, AC-4: the run's allowlist-fidelity findings at `exec` are compared with
    `accepted_fidelity`. Every loss declared, the pre-flight passes (the must-not-refuse case)
    and each run's log carries the report, where `fence.partial-source` reads `inexpressible`.
    One loss undeclared refuses the run, and so does a `widened` verdict declared for the fence,
    which is a loss and not the expected finding."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    batch = box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    assert batch.fidelity and not [ln for ln in batch.fidelity if "undeclared" in ln]
    [fence] = [ln for ln in batch.fidelity if "fence.partial-source" in ln]
    assert " inexpressible — runner: " in fence
    assert batch.exec_files is None    # both tiers are flags on this adapter
    line = '  "git.write:git push": {exec: "inexpressible"}\n'
    _rewritten(box, monkeypatch, tmp_path, line, "")
    with pytest.raises(se.Refused, match=r"accepted_fidelity does not declare at exec: "
                                         r".*git\.write \[git push\] inexpressible"):
        box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    _rewritten(box, monkeypatch, tmp_path, "fence.partial-source: {project: inexpressible, "
               "exec: inexpressible}", 'fence.partial-source: {project: inexpressible, exec: '
               '"widened:if [ -f .adlc/partials/"}')
    with pytest.raises(se.Refused, match=r"accepted_fidelity.*fence\.partial-source"):
        box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    assert not box.launches()
    eh.use_adapter(monkeypatch, box.adapter_path, box.toolkit)
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    [row] = [r for r in box.log(run) if r["kind"] == "fidelity_report"]
    assert row["argv"] == batch.fidelity
    assert not [r for r in box.log(run) if r["kind"] == "deny_unsupported"]
    assert "deny_unsupported" not in box.out.getvalue()


def test_deny_unsupported_preflight(tmp_path, monkeypatch):
    """BR-4, AC-14, AC-16: a deny-tier entry the harness cannot spell is `deny_unsupported`:
    a loud pre-flight line always, and in each run's log. One that is a local destructive move
    (`reset --hard`, `clean -f`, `branch -D`, `rm`, `release`) refuses the run. A
    non-destructive one refuses only when `require_branch_protection` is set and the branch is
    not `protected`, --allow-unprotected or not; with protection, or with the setting off, the
    run goes on."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    for routine, command in ((["git", "reset", "--hard", "HEAD"], "git reset --hard"),
                             (["git", "clean", "-f", "build"], "git clean -f"),
                             (["git", "branch", "-D", "old"], "git branch -D"),
                             (["rm", "-rf", "build"], "rm -rf"),
                             (["gh", "release", "list"], "gh release")):
        _template(box, routine)
        mark = len(box.out.getvalue())
        with pytest.raises(se.Refused, match="local destructive move `%s`" % command):
            box.orch().preflight(box.reqs, harness=box.harness, shared=True)
        said = _said_since(box, mark)
        assert said.count("WARNING: deny_unsupported:") == 1, said
        assert ("WARNING: deny_unsupported: harness fake-exec-file has no deny for `%s` (" %
                command) in said and "a local destructive move" in said
    # A non-destructive entry: `terraform apply` is not on BR-4's list of local destructive
    # moves, so branch protection decides.
    _template(box, ["terraform", "apply", "-help"])
    unprotected = {"ADLC_FORGE_MOCK_SCENARIO": "protection-no-pr"}
    for allow_unprotected in (False, True):
        with pytest.raises(se.Refused, match="require_branch_protection is set.*unprotected.*"
                                             "does not cover a deny_unsupported entry"):
            box.orch(**unprotected).preflight(box.reqs, harness=box.harness, shared=True,
                                              allow_unprotected=allow_unprotected)
    config = box.repo / ".adlc" / "config.yml"
    base = config.read_text()
    config.write_text(base + "    require_branch_protection: false\n")
    batch = box.orch(**unprotected).preflight(box.reqs, harness=box.harness, shared=True)
    assert [(i.entry, i.command, i.destructive) for i in batch.deny_unsupported] == [
        ("terraform", "terraform apply", False)]
    config.write_text(base)
    assert not box.launches()
    mark = len(box.out.getvalue())
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    said = _said_since(box, mark)
    assert ("WARNING: deny_unsupported: harness fake-exec-file has no deny for `terraform apply` "
            "(terraform): its prefix spelling `terraform apply` would also match routine "
            "`terraform apply -help`\n") in said
    rows = [r["argv"] for r in box.log(run) if r["kind"] == "deny_unsupported"]
    assert [row[:2] for row in rows] == [["terraform", "terraform apply"]]
    assert box.launches()


def test_allow_unverified_treats_the_deny_tier_as_unsupported(tmp_path, monkeypatch):
    """BR-4, AC-16: under --allow-unverified with `ask-tier-deny` not `pass`, every deny-tier and
    engine_deny entry is listed as `deny_unsupported` and the run is refused. With
    `ask-tier-deny` passing, an adapter unverified for another reason launches under the flag
    with no deny_unsupported entry (the must-not-fire case)."""
    import harness_adapter as ha
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    perms = ha.load_permissions(TEMPLATE)
    every = [" ".join(c) for e in perms["entries"] if e["tier"] == "deny" for c in e["commands"]]
    loaded = ha.load_adapter(box.adapter_path, toolkit=eh.TOOLKIT)
    every += [" ".join(c) for c in loaded["exec"]["engine_deny"]]
    for reading in ("fail", "unknown"):
        box.write_result(eh.with_reading(box.result, "ask-tier-deny", reading))
        with pytest.raises(se.Refused, match="unverified.*ask-tier-deny"):
            box.orch().preflight(box.reqs, harness=box.harness, shared=True)
        mark = len(box.out.getvalue())
        with pytest.raises(se.Refused, match="every deny-tier entry is deny_unsupported "
                                             r"\(--allow-unverified, and ask-tier-deny reads %s"
                                             % reading):
            box.orch().preflight(box.reqs, harness=box.harness, shared=True,
                                 allow_unverified=True)
        said = _said_since(box, mark)
        assert said.count("WARNING: deny_unsupported:") == len(set(every))
        for command in every:
            assert "has no deny for `%s` (" % command in said, command
    box.write_result(eh.with_reading(box.result, "fence-vs-allowlist/runner-prefix", "fail"))
    mark = len(box.out.getvalue())
    batch = box.orch().preflight(box.reqs, harness=box.harness, shared=True,
                                 allow_unverified=True)
    assert not batch.verdict.verified and batch.deny_unsupported == []
    assert "deny_unsupported" not in _said_since(box, mark)
    assert not box.launches()


def test_unspellable_engine_deny_is_deny_unsupported(tmp_path, monkeypatch):
    """AC-21, BR-4: an `engine_deny` entry the harness cannot spell apart from a routine allow
    raises `deny_unsupported`, a loud line and a row in the run's log, never a silent allow.
    It is not a local destructive move and the branch is protected, so the run goes on."""
    box = eh.probes_sandbox(tmp_path, monkeypatch)
    old = "    - [adlc, sprint-exec, run]\n"
    _rewritten(box, monkeypatch, tmp_path, old, old + "    - [gcloud, run]\n")
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    assert ("WARNING: deny_unsupported: harness fake-exec-file has no deny for `gcloud run` "
            "(exec.engine_deny): its prefix spelling `gcloud run` would also match routine "
            "`gcloud run services list`\n") in box.out.getvalue()
    rows = [r["argv"] for r in box.log(run) if r["kind"] == "deny_unsupported"]
    assert [row[:2] for row in rows] == [["exec.engine_deny", "gcloud run"]]
    # Neither tier carries it: the routine allow it would shadow is the only `gcloud run`.
    argv = box.launches()[0]["argv"]
    assert [tok for tok in argv if "gcloud run" in tok] == ["Bash(gcloud run services list:*)"]


# ---- REQ-662 BR-4, BR-15, AC-25: rule files and config surfaces at launch, exit, halt, resume ---
def _flip(text):
    """``text`` with one byte changed."""
    i = len(text) // 2
    return text[:i] + ("x" if text[i] != "x" else "y") + text[i + 1:]


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _saw(box, req="REQ-901"):
    """What each launch of ``req`` found at the paths its scenario's ``saw`` names."""
    path = box.home / ("saw-%s.jsonl" % req)
    return [json.loads(ln)["saw"] for ln in path.read_text().splitlines()] if path.exists() else []


def _rows(box, run, kind, path=None):
    return [e for e in eh.events(box, run, kind) if path is None or e["path"] == path]


def test_mutated_rule_file_is_rerendered(tmp_path, monkeypatch):
    """BR-4, AC-4: a rendered rule file one byte off is caught by its whole-file checksum at
    the next launch and at the next resume. Each logs `rule_file_rerendered` with
    `checksum_matched: false`, and the harness starts on a file byte-equal to a fresh render.
    A launch over an untouched render logs `checksum_matched: true`, and the untouched run
    reports no config_surface_violation at exit, at the halt or at the close-out (the
    must-not-fire case)."""
    box = eh.file_sandbox(tmp_path, monkeypatch)
    fresh = eh.fresh_files(box).rule_file
    close_fresh = eh.fresh_files(box, "chore/REQ-901-close-out").rule_file
    # The project tracks the rule file one byte off: the first launch's working copy starts
    # from it, and so does the close-out's after the merge, because the run stages only `src`.
    tracked = _flip(fresh)
    eh.commit_on_main(box, {eh.FILE_RULE: tracked})
    box.req(status="blocked", claim="blocked", add=["src"], saw=[eh.FILE_RULE],
            blockers=[{"reason": "reflector-questions", "question": "which?"}],
            closeout={"saw": [eh.FILE_RULE], "add": [".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    rule = os.path.join(run.wc, eh.FILE_RULE)
    want = {"harness": "fake-exec-file", "path": eh.FILE_RULE, "checksum_matched": False,
            "expected": _sha(fresh), "found": _sha(tracked), "where": "launch"}
    assert _rows(box, run, "rule_file_rerendered", eh.FILE_RULE) == [want]
    assert open(rule, encoding="utf-8").read() == fresh
    assert _saw(box)[0][eh.FILE_RULE] == fresh
    # The test changes one byte of the rendered file; the next launch catches it.
    edited = _flip(fresh)
    with open(rule, "w", encoding="utf-8") as fh:
        fh.write(edited)
    box.req(files={"src/two.txt": "two\n"})
    orch.answer("REQ-901", "go on")
    box.wait(orch)
    assert run.status == "blocked"
    rows = _rows(box, run, "rule_file_rerendered", eh.FILE_RULE)
    assert rows[1] == dict(want, found=_sha(edited))
    assert open(rule, encoding="utf-8").read() == fresh and _saw(box)[1][eh.FILE_RULE] == fresh
    # Untouched since: the checksum matches.
    box.req(status="awaiting_approval", claim="awaiting_approval", blockers=None,
            files={"src/three.txt": "three\n"})
    orch.answer("REQ-901", "go on")
    box.wait(orch)
    assert run.status == "awaiting_approval"
    rows = _rows(box, run, "rule_file_rerendered", eh.FILE_RULE)
    assert rows[2] == dict(want, checksum_matched=True, found=_sha(fresh))
    # The resume: the close-out working copy holds the tracked file, one byte off.
    assert box.approve(orch) == "approved"
    assert run.read_primary_state()["closeOut"]["status"] == "ok"
    resumed = [r for r in _rows(box, run, "rule_file_rerendered", eh.FILE_RULE)
               if r["where"] == "resume"]
    assert resumed == [dict(want, where="resume", expected=_sha(close_fresh))]
    assert _saw(box)[-1][eh.FILE_RULE] == close_fresh
    assert box.launches()[-1]["opts"]["resume"] is True
    assert not eh.events(box, run, "config_surface_violation")
    assert "config_surface_violation" not in json.dumps(se.violations_of(run))


def test_surface_edited_mid_run_is_a_violation_at_exit_and_halt(tmp_path, monkeypatch):
    """BR-15, AC-18: a fake that widens the rule file and drops a stray rules file into the
    directory surface mid-run is a `config_surface_violation` at exit; the next launch repairs
    both (`rule_file_rerendered`, false); the same edit in the next run is a violation at exit
    and again at the halt, which the halt row reports as a Rule B protocol violation.
    `rules_reload: unknown` reads as `live`. A file the fake did not touch is not reported."""
    box = eh.file_sandbox(tmp_path, monkeypatch)
    fresh = eh.fresh_files(box).rule_file
    widened = fresh + 'prefix_rule(pattern=["git", "push"], decision="allow")\n'
    stray = ".fake-exec-file/rules/zz-extra.rules"
    edit = {eh.FILE_RULE: widened, stray: 'prefix_rule(pattern=["rm"], decision="allow")\n'}
    box.req(status="blocked", claim="blocked", add=["src"], surface_writes=edit,
            blockers=[{"reason": "reflector-questions", "question": "which?"}])
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    seen = eh.events(box, run, "config_surface_violation")
    assert [(v["path"], v["where"], v["expected"], v["found"]) for v in seen] == [
        (eh.FILE_RULE, "exit", _sha(fresh), _sha(widened)),
        (stray, "exit", None, _sha(edit[stray]))]
    assert all(v["rules_reload"] == "unknown" and v["effective_mid_run"] for v in seen)
    violations = se.violations_of(run)
    assert len(violations) == 2 and all(
        v.startswith("config_surface_violation at exit: ") and "may have taken effect mid-run"
        in v for v in violations)
    # The next launch repairs both before the harness starts; that run makes the same edit
    # and halts, so it is a violation at exit and again at the halt.
    box.req(status="awaiting_approval", claim="awaiting_approval", blockers=None,
            files={"src/two.txt": "two\n"}, saw=[eh.FILE_RULE, stray])
    orch.answer("REQ-901", "go on")
    box.wait(orch)
    assert run.status == "awaiting_approval"
    repaired = [(r["path"], r["checksum_matched"], r["found"])
                for r in _rows(box, run, "rule_file_rerendered") if r["path"] in edit]
    assert repaired[-2:] == [(eh.FILE_RULE, False, _sha(widened)),
                             (stray, False, _sha(edit[stray]))]
    assert _saw(box)[-1] == {eh.FILE_RULE: fresh, stray: None}
    late = eh.events(box, run, "config_surface_violation")[2:]
    assert [(v["path"], v["where"]) for v in late] == [
        (eh.FILE_RULE, "exit"), (stray, "exit"), (eh.FILE_RULE, "halt"), (stray, "halt")]
    halt_row = box.out.getvalue()[box.out.getvalue().rindex("| REQ-901 |"):]
    assert ("Rule B protocol violation: config_surface_violation at halt: %s: expected sha256 "
            "%s, found sha256 %s" % (eh.FILE_RULE, _sha(fresh)[:12], _sha(widened)[:12])
            in halt_row)
    assert eh.FILE_CONFIG not in json.dumps(eh.events(box, run, "config_surface_violation"))


def test_prompt_delivery_renders_the_hook_file_absent(tmp_path, monkeypatch):
    """AC-25, BR-15: under `context_delivery: prompt` the harness's hook file is a surface
    rendered absent. A project that commits one has it removed from the working copy before the
    launch, so the harness starts with no hook file, and the run that leaves it alone reports
    nothing (the must-not-fire case). A hook file the fake writes mid-run is a
    `config_surface_violation` at exit. The prompt begins with ETHOS, and no engine write
    touches the hook-review table in the user config."""
    box = eh.file_sandbox(tmp_path, monkeypatch, reqs=("REQ-901", "REQ-902"))
    hooks = '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "x"}]}]}}\n'
    eh.commit_on_main(box, {eh.FILE_HOOKS: hooks})
    user = box.home / eh.FILE_USER_CONFIG
    user.parent.mkdir(parents=True)
    review = ('model = "fake-mid-1"\n\n[hooks.state."/elsewhere/.fake-exec-file/hooks.json:x"]\n'
              'trusted_hash = "sha256:abc"\n')
    user.write_text(review, encoding="utf-8")
    for req in ("REQ-901", "REQ-902"):
        box.req(req, add=["src"], saw=[eh.FILE_HOOKS])
    box.req("REQ-902", surface_writes={eh.FILE_HOOKS: hooks})
    orch = box.go(shared=True)
    for req in ("REQ-901", "REQ-902"):
        run = orch.runs[req]
        assert run.status == "awaiting_approval"
        assert _saw(box, req) == [{eh.FILE_HOOKS: None}]
        [row] = _rows(box, run, "rule_file_rerendered", eh.FILE_HOOKS)
        assert row == {"harness": "fake-exec-file", "path": eh.FILE_HOOKS,
                       "checksum_matched": False, "expected": None, "found": _sha(hooks),
                       "where": "launch"}
        prompt = open(run.file(run.exec["promptPath"]), encoding="utf-8").read()
        assert prompt.startswith(ep.ethos_text(box.toolkit, str(box.repo)).rstrip("\n"))
    quiet = orch.runs["REQ-901"]
    assert not eh.events(box, quiet, "config_surface_violation")
    assert not os.path.lexists(os.path.join(quiet.wc, eh.FILE_HOOKS))
    loud = orch.runs["REQ-902"]
    assert [(v["path"], v["where"], v["expected"], v["found"])
            for v in eh.events(box, loud, "config_surface_violation")] == [
        (eh.FILE_HOOKS, "exit", None, _sha(hooks)), (eh.FILE_HOOKS, "halt", None, _sha(hooks))]
    assert user.read_text(encoding="utf-8") == review


def test_a_flags_adapter_writes_no_surface(box):
    """BR-1: claude renders both tiers as flags and declares no config surface, no rule file
    and no user policy file, so the engine writes nothing into its working copy or its user
    folder, keeps no surface manifest and logs none of REQ-662 ADR-4's events."""
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval"
    assert "surfaces" not in run.doc and "policyManifest" not in run.doc
    kinds = {r["kind"] for r in box.log(run)}
    assert not kinds & {"rule_file_rerendered", "config_surface_violation", "adapter_refused"}
    tracked = set(eh.git(run.wc, "ls-files").splitlines())
    untracked = eh.git(run.wc, "status", "--porcelain", "--ignored", "--untracked-files=all")
    assert {ln[3:] for ln in untracked.splitlines()} <= {
        ".adlc/specs/REQ-901-thing/pipeline-state.json"}, untracked
    assert "src/REQ-901.txt" in tracked
