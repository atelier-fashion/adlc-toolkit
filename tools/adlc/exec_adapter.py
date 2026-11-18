#!/usr/bin/env python3
"""exec_adapter — the engine's view of a harness's ``exec`` block (REQ-659).

Everything harness-specific about a headless launch is data in ``harness/<name>.yml``;
this module turns that data into an argv, a child environment, an exit class and a
parsed result. No code here names a harness (conventions.md "Harness adapters are
data"). Standard library only.
"""

import json
import os
import re
from collections import namedtuple

import exec_matcher as em
import harness_adapter as ha
import harness_render as hr

#: The requirement that gives the non-Claude harnesses their exec blocks, one harness per
#: stage (REQ-662 Amendments, 2026-11-17). A refusal of a harness with no block names it.
EXEC_ADAPTERS_REQ = "REQ-662"
#: Refused at launch whatever an adapter says (BR-8).
ENGINE_FORBIDDEN_FLAGS = ha.ENGINE_FORBIDDEN_FLAGS

_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CLAIM_RE = re.compile(r"^Terminal state: ([a-z_-]+)\s*$")
_EXTRA_RE = re.compile(r"^[A-Za-z0-9_./=+:@%,*-]+$")
#: The fence runner's resolved path: one a prefix rule matches unquoted (probe row 6), so no
#: space, quote or glob, and never a relative one (REQ-682 ADR-8). The renderer holds the same.
_RUNNER_PATH_RE = hr.RUNNER_PATH_RE
#: A file root becomes a gitignore-style pattern, so it may hold no glob, quote, space or
#: empty, `.` or `..` segment: any of those would widen the rule (BUG-265).
_ROOT_RE = re.compile(r"^(/[A-Za-z0-9_.-]+)+$")
#: The placeholders a ``launch``, ``resume`` or ``config_isolation`` template may hold. Each is
#: substituted as one whole token, never inside a longer one and never by a shell (REQ-662 BR-2).
PLACEHOLDERS = ("worktree", "last_message", "session_id", "settings", "branch")
#: Placeholders whose value is a path, and so must be absolute: a relative one would resolve
#: against whatever directory the harness runs in.
_PATH_VALUES = ("worktree", "last_message", "settings", "add_dir")
#: Anything spelled like a placeholder, so one inside a longer token is found and refused.
_BRACED_RE = re.compile(r"\{[A-Za-z0-9_]+\}")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
#: What a launch may add after its template, in this order and nothing else (REQ-662 ADR-7):
#: the operator's --harness-flag tokens, the isolation tokens, the --add-dir pair and the
#: renderer's allow and deny pairs.
ADDITIONS = ("operator", "isolation", "add_dir", "allow", "deny")


#: Programs whose first argument names a subcommand: their command base is two tokens.
_SUBCOMMAND_PROGRAMS = ("git", "gh", "az", "adlc", "terraform", "gcloud", "npm", "docker",
                        "kubectl")


#: The local destructive moves REQ-662 BR-4 names. A ``deny_unsupported`` entry holding one
#: refuses the run whatever protects the branch: a forge's protection does not reach a local
#: working copy. A one-letter flag is matched inside a cluster too (``-fd`` holds ``-f``).
LOCAL_DESTRUCTIVE = (("reset", "--hard"), ("clean", "-f"), ("branch", "-D"), ("rm",),
                     ("release",))

#: One deny-tier or ``engine_deny`` command the run has no deny for (REQ-662 BR-4): its entry
#: id, its command text, why, and whether it is a local destructive move.
DenyUnsupported = namedtuple("DenyUnsupported", "entry command reason destructive")


def _token_is(token, want):
    if len(want) == 2 and want[0] == "-" and want[1] != "-":
        return len(token) > 1 and token[0] == "-" and token[1] != "-" and want[1] in token[1:]
    return token == want


def local_destructive(argv):
    """Whether ``argv`` holds one of :data:`LOCAL_DESTRUCTIVE` as a run of whole tokens."""
    argv = [str(t) for t in argv]
    for move in LOCAL_DESTRUCTIVE:
        for i in range(len(argv) - len(move) + 1):
            if all(_token_is(argv[i + k], want) for k, want in enumerate(move)):
                return True
    return False


class ExecReport(object):
    """What the pre-flight reads from one exec-scope render (REQ-662 BR-3, BR-4).

    ``findings`` are the render's; ``report`` is the ``allowlist-fidelity`` report the run log
    carries; ``undeclared`` the findings ``accepted_fidelity`` does not declare at ``exec``;
    ``deny_unsupported`` a :data:`DenyUnsupported` per command the run has no deny for; and
    ``whole_tier`` the reason the whole deny tier is in it, or None."""
    __slots__ = ("findings", "report", "undeclared", "deny_unsupported", "whole_tier")

    def __init__(self, findings, report, undeclared, deny_unsupported, whole_tier):
        self.findings = findings
        self.report = report
        self.undeclared = undeclared
        self.deny_unsupported = deny_unsupported
        self.whole_tier = whole_tier


