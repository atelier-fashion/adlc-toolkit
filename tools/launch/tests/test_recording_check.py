"""The recording checks, over fixture casts built here (REQ-672 BR-4, AC-5, ADR-6, TASK-282).

No fixture cast is a file in the repository, and none holds a real path or name in this
source: a home path is built from parts at run time, and a DenyList hit comes from a
synthetic list passed in, or from the real list read at run time and never printed. A
failure's reason is checked to name its check and event, never the text it matched.

These tests show what the checks find in fixture casts. They do not show that a real
recording passes them: only the maintainer's run of ``record_demo.py`` shows that
(LESSON-899), and ``test_committed_recording_passes_the_checks`` then holds it true.
"""
import json
import os
import subprocess
import sys
import time

import pytest

import fakes
import quickstart_steps as qs
import recording_check as rc

SCRIPT = os.path.join(rc.HERE, "recording_check.py")
HEADER = {"version": 2, "width": 100, "height": 30}
HEAD = json.dumps(HEADER) + "\n"
SYNTHETIC = {
    "organization": "example-org",
    "organization_repo": {"placeholder": "org-placeholder"},
    "public_repos": ["public-thing"],
    "repos": [
        {"name": "private-example-repo", "placeholder": "consumer-repo-1", "match": "token",
         "aliases": ["example alias"]},
        {"name": "context-thing", "placeholder": "consumer-repo-2", "match": "repo-context",
         "aliases": []},
    ],
    "people": [{"name": "Example Person", "placeholder": "a maintainer"}],
    "email_allowlist": ["noreply@example.com"],
}
DL = rc.denylist_mod.parse(json.dumps(SYNTHETIC))
CLEAN = [(1.0, "o", "\x1b[1m$ claude plugin install adlc@adlc-toolkit\x1b[0m\r\n"),
         (2.0, "o", "\x1b[32mSuccessfully installed plugin\x1b[0m\r\n"),
         (2.5, "o", "~sandbox/work/adlc-quickstart: /tmp/adlc-quickstart-e2e.k2j3/work\r\n"),
         (4.0, "o", "PASS lite-req: REQ-001 has lane: lite\r\n")]


def home_path(*rest):
    """A macOS home-directory path, built so that this file holds none."""
    return "/".join(["", "Users", "someone"] + list(rest))


def linux_home(*rest):
    return "/".join(["", "home", "someone"] + list(rest))


def credential():
    """A GitHub token shape, built so that this file holds none."""
    return "gh" + "p_" + "A1b2" * 9


def write_cast(folder, events, name="demo.cast", header=HEADER):
    path = os.path.join(str(folder), name)
    with open(path, "w", encoding="utf-8") as handle:
        for line in [header] + [list(event) for event in events]:
            handle.write(json.dumps(line) + "\n")
    return path


def write_v3(folder, events, name="v3.cast"):
    """``events`` as asciicast v3: ``term`` in the header, each time the interval since the
    event before it, a comment line after the header, and an exit event at the end."""
    header = {"version": 3, "term": {"cols": 100, "rows": 30, "type": "xterm-256color"}}
    lines, previous = [json.dumps(header), "# a comment line"], 0.0
    for time, code, data in events:
        lines.append(json.dumps([round(time - previous, 6), code, data]))
        previous = time
    path = os.path.join(str(folder), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines + [json.dumps([0.25, "x", "0"])]) + "\n")
    return path


def write_gif(folder, size, name="demo.gif"):
    """A GIF of ``size`` bytes, sparse past its signature so a large one costs nothing."""
    path = os.path.join(str(folder), name)
    with open(path, "wb") as handle:
        handle.write(b"GIF89a")
        handle.truncate(size)
    return path


def names(failures):
    return [failure.check for failure in failures]


@pytest.fixture
def run_cli(tmp_path):
    """Runs the CLI as a child on an offline PATH: an empty fake-binary directory, then
    ``/usr/bin:/bin`` without any banned name. The checker starts no binary."""
    (tmp_path / "bin").mkdir()
    path = fakes.offline_path(tmp_path / "bin", tmp_path / "mirror")

    def run(*args):
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=str(tmp_path),
                              env={"PATH": path, "HOME": os.environ["HOME"],
                                   "LANG": "en_US.UTF-8"},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=60)

    return run


