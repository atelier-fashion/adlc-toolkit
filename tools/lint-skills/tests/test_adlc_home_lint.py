"""REQ-654 BR-13 / AC-10: the `adlc-home` lint keeps the ADLC_HOME seam open.

It fails on a new literal home-directory `.claude` path in the code of
`tools/`, `scripts/`, `install.sh` and `partials/*.sh`, and is silent on every
legitimate line: comments, docstrings, test and fixture trees, REQ-669's
default-expansion token, and a line marked with its kind (LESSON-440: a
detector needs its benign path pinned as hard as its firing path).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "adlc-home" / "plugin-root"


def _by_file(findings):
    out: dict[str, list[int]] = {}
    for f in findings:
        out.setdefault(f.file, []).append(f.line)
    return out


def test_fires_on_new_literal_in_tool():
    """Every planted literal in code fires, once per line, on every surface."""
    scan = check.scan_adlc_home(FIXTURE)
    got = _by_file(f for f in scan.findings if "literal home-directory" in f.message)
    assert got == {
        "tools/kit/tool.py": [6, 10],
        "tools/kit/tool.sh": [2],
        "partials/p.sh": [1],
        "install.sh": [2],
        "scripts/hook.sh": [2],
    }
    assert all(f.check == "adlc-home" for f in scan.findings)


def test_benign_lines_do_not_fire():
    """Comments, docstrings, the ADR-2 token, a marked line, `.claude-plugin`,
    `.claude.json`, a repo-relative `.claude/worktrees` and a test tree are quiet."""
    scan = check.scan_adlc_home(FIXTURE)
    lines = _by_file(scan.findings)
    assert not set(lines.get("tools/kit/tool.py", [])) & {1, 14, 15, 16, 17, 18}
    assert not set(lines.get("tools/kit/tool.sh", [])) & {3, 4, 5, 7}
    assert "tools/kit/tests/planted.py" not in lines


def test_unknown_marker_is_a_finding():
    scan = check.scan_adlc_home(FIXTURE)
    typo = [f for f in scan.findings if "unknown adlc-home marker" in f.message]
    assert [(f.file, f.line) for f in typo] == [("tools/kit/tool.sh", 6)]
    assert "`typo`" in typo[0].message


@pytest.mark.parametrize("line,rel", [
    ('V="$HOME/.claude/x"', "tools/x.sh"),
    ('V="${HOME}/.claude/x"', "tools/x.sh"),
    ('V="${HOME:-}/.claude/x"', "partials/x.sh"),
    ('V="${HOME%/}/.claude/x"', "partials/x.sh"),
    ('V="$HOME"/.claude/x', "install.sh"),
    ('V=\\"\\$HOME\\"/.claude/x', "install.sh"),
    ('V="$my_home/.claude"', "scripts/x"),
    ('v = "~/.claude/x"', "tools/x.py"),
    ('v = Path.home() / ".claude"', "tools/x.py"),
    ('v = os.path.join(home_dir, ".claude")', "tools/x.py"),
])
def test_each_spelling_fires(line, rel):
    assert [f.line for f in check.adlc_home_findings(line + "\n", rel)] == [1]


@pytest.mark.parametrize("line,rel", [
    ('V="$HOME/.claude/x"  # adlc-home: claude-code', "tools/x.sh"),
    ('V="$HOME/.claude/adlc/plugin-root"  # adlc-home: alias', "tools/x.sh"),
    ('v = "~/.claude"  # adlc-home: default', "tools/x.py"),
    ('. "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/x.sh"', "partials/x.sh"),
    ("# $HOME/.claude in a comment", "tools/x.sh"),
    ('v = os.path.join(root, ".claude")', "tools/x.py"),
    ('V="$REPO/.claude/worktrees"', "tools/x.sh"),
    ('V="$HOME/.claude-plugin"', "tools/x.sh"),
    (check.TOOLKIT_ROOT_LINE, "scripts/x"),
])
def test_each_benign_spelling_is_quiet(line, rel):
    assert check.adlc_home_findings(line + "\n", rel) == []


def test_every_surface_is_scanned():
    """Non-vacuity: each surface family read at least one file, on the fixture
    and on this repo (LESSON-019: a family that walked nothing is not green)."""
    for root in (FIXTURE, REPO_ROOT):
        scan = check.scan_adlc_home(root)
        assert set(scan.surfaces) == set(check.ADLC_HOME_SURFACES)
        assert all(n > 0 for n in scan.surfaces.values()), (root, scan.surfaces)


def test_repo_is_clean():
    """The toolkit itself: every remaining literal is marked with its kind."""
    assert check.scan_adlc_home(REPO_ROOT).findings == []


def test_inert_outside_a_plugin_root(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.sh").write_text('V="$HOME/.claude/x"\n')
    assert check.scan_adlc_home(tmp_path).findings == []


def test_registered_in_run():
    findings, _scanned = check.run(REPO_ROOT)
    assert [f for f in findings if f.check == "adlc-home"] == []
    assert "check_adlc_home(root)" in (REPO_ROOT / "tools" / "lint-skills" / "check.py").read_text()


def test_fires_on_migration_code():
    """REQ-663 BR-13, BR-15: migration code reaches the default through the helper, so a
    literal added to it is a finding, and the shipped files carry none."""
    for rel in ("tools/adlc/migrate_home.py", "tools/adlc/home_layout.py"):
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        assert check.adlc_home_findings(text, rel) == [], rel
        assert ".claude" not in text.replace(".claude-plugin", ""), rel
        planted = text + 'BAD = os.path.join(os.path.expanduser("~"), ".claude")\n'
        found = check.adlc_home_findings(planted, rel)
        assert [f.line for f in found] == [len(planted.splitlines())], rel
        planted = text + 'BAD = "$HOME/.claude/.global-next-req"\n'
        assert len(check.adlc_home_findings(planted, rel)) == 1, rel
