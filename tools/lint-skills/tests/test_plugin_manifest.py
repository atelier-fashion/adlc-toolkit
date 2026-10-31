"""Test the REQ-669 rules of `manifest-parity` (REQ-669 BR-1, BR-12, BR-20, ADR-3).

REQ-665 ADR-1: `manifest-parity` absorbed REQ-669's check, and this file keeps its
name. `tests/test_manifest_parity.py` covers REQ-665's rules across the registry.

`scan_plugin_manifest` reads `.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json` at the scan root and holds them to the repo:
`version` equals `VERSION`, every root-level `<dir>/SKILL.md` is reachable
through `skills`, an `agents` field (if any) lists every `agents/*.md`, the
marketplace lists exactly one plugin with the manifest's name, the plugin name
avoids the reserved prefixes, repeated JSON keys are rejected (LESSON-716), and
there is no top-level `bin/`.

Fixture trees live under `fixtures/plugin-manifest/<name>/`. Their skill files
are stored as `SKILL.fixture.md` and renamed to `SKILL.md` when a tree is staged
into `tmp_path`, so the real-repo lint walk (which counts every `SKILL.md`) and
the plugin loader never see fixture skills. Only `ok` holds the Cursor and Copilot
manifests: `_stage` overlays them onto every other tree, carrying that tree's
`VERSION`, so each fixture still breaks one rule. Every scan asserts that it read
at least one manifest, so a fixture path that went wrong fails instead of passing
vacuously (LESSON-019).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plugin-manifest"
SKILL_STAND_IN = "SKILL.fixture.md"
# The manifests a fixture other than `ok` takes from `ok` when `_stage` copies it.
OVERLAID_MANIFESTS = (".cursor-plugin/plugin.json", ".github/plugin/plugin.json")

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402

# fixture -> number of manifest-parity findings it must produce.
FIXTURE_EXPECTED = {
    "ok": 0,
    "version-mismatch": 1,
    "skill-missing": 1,
    "agents-field-partial": 1,
    "duplicate-key": 1,
    "top-level-bin": 1,
    "two-marketplace-entries": 1,
}


def _stage(tmp_path: Path, name: str) -> Path:
    """Copy fixture tree ``name`` into ``tmp_path`` with its skill stand-ins renamed
    and the manifests it lacks overlaid from ``ok``, at its own ``VERSION``."""
    src = FIXTURES / name
    assert src.is_dir(), f"fixture tree missing: {src}"
    dest = tmp_path / name
    shutil.copytree(src, dest)
    for stand_in in dest.rglob(SKILL_STAND_IN):
        stand_in.rename(stand_in.with_name("SKILL.md"))
    version = (dest / "VERSION").read_text(encoding="utf-8").strip()
    for rel in OVERLAID_MANIFESTS:
        if not (dest / rel).exists():
            manifest = _read(FIXTURES / "ok", rel)
            manifest["version"] = version
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            _write(dest, rel, manifest)
    return dest


def _scan(root: Path) -> list:
    """manifest-parity findings for ``root``; fails if no manifest was read."""
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned > 0, f"vacuous scan: no manifest read under {root} (LESSON-019)"
    assert all(f.check == "manifest-parity" for f in findings)
    return findings


def _read(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _write(root: Path, rel: str, obj: dict) -> None:
    (root / rel).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _name_every_manifest(root: Path, name: str) -> None:
    """Set ``name`` on every manifest and the marketplace entry, for the rules that
    read a name's shape; ``_name_rules`` sets aside the literal ``adlc`` comparison."""
    for entry in check.MANIFEST_REGISTRY:
        manifest = _read(root, entry.path)
        manifest["name"] = name
        _write(root, entry.path, manifest)
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["plugins"][0]["name"] = name
    _write(root, check.MARKETPLACE_MANIFEST, market)


def _name_rules(root: Path) -> list:
    """Findings other than the set's literal name, which any rename also breaks."""
    return [f for f in _scan(root) if not f.message.startswith("name-mismatch")
            and "the marketplace entry is named" not in f.message]


# --- every fixture ----------------------------------------------------------

def test_fixture_set_matches_the_tree_on_disk():
    on_disk = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
    assert on_disk == set(FIXTURE_EXPECTED)


@pytest.mark.parametrize("name", sorted(FIXTURE_EXPECTED))
def test_every_fixture_scans_every_manifest(tmp_path, name):
    root = _stage(tmp_path, name)
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned == 4
    assert len(findings) == FIXTURE_EXPECTED[name], [f.format() for f in findings]


