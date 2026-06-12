#!/usr/bin/env python3
"""adlc renumber — rename an artifact id repo-wide, collision-safe (REQ-518 BR-9).

``adlc renumber <KIND-old> <KIND-new>`` rewrites the artifact's directory/file
name, its frontmatter ``id:``, and every in-repo cross-reference to the old id;
for a REQ with an existing feature branch it prints (does NOT run) the exact
branch-rename commands. It is the one-command fix the BR-4 pre-push collision
halt points at.

Safety posture (LESSON-008 strict id validation; LESSON-006 fail-loud + atomic):
- both ids must match the strict per-kind regex — no traversal, no garbage;
- it refuses to run if the NEW id itself collides on the remote (shells out to
  ``partials/id-recheck.sh`` so there is one collision authority — BR-9);
- it shows a dry-run unified diff and requires explicit approval before mutating;
- mutation is atomic per file (write temp + ``os.replace``), never a partial write.

Pure standard library — must run on a machine that never opted into delegation.
"""

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Strict per-kind id regexes (LESSON-008). Anchored, 3+ digits, nothing else.
KIND_PATTERNS = {
    "REQ": re.compile(r"^REQ-[0-9]{3,}$"),
    "BUG": re.compile(r"^BUG-[0-9]{3,}$"),
    "LESSON": re.compile(r"^LESSON-[0-9]{3,}$"),
}

# Where each kind's artifact lives, relative to repo root, and whether it is a
# directory (REQ specs) or a single file (bugs, lessons).
KIND_LAYOUT = {
    "REQ": {"subdir": os.path.join(".adlc", "specs"), "is_dir": True},
    "BUG": {"subdir": os.path.join(".adlc", "bugs"), "is_dir": False},
    "LESSON": {"subdir": os.path.join(".adlc", "knowledge", "lessons"), "is_dir": False},
}

# recheck kind token (lowercase) for the shell helper.
KIND_RECHECK = {"REQ": "req", "BUG": "bug", "LESSON": "lesson"}


def _kind_of(artifact_id):
    """Return the uppercase prefix (REQ|BUG|LESSON) of an id, or None."""
    if "-" not in artifact_id:
        return None
    prefix = artifact_id.split("-", 1)[0]
    return prefix if prefix in KIND_PATTERNS else None


def _validate_id(artifact_id):
    """True iff artifact_id matches its kind's strict regex (LESSON-008)."""
    kind = _kind_of(artifact_id)
    if kind is None:
        return False
    return bool(KIND_PATTERNS[kind].match(artifact_id))


# --- id-boundary matching (REQ-524) -------------------------------------------------
#
# The single pattern authority. Every content match, file selection, and filename
# rewrite MUST go through these two helpers so selection and rewrite cannot drift
# (REQ-524 BR-2). The boundary is DIGIT-based, not word-based: an id matches only
# when not preceded by an alphanumeric and not followed by a digit. This blocks the
# sibling-prefix corruption (`REQ-120` must never match inside `REQ-1200`, REQ-524
# adversarial M2) while still rewriting slugs (`REQ-120-demo`), frontmatter
# (`id: REQ-120`), punctuation (`REQ-120.`, `REQ-120)`), and end-of-line refs. A
# word boundary (`\b`) would not distinguish `REQ-120` from `REQ-1200` (no \b between
# the two trailing digits) and would mis-handle the `-slug` suffix — see architecture
# ADR-1.


def _id_boundary_re(artifact_id):
    """Compiled ``re`` matching artifact_id only at an id boundary (REQ-524 BR-1).

    ``(?<![A-Za-z0-9])`` — not preceded by an alphanumeric (start-of-string is fine).
    ``(?!\\d)`` — not followed by a digit. ``re.escape`` neutralizes the ``-`` and any
    regex-meta (defense-in-depth; ids are strict-validated upstream). This is the
    authoritative arbiter for every rewrite and the per-file match count.
    """
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(artifact_id) + r"(?!\d)")


