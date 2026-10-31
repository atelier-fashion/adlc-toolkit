"""REQ-665 BR-7: `manifest-parity`, across every harness in `MANIFEST_REGISTRY`.

`manifest-parity` absorbs REQ-669's check (ADR-1), so that check's own cases stay
in `test_plugin_manifest.py`; this file holds one firing test per BR-7 rule, and
the committed checkout is every rule's must-not-fire case.

Two kinds of root: `_ok` copies the `ok` fixture, a small tree with agents, and
`_checkout_copy` copies the committed manifests and skills, which is the
requirement's "sandbox copy". Neither is the checkout, and a command these tests
spawn runs with its `cwd` in the sandbox, because the lint reads repository paths
(LESSON-745).
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plugin-manifest"
SANDBOX_SCRIPT = REPO_ROOT / "tools" / "adlc" / "tests" / "e2e" / "plugin-sandbox.sh"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402
from .test_plugin_manifest import SKILL_STAND_IN, _name_rules, _read, _write  # noqa: E402

CLAUDE = ".claude-plugin/plugin.json"
CURSOR = ".cursor-plugin/plugin.json"
COPILOT = ".github/plugin/plugin.json"
EVERY_MANIFEST = (CLAUDE, CURSOR, COPILOT)
EMPTY_ENTRIES = (CURSOR, COPILOT)
# BR-7's rule names, each with a firing test below.
BR7_RULES = {
    "set-incomplete", "unparseable", "name-mismatch", "version-mismatch",
    "skill-missing", "skill-extra", "dangling-entry", "agents-ref-invalid",
    "hooks-ref-invalid", "path-missing", "unknown-key", "machine-path", "execution-key",
}
ENTRIES = {entry.path: entry for entry in check.MANIFEST_REGISTRY}
# One path key each manifest documents.
PATH_KEY_SAMPLES = [(CLAUDE, "commands"), (CURSOR, "rules"), (COPILOT, "commands")]


def _ok(tmp_path: Path) -> Path:
    """The `ok` fixture, in a sandbox, with its skill stand-ins renamed."""
    root = tmp_path / "ok"
    shutil.copytree(FIXTURES / "ok", root)
    for stand_in in root.rglob(SKILL_STAND_IN):
        stand_in.rename(stand_in.with_name("SKILL.md"))
    return root


def _checkout_copy(tmp_path: Path) -> Path:
    """The committed manifests, VERSION and skills, in a sandbox."""
    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    for entry in check.MANIFEST_REGISTRY:
        for rel in (entry.path, *entry.companions):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / rel, root / rel)
    shutil.copy(REPO_ROOT / "VERSION", root / "VERSION")
    for skill in check._plugin_root_skill_dirs(REPO_ROOT):
        (root / skill).mkdir()
        shutil.copy(REPO_ROOT / skill / "SKILL.md", root / skill / "SKILL.md")
    return root


def _scan(root: Path) -> list:
    """`manifest-parity` findings; fails if nothing was read (LESSON-019)."""
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned > 0, f"vacuous scan under {root}"
    assert all(f.check == "manifest-parity" for f in findings)
    return findings


def _rule(finding) -> str:
    return finding.message.split(":", 1)[0]


def _rules(root: Path, rule: str) -> list:
    return [f for f in _scan(root) if _rule(f) == rule]


def _edit(root: Path, rel: str, changes: dict) -> None:
    manifest = _read(root, rel)
    manifest.update(changes)
    _write(root, rel, manifest)


def _drop(root: Path, rel: str, key: str) -> None:
    manifest = _read(root, rel)
    del manifest[key]
    _write(root, rel, manifest)


def _add_skill(root: Path, name: str) -> None:
    (root / name).mkdir()
    (root / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")


# --- BR-1: the set ------------------------------------------------------------

def test_registry_is_the_set():
    rows = [(e.harness, e.path, e.companions, e.agents, e.hooks, e.name_rules)
            for e in check.MANIFEST_REGISTRY]
    assert rows == [
        ("claude", CLAUDE, (check.MARKETPLACE_MANIFEST,), "canonical", "default", True),
        ("cursor", CURSOR, (), "empty", "empty", False),
        ("copilot", COPILOT, (), "empty", "empty", False),
    ]
    assert check.PLUGIN_MANIFEST_CHECK == "manifest-parity"


def test_committed_manifests_are_clean(tmp_path):
    """AC-1 / BR-1, and the must-not-fire case of every rule."""
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    claude = _read(REPO_ROOT, CLAUDE)
    for rel in EVERY_MANIFEST:
        tool = subprocess.run(
            [sys.executable, "-m", "json.tool", str(REPO_ROOT / rel)],
            cwd=tmp_path, capture_output=True, text=True)
        assert tool.returncode == 0, tool.stderr
        manifest = _read(REPO_ROOT, rel)
        assert manifest["name"] == "adlc"
        assert manifest["version"] == version
        assert manifest["skills"] == "./"
        assert not re.search(r"/Users|/home|\$HOME", (REPO_ROOT / rel).read_text(encoding="utf-8"))
    # Exactly these keys, in both new manifests (BR-3, BR-4 and the task's list).
    for rel in EMPTY_ENTRIES:
        assert _read(REPO_ROOT, rel) == {
            "name": "adlc",
            "version": version,
            "description": claude["description"].replace(" for Claude Code", ""),
            "author": {"name": "Atelier Fashion"},
            "license": "MIT",
            "repository": claude["repository"],
            "skills": "./",
            "agents": [],
            "hooks": {},
        }
        assert "Claude Code" not in _read(REPO_ROOT, rel)["description"]
    assert not os.path.lexists(REPO_ROOT / "skills")
    assert check.scan_plugin_manifest(REPO_ROOT) == ([], 4)


# --- BR-7(a), (g): set-incomplete, path-missing -------------------------------

def test_set_incomplete_and_path_missing(tmp_path):
    """AC-4, whole: one manifest, every manifest, a consumer repo, a key, a companion."""
    for entry in check.MANIFEST_REGISTRY:
        root = _checkout_copy(tmp_path / entry.harness)
        (root / entry.path).unlink()
        findings, scanned = check.scan_plugin_manifest(root)
        assert scanned == 3
        assert [(_rule(f), f.file) for f in findings] == [("set-incomplete", entry.path)]
        assert "missing" in findings[0].message and entry.path in findings[0].message

    # Every manifest gone from a versioned skills root: never a silent pass (LESSON-019).
    root = _checkout_copy(tmp_path / "every")
    for directory in (".claude-plugin", ".cursor-plugin", ".github"):
        shutil.rmtree(root / directory)
    assert check.is_plugin_root(root)
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned == 0
    assert sorted((_rule(f), f.file) for f in findings) == sorted(
        [("set-incomplete", rel) for rel in EVERY_MANIFEST]
        + [("path-missing", check.MARKETPLACE_MANIFEST)])

    # A consumer repo that never had manifests is inert.
    consumer = tmp_path / "consumer"
    (consumer / "docs").mkdir(parents=True)
    (consumer / "README.md").write_text("# a consumer repo\n", encoding="utf-8")
    assert check.scan_plugin_manifest(consumer) == ([], 0)
    # So is one with a Cursor or Copilot plugin of its own: neither directory arms it.
    for rel in EMPTY_ENTRIES:
        (consumer / rel).parent.mkdir(parents=True)
        (consumer / rel).write_text('{"name": "theirs"}\n', encoding="utf-8")
    assert check.scan_plugin_manifest(consumer) == ([], 0)

    # A key pointing at nothing, and a missing companion.
    root = _checkout_copy(tmp_path / "paths")
    _edit(root, CURSOR, {"commands": "./no-such-commands"})
    (root / check.MARKETPLACE_MANIFEST).unlink()
    findings = _rules(root, "path-missing")
    assert sorted(f.file for f in findings) == sorted([check.MARKETPLACE_MANIFEST, CURSOR])
    assert len(_scan(root)) == 2


def test_set_incomplete_remediation_restores_the_file(tmp_path):
    """LESSON-572: the command in the message is run as written."""
    root = _checkout_copy(tmp_path / "repo")
    env = {**os.environ, "HOME": str(tmp_path / "home"), "GIT_CONFIG_NOSYSTEM": "1"}
    (tmp_path / "home").mkdir()
    git = ["git", "-c", "user.name=adlc-test", "-c", "user.email=adlc-test@example.invalid",
           "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "sandbox"]):
        subprocess.run(git + args, cwd=root, env=env, check=True)
    (root / CURSOR).unlink()
    finding, = _rules(root, "set-incomplete")
    command = re.search(r"`(git checkout [^`]+)`", finding.message).group(1)
    subprocess.run(command.split(), cwd=root, env=env, check=True)
    assert _scan(root) == []


_PATH_CASES = [(e.path, key) for e in check.MANIFEST_REGISTRY
               for key in check.MANIFEST_PATH_KEYS
               if key in e.keys and getattr(e, key, "") != "empty"]


@pytest.mark.parametrize("rel, key", _PATH_CASES)
def test_path_missing_on_every_path_key(tmp_path, rel, key):
    root = _ok(tmp_path)
    _edit(root, rel, {key: "./no/such/path"})
    string_form = _rules(root, "path-missing")
    assert [f.file for f in string_form] == [rel]
    assert f"`{key}`" in string_form[0].message and '"./no/such/path"' in string_form[0].message
    _edit(root, rel, {key: ["./alpha", "./no/such/path"]})
    assert [f.file for f in _rules(root, "path-missing")] == [rel]


@pytest.mark.parametrize("value", [
    "../", "../outside", "./../outside", "./alpha/../../outside", "VERSION", "",
    "https://example.com/x.json",
])
@pytest.mark.parametrize("rel, key", PATH_KEY_SAMPLES)
def test_path_outside_the_checkout_or_without_its_prefix(tmp_path, rel, key, value):
    """BR-7(g): `..` exists on the author's machine and dangles on every install."""
    root = _ok(tmp_path)
    (tmp_path / "outside").mkdir()
    _edit(root, rel, {key: value})
    finding, = _scan(root)
    assert _rule(finding) == "path-missing" and "not a `./` path" in finding.message


