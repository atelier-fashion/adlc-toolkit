#!/usr/bin/env python3
"""exec_surfaces — every file the exec engine writes for a run, outside its run directory
(REQ-662 ADR-4: BR-4, BR-15, BR-16).

Two places:

* **A working copy.** Each ``exec.config_surfaces`` entry is a path the harness reads once the
  folder is trusted. The engine renders each one whole or makes it absent: the adapter's own
  rule file (``exec.rule_file``) with the run's text, a project-rendered surface inside one
  (the working-copy config) with its project render, and nothing else. A directory surface
  is compared with a manifest of sha256 per file, and a stray file in it is deleted. The
  project's own allowlist file inside a surface is absent, because the exec rule file is the
  whole policy, and under ``context_delivery: prompt`` so is the harness's hook file.
* **A user policy folder.** ``exec.user_policy_file`` is the toolkit's own deny-tier file
  beside the operator's rules. It is written whole and atomically, under a lock, and the
  folder is checked against a manifest the engine recorded when it wrote the file.

Four checks use one manifest. Before a launch and before a resume a working-copy mismatch is
repaired by the render and reported (``rule_file_rerendered``), and a policy-folder mismatch
refuses the run. At exit and at the halt any mismatch is a ``config_surface_violation``. The
expected manifest is the orchestrator's, kept in the run directory: nothing a harness can
write decides a check here (LESSON-718), and the engine runs nothing it reads.

Every write ``lstat``s every component: a symlink, a hardlink or a non-regular file is
refused, and the resolved path must be under the root it was written for. Nothing here
follows a link or opens anything but a regular file. Paths are compared case-folded, as a
case-insensitive filesystem resolves them.

``bypass_config_keys`` are read from the user config and the working-copy config before a
launch and before a resume. TOML is read with ``toml_merge.scan``, the reader the renderer
uses (LESSON-716), and a file that cannot be read with certainty refuses the run.

What the render writes or removes in a working copy is hidden from git for the run, best
effort (BR-17): a tracked path is marked ``skip-worktree`` and restored from the blob oid
recorded at launch, an untracked one is listed in an engine-owned excludes file that the
working copy's own ``core.excludesFile`` names. The control is the halt-time PR-diff gate,
which is ``exec_gates``'; the trust entry in the user config (BR-5) is not done here either.

No harness name is compared here: every path and key comes from the adapter. Standard library
only.
"""

import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from collections import OrderedDict, namedtuple

import exec_ledger as el
import harness_adapter as ha
import harness_render as hr
import toml_merge

#: What a path reads as when it is not one regular file: the manifest's value in place of a
#: checksum. ``None`` is absent.
SYMLINK = "symlink"
HARDLINK = "hardlink"
DIRECTORY = "directory"
SPECIAL = "special file"
#: How long a writer waits for the policy file's lock before it refuses.
LOCK_TIMEOUT_S = 30.0
#: A file the engine writes into a working copy or a policy folder.
FILE_MODE = 0o644
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

#: One path that is not what the manifest says: ``expected`` is a sha256 or None (absent),
#: ``found`` a sha256, None or one of the markers above.
Change = namedtuple("Change", "path expected found")
#: One ``bypass_config_keys`` key a config file sets to a value the toolkit's render does not.
Hit = namedtuple("Hit", "path key value")
#: One config surface: its path, and whether it is a directory.
Surface = namedtuple("Surface", "rel directory")


class SurfaceRefused(Exception):
    """A write, a scan or a check refused: the message names the path, nothing was changed."""

    def __init__(self, message, path=None, key=None):
        super().__init__(message)
        self.path = path
        self.key = key


# ---- paths -----------------------------------------------------------------------------------
def _parts(rel):
    """``rel`` as path components: relative, with no empty, ``.`` or ``..`` segment."""
    text = str(rel).rstrip("/")
    if not text or text.startswith("/") or "\\" in text:
        raise SurfaceRefused("%r is not a relative path the engine writes" % (rel,), rel)
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise SurfaceRefused("%r holds an empty, `.` or `..` segment, so it could resolve "
                             "outside its root" % (rel,), rel)
    return parts


def fold(path):
    """``path`` as a case-insensitive filesystem compares it."""
    return os.path.normpath(str(path)).casefold()


def within(root, path):
    """Whether ``path`` resolves under ``root``, both resolved and compared case-folded."""
    base = fold(os.path.realpath(root))
    target = fold(os.path.realpath(path))
    return target.startswith(base.rstrip(os.sep) + os.sep)


def _inside(rel, surface):
    a, b = fold(rel), fold(surface)
    return a == b or a.startswith(b + "/")


def user_path(path, environ):
    """A ``$HOME/`` or ``$ADLC_HOME/`` path of the adapter, expanded with the run's own
    environment: the one the harness is handed, not this process's."""
    for name in ("$HOME", "$ADLC_HOME"):
        if path == name or path.startswith(name + "/"):
            base = (environ or {}).get(name[1:])
            if not base and name == "$ADLC_HOME":
                import adlc_home
                base = adlc_home.adlc_home()
            if not base or not os.path.isabs(base):
                raise SurfaceRefused("%s is not an absolute path in the run's environment, so "
                                     "%s cannot be placed" % (name, path), path)
            return base.rstrip("/") + path[len(name):]
    raise SurfaceRefused("%r is not under $HOME/ or $ADLC_HOME/" % (path,), path)


