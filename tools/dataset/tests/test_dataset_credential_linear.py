"""The dataset's own credential patterns are linear in the length of a line (BUG-297).

``detectors.JWT_RE``, the key assignment arm of ``detectors.EXTRA_CREDENTIAL`` and
three of ``residue._EXTRA_CREDENTIAL`` (its JWT arm, its key assignment pattern and
its base64 pattern) each had a repeat, or a lookahead, that could start at any
character of a long run, so ``re`` re-read the run from every start: four times
the line cost sixteen times the CPU, and the key assignment arm did not finish
10,000 characters of the repeated word ``token``.

These cases pin what fixed it, in the style of BUG-295's
(``tools/adlc/tests/test_credential_redact.py``): a scaling test for each pattern,
which compares two line lengths and never an absolute time; a table of
real-shaped lines, and seeded random lines, on which the patterns and the ones
they replaced give the same output; and the few shapes on which they differ.
"""
import json
import os
import random
import re
import subprocess
import sys

import pytest

import credential_redact as cr
import detectors
import residue
from dataset_helpers import DATASET_DIR, TOOLKIT

_ADLC_DIR = os.path.join(TOOLKIT, "tools", "adlc")

_C = "[A-Za-z0-9_-]"
_ID = "[A-Za-z_-]"
_B = "[A-Za-z0-9+/]"
_SCRUB_KEY = (r"(?i:secret|passw(?:or)?d|pass|api[-_]?key|access[-_]?key|private[-_]?key"
              r"|token|credential)")
_RESIDUE_KEY = (r"(?:secret|pass|api[-_]?key|access[-_]?key|private[-_]?key|token"
                r"|credential)")

#: For each pattern, the text that makes it linear and the text it replaced. The
#: reference patterns below are today's patterns with the old text put back, so
#: every comparison is of exactly the change and nothing else.
_SWAPS = {
    "JWT_RE": (
        r"(?:eyJ%s{1,255}|(?<!%s)eyJ%s+|%s{255})\.eyJ" % (_C, _C, _C, _C),
        r"eyJ%s+\.eyJ" % _C),
    "EXTRA_CREDENTIAL": (
        r"(?:(?<!%s)(?=%s*%s)%s*|%s{0,64}%s%s{0,64})" % (
            _ID, _ID, _SCRUB_KEY, _ID, _ID, _SCRUB_KEY, _ID),
        r"%s*%s%s*" % (_ID, _SCRUB_KEY, _ID)),
    "residue[0]": (
        r"(?<!%s)(?=%s*?eyJ%s)%s+\.eyJ" % (_C, _C, _C, _C),
        r"eyJ%s+\.eyJ" % _C),
    "residue[3]": (
        r"(?<!%s)(?=%s*%s)%s*" % (_ID, _ID, _RESIDUE_KEY, _ID),
        r"%s%s*" % (_RESIDUE_KEY, _ID)),
    "residue[6]": (
        r"(?<!%s)(?=%s*[A-Z])" % (_B, _B),
        r"(?=%s*[A-Z])" % _B),
}


def _now(name):
    if name.startswith("residue["):
        return residue._EXTRA_CREDENTIAL[int(name[8:-1])]
    return getattr(detectors, name)


def _before(name):
    """The pattern ``name`` as it stood before BUG-297."""
    pattern = _now(name)
    linear, superlinear = _SWAPS[name]
    assert pattern.pattern.count(linear) == 1, (
        "BUG-297: no linear arm in %s (%r); it backtracks without one" % (name, pattern.pattern))
    return re.compile(pattern.pattern.replace(linear, superlinear), pattern.flags)


@pytest.mark.parametrize("name", sorted(_SWAPS))
def test_bug_297_linear_arms_are_in_the_patterns(name):
    assert _now(name).pattern.count(_SWAPS[name][0]) == 1, (
        "BUG-297: no linear arm in %s; it backtracks without one" % name)


