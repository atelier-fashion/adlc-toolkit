"""Test the toolkit-path check (REQ-669 BR-13, BR-2, AC-7, ADR-9).

`scan_toolkit_path` walks the plugin-reachable surface (`TOOLKIT_PATH_SURFACES`)
of a plugin root and flags every literal `~/.claude/skills` / `~/.claude/agents`
spelling (`TOOLKIT_PATH_SPELLINGS`) outside `TOOLKIT_PATH_EXCEPTIONS`.

Fixture trees live under `fixtures/toolkit-path/`:

- `plugin-root/` is a benign plugin root with at least one file on every surface
  and every exception planted: the root line, the default-expansion spelling,
  comment lines, `tests/` and `fixtures/` trees, `install.sh`,
  `tools/adlc/checks.py` and the lint's own `tools/lint-skills/check.py`. Its
  skill is stored as `SKILL.fixture.md` and renamed when the tree is staged into
  `tmp_path`, so neither the real-repo lint walk nor the plugin loader sees it.
- `literal-read-path.sh` is a new partial that reads `~/.claude/skills/partials/x.sh`.
- `spellings/` holds one partial per flagged spelling.

Every scan asserts the surfaces it read, so a fixture path that went wrong fails
instead of passing vacuously (LESSON-019).
"""
from __future__ import annotations

import ast
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "toolkit-path"
SKILL_STAND_IN = "SKILL.fixture.md"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402

CHECK = "no-harness-path"
FILE_EXCEPTIONS = ("tools/adlc/checks.py", "tools/lint-skills/check.py")
# REQ-666 ADR-5: the harness probe edits the other harnesses' user files by design.
PROBE_EXCEPTION = "tools/adlc/harness_probe.py"

# spellings/<file> -> the one flagged spelling it holds, on line 3.
SPELLING_FIXTURES = {
    "tilde-skills.sh": "~/.claude/skills",
    "home-skills.sh": "$HOME/.claude/skills",
    "braced-home-skills.sh": "${HOME}/.claude/skills",
    "default-home-skills.sh": "${HOME:-}/.claude/skills",
    "tilde-agents.sh": "~/.claude/agents",
    "home-agents.sh": "$HOME/.claude/agents",
    "braced-home-agents.sh": "${HOME}/.claude/agents",
    "default-home-agents.sh": "${HOME:-}/.claude/agents",
}


def _stage(dest_parent: Path) -> Path:
    """Copy the benign plugin root under ``dest_parent``, skill stand-ins renamed."""
    src = FIXTURES / "plugin-root"
    assert src.is_dir(), f"fixture tree missing: {src}"
    dest = dest_parent / "plugin-root"
    shutil.copytree(src, dest)
    for stand_in in dest.rglob(SKILL_STAND_IN):
        stand_in.rename(stand_in.with_name("SKILL.md"))
    return dest


def _scan(root: Path) -> check.ToolkitPathScan:
    """Scan ``root``; fail unless every surface read at least one file."""
    scan = check.scan_toolkit_path(root)
    assert set(scan.surfaces) == set(check.TOOLKIT_PATH_SURFACES)
    empty = [s for s, n in scan.surfaces.items() if n == 0]
    assert not empty, f"vacuous surface(s) under {root}: {empty} (LESSON-019)"
    assert all(f.check == CHECK for f in scan.findings)
    return scan


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- BR-13 / AC-7: a literal read fails --------------------------------------

def test_literal_read_in_new_partial_fails(tmp_path):
    root = _stage(tmp_path)
    shutil.copy(FIXTURES / "literal-read-path.sh", root / "partials" / "literal-read-path.sh")
    scan = _scan(root)
    assert [(f.file, f.line) for f in scan.findings] == [("partials/literal-read-path.sh", 5)]
    assert "`~/.claude/skills`" in scan.findings[0].message
    assert "TOOLKIT_PATH_EXCEPTIONS" in scan.findings[0].message


def test_spelling_fixtures_cover_every_flagged_spelling():
    on_disk = {p.name for p in (FIXTURES / "spellings").iterdir()}
    assert on_disk == set(SPELLING_FIXTURES)
    assert sorted(SPELLING_FIXTURES.values()) == sorted(check.TOOLKIT_PATH_SPELLINGS)


