"""The exec block and exec_adapter (REQ-659 BR-3, BR-8, BR-21, BR-22)."""

import ast
import importlib.util
import json
import os
import sys
import sysconfig

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import harness_adapter as ha  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
BRANCH = "feat/REQ-901-thing"


@pytest.fixture(scope="module")
def adapter():
    return ea.load("claude", TOOLKIT)


def test_exec_block_validates(adapter, tmp_path):
    assert adapter.strategy == "worktree"
    assert adapter.trust_grant == "none"
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    bad = tmp_path / "claude.yml"
    bad.write_text(text.replace("  trust_grant: none\n", "  trust_grant: none\n  surprise: 1\n"))
    with pytest.raises(ha.AdapterError, match="surprise"):
        ha.load_adapter(str(bad), toolkit=TOOLKIT)
    bad.write_text(text.replace("    - --yolo\n", ""))
    with pytest.raises(ha.AdapterError, match="--yolo"):
        ha.load_adapter(str(bad), toolkit=TOOLKIT)
    bad.write_text(text.replace("  working_copy: {strategy: worktree}\n",
                                "  working_copy: {strategy: clone}\n"))
    assert ea.ExecAdapter(ha.load_adapter(str(bad), toolkit=TOOLKIT), TOOLKIT).strategy == "clone"
    bad.write_text(text.replace("  working_copy: {strategy: worktree}\n",
                                "  working_copy: {strategy: floppy}\n"))
    with pytest.raises(ha.AdapterError, match="working_copy"):
        ha.load_adapter(str(bad), toolkit=TOOLKIT)


def test_no_exec_block_names_the_sibling_req():
    with pytest.raises(ea.ExecRefused, match="REQ-662"):
        ea.load("codex", TOOLKIT)
    with pytest.raises(ea.ExecRefused, match="no adapter ships"):
        ea.load("gemini", TOOLKIT)


def test_deny_superset(adapter):
    allow, deny = adapter.tiers(BRANCH)
    perms = ha.load_permissions(ha.permissions_path(TOOLKIT))
    for entry in perms["entries"]:
        if entry["tier"] == "deny":
            for argv in entry["commands"]:
                assert "Bash(%s:*)" % " ".join(argv) in deny
    for needed in ("gh pr merge", "az repos pr", "terraform apply", "terraform destroy",
                   "./deploy.sh", "git push --force", "git push -f", "git worktree remove",
                   "git worktree prune", "git branch -D", "git reset --hard", "git clean -f",
                   "gh pr close", "gh release", "rm -rf", "rm -f", "rm -r",
                   "adlc sprint-exec approve", "adlc sprint-exec reject",
                   "adlc sprint-exec answer", "adlc sprint-exec abort"):
        assert "Bash(%s:*)" % needed in deny, needed
    assert "Bash(git push origin +*)" in deny
    # BUG-269: a glob deny ends in its own `*`. claude 2.1.316 matched nothing with
    # `Bash(git -C * push --force:*)`, so the engine's `git -C` force-push denies were inert.
    assert "Bash(git -C * push --force*)" in deny and "Bash(git -C * push -f*)" in deny
    for rule in deny:
        body = rule[len("Bash("):-1]
        assert not (body.endswith(":*") and "*" in body[:-2]), rule
    joined = " ".join(allow)
    assert "git -C" not in joined
    assert "Bash(git push:*)" not in allow and "Bash(git branch:*)" not in allow
    assert "Bash(git worktree:*)" not in allow
    assert "Bash(git push)" in allow
    # BUG-260: the REQ's branch push is exact. A prefix rule admitted `<branch> main` and
    # `<branch> --force` after it, and a live `claude -p` pushed main through it.
    assert "Bash(git push -u origin %s)" % BRANCH in allow
    assert "Bash(git push origin %s)" % BRANCH in allow
    for rule in allow:
        if rule.startswith(("Bash(git push", "Bash(git branch", "Bash(git worktree")):
            assert not rule.endswith(":*)"), rule
    # BUG-265: the file tools are never bare; with no roots they are not admitted at all.
    assert "Read" not in allow and "Edit" not in allow and "Write" not in allow


def test_glob_spelling_is_deny_only(adapter):
    """BUG-269: only a deny gets the glob spelling. An allow that holds an inner `*` keeps the
    `:*` it had, which Claude matches with nothing, so this fix widens no allow."""
    argv = ["git", "-C", "*", "push", "--force"]
    assert adapter.spell(argv, deny=True) == "Bash(git -C * push --force*)"
    assert adapter.spell(argv) == "Bash(git -C * push --force:*)"
    assert adapter.spell(["git", "push", "origin", "+*"], deny=True) == "Bash(git push origin +*)"
    assert adapter.spell(["git", "push", "--force"], deny=True) == "Bash(git push --force:*)"


def test_extra_that_wraps_a_deny_is_refused(adapter):
    adapter.tiers(BRANCH, [["pytest"], ["make", "test"]])
    with pytest.raises(ea.ExecRefused, match="wrap deny-tier"):
        adapter.tiers(BRANCH, [["git", "push"]])
    with pytest.raises(ea.ExecRefused, match="wrap deny-tier"):
        adapter.tiers(BRANCH, [["gh"]])
    with pytest.raises(ea.ExecRefused, match="runs its arguments"):
        adapter.tiers(BRANCH, [["sh"]])
    with pytest.raises(ea.ExecRefused, match="will not spell"):
        adapter.tiers(BRANCH, [["ls)", "Bash(rm"]])


def test_prefix_extra_sharing_a_deny_base_is_refused(adapter):
    """BUG-260: under prefix matching anything can follow an allow, so an extra that shares a
    command base with a deny admits that deny's flags after it."""
    for extra, base in ((["git", "push", "-u", "origin", "feat/x"], "git push"),
                        (["git", "branch", "--list"], "git branch"),
                        (["git", "worktree", "list"], "git worktree"),
                        (["rm", "build.log"], "rm"),
                        (["gh", "pr", "view"], "gh pr")):
        with pytest.raises(ea.ExecRefused, match="shares the command base"):
            adapter.tiers(BRANCH, [extra])
    allow, _deny = adapter.tiers(BRANCH, [["pytest"], ["make", "test"], ["git", "log"]])
    assert "Bash(git log:*)" in allow


def test_forbidden_flags(adapter):
    allow, deny = adapter.tiers(BRANCH)
    argv = adapter.launch_argv("/bin/fake", allow, deny)
    assert "--allowedTools" in argv and "--disallowedTools" in argv
    assert ea.forbidden_in(argv, adapter.forbidden) is None
    for extra, name in ((["--dangerously-skip-permissions"], "--dangerously-skip-permissions"),
                        (["--permission-mode", "bypassPermissions"],
                         "--permission-mode bypassPermissions"),
                        (["--permission-mode=bypassPermissions"],
                         "--permission-mode bypassPermissions"),
                        (["--yolo"], "--yolo"), (["--force"], "--force")):
        with pytest.raises(ea.ExecRefused, match="Rule B") as exc:
            adapter.launch_argv("/bin/fake", allow, deny, extra=extra)
        assert name in str(exc.value)
    assert ea.forbidden_in(["--permission-mode", "acceptEdits"], adapter.forbidden) is None


def test_exit_class(adapter):
    plain = {"denials": []}
    assert adapter.exit_class(0, plain, "awaiting_approval") == "ok"
    assert adapter.exit_class(1, plain, None) == "error"
    assert adapter.exit_class(99, plain, None) == "error"
    assert adapter.exit_class(None, plain, None) == "error"
    denied = {"denials": [{"tool_name": "Bash"}]}
    assert adapter.exit_class(0, denied, None) == "denied"
    assert adapter.exit_class(0, denied, "awaiting_approval") == "ok"
    mapped = ea.ExecAdapter(dict(adapter.adapter, exec=dict(
        adapter.block, exit_codes={"0": "ok", "77": "denied", "124": "timeout"})), TOOLKIT)
    assert mapped.exit_class(77, plain, None) == "denied"
    assert mapped.exit_class(124, plain, None) == "timeout"


