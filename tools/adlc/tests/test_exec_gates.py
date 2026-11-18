"""The halt-time exec-path PR-diff gate (REQ-662 BR-17, AC-18, AC-20).

Every fixture is a real throwaway repository under ``tmp_path`` with a bare ``origin`` beside
it: no network and no forge. The PR's ``headRefOid`` is the oid the fixture pushed, and the
gate reads it through the same :class:`exec_safety.Toolbox` calls ``compute_plan`` makes.
"""

import inspect
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_gates as eg  # noqa: E402
import exec_safety as es  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
IB = "main"
#: A file-rendered adapter's exec block, as test data. No harness is named: the gate reads
#: only these two keys. The rule file is untracked at the base, rendered per run; one config
#: surface is a tracked file and one a tracked directory.
BLOCK = {"allow_render": "file", "rule_file": ".codex/rules/adlc-exec.rules",
         "config_surfaces": [".codex/config.toml", ".codex/prompts/"]}
RULES = ".codex/rules/adlc-exec.rules"
CONFIG = ".codex/config.toml"
BASE_FILES = {"a.txt": "a\n", "docs/guide.md": "guide\n", CONFIG: 'model = "fixture"\n',
              ".codex/prompts/review.md": "review\n"}
RENDERED = "# rendered by the engine for one run\n"
IDENTITY = {"GIT_AUTHOR_NAME": "adlc-test", "GIT_AUTHOR_EMAIL": "adlc-test@example.invalid",
            "GIT_COMMITTER_NAME": "adlc-test", "GIT_COMMITTER_EMAIL": "adlc-test@example.invalid"}


