"""REQ-722 TASK-280 — tools/delegate/cross_family.py, the cross-family reviewer's decisions.

One class per subcommand. ``decide`` is pinned against an independent oracle over
every combination of its inputs (BR-2, BR-3, BR-4). ``validate`` is fed delegate
output against a real git checkout built in ``tmp_path``, so the path, line and
membership checks run for real (BR-6, AC-8). ``check-decline`` and
``check-dispositions`` pin BR-8 and AC-9, each with a must-not-fire case;
``check-decline`` is static, so a hostile tree under review is never run
(LESSON-718), and ``deferred`` is refused on a Critical or must-fix finding.
``pr-section`` pins byte stability and that every repo, status, reason and both
families are named (BR-5).
"""
import ast
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DELEGATE_DIR = REPO_ROOT / "tools" / "delegate"
SCRIPT = DELEGATE_DIR / "cross_family.py"
WORKFLOW = REPO_ROOT / "workflows" / "adlc-sprint.workflow.js"

sys.path.insert(0, str(DELEGATE_DIR))
import cross_family as CF  # noqa: E402
import run_outcome as RO  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

KNOWN = ("anthropic", "openai", "moonshot", "google", "meta", "other")
SPEC_REL = ".adlc/specs/REQ-001-sample/requirement.md"
SPEC = """---
id: REQ-001
---
## Description

Mentions BR-9: in prose, which is not a rule.

## Business Rules

- [ ] BR-1: the first rule
- [ ] BR-2: the second rule,
  continued on a second line
- [x] BR-4: numbering may skip a number

## Acceptance Criteria

- [ ] first criterion
- [x] second criterion
  - [ ] a nested item is not an AC
- [ ] third criterion

## Out of Scope

- [ ] BR-7: outside the section, so not a rule
"""
APP_LINES = 10


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def _main(capsys, *args):
    rc = CF.main(list(args))
    return rc, capsys.readouterr().out


_GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e"}


def _git(root, *args):
    env = dict(os.environ, **_GIT_ENV)
    return subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
                          check=True, env=env, capture_output=True, text=True).stdout


def _make_repo(root):
    """A checkout with a 10-line src/app.py, a 3-line src/util.py, a README and
    a spec, committed in two commits so a base ref exists."""
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_text("readme\nsecond\n", encoding="utf-8")
    spec = root / SPEC_REL
    spec.parent.mkdir(parents=True)
    spec.write_text(SPEC, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("".join("line %d\n" % i for i in range(1, APP_LINES + 1)),
                                         encoding="utf-8")
    (root / "src" / "util.py").write_text("a\nb\nc", encoding="utf-8")  # no final newline
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "change")
    return base


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "wt"
    base = _make_repo(root)
    changed = tmp_path / "changed.txt"
    changed.write_text("src/app.py\nsrc/util.py\n", encoding="utf-8")
    return {"root": root, "base": base, "changed": changed, "spec": root / SPEC_REL,
            "tmp": tmp_path}


def _validate(repo, text, *extra):
    out = repo["tmp"] / "delegate-out.txt"
    out.write_text(text, encoding="utf-8")
    args = ["validate", "--output", str(out), "--worktree", str(repo["root"]),
            "--spec", str(repo["spec"])]
    if not extra:
        args += ["--changed-files", str(repo["changed"])]
    proc = _run(*args, *extra)
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None), proc


GOOD = "FINDING\tMajor\tsrc/app.py\t3\tunchecked-null-return\tnull read on the retry path"


# --- the module itself --------------------------------------------------------

def test_skip_reasons_are_closed_and_ordered():
    assert CF.SKIP_REASONS == (
        "subagent-mode", "delegation-disabled", "no-binary", "family-unknown",
        "same-family", "redaction-failed", "api-error", "invalid-output",
    )


def test_class_pattern_equals_workflow_and_run_outcome():
    """One class pattern across the three engines (LESSON-441)."""
    js = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"^const FINDING_CLASS_PATTERN = '([^']+)';", js, re.M)
    assert m, "the workflow engine still defines FINDING_CLASS_PATTERN as one string"
    assert CF.FINDING_CLASS_PATTERN == m.group(1)
    assert RO.CLASS_RE.pattern.replace("\\Z", "$") == CF.FINDING_CLASS_PATTERN