def is_user_path(path):
    return str(path).startswith(("$HOME/", "$ADLC_HOME/"))


# ---- what is at a path, read without following anything ---------------------------------------
def _sha_open(path, st):
    """The sha256 of the regular file at ``path``, opened without following a link and checked
    to be the file ``st`` describes; :data:`SPECIAL` when it was swapped in between."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    except OSError:
        return SPECIAL
    try:
        now = os.fstat(fd)
        if not stat.S_ISREG(now.st_mode) or (now.st_dev, now.st_ino) != (st.st_dev, st.st_ino):
            return SPECIAL
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(fd)


def found(root, rel):
    """What ``rel`` under ``root`` is now: its sha256, None when absent, or a marker naming
    what it is instead. No link is followed and only a regular file with one link is read."""
    path = root
    parts = _parts(rel)
    for i, part in enumerate(parts):
        path = os.path.join(path, part)
        try:
            st = os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None
        last = i == len(parts) - 1
        if stat.S_ISLNK(st.st_mode):
            return SYMLINK if last else "%s at %s" % (SYMLINK, "/".join(parts[:i + 1]))
        if not last:
            if not stat.S_ISDIR(st.st_mode):
                return "%s at %s" % (SPECIAL, "/".join(parts[:i + 1]))
            continue
        if stat.S_ISDIR(st.st_mode):
            return DIRECTORY
        if not stat.S_ISREG(st.st_mode):
            return SPECIAL
        if st.st_nlink > 1:
            return HARDLINK
        return _sha_open(path, st)
    return None


def sha256_text(text):
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    return hashlib.sha256(data).hexdigest()


def _entries(root, rel):
    """``(rel, found)`` for every entry under the directory ``rel`` that is not itself a real
    directory, walked with ``lstat`` and never through a link. A ``rel`` that is not a real
    directory is itself the one entry."""
    top = os.path.join(root, *_parts(rel))
    try:
        st = os.lstat(top)
    except (FileNotFoundError, NotADirectoryError):
        return []
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return [(rel.rstrip("/"), found(root, rel))]
    out = []
    pending = [rel.rstrip("/")]
    while pending:
        current = pending.pop()
        with os.scandir(os.path.join(root, *_parts(current))) as it:
            names = sorted(entry.name for entry in it)
        for name in names:
            child = current + "/" + name
            full = os.path.join(root, *_parts(child))
            try:
                cst = os.lstat(full)
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(cst.st_mode) and not stat.S_ISLNK(cst.st_mode):
                pending.append(child)
            else:
                out.append((child, found(root, child)))
    return sorted(out)


# ---- the guarded write -----------------------------------------------------------------------
def _refuse(root, parts, i, why):
    shown = "/".join(parts[:i + 1])
    raise SurfaceRefused("%s in %s %s, so the engine neither writes nor reads through it "
                         "(REQ-662 BR-15)" % (shown, root, why), shown)


def check(root, rel, kind="file"):
    """``lstat`` every component of ``rel`` under ``root``. A symlink anywhere is refused; a
    component above the last must be a real directory; the last, when present, must be one
    regular file with one link (``kind`` ``file``) or a real directory (``dir``). The resolved
    path must be under ``root``. A missing component ends the walk: it is created by the
    write."""
    parts = _parts(rel)
    path = root
    for i, part in enumerate(parts):
        path = os.path.join(path, part)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            break
        last = i == len(parts) - 1
        if stat.S_ISLNK(st.st_mode):
            _refuse(root, parts, i, "is a symlink")
        if not last or kind == "dir":
            if not stat.S_ISDIR(st.st_mode):
                _refuse(root, parts, i, "is not a directory but a %s"
                        % ("file" if stat.S_ISREG(st.st_mode) else "FIFO, socket or device"))
            continue
        if stat.S_ISDIR(st.st_mode):
            _refuse(root, parts, i, "is a directory, not a file")
        if not stat.S_ISREG(st.st_mode):
            _refuse(root, parts, i, "is not a regular file but a FIFO, socket or device")
        if st.st_nlink > 1:
            _refuse(root, parts, i, "is a hardlink (%d links)" % st.st_nlink)
    if not within(root, os.path.join(root, *parts)):
        raise SurfaceRefused("%s resolves outside %s, so the engine neither writes nor reads "
                             "it (REQ-662 BR-15)" % (rel, root), rel)


def guarded_write(root, rel, text):
    """Write ``text`` to ``rel`` under ``root`` whole and atomically: every component checked
    first (:func:`check`), each missing directory made and checked again, then a temp file in
    the same directory renamed over the target. Returns the sha256 of what was written."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    parts = _parts(rel)
    check(root, rel, "file")
    parent = root
    for i, part in enumerate(parts[:-1]):
        parent = os.path.join(parent, part)
        try:
            os.mkdir(parent, 0o755)
        except FileExistsError:
            pass
        st = os.lstat(parent)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            _refuse(root, parts, i, "is not a real directory")
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".adlc-exec-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fchmod(fh.fileno(), FILE_MODE)
        os.replace(tmp, os.path.join(parent, parts[-1]))
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise
    check(root, rel, "file")
    return hashlib.sha256(data).hexdigest()


