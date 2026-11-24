#!/usr/bin/env python3
"""The quickstart page's steps: the one parser of ``docs/quickstart.md`` (REQ-672 ADR-2).

Everything a newcomer types on the page is a fenced block holding one line,
immediately after one marker line::

    <!-- quickstart-step: shell -->
    <!-- quickstart-step: prompt -->
    <!-- quickstart-step: answer e2e=req-id -->

``shell`` is a terminal command, ``prompt`` is typed into Claude Code, and
``answer`` is a reply to a question the page shows. ``e2e=<name>`` names one of
the substitutions the quickstart e2e driver applies (ADR-5). The step count
(AC-3), the ``newcomer-docs`` lint, the e2e driver and the recording all read the
steps here, or through :data:`MARKER_PATTERN`, so a step cannot be documented one
way and tested another.

The page also carries exactly one timing marker, in one of two forms::

    <!-- quickstart-verified: none -->
    <!-- quickstart-verified: release=X.Y.Z minutes=N date=YYYY-MM-DD -->

with the sentence :func:`timing_sentence` gives for it.

Run by path, it lists the page's steps::

    python3 tools/launch/quickstart_steps.py [PAGE]

PAGE defaults to the ``docs/quickstart.md`` beside this toolkit copy. Exit 0 when
the page has one to :data:`MAX_STEPS` well-formed steps and one well-formed timing
marker, 1 on a refusal (the reason and its line go to stderr), 2 when the page
cannot be read or the arguments are wrong. Python 3.9, standard library only.
"""

import collections
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
#: The real page, resolved from this file's own location.
DEFAULT_PAGE = os.path.join(TOOLKIT, "docs", "quickstart.md")

#: A terminal command.
KIND_SHELL = "shell"
#: A prompt typed into Claude Code.
KIND_PROMPT = "prompt"
#: A reply to a question the page shows. It counts toward the steps like the others.
KIND_ANSWER = "answer"
KINDS = (KIND_SHELL, KIND_PROMPT, KIND_ANSWER)

#: Step 3: the e2e driver appends ``--existing-repo <throwaway>``.
E2E_EXISTING_REPO = "existing-repo"
#: Step 5: the e2e driver sends the quoted prompt as a headless turn.
E2E_INIT_PROMPT = "init-prompt"
#: Step 8: the e2e driver replaces :data:`REQ_ID_PLACEHOLDER` with the id step 7 wrote.
E2E_REQ_ID = "req-id"
E2E_NAMES = (E2E_EXISTING_REPO, E2E_INIT_PROMPT, E2E_REQ_ID)

#: BR-2: the most things a newcomer types, install included.
MAX_STEPS = 8
#: The one value the page cannot know; the page says to use the id ``/adlc:spec`` printed.
REQ_ID_PLACEHOLDER = "REQ-xxx"

#: A step marker. The kind and the e2e name are checked against KINDS and
#: E2E_NAMES after the match, so a wrong word is named, not skipped.
MARKER_PATTERN = r"^<!-- quickstart-step: (?P<kind>\S+)(?: e2e=(?P<e2e>\S+))? -->$"
MARKER_RE = re.compile(MARKER_PATTERN)
#: A line that starts with this, outside a fence, must be a whole marker.
MARKER_PREFIX = "<!-- quickstart-step"

#: The timing marker, in its two forms.
VERIFIED_PATTERN = (
    r"^<!-- quickstart-verified: (?:(?P<none>none)"
    r"|release=(?P<release>[0-9]+\.[0-9]+\.[0-9]+)"
    r" minutes=(?P<minutes>[1-9][0-9]*)"
    r" date=(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})) -->$"
)
VERIFIED_RE = re.compile(VERIFIED_PATTERN)
VERIFIED_PREFIX = "<!-- quickstart-verified"

#: The visible sentence for ``quickstart-verified: none``.
NOT_MEASURED = ("Timing: this page has not been measured against a release yet, "
                "so it gives no time for a run.")

_FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: One typed step. ``line`` is the 1-based line of its command, inside the fence.
Step = collections.namedtuple("Step", "kind text e2e line")
#: A ``quickstart-verified`` record: release ``X.Y.Z``, whole minutes, ISO date.
Verified = collections.namedtuple("Verified", "release minutes date")


class QuickstartError(ValueError):
    """The page breaks the marker grammar. ``line`` is 1-based, or None for the whole page."""

    def __init__(self, line, message):
        self.line = line
        self.message = message
        super().__init__("line %d: %s" % (line, message) if line else message)


def _fence_open(line):
    """``(char, length)`` when ``line`` opens a fenced block, else None."""
    match = _FENCE_OPEN_RE.match(line)
    if not match:
        return None
    fence = match.group("fence")
    if fence[0] == "`" and "`" in match.group("info"):
        return None
    return fence[0], len(fence)


def _fence_close(line, opened):
    """True when ``line`` closes the block ``opened`` (:func:`_fence_open`)."""
    char, length = opened
    if line.startswith("    "):
        return False
    stripped = line.strip()
    return len(stripped) >= length and stripped == char * len(stripped)


