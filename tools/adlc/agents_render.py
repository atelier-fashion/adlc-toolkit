#!/usr/bin/env python3
"""agents_render — render the ``model:`` frontmatter of ``agents/*.md`` from tiers.

REQ-516. Each agent declares a stable ``tier:`` class; a config section maps
class -> model alias (with optional per-agent overrides); this module resolves
each agent's model by precedence and atomically stamps the ``model:`` line into
the file. With no config, the shipped per-agent defaults reproduce today's exact
assignments (BR-3) — zero behavior change.

Pure standard library on purpose (REQ-519 ADR-1): ``adlc agents render`` must run
on a machine that never opted into the delegation venv, so it cannot import the
delegation package or any third-party dependency. The flat config reader mirrors
``tools/delegate/_common.py:parse_delegate_config`` (REQ-515 ADR-3) rather than
pulling in PyYAML.

The render and the drift check (``check_drift``) share one resolution + parse
code path so the drift report can never diverge from what render would write
(BR-5, LESSON-006 carve-out).
"""

import argparse
import os
import re
import sys

# --- shipped defaults: agent-name -> (tier, model) --------------------------
# Captured from the committed ``agents/*.md`` at REQ-516 implementation time
# (18 agents on origin/main @ REQ-519). This per-agent map IS the zero-config
# authority (ADR-1): the ``reviewer`` class spans both opus and sonnet today, so
# a class->one-model collapse would change behavior and violate BR-3. The class
# map exists only as the adopter's override lever; with no config every agent
# resolves to its individually-shipped value below.
_SHIPPED_DEFAULTS = {
    "adversary": ("reviewer", "opus"),
    "correctness-reviewer": ("reviewer", "opus"),
    "reflector": ("reviewer", "opus"),
    "security-auditor": ("reviewer", "opus"),
    "architecture-reviewer": ("reviewer", "sonnet"),
    "quality-reviewer": ("reviewer", "sonnet"),
    "code-quality-auditor": ("reviewer", "sonnet"),
    "test-auditor": ("reviewer", "sonnet"),
    "api-cost-scanner": ("scanner", "sonnet"),
    "db-perf-scanner": ("scanner", "sonnet"),
    "latency-scanner": ("scanner", "sonnet"),
    "architecture-mapper": ("explorer", "haiku"),
    "convention-auditor": ("explorer", "haiku"),
    "delegate-pre-pass": ("explorer", "haiku"),
    "feature-tracer": ("explorer", "haiku"),
    "integration-explorer": ("explorer", "haiku"),
    "task-implementer": ("implementer", "opus"),
    "pipeline-runner": ("orchestrator", "opus"),
}

_CLASSES = ("reviewer", "scanner", "explorer", "implementer", "orchestrator")
_ALIASES = ("opus", "sonnet", "haiku", "inherit")

# Full-model-id escape hatch (BR-7): a lowercase token containing both a digit
# AND a hyphen, e.g. ``claude-opus-4-8``. Conservative on purpose; anything that
# is not an alias and not this shape fails loud. The digit requirement (enforced
# in ``_value_ok``, not the regex) is what makes a typo'd alias like
# ``claude-opus`` or ``sonet-fast`` fail loud instead of silently passing
# through as a "model id".
_FULL_ID_RE = re.compile(r"^[a-z][a-z0-9.]*(-[a-z0-9.]+)+$")
_HAS_DIGIT_RE = re.compile(r"[0-9]")

# Header comment marking model: as derived (BR-1). Kept in sync with TASK-001.
_HEADER_COMMENT = (
    "<!-- model: is rendered by `adlc agents render` from tier: + "
    "~/.claude/adlc/config.yml; do not hand-edit. -->"
)


class ConfigError(Exception):
    """Raised on an invalid config value (BR-7). Carries a fail-loud message."""


# --------------------------------------------------------------------------
# Config reading (flat, no PyYAML — mirrors _common.parse_delegate_config)
# --------------------------------------------------------------------------
def _config_path(path=None):
    if path:
        return path
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "adlc", "config.yml")