@pytest.mark.parametrize("name", sorted(SPELLING_FIXTURES))
def test_each_spelling_fails_in_its_own_fixture(tmp_path, name):
    root = _stage(tmp_path)
    shutil.copy(FIXTURES / "spellings" / name, root / "partials" / name)
    scan = _scan(root)
    assert [(f.file, f.line) for f in scan.findings] == [(f"partials/{name}", 3)]
    assert f"`{SPELLING_FIXTURES[name]}`" in scan.findings[0].message


# One file per surface, each holding one literal read on a code line.
SURFACE_PLANTS = {
    "*/SKILL.md": ("beta/SKILL.md", "# beta\n\n```sh\ncat ~/.claude/skills/ETHOS.md\n```\n"),
    "proceed/phase*.md": ("proceed/phase-9.md", "Read `$HOME/.claude/skills/templates/x.md`.\n"),
    "*/references/*.md": ("alpha/references/two.md", "Read `~/.claude/skills/partials/two.md`.\n"),
    "agents/*.md": ("agents/two.md", "# two\n\nRun `~/.claude/agents/two.md` inline.\n"),
    "partials/*.sh": ("partials/two.sh", 'cat "${HOME}/.claude/skills/ETHOS.md"\n'),
    "partials/*.md": ("partials/two.md", "```sh\n. ${HOME:-}/.claude/skills/partials/two.sh\n```\n"),
    "workflows/*.js": ("workflows/two.js", "const AGENTS = '~/.claude/agents';\n"),
    "tools/**": ("tools/kit/deep/more.py", 'PATH = "~/.claude/skills/tools"\n'),
    # A comment line: in a preset or a template it is the user's instruction.
    "presets/*": ("presets/two.yml", "#   cp ~/.claude/skills/presets/two.yml .adlc/config.yml\n"),
    "templates/*": ("templates/two-template.yml", "# Read $HOME/.claude/agents/reflector.md\n"),
}


def test_surface_plants_cover_every_surface():
    assert set(SURFACE_PLANTS) == set(check.TOOLKIT_PATH_SURFACES)


@pytest.mark.parametrize("surface", check.TOOLKIT_PATH_SURFACES)
def test_literal_fires_on_every_surface(tmp_path, surface):
    root = _stage(tmp_path)
    before = _scan(root).surfaces[surface]
    rel, text = SURFACE_PLANTS[surface]
    _write(root, rel, text)
    scan = _scan(root)
    assert scan.surfaces[surface] == before + 1
    assert [f.file for f in scan.findings] == [rel]


def test_extensionless_shebang_tool_is_scanned(tmp_path):
    root = _stage(tmp_path)
    _write(root, "tools/kit/run2", '#!/bin/sh\nexec cat "$HOME/.claude/skills/VERSION"\n')
    assert [(f.file, f.line) for f in _scan(root).findings] == [("tools/kit/run2", 2)]


# --- BR-13: the exceptions do not fire (benign path) -------------------------

def test_exceptions_do_not_fire(tmp_path):
    root = _stage(tmp_path)
    scan = _scan(root)
    assert scan.findings == []
    # The file exceptions on the walked surface were read and set aside, not missed.
    assert scan.excepted == FILE_EXCEPTIONS
    # Each planted exception really does hold a flagged spelling, so the clean
    # result above is the exception at work, not an empty fixture: the same
    # text under a path no exception covers fires.
    moved = {
        "install.sh": "tools/kit/install.sh",
        "tools/adlc/checks.py": "tools/adlc/doctor.py",
        "tools/lint-skills/check.py": "tools/lint-skills/other.py",
        "tools/kit/tests/helper.py": "tools/kit/helper.py",
        "tools/kit/fixtures/sample.sh": "tools/kit/sample.sh",
        "partials/tests/ok.test.sh": "partials/ok.test.sh",
    }
    for rel, elsewhere in moved.items():
        text = (root / rel).read_text(encoding="utf-8")
        assert check.toolkit_path_findings(text, rel) == [], rel
        assert check.toolkit_path_findings(text, elsewhere), elsewhere
    # Comment lines: strip the leaders and the same lines fire.
    for rel in ("partials/ok.sh", "tools/kit/tool.py", "tools/kit/runner"):
        text = (root / rel).read_text(encoding="utf-8")
        uncommented = "\n".join(line.lstrip().lstrip("#") for line in text.splitlines())
        assert check.toolkit_path_findings(uncommented, rel), rel


