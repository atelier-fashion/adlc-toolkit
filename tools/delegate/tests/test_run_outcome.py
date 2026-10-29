"""Tests for tools/delegate/run_outcome.py — the RunOutcome emitter (REQ-648).

The structural test validates an emitted line against the documented key list
(BR-9): every key present, every value a string (no nested object, no array),
every count a quoted decimal or ``-``, every enum in its vocabulary. The other
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
    """BR-9: the documented key list, flat scalars, counts quoted, enums closed."""
    assert "\n" not in line.strip()
    record = json.loads(line)
    assert list(record) == list(RO.KEYS), "every documented key, in order, nothing else"
    for key, value in record.items():
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
    # git may walk up into an enclosing repo; tmp_path is outside any checkout
    assert harness["sha"] == "-" or RO.SHA_RE.match(harness["sha"])
    missing = _write(tmp_path, _state(), name="b.json")
    _run("record-harness", "--state", str(missing), "--toolkit-root", str(tmp_path / "nowhere"))
    assert json.loads(missing.read_text())["harness"] == {"version": "-", "sha": "-"}


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
                                    lessonsWritten="NO_ENTRY", lessons={"step0": {}}))
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
    for key in ("validateAttempts", "verify", "lessonsWritten"):
        assert key not in fresh, key
    assert fresh["lessons"] == {"step0": {}} and fresh["req"] == "REQ-648"
