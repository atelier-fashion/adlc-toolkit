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

import exec_matcher as em
import harness_adapter as ha
import harness_render as hr

#: Where a harness's exec block lives once it ships (BR-3).
SIBLING_REQ = "REQ-662"
#: Refused at launch whatever an adapter says (BR-8).
ENGINE_FORBIDDEN_FLAGS = ha.ENGINE_FORBIDDEN_FLAGS

_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CLAIM_RE = re.compile(r"^Terminal state: ([a-z_-]+)\s*$")
_EXTRA_RE = re.compile(r"^[A-Za-z0-9_./=+:@%,*-]+$")
#: The fence runner's resolved path: one a prefix rule matches unquoted (probe row 6), so no
#: space, quote or glob, and never a relative one (REQ-682 ADR-8).
_RUNNER_PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]+$")
#: A file root becomes a gitignore-style pattern, so it may hold no glob, quote, space or
#: empty, `.` or `..` segment: any of those would widen the rule (BUG-265).
_ROOT_RE = re.compile(r"^(/[A-Za-z0-9_.-]+)+$")


#: Programs whose first argument names a subcommand: their command base is two tokens.
_SUBCOMMAND_PROGRAMS = ("git", "gh", "az", "adlc", "terraform", "gcloud", "npm", "docker",
                        "kubectl")


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
        wc = self.block["working_copy"]
        return wc["strategy"] if isinstance(wc, dict) else wc

    @property
    def trust_grant(self):
        return self.block["trust_grant"]

    @property
    def forbidden(self):
        return list(dict.fromkeys(list(ENGINE_FORBIDDEN_FLAGS)
                                  + list(self.block.get("forbidden_flags", []))))

    @property
    def can_deny(self):
        return self.adapter["capabilities"].get("deny") == "yes"

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

    def vet_extra(self, argv, entries, exact=False):
        """Refuse an extra allow that is a wildcard, an opener or wraps a deny (ADR-6).

        A deny is looked for in every form REQ-682 BR-2 names, through ``exec_matcher``,
        which judges a compound command one statement at a time as Claude does.
        """
        gran = self.adapter["capabilities"]["allowlist_granularity"]
        for token in argv:
            if not _EXTRA_RE.match(token):
                raise ExecRefused("allow entry %r holds a token the engine will not spell: %r"
                                  % (" ".join(argv), token))
        if hr.forbidden_first_token(argv):
            raise ExecRefused("allow entry %r starts with a token that runs its arguments"
                              % " ".join(argv))
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

    def tiers(self, branch, config_extra=(), write_roots=(), read_roots=()):
        """``(allow, deny)``: the argv elements of both tiers (BR-8, ADR-6).

        The file tools reach only ``write_roots`` (read and write) and ``read_roots`` (read):
        every repo's working copy and ToolkitRoot at a launch (BUG-265). A fence runs through
        the fence runner, admitted by its one absolute path (REQ-682 ADR-1).
        """
        entries, _findings = hr.exec_entries(self.adapter, self.toolkit, None)
        allow = list(self.block.get("allow_tools", []))
        allow += self.file_rules(write_roots, read_roots)
        runner = self.fence_runner()
        if runner:
            self.vet_extra([runner], entries)
            allow.append(self.spell([runner]))
        deny = []
        for entry in entries:
            if entry["kind"] == "allow":
                allow.append(self.spell(entry["spelling"], entry.get("exact", False)))
            elif self.can_deny:
                deny.append(self.spell(entry["spelling"], deny=True))
        for argv in self.block.get("allow_extra", []):
            spelled = [t.replace("{branch}", branch) for t in argv]
            self.vet_extra(spelled, entries)
            allow.append(self.spell(spelled))
        for argv in self.block.get("allow_extra_exact", []):
            spelled = [t.replace("{branch}", branch) for t in argv]
            self.vet_extra(spelled, entries, exact=True)
            allow.append(self.spell(spelled, exact=True))
        for argv in config_extra:
            self.vet_extra(list(argv), entries)
            allow.append(self.spell(argv))
        return list(dict.fromkeys(allow)), list(dict.fromkeys(deny))

    def launch_argv(self, binary, allow, deny, resume=None, extra=(), add_dir=None):
        """The whole argv. The prompt is on stdin, so nothing positional follows."""
        argv = [binary] + list(self.block["launch"]) + list(extra)
        if resume:
            argv += [self.block["resume_flag"], resume]
        if add_dir:
            argv += [self.block["add_dir_flag"], add_dir]
        argv += [self.block["allow_flag"]] + list(allow)
        if deny and self.can_deny:
            argv += [self.block["deny_flag"]] + list(deny)
        refuse_forbidden(argv, self.forbidden)
        return argv

    def isolation_flags(self, settings_path):
        return [t.replace("{settings}", settings_path)
                for t in self.block.get("config_isolation", [])]

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
        """Exactly the adapter's list, plus what the orchestrator sets (BR-22)."""
        names = list(self.block["env_passthrough"]) + list(self.block.get("auth_env", []))
        env = {k: environ[k] for k in names if k in environ}
        env["ADLC_EXEC_RUN"] = req
        if shared:
            token = environ.get("GH_TOKEN")
            if token:
                env["GH_TOKEN"] = token
        else:
            env["GH_CONFIG_DIR"] = gh_config_dir
            env["GH_TOKEN"] = scoped_token
        return env

    def parse_result(self, text):
        """The harness's JSON result, normalized; every value still data (BR-17)."""
        doc = None
        try:
            parsed = json.loads(text)
            doc = parsed if isinstance(parsed, dict) else None
        except ValueError:
            for line in reversed(text.splitlines()):
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    doc = parsed
                    break
        keys = self.block["result_keys"]
        out = {"present": doc is not None, "session_id": None, "is_error": None,
               "num_turns": None, "text": "", "cost": None, "denials": []}
        if doc is None:
            return out
        sid = doc.get(keys.get("session_id", "session_id"))
        if isinstance(sid, str) and _SESSION_RE.match(sid):
            out["session_id"] = sid
        out["is_error"] = doc.get(keys.get("is_error", "is_error"))
        turns = doc.get(keys.get("num_turns", "num_turns"))
        out["num_turns"] = turns if isinstance(turns, int) else None
        body = doc.get(keys.get("text", "result"))
        out["text"] = body if isinstance(body, str) else ""
        cost = doc.get(keys.get("cost", "cost"))
        out["cost"] = cost if isinstance(cost, (int, float)) else None
        denied = doc.get(self.block.get("denied_result_key", ""))
        if isinstance(denied, list):
            out["denials"] = denied
        return out

    def exit_class(self, rc, result, claim):
        """The closed ExitClass (BR-21): the raw code, then the result's denial list."""
        if rc is None:
            klass = "error"
        else:
            klass = self.block["exit_codes"].get(str(rc))
            if klass is None:
                klass = "ok" if rc == 0 else "error"
        if claim is None and result.get("denials"):
            return "denied"
        return klass


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
        raise ExecRefused("harness %s has no exec block yet: the sibling adapters are %s"
                          % (name, SIBLING_REQ))
    return ExecAdapter(adapter, toolkit)


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
