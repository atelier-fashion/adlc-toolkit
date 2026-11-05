"""Tests for tools/adlc/regression_check.py (REQ-691 TASK-238).

Every case builds its repository, ``.adlc/bugs/`` and ``.adlc/config.yml``
under ``tmp_path`` with ``git init``. None is ever written into the toolkit
tree, where a fixture bug report would become a real BUG record. The one case
that reads this repo's own bug reports copies them into a sandbox first.

Most cases call :func:`regression_check.main` in-process with an explicit
``--root``; the subprocess cases pass an explicit sandbox ``cwd`` (LESSON-745).
The branch case builds its own bare ``origin`` and never compares against this
repo's ``origin/main`` (LESSON-782).
"""

import ast
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import sysconfig

import pytest

import adlc
import lane_check
import regression_check as rc

_ADLC_DIR = os.path.dirname(os.path.abspath(rc.__file__))
_SCRIPT = os.path.join(_ADLC_DIR, "regression_check.py")
_ADLC = os.path.join(_ADLC_DIR, "adlc.py")
_TOOLKIT = os.path.dirname(os.path.dirname(_ADLC_DIR))

REQUIRED = "bugfix:\n  regression_test: required\n"
OFF = "bugfix:\n  regression_test: off\n"

#: A report in the shape templates/bug-template.md ships, with the two
#: REQ-691 fields left empty as TASK-240 adds them.
TEMPLATE_SHAPED = """---
id: {id}
title: "Bug Title"
status: resolved
severity: low
created: 2026-11-04
updated: 2026-11-04
component: ""       # narrow area, e.g., "API/auth"
domain: ""          # broad area
stack: []           # tech layers touched
concerns: []        # cross-cutting dimensions
tags: []            # free-form keywords
introduced_by: []   # OPTIONAL. REQ id(s) whose merge introduced the defect,
                    # e.g. ["REQ-483"]. An empty array is a meaningful
                    # "no attribution", not a missing value.
attribution: none   # OPTIONAL. derived | manual | none
regression_tests: []    # OPTIONAL. Flow list of repo-relative test paths.
regression_waiver: ""   # OPTIONAL. Double-quoted one-line reason; never both.
---

<!--
Both fields above are optional and additive.
-->

## Description
"""


# --- sandbox ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch, tmp_path):
    """Keep the operator's git config and any hook-exported GIT_* out of it."""
    for name in list(os.environ):
        if name in rc._GIT_ENV_SCRUB or name.startswith(rc._GIT_ENV_SCRUB_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args),
                          check=True, capture_output=True, text=True)


