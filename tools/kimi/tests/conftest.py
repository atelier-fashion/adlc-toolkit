import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def partials_dir():
    """Absolute path to the repo's `partials/` directory.

    Resolves via `git rev-parse --show-toplevel` so tests work from any cwd.
    """
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        # REQ-426 verify M1: opaque CalledProcessError makes the failure
        # mode unclear in CI when git is missing or the test runs outside a
        # git repo. Skip cleanly with an actionable message instead.
        pytest.skip(f"git rev-parse failed — partials tests need a git repo: {e}")
    return os.path.join(root, "partials")