def _command_base(spelling):
    """The tokens a deny shares with any command of the same kind: `git push` for
    `git push --force`, `git -C` for `git -C * push -f`, `rm` for `rm -rf` (BUG-260)."""
    spelling = tuple(spelling)
    if len(spelling) > 1 and spelling[0] in _SUBCOMMAND_PROGRAMS:
        return spelling[:2]
    return spelling[:1]


class ExecRefused(ValueError):
    """A pre-flight refusal: nothing is launched."""


def _flatten_flag(token):
    return token.split("=", 1)[0] if token.startswith("-") else token


def forbidden_in(argv, forbidden):
    """The first forbidden spelling in ``argv``, or None.

    Compared token by token, so a rule element that merely contains ``--force``
    (``Bash(git push --force:*)``) is not a flag. ``--flag=value`` is split first, and
    a two-word entry matches two adjacent tokens.
    """
    tokens = []
    for tok in argv:
        tokens.append(_flatten_flag(tok))
        if tok.startswith("-") and "=" in tok:
            tokens.append(tok.split("=", 1)[1])
    for bad in forbidden:
        parts = bad.split()
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i:i + len(parts)] == parts:
                return bad
    return None


def refuse_forbidden(argv, forbidden):
    bad = forbidden_in(argv, forbidden)
    if bad:
        raise ExecRefused("%s is a forbidden flag: Rule B keeps one-way moves with the "
                          "orchestrator, so nothing is launched" % bad)


def _placeholder(token):
    """The placeholder ``token`` is, by name, or None for a literal token. A placeholder inside
    a longer token, or one the engine does not fill, refuses the launch (REQ-662 BR-2)."""
    found = _BRACED_RE.findall(token)
    if not found:
        return None
    if found != [token]:
        raise ExecRefused("template token %r holds a placeholder inside a longer token: a "
                          "placeholder is substituted only as a whole token (REQ-662 BR-2), so "
                          "nothing is launched" % token)
    name = token[1:-1]
    if name not in PLACEHOLDERS:
        raise ExecRefused("template token %s is not a placeholder the engine fills (%s), so "
                          "nothing is launched" % (token, ", ".join("{%s}" % p
                                                                     for p in PLACEHOLDERS)))
    return name


def _vet_value(name, value):
    """``value`` as the argv token for ``{name}``: one that can only be read as that value."""
    if not isinstance(value, str) or not value or value.startswith("-") or \
            _CONTROL_RE.search(value):
        raise ExecRefused("{%s} would be %r: an empty value, a control character or a leading "
                          "`-` would not read as one argument, so nothing is launched"
                          % (name, value))
    if name in _PATH_VALUES and not os.path.isabs(value):
        raise ExecRefused("{%s} would be %r, which is not an absolute path, so nothing is "
                          "launched" % (name, value))
    if name == "session_id" and not _SESSION_RE.match(value):
        raise ExecRefused("{session_id} would be %r, which is not a session id, so nothing is "
                          "launched" % (value,))
    return value


def substitute(template, values, partial=False):
    """``template`` with each placeholder replaced by its value in ``values`` (by name), as one
    whole token and never by a shell (REQ-662 BR-2). A value is never read for placeholders in
    turn. A placeholder with no value refuses, unless ``partial`` leaves it in place."""
    out = []
    for token in template:
        name = _placeholder(token)
        if name is None:
            out.append(token)
        elif values.get(name) is not None:
            out.append(_vet_value(name, values[name]))
        elif partial:
            out.append(token)
        else:
            raise ExecRefused("%s has no value at this launch, so the template cannot be "
                              "filled: nothing is launched" % token)
    return out


def _rules(kind, rules):
    """The renderer's ``kind`` rules, each one argument that cannot be read as a flag."""
    rules = list(rules)
    for rule in rules:
        if not isinstance(rule, str) or not rule or rule.startswith("-") or \
                _CONTROL_RE.search(rule):
            raise ExecRefused("closed world: %s rule %r is not one rule argument, so nothing is "
                              "launched (REQ-662 BR-16)" % (kind, rule))
    return rules


def _first_difference(argv, expected):
    for i, (got, want) in enumerate(zip(argv, expected)):
        if got != want:
            return "argv token %d is %r where the template allows %r" % (i, got, want)
    if len(argv) > len(expected):
        return "argv token %d, %r, is past everything the template allows" % (
            len(expected), argv[len(expected)])
    return "the argv stops at token %d where the template goes on with %r" % (
        len(argv), expected[len(argv)])


