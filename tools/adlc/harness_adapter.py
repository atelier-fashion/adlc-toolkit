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
#: a command, so an allow on it is a wildcard allow (REQ-656 BR-2). ``.`` and ``source``
#: run a file as shell code and ``[`` opens every partial-sourcing fence (REQ-682 BR-7):
#: ``Bash(. :*)`` and ``Bash(source:*)`` are refused like ``Bash(eval:*)``.
FORBIDDEN_FIRST_TOKENS = FIRST_TOKEN_WILDCARDS + ("env", "xargs", "eval", "exec", "sudo", "time",
                                                  "command", "nohup", "node", ".", "source", "[")
#: ...and the same for any token starting with one of these (``python3``).
FORBIDDEN_FIRST_TOKEN_PREFIXES = ("python",)
#: An env-assignment first token (``NAME=value``), refused for every harness (REQ-662 BR-3).
#: Claude strips the prefix before matching, so there an allow on it is inert (REQ-682 row
#: 14); a harness that matches the raw text would admit any command after the assignment.
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def first_token_problem(token):
    """Why ``token`` may not open an allow, or None: it runs its arguments (REQ-656 BR-2,
    REQ-682 BR-7), or it is an env assignment (REQ-662 BR-3)."""
    token = str(token)
    if token in FORBIDDEN_FIRST_TOKENS or token.startswith(FORBIDDEN_FIRST_TOKEN_PREFIXES):
        return "runs its arguments"
    if ENV_ASSIGN_RE.match(token):
        return "is an env assignment"
    return None


#: The ExecAdapter block (REQ-659 BR-3), widened by REQ-662 (ADR-1). Version 1 was REQ-659's
#: shape; version 2 reshapes ``working_copy``, ``resume`` and ``output`` and adds the ExecBlock
#: keys. The loader reads version 2 only: a version-1 block is refused, never half-read.
EXEC_SCHEMA_VERSION = 2
EXEC_WORKING_COPIES = ("worktree", "clone", "orchestrator-git")
EXIT_CLASSES = ("ok", "denied", "timeout", "error")
#: The engine-wide vocabulary every adapter carries (BR-8); REQ-662 adds each
#: harness's equivalents to its own list.
ENGINE_FORBIDDEN_FLAGS = ("--dangerously-skip-permissions",
                          "--allow-dangerously-skip-permissions",
                          "--permission-mode bypassPermissions", "--yolo", "--force",
                          "--allow-all")
#: How a block's ``status`` is earned (REQ-662 BR-11): from the probe result file, or, for a
#: block that predates the probe gate, from its own recorded evidence (BR-1).
EXEC_VERIFICATIONS = ("probes", "recorded")
EXEC_STATUSES = ("verified", "unverified")
#: A REQ-664 ProbeResult status, as ``exec.probes`` copies it.
PROBE_STATUSES = ("pass", "fail", "unknown", "n/a")
PROMPT_DELIVERIES = ("stdin",)
#: The ``stdin-prompt`` probe's variants (REQ-664). Which one a launch implements is read from
#: the adapter's own ``prompt_flag`` tokens: present in ``launch`` or absent.
PROMPT_VARIANTS = ("with-prompt-flag", "without-prompt-flag")
CONTEXT_DELIVERIES = ("hooks", "prompt")
ALLOW_RENDERS = ("flags", "file")
EXEC_DENY_RENDERS = ("flags", "file", "none")
RULES_RELOADS = ("startup", "live", "unknown")
TIMEOUT_DELEGATES = ("supported", "unsupported")
#: The shortest verified shell timeout a delegated ``adlc-read`` fits in (REQ-662 BR-10).
DELEGATE_MIN_TIMEOUT_S = 120
#: ``claude``: ``exec_matcher`` models the harness's statement matching; ``none``: nothing does.
MATCHERS = ("claude", "none")
OUTPUT_FORMATS = ("json", "jsonl-stream")
OUTPUT_SOURCES = ("stdout", "file")
_EXEC_REQUIRED = ("working_copy", "trust_grant", "launch", "forbidden_flags", "exit_codes",
                  "output", "env_passthrough", "engine_deny", "fence_runner",
                  "harness_version", "verification", "status", "prompt_delivery",
                  "prompt_flag", "prompt_variant", "context_delivery", "allow_render",
                  "deny_render", "user_policy_file", "config_surfaces", "rules_reload",
                  "bypass_config_keys", "shell_timeout_s", "matcher")