def test_stdlib_only_and_loads_by_path_without_sys_path(tmp_path):
    """run_outcome.py loads this file by path for SKIP_REASONS: nothing on sys.path."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"yaml", "openai", "model_family", "_common", "_machine_config"}
    probe = ("import importlib.util, sys\n"
             "s = importlib.util.spec_from_file_location('cf', sys.argv[1])\n"
             "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
             "print(m.SKIP_REASONS[0], m.decide(False, '0', 'openai', 'moonshot'))\n")
    proc = subprocess.run([sys.executable, "-I", "-c", probe, str(SCRIPT)], cwd=str(tmp_path),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["subagent-mode", "None"]


def test_review_question_asks_for_the_two_line_types():
    q = CF.REVIEW_QUESTION
    assert "RULE<TAB><id><TAB><mark><TAB><note>" in q
    assert "FINDING<TAB><severity><TAB><path><TAB><line><TAB><class><TAB><title>" in q
    assert "every BR and every AC" in q
    for word in ("met, partial or unmet", "Critical, Major, Minor or Nit", "defect"):
        assert word in q
    proc = _run("question")
    assert proc.returncode == 0 and proc.stdout == q + "\n"


# --- decide -------------------------------------------------------------------

def _oracle(subagent, gate_rc, implementer, reviewer):
    """The BR-4 precedence, restated independently of the module."""
    if subagent == "1":
        return "skip subagent-mode"
    if gate_rc == "2":
        return "skip no-binary"
    if gate_rc != "0":
        return "skip delegation-disabled"
    if implementer not in KNOWN or reviewer not in KNOWN:
        return "skip family-unknown"
    if implementer == reviewer:
        return "skip same-family"
    return "run"


_FAMS = ("anthropic", "moonshot", "unknown", "Anthropic")
_COMBOS = list(itertools.product(("0", "1"), ("0", "1", "2", "7", "x"), _FAMS, _FAMS))


class TestDecide:
    @pytest.mark.parametrize("subagent,gate_rc,implementer,reviewer", _COMBOS)
    def test_precedence_one_reason(self, capsys, subagent, gate_rc, implementer, reviewer):
        rc, out = _main(capsys, "decide", "--subagent", subagent, "--gate-rc", gate_rc,
                        "--implementer", implementer, "--reviewer", reviewer)
        assert rc == 0
        words = out.split()
        assert words == ["run"] or (len(words) == 2 and words[0] == "skip"
                                    and words[1] in CF.SKIP_REASONS[:5]), out
        assert out.strip() == _oracle(subagent, gate_rc, implementer, reviewer)

    def test_equal_families_skip_same_family(self, capsys):
        for family in KNOWN:
            rc, out = _main(capsys, "decide", "--subagent", "0", "--gate-rc", "0",
                            "--implementer", family, "--reviewer", family)
            assert (rc, out) == (0, "skip same-family\n"), family
        proc = _run("decide", "--subagent", "0", "--gate-rc", "0",
                    "--implementer", "anthropic", "--reviewer", "anthropic")
        assert (proc.returncode, proc.stdout) == (0, "skip same-family\n")

    @pytest.mark.parametrize("implementer,reviewer", [
        ("unknown", "moonshot"), ("anthropic", "unknown"), ("unknown", "unknown"),
        ("claude-opus-4", "moonshot"), ("anthropic", "kimi-k2.6"), ("", "moonshot"),
        ("OPENAI", "openai"),
    ])
    def test_unknown_family_skips_family_unknown(self, capsys, implementer, reviewer):
        """BR-3: unknown, or anything that is not a declared member, never runs."""
        rc, out = _main(capsys, "decide", "--subagent", "0", "--gate-rc", "0",
                        "--implementer", implementer, "--reviewer", reviewer)
        assert (rc, out) == (0, "skip family-unknown\n")

    def test_runs_when_nothing_skips(self, capsys):
        """Benign path: authorized, two different declared families, not subagent."""
        for implementer, reviewer in itertools.permutations(KNOWN, 2):
            rc, out = _main(capsys, "decide", "--subagent", "0", "--gate-rc", "0",
                            "--implementer", implementer, "--reviewer", reviewer)
            assert (rc, out) == (0, "run\n"), (implementer, reviewer)

    @pytest.mark.parametrize("gate_rc", ["1", "3", "127", "-1", "00", " 0", ""])
    def test_any_other_gate_rc_fails_closed(self, capsys, gate_rc):
        rc, out = _main(capsys, "decide", "--subagent", "0", "--gate-rc", gate_rc,
                        "--implementer", "anthropic", "--reviewer", "moonshot")
        assert (rc, out) == (0, "skip delegation-disabled\n")

    def test_bad_subagent_value_is_usage(self):
        proc = _run("decide", "--subagent", "yes", "--gate-rc", "0",
                    "--implementer", "anthropic", "--reviewer", "moonshot")
        assert proc.returncode == 2 and proc.stdout == ""


# --- validate -----------------------------------------------------------------

_BAD_FINDINGS = [
    ("dotdot path", "FINDING\tMajor\t../etc/passwd\t1\tpath-traversal\tx"),
    ("dotdot inside", "FINDING\tMajor\tsrc/../src/app.py\t1\tpath-traversal\tx"),
    ("absolute path", "FINDING\tMajor\t/etc/passwd\t1\tpath-traversal\tx"),
    ("outside changed files", "FINDING\tMajor\tREADME.md\t1\tdoc-drift\tx"),
    ("path off charset", "FINDING\tMajor\tsrc/app.py;rm\t1\tbad-path\tx"),
    ("line past end", "FINDING\tMajor\tsrc/app.py\t%d\toff-by-one\tx" % (APP_LINES + 1)),
    ("line zero", "FINDING\tMajor\tsrc/app.py\t0\toff-by-one\tx"),
    ("line not an integer", "FINDING\tMajor\tsrc/app.py\t3a\toff-by-one\tx"),
    ("line range", "FINDING\tMajor\tsrc/app.py\t2-3\toff-by-one\tx"),
    ("past end, no final newline", "FINDING\tMinor\tsrc/util.py\t4\toff-by-one\tx"),
    ("severity off enum", "FINDING\tHigh\tsrc/app.py\t3\toff-by-one\tx"),
    ("severity case", "FINDING\tmajor\tsrc/app.py\t3\toff-by-one\tx"),
    ("class with spaces", "FINDING\tMajor\tsrc/app.py\t3\tTask Ordering\tx"),
    ("class seven words", "FINDING\tMajor\tsrc/app.py\t3\ta-b-c-d-e-f-g\tx"),
    ("class short lesson", "FINDING\tMajor\tsrc/app.py\t3\tLESSON-1\tx"),
    ("class snake case", "FINDING\tMajor\tsrc/app.py\t3\tsnake_case\tx"),
    ("too few fields", "FINDING\tMajor\tsrc/app.py\t3\toff-by-one"),
]


@needs_git
class TestValidate:
    def test_valid_finding_passes(self, repo):
        rc, data, _ = _validate(repo, GOOD + "\n")
        assert rc == 0
        assert data == {
            "findings": [{"severity": "Major", "file": "src/app.py", "line": 3,
                          "class": "unchecked-null-return",
                          "title": "null read on the retry path", "mustFix": False,
                          "userFacing": False, "source": ["cross-family"]}],
            "dropped": 0, "ruleMarks": {"met": 0, "partial": 0, "unmet": 0},
        }

    @pytest.mark.parametrize("label,bad", _BAD_FINDINGS, ids=[b[0] for b in _BAD_FINDINGS])
    def test_each_bad_field_dropped_and_counted(self, repo, label, bad):
        """BR-6 / AC-8: the bad line drops and counts; the good one beside it stays
        (the benign path: a valid finding is never caught by the same checks)."""
        rc, data, _ = _validate(repo, GOOD + "\n" + bad + "\n")
        assert rc == 0, label
        assert data["dropped"] == 1, label
        assert [f["file"] for f in data["findings"]] == ["src/app.py"]
        assert data["findings"][0]["line"] == 3

    def test_last_line_without_final_newline_is_in_range(self, repo):
        rc, data, _ = _validate(repo, "FINDING\tNit\tsrc/util.py\t3\tstyle-nit\tlast line\n")
        assert rc == 0 and data["findings"][0]["line"] == 3

    def test_all_dropped_is_invalid_output(self, repo):
        text = "\n".join(bad for _, bad in _BAD_FINDINGS) + "\nRULE\tBR-3\tmet\tno such rule\n"
        rc, data, proc = _validate(repo, text)
        assert rc == 3
        assert data["findings"] == [] and data["dropped"] == len(_BAD_FINDINGS) + 1
        assert proc.stderr == ""

    @pytest.mark.parametrize("text", [
        "", "Looks good to me.\nNo issues found.\n",
        '{"findings": [{"severity": "Major"}]}',
        "FINDING Major src/app.py 3 off-by-one spaces not tabs\n",
        "FINDINGS:\n- none\n",
    ])
    def test_unparseable_output_is_invalid(self, repo, text):
        rc, data, _ = _validate(repo, text)
        assert rc == 3 and data["findings"] == [] and data["dropped"] == 0

    def test_non_grammar_lines_ignored_not_counted(self, repo):
        text = ("Here is my review.\n\nFINDINGS:\n" + GOOD + "\n"
                "  RULE\tBR-1\tmet\tleading spaces are tolerated\nThanks!\n")
        rc, data, _ = _validate(repo, text)
        assert rc == 0 and data["dropped"] == 0
        assert len(data["findings"]) == 1 and data["ruleMarks"]["met"] == 1

    def test_rule_unmet_becomes_major_must_fix_on_spec(self, repo):
        rc, data, _ = _validate(repo, "RULE\tBR-2\tunmet\tthe diff has no retry\n")
        assert rc == 0
        spec_line = SPEC.split("\n").index("- [ ] BR-2: the second rule,") + 1
        assert data["findings"] == [{
            "severity": "Major", "file": SPEC_REL, "line": spec_line,
            "class": "omitted-requirement", "title": "BR-2 unmet: the diff has no retry",
            "mustFix": True, "userFacing": False, "source": ["cross-family"]}]
        assert data["ruleMarks"] == {"met": 0, "partial": 0, "unmet": 1}

    def test_rule_partial_is_minor_and_met_is_counted_only(self, repo):
        text = ("RULE\tAC-3\tpartial\tonly one path tested\nRULE\tBR-1\tmet\tok\n"
                "RULE\tAC-1\tmet\n")
        rc, data, _ = _validate(repo, text)
        assert rc == 0
        assert [(f["severity"], f["mustFix"], f["class"], f["title"]) for f in data["findings"]] == [
            ("Minor", False, "omitted-requirement", "AC-3 partial: only one path tested")]
        assert data["ruleMarks"] == {"met": 2, "partial": 1, "unmet": 0}

    def _state(self, repo, data):
        path = repo["tmp"] / "pipeline-state.json"
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return str(path)

    def test_multi_repo_unmet_is_a_minor_that_never_blocks(self, repo):
        """A sibling repo may implement the rule: one repo's diff cannot show it unmet."""
        state = self._state(repo, {"repos": {"web": {"touched": True}, "api": {"touched": True},
                                             "docs": {"touched": False}}})
        text = "RULE\tBR-2\tunmet\tthe diff has no retry\nRULE\tAC-3\tpartial\thalf\n"
        rc, data, _ = _validate(repo, text, "--changed-files", str(repo["changed"]), "--state", state)
        assert rc == 0
        assert [(f["severity"], f["mustFix"], f["class"], f["title"]) for f in data["findings"]] == [
            ("Minor", False, "omitted-requirement",
             "BR-2 unmet in this repo, may be met in another repo: the diff has no retry"),
            ("Minor", False, "omitted-requirement", "AC-3 partial: half")]
        assert data["ruleMarks"] == {"met": 0, "partial": 1, "unmet": 1}

    @pytest.mark.parametrize("state", [
        {"repos": {"web": {"touched": True}}},
        {"repos": {"web": {"touched": True}, "api": {"touched": False}, "docs": {}}},
        {"repos": {}},
        {"req": "REQ-001"},
    ], ids=["one-touched", "one-of-three-touched", "empty-repos", "no-repos"])
    def test_one_touched_repo_unmet_stays_major_must_fix(self, repo, state):
        """Must-not-fire neighbour: a single-repo run keeps the blocking mark."""
        rc, data, _ = _validate(repo, "RULE\tBR-2\tunmet\tno retry\n", "--changed-files",
                                str(repo["changed"]), "--state", self._state(repo, state))
        assert rc == 0
        assert [(f["severity"], f["mustFix"], f["title"]) for f in data["findings"]] == [
            ("Major", True, "BR-2 unmet: no retry")]

    @pytest.mark.parametrize("bad", [
        None, "not json", "[1, 2]", '{"repos": [1]}', '{"repos": {"web": "touched"}}',
        '{"repos": {"web": {"touched": "true"}, "api": {"touched": true}}}',
        '{"repos": {"web": {"touched": 1}, "api": {"touched": 1}}}',
    ], ids=["missing", "not-json", "not-object", "repos-list", "entry-string",
            "touched-string", "touched-int"])
    def test_unreadable_or_malformed_state_is_usage_never_one_repo(self, repo, bad):
        """A state that cannot be read must not silently decide the repo count."""
        state = str(repo["tmp"] / "missing.json") if bad is None else self._state(repo, bad)
        rc, data, proc = _validate(repo, "RULE\tBR-2\tunmet\tno retry\n", "--changed-files",
                                   str(repo["changed"]), "--state", state)
        assert rc == 2 and data is None
        assert proc.stderr.startswith("cross-family: ")

    @pytest.mark.parametrize("rid", ["BR-3", "BR-7", "BR-9", "AC-4", "AC-0", "BR-01", "REQ-1",
                                     "br-1", "BR-1 "])
    def test_rule_id_absent_from_spec_dropped(self, repo, rid):
        rc, data, _ = _validate(repo, GOOD + "\nRULE\t%s\tunmet\tx\n" % rid)
        assert rc == 0 and data["dropped"] == 1
        assert all(f["file"] != SPEC_REL for f in data["findings"])

    def test_rule_bad_mark_dropped(self, repo):
        rc, data, _ = _validate(repo, GOOD + "\nRULE\tBR-1\tdone\tx\nRULE\tBR-1\n")
        assert rc == 0 and data["dropped"] == 2

    def test_rule_only_output_is_valid_with_no_findings(self, repo):
        rc, data, _ = _validate(repo, "RULE\tBR-1\tmet\tok\nRULE\tBR-2\tmet\tok\n")
        assert rc == 0 and data["findings"] == [] and data["ruleMarks"]["met"] == 2

    def test_rule_marked_twice_keeps_worst_mark(self, repo):
        text = "RULE\tBR-1\tmet\tfine\nRULE\tBR-1\tunmet\tmissing\nRULE\tBR-1\tpartial\thalf\n"
        rc, data, _ = _validate(repo, text)
        assert rc == 0 and data["dropped"] == 0
        assert data["ruleMarks"] == {"met": 0, "partial": 0, "unmet": 1}
        assert [f["title"] for f in data["findings"]] == ["BR-1 unmet: missing"]

    def test_free_text_cut_to_charset_and_length(self, repo):
        title = "$(rm -rf ~) `x` <script>|&;" + "y" * 500
        rc, data, _ = _validate(repo, "FINDING\tCritical\tsrc/app.py\t1\tshell-injection\t%s\n" % title)
        assert rc == 0
        got = data["findings"][0]
        assert got["mustFix"] is True
        assert len(got["title"]) <= CF.FREE_TEXT_LIMIT
        assert re.fullmatch(r"[A-Za-z0-9 .,:/_-]*", got["title"])
        assert "  " not in got["title"], "space runs collapse"
        assert got["title"].startswith("rm -rf x script ")

    @pytest.mark.parametrize("raw,expected", [
        ("it's \"quoted\"; (see) a.py:3", "it s quoted see a.py:3"),
        ("tabs\tand\nnewlines  and   spaces", "tabs and newlines and spaces"),
        ("keep . , : / _ - as written", "keep . , : / _ - as written"),
        ("  ;;;  ", ""),
        (None, ""),
    ])
    def test_cut_keeps_only_the_narrow_charset(self, raw, expected):
        """Must-fire (quote, ';', parentheses, control characters) and must-not-fire
        (the kept punctuation) neighbours of the narrowed free-text charset."""
        assert CF.cut(raw) == expected
        assert len(CF.cut("a " * 300)) <= CF.FREE_TEXT_LIMIT

    def test_constrained_fields_are_not_redacted(self, repo):
        """LESSON-744: a class that a credential chain would match is kept as written."""
        cls = "task-ordering-race-abcdefghijklmnop"
        rc, data, _ = _validate(repo, "FINDING\tMinor\tsrc/app.py\t2\t%s\tx\n" % cls)
        assert rc == 0 and data["findings"][0]["class"] == cls

    def test_line_range_reads_head_not_disk(self, repo):
        with open(repo["root"] / "src" / "app.py", "a", encoding="utf-8") as handle:
            handle.write("uncommitted\n" * 5)
        rc, data, _ = _validate(repo, GOOD + "\nFINDING\tMajor\tsrc/app.py\t12\toff-by-one\tx\n")
        assert rc == 0 and data["dropped"] == 1

    def test_changed_files_from_base_ref(self, repo):
        rc, data, _ = _validate(repo, GOOD + "\nFINDING\tMajor\tREADME.md\t1\tdoc-drift\tx\n",
                                "--base", repo["base"])
        assert rc == 0 and data["dropped"] == 1 and len(data["findings"]) == 1

    def test_missing_inputs_are_usage_errors(self, repo):
        proc = _run("validate", "--output", str(repo["tmp"] / "nope"), "--worktree",
                    str(repo["root"]), "--spec", str(repo["spec"]),
                    "--changed-files", str(repo["changed"]))
        assert proc.returncode == 2
        _, _, proc = _validate(repo, GOOD, "--spec", str(repo["spec"]))  # neither list nor base
        assert proc.returncode == 2

    def test_worktree_without_its_own_git_checks_nothing(self, tmp_path):
        """LESSON-743: a directory inside a repo but not its root must not borrow
        the enclosing repo's HEAD; every line check fails closed."""
        outer = tmp_path / "outer"
        _make_repo(outer)
        inner = outer / "src"
        changed = tmp_path / "changed.txt"
        changed.write_text("src/app.py\napp.py\n", encoding="utf-8")
        out = tmp_path / "o.txt"
        out.write_text(GOOD + "\n", encoding="utf-8")
        proc = _run("validate", "--output", str(out), "--worktree", str(inner),
                    "--spec", str(outer / SPEC_REL), "--changed-files", str(changed))
        assert proc.returncode == 3


