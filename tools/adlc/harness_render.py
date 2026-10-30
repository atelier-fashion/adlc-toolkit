#!/usr/bin/env python3
"""harness_render — render the canonical sources through a harness adapter (REQ-657).

One code path serves every consumer (LESSON-006): ``adlc harness render | install |
drift``, ``adlc agents render --harness``, the doctor's ``render-currency`` check,
and the ``allowlist-fidelity`` and ``render-parity`` lints all call the functions
here, so what a lint reports is what a render writes.

Permissions are rendered as structured :class:`Rule` values first and spelled by a
format renderer last (ADR-4): the matcher (BR-9), the shared-base rule and the
fence rule (BR-8) judge rules, never strings. Nothing here branches on a harness
name: a harness is the adapter's data, and a new file format is one entry in
:data:`FORMATS`.

The allowlist this renders is a convenience for the routine tier. It is never the
gate on a deny-tier command (Rule B): the declared residuals in
``tools/lint-skills/README.md`` say what no matcher sees.

Pure standard library (LESSON-395).
"""

import difflib
import json
import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_adapter as ha  # noqa: E402

FENCE_ID = "fence.partial-source"
#: The fixed sample tail BR-9 appends to an exact deny command.
SAMPLE_TAIL = ("origin", "feature")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

RESTRAINT_SENTENCE = ("This harness does not enforce per-agent tool lists: use only the "
                      "tools this agent's task needs, and edit or write no file unless your "
                      "instructions say to.")
ETHOS_LINE = ("Before anything else, read `.adlc/ETHOS.md` (the project's principles) and "
              "follow it; when it is absent, say so and continue.")

DECLARED_RESIDUALS_HEADING = "Declared residuals"


class RenderError(ValueError):
    """A render that cannot proceed (e.g. an exec deny_render the probe forbids)."""


class Rule(object):
    """One rendered permission rule (ADR-4)."""
    __slots__ = ("entry", "argv", "tier", "kind", "spelling", "exact", "shape")

    def __init__(self, entry, argv, tier, kind, spelling, exact, shape=None):
        self.entry = entry
        self.argv = tuple(argv)
        self.tier = tier
        self.kind = kind            # allow | confirm | deny
        self.spelling = tuple(spelling)
        self.exact = exact
        self.shape = shape          # git-c for a git_c_spelling rule

    def as_dict(self):
        return OrderedDict([("entry", self.entry), ("command", list(self.argv)),
                            ("kind", self.kind), ("spelling", list(self.spelling)),
                            ("exact", self.exact)])


class Finding(object):
    """One FidelityFinding: ``(harness, entry, command, verdict)`` at a scope."""
    __slots__ = ("harness", "entry", "command", "verdict", "scope", "detail")

    def __init__(self, harness, entry, command, verdict, scope, detail=""):
        self.harness = harness
        self.entry = entry
        self.command = command
        self.verdict = verdict
        self.scope = scope
        self.detail = detail

    def key(self):
        return (self.harness, self.entry, self.command, self.verdict, self.scope)

    def format(self):
        tail = (" — " + self.detail) if self.detail else ""
        return "%s %s %s [%s] %s%s" % (self.harness, self.scope, self.entry, self.command,
                                       self.verdict, tail)


# --------------------------------------------------------------------------
# The matcher (BR-9) — fixed per granularity
# --------------------------------------------------------------------------
def allow_matches(spelling, exact, granularity, command, renders_exact):
    """Whether a rendered allow ``spelling`` matches the command ``command``."""
    spelling = tuple(spelling)
    command = tuple(command)
    if exact and renders_exact:
        return spelling == command
    if granularity == "command-base":
        stripped = list(command)
        while stripped and _ENV_ASSIGN_RE.match(stripped[0]):
            stripped.pop(0)
        return len(spelling) == 1 and bool(stripped) and stripped[0] == spelling[0]
    if granularity in ("token-prefix", "subcommand"):
        return len(command) >= len(spelling) and command[:len(spelling)] == spelling
    # prefix: a character prefix of the command text at a word boundary.
    text = " ".join(spelling)
    cmd = " ".join(command)
    return cmd == text or (cmd.startswith(text) and cmd[len(text)] == " ")


def deny_forms(command):
    """The closed set of evaluated spellings of a deny command, with their shapes."""
    command = tuple(command)
    forms = [("prefix", command)]
    if command and command[0] == "git":
        forms.append(("git-c", ("git", "-C", ".") + command[1:]))
    forms.append(("env-prefix", ("NAME=1",) + command))
    forms.append(("shell-opener", ("bash", "-lc", "'%s'" % " ".join(command))))
    return forms


def _spell(argv, granularity):
    """``(spelling, widened)`` of a routine argv under a granularity (ADR-4)."""
    argv = tuple(argv)
    if granularity == "subcommand" and len(argv) > 2:
        return argv[:2], True
    if granularity == "command-base" and len(argv) > 1:
        return argv[:1], True
    return argv, False


def _cmd(argv):
    return " ".join(argv)


# --------------------------------------------------------------------------
# Probe records (ADR-6)
# --------------------------------------------------------------------------
_PROBE_VARIANT = {"prefix": "deny-under-allow", "git-c": "wrapped-allow"}


