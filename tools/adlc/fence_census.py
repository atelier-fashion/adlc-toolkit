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
- ``direct`` — the adapter's ``matcher`` is one ``exec_matcher`` models, and it admits every
  statement over the ExecPolicy, as written, or with the exec notes' ``git -C <worktree>``
  dropped and sample values in its placeholders. On ``matcher: none`` no fence is ``direct``
  (REQ-662 BR-3, ADR-8): nothing pins how that harness matches a statement.
- ``runner`` — :func:`transform` accepts the body (every placeholder and free variable is in
  the closed tables, and in a position where its value stays data) and the static reach
  audit finds nothing (:func:`reach`). The model runs it as ``fence-run run <id>``.

Anything else is **unrouted**, and an exec prompt holding it is refused (BR-8). The census is
computed from toolkit text alone, so ``fence-run`` recomputes it on every call and trusts no
manifest, cache or environment variable (ADR-2, BR-5).

**One census per adapter** (REQ-662 ADR-8). :func:`census` routes for one exec-capable
adapter, and each has its golden, ``harness/<name>/exec-fence-census.json``. The reach audit
reads the **union** of every exec-capable adapter's deny tier and ``engine_deny``, so a fence
is ``runner`` on one adapter only when it would be on every adapter that does not run it
``direct``. ``fence-run`` accepts a fence that is ``runner`` in any of them: whichever harness
calls, no route it accepts reaches a command any adapter denies. The adapters are found from
``harness/*.yml`` under the root, never from an environment variable, argument or working
copy (REQ-682 ADR-2).

**Values** (ADR-3): a placeholder ``<name>`` or a free shell variable ``$name`` reaches the
fence only as an environment variable ``ADLC_ARG_<name>``, expanded once inside double quotes.
A placeholder is rewritten where its value cannot become code: a whole ``"<x>"`` or ``'<x>'``
token, a bare ``<x>`` word, or embedded in a double-quoted string or an unquoted word of a
statement whose command is not an interpreter (``sh``, ``eval``, ``awk``, ``sed``, …). This is
one position wider than ADR-3's three token shapes, and as safe: a quoted parameter expansion
is never re-read as shell, and the interpreter check keeps a value out of every string that is
code. A placeholder inside single quotes, a here-document, or an interpreter's arguments makes
the fence unroutable.

**The PR tie** (REQ-719 ADR-3): a placeholder whose value is a PR number carries the PR mark
(``Placeholder.pr``). ``fence-run`` reads each marked value back from the forge before the
fence runs (:func:`pr_tie_text`, the one text of that read), a tied fence's reach is read with
that read included, and its record names the values under ``tied``. A fence that hands an
unmarked value to an ``adlc_forge_pr_*`` operation as its PR argument is unroutable
(:func:`unmarked_pr_arguments`, which fails closed on what it cannot trace), and so is one
whose PR operations the check cannot read or the tie cannot cover
(:func:`pr_operation_problems`), so a fence added later starts tied or does not route. The
one exception is :data:`DECLARED_UNTIED`, keyed by full fence id, whose records name the
reason under ``untied``.

Standard library only.
"""

import functools
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
#: A REQ's own branch (REQ-662 ADR-9): it cannot spell the integration branch, a refspec, a
#: ``+`` prefix or an option, because the branch push binds it on a harness with no exact rule.
_FEATURE_BRANCH = r"(?:feat|fix|chore)/[A-Za-z0-9][A-Za-z0-9._-]*"


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
    """``pr`` is the PR mark (REQ-719 ADR-3): a value bound to a marked placeholder is checked
    by the runner to be the open PR of the branch checked out where it was called, before any
    command of the fence runs (:func:`pr_tie_text`)."""
    __slots__ = ("key", "arg", "pattern", "multi", "file", "empty_ok", "path", "scope", "pr")

    def __init__(self, key, arg, pattern, multi=False, file=False, path=False, scope=None,
                 pr=False):
        self.key = key
        self.arg = arg
        # ``$`` also matches before a final newline: an ``--arg`` value is held to the whole
        # pattern with ``\Z``. A file's value keeps ``$``, as a file the model writes ends in one.
        self.pattern = re.compile("^(?:%s)%s" % (pattern, "$" if file else r"\Z"), re.S)
        self.multi = multi
        self.file = file
        self.path = path
        self.scope = scope
        self.pr = pr
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


#: A PR number's pattern. Every placeholder that holds one carries the PR mark (REQ-719 BR-13).
PR_NUMBER = r"[0-9]{1,9}"


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
    _ph("branch-name", "branch", _FEATURE_BRANCH, path=True),
    _ph("branch", "branch", _FEATURE_BRANCH, path=True),
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
    _ph("prNumber", "pr", PR_NUMBER, pr=True),
    # Phase 7's wait before one CI read (REQ-719 ADR-6): 0 to 60 seconds and nothing else. The
    # fence is tied, so one call lasts at most the runner's PR read (fence_run.PR_TIE_TIMEOUT,
    # 20 s), this wait (60 s) and one forge read, under a harness's shell limit.
    _ph("ciWait", "ciWait", r"[0-9]|[1-5][0-9]|60"),
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
    _ph("prNumber", "prNumber", PR_NUMBER, pr=True),
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


# --------------------------------------------------------------------------- the adapters
#: Why a fence is not run as written on a harness whose matching nothing models.
NO_MATCHER = "no measurement pins this harness's statement matching (matcher: none)"


def routes_direct(adapter):
    """Whether ``adapter``'s statement matching is modelled, so a fence may be ``direct``: the
    adapter's own ``has_matcher``, which reads the loader's ``MODELLED_MATCHERS`` (REQ-662
    BR-3, ADR-8)."""
    return adapter.has_matcher


def exec_adapters(root):
    """Every exec-capable adapter under ``root``, sorted by name (REQ-662 ADR-8).

    Read from ``<root>/harness/*.yml`` and nothing else: no environment variable, argument or
    working-copy file chooses one (REQ-682 ADR-2). An adapter is exec-capable when its exec
    block carries ``exec_schema_version``. One that will not load refuses the census, since
    nothing could then say what it denies. Raises :class:`CensusError`."""
    import exec_adapter as ea
    hdir = os.path.join(root, "harness")
    try:
        names = sorted(n for n in os.listdir(hdir) if n.endswith(".yml"))
    except OSError as exc:
        raise CensusError("harness/: unreadable: %s" % exc)
    out = []
    for name in names:
        try:
            adapter = ha.load_adapter(os.path.join(hdir, name), toolkit=root)
        except ha.AdapterError as exc:
            raise CensusError("harness/%s does not load, so its deny tier is unknown: %s"
                              % (name, exc))
        if "exec_schema_version" in (adapter.get("exec") or {}):
            out.append(ea.ExecAdapter(adapter, root))
    if not out:
        raise CensusError("no adapter under %s/harness has an exec block" % root)
    return out


# --------------------------------------------------------------------------- the policy
def exec_policy(root, adapter):
    """The ExecPolicy the census judges ``direct`` against: ``adapter``'s tiers for
    :data:`SAMPLE_BRANCH`, with no project extras. The same at build time and in fence-run."""
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


def plan(code, fid=None):
    """``(placeholders, sources)`` of a body the runner can run, or :class:`Unroutable`.

    ``placeholders`` is a list of :class:`Placeholder` (``<name>`` ones, literal ones and
    free variables) and ``sources`` the partials the body sources, in order. ``fid`` is the
    fence's id: a fence :data:`DECLARED_UNTIED` names routes with an unmarked PR argument.
    """
    sources = []
    found = []
    if "ADLC_ARG_" in code:
        # The runner's bound values: a fence that set one could replace a value after the
        # runner checked it (REQ-719 BR-13).
        raise Unroutable("names ADLC_ARG_*, which only the runner sets")
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
    problems = pr_operation_problems(code)
    if problems:
        raise Unroutable(problems[0])
    unmarked = unmarked_pr_arguments(code)
    if unmarked and fid not in DECLARED_UNTIED:
        op, what = unmarked[0]
        raise Unroutable("passes %s, which carries no PR mark, as the PR argument of %s: the "
                         "runner checks a PR number the model supplies only through a marked "
                         "placeholder (REQ-719 BR-13)" % (what, op))
    return found, sources


# --------------------------------------------------------------------------- the PR tie
#: The fields the runner's PR read asks for (REQ-719 ADR-3), in the ``--fields`` form both
#: backends and the mock normalize to ``key=value`` lines (REQ-659 BR-26).
PR_TIE_FIELDS = ("number", "state", "headRefName", "isCrossRepository")


def pr_tie_text(arg):
    """The shell of the runner's read of one PR-marked value (REQ-719 ADR-3), the one text of
    it: ``fence-run`` runs it after the fence's own preload and in the fence's own environment,
    and :func:`reach_text` adds it to what a tied fence's static reach is read from, so the
    read the runner makes and the read the audit sees cannot drift (LESSON-845)."""
    return 'adlc_forge_pr_view "$%s" --fields %s' % (_env_name(arg), ",".join(PR_TIE_FIELDS))


def tied_args(placeholders):
    """The argument names of ``placeholders`` that carry the PR mark, sorted, once each."""
    return sorted(dict.fromkeys(ph.arg for ph in placeholders if ph.pr))


def reach_text(code, placeholders, root="/abs/tk"):
    """The text a runner fence's static reach is read from: the runner's PR read for each tied
    value (:func:`pr_tie_text`), then the body as the runner runs it, with a sample value
    bound to each placeholder."""
    tie = "".join(pr_tie_text(arg) + "\n" for arg in tied_args(placeholders))
    return tie + transform(code, {ph.arg: ["x"] for ph in placeholders}, root=root)


# --------------------------------------------------------------------------- BR-13
#: The ``adlc_forge_pr_*`` operations that take no PR: every other one is read as taking it
#: (REQ-719 BR-13: view, edit, ready, comment, checks, merge), so an operation added to the
#: adapter later starts checked (LESSON-781).
NOT_PR_OPERATIONS = frozenset(("adlc_forge_pr_create", "adlc_forge_pr_list"))


def is_pr_operation(name):
    """Whether ``name`` is a forge operation whose positional argument is a PR."""
    return name.startswith("adlc_forge_pr_") and name not in NOT_PR_OPERATIONS


#: Per PR operation, the options whose next word the adapter consumes as the option's value,
#: read from each function in ``partials/forge.sh`` (LESSON-716: parse as the reader does).
#: Where the GitHub arm hands its whole argv to ``gh``, an option is listed only when ``gh``
#: and the Azure DevOps arm both consume a value for it. ``view`` finds its PR itself and skips
#: only the word after ``--fields``; ``checks`` takes ``$1``; ``merge``'s own reading of its PR
#: skips only the word after ``--match-head-commit``. Any other option, and every option of an
#: operation not named here, takes no value: the word after it is checked as the PR, which can
#: only refuse more.
PR_OP_VALUE_OPTIONS = {
    "adlc_forge_pr_view": frozenset(("--fields",)),
    "adlc_forge_pr_edit": frozenset(("--title", "--body", "--body-file", "--base")),
    "adlc_forge_pr_comment": frozenset(("--body", "--body-file")),
    "adlc_forge_pr_merge": frozenset(("--match-head-commit",)),
    "adlc_forge_pr_ready": frozenset(),
    "adlc_forge_pr_checks": frozenset(),
}

#: Fences that route although they hand a PR operation a value the check finds unmarked, each
#: with why, by full fence id: any edit to the fence changes its id and drops its entry. Each
#: such record names the reason under ``untied``, in the census and in the goldens.
DECLARED_UNTIED = {
    "architect/SKILL.md#2:587fb45d":
        "the footprint publish takes $prnum from the pipeline-state.json that $REQ selects, a "
        "file the session writes: an older gap of BR-13's kind, kept routed until its owner "
        "decides (REQ-719 Phase 5)",
}

#: A positional parameter, or their count: the runner hands a fence none, so one is always a
#: value the fence put there itself (``set --``, a function's argument).
_POSITIONAL_RE = re.compile(r"\$(?:[1-9@*#]|\{(?:#?[0-9]+|#?[@*]|#)(?:[^A-Za-z0-9_}][^}]*)?\})")
#: A special parameter that is not a positional one: a status, a pid, the flags, the shell.
_SPECIAL_RE = re.compile(r"\$(?:[?$!0-]|\{[?$!0-]\})")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VAR_AT = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_ASSIGN_WORD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=(.*)$", re.S)
_REDIR_RE = re.compile(r"^([0-9]*)(<<<|<>|<&|>&|>>|>\||&>>|&>|<|>)(.*)$", re.S)
_INPUT_OPS = ("<", "<<", "<<<", "<>", "<&")
_OUTPUT_OPS = (">", ">>", ">|", "&>", "&>>", "<>")
#: A name an arithmetic expression assigns: ``n=``, ``n+=``, ``n<<=``, ``n++``, ``--n``.
_ARITH_SET = re.compile(r"(?:\+\+|--)\s*([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*"
                        r"(?:\+\+|--|(?:[-+*/%&|^]|<<|>>)?=(?!=))")