def test_child_env(adapter):
    environ = {"HOME": "/h", "PATH": "/b", "ADLC_HOME": "/a", "GH_TOKEN": "operator",
               "GITHUB_TOKEN": "operator2", "SECRET_THING": "x", "SSH_AUTH_SOCK": "/s",
               "ANTHROPIC_API_KEY": "k", "ADLC_FORGE_MOCK": "1"}
    env = adapter.child_env(environ, "REQ-901", "scoped", "/run/gh", False)
    assert env["GH_TOKEN"] == "scoped" and env["GH_CONFIG_DIR"] == "/run/gh"
    assert "GITHUB_TOKEN" not in env and "SECRET_THING" not in env
    assert env["ADLC_EXEC_RUN"] == "REQ-901" and env["ANTHROPIC_API_KEY"] == "k"
    assert set(env) <= set(adapter.block["env_passthrough"]) | set(adapter.block["auth_env"]) \
        | {"ADLC_EXEC_RUN", "GH_TOKEN", "GH_CONFIG_DIR"}
    shared = adapter.child_env(environ, "REQ-901", None, "/run/gh", True)
    assert shared["GH_TOKEN"] == "operator" and "GH_CONFIG_DIR" not in shared
    assert "GITHUB_TOKEN" not in shared


def test_parse_result(adapter):
    doc = {"session_id": "abc-1", "is_error": True, "num_turns": 3, "result": "Terminal state: blocked\nx",
           "total_cost_usd": 0.5, "permission_denials": [{"t": 1}]}
    out = adapter.parse_result(json.dumps(doc))
    assert out["session_id"] == "abc-1" and out["cost"] == 0.5 and out["denials"] == [{"t": 1}]
    assert ea.terminal_claim(out["text"]) == "blocked"
    assert ea.terminal_claim("All done") is None
    noisy = adapter.parse_result("noise\n" + json.dumps(doc) + "\n")
    assert noisy["num_turns"] == 3
    hostile = adapter.parse_result(json.dumps(dict(doc, session_id="x; rm -rf /")))
    assert hostile["session_id"] is None
    assert adapter.parse_result("not json")["present"] is False


def test_isolation_detection(adapter):
    help_text = "  --setting-sources <s>  x\n  --settings <f>  y\n  --strict-mcp-config   z\n"
    assert adapter.isolation_available(help_text)
    assert not adapter.isolation_available(help_text.replace("--strict-mcp-config", "--other"))
    flags = adapter.isolation_flags("/run/settings.json")
    assert flags == ["--setting-sources", "", "--settings", "/run/settings.json",
                     "--strict-mcp-config"]
    doc = adapter.settings_document(["Read"], ["Bash(rm -f:*)"])
    assert doc == {"permissions": {"allow": ["Read"], "deny": ["Bash(rm -f:*)"]}}
    assert "hooks" not in doc


def test_residuals_declared(adapter):
    text = " ".join(adapter.block["residuals"])
    for word in ("sh -c", "gh api", "gh -R", "semantic equivalent", "Azure DevOps", "merge bot"):
        assert word in text


#: Claude's file tools. A bare name in an allow list admits the tool on every path.
FILE_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep")


def test_file_tools_are_scoped_to_roots(adapter):
    """BUG-265: a bare `Write` wrote outside the working copy, so the toolkit the
    orchestrator sources at approve time was writable by the model."""
    allow, _deny = adapter.tiers(BRANCH, write_roots=["/w/wc", "/w/spec"],
                                 read_roots=["/t/tk"])
    assert not [a for a in allow if a in FILE_TOOLS]
    for rule in ("Edit(//w/wc/**)", "Read(//w/wc/**)", "Edit(//w/spec/**)",
                 "Read(//w/spec/**)", "Read(//t/tk/**)"):
        assert rule in allow
    assert not [a for a in allow if a.startswith(("Edit(", "Write(")) and "//w/" not in a]
    assert "Edit(//t/tk/**)" not in allow


def test_bare_file_tool_in_allow_tools_is_refused(tmp_path):
    """BUG-265: the loader refuses a bare file tool, so no adapter can bring it back."""
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    bad = tmp_path / "claude.yml"
    bad.write_text(text.replace("  allow_tools: [", "  allow_tools: [Write, ", 1))
    with pytest.raises(ha.AdapterError, match="Write"):
        ha.load_adapter(str(bad), toolkit=TOOLKIT)


@pytest.mark.parametrize("root", ["rel/path", "/a/../b", "/a b", "/a/*", "/a/", "//a", "/a/(x)", ""])
def test_unsafe_file_root_is_refused(adapter, root):
    """BUG-265: a root becomes a gitignore-style pattern, so a glob or a traversal in it
    would widen the rule."""
    with pytest.raises(ea.ExecRefused, match="root"):
        adapter.tiers(BRANCH, write_roots=[root])


def test_symlinked_root_gets_both_spellings(adapter, tmp_path):
    """BUG-265: Claude matches a file rule against the path as written, and a live row's
    write under /var/... was refused by a rule on /private/var/...: both spellings of a root
    are emitted, and both name the one directory."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    allow, _deny = adapter.tiers(BRANCH, write_roots=[str(link)])
    edits = [a for a in allow if a.startswith("Edit(")]
    assert edits == ["Edit(/%s/**)" % link, "Edit(/%s/**)" % os.path.realpath(str(real))]


@pytest.mark.parametrize("extra", [["."], [".", "/abs/tk/partials/forge.sh"], ["source"],
                                   ["source", "/abs/tk/partials/forge.sh"], ["["], ["if"],
                                   ["eval"], ["python3"], ["git", "-C"]])
def test_opener_extras_are_refused(adapter, extra):
    """REQ-682 BR-7: no exec allow is an opener. `Bash(. :*)` and `Bash(source:*)` passed
    before; `git -C` would admit `git -C <path> push --force`."""
    with pytest.raises(ea.ExecRefused, match="runs its arguments|wrap deny-tier|will not spell"):
        adapter.tiers(BRANCH, [extra])


def test_opener_in_adapter_allow_extra_is_refused_by_the_loader(tmp_path):
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    bad = tmp_path / "claude.yml"
    for opener in ("source", "eval", "python3"):
        bad.write_text(text.replace("  allow_extra_exact:\n",
                                    "  allow_extra_exact:\n    - [%s, x]\n" % opener, 1))
        with pytest.raises(ha.AdapterError, match="runs its arguments"):
            ha.load_adapter(str(bad), toolkit=TOOLKIT)


def test_current_extras_still_accepted(adapter):
    """Benign path: the adapter's own extras and the usual project extras still render."""
    allow, _deny = adapter.tiers(BRANCH, [["pytest"], ["make", "test"], ["tox"]])
    for rule in ("Bash(pytest:*)", "Bash(make test:*)", "Bash(tox:*)", "Bash(git status:*)",
                 "Bash(git push -u origin %s)" % BRANCH, "Bash(ls:*)"):
        assert rule in allow, rule


