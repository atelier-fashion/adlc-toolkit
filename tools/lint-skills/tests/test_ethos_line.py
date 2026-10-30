"""REQ-666 BR-2 / AC-3: `ethos-line`.

The ETHOS line is the one bang preamble line a skill keeps. The check reads the
canonical line from conventions.md and requires it exactly once, byte-identical,
in every `*/SKILL.md` of a plugin root.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"

_spec = importlib.util.spec_from_file_location("lint_check_ethos", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_ethos"] = _check
_spec.loader.exec_module(_check)

ETHOS, _SOURCE = _check.load_ethos_line(REPO_ROOT)


def _skill(ethos_lines: list[str], extra: str = "") -> str:
    head = "---\nname: x\ndescription: fixture\n---\n\n# /x\n\n## Ethos\n\n"
    return head + "\n".join(ethos_lines) + "\n\n## Context\n\n" + extra + "\n"


def _findings(text: str) -> list:
    return _check.check_ethos_line(text, "x/SKILL.md", ETHOS)


def test_canonical_line_is_read_from_conventions():
    assert ETHOS and ETHOS.startswith("!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md")
    assert _SOURCE == ".adlc/context/conventions.md"


def test_clean_skill_has_no_finding():
    assert _findings(_skill([ETHOS])) == []


def test_missing_line_fires_once():
    found = _findings(_skill([]))
    assert len(found) == 1 and "no ETHOS line" in found[0].message


@pytest.mark.parametrize("pos", range(0, len(ETHOS or ""), 7))
def test_line_altered_by_one_byte_fires_once(pos):
    """AC-3: a one-byte change anywhere in the line is exactly one finding."""
    ch = ETHOS[pos]
    altered = ETHOS[:pos] + ("Z" if ch != "Z" else "Y") + ETHOS[pos + 1:]
    assert len(_findings(_skill([altered]))) == 1, altered


def test_duplicate_line_fires_once():
    found = _findings(_skill([ETHOS, "", ETHOS]))
    assert len(found) == 1 and "second copy" in found[0].message


def test_other_inline_bang_command_fires():
    """BR-2: a context read left as a preamble line is a finding; the same read
    inside a fence is not."""
    bad = _skill([ETHOS], "- Conventions: !`cat .adlc/context/conventions.md`")
    assert len(_findings(bad)) == 1
    good = _skill([ETHOS], "```sh\n# adlc-context\ncat .adlc/context/conventions.md 2>/dev/null || echo 'none'\n```")
    assert _findings(good) == []


def _plugin_root(tmp_path: Path, text: str) -> Path:
    (tmp_path / "VERSION").write_text("0.0.0\n")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "SKILL.md").write_text(text)
    return tmp_path


def test_cli_wires_the_check_on_a_plugin_root(tmp_path):
    root = _plugin_root(tmp_path, _skill([]))
    out = subprocess.run([sys.executable, str(CHECK), "--root", str(root)],
                         capture_output=True, text=True, check=False)
    assert [ln for ln in out.stdout.splitlines() if ": ethos-line:" in ln] != [], out.stdout


def test_cli_is_inert_outside_a_plugin_root(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "SKILL.md").write_text(_skill([]))
    out = subprocess.run([sys.executable, str(CHECK), "--root", str(tmp_path)],
                         capture_output=True, text=True, check=False)
    assert ": ethos-line:" not in out.stdout


def test_repo_clean_and_every_skill_carries_the_line():
    """AC-3 on the real tree: clean, and not vacuously: every skill has the line
    exactly once, and `grep -n '!`'` finds that line and nothing else."""
    assert _check.check_ethos_lines(REPO_ROOT) == []
    skills = sorted(REPO_ROOT.glob("*/SKILL.md"))
    assert len(skills) >= 17
    for skill in skills:
        lines = [ln for ln in skill.read_text(encoding="utf-8").splitlines() if "!`" in ln]
        assert lines == [ETHOS], skill
