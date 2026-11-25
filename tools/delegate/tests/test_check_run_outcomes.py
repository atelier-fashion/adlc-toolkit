"""Fixture tests for tools/delegate/check-run-outcomes.sh (REQ-648 BR-7, BR-8).

Every case points $ADLC_RUN_OUTCOMES_LOG into tmp_path so the real log under
~/Library/Logs is never read. Lines are built by run_outcome.build_record where
the content matters, so a fixture cannot drift from what the emitter writes, and
by hand where the case is about a malformed or legacy line.
"""

import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DELEGATE_DIR = REPO_ROOT / "tools" / "delegate"
CHECK = str(DELEGATE_DIR / "check-run-outcomes.sh")

sys.path.insert(0, str(DELEGATE_DIR))
import run_outcome as RO  # noqa: E402

NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def line(req, classes=(), terminal="merged", version="5.4.0", when=None, severity="Major",
         loops=0, attempts=None, reason="", engine="legacy"):
    state = {"req": req, "harness": {"version": version, "sha": "c013262"},
             "verify": {"findings": [{"severity": severity, "class": c, "title": c} for c in classes],
                        "loops": loops},
             "validateAttempts": attempts or {}}
    rec = RO.build_record(state, terminal, engine, reason=reason, now=when or NOW)
    rec["req"] = req  # the AC-5 fixture names REQ-1..REQ-3, which the emitter would not
    return RO.encode(rec)


