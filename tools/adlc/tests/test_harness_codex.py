"""REQ-655: the Codex CLI adapter.

Every case that writes runs in a sandbox: HOME and ADLC_HOME point under ``tmp_path``,
and projects are throwaway git repos. No case runs a real ``codex``: the binary on
PATH, where one is needed, is a stub. The real-tool evidence is in the spec.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import agents_render
import harness_adapter as ha
import harness_doctor
import harness_render as hr
import lane_check

HERE = os.path.dirname(os.path.abspath(__file__))
ADLC = os.path.join(os.path.dirname(HERE), "adlc.py")
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CODEX_YML = os.path.join(TOOLKIT, "harness", "codex.yml")
SPEC = os.path.join(TOOLKIT, ".adlc", "specs", "REQ-655-codex-harness-adapter", "requirement.md")
RULES = ".codex/rules/adlc.rules"
SYSTEM_PATH = "/usr/bin:/bin"
OMITTED = ("git push", "git branch", "git -C")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ADLC_HOME", str(home / ".claude"))
    monkeypatch.setenv("PATH", SYSTEM_PATH)
    return tmp_path


def adapter():
    return ha.load_adapter(CODEX_YML, toolkit=TOOLKIT)


def perms():
    return ha.load_permissions(ha.permissions_path(TOOLKIT))


def result():
    return hr.load_result_file(os.path.join(TOOLKIT, ".adlc", "research", "harness-probes",
                                            "codex.json"))


def render(scope="project"):
    return hr.render_permissions(adapter(), perms(), scope, result())


def variant(tmp_path, edits):
    """A copy of the adapter with ``edits`` applied, same basename."""
    src = open(CODEX_YML, encoding="utf-8").read()
    for old, new in edits:
        assert old in src, old
        src = src.replace(old, new, 1)
    d = tmp_path / ("v%d" % len(list(tmp_path.glob("v*"))))
    d.mkdir()
    path = d / "codex.yml"
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


def stub_binary(tmp_path, name="codex"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    tool.write_text("#!/bin/sh\necho 'codex-cli 0.166.0'\n")
    tool.chmod(0o755)
    return "%s:%s" % (bin_dir, SYSTEM_PATH)


def install_delegation():
    """The ``~/bin/adlc-read`` the delegation install leaves behind."""
    bin_dir = os.path.join(os.environ["HOME"], "bin")
    os.makedirs(bin_dir, exist_ok=True)
    tool = os.path.join(bin_dir, "adlc-read")
    with open(tool, "w") as fh:
        fh.write("#!/bin/sh\n")
    os.chmod(tool, 0o755)


def rule_lines(text):
    return [line for line in text.splitlines() if line.startswith("prefix_rule(")]


# --------------------------------------------------------------------------- BR-1
def test_loader_refuses_unknown_key_and_missing_gitdir_field(tmp_path):
    assert adapter()["schema_version"] == 3
    bad = variant(tmp_path, [("name: codex\n", "name: codex\nworking_copy: worktree\n")])
    with pytest.raises(ha.AdapterError, match="working_copy"):
        ha.load_adapter(bad, toolkit=TOOLKIT)
    bad = variant(tmp_path, [("sandbox_can_reach_common_gitdir: true\n", "")])
    with pytest.raises(ha.AdapterError, match="sandbox_can_reach_common_gitdir"):
        ha.load_adapter(bad, toolkit=TOOLKIT)


def test_schema_3_fields_are_refused_under_schema_2(tmp_path):
    bad = variant(tmp_path, [("schema_version: 3", "schema_version: 2")])
    with pytest.raises(ha.AdapterError, match="schema_version 3"):
        ha.load_adapter(bad, toolkit=TOOLKIT)


def test_copilot_and_cursor_stay_at_schema_2_without_the_field():
    for name in ("copilot", "cursor"):
        loaded = ha.load_adapter(os.path.join(TOOLKIT, "harness", name + ".yml"), toolkit=TOOLKIT)
        assert loaded["schema_version"] == 2
        assert "sandbox_can_reach_common_gitdir" not in loaded


#: AC-1's exemptions: uses earlier REQs own, none of them a render input.
HARNESS_PATH_EXEMPT = {
    "tools/adlc/lane_check.py", "partials/lane-check.md",        # the blocked-path list
    "tools/adlc/checks.py", "tools/adlc/harness.py", "install.sh",  # REQ-654's mount
    "tools/adlc/harness_probe.py",                               # REQ-664's profile
    "partials/session-transcript.sh",                            # REQ-660's transcript root
    "tools/adlc/README.md",                                      # prose
}
HARNESS_PATH_RE = re.compile(r"~/\.codex|\.codex/|~/\.agents")


def harness_path_hits(root):
    hits = []
    for top in ("tools", "partials", "agents"):
        for dirpath, dirnames, files in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if d not in ("tests", "__pycache__")]
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                if rel not in HARNESS_PATH_EXEMPT and HARNESS_PATH_RE.search(
                        open(full, encoding="utf-8", errors="replace").read()):
                    hits.append(rel)
    for rel in ["install.sh"] + [os.path.join(d, "SKILL.md") for d in os.listdir(root)]:
        full = os.path.join(root, rel)
        if os.path.isfile(full) and rel not in HARNESS_PATH_EXEMPT and HARNESS_PATH_RE.search(
                open(full, encoding="utf-8", errors="replace").read()):
            hits.append(rel)
    return hits


def test_no_codex_path_outside_the_adapter(tmp_path):
    assert harness_path_hits(TOOLKIT) == []
    fixture = tmp_path / "tk"
    (fixture / "partials").mkdir(parents=True)
    (fixture / "partials" / "bad.sh").write_text("x=.codex/rules\n")
    assert harness_path_hits(str(fixture)) == ["partials/bad.sh"]
    (fixture / "partials" / "bad.sh").write_text("x=~/.agents/skills\n")
    assert harness_path_hits(str(fixture)) == ["partials/bad.sh"]
    (fixture / "partials" / "bad.sh").write_text("x=harmless\n")
    assert harness_path_hits(str(fixture)) == []


# --------------------------------------------------------------------------- BR-2
def _instructions(text):
    match = re.search(r'^developer_instructions = """\n(.*?)\n"""$', text, re.S | re.M)
    return match.group(1)


def test_agent_render_restraint_and_ethos(sandbox):
    home = os.environ["HOME"]
    project = git_repo(sandbox / "project")
    out = run_cli(["agents", "render", "--harness", "codex"], project)
    assert out.returncode == 0, out.stderr
    dest = os.path.join(home, ".codex", "agents")
    names = sorted(os.listdir(dest))
    assert names == sorted(f[:-3] + ".toml" for f in os.listdir(os.path.join(TOOLKIT, "agents"))
                           if f.endswith(".md"))
    restrained = 0
    for name in names:
        text = open(os.path.join(dest, name), encoding="utf-8").read()
        assert text.startswith('name = "%s"\n' % name[:-5])
        paras = _instructions(text).split("\n\n")
        assert paras[0] == hr.ETHOS_LINE
        if name in ("pipeline-runner.toml", "task-implementer.toml"):
            assert hr.RESTRAINT_SENTENCE not in text
        else:
            assert paras[1] == hr.RESTRAINT_SENTENCE
            restrained += 1
        assert "\nmodel = " not in text        # tier_map is unverified
    assert restrained == 17
    again = run_cli(["agents", "render", "--harness", "codex"], project)
    assert "0 changed" in again.stdout
    assert not os.path.exists(os.path.join(str(project), ".codex", "agents"))
    target = os.path.join(dest, "reflector.toml")
    open(target, "a").write("# hand edit\n")
    check = run_cli(["harness", "render", "--check", "--harness", "codex"], project)
    assert check.returncode == 1 and "reflector" in check.stdout


def test_no_rendered_copy_means_check_has_nothing_to_compare(sandbox):
    check = run_cli(["harness", "render", "--check", "--harness", "codex"], git_repo(sandbox / "p"))
    assert check.returncode == 0, check.stdout


def test_model_follows_the_tier_map(tmp_path, sandbox):
    path = variant(tmp_path, [("  opus: unverified", "  opus: gpt-test-1")])
    loaded = ha.load_adapter(path, toolkit=TOOLKIT)
    plans, _n = agents_render.plan_copies(loaded, TOOLKIT, {"classes": {}, "overrides": {}})
    by_name = dict((n, t) for n, _p, t in plans)
    assert 'model = "gpt-test-1"' in by_name["reflector"]
    assert "\nmodel = " not in by_name["quality-reviewer"]    # sonnet: unverified


@pytest.mark.parametrize("tools,restrained", [("Read, Grep", True), ("Read, Write", False),
                                              ("Bash, Edit", False)])
def test_restraint_needs_both_edit_and_write_absent(tools, restrained):
    text = "---\nname: x\ndescription: d\ntools: %s\n---\n\nBody.\n" % tools
    out = hr.render_agent_copy(adapter(), "x", text, None, [])
    assert (hr.RESTRAINT_SENTENCE in out) is restrained


@pytest.mark.parametrize("body", ['a """ b', "back\\slash", "tab\there", 'ends with "', "ctl\x01"])
def test_multiline_string_round_trips(body):
    encoded = hr._toml_multiline(body)
    inner = encoded[len('"""\n'):-len('\n"""')]
    assert '"""' not in inner
    assert json.loads('"%s"' % inner.replace('"', '\\"').replace('\\\\"', '\\"')
                      .replace("\t", "\\t")) == body


