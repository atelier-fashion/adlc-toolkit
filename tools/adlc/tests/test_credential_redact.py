"""credential_redact.py is pinned to its shell sources (REQ-671 architecture ADR-3).

The Python chains are copies of two shell regexes. These tests read the shell
files at run time and fail when a copy drifts, and one case runs the real
``adlc_intake_redact`` so the two regex engines are compared on output, not
only on pattern text (ERE alternation is leftmost-longest, Python's is
leftmost-first).

BUG-295: three arms backtracked quadratically, or worse, on one long line (the
intake chain's ``[A-Z_]+`` assignment arm, the wide chain's assignment arm and
its JWT arm). The cases at the end of this file pin the bounds that fixed it: a
scaling test for each arm, which compares two input sizes and never an absolute
time, and a table of real-shaped lines on which the bounded chains and the
unbounded ones they replaced give the same output.
"""
import ast
import json
import os
import random
import re
import resource
import shutil
import subprocess
import sys

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


# --- BUG-295: the chains are linear in the length of a line ---------------------

_C = "[A-Za-z0-9_-]"
_KEYWORDS = ("([Ss][Ee][Cc][Rr][Ee][Tt]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]"
             "|[Pp][Aa][Ss][Ss][Ww][Dd]|[Aa][Pp][Ii]_[Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn])")

#: The three arms as they stood before BUG-295, and the bounded arms that replaced
#: them. The reference chains below are today's chains with the old arms put back,
#: so the table compares exactly the change and nothing else.
_ARM_SWAPS = (
    (r"[A-Z_]{1,64}_(API_KEY|TOKEN)", r"[A-Z_]+_(API_KEY|TOKEN)"),
    (r"eyJ%s{1,255}\.eyJ%s+\.|%s{255}\.eyJ%s+\." % (_C, _C, _C, _C),
     r"eyJ%s+\.eyJ%s+\." % (_C, _C)),
    (r"[A-Za-z_]{0,64}%s[A-Za-z_]{0,64}" % _KEYWORDS, r"[A-Za-z_]*%s[A-Za-z_]*" % _KEYWORDS),
)


def _unbounded(pattern):
    """``pattern`` with each bounded arm replaced by its pre-BUG-295 form."""
    text, swapped = pattern.pattern, 0
    for bounded, unbounded in _ARM_SWAPS:
        if bounded in text:
            text, swapped = text.replace(bounded, unbounded), swapped + 1
    assert swapped, "BUG-295: no bounded arm in %r; the chain backtracks without one" % text
    return re.compile(text)


def test_bug_295_bounded_arms_are_in_the_chains():
    assert _ARM_SWAPS[0][0] in cr.INTAKE_PATTERN.pattern
    assert _ARM_SWAPS[1][0] in cr.WIDE_PATTERN.pattern
    assert _ARM_SWAPS[2][0] in cr.WIDE_PATTERN.pattern
    for pattern in cr.ALL_PATTERNS:
        for _, unbounded in _ARM_SWAPS:
            assert unbounded not in pattern.pattern, unbounded


