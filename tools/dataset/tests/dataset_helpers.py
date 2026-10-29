"""Shared helpers for the tools/dataset tests (REQ-671).

A module of its own, not ``conftest``: the ``tools/*/tests`` directories carry
no ``__init__.py``, so ``from conftest import`` would bind whichever conftest
pytest loaded first.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.dirname(HERE)
TOOLKIT = os.path.dirname(os.path.dirname(DATASET_DIR))
sys.path.insert(0, DATASET_DIR)
sys.path.insert(0, os.path.join(TOOLKIT, "tools", "adlc"))


def toolkit_is_git_checkout():
    """True when the toolkit under test is a git checkout (not a plugin cache copy)."""
    proc = subprocess.run(["git", "-C", TOOLKIT, "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    return proc.returncode == 0 and os.path.realpath(proc.stdout.strip()) == \
        os.path.realpath(TOOLKIT)


needs_toolkit_git = pytest.mark.skipif(
    not toolkit_is_git_checkout(),
    reason="the toolkit is not a git checkout here (plugin cache copy); the "
           "current-tree cases read git objects at HEAD")


class Sandbox(object):
    """A throwaway git repository with a ``main`` branch."""

    def __init__(self, root):
        self.root = str(root)
        os.makedirs(self.root)
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args):
        proc = subprocess.run(["git", "-C", self.root] + list(args),
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(path, mode) as fh:
            fh.write(content)
        return path

    def commit(self, message="commit"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")