def _init_repo(path, branch="main"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", branch)
    for key, value in (("user.name", "Regression Check Test"),
                       ("user.email", "regression-check@example.invalid"),
                       ("commit.gpgsign", "false"),
                       ("tag.gpgsign", "false")):
        _git(path, "config", key, value)


def bug_text(bug_id, status="resolved", tests=None, waiver=None, extra=()):
    """A bug report; ``tests`` and ``waiver`` are the raw text after the colon."""
    lines = ["---", "id: %s" % bug_id, 'title: "A fixture bug"', "status: %s" % status,
             "severity: low", "created: 2026-11-04", "updated: 2026-11-04",
             'component: "fixture"', "tags: []"]
    if tests is not None:
        lines.append(("regression_tests: %s" % tests).rstrip(" "))
    if waiver is not None:
        lines.append("regression_waiver: %s" % waiver)
    lines.extend(extra)
    lines += ["---", "", "## Description", "", "Fixture body.", ""]
    return "\n".join(lines)


def run_engine(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = rc.main(list(argv))
    return code, out.getvalue().splitlines()


class Project(object):
    def __init__(self, root):
        self.root = root

    @property
    def path(self):
        return str(self.root)

    def git(self, *args):
        return _git(self.root, *args)

    def write(self, rel, text):
        target = self.root.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            target.write_bytes(text)
        else:
            target.write_text(text, encoding="utf-8")
        return target

    def config(self, text):
        return self.write(".adlc/config.yml", text)

    def bug(self, bug_id, slug="fixture", text=None, **fields):
        return self.write(".adlc/bugs/%s-%s.md" % (bug_id, slug),
                          text if text is not None else bug_text(bug_id, **fields))

    def test_file(self, rel, text, track=True):
        self.write(rel, text)
        if track:
            self.git("add", "--", rel)

    def commit(self, msg="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", msg)

    def run(self, verb, *rest):
        return run_engine([verb, "--root", self.path] + list(rest))


@pytest.fixture
def make_project(tmp_path):
    made = []

    def make(config=None, name=None):
        root = tmp_path / (name or "project%d" % len(made))
        _init_repo(root)
        project = Project(root)
        if config is not None:
            project.config(config)
        made.append(project)
        return project

    return make


def counts(lines):
    """The counts line as a dict, after checking its exact shape."""
    words = lines[1].split(" ")
    assert [w.split("=")[0] for w in words] == list(rc.CLASSES), lines
    return dict((w.split("=")[0], int(w.split("=")[1])) for w in words)


def result_of(project, bug_id, *flags):
    """``(class, failure lines, rc)`` of a named run over one id."""
    code, lines = project.run("check", *flags, bug_id)
    tally = counts(lines)
    assert sum(tally.values()) == 1, lines
    cls = [name for name, n in tally.items() if n == 1][0]
    return cls, lines[2:], code


# --- BR-1: the setting, and absent means off ----------------------------------

def test_mode_values_and_absent_means_off(make_project, monkeypatch):
    parsed = []
    real_loads = rc.harness_yaml.loads

    def spy(text, source="<string>"):
        parsed.append(source)
        return real_loads(text, source)

    monkeypatch.setattr(rc.harness_yaml, "loads", spy)

    # No config file at all: off, and the line names the key that turns it on.
    p = make_project()
    assert p.run("mode") == (0, [
        "regression-test: off",
        ".adlc/config.yml does not exist, which means off; set bugfix.regression_test: "
        "required in it to turn regression tests on"])
    assert p.run("check") == (0, [
        "regression-check: off",
        "regression tests are off for this project: .adlc/config.yml does not exist, which "
        "means off; set bugfix.regression_test: required in it to turn regression tests on"])

    # A config without the key is never parsed: the tab below would be a
    # YamlError, so an rc 0 proves the prefilter cleared it.
    absent = [
        "project:\n\tname: x\n",
        "# bugfix:\n#   regression_test: required\nproject:\n  name: x\n"
        "    # regression_test: required\n\t\n",
    ]
    for text in absent:
        p = make_project(text)
        code, lines = p.run("mode")
        assert (code, lines[0]) == (0, "regression-test: off"), text
        assert "is not set in .adlc/config.yml, which means off" in lines[1]
    assert parsed == []

    # Set values, in the shapes a config may carry them.
    cases = [
        (REQUIRED, "required"),
        (OFF, "off"),
        ("bugfix: {regression_test: required}\n", "required"),
        ("project:\n  name: \"x\"  # c\nrepos:\n  web:\n    primary: true\n"
         "# a comment between sections\nbugfix:\n  regression_test: required  # on\n",
         "required"),
        ("﻿bugfix:\r\n  regression_test: off\r\n", "off"),
    ]
    for text, mode in cases:
        p = make_project(text)
        assert p.run("mode") == (0, [
            "regression-test: " + mode,
            "bugfix.regression_test is %s in .adlc/config.yml" % mode]), text
    assert len(parsed) == len(cases)

    # The key mentioned in a value forces a parse, and the setting is still absent.
    p = make_project("tags: [regression_test]\n")
    code, lines = p.run("mode")
    assert (code, lines[0]) == (0, "regression-test: off")
    assert "is not set" in lines[1]

    # The prefilter on raw bytes.
    assert not rc.may_carry_setting(b"")
    assert not rc.may_carry_setting(b"project:\n  name: x\n")
    assert not rc.may_carry_setting(b"# regression_test: required\n")
    assert not rc.may_carry_setting(b"\xef\xbb\xbf  # regression_test: on\r\nx: y\r\n")
    assert not rc.may_carry_setting(b"# a \\ in a comment\n")
    assert rc.may_carry_setting(b"bugfix:\n  regression_test: off\n")
    assert rc.may_carry_setting(b'name: "a\\\\b"\n')
    assert rc.may_carry_setting(REQUIRED.encode("utf-16"))
    assert rc.may_carry_setting(b"x: \xff regression_test\n")


# --- BR-17 / AC-16: an unreadable setting is an error, never off ---------------

def test_unreadable_config_is_an_error_not_off(make_project, tmp_path):
    texts = [
        ("tab", "bugfix:\n\tregression_test: required\n", None),
        ("unclosed quote", 'bugfix:\n  regression_test: "required\n', None),
        ("anchor", "bugfix: &b\n  regression_test: required\n", None),
        ("bad value", "bugfix:\n  regression_test: sometimes\n", "'sometimes'"),
        ("case", "bugfix:\n  regression_test: Required\n", "'Required'"),
        ("list value", "bugfix:\n  regression_test: [required]\n", "is a list"),
        ("non-mapping bugfix", "bugfix: regression_test\n", "bugfix in .adlc/config.yml is a string"),
        ("unknown key", "bugfix:\n  regression_test: required\n  strict: yes\n", "'strict'"),
        ("top level", "regression_test: required\n", "top-level key"),
        ("list document", "- regression_test\n", "not a mapping"),
        ("not utf-8", b"bugfix:\n  regression_test: \xff\n", "not UTF-8"),
        ("utf-16", REQUIRED.encode("utf-16"), "not UTF-8"),
    ]
    for label, text, fragment in texts:
        p = make_project(text)
        code, lines = p.run("mode")
        assert code == 2, label
        assert lines[0] == "regression-test: error", label
        assert len(lines) == 2, label
        for word in ("bugfix.regression_test", "'required'", "'off'"):
            assert word in lines[1], (label, lines)
        if fragment:
            assert fragment in lines[1], (label, lines)
        code, lines = p.run("check")
        assert (code, lines[0], len(lines)) == (2, "regression-check: error", 2), label
        assert not any(line.startswith("passed=") for line in lines)

    # A config that is not a regular file, or a link that leads nowhere.
    p = make_project()
    (p.root / ".adlc" / "config.yml").mkdir(parents=True)
    code, lines = p.run("mode")
    assert (code, lines[0]) == (2, "regression-test: error")
    assert "not a regular file" in lines[1]
    p = make_project()
    (p.root / ".adlc").mkdir()
    os.symlink(str(tmp_path / "nowhere.yml"), str(p.root / ".adlc" / "config.yml"))
    code, lines = p.run("check")
    assert (code, lines[0]) == (2, "regression-check: error")
    assert "does not resolve" in lines[1]
    assert str(tmp_path) not in "\n".join(lines)

    # Benign path: no config file at all is off, not an error.
    p = make_project()
    assert p.run("mode")[0] == 0
    assert p.run("check")[:1] == (0,)


# --- BR-6, BR-7 ------------------------------------------------------------------

def test_waiver_needs_a_reason(make_project):
    p = make_project(REQUIRED)
    p.bug("BUG-101", waiver='"   "')
    p.bug("BUG-102", waiver='"\t "')
    p.bug("BUG-103", waiver='""')
    p.bug("BUG-104", waiver="''")
    p.bug("BUG-105", waiver="")
    p.bug("BUG-106", waiver='"no test can reach the vendor\'s live webhook"')
    p.bug("BUG-107", tests="[]", waiver='"only reachable against the live identity provider"')
    p.bug("BUG-108", waiver="a plain reason  # and a comment")

    for bug_id in ("BUG-101", "BUG-102"):
        cls, failures, code = result_of(p, bug_id)
        assert (cls, code) == (rc.FAILED, 1)
        assert failures == ["%s: regression_waiver is blank and regression_tests is empty; "
                            "a waiver needs a one-line reason (BR-6)" % bug_id]
    for bug_id in ("BUG-103", "BUG-104", "BUG-105"):
        assert result_of(p, bug_id) == (rc.LEGACY, [], 0), bug_id
    for bug_id in ("BUG-106", "BUG-107"):
        assert result_of(p, bug_id) == (rc.WAIVED, [], 0), bug_id
    # An unquoted reason is the wrong type, not a waiver (LESSON-716).
    assert result_of(p, "BUG-108") == (rc.FAILED, [
        "BUG-108: regression_waiver: must be a quoted string, not an unquoted value"], 1)
    code, lines = p.run("check")
    assert counts(lines) == {"passed": 0, "waived": 2, "legacy": 3, "failed": 3}


def test_both_fields_set_fails(make_project):
    p = make_project(REQUIRED)
    p.test_file("tests/test_both.py", "# BUG-201 BUG-202 BUG-204\n")
    p.bug("BUG-201", tests='["tests/test_both.py"]', waiver='"and a waiver"')
    # Benign: one field set and the other empty or blank is not "both" (BR-6).
    p.bug("BUG-202", tests='["tests/test_both.py"]', waiver='""')
    p.bug("BUG-203", tests="[]", waiver='"no test can reach it"')
    p.bug("BUG-204", tests='["tests/test_both.py"]', waiver='"   "')

    cls, failures, code = result_of(p, "BUG-201")
    assert (cls, code) == (rc.FAILED, 1)
    assert failures == ["BUG-201: regression_tests and regression_waiver are both set; "
                        "record one or the other (BR-7)"]
    assert result_of(p, "BUG-202") == (rc.PASSED, [], 0)
    assert result_of(p, "BUG-203") == (rc.WAIVED, [], 0)
    assert result_of(p, "BUG-204") == (rc.PASSED, [], 0)
    code, lines = p.run("check")
    assert code == 1
    assert counts(lines) == {"passed": 2, "waived": 1, "legacy": 0, "failed": 1}
    assert [line.split(":")[0] for line in lines[2:]] == ["BUG-201"]


# --- BR-9 / AC-5: the classification table ---------------------------------------

def test_classification_table(make_project):
    p = make_project(REQUIRED)
    p.test_file("tests/test_cites.py", "# BUG-301 BUG-307 BUG-312 BUG-321\n")
    p.test_file("tests/test_other.py", "def test_nothing():\n    pass\n")
    p.test_file("tests/test_untracked.py", "# BUG-305\n", track=False)
    table = [
        ("BUG-301", dict(tests='["tests/test_cites.py"]'), rc.PASSED, None),
        ("BUG-302", dict(waiver='"no test can reach the vendor webhook"'), rc.WAIVED, None),
        ("BUG-303", dict(), rc.LEGACY, None),
        ("BUG-304", dict(tests='["tests/missing.py"]'), rc.FAILED,
         "tests/missing.py does not exist"),
        ("BUG-305", dict(tests='["tests/test_untracked.py"]'), rc.FAILED,
         "tests/test_untracked.py is not tracked by git"),
        ("BUG-306", dict(tests='["tests/test_other.py"]'), rc.FAILED,
         "tests/test_other.py does not cite BUG-306"),
        ("BUG-307", dict(tests='["tests/test_cites.py"]', waiver='"and a waiver"'), rc.FAILED,
         "are both set"),
        ("BUG-308", dict(tests='"tests/test_cites.py"'), rc.FAILED,
         "regression_tests: must be a flow list of paths"),
        ("BUG-309", dict(tests="tests/test_cites.py"), rc.FAILED,
         "regression_tests: must be a flow list of paths"),
        ("BUG-310", dict(waiver='["a reason"]'), rc.FAILED,
         "regression_waiver: must be a quoted string, not a list"),
        ("BUG-311", dict(tests="{path: tests/test_cites.py}"), rc.FAILED,
         "regression_tests: must be a flow list of paths ([\"tests/...\"]), not a mapping"),
        ("BUG-312", dict(tests='["tests/test_cites.py"]',
                         extra=['regression_tests: ["tests/test_cites.py"]']), rc.FAILED,
         "regression_tests: appears 2 times"),
        ("BUG-313", dict(extra=["tags: [again]"]), rc.FAILED, "tags: appears 2 times"),
        ("BUG-314", dict(tests="", extra=["  - tests/test_cites.py"]), rc.FAILED,
         "regression_tests: the value continues onto the next line"),
        ("BUG-315", dict(waiver='"no test can reach'), rc.FAILED,
         "regression_waiver: the opening double quote is never closed"),
        ("BUG-316", dict(tests='["tests/test_cites.py"'), rc.FAILED,
         "regression_tests: the flow list is not closed"),
        ("BUG-317", dict(extra=['regression_tests:["tests/test_cites.py"]']), rc.FAILED,
         "regression_tests: written in a spelling not every reader agrees on"),
        ("BUG-318", dict(waiver='"  "'), rc.FAILED, "a waiver needs a one-line reason"),
        ("BUG-319", dict(tests='["tests/test_cites.py", ""]'), rc.FAILED,
         "regression_tests: the list holds an empty entry"),
        ("BUG-320", dict(tests='[["tests/test_cites.py"]]'), rc.FAILED,
         "an entry is a nested collection"),
        ("BUG-321", dict(extra=['"regression_waiver": "quoted key"']), rc.FAILED,
         "regression_waiver: written in a spelling"),
        ("BUG-322", dict(waiver="|", extra=["  a block scalar"]), rc.FAILED,
         "regression_waiver: the value continues onto the next line"),
    ]
    for bug_id, fields, _, _ in table:
        p.bug(bug_id, **fields)
    p.bug("BUG-323", text="# A report with no frontmatter\n")
    p.bug("BUG-324", text=bug_text("BUG-999"))
    p.bug("BUG-325", status="open", tests='["unclosed')  # out of scope unnamed
    extra = [("BUG-323", rc.FAILED, "no frontmatter block"),
             ("BUG-324", rc.FAILED, "id: the frontmatter says BUG-999 but the file name says "
                                    "BUG-324")]

    code, lines = p.run("check")
    assert (code, lines[0]) == (1, "regression-check: fail")
    assert counts(lines) == {"passed": 1, "waived": 1, "legacy": 1, "failed": 21}
    expected = [(b, f) for b, _, c, f in table if c == rc.FAILED] + [(b, f) for b, _, f in extra]
    assert [line.split(":")[0] for line in lines[2:]] == [b for b, _ in expected]
    for line, (bug_id, fragment) in zip(lines[2:], expected):
        assert line.startswith(bug_id + ": ") and fragment in line, (bug_id, line)
    assert "BUG-325" not in "\n".join(lines)

    # Each bug on its own lands in its row's class; a named run checks the open one.
    for bug_id, _, cls, _ in table:
        assert result_of(p, bug_id)[0] == cls, bug_id
    cls, failures, _ = result_of(p, "BUG-325")
    assert cls == rc.FAILED
    assert failures == ["BUG-325: regression_tests: the opening double quote is never "
                        "closed on the key's line"]

    # A report whose file name carries no id: skipped while open like any open
    # bug, failed once resolved.
    q = make_project(REQUIRED)
    q.write(".adlc/bugs/BUG-notes.md", bug_text("BUG-326", status="open"))
    assert q.run("check") == (0, ["regression-check: pass",
                                  "passed=0 waived=0 legacy=0 failed=0"])
    q.write(".adlc/bugs/BUG-notes.md", bug_text("BUG-326"))
    assert q.run("check") == (1, ["regression-check: fail",
                                  "passed=0 waived=0 legacy=0 failed=1",
                                  "BUG-notes.md: the file name does not start with BUG-<digits>"])


# --- BR-10: exit codes and counts ------------------------------------------------

def test_exit_codes_and_counts(make_project, tmp_path):
    p = make_project(REQUIRED)
    p.test_file("tests/test_401.py", "# BUG-401\n# BUG-402\n")
    p.bug("BUG-401", tests='["tests/test_401.py"]')
    p.bug("BUG-402", status="closed", tests='["tests/test_401.py"]')
    p.bug("BUG-403", status="open")  # not counted by an unnamed run
    assert p.run("check") == (0, ["regression-check: pass",
                                  "passed=2 waived=0 legacy=0 failed=0"])

    # One failed bug is one line, every reason on it.
    p.bug("BUG-404", tests='["tests/missing.py", "tests/test_401.py"]')
    code, lines = p.run("check")
    assert code == 1
    assert lines == ["regression-check: fail", "passed=2 waived=0 legacy=0 failed=1",
                     "BUG-404: tests/missing.py does not exist; tests/test_401.py does not "
                     "cite BUG-404"]

    # The exit status a shell sees is the same, run by path from the project.
    proc = subprocess.run([sys.executable, "-E", _SCRIPT, "check"], cwd=p.path,
                          capture_output=True, text=True)
    assert (proc.returncode, proc.stdout.splitlines()) == (1, lines)

    # Zero resolved bugs is a legitimate empty state: rc 0 and all counts 0.
    q = make_project(REQUIRED)
    q.bug("BUG-405", status="open", tests='["unclosed')
    assert q.run("check") == (0, ["regression-check: pass",
                                  "passed=0 waived=0 legacy=0 failed=0"])

    # An unreadable setting is rc 2 and an off project rc 0.
    q.config("bugfix:\n  regression_test: sometimes\n")
    assert q.run("check")[0] == 2
    q.config(OFF)
    assert q.run("check")[0] == 0


# --- BR-11 / AC-8: off reads no bug report ---------------------------------------

def test_off_reads_no_bug_report(make_project, monkeypatch):
    touched = []
    real_read, real_list = rc.read_report, rc.list_reports
    monkeypatch.setattr(rc, "read_report",
                        lambda path, name: touched.append(name) or real_read(path, name))
    monkeypatch.setattr(rc, "list_reports",
                        lambda path: touched.append("<listed>") or real_list(path))
    broken = bug_text("BUG-501", tests='["unclosed')

    for config in (None, OFF, "project:\n  name: x\n"):
        p = make_project(config)
        p.bug("BUG-501", text=broken)
        for args in ((), ("BUG-501",), ("--require-recorded",)):
            code, lines = p.run("check", *args)
            assert code == 0, (config, args)
            assert lines[0] == "regression-check: off"
            assert lines[1].startswith("regression tests are off for this project: ")
            assert len(lines) == 2
        assert touched == [], config

    # Positive control (LESSON-762): the same tree in required mode opens the
    # report and fails it, so the probe above could have seen a read.
    p = make_project(REQUIRED)
    p.bug("BUG-501", text=broken)
    code, lines = p.run("check")
    assert touched == ["<listed>", "BUG-501-fixture.md"]
    assert code == 1 and lines[2].startswith("BUG-501: regression_tests:")

    # And with a bugs directory nobody can list: off never notices it, required
    # stops with an error rather than a pass.
    if os.geteuid() == 0:
        pytest.skip("root reads a mode-000 directory")
    q = make_project(OFF)
    q.bug("BUG-502", text=broken)
    bugs = q.root / ".adlc" / "bugs"
    os.chmod(str(bugs), 0)
    try:
        assert q.run("check")[0] == 0
        q.config(REQUIRED)
        code, lines = q.run("check")
        assert (code, lines[0]) == (2, "regression-check: error")
        assert ".adlc/bugs cannot be listed" in lines[1]
    finally:
        os.chmod(str(bugs), 0o755)


# --- BR-12 / AC-9: the same verdict on every branch ------------------------------

def test_same_verdict_on_two_branches(make_project, tmp_path, monkeypatch):
    p = make_project(REQUIRED, name="work")
    p.test_file("tests/test_601.py", "# BUG-601\n")
    p.bug("BUG-601", tests='["tests/test_601.py"]')
    p.bug("BUG-602")
    p.bug("BUG-603", tests='["tests/test_gone.py"]')
    p.commit("bugs and tests")

    # A bare origin whose default branch is `trunk`, with a different tree: no
    # tests, and BUG-601 recorded differently.
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "trunk", str(origin)],
                   check=True, capture_output=True)
    seed = tmp_path / "seed"
    _init_repo(seed, branch="trunk")
    seed_project = Project(seed)
    seed_project.config(REQUIRED)
    seed_project.bug("BUG-601", waiver='"a different record"')
    seed_project.commit("trunk")
    _git(seed, "push", "-q", str(origin), "trunk")
    p.git("remote", "add", "origin", str(origin))
    p.git("fetch", "-q", "origin")
    p.git("remote", "set-head", "origin", "trunk")

    # A feature branch whose bugs and tests match main; only the README differs.
    p.git("checkout", "-q", "-b", "feature", "main")
    p.write("README.md", "feature work\n")
    p.commit("feature")

    engine_argvs = []
    real_run = subprocess.run

    def spy(argv, *args, **kwargs):
        engine_argvs.append(list(argv))
        return real_run(argv, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(rc.subprocess, "run", spy)
        on_feature = p.run("check")
    p.git("checkout", "-q", "main")
    with monkeypatch.context() as m:
        m.setattr(rc.subprocess, "run", spy)
        on_main = p.run("check")

    assert on_main == on_feature
    assert on_main == (1, ["regression-check: fail", "passed=1 waived=0 legacy=1 failed=1",
                           "BUG-603: tests/test_gone.py does not exist"])
    # Every git call the engine made was a read of the index: no fetch, no
    # remote ref, no diff.
    assert engine_argvs
    for argv in engine_argvs:
        sub = argv[argv.index("-C") + 2]
        assert sub == "ls-files", argv
        assert not any("origin" in token or "refs/" in token for token in argv), argv


# --- BR-13 / AC-15: named ids and --require-recorded -------------------------------

def test_named_ids_and_require_recorded(make_project):
    p = make_project(REQUIRED)
    p.test_file("tests/test_701.py", "# BUG-701\n")
    p.bug("BUG-701", status="open", tests='["tests/test_701.py"]')
    p.bug("BUG-702", status="in-progress", waiver='"only reachable in production"')
    p.bug("BUG-703")

    # An unnamed run skips open bugs; legacy history does not fail it.
    assert p.run("check") == (0, ["regression-check: pass",
                                  "passed=0 waived=0 legacy=1 failed=0"])
    # A named run checks the open bug as it stands (the Phase 6 gate's case).
    assert result_of(p, "BUG-701") == (rc.PASSED, [], 0)
    assert result_of(p, "BUG-702") == (rc.WAIVED, [], 0)
    # --require-recorded also needs the test committed (test_require_recorded_
    # needs_committed_tests has the rule); committed, it passes.
    p.commit("record the regression test")
    assert result_of(p, "BUG-701", "--require-recorded") == (rc.PASSED, [], 0)
    # An id with no report fails, naming the id.
    assert result_of(p, "BUG-799") == (
        rc.FAILED, ["BUG-799: no bug report in .adlc/bugs"], 1)
    # --require-recorded turns legacy into failed, named or not.
    assert result_of(p, "BUG-703") == (rc.LEGACY, [], 0)
    assert result_of(p, "BUG-703", "--require-recorded") == (
        rc.FAILED, ["BUG-703: neither regression_tests nor regression_waiver is recorded"], 1)
    code, lines = p.run("check", "--require-recorded")
    assert (code, lines[1]) == (1, "passed=0 waived=0 legacy=0 failed=1")

    # Ids may sit either side of the flag; a repeated id is checked once.
    code, lines = p.run("check", "BUG-701", "--require-recorded", "BUG-703", "BUG-701")
    assert code == 1
    assert counts(lines) == {"passed": 1, "waived": 0, "legacy": 0, "failed": 1}

    # Two reports carrying one id is a failure, not a guess.
    p.bug("BUG-704", slug="one")
    p.bug("BUG-704", slug="two")
    assert result_of(p, "BUG-704") == (
        rc.FAILED, ["BUG-704: 2 reports in .adlc/bugs carry this id"], 1)

    # An argument that is not a bug id is a usage error, never a pass.
    for bad in ("BUG-7x", "bug-701", "REQ-701", "701"):
        code, lines = p.run("check", bad)
        assert (code, lines[0]) == (2, "regression-check: error"), bad


# --- BR-14 / AC-10: cross-repo paths ---------------------------------------------

def test_cross_repo_paths(make_project, tmp_path):
    outside = tmp_path / "elsewhere" / "nowhere"
    web = make_project(REQUIRED + (
        "repos:\n  web:\n    primary: true\n  api:\n    path: ../api\n"
        "  mobile:\n    path: ../mobile\n  ext:\n    path: %s\n  bare: {}\n" % outside),
        name="web")
    api = tmp_path / "api"
    _init_repo(api)
    api_project = Project(api)
    api_project.test_file("tests/test_api.py", "# BUG-801\n")
    api_project.test_file("tests/untracked.py", "# BUG-803\n", track=False)
    web.test_file("tests/test_web.py", "# BUG-801\n")

    web.bug("BUG-801", tests='["api:tests/test_api.py", "web:tests/test_web.py", '
                             '"tests/test_web.py"]')
    web.bug("BUG-802", tests='["ios:tests/test_ios.swift"]')
    web.bug("BUG-803", tests='["api:tests/untracked.py"]')
    web.bug("BUG-804", tests='["mobile:tests/test_m.py"]')
    web.bug("BUG-805", tests='["ext:tests/test_x.py"]')
    web.bug("BUG-806", tests='["bare:tests/test_x.py"]')

    code, lines = web.run("check")
    assert code == 1
    assert lines == [
        "regression-check: fail",
        "passed=1 waived=0 legacy=0 failed=5",
        "BUG-802: ios:tests/test_ios.swift: repo 'ios' is not declared under repos: in "
        ".adlc/config.yml",
        "BUG-803: api:tests/untracked.py is not tracked by git",
        "BUG-804: mobile:tests/test_m.py: repo 'mobile' is not cloned at ../mobile",
        "BUG-805: ext:tests/test_x.py: repo 'ext' is not cloned at its repos.ext.path",
        "BUG-806: bare:tests/test_x.py: repos.bare in .adlc/config.yml declares no path",
    ]
    assert str(tmp_path) not in "\n".join(lines)

    # The sibling clone goes missing: the bug that passed now fails, naming it.
    os.rename(str(api), str(tmp_path / "api-moved"))
    assert result_of(web, "BUG-801") == (
        rc.FAILED,
        ["BUG-801: api:tests/test_api.py: repo 'api' is not cloned at ../api"], 1)


# --- AC-6, AC-7, AC-11: the benign paths --------------------------------------------

def test_benign_fixture_exits_zero(make_project):
    p = make_project(REQUIRED)
    p.test_file("tests/test_901.py", "def test_bug_901():  # BUG-901\n    assert True\n")
    p.bug("BUG-901", tests='["tests/test_901.py"]')
    p.bug("BUG-902", waiver='"no test can reach the live webhook"')
    p.bug("BUG-903")
    p.bug("BUG-904", text=TEMPLATE_SHAPED.format(id="BUG-904"))
    assert p.run("check") == (0, ["regression-check: pass",
                                  "passed=1 waived=1 legacy=2 failed=0"])


def test_empty_and_missing_bugs_dir(make_project):
    zero = (0, ["regression-check: pass", "passed=0 waived=0 legacy=0 failed=0"])
    p = make_project(REQUIRED)
    assert not (p.root / ".adlc" / "bugs").exists()
    assert p.run("check") == zero
    (p.root / ".adlc" / "bugs").mkdir()
    assert p.run("check") == zero
    p.write(".adlc/bugs/README.md", "Bug reports live here.\n")
    p.write(".adlc/bugs/.gitkeep", "")
    assert p.run("check") == zero

    # A bugs path that is not a directory cannot be listed: an error, not a pass.
    q = make_project(REQUIRED)
    q.write(".adlc/bugs", "not a directory\n")
    code, lines = q.run("check")
    assert (code, lines) == (2, ["regression-check: error", ".adlc/bugs is not a directory"])


def test_legacy_never_fails_unflagged(make_project):
    # This repo's own bug reports from before REQ-691, copied into a sandbox:
    # each carries neither field, so each reads as legacy and none fails.
    p = make_project(REQUIRED)
    source = os.path.join(_TOOLKIT, ".adlc", "bugs")
    copied = 0
    for name in sorted(os.listdir(source)):
        if not (name.startswith("BUG-") and name.endswith(".md")):
            continue
        with open(os.path.join(source, name), encoding="utf-8") as handle:
            text = handle.read()
        if "\nregression_tests:" in text or "\nregression_waiver:" in text:
            continue  # recorded after REQ-691; not history
        p.write(".adlc/bugs/" + name, text)
        copied += 1
    assert copied >= 30
    code, lines = p.run("check")
    assert code == 0
    tally = counts(lines)
    assert tally["failed"] == 0 and tally["passed"] == 0 and tally["waived"] == 0
    assert tally["legacy"] >= 30

    # A report in the template's shape, fields left empty, is legacy too.
    q = make_project(REQUIRED)
    q.bug("BUG-905", text=TEMPLATE_SHAPED.format(id="BUG-905"))
    assert result_of(q, "BUG-905") == (rc.LEGACY, [], 0)
    # Only the explicit flag fails history.
    assert result_of(q, "BUG-905", "--require-recorded")[0] == rc.FAILED


# --- the path rules and the id match ------------------------------------------------

def test_bug_id_match_is_digit_bounded(make_project):
    assert rc.cites(b"# BUG-26\n", "BUG-26")
    assert rc.cites(b"(see BUG-26.)", "BUG-26")
    assert rc.cites(b"BUG-26", "BUG-26")
    assert not rc.cites(b"# BUG-261\n", "BUG-26")
    assert not rc.cites(b"# DEBUG-26\n", "BUG-26")
    assert not rc.cites(b"# BUG-0261\n", "BUG-261")
    assert not rc.cites(b"def test_bug_26():\n", "BUG-26")
    assert not rc.cites(b"# bug-26\n", "BUG-26")

    p = make_project(REQUIRED)
    p.test_file("tests/test_261.py", "# regression for BUG-261\n")
    p.test_file("tests/test_26.py", "# regression for BUG-26, not BUG-261\n")
    p.bug("BUG-26", tests='["tests/test_261.py"]')
    p.bug("BUG-261", tests='["tests/test_261.py"]')
    assert result_of(p, "BUG-26") == (
        rc.FAILED, ["BUG-26: tests/test_261.py does not cite BUG-26"], 1)
    assert result_of(p, "BUG-261") == (rc.PASSED, [], 0)
    p.bug("BUG-26", tests='["tests/test_26.py"]')
    assert result_of(p, "BUG-26") == (rc.PASSED, [], 0)


def test_path_rules(make_project, tmp_path):
    p = make_project(REQUIRED)
    ids = " ".join("BUG-%d" % n for n in range(950, 965))
    p.test_file("tests/test_ok.py", "# %s\n" % ids)
    os.symlink("test_ok.py", str(p.root / "tests" / "test_link.py"))
    p.git("add", "--", "tests/test_link.py")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test_out.py").write_text("# %s\n" % ids)
    os.symlink(str(outside), str(p.root / "ext"))
    p.test_file("tests/t1.py", "# %s\n" % ids)
    p.commit("tests")
    # Untracked, and a glob that would match the tracked t1.py: the pathspec is literal.
    p.test_file("tests/t[1].py", "# %s\n" % ids, track=False)
    p.test_file("tests/test_staged.py", "# %s\n" % ids)  # in the index, not committed
    absolute = str(p.root / "tests" / "test_ok.py")

    rules = [
        ("BUG-950", '["%s"]' % absolute,
         "regression_tests[1] is an absolute path; list it relative to its repository"),
        ("BUG-951", '["tests/../tests/test_ok.py"]', "tests/../tests/test_ok.py has a '..' segment"),
        ("BUG-952", '["tests/test_link.py"]', "tests/test_link.py is a symlink"),
        ("BUG-953", '["ext/test_out.py"]', "ext/test_out.py resolves outside its repository"),
        ("BUG-954", '["tests"]', "tests is not a regular file"),
        ("BUG-955", '["tests/t[1].py"]', "tests/t[1].py is not tracked by git"),
        ("BUG-956", '["tests/test_ok.py", "/etc/hosts"]',
         "regression_tests[2] is an absolute path"),
        ("BUG-957", '["web:"]', "regression_tests[1] names no path"),
        ("BUG-958", '["tests/a\x00b.py"]', "tests/a\\x00b.py is not a usable path"),
    ]
    for bug_id, tests, _ in rules:
        p.bug(bug_id, tests=tests)
    passes = [("BUG-960", '["tests/t1.py"]'), ("BUG-961", '["tests/test_staged.py"]'),
              ("BUG-962", '["./tests/test_ok.py"]'), ("BUG-963", "[ tests/test_ok.py , ]")]
    for bug_id, tests in passes:
        p.bug(bug_id, tests=tests)

    for bug_id, _, reason in rules:
        cls, failures, code = result_of(p, bug_id)
        assert (cls, code) == (rc.FAILED, 1), bug_id
        assert failures[0].startswith(bug_id + ": " + reason), failures
    for bug_id, _ in passes:
        assert result_of(p, bug_id) == (rc.PASSED, [], 0), bug_id
    code, lines = p.run("check")
    assert absolute not in "\n".join(lines) and str(tmp_path) not in "\n".join(lines)


# --- the reader, the contract, the CLI ---------------------------------------------

def test_strict_reader_shapes():
    def read(body, name="BUG-001-x.md", head="---\nid: BUG-001\nstatus: resolved\n"):
        return rc.read_report_text(head + body + "---\n", name)

    r = rc.read_report_text(TEMPLATE_SHAPED.format(id="BUG-001"), "BUG-001-x.md")
    assert (r.errors, r.tests, r.waiver, r.status) == ([], [], "", "resolved")

    r = read("regression_tests: [ \"tests/a.py\" , 'tests/b''s.py', tests/c.py, ]  # c\n")
    assert r.errors == [] and r.tests == ["tests/a.py", "tests/b's.py", "tests/c.py"]
    r = read('regression_waiver: "the \\"live\\" path \\\\ only"\n')
    assert r.errors == [] and r.waiver == 'the "live" path \\ only'
    r = rc.read_report_text("﻿<!-- a note -->\r\n\r\n---\r\nid: BUG-001\r\n"
                            "status: \"closed\"  # c\r\nregression_tests:\r\n---\r\n",
                            "BUG-001-x.md")
    assert (r.errors, r.status, r.tests) == ([], "closed", None)
    assert read("", head="---\nid: BUG-001\nstatus: ~\n").status is None

    refused = [
        ('regression_waiver: "line\\nbreak"\n', "regression_waiver: a backslash escape"),
        ("regression_waiver: |\n", "regression_waiver: a block scalar"),
        ("regression_tests: &a [x]\n", "regression_tests: a YAML construct"),
        ("regression_tests: [a # c]\n", "regression_tests: the flow list is not closed"),
        ("regression_tests: [a] b\n", "regression_tests: text follows the closing ]"),
        ('regression_waiver: "a" b\n', "regression_waiver: text follows the closing quote"),
        ("regression_tests: [a]\n  - b\n", "regression_tests: the value continues"),
        ("  regression_tests: [a]\n", "regression_tests: written in a spelling"),
        ("regression_tests : [a]\n", "regression_tests: written in a spelling"),
        ("status: [resolved]\n", "status: appears 2 times"),
        ("id: [BUG-001]\n", "id: appears 2 times"),
    ]
    for body, reason in refused:
        r = read(body)
        assert any(text.startswith(reason) for text in r.reasons()), (body, r.reasons())

    r = rc.read_report_text("---\nid: [BUG-001]\n---\n", "BUG-001-x.md")
    assert r.reasons() == ["id: must be a string, not a list"]
    r = rc.read_report_text("---\nid: BUG-001\n", "BUG-001-x.md")
    assert r.reasons() == ["the frontmatter opens with --- and never closes"]
    assert not r.status_known()
    r = rc.read_report_text("---\nid: BUG-001\nstatus: open\ntags: []\ntags: []\n---\n",
                            "BUG-001-x.md")
    assert r.status_known() and r.status == "open"
    r = rc.read_report_text("---\nid: BUG-001\nstatus: resolved\n---\n", "BUG-x.md")
    assert r.reasons() == ["the file name does not start with BUG-<digits>"]


def test_engine_is_stdlib_only_and_reads_no_remote():
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        for name in names:
            if os.path.isfile(os.path.join(_ADLC_DIR, name + ".py")):
                continue
            spec = importlib.util.find_spec(name)
            assert spec is not None, name
            origin = spec.origin or ""
            assert origin in ("built-in", "frozen") or \
                os.path.realpath(origin).startswith(stdlib + os.sep), (name, origin)
            assert "site-packages" not in origin, (name, origin)

    # The git subcommands the engine names: ls-files for the index, rev-parse to
    # locate the checkout, show-ref and rev-parse to resolve --base exactly,
    # ls-tree and cat-file to read the config at that ref, and cat-file for the
    # committed check. It never fetches or diffs, and the one ref it names
    # itself is each repository's own HEAD, for that check alone.
    words = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)):
            words.update(e.value for e in node.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str))
    for word in ("fetch", "diff", "ls-remote", "remote", "log", "show", "merge-base",
                 "origin", "FETCH_HEAD", "HEAD", "main", "--path-format=absolute"):
        assert word not in words, word
    for word in ("ls-files", "rev-parse", "show-ref", "--verify", "ls-tree", "cat-file"):
        assert word in words, word
    heads = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "HEAD"]
    assert len(heads) == 1 and rc._COMMITTED_REV == "HEAD", heads

    # The git environment drops at least everything lane_check.py drops.
    assert set(lane_check._GIT_ENV_SCRUB) <= set(rc._GIT_ENV_SCRUB)
    assert rc._GIT_ENV_SCRUB_PREFIXES == lane_check._GIT_ENV_SCRUB_PREFIXES