# --------------------------------------------------------------------------- BR-3, BR-4
def test_rules_render(sandbox):
    project = git_repo(sandbox / "project")
    out = run_cli(["harness", "render", "--harness", "codex"], project)
    assert out.returncode == 0, out.stderr
    text = (project / RULES).read_text()
    assert text == open(os.path.join(TOOLKIT, "harness", "codex", "rendered", "adlc.rules")).read()
    lines = rule_lines(text)
    for command in OMITTED:
        pattern = json.dumps(command.split())
        assert 'prefix_rule(pattern=%s, decision="allow")' % pattern not in lines
    assert not [line for line in lines if '"git", "-C"' in line]
    assert 'decision="forbidden"' not in text
    broad = " ".join(adapter()["capabilities"]["fence_broad_spelling"])
    assert broad not in text
    for opener in ("if", "sh", "bash", "bash -lc"):
        assert 'pattern=%s,' % json.dumps(opener.split()) not in text
    for entry in perms()["entries"]:
        for command in entry["commands"]:
            line = 'prefix_rule(pattern=%s, decision="%s")' % (
                json.dumps(command), "allow" if entry["tier"] == "routine" else "prompt")
            if entry["tier"] == "deny":
                assert line in lines, command
            elif entry["id"] != hr.FENCE_ID and " ".join(command) not in OMITTED:
                assert line in lines, command
    assert "sha256:%s" % perms()["sha256"] in text
    for command in OMITTED:
        assert "[%s]" % command in text
    assert "shape.env-prefix" in text and "shape.shell-opener" in text