#: The PR operations a fence names, wherever it names them.
_PR_OP_NAME = re.compile(r"adlc_forge_pr_(?!(?:create|list)(?![A-Za-z0-9_]))[A-Za-z0-9_]+")
#: Names whose value changes which repository, host or configuration the forge resolves: a
#: fence that sets one, or changes directory, would act where the runner's PR read never looked.
_FORGE_ENV = re.compile(r"^(?:GH_[A-Z0-9_]*|GIT_[A-Z0-9_]*|ADLC_FORGE_[A-Z0-9_]*|HOME|"
                        r"XDG_CONFIG_HOME)(?:\+?=|$)")
#: The commands that run the command after them as it is, for finding a call's head.
_PASS_THROUGH = ("command", "exec", "nohup", "time")
#: What the fence's standard input is said to hold: under ``fence-run`` it is /dev/null, but
#: the check does not rest on that.
_STDIN = "the fence's standard input"


def _dequote(word):
    """``word`` with its quotes and backslashes taken out, as the shell reads a plain word."""
    return re.sub(r"\\(.)", r"\1", word).replace('"', "").replace("'", "")


def _call_head(words, through=_PASS_THROUGH):
    """``(index, name)`` of the word that runs, after leading assignments, redirections and
    the pass-through commands; ``(len(words), "")`` when nothing runs."""
    k = 0
    while k < len(words):
        word = words[k]
        if _ASSIGN_WORD.match(word):
            k += 1
            continue
        name = _dequote(word)
        if name in through and not (name == "command" and k + 1 < len(words) and
                                    words[k + 1] in ("-v", "-V")):
            k += 1
            if name == "command" and k < len(words) and words[k] == "-p":
                k += 1
            continue
        return k, name
    return len(words), ""


