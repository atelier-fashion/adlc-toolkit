"""Tests for tools/delegate/run_outcome.py — the RunOutcome emitter (REQ-648).

The structural test validates an emitted line against the documented key list
(BR-9): every key present, every value a string (no nested object, no array),
every count a quoted decimal or ``-``, every enum in its vocabulary. The one
exception is REQ-722's optional ``crossFamily`` object, last, whose leaves are
strings too (BR-13); the REQ-722 cases at the end pin its writer and its counts. The other
cases pin the derivation, the tolerance of a state file written before this REQ
(AC-4), the class tiers (BR-6), the redaction parity with emit-telemetry.sh's
sed chain (BR-1, LESSON-441) and the state writers (atomic, merge-preserving,
monotone — BR-10, BR-4).
"""

import datetime
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
SCRIPT = DELEGATE_DIR / "run_outcome.py"

sys.path.insert(0, str(DELEGATE_DIR))
import run_outcome as RO  # noqa: E402

NOW = datetime.datetime(2026, 10, 29, 12, 0, 0, tzinfo=datetime.timezone.utc)
QUOTED_COUNT = re.compile(r"^(-|[0-9]+)\Z")


def _state(**extra):
    base = {
        "req": "REQ-648",
        "startedAt": "2026-10-29T11:00:00Z",
        "repos": {"adlc-toolkit": {
            "primary": True,
            "path": "/Users/x/GitHub/adlc-toolkit",
            "worktree": "/Users/x/GitHub/adlc-toolkit/.worktrees/REQ-648",
        }},
    }
    base.update(extra)
    return base


