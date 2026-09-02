"""Tests for tools/adlc/forge_config.py (REQ-520 BR-2, BR-6; REQ-609 BR-2/6/8/9/13).

The parse cases are loader-backed since REQ-609: `parse_forge_config` reads the
`forge:` section through `tools/delegate/_machine_config.load_machine_config`, the
same call the delegation opt-in is read with, so the shapes asserted here are the
shapes a real YAML parser sees — and the isolation cases below prove that one
file gives one verdict without either section locking the other out.
"""

import os
import subprocess
import sys

import pytest

import forge_config as fc

# On sys.path because forge_config inserted <repo>/tools/delegate when it was
# imported (REQ-609 ADR-1). Imported here to assert the OTHER consumer's verdict
# on the very same file — the whole point of BR-8 is that there is one verdict.
import _common
import _machine_config

_ADLC_DIR = os.path.dirname(os.path.abspath(fc.__file__))


def _write(tmp_path, text, name="config.yml"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def _poisoned_yaml(tmp_path):
    """A dir that, first on PYTHONPATH, makes ``import yaml`` raise ImportError.

    Shadows the real package rather than uninstalling anything, so the same
    machine can run both the missing-PyYAML case and its benign twin.
    """
    pkg = tmp_path / "poison" / "yaml"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "raise ImportError('no module named yaml (test poison)')\n")
    return str(tmp_path / "poison")


def _run_reader(cfg_path, env_extra=None, repeats=1):
    """Parse ``cfg_path`` with forge_config in a CHILD interpreter.

    A child, because the contract under test is partly what reaches stderr and
    how often (REQ-609 BR-9's "one line"), which a same-process call cannot show
    once another test has already tripped the once-per-process notice.
    """
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import forge_config as fc\n"
        "for _ in range(int(sys.argv[3])):\n"
        "    print('RESULT', sorted(fc.parse_forge_config(sys.argv[2]).items()))\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-c", code, _ADLC_DIR, cfg_path, str(repeats)],
        capture_output=True, text=True, env=env,
    )


# --- detect_provider_from_url ---------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("git@github.com:org/repo.git", "github"),
    ("https://github.com/org/repo.git", "github"),
    ("https://github.com/org/repo", "github"),
    ("git@ssh.dev.azure.com:v3/org/proj/repo", "azure-devops"),
    ("https://dev.azure.com/org/proj/_git/repo", "azure-devops"),
    ("https://org.visualstudio.com/proj/_git/repo", "azure-devops"),
    ("org@vs-ssh.org.visualstudio.com:v3/org/proj/repo", "azure-devops"),
])
def test_detect_known_hosts(url, expected):
    assert fc.detect_provider_from_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://gitlab.com/org/repo.git",
    "git@bitbucket.org:org/repo.git",
    "https://example.invalid/x/y",
])
def test_detect_unrecognized_fails_loud(url):
    with pytest.raises(fc.UnknownForgeError) as exc:
        fc.detect_provider_from_url(url)
    msg = str(exc.value)
    # names the URL and both supported providers (BR-2)
    assert url in msg
    assert "github" in msg and "azure-devops" in msg


def test_detect_no_url_fails_loud():
    with pytest.raises(fc.UnknownForgeError):
        fc.detect_provider_from_url("")


# --- looks_like_key / validate_auth (BR-6) --------------------------------

@pytest.mark.parametrize("value", [
    "gh", "az",                       # CLI login source names
    "ADO_PAT", "MY_API_TOKEN",        # env-var NAMES (SCREAMING_SNAKE)
    "AZURE_DEVOPS_EXT_PAT",
])
def test_auth_source_names_accepted(value):
    assert fc.looks_like_key(value) is False
    assert fc.validate_auth(value) == value


@pytest.mark.parametrize("value", [
    "ghp_" + "a" * 36,                # GitHub PAT
    "sk-" + "a" * 25,                 # OpenAI-style key
    "AKIA" + "A" * 16,                # AWS access key id
    "aB3xZ9qL2mN8pQ7rT4vW1yU6",       # underscore-free long mixed-class blob
])
def test_key_shaped_values_refused(value):
    assert fc.looks_like_key(value) is True
    with pytest.raises(fc.ForgeConfigError):
        fc.validate_auth(value)


# --- parse_forge_config, through the one loader (REQ-609 BR-8) -------------

