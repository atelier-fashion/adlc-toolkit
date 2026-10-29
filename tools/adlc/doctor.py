#!/usr/bin/env python3
"""adlc doctor — read-only environment health check (REQ-519).

Doctor iterates an ordered registry of checks, each reporting PASS / FAIL / SKIP
with a copy-pasteable remediation on FAIL (BR-5). It exits non-zero **iff** any
non-skip check fails (BR-4): SKIP never contributes to failure, so inapplicable
checks (a macOS-only check on Linux, delegation checks when delegation is off)
keep the overall verdict honest (BR-6).

Doctor is also the pre-flight primitive other skills call: ``--checks id1,id2``
runs only the named subset (BR-8), the contract that lets ``/sprint`` and
``/proceed`` converge their environment probes on doctor instead of maintaining
parallel probe code.

Doctor knows which install route it is running on (REQ-669 ADR-7): the plugin
copy Claude Code loads, or the clone that ``install.sh`` symlinks into
``~/.claude``. ``Profile.route`` is derived once, here, from where this file
really is, and checks that only make sense on one route gate on it.

Pure standard library — doctor must run before/without the delegation venv.
"""

import argparse
import glob
import json
import os
import platform
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adlc_home  # noqa: E402  (stdlib only; REQ-654)
import toolkit_root  # noqa: E402  (stdlib only; needs the sys.path line above)


class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


#: The two install routes (REQ-669 InstallRoute).
ROUTE_PLUGIN = "plugin"
ROUTE_SYMLINK = "symlink"

#: The plugin's manifest name and the marketplace this repo publishes (ADR-3).
PLUGIN_NAME = "adlc"
PLUGIN_MARKETPLACE = "adlc-toolkit"

#: The ``installed_plugins.json`` schema version this doctor reads. Claude Code
#: 2.1.258 writes version 2 (REQ-669 verification.md row 13). Any other version
#: is reported as unknown, never guessed at.
_RECORD_SCHEMA = 2

#: The only install key shape this doctor accepts. A key is printed inside fix
#: commands, so anything else (a quote, ``$(``, ``;``) makes the record unknown
#: rather than reaching a command line. ``fullmatch``, so a trailing newline
#: cannot slip past the anchor.
_INSTALL_KEY = re.compile(r"adlc@[a-z0-9][a-z0-9-]*")

#: The file Claude Code leaves in a cache version it no longer uses. Such a
#: copy is not an install.
_ORPHAN_MARKER = ".orphaned_at"


def valid_install_key(key) -> bool:
    """True when ``key`` is ``adlc@<marketplace>`` in the shape fixes may print."""
    return isinstance(key, str) and _INSTALL_KEY.fullmatch(key) is not None


@dataclass
class PluginInstall:
    """What this machine records about an adlc plugin install (REQ-669 ADR-7).

    ``state`` is ``present``, ``absent`` or ``unknown``. ``unknown`` is the
    answer when a record cannot be read, has a shape this doctor does not know,
    or disagrees with the plugin cache. It is never folded into either of the
    other two (LESSON-581).

    ``roots`` are the real paths Claude Code loads the plugin from, and ``keys``
    the ``adlc@<marketplace>`` install keys, both in record order.
    """

    state: str
    roots: List[str]
    keys: List[str]
    detail: str


@dataclass
class Profile:
    """Honest machine profile (BR-6).

    ``login_shell`` is read from the password database, NOT ``$SHELL`` — ``$SHELL``
    reflects the shell that happens to be invoking us, which may differ from the
    user's real login shell (e.g. a bash subshell under a zsh login).

    ``route`` is ``plugin`` or ``symlink`` (:func:`detect_route`). It defaults to
    ``symlink`` so a profile built by hand keeps today's behavior (BR-3);
    :func:`build_profile` always derives it.

    ``plugin`` is the plugin-install reading :func:`build_profile` made, so the
    checks that need it share one reading instead of repeating it. ``None`` on
    a profile built by hand, and a check then reads it itself.

    ``route_error`` is non-empty when route detection raised. ``route`` is then
    ``symlink``, so every check runs, but it is a fallback, not a finding:
    ``plugin-route`` FAILs saying so, and no check prints ``install.sh`` as a
    fix, since on a plugin machine it would double the install (BR-11).
    """

    os: str            # "Darwin" | "Linux" | other platform.system() value
    login_shell: str   # absolute path to the login shell, or "" if undetermined
    repo_root: str     # toolkit root this doctor runs from
    route: str = ROUTE_SYMLINK
    plugin: Optional[PluginInstall] = None
    route_error: str = ""


