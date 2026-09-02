#!/usr/bin/env python3
"""Forge config reader + provider resolution (REQ-520 BR-2/BR-6).

Reads the ``forge:`` block of the shared ADLC config through the **one loader**,
``tools/delegate/_machine_config.load_machine_config`` (REQ-609 BR-8, ADR-1), the
same call ``_common.parse_delegate_config`` reads its own section from. The flat
``key: value`` reader this replaces (REQ-515 ADR-3, "no PyYAML for three scalar
fields") was a second, independent answer to "what does this file say", so one
file could be read two ways: a multi-section config locked one consumer out by
the other's rule, and nine fail-open shapes were found in the flat reader's
delegate twin. One loader, one verdict. ADR-3 is amended by REQ-609 BR-14.

Resolves the active forge provider with precedence:

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

Nothing YAML-related is imported at module level: the loader imports PyYAML lazily
(LESSON-022 / BUG-056), so importing this module never puts a third-party package
in the import closure of a tool that has to run before that package exists — the
one thing a bootstrap diagnostic may never have (LESSON-395). The credential helpers
(:func:`looks_like_key`, :func:`validate_auth`) stay ported rather than imported:
they are policy, not parsing, and the delegate module's copies answer a different
question (an API key vs. a PAT source name).
"""

import importlib.util
import os
import re
import subprocess
import sys

SUPPORTED_PROVIDERS = ("github", "azure-devops")

#: The only ``malformed`` reason class the forge consumer tolerates (REQ-609
#: ADR-2). A missing parser is a statement about the machine's install, not
#: about the file: making every `/proceed` PR operation hostage to a delegation
#: install the operator never opted into would be a regression with no
#: governance benefit, because `forge.auth` never carries authority (a
#: key-shaped value is refused at validation, REQ-520 BR-6). Every FILE defect
#: stays whole-document and fail-loud for both consumers.
_TOLERATED_REASON = "dependency-missing"


class ForgeConfigError(Exception):
    """A forge config value is invalid (e.g. a key-shaped auth value)."""


class MalformedConfigError(ForgeConfigError):
    """The shared config exists but cannot be read (REQ-609 BR-13).

    A subclass of :class:`ForgeConfigError` so :func:`main` — and every caller
    that already catches the base class — turns it into a non-zero exit with an
    actionable message rather than a traceback. The message names the path and
    the reason class (for a duplicate key, the key and its line) and never
    advises setting an environment variable: no env var can make an unreadable
    file readable, and pointing at one sends a locked-out operator away from
    the file that is actually broken.
    """


class UnknownForgeError(Exception):
    """``auto`` resolution hit an unrecognized remote host."""


# --- the one loader (REQ-609 ADR-1), loaded by PATH not by sys.path --------

def _loader_candidates():
    """Where ``_machine_config.py`` may live, most-local first.

    Two levels, mirroring how ``partials/forge.sh`` locates *this* file (project
    copy, then the toolkit at ``~/.claude/skills``) and how
    ``checks._partial_path`` resolves partials. The second level is not
    decoration: a project may vendor ``tools/adlc/forge_config.py`` alone —
    forge.sh supports exactly that — and a vendored copy with no sibling
    ``tools/delegate/`` would otherwise read every config as unconfigured and
    silently fall back to origin-URL auto-detection, overriding the operator's
    written `forge.provider`.

    ``realpath``, not ``abspath``: for a symlinked checkout ``abspath`` walks
    from the symlink's directory and resolves wrongly (ASSUME-001's
    sharpening). The ``~/bin`` shim `exec`s this tree by absolute path, so
    script-relative resolution survives the wrapper indirection.
    """
    tools = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    cands = [os.path.join(tools, "delegate", "_machine_config.py")]
    home = os.path.expanduser("~")
    if home and home != "~":
        cands.append(os.path.join(
            home, ".claude", "skills", "tools", "delegate", "_machine_config.py"))
    return cands