#: (check, planted output, the part a reason must never echo, --forbid strings)
CONTENT_CASES = [
    ("home-path", "cat " + home_path("project", "notes.txt"), "someone", ()),
    ("home-path", "cd " + linux_home("project"), "someone", ()),
    ("credential", "export GH_TOKEN=" + credential(), credential(), ()),
    ("credential", "Authorization: Bear" + "er " + "x1Y2" * 6, "x1Y2" * 6, ()),
    ("denylist", "cloning Private_Example_Repo now", "example_repo", ()),
    ("denylist", "see the example-alias notes", "alias", ()),
    ("denylist", "reviewed by example person", "person", ()),
    ("denylist", "git clone example-org/secret-thing", "secret-thing", ()),
    ("denylist", "the example-org repo", "example-org", ()),
    ("forbidden", "pushed to acme-login/adlc-e2e", "acme-login", ("ACME-LOGIN",)),
]


def real_names(dl):
    """Every name the real DenyList lists as private, read at run time, never printed."""
    return [n for repo in dl.repos for n in (repo.name,) + tuple(repo.aliases)] + [
        person.name for person in dl.people]


def test_limits_and_content_checks_on_fixture_casts(tmp_path):
    """AC-5: inside every limit passes; over the length or size limit, or holding a home
    path, a credential, a DenyList name or a --forbid string, fails that check alone."""
    clean = write_cast(tmp_path, CLEAN, "clean.cast")
    assert rc.check(clean, write_gif(tmp_path, 4096), denylist=DL) == []
    assert rc.check(clean) == []  # the repository's own DenyList
    at_limit = write_cast(tmp_path, CLEAN + [(60.0, "o", "done\r\n")], "at-limit.cast")
    assert rc.check(at_limit, write_gif(tmp_path, rc.MAX_BYTES, "at-limit.gif"),
                    denylist=DL) == []

    too_long = write_cast(tmp_path, CLEAN + [(60.25, "o", "done\r\n")], "long.cast")
    assert rc.check(too_long, denylist=DL) == [
        rc.Failure("length", "the cast runs 60.25s, over the 60s limit")]
    big = write_gif(tmp_path, rc.MAX_BYTES + 1, "big.gif")
    assert names(rc.check(clean, big, denylist=DL)) == ["gif-size"]

    for n, (check, text, secret, forbid) in enumerate(CONTENT_CASES):
        cast = write_cast(tmp_path, CLEAN[:2] + [(3.0, "o", text + "\r\n")], "case-%d.cast" % n)
        failures = rc.check(cast, forbid=forbid, denylist=DL)
        assert names(failures) == [check], n
        assert failures[0].reason.endswith("at event 3 (cast line 4)"), n
        echoed = secret.lower() in failures[0].reason.lower()
        assert not echoed, "case %d echoes what it matched" % n

    real = rc.load_denylist()
    listed = real_names(real)
    assert listed, "non-vacuity: the real DenyList lists names"
    for n, name in enumerate(listed):
        for variant in (name, name.upper(), name.replace("-", "_"), name.replace("-", " ")):
            cast = write_cast(tmp_path, [(1.0, "o", "cloning " + variant + " now\r\n")], "r.cast")
            failures = rc.check(cast)
            found = names(failures) == ["denylist"]
            echoed = any(name.lower() in failure.reason.lower() for failure in failures)
            assert found and not echoed, "real DenyList entry %d: not found, or echoed" % n
    org = real.organization
    for text, hit in ((org + "/" + real.public_repos[0], False),
                      (org + "/an-unlisted-repo-e2e", True),
                      ("the " + org + " repository", bool(real.organization_repo))):
        cast = write_cast(tmp_path, [(1.0, "o", text + "\r\n")], "org.cast")
        assert names(rc.check(cast)) == (["denylist"] if hit else []), hit