def test_adlc_subcommand_runs_the_engine(make_project):
    entry = adlc.SUBCOMMANDS["regression-check"]
    assert callable(entry["handler"]) and entry["help"]

    p = make_project()
    proc = subprocess.run([sys.executable, _ADLC, "regression-check", "mode"], cwd=p.path,
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout.splitlines()[0] == "regression-test: off"

    p.config(REQUIRED)
    p.bug("BUG-990", tests='["tests/missing.py"]')
    proc = subprocess.run([sys.executable, _ADLC, "regression-check", "check"], cwd=p.path,
                          capture_output=True, text=True)
    assert proc.returncode == 1
    assert proc.stdout.splitlines()[:2] == ["regression-check: fail",
                                            "passed=0 waived=0 legacy=0 failed=1"]

    proc = subprocess.run([sys.executable, _ADLC, "--help"], cwd=p.path,
                          capture_output=True, text=True)
    assert "regression-check" in proc.stdout


def test_usage_errors_are_errors_never_a_pass(tmp_path):
    cases = [
        ([], "regression-check: error"),
        (["frob"], "regression-check: error"),
        (["check", "--help"], "regression-check: error"),
        (["check", "--req"], "regression-check: error"),
        (["mode", "-h"], "regression-test: error"),
        (["mode", "BUG-001"], "regression-test: error"),
        (["check", "--root", str(tmp_path / "missing")], "regression-check: error"),
    ]
    for argv, first in cases:
        code, lines = run_engine(argv)
        assert (code, lines[0], len(lines)) == (2, first, 2), argv
        assert str(tmp_path) not in lines[1]


def test_output_names_no_home_path_and_no_contents(make_project, tmp_path):
    p = make_project(REQUIRED)
    p.test_file("tests/test_secret.py", "API_KEY = 'sk-live-0123456789abcdef'\n")
    p.bug("BUG-980", tests='["tests/test_secret.py"]')
    p.bug("BUG-981", tests='["%s"]' % (p.root / "tests" / "test_secret.py"))
    p.bug("BUG-982", tests='["tests/evil name.py"]')
    code, lines = p.run("check")
    text = "\n".join(lines)
    assert code == 1 and len(lines) == 5
    assert "sk-live" not in text
    assert str(tmp_path) not in text and os.path.realpath(str(tmp_path)) not in text
    assert " " not in text and "tests/evil\\u2028name.py does not exist" in text


# --- REQ-691 Phase 5 findings ---------------------------------------------------------

def _commit_all(path, msg="change"):
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "--no-verify", "-m", msg)


