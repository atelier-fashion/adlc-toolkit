#!/usr/bin/env python3
"""harness_adapter — the harness adapter schema and its one loader (REQ-657 BR-1).

A harness is data: ``harness/<name>.yml`` declares where each surface lives, what
format it is written in, how canonical tool and model names map, what the
harness's permission matcher can express, and its hook events. Every ``adlc
harness`` verb, ``adlc agents render --harness``, the doctor and both lints load
adapters through :func:`load_adapter` and nothing else, so a field the schema does
not know is refused in one place (LESSON-716).

The canonical sources rendered through an adapter are loaded here too:
``templates/permissions.yml`` (:func:`load_permissions`) and
``templates/hooks.yml`` (:func:`load_hooks`).

Pure standard library (LESSON-395): the doctor loads adapters before any venv
exists, so the YAML is read by ``harness_yaml``, never PyYAML.

Adapter discovery (ADR-2): ``harness/<name>.yml`` exists only for the names
``adlc harness detect`` knows. Any other adapter loads only from an explicit
``--adapter-path <file>``, which ``install --all`` and ``/init`` never take.
"""

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_yaml  # noqa: E402

#: The schema versions this loader reads. A bump adds optional fields; a field
#: every adapter must carry is added to ``harness/claude.yml`` by the bumping REQ.
#: Version 2 (REQ-656) adds ``paths.<surface>.also``, ``hook_output``,
#: ``fidelity_notes`` and ``doctor_rows[].fact``, each refused under version 1.
#: Version 3 (REQ-655) adds the ``config`` surface, TOML ``write_mode: merge``,
#: ``capabilities.unmatched_shapes`` and ``unmatched_default``, the ``by_hand`` half
#: of a ``deny_under_allow`` record, ``doctor_rows[].requires`` and a marker row's
#: ``legacy_marker``, and makes ``sandbox_can_reach_common_gitdir`` required.
#: Version 4 (REQ-658) adds ``hook_cwd``, ``hook_output_envelope``, a rendered ``skills``
#: surface and ``capabilities.fence_unmatchable``, and doctor SKIPs an adapter with nothing
#: rendered. Each field is optional and refused under an older version, so no earlier
#: adapter changes.
KNOWN_SCHEMA_VERSIONS = (1, 2, 3, 4)

SURFACES = ("agents", "permissions", "hooks", "instructions", "skills", "config")
#: The surface by name, for code that treats it specially. A schema key, never a directory.
SKILLS_SURFACE = "skills"
SCOPES = ("project", "user")
RENDER_SCOPES = ("project", "user", "exec", "printed")
MODES = ("rendered", "printed", "mounted", "unsupported")
WRITE_MODES = ("create", "merge")
CANONICAL_EVENTS = ("session-start", "session-compact", "subagent-start")
PAYLOAD_ITEMS = ("session_id", "cwd", "transcript_path")
GRANULARITIES = ("subcommand", "token-prefix", "prefix", "command-base")
RESTRICTIONS = ("enforced", "readonly-only", "none")
SHAPES = ("prefix", "git-c", "env-prefix", "shell-opener")
DENY_RENDERS = ("confirm", "deny", "unsupported")
TRUST_MECHANISMS = ("none", "flag", "user-config-entry", "trusted-folders-file")
YES_NO = ("yes", "no")
ALIASES = ("opus", "sonnet", "haiku")
DOCTOR_ROW_KINDS = ("path-exists", "marker-present", "equals-render")
ROW_REQUIRES = ("delegation",)
BY_HAND = ("strictest-wins", "allow-wins", "unverified")
UNMATCHED_DEFAULTS = ("sandbox",)
FIDELITY_VERDICTS = ("inexpressible", "deny-unsupported", "residual:exact-deny")
#: The one deny_under_allow record Rule A grandfathers: Claude's ask-over-allow
#: precedence that the pinned template set already relies on (BR-7, BR-8).
GRANDFATHERED = ("claude", "prefix")
#: Tokens that, alone, are a first-token wildcard over every shell line (BR-8).
FIRST_TOKEN_WILDCARDS = ("if", "sh", "bash", "zsh")
#: First tokens no rendered routine allow may have: each one runs its arguments as
#: a command, so an allow on it is a wildcard allow (REQ-656 BR-2).
FORBIDDEN_FIRST_TOKENS = FIRST_TOKEN_WILDCARDS + ("env", "xargs", "eval", "exec", "sudo", "time",
                                                  "command", "nohup", "node")
#: ...and the same for any token starting with one of these (``python3``).
FORBIDDEN_FIRST_TOKEN_PREFIXES = ("python",)

#: The ExecAdapter block (REQ-659 BR-3).
EXEC_SCHEMA_VERSION = 1
EXEC_WORKING_COPIES = ("worktree", "clone", "orchestrator-git")
EXIT_CLASSES = ("ok", "denied", "timeout", "error")
#: The engine-wide vocabulary every adapter carries (BR-8); REQ-662 adds each
#: harness's equivalents to its own list.
ENGINE_FORBIDDEN_FLAGS = ("--dangerously-skip-permissions",
                          "--allow-dangerously-skip-permissions",
                          "--permission-mode bypassPermissions", "--yolo", "--force",
                          "--allow-all")
_EXEC_REQUIRED = ("working_copy", "trust_grant", "launch", "allow_flag", "shell_rule",
                  "forbidden_flags", "exit_codes", "result_keys", "env_passthrough")