def test_inert_fence_allows_retired(adapter):
    """REQ-682 BR-7: the exec tier admits fences through the fence runner by its one absolute
    path, and no longer carries the two allows that matched nothing (probe rows 9, 14)."""
    import exec_matcher as em
    allow, _deny = adapter.tiers(BRANCH)
    runner = os.path.join(os.path.realpath(TOOLKIT), "tools", "adlc", "fence-run")
    assert "Bash(%s:*)" % runner in allow
    assert "Bash(ADLC_TOOLKIT_ROOT=:*)" not in allow
    assert not [a for a in allow if "partials/" in a]
    assert em.opener_allows({"allow": allow}) == []
    assert em.admits({"allow": allow}, "%s run validate/SKILL.md#1:00000000" % runner)
    assert not em.admits({"allow": allow}, "%s-evil run x" % runner)
    assert not em.admits({"allow": allow}, "%s run x; git push origin HEAD:main" % runner)


def test_fence_runner_outside_the_root_refuses_the_launch(adapter, tmp_path):
    root = tmp_path / "tk"
    (root / "tools" / "adlc").mkdir(parents=True)
    outside = tmp_path / "evil"
    outside.write_text("#!/bin/sh\n")
    (root / "tools" / "adlc" / "fence-run").symlink_to(outside)
    moved = ea.ExecAdapter(adapter.adapter, str(root))
    with pytest.raises(ea.ExecRefused, match="fence runner"):
        moved.fence_runner()
    (root / "tools" / "adlc" / "fence-run").unlink()
    with pytest.raises(ea.ExecRefused, match="fence runner"):
        moved.fence_runner()
    spaced = tmp_path / "a b"
    (spaced / "tools" / "adlc").mkdir(parents=True)
    (spaced / "tools" / "adlc" / "fence-run").write_text("#!/bin/sh\n")
    with pytest.raises(ea.ExecRefused, match="fence runner"):
        ea.ExecAdapter(adapter.adapter, str(spaced)).fence_runner()


# ---------------------------------------------------------------- exec schema 2 (REQ-662)
FIX = os.path.join(HERE, "fixtures", "harness")
#: The three schema-2 blocks: the migrated claude block and one fixture of each render form.
#: A check proven on one of them has only proven that one's branches (LESSON-756).
SCHEMA_2 = ("claude", "fake-exec-flags", "fake-exec-file")


def _source(base):
    if base == "claude":
        return open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    return open(os.path.join(FIX, base + ".yml"), encoding="utf-8").read()


def _key_span(lines, key):
    """The lines of ``exec.<key>``: its own line and every deeper-indented line after it."""
    start = next(i for i, line in enumerate(lines) if line.startswith("  %s:" % key))
    end = start + 1
    while end < len(lines) and (lines[end].startswith("   ") or
                                lines[end].startswith("  - ")):
        end += 1
    return start, end


def _edit(text, drop=(), put=None, add=None):
    """``text`` with exec keys dropped, one key's value replaced, or one line added."""
    lines = text.split("\n")
    for key in drop:
        start, end = _key_span(lines, key)
        del lines[start:end]
    if put:
        key, value = put
        start, end = _key_span(lines, key)
        lines[start:end] = ["  %s: %s" % (key, value)]
    if add:
        start, _end = _key_span(lines, "exec_schema_version")
        lines.insert(start + 1, "  " + add)
    return "\n".join(lines)


def _write(tmp_path, base, text):
    d = tmp_path / ("v%d" % len(list(tmp_path.glob("v*"))))
    d.mkdir()
    path = d / (base + ".yml")
    path.write_text(text, encoding="utf-8")
    return str(path)


def _refused(tmp_path, base, **edit):
    path = _write(tmp_path, base, _edit(_source(base), **edit))
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(path, toolkit=TOOLKIT)
    return exc.value


def _loads(tmp_path, base, **edit):
    return ha.load_adapter(_write(tmp_path, base, _edit(_source(base), **edit)), toolkit=TOOLKIT)


REFUSALS = [
    ({"add": "surprise: 1"}, "exec.surprise"),
    ({"drop": ["exit_codes"]}, "exec.exit_codes"),
    ({"put": ("exit_codes", '{"1": error}')}, "exec.exit_codes"),
    ({"put": ("exec_schema_version", "3")}, "exec.exec_schema_version"),
    ({"put": ("exec_schema_version", "1")}, "exec.exec_schema_version"),
    ({"drop": ["forbidden_flags"]}, "exec.forbidden_flags"),
    ({"drop": ["config_surfaces"]}, "exec.config_surfaces"),
    ({"drop": ["rules_reload"]}, "exec.rules_reload"),
    ({"drop": ["bypass_config_keys"]}, "exec.bypass_config_keys"),
    ({"drop": ["prompt_variant"]}, "exec.prompt_variant"),
    ({"put": ("rules_reload", "sometimes")}, "exec.rules_reload"),
    ({"drop": ["context_delivery"]}, "exec.context_delivery"),
    ({"put": ("context_delivery", "telepathy")}, "exec.context_delivery"),
    ({"drop": ["harness_version"]}, "exec.harness_version"),
    ({"put": ("verification", "vibes")}, "exec.verification"),
    ({"put": ("status", "probably")}, "exec.status"),
    ({"put": ("prompt_delivery", "argv")}, "exec.prompt_delivery"),
    ({"put": ("matcher", "regex")}, "exec.matcher"),
    ({"put": ("allow_render", "telepathy")}, "exec.allow_render"),
    ({"drop": ["output"]}, "exec.output"),
    ({"put": ("output", "json")}, "exec.output"),
    ({"put": ("resume", "[--resume, x]")}, "exec.resume"),
    ({"put": ("shell_timeout_s", "{value: 60, verified: true, delegate: supported}")},
     "exec.shell_timeout_s.delegate"),
    ({"put": ("shell_timeout_s", "{value: 125, verified: maybe, delegate: supported}")},
     "exec.shell_timeout_s.verified"),
    ({"put": ("operator_flags", "[model]")}, "exec.operator_flags[0]"),
    ({"drop": ["engine_deny"]}, "exec.engine_deny"),
    ({"drop": ["fence_runner"]}, "exec.fence_runner"),
]


@pytest.mark.parametrize("base", SCHEMA_2)
@pytest.mark.parametrize("edit, field", REFUSALS)
def test_schema_2_refusals_name_the_key(tmp_path, base, edit, field):
    """REQ-662 BR-1, AC-1: each defect refuses the whole adapter, never a partial load, and
    the refusal names the key."""
    assert _refused(tmp_path, base, **edit).field == field


@pytest.mark.parametrize("base", SCHEMA_2)
def test_prompt_variant_follows_the_launch(tmp_path, base):
    """The variant is the one whose prompt_flag tokens the launch holds or lacks, so the gate
    reads the stdin-prompt sub-result the launch actually implements."""
    block = ha.load_adapter(_write(tmp_path, base, _source(base)), toolkit=TOOLKIT)["exec"]
    other = [v for v in ha.PROMPT_VARIANTS if v != block["prompt_variant"]][0]
    assert _refused(tmp_path, base, put=("prompt_variant", other)).field == \
        "exec.prompt_variant"
    assert _refused(tmp_path, base, put=("prompt_variant", "no-flag")).field == \
        "exec.prompt_variant"
    # Moving the flag in or out of launch with the variant kept is the same disagreement,
    # and with the variant moved to match, the block loads again.
    if block["prompt_variant"] == "with-prompt-flag":
        moved = [t for t in block["launch"] if t not in block["prompt_flag"]]
    else:
        moved = block["launch"] + block["prompt_flag"]
    assert _refused(tmp_path, base, put=("launch", json.dumps(moved))).field == \
        "exec.prompt_variant"
    text = _edit(_edit(_source(base), put=("launch", json.dumps(moved))),
                 put=("prompt_variant", other))
    assert ha.load_adapter(_write(tmp_path, base, text), toolkit=TOOLKIT)["exec"][
        "prompt_variant"] == other
    assert _refused(tmp_path, base, put=("prompt_flag", "[]")).field == "exec.prompt_flag"
    assert _refused(tmp_path, base, put=("prompt_flag", '[-p, ""]')).field == \
        "exec.prompt_flag[1]"