def test_base_reads_the_setting_and_repos_at_the_ref(make_project, tmp_path):
    # The gate's config comes from the ref the caller names, so a fix branch
    # cannot switch its own gate off or re-point a sibling (finding: gate config
    # read from the tree under check).
    p = make_project(REQUIRED + "repos:\n  web:\n    primary: true\n  api:\n    path: ../api\n",
                     name="web")
    api = tmp_path / "api"
    _init_repo(api)
    Project(api).test_file("tests/test_api.py", "# BUG-1101\n")
    p.bug("BUG-1101", tests='["api:tests/test_api.py"]')
    p.bug("BUG-1102", tests='["tests/missing.py"]')
    p.commit("required on main")
    p.git("checkout", "-q", "-b", "fix")

    # The branch turns its gate off and drops repos: in its working tree.
    p.config(OFF)
    assert p.run("check")[1][0] == "regression-check: off"
    expected = (1, ["regression-check: fail", "passed=1 waived=0 legacy=0 failed=1",
                    "BUG-1102: tests/missing.py does not exist"])
    assert p.run("check", "--base", "refs/heads/main") == expected
    assert p.run("mode", "--base", "refs/heads/main") == (0, [
        "regression-test: required",
        "bugfix.regression_test is required in .adlc/config.yml at refs/heads/main"])
    # Deleted from the working tree: still required, and repos: still resolves.
    os.remove(str(p.root / ".adlc" / "config.yml"))
    assert p.run("check", "--base", "refs/heads/main") == expected
    assert p.run("check", "--base", "refs/heads/main", "BUG-1101") == (
        0, ["regression-check: pass", "passed=1 waived=0 legacy=0 failed=0"])
    # Without --base the disk decides, as before.
    assert p.run("mode")[1][0] == "regression-test: off"

    # The ref says off: off, naming the ref, and no bug report is opened.
    q = make_project(OFF, name="q")
    q.bug("BUG-1103", tests='["unclosed')
    q.commit("off on main")
    q.config(REQUIRED)
    assert q.run("check", "--base", "refs/heads/main") == (0, [
        "regression-check: off",
        "regression tests are off for this project: bugfix.regression_test is off in "
        ".adlc/config.yml at refs/heads/main"])
    # No config at the ref is off with the no-config wording, saying where.
    r = make_project(name="r")
    r.write("README.md", "no config here\n")
    r.commit("no config")
    r.config(REQUIRED)
    assert r.run("mode", "--base", "refs/heads/main") == (0, [
        "regression-test: off",
        ".adlc/config.yml does not exist at refs/heads/main, which means off; set "
        "bugfix.regression_test: required in it to turn regression tests on"])
    # A config at the ref without the key is absent there.
    s = make_project("project:\n  name: x\n", name="s")
    s.commit("keyless")
    s.config(REQUIRED)
    code, lines = s.run("mode", "--base", "refs/heads/main")
    assert (code, lines[0]) == (0, "regression-test: off")
    assert lines[1].startswith("bugfix.regression_test is not set in .adlc/config.yml at refs/heads/main")
    # The same parse and validation rules apply to the bytes at the ref.
    t = make_project("bugfix:\n  regression_test: sometimes\n", name="t")
    t.commit("bad value")
    t.config(REQUIRED)
    code, lines = t.run("check", "--base", "refs/heads/main")
    assert (code, lines[0], len(lines)) == (2, "regression-check: error", 2)
    assert "'sometimes'" in lines[1] and ".adlc/config.yml at refs/heads/main" in lines[1]
    # A symlink in the config's place at the ref is refused, not followed.
    u = make_project(name="u")
    u.write("real.yml", REQUIRED)
    (u.root / ".adlc").mkdir()
    os.symlink("../real.yml", str(u.root / ".adlc" / "config.yml"))
    u.commit("linked config")
    code, lines = u.run("mode", "--base", "refs/heads/main")
    assert (code, lines) == (2, ["regression-test: error",
                                 ".adlc/config.yml is a symlink at refs/heads/main; the check reads "
                                 "only a regular file"])