def _remove_tree(path):
    """Delete the real directory ``path`` and everything under it, never through a link."""
    with os.scandir(path) as it:
        entries = list(it)
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            _remove_tree(entry.path)
        else:
            os.unlink(entry.path)
    os.rmdir(path)


def guarded_remove(root, rel):
    """Make ``rel`` under ``root`` absent: a link, a FIFO or a file is unlinked (never
    followed or opened), a real directory deleted with what is under it. A component above it
    that is a link or not a directory is refused. Returns whether anything was there."""
    parts = _parts(rel)
    if len(parts) > 1:
        check(root, "/".join(parts[:-1]), "dir")
    path = os.path.join(root, *parts)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode):
        _remove_tree(path)
    else:
        os.unlink(path)
    return True


# ---- the working copy's render and its manifest ----------------------------------------------
def _data(adapter):
    """The loaded adapter dict, from an ``ExecAdapter`` or the dict itself."""
    return adapter.adapter if hasattr(adapter, "adapter") else adapter


def surfaces(block, rendered=()):
    """The adapter's ``config_surfaces``: a :class:`Surface` each. A surface is a directory
    when it is declared with a trailing ``/`` or a rendered file lies under it, never because
    of what is on disk."""
    out = []
    for item in block.get("config_surfaces") or []:
        rel = str(item).rstrip("/")
        directory = str(item).endswith("/") or any(
            _inside(r, rel) and fold(r) != fold(rel) for r in rendered)
        out.append(Surface(rel, directory))
    return out


def working_copy_render(adapter, files, toolkit):
    """What the engine writes into a working copy for one run, as an ordered map of path to
    text (rendered whole) or None (absent). ``files`` is the run's
    ``harness_render.ExecFiles`` (or None when both tiers are flags), rendered with the run's
    own branch.

    The rule file holds ``files.rule_file``. Every project-rendered file inside a config
    surface is rendered as the project render renders it, so the exec render of the
    working-copy config equals the project render (AC-22); the project's allowlist file is
    absent, because the exec rule file is the whole policy, and under ``context_delivery:
    prompt`` so is the hook file (BR-15). An adapter with no config surface and no rule file
    gets nothing, and no render is run for it."""
    data = _data(adapter)
    block = data.get("exec") or {}
    declared = [str(s).rstrip("/") for s in block.get("config_surfaces") or []]
    out = OrderedDict()
    if declared:
        wanted = [s for s in ha.SURFACES if s != "agents"]
        try:
            plans, _printed = hr.plan_surfaces(data, "project", os.sep, toolkit, wanted)
        except hr.RenderError as exc:
            raise SurfaceRefused("harness %s: the project render of a config surface failed: "
                                 "%s" % (data.get("name"), exc))
        for plan in plans:
            if not any(_inside(plan.rel, s) for s in declared):
                continue
            if "permissions" in plan.surfaces:
                out[plan.rel] = None
            elif "hooks" in plan.surfaces and block.get("context_delivery") == "prompt":
                out[plan.rel] = None
            else:
                out[plan.rel] = plan.content
    rule = block.get("rule_file")
    if rule and files is not None and getattr(files, "rule_file", None) is not None:
        out.pop(rule, None)
        out[rule] = files.rule_file
    return out


def manifest_of(render, block):
    """The manifest a working copy must match after ``render``: ``files`` (path to sha256),
    ``absent`` (paths that must not exist) and ``directories`` (directory surfaces, where any
    other file is a stray). A file surface the render does not name is absent."""
    files = OrderedDict((rel, sha256_text(text)) for rel, text in render.items()
                        if text is not None)
    absent = [rel for rel, text in render.items() if text is None]
    directories = []
    for surface in surfaces(block, list(files)):
        if surface.directory:
            directories.append(surface.rel)
        elif not any(fold(surface.rel) == fold(r) for r in list(files) + absent):
            absent.append(surface.rel)
    return {"files": dict(files), "absent": sorted(set(absent)),
            "directories": sorted(set(directories))}


def _expected(root, rel, files):
    """Whether a walked ``rel`` is a manifest file: spelled the same, or a case variant that is
    the same directory entry, as a case-insensitive filesystem would have it."""
    if rel in files:
        return True
    for want in files:
        if fold(want) == fold(rel):
            try:
                return os.path.samestat(os.lstat(os.path.join(root, *_parts(want))),
                                        os.lstat(os.path.join(root, *_parts(rel))))
            except OSError:
                return False
    return False


def render(root, plan, block):
    """Bring the working copy at ``root`` to ``plan`` (:func:`working_copy_render`): every
    file written whole, every absent path removed, every stray in a directory surface deleted.
    Every component is checked before anything is changed, so a refusal changes nothing.

    Returns ``(manifest, changes)``: ``changes`` is a :class:`Change` per path the render
    wrote or removed, ``found`` what was there before. ``found == expected`` is a checksum
    that matched: the file was already the render."""
    manifest = manifest_of(plan, block)
    for rel in manifest["files"]:
        check(root, rel, "file")
    for rel in manifest["directories"]:
        check(root, rel, "dir")
    for rel in manifest["absent"]:
        parts = _parts(rel)
        if len(parts) > 1:
            check(root, "/".join(parts[:-1]), "dir")
    changes = []
    for rel, text in plan.items():
        if text is None:
            continue
        before = found(root, rel)
        written = guarded_write(root, rel, text)
        changes.append(Change(rel, written, before))
    for rel in manifest["absent"]:
        before = found(root, rel)
        if guarded_remove(root, rel):
            changes.append(Change(rel, None, before))
    for directory in manifest["directories"]:
        for rel, what in _entries(root, directory):
            if not _expected(root, rel, manifest["files"]):
                guarded_remove(root, rel)
                changes.append(Change(rel, None, what))
    return manifest, changes


