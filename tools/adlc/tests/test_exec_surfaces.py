"""Config surfaces, rule files and the user policy folder (REQ-662 ADR-4: BR-4, BR-15, BR-16)."""

import hashlib
import json
import os
import re
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_helpers as eh  # noqa: E402
import exec_surfaces as esf  # noqa: E402
import harness_adapter as ha  # noqa: E402
import sprint_exec as se  # noqa: E402

TOOLKIT = eh.TOOLKIT
FIX = os.path.join(HERE, "fixtures", "harness")
BRANCH = "feat/REQ-901-thing"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _adapter(tmp_path, **kw):
    """:func:`exec_helpers.file_adapter` as an ``ExecAdapter`` over this toolkit."""
    path = eh.file_adapter(tmp_path / "adapter", eh.probe_result(), **kw)
    return ea.ExecAdapter(ha.load_adapter(path, toolkit=TOOLKIT), TOOLKIT)


def _plan(adapter):
    files = adapter.rule_files(BRANCH, (), eh.probe_result())
    return esf.working_copy_render(adapter, files, TOOLKIT)


def _files_under(root, rel):
    return {path for path, _what in esf._entries(str(root), rel)}


def _decisions(text):
    return [m.group(1) for m in re.finditer(r'^prefix_rule\(pattern=\[.*\], decision="([a-z]+)"\)$',
                                            text, re.M)]


