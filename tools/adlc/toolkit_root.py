#!/usr/bin/env python3
"""The toolkit root for Python tools, derived from this file (REQ-669 ADR-2).

One rule, held in one place. The root is two directories above this file's
directory, taken from ``os.path.realpath(__file__)``:

- ``realpath``, never ``abspath``. On the symlink route this file is reached
  through the skills symlink, and ``abspath`` walks from the link's directory
  instead of the real one (ASSUME-001's sharpening).
- Not ``git rev-parse --show-toplevel``. A plugin cache copy has no ``.git``
  (REQ-669 verification row 11), and ``~/.claude`` can sit inside an enclosing
  dotfiles repo, so git would name some other repo's toplevel.

The derived root is accepted only if ``realpath(<root>/tools/adlc/toolkit_root.py)``
is the running file. That is an identity check, not an existence check, the same
one ``tools/delegate/_common._repo_root`` makes (ASSUME-001, LESSON-620). What it
guarantees is narrow: the root is derived from this file's real location, never
from the path it was reached by, and ``<root>/tools/adlc/toolkit_root.py``
resolves to this very file, which normally means the file sits at
``*/tools/adlc/toolkit_root.py``. A copy outside a ``tools/adlc/`` layout, where
the walk would land on an unrelated directory, is refused, and so is a regular
file planted at the derived position. A symlink planted there that points back
at the running file does satisfy the check. It vouches for this file's place
under the root and for nothing else: whatever sits under that root is trusted
as the toolkit. A legitimate cache copy and the symlinked checkout both pass,
because each is its own root.

Standard library only: the doctor imports this module, and the doctor must load
on a machine with no delegation install and no PyYAML (LESSON-395).
"""

import os

#: Where this file sits relative to the root it reports.
_SELF_PARTS = ("tools", "adlc", "toolkit_root.py")


class ToolkitRootError(Exception):
    """The toolkit root cannot be established, or a toolkit path is unsafe."""


class ToolkitFileNotFound(ToolkitRootError):
    """A toolkit-relative file does not exist under the toolkit root."""


def toolkit_root():
    """Absolute real path of the toolkit root this file belongs to.

    Raises :class:`ToolkitRootError`, naming the expected path and the running
    file, when ``<root>/tools/adlc/toolkit_root.py`` is not this file.
    """
    running = os.path.realpath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(running)))
    expected = os.path.join(root, *_SELF_PARTS)
    if os.path.realpath(expected) != running:
        raise ToolkitRootError(
            "adlc: cannot derive the toolkit root: %s is not the running file %s"
            % (expected, running))
    return root


def toolkit_file(rel):
    """Absolute path of ``rel`` under :func:`toolkit_root`, which must exist.

    ``rel`` is a relative path with ``/`` separators. An empty or absolute path,
    or one with a ``..`` segment, raises :class:`ToolkitRootError`; a path that
    names no regular file raises :class:`ToolkitFileNotFound`.
    """
    if not isinstance(rel, str) or not rel:
        raise ToolkitRootError("adlc: toolkit path must be a non-empty string: %r" % (rel,))
    if os.path.isabs(rel) or rel.startswith(("/", "\\")):
        raise ToolkitRootError("adlc: toolkit path must be relative: %r" % (rel,))
    if ".." in rel.replace("\\", "/").split("/"):
        raise ToolkitRootError("adlc: toolkit path must not contain '..': %r" % (rel,))
    path = os.path.join(toolkit_root(), rel)
    if not os.path.isfile(path):
        raise ToolkitFileNotFound("adlc: toolkit file not found: %s" % path)
    return path