_EXEC_KEYS = set(_EXEC_REQUIRED) | {
    "exec_schema_version", "trust_notice", "resume_flag", "deny_flag", "add_dir_flag",
    "shell_rule_exact", "allow_tools", "allow_extra", "allow_extra_exact", "engine_deny",
    "deny_render", "denied_result_key", "auth_env", "config_isolation",
    "config_isolation_help", "settings_keys", "sandbox_refuse", "residuals"}

#: Every format an adapter may name, with what the loader needs to know of it.
#: ``harness_render.FORMATS`` implements each one; a test holds the two equal.
FORMATS = {
    "claude-settings-json": {"json": True, "surfaces": ("permissions", "hooks"),
                             "renders_exact": True},
    "rules-json": {"json": True, "surfaces": ("permissions",), "renders_exact": False},
    "claude-agent-md": {"json": False, "surfaces": ("agents",), "renders_exact": False},
    "agents-md": {"json": False, "surfaces": ("instructions",), "renders_exact": False},
    "claude-md-import": {"json": False, "surfaces": ("instructions",),
                         "renders_exact": False},
    # Copilot CLI (REQ-656). The allowlist is a printed line: Copilot has no committed
    # form. A bare `shell(<argv>)` is at most as wide as `shell(<argv>:*)`, so an
    # exact routine entry stays bare; a deny is always spelled `:*` (ADR-2).
    "copilot-tool-flags": {"json": False, "surfaces": ("permissions",),
                           "renders_exact": True},
    "copilot-hooks-json": {"json": True, "surfaces": ("hooks",), "renders_exact": False},
    "copilot-agent-md": {"json": False, "surfaces": ("agents",), "renders_exact": False,
                         "agent_suffix": ".agent.md"},
    # Cursor (REQ-656): the CLI's permissions file and the IDE's, which is not the
    # same schema and has no deny key (ADR-6).
    "cursor-cli-json": {"json": True, "surfaces": ("permissions",), "renders_exact": False},
    "cursor-terminal-allowlist": {"json": True, "surfaces": ("permissions",),
                                  "renders_exact": False},
    # Codex CLI (REQ-655). A prefix_rule has no exact form, so an exact entry widens.
    "starlark-prefix-rule": {"json": False, "surfaces": ("permissions",),
                             "renders_exact": False, "user_delegation": True},
    "codex-hooks-json": {"json": True, "surfaces": ("hooks",), "renders_exact": False},
    "codex-config-toml": {"json": False, "toml": True, "surfaces": ("config",),
                          "renders_exact": False},
    "toml-role": {"json": False, "surfaces": ("agents",), "renders_exact": False,
                  "agent_suffix": ".toml", "agent_toml": True},
    # Named for their shape (REQ-658 ADR-5). A map of named hooks with flat handler
    # lists; `action(target)` rules, printed; agent files whose `tools:` is a YAML list,
    # in a directory the user also writes to; a file that lists directories of skills.
    "named-hooks-json": {"json": True, "surfaces": ("hooks",), "renders_exact": False},
    "action-rules-json": {"json": True, "surfaces": ("permissions",), "renders_exact": False},
    "yaml-tools-agent-md": {"json": False, "surfaces": ("agents",), "renders_exact": False,
                            "agent_tools_list": True, "agent_header": True},
    "skills-entries-json": {"json": True, "surfaces": ("skills",), "renders_exact": False},
}

_TOP_KEYS = {
    "name", "schema_version", "binary", "paths", "formats", "tool_map", "tier_map",
    "accepted_fidelity", "deny_tier_render", "default_mode_map", "exec", "trust",
    "sandbox_can_reach_common_gitdir", "hook_events", "hook_timeout_unit",
    "hook_payload", "doctor_rows", "capabilities", "hook_output", "fidelity_notes",
    "hook_cwd", "hook_output_envelope",
}
_REQUIRED_TOP = ("name", "schema_version", "binary", "paths", "formats", "tool_map",
                 "tier_map", "deny_tier_render", "trust", "hook_events", "hook_payload",
                 "capabilities")
_SURFACE_KEYS = {"user", "project", "mode", "write_mode", "owned_keys", "read_by", "also",
                 "values", "refuse", "refuse_keys", "user_owned"}
_CONFIG_KEYS = ("values", "refuse", "refuse_keys", "user_owned")
_CAP_KEYS = {"deny", "subagent_start_hook", "compact_rehook", "agent_tool_restriction",
             "allowlist_granularity", "committable_allowlist", "git_c_spelling",
             "never_restore", "deny_under_allow", "fence_broad_spelling",
             "readonly_marker", "unmatched_shapes", "unmatched_default",
             "fence_unmatchable"}
_CAP_REQUIRED = ("deny", "subagent_start_hook", "compact_rehook", "agent_tool_restriction",
                 "allowlist_granularity", "committable_allowlist")
_DUA_KEYS = ("mechanism", "result", "harness_version", "source")
_LITERAL_HOME_RE = re.compile(r"(^/(Users|home|root|var|private)/)|(^~)")
_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
_TOKEN_BAD_RE = re.compile(r"[\s;|&`]|\$\(")
_HOOK_OUTPUT_RE = re.compile(r"^json:[A-Za-z_][A-Za-z0-9_]*$")
_HOOK_CWD_RE = re.compile(r"^\.\.(/\.\.)*$")
HOOK_IDS = ("ethos-inject", "session-record")


class AdapterError(ValueError):
    """An adapter (or canonical source) outside the schema; names the field."""

    def __init__(self, source, field, reason):
        self.source = source
        self.field = field
        super().__init__("%s: %s: %s" % (source, field, reason))


