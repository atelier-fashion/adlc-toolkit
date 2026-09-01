"""Shared helpers for the provider-agnostic delegation CLIs.

The delegation layer speaks the generic OpenAI-compatible chat-completions API,
so a "provider" is fully described by three values: a base URL, a model name,
and the *name* of an environment variable holding the API key. Those three
values are resolved in exactly one place — :func:`resolve_provider` — by an
ordered cascade (REQ-515 ADR-2):

    1. CLI flags (--model, --base-url)            (per-field)
    2. ADLC_DELEGATE_* environment variables
    3. config file (~/.claude/adlc/config.yml)    (delegate: block)
    4. legacy key-env continuity (MOONSHOT_API_KEY/KIMI_API_KEY) — key data only
    5. shipped defaults (today's Moonshot/Kimi values)

A machine with today's setup (MOONSHOT_API_KEY in env, no config file) resolves
to the exact current defaults, so behavior is byte-identical.

Dependency-light by design: only ``os``, ``re``, ``stat``, ``subprocess``,
``sys`` from the stdlib plus ``openai`` (``subprocess`` only to locate the repo
root for ``toolkit_version``; ``stat`` only to refuse a non-regular config file;
``urllib.parse`` is imported inside the URL helpers, keeping the module-import
surface small). ``openai`` is imported lazily inside ``get_client`` /
``complete`` so that the pre-API guard paths (privacy notice, --dry-run, clobber
check, the key-in-config refusal, ``--version``) work even when the SDK isn't
installed.

This module also hosts the toolkit-version / ``--version`` reporting helpers
(``toolkit_version``, ``wants_version``, ``harvest_provider_flags``,
``version_report_lines``) shared by all three CLIs — delegation-independent, so
they work on the local-only ``extract-chat`` path too.
"""

import os
import re
import stat
import subprocess
import sys

# --- shipped defaults (today's exact Moonshot/Kimi values) ------------------
# Verified against a live GET /v1/models against api.moonshot.ai, 2026-08-31.
# Other model ids the endpoint served that day: "kimi-k2.7-code",
# "kimi-k2.7-code-highspeed", "kimi-k3".
#
# The previous default, "kimi-k2.5", was retired by the provider and every
# delegated call 404'd. Providers retire ids without notice: when
# delegation starts failing with "model not found", re-run the models list and
# re-pin here rather than assuming the key or the SDK is at fault (LESSON-334).
_DEFAULT_API_KEY_VAR = "MOONSHOT_API_KEY"
_DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
_DEFAULT_MODEL = "kimi-k2.6"

# Legacy aliases retained for back-compat. MOONSHOT_API_KEY is the canonical
# default key var; KIMI_API_KEY is accepted as an alias if present.
_LEGACY_KEY_VARS = ("MOONSHOT_API_KEY", "KIMI_API_KEY")