def run(tmp_path, lines, *args, shell=None):
    log = tmp_path / "run-outcomes.log"
    if lines is not None:
        log.write_text("".join(entry + "\n" for entry in lines), encoding="utf-8")
    env = dict(os.environ, ADLC_RUN_OUTCOMES_LOG=str(log))
    cmd = [shell, CHECK, *args] if shell else [CHECK, *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def rows(out):
    return [r.split("\t") for r in out.stdout.splitlines()]


# --- BR-7 / AC-5 / AC-6: Recurrence -------------------------------------------------

def test_recurrence_lesson_tier_and_no_record(tmp_path):
    log = [
        line("REQ-1", ["LESSON-390", "unique-one"]),
        line("REQ-2", ["LESSON-390", "unique-two"]),
    ]
    out = run(tmp_path, log, "--reqs", "REQ-1,REQ-2,REQ-3", "--recurrence")
    assert out.returncode == 0, out.stderr
    got = out.stdout.splitlines()
    assert got[0] == "LESSON-390\t2\t3\tlesson"
    assert got[1:3] == ["unique-one\t1\t3\treviewer", "unique-two\t1\t3\treviewer"]
    assert got[3] == "REQ-3\tno-record"
    assert len(got) == 4


def test_recurrence_reviewer_and_title_slug_tiers(tmp_path):
    legacy = {"req": "REQ-3", "verify": {"findings": [{"severity": "Minor", "title": "Unquoted variable in fence"}]}}
    log = [
        line("REQ-1", ["cross-fence-shell-state"]),
        line("REQ-2", ["cross-fence-shell-state"]),
        RO.encode({**RO.build_record(legacy, "merged", "solo", now=NOW), "req": "REQ-3"}),
    ]
    out = run(tmp_path, log, "--recurrence", "--reqs", "REQ-1,REQ-2,REQ-3")
    got = out.stdout.splitlines()
    assert got[0] == "cross-fence-shell-state\t2\t3\treviewer"
    assert got[1] == "title-slug:unquoted-variable-in-fence\t1\t3\ttitle-slug"
    assert len(got) == 2, "every listed REQ has a line, so no no-record rows"


def test_latest_line_per_req_wins(tmp_path):
    """A resumed run's earlier blocked line is not counted once it merges (BR-2)."""
    log = [
        line("REQ-1", ["early-only-class"], terminal="blocked", reason="merge-conflict"),
        line("REQ-2", ["shared-class"]),
        line("REQ-1", ["shared-class"]),
    ]
    out = run(tmp_path, log, "--recurrence", "--reqs", "REQ-1,REQ-2")
    assert out.stdout.splitlines() == ["shared-class\t2\t2\treviewer"]
    # the summary counts the same REQ once, as merged
    summary = rows(run(tmp_path, log))
    assert summary[1][:6] == ["5.4.0", "2", "2", "0", "0", "0"]


def test_recurrence_counts_a_class_once_per_req(tmp_path):
    log = [line("REQ-1", ["dup-class", "dup-class"])]
    assert run(tmp_path, log, "--recurrence", "--reqs", "REQ-1").stdout.splitlines() == ["dup-class\t1\t1\treviewer"]


def test_recurrence_missing_log_is_all_no_record(tmp_path):
    out = run(tmp_path, None, "--recurrence", "--reqs", "REQ-101,REQ-102,REQ-101")
    assert out.returncode == 0
    assert out.stdout.splitlines() == ["REQ-101\tno-record", "REQ-102\tno-record"]


def test_recurrence_usage(tmp_path):
    assert run(tmp_path, [], "--recurrence").returncode == 2
    assert run(tmp_path, [], "--recurrence", "--reqs", "REQ-1,rm -rf").returncode == 2
    assert run(tmp_path, [], "--bogus").returncode == 2


# --- BR-8 / AC-9: the window summary ---------------------------------------------------

def test_summary_exit_contract(tmp_path):
    # log absent: rc 0, nothing at all (the /analyze silent skip)
    absent = run(tmp_path, None)
    assert (absent.returncode, absent.stdout, absent.stderr) == (0, "", "")
    # present, nothing inside the window
    old = NOW - datetime.timedelta(days=30)
    stale = run(tmp_path, [line("REQ-101", when=old)], "--window", "7d")
    assert (stale.returncode, stale.stdout) == (0, "no runs in 7d window\n")
    empty = run(tmp_path, [])
    assert (empty.returncode, empty.stdout) == (0, "no runs in 7d window\n")
    # corrupt: non-empty lines, none parses
    corrupt = run(tmp_path, ["not json", '{"skill":"wrapup","step":"x"}'])
    assert corrupt.returncode == 1 and corrupt.stdout == ""
    assert corrupt.stderr.startswith("check-run-outcomes:")
    # benign: one good line among garbage is data, not corruption
    mixed = run(tmp_path, ["garbage", line("REQ-101")])
    assert mixed.returncode == 0 and rows(mixed)[1][0] == "5.4.0"
    # a wider window brings the old line back
    assert rows(run(tmp_path, [line("REQ-101", when=old)], "--window", "60d"))[1][1] == "1"


def test_summary_groups_by_toolkit_version(tmp_path):
    log = [
        line("REQ-101", ["LESSON-390", "a-class"], version="5.3.1", attempts={"phase1": 3}, loops=1),
        line("REQ-102", ["LESSON-390"], version="5.3.1", terminal="blocked", reason="merge-conflict"),
        line("REQ-103", [], version="5.4.0", terminal="pr-ready", severity="Nit"),
    ]
    out = run(tmp_path, log, "--window", "7d")
    assert out.returncode == 0, out.stderr
    table = rows(out)
    assert table[0] == OLD_HEADER + ["rejected"]
    v531, v540 = table[1], table[2]
    assert v531[:6] == ["5.3.1", "2", "1", "0", "1", "0"]
    assert v531[6:8] == ["1.00", "0.50"]
    assert v531[8:12] == ["0", "3", "0", "0"]
    assert v531[12] == "LESSON-390=2,a-class=1"
    assert v540[:6] == ["5.4.0", "1", "0", "1", "0", "0"] and v540[12] == "-"
    assert v531[13] == v540[13] == "0"


# REQ-648's header. REQ-719 adds `rejected` after it, so none of these moves.
OLD_HEADER = ["toolkit_version", "runs", "merged", "pr_ready", "blocked", "failed",
              "mean_validate_retries", "verify_loop_rate", "critical", "major", "minor",
              "nit", "top_classes"]


def _legacy_failed_other(req, version):
    """A line exactly as REQ-648 wrote it, by hand: how a run rejected before
    REQ-719 is recorded (`failed` / `other`). No line is ever rewritten."""
    ts = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('{"timestamp":"' + ts + '","skill":"proceed","step":"run-outcome","req":"' + req + '",'
            '"repo":"adlc-toolkit","engine":"exec","toolkit_version":"' + version + '",'
            '"toolkit_sha":"c013262","terminal":"failed","blocked_reason":"other",'
            '"validate_retries":"0","verify_loops":"0","findings_critical":"0",'
            '"findings_major":"0","findings_minor":"0","findings_nit":"0",'
            '"finding_classes":"","lessons_cited":"","lessons_written":"","elapsed_s":"-"}')


def _req719_logs():
    """Lines from before REQ-719, then the same log with the new values added."""
    before = [
        line("REQ-101", ["a-class"], version="5.4.0", attempts={"phase1": 2}, loops=1),
        line("REQ-102", ["a-class"], version="5.4.0", terminal="blocked", reason="merge-conflict"),
        _legacy_failed_other("REQ-103", "5.4.0"),
        line("REQ-104", [], version="5.5.0", terminal="pr-ready"),
    ]
    new = [
        line("REQ-105", ["b-class"], version="5.5.0", terminal="rejected", engine="exec",
             severity="Minor", attempts={"phase3": 3}, loops=1),
        line("REQ-106", [], version="5.5.0", terminal="failed", engine="exec", reason="aborted"),
        # blocked, answered, relaunched, then declined at the gate: the latest line wins
        line("REQ-107", ["c-class"], version="5.5.0", terminal="blocked", engine="exec",
             reason="merge-conflict"),
        line("REQ-107", ["c-class"], version="5.5.0", terminal="rejected", engine="exec"),
    ]
    return before, new


def test_req719_rejected_has_its_own_last_column(tmp_path):
    before, new = _req719_logs()

    # must-not-fire: a log with only older lines parses as before, with 0 in the new column
    old = run(tmp_path, before)
    assert old.returncode == 0, old.stderr
    old_table = rows(old)
    assert old_table[0] == OLD_HEADER + ["rejected"]
    assert old_table[1] == ["5.4.0", "3", "1", "0", "1", "1", "0.33", "0.33", "0", "2", "0", "0",
                            "a-class=2", "0"]
    assert old_table[2] == ["5.5.0", "1", "0", "1", "0", "0", "0.00", "0.00", "0", "0", "0", "0",
                            "-", "0"]

    # the old and new values together: every old column in its old position
    mixed = run(tmp_path, before + new)
    assert mixed.returncode == 0, mixed.stderr
    table = rows(mixed)
    assert table[0][:13] == OLD_HEADER and table[0][13:] == ["rejected"]
    assert all(len(r) == 14 for r in table)
    assert table[1] == old_table[1], "a version with no new line is unchanged, column for column"
    assert table[2] == ["5.5.0", "4", "0", "1", "0", "1", "0.50", "0.25", "0", "1", "1", "0",
                        "b-class=1,c-class=1", "2"]

    # a rejected line adds to `runs` and to no terminal count: not merged, not a failure
    one = run(tmp_path, before + new[:1])
    v550_before, v550_one = old_table[2], rows(one)[2]
    assert int(v550_one[1]) == int(v550_before[1]) + 1
    assert v550_one[13] == "1"
    assert v550_one[2:6] == v550_before[2:6]
    # `aborted` is a failed run like any other: it counts in `failed`, never in `rejected`
    aborted = rows(run(tmp_path, before + new[1:2]))[2]
    assert (aborted[1], aborted[5], aborted[13]) == ("2", "1", "0")


@pytest.mark.parametrize("shell", ["sh", "dash", "bash", "zsh"])
def test_req719_rejected_column_under_each_shell(tmp_path, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    before, new = _req719_logs()
    table = rows(run(tmp_path, before + new, shell=shell))
    assert table[0] == OLD_HEADER + ["rejected"], shell
    assert [r[13] for r in table[1:]] == ["0", "2"], shell


def test_window_must_be_digits(tmp_path):
    assert run(tmp_path, [], "--window", "abc").returncode == 2
    assert run(tmp_path, [], "--window", "7").returncode == 0


@pytest.mark.parametrize("shell", ["sh", "dash", "bash", "zsh"])
def test_runs_under_each_shell(tmp_path, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    log = [line("REQ-1", ["LESSON-390"]), line("REQ-2", ["LESSON-390"])]
    out = run(tmp_path, log, "--recurrence", "--reqs", "REQ-1,REQ-2,REQ-3", shell=shell)
    assert out.stdout.splitlines() == ["LESSON-390\t2\t3\tlesson", "REQ-3\tno-record"], out.stderr
    assert rows(run(tmp_path, log, shell=shell))[1][1] == "2"


def test_script_is_posix_shaped():
    code = "\n".join(l for l in Path(CHECK).read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("#"))
    for banned in ("[[", "local ", "mktemp", " jq", "set -e"):
        assert banned not in code, banned


# --- REQ-722 BR-13 / AC-13 / AC-15: the cross-family block ---------------------------

def _pre_req722(req, version, terminal="merged", reason="", engine="legacy", classes="",
                retries="0", loops="0", counts=("0", "0", "0", "0")):
    """A line exactly as REQ-648 and REQ-719 wrote it, by hand, key for key: no
    `crossFamily` object, because no line before REQ-722 has one."""
    ts = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('{"timestamp":"' + ts + '","skill":"proceed","step":"run-outcome","req":"' + req + '",'
            '"repo":"adlc-toolkit","engine":"' + engine + '","toolkit_version":"' + version + '",'
            '"toolkit_sha":"c013262","terminal":"' + terminal + '","blocked_reason":"' + reason + '",'
            '"validate_retries":"' + retries + '","verify_loops":"' + loops + '",'
            '"findings_critical":"' + counts[0] + '","findings_major":"' + counts[1] + '",'
            '"findings_minor":"' + counts[2] + '","findings_nit":"' + counts[3] + '",'
            '"finding_classes":"' + classes + '","lessons_cited":"LESSON-012",'
            '"lessons_written":"","elapsed_s":"3600"}')


#: A pre-REQ-722 log: REQ-648 and REQ-719 lines, a resumed REQ whose latest line wins, and
#: one line that does not parse.
PRE_REQ722_LOG = [
    _pre_req722("REQ-201", "5.4.0", classes="LESSON-390,a-class", retries="1", loops="1",
                counts=("0", "1", "0", "1")),
    _pre_req722("REQ-202", "5.4.0", terminal="blocked", reason="merge-conflict", classes="a-class",
                counts=("1", "0", "0", "0")),
    "not a run-outcome line",
    _pre_req722("REQ-203", "5.5.0", terminal="blocked", reason="validation-exhausted"),
    _pre_req722("REQ-203", "5.5.0", terminal="merged", classes="b-class", counts=("0", "0", "2", "0")),
    _pre_req722("REQ-204", "5.5.0", terminal="rejected", engine="exec", classes="b-class",
                retries="2", loops="1", counts=("0", "1", "1", "0")),
    _pre_req722("REQ-205", "5.5.0", terminal="failed", reason="other", engine="exec"),
]

#: check-run-outcomes.sh's output for PRE_REQ722_LOG, captured from the script as it stood
#: before REQ-722 (commit 2e99a38). The script must print it byte for byte still (AC-15).
PRE_REQ722_SUMMARY = (
    "toolkit_version\truns\tmerged\tpr_ready\tblocked\tfailed\tmean_validate_retries\t"
    "verify_loop_rate\tcritical\tmajor\tminor\tnit\ttop_classes\trejected\n"
    "5.4.0\t2\t1\t0\t1\t0\t0.50\t0.50\t1\t1\t0\t1\ta-class=2,LESSON-390=1\t0\n"
    "5.5.0\t3\t1\t0\t0\t1\t0.67\t0.33\t0\t1\t3\t0\tb-class=2\t1\n"
)
PRE_REQ722_REQS = "REQ-201,REQ-202,REQ-203,REQ-204,REQ-205,REQ-206"
PRE_REQ722_RECURRENCE = (
    "a-class\t2\t6\treviewer\nb-class\t2\t6\treviewer\nLESSON-390\t1\t6\tlesson\n"
    "REQ-206\tno-record\n"
)


def test_pre_req_log_output_unchanged(tmp_path):
    """AC-15 / BR-13: a log with no `crossFamily` object prints exactly what the
    script printed before REQ-722, in both modes and under every shell."""
    out = run(tmp_path, PRE_REQ722_LOG)
    assert (out.returncode, out.stdout, out.stderr) == (0, PRE_REQ722_SUMMARY, "")
    rec = run(tmp_path, PRE_REQ722_LOG, "--recurrence", "--reqs", PRE_REQ722_REQS)
    assert (rec.returncode, rec.stdout, rec.stderr) == (0, PRE_REQ722_RECURRENCE, "")
    # the emitter's own line for a pre-REQ-722 state carries no object either
    emitted = line("REQ-207", ["a-class"], version="5.5.0")
    assert "crossFamily" not in emitted
    for shell in ("sh", "dash", "bash", "zsh"):
        if shutil.which(shell) is not None:
            assert run(tmp_path, PRE_REQ722_LOG, shell=shell).stdout == PRE_REQ722_SUMMARY, shell


def _xfam_line(req, reviews, findings=(), version="5.6.0", when=None):
    """A line built by the emitter from a REQ-722 state."""
    state = {"req": req, "harness": {"version": version, "sha": "c013262"},
             "crossFamilyReview": reviews, "verify": {"findings": list(findings), "loops": 0}}
    rec = RO.build_record(state, "merged", "solo", now=when or NOW)
    rec["req"] = req
    return RO.encode(rec)


CROSS_HEADER = "runs\treviews\tran\tskipped\tfindings\tcross_only\tfixed\tdeclined\tskip_reasons"


def test_cross_family_block_reports_counts(tmp_path):
    """AC-13: with REQ-722 lines in the window, a `Cross-family:` block follows the
    unchanged 14-column table: the reviews ran and skipped, the cross-family
    findings, those the panel did not raise, the fixes and declines, and the skip
    reasons, counted from each REQ's latest line only."""
    xf = lambda f, **kw: dict({"severity": "Major", "file": f, "title": f, "class": "a-b"}, **kw)
    new = [
        # an earlier line for REQ-301 that the later one replaces
        _xfam_line("REQ-301", {"api": {"status": "skipped", "reason": "api-error"}}),
        _xfam_line("REQ-301", {"api": {"status": "ran"}, "web": {"status": "skipped",
                                                                  "reason": "same-family"}},
                   [xf("a", source=["cross-family"], fixed=True),
                    xf("b", source=["cross-family", "panel"], disposition="declined",
                       declineReason="b:1"),
                    xf("c", source=["panel"], fixed=True)]),
        _xfam_line("REQ-302", {"api": {"status": "skipped", "reason": "subagent-mode"}}),
        _xfam_line("REQ-303", {"api": {"status": "ran"}},
                   [xf("d", source=["cross-family"], disposition="fixed"),
                    xf("e", source=["cross-family"], disposition="deferred")]),
        _xfam_line("REQ-304", {"api": {"status": "skipped", "reason": "same-family"}}),
        # outside the window: not counted
        _xfam_line("REQ-305", {"api": {"status": "skipped", "reason": "no-binary"}},
                   when=NOW - datetime.timedelta(days=30)),
    ]
    out = run(tmp_path, PRE_REQ722_LOG + new)
    assert out.returncode == 0, out.stderr
    table, block = out.stdout.split("\n\n")
    assert out.stdout.startswith(PRE_REQ722_SUMMARY), "the table's old rows are unchanged"
    assert all(len(r.split("\t")) == 14 for r in table.splitlines())
    assert table.splitlines()[-1].split("\t")[:3] == ["5.6.0", "4", "4"]
    assert block.splitlines() == [
        "Cross-family:",
        CROSS_HEADER,
        "4\t5\t2\t3\t4\t3\t2\t1\tsame-family=2,subagent-mode=1",
    ]
    for shell in ("sh", "dash", "bash", "zsh"):
        if shutil.which(shell) is not None:
            assert run(tmp_path, PRE_REQ722_LOG + new, shell=shell).stdout == out.stdout, shell
    # the recurrence report is the class report it always was
    rec = run(tmp_path, PRE_REQ722_LOG + new, "--recurrence", "--reqs", "REQ-301,REQ-303")
    assert rec.stdout == "a-b\t2\t2\treviewer\n"
    # a ran review with nothing found still shows the block; no skip reason reads `-`
    one = run(tmp_path, [_xfam_line("REQ-306", {"api": {"status": "ran"}})])
    assert one.stdout.split("\n\n")[1].splitlines()[2] == "1\t1\t1\t0\t0\t0\t0\t0\t-"
