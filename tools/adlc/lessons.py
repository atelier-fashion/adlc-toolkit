#!/usr/bin/env python3
"""LessonSet selection for the pipeline phases that act on lessons (REQ-647).

``/spec`` Step 1.6 retrieves lessons when a spec is written; this module is how
the later phases retrieve them **by the surface being touched**: ``/proceed``
Step 0 (``step0``), each Phase-4 task (``task``), Phase 5 (``phase5``),
``/bugfix`` Phase 2 (``bugfix``) and the sprint workflow engine's retrieval
leaves. The shell entry point is ``partials/lessons.sh`` (``adlc_lessons
<subcommand> …``), which runs the INSTALLED toolkit's copy of this file. It can
also be run by path::

    python3 tools/adlc/lessons.py select --set step0 --root <dir> --spec <requirement.md>

The model supplies the one input that needs judgment, the components of the
paths being touched (``--component``, the ``/review`` Step 1.7a inference).
Everything else is decided here, deterministically: the Step 1.6 score, the
recency rule, the caps, the 40-line loaded text, the state record, the log line
and the acknowledgement check. See ``partials/lessons.md`` for the contract and
the REQ-647 ``architecture.md`` for the rules.

Contract
--------
Exit ``0`` on success. Exit ``2`` on any usage or I/O error, with exactly one
``lessons: unavailable — <reason>`` line on stdout and the detail on stderr.
Retrieval is never a gate: a caller that gets ``2`` logs the line and carries on
without lessons. There is no exit ``1``.

Standard library only: lesson frontmatter is the toolkit's one-line format
(``key: value``, a quoted scalar, or an inline ``[a, b]`` list), read the way
``partials/lesson-check.sh`` reads it.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

LESSON_ID_RE = re.compile(r"^LESSON-[0-9]{3,6}$")
LESSON_TOKEN_RE = re.compile(r"LESSON-[0-9]{3,6}(?![0-9])")
LESSON_FILE_RE = re.compile(r"^(LESSON-[0-9]{3,6})-[^/]*\.md$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{3,6}$")
COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_./-]{0,119}$")
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?$")
TRAILER_RE = re.compile(r"^[ \t]*Lessons:[ \t]*(.*)$", re.IGNORECASE)

LESSONS_REL = os.path.join(".adlc", "knowledge", "lessons")
SETS = ("step0", "task", "phase5", "bugfix")
CAPS = {"step0": 10, "task": 5, "phase5": 15, "bugfix": 5}
TASK_RECENCY_MAX = 3
SET_MAX = 15
TOPUP_BELOW = 5
TOPUP_TO = 10
TEXT_MAX_LINES = 40
KIND_VALUES = ("process", "domain")
CONFIDENCE_VALUES = ("high", "medium", "low")
LIST_FIELDS = ("stack", "concerns", "tags", "supersedes")


class LessonsError(Exception):
    """A usage or I/O failure: reported as rc 2, never as an empty pass."""


# --- frontmatter ------------------------------------------------------------

def _split_list(inner):
    """Split the inside of an inline ``[a, "b, c"]`` list on unquoted commas."""
    items, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    out = []
    for item in items:
        item = _unquote(item.strip())
        if item:
            out.append(item)
    return out


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_value(raw):
    """One frontmatter value: a quoted scalar, an inline list, or a bare word."""
    value = raw.strip()
    if not value:
        return ""
    if value[0] in "\"'":
        quote = value[0]
        end = value.find(quote, 1)
        while end != -1 and quote == '"' and value[end - 1] == "\\":
            end = value.find(quote, end + 1)
        return value[1:end] if end != -1 else value[1:]
    if value[0] == "[":
        end = value.rfind("]")
        return _split_list(value[1:end] if end != -1 else value[1:])
    # A bare value: a ` #` starts a YAML comment.
    hash_at = value.find(" #")
    if hash_at != -1:
        value = value[:hash_at]
    return value.strip()


def read_frontmatter(text):
    """Return ``(fields, block_lines, body_lines)``; ``fields`` is None when the
    file has no frontmatter block.

    The block is found the way ``adlc_lesson_check`` finds it: a leading BOM and
    each line's trailing CR are dropped, blank lines and HTML comments before it
    are skipped, and it opens only when the first other line is exactly
    ``---``. A repeated key keeps its last value, as a YAML reader would.
    """
    if text.startswith("﻿"):
        text = text[1:]
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    i, n, in_comment = 0, len(lines), False
    while i < n:
        line = lines[i]
        if in_comment:
            if "-->" in line:
                in_comment = False
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        if line.startswith("<!--"):
            in_comment = "-->" not in line
            i += 1
            continue
        break
    if i >= n or lines[i] != "---":
        return None, None, lines
    end = i + 1
    while end < n and lines[end] != "---":
        end += 1
    if end >= n:
        return None, None, lines
    fields = {}
    for raw in lines[i + 1:end]:
        match = KEY_RE.match(raw)
        if match:
            fields[match.group(1)] = parse_value(match.group(2) or "")
    return fields, lines[i:end + 1], lines[end + 1:]


def _as_list(value):
    if isinstance(value, list):
        return [v for v in value if v]
    return [value] if value else []


def _as_str(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


# --- corpus -----------------------------------------------------------------

class Doc:
    """One lesson file: its retrieval fields and its text, read once."""

    def __init__(self, lesson_id, rel_path, abs_path, fields, block, body, mtime):
        self.id = lesson_id
        self.path = rel_path
        self.abs_path = abs_path
        self.fields = fields
        self.block = block
        self.body = body
        self.mtime = mtime
        self.title = _as_str(fields.get("title")) or lesson_id
        self.component = _as_str(fields.get("component"))
        self.domain = _as_str(fields.get("domain"))
        self.stack = _as_list(fields.get("stack"))
        self.concerns = _as_list(fields.get("concerns"))
        self.tags = _as_list(fields.get("tags"))
        self.created = _as_str(fields.get("created"))
        self.updated = _as_str(fields.get("updated"))
        kind = _as_str(fields.get("kind"))
        self.kind = kind if kind in KIND_VALUES else ""
        confidence = _as_str(fields.get("confidence"))
        self.confidence = confidence if confidence in CONFIDENCE_VALUES else ""
        self.supersedes = [s for s in _as_list(fields.get("supersedes")) if LESSON_ID_RE.match(s)]

    @property
    def untagged(self):
        return not (self.component or self.domain or self.stack or self.concerns or self.tags)

    @property
    def effective_date(self):
        if self.updated:
            return self.updated
        if self.created:
            return self.created
        if self.mtime is not None:
            return datetime.datetime.fromtimestamp(self.mtime, datetime.timezone.utc).strftime("%Y-%m-%d")
        return ""


def load_corpus(root, report=None):
    """Every parseable ``LESSON-*.md`` under ``<root>/.adlc/knowledge/lessons``.

    A missing directory is an empty corpus (a cold start), not an error. A
    symlink is skipped: it could name a file outside the corpus. ``report``, when
    given, is a dict that receives ``files`` (lesson files seen) and ``skipped``
    (those with no parseable frontmatter), so a caller can tell "the corpus is
    empty" from "the reader dropped the corpus" (LESSON-571).
    """
    lessons_dir = os.path.join(root, LESSONS_REL)
    if report is not None:
        report.update(files=0, skipped=0)
    if not os.path.isdir(lessons_dir):
        return []
    docs = []
    for name in sorted(os.listdir(lessons_dir)):
        match = LESSON_FILE_RE.match(name)
        abs_path = os.path.join(lessons_dir, name)
        if not match or os.path.islink(abs_path) or not os.path.isfile(abs_path):
            continue
        if report is not None:
            report["files"] += 1
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            mtime = os.stat(abs_path).st_mtime
        except OSError:
            continue
        fields, block, body = read_frontmatter(text)
        if fields is None:
            if report is not None:
                report["skipped"] += 1
            continue
        rel = os.path.join(LESSONS_REL, name).replace(os.sep, "/")
        docs.append(Doc(match.group(1), rel, abs_path, fields, block, body, mtime))
    return docs


def superseded_by(docs, ignore_ids=()):
    """Map lesson id -> ids of the lessons that name it in ``supersedes``.

    A lesson in ``ignore_ids`` (one the diff under review changes) supersedes
    nothing: a change must not switch off its own escalation (/review 7f).
    """
    out = {}
    for doc in docs:
        if doc.id in ignore_ids:
            continue
        for target in doc.supersedes:
            if target != doc.id:
                out.setdefault(target, []).append(doc.id)
    return {k: sorted(set(v)) for k, v in out.items()}


# --- loaded text (BR-1b) ----------------------------------------------------

def _sections(body):
    """``[(heading, lines)]`` for every ``## `` section outside a code fence."""
    sections, current, fence = [], None, None
    for line in body:
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in ("```", "~~~"):
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
        if fence is None and line.startswith("## ") and marker not in ("```", "~~~"):
            current = (line[3:].strip(), [line])
            sections.append(current)
            continue
        if current is not None:
            current[1].append(line)
    out = []
    for heading, lines in sections:
        while lines and not lines[-1].strip():
            lines.pop()
        out.append((heading, lines))
    return out


