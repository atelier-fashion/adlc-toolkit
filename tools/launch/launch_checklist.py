#!/usr/bin/env python3
"""The launch checklist's parser and validator (REQ-672 ADR-8, BR-5).

``docs/launch-checklist.md`` holds one table with exactly these columns::

    | id | item | depends on | owner | status | link |

Each row is one launch item. ``depends on`` is ``none`` or a comma-separated list of
ids, ``status`` is one of :data:`STATUSES`, and ``link`` is ``none`` or one markdown
link. :func:`validate` holds the table to these rules:

- every id in :data:`REQUIRED_IDS` is present, once;
- every row has an item, an owner and a known status;
- a row depends only on ids of rows above it, so the table is in dependency order;
- each row of :data:`POST_IDS` depends on every id of :data:`LAUNCH_GATES`, directly or
  through a row that does (the maintainer's decision of one coordinated launch week),
  is owned by the maintainer, and links a draft under ``docs/launch/`` that exists;
- a row is ``live`` or ``done`` only when every row it depends on is;
- a relative link names a file that exists, and a link to an address (a URL) appears
  only once its row is ``live`` or ``done``: before that, the thing is not reachable;
- a ``live`` row, other than a post row, links the address where it is live.

The ``readme-first-screen`` lint in ``tools/lint-skills`` reads the same table with a
parser of its own, to allow a README link to the Space, the dataset or the article only
once that row is ``live``. It imports nothing from here: it mirrors :data:`COLUMNS`, the
live status (:data:`STATUS_LIVE`) and the three Hugging Face row ids (``space``,
``dataset``, ``article``), which ``tools/lint-skills/tests/test_newcomer_docs.py`` holds
equal to these.

Run by path::

    python3 tools/launch/launch_checklist.py [PATH]

PATH defaults to the ``docs/launch-checklist.md`` beside this toolkit copy. It prints
each row and ``launch-checklist: N rows, V violations``. Exit 0 when there is no
violation, 1 when there is one (each goes to stderr) or the table is malformed, 2 when
the file cannot be read, holds no row, or the arguments are wrong. Python 3.9, standard
library only.
"""

import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
#: The real checklist, resolved from this file's own location.
DEFAULT_CHECKLIST = os.path.join(TOOLKIT, "docs", "launch-checklist.md")

#: The table's header, cell for cell.
COLUMNS = ("id", "item", "depends on", "owner", "status", "link")

#: Not started, or not yet checked.
STATUS_PENDING = "pending"
#: Built and checked, waiting only on a dependency or on the launch week.
STATUS_READY = "ready"
#: Published and reachable by anyone.
STATUS_LIVE = "live"
#: A one-off action completed.
STATUS_DONE = "done"
STATUSES = (STATUS_PENDING, STATUS_READY, STATUS_LIVE, STATUS_DONE)
#: The statuses of a row whose work has happened.
FINISHED = (STATUS_LIVE, STATUS_DONE)

#: What the launch week waits for: one coordinated launch week, after the plugin
#: release, the Space, the dataset and the article are all live (maintainer, 2026-11-23).
LAUNCH_GATES = ("plugin-release", "space", "dataset", "article")

#: The rows that speak for the project in public: the three posts and the pull requests
#: to community lists. Each links its draft and is done by the maintainer by hand.
POST_IDS = ("post-show-hn", "post-reddit-claudeai", "post-x", "awesome-list-prs")

#: Every item BR-5 and ADR-8 name. A checklist may hold more rows than these.
REQUIRED_IDS = (
    "plugin-release",
    "directory-submission",
    "space",
    "dataset",
    "article",
    "readme-quickstart-verified",
    "demo-recording",
    "post-show-hn",
    "post-reddit-claudeai",
    "post-x",
    "awesome-list-prs",
    "adoption-snapshot-scheduled",
)

#: The owner of a post row (REQ-672 Permissions: the maintainer posts, by hand).
OWNER_MAINTAINER = "maintainer"
#: The ``depends on`` cell of a row that depends on nothing.
NO_DEPENDENCY = "none"
#: The ``link`` cell of a row that links nothing.
NO_LINK = "none"
#: Where post drafts live, relative to the checklist's directory.
DRAFT_DIR = "launch"

ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"^\[(?P<text>[^\[\]]+)\]\((?P<target>[^()\s]+)\)$")
#: A link target with a scheme (``https:``, ``mailto:``) is an address, not a file.
ADDRESS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

