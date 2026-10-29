"""credential_redact.py is pinned to its shell sources (REQ-671 architecture ADR-3).

The Python chains are copies of two shell regexes. These tests read the shell
files at run time and fail when a copy drifts, and one case runs the real
``adlc_intake_redact`` so the two regex engines are compared on output, not
only on pattern text (ERE alternation is leftmost-longest, Python's is
leftmost-first).
"""
import ast
import os
import re
import shutil
import subprocess

import pytest

import credential_redact as cr

_TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_INTAKE_SH = os.path.join(_TOOLKIT, "partials", "intake.sh")
_LESSON_CHECK_SH = os.path.join(_TOOLKIT, "partials", "lesson-check.sh")


def _ere_to_python(ere):
    """Translate the one POSIX class the chains use; refuse any other."""
    out = ere.replace("[[:space:]]", r"\s").replace("[:space:]", r"\s")
    leftover = re.findall(r"\[:[a-z]+:\]", out)
    assert not leftover, "untranslated POSIX class %s: extend the test, do not guess" % leftover
    return out


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _intake_ere():
    text = _read(_INTAKE_SH)
    found = re.findall(r"sed -i\.bak -E 's/(\(.*\))/\[REDACTED\]/g' \"\$_ai_f\"", text)
    assert len(found) == 1, "%s: expected one adlc_intake_redact sed line, found %d" % (
        _INTAKE_SH, len(found))
    return found[0]


def _wide_ere():
    text = _read(_LESSON_CHECK_SH)
    found = re.findall(r"^\s*_alc_cred='([^']*)'$", text, re.M)
    assert len(found) == 1, "%s: expected one _alc_cred assignment, found %d" % (
        _LESSON_CHECK_SH, len(found))
    return found[0]


def test_intake_pattern_matches_shell_chain():
    assert cr.INTAKE_PATTERN.pattern == _ere_to_python(_intake_ere())


def test_wide_pattern_matches_shell_chain():
    assert cr.WIDE_PATTERN.pattern == _ere_to_python(_wide_ere())


# Positive lines, negative lines, and lines where two arms overlap.
_CORPUS = [
    "aws AKIAABCDEFGHIJKLMNOP here",
    "token ghp_" + "a" * 36 + " end",
    "key sk-" + "b" * 24,
    "Authorization: Bearer abcdefghijklmnopqrstuvwx",
    "MOONSHOT_API_KEY=sk-" + "c" * 24,
    "export GITHUB_TOKEN: abc123",
    "two on one line AKIAABCDEFGHIJKLMNOP and ghp_" + "d" * 40,
    "plain prose about GITHUB_TOKEN being unset",
    "short sk-abc is not a key",
    "AKIA lowercase akiaabcdefghijklmnop is not matched",
    "nothing here at all",
    "",
]


@pytest.mark.skipif(shutil.which("sh") is None or shutil.which("sed") is None,
                    reason="needs sh and sed to run the shell chain")
def test_differential_against_adlc_intake_redact(tmp_path):
    src = tmp_path / "corpus.txt"
    src.write_text("\n".join(_CORPUS) + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["sh", "-c", '. "$1" && adlc_intake_redact "$2"', "sh", _INTAKE_SH, str(src)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    shell_out = src.read_text(encoding="utf-8")
    py_out, count = cr.redact("\n".join(_CORPUS) + "\n", (cr.INTAKE_PATTERN,))
    assert py_out == shell_out
    assert count == 8


def test_redact_counts_and_replaces():
    text, n = cr.redact("a AKIAABCDEFGHIJKLMNOP b", cr.ALL_PATTERNS)
    assert text == "a %s b" % cr.REPLACEMENT
    assert n == 1


def test_wide_chain_leaves_prose_naming_a_variable():
    line = "GITHUB_TOKEN: was unset in CI"
    assert cr.redact(line, (cr.WIDE_PATTERN,)) == (line, 0)
    assert not cr.find(line, (cr.WIDE_PATTERN,))


def test_wide_chain_catches_what_intake_misses():
    for line in ("pk ghs_" + "e" * 30, "url https://user:hunter22@example.com/x",
                 "-----BEGIN RSA PRIVATE KEY-----", "password = correcthorse"):
        assert not cr.find(line, (cr.INTAKE_PATTERN,)), line
        assert cr.find(line, (cr.WIDE_PATTERN,)), line


def test_module_is_stdlib_only():
    tree = ast.parse(_read(cr.__file__))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names == {"re"}
