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
    for bad in ("[[profiles]]\nx = 1\n", "approval_policy =\n",
                'approval_policy = """never"""\n'):
        user.write_text(bad)
        with pytest.raises(esf.SurfaceRefused, match="cannot be read with certainty"):
            esf.bypass_scan(adapter, [str(wc)], env)
    # A quoted key and a file with no final newline are read, and are hits; a key inside a
    # table belongs to that table, which no watched key names (review fix 5).
    for text, hit in (('approval_policy = "never"', '"never"'), ('"approval_policy" = "x"\n',
                                                                 '"x"')):
        user.write_text(text)
        assert esf.bypass_scan(adapter, [str(wc)], env) == [
            esf.Hit(str(user), "approval_policy", hit)]
    user.write_text('[profiles.p]\napproval_policy = "never"\n')
    assert esf.bypass_scan(adapter, [str(wc)], env) == []
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
    # A key after a table header belongs to that table, which no watched key names: clean
    # (review fix 5); the same key at the top level refuses the resume.
    buser.write_text(clean_user + '\nsandbox_mode = "danger-full-access"\n')
    assert esf.bypass_scan(adapter, [], {"HOME": str(box.home)}) == []
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
    policy folder mid-run is a config_surface_violation when the harness exits, and is caught
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


# ---- review fix 1: the policy file's lock is the shared mkdir lock (LESSON-014) ---------------
def _policy_env(tmp_path):
    home, state = tmp_path / "home", tmp_path / "state"
    env = {"HOME": str(home), "XDG_STATE_HOME": str(state)}
    data = {"name": "fake-exec-file", "exec": {"user_policy_file": "$HOME/" + eh.FILE_POLICY}}
    return home, env, data


def test_the_policy_lock_refuses_a_symlink_and_keeps_the_body_exception(tmp_path):
    """A symlink at the policy lock's path refuses at once, naming it, and the pre-flight
    writes nothing; a body's exception survives a release that cannot remove the lock; the
    lock makes its own state directory. The trust file's lock is the same lock."""
    import exec_trust as et
    home, env, data = _policy_env(tmp_path)
    record_file = esf.record_path(data, env)
    lock = record_file + ".lock.d"
    os.makedirs(os.path.dirname(lock))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(str(elsewhere), lock)
    with pytest.raises(esf.SurfaceRefused, match=r"%s is a symlink" % re.escape(lock)) as caught:
        with esf.file_lock(record_file, timeout=0.2):
            pass
    assert caught.value.path == lock
    with pytest.raises(esf.SurfaceRefused, match="symlink"):
        esf.ensure_policy_file(data, env, "policy\n")
    assert not (home / eh.FILE_POLICY).exists() and not os.listdir(str(elsewhere))
    os.unlink(lock)
    with pytest.raises(ValueError, match="the body's own"):
        with esf.file_lock(record_file):
            open(os.path.join(lock, "left"), "w").close()
            raise ValueError("the body's own")
    os.unlink(os.path.join(lock, "left"))
    os.rmdir(lock)
    fresh = str(tmp_path / "fresh-state" / "policy" / "x.json")
    with esf.file_lock(fresh, timeout=0.2) as held:
        assert held == fresh + ".lock.d" and os.path.isdir(held)
    trust = str(tmp_path / "trust.toml")
    with pytest.raises(ValueError, match="the body's own"):
        with et.lock(trust):
            open(os.path.join(trust + et.LOCK_SUFFIX, "left"), "w").close()
            raise ValueError("the body's own")


def test_the_policy_lock_waits_on_the_monotonic_clock(tmp_path, monkeypatch):
    """A wall clock that jumps a day per reading does not end the wait early."""
    import threading
    import time
    _home, env, data = _policy_env(tmp_path)
    record_file = esf.record_path(data, env)
    os.makedirs(record_file + ".lock.d")
    real = time.time
    jumps = []

    def jumping():
        jumps.append(1)
        return real() + 86400.0 * len(jumps)

    monkeypatch.setattr(time, "time", jumping)
    releaser = threading.Timer(0.3, os.rmdir, (record_file + ".lock.d",))
    releaser.start()
    try:
        with esf.file_lock(record_file, timeout=10.0):
            pass
    finally:
        releaser.join()