class ExecAdapter(object):
    """One harness's ``exec`` block, loaded and validated."""

    def __init__(self, adapter, toolkit=None):
        self.adapter = adapter
        self.toolkit = toolkit
        self.block = adapter.get("exec") or {}
        self.name = adapter["name"]
        self.binary = adapter["binary"]

    @property
    def strategy(self):
        return self.block["working_copy"]["strategy"]

    @property
    def output(self):
        """Where the harness's output holds each result field (REQ-662 ADR-6)."""
        return self.block["output"]

    def template(self, name):
        """The ``launch`` or ``resume`` template: the whole argv after the binary, placeholders
        unfilled. An adapter with no ``resume`` cannot be resumed (REQ-659 BR-7)."""
        if name not in ("launch", "resume"):
            raise ExecRefused("%r is not a launch template" % (name,))
        tokens = self.block.get(name)
        if not tokens:
            raise ExecRefused("harness %s declares no %s, so %s is impossible on it"
                              % (self.name, name, name))
        return list(tokens)

    def resume_tokens(self, session_id):
        """The ``resume`` template with ``{session_id}`` substituted as one whole token
        (REQ-662 BR-2). Any other placeholder is left for :meth:`launch_argv` to fill."""
        return substitute(self.template("resume"), {"session_id": session_id}, partial=True)

    def check_templates(self):
        """Refuse a template no launch could fill (REQ-662 BR-2): a placeholder inside a longer
        token, one the engine does not fill, or ``{session_id}`` outside ``resume``."""
        for key in ("launch", "resume", "config_isolation"):
            for token in self.block.get(key) or []:
                if _placeholder(token) == "session_id" and key != "resume":
                    raise ExecRefused("exec.%s holds {session_id}, and only a resume has one: "
                                      "nothing is launched" % key)

    def operator_tokens(self, tokens):
        """The operator's --harness-flag tokens, each flag one ``exec.operator_flags`` names and
        each other token the value of the flag before it (REQ-662 ADR-7). Anything else refuses
        the launch: forbidding one flag at a time never converges (LESSON-663).

        A flag takes its value as the next token or after ``=``. A flag whose value is still
        owed when the tokens end, or a value that begins with ``-``, refuses: the engine's own
        tokens follow the operator's, so the harness would read one of them, or a flag, as that
        value."""
        declared = list(self.block.get("operator_flags") or [])
        out = []
        owed = None
        for token in tokens:
            token = str(token)
            if _CONTROL_RE.search(token):
                raise ExecRefused("--harness-flag %r holds a control character, so nothing is "
                                  "launched" % token)
            if owed is not None:
                if token.startswith("-"):
                    raise ExecRefused("--harness-flag %s takes a value, and %r begins with `-`, "
                                      "so it would read as a flag: nothing is launched"
                                      % (owed, token))
                owed = None
            elif token.startswith("-"):
                name, eq, value = token.partition("=")
                if name not in declared:
                    raise ExecRefused("--harness-flag %s is not in harness %s's operator_flags "
                                      "(%s), so nothing is launched (REQ-662 BR-16)"
                                      % (token, self.name, ", ".join(declared) or "none"))
                if eq and value.startswith("-"):
                    raise ExecRefused("--harness-flag %s takes a value, and %r begins with `-`, "
                                      "so it would read as a flag: nothing is launched"
                                      % (name, value))
                owed = None if eq else name
            else:
                raise ExecRefused("--harness-flag %r is neither an operator flag nor the value of "
                                  "the one before it, so nothing is launched" % token)
            out.append(token)
        if owed is not None:
            raise ExecRefused("--harness-flag %s ends the operator's flags with its value still "
                              "owed, so the harness would read the engine's next token as that "
                              "value: nothing is launched" % owed)
        return out

    @property
    def trust_grant(self):
        return self.block["trust_grant"]

    @property
    def can_resume(self):
        """Whether the adapter declares a ``resume`` template. Without one, resume is impossible
        (REQ-659 BR-7, REQ-662 BR-7)."""
        return bool(self.block.get("resume"))

    @property
    def can_add_dir(self):
        """Whether the adapter declares an ``add_dir_flag``: a second writable directory beside
        the working copy. Without one a session writes its working copy alone, so the
        close-out's state file travels through it and a multi-repo run is refused (REQ-662
        ADR-7)."""
        return bool(self.block.get("add_dir_flag"))

    @property
    def forbidden(self):
        return list(dict.fromkeys(list(ENGINE_FORBIDDEN_FLAGS)
                                  + list(self.block.get("forbidden_flags", []))))

    @property
    def can_deny(self):
        return self.adapter["capabilities"].get("deny") == "yes"

    @property
    def delegate_supported(self):
        """Whether a delegated ``adlc-read`` fits in one shell call (REQ-662 BR-10). Anything
        but a declared ``supported`` reads as unsupported."""
        return (self.block.get("shell_timeout_s") or {}).get("delegate") == "supported"

    def spell(self, argv, exact=False, deny=False):
        text = " ".join(argv)
        if text.endswith("*"):
            # A token that ends in `*` is its own wildcard; `:*` after it would not parse.
            return self.block["shell_rule_exact"] % text
        if deny and "*" in text:
            # BUG-269: claude 2.1.316 matches no rule that holds a `*` and ends in `:*`, so
            # `Bash(git -C * push --force:*)` let the push run. A glob deny ends in a `*` of
            # its own, which matches the bare command and any arguments after it. Only a
            # deny: the same spelling on an allow would admit `--forcefoo` as well.
            return self.block["shell_rule_exact"] % (text + "*")
        template = self.block["shell_rule_exact"] if exact else self.block["shell_rule"]
        return template % text

    @property
    def has_matcher(self):
        """Whether ``exec_matcher`` models this harness's rule matching. The census asks the
        same question to decide whether a fence may route ``direct``, so this is its answer,
        ``fence_census.routes_direct``, and the two cannot drift apart when a stage adds a
        ``matcher`` value. On ``matcher: none`` nothing models it (REQ-662 ADR-8)."""
        import fence_census as fc
        return fc.routes_direct(self)

    def vet_extra(self, argv, entries, exact=False):
        """Refuse an extra allow that is a wildcard, an opener or wraps a deny (ADR-6).

        A deny is looked for in every form REQ-682 BR-2 names, through ``exec_matcher``,
        which judges a compound command one statement at a time as Claude does. On
        ``matcher: none`` nothing models how the harness matches a rule, so no extra allow can
        be vetted, and every one is refused (REQ-662 ADR-8).
        """
        if not self.has_matcher:
            raise ExecRefused("allow entry %r: harness %s declares matcher: none, so nothing "
                              "can vet an extra allow against the deny tier; allow_extra and "
                              "allow_extra_exact must be empty on it (REQ-662 ADR-8)"
                              % (" ".join(argv), self.name))
        gran = self.adapter["capabilities"]["allowlist_granularity"]
        for token in argv:
            if not _EXTRA_RE.match(token):
                raise ExecRefused("allow entry %r holds a token the engine will not spell: %r"
                                  % (" ".join(argv), token))
        if hr.forbidden_first_token(argv):
            raise ExecRefused("allow entry %r starts with a token that %s"
                              % (" ".join(argv), ha.first_token_problem(argv[0])))
        policy = em.Policy([self.spell(list(argv), exact)])
        for entry in entries:
            if entry["kind"] != "deny":
                continue
            for _shape, form in hr.deny_forms(entry["spelling"]):
                if hr.allow_matches(argv, exact, gran, form, exact):
                    raise ExecRefused("allow entry %r would wrap deny-tier `%s`"
                                      % (" ".join(argv), " ".join(form)))
            for shape, text in em.wrapped_forms(em._concrete(entry["spelling"])):
                if em.admits(policy, text):
                    raise ExecRefused("allow entry %r would wrap deny-tier `%s` (%s)"
                                      % (" ".join(argv), text, shape))
            # A prefix rule admits any tokens after it, so one that shares a command base
            # with a deny admits that deny's flags at a later position: `git push -u origin
            # <branch>:*` let `<branch> --force` and `<branch> main` through (BUG-260).
            base = _command_base(entry["spelling"])
            if not exact and tuple(argv[:len(base)]) == base:
                raise ExecRefused("allow entry %r shares the command base `%s` with deny-tier "
                                  "`%s`; list it as an exact entry instead"
                                  % (" ".join(argv), " ".join(base),
                                     " ".join(entry["spelling"])))

    def file_rules(self, write_roots=(), read_roots=()):
        """The file-tool rules, one set per root: never a bare file tool (BUG-265)."""
        rules = self.block.get("file_rules", {})
        out = []
        for kind, roots in (("write", write_roots), ("read", read_roots)):
            for given in roots:
                # Claude matches a file rule against the path as written, so a root reached
                # through a symlink (macOS's /var is /private/var) gets both spellings: they
                # name one directory, so neither widens the other.
                for root in dict.fromkeys([given, os.path.realpath(given or "x")]):
                    if (not _ROOT_RE.match(given or "") or not _ROOT_RE.match(root)
                            or "/../" in root + "/" or "/./" in root + "/"):
                        raise ExecRefused("file root %r is not a plain absolute path; it would "
                                          "widen a file rule" % (given,))
                    out += [rule.replace("{root}", root) for rule in rules.get(kind, [])]
        return list(dict.fromkeys(out))

    def fence_runner(self):
        """The fence runner's absolute path, resolved once from ToolkitRoot and vetted, or
        ``None`` when the adapter names none (REQ-682 ADR-8). A path that is not absolute,
        holds a character an unquoted prefix rule cannot match, is not a regular file, or
        leaves the root after ``realpath`` refuses the launch."""
        rel = self.block.get("fence_runner")
        if not rel:
            return None
        import toolkit_root
        root = os.path.realpath(self.toolkit or toolkit_root.toolkit_root())
        path = os.path.join(root, rel)
        real = os.path.realpath(path)
        if (not _RUNNER_PATH_RE.match(path) or "/../" in path + "/" or "/./" in path + "/"
                or not os.path.isfile(path) or os.path.islink(path)
                or os.path.commonpath([real, root]) != root):
            raise ExecRefused("fence runner %r is not a regular file under the toolkit root at "
                              "a path a prefix rule can match: nothing is launched" % path)
        return path

    def _render(self, result):
        """The exec-scope render's entries and findings, with the probe result ``result``
        (REQ-662 ADR-3). A render the probe forbids refuses the launch."""
        try:
            return hr.exec_entries(self.adapter, self.toolkit, result)
        except hr.RenderError as exc:
            raise ExecRefused(str(exc))

    def _extras(self, branch, config_extra, entries):
        """Every extra allow as ``(argv, exact)``, each vetted against the deny tier: the
        adapter's ``allow_extra`` and ``allow_extra_exact``, then the project's."""
        out = []
        for key, exact in (("allow_extra", False), ("allow_extra_exact", True)):
            for argv in self.block.get(key, []):
                spelled = [t.replace("{branch}", branch) for t in argv]
                self.vet_extra(spelled, entries, exact=exact)
                out.append((spelled, exact))
        for argv in config_extra:
            self.vet_extra(list(argv), entries)
            out.append((list(argv), False))
        return out

    def _runner(self, entries):
        runner = self.fence_runner()
        if runner and self.has_matcher:
            # On matcher: none nothing can vet the runner allow further: it is admitted by the
            # path fence_runner() vetted, and the reach audit bounds what it runs (REQ-682).
            self.vet_extra([runner], entries)
        return runner

    def tiers(self, branch, config_extra=(), write_roots=(), read_roots=(), result=None):
        """``(allow, deny)``: the argv elements of the tiers that travel as flags (BR-8, ADR-6).

        The file tools reach only ``write_roots`` (read and write) and ``read_roots`` (read):
        every repo's working copy and ToolkitRoot at a launch (BUG-265). A fence runs through
        the fence runner, admitted by its one absolute path (REQ-682 ADR-1). ``result`` is the
        REQ-664 result file, read from ToolkitRoot: only a valid ``deny_under_allow`` pass in
        it restores a wrapper allow (REQ-662 ADR-3).

        A tier the adapter renders to a file travels in :meth:`rule_files`' text, never as a
        flag: on ``allow_render: file`` the allow list is empty, and the deny list is empty
        unless ``deny_render`` is ``flags``. Every extra allow is still vetted.
        """
        entries, _findings = self._render(result)
        extras = self._extras(branch, config_extra, entries)
        runner = self._runner(entries)
        allow, deny = [], []
        if self.block.get("allow_render") == "flags":
            allow = list(self.block.get("allow_tools", []))
            allow += self.file_rules(write_roots, read_roots)
            if runner:
                allow.append(self.spell([runner]))
            allow += [self.spell(entry["spelling"], entry.get("exact", False))
                      for entry in entries if entry["kind"] == "allow"]
            allow += [self.spell(argv, exact=exact) for argv, exact in extras]
        if self.can_deny and self.block.get("deny_render") == "flags":
            deny = [self.spell(entry["spelling"], deny=True)
                    for entry in entries if entry["kind"] == "deny"]
        return list(dict.fromkeys(allow)), list(dict.fromkeys(deny))

    def rule_files(self, branch, config_extra=(), result=None):
        """The text of the files this adapter's rules travel in, a
        ``harness_render.ExecFiles`` (REQ-662 ADR-3), or None when both tiers are flags.
        Rendered, never written: the engine writes and checksums them for the run.

        The fence-runner allow is the path :meth:`fence_runner` vets, and an extra allow is
        vetted as :meth:`tiers` vets it, so the two forms refuse the same launches."""
        if "file" not in (self.block.get("allow_render"), self.block.get("deny_render")):
            return None
        entries, _findings = self._render(result)
        extras = self._extras(branch, config_extra, entries)
        values = {"fence_runner": self._runner(entries), "allow_extra": extras}
        try:
            return hr.render_exec_files(self.adapter, self.toolkit, result, values)
        except hr.RenderError as exc:
            raise ExecRefused(str(exc))

    def exec_report(self, result=None, verdict=None, allow_unverified=False):
        """What the pre-flight judges of the exec-scope render (REQ-662 BR-3, BR-4), an
        :class:`ExecReport`.

        The findings are compared with ``accepted_fidelity`` at ``exec``. Each deny-tier or
        ``engine_deny`` command the render has no deny for is ``deny_unsupported``, and under
        ``allow_unverified`` with ``verdict`` (``exec_verify.Verdict``) unverified and its
        ``ask-tier-deny`` reading not ``pass`` every one is: no deny was measured to hold."""
        _entries, findings = self._render(result)
        undeclared = hr.exec_undeclared(self.adapter, findings)
        report = hr.exec_fidelity_report(self.adapter, findings, undeclared)
        reasons = []
        for f in findings:
            if f.verdict == "deny-unsupported":
                reasons.append((f.entry, f.command, f.detail or "no deny spelling"))
        whole = None
        if allow_unverified and verdict is not None and not verdict.verified:
            reading = verdict.readings.get("ask-tier-deny", "missing")
            if reading != "pass":
                whole = ("--allow-unverified, and ask-tier-deny reads %s, so no deny is measured "
                         "to hold" % reading)
                perms = ha.load_permissions(ha.permissions_path(self.toolkit))
                reasons = [(did, " ".join(dcmd), whole)
                           for did, dcmd, _m in hr.deny_commands(self.adapter, perms, "exec")]
        out, seen = [], set()
        for entry, command, reason in reasons:
            if (entry, command) in seen:
                continue
            seen.add((entry, command))
            out.append(DenyUnsupported(entry, command, reason,
                                       local_destructive(command.split(" "))))
        return ExecReport(findings, report, undeclared, out, whole)

    def launch_argv(self, binary, allow, deny, resume=None, extra=(), add_dir=None,
                    settings=None, values=None):
        """The whole argv, built from the adapter's templates and checked closed-world before it
        is returned (REQ-662 ADR-7). The prompt is on stdin, so nothing positional follows.

        ``resume`` is a session id: the ``resume`` template runs in place of ``launch``.
        ``extra`` is the operator's --harness-flag tokens. ``settings`` is the engine's settings
        file, and with it the ``config_isolation`` tokens follow. ``values`` fills the other
        placeholders by name: ``worktree``, ``last_message`` and ``branch``."""
        extra = [str(tok) for tok in extra]
        refuse_forbidden(extra, self.forbidden)
        template = "resume" if resume else "launch"
        vals = dict(values or {})
        if resume:
            vals["session_id"] = resume
        if settings is not None:
            vals["settings"] = settings
        argv = [binary] + substitute(self.template(template), vals) + extra
        if settings is not None:
            argv += substitute(self.block.get("config_isolation", []), vals)
        if add_dir:
            if not self.block.get("add_dir_flag"):
                raise ExecRefused("harness %s declares no add_dir_flag, so a second directory "
                                  "cannot be added" % self.name)
            argv += [self.block["add_dir_flag"], add_dir]
        if self.block["allow_render"] == "flags":
            argv += [self.block["allow_flag"]] + list(allow)
        if deny and self.can_deny and self.block["deny_render"] == "flags":
            argv += [self.block["deny_flag"]] + list(deny)
        refuse_forbidden(argv, self.forbidden)
        pairs = {"operator": extra, "isolation": settings is not None, "add_dir": add_dir,
                 "allow": list(allow), "deny": list(deny)}
        return self.closed_world(argv, template, pairs, vals)

    def expected_argv(self, binary, template, pairs, values=None):
        """What ``template`` allows with ``pairs`` added, rebuilt from the adapter's own
        declaration (REQ-662 ADR-7): the one argv :meth:`closed_world` accepts.

        ``pairs`` holds the additions, each under the flag the adapter declares and in this
        order: ``operator`` (--harness-flag tokens, each flag in ``operator_flags``),
        ``isolation`` (true adds ``config_isolation``), ``add_dir`` (a path after
        ``add_dir_flag``), and ``allow`` and ``deny`` (the renderer's rules after ``allow_flag``
        and ``deny_flag``, each only where that tier renders as flags)."""
        unknown = sorted(set(pairs) - set(ADDITIONS))
        if unknown:
            raise ExecRefused("closed world: %s is not an addition a launch makes (%s)"
                              % (", ".join(unknown), ", ".join(ADDITIONS)))
        vals = values or {}
        out = [binary] + substitute(self.template(template), vals)
        out += self.operator_tokens(pairs.get("operator") or ())
        if pairs.get("isolation"):
            out += substitute(self.block.get("config_isolation", []), vals)
        if pairs.get("add_dir"):
            if not self.block.get("add_dir_flag"):
                raise ExecRefused("closed world: harness %s declares no add_dir_flag"
                                  % self.name)
            out += [self.block["add_dir_flag"], _vet_value("add_dir", pairs["add_dir"])]
        if self.block["allow_render"] == "flags":
            out += [self.block["allow_flag"]] + _rules("allow", pairs.get("allow") or ())
        deny = pairs.get("deny") or ()
        if deny and self.can_deny and self.block["deny_render"] == "flags":
            out += [self.block["deny_flag"]] + _rules("deny", deny)
        return out

    def closed_world(self, argv, template, pairs, values=None):
        """``argv`` when it is exactly :meth:`expected_argv`, or :class:`ExecRefused` naming the
        first token that differs (REQ-662 BR-16, ADR-7). One extra, one changed or one
        reordered token refuses the launch or the resume; ``forbidden_flags`` stays the lint
        backstop."""
        argv = list(argv)
        if not argv:
            raise ExecRefused("closed world: the argv is empty, so nothing is launched")
        expected = self.expected_argv(argv[0], template, pairs, values)
        if argv != expected:
            raise ExecRefused("closed world: %s, so nothing is launched (REQ-662 BR-16)"
                              % _first_difference(argv, expected))
        return argv

    def isolation_flags(self, settings_path):
        """The ``config_isolation`` tokens with ``{settings}`` filled as one whole token."""
        return substitute(self.block.get("config_isolation", []), {"settings": settings_path},
                          partial=True)

    def isolation_available(self, help_text):
        """Whether ``<binary> --help`` lists every config-isolation flag (BR-25)."""
        wanted = self.block.get("config_isolation_help", [])
        return bool(wanted) and all(re.search(r"(^|\s)%s(\s|,|$)" % re.escape(flag), help_text,
                                              re.M) for flag in wanted)

    def settings_document(self, allow, deny):
        """The orchestrator-written settings file: both tiers, and no hooks (BR-25)."""
        keys = self.block.get("settings_keys", {})
        doc = {}
        for name, values in (("allow", allow), ("deny", deny)):
            path = keys.get(name)
            if not path:
                continue
            node = doc
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = list(values)
        return doc

    def child_env(self, environ, req, scoped_token, gh_config_dir, shared):
        """Exactly the adapter's list, plus what the orchestrator sets (BR-22): the run, the
        child's forge credentials, and the delegation opt-out on a short shell timeout."""
        names = list(self.block["env_passthrough"]) + list(self.block.get("auth_env", []))
        env = {k: environ[k] for k in names if k in environ}
        env["ADLC_EXEC_RUN"] = req
        if not self.delegate_supported:
            # A delegated adlc-read would time out mid-call, so each delegation step takes its
            # documented fallback through the gate (`disabled-via-env`) (REQ-662 BR-10).
            env["ADLC_DISABLE_DELEGATE"] = "1"
        if shared:
            token = environ.get("GH_TOKEN")
            if token:
                env["GH_TOKEN"] = token
        else:
            env["GH_CONFIG_DIR"] = gh_config_dir
            env["GH_TOKEN"] = scoped_token
        return env

    def parse_result(self, text, last_message=None):
        """The harness's result, normalized; every value still data (BR-17), never an
        instruction.

        Read through ``output`` (REQ-662 ADR-6). ``text`` is the run's stdout. Under
        ``source: file``, ``last_message`` is the text of the ``{last_message}`` file the launch
        named, or None when the harness wrote none. ``format: json`` is one result object, or
        the last line that is one; each field is a key path into it. ``format: jsonl-stream``
        is one event per line; each field is ``{event, key}``, read from the first event of
        that type where the key is set for ``session_id`` and from the last one for every
        other field.

        ``error`` is the parser's message when the output is not what the adapter declares
        (REQ-662 BR-6): no result object, a line that is not a JSON event, a stream cut short
        (its last line cut, or no ``terminal_event`` event), or an empty final message.
        Whatever did parse is still returned. A missing session id is not a parse failure: it
        makes resume impossible (BR-7). ``terminal_event`` is indexed, never defaulted: the
        loader requires it under ``jsonl-stream``, and a stream block without it raises
        ``KeyError`` here rather than reading a stream cut between two lines as complete."""
        spec = self.output
        out = {"present": False, "session_id": None, "is_error": None, "num_turns": None,
               "text": "", "cost": None, "denials": [], "error": None}
        text = text or ""
        if spec["format"] == "json":
            doc = _json_result(text)
            error = None if doc is not None else "stdout holds no JSON result object"
            out["present"] = doc is not None

            def field(key, first=False):
                return _at(doc, spec.get(key)) if doc is not None else None
        else:
            events, error = _jsonl_events(text, spec["terminal_event"])
            out["present"] = bool(events)

            def field(key, first=False):
                return _pick(events, spec.get(key), first)
        sid = field("session_id", first=True)
        if isinstance(sid, str) and _SESSION_RE.match(sid):
            out["session_id"] = sid
        out["is_error"] = field("is_error")
        turns = field("num_turns")
        out["num_turns"] = turns if isinstance(turns, int) else None
        if spec["source"] == "file":
            body = last_message
            if body is None and error is None:
                error = "the harness wrote no last-message file"
        else:
            body = field("final_message")
        out["text"] = body if isinstance(body, str) else ""
        if error is None and not out["text"].strip():
            error = "the final message is empty"
        cost = field("cost")
        out["cost"] = cost if isinstance(cost, (int, float)) else None
        denied = field("denials")
        if isinstance(denied, list):
            out["denials"] = denied
        out["error"] = error
        return out

    def refusal_line(self, stderr):
        """The first line of the harness's stderr that ``denied_stderr`` matches, or None.

        Applied to the harness's own stderr log only, never to the model's message: a model
        can write anything, and a refusal is read only from what the harness records
        (REQ-662 ADR-6, LESSON-847)."""
        pattern = self.block.get("denied_stderr")
        if not pattern or not stderr:
            return None
        found = re.compile(pattern)
        for line in stderr.splitlines():
            if found.search(line):
                return line.strip()[:300]
        return None

    def exit_class(self, rc, result, claim, stderr=""):
        """The closed ExitClass (REQ-659 BR-21, REQ-662 BR-8). The raw code through
        ``exit_codes``, an undeclared code ``error``; with no claim, a refusal the harness
        recorded (the result's denial list, or its own refusal line on ``stderr``) is
        ``denied``; output that did not parse is never ``ok`` (BR-6)."""
        if rc is None:
            klass = "error"
        else:
            klass = self.block["exit_codes"].get(str(rc))
            if klass is None:
                klass = "ok" if rc == 0 else "error"
        if claim is None and (result.get("denials") or self.refusal_line(stderr)):
            return "denied"
        if result.get("error") and klass == "ok":
            return "error"
        return klass

    def exit_denied(self, rc):
        """Whether ``exit_codes`` maps the raw exit code ``rc`` to ``denied``: False for no
        code (``None``) and for a code the adapter does not declare."""
        if rc is None:
            return False
        return (self.block.get("exit_codes") or {}).get(str(rc)) == "denied"


