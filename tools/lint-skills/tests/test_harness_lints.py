"""REQ-657: the harness adapter framework's lint checks and its documentation.

`allowlist-fidelity` and `render-parity` run on the real tree (clean), and on
synthetic roots where a defect must be found; the declared residuals are one text,
carried byte-identical in every README that must state them (BR-18).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check  # noqa: E402

RESIDUAL_HOMES = ("tools/lint-skills/README.md", "tools/adlc/README.md",
                  "harness/claude/README.md")


def _block(text: str) -> str:
    lo = text.index("<!-- declared-residuals -->")
    hi = text.index("<!-- /declared-residuals -->", lo)
    return text[lo:hi]


def test_allowlist_fidelity_clean_on_tree(capsys):
    assert check.check_allowlist_fidelity(REPO_ROOT) == []
    err = capsys.readouterr().err.splitlines()
    assert "allowlist-fidelity: claude: exact=81, inexpressible=1, residual=2" in err
    # The report ends with the declared residuals.
    readme = (REPO_ROOT / "tools/lint-skills/README.md").read_text(encoding="utf-8")
    block = _block(readme).splitlines()[1:]          # the marker line excluded
    tail = [line[len("allowlist-fidelity: "):] for line in err[-len(block):]]
    assert tail == block
    assert not any("narrowed" in line for line in err)


def test_render_parity_clean_on_tree():
    assert check.check_render_parity(REPO_ROOT) == []


def test_render_parity_reports_drift(tmp_path):
    """A root whose golden differs is reported (the full matrix is in
    tools/adlc/tests/test_harness_framework.py::test_render_check_parity)."""
    import shutil
    for d in ("harness", "templates", "agents", ".claude"):
        shutil.copytree(REPO_ROOT / d, tmp_path / d)
    shutil.copytree(REPO_ROOT / "tools" / "adlc", tmp_path / "tools" / "adlc",
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    golden = tmp_path / "harness/claude/rendered/settings.json"
    doc = json.loads(golden.read_text())
    doc["permissions"]["ask"].remove("Bash(gh pr merge:*)")
    golden.write_text(json.dumps(doc, indent=2) + "\n")
    findings = check.check_render_parity(tmp_path)
    assert [f.file for f in findings] == ["harness/claude/rendered/settings.json"]
    assert findings[0].check == "render-parity" and "drifted" in findings[0].message


def test_unguarded_source_walks_hooks(tmp_path):
    good = check.guarded_source_line("ethos-inject")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "hooks.yml").write_text(
        "hooks:\n  - id: ethos-inject\n    command: |\n      %s\n      adlc_ethos_inject\n" % good)
    assert check.check_hook_sources(tmp_path) == []
    (tmp_path / "templates" / "hooks.yml").write_text(
        "hooks:\n  - id: ethos-inject\n    command: |\n"
        "      . .adlc/partials/ethos-inject.sh 2>/dev/null || . \"$ADLC_TOOLKIT_ROOT/partials/ethos-inject.sh\"\n")
    found = check.check_hook_sources(tmp_path)
    assert [(f.file, f.line, f.check) for f in found] == [("templates/hooks.yml", 4,
                                                           "unguarded-source")]
    rendered = tmp_path / "harness" / "x" / "rendered"
    rendered.mkdir(parents=True)
    (rendered / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "x=1\n. .adlc/partials/session-record.sh\nadlc_session_record"}
    ]}]}}))
    found = check.check_hook_sources(tmp_path)
    assert "harness/x/rendered/settings.json" in {f.file for f in found}


def test_shipped_hook_sources_are_canonical():
    assert check.check_hook_sources(REPO_ROOT) == []


def test_residuals_identical():
    blocks = {rel: _block((REPO_ROOT / rel).read_text(encoding="utf-8")) for rel in RESIDUAL_HOMES}
    assert len(set(blocks.values())) == 1, sorted(blocks)
    text = next(iter(blocks.values()))
    for clause in ("spelling-level", "`find -exec`", "`gh api`", "Semantic equivalents",
                   "Rule A grandfathers it", "never the gate (Rule B)", "REQ-659"):
        assert clause in text, clause


def test_no_doc_calls_the_allowlist_a_gate():
    """BR-18: nothing describes the allowlist, deny_tier_render or the lint as what
    stops a deny-tier command from running unattended."""
    import re
    bad = re.compile(r"(allowlist|deny_tier_render|allowlist-fidelity)[^.\n]{0,60}"
                     r"\b(prevents|blocks|stops|guarantees)\b", re.I)
    for rel in RESIDUAL_HOMES + ("README.md", "init/SKILL.md", "template-drift/SKILL.md",
                                 "templates/permissions.yml"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert not bad.search(text), (rel, bad.search(text).group(0))


def test_docs_carry_surfaces():
    expect = {
        "README.md": ("templates/permissions.yml", "adlc harness render", "harness-config"),
        ".adlc/context/architecture.md": ("Harness adapter framework (REQ-657)", "Rule B",
                                          "ethos-inject"),
        ".adlc/context/conventions.md": ("Harness adapters are data (REQ-657)",
                                         "accepted_fidelity", "one format renderer"),
        "tools/adlc/README.md": ("adlc harness render", "render-currency:<name>",
                                 "adlc harness drift"),
        "tools/lint-skills/README.md": ("allowlist-fidelity", "render-parity"),
        "init/SKILL.md": ("--harness", "adlc.py\" harness render", "AGENTS.md"),
        "template-drift/SKILL.md": ("harness-config", "harness drift"),
        "CHANGELOG.md": ("REQ-657", "missing `hooks` block"),
    }
    for rel, needles in expect.items():
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text, (rel, needle)
