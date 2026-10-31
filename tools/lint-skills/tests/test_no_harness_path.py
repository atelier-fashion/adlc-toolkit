"""REQ-666 BR-13 / AC-12: `no-harness-path`.

`no-harness-path` absorbs REQ-669's `toolkit-path` (its surfaces, walk and
exceptions) and widens the spellings: every harness home in skill, agent and
partial-doc text, and toolkit or foreign-harness paths in code. A general
`~/.claude` path in code stays REQ-654's `adlc-home` (ADR-5), so every line is
reported by exactly one of the two.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"

_spec = importlib.util.spec_from_file_location("lint_check_nhp", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_nhp"] = _check
_spec.loader.exec_module(_check)

FAMILIES = {
    "skill": "alpha/SKILL.md",
    "partial-doc": "partials/x.md",
    "agent": "agents/x.md",
    "partial": "partials/x.sh",
    "tool": "tools/kit/x.py",
}
TEXT = {"skill", "partial-doc", "agent"}


def _all_findings(line: str, rel: str) -> list[tuple[str, int]]:
    """Both checks' findings for a one-line file at ``rel``, as (check, line)."""
    text = line + "\n"
    found = [(f.check, f.line) for f in _check.toolkit_path_findings(text, rel)]
    if not rel.endswith(".md"):
        found += [(f.check, f.line) for f in _check.adlc_home_findings(text, rel)]
    return found


@pytest.mark.parametrize("family", sorted(FAMILIES))
@pytest.mark.parametrize("spelling", [
    "~/.claude/agents/x.md", "$HOME/.claude/adlc/config.yml", "~/.codex/config.toml",
    "~/.copilot/agents", "~/.gemini/settings.json", "~/.cursor/rules",
])
def test_each_harness_home_fires_once(family, spelling):
    """AC-12: one finding per line, in a skill, a partial, an agent and a tool.
    `$HOME/.claude/adlc` in code is the machine config, which `adlc-home` owns;
    everywhere else the finding is `no-harness-path`'s."""
    rel = FAMILIES[family]
    line = f'V="{spelling}"' if family in ("partial", "tool") else f"Read `{spelling}` first."
    found = _all_findings(line, rel)
    assert len(found) == 1, (family, spelling, found)
    owner = "adlc-home" if (spelling.startswith("$HOME/.claude/adlc") and family not in TEXT) \
        else "no-harness-path"
    assert found[0][0] == owner, found


@pytest.mark.parametrize("line,rel", [
    (_check.TOOLKIT_ROOT_LINE, "alpha/SKILL.md"),
    ("if [ -f .adlc/partials/x.sh ]; then . .adlc/partials/x.sh; else . \"$ADLC_TOOLKIT_ROOT/partials/x.sh\"; fi",
     "alpha/SKILL.md"),
    ('. "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/x.sh"', "partials/x.sh"),
    ("The counter is `${ADLC_HOME:-$HOME/.claude}/.global-next-req`.", "alpha/SKILL.md"),
    ("Transcripts live in `~/.claude/projects/`. <!-- adlc-home: claude-code -->", "partials/x.md"),
    ("<!-- model: is rendered from ~/.claude/adlc/config.yml; do not hand-edit. -->", "agents/x.md"),
    ('LITERAL = "~/.claude/skills/partials"', "tools/lint-skills/check.py"),
    ('ln -s "$CLONE" ~/.claude/skills', "install.sh"),
    ('    trust = "~/.codex/config.toml"', "tools/adlc/harness_probe.py"),
])
def test_exceptions_do_not_fire(line, rel):
    """AC-12 benign path: the root line and guarded source, the default-expansion
    spellings, a marked line, an HTML comment line (the agents' rendered header),
    the `unguarded-source` literal in the lint's own table, `install.sh`'s alias,
    and the harness probe."""
    assert [f for f in _check.toolkit_path_findings(line + "\n", rel)] == []


def test_comment_line_in_a_fence_does_not_fire():
    text = "```sh\n# counters live under ~/.claude and ~/.codex\necho ok\n```\n"
    assert _check.toolkit_path_findings(text, "alpha/SKILL.md") == []


def test_near_miss_of_an_exempt_token_fires():
    """Exceptions are literal: an unbraced default is not the exempt spelling."""
    assert len(_check.toolkit_path_findings("Use `$ADLC_HOME:-$HOME/.claude`.\n", "alpha/SKILL.md")) == 1


def test_repo_clean_every_surface_scanned():
    """BR-13 on the real tree: clean, and every surface family read files."""
    scan = _check.scan_toolkit_path(REPO_ROOT)
    assert scan.findings == [], "\n".join(f.format() for f in scan.findings)
    assert all(n > 0 for n in scan.surfaces.values()), scan.surfaces
    assert _check.TOOLKIT_PATH_CHECK == "no-harness-path"


def test_adlc_home_keeps_toolkit_lines_in_files_no_harness_path_sets_aside():
    """Phase 5 fix: `adlc-home` defers a toolkit-path line to `no-harness-path`
    only where that check reads the file; in install.sh, the doctor and the
    probe an unmarked line is still `adlc-home`'s, so it is never unread."""
    line = 'ln -s "$CLONE" ~/.claude/skills\n'
    for rel in ("install.sh", "tools/adlc/checks.py", "tools/adlc/harness_probe.py"):
        assert [f.check for f in _check.adlc_home_findings(line, rel)] == ["adlc-home"], rel
        assert _check.toolkit_path_findings(line, rel) == [], rel
    assert _check.adlc_home_findings(line, "partials/x.sh") == []
    assert [f.check for f in _check.toolkit_path_findings(line, "partials/x.sh")] == ["no-harness-path"]


def test_a_codex_home_in_a_partial_is_a_finding():
    """REQ-655 AC-1: the lint half; `.codex/` and `~/.agents` are held by that REQ's test."""
    assert _all_findings('x="$HOME/.codex/rules"', FAMILIES["partial"])