def test_base_ref_is_validated(make_project, tmp_path):
    p = make_project(REQUIRED)
    p.commit("config")
    for bad in ("-x", "main..dev", "main^{tree}", "main:README.md", "a b", "main@{1}",
                "main~1", ""):
        for verb, first in (("check", "regression-check: error"),
                            ("mode", "regression-test: error")):
            code, lines = p.run(verb, "--base=" + bad)
            assert (code, lines[0], len(lines)) == (2, first, 2), bad
            assert lines[1].startswith("usage: "), (bad, lines)
    # A well-formed ref that names nothing is an error, never off.
    code, lines = p.run("check", "--base", "refs/heads/nosuch")
    assert (code, lines) == (2, ["regression-check: error",
                                 "--base refs/heads/nosuch does not resolve to a commit"])
    # A root outside any git work tree cannot be read at a ref.
    plain = tmp_path / "plain"
    (plain / ".adlc").mkdir(parents=True)
    (plain / ".adlc" / "config.yml").write_text(REQUIRED)
    code, lines = run_engine(["mode", "--root", str(plain), "--base", "refs/heads/main"])
    assert (code, lines[0]) == (2, "regression-test: error")
    assert "not inside a git work tree" in lines[1] and str(tmp_path) not in lines[1]


def test_base_reads_a_subdirectory_project_at_its_prefix(tmp_path):
    repo = tmp_path / "mono"
    _init_repo(repo)
    (repo / "README.md").write_text("monorepo\n")
    proj = Project(repo / "sub" / "proj")
    proj.config(REQUIRED)
    proj.bug("BUG-1201", tests='["tests/missing.py"]')
    _commit_all(repo, "a project in a subdirectory")
    proj.config(OFF)
    code, lines = run_engine(["check", "--root", proj.path, "--base", "refs/heads/main"])
    assert (code, lines) == (1, ["regression-check: fail", "passed=0 waived=0 legacy=0 failed=1",
                                 "BUG-1201: tests/missing.py does not exist"])


