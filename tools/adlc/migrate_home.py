#!/usr/bin/env python3
"""``install.sh --migrate-home``: move the toolkit's machine state, reversibly (REQ-663).

``install.sh`` resolves what only the shell knows and execs this. One run is one
transaction: preflight, stage, lock, flip, release, retire, verify.

* **Preflight** changes nothing, and every refusal prints its evidence and a fix.
* **Stage** builds everything under ``<dir>`` first. Nothing reads ``<dir>`` until the
  pointer is written, so a staged copy is harmless and a failure just removes it.
* **Flip** runs inside the allocation locks of both homes. Each step registers its undo
  before it acts, and any exception, a signal included, unwinds them (ADR-4).
* **Retire** deletes the old venv, view and helper after the locks are released. It is
  irreversible, so nothing that can fail runs after it.

``--back`` is the mirror, and a repair is the forward path over a machine that is
already there: every step checks before it acts, so a run with nothing to do is zero
actions and a re-run after a crash converges. What the machine should look like is
``home_layout.py``'s to say, in one place, for this and for doctor.

Why a symlink at a counter and a tombstone at a lock (ADR-3): a counter is data, so one
file can have two names; a ``mkdir`` lock is an operation on a path, so two names are
two locks.

Pure standard library, Python 3.9: this runs on the machine's own ``python3``, before
and after the venv it rebuilds. Children never inherit ``ADLC_HOME``, because during a
migration the variable and the pointer can legitimately disagree. The default home
comes from ``adlc_home.default_home``, the one place it is spelled.

``ADLC_MIGRATE_TEST_HOOK``, when set, names a program called with a point name
(``staged``, ``flip:<step>``). A non-zero exit fails the step. It has no default, and
it runs nothing a process that can set the variable could not run itself (ADR-8).
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adlc_home  # noqa: E402
import checks  # noqa: E402
import doctor  # noqa: E402
import home_layout as hl  # noqa: E402
from home_layout import (COUNTERS, CONFIG, HELPER, LEDGER, MOVED_FILES, PROBE_DIR,  # noqa: E402
                         VENV, VIEW)

#: id-alloc's budget: 50 tries at 0.1 s (BR-3, BR-4).
LOCK_TRIES = 50
LOCK_SLEEP = 0.1

#: Characters that cannot stand unescaped where ``<dir>`` is stamped: the double-quoted
#: rc line, the ``sh`` wrappers, ``sed``'s ``|`` delimiter and the plist XML (BR-2).
UNSAFE_CHARS = "\"'`$\\&<>|\n\r\t"

BACK_PREFIX = ".adlc-home-back-"
REPAIR_PREFIX = ".adlc-home-repair-"
TOMBSTONE_TEXT = ("# %s (REQ-663 BR-6)\n"
                  "# This path is un-lockable on purpose: the toolkit's machine state moved to\n"
                  "# %s\n"
                  "# An allocator that reaches this file is a stale copy of id-alloc.sh. Re-sync\n"
                  "# it with /template-drift. Do not remove this file.\n")


class Refused(Exception):
    """A preflight refusal or a lock that could not be taken. Nothing is left changed."""


class StepFailed(Exception):
    """A step failed. ``step`` names it."""

    def __init__(self, step: str, why: str):
        super().__init__("%s: %s" % (step, why))
        self.step = step


class Verdict(NamedTuple):
    name: str
    ok: bool
    evidence: str
    fix: str = ""


Snapshot = Tuple  # ("absent",) | ("link", target) | ("file", saved_path, mode) | ...


# --- small, boring file operations -------------------------------------------

def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: str, data: bytes, mode: int = 0o644) -> None:
    """Temp file, then rename, in the target's directory (REQ-519 BR-2)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".adlc-tmp-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def copy_verified(src: str, dst: str) -> None:
    """Copy ``src`` over ``dst`` by rename, keep its mode, and prove the bytes arrived."""
    with open(src, "rb") as fh:
        data = fh.read()
    atomic_write(dst, data, os.stat(src).st_mode & 0o7777)
    if hashlib.sha256(data).hexdigest() != sha256(dst):
        raise StepFailed("copy", "%s did not verify after the copy" % dst)


def replace_with_symlink(path: str, target: str) -> None:
    """One rename: there is no moment with no file at ``path`` (BR-4)."""
    tmp = "%s.adlc-tmp-%d" % (path, os.getpid())
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, path)


def is_regular(path: str) -> bool:
    return os.path.isfile(path) and not os.path.islink(path)


def unlink_quiet(path: str) -> None:
    if os.path.lexists(path):
        os.unlink(path)


def inside(child: str, parent: str) -> bool:
    child, parent = os.path.realpath(child), os.path.realpath(parent)
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def utc_stamp() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _child_env() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != adlc_home.ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _tail(text: str, lines: int = 6) -> str:
    return " | ".join(text.strip().splitlines()[-lines:])


class Run:
    """One invocation's state. Passed around instead of a module of globals."""

    def __init__(self, args: argparse.Namespace):
        self.repo_root = os.path.abspath(args.repo_root)
        self.installer = args.installer
        self.delegate_installer = args.delegate_installer
        # Through a dotfile manager's link: the file that changes, and the one saved.
        self.rc_file = (os.path.realpath(args.rc_file) if os.path.islink(args.rc_file)
                        else args.rc_file)
        self.dry = args.dry_run
        self.prune = args.prune_backup
        self.default = adlc_home.default_home()
        self.current, self.how = hl.persisted_home()
        self.target = ""
        self.repair = False
        self.home_is_live = False       # the home is the truth, not the old paths (ADR-5)
        self.actions = 0
        self.undo: List[Tuple[str, Callable[[], None]]] = []
        self.created: List[str] = []    # staged paths this run made, for cleanup
        self.held: List[str] = []       # lock dirs held right now
        self.work_dir = ""              # the backup, or a working copy
        self.keep_work_dir = False      # on success
        self.undo_incomplete = False
        self.snapshots: Dict[str, Snapshot] = {}
        self.rendered: Dict[str, bytes] = {}
        self.mount_snap: Snapshot = ("absent",)

    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def did(self, text: str) -> None:
        self.actions += 1
        self.say("  done: %s" % text)

    def on_undo(self, what: str, fn: Callable[[], None]) -> None:
        self.undo.append((what, fn))

    def hook(self, point: str) -> None:
        program = os.environ.get("ADLC_MIGRATE_TEST_HOOK")
        if not program:
            return
        code = subprocess.run([program, point], env=_child_env()).returncode
        if code != 0:
            raise StepFailed(point, "the test hook exited %d" % code)

    def facts(self, home: str) -> hl.Facts:
        return hl.machine_facts(home, self.repo_root, self.rc_file)

    def backups(self) -> List[str]:
        return sorted(glob.glob(os.path.join(glob.escape(self.default),
                                             hl.BACKUP_PREFIX + "*")))

    def fix(self, *args: str) -> str:
        """A command line an operator can paste: every path quoted (LESSON-572)."""
        return " ".join(shlex.quote(a) for a in (self.installer,) + args)

    def internal(self, step: str, arg: str) -> None:
        """One step of a plain install, against the home it names."""
        out = subprocess.run(["bash", self.installer, "--migrate-internal", step, arg],
                             env=_child_env(), capture_output=True, text=True)
        if out.returncode != 0:
            raise StepFailed(step, "install.sh exited %d: %s"
                             % (out.returncode, _tail(out.stdout + out.stderr)))

    def delegate(self, *args: str) -> None:
        out = subprocess.run(["sh", self.delegate_installer] + list(args),
                             env=_child_env(), capture_output=True, text=True)
        if out.returncode != 0:
            raise StepFailed(args[0].lstrip("-"), "tools/delegate/install.sh exited %d: %s"
                             % (out.returncode, _tail(out.stdout + out.stderr)))