#: Distinguishes "not looked for yet" from "looked for and not found", so a
#: machine without the loader pays the search once rather than on every read.
_LOADER_UNRESOLVED = object()
_loader_module = _LOADER_UNRESOLVED


def _loader():
    """The loader module, executed from an explicit path, or ``None``.

    **Why not an import.** This module used to reach its loader by inserting a
    candidate directory at ``sys.path[0]`` at import time and then ``import
    _machine_config``. One of those candidates is derived from ``$HOME``, and
    ``sys.path[0]`` shadows the standard path for *every* later import in the
    process — including the lazy ``import yaml`` the loader itself depends on,
    and every import made afterwards by whatever tool imported this module. A
    module dropped into that directory (a stale vendored tree, a shared
    checkout, anyone who can write there) would be executed in preference to
    the real one. Loading a named file by explicit path answers the same
    question and shadows nothing.

    The module is deliberately NOT registered in ``sys.modules``: registering
    it would make this consumer's copy depend on import order relative to
    ``_common``'s ordinary ``import _machine_config``, and the point of loading
    by path is to be independent of what else the process has imported.

    Resolved once and cached — ``resolve_provider`` parses two configs on one
    call, and re-executing the module each time would also reset its
    once-per-process stderr dedupe (BR-9's "one line").
    """
    global _loader_module
    if _loader_module is not _LOADER_UNRESOLVED:
        return _loader_module
    _loader_module = None
    for path in _loader_candidates():
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("_machine_config", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            # A loader that will not execute is the same install-defect CLASS
            # as one that is not there (and as an interpreter without PyYAML):
            # the machine cannot parse the file, which says nothing about the
            # file. Broad on purpose — an exec_module failure may be anything —
            # and it degrades to the `dependency-missing` behaviour below, one
            # named stderr line included, never to a silent success.
            continue
        _loader_module = module
        break
    return _loader_module


_dependency_notice_emitted = False


def _note_dependency_missing():
    """Write the one stderr line for "this machine cannot parse the config".

    Once per process, not once per read: :func:`resolve_provider` parses two
    configs on a single call, and two identical lines read as two problems. The
    loader's own emitter already dedupes, so in the normal path (PyYAML absent,
    loader present) this is a no-op that leaves the loader's single line
    standing (REQ-609 BR-9).
    """
    global _dependency_notice_emitted
    loader = _loader()
    if loader is not None:
        loader._emit_dependency_notice()
        return
    if _dependency_notice_emitted:
        return
    _dependency_notice_emitted = True
    sys.stderr.write(
        "adlc: the ADLC config loader (tools/delegate/_machine_config.py) was not "
        "found at %s; run install.sh\n" % " or ".join(_loader_candidates()))


# --- refusal-message sanitising (copied from _common._clean_report_value) --

#: Copied, not imported: `forge_config` must not pull `_common` into its import
#: closure (it has to load on a machine with no delegation install at all), and
#: two lines of regex are a smaller cost than that coupling. Keep the two in
#: step — the origin is `tools/delegate/_common._clean_report_value`.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_report_value(v):
    """Flatten ``v`` to a single line of printable text.

    Every value interpolated into a refusal comes from the environment
    (``$ADLC_CONFIG``), a repo path, or the loader's own reason string — all
    caller-controlled — and the refusal is printed straight onto a terminal by
    `partials/forge.sh`, which since REQ-609's verify pass no longer swallows
    this stderr. A newline in a path would let one refusal forge a second
    diagnostic line; an ESC byte would let it repaint the terminal. Whitespace
    of every kind collapses to single spaces; anything still in the control
    range is dropped.
    """
    return _CONTROL_CHARS_RE.sub("", " ".join(str(v).split()))


# --- config file paths -----------------------------------------------------

def _machine_config_path():
    """Machine config path: ``$ADLC_CONFIG`` or the default.

    Defers to the loader's spelling so the two consumers cannot drift apart
    about which file they are reading (REQ-609 BR-8); the inline fallback is
    only for the no-loader sentinel.
    """
    loader = _loader()
    if loader is not None:
        return loader.default_config_path()
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "adlc", "config.yml")


