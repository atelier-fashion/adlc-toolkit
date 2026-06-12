"""Tests for agents_render (REQ-516) — engine + CLI dispatch.

Offline, tmp_path-driven. Each REQ-516 acceptance criterion maps to a test.
Mirrors the style of test_checks.py / test_dispatch.py.
"""
import os
import shutil

import pytest

import adlc
import agents_render


# --- helpers ----------------------------------------------------------------
def _agent(tier, model):
    """A minimal but realistic agent file body with frontmatter + the comment."""
    lines = ["---", "name: x", "description: d"]
    if model is not None:
        lines.append(f"model: {model}")
    lines.append(f"tier: {tier}")
    lines.append("tools: Read")
    lines.append("---")
    lines.append("<!-- model: is rendered by `adlc agents render` ... do not hand-edit. -->")
    lines.append("")
    lines.append("Body text that must never be reflowed.")
    lines.append("")
    return "\n".join(lines)


def _fake_root(tmp_path, agents):
    """Build a tmp root with agents/<name>.md for each (name)->(tier,model)."""
    adir = tmp_path / "agents"
    adir.mkdir()
    for name, (tier, model) in agents.items():
        (adir / f"{name}.md").write_text(_agent(tier, model), encoding="utf-8")
    return str(tmp_path)


def _cfg(tmp_path, body):
    p = tmp_path / "config.yml"
    p.write_text(body, encoding="utf-8")
    return str(p)


# Use a couple of real agent names so resolve_model finds them in _SHIPPED_DEFAULTS.
_REAL = {
    "api-cost-scanner": ("scanner", "sonnet"),
    "db-perf-scanner": ("scanner", "sonnet"),
    "latency-scanner": ("scanner", "sonnet"),
    "correctness-reviewer": ("reviewer", "opus"),
    "reflector": ("reviewer", "opus"),
}


# --- AC-2: no-config render is a no-op on the real checkout -----------------
def test_no_config_render_is_noop_on_real_agents(repo_root, tmp_path):
    """Fresh checkout, no config → resolved == committed for every agent; no write."""
    # Copy the real agents/ into tmp so we can render without dirtying the repo.
    src = os.path.join(repo_root, "agents")
    dst = tmp_path / "agents"
    shutil.copytree(src, dst)
    before = {p.name: p.read_bytes() for p in dst.iterdir()}
    report = agents_render.render(str(tmp_path), {"classes": {}, "overrides": {}}, write=True)
    after = {p.name: p.read_bytes() for p in dst.iterdir()}
    assert before == after, "no-config render must be byte-for-byte identical (BR-3)"
    assert all(not changed for *_x, changed in report)
    # And the resolved value equals the on-disk value for all 18.
    drift = agents_render.check_drift(str(tmp_path), {"classes": {}, "overrides": {}})
    assert drift == []


# --- AC-1: a class change touches only that class --------------------------
def test_scanner_haiku_touches_only_scanner(tmp_path):
    root = _fake_root(tmp_path, _REAL)
    before = {name: (tmp_path / "agents" / f"{name}.md").read_bytes() for name in _REAL}
    cfg = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    scanner: haiku\n"))
    report = agents_render.render(root, cfg, write=True)
    changed = {name for name, _o, _n, c in report if c}
    assert changed == {"api-cost-scanner", "db-perf-scanner", "latency-scanner"}
    # Non-scanner files must be byte-identical.
    for name in ("correctness-reviewer", "reflector"):
        after = (tmp_path / "agents" / f"{name}.md").read_bytes()
        assert after == before[name]


# --- AC-4: idempotence -----------------------------------------------------
def test_render_is_idempotent(tmp_path):
    root = _fake_root(tmp_path, _REAL)
    cfg = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    scanner: haiku\n"))
    agents_render.render(root, cfg, write=True)
    report2 = agents_render.render(root, cfg, write=True)
    assert all(not c for *_x, c in report2), "second run must change nothing"


# --- AC-3: inherit removes the line; alias restores it ---------------------
def test_inherit_removes_model_then_restore(tmp_path):
    root = _fake_root(tmp_path, _REAL)
    path = tmp_path / "agents" / "api-cost-scanner.md"
    cfg_inh = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    scanner: inherit\n"))
    agents_render.render(root, cfg_inh, write=True)
    assert "model:" not in path.read_text(encoding="utf-8").split("---")[1]
    cfg_back = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    scanner: sonnet\n"))
    agents_render.render(root, cfg_back, write=True)
    fm = path.read_text(encoding="utf-8").split("---")[1]
    assert "model: sonnet" in fm


