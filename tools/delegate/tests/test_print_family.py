"""REQ-722 TASK-278 — `adlc-read --print-family`.

The probe is how a shell learns the reviewer family (ADR-2): the config file is
parsed by the Python that owns it, never by a shell read. It prints one
`ModelFamily` member and exits 0 on every path. It reports and never authorizes,
so neither the opt-in nor the `ADLC_DISABLE_DELEGATE` veto changes what it
prints, and it makes no network call.

Every case spawns the real CLI (LESSON-329) in an environment built from scratch
with `HOME` in `tmp_path`, so neither the developer's config nor their key vars
reach a result.
"""
import os
import subprocess
import sys

import pytest

_DELEGATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _DELEGATE)
import _child_env  # noqa: E402

_CLI = os.path.join(_DELEGATE, "adlc-read")

#: The enum, restated rather than imported, so a probe that printed whatever
#: `model_family` holds would still be checked against the REQ's list.
_FAMILIES = ("anthropic", "openai", "moonshot", "google", "meta", "other",
             "unknown")


def _env(home, **extra):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}
    env.update(extra)
    return _child_env.with_yaml(env)


def _config(tmp_path, body, name="config.yml"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def _probe(env, argv=("--print-family",)):
    return subprocess.run([sys.executable, _CLI, *argv], capture_output=True,
                          text=True, env=env, timeout=30, check=False)


@pytest.mark.parametrize("family", _FAMILIES)
def test_print_family_prints_the_declared_value(family, tmp_path):
    cfg = _config(tmp_path, "delegate:\n  enabled: true\n  family: %s\n" % family)
    r = _probe(_env(tmp_path, ADLC_CONFIG=cfg))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == family + "\n"


def test_print_family_without_key_is_unknown(tmp_path):
    """AC-5 / BR-10: no `family` written resolves to `unknown`, whether there is
    no config file at all or a config that simply leaves the key out, and the
    probe still exits 0."""
    no_file = _probe(_env(tmp_path, ADLC_CONFIG=str(tmp_path / "absent.yml")))
    assert no_file.returncode == 0, no_file.stdout + no_file.stderr
    assert no_file.stdout == "unknown\n"

    default_path = _probe(_env(tmp_path))      # <HOME>/.claude/adlc/config.yml
    assert default_path.returncode == 0, default_path.stderr
    assert default_path.stdout == "unknown\n"

    cfg = _config(tmp_path, "delegate:\n  enabled: true\n  model: m\n")
    no_key = _probe(_env(tmp_path, ADLC_CONFIG=cfg))
    assert no_key.returncode == 0, no_key.stdout + no_key.stderr
    assert no_key.stdout == "unknown\n"


@pytest.mark.parametrize("body", [
    "delegate:\n  family: gpt\n",
    "delegate:\n  family: Anthropic\n",
    "delegate:\n  family: [anthropic]\n",
    "delegate:\n  family: anthropic\n  family: openai\n",
    "delegate:\n  family: anthropic\n  enbaled: false\n",
], ids=["not-a-member", "case-variant", "sequence", "duplicate", "other-key-refused"])
def test_print_family_on_a_refused_config_is_unknown(body, tmp_path):
    """A file the strict loader refuses yields no family, even when a valid one
    is written in it: a refused file is not partly read."""
    r = _probe(_env(tmp_path, ADLC_CONFIG=_config(tmp_path, body)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "unknown\n"


def test_print_family_ignores_opt_in_and_veto(tmp_path):
    """It transmits nothing, so it needs no opt-in, and the veto does not
    change what it prints (REQ-722 AC-5's `ADLC_DISABLE_DELEGATE=1` clause)."""
    cfg = _config(tmp_path, "delegate:\n  enabled: false\n  family: anthropic\n")
    for extra in ({}, {"ADLC_DISABLE_DELEGATE": "1"},
                  {"ADLC_DELEGATE_ENABLED": "1", "ADLC_DISABLE_DELEGATE": "1"}):
        r = _probe(_env(tmp_path, ADLC_CONFIG=cfg, **extra))
        assert r.returncode == 0, (extra, r.stdout + r.stderr)
        assert r.stdout == "anthropic\n", extra


def test_print_family_needs_no_other_arguments_and_is_never_inferred(tmp_path):
    """The family is declared, never inferred from a model name (BR-2): a
    `--model` flag naming another vendor's model does not change it, and an
    `ADLC_DELEGATE_MODEL` override makes it `unknown`, never that model's family."""
    cfg = _config(tmp_path, "delegate:\n  family: moonshot\n")
    r = _probe(_env(tmp_path, ADLC_CONFIG=cfg),
               argv=("--model", "claude-opus-4", "--print-family"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "moonshot\n"
    r = _probe(_env(tmp_path, ADLC_CONFIG=cfg, ADLC_DELEGATE_MODEL="gpt-4o"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "unknown\n"


def test_print_family_makes_no_network_call(tmp_path):
    """No network without the SDK: an `openai` package that raises on import is
    first on the path, delegation is opted in and a key is set, and the probe
    still answers. The control is the same poison on a real call, which must
    reach the SDK and fail, or the poison proves nothing (LESSON-602)."""
    poison = tmp_path / "poison" / "openai"
    poison.mkdir(parents=True)
    (poison / "__init__.py").write_text(
        'raise RuntimeError("imported openai")\n', encoding="utf-8")
    cfg = _config(tmp_path, "delegate:\n  enabled: true\n  family: google\n"
                            "  base_url: http://127.0.0.1:9/v1\n")
    env = _env(tmp_path, ADLC_CONFIG=cfg, MOONSHOT_API_KEY="sk-test-not-a-key",
               PYTHONPATH=str(tmp_path / "poison"))

    r = _probe(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "google\n"
    assert "RuntimeError" not in r.stderr

    corpus = tmp_path / "corpus.txt"
    corpus.write_text("a file\n", encoding="utf-8")
    control = _probe(env, argv=("--no-warn", "--paths", str(corpus),
                                "--question", "q"))
    assert control.returncode != 0, "the poisoned SDK was never imported"
    assert "RuntimeError" in control.stderr, control.stderr


@pytest.mark.parametrize("env_key, value", [
    ("ADLC_DELEGATE_MODEL", "some-other-model"),
    ("ADLC_DELEGATE_BASE_URL", "https://elsewhere.example/v1"),
])
def test_an_env_override_the_file_does_not_hold_makes_the_family_unknown(env_key, value, tmp_path):
    """ADR-2: the declaration describes the model and endpoint the file names. An
    override that sends the call elsewhere leaves the family unestablished."""
    cfg = _config(tmp_path, "delegate:\n  enabled: true\n  model: kimi-k2.6\n"
                            "  base_url: https://api.moonshot.ai/v1\n  family: moonshot\n")
    r = _probe(_env(tmp_path, ADLC_CONFIG=cfg, **{env_key: value}))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "unknown\n"


@pytest.mark.parametrize("env_key, value", [
    ("ADLC_DELEGATE_MODEL", "kimi-k2.6"),
    ("ADLC_DELEGATE_BASE_URL", "https://api.moonshot.ai/v1"),
])
def test_an_env_override_equal_to_the_file_keeps_the_family(env_key, value, tmp_path):
    """Benign path: an override that repeats what the file holds changes nothing."""
    cfg = _config(tmp_path, "delegate:\n  enabled: true\n  model: kimi-k2.6\n"
                            "  base_url: https://api.moonshot.ai/v1\n  family: moonshot\n")
    r = _probe(_env(tmp_path, ADLC_CONFIG=cfg, **{env_key: value}))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "moonshot\n"