#: Keys one render form reads (REQ-662 ADR-1), as ``((axis, value), required, optional)``. On
#: that form the required keys must be present and the optional ones may be; on any other form
#: every one of them is refused, so a block carries no field the engine would never read.
_EXEC_FORM_KEYS = (
    (("allow_render", "flags"), ("allow_flag", "shell_rule", "settings_keys"),
     ("shell_rule_exact",)),
    (("allow_render", "file"), ("rule_file",), ()),
    (("deny_render", "flags"), ("deny_flag",), ()),
)
#: Claude's file tools. A bare name in an allow list admits the tool on every path (BUG-265).
EXEC_FILE_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep")

_EXEC_KEYS = set(_EXEC_REQUIRED) | {
    "exec_schema_version", "trust_notice", "resume", "add_dir_flag", "allow_tools",
    "allow_extra", "allow_extra_exact", "auth_env", "config_isolation",
    "config_isolation_help", "sandbox_refuse", "residuals", "file_rules", "probes",
    "operator_flags", "denied_stderr"} | {
    key for _form, required, optional in _EXEC_FORM_KEYS for key in required + optional}
_EXEC_OUTPUT_REQUIRED = ("format", "source", "final_message", "session_id")
#: Where the parsed output holds each field. ``denials`` is the list a run's refusals land in.
_EXEC_OUTPUT_PATHS = ("session_id", "final_message", "is_error", "num_turns", "cost", "denials")
#: The keys of ``format: jsonl-stream`` alone: required under it and refused under any other
#: format, so no block carries one optionally. ``terminal_event`` is the event ``type`` a
#: complete stream carries. A stream without one was cut short, which is a parse failure
#: (REQ-662 BR-6); without the key, a stream cut between two whole lines would parse as
#: complete, so the parser indexes it rather than reading a default.
_EXEC_OUTPUT_STREAM_ONLY = ("terminal_event",)
#: The one placeholder ``final_message`` names under ``source: file``: the engine fills it
#: with a file in the run directory, so the harness writes no last message anywhere else.
_LAST_MESSAGE = "{last_message}"
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_KEY_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_FLAG_NAME_RE = re.compile(r"^--?[A-Za-z0-9][A-Za-z0-9-]*$")
_USER_PATH_PREFIXES = ("$HOME/", "$ADLC_HOME/")
#: A toolkit-relative path, as ``exec.fence_runner`` names the fence runner (REQ-682 ADR-8).
_TOOLKIT_REL_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")

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
    # Codex CLI (REQ-655). A prefix_rule has no exact form, so an exact entry widens, and a
    # pattern token is matched as itself: a `*` in it is no glob (REQ-662 BR-4).
    "starlark-prefix-rule": {"json": False, "surfaces": ("permissions",),
                             "renders_exact": False, "user_delegation": True,
                             "literal_tokens": True},
    "codex-hooks-json": {"json": True, "surfaces": ("hooks",), "renders_exact": False},
    # `trust_entry`: the format exec_trust's per-run `[projects."<path>"]` table is spelled for
    # (REQ-662 BR-5), so the one a `trust_grant: user-config-entry` user config may have.
    "codex-config-toml": {"json": False, "toml": True, "surfaces": ("config",),
                          "renders_exact": False, "trust_entry": True},
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


def _holds_tokens(argv, tokens):
    """Whether ``tokens`` is a contiguous run of ``argv``."""
    n = len(tokens)
    return any(list(argv[i:i + n]) == list(tokens) for i in range(len(argv) - n + 1))


def _user_path(path):
    return path.startswith(_USER_PATH_PREFIXES) and ".." not in path.split("/")


