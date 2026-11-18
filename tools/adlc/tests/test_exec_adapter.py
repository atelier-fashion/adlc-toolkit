"""The exec block and exec_adapter (REQ-659 BR-3, BR-8, BR-21, BR-22)."""

import json
import os
import sys

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
    # The engine parses only what it has a parser for, and says so.
    stream = ea.load("fake-exec-file", TOOLKIT,
                     adapter_path=os.path.join(FIX, "fake-exec-file.yml"))
    with pytest.raises(ea.ExecRefused, match="jsonl-stream"):
        stream.parse_result('{"type": "thread.started", "thread_id": "t"}\n')


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