@pytest.mark.parametrize("base, key, value", [
    ("fake-exec-file", "allow_flag", "--allow-tool"),
    ("fake-exec-file", "shell_rule", '"shell(%s:*)"'),
    ("fake-exec-file", "shell_rule_exact", '"shell(%s)"'),
    ("fake-exec-file", "settings_keys", "{allow: [a], deny: [d]}"),
    ("fake-exec-file", "deny_flag", "--deny-tool"),
    ("claude", "rule_file", ".claude/adlc-exec.rules"),
    ("fake-exec-flags", "rule_file", ".fake-exec-flags/adlc-exec.rules"),
])
def test_a_key_for_the_other_render_form_is_refused(tmp_path, base, key, value):
    """REQ-662 ADR-1: a key one form reads is refused on the other, so no block carries a
    field the engine never reads."""
    assert _refused(tmp_path, base, add="%s: %s" % (key, value)).field == "exec." + key


@pytest.mark.parametrize("base, key", [
    ("claude", "allow_flag"), ("claude", "shell_rule"), ("claude", "settings_keys"),
    ("claude", "deny_flag"), ("fake-exec-flags", "allow_flag"),
    ("fake-exec-file", "rule_file"),
])
def test_a_key_its_render_form_needs_is_required(tmp_path, base, key):
    assert _refused(tmp_path, base, drop=[key]).field == "exec." + key


def test_deny_render_and_the_user_policy_file(tmp_path):
    """A rendered deny needs a harness that can deny; a user policy file holds a file-rendered
    deny tier only, and lives under a user path."""
    no_deny = _source("fake-exec-flags").replace('  deny: "yes"', '  deny: "no"')
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(_write(tmp_path, "fake-exec-flags", no_deny), toolkit=TOOLKIT)
    assert exc.value.field == "exec.deny_render"
    assert _refused(tmp_path, "claude", put=("user_policy_file", "$HOME/.claude/x.rules")).field \
        == "exec.user_policy_file"
    assert _refused(tmp_path, "fake-exec-file",
                    put=("user_policy_file", "/etc/x.rules")).field == "exec.user_policy_file"
    assert _refused(tmp_path, "fake-exec-file",
                    put=("user_policy_file", "$HOME/../x.rules")).field == \
        "exec.user_policy_file"
    assert _loads(tmp_path, "fake-exec-file", put=("user_policy_file", "none"))


def test_surfaces_and_bypass_keys(tmp_path):
    """REQ-662 BR-15, BR-16: a surface is a working-copy path; a bypass key is scanned in a
    user path or a declared surface. Both lists may be empty only under config_isolation."""
    for base in ("fake-exec-flags", "fake-exec-file"):
        assert _refused(tmp_path, base, put=("config_surfaces", "[]")).field == \
            "exec.config_surfaces"
        assert _refused(tmp_path, base, put=("bypass_config_keys", "{}")).field == \
            "exec.bypass_config_keys"
    assert _refused(tmp_path, "fake-exec-file",
                    put=("config_surfaces", "[/etc/fake]")).field == "exec.config_surfaces[0]"
    assert _refused(tmp_path, "fake-exec-file",
                    put=("bypass_config_keys", '{".other/config.toml": [x]}')).field == \
        "exec.bypass_config_keys..other/config.toml"
    assert _refused(tmp_path, "fake-exec-file",
                    put=("bypass_config_keys", '{"$HOME/.f/config.toml": []}')).field == \
        "exec.bypass_config_keys.$HOME/.f/config.toml"
    # claude's isolation flags keep it from reading any config: both empty, and that holds
    # only while the flags are declared.
    block = ea.load("claude", TOOLKIT).block
    assert block["config_surfaces"] == [] and block["bypass_config_keys"] == {}
    assert _refused(tmp_path, "claude", drop=["config_isolation"]).field == \
        "exec.config_surfaces"


@pytest.mark.parametrize("base", SCHEMA_2)
def test_working_copy_strategy_is_an_object(tmp_path, base):
    """REQ-662 BR-9: `working_copy` is `{strategy}` with REQ-659's enum, and `worktree` needs
    the top-level `sandbox_can_reach_common_gitdir: true`."""
    assert _refused(tmp_path, base, put=("working_copy", "worktree")).field == \
        "exec.working_copy"
    assert _refused(tmp_path, base, put=("working_copy", "{strategy: floppy}")).field == \
        "exec.working_copy.strategy"
    assert _refused(tmp_path, base, put=("working_copy", "{strategy: clone, depth: 1}")).field \
        == "exec.working_copy.depth"
    for strategy in ("clone", "orchestrator-git"):
        loaded = _loads(tmp_path, base, put=("working_copy", "{strategy: %s}" % strategy))
        assert ea.ExecAdapter(loaded, TOOLKIT).strategy == strategy
    text = _edit(_source(base), put=("working_copy", "{strategy: worktree}"))
    unreached = "\n".join(line for line in text.split("\n")
                          if not line.startswith("sandbox_can_reach_common_gitdir:"))
    with pytest.raises(ha.AdapterError) as exc:
        ha.load_adapter(_write(tmp_path, base, unreached), toolkit=TOOLKIT)
    assert exc.value.field == "exec.working_copy.strategy"
    assert "sandbox_can_reach_common_gitdir" in str(exc.value)
    reached = unreached.replace("\nhook_events:", "\nsandbox_can_reach_common_gitdir: true"
                                "\nhook_events:", 1)
    loaded = ha.load_adapter(_write(tmp_path, base, reached), toolkit=TOOLKIT)
    assert ea.ExecAdapter(loaded, TOOLKIT).strategy == "worktree"


@pytest.mark.parametrize("base", SCHEMA_2)
def test_exit_map_needs_zero_and_the_closed_vocabulary(tmp_path, base):
    """REQ-659 BR-21, REQ-662 BR-8: `"0": ok` is required, and every class is an ExitClass."""
    for exits, field in (('{"1": error}', "exec.exit_codes"),
                         ('{"0": error, "1": error}', "exec.exit_codes"),
                         ('{"0": ok, "2": crashed}', "exec.exit_codes.2"),
                         ('{"0": ok, "x": error}', "exec.exit_codes"),
                         ('{"0": ok, "01": error}', "exec.exit_codes"),
                         ("[0]", "exec.exit_codes")):
        assert _refused(tmp_path, base, put=("exit_codes", exits)).field == field, exits
    loaded = _loads(tmp_path, base, put=("exit_codes",
                                         '{"0": ok, "1": error, "77": denied, "124": timeout}'))
    assert ea.ExecAdapter(loaded, TOOLKIT).exit_class(124, {"denials": []}, None) == "timeout"


@pytest.mark.parametrize("base", ("fake-exec-flags", "fake-exec-file"))
def test_a_fixture_of_each_render_form_loads(base):
    """The must-not-refuse case: a full schema-2 block of each render form loads whole."""
    adapter = ea.load(base, TOOLKIT, adapter_path=os.path.join(FIX, base + ".yml"))
    block = adapter.block
    assert block["exec_schema_version"] == ha.EXEC_SCHEMA_VERSION == 2
    assert block["allow_render"] == base.rsplit("-", 1)[1]
    assert adapter.resume_tokens("S-1").count("S-1") == 1
    assert "{session_id}" not in adapter.resume_tokens("S-1")