# ---- BR-15: rendered whole or absent, strays deleted ------------------------------------------
def test_surfaces_are_rendered_or_absent_and_strays_deleted(tmp_path):
    """BR-15, AC-18: in a directory surface the rule file and the working-copy config are
    rendered whole, the project's allowlist and the hook file are made absent, and every other
    entry (a file, a nested one, a symlink, a FIFO) is deleted, the link's target untouched.
    The manifest matches after the render. A second render over the result changes nothing
    and finds every checksum matched (the must-not-fire case); nothing outside a surface is
    touched. A file surface is rendered or absent and leaves its siblings alone."""
    adapter = _adapter(tmp_path)
    plan = _plan(adapter)
    assert plan[eh.FILE_PROJECT_RULES] is None and plan[eh.FILE_HOOKS] is None
    assert plan[eh.FILE_RULE].startswith("# Rendered by the exec engine")
    wc = tmp_path / "wc"
    surf = wc / ".fake-exec-file"
    (surf / "rules").mkdir(parents=True)
    (wc / "README.md").write_text("mine\n")
    outside = tmp_path / "outside.rules"
    outside.write_text("keep\n")
    project_rules = 'prefix_rule(pattern=["git"], decision="allow")\n'
    (surf / "rules" / "default.rules").write_text(project_rules)
    (surf / "hooks.json").write_text("{}\n")
    (surf / "config.toml").write_text('model = "x"\n')
    (surf / "notes" / "deep").mkdir(parents=True)
    (surf / "notes" / "deep" / "x.md").write_text("x\n")
    os.symlink(str(outside), str(surf / "rules" / "link.rules"))
    os.mkfifo(str(surf / "pipe"))
    manifest, changes = esf.render(str(wc), plan, adapter.block)
    assert manifest == {
        "files": {eh.FILE_CONFIG: _sha(plan[eh.FILE_CONFIG]),
                  eh.FILE_RULE: _sha(plan[eh.FILE_RULE])},
        "absent": sorted([eh.FILE_HOOKS, eh.FILE_PROJECT_RULES]),
        "directories": [".fake-exec-file"]}
    for rel, text in plan.items():
        if text is None:
            assert not os.path.lexists(str(wc / rel))
        else:
            assert (wc / rel).read_text() == text
    assert _files_under(wc, ".fake-exec-file") == set(manifest["files"])
    assert esf.verify(str(wc), manifest) == []
    assert outside.read_text() == "keep\n" and (wc / "README.md").read_text() == "mine\n"
    assert sorted(changes, key=lambda c: c.path) == sorted([
        esf.Change(eh.FILE_CONFIG, _sha(plan[eh.FILE_CONFIG]), _sha('model = "x"\n')),
        esf.Change(eh.FILE_RULE, _sha(plan[eh.FILE_RULE]), None),
        esf.Change(eh.FILE_HOOKS, None, _sha("{}\n")),
        esf.Change(eh.FILE_PROJECT_RULES, None, _sha(project_rules)),
        esf.Change(".fake-exec-file/notes/deep/x.md", None, _sha("x\n")),
        esf.Change(".fake-exec-file/pipe", None, esf.SPECIAL),
        esf.Change(".fake-exec-file/rules/link.rules", None, esf.SYMLINK)], key=lambda c: c.path)
    # Untouched: the next render rewrites the same bytes and finds each checksum matched.
    again, changes = esf.render(str(wc), plan, adapter.block)
    assert again == manifest
    assert [(c.path, c.found == c.expected) for c in changes] == [
        (eh.FILE_CONFIG, True), (eh.FILE_RULE, True)]
    # The paths the PR-diff gate and the hiding cover (BR-17, TASK-264).
    assert esf.rendered_paths(manifest) == (
        sorted([eh.FILE_CONFIG, eh.FILE_RULE, eh.FILE_HOOKS, eh.FILE_PROJECT_RULES]),
        [".fake-exec-file"])
    # A file surface: rendered (the hook file, under `hooks`) or absent (the MCP file); the
    # sibling that is no surface stays.
    flags = ha.load_adapter(os.path.join(FIX, "fake-exec-flags.yml"), toolkit=TOOLKIT)
    flat = esf.working_copy_render(flags, None, TOOLKIT)
    assert list(flat) == [".fake-exec-flags/hooks.json"] and flat[".fake-exec-flags/hooks.json"]
    other = tmp_path / "other"
    (other / ".fake-exec-flags").mkdir(parents=True)
    (other / ".fake-exec-flags" / "mcp.json").write_text('{"autoApprove": true}\n')
    (other / ".fake-exec-flags" / "permissions.json").write_text("{}\n")
    flat_manifest, _changes = esf.render(str(other), flat, flags["exec"])
    assert flat_manifest["absent"] == [".fake-exec-flags/mcp.json"]
    assert flat_manifest["directories"] == []
    assert not os.path.lexists(str(other / ".fake-exec-flags" / "mcp.json"))
    assert (other / ".fake-exec-flags" / "hooks.json").read_text() == flat[
        ".fake-exec-flags/hooks.json"]
    assert (other / ".fake-exec-flags" / "permissions.json").read_text() == "{}\n"
    assert esf.verify(str(other), flat_manifest) == []
    # A stray reappearing is a change the verify reports, once.
    (surf / "hooks.json").write_text("{}\n")
    (surf / "zz.rules").write_text("x\n")
    assert esf.verify(str(wc), manifest) == [
        esf.Change(eh.FILE_HOOKS, None, _sha("{}\n")),
        esf.Change(".fake-exec-file/zz.rules", None, _sha("x\n"))]