def test_bug_297_reference_patterns_are_the_ones_replaced():
    """The old text, spelled out once, so a wrong swap cannot pass for the old pattern."""
    assert _before("JWT_RE").pattern == r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"
    assert _before("residue[0]").pattern == (
        r"hf_[A-Za-z0-9]{30,}|ya29\.[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.eyJ"
        r"|sk_[A-Za-z0-9_-]{20,}")
    assert _before("residue[3]").pattern == (
        r"(?:secret|pass|api[-_]?key|access[-_]?key|private[-_]?key|token|credential)"
        r"[A-Za-z_-]*[\"']?[ \t]*[:=][ \t]*[\"']?[^\s\"'`]{8,}")
    assert _before("residue[6]").pattern == (
        r"(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])"
        r"[A-Za-z0-9+/]{40,}")
    assert (r"|[\"']?[A-Za-z_-]*(?i:secret|passw(?:or)?d|pass|api[-_]?key|access[-_]?key"
            r"|private[-_]?key|token|credential)[A-Za-z_-]*[\"']?[ \t]*[:=][ \t]*[\"']?"
            r"[^\s\"'`]{8,}|") in _before("EXTRA_CREDENTIAL").pattern


# --- two line lengths, one ratio ------------------------------------------------------

def _rep(unit, n):
    return (unit * (n // len(unit) + 1))[:n]


#: One long line per family: what a backtracking engine re-reads from every start.
#: A filler letter is ``x``, not ``a``: a run of ``a`` is a hex run, which the
#: scrub's hex arm takes whole before any other arm can re-read it.
_FAMILIES = {
    "letters and underscores": lambda n: _rep("Ab_", n),
    "small letters": lambda n: "x" * n,
    "the word token, repeated": lambda n: _rep("token", n),
    "secret-, repeated": lambda n: _rep("secret-", n),
    "every keyword, repeated": lambda n: _rep(
        "secretpasswordpasswdpassapi_keyaccess-keyprivate_keytokencredential", n),
    "a run, token, then blanks": lambda n: "x" * (n // 2) + "token" + " " * (n // 2),
    "token= then blanks": lambda n: _rep("token", n // 2) + "=" + " " * (n // 2),
    "a quote, then token repeated": lambda n: "'" + _rep("token", n),
    "a hex run, then token repeated": lambda n: _rep("0" * 40 + "a" + "token" * 30 + " ", n),
    "bearer and a blank, repeated": lambda n: _rep("bearer ", n),
    "eyJ, repeated": lambda n: _rep("eyJ", n),
    "eyJ headers before one long segment": lambda n: (
        _rep("eyJ", n // 2) + ".eyJ" + "x" * (n // 2)),
    "header characters and no dot": lambda n: _rep("a1-B2_", n),
    "long headers, each before .eyJ": lambda n: _rep("h" * 300 + ".eyJ ", n),
    "eyJ at the start of each long run": lambda n: _rep("eyJ" + "h" * 400 + " ", n),
    "hex digits": lambda n: _rep("0123456789abcdef", n),
    "base64 with no digit": lambda n: _rep("aB+/", n),
}

_SCALING = (
    [("JWT_RE", f) for f in (
        "eyJ, repeated", "eyJ headers before one long segment", "header characters and no dot",
        "long headers, each before .eyJ", "eyJ at the start of each long run")]
    + [("EXTRA_CREDENTIAL", f) for f in (
        "letters and underscores", "the word token, repeated", "secret-, repeated",
        "every keyword, repeated", "a run, token, then blanks", "token= then blanks",
        "a quote, then token repeated", "a hex run, then token repeated", "eyJ, repeated")]
    + [("residue[0]", f) for f in (
        "eyJ, repeated", "eyJ headers before one long segment", "header characters and no dot")]
    + [("residue[3]", f) for f in (
        "the word token, repeated", "secret-, repeated", "every keyword, repeated",
        "a run, token, then blanks", "token= then blanks")]
    + [("residue[6]", f) for f in (
        "small letters", "the word token, repeated", "eyJ, repeated", "hex digits",
        "base64 with no digit")]
    # Every credential pattern a line meets, in the order the code applies them: a
    # repeat added to any of them later is timed here too.
    + [(step, f) for step in ("the scrub's credential step", "the residue's credential step")
       for f in ("letters and underscores", "the word token, repeated", "eyJ, repeated",
                 "hex digits", "base64 with no digit", "bearer and a blank, repeated")])

_SMALL, _GROWTH = 10000, 4
#: Four times the input may cost up to this many times the CPU. A linear pattern
#: costs 4, a quadratic one 16, so 8 leaves both a factor of two away.
_MAX_RATIO = 8.0
#: A child that has not finished by now is not linear at any ratio.
_CHILD_TIMEOUT = 45

#: Each target runs the call the export makes: the scrub substitutes, the residue
#: pass searches.
_CHILD = r"""
import json, sys, time
sys.path[:0] = sys.argv[1:3]
import credential_redact as cr
import detectors
import residue


def scrub_step(line):
    for pattern in detectors.CREDENTIAL_PATTERNS:
        line = pattern.subn(cr.REPLACEMENT, line)[0]


def residue_step(line):
    return cr.find(line, cr.ALL_PATTERNS) or any(
        p.search(line) for p in residue._EXTRA_CREDENTIAL)


target = sys.argv[3]
if target == "the scrub's credential step":
    call = scrub_step
elif target == "the residue's credential step":
    call = residue_step
elif target.startswith("residue["):
    call = residue._EXTRA_CREDENTIAL[int(target[8:-1])].search
else:
    call = lambda line: getattr(detectors, target).subn(cr.REPLACEMENT, line)
out = []
for path in sys.argv[4:]:
    with open(path, encoding="utf-8") as fh:
        line = fh.read()
    best = None
    for _ in range(3):
        start = time.process_time()
        call(line)
        took = time.process_time() - start
        best = took if best is None else min(best, took)
    out.append(best)
print(json.dumps(out))
"""


@pytest.mark.parametrize("target,family", _SCALING, ids=["%s: %s" % c for c in _SCALING])
def test_bug_297_pattern_is_linear_in_line_length(target, family, tmp_path):
    """Two sizes, one ratio: no absolute time, so a slow machine cannot fail it.

    Each timing runs in a child with a time limit, because the patterns before
    BUG-297 did not finish some of these lines at all.
    """
    paths = []
    for n in (_SMALL, _SMALL * _GROWTH):
        path = tmp_path / ("line-%d.txt" % n)
        path.write_text(_FAMILIES[family](n), encoding="utf-8")
        paths.append(str(path))
    argv = [sys.executable, "-c", _CHILD, DATASET_DIR, _ADLC_DIR, target] + paths
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail("BUG-297: %s did not finish %s at %d and %d characters in %d s" % (
            target, family, _SMALL, _SMALL * _GROWTH, _CHILD_TIMEOUT))
    assert proc.returncode == 0, proc.stderr
    small, big = json.loads(proc.stdout)
    assert big <= max(small, 0.0005) * _MAX_RATIO, (
        "BUG-297: %s on %s took %.4f s at %d characters and %.4f s at %d: x%.1f for x%d "
        "the input" % (target, family, small, _SMALL, big, _SMALL * _GROWTH,
                       big / max(small, 1e-9), _GROWTH))


# --- the same output on real shapes ---------------------------------------------------

# Credential-shaped values are assembled here, so this file holds no literal a
# secret scanner would stop a push on.
_V = "v4lu3" * 4
_JWT_HEADER = "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
_JWT = _JWT_HEADER + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" * 3 + ".c2lnbmF0dXJl"
_JWT_LONG_PAYLOAD = "eyJ" + "a1B2" * 30 + ".eyJ" + "c3D4" * 400 + ".sig"
#: A header that carries a certificate chain runs to thousands of characters.
_JWT_LONG_HEADER = "eyJ" + "a1B2" * 750 + ".eyJ" + "c3D4" * 40 + ".c2ln"
_HEX = "0123456789abcdef"
_BASE64 = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0NTY3ODkwYWJjZGVm"

#: Real-shaped lines, positive and negative. The patterns and the ones they
#: replaced must agree on every one: what is replaced, where, and how many times
#: for the scrub; whether the line is a hit for the residue pass.
_REAL_SHAPES = [
    # The dataset's own key shapes.
    "hf hf_" + ("aB3" * 12)[:34] + " end",
    "ya ya29." + "aB3_-" * 5 + " end",
    "stripe sk_" + "live_" + "j" * 24,
    "authorization: bearer abcdefghijklmnopqrst+/==",
    "Authorization: BASIC QWxhZGRpbjpvcGVuIHNlc2FtZQ==",
    "curl -u deploy:" + _V + " https://example.com/api",
    "curl -u admin:short https://example.com/api",
    "sha256 " + _HEX * 4,
    "blob " + ("AbCd0123" * 6)[:44] + " end",
    "blob " + "Ab1" * 15,
    _BASE64 + "==",
    # Key-like assignments: `:`, `=`, quotes, any case, kebab and snake names.
    '"api_key": "abcd1234efgh5678ijkl"',
    "api-key: " + _V,
    "X-Api-Key: " + _V,
    "client_secret = '" + _V + "'",
    "db_password=" + _V,
    "DB_PASSWD: " + _V,
    'private_key: "' + _V + '"',
    "aws_secret_access_key = " + _V,
    "export GITHUB_TOKEN=" + _V,
    "access_token=" + _V + "&refresh_token=" + _V,
    "password: correcthorsebattery",
    "'token': '" + _V + "'",
    "credentials: " + _V,
    "passphrase = " + _V,
    "token_budget: 12000000",
    "env: {CLAUDE_CODE_OAUTH_TOKEN: " + _V + "}",
    "secret=<local-path>",
    # A name longer than 64 characters on either side of its keyword: read whole.
    "a_name_of_more_than_sixty_four_characters_in_front_of_the_keyword_which_is_secret = " + _V,
    "fix/bug-297-dataset-credential-patterns-backtrack-superlinearly-on-one-long-line-of-"
    "letters: summary1",
    "token_" + "for_the_reporting_replica_" * 4 + "= " + _V,
    # LESSON-744: the arms match inside ordinary identifiers. Unchanged.
    "compass_heading: northwest",
    "bypass-the-cache: always-on-main",
    "task-ordering-race-in-fixture",
    "slug: token-refresh-loses-the-session",
    "id: secret_rotation_window_too_short",
    # Named, not assigned: prose, short values, shapes the arms leave alone.
    "plain prose about GITHUB_TOKEN being unset",
    "GITHUB_TOKEN: was unset in CI",
    "see TOKEN_BUDGET in the config, and MAX_TOKENS",
    "max_tokens: 4096",
    "token_count = 12",
    "the token = short",
    "tokenizer.encode(text) returns tokens",
    "password reset link sent",
    "password: hunter2",
    '"api_key": "short"',
    "bearer of news",
    "the hf_ prefix and ya29. prefix",
    "- [ ] Unit tests pass locally",
    "tests: 5924 passed, 7 skipped",
    "| `partials/intake.sh` | the intake chain |",
    "commit 0123456789abcdef0123456789abcdef01234567 landed",
    "tools/adlc/tests/test_x.py",
    "a-very-long-lowercase-kebab-slug-that-goes-on-and-on-for-ever-and-ever",
    "url https://user:hunter22@example.com/x",
    "url https://example.com/path?a=b",
    "-----BEGIN RSA PRIVATE KEY-----",
    # JWTs: bare, quoted, assigned, after Bearer, glued to a word, after a terminal
    # colour code, inside a JSON string, with a long payload, with a long header.
    _JWT,
    'jwt: "' + _JWT + '"',
    "id_token=" + _JWT,
    "Authorization: Bearer " + _JWT,
    "prefix-" + _JWT,
    "\x1b[32m" + _JWT + "\x1b[0m",
    '{"msg":"line\\n' + _JWT + '"}',
    _JWT_LONG_PAYLOAD,
    "cookie session=" + _JWT_LONG_PAYLOAD + "; Path=/",
    _JWT_LONG_HEADER,
    'jwt: "' + _JWT_LONG_HEADER + '" and ' + _JWT,
    "eyJhbGciOi only a header prefix",
    _JWT_HEADER + ".payload.signature",
    _JWT_HEADER + ".eyJ no second dot",
    # Long lines of ordinary shape.
    "The quick brown fox jumps over the lazy dog, 42 times. " * 40,
    '{"a":1,"name":"value","list":[1,2,3],"nested":{"k":"v"}}' * 60,
    (_BASE64 + "+/") * 60,
    "two on one line hf_" + "k" * 32 + " and sha " + _HEX * 3,
    "nothing here at all",
    "",
]

_SCRUBBED = ("JWT_RE", "EXTRA_CREDENTIAL")
_SEARCHED = ("residue[0]", "residue[3]", "residue[6]")


def _scrub_step(line, patterns):
    count = 0
    for pattern in patterns:
        line, n = pattern.subn(cr.REPLACEMENT, line)
        count += n
    return line, count


def _same_on(line, hits):
    """Assert old and new agree on ``line``; add what the old patterns found to ``hits``."""
    for name in _SCRUBBED:
        want = _before(name).subn(cr.REPLACEMENT, line)
        assert _now(name).subn(cr.REPLACEMENT, line) == want, (name, line)
        assert [m.span() for m in _now(name).finditer(line)] == [
            m.span() for m in _before(name).finditer(line)], (name, line)
        hits[name] += want[1]
    # The residue pass only asks whether a pattern is found on a line.
    for name in _SEARCHED:
        want = bool(_before(name).search(line))
        assert bool(_now(name).search(line)) == want, (name, line)
        hits[name] += want
    old_step = (_before("JWT_RE"),) + cr.ALL_PATTERNS + (_before("EXTRA_CREDENTIAL"),)
    scrubbed = _scrub_step(line, old_step)
    assert _scrub_step(line, detectors.CREDENTIAL_PATTERNS) == scrubbed, line
    return scrubbed[0]


def test_bug_297_match_set_unchanged_on_real_shapes():
    hits = dict.fromkeys(_SCRUBBED + _SEARCHED, 0)
    for line in _REAL_SHAPES:
        scrubbed = _same_on(line, hits)
        # What the residue pass reads: the scrubbed line, placeholders masked.
        _same_on(residue._PLACEHOLDERS.sub(" ", scrubbed), dict.fromkeys(hits, 0))
    assert hits["JWT_RE"] >= 10 and hits["EXTRA_CREDENTIAL"] >= 30, hits
    assert min(hits[name] for name in _SEARCHED) >= 8, hits


#: Pieces a random line is built from: the patterns' own literals and what sits near them.
_FRAGMENTS = (
    "token", "TOKEN", "_TOKEN", "_API_KEY", "api-key", "secret", "Password", "passwd", "pass",
    "access_key", "private-key", "credential", "=", ":", ": ", " = ", " ", "  ", "\t", "eyJ",
    ".eyJ", ".", "-", "_", "A", "AB_", "ab", "x9", "sk_", "hf_", "ya29.", "ghp_", "AKIA",
    "Bearer ", "bearer ", "basic ", "-u ", "://", "@", "/", "+", "v4lu3v4lu3", "abcdefgh",
    "12345678", "task-", "GITHUB", "export ", '"', "'", "`", "hbGciOiJIUzI1NiJ9",
    "zdWIiOiIxMjM0In0", "QUJD", "a" * 24, _HEX * 3, "deadbeef", "Zz9+/", "==", "[REDACTED]",
    "user:hunter22", ",", "(", ")", _JWT, "eyJhbGci.eyJzdWIi.c2ln",
    # Letters that fold to ASCII ones under IGNORECASE, which residue[3] reads with.
    "ſ", "K", "İ", "ı", "é")


def test_bug_297_match_set_unchanged_on_random_lines_inside_the_bounds():
    """Seeded, so it is the same 6,000 lines every run. With no identifier run over 64
    characters and no header run of 255, the patterns are the ones they replaced."""
    rng = random.Random(297)
    hits = dict.fromkeys(_SCRUBBED + _SEARCHED, 0)
    checked = 0
    while checked < 6000:
        line = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 16)))
        if any(len(run) > 64 for run in re.findall("[A-Za-z_-]+", line)):
            continue
        if any(len(run) >= 255 for run in re.findall("[A-Za-z0-9_-]+", line)):
            continue
        _same_on(line, hits)
        checked += 1
    assert min(hits.values()) >= 100, "the random lines no longer exercise %s" % hits


def test_bug_297_long_names_and_long_headers_are_still_read_whole():
    """Past 64 and 255 characters the anchored arms read what the old ones read."""
    hits = dict.fromkeys(_SCRUBBED + _SEARCHED, 0)
    name = "n" * 100 + "_secret_" + "m" * 100
    for line in (
            name + " = " + _V,
            '"' + name + '": "' + _V + '"',
            "see " + name + ": " + _V + " and " + name + "=" + _V,
            name + " is only named here",
            _JWT_LONG_HEADER,
            "Authorization: Bearer " + _JWT_LONG_HEADER,
            "eyJ" + "a1B2" * 750 + ".payload.signature",
            "blob " + "Ab1" * 400 + " and " + "abc" * 400,
    ):
        _same_on(line, hits)
    assert _now("EXTRA_CREDENTIAL").sub(cr.REPLACEMENT, name + " = " + _V) == cr.REPLACEMENT
    assert _now("JWT_RE").sub(cr.REPLACEMENT, "t " + _JWT_LONG_HEADER + " e") == (
        "t %s e" % cr.REPLACEMENT)
    assert min(hits.values()) >= 2, hits


def test_bug_297_what_the_bounds_change():
    """The shapes on which a pattern and the one it replaced differ, and nothing more."""
    red = cr.REPLACEMENT
    jwt, old_jwt = _now("JWT_RE"), _before("JWT_RE")
    # A header over 255 characters glued to a word: read from 255 characters before its
    # dot, so the head of the header stays. The payload and the signature still go.
    glued = "prefix-eyJ" + "h" * 300 + ".eyJ" + "c3D4" * 10 + ".c2ln"
    assert old_jwt.sub(red, glued) == "prefix-" + red
    assert jwt.sub(red, glued) == "prefix-eyJ" + "h" * 45 + red
    # The exact-count arm does not ask for `eyJ`: 255 header characters before
    # `.eyJ`, a payload and a dot are a hit with none among them...
    assert old_jwt.search("h" * 255 + ".eyJ" + "c3D4" * 10 + ".c2ln") is None
    assert jwt.sub(red, "h" * 255 + ".eyJ" + "c3D4" * 10 + ".c2ln") == red
    # ...so a short JWT glued to the end of a longer run takes 255 characters with it.
    assert old_jwt.sub(red, "h" * 300 + _JWT) == "h" * 300 + red
    assert jwt.sub(red, "h" * 300 + _JWT) == "h" * (300 + len(_JWT_HEADER) - 255) + red

    extra, old_extra = _now("EXTRA_CREDENTIAL"), _before("EXTRA_CREDENTIAL")
    # A key-like assignment that begins where another match ended, inside one run of
    # letters: read with 64 identifier characters on each side of its keyword.
    hex_run = "0" * 40 + "a"
    assert extra.sub(red, hex_run + "_token=" + _V) == red + red
    assert extra.sub(red, hex_run + "n" * 64 + "token" + "m" * 64 + "=" + _V) == red + red
    long_head = hex_run + "n" * 70 + "token=" + _V
    assert old_extra.sub(red, long_head) == red + red
    assert extra.sub(red, long_head) == red + "n" * 6 + red
    long_tail = hex_run + "token" + "m" * 70 + "=" + _V
    assert old_extra.sub(red, long_tail) == red + red
    left = extra.sub(red, long_tail)
    assert left == red + "token" + "m" * 70 + "=" + _V
    # What that leaves is a hit for the residue pass, so the record is excluded.
    assert _now("residue[3]").search(residue._PLACEHOLDERS.sub(" ", left))