# ---- review fix 2: one fold, with the gate's Unicode normalisation -----------------------------
NFC = "café"            # é, one code point
NFD = "café"           # e and a combining acute accent


class _HideBox(object):
    """A Toolbox stand-in for :func:`exec_surfaces.hide`: ``ls-files`` answers from ``index``
    (``{path: tag}``), the repository's ``core.excludesFile`` is ``inherited``, and every call
    is appended to ``events``."""

    class Res(object):
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def __init__(self, index, events, inherited):
        self.index, self.events, self.inherited = index, events, inherited

    def git(self, repo, args, cwd=None):
        if args[0] == "ls-files":
            self.events.append(("read", "ls-files"))
            return self.Res(0, "".join("%s 100644 %s 0\t%s\0" % (tag, "1" * 40, rel)
                                       for rel, tag in sorted(self.index.items())))
        if args[:2] == ["config", "--local"]:
            self.events.append(("read", "config --local"))
            return self.Res(0, self.inherited + "\n")
        if "--get" in args:
            self.events.append(("read", " ".join(args)))
            return self.Res(1)
        self.events.append(("write", " ".join(args[:3])))
        return self.Res(0)


def test_nfc_and_nfd_spellings_fold_equal(tmp_path):
    """One fold: NFD, case-folded, NFD again, posixpath-normalised. An NFC and an NFD
    spelling of one name compare equal in the manifest (a surface the render names is not
    also made absent), in the hiding (a tracked path is not taken for an untracked render)
    and in the gate, which uses the same fold."""
    import exec_gates as eg
    nfc, nfd = ".fake-exec-file/%s.toml" % NFC, ".fake-exec-file/%s.toml" % NFD
    assert nfc != nfd and esf.fold(nfc) == esf.fold(nfd)
    assert esf.fold(".Fake-Exec-File//X.toml") == esf.fold(".fake-exec-file/x.toml")
    assert esf.fold("/Abs/" + NFC) == esf.fold("/abs/" + NFD)
    assert esf._inside(nfd, ".fake-exec-file") and esf._inside(".FAKE-EXEC-FILE/%s.toml/x"
                                                               % NFD, nfc)
    # The manifest: the surface is the file the render writes, in either spelling.
    manifest = esf.manifest_of({nfd: "x\n"}, {"config_surfaces": [nfc]})
    assert manifest == {"files": {nfd: _sha("x\n")}, "absent": [], "directories": []}
    # The hiding: the index spells it NFC, the manifest NFD; it is tracked, not untracked.
    events = []
    inherited = tmp_path / "inherited-excludes"
    inherited.write_text("*.orig\n")
    record = esf.hide(_HideBox({nfc: "H"}, events, str(inherited)), "/repo", "/wc", manifest,
                      {}, str(tmp_path / "excludes"), {"HOME": str(tmp_path)})
    assert record["untracked"] == [] and "excludesFile" not in record
    assert record["skipWorktree"] == [nfc]
    # The gate: the same fold, and no second one.
    assert not hasattr(eg, "_fold")
    assert eg.exec_path_hits([["A", nfd]], [nfc]) == [["A", nfd]]
    assert eg.gate_lines([nfd], [], [nfc]) == [
        "changes the gate: touches a config surface: %s" % nfd]