# --- preflight ---------------------------------------------------------------

def check_dir(run: Run, raw: str) -> Verdict:
    """BR-2. Refusals name the flag, as REQ-654 BR-2 names the variable."""
    if raw == "":
        return Verdict("dir", False, "--migrate-home was given an empty <dir>")
    if not raw.startswith("/"):
        return Verdict("dir", False, "--migrate-home needs an absolute <dir>, got %r" % raw)
    bad = sorted(set(raw) & set(UNSAFE_CHARS))
    if bad:
        return Verdict("dir", False,
                       "--migrate-home <dir> holds %r, which cannot stand unescaped in the rc "
                       "line, the wrappers or the plist" % "".join(bad))
    target = os.path.normpath(raw)
    target = target[1:] if target.startswith("//") else target
    if inside(target, run.default):
        return Verdict("dir", False,
                       "--migrate-home <dir> is %s, which is or sits inside the default home"
                       % target)
    if inside(target, run.repo_root):
        return Verdict("dir", False, "--migrate-home <dir> is %s, inside the clone" % target)
    if os.path.lexists(target) and not os.path.isdir(target):
        return Verdict("dir", False, "--migrate-home <dir> %s is not a directory" % target)
    foreign = foreign_entries(target, run.repo_root) if os.path.isdir(target) else []
    if foreign:
        return Verdict("dir", False,
                       "--migrate-home <dir> %s holds %s, which is not part of a toolkit home; "
                       "nothing is merged" % (target, ", ".join(foreign)),
                       "pick an empty directory, or move those aside")
    run.target = target
    state = "absent" if not os.path.exists(target) else "empty or a toolkit home"
    return Verdict("dir", True, "%s (%s)" % (target, state))


def foreign_entries(path: str, repo_root: str) -> List[str]:
    foreign = []
    for entry in sorted(os.listdir(path)):
        full = os.path.join(path, entry)
        if entry not in hl.HOME_ENTRIES:
            foreign.append(entry)
        elif entry == "adlc" and os.path.isdir(full):
            foreign += [os.path.join("adlc", e) for e in sorted(os.listdir(full))
                        if e not in hl.HOME_ADLC_ENTRIES]
        elif entry in hl.MOUNT_NAMES and not os.path.islink(full):
            foreign.append(entry)
    return foreign


def check_env(run: Run, allowed: List[str]) -> Verdict:
    """BR-3 b. The persisted home, not the resolver's, or this could never fire."""
    raw = os.environ.get(adlc_home.ENV)
    if raw is None:
        return Verdict("env", True, "ADLC_HOME is unset")
    value = raw.rstrip("/") or "/"
    if value in allowed:
        return Verdict("env", True, "ADLC_HOME names %s" % value)
    return Verdict("env", False,
                   "ADLC_HOME is %r, which is neither of %s" % (raw, ", ".join(allowed)),
                   "unset ADLC_HOME   # then re-run")


def check_pointer(run: Run) -> Verdict:
    """BR-3 c."""
    if run.how == "default":
        return Verdict("pointer", True, "no pointer: this machine has not migrated")
    if run.current == run.target:
        run.repair = True
        return Verdict("pointer", True, "already migrated to %s: this is a repair" % run.target)
    return Verdict("pointer", False,
                   "this machine is already migrated to %s (%s)" % (run.current, run.how),
                   run.fix("--migrate-home", "--back") + "   # then migrate to the new home")


def check_backup(run: Run) -> Verdict:
    """BR-3 e. A repair of the current home never trips this."""
    found = run.backups()
    if not found or run.target == run.current or run.prune:
        return Verdict("backup", True, "no backup in the way")
    return Verdict("backup", False, "a previous migration's backup exists: %s"
                   % ", ".join(found),
                   run.fix("--migrate-home", run.target, "--prune-backup"))


def check_mounts(run: Run) -> Verdict:
    """BR-3 i. BR-1 promises these still resolve afterwards, and nothing here makes them."""
    bad = []
    for name, want in hl.mount_targets(run.repo_root):
        link = os.path.join(run.default, name)
        if os.path.realpath(link) != os.path.realpath(want):
            bad.append(link)
    if bad:
        return Verdict("mounts", False, "%s does not resolve into the clone" % ", ".join(bad),
                       run.fix() + "   # installs Claude Code's mounts")
    return Verdict("mounts", True, "Claude Code's skills and agents mounts resolve into the clone")


def check_markers(run: Run, home: str) -> Verdict:
    """BR-3 h. A marker names the home it was written under, so it never moves."""
    pattern = os.path.join(glob.escape(home), PROBE_DIR, "*.marker.json")
    found = sorted(glob.glob(pattern))
    if not found:
        return Verdict("probe-markers", True, "no harness-probe recovery marker")
    names = [os.path.basename(p)[:-len(".marker.json")] for p in found]
    return Verdict("probe-markers", False,
                   "a crashed harness probe left a recovery marker: %s" % ", ".join(found),
                   "\n".join("adlc harness probe %s --recover" % n for n in names))


def check_moved_kinds(run: Run) -> Verdict:
    """A file the machine keeps elsewhere is not one this can move.

    A dotfile manager's symlink at the config would otherwise be left behind, and every
    reader would then find no config at the new home: delegation would change without
    anyone asking, which is BUG-205's shape.
    """
    bad = []
    for rel in MOVED_FILES:
        old = os.path.join(run.default, rel)
        if not os.path.lexists(old) or is_regular(old):
            continue
        if os.path.islink(old) and os.readlink(old) == os.path.join(run.current, rel):
            continue
        bad.append(old)
    if bad:
        return Verdict("moved-files", False,
                       "%s is not a regular file, so it cannot be moved" % ", ".join(bad),
                       "replace it with a regular file, then re-run")
    return Verdict("moved-files", True, "every file to move is a regular file, or already moved")


