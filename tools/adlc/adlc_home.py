#!/usr/bin/env python3
"""The toolkit's machine-state home, ``ADLC_HOME`` (REQ-654 BR-1, BR-2).

THE RULE (REQ-654 architecture ADR-2, REQ-663 BR-8). Machine state — the id
counters and their lock dirs, the reservations ledger, the machine config, the
delegate venv, the skills view — lives under one directory:

* ``ADLC_HOME`` set and absolute → that path, trailing slashes removed (a bare
  ``/`` stays ``/``);
* ``ADLC_HOME`` set, empty or not absolute → :class:`AdlcHomeError`, whose message
  names ``ADLC_HOME``. Never a silent fall-through to the default (BR-2);
* ``ADLC_HOME`` unset, pointer present → the home named by ``~/.claude/.adlc-home``,
  which ``install.sh --migrate-home`` writes;
* ``ADLC_HOME`` unset, no pointer → ``~/.claude``, spelled
  ``os.path.expanduser("~")`` joined with ``.claude`` exactly as every caller
  spelled it before REQ-654, so the default is byte-identical (the plan's Rule A);
* ``ADLC_HOME`` set and different from the pointer → :class:`AdlcPointerError`
  naming both. A fence that honoured it would allocate from a second counter;
* a pointer that is not a regular file, holds no absolute path, or names a
  directory that does not exist → :class:`AdlcPointerError` naming the pointer.

The machine config is ``$ADLC_CONFIG`` when that is set and non-empty, else
``<home>/adlc/config.yml``; a set ``ADLC_CONFIG`` never consults the home.

Written out at THREE sites, because a partial cannot import Python and a Python
module cannot be sourced by ``sh``. The other two:

* ``partials/adlc-home.sh`` — every partial, ``install.sh``, ``tools/delegate/install.sh``
* ``tools/delegate/_machine_config.py::adlc_home`` — the self-contained delegation tools

Change one, change all three: ``tests/test_adlc_home.py`` drives all three over
one input vector and fails on any disagreement.

Not here: toolkit *reads* go through ToolkitRoot (``toolkit_root.py``, REQ-669),
and the paths Claude Code itself owns stay where Claude Code reads them.

Pure standard library: the doctor imports this before any venv exists
(LESSON-395).
"""

import os

#: The variable, named once so every message spells it the same way.
ENV = "ADLC_HOME"

#: The pointer's name under the default home (REQ-663 ADR-2).
POINTER_NAME = ".adlc-home"


class AdlcHomeError(ValueError):
    """``ADLC_HOME`` is set but cannot be used. The message names the variable."""


class AdlcPointerError(AdlcHomeError):
    """The pointer cannot be used, or disagrees with ``ADLC_HOME`` (REQ-663 BR-8).

    Separate from a bad variable because doctor treats it differently: a broken
    pointer is a state of the machine for ``home-layout`` to report, where a bad
    ``ADLC_HOME`` is a bad invocation.
    """


def default_home() -> str:
    """``~/.claude``: the only name the default has, and where the pointer lives."""
    return os.path.join(os.path.expanduser("~"), ".claude")  # adlc-home: default


def pointer_path() -> str:
    """Where the pointer lives, whether or not one exists."""
    return os.path.join(default_home(), POINTER_NAME)


def read_pointer_line(path: str):
    """The first line of the file at ``path``, trailing slashes removed, or ``""``."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        line = fh.readline()
    line = line[:-1] if line.endswith("\n") else line
    return (line.rstrip("/") or "/") if line else ""


def pointer_home():
    """The home the pointer names, ``None`` with no pointer, or :class:`AdlcPointerError`."""
    path = pointer_path()
    if not os.path.lexists(path):
        return None
    if os.path.islink(path) or not os.path.isfile(path):
        raise AdlcPointerError(
            "the ADLC home pointer %s is not a regular file — run: install.sh --migrate-home "
            "<dir> to repair it, or remove it if this machine was never migrated "
            "(REQ-663 BR-8)" % path)
    try:
        value = read_pointer_line(path)
    except OSError as exc:
        raise AdlcPointerError("the ADLC home pointer %s cannot be read (%s) (REQ-663 BR-8)"
                               % (path, exc.strerror or "I/O error"))
    if not value.startswith("/"):
        raise AdlcPointerError(
            "the ADLC home pointer %s does not hold an absolute path, got %r — run: "
            "install.sh --migrate-home <dir> to repair it (REQ-663 BR-8)" % (path, value))
    if not os.path.isdir(value):
        raise AdlcPointerError(
            "the ADLC home pointer %s names %r, which does not exist — mount it, or run: "
            "install.sh --migrate-home %r to restore it from the backup (REQ-663 BR-8)"
            % (path, value, value))
    return value


def adlc_home() -> str:
    """The machine-state home, or :class:`AdlcHomeError`."""
    if ENV not in os.environ:
        pointed = pointer_home()
        return pointed if pointed is not None else default_home()
    value = os.environ[ENV]
    if value == "":
        raise AdlcHomeError(
            "ADLC_HOME is set but empty — unset it to use ~/.claude, or set it to "  # adlc-home: default
            "an absolute path (REQ-654 BR-2)")
    if not value.startswith("/"):
        raise AdlcHomeError(
            "ADLC_HOME must be an absolute path, got %r — unset it to use "
            "~/.claude, or set an absolute path (REQ-654 BR-2)" % value)  # adlc-home: default
    value = value.rstrip("/") or "/"
    pointed = pointer_home()
    if pointed is not None and pointed != value:
        raise AdlcPointerError(
            "ADLC_HOME is %r but the ADLC home pointer names %r — unset ADLC_HOME, or run "
            "install.sh --migrate-home --back first (REQ-663 BR-8)" % (value, pointed))
    return value


def adlc_home_source() -> str:
    """``env``, ``pointer`` or ``default``: what decided the home."""
    adlc_home()
    if ENV in os.environ:
        return "env"
    return "pointer" if pointer_home() is not None else "default"


def machine_config_path() -> str:
    """``$ADLC_CONFIG``, else ``<home>/adlc/config.yml`` (existing precedence, BR-2)."""
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(adlc_home(), "adlc", "config.yml")


def validate():
    """The error message when the home cannot be resolved, else ``None``."""
    try:
        adlc_home()
    except AdlcHomeError as exc:
        return str(exc)
    return None


def pointer_error():
    """The message when the pointer is what stops the home resolving, else ``None``."""
    try:
        adlc_home()
    except AdlcPointerError as exc:
        return str(exc)
    except AdlcHomeError:
        return None
    return None
