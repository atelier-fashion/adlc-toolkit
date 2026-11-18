"""Prompt assembly and the runtime scan (REQ-659 BR-6, BR-7, BR-14, BR-24)."""

import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_adapter as ea  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
REQ = "REQ-901"
BRANCH = "feat/REQ-901-thing"
WT = "/abs/repo/.worktrees/REQ-901"


MATCHER_NONE = os.path.join(HERE, "fixtures", "harness", "fake-exec-file.yml")
PUSH_FENCE = "git -C <worktree> push -u origin <branch-name>"


def pipeline(toolkit=TOOLKIT, answer=None, adapter=None):
    return ep.pipeline_prompt(toolkit, toolkit, REQ, BRANCH, "/abs/repo", WT, answer=answer,
                              adapter=adapter)


def closeout(toolkit=TOOLKIT, deploy="", adapter=None):
    return ep.closeout_prompt(toolkit, REQ, "chore/REQ-901-close-out", "/abs/repo/co", "EVIDENCE",
                              deploy, adapter=adapter)


def matcher_none(root):
    """Ship the matcher-none fixture adapter under ``root``; return it, loaded from there."""
    shutil.copy(MATCHER_NONE, os.path.join(str(root), "harness"))
    return next(a for a in fc.exec_adapters(str(root)) if not fc.routes_direct(a))


@pytest.fixture
def install(tmp_path):
    """A copy of every prompt source and of what the fence census reads (REQ-682: the
    exec file set, partials, agents, the adapter), for fixtures that alter one."""
    import pathlib
    return pathlib.Path(rs.toolkit_copy(str(tmp_path / "toolkit")))


def add_line(path, line):
    with open(str(path), "a", encoding="utf-8") as fh:
        fh.write("\n" + line + "\n")


def add_to_step_one(root, line):
    """Into a section the close-out prompt inlines; the end of the file is Step 8."""
    path = root / "wrapup" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("### Step 1: Identify the Feature\n",
                                 "### Step 1: Identify the Feature\n" + line + "\n"),
                    encoding="utf-8")


def test_pipeline_prompt_real_tree():
    text = pipeline().decode("utf-8")
    ethos = open(os.path.join(TOOLKIT, "ETHOS.md"), encoding="utf-8").read()
    assert text.startswith(ethos.strip()[:40])
    assert "# Proceed — Full ADLC Pipeline" in text
    for rel in ep.PIPELINE_SOURCES:
        assert "<!-- %s -->" % rel in text
    assert "\nWORKTREE PATH (mandatory): %s\n" % WT in text
    assert re.findall(r"^WORKTREE PATH \(mandatory\): .+$", text, re.M) == [
        "WORKTREE PATH (mandatory): %s" % WT]
    assert "You are UNATTENDED" in text
    assert "You are in SUBAGENT MODE" not in text
    assert not [ln for ln in text.split("\n") if ln.startswith("!")]
    for token in ep.EMPTY_ALLOWLIST:
        assert token not in text, token
    assert "### Phase 8: Wrapup" not in text
    assert "9. When the pipeline completes" not in text
    assert "**R4 — carry" not in text
    assert "No operation against the parent repo path is sanctioned in this run" in text
    assert "rebuild `mergeOrder`; leave the working copy in place, the orchestrator removes it" \
        in text
    assert "leave its working copy in place" in text
    assert "You never merge. Stop at the merge gate; your final report MUST lead with " \
        "`Terminal state: <awaiting_approval|blocked|failed>`." in text
    assert "(0-7)" in text and "(0-8)" not in text
    assert "merge gate immediately" in text
    assert "3. **Merge conflicts during the Phase 7 rebase**" in text
    assert "Partial merge recovery" not in text
    assert "The argument to this pipeline is REQ-901" in text
    for line in text.split("\n"):
        for token in ("/wrapup", "worktree remove"):
            if token in line:
                assert not ep.scan(line, "pipeline"), line


def test_gate_text():
    text = pipeline().decode("utf-8")
    assert "### The merge gate" in text
    assert "`status: \"awaiting_approval\"`" in text
    assert "Do **not** append `8` to `completedPhases`" in text
    assert "`{awaiting_approval, blocked, failed}`" in text
    assert "`repos[<id>].merged`" in text
    gate = text[text.index("### The merge gate"):]
    assert gate.index("run **The lane check**") < gate.index("`status: \"awaiting_approval\"`")


