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
    bad.write_text(text.replace("  working_copy: worktree\n",
                                "  working_copy: {strategy: clone}\n"))
    assert ea.ExecAdapter(ha.load_adapter(str(bad), toolkit=TOOLKIT), TOOLKIT).strategy == "clone"
    bad.write_text(text.replace("  working_copy: worktree\n", "  working_copy: floppy\n"))
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
    assert "Bash(git -C * push --force:*)" in deny
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
