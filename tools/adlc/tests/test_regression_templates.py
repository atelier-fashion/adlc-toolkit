"""The REQ-691 template changes (TASK-240): the bug template's two optional
fields and ``## Regression Test`` section, and the config template's
``bugfix.regression_test: required`` (BR-5, BR-6, BR-7, BR-15, AC-13).

Each case copies a template into a repository it builds under ``tmp_path`` with
``git init``, and runs ``tools/adlc/regression_check.py`` there as a subprocess
with that sandbox as its ``cwd`` (LESSON-745). Nothing is written into the
toolkit tree, where a fixture bug report would become a real BUG record.
``HOME`` is sandboxed by conftest; git config is isolated here.

Each case states a property of the templates as they stand, never that a file
is unchanged against ``origin/main`` (LESSON-782). Every passing reading has a
control beside it that the same test shows can read otherwise, so a template
change that breaks the reading fails here rather than passing vacuously
(LESSON-762): the template config minus its block reads ``off``, and the filled
template bug fails while its test file is untracked.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys

import pytest

import harness_yaml
import lane_check
import lessons
import regression_check as rc

_ADLC_DIR = os.path.dirname(os.path.abspath(rc.__file__))
_SCRIPT = os.path.join(_ADLC_DIR, "regression_check.py")
_TOOLKIT = os.path.dirname(os.path.dirname(_ADLC_DIR))
_CONFIG_TEMPLATE = os.path.join(_TOOLKIT, "templates", "config-template.yml")
_BUG_TEMPLATE = os.path.join(_TOOLKIT, "templates", "bug-template.md")
_DATASET_FRONTMATTER = os.path.join(_TOOLKIT, "tools", "dataset", "frontmatter.py")

BUG_ID = "BUG-901"
TEST_REL = "tests/test_reset_token.py"
#: The spellings no template may carry: a home-directory toolkit path is one
#: the plugin user does not have (lint `no-harness-path`).
HOME_SPELLINGS = ("~/.claude", "$HOME/.claude", "${HOME}/.claude")


# --- sandbox ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    """Keep the operator's git config and any hook-exported GIT_* out of it."""
    for name in list(os.environ):
        if name in rc._GIT_ENV_SCRUB or name.startswith(rc._GIT_ENV_SCRUB_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args),
                          check=True, capture_output=True, text=True)


def _init_repo(path):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    for key, value in (("user.name", "Regression Template Test"),
                       ("user.email", "regression-template@example.invalid"),
                       ("commit.gpgsign", "false")):
        _git(path, "config", key, value)
    return path