def test_a_nul_in_a_path_is_a_finding_not_a_traceback(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"rules": "./a\x00b"})
    assert [_rule(f) for f in _scan(root)] == ["path-missing"]


def test_a_url_stands_in_for_a_path_on_an_image_key_only(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"logo": "https://example.com/logo.png"})
    assert _scan(root) == []


@pytest.mark.parametrize("value", [5, True, [5], ["./alpha", False]])
@pytest.mark.parametrize("rel, key", PATH_KEY_SAMPLES)
def test_a_path_key_holding_a_scalar(tmp_path, rel, key, value):
    root = _ok(tmp_path)
    _edit(root, rel, {key: value})
    finding, = _scan(root)
    assert _rule(finding) == "path-missing" and "not a path" in finding.message


def test_dot_dot_through_a_symlink_is_refused_before_it_is_collapsed(tmp_path):
    # Collapsing `lnk/..` lexically would read `x`, which is not what opening it reads.
    root = _ok(tmp_path)
    (tmp_path / "outside").mkdir()
    (root / "lnk").symlink_to(tmp_path / "outside")
    (root / "x").write_text("", encoding="utf-8")
    _edit(root, CLAUDE, {"commands": "./lnk/../x"})
    assert [_rule(f) for f in _scan(root)] == ["path-missing"]