def check_consumers(run: Run) -> Verdict:
    """BR-3 a, over a report rather than a verdict (ADR-6).

    From the clone, so the repos root does not depend on where the operator ran this.
    """
    os.chdir(run.repo_root)
    profile = doctor.build_profile()
    report = checks.consumer_sync_report(profile)
    if report.root is None:
        return Verdict("consumer-sync", False, "no repos root to walk (%s)" % report.how,
                       "export ADLC_REPOS_ROOT=<the directory holding your repos>")
    if not report.consumers:
        return Verdict("consumer-sync", True,
                       "no consumer under %s (%s)" % (report.root, report.how))
    if report.base.unverified:
        return Verdict("consumer-sync", False,
                       "unverified-baseline: %s. Baseline %s; currency cannot be proven"
                       % (report.base.unverified, report.base.label),
                       "git -C %s fetch origin" % shlex.quote(run.repo_root))
    partials = [(c, files, note) for c, files, _layer, note in report.stale if files]
    if partials:
        return Verdict("consumer-sync", False,
                       "; ".join("%s is stale (%s)%s" % (c, ", ".join(files), note)
                                 for c, files, note in partials),
                       "\n".join(checks.consumer_sync_fix(profile, c) for c, _f, _n in partials))
    notes = ["%s: project layer only, no allocator there" % c
             for c, files, _layer, _note in report.stale if not files] + report.skipped
    notes += ["project layer not compared: %s" % u for u in report.unverified]
    tail = "; ".join(notes)
    return Verdict("consumer-sync", True,
                   "%d consumer(s) under %s have current partials%s"
                   % (len(report.consumers), report.root, ". " + tail if tail else ""))


def venv_wanted(run: Run, home: str) -> bool:
    """A machine that has the delegation install keeps it."""
    bin_dir = os.path.join(hl.user_home(), "bin")
    return (any(os.path.exists(os.path.join(h, VENV)) for h in (home, run.default, run.current))
            or any(os.path.exists(os.path.join(bin_dir, n)) for n in hl.BIN_WRAPPERS))


def check_venv(run: Run, home: str) -> Verdict:
    """BR-3 f, the half that can be asked before staging; pip answers the rest."""
    if not venv_wanted(run, home):
        return Verdict("venv", True, "no delegation venv to rebuild")
    py = shutil.which("python3")
    if not py:
        return Verdict("venv", False, "the delegation venv needs python3 to rebuild, and there "
                                      "is none on PATH", "install python3, then re-run")
    probe = subprocess.run([py, "-c", "import venv, ensurepip"], capture_output=True, text=True,
                           env=_child_env())
    if probe.returncode != 0:
        return Verdict("venv", False, "%s cannot build a venv: %s" % (py, _tail(probe.stderr, 2)),
                       "install the venv module for python3, then re-run")
    return Verdict("venv", True, "%s can rebuild the delegation venv; pip runs at staging" % py)


def old_locks(run: Run) -> List[str]:
    return [hl.lock_path(run.default, c) for c in COUNTERS]


def new_locks(run: Run, home: str) -> List[str]:
    return [hl.lock_path(home, c) for c in COUNTERS]


def check_locks(run: Run, locks: List[str]) -> Verdict:
    """BR-3 d. A dry run only looks: taking a lock is a change."""
    for lock in locks:
        if os.path.islink(lock):
            return Verdict("locks", False, "%s is a symlink: refusing (TOCTOU risk, LESSON-014)"
                           % lock, "rm %s   # after inspecting it" % shlex.quote(lock))
        if run.repair and inside(lock, run.default):
            continue    # a tombstone, or what a repair is here to replace
        if run.dry:
            if os.path.isdir(lock):
                return Verdict("locks", False, "%s is held" % lock,
                               "wait for the allocator, or rmdir %s if it crashed"
                               % shlex.quote(lock))
            continue
        if is_regular(lock) or not os.path.isdir(os.path.dirname(lock)):
            continue
        if not take_lock(lock):
            return Verdict("locks", False, "%s is held and could not be taken within the "
                                           "id-alloc budget" % lock,
                           "wait for the allocator, or rmdir %s if it crashed" % shlex.quote(lock))
        os.rmdir(lock)
    return Verdict("locks", True, "the allocation locks are free")


def take_lock(lock: str) -> bool:
    """The ``mkdir`` protocol ``id-alloc.sh`` uses: same path, same budget."""
    for attempt in range(LOCK_TRIES):
        try:
            os.mkdir(lock)
            return True
        except FileExistsError:
            if attempt + 1 < LOCK_TRIES:
                time.sleep(LOCK_SLEEP)
    return False


def report_preflight(run: Run, verdicts: List[Verdict]) -> None:
    run.say("preflight:")
    for v in verdicts:
        run.say("  [%s] %s — %s" % ("ok" if v.ok else "REFUSE", v.name, v.evidence))
        for line in v.fix.splitlines():
            run.say("    -> fix: %s" % line)


def refused(verdicts: List[Verdict]) -> bool:
    return any(not v.ok for v in verdicts)


# --- rendering and snapshots -------------------------------------------------

def render_stamps(run: Run, home: str) -> None:
    """Every stamped file's wanted bytes, from the shell that owns each text (ADR-7).

    Rendered into a temp directory, so this is safe in a dry run. Only files that exist
    are stamped, except the shim, which a healthy machine always has.
    """
    facts = run.facts(home)
    run.rendered = {}
    with tempfile.TemporaryDirectory(prefix="adlc-migrate-") as tmp:
        shim = os.path.join(tmp, "shim")
        run.internal("shim", shim)
        with open(shim, "rb") as fh:
            run.rendered[os.path.join(facts.bin_dir, "adlc")] = fh.read()
        run.delegate("--render", home, tmp)
        for name in hl.BIN_WRAPPERS:
            path = os.path.join(facts.bin_dir, name)
            if os.path.exists(path):
                with open(os.path.join(tmp, name), "rb") as fh:
                    run.rendered[path] = fh.read()
        if os.path.exists(facts.plist):
            with open(os.path.join(tmp, os.path.basename(facts.plist)), "rb") as fh:
                run.rendered[facts.plist] = fh.read()
    import harness_render
    view = os.path.join(home, VIEW)
    for path in facts.skills_files:
        if hl.skills_view_of(path) is not None:
            text = harness_render.format_skills_entries([], {"skills_root": view}, None)
            run.rendered[path] = text.encode("utf-8")


def stamp_drift(run: Run) -> List[str]:
    """The stamped files whose bytes differ from what would be written."""
    drift = []
    for path, want in sorted(run.rendered.items()):
        try:
            with open(path, "rb") as fh:
                if fh.read() == want:
                    continue
        except OSError:
            pass
        drift.append(path)
    return drift