def test_no_allow_for_a_deny_tier_command():
    rules, _f, _x = render()
    allows = [r for r in rules if r.kind == "allow"]
    for sample in (("git", "push", "--force"), ("git", "-C", "/x", "push", "--force"),
                   ("git", "branch", "-D", "x"), ("git", "-C", "/x", "branch", "-D", "x"),
                   ("git", "push", "origin", "--force"), ("git", "branch", "foo", "-D")):
        assert not [r for r in allows if hr.allow_matches(r.spelling, False, "token-prefix",
                                                          sample, False)], sample


def _pass_record(tmp_path):
    return variant(tmp_path, [(
        "prefix: {mechanism: confirm, result: unverified, harness_version: codex-cli 0.166.0, "
        "source: probe, by_hand: strictest-wins}",
        "prefix: {mechanism: confirm, result: pass, harness_version: codex-cli 0.166.0, "
        "source: probe, by_hand: strictest-wins}")])


PROBE_PASS = {"harness_version": "codex-cli 0.166.0", "probes": {"ask-tier-deny": {
    "sub_results": {"deny-under-allow": {"status": "pass"}}}}}


def test_lint_refuses_a_restored_git_push(tmp_path):
    loaded = ha.load_adapter(_pass_record(tmp_path), toolkit=TOOLKIT)
    fixture = [hr.Rule("git.write", ("git", "push"), "routine", "allow", ("git", "push"), False)]
    failures = hr.evaluate_rules(loaded, perms(), fixture, "project", PROBE_PASS)
    assert failures and "git push" in failures[0] and "--force" in failures[0]


def test_the_shipped_render_passes_the_lint():
    rules, _f, _x = render()
    assert hr.evaluate_rules(adapter(), perms(), rules, "project", result()) == []


def _fixture_perms():
    base = perms()
    entries = list(base["entries"]) + [
        {"id": "tf.all", "tier": "routine", "match": "prefix", "note": "n", "commands": [["tf"]]},
        {"id": "tf.apply", "tier": "deny", "match": "prefix", "note": "n",
         "commands": [["tf", "apply"], ["tf", "destroy"]]}]
    return dict(base, entries=entries)