class AdapterNotShipped(AdapterError):
    """A detect name with no ``harness/<name>.yml`` yet: a SKIP, never a defect."""


# --------------------------------------------------------------------------
# Locations (LESSON-397: toolkit assets from the script, never from cwd)
# --------------------------------------------------------------------------
def toolkit_dir():
    """The toolkit root this module runs from (``toolkit_root``, REQ-669)."""
    import toolkit_root
    return toolkit_root.toolkit_root()


def adapters_dir(toolkit=None):
    return os.path.join(toolkit or toolkit_dir(), "harness")


def detect_table():
    """``{name: (binaries...)}`` from ``adlc harness detect``'s own table."""
    import harness
    return {name: binaries for name, binaries, _mount in harness.HARNESSES}


def shipped_adapter_paths(toolkit=None):
    """``harness/<name>.yml`` for each detect name that has one, in detect order."""
    out = []
    table = detect_table()
    for name in table:
        path = os.path.join(adapters_dir(toolkit), name + ".yml")
        if os.path.isfile(path):
            out.append(path)
    return out


def resolve_adapter(name, adapter_path=None, toolkit=None):
    """Load ``name``'s adapter: ``adapter_path`` when given, else ``harness/<name>.yml``.

    Without ``adapter_path`` the name must be one ``adlc harness detect`` knows: a
    test-only adapter is reachable through the explicit path alone (BR-1).
    """
    if adapter_path:
        adapter = load_adapter(adapter_path, toolkit=toolkit)
        if name and adapter["name"] != name:
            raise AdapterError(adapter_path, "name",
                               "--harness %s names a different adapter (%s)"
                               % (name, adapter["name"]))
        return adapter
    table = detect_table()
    if name not in table:
        raise AdapterError("harness/%s.yml" % name, "name",
                           "unknown harness %r (known: %s); a test-only adapter loads only "
                           "with --adapter-path <file>" % (name, ", ".join(table)))
    path = os.path.join(adapters_dir(toolkit), name + ".yml")
    if not os.path.isfile(path):
        raise AdapterNotShipped("harness/%s.yml" % name, "name",
                                "no adapter ships for %r yet (only %s)" % (
                               name, ", ".join(os.path.basename(p)[:-4]
                                               for p in shipped_adapter_paths(toolkit))))
    return load_adapter(path, toolkit=toolkit)


def expand_user_path(path):
    """``$HOME``/``$ADLC_HOME`` expanded; never a literal home (BR-1)."""
    import adlc_home
    if path == "$ADLC_HOME" or path.startswith("$ADLC_HOME/"):
        return adlc_home.adlc_home() + path[len("$ADLC_HOME"):]
    if path == "$HOME" or path.startswith("$HOME/"):
        home = os.environ.get("HOME") or os.path.expanduser("~")
        return home.rstrip("/") + path[len("$HOME"):]
    raise ValueError("user path %r is not under $HOME or $ADLC_HOME" % path)


def agent_tools(agents_dir):
    """Every tool any ``agents/*.md`` ``tools:`` line names."""
    tools = set()
    if not os.path.isdir(agents_dir):
        return tools
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".md"):
            continue
        fm = read_frontmatter(os.path.join(agents_dir, fn))
        if "tools" in fm:
            tools.update(t.strip() for t in fm["tools"].split(",") if t.strip())
    return tools