def snapshot(run: Run, path: str, name: str) -> Snapshot:
    """What is at ``path`` now, saved under the working directory when it is a file."""
    if os.path.islink(path):
        return ("link", os.readlink(path))
    if not os.path.lexists(path):
        return ("absent",)
    if os.path.isdir(path):
        return ("dir",)
    saved = os.path.join(run.work_dir, "stamped" if name.startswith("stamp-") else "move", name)
    os.makedirs(os.path.dirname(saved), exist_ok=True)
    copy_verified(path, saved)
    return ("file", saved, os.stat(path).st_mode & 0o7777)


def restore(path: str, snap: Snapshot) -> None:
    kind = snap[0]
    if kind == "absent":
        unlink_quiet(path)
    elif kind == "link":
        replace_with_symlink(path, snap[1])
    elif kind == "file":
        with open(snap[1], "rb") as fh:
            atomic_write(path, fh.read(), snap[2])


def mount_snapshot(mount: str) -> Snapshot:
    if os.path.islink(mount):
        return ("link", os.readlink(mount))
    if os.path.isdir(mount):
        links = {}
        for entry in os.listdir(mount):
            path = os.path.join(mount, entry)
            if os.path.islink(path):
                links[entry] = os.readlink(path)
        return ("links", links)
    return ("absent",) if not os.path.lexists(mount) else ("other",)


def mount_restore(mount: str, snap: Snapshot) -> None:
    if snap[0] == "link":
        replace_with_symlink(mount, snap[1])
    elif snap[0] == "absent":
        unlink_quiet(mount)
    elif snap[0] == "links":
        for entry, target in snap[1].items():
            replace_with_symlink(os.path.join(mount, entry), target)


def write_manifest(run: Run) -> None:
    moved = {name: list(snap) for name, snap in run.snapshots.items()}
    data = json.dumps({"schema": 1, "target": run.target, "created": utc_stamp(),
                       "snapshots": moved}, indent=2).encode("utf-8")
    atomic_write(os.path.join(run.work_dir, "manifest.json"), data)


def snapshot_stamped(run: Run) -> None:
    """BR-10: stamped files are copied before the locks are taken."""
    # Private: it holds the rc file, and an rc file is where API keys live.
    os.makedirs(run.work_dir, mode=0o700, exist_ok=True)
    os.chmod(run.work_dir, 0o700)
    facts = run.facts(run.target or run.current)
    paths = sorted(set(run.rendered) | {run.rc_file, adlc_home.pointer_path()})
    for index, path in enumerate(paths):
        run.snapshots[path] = snapshot(run, path, "stamp-%02d-%s" % (index, os.path.basename(path)))
    run.mount_snap = mount_snapshot(facts.agents_mount)
    write_manifest(run)


# --- staging -----------------------------------------------------------------

def merge_lines(keep: str, extra: str) -> bytes:
    """``keep``'s lines, then any of ``extra``'s it lacks. The ledger is append-only."""
    with open(keep, "rb") as fh:
        lines = fh.read().splitlines()
    seen = set(lines)
    with open(extra, "rb") as fh:
        lines += [line for line in fh.read().splitlines() if line not in seen]
    return b"\n".join(lines) + b"\n"


def decimal(path: str) -> int:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read().strip()
    return int(raw) if raw.isdigit() else 0


def sync_moved(run: Run) -> None:
    """Make every ``move`` item under the target right. Run twice: staging and under locks.

    Plain forward, the old path is live, and a copy is refreshed. When the home is live
    (a repair, or a home ``ADLC_HOME`` already names, ADR-5), a regular file at an old
    path is folded in: the higher value for a counter, the union for the ledger, and a
    config that disagrees is set aside and named. A file only the target holds is kept
    either way, never deleted. A repair with the home gone restores from the backup.
    """
    for rel in MOVED_FILES:
        old, new = os.path.join(run.default, rel), os.path.join(run.target, rel)
        if not os.path.lexists(new):
            run.created.append(new)
        if not run.home_is_live:
            if is_regular(old) and (not os.path.exists(new) or sha256(old) != sha256(new)):
                copy_verified(old, new)
            elif not os.path.lexists(old) and os.path.exists(new):
                run.say("  note: keeping %s, which only the new home holds" % new)
            continue
        if not is_regular(old):
            if not os.path.exists(new):
                restore_from_backup(run, rel, new)
            continue
        if not os.path.exists(new):
            copy_verified(old, new)
        elif sha256(old) == sha256(new):
            pass
        elif rel in COUNTERS:
            if decimal(old) > decimal(new):
                copy_verified(old, new)
        elif rel == LEDGER:
            atomic_write(new, merge_lines(new, old))
        else:
            run.keep_work_dir = True
            run.say("  note: %s differs from %s; the home's copy is kept, and the other is "
                    "saved under %s" % (old, new, run.work_dir))


def restore_from_backup(run: Run, rel: str, new: str) -> None:
    saved = backup_copy(run, rel)
    if saved:
        copy_verified(saved, new)
        run.say("  restored %s from %s" % (new, saved))
    elif rel == CONFIG and run.repair and os.path.islink(os.path.join(run.default, CONFIG)):
        run.say("  WARN: %s is gone and no backup holds a copy; delegation now reads as "
                "unconfigured until you write one" % new)


def backup_copy(run: Run, rel: str) -> Optional[str]:
    """The newest copy of ``rel`` in a forward backup."""
    for backup in reversed(run.backups()):
        candidate = os.path.join(backup, "move", rel.replace(os.sep, "__"))
        if os.path.isfile(candidate):
            return candidate
    return None


def stage_tree(run: Run, home: str) -> None:
    """What is rebuilt or regenerated rather than moved (BR-4)."""
    view = os.path.join(home, VIEW)
    if not os.path.isdir(view):
        run.created.append(view)
    run.internal("view", home)
    venv = os.path.join(home, VENV)
    if venv_wanted(run, home) and not hl.venv_ready(home):
        if not os.path.exists(venv):
            run.created.append(venv)
        run.say("  rebuilding the delegation venv at %s" % venv)
        try:
            run.delegate("--venv-only", home)
        except StepFailed as exc:
            raise Refused("venv: could not rebuild %s (%s)" % (venv, exc))
        if not hl.venv_ready(home):
            raise Refused("venv: %s fails the interpreter probe after the rebuild" % venv)
    helper = os.path.join(home, HELPER)
    wanted = (os.path.exists(run.facts(home).plist)
              or any(os.path.exists(os.path.join(h, HELPER)) for h in (run.default, run.current)))
    if wanted and not os.path.isfile(helper):
        run.created.append(helper)
        src = os.path.join(run.repo_root, "tools", "delegate", HELPER + ".in")
        with open(src, "rb") as fh:
            atomic_write(helper, fh.read(), 0o755)