def test_the_quickstart_steps_pass_every_content_check(tmp_path):
    """The page's own commands, as the demo types them, are not a hit (LESSON-019): the
    real DenyList's public repo is named in step 1."""
    steps = qs.load()
    assert len(steps) >= 8
    events = [(float(n), "o", "$ " + step.text + "\r\n") for n, step in enumerate(steps, 1)]
    assert rc.check(write_cast(tmp_path, events)) == []


@pytest.mark.parametrize("check, pieces", [
    ("home-path", ["see /Us", "ers/someone/notes"]),
    ("home-path", ["see " + home_path()[:6], "\x1b[1m", home_path()[6:] + "/notes"]),
    ("home-path", ["cd /ho", "me/", "someone"]),
    ("denylist", ["cloning private-exa", "mple-repo now"]),
    ("denylist", ["cloning \x1b[1mprivate-example-repo\x1b[0m now"]),
    ("credential", ["token " + credential()[:10], credential()[10:]]),
    ("forbidden", ["by acme", "-lo", "gin"]),
    ("forbidden", ["by acme\x1b[31m-login\x1b[0m"]),
])
def test_content_checks_read_the_output_joined_and_without_escapes(tmp_path, check, pieces):
    """AC: text split across events, or broken up by colour codes, is still found."""
    events = [(1.0 + n, "o", piece) for n, piece in enumerate(pieces)]
    failures = rc.check(write_cast(tmp_path, CLEAN + [(t + 4, c, d) for t, c, d in events]),
                        forbid=["acme-login"], denylist=DL)
    assert names(failures) == [check]
    assert "at event 5 (cast line 6)" in failures[0].reason


def test_content_checks_read_the_header_and_the_other_events(tmp_path):
    header = dict(HEADER, command="python3 " + home_path("quickstart_e2e.py"))
    failures = rc.check(write_cast(tmp_path, CLEAN, header=header), denylist=DL)
    assert failures == [rc.Failure("home-path", "a home-directory path in the cast header")]
    events = CLEAN + [(5.0, "i", "private-example-repo\r")]
    failures = rc.check(write_cast(tmp_path, events, "input.cast"), denylist=DL)
    assert failures == [rc.Failure("denylist", "a DenyList name at event 5 (cast line 6)")]


def test_a_path_under_a_url_or_the_temp_directory_is_not_a_home_path(tmp_path):
    """A ``/Users/`` or ``/home/`` in a token that holds a URL's scheme and host before it,
    or right after ``scheme:/`` (the host itself), is part of a URL."""
    for n, text in enumerate([
            "https://example.com" + linux_home() + " /private/var/folders/x/T/a",
            "https://example.com" + home_path("x"),
            "GET https://api.github.com" + home_path().lower() + "/repos",
            "https://api.github.com" + "/".join(["", "users", "x"]),
            "https://host.example" + home_path("y"), "<https://h.example:8443" + linux_home() + ">",
            "http:/" + home_path("x"), "http:/" + linux_home("x")]):
        events = CLEAN + [(5.0, "o", text + "\r\n")]
        assert rc.check(write_cast(tmp_path, events, "url-%d.cast" % n), denylist=DL) == [], n


@pytest.mark.parametrize("text", [
    "/System/Volumes/Data" + home_path("x"), "/var" + linux_home(), "~/.." + home_path(),
    "(" + home_path("x"), "<" + linux_home("x"), "see https://example.com " + home_path("x"),
    'url="https://example.com" dir=' + home_path("x"), "https://example.com/a\r\n" + home_path()])
def test_a_home_path_nested_in_a_path_or_beside_a_url_is_found(tmp_path, text):
    """Only a URL's own path is skipped: a home path under another directory, or in a token
    of its own after a URL, is found."""
    failures = rc.check(write_cast(tmp_path, CLEAN + [(5.0, "o", text + "\r\n")]), denylist=DL)
    assert names(failures) == ["home-path"]


@pytest.mark.parametrize("path", [home_path("x"), linux_home("x")])
@pytest.mark.parametrize("before", ["", "cd ", 'p="', "p='", "HOME=", "PATH=/bin:", "ok\r\n",
                                    "file://"])