# ---- review fix 6: hide's run record is saved before any git write ----------------------------
def test_hide_checkpoints_the_record_before_each_git_write(tmp_path):
    """``hide(checkpoint=...)`` is called once the record holds ``launchBlobs``,
    ``skipWorktree`` and ``excludesFile``, and before each git write: the skip-worktree marks
    and the working copy's ``core.excludesFile``. A supervisor that dies after any write has
    a saved record that names it. Without a checkpoint nothing changes (the default)."""
    tracked, untracked = eh.FILE_CONFIG, eh.FILE_RULE
    manifest = {"files": {tracked: "a" * 64, untracked: "b" * 64}, "absent": [],
                "directories": []}
    inherited = tmp_path / "inherited-excludes"
    inherited.write_text("*.orig\n")
    excludes = str(tmp_path / "excludes")
    events = []
    seen = []

    def checkpoint(record):
        events.append(("checkpoint", None))
        seen.append(json.loads(json.dumps(record)))

    record = esf.hide(_HideBox({tracked: "H"}, events, str(inherited)), "/repo", "/wc",
                      manifest, {}, excludes, {"HOME": str(tmp_path)}, checkpoint=checkpoint)
    order = [e for e in events if e[0] != "read"]
    assert order == [("checkpoint", None), ("write", "update-index --skip-worktree --"),
                     ("checkpoint", None), ("write", "config --worktree core.excludesFile")]
    want = {"launchBlobs": {tracked: {"mode": "100644", "oid": "1" * 40}},
            "skipWorktree": [tracked], "untracked": [untracked], "excludesFile": excludes}
    assert record == want and seen == [want, want]
    # The default is a no-op checkpoint: the same record, the same writes.
    events[:] = []
    again = esf.hide(_HideBox({tracked: "H"}, events, str(inherited)), "/repo", "/wc",
                     manifest, {}, excludes, {"HOME": str(tmp_path)})
    assert again == want and [e for e in events if e[0] == "write"] == [
        ("write", "update-index --skip-worktree --"),
        ("write", "config --worktree core.excludesFile")]


# ---- review fix 3: writes walk with directory descriptors -------------------------------------
def test_guarded_write_does_not_follow_a_directory_swapped_after_the_check(tmp_path,
                                                                         monkeypatch):
    """The last directory is swapped for a symlink to a directory outside the root after the
    check passed, just before the write opens anything inside it: the write refuses, and
    nothing lands outside the root. The same swap at the walk's last step before a removal
    deletes nothing outside."""
    rel = ".fake-exec-file/rules/adlc-exec.rules"
    root = tmp_path / "wc"
    (root / ".fake-exec-file" / "rules").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "adlc-exec.rules").write_text("theirs\n")
    last = str(root / ".fake-exec-file" / "rules")
    real_open = os.open
    swapped = []

    def swap():
        if not swapped:
            swapped.append(1)
            os.rename(last, last + ".moved")
            os.symlink(str(outside), last)

    def opening(path, flags, mode=0o777, *, dir_fd=None):
        # The step that opens the last directory, or anything inside it, whatever form the
        # write takes: by name under a descriptor, or by an absolute path.
        name = os.fspath(path)
        if (dir_fd is not None and name == "rules") or name.startswith(last + os.sep):
            swap()
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", opening)
    with pytest.raises(esf.SurfaceRefused, match=r"\.fake-exec-file/rules in .*"):
        esf.guarded_write(str(root), rel, "ours\n")
    monkeypatch.undo()
    assert swapped and sorted(os.listdir(str(outside))) == ["adlc-exec.rules"]
    assert (outside / "adlc-exec.rules").read_text() == "theirs\n"
    assert os.listdir(last + ".moved") == []
    # A removal: the walk's last step meets the swapped directory and refuses.
    os.unlink(last)
    os.rename(last + ".moved", last)
    real_step = esf._step

    def stepping(parent, part, create):
        if part == "rules":
            os.rename(last, last + ".moved")
            os.symlink(str(outside), last)
        return real_step(parent, part, create)

    monkeypatch.setattr(esf, "_step", stepping)
    with pytest.raises(esf.SurfaceRefused, match="is a symlink or not a real directory"):
        esf.guarded_remove(str(root), rel)
    assert (outside / "adlc-exec.rules").read_text() == "theirs\n"


def test_guarded_write_sets_the_mode_on_its_descriptor(tmp_path):
    """A restored blob's mode is set on the file the write opened, never by path, and the
    write returns the sha256 of what it wrote."""
    root = tmp_path / "wc"
    root.mkdir()
    assert esf.guarded_write(str(root), "bin/run.sh", b"#!/bin/sh\n", mode=0o755) == \
        _sha("#!/bin/sh\n")
    assert stat.S_IMODE(os.lstat(str(root / "bin" / "run.sh")).st_mode) == 0o755
    esf.guarded_write(str(root), "bin/run.sh", "x\n")
    assert stat.S_IMODE(os.lstat(str(root / "bin" / "run.sh")).st_mode) == esf.FILE_MODE
    assert sorted(os.listdir(str(root / "bin"))) == ["run.sh"]