def load_result_file(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def probe_record_problem(shape, record, result):
    """Why a ``source: probe`` record does not equal REQ-664's result file, or ``None``."""
    variant = _PROBE_VARIANT.get(shape)
    if variant is None:
        return "shape %s has no REQ-664 producer; it stays unverified" % shape
    if result is None:
        return "no REQ-664 result file to verify it against"
    if result.get("harness_version") != record["harness_version"]:
        return ("harness_version %r differs from the result file's %r"
                % (record["harness_version"], result.get("harness_version")))
    try:
        status = result["probes"]["ask-tier-deny"]["sub_results"][variant]["status"]
    except (KeyError, TypeError):
        return "the result file has no ask-tier-deny/%s entry" % variant
    if status != record["result"]:
        return "record says %r, the result file's %s says %r" % (record["result"], variant,
                                                                status)
    return None


def _mechanism_at(adapter, scope):
    if scope == "exec":
        return "deny" if adapter["capabilities"]["deny"] == "yes" else "unsupported"
    if scope == "printed":
        scope = "user"
    return adapter["deny_tier_render"].get(scope, "unsupported")


def restore_ok(adapter, shape, scope, result):
    """Whether ``deny_under_allow[shape]`` is a valid pass for ``scope`` (BR-8)."""
    rec = adapter["capabilities"].get("deny_under_allow", {}).get(shape)
    if not rec or rec["result"] != "pass":
        return False
    if shape in adapter["capabilities"].get("never_restore", []):
        return False
    mech = _mechanism_at(adapter, scope)
    if mech in ("unsupported",) or rec["mechanism"] != mech:
        return False
    if rec["source"] == "grandfathered":
        return (adapter["name"], shape) == ha.GRANDFATHERED
    return probe_record_problem(shape, rec, result) is None


def _never_restore_argv(adapter, spelling):
    for item in adapter["capabilities"].get("never_restore", []):
        if isinstance(item, list) and tuple(spelling[:len(item)]) == tuple(item):
            return True
    return False


# --------------------------------------------------------------------------
# accepted_fidelity lookups
# --------------------------------------------------------------------------
def accepted(adapter, entry, command, scope):
    """The verdict ``accepted_fidelity`` accepts for ``(entry, command)`` at ``scope``."""
    table = adapter.get("accepted_fidelity", {})
    for key in ("%s:%s" % (entry, command), entry):
        if key in table:
            val = table[key]
            if isinstance(val, dict):
                return val.get(scope)
            return val if scope == "project" else None
    return None


# --------------------------------------------------------------------------
# Permissions render (BR-6, BR-8)
# --------------------------------------------------------------------------
def fence_remedy(adapter):
    return ("fence.partial-source is not committed for %s. To pre-approve the "
            "partial-sourcing fence for yourself only, add a user-level allow for the "
            "opening-token prefix `if [ -f .adlc/partials/` in that harness's user settings; "
            "never a bare first-token entry." % adapter["name"])


def render_permissions(adapter, perms, scope, result=None):
    """Render ``perms`` through ``adapter`` at ``scope``.

    Returns ``(rules, findings, extras)`` where ``extras`` holds ``default_mode``
    (``(key, value)`` or ``None``), the ``comment`` and the printed ``remedies``.
    """
    if scope not in ha.RENDER_SCOPES:
        raise RenderError("unknown scope %r" % scope)
    name = adapter["name"]
    caps = adapter["capabilities"]
    gran = caps["allowlist_granularity"]
    fmt = adapter["formats"].get("permissions", "rules-json")
    renders_exact = ha.FORMATS.get(fmt, {}).get("renders_exact", False) and scope != "exec"
    findings = []
    remedies = []
    rules = []
    routine = [e for e in perms["entries"] if e["tier"] == "routine"]
    deny_entries = [e for e in perms["entries"] if e["tier"] == "deny"]
    deny_cmds = [(e["id"], tuple(c), e["match"]) for e in deny_entries for c in e["commands"]]
    exec_cfg = adapter.get("exec") or {}
    if scope == "exec":
        for k, c in enumerate(exec_cfg.get("engine_deny", []) or []):
            if isinstance(c, list) and c:
                deny_cmds.append(("exec.engine_deny", tuple(str(t) for t in c), "prefix"))
        if exec_cfg.get("deny_render") == "none":
            status = None
            if result:
                status = (result.get("probes", {}).get("ask-tier-deny", {}) or {}).get("status")
            if status != "fail":
                raise RenderError("exec.deny_render: none is permitted only with a `fail` "
                                  "ask-tier-deny verdict (REQ-662 BR-11); the result file says %r"
                                  % status)

    # ---- routine tier (never written at user scope)
    candidates = []   # (entry, argv, spelling, exact, widened, shape)
    if scope != "user":
        for e in routine:
            for argv in e["commands"]:
                argv = tuple(argv)
                if e["id"] == FENCE_ID:
                    candidates.append(("fence", e, argv))
                    continue
                exact = e["match"] == "exact" and renders_exact
                if exact:
                    spelling, widened = argv, False
                else:
                    spelling, widened = _spell(argv, gran)
                    if e["match"] == "exact":
                        widened = True   # an exact entry collapsed to a prefix match
                candidates.append(("rule", e, argv, spelling, exact, widened, None))
            if any(c and c[0] == "git" for c in e["commands"]) and e["id"] != FENCE_ID:
                for prefix in caps.get("git_c_spelling", []):
                    spelling, widened = _spell(tuple(prefix), gran)
                    candidates.append(("rule", e, tuple(prefix), spelling, False, widened,
                                       "git-c"))

    seen_spellings = set()
    for cand in candidates:
        if cand[0] == "fence":
            _, e, argv = cand
            rules_f, finds_f, rem = _render_fence(adapter, e, argv, scope, gran)
            rules.extend(rules_f)
            findings.extend(finds_f)
            remedies.extend(rem)
            continue
        _, e, argv, spelling, exact, widened, shape_tag = cand
        command = _cmd(argv)
        wrapped = None
        for did, dcmd, _dmatch in deny_cmds:
            for shape, form in deny_forms(dcmd):
                if allow_matches(spelling, exact, gran, form, renders_exact):
                    if restore_ok(adapter, shape, scope, result) and \
                            not _never_restore_argv(adapter, spelling):
                        continue
                    wrapped = (shape, form)
                    break
            if wrapped:
                break
        if wrapped:
            findings.append(Finding(name, e["id"], command, "inexpressible", scope,
                                    "omitted: it would wrap deny-tier `%s` (shape %s)"
                                    % (_cmd(wrapped[1]), wrapped[0])))
            continue
        verdict = ("widened:%s" % _cmd(spelling)) if widened else "exact"
        findings.append(Finding(name, e["id"], command, verdict, scope))
        key = (spelling, exact)
        if key in seen_spellings:
            continue
        seen_spellings.add(key)
        rules.append(Rule(e["id"], argv, "routine", "allow", spelling, exact, shape_tag))

    # ---- deny tier
    mech = _mechanism_at(adapter, scope)
    allows = [r for r in rules if r.kind == "allow"]
    for did, dcmd, dmatch in deny_cmds:
        command = _cmd(dcmd)
        if mech == "unsupported":
            findings.append(Finding(name, did, command, "deny-unsupported", scope,
                                    "deny_tier_render has no %s mechanism" % scope))
            continue
        if scope == "exec":
            spelling, widened = _spell(dcmd, gran)
            exact = False
        else:
            exact = dmatch == "exact" and renders_exact
            if exact:
                spelling, widened = dcmd, False
            else:
                spelling, widened = _spell(dcmd, gran)
        clash = [a for a in allows
                 if allow_matches(spelling, exact, gran, a.spelling, renders_exact)]
        if clash:
            findings.append(Finding(name, did, command, "deny-unsupported", scope,
                                    "its %s spelling `%s` would also match routine `%s`"
                                    % (gran, _cmd(spelling), _cmd(clash[0].spelling))))
            continue
        rules.append(Rule(did, dcmd, "deny", "confirm" if mech == "confirm" else "deny",
                          spelling, exact))
        verdict = ("widened:%s" % _cmd(spelling)) if widened else "exact"
        findings.append(Finding(name, did, command, verdict, scope))

    # ---- residual:exact-deny (BR-9)
    for e in deny_entries:
        if e["match"] != "exact":
            continue
        for dcmd in e["commands"]:
            ext = tuple(dcmd) + SAMPLE_TAIL
            hit = [a for a in allows if allow_matches(a.spelling, a.exact, gran, ext,
                                                      renders_exact)]
            if hit:
                findings.append(Finding(name, e["id"], _cmd(dcmd), "residual:exact-deny", scope,
                                        "routine `%s` matches `%s`; the exact deny protects "
                                        "only its own spelling" % (_cmd(hit[0].spelling),
                                                                   _cmd(ext))))

    # ---- default_mode (evaluated as a routine entry)
    default_mode = None
    if scope in ("project", "printed"):
        dmm = adapter.get("default_mode_map")
        value = perms["default_mode"]
        if dmm and value in dmm.get("values", {}):
            default_mode = (dmm["key"], dmm["values"][value])
            findings.append(Finding(name, "default_mode", "default_mode", "exact", scope))
        else:
            findings.append(Finding(name, "default_mode", "default_mode", "inexpressible", scope,
                                    "no default_mode_map entry for %r" % value))
    return rules, findings, {"default_mode": default_mode, "comment": perms["comment"],
                             "remedies": remedies}


def _render_fence(adapter, e, argv, scope, gran):
    name = adapter["name"]
    command = _cmd(argv)
    if scope == "exec":
        broad = adapter["capabilities"].get("fence_broad_spelling")
        if not broad:
            return [], [Finding(name, e["id"], command, "inexpressible", scope,
                                "no fence_broad_spelling")], []
        return ([Rule(e["id"], argv, "routine", "allow", tuple(broad), False)],
                [Finding(name, e["id"], command, "widened:%s" % _cmd(broad), scope)], [])
    if scope == "user":
        return [], [], []
    spelling, widened = _spell(argv, gran)
    literal = argv[-1]
    # An opening-token prefix that keeps the partial path literal; a single token
    # (`if`, `sh`, ...) would be a wildcard allow over every shell line (BR-8).
    expressible = len(spelling) > 1 and literal in spelling
    if expressible and accepted(adapter, e["id"], command, scope) != "inexpressible":
        verdict = ("widened:%s" % _cmd(spelling)) if widened else "exact"
        return ([Rule(e["id"], argv, "routine", "allow", spelling, False)],
                [Finding(name, e["id"], command, verdict, scope)], [])
    why = ("withheld by accepted_fidelity" if expressible else
           "the %s granularity cannot keep the partial path literal" % gran)
    return [], [Finding(name, e["id"], command, "inexpressible", scope, why)], [
        fence_remedy(adapter)]


# --------------------------------------------------------------------------
# Fidelity evaluation (BR-9) — the lint's judge
# --------------------------------------------------------------------------
def first_token_wildcard(rule):
    return len(rule.spelling) == 1 and rule.spelling[0] in ha.FIRST_TOKEN_WILDCARDS


def evaluate_rules(adapter, perms, rules, scope, result=None):
    """Failures for a rendered rule list (the renderer's own, or a hand-written one).

    A rendered allow that matches a deny-tier command in a shape whose
    ``deny_under_allow`` record is not a valid pass fails, whatever
    ``accepted_fidelity`` says; so does a first-token-wildcard fence.
    """
    gran = adapter["capabilities"]["allowlist_granularity"]
    fmt = adapter["formats"].get("permissions", "rules-json")
    renders_exact = ha.FORMATS.get(fmt, {}).get("renders_exact", False) and scope != "exec"
    failures = []
    deny_cmds = [(e["id"], tuple(c)) for e in perms["entries"] if e["tier"] == "deny"
                 for c in e["commands"]]
    for rule in rules:
        if rule.kind != "allow":
            continue
        if rule.entry == FENCE_ID and first_token_wildcard(rule):
            failures.append("%s: fence.partial-source rendered as the first-token wildcard "
                            "`%s` — a wildcard allow over every shell line (BR-8)"
                            % (adapter["name"], rule.spelling[0]))
            continue
        if rule.entry == FENCE_ID and scope == "exec":
            continue
        for did, dcmd in deny_cmds:
            for shape, form in deny_forms(dcmd):
                if allow_matches(rule.spelling, rule.exact, gran, form, renders_exact) and \
                        not restore_ok(adapter, shape, scope, result):
                    failures.append("%s: rendered allow `%s` matches deny-tier `%s` (%s) as `%s` "
                                    "in shape %s, and deny_under_allow.%s is not a valid pass"
                                    % (adapter["name"], _cmd(rule.spelling), _cmd(dcmd), did,
                                       _cmd(form), shape, shape))
    return failures


def fidelity(adapter, perms, result=None, scope="project", rules=None):
    """``(findings, failures)`` for one adapter at ``scope`` (default: the gated one)."""
    failures = []
    for shape, rec in adapter["capabilities"].get("deny_under_allow", {}).items():
        if rec["source"] == "probe":
            problem = probe_record_problem(shape, rec, result)
            if problem:
                failures.append("%s: deny_under_allow.%s (source: probe): %s"
                                % (adapter["name"], shape, problem))
        elif (adapter["name"], shape) != ha.GRANDFATHERED:
            failures.append("%s: deny_under_allow.%s: `grandfathered` exists only for %s's %s"
                            % ((adapter["name"], shape) + ha.GRANDFATHERED))
    rendered, findings, _extras = render_permissions(adapter, perms, scope, result)
    failures.extend(evaluate_rules(adapter, perms, rules if rules is not None else rendered,
                                   scope, result))
    for f in findings:
        if f.verdict == "exact":
            continue
        ok = accepted(adapter, f.entry, f.command, scope)
        if ok != f.verdict:
            failures.append("%s: %s [%s] is %s at %s scope and accepted_fidelity does not list "
                            "it%s" % (f.harness, f.entry, f.command, f.verdict, scope,
                                      (" — " + f.detail) if f.detail else ""))
    return findings, failures


def fidelity_report(adapter_paths, result_files=None, toolkit=None, perms_path=None):
    """The ``allowlist-fidelity`` lint: ``(report_lines, failures)`` over the adapters.

    ``result_files`` maps an adapter name to its REQ-664 result file (or is one
    path used for every adapter); tests pass fixtures, the shipped check passes
    ``.adlc/research/harness-probes/<name>.json``.
    """
    perms = ha.load_permissions(perms_path or ha.permissions_path(toolkit))
    lines = []
    failures = []
    for path in adapter_paths:
        try:
            adapter = ha.load_adapter(path, toolkit=toolkit)
        except ha.AdapterError as exc:
            failures.append(str(exc))
            continue
        if isinstance(result_files, dict):
            rpath = result_files.get(adapter["name"])
        else:
            rpath = result_files
        result = load_result_file(rpath)
        findings, fails = fidelity(adapter, perms, result)
        failures.extend(fails)
        counts = {}
        for f in findings:
            lines.append(f.format())
            counts[f.verdict.split(":", 1)[0]] = counts.get(f.verdict.split(":", 1)[0], 0) + 1
        lines.append("%s: %s" % (adapter["name"], ", ".join(
            "%s=%d" % (k, counts[k]) for k in sorted(counts))))
    lines.extend(declared_residuals(toolkit))
    return lines, failures


def declared_residuals(toolkit=None):
    """The declared-residuals section, read from ``tools/lint-skills/README.md`` (BR-18)."""
    path = os.path.join(toolkit or ha.toolkit_dir(), "tools", "lint-skills", "README.md")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    return extract_residuals(text)


def extract_residuals(text):
    """The lines of the ``<!-- declared-residuals -->`` block, markers excluded."""
    lines = text.splitlines()
    out = []
    inside = False
    for line in lines:
        if line.strip() == "<!-- declared-residuals -->":
            inside = True
            continue
        if line.strip() == "<!-- /declared-residuals -->":
            break
        if inside:
            out.append(line)
    return out


# --------------------------------------------------------------------------
# Hooks render (BR-10)
# --------------------------------------------------------------------------
def hook_args(adapter):
    """The argument tail an adapter that renders its own hook file passes (ADR-10)."""
    hooks_spec = adapter["paths"].get("hooks", {})
    if hooks_spec.get("read_by"):
        return ""
    parts = ["--harness", adapter["name"]]
    for item in ha.PAYLOAD_ITEMS:
        fieldname = adapter["hook_payload"][item]
        if fieldname != "unsupported":
            parts += ["--field", "%s=%s" % (item, fieldname)]
    return " " + " ".join(parts)


def render_hooks(adapter, hooks):
    """``(hooks_block, findings)``: the harness's hooks object and per-event reports."""
    unit = adapter.get("hook_timeout_unit", "s")
    tail = hook_args(adapter)
    groups = OrderedDict()   # (event, matcher) -> [hook entries]
    findings = []
    for hook in hooks:
        command = hook["command"].rstrip("\n") + tail
        timeout = hook["timeout_s"] * (1000 if unit == "ms" else 1)
        for ev in hook["events"]:
            target = adapter["hook_events"][ev]
            if target == "unsupported":
                findings.append(Finding(adapter["name"], hook["id"], ev, "unsupported", "project",
                                        "hook_events.%s is unsupported" % ev))
                continue
            if isinstance(target, dict):
                key = (target["event"], target.get("matcher"))
            else:
                key = (target, None)
            groups.setdefault(key, []).append(OrderedDict([
                ("type", "command"), ("command", command), ("timeout", timeout)]))
            findings.append(Finding(adapter["name"], hook["id"], ev, "exact", "project"))
    block = OrderedDict()
    for (event, matcher), entries in groups.items():
        group = OrderedDict()
        if matcher:
            group["matcher"] = matcher
        group["hooks"] = entries
        block.setdefault(event, []).append(group)
    return block, findings


# --------------------------------------------------------------------------
# Formats (ADR-3)
# --------------------------------------------------------------------------
def _claude_spelling(rule):
    text = _cmd(rule.spelling)
    return "Bash(%s)" % text if rule.exact else "Bash(%s:*)" % text


def _set_path(doc, dotted, value):
    keys = dotted.split(".")
    cur = doc
    for k in keys[:-1]:
        cur = cur.setdefault(k, OrderedDict())
    cur[keys[-1]] = value


def format_claude_settings(rules, extras, hooks_block):
    doc = OrderedDict()
    if extras is not None:
        doc["_comment"] = extras["comment"]
        perms = OrderedDict()
        doc["permissions"] = perms
        if extras.get("default_mode"):
            key, value = extras["default_mode"]
            _set_path(doc, key, value)
        allow = [_claude_spelling(r) for r in rules if r.kind == "allow"]
        ask = [_claude_spelling(r) for r in rules if r.kind == "confirm"]
        deny = [_claude_spelling(r) for r in rules if r.kind == "deny"]
        if allow:
            perms["allow"] = allow
        if ask:
            perms["ask"] = ask
        if deny:
            perms["deny"] = deny
    if hooks_block:
        doc["hooks"] = hooks_block
    return dumps_json(doc)


def format_rules_json(rules, extras, hooks_block):
    doc = OrderedDict()
    if extras is not None:
        doc["comment"] = extras["comment"]
        if extras.get("default_mode"):
            doc["default_mode"] = extras["default_mode"][1]
        doc["rules"] = [r.as_dict() for r in rules]
    if hooks_block:
        doc["hooks"] = hooks_block
    return dumps_json(doc)


def dumps_json(doc):
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


#: Format name -> renderer kind; ``harness_adapter.FORMATS`` lists the same names.
FORMATS = {
    "claude-settings-json": format_claude_settings,
    "rules-json": format_rules_json,
    "claude-agent-md": "agents",
    "agents-md": "instructions",
    "claude-md-import": "instructions",
}


# --------------------------------------------------------------------------
# Instructions (BR-12, ADR-12)
# --------------------------------------------------------------------------
def _instructions_dir(toolkit):
    return os.path.join(toolkit or ha.toolkit_dir(), "templates", "instructions")


def skill_names(toolkit):
    root = toolkit or ha.toolkit_dir()
    names = []
    for entry in sorted(os.listdir(root)):
        if os.path.isfile(os.path.join(root, entry, "SKILL.md")):
            names.append(entry)
    return names


def agents_md_text(toolkit=None):
    with open(os.path.join(_instructions_dir(toolkit), "AGENTS.md"), encoding="utf-8") as fh:
        text = fh.read()
    skills = "\n".join("- `/%s`" % n for n in skill_names(toolkit))
    return text.replace("<!-- adlc:skills -->", skills)


def claude_md_text(toolkit=None):
    with open(os.path.join(_instructions_dir(toolkit), "CLAUDE.md"), encoding="utf-8") as fh:
        return fh.read()


IMPORT_LINE = "@AGENTS.md"


def prepend_import(existing):
    """``existing`` with one ``@AGENTS.md`` line prepended when it has none (BR-12)."""
    if any(line.strip() == IMPORT_LINE for line in existing.splitlines()):
        return existing
    return IMPORT_LINE + "\n" + existing


# --------------------------------------------------------------------------
# File plans, writes and merges (BR-2, BR-11, ADR-13)
# --------------------------------------------------------------------------
class FilePlan(object):
    """One file a render writes: its path, its full render, and how it lands."""
    __slots__ = ("harness", "surfaces", "scope", "path", "rel", "content", "write_mode",
                 "owned_keys", "golden")

    def __init__(self, harness, surfaces, scope, path, rel, content, write_mode="create",
                 owned_keys=None, golden=None):
        self.harness = harness
        self.surfaces = surfaces
        self.scope = scope
        self.path = path
        self.rel = rel
        self.content = content
        self.write_mode = write_mode    # create | merge | prepend-import
        self.owned_keys = owned_keys or []
        self.golden = golden

    def target_text(self, existing, force=False):
        """What the file should hold given what it holds now (``None`` = absent)."""
        if existing is None:
            return self.content
        if self.write_mode == "merge":
            return merge_json(existing, self.content, self.owned_keys)
        if self.write_mode == "prepend-import":
            return prepend_import(existing)
        return self.content if force else existing


def _union(old, new):
    if isinstance(old, list) and isinstance(new, list):
        out = list(new)
        for item in old:
            if item not in out:
                out.append(item)
        return out
    if isinstance(old, dict) and isinstance(new, dict):
        out = OrderedDict(new)
        for k, v in old.items():
            out[k] = _union(v, new[k]) if k in new else v
        return out
    return new


def merge_json(existing_text, rendered_text, owned_keys):
    """Refresh the owned top-level keys, union their lists, keep every other key."""
    try:
        existing = json.loads(existing_text, object_pairs_hook=OrderedDict)
    except ValueError as exc:
        raise RenderError("cannot merge into a file that is not JSON: %s" % exc)
    if not isinstance(existing, dict):
        raise RenderError("cannot merge into JSON that is not an object")
    rendered = json.loads(rendered_text, object_pairs_hook=OrderedDict)
    out = OrderedDict(existing)
    for key in owned_keys:
        if key in rendered:
            out[key] = _union(existing.get(key), rendered[key]) if key in existing \
                else rendered[key]
    return dumps_json(out)


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def apply_plans(plans, dry_run=False, force=False, out=None):
    """Write each plan atomically; ``(written, unchanged)`` counts. Idempotent."""
    out = out or sys.stdout
    written = unchanged = 0
    for plan in plans:
        existing = read_text(plan.path)
        target = plan.target_text(existing, force=force)
        surfaces = ",".join(plan.surfaces)
        if existing is not None and target == existing:
            unchanged += 1
            out.write("  unchanged  %s %s %s %s\n" % (plan.harness, surfaces, plan.scope,
                                                      plan.rel))
            continue
        if existing is not None and plan.write_mode == "create" and not force:
            unchanged += 1
            out.write("  kept       %s %s %s %s (exists; --force to overwrite)\n"
                      % (plan.harness, surfaces, plan.scope, plan.rel))
            continue
        if dry_run:
            out.write("  would-write %s %s %s %s\n" % (plan.harness, surfaces, plan.scope,
                                                       plan.rel))
            continue
        write_atomic(plan.path, target)
        written += 1
        out.write("  written    %s %s %s %s\n" % (plan.harness, surfaces, plan.scope, plan.rel))
    return written, unchanged


def plan_surfaces(adapter, scope, project_root, toolkit=None, surfaces=None, result=None):
    """The :class:`FilePlan` list for ``adapter`` at ``scope`` (``project`` / ``user``).

    Surfaces that share a path are composed into one document by their format
    (ADR-3). A ``mounted``, ``via:`` or ``unsupported`` surface writes nothing; a
    ``printed`` one is returned as text in the second element, never a file.
    """
    toolkit = toolkit or ha.toolkit_dir()
    perms = None
    hooks = None
    by_path = OrderedDict()
    printed = []
    wanted = surfaces or ha.SURFACES
    for surface in ha.SURFACES:
        if surface not in adapter["paths"]:
            continue
        spec = adapter["paths"][surface]
        mode = spec["mode"]
        fmt = adapter["formats"].get(surface)
        if mode == "printed":
            if surface in wanted:
                printed.append((surface, fmt))
            continue
        if mode != "rendered" or scope not in spec or surface == "agents":
            continue
        rel = spec[scope]
        path = os.path.join(project_root, rel) if scope == "project" else \
            ha.expand_user_path(rel)
        slot = by_path.setdefault(path, {"rel": rel, "fmt": fmt, "surfaces": [],
                                         "write_mode": spec.get("write_mode", "create"),
                                         "owned": list(spec.get("owned_keys", []))})
        slot["surfaces"].append(surface)
    plans = []
    for path, slot in by_path.items():
        # A file is rendered whole, from every surface that targets it, whenever
        # any wanted surface does: `--surface hooks` must not drop the
        # permissions half of a shared .claude/settings.json (ADR-3).
        if not any(s in wanted for s in slot["surfaces"]):
            continue
        fmt = slot["fmt"]
        golden = os.path.join(toolkit, "harness", adapter["name"], "rendered",
                              os.path.basename(slot["rel"])) if scope == "project" else None
        if fmt in ("claude-agent-md",):
            continue
        if fmt in ("agents-md", "claude-md-import"):
            if fmt == "claude-md-import":
                plans.append(FilePlan(adapter["name"], ["instructions"], scope,
                                      os.path.join(os.path.dirname(path), "AGENTS.md"),
                                      os.path.join(os.path.dirname(slot["rel"]), "AGENTS.md")
                                      .lstrip("/"),
                                      agents_md_text(toolkit), "create"))
                plans.append(FilePlan(adapter["name"], ["instructions"], scope, path, slot["rel"],
                                      IMPORT_LINE + "\n\n" + claude_md_text(toolkit),
                                      "prepend-import"))
            else:
                plans.append(FilePlan(adapter["name"], ["instructions"], scope, path, slot["rel"],
                                      agents_md_text(toolkit), "create"))
            continue
        rules, extras, block = [], None, None
        if "permissions" in slot["surfaces"]:
            if perms is None:
                perms = ha.load_permissions(ha.permissions_path(toolkit))
            rules, _f, extras = render_permissions(adapter, perms, scope, result)
        if "hooks" in slot["surfaces"]:
            if hooks is None:
                hooks = ha.load_hooks(ha.hooks_path(toolkit))
            block, _hf = render_hooks(adapter, hooks)
        content = FORMATS[fmt](rules, extras, block)
        plans.append(FilePlan(adapter["name"], slot["surfaces"], scope, path, slot["rel"],
                              content, slot["write_mode"], slot["owned"], golden))
    return plans, printed


def printed_text(adapter, toolkit=None, result=None):
    """A ``printed`` permissions render: user scope under the committed-scope rules."""
    perms = ha.load_permissions(ha.permissions_path(toolkit))
    rules, findings, extras = render_permissions(adapter, perms, "printed", result)
    fmt = adapter["formats"].get("permissions", "rules-json")
    body = FORMATS[fmt](rules, extras, None) if callable(FORMATS.get(fmt)) else ""
    return body, findings, extras["remedies"]


def exec_entries(adapter, toolkit=None, result=None):
    """The exec-scope permissions render: structured entries (REQ-659 BR-8)."""
    perms = ha.load_permissions(ha.permissions_path(toolkit))
    rules, findings, _extras = render_permissions(adapter, perms, "exec", result)
    return [r.as_dict() for r in rules], findings


# --------------------------------------------------------------------------
# Parity (BR-13) and drift (ADR-11)
# --------------------------------------------------------------------------
def unified(path_label, expected, actual):
    return "".join(difflib.unified_diff(
        (actual or "").splitlines(True), (expected or "").splitlines(True),
        fromfile="%s (committed)" % path_label, tofile="%s (render)" % path_label))


def parity(toolkit=None, adapter_paths=None):
    """ParityResults for every adapter's goldens and the in-tree renders.

    Returns a list of ``(harness, surface, path, status, diff)`` with status
    ``in-parity`` / ``drifted`` / ``missing-golden``.
    """
    toolkit = toolkit or ha.toolkit_dir()
    results = []
    paths = adapter_paths if adapter_paths is not None else ha.shipped_adapter_paths(toolkit)
    for apath in paths:
        adapter = ha.load_adapter(apath, toolkit=toolkit)
        plans, _printed = plan_surfaces(adapter, "project", toolkit, toolkit,
                                        surfaces=("permissions", "hooks"))
        for plan in plans:
            label = os.path.relpath(plan.golden, toolkit)
            committed = read_text(plan.golden)
            if committed is None:
                results.append((adapter["name"], ",".join(plan.surfaces), label,
                                "missing-golden", ""))
            elif committed != plan.content:
                results.append((adapter["name"], ",".join(plan.surfaces), label, "drifted",
                                unified(label, plan.content, committed)))
            else:
                results.append((adapter["name"], ",".join(plan.surfaces), label, "in-parity", ""))
            # The toolkit's own committed render of the same file (in-tree).
            if plan.write_mode != "prepend-import":
                tree = read_text(plan.path)
                if tree is not None or os.path.exists(os.path.dirname(plan.path)):
                    if tree is None:
                        results.append((adapter["name"], ",".join(plan.surfaces), plan.rel,
                                        "missing-golden", ""))
                    elif tree != plan.content:
                        results.append((adapter["name"], ",".join(plan.surfaces), plan.rel,
                                        "drifted", unified(plan.rel, plan.content, tree)))
                    else:
                        results.append((adapter["name"], ",".join(plan.surfaces), plan.rel,
                                        "in-parity", ""))
    # The canonical agents' model: lines (REQ-516 BR-5's drift path).
    import agents_render
    try:
        drift = agents_render.check_drift(toolkit)
    except agents_render.ConfigError as exc:
        results.append(("agents", "agents", "agents/", "drifted", "invalid config: %s\n" % exc))
        drift = []
    for agent, expected, actual in drift:
        rel = "agents/%s.md" % agent
        results.append(("agents", "agents", rel, "drifted",
                        "--- %s (committed)\n+++ %s (render)\n-model: %s\n+model: %s\n"
                        % (rel, rel, actual, expected)))
    if not drift:
        results.append(("agents", "agents", "agents/*.md model:", "in-parity", ""))
    return results


def _settings_sets(doc):
    perms = doc.get("permissions", {}) if isinstance(doc, dict) else {}
    return (set(perms.get("allow", []) or []), set(perms.get("ask", []) or []),
            set(perms.get("deny", []) or []), perms.get("defaultMode"))


def _hook_commands(doc):
    out = set()
    hooks = doc.get("hooks", {}) if isinstance(doc, dict) else {}
    if not isinstance(hooks, dict):
        return out
    for event, groups in hooks.items():
        for group in groups or []:
            for h in (group or {}).get("hooks", []) or []:
                out.add((event, group.get("matcher"), h.get("command")))
    return out


def drift(adapter, project_root, toolkit=None):
    """Template-posture drift of the project's rendered files (ADR-11, BR-11).

    Returns a list of ``(rel, classification, details)``; ``details`` always names
    every deny-tier rule the project copy lacks, whatever the classification.
    """
    toolkit = toolkit or ha.toolkit_dir()
    plans, _printed = plan_surfaces(adapter, "project", project_root, toolkit,
                                    surfaces=("permissions", "hooks"))
    out = []
    for plan in plans:
        existing = read_text(plan.path)
        if existing is None:
            out.append((plan.rel, "missing", ["absent — render it with `adlc harness render "
                                              "--harness %s`" % adapter["name"]]))
            continue
        try:
            have = json.loads(existing)
        except ValueError:
            out.append((plan.rel, "stale", ["not valid JSON"]))
            continue
        want = json.loads(plan.content)
        h_allow, h_ask, h_deny, h_mode = _settings_sets(have)
        w_allow, w_ask, w_deny, w_mode = _settings_sets(want)
        details = []
        missing = False
        for rule in sorted(w_ask - h_ask):
            details.append("missing deny-tier rule (ask): %s" % rule)
            missing = True
        for rule in sorted(w_deny - h_deny):
            details.append("missing deny-tier rule (deny): %s" % rule)
            missing = True
        for rule in sorted(w_allow - h_allow):
            details.append("missing routine rule: %s" % rule)
            missing = True
        if w_mode != h_mode:
            details.append("defaultMode is %r, the render says %r" % (h_mode, w_mode))
            missing = True
        w_hooks = _hook_commands(want)
        h_hooks = _hook_commands(have)
        if "hooks" in want and "hooks" not in have:
            details.append("missing hooks block")
            missing = True
        else:
            for event, matcher, _cmdtext in sorted(w_hooks - h_hooks,
                                                   key=lambda t: (t[0], t[1] or "")):
                details.append("missing or changed hook: %s%s" % (
                    event, (" [%s]" % matcher) if matcher else ""))
                missing = True
        extra = sorted(h_allow - w_allow) + sorted(h_ask - w_ask)
        if missing:
            cls = "stale"
        elif extra or existing != plan.content:
            cls = "customized"
            if extra:
                details.append("project additions: %s" % ", ".join(extra))
        else:
            cls = "synced"
        out.append((plan.rel, cls, details))
    return out


# --------------------------------------------------------------------------
# Agent copies (BR-4, ADR-9)
# --------------------------------------------------------------------------
def split_agent(text):
    """``(frontmatter_lines, body)`` of an agent file."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return [], text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return [], text


def _rewrite_tools(body, tool_map):
    for canon, mapped in tool_map.items():
        if mapped in ("unsupported", canon):
            continue
        body = re.sub(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % re.escape(canon), mapped, body)
    return body


def render_agent_copy(adapter, name, text, model, notices):
    """One canonical agent rendered as a copy for ``adapter`` (BR-4)."""
    caps = adapter["capabilities"]
    tool_map = adapter["tool_map"]
    fm, body = split_agent(text)
    out_fm = []
    tools_line = None
    for line in fm:
        key = line.split(":", 1)[0].strip()
        if key in ("model", "tier"):
            continue
        if key == "tools":
            tools_line = line.split(":", 1)[1]
            continue
        out_fm.append(line)
    restraint = False
    if tools_line is not None:
        canon = [t.strip() for t in tools_line.split(",") if t.strip()]
        mapped = []
        for tool in canon:
            m = tool_map.get(tool, "unsupported")
            if m != "unsupported" and m not in mapped:
                mapped.append(m)
        restriction = caps["agent_tool_restriction"]
        if restriction == "enforced":
            out_fm.append("tools: %s" % ", ".join(mapped))
            if not mapped:
                notices.append("%s: every canonical tool of %s is unsupported; tools: is empty"
                               % (adapter["name"], name))
        elif restriction == "readonly-only":
            if "Edit" not in canon and "Write" not in canon:
                out_fm.append(caps["readonly_marker"])
        else:
            restraint = True
    if model:
        out_fm.insert(min(2, len(out_fm)), "model: %s" % model)
    body = _rewrite_tools(body, tool_map)
    body = re.sub(r"^<!-- model: is rendered by .*-->\n", "", body.lstrip("\n"))
    prefix = []
    if caps["subagent_start_hook"] != "yes":
        prefix.append(ETHOS_LINE)
    if restraint:
        prefix.append(RESTRAINT_SENTENCE)
    head = ("\n\n".join(prefix) + "\n\n") if prefix else ""
    return "---\n" + "\n".join(out_fm) + "\n---\n\n" + head + body