# --- REQ-691 re-verify: --base is a full ref; --require-recorded needs commits --------

def test_base_must_be_a_full_ref(make_project):
    # A short name, HEAD, FETCH_HEAD, ORIG_HEAD or a bare sha is a usage error:
    # none of them is certainly the integration branch, and git resolves a short
    # origin/main to a tag of that name before the remote-tracking branch.
    p = make_project(REQUIRED)
    p.commit("config")
    sha = p.git("rev-parse", "HEAD").stdout.strip()
    p.git("update-ref", "refs/remotes/origin/main", "HEAD")
    p.git("update-ref", "ORIG_HEAD", "HEAD")
    (p.root / ".git" / "FETCH_HEAD").write_text("%s\t\tbranch 'main' of origin\n" % sha)
    for bad in ("main", "origin/main", "heads/main", "remotes/origin/main", "HEAD",
                "FETCH_HEAD", "ORIG_HEAD", sha, sha[:12], "refs/tags/v1", "refs/main",
                "refs/heads/", "refs/remotes/origin/", "refs/heads//main", "refs/heads/.main",
                "refs/heads/main.lock", "refs/heads/main.", "refs/remotes/origin/a..b",
                "refs/heads/main^{commit}", "refs/heads/main:x", "refs/heads/main@{1}"):
        for verb, first in (("check", "regression-check: error"),
                            ("mode", "regression-test: error")):
            code, lines = p.run(verb, "--base", bad)
            assert (code, lines[0], len(lines)) == (2, first, 2), bad
            assert lines[1].startswith("usage: ") and "name a full ref" in lines[1], (bad, lines)
    # Both full forms are usable.
    for good in ("refs/heads/main", "refs/remotes/origin/main"):
        assert p.run("mode", "--base", good) == (0, [
            "regression-test: required",
            "bugfix.regression_test is required in .adlc/config.yml at %s" % good])


def test_base_is_never_a_tag_of_the_same_name(make_project):
    # A tag named origin/main, or refs/remotes/origin/main, never stands in for the
    # remote-tracking branch. Plain rev-parse falls through to the second when the
    # branch is missing, so the ref is resolved with show-ref --verify.
    p = make_project(OFF)
    p.commit("off: the commit both tags point at")
    off = p.git("rev-parse", "HEAD").stdout.strip()
    p.config(REQUIRED)
    p.bug("BUG-1901", status="open")
    p.commit("required: the integration branch")
    for tag in ("origin/main", "refs/remotes/origin/main"):
        p.git("tag", tag, off)
    # The remote-tracking branch is not there yet: an error, never the tag's off.
    for verb, first in (("mode", "regression-test: error"), ("check", "regression-check: error")):
        code, lines = p.run(verb, "--base", "refs/remotes/origin/main")
        assert (code, lines) == (2, [first, "--base refs/remotes/origin/main does not resolve "
                                            "to a commit"]), verb
    # Once it exists, the branch is read, whatever the tags say.
    p.git("update-ref", "refs/remotes/origin/main", "HEAD")
    assert p.run("mode", "--base", "refs/remotes/origin/main") == (0, [
        "regression-test: required",
        "bugfix.regression_test is required in .adlc/config.yml at refs/remotes/origin/main"])
    assert p.run("check", "--require-recorded", "--base", "refs/remotes/origin/main",
                 "BUG-1901") == (1, [
        "regression-check: fail", "passed=0 waived=0 legacy=0 failed=1",
        "BUG-1901: neither regression_tests nor regression_waiver is recorded"])


def test_require_recorded_needs_committed_tests(make_project, tmp_path):
    # Under --require-recorded a listed test must be committed in its repository's
    # HEAD, and that copy must cite the id: what merges is the commits. A sibling's
    # staged test was the hole, since the Gate's clean-tree guard covers only the
    # primary checkout. Without the flag the worktree-and-index rules are unchanged.
    api = tmp_path / "api"
    _init_repo(api)
    sib = Project(api)
    sib.write("README.md", "api\n")
    sib.commit("api")
    p = make_project(REQUIRED + "repos:\n  api:\n    path: ../api\n", name="web")
    p.test_file("tests/test_2001.py", "# BUG-2001\n")
    p.bug("BUG-2001", status="open", tests='["tests/test_2001.py"]')
    sib.test_file("tests/test_api.py", "# BUG-2002\n")
    p.bug("BUG-2002", status="open", tests='["api:tests/test_api.py"]')
    # Staged, not committed: passes the plain check, fails the recorded one.
    for bug_id, entry in (("BUG-2001", "tests/test_2001.py"),
                          ("BUG-2002", "api:tests/test_api.py")):
        assert result_of(p, bug_id) == (rc.PASSED, [], 0), bug_id
        assert result_of(p, bug_id, "--require-recorded") == (
            rc.FAILED, ["%s: the bug report is not committed (not in HEAD); commit it; "
                        "%s is not committed (not in HEAD)" % (bug_id, entry)], 1), bug_id
    # Committed: passes both.
    p.commit("record BUG-2001")
    sib.commit("the sibling's test")
    for bug_id in ("BUG-2001", "BUG-2002"):
        assert result_of(p, bug_id, "--require-recorded") == (rc.PASSED, [], 0), bug_id
    # Committed without the id, the id added only in the working tree (and the index).
    sib.write("tests/test_old.py", "# an old test\n")
    sib.commit("an old test")
    sib.test_file("tests/test_old.py", "# an old test, now for BUG-2003\n")
    p.bug("BUG-2003", status="open", tests='["api:tests/test_old.py"]')
    p.commit("record BUG-2003")
    assert result_of(p, "BUG-2003") == (rc.PASSED, [], 0)
    assert result_of(p, "BUG-2003", "--require-recorded") == (
        rc.FAILED, ["BUG-2003: api:tests/test_old.py does not cite BUG-2003 in its committed "
                    "copy (HEAD)"], 1)
    # A project in a subdirectory names its tests from its own directory.
    mono = tmp_path / "mono"
    _init_repo(mono)
    proj = Project(mono / "sub" / "proj")
    proj.config(REQUIRED)
    proj.write("tests/test_2004.py", "# BUG-2004\n")
    proj.bug("BUG-2004", status="open", tests='["tests/test_2004.py"]')
    _commit_all(mono, "a project in a subdirectory")
    code, lines = run_engine(["check", "--root", proj.path, "--require-recorded", "BUG-2004"])
    assert (code, lines) == (0, ["regression-check: pass", "passed=1 waived=0 legacy=0 failed=0"])