def _rep(unit, n):
    return (unit * (n // len(unit) + 1))[:n]


#: One long line per family: what a backtracking engine re-reads from every start.
_FAMILIES = {
    "letters and underscores": lambda n: _rep("Ab_", n),
    "capitals and underscores": lambda n: _rep("AB_", n),
    "the word token, repeated": lambda n: _rep("token", n),
    "_TOKEN, repeated": lambda n: _rep("_TOKEN", n),
    "every keyword, repeated": lambda n: _rep("secretpasswordpasswdapi_keytoken", n),
    "a long run before _API_KEY": lambda n: "A" * n + "_API_KEY",
    "a run, _TOKEN, then blanks": lambda n: "A" * (n // 2) + "_TOKEN" + " " * (n // 2),
    "a run, token, then blanks": lambda n: "a" * (n // 2) + "token" + " " * (n // 2),
    "token= then blanks": lambda n: _rep("token", n // 2) + "=" + " " * (n // 2),
    "eyJ, repeated": lambda n: _rep("eyJ", n),
    "eyJ headers before one long segment": lambda n: _rep("eyJ", 255) + ".eyJ" + "a" * n,
    "header characters and no dot": lambda n: _rep("a1-B2_", n),
    "long headers, each before .eyJ": lambda n: _rep("h" * 300 + ".eyJ ", n),
}

_SCALING = [("INTAKE_PATTERN", f) for f in (
    "capitals and underscores", "_TOKEN, repeated", "a long run before _API_KEY",
    "a run, _TOKEN, then blanks")] + [("WIDE_PATTERN", f) for f in (
        "letters and underscores", "capitals and underscores", "the word token, repeated",
        "_TOKEN, repeated", "every keyword, repeated", "a long run before _API_KEY",
        "a run, token, then blanks", "token= then blanks", "eyJ, repeated",
        "eyJ headers before one long segment", "header characters and no dot",
        "long headers, each before .eyJ")]

_SMALL, _GROWTH = 10000, 4
#: Four times the input may cost up to this many times the CPU. A linear chain
#: costs 4, a quadratic one 16, so 8 leaves both a factor of two away.
_MAX_RATIO = 8.0
#: A child that has not finished by now is not linear at any ratio.
_CHILD_TIMEOUT = 45

_CHILD = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
import credential_redact as cr
pattern = getattr(cr, sys.argv[2])
out = []
for path in sys.argv[3:]:
    with open(path, encoding="utf-8") as fh:
        line = fh.read()
    best = None
    for _ in range(3):
        start = time.process_time()
        pattern.subn(cr.REPLACEMENT, line)
        took = time.process_time() - start
        best = took if best is None else min(best, took)
    out.append(best)
print(json.dumps(out))
"""


@pytest.mark.parametrize("chain,family", _SCALING, ids=["%s: %s" % c for c in _SCALING])
def test_bug_295_chain_is_linear_in_line_length(chain, family, tmp_path):
    """Two sizes, one ratio: no absolute time, so a slow machine cannot fail it.

    Each timing runs in a child with a time limit, because the chains before
    BUG-295 did not finish some of these lines at all.
    """
    paths = []
    for n in (_SMALL, _SMALL * _GROWTH):
        path = tmp_path / ("line-%d.txt" % n)
        path.write_text(_FAMILIES[family](n), encoding="utf-8")
        paths.append(str(path))
    argv = [sys.executable, "-c", _CHILD, os.path.dirname(cr.__file__), chain] + paths
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail("BUG-295: %s did not finish %s at %d and %d characters in %d s" % (
            chain, family, _SMALL, _SMALL * _GROWTH, _CHILD_TIMEOUT))
    assert proc.returncode == 0, proc.stderr
    small, big = json.loads(proc.stdout)
    assert big <= max(small, 0.0005) * _MAX_RATIO, (
        "BUG-295: %s on %s took %.4f s at %d characters and %.4f s at %d: x%.1f for x%d "
        "the input" % (chain, family, small, _SMALL, big, _SMALL * _GROWTH,
                       big / max(small, 1e-9), _GROWTH))


# Credential-shaped values are assembled here, so this file holds no literal a
# secret scanner would stop a push on.
_V = "v4lu3" * 4
_JWT_HEADER = "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
_JWT = _JWT_HEADER + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" * 3 + ".c2lnbmF0dXJl"
_JWT_LONG_PAYLOAD = "eyJ" + "a1B2" * 30 + ".eyJ" + "c3D4" * 400 + ".sig"

#: Real-shaped lines. The bounded chains and the unbounded ones must agree on
#: every one of them: what is replaced, where, and how many times.
_REAL_SHAPES = [
    # Assignments the chains exist for.
    "export GITHUB_TOKEN=" + _V,
    "MOONSHOT_API_KEY: " + _V,
    "MOONSHOT_API_KEY=sk-" + "c" * 24,
    "AWS_CONTAINER_AUTHORIZATION_TOKEN = " + _V,
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN=" + _V + " ACTIONS_RUNTIME_TOKEN=" + _V,
    "  - NEXT_PUBLIC_FIREBASE_API_KEY=" + _V,
    "env: {CLAUDE_CODE_OAUTH_TOKEN: " + _V + "}",
    "fooBAR_TOKEN=" + _V,
    "X_TOKEN_TOKEN=" + _V,
    "A_B_C_D_E_F_G_H_I_J_K_L_M_N_O_P_Q_R_S_T_U_V_W_X_Y_Z_API_KEY=" + _V,
    "TOKEN=" + _V,
    "_TOKEN=" + _V,
    "password = correcthorse",
    "db_password=" + _V,
    "client_secret = '" + _V + "'",
    "Passwd=12345678",
    "API_KEY=abcd1234",
    "my_api_key_for_tests = abcdefgh",
    "spring_datasource_password_for_the_reporting_replica=" + _V,
    "access_token=" + _V + "&refresh_token=" + _V,
    "token_endpoint=https://example.com/oauth/token",
    # Named, not assigned: prose, short values, a colon where the wide chain wants `=`.
    "plain prose about GITHUB_TOKEN being unset",
    "GITHUB_TOKEN: was unset in CI",
    "see TOKEN_BUDGET in the config, and MAX_TOKENS",
    "max_tokens=4096",
    "token_count = 12",
    "the token = short",
    "secret santa = fun",
    "tokenizer.encode(text) returns tokens",
    "password reset link sent",
    "ask_for_api_key_before_running the suite",
    # LESSON-744: kebab and snake identifiers. The sk- arm takes the tail of a
    # kebab word that ends in `sk`; that false positive is unchanged.
    "task-ordering-race-in-fixture",
    "class: task-ordering-race-in-fixture-setup",
    "risk-assessment-of-the-new-pipeline-stage",
    "disk-usage-report-for-the-build-cache",
    "task_ordering_race_in_fixture",
    "task-short",
    "slug: token-refresh-loses-the-session",
    "id: secret_rotation_window_too_short",
    # Key shapes.
    "aws AKIAABCDEFGHIJKLMNOP here",
    "sts ASIA" + "ABCDEFGHIJKLMNOP",
    "token ghp_" + "a" * 36 + " end",
    "pk ghs_" + "e" * 30,
    "pat github_pat_" + "f" * 30,
    "glpat-" + "g" * 24,
    "npm_" + "h" * 36,
    "xox" + "b-" + "1234567890-abcdefgh",
    "xapp-" + "1-A0123456789",
    "AIza" + "i" * 35,
    "key sk-" + "b" * 24,
    "sk_" + "live_" + "j" * 24,
    "short sk-abc is not a key",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PUBLIC KEY-----",
    "Authorization: Bearer abcdefghijklmnopqrstuvwx",
    "url https://user:hunter22@example.com/x",
    "url https://example.com/path?a=b",
    # JWTs: bare, quoted, assigned, after Bearer, with a long payload, glued to a word.
    _JWT,
    'jwt: "' + _JWT + '"',
    "id_token=" + _JWT,
    "Authorization: Bearer " + _JWT,
    "prefix-" + _JWT,
    _JWT_LONG_PAYLOAD,
    "cookie session=" + _JWT_LONG_PAYLOAD + "; Path=/",
    "\x1b[32m" + _JWT + "\x1b[0m",
    '{"msg":"line\\n' + _JWT + '"}',
    "eyJhbGciOi only a header prefix",
    _JWT_HEADER + ".payload.signature",
    # Long lines of ordinary shape.
    "The quick brown fox jumps over the lazy dog, 42 times. " * 40,
    '{"a":1,"name":"value","list":[1,2,3],"nested":{"k":"v"}}' * 60,
    "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0NTY3ODkwYWJjZGVm+/" * 60,
    "two on one line AKIAABCDEFGHIJKLMNOP and ghp_" + "d" * 40,
    "nothing here at all",
    "",
]


@pytest.mark.parametrize("chain", ["INTAKE_PATTERN", "WIDE_PATTERN"])
def test_bug_295_match_set_unchanged_on_real_shapes(chain):
    bounded = getattr(cr, chain)
    unbounded = _unbounded(bounded)
    hits = 0
    for line in _REAL_SHAPES:
        want = unbounded.subn(cr.REPLACEMENT, line)
        assert bounded.subn(cr.REPLACEMENT, line) == want, line
        assert [m.span() for m in bounded.finditer(line)] == [
            m.span() for m in unbounded.finditer(line)], line
        hits += want[1]
    assert hits >= 20, "the table no longer exercises %s" % chain


#: Pieces a random line is built from: the chains' own literals and what sits near them.
_FRAGMENTS = (
    "token", "TOKEN", "_TOKEN", "_API_KEY", "API_KEY", "secret", "Password", "passwd",
    "api_key", "=", ":", " ", "  ", "\t", "eyJ", ".eyJ", ".", "-", "_", "A", "AB_", "ab", "x9",
    "sk-", "ghp_", "AKIA", "Bearer ", "://", "@", "/", "v4lu3v4lu3", "abcdefgh", "12345678",
    "task-", "GITHUB", "export ", '"', "'", "hbGciOiJIUzI1NiJ9", "zdWIiOiIxMjM0In0", "QUJD",
    "a" * 24)


@pytest.mark.parametrize("chain", ["INTAKE_PATTERN", "WIDE_PATTERN"])
def test_bug_295_match_set_unchanged_on_random_lines_inside_the_bounds(chain):
    """Seeded, so it is the same 4,000 lines every run: with no identifier run over 64
    characters and no header run over 255, the bounded chain is the unbounded one."""
    bounded = getattr(cr, chain)
    unbounded = _unbounded(bounded)
    rng = random.Random(295)
    checked = hits = 0
    while checked < 4000:
        line = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 14)))
        if any(len(run) > 64 for run in re.findall("[A-Za-z_]+", line)):
            continue
        if any(len(run) > 255 for run in re.findall("[A-Za-z0-9_-]+", line)):
            continue
        want = unbounded.subn(cr.REPLACEMENT, line)
        assert bounded.subn(cr.REPLACEMENT, line) == want, line
        checked, hits = checked + 1, hits + want[1]
    assert hits >= 100, "the random lines no longer exercise %s" % chain


def test_bug_295_lesson_744_false_positive_class_is_unchanged():
    """A slug beginning ``task-`` still loses its tail to the sk- arm, as before."""
    for chain in (cr.INTAKE_PATTERN, cr.WIDE_PATTERN):
        assert chain.sub(cr.REPLACEMENT, "task-ordering-race-in-fixture") == "ta[REDACTED]"
        assert chain.sub(cr.REPLACEMENT, "task_ordering_race_in_fixture") == (
            "task_ordering_race_in_fixture")
        assert chain.sub(cr.REPLACEMENT, "task-short") == "task-short"


def test_bug_295_what_the_bounds_change():
    """Past the bounds the chains differ from the unbounded ones, in these ways only."""
    # A name longer than the bound keeps its head; the value still goes.
    line = "A" * 70 + "_TOKEN=" + _V
    assert cr.INTAKE_PATTERN.sub(cr.REPLACEMENT, line) == "A" * 6 + "[REDACTED]"
    line = "a" * 70 + "password=" + _V
    assert cr.WIDE_PATTERN.sub(cr.REPLACEMENT, line) == "a" * 6 + "[REDACTED]"
    # 64 identifier characters after the keyword are read; 65 are not.
    assert cr.find("secret" + "x" * 64 + "=" + _V, (cr.WIDE_PATTERN,))
    assert not cr.find("secret" + "x" * 65 + "=" + _V, (cr.WIDE_PATTERN,))
    # A JWT header longer than 255 characters is read by its last 255, wherever the JWT
    # sits: after a blank, a quote, a line break, a word, or a terminal colour code. In
    # a substitution the head of the header stays; the payload goes.
    long_header = "eyJ" + "a1B2" * 100
    jwt = long_header + ".eyJ" + "c3D4" * 20 + ".sig"
    kept = long_header[:len(long_header) - 255]
    assert cr.WIDE_PATTERN.sub(cr.REPLACEMENT, jwt) == kept + "[REDACTED]sig"
    for before in ("", " ", 'jwt: "', "a\n", "x-", "id_", "\x1b[32m", '{"msg":"line\\n'):
        assert cr.WIDE_PATTERN.sub(cr.REPLACEMENT, before + jwt) == (
            before + kept + "[REDACTED]sig"), repr(before)
        assert _unbounded(cr.WIDE_PATTERN).search(before + jwt), repr(before)
    # Every header length is read, on either side of the bound and glued to a word or not.
    for extra in (1, 100, 251, 252, 253, 255, 256, 300, 5000):
        edge = "eyJ" + "h" * extra + ".eyJ" + "p" * 20 + "."
        for before in ("", "x-", "\x1b[0m"):
            assert cr.find(before + edge, (cr.WIDE_PATTERN,)), (extra, before)
    # What the second arm adds: 255 header characters before `.eyJ`, with no `eyJ` in front.
    assert cr.find("h" * 255 + ".eyJ" + "p" * 20 + ".", (cr.WIDE_PATTERN,))
    assert not cr.find("h" * 254 + ".eyJ" + "p" * 20 + ".", (cr.WIDE_PATTERN,))


_NEEDS_SH = pytest.mark.skipif(
    shutil.which("sh") is None or shutil.which("sed") is None or shutil.which("grep") is None,
    reason="needs sh, sed and grep to run the shell chains")


@_NEEDS_SH
def test_bug_295_shell_chains_agree_on_real_shapes(tmp_path):
    """The table again, through the real sed and grep: the three copies agree."""
    lines = [line for line in _REAL_SHAPES if line]
    src = tmp_path / "shapes.txt"
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    grep = subprocess.run(
        ["sh", "-c", 'LC_ALL=C command grep -nE -e "$1" "$2"', "sh", _wide_ere(), str(src)],
        capture_output=True, text=True)
    assert grep.returncode in (0, 1), grep.stderr
    shell_hits = sorted(int(row.split(":", 1)[0]) for row in grep.stdout.splitlines())
    assert shell_hits == [i for i, line in enumerate(lines, 1) if cr.WIDE_PATTERN.search(line)]
    proc = subprocess.run(
        ["sh", "-c", '. "$1" && adlc_intake_redact "$2"', "sh", _INTAKE_SH, str(src)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert src.read_text(encoding="utf-8").split("\n")[:-1] == [
        cr.INTAKE_PATTERN.sub(cr.REPLACEMENT, line) for line in lines]


def _child_cpu(argv):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=_CHILD_TIMEOUT * 2)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    assert proc.returncode in (0, 1), proc.stderr
    return (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)


@_NEEDS_SH
@pytest.mark.parametrize("family", ["capitals and underscores", "the word token, repeated",
                                    "a long run before _API_KEY", "eyJ, repeated"])
def test_bug_295_shell_chains_are_linear_in_line_length(family, tmp_path):
    """The same ratio for sed and grep, by the CPU time of the child.

    A child that costs under 50 ms is mostly process start, so only one that
    costs more is held to the ratio; every child must finish.
    """
    small, growth = 50000, 4
    for label, argv in (
            ("adlc_intake_redact", ["sh", "-c", '. "$1" && adlc_intake_redact "$2"', "sh",
                                    _INTAKE_SH]),
            ("grep -nE _alc_cred", ["sh", "-c", 'LC_ALL=C command grep -nE -e "$1" "$2"',
                                    "sh", _wide_ere()])):
        took = []
        for n in (small, small * growth):
            path = tmp_path / ("line-%d.txt" % n)
            path.write_text(_FAMILIES[family](n) + "\n", encoding="utf-8")
            took.append(_child_cpu(argv + [str(path)]))
        assert took[1] <= max(took[0], 0.05) * _MAX_RATIO, (
            "BUG-295: %s on %s took %.3f s of CPU at %d characters and %.3f s at %d" % (
                label, family, took[0], small, took[1], small * growth))