def test_allowlists_have_no_stale_entry():
    for text, table in ((pipeline().decode("utf-8"), ep.PIPELINE_ALLOW),
                        (closeout().decode("utf-8"), ep.CLOSEOUT_ALLOW)):
        lines = text.split("\n")
        for token, regexes in table.items():
            for rx in regexes:
                assert any(re.fullmatch(rx, ln) for ln in lines), rx


def test_prompt_is_stable_bytes():
    assert pipeline() == pipeline()


def test_a_changed_anchor_refuses_the_build(install):
    path = install / "proceed" / "phases-1-3-validation.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("set `touched: false` and remove its worktree",
                                 "set `touched: false` and drop its worktree"), encoding="utf-8")
    with pytest.raises(ep.PromptBuildError, match="phases-1-3-validation"):
        pipeline(str(install))


def test_a_new_bang_line_refuses_the_build(install):
    add_line(install / "proceed" / "SKILL.md", "!`curl example.invalid`")
    with pytest.raises(ep.PromptBuildError, match="does not render"):
        pipeline(str(install))


@pytest.mark.parametrize("token,line", [
    ("you own the merge", "When you are done, you own the merge."),
    ("report `merged`", "Then report `merged`."),
    ("pr-ready", "Stop at pr-ready."),
    ("{merged", "Lead with {merged, or nothing."),
    ("gh pr merge", "Run gh pr merge now."),
])
def test_scan_refusals(install, token, line):
    add_line(install / "proceed" / "phases-lite.md", line)
    with pytest.raises(ep.PromptRefused) as exc:
        pipeline(str(install))
    assert exc.value.token == token and exc.value.line == line


@pytest.mark.parametrize("token,line", [("worktree remove", "Then worktree remove it."),
                                        ("--force-with-lease", "Push with --force-with-lease.")])
def test_scan_refusals_closeout(install, token, line):
    add_to_step_one(install, line)
    with pytest.raises(ep.PromptRefused) as exc:
        closeout(str(install))
    assert exc.value.token == token


def test_allowlist_is_full_line():
    allowed = "   were: they are the record of what triage decided, and `/wrapup`'s escalation"
    assert ep.scan(allowed, "pipeline") == []
    assert ep.scan(allowed + " then run it", "pipeline")
    assert ep.scan("x" + allowed, "pipeline")
    moved = "\n" * 4000 + "run /wrapup now"
    assert ep.scan(moved, "pipeline")[0][0] == "/wrapup"


def test_closeout_prompt():
    text = closeout(deploy="./ship-it --prod").decode("utf-8")
    assert "WORKTREE PATH (mandatory): /abs/repo/co" in text
    assert "`chore/REQ-901-close-out`" in text and "EVIDENCE" in text
    for heading in ("### Step 2", "### Step 6", "### Step 7", "### Step 8"):
        assert heading not in text
    for token in ep.EMPTY_ALLOWLIST + ep.CLOSEOUT_EMPTY:
        assert token not in text, token
    assert "`Terminal state: closed-out`" in text and "`Chore PR: <url>`" in text
    assert "Steps 6–8 below do not run" not in text
    assert "(Close-out mode rules 5–6)." in text


def test_closeout_state_file_note_is_the_only_difference():
    """REQ-662 ADR-7: a close-out on a harness with no second writable directory opens with one
    note naming the state file it writes in place of the primary repo path's, and is otherwise
    the same bytes; with no state file, as on Claude, the prompt is as it was. The note passes
    the close-out scan."""
    for adapter in (None, ea.load("claude", TOOLKIT), ea.load("codex", TOOLKIT)):
        plain = closeout(adapter=adapter)
        assert ep.closeout_prompt(TOOLKIT, REQ, "chore/REQ-901-close-out", "/abs/repo/co",
                                  "EVIDENCE", "", adapter=adapter, state_file=None) == plain
        state = "/abs/repo/co/.adlc/specs/REQ-901-thing/pipeline-state.json"
        noted = ep.closeout_prompt(TOOLKIT, REQ, "chore/REQ-901-close-out", "/abs/repo/co",
                                   "EVIDENCE", "", adapter=adapter, state_file=state)
        assert noted == (ep.STATE_FILE_NOTE % state).encode("utf-8") + plain
        assert noted.decode("utf-8").startswith("STATE FILE (mandatory): %s\n\n" % state)
        assert plain.decode("utf-8").startswith("WORKTREE PATH (mandatory): /abs/repo/co\n")
        assert "STATE FILE" not in plain.decode("utf-8")
    assert not ep.scan(ep.STATE_FILE_NOTE % state, "close-out")