def test_a_same_position_entry_restores(tmp_path):
    loaded = ha.load_adapter(_pass_record(tmp_path), toolkit=TOOLKIT)
    rules, _f, _x = hr.render_permissions(loaded, _fixture_perms(), "project", PROBE_PASS)
    assert ("tf",) in [r.spelling for r in rules if r.kind == "allow"]
    assert ("git", "push") not in [r.spelling for r in rules if r.kind == "allow"]


def test_restoration_needs_the_by_hand_result(tmp_path):
    path = _pass_record(tmp_path)
    src = open(path).read().replace(
        "result: pass, harness_version: codex-cli 0.166.0, source: probe, by_hand: strictest-wins",
        "result: pass, harness_version: codex-cli 0.166.0, source: probe, by_hand: allow-wins")
    open(path, "w").write(src)
    loaded = ha.load_adapter(path, toolkit=TOOLKIT)
    rules, _f, _x = hr.render_permissions(loaded, _fixture_perms(), "project", PROBE_PASS)
    assert ("tf",) not in [r.spelling for r in rules]


def test_a_flag_is_not_a_same_position_spelling():
    assert hr.same_position(("tf",), ("tf", "apply"))
    assert not hr.same_position(("git", "push"), ("git", "push", "--force"))
    assert not hr.same_position(("git", "push"), ("git", "push", "origin", "+HEAD:x"))


def test_fidelity_lists_every_declared_loss():
    findings, failures = hr.fidelity(adapter(), perms(), result())
    assert failures == []
    keys = set()
    for f in findings:
        if f.verdict != "exact":
            keys.add((f.entry, f.command))
    for pair in (("git.write", "git push"), ("git.read", "git branch"), ("git.read", "git -C"),
                 ("git.config.identity", "git config user.email"), ("npm.ci", "npm ci"),
                 ("shape.env-prefix", "env-prefix"), ("shape.shell-opener", "shell-opener")):
        assert pair in keys, pair
    assert any(e == hr.FENCE_ID for e, _c in keys)


def _declared_keys():
    return [k for k in adapter()["accepted_fidelity"] if k != hr.FENCE_ID]


@pytest.mark.parametrize("key", _declared_keys())
def test_removing_a_declared_loss_fails_the_lint(key):
    loaded = adapter()
    del loaded["accepted_fidelity"][key]
    _f, failures = hr.fidelity(loaded, perms(), result())
    assert failures and any(key.split(":")[0] in f for f in failures)


def test_prompt_to_allow_is_harness_config_drift(sandbox):
    project = git_repo(sandbox / "project")
    run_cli(["harness", "render", "--harness", "codex"], project)
    assert run_cli(["harness", "drift", "--harness", "codex"], project).returncode == 0
    path = project / RULES
    path.write_text(path.read_text().replace(
        'prefix_rule(pattern=["gh", "pr", "merge"], decision="prompt")',
        'prefix_rule(pattern=["gh", "pr", "merge"], decision="allow")'))
    out = run_cli(["harness", "drift", "--harness", "codex"], project)
    assert out.returncode == 1
    assert "stale" in out.stdout and '["gh", "pr", "merge"]' in out.stdout


def test_a_softened_config_is_drift(sandbox):
    project = git_repo(sandbox / "project")
    run_cli(["harness", "render", "--harness", "codex"], project)
    path = project / ".codex" / "config.toml"
    path.write_text(path.read_text().replace("on-request", "untrusted"))
    out = run_cli(["harness", "drift", "--harness", "codex"], project)
    assert out.returncode == 1 and "approval_policy" in out.stdout


# --------------------------------------------------------------------------- BR-5
def _render(project, path=None):
    return run_cli(["harness", "render", "--harness", "codex"], project, path)


def test_init_config_render(sandbox):
    project = git_repo(sandbox / "project")
    home_config = os.path.join(os.environ["HOME"], ".codex", "config.toml")
    assert _render(project).returncode == 0
    text = (project / ".codex" / "config.toml").read_text()
    assert text == 'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
    assert "writable_roots" not in text and not os.path.exists(home_config)

    other = git_repo(sandbox / "other")
    (other / ".codex").mkdir()
    (other / ".codex" / "config.toml").write_text('model = "x"\n')
    assert _render(other).returncode == 0
    merged = (other / ".codex" / "config.toml").read_text()
    assert 'model = "x"' in merged and "sandbox_mode" in merged


@pytest.mark.parametrize("line", ['sandbox_mode = "danger-full-access"\n',
                                  'approval_policy = "never"\n'])