def _repo_root():
    """Absolute path to the toolkit checkout root.

    Prefers ``git rev-parse --show-toplevel`` from this module's own directory so
    it resolves through the ~/bin wrapper indirection regardless of the caller's
    cwd (LESSON-397: a toolkit asset resolves from the script location, never
    from the caller's project). ``realpath`` first, so a symlinked install walks
    from the real file's directory rather than the symlink's.

    The git-derived root is only accepted when its ``tools/delegate/_common.py``
    IS this very file — an identity check, not an existence check. Same
    LESSON-397 class: when the toolkit is vendored INSIDE another git repo,
    ``rev-parse`` reports the HOST repo's toplevel, and an unvalidated result
    would silently read the host project's ``VERSION`` file. Mere existence is
    not enough either, because an OUTER toolkit checkout that contains a
    vendored INNER copy has the marker file at its own root and would otherwise
    win — reporting the outer version for a run of the inner code. Falling back
    to the walk-up in both cases reports the version of the copy being run.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    try:
        out = subprocess.run(
            ["git", "-C", here, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.strip()
        # ValueError covers UnicodeDecodeError from text=True when a path in the
        # output is not valid UTF-8 — a traceback there would be a crash, not a
        # version report.
        if out and os.path.realpath(
                os.path.join(out, "tools", "delegate", "_common.py")
        ) == os.path.realpath(__file__):
            return out
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    # tools/delegate/_common.py -> tools/delegate -> tools -> <root>
    return os.path.dirname(os.path.dirname(here))


# A version token is a version-ish word: digits, letters, and the separators a
# semver / pre-release / build-metadata string uses. Bounded and charset-limited
# so a VERSION file can never contribute a space, a colon, or a control byte to
# the BR-9 report — the ingredients of a forged `key: value` line.
_VERSION_TOKEN_RE = re.compile(r"^[0-9A-Za-z._+-]{1,64}\Z")


def toolkit_version():
    """Read the toolkit ``VERSION`` file; ``"unknown"`` if it can't be read.

    VERSION is the single source of truth — never hardcode the version here.
    Only the first line is read, bounded: a multi-line or oversized VERSION must
    not be able to forge extra ``key: value`` lines in the BR-9 report. Anything
    that is not a plausible version token (empty, spaced, punctuated, over 64
    chars) reports ``"unknown"`` rather than being echoed into the report.
    """
    path = os.path.join(_repo_root(), "VERSION")
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline(128).strip()
    except OSError:
        return "unknown"
    return first if _VERSION_TOKEN_RE.match(first) else "unknown"


def _config_path():
    """Path to the delegate config file: ``$ADLC_CONFIG`` or the default."""
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "adlc", "config.yml")


def _strip_inline(value):
    """Strip surrounding quotes and a trailing ``# comment`` from a YAML scalar."""
    value = value.strip()
    # Drop an unquoted trailing comment (only when not inside quotes).
    if value[:1] not in ("'", '"'):
        hashpos = value.find(" #")
        if hashpos != -1:
            value = value[:hashpos].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def parse_delegate_config(path=None):
    """Parse the ``delegate:`` block from the YAML config, if the file exists.

    Deliberately a minimal flat ``key: value`` reader — NOT a full YAML parser
    (REQ-515 ADR-3: no PyYAML dependency for three scalar fields). Reads only the
    keys it knows under a top-level ``delegate:`` mapping; ignores everything
    else. Returns a dict with any of ``enabled``/``base_url``/``model``/
    ``api_key_env`` that were present (``enabled`` coerced to bool). An absent or
    unreadable file yields ``{}`` — a valid legacy/env-only configuration.

    Only a REGULAR file is read. ``ADLC_CONFIG`` is caller-controlled, and
    ``os.path.isfile``-style existence checks say nothing about the kind of
    object: pointing it at a fifo would block ``open()`` forever (a ``--version``
    that never returns), and a device node would stream unbounded input. The read
    is bounded too — a config with three scalar fields has no business being
    larger than 64 KiB, and the parser must not be a memory amplifier.
    """
    if path is None:
        path = _config_path()
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            return {}
    except OSError:
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read(65536).splitlines()
    except OSError:
        return {}

    known = {"enabled", "base_url", "model", "api_key_env"}
    out = {}
    in_block = False
    block_indent = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if not in_block:
            if stripped.rstrip() == "delegate:" and indent == 0:
                in_block = True
            continue
        # Inside the delegate block: a key at deeper indent than `delegate:`.
        if indent == 0:
            # Dedent back to top level — block ended.
            break
        if block_indent is None:
            block_indent = indent
        if indent < block_indent:
            break
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key not in known:
            continue
        value = _strip_inline(value)
        if key == "enabled":
            out["enabled"] = value.lower() in ("true", "yes", "1", "on")
        else:
            out[key] = value
    return out


# `\Z`, never `$`: Python's `$` also matches just before a trailing newline, so
# `$'MY_KEY\n'` would pass an env-var-NAME check and then inject a blank line
# into the BR-9 report. `\Z` is the true end of string.
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")
# Allow-list for the RESOLVED api_key_env (BR-3). Deliberately narrower than
# `_ENV_VAR_NAME_RE`: a key-env var name is SCREAMING_SNAKE_CASE by universal
# convention, so anything else is presumed to be a key value that the key-family
# blocklist happened not to recognize (gsk_…, hf_…, and every vendor prefix
# invented after this file was written).
_KEY_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*\Z")
# Key-shaped families the redaction chain already knows, plus a generic
# high-entropy run (>=32 chars, mixed classes) — see REQ-515 ADR-4 / BR-3.
# The AWS access-key-ID family needs every prefix, not just AKIA: an ID is 20
# uppercase alphanumerics with no underscore, so it satisfies the
# UPPER_SNAKE_CASE allow-list AND is too short for the 24-char underscore-free
# heuristic — the blocklist is the only layer that can refuse it.
_KEYISH_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}"
    r"|(?:AKIA|ASIA|ABIA|ACCA|AIPA|ANPA|AROA)[A-Z0-9]{16}"
    r"|ghp_[A-Za-z0-9]{36,}"
    r"|Bearer\s+[A-Za-z0-9._-]{20,})"
)