def _engine(repo, *argv):
    """``(rc, stdout lines)`` of the engine run in ``repo``, as a project would."""
    proc = subprocess.run([sys.executable, _SCRIPT] + list(argv), cwd=str(repo),
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return proc.returncode, proc.stdout.splitlines()


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _bugfix_section(text):
    """The config template's ``bugfix`` banner through the line before the next."""
    banner = "# " + "-" * 75 + "\n"
    start = text.index(banner + "# bugfix:")
    end = text.index(banner, text.index("\nbugfix:", start))
    return text[start:end]


def _filled(text, **fields):
    """The bug template with its placeholders filled; each must be present once."""
    replacements = [("id: BUG-xxx\n", "id: %s\n" % BUG_ID),
                    ('title: "Bug Title"\n', 'title: "Reset token reused"\n'),
                    ("status: open\n", "status: resolved\n"),
                    ("severity: critical | high | medium | low\n", "severity: high\n"),
                    ("created: YYYY-MM-DD\n", "created: 2026-11-04\n"),
                    ("updated: YYYY-MM-DD\n", "updated: 2026-11-04\n")]
    for field, value in fields.items():
        # Only the value changes: the field's comment stays on its line.
        old = {"tests": "regression_tests: []", "waiver": 'regression_waiver: ""'}[field]
        new = {"tests": "regression_tests: %s", "waiver": "regression_waiver: %s"}[field]
        replacements.append((old + " ", new % value + " "))
    for old, new in replacements:
        assert text.count(old) == 1, "the bug template no longer carries %r once" % old
        text = text.replace(old, new)
    return text


def _project(tmp_path, name="project"):
    """A repository whose ``.adlc/config.yml`` is a copy of the config template."""
    repo = _init_repo(tmp_path / name)
    (repo / ".adlc" / "bugs").mkdir(parents=True)
    shutil.copyfile(_CONFIG_TEMPLATE, str(repo / ".adlc" / "config.yml"))
    return repo


def _write_bug(repo, text):
    (repo / ".adlc" / "bugs" / ("%s-reset-token.md" % BUG_ID)).write_text(
        text, encoding="utf-8")


def _load_dataset_frontmatter():
    spec = importlib.util.spec_from_file_location("_dataset_frontmatter_for_templates",
                                                  _DATASET_FRONTMATTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- BR-15: the config template --------------------------------------------------

def test_config_template_reads_required(tmp_path):
    text = _read(_CONFIG_TEMPLATE)
    raw = text.encode("utf-8")

    # The stdlib subset the engine reads it with parses it whole, and the
    # section is the one-key mapping the engine accepts.
    document = harness_yaml.loads(text, "templates/config-template.yml")
    assert document["bugfix"] == {"regression_test": "required"}
    assert len(document["bugfix"]) == 1
    assert "regression_test" not in document
    assert rc.setting_from_document(document) == (rc.MODE_REQUIRED, rc.SOURCE_SET)

    # A project whose config is a copy of the template is `required`.
    repo = _project(tmp_path)
    code, lines = _engine(repo, "mode")
    assert (code, lines) == (0, ["regression-test: required",
                                 "bugfix.regression_test is required in .adlc/config.yml"])

    # Control: the same copy minus the two uncommented lines reads `off`, as a
    # config from an older template does, so `required` came from the block.
    older = text.replace("\nbugfix:\n  regression_test: required\n", "\n")
    assert older != text
    (repo / ".adlc" / "config.yml").write_text(older, encoding="utf-8")
    code, lines = _engine(repo, "mode")
    assert (code, lines[0]) == (0, "regression-test: off")
    assert "set it to required" in lines[1]

    # The block sits after the commented `branches` example and before `sprint`,
    # and holds exactly the two uncommented lines.
    section = _bugfix_section(text)
    assert text.index("\n# branches:\n#   integration: dev\n") < text.index(section)
    assert text.index(section) < text.index("# sprint: ")
    live = [line for line in section.splitlines() if line and not line.startswith("#")]
    assert live == ["bugfix:", "  regression_test: required"]

    # It documents both values, that absent means off, when to choose off, the
    # per-bug waiver, and the command a CI job runs.
    prose = " ".join(line.lstrip("# ") for line in section.splitlines())
    prose = re.sub(r"\s+", " ", prose)
    for needle in ("#   required  ", "#   off       "):
        assert needle in section, needle
    for phrase in ("An absent key, an absent `bugfix` section or no config file at all "
                   "means `off`",
                   "upgrading the toolkit changes nothing",
                   "Choose `off` when the project has no test suite",
                   "does not want a regression test per bug",
                   "`regression_waiver` field",
                   "`adlc regression-check check`",
                   "a CI job can run the same command"):
        assert phrase in prose, phrase

    # The lane check still skips the template unparsed, and the section names no
    # home-directory path and gives no bare `/init`.
    assert not lane_check.may_carry_lanes(raw)
    assert rc.may_carry_setting(raw)
    assert not [s for s in HOME_SPELLINGS if s in section]
    assert "/init" not in section


# --- BR-5, BR-6, BR-7, AC-13: the bug template ------------------------------------

def test_bug_template_documents_fields_and_section(tmp_path):
    text = _read(_BUG_TEMPLATE)
    lines = text.splitlines()

    # The two fields follow `attribution:`, each with its comment, in the
    # frontmatter; the HTML comment calls them optional, additive and legacy
    # when empty.
    keys = [line.split(":", 1)[0] for line in lines[1:lines.index("---", 1)]
            if re.match(r"^[a-z_]+:", line)]
    assert keys[-3:] == ["attribution", "regression_tests", "regression_waiver"]
    assert any(line.startswith("regression_tests: []    # OPTIONAL.") for line in lines)
    assert any(line.startswith('regression_waiver: ""   # OPTIONAL.') for line in lines)
    for phrase in ("Flow list on this one line only", "Always double-quoted",
                   "Never set both fields", "`<repo-id>:<path>`",
                   "`bugfix.regression_test: required`",
                   "`regression_tests` and `regression_waiver` are optional and additive",
                   "absent, an empty list and an empty string all mean the same thing",
                   "legacy"):
        assert phrase in re.sub(r"\s*\n\s*#?\s*", " ", text), phrase

    # The section comes after `## Resolution`, with a slot for each BR-5 item
    # and the waiver, and says it stays empty when regression tests are off.
    headings = [line for line in lines if line.startswith("## ")]
    at = headings.index("## Regression Test")
    assert headings[at - 1:at + 2] == ["## Resolution", "## Regression Test",
                                       "## Files Changed"]
    body = text[text.index("## Regression Test"):text.index("## Files Changed")]
    for slot in ("- Test path(s):", "- Command run:",
                 "- Without the fix: fails — `<the first failing assertion line>`",
                 "- With the fix: passes", "- Waived:",
                 "stays empty\nwhen regression tests are off"):
        assert slot in body, slot

    # Every reader of bug frontmatter reads the two fields as empty, not as text
    # cut from the comments beside them.
    fields, _, _ = lessons.read_frontmatter(text)
    assert (fields["regression_tests"], fields["regression_waiver"]) == ([], "")
    dataset = _load_dataset_frontmatter()
    split, finding = dataset.split(text)
    parsed, findings = dataset.parse(split)
    assert finding is None and findings == []
    assert (parsed["regression_tests"], parsed["regression_waiver"]) == ([], "")
    assert not [s for s in HOME_SPELLINGS if s in text]
    assert "/init" not in text

    # Filled from the template and left empty: legacy, which never fails a run,
    # and which `--require-recorded` (the /bugfix gate) refuses.
    repo = _project(tmp_path)
    _write_bug(repo, _filled(text))
    code, out = _engine(repo, "check")
    assert (code, out) == (0, ["regression-check: pass",
                               "passed=0 waived=0 legacy=1 failed=0"])
    code, out = _engine(repo, "check", "--require-recorded", BUG_ID)
    assert (code, out[:2]) == (1, ["regression-check: fail",
                                   "passed=0 waived=0 legacy=0 failed=1"])

    # Naming a test that cites the id: failed while it is untracked, passed once
    # git tracks it.
    _write_bug(repo, _filled(text, tests='["%s"]' % TEST_REL))
    (repo / "tests").mkdir()
    (repo / TEST_REL).write_text(
        "def test_reset_token_is_single_use():  # %s\n    assert True\n" % BUG_ID,
        encoding="utf-8")
    code, out = _engine(repo, "check")
    assert (code, out) == (1, ["regression-check: fail",
                               "passed=0 waived=0 legacy=0 failed=1",
                               "%s: %s is not tracked by git" % (BUG_ID, TEST_REL)])
    _git(repo, "add", "--", TEST_REL)
    code, out = _engine(repo, "check")
    assert (code, out) == (0, ["regression-check: pass",
                               "passed=1 waived=0 legacy=0 failed=0"])


def test_bug_template_waiver_and_both_fields(tmp_path):
    """BR-6 and BR-7 on a report filled from the template: a quoted reason is a
    waiver, and a report carrying both fields fails."""
    text = _read(_BUG_TEMPLATE)
    repo = _project(tmp_path)
    reason = '"the defect lives in a vendor webhook no local test can reach"'

    _write_bug(repo, _filled(text, waiver=reason))
    code, out = _engine(repo, "check")
    assert (code, out) == (0, ["regression-check: pass",
                               "passed=0 waived=1 legacy=0 failed=0"])
    fields, _, _ = lessons.read_frontmatter(_filled(text, waiver=reason))
    assert fields["regression_waiver"] == reason.strip('"')

    (repo / "tests").mkdir()
    (repo / TEST_REL).write_text("# %s\n" % BUG_ID, encoding="utf-8")
    _git(repo, "add", "--", TEST_REL)
    _write_bug(repo, _filled(text, tests='["%s"]' % TEST_REL, waiver=reason))
    code, out = _engine(repo, "check")
    assert (code, out[:2]) == (1, ["regression-check: fail",
                                   "passed=0 waived=0 legacy=0 failed=1"])
    assert out[2].startswith("%s: regression_tests and regression_waiver are both set"
                             % BUG_ID)