def _exec_forms(src, block, data):
    """The render forms (REQ-662 ADR-1): the keys each form reads, and the deny capability a
    rendered deny needs."""
    _enum(src, "exec.allow_render", block["allow_render"], ALLOW_RENDERS)
    _enum(src, "exec.deny_render", block["deny_render"], EXEC_DENY_RENDERS)
    for (axis, value), required, optional in _EXEC_FORM_KEYS:
        for key in required + optional:
            if block[axis] == value:
                if key in required and key not in block:
                    raise AdapterError(src, "exec." + key, "is required with %s: %s"
                                       % (axis, value))
            elif key in block:
                raise AdapterError(src, "exec." + key, "is read only with %s: %s, and this "
                                   "block declares %s: %s (REQ-662 ADR-1)"
                                   % (axis, value, axis, block[axis]))
    caps = data.get("capabilities")
    if block["deny_render"] != "none" and not (isinstance(caps, dict)
                                               and caps.get("deny") == "yes"):
        raise AdapterError(src, "exec.deny_render", "%s needs capabilities.deny: yes; a harness "
                           "that cannot deny declares none" % block["deny_render"])


def _exec_working_copy(src, block, data):
    """``working_copy: {strategy}`` (REQ-662 BR-9). ``worktree`` needs the top-level record
    that the sandbox reaches the common git dir; the probe that backs it is ``exec_verify``'s."""
    wc = block["working_copy"]
    if not isinstance(wc, dict):
        raise AdapterError(src, "exec.working_copy", "must be a mapping {strategy: ...} at "
                           "exec_schema_version %d" % EXEC_SCHEMA_VERSION)
    _unknown(src, "exec.working_copy.", wc, {"strategy"})
    strategy = _enum(src, "exec.working_copy.strategy", wc.get("strategy"), EXEC_WORKING_COPIES)
    reach = data.get("sandbox_can_reach_common_gitdir")
    if strategy == "worktree" and reach != "true":
        raise AdapterError(src, "exec.working_copy.strategy", "worktree needs the top-level "
                           "sandbox_can_reach_common_gitdir: true (this adapter says %r); "
                           "declare clone or orchestrator-git (REQ-662 BR-9)" % (reach,))


def _exec_trust_grant(src, block, data):
    """``trust_grant`` (REQ-662 BR-5). ``user-config-entry`` appends a TOML
    ``[projects."<path>"]`` table to ``paths.config.user``, a spelling known only for a config
    format the registry marks ``trust_entry``, so a user config in any other format is refused
    here rather than have that table appended to it. An adapter with no ``paths.config.user``
    has no file to write, and ``exec_trust`` refuses its grant at the launch."""
    grant = _enum(src, "exec.trust_grant", block["trust_grant"], TRUST_MECHANISMS)
    config = (data.get("paths") or {}).get("config") or {}
    if grant != "user-config-entry" or "user" not in config:
        return
    fmt = (data.get("formats") or {}).get("config")
    if not (FORMATS.get(fmt) or {}).get("trust_entry"):
        known = ", ".join(sorted(n for n, f in FORMATS.items() if f.get("trust_entry")))
        raise AdapterError(src, "exec.trust_grant", "user-config-entry appends a TOML "
                           "[projects.\"<path>\"] table to paths.config.user, an entry spelled "
                           "for %s; this adapter's user config is %s, for which the entry's "
                           "spelling is not known yet (REQ-662 BR-5)"
                           % (known, fmt or "a file with no declared format"))