def stage_forward(run: Run) -> None:
    if not os.path.isdir(run.target):
        run.created.append(run.target)
        os.makedirs(run.target)
    adlc_dir = os.path.join(run.target, "adlc")
    if not os.path.isdir(adlc_dir):
        run.created.append(adlc_dir)
        os.makedirs(adlc_dir)
    sync_moved(run)
    stage_tree(run, run.target)
    for name, want in hl.mount_targets(run.repo_root):
        link = os.path.join(run.target, name)
        if os.path.lexists(link) and not os.path.islink(link):
            raise Refused("mounts: %s is not a symlink" % link)
        if not (os.path.islink(link) and os.readlink(link) == want):
            if not os.path.lexists(link):
                run.created.append(link)
            replace_with_symlink(link, want)


#: Every name this tool ever deletes. A path that ends in anything else is refused, so a
#: bad variable cannot reach a tree nobody meant (conventions.md "Bash in skills").
OWNED_NAMES = frozenset(tuple(os.path.basename(rel) for rel in MOVED_FILES)
                        + (os.path.basename(VIEW), VENV, HELPER, "adlc", adlc_home.POINTER_NAME)
                        + hl.MOUNT_NAMES)
OWNED_PREFIXES = (hl.BACKUP_PREFIX, BACK_PREFIX, REPAIR_PREFIX)


def remove_path(path: str) -> None:
    """Remove something this tool owns, by a name it owns, and never a tree through a link."""
    name = os.path.basename(path)
    if not os.path.isabs(path) or not (name in OWNED_NAMES or name.startswith(OWNED_PREFIXES)):
        raise ValueError("refusing to remove %r: not a name this tool owns" % path)
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def clean_stage(run: Run) -> None:
    """Remove what this run staged, newest first, so a refusal leaves nothing."""
    for path in reversed(run.created):
        try:
            if os.path.isdir(path) and not os.path.islink(path) and path == run.target:
                remove_home_items(path)
                os.rmdir(path)
            else:
                remove_path(path)
        except OSError as exc:
            run.say("  WARN: could not remove staged %s (%s)" % (path, exc.strerror))
    run.created = []


def remove_home_items(home: str) -> None:
    """Every toolkit-owned entry under ``home``, by name, and nothing else.

    The mounts only as the links this tool makes: a directory of that name is somebody's.
    """
    for rel in MOVED_FILES + (VIEW, VENV, HELPER):
        remove_path(os.path.join(home, rel))
    for rel in hl.MOUNT_NAMES:
        if os.path.islink(os.path.join(home, rel)):
            os.unlink(os.path.join(home, rel))
    for rel in (PROBE_DIR, "adlc"):
        path = os.path.join(home, rel)
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)


# --- locks -------------------------------------------------------------------

def hold(run: Run, locks: List[str]) -> None:
    """Take ``locks``. A repair takes over a directory a crashed stale allocator left."""
    for lock in locks:
        if os.path.islink(lock):
            raise Refused("locks: %s is a symlink: refusing (TOCTOU risk, LESSON-014)" % lock)
        if is_regular(lock):
            continue
        if take_lock(lock):
            run.held.append(lock)
        elif run.repair and inside(lock, run.default):
            run.say("  note: taking over %s, left by a stale allocator" % lock)
            run.held.append(lock)
        else:
            raise Refused("locks: %s is held and could not be taken within the id-alloc "
                          "budget" % lock)


def release(run: Run) -> None:
    for lock in reversed(run.held):
        if os.path.isdir(lock) and not os.path.islink(lock):
            try:
                os.rmdir(lock)
            except OSError:
                pass
    run.held = []


# --- forward flip steps ------------------------------------------------------

def link_old_path(run: Run, rel: str) -> None:
    old, new = os.path.join(run.default, rel), os.path.join(run.target, rel)
    if os.path.islink(old) and os.readlink(old) == new:
        return
    snap = snapshot(run, old, rel.replace(os.sep, "__"))
    run.snapshots[rel] = snap
    run.on_undo("restore %s" % old, lambda: restore(old, snap))
    replace_with_symlink(old, new)
    run.did("linked %s -> %s" % (old, new))


def step_counters(run: Run) -> None:
    for name in COUNTERS:
        link_old_path(run, name)


def step_config(run: Run) -> None:
    """A machine with no config keeps none (BUG-205): nothing to link to.

    Nor a link to nothing: the loader refuses a dangling symlink, where it reads an
    absent file as unconfigured.
    """
    old = os.path.join(run.default, CONFIG)
    if os.path.exists(os.path.join(run.target, CONFIG)):
        link_old_path(run, CONFIG)
    elif os.path.islink(old):
        snap = snapshot(run, old, CONFIG.replace(os.sep, "__"))
        run.on_undo("restore %s" % old, lambda: restore(old, snap))
        os.unlink(old)
        run.did("removed the dangling link %s" % old)


def step_ledger(run: Run) -> None:
    """No link: every shipped reader and writer refuses a symlinked ledger (LESSON-014)."""
    old = os.path.join(run.default, LEDGER)
    if os.path.lexists(old):
        snap = snapshot(run, old, LEDGER)
        run.snapshots[LEDGER] = snap
        run.on_undo("restore %s" % old, lambda: restore(old, snap))
        os.unlink(old)
        run.did("moved %s -> %s" % (old, os.path.join(run.target, LEDGER)))


def step_pointer(run: Run) -> None:
    path = adlc_home.pointer_path()
    want = (run.target + "\n").encode("utf-8")
    if is_regular(path):
        with open(path, "rb") as fh:
            if fh.read() == want:
                return
    run.on_undo("restore the pointer", lambda: restore(path, run.snapshots[path]))
    if os.path.lexists(path) and not is_regular(path):
        remove_path(path)
    atomic_write(path, want)
    run.did("wrote the pointer %s" % path)


def write_rc(run: Run, new_text: str) -> None:
    """Through a symlink: an rc file kept by a dotfile manager stays a symlink."""
    path = os.path.realpath(run.rc_file) if os.path.islink(run.rc_file) else run.rc_file
    mode = os.stat(path).st_mode & 0o7777 if os.path.exists(path) else 0o644
    atomic_write(path, new_text.encode("utf-8"), mode)


def step_rc(run: Run) -> None:
    text = hl.read_text(run.rc_file) or ""
    line = 'export PATH="%s:$PATH"' % os.path.join(os.path.dirname(run.default), "bin")
    want = hl.rc_with_home(text, run.target, line)
    if want != text:
        path = run.rc_file
        run.on_undo("restore %s" % path, lambda: restore(path, run.snapshots[path]))
        write_rc(run, want)
        run.did("wrote the ADLC_HOME line in %s" % run.rc_file)


