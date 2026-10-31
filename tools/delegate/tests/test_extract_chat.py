"""Hermetic CLI tests for tools/delegate/extract-chat."""
import importlib.util
import json
import os
import re
import subprocess
import sys

import pytest


SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "extract-chat",
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "transcripts")
CLAUDE_JSONL = os.path.join(FIXTURES, "claude.jsonl")
CLAUDE_EXPECTED = os.path.join(FIXTURES, "claude.expected.txt")
CLAUDE_PROVENANCE = os.path.join(FIXTURES, "claude.provenance.md")

FORMATS = ("claude", "codex", "copilot", "gemini", "cursor", "antigravity")
UNPROVEN_FORMATS = ("codex", "copilot", "gemini", "cursor", "antigravity")


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


# --- REQ-660: --format, the record-type filter and the real claude fixture ---

def _raw(*argv):
    """Run the CLI undecoded and unchecked: byte-exact goldens, and refusals."""
    return subprocess.run([sys.executable, SCRIPT, *argv],
                          capture_output=True, check=False)


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _fixture_blocks(block_type):
    """Every content block of `block_type` in the real fixture."""
    blocks = []
    for line in _read_text(CLAUDE_JSONL).splitlines():
        content = json.loads(line)["message"]["content"]
        if isinstance(content, list):
            blocks += [b for b in content if b.get("type") == block_type]
    return blocks


def test_claude_golden_default_format():
    r = _raw(CLAUDE_JSONL)
    assert r.returncode == 0, r.stderr
    assert r.stdout == _read_bytes(CLAUDE_EXPECTED)


def test_claude_golden_explicit_format():
    r = _raw("--format", "claude", CLAUDE_JSONL)
    assert r.returncode == 0, r.stderr
    assert r.stdout == _read_bytes(CLAUDE_EXPECTED)


def test_claude_output_has_no_tool_markers():
    tool_uses = _fixture_blocks("tool_use")
    tool_results = _fixture_blocks("tool_result")
    assert tool_uses and tool_results, "the fixture must exercise a tool round trip"

    out = _raw("--format", "claude", CLAUDE_JSONL).stdout.decode("utf-8")
    assert "## Human" in out
    assert "## Assistant" in out

    markers = ["tool_use", "tool_result"]
    markers += [b["id"] for b in tool_uses]
    markers += [b["input"]["description"] for b in tool_uses]
    markers += [b["tool_use_id"] for b in tool_results]
    for marker in markers:
        assert marker not in out, marker
    # The prompt quotes the result text, so its one copy there is expected and
    # any further copy came from the tool call or its result.
    for block in tool_results:
        assert out.count(block["content"]) == 1, block["content"]


def test_format_bogus_names_values(tmp_path):
    target = tmp_path / "out.txt"
    r = _raw("--format", "bogus", CLAUDE_JSONL, "-o", str(target))
    assert r.returncode != 0
    stderr = r.stderr.decode("utf-8")
    for name in FORMATS:
        assert name in stderr, stderr
    assert not target.exists()


@pytest.mark.parametrize("fmt", UNPROVEN_FORMATS)
def test_unproven_formats_refuse(fmt, tmp_path):
    target = tmp_path / "out.txt"
    r = _raw("--format", fmt, CLAUDE_JSONL, "-o", str(target))
    assert r.returncode != 0
    assert r.stdout == b""
    lines = r.stderr.decode("utf-8").splitlines()
    assert len(lines) == 1, lines
    assert "--format %s has no parser" % fmt in lines[0]
    assert "no real %s transcript" % fmt in lines[0]
    assert not target.exists()


@pytest.mark.parametrize("fmt", UNPROVEN_FORMATS)
def test_unproven_format_refuses_before_opening_the_input(fmt, tmp_path):
    r = _raw("--format", fmt, str(tmp_path / "no-such.jsonl"))
    assert r.returncode != 0
    stderr = r.stderr.decode("utf-8")
    assert "has no parser" in stderr, stderr
    assert "cannot open" not in stderr, stderr