def _looks_like_key(value):
    """True if ``value`` looks like an actual key rather than an env-var NAME.

    BR-3: the config stores ``api_key_env`` — the *name* of an env var — never a
    key. A value that matches a known key family, that is a long mixed-class
    token without an underscore (the key signature — real env var names use
    SCREAMING_SNAKE_CASE), or that simply isn't a valid env-var name, is treated
    as a key.
    """
    if not value:
        return False
    # Known key families (sk-…, AKIA…, ghp_…, Bearer …).
    if _KEYISH_RE.search(value):
        return True
    # A long alphanumeric run with NO underscore that mixes letters and digits
    # is almost certainly a key, even though it happens to be a syntactically
    # valid env-var name. Real key-VAR names use underscores (MY_API_KEY), so an
    # underscore-free 24+ char letters+digits blob is the key itself. Check this
    # BEFORE accepting on env-var-name shape.
    if len(value) >= 24 and "_" not in value and " " not in value \
            and re.search(r"[A-Za-z]", value) and re.search(r"[0-9]", value):
        return True
    # Otherwise a syntactically valid env-var name is accepted as a NAME.
    if _ENV_VAR_NAME_RE.match(value):
        return False
    # Anything else (spaces, punctuation, not a valid name) is rejected — the
    # field is contractually a NAME.
    return True


class Provider:
    """Resolved delegation provider. ``api_key`` is resolved lazily by callers
    that actually need the network (so --dry-run / guard paths never touch it).
    """

    __slots__ = ("base_url", "model", "api_key_env", "enabled", "source")

    def __init__(self, base_url, model, api_key_env, enabled, source):
        self.base_url = base_url
        self.model = model
        self.api_key_env = api_key_env
        self.enabled = enabled
        self.source = source


def _legacy_key_present():
    """True if either legacy key var is set and non-empty in the environment."""
    return any(os.environ.get(v) for v in _LEGACY_KEY_VARS)


def delegation_enabled(cfg=None):
    """BR-11 opt-in: delegation is OFF by default on fresh installs.

    Resolved in the SAME precedence order as the provider fields (BR-2), which
    ``enabled`` previously did not follow (BUG-205):

      0. ``ADLC_DISABLE_DELEGATE=1`` in the environment      → DISABLED, always
      1. ``ADLC_DELEGATE_ENABLED=1`` in the environment      → enabled
      2. ``delegate.enabled`` in the config file, if PRESENT → decisive, either way
      3. a legacy key (``KIMI_API_KEY``/``MOONSHOT_API_KEY``) → enabled (continuity)
      4. otherwise                                           → disabled

    Step 0 is the kill switch, and it outranks every other arm including an
    explicit ``ADLC_DELEGATE_ENABLED=1`` — matching ``delegate-gate.sh``, which
    tests it before the opt-in cascade and returns ``disabled-via-env``. Until
    BUG-209 this arm did not exist in Python at all: the switch was implemented
    only in the shell gate, which is **vendored per repo**, so a repo carrying a
    stale ``.adlc/partials/delegate-gate.sh`` — or any direct CLI call — walked
    straight past a documented emergency stop and transmitted file contents.

    That is the same structural defect BUG-206 fixed for ``enabled``, missed for
    the one control whose entire purpose is to be reachable when something has
    already gone wrong. A kill switch that lives only in the copied layer is not
    a kill switch.

    Step 2 is three-state on purpose. ``parse_delegate_config`` records
    ``enabled`` only when the key actually appears, so ``None`` (absent) is
    distinguishable from ``False`` (written down). Absence is a default and
    yields to the continuity exception below it; an explicit ``false`` is an
    operator instruction and outranks it.

    That distinction is the whole of BUG-205. The continuity exception in BR-11
    was specified for pre-config installs — where ``enabled`` is absent — but was
    implemented as a flat OR that also swallowed an explicit ``enabled: false``.
    Since REQ-519 ``install.sh`` scaffolds a config containing exactly that line,
    so any install with a legacy key exported had delegation on while its config
    said off, and file contents were transmitted after the operator wrote down
    that they must not be.

    Setting only ``ADLC_DELEGATE_BASE_URL``/``_MODEL`` is NOT opt-in.
    """
    if cfg is None:
        cfg = parse_delegate_config()
    # Kill switch first: it outranks every arm below, opt-in env var included.
    # Exact "1" only, matching delegate-gate.sh's `[ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]`
    # so the two layers cannot disagree about what counts as set.
    if os.environ.get("ADLC_DISABLE_DELEGATE") == "1":
        return False
    if os.environ.get("ADLC_DELEGATE_ENABLED") == "1":
        return True
    configured = cfg.get("enabled")
    if configured is not None:
        return configured
    if _legacy_key_present():
        return True
    return False


