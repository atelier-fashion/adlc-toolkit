"""Prompt assembly and the runtime scan (REQ-659 BR-6, BR-7, BR-14, BR-24)."""

import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_prompt as ep  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
REQ = "REQ-901"
BRANCH = "feat/REQ-901-thing"
WT = "/abs/repo/.worktrees/REQ-901"


def pipeline(toolkit=TOOLKIT, answer=None):
    return ep.pipeline_prompt(toolkit, toolkit, REQ, BRANCH, "/abs/repo", WT, answer=answer)


def closeout(toolkit=TOOLKIT, deploy=""):
    return ep.closeout_prompt(toolkit, REQ, "chore/REQ-901-close-out", "/abs/repo/co", "EVIDENCE",
                              deploy)


@pytest.fixture
def install(tmp_path):
    """A copy of every prompt source, for fixtures that alter one."""
    root = tmp_path / "toolkit"
    root.mkdir()
    for rel in ("proceed", "wrapup"):
        shutil.copytree(os.path.join(TOOLKIT, rel), str(root / rel))
    (root / "sprint").mkdir()
    shutil.copy(os.path.join(TOOLKIT, "sprint", "SKILL.md"), str(root / "sprint" / "SKILL.md"))
    shutil.copy(os.path.join(TOOLKIT, "ETHOS.md"), str(root / "ETHOS.md"))
    return root


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
    allowed = "   # /wrapup call sites. Derivation + renumber message live in partials/id-recheck.sh."
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
