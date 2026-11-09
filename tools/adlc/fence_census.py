#!/usr/bin/env python3
"""fence_census — every shell fence an exec run can meet, each with an id and a route (REQ-682).

A **fence** is a fenced block whose info string is ``sh``, ``bash`` or ``shell``, indented or
not. An unlabelled block is prose, so the ``worktree remove`` example in ``phase-0-setup.md``
item 4b is not a fence. Fences are read from the **view** of each file in :data:`EXEC_FILES`:
the bytes the model is given. The pipeline sources are read after ``exec_prompt``'s cuts and
rewrites, ``wrapup/SKILL.md`` after the close-out's, and every other file whole, as
``fence-run show`` prints it.

**Id** (ADR-2): ``<toolkit-relative path>#<ordinal>:<sha8>``. The ordinal is the 1-based index
among the shell fences of that view, and ``sha8`` the first eight hex digits of the SHA-256 of
the fence body as the view holds it, before any runner transform, so an id is the same on
every machine and changes when the fence does.

**Route** (ADR-6), decided in this order:

- ``excised`` — the id is in :data:`EXCISED`, or the body names a BR-24 token or a deny-tier
  spelling. The model is told, in one line, that the fence does not run under ``--exec``.
- ``engine`` — the id is in :data:`ENGINE`: the orchestrator did the work before launch.
- ``direct`` — ``exec_matcher`` admits every statement over the ExecPolicy, as written, or
  with the exec notes' ``git -C <worktree>`` dropped and sample values in its placeholders.
- ``runner`` — :func:`transform` accepts the body (every placeholder and free variable is in
  the closed tables, and in a position where its value stays data) and the static reach
  audit finds nothing (:func:`reach`). The model runs it as ``fence-run run <id>``.

Anything else is **unrouted**, and an exec prompt holding it is refused (BR-8). The census is
computed from toolkit text alone, so ``fence-run`` recomputes it on every call and trusts no
manifest, cache or environment variable (ADR-2, BR-5).

**Values** (ADR-3): a placeholder ``<name>`` or a free shell variable ``$name`` reaches the
fence only as an environment variable ``ADLC_ARG_<name>``, expanded once inside double quotes.
A placeholder is rewritten where its value cannot become code: a whole ``"<x>"`` or ``'<x>'``
token, a bare ``<x>`` word, or embedded in a double-quoted string or an unquoted word of a
statement whose command is not an interpreter (``sh``, ``eval``, ``awk``, ``sed``, …). This is
one position wider than ADR-3's three token shapes, and as safe: a quoted parameter expansion
is never re-read as shell, and the interpreter check keeps a value out of every string that is
code. A placeholder inside single quotes, a here-document, or an interpreter's arguments makes
the fence unroutable.

Standard library only.
"""

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import exec_matcher as em  # noqa: E402
import exec_prompt as ep  # noqa: E402
import harness_adapter as ha  # noqa: E402
import toolkit_root as tkr  # noqa: E402

SHELL_INFOS = ("sh", "bash", "shell")
_OPEN_RE = re.compile(r"^(\s*)```([A-Za-z0-9_+-]*)\s*$")
_CLOSE_RE = re.compile(r"^\s*```\s*$")

PIPELINE_FILES = ("proceed/SKILL.md",) + tuple(ep.PIPELINE_SOURCES)
CLOSEOUT_FILE = "wrapup/SKILL.md"
#: Every agent the delivered text, or a skill it sends the model to, dispatches by name.
EXEC_AGENTS = ("architecture-mapper", "architecture-reviewer", "correctness-reviewer",
               "feature-tracer", "integration-explorer", "lite-reviewer", "pipeline-runner",
               "quality-reviewer", "reflector", "security-auditor", "task-implementer",
               "test-auditor")
#: The closed exec file set (ADR-5). ``invoked_files`` holds it equal to what the delivered
#: text names, in both directions, so it cannot lag the text (LESSON-712).
EXEC_FILES = PIPELINE_FILES + (
    CLOSEOUT_FILE, "architect/SKILL.md", "manifest/SKILL.md", "review/SKILL.md",
    "spec/SKILL.md", "spec/references/intake-source-read.md",
    "spec/references/retrieval-body-read.md", "validate/SKILL.md",
) + tuple("agents/%s.md" % name for name in EXEC_AGENTS)

#: Files the delivered text names for one section only: the model is shown that section and
#: nothing else. The pipeline names ``agents/pipeline-runner.md`` for its blocker and
#: conflict-record schemas; the rest of that file is the legacy engine's, merge included.
SECTION_VIEWS = {
    "agents/pipeline-runner.md": ("## Blocker Handling", "### Bounded resolution (BUG-207)"),
}
#: Skills the text tells the operator, not the model, to run: never delivered.
USER_ONLY = {
    "init": "a remediation the text tells the operator to run before a pipeline: the exec "
            "engine refuses a REQ whose context files are missing, so the model never runs it",
}

_TRANSCRIPT = ("close-out rule 4: transcript discovery is skipped, and the lesson is drafted "
               "from the run evidence in this prompt")
_SPEC_TIME = (        "/spec's intake, retrieval reads and id allocation run when a spec is written, never "
        "inside an exec pipeline, which reads /spec only for its Step 1.6 scoring rule")

ENGINE = {
    "proceed/phase-0-setup.md#1": (
        "the orchestrator fetched origin in every touched repo before launch"),
    "proceed/phase-0-setup.md#3": (
        "the orchestrator checked `git worktree list` for a collision before launch"),
    "proceed/phase-0-setup.md#4": (
        "the orchestrator created this working copy on the REQ's branch before launch"),
}

EXCISED = {
    "proceed/phase-0-setup.md#2": (
        "the REQ id was allocated by /spec, and the orchestrator found this REQ's spec on the "
        "integration branch before it created the branch; the recheck needs the id written "
        "into the fence text, which the runner does not do"),
    "proceed/SKILL.md#3": (
        "the delegate pre-pass composes its steps 2 to 4 in one shell of your own, which no "
        "exec allow admits: under --exec the reviewers run without candidates (the fallback)"),
    "proceed/phases-telemetry.md#3": (
        "the findings record is your own JSON, and the runner binds no here-document: carry "
        "the Phase-5 findings in your final report instead"),
    "manifest/SKILL.md#2": (
        "the in-flight manifest is advisory, and the /sprint orchestrator ranked this batch "
        "before launch, as Step 0 item 4 says for a sprint run; an absent verdict never blocks"),
    "agents/test-auditor.md#1": (
        "an example search, not a step: run `find` yourself with the scope and name filled in"),
    "validate/SKILL.md#2": (
        "the standalone acknowledgement check: inside a pipeline, Phase 5 Step B runs it"),
    "wrapup/SKILL.md#5": _TRANSCRIPT,
    "wrapup/SKILL.md#6": _TRANSCRIPT,
    "wrapup/SKILL.md#7": _TRANSCRIPT,
    "spec/SKILL.md#2": _SPEC_TIME,
    "spec/SKILL.md#3": _SPEC_TIME,
    "spec/SKILL.md#4": _SPEC_TIME,
    "spec/SKILL.md#5": _SPEC_TIME,
    "spec/SKILL.md#7": _SPEC_TIME,
    "spec/references/intake-source-read.md#*": _SPEC_TIME,
    "spec/references/retrieval-body-read.md#*": _SPEC_TIME,
}

#: A placeholder: the argument name, the full-match pattern, and how it is supplied.
#: ``multi`` lets ``--flag "<name>"`` be bound once per value; ``file`` takes ``--arg-file``.
_PATH = r"/[A-Za-z0-9_.,@+/-]{1,1000}"
_REL_OR_ABS = r"/?[A-Za-z0-9_.,@+-][A-Za-z0-9_.,@+/-]{0,1000}"
_BRANCH = r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,200}"
_COMPONENT = r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,200}"
_LINE = r"[^\x00-\x1f\x7f]{1,240}"