def test_a_skill_directory_through_a_symlink_out_of_the_checkout(tmp_path):
    root = _ok(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("---\nname: gamma\n---\n", encoding="utf-8")
    (root / "gamma").symlink_to(outside)
    finding, = _scan(root)
    assert _rule(finding) == "skill-extra" and finding.file == "gamma/"


@pytest.mark.parametrize("rel, key", [(CURSOR, "hooks"), (CURSOR, "agents"),
                                      (COPILOT, "hooks"), (COPILOT, "agents")])
def test_the_shape_rule_alone_reads_a_path_on_an_empty_key(tmp_path, rel, key):
    # `add that path` would point the harness at what BR-3 and BR-4 forbid.
    root = _ok(tmp_path)
    _edit(root, rel, {key: "./nope"})
    assert [_rule(f) for f in _scan(root)] == [f"{key}-ref-invalid"]


def test_path_through_a_symlink_out_of_the_checkout(tmp_path):
    root = _ok(tmp_path)
    (tmp_path / "outside").mkdir()
    (root / "elsewhere").symlink_to(tmp_path / "outside")
    _edit(root, CLAUDE, {"commands": "./elsewhere"})
    assert [_rule(f) for f in _scan(root)] == ["path-missing"]


def test_a_manifest_that_is_a_symlink_out_of_the_checkout(tmp_path):
    root = _ok(tmp_path)
    (tmp_path / "plugin.json").write_text((root / CURSOR).read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (root / CURSOR).unlink()
    (root / CURSOR).symlink_to(tmp_path / "plugin.json")
    finding, = _scan(root)
    assert _rule(finding) == "unparseable" and finding.file == CURSOR


@pytest.mark.parametrize("depth", [600, 900, 5000])
def test_a_deep_manifest_is_a_result_not_a_traceback(tmp_path, depth):
    root = _ok(tmp_path)
    text = (root / CURSOR).read_text(encoding="utf-8").rstrip()
    deep = '"metadata": ' + "[" * depth + "]" * depth
    (root / CURSOR).write_text(text[:-1] + ", " + deep + "}\n", encoding="utf-8")
    assert {f.file for f in _scan(root)} == {CURSOR}


@pytest.mark.parametrize("value", [
    "./alpha", "./agents/one.md", ["./alpha"], {}, [],
])
@pytest.mark.parametrize("rel, key", PATH_KEY_SAMPLES)
def test_path_missing_stays_quiet(tmp_path, rel, key, value):
    root = _ok(tmp_path)
    _edit(root, rel, {key: value})
    assert _scan(root) == []


# --- BR-7(b): unparseable -----------------------------------------------------

@pytest.mark.parametrize("rel", [*EVERY_MANIFEST, check.MARKETPLACE_MANIFEST])
@pytest.mark.parametrize("raw, needle", [
    (b'{"name": "adlc", "name": "adlc"}\n', "repeated JSON key"),
    (b'{"name": "adlc",}\n', "not valid JSON"),
    (b'{"name": NaN}\n', "NaN"),
    (b'["adlc"]\n', "JSON object"),
    (b'\xff\xfe\n', "UTF-8"),
])
def test_unparseable_is_one_finding_and_the_rest_still_run(tmp_path, rel, raw, needle):
    root = _ok(tmp_path)
    (root / rel).write_bytes(raw)
    finding, = _scan(root)
    assert _rule(finding) == "unparseable" and needle in finding.message and finding.file == rel
    # The other manifests are still read: a second, separate drift is still seen.
    other = next(m for m in EVERY_MANIFEST if m != rel)
    _edit(root, other, {"version": "9.9.9"})
    assert sorted(_rule(f) for f in _scan(root)) == ["unparseable", "version-mismatch"]


# --- BR-7(c): name-mismatch ---------------------------------------------------

@pytest.mark.parametrize("rel", EMPTY_ENTRIES)
def test_name_mismatch(tmp_path, rel):
    root = _ok(tmp_path)
    _edit(root, rel, {"name": "adlc-other"})
    finding, = _scan(root)
    assert _rule(finding) == "name-mismatch" and finding.file == rel
    assert '"adlc-other"' in finding.message and '`"name": "adlc"`' in finding.message


def test_name_is_the_literal_not_the_first_name_found(tmp_path):
    # `session-start.sh` and `adlc doctor` recognise a copy by `adlc`, so the Claude
    # manifest is the one in the wrong, and the remedy must not spread its name.
    root = _ok(tmp_path)
    _edit(root, CLAUDE, {"name": "adlc-other"})
    finding, = _rules(root, "name-mismatch")
    assert finding.file == CLAUDE and '`"name": "adlc"`' in finding.message


def test_a_set_renamed_in_step_is_still_wrong(tmp_path):
    """BR-1, AC-1: every manifest and the marketplace entry agree, on the wrong name."""
    root = _ok(tmp_path)
    for rel in EVERY_MANIFEST:
        _edit(root, rel, {"name": "zzz"})
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["plugins"][0]["name"] = "zzz"
    _write(root, check.MARKETPLACE_MANIFEST, market)
    assert sorted(f.file for f in _rules(root, "name-mismatch")) == sorted(EVERY_MANIFEST)
    assert [f.file for f in _scan(root) if "marketplace entry" in f.message] == [
        check.MARKETPLACE_MANIFEST]


@pytest.mark.parametrize("value", [None, 7, ""])
@pytest.mark.parametrize("rel", EVERY_MANIFEST)
def test_name_absent_or_not_a_string_is_a_mismatch(tmp_path, rel, value):
    root = _ok(tmp_path)
    if value is None:
        _drop(root, rel, "name")
    else:
        _edit(root, rel, {"name": value})
    finding, = _scan(root)
    assert _rule(finding) == "name-mismatch" and finding.file == rel


def test_no_name_anywhere_is_still_a_finding_per_manifest(tmp_path):
    root = _ok(tmp_path)
    for rel in EVERY_MANIFEST:
        _drop(root, rel, "name")
    assert sorted(f.file for f in _rules(root, "name-mismatch")) == sorted(EVERY_MANIFEST)


def test_name_rules_follow_the_registry(tmp_path):
    root = _ok(tmp_path)
    for rel in EVERY_MANIFEST:
        _edit(root, rel, {"name": "claude-adlc"})
    fired = [f for f in _scan(root) if "reserved prefix" in f.message]
    assert [f.file for f in fired] == [e.path for e in check.MANIFEST_REGISTRY if e.name_rules]


# --- BR-7(d) / BR-5: version-mismatch -----------------------------------------

def test_version_mismatch_per_manifest(tmp_path):
    """AC-3: one finding per manifest, naming the file and the expected value."""
    root = _checkout_copy(tmp_path)
    original = (root / "VERSION").read_bytes()
    assert _scan(root) == []
    (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    findings = _scan(root)
    assert sorted(f.file for f in findings) == sorted(EVERY_MANIFEST)
    for finding in findings:
        assert _rule(finding) == "version-mismatch"
        assert '"9.9.9"' in finding.message and finding.file in finding.message
        prefix = f"{finding.file}:{finding.line}: manifest-parity: version-mismatch: "
        assert finding.format().startswith(prefix)
    (root / "VERSION").write_bytes(original)
    assert _scan(root) == []


@pytest.mark.parametrize("rel", EVERY_MANIFEST)
def test_one_manifest_behind_is_one_finding(tmp_path, rel):
    root = _ok(tmp_path)
    _edit(root, rel, {"version": "1.2.2"})
    finding, = _scan(root)
    assert _rule(finding) == "version-mismatch" and finding.file == rel
    assert '`"version": "1.2.3"`' in finding.message


def test_version_file_missing_is_one_finding_not_one_per_manifest(tmp_path):
    root = _ok(tmp_path)
    (root / "VERSION").unlink()
    finding, = _scan(root)
    assert _rule(finding) == "version-mismatch" and finding.file == "VERSION"


@pytest.mark.parametrize("content", ["", " \n\n"])
def test_an_empty_version_file_is_missing_not_a_version(tmp_path, content):
    # A remedy of `set "version": ""` would clear the lint with no version anywhere.
    root = _ok(tmp_path)
    (root / "VERSION").write_text(content, encoding="utf-8")
    finding, = _scan(root)
    assert _rule(finding) == "version-mismatch" and finding.file == "VERSION"


# --- BR-7(e) / BR-2: skill-missing, skill-extra, dangling-entry ---------------

def _apply_add(root: Path, message: str) -> str:
    """Do what a `skill-missing` remediation says, verbatim; returns the file it named."""
    entry, rel = re.search(r'add "([^"]+)" to `skills` in (\S+),', message).groups()
    manifest = _read(root, rel)
    manifest["skills"].append(entry)
    _write(root, rel, manifest)
    return rel


def _apply_remove(root: Path, message: str) -> str:
    """Do what a `dangling-entry` or `skill-extra` remediation says, verbatim."""
    entry, rel = re.search(r'remove "([^"]+)" from `skills` in (\S+) \(', message).groups()
    manifest = _read(root, rel)
    manifest["skills"].remove(entry)
    _write(root, rel, manifest)
    return rel


@pytest.mark.parametrize("rel", EVERY_MANIFEST)
def test_skill_added_and_removed(tmp_path, rel):
    """AC-2."""
    root = _checkout_copy(tmp_path)
    skills = check._plugin_root_skill_dirs(root)

    # A `"./"` manifest needs no edit through either change.
    assert _read(root, rel)["skills"] == "./"
    _add_skill(root, "zzz-test")
    assert _scan(root) == []
    shutil.rmtree(root / "zzz-test")
    assert _scan(root) == []

    # A manifest that enumerates: the new skill fires, and the fix returns it to clean.
    _edit(root, rel, {"skills": [f"./{skill}" for skill in skills]})
    assert _scan(root) == []
    _add_skill(root, "zzz-test")
    finding, = _scan(root)
    assert _rule(finding) == "skill-missing" and finding.file == rel
    assert "`zzz-test/`" in finding.message and rel in finding.message
    assert _apply_add(root, finding.message) == rel
    assert _scan(root) == []

    # A directory removed while the manifest still names it.
    shutil.rmtree(root / skills[0])
    finding, = _scan(root)
    assert _rule(finding) == "dangling-entry" and finding.file == rel
    assert f'"./{skills[0]}"' in finding.message
    assert _apply_remove(root, finding.message) == rel
    assert _scan(root) == []


@pytest.mark.parametrize("rel", EMPTY_ENTRIES)
def test_no_skills_field_on_every_manifest(tmp_path, rel):
    root = _ok(tmp_path)
    _drop(root, rel, "skills")
    finding, = _scan(root)
    assert _rule(finding) == "skill-missing" and finding.file == rel
    assert "no `skills` field" in finding.message and '`"skills": "./"`' in finding.message


@pytest.mark.parametrize("value", [7, {"path": "./"}, ["./alpha", 7]])
def test_skills_of_the_wrong_type(tmp_path, value):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"skills": value})
    finding, = _scan(root)
    assert _rule(finding) == "skill-missing" and "path string" in finding.message


@pytest.mark.parametrize("rel", EVERY_MANIFEST)
@pytest.mark.parametrize("extra", ["./agents", "./scripts/"])
def test_entry_with_no_skill_md_is_skill_extra(tmp_path, rel, extra):
    root = _ok(tmp_path)
    _edit(root, rel, {"skills": ["./alpha", "./beta", extra]})
    finding, = _scan(root)
    assert _rule(finding) == "skill-extra" and finding.file == rel
    assert json.dumps(extra) in finding.message
    assert _apply_remove(root, finding.message) == rel
    assert _scan(root) == []


@pytest.mark.parametrize("nested", ["./tools/nested", "./.hidden"])
def test_entry_outside_the_skill_set_is_skill_extra(tmp_path, nested):
    # It holds a SKILL.md, but BR-7(e) asks for exactly the SkillSet: one root level,
    # no hidden directories, the loader's own rule.
    root = _ok(tmp_path)
    (root / nested / "SKILL.md").parent.mkdir(parents=True)
    (root / nested / "SKILL.md").write_text("# not in the set\n", encoding="utf-8")
    _edit(root, CURSOR, {"skills": ["./alpha", "./beta", nested]})
    assert [_rule(f) for f in _scan(root)] == ["skill-extra"]


@pytest.mark.parametrize("value", ["./no-such-dir", ["./no-such-dir"]])
def test_dangling_entry_in_either_form_with_or_without_skills(tmp_path, value):
    # LESSON-749: `path-missing` hands `skills` over, so the string form must be read
    # here too, including on a root with no skill for `skill-missing` to report.
    root = _ok(tmp_path)
    shutil.rmtree(root / "alpha")
    shutil.rmtree(root / "beta")
    _edit(root, COPILOT, {"skills": value})
    finding, = _scan(root)
    assert _rule(finding) == "dangling-entry" and finding.file == COPILOT


def test_entry_the_loader_refuses_is_still_read(tmp_path):
    # `zeta` has no `./`, so it reaches nothing, and naming no directory it dangles.
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"skills": ["./alpha", "./beta", "zeta"]})
    assert [_rule(f) for f in _scan(root)] == ["dangling-entry"]


