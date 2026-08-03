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

Dependency-light by design: only ``os``, ``re``, ``subprocess``, ``sys`` from the
stdlib plus ``openai`` (``subprocess`` only to locate the repo root for
``toolkit_version``; ``urllib.parse`` is imported inside
``_redact_url_userinfo`` to keep the module-import surface at four names).
``openai`` is imported lazily inside ``get_client`` /
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
import subprocess
import sys

# --- shipped defaults (today's exact Moonshot/Kimi values) ------------------
# Verified against the Moonshot/Kimi API docs (platform.kimi.ai), May 2026.
# Other valid model ids: "kimi-k2.6", "kimi-k2-thinking", "kimi-k2-turbo-preview".
_DEFAULT_API_KEY_VAR = "MOONSHOT_API_KEY"
_DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
_DEFAULT_MODEL = "kimi-k2.5"

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

    The git-derived root is only accepted when it actually *is* a toolkit
    checkout (it contains ``tools/delegate/_common.py``). Same LESSON-397 class:
    when the toolkit is vendored INSIDE another git repo, ``rev-parse`` reports
    the HOST repo's toplevel, and an unvalidated result would silently read the
    host project's ``VERSION`` file. Falling back to the walk-up in that case
    reports the vendored copy's own version, which is the one being run.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    try:
        out = subprocess.run(
            ["git", "-C", here, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.strip()
        if out and os.path.isfile(
                os.path.join(out, "tools", "delegate", "_common.py")):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    # tools/delegate/_common.py -> tools/delegate -> tools -> <root>
    return os.path.dirname(os.path.dirname(here))


def toolkit_version():
    """Read the toolkit ``VERSION`` file; ``"unknown"`` if it can't be read.

    VERSION is the single source of truth — never hardcode the version here.
    Only the first line is read, bounded: a multi-line or oversized VERSION must
    not be able to forge extra ``key: value`` lines in the BR-9 report, and an
    empty file reports ``"unknown"`` rather than a blank version.
    """
    path = os.path.join(_repo_root(), "VERSION")
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline(128).strip()
    except OSError:
        return "unknown"
    return first or "unknown"


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
    """
    if path is None:
        path = _config_path()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
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


_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Allow-list for the RESOLVED api_key_env (BR-3). Deliberately narrower than
# `_ENV_VAR_NAME_RE`: a key-env var name is SCREAMING_SNAKE_CASE by universal
# convention, so anything else is presumed to be a key value that the key-family
# blocklist happened not to recognize (gsk_…, hf_…, and every vendor prefix
# invented after this file was written).
_KEY_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Key-shaped families the redaction chain already knows, plus a generic
# high-entropy run (>=32 chars, mixed classes) — see REQ-515 ADR-4 / BR-3.
_KEYISH_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}"
    r"|AKIA[A-Z0-9]{16}"
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

    Enabled iff ANY of:
      * ``delegate.enabled: true`` in the config file, OR
      * ``ADLC_DELEGATE_ENABLED=1`` in the environment, OR
      * a legacy key (``KIMI_API_KEY``/``MOONSHOT_API_KEY``) is set (continuity
        exception for today's installs).

    Setting only ``ADLC_DELEGATE_BASE_URL``/``_MODEL`` is NOT opt-in.
    """
    if cfg is None:
        cfg = parse_delegate_config()
    if cfg.get("enabled") is True:
        return True
    if os.environ.get("ADLC_DELEGATE_ENABLED") == "1":
        return True
    if _legacy_key_present():
        return True
    return False


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

def wants_version(argv, value_flags=frozenset()):
    """True if ``--version``/``-V`` appears in argv in FLAG position.

    ``argv`` may be ``None``, in which case ``sys.argv[1:]`` is scanned. The scan
    is value-aware: a token that is the value of a preceding option in
    ``value_flags`` is skipped, so ``--question -V`` asks a question *about* the
    string ``-V`` instead of printing the version. Scanning stops at ``--``, and
    an attached form (``--question=--version``) can never match because the
    comparison is whole-token equality.

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
    return False


def harvest_provider_flags(argv):
    """Extract ``--model`` / ``--base-url`` from a raw argv, pre-argparse.

    The ``--version`` path prints the config a REAL call would resolve, and per
    BR-3 that includes the per-invocation flag overrides — which argparse never
    gets to see on this path (ADR-1). Both the separated (``--model x``) and
    attached (``--model=x``) forms are recognized; the scan stops at ``--``.
    Returns ``(model, base_url)``, each ``None`` when not supplied.
    """
    effective = argv if argv is not None else sys.argv[1:]
    model = None
    base_url = None
    pending = None
    for token in effective:
        if token == "--":
            break
        if pending is not None:
            if pending == "--model":
                model = token
            else:
                base_url = token
            pending = None
            continue
        if token in ("--model", "--base-url"):
            pending = token
        elif token.startswith("--model="):
            model = token[len("--model="):]
        elif token.startswith("--base-url="):
            base_url = token[len("--base-url="):]
    return model, base_url


def _redact_url_userinfo(url):
    """Return ``url`` with any ``user:pass@`` userinfo replaced by ``***@``.

    A base URL can legitimately carry credentials, and ``--version`` is the one
    path that PRINTS it. Applied on the print path only — never to the value
    handed to ``get_client``, which needs the credentials intact. A URL that
    cannot be split is returned unchanged (there is nothing to redact if there
    is nothing parseable).
    """
    from urllib.parse import urlsplit, urlunsplit
    try:
        parts = urlsplit(url)
        if parts.username is None and parts.password is None:
            return url
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit(
            (parts.scheme, "***@" + host, parts.path, parts.query, parts.fragment)
        )
    except ValueError:
        return url


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
    """
    lines = ["adlc-toolkit %s" % toolkit_version()]
    if not include_config:
        return lines
    try:
        provider = resolve_provider(
            args_model=args_model, args_base_url=args_base_url)
    except SystemExit as exc:
        lines.append("config_error: %s" % " ".join(str(exc).split()))
        return lines
    lines.append("base_url: %s" % _redact_url_userinfo(provider.base_url))
    lines.append("model: %s" % provider.model)
    lines.append("api_key_env: %s" % provider.api_key_env)
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

    The text names the resolved model and the two suppression mechanisms
    (``--no-warn`` flag, ``ADLC_DELEGATE_NO_WARN`` env var).
    The API key value/var name is never interpolated.
    """
    if stream is None:
        stream = sys.stderr
    if provider is None:
        provider = resolve_provider()
    stream.write(
        f"delegate: sending file contents to the configured endpoint "
        f"({provider.model}). Pass --no-warn or set ADLC_DELEGATE_NO_WARN=1 "
        "to silence.\n"
    )


def complete(client, model, messages, max_tokens):
    """Call ``chat.completions.create`` and return the content string.

    Raises ``SystemExit`` if the model returns empty/whitespace content.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    if not getattr(resp, "choices", None):
        raise SystemExit("API returned no choices — check the model id and your account quota")
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise SystemExit("empty completion — increase --max-tokens")
    return content
