#!/usr/bin/env python3
"""The quickstart e2e's outcome checks (REQ-672 BR-9, architecture ADR-5).

Five named checks judge a quickstart run from the disk and the forge, never from the
model's wording. The one piece of model text any of them reads is a line that begins
``NO_ENTRY:`` anywhere in the last step's stream-json transcript, which is how
``/adlc:wrapup`` says it wrote no lesson.

==========================  ====================================================
``plugin-installed``        ``claude plugin list --json`` in the sandbox lists the
                            plugin the page installs, not disabled
``adlc-scaffold``           ``.adlc/context/`` in the project holds a ``.md`` file
``lite-req``                a ``.adlc/specs/REQ-*/requirement.md`` whose frontmatter
                            says exactly ``lane: "lite"`` and has no
                            ``lane_escalated``: the copy on ``origin/main`` when the
                            file is there, else the working copy
``pr-merged``               ``gh pr list --state merged`` on the throwaway repo shows
                            a PR from a branch that names the run's REQ id
``lesson-or-no-entry``      a ``LESSON-*.md`` under ``.adlc/knowledge/lessons/`` (on
                            disk, or on ``origin/main``), or the ``NO_ENTRY:`` line
==========================  ====================================================

:func:`setup_pushed` is a sixth check, a precondition rather than a BR-9 outcome: the
driver runs it just before the last step, because ``/adlc:proceed`` branches from
``origin/main`` and step 6's answer asks ``/adlc:init`` to commit and push its setup.

``origin/main`` is read only after the driver's ``git fetch origin`` succeeded, which
the caller says with ``fetched=True``. Otherwise ``lite-req`` and ``setup-pushed`` fail
with :data:`NOT_FETCHED`, and ``lesson-or-no-entry`` does too unless a lesson on disk or
the ``NO_ENTRY:`` line decides it: a stale ref never passes a check, and the working copy
is never read in its place.

Every check takes paths and an injected command runner, ``run(argv, cwd)``, which
returns ``(returncode, stdout, stderr)`` and resolves ``argv[0]`` itself. A check
returns a :class:`Result`; one that cannot establish its outcome fails, with the
reason, and never passes by default (LESSON-581). Python 3.9, standard library only.
"""

import collections
import glob
import json
import os
import re

PLUGIN_INSTALLED = "plugin-installed"
ADLC_SCAFFOLD = "adlc-scaffold"
LITE_REQ = "lite-req"
PR_MERGED = "pr-merged"
LESSON_OR_NO_ENTRY = "lesson-or-no-entry"
#: The BR-9 outcomes, in the order a run produces them.
OUTCOMES = (PLUGIN_INSTALLED, ADLC_SCAFFOLD, LITE_REQ, PR_MERGED, LESSON_OR_NO_ENTRY)
#: The precondition of the last step: the project setup is committed and on origin/main.
SETUP_PUSHED = "setup-pushed"

#: The one frontmatter value ``lite-req`` accepts.
LITE_LANE = '"lite"'
#: The key ``/adlc:proceed`` adds to a spec when it escalates it to the full lane.
LANE_ESCALATED = "lane_escalated"
#: The prefix ``/adlc:wrapup`` gives its reason for writing no lesson.
NO_ENTRY = "NO_ENTRY:"
#: What :func:`setup_pushed` ignores: step 7 writes the spec, and nothing pushes it.
SPECS_PREFIX = ".adlc/specs/"
#: The branch every lesson lands on once the PR merges.
MAIN_REF = "origin/main"
#: Why a check that reads :data:`MAIN_REF` fails when the fetch before it did not succeed.
NOT_FETCHED = "could not fetch origin, so %s is not known to be current" % MAIN_REF

#: One check's verdict. ``ok`` is True or False here; the driver uses None for a
#: check it did not run, which it reports as SKIPPED.
Result = collections.namedtuple("Result", "name ok reason")

_REQ_DIR_RE = re.compile(r"^(REQ-[0-9]+)(?:-|$)")
_LANE_RE = re.compile(r"^lane:[ \t]*(\"[^\"]*\"|'[^']*'|[^\s#]*)[ \t]*(?:#.*)?$")
_ESCALATED_RE = re.compile(r"^%s[ \t]*:" % LANE_ESCALATED)
_NO_ENTRY_RE = re.compile(r"^[ \t]*(?:[-*>][ \t]+)?`?" + re.escape(NO_ENTRY))
_EXCERPT = 160