@pytest.mark.parametrize("skills", [["alpha", "./alpha", "./beta"], ["./alpha", "beta", "./beta"],
                                    ["./alpha", "./beta", ""]])
def test_an_entry_the_loader_refuses_beside_its_twin_is_still_read(tmp_path, skills):
    # The first pass drops it, and it matches a skill directory: the second must not.
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"skills": skills})
    finding, = _scan(root)
    assert _rule(finding) == "dangling-entry" and "does not start with `./`" in finding.message


def test_a_file_entry_names_no_directory(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"skills": ["./alpha/SKILL.md", "./beta"]})
    assert sorted(_rule(f) for f in _scan(root)) == ["dangling-entry", "skill-missing"]


@pytest.mark.parametrize("kind", ["directory", "file", "symlink-to-dir", "dangling-symlink"])
def test_root_skills_dir_is_skill_extra(tmp_path, kind):
    """BR-2 / ADR-8: Claude Code scans a root `skills/` beside its `skills` key."""
    root = _ok(tmp_path)
    assert _scan(root) == []
    skills = root / "skills"
    if kind == "directory":
        skills.mkdir()
    elif kind == "file":
        skills.write_text("not a directory\n", encoding="utf-8")
    elif kind == "symlink-to-dir":
        skills.symlink_to(root / "alpha")
    else:
        skills.symlink_to(root / "no-such-dir")
    finding, = _scan(root)
    assert _rule(finding) == "skill-extra" and finding.file == "skills/"
    assert "double the catalog" in finding.message


# --- BR-7(f): agents-ref-invalid, hooks-ref-invalid ---------------------------

@pytest.mark.parametrize("rel", EMPTY_ENTRIES)
@pytest.mark.parametrize("value", ["absent", "./agents", ["./agents/one.md"], {}, None])
def test_agents_ref_invalid(tmp_path, rel, value):
    """BR-3: on Cursor and Copilot the key is present and `[]`, nothing else."""
    root = _ok(tmp_path)
    if value == "absent":
        _drop(root, rel, "agents")
    else:
        _edit(root, rel, {"agents": value})
    finding, = _scan(root)
    assert _rule(finding) == "agents-ref-invalid" and finding.file == rel
    assert ("absent" in finding.message) == (value == "absent")
    assert '`"agents": []`' in finding.message
    _edit(root, rel, {"agents": []})
    assert _scan(root) == []


def test_agents_canonical_keeps_the_requirement_669_rule(tmp_path):
    root = _ok(tmp_path)
    assert "agents" not in _read(root, CLAUDE)  # absent is clean
    assert _scan(root) == []
    _edit(root, CLAUDE, {"agents": ["./agents/one.md", "./agents/two.md"]})
    assert _scan(root) == []
    _edit(root, CLAUDE, {"agents": ["./agents/one.md"]})
    finding, = _scan(root)
    assert _rule(finding) == "agents-ref-invalid" and "`agents/two.md`" in finding.message
    _edit(root, CLAUDE, {"agents": 7})
    finding, = _scan(root)
    assert _rule(finding) == "agents-ref-invalid" and "path string" in finding.message


@pytest.mark.parametrize("rel", EMPTY_ENTRIES)
@pytest.mark.parametrize("value", ["absent", "./agents", [], {"SessionStart": []}, None])
def test_hooks_ref_invalid(tmp_path, rel, value):
    """BR-4: on Cursor and Copilot the key is present and `{}`, nothing else."""
    root = _ok(tmp_path)
    if value == "absent":
        _drop(root, rel, "hooks")
    else:
        _edit(root, rel, {"hooks": value})
    finding, = _scan(root)
    assert _rule(finding) == "hooks-ref-invalid" and finding.file == rel
    assert ("absent" in finding.message) == (value == "absent")
    assert '`"hooks": {}`' in finding.message
    _edit(root, rel, {"hooks": {}})
    assert _scan(root) == []


def test_hooks_default_has_no_shape_rule(tmp_path):
    root = _ok(tmp_path)
    assert "hooks" not in _read(root, CLAUDE)
    assert _scan(root) == []
    _edit(root, CLAUDE, {"hooks": {}})
    assert _scan(root) == []


# --- BR-7(j) / BR-4: execution-key --------------------------------------------

@pytest.mark.parametrize("value", [
    {"x": {"command": "./nope"}}, "./VERSION", "./no-such", {}, [],
])
@pytest.mark.parametrize("rel, key", [(e.path, k) for e in check.MANIFEST_REGISTRY
                                      for k in check.MANIFEST_EXEC_KEYS if k in e.keys])
def test_a_server_key_fires_in_any_form(tmp_path, rel, key, value):
    """Entities, `mcp_ref`: absent, so what it holds does not matter."""
    root = _ok(tmp_path)
    _edit(root, rel, {key: value})
    finding, = _scan(root)
    assert _rule(finding) == "execution-key" and f"`{key}`" in finding.message


@pytest.mark.parametrize("value", [
    {"build": {"command": "./nope"}}, [{"inline": "object"}], ["./alpha", {"inline": "object"}],
])
@pytest.mark.parametrize("rel, key", PATH_KEY_SAMPLES)
def test_an_inline_definition_fires(tmp_path, rel, key, value):
    root = _ok(tmp_path)
    _edit(root, rel, {key: value})
    assert [_rule(f) for f in _scan(root)] == ["execution-key"]


