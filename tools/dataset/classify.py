"""Map every `.adlc/` path to a kind or a named exclusion (REQ-671 BR-4).

The scope check is only as good as this table. A path that matches neither a
kind nor an exclusion returns ``None``, and the export refuses: a new kind of
file under `.adlc/` must be decided on, not silently dropped or silently
published.
"""
import re
from collections import namedtuple

#: Kind order is also the record order in the dataset.
KIND_ORDER = ("requirement", "architecture", "task", "lesson", "bug", "assumption")

_SPEC = r"^\.adlc/specs/(REQ-[0-9]+)(?:-[^/]*)?/"

#: (kind, pattern). Group 1 is the owning REQ or the artifact's own id; a task's
#: group 2 is its TASK id.
KINDS = (
    ("requirement", re.compile(_SPEC + r"requirement\.md$")),
    ("architecture", re.compile(_SPEC + r"architecture\.md$")),
    ("task", re.compile(_SPEC + r"tasks/(TASK-[0-9]+)(?:-[^/]*)?\.md$")),
    ("lesson", re.compile(r"^\.adlc/knowledge/lessons/(LESSON-[0-9]+)(?:-[^/]*)?\.md$")),
    ("bug", re.compile(r"^\.adlc/bugs/(BUG-[0-9]+)(?:-[^/]*)?\.md$")),
    ("assumption", re.compile(r"^\.adlc/knowledge/assumptions/(ASSUME-[0-9]+)(?:-[^/]*)?\.md$")),
)

#: (reason, pattern). Each is a decision, with a reason the report prints.
EXCLUSIONS = (
    ("context doc (project-wide, not an artifact of one REQ)",
     re.compile(r"^\.adlc/context/[^/]+\.md$")),
    ("research note", re.compile(r"^\.adlc/research/")),
    ("verification notes", re.compile(_SPEC + r"verification\.md$")),
    ("adversary report", re.compile(_SPEC + r"adversary-report\.md$")),
    ("spike result", re.compile(_SPEC + r"[^/]+-spike-result\.md$")),
    ("pipeline state (machine-local)", re.compile(_SPEC + r"pipeline-state\.json$")),
    ("id counter", re.compile(r"^\.adlc/\.next-[a-z]+$")),
    ("project config", re.compile(r"^\.adlc/config\.yml$")),
)

Artifact = namedtuple("Artifact", "kind id parent_req")
Excluded = namedtuple("Excluded", "reason")


def classify(path):
    """Return an :class:`Artifact`, an :class:`Excluded`, or ``None`` (unmapped)."""
    for kind, pattern in KINDS:
        m = pattern.match(path)
        if not m:
            continue
        if kind == "requirement":
            return Artifact(kind, m.group(1), "")
        if kind == "architecture":
            return Artifact(kind, m.group(1) + "/architecture", m.group(1))
        if kind == "task":
            return Artifact(kind, m.group(1) + "/" + m.group(2), m.group(1))
        return Artifact(kind, m.group(1), "")
    for reason, pattern in EXCLUSIONS:
        if pattern.search(path):
            return Excluded(reason)
    return None


def kind_rank(kind):
    return KIND_ORDER.index(kind)