def test_output_shapes(tmp_path):
    """REQ-662 ADR-6: a field is a key path under `json` and `{event, key}` under
    `jsonl-stream`; a file-read final message is a placeholder the launch hands the harness."""
    for put, field in ((("output", "{format: json, source: stdout, session_id: id}"),
                        "exec.output.final_message"),
                       (("output", "{format: xml, source: stdout, session_id: a, "
                                   "final_message: b}"), "exec.output.format"),
                       (("output", "{format: json, source: stdout, session_id: a, "
                                   "final_message: b, extra: c}"), "exec.output.extra"),
                       (("output", "{format: json, source: stdout, session_id: 'a b', "
                                   "final_message: b}"), "exec.output.session_id")):
        assert _refused(tmp_path, "claude", put=put).field == field
    text = _source("fake-exec-file")
    for old, new, field in (
            ('final_message: "{last_message}"', 'final_message: "{elsewhere}"',
             "exec.output.final_message"),
            ('final_message: "{last_message}"', "final_message: last_message",
             "exec.output.final_message"),
            ("session_id: {event: thread.started, key: thread_id}", "session_id: thread_id",
             "exec.output.session_id"),
            ("session_id: {event: thread.started, key: thread_id}",
             "session_id: {event: thread.started}", "exec.output.session_id.key")):
        with pytest.raises(ha.AdapterError) as exc:
            ha.load_adapter(_write(tmp_path, "fake-exec-file", text.replace(old, new)),
                            toolkit=TOOLKIT)
        assert exc.value.field == field, new
    # `terminal_event` is a jsonl-stream key, and an event type (REQ-662 TASK-269).
    assert _refused(tmp_path, "claude", put=("output", "{format: json, source: stdout, "
                                                       "session_id: a, final_message: b, "
                                                       "terminal_event: done}")).field == \
        "exec.output.terminal_event"
    for bad in ("terminal_event: turn completed", "terminal_event: [turn.completed]"):
        with pytest.raises(ha.AdapterError) as exc:
            ha.load_adapter(_write(tmp_path, "fake-exec-file", text.replace(
                "terminal_event: turn.completed", bad)), toolkit=TOOLKIT)
        assert exc.value.field == "exec.output.terminal_event", bad
    assert ha.load_adapter(_write(tmp_path, "fake-exec-file", text.replace(
        "    terminal_event: turn.completed\n", "")), toolkit=TOOLKIT)


# --------------------------------------- output parsed by declared format (REQ-662 ADR-6, BR-6)
OUTPUT = os.path.join(HERE, "fixtures", "exec-output")


def _fixture(name):
    with open(os.path.join(OUTPUT, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def stream():
    """The Codex-shaped fixture: JSONL events on stdout, the last message in the -o file."""
    return ea.load("fake-exec-file", TOOLKIT, adapter_path=os.path.join(FIX, "fake-exec-file.yml"))


def test_jsonl_parser_and_its_failures(stream):
    """REQ-662 BR-6, AC-6: a well-formed stream yields `thread.started`'s id and the -o file's
    message (the must-not-fail case); a truncated stream, a cut last line, non-JSON stdout and
    an empty or missing final message each yield the parser's message, which classifies the
    run `error`, never `ok`, whatever the exit code said."""
    good = _fixture("codex-jsonl.synthetic.stdout.jsonl")
    message = _fixture("codex-jsonl.synthetic.last-message.txt")
    out = stream.parse_result(good, message)
    assert out["error"] is None and out["present"] is True
    assert out["session_id"] == "0199c0de-5a1e-7f00-9c0d-e00000000001"
    assert out["text"] == message and ea.terminal_claim(out["text"]) == "awaiting_approval"
    assert stream.exit_class(0, out, "awaiting_approval") == "ok"
    for name, last, words in (
            ("codex-jsonl-no-terminal.synthetic.stdout.jsonl", message,
             "no turn.completed event"),
            ("codex-jsonl-cut.synthetic.stdout.jsonl", message, "last line is cut"),
            ("not-json.synthetic.stdout.txt", message, "line 1 is not JSON"),
            ("codex-jsonl.synthetic.stdout.jsonl",
             _fixture("codex-jsonl-empty-message.synthetic.last-message.txt"),
             "final message is empty"),
            ("codex-jsonl.synthetic.stdout.jsonl", None, "no last-message file"),
            ("codex-jsonl.synthetic.stdout.jsonl", "  \n", "final message is empty")):
        out = stream.parse_result(_fixture(name), last)
        assert words in out["error"], (name, out["error"])
        claim = ea.terminal_claim(out["text"])
        assert stream.exit_class(0, out, claim) == "error", name
        assert stream.exit_class(1, out, claim) == "error", name
    # What parsed before a failure is still read: a cut stream keeps its session id.
    cut = stream.parse_result(_fixture("codex-jsonl-cut.synthetic.stdout.jsonl"), message)
    assert cut["session_id"] == "0199c0de-5a1e-7f00-9c0d-e00000000001"
    # An empty stdout, a JSON line that is not an event and a mid-stream non-JSON line fail.
    for text, words in (("", "stdout is empty"), ('[1, 2]\n', "is not an event"),
                        ('{"type": "thread.started", "thread_id": "t"}\nWARN x\n'
                         '{"type": "turn.completed"}\n', "line 2 is not JSON")):
        assert words in stream.parse_result(text, message)["error"]
    # No session id is not a parse failure (it makes resume impossible, BR-7), and a value
    # that is not a session id is dropped, as under `json`.
    lines = good.splitlines(True)
    assert stream.parse_result("".join(lines[1:]), message)["error"] is None
    assert stream.parse_result("".join(lines[1:]), message)["session_id"] is None
    hostile = good.replace("0199c0de-5a1e-7f00-9c0d-e00000000001", "x; rm -rf /")
    assert stream.parse_result(hostile, message)["session_id"] is None


def test_jsonl_fields_take_the_first_session_and_the_last_message(stream):
    """REQ-662 ADR-6: under jsonl-stream `session_id` is read from the first event of its type
    where the key is set, and every other field from the last; under `source: stdout` the
    final message comes from the stream."""
    adapter = ea.ExecAdapter(dict(stream.adapter, exec=dict(stream.block, output={
        "format": "jsonl-stream", "source": "stdout", "terminal_event": "turn.completed",
        "session_id": {"event": "thread.started", "key": "thread_id"},
        "final_message": {"event": "item.completed", "key": "item.text"},
        "num_turns": {"event": "turn.completed", "key": "usage.turns"}})), TOOLKIT)
    text = "".join(json.dumps(e) + "\n" for e in (
        {"type": "thread.started", "thread_id": "first-1"},
        {"type": "thread.started", "thread_id": "second-2"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "early"}},
        {"type": "item.completed", "item": {"type": "agent_message",
                                            "text": "Terminal state: blocked"}},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}},
        {"type": "turn.completed", "usage": {"turns": 3}}))
    out = adapter.parse_result(text)
    assert out["session_id"] == "first-1" and out["text"] == "Terminal state: blocked"
    assert out["num_turns"] == 3 and out["error"] is None
    assert "final message is empty" in adapter.parse_result(
        text.replace("Terminal state: blocked", "").replace("early", ""))["error"]


def test_json_parser_is_unchanged_and_fails_closed(adapter):
    """Claude's `json` parser reads what it read before (REQ-662 BR-1); stdout with no result
    object and an empty `result` are parse failures under it too (BR-6)."""
    doc = json.loads(_fixture("claude-json.synthetic.stdout.json"))
    out = adapter.parse_result(_fixture("claude-json.synthetic.stdout.json"))
    assert out["error"] is None and out["session_id"] == doc["session_id"]
    assert out["text"] == doc["result"] and out["num_turns"] == 7 and out["cost"] == 0.42
    # A last-message file, if any, is not read under `source: stdout`.
    assert adapter.parse_result(_fixture("claude-json.synthetic.stdout.json"), "x")["text"] == \
        doc["result"]
    bad = adapter.parse_result(_fixture("not-json.synthetic.stdout.txt"))
    assert bad["present"] is False and "no JSON result object" in bad["error"]
    empty = adapter.parse_result(json.dumps(dict(doc, result="")))
    assert "final message is empty" in empty["error"] and empty["session_id"]
    assert adapter.exit_class(0, empty, None) == "error"


