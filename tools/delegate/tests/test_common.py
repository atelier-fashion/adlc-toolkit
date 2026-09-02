"""Offline tests for tools/delegate/_common.py."""

import io
import os
import threading

import pytest

import _common
import _machine_config


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
    # Provider-neutral notice (REQ-515): names the resolved model + the delegate,
    # not "Moonshot" hardcoded, and mentions the suppression mechanisms.
    assert "delegate" in out
    assert "--no-warn" in out
    assert "ADLC_DELEGATE_NO_WARN" in out
    assert "MOONSHOT_API_KEY" not in out
    assert out.endswith("\n")


def test_emit_exfil_notice_names_the_endpoint_host(tmp_path):
    """REQ-553: the notice names WHERE the contents are going, not just what
    model is asked. A `base_url` hijacked via env or config otherwise changes the
    destination with nothing in the notice to show it. Userinfo is redacted —
    the notice must not become a new place credentials get printed.
    """
    buf = io.StringIO()
    provider = _common.Provider(
        base_url="https://svc:sekret123@gw.example/v1",
        model="probe-model",
        api_key_env="MY_PROVIDER_KEY",
        enabled=True,
        source="test",
    )
    _common.emit_exfil_notice(stream=buf, provider=provider)
    out = buf.getvalue()
    assert "gw.example" in out
    assert "probe-model" in out
    assert "sekret123" not in out
    assert "MY_PROVIDER_KEY" not in out
    assert out.count("\n") == 1  # still exactly one line


# --- REQ-422 / REQ-515: rc-fallback for the default key var when not in env ---
# _read_key_from_rc now takes the var NAME (REQ-515 provider-agnostic resolver).