def _is_placeholder_word(word):
    match = _PH_RE.fullmatch(word)
    return bool(match and _lookup(match.group(1)))


class _Node(object):
    """One command of :func:`_parse`'s tree: ``simple`` (``words``), ``group`` (``{…}`` or
    ``(…)``), ``if``, ``loop`` (``while``, ``until``), ``for``, ``select``, ``case``, ``func`` or
    ``arith`` (``((…))``), with its redirections as ``(operator, target)``, a here-document's
    target being its body. ``body`` is a list of pipelines; ``pipe`` is the one this node is an
    element of; ``header`` a ``for`` list or ``case`` word, ``None`` for a ``for`` with none."""
    __slots__ = ("kind", "words", "redirs", "body", "parent", "pipe", "name", "header")

    def __init__(self, kind, parent):
        self.kind = kind
        self.words = []
        self.redirs = []
        self.body = []
        self.parent = parent
        self.pipe = None
        self.name = None
        self.header = None


class _Parser(object):
    """A reading of :func:`shell_tokens`'s tokens into :class:`_Node` trees, for the PR
    argument check. Not a shell: what it does not recognize it steps over, and it sets
    ``broken`` when a construct does not close, so its reader can fail closed."""

    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0
        self.broken = False

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def at_word(self, *vals):
        kind, val = self.peek()
        return kind == "word" and (not vals or val in vals)

    def expect(self, val):
        if self.peek()[1] == val:
            self.i += 1
        else:
            self.broken = True

    def newlines(self):
        while self.peek() in (("op", "\n"), ("op", ";")):
            self.i += 1

    def statements(self, parent, ends):
        """The pipelines up to a word or operator in ``ends`` (not consumed), or the end."""
        pipes = []
        while self.i < len(self.toks):
            kind, val = self.peek()
            if kind == "op" and val in (";", "&", "\n", "&&", "||"):
                self.i += 1
                continue
            if val in ends:
                break
            pipe = self.pipeline(parent, ends)
            if pipe:
                pipes.append(pipe)
            else:
                self.i += 1
                self.broken = True
        return pipes

    def pipeline(self, parent, ends):
        pipe = []
        if self.at_word("!"):
            self.i += 1
        while True:
            node = self.command(parent, ends)
            if node is None:
                break
            node.pipe = pipe
            pipe.append(node)
            if self.peek() != ("op", "|"):
                break
            self.i += 1
            while self.peek() == ("op", "\n"):
                self.i += 1
        return pipe

    def command(self, parent, ends):
        kind, val = self.peek()
        if kind is None or (kind == "word" and val in ends):
            return None
        if kind == "doc":
            return self.simple(parent)
        if kind == "op":
            if val != "(":
                return None
            if self.peek(1) == ("op", "("):
                return self.arith(parent)
            self.i += 1
            node = _Node("group", parent)
            node.body = self.statements(node, (")",))
            self.expect(")")
            return self.redirects(node)
        if val == "{":
            self.i += 1
            node = _Node("group", parent)
            node.body = self.statements(node, ("}",))
            self.expect("}")
            return self.redirects(node)
        if val == "if":
            self.i += 1
            node = _Node("if", parent)
            while True:
                node.body += self.statements(node, ("then", "elif", "else", "fi"))
                if not self.at_word("then", "elif", "else"):
                    break
                self.i += 1
            self.expect("fi")
            return self.redirects(node)
        if val in ("while", "until"):
            self.i += 1
            node = _Node("loop", parent)
            node.body = self.statements(node, ("do",))
            self.expect("do")
            node.body += self.statements(node, ("done",))
            self.expect("done")
            return self.redirects(node)
        if val in ("for", "select"):
            return self.for_loop(parent, val)
        if val == "case":
            return self.case(parent)
        if val == "function" and self.peek(1)[0] == "word":
            name = self.peek(1)[1]
            self.i += 2
            if self.peek() == ("op", "(") and self.peek(1) == ("op", ")"):
                self.i += 2
            return self.function(parent, name)
        if _NAME_OK.match(val) and self.peek(1) == ("op", "(") and self.peek(2) == ("op", ")"):
            self.i += 3
            return self.function(parent, val)
        return self.simple(parent)

    def for_loop(self, parent, keyword):
        self.i += 1
        node = _Node(keyword, parent)
        if not self.at_word():
            self.broken = True
            return node
        node.name = self.peek()[1]
        self.i += 1
        while self.peek() == ("op", "\n"):
            self.i += 1
        if self.at_word("in"):
            self.i += 1
            node.header = []
            while self.at_word():
                node.header.append(self.peek()[1])
                self.i += 1
        self.newlines()
        self.expect("do")
        node.body = self.statements(node, ("done",))
        self.expect("done")
        return self.redirects(node)

    def case(self, parent):
        self.i += 1
        node = _Node("case", parent)
        if self.at_word():
            node.header = [self.peek()[1]]
            self.i += 1
        while self.peek() == ("op", "\n"):
            self.i += 1
        self.expect("in")
        while self.i < len(self.toks):
            self.newlines()
            if self.at_word("esac"):
                break
            while self.i < len(self.toks) and self.peek() != ("op", ")"):
                self.i += 1
            self.i += 1
            node.body += self.statements(node, (";;", "esac"))
            if self.peek() == ("op", ";;"):
                self.i += 1
        self.expect("esac")
        return self.redirects(node)

    def function(self, parent, name):
        node = _Node("func", parent)
        node.name = name
        while self.peek() == ("op", "\n"):
            self.i += 1
        body = self.command(node, ())
        if body is None:
            self.broken = True
        else:
            body.pipe = [body]
            node.body = [body.pipe]
        return node

    def arith(self, parent):
        node = _Node("arith", parent)
        self.i += 2
        depth = 0
        while self.i < len(self.toks):
            kind, val = self.peek()
            self.i += 1
            if kind == "op" and val == "(":
                depth += 1
            elif kind == "op" and val == ")":
                if depth == 0:
                    self.expect(")")
                    return self.redirects(node)
                depth -= 1
            elif kind == "word":
                node.words.append(val)
        self.broken = True
        return node

    def simple(self, parent):
        node = _Node("simple", parent)
        self.collect(node)
        return node

    def redirects(self, node):
        self.collect(node)
        if node.kind != "simple" and node.words:
            self.broken = True       # words after a compound command's close
        return node

    def collect(self, node):
        """The words and here-documents up to the next operator, split into ``node``'s words
        and redirections. A closed-table ``<name>`` word is a placeholder, not a redirection."""
        words = []
        while True:
            kind, val = self.peek()
            if kind == "word":
                words.append(val)
            elif kind == "doc":
                node.redirs.append(("<<", val))
            else:
                break
            self.i += 1
        k = 0
        while k < len(words):
            word = words[k]
            red = None if _is_placeholder_word(word) else _REDIR_RE.match(word)
            if red is None:
                node.words.append(word)
                k += 1
                continue
            target = red.group(3)
            if not target and k + 1 < len(words):
                k += 1
                target = words[k]
            elif not target:
                self.broken = True
                target = None
            node.redirs.append((red.group(2), target))
            k += 1