def _project_config_path(repo_dir):
    """Per-project config path under ``<repo_dir>/.adlc/config.yml``."""
    return os.path.join(repo_dir, ".adlc", "config.yml")


# --- the forge section, read through the one loader (REQ-609 BR-8) ---------

#: The keys this consumer reads. Unknown keys under ``forge:`` are IGNORED, not
#: refused — unlike the delegate schema, whose closed key set exists because an
#: ignored `enbaled: false` costs an exfiltration. `forge.auth` never carries
#: authority, and closing this section's schema is explicitly out of scope for
#: REQ-609 ("their validation stays where it is").
FORGE_KEYS = ("provider", "auth")


def parse_forge_config(path=None):
    """The ``forge:`` section of the config at ``path``, or ``{}``.

    Reads through :func:`_machine_config.load_machine_config` — the same call,
    on the same file, that the delegation opt-in is read with (REQ-609 BR-8), so
    a defect anywhere in the document is one verdict rather than two. Outcomes:

      * absent config                -> ``{}`` (nothing configured)
      * parsed, no ``forge`` section -> ``{}`` (unconfigured, not locked out)
      * parsed with a ``forge`` map  -> its ``provider``/``auth`` keys
      * ``dependency-missing``       -> ``{}`` after one stderr line (ADR-2)
      * any other ``malformed``      -> :class:`MalformedConfigError`

    The single tolerated reason is the machine's install, not the file (see
    :data:`_TOLERATED_REASON`). Every file defect — unreadable, undecodable,
    over-cap, a duplicated key ANYWHERE in the document including under
    ``delegate:``, a top level that is not a mapping — refuses here exactly as
    it refuses for the delegate consumer (REQ-609 BR-2).
    """
    if path is None:
        path = _machine_config_path()

    loader = _loader()
    if loader is None:
        _note_dependency_missing()
        return {}

    outcome = loader.load_machine_config(path)
    if outcome.kind == loader.KIND_ABSENT:
        return {}
    if outcome.kind == loader.KIND_MALFORMED:
        if outcome.reason_class == _TOLERATED_REASON:
            _note_dependency_missing()
            return {}
        raise MalformedConfigError(
            "the ADLC config at %s cannot be read (%s). Fix the file — the "
            "forge provider cannot be resolved from a config that does not "
            "parse." % (_clean_report_value(outcome.path),
                        _clean_report_value(outcome.reason)))
    return _forge_section(outcome.document, outcome.path)


def _forge_section(document, path):
    """Pick ``forge:`` out of a parsed document; refuse a shape we cannot read.

    An absent section, and a ``forge:`` header with nothing under it, are both
    ``{}`` — *unconfigured*, which resolves to ``auto`` detection. A section
    that is present but is not a mapping, or a ``provider``/``auth`` that is not
    a string, is refused rather than coerced: ``str()`` of a mapping is not what
    the operator wrote, and guessing is how a reader that skips what it does not
    understand fails open (LESSON-483).
    """
    if not document:
        return {}
    section = document.get("forge")
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise MalformedConfigError(
            "the ADLC config at %s cannot be read (not-a-mapping: the 'forge' "
            "section is not a mapping). Fix the file."
            % (_clean_report_value(path),))
    out = {}
    for key in FORGE_KEYS:
        if key not in section:
            continue
        value = section[key]
        if value is None:
            # `provider:` with nothing after it. Written but empty is the same
            # as unwritten for both fields, and the flat reader read it as "".
            continue
        if not isinstance(value, str):
            raise MalformedConfigError(
                "the ADLC config at %s cannot be read (not-a-string: "
                "'forge.%s' must be a string). Fix the file."
                % (_clean_report_value(path), key))
        out[key] = value
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