def verify(root, manifest):
    """Every :class:`Change` between the working copy at ``root`` and ``manifest``, read and
    never written: a file that differs, an absent path that exists, a stray in a directory
    surface. Empty when the working copy is what the engine rendered."""
    out = []
    for rel, sha in sorted(manifest.get("files", {}).items()):
        now = found(root, rel)
        if now != sha:
            out.append(Change(rel, sha, now))
    for rel in manifest.get("absent", []):
        now = found(root, rel)
        if now is not None:
            out.append(Change(rel, None, now))
    shown = {fold(c.path) for c in out}
    for directory in manifest.get("directories", []):
        for rel, what in _entries(root, directory):
            if fold(rel) not in shown and not _expected(root, rel, manifest.get("files", {})):
                out.append(Change(rel, None, what))
    return out


def rendered_paths(manifest):
    """``(paths, prefixes)`` of a working-copy manifest: every path the engine renders or makes
    absent for a run, file surfaces included, and the directory surfaces, each a prefix. What
    the halt-time PR-diff gate and the hiding of exec-rendered paths cover (BR-17)."""
    paths = set(manifest.get("files", {})) | set(manifest.get("absent", []))
    return sorted(paths), sorted(set(manifest.get("directories", [])))


def reload_effective(block):
    """Whether a rule file edited mid-run can take effect before the next re-render (BR-15):
    ``live`` says so, ``startup`` says not, and ``unknown`` is read as ``live``."""
    return block.get("rules_reload") != "startup"


def change_text(change):
    """One :class:`Change` as a person reads it."""
    def shown(value):
        if value is None:
            return "absent"
        return "sha256 %s" % value[:12] if _SHA_RE.match(value) else value
    return "%s: expected %s, found %s" % (change.path, shown(change.expected),
                                          shown(change.found))


def violation_text(change, block, where):
    """A ``config_surface_violation`` as the halt and the run log state it (BR-15)."""
    reach = ("rules_reload is %s, so the edit may have taken effect mid-run"
             % block.get("rules_reload", "unknown") if reload_effective(block) else
             "rules_reload is startup, so the edit could not take effect before the next "
             "re-render")
    return "config_surface_violation at %s: %s changed since the engine rendered it; %s" % (
        where, change_text(change), reach)


# ---- hiding what the render wrote from git, and restoring it (BR-17) -------------------------
#: The setting a working copy's own ``core.excludesFile`` needs, and the git that first has it.
WORKTREE_CONFIG = "extensions.worktreeConfig"
WORKTREE_CONFIG_GIT = (2, 20)
#: The index modes a hidden path is written back as: a file and an executable file.
_RESTORABLE = {"100644": FILE_MODE, "100755": 0o755}
#: One stage-0 index entry: its ``ls-files -t`` tag (``S`` is skip-worktree), mode and oid.
Entry = namedtuple("Entry", "tag mode oid")


def renders_files(block):
    """Whether an adapter writes into a working copy for a run (a rule file or a config
    surface). Only such an adapter hides anything from git or needs
    ``extensions.worktreeConfig``; a flags-only one is unchanged (BR-1)."""
    return bool(block.get("config_surfaces") or block.get("rule_file"))


def _git(box, repo, args, what, cwd=None, ok=(0,)):
    """``box.git``, which runs with hooks and fsmonitor disabled; any other exit status
    refuses, naming ``what``."""
    res = box.git(repo, args, cwd=cwd)
    if res.returncode not in ok:
        raise SurfaceRefused("%s failed in %s: %s" % (what, cwd or repo, res.stderr.strip()))
    return res


def worktree_config(box, repo):
    """``repo`` reading config per working copy, which hiding an untracked render needs:
    ``present`` when its git config already sets ``extensions.worktreeConfig``, ``enabled``
    when this call has set it in the repository's own config, where it stays set.

    Refused, naming the setting, when the git predates it, when the config sets it false, and
    when the config sets ``core.worktree`` or a true ``core.bare``: with the extension on,
    every linked working copy reads those, and git's worktree documentation moves them to the
    main working tree's ``config.worktree`` first, a change the engine does not make."""
    match = re.search(r"(\d+)\.(\d+)", box.git(repo, ["version"]).stdout)
    version = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    if version < WORKTREE_CONFIG_GIT:
        raise SurfaceRefused("%s needs git %d.%d or newer, and this git is %d.%d" % (
            (WORKTREE_CONFIG,) + WORKTREE_CONFIG_GIT + version), WORKTREE_CONFIG)

    def local(key, kind=None):
        args = ["config", "--local"] + (["--type=" + kind] if kind else []) + ["--get", key]
        res = _git(box, repo, args, "reading %s" % key, ok=(0, 1))
        return res.stdout.strip() if res.returncode == 0 else None

    have = local(WORKTREE_CONFIG, "bool")
    if have == "true":
        return "present"
    if have == "false":
        raise SurfaceRefused("%s is false in %s's git config, and the engine hides what it "
                             "renders in a working copy through `git config --worktree`, which "
                             "needs it true" % (WORKTREE_CONFIG, repo), WORKTREE_CONFIG)
    moved = [key for key, value in (("core.worktree", local("core.worktree")),
                                    ("core.bare", local("core.bare", "bool")))
             if value and value != "false"]
    if moved:
        raise SurfaceRefused("enabling %s in %s is refused: its git config sets %s, which every "
                             "linked working copy would then read, and git's worktree "
                             "documentation moves it to config.worktree first"
                             % (WORKTREE_CONFIG, repo, " and ".join(moved)), WORKTREE_CONFIG)
    res = box.git(repo, ["config", "--local", WORKTREE_CONFIG, "true"])
    if res.returncode != 0 or local(WORKTREE_CONFIG, "bool") != "true":
        raise SurfaceRefused("enabling %s in %s was refused: %s" % (
            WORKTREE_CONFIG, repo, res.stderr.strip() or "it does not read back true"),
            WORKTREE_CONFIG)
    return "enabled"