# --- BR-2: override beats class --------------------------------------------
def test_override_beats_class(tmp_path):
    cfg = agents_render.parse_agents_config(_cfg(
        tmp_path,
        "agents:\n  classes:\n    reviewer: sonnet\n  overrides:\n"
        "    correctness-reviewer: opus\n    reflector: inherit\n"))
    assert agents_render.resolve_model("correctness-reviewer", cfg) == "opus"
    assert agents_render.resolve_model("reflector", cfg) == "inherit"
    assert agents_render.resolve_model("api-cost-scanner", cfg) == "sonnet"  # shipped default


# --- AC-6: invalid alias fails loud ----------------------------------------
def test_invalid_alias_fails_loud(tmp_path):
    cfg = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    scanner: gpt5\n"))
    with pytest.raises(agents_render.ConfigError) as exc:
        agents_render.validate_config(cfg)
    msg = str(exc.value)
    assert "scanner" in msg and "gpt5" in msg
    assert "opus" in msg and "sonnet" in msg and "haiku" in msg  # allowed set named


def test_unknown_tier_class_fails_loud(tmp_path):
    cfg = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  classes:\n    janitor: opus\n"))
    with pytest.raises(agents_render.ConfigError) as exc:
        agents_render.validate_config(cfg)
    assert "janitor" in str(exc.value)


def test_full_model_id_escape_hatch_accepted(tmp_path):
    cfg = agents_render.parse_agents_config(
        _cfg(tmp_path, "agents:\n  overrides:\n    reflector: claude-opus-4-8\n"))
    agents_render.validate_config(cfg)  # must not raise
    assert agents_render.resolve_model("reflector", cfg) == "claude-opus-4-8"


def test_escape_hatch_requires_a_digit_else_fails_loud(tmp_path):
    # A hyphenated-but-digitless token (a plausible typo of a real id) must
    # fail loud, NOT pass through as a "model id" (BR-7, no silent fall-through).
    for bad in ("claude-opus", "sonet-fast", "foo-bar"):
        cfg = agents_render.parse_agents_config(
            _cfg(tmp_path, f"agents:\n  overrides:\n    reflector: {bad}\n"))
        with pytest.raises(agents_render.ConfigError):
            agents_render.validate_config(cfg)


# --- AC-5: drift detection -------------------------------------------------
def test_check_drift_flags_handedit(tmp_path):
    root = _fake_root(tmp_path, _REAL)
    path = tmp_path / "agents" / "reflector.md"
    # Hand-edit reflector opus -> sonnet (diverges from shipped default).
    txt = path.read_text(encoding="utf-8").replace("model: opus", "model: sonnet")
    path.write_text(txt, encoding="utf-8")
    drift = agents_render.check_drift(root, {"classes": {}, "overrides": {}})
    names = {d[0] for d in drift}
    assert "reflector" in names
    # Re-render clears it.
    agents_render.render(root, {"classes": {}, "overrides": {}}, write=True)
    assert agents_render.check_drift(root, {"classes": {}, "overrides": {}}) == []


# --- config parsing edge cases (coexist with delegate:) --------------------
def test_config_coexists_with_delegate_block(tmp_path):
    cfg = agents_render.parse_agents_config(_cfg(
        tmp_path,
        "delegate:\n  enabled: true\n  model: kimi-k2.5\n"
        "agents:\n  classes:\n    scanner: haiku\n"))
    assert cfg["classes"] == {"scanner": "haiku"}
    assert cfg["overrides"] == {}


def test_absent_config_yields_empty_maps(tmp_path):
    cfg = agents_render.parse_agents_config(str(tmp_path / "does-not-exist.yml"))
    assert cfg == {"classes": {}, "overrides": {}}


# --- CLI dispatch (mirrors test_dispatch) ----------------------------------
def test_agents_subcommand_registered():
    assert "agents" in adlc.SUBCOMMANDS
    assert callable(adlc.SUBCOMMANDS["agents"]["handler"])
    assert adlc.SUBCOMMANDS["agents"]["help"]


def test_adlc_agents_render_check_dispatches(repo_root):
    # No config on PATH -> no drift on a pristine checkout -> exit 0.
    rc = adlc.main(["agents", "render", "--check", "--root", repo_root,
                    "--config", str(repo_root) + "/__no_such_config__.yml"])
    assert rc == 0


def test_agents_render_check_nonzero_on_drift(tmp_path, monkeypatch):
    root = _fake_root(tmp_path, _REAL)
    path = tmp_path / "agents" / "reflector.md"
    path.write_text(path.read_text(encoding="utf-8").replace("model: opus", "model: haiku"),
                    encoding="utf-8")
    rc = agents_render.main(["render", "--check", "--root", root,
                             "--config", str(tmp_path / "none.yml")])
    assert rc == 1


def test_agents_render_invalid_config_returns_2(tmp_path):
    cfgpath = _cfg(tmp_path, "agents:\n  classes:\n    scanner: gpt5\n")
    root = _fake_root(tmp_path, _REAL)
    rc = agents_render.main(["render", "--root", root, "--config", cfgpath])
    assert rc == 2
