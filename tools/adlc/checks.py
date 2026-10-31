#!/usr/bin/env python3
"""adlc doctor checks (REQ-519 BR-4).

Each check is a function ``(profile) -> (Result, detail, remediation)`` and is
registered in ``REGISTRY`` in report order. Every FAIL carries a copy-pasteable
remediation — a literal command or exact file edit, never "see docs" (BR-5).

The ``delegate-gate`` check **reuses REQ-515's shipped surface** rather than
reinventing config resolution (REQ-519 ADR-4): it sources
``partials/delegate-gate.sh`` for the 0/1/2 gate verdict and reads
``tools/delegate/_common.parse_delegate_config`` (via a subprocess probe) to
distinguish "not opted in" (SKIP) from "config says enabled but the binary is
missing" (FAIL — misconfigured).

Pure standard library: doctor must run before/without the delegation venv. That
holds transitively (LESSON-395) — nothing YAML-related is imported here or in
anything imported here, because the `pyyaml` check below exists precisely to
report on a machine where PyYAML is missing, and a check that cannot load
without the thing it diagnoses cannot report it.

Checks know the install route (REQ-669 ADR-7). The six that inspect what
``install.sh`` builds (REQ-654 added the skills view and the ``~/.agents/skills``
mount to REQ-669's four) are ``applies_to`` the symlink route only, so a
plugin-only machine SKIPs them with a notice. ``plugin-route`` reports the route
and checks the plugin's wiring, and ``doubled-install`` fires when both routes
are installed at once (BR-11). A remediation that runs ``install.sh`` is printed
on the symlink route only: on the plugin route it would symlink the plugin's
copy into ``~/.claude`` and double the install. When route detection failed,
the route is a fallback, so ``install.sh`` is not printed then either.

Every path, interpreter and install key a fix command carries goes through
``shlex.quote``. They come from real paths, the install record and the plugin
cache, and a quote, ``$(`` or ``;`` in any of them must stay text when the
operator pastes the line into a shell.
"""

import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

import adlc_home
import toolkit_root
from doctor import (PLUGIN_MARKETPLACE, PLUGIN_NAME, ROUTE_PLUGIN, Check, PluginInstall,
                    Profile, Result, detect_plugin_install, plugin_manifest,
                    under_plugin_cache, valid_install_key)

#: Every printed fix quotes what it interpolates (see the module docstring).
_q = shlex.quote

# A counter lock dir older than this (seconds) with no live holder is treated as
# stale (BR-4 "lock-dir not stale"). 15 minutes is generous for any real
# increment, which holds the lock for milliseconds.
_STALE_LOCK_SECONDS = 15 * 60

_COUNTERS = (".global-next-req", ".global-next-bug", ".global-next-lesson")

#: Every subprocess doctor uses to read the config is bounded. An interpreter
#: on a stalled network mount, or one whose site customization blocks, would
#: otherwise hang `adlc doctor` with no output — the one thing a bootstrap
#: diagnostic may never do. 20s is far beyond a real `import yaml`.
_PROBE_TIMEOUT_SECONDS = 20


# --- helpers ---------------------------------------------------------------

def _claude_home() -> str:
    """Claude Code's own directory: its skills and agents mounts live here.

    Not machine state (REQ-654 ADR-1): ``install.sh`` keeps Claude Code's mount at
    ``~/.claude`` whatever ``ADLC_HOME`` says, so the symlink checks and the
    doubled-install test read it here. Machine state is :func:`_adlc_home`.
    """
    return os.path.join(os.path.expanduser("~"), ".claude")  # adlc-home: claude-code


def _adlc_home() -> str:
    """The machine-state home (REQ-654 BR-1): counters, venv, config, skills view.

    ``doctor.main`` refuses an unusable ``ADLC_HOME`` before any check runs, so
    from a check this raises only when the check is called directly (a test).
    """
    return adlc_home.adlc_home()


