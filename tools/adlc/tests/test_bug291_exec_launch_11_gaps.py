"""BUG-291: the three gaps one answered Codex launch found (`codex-exec-manual.md`, launch 11).

Fact 13: a `git add … && git commit …` at the end of a line that began with `git show … | rg …`
ran in the sandbox, Git could not create its index lock, and the session reported a blocker
without running the two alone. Fact 14: after the operator's `answer` the relaunched run read
`stalled` on its first poll, its idle time the operator's wait. Fact 15: the relaunched session
ran the draft-PR fence again and the mock forge opened a second PR, which cost the run at the
gate.

No test here launches a real harness. The fake is scripted: it shows what the engine, the
fence and the mock do, never what a model does after reading the new note.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_helpers as eh  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import sprint_exec as se  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
REQ = "REQ-901"
SETUP = "proceed/phase-0-setup.md"
#: The note's sentences, each a claim a session acts on.
SENTENCES = (
    "A `git add` or a `git commit` chained after another command can run inside the harness's "
    "sandbox, where Git cannot write its index.",
    "It then fails with `index.lock` and `Operation not permitted`, and that command changed "
    "nothing.",
    "That is the sandbox and not a blocker: run `git add <paths>` on a line of its own, then "
    "`git commit` on a line of its own, and go on.",
    "Report a blocker only if one of them fails that way when run alone.",
)
#: Git's own words in launch 11, for a linked worktree's index.
GIT_SAID = ("Unable to create '/abs/widgets/.git/worktrees/REQ-900/index.lock': Operation not "
            "permitted")
#: A command that fails as launch 11's chained line did: Git's line, exit 128.
LOCKED = "echo \"fatal: %s\"; exit 128" % GIT_SAID
#: What launch 11's session said had stopped it.
ACCOUNT = ("Terminal state: blocked\n\nPhase 4 is implemented and its tests pass, but the commit "
           "could not be made: Git could not create `index.lock` (Operation not permitted).")
BLOCKER = {"phase": 4, "reason": "commit-permission",
           "detail": "Git could not create index.lock: Operation not permitted"}
#: A relaunch that reaches the gate: the second session needs a change of its own to commit.
TO_THE_GATE = {"status": "awaiting_approval", "claim": "awaiting_approval", "sid": "session-two",
               "blockers": None, "text": None, "files": {"z.txt": "z\n"}}


def _folded(text):
    return " ".join(text.split())


def test_bug291_every_exec_prompt_says_what_a_sandboxed_git_write_means():
    """The note follows the refused-line note in the exec notes, so the pipeline prompt of
    every exec adapter holds it once, and so does the close-out's, whose session commits too.
    A solo `/proceed` reads neither: it has no sandbox that a chained line can fall into. The
    note holds no token either scan refuses."""
    assert ep.SANDBOXED_GIT_NOTE == " ".join(SENTENCES) + "\n"
    assert ep._EXEC_NOTES.endswith(ep.REFUSED_LINE_NOTE + ep.SANDBOXED_GIT_NOTE)
    assert ep.scan(ep.SANDBOXED_GIT_NOTE) == []
    assert ep.scan(ep.SANDBOXED_GIT_NOTE, "close-out") == []
    for rel in ep.PIPELINE_SOURCES + ("proceed/SKILL.md",):
        with open(os.path.join(TOOLKIT, rel), encoding="utf-8") as fh:
            assert SENTENCES[2] not in _folded(fh.read()), rel
    adapters = [None] + list(fc.exec_adapters(TOOLKIT))
    assert {a.name for a in adapters[1:]} >= {"claude", "codex"}
    for adapter in adapters:
        name = getattr(adapter, "name", None)
        prompt = ep.pipeline_prompt(
            TOOLKIT, TOOLKIT, REQ, "feat/REQ-901-thing", "/abs/repo",
            "/abs/repo/.worktrees/REQ-901", adapter=adapter).decode("utf-8")
        assert prompt.count(ep.SANDBOXED_GIT_NOTE) == 1, name
        assert prompt.index(ep.REFUSED_LINE_NOTE) < prompt.index(ep.SANDBOXED_GIT_NOTE), name
        close = ep.closeout_prompt(TOOLKIT, REQ, "chore/REQ-901-close-out", "/abs/repo/co",
                                   "EVIDENCE", "", adapter=adapter).decode("utf-8")
        assert close.count(ep.SANDBOXED_GIT_NOTE) == 1, name
        assert close.index(ep.SANDBOXED_GIT_NOTE) < close.index("--- RUN EVIDENCE ---"), name


def _lock_notes(run):
    return [n for n in run.doc.get("notes", []) if "the session's log holds Git's" in n]


def test_bug291_a_blocked_run_whose_log_holds_gits_lock_error_names_the_way_out(tmp_path):
    """On the shipped Codex block the fake session's command fails as launch 11's chained line
    did, and the session ends `blocked` on an account of its own. The run is still `blocked`,
    class `ok`, reason `other`: the account is accurate about the error, and the engine does
    not second-guess it. What the row gains is what the error usually is and that an `answer`
    is enough, so the operator need not work it out. A session that met the same line and went
    on to the gate gets no note. The answer relaunches the run to the gate."""
    box = eh.adapter_sandbox(tmp_path, "codex", reqs=("REQ-901", "REQ-902", "REQ-903"))
    box.req("REQ-901", commands=[LOCKED], status="blocked", claim="blocked", blockers=[BLOCKER],
            text=ACCOUNT, after_answer=dict(TO_THE_GATE, commands=[]))
    box.req("REQ-902", commands=[LOCKED])
    box.req("REQ-903", commands=[LOCKED], status="failed", claim="failed",
            text="Terminal state: failed\n\nGit could not create `index.lock`.")
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert GIT_SAID in eh.read_text(run.file("stdout.json"))
    assert (run.status, run.exec["exitClass"], run.exec["exitCode"]) == ("blocked", "ok", 0)
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes("REQ-901")] == \
        [("blocked", "other")]
    notes = _lock_notes(run)
    assert len(notes) == 1, run.doc.get("notes")
    assert notes[0].startswith("launch 1: the session's log holds Git's"), notes
    assert GIT_SAID in notes[0], notes
    assert "runs in the harness's sandbox" in notes[0] and "an `answer`" in notes[0], notes
    assert "each on a line of its own" in notes[0], notes
    row = se.render_row(run)
    assert "  note: %s" % notes[0] in row
    assert any("commit-permission" in line for line in row)
    # A lock error the session got past is not news at the gate.
    gate = orch.runs["REQ-902"]
    assert gate.status == "awaiting_approval" and _lock_notes(gate) == []
    # A `failed` the session claims is read the same way as a `blocked`.
    failed = orch.runs["REQ-903"]
    assert failed.status == "failed" and len(_lock_notes(failed)) == 1
    # The way out the row names.
    orch.answer("REQ-901", "run `git add` and then `git commit`, each on a line of its own")
    box.wait(orch)
    assert run.status == "awaiting_approval" and run.exec["sessionId"] == "session-two"
    assert len(_lock_notes(run)) == 1


def test_bug291_a_harness_with_no_sandbox_gets_no_such_note(tmp_path):
    """Claude's adapter declares no sandbox for an unmatched command, so the engine has no
    reason to give for a lock error there: a session whose report quotes Git's line is shown
    as it reports itself."""
    box = eh.adapter_sandbox(tmp_path, "claude")
    box.req(status="blocked", claim="blocked", blockers=[BLOCKER],
            text=ACCOUNT + "\n\nfatal: %s" % GIT_SAID)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked" and GIT_SAID in eh.read_text(run.file("stdout.json"))
    assert _lock_notes(run) == []


def test_bug291_a_relaunched_run_is_not_stalled_by_the_wait_for_its_operator(tmp_path):
    """A run blocks, and its operator answers two hours later. The working copy's state file
    was last written when the run blocked, so measured from that file alone the relaunched
    session reads `stalled` on the first poll, with the operator's wait as its idle time.
    Idleness is measured from the later of the state file's mtime and the current launch's
    start: the relaunch reads `running`, and reads `stalled` once its own launch is that old.
    `startedAt` stays the run's first start."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    box.blocked(after_answer=dict(TO_THE_GATE, sleep_first=30))
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    run.doc["config"]["stall_minutes"] = 20
    started = run.exec["startedAt"]
    old = time.time() - 7200
    os.utime(run.wc_state_path(), (old, old))
    orch.answer(REQ, "go on")
    # The fake writes state as it starts, which a real session does not: put the file back to
    # when the run blocked, as launch 11's was on the first poll after its answer.
    eh.until(lambda: os.stat(run.wc_state_path()).st_mtime > old + 60,
             what="the relaunched harness to start")
    os.utime(run.wc_state_path(), (old, old))
    try:
        orch.poll_once()
        assert run.status == "running", box.out.getvalue()
        assert "stalled" not in box.out.getvalue()
        assert run.exec["startedAt"] == started and run.exec["launchedAt"] >= started
        # A relaunch that is itself idle past the limit still stalls.
        run.exec["launchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(old))
        orch.poll_once()
        assert run.status == "stalled"
        assert "%s stalled: no state write for 120 minutes" % REQ in box.out.getvalue()
        # And a state write ends the stall, as before.
        os.utime(run.wc_state_path(), None)
        orch.poll_once()
        assert run.status == "running"
    finally:
        orch.abort(REQ, by="operator")


def _outputs(run, name):
    """The output of each command the jsonl fake reports having run in one launch."""
    with open(run.file(name), encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh if line.strip()]
    return [e["item"]["aggregated_output"] for e in events
            if e.get("type") == "item.completed"
            and e["item"].get("type") == "command_execution"]


def test_bug291_the_draft_pr_fence_run_twice_opens_one_pr(tmp_path):
    """On the shipped Codex block the fake session runs Step 0's draft-PR fence through the
    fence runner, as launch 11's did, and ends `blocked`. After the operator's `answer` the
    relaunched session runs the same fence again, as one that read `prNumber: null` does. The
    fence finds the open PR of the branch into its base and prints that one, marked
    `pr_exists=1`; the forge is asked to create a PR once; and the run reaches the gate, where
    the engine finds one open PR."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    records = fc.census(box.toolkit, box.adapter())
    fence_id = next(r["id"] for r in records if r["id"].startswith(SETUP + "#7:"))
    runner = os.path.join(os.path.realpath(str(box.toolkit)), "tools", "adlc", "fence-run")
    draft = ("%s run '%s' --arg repo='acme/widgets' --arg branch=\"$(git branch --show-current)\" "
             "--arg integrationBranch='main' --arg req='%s' --arg title='thing'; echo \"rc=$?\""
             % (runner, fence_id, REQ))
    box.blocked(commands=[draft], after_answer=TO_THE_GATE)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert run.status == "blocked"
    (first,) = _outputs(run, "stdout.json")
    assert first.rstrip().endswith("rc=0") and "number=101" in first, first
    assert "pr_exists" not in first, first
    orch.answer(REQ, "go on")
    box.wait(orch)
    (second,) = _outputs(run, "stdout.2.json")
    assert second.rstrip().endswith("rc=0"), second
    assert second.splitlines()[:4] == ["url=https://mock.forge/acme/widgets/pull/101",
                                       "number=101", "state=OPEN", "pr_exists=1"], second
    assert len(box.calls("pr_create")) == 1, box.calls("pr_create")
    prs = json.loads((box.store / "prs.json").read_text())["prs"]
    assert [(p["number"], p["state"]) for p in prs] == [(101, "OPEN")]
    assert run.status == "awaiting_approval", run.doc.get("notes")


def _fence_text():
    """Step 0's draft-PR fence as `proceed/phase-0-setup.md` holds it, the text every engine
    reads."""
    with open(os.path.join(TOOLKIT, SETUP), encoding="utf-8") as fh:
        fences = fc.fences(fh.read(), SETUP)
    (fence,) = [f for f in fences if "adlc_forge_pr_create" in f.code]
    return fence.code


def _mock(store, *args, provider="github"):
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_FORGE_MOCK_STORE=str(store),
               ADLC_FORGE_MOCK_PROVIDER=provider)
    env.pop("ADLC_FORGE_MOCK_SCENARIO", None)
    return subprocess.run([sys.executable, os.path.join(TOOLKIT, "tools", "adlc", "forge_mock.py")]
                          + list(args), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)


def _store(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    (store / "config.json").write_text(json.dumps({"remote": "", "owner": "acme",
                                                   "name": "widgets"}))
    return store


def _classify(raw):
    """The class `partials/forge.sh` gives a backend's stderr."""
    script = '. "$1/partials/forge.sh"; _adlc_forge_classify "$2"'
    return subprocess.run(["sh", "-c", script, "sh", TOOLKIT, raw], stdout=subprocess.PIPE,
                          universal_newlines=True, check=True).stdout.strip()


def test_bug291_the_mock_refuses_a_second_open_pr_for_one_head_and_base(tmp_path):
    """GitHub refuses a second open PR for the same head and base, and so does Azure DevOps.
    The mock used to open one, which is how a session that ran the fence twice got a second PR
    and no error (LESSON-891: a double no kinder than the real service). The refusal carries
    the class the adapter gives the forge's own words. Another base, or the same pair once the
    first PR is no longer open, still opens."""
    store = _store(tmp_path)
    make = ["pr_create", "--draft", "--base", "main", "--head", "feat/x", "--title", "t",
            "--body", "b"]
    assert _mock(store, *make).stdout.splitlines()[:2] == [
        "url=https://mock.forge/acme/widgets/pull/101", "number=101"]
    again = _mock(store, *make)
    assert again.returncode == 1
    said = 'a pull request for branch "feat/x" into branch "main" already exists:'
    assert again.stdout.splitlines() == [
        "error_class=network", "raw=%s" % said,
        "raw=https://mock.forge/acme/widgets/pull/101"]
    assert _classify("%s\nhttps://github.com/acme/widgets/pull/101" % said) == "network"
    other = _mock(store, "pr_create", "--base", "develop", "--head", "feat/x", "--title", "t",
                  "--body", "b")
    assert other.returncode == 0 and "number=102" in other.stdout
    doc = json.loads((store / "prs.json").read_text())
    doc["prs"][0]["state"] = "CLOSED"
    (store / "prs.json").write_text(json.dumps(doc))
    assert "number=103" in _mock(store, *make).stdout
    # Azure DevOps says it in its own words, which the adapter classes the same way.
    other = tmp_path / "ado"
    other.mkdir()
    ado = _store(other)
    assert _mock(ado, *make, provider="azure-devops").returncode == 0
    refused = _mock(ado, *make, provider="azure-devops")
    assert refused.returncode == 1 and refused.stdout.splitlines() == [
        "error_class=network",
        "raw=TF401179: An active pull request for the source and target branch already exists."]
    assert _classify(refused.stdout.splitlines()[1][4:]) == "network"


def test_bug291_the_mock_lists_by_base_and_prints_what_the_fence_asks_for(tmp_path):
    """The fence's read: `--head`, `--base`, `--state open`, and a `--jq` program that prints
    each PR as `url=`, `number=` and `state=OPEN` lines. The mock models that one program
    shape; `gh` runs it for real. On Azure DevOps the adapter's list ignores `--jq` and prints
    its JSON rows, so the mock does too."""
    store = _store(tmp_path)
    for base in ("main", "develop"):
        _mock(store, "pr_create", "--base", base, "--head", "feat/x", "--title", "t",
              "--body", "b")
    program = '.[] | "url=\\(.url)\\nnumber=\\(.number)\\nstate=OPEN"'
    assert program in _fence_text()
    read = ["pr_list", "-R", "acme/widgets", "--head", "feat/x", "--base", "develop", "--state",
            "open", "--json", "number,url", "--jq", program]
    assert _mock(store, *read).stdout.splitlines() == [
        "url=https://mock.forge/acme/widgets/pull/102", "number=102", "state=OPEN"]
    read[read.index("develop")] = "release"
    assert _mock(store, *read).stdout == ""
    read[read.index("release")] = "main"
    rows = json.loads(_mock(store, *read, provider="azure-devops").stdout)
    assert [r["number"] for r in rows] == [101]


def _run_fence(tmp_path, store, provider):
    """The fence as a solo session runs it: the body, its placeholders filled in, in a
    directory with no vendored partials and a throwaway HOME."""
    code = _fence_text()
    for key, value in (("<owner/repo>", "acme/widgets"), ("<branch-name>", "feat/REQ-901-thing"),
                       ("<integration-branch>", "main"), ("REQ-xxx", REQ),
                       ("<short title>", "thing")):
        code = code.replace(key, value)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "CLAUDE_PLUGIN_ROOT": TOOLKIT,
           "ADLC_FORGE_MOCK": "1", "ADLC_FORGE_MOCK_STORE": str(store),
           "ADLC_FORGE_MOCK_PROVIDER": provider}
    return subprocess.run(["sh", "-c", code], cwd=str(home), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)


