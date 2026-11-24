"""A whole scrub of a line, and a whole residue pass over it, are linear in its length (BUG-298).

BUG-297 made the credential patterns linear and could not time ``Scrubber.scrub_line``
or ``Checker.scan_line`` whole, because two things outside the credential step were not:

- the two email patterns. ``residue._EMAIL`` began at every character of a run with no
  ``@`` and read the rest of the run from each; ``detectors.EMAIL_RE`` did the same after
  every underscore, which its lookbehind leaves out and its repeat reads;
- what the scrub and the residue pass did once for each hit. Each asked whether a name
  stands in a table cell, and the scrub whether a person's name starts a sentence, by
  searching the line from its start, and the scrub put the line together again for each
  replacement.

Four times the line cost sixteen times the CPU. These cases pin what fixed it, in the
style of ``test_dataset_credential_linear.py``: a scaling test of both whole functions on
every line family, which compares two line lengths and never an absolute time; and a
table of real-shaped lines, and seeded random lines, on which every changed piece, and
both whole functions, give what they gave before.
"""
import glob
import json
import os
import random
import re
import subprocess
import sys

import pytest

import denylist
import detectors
import residue
import scrub
from dataset_helpers import DATASET_DIR, TOOLKIT
from test_dataset_credential_linear import (  # noqa: E402
    _CHILD_TIMEOUT, _FAMILIES as _CREDENTIAL_FAMILIES, _GROWTH, _MAX_RATIO, _SMALL, _rep)

_ADLC_DIR = os.path.join(TOOLKIT, "tools", "adlc")

#: A DenyList with one of everything: the organization as a repository, a token entry
#: with aliases, a context entry, a one-word and a three-word person, an allow list.
FIXTURE = {
    "organization": "acme-org",
    "organization_repo": {"placeholder": "consumer-repo-9"},
    "public_repos": ["open-tool"],
    "repos": [
        {"name": "secret-api", "placeholder": "consumer-repo-1", "match": "token",
         "aliases": ["Secret API", "Hush Service"]},
        {"name": "web-app", "placeholder": "consumer-repo-2", "match": "token", "aliases": []},
        {"name": "platform", "placeholder": "consumer-repo-3", "match": "repo-context",
         "aliases": []},
    ],
    "people": [{"name": "Dana", "placeholder": "the maintainer"},
               {"name": "Dana Q Smith", "placeholder": "the maintainer"}],
    "email_allowlist": ["noreply@anthropic.com", "git@github.com"],
}


def _fixture(organization_repo=True):
    data = json.loads(json.dumps(FIXTURE))
    if not organization_repo:
        data["organization_repo"] = None
    return denylist.parse(json.dumps(data))


# --- the rules are the patterns they were ---------------------------------------------

#: The two patterns as they stood before BUG-298, spelled out once. They are still the
#: rule; what changed is how they are run.
_SCRUB_RULE = (r"(?<![A-Za-z0-9.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
               r"\.[A-Za-z]{2,}(?![A-Za-z0-9])")
