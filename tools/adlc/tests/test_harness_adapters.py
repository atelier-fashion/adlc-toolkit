"""REQ-656: the Copilot CLI and Cursor adapters on the REQ-657 framework.

Every case that writes runs in a sandbox: HOME and ADLC_HOME point under
``tmp_path``, projects are throwaway git repos, binaries are fakes on a sandbox
PATH. No real copilot or agent binary is run, so nothing here is evidence of what
either harness does: that is BR-13's dogfood, which is owed (spec, Deferred).
"""

import hashlib
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
COPILOT_YML = os.path.join(TOOLKIT, "harness", "copilot.yml")
CURSOR_YML = os.path.join(TOOLKIT, "harness", "cursor.yml")
SYSTEM_PATH = "/usr/bin:/bin"
SHAPES = ("prefix", "git-c", "env-prefix", "shell-opener")


# --------------------------------------------------------------------------- helpers
@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ADLC_HOME", str(home / ".claude"))
    return tmp_path


def perms():
    return ha.load_permissions(ha.permissions_path(TOOLKIT))


def copilot():
    return ha.load_adapter(COPILOT_YML, toolkit=TOOLKIT)


def cursor():
    return ha.load_adapter(CURSOR_YML, toolkit=TOOLKIT)


def variant(tmp_path, src_path, edits):
    """A copy of a shipped adapter with ``(old, new)`` edits, same basename."""
    src = open(src_path, encoding="utf-8").read()
    for old, new in edits:
        assert old in src, old
        src = src.replace(old, new, 1)
    d = tmp_path / ("v%d" % len(list(tmp_path.glob("v*"))))
    d.mkdir()
    path = d / os.path.basename(src_path)
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


def fake_bin(bindir, name):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text("#!/bin/sh\necho '%s 9.9.9'\n" % name)
    p.chmod(0o755)
    return str(bindir)


def init_fence():
    text = open(os.path.join(TOOLKIT, "init", "SKILL.md"), encoding="utf-8").read()
    section = text[text.index("### Step 8:"):text.index("### Step 9:")]
    body = section[section.index("```bash\n") + 8:]
    return body[:body.index("```")]


