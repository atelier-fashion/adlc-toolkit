"""REQ-553: `--version` / `-V` on adlc-read, adlc-write, and extract-chat.

Every test spawns the CLI as a real subprocess (LESSON-329) so the assertions
cover the shipped entry point — argv scanning, exit status, and which stream the
output lands on — not an in-process call to `main()`. The environment is built
from scratch for each run (never inherited) and `HOME` points at `tmp_path`, so
neither the developer's key vars nor a real `~/.claude/adlc/config.yml` can leak
into a result.

The output contract under test (BR-9 / ADR-3), on stdout, exit 0:

    adlc-toolkit <VERSION-file-content>
    base_url: <resolved>
    model: <resolved>
    api_key_env: <NAME only>
    enabled: true|false

`extract-chat` prints the version line only (no delegate config). On a refused
config the contract is the version line plus a single `config_error:` line.

BR-4 verification strategy (no eager SDK import) — two complementary checks,
since neither alone is conclusive:

  1. `python -X importtime <cli> --version` and assert `openai` never appears in
     the import trace. This proves the module was not imported on this path even
     though it *is* installed in the venv running the tests — `-I`/`-S` cannot
     show that, because they do not hide a venv-installed package.
  2. Run the CLIs under an interpreter where the SDK genuinely cannot be
     imported (the system `python3` with user site-packages suppressed) and
     assert exit 0. This is the real "clean venv" case from the AC. The helper
     first probes that the import actually fails there and skips otherwise —
     an assertion that passes because the SDK was importable all along would be
     a rotted guard, not coverage.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)                                  # tools/delegate
REPO_ROOT = os.path.dirname(os.path.dirname(TOOLS))            # toolkit root
sys.path.insert(0, TOOLS)
import _common  # noqa: E402

ADLC_READ = os.path.join(TOOLS, "adlc-read")
ADLC_WRITE = os.path.join(TOOLS, "adlc-write")
EXTRACT_CHAT = os.path.join(TOOLS, "extract-chat")

ALL_CLIS = (ADLC_READ, ADLC_WRITE, EXTRACT_CHAT)
CONFIG_CLIS = (ADLC_READ, ADLC_WRITE)  # the two that also print resolved config

# The exact BR-9 config key set — nothing more (Provider.source is deliberately
# excluded by ADR-3), nothing less.
BR9_CONFIG_KEYS = {"base_url", "model", "api_key_env", "enabled"}

_SYSTEM_PYTHON = "/usr/bin/python3"


def _expected_version():
    """The VERSION file content, read from the repo root the tests live in."""
    with open(os.path.join(REPO_ROOT, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


VERSION_LINE = "adlc-toolkit " + _expected_version()


def _clean_env(home, **extra):
    """A from-scratch env: only PATH (git, for the repo-root lookup) and HOME.

    Built by construction rather than by deleting keys from ``os.environ`` so a
    delegate var added later cannot silently start leaking into these tests.
    """
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}
    env.update(extra)
    return env


def _run(argv, env, cwd=None, python=None):
    return subprocess.run(
        [python or sys.executable, *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def _version_run(cli, tmp_path, flag="--version", **env_extra):
    return _run([cli, flag], env=_clean_env(tmp_path, **env_extra))


def _config_lines(stdout):
    """Parse the post-version lines as ``key: value``, returning a dict.

    Asserts the shape as it parses — a line without a `: ` separator is itself a
    contract violation (BR-9 exists so `adlc doctor` can consume this later).
    """
    lines = stdout.rstrip("\n").split("\n")
    out = {}
    for line in lines[1:]:
        assert ": " in line, f"not a `key: value` line: {line!r}"
        key, _, value = line.partition(": ")
        assert key and value, f"empty key or value: {line!r}"
        out[key] = value
    return out


def _write_config(home, body):
    """Write ``<HOME>/.claude/adlc/config.yml`` — the default config location."""
    cfg_dir = os.path.join(str(home), ".claude", "adlc")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg = os.path.join(cfg_dir, "config.yml")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write(body)
    return cfg


def _find_sdk_free_python():
    """An interpreter that genuinely cannot import the SDK, or ``None``.

    The system python is used with user site-packages suppressed; the probe below
    confirms the import really fails there before any test relies on it.
    """
    if not os.path.exists(_SYSTEM_PYTHON):
        return None
    probe = subprocess.run(
        [_SYSTEM_PYTHON, "-s", "-c", "import openai"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1"},
        check=False,
    )
    return None if probe.returncode == 0 else _SYSTEM_PYTHON


_SDK_FREE_PYTHON = _find_sdk_free_python()


# --- BR-1 / BR-5: the version line, all three CLIs -------------------------

@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_line_matches_version_file(cli, flag, tmp_path):
    r = _version_run(cli, tmp_path, flag=flag)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == VERSION_LINE, r.stdout
    assert "Traceback" not in r.stderr, r.stderr


def test_extract_chat_prints_version_line_only(tmp_path):
    """No delegate config for the local-only CLI (spec Assumptions / ADR-3)."""
    r = _version_run(EXTRACT_CHAT, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == VERSION_LINE


# --- BR-1 / ADR-1: works with no other arguments ---------------------------

def test_adlc_write_version_needs_no_required_args(tmp_path):
    """--spec/--target are `required=True`; argparse would exit 2 first, so the
    pre-parse argv scan is what makes this exit 0 (ADR-1)."""
    r = _version_run(ADLC_WRITE, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the following arguments are required" not in r.stderr
    assert r.stdout.split("\n")[0] == VERSION_LINE


def test_extract_chat_version_needs_no_positional(tmp_path):
    r = _version_run(EXTRACT_CHAT, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the following arguments are required" not in r.stderr


def test_version_composes_with_no_warn(tmp_path):
    """BR-7 / ADR-1: the scan covers the whole argv, not just argv[0]."""
    r = _run([ADLC_READ, "--no-warn", "-V"], env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == VERSION_LINE


# --- BR-9: exact key set, `key: value` shape -------------------------------

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_config_lines_carry_exactly_the_br9_keys(cli, tmp_path):
    r = _version_run(cli, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = _config_lines(r.stdout)
    assert set(cfg) == BR9_CONFIG_KEYS, sorted(cfg)


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_enabled_is_a_lowercase_boolean(cli, tmp_path):
    r = _version_run(cli, tmp_path)
    assert _config_lines(r.stdout)["enabled"] in ("true", "false")


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_defaults_are_reported_on_a_bare_machine(cli, tmp_path):
    """No env, no config file → the shipped defaults, matching what a real call
    would resolve through the same resolver (BR-3)."""
    cfg = _config_lines(_version_run(cli, tmp_path).stdout)
    assert cfg["base_url"] == _common._DEFAULT_BASE_URL
    assert cfg["model"] == _common._DEFAULT_MODEL
    assert cfg["api_key_env"] == _common._DEFAULT_API_KEY_VAR
    assert cfg["enabled"] == "false"  # BR-11 opt-in: off on a fresh install


# --- BR-2 / BR-3: the reported config is the resolved config ---------------

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_env_overrides_appear_in_output(cli, tmp_path):
    r = _version_run(
        cli, tmp_path,
        ADLC_DELEGATE_MODEL="probe-model",
        ADLC_DELEGATE_BASE_URL="https://probe.example/v1",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = _config_lines(r.stdout)
    assert cfg["model"] == "probe-model"
    assert cfg["base_url"] == "https://probe.example/v1"


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_config_file_values_appear_in_output(cli, tmp_path):
    _write_config(
        tmp_path,
        'delegate:\n'
        '  enabled: true\n'
        '  base_url: "https://cfg.example/v1"\n'
        '  api_key_env: "MY_PROVIDER_KEY"\n',
    )
    cfg = _config_lines(_version_run(cli, tmp_path).stdout)
    assert cfg["base_url"] == "https://cfg.example/v1"
    assert cfg["api_key_env"] == "MY_PROVIDER_KEY"
    assert cfg["enabled"] == "true"


# --- BR-2: the key VALUE is never read or printed --------------------------

_SECRET = "sk-test-secret-value"


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_key_env_name_is_printed(cli, tmp_path):
    """Positive half: the env var NAME is reported (that is the diagnostic)."""
    r = _version_run(cli, tmp_path, MOONSHOT_API_KEY=_SECRET)
    cfg = _config_lines(r.stdout)
    assert cfg["api_key_env"] == "MOONSHOT_API_KEY"
    # The legacy key var is also the opt-in continuity signal.
    assert cfg["enabled"] == "true"


@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_key_value_never_appears_anywhere(cli, tmp_path):
    """Negative half: not on stdout, not on stderr, not even redacted."""
    r = _version_run(cli, tmp_path, MOONSHOT_API_KEY=_SECRET)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _SECRET not in r.stdout
    assert _SECRET not in r.stderr


# --- BR-6: fail-soft on a refused config -----------------------------------

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_key_in_config_degrades_to_config_error_line(cli, tmp_path):
    """A config storing a KEY where a NAME belongs makes resolve_provider raise.
    --version must still report the version and degrade to one diagnostic line
    (LESSON-395) — exit 0, no traceback."""
    _write_config(
        tmp_path,
        'delegate:\n  enabled: true\n  api_key_env: "sk-abcdefghijklmnop0123456789"\n',
    )
    r = _version_run(cli, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[0] == VERSION_LINE
    assert len(lines) == 2, r.stdout
    assert lines[1].startswith("config_error: ")
    assert "\n" not in lines[1]  # one line, not a wrapped multi-line message
    assert "Traceback" not in r.stderr, r.stderr


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_config_error_does_not_leak_the_offending_value(cli, tmp_path):
    """The refused value IS a key — the diagnostic must not echo it back."""
    _write_config(tmp_path, f'delegate:\n  api_key_env: "{_SECRET}xxxxxxxxxxxx"\n')
    r = _version_run(cli, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "config_error: " in r.stdout
    assert _SECRET not in r.stdout + r.stderr


# --- BR-5 / LESSON-397: script-derived root, not caller cwd ----------------

@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_version_from_a_foreign_cwd(cli, tmp_path):
    """Run from an unrelated project directory that has its own VERSION file:
    the toolkit's version must be reported, never the caller's."""
    decoy = tmp_path / "VERSION"
    decoy.write_text("0.0.0-caller-project\n", encoding="utf-8")
    r = _run([cli, "--version"], env=_clean_env(tmp_path), cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == VERSION_LINE
    assert "0.0.0-caller-project" not in r.stdout


# --- BR-4: no SDK import on the version path -------------------------------

@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_version_path_does_not_import_the_sdk(cli, tmp_path):
    """Strategy 1 (see module docstring): `-X importtime` writes one trace line
    per imported module to stderr, so the SDK's absence there proves the import
    never happened — even though it IS installed in the venv running this test.
    """
    r = subprocess.run(
        [sys.executable, "-X", "importtime", cli, "--version"],
        capture_output=True, text=True, env=_clean_env(tmp_path), check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # Guard the guard: if -X importtime ever stops emitting, the grep below
    # would pass vacuously.
    assert "import time:" in r.stderr, r.stderr
    assert "openai" not in r.stderr, r.stderr


@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_version_works_where_the_sdk_is_not_installed(cli, tmp_path):
    """Strategy 2 (see module docstring): the clean-venv case from the AC, run
    under an interpreter where `import openai` genuinely raises."""
    if _SDK_FREE_PYTHON is None:
        pytest.skip(
            "no interpreter on this machine where the SDK import fails "
            f"({_SYSTEM_PYTHON} missing, or it has the SDK on the system path)"
        )
    env = _clean_env(tmp_path, PYTHONNOUSERSITE="1")
    r = _run(["-s", cli, "--version"], env=env, python=_SDK_FREE_PYTHON)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == VERSION_LINE
    assert "Traceback" not in r.stderr, r.stderr
