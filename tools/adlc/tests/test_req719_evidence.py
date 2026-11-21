"""REQ-719 BR-26 and BR-29: the two real runs are on record, and the suite keeps out of the
real home (AC-20, AC-23).

The evidence for BR-26 is the runs themselves, made by the operator's request against a real
`codex exec` and a real GitHub PR, and their record in
`.adlc/research/harness-probes/codex-exec-manual.md`. No test can stand for a real run
(LESSON-891): the first test here only checks that the note carries both records and says
what they do not show. The second checks what every other test in this directory relies on:
`HOME`, the machine-state home and the exec engine's state home all resolve inside a
throwaway directory, so a run of the suite leaves nothing under the operator's home.
"""

import os
import pwd
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import adlc_home  # noqa: E402
import exec_ledger as el  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
NOTE = os.path.join(TOOLKIT, ".adlc", "research", "harness-probes", "codex-exec-manual.md")


def _section(text, heading):
    """The text of the `## ` section whose heading starts with ``heading``."""
    start = text.index("\n## " + heading)
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def _rows(section):
    """The table rows of ``section`` as lists of cells, header and rule rows left out."""
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("|")]
    return [r for r in rows if not set("".join(r)) <= set("-: ")][1:]


def test_req719_the_note_records_both_real_runs():
    """AC-20: the note holds a launch that passed Phase 7 against the mock forge on a real
    Codex with no `answer`, and what `adlc_forge_pr_checks` printed and returned against a real
    GitHub PR. It also says which launch did not get there, and what was not measured."""
    with open(NOTE, encoding="utf-8") as fh:
        text = fh.read()
    launches = _section(text, "Two launches for REQ-719")
    assert re.search(r"\(20[0-9]{2}-[01][0-9]-[0-3][0-9]\)", launches.splitlines()[1])
    assert re.search(r"`codex-cli [0-9]+\.[0-9]+\.[0-9]+`", launches)
    assert re.search(r"REQ-719 branch at `[0-9a-f]{7,40}`", launches)
    assert "Nothing was approved." in launches
    rows = _rows(launches)
    passed = [r for r in rows if r[1].startswith("`awaiting_approval`")]
    assert len(passed) == 1, rows
    assert "No `answer` was given." in passed[0][3]
    assert "`adlc_forge_pr_checks`" in passed[0][3] and "diff fence" in passed[0][3]
    # Every launch is recorded, the one that stopped early too (as BUG-287's were).
    assert len(rows) >= 2 and any(r[1].startswith("`blocked`") for r in rows)
    assert "read `checks=none` each time" in launches

    github = _section(text, "`adlc_forge_pr_checks` against GitHub")
    assert re.search(r"`gh` [0-9]+\.[0-9]+\.[0-9]+", github)
    calls = {r[0].split("`")[1]: r for r in _rows(github)}
    real = [r for call, r in calls.items() if r[1] == "`checks=none`"]
    assert real and all(r[2] == "0" for r in real)
    missing = [r for r in calls.values() if "`error_class=pr-not-found`" in r[1]]
    assert len(missing) == 1 and missing[0][2] == "1"
    # What the read did not show is said, not left out.
    assert "was not read\nagainst GitHub" in github or "was not read against GitHub" in github


def test_req719_the_suite_runs_under_a_throwaway_home(tmp_path):
    """AC-23: under this directory's conftest, `HOME` is a throwaway directory that is neither
    the operator's home nor inside it, and nothing the runner's shell exported points the
    machine-state home or the exec engine's state home anywhere else. The benign path: a test
    that sets one of them itself is free to (the exec sandbox does), which is why the conftest
    unsets them and does not pin them."""
    real = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    home = os.path.realpath(os.environ["HOME"])
    assert home != real and not home.startswith(real + os.sep)
    assert os.path.isdir(home) and os.path.realpath(os.path.expanduser("~")) == home
    for name in ("ADLC_HOME", "ADLC_CONFIG", "ADLC_REPOS_ROOT", "XDG_STATE_HOME"):
        assert name not in os.environ, name
    for resolved in (adlc_home.adlc_home(), el.state_home(dict(os.environ))):
        path = os.path.realpath(resolved)
        assert path == home or path.startswith(home + os.sep), resolved
        assert not path.startswith(real + os.sep)