# The gate's full reason vocabulary (REQ-603 BR-4). The probe produces only the
# first four; `no-binary` and `unset` are the shell gate's alone — an unresolvable
# binary cannot be asked anything, and `unset` is the pre-call initial value.
GATE_REASONS = ("ok", "disabled-via-env", "disabled-via-config", "not-opted-in")
_GATE_ONLY_REASONS = ("no-binary", "unset")


def resolve_gate_verdict(cfg=None):
    """Return ``(enabled, reason)`` — the single authority for delegation opt-in.

    REQ-603 BR-1: the shell gate may *withhold* delegation (no-binary, veto) but
    may never *grant* it. Every path on which the gate concludes "delegated"
    resolves here.

    Two properties are easy to lose and load-bearing:

    1. **It resolves the provider, not merely the opt-in cascade.** LESSON-392:
       an enablement probe that checks a cheaper subset than the real call
       green-lights delegation that then fails on the first API call, mislabelled
       as a runtime error. ``resolve_provider`` raises ``SystemExit`` for a
       key-in-config config; that refusal is a *config* reason, not "not opted
       in", and callers need to be told which.
    2. **`enabled: false` is decisive regardless of a legacy key** (REQ-603 BR-4 /
       architecture ADR-4). The shell heuristic this replaces never read
       ``enabled`` at all — it reported ``disabled-via-config`` only when a config
       file existed *and* a legacy key happened to be exported, so the same
       written instruction produced two different labels depending on an
       unrelated variable. The label is corrected here; the return code the gate
       derives from it is unchanged.
    """
    if cfg is None:
        cfg = parse_delegate_config()

    # Step 0 — the kill switch, ahead of every authorizing arm (BUG-209).
    if os.environ.get("ADLC_DISABLE_DELEGATE") == "1":
        return False, "disabled-via-env"

    # An explicit `enabled: false` is an instruction, not an absent default. It
    # outranks the legacy key (BUG-205) and names itself (ADR-4).
    if cfg.get("enabled") is False:
        return False, "disabled-via-config"

    if not delegation_enabled(cfg):
        return False, "not-opted-in"

    # Opted in — but only "enabled" if the real call could actually run. Share
    # the real call's resolution rather than a cheaper subset (LESSON-392).
    try:
        resolve_provider(cfg=cfg)
    except SystemExit:
        return False, "disabled-via-config"
    return True, "ok"


def require_delegation_enabled(prog, cfg=None):
    """Refuse to transmit when delegation is not opted in (BUG-206).

    The shell gate (``partials/delegate-gate.sh``) is supposed to stop a
    delegating skill before it ever reaches a CLI invocation. But that gate is
    **vendored per repo** — skills source ``.adlc/partials/delegate-gate.sh``
    ahead of the toolkit copy — so a repo carrying a stale vendored copy calls
    straight through a correct opt-out, and nothing downstream objects. Until
    this guard existed, ``enabled`` was consulted only by ``--print-enabled``:
    the flag that governs whether file contents may leave the machine was read
    exclusively by the probe, never by the code path that does the leaving.

    A governance control cannot live only in a layer that gets copied around.
    This is the backstop in the one place that is not copied — and it is what
    makes vendored-gate staleness a correctness problem rather than a
    data-governance one.

    Exits non-zero with an actionable message. Delegating skills already treat a
    non-zero exit as "fall back and read directly" (BR-4), so a refusal here
    degrades exactly like a missing binary rather than breaking the caller.
    """
    if delegation_enabled(cfg):
        return
    # Name the kill switch when it is the cause. Telling someone to enable
    # delegation when they just set ADLC_DISABLE_DELEGATE=1 is advice against
    # their own stated intent — and it reads as the switch having been ignored,
    # which is precisely the bug this branch fixes (BUG-209). Mirrors the gate's
    # disabled-via-env / not-opted-in split.
    if os.environ.get("ADLC_DISABLE_DELEGATE") == "1":
        sys.exit(
            "%s: delegation disabled via ADLC_DISABLE_DELEGATE — refusing to send "
            "file contents to a third-party endpoint.\n"
            "Unset it to restore the configured behaviour (`%s --version` prints "
            "the resolved value)." % (prog, prog)
        )
    sys.exit(
        "%s: delegation is not enabled — refusing to send file contents to a "
        "third-party endpoint.\n"
        "Enable it with `delegate.enabled: true` in ~/.claude/adlc/config.yml, or "
        "ADLC_DELEGATE_ENABLED=1 in the environment.\n"
        "(`%s --version` prints the resolved value. ADLC_DISABLE_DELEGATE=1 forces "
        "it off regardless.)" % (prog, prog)
    )