def test_exec_render_of_the_working_copy_config_is_the_project_render():
    """AC-22, BR-15: on the Codex adapter's own paths, the exec render of its working-copy
    config is byte-equal to the committed project render, and so is the hook file under
    `context_delivery: hooks`; under `prompt` the hook file is absent, and the project's
    allowlist file in the same directory is absent under both, because the exec rule file is
    the whole policy there."""
    codex = ha.load_adapter(os.path.join(TOOLKIT, "harness", "codex.yml"), toolkit=TOOLKIT)
    fixture = ha.load_adapter(eh.CODEX_SHAPED_FIXTURE, toolkit=TOOLKIT)["exec"]
    paths = codex["paths"]
    surface = os.path.dirname(paths["config"]["project"]) + "/"
    rule = os.path.join(os.path.dirname(paths["permissions"]["project"]), "adlc-exec.rules")
    files = type("Files", (), {"rule_file": "# the run's rules\n"})()
    golden = os.path.join(TOOLKIT, "harness", "codex", "rendered")
    for delivery in ("prompt", "hooks"):
        data = dict(codex, exec=dict(fixture, config_surfaces=[surface], rule_file=rule,
                                     context_delivery=delivery))
        plan = esf.working_copy_render(data, files, TOOLKIT)
        with open(os.path.join(golden, os.path.basename(paths["config"]["project"])),
                  encoding="utf-8") as fh:
            assert plan[paths["config"]["project"]] == fh.read()
        with open(os.path.join(golden, os.path.basename(paths["hooks"]["project"])),
                  encoding="utf-8") as fh:
            hooks = fh.read()
        assert plan[paths["hooks"]["project"]] == (None if delivery == "prompt" else hooks)
        assert plan[paths["permissions"]["project"]] is None
        assert plan[rule] == "# the run's rules\n"


# ---- AC-18: the guarded write ----------------------------------------------------------------
def test_guarded_write_refuses_links_and_fifos(tmp_path):
    """AC-18, BR-15: a plain directory and a plain file are written, and written again (the
    must-not-refuse case). A symlink, a hardlink or a FIFO at the file, a symlink, a FIFO or a
    file at a directory component, and a path that resolves outside the root are each
    refused, naming the component, and nothing outside the root changes. Nothing is followed
    or opened to tell what is there, and a render that meets one changes nothing."""
    rel = ".fake-exec-file/rules/adlc-exec.rules"
    plain = tmp_path / "plain"
    plain.mkdir()
    assert esf.guarded_write(str(plain), rel, "one\n") == _sha("one\n")
    assert esf.guarded_write(str(plain), rel, "two\n") == _sha("two\n")
    st = os.lstat(str(plain / rel))
    assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and (plain / rel).read_text() == "two\n"
    assert sorted(os.listdir(str(plain / ".fake-exec-file" / "rules"))) == ["adlc-exec.rules"]
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target"
    target.write_text("theirs\n")

    def root(name):
        path = tmp_path / name
        (path / ".fake-exec-file" / "rules").mkdir(parents=True)
        return path

    final = {}
    final["symlink"] = root("final-link")
    os.symlink(str(target), str(final["symlink"] / rel))
    final["hardlink"] = root("final-hardlink")
    os.link(str(target), str(final["hardlink"] / rel))
    final["FIFO"] = root("final-fifo")
    os.mkfifo(str(final["FIFO"] / rel))
    for what, path in final.items():
        with pytest.raises(esf.SurfaceRefused, match=r"%s .*(%s)" % (re.escape(rel), {
                "symlink": "is a symlink", "hardlink": "is a hardlink",
                "FIFO": "FIFO, socket or device"}[what])):
            esf.guarded_write(str(path), rel, "x\n")
        assert esf.found(str(path), rel) == {"symlink": esf.SYMLINK, "hardlink": esf.HARDLINK,
                                             "FIFO": esf.SPECIAL}[what]
    middle = {}
    middle["symlink"] = tmp_path / "mid-link"
    middle["symlink"].mkdir()
    os.symlink(str(outside), str(middle["symlink"] / ".fake-exec-file"))
    middle["FIFO"] = tmp_path / "mid-fifo"
    (middle["FIFO"] / ".fake-exec-file").mkdir(parents=True)
    os.mkfifo(str(middle["FIFO"] / ".fake-exec-file" / "rules"))
    middle["file"] = tmp_path / "mid-file"
    middle["file"].mkdir()
    (middle["file"] / ".fake-exec-file").write_text("a file\n")
    for what, path in middle.items():
        with pytest.raises(esf.SurfaceRefused, match=r"\.fake-exec-file(/rules)? in .* (%s)"
                           % {"symlink": "is a symlink", "FIFO": "FIFO, socket or device",
                              "file": "is not a directory but a file"}[what]):
            esf.guarded_write(str(path), rel, "x\n")
    for bad in ("../escaped.rules", "/abs/escaped.rules", ".fake-exec-file/../../escaped.rules",
                ".fake-exec-file//x", "./x"):
        with pytest.raises(esf.SurfaceRefused, match="relative path|`.` or `..`"):
            esf.guarded_write(str(plain), bad, "x\n")
    # The resolved path is compared case-folded, as a case-insensitive filesystem resolves it.
    assert esf.within(str(plain), str(plain / "a"))
    assert esf.within(str(plain), str(plain).upper() + "/A")
    assert not esf.within(str(plain), str(outside / "a"))
    assert not esf.within(str(plain), str(plain))
    assert sorted(os.listdir(str(outside))) == ["target"] and target.read_text() == "theirs\n"
    assert os.lstat(str(target)).st_nlink == 2      # the hardlink was refused, not replaced
    # A removal unlinks a link and never follows it.
    assert esf.guarded_remove(str(final["symlink"]), rel)
    assert target.read_text() == "theirs\n"
    # A render that meets a refused component changes nothing, a stray included.
    adapter = _adapter(tmp_path)
    plan = _plan(adapter)
    wc = tmp_path / "wc"
    wc.mkdir()
    os.symlink(str(outside), str(wc / ".fake-exec-file"))
    with pytest.raises(esf.SurfaceRefused, match="is a symlink"):
        esf.render(str(wc), plan, adapter.block)
    assert sorted(os.listdir(str(outside))) == ["target"]