def test_output_fixtures_are_marked_synthetic():
    """REQ-662 BR-6: while an adapter is unverified its parser fixture is marked synthetic, and
    no fixture holds an absolute home path."""
    names = sorted(os.listdir(OUTPUT))
    assert "README.md" in names and "synthetic" in _fixture("README.md")
    for name in names:
        if name != "README.md":
            assert ".synthetic." in name, name
        text = _fixture(name)
        for home in ("/Users/", "/home/", "/root/"):
            assert home not in text, (name, home)


def test_denied_stderr_reads_the_harness_stderr_only():
    """REQ-662 ADR-6, BR-8: a run with no claim whose stderr holds the harness's refusal line is
    `denied`; the same words in the model's message are never read as one, and a claim keeps
    the exit code's class."""
    flags = ea.load("fake-exec-flags", TOOLKIT,
                    adapter_path=os.path.join(FIX, "fake-exec-flags.yml"))
    said = {"denials": [], "text": "Permission denied: shell(rm -rf /)", "error": None}
    assert flags.exit_class(0, said, None, stderr="") == "ok"
    assert flags.exit_class(0, said, None, stderr="ok\n") == "ok"
    line = "Permission denied: shell(git push --force)"
    stderr = "starting\n%s\n" % line
    assert flags.refusal_line(stderr) == line
    assert flags.exit_class(0, {"denials": [], "text": "", "error": None}, None,
                            stderr) == "denied"
    assert flags.exit_class(0, {"denials": [], "text": "x", "error": None},
                            "awaiting_approval", stderr) == "ok"
    # Anchored as the adapter wrote it: a line that only mentions the words is not a refusal.
    assert flags.refusal_line("note: Permission denied: x\n") is None
    # An adapter that declares no pattern reads no refusal from stderr.
    assert ea.load("claude", TOOLKIT).refusal_line(stderr) is None


def test_exit_codes_keep_the_closed_vocabulary(adapter):
    """REQ-662 BR-8: each declared code maps to its class, an undeclared one is `error`, and a
    parse failure turns `ok` into `error` while a declared `denied` or `timeout` stands."""
    mapped = ea.ExecAdapter(dict(adapter.adapter, exec=dict(
        adapter.block, exit_codes={"0": "ok", "1": "error", "42": "error", "53": "denied",
                                   "124": "timeout"})), TOOLKIT)
    plain = {"denials": [], "error": None}
    for rc, klass in ((0, "ok"), (1, "error"), (42, "error"), (53, "denied"), (124, "timeout"),
                      (99, "error"), (None, "error")):
        assert mapped.exit_class(rc, plain, "awaiting_approval") == klass, rc
    broken = {"denials": [], "error": "the stream has no turn.completed event"}
    for rc, klass in ((0, "error"), (53, "denied"), (124, "timeout"), (99, "error")):
        assert mapped.exit_class(rc, broken, "awaiting_approval") == klass, rc
    assert set(ha.EXIT_CLASSES) == {"ok", "denied", "timeout", "error"}


def test_matcher_none_refuses_every_extra_allow(tmp_path):
    """REQ-662 ADR-8: on `matcher: none` nothing can vet an extra allow against the deny tier, so
    any `allow_extra`, `allow_extra_exact` or config extra is refused; with none the tiers
    render (the must-not-refuse case), the fence runner included."""
    plain = ea.ExecAdapter(_loads(tmp_path, "fake-exec-flags"), TOOLKIT)
    allow, _deny = plain.tiers(BRANCH)
    assert any("fence-run" in rule for rule in allow)
    for key in ("allow_extra", "allow_extra_exact"):
        extra = ea.ExecAdapter(_loads(tmp_path, "fake-exec-flags",
                                      add="%s: [[make, test]]" % key), TOOLKIT)
        with pytest.raises(ea.ExecRefused, match="matcher: none"):
            extra.tiers(BRANCH)
    with pytest.raises(ea.ExecRefused, match="matcher: none"):
        plain.tiers(BRANCH, [["pytest"]])
    with pytest.raises(ea.ExecRefused, match="matcher: none"):
        plain.vet_extra(["make", "test"], [], exact=True)


def test_probes_cache_follows_verification(tmp_path):
    """REQ-662 BR-11: `probes` is read under `verification: probes` only, and each row is the
    result file's `{id, ran_at, harness_version, status}`."""
    assert _refused(tmp_path, "fake-exec-file", drop=["probes"]).field == "exec.probes"
    assert _refused(tmp_path, "fake-exec-file", put=("probes", "[]")).field == "exec.probes"
    assert _refused(tmp_path, "claude", add="probes: []").field == "exec.probes"
    text = _source("fake-exec-file")
    for old, new, field in (("      status: pass", "      status: green",
                             "exec.probes[0].status"),
                            ("      status: pass", "      status: pass\n      verdict: ok",
                             "exec.probes[0].verdict")):
        with pytest.raises(ha.AdapterError) as exc:
            ha.load_adapter(_write(tmp_path, "fake-exec-file", text.replace(old, new, 1)),
                            toolkit=TOOLKIT)
        assert exc.value.field == field


def test_claude_block_is_migrated_without_a_behaviour_change(adapter):
    """REQ-662 BR-1: the claude block reads at schema 2 and the engine sees what it saw at 1."""
    block = adapter.block
    assert block["exec_schema_version"] == 2
    for key, value in (("verification", "recorded"), ("status", "verified"),
                       ("context_delivery", "prompt"), ("allow_render", "flags"),
                       ("deny_render", "flags"), ("matcher", "claude"),
                       ("user_policy_file", "none"), ("prompt_delivery", "stdin"),
                       ("prompt_variant", "with-prompt-flag")):
        assert block[key] == value, key
    assert "probes" not in block
    for gone in ("resume_flag", "result_keys", "denied_result_key"):
        assert gone not in block
    allow, deny = adapter.tiers(BRANCH)
    fresh = adapter.launch_argv("/bin/fake", allow, deny, extra=["--model", "m"])
    assert fresh[:4] == ["/bin/fake", "-p", "--output-format", "json"]
    assert "--resume" not in fresh
    resumed = adapter.launch_argv("/bin/fake", allow, deny, resume="abc-1",
                                  extra=["--model", "m"])
    assert resumed[resumed.index("--resume") + 1] == "abc-1"
    assert sorted(resumed) == sorted(fresh + ["--resume", "abc-1"])


def test_resume_needs_a_declared_template(adapter):
    no_resume = ea.ExecAdapter(dict(adapter.adapter, exec={
        k: v for k, v in adapter.block.items() if k != "resume"}), TOOLKIT)
    with pytest.raises(ea.ExecRefused, match="resume is impossible"):
        no_resume.launch_argv("/bin/fake", [], [], resume="abc-1")


@pytest.mark.parametrize("name", ("codex", "copilot", "cursor", "antigravity"))
def test_unstaged_adapters_load_and_are_refused_by_name(name):
    """REQ-662 Amendments 2026-11-17: an adapter whose stage has not run keeps its placeholder
    block, which the loader leaves opaque, and the engine refuses it by name."""
    loaded = ha.resolve_adapter(name, toolkit=TOOLKIT)
    assert "exec_schema_version" not in loaded["exec"]
    with pytest.raises(ea.ExecRefused) as exc:
        ea.load(name, TOOLKIT)
    assert name in str(exc.value) and "REQ-662" in str(exc.value)