def read_frontmatter(path):
    """The flat ``key: value`` frontmatter of an agent file (first ``---`` block)."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if not lines or lines[0].strip() != "---":
        return out
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------
# Schema helpers
# --------------------------------------------------------------------------
def _need_map(src, field, value):
    if not isinstance(value, dict):
        raise AdapterError(src, field, "must be a mapping")
    return value


def _need_list(src, field, value):
    if not isinstance(value, list):
        raise AdapterError(src, field, "must be a list")
    return value


def _need_str(src, field, value):
    if not isinstance(value, str) or not value:
        raise AdapterError(src, field, "must be a non-empty string")
    return value


def _enum(src, field, value, allowed):
    if value not in allowed:
        raise AdapterError(src, field, "%r is not one of %s" % (value, ", ".join(
            str(a) for a in allowed)))
    return value


def _project_path(src, field, value):
    ppath = _need_str(src, field, value)
    if ppath.startswith("/") or ppath.startswith("~") or "$" in ppath or \
            ".." in ppath.split("/"):
        raise AdapterError(src, field, "%r must be repo-relative" % ppath)
    return ppath


def _need_schema(src, field, version, need):
    if version < need:
        raise AdapterError(src, field, "needs schema_version %d (this adapter declares %d)"
                           % (need, version))


def _need_schema_2(src, field, version):
    _need_schema(src, field, version, 2)


def _need_schema_3(src, field, version):
    _need_schema(src, field, version, 3)


def _need_schema_4(src, field, version):
    _need_schema(src, field, version, 4)


def _hook_output_envelope(src, data):
    """Each envelope wraps a hook's ``--context-key`` JSON: valid JSON around one ``%s``,
    with no quote the rendered shell line could not hold."""
    outputs = data.get("hook_output", {})
    for hook, envelope in _need_map(src, "hook_output_envelope",
                                    data["hook_output_envelope"]).items():
        field = "hook_output_envelope." + hook
        _enum(src, field, hook, HOOK_IDS)
        _need_str(src, field, envelope)
        if hook not in outputs:
            raise AdapterError(src, field, "wraps hook_output, which has no %s entry" % hook)
        if envelope.count("%") != 1 or "%s" not in envelope or "'" in envelope:
            raise AdapterError(src, field, "must hold one %s, no other %, and no single quote")
        try:
            json.loads(envelope % "{}")
        except ValueError as exc:
            raise AdapterError(src, field, "is not JSON around %%s: %s" % exc)


def _exec_block(src, block):
    """The ExecAdapter block (REQ-659 BR-3): closed keys, each with its shape.

    A block without ``exec_schema_version`` stays the opaque map REQ-657 allowed.
    """
    if block["exec_schema_version"] != EXEC_SCHEMA_VERSION:
        raise AdapterError(src, "exec.exec_schema_version", "%r is not a version this loader "
                           "knows (%d)" % (block["exec_schema_version"], EXEC_SCHEMA_VERSION))
    _unknown(src, "exec.", block, _EXEC_KEYS)
    for key in _EXEC_REQUIRED:
        if key not in block:
            raise AdapterError(src, "exec." + key, "is required when exec_schema_version is set")
    wc = block["working_copy"]
    if isinstance(wc, dict):
        _unknown(src, "exec.working_copy.", wc, {"strategy"})
        wc = wc.get("strategy")
    _enum(src, "exec.working_copy", wc, EXEC_WORKING_COPIES)
    _enum(src, "exec.trust_grant", block["trust_grant"], TRUST_MECHANISMS)
    for key in ("resume_flag", "allow_flag", "deny_flag", "add_dir_flag", "shell_rule",
                "shell_rule_exact", "trust_notice", "denied_result_key"):
        if key in block:
            _need_str(src, "exec." + key, block[key])
    for key in ("launch", "allow_tools", "forbidden_flags", "env_passthrough", "auth_env",
                "config_isolation", "config_isolation_help", "residuals"):
        if key in block:
            for i, item in enumerate(_need_list(src, "exec." + key, block[key])):
                _need_str(src, "exec.%s[%d]" % (key, i), item)
    for key in ("allow_extra", "allow_extra_exact", "engine_deny"):
        for i, item in enumerate(_need_list(src, "exec." + key, block.get(key, []))):
            _token_list(src, "exec.%s[%d]" % (key, i), item)
    for code, klass in _need_map(src, "exec.exit_codes", block["exit_codes"]).items():
        if not str(code).lstrip("-").isdigit():
            raise AdapterError(src, "exec.exit_codes", "%r is not an exit code" % (code,))
        _enum(src, "exec.exit_codes." + str(code), klass, EXIT_CLASSES)
    _unknown(src, "exec.result_keys.", _need_map(src, "exec.result_keys", block["result_keys"]),
             {"session_id", "is_error", "num_turns", "text", "cost"})
    if "settings_keys" in block:
        _unknown(src, "exec.settings_keys.", _need_map(src, "exec.settings_keys",
                                                       block["settings_keys"]), {"allow", "deny"})
    if "sandbox_refuse" in block:
        _unknown(src, "exec.sandbox_refuse.", _need_map(src, "exec.sandbox_refuse",
                                                        block["sandbox_refuse"]), {"files", "key"})
    missing = [f for f in ENGINE_FORBIDDEN_FLAGS if f not in block["forbidden_flags"]]
    if missing:
        raise AdapterError(src, "exec.forbidden_flags", "must carry the engine-wide vocabulary; "
                           "missing %s" % ", ".join(missing))


def _config_surface(src, field, spec):
    """The ``config`` surface's owned values: what a merge adds and what it refuses."""
    values = _need_map(src, field + ".values", spec.get("values"))
    owned = spec.get("owned_keys", [])
    for key, value in values.items():
        if key not in owned:
            raise AdapterError(src, field + ".values." + key, "not in owned_keys")
        _need_str(src, field + ".values." + key, value)
    if sorted(values) != sorted(owned):
        raise AdapterError(src, field + ".owned_keys", "each owned key needs a value")
    for key, refused in _need_map(src, field + ".refuse", spec.get("refuse", {})).items():
        if key not in owned:
            raise AdapterError(src, field + ".refuse." + key, "not in owned_keys")
        for k, item in enumerate(_need_list(src, field + ".refuse." + key, refused)):
            _need_str(src, "%s.refuse.%s[%d]" % (field, key, k), item)
    for k, item in enumerate(_need_list(src, field + ".refuse_keys",
                                        spec.get("refuse_keys", []))):
        _need_str(src, "%s.refuse_keys[%d]" % (field, k), item)
    if "user_owned" in spec:
        owned_map = _need_map(src, field + ".user_owned", spec["user_owned"])
        _unknown(src, field + ".user_owned.", owned_map, {"table", "key"})
        _need_str(src, field + ".user_owned.table", owned_map.get("table"))
        _need_str(src, field + ".user_owned.key", owned_map.get("key"))


def _unknown(src, prefix, mapping, allowed):
    for key in mapping:
        if key not in allowed:
            raise AdapterError(src, prefix + key if prefix else key,
                               "unknown key (the schema has %s)" % ", ".join(sorted(allowed)))


def _token_list(src, field, value):
    _need_list(src, field, value)
    if not value:
        raise AdapterError(src, field, "must not be empty")
    for k, tok in enumerate(value):
        if not isinstance(tok, str) or not tok:
            raise AdapterError(src, "%s[%d]" % (field, k), "must be a non-empty string token")
        if _TOKEN_BAD_RE.search(tok):
            raise AdapterError(src, "%s[%d]" % (field, k),
                               "token %r is shell text, not an argv token" % tok)
    return [str(t) for t in value]


