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
        "bugfix:\n  other: 1\n",
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
    for bug_id in ("BUG-106", "BUG-107", "BUG-108"):
        assert result_of(p, bug_id) == (rc.WAIVED, [], 0), bug_id
    code, lines = p.run("check")
    assert counts(lines) == {"passed": 0, "waived": 3, "legacy": 3, "failed": 2}


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

    # The only git subcommand the engine names is ls-files.
    words = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)):
            words.update(e.value for e in node.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str))
    for word in ("fetch", "diff", "ls-remote", "remote", "log", "show", "cat-file",
                 "rev-parse", "merge-base", "origin", "FETCH_HEAD"):
        assert word not in words, word
    assert "ls-files" in words

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