_RESIDUE_RULE = (r"[^\s@<>()\[\]{}\"'`,;|:/=]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                 r"\.[A-Za-z]{2,}(?![A-Za-z0-9])")
_TABLE_CELL_RULE = re.compile(r"\|[ \t]*$")
_SENTENCE_RULE = re.compile(r"(?:^[ \t>*#|-]*|[.!?:][ \t]+)$")


def test_bug_298_the_rules_are_the_patterns_they_were():
    """So every comparison below with ``finditer`` is with the pattern before BUG-298."""
    assert detectors.EMAIL_RE.pattern == _SCRUB_RULE
    assert residue._EMAIL.pattern == _RESIDUE_RULE
    assert detectors.EMAIL_RE.flags == residue._EMAIL.flags == re.compile("x").flags
    # The run patterns are the rules with one thing added: the start of the run.
    scrub_local, residue_local = r"[A-Za-z0-9._%+-]", r"[^\s@<>()\[\]{}\"'`,;|:/=]"
    assert detectors._EMAIL_RUN_RE.pattern == "(?<!%s)%s" % (
        scrub_local, _SCRUB_RULE[len("(?<![A-Za-z0-9.%+-])"):])
    assert residue._EMAIL_RUN.pattern == "(?<!%s)%s" % (residue_local, _RESIDUE_RULE)


def test_bug_298_the_rules_are_tried_at_one_position_never_searched():
    """``EMAIL_RE`` and ``_EMAIL`` are superlinear when searched; the code only matches them."""
    sources = sorted(glob.glob(os.path.join(DATASET_DIR, "*.py")))
    assert len(sources) >= 8
    uses = []
    for path in sources:
        with open(path, encoding="utf-8") as fh:
            uses += re.findall(r"(?<![A-Za-z0-9_.`])(?:detectors\.)?(?:EMAIL_RE|_EMAIL)\.(\w+)\(",
                               fh.read())
    assert uses == ["match", "match"], (
        "BUG-298: an email rule is run with %s; run it with detectors.emails or "
        "residue._emails" % uses)


# --- two line lengths, one ratio ------------------------------------------------------

_EVERYTHING = ("Dana (dana@example.com) fixed platform#12 in /Users/dana/src/secret-api at "
               "0123abc, see https://github.com/acme-org/thing/pull/5 and acme-org/web-app; ")

#: One long line per family, beside BUG-297's. A filler letter is ``x``, not ``a``: a run
#: of ``a`` is a hex run.
_LINE_FAMILIES = {
    # A run that holds no address: every start in it used to read the rest of it.
    "mixed letters": lambda n: _rep("xYz", n),
    "sk_, repeated": lambda n: _rep("sk_", n),
    "a. repeated, then @x": lambda n: _rep("a.", n) + "@x",
    "x_ repeated, then @x.com": lambda n: _rep("x_", n) + "@x.com",
    "letters that are not ASCII": lambda n: _rep("éü", n),
    # Around the @.
    "a@, repeated": lambda n: _rep("a@", n),
    "a@b., repeated": lambda n: _rep("a@b.", n),
    "an @, then dots": lambda n: "x@" + "." * n,
    "an @, then hyphens": lambda n: "x@" + "-" * n,
    "an @, then x-. repeated": lambda n: "x@" + _rep("x-.", n),
    "an @, then labels that end in a digit": lambda n: "x@" + _rep("x1.", n),
    "a long local part, an @, a long domain and no top-level domain": lambda n: (
        "x" * (n // 2) + "@" + "x" * (n // 2)),
    # Many addresses: the search goes on from where each one ended.
    "addresses and blanks": lambda n: _rep("user@example.com ", n),
    "addresses joined by an underscore": lambda n: _rep("user@example.com_", n),
    "addresses joined by a dot": lambda n: _rep("user@example.com.", n),
    "allowed addresses and blanks": lambda n: _rep("git@github.com ", n),
    # Many hits of the other rules: what is done for each must not read the line again.
    "a person and a blank, repeated": lambda n: _rep("Dana ", n),
    "a person at the start of each sentence": lambda n: _rep("Dana. ", n),
    "a full name and a blank, repeated": lambda n: _rep("Dana Q Smith ", n),
    "a context name in prose": lambda n: _rep("platform ", n),
    "a context name in prose between table cells": lambda n: _rep("| see platform now ", n),
    "a context name in table cells": lambda n: _rep("| platform ", n),
    "the organization in prose between table cells": lambda n: _rep("| see acme-org now ", n),
    "a token name and a blank, repeated": lambda n: _rep("secret-api ", n),
    "home paths": lambda n: _rep("/Users/dana/src/other/a.py ", n),
    "names in the organization's namespace": lambda n: _rep("acme-org/thing ", n),
    "links into the organization": lambda n: _rep(
        "https://github.com/acme-org/thing/pull/5 ", n),
    "one hit of every rule, repeated": lambda n: _rep(_EVERYTHING, n),
    "prose": lambda n: _rep("The quick brown fox jumps over the lazy dog, 42 times. ", n),
}
assert not set(_LINE_FAMILIES) & set(_CREDENTIAL_FAMILIES)
_FAMILIES = dict(_CREDENTIAL_FAMILIES, **_LINE_FAMILIES)

_ADDRESS_FAMILIES = ("letters and underscores", "small letters") + tuple(
    list(_LINE_FAMILIES)[:16])
_NAME_FAMILIES = ("a context name in prose", "a context name in prose between table cells",
                  "a context name in table cells",
                  "the organization in prose between table cells")

_SCALING = (
    # Both whole functions, on every family: a repeat, or a read of the line for each
    # hit, added to any step of either later is timed here too.
    [(target, f) for target in ("Scrubber.scrub_line", "Checker.scan_line")
     for f in sorted(_FAMILIES)]
    # The changed pieces alone, where a whole function's other steps would hide them.
    + [("Detectors.email_hits", f) for f in _ADDRESS_FAMILIES]
    + [(target, f) for target in ("Detectors.has_denylist_hit",
                                  "Checker._named, for each context name")
       for f in _NAME_FAMILIES]
    + [("scrub._replace_spans, for each person", "a person and a blank, repeated")])

_CHILD = r"""
import json, sys, time
sys.path[:0] = sys.argv[1:3]
import denylist
import detectors
import residue
import scrub

with open(sys.argv[3], encoding="utf-8") as fh:
    dl = denylist.parse(fh.read())
checker = residue.Checker(dl)
people = detectors.Detectors(dl).people_re
call = {
    "Scrubber.scrub_line": scrub.Scrubber(dl).scrub_line,
    "Checker.scan_line": checker.scan_line,
    "Detectors.email_hits": detectors.Detectors(dl).email_hits,
    "Detectors.has_denylist_hit": detectors.Detectors(dl).has_denylist_hit,
    "Checker._named, for each context name": lambda line: [
        checker._named(line, m) for m in checker.context.finditer(line)],
    "scrub._replace_spans, for each person": lambda line: scrub._replace_spans(
        line, [m.span() for m in people.finditer(line)], "the maintainer"),
}[sys.argv[4]]
out = []
for path in sys.argv[5:]:
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
def test_bug_298_line_is_linear_in_its_length(target, family, tmp_path):
    """Two sizes, one ratio: no absolute time, so a slow machine cannot fail it.

    Each timing runs in a child with a time limit: before BUG-298 the residue pass
    took over twenty seconds on one of these lines.
    """
    fixture = tmp_path / "denylist.json"
    fixture.write_text(json.dumps(FIXTURE), encoding="utf-8")
    paths = []
    for n in (_SMALL, _SMALL * _GROWTH):
        path = tmp_path / ("line-%d.txt" % n)
        path.write_text(_FAMILIES[family](n), encoding="utf-8")
        paths.append(str(path))
    argv = [sys.executable, "-c", _CHILD, DATASET_DIR, _ADLC_DIR, str(fixture), target] + paths
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail("BUG-298: %s did not finish %s at %d and %d characters in %d s" % (
            target, family, _SMALL, _SMALL * _GROWTH, _CHILD_TIMEOUT))
    assert proc.returncode == 0, proc.stderr
    small, big = json.loads(proc.stdout)
    assert big <= max(small, 0.0005) * _MAX_RATIO, (
        "BUG-298: %s on %s took %.4f s at %d characters and %.4f s at %d: x%.1f for x%d "
        "the input" % (target, family, small, _SMALL, big, _SMALL * _GROWTH,
                       big / max(small, 1e-9), _GROWTH))


# --- the same output on real shapes ---------------------------------------------------

_LONG_LOCAL = "first.middle.last+a-tag-that-goes-on-and-on-for-more-than-sixty-four-characters"

#: Real-shaped lines with an address in them, or with what looks like one.
_ADDRESS_SHAPES = [
    # Addresses as they are written.
    "mail dana@example.com today",
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "Signed-off-by: Dana Q Smith <dana.q.smith@example.org>",
    "reply to <first.last+tag@sub.example.co.uk>.",
    "see mailto:help@example.com, or ask.",
    "(owner: ops-team@example.io)",
    "contact='billing@example.com'; cc=\"legal@example.com\"",
    "email=dana@example.com&next=/home",
    "DANA@EXAMPLE.COM and Dana@Example.Com",
    "user_name@example.com",
    "100%sure@example.com",
    "émilie@example.fr",
    "dana@xn--bcher-kva.example",
    _LONG_LOCAL + "@example.com",
    "wide＠example.com and zero​width@example.com",
    # Markdown around an address.
    "_jane@example.com_ and *x@y.example.org*",
    "__bold@example.com__",
    "`code@example.com`",
    "[mail](mailto:link@example.com)",
    "| owner | dana@example.com |",
    "> quoted@example.com wrote:",
    # Addresses that touch: the search goes on where the last one ended.
    "a@b.example.com_c@d.example.org",
    "a@b.example.com__c@d.example.org",
    "a@b.example.com_.c@d.example.org",
    "a@b.example.com%x_c@d.example.org",
    "a@b.example.com.c@d.example.org",
    "a@b.example.com-c@d.example.org",
    "a@b.example.com+c@d.example.org",
    "a@b.example.com,c@d.example.org;e@f.example.net",
    "git@github.com.x@evil.example.org",
    "git@github.com_x@evil.example.org",
    "noreply@anthropic.coméx@evil.example.org",
    "user@example.comuser@example.com",
    "one@example.com two@example.com three@example.com " * 30,
    # A remote, a user in a URL, a host with a user.
    "git@github.com:acme-org/open-tool.git",
    "ssh://git@github.com/acme-org/open-tool",
    "https://dana@example.com/path?q=1",
    "scp dana@build.example.net:/var/log/x .",
    # Not addresses.
    "@types/node and @decorator",
    "react@18.3.1 and pkg@1.2.3",
    "python@3.9 is installed",
    "name@v2.0",
    "user@localhost",
    "user@host and x@y.z",
    "a@b.c0m",
    "foo@bar.com9",
    "foo@bar_baz.com",
    "a @ b.com",
    "at @ and @@ and a@@b.com",
    "x[i]@y",
    "v1.2.3 and 10.0.0.1",
    "the hf_ prefix, sk_live_ and snake_case_names_that_go_on",
    "tools/adlc/tests/test_x.py::test_case",
    "| `partials/intake.sh` | the intake chain |",
    "- [ ] Unit tests pass locally",
    "The quick brown fox jumps over the lazy dog, 42 times. " * 40,
    "",
]

#: Lines for what is asked once for each hit: a table cell, the start of a sentence.
_HIT_SHAPES = [
    "Dana wrote it. Dana agreed, and Dana left.",
    "- Dana wrote it",
    "> * Dana: see below",
    "| Dana | owner |",
    "## Dana Q Smith",
    "note: Dana Q Smith reviewed. DANA approved!  Dana?\tDana",
    "see Dana.Dana and Dana.  Dana",
    "ask dana, then Dana-Q_Smith",
    "the platform team owns it",
    "The platform is down; platform, again.",
    "| platform | the service |",
    "|platform|",
    "| platform",
    "platform |",
    "|  platform\t| x | the platform |",
    "| see platform now | platform. |",
    "clone platform.git",
    "in `platform` and platform/src",
    "platform#12 landed at 0123abc",
    "acme-org owns it",
    "| acme-org | the organization |",
    "| see acme-org now |",
    "acme-org/thing and acme-org/open-tool and acme-org/platform.git",
    "see https://github.com/acme-org/thing/pull/5, then github.com/dana/dotfiles",
    "/Users/dana/src/open-tool/tools/x.py and /home/dana/other/y.py",
    "secret-api, Secret API, secret_api and Hush Service",
    _EVERYTHING * 3,
    "Dana\n",
    "| \nplatform\n|",
    ". \nDana",
    "\nDana",
]


def _spans(matches):
    return [m.span() for m in matches]


def _pieces_same_on(line, hits):
    """Assert every changed piece gives on ``line`` what it replaced; count into ``hits``."""
    want = _spans(detectors.EMAIL_RE.finditer(line))
    assert _spans(detectors.emails(line)) == want, line
    hits["scrub addresses"] += len(want)
    hits["scrub resumed"] += len(want) - len(_spans(detectors._EMAIL_RUN_RE.finditer(line)))
    want = _spans(residue._EMAIL.finditer(line))
    assert _spans(residue._emails(line)) == want, line
    hits["residue addresses"] += len(want)
    hits["residue resumed"] += len(want) - len(_spans(residue._EMAIL_RUN.finditer(line)))
    lead = len(line) - len(line.lstrip(scrub._LINE_LEAD))
    for at in range(len(line) + 1):
        want = bool(_TABLE_CELL_RULE.search(line[:at]))
        assert detectors._after_pipe(line, at) == want, (line, at)
        assert residue._after_pipe(line, at) == want, (line, at)
        assert bool(detectors._CELL_END_RE.match(line, at)) == bool(
            residue._CELL_END.match(line, at)) == bool(re.match(r"[ \t]*\|", line[at:]))
        hits["after a pipe"] += want
        want = bool(_SENTENCE_RULE.search(line[:at]))
        assert scrub._starts_sentence(line, at, lead) == want, (line, at)
        hits["sentence starts"] += want


def _replace_spans_before(line, spans, replacement):
    """``scrub._replace_spans`` as it stood: the line put together again for each span."""
    out = line
    for s, e in sorted(set(spans), reverse=True):
        rep = replacement(out[s:e], s) if callable(replacement) else replacement
        out = out[:s] + rep + out[e:]
    return out


#: Every piece BUG-298 changed, as it stood. Put back together, they are the scrub and
#: the residue pass before the fix.
_BEFORE = (
    (detectors, "emails", lambda line: detectors.EMAIL_RE.finditer(line)),
    (detectors, "_after_pipe", lambda line, end: bool(_TABLE_CELL_RULE.search(line[:end]))),
    (residue, "_emails", lambda line: residue._EMAIL.finditer(line)),
    (residue, "_after_pipe", lambda line, end: bool(_TABLE_CELL_RULE.search(line[:end]))),
    (scrub, "_starts_sentence",
     lambda line, start, lead: bool(_SENTENCE_RULE.search(line[:start]))),
    (scrub, "_replace_spans", _replace_spans_before),
)


def _whole(scrubber, checker, line):
    """Everything the scrub and the residue pass say about ``line``."""
    scrubbed, counts, prose = scrubber.scrub_line(line)
    text, findings, prose_hits = scrubber.scrub_text(line, "f")
    return (scrubbed, counts, prose, text, findings, prose_hits, checker.scan_line(line),
            checker.scan_line(scrubbed), residue.scan(line, checker), residue.scan(text, checker))


def _whole_same_on(lines, monkeypatch):
    """Assert both whole functions give on ``lines`` what they gave before; return the results."""
    pairs = [(scrub.Scrubber(dl), residue.Checker(dl))
             for dl in (_fixture(), _fixture(organization_repo=False))]
    now = [[_whole(s, c, line) for s, c in pairs] for line in lines]
    for module, name, old in _BEFORE:
        monkeypatch.setattr(module, name, old)
    for line, got in zip(lines, now):
        assert got == [_whole(s, c, line) for s, c in pairs], line
    monkeypatch.undo()
    return [got[0] for got in now]


def _new_hits():
    return dict.fromkeys(("scrub addresses", "scrub resumed", "residue addresses",
                          "residue resumed", "after a pipe", "sentence starts"), 0)


def test_bug_298_pieces_unchanged_on_real_shapes():
    hits = _new_hits()
    for line in _ADDRESS_SHAPES + _HIT_SHAPES:
        _pieces_same_on(line, hits)
    assert hits["scrub addresses"] >= 130 and hits["residue addresses"] >= 130, hits
    assert hits["scrub resumed"] >= 4 and hits["residue resumed"] >= 6, hits
    assert hits["after a pipe"] >= 40 and hits["sentence starts"] >= 60, hits
    silent = [line for line in _ADDRESS_SHAPES if not list(residue._emails(line))]
    assert len(silent) >= 18, "the table needs lines with no address in them"


def test_bug_298_scrub_and_residue_unchanged_on_real_shapes(monkeypatch):
    lines = _ADDRESS_SHAPES + _HIT_SHAPES
    results = _whole_same_on(lines, monkeypatch)
    counts = {}
    for scrubbed, per_rule, prose, _, _, _, fired, _, _, _ in results:
        for rule, n in per_rule:
            counts[rule] = counts.get(rule, 0) + n
        counts["prose"] = counts.get("prose", 0) + len(prose)
        counts["capital"] = counts.get("capital", 0) + scrubbed.count("The maintainer")
        counts["residue email"] = counts.get("residue email", 0) + ("email" in fired)
    assert counts["email"] >= 120 and counts["residue email"] >= 30, counts
    assert counts["person"] >= 20 and counts["capital"] >= 8, counts
    assert counts["denylist"] >= 18 and counts["prose"] >= 4, counts


def test_bug_298_scrub_and_residue_unchanged_on_every_family(monkeypatch):
    """Runs are kept short here: the pieces that were replaced are too slow on long ones."""
    lines = [build(n) for _, build in sorted(_FAMILIES.items()) for n in (60, 700)]
    hits = _new_hits()
    for line in lines:
        _pieces_same_on(line, hits)
    _whole_same_on(lines, monkeypatch)


#: Pieces a random line is built from: what the changed pieces read, and what sits near it.
_FRAGMENTS = (
    "a", "b", "x", "Z", "9", "0", ".", "..", "-", "_", "__", "%", "+", "@", " ", "  ", "\t", "/",
    ":", "=", "<", ">", "(", ")", "[", "]", "'", '"', "`", ",", ";", "|", "| ", " |", "!", "?",
    "#", "*", "> ", "- ", "# ", ". ", ": ", "! ", "? ", ".\t", "\n", " \n", "|\n", ". \n", "\r",
    "\x0b", "\x1c", "\x85", " ", "\xa0", "é", "ı", "ſ", "K", "​",
    "‐", "＠", "｜", "com", "org", "io", "c", ".com", ".org", ".c", ".co1", ".c-m",
    "@x", "@x.co", "@b.com", "user@example.com", "git@github.com", "noreply@anthropic.com",
    "GIT@GitHub.com", "a@b.cd", "u_v@w.xy", "first.last+tag@sub.example.co.uk", "_a@b.com_",
    "*x@y.org*", "<a@b.com>", "mailto:a@b.com", "a@b.com.", "a@b.com-", "a@b.com_", "a@b.com%",
    "a@b.com+", "a@b.com!", "a@b.comé", "a@b.com9", "a@b.c0m", "v1.2.3", "@types/node",
    "user@host", "x@y.z", "@@x.yy",
    "Dana", "dana", "Dana Q Smith", "Dana-Q_Smith", "DANA", "Danas", "platform", "Platform",
    "platform.git", "platforms", "secret-api", "secret_api", "Secret API", "Hush Service",
    "web-app", "acme-org", "acme_org", "acme-org/", "acme-org/thing", "acme-org/open-tool",
    "acme-org/platform.git", "open-tool", "https://github.com/acme-org/thing/pull/5",
    "github.com/dana/x", "gist.github.com/dana/abc123", "/Users/dana/src/x.py",
    "/home/dana/open-tool/a.py", "/tmp//home/x", "0123abc", "deadbeef01", "#12", "&#12;",
    "name#50", "consumer-repo-1", "consumer-repo-3", "private-repo", "[link removed]", "<home>",
    "<email>", "<sha>", "[REDACTED]", "the", "see", "wrote it", "and")


def test_bug_298_pieces_unchanged_on_random_lines():
    """Seeded, so it is the same 6,000 lines every run."""
    rng = random.Random(298)
    hits = _new_hits()
    for _ in range(6000):
        _pieces_same_on("".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 24))), hits)
    assert min(hits.values()) >= 200, "the random lines no longer exercise %s" % hits


def test_bug_298_scrub_and_residue_unchanged_on_random_lines(monkeypatch):
    rng = random.Random(2980)
    lines = ["".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 20)))
             for _ in range(4000)]
    results = _whole_same_on(lines, monkeypatch)
    counts = {}
    for scrubbed, per_rule, prose, _, _, _, fired, _, _, _ in results:
        for rule, n in per_rule:
            counts[rule] = counts.get(rule, 0) + n
        counts["prose"] = counts.get("prose", 0) + len(prose)
        counts["capital"] = counts.get("capital", 0) + scrubbed.count("The maintainer")
        for name in fired:
            counts["residue " + name] = counts.get("residue " + name, 0) + 1
    assert min(counts[rule] for rule in scrub.RULES if rule != "credential") >= 50, counts
    assert counts["prose"] >= 10 and counts["capital"] >= 50, counts
    assert counts["residue email"] >= 500 and counts["residue denylist"] >= 500, counts


def test_bug_298_span_replacement_unchanged_on_random_spans():
    rng = random.Random(29800)
    for _ in range(2000):
        line = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(0, 12)))
        cuts = sorted(rng.sample(range(len(line) + 1), min(len(line) + 1, 2 * rng.randint(0, 4))))
        spans = [(s, e) for s, e in zip(cuts[::2], cuts[1::2])]
        rng.shuffle(spans)
        spans += spans[:1]
        for replacement in ("<x>", "", lambda text, start: "[%s@%d]" % (text.upper(), start)):
            assert scrub._replace_spans(line, spans, replacement) == _replace_spans_before(
                line, spans, replacement), (line, spans)


# --- why the start of the run is not enough -------------------------------------------

def test_bug_298_an_address_that_begins_where_the_last_one_ended_is_still_found():
    """A lookbehind alone loses these: the search resumes inside a run (BUG-297's lesson)."""
    scrubber, checker = scrub.Scrubber(_fixture()), residue.Checker(_fixture())

    # The scrub's rule begins again after an underscore. The second address is replaced.
    glued = "mail a@b.example.com_c@d.example.org now"
    assert len(list(detectors._EMAIL_RUN_RE.finditer(glued))) == 1
    out, counts, _ = scrubber.scrub_line(glued)
    assert out == "mail <email>_<email> now" and dict(counts)["email"] == 2
    # After the first underscore of the run, wherever it is, and at no other start.
    far = "a@b.example.com%+.x_c@d.example.org"
    assert scrubber.scrub_line(far)[0] == "<email>%+.x_<email>"
    # The rule never began after a dot, and does not now: the residue pass finds that one.
    after_dot = scrubber.scrub_line("a@b.example.com.c@d.example.org")[0]
    assert after_dot == "<email>.c@d.example.org" and checker.scan_line(after_dot) == ["email"]
    # An allowed address in front does not hide the one glued to it.
    hidden = "git@github.com_x@evil.example.org"
    assert scrubber.scrub_line(hidden)[0] == "git@github.com_<email>"

    # The residue pass's rule begins again at once, at any character it reads.
    for hidden in ("git@github.com.x@evil.example.org", "git@github.com_x@evil.example.org",
                   "noreply@anthropic.com-x@evil.example.org",
                   "git@github.coméx@evil.example.org"):
        assert len(list(residue._EMAIL_RUN.finditer(hidden))) == 1, hidden
        assert [m.group(0) for m in residue._emails(hidden)][0] in FIXTURE["email_allowlist"]
        assert "email" in checker.scan_line(hidden), hidden
    assert "email" not in checker.scan_line("git@github.com. Then noreply@anthropic.com.")


def test_bug_298_sentence_starts_and_table_cells_as_before():
    """What the two per-hit checks decide, on the shapes they were written for."""
    scrubber, checker = scrub.Scrubber(_fixture()), residue.Checker(_fixture())
    line = "Dana wrote it. Dana agreed, and Dana left: Dana!  Dana"
    assert scrubber.scrub_line(line)[0] == (
        "The maintainer wrote it. The maintainer agreed, and the maintainer left: "
        "The maintainer!  The maintainer")
    assert scrubber.scrub_line("> - Dana, and | Dana")[0] == (
        "> - The maintainer, and | the maintainer")
    # A context name alone in a table cell names the repository; in a sentence it does not.
    assert scrubber.scrub_line("| platform | the service |")[0] == (
        "| consumer-repo-3 | the service |")
    assert scrubber.scrub_line("| see platform now | the platform |")[0] == (
        "| see platform now | the platform |")
    assert checker.scan_line("| platform | the service |") == ["denylist"]
    assert checker.scan_line("| see platform now | the service |") == []