#: Where a path value may point. A fence writes some of these (a state file) and reads the
#: others, so a free absolute path would be a write or a read the model's own file tools are
#: refused (BUG-265). ``cwd``: at or under the working directory. ``spec-dir``: that, or the
#: named file of a REQ's spec directory in any repo, which is where the primary-path
#: pipeline-state.json and the spec live. The working directory is the session's, which no
#: admitted command can change (`cd` is on no allowlist), so the check rests on no state the
#: model controls (BR-5).
_SPEC_FILE = r"^/(?:[A-Za-z0-9_.,@+-]+/)+\.adlc/specs/REQ-[0-9]{3,6}-[a-z0-9-]+/%s$"
SCOPES = {
    "state": re.compile(_SPEC_FILE % r"pipeline-state\.json"),
    "spec": re.compile(_SPEC_FILE % r"requirement\.md"),
    "tasks": re.compile(_SPEC_FILE % r"tasks"),
}


class Placeholder(object):
    __slots__ = ("key", "arg", "pattern", "multi", "file", "empty_ok", "path", "scope")

    def __init__(self, key, arg, pattern, multi=False, file=False, path=False, scope=None):
        self.key = key
        self.arg = arg
        self.pattern = re.compile("^(?:%s)$" % pattern, re.S)
        self.multi = multi
        self.file = file
        self.path = path
        self.scope = scope
        self.empty_ok = bool(self.pattern.match(""))

    def check_scope(self, value, cwd):
        """``None`` when a path value points where its scope allows, else why not."""
        if not self.scope or not value:
            return None
        base = os.path.realpath(cwd)
        real = os.path.realpath(os.path.join(cwd, value))
        if os.path.commonpath([real, base]) == base:
            return None
        rx = SCOPES.get(self.scope)
        if rx is not None and rx.match(value) and rx.match(real):
            return None
        return ("points outside the working directory%s" %
                (", and is not a REQ spec directory's %s" % self.scope if rx else ""))

    def check(self, value):
        """``None`` when ``value`` is admissible, else why not."""
        if "\x00" in value:
            return "holds a NUL"
        if not self.pattern.match(value):
            return "does not match %s" % self.pattern.pattern
        if self.path and ".." in value.split("/"):
            return "holds a `..` segment"
        if not self.file and value.startswith("-") and not self.empty_ok:
            return "starts with `-`"
        return None


def _ph(key, arg, pattern, **kw):
    return key, Placeholder(key, arg, pattern, **kw)


#: ``<name>`` placeholders, by the literal text between the angle brackets (ADR-3). Closed:
#: a name not listed here makes its fence unroutable.
PLACEHOLDERS = dict([
    _ph("worktree", "worktree", _PATH, path=True, scope="cwd"),
    _ph("primary worktree", "root", _PATH, path=True, scope="cwd"),
    _ph("spec", "spec", _PATH, path=True, scope="spec"),
    _ph("state", "state", _PATH, path=True, scope="state"),
    _ph("tasks", "tasks", _PATH, path=True, scope="tasks"),
    _ph("pipeline-state.json", "state", _REL_OR_ABS, path=True, scope="state"),
    _ph("requirement.md", "spec", _REL_OR_ABS, path=True, scope="spec"),
    _ph("integrationBranch", "integrationBranch", _BRANCH, path=True),
    _ph("integration-branch", "integrationBranch", _BRANCH, path=True),
    _ph("branch-name", "branch", r"(?:feat|fix|chore)/[A-Za-z0-9_.-]{1,200}", path=True),
    _ph("branch", "branch", r"(?:feat|fix|chore)/[A-Za-z0-9_.-]{1,200}", path=True),
    _ph("component", "component", _COMPONENT, multi=True, path=True),
    _ph("TASK-xxx", "task", r"TASK-[0-9]{3,6}"),
    _ph("mode", "mode", r"(?:--fresh|--reuse)?"),
    _ph("1|3", "phase", r"[13]"),
    _ph("n", "attempt", r"[1-9][0-9]{0,2}"),
    _ph("0|1", "loops", r"[01]"),
    _ph("blocked|failed", "terminal", r"blocked|failed"),
    _ph("token, or empty", "reason", r"[a-z-]{0,40}"),
    _ph("owner/repo", "repo", r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}"),
    _ph("short title", "title", _LINE),
    _ph("prNumber", "pr", r"[0-9]{1,9}"),
    _ph("id", "id", r"(?:(?:REQ|BUG|TASK|LESSON|ASSUME)-)?[0-9]{3,6}"),
    _ph("slug", "slug", r"[a-z0-9]+(?:-[a-z0-9]+){0,12}"),
    _ph("mark", "mark", r"adlc-transcript-mark-[0-9a-f]{16}"),
    _ph("LESSON-a,LESSON-b", "ids", r"NO_ENTRY|LESSON-[0-9]{3,6}(?:,LESSON-[0-9]{3,6})*"),
    _ph("the lane_escalated value, verbatim", "lane_escalated", r"[^\x00\n]{1,4000}", file=True),
    _ph("req-ids", "req_ids", r"(?:REQ-[0-9]{3,6}(?: REQ-[0-9]{3,6}){0,30})?"),
])
#: Literal tokens the text tells the model to replace, treated as placeholders.
LITERAL_PLACEHOLDERS = dict([
    _ph("REQ-xxx", "req", r"REQ-[0-9]{3,6}"),
])
#: Free shell variables the prose tells the model to set before the fence (ADR-3): each is
#: bound as ``ADLC_ARG_<name>`` like a placeholder. Closed, like PLACEHOLDERS.
VAR_PLACEHOLDERS = dict([
    _ph("prNumber", "prNumber", r"[0-9]{1,9}"),
    _ph("NEW_BODY", "NEW_BODY", r"[^\x00]{1,1048576}", file=True),
    _ph("FINAL_TITLE", "FINAL_TITLE", _LINE),
    # The path `skill-flag.sh create` prints, and nothing else: `mark` appends to <flag>.state
    # and `clear` removes <flag>, so a free path would be a write or a delete anywhere.
    _ph("flag", "flag", r"/[A-Za-z0-9_./-]{0,400}/adlc-skill-flag\.[A-Za-z0-9]{6,32}", path=True),
    _ph("REQ", "REQ", r"(?:REQ-[0-9]{3,6})?"),
    _ph("LESSON_NUM", "LESSON_NUM", r"[0-9]{1,6}"),
    _ph("MAPPER_PATHS", "MAPPER_PATHS", r"(?:[A-Za-z0-9_][A-Za-z0-9_./-]{0,300}\n?){0,500}",
        file=True),
])
#: Variables a fence reads that the run provides: the environment, the shell, or a partial
#: the fence sources. Never a placeholder.
RUNTIME_VARS = frozenset((
    "HOME", "TMPDIR", "PATH", "PWD", "IFS", "ADLC_TOOLKIT_ROOT", "CLAUDE_PLUGIN_ROOT",
    "DELEGATE_TOOLS", "ADLC_READ_BIN", "ADLC_DELEGATE_GATE_REASON", "ADLC_FORGE_PROVIDER",
    "ADLC_EXEC_RUN", "ADLC_HOME", "ZSH_VERSION", "BASH_VERSION",
    # /manifest's optional hand-off variables: read from the environment, absent under exec.
    "MANIFEST_SKIP_FETCH", "MANIFEST_SELF"))
_SPECIAL_VARS = frozenset("?$!#@*-0123456789")

#: Statement commands whose arguments are code: a value spliced into them would run.
INTERPRETERS = frozenset((
    "sh", "bash", "zsh", "dash", "ksh", "eval", "exec", "awk", "gawk", "sed", "perl", "ruby",
    "node", "python", "python3", "xargs", "env", "find", "trap", "source", ".", "jq"))