def resolve_provider(args_model=None, args_base_url=None, cfg=None):
    """Resolve the provider via the BR-2 precedence cascade.

    Highest precedence wins, per field. Raises ``SystemExit`` (BR-3) if the
    config's ``api_key_env`` — or the value the whole cascade RESOLVES to,
    including the ``ADLC_DELEGATE_API_KEY_ENV`` override — holds a key value
    rather than an env-var name.
    """
    if cfg is None:
        cfg = parse_delegate_config()

    # api_key_env: env var override > config > legacy default. Validate config.
    cfg_key_env = cfg.get("api_key_env")
    if cfg_key_env is not None and _looks_like_key(cfg_key_env):
        raise SystemExit(
            "config 'delegate.api_key_env' must be the NAME of an environment "
            "variable (e.g. MY_PROVIDER_KEY), not a key value. The key itself "
            "must never be stored in the config file."
        )
    api_key_env = (
        os.environ.get("ADLC_DELEGATE_API_KEY_ENV")
        or cfg_key_env
        or _DEFAULT_API_KEY_VAR
    )
    # Validate what the cascade actually RESOLVED to, not just the config branch:
    # `ADLC_DELEGATE_API_KEY_ENV` outranks the config and was previously
    # unchecked, so a key pasted there reached `os.environ.get(<the key>)` and
    # could be echoed back by any diagnostic that prints the NAME. The allow-list
    # also catches vendor key prefixes the key-family blocklist doesn't know.
    # The refusal message is a constant — the rejected value is NEVER
    # interpolated, because the value is exactly what may be a live secret.
    if _looks_like_key(api_key_env) or not _KEY_ENV_NAME_RE.match(api_key_env):
        raise SystemExit(
            "resolved 'api_key_env' must be an UPPER_SNAKE_CASE environment "
            "variable NAME (e.g. MY_PROVIDER_KEY); never a key value — set it "
            "via config api_key_env or ADLC_DELEGATE_API_KEY_ENV"
        )

    # base_url: flag > ADLC_DELEGATE_BASE_URL > config > default.
    base_url = (
        args_base_url
        or os.environ.get("ADLC_DELEGATE_BASE_URL")
        or cfg.get("base_url")
        or _DEFAULT_BASE_URL
    )

    # model: flag > ADLC_DELEGATE_MODEL > config > default.
    # (REQ-522 ADR-5: the legacy KIMI_MODEL read is dropped — it was a branded
    # non-key env var, not key-continuity data. Use ADLC_DELEGATE_MODEL.)
    model = (
        args_model
        or os.environ.get("ADLC_DELEGATE_MODEL")
        or cfg.get("model")
        or _DEFAULT_MODEL
    )

    # source: a coarse label for diagnostics (not part of the contract).
    if args_model or args_base_url:
        source = "flags"
    elif os.environ.get("ADLC_DELEGATE_BASE_URL") or os.environ.get("ADLC_DELEGATE_MODEL"):
        source = "env"
    elif cfg:
        source = "config"
    else:
        source = "defaults"

    return Provider(base_url, model, api_key_env, delegation_enabled(cfg), source)


# --- `--version` reporting (shared by all three CLIs) ----------------------

def wants_version(argv, value_flags=frozenset(), known_flags=None):
    """True if ``--version``/``-V`` appears in argv in FLAG position.

    ``argv`` may be ``None``, in which case ``sys.argv[1:]`` is scanned. The scan
    is value-aware: a token that is the value of a preceding option in
    ``value_flags`` is skipped, so ``--question -V`` asks a question *about* the
    string ``-V`` instead of printing the version. Scanning stops at ``--``, and
    an attached form (``--question=--version``) can never match because the
    comparison is whole-token equality.

    ``known_flags`` — every option spelling the CLI's parser declares — closes
    the last gap. Without it the scan silently assumes any token it does not
    recognize is harmless, so ``--sp "--version"`` (a prefix ABBREVIATION of
    ``--spec`` back when the parsers allowed them) put ``--version`` in what the
    scan read as flag position: the CLI printed the version, exited 0, and did
    nothing the user asked for. Now an unrecognized option token makes the scan
    decline, handing the argv to argparse so it can raise its own error. This is
    only sound because the parsers set ``allow_abbrev=False``: the declared
    spellings are then the ONLY accepted spellings, so a fixed set is provably
    complete. Omitting ``known_flags`` keeps the older, weaker behavior.

    Known limitation: an option with ``nargs='+'`` (``--paths``) consumes an
    unbounded number of values, so only its first value is skipped. A
    dash-prefixed token among the remaining values would still be seen in flag
    position — but argparse rejects such an argv anyway ("expected one
    argument" / "unrecognized arguments"), so the case is unreachable in any
    invocation that could otherwise have succeeded.
    """
    effective = argv if argv is not None else sys.argv[1:]
    skip_next = False
    for token in effective:
        if token == "--":
            return False
        if skip_next:
            skip_next = False
            continue
        if token in ("--version", "-V"):
            return True
        if token in value_flags:
            skip_next = True
            continue
        if known_flags is not None and len(token) > 1 and token.startswith("-"):
            # Attached form: `--model=x` is the option `--model`.
            if token.split("=", 1)[0] not in known_flags:
                return False
    return False