def test_read_key_from_rc_finds_canonical_form(monkeypatch, tmp_path):
    """Canonical `export VAR="..."` form is extracted from ~/.zshrc."""
    home = tmp_path
    (home / ".zshrc").write_text(
        '# some comment\nexport MOONSHOT_API_KEY="sk-from-zshrc-xyz"\nexport OTHER="x"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == "sk-from-zshrc-xyz"


def test_read_key_from_rc_falls_back_to_bash_profile(monkeypatch, tmp_path):
    """If ~/.zshrc lacks the key, ~/.bash_profile is checked next."""
    home = tmp_path
    (home / ".zshrc").write_text("# no key here\n", encoding="utf-8")
    (home / ".bash_profile").write_text(
        'export MOONSHOT_API_KEY="sk-from-bash-profile"\n', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == "sk-from-bash-profile"


def test_read_key_from_rc_returns_empty_when_no_rc_has_key(monkeypatch, tmp_path):
    """If no rc file contains the export, returns empty string."""
    home = tmp_path
    (home / ".zshrc").write_text("# nothing\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == ""


def test_read_key_from_rc_ignores_indented_export(monkeypatch, tmp_path):
    """Only matches lines starting at column 0 — defensive against partial matches."""
    home = tmp_path
    (home / ".zshrc").write_text(
        '  export MOONSHOT_API_KEY="indented-not-canonical"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == ""


#: Separators `str.splitlines` honours that a shell does not. Text after one of
#: these is still on the same command line for sh, bash and zsh.
_NOT_SHELL_LINE_BREAKS = ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
                          " ", " ")


@pytest.mark.parametrize("sep", _NOT_SHELL_LINE_BREAKS,
                         ids=[repr(s) for s in _NOT_SHELL_LINE_BREAKS])
def test_rc_reader_splits_only_where_a_shell_does(monkeypatch, tmp_path, sep):
    """The rc reader answers "what did the shell export?", so it has to split
    the file the way the shell does.

    `str.splitlines` breaks on eight characters beyond `\\n`/`\\r\\n`/`\\r`, and a
    shell breaks on none of them. So `# note\\x0bexport K="v"` is one COMMENT
    line that never runs — while a `splitlines`-based reader sees two lines, the
    second one canonical, and reports a key the environment does not and will
    never contain. The reader would then hand `get_client` a credential the
    machine never had, and the failure lands on a real call.

    Derived, not asserted from memory: each separator is confirmed to be one
    `str.splitlines` really does honour, so a future Python that adds another
    surfaces as a red row rather than as a value invented out of a comment.
    """
    assert len(("a" + sep + "b").splitlines()) == 2, repr(sep)
    home = tmp_path
    (home / ".zshrc").write_text(
        '# a note about the key' + sep + 'export MOONSHOT_API_KEY="sk-smuggled"\n',
        encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == ""


@pytest.mark.parametrize("eol,label", [("\n", "lf"), ("\r\n", "crlf"),
                                       ("\r", "cr")])
def test_rc_reader_still_reads_a_real_line(monkeypatch, tmp_path, eol, label):
    """The working subject for the test above (LESSON-602).

    An exclusion test passes just as well against a reader that finds nothing at
    all, so the same export on its own line — after each of the three endings a
    shell actually honours — must still be found.
    """
    home = tmp_path
    (home / ".zshrc").write_text(
        '# a note about the key' + eol + 'export MOONSHOT_API_KEY="sk-real"' + eol,
        encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == "sk-real"


def test_provider_source_is_defaults_when_the_config_is_malformed(monkeypatch):
    """`source` is a claim about where the reported values CAME from.

    A malformed config supplies nothing: every field below comes from the
    shipped defaults. But the guard that decides this was written against a
    single `_MALFORMED` sentinel and stayed that way when the reason and the
    path joined it (REQ-609 BR-13) — three keys, only one of them excluded — so
    it answered "config" for every unreadable file, and `--version` named a file
    the loader had just refused to read as the source of values it never
    supplied.
    """
    for var in ("ADLC_DELEGATE_MODEL", "ADLC_DELEGATE_BASE_URL",
                "ADLC_DELEGATE_API_KEY_ENV"):
        monkeypatch.delenv(var, raising=False)
    malformed = {_common._MALFORMED: True,
                 _common._MALFORMED_REASON: "duplicate-key: 'enabled' at line 3",
                 _common._MALFORMED_PATH: "/tmp/config.yml"}
    provider = _common.resolve_provider(cfg=malformed)
    assert provider.source == "defaults", provider
    assert provider.enabled is False

    # Not vacuous: a config that really did supply a field still says "config".
    assert _common.resolve_provider(cfg={"model": "m"}).source == "config"


def test_rc_reader_opens_by_descriptor_and_skips_fifo(monkeypatch, tmp_path):
    """REQ-609 BR-5: the rc reader opens the way the config loader does.

    Both readers open with ``O_RDONLY | O_NONBLOCK`` and decide ``S_ISREG`` on
    ``fstat`` of the descriptor they actually opened. A plain ``open()`` on a
    fifo with no writer blocks forever — and this is the path that resolves an
    API key, so the hang lands on a real call rather than on a probe. A
    ``stat``-then-``open`` pair would not help either: it answers a question
    about whatever was at that name a moment ago.

    A thread and a flag, never ``signal.alarm`` and never a timeout exception:
    ``TimeoutError`` IS an ``OSError``, so the reader's own ``except OSError``
    would swallow the alarm meant to catch the hang and the test would pass on
    exactly the failure it exists to detect.
    """
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    home = tmp_path
    try:
        os.mkfifo(str(home / ".zshrc"))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"mkfifo unavailable here: {exc}")
    # The next candidate holds the key, so "skipped" is distinguishable from
    # "read as empty": the reader must go on and find this.
    (home / ".bash_profile").write_text(
        'export MOONSHOT_API_KEY="sk-past-the-fifo"\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    box = {}
    t = threading.Thread(
        target=lambda: box.setdefault(
            "key", _common._read_key_from_rc("MOONSHOT_API_KEY")))
    t.daemon = True
    t.start()
    t.join(1.0)
    assert not t.is_alive(), "the rc read blocked on the fifo"
    assert box["key"] == "sk-past-the-fifo"


def test_rc_reader_skips_a_directory_and_reads_no_name_by_stat(
        monkeypatch, tmp_path):
    """The other non-regular shapes, and the structural half of BR-5: with
    ``os.stat`` made to explode, the reader still works — because it never
    consults the name, only the descriptor."""
    home = tmp_path
    (home / ".zshrc").mkdir()                      # a directory, not a file
    (home / ".bash_profile").write_text(
        'export MOONSHOT_API_KEY="sk-from-bash-profile"\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    def _forbidden(*a, **kw):
        raise AssertionError("the rc reader must not stat the path by name")

    monkeypatch.setattr(os, "stat", _forbidden)
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == "sk-from-bash-profile"


def test_rc_reader_read_is_bounded(monkeypatch, tmp_path):
    """The rc read is capped. Unlike the config cap this one truncates rather
    than refusing — an rc file is not a governance document — so a key inside
    the cap is still found and the tail is simply not loaded."""
    home = tmp_path
    (home / ".zshrc").write_text(
        'export MOONSHOT_API_KEY="sk-near-the-top"\n'
        + "# pad\n" * (_machine_config.RC_CAP_BYTES // 6 + 100),
        encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _common._read_key_from_rc("MOONSHOT_API_KEY") == "sk-near-the-top"
    assert os.path.getsize(str(home / ".zshrc")) > _machine_config.RC_CAP_BYTES


def test_get_client_uses_env_when_set(monkeypatch, tmp_path):
    """Env var takes precedence over rc-fallback."""
    pytest.importorskip("openai")  # needs the delegate venv (tools/delegate/install.sh)
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
    pytest.importorskip("openai")  # needs the delegate venv (tools/delegate/install.sh)
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