RULE_NO_ROWS = "no-rows"
RULE_MISSING_ID = "missing-required-id"
RULE_DUPLICATE_ID = "duplicate-id"
RULE_MALFORMED_ID = "malformed-id"
RULE_NO_ITEM = "no-item"
RULE_NO_OWNER = "no-owner"
RULE_POST_OWNER = "post-owner"
RULE_UNKNOWN_STATUS = "unknown-status"
RULE_EMPTY_DEPENDENCY = "empty-dependency"
RULE_SELF_DEPENDENCY = "self-dependency"
RULE_LATER_DEPENDENCY = "dependency-on-later-row"
RULE_UNKNOWN_DEPENDENCY = "unknown-dependency"
RULE_LAUNCH_GATE = "post-before-launch-gate"
RULE_FINISHED_EARLY = "finished-before-dependency"
RULE_MALFORMED_LINK = "malformed-link"
RULE_LINK_MISSING = "link-target-missing"
RULE_ADDRESS_EARLY = "address-before-live"
RULE_LIVE_WITHOUT_ADDRESS = "live-without-address"
RULE_MISSING_DRAFT = "missing-draft"

#: One table row. ``line`` is 1-based; ``depends`` is a tuple of the comma-separated
#: names as written, empty for ``none``.
Row = collections.namedtuple("Row", "line id item depends owner status link")
#: One broken rule. ``line`` is the row's line, or None for the whole table.
Violation = collections.namedtuple("Violation", "line id rule message")


class ChecklistError(ValueError):
    """The table is malformed. ``line`` is 1-based, or None for the whole page."""

    def __init__(self, line, message):
        self.line = line
        self.message = message
        super().__init__("line %d: %s" % (line, message) if line else message)