def test_a_platform_without_dir_fd_refuses_loudly(tmp_path, monkeypatch):
    """Where ``os`` cannot walk by descriptor the write and the removal refuse, naming what
    is missing, and never fall back to the path form."""
    root = tmp_path / "wc"
    (root / "a").mkdir(parents=True)
    (root / "a" / "b").write_text("keep\n")
    assert esf._DIR_FD_MISSING == []
    monkeypatch.setattr(esf, "_DIR_FD_MISSING", ["open", "rename"])
    for call in (lambda: esf.guarded_write(str(root), "a/c", "x\n"),
                 lambda: esf.guarded_remove(str(root), "a/b")):
        with pytest.raises(esf.SurfaceRefused, match="no descriptor-relative open, rename"):
            call()
    assert sorted(os.listdir(str(root / "a"))) == ["b"]


def test_read_config_does_not_follow_a_link_swapped_after_the_check(tmp_path, monkeypatch):
    """A working-copy config swapped for a symlink between its ``lstat`` and its open is
    refused, not read; a FIFO there is refused without blocking."""
    path = str(tmp_path / "config.toml")
    with open(path, "w") as fh:
        fh.write('sandbox_mode = "workspace-write"\n')
    elsewhere = str(tmp_path / "elsewhere.toml")
    with open(elsewhere, "w") as fh:
        fh.write('model = "x"\n')
    real_lstat = os.lstat
    swapped = []

    def lstat(p, *a, **kw):
        st = real_lstat(p, *a, **kw)
        if os.fspath(p) == path and not swapped:
            swapped.append(1)
            os.unlink(path)
            os.symlink(elsewhere, path)
        return st

    monkeypatch.setattr(os, "lstat", lstat)
    with pytest.raises(esf.SurfaceRefused, match="changed while it was read|is a symlink"):
        esf._read_config(path, False)
    monkeypatch.undo()
    assert swapped
    os.unlink(path)
    os.mkfifo(path)
    with pytest.raises(esf.SurfaceRefused, match="not a regular file"):
        esf._read_config(path, False)
    with pytest.raises(esf.SurfaceRefused, match="not a regular file"):
        esf._read_config(path, True)


# ---- review fix 4: a policy change during a run is marked on the record -----------------------
def test_a_policy_change_during_a_run_is_marked_until_install(tmp_path, monkeypatch):
    """The operator's own file may change between runs: the next pre-flight records it. A
    change a run's strict check finds is marked on the record, naming the files, and every
    pre-flight refuses while it is marked, the file put back or not, naming them and the
    command to run; ``install_policy_file`` re-records the folder and clears the mark."""
    home, env, data = _policy_env(tmp_path)
    folder = home / eh.FILE_POLICY_DIR
    folder.mkdir(parents=True)
    operator = folder / "default.rules"
    operator.write_text("# mine\n")
    record = esf.install_policy_file(data, env, "policy\n")
    assert "violated" not in record
    operator.write_text("# mine, edited between runs\n")
    record = esf.ensure_policy_file(data, env, "policy\n")
    assert record["files"]["default.rules"] == _sha("# mine, edited between runs\n")
    operator.write_text("# changed during a run\n")
    problems = esf.check_policy(record)
    assert [c.path for c in problems] == [str(operator)]
    marked = esf.mark_policy_violation(data, env, problems)
    assert marked["violated"] == [str(operator)]
    assert esf.read_record(data, env)["violated"] == [str(operator)]
    assert esf.mark_policy_violation(data, env, [str(operator)])["violated"] == [str(operator)]
    operator.write_text("# mine, edited between runs\n")
    for _ in range(2):
        with pytest.raises(esf.SurfaceRefused) as caught:
            esf.ensure_policy_file(data, env, "policy\n")
        text = str(caught.value)
        assert str(operator) in text and "during an exec run" in text
        assert "inspect" in text and \
            "`adlc harness install --exec --harness fake-exec-file`" in text
    lock_dir = os.path.dirname(esf.record_path(data, env))
    assert not [n for n in os.listdir(lock_dir) if not n.endswith(".json")]
    record = esf.install_policy_file(data, env, "policy\n")
    assert "violated" not in record and "violated" not in esf.read_record(data, env)
    assert esf.ensure_policy_file(data, env, "policy\n")["sha256"] == _sha("policy\n")
    # A record that went missing is marked all the same.
    os.unlink(esf.record_path(data, env))
    esf.mark_policy_violation(data, env, [str(operator)])
    with pytest.raises(esf.SurfaceRefused, match="during an exec run"):
        esf.ensure_policy_file(data, env, "policy\n")
    # Through the engine: the pre-flight refuses while the record is marked.
    box = eh.file_sandbox(tmp_path / "engine", monkeypatch)
    (box.home / eh.FILE_POLICY_DIR).mkdir(parents=True)
    (box.home / eh.FILE_POLICY_DIR / "default.rules").write_text("# mine\n")
    box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    adapter = ea.load(box.harness, box.toolkit)
    esf.mark_policy_violation(adapter, box.environ,
                              [str(box.home / eh.FILE_POLICY_DIR / "default.rules")])
    with pytest.raises(se.Refused, match="during an exec run"):
        box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    esf.install_policy_file(adapter, box.environ, eh.fresh_files(box).user_policy_file)
    box.orch().preflight(box.reqs, harness=box.harness, shared=True)