#: The canonical root line and source line (REQ-669, REQ-610): rewritten, never run as-is.
ROOT_LINE = """\
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
""".strip()
_SOURCE_RE = re.compile(
    r'^(\s*)if \[ -f \.adlc/partials/([A-Za-z0-9_-]+)\.sh \]; then \. \.adlc/partials/\2\.sh; '
    r'else \. "\$ADLC_TOOLKIT_ROOT/partials/\2\.sh"; fi\s*$')
_DOT_RE = re.compile(r"(?:^|[;&|({]|\bthen\b|\belse\b|\bdo\b)\s*(?:\.|source)\s")
_PH_RE = re.compile(r"<([A-Za-z][^<>\n]*?|[0-9]+(?:\|[0-9]+)+)>")
_VAR_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|([A-Za-z_][A-Za-z0-9_]*))")
_ASSIGN_RE = re.compile(r"(?:^|[\s;&|(`]|\$\()([A-Za-z_][A-Za-z0-9_]*)=")
_FOR_READ_RE = re.compile(r"\b(?:for|read(?:\s+-[a-z]+)*)((?:\s+[A-Za-z_][A-Za-z0-9_]*)+)")

#: The sample values a ``direct`` check puts in a placeholder, and the branch its policy is
#: rendered for: the same at the prompt build and in ``fence-run``.
SAMPLE_BRANCH = "feat/REQ-901-sample"
SAMPLE_VALUES = {"branch": SAMPLE_BRANCH, "worktree": "/abs/wc", "repo-path": "/abs/repo"}


#: The shape of a fence id (ADR-2).
_ID_OK = re.compile(r"^[A-Za-z0-9_./-]+#[0-9]+:[0-9a-f]{8}$")


class CensusError(ValueError):
    """The census cannot be built: a file of the exec set is missing or will not cut."""


class Fence(object):
    """One shell fence of a view."""
    __slots__ = ("rel", "ordinal", "info", "body", "indent", "start", "end")

    def __init__(self, rel, ordinal, info, body, indent, start, end):
        self.rel = rel
        self.ordinal = ordinal
        self.info = info
        self.body = body
        self.indent = indent
        self.start = start
        self.end = end

    @property
    def key(self):
        return "%s#%d" % (self.rel, self.ordinal)

    @property
    def sha8(self):
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()[:8]

    @property
    def id(self):
        return "%s:%s" % (self.key, self.sha8)

    @property
    def code(self):
        """The body with the fence's own indentation removed."""
        out = []
        for line in self.body.split("\n"):
            out.append(line[len(self.indent):] if line.startswith(self.indent) else line.lstrip())
        return "\n".join(out)


def fences(text, rel=""):
    """Every shell fence of ``text``, in order, as :class:`Fence`."""
    out = []
    lines = text.split("\n")
    i = 0
    n = 0
    while i < len(lines):
        match = _OPEN_RE.match(lines[i])
        if not match:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not _CLOSE_RE.match(lines[j]):
            j += 1
        if match.group(2) in SHELL_INFOS:
            n += 1
            out.append(Fence(rel, n, match.group(2), "\n".join(lines[i + 1:j]), match.group(1),
                             i, j))
        i = j + 1
    return out


def view(root, rel):
    """The bytes of ``rel`` the model is given under ``--exec`` (ADR-5)."""
    if rel not in EXEC_FILES:
        raise CensusError("%s is not in the exec file set" % rel)
    try:
        if rel == "proceed/SKILL.md":
            return ep.proceed_view(root)
        if rel in ep.PIPELINE_SOURCES:
            return ep.companion_view(root, rel)
        if rel == CLOSEOUT_FILE:
            return ep.closeout_view(root)
    except ep.PromptBuildError as exc:
        raise CensusError(str(exc))
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise CensusError("cannot read %s: %s" % (rel, exc))
    cut = SECTION_VIEWS.get(rel)
    if cut is None:
        return text
    start, end = cut
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln == start]
    stops = [i for i, ln in enumerate(lines) if ln == end]
    if len(hits) != 1 or len(stops) != 1 or stops[0] < hits[0]:
        raise CensusError("%s: the section %r to %r moved" % (rel, start, end))
    return "\n".join(lines[hits[0]:stops[0]]).rstrip() + "\n"


# --------------------------------------------------------------------------- invoked files
_INVOKE_RE = re.compile(r"\b(?:[Ii]nvoke|[Rr]e-invoke|[Rr]un|[Rr]e-run)\s+(?:the\s+)?"
                        r"`/([a-z][a-z-]*)(?=[`\s])")
_AGENT_PATH_RE = re.compile(r"\bagents/([a-z][a-z-]*)\.md")
_REFERENCE_RE = re.compile(r"\b([a-z][a-z-]*/references/[a-z0-9-]+\.md)")


def agent_names(root):
    try:
        return sorted(n[:-3] for n in os.listdir(os.path.join(root, "agents")) if n.endswith(".md"))
    except OSError:
        return []


def invoked_files(text, agents=()):
    """The skill, reference and agent files ``text`` tells the model to invoke or follow."""
    out = set()
    for match in _INVOKE_RE.finditer(text):
        if match.group(1) not in USER_ONLY:
            out.add("%s/SKILL.md" % match.group(1))
    for match in _AGENT_PATH_RE.finditer(text):
        if match.group(1) in agents:
            out.add("agents/%s.md" % match.group(1))
    for match in _REFERENCE_RE.finditer(text):
        out.add(match.group(1))
    for name in agents:
        if re.search(r"(?:`|\*\*)%s(?:`|\*\*)" % re.escape(name), text):
            out.add("agents/%s.md" % name)
    return out


def named_closure(root, texts):
    """Every file the delivered ``texts`` name, and every file those files name, in turn."""
    agents = agent_names(root)
    seen = set()
    frontier = set()
    for text in texts:
        frontier |= invoked_files(text, agents)
    while frontier:
        seen |= frontier
        nxt = set()
        for rel in frontier:
            path = os.path.join(root, rel)
            if rel in EXEC_FILES:
                # What the model is shown of it, not the whole file (SECTION_VIEWS).
                try:
                    nxt |= invoked_files(view(root, rel), agents)
                except CensusError:
                    pass
            elif os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    nxt |= invoked_files(fh.read(), agents)
        frontier = nxt - seen
    return seen


def coverage_problems(root, texts):
    """Names the delivered text reaches that the exec set lacks, and members it no longer
    names (both directions, LESSON-712). Empty when the set is exact."""
    named = named_closure(root, texts) | set(PIPELINE_FILES) | {CLOSEOUT_FILE}
    problems = ["%s is named by the delivered text but is not in EXEC_FILES" % rel
                for rel in sorted(named - set(EXEC_FILES))]
    problems += ["%s is in EXEC_FILES but no delivered text names it" % rel
                 for rel in sorted(set(EXEC_FILES) - named)]
    return problems


# --------------------------------------------------------------------------- the policy
def exec_policy(root, adapter=None):
    """The ExecPolicy the census judges ``direct`` against: the adapter's tiers for
    :data:`SAMPLE_BRANCH`, with no project extras. The same at build time and in fence-run."""
    import exec_adapter as ea
    adapter = adapter or ea.load("claude", root)
    allow, deny = adapter.tiers(SAMPLE_BRANCH)
    return {"allow": allow, "deny": deny}


# --------------------------------------------------------------------------- transform
class Unroutable(ValueError):
    """The body cannot be run by the runner; the message says why."""


def _statement_command(code, pos):
    """The command word of the statement ``pos`` sits in (quotes stripped), or ''."""
    start = 0
    quote = None
    i = 0
    while i < pos:
        c = code[i]
        if quote:
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c in ";\n|&(" or code.startswith("$(", i):
            start = i + 1
        i += 1
    words = em.words(code[start:pos])
    for word in words:
        bare = word.strip("'\"")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", bare):
            continue
        if bare in ("if", "then", "else", "elif", "do", "while", "until", "!", "{", "command",
                    "time"):
            continue
        return bare
    return ""