def _strip_inline(value):
    """Strip surrounding quotes and a trailing ``# comment`` from a YAML scalar."""
    value = value.strip()
    if value[:1] not in ("'", '"'):
        hashpos = value.find(" #")
        if hashpos != -1:
            value = value[:hashpos].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def parse_agents_config(path=None):
    """Parse the ``agents:`` block (``classes:`` / ``overrides:`` sub-maps).

    Minimal two-level flat reader. Returns
    ``{"classes": {...}, "overrides": {...}}`` with only the keys present; an
    absent file or ``agents:`` section yields ``{"classes": {}, "overrides": {}}``
    (the shipped-defaults configuration, BR-3). Ignores every other top-level
    section (including REQ-515's sibling ``delegate:`` block) so both coexist.
    """
    out = {"classes": {}, "overrides": {}}
    try:
        with open(_config_path(path), "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out

    in_agents = False
    agents_indent = 0
    cur_sub = None          # "classes" | "overrides" | None
    sub_indent = None       # indent of keys under the current sub-map
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if not in_agents:
            if stripped == "agents:" and indent == 0:
                in_agents = True
                agents_indent = indent
            continue
        # Inside agents:. A return to top-level indent ends the block.
        if indent <= agents_indent:
            break
        # A sub-map header: "classes:" / "overrides:" with empty value.
        key_part = stripped.split(":", 1)[0].strip()
        value_part = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
        if value_part == "" and key_part in ("classes", "overrides"):
            cur_sub = key_part
            sub_indent = None
            continue
        if cur_sub is None or ":" not in stripped:
            continue
        if sub_indent is None:
            sub_indent = indent
        if indent < sub_indent:
            # dedented out of the sub-map; could be the other sub-map header,
            # but that was handled above — here it means an unexpected key.
            cur_sub = None
            continue
        k, _, v = stripped.partition(":")
        out[cur_sub][k.strip()] = _strip_inline(v)
    return out


# --------------------------------------------------------------------------
# Validation (BR-7 — fail loud, no silent fall-through)
# --------------------------------------------------------------------------
def _value_ok(value):
    if value in _ALIASES:
        return True
    # Full-model-id escape hatch: must look like an id (hyphenated) AND carry a
    # version digit — so a bare typo'd alias (claude-opus, sonet-fast) fails loud.
    return bool(_FULL_ID_RE.match(value)) and bool(_HAS_DIGIT_RE.search(value))


def validate_config(config):
    """Raise ConfigError on the first invalid value, naming key/value/allowed set.

    Validates every value under ``classes`` and ``overrides`` BEFORE any file is
    written, so an invalid config never half-renders. Also rejects an unknown
    tier-class key under ``classes`` (a typo'd class would otherwise be silently
    ignored — also a fail-loud condition).
    """
    allowed = ", ".join(_ALIASES) + " (or a full model id like claude-opus-4-8)"
    for cls, value in config.get("classes", {}).items():
        if cls not in _CLASSES:
            raise ConfigError(
                f"agents.classes: unknown tier class '{cls}'. "
                f"Allowed classes: {', '.join(_CLASSES)}."
            )
        if not _value_ok(value):
            raise ConfigError(
                f"agents.classes.{cls}: invalid model alias '{value}'. "
                f"Allowed: {allowed}."
            )
    for agent, value in config.get("overrides", {}).items():
        if not _value_ok(value):
            raise ConfigError(
                f"agents.overrides.{agent}: invalid model alias '{value}'. "
                f"Allowed: {allowed}."
            )


# --------------------------------------------------------------------------
# Resolution (BR-2 precedence: override > class > shipped default)
# --------------------------------------------------------------------------
def resolve_model(agent, config):
    """Resolve ``agent``'s model: override > class mapping > shipped default."""
    overrides = config.get("overrides", {})
    if agent in overrides:
        return overrides[agent]
    tier, shipped = _SHIPPED_DEFAULTS[agent]
    classes = config.get("classes", {})
    if tier in classes:
        return classes[tier]
    return shipped


# --------------------------------------------------------------------------
# Frontmatter parsing + per-file rewrite (BR-4 — atomic, idempotent, surgical)
# --------------------------------------------------------------------------
def _split_frontmatter(text):
    """Return (pre, fm_lines, post_idx) where fm_lines is the frontmatter body.

    ``text`` is the whole file. ``fm_lines`` is the list of lines BETWEEN the
    opening and closing ``---`` fences (exclusive). Returns ``None`` if there is
    no well-formed frontmatter block.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (lines, 1, i)  # open at 0, close at i
    return None


def _render_text(text, model):
    """Return the file text with the frontmatter ``model:`` line set to ``model``.

    ``model == "inherit"`` removes the line entirely. Only the ``model:`` line is
    touched; every other line is byte-preserved. If no change is needed the input
    is returned unchanged (caller skips the write — idempotence).
    """
    split = _split_frontmatter(text)
    if split is None:
        return text  # no frontmatter — leave untouched (defensive)
    lines, open_idx, close_idx = split
    fm = lines[open_idx:close_idx]

    model_pos = None
    tier_pos = None
    for j, line in enumerate(fm):
        if line.startswith("model:") and model_pos is None:
            model_pos = j
        if line.startswith("tier:") and tier_pos is None:
            tier_pos = j

    if model == "inherit":
        if model_pos is not None:
            del fm[model_pos]
        # else already absent — no-op
    else:
        new_line = f"model: {model}"
        if model_pos is not None:
            fm[model_pos] = new_line
        else:
            # Re-add after tier: (deterministic position); else at the top.
            insert_at = (tier_pos + 1) if tier_pos is not None else 0
            fm.insert(insert_at, new_line)

    new_lines = lines[:open_idx] + fm + lines[close_idx:]
    return "\n".join(new_lines)


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _agents_dir(root):
    return os.path.join(root, "agents")


def _iter_agents(root):
    """Yield (agent_name, path) for every known agent file present under root."""
    adir = _agents_dir(root)
    for name in sorted(_SHIPPED_DEFAULTS):
        path = os.path.join(adir, name + ".md")
        if os.path.isfile(path):
            yield name, path


def _current_model(text):
    """The agent's on-disk model alias, or ``"inherit"`` if the line is absent."""
    split = _split_frontmatter(text)
    if split is None:
        return None
    lines, open_idx, close_idx = split
    for line in lines[open_idx:close_idx]:
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return "inherit"


def render(root, config, write=True):
    """Render every agent's ``model:`` from ``config``. Returns a report list.

    Each report entry is ``(agent, old_model, new_model, changed)``. With
    ``write=False`` no file is touched (used by ``--check`` / ``check_drift``).
    Validation runs first (BR-7) so an invalid config never half-renders.
    """
    validate_config(config)
    report = []
    for name, path in _iter_agents(root):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        old = _current_model(text)
        target = resolve_model(name, config)
        new_text = _render_text(text, target)
        changed = new_text != text
        if changed and write:
            _atomic_write(path, new_text)
        report.append((name, old, target, changed))
    return report


def check_drift(root, config=None):
    """Return the list of (agent, expected, actual) where on-disk != resolved.

    Read-only. Shares ``render``'s resolution + parse path so it can never
    diverge from what ``render`` would write (BR-5).
    """
    if config is None:
        config = parse_agents_config()
    validate_config(config)
    drift = []
    for name, path in _iter_agents(root):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        actual = _current_model(text)
        expected = resolve_model(name, config)
        if actual != expected:
            drift.append((name, expected, actual))
    return drift


# --------------------------------------------------------------------------
# CLI entry — `adlc agents render [--check] [--config PATH] [--root PATH]`
# --------------------------------------------------------------------------
def _repo_root():
    """Toolkit checkout root, resolving through the skills symlink via git."""
    here = os.path.dirname(os.path.abspath(__file__))
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", here, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.path.dirname(os.path.dirname(here))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="adlc agents", description=__doc__)
    sub = parser.add_subparsers(dest="action")
    p_render = sub.add_parser("render", help="stamp model: into agents/*.md from tiers")
    p_render.add_argument("--check", action="store_true",
                          help="report drift only; write nothing (non-zero exit on drift)")
    p_render.add_argument("--config", default=None, help="path to config.yml")
    p_render.add_argument("--root", default=None, help="toolkit checkout root")

    ns = parser.parse_args(argv)
    if ns.action != "render":
        parser.print_help()
        return 2

    root = ns.root or _repo_root()
    try:
        config = parse_agents_config(ns.config)
        if ns.check:
            drift = check_drift(root, config)
            if drift:
                sys.stderr.write("agent model drift (expected != actual):\n")
                for name, expected, actual in drift:
                    sys.stderr.write(f"  {name}: expected {expected}, found {actual}\n")
                return 1
            print("no agent model drift")
            return 0
        report = render(root, config, write=True)
    except ConfigError as exc:
        sys.stderr.write(f"adlc agents render: {exc}\n")
        return 2

    changed = [r for r in report if r[3]]
    for name, old, new, _ in changed:
        print(f"  {name}: {old} -> {new}")
    print(f"rendered {len(report)} agents, {len(changed)} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