def loaded_text(doc):
    """The frontmatter, ``## Lesson`` and ``## Applies When``, capped at 40 lines.

    No ``## Lesson`` section: the first body section stands in for it. No
    ``## Applies When``: the title stands in for it. Over 40 lines: the first 39
    and a truncation marker, exactly 40.
    """
    sections = _sections(doc.body)
    by_heading = {}
    for heading, lines in sections:
        by_heading.setdefault(heading, lines)
    lesson = by_heading.get("Lesson")
    if lesson is None and sections:
        lesson = sections[0][1]
    applies = by_heading.get("Applies When")
    parts = [list(doc.block)]
    if lesson and lesson is not applies:
        parts.append(lesson)
    parts.append(applies if applies is not None else [f"Applies When: {doc.title}"])
    out = []
    for part in parts:
        if out:
            out.append("")
        out.extend(part)
    if len(out) > TEXT_MAX_LINES:
        out = out[:TEXT_MAX_LINES - 1] + [f"[… truncated — read {doc.id} for the rest]"]
    return out


# --- selection (the /spec Step 1.6 rule over lessons) -----------------------

def clean_components(values):
    """Drop anything that is not a component-shaped token (they come from a model)."""
    out = []
    for value in values or []:
        value = (value or "").strip().strip("/")
        if value and COMPONENT_RE.match(value) and ".." not in value and value not in out:
            out.append(value)
    return out