def _parse(code):
    """``(pipelines, broken)`` of shell ``code``: see :class:`_Parser`. A here-document whose
    body cannot be found, or a ``<<`` inside a word, which the tokenizer does not split,
    marks the reading broken."""
    bodies = {}
    toks = []
    count = 0
    broken = False
    for kind, val in shell_tokens(code, bodies):
        if kind == "subst":
            continue
        if kind == "word" and val == "<<":
            toks.append(("doc", bodies.get(count)))
            broken = broken or count not in bodies
            count += 1
            continue
        if kind == "word" and re.search(r"(?<!<)<<(?!<)", _strip_quoted(val)):
            broken = True
        toks.append((kind, val))
    parser = _Parser(toks)
    pipes = parser.statements(None, ())
    return pipes, broken or parser.broken


def _strip_quoted(word):
    """``word`` without its single-quoted parts: text no shell reads as syntax."""
    return re.sub(r"'[^']*'", "", word)


def _walk(pipes):
    """Every node of ``pipes``, outer before inner."""
    for pipe in pipes:
        for node in pipe:
            yield node
            for inner in _walk(node.body):
                yield inner


def _own_texts(node):
    """The texts ``node`` holds itself, not counting the commands in its body: its words, its
    ``for`` list or ``case`` word, and its redirections' targets and here-document bodies."""
    return node.words + (node.header or []) + [t for _op, t in node.redirs if t is not None]


def _exempt(node):
    """Whether ``node`` calls ``adlc_forge_pr_create`` or ``adlc_forge_pr_list``, whose output is
    the forge's answer, not a value the model supplies, whatever their arguments hold (BR-14)."""
    return node.kind == "simple" and _call_head(node.words)[1] in NOT_PR_OPERATIONS


def _node_text(node):
    """All the text of ``node`` and the commands inside it that can carry a value into what
    it prints, every exempt call left out (:func:`_exempt`)."""
    parts = []
    for one in [node] + list(_walk(node.body)):
        if not _exempt(one):
            parts += [_filtered(t) for t in _own_texts(one)]
    return " ".join(parts)


@functools.lru_cache(maxsize=4096)
def _commands_text(code):
    """:func:`_node_text` of every top-level command of ``code``."""
    pipes, _broken = _parse(code)
    return " ".join(_node_text(node) for pipe in pipes for node in pipe)


@functools.lru_cache(maxsize=4096)
def _filtered(text):
    """``text`` with each command substitution replaced by :func:`_commands_text` of what it
    runs, so a substitution of an exempt call adds nothing (BR-14). Arithmetic stays as it is."""
    out = []
    i = 0
    while i < len(text):
        if text.startswith("$((", i):
            end = _skip_paren(text, i + 1)
            out.append(text[i:end])
            i = end
        elif text.startswith("$(", i):
            end = _skip_paren(text, i + 1)
            out.append(" %s " % _commands_text(text[i + 2:end - 1]))
            i = end
        elif text[i] == "`":
            end = text.find("`", i + 1)
            end = len(text) if end == -1 else end
            out.append(" %s " % _commands_text(text[i + 1:end]))
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _strip_substitutions(text):
    """``text`` with each command substitution (``$(…)`` and backticks) taken out, for reading
    what a word itself spells; an arithmetic ``$((…))`` is text, and stays."""
    out = []
    i = 0
    while i < len(text):
        if text.startswith("$((", i):
            end = _skip_paren(text, i + 1)
            out.append(text[i:end])
            i = end
        elif text.startswith("$(", i):
            i = _skip_paren(text, i + 1)
        elif text[i] == "`":
            end = text.find("`", i + 1)
            i = len(text) if end == -1 else end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _substitutions(text):
    """The inner text of each command substitution in ``text``, outermost only."""
    out = []
    i = 0
    while i < len(text):
        if text.startswith("$((", i):
            end = _skip_paren(text, i + 1)
            out += _substitutions(text[i + 3:end - 2])
            i = end
        elif text.startswith("$(", i):
            end = _skip_paren(text, i + 1)
            out.append(text[i + 2:end - 1])
            i = end
        elif text[i] == "`":
            end = text.find("`", i + 1)
            end = len(text) if end == -1 else end
            out.append(text[i + 1:end])
            i = end + 1
        else:
            i += 1
    return out


def _var_refs(text):
    """The names ``text`` reads: each ``$name`` and ``${name…}``, the names inside ``${…}``'s
    operand, and every name inside an arithmetic expansion, a subscript or a substring offset,
    which read a variable by its bare name."""
    names = []
    i = 0
    while i < len(text):
        if text.startswith("$((", i):
            end = _skip_paren(text, i + 1)
            names += _IDENT_RE.findall(text[i + 3:end - 2])
            i = end
        elif text.startswith("${", i):
            end = _skip_brace(text, i + 1)
            inner = text[i + 2:end - 1]
            head = re.match(r"[#!]?([A-Za-z_][A-Za-z0-9_]*)", inner)
            if head:
                names.append(head.group(1))
                rest = inner[head.end():]
                if rest.startswith("[") or (rest.startswith(":") and rest[1:2] not in "-=+?"):
                    names += _IDENT_RE.findall(rest)
                else:
                    names += _var_refs(rest)
            else:
                names += _var_refs(inner)
            i = end
        else:
            match = _VAR_AT.match(text, i)
            if match:
                names.append(match.group(1))
                i = match.end()
            else:
                i += 1
    return names


class _Flow(object):
    """What :func:`_flow` found: ``tainted`` ``{name: what}``, ``assigned`` (every name the
    fence gives a value), ``free`` (:func:`free_vars`) and ``paths`` ``{path: what}``, the files
    a fence writes from tainted text, named by a literal path."""
    __slots__ = ("tainted", "assigned", "free", "paths")


def _taint_in(text, flow):
    """The first model-supplied value without the PR mark ``text`` holds, spelled as the fence
    spells it, or ``None``: a ``<name>`` or literal placeholder whose entry is unmarked, a free
    variable a table names without the mark, a positional parameter, a tainted variable, or a
    file the fence wrote from tainted text. A command substitution counts what it runs, less
    every exempt call (:func:`_filtered`)."""
    text = _filtered(text)
    for match in _PH_RE.finditer(text):
        ph = _lookup(match.group(1))
        if ph is not None and not ph.pr:
            return "<%s>" % match.group(1)
    for lit, ph in LITERAL_PLACEHOLDERS.items():
        if lit in text and not ph.pr:
            return lit
    match = _POSITIONAL_RE.search(text)
    if match:
        return "%s (a positional parameter)" % match.group(0)
    for name in _var_refs(text):
        if name in flow.tainted:
            return "$%s (assigned from %s)" % (name, flow.tainted[name])
        ph = VAR_PLACEHOLDERS.get(name)
        if name in flow.free and ph is not None and not ph.pr:
            return "$%s" % name
    for path, what in sorted(flow.paths.items()):
        if path in text:
            return "%s (a file written from %s)" % (path, what)
    return None


def _feeder(node):
    """``(text, None)``: the text that feeds ``node``'s standard input (its own input
    redirections, or the commands piped into it or into a command around it); or ``(None,
    why)`` when that is a descriptor or here-document the check cannot place, a function's
    caller, or the fence's own standard input."""
    cur = node
    while cur is not None:
        ins = [(op, t) for op, t in cur.redirs if op in _INPUT_OPS]
        if ins:
            if any(op == "<&" or t is None for op, t in ins):
                return None, "a descriptor or here-document the check cannot place"
            return " ".join(t for _op, t in ins), None
        if cur.pipe and cur.pipe[0] is not cur:
            k = next(j for j, other in enumerate(cur.pipe) if other is cur)
            return " ".join(_node_text(other) for other in cur.pipe[:k]), None
        if cur.kind == "func":
            return None, "the caller of function %s" % cur.name
        cur = cur.parent
    return None, _STDIN