def _write(tmp_path, data, name="pipeline-state.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _run(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                          capture_output=True, text=True)


def assert_structural(line):
    """BR-9: the documented key list, flat scalars, counts quoted, enums closed.

    REQ-722 appends one optional key, `crossFamily`, last: every other key is
    always present and a flat string; `crossFamily`, when present, is an object
    whose leaves are all strings (BR-13)."""
    assert "\n" not in line.strip()
    record = json.loads(line)
    assert RO.KEYS[-len(RO.OPTIONAL_KEYS):] == RO.OPTIONAL_KEYS == ("crossFamily",)
    required = [k for k in RO.KEYS if k not in RO.OPTIONAL_KEYS]
    assert list(record) in (required, list(RO.KEYS)), "every documented key, in order, nothing else"
    for key, value in record.items():
        if key == "crossFamily":
            assert_cross_family_shape(value)
            continue
        assert isinstance(value, str), f"{key} is {type(value).__name__}, not a string"
    for key in RO.COUNT_KEYS:
        assert QUOTED_COUNT.match(record[key]), f"{key}={record[key]!r} is not a quoted count"
    assert record["elapsed_s"] == "-" or record["elapsed_s"].isdigit()
    assert record["skill"] == "proceed" and record["step"] == "run-outcome"
    assert record["engine"] in RO.ENGINES
    assert record["terminal"] in RO.TERMINALS
    assert record["blocked_reason"] in RO.BLOCKED_REASONS + ("",)
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z", record["timestamp"])
    for cls in filter(None, record["finding_classes"].split(",")):
        assert RO.CLASS_RE.match(cls), cls
    return record


def assert_cross_family_shape(obj):
    """The `crossFamily` object: the counts as quoted decimals, then `repos`, each
    a valid repo id mapping to a closed `status` and `reason`, nothing else."""
    cf = RO._sibling("cross_family")
    assert isinstance(obj, dict)
    assert list(obj) == list(RO.CROSS_FAMILY_COUNTS) + ["repos"]
    for key in RO.CROSS_FAMILY_COUNTS:
        assert isinstance(obj[key], str) and obj[key].isdigit(), (key, obj[key])
    assert isinstance(obj["repos"], dict)
    for repo, entry in obj["repos"].items():
        assert RO.REPO_ID_RE.match(repo), repo
        assert list(entry) == ["status", "reason"]
        assert entry["status"] in cf.REVIEW_STATUSES + ("-",)
        assert entry["reason"] in cf.SKIP_REASONS + ("-",)
        assert entry["reason"] == "-" or entry["status"] == "skipped"


# --- BR-9 / BR-1: the line --------------------------------------------------------

def test_emitted_line_is_flat_and_complete(tmp_path):
    state = _state(
        harness={"version": "5.4.0", "sha": "c013262"},
        validateAttempts={"phase1": 2, "phase3": 1},
        verify={"findings": [
            {"severity": "Major", "file": "a.py", "title": "t", "class": "unanchored-marker-regex", "fixed": True},
            {"severity": "Nit", "file": "b.md", "title": "u", "class": "LESSON-390", "fixed": False},
        ], "loops": 1},
        lessons={"acknowledged": {"ids": ["LESSON-012", "LESSON-571"]}},
        lessonsWritten=["LESSON-740"],
    )
    out = _run("emit", "--state", str(_write(tmp_path, state)), "--terminal", "merged", "--engine", "solo")
    assert out.returncode == 0, out.stderr
    assert out.stdout.count("\n") == 1
    rec = assert_structural(out.stdout)
    assert rec["req"] == "REQ-648" and rec["repo"] == "adlc-toolkit"
    assert rec["toolkit_version"] == "5.4.0" and rec["toolkit_sha"] == "c013262"
    assert rec["validate_retries"] == "1" and rec["verify_loops"] == "1"
    assert (rec["findings_critical"], rec["findings_major"], rec["findings_minor"], rec["findings_nit"]) == ("0", "1", "0", "1")
    assert rec["finding_classes"] == "unanchored-marker-regex,LESSON-390"
    assert rec["lessons_cited"] == "LESSON-012,LESSON-571"
    assert rec["lessons_written"] == "LESSON-740"
    assert rec["blocked_reason"] == ""


def test_repo_strips_worktree_suffix():
    state = _state(repos={"r": {"primary": True, "path": "/a/b/proj/.worktrees/REQ-648"}})
    assert RO.build_record(state, "merged", "solo", now=NOW)["repo"] == "proj"


def test_elapsed_spans_started_at():
    assert RO.build_record(_state(), "merged", "solo", now=NOW)["elapsed_s"] == "3600"
    assert RO.build_record(_state(startedAt="garbage"), "merged", "solo", now=NOW)["elapsed_s"] == "-"


def test_bad_terminal_or_engine_is_usage(tmp_path):
    path = str(_write(tmp_path, _state()))
    assert _run("emit", "--state", path, "--terminal", "done", "--engine", "solo").returncode == 2
    assert _run("emit", "--state", path, "--terminal", "merged", "--engine", "cloud").returncode == 2


# --- REQ-719 BR-18 / AC-14: `rejected`, the exec engine's own terminal ------------

def test_req719_rejected_is_an_exec_only_terminal(tmp_path):
    # A close-out that failed would give a merged line `close-out-failed`; a
    # rejected line keeps an empty reason whatever the state says.
    state = _state(closeOut={"status": "failed", "reason": "chore PR blocked"},
                   verify={"findings": [{"severity": "Major", "class": "a-class", "title": "t"}], "loops": 1})
    path = str(_write(tmp_path, state))
    operator_text = "not this quarter, the API is frozen"

    # must-not-fire: the exec engine writes it, one line, no reason
    out = _run("emit", "--state", path, "--terminal", "rejected", "--engine", "exec",
               "--reason", operator_text)
    assert out.returncode == 0, out.stderr
    assert out.stdout.count("\n") == 1
    rec = assert_structural(out.stdout)
    assert (rec["terminal"], rec["engine"], rec["blocked_reason"]) == ("rejected", "exec", "")
    assert operator_text not in out.stdout and "frozen" not in out.stdout
    assert rec["findings_major"] == "1" and rec["finding_classes"] == "a-class", "the run's own record is kept"
    plain = RO.build_record(_state(), "rejected", "exec", now=NOW)
    assert plain["blocked_reason"] == ""

    # every other engine: a usage error, nothing printed
    for engine in ("solo", "legacy", "workflow"):
        refused = _run("emit", "--state", path, "--terminal", "rejected", "--engine", engine)
        assert refused.returncode == 2, (engine, refused.stderr)
        assert refused.stdout == "", engine
        assert refused.stderr.startswith("run-outcome: --terminal rejected"), refused.stderr
        with pytest.raises(RO.UsageError):
            RO.build_record(state, "rejected", engine, now=NOW)

    # must-not-fire: REQ-648's four terminals stay open to every engine
    for engine in RO.ENGINES:
        for terminal in ("merged", "pr-ready", "blocked", "failed"):
            assert RO.build_record(_state(), terminal, engine, now=NOW)["terminal"] == terminal

    # through the wrapper: a refused line leaves the log byte-identical, rc 0
    wrapper = DELEGATE_DIR / "emit-run-outcome.sh"
    log = tmp_path / "logs" / "run-outcomes.log"
    log.parent.mkdir()
    log.write_text('{"earlier":"line"}\n', encoding="utf-8")
    before = log.read_bytes()
    env = dict(os.environ, ADLC_RUN_OUTCOMES_LOG=str(log))
    for engine in ("solo", "legacy", "workflow"):
        wrapped = subprocess.run(["sh", str(wrapper), "--state", path, "--terminal", "rejected",
                                  "--engine", engine], env=env, capture_output=True, text=True)
        assert wrapped.returncode == 0, wrapped.stderr
        assert any(l.startswith("run-outcome: emit failed (rc 2)")
                   for l in wrapped.stderr.splitlines()), wrapped.stderr
        assert wrapped.stdout == "", engine
        assert log.read_bytes() == before, engine
    appended = subprocess.run(["sh", str(wrapper), "--state", path, "--terminal", "rejected",
                               "--engine", "exec"], env=env, capture_output=True, text=True)
    assert appended.returncode == 0 and appended.stderr == "", appended.stderr
    added = log.read_text(encoding="utf-8").splitlines()[1:]
    assert len(added) == 1
    assert assert_structural(added[0])["terminal"] == "rejected"


# --- REQ-719 BR-19: `aborted` ---------------------------------------------------

def test_req719_aborted_is_a_reason_of_its_own(tmp_path):
    assert "aborted" in RO.BLOCKED_REASONS
    out = _run("emit", "--state", str(_write(tmp_path, _state())), "--terminal", "failed",
               "--engine", "exec", "--reason", "aborted")
    assert out.returncode == 0, out.stderr
    rec = assert_structural(out.stdout)
    assert (rec["terminal"], rec["blocked_reason"]) == ("failed", "aborted")
    assert RO.normalize_blocked_reason(" Aborted ") == "aborted"
    # it takes nothing from its neighbours: those still map where they did
    assert RO.normalize_blocked_reason("other") == "other"
    assert RO.normalize_blocked_reason("lane-check") == "other"
    assert RO.normalize_blocked_reason("close-out-failed") == "close-out-failed"
    # a reason passed with a non-halt terminal is still ignored
    assert RO.build_record(_state(), "merged", "exec", reason="aborted", now=NOW)["blocked_reason"] == ""


def test_req719_aborted_from_any_other_engine_reads_other(tmp_path):
    """A session writes its own run-outcome line through a fence, with a reason token of its
    choosing. `aborted` is the exec engine's, an operator's `abort`: from `solo`, `legacy` or
    `workflow` the line is still written, and its reason reads `other`."""
    for engine in RO.ENGINES:
        for terminal in ("failed", "blocked"):
            rec = RO.build_record(_state(), terminal, engine, reason="aborted", now=NOW)
            want = "aborted" if engine == RO.REJECTED_ENGINE else "other"
            assert rec["blocked_reason"] == want, (engine, terminal)
    out = _run("emit", "--state", str(_write(tmp_path, _state())), "--terminal", "failed",
               "--engine", "solo", "--reason", "aborted")
    assert out.returncode == 0, out.stderr
    assert assert_structural(out.stdout)["blocked_reason"] == "other"


# --- REQ-719 BR-21: the workflow engine has no reject ------------------------------

def test_req719_workflow_terminal_enum_is_unchanged():
    text = (REPO_ROOT / "workflows" / "adlc-sprint.workflow.js").read_text(encoding="utf-8")
    start = text.index("const TERMINAL = {")
    match = re.search(r"state:\s*\{\s*type:\s*'string',\s*enum:\s*\[([^\]]*)\]", text[start:])
    assert match, "TERMINAL.state is no longer a string enum"
    enum = re.findall(r"'([^']*)'", match.group(1))
    assert enum == ["merged", "pr-ready", "blocked", "failed"]
    # the workflow passes TERMINAL.state verbatim, so its whole enum is accepted,
    # and the one terminal it cannot hold is the one it may not write
    assert set(enum) == set(RO.TERMINALS) - {"rejected"}
    for terminal in enum:
        assert RO.build_record(_state(), terminal, "workflow", now=NOW)["terminal"] == terminal
    with pytest.raises(RO.UsageError):
        RO.build_record(_state(), "rejected", "workflow", now=NOW)


# --- AC-4: a state file written before this REQ -----------------------------------

def test_absent_keys_emit_dash_and_zero(tmp_path):
    out = _run("emit", "--state", str(_write(tmp_path, _state())), "--terminal", "pr-ready", "--engine", "legacy")
    assert out.returncode == 0, out.stderr
    rec = assert_structural(out.stdout)
    assert rec["toolkit_version"] == "-" and rec["toolkit_sha"] == "-"
    for key in RO.COUNT_KEYS:
        assert rec[key] == "0", key
    assert rec["finding_classes"] == "" and rec["lessons_cited"] == "" and rec["lessons_written"] == ""


def test_malformed_values_do_not_fail():
    state = _state(harness="not-an-object", validateAttempts={"phase1": "three", "phase3": True},
                   verify={"findings": "nope", "loops": -4}, lessons=[], lessonsWritten=7)
    rec = RO.build_record(state, "failed", "workflow", reason="phase0-no-worktree", now=NOW)
    assert rec["validate_retries"] == "0" and rec["verify_loops"] == "0"
    assert rec["toolkit_version"] == "-" and rec["blocked_reason"] == "no-worktree"


def test_missing_state_needs_req(tmp_path):
    missing = str(tmp_path / "absent.json")
    assert _run("emit", "--state", missing, "--terminal", "failed", "--engine", "workflow").returncode == 1
    out = _run("emit", "--state", missing, "--terminal", "failed", "--engine", "workflow",
               "--reason", "phase0-no-worktree", "--req", "REQ-999")
    assert out.returncode == 0, out.stderr
    rec = assert_structural(out.stdout)
    assert rec["req"] == "REQ-999" and rec["repo"] == "-" and rec["blocked_reason"] == "no-worktree"


# --- AC-2 / BR-5: halts and reasons -----------------------------------------------

def test_validation_exhausted_line(tmp_path):
    state = _state(validateAttempts={"phase1": 3})
    out = _run("emit", "--state", str(_write(tmp_path, state)), "--terminal", "blocked",
               "--engine", "solo", "--reason", "validation-exhausted")
    rec = assert_structural(out.stdout)
    assert rec["terminal"] == "blocked"
    assert rec["blocked_reason"] == "validation-exhausted"
    assert rec["validate_retries"] == "2"
    assert rec["lessons_written"] == ""


def test_validate_retries_rule():
    assert RO.validate_retries({"phase1": 3}) == 2
    assert RO.validate_retries({"phase1": 1, "phase3": 1}) == 0
    assert RO.validate_retries({"phase1": 2, "phase3": 3}) == 3
    assert RO.validate_retries({"phase1": "2"}) == 1
    assert RO.validate_retries({"phase1": True, "phase3": 2.5}) == 0
    assert RO.validate_retries(None) == 0


@pytest.mark.parametrize("reason,expected", [
    ("spec-validation", "validation-exhausted"),
    ("architecture-validation", "validation-exhausted"),
    ("validation-exhausted", "validation-exhausted"),
    ("reflector-questions", "reflector-questions"),
    ("merge-conflict", "merge-conflict"),
    ("needs-manual-rebase", "merge-conflict"),
    ("merge conflict — the PR could not be merged cleanly", "merge-conflict"),
    ("merge-unverified", "merge-unverified"),
    ("merge claim could not be verified via gh pr view (state != MERGED)", "merge-unverified"),
    ("phase0-no-worktree", "no-worktree"),
    ("phase8-no-pr", "no-pr"),
    ("phase8-no-repo", "setup-error"),
    ("close-out-failed", "close-out-failed"),
    ("lane-check", "other"),
    ("", ""),
])
def test_normalize_blocked_reason_maps_workflow_reasons(reason, expected):
    assert RO.normalize_blocked_reason(reason) == expected
    assert expected in RO.BLOCKED_REASONS + ("",)


def test_merged_terminal_has_empty_blocked_reason():
    """Must-not-fire: a reason passed with a non-halt terminal is ignored."""
    assert RO.build_record(_state(), "merged", "solo", reason="merge-conflict", now=NOW)["blocked_reason"] == ""
    assert RO.build_record(_state(), "pr-ready", "legacy", now=NOW)["blocked_reason"] == ""
    failed_close = _state(closeOut={"status": "failed", "reason": "chore PR blocked"})
    assert RO.build_record(failed_close, "merged", "workflow", now=NOW)["blocked_reason"] == "close-out-failed"


# --- BR-6 / AC-8 / AC-11: class and redaction -------------------------------------

def test_finding_class_tiers():
    assert RO.finding_class({"lessonId": "LESSON-390", "class": "x-y", "title": "T"}) == "LESSON-390"
    assert RO.finding_class({"class": "cross-fence-shell-state", "title": "T"}) == "cross-fence-shell-state"
    assert RO.finding_class({"class": "Task Ordering", "title": "Task ordering race"}) == "title-slug:task-ordering-race"
    assert RO.finding_class({"title": "A very long title with many words in it"}) == "title-slug:a-very-long-title-with-many"
    assert RO.finding_class({"lessonId": "LESSON-12", "class": "ok-class"}) == "ok-class"
    assert RO.finding_class({}) == "title-slug:untitled"
    assert RO.class_tier("LESSON-390") == "lesson"
    assert RO.class_tier("title-slug:a-b") == "title-slug"
    assert RO.class_tier("cross-fence-shell-state") == "reviewer"
    for c in ("task-ordering-race", "LESSON-390", "title-slug:x-y"):
        assert RO.CLASS_RE.match(c)
    for c in ("Task Ordering", "a-b-c-d-e-f-g", "LESSON-1", "title-slug:", "x_y"):
        assert not RO.CLASS_RE.match(c)


def test_class_slug_survives_redaction(tmp_path):
    state = _state(verify={"findings": [
        {"severity": "Minor", "file": "f", "title": "t", "class": "task-ordering-race-in-fixture"},
    ]})
    rec = assert_structural(_run("emit", "--state", str(_write(tmp_path, state)),
                                 "--terminal", "merged", "--engine", "solo").stdout)
    assert rec["finding_classes"] == "task-ordering-race-in-fixture"
    # Why the class is exempt from redaction and regex-validated instead (BR-6):
    # `ta` + `sk-ordering-race-in-fixture` is an `sk-` run of 20+ characters, so
    # the chain WOULD rewrite it and manufacture a false `[REDACTED]` recurrence.
    assert RO.redact("task-ordering-race-in-fixture") != "task-ordering-race-in-fixture"
    # must-not-fire: redaction leaves ordinary free-text values alone
    for benign in ("adlc-toolkit", "5.4.0", "risk-check", "plain words here"):
        assert RO.redact(benign) == benign


def test_free_text_credential_is_redacted(tmp_path):
    token = "ghp_" + "A1b2C3d4E5" * 3 + "abcdef"
    assert len(token) == 40
    state = _state(harness={"version": token, "sha": "c013262"},
                   repos={"r": {"primary": True, "path": f"/x/{token}"}})
    rec = assert_structural(_run("emit", "--state", str(_write(tmp_path, state)),
                                 "--terminal", "merged", "--engine", "solo").stdout)
    assert rec["toolkit_version"] == "[REDACTED]"
    assert rec["repo"] == "[REDACTED]"
    assert token not in json.dumps(rec)


def _sed_chain():
    """The redaction expression, read out of emit-telemetry.sh (not retyped)."""
    text = (DELEGATE_DIR / "emit-telemetry.sh").read_text(encoding="utf-8")
    match = re.search(r"sed -E '(s/.+?/\[REDACTED\]/g)'", text)
    assert match, "emit-telemetry.sh no longer carries the sed -E redaction line"
    return match.group(1)


REDACTION_FIXTURE = [
    "plain text with nothing secret",
    "key sk-" + "a" * 24 + " trailing",
    "aws AKIA" + "ABCDEFGHIJKLMNOP" + " id",
    "gh ghp_" + "x" * 36 + " token",
    "auth Bearer " + "abc.def-ghi_" * 3,
    "MOONSHOT_API_KEY=supersecretvalue rest",
    "GITHUB_TOKEN: abc123 more",
    "two sk-" + "b" * 30 + " and ghp_" + "y" * 40,
    "class task-ordering-race-in-fixture stays",
]


@pytest.mark.skipif(shutil.which("sed") is None, reason="sed not installed")
def test_redaction_parity_with_emit_telemetry_sed_chain():
    expr = _sed_chain()
    for sample in REDACTION_FIXTURE:
        sed = subprocess.run(["sed", "-E", expr], input=sample, capture_output=True, text=True)
        assert sed.returncode == 0, sed.stderr
        assert RO.redact(sample) == sed.stdout.rstrip("\n"), sample


# --- AC-1 / BR-10: the harness stamp ----------------------------------------------

def _git_repo(path, version="9.9.9"):
    path.mkdir()
    (path / "VERSION").write_text(version + "\n", encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e")
    for cmd in (["init", "-q"], ["add", "VERSION"], ["commit", "-q", "-m", "v"]):
        subprocess.run(["git", "-C", str(path), *cmd], check=True, env=env, capture_output=True)
    sha = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return sha


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_record_harness_written_once(tmp_path):
    root = tmp_path / "toolkit"
    sha = _git_repo(root)
    state = _write(tmp_path, _state())
    out = _run("record-harness", "--state", str(state), "--toolkit-root", str(root))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == f"harness: 9.9.9 {sha}"
    data = json.loads(state.read_text())
    assert data["harness"] == {"version": "9.9.9", "sha": sha}
    assert data["req"] == "REQ-648" and "repos" in data, "other keys survive"
    # never re-read: a later call against a different toolkit keeps the first stamp
    other = tmp_path / "other"
    _git_repo(other, version="1.0.0")
    _run("record-harness", "--state", str(state), "--toolkit-root", str(other))
    assert json.loads(state.read_text())["harness"] == {"version": "9.9.9", "sha": sha}


def test_record_harness_plugin_cache_has_no_sha(tmp_path):
    """The plugin cache copy has VERSION and no .git: sha is '-'."""
    root = tmp_path / "cache"
    root.mkdir()
    (root / "VERSION").write_text("5.4.0\n", encoding="utf-8")
    state = _write(tmp_path, _state())
    assert _run("record-harness", "--state", str(state), "--toolkit-root", str(root)).returncode == 0
    harness = json.loads(state.read_text())["harness"]
    assert harness["version"] == "5.4.0"
    assert harness["sha"] == "-"
    missing = _write(tmp_path, _state(), name="b.json")
    _run("record-harness", "--state", str(missing), "--toolkit-root", str(tmp_path / "nowhere"))
    assert json.loads(missing.read_text())["harness"] == {"version": "-", "sha": "-"}


def test_bug289_a_stamp_with_no_state_file_writes_nothing_and_says_what_to_do(tmp_path):
    """BUG-289: an exec session stamped the harness before Step 0's lessons fence had created
    the state file, and read the bare `state file not found` as a failed setup. The stamp
    still creates nothing, because the file's first writer decides fresh or resume, and its
    one line now says the file is not there yet, that this is no blocker, and which fence
    creates it. Through the wrapper the status is 0 and the second line says to carry on."""
    root = tmp_path / "cache"
    root.mkdir()
    (root / "VERSION").write_text("5.4.0\n", encoding="utf-8")
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    state = spec_dir / "pipeline-state.json"
    for mode in ([], ["--fresh"]):
        out = _run("record-harness", "--state", str(state), "--toolkit-root", str(root), *mode)
        assert out.returncode == 1 and out.stdout == "", (mode, out.stdout)
        [line] = out.stderr.splitlines()
        assert line.startswith(f"run-outcome: state file not found: {state} ("), line
        assert "not a blocker" in line and "Step 0's lessons fence creates this file" in line
        assert "run it, then this one again" in line
        assert list(spec_dir.iterdir()) == [], "the stamp creates no file"
    wrapper = DELEGATE_DIR / "emit-run-outcome.sh"
    wrapped = subprocess.run(["sh", str(wrapper), "record-harness", "--state", str(state),
                              "--toolkit-root", str(root), "--fresh"],
                             capture_output=True, text=True)
    assert wrapped.returncode == 0 and wrapped.stdout == ""
    first, second = wrapped.stderr.splitlines()
    assert first.startswith("run-outcome: state file not found: ") and "not a blocker" in first
    assert second == ("run-outcome: record-harness failed (rc 1) — state not updated; "
                      "telemetry never halts the pipeline, so carry on")
    assert list(spec_dir.iterdir()) == []
    # must-not-fire: once the file exists the same call stamps it and prints neither line.
    state.write_text(json.dumps({"lessons": {"step0": {"lessons": []}}}), encoding="utf-8")
    wrapped = subprocess.run(["sh", str(wrapper), "record-harness", "--state", str(state),
                              "--toolkit-root", str(root), "--fresh"],
                             capture_output=True, text=True)
    assert wrapped.returncode == 0 and wrapped.stderr == "", wrapped.stderr
    assert wrapped.stdout.strip() == "harness: 5.4.0 -"
    data = json.loads(state.read_text())
    assert data["harness"] == {"version": "5.4.0", "sha": "-"}
    assert data["lessons"] == {"step0": {"lessons": []}}, "the lessons fence's key survives"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_toolkit_sha_comes_from_state_not_disk(tmp_path):
    """AC-1: the line carries the Step-0 sha even after the clone moved on."""
    root = tmp_path / "toolkit"
    first = _git_repo(root)
    state = _write(tmp_path, _state())
    _run("record-harness", "--state", str(state), "--toolkit-root", str(root))
    (root / "VERSION").write_text("9.9.10\n", encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e")
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "pull"], check=True, env=env, capture_output=True)
    rec = assert_structural(_run("emit", "--state", str(state), "--terminal", "merged", "--engine", "solo").stdout)
    assert rec["toolkit_sha"] == first and rec["toolkit_version"] == "9.9.9"


# --- validateAttempts --------------------------------------------------------------

def test_record_validate_is_monotone(tmp_path):
    state = _write(tmp_path, _state(notes=["keep me"]))
    assert _run("record-validate", "--state", str(state), "--phase", "1", "--attempt", "1").returncode == 0
    _run("record-validate", "--state", str(state), "--phase", "1", "--attempt", "2")
    _run("record-validate", "--state", str(state), "--phase", "1", "--attempt", "2")  # replay
    _run("record-validate", "--state", str(state), "--phase", "1", "--attempt", "1")  # stale
    data = json.loads(state.read_text())
    assert data["validateAttempts"] == {"phase1": 2, "phase3": 0}
    assert data["notes"] == ["keep me"]
    assert _run("record-validate", "--state", str(state), "--phase", "2", "--attempt", "1").returncode == 2
    assert _run("record-validate", "--state", str(state), "--phase", "3", "--attempt", "0").returncode == 2


# --- BR-4 / AC-3: verify -------------------------------------------------------------

def test_record_verify_normalises_and_marks_fixed(tmp_path):
    state = _write(tmp_path, _state(verify={"loops": 1, "findings": []}))
    findings = [
        {"severity": "High", "file": "a.py", "title": "Injection", "class": "unvalidated-shell-arg", "fixed": True},
        {"severity": "Medium", "file": "b.py", "title": "Naming drift"},
        {"severity": "Low", "file": "c.md", "title": "typo", "lessonId": "LESSON-404", "class": "x"},
        {"severity": "Critical", "file": "d.js", "title": "Race", "class": "Bad Class", "fixed": "yes"},
    ]
    out = _run("record-verify", "--state", str(state), "--findings", "-", stdin=json.dumps(findings))
    assert out.returncode == 0, out.stderr
    data = json.loads(state.read_text())
    v = data["verify"]
    assert v["loops"] == 1, "loops kept when not given"
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z", v["consolidatedAt"])
    got = [(f["severity"], f["class"], f["fixed"]) for f in v["findings"]]
    assert got == [
        ("Major", "unvalidated-shell-arg", True),
        ("Minor", "title-slug:naming-drift", False),
        ("Nit", "LESSON-404", False),
        ("Critical", "title-slug:race", False),  # a non-boolean fixed is not fixed
    ]
    assert v["findings"][2]["lessonId"] == "LESSON-404"
    for f in v["findings"]:
        assert RO.CLASS_RE.match(f["class"])
    # the emitted counts come from what was recorded, not from the worktree copy
    rec = assert_structural(_run("emit", "--state", str(state), "--terminal", "merged", "--engine", "solo").stdout)
    assert (rec["findings_critical"], rec["findings_major"], rec["findings_minor"], rec["findings_nit"]) == ("1", "1", "1", "1")
    # a second write (Step C) replaces the list and can set loops
    _run("record-verify", "--state", str(state), "--findings", "-", "--loops", "0", stdin="[]")
    assert json.loads(state.read_text())["verify"]["findings"] == []


def test_record_verify_rejects_bad_input(tmp_path):
    state = _write(tmp_path, _state())
    assert _run("record-verify", "--state", str(state), "--findings", "-", stdin="{not json").returncode == 2
    assert _run("record-verify", "--state", str(state), "--findings", "-", stdin='{"a":1}').returncode == 2
    assert _run("record-verify", "--state", str(state), "--findings", "-", "--loops", "x", stdin="[]").returncode == 2
    assert "verify" not in json.loads(state.read_text())


def test_record_on_missing_state_is_rc1(tmp_path):
    out = _run("record-validate", "--state", str(tmp_path / "none.json"), "--phase", "1", "--attempt", "1")
    assert out.returncode == 1 and out.stderr.startswith("run-outcome:")


# --- lessonsWritten -----------------------------------------------------------------

def test_record_lessons_written(tmp_path):
    state = _write(tmp_path, _state())
    assert _run("record-lessons-written", "--state", str(state), "--ids", "LESSON-740, LESSON-741").returncode == 0
    assert json.loads(state.read_text())["lessonsWritten"] == ["LESSON-740", "LESSON-741"]
    rec = RO.build_record(json.loads(state.read_text()), "merged", "solo", now=NOW)
    assert rec["lessons_written"] == "LESSON-740,LESSON-741"
    _run("record-lessons-written", "--state", str(state), "--no-entry")
    assert RO.build_record(json.loads(state.read_text()), "merged", "solo", now=NOW)["lessons_written"] == "NO_ENTRY"
    assert _run("record-lessons-written", "--state", str(state), "--ids", "LESSON-1,oops").returncode == 2


def test_state_write_is_atomic_and_leaves_no_temp(tmp_path):
    state = _write(tmp_path, _state())
    _run("record-validate", "--state", str(state), "--phase", "3", "--attempt", "1")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pipeline-state.json"]


# --- AC-10: the delegation tools are untouched ---------------------------------------

def test_delegation_tools_untouched():
    """emit-telemetry.sh and check-delegation.sh are byte-identical to origin/main."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    probe = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", "-q", "origin/main"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("no origin/main ref in this checkout")
    diff = subprocess.run(["git", "-C", str(REPO_ROOT), "diff", "--quiet", "origin/main", "--",
                           "tools/delegate/emit-telemetry.sh", "tools/delegate/check-delegation.sh"])
    assert diff.returncode == 0, "REQ-648 must not modify emit-telemetry.sh or check-delegation.sh"


# --- record-carry: the primary-path copy is complete before teardown ---------------

def test_record_carry_fills_missing_keys_only(tmp_path):
    primary = _write(tmp_path, {"req": "REQ-648", "lessons": {"step0": {"lessons": []}},
                                "harness": {"version": "5.4.0", "sha": "c013262"},
                                "completed": True, "currentPhase": 8}, name="primary.json")
    worktree = _write(tmp_path, _state(completed=False, currentPhase=7, validateAttempts={"phase1": 2}),
                      name="worktree.json")
    out = _run("record-carry", "--state", str(primary), "--from", str(worktree))
    assert out.returncode == 0, out.stderr
    data = json.loads(primary.read_text())
    assert data["completed"] is True and data["currentPhase"] == 8, "the primary copy's keys win"
    assert data["startedAt"] == "2026-10-29T11:00:00Z" and "repos" in data, "missing keys are carried"
    assert data["validateAttempts"] == {"phase1": 2}
    rec = RO.build_record(data, "merged", "solo", now=NOW)
    assert rec["repo"] == "adlc-toolkit" and rec["elapsed_s"] == "3600" and rec["validate_retries"] == "1"
    again = _run("record-carry", "--state", str(primary), "--from", str(worktree))
    assert "nothing" in again.stdout
    assert _run("record-carry", "--state", str(primary), "--from", str(tmp_path / "gone.json")).returncode == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_record_harness_fresh_restamps_and_clears_a_prior_run(tmp_path):
    """LESSON-719: fresh vs resume comes from the caller's progress record, not
    from whether the key exists — a fresh re-run must not inherit the old stamp."""
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    _git_repo(old_root, version="1.0.0")
    new_sha = _git_repo(new_root, version="2.0.0")
    state = _write(tmp_path, _state(validateAttempts={"phase1": 3}, verify={"findings": [], "loops": 1},
                                    lessonsWritten="NO_ENTRY", lessons={"step0": {}},
                                    crossFamilyReview={"adlc-toolkit": {"status": "ran"}}))
    _run("record-harness", "--state", str(state), "--toolkit-root", str(old_root))
    assert json.loads(state.read_text())["harness"]["version"] == "1.0.0"
    # a resume keeps everything
    _run("record-harness", "--state", str(state), "--toolkit-root", str(new_root))
    kept = json.loads(state.read_text())
    assert kept["harness"]["version"] == "1.0.0" and kept["validateAttempts"] == {"phase1": 3}
    # a fresh Step 0 re-stamps and clears the earlier run's records, nothing else
    assert _run("record-harness", "--state", str(state), "--toolkit-root", str(new_root), "--fresh").returncode == 0
    fresh = json.loads(state.read_text())
    assert fresh["harness"] == {"version": "2.0.0", "sha": new_sha}
    for key in ("validateAttempts", "verify", "lessonsWritten", "crossFamilyReview"):
        assert key not in fresh, key
    assert fresh["lessons"] == {"step0": {}} and fresh["req"] == "REQ-648"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_record_harness_ignores_an_enclosing_repo(tmp_path):
    """A ToolkitRoot with no .git of its own, inside some other checkout (the
    plugin cache under a git-tracked HOME), stamps sha '-', not the outer sha."""
    outer = tmp_path / "home"
    _git_repo(outer)
    cache = outer / ".claude" / "plugins" / "cache" / "adlc"
    cache.mkdir(parents=True)
    (cache / "VERSION").write_text("5.4.0\n", encoding="utf-8")
    assert RO.read_harness(str(cache)) == {"version": "5.4.0", "sha": "-"}
    # its own checkout — a directory .git, or a linked worktree's .git file — still counts
    assert RO.SHA_RE.match(RO.read_harness(str(outer))["sha"])


# --- REQ-722: the cross-family review record, its findings and its counts --------

CF_PATH = DELEGATE_DIR / "cross_family.py"


def _cf():
    return RO._sibling("cross_family")


def _xfam(state, *args):
    return _run("record-cross-family", "--state", str(state), *args)


def _verify(state, findings, *extra):
    return _run("record-verify", "--state", str(state), "--findings", "-", *extra,
                stdin=json.dumps(findings))


def test_record_cross_family_written_at_event(tmp_path):
    """BR-5: one call writes the repo's record at once, in one atomic write that
    keeps every other key; a skip writes its reason, a run writes none; a second
    repo joins the first; nothing is redacted (LESSON-744)."""
    before = _state(lessons={"step0": {}}, verify={"findings": [], "loops": 0})
    state = _write(tmp_path, before)
    out = _xfam(state, "--repo", "adlc-toolkit", "--status", "ran", "--implementer", "anthropic",
                "--reviewer", "moonshot", "--findings", "3", "--dropped", "1")
    assert out.returncode == 0, out.stderr
    assert out.stdout == "crossFamilyReview: adlc-toolkit ran, 3 finding(s), 1 dropped\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pipeline-state.json"], "atomic, no temp left"
    data = json.loads(state.read_text())
    assert data["crossFamilyReview"] == {"adlc-toolkit": {
        "status": "ran", "implementerFamily": "anthropic", "reviewerFamily": "moonshot",
        "findingCount": 3, "droppedCount": 1, "declinedCount": 0}}
    assert {k: v for k, v in data.items() if k != "crossFamilyReview"} == before

    # a skip, for a second repo whose id the credential chain would otherwise eat
    repo = "task-" + "x" * 24
    out = _xfam(state, "--repo", repo, "--status", "skipped", "--reason", "same-family",
                "--implementer", "openai", "--reviewer", "openai")
    assert out.returncode == 0, out.stderr
    assert out.stdout == f"crossFamilyReview: {repo} skipped same-family, 0 finding(s), 0 dropped\n"
    reviews = json.loads(state.read_text())["crossFamilyReview"]
    assert list(reviews) == ["adlc-toolkit", repo]
    assert reviews[repo] == {"status": "skipped", "reason": "same-family", "implementerFamily": "openai",
                             "reviewerFamily": "openai", "findingCount": 0, "droppedCount": 0,
                             "declinedCount": 0}
    assert reviews["adlc-toolkit"]["status"] == "ran", "the first repo's record is kept"

    # every reason in the closed vocabulary is accepted, through the shell wrapper too
    wrap = DELEGATE_DIR / "emit-run-outcome.sh"
    for reason in _cf().SKIP_REASONS:
        out = subprocess.run(["sh", str(wrap), "record-cross-family", "--state", str(state),
                              "--repo", "widgets", "--status", "skipped", "--reason", reason,
                              "--implementer", "unknown", "--reviewer", "moonshot"],
                             capture_output=True, text=True)
        assert (out.returncode, out.stderr) == (0, ""), reason
        assert json.loads(state.read_text())["crossFamilyReview"]["widgets"]["reason"] == reason


def test_record_cross_family_reason_vocabulary(tmp_path):
    """BR-4/BR-5: a reason outside SKIP_REASONS, a skip with no reason, a run with
    one, a family outside the enum, a bad repo id or count: usage (rc 2), and the
    state file is not touched. SKIP_REASONS is cross_family.py's own tuple."""
    assert _cf().__file__ == str(CF_PATH)
    assert '"delegation-disabled"' not in SCRIPT.read_text(encoding="utf-8"), "never a copy"
    state = _write(tmp_path, _state())
    original = state.read_text()
    good = ["--repo", "widgets", "--implementer", "anthropic", "--reviewer", "moonshot"]
    bad = [
        ["--status", "skipped", "--reason", "too-slow"],
        ["--status", "skipped", "--reason", "SAME-FAMILY"],
        ["--status", "skipped"],
        ["--status", "ran", "--reason", "same-family"],
        ["--status", "maybe"],
        ["--status", "skipped", "--reason", "same-family", "--findings", "2"],
        ["--status", "ran", "--findings", "-1"],
        ["--status", "ran", "--dropped", "many"],
    ]
    for args in bad:
        out = _xfam(state, *good, *args)
        assert out.returncode == 2, args
        assert out.stderr.startswith("run-outcome: "), args
    for flag, value in (("--implementer", "Anthropic"), ("--reviewer", "kimi-k2.6"),
                        ("--reviewer", "openai-compatible"), ("--implementer", "")):
        args = ["--repo", "widgets", "--status", "ran", "--implementer", "anthropic",
                "--reviewer", "moonshot"]
        args[args.index(flag) + 1] = value
        out = _xfam(state, *args)
        assert out.returncode == 2, (flag, value)
        assert value == "" or value not in out.stderr, "the message never echoes the rejected value"
    for repo in ("", "a/b", 'a"b', "x" * 65):
        assert _xfam(state, "--repo", repo, "--status", "ran", "--implementer", "anthropic",
                     "--reviewer", "moonshot").returncode == 2, repo
    assert _xfam(state, "--status", "ran", "--implementer", "anthropic",
                 "--reviewer", "moonshot").returncode == 2, "--repo is required"
    assert state.read_text() == original
    assert _xfam(tmp_path / "gone.json", *good, "--status", "ran").returncode == 1


def test_normalize_findings_keeps_the_cross_family_fields():
    raw = [
        {"severity": "Major", "file": "a.py", "title": "T", "class": "a-b",
         "source": ["cross-family", "panel", "cross-family", "planner"], "disposition": "declined",
         "declineReason": "a.py:3 guards it; key sk-" + "A" * 24},
        {"severity": "Minor", "file": "b.py", "title": "U", "source": "cross-family",
         "disposition": "ignored", "declineReason": "  "},
        {"severity": "Nit", "file": "c.py", "title": "V", "source": ["planner"], "disposition": "fixed"},
        {"severity": "Nit", "file": "d.py", "title": "W", "source": 7},
    ]
    a, b, c, d = RO.normalize_findings(raw)
    assert a["source"] == ["cross-family", "panel"], "closed members, sorted, once each"
    assert a["disposition"] == "declined"
    assert a["declineReason"] == "a.py:3 guards it; key " + RO.REDACTED, "free text is redacted"
    assert b["source"] == ["cross-family"], "a lone string is a one-member list"
    assert "disposition" not in b and "declineReason" not in b
    assert "source" not in c and c["disposition"] == "fixed", "no known member: absent"
    assert "source" not in d
    assert list(a) == ["severity", "file", "title", "class", "fixed", "source", "disposition",
                       "declineReason"]


_KEY = "sk-" + "A" * 24
_LONG = "tools/risk-assessment-" + "x" * 20 + ".py"


def _cited_repo(tmp_path):
    """A checkout holding the files the decline citations below name, committed."""
    import subprocess
    repo = tmp_path / "wt"
    (repo / "tools").mkdir(parents=True)
    (repo / "t").mkdir()
    (repo / "tools" / "risk-assessment-x.py").write_text("x = 1\n" * 20, encoding="utf-8")
    (repo / _LONG).write_text("x = 1\n" * 20, encoding="utf-8")
    (repo / "t" / "ui.test.js").write_text(
        "test('risk-assessment-%s', () => {});\ntest('risk', () => {});\n" % ("x" * 20),
        encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "c"]):
        subprocess.run(cmd, cwd=str(repo), env=env, check=True)
    return str(repo)