def test_reads_section_through_load_machine_config(tmp_path, monkeypatch):
    """The section comes back, and it comes back THROUGH the shared loader.

    Both halves matter. The value assertion alone would pass against any reader;
    the spy is what pins BR-8's "one loader, one verdict". The shapes are chosen
    to be ones the retired flat reader got wrong: a comment on the section
    header (which discarded the whole block), a quoted key, and a sibling
    section with nested mappings after it.
    """
    cfg = _write(tmp_path, (
        "delegate:\n  enabled: false\n"
        "forge:  # the forge for this machine\n"
        "  'provider': azure-devops  # ado\n"
        "  auth: ADO_PAT\n"
        "repos:\n  web:\n    primary: true\n"
    ))
    seen = []
    real = _machine_config.load_machine_config

    def spy(path=None):
        seen.append(path)
        return real(path)

    monkeypatch.setattr(fc._machine_config, "load_machine_config", spy)
    assert fc.parse_forge_config(cfg) == {"provider": "azure-devops", "auth": "ADO_PAT"}
    assert seen == [cfg], "parse_forge_config must read through load_machine_config"


def test_forge_only_config_leaves_delegate_unconfigured(tmp_path):
    """A shared config carrying only `forge:` must not lock delegation out.

    BR-6: an absent `delegate` section is *unconfigured* — `{}`, so continuity
    may still apply — not malformed. The old "no block found is malformed" rule
    locked out every machine whose config had only a forge section.
    """
    cfg = _write(tmp_path, "forge:\n  provider: github\n  auth: gh\n")
    assert fc.parse_forge_config(cfg) == {"provider": "github", "auth": "gh"}
    assert _common.parse_delegate_config(cfg) == {}


def test_delegate_only_config_leaves_forge_unconfigured(tmp_path):
    """The mirror direction: only `delegate:` leaves forge unconfigured (auto)."""
    cfg = _write(tmp_path, "delegate:\n  enabled: true\n  model: some-model\n")
    assert fc.parse_forge_config(cfg) == {}
    # ... while the delegate consumer reads its own section from the same file.
    assert _common.parse_delegate_config(cfg).get("enabled") is True


def test_duplicate_key_is_whole_document(tmp_path):
    """A repeated key refuses for BOTH consumers, whichever section it is in.

    BR-2: one loader gives one verdict. A duplicate under `delegate:` makes
    forge refuse; a duplicate under `forge:` makes the delegate section
    malformed. The refusal names the duplicated key and the line of its SECOND
    occurrence, so the operator fixes the file instead of guessing which
    consumer objected (BR-13).
    """
    dup_in_delegate = _write(tmp_path, (
        "delegate:\n  enabled: false\n  enabled: true\n"
        "forge:\n  provider: github\n"
    ), name="dup-delegate.yml")
    with pytest.raises(fc.MalformedConfigError) as exc:
        fc.parse_forge_config(dup_in_delegate)
    msg = str(exc.value)
    assert dup_in_delegate in msg
    assert "duplicate-key" in msg
    assert "enabled" in msg and "line 3" in msg

    dup_in_forge = _write(tmp_path, (
        "delegate:\n  enabled: false\n"
        "forge:\n  provider: github\n  provider: azure-devops\n"
    ), name="dup-forge.yml")
    cfg = _common.parse_delegate_config(dup_in_forge)
    assert cfg.get(_common._MALFORMED) is True
    assert "duplicate-key" in cfg.get(_common._MALFORMED_REASON, "")

    # Benign twin: the same two sections with no repeat read cleanly for both.
    clean = _write(tmp_path, (
        "delegate:\n  enabled: false\n"
        "forge:\n  provider: github\n"
    ), name="clean.yml")
    assert fc.parse_forge_config(clean) == {"provider": "github"}
    assert _common.parse_delegate_config(clean) == {"enabled": False}


# --- the ADR-2 carve-out: dependency-missing is unconfigured, loudly -------

def test_dependency_missing_is_unconfigured_for_forge_with_stderr(tmp_path):
    """No PyYAML in this interpreter -> `{}` plus ONE stderr line (BR-9, ADR-2).

    A missing parser is a statement about the machine's install, not about the
    file, and `forge.auth` never carries authority — so forge proceeds
    unconfigured rather than making every PR operation hostage to a delegation
    install nobody opted into. It is not silent: the operator gets the same
    named line the delegate consumer emits, once, however many times the config
    is read in that process.
    """
    cfg = _write(tmp_path, "forge:\n  provider: github\n  auth: ADO_PAT\n")

    missing = _run_reader(cfg, {"PYTHONPATH": _poisoned_yaml(tmp_path)}, repeats=2)
    assert missing.returncode == 0, missing.stderr
    assert missing.stdout.count("RESULT []") == 2, missing.stdout
    pyyaml_lines = [ln for ln in missing.stderr.splitlines() if "PyYAML" in ln]
    assert len(pyyaml_lines) == 1, missing.stderr
    assert "install.sh" in pyyaml_lines[0]

    # Benign twin: the same file, the same interpreter, PyYAML importable.
    present = _run_reader(cfg, repeats=2)
    assert present.returncode == 0, present.stderr
    assert "'provider', 'github'" in present.stdout
    assert "PyYAML" not in present.stderr


