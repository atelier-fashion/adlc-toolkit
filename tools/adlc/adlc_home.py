#!/usr/bin/env python3
"""The toolkit's machine-state home, ``ADLC_HOME`` (REQ-654 BR-1, BR-2).

THE RULE (REQ-654 architecture ADR-2). Machine state — the id counters and their
lock dirs, the reservations ledger, the machine config, the delegate venv, the
skills view — lives under one directory:

* ``ADLC_HOME`` unset → ``~/.claude``, spelled ``os.path.expanduser("~")`` joined
  with ``.claude`` exactly as every caller spelled it before REQ-654, so the
  default is byte-identical (the plan's Rule A);
* ``ADLC_HOME`` set and absolute → that path, trailing slashes removed (a bare
  ``/`` stays ``/``);
* ``ADLC_HOME`` set, empty or not absolute → :class:`AdlcHomeError`, whose message
  names ``ADLC_HOME``. Never a silent fall-through to the default (BR-2).

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


class AdlcHomeError(ValueError):
    """``ADLC_HOME`` is set but cannot be used. The message names the variable."""


def adlc_home() -> str:
    """The machine-state home, or :class:`AdlcHomeError`."""
    if ENV not in os.environ:
        return os.path.join(os.path.expanduser("~"), ".claude")  # adlc-home: default
    value = os.environ[ENV]
    if value == "":
        raise AdlcHomeError(
            "ADLC_HOME is set but empty — unset it to use ~/.claude, or set it to "  # adlc-home: default
            "an absolute path (REQ-654 BR-2)")
    if not value.startswith("/"):
        raise AdlcHomeError(
            "ADLC_HOME must be an absolute path, got %r — unset it to use "
            "~/.claude, or set an absolute path (REQ-654 BR-2)" % value)  # adlc-home: default
    return value.rstrip("/") or "/"


def adlc_home_source() -> str:
    """``env`` when ``ADLC_HOME`` decided the home, ``default`` otherwise."""
    adlc_home()
    return "env" if ENV in os.environ else "default"


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