class TestSpecRules:
    def test_numbering_matches_validate(self, tmp_path):
        spec = tmp_path / "requirement.md"
        spec.write_text(SPEC, encoding="utf-8")
        rules = CF.spec_rules(SPEC)
        assert list(rules) == ["BR-1", "BR-2", "BR-4", "AC-1", "AC-2", "AC-3"]
        assert rules["BR-2"][1] == "the second rule, continued on a second line"
        proc = _run("spec-rules", "--spec", str(spec))
        assert proc.returncode == 0
        assert proc.stdout.splitlines()[0] == "BR-1: the first rule"
        assert proc.stdout.splitlines()[-1] == "AC-3: third criterion"

    def test_fenced_rules_are_not_rules(self):
        text = "## Business Rules\n\n```\n- [ ] BR-5: in a fence\n```\n- [ ] BR-6: real\n"
        assert list(CF.spec_rules(text)) == ["BR-6"]


# --- check-decline ------------------------------------------------------------

_TEST_FILES = {
    "tests/test_app.py": ("def helper():\n    pass\n\n\ndef test_guard():\n    assert helper() is None\n\n\n"
                          "class TestRetry:\n    def test_param(self):\n        pass\n\n"
                          "    def setup_method(self):\n        pass\n"),
    "web/ui.test.js": ("const test = require('node:test');\n"
                       "test('renders empty state', () => {});\n"
                       "test(\"keeps order\", () => {});\n"
                       "t.test('nested subtest', () => {});\n"),
    "partials/tests/x.test.sh": ("check() { :; }\nbegin case_one\ntest_two() {\n  :\n}\n"),
    "pkg/x_test.go": "package pkg\n\nfunc TestX(t *testing.T) {}\nfunc helperX() {}\n",
    "tools/helper.py": "def test_not_a_test_file():\n    pass\n",
}