def test_missing_loader_is_unconfigured_with_stderr(tmp_path):
    """A copy with no reachable loader is the same class: `{}` plus one line.

    `partials/forge.sh` supports a project that vendors `tools/adlc/forge_config.py`
    alone. Since REQ-609 that copy needs the loader, which it finds next to
    itself or in the installed toolkit (`~/.claude/skills`); with neither, the
    machine cannot parse the config — an install defect, not a file defect — so
    the same carve-out applies, loudly.
    """
    vendored = tmp_path / "vend" / "tools" / "adlc"
    vendored.mkdir(parents=True)
    (vendored / "forge_config.py").write_text(
        open(fc.__file__, encoding="utf-8").read())
    (tmp_path / "nohome").mkdir()
    cfg = _write(tmp_path, "forge:\n  provider: azure-devops\n", name="v.yml")
    env = dict(os.environ, HOME=str(tmp_path / "nohome"))
    env.pop("PYTHONPATH", None)
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import forge_config as fc; "
         "print('RESULT', fc.parse_forge_config(sys.argv[2]))",
         str(vendored), cfg],
        capture_output=True, text=True, env=env,
    )
    assert out.returncode == 0, out.stderr
    assert "RESULT {}" in out.stdout
    assert "_machine_config.py" in out.stderr and "install.sh" in out.stderr


# --- every other malformed reason refuses (BR-2, BR-13) --------------------

def _dangling(tmp_path):
    link = tmp_path / "dangling.yml"
    link.symlink_to(tmp_path / "does-not-exist.yml")
    return str(link)


def test_malformed_config_refuses_naming_path_and_reason(tmp_path):
    """Every reason class except `dependency-missing` is a refusal.

    Each case asserts the message names the path and the reason CLASS, and that
    it never advises setting an environment variable — no env var can make an
    unreadable file readable, and pointing at one sends a locked-out operator
    away from the file that is actually broken (BR-13).
    """
    cases = [
        ("not-regular-file", str(tmp_path)),                       # a directory
        ("not-regular-file", os.devnull),                          # /dev/null
        ("dangling-symlink", _dangling(tmp_path)),
        ("not-a-mapping", _write(tmp_path, "- a\n- b\n", name="list.yml")),
        ("yaml-error", _write(tmp_path, "forge:\n\tprovider: x\n", name="tab.yml")),
        ("over-cap", _write(
            tmp_path,
            "forge:\n  provider: github\n# " + "x" * 70000 + "\n",
            name="big.yml")),
    ]
    for reason_class, path in cases:
        with pytest.raises(fc.MalformedConfigError) as exc:
            fc.parse_forge_config(path)
        msg = str(exc.value)
        assert path in msg, (reason_class, msg)
        assert reason_class in msg, (reason_class, msg)
        assert "ADLC_DELEGATE_ENABLED" not in msg
        assert "export " not in msg

    # Benign twin: a regular, in-cap, mapping-topped file at the same shape.
    ok = _write(tmp_path, "forge:\n  provider: github\n", name="ok.yml")
    assert fc.parse_forge_config(ok) == {"provider": "github"}


def test_forge_section_shapes(tmp_path):
    """Absent / empty is unconfigured; a shape we cannot read is refused."""
    assert fc.parse_forge_config(str(tmp_path / "nope.yml")) == {}          # absent
    assert fc.parse_forge_config(_write(tmp_path, "", name="empty.yml")) == {}
    assert fc.parse_forge_config(
        _write(tmp_path, "delegate:\n  enabled: true\n", name="d.yml")) == {}
    assert fc.parse_forge_config(
        _write(tmp_path, "forge:\n", name="hdr.yml")) == {}                 # empty section
    assert fc.parse_forge_config(
        _write(tmp_path, "forge: {}\n", name="flow.yml")) == {}
    # Quotes and inline comments are the parser's job now, not a hand-written strip.
    assert fc.parse_forge_config(_write(
        tmp_path, "forge:\n  provider: 'github'\n  auth: \"GH_TOKEN_NAME\"  # x\n",
        name="q.yml")) == {"provider": "github", "auth": "GH_TOKEN_NAME"}
    # A non-mapping section, and a non-string value, are refused rather than
    # coerced — `str()` of a mapping is not what the operator wrote.
    for text, name in (("forge: github\n", "scalar.yml"),
                       ("forge:\n  - github\n", "seq.yml")):
        with pytest.raises(fc.MalformedConfigError):
            fc.parse_forge_config(_write(tmp_path, text, name=name))
    for text, name in (("forge:\n  provider:\n    name: github\n", "nested.yml"),
                       ("forge:\n  auth: 12345\n", "int.yml")):
        with pytest.raises(fc.MalformedConfigError):
            fc.parse_forge_config(_write(tmp_path, text, name=name))