# ---- BR-16: bypass_config_keys -----------------------------------------------------------------
def test_bypass_config_keys_refuse(tmp_path, monkeypatch):
    """BR-16, AC-19: a user config and a working-copy config each carrying a
    `bypass_config_keys` key at a value the toolkit's render does not set refuse the run, at
    launch and at resume; a config that cannot be read with certainty refuses it; a clean pair,
    holding the toolkit's own values, other keys and a trust table, does not (the
    must-not-refuse case). TOML is read with toml_merge.scan, JSON with duplicates refused."""
    adapter = _adapter(tmp_path)
    plan = _plan(adapter)
    home, wc = tmp_path / "home", tmp_path / "wc"
    env = {"HOME": str(home)}
    user, local = home / eh.FILE_USER_CONFIG, wc / eh.FILE_CONFIG
    user.parent.mkdir(parents=True)
    local.parent.mkdir(parents=True)
    clean_user = ('approval_policy = "on-request"\nmodel = "fake-mid-1"\n\n'
                  '[projects."/elsewhere"]\ntrust_level = "trusted"\n')
    user.write_text(clean_user)
    local.write_text(plan[eh.FILE_CONFIG])
    assert esf.bypass_scan(adapter, [str(wc)], env) == []
    user.write_text('approval_policy = "never"\n')
    assert esf.bypass_scan(adapter, [str(wc)], env) == [
        esf.Hit(str(user), "approval_policy", '"never"')]
    user.write_text(clean_user)
    local.write_text('sandbox_mode = "danger-full-access"\n')
    assert esf.bypass_scan(adapter, [str(wc)], env) == [
        esf.Hit(str(local), "sandbox_mode", '"danger-full-access"')]
    local.write_text(plan[eh.FILE_CONFIG])
    for bad in ("[[profiles]]\nx = 1\n", 'approval_policy = "never"', '"approval_policy" = "x"\n',
                '[profiles.p]\napproval_policy = "never"\n', "approval_policy =\n"):
        user.write_text(bad)
        with pytest.raises(esf.SurfaceRefused, match="cannot be read with certainty"):
            esf.bypass_scan(adapter, [str(wc)], env)
    user.write_text(clean_user)
    os.unlink(str(local))
    os.symlink(str(user), str(local))
    with pytest.raises(esf.SurfaceRefused, match="is a symlink"):
        esf.bypass_scan(adapter, [str(wc)], env)
    os.unlink(str(local))
    assert esf.bypass_scan(adapter, [str(wc)], env) == []       # absent is clean
    # JSON configs, on the flags fixture: a key's presence is a hit, a duplicate refuses.
    flags = ha.load_adapter(os.path.join(FIX, "fake-exec-flags.yml"), toolkit=TOOLKIT)
    (home / ".fake-exec-flags").mkdir()
    (home / ".fake-exec-flags" / "config.json").write_text('{"allowAllTools": false}\n')
    (wc / ".fake-exec-flags").mkdir()
    (wc / ".fake-exec-flags" / "mcp.json").write_text('{"servers": {}}\n')
    assert [(h.key, h.value) for h in esf.bypass_scan(flags, [str(wc)], env)] == [
        ("allowAllTools", "false")]
    (home / ".fake-exec-flags" / "config.json").write_text('{"a": 1, "a": 2}\n')
    with pytest.raises(esf.SurfaceRefused, match="duplicate key"):
        esf.bypass_scan(flags, [str(wc)], env)

    # Through the engine. The launch: a user config hit, and an unparsable one, refuse the
    # pre-flight; a working-copy config hit the project commits refuses the launch, naming it.
    box = eh.file_sandbox(tmp_path / "launch", monkeypatch)
    buser = box.home / eh.FILE_USER_CONFIG
    buser.parent.mkdir(parents=True)
    for text, why in (('approval_policy = "never"\n', "sets approval_policy"),
                      ("[[x]]\n", "cannot be read with certainty")):
        buser.write_text(text)
        with pytest.raises(se.Refused, match=why):
            box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    buser.write_text(clean_user)
    eh.commit_on_main(box, {eh.FILE_CONFIG: 'sandbox_mode = "danger-full-access"\n'})
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "failed" and not box.launches()
    assert "sets sandbox_mode" in json.dumps(run.read_primary_state()["notes"])
    [refused] = eh.events(box, run, "adapter_refused")
    assert refused["where"] == "launch" and refused["hits"] == [
        {"path": os.path.join(run.wc, eh.FILE_CONFIG), "key": "sandbox_mode",
         "value": '"danger-full-access"'}]
    assert buser.read_text() == clean_user
    # The resume: a clean pair launches; a user config hit planted before the approval
    # refuses the close-out's resume, and nothing resumes.
    box = eh.file_sandbox(tmp_path / "resume", monkeypatch)
    buser = box.home / eh.FILE_USER_CONFIG
    buser.parent.mkdir(parents=True)
    buser.write_text(clean_user)
    eh.commit_on_main(box, {eh.FILE_CONFIG: plan[eh.FILE_CONFIG]})
    box.req(add=["src"], closeout={"add": [".adlc"]})
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval" and len(box.launches()) == 1
    assert not eh.events(box, run, "adapter_refused")
    buser.write_text(clean_user + '\nsandbox_mode = "danger-full-access"\n')
    with pytest.raises(esf.SurfaceRefused, match="cannot be read"):
        esf.bypass_scan(adapter, [], {"HOME": str(box.home)})    # a top-level key after a table
    buser.write_text('sandbox_mode = "danger-full-access"\n' + clean_user)
    assert box.approve(orch) == "approved"
    close = run.read_primary_state()["closeOut"]
    assert close["status"] == "failed" and "sets sandbox_mode" in close["reason"]
    assert len(box.launches()) == 1
    assert [e["where"] for e in eh.events(box, run, "adapter_refused")] == ["resume"]