def test_a_weakened_posture_exits_non_zero(sandbox, line):
    project = git_repo(sandbox / "project")
    (project / ".codex").mkdir()
    config = project / ".codex" / "config.toml"
    config.write_text(line)
    out = _render(project)
    assert out.returncode != 0
    assert "posture is not set" in out.stderr and "Rule B" in out.stderr
    assert config.read_text() == line


@pytest.mark.parametrize("text,construct", [
    ('sandbox_mode = "a"\nsandbox_mode = "b"\n', "duplicate key"),
    ('[t]\nsandbox_mode = "x"\n', "inside a table"),
    ('a.b = 1\n', "dotted key"),
    ('note = """\nx\n"""\n', "multi-line string"),
    ('roots = [\n  "a",\n]\n', "multi-line array"),
    ('"sandbox_mode" = "x"\n', "quoted key spelling"),
    ('x = { a = 1 }\n', "top-level inline table"),
    ('[[a]]\nb = 1\n', "[[array-of-tables]]"),
    ('[sandbox_workspace_write]\n[sandbox_workspace_write]\n', "duplicate [sandbox_workspace_write]"),
    ('["sandbox_workspace_write"]\n', "quoted [sandbox_workspace_write]"),
    ('[ sandbox_workspace_write ]\n', "spaced [sandbox_workspace_write]"),
    ('profile = "x"\n', "top-level profile"),
    ('a = 1\r\n', "CRLF"),
    ('﻿a = 1\n', "BOM"),
    ('a = 1', "missing trailing newline"),
])
def test_a_fail_closed_construct_leaves_the_file_and_exits_non_zero(sandbox, text, construct):
    project = git_repo(sandbox / "project")
    (project / ".codex").mkdir()
    config = project / ".codex" / "config.toml"
    config.write_bytes(text.encode("utf-8"))
    out = _render(project)
    assert out.returncode != 0 and construct in out.stderr
    assert config.read_bytes() == text.encode("utf-8")


def test_stanza_is_printed_only_when_the_gate_needs_it(sandbox):
    needed = {"probes": {"git-write-worktree": {"sub_results": {
        "root-is-worktree": {"status": "fail"}, "writable-roots-repo": {"status": "pass"}}}}}
    assert hr.writable_roots_needed(needed)
    assert not hr.writable_roots_needed(result())    # root-is-worktree passed
    assert not hr.writable_roots_needed(None)
    assert hr.writable_root_stanza(adapter(), "/r/.git") == \
        '[sandbox_workspace_write]\nwritable_roots = ["/r/.git"]\n'
    assert "sandbox_workspace_write" not in _render(git_repo(sandbox / "p")).stdout


def test_writable_root_is_explicit_union_only(sandbox):
    project = git_repo(sandbox / "project")
    config = os.path.join(os.environ["HOME"], ".codex", "config.toml")
    os.makedirs(os.path.dirname(config))
    with open(config, "w") as fh:
        fh.write('model = "m"\n\n[sandbox_workspace_write]\nwritable_roots = ["/old"]\n')
    os.chmod(config, 0o600)
    before = open(config).read()
    assert run_cli(["harness", "install", "--harness", "codex"], project).returncode == 0
    assert open(config).read() == before
    out = run_cli(["harness", "install", "--harness", "codex", "--writable-root", "/new/.git"],
                  project)
    assert out.returncode == 0, out.stderr
    after = open(config).read()
    assert 'writable_roots = ["/old", "/new/.git"]' in after and 'model = "m"' in after
    assert '+writable_roots = ["/old", "/new/.git"]' in out.stdout
    assert "widens every codex session" in out.stdout
    assert os.stat(config).st_mode & 0o777 == 0o600
    assert run_cli(["harness", "install", "--harness", "codex", "--writable-root", "relative"],
                   project).returncode == 2
    assert run_cli(["harness", "install", "--all", "--writable-root", "/x"],
                   project).returncode == 2


# --------------------------------------------------------------------------- BR-6, BR-7
def _commands(doc, event):
    return [h for group in doc["hooks"][event] for h in group["hooks"]]


