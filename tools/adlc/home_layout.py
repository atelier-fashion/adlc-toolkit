#!/usr/bin/env python3
"""What a migrated toolkit home looks like (REQ-663 ADR-5).

One statement of the layout, read two ways: ``adlc doctor``'s ``home-layout`` check
reports :func:`inspect`'s findings as a FAIL, and ``migrate_home.py`` reads the same
findings as its plan, so what doctor complains about and what a repair does cannot
drift. No finding means healthy.

The inventory below was enumerated from the code that reads the home, not from the
spec's list. What never moves: REQ-654 BR-3's two compatibility aliases (Claude Code's
skills mount and the plugin-root pointer), its agents mount, its own files, and
``adlc/harness-probe/``, whose recovery markers name the home they were written under
(a marker refuses the migration; see ``migrate_home.py``).

Reads only. Pure standard library, because doctor must diagnose a half-migrated
machine without the venv it is checking (LESSON-395): nothing here imports
``_machine_config`` or PyYAML, and JSON is the only format parsed. The default home
comes from ``adlc_home.default_home``, the one place it is spelled.
"""

import glob
import json
import os
import re
from typing import List, NamedTuple, Optional, Tuple

import adlc_home

#: The machine-global counters. Each gets a compatibility symlink and a lock tombstone.
COUNTERS = (".global-next-req", ".global-next-bug", ".global-next-lesson")
LOCK_SUFFIX = ".lock.d"
LEDGER = ".adlc-own-reservations"
CONFIG = os.path.join("adlc", "config.yml")
VENV = "delegate-venv"
VIEW = os.path.join("adlc", "skills-view")
HELPER = "delegate-launchctl-setenv.sh"
PROBE_DIR = os.path.join("adlc", "harness-probe")
#: The two links a home keeps to the clone. Each is checked as a link and never read
#: through: toolkit reads go through ToolkitRoot.
MOUNT_NAMES = ("skills", "agents")
#: Every ``move`` item, as paths relative to a home.
MOVED_FILES = COUNTERS + (LEDGER, CONFIG)

BIN_WRAPPERS = ("adlc-read", "adlc-write", "extract-chat")
PLIST_LABEL = "com.adlc-toolkit.delegate-setenv"
RC_MARKER = "# >>> adlc-toolkit (REQ-519) >>>"
RC_MARKER_END = "# <<< adlc-toolkit (REQ-519) <<<"
_RC_LINE_RE = re.compile(r'^export ADLC_HOME="(.*)"$')

#: Names a toolkit home may hold (BR-2): anything else in ``<dir>`` is foreign.
HOME_ENTRIES = frozenset(COUNTERS + tuple(c + LOCK_SUFFIX for c in COUNTERS)
                         + (LEDGER, "adlc", VENV, HELPER) + MOUNT_NAMES)
HOME_ADLC_ENTRIES = frozenset(("config.yml", "skills-view", "harness-probe"))

BACKUP_PREFIX = ".adlc-home-backup-"
TOMBSTONE_MARK = "adlc-toolkit tombstone"


class Finding(NamedTuple):
    """One way the machine differs from the layout. ``step`` names the flip step."""
    step: str
    item: str
    detail: str


class Facts(NamedTuple):
    """Everything :func:`inspect` reads about the machine, gathered once."""
    default: str        # the default home, where the old paths are
    home: str           # the migrated home being checked
    repo_root: str      # the clone
    rc_file: str        # the login shell's rc file
    bin_dir: str        # the user's bin directory
    plist: str          # the LaunchAgent plist
    agents_mount: str   # the mount the other harnesses read
    skills_files: Tuple[str, ...]  # harness skills surfaces that name the view


def user_home() -> str:
    return os.path.dirname(adlc_home.default_home())


def mount_targets(repo_root: str) -> List[Tuple[str, str]]:
    """``(name, what it must resolve to)`` per link a home keeps to the clone."""
    return [(MOUNT_NAMES[0], repo_root), (MOUNT_NAMES[1], os.path.join(repo_root, MOUNT_NAMES[1]))]