def _exec_probes(src, block, verification):
    """``probes``: a cache of the result file's rows, read only under ``verification: probes``
    and never a verdict of its own (REQ-662 BR-11)."""
    if verification == "recorded":
        if "probes" in block:
            raise AdapterError(src, "exec.probes", "is read only with verification: probes; a "
                               "recorded block stands on its recorded evidence (REQ-662 BR-1)")
        return
    if "probes" not in block:
        raise AdapterError(src, "exec.probes", "is required with verification: probes")
    records = _need_list(src, "exec.probes", block["probes"])
    if not records:
        raise AdapterError(src, "exec.probes", "must not be empty with verification: probes")
    seen = set()
    for i, rec in enumerate(records):
        field = "exec.probes[%d]" % i
        _need_map(src, field, rec)
        _unknown(src, field + ".", rec, {"id", "ran_at", "harness_version", "status"})
        for key in ("id", "ran_at", "harness_version"):
            _need_str(src, "%s.%s" % (field, key), rec.get(key))
        _enum(src, field + ".status", rec.get("status"), PROBE_STATUSES)
        if rec["id"] in seen:
            raise AdapterError(src, field + ".id", "%r is listed twice" % rec["id"])
        seen.add(rec["id"])


def _exec_prompt(src, block):
    """``prompt_variant`` names the ``stdin-prompt`` variant the launch implements, and the
    adapter's own ``prompt_flag`` tokens decide which one that is: ``with-prompt-flag`` when
    ``launch`` holds them as a contiguous run, ``without-prompt-flag`` when it does not."""
    _enum(src, "exec.prompt_delivery", block["prompt_delivery"], PROMPT_DELIVERIES)
    flag = _need_list(src, "exec.prompt_flag", block["prompt_flag"])
    if not flag:
        raise AdapterError(src, "exec.prompt_flag", "must not be empty")
    for k, tok in enumerate(flag):
        _need_str(src, "exec.prompt_flag[%d]" % k, tok)
    variant = _enum(src, "exec.prompt_variant", block["prompt_variant"], PROMPT_VARIANTS)
    held = _holds_tokens(block["launch"], flag)
    if held != (variant == "with-prompt-flag"):
        raise AdapterError(src, "exec.prompt_variant", "%s disagrees with exec.launch, which %s "
                           "the prompt_flag tokens %s: the gate would read a stdin-prompt "
                           "variant the launch does not implement"
                           % (variant, "holds" if held else "lacks", json.dumps(flag)))


def _exec_surfaces(src, block):
    """``config_surfaces`` and ``bypass_config_keys`` (REQ-662 BR-15, BR-16). Either may be
    empty only where ``config_isolation`` keeps the harness from reading config at all."""
    isolated = bool(block.get("config_isolation"))
    surfaces = []
    for i, item in enumerate(_need_list(src, "exec.config_surfaces", block["config_surfaces"])):
        path = _project_path(src, "exec.config_surfaces[%d]" % i, item).rstrip("/")
        if path in surfaces:
            raise AdapterError(src, "exec.config_surfaces[%d]" % i, "%r is listed twice" % item)
        surfaces.append(path)
    if not surfaces and not isolated:
        raise AdapterError(src, "exec.config_surfaces", "must name every working-copy file or "
                           "directory the harness reads once the folder is trusted; it may be "
                           "empty only where config_isolation keeps the harness from reading "
                           "them")
    keys = _need_map(src, "exec.bypass_config_keys", block["bypass_config_keys"])
    for path, names in keys.items():
        field = "exec.bypass_config_keys." + path
        if not _user_path(path):
            _project_path(src, field, path)
            if not any(path == s or path.startswith(s + "/") for s in surfaces):
                raise AdapterError(src, field, "is neither a user path ($HOME/, $ADLC_HOME/) nor "
                                   "one of exec.config_surfaces or a file inside one")
        items = _need_list(src, field, names)
        if not items:
            raise AdapterError(src, field, "must not be empty")
        for k, name in enumerate(items):
            _need_str(src, "%s[%d]" % (field, k), name)
    if not keys and not isolated:
        raise AdapterError(src, "exec.bypass_config_keys", "must name, per config surface, the "
                           "keys that relax approval or sandboxing; it may be empty only where "
                           "config_isolation keeps the harness from reading its config")


