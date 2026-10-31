"""Sandbox for the `adlc harness probe` end-to-end tests (REQ-664 BR-14).

Every case runs the real CLI as a subprocess with its own HOME, PATH, TMPDIR and
caller repository, and with the fake harness installed under the binary names
the profiles look up. Nothing a case does can reach the machine running it.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ADLC = os.path.join(os.path.dirname(TESTS), "adlc.py")
FAKE_DIR = os.path.join(TESTS, "fake_harness")
WRAPPER = os.path.join(FAKE_DIR, "fake-harness")
IMPL = os.path.join(FAKE_DIR, "fake_harness_impl.py")
BINARY = {"claude": "claude", "copilot": "copilot", "codex": "codex", "gemini": "gemini",
          "cursor": "agent", "antigravity": "agy"}
HARNESSES = tuple(BINARY)
SYSTEM_PATH = "/usr/bin:/bin"


class Sandbox:
    def __init__(self, tmp_path, harnesses=HARNESSES, scenario="perform", flags=(),
                 version=None):
        self.root = str(tmp_path)
        self.home = os.path.join(self.root, "home")
        self.bin = os.path.join(self.root, "bin")
        self.tmp = os.path.join(self.root, "tmp")
        self.repo = os.path.join(self.root, "repo")
        self.log = os.path.join(self.root, "fake.log")
        self.pidfile = os.path.join(self.root, "fake.pids")
        for d in (self.home, self.bin, self.tmp, self.repo):
            os.makedirs(d, exist_ok=True)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        for h in harnesses:
            self.install(h)
        self.scenario = scenario
        self.flags = list(flags)
        self.version = version

    def install(self, harness):
        dest = os.path.join(self.bin, BINARY[harness])
        shutil.copy2(WRAPPER, dest)
        os.chmod(dest, 0o755)
        # An installed codex or gemini has its home directory; the probe's
        # created_dirs then hold only what the probe itself made (BR-4).
        if harness in ("codex", "gemini"):
            os.makedirs(os.path.join(self.home, "." + harness), exist_ok=True)

    def uninstall(self, harness):
        path = os.path.join(self.bin, BINARY[harness])
        if os.path.exists(path):
            os.remove(path)

    @property
    def adlc_home(self):
        return os.path.join(self.home, ".claude")

    def env(self, **extra):
        env = {"HOME": self.home, "PATH": self.bin + ":" + SYSTEM_PATH, "TMPDIR": self.tmp,
               "FAKE_HARNESS_IMPL": IMPL, "FAKE_HARNESS_PYTHON": sys.executable,
               "FAKE_HARNESS_SCENARIO": self.scenario,
               "FAKE_HARNESS_FLAGS": ",".join(self.flags),
               "FAKE_HARNESS_LOG": self.log, "FAKE_HARNESS_PIDFILE": self.pidfile,
               "SHELL": "/bin/sh", "PYTHONDONTWRITEBYTECODE": "1"}
        if self.version:
            env["FAKE_HARNESS_VERSION"] = self.version
        for key in ("LANG", "LC_ALL"):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update({k: v for k, v in extra.items() if v is not None})
        return env

    def run(self, *args, cwd=None, timeout=900, **extra):
        return subprocess.run([sys.executable, ADLC, "harness", "probe"] + list(args),
                              cwd=cwd or self.repo, env=self.env(**extra),
                              capture_output=True, text=True, timeout=timeout)

    def popen(self, *args, cwd=None, **extra):
        return subprocess.Popen([sys.executable, ADLC, "harness", "probe"] + list(args),
                                cwd=cwd or self.repo, env=self.env(**extra),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def result_path(self, harness):
        return os.path.join(self.repo, ".adlc", "research", "harness-probes",
                            "%s.json" % harness)

    def result(self, harness):
        with open(self.result_path(harness), encoding="utf-8") as fh:
            return json.load(fh)

    def log_records(self, event=None):
        if not os.path.exists(self.log):
            return []
        out = [json.loads(line) for line in open(self.log, encoding="utf-8")]
        return [r for r in out if event is None or r.get("event") == event]

    def marker(self, harness):
        return os.path.join(self.adlc_home, "adlc", "harness-probe", "%s.marker.json" % harness)


def listing(path, skip=()):
    """Every file and directory under ``path`` with each file's sha256."""
    out = {}
    if not os.path.isdir(path):
        return out
    for dirpath, dirs, files in os.walk(path):
        rel = os.path.relpath(dirpath, path)
        if any(rel == s or rel.startswith(s + os.sep) for s in skip):
            dirs[:] = []
            continue
        for d in dirs:
            out[os.path.normpath(os.path.join(rel, d)) + "/"] = None
        for f in files:
            full = os.path.join(dirpath, f)
            try:
                with open(full, "rb") as fh:
                    out[os.path.normpath(os.path.join(rel, f))] = hashlib.sha256(
                        fh.read()).hexdigest()
            except OSError:
                out[os.path.normpath(os.path.join(rel, f))] = "unreadable"
    return out


def statuses(result):
    return {pid: (entry["status"], entry.get("reason")) for pid, entry in
            result["probes"].items()}
