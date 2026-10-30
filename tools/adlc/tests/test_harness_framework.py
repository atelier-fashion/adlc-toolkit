"""REQ-657: the harness adapter framework.

Every case that writes runs in a sandbox: HOME and ADLC_HOME point under
``tmp_path``, projects are throwaway git repos, and toolkit copies live in
``tmp_path``. Nothing here writes the real home directory or the checkout.
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
import harness_yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ADLC = os.path.join(os.path.dirname(HERE), "adlc.py")
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FIX = os.path.join(HERE, "fixtures", "harness")
CLAUDE_YML = os.path.join(TOOLKIT, "harness", "claude.yml")
GOLDEN = os.path.join(TOOLKIT, "harness", "claude", "rendered", "settings.json")
SYSTEM_PATH = "/usr/bin:/bin"
OLD_NAME = "claude-settings-" + "template.json"


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


def claude():
    return ha.load_adapter(CLAUDE_YML, toolkit=TOOLKIT)


def variant(tmp_path, base, edits, name=None):
    """A copy of fixture ``base`` with ``edits`` (old, new) applied, same basename."""
    src = open(os.path.join(FIX, base + ".yml"), encoding="utf-8").read() \
        if base != "claude" else open(CLAUDE_YML, encoding="utf-8").read()
    for old, new in edits:
        assert old in src, old
        src = src.replace(old, new, 1)
    d = tmp_path / ("v%d" % len(list(tmp_path.glob("v*"))))
    d.mkdir()
    path = d / ((name or base) + ".yml")
    path.write_text(src, encoding="utf-8")
    return str(path)


def load(path):
    return ha.load_adapter(path, toolkit=TOOLKIT)


def run_cli(args, cwd, env_extra=None, path=None):
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
           "PATH": path or SYSTEM_PATH, "PYTHONDONTWRITEBYTECODE": "1"}
    env.update(env_extra or {})
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


def toolkit_copy(tmp_path):
    """A self-contained toolkit copy: the CLI, the adapter data, templates, agents."""
    root = tmp_path / "tk"
    for d in ("harness", "templates", "agents", ".claude", "partials"):
        shutil.copytree(os.path.join(TOOLKIT, d), str(root / d),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    shutil.copytree(os.path.join(TOOLKIT, "tools", "adlc"), str(root / "tools" / "adlc"),
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    shutil.copy(os.path.join(TOOLKIT, "VERSION"), str(root / "VERSION"))
    return root


# --------------------------------------------------------------------------- YAML subset
def test_yaml_subset_accepts_what_the_adapters_use():
    doc = harness_yaml.loads("a: 1\nb: [x, \"[\", [y, z]]\nc: {k: v, n: 2}\nd: |\n  one\n  two\n"
                             "e:\n  - id: q\n    v: w\n  - plain\n")
    assert doc == {"a": 1, "b": ["x", "[", ["y", "z"]], "c": {"k": "v", "n": 2},
                   "d": "one\ntwo\n", "e": [{"id": "q", "v": "w"}, "plain"]}


@pytest.mark.parametrize("text, words", [
    ("a: 1\na: 2\n", "given twice"),
    ("binary: x\n\"binary\": y\n", "given twice"),
    ("a:\n\tb: 1\n", "tab"),
    ("a: &x 1\n", "indicator"),
    ("a: *x\n", "indicator"),
    ("a: !tag 1\n", "indicator"),
    ("a: >\n  folded\n", "indicator"),
    ("---\na: 1\n", "document"),
    ("a: 'open\n", "never closed"),
    ("a: x: y\n", "': '"),
    ("a:\n", "no value"),
])
def test_yaml_subset_refuses_the_rest(text, words):
    with pytest.raises(harness_yaml.YamlError) as exc:
        harness_yaml.loads(text, "t.yml")
    assert words in str(exc.value)


# --------------------------------------------------------------------------- BR-1 / AC-1
def test_claude_adapter_loads():
    a = claude()
    assert a["name"] == "claude" and a["schema_version"] == 1
    assert a["trust"]["mechanism"] == "user-config-entry"      # ASSUME-010
    assert a["capabilities"]["subagent_start_hook"] == "no"     # Deferred
    assert a["deny_tier_render"] == {"project": "confirm"}
    assert a["capabilities"]["allowlist_granularity"] == "prefix"
    assert a["hook_events"]["subagent-start"] == "unsupported"
    assert set(ha.FORMATS) == set(hr.FORMATS)


@pytest.mark.parametrize("edit, field", [
    (("name: claude\n", "name: claude\nbogus: 1\n"), "bogus"),
    (("schema_version: 1", "schema_version: 9"), "schema_version"),
    (("  session-compact: {event: SessionStart, matcher: compact}\n", ""),
     "hook_events.session-compact"),
    (("  Bash: Bash\n", ""), "tool_map.Bash"),
    (("    user: $HOME/.claude/agents", "    user: /Users/someone/.claude/agents"),
     "paths.agents.user"),
    (("binary: claude", "binary: codex"), "binary"),
    (("hook_timeout_unit: s", "hook_timeout_unit: s\nexec: 3"), "exec"),
    (("binary: claude", "binary: claude\nbinary: claude"), "binary"),
])
def test_loader_rejects(tmp_path, sandbox, edit, field):
    path = variant(tmp_path, "claude", [edit])
    with pytest.raises(ha.AdapterError) as exc:
        load(path)
    assert field in str(exc.value)
    # No adlc harness subcommand proceeds past the failure.
    proc = run_cli(["harness", "render", "--harness", "claude", "--adapter-path", path,
                    "--dry-run"], tmp_path)
    assert proc.returncode == 2 and field in proc.stderr


def test_loader_rejects_grandfathered_elsewhere(tmp_path):
    rec = "{mechanism: confirm, result: pass, harness_version: n/a, source: grandfathered}"
    for edits, field in (
            ([("  deny_under_allow: {}", "  deny_under_allow:\n    prefix: " + rec)],
             "deny_under_allow.prefix.source"),
            ([("allowlist_granularity: prefix", "allowlist_granularity: fence-prefix")],
             "allowlist_granularity"),
            ([("  deny_under_allow: {}", "  deny_under_allow:\n    prefix: {mechanism: confirm}")],
             "deny_under_allow.prefix.result")):
        with pytest.raises(ha.AdapterError) as exc:
            load(variant(tmp_path, "fake-prefix", edits))
        assert field in str(exc.value)
    for tok in ("if", "sh", "bash", "zsh"):
        with pytest.raises(ha.AdapterError) as exc:
            load(variant(tmp_path, "fake-prefix", [(
                'fence_broad_spelling: [if, "[", -f, .adlc/partials/]',
                "fence_broad_spelling: [%s]" % tok)]))
        assert "fence_broad_spelling" in str(exc.value)


def test_adapter_path_is_the_only_way_a_test_adapter_loads(tmp_path, sandbox):
    with pytest.raises(ha.AdapterError):
        ha.resolve_adapter("fake")
    assert ha.resolve_adapter("fake", os.path.join(FIX, "fake.yml"), TOOLKIT)["name"] == "fake"
    assert all(os.path.dirname(p) == os.path.join(TOOLKIT, "harness")
               for p in ha.shipped_adapter_paths(TOOLKIT))
    proc = run_cli(["harness", "install", "--all", "--adapter-path",
                    os.path.join(FIX, "fake.yml")], tmp_path)
    assert proc.returncode == 2 and "--all does not take --adapter-path" in proc.stderr
    init = open(os.path.join(TOOLKIT, "init", "SKILL.md"), encoding="utf-8").read()
    assert "--adapter-path" not in init


# --------------------------------------------------------------------------- BR-6 / BR-7 / AC-5 / AC-6
def test_permissions_two_tiers():
    p = perms()
    assert {e["tier"] for e in p["entries"]} == {"routine", "deny"}
    ids = {e["id"] for e in p["entries"]}
    assert {"git.read", "git.write", "gh.read", "gh.pr.create", "gh.merge", "deploy",
            "terraform", "git.push.force", "rm.recursive", "fence.partial-source"} <= ids
    text = open(ha.permissions_path(TOOLKIT), encoding="utf-8").read()
    assert not re.search(r"tier:\s*ask", text)


def _pinned():
    return json.load(open(os.path.join(FIX, "pinned-template-sets.json"), encoding="utf-8"))


def test_claude_render_equals_pinned_template():
    plans, _p = hr.plan_surfaces(claude(), "project", TOOLKIT, TOOLKIT,
                                 surfaces=("permissions", "hooks"))
    doc = json.loads(plans[0].content)
    pin = _pinned()
    assert set(doc["permissions"]["allow"]) == set(pin["allow"])
    assert set(doc["permissions"]["ask"]) == set(pin["ask"])
    assert doc["permissions"]["defaultMode"] == pin["defaultMode"]
    assert doc["_comment"] == pin["_comment"]
    assert list(doc) == ["_comment", "permissions", "hooks"]
    assert not any(e.startswith(("Bash(if", "Bash(sh", "Bash(bash", "Bash(zsh"))
                   for e in doc["permissions"]["allow"])
    assert open(GOLDEN, encoding="utf-8").read() == plans[0].content


def test_prefix_unverified_breaks_the_pinned_set(tmp_path):
    a = load(variant(tmp_path, "claude", [("result: pass", "result: unverified")]))
    rules, findings, _x = hr.render_permissions(a, perms(), "project")
    allow = {hr._claude_spelling(r) for r in rules if r.kind == "allow"}
    assert "Bash(git push:*)" not in allow and "Bash(git branch:*)" not in allow
    assert set(_pinned()["allow"]) != allow
    omitted = {(f.entry, f.command) for f in findings if f.verdict == "inexpressible"}
    assert ("git.write", "git push") in omitted and ("git.read", "git branch") in omitted


def test_template_deleted_and_unreferenced():
    assert not os.path.exists(os.path.join(TOOLKIT, "templates", OLD_NAME))
    hits = []
    for top in ("agents", "partials", "tools", "templates"):
        for dirpath, _dirs, files in os.walk(os.path.join(TOOLKIT, top)):
            for fn in files:
                p = os.path.join(dirpath, fn)
                try:
                    if OLD_NAME in open(p, encoding="utf-8", errors="replace").read():
                        hits.append(p)
                except OSError:
                    pass
    for fn in os.listdir(TOOLKIT):
        p = os.path.join(TOOLKIT, fn, "SKILL.md")
        if os.path.isfile(p) and OLD_NAME in open(p, encoding="utf-8").read():
            hits.append(p)
    if OLD_NAME in open(os.path.join(TOOLKIT, "README.md"), encoding="utf-8").read():
        hits.append("README.md")
    assert hits == []


def test_old_template_line_in_a_skill_fails_the_lint(tmp_path):
    sys.path.insert(0, os.path.join(TOOLKIT, "tools", "lint-skills"))
    import check
    (tmp_path / "init").mkdir()
    (tmp_path / "init" / "SKILL.md").write_text(
        "---\nname: init\n---\ncp ~/.claude/skills/templates/%s .claude/settings.json\n" % OLD_NAME)
    findings = check.check_retired_settings_template(tmp_path)
    assert [f.check for f in findings] == ["retired-settings-template"]
    (tmp_path / "init" / "SKILL.md").write_text("---\nname: init\n---\nadlc harness render\n")
    assert check.check_retired_settings_template(tmp_path) == []


# --------------------------------------------------------------------------- BR-8 / BR-9 / AC-7 / AC-16
def test_fidelity_claude_clean():
    result = hr.load_result_file(os.path.join(TOOLKIT, ".adlc", "research", "harness-probes",
                                              "claude.json"))
    findings, failures = hr.fidelity(claude(), perms(), result)
    assert failures == []
    odd = sorted((f.entry, f.command, f.verdict) for f in findings if f.verdict != "exact")
    assert odd == [("fence.partial-source", "if [ -f .adlc/partials/", "inexpressible"),
                   ("git.push.force", "git push --force", "residual:exact-deny"),
                   ("git.push.force", "git push -f", "residual:exact-deny")]
    assert all(f.verdict != "narrowed" for f in findings)
    _r, exec_findings, _x = hr.render_permissions(claude(), perms(), "exec", result)
    fence = [f for f in exec_findings if f.entry == "fence.partial-source"]
    assert fence[0].verdict == "widened:if [ -f .adlc/partials/"
    assert claude()["accepted_fidelity"]["fence.partial-source"]["exec"] == fence[0].verdict


def test_fake_command_base_fails_without_acceptance():
    a = load(os.path.join(FIX, "fake.yml"))
    findings, failures = hr.fidelity(a, perms())
    by = {(f.entry, f.command): f.verdict for f in findings}
    assert by[("test.npm", "npm test")] == "widened:npm"
    assert any("test.npm [npm test] is widened:npm" in m for m in failures)
    for e in ("gh.merge", "deploy", "terraform", "git.push.force"):
        assert any(m.startswith("fake: %s " % e) and "deny-unsupported" in m for m in failures), e
    for key in (("git.read", "git status"), ("git.write", "git push"), ("gh.read", "gh pr view"),
                ("gh.api", "gh api")):
        assert by[key] == "inexpressible", key
    rules, _f, _x = hr.render_permissions(a, perms(), "project")
    assert not any(r.spelling in (("git",), ("gh",)) for r in rules)


def test_fake_prefix_git_c_shared_base(tmp_path):
    def gitc(adapter, result=None):
        rules, findings, _x = hr.render_permissions(adapter, perms(), "project", result)
        verdicts = {f.verdict for f in findings if f.command == "git -C"}
        return any(r.spelling == ("git", "-C") for r in rules), verdicts
    base = load(os.path.join(FIX, "fake-prefix.yml"))
    assert gitc(base) == (False, {"inexpressible"})
    result = hr.load_result_file(os.path.join(FIX, "probe-pass.json"))
    rec = "{mechanism: %s, result: pass, harness_version: %s, source: probe}"
    ok = load(variant(tmp_path, "fake-prefix", [(
        "deny_under_allow: {}", "deny_under_allow:\n    git-c: " + rec % ("confirm", "1.2.3"))]))
    assert gitc(ok, result) == (True, {"exact"})
    findings, failures = hr.fidelity(ok, perms(), result)
    assert not any("git -C" in m for m in failures)
    for mech, ver in (("deny", "1.2.3"), ("confirm", "9.9.9")):
        bad = load(variant(tmp_path, "fake-prefix", [(
            "deny_under_allow: {}", "deny_under_allow:\n    git-c: " + rec % (mech, ver))]))
        assert gitc(bad, result)[0] is False
    _f, failures = hr.fidelity(load(variant(tmp_path, "fake-prefix", [(
        "deny_under_allow: {}", "deny_under_allow:\n    git-c: " + rec % ("confirm", "9.9.9"))])),
        perms(), result)
    assert any("source: probe" in m for m in failures)
    _f, failures = hr.fidelity(ok, perms(), None)
    assert any("no REQ-664 result file" in m for m in failures)
    never = load(variant(tmp_path, "fake-prefix", [
        ("deny_under_allow: {}", "deny_under_allow:\n    git-c: " + rec % ("confirm", "1.2.3")),
        ("git_c_spelling: [[git, -C]]", "git_c_spelling: [[git, -C]]\n  never_restore: [git-c]")]))
    assert gitc(never, result)[0] is False


@pytest.mark.parametrize("spelling, shape", [
    (("git", "-C"), "git-c"), (("NAME=1", "git", "push"), "env-prefix"),
    (("bash", "-lc"), "shell-opener"), (("git", "push"), "prefix")])
def test_hand_written_render_fails(spelling, shape):
    a = load(os.path.join(FIX, "fake-prefix.yml"))
    rules = [hr.Rule("git.write", spelling, "routine", "allow", spelling, False)]
    failures = hr.evaluate_rules(a, perms(), rules, "project")
    assert any("shape %s" % shape in m and "git push --force" in m for m in failures), failures


def test_fence_first_token_wildcard():
    a = load(os.path.join(FIX, "fake-prefix.yml"))
    for tok in ("if", "sh", "bash", "zsh"):
        rules = [hr.Rule("fence.partial-source", (tok,), "routine", "allow", (tok,), False)]
        assert any("first-token wildcard" in m for m in hr.evaluate_rules(a, perms(), rules,
                                                                          "project"))
    rules, findings, extras = hr.render_permissions(load(os.path.join(FIX, "fake.yml")), perms(),
                                                    "project")
    assert not any(r.entry == "fence.partial-source" for r in rules)
    assert [f.verdict for f in findings if f.entry == "fence.partial-source"] == ["inexpressible"]
    assert extras["remedies"] and "sh:*" not in extras["remedies"][0]
    rules, _f, _x = hr.render_permissions(a, perms(), "project")
    fence = [r for r in rules if r.entry == "fence.partial-source"]
    assert fence and fence[0].spelling == ("if", "[", "-f", ".adlc/partials/")


def test_matcher_vectors(tmp_path):
    m = hr.allow_matches
    assert m(("git",), False, "command-base", ("FOO=1", "git", "push", "--force"), False)
    assert hr._spell(("gcloud", "run", "services"), "subcommand") == (("gcloud", "run"), True)
    assert m(("git", "push"), False, "token-prefix", ("git", "push", "--force"), False)
    assert not m(("git", "push"), False, "token-prefix", ("git", "-C", ".", "push", "--force"),
                 False)
    assert m(("git", "-C"), False, "token-prefix", ("git", "-C", ".", "push", "--force"), False)
    assert not m(("git", "pu"), False, "prefix", ("git", "push", "--force"), False)
    assert m(("git", "push"), False, "prefix", ("git", "push", "--force"), False)
    assert m(("git", "push", "--force"), True, "prefix", ("git", "push", "--force"), True)
    assert not m(("git", "push", "--force"), True, "prefix",
                 ("git", "push", "--force", "origin", "feature"), True)
    assert m(("git", "push", "--force"), True, "prefix",
             ("git", "push", "--force", "origin", "feature"), False)  # collapsed to a prefix
    # Wrappers outside the closed set are never evaluated.
    assert [s for s, _f in hr.deny_forms(("git", "push", "--force"))] == [
        "prefix", "git-c", "env-prefix", "shell-opener"]
    # accepted_fidelity: entry id covers every command; "<id>:<argv>" one; narrower wins.
    a = {"accepted_fidelity": {"x": "inexpressible", "x:git push": "widened:git"}}
    assert hr.accepted(a, "x", "git push", "project") == "widened:git"
    assert hr.accepted(a, "x", "git pull", "project") == "inexpressible"
    assert hr.accepted(a, "x", "git pull", "exec") is None
    b = {"accepted_fidelity": {"x": {"exec": "inexpressible"}}}
    assert hr.accepted(b, "x", "git", "project") is None
    assert hr.accepted(b, "x", "git", "exec") == "inexpressible"
    # default_mode with no map is inexpressible and fails unless accepted.
    nomap = load(os.path.join(FIX, "fake-prefix.yml"))
    _f, failures = hr.fidelity(nomap, perms())
    assert any("default_mode [default_mode] is inexpressible" in x for x in failures)
    rules, findings, extras = hr.render_permissions(claude(), perms(), "project")
    assert extras["default_mode"] == ("permissions.defaultMode", "acceptEdits")
    # residual:exact-deny fails unless listed.
    unlisted = load(variant(tmp_path, "claude", [
        ("  git.push.force: residual:exact-deny\n", "")]))
    _f, failures = hr.fidelity(unlisted, perms())
    assert any("residual:exact-deny" in x for x in failures)
    # env-prefix and shell-opener stay unverified for claude.
    assert not hr.restore_ok(claude(), "env-prefix", "project", None)
    assert not hr.restore_ok(claude(), "shell-opener", "project", None)
    assert hr.restore_ok(claude(), "prefix", "project", None)


def test_scope_vectors(tmp_path, sandbox):
    rules, findings, _x = hr.render_permissions(claude(), perms(), "user")
    assert not any(r.kind == "allow" for r in rules)
    assert all(f.verdict == "deny-unsupported" for f in findings)
    # A fixture with a user path and a user deny mechanism writes the deny tier only.
    upath = variant(tmp_path, "fake-prefix", [
        ("    project: .fake-prefix/permissions.json",
         "    project: .fake-prefix/permissions.json\n    user: $HOME/.fake-prefix/permissions.json"),
        ("  project: confirm", "  project: confirm\n  user: deny")])
    a = load(upath)
    plans, _p = hr.plan_surfaces(a, "user", str(tmp_path), TOOLKIT)
    hr.apply_plans(plans, out=open(os.devnull, "w"))
    written = json.load(open(os.path.join(os.environ["HOME"], ".fake-prefix",
                                          "permissions.json")))
    kinds = {r["kind"] for r in written["rules"]}
    assert kinds == {"deny"}
    assert not any(r["entry"] == "fence.partial-source" for r in written["rules"])
    # printed: committed-scope rules, no first-token or broad fence.
    prules, _pf, _px = hr.render_permissions(load(os.path.join(FIX, "fake.yml")), perms(),
                                             "printed")
    assert not any(r.entry == "fence.partial-source" for r in prules)
    # shared-base at exec: a confirm pass does not carry to a hard deny.
    exec_rules, exec_f, _x = hr.render_permissions(claude(), perms(), "exec")
    assert ("git", "push") not in {r.spelling for r in exec_rules if r.kind == "allow"}
    proj_rules, _f, _x = hr.render_permissions(claude(), perms(), "project")
    assert ("git", "push") in {r.spelling for r in proj_rules if r.kind == "allow"}
    deny = [r for r in exec_rules if r.kind == "deny"]
    assert any(r.argv == ("git", "push", "--force") and not r.exact for r in deny)
    # exec.engine_deny joins; deny_render none needs a `fail` ask-tier-deny verdict.
    eng = load(variant(tmp_path, "claude", [(
        "hook_timeout_unit: s", "hook_timeout_unit: s\nexec:\n  engine_deny: [[adlc, sprint, approve]]")]))
    er, _ef, _x = hr.render_permissions(eng, perms(), "exec")
    assert any(r.entry == "exec.engine_deny" and r.kind == "deny" for r in er)
    none = load(variant(tmp_path, "claude", [(
        "hook_timeout_unit: s", "hook_timeout_unit: s\nexec:\n  deny_render: none")]))
    with pytest.raises(hr.RenderError):
        hr.render_permissions(none, perms(), "exec", {"probes": {"ask-tier-deny": {"status": "pass"}}})
    hr.render_permissions(none, perms(), "exec", {"probes": {"ask-tier-deny": {"status": "fail"}}})
    proc = run_cli(["harness", "render", "--harness", "claude", "--scope", "user"], tmp_path)
    assert proc.returncode == 0 and "nothing written" in proc.stdout
    assert not os.listdir(os.environ["HOME"]) or os.listdir(os.environ["HOME"]) == [".fake-prefix"]


# --------------------------------------------------------------------------- BR-10 / AC-8
def test_hooks_render(tmp_path, sandbox):
    block, findings = hr.render_hooks(claude(), ha.load_hooks(ha.hooks_path(TOOLKIT)))
    groups = block["SessionStart"]
    assert [g.get("matcher") for g in groups] == ["startup|resume|clear", "compact"]
    first = [h["command"].splitlines()[-1] for h in groups[0]["hooks"]]
    assert first == ["adlc_ethos_inject", "adlc_session_record"]
    assert all(h["timeout"] == 10 for g in groups for h in g["hooks"])
    assert "SubagentStart" not in block
    assert any(f.command == "subagent-start" and f.verdict == "unsupported" for f in findings)
    fake_block, _f = hr.render_hooks(load(os.path.join(FIX, "fake.yml")),
                                     ha.load_hooks(ha.hooks_path(TOOLKIT)))
    hooks = fake_block["sessionStart"][0]["hooks"]
    assert {h["timeout"] for h in hooks} == {10000}
    assert all(h["command"].endswith("--harness fake --field session_id=sessionId --field cwd=cwd")
               for h in hooks)
    proc = run_cli(["harness", "render", "--harness", "fake", "--adapter-path",
                    os.path.join(FIX, "fake.yml"), "--surface", "hooks"],
                   git_repo(tmp_path / "proj"), {"HOME": str(tmp_path), "ADLC_HOME": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr
    assert '"timeout": 10000' in (tmp_path / "proj" / ".fake" / "hooks.json").read_text()


# --------------------------------------------------------------------------- BR-2 / BR-3 / AC-2
def test_render_dry_run_and_idempotent(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    proc = run_cli(["harness", "render", "--harness", "claude", "--dry-run"], proj)
    assert proc.returncode == 0 and "would-write" in proc.stdout
    assert subprocess.run(["git", "-C", str(proj), "status", "--porcelain"],
                          capture_output=True, text=True).stdout == ""
    assert run_cli(["harness", "render", "--harness", "claude"], proj).returncode == 0
    first = (proj / ".claude" / "settings.json").read_bytes()
    second = run_cli(["harness", "render", "--harness", "claude"], proj)
    assert "zero actions" in second.stdout
    assert (proj / ".claude" / "settings.json").read_bytes() == first
    assert first.decode() == open(GOLDEN, encoding="utf-8").read()


def test_install_claude_nothing_to_write(tmp_path, sandbox):
    home = os.environ["ADLC_HOME"]
    proc = run_cli(["harness", "install", "--harness", "claude"], tmp_path)
    assert proc.returncode == 0
    assert "nothing to write" in proc.stdout
    assert not os.path.exists(home) or os.listdir(home) == []


# --------------------------------------------------------------------------- BR-11 / BR-12 / AC-6 / AC-9 / AC-10
def test_merge_write_mode(tmp_path, sandbox):
    path = variant(tmp_path, "fake-prefix", [(
        "    mode: rendered\nformats:",
        "    mode: rendered\n    write_mode: merge\n    owned_keys: [permissions, hooks]\nformats:"),
        ("  permissions: rules-json", "  permissions: claude-settings-json")])
    proj = git_repo(tmp_path / "proj")
    target = proj / ".fake-prefix" / "permissions.json"
    target.parent.mkdir()
    target.write_text(json.dumps({"projectKey": {"keep": True},
                                  "permissions": {"allow": ["Bash(make deploy-docs:*)"]}}))
    proc = run_cli(["harness", "render", "--harness", "fake-prefix", "--adapter-path", path,
                    "--surface", "permissions"], proj)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(target.read_text())
    assert doc["projectKey"] == {"keep": True}
    assert "Bash(make deploy-docs:*)" in doc["permissions"]["allow"]
    assert "Bash(git status:*)" in doc["permissions"]["allow"]
    again = run_cli(["harness", "render", "--harness", "fake-prefix", "--adapter-path", path,
                     "--surface", "permissions"], proj)
    assert "zero actions" in again.stdout


def _init_step8_fence():
    text = open(os.path.join(TOOLKIT, "init", "SKILL.md"), encoding="utf-8").read()
    section = text[text.index("### Step 8:"):text.index("### Step 9:")]
    body = section[section.index("```bash\n") + 8:]
    return body[:body.index("```")]


def test_init_render_project_layer(tmp_path, sandbox):
    fence = _init_step8_fence().replace("'<harnesses>'", "''")
    bindir = fake_bin(tmp_path / "bin", "codex")
    proj = git_repo(tmp_path / "proj")
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
           "PATH": bindir + ":" + SYSTEM_PATH, "CLAUDE_PLUGIN_ROOT": TOOLKIT}
    run = lambda: subprocess.run(["/bin/sh", "-c", fence], cwd=str(proj), env=env,  # noqa: E731
                                 capture_output=True, text=True, timeout=120)
    first = run()
    assert first.returncode == 0, first.stderr
    files = {p: (proj / p).read_bytes() for p in (".claude/settings.json", "AGENTS.md",
                                                   "CLAUDE.md")}
    assert files[".claude/settings.json"].decode() == open(GOLDEN, encoding="utf-8").read()
    assert files["CLAUDE.md"].decode().splitlines()[0] == "@AGENTS.md"
    assert b"/proceed" in files["AGENTS.md"]
    run()
    assert all((proj / p).read_bytes() == b for p, b in files.items())
    assert not (proj / ".codex").exists() and not (proj / ".github").exists()
    sys.path.insert(0, os.path.join(TOOLKIT, "tools", "lint-skills"))
    import check
    for which, rel in (("init", "init/SKILL.md"), ("template-drift", "template-drift/SKILL.md")):
        text = open(os.path.join(TOOLKIT, rel), encoding="utf-8").read()
        assert "harness-config" in check.parse_sync_surface_block(text, which)


def test_claude_md_prepend_only(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    original = "".join("line %d of the project's own notes\n" % i for i in range(1, 41))
    (proj / "CLAUDE.md").write_text(original)
    proc = run_cli(["harness", "render", "--harness", "claude", "--surface", "instructions"], proj)
    assert proc.returncode == 0, proc.stderr
    after = (proj / "CLAUDE.md").read_text()
    assert after == "@AGENTS.md\n" + original
    assert "follow-up" in proc.stdout
    assert (proj / "AGENTS.md").is_file()
    run_cli(["harness", "render", "--harness", "claude", "--surface", "instructions"], proj)
    assert (proj / "CLAUDE.md").read_text() == after


def test_drift_old_template_consumer(tmp_path, sandbox):
    proj = git_repo(tmp_path / "proj")
    (proj / ".claude").mkdir()
    shutil.copy(os.path.join(FIX, "old-consumer-settings.json"), str(proj / ".claude" /
                                                                     "settings.json"))
    rows = hr.drift(claude(), str(proj), TOOLKIT)
    assert [(r, c) for r, c, _d in rows] == [(".claude/settings.json", "stale")]
    assert rows[0][2] == ["missing hooks block"]
    proc = run_cli(["harness", "drift", "--harness", "claude"], proj)
    assert proc.returncode == 1 and "missing hooks block" in proc.stdout
    # A customized copy that drops a deny-tier rule names it whatever else it is.
    doc = json.load(open(GOLDEN))
    doc["permissions"]["ask"].remove("Bash(gh pr merge:*)")
    doc["permissions"]["allow"].append("Bash(make:*)")
    (proj / ".claude" / "settings.json").write_text(json.dumps(doc))
    rows = hr.drift(claude(), str(proj), TOOLKIT)
    assert rows[0][1] == "stale"
    assert "missing deny-tier rule (ask): Bash(gh pr merge:*)" in rows[0][2]
    shutil.copy(GOLDEN, str(proj / ".claude" / "settings.json"))
    assert hr.drift(claude(), str(proj), TOOLKIT)[0][1] == "synced"


# --------------------------------------------------------------------------- BR-13 / AC-11
def test_render_check_parity(tmp_path, sandbox):
    tk = toolkit_copy(tmp_path)
    assert all(s == "in-parity" for *_x, s, _d in hr.parity(str(tk)))
    sys.path.insert(0, os.path.join(TOOLKIT, "tools", "lint-skills"))
    import check
    assert check.check_render_parity(tk) == []
    for mutate, label in (
            (lambda: (tk / "harness/claude/rendered/settings.json").write_text(
                (tk / "harness/claude/rendered/settings.json").read_text().replace(
                    "Bash(wc:*)", "Bash(wc2:*)")), "harness/claude/rendered/settings.json"),
            (lambda: (tk / "agents/reflector.md").write_text(
                (tk / "agents/reflector.md").read_text().replace("model: opus", "model: haiku")),
             "agents/reflector.md"),
            (lambda: (tk / ".claude/settings.json").write_text(
                (tk / ".claude/settings.json").read_text().replace("Bash(ls:*)", "Bash(ls -la:*)")),
             ".claude/settings.json")):
        mutate()
        bad = [r for r in hr.parity(str(tk)) if r[3] != "in-parity"]
        assert [r[2] for r in bad] == [label], bad
        assert bad[0][4].startswith("--- %s" % label)
        lint = check.check_render_parity(tk)
        assert [f.file for f in lint] == [label]
        proc = subprocess.run([sys.executable, str(tk / "tools/adlc/adlc.py"), "harness",
                               "render", "--check"], cwd=str(tk), capture_output=True, text=True,
                              env={"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
                                   "PATH": SYSTEM_PATH})
        assert proc.returncode == 1 and label in proc.stdout
        # re-rendering clears it
        if label.startswith("agents/"):
            subprocess.run([sys.executable, str(tk / "tools/adlc/adlc.py"), "agents", "render",
                            "--harness", "claude"], check=True, capture_output=True,
                           env={"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
                                "PATH": SYSTEM_PATH})
        else:
            shutil.copy(GOLDEN, str(tk / label))
        assert all(r[3] == "in-parity" for r in hr.parity(str(tk)))


# --------------------------------------------------------------------------- BR-15 / AC-13
def test_doctor_render_currency(tmp_path, sandbox):
    nobin = run_cli(["doctor", "--checks", "harness:claude,render-currency:claude"], tmp_path)
    assert "[SKIP] harness:claude" in nobin.stdout and "[SKIP] render-currency:claude" in nobin.stdout
    bindir = fake_bin(tmp_path / "bin", "claude")
    path = bindir + ":" + SYSTEM_PATH
    ok = run_cli(["doctor", "--checks", "harness:claude,render-currency:claude"], tmp_path,
                 path=path)
    assert "[PASS] harness:claude" in ok.stdout and "[PASS] render-currency:claude" in ok.stdout
    same = run_cli(["harness", "doctor", "--harness", "claude"], tmp_path, path=path)
    assert "[PASS] render-currency:claude" in same.stdout
    tk = toolkit_copy(tmp_path)
    (tk / "agents/reflector.md").write_text(
        (tk / "agents/reflector.md").read_text().replace("model: opus", "model: haiku"))
    cli = [sys.executable, str(tk / "tools/adlc/adlc.py")]
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"], "PATH": path}
    bad = subprocess.run(cli + ["doctor", "--checks", "render-currency:claude"], cwd=str(tmp_path),
                         env=env, capture_output=True, text=True)
    assert "[FAIL] render-currency:claude" in bad.stdout
    fix = re.search(r"-> fix: (.*)", bad.stdout).group(1)
    assert fix == "adlc agents render --harness claude"
    subprocess.run(cli + fix.split()[1:], env=env, check=True, capture_output=True)
    good = subprocess.run(cli + ["doctor", "--checks", "render-currency:claude"], cwd=str(tmp_path),
                          env=env, capture_output=True, text=True)
    assert "[PASS] render-currency:claude" in good.stdout


def test_doctor_rows(tmp_path, sandbox):
    home = os.environ["HOME"]
    path = variant(tmp_path, "fake", [("committable_allowlist: \"yes\"",
                                       "committable_allowlist: \"yes\"\ndoctor_rows:\n"
                                       "  - {id: cfg, kind: path-exists, target: $HOME/.fake/cfg, "
                                       "remediation: touch ~/.fake/cfg}\n"
                                       "  - id: mark\n    kind: marker-present\n"
                                       "    target: {path: $HOME/.fake/cfg, marker: adlc-on}\n"
                                       "    remediation: echo adlc-on >> ~/.fake/cfg\n"
                                       "  - {id: agents, kind: equals-render, target: hooks, "
                                       "remediation: adlc harness render --harness fake}\n")])
    ha.load_adapter(path, toolkit=TOOLKIT)
    bindir = fake_bin(tmp_path / "bin", "fake")
    proj = git_repo(tmp_path / "proj")
    run = lambda: run_cli(["harness", "doctor", "--harness", "fake", "--adapter-path", path],  # noqa
                          proj, path=bindir + ":" + SYSTEM_PATH)
    out = run().stdout
    for rid, remedy in (("cfg", "touch ~/.fake/cfg"), ("mark", "echo adlc-on >> ~/.fake/cfg"),
                        ("agents", "adlc harness render --harness fake")):
        assert "[FAIL] row %s" % rid in out and remedy in out
    os.makedirs(os.path.join(home, ".fake"))
    open(os.path.join(home, ".fake", "cfg"), "w").write("adlc-on\n")
    assert run_cli(["harness", "render", "--harness", "fake", "--adapter-path", path,
                    "--surface", "hooks"], proj).returncode == 0
    out = run().stdout
    for rid in ("cfg", "mark", "agents"):
        assert "[PASS] row %s" % rid in out, out
    for fn in os.listdir(os.path.dirname(ADLC)):
        if fn.endswith(".py"):
            assert "fake" not in open(os.path.join(os.path.dirname(ADLC), fn)).read(), fn


# --------------------------------------------------------------------------- BR-4 / BR-5 / AC-3 / AC-4
def _render_fake(tmp_path, edits=(), config=None):
    path = variant(tmp_path, "fake", list(edits)) if edits else os.path.join(FIX, "fake.yml")
    adapter = ha.load_adapter(path, toolkit=TOOLKIT)
    cfg = config or {"classes": {}, "overrides": {}}
    report = agents_render.render_copies(adapter, TOOLKIT, cfg, write=True)
    dest = os.path.join(os.environ["HOME"], ".fake", "agents")
    texts = {n: open(os.path.join(dest, n + ".md")).read() for n, _p, _c in report}
    shutil.rmtree(dest)
    return texts, path


def test_agents_copy_render(tmp_path, sandbox):
    assert subprocess.run([sys.executable, ADLC, "agents", "render"], capture_output=True,
                          env={"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
                               "PATH": SYSTEM_PATH}).returncode == 0
    assert subprocess.run([sys.executable, ADLC, "agents", "render", "--harness", "claude"],
                          capture_output=True, env={"HOME": os.environ["HOME"],
                                                    "ADLC_HOME": os.environ["ADLC_HOME"],
                                                    "PATH": SYSTEM_PATH}).returncode == 0
    assert subprocess.run(["git", "-C", TOOLKIT, "diff", "--quiet", "--", "agents/"]).returncode == 0
    texts, _p = _render_fake(tmp_path)
    assert len(texts) == 19
    no_tools = {"task-implementer", "pipeline-runner"}
    for name, text in texts.items():
        fm, body = hr.split_agent(text)
        assert body.lstrip("\n").startswith(hr.ETHOS_LINE), name
        tools = [l for l in fm if l.startswith("tools:")]
        if name in no_tools:
            assert tools == [] and hr.RESTRAINT_SENTENCE not in body
        else:
            assert len(tools) == 1 and "Bash" not in tools[0], name
            assert hr.RESTRAINT_SENTENCE not in body
    assert "tools: read_file, grep, glob" in texts["reflector"]
    none, _p = _render_fake(tmp_path, [("agent_tool_restriction: enforced",
                                        "agent_tool_restriction: none")])
    lines = set()
    for name, text in none.items():
        fm, body = hr.split_agent(text)
        assert not any(l.startswith("tools:") for l in fm)
        paras = body.lstrip("\n").split("\n\n")
        if name in no_tools:
            assert hr.RESTRAINT_SENTENCE not in body
        else:
            assert paras[1] == hr.RESTRAINT_SENTENCE
            lines.add(paras[1])
    assert len(lines) == 1
    ro, _p = _render_fake(tmp_path, [("agent_tool_restriction: enforced",
                                      "agent_tool_restriction: readonly-only")])
    for name, text in ro.items():
        fm, _b = hr.split_agent(text)
        if name not in no_tools:
            assert "readonly: true" in fm and not any(l.startswith("tools:") for l in fm)
    hooked, _p = _render_fake(tmp_path, [('subagent_start_hook: "no"', 'subagent_start_hook: "yes"')])
    assert not any(hr.ETHOS_LINE in t for t in hooked.values())
    # The CLI writes under the user path only, nothing in the project.
    proj = git_repo(tmp_path / "proj")
    proc = subprocess.run([sys.executable, ADLC, "agents", "render", "--harness", "fake",
                           "--adapter-path", os.path.join(FIX, "fake.yml")], cwd=str(proj),
                          capture_output=True, text=True,
                          env={"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"],
                               "PATH": SYSTEM_PATH})
    assert proc.returncode == 0, proc.stderr
    assert len(os.listdir(os.path.join(os.environ["HOME"], ".fake", "agents"))) == 19
    assert os.listdir(str(proj)) == [".git"]


def test_harness_tier_column(tmp_path, sandbox):
    cfgfile = tmp_path / "config.yml"
    cfgfile.write_text("agents:\n  harness:\n    fake:\n      classes:\n        scanner: sonnet\n")
    cfg = agents_render.parse_agents_config(str(cfgfile))
    adapter = ha.load_adapter(os.path.join(FIX, "fake.yml"), toolkit=TOOLKIT)
    plans, notices = agents_render.plan_copies(adapter, TOOLKIT, cfg)
    models = {n: [l for l in hr.split_agent(t)[0] if l.startswith("model:")] for n, _p, t in plans}
    assert models["api-cost-scanner"] == ["model: fake-mid-1"]
    assert models["feature-tracer"] == []
    tier = [n for n in notices if "tier_map" in n]
    assert len(tier) == 1 and "haiku" in tier[0] and "unverified" in tier[0]
    assert models["reflector"] == ["model: fake-large-1"]
    assert agents_render.check_drift(TOOLKIT, cfg) == []        # default column unchanged
    cfgfile.write_text("agents:\n  harness:\n    fake:\n      classes:\n        scanner: fake-x-9\n")
    plans, _n = agents_render.plan_copies(adapter, TOOLKIT,
                                          agents_render.parse_agents_config(str(cfgfile)))
    assert "model: fake-x-9" in dict((n, t) for n, _p, t in plans)["latency-scanner"]
    cfgfile.write_text("agents:\n  harness:\n    fake:\n      classes:\n        bogus: x\n")
    with pytest.raises(agents_render.ConfigError) as exc:
        agents_render.validate_config(agents_render.parse_agents_config(str(cfgfile)))
    assert "bogus" in str(exc.value)
    cfgfile.write_text("agents:\n  colours:\n    scanner: red\n")
    with pytest.raises(agents_render.ConfigError) as exc:
        agents_render.validate_config(agents_render.parse_agents_config(str(cfgfile)))
    assert "agents.colours" in str(exc.value)
    # --check agrees with render on the fake column.
    cfgfile.write_text("agents:\n  harness:\n    fake:\n      classes:\n        scanner: sonnet\n")
    env = {"HOME": os.environ["HOME"], "ADLC_HOME": os.environ["ADLC_HOME"], "PATH": SYSTEM_PATH}
    base = [sys.executable, ADLC, "agents", "render", "--harness", "fake", "--adapter-path",
            os.path.join(FIX, "fake.yml"), "--config", str(cfgfile)]
    assert subprocess.run(base + ["--check"], env=env, capture_output=True).returncode == 1
    assert subprocess.run(base, env=env, capture_output=True).returncode == 0
    assert subprocess.run(base + ["--check"], env=env, capture_output=True).returncode == 0


#: The framework's code: the loader, the renderers, the doctor check, the verbs and
#: the agent renderer. REQ-664's probe catalogue (harness_probe.py) and its test
#: double exercise each harness's own behaviour by design and are not renderers.
FRAMEWORK_MODULES = ("harness_yaml.py", "harness_adapter.py", "harness_render.py",
                     "harness_doctor.py", "harness_cli.py", "agents_render.py")


def test_no_renderer_branches_on_a_harness_name():
    adlc_dir = os.path.dirname(ADLC)
    for fn in FRAMEWORK_MODULES:
        text = open(os.path.join(adlc_dir, fn)).read()
        assert "if harness == " not in text, fn
        assert not re.search(r"""==\s*["'](claude|copilot|codex|gemini|cursor)["']""", text), fn
    for fn in ("harness.py", "checks.py", "doctor.py", "adlc.py"):
        assert "if harness == " not in open(os.path.join(adlc_dir, fn)).read(), fn