def _lines(text):
    """``text`` cut at each ``\\n`` and nowhere else, one trailing ``\\r`` stripped from each
    line; a final ``\\n`` ends the last line and starts no empty one. ``str.splitlines`` also
    cuts at U+0085, U+2028 and U+2029, which a JSON writer may leave raw inside a string, so
    one of them in the model's message would cut an event in two (REQ-662 BR-6)."""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _json_result(text):
    """The one JSON result object in ``text``, or the last line that is one, or None."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        for line in reversed(_lines(text)):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _jsonl_events(text, terminal):
    """``(events, error)``: each line of a JSONL stream as an event (a JSON object with a
    ``type``), and the parser's message when the stream is not one. A line ends at ``\\n``
    only (:func:`_lines`), and blank lines are skipped. A last line with no newline that does
    not parse was cut, and a stream with no event of type ``terminal`` (the adapter's
    ``output.terminal_event``) was cut short. The events read before an error are kept."""
    if not text.strip():
        return [], "stdout is empty: the harness printed no event stream"
    lines = _lines(text)
    whole = text.endswith("\n")
    events = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            if number == len(lines) and not whole:
                return events, "the stream's last line is cut (line %d is not JSON and ends " \
                               "with no newline): the stream was truncated" % number
            return events, "stdout line %d is not JSON: the output is not the jsonl-stream " \
                           "the adapter declares" % number
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            return events, "stdout line %d is not an event (a JSON object with a type)" % number
        events.append(event)
    if not any(event["type"] == terminal for event in events):
        return events, "the stream has no %s event: it was truncated" % terminal
    return events, None


def _pick(events, spec, first):
    """The value at ``spec``'s key path in the first (``first``) or last event whose ``type``
    is ``spec``'s event and where that path is set, or None."""
    if not spec:
        return None
    for event in (events if first else reversed(events)):
        if event.get("type") == spec["event"]:
            value = _at(event, spec["key"])
            if value is not None:
                return value
    return None