def _commit_tests(repo, files=_TEST_FILES, message="tests"):
    for rel, body in files.items():
        path = repo["root"] / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _git(repo["root"], "add", ".")
    _git(repo["root"], "commit", "-q", "-m", message)


@needs_git
class TestCheckDecline:
    @pytest.mark.parametrize("reason,qualifies", [
        ("src/app.py:3 already returns early on None", True),
        ("the guard at src/app.py:2-4.", True),
        ("(see src/util.py:3)", True),
        ("README.md:1 documents the limit", True),
        ("no citation here, I just disagree", False),
        ("", False),
        ("../etc/passwd:1", False),
        ("src/app.py:3 and ../etc/passwd:1", False),
        ("src/../src/app.py:3", False),
        ("src/app.py:%d is past the end" % (APP_LINES + 1), False),
        ("src/app.py:0", False),
        ("src/app.py:3-%d" % (APP_LINES + 1), False),
        ("src/app.py:5-3", False),
        ("untracked.py:1", False),
        ("src/app.py says so", False),
    ])
    def test_reason_needs_checkable_citation(self, repo, reason, qualifies):
        """BR-8, with benign cases: a reason citing real code qualifies."""
        (repo["root"] / "untracked.py").write_text("x\n", encoding="utf-8")
        proc = _run("check-decline", "--reason", reason, "--worktree", str(repo["root"]))
        assert proc.returncode == (0 if qualifies else 1), proc.stdout
        assert proc.stdout.startswith("qualifies: " if qualifies else "does not qualify: ")

    @pytest.mark.parametrize("reason,qualifies", [
        ("test:tests/test_app.py::test_guard exercises the null path and passes", True),
        ("test:tests/test_app.py::TestRetry::test_param covers it", True),
        ("test:tests/test_app.py::test_param.", True),
        ("test:tests/test_app.py::test_guard[a-b] passes", True),
        ("test:tests/test_app.py::test_guard: passes", True),
        ("test:web/ui.test.js::renders empty state covers it", True),
        ("test:web/ui.test.js::keeps order", True),
        ("test:partials/tests/x.test.sh::case_one passes", True),
        ("test:partials/tests/x.test.sh::test_two", True),
        ("test:pkg/x_test.go::TestX: passes", True),
        # must-not-fire neighbours of each of the above
        ("test:tests/test_app.py::test_missing passes", False),
        ("test:tests/test_app.py::helper is called", False),
        ("test:tests/test_app.py::setup_method", False),
        ("test:tests/test_app.py::test_guardian", False),
        ("test:tests/test_app.py::test_guard::deeper", False),
        ("test:tests/test_app.py::TestRetry::test_guard", False),
        ("test:web/ui.test.js::renders", False),
        ("test:web/ui.test.js::nested subtest", False),
        ("test:partials/tests/x.test.sh::check", False),
        ("test:pkg/x_test.go::helperX", False),
        ("test:tools/helper.py::test_not_a_test_file", False),
        ("test:tests/test_new.py::test_new", False),
        ("test:tests/test_staged.py::test_staged", False),
        ("test:../x_test.py::test_a", False),
        ("test:tests/../tests/test_app.py::test_guard", False),
        ("test:/abs/test_app.py::test_guard", False),
        ("tests/test_app.py::test_guard", False),
    ])
    def test_test_citation_checked_statically(self, repo, reason, qualifies):
        """A ``test:<path>::<name>`` qualifies only for a tracked test file whose
        HEAD blob defines the name; an untracked or staged-only file never does."""
        _commit_tests(repo)
        (repo["root"] / "tests" / "test_new.py").write_text("def test_new():\n    pass\n", encoding="utf-8")
        (repo["root"] / "tests" / "test_staged.py").write_text("def test_staged():\n    pass\n",
                                                               encoding="utf-8")
        _git(repo["root"], "add", "tests/test_staged.py")
        proc = _run("check-decline", "--reason", reason, "--worktree", str(repo["root"]))
        assert proc.returncode == (0 if qualifies else 1), (reason, proc.stdout)

    def test_test_citations_execute_nothing(self, repo):
        """LESSON-718: the tree under review is never run. A hostile conftest.py, a
        pytest.py that would shadow the real one, and a config naming python as the
        stack are all present, and none of them runs."""
        marker = repo["tmp"] / "executed"
        payload = "open(%r, 'a').write(__name__ + '\\n')\n" % str(marker)
        _commit_tests(repo, {"conftest.py": payload, "pytest.py": payload,
                             "tests/conftest.py": payload, "tests/__init__.py": payload,
                             ".adlc/config.yml": "stack:\n  languages: [python]\n",
                             "tests/test_app.py": _TEST_FILES["tests/test_app.py"]}, "hostile")
        for reason, rc in (("test:tests/test_app.py::test_guard passes", 0),
                           ("test:tests/test_app.py::test_absent passes", 1)):
            proc = subprocess.run([sys.executable, str(SCRIPT), "check-decline", "--reason", reason,
                                   "--worktree", str(repo["root"])], cwd=str(repo["root"]),
                                  capture_output=True, text=True)
            assert proc.returncode == rc, proc.stdout + proc.stderr
        state = _state(repo["tmp"], [_finding(disposition="declined",
                                              declineReason="test:tests/test_app.py::test_guard")])
        proc = subprocess.run([sys.executable, str(SCRIPT), "check-dispositions", "--state", str(state),
                               "--worktree", str(repo["root"])], cwd=str(repo["root"]),
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout
        assert not marker.exists(), marker.read_text()

    def test_no_test_runner_option_or_code_remains(self, repo):
        """The lister is gone: no option names it, and the module runs no subprocess
        but git."""
        proc = _run("check-decline", "--reason", "src/app.py:3", "--worktree", str(repo["root"]),
                    "--test-lister", "true")
        assert proc.returncode == 2
        source = SCRIPT.read_text(encoding="utf-8")
        for gone in ("--collect-only", "test-lister", "LISTER_TIMEOUT_S", "STACK_TEST_LISTERS",
                     "_stack_languages", '"pytest"', "shlex"):
            assert gone not in source, gone
        calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
                 and getattr(n.func.value, "id", None) == "subprocess"]
        assert len(calls) == 1 and '["git", "-C"' in ast.get_source_segment(source, calls[0])

    @pytest.mark.parametrize("path,kind", [
        ("tests/test_a.py", "python"), ("a_test.py", "python"), ("ui.test.js", "js"),
        ("x.test.sh", "sh"), ("pkg/x_test.go", "go"),
        ("tests/a.py", None), ("testing.py", None), ("ui.spec.js", None), ("x.test.ts", None),
        ("test_a.pyc", None), ("x_test.go.bak", None),
    ])
    def test_test_file_kinds(self, path, kind):
        assert CF.test_file_kind(path) == kind

    def test_python_tests_are_parsed_never_imported(self):
        blob = b"import os\nos.system('touch /tmp/never')\ndef test_a():\n    pass\n"
        assert CF.defined_tests("tests/test_x.py", blob) == frozenset({"test_a"})
        assert CF.defined_tests("tests/test_x.py", b"def test_a(:\n") == frozenset()
        assert CF.defined_tests("tests/test_x.py", b"\0def test_a(): pass\n") == frozenset()

    def test_citation_tokens_match_what_check_decline_parses(self):
        text = ("see src/a.py:3-4, test:tests/test_x.py::test_y passes; README.md:1 and "
                "test:web/ui.test.js::renders empty state, not a.py:x or test:a.py:1")
        got = [text[a:b] for a, b, _ in CF.citation_tokens(text)]
        assert got == ["src/a.py:3-4", "test:tests/test_x.py::test_y", "README.md:1",
                       "test:web/ui.test.js::renders", "a.py:1"]
        assert [p for _, _, p in CF.citation_tokens(text)] == [
            "src/a.py", "tests/test_x.py", "README.md", "web/ui.test.js", "a.py"]
        assert CF.citation_tokens(None) == [] and CF.citation_tokens("no citation") == []

    def test_redacted_reason_still_qualifies(self, repo):
        """A citation the credential chain would cut into survives R3 (run_outcome
        keeps citation tokens whole), so a reason that qualified at Step C still
        qualifies at Phase 6."""
        rel = "tools/risk-assessment-" + "x" * 20 + ".py"
        _commit_tests(repo, {rel: "".join("v%d = %d\n" % (i, i) for i in range(1, 16))}, "risk")
        reason = "%s:12 clamps it before the read" % rel
        assert RO.redact(reason) != reason, "the chain alone would mangle this citation"
        checker = CF.DeclineChecker(str(repo["root"]))
        stored = RO.normalize_findings([_finding(disposition="declined", declineReason=reason)], checker)
        assert stored[0]["declineReason"] == reason
        assert checker.verdict(stored[0]["declineReason"]) == (True, "cites %s:12" % rel)
        assert checker.verdict(RO.redact(reason))[0] is False

    def test_enclosing_repo_is_not_asked(self, tmp_path):
        """LESSON-743: README.md is tracked by the enclosing repo, at its root;
        from a nested directory with no .git it must not qualify."""
        outer = tmp_path / "outer"
        _make_repo(outer)
        (outer / "src" / "README.md").write_text("nested\n", encoding="utf-8")
        (outer / "src" / "test_n.py").write_text("def test_n():\n    pass\n", encoding="utf-8")
        _git(outer, "add", ".")
        _git(outer, "commit", "-q", "-m", "nested readme")
        checker = CF.DeclineChecker(str(outer / "src"))
        assert checker.verdict("README.md:1")[0] is False
        assert checker.verdict("test:test_n.py::test_n")[0] is False
        assert CF.DeclineChecker(str(outer)).verdict("README.md:1")[0] is True
        assert CF.DeclineChecker(str(outer)).verdict("test:src/test_n.py::test_n")[0] is True