def test_bug291_the_fence_as_a_solo_session_runs_it(tmp_path):
    """The same fence text outside the exec engine. On GitHub's shape the second run prints the
    open PR and creates nothing. Where the read cannot show the PR (the Azure DevOps list
    prints JSON, whatever `--jq` says), the fence goes on to the create, as it always did, and
    the forge's refusal is what the session reads: an error and a non-zero status, never a
    second PR."""
    store = _store(tmp_path)
    first = _run_fence(tmp_path, store, "github")
    assert first.returncode == 0 and "number=101" in first.stdout, first
    assert "pr_exists" not in first.stdout
    second = _run_fence(tmp_path, store, "github")
    assert second.returncode == 0 and second.stdout.splitlines() == [
        "url=https://mock.forge/acme/widgets/pull/101", "number=101", "state=OPEN",
        "pr_exists=1"], second
    assert len(json.loads((store / "prs.json").read_text())["prs"]) == 1
    other = tmp_path / "ado"
    other.mkdir()
    ado = _store(other)
    assert _run_fence(tmp_path, ado, "azure-devops").returncode == 0
    refused = _run_fence(tmp_path, ado, "azure-devops")
    assert refused.returncode != 0, refused
    assert "error_class=network" in refused.stdout and "TF401179" in refused.stdout, refused
    assert "pr_exists" not in refused.stdout
    assert len(json.loads((ado / "prs.json").read_text())["prs"]) == 1


def test_bug291_the_fence_routes_and_the_goldens_hold_it():
    """The fence names only `adlc_forge_pr_list` and `adlc_forge_pr_create`, the two forge
    operations that take no PR, so it stays inside the census's closed shapes: `runner` on
    every exec adapter, untied, and in each adapter's golden as computed."""
    code = _fence_text()
    assert code.index("adlc_forge_pr_list") < code.index("adlc_forge_pr_create")
    assert fc.pr_operation_problems(code) == [] and fc.unmarked_pr_arguments(code) == []
    for adapter in fc.exec_adapters(TOOLKIT):
        (rec,) = [r for r in fc.census(TOOLKIT, adapter) if r["id"].startswith(SETUP + "#7:")]
        assert rec["route"] == "runner" and "tied" not in rec, (adapter.name, rec)
        assert rec["placeholders"] == ["branch", "integrationBranch", "repo", "req", "title"]
        assert "gh pr list" in rec["reach"] and "gh pr create" in rec["reach"], rec
    assert fc.stale_goldens(TOOLKIT) == []