# ---- AC-14: the user policy folder -------------------------------------------------------------
def test_user_policy_folder_manifest(tmp_path, monkeypatch):
    """AC-14, BR-4: under a sandbox HOME holding an operator-authored rules file, the
    pre-flight writes only the toolkit's policy file, which holds the deny tier and no allow,
    and leaves the operator's file byte-identical. A missing or drifted toolkit file, or a
    stray in the folder, refuses the pre-flight, the launch and the resume, naming the file;
    an untouched folder passes each (the must-not-refuse case)."""
    box = eh.file_sandbox(tmp_path, monkeypatch)
    folder = box.home / eh.FILE_POLICY_DIR
    folder.mkdir(parents=True)
    operator = folder / "default.rules"
    mine = '# mine\nprefix_rule(pattern=["ls"], decision="allow")\n'
    operator.write_text(mine)
    policy = box.home / eh.FILE_POLICY
    batch = box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    text = policy.read_text()
    assert text == eh.fresh_files(box).user_policy_file == batch.exec_files.user_policy_file
    assert _decisions(text) and set(_decisions(text)) == {"forbidden"}
    assert operator.read_text() == mine
    assert sorted(os.listdir(str(folder))) == ["adlc-exec.rules", "default.rules"]
    assert sorted(os.listdir(str(box.home / ".fake-exec-file"))) == ["rules"]
    inode = os.stat(str(policy)).st_ino
    box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    assert os.stat(str(policy)).st_ino == inode       # untouched: nothing rewritten
    # The operator's own file is theirs between runs: an edit is recorded, not refused.
    operator.write_text(mine + "# more\n")
    box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    adapter = ea.load(box.harness, box.toolkit)

    def refused(match):
        with pytest.raises(se.Refused, match=match):
            box.orch().preflight(box.reqs, harness=box.harness, shared=True)

    policy.write_text(text + 'prefix_rule(pattern=["git", "push"], decision="allow")\n')
    refused(r"%s: expected sha256 %s, found sha256" % (re.escape(str(policy)), _sha(text)[:12]))
    policy.write_text(text)
    policy.unlink()
    refused(r"%s: expected sha256 %s, found absent" % (re.escape(str(policy)), _sha(text)[:12]))
    esf.install_policy_file(adapter, box.environ, text)
    stray = folder / "zz-extra.rules"
    stray.write_text('prefix_rule(pattern=["rm"], decision="allow")\n')
    refused(r"%s: expected absent, found sha256" % re.escape(str(stray)))
    stray.unlink()
    # Before the launch: the folder changes between the pre-flight and the launch.
    orch = box.orch()
    batch = orch.preflight(box.reqs, harness=box.harness, shared=True)
    operator.write_text(mine)
    orch.launch_batch(box.reqs, batch)
    run = orch.runs["REQ-901"]
    assert run.status == "failed" and not box.launches()
    assert str(operator) in json.dumps(run.read_primary_state()["notes"])
    # Before the resume: an untouched run launches and halts; a stray before the approval
    # refuses the resume, naming it.
    box2 = eh.file_sandbox(tmp_path / "second", monkeypatch)
    folder2 = box2.home / eh.FILE_POLICY_DIR
    folder2.mkdir(parents=True)
    (folder2 / "default.rules").write_text(mine)
    box2.req(add=["src"], closeout={"add": [".adlc"]})
    orch = box2.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "awaiting_approval" and len(box2.launches()) == 1
    assert not eh.events(box2, run, "config_surface_violation")
    stray2 = folder2 / "zz-extra.rules"
    stray2.write_text("x\n")
    assert box2.approve(orch) == "approved"
    close = run.read_primary_state()["closeOut"]
    assert close["status"] == "failed" and str(stray2) in close["reason"]
    assert "the resume is refused" in close["reason"] and len(box2.launches()) == 1


