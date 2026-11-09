#!/usr/bin/env python3
"""exec_matcher — how the installed ``claude`` judges a Bash command at exec scope (REQ-682).

The model of Claude's matching is pinned to what was measured, not to the documentation:
the probe table in ``.adlc/specs/REQ-682-exec-fences-run-without-widening/architecture.md``
("Evidence first"), run against ``claude`` 2.1.316 under BUG-260's isolation flags. Each row
is a fixture in ``tests/test_exec_matcher.py``.

- A compound command is judged one statement at a time (rows 2, 3, 8): ``;``, ``&&``,
  ``||``, ``|``, ``&`` and a newline split it, and the condition and body of an
  ``if … then … else … fi`` are statements of their own.
- A quoted ``;`` does not split, and an allow matches the raw, quoted text (row 6).
- ``.`` and ``source`` are refused even under a matching allow (rows 9, 10), and so are a
  nested command (``$(…)`` or a backtick, row 5), a redirection other than to
  ``/dev/null`` (row 7) and an env prefix (rows 4, 13, 14).
- A prefix rule ``Bash(X:*)`` admits ``X`` and ``X <anything>``, never ``X-more`` (row 12).
- A deny matches through an env prefix (row 15).

Where the evidence is silent (a here-document, a subshell, a loop, a comment, a variable
expansion) the statement's refusal is ``unmeasured``, so :func:`admits` is conservative and
never says yes on a guess (LESSON-716). :func:`deny_hits` leans the other way: it strips env
prefixes and ``git -C <path>`` before it compares a statement with the deny rules, so a deny
is found in every wrapped form BR-2 names.

Rows 16-18 are Claude's path checks (a path outside the working directories, a ``..``), not
statement matching: this module does not model them, and BUG-265's live rows pin them.

The per-statement prefix test is ``harness_render.allow_matches``, so there is one prefix
rule in the toolkit, not two. Standard library only.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_adapter as ha  # noqa: E402
import harness_render as hr  # noqa: E402

_RULE_RE = re.compile(r"^Bash\((.*)\)$", re.S)
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_DEVNULL_REDIRECT = re.compile(r"^(?:[0-9]?>>?|&>)/dev/null$")
_REDIRECT_OPS = (">", ">>", "1>", "2>", "1>>", "2>>", "&>")
#: The ``if`` grammar the probes measured (row 8); every other compound keyword is unmeasured.
_IF_WORDS = ("if", "then", "else", "elif")
_UNMEASURED_WORDS = ("for", "while", "until", "case", "esac", "do", "done", "function", "select",
                     "!", "{", "}", "[[", "]]", "coproc", "time", "fi")

REFUSE_SOURCE = "'.' evaluates arguments as shell code"
REFUSE_NESTED = "a nested command can't be checked before it runs"
REFUSE_REDIRECT = "output redirection needs approval"
REFUSE_ENV = "an env-prefixed command is not admitted by a bare allow"
REFUSE_UNMEASURED = "unmeasured"
REFUSE_DENIED = "denied"
REFUSE_NO_ALLOW = "no allow matches"


class Statement(object):
    """One statement of a compound command, with what the lexer saw in it."""
    __slots__ = ("text", "flags")

    def __init__(self, text, flags):
        self.text = text
        self.flags = frozenset(flags)

    def __repr__(self):
        return "Statement(%r, %r)" % (self.text, sorted(self.flags))


def _lex(cmd):
    """Split ``cmd`` into raw statements outside quotes, recording what each one holds.

    ``flags`` names the constructs seen outside single quotes: ``nested`` (``$(`` or a
    backtick), ``var`` (a ``$`` expansion), ``redir`` (``<`` or ``>``), ``heredoc``,
    ``subshell``, ``comment`` and ``unterminated``.
    """
    out = []
    buf = []
    flags = set()
    quote = None
    i = 0
    n = len(cmd)
    word_start = True

    def flush():
        text = "".join(buf).strip()
        if text or flags:
            out.append((text, set(flags)))
        del buf[:]
        flags.clear()

    while i < n:
        c = cmd[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\":
            if cmd.startswith("\\\n", i):
                i += 2          # a line continuation joins the two lines
                continue
            buf.append(cmd[i:i + 2])
            i += 2
            word_start = False
            continue
        if quote == '"':
            buf.append(c)
            if c == '"':
                quote = None
            elif c == "`" or cmd.startswith("$(", i):
                flags.add("nested")
            elif c == "$":
                flags.add("var")
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            buf.append(c)
            i += 1
            word_start = False
            continue
        if c == "#" and word_start:
            end = cmd.find("\n", i)
            i = n if end == -1 else end
            flags.add("comment")
            continue
        if c in "\n;":
            flush()
            i += 1
            word_start = True
            continue
        if cmd.startswith("&&", i) or cmd.startswith("||", i):
            flush()
            i += 2
            word_start = True
            continue
        if c == "|":
            flush()
            i += 1
            word_start = True
            continue
        if c == "&" and not cmd.startswith("&>", i) and not (buf and buf[-1] in "<>"):
            flush()
            i += 1
            word_start = True
            continue
        if c == "`" or cmd.startswith("$(", i):
            flags.add("nested")
        elif c == "$":
            flags.add("var")
        if cmd.startswith("<<", i):
            flags.add("heredoc")
        elif c in "<>":
            flags.add("redir")
        if c in "()" or (c in "{}" and word_start):
            flags.add("subshell")
        buf.append(c)
        word_start = c in " \t"
        i += 1
    if quote is not None:
        flags.add("unterminated")
    flush()
    return out


def words(text):
    """Whitespace-separated words, with quoted spans kept whole, quotes included."""
    out = []
    cur = []
    quote = None
    for c in text:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in ("'", '"'):
            quote = c
            cur.append(c)
            continue
        if c in " \t":
            if cur:
                out.append("".join(cur))
                cur = []
            continue
        cur.append(c)
    if cur:
        out.append("".join(cur))
    return out


def statements(cmd):
    """Every statement Claude checks on its own, in order (rows 2, 3, 6, 8).

    The ``if``/``then``/``else``/``elif`` keyword is dropped from the front of its
    statement, and a bare ``fi`` is not a statement, so the condition and each body of an
    ``if`` are judged as the commands they are.
    """
    out = []
    for text, flags in _lex(cmd):
        ws = words(text)
        while ws and ws[0] in _IF_WORDS:
            ws = ws[1:]
        if ws == ["fi"] or (not ws and not flags):
            continue
        out.append(Statement(" ".join(ws), flags))
    return out


def _redirect_refusal(stmt):
    ws = words(stmt.text)
    i = 0
    while i < len(ws):
        w = ws[i]
        if w.startswith(("'", '"')):
            i += 1
            continue
        if _DEVNULL_REDIRECT.match(w):
            i += 1
            continue
        if w in _REDIRECT_OPS and i + 1 < len(ws) and ws[i + 1] == "/dev/null":
            i += 2
            continue
        if "<" in w or ">" in w:
            return REFUSE_REDIRECT
        i += 1
    return None


def refusal(stmt):
    """Why Claude refuses ``stmt`` whatever the allow list says, or ``None``."""
    if isinstance(stmt, str):
        found = statements(stmt)
        if len(found) != 1:
            return REFUSE_UNMEASURED
        stmt = found[0]
    ws = words(stmt.text)
    if ws and ws[0] in (".", "source"):
        return REFUSE_SOURCE
    if "nested" in stmt.flags:
        return REFUSE_NESTED
    if ws and _ENV_RE.match(ws[0]):
        return REFUSE_ENV
    if "heredoc" in stmt.flags:
        return REFUSE_UNMEASURED
    if "redir" in stmt.flags:
        why = _redirect_refusal(stmt)
        if why:
            return why
    if stmt.flags & {"var", "subshell", "comment", "unterminated"}:
        return REFUSE_UNMEASURED
    if not ws or ws[0] in _UNMEASURED_WORDS:
        return REFUSE_UNMEASURED
    return None


class Rule(object):
    """One ``Bash(...)`` rule: a prefix rule ``Bash(X:*)`` or an exact ``Bash(X)``.

    A ``*`` inside the text is Claude's wildcard (``Bash(git -C * push --force:*)``)."""
    __slots__ = ("raw", "text", "prefix", "_rx")

    def __init__(self, raw):
        match = _RULE_RE.match(raw)
        if not match:
            raise ValueError("not a Bash rule: %r" % raw)
        body = match.group(1)
        self.raw = raw
        self.prefix = body.endswith(":*")
        self.text = body[:-2] if self.prefix else body
        self._rx = None
        if "*" in self.text:
            pattern = ".*".join(re.escape(p) for p in self.text.split("*"))
            self._rx = re.compile("^%s%s$" % (pattern, r"(?:\s.*)?" if self.prefix else ""),
                                  re.S)

    def matches(self, text):
        """Whether this rule matches one statement's raw text."""
        if self._rx is not None:
            return bool(self._rx.match(text))
        return hr.allow_matches(tuple(self.text.split(" ")), not self.prefix, "prefix",
                                tuple(text.split(" ")), True)

    @property
    def first_token(self):
        ws = self.text.split(" ")
        return ws[0] if ws else ""


def bash_rules(rules):
    """The ``Bash(...)`` rules of a rendered tier; other tools' rules are skipped."""
    out = []
    for raw in rules:
        if isinstance(raw, Rule):
            out.append(raw)
        elif isinstance(raw, str) and _RULE_RE.match(raw):
            out.append(Rule(raw))
    return out


class Policy(object):
    """The rendered ExecPolicy: the allow and deny tiers the harness enforces."""

    def __init__(self, allow=(), deny=()):
        self.allow = bash_rules(allow)
        self.deny = bash_rules(deny)

    @classmethod
    def of(cls, policy):
        if isinstance(policy, Policy):
            return policy
        if isinstance(policy, dict):
            return cls(policy.get("allow", ()), policy.get("deny", ()))
        allow, deny = policy
        return cls(allow, deny)


def _deny_views(text):
    """The spellings a deny is compared with: as written, without its env prefixes, and
    without ``git -C <path>``, whitespace collapsed (row 15; BR-2's wrapped forms)."""
    ws = words(text)
    views = [list(ws)]
    stripped = list(ws)
    while stripped and _ENV_RE.match(stripped[0]):
        stripped.pop(0)
    views.append(stripped)
    for base in list(views):
        if len(base) >= 3 and base[0] == "git" and base[1] == "-C":
            views.append(["git"] + base[3:])
    return list(dict.fromkeys(" ".join(v) for v in views if v))


def _denied(policy, text):
    return [rule.raw for view in _deny_views(text) for rule in policy.deny if rule.matches(view)]


def deny_hits(policy, cmd):
    """Every ``(statement, deny rule)`` where a deny of ``policy`` matches ``cmd``.

    Each statement is compared as written, with its env prefixes stripped and with
    ``git -C <path>`` stripped, so a deny is found in every wrapped form BR-2 names.
    """
    policy = Policy.of(policy)
    hits = []
    for stmt in statements(cmd):
        for raw in _denied(policy, stmt.text):
            hits.append((stmt.text, raw))
    return list(dict.fromkeys(hits))


def explain(policy, cmd):
    """``None`` when ``policy`` admits ``cmd``; else ``(statement, reason)`` for the first
    statement it does not admit."""
    policy = Policy.of(policy)
    found = statements(cmd)
    if not found:
        return (cmd.strip(), REFUSE_UNMEASURED)
    for stmt in found:
        why = refusal(stmt)
        if why:
            return (stmt.text, why)
        if _denied(policy, stmt.text):
            return (stmt.text, REFUSE_DENIED)
        if not any(rule.matches(stmt.text) for rule in policy.allow):
            return (stmt.text, REFUSE_NO_ALLOW)
    return None


def admits(policy, cmd):
    """Whether ``policy`` admits every statement of ``cmd``, as Claude was measured to."""
    return explain(policy, cmd) is None


def opener_allows(policy):
    """Allow rules that open every line or run their arguments: a first-token wildcard, an
    opener (``if``, ``sh``, ``.``, ``source``, ``eval``, ``python*``, …) (BR-7)."""
    policy = Policy.of(policy)
    bad = []
    for rule in policy.allow:
        first = rule.first_token
        if not rule.text.strip() or first == "*" or first in ha.FORBIDDEN_FIRST_TOKENS or \
                first.startswith(ha.FORBIDDEN_FIRST_TOKEN_PREFIXES):
            bad.append(rule.raw)
    return bad


#: The admitted statement a compound form puts in front of a deny.
SAMPLE_ALLOWED = " ".join(hr.COMPOUND_HEAD)


def wrapped_forms(command):
    """``(shape, text)`` for every BR-2 form of deny-tier ``command``: as written, behind an
    arbitrary env prefix, under ``git -C <path>``, after an admitted statement (``;``,
    ``&&``, ``||``, a newline) and inside an ``if``. ``harness_render.deny_forms`` holds the
    token forms, so the render and this module test one set."""
    ws = tuple(command) if not isinstance(command, str) else tuple(command.split(" "))
    text = " ".join(ws)
    forms = [(shape, " ".join(form)) for shape, form in hr.deny_forms(ws, wrapped=True)]
    forms += [("compound-tail", "%s\n%s" % (SAMPLE_ALLOWED, text)),
              ("compound-tail", "if [ -d . ]; then %s; fi" % text)]
    if ws and ws[0] == "git":
        forms.append(("git-c", " ".join(("git", "-C", "/tmp/wc") + ws[1:])))
    return forms


def policy_problems(policy, deny_spellings):
    """What makes ``policy`` wider than Rule B allows: an opener allow, or a deny-tier
    spelling admitted in any wrapped form. Empty when the policy is sound (AC-3)."""
    policy = Policy.of(policy)
    problems = ["opener allow %s runs its arguments (BR-7)" % raw
                for raw in opener_allows(policy)]
    for spelling in deny_spellings:
        for shape, form in wrapped_forms(spelling):
            if admits(policy, form):
                problems.append("deny-tier `%s` admitted as %s: %r"
                                % (spelling if isinstance(spelling, str) else " ".join(spelling),
                                   shape, form))
    return problems


def _concrete(spelling):
    """A deny spelling with each ``*`` wildcard filled in, so it is a command to test."""
    out = []
    for tok in spelling:
        if tok == "*":
            out.append("/tmp/wc")
        elif tok.endswith("*"):
            out.append(tok[:-1] + "HEAD:main")
        else:
            out.append(tok)
    return tuple(out)


#: The one-way moves BR-2 names that no deny entry spells: a push of anything but the run's
#: own branch, and the BR-24 tokens that are commands.
EXTRA_DENY_TIER = (("git", "push", "origin", "main"), ("git", "push", "origin", "HEAD:main"),
                   ("git", "push", "origin", "+HEAD:feat/x"), ("git", "push", "--mirror"),
                   ("git", "push", "origin", "--delete", "feat/x"),
                   ("adlc_forge_pr_merge",), ("adlc_forge_pr_merge", "1", "--squash"),
                   ("gh", "pr", "merge", "1"), ("az", "repos", "pr", "update"))


def deny_tier_spellings(adapter, toolkit):
    """Every BR-2 deny-tier spelling, concrete: ``templates/permissions.yml``'s deny tier,
    the adapter's ``engine_deny``, and the BR-24 command tokens plus the other pushes."""
    perms = ha.load_permissions(ha.permissions_path(toolkit))
    out = [tuple(c) for e in perms["entries"] if e["tier"] == "deny" for c in e["commands"]]
    out += [tuple(c) for c in (adapter.get("exec") or {}).get("engine_deny", [])]
    out += list(EXTRA_DENY_TIER)
    return list(dict.fromkeys(_concrete(s) for s in out))