def with_ancestors(specific):
    """The caller's components plus each one's ancestors short of a one-segment root."""
    out = list(specific)
    for component in specific:
        parts = component.split("/")
        for k in range(len(parts) - 1, 1, -1):
            ancestor = "/".join(parts[:k])
            if ancestor not in out:
                out.append(ancestor)
    return out


def make_query(components, frontmatter):
    return {
        "components": list(components),
        "domain": _as_str(frontmatter.get("domain")),
        "stack": _as_list(frontmatter.get("stack")),
        "concerns": _as_list(frontmatter.get("concerns")),
        "tags": _as_list(frontmatter.get("tags")),
    }


def score(doc, query):
    """``+3`` component, ``+2`` domain, ``+2``/concern, ``+1``/stack, ``+1``/tag,
    ``+1`` floor for an untagged lesson."""
    total = 0
    if doc.component and doc.component in query["components"]:
        total += 3
    if doc.domain and doc.domain == query["domain"]:
        total += 2
    total += 2 * len(set(doc.concerns) & set(query["concerns"]))
    total += len(set(doc.stack) & set(query["stack"]))
    total += len(set(doc.tags) & set(query["tags"]))
    if doc.untagged:
        total += 1
    return total


def step16_order(pairs):
    """Sort ``(doc, score)`` by ``(score DESC, effective_date DESC, id ASC)``."""
    ordered = sorted(pairs, key=lambda p: p[0].id)
    ordered.sort(key=lambda p: p[0].effective_date, reverse=True)
    ordered.sort(key=lambda p: p[1], reverse=True)
    return ordered


