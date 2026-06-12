#!/usr/bin/env python3
"""adlc — umbrella CLI for the ADLC toolkit.

A single user-facing entry point whose subcommands are registered in a
data-driven table (``SUBCOMMANDS``) so later REQs add commands without editing
dispatch logic (REQ-519 BR-11). ``doctor`` is the first subcommand; ``renumber``
(REQ-518) and the tier render (REQ-516) are the designated next homes.

This module is **pure standard library** on purpose: ``adlc doctor`` must run on
a machine that has never opted into delegation, so it cannot depend on the delegate
delegation venv or any third-party package (REQ-519 ADR-1). Subcommand modules
are imported lazily inside their handler so an import problem in one subcommand
never breaks ``adlc --version`` or the usage listing.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _repo_root():
    """Absolute path to the toolkit checkout root.

    Prefers ``git rev-parse --show-toplevel`` from this script's directory so it
    resolves through the skills symlink regardless of cwd; falls back to walking
    up from ``__file__`` (``tools/adlc/adlc.py`` → repo root is two levels up).
    """
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
    # tools/adlc/adlc.py -> tools/adlc -> tools -> <root>
    return os.path.dirname(os.path.dirname(here))


def _version():
    """Read the toolkit VERSION file; never hardcode the version (BR-3 spirit)."""
    path = os.path.join(_repo_root(), "VERSION")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "unknown"


def _cmd_doctor(argv):
    """Lazy-import the doctor subcommand and delegate to its main()."""
    import doctor  # noqa: E402  (lazy so --version works even if doctor breaks)

    return doctor.main(argv)


def _cmd_agents(argv):
    """Lazy-import the agents render subcommand and delegate to its main()."""
    import agents_render  # noqa: E402  (lazy so --version works even if it breaks)

    return agents_render.main(argv)


def _cmd_renumber(argv):
    """Lazy-import the renumber subcommand and delegate to its main() (REQ-518)."""
    import renumber  # noqa: E402  (lazy so --version works even if renumber breaks)

    return renumber.main(argv)


# Data-driven subcommand registry. Adding a command = appending one entry;
# dispatch below never changes. Each handler takes the remaining argv (the
# args AFTER the subcommand name) and returns an int exit code.
SUBCOMMANDS = {
    "doctor": {
        "handler": _cmd_doctor,
        "help": "read-only environment health check with per-check remediation",
    },
    "agents": {
        "handler": _cmd_agents,
        "help": "render agents/*.md model: from tier classes + config (render [--check])",
    },
    "renumber": {
        "handler": _cmd_renumber,
        "help": "rename an artifact id repo-wide, collision-safe (dry-run by default)",
    },
}


def _usage(prog):
    lines = [
        f"usage: {prog} <command> [options]",
        "",
        "commands:",
    ]
    width = max((len(name) for name in SUBCOMMANDS), default=0)
    for name in SUBCOMMANDS:
        lines.append(f"  {name.ljust(width)}  {SUBCOMMANDS[name]['help']}")
    lines += [
        "",
        f"  {'--version'.ljust(width)}  print the toolkit version and exit",
    ]
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = "adlc"

    if argv and argv[0] in ("--version", "-V"):
        print(_version())
        return 0

    if not argv or argv[0] in ("-h", "--help"):
        print(_usage(prog))
        # No command is a usage error (non-zero); explicit --help is success.
        return 0 if (argv and argv[0] in ("-h", "--help")) else 2

    command = argv[0]
    rest = argv[1:]
    entry = SUBCOMMANDS.get(command)
    if entry is None:
        sys.stderr.write(
            f"{prog}: unknown command '{command}'\n\n{_usage(prog)}\n"
        )
        return 2
    return entry["handler"](rest)


if __name__ == "__main__":
    raise SystemExit(main())
