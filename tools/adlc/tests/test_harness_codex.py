"""REQ-655: the Codex CLI adapter.

Every case that writes runs in a sandbox: HOME and ADLC_HOME point under ``tmp_path``,
and projects are throwaway git repos. No case runs a real ``codex``: the binary on
PATH, where one is needed, is a stub. The real-tool evidence is in the spec.
"""

import copy
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import agents_render
import exec_adapter as ea
import exec_verify as ev
import fence_census as fc
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
    assert restrained == 18
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
    # REQ-662: the retired broad opener is no longer declared, and nothing renders it.
    assert "fence_broad_spelling" not in adapter()["capabilities"]
    assert '["if", "[", "-f", ".adlc/partials/"]' not in text
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
    """The committed render's mechanism (`confirm`) with a pass and the by-hand result: the
    record a project-scope restore needs. The shipped record is the exec engine's (`deny`)."""
    return variant(tmp_path, [(
        "prefix: {mechanism: deny, result: pass, harness_version: codex-cli 0.166.0, "
        "source: probe}",
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


# --------------------------------------------------------------------------- REQ-662: exec
#: What `codex --version` printed on the machine the result file was recorded on. Passed to
#: the verdict as the installed version: no test runs a real `codex`.
CODEX_VERSION = "codex-cli 0.166.0"
EXEC_WT = "/abs/repo/.worktrees/REQ-901"
EXEC_LAST = "/run/0123abcd/stdout.last-message.txt"
EXEC_BRANCH = "feat/REQ-901-sample"


def exec_codex(path=None):
    """The Codex adapter as the exec engine reads it: loaded through ``exec_adapter.load``."""
    if path is None:
        return ea.load("codex", TOOLKIT)
    return ea.ExecAdapter(ha.load_adapter(path, toolkit=TOOLKIT), TOOLKIT)


def with_exec(adapter, **keys):
    """``adapter`` reading an exec block with these keys replaced."""
    return ea.ExecAdapter(dict(adapter.adapter, exec=dict(adapter.block, **keys)), TOOLKIT)


def reading(changes):
    """The committed codex.json with ``{probe: status}`` or ``{probe/variant: status}`` changed,
    in memory: a fixture result that differs from the record in exactly those readings."""
    doc = copy.deepcopy(result())
    for key, status in changes.items():
        probe, _, sub = key.partition("/")
        if sub:
            doc["probes"][probe]["sub_results"][sub]["status"] = status
        else:
            doc["probes"][probe]["status"] = status
    return doc


def prefix_rules(text):
    """``[(decision, pattern)]`` of each ``prefix_rule`` line; every other line is a comment or
    blank."""
    out = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = hr._PREFIX_RULE_RE.match(line)
        assert match, line
        out.append((match.group(2), tuple(json.loads(match.group(1)))))
    return out


def test_codex_declares_prompt_delivery_and_is_verified():
    """AC-25, AC-11, BR-11: the block loads at exec schema 2, declares context_delivery:
    prompt, and the verdict over the committed codex.json reads verified. The same block
    declaring hooks reads unverified naming trust-then-headless and session-start-context;
    with allowlist-loaded failing, the prompt block reads unverified too. The yml's status and
    probes are caches the verdict checks, never the verdict."""
    adapter = exec_codex()
    block = adapter.block
    assert block["exec_schema_version"] == ha.EXEC_SCHEMA_VERSION == 2
    assert block["context_delivery"] == "prompt" and block["verification"] == "probes"
    assert block["harness_version"] == result()["harness_version"] == CODEX_VERSION
    verdict = ev.verdict(adapter, result(), CODEX_VERSION)
    assert verdict.verified, verdict.summary()
    assert verdict.doctor_line() == "exec: verified"
    # The readings the verdict stands on: hooks-loaded fails, which prompt does not need.
    assert verdict.readings["trust-then-headless"] == "fail"
    assert verdict.readings["trust-then-headless/hooks-loaded"] == "fail"
    assert verdict.readings["trust-then-headless/allowlist-loaded"] == "pass"
    assert result()["probes"]["session-start-context"]["status"] == "fail"
    hooks = ev.verdict(with_exec(adapter, context_delivery="hooks"), result(), CODEX_VERSION)
    assert hooks.subjects == ["trust-then-headless", "session-start-context"], hooks.summary()
    assert hooks.doctor_line() == "exec: unverified (trust-then-headless, session-start-context)"
    broken = ev.verdict(adapter, reading({"trust-then-headless/allowlist-loaded": "fail"}),
                        CODEX_VERSION)
    assert broken.subjects == ["trust-then-headless"] and "allowlist-loaded" in broken.summary()
    # exec.probes cites every required probe as the result file records it.
    cited = {row["id"]: row for row in block["probes"]}
    assert set(ev.required(block)) <= set(cited)
    for probe, row in cited.items():
        record = result()["probes"][probe]
        assert (row["status"], row["ran_at"], row["harness_version"]) == (
            record["status"], record["ran_at"], result()["harness_version"]), probe
    # A stale cache, another installed version, no binary and a result recorded under another
    # version each read unverified.
    stale = ev.verdict(with_exec(adapter, status="unverified"), result(), CODEX_VERSION)
    assert stale.subjects == ["status"]
    for installed in ("codex-cli 0.167.0", None):
        assert ev.verdict(adapter, result(), installed).subjects == ["installed-version"]
    other = dict(result(), harness_version="codex-cli 0.165.0")
    assert set(ev.verdict(adapter, other, CODEX_VERSION).subjects) == set(ev.required(block))
    assert not ev.verdict(adapter, None, CODEX_VERSION).verified


def test_exec_values_follow_the_result_file():
    """Every exec value that a probe decides reads what codex.json records (guess nothing):
    the delegation timeout, the refusal line, the output events and the stdin variant."""
    adapter = exec_codex()
    block = adapter.block
    probes = result()["probes"]
    assert probes["shell-timeout"]["status"] == "pass"
    assert block["shell_timeout_s"] == {"value": 125, "verified": "true",
                                        "delegate": "supported"}
    assert "sleep 125" in probes["shell-timeout"]["evidence"]["stdout_tail"]
    # The refusal line is the harness's stderr for the `forbidden` command, and the model's
    # stream of that launch does not hold it (LESSON-847).
    denied = probes["ask-tier-deny"]["sub_results"]["deny-under-allow"]["evidence"]
    line = adapter.refusal_line(denied["stderr_tail"])
    assert line and "rejected: policy forbids commands starting with" in line
    assert adapter.refusal_line(denied["stdout_tail"]) is None
    # A whole captured stream parses through the declared output: its session id is the
    # thread.started event's, and it ends with the terminal event.
    launch = probes["stdin-prompt"]["sub_results"][block["prompt_variant"]]["evidence"]
    stdout = launch["stdout_tail"]
    assert len(stdout.encode("utf-8")) == launch["stdout_bytes"], "the capture is cut"
    parsed = adapter.parse_result(stdout, last_message="the last message")
    thread = json.loads(stdout.splitlines()[0])
    assert thread["type"] == "thread.started"
    assert parsed["error"] is None and parsed["session_id"] == thread["thread_id"]
    assert block["output"]["final_message"] == "{last_message}"
    assert block["output"]["terminal_event"] == "turn.completed"
    # Nothing the probe cannot vouch for is declared: no extra allow (matcher: none), no
    # isolation flags, no second writable directory and no CODEX_HOME override.
    for key in ("allow_extra", "allow_extra_exact", "add_dir_flag", "config_isolation",
                "auth_env"):
        assert key not in block, key
    assert block["matcher"] == "none" and block["rules_reload"] == "unknown"
    assert "CODEX_HOME" not in block["env_passthrough"]


def test_codex_launch_argv_snapshot():
    """AC-2, BR-2, BR-16: the launch is `codex exec --json --sandbox workspace-write -C <wt> -o
    <file>` with the prompt on stdin, the argv the stdin-prompt variant it names ran; the
    resume is ADR-7's, measured on 2026-11-18 (`codex-exec-manual.md`, rows `resume-continues`
    and `resume-keeps-rules`, and fact 5). Neither holds a forbidden flag or `-p`, and a
    forbidden entry or a `-c`, `-p` or `--profile` token added to either is refused."""
    adapter = exec_codex()
    values = {"worktree": EXEC_WT, "last_message": EXEC_LAST}
    fresh = adapter.launch_argv("/bin/codex", [], [], values=values)
    assert fresh == ["/bin/codex", "exec", "--json", "--sandbox", "workspace-write", "-C",
                     EXEC_WT, "-o", EXEC_LAST]
    resumed = adapter.launch_argv("/bin/codex", [], [], resume="T-1", values=values)
    assert resumed == ["/bin/codex", "exec", "resume", "--json", "-o", EXEC_LAST, "T-1", "-"]
    with_model = adapter.launch_argv("/bin/codex", [], [], extra=["--model", "m"],
                                     values=values)
    assert with_model == fresh + ["--model", "m"]
    # The template is the argv the declared variant measured, path for path.
    variants = result()["probes"]["stdin-prompt"]["sub_results"]
    assert variants[adapter.block["prompt_variant"]]["status"] == "pass"
    measured = variants[adapter.block["prompt_variant"]]["evidence"]["command"]
    assert measured == ["codex"] + ea.substitute(adapter.template("launch"), {
        "worktree": measured[6], "last_message": measured[8]})
    # The other variant is this launch plus prompt_flag (its paths differ: another launch).
    flagged = variants["with-prompt-flag"]["evidence"]["command"]

    def shape(argv):
        return [tok for i, tok in enumerate(argv) if i not in (6, 8)]
    assert shape(flagged) == shape(measured) + adapter.block["prompt_flag"]
    for argv in (fresh, resumed):
        assert "-p" not in argv and ea.forbidden_in(argv, adapter.forbidden) is None
    for entry in adapter.block["forbidden_flags"]:
        assert "=" not in entry, entry
        with pytest.raises(ea.ExecRefused):
            adapter.launch_argv("/bin/codex", [], [], extra=entry.split(), values=values)
    pairs = {"operator": [], "isolation": False, "add_dir": None, "allow": [], "deny": []}
    for argv, template, vals in ((fresh, "launch", values),
                                 (resumed, "resume", dict(values, session_id="T-1"))):
        assert adapter.closed_world(argv, template, pairs, vals) == argv
        for token in (["-c", "sandbox_mode=danger-full-access"], ["-p", "x"],
                      ["--profile", "x"], ["--add-dir", "/tmp"]):
            with pytest.raises(ea.ExecRefused, match="closed world"):
                adapter.closed_world(argv + token, template, pairs, vals)
    with pytest.raises(ea.ExecRefused, match="operator_flags"):
        adapter.launch_argv("/bin/codex", [], [], extra=["--add-dir", "/tmp"], values=values)


def test_codex_exec_rule_files():
    """BR-3, BR-4, AC-4: the working-copy rule file holds the fence-runner allow once, a
    `forbidden` rule for every deny-tier and engine_deny entry, and no `git push`, `git branch`
    or `git -C` allow; the user policy file holds the same denies and no allow. Every loss the
    exec render reports is declared at `exec`, so the pre-flight's fidelity check passes, and
    no deny is deny_unsupported."""
    adapter = exec_codex()
    files = adapter.rule_files(EXEC_BRANCH, result=result())
    rules = prefix_rules(files.rule_file)
    assert {d for d, _p in rules} == {"allow", "forbidden"}
    allow = [p for d, p in rules if d == "allow"]
    forbidden = [p for d, p in rules if d == "forbidden"]
    runner = adapter.fence_runner()
    assert allow.count((runner,)) == 1 and runner.endswith("/tools/adlc/fence-run")
    for base in OMITTED:
        assert not [p for p in allow if p[:2] == tuple(base.split())], base
    deny = [tuple(c) for e in perms()["entries"] if e["tier"] == "deny" for c in e["commands"]]
    assert not [c for c in deny if any("*" in tok for tok in c)]
    engine = [tuple(c) for c in adapter.block["engine_deny"]]
    assert sorted(forbidden) == sorted(set(deny + engine))
    policy = prefix_rules(files.user_policy_file)
    assert {d for d, _p in policy} == {"forbidden"}
    assert sorted(p for _d, p in policy) == sorted(forbidden)
    assert adapter.tiers(EXEC_BRANCH, result=result()) == ([], [])
    verdict = ev.verdict(adapter, result(), CODEX_VERSION)
    report = adapter.exec_report(result(), verdict)
    assert report.undeclared == [] and report.deny_unsupported == []
    assert report.whole_tier is None
    losses = {(f.entry, f.command): f.verdict for f in report.findings if f.verdict != "exact"}
    for (entry, command), verdict_text in losses.items():
        assert hr.accepted(adapter.adapter, entry, command, "exec") == verdict_text
    assert losses[(hr.FENCE_ID, "if [ -f .adlc/partials/")] == "inexpressible"
    # Remove one exec verdict and the pre-flight's comparison names it.
    loaded = copy.deepcopy(adapter.adapter)
    del loaded["accepted_fidelity"]["git.write:git push"]["exec"]
    undeclared = ea.ExecAdapter(loaded, TOOLKIT).exec_report(result(), verdict).undeclared
    assert [(f.entry, f.command) for f in undeclared] == [("git.write", "git push")]


def test_strategy_agrees_with_the_gitdir_record_and_the_probe(tmp_path):
    """AC-9, BR-9: `worktree` agrees with the top-level sandbox_can_reach_common_gitdir record
    and with git-write-worktree in codex.json on every variant. A record that disagrees
    refuses the adapter at load naming both keys; a result where the probe disagrees reads
    unverified naming the probe and the record, with the declared value and the verdict."""
    adapter = exec_codex()
    assert adapter.strategy == "worktree"
    assert adapter.adapter["sandbox_can_reach_common_gitdir"] == "true"
    probe = result()["probes"]["git-write-worktree"]
    assert probe["status"] == "pass"
    assert {k: v["status"] for k, v in probe["sub_results"].items()} == {
        "root-is-worktree": "pass", "writable-roots-repo": "pass"}
    for record in ("false", "unverified"):
        path = variant(tmp_path, [("sandbox_can_reach_common_gitdir: true\n",
                                   "sandbox_can_reach_common_gitdir: %s\n" % record)])
        with pytest.raises(ha.AdapterError) as exc:
            ha.load_adapter(path, toolkit=TOOLKIT)
        assert exc.value.field == "exec.working_copy.strategy"
        assert "sandbox_can_reach_common_gitdir" in str(exc.value) and record in str(exc.value)
    failed = ev.verdict(adapter, reading({"git-write-worktree": "fail"}), CODEX_VERSION)
    assert {"git-write-worktree", "sandbox_can_reach_common_gitdir"} <= set(failed.subjects)
    details = {p.subject: p.detail for p in failed.problems}
    assert "worktree" in failed.summary() and "fail" in details["git-write-worktree"]
    assert "declares true" in details["sandbox_can_reach_common_gitdir"]
    one = ev.verdict(adapter, reading({"git-write-worktree/writable-roots-repo": "fail"}),
                     CODEX_VERSION)
    assert one.subjects == ["git-write-worktree"] and "writable-roots-repo" in one.summary()


def test_codex_census_golden_is_fresh_and_has_no_direct_route():
    """AC-24, BR-3, ADR-8, ADR-9: Codex is exec-capable, its block loads with fence_runner and
    without capabilities.fence_broad_spelling, and its committed census is a fresh one with no
    `direct` route and none unrouted. The Step 0 branch push is the one push the runner makes."""
    adapter = exec_codex()
    assert adapter.block["fence_runner"] == "tools/adlc/fence-run"
    assert "fence_broad_spelling" not in adapter.adapter["capabilities"]
    assert "codex" in [a.name for a in fc.exec_adapters(TOOLKIT)]
    records = fc.census(TOOLKIT, adapter)
    with open(os.path.join(TOOLKIT, fc.golden_path("codex")), encoding="utf-8") as fh:
        assert fh.read() == fc.dumps(fc.golden_doc(records)), "run fence_census.py --write"
    assert [r["id"] for r in records if r["route"] == "direct"] == []
    assert fc.unrouted(records) == []
    [push] = [r for r in records if r.get("push")]
    assert push["route"] == "runner" and push["push"] == fc.BRANCH_PUSH
    assert push["id"].startswith("proceed/phase-0-setup.md#")


LIVE_SCRIPT = os.path.join(TOOLKIT, "tools", "adlc", "tests", "e2e", "codex-exec-live.py")
#: What the live script must call by these names; a rename that leaves it stale fails here.
LIVE_CALLS = {
    "adapter": ("launch_argv", "child_env", "rule_files", "parse_result", "refusal_line",
                "can_resume"),
    "esf": ("render", "working_copy_render", "install_policy_file", "policy_path",
            "record_path", "verify"),
    "et": ("grant", "revoke", "user_config_path", "probe_marker"),
    "fr": ("runner_call",),
    "fc": ("census", "fences", "view"),
}


def _live_tree():
    import ast
    with open(LIVE_SCRIPT, encoding="utf-8") as fh:
        return ast.parse(fh.read(), LIVE_SCRIPT)


def test_the_codex_live_script_calls_what_the_engine_has():
    """REQ-662 TASK-266: `tools/adlc/tests/e2e/codex-exec-live.py` is never run by pytest (its
    name is no test module's), so nothing ran its calls into the engine. This reads it with
    `ast`: every attribute it takes from an engine module it imports, and every one it takes
    from the loaded Codex adapter, must exist, so a renamed function cannot leave the script
    stale unnoticed."""
    import ast
    import importlib
    assert not os.path.basename(LIVE_SCRIPT).startswith("test_")
    tree = _live_tree()
    modules = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if os.path.isfile(os.path.join(TOOLKIT, "tools", "adlc", alias.name + ".py")):
                    modules[alias.asname or alias.name] = importlib.import_module(alias.name)
    assert {"ea", "esf", "et", "ev", "fc", "fr", "hp", "adlc_home"} <= set(modules)
    owners = dict(modules, adapter=exec_codex())
    used = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and \
                node.value.id in owners:
            used.setdefault(node.value.id, set()).add(node.attr)
    missing = sorted("%s.%s" % (owner, attr) for owner, attrs in used.items()
                     for attr in attrs if not hasattr(owners[owner], attr))
    assert missing == []
    for owner, attrs in LIVE_CALLS.items():
        assert set(attrs) <= used.get(owner, set()), (owner, set(attrs) - used.get(owner, set()))


def test_the_codex_live_script_grants_under_the_real_probe_marker():
    """REQ-662 BR-5: the live script edits the real user config, so its grant must refuse while
    a probe run is mid-recovery, as the engine's does: the marker it passes is
    `et.probe_marker(adlc_home.adlc_home(), HARNESS)`, never a path of its own."""
    import ast
    grants = [node for node in ast.walk(_live_tree()) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == "grant"
              and isinstance(node.func.value, ast.Name) and node.func.value.id == "et"]
    assert len(grants) == 1
    marker = grants[0].args[4]
    assert ast.dump(marker) == ast.dump(ast.parse(
        "et.probe_marker(adlc_home.adlc_home(), HARNESS)", mode="eval").body)


def test_codex_bypass_scan_refuses_sandbox_permissions(sandbox):
    """REQ-662 BR-16: `sandbox_permissions` widens what the sandbox admits (`codex exec --help`
    at 0.166.0 gives `-c 'sandbox_permissions=["disk-full-read-access"]'` as its own example of
    an override), so it is a bypass key of the user config and of the working copy's config:
    set in either, it is a hit, which refuses the run. Neither file set is the clean case."""
    import exec_surfaces as esf
    adapter = exec_codex()
    for keys in adapter.block["bypass_config_keys"].values():
        assert "sandbox_permissions" in keys
    env = {"HOME": os.environ["HOME"]}
    wt = sandbox / "wt"
    (wt / ".codex").mkdir(parents=True)
    assert esf.bypass_scan(adapter, [str(wt)], env) == []
    line = 'sandbox_permissions = ["disk-full-read-access"]\n'
    user = os.path.join(env["HOME"], ".codex", "config.toml")
    os.makedirs(os.path.dirname(user))
    with open(user, "w", encoding="utf-8") as fh:
        fh.write(line)
    (wt / ".codex" / "config.toml").write_text(line, encoding="utf-8")
    hits = esf.bypass_scan(adapter, [str(wt)], env)
    assert sorted((os.path.basename(os.path.dirname(os.path.dirname(h.path))), h.key)
                  for h in hits) == [("home", "sandbox_permissions"), ("wt", "sandbox_permissions")]
