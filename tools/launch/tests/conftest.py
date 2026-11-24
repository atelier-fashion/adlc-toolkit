"""Fixtures for the tools/launch tests (REQ-672 ADR-1), mirroring tools/adlc/tests/conftest.py.

Puts ``tools/launch`` on ``sys.path`` so ``import quickstart_steps`` resolves from any
working directory. Helpers a test file needs live in that file, or in a module of their
own: the ``tools/*/tests`` directories carry no ``__init__.py``, so ``from conftest
import`` would bind whichever conftest pytest loaded first.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _sandbox_home(monkeypatch, tmp_path_factory):
    """Point ``HOME`` at a throwaway directory, and ``ADLC_HOME`` under it, for every test.

    Nothing these tests run may read or write the runner's own home: the scripts they
    start reach ``~`` through git and through ``gh``. A test that needs a particular home
    sets ``HOME`` itself, and that wins.
    """
    home = tmp_path_factory.mktemp("sandbox-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ADLC_HOME", os.path.join(str(home), ".claude"))


@pytest.fixture(autouse=True)
def _no_inherited_toolkit_env(monkeypatch):
    """Keep the runner's own install, forge and git settings out of every test.

    Each of these, inherited from the shell running pytest, would point a sandboxed case
    at the real machine or the real forge. Their values are never read: they are removed.
    """
    for name in ("CLAUDE_CONFIG_DIR", "ADLC_TOOLKIT_ROOT", "ADLC_CONFIG", "ADLC_REPOS_ROOT",
                 "XDG_STATE_HOME", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GH_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name, raising=False)