def test_a_home_path_after_a_space_quote_equals_or_line_start_is_found(tmp_path, path, before):
    failures = rc.check(write_cast(tmp_path, [(1.0, "o", before + path + "\r\n")]), denylist=DL)
    assert names(failures) == ["home-path"]


@pytest.mark.parametrize("hide", ["x\b", "x\x1b[1D", "xy\x1b[2D", "x\x1b[8G", "x\x1b[8`",
                                  "\u200b", "\u2060", "\ufeff", "\u2061", "\U000e0041",
                                  "\u034f", "\u00ad", "\ufe00", "\ufe0f"])
def test_a_home_path_a_terminal_draws_is_found(tmp_path, hide):
    """Backspace, a cursor move back or to a column, or an invisible character inside the
    word: the raw and escape-stripped texts hold no home path, but the terminal draws one."""
    text = "see " + home_path()[:3] + hide + home_path()[3:] + "/notes\r\n"
    failures = rc.check(write_cast(tmp_path, CLEAN + [(5.0, "o", text)]), denylist=DL)
    assert failures == [rc.Failure("home-path", "a home-directory path at event 5 (cast line 6), "
                                                "as a terminal draws it")]


@pytest.mark.parametrize("text", ["deployed \u2764\ufe0f \u2705\ufe0e done",
                                  "\U0001F44D\U0001F3FD thanks", home_path()[:6] + "\t/srv",
                                  "name\tsize\x1b[20Gok"])
def test_an_emoji_with_a_variation_selector_or_a_tab_is_not_a_hit(tmp_path, text):
    events = CLEAN + [(5.0, "o", text + "\r\n")]
    assert rc.check(write_cast(tmp_path, events), denylist=DL) == []


@pytest.mark.parametrize("move", ["\x1b[999999999C", "\x1b[999999999G", "\x1b[" + "9" * 40 + "C"])
def test_a_hostile_width_or_cursor_move_is_capped(tmp_path, move):
    """A header width of 10**9 and a cursor move as far: the line drawn is at most
    MAX_WIDTH wide, and the check returns at once."""
    rendered, origins = rc.render(move + "x", 10 ** 9)
    assert len(rendered) <= rc.MAX_WIDTH and rendered.endswith("x")
    assert len(origins) == len(rendered)
    started, header = time.time(), dict(HEADER, width=10 ** 9)
    cast = write_cast(tmp_path, [(1.0, "o", move + "x\r\n")], header=header)
    assert rc.check(cast, denylist=DL) == []
    assert time.time() - started < 10


