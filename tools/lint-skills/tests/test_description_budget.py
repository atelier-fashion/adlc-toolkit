"""REQ-666 BR-7 / AC-7: `description-budget` (Unicode code points, never bytes)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"

_spec = importlib.util.spec_from_file_location("lint_check_budget", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_budget"] = _check
_spec.loader.exec_module(_check)

BUDGET = _check.DESCRIPTION_BUDGET
ETHOS, _ = _check.load_ethos_line(REPO_ROOT)


def _root(tmp_path: Path, descriptions: dict[str, str]) -> Path:
    (tmp_path / "VERSION").write_text("0.0.0\n")
    for name, desc in descriptions.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\n# /{name}\n\n{ETHOS}\n", encoding="utf-8")
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), "--root", str(root)],
                          capture_output=True, text=True, check=False)


def _budget_lines(out: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in out.stdout.splitlines() if ": description-budget:" in ln]


def test_budget_is_512():
    assert BUDGET == 512


def test_one_code_point_over_fires(tmp_path):
    """AC-7: at the budget is clean, one code point over is one finding."""
    out = _run(_root(tmp_path, {"at": "a" * BUDGET, "over": "a" * (BUDGET + 1)}))
    found = _budget_lines(out)
    assert len(found) == 1 and found[0].startswith("over/SKILL.md:3:"), out.stdout


def test_code_points_not_bytes(tmp_path):
    """AC-7: a description one code point over the budget but under it in bytes
    would pass a byte count; it must still fire. And one under in code points
    but over in bytes must not."""
    over = "é" * (BUDGET + 1)
    under = "é" * (BUDGET - 1)
    assert len(under.encode("utf-8")) > BUDGET
    out = _run(_root(tmp_path, {"over": over, "under": under}))
    assert [ln.split(":")[0] for ln in _budget_lines(out)] == ["over/SKILL.md"], out.stdout


def test_quoted_description_counts_its_value(tmp_path):
    out = _run(_root(tmp_path, {"q": '"' + "a" * BUDGET + '"'}))
    assert _budget_lines(out) == [], out.stdout


def test_inert_outside_a_plugin_root(tmp_path):
    root = _root(tmp_path, {"over": "a" * (BUDGET + 1)})
    (root / "VERSION").unlink()
    assert _budget_lines(_run(root)) == []


def test_repo_clean_and_sum_printed():
    """BR-7 on the real tree: every skill at or under the budget, and the sum is
    printed (non-vacuous: 17 descriptions read)."""
    out = _run(REPO_ROOT)
    assert _budget_lines(out) == [], out.stdout
    summary = [ln for ln in out.stderr.splitlines() if ln.startswith("description-budget: ")]
    assert len(summary) == 1, out.stderr
    count = int(summary[0].split()[1])
    assert count >= 17, summary


def test_trimmed_descriptions_keep_their_trigger_phrases():
    """AC-7: the two trimmed skills still list the phrases a user types."""
    adversary = (REPO_ROOT / "adversary" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ('"attack this"', '"adversary"', '"red-team this spec/plan/PR"', '"try to break this"',
                   '"what\'s wrong with this requirement"'):
        assert phrase in _check.skill_description(adversary)[0], phrase
    drift = (REPO_ROOT / "template-drift" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ('"check template drift"', '"template drift"', '"are my templates out of date"'):
        assert phrase in _check.skill_description(drift)[0], phrase


def test_block_scalar_and_continued_descriptions_are_measured_whole():
    """Phase 5 fix (LESSON-716): read the value the way a YAML loader does, so a
    long description cannot hide behind `>` or a line break."""
    folded = "---\nname: x\ndescription: >\n  " + "a " * 300 + "\n  tail\n---\n"
    desc, line = _check.skill_description(folded)
    assert line == 3 and len(desc) > BUDGET and desc.endswith("tail")
    continued = "---\nname: x\ndescription: first part\n  second part\n---\n"
    assert _check.skill_description(continued)[0] == "first part second part"