def _claude_dir() -> str:
    """Where Claude Code keeps its plugins: ``$CLAUDE_CONFIG_DIR``, else ``~/.claude``.

    Claude Code reads its configuration directory from ``CLAUDE_CONFIG_DIR``
    when that is set, and the plugin cache, ``installed_plugins.json`` and
    ``known_marketplaces.json`` live under it. Reading ``~/.claude`` there
    instead finds no plugin, so a plugin user would get ``route=symlink`` and
    be told to run install.sh. Only an absolute value is honoured: a relative
    one would depend on the directory the doctor was started in.

    This directory is for the plugin signals only. The pointer and the symlink
    install stay under ``~/.claude``, where the SessionStart hook and install.sh
    write them, and the machine config under ``ADLC_HOME`` (REQ-654).
    """
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if configured and os.path.isabs(configured):
        return configured
    return os.path.join(os.path.expanduser("~"), ".claude")  # adlc-home: claude-code


def _claude_dir_label() -> str:
    """How reports spell :func:`_claude_dir`, without the expanded home path."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "")
    return "$CLAUDE_CONFIG_DIR" if configured and os.path.isabs(configured) else "~/.claude"  # adlc-home: claude-code


def _read_json(path: str):
    """``(value, "")`` for a readable JSON file, else ``(None, reason)``.

    The reason is ``absent`` when nothing is at ``path``. Errors are reported
    by kind only, without the absolute path ``OSError`` embeds (LESSON-021).
    """
    if not os.path.lexists(path):
        return None, "absent"
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), ""
    except OSError as exc:
        return None, exc.strerror or "unreadable"
    except (ValueError, UnicodeDecodeError) as exc:
        return None, "not JSON: %s" % (exc,)


def plugin_manifest(root: str) -> Optional[dict]:
    """``<root>/.claude-plugin/plugin.json`` when it is an object naming adlc."""
    data, _err = _read_json(os.path.join(root, ".claude-plugin", "plugin.json"))
    if isinstance(data, dict) and data.get("name") == PLUGIN_NAME:
        return data
    return None


def _cache_dir() -> str:
    return os.path.join(_claude_dir(), "plugins", "cache")


def _cache_copies() -> List[Tuple[str, str]]:
    """``(key, real root)`` for each ``cache/<marketplace>/adlc/<version>/`` copy.

    A copy counts only when its ``plugin.json`` names adlc and it carries no
    ``.orphaned_at``, the marker Claude Code leaves in a version it no longer
    uses. The cache prefix is escaped before it goes into the pattern, because
    it derives from ``$HOME`` and ``glob`` reads ``[``, ``*`` and ``?`` there as
    syntax.
    """
    pattern = os.path.join(glob.escape(_cache_dir()), "*", PLUGIN_NAME, "*")
    copies = []
    for path in sorted(glob.glob(pattern)):
        if os.path.lexists(os.path.join(path, _ORPHAN_MARKER)):
            continue
        if os.path.isdir(path) and plugin_manifest(path) is not None:
            marketplace = os.path.basename(os.path.dirname(os.path.dirname(path)))
            copies.append(("%s@%s" % (PLUGIN_NAME, marketplace), os.path.realpath(path)))
    return copies


def _local_marketplace_root(marketplace: str) -> Optional[str]:
    """Real path a local-path marketplace runs adlc from, else ``None``.

    A plugin from a ``directory`` marketplace runs from its source directory,
    not from the cache copy that is also written (verification.md row 12, E4,
    and N3). The marketplace's own ``marketplace.json`` names the plugin's
    source relative to that directory. Anything unreadable gives ``None``, and
    the caller falls back to the recorded ``installPath``.
    """
    known, _err = _read_json(os.path.join(_claude_dir(), "plugins", "known_marketplaces.json"))
    entry = known.get(marketplace) if isinstance(known, dict) else None
    if not isinstance(entry, dict):
        return None
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "directory":
        return None
    for base in (entry.get("installLocation"), source.get("path")):
        if not isinstance(base, str) or not os.path.isabs(base):
            continue
        manifest, _err = _read_json(os.path.join(base, ".claude-plugin", "marketplace.json"))
        plugins = manifest.get("plugins") if isinstance(manifest, dict) else None
        for plugin in plugins if isinstance(plugins, list) else []:
            if isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME \
                    and isinstance(plugin.get("source"), str):
                return os.path.realpath(os.path.join(base, plugin["source"]))
    return None


def _unknown(detail: str) -> PluginInstall:
    return PluginInstall("unknown", [], [], detail)


def detect_plugin_install() -> PluginInstall:
    """Read this machine's adlc plugin install from its two signals.

    The signals are the install record, ``plugins/installed_plugins.json``,
    and the plugin cache, ``plugins/cache/*/adlc/*/``, both under
    :func:`_claude_dir`. The record is preferred when it exists. When there is
    no record, the cache alone answers. A well-formed record with no adlc
    entry is ``absent`` whatever the cache holds: ``claude plugin uninstall``
    leaves the cache copies behind, so they are reported as leftovers, not as
    a conflict. A record that cannot be read, has an unknown schema, or holds
    an adlc entry this doctor cannot use is ``unknown`` (REQ-669 TASK-128,
    LESSON-581). Only the record's ``installPath`` names the live copy, because
    older versions stay in the cache after an update (verification.md rows 12
    and 13).
    """
    record_path = os.path.join(_claude_dir(), "plugins", "installed_plugins.json")
    record_name = _claude_dir_label() + "/plugins/installed_plugins.json"
    copies = _cache_copies()
    data, err = _read_json(record_path)
    if err == "absent":
        if not copies:
            return PluginInstall(
                "absent", [], [],
                "no %s and no adlc copy in the plugin cache" % record_name)
        bad = [k for k, _r in copies if not valid_install_key(k)]
        if bad:
            return _unknown("the plugin cache holds an adlc copy under %r, which is not "
                            "an adlc@<marketplace> install key" % bad[0])
        keys = _unique(k for k, _r in copies)
        roots = _unique(r for _k, r in copies)
        return PluginInstall(
            "present", roots, keys,
            "%s in the plugin cache at %s, with no %s to cross-check"
            % (", ".join(keys), ", ".join(roots), record_name))
    if err:
        return _unknown("%s cannot be read (%s)" % (record_name, err))
    if not isinstance(data, dict) or data.get("version") != _RECORD_SCHEMA \
            or not isinstance(data.get("plugins"), dict):
        version = data.get("version") if isinstance(data, dict) else None
        return _unknown("%s is not the version-%d shape this doctor reads (version: %r)"
                        % (record_name, _RECORD_SCHEMA, version))
    entries = []
    for key, records in data["plugins"].items():
        if not isinstance(key, str) or key.split("@", 1)[0] != PLUGIN_NAME:
            continue
        if not valid_install_key(key):
            return _unknown("%s entry %r is not an adlc@<marketplace> install key"
                            % (record_name, key))
        if not isinstance(records, list) or not records:
            return _unknown("%s entry %s is not a list of installs" % (record_name, key))
        for rec in records:
            path = rec.get("installPath") if isinstance(rec, dict) else None
            if not isinstance(path, str) or not os.path.isabs(path):
                return _unknown("%s entry %s has no absolute installPath" % (record_name, key))
            entries.append((key, path))
    if not entries:
        detail = "%s records no adlc install" % record_name
        if copies:
            # What `claude plugin uninstall` leaves: the record entry goes, the
            # cache copies stay. Claude Code loads only what the record names.
            detail += ("; leftover adlc copies in the plugin cache at %s are not loaded: "
                       "Claude Code loads only a copy the record names"
                       % ", ".join(_unique(r for _k, r in copies)))
        return PluginInstall("absent", [], [], detail)
    roots, keys = [], []
    for key, path in entries:
        marketplace = key.split("@", 1)[1] if "@" in key else ""
        load = _local_marketplace_root(marketplace) or os.path.realpath(path)
        if plugin_manifest(load) is None:
            return _unknown(
                "%s records %s at %s, which holds no .claude-plugin/plugin.json naming %s"
                % (record_name, key, load, PLUGIN_NAME))
        roots.append(load)
        keys.append(key)
    roots, keys = _unique(roots), _unique(keys)
    return PluginInstall("present", roots, keys,
                         "%s at %s" % (", ".join(keys), ", ".join(roots)))


def _unique(items) -> List[str]:
    seen: Dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def under_plugin_cache(root: str) -> bool:
    """True when ``root`` really sits inside ``~/.claude/plugins/cache/``."""
    cache = os.path.realpath(_cache_dir())
    return os.path.realpath(root).startswith(cache + os.sep)


def detect_route(root: str, plugin: PluginInstall,
                 symlink_target: Optional[str] = None) -> str:
    """``plugin`` when ``root`` is a copy Claude Code loads as the plugin.

    That is a root inside the plugin cache (ADR-7), or one the install record
    names, which covers a local-path marketplace that runs from its source
    directory (verification.md N3). Every comparison is on real paths
    (ASSUME-001), never on ``git rev-parse``, because ``~/.claude`` can sit
    inside a dotfiles repo. Anything else is ``symlink``, the route whose checks
    run in full, so a machine this cannot place is never spared a check.

    ``symlink_target`` is the real directory the install.sh symlink install
    links, or ``None``. A recorded root that is also that target (a
    contributor's clone, installed both ways) stays ``symlink``, so the symlink
    health checks still run on it. ``doubled-install`` still reports the
    doubling.
    """
    real = os.path.realpath(root)
    if under_plugin_cache(real):
        return ROUTE_PLUGIN
    if real in plugin.roots:
        if symlink_target is not None and os.path.realpath(symlink_target) == real:
            return ROUTE_SYMLINK
        return ROUTE_PLUGIN
    return ROUTE_SYMLINK


def _detect_login_shell() -> str:
    """Real login shell from the password DB, not $SHELL (BR-6)."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_shell or ""
    except (ImportError, KeyError, OSError):
        # pwd is POSIX-only; on a platform without it, degrade to empty rather
        # than lying via $SHELL.
        return ""


def _detect_repo_root() -> str:
    """The toolkit root this doctor runs from, by ``toolkit_root`` (ADR-2).

    Not ``git rev-parse --show-toplevel``: a plugin cache copy has no ``.git``
    (verification.md row 11), so git would name an enclosing repo or nothing.
    On the symlink route the identity-checked root is the clone, which is what
    git reported there. A refused root falls back to the same walk rather than
    stopping the doctor, which must always report.
    """
    try:
        return toolkit_root.toolkit_root()
    except toolkit_root.ToolkitRootError:
        here = os.path.dirname(os.path.realpath(__file__))
        return os.path.dirname(os.path.dirname(here))


def _symlink_target() -> Optional[str]:
    """The real directory the install.sh symlink install links, or ``None``.

    ``checks`` owns that test (``_symlink_install``) and imports this module,
    so it is imported here, at call time.
    """
    import checks
    sym = checks._symlink_install()
    return sym[1] if sym else None


def _error_text(exc: Exception) -> str:
    """``Type: message``, with an ``OSError``'s reason only, never its path (LESSON-021)."""
    reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
    return "%s: %s" % (type(exc).__name__, reason) if reason else type(exc).__name__


def build_profile() -> Profile:
    """The machine profile, with the plugin install read once for every check."""
    root = _detect_repo_root()
    plugin: Optional[PluginInstall] = None
    route, route_error = ROUTE_SYMLINK, ""
    try:
        plugin = detect_plugin_install()
        route = detect_route(root, plugin, _symlink_target())
    except Exception as exc:  # the profile must never stop the doctor
        # The symlink route runs every check. `plugin-route` reports the
        # failure as a FAIL, and no fix prints install.sh (Profile.route_error).
        route, route_error = ROUTE_SYMLINK, _error_text(exc)
        if plugin is None:
            plugin = _unknown("plugin install detection failed (%s)" % route_error)
    return Profile(
        os=platform.system(),
        login_shell=_detect_login_shell(),
        repo_root=root,
        route=route,
        plugin=plugin,
        route_error=route_error,
    )


# A check's run() returns (Result, detail, remediation). remediation is only
# meaningful on FAIL and must be a copy-pasteable command or exact file edit
# (BR-5); on PASS/SKIP it may be "". A check with more than one way out puts
# one fix per line, and the report prints each on its own `-> fix:` line.
CheckRun = Callable[[Profile], Tuple[Result, str, str]]


@dataclass
class Check:
    id: str
    run: CheckRun
    # applies_to gates platform/opt-in relevance (BR-6). When it returns False,
    # the check is reported SKIP-with-notice, never FAIL.
    applies_to: Callable[[Profile], bool] = field(default=lambda p: True)
    skip_notice: str = "not applicable on this machine"


@dataclass
class CheckOutcome:
    id: str
    result: Result
    detail: str
    remediation: str


def _build_registry() -> List[Check]:
    """Assemble the ordered registry from checks.py.

    Imported lazily so the doctor framework (and its tests) can be exercised even
    if a specific check has an import issue; an empty registry is a valid state
    for framework-only tests.
    """
    try:
        import checks
    except ImportError:
        return []
    return checks.REGISTRY


def run_checks(profile: Profile,
               registry: Optional[List[Check]] = None,
               only: Optional[List[str]] = None) -> List[CheckOutcome]:
    """Run the registry (optionally filtered to ``only``) and collect outcomes.

    ``only`` is validated by the caller (main) before reaching here; an unknown
    id is a hard error there, not a silent no-op (BR-8).
    """
    if registry is None:
        registry = _build_registry()
    outcomes: List[CheckOutcome] = []
    for check in registry:
        if only is not None and check.id not in only:
            continue
        if not check.applies_to(profile):
            outcomes.append(CheckOutcome(check.id, Result.SKIP, check.skip_notice, ""))
            continue
        try:
            result, detail, remediation = check.run(profile)
        except Exception as exc:  # a check must never crash doctor
            outcomes.append(CheckOutcome(
                check.id, Result.FAIL,
                f"check raised {type(exc).__name__}: {exc}",
                "report this as a doctor bug; rerun with the check excluded via "
                f"--checks <others> to continue",
            ))
            continue
        outcomes.append(CheckOutcome(check.id, result, detail, remediation))
    return outcomes


def verdict_exit_code(outcomes: List[CheckOutcome]) -> int:
    """0 unless any non-skip check FAILed (BR-4)."""
    return 1 if any(o.result is Result.FAIL for o in outcomes) else 0


def format_report(outcomes: List[CheckOutcome], profile: Profile) -> str:
    lines: List[str] = []
    for o in outcomes:
        lines.append(f"[{o.result.value}] {o.id} — {o.detail}")
        if o.result is Result.FAIL and o.remediation:
            for fix in o.remediation.splitlines():
                lines.append(f"    -> fix: {fix}")
    n_fail = sum(1 for o in outcomes if o.result is Result.FAIL)
    n_skip = sum(1 for o in outcomes if o.result is Result.SKIP)
    n_pass = sum(1 for o in outcomes if o.result is Result.PASS)
    lines.append("")
    shell = profile.login_shell or "(undetermined)"
    route = profile.route + (" (route detection failed)" if profile.route_error else "")
    lines.append(f"profile: os={profile.os} login_shell={shell} route={route}")
    verdict = "OK" if n_fail == 0 else "FAILED"
    lines.append(
        f"verdict: {verdict} ({n_pass} pass, {n_fail} fail, {n_skip} skip)"
    )
    return "\n".join(lines)


def _parse_only(value: str, registry: List[Check]) -> List[str]:
    """Parse a --checks value into a validated list of ids.

    Unknown ids are a hard error (BR-8) — returns the list on success, raises
    ValueError with the valid set on failure.
    """
    requested = [s.strip() for s in value.split(",") if s.strip()]
    valid = {c.id for c in registry}
    unknown = [r for r in requested if r not in valid]
    if unknown:
        raise ValueError(
            "unknown check id(s): " + ", ".join(unknown)
            + "\nvalid checks: " + ", ".join(sorted(valid))
        )
    return requested


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="adlc doctor",
        description="Read-only environment health check.",
    )
    parser.add_argument(
        "--checks",
        metavar="id1,id2",
        help="run only the named checks (comma-separated). The skill pre-flight "
             "contract: e.g. --checks forge,delegate-gate",
    )
    args = parser.parse_args(argv)

    # REQ-654 BR-2: an ADLC_HOME that is set but empty or relative is an error
    # naming the variable, before any check reads a path. Falling through to
    # ~/.claude would report on a machine the operator did not point us at.
    home_error = adlc_home.validate()
    if home_error:
        sys.stderr.write("adlc doctor: %s\n" % home_error)
        return 2

    profile = build_profile()
    registry = _build_registry()

    only = None
    if args.checks:
        try:
            only = _parse_only(args.checks, registry)
        except ValueError as exc:
            sys.stderr.write(f"adlc doctor: {exc}\n")
            return 2

    outcomes = run_checks(profile, registry=registry, only=only)
    print(format_report(outcomes, profile))
    return verdict_exit_code(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