def rc_file_for(login_shell: Optional[str]) -> str:
    """The rc file install.sh's ``login_rc_file`` picks for a login shell."""
    home = user_home()
    shell = login_shell or ""
    if shell.endswith("zsh"):
        return os.path.join(home, ".zshrc")
    if shell.endswith("bash"):
        return os.path.join(home, ".bash_profile")
    return os.path.join(home, ".profile")


def lock_path(home: str, counter: str) -> str:
    return os.path.join(home, counter + LOCK_SUFFIX)


def harness_skills_files() -> Tuple[str, ...]:
    """Every user-level ``skills`` surface an adapter renders, from the adapters.

    Read from data, so no harness name enters this module. An adapter that does not
    load is ``render-currency``'s to report.
    """
    import harness_adapter as ha
    out = []
    for path in ha.shipped_adapter_paths():
        try:
            spec = ha.load_adapter(path)["paths"].get(ha.SKILLS_SURFACE) or {}
            if spec.get("mode") == "rendered" and spec.get("user"):
                out.append(ha.expand_user_path(spec["user"]))
        except (ha.AdapterError, OSError, ValueError):
            continue
    return tuple(out)


def machine_facts(home: str, repo_root: str, rc_file: str) -> Facts:
    user = user_home()
    return Facts(
        default=adlc_home.default_home(),
        home=home,
        repo_root=repo_root,
        rc_file=rc_file,
        bin_dir=os.path.join(user, "bin"),
        plist=os.path.join(user, "Library", "LaunchAgents", PLIST_LABEL + ".plist"),
        agents_mount=os.path.join(user, ".agents", MOUNT_NAMES[0]),
        skills_files=harness_skills_files(),
    )


# --- what the machine says about itself --------------------------------------

def raw_pointer() -> Optional[str]:
    """The pointer's first line, unvalidated, or ``None`` with no readable pointer.

    Not the resolver: this runs on machines the resolver refuses.
    """
    path = adlc_home.pointer_path()
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        return adlc_home.read_pointer_line(path) or None
    except OSError:
        return None


def traced_home(default: Optional[str] = None) -> Optional[str]:
    """The home a compatibility symlink at an old path names, or ``None``."""
    base = default or adlc_home.default_home()
    for name in COUNTERS:
        path = os.path.join(base, name)
        if os.path.islink(path):
            target = os.readlink(path)
            if target.startswith("/"):
                return os.path.dirname(target)
    path = os.path.join(base, CONFIG)
    if os.path.islink(path):
        target = os.readlink(path)
        if target.startswith("/"):
            return os.path.dirname(os.path.dirname(target))
    return None


def has_tombstone(default: Optional[str] = None) -> bool:
    base = default or adlc_home.default_home()
    return any(os.path.isfile(lock_path(base, c)) and not os.path.islink(lock_path(base, c))
               for c in COUNTERS)


def persisted_home() -> Tuple[str, str]:
    """``(home, how)`` read without the variable: ``pointer``, ``traces`` or ``default``."""
    default = adlc_home.default_home()
    pointed = raw_pointer()
    if pointed:
        return pointed, "pointer"
    traced = traced_home(default)
    if traced:
        return traced, "traces"
    return default, "default"


def is_migrated() -> bool:
    """A pointer in any state, or what a migration leaves at the old paths."""
    default = adlc_home.default_home()
    return (os.path.lexists(adlc_home.pointer_path()) or traced_home(default) is not None
            or has_tombstone(default))


def rc_home_line(text: str) -> Optional[str]:
    """The value of the ``ADLC_HOME`` line inside the REQ-519 block, or ``None``."""
    inside = False
    for line in text.splitlines():
        if line == RC_MARKER:
            inside = True
        elif line == RC_MARKER_END:
            inside = False
        elif inside:
            found = _RC_LINE_RE.match(line)
            if found:
                return found.group(1)
    return None


