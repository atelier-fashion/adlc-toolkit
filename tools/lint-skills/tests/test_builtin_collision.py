"""Test the builtin-collision check (REQ-669 BR-10, ADR-5, TASK-133).

Claude Code owns some of the toolkit's skill names (`BUILTIN_COLLISION_NAMES`).
On the plugin install a bare `/init` reaches the built-in, not `/adlc:init`, so
every instruction that names a watched skill prints both spellings on the same
line. `scan_builtin_collision` walks `BUILTIN_COLLISION_SURFACES` of a plugin
root and flags an instruction-style bare mention on a line without
`/adlc:<name>`. A noun mention (a heading, a table cell, "the `/init` skill
copies…") does not fire.

Fixture trees live under `fixtures/builtin-collision/`:

- `plugin-root/` is a benign plugin root with at least one file on every
  surface: dual spellings in each of the three forms conventions.md states,
  noun mentions, and bare instructions planted only under `tests/` and
  `fixtures/` trees. Its skill is stored as `SKILL.fixture.md` and renamed when
  the tree is staged into `tmp_path`, so neither the real-repo lint walk nor the
  plugin loader sees it.
- `run-init-first.md` holds the prerequisite sentence with a bare "Run `/init`
  first".

Every scan asserts the surfaces it found files on, so a fixture path that went
wrong fails instead of passing vacuously (LESSON-019).
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
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "builtin-collision"
SKILL_STAND_IN = "SKILL.fixture.md"
E2E_SCRIPT = REPO_ROOT / "tools" / "adlc" / "tests" / "e2e" / "plugin-sandbox.sh"
CONVENTIONS = REPO_ROOT / ".adlc" / "context" / "conventions.md"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402

CHECK = "builtin-collision"


def _stage(dest_parent: Path) -> Path:
    """Copy the benign plugin root under ``dest_parent``, skill stand-ins renamed."""
    src = FIXTURES / "plugin-root"
    assert src.is_dir(), f"fixture tree missing: {src}"
    dest = dest_parent / "plugin-root"
    shutil.copytree(src, dest)
    for stand_in in dest.rglob(SKILL_STAND_IN):
        stand_in.rename(stand_in.with_name("SKILL.md"))
    return dest


def _scan(root: Path) -> check.BuiltinCollisionScan:
    """Scan ``root``; fail unless every surface found at least one file."""
    scan = check.scan_builtin_collision(root)
    assert set(scan.surfaces) == set(check.BUILTIN_COLLISION_SURFACES)
    empty = [s for s, n in scan.surfaces.items() if n == 0]
    assert not empty, f"vacuous surface(s) under {root}: {empty} (LESSON-019)"
    assert all(f.check == CHECK for f in scan.findings)
    return scan


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fires(text: str, rel: str = "alpha/SKILL.md") -> list[check.Finding]:
    return check.builtin_collision_findings(text, rel)


# --- BR-10: a bare instruction fails -----------------------------------------

def test_bare_instruction_fires(tmp_path):
    root = _stage(tmp_path)
    shutil.copy(FIXTURES / "run-init-first.md", root / "partials" / "run-init-first.md")
    scan = _scan(root)
    assert [(f.file, f.line) for f in scan.findings] == [("partials/run-init-first.md", 3)]
    message = scan.findings[0].message
    assert "bare `/init`" in message
    assert "`/init` (`/adlc:init` on the plugin install)" in message
    assert "BUILTIN_COLLISION_NAMES" in message


@pytest.mark.parametrize("name", check.BUILTIN_COLLISION_NAMES)
def test_every_watched_name_fires(name):
    findings = _fires(f"Run `/{name}` first.\n")
    assert [f.line for f in findings] == [1]
    assert f"bare `/{name}`" in findings[0].message
    assert f"`/adlc:{name}` on the plugin install" in findings[0].message


@pytest.mark.parametrize("line", [
    # A verb right before the slash token, in the shapes the audit listed.
    "Run `/init` to vendor .adlc/ETHOS.md.",
    "haven't re-run `/init` since the toolkit shipped the partial.",
    "reports them `stale` in every consumer project until it re-runs `/init`.",
    "consider running /init to scaffold one",
    "recommend running `/init`.",
    "recommend `/init`.",
    "Re-running `/init` also removes them.",
    "Do NOT re-run `/review`.",
    "Ready for `/review`",
    "or proceed to `/review`",
    "Address these issues before `/review`",
    "ask the user whether to fix now or note for `/review`",
    "Type `/status` to see the dashboard.",
    "try /status",
    "invoke '/init'",
    'use "/review"',
    # A phrase right after it.
    "the user to run `/init` first",
    "`/init` there too",
    "— `/init` if missing",
    "and /init to refresh the vendored gate)",
    "/init to copy it down",
    "/init to set up the repo",
    # In a comment: an instruction a reader follows is still one.
    "# Copy this file to .adlc/config.yml in the repo where you run /init, then",
    "    // run /init first",
    # In a quoted runtime string and a `!` line.
    'echo "missing — run /init"',
    "!`test -f .adlc/ETHOS.md && echo present || echo absent — run /init`",
])
def test_instruction_shapes_fire(line):
    findings = _fires(line + "\n")
    assert len(findings) == 1, findings
    assert findings[0].check == CHECK


@pytest.mark.parametrize("line", [
    # The three dual-spelling forms conventions.md states.
    "Run `/init` (`/adlc:init` on the plugin install) first.",
    "re-run install.sh --with-delegation, and /init (/adlc:init on the plugin install) to refresh",
    "echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md",
    'Ready for `/review` (`/adlc:review` on the plugin install)',
    "Type `/status` (`/adlc:status` on the plugin install).",
    # The plugin spelling alone.
    "Run `/adlc:init` first.",
    # Noun mentions: headings, table cells, the skill as a subject or object.
    "# /init — Bootstrap ADLC Structure",
    "| `/init` | Bootstrap `.adlc/` structure in a new repo |",
    "| `/review` | Multi-agent code review |",
    "The `/init` skill copies the templates.",
    "Unlike `/status`, which reconstructs its view from the local checkout",
    "the formal `/review` step",
    "Consumer projects get a copy at `/init` time.",
    "When running under `/status`, this skill prints one line.",
    "Mirrors /review's gate.",
    "(New projects per the `/init` Step 6 policy don't copy templates locally.)",
    "`/spec` → `/validate` → `/reflect` → `/review` → `/wrapup`",
    # Path components and longer names are not a mention of the skill.
    "Read `$ADLC_TOOLKIT_ROOT/init/SKILL.md` before you run it.",
    "run init/SKILL.md first",
    "run `/initialize` first",
    "run `/init-repo` first",
    "run `/reviews` first",
    "run `/code-review` first",
    "run ./init first",
    # A name Claude Code does not own stays bare.
    "Run `/validate` first, then proceed to `/architect`.",
])
def test_dual_spellings_and_noun_mentions_do_not_fire(line):
    assert _fires(line + "\n") == []


def test_dual_spelling_and_noun_mention_clean(tmp_path):
    root = _stage(tmp_path)
    scan = _scan(root)
    assert scan.findings == [], "\n".join(f.format() for f in scan.findings)
    # The clean result is the dual spellings at work, not an empty fixture: with
    # each plugin spelling broken, the same files fire.
    broken = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if "/adlc:" not in text or check.builtin_collision_excepted_file(rel):
            continue
        assert _fires(text.replace("/adlc:", "/plugin:"), rel), rel
        broken += 1
    assert broken >= 10
    # The test and fixture trees hold bare instructions that fire anywhere else.
    for rel, elsewhere in {
        "tools/kit/tests/helper.py": "tools/kit/helper.py",
        "tools/kit/fixtures/sample.sh": "tools/kit/sample.sh",
    }.items():
        text = (root / rel).read_text(encoding="utf-8")
        assert check.builtin_collision_findings(text, rel) == [], rel
        assert check.builtin_collision_findings(text, elsewhere), elsewhere


def test_plugin_spelling_of_one_name_does_not_excuse_another():
    findings = _fires("Run `/init` (`/adlc:init` on the plugin install) first, then type `/status`.\n")
    assert len(findings) == 1
    assert findings[0].message.startswith("bare `/status` in an instruction")


def test_one_finding_per_line_naming_every_bare_name():
    findings = _fires("Run `/init` first, then proceed to `/review`.\nok\nready for /status\n")
    assert [f.line for f in findings] == [1, 3]
    assert "bare `/init`, `/review`" in findings[0].message


# One file per surface, each holding one bare instruction.
SURFACE_PLANTS = {
    "*/SKILL.md": ("beta/SKILL.md", "# beta\n\nRun `/init` first.\n"),
    "proceed/phase*.md": ("proceed/phase-9.md", "Do NOT re-run `/review`.\n"),
    "agents/*.md": ("agents/two.md", "# two\n\nTell the user to run `/init` first.\n"),
    "partials/*.sh": ("partials/two.sh", 'echo "run /init to vendor partials" >&2\n'),
    "partials/*.md": ("partials/two.md", "Projects that haven't re-run `/init` fall back.\n"),
    "workflows/*.js": ("workflows/two.js", "const NOTE = 'ready for /review';\n"),
    "tools/**": ("tools/kit/deep/more.py", 'FIX = "re-run /init to vendor partials"\n'),
    "proceed/*.md": ("proceed/notes.md", "Ready for `/review`.\n"),
    "workflows/*.md": ("workflows/NOTES.md", "To refresh it, re-run `/init`.\n"),
    "presets/*": ("presets/two.yml", "# Copy this file in the repo where you run /init, then\n"),
    "templates/*": ("templates/two-template.md", "Run `/init` first.\n"),
    "scripts/*": ("scripts/two", "#!/bin/sh\necho 'type /status' >&2\n"),
    "hooks/*": ("hooks/two.json", '{"_comment": "run /init first"}\n'),
    "ETHOS.md": ("ETHOS.md", "# Ethos\n\nRun `/init` to vendor this file.\n"),
    "tools/delegate/*": ("tools/delegate/NOTES.txt", "Re-run `/init` to refresh the gate.\n"),
    "README.md": ("README.md", "# Fixture\n\nIn any code repo, run `/init` first.\n"),
    "RELEASING.md": ("RELEASING.md", "2. Consumers re-sync: re-run `/init` to refresh them.\n"),
}


def test_surface_plants_cover_every_surface():
    assert set(SURFACE_PLANTS) == set(check.BUILTIN_COLLISION_SURFACES)


@pytest.mark.parametrize("surface", check.BUILTIN_COLLISION_SURFACES)
def test_bare_instruction_fires_on_every_surface(tmp_path, surface):
    root = _stage(tmp_path)
    before = _scan(root).surfaces[surface]
    rel, text = SURFACE_PLANTS[surface]
    replaced = (root / rel).is_file()
    _write(root, rel, text)
    scan = _scan(root)
    assert scan.surfaces[surface] == before + (0 if replaced else 1)
    assert [f.file for f in scan.findings] == [rel]


def test_a_file_two_surfaces_yield_is_read_once(tmp_path):
    root = _stage(tmp_path)
    # A code file under tools/delegate/ is on both `tools/**` and `tools/delegate/*`.
    _write(root, "tools/delegate/gate.sh", 'echo "re-run /init to refresh the gate" >&2\n')
    scan = _scan(root)
    assert [(f.file, f.line) for f in scan.findings] == [("tools/delegate/gate.sh", 1)]


def test_surfaces_are_listed_once():
    # presets/* and templates/* come from toolkit-path's surface now; listing them
    # again here would scan and count them twice.
    surfaces = check.BUILTIN_COLLISION_SURFACES
    assert len(surfaces) == len(set(surfaces)), surfaces
    assert {"presets/*", "templates/*"} <= set(check.TOOLKIT_PATH_SURFACES)


@pytest.mark.parametrize("rel", ["README.md", "RELEASING.md"])
def test_root_docs_are_on_the_surface(tmp_path, rel):
    """The two root docs a reader follows step by step are read; CHANGELOG.md,
    whose released entries are a record, is not."""
    root = _stage(tmp_path)
    _write(root, rel, "Re-run `/init` to refresh them.\n")
    _write(root, "CHANGELOG.md", "## [1.0.0]\n\n- Re-run `/init` to refresh them.\n")
    assert [f.file for f in _scan(root).findings] == [rel]
    _write(root, rel, "Re-run `/init` (`/adlc:init` on the plugin install) to refresh them.\n")
    assert _scan(root).findings == []
    assert "CHANGELOG.md" not in check.BUILTIN_COLLISION_SURFACES


def test_test_and_fixture_trees_are_not_read(tmp_path):
    root = _stage(tmp_path)
    for rel in (
        "partials/tests/x.test.sh",
        "tools/kit/tests/deep/x.py",
        "tools/kit/fixtures/x.sh",
        "tools/delegate/tests/x.py",
        "workflows/tests/x.test.js",
    ):
        _write(root, rel, "#!/bin/sh\n# run /init first\n")
    assert _scan(root).findings == []


# --- the walk: arming, nested checkouts, the skipped-root case ---------------

def test_inert_outside_a_plugin_root(tmp_path):
    _write(tmp_path, "alpha/SKILL.md", "# alpha\n\nRun `/init` first.\n")
    assert check.scan_builtin_collision(tmp_path) == check.BuiltinCollisionScan([], {})


def test_armed_by_the_manifest_directory_alone(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    _write(tmp_path, "partials/x.md", "Run `/init` first.\n")
    assert [f.file for f in check.scan_builtin_collision(tmp_path).findings] == ["partials/x.md"]


def test_nested_checkouts_and_hidden_dirs_are_not_walked(tmp_path):
    root = _stage(tmp_path)
    bare = "#!/bin/sh\necho 'run /init first'\n"
    for rel in (
        ".claude/worktrees/peer/alpha/SKILL.md",
        ".worktrees/REQ-1/partials/leak.sh",
        "tools/.claude/worktrees/peer/tools/leak.py",
        "tools/kit/node_modules/pkg/leak.js",
        "tools/kit/__pycache__/leak.py",
        "partials/nested/leak.sh",
    ):
        _write(root, rel, bare)
    assert _scan(root).findings == []


@pytest.mark.parametrize("parent", [".worktrees/REQ-669", ".claude/worktrees/peer"])
def test_root_inside_worktrees_is_scanned(tmp_path, parent):
    outer = tmp_path / parent
    outer.mkdir(parents=True)
    root = _stage(outer)
    shutil.copy(FIXTURES / "run-init-first.md", root / "partials" / "run-init-first.md")
    assert [(f.file, f.line) for f in _scan(root).findings] == [("partials/run-init-first.md", 3)]


def test_symlink_out_of_root_is_not_followed(tmp_path):
    root = _stage(tmp_path / "in")
    outside = tmp_path / "outside.md"
    outside.write_text("Run `/init` first.\n", encoding="utf-8")
    (root / "partials" / "escape.md").symlink_to(outside)
    assert _scan(root).findings == []


def test_wired_into_run_and_main(tmp_path, capsys):
    root = _stage(tmp_path)
    shutil.copy(FIXTURES / "run-init-first.md", root / "partials" / "run-init-first.md")
    findings, scanned = check.run(root)
    assert scanned == 1
    assert [(f.file, f.line) for f in findings if f.check == CHECK] == [("partials/run-init-first.md", 3)]
    assert check.main(["--root", str(root)]) > 0
    assert "partials/run-init-first.md:3: builtin-collision: " in capsys.readouterr().out


# --- the rule's sources agree ------------------------------------------------

def test_watched_names_are_toolkit_skills():
    assert check.BUILTIN_COLLISION_NAMES == ("init", "status", "review")
    for name in check.BUILTIN_COLLISION_NAMES:
        assert (REPO_ROOT / name / "SKILL.md").is_file(), name


def _e2e_literal(name: str) -> str:
    """The literal value of ``<name> = (...)`` or ``<name> = [...]`` in the e2e
    script's embedded helpers."""
    text = E2E_SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"^%s = ([(\[].*?[)\]])$" % name, text, re.M | re.S)
    assert m, f"{name} not found in {E2E_SCRIPT.name}"
    return ast.literal_eval(m.group(1))