def _unseen(word, data=False):
    """The names ``word`` may give a value in a way :func:`_flow` does not follow: every name
    it holds that is not a read (``$x``, ``${x…}`` without ``=``), a name an arithmetic
    expansion only reads, an option's letters, an escaped character (``\\n``) or a segment of
    a path. With ``data`` (a
    here-document body) only an assigning expansion or arithmetic counts."""
    w = _strip_substitutions(word)
    found = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?:?=", w))
    out = []
    i = 0
    while i < len(w):
        if w.startswith("$((", i):
            end = _skip_paren(w, i + 1)
            for match in _ARITH_SET.finditer(w[i + 3:end - 2]):
                found.add(match.group(1) or match.group(2))
            out.append(" ")
            i = end
        else:
            out.append(w[i])
            i += 1
    if data:
        return found
    w = re.sub(r"\$\{[#!]?[A-Za-z_][A-Za-z0-9_]*", "${", "".join(out))
    w = _VAR_AT.sub("$", w)
    if _dequote(w).startswith("-"):
        w = w.split("=", 1)[1] if "=" in w else ""
    for match in _IDENT_RE.finditer(w):
        before = w[match.start() - 1] if match.start() else ""
        after = w[match.end():match.end() + 2]
        if before in ("/", ".", "\\") or (after[:1] in ("/", ".") and after != "/="):
            continue
        found.add(match.group(0))
    return found


def _flow(code):
    """Which variables ``code`` gives a model-supplied value without the PR mark (REQ-719
    BR-13), as a :class:`_Flow`.

    Flow-insensitive: a name ever given a tainted value is tainted everywhere, so reusing a
    name is refused, and control flow is not followed (a value the fence spells itself is its
    own, whichever branch chose it). A value is tainted when its text holds an unmarked
    placeholder, an unmarked free variable a table names, a positional parameter or a tainted
    variable (:func:`_taint_in`). That text is an assignment's value with what its command
    substitutions run, a ``for`` list, and for a ``read`` what feeds it (:func:`_feeder`): a
    here-document, a here-string, a redirected file's name, or the commands piped in. What
    ``adlc_forge_pr_create`` and ``adlc_forge_pr_list`` print adds nothing (BR-14).

    Fail closed: a ``read`` from a descriptor, a function's caller or the fence's standard
    input; ``for x`` over the positional parameters; ``select``; an arithmetic command and
    ``let``; a ``getopts``; a name given a value through a computed name, which taints every
    name; and a name that occurs anywhere the check does not read as a read or one of the
    assignments above (``printf -v``, ``${x:=…}``, ``declare``) are tainted. A file a command
    writes from tainted text taints the variable naming it, or its literal path, and so does
    a command handed tainted text for each variable its arguments name (it may write that
    file); the forge's own operations write none. Reaching the end, the iteration stops."""
    flow = _Flow()
    flow.free = set(free_vars(code))
    assigns = []        # ([names], text): each name is given text's value
    always = {}         # name: what, tainted whatever any text holds
    weak = {}           # the same, for a construct the check does not follow: a value it can
    #                     trace wins the message
    file_writes = []    # ([names], literal path or None, input text, label)
    words = []          # (word, set of names its leading `name=` is read as assigning, data)
    computed = []

    def visit(text):
        pipes, broken = _parse(text)
        for node in _walk(pipes):
            for t in _own_texts(node):
                for sub in _substitutions(t):
                    visit(sub)
            for op, t in node.redirs:
                if op == "<<" and t is not None:
                    words.append((t, (), True))
            if node.kind == "simple":
                simple(node, broken)
            elif node.kind in ("for", "select"):
                if node.header is None:
                    always.setdefault(node.name, "a positional parameter (`for %s`)" % node.name)
                else:
                    assigns.append(([node.name], " ".join(node.header)))
                    words.extend((w, (), False) for w in node.header)
                if node.kind == "select":
                    always.setdefault(node.name, _STDIN)
                    always.setdefault("REPLY", _STDIN)
            elif node.kind == "arith":
                for w in node.words:
                    for name in _IDENT_RE.findall(w):
                        always.setdefault(name, "an arithmetic command")
            elif node.kind == "case":
                words.extend((w, (), False) for w in node.header or ())
            writes(node)

    def writes(node):
        outs = [t for op, t in node.redirs if op in _OUTPUT_OPS and t is not None]
        outs = [t for t in outs if _dequote(t) not in ("/dev/null", "/dev/stderr", "/dev/stdout")]
        if not outs:
            return
        fed, why = _feeder(node)
        text = _node_text(node) + " " + (fed or "")
        for target in outs:
            names = [n for n in _var_refs(target) if n not in flow.free]
            literal = None if "$" in target else _dequote(target)
            if why:
                for name in names:
                    always.setdefault(name, "a file written from %s" % why)
                if literal:
                    flow.paths.setdefault(literal, why)
            else:
                file_writes.append((names, literal, text, "a file written from %s"))
            words.append((target, (), False))

    def simple(node, broken):
        ws = node.words
        k, head = _call_head(ws, through=_PASS_THROUGH + ("builtin",))
        for j, w in enumerate(ws):
            match = _ASSIGN_WORD.match(w) if j < k else None
            if match:
                assigns.append(([match.group(1)], match.group(2)))
                words.append((w, (match.group(1),), False))
        args = ws[k + 1:]
        if head in ("export", "readonly", "local") and not any(a.startswith("-") for a in args):
            for a in args:
                match = _ASSIGN_WORD.match(a)
                if match:
                    assigns.append(([match.group(1)], match.group(2)))
                    words.append((a, (match.group(1),), False))
                elif not _NAME_OK.match(a):
                    words.append((a, (), False))
                    if "$" in a.split("=", 1)[0]:
                        computed.append(a)
            return
        if head == "unset":
            words.extend((a, (), False) for a in args if not _NAME_OK.match(a))
            return
        if head in ("read", "mapfile", "readarray"):
            targets = [a for a in args if _NAME_OK.match(a)]
            fed, why = _feeder(node)
            if broken:
                fed, why = None, "a here-document the check cannot place"
            if any(a.startswith("-") and ("u" in a or "p" in a) for a in args):
                fed, why = None, "a descriptor or coprocess the check does not follow"
            computed.extend(a for a in args if not _NAME_OK.match(a) and "$" in a)
            targets = targets or ["REPLY" if head == "read" else "MAPFILE"]
            if why:
                for name in targets:
                    always.setdefault(name, why)
            else:
                assigns.append((targets, fed))
            words.extend((a, (), False) for a in args if not _NAME_OK.match(a))
            return
        if head == "getopts":
            for name in ["OPTARG", "OPTIND"] + [a for a in args[1:2] if _NAME_OK.match(a)]:
                always.setdefault(name, "getopts")
        if head == "let":
            for a in args:
                for name in _IDENT_RE.findall(a):
                    always.setdefault(name, "let")
        if head in ("declare", "typeset", "export", "readonly", "local") and \
                any("$" in a.split("=", 1)[0] for a in args if not a.startswith("-")):
            computed.append(head)
        if head in ("printf", "print") and \
                any(a == "-v" and "$" in b for a, b in zip(args, args[1:])):
            computed.append(head)
        words.extend((w, (), False) for w in ws[k:])
        if not head.startswith("adlc_forge_"):
            names = [n for a in args for n in _var_refs(_strip_substitutions(a))
                     if n not in flow.free]
            if names:
                fed, _why = _feeder(node)
                file_writes.append((names, None, " ".join(args) + " " + (fed or ""),
                                    "an argument of a command handed %s"))

    flow.paths = {}
    visit(code)
    assigned = set(always)
    for names, _text in assigns:
        assigned.update(names)
    for word, recognized, data in words:
        lead = ""
        for name in recognized:
            match = re.match(r"%s\+?=" % name, word)
            lead = match.group(0) if match else ""
        for name in _unseen(word[len(lead):], data) & assigned:
            weak.setdefault(name, "a construct the check does not follow (%s)" % word[:60])
    # A name the fence assigns in a way none of the above reads (it is not free, yet nothing
    # here gives it a value): what it holds is not followed either.
    regex_assigned = {v for v in _all_assigned(code)} - assigned
    for name in regex_assigned:
        weak.setdefault(name, "an assignment the check does not follow")
        assigned.add(name)
    if computed:
        for name in assigned:
            weak.setdefault(name, "a variable whose name the fence computes (%s)"
                            % computed[0][:60])
    flow.assigned = assigned
    flow.tainted = dict(always)
    _spread(flow, assigns, file_writes)
    for name, what in weak.items():
        flow.tainted.setdefault(name, what)
    _spread(flow, assigns, file_writes)
    return flow