@pytest.mark.parametrize("reason,stored", [
    # The finding's example, exactly: the chain leaves it alone, and so does this.
    ("tools/risk-assessment-x.py:12 bounds it", "tools/risk-assessment-x.py:12 bounds it"),
    # A tracked citation with an ``sk-`` run of 20+ inside it: kept whole (must-fire of the fix).
    (_LONG + ":12 bounds it", _LONG + ":12 bounds it"),
    (_LONG + ":12-14", _LONG + ":12-14"),
    ("test:t/ui.test.js::risk-assessment-" + "x" * 20 + " passes",
     "test:t/ui.test.js::risk-assessment-" + "x" * 20 + " passes"),
    # The rest of the text is redacted as before (must-not-fire of the exemption).
    (_LONG + ":12 bounds it; key " + _KEY, _LONG + ":12 bounds it; key " + RO.REDACTED),
    ("test:t/ui.test.js::risk passes " + _KEY, "test:t/ui.test.js::risk passes " + RO.REDACTED),
    # A credential shaped like a citation names nothing the repository holds: redacted
    # (the Step D security regression: each of these used to come back whole).
    (_KEY + ":12", RO.REDACTED + ":12"),
    (_KEY + ".py:1", RO.REDACTED + ".py:1"),
    ("x/" + _KEY + ":1", "x/" + RO.REDACTED + ":1"),
    ("ghp_" + "A" * 36 + "/x:12", RO.REDACTED + "/x:12"),
    ("AKIA" + "A" * 16 + "/x.py:3", RO.REDACTED + "/x.py:3"),
    ("q/OPENAI_API_KEY:123456789", "q/" + RO.REDACTED),
    ("test:a/b::" + _KEY, "test:a/b::" + RO.REDACTED),
    ("test:t/ui.test.js::" + _KEY, "test:t/ui.test.js::" + RO.REDACTED),
    # A real file cited past its end is not a citation that checks out: redacted.
    (_LONG + ":99", "tools/ri" + RO.REDACTED + ".py:99"),
    # A match that starts outside a token and runs into it is redacted whole.
    ("X_TOKEN=a.py:1", RO.REDACTED),
    ("Bearer " + "b" * 24 + " a.py:1", RO.REDACTED + " a.py:1"),
    ("no citation, key " + _KEY, "no citation, key " + RO.REDACTED),
])
def test_decline_reason_keeps_citations_whole(tmp_path, reason, stored):
    """REQ-722 BR-8: R3 redacts a ``declineReason`` but keeps every citation that checks
    out against ``HEAD``, so a reason that qualified at Step C is still the same reason at
    Phase 6; a credential shaped like a citation is still redacted."""
    checker = RO._sibling("cross_family").DeclineChecker(_cited_repo(tmp_path))
    [entry] = RO.normalize_findings([{"severity": "Major", "file": "a.py", "title": "T",
                                      "source": ["cross-family"], "disposition": "declined",
                                      "declineReason": reason}], checker)
    assert entry["declineReason"] == stored
    assert RO.redact_reason(reason, checker) == stored