def placeholders_of(code):
    """The placeholder keys in ``code`` outside comments, in order, without duplicates."""
    keys = []
    for line in code.split("\n"):
        if line.lstrip().startswith("#"):
            continue
        for match in _PH_RE.finditer(line):
            keys.append(match.group(1))
        for lit in LITERAL_PLACEHOLDERS:
            if lit in line:
                keys.append(lit)
    return list(dict.fromkeys(keys))


def free_vars(code):
    """Variables ``code`` reads that it never assigns and the run does not provide."""
    assigned = set()
    used = []
    for line in code.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        assigned |= {m.group(1) for m in _ASSIGN_RE.finditer(line)}
        for m in _FOR_READ_RE.finditer(line):
            assigned |= set(m.group(1).split()) - {"in", "do"}
        for match in _VAR_RE.finditer(line):
            used.append(match.group(1) or match.group(2))
    return [v for v in dict.fromkeys(used) if v not in assigned and v not in RUNTIME_VARS]


def _lookup(key):
    return PLACEHOLDERS.get(key) or LITERAL_PLACEHOLDERS.get(key)


def plan(code):
    """``(placeholders, sources)`` of a body the runner can run, or :class:`Unroutable`.

    ``placeholders`` is a list of :class:`Placeholder` (``<name>`` ones, literal ones and
    free variables) and ``sources`` the partials the body sources, in order.
    """
    sources = []
    found = []
    for line in code.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == ROOT_LINE:
            continue
        match = _SOURCE_RE.match(line)
        if match:
            sources.append(match.group(2))
            continue
        if _DOT_RE.search(line) or re.match(r"^\s*(?:\.|source)\s", line):
            raise Unroutable("sources a file outside the canonical spelling: %s" % stripped[:120])
        if "ADLC_TOOLKIT_ROOT=" in line:
            raise Unroutable("assigns ADLC_TOOLKIT_ROOT outside the canonical root line")
    for key in placeholders_of(code):
        ph = _lookup(key)
        if ph is None:
            raise Unroutable("placeholder <%s> is not in the closed table" % key)
        found.append(ph)
    for name in free_vars(code):
        ph = VAR_PLACEHOLDERS.get(name)
        if ph is None:
            raise Unroutable("reads $%s, which it never sets and no table names" % name)
        found.append(ph)
    # Dry-run the rewrite with every value bound once, so a placeholder in a position the
    # runner will not rewrite is found now, not at run time.
    transform(code, {ph.arg: ["x"] for ph in found}, root="/abs/tk")
    return found, sources


def _env_name(arg, index=None):
    base = "ADLC_ARG_" + re.sub(r"[^A-Za-z0-9_]", "_", arg)
    return base if index is None else "%s_%d" % (base, index)


