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
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return os.path.join(root, "partials")