def _excerpt(text):
    """The first non-blank line of ``text``, cut to a readable length."""
    for line in (text or "").splitlines():
        if line.strip():
            line = line.strip()
            return line if len(line) <= _EXCERPT else line[:_EXCERPT] + "..."
    return ""


def _failed(argv, code, stderr):
    detail = _excerpt(stderr)
    return "`%s` exited %d%s" % (" ".join(argv[:3]), code, ": " + detail if detail else "")


def _json_list(text):
    """``text`` parsed as a JSON list of objects, or None."""
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    return value


def req_dirs(project):
    """The names of the ``REQ-<n>[-slug]`` directories under the project's ``.adlc/specs/``."""
    specs = os.path.join(project, ".adlc", "specs")
    try:
        names = os.listdir(specs)
    except OSError:
        return []
    return sorted(name for name in names
                  if _REQ_DIR_RE.match(name) and os.path.isdir(os.path.join(specs, name)))


def req_id(dirname):
    """``REQ-001`` for the directory ``REQ-001-greet-name``."""
    match = _REQ_DIR_RE.match(dirname)
    if not match:
        raise ValueError("%r is not a REQ directory" % dirname)
    return match.group(1)


def _frontmatter(text):
    """The lines after a leading ``---``, up to the next; none when there is no frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    found = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        found.append(line.rstrip())
    return found


def lane_of(text):
    """The raw value of the ``lane:`` key in the frontmatter of ``text``, or None.

    The value is returned as written, quotes included, so ``lane: "lite"`` gives
    ``'"lite"'`` and ``lane: lite`` gives ``'lite'``. Body text is never read.
    """
    for line in _frontmatter(text):
        match = _LANE_RE.match(line)
        if match:
            return match.group(1)
    return None


def escalated(text):
    """True when the frontmatter of ``text`` carries :data:`LANE_ESCALATED`."""
    return any(_ESCALATED_RE.match(line) for line in _frontmatter(text))


def plugin_installed(run, cwd, plugin_id):
    """``plugin-installed``: ``claude plugin list --json`` lists ``plugin_id``, enabled."""
    argv = ["claude", "plugin", "list", "--json"]
    code, out, err = run(argv, cwd)
    if code != 0:
        return Result(PLUGIN_INSTALLED, False, _failed(argv, code, err))
    entries = _json_list(out)
    if entries is None:
        return Result(PLUGIN_INSTALLED, False, "`claude plugin list --json` did not print a "
                      "JSON list of plugins")
    found = [entry for entry in entries if entry.get("id") == plugin_id]
    if not found:
        return Result(PLUGIN_INSTALLED, False, "`claude plugin list --json` lists %d plugin(s), "
                      "and %s is not one of them" % (len(entries), plugin_id))
    if found[0].get("enabled") is False:
        return Result(PLUGIN_INSTALLED, False, "%s is installed but disabled" % plugin_id)
    return Result(PLUGIN_INSTALLED, True, "%s is installed (version %s)"
                  % (plugin_id, found[0].get("version", "unknown")))


def adlc_scaffold(project):
    """``adlc-scaffold``: ``/adlc:init`` wrote the project context under ``.adlc/context/``.

    ``.adlc/`` alone is not enough: ``/adlc:spec`` creates ``.adlc/specs/`` whether or
    not ``/adlc:init`` ran.
    """
    context = os.path.join(project, ".adlc", "context")
    if not os.path.isdir(os.path.join(project, ".adlc")):
        return Result(ADLC_SCAFFOLD, False, "the project has no .adlc/ directory")
    written = sorted(os.path.basename(path) for path in glob.glob(os.path.join(context, "*.md"))
                     if os.path.isfile(path))
    if not written:
        return Result(ADLC_SCAFFOLD, False, ".adlc/ exists, but .adlc/context/ holds no .md "
                      "file, so /adlc:init did not write the project context")
    return Result(ADLC_SCAFFOLD, True, ".adlc/context/ holds %s" % ", ".join(written))


def _spec_copy(project, name, run):
    """``(text, where)``: REQ ``name``'s ``requirement.md`` as ``origin/main`` holds it,
    else the working copy's; ``text`` is None when neither can be read."""
    rel = "%s%s/requirement.md" % (SPECS_PREFIX, name)
    where = "in the working copy"
    if run is not None:
        code, out, _err = run(["git", "show", "%s:%s" % (MAIN_REF, rel)], project)
        if code == 0:
            return out, "on " + MAIN_REF
        where += ", not on " + MAIN_REF
    try:
        with open(os.path.join(project, rel), encoding="utf-8") as handle:
            return handle.read(), where
    except (OSError, UnicodeDecodeError):
        return None, where