# --- benign path ------------------------------------------------------------

def test_repo_root_and_ok_fixture_are_clean(tmp_path):
    repo_findings, repo_scanned = check.scan_plugin_manifest(REPO_ROOT)
    assert repo_scanned == 4
    assert repo_findings == [], [f.format() for f in repo_findings]
    ok = _stage(tmp_path, "ok")
    ok_findings, ok_scanned = check.scan_plugin_manifest(ok)
    assert ok_scanned == 4
    assert ok_findings == []
    # The ok fixture is a real plugin root: two skills, two agents, no agents field.
    assert check._plugin_root_skill_dirs(ok) == ["alpha", "beta"]
    assert "agents" not in _read(ok, check.PLUGIN_MANIFEST)


def test_check_is_wired_into_run_and_main(tmp_path):
    root = _stage(tmp_path, "version-mismatch")
    (root / "alpha").mkdir()
    # A complete skill (REQ-666: the ETHOS line), so the only finding is this check's.
    ethos, _ = check.load_ethos_line(check.LINT_TOOLKIT_ROOT)
    (root / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\n---\n# alpha\n\n" + ethos + "\n", encoding="utf-8")
    findings, scanned = check.run(root)
    assert scanned == 1
    assert [f.check for f in findings] == ["manifest-parity"]
    assert check.main(["--root", str(root)]) == 1


def test_inert_outside_a_plugin_root(tmp_path):
    # A root built for another check: a SKILL.md, no VERSION, no .claude-plugin/.
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "SKILL.md").write_text("# alpha\n", encoding="utf-8")
    assert check.scan_plugin_manifest(tmp_path) == ([], 0)
    findings, _ = check.run(tmp_path)
    assert not [f for f in findings if f.check == "manifest-parity"]


@pytest.mark.parametrize("skills", [
    ".", "./", ["./"], ["."], ["./alpha", "./beta"], ["./alpha/", "./beta"],
])
def test_skills_spellings_the_loader_accepts_are_reachable(tmp_path, skills):
    root = _stage(tmp_path, "ok")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    plugin["skills"] = skills
    _write(root, check.PLUGIN_MANIFEST, plugin)
    assert _scan(root) == []


def test_agents_field_listing_every_agent_is_clean(tmp_path):
    root = _stage(tmp_path, "agents-field-partial")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    plugin["agents"] = ["./agents/one.md", "./agents/two.md"]
    _write(root, check.PLUGIN_MANIFEST, plugin)
    assert _scan(root) == []


# --- BR-12: version and skills ----------------------------------------------

def test_version_mismatch_fails(tmp_path):
    root = _stage(tmp_path, "version-mismatch")
    findings = _scan(root)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == ".claude-plugin/plugin.json"
    assert '"1.2.4"' in f.message and '"1.2.3"' in f.message
    lines = (root / check.PLUGIN_MANIFEST).read_text(encoding="utf-8").splitlines()
    assert '"version"' in lines[f.line - 1]
    # The comparison is against the TRIMMED content: a trailing newline or space
    # in VERSION is not a mismatch.
    (root / "VERSION").write_text("1.2.3 \n\n", encoding="utf-8")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    plugin["version"] = "1.2.3"
    _write(root, check.PLUGIN_MANIFEST, plugin)
    assert _scan(root) == []


def test_version_absent_or_not_a_string_fails(tmp_path):
    root = _stage(tmp_path, "ok")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    del plugin["version"]
    _write(root, check.PLUGIN_MANIFEST, plugin)
    findings = _scan(root)
    assert len(findings) == 1 and "absent" in findings[0].message
    plugin["version"] = 1.2
    _write(root, check.PLUGIN_MANIFEST, plugin)
    assert len(_scan(root)) == 1


def test_version_file_missing_fails(tmp_path):
    root = _stage(tmp_path, "ok")
    (root / "VERSION").unlink()
    findings = _scan(root)
    assert [f.file for f in findings] == ["VERSION"]


def test_skill_missing_from_manifest_fails(tmp_path):
    root = _stage(tmp_path, "skill-missing")
    findings = _scan(root)
    assert len(findings) == 1
    assert "`beta/`" in findings[0].message
    assert "`alpha/`" not in findings[0].message


def test_skills_entry_without_dot_slash_reaches_nothing(tmp_path):
    # Claude Code 2.1.258 refuses `alpha` ("must start with ./"), so it exposes nothing.
    root = _stage(tmp_path, "ok")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    plugin["skills"] = ["alpha", "./beta"]
    _write(root, check.PLUGIN_MANIFEST, plugin)
    missing, refused = _scan(root)
    assert "`alpha/`" in missing.message and "does not start with `./`" in refused.message