def _verdict(src, field, value):
    if not isinstance(value, str):
        raise AdapterError(src, field, "must be a verdict string")
    if value.startswith("widened:") and len(value) > len("widened:"):
        return value
    if value in ("narrowed", "exact"):
        raise AdapterError(src, field, "%r is not an acceptable verdict (there is no "
                                       "`narrowed`; `exact` needs no acceptance)" % value)
    return _enum(src, field, value, FIDELITY_VERDICTS + ("widened:<spelling>",))


# --------------------------------------------------------------------------
# The loader
# --------------------------------------------------------------------------
def load_adapter(path, toolkit=None, agents_dir=None, table=None):
    """Load and validate the adapter at ``path``; :class:`AdapterError` on any defect."""
    src = path
    try:
        data = harness_yaml.load_file(path)
    except harness_yaml.YamlError as exc:
        raise AdapterError(src, "yaml", str(exc))
    _need_map(src, "(top level)", data)
    _unknown(src, "", data, _TOP_KEYS)
    for key in _REQUIRED_TOP:
        if key not in data:
            raise AdapterError(src, key, "required key is missing")

    name = _need_str(src, "name", data["name"])
    base = os.path.basename(path)
    if base != name + ".yml":
        raise AdapterError(src, "name", "%r must equal the file's basename (%s)" % (name, base))
    if not isinstance(data["schema_version"], int) or \
            data["schema_version"] not in KNOWN_SCHEMA_VERSIONS:
        raise AdapterError(src, "schema_version", "%r is not a version this loader knows (%s)"
                           % (data["schema_version"],
                              ", ".join(str(v) for v in KNOWN_SCHEMA_VERSIONS)))

    binary = _need_str(src, "binary", data["binary"])
    table = detect_table() if table is None else table
    if name in table and binary not in table[name]:
        raise AdapterError(src, "binary", "%r disagrees with `adlc harness detect`'s table "
                           "for %s (%s)" % (binary, name, ", ".join(table[name])))

    paths = _need_map(src, "paths", data["paths"])
    formats = _need_map(src, "formats", data["formats"])
    for surface in paths:
        if surface not in SURFACES:
            raise AdapterError(src, "paths." + surface, "unknown surface (the schema has %s)"
                               % ", ".join(SURFACES))
        spec = _need_map(src, "paths." + surface, paths[surface])
        _unknown(src, "paths.%s." % surface, spec, _SURFACE_KEYS)
        field = "paths.%s" % surface
        mode = _need_str(src, field + ".mode", spec.get("mode"))
        if mode.startswith("via:"):
            if mode[4:] not in table:
                raise AdapterError(src, field + ".mode", "via: names an unknown harness %r"
                                   % mode[4:])
        else:
            _enum(src, field + ".mode", mode, MODES)
        has_path = "user" in spec or "project" in spec
        if (mode.startswith("via:") or mode in ("unsupported", "printed")) and has_path:
            raise AdapterError(src, field, "a %s surface declares no path" % mode)
        if mode in ("rendered", "mounted") and not has_path:
            raise AdapterError(src, field, "a %s surface declares a user or project path" % mode)
        if "user" in spec:
            upath = _need_str(src, field + ".user", spec["user"])
            if _LITERAL_HOME_RE.search(upath) or "$" in upath and not (
                    upath.startswith("$HOME/") or upath.startswith("$ADLC_HOME/")):
                raise AdapterError(src, field + ".user", "%r is a literal home-directory path; "
                                   "spell it with $HOME or $ADLC_HOME" % upath)
            if not (upath.startswith("$HOME/") or upath.startswith("$ADLC_HOME/")):
                raise AdapterError(src, field + ".user", "%r must start with $HOME/ or "
                                   "$ADLC_HOME/" % upath)
            if "/../" in upath + "/" or upath.endswith("/.."):
                raise AdapterError(src, field + ".user", "must not contain '..'")
        if "project" in spec:
            _project_path(src, field + ".project", spec["project"])
        if "also" in spec:
            _need_schema_2(src, field + ".also", data["schema_version"])
            if mode != "rendered" or "project" not in spec:
                raise AdapterError(src, field + ".also", "only a rendered surface with a project "
                                   "path adds a further file")
            for k, item in enumerate(_need_list(src, field + ".also", spec["also"])):
                ifield = "%s.also[%d]" % (field, k)
                _need_map(src, ifield, item)
                _unknown(src, ifield + ".", item, {"project", "format"})
                _project_path(src, ifield + ".project", item.get("project"))
                ifmt = _need_str(src, ifield + ".format", item.get("format"))
                if ifmt not in FORMATS or surface not in FORMATS[ifmt]["surfaces"]:
                    raise AdapterError(src, ifield + ".format", "format %r does not render the "
                                       "%s surface" % (ifmt, surface))
        if surface == "config":
            _need_schema_3(src, field, data["schema_version"])
        else:
            for key in _CONFIG_KEYS:
                if key in spec:
                    raise AdapterError(src, "%s.%s" % (field, key), "only the config surface "
                                       "takes this key")
        wmode = spec.get("write_mode", "create")
        _enum(src, field + ".write_mode", wmode, WRITE_MODES)
        if mode in ("rendered", "printed"):
            if surface not in formats:
                raise AdapterError(src, "formats." + surface, "a %s surface names its format"
                                   % mode)
        if mode == "rendered" and surface == SKILLS_SURFACE:
            _need_schema_4(src, field + ".mode", data["schema_version"])
        if wmode == "merge":
            fmt = formats.get(surface)
            if fmt not in FORMATS or not (FORMATS[fmt]["json"] or FORMATS[fmt].get("toml")):
                raise AdapterError(src, field + ".write_mode", "merge needs a JSON or TOML format")
            if FORMATS[fmt].get("toml"):
                _need_schema_3(src, field + ".write_mode", data["schema_version"])
            owned = _need_list(src, field + ".owned_keys", spec.get("owned_keys"))
            if not owned:
                raise AdapterError(src, field + ".owned_keys", "merge needs owned keys")
            for k in owned:
                _need_str(src, field + ".owned_keys[]", k)
        elif "owned_keys" in spec:
            raise AdapterError(src, field + ".owned_keys", "only a merge surface owns keys")
        if surface == "config":
            _config_surface(src, field, spec)
        if "read_by" in spec:
            if surface != "hooks":
                raise AdapterError(src, field + ".read_by", "only the hooks surface is read as-is")
            for k, other in enumerate(_need_list(src, field + ".read_by", spec["read_by"])):
                _enum(src, "%s.read_by[%d]" % (field, k), other, tuple(table))
    for surface, fmt in formats.items():
        if surface not in SURFACES:
            raise AdapterError(src, "formats." + surface, "unknown surface")
        if fmt not in FORMATS:
            raise AdapterError(src, "formats." + surface, "format %r has no registered "
                               "renderer (registered: %s)" % (fmt, ", ".join(sorted(FORMATS))))
        if surface not in FORMATS[fmt]["surfaces"]:
            raise AdapterError(src, "formats." + surface, "format %r does not render the %s "
                               "surface" % (fmt, surface))

    tool_map = _need_map(src, "tool_map", data["tool_map"])
    for tool, mapped in tool_map.items():
        _need_str(src, "tool_map." + tool, mapped)
    agents_dir = agents_dir or os.path.join(toolkit or toolkit_dir(), "agents")
    for tool in sorted(agent_tools(agents_dir)):
        if tool not in tool_map:
            raise AdapterError(src, "tool_map." + tool, "missing: an agents/*.md tools: line "
                               "uses %s (map it, or map it to `unsupported`)" % tool)

    tier_map = _need_map(src, "tier_map", data["tier_map"])
    for alias, model in tier_map.items():
        _enum(src, "tier_map." + alias, alias, ALIASES)
        _need_str(src, "tier_map." + alias, model)

    dtr = _need_map(src, "deny_tier_render", data["deny_tier_render"])
    for scope, how in dtr.items():
        _enum(src, "deny_tier_render." + scope, scope, SCOPES)
        _enum(src, "deny_tier_render." + scope, how, DENY_RENDERS)

    accepted = data.get("accepted_fidelity", {})
    _need_map(src, "accepted_fidelity", accepted)
    for key, val in accepted.items():
        field = "accepted_fidelity." + key
        if isinstance(val, dict):
            for scope, verdict in val.items():
                _enum(src, field + "." + scope, scope, ("project", "user", "exec"))
                _verdict(src, field + "." + scope, verdict)
        else:
            _verdict(src, field, val)

    if "default_mode_map" in data:
        dmm = _need_map(src, "default_mode_map", data["default_mode_map"])
        _unknown(src, "default_mode_map.", dmm, {"key", "values"})
        _need_str(src, "default_mode_map.key", dmm.get("key"))
        for k, v in _need_map(src, "default_mode_map.values", dmm.get("values")).items():
            _need_str(src, "default_mode_map.values." + k, v)

    if "exec" in data:
        if not isinstance(data["exec"], dict):
            raise AdapterError(src, "exec", "must be a mapping or absent (its keys are "
                               "REQ-659's and REQ-662's)")
        if "exec_schema_version" in data["exec"]:
            _exec_block(src, data["exec"])

    trust = _need_map(src, "trust", data["trust"])
    _unknown(src, "trust.", trust, {"mechanism", "detail"})
    _enum(src, "trust.mechanism", trust.get("mechanism"), TRUST_MECHANISMS)
    _need_str(src, "trust.detail", trust.get("detail"))

    if "sandbox_can_reach_common_gitdir" in data:
        _enum(src, "sandbox_can_reach_common_gitdir", data["sandbox_can_reach_common_gitdir"],
              ("true", "false", "unverified"))
    elif data["schema_version"] >= 3:
        raise AdapterError(src, "sandbox_can_reach_common_gitdir",
                           "required at schema_version 3 and above")

    events = _need_map(src, "hook_events", data["hook_events"])
    for ev in CANONICAL_EVENTS:
        if ev not in events:
            raise AdapterError(src, "hook_events." + ev, "every canonical event must be mapped "
                               "(to the harness's event name, or `unsupported`)")
    for ev, target in events.items():
        _enum(src, "hook_events." + ev, ev, CANONICAL_EVENTS)
        if isinstance(target, dict):
            _unknown(src, "hook_events.%s." % ev, target, {"event", "matcher"})
            _need_str(src, "hook_events.%s.event" % ev, target.get("event"))
            if "matcher" in target:
                _need_str(src, "hook_events.%s.matcher" % ev, target["matcher"])
        else:
            _need_str(src, "hook_events." + ev, target)
    _enum(src, "hook_timeout_unit", data.get("hook_timeout_unit", "s"), ("s", "ms"))
    payload = _need_map(src, "hook_payload", data["hook_payload"])
    for item in PAYLOAD_ITEMS:
        if item not in payload:
            raise AdapterError(src, "hook_payload." + item, "required (a field name, or "
                               "`unsupported`)")
    for item, fieldname in payload.items():
        _enum(src, "hook_payload." + item, item, PAYLOAD_ITEMS)
        _need_str(src, "hook_payload." + item, fieldname)

    if "hook_output" in data:
        _need_schema_2(src, "hook_output", data["schema_version"])
        for hook, how in _need_map(src, "hook_output", data["hook_output"]).items():
            _enum(src, "hook_output." + hook, hook, HOOK_IDS)
            if not isinstance(how, str) or not _HOOK_OUTPUT_RE.match(how):
                raise AdapterError(src, "hook_output." + hook, "%r is not json:<key>" % (how,))

    if "hook_cwd" in data:
        _need_schema_4(src, "hook_cwd", data["schema_version"])
        if not isinstance(data["hook_cwd"], str) or not _HOOK_CWD_RE.match(data["hook_cwd"]):
            raise AdapterError(src, "hook_cwd", "%r is not a path of .. segments"
                               % (data["hook_cwd"],))
    if "hook_output_envelope" in data:
        _need_schema_4(src, "hook_output_envelope", data["schema_version"])
        _hook_output_envelope(src, data)

    if "fidelity_notes" in data:
        _need_schema_2(src, "fidelity_notes", data["schema_version"])
        for k, note in enumerate(_need_list(src, "fidelity_notes", data["fidelity_notes"])):
            _need_str(src, "fidelity_notes[%d]" % k, note)

    for k, row in enumerate(_need_list(src, "doctor_rows", data.get("doctor_rows", []))):
        field = "doctor_rows[%d]" % k
        _need_map(src, field, row)
        _unknown(src, field + ".", row, {"id", "kind", "target", "remediation", "fact",
                                         "requires"})
        _need_str(src, field + ".id", row.get("id"))
        _enum(src, field + ".kind", row.get("kind"), DOCTOR_ROW_KINDS)
        _need_str(src, field + ".remediation", row.get("remediation"))
        if "fact" in row:
            _need_schema_2(src, field + ".fact", data["schema_version"])
            _need_str(src, field + ".fact", row["fact"])
            if row.get("kind") != "path-exists":
                raise AdapterError(src, field + ".fact", "only a path-exists row states a fact")
        if "requires" in row:
            _need_schema_3(src, field + ".requires", data["schema_version"])
            _enum(src, field + ".requires", row["requires"], ROW_REQUIRES)
        target = row.get("target")
        if row.get("kind") == "marker-present":
            tmap = _need_map(src, field + ".target", target)
            _unknown(src, field + ".target.", tmap, {"path", "marker", "legacy_marker"})
            tpath = _need_str(src, field + ".target.path", tmap.get("path"))
            _need_str(src, field + ".target.marker", tmap.get("marker"))
            if "legacy_marker" in tmap:
                _need_schema_3(src, field + ".target.legacy_marker", data["schema_version"])
                _need_str(src, field + ".target.legacy_marker", tmap["legacy_marker"])
        elif row.get("kind") == "equals-render":
            tpath = _enum(src, field + ".target", target, SURFACES)
        else:
            tpath = _need_str(src, field + ".target", target)
        if ".." in tpath.split("/") or tpath.startswith(("/", "~")):
            raise AdapterError(src, field + ".target", "must be repo-relative or start with "
                               "$HOME/ or $ADLC_HOME/, without '..'")

    caps = _need_map(src, "capabilities", data["capabilities"])
    _unknown(src, "capabilities.", caps, _CAP_KEYS)
    for key in _CAP_REQUIRED:
        if key not in caps:
            raise AdapterError(src, "capabilities." + key, "required key is missing")
    for key in ("deny", "subagent_start_hook", "compact_rehook", "committable_allowlist"):
        _enum(src, "capabilities." + key, caps[key], YES_NO)
    _enum(src, "capabilities.agent_tool_restriction", caps["agent_tool_restriction"],
          RESTRICTIONS)
    if caps["agent_tool_restriction"] == "readonly-only":
        _need_str(src, "capabilities.readonly_marker", caps.get("readonly_marker"))
    _enum(src, "capabilities.allowlist_granularity", caps["allowlist_granularity"],
          GRANULARITIES)
    for k, spelling in enumerate(_need_list(src, "capabilities.git_c_spelling",
                                            caps.get("git_c_spelling", []))):
        _token_list(src, "capabilities.git_c_spelling[%d]" % k, spelling)
    for k, item in enumerate(_need_list(src, "capabilities.never_restore",
                                        caps.get("never_restore", []))):
        if isinstance(item, list):
            _token_list(src, "capabilities.never_restore[%d]" % k, item)
        else:
            _enum(src, "capabilities.never_restore[%d]" % k, item, SHAPES)
    dua = _need_map(src, "capabilities.deny_under_allow", caps.get("deny_under_allow", {}))
    for shape, rec in dua.items():
        field = "capabilities.deny_under_allow." + shape
        _enum(src, field, shape, SHAPES)
        _need_map(src, field, rec)
        _unknown(src, field + ".", rec, set(_DUA_KEYS) | {"by_hand"})
        for key in _DUA_KEYS:
            if key not in rec:
                raise AdapterError(src, field + "." + key, "required field of a deny_under_allow "
                                   "record is missing")
        _enum(src, field + ".mechanism", rec["mechanism"], ("confirm", "deny"))
        _enum(src, field + ".result", rec["result"], ("pass", "unverified"))
        _need_str(src, field + ".harness_version", rec["harness_version"])
        _enum(src, field + ".source", rec["source"], ("probe", "grandfathered"))
        if "by_hand" in rec:
            _need_schema_3(src, field + ".by_hand", data["schema_version"])
            _enum(src, field + ".by_hand", rec["by_hand"], BY_HAND)
        if rec["source"] == "grandfathered" and (name, shape) != GRANDFATHERED:
            raise AdapterError(src, field + ".source", "`grandfathered` exists only for "
                               "%s's %s shape (Rule A); anything else is a probe result"
                               % GRANDFATHERED)
    if "unmatched_shapes" in caps:
        _need_schema_3(src, "capabilities.unmatched_shapes", data["schema_version"])
        for k, item in enumerate(_need_list(src, "capabilities.unmatched_shapes",
                                            caps["unmatched_shapes"])):
            _enum(src, "capabilities.unmatched_shapes[%d]" % k, item, SHAPES)
    if "unmatched_default" in caps:
        _need_schema_3(src, "capabilities.unmatched_default", data["schema_version"])
        _enum(src, "capabilities.unmatched_default", caps["unmatched_default"],
              UNMATCHED_DEFAULTS)
    if "fence_unmatchable" in caps:
        _need_schema_4(src, "capabilities.fence_unmatchable", data["schema_version"])
        _enum(src, "capabilities.fence_unmatchable", caps["fence_unmatchable"], YES_NO)
    if "fence_broad_spelling" in caps:
        fbs = _token_list(src, "capabilities.fence_broad_spelling", caps["fence_broad_spelling"])
        if len(fbs) == 1 and fbs[0] in FIRST_TOKEN_WILDCARDS:
            raise AdapterError(src, "capabilities.fence_broad_spelling", "a bare %r is a "
                               "first-token wildcard over every shell line (BR-8)" % fbs[0])
    elif caps["allowlist_granularity"] != "command-base" and \
            caps.get("fence_unmatchable") != "yes":
        raise AdapterError(src, "capabilities.fence_broad_spelling", "required unless the "
                           "granularity is command-base or no rule can match the fence")
    data["_path"] = os.path.abspath(path)
    return data