def _spread(flow, assigns, file_writes):
    """Taint each name given a value from tainted text, to a fixed point (:func:`_flow`)."""
    changed = True
    while changed:
        changed = False
        for names, text in assigns:
            what = _taint_in(text, flow)
            for name in names:
                if what is not None and name not in flow.tainted:
                    flow.tainted[name] = what
                    changed = True
        for names, literal, text, label in file_writes:
            what = _taint_in(text, flow)
            if what is None:
                continue
            for name in names:
                if name not in flow.tainted:
                    flow.tainted[name] = label % what
                    changed = True
            if literal and literal not in flow.paths:
                flow.paths[literal] = what
                changed = True


def _all_assigned(code):
    """Every name :func:`free_vars` reads as assigned in ``code``."""
    names = set()
    for line in code.split("\n"):
        if line.lstrip().startswith("#"):
            continue
        names |= {m.group(1) for m in _ASSIGN_RE.finditer(line)}
        for m in _FOR_READ_RE.finditer(line):
            names |= set(m.group(1).split()) - {"in", "do"}
    return names


def tainted_vars(code):
    """``{name: what}``: each variable ``code`` gives a model-supplied value without the PR
    mark, directly or through another variable (REQ-719 BR-13, :func:`_flow`). ``what`` names
    the value, as the fence spells it."""
    return _flow(code).tainted


def _pr_positionals(op, words):
    """The words of one call of the PR operation ``op`` that can be its PR: every word after the
    operation that is neither an option, the value of an option :data:`PR_OP_VALUE_OPTIONS`
    names for ``op``, nor a redirection."""
    takes = PR_OP_VALUE_OPTIONS.get(op, frozenset())
    out = []
    skip = False
    for word in words[1:]:
        if skip:
            skip = False
            continue
        bare = _bare(word)
        # A bare `<prNumber>` is a placeholder the runner rewrites, not a redirection.
        red = None if _PH_RE.match(word) else _REDIRECT_WORD.match(word)
        if red:
            skip = not red.group(1)
            continue
        if bare.startswith("-"):
            skip = bare in takes
            continue
        out.append(word)
    return out


def _pr_word_problem(word, flow):
    """What makes ``word``, a PR argument, carry no PR mark, spelled as the fence spells it, or
    ``None``. Outside its command substitutions every placeholder must be marked and every
    variable a marked free one or one the fence assigns and :func:`_flow` finds clean; a
    positional or special parameter, or a variable the fence never assigns, is refused. A
    substitution is held to :func:`_taint_in`."""
    direct = _strip_substitutions(word)
    for match in _PH_RE.finditer(direct):
        ph = _lookup(match.group(1))
        if ph is not None and not ph.pr:
            return "<%s>" % match.group(1)
    for lit, ph in LITERAL_PLACEHOLDERS.items():
        if lit in direct and not ph.pr:
            return lit
    match = _POSITIONAL_RE.search(direct)
    if match:
        return "%s (a positional parameter)" % match.group(0)
    match = _SPECIAL_RE.search(direct)
    if match:
        return "%s (a special parameter)" % match.group(0)
    for name in _var_refs(direct):
        ph = VAR_PLACEHOLDERS.get(name)
        if name in flow.free and ph is not None and name not in flow.assigned:
            if not ph.pr:
                return "$%s" % name
            continue
        if name in flow.tainted:
            return "$%s (assigned from %s)" % (name, flow.tainted[name])
        if name not in flow.assigned:
            return "$%s (a variable the fence never assigns)" % name
    for sub in _substitutions(word):
        what = _taint_in("$(%s)" % sub, flow)
        if what is not None:
            return what
    return None


def _pr_calls(code):
    """``[(operation, words)]`` for each call of a PR operation in ``code``, substitutions
    included, read through every wrapper :func:`_unwrap` knows."""
    out = []
    for words in simple_commands(code):
        words = _unwrap(words) or []
        if words and is_pr_operation(_dequote(words[0])):
            out.append((_dequote(words[0]), words))
    return out


def pr_operation_problems(code):
    """Why ``code``'s PR operations cannot be checked at all (REQ-719 BR-13), each a reason the
    fence does not route, or empty:

    - a PR operation named anywhere but as the command of a call the check reads: through
      ``xargs``, ``eval``, ``sh -c``, a variable or a string, its PR is not a word it can see;
    - ``-R``/``--repo`` on a PR operation, in any spelling ``gh`` reads: the runner's PR read is
      made without it, so the operation would act in a repository the tie never read;
    - setting ``GH_*``, ``GIT_*``, ``ADLC_FORGE_*``, ``HOME`` or ``XDG_CONFIG_HOME``, or changing
      directory, in a fence with a PR operation, for the same reason;
    - an option of a PR operation whose name holds a value, which could spell either."""
    bodies = {}
    toks = shell_tokens(code, bodies)
    texts = [_dequote(v) for k, v in toks if k == "word"] + list(bodies.values())
    named = [m.group(0) for t in texts for m in _PR_OP_NAME.finditer(t)]
    if not named:
        return []
    problems = []
    direct = []
    for words in simple_commands(code):
        k, head = _call_head(words)
        if is_pr_operation(head):
            direct.append(head)
    for op in sorted(set(named)):
        if named.count(op) > direct.count(op):
            problems.append("names %s outside a call the check reads (through xargs, eval, "
                            "`sh -c`, a variable or a string), so its PR argument cannot be "
                            "checked (REQ-719 BR-13)" % op)
    for op, words in _pr_calls(code):
        for word in words[1:]:
            bare = _dequote(word)
            if bare == "--repo" or bare.startswith("--repo=") or \
                    (bare.startswith("-") and not bare.startswith("--") and "R" in bare):
                problems.append("names the repository of %s with %s: the runner's PR read is "
                                "made without it, so the operation would act in a repository "
                                "the tie never read (REQ-719 BR-13)" % (op, word))
            elif bare.startswith("-") and re.search(r"[$<`]", word.split("=", 1)[0]):
                problems.append("hands %s the option %s, whose name holds a value: the check "
                                "cannot tell it from the PR or -R (REQ-719 BR-13)" % (op, word))
    for val in _all_words(code):
        if _FORGE_ENV.match(_dequote(val)):
            problems.append("sets %s in a fence with a PR operation: the runner's PR read is "
                            "made without it, so the operation would act where the tie never "
                            "read (REQ-719 BR-13)" % _dequote(val).split("=", 1)[0])
    for words in simple_commands(code):
        _k, head = _call_head(words)
        if head in ("cd", "pushd", "popd"):
            problems.append("changes directory (%s) in a fence with a PR operation: the "
                            "runner's PR read is made where it was called, so the operation "
                            "would act where the tie never read (REQ-719 BR-13)" % head)
    return list(dict.fromkeys(problems))