# ---- AC-22: the policy file is whole and atomic ------------------------------------------------
WRITER = """
import os, sys
sys.path.insert(0, %(tools)r)
import exec_surfaces as esf
data = {"name": "fake-exec-file", "exec": {"user_policy_file": "$HOME/%(rel)s"}}
text = sys.argv[1] * 20000
for _ in range(15):
    esf.install_policy_file(data, {"HOME": %(home)r, "XDG_STATE_HOME": %(state)r}, text)
"""


def test_user_policy_file_is_whole_file_and_atomic(tmp_path, monkeypatch):
    """AC-22, BR-4: the policy file is written whole (a longer file it replaces leaves no
    tail) and atomically: concurrent writers leave one intact file, the record of the last
    one to write it, and no temp file or lock behind. A file the fake harness writes into the
    policy folder mid-run is a config_surface_violation at exit and at the halt, and is caught
    by the folder's manifest at the next launch, which it refuses."""
    home, state = tmp_path / "home", tmp_path / "state"
    env = {"HOME": str(home), "XDG_STATE_HOME": str(state)}
    data = {"name": "fake-exec-file", "exec": {"user_policy_file": "$HOME/" + eh.FILE_POLICY}}
    path = home / eh.FILE_POLICY
    path.parent.mkdir(parents=True)
    path.write_text("x" * 100000)
    record = esf.install_policy_file(data, env, "short\n")
    assert path.read_text() == "short\n" and record["sha256"] == _sha("short\n")
    script = WRITER % {"tools": os.path.join(HERE, ".."), "rel": eh.FILE_POLICY,
                       "home": str(home), "state": str(state)}
    letters = "abcdef"
    procs = [subprocess.Popen([sys.executable, "-c", script, ch]) for ch in letters]
    assert [p.wait(timeout=120) for p in procs] == [0] * len(letters)
    text = path.read_text()
    assert text in {ch * 20000 for ch in letters}
    assert sorted(os.listdir(str(path.parent))) == ["adlc-exec.rules"]
    record = esf.read_record(data, env)
    assert record["sha256"] == _sha(text) and record["files"] == {"adlc-exec.rules": _sha(text)}
    assert not [n for n in os.listdir(os.path.dirname(record["record"])) if n.endswith(".lock.d")]
    assert esf.policy_problems(record) == []

    # The fake writes into the policy folder mid-run.
    box = eh.file_sandbox(tmp_path / "run", monkeypatch)
    planted = str(box.home / eh.FILE_POLICY_DIR / "fake.rules")
    rule = 'prefix_rule(pattern=["git", "push"], decision="allow")\n'
    box.req(status="blocked", claim="blocked", add=["src"], surface_writes={planted: rule},
            blockers=[{"reason": "reflector-questions", "question": "which?"}])
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    assert run.status == "blocked"
    [seen] = eh.events(box, run, "config_surface_violation")
    assert (seen["path"], seen["where"], seen["expected"], seen["found"]) == (
        planted, "exit", None, _sha(rule))
    box.req(status="awaiting_approval", claim="awaiting_approval", blockers=None,
            files={"src/two.txt": "two\n"}, surface_writes={})
    with pytest.raises(se.Refused, match=r"the launch is refused.*%s: expected absent"
                       % re.escape(planted)):
        orch.answer("REQ-901", "go on")
    assert len(box.launches()) == 1
    os.unlink(planted)
    orch.answer("REQ-901", "go on")
    box.wait(orch)
    assert run.status == "awaiting_approval" and len(box.launches()) == 2
    assert len(eh.events(box, run, "config_surface_violation")) == 1


def test_rules_reload_unknown_is_handled_as_live():
    """BR-15, AC-18: `rules_reload: unknown` is read exactly as `live`: an edit may have
    taken effect mid-run, and the violation says so; only `startup` says it could not."""
    change = esf.Change(".fake-exec-file/rules/adlc-exec.rules", "a" * 64, "b" * 64)
    assert esf.reload_effective({"rules_reload": "unknown"}) is True
    assert esf.reload_effective({"rules_reload": "live"}) is True
    assert esf.reload_effective({"rules_reload": "startup"}) is False
    unknown = esf.violation_text(change, {"rules_reload": "unknown"}, "exit")
    live = esf.violation_text(change, {"rules_reload": "live"}, "exit")
    assert unknown == live.replace("rules_reload is live", "rules_reload is unknown")
    assert "may have taken effect mid-run" in unknown
    assert "could not take effect" in esf.violation_text(change, {"rules_reload": "startup"},
                                                         "halt")
