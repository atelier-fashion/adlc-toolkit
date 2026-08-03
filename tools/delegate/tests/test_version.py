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
import importlib.util
import os
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader

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


def _load_cli_module(cli):
    """Import an extensionless CLI script as a module, for parser introspection.

    The one place in this file that does NOT go through a subprocess: the drift
    guard below compares a module-level constant against the parser object it is
    supposed to mirror, and there is no way to observe an object identity across
    a process boundary. Executing the module is side-effect-free — every CLI
    guards its entry point with `if __name__ == "__main__"`.
    """
    name = "_cli_" + os.path.basename(cli).replace("-", "_")
    loader = SourceFileLoader(name, cli)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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


# --- BR-2/BR-3: precedence rank 1 (CLI flags) is reflected too --------------
# The version path never reaches argparse (ADR-1), so the flags have to be
# harvested from the raw argv or the report silently drops the highest-priority
# tier of the documented cascade and reports a provider the real call would not
# use — the LESSON-392 failure mode the whole feature exists to prevent.

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_model_flag_is_reflected_in_version_output(cli, tmp_path):
    r = _run([cli, "--model", "probe-flag-model", "--version"],
             env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _config_lines(r.stdout)["model"] == "probe-flag-model", r.stdout


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_attached_flag_form_is_reflected_in_version_output(cli, tmp_path):
    """`--base-url=VALUE` is as valid as `--base-url VALUE` to argparse, so the
    pre-parse harvest has to understand both forms."""
    r = _run([cli, "--base-url=https://flag.example/v1", "--version"],
             env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _config_lines(r.stdout)["base_url"] == "https://flag.example/v1", r.stdout


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_flag_outranks_env_in_version_output(cli, tmp_path):
    """Rank 1 beats rank 2 in the report exactly as it does in a real call."""
    r = _run([cli, "--model", "flag-model", "-V"],
             env=_clean_env(tmp_path, ADLC_DELEGATE_MODEL="env-model"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _config_lines(r.stdout)["model"] == "flag-model", r.stdout


# --- value smuggling: `-V` in VALUE position is not a version request -------
# The scan runs before argparse, so an argv-wide membership test turns an
# invocation argparse would reject into a silent exit-0 that prints the version
# and does nothing the user asked for. The value-aware scan skips option values
# so argparse gets to raise its own error.

def test_question_value_is_not_read_as_a_version_request(tmp_path):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("hello\n", encoding="utf-8")
    r = _run([ADLC_READ, "--dry-run", "--paths", str(corpus), "--question", "-V"],
             env=_clean_env(tmp_path))
    assert not r.stdout.startswith("adlc-toolkit"), r.stdout
    assert VERSION_LINE not in r.stdout, r.stdout
    assert r.returncode == 2, r.stdout + r.stderr
    assert "expected one argument" in r.stderr, r.stderr


def test_dry_run_survives_a_question_that_mentions_the_flag(tmp_path):
    """The other half: skipping values must not suppress a real `--version`
    elsewhere, nor break an ordinary run whose question names the flag."""
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("hello\n", encoding="utf-8")
    r = _run([ADLC_READ, "--dry-run", "--paths", str(corpus),
              "--question", "-V does what exactly?"], env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert not r.stdout.startswith("adlc-toolkit"), r.stdout
    assert "system: " in r.stdout, r.stdout


def test_spec_value_is_not_read_as_a_version_request(tmp_path):
    r = _run([ADLC_WRITE, "--spec", "--version", "--target", str(tmp_path / "x")],
             env=_clean_env(tmp_path))
    assert not r.stdout.startswith("adlc-toolkit"), r.stdout
    assert VERSION_LINE not in r.stdout, r.stdout


def test_attached_spec_value_is_not_read_as_a_version_request(tmp_path):
    """`--spec=--version` parses fine, so this one reaches the real path and
    fails on the missing key (exit non-zero) — what it must NOT do is print the
    version report."""
    r = _run([ADLC_WRITE, "--spec=--version", "--target", str(tmp_path / "x")],
             env=_clean_env(tmp_path))
    assert VERSION_LINE not in r.stdout, r.stdout
    assert not (tmp_path / "x").exists()


def test_extract_chat_output_value_is_not_read_as_a_version_request(tmp_path):
    """`-o -V` names an output file. The cheap membership pre-filter that gates
    the lazy `_common` import would say yes here; `wants_version` is the
    authority and falls through to normal parsing."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    r = _run([EXTRACT_CHAT, str(transcript), "-o", "-V"], env=_clean_env(tmp_path))
    assert not r.stdout.startswith("adlc-toolkit"), r.stdout
    assert VERSION_LINE not in r.stdout, r.stdout


# --- BR-5 / LESSON-397: a vendored checkout reports ITS version -------------

def test_vendored_checkout_reports_its_own_version(tmp_path):
    """The toolkit copied inside another git repo: `git rev-parse` from the
    module's directory reports the HOST repo's toplevel, whose VERSION file is
    the wrong answer. The root is accepted only when it really is a toolkit
    checkout, so the walk-up fallback wins here."""
    outer = tmp_path / "outer"
    vendored = outer / "vendor" / "tk" / "tools" / "delegate"
    vendored.mkdir(parents=True)
    try:
        init = subprocess.run(["git", "init"], cwd=str(outer),
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        pytest.skip("git is not installed; the host-repo confusion needs a repo")
    if init.returncode != 0:
        pytest.skip(f"git init failed: {init.stderr}")

    (outer / "VERSION").write_text("9.9.9-decoy\n", encoding="utf-8")
    (outer / "vendor" / "tk" / "VERSION").write_text("1.2.3-vendored\n",
                                                     encoding="utf-8")
    for src in (os.path.join(TOOLS, "_common.py"), ADLC_READ):
        shutil.copy(src, str(vendored))

    r = _run([str(vendored / "adlc-read"), "--version"], env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == "adlc-toolkit 1.2.3-vendored", r.stdout
    assert "9.9.9-decoy" not in r.stdout


# --- BR-2: the RESOLVED api_key_env is validated, not just the config one ---

_RAW_KEY_IN_ENV = "sk-live-RAWKEY0123456789abcdefgh"


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_key_pasted_into_the_env_override_is_refused(cli, tmp_path):
    """`ADLC_DELEGATE_API_KEY_ENV` outranks the config, so validating only the
    config branch leaves the highest-precedence source unchecked — and this
    field is printed by name, so an unvalidated key there is a key on stdout."""
    r = _version_run(cli, tmp_path, ADLC_DELEGATE_API_KEY_ENV=_RAW_KEY_IN_ENV)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[0] == VERSION_LINE
    assert lines[1].startswith("config_error: "), r.stdout
    assert _RAW_KEY_IN_ENV not in r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr


@pytest.mark.parametrize("vendor_key", [
    "gsk_abcdefghijklmnopqrstuvwxyz012345",   # Groq-style prefix
    "hf_abcdefghijklmnopqrstuvwxyz012345",    # Hugging Face-style prefix
])
@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_vendor_prefixed_key_the_blocklist_misses_is_still_refused(
        cli, vendor_key, tmp_path):
    """These are syntactically valid env-var names and carry an underscore, so
    the key-family blocklist and the underscore-free heuristic both pass them.
    The UPPER_SNAKE_CASE allow-list on the resolved value is what catches them —
    a blocklist can never enumerate every vendor prefix."""
    _write_config(tmp_path, f'delegate:\n  api_key_env: "{vendor_key}"\n')
    r = _version_run(cli, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "config_error: " in r.stdout, r.stdout
    assert vendor_key not in r.stdout + r.stderr


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_base_url_userinfo_is_redacted_on_the_print_path(cli, tmp_path):
    """A base URL may legitimately carry `user:pass@`, and --version is the one
    path that prints it. Redacted for display only — get_client still receives
    the URL intact."""
    r = _version_run(
        cli, tmp_path,
        ADLC_DELEGATE_BASE_URL="https://svc:sekret123@gw.example/v1",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "***@gw.example" in r.stdout, r.stdout
    assert "sekret123" not in r.stdout + r.stderr


# --- BR-6: unparseable config is fail-SOFT, not a refusal ------------------

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_unparseable_config_reports_shipped_defaults(cli, tmp_path):
    """`config_error:` is the REFUSAL path, not the "something was odd" path.
    A config the minimal reader cannot make sense of yields no delegate keys at
    all, so resolution falls through to the shipped defaults — which is exactly
    what a real call would use, so reporting anything else would be a lie."""
    cfg_dir = tmp_path / ".claude" / "adlc"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yml").write_bytes(
        b"\x00\xff\xfe\x01binary garbage\x00not: yaml: at all\n\x80\x81\n"
    )
    r = _version_run(cli, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "config_error:" not in r.stdout, r.stdout
    cfg = _config_lines(r.stdout)
    assert r.stdout.split("\n")[0] == VERSION_LINE
    assert cfg["base_url"] == _common._DEFAULT_BASE_URL
    assert cfg["model"] == _common._DEFAULT_MODEL
    assert cfg["api_key_env"] == _common._DEFAULT_API_KEY_VAR


# --- unit coverage for the shared helpers ----------------------------------
# In-process (no subprocess): these exercise branches a spawned CLI cannot reach
# on a healthy machine — a missing `git`, an absent or malformed VERSION file.

_READ_VALUE_FLAGS = frozenset({
    "--paths", "--question", "--max-tokens", "--model", "--base-url",
})


class TestRepoRootAndVersionUnit:

    def test_repo_root_walks_up_when_git_is_unavailable(self, monkeypatch):
        def _no_git(*args, **kwargs):
            raise FileNotFoundError("git")
        monkeypatch.setattr(_common.subprocess, "run", _no_git)
        here = os.path.dirname(os.path.realpath(_common.__file__))
        assert _common._repo_root() == os.path.dirname(os.path.dirname(here))

    def test_version_is_unknown_when_the_file_is_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_common, "_repo_root", lambda: str(tmp_path))
        assert _common.toolkit_version() == "unknown"

    def test_version_is_unknown_when_the_file_is_empty(self, monkeypatch, tmp_path):
        (tmp_path / "VERSION").write_text("", encoding="utf-8")
        monkeypatch.setattr(_common, "_repo_root", lambda: str(tmp_path))
        assert _common.toolkit_version() == "unknown"

    def test_only_the_first_version_line_is_read(self, monkeypatch, tmp_path):
        """A multi-line VERSION must not be able to forge extra BR-9 lines."""
        (tmp_path / "VERSION").write_text("9.9.9\ninjected: line\n", encoding="utf-8")
        monkeypatch.setattr(_common, "_repo_root", lambda: str(tmp_path))
        assert _common.toolkit_version() == "9.9.9"


class TestArgvHelpersUnit:

    @pytest.mark.parametrize("argv,expected", [
        ([], False),
        (["--version"], True),
        (["-V"], True),
        (["--no-warn", "-V"], True),
        (["--model", "m", "--version"], True),
        (["--paths", "a.txt", "--version"], True),
        (["--question", "-V"], False),                 # value position
        (["--question", "--version"], False),          # value position
        (["--question=--version"], False),             # attached form
        (["--", "--version"], False),                  # after the separator
        (["--dry-run", "--", "-V"], False),
    ])
    def test_wants_version_is_value_aware(self, argv, expected):
        assert _common.wants_version(argv, _READ_VALUE_FLAGS) is expected

    def test_wants_version_without_value_flags_still_finds_the_flag(self):
        assert _common.wants_version(["-V"]) is True

    @pytest.mark.parametrize("argv,expected", [
        (["--version"], (None, None)),
        (["--model", "m1", "--version"], ("m1", None)),
        (["--model=m2", "-V"], ("m2", None)),
        (["--base-url", "https://b/v1", "-V"], (None, "https://b/v1")),
        (["--base-url=https://c/v1", "--model=m3"], ("m3", "https://c/v1")),
        (["--", "--model", "m4"], (None, None)),
    ])
    def test_harvest_provider_flags(self, argv, expected):
        assert _common.harvest_provider_flags(argv) == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://api.example/v1", "https://api.example/v1"),
        ("https://svc:sekret123@gw.example/v1", "https://***@gw.example/v1"),
        ("https://svc@gw.example:8443/v1", "https://***@gw.example:8443/v1"),
        ("not a url at all", "not a url at all"),
        ("", ""),
    ])
    def test_redact_url_userinfo(self, url, expected):
        assert _common._redact_url_userinfo(url) == expected


class TestVersionReportLinesUnit:

    def test_version_line_only_when_config_is_excluded(self):
        lines = _common.version_report_lines(include_config=False)
        assert lines == [VERSION_LINE]

    def test_config_error_is_a_single_flattened_line(self, monkeypatch):
        def _refuse(**kwargs):
            raise SystemExit("refused\nacross\nlines")
        monkeypatch.setattr(_common, "resolve_provider", _refuse)
        lines = _common.version_report_lines()
        assert lines == [VERSION_LINE, "config_error: refused across lines"]


# ===========================================================================
# Re-audit round: the residuals. Each block below pins one attack that the
# first hardening pass left reachable.
# ===========================================================================

# --- prefix abbreviation: the scan's option sets are only complete if
#     argparse refuses every spelling they do not list --------------------
# `allow_abbrev` defaults to True, so `--sp x` used to be a legal spelling of
# `--spec x`. No fixed set can enumerate abbreviations, so the value-aware scan
# could not know `--sp`'s next token was a VALUE: `--sp "--version"` put
# `--version` in what the scan read as flag position and the CLI printed the
# version and exited 0, having generated nothing. Turning abbreviation off makes
# the declared spellings the only accepted ones — and the scan now declines on
# any option it does not recognize, so argparse gets to raise its own error.

@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_parsers_refuse_prefix_abbreviation(cli):
    """The property every exact-spelling set in these CLIs rests on."""
    assert _load_cli_module(cli)._build_parser().allow_abbrev is False


@pytest.mark.parametrize("cli", ALL_CLIS, ids=os.path.basename)
def test_known_flags_mirrors_the_parser_exactly(cli):
    """`_KNOWN_FLAGS` is a hand-written mirror of the parser's option surface.

    A drift guard, not a behavior test: an option added to `_build_parser()` and
    forgotten here would make the scan decline on a legal invocation (`--version`
    stops working alongside the new flag), and a stale entry would re-open the
    hole. `_actions`/`option_strings` are argparse internals, deliberately — they
    are the only complete statement of what the parser accepts.
    """
    module = _load_cli_module(cli)
    declared = set()
    for action in module._build_parser()._actions:
        declared.update(action.option_strings)
    assert module._KNOWN_FLAGS == declared, sorted(
        module._KNOWN_FLAGS.symmetric_difference(declared))


def test_abbreviated_flag_is_rejected_by_argparse(tmp_path):
    """`--sp x` is no longer a spelling of `--spec x`."""
    r = _run([ADLC_WRITE, "--sp", "x", "--target", str(tmp_path / "y")],
             env=_clean_env(tmp_path))
    assert r.returncode == 2, r.stdout + r.stderr
    # argparse reports the now-missing required `--spec` before it gets to the
    # leftover `--sp`; either half proves the abbreviation was not honored.
    assert ("the following arguments are required: --spec" in r.stderr
            or "unrecognized arguments" in r.stderr), r.stderr
    assert not (tmp_path / "y").exists()


def test_unknown_option_is_reported_not_swallowed_by_the_version_scan(tmp_path):
    """A CLI with no required args: the scan must hand `--sp` to argparse."""
    r = _run([ADLC_READ, "--sp", "x"], env=_clean_env(tmp_path))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "unrecognized arguments" in r.stderr, r.stderr


@pytest.mark.parametrize("argv_tail,cli", [
    (["--sp", "--version", "--target", "OUT"], ADLC_WRITE),
    (["--quest", "--version"], ADLC_READ),
    (["--out", "-V", "TRANSCRIPT"], EXTRACT_CHAT),
], ids=["adlc-write", "adlc-read", "extract-chat"])
def test_abbreviated_flag_cannot_hijack_the_version_path(
        argv_tail, cli, tmp_path):
    """The hijack itself: an abbreviation the scan cannot enumerate used to put
    `--version` in flag position, so the CLI printed the version, exited 0, and
    did nothing the user asked for. Exit 2 from argparse is the correct outcome.
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    subs = {"OUT": str(tmp_path / "z"), "TRANSCRIPT": str(transcript)}
    argv = [subs.get(tok, tok) for tok in argv_tail]

    r = _run([cli, *argv], env=_clean_env(tmp_path))
    assert VERSION_LINE not in r.stdout, r.stdout
    assert not r.stdout.startswith("adlc-toolkit"), r.stdout
    assert r.returncode == 2, r.stdout + r.stderr
    assert not (tmp_path / "z").exists()


# --- report forgery: every printed value is flattened ----------------------
# One line per field IS the BR-9 contract, and every value in the report comes
# from argv, the environment, or a config file. A newline inside one of them
# forged a field a consumer would then trust — `enabled: false` from a --model.

_FORGERY = "fake\nenabled: false"


def _enabled_lines(stdout):
    return [ln for ln in stdout.split("\n") if ln.startswith("enabled:")]


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_newline_in_model_flag_cannot_forge_a_report_line(cli, tmp_path):
    r = _run([cli, "--model=" + _FORGERY, "--version"], env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "model: fake enabled: false" in r.stdout, r.stdout
    assert _enabled_lines(r.stdout) == ["enabled: false"], r.stdout
    # The shape guard still holds: exactly the BR-9 keys, one line each.
    assert set(_config_lines(r.stdout)) == BR9_CONFIG_KEYS, r.stdout


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_newline_in_model_env_cannot_forge_a_report_line(cli, tmp_path):
    r = _version_run(cli, tmp_path, ADLC_DELEGATE_MODEL=_FORGERY)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "model: fake enabled: false" in r.stdout, r.stdout
    assert _enabled_lines(r.stdout) == ["enabled: false"], r.stdout


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_newline_in_base_url_cannot_forge_a_report_line(cli, tmp_path):
    """The same guarantee on the field that also goes through the redactor —
    sanitizing must happen AFTER redaction, or the redactor's output is the hole.
    """
    r = _version_run(
        cli, tmp_path,
        ADLC_DELEGATE_BASE_URL="https://probe.example/v1\nenabled: false",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert _enabled_lines(r.stdout) == ["enabled: false"], r.stdout
    assert set(_config_lines(r.stdout)) == BR9_CONFIG_KEYS, r.stdout


class TestCleanReportValueUnit:

    @pytest.mark.parametrize("raw,expected", [
        ("fake\nenabled: false", "fake enabled: false"),
        ("a\r\nb", "a b"),
        ("a\tb", "a b"),
        ("  padded  ", "padded"),
        ("esc\x1b[31mred", "esc[31mred"),   # ANSI introducer stripped
        ("nul\x00byte", "nulbyte"),
        ("del\x7fchar", "delchar"),
        ("plain", "plain"),
    ])
    def test_values_are_flattened_and_stripped(self, raw, expected):
        assert _common._clean_report_value(raw) == expected


# --- root identity: existence of the marker file is not identity -----------

def test_outer_toolkit_does_not_win_over_the_inner_copy(tmp_path):
    """A toolkit checkout vendored inside ANOTHER toolkit checkout.

    `git rev-parse` reports the outer toplevel, and the outer really does have
    `tools/delegate/_common.py` — so an existence check accepts it and reports
    the OUTER version for a run of the INNER code. Only comparing that marker
    against this very file distinguishes them.
    """
    outer = tmp_path / "outer"
    outer_delegate = outer / "tools" / "delegate"
    inner = outer / "vendor" / "tk"
    inner_delegate = inner / "tools" / "delegate"
    outer_delegate.mkdir(parents=True)
    inner_delegate.mkdir(parents=True)
    try:
        init = subprocess.run(["git", "init"], cwd=str(outer),
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        pytest.skip("git is not installed; this confusion needs a repo")
    if init.returncode != 0:
        pytest.skip(f"git init failed: {init.stderr}")

    (outer / "VERSION").write_text("9.9.9-outer-decoy\n", encoding="utf-8")
    (inner / "VERSION").write_text("1.2.3-inner\n", encoding="utf-8")
    # The outer checkout carries the marker file too — that is the whole point.
    shutil.copy(os.path.join(TOOLS, "_common.py"), str(outer_delegate))
    for src in (os.path.join(TOOLS, "_common.py"), ADLC_READ):
        shutil.copy(src, str(inner_delegate))

    r = _run([str(inner_delegate / "adlc-read"), "--version"],
             env=_clean_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split("\n")[0] == "adlc-toolkit 1.2.3-inner", r.stdout
    assert "9.9.9-outer-decoy" not in r.stdout


# --- `\Z` vs `$`: a trailing newline is not the end of a name --------------

@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_trailing_newline_in_key_env_name_is_refused(cli, tmp_path):
    """`$'MOONSHOT_API_KEY\\n'` matched `^[A-Z][A-Z0-9_]*$` — Python's `$` also
    matches before a trailing newline — so it was accepted as a NAME and printed,
    emitting a blank line into the middle of the report."""
    r = _version_run(cli, tmp_path,
                     ADLC_DELEGATE_API_KEY_ENV="MOONSHOT_API_KEY\n")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.rstrip("\n").split("\n")
    assert lines[0] == VERSION_LINE
    assert lines[1].startswith("config_error: "), r.stdout
    assert len(lines) == 2, r.stdout
    assert "" not in lines, r.stdout          # no blank line anywhere
    assert "Traceback" not in r.stderr, r.stderr


def test_env_var_name_regexes_reject_a_trailing_newline():
    assert not _common._KEY_ENV_NAME_RE.match("MOONSHOT_API_KEY\n")
    assert not _common._ENV_VAR_NAME_RE.match("MOONSHOT_API_KEY\n")
    assert _common._KEY_ENV_NAME_RE.match("MOONSHOT_API_KEY")
    assert _common._ENV_VAR_NAME_RE.match("MOONSHOT_API_KEY")


# --- AWS access-key IDs pass every other layer -----------------------------
# 20 uppercase alphanumerics: valid UPPER_SNAKE_CASE for the allow-list, and two
# characters short of the 24-char underscore-free heuristic. The key-family
# blocklist is the only layer that can refuse one, and it only knew `AKIA`.

_AWS_IDS = [
    "ASIAIOSFODNN7EXAMPLE",   # temporary/STS credentials
    "AKIAIOSFODNN7EXAMPLE",   # long-term access key (already covered)
    "AROAIOSFODNN7EXAMPLE",   # role
    "ANPAIOSFODNN7EXAMPLE",   # managed policy
]


@pytest.mark.parametrize("aws_id", _AWS_IDS)
def test_aws_access_key_ids_are_recognized_as_keys(aws_id):
    assert _common._looks_like_key(aws_id) is True
    # Guard the guard: they really do pass the layers that used to let them by.
    assert _common._KEY_ENV_NAME_RE.match(aws_id)
    assert len(aws_id) < 24


@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_aws_access_key_id_in_key_env_is_refused(cli, tmp_path):
    aws_id = "ASIAIOSFODNN7EXAMPLE"
    r = _version_run(cli, tmp_path, ADLC_DELEGATE_API_KEY_ENV=aws_id)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "config_error: " in r.stdout, r.stdout
    # The refusal message is a constant, so absence here is a real guarantee.
    assert aws_id not in r.stdout + r.stderr


# --- redaction is fail-closed ----------------------------------------------
# `urlsplit` REFUSES some strings, and the old code returned the input unchanged
# on ValueError — printing the password verbatim for exactly the inputs that
# most needed redacting.

_REDACT_SECRET = "SECRETPW"


@pytest.mark.parametrize("base_url", [
    "https://user:%s@[::1/v1" % _REDACT_SECRET,   # unterminated IPv6 → ValueError
    "user:%s@api.example.com/v1" % _REDACT_SECRET,  # scheme-less pre-host segment
    "%s@api.example.com/v1" % _REDACT_SECRET,       # scheme-less, no colon
    "//user:%s@api.example.com/v1" % _REDACT_SECRET,
])
@pytest.mark.parametrize("cli", CONFIG_CLIS, ids=os.path.basename)
def test_malformed_url_userinfo_never_reaches_the_output(cli, base_url, tmp_path):
    r = _version_run(cli, tmp_path, ADLC_DELEGATE_BASE_URL=base_url)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _REDACT_SECRET not in r.stdout, r.stdout
    assert _REDACT_SECRET not in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr


class TestRedactorFailClosedUnit:

    @pytest.mark.parametrize("url", [
        "https://user:SECRETPW@[::1/v1",
        "user:SECRETPW@api.example.com/v1",
        "SECRETPW@api.example.com/v1",
        "//user:SECRETPW@h/v1",
        "http://a:SECRETPW@h:99/p?q=1#f",
    ])
    def test_no_secret_survives_redaction(self, url):
        assert "SECRETPW" not in _common._redact_url_userinfo(url)

    def test_unparseable_url_yields_a_constant_not_the_input(self):
        out = _common._redact_url_userinfo("https://user:SECRETPW@[::1/v1")
        assert out == "<unredactable>"

    @pytest.mark.parametrize("url,expected", [
        ("https://api.example/v1", "api.example"),
        ("https://svc:sekret123@gw.example/v1", "***@gw.example"),
        ("https://gw.example:8443/v1", "gw.example:8443"),
    ])
    def test_endpoint_host(self, url, expected):
        assert _common._endpoint_host(url) == expected

    def test_endpoint_host_is_single_line(self):
        assert "\n" not in _common._endpoint_host("https://h/v1\nenabled: false")


# --- the privacy notice names the endpoint ---------------------------------

def test_notice_names_the_resolved_endpoint_host(tmp_path):
    """A hijacked `base_url` changes WHERE file contents go without changing
    anything else the user sees. The notice fires before `get_client()`, so the
    missing-key exit still leaves it on stderr (the test_cli_warn.py pattern)."""
    src = tmp_path / "x.txt"
    src.write_text("hello\n", encoding="utf-8")
    r = _run(
        [ADLC_READ, "--paths", str(src), "--question", "q"],
        env=_clean_env(tmp_path,
                       ADLC_DELEGATE_BASE_URL="https://hijacked.example/v1"),
    )
    assert "delegate: sending file contents" in r.stderr, r.stderr
    assert "hijacked.example" in r.stderr, r.stderr
    assert r.returncode != 0  # no key: still exits non-zero, after the notice


def test_notice_does_not_leak_base_url_userinfo(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n", encoding="utf-8")
    r = _run(
        [ADLC_READ, "--paths", str(src), "--question", "q"],
        env=_clean_env(
            tmp_path,
            ADLC_DELEGATE_BASE_URL="https://svc:sekret123@gw.example/v1"),
    )
    assert "delegate: sending file contents" in r.stderr, r.stderr
    assert "gw.example" in r.stderr, r.stderr
    assert "sekret123" not in r.stdout + r.stderr


# --- the version token is a version, not free text -------------------------

class TestVersionTokenCharsetUnit:

    @pytest.mark.parametrize("content,expected", [
        ("5.0.0\n", "5.0.0"),
        ("1.2.3-rc.1+build.7\n", "1.2.3-rc.1+build.7"),
        ("enabled: false\n", "unknown"),     # would forge a BR-9 line
        ("5.0.0 extra\n", "unknown"),
        ("a" * 65 + "\n", "unknown"),
        ("\x1b[31m5.0.0\n", "unknown"),      # ANSI escape
        ("\n", "unknown"),
    ])
    def test_only_version_shaped_tokens_are_reported(
            self, monkeypatch, tmp_path, content, expected):
        (tmp_path / "VERSION").write_text(content, encoding="utf-8")
        monkeypatch.setattr(_common, "_repo_root", lambda: str(tmp_path))
        assert _common.toolkit_version() == expected

    def test_a_forging_version_file_yields_one_clean_line(
            self, monkeypatch, tmp_path):
        (tmp_path / "VERSION").write_text("enabled: false\n", encoding="utf-8")
        monkeypatch.setattr(_common, "_repo_root", lambda: str(tmp_path))
        assert _common.version_report_lines(include_config=False) == [
            "adlc-toolkit unknown"]


# --- config file: regular files only, bounded read -------------------------

def test_fifo_config_does_not_hang_the_version_path(tmp_path):
    """`ADLC_CONFIG` is caller-controlled. Opening a fifo with no writer blocks
    forever, so `--version` never returned — an existence check cannot see that,
    only a file-TYPE check can. The timeout is the assertion."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    fifo = tmp_path / "config.yml"
    try:
        os.mkfifo(str(fifo))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"mkfifo unavailable here: {exc}")

    r = subprocess.run(
        [sys.executable, ADLC_READ, "--version"],
        capture_output=True, text=True, check=False, timeout=10,
        env=_clean_env(tmp_path, ADLC_CONFIG=str(fifo)),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = _config_lines(r.stdout)
    assert cfg["base_url"] == _common._DEFAULT_BASE_URL
    assert cfg["model"] == _common._DEFAULT_MODEL


def test_directory_config_is_ignored_not_crashed(tmp_path):
    """The same file-type guard, on the case a plain `open()` would raise for."""
    cfg = tmp_path / "config.yml"
    cfg.mkdir()
    assert _common.parse_delegate_config(str(cfg)) == {}


def test_oversized_config_is_read_bounded(tmp_path):
    """A three-scalar config is never 64 KiB. The `delegate:` block is at the
    top, so the bounded read still finds it — the tail is simply not loaded."""
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        'delegate:\n  model: "bounded-probe"\n' + "# pad\n" * 40000,
        encoding="utf-8",
    )
    assert _common.parse_delegate_config(str(cfg))["model"] == "bounded-probe"


# --- harvest is value-aware and treats an empty value as absent ------------

class TestHarvestValueAwarenessUnit:

    @pytest.mark.parametrize("argv,expected", [
        # A value position is a value position for BOTH scans, or the report
        # names a provider the real call would never use.
        (["--question", "--model", "foo"], (None, None)),
        (["--paths", "--base-url", "https://x/v1"], (None, None)),
        (["--question", "--model=m"], (None, None)),
        # Empty value == not supplied (matches resolve_provider's `or` chain).
        (["--model="], (None, None)),
        (["--base-url="], (None, None)),
        (["--model", ""], (None, None)),
        # Unchanged behavior for everything else.
        (["--question", "q", "--model", "m"], ("m", None)),
        (["--max-tokens", "10", "--model=m"], ("m", None)),
        (["--model", "m", "--base-url", "https://b/v1"], ("m", "https://b/v1")),
    ])
    def test_harvest_skips_other_options_values(self, argv, expected):
        assert _common.harvest_provider_flags(argv, _READ_VALUE_FLAGS) == expected

    def test_harvest_without_value_flags_keeps_the_old_behavior(self):
        """Default arg unchanged, so an un-updated caller cannot silently break."""
        assert _common.harvest_provider_flags(
            ["--question", "--model", "foo"]) == ("foo", None)


class TestWantsVersionKnownFlagsUnit:

    _KNOWN = _READ_VALUE_FLAGS | frozenset({"-h", "--help", "--dry-run",
                                            "--no-warn", "--print-enabled"})

    @pytest.mark.parametrize("argv,expected", [
        (["--version"], True),
        (["--no-warn", "-V"], True),
        (["--model=m", "--version"], True),
        (["--dry-run", "--paths", "a.txt", "-V"], True),
        (["--sp", "--version"], False),          # unknown option: defer
        (["--quest", "-V"], False),              # unknown option: defer
        (["--nope=1", "--version"], False),      # unknown attached form
    ])
    def test_unknown_options_make_the_scan_decline(self, argv, expected):
        assert _common.wants_version(argv, _READ_VALUE_FLAGS,
                                     self._KNOWN) is expected

    def test_omitting_known_flags_keeps_the_old_behavior(self):
        assert _common.wants_version(["--sp", "--version"],
                                     _READ_VALUE_FLAGS) is True
