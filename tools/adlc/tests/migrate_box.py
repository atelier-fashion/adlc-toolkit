"""A sandboxed machine for the migration tests (REQ-663 ADR-8).

Everything a migration touches is built here, and nothing else is reachable:

* ``HOME``, ``ADLC_REPOS_ROOT`` and ``TMPDIR`` are sandbox paths, passed explicitly to
  every child, because a child does not read pytest's monkeypatched environment.
* A stub ``launchctl`` is first on ``PATH``. This is not a convenience:
  ``launchctl bootout gui/<uid> <plist>`` finds its agent by the label inside the plist,
  so a sandbox plist reaching the real binary would unload the real agent.
  :meth:`Box.env` asserts the stub is what ``PATH`` resolves.
* ``requirements.txt`` in the sandbox clone names a hand-built local wheel, so
  ``python3 -m venv`` and ``pip install`` run for real, with ``PIP_NO_INDEX`` set and
  no network.

:func:`tree_state` is the checksum the "changed nothing" assertions compare.
"""

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_install_home as inst  # noqa: E402  (the sandbox clone builder)

COUNTERS = (".global-next-req", ".global-next-bug", ".global-next-lesson")
CONFIG_TEXT = "delegate:\n  enabled: true\n"
LEDGER_TEXT = "req 7 aaaa\nbug 3 bbbb\n"
PLIST_NAME = "com.adlc-toolkit.delegate-setenv.plist"