def test_an_output_too_large_to_render_fails_oversize(tmp_path):
    """Past MAX_RENDER characters the renderer stops, and the check fails rather than
    passing; an output a quarter that size passes."""
    line = "lorem ipsum dolor sit amet " * 3 + "\r\n"
    small = line * (rc.MAX_RENDER // 4 // len(line))
    assert rc.check(write_cast(tmp_path, [(1.0, "o", small)], "small.cast"), denylist=DL) == []
    big = line * (5 * 1024 * 1024 // len(line) + 1)
    failures = rc.check(write_cast(tmp_path, [(1.0, "o", big)], "big.cast"), denylist=DL)
    assert failures == [rc.Failure("oversize", "the recording's output is too large to check")]


def test_the_credential_windows_cover_every_short_span():
    """Each span of at most CREDENTIAL_OVERLAP characters in a line is whole in a window."""
    size, overlap = rc.CREDENTIAL_WINDOW, rc.CREDENTIAL_OVERLAP
    for length in (0, 1, size, size + 1, 3 * size - 2 * overlap, 3 * size + 7):
        windows = list(rc._windows("ab\n" + "x" * length))
        assert windows[0] == (0, "ab")
        spans = [(start, start + len(piece)) for start, piece in windows[1:]]
        assert spans[-1][1] == 3 + length
        for at in range(3, 3 + max(length - overlap, 0) + 1):
            assert any(lo <= at and at + min(overlap, length) <= hi for lo, hi in spans), at


def test_a_credential_in_a_very_long_line_is_found_in_bounded_time(tmp_path):
    """A credential pattern is quadratic on a long run of letters: the check runs it over
    windows, so a 200,000-character line is read in bounded time, and a credential across
    a window's end is found whole in the next window."""
    token = "gh" + "p_" + "AbCd" * 9  # letters only: the filler's run goes on through it
    step = rc.CREDENTIAL_WINDOW - rc.CREDENTIAL_OVERLAP
    at = 2 * step + rc.CREDENTIAL_WINDOW - len(token) // 2  # across the third window's end
    line = "a" * at + token
    line += "a" * (200000 - len(line))
    started = time.time()
    failures = rc.check(write_cast(tmp_path, [(1.0, "o", line + "\n")]), denylist=DL)
    assert failures == [rc.Failure("credential", "a credential shape at event 1 (cast line 2)")]
    assert rc._first_credential(line) == at
    for n, clean in enumerate(["a" * 40000, "lorem ipsum " * 16667]):
        cast = write_cast(tmp_path, [(1.0, "o", clean + "\n")], "clean-%d.cast" % n)
        assert rc.check(cast, denylist=DL) == [], n
    assert time.time() - started < 10  # generous: the machine may be loaded


def test_a_progress_line_redrawn_with_carriage_returns_passes(tmp_path):
    progress = "".join("\rReceiving objects: %3d%% (%d/4)\x1b[K" % (25 * n, n)
                       for n in range(5)) + ", done.\r\n"
    assert rc.render(progress)[0] == "Receiving objects: 100% (4/4), done.\n"
    assert rc.check(write_cast(tmp_path, CLEAN + [(5.0, "o", progress)]), denylist=DL) == []


def test_forbidden_is_a_whole_word_in_any_case(tmp_path):
    """Not preceded or followed by a letter, digit or ``-``, the characters of a GitHub
    login: a short login inside a longer word is not a hit."""
    cases = [("Hello, Ada", True), ("pushed to ADA/repo", True), ("by \x1b[1mada\x1b[0m.", True),
             ("by a\x1b[1mda", True), ("canada Adams", False), ("ada-lovelace x-ada ada9", False)]
    for n, (text, hit) in enumerate(cases):
        cast = write_cast(tmp_path, CLEAN + [(5.0, "o", text + "\r\n")], "w-%d.cast" % n)
        found = names(rc.check(cast, forbid=["ada"], denylist=DL))
        assert found == (["forbidden"] if hit else []), n
    pattern = rc.word_pattern("fake-login-123")
    assert [bool(pattern.search(t)) for t in ("/FAKE-LOGIN-123/", "xfake-login-123",
                                               "fake-login-1234", "fake-login-123-e2e")] == [
        True, False, False, False]


def test_report_counts_and_the_empty_cast(tmp_path, run_cli):
    """AC: the report gives the duration, the event count and the GIF's size; a cast with
    no output event fails."""
    clean = write_cast(tmp_path, CLEAN)
    done = run_cli(clean, "--gif", write_gif(tmp_path, 4096))
    assert (done.returncode, done.stdout, done.stderr) == (
        0, "recording-check: duration=4.00s events=4 gif=4096\nPASS\n", "")
    done = run_cli(clean)
    assert done.stdout.splitlines()[0] == "recording-check: duration=4.00s events=4 gif=none"
    quiet = write_cast(tmp_path, [(0.5, "r", "100x30"), (1.0, "i", "y"), (1.5, "o", "")], "q.cast")
    done = run_cli(quiet)
    assert done.returncode == 1
    assert done.stdout.splitlines() == ["recording-check: duration=1.50s events=3 gif=none",
                                        "FAIL empty: the cast has no output events"]
    done = run_cli(write_cast(tmp_path, [], "header-only.cast"))
    assert done.stdout.splitlines() == ["recording-check: duration=0.00s events=0 gif=none",
                                        "FAIL empty: the cast has no output events"]


def test_cli_names_each_failed_check_and_never_what_it_matched(tmp_path, run_cli):
    denylist = tmp_path / "denylist.json"
    denylist.write_text(json.dumps(SYNTHETIC), encoding="utf-8")
    events = CLEAN + [(5.0, "o", "acme-login cloned private-example-repo into "
                       + home_path("x") + "\r\n"), (70.0, "o", "done\r\n")]
    done = run_cli(write_cast(tmp_path, events), "--gif",
                   write_gif(tmp_path, rc.MAX_BYTES + 1), "--forbid", "nothing-here",
                   "acme-login", "--denylist", str(denylist))
    assert done.returncode == 1
    assert done.stdout.splitlines() == [
        "recording-check: duration=70.00s events=6 gif=%d" % (rc.MAX_BYTES + 1),
        "FAIL length: the cast runs 70.00s, over the 60s limit",
        "FAIL home-path: a home-directory path at event 5 (cast line 6)",
        "FAIL denylist: a DenyList name at event 5 (cast line 6)",
        "FAIL forbidden: a forbidden string at event 5 (cast line 6)",
        "FAIL gif-size: the GIF is %d bytes, over the %d-byte limit"
        % (rc.MAX_BYTES + 1, rc.MAX_BYTES)]
    for secret in ("acme-login", "private-example-repo", "someone"):
        assert secret not in done.stdout + done.stderr


def test_cli_exits_2_on_an_unreadable_input_or_a_refused_argument(tmp_path, run_cli):
    clean = write_cast(tmp_path, CLEAN)
    bad = tmp_path / "bad-denylist.json"
    bad.write_text("{not json", encoding="utf-8")
    for args, said in (([str(tmp_path / "missing.cast")], "cannot read an input"),
                       ([clean, "--gif", str(tmp_path / "missing.gif")], "cannot read an input"),
                       ([clean, "--denylist", str(bad)], "cannot read an input"),
                       ([clean, "--forbid", " "], "refused: a --forbid string is empty")):
        done = run_cli(*args)
        assert done.returncode == 2, args
        assert done.stdout == "" and said in done.stderr, args
    assert run_cli().returncode == 2  # no CAST: argparse's usage error


HEADER_LINE_CASES = [
    ("[]\n", 1, "the header is not a JSON object"),
    ('{"version": 1, "width": 80, "height": 24}\n', 1, "version is not 2 or 3"),
    ('{"version": 3, "width": 80, "height": 24}\n', 1, "the header's term is not a JSON object"),
    ('{"version": 3, "term": {"cols": 0, "rows": 24}}\n', 1, "term.cols is not a positive integer"),
    ('{"version": 3, "term": {"cols": 80, "rows": 24}}\n[1.0, "y", "x"]\n', 2,
     "code is not one of o, i, m, r, x"),
    ('{"version": 3, "term": {"cols": 80, "rows": 24}}\n[-0.5, "o", "x"]\n', 2,
     "time is not a non-negative number"),
    (HEAD + "# a v2 cast has no comment line\n", 2, "not JSON"),
    ('{"version": 2, "width": 0, "height": 24}\n', 1, "width is not a positive integer"),
    ('{"version": 2, "width": 80}\n', 1, "height is not a positive integer"),
    ('{"version": 2, "width": 80, "height": 24, "duration": "1"}\n', 1, "duration"),
    ("", 1, "the file is empty"),
    (HEAD + '[1.0, "o"]\n', 2, "not a [time, code, data] list"),
    (HEAD + '{"time": 1.0}\n', 2, "not a [time, code, data] list"),
    (HEAD + '["1.0", "o", "x"]\n', 2, "time is not a non-negative number"),
    (HEAD + '[true, "o", "x"]\n', 2, "time is not a non-negative number"),
    (HEAD + '[-1, "o", "x"]\n', 2, "time is not a non-negative number"),
    (HEAD + '[NaN, "o", "x"]\n', 2, "not JSON"),
    (HEAD + '[1.0, "x", "x"]\n', 2, "code is not one of o, i, m, r"),
    (HEAD + '[1.0, 1, "x"]\n', 2, "code is not one of o, i, m, r"),
    (HEAD + '[1.0, "o", 5]\n', 2, "data is not a string"),
    (HEAD + '[1.0, "o", "a"] trailing\n', 2, "not JSON"),
    (HEAD + '[2.0, "o", "a"]\n[1.0, "o", "b"]\n', 3, "earlier than the event before it"),
    (HEAD + '[1.0, "o", "a"]\n\n[2.0, "o", "b"]\n', 3, "a blank line"),
]


@pytest.mark.parametrize("text, line, said", HEADER_LINE_CASES)
def test_a_malformed_line_fails_naming_it(tmp_path, text, line, said):
    path = tmp_path / "bad.cast"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(rc.CastError) as caught:
        rc.load_cast(str(path))
    assert caught.value.line == line and said in caught.value.reason
    failures = rc.check(str(path), denylist=DL)
    assert names(failures) == ["malformed"]
    assert failures[0].reason.startswith("line %d: " % line)


def test_a_malformed_cast_is_reported_by_the_cli(tmp_path, run_cli):
    path = tmp_path / "bad.cast"
    path.write_bytes(HEAD.encode() + b'[1.0, "o", "ok"]\n[2.0, "o", "\xff"]\n')
    done = run_cli(str(path))
    assert done.returncode == 1
    assert done.stdout.splitlines() == ["recording-check: duration=unknown events=unknown gif=none",
                                        "FAIL malformed: line 3: not UTF-8"]


def test_load_cast_reads_events_and_duration_from_the_last_event(tmp_path):
    header = dict(HEADER, duration=1.0, env={"TERM": "xterm-256color"})
    path = write_cast(tmp_path, CLEAN, header=header)
    loaded_header, events = rc.load_cast(path)
    assert loaded_header == header
    assert events == [(float(t), c, d) for t, c, d in CLEAN]
    assert rc.duration(events) == 4.0 and rc.duration([]) == 0.0


def test_a_v3_cast_loads_as_the_same_v2_cast(tmp_path):
    """asciicast v3 (asciinema 3's default): intervals summed into absolute times, ``term``
    as ``width``/``height``/``env.TERM``, the comment skipped and the exit event dropped.
    A failure names the v3 file's own line."""
    events = CLEAN + [(5.123457, "i", "y"), (7.0, "r", "90x30"), (9.25, "o", "bye\r\n")]
    v2_header, v2_events = rc.load_cast(write_cast(tmp_path, events))
    v3_header, v3_events = rc.load_cast(write_v3(tmp_path, events))
    assert v3_events == v2_events and rc.duration(v3_events) == rc.duration(v2_events) == 9.25
    assert (v3_header["version"], v3_header["width"], v3_header["height"]) == (2, 100, 30)
    assert v3_header["env"] == {"TERM": "xterm-256color"}
    assert rc.check(write_v3(tmp_path, events), denylist=DL) == []
    bad = write_v3(tmp_path, events + [(9.5, "o", home_path("x") + "\r\n")], "bad.cast")
    assert rc.check(bad, denylist=DL) == [
        rc.Failure("home-path", "a home-directory path at event 8 (cast line 10)")]


@pytest.mark.parametrize("present", [(), ("demo.cast",), ("demo.gif",), ("demo.cast", "demo.gif")])
def test_the_committed_pair_rule(tmp_path, present):
    """Both files are checked, exactly one fails, and neither passes with a notice."""
    docs = tmp_path / "docs"
    docs.mkdir()
    if "demo.cast" in present:
        write_cast(docs, CLEAN)
    if "demo.gif" in present:
        write_gif(docs, 4096)
    failures, notice = rc.check_committed(str(tmp_path), denylist=DL)
    if not present:
        assert failures == [] and "neither docs/demo.cast nor docs/demo.gif" in notice
    elif len(present) == 1:
        assert names(failures) == ["pair"] and notice is None
        assert failures[0].reason.startswith("docs/%s exists without" % present[0])
    else:
        assert failures == [] and notice is None
        write_cast(docs, CLEAN + [(5.0, "o", home_path("x") + "\r\n")])
        assert names(rc.check_committed(str(tmp_path), denylist=DL)[0]) == ["home-path"]


def test_committed_recording_passes_the_checks():
    """Runs the checks over the repository's docs/demo.cast and docs/demo.gif when both
    exist, fails when only one does, and is skipped, which pytest reports, when neither does."""
    failures, notice = rc.check_committed()
    if notice and not failures:
        pytest.skip("no committed recording: docs/demo.cast and docs/demo.gif are absent")
    assert failures == []