def test_module_import_pulls_in_no_yaml():
    """Importing forge_config must not import PyYAML (LESSON-395, BR-1).

    `checks.py` and `adlc doctor` must load on a machine that has no PyYAML at
    all — that is the machine the `pyyaml` check exists to report on.
    """
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import forge_config; "
         "print('yaml' in sys.modules)", _ADLC_DIR],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


# --- resolve_provider precedence (BR-2) ------------------------------------

def test_precedence_project_over_machine():
    assert fc.resolve_provider(
        ".", cfg_project={"provider": "github"}, cfg_machine={"provider": "azure-devops"},
    ) == ("github", "project-config")


def test_precedence_machine_when_project_auto():
    assert fc.resolve_provider(
        ".", cfg_project={"provider": "auto"}, cfg_machine={"provider": "azure-devops"},
    ) == ("azure-devops", "machine-config")


def test_invalid_explicit_provider_refused():
    with pytest.raises(fc.ForgeConfigError):
        fc.resolve_provider(".", cfg_project={"provider": "gitlab"}, cfg_machine={})


def test_auto_falls_through_to_url(tmp_path):
    # No provider in either config -> auto -> detect from origin.
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin",
         "https://github.com/o/r.git"], check=True,
    )
    provider, source = fc.resolve_provider(str(repo), cfg_project={}, cfg_machine={})
    assert provider == "github"
    assert source == "auto"


# --- CLI entrypoint --------------------------------------------------------

def test_cli_resolve_provider(tmp_path):
    # Synthetic repo with a github origin — the toolkit checkout's own origin
    # varies by clone location (e.g. an ADO mirror), so never assert on it.
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin",
         "https://github.com/o/r.git"], check=True,
    )
    env = dict(os.environ, ADLC_CONFIG=str(tmp_path / "no-machine-config.yml"))
    out = subprocess.run(
        ["python3", fc.__file__, "resolve-provider", str(repo)],
        capture_output=True, text=True, env=env,
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "github"


def test_cli_refuses_malformed_config_naming_path_and_reason(tmp_path):
    """The refusal is an EXIT, not an exception the caller may swallow (BR-13).

    `partials/forge.sh` and the `forge` doctor check drive this CLI, so the
    observable contract is the exit status plus the stderr line — and the line
    must name the path and the reason class without advising an env var
    (LESSON-478: assert the output, not just the code).
    """
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/o/r.git"], check=True)
    bad = _write(tmp_path, "forge:\n  provider: github\n  provider: github\n",
                 name="dup.yml")
    out = subprocess.run(
        [sys.executable, fc.__file__, "resolve-provider", str(repo)],
        capture_output=True, text=True, env=dict(os.environ, ADLC_CONFIG=bad),
    )
    assert out.returncode == 2, out.stdout
    assert bad in out.stderr
    assert "duplicate-key" in out.stderr and "line 3" in out.stderr
    assert "ADLC_DELEGATE_ENABLED" not in out.stderr

    # Benign twin: the same repo and CLI with a readable config resolves.
    good = _write(tmp_path, "forge:\n  provider: auto\n", name="good.yml")
    ok = subprocess.run(
        [sys.executable, fc.__file__, "resolve-provider", str(repo)],
        capture_output=True, text=True, env=dict(os.environ, ADLC_CONFIG=good),
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == "github"


def test_cli_validate_auth_rejects_key():
    script = fc.__file__
    out = subprocess.run(
        ["python3", script, "validate-auth", "ghp_" + "a" * 36],
        capture_output=True, text=True,
    )
    # main returns 2 on a key-shaped value, with an actionable stderr message.
    assert out.returncode == 2
    assert "SOURCE name" in out.stderr or "never a key" in out.stderr
