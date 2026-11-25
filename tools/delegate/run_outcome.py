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
        Print one JSON line (every value a string; counts are quoted decimals
        or "-"). ``emit-run-outcome.sh`` appends it to the log.
        ``--terminal rejected`` is a usage error with any engine but ``exec``,
        and its line has an empty ``blocked_reason`` (REQ-719 BR-18). The one
        nested value is the optional ``crossFamily`` object, last, present only
        when the state recorded a cross-family review (REQ-722 BR-13), so a
        line for a state written before REQ-722 is unchanged.
    record-harness --state S --toolkit-root DIR [--fresh]
        Write ``harness: {version, sha}`` once; on a resume an existing one is
        kept (BR-10, never re-read). ``--fresh`` — a fresh Step 0, decided from
        the progress record exactly as ``adlc_lessons --fresh`` is (LESSON-719),
        never from whether the key exists — re-stamps it and clears the
        ``validateAttempts``, ``verify``, ``lessonsWritten`` and
        ``crossFamilyReview`` an earlier run of the same REQ left in the
        primary-path copy.
    record-validate --state S --phase 1|3 --attempt N
        Set ``validateAttempts.phase<N>`` to max(existing, N): absolute and
        monotone, so a replay or a repeated call never double-counts.
    record-verify --state S --findings FILE|- [--loops N]
        Normalise the findings (severity scale, BR-6 class tiers, ``fixed``,
        an integer ``line``, and REQ-722's ``source``, ``disposition``,
        ``declineReason`` and a true ``mustFix``) and
        replace ``verify.findings``; stamp ``consolidatedAt``. A finding that
        omits ``disposition`` or ``declineReason`` takes them from the earlier
        entry with the same dedupe key, its ``source`` is the union of both,
        and a ``mustFix: true`` is kept, so a later re-record cannot erase a
        decline or make a must-fix finding deferrable (REQ-722 BR-8).
    record-cross-family --state S --repo ID --status ran|skipped [--reason R]
                        --implementer F --reviewer F [--findings N] [--dropped N]
        Write ``crossFamilyReview.<repo>`` at the moment the review runs or
        skips (REQ-722 BR-5). ``--reason`` is required exactly when skipped
        and must be one of ``cross_family.SKIP_REASONS``; both families must be
        members of the ``model_family`` enum. Every value is a constrained id
        or a count, validated and never redacted (LESSON-744).
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
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

# --- vocabularies ------------------------------------------------------------

TERMINALS = ("merged", "pr-ready", "blocked", "failed", "rejected")
ENGINES = ("solo", "legacy", "workflow", "exec")
# `rejected` is a person declining a PR at the exec engine's merge gate
# (REQ-719 BR-18). Only that engine has the gate, so only it may write this
# terminal: the check names the one engine allowed, and any engine added later
# starts refused.
REJECTED_ENGINE = "exec"
BLOCKED_REASONS = (
    "validation-exhausted", "reflector-questions", "merge-conflict",
    "merge-unverified", "close-out-failed", "setup-error", "no-worktree",
    "no-pr", "aborted", "cross-family-dispositions", "other",
)
# Reasons only the exec engine writes: its `abort` verb ended the run (REQ-719 BR-19).
EXEC_ONLY_REASONS = ("aborted",)
SEVERITIES = ("Critical", "Major", "Minor", "Nit")
# Agents that use a High/Medium/Low scale map on emission (REQ-648 Entities).
SEVERITY_MAP = {
    "critical": "Critical", "major": "Major", "minor": "Minor", "nit": "Nit",
    "high": "Major", "medium": "Minor", "low": "Nit", "info": "Nit",
}

