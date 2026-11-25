"""REQ-722 TASK-279: ``adlc harness family``, the implementer's model family.

The family comes from sources the session under review cannot write (ADR-2): the exec
engine's run record when ``ADLC_EXEC_RUN`` is set, else Claude Code's ``CLAUDECODE=1``,
else ``unknown``. Each case runs under the conftest's throwaway ``HOME`` with no
``XDG_STATE_HOME``, so a run record seeded here lives under ``tmp_path`` and the runner's
own exec runs are never read.
"""

import json
import os
import subprocess
import sys

import pytest

import exec_ledger as el
import harness_adapter as ha
import harness_cli
import sprint_exec as se

HERE = os.path.dirname(os.path.abspath(__file__))
ADLC = os.path.join(os.path.dirname(HERE), "adlc.py")
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REQ = "REQ-901"


# --------------------------------------------------------------------------- helpers
def git_repo(path):
    os.makedirs(path)
    subprocess.run(["git", "init", "-q", path], check=True)
    return os.path.realpath(path)


def seed_run(primary, harness, req=REQ, started="2026-11-24T10:00:00Z", **extra):
    """A run directory as ``sprint-exec run`` leaves it: ``run.json`` under the engine's
    state root, naming ``harness`` at the top and in ``exec`` (sprint_exec.py's doc)."""
    path = el.create_run_dir(os.environ)
    doc = {"req": req, "primary": primary, "exec": {"startedAt": started}}
    if harness is not None:
        doc["harness"] = harness
        doc["exec"]["harness"] = harness
    doc.update(extra)
    el.atomic_json(os.path.join(path, el.RUN_RECORD), doc)
    return path


def family(environ, cwd, toolkit=TOOLKIT):
    env = {"HOME": os.environ["HOME"]}
    env.update(environ)
    return harness_cli.implementer_family(env, cwd, toolkit)


def toolkit_with_claude(tmp_path, edit):
    """A toolkit holding only ``harness/claude.yml``, with ``edit`` applied to its text."""
    tk = tmp_path / "tk"
    (tk / "harness").mkdir(parents=True)
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    (tk / "harness" / "claude.yml").write_text(edit(text), encoding="utf-8")
    return str(tk)