def step_stamps(run: Run) -> None:
    plist = run.facts(run.target or run.current).plist
    for path in stamp_drift(run):
        if path == plist:
            continue
        snap = run.snapshots.get(path, ("absent",))
        run.on_undo("restore %s" % path, lambda p=path, s=snap: restore(p, s))
        if os.path.exists(path):
            mode = os.stat(path).st_mode & 0o7777
        else:
            mode = 0o755 if os.path.dirname(path) == os.path.join(hl.user_home(), "bin") else 0o644
        atomic_write(path, run.rendered[path], mode)
        run.did("stamped %s" % path)


def launchctl_reload(plist: str, write: Callable[[], None]) -> None:
    """Bootout first, so no live agent is mid-run while its files change (REQ-522 BR-8)."""
    tool = shutil.which("launchctl")
    domain = "gui/%d" % os.getuid()
    if tool:
        subprocess.run([tool, "bootout", domain, plist], capture_output=True)
    write()
    lint = shutil.which("plutil")
    if lint and subprocess.run([lint, "-lint", plist], capture_output=True).returncode != 0:
        raise StepFailed("plist", "%s fails plutil -lint" % plist)
    if tool and subprocess.run([tool, "bootstrap", domain, plist],
                               capture_output=True).returncode != 0:
        if subprocess.run([tool, "load", plist], capture_output=True).returncode != 0:
            print("  WARN: could not load %s; the delegate env will not persist across "
                  "reboots until it is" % plist, flush=True)


def step_plist(run: Run) -> None:
    plist = run.facts(run.target or run.current).plist
    if plist not in stamp_drift(run):
        return

    def undo() -> None:
        launchctl_reload(plist, lambda: restore(plist, run.snapshots[plist]))

    run.on_undo("restore %s" % plist, undo)
    launchctl_reload(plist, lambda: atomic_write(plist, run.rendered[plist], 0o644))
    run.did("stamped and reloaded %s" % plist)
    if not shutil.which("launchctl"):
        run.say("  note: launchctl is not on PATH, so the agent was not reloaded")


def step_mount(run: Run, home: str) -> None:
    mount = run.facts(home).agents_mount
    before = mount_snapshot(mount)
    run.on_undo("restore %s" % mount, lambda: mount_restore(mount, run.mount_snap))
    run.internal("mount", home)
    if mount_snapshot(mount) != before:
        run.did("re-pointed %s at %s" % (mount, os.path.join(home, VIEW)))


def step_tombstones(run: Run) -> None:
    """The lock paths become un-lockable (BR-6, ADR-3).

    An allocator can win the moment between the ``rmdir`` and the exclusive create only
    if it is using the old path, and it writes through the symlink while this run holds
    the ``<dir>`` locks, so nobody races it. The create waits for it, within budget.
    """
    for name in COUNTERS:
        lock = hl.lock_path(run.default, name)
        if is_regular(lock):
            continue
        run.on_undo("remove the tombstone at %s" % lock, lambda p=lock: unlink_quiet(p))
        if os.path.islink(lock):
            os.unlink(lock)
        elif os.path.isdir(lock):
            os.rmdir(lock)
        run.held = [held for held in run.held if held != lock]
        text = (TOMBSTONE_TEXT % (hl.TOMBSTONE_MARK, run.target)).encode("utf-8")
        for attempt in range(LOCK_TRIES):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if attempt + 1 == LOCK_TRIES:
                    raise StepFailed("tombstones", "%s stayed locked" % lock)
                time.sleep(LOCK_SLEEP)
                continue
            with os.fdopen(fd, "wb") as fh:
                fh.write(text)
            break
    run.did("tombstoned the old lock paths under %s" % run.default)


def run_flip(run: Run, steps: List[Tuple[str, Callable[[Run], None]]]) -> None:
    current = "?"
    try:
        for current, fn in steps:
            fn(run)
            run.hook("flip:" + current)
    except BaseException as exc:
        run.say("  flip failed at step '%s': %s" % (current, exc))
        unwind(run)
        raise StepFailed(current, str(exc))


def unwind(run: Run) -> None:
    """Every undo, newest first. One that fails does not stop the others."""
    failed = []
    for what, fn in reversed(run.undo):
        try:
            fn()
            run.say("  undone: %s" % what)
        except Exception as exc:  # the rest of the list still has to run
            failed.append("%s (%s)" % (what, exc))
    run.undo = []
    if failed:
        run.undo_incomplete = True
        run.say("  UNDO INCOMPLETE. By hand, from %s: %s" % (run.work_dir, "; ".join(failed)))


def on_signal(signum: int, _frame: object) -> None:
    raise KeyboardInterrupt("signal %d" % signum)


# --- forward -----------------------------------------------------------------

def plan_forward(run: Run) -> List[str]:
    """One line per item, compat entry, stamped file, and write (BR-10, AC-6)."""
    t, d = run.target, run.default
    lines = []
    for rel in MOVED_FILES:
        old = os.path.join(d, rel)
        if is_regular(old):
            lines.append("move %s -> %s (checksum verified)" % (old, os.path.join(t, rel)))
    if os.path.exists(os.path.join(d, VENV)) or venv_wanted(run, t):
        lines.append("rebuild %s from tools/delegate/requirements.txt, retire %s"
                     % (os.path.join(t, VENV), os.path.join(d, VENV)))
    lines.append("regenerate the view %s, retire %s" % (os.path.join(t, VIEW), os.path.join(d, VIEW)))
    if os.path.exists(os.path.join(d, HELPER)):
        lines.append("regenerate the launchd helper %s, retire %s"
                     % (os.path.join(t, HELPER), os.path.join(d, HELPER)))
    lines.append("create %s" % " and ".join(os.path.join(t, n) for n in hl.MOUNT_NAMES))
    for name in COUNTERS:
        lines.append("compat symlink %s -> %s" % (os.path.join(d, name), os.path.join(t, name)))
    if is_regular(os.path.join(d, CONFIG)):
        lines.append("compat symlink %s -> %s" % (os.path.join(d, CONFIG), os.path.join(t, CONFIG)))
    for name in COUNTERS:
        lines.append("tombstone %s" % hl.lock_path(d, name))
    lines.append("pointer %s names %s" % (adlc_home.pointer_path(), t))
    lines.append('rc file %s gains export ADLC_HOME="%s"' % (run.rc_file, t))
    drift = stamp_drift(run)
    for path in sorted(run.rendered):
        lines.append("stamp %s%s" % (path, "" if path in drift else " (already current)"))
    lines.append("re-point %s at %s" % (run.facts(t).agents_mount, os.path.join(t, VIEW)))
    lines.append("backup under %s%s" % (os.path.join(d, hl.BACKUP_PREFIX), "<UTC time>"))
    return lines