def transform(code, values, root):
    """The body as the runner runs it: the root line literal, each canonical source the
    ToolkitRoot arm, and every placeholder and free variable a quoted ``ADLC_ARG_*`` expansion.

    ``values`` maps an argument name to its list of values; a ``multi`` placeholder in a
    ``--flag "<x>"`` pair is expanded once per value. Raises :class:`Unroutable`.
    """
    out_lines = []
    heredoc = None
    lines = code.split("\n")
    # Only a variable the fence never assigns is a value to bind: a `$flag` the fence set
    # itself two lines up is its own, and stays as written.
    free = set(free_vars(code))
    for k, line in enumerate(lines):
        if heredoc is not None:
            if line.strip() == heredoc:
                heredoc = None
                out_lines.append(line)
                continue
            single = _PH_RE.fullmatch(line.strip())
            if single and _lookup(single.group(1)) and out_lines and \
                    k + 1 < len(lines) and lines[k + 1].strip() == heredoc:
                # A quoted here-document whose whole body is one placeholder: unquote its
                # delimiter and expand the value once. An expansion's result is never
                # re-read, so the value stays data.
                out_lines[-1] = re.sub(r"<<-?\s*'([A-Za-z_][A-Za-z0-9_]*)'", r"<<\1",
                                       out_lines[-1])
                out_lines.append("${%s}" % _env_name(_lookup(single.group(1)).arg))
                continue
            if _PH_RE.search(line) or any(lit in line for lit in LITERAL_PLACEHOLDERS):
                raise Unroutable("a placeholder in a here-document body is never rewritten")
            out_lines.append(line)
            continue
        stripped = line.strip()
        if stripped == ROOT_LINE:
            out_lines.append('ADLC_TOOLKIT_ROOT="%s"; export ADLC_TOOLKIT_ROOT' % root)
            continue
        match = _SOURCE_RE.match(line)
        if match:
            out_lines.append('%s. "%s/partials/%s.sh"' % (match.group(1), root, match.group(2)))
            continue
        if stripped.startswith("#"):
            out_lines.append(line)
            continue
        out_lines.append(_rewrite_line(line, values, free))
        doc = re.search(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?", line)
        if doc and not re.search(r"<<<", line):
            heredoc = doc.group(1)
    return "\n".join(out_lines)


def _multi_pair(line, start, end):
    """``(flag_start, flag)`` when ``"<x>"`` at [start, end) is the value of a ``--flag``."""
    before = line[:start]
    match = re.search(r"(--[A-Za-z][A-Za-z0-9-]*)\s+$", before)
    if match:
        return match.start(1), match.group(1)
    return None


def _rewrite_line(line, values, free=None):
    out = []
    i = 0
    quote = None
    n = len(line)
    while i < n:
        c = line[i]
        if quote is None and c == "#" and (i == 0 or line[i - 1] in " \t"):
            out.append(line[i:])
            break
        match = _PH_RE.match(line, i) if c == "<" else None
        lit = None
        if match is None:
            for key in LITERAL_PLACEHOLDERS:
                if line.startswith(key, i):
                    lit = key
                    break
        if match is not None or lit is not None:
            key = match.group(1) if match is not None else lit
            end = match.end() if match is not None else i + len(lit)
            ph = _lookup(key)
            if ph is None:
                raise Unroutable("placeholder <%s> is not in the closed table" % key)
            out_text, consumed = _replace(line, i, end, quote, ph, values, out)
            if out_text is None:
                raise Unroutable("placeholder <%s> sits where its value could become code: %s"
                                 % (key, line.strip()[:120]))
            out.append(out_text)
            if consumed:
                quote = None
            i = end + consumed
            continue
        var = _VAR_RE.match(line, i) if c == "$" and quote != "'" else None
        if var is not None:
            name = var.group(1) or var.group(2)
            ph = VAR_PLACEHOLDERS.get(name)
            if ph is not None and (free is None or name in free) and \
                    name not in _assigned_in(line):
                if quote == '"':
                    out.append("${%s}" % _env_name(ph.arg))
                else:
                    out.append('"${%s}"' % _env_name(ph.arg))
                i = var.end()
                continue
        if c == "\\" and quote != "'":
            out.append(line[i:i + 2])
            i += 2
            continue
        if quote is None and c in ("'", '"'):
            quote = c
        elif quote == c:
            quote = None
        out.append(c)
        i += 1
    return "".join(out)


def _assigned_in(line):
    return {m.group(1) for m in _ASSIGN_RE.finditer(line)}


def _replace(line, start, end, quote, ph, values, out):
    """The text that replaces a placeholder at [start, end), and how many trailing
    characters it also consumed (a closing quote), or ``(None, 0)`` when it may not be."""
    vals = values.get(ph.arg, [])
    before = line[start - 1] if start > 0 else " "
    after = line[end] if end < len(line) else " "
    whole_dq = quote == '"' and before == '"' and after == '"'
    whole_sq = quote == "'" and before == "'" and after == "'"
    command = _statement_command(line, start)
    if whole_dq or whole_sq:
        pair = _multi_pair(line, start - 1, end + 1) if ph.multi else None
        if pair is not None:
            flag_start, flag = pair
            # Drop the flag and the opening quote already emitted, and emit one pair per value.
            emitted = "".join(out)
            cut = len(emitted) - (start - 1 - flag_start) - 1
            del out[:]
            out.append(emitted[:cut])
            parts = ['%s "${%s}"' % (flag, _env_name(ph.arg, k)) for k in range(len(vals))]
            return " ".join(parts), 1
        if whole_sq:
            # '<x>' becomes "${ADLC_ARG_x}": drop the emitted opening quote.
            emitted = "".join(out)
            del out[:]
            out.append(emitted[:-1])
            return '"${%s}"' % _env_name(ph.arg), 1
        return "${%s}" % _env_name(ph.arg), 0
    if command in INTERPRETERS:
        return None, 0
    if quote == "'":
        return None, 0
    if quote == '"':
        return "${%s}" % _env_name(ph.arg), 0
    if before in " \t" and after in " \t;":
        if ph.empty_ok:
            return '${%s:+"${%s}"}' % (_env_name(ph.arg), _env_name(ph.arg)), 0
        return '"${%s}"' % _env_name(ph.arg), 0
    return '"${%s}"' % _env_name(ph.arg), 0


# --------------------------------------------------------------------------- reach (ADR-7)
_FUNC_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\) \{\s*(?:#.*)?$")
#: Commands a runner fence, or a function it reaches, may call. Closed: a word that is neither
#: here nor a function in partials/*.sh fails the audit, so a new verb starts refused (BR-4).
EXTERNAL = frozenset((
    # shell built-ins and keywords at command position
    ":", "[", "test", "true", "false", "echo", "printf", "read", "set", "unset", "export",
    "return", "exit", "shift", "cd", "pwd", "trap", "wait", "case", "esac", "for", "in", "do",
    "done", "while", "until", "if", "then", "else", "elif", "fi", "break", "continue", "local",
    "command", "type", "umask", "getopts", "hash", "kill", "sleep",
    # POSIX utilities
    "cat", "grep", "sed", "awk", "tr", "cut", "head", "tail", "sort", "uniq", "wc", "find",
    "basename", "dirname", "mktemp", "mkdir", "rm", "rmdir", "cp", "mv", "ln", "ls", "chmod",
    "date", "od", "env", "uname", "id", "stat", "touch", "readlink", "realpath", "tee", "xargs",
    "comm", "diff", "cmp", "fold", "paste", "expr", "seq", "base64", "shasum", "sha256sum",
    "md5", "md5sum", "iconv", "file", "dd", "timeout", "gtimeout", "nohup", "jq", "python3",
    # the forges and git
    "git", "gh", "az", "curl",
    # toolkit executables, reached through a variable the partials resolve
    "$DELEGATE_TOOLS/skill-flag.sh", "$DELEGATE_TOOLS/emit-telemetry.sh",
    "$DELEGATE_TOOLS/emit-run-outcome.sh", "$DELEGATE_TOOLS/check-delegation.sh",
    "$ADLC_READ_BIN", "$adlc_fp_py", "$adlc_ls_py", "$adlc_lc_py", "$adlc_rgc_py",
    "$adlc_dg_bin", "$_adlc_bin", "$_t", "$_timeout", "$adlc_fpy_exe", "$adlc_mkp_py",
    "which", "setopt", "unsetopt", "emulate",
))
#: The toolkit executables a fence or a partial runs through a variable, with every file each
#: one runs: their own reach is read too (BR-4), a shell script command by command, a Python
#: one by the commands its string literals can spell.
TOOLKIT_EXECUTABLES = {
    "$DELEGATE_TOOLS/skill-flag.sh": ("tools/delegate/skill-flag.sh",),
    "$DELEGATE_TOOLS/emit-telemetry.sh": ("tools/delegate/emit-telemetry.sh",),
    "$DELEGATE_TOOLS/emit-run-outcome.sh": ("tools/delegate/emit-run-outcome.sh",
                                            "tools/delegate/run_outcome.py"),
    "$DELEGATE_TOOLS/check-delegation.sh": ("tools/delegate/check-delegation.sh",),
    "$ADLC_READ_BIN": ("tools/delegate/adlc-read", "tools/delegate/_common.py",
                       "tools/delegate/_machine_config.py"),
    "$adlc_fp_py": ("tools/adlc/forge_config.py",),
    "$adlc_mkp_py": ("tools/adlc/forge_mock.py", "tools/adlc/forge_protection.py"),
    "$adlc_ls_py": ("tools/adlc/lessons.py",),
    "$adlc_lc_py": ("tools/adlc/lane_check.py",),
    "$adlc_rgc_py": ("tools/adlc/regression_check.py",),
}
#: A deny-tier spelling in a toolkit executable that is reach, with why: the exact command,
#: so an edit to it is a finding again.
DECLARED_REACH = {
    ("tools/delegate/skill-flag.sh", 'rm -f "$2" "$2.state"'): (
        "`skill-flag.sh clear` removes the flag file it created and its sidecar; the runner "
        "binds `flag` only to an adlc-skill-flag.* path"),
}
_PY_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'')
_SH_FUNC = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)", re.M)


def script_reach(root, rel, deny_texts):
    """``(externals, problems)`` of one toolkit executable. A shell script is read command by
    command like a partial; a Python file by its string literals: an external it can name is
    reach, and a deny-tier spelling whose every token it holds is a problem (conservative)."""
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return [], ["%s: unreadable: %s" % (rel, exc)]
    externals = set()
    problems = []
    if rel.endswith(".sh"):
        local = set(_SH_FUNC.findall(text))
        for words in simple_commands(text):
            words = _unwrap(words)
            if not words:
                continue
            cmd = _bare(words[0])
            for hit in _deny_hits_in(words, set(), deny_texts):
                if (rel, " ".join(words)) in DECLARED_REACH:
                    continue
                problems.append("%s: deny-tier `%s` runs: %s" % (rel, hit, _command_text(words)))
            if cmd in local or cmd.startswith("$") or cmd in _NOISE:
                continue
            if cmd in EXTERNAL:
                externals.add(_external_shape(words))
            else:
                problems.append("%s: runs `%s`, which EXTERNAL does not name" % (rel, cmd))
        return sorted(externals), problems
    literals = set()
    for match in _PY_LITERAL.finditer(text):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        literals.add(value)
        literals.update(value.split())
    externals = {c for c in ("git", "gh", "az", "curl") if c in literals}
    for deny in deny_texts:
        if all(tok in literals for tok in deny.split()):
            problems.append("%s: holds every token of deny-tier `%s`" % (rel, deny))
    return sorted(externals), problems


#: Every toolkit file fence-run reads besides the exec set: the orchestrator's install
#: manifest covers them (``exec_safety.install_files``), so a change mid-run is caught.
RUNNER_READS = ("harness/claude.yml", "templates/permissions.yml", "tools/adlc/fence-run") + \
    tuple(sorted(set(rel for rels in TOOLKIT_EXECUTABLES.values() for rel in rels)))


#: The one function whose push is reach, not a deny (amended BR-2): the id-reservation push,
#: a non-force push of a new ref under refs/adlc/ids/ that moves no branch (ADR-7).
PUSH_REACH = {"adlc_reserve_id": "git push origin <oid>:refs/adlc/ids/<kind>/<n>"}
#: A function that runs the argv its caller spells: the audit reads the caller's line instead.
DISPATCHERS = {"_adlc_forge_run": "runs the argv its caller spells after `--`"}
#: Spellings that refuse under ADLC_FENCE_TOOLKIT_ONLY=1, with the guard text that refuses
#: them: the audit holds the guard present, and exempts the call shape (BR-5).
GUARDED = {
    "_adlc_forge_run -- az": ("_adlc_forge_run",
                              'opaque_entry_refused: forge: the Azure DevOps backend'),
}
#: Constructs that run data as code (ADR-7).
#: A partial sourcing a sibling partial from ToolkitRoot: the operand the partials' guarded
#: lines spell, or the directory of the partial being sourced (REQ-669 ADR-2). Under fence-run
#: both name ToolkitRoot's partials/, which is not data the model controls.
#: The partials' default-expansion operand (REQ-669 ADR-2), taken from the root line's last arm
#: so the toolkit's home literal is spelled once in this module.
_PARTIAL_OPERAND = ROOT_LINE.rsplit("=", 1)[1].rstrip('"') + "/partials/"
_TOOLKIT_SOURCE_RE = re.compile(r'^(?:%s|"\$_ADLC_[A-Z]+_DIR/)[a-z0-9-]+\.sh"$'
                                % re.escape(_PARTIAL_OPERAND))
