"""Hermetic CLI tests for tools/kimi/extract-chat."""
import json
import os
import subprocess
import sys

import pytest


SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "extract-chat",
)


def _run(jsonl_path, *extra):
    return subprocess.run(
        [sys.executable, SCRIPT, str(jsonl_path), *extra],
        capture_output=True,
        text=True,
        check=True,
    )


def _write(tmp_path, lines):
    p = tmp_path / "trans.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _line(role, content):
    return json.dumps({"message": {"role": role, "content": content}})


def test_user_text_emitted(tmp_path):
    p = _write(tmp_path, [_line("user", "hello there friend")])
    out = _run(p).stdout
    assert "## Human" in out
    assert "hello there friend" in out


def test_assistant_text_emitted_tool_use_skipped(tmp_path):
    content = [
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "TOOLUSE_PAYLOAD_XYZ"}},
    ]
    p = _write(tmp_path, [_line("assistant", content)])
    out = _run(p).stdout
    assert "## Assistant" in out
    assert "hello" in out
    assert "TOOLUSE_PAYLOAD_XYZ" not in out


def test_tool_result_filtered(tmp_path):
    content = [
        {"type": "tool_result", "content": "TOOLRESULT_PAYLOAD_XYZ"},
    ]
    p = _write(tmp_path, [_line("user", content)])
    out = _run(p).stdout
    assert "TOOLRESULT_PAYLOAD_XYZ" not in out


def test_image_block_filtered(tmp_path):
    content = [
        {"type": "image", "source": {"data": "IMAGE_PAYLOAD_XYZ"}},
    ]
    p = _write(tmp_path, [_line("assistant", content)])
    out = _run(p).stdout
    assert "IMAGE_PAYLOAD_XYZ" not in out


def test_data_uri_string_filtered(tmp_path):
    payload = "data:image/png;base64," + "X" * 50
    p = _write(tmp_path, [_line("user", [payload])])
    out = _run(p).stdout
    assert "data:image/png" not in out
    assert payload not in out


def test_raw_base64_600_chars_filtered(tmp_path):
    payload = "A" * 600
    p = _write(tmp_path, [_line("user", [payload])])
    out = _run(p).stdout
    assert payload not in out


def test_500_char_prose_passes(tmp_path):
    prose = ("hello world " * 42)[:500]
    assert len(prose) == 500
    p = _write(tmp_path, [_line("user", [prose])])
    out = _run(p).stdout
    assert prose in out


def test_malformed_json_skipped(tmp_path):
    lines = [
        _line("user", "valid_line_one"),
        "NOT_JSON_AT_ALL",
        _line("user", "valid_line_two"),
    ]
    p = _write(tmp_path, lines)
    out = _run(p).stdout
    assert "valid_line_one" in out
    assert "valid_line_two" in out


def test_output_file_matches_stdout(tmp_path):
    p = _write(tmp_path, [_line("user", "hello there")])
    stdout_out = _run(p).stdout
    out_file = tmp_path / "x.txt"
    _run(p, "-o", str(out_file))
    assert out_file.read_text(encoding="utf-8") == stdout_out


# --- threshold-boundary + prose-passthrough regression nets ---

def test_raw_base64_511_chars_passes(tmp_path):
    # One char under the threshold: must pass through even though every char
    # is in the base64 alphabet.
    payload = "A" * 511
    p = _write(tmp_path, [_line("user", [payload])])
    out = _run(p).stdout
    assert payload in out


def test_raw_base64_512_chars_filtered(tmp_path):
    # Exactly at the threshold: must be filtered.
    payload = "A" * 512
    p = _write(tmp_path, [_line("user", [payload])])
    out = _run(p).stdout
    assert payload not in out


def test_600_char_prose_with_spaces_passes(tmp_path):
    # 600 chars of letters + spaces. With the (correct) regex this is NOT
    # base64 (spaces fail the fullmatch), so it must pass through. This test
    # protects against the original `\s`-in-regex bug where ordinary prose at
    # >= 512 chars would be silently filtered.
    prose = ("the quick brown fox jumps over the lazy dog " * 20)[:600]
    assert len(prose) == 600
    p = _write(tmp_path, [_line("user", [prose])])
    out = _run(p).stdout
    assert prose in out