@pytest.mark.parametrize("rel, text", [
    # The canonical root line, bare and indented.
    ("alpha/SKILL.md", f"```sh\n{check.TOOLKIT_ROOT_LINE}\n```\n"),
    ("alpha/SKILL.md", f"1. step\n\n   ```sh\n   {check.TOOLKIT_ROOT_LINE}\n   ```\n"),
    # The default-expansion spelling, once and twice on a line, in code and prose.
    ("partials/a.sh", 'x="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"\n'),
    ("partials/a.sh", '[ -x "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/a" ] && '
                      'D="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/b"\n'),
    ("partials/a.md", 'The engine is `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/x"`.\n'),
    # Comment lines in each comment syntax.
    ("partials/a.sh", "# ~/.claude/skills\n    # $HOME/.claude/skills\n"),
    ("tools/k/a.py", "# ~/.claude/agents\n"),
    ("alpha/SKILL.md", "```bash\n  # ${HOME}/.claude/skills\n```\n"),
    ("workflows/a.js", "// ~/.claude/agents\n"),
    ("workflows/a.js", "/*\n * ~/.claude/skills\n */\nconst a = 1;\n"),
    # Test and fixture trees at any depth.
    ("tools/k/tests/x.py", 'P = "~/.claude/skills"\n'),
    ("partials/tests/fixtures/x.sh", ". ~/.claude/skills/partials/x.sh\n"),
    ("tests/SKILL.md", "~/.claude/skills\n"),
    # The file exceptions.
    ("install.sh", 'ln -s "$PWD" "$HOME/.claude/skills"\n'),
    ("tools/adlc/checks.py", 'P = "~/.claude/skills"\n'),
    ("tools/lint-skills/check.py", 'P = "~/.claude/agents"\n'),
    # A spelling-adjacent path that is not toolkit-owned.
    ("partials/a.sh", 'cat "$HOME/.claude/adlc/plugin-root"\nc=~/.claude/.global-next-req\n'),
    # A preset or template that copies through ToolkitRoot.
    ("presets/x.yml", '#   cp "$ADLC_TOOLKIT_ROOT/presets/x.yml" .adlc/config.yml\n'),
    ("templates/x.yml", "# the clone install.sh links into ~/.claude\n"),
    ("templates/x.md", f"```sh\n{check.TOOLKIT_ROOT_LINE}\n```\n"),
    # The same instruction-style comment outside presets/templates is a comment.
    ("partials/a.sh", "#   cp ~/.claude/skills/presets/x.yml .adlc/config.yml\n"),
    # Python: joins that are not the toolkit's directories, a join in a comment,
    # the join shape outside Python, and a test tree.
    ("tools/k/a.py", 'P = os.path.join(home, ".claude", "adlc", "config.yml")\n'),
    ("tools/k/a.py", 'P = os.path.join(home, ".claude", "skills-cache")\n'),
    ("tools/k/a.py", 'P = os.path.join(home, ".claude/skills.bak")\n'),
    ("tools/k/a.py", "P = os.path.join(home, '.claude', 'plugins', 'cache')\n"),
    ("tools/k/a.py", '# os.path.join(home, ".claude", "skills")\n'),
    ("tools/k/a.js", 'const p = path.join(home, ".claude", "skills");\n'),
    ("tools/k/tests/a.py", 'P = os.path.join(home, ".claude", "skills")\n'),
])
def test_benign_line_shapes_do_not_fire(rel, text):
    assert check.toolkit_path_findings(text, rel) == []