def test_install_lets_a_run_blocked_for_a_policy_change_go_on(tmp_path, monkeypatch):
    """REQ-662 BR-4, the whole loop. An operator file in the policy folder changed during a run:
    at the exit the run is blocked and the engine's record marked, so a new pre-flight refuses.
    The operator looks and runs `adlc harness install --exec`, which records the folder anew.
    The blocked run's own copy of the record is the older one: a relaunch takes the newer,
    unmarked record as its copy and checks the folder strictly against that, so a folder that
    changed again since is refused, naming the ways out, and marks nothing (only the exit
    marks), while a folder as recorded relaunches (the must-not-refuse case), and a new
    pre-flight passes."""
    box = eh.file_sandbox(tmp_path, monkeypatch)
    folder = box.home / eh.FILE_POLICY_DIR
    folder.mkdir(parents=True)
    operator = folder / "default.rules"
    operator.write_text("# mine\n")
    box.req(status="blocked", claim="blocked", add=["src"],
            surface_writes={str(operator): "# changed during the run\n"},
            blockers=[{"reason": "reflector-questions", "question": "which?"}])
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    adapter = ea.load(box.harness, box.toolkit)
    assert run.status == "blocked" and se.PROTOCOL in json.dumps(
        run.read_primary_state()["blockers"])
    assert esf.read_record(adapter, box.environ)["violated"] == [str(operator)]
    with pytest.raises(se.Refused, match="during an exec run"):
        box.orch().preflight(box.reqs, harness=box.harness, shared=True)
    box.req(status="awaiting_approval", claim="awaiting_approval", blockers=None,
            files={"src/two.txt": "two\n"}, surface_writes={})
    text = eh.fresh_files(box).user_policy_file
    esf.install_policy_file(adapter, box.environ, text)
    # Changed again after the re-record: refused, naming the ways out, and nothing marked.
    operator.write_text("# changed once more\n")
    with pytest.raises(se.Refused) as caught:
        orch.answer("REQ-901", "go on")
    message = str(caught.value)
    assert "the launch is refused" in message and str(operator) in message
    assert "`adlc harness install --exec --harness fake-exec-file`" in message
    assert "`adlc sprint-exec answer REQ-901`" in message
    assert "violated" not in esf.read_record(adapter, box.environ)
    assert run.status == "blocked" and len(box.launches()) == 1
    record = esf.install_policy_file(adapter, box.environ, text)
    orch.answer("REQ-901", "go on")
    box.wait(orch)
    assert run.status == "awaiting_approval" and len(box.launches()) == 2
    assert run.doc["policyManifest"] == record
    assert len(eh.events(box, run, "config_surface_violation")) == 1
    assert "violated" not in esf.read_record(adapter, box.environ)
    box.orch().preflight(box.reqs, harness=box.harness, shared=True)


# ---- review fix 5: the bypass scan on the shipped Codex block ---------------------------------
CODEX_USER = ".codex/config.toml"
WRITABLE = "sandbox_workspace_write.writable_roots"
NETWORK = "sandbox_workspace_write.network_access"