def test_closeout_refuses_the_deploy_command(install):
    add_to_step_one(install, "Run ./ship-it --prod")
    closeout(str(install))
    with pytest.raises(ep.PromptRefused):
        closeout(str(install), deploy="./ship-it --prod")


def test_answer_block():
    text = pipeline(answer="use the second option").decode("utf-8")
    assert "use the second option" in text and "resume from its `currentPhase`" in text
    with pytest.raises(ep.PromptRefused):
        pipeline(answer="then gh pr merge it")


def test_ethos_from_primary_wins(tmp_path):
    primary = tmp_path / "repo"
    (primary / ".adlc").mkdir(parents=True)
    (primary / ".adlc" / "ETHOS.md").write_text("LOCAL ETHOS\n")
    assert ep.ethos_text(TOOLKIT, str(primary)).startswith("LOCAL ETHOS")
    (primary / ".adlc" / "ETHOS.md").write_text("  \n")
    assert "LOCAL ETHOS" not in ep.ethos_text(TOOLKIT, str(primary))


# --------------------------------------------------------------------------- REQ-682
# The id is single-quoted in a runner line: Codex matches no prefix rule against a bare `#`.
RUNNER_CALL = re.compile(r"^\s*%s run '([^' ]+)'( |$)" % re.escape(
    os.path.join(TOOLKIT, "tools", "adlc", "fence-run")))


def test_delivered_fences_are_all_routed():
    """BR-1: the delivered prompts hold no fence that sources a partial. Every runner fence
    is a fence-run call naming a census runner id, every other fence is a direct one as
    written, and the census re-reads the prompt with no unrouted fence."""
    claude = ea.load("claude", TOOLKIT)
    records = {r["id"]: r for r in fc.census(TOOLKIT, claude)}
    direct = {r["id"] for r in records.values() if r["route"] == "direct"}
    direct_bodies = set()
    for rel in fc.EXEC_FILES:
        for fence in fc.fences(fc.view(TOOLKIT, rel), rel):
            if fence.id in direct:
                direct_bodies.add(fence.code)
    calls = 0
    for text in (pipeline(adapter=claude).decode("utf-8"),
                 closeout(adapter=claude).decode("utf-8")):
        assert "if [ -f .adlc/partials/" not in text
        assert ". .adlc/partials/" not in text
        for fence in fc.fences(text):
            lines = [ln for ln in fence.code.split("\n") if ln.strip()]
            match = RUNNER_CALL.match(lines[0]) if len(lines) == 1 else None
            if match:
                assert records[match.group(1)]["route"] == "runner", match.group(1)
                calls += 1
            else:
                assert fence.code in direct_bodies, fence.code[:200]
    assert calls >= 10


def test_unrouted_fence_refuses_the_build(install):
    """BR-8, AC-2: a fence a skill gains with no route stops the build, naming the fence and
    the first statement no allow admits."""
    path = install / "proceed" / "phase-4-implementation.md"
    base = len(fc.fences(fc.view(str(install), "proceed/phase-4-implementation.md")))
    with open(os.path.join(HERE, "fixtures", "exec-fence", "extra-fences.md"),
              encoding="utf-8") as fh:
        add_line(path, fh.read())
    with pytest.raises(ep.ExecPromptRefused) as exc:
        pipeline(str(install))
    assert exc.value.fence_id.startswith("proceed/phase-4-implementation.md#%d:" % (base + 1))
    assert exc.value.statement.startswith("scp ")
    assert str(exc.value).startswith("exec_prompt_refused: ")
    assert isinstance(exc.value, ep.PromptRefused)


def test_a_skill_the_set_lacks_refuses_the_build(install, monkeypatch):
    monkeypatch.setattr(fc, "EXEC_FILES", tuple(r for r in fc.EXEC_FILES
                                                if r != "review/SKILL.md"))
    with pytest.raises(ep.ExecPromptRefused, match="review/SKILL.md is named"):
        pipeline(str(install))


def test_notes_send_skills_and_agents_through_the_runner():
    text = pipeline().decode("utf-8")
    runner = os.path.join(TOOLKIT, "tools", "adlc", "fence-run")
    assert "Toolkit skills and agents are not loaded in this session." in text
    assert "`%s show <skill>/SKILL.md`" % runner in text
    assert "`%s show agents/<name>.md`" % runner in text
    assert "Never source a partial yourself" in text