# --------------------------------------------------------------------------
# Canonical sources
# --------------------------------------------------------------------------
def load_permissions(path):
    """``templates/permissions.yml``: two tiers of argv-prefix entries (BR-6)."""
    src = path
    try:
        data = harness_yaml.load_file(path)
    except harness_yaml.YamlError as exc:
        raise AdapterError(src, "yaml", str(exc))
    _need_map(src, "(top level)", data)
    _unknown(src, "", data, {"default_mode", "comment", "entries"})
    _need_str(src, "default_mode", data.get("default_mode"))
    _need_str(src, "comment", data.get("comment"))
    seen = set()
    entries = []
    for k, entry in enumerate(_need_list(src, "entries", data.get("entries"))):
        field = "entries[%d]" % k
        _need_map(src, field, entry)
        _unknown(src, field + ".", entry, {"id", "tier", "commands", "match", "note"})
        eid = _need_str(src, field + ".id", entry.get("id"))
        if not _ID_RE.match(eid):
            raise AdapterError(src, field + ".id", "%r is not a dotted semantic id" % eid)
        if eid in seen:
            raise AdapterError(src, field + ".id", "%r is given twice" % eid)
        seen.add(eid)
        _enum(src, field + ".tier", entry.get("tier"), ("routine", "deny"))
        match = entry.get("match", "prefix")
        _enum(src, field + ".match", match, ("prefix", "exact"))
        _need_str(src, field + ".note", entry.get("note"))
        cmds = [_token_list(src, "%s.commands[%d]" % (field, j), c)
                for j, c in enumerate(_need_list(src, field + ".commands", entry.get("commands")))]
        if not cmds:
            raise AdapterError(src, field + ".commands", "must not be empty")
        entries.append({"id": eid, "tier": entry["tier"], "match": match,
                        "note": entry["note"], "commands": cmds})
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    return {"default_mode": data["default_mode"], "comment": data["comment"],
            "entries": entries, "sha256": digest}