def run_init(proj, harnesses, path=SYSTEM_PATH):
    """`/init` Step 8 exactly as the skill carries it."""
    literal = "''" if harnesses is None else shlex.quote(harnesses)
    fence = init_fence().replace("'<harnesses>'", literal)
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"], "PATH": path,
           "CLAUDE_PLUGIN_ROOT": TOOLKIT}
    proc = subprocess.run(["/bin/sh", "-c", fence], cwd=str(proj), env=env, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc


def printed(adapter=None):
    return hr.printed_text(adapter or copilot(), TOOLKIT)


def flags(line):
    """``(allow, deny)`` lists of the printed line's ``shell(...)`` patterns."""
    tokens = shlex.split(line)
    assert tokens[0] == "copilot"
    allow = [tokens[i + 1] for i, t in enumerate(tokens) if t == "--allow-tool"]
    deny = [tokens[i + 1] for i, t in enumerate(tokens) if t == "--deny-tool"]
    assert len(allow) + len(deny) == (len(tokens) - 1) / 2, line
    return allow, deny


def inner(pattern):
    """A ``shell(...)`` or ``Shell(...)`` pattern's text, ``:*`` removed."""
    m = re.fullmatch(r"[Ss]hell\((.*?)(:\*)?\)", pattern)
    assert m, pattern
    return m.group(1)


def deny_commands():
    return [(e["id"], tuple(c)) for e in perms()["entries"] if e["tier"] == "deny"
            for c in e["commands"]]


def cursor_files():
    plans, _p = hr.plan_surfaces(cursor(), "project", TOOLKIT, TOOLKIT,
                                 surfaces=("permissions", "hooks"))
    return {os.path.basename(p.rel): json.loads(p.content) for p in plans}


# --------------------------------------------------------------------------- BR-1 / AC-1
def test_adapters_load():
    for adapter in (copilot(), cursor()):
        assert adapter["schema_version"] == 2
        assert adapter["trust"]["mechanism"] == "flag"
        assert adapter["paths"]["skills"]["user"] == "$HOME/.agents/skills"
        assert adapter["paths"]["instructions"]["project"] == "AGENTS.md"
        assert list(adapter["tier_map"].values()) == ["unverified"] * 3
        assert list(adapter["hook_payload"].values()) == ["unsupported"] * 3
        dua = adapter["capabilities"]["deny_under_allow"]
        assert sorted(dua) == sorted(SHAPES)
        assert {r["result"] for r in dua.values()} == {"unverified"}
        assert adapter["capabilities"]["subagent_start_hook"] == "no"
    assert copilot()["deny_tier_render"] == {"user": "deny"}
    assert cursor()["deny_tier_render"] == {"project": "deny"}
    assert copilot()["capabilities"]["git_c_spelling"] == [["git", "-C"]]
    assert cursor()["capabilities"]["git_c_spelling"] == []
    assert copilot()["binary"] == "copilot" and cursor()["binary"] == "agent"


def test_claude_adapter_is_untouched():
    claude = ha.load_adapter(os.path.join(TOOLKIT, "harness", "claude.yml"), toolkit=TOOLKIT)
    assert claude["schema_version"] == 1
    assert not {"hook_output", "fidelity_notes"} & set(claude)


REQUIRED_LINES = [
    (COPILOT_YML, "name: copilot\n", "name"), (COPILOT_YML, "binary: copilot\n", "binary"),
    (COPILOT_YML, "schema_version: 2\n", "schema_version"),
    (COPILOT_YML, "  Grep: search\n", "tool_map.Grep"),
    (COPILOT_YML, "  session-compact: unsupported\n", "hook_events.session-compact"),
    (COPILOT_YML, "  session_id: unsupported\n", "hook_payload.session_id"),
    (COPILOT_YML, "  deny: \"yes\"\n", "capabilities.deny"),
    (CURSOR_YML, "name: cursor\n", "name"), (CURSOR_YML, "binary: agent\n", "binary"),
    (CURSOR_YML, "  Grep: unsupported\n", "tool_map.Grep"),
    (CURSOR_YML, "  allowlist_granularity: command-base\n", "capabilities.allowlist_granularity"),
]


@pytest.mark.parametrize("src, line, field", REQUIRED_LINES)
def test_loader_rejects_a_missing_field(tmp_path, src, line, field):
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(variant(tmp_path, src, [(line, "")]), toolkit=TOOLKIT)
    assert field in str(exc.value) or "name" in field and "basename" in str(exc.value)


@pytest.mark.parametrize("src, edit, field", [
    (COPILOT_YML, ("user: $HOME/.copilot/agents", "user: ~/.copilot/agents"), "paths.agents.user"),
    (CURSOR_YML, ("target: $HOME/.claude/agents", "target: ~/.claude/agents"),
     "doctor_rows[2].target"),
    (CURSOR_YML, ("schema_version: 2", "schema_version: 1"), "needs schema_version 2"),
    (COPILOT_YML, ("schema_version: 2", "schema_version: 1"), "needs schema_version 2"),
    (CURSOR_YML, ("format: cursor-terminal-allowlist", "format: agents-md"), "also[0].format"),
    (CURSOR_YML, ("project: .cursor/permissions.json", "project: /etc/x.json"),
     "also[0].project"),
    (COPILOT_YML, ("ethos-inject: json:additionalContext", "ethos-inject: plain"),
     "hook_output.ethos-inject"),
    (COPILOT_YML, ("ethos-inject: json:additionalContext", "bogus-hook: json:x"),
     "hook_output.bogus-hook"),
])
def test_loader_refuses_bad_schema_2_fields(tmp_path, src, edit, field):
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(variant(tmp_path, src, [edit]), toolkit=TOOLKIT)
    assert field in str(exc.value)


def test_no_literal_home_in_harness():
    pat = re.compile(r"~/\.claude|~/\.copilot|~/\.cursor")
    hits = []
    for dirpath, _dirs, files in os.walk(os.path.join(TOOLKIT, "harness")):
        for fn in files:
            path = os.path.join(dirpath, fn)
            if pat.search(open(path, encoding="utf-8").read()):
                hits.append(path)
    assert hits == []


# --------------------------------------------------------------------------- BR-2 / AC-2
def test_rule_b_over_every_render(sandbox):
    body, findings, remedies = printed()
    assert body.count("\n") == 1, "the printed render is one line"
    # The line's flags, not the text inside a deny's pattern (`git push --force` is
    # meant to be there): no --allow-all-tools, --force, --yolo or anything else.
    assert set(shlex.split(body)[1::2]) == {"--allow-tool", "--deny-tool"}
    allow, deny = flags(body)
    assert not [p for p in allow if inner(p) in ("", "*") or "*" in inner(p)], allow
    gran = copilot()["capabilities"]["allowlist_granularity"]
    allow_spellings = [(tuple(inner(p).split()), not p.endswith(":*)")) for p in allow]

    files = cursor_files()
    cli = files["cli.json"]["permissions"]
    terminal = files["permissions.json"]["terminalAllowlist"]
    for text in (json.dumps(cli), json.dumps(terminal)):
        assert "*" not in text and "--" not in text
    cursor_allow = [inner(p) for p in cli["allow"]]

    for _id, dcmd in deny_commands():
        forms = [form for _s, form in hr.deny_forms(dcmd)]
        if dcmd[0] == "git":
            forms.append(("git", "-C", "/some/path") + dcmd[1:])
        for form in forms:
            for spelling, exact in allow_spellings:
                assert not hr.allow_matches(spelling, exact, gran, form, True), (spelling, form)
            for base in cursor_allow + terminal:
                assert not hr.allow_matches((base,), False, "command-base", form, False), \
                    (base, form)

    # Every deny-tier entry is denied, or declared deny-unsupported and in the report.
    for name, adapter, denied in (("copilot", copilot(), {inner(p) for p in deny}),
                                  ("cursor", cursor(), {inner(p) for p in cli["deny"]})):
        scope = hr.gated_scope(adapter)
        _f, failures = hr.fidelity(adapter, perms())
        assert failures == [], failures
        rules, find, _x = hr.render_permissions(adapter, perms(), scope)
        for did, dcmd in deny_commands():
            spelled = [r for r in rules if r.kind == "deny" and r.argv == dcmd]
            if spelled:
                assert hr._cmd(spelled[0].spelling) in denied
            else:
                assert hr.accepted(adapter, did, hr._cmd(dcmd), scope) == "deny-unsupported"
                assert [f for f in find if f.entry == did and f.command == hr._cmd(dcmd) and
                        f.verdict == "deny-unsupported"]

    # Exactly one --deny-tool per argv prefix, counted per prefix (no entry is dropped).
    assert sorted(inner(p) for p in deny) == sorted(hr._cmd(d) for _i, d in deny_commands())
    assert all(p.endswith(":*)") for p in deny)

    # No rendered allow has a first token in BR-2's set.
    firsts = [s[0] for s, _e in allow_spellings] + cursor_allow + terminal
    for token in firsts:
        assert not hr.forbidden_first_token((token,)), token
    for token in ("if", "sh", "bash", "zsh", "env", "xargs", "eval", "exec", "sudo", "time",
                  "command", "nohup", "python", "python3", "node"):
        assert hr.forbidden_first_token((token, "x"))
    assert not hr.forbidden_first_token(("git", "status"))

    # The broad fence spelling exists only as a labelled, separate remedy.
    broad = hr._cmd(copilot()["capabilities"]["fence_broad_spelling"])
    assert broad not in body
    labelled = [r for r in remedies if broad in r]
    assert labelled and all(r.startswith("WIDENING, not applied") for r in labelled)


def test_a_forbidden_first_token_is_omitted_and_reported(tmp_path):
    src = open(ha.permissions_path(TOOLKIT), encoding="utf-8").read()
    extra = src.replace("  - id: shell.pwd\n",
                        "  - id: shell.run\n    tier: routine\n    note: nope\n"
                        "    commands:\n      - [env, FOO=1]\n      - [python3, -c]\n"
                        "  - id: shell.pwd\n", 1)
    path = tmp_path / "permissions.yml"
    path.write_text(extra, encoding="utf-8")
    p = ha.load_permissions(str(path))
    for adapter in (copilot(), cursor()):
        rules, findings, _x = hr.render_permissions(adapter, p, hr.gated_scope(adapter))
        assert not any(r.entry == "shell.run" for r in rules)
        verdicts = [f.verdict for f in findings if f.entry == "shell.run"]
        assert verdicts == ["inexpressible", "inexpressible"]
    hand = [hr.Rule("shell.run", ("env", "x"), "routine", "allow", ("env", "x"), False)]
    assert any("runs its arguments" in m for m in hr.evaluate_rules(copilot(), perms(), hand,
                                                                    "printed"))


def test_clash_reads_candidates_not_survivors():
    """REQ-656 ADR-4: `Shell(git)` must read as shared, not deny all of git."""
    rules, findings, _x = hr.render_permissions(cursor(), perms(), "project")
    assert ("git",) not in {r.spelling for r in rules}
    assert ("gh",) not in {r.spelling for r in rules}
    assert {f.verdict for f in findings if f.entry == "gh.merge"} == {"deny-unsupported"}


# --------------------------------------------------------------------------- BR-3 / AC-3
def test_copilot_agents(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    first = run_cli(["agents", "render", "--harness", "copilot"], proj)
    assert first.returncode == 0, first.stderr
    dest = os.path.join(os.environ["HOME"], ".copilot", "agents")
    names = sorted(os.listdir(dest))
    canon = sorted(f[:-3] for f in os.listdir(os.path.join(TOOLKIT, "agents"))
                   if f.endswith(".md"))
    assert names == ["%s.agent.md" % n for n in canon]
    review = open(os.path.join(dest, "correctness-reviewer.agent.md"), encoding="utf-8").read()
    fm, _body = hr.split_agent(review)
    assert "tools: read, search, execute" in fm
    impl = open(os.path.join(dest, "task-implementer.agent.md"), encoding="utf-8").read()
    assert not any(l.startswith("tools:") for l in hr.split_agent(impl)[0])
    assert not (proj / ".github").exists() and os.listdir(str(proj)) == [".git"]
    second = run_cli(["agents", "render", "--harness", "copilot"], proj)
    assert ", 0 changed" in second.stdout
    bad = variant(tmp_path, COPILOT_YML, [("  Grep: search\n", "")])
    proc = run_cli(["agents", "render", "--adapter-path", bad, "--harness", "copilot"], proj)
    assert proc.returncode == 2 and "tool_map" in proc.stderr
    assert run_cli(["harness", "render", "--check"], proj).returncode == 0


def test_agent_body_rewrites_tool_names_only():
    a = copilot()
    text = ("---\nname: x\ntools: Read, Bash\n---\n\n"
            "Write tests first.\n1. Write down the plan.\n- Read the file.\n"
            "Do not use the Edit or Write tools. Use Grep, then Read to verify.\n")
    body = hr.split_agent(hr.render_agent_copy(a, "x", text, None, []))[1]
    assert "Write tests first." in body and "1. Write down the plan." in body
    assert "- Read the file." in body
    assert "Do not use the edit or edit tools. Use search, then read to verify." in body


def test_harness_render_user_scope_writes_copies_project_scope_does_not(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_cli(["harness", "render", "--harness", "copilot"], proj)
    assert proc.returncode == 0 and "adlc harness install --harness copilot" in proc.stdout
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".copilot"))
    proc = run_cli(["harness", "render", "--harness", "copilot", "--scope", "user", "--dry-run"],
                   proj)
    assert proc.returncode == 0 and not os.path.exists(
        os.path.join(os.environ["HOME"], ".copilot"))
    proc = run_cli(["harness", "render", "--harness", "copilot", "--scope", "user"], proj)
    assert proc.returncode == 0, proc.stderr
    assert len(os.listdir(os.path.join(os.environ["HOME"], ".copilot", "agents"))) == 19


def test_install_writes_user_surfaces_only(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_cli(["harness", "install", "--harness", "copilot"], proj)
    assert proc.returncode == 0, proc.stderr
    assert len(os.listdir(os.path.join(os.environ["HOME"], ".copilot", "agents"))) == 19
    assert sorted(os.listdir(os.path.join(os.environ["HOME"], ".copilot"))) == ["agents"]
    assert os.listdir(str(proj)) == [".git"]
    proc = run_cli(["harness", "install", "--harness", "cursor"], proj)
    assert proc.returncode == 0 and "nothing to write" in proc.stdout
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".cursor"))