def test_unquoted_waiver_is_the_wrong_type(make_project):
    # LESSON-716: a plain value means something different to every reader
    # (false, 0, a cut at ' #'), so a waiver must be quoted.
    p = make_project(REQUIRED)
    plain = [("BUG-1401", "false"), ("BUG-1402", "0"), ("BUG-1403", "reason: a colon"),
             ("BUG-1404", "- dash"), ("BUG-1405", "a plain reason  # and a comment")]
    for bug_id, raw in plain:
        p.bug(bug_id, waiver=raw)
    for bug_id, _ in plain:
        assert result_of(p, bug_id) == (rc.FAILED, [
            "%s: regression_waiver: must be a quoted string, not an unquoted value" % bug_id],
            1), bug_id
    # Benign: either quote style is a waiver; the template's "" and an empty
    # value are absent.
    p.bug("BUG-1406", waiver='"false"')
    p.bug("BUG-1407", waiver="'a reason: with a colon'")
    p.bug("BUG-1408", waiver='""')
    p.bug("BUG-1409", waiver="")
    p.bug("BUG-1410", waiver="~")
    assert result_of(p, "BUG-1406") == (rc.WAIVED, [], 0)
    assert result_of(p, "BUG-1407") == (rc.WAIVED, [], 0)
    for bug_id in ("BUG-1408", "BUG-1409", "BUG-1410"):
        assert result_of(p, bug_id) == (rc.LEGACY, [], 0), bug_id


def test_relative_sibling_resolves_from_the_main_worktree(tmp_path):
    # /proceed resolves repos.<id>.path from the primary checkout, so a fix
    # worktree under it must resolve ../api the same way (BUG-210's rule).
    api = tmp_path / "api"
    _init_repo(api)
    Project(api).test_file("tests/test_api.py", "# BUG-1301 BUG-1302 BUG-1303\n")

    primary = tmp_path / "web"
    _init_repo(primary)
    web = Project(primary)
    web.config(REQUIRED + "repos:\n  web:\n    primary: true\n  api:\n    path: ../api\n"
               "  abs:\n    path: %s\n" % api)
    web.write(".gitignore", ".worktrees/\n")
    web.commit("config")
    web.git("worktree", "add", "-q", "-b", "fix", ".worktrees/fix")
    fix = Project(primary / ".worktrees" / "fix")
    fix.bug("BUG-1301", tests='["api:tests/test_api.py"]')
    fix.bug("BUG-1302", tests='["abs:tests/test_api.py"]')
    assert result_of(fix, "BUG-1301") == (rc.PASSED, [], 0)
    # An absolute repos path to an existing clone passes, from either checkout.
    assert result_of(fix, "BUG-1302") == (rc.PASSED, [], 0)
    web.bug("BUG-1301", tests='["api:tests/test_api.py"]')
    assert result_of(web, "BUG-1301") == (rc.PASSED, [], 0)

    # A project in a subdirectory: the path is relative to the project's place
    # in the primary checkout (mono/sub/proj/../../../api is the sibling).
    mono = tmp_path / "mono"
    _init_repo(mono)
    proj = Project(mono / "sub" / "proj")
    proj.config(REQUIRED + "repos:\n  api:\n    path: ../../../api\n")
    (mono / ".gitignore").write_text(".worktrees/\n")
    _commit_all(mono, "nested project")
    _git(mono, "worktree", "add", "-q", "-b", "fix", ".worktrees/fix")
    nested = Project(mono / ".worktrees" / "fix" / "sub" / "proj")
    nested.bug("BUG-1303", tests='["api:tests/test_api.py"]')
    assert result_of(nested, "BUG-1303") == (rc.PASSED, [], 0)
    proj.bug("BUG-1303", tests='["api:tests/test_api.py"]')
    assert result_of(proj, "BUG-1303") == (rc.PASSED, [], 0)


def test_parse_failure_that_cannot_define_the_setting_is_off(make_project):
    # The prefilter's backslash and trailing-comment hits force a parse; when the
    # subset refuses the file and nothing in it is shaped like either key, the
    # config cannot define the setting, so it is off, not a stop.
    benign = [
        'defaults: &d\na: 1\nlint:\n  pattern: "src\\\\.*"\n',
        'lint:\n  pattern: "src\\.*"\n',
        "notes: >\n  folded text\nwin: C:\\tools\n",
        "anchor: &a 1\nfoo: 1  # regression_test\n",
    ]
    for text in benign:
        p = make_project(text)
        assert p.run("mode") == (0, [
            "regression-test: off",
            "bugfix.regression_test is not set in .adlc/config.yml, which means off; set it "
            "to required to turn regression tests on"]), text
        assert p.run("check")[0] == 0, text
    # Positive control: a key-shaped occurrence of either key still stops.
    stops = [
        "defaults: &d\nbugfix:\n  regression_test: required\n",
        "notes: >\n  x\nci:\n  regression_test: required\n",
        "{bugfix: {regression_test: required}, a: &x 1}\n",
        "a: &x 1\n'bugfix': x\n",
        '"bug\\x66ix":\n  "regression\\x5ftest": required\n',
        REQUIRED.encode("utf-16-le"),
    ]
    for text in stops:
        p = make_project(text)
        code, lines = p.run("mode")
        assert (code, lines[0]) == (2, "regression-test: error"), text
        assert "bugfix.regression_test" in lines[1]


def test_bugfix_block_is_always_validated(make_project, monkeypatch):
    for text, fragment in (("bugfix:\n  regresion_test: required\n", "'regresion_test'"),
                           ("bugfix:\n  other: 1\n", "'other'"),
                           ("bugfix: required\n", "bugfix in .adlc/config.yml is a string")):
        p = make_project(text)
        for verb, first in (("mode", "regression-test: error"),
                            ("check", "regression-check: error")):
            code, lines = p.run(verb)
            assert (code, lines[0], len(lines)) == (2, first, 2), text
            assert fragment in lines[1], (text, lines)
    # Benign: bugfix named only in a comment is still never parsed.
    parsed = []
    real_loads = rc.harness_yaml.loads
    monkeypatch.setattr(rc.harness_yaml, "loads",
                        lambda text, source="<string>": parsed.append(source)
                        or real_loads(text, source))
    p = make_project("# bugfix:\n#   regresion_test: required\nproject:\n  name: x\n")
    assert p.run("mode")[1][0] == "regression-test: off"
    assert parsed == []


def test_nested_keys_are_not_misspellings(make_project):
    # LESSON-404 / LESSON-716: a read key's name under another key's block, or
    # inside a block scalar, is a mention, not the key.
    p = make_project(REQUIRED)
    p.bug("BUG-1501", extra=["deploy:", "  status: live", "  id: rev-12"])
    p.bug("BUG-1502", status="open",
          extra=["notes: |", "  regression_tests: none yet", "  status: resolved"])
    p.bug("BUG-1503", status="open", extra=["ci:", "  status: green"])
    p.bug("BUG-1504", extra=["checks:", "- name: lint", "  status: green"])
    assert p.run("check") == (0, ["regression-check: pass",
                                  "passed=0 waived=0 legacy=2 failed=0"])
    for bug_id in ("BUG-1501", "BUG-1502", "BUG-1503", "BUG-1504"):
        assert result_of(p, bug_id) == (rc.LEGACY, [], 0), bug_id

    # Positive control: with no block open above it, an indented read key is
    # still a misspelling, and it makes the status unknown.
    q = make_project(REQUIRED)
    q.bug("BUG-1505", status="open", extra=["  status: resolved"])
    q.bug("BUG-1506", status="open", extra=["deploy: live", "  status: resolved"])
    q.bug("BUG-1507", extra=["  regression_tests: [\"tests/x.py\"]"])
    code, lines = q.run("check")
    assert (code, lines[1]) == (1, "passed=0 waived=0 legacy=0 failed=3")
    assert [line.split(":")[0] for line in lines[2:]] == ["BUG-1505", "BUG-1506", "BUG-1507"]
    for line in lines[2:]:
        assert "written in a spelling not every reader agrees on" in line