def _exec_shell_timeout(src, spec):
    """``shell_timeout_s: {value, verified, delegate}`` (REQ-662 BR-10). ``supported`` means a
    verified value of at least ``DELEGATE_MIN_TIMEOUT_S``; ``verified`` is ``true`` or
    ``false`` as written, the way this loader reads every boolean."""
    field = "exec.shell_timeout_s"
    _need_map(src, field, spec)
    _unknown(src, field + ".", spec, {"value", "verified", "delegate"})
    for key in ("value", "verified", "delegate"):
        if key not in spec:
            raise AdapterError(src, "%s.%s" % (field, key), "is required")
    value = spec["value"]
    if value != "unknown" and not (isinstance(value, int) and value > 0):
        raise AdapterError(src, field + ".value", "%r is not a whole number of seconds or "
                           "unknown" % (value,))
    verified = _enum(src, field + ".verified", spec["verified"], ("true", "false"))
    if verified == "true" and value == "unknown":
        raise AdapterError(src, field + ".verified", "true needs a measured value")
    delegate = _enum(src, field + ".delegate", spec["delegate"], TIMEOUT_DELEGATES)
    if delegate == "supported" and not (verified == "true"
                                        and value >= DELEGATE_MIN_TIMEOUT_S):
        raise AdapterError(src, field + ".delegate", "supported needs a verified value of at "
                           "least %d s; declare unsupported" % DELEGATE_MIN_TIMEOUT_S)


def _exec_output(src, block):
    """``output`` (REQ-662 ADR-6). ``format`` is how stdout is parsed; ``source`` is where the
    final message is read. Under ``format: json`` a field is a key path into the result object
    (``key`` or ``a.b``); under ``jsonl-stream`` it is ``{event, key}``, a key path inside the
    event whose ``type`` is ``event``, and the required ``terminal_event`` names the event a
    complete stream carries. Under ``source: file``, ``final_message`` is exactly
    ``{last_message}``, the placeholder that names the file the harness writes its last
    message to, and it must be a whole token of ``launch`` (and of ``resume``), or the engine
    would read a file the harness was never told to write."""
    out = block["output"]
    if not isinstance(out, dict):
        raise AdapterError(src, "exec.output", "must be a mapping {format, source, final_message, "
                           "session_id} at exec_schema_version %d" % EXEC_SCHEMA_VERSION)
    _unknown(src, "exec.output.", out, set(_EXEC_OUTPUT_REQUIRED) | set(_EXEC_OUTPUT_PATHS)
             | set(_EXEC_OUTPUT_STREAM_ONLY))
    for key in _EXEC_OUTPUT_REQUIRED:
        if key not in out:
            raise AdapterError(src, "exec.output." + key, "is required")
    fmt = _enum(src, "exec.output.format", out["format"], OUTPUT_FORMATS)
    source = _enum(src, "exec.output.source", out["source"], OUTPUT_SOURCES)
    if "terminal_event" in out:
        if fmt != "jsonl-stream":
            raise AdapterError(src, "exec.output.terminal_event", "is read under format: "
                               "jsonl-stream only: a json result has no events")
        event = _need_str(src, "exec.output.terminal_event", out["terminal_event"])
        if not _EVENT_TYPE_RE.match(event):
            raise AdapterError(src, "exec.output.terminal_event", "%r is not an event type"
                               % (event,))
    elif fmt == "jsonl-stream":
        raise AdapterError(src, "exec.output.terminal_event", "is required under format: "
                           "jsonl-stream: without it, a stream cut between two whole lines "
                           "parses as complete")
    for key in _EXEC_OUTPUT_PATHS:
        if key not in out:
            continue
        field, value = "exec.output." + key, out[key]
        if key == "final_message" and source == "file":
            if value != _LAST_MESSAGE:
                raise AdapterError(src, field, "under source: file, must be exactly %s, the "
                                   "placeholder the engine fills with the file the harness "
                                   "writes its last message to; it is %r" % (_LAST_MESSAGE,
                                                                             value))
            for argv in ("launch", "resume"):
                if argv in block and value not in block[argv]:
                    raise AdapterError(src, field, "%s is not a whole token of exec.%s"
                                       % (value, argv))
        elif fmt == "json":
            if not isinstance(value, str) or not _KEY_PATH_RE.match(value):
                raise AdapterError(src, field, "must be a key path into the JSON result "
                                   "(`key` or `a.b`)")
        else:
            if not isinstance(value, dict):
                raise AdapterError(src, field, "must be {event, key} under format: "
                                   "jsonl-stream")
            _unknown(src, field + ".", value, {"event", "key"})
            _need_str(src, field + ".event", value.get("event"))
            if not isinstance(value.get("key"), str) or not _KEY_PATH_RE.match(value["key"]):
                raise AdapterError(src, field + ".key", "must be a key path into the event "
                                   "(`key` or `a.b`)")