def lite_req(project, run=None, *, fetched=False):
    """``lite-req``: a REQ whose ``requirement.md`` has ``lane: "lite"`` exactly, and no
    ``lane_escalated``.

    With ``run``, the copy on ``origin/main`` decides when the file is there; the working
    copy decides only when it is not. An escalation rewrites the spec on the feature
    branch, which reaches ``origin/main`` when the PR merges, while the project's own
    checkout keeps the ``lite`` copy ``/adlc:spec`` wrote. The driver fetches first, and
    unless ``fetched`` says that fetch succeeded the check fails with
    :data:`NOT_FETCHED`, reading neither the stale ref nor the working copy.
    """
    if run is not None and not fetched:
        return Result(LITE_REQ, False, NOT_FETCHED)
    names = req_dirs(project)
    if not names:
        return Result(LITE_REQ, False, "no .adlc/specs/REQ-*/ directory in the project")
    seen = []
    for name in names:
        text, where = _spec_copy(project, name, run)
        if text is None:
            seen.append("%s has no readable requirement.md %s" % (name, where))
            continue
        lane, raised = lane_of(text), escalated(text)
        if lane == LITE_LANE and not raised:
            return Result(LITE_REQ, True, "%s has lane: %s %s" % (name, LITE_LANE, where))
        state = "no lane" if lane is None else "lane: " + lane
        seen.append("%s has %s%s %s" % (name, state, " and " + LANE_ESCALATED if raised else "",
                                        where))
    return Result(LITE_REQ, False, "no REQ has lane: %s without %s (%s)"
                  % (LITE_LANE, LANE_ESCALATED, "; ".join(seen)))


def pr_merged(run, cwd, repo, req):
    """``pr-merged``: the throwaway ``repo`` has a merged PR from a branch naming ``req``.

    The branch is matched so a merged PR the run did not make cannot pass the check.
    """
    if not req:
        return Result(PR_MERGED, False, "no REQ id in .adlc/specs/, so no pull request can be "
                      "tied to this run")
    argv = ["gh", "pr", "list", "--repo", repo, "--state", "merged", "--json",
            "number,headRefName"]
    code, out, err = run(argv, cwd)
    if code != 0:
        return Result(PR_MERGED, False, _failed(argv, code, err))
    prs = _json_list(out)
    if prs is None:
        return Result(PR_MERGED, False, "`gh pr list` did not print a JSON list")
    naming = re.compile(r"(?<![0-9])%s(?![0-9])" % re.escape(req))
    for pr in prs:
        branch = pr.get("headRefName")
        if isinstance(branch, str) and naming.search(branch):
            return Result(PR_MERGED, True, "PR #%s from %s is merged in %s"
                          % (pr.get("number", "?"), branch, repo))
    if prs:
        return Result(PR_MERGED, False, "%s has %d merged PR(s), none from a branch naming %s"
                      % (repo, len(prs), req))
    return Result(PR_MERGED, False, "%s has no merged pull request" % repo)


def no_entry_line(text):
    """The first line of ``text`` that begins ``NO_ENTRY:`` (a list or quote mark aside)."""
    for line in (text or "").splitlines():
        if _NO_ENTRY_RE.match(line):
            return line.strip()
    return None


def result_event(stream):
    """The last ``"type": "result"`` object of a stream-json transcript, or None."""
    found = None
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            found = event
    return found