def test_hooks_render(sandbox):
    project = git_repo(sandbox / "project")
    assert _render(project).returncode == 0
    path = project / ".codex" / "hooks.json"
    doc = json.loads(path.read_text())
    assert sorted(doc["hooks"]) == ["SessionStart", "SubagentStart"]
    start = _commands(doc, "SessionStart")
    assert len(start) == 2 and len(_commands(doc, "SubagentStart")) == 1
    assert all(h["timeout"] == 10 for h in start)
    assert "adlc_session_record --harness codex" in start[1]["command"]
    assert "--context-key" not in path.read_text()
    subprocess.run([sys.executable, "-m", "json.tool", str(path)], check=True,
                   capture_output=True)

    def run(hook, cwd):
        env = {"HOME": os.environ["HOME"], "PATH": SYSTEM_PATH, "ADLC_TOOLKIT_ROOT": TOOLKIT,
               "CLAUDE_PLUGIN_ROOT": TOOLKIT}
        return subprocess.run(["/bin/sh", "-c", hook["command"]], cwd=str(cwd), env=env, input="",
                              capture_output=True, text=True, timeout=30)

    assert (run(start[0], project).stdout, run(start[0], project).returncode) == ("", 0)
    (project / ".adlc").mkdir()
    (project / ".adlc" / "ETHOS.md").write_text("# The ethos\n")
    ran = run(start[0], project)
    assert ran.returncode == 0 and ran.stdout == "# The ethos\n"


def test_compaction_is_not_mapped():
    loaded = adapter()
    assert loaded["hook_events"]["session-compact"] == "unsupported"
    assert loaded["capabilities"]["compact_rehook"] == "no"
    assert loaded["capabilities"]["subagent_start_hook"] == "no"
    assert "hook_output" not in loaded


def test_agents_md_is_created_or_kept(sandbox):
    project = git_repo(sandbox / "project")
    assert _render(project).returncode == 0
    assert "## Skills" in (project / "AGENTS.md").read_text()
    other = git_repo(sandbox / "other")
    (other / "AGENTS.md").write_text("mine\n")
    assert _render(other).returncode == 0
    assert (other / "AGENTS.md").read_text() == "mine\n"
    assert not (other / ".codex" / "agents").exists()


@pytest.mark.parametrize("path", [RULES, ".codex/config.toml"])
def test_lane_check_blocks_the_codex_layer(path):
    assert ".codex/**" in lane_check.DEFAULT_BLOCKED_PATHS
    failures = lane_check.evaluate([path], lane_check.effective_config())[1]
    assert ("blocked-path", path) in failures


# --------------------------------------------------------------------------- BR-8
def _install_slice():
    text = open(os.path.join(TOOLKIT, "tools", "delegate", "install.sh")).read()
    start = text.index("# --- the same routing for Codex CLI")
    return text[start:text.index("# --- next steps", start)]


def _run_slice(tmp_path, path):
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True, exist_ok=True)
    python = venv / "python3"
    if not python.exists():
        python.symlink_to(sys.executable)
    script = 'set -eu\nVENV_DIR=%s\nREPO_ROOT=%s\n%s' % (tmp_path / "venv", TOOLKIT,
                                                         _install_slice())
    return subprocess.run(["/bin/sh", "-c", script], cwd=str(tmp_path), capture_output=True,
                          text=True, timeout=60,
                          env={"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
                               "PATH": path, "PYTHONDONTWRITEBYTECODE": "1"})


def _sums(*paths):
    return [open(p, "rb").read() for p in paths]


def test_delegate_installer_routes_codex(sandbox):
    home = os.environ["HOME"]
    path = stub_binary(sandbox)
    install_delegation()
    agents_md = os.path.join(home, ".codex", "AGENTS.md")
    rules = os.path.join(home, ".codex", "rules", "adlc.rules")
    first = _run_slice(sandbox, path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert open(agents_md).read().count("delegate-routing:start") == 1
    lines = rule_lines(open(rules).read())
    assert sorted(lines) == sorted('prefix_rule(pattern=["%s"], decision="allow")' % n
                                   for n in ("adlc-read", "adlc-write", "extract-chat"))
    before = _sums(agents_md, rules)
    second = _run_slice(sandbox, path)
    assert "already present" in second.stdout
    assert _sums(agents_md, rules) == before


def test_routing_block_equals_the_claude_one(sandbox):
    path = stub_binary(sandbox)
    install_delegation()
    _run_slice(sandbox, path)
    text = open(os.path.join(os.environ["HOME"], ".codex", "AGENTS.md")).read()
    canon = open(os.path.join(TOOLKIT, "tools", "delegate", "claude-md-routing.txt")).read()
    assert text == canon.rstrip("\n") + "\n"


def test_legacy_marker_gets_no_second_block(sandbox):
    agents_md = os.path.join(os.environ["HOME"], ".codex", "AGENTS.md")
    os.makedirs(os.path.dirname(agents_md))
    with open(agents_md, "w") as fh:
        fh.write("<!-- kimi-delegation:start -->\nold\n")
    install_delegation()
    _run_slice(sandbox, stub_binary(sandbox))
    assert open(agents_md).read() == "<!-- kimi-delegation:start -->\nold\n"


def test_no_codex_means_nothing_written(sandbox):
    install_delegation()
    out = _run_slice(sandbox, SYSTEM_PATH)
    assert out.returncode == 0 and "codex not detected" in out.stdout
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".codex"))


