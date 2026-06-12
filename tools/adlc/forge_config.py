#!/usr/bin/env python3
"""Forge config reader + provider resolution (REQ-520 BR-2/BR-6).

A thin reader for the ``forge:`` block of the shared ADLC config, mirroring
``tools/delegate/_common.parse_delegate_config`` (flat ``key: value``, NO PyYAML —
REQ-515 ADR-3). Resolves the active forge provider with precedence:

    per-project .adlc/config.yml  >  machine ~/.claude/adlc/config.yml  >  auto

``auto`` detects the provider from the ``origin`` remote URL:

    github.com                        -> github
    dev.azure.com / *.visualstudio.com -> azure-devops
    anything else                     -> fail loud (UnknownForgeError), naming the
                                         URL and the two supported providers — NEVER
                                         a silent default to GitHub (BR-2, LESSON-009)

Credential discipline (BR-6): the ``auth`` field stores a credential *source name*
only — ``gh`` (logged-in CLI), an env-var NAME holding a PAT, or ``az`` (CLI login).
A key-shaped ``auth`` value is refused via :func:`looks_like_key` (ported from
``_common._looks_like_key``) — never a key value in config.

Pure standard library; importable without the delegation venv. Deliberately keeps
NO import dependency on the delegate module (adlc must work on a skills-only checkout),
so the two small helpers are ported rather than imported — the same boundary
discipline ``checks._config_enabled`` uses via a subprocess probe.
"""

import os
import re
import subprocess

SUPPORTED_PROVIDERS = ("github", "azure-devops")


class ForgeConfigError(Exception):
    """A forge config value is invalid (e.g. a key-shaped auth value)."""


class UnknownForgeError(Exception):
    """``auto`` resolution hit an unrecognized remote host."""


# --- config file paths -----------------------------------------------------

def _machine_config_path():
    """Machine config path: ``$ADLC_CONFIG`` or the default."""
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "adlc", "config.yml")


def _project_config_path(repo_dir):
    """Per-project config path under ``<repo_dir>/.adlc/config.yml``."""
    return os.path.join(repo_dir, ".adlc", "config.yml")


# --- minimal flat-YAML reader (ported shape from parse_delegate_config) -----

def _strip_inline(value):
    """Strip surrounding quotes and a trailing `` # comment`` from a scalar."""
    value = value.strip()
    if value[:1] not in ("'", '"'):
        hashpos = value.find(" #")
        if hashpos != -1:
            value = value[:hashpos].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def parse_forge_config(path=None):
    """Parse the ``forge:`` block from the YAML config, if the file exists.

    A minimal flat ``key: value`` reader (NOT a full YAML parser — REQ-515 ADR-3).
    Reads only ``provider`` and ``auth`` under a top-level ``forge:`` mapping;
    ignores everything else. An absent/unreadable file yields ``{}`` (a valid
    auto-detect configuration). The same block-parsing loop shape as
    ``parse_delegate_config``: top-level ``forge:`` mapping, dedent ends the block.
    """
    if path is None:
        path = _machine_config_path()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return {}

    known = {"provider", "auth"}
    out = {}
    in_block = False
    block_indent = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if not in_block:
            if stripped.rstrip() == "forge:" and indent == 0:
                in_block = True
            continue
        if indent == 0:
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
        out[key] = _strip_inline(value)
    return out


# --- key-shaped value refusal (ported from _common._looks_like_key, BR-6) ---

_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KEYISH_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}"
    r"|AKIA[A-Z0-9]{16}"
    r"|ghp_[A-Za-z0-9]{36,}"
    r"|Bearer\s+[A-Za-z0-9._-]{20,})"
)
# The handful of legitimate non-env-var-name auth source names the adapter
# accepts verbatim (CLI logins). Anything else must be an env-var NAME.
_CLI_AUTH_NAMES = ("gh", "az")


def looks_like_key(value):
    """True if ``value`` looks like an actual key rather than a credential SOURCE name.

    BR-6: ``forge.auth`` is a source name — ``gh``/``az`` (CLI login) or the NAME of
    an env var holding a PAT — never a key value. Mirrors ``_common._looks_like_key``:
    a known key family, an underscore-free long mixed-class blob (the key signature),
    or a value that is neither a CLI-login name nor a valid env-var name, is a key.
    """
    if not value:
        return False
    if value in _CLI_AUTH_NAMES:
        return False
    if _KEYISH_RE.search(value):
        return True
    # Long underscore-free mixed-class blob = a key, even if a syntactically valid
    # env-var name. Real key-VAR names use SCREAMING_SNAKE_CASE (underscores).
    if len(value) >= 24 and "_" not in value and " " not in value \
            and re.search(r"[A-Za-z]", value) and re.search(r"[0-9]", value):
        return True
    if _ENV_VAR_NAME_RE.match(value):
        return False
    return True