def prune(run: Run) -> None:
    """The backup, and any working copy a killed run left beside it."""
    for prefix in (hl.BACKUP_PREFIX, BACK_PREFIX, REPAIR_PREFIX):
        for path in sorted(glob.glob(os.path.join(glob.escape(run.default), prefix + "*"))):
            remove_path(path)
            run.say("  pruned the backup %s" % path)


def do_forward(run: Run, raw_dir: str) -> int:
    verdicts = [check_dir(run, raw_dir)]
    if refused(verdicts):
        report_preflight(run, verdicts)
        return 1
    run.say("ADLC home migration  (%s)" % ("dry run" if run.dry else "live"))
    run.say("  current home: %s (%s)" % (run.current, run.how))
    run.say("  target home:  %s" % run.target)
    verdicts += [check_env(run, [run.current, run.target]), check_pointer(run),
                 check_backup(run), check_mounts(run), check_moved_kinds(run),
                 check_markers(run, run.current)]
    run.home_is_live = run.repair or (os.environ.get(adlc_home.ENV, "").rstrip("/") == run.target)
    gate = check_consumers(run)
    if run.repair and not gate.ok:
        gate = Verdict("consumer-sync", True, "note, not a refusal on a repair (the move already "
                                              "happened): " + gate.evidence)
    verdicts += [gate, check_venv(run, run.target)]
    if refused(verdicts):
        verdicts.append(Verdict("locks", True, "not attempted"))
        report_preflight(run, verdicts)
        return 1
    verdicts.append(check_locks(run, old_locks(run) + new_locks(run, run.target)))
    report_preflight(run, verdicts)
    if refused(verdicts):
        return 1

    render_stamps(run, run.target)
    facts = run.facts(run.target)
    findings = hl.inspect(facts) if run.repair else []
    drift = stamp_drift(run)
    work = not run.repair or bool(findings) or bool(drift)
    if run.dry:
        run.say("plan:")
        lines = (["repair %s: %s" % (f.item, f.detail) for f in findings]
                 + ["stamp %s" % p for p in drift]) if run.repair else plan_forward(run)
        for line in lines:
            run.say("  would: %s" % line)
        if run.prune:
            run.say("  would: prune %s" % (", ".join(run.backups()) or "(no backup)"))
        run.say("Dry run: no changes made. %d action(s) planned." % len(lines))
        return 0
    if run.prune:
        prune(run)
    if not work:
        run.say("Migration summary: 0 action(s); %s is already current." % run.target)
        return 0

    stamp = utc_stamp()
    run.work_dir = os.path.join(run.default, (REPAIR_PREFIX if run.repair else hl.BACKUP_PREFIX)
                                + stamp)
    run.keep_work_dir = not run.repair
    previous = {sig: signal.signal(sig, on_signal)
                for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        run.say("staging %s:" % run.target)
        stage_forward(run)
        run.hook("staged")
        snapshot_stamped(run)
        hold(run, old_locks(run) + new_locks(run, run.target))
        sync_moved(run)
        for rel in MOVED_FILES:
            old = os.path.join(run.default, rel)
            if is_regular(old):
                run.snapshots[rel] = snapshot(run, old, rel.replace(os.sep, "__"))
        write_manifest(run)
        run.say("flipping:")
        run_flip(run, [("counters", step_counters), ("config", step_config),
                       ("ledger", step_ledger), ("pointer", step_pointer), ("rc", step_rc),
                       ("stamps", step_stamps), ("plist", step_plist),
                       ("mount", lambda r: step_mount(r, r.target)),
                       ("tombstones", step_tombstones)])
    except (Refused, StepFailed, OSError, KeyboardInterrupt) as exc:
        return abandon(run, previous, exc, "migration",
                       "nothing was migrated; the machine is as it was")
    release(run)
    for sig, handler in previous.items():
        signal.signal(sig, handler)
    retire(run, run.default, (VENV, VIEW, HELPER))
    if run.repair and not run.keep_work_dir:
        remove_path(run.work_dir)
    return finish(run, run.facts(run.target))


def abandon(run: Run, previous: Dict, exc: BaseException, what: str, outcome: str) -> int:
    """After a failed stage or flip: leave nothing behind, unless an undo went wrong."""
    release(run)
    if run.undo_incomplete:
        run.say("%s failed and could not be fully undone; the copies are in %s"
                % (what, run.work_dir))
    else:
        clean_stage(run)
        if run.work_dir and os.path.isdir(run.work_dir):
            remove_path(run.work_dir)
    for sig, handler in previous.items():
        signal.signal(sig, handler)
    step = exc.step if isinstance(exc, StepFailed) else "stage"
    run.say("%s failed at step '%s': %s" % (what, step, exc))
    if not run.undo_incomplete:
        run.say("%s." % outcome)
    return 1


def retire(run: Run, base: str, rels: Tuple[str, ...]) -> None:
    """After the locks, because this cannot be undone (ADR-4). A failure is a warning."""
    for rel in rels:
        path = os.path.join(base, rel)
        if not os.path.lexists(path):
            continue
        try:
            remove_path(path)
            run.did("retired %s" % path)
        except OSError as exc:
            run.say("  WARN: could not remove %s (%s); a repair retires it"
                    % (path, exc.strerror))


def finish(run: Run, facts: hl.Facts) -> int:
    findings = hl.inspect(facts)
    for f in findings:
        run.say("  verify: %s: %s" % (f.item, f.detail))
    run.say("")
    run.say("Migration summary: %d action(s); the home is now %s." % (run.actions, facts.home))
    if not run.repair:
        run.say("  backup: %s (kept until --back or --prune-backup)" % run.work_dir)
    if findings:
        run.say("  verification failed: run %s to repair"
                % run.fix("--migrate-home", facts.home))
        return 1
    return 0


# --- back --------------------------------------------------------------------

def move_back(run: Run, rel: str) -> None:
    old, new = os.path.join(run.default, rel), os.path.join(run.current, rel)
    snap = run.snapshots.get("old:" + rel) or ("absent",)
    run.on_undo("restore %s" % old, lambda: restore(old, snap))
    if os.path.exists(new):
        copy_verified(new, old)
        run.did("moved %s -> %s" % (new, old))
    else:
        unlink_quiet(old)


def step_back_counters(run: Run) -> None:
    for name in COUNTERS:
        move_back(run, name)


def step_back_config(run: Run) -> None:
    move_back(run, CONFIG)


def step_back_ledger(run: Run) -> None:
    move_back(run, LEDGER)


def step_back_pointer(run: Run) -> None:
    path = adlc_home.pointer_path()
    run.on_undo("restore the pointer", lambda: restore(path, run.snapshots[path]))
    unlink_quiet(path)
    run.did("removed the pointer %s" % path)


def step_back_rc(run: Run) -> None:
    text = hl.read_text(run.rc_file) or ""
    want = hl.rc_without_home(text)
    if want != text:
        path = run.rc_file
        run.on_undo("restore %s" % path, lambda: restore(path, run.snapshots[path]))
        write_rc(run, want)
        run.did("removed the ADLC_HOME line from %s" % run.rc_file)


def step_back_tombstones(run: Run) -> None:
    """Last: until now they keep every allocator resolving the default out (ADR-4)."""
    for name in COUNTERS:
        lock = hl.lock_path(run.default, name)
        if is_regular(lock):
            text = (TOMBSTONE_TEXT % (hl.TOMBSTONE_MARK, run.current)).encode("utf-8")
            run.on_undo("restore the tombstone at %s" % lock,
                        lambda p=lock, b=text: atomic_write(p, b))
            os.unlink(lock)
    run.did("removed the tombstones under %s" % run.default)


def retire_home(run: Run, home: str) -> None:
    """``<dir>`` goes only when nothing but the migrated home remains in it (BR-9)."""
    try:
        remove_home_items(home)
    except OSError as exc:
        run.say("  WARN: could not clear %s (%s)" % (home, exc.strerror))
    left = sorted(os.listdir(home)) if os.path.isdir(home) else []
    if left:
        run.say("  note: %s stays: it holds %s, which the toolkit did not put there"
                % (home, ", ".join(left)))
    elif os.path.isdir(home):
        os.rmdir(home)
        run.did("removed %s" % home)


def do_back(run: Run) -> int:
    run.say("ADLC home migration, back  (%s)" % ("dry run" if run.dry else "live"))
    home = hl.raw_pointer()
    verdicts = []
    if not home:
        fix = ""
        if run.how == "traces":
            fix = run.fix("--migrate-home", run.current) + "   # restores the pointer"
        verdicts.append(Verdict("pointer", False, "no home pointer: nothing says where this "
                                                  "machine migrated to", fix))
    elif not os.path.isdir(home):
        verdicts.append(Verdict("pointer", False, "the pointer names %s, which does not exist"
                                % home, "mount it, or: %s   # restores it from the backup"
                                % run.fix("--migrate-home", home)))
    elif inside(home, run.default) or inside(run.default, home):
        # Reversing onto itself would end by clearing the home it just filled.
        verdicts.append(Verdict("pointer", False, "the pointer names %s, which holds or sits "
                                                  "inside the default home" % home,
                                "rm %s   # this machine is not migrated" %
                                shlex.quote(adlc_home.pointer_path())))
    if refused(verdicts):
        report_preflight(run, verdicts)
        return 1
    run.current = home
    verdicts += [Verdict("pointer", True, "the pointer names %s" % home),
                 check_env(run, [home]), check_markers(run, home), check_venv(run, run.default)]
    if refused(verdicts):
        verdicts.append(Verdict("locks", True, "not attempted"))
        report_preflight(run, verdicts)
        return 1
    verdicts.append(check_locks(run, new_locks(run, home)))
    report_preflight(run, verdicts)
    if refused(verdicts):
        return 1
    render_stamps(run, run.default)
    if run.dry:
        lines = ["%s -> %s" % (os.path.join(home, rel), os.path.join(run.default, rel))
                 for rel in MOVED_FILES if os.path.exists(os.path.join(home, rel))]
        lines += ["remove the tombstone %s" % hl.lock_path(run.default, c) for c in COUNTERS]
        lines += ["rebuild %s, regenerate %s" % (os.path.join(run.default, VENV),
                                                 os.path.join(run.default, VIEW))]
        lines += ["stamp %s" % p for p in stamp_drift(run)]
        lines += ["remove the pointer %s and the rc line in %s"
                  % (adlc_home.pointer_path(), run.rc_file)]
        lines += ["re-point %s" % run.facts(run.default).agents_mount,
                  "remove %s when nothing else remains in it" % home]
        run.say("plan:")
        for line in lines:
            run.say("  would: %s" % line)
        run.say("Dry run: no changes made. %d action(s) planned." % len(lines))
        return 0

    run.work_dir = os.path.join(run.default, BACK_PREFIX + utc_stamp())
    previous = {sig: signal.signal(sig, on_signal)
                for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    run.target = run.default
    try:
        run.say("staging %s:" % run.default)
        stage_tree(run, run.default)
        run.hook("staged")
        snapshot_stamped(run)
        hold(run, new_locks(run, home))
        for rel in MOVED_FILES:
            run.snapshots["old:" + rel] = snapshot(run, os.path.join(run.default, rel),
                                                   "old-" + rel.replace(os.sep, "__"))
            new = os.path.join(home, rel)
            if os.path.exists(new):
                run.snapshots["live:" + rel] = snapshot(run, new,
                                                        "live-" + rel.replace(os.sep, "__"))
        write_manifest(run)
        run.say("flipping:")
        run_flip(run, [("counters", step_back_counters), ("config", step_back_config),
                       ("ledger", step_back_ledger), ("stamps", step_stamps),
                       ("plist", step_plist), ("rc", step_back_rc),
                       ("pointer", step_back_pointer),
                       ("mount", lambda r: step_mount(r, r.default)),
                       ("tombstones", step_back_tombstones)])
    except (Refused, StepFailed, OSError, KeyboardInterrupt) as exc:
        return abandon(run, previous, exc, "--back",
                       "the migrated layout at %s is as it was" % home)
    release(run)
    for sig, handler in previous.items():
        signal.signal(sig, handler)
    retire_home(run, home)
    for path in run.backups() + [run.work_dir]:
        remove_path(path)
    run.say("")
    run.say("Migration summary: %d action(s); the home is %s again." % (run.actions, run.default))
    if os.environ.get(adlc_home.ENV):
        run.say("  note: this shell still exports ADLC_HOME: unset it, or open a new shell.")
    else:
        run.say("  note: a shell opened before this still exports ADLC_HOME: open a new one.")
    return 0


# --- entry -------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="install.sh --migrate-home", add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--delegate-installer", required=True)
    parser.add_argument("--rc-file", required=True)
    parser.add_argument("--dir")
    parser.add_argument("--back", action="store_true")
    parser.add_argument("--prune-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.back and (args.dir is not None or args.prune_backup):
        sys.stderr.write("install.sh: --migrate-home --back takes no <dir> and no "
                         "--prune-backup: it consumes the backup itself\n")
        return 2
    run = Run(args)
    if args.back:
        return do_back(run)
    if args.dir is None:
        if not args.prune_backup:
            sys.stderr.write("install.sh: --migrate-home needs a <dir>, or --back\n")
            return 2
        if run.dry:
            run.say("Dry run: would prune %s" % (", ".join(run.backups()) or "(no backup)"))
            return 0
        prune(run)
        run.say("Migration summary: 0 action(s) besides the prune.")
        return 0
    return do_forward(run, args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