def harvest_provider_flags(argv, value_flags=frozenset()):
    """Extract ``--model`` / ``--base-url`` from a raw argv, pre-argparse.

    The ``--version`` path prints the config a REAL call would resolve, and per
    BR-3 that includes the per-invocation flag overrides — which argparse never
    gets to see on this path (ADR-1). Both the separated (``--model x``) and
    attached (``--model=x``) forms are recognized; the scan stops at ``--``.
    Returns ``(model, base_url)``, each ``None`` when not supplied.

    Value-aware in the same way as :func:`wants_version`, and given the SAME
    ``value_flags`` set by every caller: without it, ``--question --model``
    would harvest nothing but ``--question --model foo`` would harvest ``foo``
    as the model, reporting a provider the real call would never use. An empty
    value (``--model=``) counts as not-supplied, matching the ``or``-chain
    fallthrough in :func:`resolve_provider`.
    """
    effective = argv if argv is not None else sys.argv[1:]
    model = None
    base_url = None
    pending = None
    skip_next = False
    for token in effective:
        if token == "--":
            break
        if skip_next:
            skip_next = False
            continue
        if pending is not None:
            if pending == "--model":
                model = token or None
            else:
                base_url = token or None
            pending = None
            continue
        # `--model`/`--base-url` are themselves members of `value_flags`, so they
        # must be matched BEFORE the generic skip branch below.
        if token in ("--model", "--base-url"):
            pending = token
        elif token.startswith("--model="):
            model = token[len("--model="):] or None
        elif token.startswith("--base-url="):
            base_url = token[len("--base-url="):] or None
        elif token in value_flags:
            skip_next = True
    return model, base_url


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_report_value(v):
    """Flatten ``v`` to a single line of printable text for the BR-9 report.

    Every value in the report comes from argv, the environment, or a config
    file — all caller-controlled — and the report's whole value as a contract is
    that one line means one field. A newline in a model name would otherwise let
    ``--model=$'fake\\nenabled: false'`` forge an ``enabled:`` line, and an ESC
    byte would let it repaint the terminal. Whitespace (of every kind) collapses
    to single spaces; anything still in the C0/C1-adjacent control range is
    dropped outright.
    """
    return _CONTROL_CHARS_RE.sub("", " ".join(str(v).split()))


# Syntactic userinfo prefix: an optional `scheme://` (or bare `//`), then any
# run without `/`, `@`, or whitespace, then `@`. Deliberately looser than RFC
# 3986 so it also matches the strings `urlsplit` REFUSES to parse — that is the
# whole point (see `_redact_url_userinfo`). It over-matches at worst, which
# redacts something harmless rather than printing something secret.
_USERINFO_PREFIX_RE = re.compile(
    r"^((?:[A-Za-z][A-Za-z0-9+.\-]*:)?//)?[^/@\s]+@"
)

# Returned instead of the input when the URL cannot be parsed at all. A constant:
# it carries no caller state, so it cannot leak anything (LESSON-021).
_UNREDACTABLE = "<unredactable>"


def _redact_url_userinfo(url):
    """Return ``url`` with any ``user:pass@`` userinfo replaced by ``***@``.

    A base URL can legitimately carry credentials, and ``--version`` is the one
    path that PRINTS it. Applied on the print path only — never to the value
    handed to ``get_client``, which needs the credentials intact.

    **Fail-closed.** The userinfo is stripped SYNTACTICALLY first, before
    ``urlsplit`` is consulted, because ``urlsplit`` refuses some strings
    outright — ``https://user:pw@[::1/v1`` (unterminated IPv6 literal) raises
    ``ValueError``, and returning the input unchanged on that path printed the
    password verbatim. The parser-based pass still runs afterwards for
    well-formed URLs (it normalizes the netloc); if it raises even on the
    already-stripped string, a constant is returned rather than any form of the
    caller's value.
    """
    text = str(url)
    stripped = _USERINFO_PREFIX_RE.sub(
        lambda m: (m.group(1) or "") + "***@", text, count=1)
    from urllib.parse import urlsplit, urlunsplit
    try:
        parts = urlsplit(stripped)
        if parts.username is None and parts.password is None:
            return stripped
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit(
            (parts.scheme, "***@" + host, parts.path, parts.query, parts.fragment)
        )
    except ValueError:
        return _UNREDACTABLE