def _all_words(code):
    """Every word of ``code``, the words of its command substitutions included."""
    out = []
    for kind, val in shell_tokens(code):
        if kind == "word":
            out.append(val)
        elif kind == "subst":
            out += _all_words(val)
    return out


def unmarked_pr_arguments(code):
    """``[(operation, what)]`` for each call in ``code`` of a PR operation
    (:func:`is_pr_operation`) whose PR argument holds a model-supplied value without the PR
    mark (REQ-719 BR-13), as :func:`_pr_word_problem` names it. A number the fence fills from
    ``adlc_forge_pr_create`` or ``adlc_forge_pr_list`` is the forge's, not the model's (BR-14).
    Empty when every such argument is marked. A call with no PR argument at all (the current
    branch's PR) has none to check."""
    calls = _pr_calls(code)
    if not calls:
        return []
    flow = _flow(code)
    found = []
    for op, words in calls:
        for word in _pr_positionals(op, words):
            what = _pr_word_problem(word, flow)
            if what is not None:
                found.append((op, what))
                break
    return found


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


def runner_reads(root):
    """Every toolkit file fence-run reads besides the exec set: every adapter it may load to
    find the exec-capable ones (REQ-662 ADR-8), the template, itself, and the executables its
    fences run. The orchestrator's install manifest covers them (``exec_safety.install_files``),
    so a change mid-run is caught."""
    try:
        names = sorted(n for n in os.listdir(os.path.join(root, "harness")) if n.endswith(".yml"))
    except OSError:
        names = []
    return tuple("harness/" + n for n in names) + \
        ("templates/permissions.yml", "tools/adlc/fence-run") + \
        tuple(sorted(set(rel for rels in TOOLKIT_EXECUTABLES.values() for rel in rels)))


#: :func:`runner_reads` of the toolkit this module belongs to.
RUNNER_READS = runner_reads(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))


#: The pushes a runner fence may make, by kind: REQ-682 BR-2's two exceptions to the deny tier
#: (as amended 2026-11-09 and 2026-11-17). Any other push fails the audit.
#:
#: - ``id-reservation``: the one function whose push is reach, a non-force push of a new ref
#:   under refs/adlc/ids/ that moves no branch (REQ-682 ADR-7).
#: - ``branch``: the Step 0 branch push, made by the fence body itself and only in exactly this
#:   argv (REQ-662 ADR-9). It takes the runner route on a harness whose rules have no exact
#:   form; on ``claude`` the fence stays ``direct``. ``same_dir`` names the values the runner
#:   holds to the directory it was called from, and the ``branch`` value's pattern cannot spell
#:   the integration branch, a refspec, a ``+`` prefix or an option.
ID_RESERVATION = "id-reservation"
BRANCH_PUSH = "branch"
PUSH_REACH = {
    ID_RESERVATION: {"function": "adlc_reserve_id",
                     "spelling": "git push origin <oid>:refs/adlc/ids/<kind>/<n>"},
    BRANCH_PUSH: {"argv": ("git", "-C", '"${ADLC_ARG_worktree}"', "push", "-u", "origin",
                           '"${ADLC_ARG_branch}"'),
                  "spelling": "git -C $ADLC_ARG_worktree push -u origin $ADLC_ARG_branch",
                  "same_dir": ("worktree",),
                  # The runner pushes only the branch checked out in that directory, so on a
                  # harness whose exact rule names the run's own branch the union adds no
                  # other branch to what a model can push.
                  "head": ("branch",)},
}


def push_kind(words, func):
    """The :data:`PUSH_REACH` kind of one ``git push`` command (its words as the body holds
    them, wrappers dropped), run by function ``func`` (``None``: the fence body), or ``None``
    when it is neither."""
    for kind, spec in PUSH_REACH.items():
        if "function" in spec and func == spec["function"]:
            return kind
        if "argv" in spec and func is None and tuple(words) == spec["argv"]:
            return kind
    return None
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


def shell_tokens(text, bodies=None):
    """``("word", raw)``, ``("op", op)`` and ``("subst", inner)`` tokens of shell ``text``.

    Quotes, ``${…}`` and ``$(…)`` stay inside their word, and each command substitution's
    inner text is also yielded, to be read as commands in turn. Comments and here-document
    bodies are dropped. A reading for the reach audit, not a shell: it is conservative where
    it is unsure, because an unknown word fails the audit rather than passing it.

    Each here-document operator is the word ``<<``. With ``bodies`` (a dict), the body of the
    k-th one is stored under ``k``; one whose body cannot be found has no entry."""
    out = []
    docs = []
    i = 0
    n = len(text)
    count = 0
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(("op", "\n"))
            i += 1
            for delim, k in docs:
                lines = []
                while i < n:
                    end = text.find("\n", i)
                    end = n if end == -1 else end
                    line = text[i:end]
                    i = end + 1
                    if line.strip() == delim:
                        break
                    lines.append(line)
                if bodies is not None:
                    bodies[k] = "\n".join(lines)
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
                docs.append((delim, count))
            count += 1
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


def _adapter_list(adapters):
    return list(adapters) if isinstance(adapters, (list, tuple)) else [adapters]


def union_deny_texts(adapters, root):
    """The deny-tier spellings the reach audit looks for: the **union** over ``adapters`` (one
    ExecAdapter or several) of each one's deny tier and ``engine_deny`` (REQ-662 ADR-8)."""
    texts = []
    for adapter in _adapter_list(adapters):
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


def reach(code, index, adapters, root, denies=None):
    """The static reach of a runner body (ADR-7): ``(externals, problems, functions)``.

    ``externals`` is the sorted set of external command shapes the body and every function it
    reaches can run; ``problems`` names each deny-tier spelling, code-from-data construct or
    unknown command, with the function and ``file:line``; ``functions`` is the closure. The
    audit reads what runs, command by command, never the text a command prints. Recording
    stubs prove the paths a run takes; this proves the branches (TASK-247).

    The deny tier is the union over ``adapters`` (:func:`union_deny_texts`), or ``denies``
    when the caller has computed it."""
    deny_texts = denies if denies is not None else union_deny_texts(adapters, root)
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
            if shape == "git push" and push_kind(words, func) is None:
                problems.append("%s: pushes: a runner fence pushes only an id reservation, or "
                                "the branch as exactly `%s` (BR-2): %s"
                                % (label, PUSH_REACH[BRANCH_PUSH]["spelling"],
                                   _command_text(words)[:100]))
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


def _branch_push(argv):
    """Whether a recorded argv is the :data:`BRANCH_PUSH` kind as it runs: exactly
    ``git -C <absolute path> push -u origin <branch>``, the branch matching its pattern."""
    args = list(argv)
    return (len(args) == 7 and args[:2] == ["git", "-C"] and args[2].startswith("/")
            and args[3:6] == ["push", "-u", "origin"]
            and PLACEHOLDERS["branch"].check(args[6]) is None)