def _exec_block(src, block, data):
    """The ExecAdapter block at exec schema 2 (REQ-659 BR-3, REQ-662 ADR-1): closed keys,
    each with its shape, and the keys one render form reads only on that form.

    A block without ``exec_schema_version`` stays the opaque map REQ-657 allowed.
    """
    version = block["exec_schema_version"]
    if version != EXEC_SCHEMA_VERSION:
        raise AdapterError(src, "exec.exec_schema_version", "%r is not a version this loader "
                           "knows (%d)%s" % (version, EXEC_SCHEMA_VERSION,
                                             "; version 1 is REQ-659's shape, which REQ-662 "
                                             "widened: migrate the block" if version == 1
                                             else ""))
    _unknown(src, "exec.", block, _EXEC_KEYS)
    for key in _EXEC_REQUIRED:
        if key not in block:
            raise AdapterError(src, "exec." + key, "is required at exec_schema_version %d"
                               % EXEC_SCHEMA_VERSION)
    _exec_forms(src, block, data)
    _exec_working_copy(src, block, data)
    _exec_trust_grant(src, block, data)
    _need_str(src, "exec.harness_version", block["harness_version"])
    _enum(src, "exec.status", block["status"], EXEC_STATUSES)
    _exec_probes(src, block, _enum(src, "exec.verification", block["verification"],
                                   EXEC_VERIFICATIONS))
    for key in ("allow_flag", "deny_flag", "add_dir_flag", "shell_rule", "shell_rule_exact",
                "trust_notice"):
        if key in block:
            _need_str(src, "exec." + key, block[key])
    for key in ("launch", "resume", "allow_tools", "forbidden_flags", "env_passthrough",
                "auth_env", "config_isolation", "config_isolation_help", "residuals",
                "operator_flags"):
        if key in block:
            for i, item in enumerate(_need_list(src, "exec." + key, block[key])):
                if key == "config_isolation" and item == "":
                    continue   # an empty value is an argument: `--setting-sources ""` (BUG-260)
                _need_str(src, "exec.%s[%d]" % (key, i), item)
    if "resume" in block and "{session_id}" not in block["resume"]:
        raise AdapterError(src, "exec.resume", "must hold {session_id} as a whole token: a "
                           "resume that names no session resumes nothing")
    for i, flag in enumerate(block.get("operator_flags", [])):
        if not _FLAG_NAME_RE.match(flag):
            raise AdapterError(src, "exec.operator_flags[%d]" % i, "%r is not a flag name "
                               "(`--name` or `-n`)" % flag)
    _exec_prompt(src, block)
    _enum(src, "exec.context_delivery", block["context_delivery"], CONTEXT_DELIVERIES)
    _enum(src, "exec.rules_reload", block["rules_reload"], RULES_RELOADS)
    _enum(src, "exec.matcher", block["matcher"], MATCHERS)
    if "rule_file" in block:
        _project_path(src, "exec.rule_file", block["rule_file"])
    policy = _need_str(src, "exec.user_policy_file", block["user_policy_file"])
    if policy != "none":
        if not _user_path(policy):
            raise AdapterError(src, "exec.user_policy_file", "%r must be none or a path under "
                               "$HOME/ or $ADLC_HOME/ without '..'" % policy)
        if block["deny_render"] != "file":
            raise AdapterError(src, "exec.user_policy_file", "is written only with deny_render: "
                               "file (this block declares %s); declare none"
                               % block["deny_render"])
    _exec_surfaces(src, block)
    _exec_shell_timeout(src, block["shell_timeout_s"])
    if "denied_stderr" in block:
        pattern = _need_str(src, "exec.denied_stderr", block["denied_stderr"])
        try:
            re.compile(pattern)
        except re.error as exc:
            raise AdapterError(src, "exec.denied_stderr", "is not a regular expression: %s"
                               % exc)
    _exec_output(src, block)
    for i, item in enumerate(block.get("allow_tools", [])):
        if item in EXEC_FILE_TOOLS:
            raise AdapterError(src, "exec.allow_tools[%d]" % i,
                               "%s is a file tool, and a bare file tool admits every path; "
                               "scope it under exec.file_rules (BUG-265)" % item)
    if "file_rules" in block:
        rules = block["file_rules"]
        if not isinstance(rules, dict):
            raise AdapterError(src, "exec.file_rules", "must be a mapping of write and read")
        _unknown(src, "exec.file_rules.", rules, {"write", "read"})
        for kind in ("write", "read"):
            for i, item in enumerate(_need_list(src, "exec.file_rules." + kind,
                                                rules.get(kind, []))):
                _need_str(src, "exec.file_rules.%s[%d]" % (kind, i), item)
                if "{root}" not in item:
                    raise AdapterError(src, "exec.file_rules.%s[%d]" % (kind, i),
                                       "must hold {root}: a file rule with no path admits "
                                       "every path (BUG-265)")
    if "fence_runner" in block:
        runner = _need_str(src, "exec.fence_runner", block["fence_runner"])
        if not _TOOLKIT_REL_RE.match(runner) or ".." in runner.split("/"):
            raise AdapterError(src, "exec.fence_runner", "must be a toolkit-relative path with no "
                               "`..` segment: the engine resolves it under ToolkitRoot (REQ-682)")
    for key in ("allow_extra", "allow_extra_exact", "engine_deny"):
        for i, item in enumerate(_need_list(src, "exec." + key, block.get(key, []))):
            _token_list(src, "exec.%s[%d]" % (key, i), item)
            first = str(item[0])
            why = first_token_problem(first) if key != "engine_deny" else None
            if why:
                raise AdapterError(src, "exec.%s[%d]" % (key, i),
                                   "first token %r %s, so the allow would admit any command "
                                   "(REQ-682 BR-7, REQ-662 BR-3)" % (first, why))
    codes = _need_map(src, "exec.exit_codes", block["exit_codes"])
    for code, klass in codes.items():
        # Quoted, in canonical form: exit_class looks a code up as str(rc).
        if not isinstance(code, str) or not code.lstrip("-").isdigit() or \
                str(int(code)) != code:
            raise AdapterError(src, "exec.exit_codes", "%r is not an exit code" % (code,))
        _enum(src, "exec.exit_codes." + code, klass, EXIT_CLASSES)
    if codes.get("0") != "ok":
        raise AdapterError(src, "exec.exit_codes", "must map \"0\" to ok (REQ-659 BR-21), and "
                           "maps it to %r" % (codes.get("0"),))
    if "settings_keys" in block:
        _unknown(src, "exec.settings_keys.", _need_map(src, "exec.settings_keys",
                                                       block["settings_keys"]), {"allow", "deny"})
    if "sandbox_refuse" in block:
        _unknown(src, "exec.sandbox_refuse.", _need_map(src, "exec.sandbox_refuse",
                                                        block["sandbox_refuse"]), {"files", "key"})
    if not block["forbidden_flags"]:
        raise AdapterError(src, "exec.forbidden_flags", "must not be empty: it carries the "
                           "engine-wide vocabulary (REQ-659 BR-8)")
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
            _exec_block(src, data["exec"], data)

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
            caps.get("fence_unmatchable") != "yes" and \
            not (data.get("exec") or {}).get("fence_runner"):
        # Its one reader is the exec render; an adapter whose exec block names a fence runner
        # renders no fence rule there (REQ-682 ADR-8), so it has nothing to spell.
        raise AdapterError(src, "capabilities.fence_broad_spelling", "required unless the "
                           "granularity is command-base, no rule can match the fence, or the "
                           "exec block names a fence_runner")
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