# --- check-dispositions -------------------------------------------------------

def _finding(**extra):
    base = {"severity": "Major", "file": "src/app.py", "line": 3, "class": "off-by-one",
            "title": "loop bound", "source": ["cross-family"]}
    base.update(extra)
    return base


def _state(tmp_path, findings=None, **extra):
    data = {"req": "REQ-001"}
    if findings is not None:
        data["verify"] = {"findings": findings, "loops": 0}
    data.update(extra)
    path = tmp_path / "pipeline-state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _dispositions(repo, path):
    return _run("check-dispositions", "--state", str(path), "--worktree", str(repo["root"]))


@needs_git
class TestCheckDispositions:
    def test_undisposed_finding_fails(self, repo):
        state = _state(repo["tmp"], [
            _finding(),
            _finding(title="merged one", source=["panel", "cross-family"]),
            _finding(title="panel only", source=["panel"]),
            {"severity": "Minor", "file": "a.md", "title": "pre-REQ shape"},
        ])
        proc = _dispositions(repo, state)
        assert proc.returncode == 1
        lines = proc.stdout.splitlines()
        assert lines == [
            "cross-family finding no disposition: Major src/app.py:3 loop bound",
            "cross-family finding no disposition: Major src/app.py:3 merged one",
        ]

    def test_decline_without_reason_is_undisposed(self, repo):
        """AC-9: a decline with no qualifying reason is no disposition."""
        for reason in (None, "", "trust me", "../etc/passwd:1", "src/app.py:99"):
            extra = {"disposition": "declined"}
            if reason is not None:
                extra["declineReason"] = reason
            proc = _dispositions(repo, _state(repo["tmp"], [_finding(**extra)]))
            assert proc.returncode == 1, reason
            assert "declined without a qualifying reason" in proc.stdout
        ok = _state(repo["tmp"], [_finding(disposition="declined",
                                           declineReason="src/app.py:3 bounds the loop")])
        proc = _dispositions(repo, ok)
        assert proc.returncode == 0, proc.stdout

    def test_every_disposition_kind_passes(self, repo):
        state = _state(repo["tmp"], [
            _finding(disposition="fixed"), _finding(disposition="deferred"),
            _finding(fixed=True),
            _finding(disposition="declined", declineReason="see src/util.py:1-3"),
        ])
        proc = _dispositions(repo, state)
        assert (proc.returncode, proc.stdout) == (0, "cross-family dispositions: none outstanding\n")

    @pytest.mark.parametrize("extra,ok", [
        ({"severity": "Critical"}, False),
        ({"severity": "Major", "mustFix": True}, False),
        ({"severity": "Minor", "mustFix": True}, False),
        ({"severity": "Major", "mustFix": "yes"}, False),
        ({"severity": "Major", "mustFix": 1}, False),
        ({"severity": "Critical", "fixed": True}, False),
        ({"severity": "high"}, False),
        ({"severity": None}, False),
        ({"severity": "Minor"}, True),
        ({"severity": "Major"}, True),
        ({"severity": "Major", "mustFix": False}, True),
        ({"severity": "Major", "mustFix": 0}, True),
        ({"severity": "Nit"}, True),
    ], ids=["critical", "must-fix-major", "must-fix-minor", "must-fix-string", "must-fix-int",
            "critical-fixed-flag", "severity-off-enum", "severity-absent", "minor", "major",
            "major-must-fix-false", "major-must-fix-zero", "nit"])
    def test_deferred_only_when_neither_critical_nor_must_fix(self, repo, extra, ok):
        """Step C: a Critical or must-fix Major is always fixed, never deferred. A
        severity that cannot be read cannot be shown not to be Critical."""
        finding = _finding(disposition="deferred", **extra)
        if extra.get("severity") is None:
            finding.pop("severity")
        proc = _dispositions(repo, _state(repo["tmp"], [finding]))
        assert proc.returncode == (0 if ok else 1), proc.stdout
        if not ok:
            assert proc.stdout.startswith(
                "cross-family finding deferred, but a Critical or must-fix finding is never deferred: ")

    def test_critical_and_must_fix_pass_when_fixed_or_declined(self, repo):
        """Must-not-fire neighbour: only ``deferred`` is refused on them."""
        state = _state(repo["tmp"], [
            _finding(severity="Critical", disposition="fixed"),
            _finding(severity="Major", mustFix=True, fixed=True),
            _finding(severity="Critical", disposition="declined", declineReason="src/app.py:3"),
        ])
        proc = _dispositions(repo, state)
        assert proc.returncode == 0, proc.stdout

    @pytest.mark.parametrize("findings", [None, [], [{"severity": "Major", "file": "a.js",
                                                      "title": "t", "class": "x", "fixed": False}]])
    def test_pre_req_state_passes(self, repo, findings):
        proc = _dispositions(repo, _state(repo["tmp"], findings))
        assert proc.returncode == 0

    def test_unknown_disposition_is_undisposed(self, repo):
        proc = _dispositions(repo, _state(repo["tmp"], [_finding(disposition="ignored")]))
        assert proc.returncode == 1

    def test_unreadable_state_is_usage_not_outstanding(self, repo):
        proc = _dispositions(repo, repo["tmp"] / "missing.json")
        assert proc.returncode == 2
        bad = repo["tmp"] / "bad.json"
        bad.write_text("[1, 2]", encoding="utf-8")
        assert _dispositions(repo, bad).returncode == 2


