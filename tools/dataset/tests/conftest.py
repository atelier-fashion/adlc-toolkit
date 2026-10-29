"""Fixtures for the tools/dataset tests (REQ-671).

``isolated_git`` scrubs ``GIT_*`` and points ``HOME`` at an empty directory
(the ``tools/adlc/tests/test_lane_check.py`` precedent), so no test reads the
runner's own git config. ``sandbox`` is a throwaway repository with a ``main``
branch. Path setup and helpers live in ``dataset_helpers``.
"""
import os

import pytest

from dataset_helpers import Sandbox


@pytest.fixture
def isolated_git(tmp_path, monkeypatch):
    """Scrub GIT_* and point HOME at an empty dir for the duration of a test."""
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")
    return home


@pytest.fixture
def sandbox(tmp_path, isolated_git):
    return Sandbox(tmp_path / "repo")