def test_instruction_patterns_match_the_e2e_audit():
    # The lint and `builtin_collision_static` must agree on what an instruction is,
    # or a clean lint could still leave the e2e audit a bare line to fail on.
    assert _e2e_literal("INSTR_VERB") == check.BUILTIN_COLLISION_VERB_RE
    assert _e2e_literal("INSTR_TAIL") == check.BUILTIN_COLLISION_TAIL_RE


def test_e2e_shipped_families_are_on_the_surface():
    shipped = _e2e_literal("SHIPPED")
    # `tools/adlc/*.py` is code under `tools/**`; every other family is listed.
    covered = set(check.BUILTIN_COLLISION_SURFACES) | {"tools/adlc/*.py"}
    assert set(shipped) <= covered, set(shipped) - covered


def test_conventions_and_readme_state_the_rule():
    conventions = CONVENTIONS.read_text(encoding="utf-8")
    assert "## Skill names Claude Code also owns" in conventions
    assert "`` `/init` (`/adlc:init` on the plugin install) ``" in conventions
    assert "`/init (/adlc:init on the plugin install)`" in conventions
    assert "`/init, or /adlc:init on the plugin install`" in conventions
    assert "BUILTIN_COLLISION_NAMES" in conventions
    readme = (LINT_DIR / "README.md").read_text(encoding="utf-8")
    assert "`builtin-collision`" in readme
    assert "BUILTIN_COLLISION_NAMES" in readme
    for surface in check.BUILTIN_COLLISION_SURFACES:
        assert f"`{surface}`" in readme, surface


# --- BR-10: the real tree ----------------------------------------------------

def test_repo_root_clean_and_every_surface_scanned():
    scan = _scan(REPO_ROOT)
    assert scan.findings == [], "\n".join(f.format() for f in scan.findings)
    # Floors from the tree this check landed on: 17 skills, 19 agents, 13 shell
    # partials, 8 templates. A walk that lost most of a family fails here.
    assert scan.surfaces["*/SKILL.md"] >= 17
    assert scan.surfaces["agents/*.md"] >= 19
    assert scan.surfaces["partials/*.sh"] >= 13
    assert scan.surfaces["templates/*"] >= 8
    assert scan.surfaces["README.md"] == 1 and scan.surfaces["RELEASING.md"] == 1
    findings, _ = check.run(REPO_ROOT)
    assert not [f for f in findings if f.check == CHECK]