def test_decline_reason_without_a_checkout_is_plainly_redacted(tmp_path):
    """No worktree to check against: every chain match is redacted, citations included,
    and record-verify finds the worktree from the state's primary repo."""
    assert RO.redact_reason(_LONG + ":12") == "tools/ri" + RO.REDACTED + ".py:12"
    assert RO.decline_checker(str(tmp_path / "absent.json")) is None
    repo = _cited_repo(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"repos": {"r": {"primary": True, "worktree": repo}}}), encoding="utf-8")
    assert RO.decline_checker(str(state)) is not None
    state.write_text(json.dumps({"repos": {"r": {"primary": True, "worktree": str(tmp_path / "nope")}}}),
                     encoding="utf-8")
    assert RO.decline_checker(str(state)) is None


def test_must_fix_is_kept_and_never_shrinks(tmp_path):
    """check-dispositions refuses ``deferred`` on a must-fix finding, so R3 keeps a
    true ``mustFix`` and a re-record that leaves it out keeps it still. Only
    ``true`` is kept, with or without the REQ-722 fields (Step D: a writer that passes
    it alone must not lose it)."""
    raw = [
        {"severity": "Major", "file": "a.py", "title": "T", "source": ["cross-family"], "mustFix": True},
        {"severity": "Major", "file": "b.py", "title": "U", "source": ["cross-family"], "mustFix": False},
        {"severity": "Major", "file": "c.py", "title": "V", "source": ["cross-family"], "mustFix": "true"},
        {"severity": "Major", "file": "d.py", "title": "W", "mustFix": True},
    ]
    a, b, c, d = RO.normalize_findings(raw)
    assert a["mustFix"] is True and d["mustFix"] is True
    assert all("mustFix" not in e for e in (b, c))
    state = _write(tmp_path, _state())
    assert _verify(state, raw[:1]).returncode == 0
    again = [{"severity": "Major", "file": "a.py", "title": "T", "source": ["cross-family"],
              "disposition": "deferred"}]
    assert _verify(state, again, "--loops", "1").returncode == 0
    [entry] = json.loads(state.read_text())["verify"]["findings"]
    assert entry["mustFix"] is True and entry["disposition"] == "deferred"