def _strings(value):
    """Every string inside a decoded JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, dict)):
        for item in value.values() if isinstance(value, dict) else value:
            for text in _strings(item):
                yield text


def transcript_no_entry(transcript):
    """The first ``NO_ENTRY:`` line in a stream-json transcript, or None.

    Each JSON line is decoded and every string in it read line by line, so a message,
    a tool result or the final result counts alike; a line that is not JSON is read as
    it is.
    """
    for raw in (transcript or "").splitlines():
        try:
            texts = _strings(json.loads(raw))
        except ValueError:
            texts = [raw]
        for text in texts:
            line = no_entry_line(text)
            if line:
                return line
    return None


def lesson_or_no_entry(project, transcript, run=None, *, fetched=False):
    """``lesson-or-no-entry``: a lesson file, or the wrapup's ``NO_ENTRY:`` line.

    The lesson is looked for in the project's working tree, then, when ``run`` is
    given, on ``origin/main``: ``/adlc:proceed`` writes it in its own worktree and
    merges it there. ``origin/main`` is read only when ``fetched`` says the driver's
    fetch succeeded; when it did not, and nothing else decides the check, it fails with
    :data:`NOT_FETCHED`. ``transcript`` is the last step's whole stream-json output, and
    only the last step's: the wrapup runs inside ``/adlc:proceed``.
    """
    lessons = os.path.join(project, ".adlc", "knowledge", "lessons")
    found = sorted(os.path.basename(path) for path in glob.glob(os.path.join(lessons, "LESSON-*.md"))
                   if os.path.isfile(path))
    if found:
        return Result(LESSON_OR_NO_ENTRY, True, "lesson %s" % found[0])
    if run is not None and fetched:
        code, out, _err = run(["git", "ls-tree", "-r", "--name-only", MAIN_REF, "--",
                               ".adlc/knowledge/lessons"], project)
        merged = sorted(os.path.basename(path) for path in out.splitlines()
                        if re.match(r"^LESSON-.*\.md$", os.path.basename(path))) if code == 0 else []
        if merged:
            return Result(LESSON_OR_NO_ENTRY, True, "lesson %s on %s" % (merged[0], MAIN_REF))
    line = transcript_no_entry(transcript)
    if line:
        return Result(LESSON_OR_NO_ENTRY, True, "the last step's transcript has the line %s"
                      % _excerpt(line))
    missing = ("no LESSON-*.md under .adlc/knowledge/lessons/, and no line of the last "
               "step's transcript begins %s" % NO_ENTRY)
    if run is not None and not fetched:
        return Result(LESSON_OR_NO_ENTRY, False, "%s; %s" % (NOT_FETCHED, missing))
    return Result(LESSON_OR_NO_ENTRY, False, missing)


def _outside_specs(path):
    return not path.startswith(SPECS_PREFIX)


def setup_pushed(run, project, *, fetched=False):
    """``setup-pushed``: nothing outside ``.adlc/specs/`` is uncommitted or unpushed.

    Unpushed is judged against ``origin/main``, so unless ``fetched`` says the fetch
    before this check succeeded it fails with :data:`NOT_FETCHED`.
    """
    if not fetched:
        return Result(SETUP_PUSHED, False, NOT_FETCHED)
    argv = ["git", "status", "--porcelain", "--untracked-files=all"]
    code, out, err = run(argv, project)
    if code != 0:
        return Result(SETUP_PUSHED, False, _failed(argv, code, err))
    dirty = []
    for line in out.splitlines():
        path = line[3:].split(" -> ")[-1].strip('"')
        if line.strip() and _outside_specs(path):
            dirty.append(path)
    if dirty:
        return Result(SETUP_PUSHED, False, "%d path(s) outside %s are uncommitted before the "
                      "last step, such as %s" % (len(dirty), SPECS_PREFIX, dirty[0]))
    argv = ["git", "diff", "--name-only", MAIN_REF, "HEAD"]
    code, out, err = run(argv, project)
    if code != 0:
        return Result(SETUP_PUSHED, False, "%s is not known in the project, so main was not "
                      "pushed: %s" % (MAIN_REF, _failed(argv, code, err)))
    unpushed = [path for path in out.splitlines() if path and _outside_specs(path)]
    if unpushed:
        return Result(SETUP_PUSHED, False, "%d committed path(s) outside %s are not on %s, "
                      "such as %s" % (len(unpushed), SPECS_PREFIX, MAIN_REF, unpushed[0]))
    return Result(SETUP_PUSHED, True, "the project setup is committed and on %s" % MAIN_REF)


def run_all(run, project, plugin_id, repo, transcript, cwd=None, *, fetched=False):
    """The five BR-9 outcome checks, in :data:`OUTCOMES` order.

    ``transcript`` is the last step's stream-json output. ``cwd`` is where the ``claude``
    and ``gh`` reads run; it defaults to ``project``. ``fetched`` is True only when the
    ``git fetch origin`` just before succeeded: without it no check reads ``origin/main``.
    The REQ id ``pr-merged`` matches is the project's one ``.adlc/specs/REQ-*/``
    directory; with none, or several, that check fails and says so.
    """
    cwd = cwd or project
    names = req_dirs(project)
    if len(names) > 1:
        merged = Result(PR_MERGED, False, "%d REQ directories in .adlc/specs/ (%s), so no pull "
                        "request can be tied to this run" % (len(names), ", ".join(names)))
    else:
        merged = pr_merged(run, cwd, repo, req_id(names[0]) if names else None)
    return [
        plugin_installed(run, cwd, plugin_id),
        adlc_scaffold(project),
        lite_req(project, run, fetched=fetched),
        merged,
        lesson_or_no_entry(project, transcript, run, fetched=fetched),
    ]