def test_no_skills_field_is_one_finding(tmp_path):
    root = _stage(tmp_path, "ok")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    del plugin["skills"]
    _write(root, check.PLUGIN_MANIFEST, plugin)
    findings = _scan(root)
    assert len(findings) == 1 and "no `skills` field" in findings[0].message


def test_nested_and_hidden_skill_dirs_are_not_skills(tmp_path):
    # The loader reads one level and skips hidden dirs; so does the check.
    root = _stage(tmp_path, "skill-missing")
    plugin = _read(root, check.PLUGIN_MANIFEST)
    plugin["skills"] = ["./alpha", "./beta"]
    _write(root, check.PLUGIN_MANIFEST, plugin)
    for rel in (".adlc/hidden/SKILL.md", "tools/nested/SKILL.md"):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text("# not a plugin skill\n", encoding="utf-8")
    assert _scan(root) == []


def test_agents_field_partial_fails(tmp_path):
    root = _stage(tmp_path, "agents-field-partial")
    findings = _scan(root)
    assert len(findings) == 1
    assert "`agents/two.md`" in findings[0].message


# --- LESSON-716: strict parsing -----------------------------------------------

def test_duplicate_key_rejected(tmp_path):
    root = _stage(tmp_path, "duplicate-key")
    text = (root / check.PLUGIN_MANIFEST).read_text(encoding="utf-8")
    # The trap: plain json.loads keeps the last value, which matches VERSION.
    assert json.loads(text)["version"] == "1.2.3"
    findings = _scan(root)
    assert len(findings) == 1
    f = findings[0]
    assert "repeated JSON key" in f.message and '"version"' in f.message
    assert text.splitlines()[f.line - 1].strip() == '"version": "1.2.3",'


def test_nested_duplicate_key_rejected(tmp_path):
    root = _stage(tmp_path, "ok")
    (root / check.MARKETPLACE_MANIFEST).write_text(
        '{"name": "adlc-toolkit", "owner": {"name": "A"}, "description": "d",\n'
        ' "plugins": [{"name": "adlc", "source": "./", "source": "./elsewhere"}]}\n',
        encoding="utf-8",
    )
    findings = _scan(root)
    assert len(findings) == 1 and '"source"' in findings[0].message


@pytest.mark.parametrize("bad_text, needle", [
    ('{"name": "adlc", "version": "1.2.3", "skills": "./",}\n', "not valid JSON"),
    ('{"name": "adlc", "version": "1.2.3", "skills": "./", "x": NaN}\n', "NaN"),
    ('["adlc"]\n', "JSON object"),
])
def test_unparseable_manifest_is_one_finding(tmp_path, bad_text, needle):
    root = _stage(tmp_path, "ok")
    (root / check.PLUGIN_MANIFEST).write_text(bad_text, encoding="utf-8")
    findings = _scan(root)
    assert len(findings) == 1 and needle in findings[0].message


def test_missing_manifests_are_findings_once_armed(tmp_path):
    # VERSION plus a root-level skill arms the check, so deleting the manifest
    # directory is two findings, not a silent skip (LESSON-019). The Cursor and
    # Copilot manifests are still read.
    root = _stage(tmp_path, "ok")
    shutil.rmtree(root / ".claude-plugin")
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned == 2
    assert sorted(f.file for f in findings) == [check.MARKETPLACE_MANIFEST, check.PLUGIN_MANIFEST]
    assert all("missing" in f.message for f in findings)


def test_one_missing_manifest_is_one_finding(tmp_path):
    root = _stage(tmp_path, "ok")
    (root / check.MARKETPLACE_MANIFEST).unlink()
    findings, scanned = check.scan_plugin_manifest(root)
    assert scanned == 3
    assert [f.file for f in findings] == [check.MARKETPLACE_MANIFEST]


# --- BR-20: no top-level bin/ -------------------------------------------------

def test_top_level_bin_rejected(tmp_path):
    root = _stage(tmp_path, "top-level-bin")
    findings = _scan(root)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == "bin/"
    assert "claude.ai sync" in f.message and "scripts/" in f.message
    # Benign: executables under scripts/ (present in this fixture and in ok) and a
    # bin/ nested below the root are not the rejected shape.
    shutil.rmtree(root / "bin")
    (root / "tools" / "x" / "bin").mkdir(parents=True)
    (root / "tools" / "x" / "bin" / "tool").write_text("#!/bin/sh\n", encoding="utf-8")
    assert (root / "scripts" / "adlc").is_file()
    assert _scan(root) == []