_TEMP_ASSIGN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=\$\(mktemp\b")


def function_index(root):
    """``name -> (file, line, body lines)`` for every function in ``partials/*.sh``.

    A function is ``name() {`` at column 0 up to the next ``}`` at column 0: the style every
    partial uses. A ``name()`` written any other way fails loudly (TASK-247)."""
    index = {}
    pdir = os.path.join(root, "partials")
    for name in sorted(os.listdir(pdir)):
        if not name.endswith(".sh"):
            continue
        rel = "partials/" + name
        with open(os.path.join(pdir, name), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        i = 0
        in_sq = False
        while i < len(lines):
            line = lines[i]
            # A multi-line single-quoted string (session-record.sh's Python program) is
            # data: skip to the line that closes it.
            if in_sq:
                in_sq = "'" not in line
                i += 1
                continue
            if _opens_single_quote(line):
                in_sq = True
                i += 1
                continue
            doc = re.search(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?\s*$", line)
            if doc and not line.lstrip().startswith("#"):
                # A here-document's body is data (a Python program, a template), never a
                # definition: skip to its delimiter.
                end = next((k for k in range(i + 1, len(lines))
                            if lines[k].strip() == doc.group(1)), len(lines))
                i = end + 1
                continue
            match = _FUNC_RE.match(line)
            if match is None:
                if re.match(r"^\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\)", line) and \
                        not line.lstrip().startswith("#"):
                    raise CensusError("%s:%d defines a function in a form the index does not "
                                      "read: %s" % (rel, i + 1, line.strip()[:80]))
                i += 1
                continue
            j = i + 1
            while j < len(lines) and lines[j] != "}":
                j += 1
            index[match.group(1)] = (rel, i + 1, lines[i + 1:j])
            i = j + 1
    return index


def _opens_single_quote(line):
    """Whether ``line`` leaves a single-quoted string open at its end."""
    if line.lstrip().startswith("#"):
        return False
    quote = None
    for c in line:
        if quote:
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c == "#":
            break
    return quote == "'"


def _skip_quoted(text, i):
    """Index just past the string that opens at ``text[i]`` (a ``'`` or a ``"``)."""
    quote = text[i]
    j = i + 1
    while j < len(text):
        c = text[j]
        if quote == '"' and c == "\\":
            j += 2
            continue
        if c == quote:
            return j + 1
        if quote == '"' and text.startswith("$(", j):
            j = _skip_paren(text, j + 1)
            continue
        j += 1
    return len(text)


def _skip_paren(text, i):
    """Index just past the ``)`` matching the ``(`` at ``text[i]``."""
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c in ("'", '"'):
            j = _skip_quoted(text, j)
            continue
        if c == "\\":
            j += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(text)


def _skip_brace(text, i):
    """Index just past the ``}`` matching the ``{`` at ``text[i]``."""
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c in ("'", '"'):
            j = _skip_quoted(text, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(text)


_OPS = (";;", "&&", "||", ";", "|", "&", "(", ")", "\n")


def _substs_in(text):
    """The command substitutions inside an arithmetic expansion's text."""
    out = []
    k = 0
    while k < len(text):
        if text.startswith("$(", k) and not text.startswith("$((", k):
            end = _skip_paren(text, k + 1)
            out.append(text[k + 2:end - 1])
            k = end
            continue
        k += 1
    return out
_WORD_END = " \t\n;&|()"


def shell_tokens(text):
    """``("word", raw)``, ``("op", op)`` and ``("subst", inner)`` tokens of shell ``text``.

    Quotes, ``${…}`` and ``$(…)`` stay inside their word, and each command substitution's
    inner text is also yielded, to be read as commands in turn. Comments and here-document
    bodies are dropped. A reading for the reach audit, not a shell: it is conservative where
    it is unsure, because an unknown word fails the audit rather than passing it."""
    out = []
    docs = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(("op", "\n"))
            i += 1
            for delim in docs:
                while i < n:
                    end = text.find("\n", i)
                    end = n if end == -1 else end
                    line = text[i:end]
                    i = end + 1
                    if line.strip() == delim:
                        break
            docs = []
            continue
        if c in " \t":
            i += 1
            continue
        if text.startswith("\\\n", i):
            i += 2
            continue
        if c == "#":
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        op = next((o for o in _OPS if text.startswith(o, i)), None)
        if op == "&" and text.startswith("&>", i):
            op = None         # `&>file` is a redirection, not a background `&`
        if op:
            out.append(("op", op))
            i += len(op)
            continue
        if text.startswith("<<", i) and not text.startswith("<<<", i):
            k = i + 2 + (1 if text.startswith("<<-", i) else 0)
            while k < n and text[k] in " \t":
                k += 1
            m = k
            while m < n and text[m] not in _WORD_END:
                m += 1
            delim = text[k:m].strip("'\"")
            if delim:
                docs.append(delim)
            out.append(("word", "<<"))
            i = m
            continue
        j = i
        while j < n and (text[j] not in _WORD_END or
                         (text[j] == "&" and j > i and text[j - 1] in "<>") or
                         (text[j] == "&" and j == i and text.startswith("&>", j))):
            ch = text[j]
            if ch in ("'", '"'):
                start = j
                j = _skip_quoted(text, j)
                if ch == '"':
                    k = start + 1
                    while k < j:
                        if text.startswith("$(", k):
                            end = _skip_paren(text, k + 1)
                            out.append(("subst", text[k + 2:end - 1]))
                            k = end
                            continue
                        k += 1
                continue
            if ch == "\\":
                j += 2
                continue
            if text.startswith("$((", j):
                end = _skip_paren(text, j + 1)
                out += [("subst", s) for s in _substs_in(text[j + 3:end - 2])]
                j = end
                continue
            if text.startswith("$(", j):
                end = _skip_paren(text, j + 1)
                out.append(("subst", text[j + 2:end - 1]))
                j = end
                continue
            if text.startswith("${", j):
                j = _skip_brace(text, j + 1)
                continue
            if ch == "`":
                end = text.find("`", j + 1)
                end = n if end == -1 else end + 1
                out.append(("subst", text[j + 1:end - 1]))
                j = end
                continue
            j += 1
        out.append(("word", text[i:j]))
        i = j
    return out


_SKIP_WORDS = frozenset(("if", "then", "else", "elif", "fi", "do", "done", "while", "until",
                         "!", "{", "}"))
_REDIRECT_WORD = re.compile(r"^[0-9]*(?:>>?|<|&>|>&)(.*)$")


def simple_commands(text):
    """The word list of every simple command in shell ``text``, substitutions included, with
    keywords, assignments and redirections removed from the front: ``words[0]`` is what runs."""
    cmds = []
    cur = []
    state = "cmd"
    case_depth = 0
    for kind, val in shell_tokens(text):
        if kind == "subst":
            cmds += simple_commands(val)
            continue
        if kind == "op":
            if cur:
                cmds.append(cur)
                cur = []
            if state == "pattern" and val == ")":
                state = "cmd"
            elif val == ";;" and case_depth:
                state = "pattern"
            continue
        if state == "for":
            if val == "do":
                state = "cmd"
            continue
        if state == "case-word":
            if val == "in":
                state = "pattern"
            continue
        if state == "pattern":
            if val == "esac":
                case_depth -= 1
                state = "cmd"
            continue
        if not cur:
            if val == "esac" and case_depth:
                case_depth -= 1
                continue
            if val in _SKIP_WORDS:
                continue
            if val == "case":
                case_depth += 1
                state = "case-word"
                continue
            if val == "for":
                state = "for"
                continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", val):
                continue
            red = _REDIRECT_WORD.match(val)
            if red:
                if not red.group(1):
                    cur = ["\x00redirect-target"]
                continue
        elif cur == ["\x00redirect-target"]:
            cur = []
            continue
        cur.append(val)
    if cur:
        cmds.append(cur)
    return [c for c in cmds if c and c != ["\x00redirect-target"]]


def _bare(word):
    """A word with its quotes dropped, and ``"$X"/y`` spelled ``$X/y``."""
    word = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_@]*)\}', r"$\1", word)
    return word.replace('"', "").replace("'", "")


def _external_shape(words):
    """``git fetch``, ``gh pr create``, ``az repos pr``: an external command and its verbs."""
    ws = [_bare(w) for w in words]
    head = ws[0]
    if head == "git":
        rest = ws[1:]
        while rest and rest[0] in ("-C", "-c"):
            rest = rest[2:]
        return "git " + rest[0] if rest and not rest[0].startswith(("$", "-")) else "git"
    if head in ("gh", "az"):
        verbs = []
        for w in ws[1:]:
            if w.startswith(("-", "$")) or len(verbs) == (2 if head == "gh" else 3):
                break
            verbs.append(w)
        return " ".join([head] + verbs)
    return head


def _deny_texts(adapter, root):
    texts = []
    for spelling in em.deny_tier_spellings(adapter.adapter, root):
        text = " ".join(spelling)
        if text.startswith("adlc_forge_pr_merge"):
            text = "adlc_forge_pr_merge"
        texts.append(text)
    return list(dict.fromkeys(texts))


_NOISE = frozenset(("[", ":", "test", "true", "false", "echo", "printf", "read", "set",
                    "unset", "export", "return", "exit", "shift", "cd", "pwd", "trap", "break",
                    "continue", "local", "wait", "type", "hash", "umask", "getopts"))
#: Commands whose arguments hold a program (ADR-7's "constructs that run data as code"): the
#: audit reads that program text for deny-tier spellings.
PROGRAM_COMMANDS = frozenset(("awk", "gawk", "sed", "perl", "python3", "jq", "ruby", "node"))
#: Wrappers that run the command after them: the audit reads that command instead.
_WRAPPERS = ("command", "exec", "nohup", "time", "env", "timeout", "gtimeout", "xargs")


def _unwrap(words):
    """The words of the command a wrapper runs, or ``None`` for a query (``command -v``)."""
    ws = list(words)
    while ws:
        head = _bare(ws[0])
        if head == "command":
            if len(ws) > 1 and ws[1] in ("-v", "-V"):
                return None
            ws = ws[1:]
            if ws and ws[0] == "-p":
                ws = ws[1:]
        elif head in ("exec", "nohup", "time"):
            ws = ws[1:]
        elif head == "env":
            ws = ws[1:]
            while ws and (ws[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", ws[0])):
                ws = ws[1:]
        elif head in ("timeout", "gtimeout") or head.endswith("_timeout") or head == "$_t":
            ws = ws[2:] if len(ws) > 2 else []
        elif head == "xargs":
            ws = ws[1:]
            while ws and ws[0].startswith("-"):
                ws = ws[1:]
        else:
            break
    return ws or None


def _command_text(words):
    return " ".join(_bare(w) for w in words)


def _deny_hits_in(words, temp_vars, deny_texts):
    """The deny-tier spellings this one command is, judged on what runs (never on a message
    it prints), with ``git -C <path>`` and env prefixes seen through: ``rm`` of a file this
    body made with mktemp is not reach."""
    words = list(words)
    if len(words) > 2 and _bare(words[0]) == "git" and words[1] == "-C":
        words = [words[0]] + words[3:]
    text = _command_text(words)
    hits = []
    for deny in deny_texts:
        if text != deny and not text.startswith(deny + " "):
            continue
        if deny.startswith("rm ") and temp_vars:
            alt = "|".join(re.escape(v) for v in temp_vars)
            rx = re.compile(r'^"?\$\{?(?:%s)\}?(?:[./][^"\s]*)?"?$' % alt)
            operands = [w for w in words[1:] if not w.startswith("-")]
            if operands and all(rx.match(op) for op in operands):
                continue
        hits.append(deny)
    return hits


def reach(code, index, adapter, root):
    """The static reach of a runner body (ADR-7): ``(externals, problems, functions)``.

    ``externals`` is the sorted set of external command shapes the body and every function it
    reaches can run; ``problems`` names each deny-tier spelling, code-from-data construct or
    unknown command, with the function and ``file:line``; ``functions`` is the closure. The
    audit reads what runs, command by command, never the text a command prints. Recording
    stubs prove the paths a run takes; this proves the branches (TASK-247)."""
    deny_texts = _deny_texts(adapter, root)
    externals = set()
    problems = []
    seen = set()
    scripts = {}

    def judge(words, label, temps, func, calls, depth=0):
        words = _unwrap(words)
        if not words:
            return
        cmd = _bare(words[0])
        for hit in _deny_hits_in(words, temps, deny_texts):
            problems.append("%s: deny-tier `%s` runs: %s" % (label, hit,
                                                             _command_text(words)[:100]))
        if cmd in ("trap",) and len(words) > 1 and depth < 3:
            for inner in simple_commands(_bare(words[1])):
                judge(inner, label, temps, func, calls, depth + 1)
            return
        if cmd in ("sh", "bash", "zsh", "dash") and "-c" in words[1:3]:
            body = words[words.index("-c") + 1] if words.index("-c") + 1 < len(words) else ""
            if "$" in body.replace("\\$", ""):
                problems.append("%s: sh -c of a non-literal body: %s"
                                % (label, _command_text(words)[:100]))
            elif depth < 3:
                for inner in simple_commands(_bare(body)):
                    judge(inner, label, temps, func, calls, depth + 1)
            return
        if cmd == "eval":
            problems.append("%s: eval runs data as code: %s" % (label, _command_text(words)[:100]))
            return
        if cmd == "find" and depth < 3:
            # `find -exec`/`-execdir`/`-ok` runs a command of its own: judge it like any other.
            ws = list(words)
            for k, w in enumerate(ws):
                if _bare(w) in ("-exec", "-execdir", "-ok", "-okdir"):
                    inner = []
                    for v in ws[k + 1:]:
                        if _bare(v) in (";", "\\;", "+"):
                            break
                        inner.append(v)
                    if inner:
                        judge(inner, label, temps, func, calls, depth + 1)
        if cmd in PROGRAM_COMMANDS:
            # A program handed to an interpreter (awk's system(), sed's `e`, perl -e) is code
            # no command reading sees: a deny-tier spelling anywhere in it is a finding.
            text = _command_text(words)
            for deny in deny_texts:
                if re.search(r"(?:^|[^A-Za-z0-9_-])%s(?:$|[^A-Za-z0-9_-])" % re.escape(deny),
                             text):
                    problems.append("%s: deny-tier `%s` in the program %s runs: %s"
                                    % (label, deny, cmd, text[:100]))
        if cmd in (".", "source"):
            target = words[1] if len(words) > 1 else ""
            if _TOOLKIT_SOURCE_RE.match(target):
                return        # a partial sourcing a sibling from ToolkitRoot's partials/
            if "$" in target:
                problems.append("%s: . of a non-literal operand: %s"
                                % (label, _command_text(words)[:100]))
            return
        if cmd in index:
            calls.append(cmd)
            if cmd in DISPATCHERS and len(words) > 2 and words[1] == "--":
                inner = words[2:]
                shape = _external_shape(inner)
                guarded = any(_command_text([cmd, "--"] + inner[:1]) == g for g in GUARDED)
                if not guarded:
                    externals.add(shape)
                    for hit in _deny_hits_in(inner, temps, deny_texts):
                        problems.append("%s: deny-tier `%s` runs through %s: %s"
                                        % (label, hit, cmd, _command_text(inner)[:100]))
            return
        if cmd in ("$@", "$*") and func in DISPATCHERS:
            return
        if cmd in TOOLKIT_EXECUTABLES:
            externals.add(cmd)
            for rel in TOOLKIT_EXECUTABLES[cmd]:
                if rel not in scripts:
                    scripts[rel] = script_reach(root, rel, deny_texts)
                externals.update(scripts[rel][0])
                problems.extend(scripts[rel][1])
            return
        if cmd in EXTERNAL:
            shape = _external_shape(words)
            if shape == "git push" and func not in PUSH_REACH:
                problems.append("%s: pushes: a runner fence never pushes a branch (BR-2): %s"
                                % (label, _command_text(words)[:100]))
            if cmd not in _NOISE:
                externals.add(shape)
            return
        problems.append("%s: runs `%s`, which neither the function index nor EXTERNAL names"
                        % (label, cmd))

    def scan(text, label, func=None):
        temps = set(m.group(1) for m in _TEMP_ASSIGN_RE.finditer(text))
        calls = []
        for words in simple_commands(text):
            judge(words, label, temps, func, calls)
        return calls

    todo = scan(code, "fence")
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        rel, line, body = index[name]
        todo += scan("\n".join(body), "%s (%s:%d)" % (name, rel, line), func=name)
    for shape, (func, guard) in GUARDED.items():
        if func in seen and not any(guard in ln for ln in index[func][2]):
            problems.append("%s: the guard that exempts `%s` is missing (%r)"
                            % (func, shape, guard))
    return sorted(externals), sorted(dict.fromkeys(problems)), sorted(seen)


_RESERVATION_DST = re.compile(r"^refs/adlc/ids/(?:req|bug|lesson|assume|task)/[0-9]{3,6}$")
_OID = re.compile(r"^[0-9a-f]{7,64}$")


def push_problems(argvs):
    """Why each recorded ``git push`` is not the id-reservation push, the one push BR-2 (as
    amended) lets a runner fence make: non-force, ``<oid>:refs/adlc/ids/<kind>/<n>``, and
    moving no branch. Empty when every push is that one (ADR-7)."""
    problems = []
    for argv in argvs:
        args = list(argv)
        if args and args[0] == "git":
            args = args[1:]
        while len(args) >= 2 and args[0] in ("-C", "-c"):
            args = args[2:]
        if not args or args[0] != "push":
            continue
        rest = args[1:]
        flags = [a for a in rest if a.startswith("-")]
        positional = [a for a in rest if not a.startswith("-")]
        if flags:
            problems.append("push with %s: %s" % (" ".join(flags), " ".join(argv)))
            continue
        if len(positional) < 2:
            problems.append("push without an explicit refspec: %s" % " ".join(argv))
            continue
        for spec in positional[1:]:
            src, sep, dst = spec.partition(":")
            if spec.startswith("+") or not sep or not _OID.match(src) or \
                    not _RESERVATION_DST.match(dst):
                problems.append("push of %r is not an id reservation: %s"
                                % (spec, " ".join(argv)))
    return problems


# --------------------------------------------------------------------------- the census
_BR24 = tuple(t for t in ep.EMPTY_ALLOWLIST + ep.CLOSEOUT_EMPTY if t)


def _route(fence, policy, index, adapter, root):
    rec = {"id": fence.id, "route": None, "reason": "", "placeholders": [], "sources": [],
           "reach": [], "functions": []}
    key = fence.key
    code = fence.code
    whole_file = "%s#*" % fence.rel
    if key in EXCISED or whole_file in EXCISED:
        rec["route"], rec["reason"] = "excised", EXCISED.get(key) or EXCISED[whole_file]
        return rec
    if key in ENGINE:
        rec["route"], rec["reason"] = "engine", ENGINE[key]
        return rec
    tokens = [t for t in _BR24 if t in code]
    if tokens:
        rec["route"] = "excised"
        rec["reason"] = "it names a one-way move the orchestrator keeps"
        return rec
    if em.admits(policy, code) or _direct_with_samples(code, policy):
        rec["route"] = "direct"
        return rec
    try:
        found, sources = plan(code)
    except Unroutable as exc:
        rec["route"], rec["reason"] = "unrouted", str(exc)
        rec["refused"] = list(em.explain(policy, code) or ())
        return rec
    sample = {ph.arg: ["x"] for ph in found}
    externals, problems, funcs = reach(transform(code, sample, root="/abs/tk"), index, adapter,
                                       root)
    if problems:
        rec["route"] = "unrouted"
        rec["reason"] = "reach: " + "; ".join(problems[:3])
        rec["refused"] = list(em.explain(policy, code) or ())
        rec["problems"] = problems
        return rec
    rec["route"] = "runner"
    rec["placeholders"] = sorted(dict.fromkeys(ph.arg for ph in found))
    rec["sources"] = sources
    rec["reach"] = externals
    rec["functions"] = funcs
    return rec


def _direct_with_samples(code, policy):
    """Whether the body, with the exec notes' ``git -C <worktree>`` dropped and sample values
    in its placeholders, is admitted: the model runs such a fence itself, as written."""
    if not re.search(r"git -C <(?:worktree|repo-path)> ", code):
        return False
    text = re.sub(r"git -C <(?:worktree|repo-path)> ", "git ", code)
    for key in placeholders_of(text):
        ph = _lookup(key)
        if ph is None or ph.arg not in SAMPLE_VALUES:
            return False
        text = text.replace("<%s>" % key, SAMPLE_VALUES[ph.arg])
    return em.admits(policy, text)


def census(root, adapter=None):
    """Every fence of every exec file, routed: a list of records sorted by id."""
    import exec_adapter as ea
    adapter = adapter or ea.load("claude", root)
    policy = exec_policy(root, adapter)
    index = function_index(root)
    records = []
    for rel in EXEC_FILES:
        for fence in fences(view(root, rel), rel):
            records.append(_route(fence, policy, index, adapter, root))
    return records


def unrouted(records):
    return [r for r in records if r["route"] == "unrouted"]


def golden_doc(records):
    """The committed golden: every id with its route, placeholders and reach."""
    keep = ("id", "route", "reason", "placeholders", "sources", "reach")
    return {"comment": "REQ-682 exec fence census. Regenerate with "
                       "`python3 tools/adlc/fence_census.py --write`; a diff here is a fence "
                       "whose route, values or reach changed.",
            "fences": [{k: r[k] for k in keep if r.get(k) not in (None, "", [])}
                       for r in records]}


GOLDEN = os.path.join("harness", "claude", "exec-fence-census.json")


def dumps(doc):
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="fence_census.py", description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="rewrite the committed golden")
    group.add_argument("--check", action="store_true", help="fail when the golden is stale")
    args = parser.parse_args(argv)
    root = tkr.toolkit_root()
    records = census(root)
    bad = unrouted(records)
    for rec in bad:
        sys.stderr.write("unrouted: %s: %s\n" % (rec["id"], rec["reason"]))
    text = dumps(golden_doc(records))
    path = os.path.join(root, GOLDEN)
    if args.write:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return 1 if bad else 0
    if args.check:
        try:
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = ""
        if current != text:
            sys.stderr.write("fence_census: %s is stale; run fence_census.py --write\n" % GOLDEN)
            return 1
        return 1 if bad else 0
    for rec in records:
        sys.stdout.write("%-9s %s %s\n" % (rec["route"], rec["id"], rec["reason"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