# --- pr-section ---------------------------------------------------------------

_RECORDS = {
    "web": {"status": "skipped", "reason": "same-family", "implementerFamily": "anthropic",
            "reviewerFamily": "anthropic", "findingCount": 0, "droppedCount": 0,
            "declinedCount": 0},
    "adlc-toolkit": {"status": "ran", "implementerFamily": "anthropic",
                     "reviewerFamily": "moonshot", "findingCount": 3, "droppedCount": 1,
                     "declinedCount": 1},
}
_EXPECTED_SECTION = """## Cross-family review

| Repo | Review | Skip reason | Implementer family | Reviewer family | Findings | Dropped | Declined |
|------|--------|-------------|--------------------|-----------------|----------|---------|----------|
| adlc-toolkit | ran | - | anthropic | moonshot | 3 | 1 | 1 |
| web | skipped | same-family | anthropic | anthropic | 0 | 0 | 0 |

A repo whose review did not run had a single-family Phase-5 panel.

### Declined cross-family findings

- Major src/app.py:3 loop bound. Declined: src/app.py:3 bounds the loop
"""


class TestPrSection:
    def _state(self, tmp_path, records, findings=()):
        return _state(tmp_path, list(findings), crossFamilyReview=records)

    def test_names_every_repo_status_reason_and_families(self, tmp_path):
        declined = _finding(disposition="declined", declineReason="src/app.py:3 bounds the loop")
        proc = _run("pr-section", "--state", str(self._state(tmp_path, _RECORDS, [declined, _finding()])))
        assert proc.returncode == 0
        assert proc.stdout == _EXPECTED_SECTION

    def test_byte_stable(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        reordered = dict(reversed(list(_RECORDS.items())))
        out_a = _run("pr-section", "--state", str(self._state(a, _RECORDS))).stdout
        out_b = _run("pr-section", "--state", str(self._state(b, reordered))).stdout
        assert out_a == out_b == _run("pr-section", "--state", str(a / "pipeline-state.json")).stdout
        assert out_a.endswith("### Declined cross-family findings\n\nNone.\n")

    def test_all_ran_says_so(self, tmp_path):
        records = {"r": dict(_RECORDS["adlc-toolkit"])}
        out = CF.pr_section(json.loads(self._state(tmp_path, records).read_text()))
        assert "Every repo's Phase-5 panel had a cross-family reviewer." in out

    def test_absent_record_says_not_recorded(self, tmp_path):
        out = _run("pr-section", "--state", str(_state(tmp_path))).stdout
        assert out == ("## Cross-family review\n\nNo cross-family review was recorded for this "
                       "run, so its Phase-5 panel was single-family.\n")

    def test_invalid_values_are_not_echoed(self, tmp_path):
        records = {"r|x`": {"status": "maybe", "reason": "rm -rf /", "implementerFamily": "mistral",
                            "reviewerFamily": "$(id)", "findingCount": -1, "droppedCount": True,
                            "declinedCount": "3"},
                   "s": {"status": "skipped", "reason": "because", "implementerFamily": "openai",
                         "reviewerFamily": "openai"}}
        out = CF.pr_section(json.loads(self._state(tmp_path, records).read_text()))
        assert "| r_x_ | not recorded | - | unknown | unknown | - | - | - |" in out
        assert "| s | skipped | not recorded | openai | openai | - | - | - |" in out
        for leaked in ("rm -rf", "mistral", "$(id)", "because", "`"):
            assert leaked not in out


def test_a_ran_review_whose_findings_never_reached_verify_is_outstanding(tmp_path):
    """Step D (REQ-722): a review that ran with findings, and no cross-family entry in
    `verify`, is refused; a ran review with none, or a skip, is not (must-not-fire)."""
    checker = CF.DeclineChecker(str(tmp_path))
    ran = {"crossFamilyReview": {"api": {"status": "ran", "findingCount": 2}}}
    assert len(CF.outstanding(ran, checker)) == 1
    assert CF.outstanding({"crossFamilyReview": {"api": {"status": "ran", "findingCount": 0}}}, checker) == []
    assert CF.outstanding({"crossFamilyReview": {"api": {"status": "skipped", "reason": "same-family"}}}, checker) == []
    assert CF.outstanding({}, checker) == []


def test_touched_repos_counts_an_engine_shaped_entry(tmp_path):
    """Step D (REQ-722): the workflow engine writes only `worktree`; such an entry is touched."""
    engine = {"repos": {"a": {"worktree": "/w/a"}, "b": {"worktree": "/w/b"}}}
    assert CF.touched_repos(engine) == 2
    assert CF.touched_repos({"repos": {"a": {"worktree": "/w/a", "touched": False}}}) == 0
    assert CF.touched_repos({"repos": {"a": {}}}) == 0