def test_symlinks_out_of_the_root_are_refused(make_project, tmp_path):
    outside = tmp_path / "outside"
    (outside / "bugs").mkdir(parents=True)
    secret = bug_text("BUG-1601").replace("id: BUG-1601", "id: sk-live-0123456789")
    (outside / "BUG-1601-x.md").write_text(secret)
    (outside / "bugs" / "BUG-1604-x.md").write_text(secret.replace("1601", "1604"))
    (outside / "config.yml").write_text(REQUIRED + "# sk-live-0123456789\n")

    # A symlinked bug report fails, wherever it points, and its target is not read.
    p = make_project(REQUIRED)
    (p.root / ".adlc" / "bugs").mkdir(parents=True)
    os.symlink(str(outside / "BUG-1601-x.md"), str(p.root / ".adlc" / "bugs" / "BUG-1601-x.md"))
    p.write("docs/BUG-1602.md", bug_text("BUG-1602", status="open"))
    os.symlink("../../docs/BUG-1602.md", str(p.root / ".adlc" / "bugs" / "BUG-1602-x.md"))
    failed = ["BUG-1601: is a symlink; a bug report must be a regular file in .adlc/bugs",
              "BUG-1602: is a symlink; a bug report must be a regular file in .adlc/bugs"]
    code, lines = p.run("check")
    assert (code, lines) == (1, ["regression-check: fail",
                                 "passed=0 waived=0 legacy=0 failed=2"] + failed)
    assert result_of(p, "BUG-1601") == (rc.FAILED, failed[:1], 1)
    text = "\n".join(lines)
    assert "sk-live" not in text and str(tmp_path) not in text

    # A bugs directory, or a .adlc, that resolves outside the root is an error.
    q = make_project(REQUIRED)
    os.symlink(str(outside / "bugs"), str(q.root / ".adlc" / "bugs"))
    assert q.run("check") == (2, ["regression-check: error",
                                  ".adlc/bugs resolves outside the project root"])
    r = make_project()
    os.symlink(str(outside), str(r.root / ".adlc"))
    for verb, first in (("mode", "regression-test: error"), ("check", "regression-check: error")):
        code, lines = r.run(verb)
        assert (code, lines[0], len(lines)) == (2, first, 2)
        assert ".adlc/config.yml resolves outside the project root" in lines[1]
        assert "sk-live" not in lines[1] and str(tmp_path) not in lines[1]
    # With --base the config comes from the ref; the bugs still may not leave the root.
    b = make_project(REQUIRED)
    b.commit("config")
    shutil.rmtree(str(b.root / ".adlc"))
    os.symlink(str(outside), str(b.root / ".adlc"))
    assert b.run("check", "--base", "refs/heads/main") == (
        2, ["regression-check: error", ".adlc resolves outside the project root"])

    # A disk config that is a symlink out of the root is an error, never followed.
    s = make_project()
    (s.root / ".adlc").mkdir()
    os.symlink(str(outside / "config.yml"), str(s.root / ".adlc" / "config.yml"))
    code, lines = s.run("mode")
    assert (code, lines[0]) == (2, "regression-test: error")
    assert ".adlc/config.yml resolves outside the project root" in lines[1]
    assert "sk-live" not in lines[1]

    # Benign: a config link and a bugs link that stay inside the root are followed.
    t = make_project()
    t.write("conf/adlc.yml", REQUIRED)
    (t.root / ".adlc").mkdir()
    os.symlink("../conf/adlc.yml", str(t.root / ".adlc" / "config.yml"))
    t.write("docs/bugs/BUG-1603-x.md", bug_text("BUG-1603"))
    os.symlink("../docs/bugs", str(t.root / ".adlc" / "bugs"))
    assert t.run("mode")[1][0] == "regression-test: required"
    assert t.run("check") == (0, ["regression-check: pass",
                                  "passed=0 waived=0 legacy=1 failed=0"])


def test_output_escaping_matches_lane_check():
    # The copy is deliberate (the engine imports nothing but harness_yaml); this
    # pins it to lane_check.py's, so a fix to one cannot miss the other.
    assert rc._UNSAFE_RE.pattern == lane_check._UNSAFE_RE.pattern
    samples = ["plain", "a\\b", "line\nbreak\r", "\x00\x1f\x7f\x85\x9f", "\u2028\u2029",
               "\u202e\u2066\u2069", "\ufeff\u200b\u200f\u061c", "\udcff", "caf\u00e9"]
    for sample in samples:
        assert rc.one_line(sample) == lane_check.one_line(sample), sample
    assert all("\n" not in rc.one_line(s) and len(rc.one_line(s).splitlines()) <= 1
               for s in samples)


def test_git_that_cannot_run_fails_the_bug(make_project, monkeypatch, tmp_path):
    api = tmp_path / "api"
    _init_repo(api)
    Project(api).test_file("tests/test_api.py", "# BUG-1701\n")
    p = make_project(REQUIRED + "repos:\n  api:\n    path: ../api\n", name="web")
    p.test_file("tests/test_1701.py", "# BUG-1701\n")
    p.bug("BUG-1701", tests='["tests/test_1701.py", "api:tests/test_api.py"]')
    p.commit("config")
    # Positive control: with git on PATH the bug passes.
    assert result_of(p, "BUG-1701") == (rc.PASSED, [], 0)

    nogit = tmp_path / "nogit"
    nogit.mkdir()
    monkeypatch.setenv("PATH", str(nogit))
    cls, failures, code = result_of(p, "BUG-1701")
    assert (cls, code) == (rc.FAILED, 1)
    assert failures[0].startswith("BUG-1701: tests/test_1701.py cannot be checked: git could "
                                  "not be run; api:tests/test_api.py")
    assert "git could not be run" in failures[0].split("; ")[1]
    code, lines = p.run("check")
    assert (code, lines[1]) == (1, "passed=0 waived=0 legacy=0 failed=1")
    # With --base, a git that cannot run is an error, never off.
    code, lines = p.run("mode", "--base", "refs/heads/main")
    assert (code, lines[0]) == (2, "regression-test: error")
    assert "git could not be run" in lines[1]


def test_unnamed_run_fails_duplicate_ids(make_project):
    p = make_project(REQUIRED)
    p.test_file("tests/test_1801.py", "# BUG-1801\n")
    p.bug("BUG-1801", slug="one", tests='["tests/test_1801.py"]')
    p.bug("BUG-1801", slug="two", waiver='"a reason"')
    # Both open: out of an unnamed run's scope, like any open bug.
    p.bug("BUG-1802", slug="one", status="open")
    p.bug("BUG-1802", slug="two", status="open")
    reason = "BUG-1801: 2 reports in .adlc/bugs carry this id"
    assert p.run("check") == (1, ["regression-check: fail",
                                  "passed=0 waived=0 legacy=0 failed=2", reason, reason])
    assert result_of(p, "BUG-1801") == (rc.FAILED, [reason], 1)


def test_require_recorded_needs_the_report_committed_as_on_disk(make_project):
    # The report is read from the working tree, and the Gate's clean-tree guard
    # trusts git status, which a skip-worktree (or assume-unchanged) entry
    # silences. A waiver written only on disk and hidden that way must not pass
    # the recorded check: the PR merges the commits, not the disk copy.
    p = make_project(REQUIRED)
    p.bug("BUG-2101", status="open")
    p.commit("BUG-2101 with nothing recorded")
    rel = ".adlc/bugs/BUG-2101-fixture.md"
    assert result_of(p, "BUG-2101", "--require-recorded") == (
        rc.FAILED, ["BUG-2101: neither regression_tests nor regression_waiver is recorded"], 1)
    p.bug("BUG-2101", status="open", waiver='"only on disk"')
    subprocess.run(["git", "-C", p.path, "update-index", "--skip-worktree", rel], check=True)
    assert subprocess.run(["git", "-C", p.path, "status", "--porcelain"],
                          capture_output=True, check=True).stdout == b""
    # The plain check still judges the disk copy; the recorded one refuses it.
    assert result_of(p, "BUG-2101") == (rc.WAIVED, [], 0)
    assert result_of(p, "BUG-2101", "--require-recorded") == (
        rc.FAILED, ["BUG-2101: the bug report differs from its committed copy (HEAD); "
                    "commit it"], 1)
    # Committed as it stands, the waiver counts.
    subprocess.run(["git", "-C", p.path, "update-index", "--no-skip-worktree", rel], check=True)
    p.commit("record the waiver")
    assert result_of(p, "BUG-2101", "--require-recorded") == (rc.WAIVED, [], 0)


def test_require_recorded_refuses_a_committed_symlink_test(make_project):
    # A symlink committed where the test should be, its target text citing the
    # id, with a regular file on disk hidden by skip-worktree: the committed
    # entry is not a test file, as the disk rule already says of a symlink.
    p = make_project(REQUIRED)
    rel = "tests/test_2201.py"
    os.makedirs(os.path.join(p.path, "tests"))
    os.symlink("BUG-2201.py", os.path.join(p.path, rel))
    p.bug("BUG-2201", status="open", tests='["%s"]' % rel)
    p.commit("a symlink in the test's place")
    os.remove(os.path.join(p.path, rel))
    p.write(rel, "# BUG-2201\n")
    subprocess.run(["git", "-C", p.path, "update-index", "--skip-worktree", rel], check=True)
    assert result_of(p, "BUG-2201", "--require-recorded") == (
        rc.FAILED, ["BUG-2201: %s is not committed as a regular file (HEAD)" % rel], 1)