def rc_with_home(text: str, home: str, path_line: str) -> str:
    """``text`` with the block carrying exactly one ``ADLC_HOME`` line for ``home``.

    The block is created when the rc file has none, as ``ensure_path`` would, so a
    machine whose rc file lost it still gets the setting. Idempotent.
    """
    want = 'export ADLC_HOME="%s"' % home
    lines = text.split("\n")
    if RC_MARKER not in lines:
        tail = "" if text == "" or text.endswith("\n") else "\n"
        return "%s%s%s\n%s\n%s\n%s\n" % (text, tail, RC_MARKER, path_line, want, RC_MARKER_END)
    out, inside, done = [], False, False
    for line in lines:
        if line == RC_MARKER:
            inside = True
        elif line == RC_MARKER_END:
            if inside and not done:
                out.append(want)
                done = True
            inside = False
        elif inside and _RC_LINE_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def rc_without_home(text: str) -> str:
    """``text`` with the block's ``ADLC_HOME`` line gone and everything else untouched."""
    out, inside = [], False
    for line in text.split("\n"):
        if line == RC_MARKER:
            inside = True
        elif line == RC_MARKER_END:
            inside = False
        elif inside and _RC_LINE_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def venv_ready(home: str) -> bool:
    """THE ONE INTERPRETER RULE's question, for any home (REQ-609 BR-8)."""
    venv = os.path.join(home, VENV)
    exe = os.path.join(venv, "bin", "python3")
    if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
        return False
    pattern = os.path.join(glob.escape(venv), "lib", "python*", "site-packages", "yaml")
    return any(os.path.isdir(p) for p in glob.glob(pattern))


def skills_view_of(path: str) -> Optional[str]:
    """The skills-view path a harness ``skills`` surface names, or ``None``."""
    text = read_text(path)
    if text is None:
        return None
    try:
        entries = json.loads(text).get("entries", [])
    except (ValueError, AttributeError):
        return None
    for entry in entries if isinstance(entries, list) else []:
        value = entry.get("path") if isinstance(entry, dict) else None
        if isinstance(value, str) and value.endswith(os.sep + VIEW):
            return value
    return None


# --- the comparison ----------------------------------------------------------

def _inspect_moved(f: Facts) -> List[Finding]:
    out = []
    for name in COUNTERS:
        old, new = os.path.join(f.default, name), os.path.join(f.home, name)
        if os.path.islink(old):
            if os.readlink(old) != new:
                out.append(Finding("counters", old, "points at %s, not %s"
                                   % (os.readlink(old), new)))
        elif os.path.lexists(old):
            out.append(Finding("counters", old, "a regular file remains at the old path"))
        else:
            out.append(Finding("counters", old, "no compatibility symlink"))
    old, new = os.path.join(f.default, CONFIG), os.path.join(f.home, CONFIG)
    if os.path.islink(old):
        if os.readlink(old) != new:
            out.append(Finding("config", old, "points at %s, not %s" % (os.readlink(old), new)))
        elif not os.path.exists(new):
            out.append(Finding("config", new, "missing, and the compatibility symlink dangles, "
                                              "which the config loader refuses"))
    elif os.path.lexists(old):
        out.append(Finding("config", old, "a regular file remains at the old path"))
    elif os.path.exists(new):
        out.append(Finding("config", old, "no compatibility symlink to %s" % new))
    old = os.path.join(f.default, LEDGER)
    if os.path.lexists(old):
        out.append(Finding("ledger", old, "the ledger remains at the old path"))
    return out


def _inspect_locks(f: Facts) -> List[Finding]:
    out = []
    for name in COUNTERS:
        lock = lock_path(f.default, name)
        if os.path.islink(lock):
            out.append(Finding("tombstones", lock, "a symlink, not a tombstone"))
        elif os.path.isdir(lock):
            out.append(Finding("tombstones", lock,
                               "a directory: a stale allocator crashed here, or the tombstone "
                               "was removed"))
        elif not os.path.isfile(lock):
            out.append(Finding("tombstones", lock, "lockable: no tombstone"))
    return out


