"""Offline tests for tools/kimi/_common.py."""

import io
import os

import pytest

import _common


def test_pack_corpus_uses_basename_by_default(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("print('hi')\n", encoding="utf-8")
    result = _common.pack_corpus([str(f)])
    assert f"<file path='{os.path.basename(str(f))}'>" in result
    assert str(f) not in result


def test_pack_corpus_full_path_when_opted_in(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("print('hi')\n", encoding="utf-8")
    result = _common.pack_corpus([str(f)], use_basename=False)
    assert f"<file path='{str(f)}'>" in result
    assert str(f) in result


def test_pack_corpus_missing_file_raises_with_full_path():
    missing = "/definitely/not/here.txt"
    with pytest.raises(SystemExit) as excinfo:
        _common.pack_corpus([missing])
    assert missing in str(excinfo.value)


def test_pack_corpus_preserves_input_order(tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("A\n", encoding="utf-8")
    b.write_text("B\n", encoding="utf-8")
    result = _common.pack_corpus([str(a), str(b)])
    assert result.index("a.py") < result.index("b.py")


def test_strip_fences_no_fence_passthrough():
    assert _common._strip_fences("hello\nworld") == "hello\nworld"


def test_strip_fences_plain():
    text = "```\nx=1\n```"
    assert _common._strip_fences(text) == "x=1"


def test_strip_fences_language_tagged_open():
    text = "```python\nx=1\n```"
    assert _common._strip_fences(text) == "x=1"


def test_strip_fences_language_tagged_close():
    text = "```\nx=1\n```python"
    assert _common._strip_fences(text) == "x=1"


def test_emit_exfil_notice_writes_to_stream():
    buf = io.StringIO()
    _common.emit_exfil_notice(stream=buf)
    out = buf.getvalue()
    assert "Moonshot" in out
    assert "--no-warn" in out
    assert "KIMI_NO_WARN" in out
    assert "MOONSHOT_API_KEY" not in out
    assert out.endswith("\n")


# --- REQ-422: rc-fallback when MOONSHOT_API_KEY is not in env ---

def test_read_key_from_rc_finds_canonical_form(monkeypatch, tmp_path):
    """Canonical `export VAR="..."` form is extracted from ~/.zshrc."""
    home = tmp_path
    (home / ".zshrc").write_text(
        '# some comment\nexport MOONSHOT_API_KEY="sk-from-zshrc-xyz"\nexport OTHER="x"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc() == "sk-from-zshrc-xyz"


def test_read_key_from_rc_falls_back_to_bash_profile(monkeypatch, tmp_path):
    """If ~/.zshrc lacks the key, ~/.bash_profile is checked next."""
    home = tmp_path
    (home / ".zshrc").write_text("# no key here\n", encoding="utf-8")
    (home / ".bash_profile").write_text(
        'export MOONSHOT_API_KEY="sk-from-bash-profile"\n', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc() == "sk-from-bash-profile"


def test_read_key_from_rc_returns_empty_when_no_rc_has_key(monkeypatch, tmp_path):
    """If no rc file contains the export, returns empty string."""
    home = tmp_path
    (home / ".zshrc").write_text("# nothing\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc() == ""


def test_read_key_from_rc_ignores_indented_export(monkeypatch, tmp_path):
    """Only matches lines starting at column 0 — defensive against partial matches."""
    home = tmp_path
    (home / ".zshrc").write_text(
        '  export MOONSHOT_API_KEY="indented-not-canonical"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc() == ""


def test_get_client_uses_env_when_set(monkeypatch, tmp_path):
    """Env var takes precedence over rc-fallback."""
    home = tmp_path
    (home / ".zshrc").write_text(
        'export MOONSHOT_API_KEY="sk-from-rc"\n', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-from-env")
    client = _common.get_client()
    assert client.api_key == "sk-from-env"


def test_get_client_falls_back_to_rc_when_env_missing(monkeypatch, tmp_path):
    """When env var is absent, rc-fallback supplies the key (REQ-422 fix)."""
    home = tmp_path
    (home / ".zshrc").write_text(
        'export MOONSHOT_API_KEY="sk-rc-fallback"\n', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    client = _common.get_client()
    assert client.api_key == "sk-rc-fallback"


def test_get_client_raises_when_neither_env_nor_rc_has_key(monkeypatch, tmp_path):
    """Both sources empty → SystemExit naming the var, key value never echoed."""
    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        _common.get_client()
    assert "MOONSHOT_API_KEY" in str(exc.value)