def _index(box, repo, wc, paths):
    """``{path: Entry}`` for each stage-0 index entry of ``wc`` at or under one of ``paths``,
    matched case-folded (``:(icase,literal)``), as a case-insensitive filesystem resolves
    them. The keys are the index's own spelling."""
    if not paths:
        return {}
    specs = [":(icase,literal)%s" % str(p).rstrip("/") for p in paths]
    res = _git(box, repo, ["ls-files", "-z", "-s", "-t", "--"] + specs, "listing the index",
               cwd=wc)
    out = {}
    for item in res.stdout.split("\0"):
        head, _, rel = item.partition("\t")
        fields = head.split(" ")
        if rel and len(fields) == 4 and fields[3] == "0":
            out[rel] = Entry(fields[0], fields[1], fields[2])
    return out


def inherited_excludes(box, repo, environ):
    """The text of the excludes file a working copy of ``repo`` reads without the engine's
    setting, which that setting replaces: the repository's ``core.excludesFile``, else the
    operator's global one, else git's default (``$XDG_CONFIG_HOME/git/ignore``,
    ``~/.config/git/ignore``). Read as patterns, never run; one that cannot be read is empty."""
    environ = environ or {}
    res = box.git(repo, ["config", "--local", "--path", "--get", "core.excludesFile"])
    path = res.stdout.strip() if res.returncode == 0 else ""
    env = {"HOME": environ.get("HOME", ""), "XDG_CONFIG_HOME": environ.get("XDG_CONFIG_HOME", ""),
           "PATH": "/usr/bin:/bin"}
    if not path:
        res = subprocess.run([box.tools["git"], "config", "--global", "--path", "--get",
                              "core.excludesFile"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, universal_newlines=True, env=env,
                             cwd=box.run_dir)
        path = res.stdout.strip() if res.returncode == 0 else ""
    if not path and (env["XDG_CONFIG_HOME"] or env["HOME"]):
        path = os.path.join(env["XDG_CONFIG_HOME"] or os.path.join(env["HOME"], ".config"),
                            "git", "ignore")
    if not os.path.isabs(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _ignore_line(rel):
    """``rel`` as one gitignore pattern matching that path alone, from the working-copy root."""
    return "/" + "".join("\\" + c if c in "\\*?[ " else c for c in rel)


def hide(box, repo, wc, manifest, record, excludes, environ=None, gitdir_write=None):
    """Keep what :func:`render` wrote or removed in ``wc``, a working copy of ``repo``, out of
    git's view for the run. ``record`` is the run record's entry for ``wc`` (``{}`` the first
    time), updated in place and returned:

    * ``launchBlobs``: each tracked path the render covers (``manifest``'s files and absent
      paths, and anything under a directory surface), with the index mode and blob oid it had
      when first hidden. Recorded once: a path first tracked at a later launch or resume is
      recorded as None, so a commit the model made is never taken for the launch state.
    * ``skipWorktree``: each of those paths, marked ``skip-worktree``.
    * ``untracked``: each rendered file git does not track, listed in ``excludes``, an
      engine-owned file outside the working copy that this working copy's ``core.excludesFile``
      names (``git config --worktree``; the shared ``info/exclude`` is never written), after
      the excludes file that setting replaces (:func:`inherited_excludes`).

    ``gitdir_write(write)`` runs ``write``, the one call here that changes a file the common
    gitdir checksum covers (REQ-659 BR-23 b). This is best effort: ``git add --sparse`` and
    ``git update-index --no-skip-worktree`` defeat it, a declared residual (BR-19), and the
    halt-time PR-diff gate is the control."""
    gitdir_write = gitdir_write or (lambda write: write())
    paths, prefixes = rendered_paths(manifest)
    for rel in paths + prefixes:
        _parts(rel)
        if "\n" in rel or "\r" in rel:
            raise SurfaceRefused("%r holds a line break, so no excludes line can name it"
                                 % (rel,), rel)
    index = _index(box, repo, wc, paths + prefixes)
    first = "launchBlobs" not in record
    blobs = record.setdefault("launchBlobs", {})
    for rel, entry in sorted(index.items()):
        if rel not in blobs:
            blobs[rel] = {"mode": entry.mode, "oid": entry.oid} if first else None
    mark = sorted(rel for rel, entry in index.items() if entry.tag != "S")
    if mark:
        _git(box, repo, ["update-index", "--skip-worktree", "--"] + mark,
             "marking skip-worktree", cwd=wc)
    record["skipWorktree"] = sorted(set(record.get("skipWorktree") or []) | set(index))
    tracked = {fold(rel) for rel in index}
    record["untracked"] = sorted(r for r in manifest.get("files", {}) if fold(r) not in tracked)
    if record["untracked"]:
        record["excludesFile"] = excludes
        text = ("# Written by the ADLC exec engine for one run (REQ-662 BR-17): the excludes "
                "file this setting replaces, then the paths the engine renders untracked.\n"
                + inherited_excludes(box, repo, environ).rstrip("\n") + "\n"
                + "".join(_ignore_line(rel) + "\n" for rel in record["untracked"]))
        el.atomic_write(excludes, text.encode("utf-8"))
        res = _git(box, repo, ["config", "--worktree", "--get", "core.excludesFile"],
                   "reading core.excludesFile", cwd=wc, ok=(0, 1))
        if res.returncode != 0 or res.stdout.strip() != excludes:
            gitdir_write(lambda: _git(
                box, repo, ["config", "--worktree", "core.excludesFile", excludes],
                "`git config --worktree core.excludesFile` (%s)" % WORKTREE_CONFIG, cwd=wc))
    return record


def _write_blob(box, repo, wc, rel, entry, staging):
    """The blob ``entry`` names, written to ``rel`` under ``wc`` byte for byte: read with
    ``git unpack-file`` in ``staging``, outside the working copy, then written by
    :func:`guarded_write` with its index mode."""
    if entry["mode"] not in _RESTORABLE:
        raise SurfaceRefused("its launch entry has mode %s, which the engine does not write"
                             % entry["mode"], rel)
    os.makedirs(staging, exist_ok=True)
    res = _git(box, repo, ["--git-dir=" + box.common_dir(repo), "unpack-file", entry["oid"]],
               "reading blob %s" % entry["oid"], cwd=staging)
    tmp = os.path.join(staging, os.path.basename(res.stdout.strip()))
    try:
        with open(tmp, "rb") as fh:
            data = fh.read()
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)
    guarded_write(wc, rel, data)
    os.chmod(os.path.join(wc, *_parts(rel)), _RESTORABLE[entry["mode"]])


def restore(box, repo, wc, record, staging, gitdir_write=None):
    """Undo :func:`hide` in ``wc``, before the final push and at cleanup: each path tracked at
    launch written back from the blob oid recorded then (never from HEAD, which may have
    moved), each untracked render removed unless the branch now tracks it, each skip-worktree
    mark the engine set cleared, and ``core.excludesFile`` unset where it is still the
    engine's. Idempotent; a working copy that is gone is left alone.

    Returns ``{"restored", "removed", "unmarked", "problems"}``. A path that cannot be
    restored is a problem, never a stop, because cleanup goes on."""
    gitdir_write = gitdir_write or (lambda write: write())
    out = {"restored": [], "removed": [], "unmarked": [], "problems": []}
    if not os.path.isdir(wc):
        return out
    excludes = record.get("excludesFile")
    if excludes:
        res = box.git(repo, ["config", "--worktree", "--get", "core.excludesFile"], cwd=wc)
        if res.returncode == 0 and res.stdout.strip() == excludes:
            res = gitdir_write(lambda: box.git(
                repo, ["config", "--worktree", "--unset", "core.excludesFile"], cwd=wc))
            if res.returncode != 0:
                out["problems"].append("core.excludesFile: %s" % res.stderr.strip())
    blobs = record.get("launchBlobs") or {}
    marked = record.get("skipWorktree") or []
    index = _index(box, repo, wc, sorted(set(marked) | set(blobs) |
                                         set(record.get("untracked") or [])))
    unmark = [rel for rel in marked if rel in index and index[rel].tag == "S"]
    if unmark:
        res = box.git(repo, ["update-index", "--no-skip-worktree", "--"] + unmark, cwd=wc)
        if res.returncode != 0:
            out["problems"].append("skip-worktree: %s" % res.stderr.strip())
        else:
            out["unmarked"] = unmark
    if out["unmarked"] == unmark:
        record["skipWorktree"] = []
    for rel in sorted(blobs):
        if blobs[rel] is None:
            continue
        try:
            _write_blob(box, repo, wc, rel, blobs[rel], staging)
            out["restored"].append(rel)
        except (SurfaceRefused, OSError) as exc:
            out["problems"].append("%s: %s" % (rel, exc))
    tracked = {fold(rel) for rel in index}
    for rel in record.get("untracked") or []:
        if fold(rel) in tracked:
            continue
        try:
            if guarded_remove(wc, rel):
                out["removed"].append(rel)
        except (SurfaceRefused, OSError) as exc:
            out["problems"].append("%s: %s" % (rel, exc))
    return out


# ---- bypass_config_keys (BR-16) --------------------------------------------------------------
def _owned_values(data, rel):
    """The values the toolkit's own render of the config at ``rel`` sets: the adapter's
    ``paths.config.values`` when ``rel`` is that surface's project or user path. A key set to
    one of these does not relax anything: the toolkit's render writes it."""
    spec = (data.get("paths") or {}).get("config") or {}
    if rel in (spec.get("project"), spec.get("user")):
        return dict(spec.get("values") or {})
    return {}


def _read_config(path, user):
    """The text of the config at ``path``, or None when it is absent. A working-copy config is
    read only as one regular file with one link; a user config may be the operator's link,
    and must resolve to a regular file."""
    try:
        st = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if user:
        try:
            st = os.stat(path)
        except OSError:
            raise SurfaceRefused("%s is a link to nothing" % path, path)
    elif stat.S_ISLNK(st.st_mode) or st.st_nlink > 1:
        raise SurfaceRefused("%s is a %s, which the engine does not read as a config"
                             % (path, "symlink" if stat.S_ISLNK(st.st_mode) else "hardlink"),
                             path)
    if not stat.S_ISREG(st.st_mode):
        raise SurfaceRefused("%s is not a regular file, so it cannot be read as a config"
                             % path, path)
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise SurfaceRefused("%s cannot be read: %s" % (path, exc.__class__.__name__), path)


def _json_pairs(pairs):
    seen = OrderedDict()
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key %r" % key)
        seen[key] = value
    return seen


def _toml_lookup(scan, key):
    """The raw value of the dotted ``key`` in a ``toml_merge.Scan``, or None."""
    parts = key.split(".")
    if len(parts) == 1:
        return scan.top.get(key)
    for i in range(1, len(parts)):
        table, sub = ".".join(parts[:i]), ".".join(parts[i:])
        row = scan.table_keys.get(table, {}).get(sub)
        if row is not None:
            return row[0]
    return None


def _toml_hits(path, text, keys, owned):
    undotted = tuple(k for k in keys if "." not in k)
    try:
        scan = toml_merge.scan(text, owned_keys=undotted)
    except toml_merge.TomlConstructError as exc:
        raise SurfaceRefused("%s cannot be read with certainty (%s), so whether it relaxes "
                             "approval or sandboxing is unknown (REQ-662 BR-16)" % (path, exc),
                             path)
    hits = []
    for key in keys:
        raw = _toml_lookup(scan, key)
        if raw is None:
            continue
        if key in owned:
            want = owned[key]
            same = (toml_merge.plain_string(raw) == want) if isinstance(want, str) else \
                raw == json.dumps(want)
            if same:
                continue
        hits.append(Hit(path, key, raw))
    return hits


def _json_hits(path, text, keys, owned):
    try:
        doc = json.loads(text, object_pairs_hook=_json_pairs)
    except ValueError as exc:
        raise SurfaceRefused("%s cannot be read with certainty (%s), so whether it relaxes "
                             "approval or sandboxing is unknown (REQ-662 BR-16)" % (path, exc),
                             path)
    if not isinstance(doc, dict):
        raise SurfaceRefused("%s is not a JSON object, so it cannot be scanned (REQ-662 BR-16)"
                             % path, path)
    hits = []
    for key in keys:
        node, present = doc, True
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                present = False
                break
        if present and not (key in owned and node == owned[key]):
            hits.append(Hit(path, key, json.dumps(node)))
    return hits


def bypass_scan(adapter, roots, environ):
    """BR-16: every :class:`Hit` in the configs ``bypass_config_keys`` names, the user ones
    once and each working-copy one under every root in ``roots``. A key is a hit when the file
    sets it to anything but the value the toolkit's own render of that file sets. A file that
    cannot be read with certainty refuses (:class:`SurfaceRefused`); an absent one is clean.

    The file is read by its extension: ``.toml`` with ``toml_merge.scan`` and ``.json`` with
    duplicate keys refused. Any other format has no reader here, so it refuses."""
    data = _data(adapter)
    block = data.get("exec") or {}
    hits = []
    for rel, keys in (block.get("bypass_config_keys") or {}).items():
        user = is_user_path(rel)
        if user:
            paths = [user_path(rel, environ)]
        else:
            paths = []
            for root in roots:
                check(root, rel, "file")
                paths.append(os.path.join(root, *_parts(rel)))
        owned = _owned_values(data, rel)
        for path in paths:
            text = _read_config(path, user)
            if text is None:
                continue
            if rel.endswith(".toml"):
                hits += _toml_hits(path, text, list(keys), owned)
            elif rel.endswith(".json"):
                hits += _json_hits(path, text, list(keys), owned)
            else:
                raise SurfaceRefused("%s has no reader in the engine, so its bypass keys cannot "
                                     "be scanned (REQ-662 BR-16)" % path, path)
    return hits


def hit_text(data, hit):
    return ("harness %s: %s sets %s = %s, a bypass_config_keys key that relaxes approval or "
            "sandboxing, so the run is refused (REQ-662 BR-16)"
            % (data.get("name"), hit.path, hit.key, hit.value))


# ---- the user policy folder (BR-4) -----------------------------------------------------------
def policy_path(adapter, environ):
    """The absolute path of the adapter's ``exec.user_policy_file``, or None for ``none``."""
    block = _data(adapter).get("exec") or {}
    value = block.get("user_policy_file")
    if not value or value == "none":
        return None
    return user_path(value, environ)


def record_path(adapter, environ):
    """Where the engine keeps the policy folder's manifest: its own state directory, never the
    folder it describes and never a working copy."""
    return os.path.join(el.exec_root(environ), "policy", "%s.json" % _data(adapter)["name"])


@contextlib.contextmanager
def file_lock(path, timeout=LOCK_TIMEOUT_S):
    """A lock directory at ``path + ".lock.d"`` (``mkdir``, the allocator's pattern), held for
    the block. A lock still held after ``timeout`` seconds refuses, naming it."""
    lock = path + ".lock.d"
    os.makedirs(os.path.dirname(lock), mode=0o700, exist_ok=True)
    end = time.time() + timeout
    while True:
        try:
            os.mkdir(lock, 0o700)
            break
        except FileExistsError:
            if time.time() > end:
                raise SurfaceRefused("the lock %s is still held after %ds: another writer of "
                                     "the policy file is running, or one died holding it; "
                                     "remove it once no exec run is live" % (lock, timeout),
                                     lock)
            time.sleep(0.02)
    try:
        yield lock
    finally:
        os.rmdir(lock)


def _folder_entries(folder):
    """``{name: found}`` for every entry under the policy folder, walked with ``lstat``. The
    folder may be the operator's link; nothing under it is followed."""
    real = os.path.realpath(folder)
    if not os.path.isdir(real):
        return {}
    out = {}
    pending = [""]
    while pending:
        current = pending.pop()
        with os.scandir(os.path.join(real, current) if current else real) as it:
            names = sorted(e.name for e in it)
        for name in names:
            rel = current + "/" + name if current else name
            try:
                st = os.lstat(os.path.join(real, rel))
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode):
                pending.append(rel)
            else:
                out[rel] = found(real, rel)
    return out