def _inspect_stamps(f: Facts) -> List[Finding]:
    out = []
    shim = os.path.join(f.bin_dir, "adlc")
    text = read_text(shim)
    if text is not None and adlc_home.POINTER_NAME not in text:
        out.append(Finding("stamps", shim, "does not read the home pointer"))
    want = "%s/bin/python3" % os.path.join(f.home, VENV)
    for name in BIN_WRAPPERS:
        path = os.path.join(f.bin_dir, name)
        text = read_text(path)
        if text is not None and want not in text:
            out.append(Finding("stamps", path, "does not exec %s" % want))
    text = read_text(f.plist)
    want = os.path.join(f.home, HELPER)
    if text is not None and want not in text:
        out.append(Finding("plist", f.plist, "does not run %s" % want))
    view = os.path.join(f.home, VIEW)
    for path in f.skills_files:
        named = skills_view_of(path)
        if named is not None and named != view:
            out.append(Finding("stamps", path, "names %s, not %s" % (named, view)))
    return out


def _inspect_state(f: Facts) -> List[Finding]:
    out = []
    venv = os.path.join(f.home, VENV)
    wrappers = any(os.path.exists(os.path.join(f.bin_dir, n)) for n in BIN_WRAPPERS)
    if (os.path.exists(venv) or wrappers) and not venv_ready(f.home):
        out.append(Finding("venv", venv, "fails the interpreter probe (a python3 and PyYAML)"))
    helper = os.path.join(f.home, HELPER)
    if os.path.exists(f.plist) and not os.path.isfile(helper):
        out.append(Finding("helper", helper, "missing, and the plist runs it"))
    view = os.path.join(f.home, VIEW)
    if os.path.islink(view) or not os.path.isdir(view):
        out.append(Finding("view", view, "missing"))
    if os.path.lexists(f.agents_mount):
        if os.path.islink(f.agents_mount):
            if os.readlink(f.agents_mount) != view:
                out.append(Finding("mount", f.agents_mount, "points at %s, not %s"
                                   % (os.readlink(f.agents_mount), view)))
        elif os.path.isdir(f.agents_mount):
            for entry in sorted(os.listdir(f.agents_mount)):
                path = os.path.join(f.agents_mount, entry)
                if os.path.islink(path) and os.readlink(path).endswith("/%s/%s" % (VIEW, entry)) \
                        and os.readlink(path) != os.path.join(view, entry):
                    out.append(Finding("mount", path, "points at %s" % os.readlink(path)))
    else:
        out.append(Finding("mount", f.agents_mount, "absent"))
    for rel in (VENV, VIEW, HELPER):
        path = os.path.join(f.default, rel)
        if os.path.lexists(path):
            out.append(Finding("retire", path, "remains at the old path"))
    for name, target in mount_targets(f.repo_root):
        for base in (f.home, f.default):
            link = os.path.join(base, name)
            if base == f.home and not os.path.islink(link):
                out.append(Finding("mounts", link, "missing"))
            elif os.path.realpath(link) != os.path.realpath(target):
                step = "mounts" if base == f.home else "claude-mounts"
                out.append(Finding(step, link, "does not resolve to %s" % target))
    return out


def inspect(f: Facts, env_home: Optional[str] = None) -> List[Finding]:
    """Every way the machine differs from a healthy migrated layout at ``f.home``."""
    out = []
    pointed = raw_pointer()
    pointer = adlc_home.pointer_path()
    if not os.path.lexists(pointer):
        out.append(Finding("pointer", pointer, "missing: the machine has lost its pointer"))
    elif pointed is None or os.path.islink(pointer) or not os.path.isfile(pointer):
        out.append(Finding("pointer", pointer, "not a regular file naming a home"))
    elif pointed != f.home:
        out.append(Finding("pointer", pointer, "names %s, not %s" % (pointed, f.home)))
    if not os.path.isdir(f.home):
        out.append(Finding("home", f.home, "does not exist"))
    text = read_text(f.rc_file)
    named = rc_home_line(text) if text is not None else None
    if named != f.home:
        out.append(Finding("rc", f.rc_file, 'carries no export ADLC_HOME="%s" in the REQ-519 '
                                            "block" % f.home))
    if env_home is not None and (env_home.rstrip("/") or "/") != f.home:
        out.append(Finding("env", "ADLC_HOME", "is %s in this environment, and the machine's "
                                               "home is %s" % (env_home, f.home)))
    return (out + _inspect_moved(f) + _inspect_locks(f) + _inspect_stamps(f)
            + _inspect_state(f))
