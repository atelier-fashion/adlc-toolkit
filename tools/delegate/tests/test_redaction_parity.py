"""The cross-family partial's redaction chain is the intake chain (REQ-722 ADR-6, ASSUME-009).

``partials/cross-family-review.sh`` carries the five-arm credential chain inline,
because a shared partial would change the REQ-417 pre-pass, which REQ-722 BR-11
keeps as it is. This test reads the chain out of the partial at run time and pins
it to ``tools/adlc/credential_redact.py`` ``INTAKE_PATTERN``, the Python copy of
``partials/intake.sh``'s linear form (BUG-295): first by pattern text, then by
running the partial's own ``sed`` line and the Python pattern over one corpus and
comparing the output, because ERE alternation is leftmost-longest and Python's is
leftmost-first.
"""
import importlib.util
import os
import re
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
PARTIAL = os.path.join(REPO_ROOT, "partials", "cross-family-review.sh")

# The partial's one redaction line, in the shape it must keep: `sed -i.bak -E`
# over "$CORPUS", replacing every match with [REDACTED].
_SED_LINE_RE = re.compile(r"sed -i\.bak -E 's/(\(.*\))/\[REDACTED\]/g' \"\$CORPUS\"")


def _credential_redact():
    path = os.path.join(REPO_ROOT, "tools", "adlc", "credential_redact.py")
    spec = importlib.util.spec_from_file_location("xfam_credential_redact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _partial_ere():
    with open(PARTIAL, encoding="utf-8") as handle:
        found = _SED_LINE_RE.findall(handle.read())
    assert len(found) == 1, "%s: expected one redaction sed line over $CORPUS, found %d" % (
        PARTIAL, len(found))
    return found[0]


def _ere_to_python(ere):
    """Translate the one POSIX class the chain uses; refuse any other."""
    out = ere.replace("[[:space:]]", r"\s").replace("[:space:]", r"\s")
    leftover = re.findall(r"\[:[a-z]+:\]", out)
    assert not leftover, "untranslated POSIX class %s: extend the test, do not guess" % leftover
    return out


def _key(n, fill="a1b2"):
    """A credential-shaped value assembled at run time, so this file holds none."""
    return (fill * n)[:n]


# Positive lines for every arm, negatives, two arms on one line, the bounded name
# arm past its 64-character bound, and LESSON-744's kebab identifier, which the
# chain over-matches in both engines alike.
CORPUS = [
    "client = connect('sk-" + _key(24) + "')",
    "aws AKIA" + "ABCDEFGHIJKLMNOP" + " here",
    "token ghp_" + _key(36) + " end",
    "Authorization: Bearer " + _key(24),
    "MOONSHOT_API_KEY=sk-" + _key(24),
    "export GITHUB_TOKEN: abc123",
    "+GITHUB_TOKEN=abc123def456",
    "two on one line AKIA" + "ABCDEFGHIJKLMNOP" + " and ghp_" + _key(40),
    "  - NEXT_PUBLIC_FIREBASE_API_KEY=" + _key(30),
    "A" * 80 + "_API_KEY=" + _key(12),
    "plain prose about GITHUB_TOKEN being unset",
    "short sk-abc is not a key",
    "class task-ordering-race-in-fixture stays",
    "nothing here at all",
    "",
]


def test_partial_chain_matches_intake_pattern():
    cr = _credential_redact()
    assert _ere_to_python(_partial_ere()) == cr.INTAKE_PATTERN.pattern
    # The linear form (BUG-295): the name before _API_KEY or _TOKEN is bounded.
    assert "[A-Z_]{1,64}_(API_KEY|TOKEN)" in _partial_ere()


@pytest.mark.skipif(shutil.which("sed") is None, reason="needs sed to run the shell chain")
def test_partial_chain_output_matches_intake_pattern(tmp_path):
    cr = _credential_redact()
    text = "\n".join(CORPUS) + "\n"
    corpus = tmp_path / "corpus"
    corpus.write_text(text, encoding="utf-8")
    proc = subprocess.run(["sed", "-i.bak", "-E", "s/%s/[REDACTED]/g" % _partial_ere(), str(corpus)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    shell_out = corpus.read_text(encoding="utf-8")
    py_out, count = cr.redact(text, (cr.INTAKE_PATTERN,))
    assert shell_out == py_out
    assert count == 12
    assert "sk-" + _key(24) not in shell_out and "abc123def456" not in shell_out
    # LESSON-744: the sk- arm takes the tail of `task-...`. Both engines agree, and
    # it is why constrained fields (paths, classes) are validated, never redacted.
    assert "class ta[REDACTED] stays" in shell_out