def check_policy(record, strict=True):
    """:func:`policy_problems` under the writers' lock, so a check never sees a writer's temp
    file. ``record`` names its own lock (``record``)."""
    with file_lock(record["record"]):
        return policy_problems(record, strict)


def policy_problems(record, strict=True):
    """Every :class:`Change` between the policy folder and ``record``: the toolkit's file
    missing or drifted, and a stray file. ``strict`` (at a launch, a resume, the exit and the
    halt) also counts an operator file that changed or went since the record; the pre-flight
    of a new batch reads ``strict=False``, because between runs the operator's own files are
    the operator's, and exec never judges or edits them."""
    folder = record["folder"]
    own = os.path.basename(record["path"])
    now = _folder_entries(folder)
    out = []
    if now.get(own) != record["sha256"]:
        out.append(Change(record["path"], record["sha256"], now.get(own)))
    for rel, what in sorted(now.items()):
        if rel == own:
            continue
        if rel not in record["files"]:
            out.append(Change(os.path.join(folder, rel), None, what))
        elif strict and record["files"][rel] != what:
            out.append(Change(os.path.join(folder, rel), record["files"][rel], what))
    if strict:
        for rel in sorted(set(record["files"]) - set(now) - {own}):
            out.append(Change(os.path.join(folder, rel), record["files"][rel], None))
    return out