# The documented key list, in emission order. The structural test pins it.
# `crossFamily` (REQ-722 BR-13) is last, so a reader that finds a flat key by its
# first occurrence never reads a nested one, and it is optional: emitted only when
# the state holds something for it (OPTIONAL_KEYS).
KEYS = (
    "timestamp", "skill", "step", "req", "repo", "engine", "toolkit_version",
    "toolkit_sha", "terminal", "blocked_reason", "validate_retries",
    "verify_loops", "findings_critical", "findings_major", "findings_minor",
    "findings_nit", "finding_classes", "lessons_cited", "lessons_written",
    "elapsed_s", "crossFamily",
)
OPTIONAL_KEYS = ("crossFamily",)
# The counts inside `crossFamily`, in emission order, before its `repos` map.
CROSS_FAMILY_COUNTS = ("findings", "cross_only", "fixed", "declined")
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
# A `crossFamilyReview` key: a repo id as `pipeline-state.json` `repos` names it
# (exec_safety.VALID_REPO_ID's charset). No `"` or `\`, so the run-outcome
# line's awk reader can find it.
REPO_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}\Z")  # the cross-family repo-id charset
# The member a finding's `source` names for the six-agent panel (REQ-722 BR-7);
# the other member is cross_family.SOURCE.
PANEL_SOURCE = "panel"

# The whitespace a JavaScript `\s` and `String.prototype.trim` match, so
# dedupe_key() normalises a title exactly as the workflow engine's dedupeKey().
_JS_SPACE = ("\t\n\v\f\r   " + "".join(chr(c) for c in range(0x2000, 0x200b))
             + "    　﻿")
_JS_SPACE_RUN = re.compile("[" + re.escape(_JS_SPACE) + "]+")


def _load_credential_redact():
    """tools/adlc/credential_redact.py, the toolkit's one Python copy of the
    credential chains (REQ-671 ADR-3), loaded by path from this file's own
    toolkit so nothing is added to ``sys.path``."""
    here = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(os.path.dirname(os.path.dirname(here)), "tools", "adlc", "credential_redact.py")
    spec = importlib.util.spec_from_file_location("adlc_credential_redact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The five-arm chain: credential_redact.INTAKE_PATTERN, the same chain as
# tools/delegate/emit-telemetry.sh's sed line (REQ-415). REQ-671 landed first,
# so this module uses its copy instead of keeping a second one (LESSON-441);
# test_run_outcome.py still runs the real sed line against it.
_CREDENTIALS = _load_credential_redact()
REDACT_RE = _CREDENTIALS.INTAKE_PATTERN
REDACTED = _CREDENTIALS.REPLACEMENT


class RunOutcomeError(Exception):
    """A state file that cannot be read or written (rc 1)."""


_SIBLINGS = {}


def _sibling(name):
    """``tools/delegate/<name>.py``, loaded by path on first use and cached.

    ``cross_family`` holds the REQ-722 vocabularies (``SKIP_REASONS``,
    ``REVIEW_STATUSES``, ``DISPOSITIONS``, ``SOURCE``) and ``model_family`` the
    one ``ModelFamily`` enum: each is read from its owner, never copied. Loaded
    lazily, so a state written before REQ-722 never needs either file, and its
    line is built exactly as before.
    """
    # One of four by-path loaders, kept alike: cross_family._model_family,
    # _machine_config._model_family and tools/adlc/harness_adapter.py's
    # _model_family. A fix to how one loads (or fails to) belongs in all four.
    if name not in _SIBLINGS:
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), name + ".py")
        try:
            spec = importlib.util.spec_from_file_location("adlc_delegate_" + name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError) as exc:
            raise RunOutcomeError(f"cannot load {path}: {exc}") from exc
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


class UsageError(Exception):
    """A bad argument (rc 2)."""


# --- pure helpers ------------------------------------------------------------

def redact(text):
    """Replace every credential-shaped run with ``[REDACTED]``."""
    return REDACT_RE.sub(REDACTED, text if isinstance(text, str) else str(text))