def test_no_delegation_means_no_routing(sandbox):
    out = run_cli(["harness", "install", "--harness", "codex"], git_repo(sandbox / "p"),
                  stub_binary(sandbox))
    assert out.returncode == 0 and "delegation is not installed" in out.stdout
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".codex", "AGENTS.md"))
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".codex", "rules"))


def test_a_tampered_routing_block_is_not_written(tmp_path):
    root = tmp_path / "tools" / "delegate"
    root.mkdir(parents=True)
    (root / "claude-md-routing.txt").write_text("tampered\n")
    (root / "claude-md-routing.txt.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(hr.RenderError, match="pinned hash"):
        hr.routing_text(str(tmp_path))


def test_installer_names_no_codex_path():
    text = open(os.path.join(TOOLKIT, "tools", "delegate", "install.sh")).read()
    assert ".codex" not in text


# --------------------------------------------------------------------------- BR-9, BR-10
def _doctor(args, cwd, path):
    return run_cli(["doctor"] + args, cwd, path)


def test_doctor_rows(sandbox):
    project = git_repo(sandbox / "project")
    checks = ["--checks", "render-currency:codex,codex-rules,codex-routing"]
    absent = _doctor(checks, project, SYSTEM_PATH)
    for row in ("render-currency:codex", "codex-rules", "codex-routing"):
        assert "[SKIP] %s" % row in absent.stdout, absent.stdout
    path = stub_binary(sandbox)
    assert "[SKIP] codex-rules — delegation is not installed" in \
        _doctor(checks, project, path).stdout
    assert run_cli(["harness", "install", "--harness", "codex"], project, path).returncode == 0
    target = os.path.join(os.environ["HOME"], ".codex", "agents", "reflector.toml")
    os.remove(target)
    broken = _doctor(checks, project, path)
    assert "[FAIL] render-currency:codex" in broken.stdout and "reflector" in broken.stdout
    remedy = re.search(r"adlc agents render --harness codex", broken.stdout)
    assert remedy
    assert run_cli(["agents", "render", "--harness", "codex"], project, path).returncode == 0
    assert "[PASS] render-currency:codex" in _doctor(checks, project, path).stdout


def test_user_rules_do_not_move_with_the_template(sandbox):
    install_delegation()
    plans, _p = hr.plan_surfaces(adapter(), "user", TOOLKIT, TOOLKIT, surfaces=("permissions",))
    assert "sha256" not in plans[0].content and plans[0].content.count("prefix_rule") == 3


def test_a_tampered_rules_row_is_fixed_by_its_remediation(sandbox):
    project = git_repo(sandbox / "project")
    path = stub_binary(sandbox)
    install_delegation()
    assert run_cli(["harness", "install", "--harness", "codex"], project, path).returncode == 0
    rules = os.path.join(os.environ["HOME"], ".codex", "rules", "adlc.rules")
    open(rules, "a").write('prefix_rule(pattern=["rm"], decision="allow")\n')
    rows = dict((r[0], r) for r in harness_doctor.row_outcomes(adapter(), TOOLKIT, str(project)))
    assert rows["codex-rules"][1] == "FAIL"
    remedy = rows["codex-rules"][3].split()
    assert remedy[0] == "adlc"
    assert run_cli(remedy[1:], project, path).returncode == 0
    rows = dict((r[0], r) for r in harness_doctor.row_outcomes(adapter(), TOOLKIT, str(project)))
    assert rows["codex-rules"][1] == "PASS"


def test_only_if_detected_refuses_an_unknown_name(sandbox):
    out = run_cli(["harness", "install", "--harness", "nosuch", "--only-if-detected"],
                  git_repo(sandbox / "p"))
    assert out.returncode == 2 and "nosuch" in out.stderr


def test_a_linked_user_config_stays_a_link(sandbox):
    home = os.environ["HOME"]
    real = sandbox / "dotfiles.toml"
    real.write_text('model = "m"\n')
    os.makedirs(os.path.join(home, ".codex"))
    os.symlink(str(real), os.path.join(home, ".codex", "config.toml"))
    out = run_cli(["harness", "install", "--harness", "codex", "--writable-root", "/a/.git"],
                  git_repo(sandbox / "p"))
    assert out.returncode == 0, out.stderr
    assert os.path.islink(os.path.join(home, ".codex", "config.toml"))
    assert "writable_roots" in real.read_text()


def test_rows_need_only_the_adapter(tmp_path):
    loaded = adapter()
    assert [r["id"] for r in loaded["doctor_rows"]] == ["codex-rules", "codex-routing"]
    loaded["doctor_rows"] = []
    assert harness_doctor.row_outcomes(loaded, TOOLKIT, str(tmp_path)) == []


def test_marker_row_accepts_the_legacy_marker(sandbox):
    install_delegation()
    agents_md = os.path.join(os.environ["HOME"], ".codex", "AGENTS.md")
    os.makedirs(os.path.dirname(agents_md))
    with open(agents_md, "w") as fh:
        fh.write("<!-- kimi-delegation:start -->\n")
    rows = dict((r[0], r[1]) for r in harness_doctor.row_outcomes(adapter(), TOOLKIT, str(sandbox)))
    assert rows["codex-routing"] == "PASS"


def test_doctor_refuses_unverified_gitdir(tmp_path, sandbox):
    path = variant(tmp_path, [("sandbox_can_reach_common_gitdir: true",
                               "sandbox_can_reach_common_gitdir: unverified")])
    status, detail, remedy = harness_doctor.render_currency("codex", path, TOOLKIT)
    assert status == "FAIL" and "sandbox_can_reach_common_gitdir" in detail and remedy
    assert harness_doctor.render_currency("codex", None, TOOLKIT)[0] == "SKIP"   # binary absent


def test_doctor_stays_standard_library():
    probe = ("import sys\nsys.path.insert(0, %r)\nimport checks, toml_merge\n"
             "bad = [m for m in sys.modules if m.split('.')[0] in ('yaml', 'tomllib', 'tomli')]\n"
             "sys.exit(1 if bad else 0)\n" % os.path.dirname(HERE))
    assert subprocess.run([sys.executable, "-c", probe], timeout=60).returncode == 0


def test_no_code_branches_on_a_harness_name():
    for name in os.listdir(os.path.dirname(HERE)):
        if name.endswith(".py") and name != "harness_probe.py":
            text = open(os.path.join(os.path.dirname(HERE), name), encoding="utf-8").read()
            assert "if harness == " not in text, name


def test_gate_record_is_complete():
    text = open(SPEC, encoding="utf-8").read()
    record = text[text.index("**Gate record (BR-10)"):]
    record = record[:record.index("\n- ", 10)] if "\n- id allocated" in record else record
    version = result()["harness_version"]
    assert version in text[text.index("**Gate record (BR-10)"):]
    for spelling in ("`git push --force`", "`git push --force-with-lease`",
                     "`git push origin +HEAD:refs/heads/x`", "`git push origin --force`",
                     "`git branch -D x`", "`git -C <path> push --force`"):
        match = re.search(re.escape(spelling) + r" `(prompted|ran|sandbox-failed)`", text)
        assert match, spelling
    assert text.count("`strictest-wins`") >= 2
    sub = result()["probes"]["git-write-worktree"]["sub_results"]
    assert result()["probes"]["git-write-worktree"]["status"] == "pass"
    assert sub["root-is-worktree"]["status"] == "pass"
    assert adapter()["sandbox_can_reach_common_gitdir"] == "true"
    assert not hr.writable_roots_needed(result())


def test_claude_golden_and_adapter_unmoved():
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    assert text.count("sandbox_can_reach_common_gitdir: true\n") == 1
    assert "schema_version: 1\n" in text
    claude = ha.load_adapter(os.path.join(TOOLKIT, "harness", "claude.yml"), toolkit=TOOLKIT)
    bad = [r for r in hr.parity(TOOLKIT, [claude["_path"]]) if r[3] != "in-parity"]
    assert bad == []


def test_config_files_stay_out_of_templates():
    for root, _dirs, files in os.walk(os.path.join(TOOLKIT, "templates")):
        for name in files:
            text = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
            assert "danger-full-access" not in text and 'approval_policy = "never"' not in text
    rendered = os.path.join(TOOLKIT, "harness", "codex", "rendered")
    for name in os.listdir(rendered):
        text = open(os.path.join(rendered, name), encoding="utf-8").read()
        assert "danger-full-access" not in text and 'approval_policy = "never"' not in text
