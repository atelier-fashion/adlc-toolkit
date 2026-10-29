#!/usr/bin/env python3
"""run_outcome.py — the deterministic RunOutcome emitter and its state writers (REQ-648).

One JSON line per pipeline terminal, derived by code from the primary-path
``pipeline-state.json`` rather than from the model's recollection (LESSON-012).
The model supplies only what exists nowhere else: the terminal tag, the engine,
a halt reason, and the consolidated Phase-5 findings (they live in the
conversation). Every count, class, retry total, the elapsed time, the toolkit
stamp and the redaction are computed here.

Subcommands::

    emit --state S --terminal T --engine E [--reason R] [--req REQ-xxx]
        Print one flat JSON line (every value a string; counts are quoted
        decimals or "-"). ``emit-run-outcome.sh`` appends it to the log.
    record-harness --state S --toolkit-root DIR [--fresh]
        Write ``harness: {version, sha}`` once; on a resume an existing one is
        kept (BR-10, never re-read). ``--fresh`` — a fresh Step 0, decided from
        the progress record exactly as ``adlc_lessons --fresh`` is (LESSON-719),
        never from whether the key exists — re-stamps it and clears the
        ``validateAttempts``, ``verify`` and ``lessonsWritten`` an earlier run of
        the same REQ left in the primary-path copy.
    record-validate --state S --phase 1|3 --attempt N
        Set ``validateAttempts.phase<N>`` to max(existing, N): absolute and
        monotone, so a replay or a repeated call never double-counts.
    record-verify --state S --findings FILE|- [--loops N]
        Normalise the findings (severity scale, BR-6 class tiers, ``fixed``)
        and replace ``verify.findings``; stamp ``consolidatedAt``.
    record-lessons-written --state S (--ids LESSON-a,LESSON-b | --no-entry)
        Record ``/wrapup``'s ``### Lessons captured`` outcome.
    record-carry --state S --from W
        Copy every top-level key of W (the worktree copy) that S (the
        primary-path copy) lacks into S, before teardown deletes W. S's own keys
        win, so the records above, ``lessons`` and the terminal record survive.

Exit codes: 0 ok; 1 a state file that cannot be read or written; 2 usage.
Every state write is atomic (tempfile in the same directory + ``os.replace``)
and merge-preserving: it reads the file, sets one key, and writes the rest back
unchanged — the ``tools/adlc/lessons.py`` ``write_state`` pattern.

Stdlib only: the plugin route runs it with the system ``python3``.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

# --- vocabularies ------------------------------------------------------------

TERMINALS = ("merged", "pr-ready", "blocked", "failed")
ENGINES = ("solo", "legacy", "workflow")
BLOCKED_REASONS = (
    "validation-exhausted", "reflector-questions", "merge-conflict",
    "merge-unverified", "close-out-failed", "setup-error", "no-worktree",
    "no-pr", "other",
)
SEVERITIES = ("Critical", "Major", "Minor", "Nit")
# Agents that use a High/Medium/Low scale map on emission (REQ-648 Entities).
SEVERITY_MAP = {
    "critical": "Critical", "major": "Major", "minor": "Minor", "nit": "Nit",
    "high": "Major", "medium": "Minor", "low": "Nit", "info": "Nit",
}

# The documented key list, in emission order. The structural test pins it.
KEYS = (
    "timestamp", "skill", "step", "req", "repo", "engine", "toolkit_version",
    "toolkit_sha", "terminal", "blocked_reason", "validate_retries",
    "verify_loops", "findings_critical", "findings_major", "findings_minor",
    "findings_nit", "finding_classes", "lessons_cited", "lessons_written",
    "elapsed_s",
)
COUNT_KEYS = (
    "validate_retries", "verify_loops", "findings_critical", "findings_major",
    "findings_minor", "findings_nit",
)

# A finding's class (BR-6): a reviewer-emitted pattern name, a lesson id, or a
# title slug. The format admits no credential shape, which is why the class is
# exempt from free-text redaction.
REVIEWER_CLASS_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,5}\Z")
LESSON_ID_RE = re.compile(r"^LESSON-[0-9]{3,6}\Z")
TITLE_SLUG_RE = re.compile(r"^title-slug:[a-z0-9-]+\Z")
CLASS_RE = re.compile(
    r"^([a-z0-9]+(-[a-z0-9]+){0,5}|LESSON-[0-9]{3,6}|title-slug:[a-z0-9-]+)\Z")
REQ_ID_RE = re.compile(r"^REQ-[0-9]{3,6}\Z")
VERSION_RE = re.compile(r"^[0-9A-Za-z._+-]{1,64}\Z")
SHA_RE = re.compile(r"^[0-9a-f]{4,40}\Z")

# The five-arm chain of tools/delegate/emit-telemetry.sh (REQ-415), with
# [[:space:]] written \s. test_run_outcome.py runs the real sed line against
# this copy on a fixture (LESSON-441 — two copies drift; the test is the
# guard). REQ-671's tools/adlc/credential_redact.INTAKE_PATTERN is the same
# chain: whichever of the two REQs lands second points this module at it.
REDACT_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}"
    r"|Bearer [A-Za-z0-9._-]{20,}"
    r"|[A-Z_]+_(API_KEY|TOKEN)\s*[=:]\s*[^\s]+)"
)
REDACTED = "[REDACTED]"


class RunOutcomeError(Exception):
    """A state file that cannot be read or written (rc 1)."""


class UsageError(Exception):
    """A bad argument (rc 2)."""


# --- pure helpers ------------------------------------------------------------

def redact(text):
    """Replace every credential-shaped run with ``[REDACTED]``."""
    return REDACT_RE.sub(REDACTED, text if isinstance(text, str) else str(text))


def as_int(value):
    """``value`` as a non-negative int, or None. Booleans are not counts."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def normalize_severity(value):
    """Map any agent's severity onto Critical|Major|Minor|Nit; unknown → Minor."""
    if isinstance(value, str):
        mapped = SEVERITY_MAP.get(value.strip().lower())
        if mapped:
            return mapped
    return "Minor"


