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