def git(cwd, *args, stdin=None, index=None):
    """The fixture's own git, standing in for the model: never the gate's."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env.update(IDENTITY, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if index:
        env["GIT_INDEX_FILE"] = index
    res = subprocess.run(["git", "-C", str(cwd)] + list(args), input=stdin, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    assert res.returncode == 0, (args, res.stderr)
    return res.stdout.strip()


def write(root, rel, text):
    path = os.path.join(str(root), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Repo(object):
    """A primary checkout with an ``origin``, and a Toolbox registered on it at 'launch'."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        bare = tmp_path / "origin.git"
        subprocess.check_call(["git", "init", "-q", "--bare", "-b", IB, str(bare)])
        self.work = tmp_path / "work"
        subprocess.check_call(["git", "init", "-q", "-b", IB, str(self.work)])
        for rel, text in BASE_FILES.items():
            write(self.work, rel, text)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-qm", "base")
        git(self.work, "remote", "add", "origin", str(bare))
        git(self.work, "push", "-q", "origin", IB)
        self.base = git(self.work, "rev-parse", "HEAD")
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        self.box = es.Toolbox(str(run_dir), TOOLKIT,
                              {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"]})
        self.box.prepare()
        self.box.register_tree(str(self.work))
        self.targets = eg.exec_path_targets(BLOCK)

    # -- building a PR head ------------------------------------------------------------
    def plumb(self, name, files=None, links=None, remove=()):
        """A commit on the base built in a private index, so a case variant is recorded as
        spelled whatever the filesystem folds."""
        index = str(self.tmp / ("index-" + name))
        git(self.work, "read-tree", self.base, index=index)
        for mode, entries in (("100644", files or {}), ("120000", links or {})):
            for rel, text in entries.items():
                blob = git(self.work, "hash-object", "-w", "--stdin", stdin=text)
                git(self.work, "update-index", "--add", "--cacheinfo",
                    "%s,%s,%s" % (mode, blob, rel), index=index)
        for rel in remove:
            git(self.work, "update-index", "--force-remove", rel, index=index)
        tree = git(self.work, "write-tree", index=index)
        return git(self.work, "commit-tree", tree, "-p", self.base, "-m", name)

    def checkout(self, name):
        git(self.work, "checkout", "-q", "-B", "fx-" + name, self.base)

    def commit(self, name):
        git(self.work, "commit", "-qm", name)
        return git(self.work, "rev-parse", "HEAD")

    def push(self, name, oid):
        branch = "feat/REQ-900-%s" % name
        git(self.work, "push", "-q", "origin", "%s:refs/heads/%s" % (oid, branch))
        return branch

    # -- the gate, as compute_plan reaches it -------------------------------------------
    def gate(self, branch):
        eg.fetch_integration(self.box, str(self.work), IB)
        oid = eg.fetch_branch(self.box, str(self.work), branch)
        changed = eg.changed_paths(self.box, str(self.work), IB, oid)
        return oid, changed, eg.exec_path_touched(self.box, str(self.work), IB, oid,
                                                  self.targets)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


# -- one fixture per way a PR can touch an exec path ---------------------------------------
def _add(repo):
    return repo.plumb("add", files={RULES: RENDERED}), [["A", RULES]]


def _modify(repo):
    return repo.plumb("modify", files={CONFIG: 'model = "other"\n'}), [["M", CONFIG]]


def _delete(repo):
    return repo.plumb("delete", remove=[CONFIG]), [["D", CONFIG]]


def _rename_into(repo):
    repo.checkout("rename-into")
    git(repo.work, "mv", "docs/guide.md", ".codex/prompts/guide.md")
    return repo.commit("rename into"), [["A", ".codex/prompts/guide.md"]]


def _rename_out_of(repo):
    repo.checkout("rename-out-of")
    git(repo.work, "mv", ".codex/prompts/review.md", "docs/review.md")
    return repo.commit("rename out of"), [["D", ".codex/prompts/review.md"]]


def _case_variant(repo):
    # On a case-insensitive checkout this file is the config surface.
    return repo.plumb("case-variant", files={".CODEX/Config.TOML": RENDERED}), \
        [["A", ".CODEX/Config.TOML"]]


def _directory_prefix(repo):
    rel = ".codex/prompts/nested/extra.md"
    return repo.plumb("directory-prefix", files={rel: "extra\n"}), [["A", rel]]


def _parent_replaced(repo):
    # A symlink where the rule file's directory belongs redirects the next render.
    return repo.plumb("parent-replaced", links={".codex/rules": "/elsewhere"}), \
        [["A", ".codex/rules"]]


def _hide_tracked(repo, name):
    """The engine's best-effort hiding of a tracked surface: overwritten, skip-worktree."""
    repo.checkout(name)
    write(repo.work, CONFIG, RENDERED)
    git(repo.work, "update-index", "--skip-worktree", CONFIG)
    assert git(repo.work, "status", "--porcelain") == ""


def _no_skip_worktree(repo):
    _hide_tracked(repo, "no-skip-worktree")
    git(repo.work, "update-index", "--no-skip-worktree", CONFIG)
    git(repo.work, "add", CONFIG)
    return repo.commit("force-add through --no-skip-worktree"), [["M", CONFIG]]


def _add_sparse(repo):
    _hide_tracked(repo, "add-sparse")
    # On git 2.54 a bare `git add --sparse` trusts the skip-worktree entry and stages
    # nothing; with --renormalize it reads the file and stages it.
    git(repo.work, "add", "--sparse", "--renormalize", CONFIG)
    return repo.commit("force-add through add --sparse"), [["M", CONFIG]]


def _force_added_excluded(repo):
    """The untracked rule file, hidden by an excludes file, then force-added."""
    repo.checkout("force-added-excluded")
    write(repo.work, RULES, RENDERED)
    excludes = str(repo.tmp / "excludes")
    write(repo.tmp, "excludes", "/" + RULES + "\n")
    hidden = ("-c", "core.excludesFile=" + excludes)
    assert git(repo.work, *(hidden + ("status", "--porcelain", "-uall"))) == ""
    git(repo.work, *(hidden + ("add", "-f", RULES)))
    return repo.commit("force-add an excluded path"), [["A", RULES]]


FORCE_ADDED = {"no-skip-worktree": CONFIG, "add-sparse": CONFIG, "force-added-excluded": RULES}
FIXTURES = {"add": _add, "modify": _modify, "delete": _delete, "rename-into": _rename_into,
            "rename-out-of": _rename_out_of, "case-variant": _case_variant,
            "directory-prefix": _directory_prefix, "parent-replaced": _parent_replaced,
            "no-skip-worktree": _no_skip_worktree, "add-sparse": _add_sparse,
            "force-added-excluded": _force_added_excluded}


def _benign(repo):
    """The must-not-refuse PR, committed from a working copy that holds the engine's own
    renders, hidden: the tracked surface overwritten and skip-worktree, the rule file
    untracked. Near-misses of every target are committed alongside."""
    _hide_tracked(repo, "benign")
    write(repo.work, RULES, RENDERED)
    for rel in ("a.txt", ".codex-notes.md", ".codex/promptsx/a.md",
                ".codex/rules/adlc-exec.rules.bak", "docs/.codex/config.toml"):
        write(repo.work, rel, "benign\n")
        git(repo.work, "add", rel)
    return repo.commit("benign"), []


def _plan(hits, changed):
    """What the wiring stores: the hit paths, beside an acknowledged gate-change line."""
    paths = [p for _status, p in changed]
    return {eg.EXEC_PATH_KEY: sorted({p for _status, p in hits}),
            "changesGate": eg.gate_lines(paths, [], BLOCK["config_surfaces"]),
            "ackGateChange": True}


@pytest.mark.parametrize("name", sorted(FIXTURES) + ["benign"])
def test_exec_path_gate_fixtures(repo, name):
    """BR-17, AC-20: each way a PR can touch an exec-rendered path or a config surface
    populates the list and makes approve's check refuse, acknowledged or not; the benign PR
    leaves the list empty and the check passes."""
    builder = FIXTURES.get(name, _benign)
    oid, expected = builder(repo)
    branch = repo.push(name, oid)
    got_oid, changed, hits = repo.gate(branch)
    assert got_oid == oid
    assert hits == expected, (name, changed)
    if name in FORCE_ADDED:
        # The hidden content really is in the PR head: the fixture is not vacuous.
        rel = FORCE_ADDED[name]
        assert eg.show_blob(repo.box, str(repo.work), oid, rel) == RENDERED
    plan = _plan(hits, changed)
    if not expected:
        assert plan[eg.EXEC_PATH_KEY] == [] and plan["changesGate"] == []
        assert eg.check_exec_path(plan) is None
        return
    assert plan["ackGateChange"] is True
    with pytest.raises(eg.ExecPathTouched) as caught:
        eg.check_exec_path(plan)
    assert caught.value.paths == [p for _s, p in expected]
    for _status, path in expected:
        assert re.search(re.escape(path), str(caught.value))
    assert "--ack-gate-change does not cover it" in str(caught.value)


def test_the_check_takes_no_acknowledgement():
    """--ack-gate-change has no way in: the check's one argument is the plan, and its error
    is no GateError a caller could treat as 'could not be evaluated'."""
    assert list(inspect.signature(eg.check_exec_path).parameters) == ["plan"]
    assert not issubclass(eg.ExecPathTouched, eg.GateError)
    plan = {eg.EXEC_PATH_KEY: [CONFIG], "changesGate": [], "ackGateChange": True}
    with pytest.raises(eg.ExecPathTouched, match=re.escape(CONFIG)):
        eg.check_exec_path(plan)


@pytest.mark.parametrize("plan", [{}, {eg.EXEC_PATH_KEY: None}, {eg.EXEC_PATH_KEY: CONFIG},
                                  {eg.EXEC_PATH_KEY: [1]}, None])
def test_a_plan_without_the_gate_result_is_refused(plan):
    """Fail closed: a plan the gate never wrote is not a clean one."""
    with pytest.raises(eg.ExecPathTouched, match="no exec-path gate result"):
        eg.check_exec_path(plan)


def test_surface_change_is_on_the_changes_the_gate_list(repo):
    """AC-18: a PR touching a config surface, by any spelling, is named on REQ-659's
    'changes the gate' list; a PR touching none adds no line."""
    oid = repo.plumb("surface", files={CONFIG: 'model = "other"\n',
                                       ".Codex/Prompts/new.md": "new\n"})
    _oid, changed, _hits = repo.gate(repo.push("surface", oid))
    lines = eg.gate_lines([p for _s, p in changed], [], BLOCK["config_surfaces"])
    assert lines == ["changes the gate: touches a config surface: .Codex/Prompts/new.md, %s"
                     % CONFIG]
    benign = repo.plumb("not-a-surface", files={"a.txt": "b\n", ".codex/promptsx/a.md": "x\n"})
    _oid, changed, _hits = repo.gate(repo.push("not-a-surface", benign))
    assert eg.gate_lines([p for _s, p in changed], [], BLOCK["config_surfaces"]) == []
    # REQ-659's own lines are unchanged, and the two-argument call still reads as before.
    assert eg.gate_lines([".adlc/partials/forge.sh"], []) == [
        "changes the gate: touches .adlc/partials/forge.sh"]


def test_targets_come_from_the_block_and_the_run_record():
    """LESSON-718: every target is an argument, from the adapter and the run record. A block
    with no rule file and no surface has none, and a target the gate cannot place refuses."""
    assert eg.exec_path_targets(BLOCK, [".codex/prompts", "AGENTS.override.md"]) == [
        RULES, CONFIG, ".codex/prompts", "AGENTS.override.md"]
    assert eg.exec_path_targets({"allow_render": "flags", "config_surfaces": []}) == []
    assert eg.exec_path_hits([["A", RULES], ["M", CONFIG]], []) == []
    for bad in ("/etc/x", "../x", "a/../../x", "~/x", "$HOME/x", ".", "./", "", None):
        with pytest.raises(eg.GateError):
            eg.exec_path_targets({"config_surfaces": [bad]})
    with pytest.raises(eg.GateError):
        eg.exec_path_targets({"config_surfaces": ".codex"})
    with pytest.raises(eg.GateError):
        eg.exec_path_targets({"rule_file": ""})


def test_the_gate_runs_git_through_the_toolbox(repo):
    """REQ-659 BR-23: the gate's diff runs with hooks and fsmonitor disabled, as every other
    orchestrator git call does."""
    repo.gate(repo.push("logged", repo.plumb("logged", files={RULES: RENDERED})))
    with open(repo.box.log_path, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    diffs = [r for r in records if r["kind"] == "git" and "--no-renames" in r["argv"]]
    assert diffs
    for record in diffs:
        pairs = {record["env"]["GIT_CONFIG_KEY_%d" % i]: record["env"]["GIT_CONFIG_VALUE_%d" % i]
                 for i in range(int(record["env"]["GIT_CONFIG_COUNT"]))}
        assert pairs["core.hooksPath"] == os.path.join(repo.box.run_dir, "hooks-empty")
        assert pairs["core.fsmonitor"] == "false"