def load_hooks(path):
    """``templates/hooks.yml``: the canonical hook set (BR-10)."""
    src = path
    try:
        data = harness_yaml.load_file(path)
    except harness_yaml.YamlError as exc:
        raise AdapterError(src, "yaml", str(exc))
    _need_map(src, "(top level)", data)
    _unknown(src, "", data, {"hooks"})
    out = []
    seen = set()
    for k, hook in enumerate(_need_list(src, "hooks", data.get("hooks"))):
        field = "hooks[%d]" % k
        _need_map(src, field, hook)
        _unknown(src, field + ".", hook, {"id", "events", "command", "timeout_s"})
        hid = _enum(src, field + ".id", hook.get("id"), ("ethos-inject", "session-record"))
        if hid in seen:
            raise AdapterError(src, field + ".id", "%r is given twice" % hid)
        seen.add(hid)
        events = _need_list(src, field + ".events", hook.get("events"))
        for ev in events:
            _enum(src, field + ".events[]", ev, CANONICAL_EVENTS)
        _need_str(src, field + ".command", hook.get("command"))
        timeout = hook.get("timeout_s")
        if not isinstance(timeout, int) or timeout <= 0:
            raise AdapterError(src, field + ".timeout_s", "must be a positive integer (seconds)")
        out.append({"id": hid, "events": list(events), "command": hook["command"],
                    "timeout_s": timeout})
    return out


def permissions_path(toolkit=None):
    return os.path.join(toolkit or toolkit_dir(), "templates", "permissions.yml")


def hooks_path(toolkit=None):
    return os.path.join(toolkit or toolkit_dir(), "templates", "hooks.yml")