@pytest.mark.parametrize("text, want", [
    ('[sandbox_workspace_write]\nwritable_roots = ["/elsewhere"]\n',
     [(WRITABLE, '["/elsewhere"]')]),
    ('sandbox_workspace_write = { writable_roots = ["/elsewhere"] }\n',
     "top-level inline table at line 1"),
    ('sandbox_workspace_write.writable_roots = ["/elsewhere"]\n', "dotted key at line 1"),
    ('["sandbox_workspace_write"]\nwritable_roots = ["/elsewhere"]\n',
     [(WRITABLE, '["/elsewhere"]')]),
    ('"sandbox_mode" = "danger-full-access"\n', [("sandbox_mode", '"danger-full-access"')]),
    ("[sandbox_workspace_write]\n'network_access' = true\n", [(NETWORK, "true")]),
    ("[sandbox_workspace_write]\nnetwork_access = true\n", [(NETWORK, "true")]),
    ('profile = "x"\n', [("profile", '"x"')]),
    ('[sandbox_workspace_write]\nwritable_roots = [\n  "/elsewhere",\n]\n',
     "multi-line array at line 2"),
    ('approval_policy = "never"', [("approval_policy", '"never"')]),
    # The must-not-refuse cases.
    ("[sandbox_workspace_write]\nexclude_slash_tmp = true\n", []),
    ('[profiles.fast]\napproval_policy = "never"\nsandbox_mode = "danger-full-access"\n', []),
    ('model = "x"', []),
    ('sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n', []),
])
def test_bypass_scan_on_the_shipped_codex_block(tmp_path, text, want):
    """BR-16 on the shipped Codex block: each spelling of a watched key is a hit or a refusal,
    never a silent clean scan, in the user config and in a working copy's config alike, where
    the keys watched are the ones the block lists for that file. A refusal names the file, the
    construct and its line and says what to do: the engine reads the file with a strict line
    reader, so put that value on one line. A profile table nobody selects, an unrelated key in
    the sandbox table and a file with no final newline are clean (the must-not-refuse
    cases)."""
    codex = ea.load("codex", TOOLKIT)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    wc = tmp_path / "wc"
    (wc / ".codex").mkdir(parents=True)
    watched = codex.block["bypass_config_keys"]
    assert set(watched) == {"$HOME/" + CODEX_USER, CODEX_USER}
    for path, roots, keys in ((home / CODEX_USER, [], watched["$HOME/" + CODEX_USER]),
                              (wc / CODEX_USER, [str(wc)], watched[CODEX_USER])):
        for other in (home / CODEX_USER, wc / CODEX_USER):
            if other.exists():
                other.unlink()
        path.write_text(text)
        if isinstance(want, str):
            with pytest.raises(esf.SurfaceRefused) as caught:
                esf.bypass_scan(codex, roots, {"HOME": str(home)})
            message = str(caught.value)
            assert str(path) in message and want in message
            assert "cannot be read with certainty" in message and "(REQ-662 BR-16)" in message
            assert "strict line reader" in message and "on one line" in message
            continue
        hits = esf.bypass_scan(codex, roots, {"HOME": str(home)})
        assert [(h.key, h.value) for h in hits] == [(k, v) for k, v in want if k in keys], path
        assert all(h.path == str(path) for h in hits)


def test_the_json_scan_refuses_with_the_same_text(tmp_path):
    """The TOML and JSON readers refuse through one helper, so the refusal reads the same."""
    flags = ha.load_adapter(os.path.join(FIX, "fake-exec-flags.yml"), toolkit=TOOLKIT)
    home = tmp_path / "home"
    (home / ".fake-exec-flags").mkdir(parents=True)
    (home / ".fake-exec-flags" / "config.json").write_text('{"a": 1, "a": 2}\n')
    with pytest.raises(esf.SurfaceRefused) as caught:
        esf.bypass_scan(flags, [], {"HOME": str(home)})
    assert str(caught.value) == esf.unreadable_text(
        str(home / ".fake-exec-flags" / "config.json"), "duplicate key 'a'", esf.JSON_ADVICE)