@pytest.mark.parametrize("rel, text", [
    # Near-miss variants of the root line are findings (byte-exact match).
    ("alpha/SKILL.md", f"```sh\n{check.TOOLKIT_ROOT_LINE} \n```\n"),
    ("alpha/SKILL.md", f"```sh\n{check.TOOLKIT_ROOT_LINE}  # root\n```\n"),
    ("alpha/SKILL.md",
     "```sh\n" + check.TOOLKIT_ROOT_LINE.replace('"$HOME/.claude/skills"', '"${HOME}/.claude/skills"')
     + "\n```\n"),
    # Near-miss variants of the default-expansion spelling are findings.
    ("partials/a.sh", "x=${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/a\n"),
    ("partials/a.sh", 'x="${ADLC_TOOLKIT_ROOT:-${HOME}/.claude/skills}/a"\n'),
    ("partials/a.sh", 'x="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"\n'),
    # The token is removed, the rest of the line is still checked.
    ("partials/a.sh", 'x="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/a"; y=~/.claude/agents\n'),
    # A trailing comment does not make a code line a comment line.
    ("partials/a.sh", "cat ~/.claude/skills/x  # read\n"),
    # A Markdown heading is not a comment, nor is a `#` line outside a shell fence.
    ("alpha/SKILL.md", "# Read ~/.claude/skills first\n"),
    # Code after a one-line block comment is checked.
    ("workflows/a.js", "/* ns */\nconst p = '~/.claude/agents';\n"),
    # A file named like an exception, at another path, is not excepted.
    ("tools/delegate/install.sh", 'cp x "$HOME/.claude/skills/x"\n'),
    ("partials/checks.py", 'P = "~/.claude/skills"\n'),
    # A directory merely containing the word is not a test tree.
    ("tools/k/contests/x.py", 'P = "~/.claude/skills"\n'),
    # The `$HOME` spellings of the agents directory.
    ("partials/a.sh", 'cat "$HOME/.claude/agents/reflector.md"\n'),
    ("agents/a.md", "Read `${HOME}/.claude/agents/a.md` inline.\n"),
    ("workflows/a.js", "const A = `${HOME:-}/.claude/agents`;\n"),
    # Under presets/ and templates/ a comment line is an instruction: no exemption.
    ("presets/x.yml", "#   cp ~/.claude/skills/presets/x.yml .adlc/config.yml\n"),
    ("presets/README.md", "```bash\n# cp ~/.claude/skills/presets/x.yml .adlc/config.yml\n```\n"),
    ("templates/config-template.yml", "# $HOME/.claude/skills on the symlink route\n"),
    ("templates/x-template.md", "```sh\n  # ${HOME}/.claude/agents\n```\n"),
    # Python: a path joined from parts, in each shape.
    ("tools/k/a.py", 'P = os.path.join(home, ".claude", "skills")\n'),
    ("tools/k/a.py", "P = Path.home() / '.claude' / 'agents' / 'reflector.md'\n"),
    ("tools/k/a.py", 'P = os.path.join(os.path.expanduser("~"), ".claude/skills", "ETHOS.md")\n'),
    ("tools/k/a.py", 'P = os.path.join(home, ".claude",\n  "x") + os.path.join(h, ".claude" , "agents")\n'),
])
def test_near_misses_fire(rel, text):
    findings = check.toolkit_path_findings(text, rel)
    assert len(findings) == 1, findings
    assert findings[0].check == CHECK


def test_one_finding_per_line_naming_every_spelling():
    findings = check.toolkit_path_findings('a=~/.claude/skills; b="$HOME/.claude/skills"\n', "partials/a.sh")
    assert [f.line for f in findings] == [1]
    assert "`~/.claude/skills`" in findings[0].message
    assert "`$HOME/.claude/skills`" in findings[0].message


def test_exception_literals_track_their_sources():
    by_kind = {}
    for e in check.TOOLKIT_PATH_EXCEPTIONS:
        by_kind.setdefault(e.kind, []).append(e.value)
    assert set(by_kind) == {"line", "token", "file", "comment", "tree", "marker"}
    assert by_kind["marker"] == ["adlc-home"]  # REQ-666 ADR-5: one marker, both checks
    assert by_kind["line"] == [check.TOOLKIT_ROOT_LINE, check.PROBE_PROJECT_SKILLS_LINE]
    # REQ-664's line is the probe's, verbatim: drift there is a finding, not a pass.
    probe = (Path(__file__).resolve().parents[2] / "adlc" / "harness_probe.py")
    assert check.PROBE_PROJECT_SKILLS_LINE in probe.read_text(encoding="utf-8").splitlines()
    # The token is the ADR-2 operand's prefix, so the two cannot drift apart.
    token, adlc_home_token = by_kind["token"]
    assert check.PARTIAL_SOURCE_OPERAND.startswith(token)
    assert adlc_home_token == "${ADLC_HOME:-$HOME/.claude}"  # REQ-666 BR-13
    assert by_kind["file"] == ["install.sh", *FILE_EXCEPTIONS, PROBE_EXCEPTION]
    assert by_kind["tree"] == ["tests", "fixtures"]


def test_readme_quotes_the_exception_list_by_name():
    readme = (LINT_DIR / "README.md").read_text(encoding="utf-8")
    assert "`no-harness-path`" in readme
    assert "TOOLKIT_PATH_EXCEPTIONS" in readme
    assert "REQ-666" in readme
    for e in check.TOOLKIT_PATH_EXCEPTIONS:
        if e.kind in ("file", "tree"):
            assert f"`{e.value}" in readme, e.value
    for surface in check.TOOLKIT_PATH_SURFACES:
        assert f"`{surface}`" in readme, surface


