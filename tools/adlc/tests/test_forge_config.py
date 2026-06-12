"""Tests for tools/adlc/forge_config.py (REQ-520 BR-2, BR-6)."""

import os
import subprocess

import pytest

import forge_config as fc


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


# --- parse_forge_config ----------------------------------------------------

def _write(tmp_path, text):
    p = tmp_path / "config.yml"
    p.write_text(text)
    return str(p)


def test_parse_reads_forge_block(tmp_path):
    cfg = _write(tmp_path, (
        "delegate:\n  enabled: true\n"
        "forge:\n  provider: azure-devops  # ado\n  auth: ADO_PAT\n"
        "repos:\n  web:\n    primary: true\n"
    ))
    assert fc.parse_forge_config(cfg) == {"provider": "azure-devops", "auth": "ADO_PAT"}


def test_parse_absent_file_is_empty(tmp_path):
    assert fc.parse_forge_config(str(tmp_path / "nope.yml")) == {}


def test_parse_no_forge_block(tmp_path):
    cfg = _write(tmp_path, "delegate:\n  enabled: true\n")
    assert fc.parse_forge_config(cfg) == {}


def test_parse_strips_quotes_and_comments(tmp_path):
    cfg = _write(tmp_path, "forge:\n  provider: 'github'\n  auth: \"GH_TOKEN_NAME\"\n")
    assert fc.parse_forge_config(cfg) == {"provider": "github", "auth": "GH_TOKEN_NAME"}


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


def test_cli_validate_auth_rejects_key():
    script = fc.__file__
    out = subprocess.run(
        ["python3", script, "validate-auth", "ghp_" + "a" * 36],
        capture_output=True, text=True,
    )
    # main returns 2 on a key-shaped value, with an actionable stderr message.
    assert out.returncode == 2
    assert "SOURCE name" in out.stderr or "never a key" in out.stderr
