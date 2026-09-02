"""Keep PyYAML importable in a child interpreter whose ``HOME`` is redirected.

Several suites here spawn the CLIs as real subprocesses with an environment
built from scratch and ``HOME`` pointed at a tmp dir, so that a developer's own
``~/.claude/adlc/config.yml`` and key vars cannot leak into a result. Since
REQ-609 the config is parsed by PyYAML (BR-1), and on an interpreter whose
PyYAML lives in the **user** site-packages — ``python3`` on macOS, where
``pip install --user`` is the only option without root — redirecting ``HOME``
also removes PyYAML from the child's import path. The config the test just
wrote then reads back as ``dependency-missing`` and the CLI fails closed
(REQ-609 BR-9).

That is the right product behaviour and the wrong test premise: those tests are
about precedence and reporting, not about whether the parser is installed. The
BR-9 behaviour has its own tests, which poison the import deliberately rather
than relying on where a machine happens to keep its packages.

So: hand the child a directory containing a symlink to the PyYAML package the
PARENT can import, and nothing else. A symlink to the package rather than the
site-packages directory itself, because that directory also holds ``openai`` —
and the BR-4 tests that prove ``--version`` runs with no SDK installed probe for
an un-importable ``openai`` and *skip* when they find one, so widening the path
would silently retire them instead of failing loudly.

Where the parent cannot import PyYAML either (a bare venv), nothing is added
and the child sees exactly what it saw before.
"""

import atexit
import os
import shutil
import tempfile

_dir = None


def _build():
    try:
        import yaml
    except ImportError:
        return None
    pkg = os.path.dirname(os.path.abspath(yaml.__file__))
    if not os.path.isdir(pkg):
        return None
    tmp = tempfile.mkdtemp(prefix="adlc-yaml-path-")
    atexit.register(shutil.rmtree, tmp, True)
    try:
        os.symlink(pkg, os.path.join(tmp, os.path.basename(pkg)))
    except OSError:
        shutil.rmtree(tmp, True)
        return None
    return tmp


def yaml_path_dir():
    """The directory to put on a child's ``PYTHONPATH``, or ``None``."""
    global _dir
    if _dir is None:
        _dir = _build() or ""
    return _dir or None


def with_yaml(env):
    """Return ``env`` with :func:`yaml_path_dir` prepended to ``PYTHONPATH``.

    Mutates nothing the caller owns; returns the same mapping when there is
    nothing to add.
    """
    extra = yaml_path_dir()
    if not extra:
        return env
    out = dict(env)
    existing = out.get("PYTHONPATH")
    out["PYTHONPATH"] = extra + os.pathsep + existing if existing else extra
    return out
