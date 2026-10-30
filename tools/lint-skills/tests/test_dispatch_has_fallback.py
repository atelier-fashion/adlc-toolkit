"""REQ-666 BR-3, BR-4, BR-12 / AC-4, AC-11: `dispatch-has-fallback`.

The check (REQ-669's `dispatch-fallback`, renamed and widened) requires every
step that dispatches agents to say what to do when the harness cannot: the
canonical dispatch paragraph for a toolkit agent, at least its leading clause for
any other agent, or the explicit-stop block. Both blocks are read from
conventions.md, never copied here.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"
NAME = "dispatch-has-fallback"

_spec = importlib.util.spec_from_file_location("lint_check_dhf", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_dhf"] = _check
_spec.loader.exec_module(_check)


def _paragraph() -> str:
    text, _ = _check.load_dispatch_sentence(REPO_ROOT)
    assert text, "conventions.md has no readable dispatch paragraph"
    return text


def _stop() -> str:
    text, _ = _check.load_dispatch_stop(REPO_ROOT)
    assert text, "conventions.md has no readable explicit-stop block"
    return text


def _lint(tmp_path: Path, body: str) -> list[str]:
    skill = tmp_path / "fixture"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: fixture\ndescription: dispatch fixture\n---\n\n# /fixture\n\n" + body,
        encoding="utf-8",
    )
    out = subprocess.run(
        [sys.executable, str(CHECK), "--root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    return [ln for ln in out.stdout.splitlines() if f": {NAME}:" in ln]


def test_generic_dispatch_without_fallback_fires_once(tmp_path):
    """AC-11: "launch 3 agents using the Agent tool" with no fallback is exactly
    one finding, on that line."""
    found = _lint(tmp_path, "## Step 1\n\nThen launch 3 agents using the Agent tool, one per area.\n")
    assert len(found) == 1, found
    assert found[0].startswith("fixture/SKILL.md:10:"), found


def test_canonical_paragraph_is_clean(tmp_path):
    """AC-11 benign path: the same instruction followed by the canonical
    paragraph, and a toolkit agent dispatched beside it, draw nothing."""
    body = (
        "## Step 1\n\nLaunch 3 agents using the Agent tool: the **reflector** agent and two more.\n\n"
        + _paragraph() + "\n"
    )
    assert _lint(tmp_path, body) == []


def test_explicit_stop_is_clean(tmp_path):
    """AC-11: /sprint's explicit-stop block satisfies the check for a toolkit
    agent, with no dispatch paragraph anywhere in the file."""
    body = "## Step 3\n\nFor each REQ, launch a **pipeline-runner** agent using the Agent tool.\n\n" + _stop() + "\n"
    assert _lint(tmp_path, body) == []


def test_toolkit_agent_needs_more_than_the_leading_clause(tmp_path):
    """A toolkit agent is owed the whole paragraph: the leading clause alone
    leaves out the vendored-checklist and name-form rules."""
    body = ("## Step 1\n\nIf this harness can run subagents, dispatch the **reflector** agent; "
            "if it cannot, do the review yourself.\n")
    found = _lint(tmp_path, body)
    assert len(found) == 1 and "`reflector` agent" in found[0], found


def test_builtin_with_leading_clause_is_clean_and_without_fires(tmp_path):
    """BR-3: /bugfix's Explore dispatch has no checklist file, so the leading
    clause with its own inline arm is enough; the bare instruction is not."""
    good = ("## Phase 2\n\n2. If this harness can run subagents, launch Explore agents to trace the bug; "
            "if it cannot, or you are a subagent, trace the bug yourself with your harness's search and read tools:\n")
    assert _lint(tmp_path, good) == []
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    assert len(_lint(bad_root, "## Phase 2\n\n2. Launch Explore agents to trace the bug:\n")) == 1


def test_descriptions_are_not_instructions(tmp_path):
    """Must-not-fire: a past participle, a noun use and a cross-reference."""
    body = (
        "## Step 1\n\n- Running inside a subagent context (e.g., dispatched via the Agent tool).\n"
        "- Pass the summary in the dispatch prompt to each of the 4 audit agents launched in Step 2.\n"
        "- When dispatching the corresponding audit agent in Step 2, include the block.\n"
        "- Do not launch further agents here.\n"
    )
    assert _lint(tmp_path, body) == []


def test_paragraph_names_init_and_toolkit_fallback():
    """BR-4: the inline arm reads the vendored copy, names `/init` (dual-spelled,
    LESSON-728) when it is absent, falls back to ToolkitRoot's copy, never
    improvises, and keeps BUG-230's read-only rule for review and audit agents."""
    p = _paragraph()
    assert p.startswith("If this harness can run subagents, dispatch these agents in parallel; "
                        "if it cannot, or you are a subagent, run each checklist inline from "
                        "`.adlc/agents/<name>.md`.")
    for needle in ("`/init` (`/adlc:init` on the plugin install)", "`$ADLC_TOOLKIT_ROOT/agents/<name>.md`",
                   "never improvise a checklist", "read-only",
                   "no test runner, build tool, package manager or interpreter"):
        assert needle in p, needle
    s = _stop()
    assert "requires a harness that can run subagents" in s and "stop" in s


def test_repo_clean_and_non_vacuous():
    """BR-3 on the real tree: no finding, and every named dispatcher both has a
    mention the detector sees and carries the block it owes (LESSON-019)."""
    out = subprocess.run([sys.executable, str(CHECK), "--root", str(REPO_ROOT)],
                         capture_output=True, text=True, check=False)
    assert [ln for ln in out.stdout.splitlines() if f": {NAME}:" in ln] == [], out.stdout
    names = _check.load_agent_names(REPO_ROOT)
    owed = {"sprint/SKILL.md": _stop()}
    for rel in ("architect/SKILL.md", "review/SKILL.md", "optimize/SKILL.md", "reflect/SKILL.md",
                "analyze/SKILL.md", "adversary/SKILL.md", "proceed/SKILL.md",
                "proceed/phase-4-implementation.md", "proceed/phases-lite.md", "sprint/SKILL.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        mentions, _ = _check.dispatch_mentions(text, names, _paragraph(), _stop())
        assert any(m.agent for m in mentions), rel
        assert owed.get(rel, _paragraph()) in " ".join(text.split()), rel


def test_no_claude_agents_literal():
    """AC-4: no skill, agent or partial names `~/.claude/agents`."""
    hits = []
    for pattern in ("*/SKILL.md", "agents/*.md", "partials/*"):
        for path in REPO_ROOT.glob(pattern):
            if path.is_file() and "~/.claude/agents" in path.read_text(encoding="utf-8", errors="replace"):
                hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == []
