"""REQ-658: the Antigravity CLI adapter.

Every case that writes runs in a sandbox: HOME and ADLC_HOME point under ``tmp_path``, and
projects are throwaway git repos. No case runs a real ``agy``: the binary on PATH, where one
is needed, is a stub. The real-tool evidence is `.adlc/research/antigravity-compatibility.md`.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import pytest

import agents_render
import harness_adapter as ha
import harness_doctor
import harness_render as hr

HERE = os.path.dirname(os.path.abspath(__file__))
ADLC = os.path.join(os.path.dirname(HERE), "adlc.py")
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ADAPTER = os.path.join(TOOLKIT, "harness", "antigravity.yml")
NOTE = os.path.join(TOOLKIT, ".adlc", "research", "antigravity-compatibility.md")
SPEC = os.path.join(TOOLKIT, ".adlc", "specs", "REQ-658-gemini-cli-adapter", "requirement.md")
RESULT = os.path.join(TOOLKIT, ".adlc", "research", "harness-probes", "antigravity.json")
FIXTURE = os.path.join(TOOLKIT, ".adlc", "research", "harness-probes", "fixtures",
                       "antigravity.jsonl")
SYSTEM_PATH = "/usr/bin:/bin"
SURFACES = ("settings", "permissions", "project-config", "hooks", "hook-output", "skills",
            "agents", "rules", "plugins", "trust", "transcripts", "exit-codes")
OMITTED = ("git push", "git branch", "git -C")
_NOTE_ROW = re.compile(r"^\| ([a-z-]+) \| (inspection|docs|probe) \| ([0-9.]+) \| (.+?) \| "
                       r"(usable|unusable|unverified) \| (.+) \|$", re.MULTILINE)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ADLC_HOME", str(home / ".claude"))
    monkeypatch.setenv("PATH", SYSTEM_PATH)
    return tmp_path


def adapter():
    return ha.load_adapter(ADAPTER, toolkit=TOOLKIT)


def perms():
    return ha.load_permissions(ha.permissions_path(TOOLKIT))


def hooks():
    return ha.load_hooks(ha.hooks_path(TOOLKIT))


def result():
    return hr.load_result_file(RESULT)


def printed():
    rules, findings, extras = hr.render_permissions(adapter(), perms(), "printed", result())
    return rules, findings, json.loads(hr.format_action_rules(rules, extras, None))


def variant(tmp_path, edits):
    """A copy of the adapter with ``edits`` applied, same basename."""
    src = open(ADAPTER, encoding="utf-8").read()
    for old, new in edits:
        assert old in src, old
        src = src.replace(old, new, 1)
    d = tmp_path / ("v%d" % len(list(tmp_path.glob("v*"))))
    d.mkdir()
    path = d / "antigravity.yml"
    path.write_text(src, encoding="utf-8")
    return str(path)


def run_cli(args, cwd, path=None):
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
           "PATH": path or SYSTEM_PATH, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, ADLC] + list(args), cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=120)


def git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def stub_agy(tmp_path):
    """An `agy` that logs each call, so a test can show `agy plugin` never ran."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / "agy"
    log = tmp_path / "agy.log"
    tool.write_text('#!/bin/sh\necho "$*" >> %s\necho 1.4.12\n' % shlex.quote(str(log)))
    tool.chmod(0o755)
    return "%s:%s" % (bin_dir, SYSTEM_PATH), log


def user_path(rel):
    return os.path.join(os.environ["HOME"], rel)


# --------------------------------------------------------------------------- BR-1
def note_rows():
    return _NOTE_ROW.findall(open(NOTE, encoding="utf-8").read())


def test_note_has_every_row():
    rows = note_rows()
    assert {r[0] for r in rows} == set(SURFACES)
    assert {r[2] for r in rows} == {"1.4.12"}
    text = open(NOTE, encoding="utf-8").read()
    assert "## The route" in text
    assert all(r[3].strip() and r[5].strip() for r in rows)


def test_no_usable_row_from_docs_alone():
    bad = [r[3] for r in note_rows() if r[1] == "docs" and r[4] != "unverified"]
    assert bad == []
    assert any(r[1] == "docs" for r in note_rows())


def test_every_note_row_shape_is_read():
    """The row reader above must not skip a row it cannot parse, or the two tests before
    this one would pass over it."""
    text = open(NOTE, encoding="utf-8").read()
    body = text.split("## Compatibility")[1].split("## The route")[0]
    table = [ln for ln in body.splitlines() if ln.startswith("| ") and not ln.startswith(
        "| Surface")]
    assert len(table) == len(note_rows())


def test_result_is_scrubbed():
    """BR-3: no email, login or account id. The login is read from the record itself, so
    this holds on any machine: a home path would have been rewritten to `~`."""
    for path in (RESULT, FIXTURE):
        text = open(path, encoding="utf-8").read()
        assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", text), path
        assert "/Users/" not in text and "/home/" not in text, path
        assert not re.search(r'creator_(user|account)_id\\*"\s*:\s*\\*"[^"\[]', text), path


def test_result_has_a_verdict_per_probe():
    data = result()
    assert data["harness"] == "antigravity" and data["harness_version"] == "1.4.12"
    for pid, entry in data["probes"].items():
        assert entry["status"] in ("pass", "fail", "unknown", "n/a"), pid
        if entry["status"] in ("n/a", "unknown"):
            assert entry.get("reason"), pid
    assert data["probes"]["git-write-worktree"]["status"] == "pass"


# --------------------------------------------------------------------------- BR-5
def test_no_harness_name_in_code():
    """BR-5: the two tables and the blocked path, nothing else in `tools/adlc`."""
    allowed = {"harness.py", "harness_probe.py"}
    found = []
    root = os.path.join(TOOLKIT, "tools", "adlc")
    for name in sorted(os.listdir(root)):
        if name.endswith(".py") and name not in allowed:
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if re.search(r"antigravity|\bagy\b", line):
                        found.append("%s:%d" % (name, number))
    assert found == []
    table = [ln for ln in open(os.path.join(root, "harness.py"), encoding="utf-8")
             if re.search(r"antigravity|\bagy\b", ln)]
    assert len(table) == 1 and '("antigravity", ("agy",), "skills-config")' in table[0]


def test_other_adapters_are_not_edited():
    out = subprocess.run(["git", "-C", TOOLKIT, "diff", "--name-only", "origin/main", "--",
                          "harness/claude.yml", "harness/copilot.yml", "harness/cursor.yml",
                          "harness/codex.yml"], capture_output=True, text=True)
    if out.returncode:
        pytest.skip("no origin/main here")
    assert out.stdout == ""


def test_loader_refusals(tmp_path, sandbox):
    assert adapter()["schema_version"] == 4
    bad = variant(tmp_path, [("name: antigravity\n", "name: antigravity\nworking_copy: x\n")])
    with pytest.raises(ha.AdapterError, match="working_copy"):
        ha.load_adapter(bad, toolkit=TOOLKIT)
    bad = variant(tmp_path, [("sandbox_can_reach_common_gitdir: true\n", "")])
    with pytest.raises(ha.AdapterError, match="sandbox_can_reach_common_gitdir"):
        ha.load_adapter(bad, toolkit=TOOLKIT)
    bad = variant(tmp_path, [("sandbox_can_reach_common_gitdir: true\n",
                              "sandbox_can_reach_common_gitdir: unverified\n")])
    status, detail, _remedy = harness_doctor.render_currency("antigravity", bad, TOOLKIT)
    assert status == "FAIL" and "sandbox_can_reach_common_gitdir" in detail


@pytest.mark.parametrize("old, new, words", [
    ('hook_cwd: ".."\n', 'hook_cwd: ../.agents\n', "hook_cwd"),
    ('hook_cwd: ".."\n', 'hook_cwd: "cd /; x"\n', "hook_cwd"),
    ("'{\"injectSteps\":[{\"systemMessage\":%s}]}'", "'{\"a\":%d}'", "%s"),
    ("'{\"injectSteps\":[{\"systemMessage\":%s}]}'", "'{\"a\":%s'", "not JSON"),
    ("  ethos-inject: json:systemMessage\n", "", "hook_output"),
])
def test_hook_fields_are_refused_when_malformed(tmp_path, old, new, words):
    with pytest.raises(ha.AdapterError, match=re.escape(words)):
        ha.load_adapter(variant(tmp_path, [(old, new)]), toolkit=TOOLKIT)


@pytest.mark.parametrize("addition, field", [
    ('hook_cwd: ".."\n', "hook_cwd"),
    ("hook_output_envelope:\n  ethos-inject: '{\"a\":%s}'\n", "hook_output_envelope"),
    ('  fence_unmatchable: "yes"\n', "fence_unmatchable"),
])
def test_schema_4_fields_are_refused_under_schema_3(tmp_path, addition, field):
    """On Codex's adapter, schema 3, so the field itself is what gets refused."""
    src = open(os.path.join(TOOLKIT, "harness", "codex.yml"), encoding="utf-8").read()
    assert src.rstrip().splitlines()[-1].startswith("  fence_broad_spelling")
    path = tmp_path / "codex.yml"
    path.write_text(src + addition, encoding="utf-8")
    with pytest.raises(ha.AdapterError, match=r"%s.*schema_version 4" % field):
        ha.load_adapter(str(path), toolkit=TOOLKIT)


def test_a_rendered_skills_surface_needs_schema_4(tmp_path):
    src = open(ADAPTER, encoding="utf-8").read()
    src = src.replace('hook_cwd: ".."\n', "")
    src = re.sub(r"hook_output_envelope:\n  .*\n", "", src)
    src = src.replace('  fence_unmatchable: "yes"\n', "  fence_broad_spelling: [if, x]\n")
    d = tmp_path / "plain"
    d.mkdir()
    path = d / "antigravity.yml"
    path.write_text(src.replace("schema_version: 4\n", "schema_version: 3\n"), encoding="utf-8")
    with pytest.raises(ha.AdapterError, match=r"paths\.skills\.mode"):
        ha.load_adapter(str(path), toolkit=TOOLKIT)


def test_earlier_adapters_stay_below_schema_4():
    for name, version in (("copilot", 2), ("cursor", 2), ("codex", 3)):
        data = ha.load_adapter(os.path.join(TOOLKIT, "harness", name + ".yml"), toolkit=TOOLKIT)
        assert data["schema_version"] == version
        assert not {"hook_cwd", "hook_output_envelope"} & set(data)


# --------------------------------------------------------------------------- BR-6
def test_render_holds_rule_b():
    rules, findings, doc = printed()
    allow = doc["permissions"]["allow"]
    deny = doc["permissions"]["deny"]
    assert list(doc) == ["permissions"], "a user-level agentMode reaches every project"
    assert "ask" not in doc["permissions"]
    for e in perms()["entries"]:
        if e["tier"] != "deny":
            continue
        for command in e["commands"]:
            text = " ".join(command)
            assert "command(%s)" % text not in allow, text
            assert "command(%s)" % text in deny, text
    for gone in OMITTED:
        assert "command(%s)" % gone not in allow
        assert any(f.command == gone and f.verdict == "inexpressible" for f in findings)
    assert all(not r.startswith("command(if") and not r.startswith("command(sh)") for r in allow)
    assert hr.fidelity(adapter(), perms(), result())[1] == []


def test_no_fence_rule_is_rendered_and_no_remedy_promises_one():
    """The note's fence row: no rule matches, so a rule would be inert (LESSON-757)."""
    _rules, findings, extras = hr.render_permissions(adapter(), perms(), "printed", result())
    fence = [f for f in findings if f.entry == hr.FENCE_ID]
    assert [f.verdict for f in fence] == ["inexpressible"]
    assert extras["remedies"] == []


def test_a_dangerous_flag_appears_only_where_it_is_refused():
    """AC-6: no code or adapter names it. The tests name it to ban it from every launch."""
    grep = subprocess.run(["grep", "-rn", "dangerously-skip-permissions",
                           os.path.join(TOOLKIT, "tools", "adlc"), ADAPTER],
                          capture_output=True, text=True)
    assert [ln for ln in grep.stdout.splitlines() if "/tests/" not in ln] == []


def test_rm_fixture_is_omitted(tmp_path):
    """AC-6: a routine `rm` prefixes `rm -rf`, so it is omitted by the computed rule, and
    the lint names the key it needs."""
    src = open(ha.permissions_path(TOOLKIT), encoding="utf-8").read()
    entry = ("  - id: fixture.rm\n    tier: routine\n    note: a routine rm\n    commands:\n"
             "      - [rm]\n")
    fixture = tmp_path / "permissions.yml"
    fixture.write_text(src.replace("entries:\n", "entries:\n" + entry, 1), encoding="utf-8")
    loaded = ha.load_permissions(str(fixture))
    rules, findings, _extras = hr.render_permissions(adapter(), loaded, "printed", result())
    assert not any(r.kind == "allow" and r.spelling == ("rm",) for r in rules)
    assert any(f.command == "rm" and "would wrap deny-tier" in f.detail for f in findings)
    _found, failures = hr.fidelity(adapter(), loaded, result())
    assert any("fixture.rm [rm]" in msg for msg in failures)


@pytest.mark.parametrize("key", ['"git.write:git push"', "fence.partial-source",
                                 '"npm.ci:npm ci"'])
def test_removing_a_declared_loss_fails_the_lint(tmp_path, key):
    src = open(ADAPTER, encoding="utf-8").read()
    line = next(ln for ln in src.splitlines() if ln.startswith("  " + key + ":"))
    path = variant(tmp_path, [(line + "\n", "")])
    _found, failures = hr.fidelity(ha.load_adapter(path, toolkit=TOOLKIT), perms(), result())
    assert any(key.strip('"').split(":")[0] in msg for msg in failures), failures


def test_project_render_writes_no_permission_file(sandbox):
    """What `/init --harness antigravity` runs: no permission file, and no `agy plugin`."""
    path, log = stub_agy(sandbox)
    project = git_repo(sandbox / "proj")
    out = run_cli(["harness", "render", "--harness", "antigravity"], project, path)
    assert out.returncode == 0, out.stderr
    assert "plugin" not in (log.read_text() if log.exists() else "")
    assert "printed permissions" in out.stdout
    assert sorted(os.listdir(project / ".agents")) == ["hooks.json"]
    assert not (project / ".gemini").exists()
    assert "command(git status)" in out.stdout and "agentMode" not in out.stdout