def _cells(line):
    """The stripped cells of a pipe-table line."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in _CELL_SPLIT_RE.split(body)]


def _dependencies(cell):
    if cell == NO_DEPENDENCY:
        return ()
    return tuple(name.strip() for name in cell.split(","))


def _closes(line, fence):
    """True when ``line`` closes a fenced block opened by the run ``fence`` (```` ``` ````)."""
    stripped = line.strip()
    return (len(stripped) >= len(fence) and stripped == fence[0] * len(stripped)
            and not line.startswith("    "))


def parse(text):
    """Every row of the checklist table in ``text``, in order, as :class:`Row`.

    The table is the one whose header is :data:`COLUMNS`; a header inside a fenced
    block is example text. Returns ``[]`` when there is no such table or it has no row.
    Raises :class:`ChecklistError` on a missing or malformed separator line, a row
    whose cell count is not six, or a second table with the same header.
    """
    lines = text.splitlines()
    rows = []
    header_at = None
    fence = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if fence is not None:
            if _closes(line, fence):
                fence = None
            index += 1
            continue
        match = _FENCE_RE.match(line)
        if match:
            fence = match.group(1)
            index += 1
            continue
        if not (line.lstrip().startswith("|") and tuple(_cells(line)) == COLUMNS):
            index += 1
            continue
        if header_at is not None:
            raise ChecklistError(index + 1, "a second table with the checklist's columns; the "
                                 "first is on line %d" % header_at)
        header_at = index + 1
        separator = lines[index + 1] if index + 1 < len(lines) else ""
        cells = _cells(separator)
        if len(cells) != len(COLUMNS) or not all(_SEPARATOR_CELL_RE.match(c) for c in cells):
            raise ChecklistError(index + 2, "the header is not followed by a separator line "
                                 "of %d cells such as |---|" % len(COLUMNS))
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            cells = _cells(lines[index])
            if len(cells) != len(COLUMNS):
                raise ChecklistError(index + 1, "%d cells; a checklist row has %d: %s"
                                     % (len(cells), len(COLUMNS), " | ".join(COLUMNS)))
            row_id, item, depends, owner, status, link = cells
            rows.append(Row(index + 1, row_id, item, _dependencies(depends), owner, status,
                            link))
            index += 1
    return rows


def link_target(cell):
    """The target of a ``link`` cell: None for ``none``, else the markdown link's target.

    Raises ValueError when the cell is neither ``none`` nor one markdown link.
    """
    if cell == NO_LINK:
        return None
    match = LINK_RE.match(cell)
    if not match:
        raise ValueError("link %r is neither %r nor one markdown link [text](target)"
                         % (cell, NO_LINK))
    return match.group("target")


def is_address(target):
    """True when a link target is an address with a scheme, not a file path."""
    return bool(ADDRESS_RE.match(target))


def _file_of(target, base_dir):
    """The absolute file a relative link target names, without its fragment or query."""
    path = re.split(r"[#?]", target, 1)[0]
    if not path or path.startswith("/"):
        return None
    return os.path.normpath(os.path.join(base_dir, path))


def _inside(path, directory):
    directory = os.path.normpath(directory)
    try:
        return os.path.commonpath([path, directory]) == directory and path != directory
    except ValueError:
        return False


def _check_link(row, base_dir, out):
    """Append the violations of ``row``'s link cell to ``out``."""
    is_post = row.id in POST_IDS
    try:
        target = link_target(row.link)
    except ValueError as exc:
        out.append(Violation(row.line, row.id, RULE_MISSING_DRAFT if is_post
                             else RULE_MALFORMED_LINK, str(exc)))
        return
    if is_post:
        drafts = os.path.join(base_dir, DRAFT_DIR)
        path = None if target is None or is_address(target) else _file_of(target, base_dir)
        if path is None or not _inside(path, drafts) or not os.path.isfile(path):
            out.append(Violation(row.line, row.id, RULE_MISSING_DRAFT,
                                 "a post row links its draft, an existing file under %s/; "
                                 "the link is %r" % (DRAFT_DIR, row.link)))
        return
    if target is None:
        if row.status == STATUS_LIVE:
            out.append(Violation(row.line, row.id, RULE_LIVE_WITHOUT_ADDRESS,
                                 "the row is live but links nothing; link the address "
                                 "where it is live"))
        return
    if is_address(target):
        if row.status not in FINISHED:
            out.append(Violation(row.line, row.id, RULE_ADDRESS_EARLY,
                                 "links the address %r while the row is %s; until it is "
                                 "live, link a file in this repository or none"
                                 % (target, row.status)))
        return
    if row.status == STATUS_LIVE:
        out.append(Violation(row.line, row.id, RULE_LIVE_WITHOUT_ADDRESS,
                             "the row is live but links the file %r; link the address "
                             "where it is live" % target))
    path = _file_of(target, base_dir)
    if path is None:
        out.append(Violation(row.line, row.id, RULE_MALFORMED_LINK,
                             "link target %r is not a relative path" % target))
    elif not os.path.isfile(path):
        out.append(Violation(row.line, row.id, RULE_LINK_MISSING,
                             "link target %r names no file (looked for %s)" % (target, path)))


def validate(rows, base_dir):
    """Every rule ``rows`` break, as a list of :class:`Violation`; empty when none.

    ``base_dir`` is the directory relative links resolve against: the checklist's own.
    No rows is itself a violation, so an empty or unreadable table never passes.
    """
    out = []
    if not rows:
        return [Violation(None, None, RULE_NO_ROWS, "no checklist rows were read; the "
                          "table needs the columns %s" % " | ".join(COLUMNS))]
    first_line = {}
    for row in rows:
        first_line.setdefault(row.id, row.line)
    above = {}
    reach = {}
    for row in rows:
        if not ID_RE.match(row.id):
            out.append(Violation(row.line, row.id, RULE_MALFORMED_ID,
                                 "id %r is not lower-case words joined by hyphens" % row.id))
        if row.id in above:
            out.append(Violation(row.line, row.id, RULE_DUPLICATE_ID,
                                 "id %r is already used on line %d" % (row.id,
                                                                       above[row.id].line)))
        if not row.item:
            out.append(Violation(row.line, row.id, RULE_NO_ITEM, "the item is empty"))
        if not row.owner:
            out.append(Violation(row.line, row.id, RULE_NO_OWNER, "the owner is empty"))
        elif row.id in POST_IDS and row.owner != OWNER_MAINTAINER:
            out.append(Violation(row.line, row.id, RULE_POST_OWNER,
                                 "owner %r; the maintainer posts by hand, so a post row's "
                                 "owner is %r" % (row.owner, OWNER_MAINTAINER)))
        if row.status not in STATUSES:
            out.append(Violation(row.line, row.id, RULE_UNKNOWN_STATUS,
                                 "status %r is not one of %s" % (row.status,
                                                                 ", ".join(STATUSES))))
        reached = set()
        for name in row.depends:
            if not name:
                out.append(Violation(row.line, row.id, RULE_EMPTY_DEPENDENCY,
                                     "an empty name in depends on; write %r when the row "
                                     "depends on nothing" % NO_DEPENDENCY))
            elif name == row.id:
                out.append(Violation(row.line, row.id, RULE_SELF_DEPENDENCY,
                                     "the row depends on itself"))
            elif name in above:
                reached.add(name)
                reached.update(reach.get(name, ()))
                if row.status in FINISHED and above[name].status not in FINISHED:
                    out.append(Violation(row.line, row.id, RULE_FINISHED_EARLY,
                                         "the row is %s but %r, which it depends on, is %s"
                                         % (row.status, name, above[name].status)))
            elif name in first_line:
                out.append(Violation(row.line, row.id, RULE_LATER_DEPENDENCY,
                                     "depends on %r, which is on line %d, below it; a row "
                                     "depends only on rows above it" % (name,
                                                                        first_line[name])))
            elif name == NO_DEPENDENCY:
                out.append(Violation(row.line, row.id, RULE_UNKNOWN_DEPENDENCY,
                                     "%r together with ids; write it alone, or only the ids"
                                     % NO_DEPENDENCY))
            else:
                out.append(Violation(row.line, row.id, RULE_UNKNOWN_DEPENDENCY,
                                     "depends on %r, which no row has" % name))
        if row.id in POST_IDS:
            missing = [gate for gate in LAUNCH_GATES if gate not in reached]
            if missing:
                out.append(Violation(row.line, row.id, RULE_LAUNCH_GATE,
                                     "a post waits for the launch week, but this row does "
                                     "not depend on %s, directly or through a row that does"
                                     % ", ".join(missing)))
        _check_link(row, base_dir, out)
        if row.id not in above:
            above[row.id] = row
            reach[row.id] = reached
    for required in REQUIRED_IDS:
        if required not in above:
            out.append(Violation(None, required, RULE_MISSING_ID,
                                 "the required item %r has no row" % required))
    return out


def format_violation(violation):
    """One violation as a line: ``line N: <id>: <rule>: <message>``."""
    where = "line %d: " % violation.line if violation.line else ""
    who = "%s: " % violation.id if violation.id else ""
    return "%s%s%s: %s" % (where, who, violation.rule, violation.message)


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def load(path=None):
    """The rows of the checklist at ``path``, by default :data:`DEFAULT_CHECKLIST`."""
    return parse(_read(path or DEFAULT_CHECKLIST))


USAGE = "usage: python3 tools/launch/launch_checklist.py [PATH]"


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if len(args) > 1:
        sys.stderr.write(USAGE + "\n")
        return 2
    path = args[0] if args else DEFAULT_CHECKLIST
    try:
        text = _read(path)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("launch-checklist: cannot read %s: %s\n" % (path, exc))
        return 2
    try:
        rows = parse(text)
    except ChecklistError as exc:
        sys.stderr.write("launch-checklist: %s: refused: %s\n" % (path, exc))
        return 1
    if not rows:
        sys.stderr.write("launch-checklist: %s: 0 rows: no table with the columns %s, or "
                         "it has no row; nothing was checked\n" % (path, " | ".join(COLUMNS)))
        return 2
    violations = validate(rows, os.path.dirname(os.path.abspath(path)))
    for row in rows:
        print("%s [%s] depends on: %s" % (row.id, row.status,
                                          ", ".join(row.depends) or NO_DEPENDENCY))
    for violation in violations:
        sys.stderr.write("launch-checklist: %s\n" % format_violation(violation))
    print("launch-checklist: %d rows, %d violations" % (len(rows), len(violations)))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