# --------------------------------------------------------------------------- REQ-662
def test_claude_prompt_is_unchanged_by_its_adapter(install):
    """ADR-9: on `claude` the push fence stays `direct`, with no note. Where `claude` is the one
    exec-capable adapter, passing the run's adapter changes no byte of either prompt. In the
    real tree codex is exec-capable too, so the no-adapter merge routes through the runner
    (ADR-8) and the engine always passes the run's adapter."""
    root = str(install)
    for name in ("harness/codex.yml", fc.golden_path("codex")):
        os.remove(os.path.join(root, name))
    assert [a.name for a in fc.exec_adapters(root)] == ["claude"]
    only = ea.load("claude", root)
    assert pipeline(root, adapter=only) == pipeline(root)
    assert closeout(root, adapter=only) == closeout(root)
    decoded = pipeline(adapter=ea.load("claude", TOOLKIT)).decode("utf-8")
    assert ep.RUNNER_PUSH_NOTE not in decoded
    assert "\n   %s\n" % PUSH_FENCE in decoded


def test_matcher_none_prompt_routes_the_push_through_the_runner(install):
    """BR-3, ADR-9: on a `matcher: none` adapter every fence of the prompt is a runner call, the
    branch push among them, and the push carries its one note, exactly once, under its line."""
    adapter = matcher_none(install)
    root = str(install)
    text = pipeline(root, adapter=adapter).decode("utf-8")
    assert PUSH_FENCE not in text
    assert text.count(ep.RUNNER_PUSH_NOTE) == 1
    records = {r["id"]: r for r in fc.census(root, adapter)}
    push = next(r for r in records.values() if r["id"].startswith("proceed/phase-0-setup.md#6:"))
    runner = os.path.join(root, "tools", "adlc", "fence-run")
    call = "   %s run '%s' --arg worktree='<worktree>' --arg branch='<branch-name>'" % (
        runner, push["id"])
    assert "%s\n   ```\n   %s\n" % (call, ep.RUNNER_PUSH_NOTE) in text
    pattern = re.compile(r"^\s*%s run '([^' ]+)'( |$)" % re.escape(runner))
    calls = 0
    for fence in fc.fences(text):
        lines = [ln for ln in fence.code.split("\n") if ln.strip()]
        match = pattern.match(lines[0]) if len(lines) == 1 else None
        assert match, fence.code[:200]
        assert records[match.group(1)]["route"] == "runner"
        calls += 1
    assert calls >= 10
    close = closeout(root, adapter=adapter).decode("utf-8")
    assert ep.RUNNER_PUSH_NOTE not in close
    assert pipeline(root).decode("utf-8").count(ep.RUNNER_PUSH_NOTE) == 0


def test_push_note_anchor_must_match_once(install, monkeypatch):
    """The note is a rewrite like every other: an anchor that matches no line, or several,
    stops the build rather than landing anywhere else."""
    adapter = matcher_none(install)
    real = fr.rewrite_text

    def no_closing_line(text, rel, records, root):
        return real(text, rel, records, root).replace("'<branch-name>'\n   ```\n",
                                                      "'<branch-name>'\n   ```  \n")
    monkeypatch.setattr(fr, "rewrite_text", no_closing_line)
    with pytest.raises(ep.PromptBuildError, match="anchor matched 0 times"):
        pipeline(str(install), adapter=adapter)
    monkeypatch.setattr(fr, "rewrite_text", real)
    monkeypatch.setattr(fr, "runner_call", lambda rec, root, phs: "one line for every fence")
    with pytest.raises(ep.PromptBuildError, match="anchor matched [2-9] times"):
        pipeline(str(install), adapter=adapter)


def test_unrouted_fence_refuses_the_build_on_a_matcher_none_adapter(install):
    """AC-24: an unrouted fixture fence refuses the prompt build with `exec_prompt_refused` on
    an adapter whose matching nothing models, naming the fence and its first statement."""
    adapter = matcher_none(install)
    path = install / "proceed" / "phase-4-implementation.md"
    base = len(fc.fences(fc.view(str(install), "proceed/phase-4-implementation.md")))
    with open(os.path.join(HERE, "fixtures", "exec-fence", "extra-fences.md"),
              encoding="utf-8") as fh:
        add_line(path, fh.read())
    with pytest.raises(ep.ExecPromptRefused) as exc:
        pipeline(str(install), adapter=adapter)
    assert exc.value.fence_id.startswith("proceed/phase-4-implementation.md#%d:" % (base + 1))
    assert exc.value.statement.startswith("scp ")
    assert str(exc.value).startswith("exec_prompt_refused: ")
