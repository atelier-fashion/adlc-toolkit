"""Test the agent model: drift check added to lint-skills (REQ-516 / BR-5).

Builds a tmp root containing tools/adlc/agents_render.py + a small agents/ tree
and exercises check.check_agent_model_drift directly (it imports the real engine
from <root>/tools/adlc).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
ADLC_DIR = REPO_ROOT / "tools" / "adlc"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402


def _build_root(tmp_path: Path, agents: dict[str, str]) -> Path:
    """tmp root with tools/adlc/agents_render.py + agents/<name>.md (model values)."""
    (tmp_path / "tools" / "adlc").mkdir(parents=True)
    shutil.copyfile(ADLC_DIR / "agents_render.py",
                    tmp_path / "tools" / "adlc" / "agents_render.py")
    adir = tmp_path / "agents"
    adir.mkdir()
    for name, model in agents.items():
        body = (
            "---\n"
            f"name: {name}\n"
            "description: d\n"
            f"model: {model}\n"
            "tier: reviewer\n"
            "tools: Read\n"
            "---\n"
            "<!-- comment -->\n\nBody.\n"
        )
        (adir / f"{name}.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_drift_finding_on_handedit(tmp_path, monkeypatch):
    # correctness-reviewer ships as opus; set it to sonnet to force drift.
    monkeypatch.setenv("ADLC_CONFIG", str(tmp_path / "no-config.yml"))
    root = _build_root(tmp_path, {"correctness-reviewer": "sonnet"})
    findings = check.check_agent_model_drift(root)
    assert any(f.check == "agent-model-drift" and "correctness-reviewer" in f.file
               for f in findings)


def test_no_drift_when_shipped_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ADLC_CONFIG", str(tmp_path / "no-config.yml"))
    root = _build_root(tmp_path, {"correctness-reviewer": "opus"})  # matches shipped
    findings = check.check_agent_model_drift(root)
    assert findings == []


def test_degrades_when_engine_absent(tmp_path):
    # A root with no tools/adlc/agents_render.py -> zero findings, no crash.
    (tmp_path / "agents").mkdir()
    assert check.check_agent_model_drift(tmp_path) == []