def cli(cwd, env):
    base = {"HOME": os.environ["HOME"], "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update(env)
    return subprocess.run([sys.executable, ADLC, "harness", "family"], cwd=cwd, env=base,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=60)


# --------------------------------------------------------------------------- the three arms
def test_exec_run_record_outranks_the_claude_marker(tmp_path):
    """AC: under a seeded run record naming codex, the command prints `openai` even with
    CLAUDECODE=1 set: the engine's record is read first."""
    primary = git_repo(str(tmp_path / "primary"))
    seed_run(primary, "codex")
    res = cli(primary, {"ADLC_EXEC_RUN": REQ, "CLAUDECODE": "1"})
    assert (res.returncode, res.stdout, res.stderr) == (0, "openai\n", "")


def test_the_run_is_found_from_a_working_copy_of_the_primary(tmp_path):
    """The child's cwd is ``<primary>/.worktrees/<req>``; the run is the primary's."""
    primary = git_repo(str(tmp_path / "primary"))
    subprocess.run(["git", "-C", primary, "commit", "-q", "--allow-empty", "-m", "base"],
                   check=True, env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    wc = os.path.join(primary, ".worktrees", REQ)
    subprocess.run(["git", "-C", primary, "worktree", "add", "-q", "--detach", wc], check=True)
    seed_run(primary, "codex")
    assert family({"ADLC_EXEC_RUN": REQ}, wc) == "openai"


def test_the_run_tag_picks_the_run_whatever_the_cwd(tmp_path):
    """With ``ADLC_EXEC_RUN_TAG`` set, the run is the one the engine tagged, not the newest
    run of the REQ in the cwd's repo."""
    primary = git_repo(str(tmp_path / "primary"))
    tagged = seed_run(primary, "codex", started="2026-11-24T09:00:00Z")
    seed_run(primary, "claude", started="2026-11-24T11:00:00Z")
    env = {"ADLC_EXEC_RUN": REQ, se.RUN_TAG_ENV: se.run_tag(tagged)}
    assert family(env, str(tmp_path)) == "openai"
    assert family({"ADLC_EXEC_RUN": REQ}, primary) == "anthropic"


@pytest.mark.parametrize("marker, expected", [
    ("1", "anthropic"), ("0", "unknown"), ("true", "unknown"), ("", "unknown"),
])
def test_claude_marker_without_an_exec_run(tmp_path, marker, expected):
    """AC: CLAUDECODE=1 and no exec run prints `anthropic`; only exactly `1` counts."""
    res = cli(str(tmp_path), {"CLAUDECODE": marker, "CLAUDE_CODE_ENTRYPOINT": "cli"})
    assert (res.returncode, res.stdout) == (0, expected + "\n")


#: Both markers a Claude Code shell carries (REQ-722 Phase 5: one alone is not enough).
CLAUDE_SHELL = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"}


@pytest.mark.parametrize("env", [
    {"CLAUDECODE": "1"},
    {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": ""},
    dict(CLAUDE_SHELL, CODEX_SANDBOX="seatbelt"),
    dict(CLAUDE_SHELL, CODEX_SANDBOX_NETWORK_DISABLED="1"),
], ids=["lone-claudecode", "empty-entrypoint", "codex-child", "codex-child-no-network"])
def test_an_inherited_or_lone_claude_marker_reads_unknown(tmp_path, env):
    """Phase-5 security fix: a Claude Code shell passes its markers on, so a lone CLAUDECODE,
    or both markers beside another harness's own marker, is not a claim of `anthropic`."""
    res = cli(str(tmp_path), env)
    assert (res.returncode, res.stdout) == (0, "unknown\n")


@pytest.mark.parametrize("extra", [
    {"CODEX_SANDBOX": ""}, {"CODEX_HOME": "/x/.codex"}, {"CURSOR_TRACE_ID": "abc"},
    {"COPILOT_AGENT": "1"},
], ids=["empty-codex-sandbox", "codex-home", "cursor-terminal", "copilot-var"])
def test_both_claude_markers_and_a_config_variable_read_anthropic(tmp_path, extra):
    """Must-not-fire: an empty child marker, or a configuration or terminal variable of
    another harness, does not veto (it says nothing about which harness runs this)."""
    res = cli(str(tmp_path), dict(CLAUDE_SHELL, **extra))
    assert (res.returncode, res.stdout) == (0, "anthropic\n")


def test_neither_source_prints_unknown(tmp_path):
    res = cli(str(tmp_path), {})
    assert (res.returncode, res.stdout, res.stderr) == (0, "unknown\n", "")


# --------------------------------------------------------------------------- BR-3
def _no_record(tmp_path, primary):
    return {}


def _record_of_another_req(tmp_path, primary):
    seed_run(primary, "codex", req="REQ-902")
    return {}


def _record_of_another_repo(tmp_path, primary):
    seed_run(git_repo(str(tmp_path / "other")), "codex")
    return {}


def _record_without_a_harness(tmp_path, primary):
    seed_run(primary, None)
    return {}


def _record_naming_an_unshipped_harness(tmp_path, primary):
    seed_run(primary, "fake")
    return {}


def _record_that_is_not_json(tmp_path, primary):
    path = seed_run(primary, "codex")
    with open(os.path.join(path, el.RUN_RECORD), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    return {}


def _a_tag_no_run_carries(tmp_path, primary):
    seed_run(primary, "codex")
    return {se.RUN_TAG_ENV: "0" * 32}


def _a_tag_of_another_reqs_run(tmp_path, primary):
    return {se.RUN_TAG_ENV: se.run_tag(seed_run(primary, "codex", req="REQ-902"))}


@pytest.mark.parametrize("arrange", [
    _no_record, _record_of_another_req, _record_of_another_repo, _record_without_a_harness,
    _record_naming_an_unshipped_harness, _record_that_is_not_json, _a_tag_no_run_carries,
    _a_tag_of_another_reqs_run,
], ids=lambda f: f.__name__.strip("_"))
def test_unestablished_implementer_is_unknown(tmp_path, arrange):
    """BR-3: a set ADLC_EXEC_RUN with no readable record of that run is `unknown`. It never
    falls through to CLAUDECODE, which the session could set in its own shell."""
    primary = git_repo(str(tmp_path / "primary"))
    env = {"ADLC_EXEC_RUN": REQ, "CLAUDECODE": "1"}
    env.update(arrange(tmp_path, primary))
    assert family(env, primary) == "unknown"


def test_a_forged_exec_marker_prints_unknown(tmp_path):
    """The command, end to end: a marker no engine set, beside CLAUDECODE=1."""
    res = cli(str(tmp_path), {"ADLC_EXEC_RUN": REQ, "CLAUDECODE": "1"})
    assert (res.returncode, res.stdout) == (0, "unknown\n")


def test_a_failure_is_unknown_with_one_stderr_line(monkeypatch, capsys):
    def broken(*_a):
        raise ha.AdapterError("x", "model_family", "boom")
    monkeypatch.setattr(harness_cli, "implementer_family", broken)
    assert harness_cli.main(["family"]) == 0
    out, err = capsys.readouterr()
    assert out == "unknown\n"
    assert len(err.splitlines()) == 1 and "reading unknown" in err


# --------------------------------------------------------------------------- BR-2
def test_family_never_inferred_from_harness_name_alone(tmp_path):
    """BR-2: the family is what the adapter declares. The `claude` name with no declaration
    reads `unknown`, a declaration of another family is taken as declared, and a harness that
    can run Anthropic models (copilot) reads its own declaration, `unknown`."""
    def drop(text):
        lines = [ln for ln in text.split("\n") if not ln.startswith("model_family:")]
        assert len(lines) == len(text.split("\n")) - 1
        return "\n".join(lines)
    undeclared = toolkit_with_claude(tmp_path / "a", drop)
    assert family(CLAUDE_SHELL, str(tmp_path), undeclared) == "unknown"
    other = toolkit_with_claude(tmp_path / "b", lambda t: t.replace(
        "model_family: anthropic", "model_family: openai"))
    assert family(CLAUDE_SHELL, str(tmp_path), other) == "openai"
    primary = git_repo(str(tmp_path / "primary"))
    seed_run(primary, "copilot")
    assert family({"ADLC_EXEC_RUN": REQ}, primary) == "unknown"


# --------------------------------------------------------------------------- LESSON-718
_AUDIT = r'''
import json, os, runpy, sys
watch = os.path.realpath(sys.argv[1])
adlc = sys.argv[2]
seen, busy = [], []
def hook(event, args):
    if busy or event not in ("open", "os.listdir", "os.scandir") or not args:
        return
    path = args[0]
    if not isinstance(path, (str, bytes)):
        return
    busy.append(1)
    try:
        path = os.fsdecode(path)
        seen.append(os.path.realpath(os.path.join(os.getcwd(), path)))
    finally:
        busy.pop()
sys.addaudithook(hook)
sys.argv = [adlc, "harness", "family"]
try:
    runpy.run_path(adlc, run_name="__main__")
except SystemExit:
    pass
sys.stdout.flush()
hits = [p for p in seen if p == watch or p.startswith(watch + os.sep)]
sys.stderr.write("AUDIT " + json.dumps({"hits": hits, "opens": len(seen)}) + "\n")
'''


@pytest.mark.parametrize("exec_run", [False, True], ids=["claude-marker", "exec-run"])
def test_family_never_reads_the_worktrees_adlc(tmp_path, exec_run):
    """AC (LESSON-718): adapters come from the installed toolkit. A forged adapter and a
    forged run record under the current worktree's `.adlc/` are never opened, and every
    file open the command makes is audited for it."""
    primary = git_repo(str(tmp_path / "primary"))
    forged = os.path.join(primary, ".adlc")
    os.makedirs(os.path.join(forged, "harness"))
    src = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    with open(os.path.join(forged, "harness", "claude.yml"), "w", encoding="utf-8") as fh:
        fh.write(src.replace("model_family: anthropic", "model_family: openai"))
    with open(os.path.join(forged, el.RUN_RECORD), "w", encoding="utf-8") as fh:
        json.dump({"req": REQ, "primary": primary, "harness": "codex"}, fh)
    env = {"HOME": os.environ["HOME"], "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"}
    if exec_run:
        seed_run(primary, "claude")
        env["ADLC_EXEC_RUN"] = REQ
    driver = tmp_path / "audit.py"
    driver.write_text(_AUDIT, encoding="utf-8")
    res = subprocess.run([sys.executable, "-I", str(driver), forged, ADLC], cwd=primary,
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, timeout=60)
    assert res.stdout == "anthropic\n", res.stderr
    audit = json.loads(res.stderr.split("AUDIT ", 1)[1])
    assert audit["opens"] > 0
    assert audit["hits"] == []

