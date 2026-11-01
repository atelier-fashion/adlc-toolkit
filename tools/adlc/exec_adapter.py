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

import harness_adapter as ha
import harness_render as hr

#: Where a harness's exec block lives once it ships (BR-3).
SIBLING_REQ = "REQ-662"
#: Refused at launch whatever an adapter says (BR-8).
ENGINE_FORBIDDEN_FLAGS = ha.ENGINE_FORBIDDEN_FLAGS

_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CLAIM_RE = re.compile(r"^Terminal state: ([a-z_-]+)\s*$")
_EXTRA_RE = re.compile(r"^[A-Za-z0-9_./=+:@%,*-]+$")


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

    def spell(self, argv, exact=False):
        text = " ".join(argv)
        if text.endswith("*"):
            # A token that ends in `*` is its own wildcard; `:*` after it would not parse.
            return self.block["shell_rule_exact"] % text
        template = self.block["shell_rule_exact"] if exact else self.block["shell_rule"]
        return template % text

    def vet_extra(self, argv, entries, exact=False):
        """Refuse an extra allow that is a wildcard or wraps a deny (ADR-6)."""
        gran = self.adapter["capabilities"]["allowlist_granularity"]
        for token in argv:
            if not _EXTRA_RE.match(token):
                raise ExecRefused("allow entry %r holds a token the engine will not spell: %r"
                                  % (" ".join(argv), token))
        if hr.forbidden_first_token(argv):
            raise ExecRefused("allow entry %r starts with a token that runs its arguments"
                              % " ".join(argv))
        for entry in entries:
            if entry["kind"] != "deny":
                continue
            for _shape, form in hr.deny_forms(entry["spelling"]):
                if hr.allow_matches(argv, exact, gran, form, exact):
                    raise ExecRefused("allow entry %r would wrap deny-tier `%s`"
                                      % (" ".join(argv), " ".join(form)))

    def tiers(self, branch, config_extra=()):
        """``(allow, deny)``: the argv elements of both tiers (BR-8, ADR-6)."""
        entries, _findings = hr.exec_entries(self.adapter, self.toolkit, None)
        allow = list(self.block.get("allow_tools", []))
        deny = []
        for entry in entries:
            if entry["kind"] == "allow":
                allow.append(self.spell(entry["spelling"], entry.get("exact", False)))
            elif self.can_deny:
                deny.append(self.spell(entry["spelling"]))
        for argv in self.block.get("allow_extra", []):
            spelled = [t.replace("{branch}", branch) for t in argv]
            self.vet_extra(spelled, entries)
            allow.append(self.spell(spelled))
        for argv in self.block.get("allow_extra_exact", []):
            self.vet_extra(list(argv), entries, exact=True)
            allow.append(self.spell(argv, exact=True))
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
