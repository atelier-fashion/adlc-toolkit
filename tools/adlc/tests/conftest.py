"""Test fixtures for tools/adlc — mirrors tools/kimi/tests/conftest.py.

Inserts the parent dir (tools/adlc) onto sys.path so `import adlc`,
`import doctor`, `import checks` resolve regardless of cwd.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def repo_root():
    """Absolute path to the toolkit checkout root via git, SKIP if unavailable."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"git rev-parse failed — adlc tests need a git repo: {e}")
    return root