def test_an_undocumented_server_key_is_unknown_key_alone(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"extensions": "./VERSION"})
    assert [_rule(f) for f in _scan(root)] == ["unknown-key"]


@pytest.mark.parametrize("rel", check.MANIFEST_DEFAULT_EXEC_FILES)
def test_a_default_location_file_fires(tmp_path, rel):
    root = _ok(tmp_path)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text("{}\n", encoding="utf-8")
    finding, = _scan(root)
    assert _rule(finding) == "execution-key" and finding.file == rel


@pytest.mark.parametrize("key, value", [
    ("hooks", {"SessionStart": []}), ("strict", False), ("mcpServers", {}), ("adlcExtra", 1),
])
def test_the_marketplace_entry_holds_only_what_is_listed(tmp_path, key, value):
    root = _ok(tmp_path)
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["plugins"][0][key] = value
    _write(root, check.MARKETPLACE_MANIFEST, market)
    finding, = _scan(root)
    assert _rule(finding) == "unknown-key" and f'"{key}"' in finding.message


def test_the_marketplace_top_level_holds_only_what_is_listed(tmp_path):
    root = _ok(tmp_path)
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["allowCrossMarketplaceDependenciesOn"] = ["other"]
    _write(root, check.MARKETPLACE_MANIFEST, market)
    assert [_rule(f) for f in _scan(root)] == ["unknown-key"]


def test_inline_hooks_fire_where_the_key_is_left_to_its_default(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CLAUDE, {"hooks": {"SessionStart": [{"command": "./nope"}]}})
    finding, = _scan(root)
    assert _rule(finding) == "execution-key" and finding.file == CLAUDE


@pytest.mark.parametrize("rel", EMPTY_ENTRIES)
def test_inline_hooks_stay_with_the_shape_rule_where_it_applies(tmp_path, rel):
    root = _ok(tmp_path)
    _edit(root, rel, {"hooks": {"SessionStart": [{"command": "./nope"}]}})
    assert [_rule(f) for f in _scan(root)] == ["hooks-ref-invalid"]


# --- BR-7(h): unknown-key -----------------------------------------------------

@pytest.mark.parametrize("rel", EVERY_MANIFEST)
def test_unknown_key_per_harness(tmp_path, rel):
    """AC-12: on every committed manifest, with a remediation that removes it."""
    root = _checkout_copy(tmp_path)
    assert _scan(root) == []
    _edit(root, rel, {"adlcExtra": True})
    finding, = _scan(root)
    assert _rule(finding) == "unknown-key" and finding.file == rel
    assert f'remove "adlcExtra" from {rel}' in finding.message
    assert ENTRIES[rel].harness in finding.message
    lines = (root / rel).read_text(encoding="utf-8").splitlines()
    assert '"adlcExtra"' in lines[finding.line - 1]
    _drop(root, rel, "adlcExtra")
    assert _scan(root) == []


@pytest.mark.parametrize("key, value, documented_on", [
    ("displayName", "ADLC", CLAUDE),
    ("logo", "./VERSION", CURSOR),
    ("category", "development", COPILOT),
])
def test_a_key_is_documented_per_harness(tmp_path, key, value, documented_on):
    for rel in EVERY_MANIFEST:
        root = _ok(tmp_path / rel.replace("/", "_"))
        _edit(root, rel, {key: value})
        assert [_rule(f) for f in _scan(root)] == ([] if rel == documented_on else ["unknown-key"])


# --- BR-7(i): machine-path ----------------------------------------------------

@pytest.mark.parametrize("value", [
    "/opt/adlc", "~/adlc", "~", "$HOME/adlc", "${HOME}/adlc", "${HOME:-/tmp}/adlc",
    "see $HOME for this", "from /Users/someone/adlc", "from /home/someone/adlc",
    "(/home/someone/adlc)", "file:///Users/someone/adlc", "file:///opt/adlc",
    "file://localhost/Users/someone/adlc", "file:adlc", "ssh://example.com/home/adlc",
    "https://someone:secret@example.com/adlc", "http://example.com/adlc",
    "HTTP://example.com:8080/adlc", "https://?x", "https://#f", "https://:443",
    "https://example.com/ /Users/someone/adlc", "https://example.com/ $HOME/adlc",
    "see /USERS/someone", "x:/users/someone/y", "=/Users", "= /home", " /opt/adlc", " ~/adlc",
    " file:///opt/adlc", r"C:\Users\someone", r"\\server\share", "$USERPROFILE/adlc",
    "%USERPROFILE%/adlc", "%HOME%/adlc", "${env:HOME}/adlc", "~someone/adlc",
    "git@github.com:a/b.git", "ssh:git@github.com/x", "mailto:a@example.com",
    "data:text/html,x", "javascript:alert(1)",
])
@pytest.mark.parametrize("rel", EVERY_MANIFEST)
def test_machine_path_fires(tmp_path, rel, value):
    root = _ok(tmp_path)
    _edit(root, rel, {"homepage": value})
    finding, = _scan(root)
    assert _rule(finding) == "machine-path" and finding.file == rel
    assert "`homepage`" in finding.message
    lines = (root / rel).read_text(encoding="utf-8").splitlines()
    assert '"homepage"' in lines[finding.line - 1]


@pytest.mark.parametrize("value", [
    "https://github.com/atelier-fashion/adlc-toolkit",
    "https://example.com/home/adlc", "https://example.com/Users/adlc",
    "https://example.com/-/home/adlc", "HTTPS://example.com:8080/adlc",
    "https://example.com/adlc and more text", "Note: a word then a colon",
    "./home/adlc", "../Users/adlc", "a/home/b", "the home directory",
    "users and homes", "~name", "a~/b", "$HOMEBREW_PREFIX",
])
def test_machine_path_stays_quiet(tmp_path, value):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"homepage": value})
    assert _scan(root) == []


def test_machine_path_walks_every_string_value(tmp_path):
    root = _ok(tmp_path)
    _edit(root, COPILOT, {
        "author": {"name": "A", "url": "/Users/someone/site"},
        "keywords": ["fine", "$HOME/keyword"],
    })
    findings = _rules(root, "machine-path")
    assert len(findings) == 2 and {f.file for f in findings} == {COPILOT}
    assert "`author.url`" in findings[0].message and "`keywords[1]`" in findings[1].message


def test_machine_path_lands_on_its_key_when_the_value_repeats(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"homepage": "/opt/same", "repository": "/opt/same"})
    lines = (root / CURSOR).read_text(encoding="utf-8").splitlines()
    fired = {lines[f.line - 1].split(":")[0].strip() for f in _rules(root, "machine-path")}
    assert fired == {'"homepage"', '"repository"'}


def test_machine_path_lands_on_its_value_when_the_key_repeats(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CLAUDE, {"author": {"name": "A", "url": "https://example.com/a"},
                         "metadata": {"url": "/opt/deep"}})
    finding, = _scan(root)
    assert "/opt/deep" in (root / CLAUDE).read_text(encoding="utf-8").splitlines()[finding.line - 1]


def test_machine_path_reads_a_key_but_not_as_a_value(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CLAUDE, {"metadata": {"/Users/not-a-value": 1}})
    assert _scan(root) == []


def test_machine_path_reads_the_companion(tmp_path):
    root = _ok(tmp_path)
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["owner"]["url"] = "/Users/someone/site"
    _write(root, check.MARKETPLACE_MANIFEST, market)
    finding, = _scan(root)
    assert _rule(finding) == "machine-path" and finding.file == check.MARKETPLACE_MANIFEST


