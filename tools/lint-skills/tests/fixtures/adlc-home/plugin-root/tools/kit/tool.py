"""A tool. Its docstring may name ~/.claude/adlc/config.yml: a docstring is not code."""
import os


def fires():
    return os.path.join(os.path.expanduser("~"), ".claude", "counter")  # FIRES: py-join


def fires_string():
    return "~/.claude/adlc/config.yml"  # FIRES: tilde in a string


def benign():
    """Docstrings are exempt: $HOME/.claude here is prose."""
    # A comment naming ~/.claude is not code.
    claude = os.path.join(os.path.expanduser("~"), ".claude")  # adlc-home: claude-code
    manifest = os.path.join(os.path.expanduser("~"), ".claude-plugin", "plugin.json")
    worktrees = os.path.join("/repo", ".claude", "worktrees")
    return claude, manifest, worktrees