def policy_refusal(data, problems, where):
    return ("harness %s: the user policy folder is not what the engine recorded, so the %s is "
            "refused (REQ-662 BR-4): %s; if you changed it yourself, run `adlc harness install "
            "--exec --harness %s` to write the toolkit's file and record the folder again"
            % (data.get("name"), where, "; ".join(change_text(c) for c in problems),
               data.get("name")))


def _write_policy(data, path, text, record_file):
    """The toolkit's file written whole and atomically when it is not already ``text``, then
    the folder's manifest recorded. Called under :func:`file_lock`."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(path)
    want = sha256_text(text)
    if found(folder, name) != want:
        guarded_write(folder, name, text)
    record = {"harness": data["name"], "path": path, "folder": folder, "sha256": want,
              "files": _folder_entries(folder), "record": record_file,
              "recordedAt": el.now()}
    os.makedirs(os.path.dirname(record_file), mode=0o700, exist_ok=True)
    el.atomic_json(record_file, record)
    return record


def read_record(adapter, environ):
    doc = el.read_json(record_path(adapter, environ))
    return doc if isinstance(doc, dict) and isinstance(doc.get("files"), dict) else None


def ensure_policy_file(adapter, environ, text):
    """The pre-flight's write of the user policy file (BR-4), under the lock: the folder is
    first checked against the engine's last record of it (a missing or drifted toolkit file,
    or a stray, refuses, naming it), then the file is written whole and atomically when the
    render changed, and the folder recorded again. Returns the record, which the run keeps
    and checks before each launch and resume; None when the adapter has no policy file."""
    data = _data(adapter)
    path = policy_path(data, environ)
    if path is None or text is None:
        return None
    record_file = record_path(data, environ)
    with file_lock(record_file):
        last = read_record(data, environ)
        if last is not None and last.get("path") == path:
            problems = policy_problems(last, strict=False)
            if problems:
                raise SurfaceRefused(policy_refusal(data, problems, "launch"), path)
        return _write_policy(data, path, text, record_file)


def install_policy_file(adapter, environ, text):
    """The write ``adlc harness install --exec`` makes, the operator's explicit one: the
    toolkit's file written whole and atomically under the lock, whatever it held, and the
    folder recorded as it now stands, the operator's own files included. A second run is a
    no-op on the file. ``text`` is the adapter's ``harness_render.ExecFiles.user_policy_file``
    (``ExecAdapter.rule_files``)."""
    data = _data(adapter)
    path = policy_path(data, environ)
    if path is None:
        raise SurfaceRefused("harness %s declares no exec.user_policy_file" % data.get("name"))
    record_file = record_path(data, environ)
    with file_lock(record_file):
        return _write_policy(data, path, text, record_file)