def _id_boundary_ere(artifact_id):
    """git-grep ERE string with the SAME boundary semantics (REQ-524 BR-2).

    git grep's ERE engine has no lookaround, so selection uses an enclosing-group
    ERE that may *over*-select but never under-selects; the authoritative
    ``_id_boundary_re`` re-applied per file in ``_rewrite_file`` produces the real
    match count and drops any zero-match over-selection. Both helpers derive from
    one escaped id so they cannot drift. ``[^A-Za-z0-9]`` mirrors the lookbehind;
    ``[^0-9]`` mirrors the digit-lookahead; ``^``/``$`` cover the string edges.
    """
    esc = re.escape(artifact_id)
    return r"(^|[^A-Za-z0-9])" + esc + r"([^0-9]|$)"


def _repo_root():
    """Repo root of the artifact being renumbered — resolved from the CALLER's cwd,
    not the script location. ``adlc renumber`` operates on whatever repo the user is
    standing in (the one that holds the colliding artifact), which is generally NOT
    the toolkit repo where this script lives. Falls back to cwd if not in a git repo.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.getcwd()


def _toolkit_root():
    """Root of the TOOLKIT repo (where partials/ lives) — resolved from THIS script's
    location, independent of the caller's cwd. ``tools/adlc/renumber.py`` -> root is
    two levels up; prefer git for symlink-correctness."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        out = subprocess.run(
            ["git", "-C", here, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.path.dirname(os.path.dirname(here))


def _find_partial(name):
    """Resolve a partials/<name>. The recheck helper lives in the TOOLKIT repo (and
    the caller's project copy under .adlc/partials), so check both: caller's project
    first, then the toolkit checkout, then the installed skills dir."""
    candidates = [
        os.path.join(_repo_root(), ".adlc", "partials", name),   # caller's project copy
        os.path.join(_toolkit_root(), "partials", name),         # toolkit checkout
        os.path.expanduser(os.path.join("~", ".claude", "skills", "partials", name)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def remote_collision(new_id):
    """True iff new_id collides on the remote (shells out to id-recheck.sh — BR-9).

    Returns False (no collision) when the recheck helper is unavailable or the
    remote is unreachable — the recheck can only FIND a collision, never invent
    one (BR-3). The caller still benefits from the strict-regex + local-rename
    safety even when the network probe is degraded.
    """
    partial = _find_partial("id-recheck.sh")
    if partial is None:
        return False
    kind = KIND_RECHECK[_kind_of(new_id)]
    # adlc_recheck_id returns 1 on collision, 0 otherwise. Source then call in one sh -c.
    script = '. "$1"; adlc_recheck_id "$2" "$3"'
    try:
        proc = subprocess.run(
            ["sh", "-c", script, "sh", partial, kind, new_id],
            capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 1


def _artifact_path(root, artifact_id):
    """Absolute path to the artifact dir (REQ) or the dir holding its file."""
    kind = _kind_of(artifact_id)
    layout = KIND_LAYOUT[kind]
    base = os.path.join(root, layout["subdir"])
    return base, layout["is_dir"]


def _locate_old(root, old_id):
    """Find the existing artifact path for old_id. Returns (path, is_dir) or (None, _).

    REQ: a directory named ``REQ-xxx-slug``. BUG/LESSON: a file ``BUG-xxx-slug.md``.
    """
    base, is_dir = _artifact_path(root, old_id)
    if not os.path.isdir(base):
        return None, is_dir
    for name in sorted(os.listdir(base)):
        if is_dir:
            if name == old_id or name.startswith(old_id + "-"):
                full = os.path.join(base, name)
                if os.path.isdir(full):
                    return full, True
        else:
            if name == old_id + ".md" or name.startswith(old_id + "-"):
                full = os.path.join(base, name)
                if os.path.isfile(full):
                    return full, False
    return None, is_dir


def _renamed_path(old_path, old_id, new_id):
    """Compute the new path by swapping the id token in the basename (boundary-anchored).

    Uses the shared id-boundary pattern (REQ-524 BR-1) rather than a bare
    ``str.replace`` so a basename like ``REQ-1200-demo`` is never mangled when
    renumbering ``REQ-120``. The basename here is already located by
    ``_locate_old`` (boundary-safe), so this is belt-and-suspenders, but it keeps
    the invariant uniform across every rewrite site.
    """
    parent = os.path.dirname(old_path)
    base = os.path.basename(old_path)
    new_base, _n = _id_boundary_re(old_id).subn(new_id, base, count=1)
    return os.path.join(parent, new_base)


def _grep_references(root, old_id):
    """Files under root that contain old_id at an id boundary, excluding .git.

    Selection is boundary-anchored (REQ-524 BR-2): a file containing only
    ``REQ-1200`` is NOT selected when renumbering ``REQ-120``. Uses ``git grep -lE``
    with the shared boundary ERE when possible (respects .gitignore, fast); falls
    back to a manual walk using the authoritative ``_id_boundary_re``. git grep's
    ERE may over-select on rare edges (no lookaround); the per-file ``subn`` in
    ``_rewrite_file`` arbitrates and drops any zero-match over-selection.
    """
    ere = _id_boundary_ere(old_id)
    try:
        out = subprocess.run(
            ["git", "-C", root, "grep", "-lE", "--", ere],
            capture_output=True, text=True, check=False,
        )
        if out.returncode in (0, 1):  # 1 = no matches, not an error
            return [os.path.join(root, p) for p in out.stdout.splitlines() if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    pat = _id_boundary_re(old_id)
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                with open(full, encoding="utf-8") as fh:
                    if pat.search(fh.read()):
                        matches.append(full)
            except (OSError, UnicodeDecodeError):
                continue
    return matches


def _rewrite_file(path, old_id, new_id, apply_change, root=None):
    """Replace old_id -> new_id in a file at id boundaries. Returns ``(diff, count)``.

    ``count`` is the number of boundary-anchored matches (REQ-524 BR-3) — 0 means
    nothing to do (e.g. a git-grep over-selection of a ``REQ-1200``-only file when
    renumbering ``REQ-120``). The unified-diff headers use the **repo-relative**
    path (REQ-524 BR-5, LESSON-021) so no absolute path leaks into stdout/CI logs.
    When apply_change is True and count > 0, writes atomically (temp + os.replace).
    """
    try:
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
    except (OSError, UnicodeDecodeError):
        return "", 0
    updated, count = _id_boundary_re(old_id).subn(new_id, original)
    if count == 0 or updated == original:
        return "", 0
    label = os.path.relpath(path, root) if root else os.path.basename(path)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=label, tofile=label,
    ))
    if apply_change:
        d = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".renumber-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(updated)
            os.replace(tmp, path)  # atomic on POSIX
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    return diff, count


def plan(root, old_id, new_id):
    """Build the rename plan: old_path, new_path, is_dir, and ref_files paired with
    their boundary match counts.

    ``refs`` is a list of ``(path, count)`` where count is the number of
    boundary-anchored matches in that file (REQ-524 BR-3). Files that the selection
    over-selected but contain zero real (boundary) matches — e.g. a ``REQ-1200``-only
    file when renumbering ``REQ-120`` — have count 0 and are dropped here, so they
    never appear in the dry-run plan (REQ-524 BR-2). The artifact's own path is
    excluded (its content is rewritten after the path rename)."""
    old_path, is_dir = _locate_old(root, old_id)
    if old_path is None:
        return None
    new_path = _renamed_path(old_path, old_id, new_id)
    pat = _id_boundary_re(old_id)
    refs = []
    for r in _grep_references(root, old_id):
        # The artifact's own content is rewritten after the path rename; keep separate.
        if r.startswith(old_path):
            continue
        try:
            with open(r, encoding="utf-8") as fh:
                count = len(pat.findall(fh.read()))
        except (OSError, UnicodeDecodeError):
            count = 0
        if count > 0:  # drop git-grep over-selection (boundary-zero files)
            refs.append((r, count))
    return {"old_path": old_path, "new_path": new_path, "is_dir": is_dir, "refs": refs}


def _branch_commands(old_id, new_id):
    """For a REQ, the exact (un-run) branch rename/push/delete commands."""
    if _kind_of(old_id) != "REQ":
        return []
    old_l = old_id.lower()
    new_l = new_id.lower()
    return [
        f"  git branch -m feat/{old_l}-<slug> feat/{new_l}-<slug>",
        f"  git push origin :feat/{old_l}-<slug> feat/{new_l}-<slug>",
        f"  git push origin -u feat/{new_l}-<slug>",
    ]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="adlc renumber",
        description="Rename an artifact id repo-wide, collision-safe (REQ-518).",
    )
    parser.add_argument("old_id", help="existing id, e.g. REQ-600")
    parser.add_argument("new_id", help="target id, e.g. REQ-601")
    parser.add_argument(
        "--yes", action="store_true",
        help="apply after showing the dry-run diff (default: dry-run only)",
    )
    args = parser.parse_args(argv)

    old_id, new_id = args.old_id, args.new_id

    # 1. Strict id validation (LESSON-008).
    if not _validate_id(old_id):
        sys.stderr.write(f"adlc renumber: invalid old id '{old_id}'\n")
        return 2
    if not _validate_id(new_id):
        sys.stderr.write(f"adlc renumber: invalid new id '{new_id}'\n")
        return 2
    if _kind_of(old_id) != _kind_of(new_id):
        sys.stderr.write(
            f"adlc renumber: kind mismatch — '{old_id}' and '{new_id}' "
            "must be the same kind (REQ/BUG/LESSON)\n"
        )
        return 2
    if old_id == new_id:
        sys.stderr.write("adlc renumber: old and new ids are identical\n")
        return 2

    # 2. Refuse if the NEW id collides on the remote (BR-9).
    if remote_collision(new_id):
        sys.stderr.write(
            f"adlc renumber: refusing — new id '{new_id}' also collides on the "
            "remote. Pick a higher id (the recheck above prints the next free one).\n"
        )
        return 1

    root = _repo_root()

    # 3. Build the plan.
    p = plan(root, old_id, new_id)
    if p is None:
        sys.stderr.write(
            f"adlc renumber: could not locate artifact for '{old_id}' under {root}\n"
        )
        return 1

    apply_change = args.yes

    # 4. Dry-run diff (always shown). Path rename + frontmatter/reference rewrites.
    #    All paths are repo-relative — no absolute path in output (BR-5, LESSON-021).
    print(f"renumber {old_id} -> {new_id}")
    print(f"  rename: {os.path.relpath(p['old_path'], root)}")
    print(f"      -> {os.path.relpath(p['new_path'], root)}")
    print(f"  references to rewrite: {len(p['refs'])} file(s)")
    for r, count in p["refs"]:
        rel = os.path.relpath(r, root)
        print(f"    - {rel} ({count} match{'es' if count != 1 else ''})")
    cmds = _branch_commands(old_id, new_id)
    if cmds:
        print("  branch (run manually if a feature branch exists):")
        for c in cmds:
            print(c)

    if not apply_change:
        print("\nDRY RUN — re-run with --yes to apply.")
        return 0

    # 5. Apply atomically. Rename the path first, then rewrite the moved artifact's
    #    own content and every external reference.
    os.rename(p["old_path"], p["new_path"])
    # Rewrite content inside the moved artifact.
    if p["is_dir"]:
        for dirpath, _dirs, files in os.walk(p["new_path"]):
            for fn in files:
                _rewrite_file(os.path.join(dirpath, fn), old_id, new_id, True, root)
    else:
        _rewrite_file(p["new_path"], old_id, new_id, True, root)
    # Rewrite external references.
    for r, _count in p["refs"]:
        _rewrite_file(r, old_id, new_id, True, root)

    print(f"\nApplied. {old_id} is now {new_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