def ranked(docs, query):
    return step16_order([(d, s) for d in docs for s in [score(d, query)] if s > 0])


def _prefix_of_any(component, components):
    return bool(component) and any(c.startswith(component + "/") for c in components)


def _entry(doc, score_value, spec_created, superseded, standing):
    entry = {"id": doc.id, "title": doc.title, "path": doc.path}
    if doc.component:
        entry["component"] = doc.component
    if score_value is not None:
        entry["score"] = score_value
    if doc.confidence and standing:
        entry["confidence"] = doc.confidence
    if doc.kind:
        entry["kind"] = doc.kind
    if spec_created and doc.created and doc.created > spec_created:
        entry["newerThanSpec"] = True
    if superseded.get(doc.id):
        entry["supersededBy"] = superseded[doc.id]
    return entry


def select(set_name, docs, frontmatter, components=(), step0_entries=None):
    """Compute one LessonSet's ``(query, members)``; members are ``(doc, score)``.

    ``frontmatter`` is the spec's (or, for ``bugfix``, the bug's). ``components``
    is the caller's most-specific list. ``step0_entries`` feeds the task set's
    process carry-over. Pure over its arguments.
    """
    if set_name not in SETS:
        raise LessonsError(f"unknown set '{set_name}'")
    own = clean_components([_as_str(frontmatter.get("component"))])
    if set_name == "step0":
        specific = own
        query = make_query(specific, frontmatter)
    elif set_name == "bugfix":
        specific = clean_components(list(own) + list(components))
        query = make_query(with_ancestors(specific), frontmatter)
    else:
        specific = clean_components(components)
        query = make_query(with_ancestors(specific), frontmatter)
    scored = ranked(docs, query)
    members = scored[:CAPS[set_name]]
    chosen = {d.id for d, _ in members}

    if set_name == "task":
        spec_created = _as_str(frontmatter.get("created"))
        candidates = []
        for doc, value in scored:
            if doc.id in chosen or not (spec_created and doc.created and doc.created > spec_created):
                continue
            if doc.component in query["components"] or (
                    doc.domain and doc.domain == query["domain"]
                    and _prefix_of_any(doc.component, query["components"])):
                candidates.append((doc, value))
        candidates.sort(key=lambda p: 0 if p[0].component in specific else 1)  # stable
        for doc, value in candidates[:TASK_RECENCY_MAX]:
            members.append((doc, value))
            chosen.add(doc.id)
        by_id = {d.id: d for d in docs}
        if step0_entries is None:
            step0_query = make_query(own, frontmatter)
            step0_entries = [{"id": d.id, "kind": d.kind} for d, _ in ranked(docs, step0_query)[:CAPS["step0"]]]
        for entry in step0_entries:
            if len(members) >= SET_MAX:
                break
            doc = by_id.get(entry.get("id"))
            if entry.get("kind") == "process" and doc is not None and doc.id not in chosen:
                members.append((doc, score(doc, query)))
                chosen.add(doc.id)

    if set_name == "phase5" and len(members) < TOPUP_BELOW:
        recent = sorted(docs, key=lambda d: d.id)
        recent.sort(key=lambda d: d.effective_date, reverse=True)
        for doc in recent:
            if len(members) >= TOPUP_TO:
                break
            if doc.id not in chosen:
                members.append((doc, None))
                chosen.add(doc.id)
    return query, members