def _at(doc, path):
    """The value at a dotted key path (``key`` or ``a.b``) in a parsed object, or None."""
    if not path:
        return None
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def terminal_claim(text):
    """The tag on the report's first line, or None. Line two carries a chore PR."""
    first = (text or "").strip().split("\n", 1)[0]
    match = _CLAIM_RE.match(first)
    return match.group(1) if match else None


def load(name, toolkit=None, adapter_path=None):
    """The ``ExecAdapter`` for ``name``, or :class:`ExecRefused` (BR-3)."""
    try:
        adapter = ha.resolve_adapter(name, adapter_path, toolkit)
    except ha.AdapterNotShipped as exc:
        raise ExecRefused("no adapter ships for %s yet: %s" % (name, exc))
    except ha.AdapterError as exc:
        raise ExecRefused(str(exc))
    if "exec_schema_version" not in (adapter.get("exec") or {}):
        staged = staged_harnesses(toolkit)
        raise ExecRefused("harness %s has no exec block yet (%s ships one harness per stage; %s)"
                          % (name, EXEC_ADAPTERS_REQ,
                             "%s %s staged" % (", ".join(staged),
                                               "is" if len(staged) == 1 else "are")
                             if staged else "none is staged yet"))
    return ExecAdapter(adapter, toolkit)


def staged_harnesses(toolkit=None):
    """The shipped adapters a stage of :data:`EXEC_ADAPTERS_REQ` has given an exec block, in
    ``adlc harness detect`` order: an exec block under ``verification: probes``. A block under
    ``verification: recorded`` stands on REQ-659's evidence, not on a stage (REQ-662 BR-1), and
    an adapter that does not load is left out of what is only a message."""
    out = []
    for path in ha.shipped_adapter_paths(toolkit):
        try:
            block = ha.load_adapter(path, toolkit=toolkit).get("exec") or {}
        except ha.AdapterError:
            continue
        if "exec_schema_version" in block and block.get("verification") == "probes":
            out.append(os.path.basename(path)[:-len(".yml")])
    return out


def sandbox_setting(adapter, primary, read_json):
    """The first settings file that turns the sandbox on, or None (OQ-4)."""
    spec = adapter.block.get("sandbox_refuse")
    if not spec:
        return None
    for path in spec.get("files", []):
        if path.startswith("$HOME"):
            full = ha.expand_user_path(path)
        else:
            full = os.path.join(primary, path)
        doc = read_json(full)
        for key in spec.get("key", []):
            doc = doc.get(key) if isinstance(doc, dict) else None
        if doc is True:
            return full
    return None