def _endpoint_host(base_url):
    """Display-safe host of ``base_url`` — userinfo-redacted, single-line.

    Redaction happens FIRST, so a credential-bearing base URL never reaches the
    parser (or the output) intact. Falls back to the whole redacted string when
    there is no netloc to extract (a scheme-less or unparseable value), which is
    still safe by construction.
    """
    safe = _redact_url_userinfo(base_url)
    from urllib.parse import urlsplit
    try:
        netloc = urlsplit(safe).netloc
    except ValueError:
        netloc = ""
    return _clean_report_value(netloc or safe)


def version_report_lines(args_model=None, args_base_url=None, include_config=True):
    """The BR-9 ``--version`` output, as a list of lines.

    This is the ONLY implementation of the BR-9 contract — the three CLIs differ
    only in which ``value_flags`` they pass to :func:`wants_version` and whether
    they ask for the config block, so the format cannot drift between them.

    ``include_config=False`` yields the version line alone (``extract-chat`` has
    no delegate config). Otherwise the config is produced by the same
    :func:`resolve_provider` a real call uses (BR-3, LESSON-392); a refusal
    degrades to one flattened ``config_error:`` line instead of a traceback
    (BR-6). Those messages are path-free, value-free constants by construction
    (LESSON-021) — nothing here re-introduces caller state into the output.

    EVERY interpolated value goes through :func:`_clean_report_value`. The
    version token, the model, and the key-var name are all caller-influenced
    (VERSION file, argv, environment, config file), and "one line per field" is
    the entire BR-9 contract: an un-flattened value could forge a field a
    consumer would then trust. ``enabled`` is the one literal here, so it needs
    no sanitizing — and is therefore also the one field that must never be
    forgeable from any of the others.
    """
    lines = ["adlc-toolkit %s" % _clean_report_value(toolkit_version())]
    if not include_config:
        return lines
    try:
        provider = resolve_provider(
            args_model=args_model, args_base_url=args_base_url)
    except SystemExit as exc:
        lines.append("config_error: %s" % _clean_report_value(exc))
        return lines
    lines.append("base_url: %s" % _clean_report_value(
        _redact_url_userinfo(provider.base_url)))
    lines.append("model: %s" % _clean_report_value(provider.model))
    lines.append("api_key_env: %s" % _clean_report_value(provider.api_key_env))
    lines.append("enabled: %s" % ("true" if provider.enabled else "false"))
    return lines