@pytest.mark.parametrize("rel, key", PATH_KEY_SAMPLES)
@pytest.mark.parametrize("value", ["/opt/no-such", ["/opt/no-such"], "~/no-such"])
def test_a_machine_path_on_a_path_key_is_reported_once(tmp_path, rel, key, value):
    # `path-missing` defers to the walk that reads every string, so it is seen once.
    root = _ok(tmp_path)
    _edit(root, rel, {key: value})
    assert [_rule(f) for f in _scan(root)] == ["machine-path"]


def test_a_machine_path_in_skills_is_reported_once(tmp_path):
    root = _ok(tmp_path)
    _edit(root, CURSOR, {"skills": ["./alpha", "./beta", "/opt/no-such"]})
    assert [_rule(f) for f in _scan(root)] == ["machine-path"]


# --- BR-7 as a whole ----------------------------------------------------------

def _set_incomplete(root):
    (root / CURSOR).unlink()


def _unparseable(root):
    (root / CURSOR).write_text("[]\n", encoding="utf-8")


def _duplicate_key(root):
    (root / CURSOR).write_text('{"name": "adlc", "name": "adlc"}\n', encoding="utf-8")


def _skills_entry(entry):
    return lambda root: _edit(root, COPILOT, {"skills": ["./alpha", "./beta", entry]})


FIRINGS = {
    "set-incomplete": [_set_incomplete],
    "unparseable": [_unparseable, _duplicate_key],
    "name-mismatch": [
        lambda root: _edit(root, CURSOR, {"name": "other"}),
        lambda root: _drop(root, CLAUDE, "name"),
    ],
    "version-mismatch": [
        lambda root: _edit(root, COPILOT, {"version": "0.0.0"}),
        lambda root: (root / "VERSION").unlink(),
    ],
    "skill-missing": [
        lambda root: _edit(root, COPILOT, {"skills": ["./alpha"]}),
        lambda root: _drop(root, COPILOT, "skills"),
    ],
    "skill-extra": [_skills_entry("./agents"), lambda root: (root / "skills").mkdir()],
    "dangling-entry": [_skills_entry("./no-such-dir")],
    "agents-ref-invalid": [lambda root: _drop(root, CURSOR, "agents")],
    "hooks-ref-invalid": [lambda root: _drop(root, COPILOT, "hooks")],
    "path-missing": [
        lambda root: _edit(root, CURSOR, {"commands": "./no-such-file"}),
        lambda root: (root / check.MARKETPLACE_MANIFEST).unlink(),
    ],
    "unknown-key": [lambda root: _edit(root, COPILOT, {"adlcExtra": True})],
    "machine-path": [lambda root: _edit(root, CURSOR, {"homepage": "/opt/adlc"})],
    "execution-key": [
        lambda root: _edit(root, CURSOR, {"mcpServers": {"x": {"command": "./nope"}}}),
        lambda root: _edit(root, COPILOT, {"commands": {"x": {"command": "./nope"}}}),
    ],
}
_FIRING_CASES = [(rule, i) for rule in sorted(FIRINGS) for i in range(len(FIRINGS[rule]))]


def test_every_br7_rule_is_in_the_table():
    assert set(FIRINGS) == BR7_RULES


@pytest.mark.parametrize("rule, index", _FIRING_CASES)
def test_rule_leads_the_message_and_ends_with_its_remedy(tmp_path, rule, index):
    """ADR-3, LESSON-572: `<rule>: … — <exact edit> naming the file (REQ-665 BR-n)`."""
    root = _ok(tmp_path)
    assert _scan(root) == []
    FIRINGS[rule][index](root)
    finding, = _scan(root)
    assert _rule(finding) == rule
    assert finding.format().startswith(f"{finding.file}:{finding.line}: manifest-parity: {rule}: ")
    cause, separator, remedy = finding.message.partition(" — ")
    assert separator, finding.message
    assert " — " not in remedy, finding.message
    assert finding.file.rstrip("/") in remedy, finding.message
    assert re.search(r"\(REQ-665 BR-\d+(?:, [A-Z]+-\d+)?\)$", remedy), finding.message


def test_requirement_669_wording_takes_no_rule_tag(tmp_path):
    # ADR-3: reserved-name, marketplace and `bin` keep their words.
    root = _ok(tmp_path)
    (root / "bin").mkdir()
    finding, = _scan(root)
    assert finding.message.startswith("a top-level bin/ exists")


def _rename_claude(name):
    def mutate(root):
        for rel in EVERY_MANIFEST:
            _edit(root, rel, {"name": name})
        market = _read(root, check.MARKETPLACE_MANIFEST)
        market["plugins"][0]["name"] = name
        _write(root, check.MARKETPLACE_MANIFEST, market)
    return mutate


def _edit_market(change):
    def mutate(root):
        market = _read(root, check.MARKETPLACE_MANIFEST)
        change(market)
        _write(root, check.MARKETPLACE_MANIFEST, market)
    return mutate


def _second_entry(market):
    market["plugins"].append({"name": "other", "source": "./"})


@pytest.mark.parametrize("mutate, needle", [
    (lambda root: _edit(root, CLAUDE, {"version": "0.0.0"}), "version-mismatch"),
    (lambda root: _drop(root, CLAUDE, "skills"), "no `skills` field"),
    (lambda root: _edit(root, CLAUDE, {"skills": ["./alpha"]}), "`beta/`"),
    (lambda root: _edit(root, CLAUDE, {"agents": ["./agents/one.md"]}), "`agents/two.md`"),
    (lambda root: (root / CLAUDE).write_text('{"name": "a", "name": "b"}\n', encoding="utf-8"),
     "repeated JSON key"),
    (lambda root: _drop(root, CLAUDE, "name"), "name-mismatch"),
    (_edit_market(_second_entry), "2 entries"),
    (_edit_market(lambda market: market.update(plugins=[])), "0 entries"),
    (_edit_market(lambda market: market.update(plugins={})), "must be an array"),
    (_edit_market(lambda market: market["plugins"][0].update(name="other")), '"other"'),
    (_edit_market(lambda market: market["plugins"][0].update(source="./x")), "`source`"),
    (lambda root: (root / "bin").mkdir(), "top-level bin/"),
    (lambda root: (root / check.MARKETPLACE_MANIFEST).unlink(), "missing"),
], ids=[
    "version", "no-skills", "skill-unreachable", "agents-partial", "repeated-key",
    "name-absent", "two-entries", "zero-entries",
    "plugins-not-array", "entry-renamed", "entry-source", "top-level-bin", "marketplace-missing",
])
def test_every_requirement_669_rule_fires_under_manifest_parity(tmp_path, mutate, needle):
    """AC-5: the absorbed rules, each still firing, each under the one check id."""
    root = _ok(tmp_path)
    mutate(root)
    finding, = _scan(root)
    assert finding.check == "manifest-parity" and needle in finding.message


@pytest.mark.parametrize("name, needle", [("claude-adlc", "reserved prefix"), ("Adlc", "kebab-case")])
def test_requirement_669_name_rules_fire_beside_the_literal(tmp_path, name, needle):
    root = _ok(tmp_path)
    _rename_claude(name)(root)
    finding, = _name_rules(root)
    assert needle in finding.message


def _check_sh(tmp_path: Path, root: Path) -> subprocess.CompletedProcess:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        ["sh", str(LINT_DIR / "check.sh"), "--root", str(root)],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "HOME": str(home), "ADLC_HOME": str(home)})