def test_unproven_format_leaves_an_existing_output_file_alone(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("KEEP_ME", encoding="utf-8")
    r = _raw("--format", "codex", CLAUDE_JSONL, "-o", str(target))
    assert r.returncode != 0
    assert target.read_text(encoding="utf-8") == "KEEP_ME"


def test_format_value_is_not_read_as_a_version_request():
    r = _raw(CLAUDE_JSONL, "--format", "-V")
    assert r.returncode == 2, r.stdout
    assert not r.stdout.startswith(b"adlc-toolkit"), r.stdout


def test_version_alongside_format_still_prints_the_version():
    r = _raw("--format", "claude", "--version")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith(b"adlc-toolkit"), r.stdout


def _typed_record(rtype, text):
    return json.dumps({
        "type": rtype,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    })


@pytest.mark.parametrize("rtype", ["api-request-blob", "attachment", ["not-a-string"]],
                         ids=["api-request-blob", "attachment", "unhashable"])
def test_harness_internal_record_is_dropped(rtype, tmp_path):
    p = _write(tmp_path, [_typed_record(rtype, "INJECTED_CONTEXT_XYZ")])
    assert _run(p).stdout == ""


def test_harness_internal_record_does_not_cost_its_neighbours(tmp_path):
    p = _write(tmp_path, [
        _typed_record("api-request-blob", "INJECTED_CONTEXT_XYZ"),
        _typed_record("user", "the real prompt"),
    ])
    assert _run(p).stdout == "## Human\nthe real prompt\n"


def test_record_with_no_type_still_parses(tmp_path):
    record = {"message": {"role": "user",
                          "content": [{"type": "text", "text": "no type here"}]}}
    p = _write(tmp_path, [json.dumps(record)])
    assert _run(p).stdout == "## Human\nno type here\n"


# --- BR-11: what a committed fixture may not hold ---------------------------

def _load_credential_redact():
    """The toolkit's one Python copy of the credential chains, by path."""
    path = os.path.join(REPO_ROOT, "tools", "adlc", "credential_redact.py")
    spec = importlib.util.spec_from_file_location("adlc_credential_redact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURE_SCANS = (
    ("credential", _load_credential_redact().INTAKE_PATTERN),  # the REQ-415 five
    ("home path", re.compile(r"/Users/|/home/")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
)


@pytest.mark.parametrize("path", [CLAUDE_JSONL, CLAUDE_EXPECTED, CLAUDE_PROVENANCE],
                         ids=os.path.basename)
def test_fixture_holds_no_credential_home_path_or_email(path):
    text = _read_text(path)
    assert text.strip(), path
    for label, pattern in FIXTURE_SCANS:
        hit = pattern.search(text)
        # The offset, not the match: a failure here must not print the secret.
        assert hit is None, "%s at offset %d of %s" % (
            label, hit.start(), os.path.basename(path))


# Assembled at runtime so this file never holds a literal of a scanned shape.
@pytest.mark.parametrize("sample", [
    "sk-" + "a" * 24,
    "AKIA" + "A" * 16,
    "ghp_" + "a" * 36,
    "Bearer " + "a" * 24,
    "SERVICE" + "_TOKEN=" + "abc",
    "SERVICE" + "_API_KEY: " + "abc",
    "/Users/" + "someone/x",
    "/home/" + "someone/x",
    "someone" + "@" + "example.invalid",
], ids=["sk", "akia", "ghp", "bearer", "token", "api-key", "users", "home", "email"])
def test_fixture_scan_detects_each_shape(sample):
    assert any(pattern.search(sample) for _, pattern in FIXTURE_SCANS), sample


def test_provenance_names_a_harness_version_and_capture_date():
    text = _read_text(CLAUDE_PROVENANCE)
    assert re.search(r"^- \*\*Harness:\*\* .*\b\d+\.\d+\.\d+\b", text, re.M), text
    assert re.search(r"^- \*\*Captured:\*\* \d{4}-\d{2}-\d{2}\b", text, re.M), text