def _read_key_from_rc(var_name):
    """Last-resort fallback: read ``export <var_name>="..."`` from rc files.

    On macOS, when Claude Code (or any GUI app) is launched before
    ``launchctl setenv`` runs, its child Bash subprocesses inherit an empty
    env — even though ``~/.zshrc`` has the export. Result: delegation silently
    falls back even though the key is present on disk. ``get_client`` falls back
    to this function, which reads the key directly from canonical rc files.
    **Does NOT source or eval** the rc file — uses a narrow awk-style extraction
    (REQ-422 / LESSON-011). Returns the key or empty string. Only applied to the
    default Moonshot var (the legacy launchctl-propagation defense); arbitrary
    provider key vars are expected to be set in the environment directly.
    """
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".zshrc"),
        os.path.join(home, ".bash_profile"),
        os.path.join(home, ".bashrc"),
    ]
    needle = f"export {var_name}="
    for rc in candidates:
        try:
            with open(rc, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    # Only match the canonical, non-indented `export VAR="..."` form.
                    if line.startswith(needle):
                        try:
                            _, after = line.split('="', 1)
                            value, _ = after.split('"', 1)
                        except ValueError:
                            continue
                        if value:
                            return value
        except OSError:
            continue
    return ""


def resolve_key(provider):
    """Return the API key for ``provider`` from the env var it names.

    Falls back to the rc-file reader only for the legacy default Moonshot var
    (preserving the macOS launchctl-propagation defense). Raises ``SystemExit``
    naming the env var if the key cannot be found. The key value is never printed.
    """
    api_key = os.environ.get(provider.api_key_env)
    if not api_key and provider.api_key_env == _DEFAULT_API_KEY_VAR:
        api_key = _read_key_from_rc(provider.api_key_env)
    if not api_key:
        hint = (
            f" and was not found in ~/.zshrc, ~/.bash_profile, or ~/.bashrc"
            if provider.api_key_env == _DEFAULT_API_KEY_VAR
            else ""
        )
        raise SystemExit(
            f"{provider.api_key_env} is not set{hint} — "
            f'add `export {provider.api_key_env}="..."` to your shell environment.'
        )
    return api_key


def get_client(provider=None):
    """Return an ``openai.OpenAI`` client pointed at the resolved endpoint."""
    if provider is None:
        provider = resolve_provider()
    api_key = resolve_key(provider)
    import openai
    return openai.OpenAI(base_url=provider.base_url, api_key=api_key)


def get_model(provider=None):
    """Return the resolved model name."""
    if provider is None:
        provider = resolve_provider()
    return provider.model


def pack_corpus(paths, *, use_basename=True):
    """Read each path and join them as ``<file path='...'>`` blocks, in order.

    Callers put files before the question so the corpus prefix can be cached.
    When ``use_basename`` is true (default), the ``path`` attribute embeds only
    ``os.path.basename(p)`` so absolute paths on the caller's machine don't
    leak to the API. Local error messages keep the full path for actionability.
    """
    blocks = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except FileNotFoundError:
            raise SystemExit(f"file not found: {p}")
        except OSError as exc:
            raise SystemExit(f"cannot read {p}: {exc}")
        attr = os.path.basename(p) if use_basename else p
        blocks.append(f"<file path='{attr}'>\n{content}\n</file>")
    return "\n\n".join(blocks)


def _strip_fences(text):
    lines = text.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        # find a trailing fence line
        end = None
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        if end is not None:
            return "\n".join(lines[1:end])
    return text


def warn_suppressed():
    """True if the privacy notice is suppressed via env.

    Honors ``ADLC_DELEGATE_NO_WARN``. The per-call ``--no-warn`` flag is checked
    by the CLIs directly. (REQ-522 ADR-5 dropped the legacy ``KIMI_NO_WARN``
    alias — a branded non-key env var, not key-continuity data.)
    """
    return os.environ.get("ADLC_DELEGATE_NO_WARN") == "1"


def emit_exfil_notice(stream=None, provider=None):
    """Write the one-line exfiltration warning to ``stream`` (default stderr).

    The text names the resolved model, the resolved endpoint HOST, and the two
    suppression mechanisms (``--no-warn`` flag, ``ADLC_DELEGATE_NO_WARN`` env
    var). The API key value/var name is never interpolated.

    The host is what makes this notice load-bearing rather than decorative: the
    whole point is "your file contents are leaving this machine", and a base URL
    hijacked through the environment or a config file changes WHERE they go
    without changing anything else the user sees. Redacted and flattened for
    display (``_endpoint_host``) so the notice cannot itself become a leak or a
    forgery vector.
    """
    if stream is None:
        stream = sys.stderr
    if provider is None:
        provider = resolve_provider()
    stream.write(
        f"delegate: sending file contents to the configured endpoint "
        f"({_clean_report_value(provider.model)} at "
        f"{_endpoint_host(provider.base_url)}). "
        "Pass --no-warn or set ADLC_DELEGATE_NO_WARN=1 to silence.\n"
    )


def _api_error_message(exc, model):
    """Turn an ``openai.APIStatusError`` into one actionable line.

    A raw traceback here reads as a local bug and sends people auditing their
    key or the SDK when the provider simply retired a model id (LESSON-334).
    """
    status = getattr(exc, "status_code", None)
    if status == 404:
        return (
            f"model {model!r} not found at the configured endpoint (404). "
            "The provider may have retired it — list the endpoint's current "
            "models and re-pin via --model, ADLC_DELEGATE_MODEL, or "
            "delegate.model in the config file."
        )
    if status in (401, 403):
        return (
            f"the delegate endpoint rejected the API key ({status}). "
            "Check that the variable named by api_key_env holds a valid key "
            "for this endpoint (adlc-read --version prints which one)."
        )
    if status == 429:
        return (
            "the delegate endpoint is rate-limiting or out of quota (429). "
            "Retry later or check your account's billing status."
        )
    return f"delegate endpoint returned {status or 'an error'}: {exc}"


def complete(client, model, messages, max_tokens):
    """Call ``chat.completions.create`` and return the content string.

    Raises ``SystemExit`` if the model returns empty/whitespace content.
    """
    # openai is already in sys.modules — get_client() imported it to build the
    # client we were handed. Keep the import local anyway so this module stays
    # importable without the SDK installed (BUG-056).
    import openai

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
    except openai.APIStatusError as exc:
        raise SystemExit(_api_error_message(exc, model)) from None
    except openai.APIConnectionError as exc:
        raise SystemExit(
            f"could not reach the delegate endpoint: {exc}. "
            "Check your network and the configured base_url."
        ) from None
    if not getattr(resp, "choices", None):
        raise SystemExit("API returned no choices — check the model id and your account quota")
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise SystemExit("empty completion — increase --max-tokens")
    return content