def push_problems(argvs):
    """Why each recorded ``git push`` is neither push BR-2 (as amended) lets a runner fence
    make: the id reservation (non-force, ``<oid>:refs/adlc/ids/<kind>/<n>``, moving no branch,
    ADR-7) or the exact branch push (REQ-662 ADR-9). Empty when every push is one of them."""
    problems = []
    for argv in argvs:
        if _branch_push(argv):
            continue
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


def _refused(policy, code):
    """``[statement, why]`` for the first statement not run as written, for BR-8's message."""
    if policy is not None:
        return list(em.explain(policy, code) or ())
    found = em.statements(code)
    return [found[0].text, NO_MATCHER] if found else []


def _route(fence, policy, index, root, denies):
    """One fence's record. ``policy`` is ``None`` on an adapter whose matching nothing models,
    and then no fence is ``direct``; ``denies`` is the union deny tier the reach audit reads."""
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
    if policy is not None and (em.admits(policy, code) or _direct_with_samples(code, policy)):
        rec["route"] = "direct"
        return rec
    try:
        found, sources = plan(code, fence.id)
    except Unroutable as exc:
        rec["route"], rec["reason"] = "unrouted", str(exc)
        rec["refused"] = _refused(policy, code)
        return rec
    # A tied fence's reach includes the runner's own PR read (REQ-719 BR-12, LESSON-845).
    body = reach_text(code, found)
    externals, problems, funcs = reach(body, index, (), root, denies)
    if problems:
        rec["route"] = "unrouted"
        rec["reason"] = "reach: " + "; ".join(problems[:3])
        rec["refused"] = _refused(policy, code)
        rec["problems"] = problems
        return rec
    rec["route"] = "runner"
    rec["placeholders"] = sorted(dict.fromkeys(ph.arg for ph in found))
    tied = tied_args(found)
    if tied:
        rec["tied"] = tied
    if fence.id in DECLARED_UNTIED:
        rec["untied"] = DECLARED_UNTIED[fence.id]
    rec["sources"] = sources
    rec["reach"] = externals
    rec["functions"] = funcs
    kinds = [push_kind(_unwrap(words) or [], None) for words in simple_commands(body)]
    if BRANCH_PUSH in kinds:
        rec["push"] = BRANCH_PUSH
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
    """Every fence of every exec file, routed for ``adapter``, in file and fence order.

    ``adapter`` is an exec-capable ``ExecAdapter``. The reach audit reads the union of its deny
    tier and every exec-capable adapter's under ``root`` (REQ-662 ADR-8). With no adapter, the
    result is :func:`merge` over every exec-capable adapter under ``root``: what ``fence-run``
    accepts and ``show`` prints, whichever harness calls. There is no harness default."""
    if adapter is None:
        return merge([_census_one(root, a) for a in exec_adapters(root)])
    return _census_one(root, adapter)


def _census_one(root, adapter):
    policy = exec_policy(root, adapter) if routes_direct(adapter) else None
    denies = union_deny_texts(exec_adapters(root) + [adapter], root)
    index = function_index(root)
    records = []
    for rel in EXEC_FILES:
        for fence in fences(view(root, rel), rel):
            records.append(_route(fence, policy, index, root, denies))
    return records


def merge(censuses):
    """One record per fence from several adapters' censuses (REQ-662 ADR-8): the first
    ``runner`` record when any adapter routes the fence ``runner``, because ``fence-run`` accepts
    it whichever harness calls; else the first ``direct`` one; else the first adapter's. Only
    ``direct`` differs between adapters, since the reach audit reads one union deny tier."""
    if not censuses:
        raise CensusError("no census to merge")
    by_id = [dict((r["id"], r) for r in records) for records in censuses]
    out = []
    for rec in censuses[0]:
        recs = [b[rec["id"]] for b in by_id if rec["id"] in b]
        out.append(next((r for r in recs if r["route"] == "runner"), None) or
                   next((r for r in recs if r["route"] == "direct"), None) or rec)
    return out


def unrouted(records):
    return [r for r in records if r["route"] == "unrouted"]


def golden_doc(records):
    """The committed golden: every id with its route, placeholders and reach."""
    keep = ("id", "route", "reason", "placeholders", "tied", "untied", "sources", "reach", "push")
    return {"comment": "REQ-682 exec fence census. Regenerate with "
                       "`python3 tools/adlc/fence_census.py --write`; a diff here is a fence "
                       "whose route, values or reach changed.",
            "fences": [{k: r[k] for k in keep if r.get(k) not in (None, "", [])}
                       for r in records]}


#: Each adapter's golden sits beside its renders, never under ``rendered/``, which
#: ``render-parity`` walks.
GOLDEN_NAME = "exec-fence-census.json"


def golden_path(name):
    """The toolkit-relative golden of the adapter named ``name``."""
    return os.path.join("harness", name, GOLDEN_NAME)


def dumps(doc):
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def goldens(root):
    """``[(adapter, rel, text, unrouted records)]`` for every exec-capable adapter."""
    out = []
    for adapter in exec_adapters(root):
        records = census(root, adapter)
        out.append((adapter, golden_path(adapter.name), dumps(golden_doc(records)),
                    unrouted(records)))
    return out


def stale_goldens(root, fresh=None):
    """Each golden under ``root`` that is not its adapter's fresh census, with why: missing,
    stale, or naming no exec-capable adapter. Empty when every golden is fresh."""
    fresh = goldens(root) if fresh is None else fresh
    problems = []
    for _adapter, rel, text, _bad in fresh:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            problems.append("%s is missing" % rel)
            continue
        if current != text:
            problems.append("%s is stale" % rel)
    names = set(a.name for a, _rel, _text, _bad in fresh)
    hdir = os.path.join(root, "harness")
    for name in sorted(os.listdir(hdir)):
        if os.path.isfile(os.path.join(hdir, name, GOLDEN_NAME)) and name not in names:
            problems.append("%s names no exec-capable adapter" % golden_path(name))
    return problems


def write_goldens(root, fresh=None):
    """Write every exec-capable adapter's golden; returns the paths written."""
    fresh = goldens(root) if fresh is None else fresh
    for _adapter, rel, text, _bad in fresh:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return [rel for _a, rel, _t, _b in fresh]


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="fence_census.py", description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true",
                       help="rewrite every exec-capable adapter's committed golden")
    group.add_argument("--check", action="store_true",
                       help="fail when any adapter's golden is missing or stale")
    args = parser.parse_args(argv)
    root = tkr.toolkit_root()
    try:
        fresh = goldens(root)
    except CensusError as exc:
        sys.stderr.write("fence_census: %s\n" % exc)
        return 1
    bad = False
    for adapter, _rel, _text, records in fresh:
        for rec in records:
            sys.stderr.write("unrouted: %s: %s: %s\n" % (adapter.name, rec["id"], rec["reason"]))
            bad = True
    if args.write:
        write_goldens(root, fresh)
        return 1 if bad else 0
    if args.check:
        problems = stale_goldens(root, fresh)
        for problem in problems:
            sys.stderr.write("fence_census: %s; run fence_census.py --write\n" % problem)
        return 1 if bad or problems else 0
    for adapter in exec_adapters(root):
        for rec in census(root, adapter):
            sys.stdout.write("%-9s %-8s %s %s\n" % (rec["route"], adapter.name, rec["id"],
                                                     rec["reason"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
