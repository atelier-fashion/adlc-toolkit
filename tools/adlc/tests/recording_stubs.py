"""Recording stubs for git, gh, az, curl and sh, and a copy of the toolkit for fence tests (REQ-682).

``install(bin_dir, log)`` writes one stub per command into ``bin_dir``. Each stub appends
``{"cmd": <name>, "argv": [...], "cwd": ...}`` to the JSONL file ``log`` and exits 0 having
printed nothing, so a run proves the paths it took, never a branch it did not reach. Put
``bin_dir`` first on ``PATH``. ``calls(log)`` reads the log back.

``toolkit_copy(dest)`` copies every tree the fence census reads, so a test can alter one file
of the exec set without touching the real toolkit.
"""

import json
import os
import shutil
import stat

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.realpath(os.path.join(HERE, "..", "..", ".."))
STUBBED = ("git", "gh", "az", "curl", "sh")
#: What the census reads: the exec file set, the partials its fences reach, the adapter and
#: template the ExecPolicy comes from, and tools/adlc itself (toolkit_root's identity check).
COPY_TREES = ("proceed", "wrapup", "validate", "architect", "manifest", "review", "spec",
              "agents", "partials", "harness", "templates", "tools/adlc", "tools/delegate")
COPY_FILES = ("sprint/SKILL.md", "ETHOS.md")

_STUB = """#!/bin/sh
# recording stub (REQ-682 tests): logs its argv and succeeds, printing nothing.
exec python3 -I -c 'import json, os, sys
with open(sys.argv[1], "a") as fh:
    fh.write(json.dumps({"cmd": sys.argv[2], "argv": sys.argv[3:], "cwd": os.getcwd()}) + "\\n")
' %(log)s %(name)s "$@"
"""


def install(bin_dir, log):
    """Write a recording stub for each of :data:`STUBBED` into ``bin_dir``."""
    os.makedirs(bin_dir, exist_ok=True)
    for name in STUBBED:
        path = os.path.join(bin_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_STUB % {"log": _sh_quote(log), "name": name})
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _sh_quote(text):
    return "'%s'" % text.replace("'", "'\\''")


def calls(log):
    """Every recorded call, in order."""
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def command_text(call):
    return " ".join([call["cmd"]] + list(call["argv"]))


def toolkit_copy(dest):
    """A copy of the trees the census reads, under ``dest``; returns its real path."""
    for rel in COPY_TREES:
        shutil.copytree(os.path.join(TOOLKIT, rel), os.path.join(dest, rel),
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"))
    for rel in COPY_FILES:
        os.makedirs(os.path.dirname(os.path.join(dest, rel)) or dest, exist_ok=True)
        shutil.copy(os.path.join(TOOLKIT, rel), os.path.join(dest, rel))
    return os.path.realpath(dest)