# --- the walk: arming, nested checkouts, the skipped-root case ---------------

def test_inert_outside_a_plugin_root(tmp_path):
    # A root built for another check: a skill and a literal read, no VERSION and
    # no .claude-plugin/, so it is not a plugin root and has no plugin surface.
    _write(tmp_path, "alpha/SKILL.md", "# alpha\n\n```sh\n. ~/.claude/skills/partials/x.sh\n```\n")
    assert check.scan_toolkit_path(tmp_path) == check.ToolkitPathScan([], {}, ())


def test_armed_by_the_manifest_directory_alone(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    _write(tmp_path, "partials/x.sh", ". ~/.claude/skills/partials/y.sh\n")
    scan = check.scan_toolkit_path(tmp_path)
    assert [f.file for f in scan.findings] == ["partials/x.sh"]


def test_nested_checkouts_and_hidden_dirs_are_not_walked(tmp_path):
    root = _stage(tmp_path)
    literal = '#!/bin/sh\n. ~/.claude/skills/partials/x.sh\n'
    for rel in (
        ".claude/worktrees/peer/alpha/SKILL.md",
        ".claude/worktrees/peer/tools/leak.py",
        ".worktrees/REQ-1/partials/leak.sh",
        "tools/.claude/worktrees/peer/tools/leak.py",
        "tools/kit/.worktrees/REQ-1/leak.sh",
        "tools/kit/node_modules/pkg/leak.js",
        "tools/kit/__pycache__/leak.py",
        "tools/.git/hooks/pre-commit",
        "partials/nested/leak.sh",
        "workflows/tests/leak.js",
    ):
        _write(root, rel, literal)
    assert _scan(root).findings == []


@pytest.mark.parametrize("parent", [".worktrees/REQ-669", ".claude/worktrees/peer", ".git/x"])
def test_root_inside_worktrees_is_scanned(tmp_path, parent):
    # LESSON-019's skipped-root case: the root's own components are never tested.
    outer = tmp_path / parent
    outer.mkdir(parents=True)
    root = _stage(outer)
    shutil.copy(FIXTURES / "literal-read-path.sh", root / "partials" / "literal-read-path.sh")
    scan = _scan(root)
    assert [(f.file, f.line) for f in scan.findings] == [("partials/literal-read-path.sh", 5)]


def test_symlink_out_of_root_is_not_followed(tmp_path):
    root = _stage(tmp_path / "in")
    outside = tmp_path / "outside.sh"
    outside.write_text(". ~/.claude/skills/partials/x.sh\n", encoding="utf-8")
    (root / "partials" / "escape.sh").symlink_to(outside)
    assert _scan(root).findings == []


def test_wired_into_run_and_main(tmp_path, capsys):
    root = _stage(tmp_path)
    shutil.copy(FIXTURES / "literal-read-path.sh", root / "partials" / "literal-read-path.sh")
    findings, scanned = check.run(root)
    assert scanned == 1
    assert [(f.file, f.line) for f in findings if f.check == CHECK] == [
        ("partials/literal-read-path.sh", 5)]
    assert check.main(["--root", str(root)]) > 0
    assert "partials/literal-read-path.sh:5: no-harness-path: " in capsys.readouterr().out


# --- BR-13 / BR-2: the real tree --------------------------------------------

def test_repo_root_clean_and_every_surface_scanned():
    scan = _scan(REPO_ROOT)
    assert scan.findings == [], "\n".join(f.format() for f in scan.findings)
    assert scan.excepted == tuple(sorted(FILE_EXCEPTIONS + (PROBE_EXCEPTION,)))
    # Floors from the tree this check landed on: 17 skills, 19 agents, 13 shell
    # partials. A walk that lost most of a family fails here, not only an empty one.
    assert scan.surfaces["*/SKILL.md"] >= 17
    assert scan.surfaces["agents/*.md"] >= 19
    assert scan.surfaces["partials/*.sh"] >= 13
    assert scan.surfaces["workflows/*.js"] >= 1
    findings, _ = check.run(REPO_ROOT)
    assert not [f for f in findings if f.check == CHECK]


def test_repo_presets_and_templates_are_read_without_the_comment_exemption():
    scan = _scan(REPO_ROOT)
    assert scan.surfaces["presets/*"] >= 2
    assert scan.surfaces["templates/*"] >= 8
    # The preset's copy instruction is a comment line, and it goes through
    # ToolkitRoot, matching the config template's.
    preset = (REPO_ROOT / "presets" / "ios-firebase-cloudrun.yml").read_text(encoding="utf-8")
    template = (REPO_ROOT / "templates" / "config-template.yml").read_text(encoding="utf-8")
    copy = '#   cp "$ADLC_TOOLKIT_ROOT/presets/ios-firebase-cloudrun.yml" .adlc/config.yml'
    assert copy in preset.splitlines() and copy in template.splitlines()
    # Put the retired spelling back and the comment line fires.
    old = preset.replace('"$ADLC_TOOLKIT_ROOT/presets/', "~/.claude/skills/presets/")
    findings = check.toolkit_path_findings(old, "presets/ios-firebase-cloudrun.yml")
    assert [f.line for f in findings] == [preset.splitlines().index(copy) + 1]


# --- tools/adlc/checks.py: the whole-file exception, held to its purpose ------

CHECKS_PY = REPO_ROOT / "tools" / "adlc" / "checks.py"
# The doctor functions that inspect the symlink install (REQ-669 ADR-7), and so
# name `~/.claude/skills` / `~/.claude/agents` on purpose. The file exception in
# TOOLKIT_PATH_EXCEPTIONS covers the whole file; this list is what it is for.
CHECKS_PY_INSPECTORS = frozenset({
    "_symlink_install",
    "check_doubled_install",
    # check_skills_symlink and check_agents_symlink left this list with REQ-654
    # (ADR-6): they walk `_mount_homes()` (Claude Code's directory, and
    # ADLC_HOME when it differs) and join "skills"/"agents" onto each, so no
    # line of theirs spells the symlink install any more. Fewer names, same rule.
})
# The doctor's own join shape: `os.path.join(_claude_home(), "skills")`.
_CLAUDE_HOME_JOIN_RE = re.compile(r"""_claude_home\(\)\s*,\s*["'](?:skills|agents)["']""")


def _checks_py_symlink_names(text: str) -> list[tuple[int, str | None]]:
    """``(line, enclosing top-level function or None)`` for every line of
    ``text`` that names the symlink install: a TOOLKIT_PATH_SPELLINGS entry, a
    Python `.claude`/`skills` join, or a `_claude_home()` join. Comment lines
    and docstrings count: a docstring is where the `_partial_path` fallback was
    described."""
    spans = [(n.lineno, n.end_lineno, n.name) for n in ast.parse(text).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not (any(s in line for s in check.TOOLKIT_PATH_SPELLINGS)
                or check.TOOLKIT_PATH_PY_JOIN_RE.search(line)
                or _CLAUDE_HOME_JOIN_RE.search(line)):
            continue
        owner = next((name for start, end, name in spans if start <= lineno <= end), None)
        out.append((lineno, owner))
    return out


def test_checks_py_names_the_symlink_install_only_where_it_inspects_it():
    """The committed checks.py names the symlink install only inside the
    functions that inspect it. ADR-2 replaced `_partial_path`'s
    `~/.claude/skills` fallback in this same file, which is where a regression
    would land, unseen by the whole-file exception."""
    names = _checks_py_symlink_names(CHECKS_PY.read_text(encoding="utf-8"))
    stray = [(line, owner) for line, owner in names if owner not in CHECKS_PY_INSPECTORS]
    assert stray == [], f"tools/adlc/checks.py names the symlink install outside {sorted(CHECKS_PY_INSPECTORS)}: {stray}"
    # Not vacuous: each named inspector does name it, so the list stays current.
    assert {owner for _line, owner in names} == CHECKS_PY_INSPECTORS


@pytest.mark.parametrize("regression", [
    '    legacy = os.path.join(_claude_home(), "skills", "partials", name)\n',
    '    legacy = os.path.expanduser("~/.claude/skills/partials/" + name)\n',
    '    legacy = os.path.join(os.path.expanduser("~"), ".claude", "skills", "partials", name)\n',
    '    # fall back to $HOME/.claude/skills/partials\n',
])
def test_checks_py_guard_fires_on_a_partial_path_fallback(regression):
    text = CHECKS_PY.read_text(encoding="utf-8")
    anchor = '    local = os.path.join(profile.repo_root, "partials", name)\n'
    assert text.count(anchor) == 1, "_partial_path changed shape; update the anchor"
    mutated = text.replace(anchor, anchor + regression)
    names = _checks_py_symlink_names(mutated)
    assert ("_partial_path" in {owner for _line, owner in names}), names