def test_check_sh_exit_contract(tmp_path):
    """AC-5: clean is 0, findings are their count, and a vacuous scan stays 255."""
    assert _check_sh(tmp_path, REPO_ROOT).returncode == 0

    empty = tmp_path / "empty"
    empty.mkdir()
    assert _check_sh(tmp_path, empty).returncode == 255

    # One complete skill, so the only finding is this check's.
    root = _ok(tmp_path)
    ethos, _ = check.load_ethos_line(check.LINT_TOOLKIT_ROOT)
    for skill in ("alpha", "beta"):
        (root / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\n---\n# {skill}\n\n{ethos}\n", encoding="utf-8")
    assert _check_sh(tmp_path, root).returncode == 0
    (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    drifted = _check_sh(tmp_path, root)
    assert drifted.returncode == 3, drifted.stdout + drifted.stderr
    assert drifted.stdout.count(": manifest-parity: version-mismatch: ") == 3


# --- RELEASING steps 2 and 3, as the e2e sandbox makes them -------------------

def test_sandbox_release_bump_moves_every_manifest(tmp_path):
    """The set is the registry: a manifest `cmd_set_version` skips fails this, as it
    would fail the e2e `test_release_update` case, without a `claude` binary."""
    script = SANDBOX_SCRIPT.read_text(encoding="utf-8")
    body = re.search(r"^def cmd_set_version\(.*?(?=^def )", script, re.M | re.S).group(0)
    namespace = {"collections": collections, "json": json, "os": os}
    exec(body, namespace)
    root = _checkout_copy(tmp_path)
    namespace["cmd_set_version"](str(root), "9.9.9-e2e")
    assert (root / "VERSION").read_text(encoding="utf-8") == "9.9.9-e2e\n"
    assert check.scan_plugin_manifest(root) == ([], 4)
    # `--ref` can name a tag from before the alternative manifests landed.
    shutil.rmtree(root / ".cursor-plugin")
    namespace["cmd_set_version"](str(root), "9.9.10-e2e")
    assert _read(root, CLAUDE)["version"] == "9.9.10-e2e"
    assert (root / "VERSION").read_text(encoding="utf-8") == "9.9.10-e2e\n"


# --- BR-6, BR-8, BR-9, BR-12, BR-14: the documents --------------------------------

# Spelled in pieces so this file is not itself a hit.
_RETIRED_CHECK = "plugin-" + "manifest"
_FIXTURE_PATH = "fixtures/" + _RETIRED_CHECK
# The whole name: REQ-665's own spec directory starts `REQ-665-plugin-manifests-…`.
_RETIRED_NAME = re.compile(re.escape(_RETIRED_CHECK) + r"(?![\w-])")
# A mention that is history: what absorbed it, or the comment that dates it.
_RETIRED_HISTORY = re.compile(r"\babsorb|^\s*#\s+REQ-669 ADR-3: ")
_DOC_TREES = ("agents", "harness", "partials", "presets", "scripts", "space", "templates",
              "tools", "workflows")
_DOC_TREES_SKIPPED = {"__pycache__", "fixtures", "node_modules", "tests"}

README_SECTION = "### Install as a plugin on other harnesses (alternative)"
# One subsection per registry entry but Claude Code; Gemini CLI is the BR-9 extra.
README_HEADINGS = {"cursor": "#### Cursor (pinned plugin)",
                   "copilot": "#### Copilot CLI (pinned plugin)"}
GEMINI_HEADING = "#### Gemini CLI"
VENDOR_DOCS = {
    "cursor": "https://cursor.com/docs/plugins",
    "copilot": "https://docs.github.com/en/copilot/reference/copilot-cli-reference/"
               "cli-plugin-reference",
}
SET_PARTS = ("**Install.**", "**What loads.**", "**What does not load.**", "**Coexistence.**",
             "**Update.**", "**Trade-off.**")
BR9_TRADE_OFF = (
    "A pinned copy is reproducible and changes only when you update it, and can therefore "
    "be behind the clone; the live clone shows every commit instantly and cannot be pinned."
)
BR6_DEPENDENCY = (
    "does not replace a Claude Code install route on a machine that runs the skills, because "
    "a skill resolves ToolkitRoot, the installed engines and the `adlc` CLI through it"
)


def _doc(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _alternative_section() -> str:
    readme = _doc("README.md")
    start = readme.index(f"{README_SECTION}\n")
    return readme[start:readme.index("\n### ", start)]


def _subsection(section: str, heading: str) -> str:
    start = section.index(f"\n{heading}\n")
    end = section.find("\n#### ", start + 1)
    return section[start:] if end == -1 else section[start:end]


def _part(body: str, label: str) -> str:
    """One `- **Label**` bullet of a subsection, up to the next bullet."""
    start = body.index(f"- {label}")
    end = body.find("\n- **", start + 1)
    return body[start:] if end == -1 else body[start:end]


def _missing_parts(body: str) -> list[str]:
    return [label for label in SET_PARTS if f"- {label}" not in body]


def _probe_result(harness: str) -> Path:
    return REPO_ROOT / ".adlc" / "research" / "harness-probes" / f"{harness}.json"


def _replacement_claims(section: str) -> list[str]:
    """Sentences that call a plugin here a replacement for a Claude Code route."""
    return [
        sentence for sentence in re.split(r"(?<=[.:;])\s+", section)
        if re.search(r"replac|substitut|supersed|instead of|in place of", sentence, re.I)
        and re.search(r"Claude Code|install route|symlink install|plugin route", sentence)
        and "does not replace" not in sentence
    ]


def _live_mentions(text: str) -> list[str]:
    """Lines that still name the retired check as live (AC-11)."""
    return [
        line.strip() for line in text.splitlines()
        if _RETIRED_NAME.search(line.replace(_FIXTURE_PATH, ""))
        and not _RETIRED_HISTORY.search(line)
    ]


def _doc_surface() -> list[Path]:
    """What a reader or the toolkit reads, outside history (CHANGELOG, specs, knowledge)
    and outside the trees that plant the name on purpose."""
    paths = [REPO_ROOT / rel for rel in ("README.md", "RELEASING.md", "AGENTS.md", "ETHOS.md")]
    paths += sorted((REPO_ROOT / ".adlc" / "context").glob("*.md"))
    paths += sorted(REPO_ROOT.glob("*/SKILL.md"))
    for top in _DOC_TREES:
        paths += [path for path in sorted((REPO_ROOT / top).rglob("*")) if path.is_file()
                  and not _DOC_TREES_SKIPPED.intersection(path.parts)]
    return paths


def test_readme_keeps_claude_first_and_no_replacement_claim():
    """BR-6, AC-10: Claude Code stays first, and no line trades its route away."""
    readme = _doc("README.md")
    order = [readme.index(mark) for mark in (
        "## Install\n",
        "claude plugin marketplace add atelier-fashion/adlc-toolkit",
        "## Contributing and live install",
        "### Other agent harnesses: `~/.agents/skills`",
        README_SECTION,
        "git clone --branch <tag>",
        "copilot plugin install ./adlc-toolkit",
        "### Harness adapters:",
    )]
    assert order == sorted(order)
    # These lines are what `space/build.mjs` reads and users type: unchanged, and first.
    assert [line for line in readme.splitlines() if line.startswith("claude plugin ")] == [
        "claude plugin marketplace add atelier-fashion/adlc-toolkit",
        "claude plugin install adlc@adlc-toolkit",
        "claude plugin marketplace update adlc-toolkit",
        "claude plugin update adlc@adlc-toolkit",
    ]
    section = _alternative_section()
    assert "This is an alternative for harnesses other than Claude Code." in section
    for heading in README_HEADINGS.values():  # once per harness, BR-6
        assert _subsection(section, heading).count(BR6_DEPENDENCY) == 1
    assert _replacement_claims(section) == []
    planted = "A plugin here replaces a Claude Code install route."
    assert _replacement_claims(f"{section}\n{planted}\n") == [planted]


def test_readme_alternative_section_parts():
    """BR-8, BR-9, AC-10: every set harness has every part, and each claim is marked."""
    assert set(README_HEADINGS) == {e.harness for e in check.MANIFEST_REGISTRY} - {"claude"}
    section = _alternative_section()
    repository = _read(REPO_ROOT, CLAUDE)["repository"]
    for harness, heading in README_HEADINGS.items():
        body = _subsection(section, heading)
        assert _missing_parts(body) == []
        for label in SET_PARTS:
            assert _missing_parts(body.replace(f"- {label}", "")) == [label]

        # BR-13: marked, with its source, and the absent probe is really absent.
        assert "**Unverified.** Source:" in body
        assert VENDOR_DOCS[harness] in body
        assert f"`{harness}.json` does not exist" in body
        assert not _probe_result(harness).exists(), (
            f"{harness}.json now exists: replace the README's unverified marking with it (BR-13)")

        assert f"git clone --branch <tag> {repository}" in _part(body, "**Install.**")
        assert "The skills" in _part(body, "**What loads.**")
        lost = _part(body, "**What does not load.**")
        for needle in ('"agents": []', '"hooks": {}', "MCP:", BR6_DEPENDENCY):
            assert needle in lost, needle
        assert "~/.agents/skills" in _part(body, "**Coexistence.**")
        assert "git -C adlc-toolkit checkout <new-tag>" in _part(body, "**Update.**")
        assert BR9_TRADE_OFF in _part(body, "**Trade-off.**")

    cursor = _subsection(section, README_HEADINGS["cursor"])
    copy = "cp -R adlc-toolkit ~/.cursor/plugins/local/adlc"
    assert copy in _part(cursor, "**Install.**") and copy in _part(cursor, "**Update.**")
    assert "do not symlink" in _part(cursor, "**Install.**")
    assert "listed twice" in _part(cursor, "**Coexistence.**")
    assert "**unverified**" in _part(cursor, "**Coexistence.**")

    copilot = _subsection(section, README_HEADINGS["copilot"])
    install = "copilot plugin install ./adlc-toolkit"
    assert install in _part(copilot, "**Install.**") and install in _part(copilot, "**Update.**")
    together = _part(copilot, "**Coexistence.**")
    for needle in ("first-found-wins", "the mount **wins**", "silently ignored",
                   "the pin has no effect while the mount exists"):
        assert needle in together, needle


def test_no_gemini_manifest_and_readme_says_why():
    """AC-7, BR-2: outside the set, and the README says so and why."""
    assert "gemini" not in {entry.harness for entry in check.MANIFEST_REGISTRY}
    assert not os.path.lexists(REPO_ROOT / "gemini-extension.json")
    assert not os.path.lexists(REPO_ROOT / "skills")
    assert not _probe_result("gemini").exists(), (
        "gemini.json now exists: replace the README's unverified marking with it (BR-13)")
    body = _subsection(_alternative_section(), GEMINI_HEADING)
    for needle in (
        "No manifest ships for Gemini CLI",
        "there is no `gemini-extension.json`",
        "Gemini CLI uses the `~/.agents/skills` mount",
        "**Unverified.** Source:",
        "https://geminicli.com/docs/extensions/reference",
        "`gemini.json` does not exist",
        "only from `<extension>/skills`",
        "double the Claude Code plugin's catalog",
        "`fs.promises.cp`",
        "no opt-out",
        "none is published",
    ):
        assert needle in body, needle
    assert _missing_parts(body) == list(SET_PARTS)  # nothing to install, so no steps


def test_docs_name_the_new_check():
    """BR-12, AC-11: the documents carry the new surfaces, and outside history the
    retired name is only the fixture directory ADR-1 kept."""
    lint = _doc("tools/lint-skills/README.md")
    start = lint.index("12. **Manifest parity (`manifest-parity`)**")
    item = lint[start:lint.index("\n13. **", start)]
    assert f"it absorbed REQ-669's `{_RETIRED_CHECK}`" in item
    for rule in BR7_RULES:
        assert f"| `{rule}` |" in item, rule
    for entry in check.MANIFEST_REGISTRY:
        assert f"| `{entry.harness}` | `{entry.path}` |" in item, entry.harness
    for row in ("`PLUGIN_RESERVED_NAME_PREFIXES`", "does not have exactly one entry",
                "a top-level `bin` exists, of any kind", "repeats a key, at any depth"):
        assert row in item, row  # REQ-669's rows stay

    releasing = _doc("RELEASING.md")
    step = releasing[releasing.index("3. **Bump the plugin manifests.**"):
                     releasing.index("4. **Write the CHANGELOG entry.**")]
    for entry in check.MANIFEST_REGISTRY:
        assert entry.path in step, entry.path
    assert "`manifest-parity` lint check" in step
    assert "the `manifest-parity` lint check fails on a top-level `bin/`" in releasing

    changelog = _doc("CHANGELOG.md")
    for needle in ("(REQ-665).**", "**No Gemini manifest ships.**",
                   "**Cursor and Copilot are unverified.**", "`manifest-parity` absorbs"):
        assert needle in changelog, needle

    architecture = _doc(".adlc/context/architecture.md")
    for needle in ("├── .cursor-plugin/", "├── .github/plugin/",
                   "*Alternative manifests (REQ-665)*", "REQ-665 landed second and reconciled",
                   "`manifest-parity` absorbed", "Gemini left the set"):
        assert needle in architecture, needle

    overview = _doc(".adlc/context/project-overview.md")
    for needle in ("`.cursor-plugin/plugin.json`", "`.github/plugin/plugin.json`",
                   "catalog mounts", "needs a Claude Code route behind it", "Gemini CLI has none"):
        assert needle in overview, needle

    hits = [f"{path.relative_to(REPO_ROOT)}: {line}" for path in _doc_surface()
            for line in _live_mentions(path.read_text(encoding="utf-8", errors="replace"))]
    assert hits == []
    # Non-vacuous: the scan reads the documents, and the filter fires on a live name.
    surface = {str(path.relative_to(REPO_ROOT)) for path in _doc_surface()}
    assert {"README.md", "RELEASING.md", "tools/lint-skills/README.md",
            "tools/lint-skills/check.py", ".adlc/context/architecture.md"} <= surface
    assert (Path(__file__).resolve().parent / _FIXTURE_PATH).is_dir()
    assert _live_mentions(f"Per root, armed like `{_RETIRED_CHECK}`.\n") != []
    assert _live_mentions(f"Fixture trees are in `tests/{_FIXTURE_PATH}/`.\n") == []
    assert _live_mentions(f"See REQ-665-{_RETIRED_CHECK}s-alternative-install.\n") == []


def test_req658_names_the_absent_manifest():
    """AC-13, BR-14: the note is REQ-658's to act on, so this pins that it is there,
    not how the spec reads once REQ-658 has decided."""
    spec = _doc(".adlc/specs/REQ-658-gemini-cli-adapter/requirement.md")
    assert "`gemini-extension.json`" in spec and "REQ-665 BR-14" in spec