def build_set(set_name, docs, frontmatter, components=(), step0_entries=None,
              changed_ids=(), retrieved_at=None, with_text=False):
    query, members = select(set_name, docs, frontmatter, components, step0_entries)
    superseded = superseded_by(docs, ignore_ids=changed_ids)
    spec_created = _as_str(frontmatter.get("created")) if set_name != "bugfix" else ""
    lessons = []
    for doc, value in members:
        entry = _entry(doc, value, spec_created, superseded, doc.id not in changed_ids)
        if with_text:
            entry["text"] = "\n".join(loaded_text(doc))
        lessons.append(entry)
    cap = SET_MAX if set_name == "task" else CAPS[set_name]
    return {
        "query": query,
        "lessons": lessons,
        "cap": cap,
        "retrievedAt": retrieved_at or now_iso(),
    }


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        moment = datetime.datetime.fromisoformat(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        return moment.timestamp()
    except (AttributeError, ValueError):
        return None


# --- log line (BR-10) -------------------------------------------------------

def stale_count(docs, retrieved_at):
    """Lesson files whose mtime is later than the set's ``retrievedAt``.

    Compared at whole seconds, the precision ``retrievedAt`` is written at, so a
    file written in the same second the set was computed is not counted.
    """
    moment = parse_iso(retrieved_at or "")
    if moment is None:
        return 0
    return sum(1 for d in docs if d.mtime is not None and int(d.mtime) > moment)


def log_line(label, lessonset, stale=0):
    lessons = lessonset.get("lessons") or []
    plain = [e["id"] for e in lessons if not e.get("newerThanSpec")]
    newer = [e["id"] for e in lessons if e.get("newerThanSpec")]
    line = f"Lessons loaded ({label}): " + (", ".join(plain) if plain else ("none" if not newer else ""))
    line = line.rstrip()
    if newer:
        line += f" [newer-than-spec: {', '.join(newer)}]"
    if stale:
        line += f" (stale: {stale} lessons newer than this set)"
    return line


def label_for(set_name, task_id=None):
    return f"task {task_id}" if set_name == "task" and task_id else set_name


# --- acknowledgement check (BR-4) -------------------------------------------

def unacknowledged(lessons, components, acknowledged, limit=5):
    """The Info lines for applicable lessons nobody acknowledged.

    A lesson qualifies when its ``component`` is one of ``components`` or it
    carries ``kind: process`` — a ``domain``- or ``tags``-only match never does —
    and its id is not in ``acknowledged``. Highest score first, unscored last,
    then id. At most ``limit`` lines, then one ``(+N more …)`` line.
    """
    comps = set(components or [])
    acked = set(acknowledged or [])
    applicable = [
        e for e in (lessons or [])
        if e.get("id") not in acked
        and ((e.get("component") and e.get("component") in comps) or e.get("kind") == "process")
    ]
    applicable.sort(key=lambda e: (0 if isinstance(e.get("score"), int) else 1,
                                   -(e.get("score") or 0), e.get("id", "")))
    lines = [f"Applicable lesson not acknowledged: {e['id']} — {e.get('title', '')}"
             for e in applicable[:limit]]
    if len(applicable) > limit:
        lines.append(f"(+{len(applicable) - limit} more applicable lessons not listed)")
    return lines


def trailer_ids(messages):
    """Lesson ids named in ``Lessons:`` trailer lines of commit messages."""
    found = set()
    for line in (messages or "").splitlines():
        match = TRAILER_RE.match(line)
        if match:
            found.update(t for t in LESSON_TOKEN_RE.findall(match.group(1)) if LESSON_ID_RE.match(t))
    return found


def verification_ids(task_texts):
    """Lesson ids cited inside each task file's ``## Verification`` section."""
    found = set()
    for text in task_texts:
        for heading, lines in _sections(text.split("\n")):
            if heading == "Verification":
                found.update(LESSON_TOKEN_RE.findall("\n".join(lines)))
    return found


# --- git and state I/O ------------------------------------------------------

def _git(worktree, args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        proc = subprocess.run(["git", "-C", worktree] + args, capture_output=True,
                              text=True, env=env, check=False)
    except OSError as exc:
        raise LessonsError(f"git failed: {exc}") from exc
    if proc.returncode != 0:
        raise LessonsError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _check_ref(ref):
    """A ref is handed to git as an argument; one that starts with ``-`` would be
    read as an option."""
    if ref is not None and (not ref or ref.startswith("-") or any(c.isspace() for c in ref)):
        raise LessonsError(f"not a usable git ref: '{ref}'")


def changed_lesson_ids(worktree, base):
    """Lesson ids whose files the diff against ``base`` adds or modifies."""
    names = _git(worktree, ["diff", "--name-only", f"{base}...HEAD"]).splitlines()
    names += _git(worktree, ["diff", "--name-only", "HEAD"]).splitlines()
    names += _git(worktree, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    out = set()
    prefix = LESSONS_REL.replace(os.sep, "/") + "/"
    for name in names:
        if name.startswith(prefix):
            match = LESSON_FILE_RE.match(name[len(prefix):])
            if match:
                out.add(match.group(1))
    return out


def read_frontmatter_file(path, what):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            fields, _, _ = read_frontmatter(handle.read())
    except OSError as exc:
        raise LessonsError(f"cannot read {what} {path}: {exc.strerror}") from exc
    if fields is None:
        raise LessonsError(f"{what} {path} has no frontmatter block")
    return fields


def read_state(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise LessonsError(f"cannot read state file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LessonsError(f"state file {path} is not a JSON object")
    return data


def state_record(data, set_name, task_id):
    lessons = data.get("lessons")
    if not isinstance(lessons, dict):
        return None
    if set_name == "task":
        tasks = lessons.get("tasks")
        record = tasks.get(task_id) if isinstance(tasks, dict) else None
    else:
        record = lessons.get(set_name)
    return record if isinstance(record, dict) else None


def write_state(path, req_id, set_name, task_id, lessonset, fresh):
    """Merge one set into the state file atomically; every other key survives."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise LessonsError(f"state directory does not exist: {directory}")
    data = read_state(path)
    if req_id and "req" not in data:
        data["req"] = req_id
    lessons = data.get("lessons")
    if fresh or not isinstance(lessons, dict):
        lessons = {}
    record = {k: v for k, v in lessonset.items()}
    record["lessons"] = [{k: v for k, v in e.items() if k != "text"} for e in lessonset["lessons"]]
    if set_name == "task":
        tasks = lessons.get("tasks")
        if not isinstance(tasks, dict):
            tasks = {}
        tasks[task_id] = record
        lessons["tasks"] = tasks
    else:
        lessons[set_name] = record
    data["lessons"] = lessons
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
        raise LessonsError(f"cannot write state file {path}: {exc}") from exc


def _with_text(lessonset, docs):
    by_id = {d.id: d for d in docs}
    out = dict(lessonset)
    out["lessons"] = []
    for entry in lessonset.get("lessons") or []:
        entry = dict(entry)
        doc = by_id.get(entry.get("id"))
        if doc is not None:
            entry["text"] = "\n".join(loaded_text(doc))
        out["lessons"].append(entry)
    return out


def render_text(header, lessonset):
    """The text format: the log or list line, then one block per lesson."""
    lines = [header]
    for entry in lessonset.get("lessons") or []:
        notes = []
        if isinstance(entry.get("score"), int):
            notes.append(f"score {entry['score']}")
        if entry.get("kind") == "process":
            notes.append("process")
        if entry.get("newerThanSpec"):
            notes.append("newer than spec")
        if entry.get("supersededBy"):
            notes.append("superseded by " + ", ".join(entry["supersededBy"]))
        suffix = f" ({'; '.join(notes)})" if notes else ""
        lines += ["", f"### {entry['id']} — {entry.get('title', '')}{suffix}"]
        if entry.get("text"):
            lines += entry["text"].split("\n")
    return "\n".join(lines)


def bugfix_header(lessonset):
    lessons = lessonset.get("lessons") or []
    if not lessons:
        return "Prior lessons consulted: none"
    rows = ["Prior lessons consulted:"]
    for e in lessons:
        rows.append(f"- {e['id']} — {e.get('title', '')} (score {e.get('score', 0)})")
    return "\n".join(rows)


# --- commands ---------------------------------------------------------------

def cmd_select(args):
    if args.set == "bugfix":
        if not args.bug:
            raise LessonsError("--set bugfix needs --bug <bug.md>")
        frontmatter = read_frontmatter_file(args.bug, "bug report")
    else:
        if not args.spec:
            raise LessonsError(f"--set {args.set} needs --spec <requirement.md>")
        frontmatter = read_frontmatter_file(args.spec, "spec")
    task_id = args.task_id
    if args.set == "task" and (not task_id or not TASK_ID_RE.match(task_id)):
        raise LessonsError("--set task needs --task-id TASK-nnn")
    if args.fresh and args.reuse:
        raise LessonsError("--fresh and --reuse are mutually exclusive")
    if args.fresh and args.set != "step0":
        raise LessonsError("--fresh resets every recorded set, so it belongs to --set step0 only")
    _check_ref(args.base)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        raise LessonsError(f"--root is not a directory: {args.root}")
    corpus_report = {}
    docs = load_corpus(root, corpus_report)
    if corpus_report.get("skipped"):
        print(f"lessons: {corpus_report['skipped']} of {corpus_report['files']} lesson files have no "
              "parseable frontmatter and were skipped", file=sys.stderr)
    if corpus_report.get("files") and not docs:
        raise LessonsError(f"none of the {corpus_report['files']} lesson files parsed — a reader "
                           "failure, not an empty corpus")
    dropped = [c for c in args.component if c not in clean_components([c])]
    for value in dropped:
        print(f"lessons: ignored component '{value}' (not a component-shaped token)", file=sys.stderr)

    state_path = args.state_out
    existing = state_record(read_state(state_path), args.set, task_id) if (args.reuse and state_path) else None
    if existing is not None:
        lessonset = existing
        written = False
    else:
        step0_entries = None
        if args.set == "task":
            step0 = state_record(read_state(args.state or state_path), "step0", None)
            if step0 is not None:
                step0_entries = step0.get("lessons") or []
        changed = set()
        if args.set == "phase5" and args.base:
            try:
                changed = changed_lesson_ids(root, args.base)
            except LessonsError as exc:
                # Fail safe both ways: the set still loads, and no lesson keeps an
                # exemption it could have switched on in this very diff (/review 7f).
                print(f"lessons: cannot list the lesson files this diff changes ({exc}); "
                      "treating every lesson as changed, so none carries escalation standing",
                      file=sys.stderr)
                changed = {d.id for d in docs}
        lessonset = build_set(args.set, docs, frontmatter, args.component, step0_entries,
                              changed, args.retrieved_at)
        written = False
        if state_path and args.set != "bugfix":
            write_state(state_path, _as_str(frontmatter.get("id")), args.set, task_id,
                        lessonset, args.fresh)
            written = True
    if state_path and args.set != "bugfix":
        print(f"lessons: {'wrote' if written else 'reused'} "
              f"lessons.{'tasks.' + task_id if args.set == 'task' else args.set} in {state_path}",
              file=sys.stderr)

    if args.with_text or args.format == "text":
        lessonset = _with_text(lessonset, docs)
    if args.format == "json":
        print(json.dumps(lessonset, indent=2, ensure_ascii=False))
        return 0
    if args.set == "bugfix":
        header = bugfix_header(lessonset)
    else:
        header = log_line(label_for(args.set, task_id), lessonset,
                          stale_count(docs, lessonset.get("retrievedAt")))
    print(render_text(header, lessonset))
    return 0


def cmd_text(args):
    path = os.path.abspath(args.lesson)
    name = os.path.basename(path)
    match = LESSON_FILE_RE.match(name)
    if not match:
        raise LessonsError(f"not a LESSON-<digits>-<slug>.md file: {name}")
    if os.path.islink(path):
        raise LessonsError(f"refusing a symlink: {args.lesson}")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            fields, block, body = read_frontmatter(handle.read())
    except OSError as exc:
        raise LessonsError(f"cannot read {args.lesson}: {exc.strerror}") from exc
    if fields is None:
        raise LessonsError(f"{args.lesson} has no frontmatter block")
    doc = Doc(match.group(1), name, path, fields, block, body, None)
    print("\n".join(loaded_text(doc)))
    return 0


def _key(value):
    if value in ("step0", "phase5"):
        return value, None
    if value.startswith("tasks.") and TASK_ID_RE.match(value[len("tasks."):]):
        return "task", value[len("tasks."):]
    raise LessonsError(f"--key must be step0, phase5 or tasks.TASK-nnn, not '{value}'")


def cmd_log_line(args):
    set_name, task_id = _key(args.key)
    record = state_record(read_state(args.state), set_name, task_id)
    if record is None:
        print(f"Lessons loaded ({label_for(set_name, task_id)}): not recorded")
        return 0
    docs = load_corpus(os.path.abspath(args.root))
    print(log_line(label_for(set_name, task_id), record, stale_count(docs, record.get("retrievedAt"))))
    return 0


def cmd_ack_check(args):
    for ref in args.base:
        _check_ref(ref)
    record = state_record(read_state(args.state), "phase5", None)
    root = os.path.abspath(args.root)
    if record is None:
        if not (args.spec and args.component):
            print("No lessons.phase5 set recorded — acknowledgement check skipped.")
            return 0
        docs = load_corpus(root)
        record = build_set("phase5", docs, read_frontmatter_file(args.spec, "spec"), args.component)
    worktrees, bases = args.worktree, args.base
    if len(bases) == 1:
        bases = bases * len(worktrees)
    if len(bases) != len(worktrees):
        raise LessonsError("give one --base, or one --base per --worktree")
    acknowledged = set()
    for worktree, base in zip(worktrees, bases):
        acknowledged |= trailer_ids(_git(worktree, ["log", "--format=%B", f"{base}..HEAD"]))
    texts = []
    if args.tasks_dir and os.path.isdir(args.tasks_dir):
        for name in sorted(os.listdir(args.tasks_dir)):
            path = os.path.join(args.tasks_dir, name)
            if name.startswith("TASK-") and name.endswith(".md") and os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    texts.append(handle.read())
    acknowledged |= verification_ids(texts)
    lines = unacknowledged(record.get("lessons"), (record.get("query") or {}).get("components"),
                           acknowledged)
    print("\n".join(lines) if lines else "No unacknowledged applicable lessons.")
    return 0


class _ArgumentParser(argparse.ArgumentParser):
    """argparse that raises instead of exiting, so a usage error is rc 2 with the
    contract line rather than argparse's own exit."""

    def error(self, message):
        raise LessonsError(message)


def _parser():
    parser = _ArgumentParser(prog="lessons.py", add_help=False)
    sub = parser.add_subparsers(dest="command", parser_class=_ArgumentParser)
    sel = sub.add_parser("select", add_help=False)
    sel.add_argument("--set", required=True, choices=SETS)
    sel.add_argument("--root", required=True)
    sel.add_argument("--spec")
    sel.add_argument("--bug")
    sel.add_argument("--component", action="append", default=[])
    sel.add_argument("--task-id")
    sel.add_argument("--state")
    sel.add_argument("--state-out")
    sel.add_argument("--fresh", action="store_true")
    sel.add_argument("--reuse", action="store_true")
    sel.add_argument("--base")
    sel.add_argument("--format", choices=("text", "json"), default="text")
    sel.add_argument("--with-text", action="store_true")
    sel.add_argument("--retrieved-at")
    txt = sub.add_parser("text", add_help=False)
    txt.add_argument("lesson")
    log = sub.add_parser("log-line", add_help=False)
    log.add_argument("--state", required=True)
    log.add_argument("--key", required=True)
    log.add_argument("--root", required=True)
    ack = sub.add_parser("ack-check", add_help=False)
    ack.add_argument("--state")
    ack.add_argument("--root", required=True)
    ack.add_argument("--worktree", action="append", required=True)
    ack.add_argument("--base", action="append", required=True)
    ack.add_argument("--tasks-dir")
    ack.add_argument("--spec")
    ack.add_argument("--component", action="append", default=[])
    return parser


COMMANDS = {"select": cmd_select, "text": cmd_text, "log-line": cmd_log_line, "ack-check": cmd_ack_check}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
        if args.command not in COMMANDS:
            raise LessonsError("usage: lessons.py select|text|log-line|ack-check …")
        return COMMANDS[args.command](args)
    except LessonsError as exc:
        print(f"lessons.py: {exc}", file=sys.stderr)
        print(f"lessons: unavailable — {exc}")
        return 2
    except Exception as exc:  # an error is never an empty pass (LESSON-581)
        print(f"lessons.py: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"lessons: unavailable — unexpected {type(exc).__name__}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