# ------------------------------- launch and resume from the templates, closed world (REQ-662)
RUN_DIR = "/run/0123abcd"
WT = "/repo/.worktrees/REQ-901"
LAST = RUN_DIR + "/stdout.last-message.txt"
SETTINGS = RUN_DIR + "/settings.json"
ADDED = "/repo/.adlc/specs/REQ-901-thing"
ALLOW = ["Bash(git status:*)", "Bash(git log:*)"]
DENY = ["Bash(git push --force:*)"]


def _schema2(base):
    if base == "claude":
        return ea.load("claude", TOOLKIT)
    return ea.load(base, TOOLKIT, adapter_path=os.path.join(FIX, base + ".yml"))


def _with(adapter, **block):
    """``adapter`` reading a block with these exec keys replaced."""
    return ea.ExecAdapter(dict(adapter.adapter, exec=dict(adapter.block, **block)), TOOLKIT)


def _launch(adapter, resume=None, extra=(), add_dir=None, allow=ALLOW, values=None):
    """The must-not-refuse launch of ``adapter``: its argv, and what ``closed_world`` reads."""
    values = values or {"worktree": WT, "last_message": LAST, "branch": BRANCH}
    settings = SETTINGS if adapter.block.get("config_isolation") else None
    argv = adapter.launch_argv("/bin/fake", allow, DENY, resume=resume, extra=extra,
                               add_dir=add_dir, settings=settings, values=values)
    pairs = {"operator": list(extra), "isolation": settings is not None, "add_dir": add_dir,
             "allow": list(allow), "deny": DENY}
    return argv, pairs, dict(values, settings=settings, session_id=resume)


def test_launch_argv_snapshot():
    """AC-2: the launch and resume argv of each staged block, token for token. Claude's is
    REQ-659's argv; the file-render fixture is the Codex shape ADR-6 measured, with no `-p`
    and its prompt on stdin."""
    claude = _schema2("claude")
    isolation = ["--setting-sources", "", "--settings", SETTINGS, "--strict-mcp-config"]
    tiers = ["--allowedTools"] + ALLOW + ["--disallowedTools"] + DENY
    assert _launch(claude, extra=["--model", "m"])[0] == (
        ["/bin/fake", "-p", "--output-format", "json", "--model", "m"] + isolation + tiers)
    assert _launch(claude, resume="abc-1", add_dir=ADDED)[0] == (
        ["/bin/fake", "-p", "--output-format", "json", "--resume", "abc-1"] + isolation
        + ["--add-dir", ADDED] + tiers)
    codex_shaped = _schema2("fake-exec-file")
    fresh = _launch(codex_shaped)[0]
    assert fresh == ["/bin/fake", "exec", "--json", "--sandbox", "workspace-write", "-C", WT,
                     "-o", LAST]
    resumed = _launch(codex_shaped, resume="T-1", extra=["--model", "m"])[0]
    assert resumed == ["/bin/fake", "exec", "resume", "--json", "-o", LAST, "T-1", "-",
                       "--model", "m"]
    for argv in (fresh, resumed):
        assert "-p" not in argv and ea.forbidden_in(argv, codex_shaped.forbidden) is None
    flags = _schema2("fake-exec-flags")
    assert _launch(flags, extra=["--model=m"])[0] == (
        ["/bin/fake", "-s", "--output-format", "json", "--no-ask-user", "-C", WT, "--model=m",
         "--allow-tool"] + ALLOW + ["--deny-tool"] + DENY)


def test_placeholders_are_whole_tokens(tmp_path):
    """BR-2: a placeholder is one whole argv token, filled once from a declared value. Inside a
    longer token, undeclared, or with no value, it refuses the launch; so does a value that
    would not read as one argument."""
    stream = _schema2("fake-exec-file")
    stream.check_templates()
    argv = _launch(stream)[0]
    assert argv[argv.index("-C") + 1] == WT and argv[argv.index("-o") + 1] == LAST
    assert not [tok for tok in argv if "{" in tok]
    # A value is never read for placeholders in turn.
    odd = _launch(stream, values={"worktree": "/w/{branch}", "last_message": LAST,
                                  "branch": BRANCH})[0]
    assert odd[odd.index("-C") + 1] == "/w/{branch}"
    for launch in (["exec", "--cd={worktree}", "-o", "{last_message}"],
                   ["exec", "-C", "{worktree}/sub", "-o", "{last_message}"],
                   ["exec", "-C", "x{worktree}", "-o", "{last_message}"],
                   ["exec", "-C", "{worktree}", "-o", "{last_message}{branch}"]):
        partial = _with(stream, launch=launch)
        with pytest.raises(ea.ExecRefused, match="inside a longer token"):
            partial.check_templates()
        with pytest.raises(ea.ExecRefused, match="inside a longer token"):
            _launch(partial)
    with pytest.raises(ea.ExecRefused, match="inside a longer token"):
        _with(stream, resume=["exec", "resume", "--id={session_id}", "-"]).resume_tokens("S-1")
    # The loader reads such a template, so the engine's pre-flight is the check.
    text = open(os.path.join(FIX, "fake-exec-file.yml"), encoding="utf-8").read()
    loaded = ea.ExecAdapter(ha.load_adapter(_write(tmp_path, "fake-exec-file", text.replace(
        '-C, "{worktree}"', '"--cd={worktree}"')), toolkit=TOOLKIT), TOOLKIT)
    with pytest.raises(ea.ExecRefused, match="inside a longer token"):
        loaded.check_templates()
    with pytest.raises(ea.ExecRefused, match="not a placeholder the engine fills"):
        _launch(_with(stream, launch=["exec", "-C", "{home}", "-o", "{last_message}"]))
    with pytest.raises(ea.ExecRefused, match="only a resume has one"):
        _with(stream, launch=["exec", "{session_id}", "-o", "{last_message}"]).check_templates()
    with pytest.raises(ea.ExecRefused, match="{last_message} has no value"):
        _launch(stream, values={"worktree": WT})
    for name, value, word in (("worktree", "repo/wt", "absolute"),
                              ("worktree", "--yolo", "leading"),
                              ("last_message", "/run/a\nb", "control"),
                              ("last_message", "", "empty")):
        values = {"worktree": WT, "last_message": LAST, "branch": BRANCH}
        values[name] = value
        with pytest.raises(ea.ExecRefused, match=word):
            _launch(stream, values=values)
    with pytest.raises(ea.ExecRefused, match="not a session id"):
        _launch(stream, resume="x; rm -rf /")
    # Claude's whole-token placeholders: the session id and the settings file.
    claude = _schema2("claude")
    argv = _launch(claude, resume="abc-1")[0]
    assert argv[argv.index("--resume") + 1] == "abc-1"
    assert argv[argv.index("--settings") + 1] == SETTINGS


def _tampered(argv):
    """Every argv one token away from ``argv``: one extra, one changed, one reordered."""
    out = []
    for i in range(1, len(argv) + 1):
        out.append(argv[:i] + ["--verbose"] + argv[i:])
        out.append(argv[:i] + ["value"] + argv[i:])
    for i in range(1, len(argv)):
        changed = list(argv)
        changed[i] += "x"
        out.append(changed)
        if i + 1 < len(argv) and argv[i] != argv[i + 1]:
            swapped = list(argv)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            out.append(swapped)
    out.append(argv[:-1])
    return out