def validate_auth(value):
    """Raise ForgeConfigError if ``value`` is key-shaped; return it otherwise."""
    if value and looks_like_key(value):
        raise ForgeConfigError(
            "forge.auth must be a credential SOURCE name (e.g. 'gh', 'az', or the "
            "NAME of an environment variable holding a PAT) — never a key value. "
            "Set forge.auth to the env-var name and put the PAT in that env var."
        )
    return value


# --- provider auto-detection from the origin URL (BR-2) --------------------

def detect_provider_from_url(url):
    """Map an ``origin`` remote URL to a provider, or raise UnknownForgeError.

    Recognizes both SSH and HTTPS forms. ``github.com`` -> github;
    ``dev.azure.com`` / ``*.visualstudio.com`` -> azure-devops; anything else
    fails loud naming the URL and the supported providers (BR-2, LESSON-009).
    """
    if not url:
        raise UnknownForgeError(
            "cannot auto-detect forge provider: no 'origin' remote URL. "
            "Set forge.provider to one of: " + ", ".join(SUPPORTED_PROVIDERS) + "."
        )
    host = _extract_host(url).lower()
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    # ADO HTTPS: dev.azure.com, <org>.visualstudio.com.
    # ADO SSH:   ssh.dev.azure.com, vs-ssh.<org>.visualstudio.com.
    if (host == "dev.azure.com" or host.endswith(".dev.azure.com")
            or host == "visualstudio.com" or host.endswith(".visualstudio.com")):
        return "azure-devops"
    raise UnknownForgeError(
        f"cannot auto-detect forge provider from origin URL '{url}' "
        f"(host '{host}'). Supported providers: {', '.join(SUPPORTED_PROVIDERS)}. "
        f"Set forge.provider explicitly in .adlc/config.yml."
    )


def _extract_host(url):
    """Best-effort host extraction from an SSH or HTTPS git remote URL."""
    u = url.strip()
    # scp-like SSH: git@host:org/repo.git
    m = re.match(r"^[A-Za-z0-9_.-]+@([^:/]+):", u)
    if m:
        return m.group(1)
    # ssh:// or https:// URL
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]+@)?([^:/]+)", u)
    if m:
        return m.group(1)
    return u


def _origin_url(repo_dir):
    """The ``origin`` remote URL for ``repo_dir``, or "" if none."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir, "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
    except (OSError, ValueError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


# --- top-level resolution (BR-2 precedence) --------------------------------

def resolve_provider(repo_dir=".", cfg_project=None, cfg_machine=None):
    """Resolve ``(provider, source)`` for ``repo_dir``.

    Precedence (BR-2): per-project config ``forge.provider`` > machine config
    ``forge.provider`` > ``auto`` detection from the origin URL. An explicit
    ``provider`` value (anything other than ``auto``) is validated against the
    supported set. ``cfg_project``/``cfg_machine`` may be injected (tests); if
    None they are read from disk. Raises UnknownForgeError on unrecognized-host
    ``auto`` and ForgeConfigError on an invalid explicit provider.
    """
    if cfg_project is None:
        cfg_project = parse_forge_config(_project_config_path(repo_dir))
    if cfg_machine is None:
        cfg_machine = parse_forge_config(_machine_config_path())

    for cfg, source in ((cfg_project, "project-config"), (cfg_machine, "machine-config")):
        provider = (cfg.get("provider") or "").strip().lower()
        if provider and provider != "auto":
            if provider not in SUPPORTED_PROVIDERS:
                raise ForgeConfigError(
                    f"forge.provider '{provider}' is not supported. "
                    f"Use one of: {', '.join(SUPPORTED_PROVIDERS)}, or 'auto'."
                )
            return provider, source

    return detect_provider_from_url(_origin_url(repo_dir)), "auto"


# --- CLI entrypoint (used by partials/forge.sh and the doctor check) -------

def main(argv=None):
    """Print the resolved provider, or an error to stderr (exit 2).

    Usage: ``forge_config.py resolve-provider [<repo-dir>]``
           ``forge_config.py validate-auth <value>``
    """
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: forge_config.py resolve-provider [repo] | "
                         "validate-auth <value>\n")
        return 2
    cmd = argv[0]
    try:
        if cmd == "resolve-provider":
            repo = argv[1] if len(argv) > 1 else "."
            provider, _source = resolve_provider(repo)
            print(provider)
            return 0
        if cmd == "validate-auth":
            validate_auth(argv[1] if len(argv) > 1 else "")
            return 0
    except (UnknownForgeError, ForgeConfigError) as exc:
        sys.stderr.write(f"forge: {exc}\n")
        return 2
    sys.stderr.write(f"forge_config.py: unknown command '{cmd}'\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