# --- BUG-258: no root CLAUDE.md ------------------------------------------------

@pytest.mark.parametrize("kind", ["file", "dangling-symlink"])
def test_root_claude_md_rejected(tmp_path, kind):
    """The file `adlc harness render` writes and `--strict` validate fails on; a
    copy under `.claude/` is the toolkit's own and draws nothing."""
    root = _stage(tmp_path, "ok")
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "CLAUDE.md").write_text("@../AGENTS.md\n", encoding="utf-8")
    assert _scan(root) == []
    if kind == "file":
        (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    else:
        (root / "CLAUDE.md").symlink_to(root / "no-such-file")
    findings = _scan(root)
    assert [f.file for f in findings] == ["CLAUDE.md"], findings
    assert ".claude/CLAUDE.md" in findings[0].message


@pytest.mark.parametrize("kind", ["file", "symlink-to-dir", "dangling-symlink"])
def test_top_level_bin_of_any_kind_rejected(tmp_path, kind):
    """BR-20: the sync path sees a top-level `bin` entry whatever it is, so a
    file or a symlink named `bin` is rejected like a directory."""
    root = _stage(tmp_path, "ok")
    assert _scan(root) == []
    if kind == "file":
        (root / "bin").write_text("#!/bin/sh\n", encoding="utf-8")
    elif kind == "symlink-to-dir":
        (root / "bin").symlink_to(root / "scripts")
    else:
        (root / "bin").symlink_to(root / "no-such-dir")
    findings = _scan(root)
    assert [f.file for f in findings] == ["bin/"], findings
    assert "file or symlink" in findings[0].message


# --- BR-1: one marketplace entry, named like the plugin -----------------------

def test_single_marketplace_entry_named_adlc(tmp_path):
    # The real repo is both the marketplace and the plugin: one entry, `adlc`, at `./`.
    plugin = _read(REPO_ROOT, check.PLUGIN_MANIFEST)
    market = _read(REPO_ROOT, check.MARKETPLACE_MANIFEST)
    assert plugin["name"] == "adlc"
    assert market["name"] == "adlc-toolkit"
    assert market["plugins"] == [{"name": "adlc", "source": "./"}]
    assert plugin["version"] == (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert "agents" not in plugin and plugin["skills"] == "./"

    # A renamed entry is one finding.
    root = _stage(tmp_path, "ok")
    staged = _read(root, check.MARKETPLACE_MANIFEST)
    staged["plugins"][0]["name"] = "adlc-renamed"
    _write(root, check.MARKETPLACE_MANIFEST, staged)
    findings = _scan(root)
    assert len(findings) == 1 and '"adlc-renamed"' in findings[0].message


def test_two_marketplace_entries_fails(tmp_path):
    root = _stage(tmp_path, "two-marketplace-entries")
    findings = _scan(root)
    assert len(findings) == 1 and "2 entries" in findings[0].message


def test_zero_marketplace_entries_fails(tmp_path):
    root = _stage(tmp_path, "ok")
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["plugins"] = []
    _write(root, check.MARKETPLACE_MANIFEST, market)
    findings = _scan(root)
    assert len(findings) == 1 and "0 entries" in findings[0].message


@pytest.mark.parametrize("source", ["./elsewhere", {"source": "github", "repo": "a/b"}])
def test_marketplace_entry_source_must_be_this_repo(tmp_path, source):
    root = _stage(tmp_path, "ok")
    market = _read(root, check.MARKETPLACE_MANIFEST)
    market["plugins"][0]["source"] = source
    _write(root, check.MARKETPLACE_MANIFEST, market)
    findings = _scan(root)
    assert len(findings) == 1 and "`source`" in findings[0].message


# --- plugin name rules --------------------------------------------------------

@pytest.mark.parametrize("name", ["claude-adlc", "anthropic-tools", "claudeadlc", "cc-plugin-adlc"])
def test_reserved_prefix_plugin_name_fails(tmp_path, name):
    root = _stage(tmp_path, "ok")
    _name_every_manifest(root, name)
    finding, = _name_rules(root)
    assert "reserved prefix" in finding.message


def test_reserved_prefixes_match_the_requirement():
    # requirement.md, Entities: must not start with `claude-`, `anthropic-`,
    # `anthropics-` or `cc-plugin-`. The first two are kept bare (`claude`,
    # `anthropic`), which also covers `anthropics-` and the no-hyphen forms.
    assert check.PLUGIN_RESERVED_NAME_PREFIXES == ("claude", "anthropic", "cc-plugin-")


@pytest.mark.parametrize("name", ["cc-tools", "ccplugin-adlc", "adlc-cc-plugin-x", "cc-plugins"])
def test_near_reserved_plugin_name_is_clean(tmp_path, name):
    root = _stage(tmp_path, "ok")
    _name_every_manifest(root, name)
    assert _name_rules(root) == []


@pytest.mark.parametrize("name", ["Adlc", "adlc_toolkit", "adlc:x", "adlc--x"])
def test_non_kebab_plugin_name_fails(tmp_path, name):
    root = _stage(tmp_path, "ok")
    _name_every_manifest(root, name)
    finding, = _name_rules(root)
    assert "kebab-case" in finding.message


# --- BR-1: the README's install commands name the manifests -------------------

README_INSTALL_COMMANDS = (
    "claude plugin marketplace add atelier-fashion/adlc-toolkit",
    "claude plugin install adlc@adlc-toolkit",
)
_MARKETPLACE_ADD_RE = r"^claude plugin marketplace add ([A-Za-z0-9-]+/[A-Za-z0-9_.-]+)$"
_INSTALL_RE = r"^claude plugin install ([a-z0-9-]+)@([a-z0-9-]+)$"


def _readme_install_problems(readme: str, plugin: dict, market: dict) -> list[str]:
    """What is wrong with README.md's install commands against the manifests."""
    problems = []
    lines = {line.strip() for line in readme.splitlines()}
    for command in README_INSTALL_COMMANDS:
        if command not in lines:
            problems.append(f"README.md has no line `{command}`")
    installs = [m.groups() for m in (re.match(_INSTALL_RE, ln) for ln in lines) if m]
    for plugin_name, market_name in installs:
        if plugin_name != plugin.get("name"):
            problems.append(f"installs plugin {plugin_name!r}, plugin.json names {plugin.get('name')!r}")
        if plugin_name != market.get("plugins", [{}])[0].get("name"):
            problems.append(f"installs plugin {plugin_name!r}, marketplace.json lists another")
        if market_name != market.get("name"):
            problems.append(f"installs from {market_name!r}, marketplace.json names {market.get('name')!r}")
    repository = plugin.get("repository", "")
    repository = repository.get("url", "") if isinstance(repository, dict) else repository
    for added in (m.group(1) for m in (re.match(_MARKETPLACE_ADD_RE, ln) for ln in lines) if m):
        if not repository.rstrip("/").endswith("github.com/" + added):
            problems.append(f"adds marketplace repo {added!r}, plugin.json repository is {repository!r}")
    return problems


def _manifests() -> tuple[dict, dict]:
    plugin = json.loads((REPO_ROOT / check.PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    market = json.loads((REPO_ROOT / check.MARKETPLACE_MANIFEST).read_text(encoding="utf-8"))
    return plugin, market


def test_readme_install_commands_match_the_manifests():
    """BR-1 machine check: README.md carries both install commands verbatim, each
    on a line of its own; every `claude plugin install <plugin>@<marketplace>`
    line types the `name`s plugin.json and marketplace.json carry; and the repo
    `marketplace add` names is plugin.json's `repository`."""
    plugin, market = _manifests()
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert _readme_install_problems(readme, plugin, market) == []
    # The commands themselves spell the manifests' names.
    assert README_INSTALL_COMMANDS[1] == f"claude plugin install {plugin['name']}@{market['name']}"


@pytest.mark.parametrize("old, new, edits", [
    # A command edited in the README.
    ("claude plugin install adlc@adlc-toolkit", "claude plugin install adlc@adlc-tools", None),
    ("claude plugin marketplace add atelier-fashion/adlc-toolkit",
     "claude plugin marketplace add atelier-fashion/adlc", None),
    # A manifest renamed under an unchanged README.
    (None, None, ("plugin", "name", "adlc-kit")),
    (None, None, ("market", "name", "adlc-market")),
    (None, None, ("plugin", "repository", "https://github.com/someone/else")),
])
def test_readme_install_check_fires_on_drift(old, new, edits):
    plugin, market = _manifests()
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    if old is not None:
        assert old in readme
        readme = readme.replace(old, new)
    if edits is not None:
        which, key, value = edits
        (plugin if which == "plugin" else market)[key] = value
    assert _readme_install_problems(readme, plugin, market), (old, edits)