def _read_step(lines, index):
    """The step whose marker is ``lines[index]``, and the index after its fence."""
    number = index + 1
    match = MARKER_RE.match(lines[index].rstrip())
    if not match:
        raise QuickstartError(number, "malformed quickstart-step marker %r: write "
                              "'<!-- quickstart-step: KIND -->', optionally with ' e2e=NAME' "
                              "before ' -->'" % lines[index].strip())
    kind, e2e = match.group("kind"), match.group("e2e")
    if kind not in KINDS:
        raise QuickstartError(number, "unknown step kind %r: the kinds are %s"
                              % (kind, ", ".join(KINDS)))
    if e2e is not None and e2e not in E2E_NAMES:
        raise QuickstartError(number, "unknown e2e name %r: the names are %s"
                              % (e2e, ", ".join(E2E_NAMES)))
    opened = _fence_open(lines[index + 1]) if index + 1 < len(lines) else None
    if opened is None:
        raise QuickstartError(number, "the marker is not immediately followed by a fenced "
                              "block holding the step")
    body = []
    cursor = index + 2
    while cursor < len(lines) and not _fence_close(lines[cursor], opened):
        body.append((cursor + 1, lines[cursor]))
        cursor += 1
    if cursor >= len(lines):
        raise QuickstartError(number + 1, "the step's fenced block is never closed")
    commands = [text for _, text in body if text.strip()]
    if not commands:
        raise QuickstartError(number + 1, "the step's fenced block holds no command")
    if len(body) != 1:
        raise QuickstartError(number + 1, "the step's fenced block holds %d lines; a step "
                              "is exactly one command line" % len(body))
    line, text = body[0]
    text = text.strip()
    if text.endswith("\\"):
        raise QuickstartError(line, "the step's command ends in a backslash; a step is "
                              "exactly one command line")
    return Step(kind, text, e2e, line), cursor + 1


def parse(text):
    """Every marked step of the page ``text``, in order, as :class:`Step`.

    Raises :class:`QuickstartError` on a marker with no fence right after it, a
    fence of more or fewer than one command line, an unknown kind, an unknown e2e
    name, a malformed marker, or a fence that is never closed. A marker inside an
    unmarked fenced block is example text, not a step.
    """
    lines = text.splitlines()
    steps = []
    opened = None
    opened_at = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if opened is not None:
            if _fence_close(line, opened):
                opened = None
            index += 1
            continue
        if line.strip().startswith(MARKER_PREFIX):
            step, index = _read_step(lines, index)
            steps.append(step)
            continue
        opened = _fence_open(line)
        opened_at = index + 1
        index += 1
    if opened is not None:
        raise QuickstartError(opened_at, "this fenced block is never closed, so nothing "
                              "after it can be read")
    return steps


def check_count(steps):
    """Raise :class:`QuickstartError` unless there are 1 to :data:`MAX_STEPS` steps (BR-2)."""
    if not steps:
        raise QuickstartError(None, "the page has no marked steps")
    if len(steps) > MAX_STEPS:
        raise QuickstartError(steps[MAX_STEPS].line, "%d steps, more than the %d a newcomer "
                              "may type (BR-2)" % (len(steps), MAX_STEPS))


def verified(text):
    """The page's one ``quickstart-verified`` marker: None for ``none``, else :class:`Verified`.

    Raises :class:`QuickstartError` when the marker is missing, appears twice, or
    is in neither form.
    """
    found = []
    opened = None
    for number, line in enumerate(text.splitlines(), 1):
        if opened is not None:
            if _fence_close(line, opened):
                opened = None
            continue
        if line.strip().startswith(VERIFIED_PREFIX):
            match = VERIFIED_RE.match(line.rstrip())
            if not match:
                raise QuickstartError(number, "malformed quickstart-verified marker %r: write "
                                      "'<!-- quickstart-verified: none -->' or '<!-- "
                                      "quickstart-verified: release=X.Y.Z minutes=N "
                                      "date=YYYY-MM-DD -->'" % line.strip())
            found.append((number, match))
            continue
        opened = _fence_open(line)
    if not found:
        raise QuickstartError(None, "the page has no quickstart-verified marker")
    if len(found) > 1:
        raise QuickstartError(found[1][0], "a second quickstart-verified marker; the first "
                              "is on line %d" % found[0][0])
    number, match = found[0]
    if match.group("none"):
        return None
    try:
        datetime.datetime.strptime(match.group("date"), "%Y-%m-%d")
    except ValueError:
        raise QuickstartError(number, "%r is not a calendar date" % match.group("date"))
    return Verified(match.group("release"), int(match.group("minutes")), match.group("date"))


def timing_sentence(record):
    """The visible sentence the page carries for a :func:`verified` result."""
    if record is None:
        return NOT_MEASURED
    return "Timing: a run took %d %s on release %s, measured on %s." % (
        record.minutes, "minute" if record.minutes == 1 else "minutes", record.release,
        record.date)


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def load(path=None):
    """The steps of the page at ``path``, by default :data:`DEFAULT_PAGE`."""
    return parse(_read(path or DEFAULT_PAGE))


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] in ("-h", "--help"):
        print("usage: python3 tools/launch/quickstart_steps.py [PAGE]")
        return 0
    if len(args) > 1:
        sys.stderr.write("usage: python3 tools/launch/quickstart_steps.py [PAGE]\n")
        return 2
    path = args[0] if args else DEFAULT_PAGE
    try:
        text = _read(path)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("quickstart_steps: cannot read %s: %s\n" % (path, exc))
        return 2
    try:
        steps = parse(text)
        check_count(steps)
        record = verified(text)
    except QuickstartError as exc:
        sys.stderr.write("quickstart_steps: %s: refused: %s\n" % (path, exc))
        return 1
    for number, step in enumerate(steps, 1):
        tag = step.kind if step.e2e is None else "%s e2e=%s" % (step.kind, step.e2e)
        print("%d. [%s] %s" % (number, tag, step.text))
    print("steps=%d" % len(steps))
    if record is None:
        print("verified=none")
    else:
        print("verified=release=%s minutes=%d date=%s" % record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