def title_slug(title):
    """``title-slug:<slug>`` of a free-form title: at most six lowercase words."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())[:6]
    return "title-slug:" + ("-".join(words) if words else "untitled")


def finding_class(finding):
    """BR-6 class, in tier order: the matched lesson id, the reviewer-emitted
    class, then a slug of the title. Every result matches ``CLASS_RE``."""
    lesson = finding.get("lessonId")
    if isinstance(lesson, str) and LESSON_ID_RE.match(lesson):
        return lesson
    cls = finding.get("class")
    if isinstance(cls, str):
        if REVIEWER_CLASS_RE.match(cls) or LESSON_ID_RE.match(cls) or TITLE_SLUG_RE.match(cls):
            return cls
    return title_slug(finding.get("title"))


def class_tier(cls):
    """``lesson`` | ``title-slug`` | ``reviewer`` — the Recurrence row label."""
    if LESSON_ID_RE.match(cls):
        return "lesson"
    if cls.startswith("title-slug:"):
        return "title-slug"
    return "reviewer"


def normalize_blocked_reason(reason):
    """Map a halt reason — a solo token or the workflow's free text — onto the
    closed ``blocked_reason`` enum (BR-5). Empty stays empty."""
    text = (reason or "").strip().lower()
    if not text:
        return ""
    if text in BLOCKED_REASONS:
        return text
    if text.endswith("-validation") or text.startswith("validation"):
        return "validation-exhausted"
    if text.startswith("reflector"):
        return "reflector-questions"
    if text in ("needs-manual-rebase", "trial-merge") or text.startswith("merge-conflict") \
            or text.startswith("merge conflict"):
        return "merge-conflict"
    if text.startswith("merge-unverified") or "could not be verified" in text:
        return "merge-unverified"
    if text in ("phase0-no-worktree", "no-worktree"):
        return "no-worktree"
    if text in ("phase8-no-pr", "no-pr"):
        return "no-pr"
    if text in ("phase8-no-repo", "setup-error") or text.startswith("setup"):
        return "setup-error"
    if text.startswith("close-out"):
        return "close-out-failed"
    return "other"


def validate_retries(attempts):
    """Σ max(attempts − 1, 0) over phase1 and phase3; a phase that never ran,
    or a value that is not a count, contributes 0."""
    if not isinstance(attempts, dict):
        return 0
    total = 0
    for key in ("phase1", "phase3"):
        n = as_int(attempts.get(key))
        if n:
            total += max(n - 1, 0)
    return total


def _iso_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def _primary_repo(state):
    repos = state.get("repos")
    if not isinstance(repos, dict) or not repos:
        return None
    for rec in repos.values():
        if isinstance(rec, dict) and rec.get("primary") is True:
            return rec
    first = next(iter(repos.values()))
    return first if isinstance(first, dict) else None


def _repo_name(state):
    rec = _primary_repo(state) or {}
    path = rec.get("path") if isinstance(rec.get("path"), str) else ""
    if not path:
        return "-"
    path = re.sub(r"/\.worktrees/.*$", "", path.rstrip("/"))
    return os.path.basename(path) or "-"


def _ids(values):
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, list):
        return []
    out = []
    for v in values:
        v = v.strip() if isinstance(v, str) else ""
        if LESSON_ID_RE.match(v) and v not in out:
            out.append(v)
    return out


def _findings(state):
    verify = state.get("verify")
    if not isinstance(verify, dict):
        return []
    found = verify.get("findings")
    return [f for f in found if isinstance(f, dict)] if isinstance(found, list) else []


def build_record(state, terminal, engine, reason="", req=None, now=None):
    """The RunOutcome dict for ``state`` — every value a string, keys in KEYS order."""
    if terminal not in TERMINALS:
        raise UsageError(f"--terminal must be one of {', '.join(TERMINALS)}")
    if engine not in ENGINES:
        raise UsageError(f"--engine must be one of {', '.join(ENGINES)}")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state = state if isinstance(state, dict) else {}

    req_id = state.get("req") if isinstance(state.get("req"), str) else (req or "")
    req_id = req_id if REQ_ID_RE.match(req_id or "") else "-"

    harness = state.get("harness") if isinstance(state.get("harness"), dict) else {}
    version = harness.get("version") if isinstance(harness.get("version"), str) else ""
    sha = harness.get("sha") if isinstance(harness.get("sha"), str) else ""

    if terminal in ("blocked", "failed"):
        blocked = normalize_blocked_reason(reason)
    else:
        close_out = state.get("closeOut") if isinstance(state.get("closeOut"), dict) else {}
        blocked = "close-out-failed" if close_out.get("status") == "failed" else ""

    verify = state.get("verify") if isinstance(state.get("verify"), dict) else {}
    loops = as_int(verify.get("loops"))
    findings = _findings(state)
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[normalize_severity(f.get("severity"))] += 1

    lessons = state.get("lessons") if isinstance(state.get("lessons"), dict) else {}
    acked = lessons.get("acknowledged") if isinstance(lessons.get("acknowledged"), dict) else {}

    written = state.get("lessonsWritten")
    if written == "NO_ENTRY":
        lessons_written = "NO_ENTRY"
    else:
        lessons_written = ",".join(_ids(written))

    started = _parse_iso(state.get("startedAt"))
    elapsed = str(max(int((now - started).total_seconds()), 0)) if started else "-"

    record = {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill": "proceed",
        "step": "run-outcome",
        "req": req_id,
        "repo": redact(_repo_name(state)),
        "engine": engine,
        "toolkit_version": redact(version) if VERSION_RE.match(version) else "-",
        "toolkit_sha": sha if SHA_RE.match(sha) else "-",
        "terminal": terminal,
        "blocked_reason": blocked,
        "validate_retries": str(validate_retries(state.get("validateAttempts"))),
        "verify_loops": str(loops if loops is not None else 0),
        "findings_critical": str(counts["Critical"]),
        "findings_major": str(counts["Major"]),
        "findings_minor": str(counts["Minor"]),
        "findings_nit": str(counts["Nit"]),
        "finding_classes": ",".join(finding_class(f) for f in findings),
        "lessons_cited": ",".join(_ids(acked.get("ids"))),
        "lessons_written": lessons_written,
        "elapsed_s": elapsed,
    }
    return {k: record[k] for k in KEYS}


def encode(record):
    """One line of compact JSON; ``ensure_ascii`` keeps it a single line."""
    return json.dumps(record, ensure_ascii=True, separators=(",", ":"))


def normalize_findings(raw):
    """The ``verify.findings`` entries for a list of consolidated findings."""
    if not isinstance(raw, list):
        raise UsageError("--findings must be a JSON array of finding objects")
    out = []
    for f in raw:
        if not isinstance(f, dict):
            raise UsageError("--findings must be a JSON array of finding objects")
        entry = {
            "severity": normalize_severity(f.get("severity")),
            "file": f.get("file") if isinstance(f.get("file"), str) else "",
            "title": f.get("title") if isinstance(f.get("title"), str) else "",
            "class": finding_class(f),
            "fixed": f.get("fixed") is True,
        }
        lesson = f.get("lessonId")
        if isinstance(lesson, str) and LESSON_ID_RE.match(lesson):
            entry["lessonId"] = lesson
        out.append(entry)
    return out


# --- state I/O ----------------------------------------------------------------

def read_state(path, missing_ok=False):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise RunOutcomeError(f"state file not found: {path}")
    except (OSError, ValueError) as exc:
        raise RunOutcomeError(f"cannot read state file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RunOutcomeError(f"state file {path} is not a JSON object")
    return data


def write_state(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise RunOutcomeError(f"state directory does not exist: {directory}")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory,
                                         prefix=".pipeline-state.", suffix=".tmp", delete=False)
    try:
        with handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(handle.name, path)
    except OSError as exc:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise RunOutcomeError(f"cannot write state file {path}: {exc}") from exc


def _update(path, mutate):
    data = read_state(path)
    mutate(data)
    write_state(path, data)
    return data


def read_harness(toolkit_root):
    """``{version, sha}`` of the toolkit at ``toolkit_root``; ``-`` when unresolvable."""
    version = "-"
    try:
        with open(os.path.join(toolkit_root, "VERSION"), encoding="utf-8") as handle:
            candidate = handle.read().strip()
        if VERSION_RE.match(candidate):
            version = candidate
    except OSError:
        pass
    sha = "-"
    # Only ToolkitRoot's OWN checkout counts: `git -C` walks up, so a root with
    # no `.git` (the plugin cache copy) inside a git-tracked HOME would
    # otherwise report the enclosing repo's sha. A linked worktree's `.git` is
    # a file, hence `exists`, not `isdir`.
    if os.path.isdir(toolkit_root) and os.path.exists(os.path.join(toolkit_root, ".git")):
        try:
            out = subprocess.run(["git", "-C", toolkit_root, "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=10)
            candidate = out.stdout.strip()
            if out.returncode == 0 and SHA_RE.match(candidate):
                sha = candidate
        except (OSError, subprocess.SubprocessError):
            pass
    return {"version": version, "sha": sha}


# --- commands -----------------------------------------------------------------

def cmd_emit(args):
    state = read_state(args.state, missing_ok=bool(args.req))
    if state is None:
        state = {}
    print(encode(build_record(state, args.terminal, args.engine, args.reason or "", args.req)))
    return 0


RUN_KEYS = ("validateAttempts", "verify", "lessonsWritten")


def cmd_record_harness(args):
    result = {}

    def mutate(data):
        if args.fresh:
            for key in RUN_KEYS:
                data.pop(key, None)
        current = data.get("harness")
        if args.fresh or not (isinstance(current, dict) and "version" in current and "sha" in current):
            data["harness"] = read_harness(args.toolkit_root)
        result.update(data["harness"])

    _update(args.state, mutate)
    print(f"harness: {result.get('version', '-')} {result.get('sha', '-')}")
    return 0


def cmd_record_validate(args):
    attempt = as_int(args.attempt)
    if not attempt:
        raise UsageError("--attempt must be a positive integer")
    key = f"phase{args.phase}"

    def mutate(data):
        attempts = data.get("validateAttempts")
        if not isinstance(attempts, dict):
            attempts = {}
        attempts[key] = max(as_int(attempts.get(key)) or 0, attempt)
        attempts.setdefault("phase1", 0)
        attempts.setdefault("phase3", 0)
        data["validateAttempts"] = attempts

    data = _update(args.state, mutate)
    print(f"validateAttempts: phase1={data['validateAttempts']['phase1']} "
          f"phase3={data['validateAttempts']['phase3']}")
    return 0


def cmd_record_verify(args):
    try:
        if args.findings == "-":
            raw = json.load(sys.stdin)
        else:
            with open(args.findings, encoding="utf-8") as handle:
                raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise UsageError(f"--findings is not readable JSON: {exc}") from exc
    findings = normalize_findings(raw)
    loops = None
    if args.loops is not None:
        loops = as_int(args.loops)
        if loops is None:
            raise UsageError("--loops must be a non-negative integer")

    def mutate(data):
        current = data.get("verify") if isinstance(data.get("verify"), dict) else {}
        kept = as_int(current.get("loops"))
        data["verify"] = {
            "findings": findings,
            "loops": loops if loops is not None else (kept if kept is not None else 0),
            "consolidatedAt": _iso_now(),
        }

    data = _update(args.state, mutate)
    v = data["verify"]
    fixed = sum(1 for f in v["findings"] if f["fixed"])
    print(f"verify: {len(v['findings'])} finding(s), {fixed} fixed, loops={v['loops']}")
    return 0


def cmd_record_carry(args):
    source = read_state(args.source)
    carried = []

    def mutate(data):
        for key, value in source.items():
            if key not in data:
                data[key] = value
                carried.append(key)

    _update(args.state, mutate)
    print("carried: " + (", ".join(carried) if carried else "(nothing — every key already present)"))
    return 0


def cmd_record_lessons_written(args):
    if args.no_entry:
        value = "NO_ENTRY"
    else:
        value = _ids(args.ids or "")
        bad = [t for t in (args.ids or "").split(",") if t.strip() and not LESSON_ID_RE.match(t.strip())]
        if bad:
            raise UsageError(f"--ids holds a value that is not a LESSON-nnn id: {bad[0]!r}")

    def mutate(data):
        data["lessonsWritten"] = value

    _update(args.state, mutate)
    print("lessonsWritten: " + (value if isinstance(value, str) else (",".join(value) or "(none)")))
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _parser():
    p = _Parser(prog="run_outcome.py", add_help=False)
    sub = p.add_subparsers(dest="command", parser_class=_Parser)
    e = sub.add_parser("emit", add_help=False)
    e.add_argument("--state", required=True)
    e.add_argument("--terminal", required=True)
    e.add_argument("--engine", required=True)
    e.add_argument("--reason", default="")
    e.add_argument("--req")
    h = sub.add_parser("record-harness", add_help=False)
    h.add_argument("--state", required=True)
    h.add_argument("--toolkit-root", required=True)
    h.add_argument("--fresh", action="store_true")
    v = sub.add_parser("record-validate", add_help=False)
    v.add_argument("--state", required=True)
    v.add_argument("--phase", required=True, choices=("1", "3"))
    v.add_argument("--attempt", required=True)
    f = sub.add_parser("record-verify", add_help=False)
    f.add_argument("--state", required=True)
    f.add_argument("--findings", required=True)
    f.add_argument("--loops")
    w = sub.add_parser("record-lessons-written", add_help=False)
    w.add_argument("--state", required=True)
    group = w.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids")
    group.add_argument("--no-entry", action="store_true")
    c = sub.add_parser("record-carry", add_help=False)
    c.add_argument("--state", required=True)
    c.add_argument("--from", dest="source", required=True)
    return p


COMMANDS = {
    "emit": cmd_emit,
    "record-harness": cmd_record_harness,
    "record-validate": cmd_record_validate,
    "record-verify": cmd_record_verify,
    "record-lessons-written": cmd_record_lessons_written,
    "record-carry": cmd_record_carry,
}


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.command not in COMMANDS:
            raise UsageError("usage: run_outcome.py emit|record-harness|record-validate|"
                             "record-verify|record-lessons-written|record-carry …")
        return COMMANDS[args.command](args)
    except UsageError as exc:
        print(f"run-outcome: {exc}", file=sys.stderr)
        return 2
    except RunOutcomeError as exc:
        print(f"run-outcome: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