def test_normalize_findings_keeps_an_integer_line():
    """REQ-722 TASK-282: a 1-based integer ``line`` is kept, so the PR section and
    check-dispositions can name ``file:line``; anything else is left out."""
    raw = [
        {"severity": "Major", "file": "a.py", "title": "T", "line": 12, "source": ["cross-family"]},
        {"severity": "Major", "file": "b.py", "title": "U", "line": True},
        {"severity": "Major", "file": "c.py", "title": "V", "line": "12"},
        {"severity": "Major", "file": "d.py", "title": "W", "line": 0},
        {"severity": "Major", "file": "e.py", "title": "X", "line": 3.0},
        {"severity": "Major", "file": "f.py", "title": "Y"},
    ]
    a, *rest = RO.normalize_findings(raw)
    assert a["line"] == 12
    assert list(a) == ["severity", "file", "title", "class", "fixed", "line", "source"]
    assert all("line" not in entry for entry in rest)


def test_dedupe_key_matches_the_workflow_engine():
    """The carry-forward key is the workflow engine's dedupeKey(): file plus the
    title lowercased, whitespace runs collapsed, ends trimmed."""
    cases = [
        {"file": "a.py", "title": "Missing  Guard"},
        {"file": "a.py", "title": "\tmissing guard \n"},
        {"file": "a.py", "title": "missing guard﻿"},
        {"file": "a.py", "title": "missing  guard"},
        {"file": "b.py", "title": "missing guard"},
        {"file": "a.py"},
        {"title": "Only A Title"},
    ]
    keys = [RO.dedupe_key(c) for c in cases]
    assert keys[0] == keys[1] == keys[2] == keys[3] == ("a.py", "missing guard")
    assert keys[4] != keys[0] and keys[5] == ("a.py", "") and keys[6] == ("", "only a title")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed: the parity half needs it")
    loader = REPO_ROOT / "workflows" / "tests" / "_load-pure.js"
    workflow = REPO_ROOT / "workflows" / "adlc-sprint.workflow.js"
    script = ("const h = require(process.argv[1])(process.argv[2]);"
              "const cases = JSON.parse(process.argv[3]);"
              "process.stdout.write(JSON.stringify(cases.map((c) => h.dedupeKey(c).split('\\x00'))));")
    out = subprocess.run([node, "-e", script, str(loader), str(workflow), json.dumps(cases)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert [tuple(k) for k in json.loads(out.stdout)] == keys


def test_rerecord_keeps_decline(tmp_path):
    """BR-8: an R3 re-record that omits `disposition` does not erase a decline
    recorded earlier for the same dedupe key, nor its reason, nor who raised the
    finding; a new disposition replaces the old one; another key inherits nothing."""
    state = _write(tmp_path, _state())
    first = [
        {"severity": "Major", "file": "src/a.py", "title": "Missing bounds check", "class": "a-b",
         "source": ["cross-family"], "disposition": "declined",
         "declineReason": "src/a.py:12 clamps the index before the read"},
        {"severity": "Minor", "file": "src/b.py", "title": "Unused import", "source": ["panel"]},
        {"severity": "Minor", "file": "src/c.py", "title": "Stale comment",
         "source": ["cross-family"], "disposition": "declined", "declineReason": "src/c.py:4 says so"},
    ]
    assert _verify(state, first).returncode == 0
    # Step D's re-record: the same findings, reworded in case and spacing, with no
    # disposition, no reason and only the panel named; one now fixed; one new.
    second = [
        {"severity": "Major", "file": "src/a.py", "title": "  missing   BOUNDS check", "class": "a-b",
         "source": ["panel"], "fixed": False},
        {"severity": "Minor", "file": "src/b.py", "title": "Unused import", "fixed": True},
        {"severity": "Minor", "file": "src/c.py", "title": "Stale comment", "disposition": "fixed",
         "fixed": True},
        {"severity": "Nit", "file": "src/d.py", "title": "Missing bounds check"},
    ]
    out = _verify(state, second, "--loops", "1")
    assert out.returncode == 0, out.stderr
    a, b, c, d = json.loads(state.read_text())["verify"]["findings"]
    assert a["disposition"] == "declined"
    assert a["declineReason"] == "src/a.py:12 clamps the index before the read"
    assert a["source"] == ["cross-family", "panel"], "who raised it never shrinks"
    assert a["title"] == "  missing   BOUNDS check", "the new entry's own fields are kept"
    assert b["source"] == ["panel"] and "disposition" not in b
    assert c["disposition"] == "fixed" and "declineReason" not in c, "a new disposition wins, alone"
    assert not any(k in d for k in ("source", "disposition", "declineReason")), "another file"
    # and a third re-record that omits everything keeps the decline still
    assert _verify(state, [{"severity": "Major", "file": "src/a.py", "title": "Missing bounds check"}]
                   ).returncode == 0
    [again] = json.loads(state.read_text())["verify"]["findings"]
    assert (again["disposition"], again["source"]) == ("declined", ["cross-family", "panel"])
    assert again["declineReason"] == "src/a.py:12 clamps the index before the read"


def test_declined_count_is_derived_from_verify(tmp_path):
    """`declinedCount` follows `verify` on every record write: a skip declined
    nothing; with one repo ran, every cross-family decline is its; with two, a
    finding names no repo, so their counts are left as they were."""
    state = _write(tmp_path, _state())
    run = ["--status", "ran", "--implementer", "anthropic", "--reviewer", "moonshot"]
    assert _xfam(state, "--repo", "api", *run, "--findings", "2").returncode == 0
    assert _xfam(state, "--repo", "web", "--status", "skipped", "--reason", "no-binary",
                 "--implementer", "anthropic", "--reviewer", "unknown").returncode == 0
    findings = [
        {"severity": "Major", "file": "a", "title": "a", "source": ["cross-family"],
         "disposition": "declined", "declineReason": "a:1"},
        {"severity": "Major", "file": "b", "title": "b", "source": ["panel", "cross-family"],
         "disposition": "declined", "declineReason": "b:1"},
        {"severity": "Major", "file": "c", "title": "c", "source": ["panel"], "disposition": "declined",
         "declineReason": "c:1"},
    ]
    assert _verify(state, findings).returncode == 0
    reviews = json.loads(state.read_text())["crossFamilyReview"]
    assert reviews["api"]["declinedCount"] == 2, "panel-only declines are not the reviewer's"
    assert reviews["web"]["declinedCount"] == 0
    # a re-run of the record keeps the derived count
    assert _xfam(state, "--repo", "api", *run, "--findings", "2").returncode == 0
    assert json.loads(state.read_text())["crossFamilyReview"]["api"]["declinedCount"] == 2
    # a second repo that ran: no attribution, nothing overwritten
    assert _xfam(state, "--repo", "web", *run).returncode == 0
    assert _verify(state, findings[:1]).returncode == 0
    reviews = json.loads(state.read_text())["crossFamilyReview"]
    assert (reviews["api"]["declinedCount"], reviews["web"]["declinedCount"]) == (2, 0)


def test_cross_family_counts_from_state(tmp_path):
    """BR-13: the line's `crossFamily` object is derived from the state file:
    per repo the status and reason, and over `verify` the cross-family findings,
    those the panel did not raise, and how many were fixed and declined. Emit
    takes no flag for any of it, so the model cannot supply a count."""
    state = _state(
        crossFamilyReview={
            "web": {"status": "skipped", "reason": "same-family", "findingCount": 9},
            "api": {"status": "ran", "reason": "same-family", "findingCount": 9, "declinedCount": 9},
            "bad/id": {"status": "ran"},
            "odd": {"status": "maybe", "reason": "too-slow"},
            "lost": {"status": "skipped", "reason": "too-slow"},
        },
        verify={"findings": [
            {"severity": "Major", "file": "a", "title": "a", "source": ["cross-family"], "fixed": True},
            {"severity": "Minor", "file": "b", "title": "b", "source": ["cross-family", "panel"],
             "fixed": True, "disposition": "declined", "declineReason": "b:1"},
            {"severity": "Minor", "file": "c", "title": "c", "source": ["cross-family"],
             "disposition": "deferred"},
            {"severity": "Nit", "file": "d", "title": "d", "source": ["cross-family"],
             "disposition": "fixed"},
            {"severity": "Nit", "file": "e", "title": "e", "source": ["panel"], "fixed": True},
            {"severity": "Nit", "file": "f", "title": "f", "fixed": True},
        ], "loops": 1},
    )
    out = _run("emit", "--state", str(_write(tmp_path, state)), "--terminal", "merged", "--engine", "solo")
    assert out.returncode == 0, out.stderr
    rec = assert_structural(out.stdout)
    assert list(rec) == list(RO.KEYS)
    assert rec["crossFamily"] == {
        "findings": "4", "cross_only": "3", "fixed": "2", "declined": "1",
        "repos": {
            "api": {"status": "ran", "reason": "-"},
            "lost": {"status": "skipped", "reason": "-"},
            "odd": {"status": "-", "reason": "-"},
            "web": {"status": "skipped", "reason": "same-family"},
        },
    }
    assert out.stdout.rstrip("\n").endswith("}}}"), "the object is the line's last key"
    assert _run("emit", "--state", str(tmp_path / "pipeline-state.json"), "--terminal", "merged",
                "--engine", "solo", "--cross-family", "x").returncode == 2

    # cross-family findings with no record still count; a record with no findings reports zeros
    only_findings = RO.build_record(_state(verify=state["verify"]), "merged", "solo", now=NOW)
    assert only_findings["crossFamily"]["findings"] == "4" and only_findings["crossFamily"]["repos"] == {}
    skipped = _state(crossFamilyReview={"api": {"status": "skipped", "reason": "subagent-mode"}})
    assert RO.build_record(skipped, "merged", "solo", now=NOW)["crossFamily"] == {
        "findings": "0", "cross_only": "0", "fixed": "0", "declined": "0",
        "repos": {"api": {"status": "skipped", "reason": "subagent-mode"}}}
    # panel-only sources and an empty record are nothing to report
    panel = _state(crossFamilyReview={}, verify={"findings": [{"title": "x", "source": ["panel"]}]})
    assert "crossFamily" not in RO.build_record(panel, "merged", "solo", now=NOW)


#: The emitted line for PRE_REQ722_STATE, captured from run_outcome.py as it stood
#: before REQ-722 (commit 2e99a38).
PRE_REQ722_LINE = (
    '{"timestamp":"2026-10-29T12:00:00Z","skill":"proceed","step":"run-outcome","req":"REQ-648",'
    '"repo":"adlc-toolkit","engine":"solo","toolkit_version":"5.4.0","toolkit_sha":"c013262",'
    '"terminal":"merged","blocked_reason":"","validate_retries":"1","verify_loops":"1",'
    '"findings_critical":"0","findings_major":"1","findings_minor":"0","findings_nit":"1",'
    '"finding_classes":"unanchored-marker-regex,LESSON-390","lessons_cited":"LESSON-012,LESSON-571",'
    '"lessons_written":"LESSON-740","elapsed_s":"3600"}'
)
PRE_REQ722_STATE = _state(
    harness={"version": "5.4.0", "sha": "c013262"},
    validateAttempts={"phase1": 2, "phase3": 1},
    verify={"findings": [
        {"severity": "Major", "file": "a.py", "title": "Unquoted path", "class": "unanchored-marker-regex",
         "fixed": True},
        {"severity": "Nit", "file": "b.md", "title": "u", "class": "LESSON-390", "lessonId": "LESSON-390",
         "fixed": False},
    ], "loops": 1, "consolidatedAt": "2026-10-29T11:30:00Z"},
    lessons={"acknowledged": {"ids": ["LESSON-012", "LESSON-571"]}},
    lessonsWritten=["LESSON-740"],
    closeOut={"status": "ok"},
)


def test_pre_req_state_reports_unchanged(tmp_path, monkeypatch):
    """AC-15: a state file written before REQ-722 emits the line it always did,
    byte for byte, its findings re-record to the same entries, and neither path
    needs cross_family.py or model_family.py at all."""
    def unavailable(name):
        raise AssertionError(f"a pre-REQ-722 state loaded {name}.py")

    monkeypatch.setattr(RO, "_sibling", unavailable)
    assert RO.encode(RO.build_record(PRE_REQ722_STATE, "merged", "solo", now=NOW)) == PRE_REQ722_LINE
    raw = [{"severity": "high", "file": "a.py", "title": "T", "class": "x-y", "fixed": True,
            "lessonId": "LESSON-390", "extra": 1}]
    assert RO.normalize_findings(raw) == [{"severity": "Major", "file": "a.py", "title": "T",
                                           "class": "LESSON-390", "fixed": True, "lessonId": "LESSON-390"}]
    prior = PRE_REQ722_STATE["verify"]["findings"]
    assert RO.carry_forward(RO.normalize_findings(prior), prior) == RO.normalize_findings(prior)
    data = json.loads(json.dumps(PRE_REQ722_STATE))
    RO.sync_declined(data)
    assert data == PRE_REQ722_STATE
    monkeypatch.undo()
    # end to end: a record-verify of the same findings leaves verify as it was, but the stamp
    state = _write(tmp_path, PRE_REQ722_STATE)
    assert _verify(state, prior, "--loops", "1").returncode == 0
    after = json.loads(state.read_text())
    assert after["verify"]["findings"] == prior and "crossFamilyReview" not in after
    assert {k: v for k, v in after.items() if k != "verify"} == {
        k: v for k, v in PRE_REQ722_STATE.items() if k != "verify"}