def build_wheel(directory):
    """``PyYAML-6.0.3-py3-none-any.whl`` holding only ``yaml/__init__.py``.

    ``yaml`` under ``site-packages`` is all the interpreter rule asks for. No network,
    no build backend: a wheel is a zip.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "PyYAML-6.0.3-py3-none-any.whl")
    info = "PyYAML-6.0.3.dist-info"
    with zipfile.ZipFile(path, "w") as whl:
        whl.writestr("yaml/__init__.py", '__version__ = "6.0.3"\n')
        whl.writestr(info + "/METADATA", "Metadata-Version: 2.1\nName: PyYAML\nVersion: 6.0.3\n")
        whl.writestr(info + "/WHEEL", "Wheel-Version: 1.0\nGenerator: test\n"
                                      "Root-Is-Purelib: true\nTag: py3-none-any\n")
        whl.writestr(info + "/RECORD", "")
    return path


def tree_state(*roots):
    """{path: what is there}, for a before-and-after compare. Follows no symlink."""
    state = {}
    for root in roots:
        if not os.path.lexists(root):
            state[root] = None
            continue
        if not os.path.isdir(root) or os.path.islink(root):
            state[root] = _entry(root)
            continue
        for base, dirs, files in os.walk(root, followlinks=False):
            for name in sorted(dirs + files):
                path = os.path.join(base, name)
                state[path] = _entry(path)
    return state


def _entry(path):
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return ("link", os.readlink(path))
    if stat.S_ISDIR(st.st_mode):
        return ("dir",)
    with open(path, "rb") as fh:
        return ("file", hashlib.sha256(fh.read()).hexdigest(), stat.S_IMODE(st.st_mode))


def run_sh(script):
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True)


class Box:
    def __init__(self, tmp):
        self.tmp = str(tmp)
        self.clone = inst.make_clone(os.path.join(self.tmp, "clone dir"))
        self.home = inst.make_home(os.path.join(self.tmp, "home"))
        self.claude = os.path.join(self.home, ".claude")
        self.dest = os.path.join(self.home, "adlc-home")
        self.repos = os.path.join(self.tmp, "repos")
        os.makedirs(self.repos)
        self.stub = os.path.join(self.tmp, "stub-bin")
        os.makedirs(self.stub)
        self.launchctl_log = os.path.join(self.tmp, "launchctl.log")
        self._stub_launchctl()
        for name in ("harness",):
            source = os.path.join(inst.TOOLKIT, name)
            if os.path.isdir(source):
                shutil.copytree(source, os.path.join(self.clone, name),
                                ignore=shutil.ignore_patterns("rendered"))
        shutil.copytree(os.path.join(inst.TOOLKIT, "templates"),
                        os.path.join(self.clone, "templates"))
        self.wheel = build_wheel(os.path.join(self.tmp, "wheels"))
        with open(os.path.join(self.clone, "tools", "delegate", "requirements.txt"), "w") as fh:
            fh.write(self.wheel + "\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "sandbox")

    def git(self, *args, cwd=None):
        base = ["git", "-C", cwd or self.clone, "-c", "user.email=t@t", "-c", "user.name=t"]
        return subprocess.run(base + list(args), check=True, capture_output=True, text=True,
                              env={"PATH": inst.SYSTEM_PATH, "HOME": self.home})

    def _stub_launchctl(self):
        path = os.path.join(self.stub, "launchctl")
        with open(path, "w") as fh:
            fh.write('#!/bin/sh\necho "$*" >> "%s"\nexit 0\n' % self.launchctl_log)
        os.chmod(path, 0o755)

    def env(self, **extra):
        env = {"HOME": self.home, "PATH": "%s:%s" % (self.stub, inst.SYSTEM_PATH),
               "USER": os.environ.get("USER", "u"), "ADLC_REPOS_ROOT": self.repos,
               "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
        env.update(extra)
        env = {k: v for k, v in env.items() if v is not None}
        found = shutil.which("launchctl", path=env["PATH"])
        assert found == os.path.join(self.stub, "launchctl"), "launchctl must be the stub"
        return env

    def install(self, *args, env=None, **extra):
        return subprocess.run(["bash", os.path.join(self.clone, "install.sh")] + list(args),
                              cwd=self.home, env=env or self.env(**extra),
                              capture_output=True, text=True, timeout=300)

    def delegate_install(self, *args, **extra):
        return subprocess.run(["sh", os.path.join(self.clone, "tools", "delegate", "install.sh")]
                              + list(args), cwd=self.home, env=self.env(**extra),
                              capture_output=True, text=True, timeout=300)

    def migrate(self, *args, **extra):
        return self.install("--migrate-home", self.dest, *args, **extra)

    def back(self, *args, **extra):
        return self.install("--migrate-home", "--back", *args, **extra)

    def doctor(self, *args, **extra):
        return subprocess.run([sys.executable, os.path.join(self.clone, "tools", "adlc", "adlc.py"),
                               "doctor"] + list(args), cwd=self.home, env=self.env(**extra),
                              capture_output=True, text=True, timeout=120)

    def seed(self):
        """A healthy default install: what ./install.sh leaves, with state in it."""
        out = self.install()
        assert out.returncode == 0, out.stdout + out.stderr
        for index, name in enumerate(COUNTERS):
            self.write(self.path(name), "%d\n" % (100 + index))
        self.write(self.path(".adlc-own-reservations"), LEDGER_TEXT)
        self.write(self.path("adlc", "config.yml"), CONFIG_TEXT)
        self.write(self.path("CLAUDE.md"), "# mine\n")
        self.write(self.path("settings.json"), "{}\n")
        return self

    def seed_delegation(self):
        """Then the delegation install, for real: venv, wrappers, helper, plist."""
        self.seed()
        out = self.delegate_install()
        assert out.returncode == 0, out.stdout + out.stderr
        return self

    def path(self, *parts):
        return os.path.join(self.claude, *parts)

    def moved(self, *parts):
        return os.path.join(self.dest, *parts)

    def hook(self, body):
        path = os.path.join(self.tmp, "hook.sh")
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return path

    @staticmethod
    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    @staticmethod
    def read(path):
        with open(path) as fh:
            return fh.read()

    def machine(self):
        """Every root a refusal promises not to touch."""
        return tree_state(self.claude, os.path.join(self.home, "bin"),
                          os.path.join(self.home, "Library", "LaunchAgents"),
                          os.path.join(self.home, ".agents"),
                          os.path.join(self.home, ".zshrc"),
                          os.path.join(self.home, ".bash_profile"),
                          os.path.join(self.home, ".profile"))

    def rc(self):
        """The rc file install.sh picks: the one whose marker block the migration edits."""
        for name in (".zshrc", ".bash_profile", ".profile"):
            path = os.path.join(self.home, name)
            if "ADLC_HOME" in self.read(path):
                return path
        return None

    def out(self, result):
        return result.stdout + result.stderr