def test_parity_fails_on_one_changed_byte(tmp_path):
    """AC-13: each golden this adapter owns is held, to the byte, skills.json included,
    whose real render differs per machine."""
    tk = tmp_path / "tk"
    for d in ("harness", "templates", "agents", ".claude", "partials"):
        shutil.copytree(os.path.join(TOOLKIT, d), str(tk / d),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    assert all(r[3] == "in-parity" for r in hr.parity(str(tk)))
    rendered = tk / "harness" / "antigravity" / "rendered"
    assert sorted(os.listdir(rendered)) == ["agents.json", "hooks.json",
                                            "printed-permissions.txt", "skills.json"]
    for name in os.listdir(rendered):
        golden = rendered / name
        original = golden.read_bytes()
        golden.write_bytes(original.replace(b"{", b"[", 1))
        bad = [r[2] for r in hr.parity(str(tk)) if r[3] != "in-parity"]
        assert bad == ["harness/antigravity/rendered/" + name]
        golden.write_bytes(original)


# --------------------------------------------------------------------------- BR-7
def test_no_merge_surface():
    """BR-7 reads not applicable, and `merge_json` is as REQ-657 shipped it."""
    surfaces = adapter()["paths"]
    assert all(s.get("write_mode", "create") == "create" for s in surfaces.values())
    source = open(os.path.join(TOOLKIT, "tools", "adlc", "harness_render.py"),
                  encoding="utf-8").read()
    assert "def merge_json(existing_text, rendered_text, owned_keys):" in source


def test_a_users_skills_file_is_kept(sandbox):
    path = user_path(".gemini/config/skills.json")
    os.makedirs(os.path.dirname(path))
    mine = '{"entries": [{"path": "/my/skills"}]}\n'
    open(path, "w").write(mine)
    out = run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert out.returncode == 0, out.stderr
    assert "kept" in out.stdout and "add it to your file" in out.stdout
    assert TOOLKIT in out.stdout
    assert open(path).read() == mine


# --------------------------------------------------------------------------- BR-8
def rendered_commands():
    block, _found = hr.render_hooks(adapter(), hooks())
    return {("ethos-inject" if "adlc_ethos_inject" in h["command"] else "session-record"): h
            for h in block["SessionStart"][0]["hooks"]}


def test_hook_wraps_the_canonical_command():
    commands = rendered_commands()
    for hook in hooks():
        got = commands[hook["id"]]["command"]
        assert got.startswith("cd .. || exit 0\n")
        assert hook["command"].rstrip("\n") in got
        assert commands[hook["id"]]["timeout"] == hook["timeout_s"]
    tail = "--harness antigravity --field session_id=conversationId " \
           "--field transcript_path=transcriptPath"
    assert commands["session-record"]["command"].endswith(tail)
    ethos = commands["ethos-inject"]["command"]
    assert tail + " --context-key systemMessage | {" in ethos


def test_hook_events_are_only_session_start():
    block, findings = hr.render_hooks(adapter(), hooks())
    assert list(block) == ["SessionStart"]
    missing = {f.command for f in findings if f.verdict == "unsupported"}
    assert missing == {"session-compact", "subagent-start"}
    assert adapter()["capabilities"]["subagent_start_hook"] == "no"


def project_with_ethos(root, ethos):
    project = git_repo(root / "proj")
    (project / ".agents").mkdir()
    (project / ".adlc" / "partials").mkdir(parents=True)
    if ethos is not None:
        (project / ".adlc" / "ETHOS.md").write_text(ethos, encoding="utf-8")
    for name in ("ethos-inject.sh", "session-record.sh"):
        shutil.copy(os.path.join(TOOLKIT, "partials", name), project / ".adlc" / "partials")
    return project


@pytest.mark.parametrize("shell", ["/bin/sh", "bash", "zsh", "dash"])
def test_hook_prints_inject_steps(sandbox, shell):
    """AC-8's shape, on each shell: run the rendered command where `agy` runs it, in
    `.agents/`. ETHOS arrives as one JSON document, with its quotes and backslashes."""
    if not shutil.which(shell):
        pytest.skip("%s is not installed" % shell)
    text = '# Ethos\n\nA "quoted" word, a back\\slash, and a tab\there.\n'
    project = project_with_ethos(sandbox, text)
    command = rendered_commands()["ethos-inject"]["command"]
    out = subprocess.run([shell, "-c", command], cwd=str(project / ".agents"),
                         capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert list(data) == ["injectSteps"]
    assert data["injectSteps"][0]["systemMessage"]["systemMessage"] == text


def test_no_ethos_prints_nothing(sandbox):
    """A hook never invents a constitution, and `agy` gets no half-written JSON."""
    project = project_with_ethos(sandbox, None)
    command = rendered_commands()["ethos-inject"]["command"]
    out = subprocess.run(["sh", "-c", command], cwd=str(project / ".agents"),
                         capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    assert (out.returncode, out.stdout) == (0, "")


def test_session_record_names_the_harness(sandbox):
    project = project_with_ethos(sandbox, "x\n")
    transcript = user_path(".gemini/antigravity-cli/brain/abc/t.jsonl")
    payload = json.dumps({"conversationId": "abc-123", "transcriptPath": transcript,
                          "workspacePaths": [str(project)]})
    command = rendered_commands()["session-record"]["command"]
    out = subprocess.run(["sh", "-c", command], cwd=str(project / ".agents"), input=payload,
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout == "", out.stderr
    sidecar = (project / ".adlc" / ".session" / "abc-123").read_text().splitlines()
    assert sidecar[0] == "harness=antigravity"
    assert sidecar[1] == "session_id=abc-123"
    assert sidecar[2] == "transcript_path=" + transcript
    assert os.path.realpath(sidecar[3].split("=", 1)[1]) == os.path.realpath(str(project))


def test_hook_file_is_a_map_of_named_hooks(sandbox):
    project = git_repo(sandbox / "proj")
    assert run_cli(["harness", "render", "--harness", "antigravity"], project).returncode == 0
    doc = json.loads((project / ".agents" / "hooks.json").read_text())
    assert list(doc) == ["adlc"]
    assert list(doc["adlc"]) == ["SessionStart"]
    assert all(set(h) == {"type", "command", "timeout"} for h in doc["adlc"]["SessionStart"])


def test_a_changed_hook_is_drift(sandbox):
    """The named-hook shape, read by the drift path it needs its own reader for."""
    project = git_repo(sandbox / "proj")
    run_cli(["harness", "render", "--harness", "antigravity"], project)
    path = project / ".agents" / "hooks.json"
    assert run_cli(["harness", "drift", "--harness", "antigravity"], project).returncode == 0
    doc = json.loads(path.read_text())
    doc["adlc"]["SessionStart"].pop()
    path.write_text(json.dumps(doc))
    out = run_cli(["harness", "drift", "--harness", "antigravity"], project)
    assert out.returncode == 1 and "missing or changed hook: SessionStart" in out.stdout


# --------------------------------------------------------------------------- BR-9
def test_agents_render_and_refuse(sandbox):
    out = run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert out.returncode == 0, out.stderr
    target = user_path(".gemini/config/agents")
    names = sorted(os.listdir(target))
    assert names == sorted(f for f in os.listdir(os.path.join(TOOLKIT, "agents"))
                           if f.endswith(".md"))
    for name in names:
        front, body = hr.split_agent(open(os.path.join(target, name), encoding="utf-8").read())
        assert front[0] == hr.AGENT_MARKER
        assert body.lstrip().startswith(hr.ETHOS_LINE), name
        assert not any(ln.startswith(("model:", "tier:")) for ln in front), name
        tools = [ln for ln in front if ln.startswith("tools:")]
        assert len(tools) == 1 and re.match(r"^tools: \[[a-z_, ]+\]$", tools[0]), (name, tools)
    # A headerless file at a target path is refused, and nothing is written.
    theirs = os.path.join(target, "reflector.md")
    open(theirs, "w").write("---\nname: reflector\ndescription: mine\n---\n\nMine.\n")
    other = os.path.join(target, "adversary.md")
    os.remove(other)
    out = run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert out.returncode == 2
    assert "refusing to overwrite" in out.stderr and "reflector.md" in out.stderr
    assert "Mine." in open(theirs).read()
    assert not os.path.exists(other)


def test_an_agent_with_no_tools_line_gets_the_whole_set(sandbox):
    """`tools` defaults to `[]`, and the docs do not say what that means, so an agent that
    has every tool on Claude Code says so here rather than leaning on that default."""
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    for name in ("pipeline-runner.md", "task-implementer.md"):
        front, _body = hr.split_agent(open(user_path(".gemini/config/agents/" + name),
                                           encoding="utf-8").read())
        tools = next(ln for ln in front if ln.startswith("tools:"))
        for tool in ("read_file", "run_command", "edit_file", "write_file", "invoke_subagent"):
            assert tool in tools, (name, tool)


def test_a_file_that_is_not_text_is_refused_too(sandbox):
    path = user_path(".gemini/config/agents/reflector.md")
    os.makedirs(os.path.dirname(path))
    with open(path, "wb") as fh:
        fh.write(b"\xff\xfe\x00binary")
    out = run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert out.returncode == 2 and "refusing to overwrite" in out.stderr


def test_a_rendered_copy_is_refreshed(sandbox):
    """Benign path of the refusal: a file this toolkit rendered is rewritten as before."""
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    path = user_path(".gemini/config/agents/reflector.md")
    text = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write(text + "\ndrift\n")
    assert run_cli(["harness", "install", "--harness", "antigravity"], sandbox).returncode == 0
    assert open(path, encoding="utf-8").read() == text


def test_copy_harnesses_without_the_header_are_not_refused(sandbox):
    """Copilot and Codex keep what they do today: no marker, no refusal."""
    data = ha.load_adapter(os.path.join(TOOLKIT, "harness", "codex.yml"), toolkit=TOOLKIT)
    path = user_path(".codex/agents/reflector.toml")
    os.makedirs(os.path.dirname(path))
    open(path, "w").write("name = \"mine\"\n")
    report = agents_render.render_copies(data, TOOLKIT, agents_render.parse_agents_config())
    assert any(r[2] for r in report)
    assert 'name = "mine"' not in open(path).read()


def test_unmapped_tool_exits_naming_it(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "x.md").write_text("---\nname: x\ndescription: d\ntools: Read, Telepathy\n---\n")
    with pytest.raises(ha.AdapterError, match="Telepathy"):
        ha.load_adapter(ADAPTER, toolkit=TOOLKIT, agents_dir=str(agents))


def test_model_is_omitted_and_canonical_agents_are_untouched(sandbox):
    before = {f: open(os.path.join(TOOLKIT, "agents", f), "rb").read()
              for f in os.listdir(os.path.join(TOOLKIT, "agents"))}
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert not os.path.exists(user_path(".claude/agents"))
    after = {f: open(os.path.join(TOOLKIT, "agents", f), "rb").read()
             for f in os.listdir(os.path.join(TOOLKIT, "agents"))}
    assert before == after


# --------------------------------------------------------------- BR-4, BR-10, BR-12
def test_install_runs_no_plugin_command(sandbox):
    path, log = stub_agy(sandbox)
    out = run_cli(["harness", "install", "--harness", "antigravity"], sandbox, path)
    assert out.returncode == 0, out.stderr
    assert "printed, never written" in out.stdout
    assert "--surface permissions" in out.stdout
    assert os.path.isfile(user_path(".gemini/config/skills.json"))
    assert not os.path.exists(user_path(".gemini/config/plugins"))
    assert not os.path.exists(user_path(".gemini/antigravity-cli/settings.json"))
    calls = log.read_text() if log.exists() else ""
    assert "plugin" not in calls


def test_no_manifest_is_added():
    for rel in ("gemini-extension.json", ".antigravity-plugin/plugin.json",
                ".gemini-plugin/plugin.json", "plugin.json", "hooks.json"):
        assert not os.path.exists(os.path.join(TOOLKIT, rel)), rel


def test_skills_file_names_the_view_or_the_toolkit(sandbox):
    path = user_path(".gemini/config/skills.json")
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert json.load(open(path)) == {"entries": [{"path": TOOLKIT}]}
    view = user_path(".claude/adlc/skills-view")
    os.makedirs(view)
    os.remove(path)
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox)
    assert json.load(open(path)) == {"entries": [{"path": view}]}


def test_render_currency_cycle(sandbox):
    """AC-10, end to end, through the same check `adlc doctor` runs."""
    def doctor(path):
        return run_cli(["doctor", "--checks", "render-currency:antigravity,antigravity-skills"],
                       sandbox, path)

    nobin = doctor(SYSTEM_PATH)
    assert "[SKIP] render-currency:antigravity" in nobin.stdout
    assert "[SKIP] antigravity-skills" in nobin.stdout
    path, _log = stub_agy(sandbox)
    fresh = doctor(path)
    assert "[SKIP] render-currency:antigravity" in fresh.stdout, fresh.stdout
    assert "nothing rendered" in fresh.stdout and "[SKIP] antigravity-skills" in fresh.stdout
    assert run_cli(["harness", "install", "--harness", "antigravity"], sandbox, path).returncode == 0
    ok = doctor(path)
    assert "[PASS] render-currency:antigravity" in ok.stdout, ok.stdout
    assert "[PASS] antigravity-skills" in ok.stdout
    os.remove(user_path(".gemini/config/agents/reflector.md"))
    bad = doctor(path)
    assert "[FAIL] render-currency:antigravity" in bad.stdout
    assert "reflector" in bad.stdout
    fix = re.search(r"-> fix: (adlc .*)|fix: (adlc .*)|(adlc agents render --harness \S+)",
                    bad.stdout)
    assert fix, bad.stdout
    remedy = next(g for g in fix.groups() if g)
    argv = shlex.split(remedy)[1:]
    assert run_cli(argv, sandbox, path).returncode == 0
    assert "[PASS] render-currency:antigravity" in doctor(path).stdout


def test_a_deleted_skills_file_fails_and_its_row_fixes_it(sandbox):
    path, _log = stub_agy(sandbox)
    run_cli(["harness", "install", "--harness", "antigravity"], sandbox, path)
    os.remove(user_path(".gemini/config/skills.json"))
    out = run_cli(["doctor", "--checks", "render-currency:antigravity"], sandbox, path)
    assert "[FAIL] render-currency:antigravity" in out.stdout
    assert ".gemini/config/skills.json" in out.stdout
    row = run_cli(["doctor", "--checks", "antigravity-skills"], sandbox, path)
    assert "[FAIL] antigravity-skills" in row.stdout
    assert "adlc harness install --harness antigravity" in row.stdout


def test_rows_need_only_the_adapter(sandbox, tmp_path):
    src = open(ADAPTER, encoding="utf-8").read()
    block = re.search(r"doctor_rows:\n(  .*\n)+", src).group(0)
    data = ha.load_adapter(variant(tmp_path, [(block, "doctor_rows: []\n")]), toolkit=TOOLKIT)
    assert harness_doctor.row_outcomes(data, TOOLKIT) == []


def test_older_adapters_keep_their_doctor_behaviour(sandbox):
    """ADR-10 is schema 4 only: an unrendered Codex still reads what it read."""
    data = ha.load_adapter(os.path.join(TOOLKIT, "harness", "codex.yml"), toolkit=TOOLKIT)
    assert harness_doctor.nothing_rendered(data, TOOLKIT) is False


def _tree(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            out[os.path.relpath(path, root)] = open(path, "rb").read()
    return out


def test_no_writes_without_a_command(sandbox):
    """AC-12: detect and doctor with `agy` on PATH write nothing, here or in a project."""
    path, _log = stub_agy(sandbox)
    project = git_repo(sandbox / "proj")
    home = os.environ["HOME"]
    before = (_tree(home), sorted(os.listdir(project)))
    run_cli(["harness", "detect"], project, path)
    run_cli(["doctor", "--checks", "harness:antigravity,render-currency:antigravity"], project,
            path)
    assert (_tree(home), sorted(os.listdir(project))) == before


def test_gemini_keeps_no_adapter():
    assert not os.path.exists(os.path.join(TOOLKIT, "harness", "gemini.yml"))
    status, detail, _remedy = harness_doctor.render_currency("gemini", None, TOOLKIT)
    assert status == "SKIP" and "no adapter ships" in detail


# --------------------------------------------------------------------- BR-14, BR-15
@pytest.mark.parametrize("rel, words", [
    ("README.md", "### Antigravity CLI"),
    (".adlc/context/architecture.md", "Antigravity CLI adapter (REQ-658)"),
    ("tools/adlc/README.md", "harness/antigravity.yml"),
    ("CHANGELOG.md", "REQ-658"),
    (".adlc/specs/REQ-662-exec-adapters-copilot-codex-gemini-cursor/requirement.md",
     "antigravity.json"),
])
def test_documents_name_the_surfaces(rel, words):
    assert words in open(os.path.join(TOOLKIT, rel), encoding="utf-8").read()


def test_deferred_lists_every_unverified_row():
    """BR-15: a row the note left unverified is owed in the spec, by its key."""
    spec = open(SPEC, encoding="utf-8").read()
    assert "\n## Deferred\n" in spec
    deferred = spec.split("\n## Deferred\n")[1].split("\n## ")[0]
    for row in note_rows():
        if row[4] == "unverified":
            key = re.search(r"`([^`]+)`", row[3])
            assert (key.group(1) if key else row[3]) in deferred, row[3]
    assert "atelier-fashion" in deferred
    assert re.search(r"^status: (approved|in-progress|complete)$", spec, re.MULTILINE)