def redact_reason(text, checker=None):
    """A ``declineReason`` redacted, its verified citations kept whole (REQ-722 BR-8).

    ``cross_family.py check-decline`` qualified the reason by its citations and checks
    it again at Phase 6 from what this writes, so a real citation the chain would cut
    into (``tools/risk-assessment-<20 more>.py:12`` holds an ``sk-`` run) must survive.
    A chain match is left alone only when it lies wholly inside a span ``checker``
    (a ``cross_family.DeclineChecker`` over the run's worktree) confirms against
    ``HEAD``: a tracked file with the line in range, or a test the tracked test file
    defines. A credential merely shaped like a citation names nothing the repository
    holds, so it is redacted (Phase-5 Step D security fix). With no ``checker`` (no
    worktree to check against) every match is redacted, as :func:`redact` would.
    """
    text = text if isinstance(text, str) else str(text)
    kept = checker.confirmed_spans(text) if checker is not None else []
    out = []
    at = 0
    for match in REDACT_RE.finditer(text):
        if any(start <= match.start() and match.end() <= end for start, end in kept):
            continue
        out += [text[at:match.start()], REDACTED]
        at = match.end()
    out.append(text[at:])
    return "".join(out)


def decline_checker(state_path):
    """A ``cross_family.DeclineChecker`` over the primary repo's worktree named in the
    state file, or ``None`` when the state names none, or none that is a checkout.
    Only :func:`redact_reason` uses it, and ``None`` there means plain redaction."""
    try:
        with open(state_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    repos = data.get("repos") if isinstance(data, dict) else None
    if not isinstance(repos, dict):
        return None
    for entry in repos.values():
        if isinstance(entry, dict) and entry.get("primary") is True:
            worktree = entry.get("worktree")
            if isinstance(worktree, str) and os.path.isdir(os.path.join(worktree, ".git")) \
                    or isinstance(worktree, str) and os.path.isfile(os.path.join(worktree, ".git")):
                return _sibling("cross_family").DeclineChecker(worktree)
    return None


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


# --- REQ-722: cross-family findings and the review record ---------------------

def dedupe_key(finding):
    """A finding's identity across re-records: its file plus its title lowercased,
    with each whitespace run collapsed to one space and the ends trimmed. The
    workflow engine's ``dedupeKey()`` and Step B's merge use the same key."""
    path = finding.get("file") if isinstance(finding.get("file"), str) else ""
    title = finding.get("title") if isinstance(finding.get("title"), str) else ""
    return (path, _JS_SPACE_RUN.sub(" ", title.lower()).strip(_JS_SPACE))


def finding_sources(value):
    """``source`` as a sorted, de-duplicated list of the closed members, or None.

    A lone string counts as a one-item list, so a cross-family finding cannot
    lose its identity by its shape. Unknown members are dropped, and a value
    with no known member is no ``source`` at all (absent stays absent).
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return None
    allowed = (PANEL_SOURCE, _sibling("cross_family").SOURCE)
    kept = sorted({v for v in value if isinstance(v, str) and v in allowed})
    return kept or None


def finding_extras(finding, checker=None):
    """The REQ-722 fields of one finding, each kept only when valid: ``source``
    (closed members), ``disposition`` (``cross_family.DISPOSITIONS``),
    ``declineReason`` (free text, so redacted, its citations kept:
    :func:`redact_reason`), and ``mustFix`` when it is ``true``, which
    ``check-dispositions`` reads (a must-fix finding is never ``deferred``). A
    finding with none of the first three — every finding written before
    REQ-722 — gets none, and loads nothing."""
    extras = {}
    if not any(k in finding for k in ("source", "disposition", "declineReason")):
        # mustFix alone is kept too, so a writer that passes it without a REQ-722 key
        # never loses it (check-dispositions reads it); nothing else loads.
        if finding.get("mustFix") is True:
            extras["mustFix"] = True
        return extras
    sources = finding_sources(finding.get("source"))
    if sources:
        extras["source"] = sources
    if finding.get("disposition") in _sibling("cross_family").DISPOSITIONS:
        extras["disposition"] = finding["disposition"]
    reason = finding.get("declineReason")
    if isinstance(reason, str) and reason.strip():
        extras["declineReason"] = redact_reason(reason, checker)
    if finding.get("mustFix") is True:
        extras["mustFix"] = True
    return extras


def carry_forward(findings, prior):
    """Keep what an earlier record knew about each finding (REQ-722 BR-8).

    For every new entry, the first earlier entry with the same :func:`dedupe_key`
    supplies ``disposition`` when the new one has none, ``declineReason`` when
    both are ``declined`` and the new one gives no reason, its ``source``
    members, which join the new entry's: who raised a finding never shrinks,
    and ``mustFix: true``, which never shrinks either.
    The earlier values are re-validated, since the state file is data.
    """
    earlier = {}
    for entry in prior if isinstance(prior, list) else []:
        if isinstance(entry, dict):
            earlier.setdefault(dedupe_key(entry), entry)
    for entry in findings:
        old = earlier.get(dedupe_key(entry))
        if old is None:
            continue
        old = finding_extras(old)
        if "source" in old:
            entry["source"] = sorted(set(entry.get("source", [])) | set(old["source"]))
        if "disposition" not in entry and "disposition" in old:
            entry["disposition"] = old["disposition"]
        if old.get("mustFix") is True:
            entry["mustFix"] = True
        if ("declineReason" not in entry and "declineReason" in old
                and entry.get("disposition") == old.get("disposition") == "declined"):
            entry["declineReason"] = old["declineReason"]
    return findings


def _is_cross_family(finding):
    sources = finding_sources(finding.get("source")) if "source" in finding else None
    return bool(sources) and _sibling("cross_family").SOURCE in sources


def _is_fixed(finding):
    """A disposition, when there is one, decides; otherwise the R3 ``fixed`` flag."""
    if "disposition" in finding:
        return finding.get("disposition") == "fixed"
    return finding.get("fixed") is True


def cross_family_counts(state):
    """``{findings, cross_only, fixed, declined}`` over ``verify.findings``: the
    findings whose ``source`` names the cross-family reviewer, those it alone
    raised (the panel did not), and how many were fixed and declined."""
    found = [f for f in _findings(state) if _is_cross_family(f)]
    only = [f for f in found if finding_sources(f.get("source")) == [_sibling("cross_family").SOURCE]]
    return {
        "findings": len(found),
        "cross_only": len(only),
        "fixed": sum(1 for f in found if _is_fixed(f)),
        "declined": sum(1 for f in found if f.get("disposition") == "declined"),
    }


def sync_declined(data):
    """Derive each ``crossFamilyReview.<repo>.declinedCount`` from ``verify``.

    A skipped review raised nothing, so it declined nothing. A cross-family
    finding comes only from a repo whose review ran, so when exactly one repo
    ran, every declined one is that repo's. With two or more, a finding does not
    name its repo, so their counts are left as they are (``verify`` still has
    the run's total, which the run-outcome line reports).
    """
    reviews = data.get("crossFamilyReview")
    if not isinstance(reviews, dict):
        return
    records = [r for r in reviews.values() if isinstance(r, dict)]
    ran = [r for r in records if r.get("status") == "ran"]
    declined = cross_family_counts(data)["declined"] if len(ran) == 1 else None
    for record in records:
        if record.get("status") != "ran":
            record["declinedCount"] = 0
        elif declined is not None:
            record["declinedCount"] = declined


def cross_family_summary(state):
    """The run-outcome line's ``crossFamily`` object, or None when the state has
    nothing for it: no ``crossFamilyReview`` record and no finding with a
    ``source``, which is every state written before REQ-722 (AC-15).

    Every value is a string: the counts from :func:`cross_family_counts`, then
    ``repos``, mapping each valid repo id to its ``status`` and ``reason``
    (``-`` when the record has none, or one outside the vocabulary).
    """
    reviews = state.get("crossFamilyReview")
    reviews = reviews if isinstance(reviews, dict) else {}
    if not reviews and not any("source" in f for f in _findings(state)):
        return None
    counts = cross_family_counts(state)
    if not reviews and not counts["findings"]:
        return None
    cf = _sibling("cross_family")
    repos = {}
    for repo in sorted(r for r in reviews if isinstance(r, str) and REPO_ID_RE.match(r)):
        record = reviews[repo] if isinstance(reviews[repo], dict) else {}
        status = record.get("status") if record.get("status") in cf.REVIEW_STATUSES else "-"
        reason = record.get("reason")
        reason = reason if status == "skipped" and reason in cf.SKIP_REASONS else "-"
        repos[repo] = {"status": status, "reason": reason}
    summary = {key: str(counts[key]) for key in CROSS_FAMILY_COUNTS}
    summary["repos"] = repos
    return summary


def build_record(state, terminal, engine, reason="", req=None, now=None):
    """The RunOutcome dict for ``state`` — every value a string, keys in KEYS order."""
    if terminal not in TERMINALS:
        raise UsageError(f"--terminal must be one of {', '.join(TERMINALS)}")
    if engine not in ENGINES:
        raise UsageError(f"--engine must be one of {', '.join(ENGINES)}")
    if terminal == "rejected" and engine != REJECTED_ENGINE:
        raise UsageError(f"--terminal rejected is written by --engine {REJECTED_ENGINE} only")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state = state if isinstance(state, dict) else {}

    req_id = state.get("req") if isinstance(state.get("req"), str) else (req or "")
    req_id = req_id if REQ_ID_RE.match(req_id or "") else "-"

    harness = state.get("harness") if isinstance(state.get("harness"), dict) else {}
    version = harness.get("version") if isinstance(harness.get("version"), str) else ""
    sha = harness.get("sha") if isinstance(harness.get("sha"), str) else ""

    if terminal in ("blocked", "failed"):
        blocked = normalize_blocked_reason(reason)
        if blocked in EXEC_ONLY_REASONS and engine != REJECTED_ENGINE:
            # A session writes its own line through a fence, with any reason token: one
            # that only the exec engine may write reads `other` from anyone else, so an
            # operator's abort cannot be forged in the log (REQ-719).
            blocked = "other"
    elif terminal == "rejected":
        # A declined PR is neither a halt nor a close-out: no reason, whatever
        # the state's closeOut says (BR-18). The operator's text stays in the
        # approval ledger, never in this log.
        blocked = ""
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
    cross = cross_family_summary(state)
    if cross is not None:
        record["crossFamily"] = cross
    return {k: record[k] for k in KEYS if k in record}


def encode(record):
    """One line of compact JSON; ``ensure_ascii`` keeps it a single line."""
    return json.dumps(record, ensure_ascii=True, separators=(",", ":"))


def normalize_findings(raw, checker=None):
    """The ``verify.findings`` entries for a list of consolidated findings. The
    REQ-722 fields follow the REQ-648 ones, each only when given and valid
    (:func:`finding_extras`), so a finding without them is written as before.
    ``line`` is kept when it is a 1-based integer (never a bool), so the PR
    section and ``cross_family.py check-dispositions`` can name ``file:line``."""
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
        line = f.get("line")
        if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
            entry["line"] = line
        entry.update(finding_extras(f, checker))
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
        # BUG-289: a session read the bare message as a failed setup and ended its run. The
        # line says what it means and what to do; nothing is created here, because the file's
        # first writer decides fresh or resume (Step 0 item 7).
        raise RunOutcomeError(f"state file not found: {path} (nothing recorded, and not a "
                              "blocker: Step 0's lessons fence creates this file, so if that "
                              "fence has not run, run it, then this one again)")
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


RUN_KEYS = ("validateAttempts", "verify", "lessonsWritten", "crossFamilyReview")


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
    findings = normalize_findings(raw, decline_checker(args.state))
    loops = None
    if args.loops is not None:
        loops = as_int(args.loops)
        if loops is None:
            raise UsageError("--loops must be a non-negative integer")

    def mutate(data):
        current = data.get("verify") if isinstance(data.get("verify"), dict) else {}
        kept = as_int(current.get("loops"))
        data["verify"] = {
            "findings": carry_forward(findings, current.get("findings")),
            "loops": loops if loops is not None else (kept if kept is not None else 0),
            "consolidatedAt": _iso_now(),
        }
        sync_declined(data)

    data = _update(args.state, mutate)
    v = data["verify"]
    fixed = sum(1 for f in v["findings"] if f["fixed"])
    print(f"verify: {len(v['findings'])} finding(s), {fixed} fixed, loops={v['loops']}")
    return 0


def _family_arg(value, flag):
    try:
        return _sibling("model_family").parse_family(value)
    except ValueError as exc:
        raise UsageError(f"{flag}: {exc}") from exc


def cmd_record_cross_family(args):
    cf = _sibling("cross_family")
    if not REPO_ID_RE.match(args.repo or ""):
        raise UsageError("--repo must be a repo id: 1 to 64 of A-Z a-z 0-9 . _ -")
    if args.status not in cf.REVIEW_STATUSES:
        raise UsageError(f"--status must be one of {', '.join(cf.REVIEW_STATUSES)}")
    if args.status == "skipped":
        if args.reason not in cf.SKIP_REASONS:
            raise UsageError(f"--status skipped needs --reason, one of {', '.join(cf.SKIP_REASONS)}")
    elif args.reason is not None:
        raise UsageError("--reason is given only with --status skipped")
    implementer = _family_arg(args.implementer, "--implementer")
    reviewer = _family_arg(args.reviewer, "--reviewer")
    counts = {}
    for flag, value in (("--findings", args.findings), ("--dropped", args.dropped)):
        n = as_int(value) if value is not None else 0
        if n is None:
            raise UsageError(f"{flag} must be a non-negative integer")
        counts[flag] = n
    if args.status == "skipped" and counts["--findings"]:
        raise UsageError("a skipped review has no findings: --findings must be 0")

    record = {"status": args.status}
    if args.status == "skipped":
        record["reason"] = args.reason
    record.update({
        "implementerFamily": implementer,
        "reviewerFamily": reviewer,
        "findingCount": counts["--findings"],
        "droppedCount": counts["--dropped"],
        "declinedCount": 0,
    })

    def mutate(data):
        reviews = data.get("crossFamilyReview")
        if not isinstance(reviews, dict):
            reviews = {}
        reviews[args.repo] = record
        data["crossFamilyReview"] = reviews
        sync_declined(data)

    data = _update(args.state, mutate)
    written = data["crossFamilyReview"][args.repo]
    print(f"crossFamilyReview: {args.repo} {written['status']}"
          + (f" {written['reason']}" if "reason" in written else "")
          + f", {written['findingCount']} finding(s), {written['droppedCount']} dropped")
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
    x = sub.add_parser("record-cross-family", add_help=False)
    x.add_argument("--state", required=True)
    x.add_argument("--repo", required=True)
    x.add_argument("--status", required=True)
    x.add_argument("--reason")
    x.add_argument("--implementer", required=True)
    x.add_argument("--reviewer", required=True)
    x.add_argument("--findings")
    x.add_argument("--dropped")
    return p


COMMANDS = {
    "emit": cmd_emit,
    "record-harness": cmd_record_harness,
    "record-validate": cmd_record_validate,
    "record-verify": cmd_record_verify,
    "record-lessons-written": cmd_record_lessons_written,
    "record-carry": cmd_record_carry,
    "record-cross-family": cmd_record_cross_family,
}


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.command not in COMMANDS:
            raise UsageError("usage: run_outcome.py emit|record-harness|record-validate|"
                             "record-verify|record-lessons-written|record-carry|"
                             "record-cross-family …")
        return COMMANDS[args.command](args)
    except UsageError as exc:
        print(f"run-outcome: {exc}", file=sys.stderr)
        return 2
    except RunOutcomeError as exc:
        print(f"run-outcome: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