def _resolves_into_checkout(link_path: str) -> bool:
    """True if link_path is a symlink whose real target is inside a git checkout."""
    if not os.path.islink(link_path):
        return False
    target = os.path.realpath(link_path)
    if not os.path.isdir(target):
        return False
    # The target (or, for agents, its parent) must be a git working tree.
    probe = target
    return subprocess.run(
        ["git", "-C", probe, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    ).returncode == 0


# --- the ONE interpreter rule (REQ-609 BR-8, ADR-2) ------------------------
#
# THE RULE: prefer `<ADLC_HOME>/delegate-venv/bin/python3` when it is a
# regular executable file AND that venv carries a `yaml` package directory
# under `lib/python*/site-packages/`; otherwise `python3` from `$PATH`.
# ADLC_HOME defaults to ~/.claude (REQ-654 ADR-3); when it cannot be resolved
# there is no venv to prefer, and the caller that needs the home says why.
#
# It is written out at THREE sites, because a shell partial cannot import
# Python and a Python module cannot be sourced by `sh`. The other two:
#
#   * `ensure_adlc_shim` in the root `install.sh` — the `adlc` shim's own text
#   * `_adlc_forge_python` in `partials/forge.sh` — the path `/proceed` takes
#     for every PR operation
#
# Change one, change all three.
#
# Why the second half is not optional: a venv created before REQ-609 carries
# `openai` and no PyYAML, and a plain `./install.sh` rewrites the shim without
# refreshing any venv. Preferring such a venv points every config read at the
# one interpreter on the machine that cannot parse the file — the loader
# answers `dependency-missing`, the forge consumer takes its ADR-2 carve-out,
# and a written `forge.provider` is silently overridden by origin-URL
# auto-detection. The venv directory is tested, never an interpreter spawned,
# so the two shell sites can ask the identical question.

def _delegate_venv():
    """``<ADLC_HOME>/delegate-venv``, or ``None`` when the home cannot be resolved."""
    try:
        return os.path.join(_adlc_home(), "delegate-venv")
    except adlc_home.AdlcHomeError:
        return None


def _venv_has_pyyaml(venv: str) -> bool:
    """True if ``venv`` carries a PyYAML package directory. No subprocess.

    ``venv`` is INTERPOLATED into a glob pattern, so it is escaped first: it is
    derived from ``$HOME``, and ``glob`` reads ``[``, ``]``, ``*`` and ``?`` in
    that prefix as pattern syntax. A home directory named ``h[1] x`` turns the
    literal path into a character class that matches nothing, and a fully
    populated venv comes back ``no-pyyaml`` — the doctor then tells the operator
    to install a PyYAML they already have, and ``_delegate_interpreter`` walks
    away from the one interpreter on that machine which can parse the config.
    Only the ``python*`` component is meant to be a pattern (REQ-609 verify D2).
    """
    pattern = os.path.join(
        glob.escape(venv), "lib", "python*", "site-packages", "yaml")
    return any(os.path.isdir(p) for p in glob.glob(pattern))


def _venv_state() -> str:
    """``ready`` | ``no-pyyaml`` | ``absent`` for the delegate venv."""
    venv = _delegate_venv()
    if venv is None:
        return "absent"
    exe = os.path.join(venv, "bin", "python3")
    if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
        return "absent"
    return "ready" if _venv_has_pyyaml(venv) else "no-pyyaml"


def _delegate_interpreter() -> str:
    """The interpreter ``adlc`` runs under, per THE RULE above.

    One helper on purpose: the doctor's ``pyyaml`` check must report on the
    SAME interpreter the config probes below run in, or it reports on a machine
    nobody is using (LESSON-392).

    The fallback is spelled ``sys.executable`` rather than a `$PATH` lookup
    because that IS `$PATH`'s `python3` when `adlc` was started by the shim's
    fallback arm, and it is the honest answer when it was not (a developer
    running `python3.11 tools/adlc/adlc.py doctor` wants a report about the
    interpreter they used). The shell sites cannot ask that question, so they
    spell the same rule as `python3`.
    """
    if _venv_state() == "ready":
        return os.path.join(_delegate_venv(), "bin", "python3")
    return sys.executable


def _machine_config_path() -> str:
    """The machine config path, spelled as ``_machine_config.default_config_path``.

    ``adlc_home.machine_config_path``, not ``_machine_config``: this module must
    load on a machine that has no delegation install at all (LESSON-395), which
    is exactly the machine the `pyyaml` check exists to report on. The two
    spellings are pinned equal by ``tests/test_adlc_home.py``.
    """
    return adlc_home.machine_config_path()


def _partial_path(profile: Profile, name: str) -> str:
    """Resolve a partial with the two-level fallback (project, then toolkit).

    The toolkit level is ``toolkit_root.toolkit_file`` (REQ-669 ADR-2), the
    tree this module runs from, not the symlink install's directory, which a
    plugin-only machine does not have. When neither level has the file, the project path
    is returned so the caller's ``isfile`` check reports it missing.
    """
    local = os.path.join(profile.repo_root, "partials", name)
    if os.path.isfile(local):
        return local
    try:
        return toolkit_root.toolkit_file("partials/" + name)
    except toolkit_root.ToolkitRootError:
        return local


def _read_text(path: str):
    """The file's text, or ``None`` when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


# --- install route (REQ-669 ADR-7) -----------------------------------------

#: The skill the doubled-install finding traces through both spellings.
_SAMPLE_SKILL = "spec"

#: SKIP notice of the six checks that inspect what install.sh builds.
_SYMLINK_ROUTE_ONLY = ("plugin route: this check inspects the install.sh symlink "
                       "install, which the plugin route does not use")

#: Claude Code is taken to set this to ``1`` in the shells it starts. That is
#: unverified: REQ-669 verification.md records Claude Code 2.1.258 and has no
#: row for this variable. Only inside such a shell must the SessionStart hook's
#: PATH entry be present (BR-7); outside one, a missing entry is a note.
_IN_CLAUDE_CODE_ENV = "CLAUDECODE"


def _on_symlink_route(profile: Profile) -> bool:
    return profile.route != ROUTE_PLUGIN


def _install_sh_ok(profile: Profile) -> bool:
    """True when a fix may run install.sh: the symlink route, known to be one (BR-11)."""
    return profile.route != ROUTE_PLUGIN and not profile.route_error


def _plugin_install(profile: Profile) -> PluginInstall:
    """The profile's plugin-install reading, made here for a profile built by hand."""
    return profile.plugin if profile.plugin is not None else detect_plugin_install()


def _install_key(root: str) -> str:
    """``adlc@<marketplace>`` read off a cache path, else this repo's marketplace.

    A marketplace directory whose name is not a valid install key falls back
    to this repo's marketplace rather than reaching a fix command.
    """
    real = os.path.realpath(root)
    if os.path.basename(os.path.dirname(real)) == PLUGIN_NAME:
        marketplace = os.path.basename(os.path.dirname(os.path.dirname(real)))
        key = "%s@%s" % (PLUGIN_NAME, marketplace)
        if valid_install_key(key) and os.path.basename(os.path.dirname(os.path.dirname(
                os.path.dirname(real)))) == "cache":
            return key
    return "%s@%s" % (PLUGIN_NAME, PLUGIN_MARKETPLACE)


def _reinstall_fix(key: str) -> str:
    return "claude plugin uninstall %s && claude plugin install %s" % (_q(key), _q(key))


def _pointer_problem(root: str):
    """Why ``~/.claude/adlc/plugin-root`` does not name ``root``, or ``""``.

    The SessionStart hook writes the plugin root and one newline (ADR-4). An
    empty or relative value is a problem, not a match: ``realpath("")`` is the
    current directory, which may well be ``root``.
    """
    pointer = os.path.join(_claude_home(), "adlc", "plugin-root")
    text = _read_text(pointer)
    if text is None:
        state = "missing" if not os.path.lexists(pointer) else "unreadable"
        return ("~/.claude/adlc/plugin-root is %s, so skill text read without "  # adlc-home: alias
                "substitution cannot find this copy (ToolkitRoot arm 3)" % state)
    value = text[:-1] if text.endswith("\n") else text
    if not value or "\n" in value or not os.path.isabs(value):
        return "~/.claude/adlc/plugin-root does not hold one absolute path"  # adlc-home: alias
    if os.path.realpath(value) != root:
        return "~/.claude/adlc/plugin-root names %s, not this copy" % value  # adlc-home: alias
    return ""


def _local_pointer_note(root: str) -> str:
    """What the pointer holds, for a plugin root outside the plugin cache.

    The SessionStart hook records only a plugin-cache copy (ADR-4), so a
    local-path marketplace, which runs from its source directory, never records
    itself. A pointer that does not name such a root is expected, not a fault,
    and re-running the hook would not change it.
    """
    text = _read_text(os.path.join(_claude_home(), "adlc", "plugin-root"))
    value = (text[:-1] if text and text.endswith("\n") else text) or ""
    held = value if value and "\n" not in value and os.path.isabs(value) else "absent"
    return ("the SessionStart hook records only a plugin-cache copy, so skill text "
            "read without substitution resolves through ~/.claude/adlc/plugin-root "  # adlc-home: alias
            "(%s), not this local-path copy" % held)


def check_plugin_route(profile: Profile):
    """Report the route and version; on the plugin route, check its wiring.

    On the plugin route three things must hold: this copy is the one Claude
    Code loads, the SessionStart hook has recorded it in
    ``~/.claude/adlc/plugin-root`` (ToolkitRoot arm 3, ADR-4; a copy outside the
    plugin cache is never recorded, so there it is only reported), and
    ``scripts/adlc`` is executable and, inside a Claude Code session, on PATH
    (BR-7). A plugin install this doctor cannot read is a FAIL, never a PASS
    (LESSON-581). The symlink route has none of these, so there the check only
    reports. When route detection failed, the route is a fallback and this
    check FAILs saying so.
    """
    root = os.path.realpath(profile.repo_root)
    details_fix = "claude plugin details adlc   # shows the adlc install Claude Code loads"
    if profile.route_error:
        return (
            Result.FAIL,
            f"route detection failed ({profile.route_error}); the doctor fell back to the "
            "symlink route so every check runs, and prints no install.sh fix, because "
            "this may be a plugin install",
            details_fix,
        )
    if profile.route != ROUTE_PLUGIN:
        version = (_read_text(os.path.join(root, "VERSION")) or "").strip() or "unknown"
        return Result.PASS, f"symlink route: {root}, version {version}", ""

    manifest = plugin_manifest(root) or {}
    version = manifest.get("version") if isinstance(manifest.get("version"), str) else "unknown"
    head = f"plugin route: {root}, version {version}"
    plugin = _plugin_install(profile)
    if plugin.state == "unknown":
        return (
            Result.FAIL,
            f"{head}; cannot confirm this is the copy Claude Code loads: {plugin.detail}",
            details_fix,
        )
    key = plugin.keys[0] if plugin.keys else _install_key(root)
    if root not in plugin.roots:
        if plugin.roots:
            return (
                Result.FAIL,
                f"{head}; this is not the copy Claude Code loads ({', '.join(plugin.roots)})",
                "%s doctor" % _q(os.path.join(plugin.roots[0], "scripts", "adlc")),
            )
        if not manifest:
            return (
                Result.FAIL,
                f"{head}; this copy has no .claude-plugin/plugin.json naming {PLUGIN_NAME}",
                _reinstall_fix(key),
            )
        # A cache copy the record does not name: what an uninstall leaves.
        return (
            Result.FAIL,
            f"{head}; the adlc plugin is not installed, so Claude Code does not load "
            f"this copy: {plugin.detail}",
            details_fix,
        )

    problems, fixes = [], []
    cached = under_plugin_cache(root)
    pointer = _pointer_problem(root) if cached else ""
    if pointer:
        problems.append(pointer)
        fixes.append("CLAUDE_PLUGIN_ROOT=%s sh %s" % (
            _q(root), _q(os.path.join(root, "scripts", "session-start.sh")))
            + "   # what the SessionStart hook runs; a new Claude Code session does the same")

    shim = os.path.join(root, "scripts", "adlc")
    if not os.path.isfile(shim):
        problems.append("scripts/adlc is missing from this copy")
        fixes.append(_reinstall_fix(key))
    elif not os.access(shim, os.X_OK):
        problems.append("scripts/adlc is not executable")
        fixes.append("chmod +x %s" % _q(shim))

    on_path = shutil.which("adlc")
    path_note = ""
    if on_path and os.path.realpath(on_path) == os.path.realpath(shim):
        path_note = "adlc on PATH is this copy's scripts/adlc"
    elif on_path:
        path_note = f"adlc on PATH is {on_path}, not this copy's scripts/adlc"
    elif os.environ.get(_IN_CLAUDE_CODE_ENV) == "1":
        problems.append("adlc is not on this Claude Code session's PATH")
        # `$PATH` stays inside double quotes so it expands; the root is a
        # separately quoted word glued on after the colon.
        fixes.append('export PATH="$PATH":%s' % _q(os.path.join(root, "scripts"))
                     + "   # what the SessionStart hook adds; a new Claude Code session does the same")
    else:
        path_note = ("adlc is not on this shell's PATH; the SessionStart hook adds "
                     "scripts/ inside Claude Code sessions")

    if problems:
        return Result.FAIL, f"{head}: " + "; ".join(problems), "\n".join(fixes)
    pointer_note = ("~/.claude/adlc/plugin-root names this copy" if cached  # adlc-home: alias
                    else _local_pointer_note(root))
    return (
        Result.PASS,
        f"{head} ({', '.join(plugin.keys)}); {pointer_note}; "
        f"scripts/adlc is executable; {path_note}",
        "",
    )


def _symlink_install():
    """``(skills link, real target, agents link or None)``, or ``None``.

    The install.sh symlink install counts when ``~/.claude/skills`` is a symlink
    to a directory that holds ``partials/`` (the test that ToolkitRoot's arm 2
    makes, ADR-1) and the sample skill. A directory of personal skills, or a link to
    one, is not this toolkit. The agents link is returned only when it points
    into the same tree, so a fix never removes a link this toolkit did not make.
    """
    skills = os.path.join(_claude_home(), "skills")
    if not os.path.islink(skills):
        return None
    target = os.path.realpath(skills)
    if not (os.path.isdir(os.path.join(target, "partials"))
            and os.path.isfile(os.path.join(target, _SAMPLE_SKILL, "SKILL.md"))):
        return None
    agents = os.path.join(_claude_home(), "agents")
    ours = os.path.islink(agents) and \
        os.path.realpath(agents) == os.path.realpath(os.path.join(target, "agents"))
    return skills, target, (agents if ours else None)


def _doubled_fixes(sym, keys):
    """One copy-pasteable line per way out of a doubled install (BR-11)."""
    skills, target, agents = sym
    uninstall = " && ".join("claude plugin uninstall %s" % _q(k) for k in keys)
    removals = ["rm %s" % _q(skills)] + (["rm %s" % _q(agents)] if agents else [])
    # install.sh's ~/bin/adlc shim runs the clone and comes first on PATH, so
    # with only the links gone `adlc doctor` would still run the clone, see the
    # symlink route without its links, and advise re-creating them.
    shim = os.path.join(os.path.expanduser("~"), "bin", "adlc")
    text = _read_text(shim) if os.path.isfile(shim) else None
    if text and os.path.join(target, "tools", "adlc", "adlc.py") in text:
        removals.append("rm %s" % _q(shim))
    return [
        f"{uninstall}   # keep the symlink install: skills stay bare (/{_SAMPLE_SKILL})",
        " && ".join(removals)
        + "   # keep the plugin: skills become /adlc:<name>; removes the links, not the clone",
    ]


def check_doubled_install(profile: Profile):
    """FAIL when the symlink install and the adlc plugin are both installed (BR-11).

    The finding names which copy each spelling of the sample skill reaches and
    prints one fix per way out. A plugin install that cannot be read, next to a
    live symlink install, is also a FAIL: it is not known to be safe
    (LESSON-581). With either install alone the check passes and prints no
    finding (LESSON-440).
    """
    plugin = _plugin_install(profile)
    sym = _symlink_install()
    if sym is None:
        return (Result.PASS,
                f"no install.sh symlink install at ~/.claude/skills (adlc plugin: {plugin.state})",  # adlc-home: claude-code
                "")
    _skills, target, _agents = sym
    if plugin.state == "absent":
        return (Result.PASS,
                f"symlink install only: ~/.claude/skills -> {target}; {plugin.detail}", "")  # adlc-home: claude-code
    keys = plugin.keys or [f"{PLUGIN_NAME}@{PLUGIN_MARKETPLACE}"]
    fixes = _doubled_fixes(sym, keys)
    if plugin.state != "present":
        return (
            Result.FAIL,
            f"the symlink install is active (~/.claude/skills -> {target}), and whether "  # adlc-home: claude-code
            f"the adlc plugin is installed too cannot be told: {plugin.detail}",
            "\n".join(["claude plugin details adlc   # if Claude Code lists the plugin, "
                       "the install is doubled; then run one of the next two lines"] + fixes),
        )
    plugin_copies = " and ".join(
        os.path.join(r, _SAMPLE_SKILL, "SKILL.md") for r in plugin.roots)
    same = " (the same directory, loaded through both routes)" if target in plugin.roots else ""
    return (
        Result.FAIL,
        f"both installs are active{same}. Bare /{_SAMPLE_SKILL} reaches the personal copy "
        f"at ~/.claude/skills ({os.path.join(target, _SAMPLE_SKILL, 'SKILL.md')}); "  # adlc-home: claude-code
        f"/adlc:{_SAMPLE_SKILL} reaches the plugin ({', '.join(plugin.keys)}) at "
        f"{plugin_copies}. A bare name reaches a plugin skill only when nothing else "
        "owns it (skills docs; measured for the plugin-only case in REQ-669 "
        "verification.md row 6, Claude Code 2.1.258)",
        "\n".join(fixes),
    )


# --- symlink checks --------------------------------------------------------

def _mount_homes():
    """Every directory install.sh keeps a skills/agents pair in (REQ-654 ADR-6).

    Claude Code's ``~/.claude`` always; ``ADLC_HOME`` too when it names another
    directory. One entry when the home is the default, two when it is not.
    """
    homes = [_claude_home()]
    try:
        home = _adlc_home()
    except adlc_home.AdlcHomeError:
        return homes
    if os.path.realpath(home) != os.path.realpath(homes[0]):
        homes.append(home)
    return homes


def check_skills_symlink(profile: Profile):
    links = [os.path.join(h, "skills") for h in _mount_homes()]
    bad = [link for link in links if not _resolves_into_checkout(link)]
    if not bad:
        return Result.PASS, "; ".join(
            f"{link} -> {os.path.realpath(link)}" for link in links), ""
    return (
        Result.FAIL,
        "; ".join(f"{link} is missing, dangling, or not a symlink into a git checkout"
                  for link in bad),
        "\n".join("ln -sfn %s %s" % (_q(profile.repo_root), _q(link)) for link in bad),
    )


def check_agents_symlink(profile: Profile):
    target = os.path.join(profile.repo_root, "agents")
    links = [os.path.join(h, "agents") for h in _mount_homes()]
    bad = [link for link in links
           if not (os.path.islink(link)
                   and os.path.realpath(link) == os.path.realpath(target))]
    if not bad:
        return Result.PASS, "; ".join(
            f"{link} -> {os.path.realpath(link)}" for link in links), ""
    return (
        Result.FAIL,
        "; ".join(f"{link} does not resolve to {target}" for link in bad),
        "\n".join("ln -sfn %s %s" % (_q(target), _q(link)) for link in bad),
    )


# --- the skills view and the ~/.agents/skills mount (REQ-654 BR-9, ADR-8) ---
#
# Both inspect what install.sh builds, so both SKIP on the plugin route with the
# other symlink-route checks. The tree they compare against is the clone
# Claude Code's mount points at (install.sh builds the view from the same
# REPO_ROOT), else the tree this doctor runs from.

#: A skill directory name the view may link (install.sh's `toolkit_skill_names`).
_SKILL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _skills_view() -> str:
    return os.path.join(_adlc_home(), "adlc", "skills-view")


def _agents_mount() -> str:
    return os.path.join(os.path.expanduser("~"), ".agents", "skills")


def _view_source(profile: Profile) -> str:
    sym = _symlink_install()
    return sym[1] if sym else os.path.realpath(profile.repo_root)


def _toolkit_skills(root: str):
    """Sorted names of ``<root>/<name>/SKILL.md`` at depth one, as install.sh lists them."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    return sorted(n for n in entries
                  if _SKILL_NAME_RE.fullmatch(n)
                  and os.path.isfile(os.path.join(root, n, "SKILL.md")))


def _install_fix(profile: Profile, why: str) -> str:
    """The verbatim fix that runs install.sh, from any directory (LESSON-572)."""
    if _install_sh_ok(profile):
        return "%s   # %s" % (_q(os.path.join(profile.repo_root, "install.sh")), why)
    return ("claude plugin details adlc   # route detection failed: if Claude Code lists "
            "adlc, this machine uses the plugin route and install.sh is not the fix")


def check_skills_view(profile: Profile):
    """FAIL unless every skill has exactly its link in the view and nothing dangles."""
    view = _skills_view()
    source = _view_source(profile)
    names = _toolkit_skills(source)
    why = "rebuilds the skills view"
    if os.path.islink(view) or not os.path.isdir(view):
        return (Result.FAIL,
                f"skills view {view} is missing; Copilot, Codex, Gemini and Cursor read the "
                "toolkit's skills through it (~/.agents/skills)",
                _install_fix(profile, why))
    problems = []
    for name in names:
        link = os.path.join(view, name)
        want = os.path.realpath(os.path.join(source, name))
        if not os.path.islink(link):
            problems.append(f"{name}: no link" if not os.path.lexists(link)
                            else f"{name}: not a symlink")
        elif not os.path.exists(link):
            problems.append(f"{name}: dangling")
        elif os.path.realpath(link) != want:
            problems.append(f"{name}: points at {os.path.realpath(link)}")
    try:
        extra = sorted(e for e in os.listdir(view)
                       if os.path.islink(os.path.join(view, e)) and e not in names)
    except OSError:
        extra = []
    problems += [f"{e}: not a skill in {source}" for e in extra]
    if problems:
        return (Result.FAIL,
                f"skills view {view} is out of date ({'; '.join(problems)}). A skill "
                "directory added to the clone reaches ~/.agents/skills only after "
                "install.sh runs (REQ-654 BR-6)",
                _install_fix(profile, why))
    return (Result.PASS,
            f"{view}: {len(names)} skills linked into {source}; a newly added skill "
            "appears there after the next install.sh run", "")


def check_agents_skills_mount(profile: Profile):
    """``~/.agents/skills`` is the view, or a directory holding the per-skill links."""
    mount = _agents_mount()
    view = _skills_view()
    source = _view_source(profile)
    why = "mounts the skills view at ~/.agents/skills"
    if os.path.islink(mount) and os.path.realpath(mount) == os.path.realpath(view):
        return Result.PASS, f"{mount} -> {view}", ""
    if os.path.isdir(mount):
        missing, broken, taken = [], [], []
        for name in _toolkit_skills(source):
            entry = os.path.join(mount, name)
            if not os.path.lexists(entry):
                missing.append(name)
            elif (os.path.islink(entry) and os.path.realpath(entry)
                  == os.path.realpath(os.path.join(source, name))):
                continue
            elif os.path.islink(entry) and os.readlink(entry).endswith(
                    "/adlc/skills-view/" + name):
                broken.append(name)
            else:
                taken.append(name)
        note = (f"; names taken by your own entries, left alone: {', '.join(taken)}"
                if taken else "")
        if missing or broken:
            parts = ([f"no link for {', '.join(missing)}"] if missing else []) + \
                    ([f"dangling links for {', '.join(broken)}"] if broken else [])
            return (Result.FAIL,
                    f"{mount} is your directory, and {'; '.join(parts)}{note}",
                    _install_fix(profile, why))
        return (Result.PASS,
                f"{mount} is your directory and holds a link to every toolkit skill{note}",
                "")
    if os.path.islink(mount):
        target = os.readlink(mount)
        if target.endswith("/adlc/skills-view"):
            return (Result.FAIL, f"{mount} is a dangling link to an earlier skills view ({target})",
                    _install_fix(profile, why))
        return (Result.FAIL,
                f"{mount} is a dangling link to {target}, which install.sh did not make",
                "mv %s %s && %s" % (_q(mount), _q(mount + ".bak"),
                                    _install_fix(profile, why)))
    if os.path.lexists(mount):
        return (Result.FAIL, f"{mount} is a file, not a directory",
                "mv %s %s && %s" % (_q(mount), _q(mount + ".bak"),
                                    _install_fix(profile, why)))
    return (Result.FAIL,
            f"{mount} is absent: Copilot, Codex, Gemini and Cursor see none of the "
            "toolkit's skills", _install_fix(profile, why))


# --- consumer-sync (REQ-654 BR-8, BR-9, ADR-8) ------------------------------
#
# Every consumer repo whose vendored .adlc/partials/ is behind the canonical
# copies, machine-wide. A stale vendored partial is the hazard that made moving
# the toolkit's home unsafe (LESSON-441), so a stale one FAILs. The baseline is
# established before anything is compared (BUG-204): a checkout that is not
# clean-and-current is compared through origin/<default>, and with no
# trustworthy baseline the verdict is withheld, never guessed (LESSON-581).
# Read-only: no fetch, and nothing is written to any repo, .git included.
#
# The same walk reports a stale project layer (a settings file with no hooks
# block, say) through `adlc harness drift`'s comparison, which render-currency,
# looking only at agents and user-level surfaces, cannot see. A repo with
# something stale is then asked about on GitHub: one GitHub calls archived cannot
# take the fix, so it is skipped by name. Only `gh`'s own true does that. No
# answer leaves the repo stale, and a repo with nothing stale costs no request.

def _git_out(root: str, *args):
    """``git -C root args`` stdout stripped, or ``None`` on a non-zero exit."""
    try:
        # --no-optional-locks: `status` and `diff` otherwise refresh the index,
        # a write into a repo this check promises not to touch.
        out = subprocess.run(["git", "--no-optional-locks", "-C", root] + list(args),
                             capture_output=True, timeout=_PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.decode("utf-8", "replace").strip() if out.returncode == 0 else None


def _main_worktree(path: str):
    """The main worktree of the git repo holding ``path``, or ``None``."""
    common = _git_out(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    return os.path.dirname(os.path.realpath(common))


def _repos_root(profile: Profile):
    """``(root, how)``: ``$ADLC_REPOS_ROOT``, else id-alloc's default, or ``(None, why)``."""
    env = os.environ.get("ADLC_REPOS_ROOT")
    if env:
        return env, "$ADLC_REPOS_ROOT"
    main = _main_worktree(os.getcwd()) or _main_worktree(profile.repo_root)
    if main:
        return os.path.dirname(main), "the parent of %s (id-alloc's default)" % main
    return None, "not inside a git repo and the toolkit is not a checkout; set ADLC_REPOS_ROOT"


def _consumers(root: str, toolkit: str):
    out = []
    try:
        children = sorted(os.listdir(root))
    except OSError:
        return out
    skip = {os.path.realpath(toolkit)}
    main = _main_worktree(toolkit)
    if main:
        skip.add(os.path.realpath(main))
    for name in children:
        path = os.path.join(root, name)
        if name.startswith(".") or not os.path.isdir(path):
            continue
        if not os.path.lexists(os.path.join(path, ".git")):
            continue
        if not os.path.isdir(os.path.join(path, ".adlc", "partials")):
            continue
        if os.path.realpath(path) in skip:
            continue
        out.append(path)
    return out


def _disk_partials(root: str):
    """``{name: bytes}`` for ``<root>/partials/*.sh``."""
    out = {}
    pdir = os.path.join(root, "partials")
    try:
        names = sorted(os.listdir(pdir))
    except OSError:
        return out
    for name in names:
        path = os.path.join(pdir, name)
        if name.endswith(".sh") and os.path.isfile(path):
            try:
                with open(path, "rb") as fh:
                    out[name] = fh.read()
            except OSError:
                continue
    return out


class _Baseline:
    """What the canonical partials are compared from, named (BUG-204)."""

    def __init__(self, label, source, partials, unverified="", ref=None):
        self.label = label            # e.g. "main, clean, 0 behind origin/main ..."
        self.source = source          # "the working tree" | "origin/main" | "adlc plugin 5.4.0"
        self.partials = partials      # {name: bytes}
        self.unverified = unverified  # non-empty: why no verdict can be trusted
        self.ref = ref                # the origin ref of a checkout, whichever copy is read


def _consumer_baseline(profile: Profile) -> _Baseline:
    root = profile.repo_root
    if not os.path.lexists(os.path.join(root, ".git")):
        manifest = plugin_manifest(root)
        version = manifest.get("version") if manifest else None
        if isinstance(version, str) and re.fullmatch(r"[0-9A-Za-z.+-]+", version):
            name = f"adlc plugin {version}"
            return _Baseline(name, name, _disk_partials(root))
        return _Baseline("a toolkit copy with no .git and no readable plugin version",
                         "the copy on disk", _disk_partials(root),
                         unverified="no adlc plugin version could be read from "
                                    ".claude-plugin/plugin.json")
    branch = _git_out(root, "symbolic-ref", "--quiet", "--short", "HEAD") or "detached HEAD"
    head_ref = _git_out(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    default = head_ref[len("origin/"):] if head_ref and head_ref.startswith("origin/") else "main"
    dirty = bool(_git_out(root, "status", "--porcelain", "--", "partials"))
    ref = "origin/" + default
    has_ref = _git_out(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None
    behind = _git_out(root, "rev-list", "--count", "HEAD.." + ref) if has_ref else None
    label = "%s%s, %s" % (branch, ", partials/ dirty" if dirty else "",
                          "%s behind %s as of the last fetch" % (behind, ref)
                          if has_ref else "no %s ref" % ref)
    if not has_ref:
        return _Baseline(label, "the working tree", _disk_partials(root),
                         unverified="no %s ref to establish the baseline (no remote, or "
                                    "never fetched: git -C %s fetch origin)" % (ref, _q(root)))
    same = _git_out(root, "diff", "--quiet", "HEAD", ref, "--", "partials") is not None
    if branch == default and not dirty and behind == "0" and same:
        return _Baseline(label, "the working tree", _disk_partials(root), ref=ref)
    listing = _git_out(root, "ls-tree", "--name-only", ref, "partials/") or ""
    partials = {}
    for path in listing.splitlines():
        name = path.split("/", 1)[-1]
        if not (name.endswith(".sh") and "/" not in name):
            continue
        try:
            shown = subprocess.run(["git", "-C", root, "show", "%s:%s" % (ref, path)],
                                   capture_output=True, timeout=_PROBE_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if shown.returncode == 0:
            partials[name] = shown.stdout
    if not partials:
        return _Baseline(label, ref, {}, unverified="%s carries no partials/*.sh" % ref)
    return _Baseline(label, ref, partials, ref=ref)


def _stale_files(consumer: str, canonical: dict):
    out = []
    vdir = os.path.join(consumer, ".adlc", "partials")
    for name in sorted(canonical):
        path = os.path.join(vdir, name)
        if not os.path.isfile(path):
            out.append(name + " (missing)")
            continue
        try:
            with open(path, "rb") as fh:
                if fh.read() != canonical[name]:
                    out.append(name)
        except OSError:
            out.append(name + " (unreadable)")
    return out


#: What a project-layer render reads from the toolkit.
_RENDER_INPUTS = ("harness", "templates/permissions.yml", "templates/hooks.yml")


def _project_layers(consumers: list, profile: Profile, base: _Baseline):
    """``({consumer: [finding]}, [why not compared])``, ``adlc harness drift``'s verdict.

    A render reads the toolkit's disk copy, so in a checkout it counts only while
    those inputs match the ref, even when ``partials/`` is clean and current: an
    unmerged template must not call every consumer stale (BUG-204).
    """
    if base.ref and _git_out(profile.repo_root, "diff", "--quiet", base.ref, "--",
                             *_RENDER_INPUTS) is None:
        return {}, ["the toolkit's %s differ from %s" % (", ".join(_RENDER_INPUTS), base.ref)]
    import harness_render
    layers, unverified = {}, []
    for consumer in consumers:
        try:
            rows = harness_render.stale_project_layer(consumer, profile.repo_root)
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            unverified.append("%s (%s)" % (consumer, exc))
            continue
        layers[consumer] = ["%s %s %s: %s" % (name, rel, cls, ", ".join(details))
                            for name, rel, cls, details in rows]
    return layers, unverified


#: A github.com origin in the spellings git hands back. The slug is passed to `gh`
#: and printed, and the rest of the URL is neither: it can carry a token.
_GITHUB_ORIGIN_RE = re.compile(
    r"(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.git)?/?")


def _archive_state(consumer: str):
    """``(archived, why)``: ``True`` or ``False`` on ``gh``'s word, else ``None``."""
    origin = _git_out(consumer, "remote", "get-url", "origin")
    if not origin:
        return None, "no origin remote"
    match = _GITHUB_ORIGIN_RE.fullmatch(origin)
    if not match:
        return None, "origin is not on github.com"
    slug = match.group(1)
    gh = shutil.which("gh")
    if not gh:
        return None, "gh is not on PATH"
    try:
        out = subprocess.run([gh, "repo", "view", slug, "--json", "isArchived",
                              "--jq", ".isArchived"], capture_output=True,
                             stdin=subprocess.DEVNULL, timeout=_PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None, "gh repo view %s did not answer" % slug
    answer = out.stdout.decode("utf-8", "replace").strip()
    if out.returncode == 0 and answer == "true":
        return True, "%s is archived on GitHub and cannot take a PR" % slug
    if out.returncode == 0 and answer == "false":
        return False, ""
    return None, "gh repo view %s gave no answer (exit %d)" % (slug, out.returncode)


def _stale_reason(files: list, layer: list):
    reasons = ["%d file%s: %s" % (len(files), "" if len(files) == 1 else "s", ", ".join(files))
               ] if files else []
    return "; ".join(reasons + ["project layer %s" % finding for finding in layer])


def check_consumer_sync(profile: Profile):
    root, how = _repos_root(profile)
    if root is None:
        return Result.SKIP, f"no repos root ({how})", ""
    consumers = _consumers(root, profile.repo_root)
    if not consumers:
        return (Result.SKIP,
                f"no consumer under {root} ({how}) has a vendored .adlc/partials/", "")
    base = _consumer_baseline(profile)
    if base.unverified:
        differ = [c for c in consumers if _stale_files(c, base.partials)]
        return (Result.SKIP,
                f"unverified-baseline: {base.unverified}. Baseline {base.label}; "
                f"{len(consumers)} consumer(s) under {root}, {len(differ)} differ from "
                f"{base.source}{': ' + ', '.join(differ) if differ else ''}. No verdict "
                "is asserted until the baseline can be trusted", "")
    layers, unverified = _project_layers(consumers, profile, base)
    stale, skipped = [], []
    for consumer in consumers:
        reason = _stale_reason(_stale_files(consumer, base.partials), layers.get(consumer, []))
        if not reason:
            continue
        archived, why = _archive_state(consumer)
        if archived:
            skipped.append("skipped %s (%s)" % (consumer, why))
            continue
        note = " [archive state unknown: %s]" % why if archived is None else ""
        stale.append((consumer, "%s is stale (%s)%s" % (consumer, reason, note)))
    tail = "".join(". " + line for line in skipped)
    if unverified:
        tail += ". Project layer not compared: %s" % "; ".join(unverified)
    if stale:
        skill = "/adlc:template-drift" if profile.route == ROUTE_PLUGIN else "/template-drift"
        detail = "; ".join(line for _c, line in stale)
        return (Result.FAIL,
                f"{detail}. Compared against {base.source} (baseline {base.label}); a stale "
                "vendored partial is read before the canonical copy, so its fixes never run "
                f"there (LESSON-441){tail}",
                "\n".join("cd %s && claude -p %s" % (_q(c), _q(skill)) for c, _line in stale))
    checked = len(consumers) - len(skipped)
    if unverified or not checked:
        return (Result.SKIP,
                f"{checked} consumer(s) under {root} show nothing stale against {base.source} "
                f"(baseline {base.label}), and no verdict is asserted{tail}", "")
    return (Result.PASS,
            f"{checked} consumer(s) under {root} in sync with {base.source} "
            f"(baseline {base.label}){tail}", "")


# --- toolkit clone health --------------------------------------------------

def check_toolkit_clean(profile: Profile):
    root = profile.repo_root
    head = subprocess.run(
        ["git", "-C", root, "symbolic-ref", "--quiet", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0:
        return (
            Result.FAIL,
            "toolkit clone is in detached HEAD state",
            "git -C %s checkout main" % _q(root),
        )
    dirty = subprocess.run(
        ["git", "-C", root, "status", "--porcelain"],
        capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        return (
            Result.FAIL,
            "toolkit clone has uncommitted changes",
            "git -C %s status   # review, then commit or stash" % _q(root),
        )
    return Result.PASS, f"on {head.stdout.strip()}, clean", ""


# --- PATH / shims ----------------------------------------------------------

def check_path_shims(profile: Profile):
    # With route detection failed this may be a plugin machine, where
    # install.sh doubles the install (BR-11); the fix asks first.
    unsure = ("claude plugin details adlc   # route detection failed: if Claude Code "
              "lists adlc, its scripts/adlc is the CLI and the plugin needs no shim")
    adlc = shutil.which("adlc")
    if not adlc:
        return (
            Result.FAIL,
            "adlc is not on PATH",
            "./install.sh --repair   # then restart your shell (or: source ~/.zshrc)"
            if _install_sh_ok(profile) else unsure,
        )
    probe = subprocess.run([adlc, "--version"], capture_output=True, text=True)
    if probe.returncode != 0:
        return (
            Result.FAIL,
            f"adlc on PATH ({adlc}) but `adlc --version` failed",
            "./install.sh --repair   # regenerates the shim" if _install_sh_ok(profile) else unsure,
        )
    return Result.PASS, f"adlc -> {adlc} (v{probe.stdout.strip()})", ""


# --- gh --------------------------------------------------------------------

def check_gh_present(profile: Profile):
    gh = shutil.which("gh")
    if gh:
        return Result.PASS, f"gh -> {gh}", ""
    install_line = (
        "brew install gh" if profile.os == "Darwin"
        else "see https://github.com/cli/cli#installation"
    )
    return Result.FAIL, "gh (GitHub CLI) is not on PATH", install_line


def check_gh_auth(profile: Profile):
    # Retained as a helper reused by check_forge on the github branch (REQ-520
    # ADR-4). It is NO LONGER in REGISTRY — the `forge` check is the single
    # forge-auth mechanism and folds this probe in for provider github.
    if not shutil.which("gh"):
        return Result.SKIP, "gh not installed (see gh-present)", ""
    status = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True,
    )
    if status.returncode == 0:
        return Result.PASS, "gh is authenticated", ""
    return Result.FAIL, "gh is not authenticated", "gh auth login"


# --- forge adapter (REQ-520 BR-7) — supersedes the standalone gh-auth check --

def _forge_provider_verdict(profile: Profile):
    """Resolve the forge provider by sourcing partials/forge.sh under bash.

    Returns (provider, detail) on success, or (None, reason) when resolution
    failed. ``no-remote`` is a distinguished reason -> the check SKIPs (BR-7).
    Mirrors ``_gate_verdict``'s source-a-partial-under-bash pattern.
    """
    partial = _partial_path(profile, "forge.sh")
    if not os.path.isfile(partial):
        return None, "forge-partial-missing"
    # Resolve against the current working dir (the repo doctor was invoked in),
    # not the toolkit root — provider is a property of the consumer repo's remote.
    # No temp-file redirect: subprocess capture_output collects stderr into
    # proc.stderr, so there is no predictable-path junk file / TOCTOU foothold
    # (LESSON-008). The function's fail-loud message lands in proc.stderr if needed.
    # The path is shell-quoted: a checkout under a directory whose name holds a
    # `'` would otherwise end the quote and run the rest of the path as shell.
    script = (
        f". {_q(partial)}; "
        "adlc_forge_provider \"$PWD\"; rc=$?; "
        'printf "%s\\n" "$rc"'
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    out = proc.stdout.splitlines()
    # The script prints the provider (from adlc_forge_provider) then the rc line.
    # Parse defensively: provider is the recognized non-rc line.
    provider = ""
    for line in out:
        s = line.strip()
        if s in ("github", "azure-devops"):
            provider = s
    if provider:
        return provider, "resolved"
    # No remote at all is the documented SKIP case.
    if not _has_remote(profile):
        return None, "no-remote"
    return None, "unresolved"


def _has_remote(profile: Profile) -> bool:
    out = subprocess.run(
        ["git", "remote"], capture_output=True, text=True,
    )
    return out.returncode == 0 and bool(out.stdout.strip())


def check_forge(profile: Profile):
    """Resolved provider, backend CLI present, auth valid, read-only probe (BR-7).

    SKIP-with-reason when the repo has no remote. Supersedes the standalone
    gh-auth check: for provider github it performs the gh auth probe; for
    azure-devops it checks `az`/PAT.
    """
    if not _has_remote(profile):
        return Result.SKIP, "no git remote — forge provider not applicable", ""

    provider, reason = _forge_provider_verdict(profile)
    if provider is None:
        if reason == "no-remote":
            return Result.SKIP, "no git remote — forge provider not applicable", ""
        if reason == "forge-partial-missing":
            return (
                Result.FAIL,
                "partials/forge.sh not found — forge adapter is not installed",
                "re-run /init (/adlc:init on the plugin install) to vendor partials, or check the toolkit checkout",
            )
        # Unrecognized host / unresolved: fail loud (BR-2) with config remediation.
        return (
            Result.FAIL,
            "could not resolve a forge provider (unrecognized origin host?)",
            "set forge.provider in .adlc/config.yml to one of: github, azure-devops",
        )

    if provider == "github":
        if not shutil.which("gh"):
            install = ("brew install gh" if profile.os == "Darwin"
                       else "see https://github.com/cli/cli#installation")
            return Result.FAIL, "forge=github but gh (GitHub CLI) is not on PATH", install
        # Fold in the gh auth probe (the superseded gh-auth check).
        auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if auth.returncode != 0:
            return Result.FAIL, "forge=github: gh is not authenticated", "gh auth login"
        return Result.PASS, "forge=github: gh present and authenticated", ""

    if provider == "azure-devops":
        if not shutil.which("az"):
            return (
                Result.FAIL,
                "forge=azure-devops but az (Azure CLI) is not on PATH",
                "brew install azure-cli && az extension add --name azure-devops"
                if profile.os == "Darwin"
                else "install the Azure CLI + azure-devops extension "
                     "(https://learn.microsoft.com/cli/azure/install-azure-cli)",
            )
        # Either an az login session OR a PAT env var named in config satisfies auth.
        acct = subprocess.run(["az", "account", "show"], capture_output=True, text=True)
        pat_var, pat_set = _forge_pat_status(profile)
        if acct.returncode == 0 or pat_set:
            how = "az login session" if acct.returncode == 0 else f"PAT env var {pat_var}"
            return Result.PASS, f"forge=azure-devops: authenticated via {how}", ""
        remediation = "az login"
        if pat_var:
            remediation = f"az login   # or set the PAT env var {pat_var}"
        return (
            Result.FAIL,
            "forge=azure-devops: no az login session and PAT env var not set",
            remediation,
        )

    return Result.FAIL, f"unknown forge provider '{provider}'", \
        "set forge.provider to github or azure-devops in .adlc/config.yml"


def _forge_pat_status(profile: Profile):
    """Return (pat_var_name, is_set). Reads forge.auth from config (a var NAME).

    Reuses tools/adlc/forge_config.parse_forge_config via subprocess probe so
    checks keeps no hard import of the forge module at registry-build time.
    The probe runs in ``_delegate_interpreter()`` — the interpreter that has
    PyYAML where delegation is installed — so the probe reads the config the
    same way the real call does (REQ-609 BR-8, LESSON-392). A malformed config
    makes the reader exit non-zero, which lands here as "no PAT var", and the
    `pyyaml`/`forge` checks report the real cause.
    """
    reader = os.path.join(profile.repo_root, "tools", "adlc", "forge_config.py")
    if not os.path.isfile(reader):
        return "", False
    cfg_proj = os.path.join(os.getcwd(), ".adlc", "config.yml")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import forge_config as fc; "
        "d = fc.parse_forge_config(sys.argv[2]); print(d.get('auth', ''))"
    )
    try:
        out = subprocess.run(
            [_delegate_interpreter(), "-c", code, os.path.dirname(reader), cfg_proj],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        # An interpreter that will not run, or will not finish, is "no PAT var"
        # here; the `pyyaml` check reports the real cause.
        return "", False
    auth = out.stdout.strip() if out.returncode == 0 else ""
    # 'gh'/'az' are CLI-login sources, not PAT var names.
    if not auth or auth in ("gh", "az"):
        return "", False
    return auth, bool(os.environ.get(auth))


# --- reservation namespace pushability (REQ-546 BR-13) ---------------------

def _classify_git_failure(stderr: str) -> str:
    """Name the failing layer from a git push/ls-remote stderr (BR-13).

    Ordered most-specific first. Auth and server-policy declines are distinct
    failure modes a machine operator must fix differently; transport is the
    catch-all connectivity bucket.
    """
    s = (stderr or "").lower()
    # 403 only as a standalone number: git echoes refs and object ids in its
    # stderr, and a hex token such as the doctor's random probe ref can hold
    # "403" (one nonce in about 300).
    if ("authentication failed" in s or "permission denied" in s
            or re.search(r"\b403\b", s)
            or "could not read username" in s or "invalid username or password" in s):
        return "auth"
    if ("pre-receive hook declined" in s or "[remote rejected]" in s
            or "protected branch" in s or "denied" in s):
        return "server policy"
    if ("could not read from remote" in s or "does not appear to be a git repository" in s
            or "could not resolve host" in s or "unable to access" in s
            or "connection" in s or "timed out" in s or "network" in s):
        return "transport"
    return "unknown"


def check_reservations(profile: Profile):
    """Reservation ref namespace is readable AND writable on origin (BR-13).

    A machine that silently cannot push reservations allocates permanently
    degraded — the one remaining duplicate source REQ-546 leaves open by design —
    so doctor catches it. Probes: (1) ls-remote the namespace (read + transport +
    read-auth); (2) push an EPHEMERAL probe ref that is actually pushed and deleted
    (`refs/adlc/ids/_probe/<nonce>` — `_probe` is not a real kind, so it reserves
    nothing; the delete is the ONE sanctioned deletion). A `git push --dry-run` is
    NOT a substitute — it never exercises server-side pre-receive policy, exactly the
    layer this check exists to catch. Pure subprocess, no dependency on the mechanism
    it diagnoses (LESSON-395). SKIP-with-reason on a remote-less repo.
    """
    if not _has_remote(profile):
        return Result.SKIP, "no git remote — reservation namespace not applicable", ""

    # GIT_TERMINAL_PROMPT=0 so an auth-required remote fails fast (reported as a layer)
    # instead of hanging the whole doctor run on a credential prompt.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    # 1. Readability (also exercises transport + read auth).
    read = subprocess.run(
        ["git", "ls-remote", "origin", "refs/adlc/ids/*"],
        capture_output=True, text=True, env=env,
    )
    if read.returncode != 0:
        layer = _classify_git_failure(read.stderr)
        return (
            Result.FAIL,
            f"reservation namespace not readable ({layer})",
            "verify `git ls-remote origin` works — reservations live under refs/adlc/ids/*",
        )

    # 2. Writability via a real ephemeral probe ref. Probe object: a tiny throwaway
    #    commit over the empty tree (git commit-tree needs a configured identity — if
    #    unset, SKIP and defer to the git-identity check rather than false-passing).
    tree = subprocess.run(
        ["git", "hash-object", "-w", "-t", "tree", os.devnull],
        capture_output=True, text=True,
    ).stdout.strip() or "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ct = subprocess.run(
        ["git", "commit-tree", tree],
        input="adlc-doctor-reservation-probe\n", capture_output=True, text=True,
    )
    obj = ct.stdout.strip()
    if not obj:
        return (
            Result.SKIP,
            "cannot build a probe object (git identity unset — see git-identity check)",
            "",
        )

    proberef = "refs/adlc/ids/_probe/" + os.urandom(8).hex()
    push = subprocess.run(
        ["git", "push", "origin", f"{obj}:{proberef}"],
        capture_output=True, text=True, env=env,
    )
    if push.returncode != 0:
        layer = _classify_git_failure(push.stderr)
        return (
            Result.FAIL,
            f"reservation namespace not writable ({layer})",
            "grant push access to refs/adlc/ids/* on origin — otherwise id allocation "
            "runs permanently degraded (ids get verified late by the REQ-545 recheck)",
        )
    # Cleanup: delete the probe ref (the ONE sanctioned deletion — it reserves nothing).
    subprocess.run(
        ["git", "push", "origin", "--delete", proberef],
        capture_output=True, text=True, env=env,
    )
    return Result.PASS, "reservation namespace readable and writable on origin", ""


# --- git identity ----------------------------------------------------------

def check_git_identity(profile: Profile):
    def _cfg(key):
        return subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True,
        ).stdout.strip()

    name, email = _cfg("user.name"), _cfg("user.email")
    if name and email:
        return Result.PASS, f"git identity: {name} <{email}>", ""
    missing = []
    if not name:
        missing.append('git config --global user.name "Your Name"')
    if not email:
        missing.append('git config --global user.email "you@example.com"')
    return (
        Result.FAIL,
        "git identity is not fully set ("
        + ", ".join(k for k, v in (("user.name", name), ("user.email", email)) if not v)
        + " missing)",
        " && ".join(missing),
    )


# --- delegation gate (REUSES REQ-515, ADR-4) -------------------------------

def _gate_verdict(profile: Profile):
    """Return (rc, reason) from sourcing partials/delegate-gate.sh under bash.

    Captures the function's own rc into a var BEFORE echoing (the partial's
    documented protocol) so the echo does not clobber $?.
    """
    partial = _partial_path(profile, "delegate-gate.sh")
    if not os.path.isfile(partial):
        return None, "gate-partial-missing"
    # Shell-quoted, as in ``_forge_provider_verdict``.
    script = (
        f". {_q(partial)}; adlc_delegate_gate_check; rc=$?; "
        'printf "%s\\n%s\\n" "$rc" "$ADLC_DELEGATE_GATE_REASON"'
    )
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True,
    ).stdout.splitlines()
    if len(out) < 2:
        return None, "gate-probe-failed"
    try:
        return int(out[0].strip()), out[1].strip()
    except ValueError:
        return None, "gate-probe-unparsable"


def _config_enabled(profile: Profile):
    """True iff delegate.enabled is true in the REQ-515 config.

    Reuses tools/delegate/_common.parse_delegate_config via a subprocess probe so
    adlc keeps no hard import dependency on the delegate module (it may be absent
    on a skills-only checkout). Returns False on any failure (treated as
    not-opted-in). (REQ-522 renamed tools/kimi -> tools/delegate.)

    The probe runs in ``_delegate_interpreter()``: the config is parsed with
    PyYAML since REQ-609, and the venv is where ``install.sh`` pins it — probing
    with a bare ``python3`` from ``$PATH`` would answer for an interpreter the
    real call never uses (BR-8, LESSON-392).
    """
    common_dir = os.path.join(profile.repo_root, "tools", "delegate")
    if not os.path.isfile(os.path.join(common_dir, "_common.py")):
        return False
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import _common; "
        "print('1' if _common.parse_delegate_config().get('enabled') else '0')"
    )
    try:
        out = subprocess.run(
            [_delegate_interpreter(), "-c", code, common_dir],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and out.stdout.strip() == "1"


# --- PyYAML in the interpreter adlc runs under (REQ-609 BR-8, ADR-2) -------

def _pyyaml_requirement(root: str) -> str:
    """The ``pyyaml`` line of the toolkit's delegate requirements, e.g. ``pyyaml==6.0.3``.

    Read from ``tools/delegate/requirements.txt`` so the pin lives in one
    place; a missing file or line gives the bare name.
    """
    text = _read_text(os.path.join(root, "tools", "delegate", "requirements.txt")) or ""
    for line in text.splitlines():
        spec = line.split("#", 1)[0].strip()
        name = spec
        for sep in "=<>!~;[ ":
            name = name.split(sep, 1)[0]
        if name.lower() == "pyyaml":
            return spec
    return "pyyaml"


#: Where the machine-config scaffold's text lives: the plugin's SessionStart
#: hook. test_config_scaffold_parity.py pins the bytes that hook writes to the
#: bytes install.sh's `ensure_config` writes, and that this reader returns, so
#: the doctor compares against that one source rather than a third copy.
_SCAFFOLD_SOURCE = ("scripts", "session-start.sh")
#: The hook's assignment of the scaffold text: one single-quoted shell word.
_SCAFFOLD_OPEN = b"\nadlc_ss_scaffold='"


def _config_scaffold(root: str):
    """The bytes a fresh machine config holds, as the hook and install.sh write them.

    Read off the hook's ``adlc_ss_scaffold='...'`` assignment under ``root``;
    the write adds one newline. ``None`` when the hook is missing or its
    assignment is not that one single-quoted word, so the check does not skip.
    """
    try:
        with open(os.path.join(root, *_SCAFFOLD_SOURCE), "rb") as fh:
            text = fh.read()
    except OSError:
        return None
    if text.count(_SCAFFOLD_OPEN) != 1:
        return None
    body = text.split(_SCAFFOLD_OPEN, 1)[1]
    if b"'" not in body:
        return None
    return body.split(b"'", 1)[0] + b"\n"


def _is_untouched_scaffold(path: str, root: str) -> bool:
    """True when the file at ``path`` is byte for byte the config scaffold."""
    scaffold = _config_scaffold(root)
    if scaffold is None:
        return False
    try:
        with open(path, "rb") as fh:
            return fh.read(len(scaffold) + 1) == scaffold
    except OSError:
        return False


def check_pyyaml(profile: Profile):
    """Is PyYAML importable in the interpreter that parses the ADLC config?

    Since REQ-609 the machine config is parsed by ``yaml.safe_load`` behind a
    strict schema, and a missing PyYAML is not a silent degradation: the
    delegate consumer refuses outright, and the forge consumer proceeds
    unconfigured after a stderr line — silently overriding a written
    `forge.provider` with origin-URL auto-detection. So doctor reports the
    interpreter THE RULE selects, and says when the venv is being bypassed
    because it has no PyYAML of its own.

    **SKIP has two shapes**, both with no delegate venv and no project
    config: no machine config either, or a machine config that is byte for
    byte the delegation-off scaffold install.sh and the plugin's SessionStart
    hook write. The hook writes that file on every plugin machine, and a fresh
    Mac's system ``python3`` has no PyYAML, so without the second shape the
    plugin route's first ``adlc doctor`` would FAIL (REQ-669 AC-1). Read
    without PyYAML, the scaffold changes nothing: delegation stays off and the
    forge stays unconfigured, which is what it says. A red row for a parser
    with nothing to change teaches operators to ignore the verdict. A project
    config, an edited machine config, or a venv makes the check live again.

    The probe is a subprocess, never an import here — this module must load on
    a machine that has no PyYAML at all (LESSON-395) — and it is bounded, so a
    stalled interpreter is a FAIL rather than a doctor that never returns.
    """
    interp = _delegate_interpreter()
    venv = _delegate_venv()
    state = _venv_state()
    machine_cfg = _machine_config_path()
    project_cfg = os.path.join(os.getcwd(), ".adlc", "config.yml")
    configs = [p for p in (machine_cfg, project_cfg) if os.path.isfile(p)]

    if state == "absent" and not configs:
        return (
            Result.SKIP,
            "no delegate venv and no ADLC config to parse yet (looked at "
            f"{machine_cfg} and {project_cfg})",
            "",
        )
    if state == "absent" and configs == [machine_cfg] \
            and _is_untouched_scaffold(machine_cfg, profile.repo_root):
        return (
            Result.SKIP,
            f"{machine_cfg} is the unedited delegation-off scaffold install.sh and the "
            f"plugin's SessionStart hook write, with no project config at {project_cfg} "
            "and no delegate venv: read without PyYAML it sets nothing. Editing that file, "
            "or adding a project config, makes this check live",
            "",
        )

    # The fix has to be correct for the CASE (BR-5). `install.sh
    # --with-delegation` creates or refreshes the venv, which is what pins
    # PyYAML at the version the toolkit tests against. The retired alternative,
    # `python3 -m pip install --user 'pyyaml>=6.0'`, was neither: pip refuses
    # `--user` inside a venv, and outside one it bypasses the `==6.0.3` pin.
    # On the plugin route install.sh is not the fix: run from the plugin's copy
    # it would symlink that copy into ~/.claude and double the install (BR-11).
    # The interpreter gets the pinned requirement directly instead, with
    # `--user` only outside the venv. A failed route detection gets the same,
    # since it may be the plugin route.
    if not _install_sh_ok(profile):
        user = "" if venv and interp == os.path.join(venv, "bin", "python3") else " --user"
        installer = "%s -m pip install%s %s" % (
            _q(interp), user, _q(_pyyaml_requirement(profile.repo_root)))
    else:
        installer = _q(os.path.join(profile.repo_root, "install.sh")) + " --with-delegation"
    if state == "no-pyyaml":
        pip_fix = "%s install -r %s" % (
            _q(os.path.join(venv, "bin", "pip")),
            _q(os.path.join(profile.repo_root, "tools", "delegate", "requirements.txt")),
        )
        fix = "%s   # or: %s" % (pip_fix, installer)
        note = (" (falling back from %s, which has no PyYAML — a venv created "
                "before REQ-609 carries openai only)" % (venv,))
        # On a PASS the fix goes in the DETAIL too, because `format_report`
        # prints `remediation` on FAIL only — and the interesting case here IS a
        # PASS: the config parses fine under $PATH's python3 while every
        # delegate CLI, which `exec`s the venv unconditionally, cannot parse it
        # at all. On a FAIL the remediation line carries it, so repeating it in
        # the detail would only make a long line longer.
        pass_note = "%s; fix: %s)" % (note[:-1], pip_fix)
    else:
        fix = installer
        note = ""
        pass_note = ""

    try:
        probe = subprocess.run(
            [interp, "-c", "import yaml; print(yaml.__version__)"],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            Result.FAIL,
            f"{interp} did not answer the PyYAML probe within "
            f"{_PROBE_TIMEOUT_SECONDS}s{note}",
            fix,
        )
    except OSError as exc:
        # The selected interpreter could not be executed at all. Still a FAIL
        # with the same fix — doctor reports, it never crashes.
        return (
            Result.FAIL,
            f"could not run {interp} to check PyYAML ({exc.strerror or exc}){note}",
            fix,
        )
    version = probe.stdout.strip()
    if probe.returncode == 0 and version:
        return Result.PASS, f"PyYAML {version} in {interp}{pass_note}", (fix if note else "")
    return (
        Result.FAIL,
        f"PyYAML is not importable in {interp}{note} — the ADLC config "
        f"({', '.join(configs) or machine_cfg}) cannot be parsed there",
        fix,
    )


def check_delegate_gate(profile: Profile):
    rc, reason = _gate_verdict(profile)
    if rc == 0:
        return Result.PASS, "delegation enabled and reachable", ""
    if rc == 1:
        # opt-in off, or explicitly disabled — not a failure (BR-9 default).
        return Result.SKIP, f"delegation not active ({reason})", ""
    if rc == 2:
        # adlc-read not on PATH. Only a FAIL if config asked for delegation
        # (misconfigured); otherwise it is the expected not-opted-in posture.
        if _config_enabled(profile):
            if not _install_sh_ok(profile):
                # The plugin ships no delegation CLIs, and install.sh from its
                # copy would double the install, so the config edit is the fix.
                # A failed route detection may be the plugin route.
                fix = ("set delegate.enabled: false in %s   "
                       "# the adlc plugin does not install the delegation CLIs"
                       % _q(_machine_config_path()))
            else:
                fix = ("./install.sh --with-delegation   # installs the delegate shims, "
                       "or set delegate.enabled: false in %s" % _q(_machine_config_path()))
            return (
                Result.FAIL,
                "delegation config sets enabled: true but adlc-read is not on PATH",
                fix,
            )
        return Result.SKIP, "delegation not enabled (adlc-read not installed)", ""
    # rc is None — the gate probe itself failed.
    return (
        Result.FAIL,
        f"could not evaluate the delegation gate ({reason})",
        "verify partials/delegate-gate.sh is present and bash is on PATH",
    )


# --- counters --------------------------------------------------------------

def _lock_is_stale(lock_dir: str) -> bool:
    try:
        age = time.time() - os.path.getmtime(lock_dir)
    except OSError:
        return False
    return age > _STALE_LOCK_SECONDS


def check_counters(profile: Profile):
    base = _adlc_home()
    problems = []
    fixes = []
    for name in _COUNTERS:
        path = os.path.join(base, name)
        lock = path + ".lock.d"
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = fh.read().strip()
            except OSError as exc:
                # Use strerror, not str(exc): OSError.__str__ embeds the absolute
                # filename, which leaks into the report/CI logs (LESSON-021).
                problems.append(f"{name} unreadable ({exc.strerror or 'I/O error'})")
                fixes.append("ls -l %s" % _q(path))
                continue
            if not raw.isdigit():
                problems.append(f"{name} is not numeric ('{raw}')")
                fixes.append("printf '<correct-next-number>' > %s" % _q(path))
        # A counter that does not exist yet is fine (first run) — not flagged.
        if os.path.isdir(lock) and _lock_is_stale(lock):
            problems.append(f"{name} has a stale lock dir")
            fixes.append("rmdir %s" % _q(lock))
    if problems:
        return Result.FAIL, "; ".join(problems), " && ".join(fixes)
    return Result.PASS, "global counters present, numeric, no stale locks", ""


# --- launchctl (macOS-only, opt-in) ----------------------------------------

def check_launchctl(profile: Profile):
    # applies_to already gates this off on non-Darwin (BR-6). Reaching here means
    # macOS. The LaunchAgent only matters when delegation is opted in.
    rc, _reason = _gate_verdict(profile)
    if rc != 0:
        return Result.SKIP, "delegation not active — launchctl setenv not required", ""
    # REQ-522 renamed the LaunchAgent label; the installer migrates the old one.
    label = "com.adlc-toolkit.delegate-setenv"
    listed = subprocess.run(
        ["launchctl", "list", label], capture_output=True, text=True,
    )
    if listed.returncode == 0:
        return Result.PASS, f"LaunchAgent {label} is loaded", ""
    plist = os.path.join(
        os.path.expanduser("~"), "Library", "LaunchAgents", label + ".plist",
    )
    return (
        Result.FAIL,
        f"LaunchAgent {label} is not loaded",
        "launchctl bootstrap gui/$(id -u) %s" % _q(plist),
    )


# --- template version (consumer-project staleness pointer) -----------------

def check_template_version(profile: Profile):
    # Only meaningful inside a consumer project that vendored templates.
    project_templates = os.path.join(os.getcwd(), ".adlc", "templates")
    if not os.path.isdir(project_templates):
        return Result.SKIP, "not inside a consumer project with vendored templates", ""
    return (
        Result.PASS,
        "project .adlc/templates present — run /template-drift to compare with toolkit",
        "",
    )


# --- harness:<name> (report-only, never fails the verdict, REQ-654 BR-9) ----
#
# One check per harness `adlc harness detect` knows, built from its table so the
# two can never disagree about the harness set. The former `claude-code` check
# is `harness:claude` now (REQ-519 open question 2, resolved the same way): a
# present binary is reported with its version and mount state, an absent one
# SKIPs, and nothing here is ever a FAIL. Whether ~/.agents/skills reaches the
# toolkit is `agents-skills-mount`'s question, which does fail.

def _harness_check(name: str):
    def run(profile: Profile):
        import harness
        p = harness.probe(name, profile.repo_root)
        if p.state != "present":
            return (Result.SKIP,
                    f"{p.binary} not detected on PATH (report-only)", "")
        return (Result.PASS,
                f"{p.binary} -> {p.path} (version: {p.version}; skills mount: "
                f"{p.mount}){_harness_facts(name)} (report-only; not gated)", "")
    run.__name__ = "check_harness_" + name
    return run


def _harness_facts(name: str) -> str:
    """The adapter's ``doctor_rows`` facts, as text to report (REQ-656 BR-10)."""
    import harness_adapter
    import harness_doctor
    try:
        adapter = harness_adapter.resolve_adapter(name)
    except harness_adapter.AdapterError:
        return ""
    return "".join("; " + line for line in harness_doctor.fact_lines(adapter))


def _harness_checks():
    import harness
    return [Check("harness:" + name, _harness_check(name)) for name in harness.NAMES]


# --- render-currency:<name> (REQ-657 BR-15) ---------------------------------
#
# One framework check per harness detect knows, driven by that harness's adapter:
# the adapter validates (BR-1), every user-level surface it renders equals a fresh
# render, and its data-declared doctor_rows hold. `adlc harness doctor` calls the
# same function (harness_doctor.render_currency), so there is one copy of the code.

def _render_currency_check(name: str):
    def run(profile: Profile):
        import harness_doctor
        status, detail, remediation = harness_doctor.render_currency(name)
        result = {"PASS": Result.PASS, "FAIL": Result.FAIL}.get(status, Result.SKIP)
        return result, detail, remediation
    run.__name__ = "check_render_currency_" + name
    return run


def _render_currency_checks():
    import harness
    return [Check("render-currency:" + name, _render_currency_check(name))
            for name in harness.NAMES]


# --- the adapters' doctor_rows (REQ-655 BR-9) -------------------------------
#
# Each row an adapter declares without a `fact` is a check of its own, by the row's
# id: data, no check code per harness. Dropping the row from the adapter drops the
# check. An adapter that does not load adds none: render-currency reports it.

def _row_check(name: str, row_id: str):
    def run(profile: Profile):
        import harness_adapter
        import harness_doctor
        adapter = harness_adapter.resolve_adapter(name)
        skip = None
        if not harness_doctor.binary_present(adapter):
            skip = "%s not detected on PATH" % adapter["binary"]
        for rid, status, detail, remedy in harness_doctor.row_outcomes(
                adapter, harness_adapter.toolkit_dir(), skip_reason=skip):
            if rid == row_id:
                result = {"PASS": Result.PASS, "FAIL": Result.FAIL}.get(status, Result.SKIP)
                return result, detail, remedy
        return Result.SKIP, "%s declares no row %s" % (name, row_id), ""
    run.__name__ = "check_row_" + row_id.replace("-", "_")
    return run


def _doctor_row_checks():
    import harness_adapter
    checks = []
    for path in harness_adapter.shipped_adapter_paths():
        try:
            adapter = harness_adapter.load_adapter(path)
        except (harness_adapter.AdapterError, OSError):
            continue
        for row in adapter.get("doctor_rows", []):
            if "fact" not in row:
                checks.append(Check(row["id"], _row_check(adapter["name"], row["id"])))
    return checks


# --- registry (report order) ----------------------------------------------

REGISTRY = [
    # Reports the route every later check is gated on, so it runs first (ADR-7).
    Check("plugin-route", check_plugin_route),
    # The six checks of what install.sh builds SKIP on the plugin route: these
    # two, the view and the mount below, toolkit-clean and path-shims.
    Check("skills-symlink", check_skills_symlink,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    Check("agents-symlink", check_agents_symlink,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    # Runs on both routes: either one can find the other installed (BR-11).
    Check("doubled-install", check_doubled_install),
    # What install.sh builds for the non-Claude harnesses (REQ-654 BR-9).
    Check("skills-view", check_skills_view,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    Check("agents-skills-mount", check_agents_skills_mount,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    Check("toolkit-clean", check_toolkit_clean,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    Check("path-shims", check_path_shims,
          applies_to=_on_symlink_route, skip_notice=_SYMLINK_ROUTE_ONLY),
    Check("gh-present", check_gh_present),
    # `forge` supersedes the standalone gh-auth check (REQ-520 ADR-4): it folds the
    # gh auth probe in for provider github and handles azure-devops auth too.
    Check("forge", check_forge),
    Check("reservations", check_reservations),
    Check("git-identity", check_git_identity),
    Check("delegate-gate", check_delegate_gate),
    # Reads on the interpreter BOTH config consumers use, so it is registered
    # next to the delegation check it explains (REQ-609 ADR-2).
    Check("pyyaml", check_pyyaml),
    Check("counters", check_counters),
    Check(
        "launchctl",
        check_launchctl,
        applies_to=lambda p: p.os == "Darwin",
        skip_notice="launchctl is macOS-only",
    ),
    Check("template-version", check_template_version),
    # Machine-wide: every consumer's vendored partials against the canonical ones.
    Check("consumer-sync", check_consumer_sync),
] + _harness_checks() + _render_currency_checks() + _doctor_row_checks()
