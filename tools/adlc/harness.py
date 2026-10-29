#!/usr/bin/env python3
"""adlc harness detect — which agent harnesses are installed, and mounted (REQ-654 BR-7).

Read-only and pure standard library (LESSON-395): `/init --harness` and the exec
engine will call it to choose defaults before the machine is set up, so it may
depend on nothing it reports on.

For each of the five harnesses the multi-harness plan surveyed it reports:

* **binary** — the first of the harness's executable names found on ``PATH``,
  ``present`` or ``absent``. Cursor's CLI installs as ``agent``, with a possible
  ``cursor-agent`` alias, and either counts.
* **version** — the first line ``<binary> --version`` prints, under a short
  timeout. A non-zero exit, a timeout, an OS error or empty output is
  ``unknown``: never an error, and never a guess (LESSON-581).
* **mount** — ``n/a`` when the binary is absent. Otherwise ``mounted`` when the
  harness's user-level skills directory reaches this toolkit, else
  ``not-mounted``. Claude Code reads its own skills mount, which install.sh keeps
  whatever ``ADLC_HOME`` says (REQ-654 BR-6), or loads the adlc plugin; the
  doctor's symlink-install test decides which. The other four read
  ``$HOME/.agents/skills`` (architecture ADR-7).

Absence of every harness is a result, so the command exits 0 whenever it ran.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: (name, executable names tried in order, where its user-level skills live).
#: ``claude`` is the only harness with its own mount; the rest share one.
HARNESSES: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("claude", ("claude",), "claude"),
    ("copilot", ("copilot",), "agents"),
    ("codex", ("codex",), "agents"),
    ("gemini", ("gemini",), "agents"),
    ("cursor", ("agent", "cursor-agent"), "agents"),
)
NAMES = tuple(h[0] for h in HARNESSES)

#: Seconds a ``--version`` probe may take before it is ``unknown``. Kept short:
#: doctor runs five of these, and a binary that blocks (a login prompt, a
#: network check) must cost the report seconds, not a hang.
PROBE_TIMEOUT_SECONDS = 3.0

#: The longest version string reported; the rest is cut, not wrapped.
_VERSION_MAX = 120
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class HarnessProbe:
    """One harness, as BR-7 names the fields."""

    name: str
    binary: str            # the executable name looked up (the first, when absent)
    state: str             # present | absent
    path: Optional[str]    # where the binary is, when present
    version: str           # the version line, or "unknown"; "n/a" when absent
    mount: str             # mounted | not-mounted | n/a


def _toolkit_root() -> Optional[str]:
    import toolkit_root
    try:
        return toolkit_root.toolkit_root()
    except toolkit_root.ToolkitRootError:
        return None


def _version(exe: str) -> str:
    """The first output line of ``exe --version``, or ``unknown``.

    The child gets its own session, so a timeout kills everything it started
    (a wrapper script's ``sleep`` included), and stdin is closed, so a binary
    that asks a question gets end-of-file instead of waiting for an answer.
    """
    try:
        proc = subprocess.Popen([exe, "--version"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except OSError:
        return "unknown"
    try:
        out, _err = proc.communicate(timeout=PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        try:
            proc.communicate(timeout=PROBE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    for raw in out.decode("utf-8", "replace").splitlines():
        line = _CONTROL.sub("", raw).strip()
        if line:
            return line[:_VERSION_MAX]
    return "unknown"


def _claude_mounted() -> bool:
    """Claude Code reaches a toolkit: its skills mount, or the adlc plugin.

    The mount test is the doctor's own (``checks._symlink_install``: a link to a
    tree with ``partials/`` and the sample skill), so detect and doctor cannot
    disagree about what "mounted" means, and only the doctor's symlink checks
    spell Claude Code's skills path (REQ-669 AC-4).
    """
    try:
        import checks
        if checks._symlink_install() is not None:
            return True
        import doctor
        return doctor.detect_plugin_install().state == "present"
    except Exception:  # a probe must never stop the report
        return False


def _agents_mounted(root: Optional[str]) -> bool:
    """At least one toolkit skill resolves into this toolkit through ``~/.agents/skills``."""
    try:
        import checks
        mount = checks._agents_mount()
        sym = checks._symlink_install()
    except Exception:  # a probe must never stop the report
        return False
    # The tree this runs from, and the clone Claude Code's mount points at:
    # install.sh builds the view from the latter, so a run from a worktree of
    # that clone must still see the view as reaching the toolkit.
    roots = {os.path.realpath(r) for r in (root, sym[1] if sym else None) if r}
    if not roots or not os.path.isdir(mount):
        return False
    try:
        names = os.listdir(mount)
    except OSError:
        return False
    for name in names:
        entry = os.path.join(mount, name, "SKILL.md")
        if not os.path.isfile(entry):
            continue
        real = os.path.realpath(entry)
        if any(real == os.path.join(r, name, "SKILL.md") for r in roots):
            return True
    return False


def probe(name: str, root: Optional[str] = None) -> HarnessProbe:
    """Probe one harness by name. Never raises for a harness in :data:`NAMES`."""
    for hname, binaries, mount_kind in HARNESSES:
        if hname != name:
            continue
        for binary in binaries:
            path = shutil.which(binary)
            if path:
                if mount_kind == "claude":
                    mounted = _claude_mounted()
                else:
                    mounted = _agents_mounted(root)
                return HarnessProbe(name, binary, "present", path, _version(path),
                                    "mounted" if mounted else "not-mounted")
        return HarnessProbe(name, binaries[0], "absent", None, "n/a", "n/a")
    raise ValueError("unknown harness %r (known: %s)" % (name, ", ".join(NAMES)))


def probe_all() -> List[HarnessProbe]:
    root = _toolkit_root()
    return [probe(name, root) for name in NAMES]


def format_table(probes: List[HarnessProbe]) -> str:
    rows = [("harness", "binary", "state", "version", "mount")]
    rows += [(p.name, p.binary, p.state, p.version, p.mount) for p in probes]
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    lines = []
    for r in rows:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(4)) + "  " + r[4])
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="adlc harness",
        description="Read-only: which agent harnesses are installed, and whether "
                    "each one's skills directory reaches this toolkit.")
    sub = parser.add_subparsers(dest="verb")
    detect = sub.add_parser("detect", help="probe the five known harnesses")
    detect.add_argument("--json", action="store_true",
                        help="one JSON object per harness, as an array")
    args = parser.parse_args(argv)
    if args.verb != "detect":
        parser.print_usage(sys.stderr)
        return 2
    probes = probe_all()
    if args.json:
        print(json.dumps([asdict(p) for p in probes], indent=2))
    else:
        print(format_table(probes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