# --------------------------------------------------------------------------- BR-4 / AC-4
def test_tier_map_omits_model(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_cli(["agents", "render", "--harness", "copilot"], proj)
    dest = os.path.join(os.environ["HOME"], ".copilot", "agents")
    for fn in os.listdir(dest):
        assert not any(l.startswith("model:") for l in hr.split_agent(
            open(os.path.join(dest, fn), encoding="utf-8").read())[0])
    notices = [l for l in proc.stderr.splitlines() if "tier_map" in l]
    assert len(notices) == len(set(notices)) and notices
    path = variant(tmp_path, COPILOT_YML, [("  opus: unverified", "  opus: copilot-opus-x")])
    a = ha.load_adapter(path, toolkit=TOOLKIT)
    cfg = {"classes": {}, "overrides": {}}
    plans, _n = agents_render.plan_copies(a, TOOLKIT, cfg)
    with_model = [n for n, _p, t in plans if "model: copilot-opus-x" in hr.split_agent(t)[0]]
    resolved = [n for n, _p, _t in plans if agents_render.resolve_model(n, cfg, "copilot") == "opus"]
    assert with_model and sorted(with_model) == sorted(resolved)
    assert agents_render.check_drift(TOOLKIT, cfg) == []    # the claude render is unchanged


# --------------------------------------------------------------------------- BR-5 / AC-5
def _hook_doc(proj):
    return json.load(open(proj / ".github" / "hooks" / "adlc.json", encoding="utf-8"))


def _run_hook(cmd, cwd, plugin_root=None):
    env = {"HOME": os.environ["HOME"], "PATH": SYSTEM_PATH}
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    return subprocess.run(["/bin/sh", "-c", cmd], cwd=str(cwd), env=env, input="",
                          capture_output=True, text=True, timeout=30)


def test_copilot_hooks(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    (proj / ".adlc").mkdir()
    ethos = "Principle \"one\"\n\tindented \\ backslash\n"
    (proj / ".adlc" / "ETHOS.md").write_text(ethos, encoding="utf-8")
    run_init(proj, "copilot")
    doc = _hook_doc(proj)
    assert doc["version"] == 1 and sorted(doc["hooks"]) == ["sessionStart", "subagentStart"]
    start, sub = doc["hooks"]["sessionStart"], doc["hooks"]["subagentStart"]
    assert [h["bash"].splitlines()[-1].split()[0] for h in start] == \
        ["adlc_ethos_inject", "adlc_session_record"]
    assert [h["bash"].splitlines()[-1].split()[0] for h in sub] == ["adlc_ethos_inject"]
    assert {h["timeoutSec"] for h in start + sub} == {10}
    assert {h["type"] for h in start + sub} == {"command"}

    ran = _run_hook(start[0]["bash"], proj, TOOLKIT)
    assert ran.returncode == 0 and ran.stderr == ""
    assert json.loads(ran.stdout) == {"additionalContext": ethos}

    (proj / ".adlc" / "ETHOS.md").unlink()
    ran = _run_hook(start[0]["bash"], proj, TOOLKIT)
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "", "")

    record = start[1]["bash"]
    assert record.endswith("adlc_session_record --harness copilot")
    assert "--context-key" not in record
    claude = json.load(open(os.path.join(TOOLKIT, "harness", "claude", "rendered",
                                         "settings.json"), encoding="utf-8"))
    claude_record = claude["hooks"]["SessionStart"][0]["hooks"][1]["command"]
    assert claude_record.endswith("adlc_session_record") and "--harness" not in claude_record
    assert ". .adlc/partials/session-record.sh; else" in record

    bare = tmp_path / "bare"
    bare.mkdir()
    for hook in start:
        ran = _run_hook(hook["bash"], bare)
        assert (ran.returncode, ran.stdout, ran.stderr) == (0, "", "")

    text = (proj / ".github" / "hooks" / "adlc.json").read_text(encoding="utf-8")
    assert os.environ["HOME"] not in text
    before = text
    run_init(proj, "copilot")
    assert (proj / ".github" / "hooks" / "adlc.json").read_text(encoding="utf-8") == before


def test_plain_stdout_is_kept_for_claude(tmp_path):
    """The `claude` render stays plain stdout: hook_output is the adapter's, not global."""
    block, _f = hr.render_hooks(ha.load_adapter(os.path.join(TOOLKIT, "harness", "claude.yml"),
                                                toolkit=TOOLKIT),
                                ha.load_hooks(ha.hooks_path(TOOLKIT)))
    text = json.dumps(block)
    assert "--context-key" not in text


def test_template_drift_reports_the_opted_in_layers(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    plain = run_cli(["harness", "drift", "--harness", "claude", "--opted-in"], proj)
    assert "copilot" not in plain.stdout and "cursor" not in plain.stdout
    run_init(proj, "claude,copilot,cursor")
    proc = run_cli(["harness", "drift", "--harness", "claude", "--opted-in"], proj)
    assert proc.returncode == 0, proc.stdout
    for line in ("harness-config claude .claude/settings.json: synced",
                 "harness-config copilot .github/hooks/adlc.json: synced",
                 "harness-config cursor .cursor/cli.json: synced",
                 "harness-config cursor .cursor/permissions.json: synced"):
        assert line in proc.stdout
    # A dropped deny and a dropped hook are named, whatever the rest of the file says.
    cli = proj / ".cursor" / "cli.json"
    doc = json.loads(cli.read_text())
    doc["permissions"]["deny"].remove("Shell(rm)")
    cli.write_text(json.dumps(doc))
    hooks = proj / ".github" / "hooks" / "adlc.json"
    doc = json.loads(hooks.read_text())
    del doc["hooks"]["subagentStart"]
    hooks.write_text(json.dumps(doc))
    term = proj / ".cursor" / "permissions.json"
    doc = json.loads(term.read_text())
    doc["terminalAllowlist"].remove("npm")
    term.write_text(json.dumps(doc))
    proc = run_cli(["harness", "drift", "--harness", "claude", "--opted-in"], proj)
    assert proc.returncode == 1
    assert "missing deny-tier rule (deny): Shell(rm)" in proc.stdout
    assert "missing or changed hook: subagentStart" in proc.stdout
    assert "missing routine rule: npm" in proc.stdout


# --------------------------------------------------------------------------- BR-6 / AC-6
def test_printed_line(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_init(proj, "copilot")
    line = [l for l in proc.stdout.splitlines() if l.startswith("copilot --allow-tool")]
    assert len(line) == 1
    render = run_cli(["harness", "render", "--harness", "copilot"], proj)
    assert render.returncode == 0 and line[0] in render.stdout
    allow, deny = flags(line[0])
    for want in ("shell(git status:*)", "shell(gh pr view:*)", "shell(gh pr create:*)",
                 "shell(npm test:*)", "shell(gh api:*)", "shell(git worktree:*)",
                 "shell(npm ci)", "shell(pwd)", "shell(git config user.email)"):
        assert want in allow, want
    for absent in ("git push", "git branch", "git -C", "if [ -f .adlc/partials/"):
        assert not [p for p in allow if inner(p) == absent], absent
    for want in ("git push --force", "git branch -D", "gh pr merge", "terraform apply",
                 "rm -rf", "./deploy.sh", "gh release"):
        assert [p for p in deny if inner(p) == want], want
    assert copilot()["deny_tier_render"] == {"user": "deny"}

    for needle in ("git.read [git branch] inexpressible", "git.write [git push] inexpressible",
                   "git.read [git -C] inexpressible", "git.write [git -C] inexpressible",
                   "git.config.identity [git -C] inexpressible",
                   "fence.partial-source [if [ -f .adlc/partials/] inexpressible",
                   "will prompt", "every `git -C ...` call will prompt",
                   "subcommand granularity admits"):
        assert needle in render.stderr, needle
    _findings, failures = hr.fidelity(copilot(), perms())
    assert failures == []
    table = copilot()["accepted_fidelity"]
    assert sum(1 for k in table if k.endswith(":git -C")) == 3
    assert not os.path.exists(os.path.join(os.environ["HOME"], ".copilot"))


def test_unverified_records_are_not_checked_but_a_pass_is(tmp_path):
    """Only a `pass` must equal a result file, so a fresh adapter lints clean."""
    assert hr.fidelity(copilot(), perms(), None)[1] == []
    path = variant(tmp_path, COPILOT_YML, [(
        "prefix: {mechanism: deny, result: unverified",
        "prefix: {mechanism: deny, result: pass")])
    _f, failures = hr.fidelity(ha.load_adapter(path, toolkit=TOOLKIT), perms(), None)
    assert any("no REQ-664 result file" in m for m in failures)


# --------------------------------------------------------------------------- BR-7 / AC-7
def test_one_instruction_file(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    run_init(proj, "copilot")
    run_init(proj, "cursor")
    assert (proj / "AGENTS.md").is_file()
    assert not (proj / ".github" / "copilot-instructions.md").exists()
    assert not (proj / ".cursor" / "rules").exists()
    md = sorted(p.name for p in proj.iterdir() if p.suffix == ".md")
    assert md == ["AGENTS.md"]


# --------------------------------------------------------------------------- BR-8 / AC-8
def test_cursor_permissions(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_init(proj, "cursor")
    cli = json.loads((proj / ".cursor" / "cli.json").read_text())
    ide = json.loads((proj / ".cursor" / "permissions.json").read_text())

    allow, deny = cli["permissions"]["allow"], cli["permissions"]["deny"]
    assert sorted(inner(p) for p in allow) == sorted(ide["terminalAllowlist"])
    assert list(ide) == ["terminalAllowlist"], "the IDE file has no deny key"
    for want in ("Shell(terraform)", "Shell(rm)", "Shell(./deploy.sh)"):
        assert want in deny
    assert deny.count("Shell(rm)") == 1 and deny.count("Shell(terraform)") == 1
    for absent in ("Shell(git)", "Shell(gh)", "Shell(if)", "Shell(sh)", "Shell(bash)",
                   "Shell(gcloud)"):
        assert absent not in allow and absent not in deny
    assert allow.count("Shell(npm)") == 1
    assert not [e for e in allow + deny if " " in e], "no entry names a subcommand"

    a = cursor()
    assert a["deny_tier_render"] == {"project": "deny"}
    table = a["accepted_fidelity"]
    for eid in ("git.read", "git.write", "git.config.identity", "gh.read", "gh.pr.create",
                "gh.api", "fence.partial-source"):
        assert table[eid] == "inexpressible", eid
    for eid in ("git.push.force", "git.reset.hard", "git.clean", "git.branch.force-delete",
                "gh.merge", "gh.pr.close", "gh.release"):
        assert table[eid] == "deny-unsupported", eid
    assert table["test.npm"] == "widened:npm" and table["npm.ci"] == "widened:npm"
    assert table["npm.install:npm install"] == "widened:npm"
    assert table["rm.recursive"] == "widened:rm" and table["rm.force"] == "widened:rm"
    assert table["terraform"] == "widened:terraform"

    for needle in ("git.read [git status] inexpressible", "gh.merge [gh pr merge] deny-unsupported",
                   "`git` and `gh` will prompt", "widened to the whole command: `npm`, `pwd`, "
                   "`rm`, `terraform`", "has no deny key", "fence.partial-source is not committed"):
        assert needle in proc.stderr, needle
    home = os.environ["HOME"]
    for rel in ("cli.json", "permissions.json"):
        assert home not in (proj / ".cursor" / rel).read_text()


# --------------------------------------------------------------------------- BR-9 / AC-9
def test_cursor_agents_render_is_a_noop(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    home_before = sorted(os.listdir(os.environ["HOME"]))
    proc = run_cli(["agents", "render", "--harness", "cursor"], proj)
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.strip().splitlines()) == 1
    assert "~/.claude/agents" in proc.stdout
    assert sorted(os.listdir(os.environ["HOME"])) == home_before
    assert os.listdir(str(proj)) == [".git"]
    render = run_cli(["harness", "render", "--harness", "cursor"], proj)
    assert render.returncode == 0
    wrote = {os.path.relpath(os.path.join(d, f), str(proj))
             for d, _dirs, fs in os.walk(str(proj)) if ".git" not in d.split(os.sep) for f in fs}
    assert wrote == {".cursor/cli.json", ".cursor/permissions.json", "AGENTS.md"}
    a = cursor()
    assert a["paths"]["agents"]["mode"] == "via:claude"
    assert a["paths"]["hooks"]["mode"] == "via:claude"


# --------------------------------------------------------------------------- BR-10 / AC-10
def _checksum(root):
    h = hashlib.sha256()
    for dirpath, dirs, files in sorted(os.walk(root)):
        dirs.sort()
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            h.update(path.encode())
            with open(path, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def test_doctor_rows_and_currency(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    checks = "harness:copilot,harness:cursor,render-currency:copilot"
    nobin = run_cli(["doctor", "--checks", checks], proj)
    for cid in checks.split(","):
        assert "[SKIP] %s" % cid in nobin.stdout, nobin.stdout
    bindir = tmp_path / "bin"
    path = fake_bin(bindir, "copilot") + ":" + SYSTEM_PATH
    assert run_cli(["agents", "render", "--harness", "copilot"], proj).returncode == 0
    os.unlink(os.path.join(os.environ["HOME"], ".copilot", "agents", "reflector.agent.md"))
    before = _checksum(os.environ["HOME"])
    bad = run_cli(["doctor", "--checks", "harness:copilot,render-currency:copilot"], proj,
                  path=path)
    assert _checksum(os.environ["HOME"]) == before, "doctor writes nothing"
    assert "[FAIL] render-currency:copilot" in bad.stdout, bad.stdout
    assert "[FAIL] harness:copilot" not in bad.stdout
    assert "report-only" in bad.stdout
    fix = re.search(r"-> fix: (.*)", bad.stdout).group(1)
    assert fix == "adlc agents render --harness copilot"
    assert run_cli(fix.split()[1:], proj).returncode == 0
    good = run_cli(["doctor", "--checks", "render-currency:copilot"], proj, path=path)
    assert "[PASS] render-currency:copilot" in good.stdout, good.stdout
    assert "deny_under_allow: prefix=unverified" in good.stdout

    path = fake_bin(bindir, "agent") + ":" + SYSTEM_PATH
    out = run_cli(["doctor", "--checks", "harness:cursor"], proj, path=path).stdout
    assert "[FAIL]" not in out
    for fact in ("~/.claude/skills", "~/.claude/agents", "~/.agents/skills",
                 "discovered twice", "agents and hooks come from Claude's paths"):
        assert fact in out, fact
    rows = cursor()["doctor_rows"]
    assert {r["kind"] for r in rows} == {"path-exists"}
    assert {r["target"] for r in rows} == {"$HOME/.agents/skills", "$HOME/.claude/skills",
                                           "$HOME/.claude/agents"}
    assert all("fact" in r for r in rows)
    assert harness_doctor.row_outcomes(cursor(), TOOLKIT, str(proj)) == [], \
        "a fact row is never judged, so an absent path cannot fail render-currency"
    # A fact row on a machine with nothing mounted reports, and render-currency passes.
    assert "[PASS] render-currency:cursor" in run_cli(
        ["doctor", "--checks", "render-currency:cursor"], proj, path=path).stdout

    grep = subprocess.run(["grep", "-rnE", "def check_harness_(copilot|cursor)",
                           os.path.dirname(ADLC), "--include=*.py"],
                          capture_output=True, text=True)
    assert grep.stdout == ""


def test_deny_under_allow_recompute(tmp_path):
    for adapter in (copilot(), cursor()):
        assert [(s, st) for s, st, _w in harness_doctor.deny_under_allow_status(adapter, None)] \
            == [(s, "unverified") for s in SHAPES]
    rec = ("prefix: {mechanism: deny, result: unverified, harness_version: unverified, "
           "source: probe}")
    path = variant(tmp_path, COPILOT_YML, [(rec, rec.replace("result: unverified", "result: pass")
                                            .replace("harness_version: unverified",
                                                     "harness_version: 1.2.3"))])
    a = ha.load_adapter(path, toolkit=TOOLKIT)
    def status(result):
        return dict((s, st) for s, st, _w in harness_doctor.deny_under_allow_status(a, result))
    assert status(None)["prefix"] == "unverified"
    def result(version, verdict):
        return {"harness_version": version, "probes": {"ask-tier-deny": {"sub_results": {
            "deny-under-allow": {"status": verdict}}}}}
    assert status(result("9.9.9", "pass"))["prefix"] == "unverified"
    assert status(result("1.2.3", "fail"))["prefix"] == "unverified"
    assert status(result("1.2.3", "pass"))["prefix"] == "pass"


def test_adapters_declare_data_not_code():
    for fn in os.listdir(os.path.dirname(ADLC)):
        if fn.startswith("harness_") and fn.endswith(".py") and fn != "harness_probe.py":
            text = open(os.path.join(os.path.dirname(ADLC), fn), encoding="utf-8").read()
            assert not re.search(r"""==\s*["'](copilot|cursor)["']""", text), fn


# --------------------------------------------------------------------------- BR-14 / AC-14
def test_no_flag_writes_nothing_new(tmp_path, sandbox):
    def tree(root):
        return sorted(os.path.relpath(os.path.join(d, f), str(root))
                      for d, _dirs, fs in os.walk(str(root)) if ".git" not in d.split(os.sep)
                      for f in fs)
    plain = git_repo(tmp_path / "plain")
    run_init(plain, None)
    assert tree(plain) == [".claude/settings.json", "AGENTS.md", "CLAUDE.md"]
    bindir = tmp_path / "bin"
    fake_bin(bindir, "copilot")
    path = fake_bin(bindir, "agent") + ":" + SYSTEM_PATH
    detected = git_repo(tmp_path / "detected")
    run_init(detected, None, path=path)
    assert tree(detected) == tree(plain)
    for rel in tree(plain):
        assert (plain / rel).read_bytes() == (detected / rel).read_bytes()
    home = os.environ["HOME"]
    assert not os.path.exists(os.path.join(home, ".copilot"))
    assert not os.path.exists(os.path.join(home, ".cursor"))
    assert not os.path.exists(os.path.join(home, ".claude"))
    assert (plain / ".claude" / "settings.json").read_text() == open(
        os.path.join(TOOLKIT, "harness", "claude", "rendered", "settings.json"),
        encoding="utf-8").read()


# --------------------------------------------------------------------------- Phase 5
def _lint():
    sys.path.insert(0, os.path.join(TOOLKIT, "tools", "lint-skills"))
    import check
    return check


def test_a_local_cursor_dir_does_not_fail_parity(tmp_path):
    """A contributor's own `.cursor/` or `.github/hooks/` is theirs, not a render."""
    tk = tmp_path / "tk"
    for d in ("harness", "templates", "agents", ".claude", "partials"):
        shutil.copytree(os.path.join(TOOLKIT, d), str(tk / d),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (tk / ".cursor").mkdir()
    (tk / ".cursor" / "cli.json").write_text('{"permissions": {"allow": ["Shell(make)"]}}\n')
    (tk / ".github" / "hooks").mkdir(parents=True)
    assert all(r[3] == "in-parity" for r in hr.parity(str(tk)))
    (tk / ".claude" / "settings.json").write_text("{}\n")
    assert [r[2] for r in hr.parity(str(tk)) if r[3] != "in-parity"] == [".claude/settings.json"]


def test_goldens_read_the_result_a_real_render_reads(tmp_path):
    tk = tmp_path / "tk"
    for d in ("harness", "templates", "agents", ".claude", "partials"):
        shutil.copytree(os.path.join(TOOLKIT, d), str(tk / d),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    yml = tk / "harness" / "copilot.yml"
    rec = "prefix: {mechanism: deny, result: unverified, harness_version: unverified, source: probe}"
    text = yml.read_text(encoding="utf-8")
    assert rec in text
    yml.write_text(text.replace(rec, rec.replace("result: unverified", "result: pass").replace(
        "harness_version: unverified", "harness_version: 1.2.3")).replace(
            '  "git.read:git branch": {user: inexpressible}\n', "").replace(
            '  "git.write:git push": {user: inexpressible}\n', ""), encoding="utf-8")
    probes = tk / ".adlc" / "research" / "harness-probes"
    probes.mkdir(parents=True)
    (probes / "copilot.json").write_text(json.dumps({
        "harness_version": "1.2.3", "probes": {"ask-tier-deny": {"sub_results": {
            "deny-under-allow": {"status": "pass"}}}}}))
    hr.write_goldens(str(tk))
    line = (tk / "harness" / "copilot" / "rendered" / "printed-permissions.txt").read_text()
    assert "--allow-tool 'shell(git push:*)'" in line, "a lift reaches the golden"
    assert all(r[3] == "in-parity" for r in hr.parity(str(tk)))


def test_opted_in_needs_the_main_file(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    (proj / ".cursor").mkdir()
    (proj / ".cursor" / "permissions.json").write_text('{"terminalAllowlist": ["make"]}\n')
    proc = run_cli(["harness", "drift", "--harness", "claude", "--opted-in"], proj)
    assert "cursor" not in proc.stdout, "a project's own IDE file has not asked for this layer"
    (proj / ".cursor" / "cli.json").write_text("{}\n")
    assert "harness-config cursor" in run_cli(["harness", "drift", "--harness", "claude",
                                               "--opted-in"], proj).stdout
    out = run_cli(["harness", "drift", "--harness", "claude", "--opted-in", "--json"], proj).stdout
    assert {row["harness"] for row in json.loads(out)} == {"claude", "cursor"}


def test_template_drift_fence_runs_opted_in():
    text = open(os.path.join(TOOLKIT, "template-drift", "SKILL.md"), encoding="utf-8").read()
    assert "harness drift --harness claude --opted-in" in text
    block = _lint().parse_sync_surface_block(text, "template-drift")
    assert "harness-config" in block
    for rel in (".github/hooks/adlc.json", ".cursor/cli.json", ".cursor/permissions.json"):
        assert rel in text


def test_unguarded_source_walks_the_copilot_render(tmp_path):
    check = _lint()
    assert check.check_hook_sources(_root_with_hook("adlc_ethos_inject\n", tmp_path)) == []
    bad = _root_with_hook(". .adlc/partials/ethos-inject.sh 2>/dev/null || . x\n", tmp_path)
    assert [f.check for f in check.check_hook_sources(bad)] == ["unguarded-source"]


def _root_with_hook(command, tmp_path):
    root = tmp_path / ("r%d" % len(list(tmp_path.glob("r*"))))
    rendered = root / "harness" / "copilot" / "rendered"
    rendered.mkdir(parents=True)
    (rendered / "adlc.json").write_text(json.dumps({
        "version": 1, "hooks": {"sessionStart": [{"type": "command", "bash": command}]}}))
    return root


def test_a_fact_needs_a_path_exists_row(tmp_path):
    path = variant(tmp_path, COPILOT_YML, [(
        "    kind: path-exists\n    target: $HOME/.agents/skills\n",
        "    kind: marker-present\n    target: {path: $HOME/.agents/skills, marker: x}\n")])
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(path, toolkit=TOOLKIT)
    assert "doctor_rows[0].fact" in str(exc.value)


def test_summary_stays_on_the_rendered_scope(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    claude_project = run_cli(["harness", "render", "--harness", "claude", "--dry-run"], proj)
    assert "will prompt" not in claude_project.stderr
    for scope in ("exec", "user"):
        proc = run_cli(["harness", "render", "--harness", "claude", "--scope", scope], proj)
        assert "will prompt" not in proc.stderr and "no hard deny" not in proc.stderr, scope


def test_a_printed_render_with_no_broad_spelling_keeps_the_plain_remedy(tmp_path):
    path = variant(tmp_path, CURSOR_YML, [])
    adapter = ha.load_adapter(path, toolkit=TOOLKIT)
    assert hr.printed_fence_remedy(adapter) == hr.fence_remedy(adapter)
    assert "WIDENING" in hr.printed_fence_remedy(copilot())


def test_failing_currency_still_reports_deny_under_allow(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    path = fake_bin(tmp_path / "bin", "copilot") + ":" + SYSTEM_PATH
    out = run_cli(["doctor", "--checks", "render-currency:copilot"], proj, path=path).stdout
    assert "[FAIL] render-currency:copilot" in out and "deny_under_allow: prefix=unverified" in out


# --------------------------------------------------------------------------- goldens
def test_goldens_round_trip(tmp_path):
    tk = tmp_path / "tk"
    for d in ("harness", "templates", "agents", ".claude", "partials"):
        shutil.copytree(os.path.join(TOOLKIT, d), str(tk / d),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    assert hr.write_goldens(str(tk)) == []
    golden = tk / "harness" / "copilot" / "rendered" / "printed-permissions.txt"
    golden.write_text(golden.read_text().replace("git status", "git statuz"))
    bad = [r for r in hr.parity(str(tk)) if r[3] != "in-parity"]
    assert [r[2] for r in bad] == ["harness/copilot/rendered/printed-permissions.txt"]
    agents = tk / "agents" / "reflector.md"
    agents.write_text(agents.read_text().replace("tools: Read, Grep, Glob", "tools: Read, Write"))
    assert "harness/copilot/rendered/agents.json" in [
        r[2] for r in hr.parity(str(tk)) if r[3] != "in-parity"]
    assert sorted(hr.write_goldens(str(tk))) == ["harness/copilot/rendered/agents.json",
                                                 "harness/copilot/rendered/printed-permissions.txt"]
    assert all(r[3] == "in-parity" for r in hr.parity(str(tk)))


def test_shipped_goldens_name_the_rendered_files():
    root = os.path.join(TOOLKIT, "harness")
    assert sorted(os.listdir(os.path.join(root, "copilot", "rendered"))) == [
        "adlc.json", "agents.json", "printed-permissions.txt"]
    assert sorted(os.listdir(os.path.join(root, "cursor", "rendered"))) == ["cli.json",
                                                                            "permissions.json"]
    manifest = json.load(open(os.path.join(root, "copilot", "rendered", "agents.json"),
                              encoding="utf-8"))
    assert manifest["task-implementer.agent.md"] is None
    assert manifest["correctness-reviewer.agent.md"] == "read, search, execute"