@pytest.mark.parametrize("resume", (None, "S-1"), ids=("launch", "resume"))
@pytest.mark.parametrize("base", SCHEMA_2)
def test_closed_world_argv(base, resume):
    """BR-16, AC-19: the final argv is the template with only declared placeholders filled and
    the declared additions: the operator's flags, the isolation tokens, the --add-dir pair and
    the renderer's allow and deny pairs. What the builder made is accepted (the must-not-refuse
    case); one extra, one changed and one reordered token are each refused, at launch and at
    resume."""
    adapter = _schema2(base)
    template = "resume" if resume else "launch"
    extra = [adapter.block["operator_flags"][0], "m"]
    add_dir = ADDED if adapter.block.get("add_dir_flag") else None
    argv, pairs, values = _launch(adapter, resume=resume, extra=extra, add_dir=add_dir)
    assert adapter.closed_world(argv, template, pairs, values) == argv
    if adapter.block["allow_render"] == "flags":
        assert adapter.block["allow_flag"] in argv and adapter.block["deny_flag"] in argv
    tampered = _tampered(argv)
    assert len(tampered) > 3 * len(argv)
    for bad in tampered:
        with pytest.raises(ea.ExecRefused, match="closed world"):
            adapter.closed_world(bad, template, pairs, values)
    other = "launch" if resume else "resume"
    with pytest.raises(ea.ExecRefused, match="closed world"):
        adapter.closed_world(argv, other, pairs, dict(values, session_id="S-2"))
    with pytest.raises(ea.ExecRefused, match="not an addition"):
        adapter.closed_world(argv, template, dict(pairs, env=["X=1"]), values)


def test_only_the_renderer_pairs_are_added():
    """AC-19: on a file-render block no allow or deny pair is an addition, and on a flags block
    a rule that would read as a flag is not a rule."""
    stream = _schema2("fake-exec-file")
    argv, pairs, values = _launch(stream)
    assert "--allow-tool" not in argv
    for added in (["--allow-tool", "shell(rm)"], ["--deny-tool", "shell(ls)"]):
        with pytest.raises(ea.ExecRefused, match="closed world"):
            stream.closed_world(argv + added, "launch", pairs, values)
    claude = _schema2("claude")
    for smuggled in ("--add-dir", "-p", "--mcp-config"):
        with pytest.raises(ea.ExecRefused, match="not one rule argument"):
            _launch(claude, allow=ALLOW + [smuggled])


@pytest.mark.parametrize("resume", (None, "S-1"), ids=("launch", "resume"))
@pytest.mark.parametrize("token", (["-c", "sandbox_mode=danger-full-access"],
                                   ["-c=sandbox_mode=danger-full-access"],
                                   ["--config", "approval_policy=never"],
                                   ["--config=approval_policy=never"],
                                   ["-p", "yolo"], ["--profile", "yolo"], ["--profile=yolo"]),
                         ids=lambda t: t[0].split("=")[0] + ("=" if "=" in t[0] else ""))
def test_config_and_profile_tokens_off_the_template_are_refused(token, resume):
    """BR-16: a `-c`, `--config`, `-p` or `--profile` token the template does not hold is
    refused on the file-render fixture, at launch and at resume, wherever it sits and however
    it reached the argv."""
    stream = _schema2("fake-exec-file")
    template = "resume" if resume else "launch"
    argv, pairs, values = _launch(stream, resume=resume)
    for at in range(1, len(argv) + 1):
        with pytest.raises(ea.ExecRefused, match="closed world"):
            stream.closed_world(argv[:at] + token + argv[at:], template, pairs, values)
    with pytest.raises(ea.ExecRefused):
        _launch(stream, resume=resume, extra=token)


def test_operator_flags_filter_harness_flags(adapter):
    """ADR-7: an operator's --harness-flag reaches the harness only when its flag is one
    `operator_flags` names, with at most its value; the must-not-refuse case launches."""
    assert adapter.block["operator_flags"] == ["--model", "--max-turns"]
    for ok in ([], ["--model", "m"], ["--model=m"], ["--max-turns", "3", "--model", "m"]):
        assert adapter.operator_tokens(ok) == ok
        argv = adapter.launch_argv("/bin/fake", [], [], extra=ok)
        assert argv[4:4 + len(ok)] == ok
    for bad, word in ((["--add-dir", "/"], "operator_flags"),
                      (["--permission-mode", "acceptEdits"], "operator_flags"),
                      (["--settings", "/tmp/x.json"], "operator_flags"),
                      (["--modelx", "m"], "operator_flags"),
                      (["--model", "m", "n"], "neither"),
                      (["a prompt"], "neither"),
                      (["--model", "a\nb"], "control")):
        with pytest.raises(ea.ExecRefused, match=word):
            adapter.operator_tokens(bad)
        with pytest.raises(ea.ExecRefused, match=word):
            adapter.launch_argv("/bin/fake", [], [], extra=bad)
    # A forbidden flag is still named as one: the backstop speaks first.
    with pytest.raises(ea.ExecRefused, match="Rule B"):
        adapter.launch_argv("/bin/fake", [], [], extra=["--yolo"])
    with pytest.raises(ea.ExecRefused, match="operator_flags .none."):
        _with(adapter, operator_flags=[]).operator_tokens(["--model", "m"])


def test_child_env_disables_delegation_on_a_short_shell_timeout(adapter):
    """BR-10: `delegate: unsupported` puts ADLC_DISABLE_DELEGATE=1 in the child over any value
    the operator's environment holds; `supported` adds nothing of its own."""
    environ = {"HOME": "/h", "PATH": "/b", "ADLC_DISABLE_DELEGATE": "0", "OTHER": "x"}
    assert adapter.delegate_supported
    assert adapter.child_env(environ, "REQ-901", None, "/g", True)["ADLC_DISABLE_DELEGATE"] == "0"
    assert "ADLC_DISABLE_DELEGATE" not in adapter.child_env({"HOME": "/h"}, "REQ-901", None,
                                                            "/g", True)
    short = _with(adapter, shell_timeout_s={"value": 60, "verified": True,
                                            "delegate": "unsupported"})
    assert not short.delegate_supported
    for given in (environ, {"HOME": "/h"}):
        assert short.child_env(given, "REQ-901", None, "/g", True)["ADLC_DISABLE_DELEGATE"] == "1"
    fixture = _schema2("fake-exec-flags")
    assert "ADLC_DISABLE_DELEGATE" not in fixture.block["env_passthrough"]
    assert fixture.child_env(environ, "REQ-901", None, "/g", True) == {
        "HOME": "/h", "PATH": "/b", "ADLC_EXEC_RUN": "REQ-901", "ADLC_DISABLE_DELEGATE": "1"}


#: The engine's own modules. Each is followed through every tools/adlc module it imports.
EXEC_MODULES = ("exec_adapter", "sprint_exec", "exec_safety", "exec_gates", "exec_ledger",
                "exec_matcher", "exec_prompt")


def test_exec_modules_import_only_stdlib():
    """BR-13: argv construction, rendering and parsing are stdlib Python. Every module the
    engine imports, followed through tools/adlc, is the standard library or one of the
    toolkit's own, and none is PyYAML."""
    here = os.path.realpath(os.path.join(HERE, ".."))
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    seen, todo = set(), list(EXEC_MODULES)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        path = os.path.join(here, name + ".py")
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, (name, "relative import")
                names = [node.module.split(".")[0]]
            else:
                continue
            for imported in names:
                assert imported != "yaml", name
                if os.path.isfile(os.path.join(here, imported + ".py")):
                    todo.append(imported)
                    continue
                spec = importlib.util.find_spec(imported)
                assert spec is not None, (name, imported)
                origin = spec.origin or ""
                builtin = origin in ("built-in", "frozen") or imported in sys.builtin_module_names
                in_stdlib = os.path.realpath(origin).startswith(stdlib + os.sep)
                assert (builtin or in_stdlib) and "site-packages" not in origin, (
                    name, imported, origin)
    assert set(EXEC_MODULES) <= seen and "harness_adapter" in seen
