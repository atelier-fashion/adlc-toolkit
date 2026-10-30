"""REQ-660 ADR-4, BR-6, BR-8: the partial's detection table and its one seam.

`partials/session-record.sh` runs at session start with POSIX sh and python3 stdlib,
so it cannot read `harness/*.yml`. It embeds the table instead, and these tests hold
the copy equal to the adapter it came from. The behaviour of the partial lives in
`partials/tests/hooks.test.sh`; the one run here crosses into Python because it is
`harness_render.hook_args`, not a hand-typed string, that spells the arguments.

Every run writes under ``tmp_path``, with HOME and ADLC_HOME pointing there.
"""

import json
import os
import re
import subprocess

import pytest

import harness_adapter as ha
import harness_render as hr

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PARTIAL = os.path.join(TOOLKIT, "partials", "session-record.sh")
GOLDEN = os.path.join(TOOLKIT, "harness", "claude", "rendered", "settings.json")
FAKE_YML = os.path.join(HERE, "fixtures", "harness", "fake.yml")
SOURCE_LINE = (
    'if [ -f .adlc/partials/session-record.sh ]; then . .adlc/partials/session-record.sh; '
    'else . "$ADLC_TOOLKIT_ROOT/partials/session-record.sh"; fi'
)


def partial_text():
    with open(PARTIAL, encoding="utf-8") as fh:
        return fh.read()


def table():
    rows = re.findall(r"^TABLE = (.*)$", partial_text(), re.MULTILINE)
    assert len(rows) == 1, "the table stays on one line"
    return json.loads(rows[0])


def adapter(name):
    return ha.load_adapter(os.path.join(ha.adapters_dir(TOOLKIT), name + ".yml"), toolkit=TOOLKIT)


def declared(payload_map):
    return {item: key for item, key in payload_map.items() if key != "unsupported"}


def payload_columns(row):
    return {item: row[item] for item in ha.PAYLOAD_ITEMS if item in row}


def test_claude_row_equals_hook_payload():
    assert payload_columns(table()["claude"]) == adapter("claude")["hook_payload"]


def test_claude_row_marker_is_the_transcript_root():
    assert table()["claude"]["marker"] == "/.claude/projects/"


def test_every_row_has_an_adapter_declaring_its_fields():
    """OQ-1: a row and its hook_payload map arrive together, from a captured payload."""
    for name, row in table().items():
        assert declared(payload_columns(row)) == declared(adapter(name)["hook_payload"])


@pytest.mark.parametrize("name", ["copilot", "cursor"])
def test_a_reader_of_the_shared_render_has_a_row_once_its_adapter_declares_one(name):
    if name not in adapter("claude")["paths"]["hooks"]["read_by"]:
        pytest.fail("%s no longer reads the shared render: update this test" % name)
    if not os.path.exists(os.path.join(ha.adapters_dir(TOOLKIT), name + ".yml")):
        pytest.skip("harness/%s.yml has not landed" % name)
    fields = declared(adapter(name)["hook_payload"])
    if not fields:
        pytest.skip("harness/%s.yml declares every field unsupported" % name)
    rows = table()
    assert name in rows, (
        "harness/%s.yml declares payload fields but the partial has no row: add one to "
        "TABLE from a captured payload (REQ-660 OQ-1)" % name)
    assert declared(payload_columns(rows[name])) == fields


def test_rendered_command_names_the_partial():
    with open(GOLDEN, encoding="utf-8") as fh:
        doc = json.load(fh)
    groups = [g for g in doc["hooks"]["SessionStart"] if g.get("matcher") == "startup|resume|clear"]
    assert len(groups) == 1
    commands = [h["command"] for h in groups[0]["hooks"]
                if h["command"].splitlines()[-1] == "adlc_session_record"]
    assert len(commands) == 1, "one hook command, one entry"
    assert SOURCE_LINE in commands[0].splitlines()
    # The golden's body is the template's, so the partial stays the only seam.
    hooks = {h["id"]: h for h in ha.load_hooks(ha.hooks_path(TOOLKIT))}
    assert commands[0] == hooks["session-record"]["command"].rstrip("\n")


def test_the_function_the_command_calls_is_the_one_the_partial_defines():
    assert re.search(r"^adlc_session_record\(\) \{$", partial_text(), re.MULTILINE)


def new_project(tmp_path):
    project = tmp_path / "project"
    (project / ".adlc").mkdir(parents=True)
    return project


def run_partial(tmp_path, project, tail, payload):
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "ADLC_HOME": str(home / ".claude"), "PATH": os.environ["PATH"]}
    script = '. "$1"; adlc_session_record' + tail
    return subprocess.run(["sh", "-c", script, "sh", PARTIAL], cwd=str(project), env=env,
                          input=json.dumps(payload), capture_output=True, text=True, timeout=8)


def test_hook_args_are_what_the_partial_reads(tmp_path):
    """REQ-657 ADR-10's tail, spelled by the renderer, for an adapter with its own hook file."""
    tail = hr.hook_args(ha.load_adapter(FAKE_YML, toolkit=TOOLKIT))
    assert tail == " --harness fake --field session_id=sessionId --field cwd=cwd"
    project = new_project(tmp_path)
    proc = run_partial(tmp_path, project, tail, {
        "sessionId": "T-9", "session_id": "not-this-one", "cwd": "/work/tree",
        "transcript_path": "/not/read"})
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
    lines = (project / ".adlc" / ".session" / "T-9").read_text(encoding="utf-8").splitlines()
    assert lines[:4] == ["harness=unknown", "session_id=T-9", "transcript_path=", "cwd=/work/tree"]
    assert lines[4].startswith("started_at=") and len(lines) == 5


def test_a_fifo_at_the_sidecar_path_does_not_block(tmp_path):
    """BR-5. Here, not in hooks.test.sh, because a regression hangs and sh has no portable bound."""
    project = new_project(tmp_path)
    session = project / ".adlc" / ".session"
    session.mkdir()
    os.mkfifo(str(session / "s1"))
    proc = run_partial(tmp_path, project, "", {"session_id": "s1"})
    assert proc.returncode == 0
    assert (session / "s1").is_file()


def test_the_harness_names_agree_across_the_three_surfaces():
    """One set, four spellings: the partial's enum, discovery's enum and extract-chat's."""
    record = re.search(r'^HARNESSES = \((.*)\)$', partial_text(), re.MULTILINE).group(1)
    names = set(re.findall(r'"([a-z]+)"', record)) - {"unknown"}
    with open(os.path.join(TOOLKIT, "partials", "session-transcript.sh"), encoding="utf-8") as fh:
        discovery = re.search(r'^\s+(claude\|[a-z|]+)\) ;;$', fh.read(), re.MULTILINE).group(1)
    with open(os.path.join(TOOLKIT, "tools", "delegate", "extract-chat"), encoding="utf-8") as fh:
        formats = re.search(r'^FORMATS = \((.*?)\)$', fh.read(), re.MULTILINE | re.DOTALL).group(1)
    assert names == set(discovery.split("|")) == set(re.findall(r'"([a-z]+)"', formats))
