"""BR-11 as one function: ``exec_verify.verdict`` (REQ-662 ADR-2, TASK-260).

The fixture adapters (``fixtures/harness/fake-exec-{flags,file}.yml``) and result files
(``fixtures/probe-results/``) are synthetic. Each case changes one reading or one declaration
of an acceptable pair and holds what the verdict says, so a rule is tested alone.
"""

import argparse
import copy
import io
import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_verify as ev  # noqa: E402
import harness_adapter as ha  # noqa: E402
import harness_cli  # noqa: E402
import harness_doctor  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
ADAPTERS = os.path.join(HERE, "fixtures", "harness")
RESULTS = os.path.join(HERE, "fixtures", "probe-results")
#: Which result file each fixture adapter is acceptable against.
PAIRS = {"fake-exec-flags": "hooks-pass", "fake-exec-file": "prompt-pass"}


def result(name):
    with open(os.path.join(RESULTS, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def set_reading(res, key, status):
    """``probe`` or ``probe/variant`` reads ``status``; ``None`` removes it."""
    probe, _, variant = key.partition("/")
    row = res["probes"].setdefault(probe, {"status": "pass", "ran_at": res["ran_at"]})
    if variant:
        subs = row.setdefault("sub_results", {})
        if status is None:
            subs.pop(variant, None)
        else:
            subs[variant] = {"status": status}
    elif status is None:
        res["probes"].pop(probe)
    else:
        row["status"] = status
    return res


def cite(adapter, res):
    """The yml caches as a maintainer would write them from ``res``: ``exec.probes`` cites
    each required row and ``exec.status`` is ``verified``."""
    adapter["exec"]["probes"] = [
        {"id": p, "ran_at": res["probes"][p]["ran_at"], "harness_version":
         res["harness_version"], "status": res["probes"][p]["status"]}
        for p in ev.required(adapter["exec"]) if p in res["probes"]]
    adapter["exec"]["status"] = "verified"
    return adapter


def fixture(name, top=None, **block):
    """A fixture adapter as the loader reads it, with top-level and exec keys replaced."""
    adapter = copy.deepcopy(ha.load_adapter(os.path.join(ADAPTERS, name + ".yml"),
                                            toolkit=TOOLKIT))
    adapter.update(top or {})
    adapter["exec"].update(block)
    return adapter


def judge(name, edits=(), top=None, res=None, version=None, **block):
    """The verdict for fixture ``name`` against its acceptable result with ``edits``
    (``(key, status)`` pairs) applied, caches cited from the edited result."""
    res = res or result(PAIRS[name])
    for key, status in edits:
        set_reading(res, key, status)
    adapter = cite(fixture(name, top, **block), res)
    return ev.verdict(adapter, res, version or adapter["exec"]["harness_version"])


# ---- AC-11 ------------------------------------------------------------------------------------
UNVERIFIED = [
    # (fixture, edits, declarations, the subject named)
    ("fake-exec-flags", [("trust-then-headless", "unknown")], {}, "trust-then-headless"),
    ("fake-exec-flags", [("trust-then-headless/hooks-loaded", "n/a")], {}, "trust-then-headless"),
    ("fake-exec-flags", [("session-start-context", "n/a")], {}, "session-start-context"),
    ("fake-exec-flags", [("session-start-context", "unknown")], {}, "session-start-context"),
    ("fake-exec-file", [("trust-then-headless/allowlist-loaded", "unknown")], {},
     "trust-then-headless"),
    # stdin-prompt's top-level pass is not read: the variant prompt_variant names is.
    ("fake-exec-flags", [("stdin-prompt/without-prompt-flag", "fail")], {}, "stdin-prompt"),
    ("fake-exec-file", [("stdin-prompt/without-prompt-flag", None)], {}, "stdin-prompt"),
    ("fake-exec-flags", [("stdin-prompt/without-prompt-flag", "unknown")], {}, "stdin-prompt"),
    # fence-vs-allowlist's runner-prefix variant, never its top-level status.
    ("fake-exec-flags", [("fence-vs-allowlist", "pass"), ("fence-vs-allowlist/runner-prefix",
                                                          "fail")], {}, "fence-vs-allowlist"),
    ("fake-exec-file", [("fence-vs-allowlist/runner-prefix", "n/a")], {}, "fence-vs-allowlist"),
    ("fake-exec-file", [("fence-vs-allowlist/runner-prefix", None)], {}, "fence-vs-allowlist"),
    # Declaration-bound probes must read pass or fail.
    ("fake-exec-flags", [("git-write-main", "unknown")], {}, "git-write-main"),
    ("fake-exec-file", [("git-write-worktree", "n/a")], {}, "git-write-worktree"),
    ("fake-exec-flags", [("shell-timeout", "n/a")], {}, "shell-timeout"),
    ("fake-exec-file", [("ask-tier-deny", "unknown")], {}, "ask-tier-deny"),
    ("fake-exec-file", [("ask-tier-deny", None)], {}, "ask-tier-deny"),
    # A disagreement refuses, naming the declared value and the verdict.
    ("fake-exec-flags", [("git-write-worktree", "fail")], {}, "git-write-worktree"),
    ("fake-exec-file", [("shell-timeout", "fail")], {}, "shell-timeout"),
    ("fake-exec-flags", [("ask-tier-deny/deny-under-allow", "fail")], {}, "ask-tier-deny"),
    ("fake-exec-file", [("ask-tier-deny/deny-under-allow", "unknown")], {}, "ask-tier-deny"),
    ("fake-exec-file", [("ask-tier-deny", "fail"), ("ask-tier-deny/deny-under-allow", "fail")],
     {}, "ask-tier-deny"),
    ("fake-exec-file", [("git-write-main", "fail")], {}, "git-write-main"),
]


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_verdict_table_acceptable_pair_is_verified(name):
    """The must-not-refuse case: every hard probe pass, every declaration-bound one agreeing."""
    verdict = judge(name)
    assert verdict.status == "verified" and verdict.problems == (), verdict
    assert verdict.doctor_line() == "exec: verified"


@pytest.mark.parametrize("name,edits,block,subject", UNVERIFIED)
def test_verdict_table(name, edits, block, subject):
    verdict = judge(name, edits, **block)
    assert verdict.status == "unverified"
    assert subject in verdict.subjects, verdict
    assert "exec: unverified (" in verdict.doctor_line() and subject in verdict.doctor_line()


@pytest.mark.parametrize("name,edits,block,declared,read", [
    ("fake-exec-flags", [("git-write-worktree", "fail")], {}, "strategy worktree", "reads fail"),
    ("fake-exec-file", [("shell-timeout", "fail")], {}, "delegate supported", "reads fail"),
    ("fake-exec-flags", [("ask-tier-deny/deny-under-allow", "fail")], {}, "deny_render flags",
     "deny-under-allow fail"),
    ("fake-exec-file", [("ask-tier-deny", "fail"), ("ask-tier-deny/deny-under-allow", "fail")],
     {}, "deny_render file", "reads fail"),
])
def test_disagreement_names_the_declared_value_and_the_verdict(name, edits, block, declared,
                                                                read):
    detail = " ".join(p.detail for p in judge(name, edits, **block).problems)
    assert declared in detail and read in detail, detail


def test_a_pass_under_another_version_names_each_probe():
    res = result("hooks-pass")
    res["harness_version"] = "fake-exec-flags 0.9.0"
    verdict = judge("fake-exec-flags", res=res)
    assert verdict.status == "unverified"
    assert set(verdict.subjects) == set(ev.REQUIRED)
    assert all("0.9.0" in p.detail and "1.0.0" in p.detail for p in verdict.problems)


@pytest.mark.parametrize("name,edits,block,top", [
    # git-write-worktree: fail with a clone (and a reach record that agrees with it).
    ("fake-exec-file", [("git-write-worktree", "fail"),
                        ("git-write-worktree/root-is-worktree", "fail")], {}, {}),
    ("fake-exec-flags", [("git-write-worktree", "fail")], {"working_copy": {"strategy": "clone"}},
     {"sandbox_can_reach_common_gitdir": "false"}),
    ("fake-exec-flags", [("git-write-worktree", "fail"), ("git-write-main", "fail")],
     {"working_copy": {"strategy": "orchestrator-git"}},
     {"sandbox_can_reach_common_gitdir": "false"}),
    # shell-timeout: fail with delegate: unsupported.
    ("fake-exec-flags", [("shell-timeout", "fail")], {}, {}),
    ("fake-exec-file", [("shell-timeout", "fail")],
     {"shell_timeout_s": {"value": "unknown", "verified": "false", "delegate": "unsupported"}},
     {}),
    # ask-tier-deny: fail with deny_render: none (no baseline sentinel).
    ("fake-exec-flags", [("ask-tier-deny", "fail"), ("ask-tier-deny/deny-under-allow", "fail"),
                         ("ask-tier-deny/wrapped-allow", "fail")], {"deny_render": "none"}, {}),
])
def test_a_fail_that_agrees_with_a_fallback_is_verified(name, edits, block, top):
    verdict = judge(name, edits, top=top, **block)
    assert verdict.status == "verified", verdict


# ---- BR-9 -------------------------------------------------------------------------------------
@pytest.mark.parametrize("edits", [
    [("git-write-worktree", "fail")],
    [("git-write-worktree", "unknown")],
    [("git-write-worktree", None)],
    [("git-write-worktree/writable-roots-repo", "fail")],
])
def test_worktree_needs_a_passing_probe(edits):
    verdict = judge("fake-exec-flags", edits)
    assert verdict.status == "unverified"
    assert "git-write-worktree" in verdict.subjects, verdict


@pytest.mark.parametrize("reach,edits,read", [
    ("true", [("git-write-worktree", "fail")], "fail"),
    ("false", [], "pass"),
    ("unverified", [], "pass"),
])
def test_reach_record_must_agree_with_git_write_worktree(reach, edits, read):
    verdict = judge("fake-exec-flags", edits, top={"sandbox_can_reach_common_gitdir": reach},
                    working_copy={"strategy": "orchestrator-git"})
    problem = [p for p in verdict.problems if p.subject == "sandbox_can_reach_common_gitdir"]
    assert verdict.status == "unverified" and problem, verdict
    assert "declares %s" % reach in problem[0].detail and "reads %s" % read in problem[0].detail


# ---- AC-16 ------------------------------------------------------------------------------------
@pytest.mark.parametrize("dua,render,status", [
    ("pass", "flags", "verified"),
    ("pass", "none", "verified"),
    ("fail", "none", "unverified"),
    ("unknown", "none", "unverified"),
    ("n/a", "none", "unverified"),
    ("fail", "flags", "unverified"),
])
def test_baseline_present_makes_deny_under_allow_hard(dua, render, status):
    edits = [("ask-tier-deny/deny-under-allow", dua)]
    if dua != "pass":
        edits.append(("ask-tier-deny/lone-deny", "fail"))
        edits.append(("ask-tier-deny/wrapped-allow", "fail"))
        edits.append(("ask-tier-deny", "fail"))
    verdict = judge("fake-exec-flags", edits, res=result("baseline-present"), deny_render=render)
    assert verdict.status == status, verdict
    if status == "unverified":
        assert any(p.subject == "ask-tier-deny" and "baseline" in p.detail
                   for p in verdict.problems), verdict


def test_without_the_sentinel_deny_under_allow_stays_declaration_bound():
    edits = [("ask-tier-deny", "fail"), ("ask-tier-deny/deny-under-allow", "fail"),
             ("ask-tier-deny/wrapped-allow", "fail")]
    assert judge("fake-exec-flags", edits, deny_render="none").verified
    assert not judge("fake-exec-flags", edits).verified


@pytest.mark.parametrize("baseline", ["unknown", "n/a", None])
def test_an_unmeasured_baseline_reads_unverified(baseline):
    verdict = judge("fake-exec-file", [("ask-tier-deny/baseline", baseline)])
    assert verdict.status == "unverified" and "ask-tier-deny" in verdict.subjects


# ---- AC-25 ------------------------------------------------------------------------------------
def test_context_delivery_prompt_requires_only_allowlist_loaded():
    res = result("prompt-pass")
    assert res["probes"]["trust-then-headless"]["status"] == "fail"
    assert res["probes"]["session-start-context"]["status"] == "fail"
    assert judge("fake-exec-file", res=copy.deepcopy(res)).status == "verified"
    hooks = judge("fake-exec-file", res=copy.deepcopy(res), context_delivery="hooks")
    assert hooks.status == "unverified"
    assert {"trust-then-headless", "session-start-context"} <= set(hooks.subjects), hooks
    blind = judge("fake-exec-file", [("trust-then-headless/allowlist-loaded", "fail")])
    assert blind.status == "unverified" and "trust-then-headless" in blind.subjects


# ---- AC-17 ------------------------------------------------------------------------------------
def write_result(root, name, res):
    path = os.path.join(str(root), ".adlc", "research", "harness-probes", name + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh)
    return path


def version_binary(bindir, name, version):
    os.makedirs(str(bindir), exist_ok=True)
    path = os.path.join(str(bindir), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n[ \"$1\" = --version ] && echo '%s'\n" % version)
    os.chmod(path, 0o755)
    return path


def test_version_bound_and_read_from_toolkit_root(tmp_path):
    good = result("hooks-pass")
    adapter = cite(fixture("fake-exec-flags"), good)
    declared = adapter["exec"]["harness_version"]
    # The installed binary's version must equal exec.harness_version.
    other = ev.verdict(adapter, good, "fake-exec-flags 1.0.1")
    assert other.status == "unverified" and other.subjects == ["installed-version"]
    assert "1.0.1" in other.problems[0].detail and declared in other.problems[0].detail
    assert ev.verdict(adapter, good, None).subjects == ["installed-version"]
    # The result is read from ToolkitRoot. ToolkitRoot records a fail; a working copy of the
    # same repository has edited it to pass, and that copy is never read.
    toolkit = tmp_path / "toolkit"
    working_copy = toolkit / ".worktrees" / "REQ-901"
    bad = set_reading(copy.deepcopy(good), "stdin-prompt/without-prompt-flag", "fail")
    write_result(toolkit, "fake-exec-flags", bad)
    write_result(working_copy, "fake-exec-flags", good)
    assert ev.result_path(adapter, str(toolkit)) == os.path.join(
        str(toolkit), ".adlc", "research", "harness-probes", "fake-exec-flags.json")
    binary = version_binary(tmp_path / "bin", "fake-exec-flags", declared)
    verdict = ev.recompute(adapter, str(toolkit), binary)
    assert verdict.status == "unverified" and "stdin-prompt" in verdict.subjects, verdict
    assert ev.recompute(adapter, str(working_copy), binary).verified
    # The installed version comes from REQ-654's lookup, run in the environment given.
    assert ev.installed_version(binary) == declared
    assert ev.recompute(adapter, str(working_copy),
                        version_binary(tmp_path / "bin2", "fake-exec-flags", "0.0.1")).subjects \
        == ["installed-version"]
    # A missing or unreadable file reads unverified.
    empty = tmp_path / "empty"
    assert ev.recompute(adapter, str(empty), binary).subjects == ["result-file"]
    garbled = write_result(empty, "fake-exec-flags", {})
    with open(garbled, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert ev.recompute(adapter, str(empty), binary).subjects == ["result-file"]


def test_hand_set_status_verified_without_a_result_file():
    adapter = fixture("fake-exec-file")
    assert adapter["exec"]["status"] == "verified"
    verdict = ev.verdict(adapter, None, adapter["exec"]["harness_version"])
    assert verdict.status == "unverified" and verdict.subjects == ["result-file"]


def test_recorded_skips_the_probe_set_and_still_compares_the_version():
    claude = ha.load_adapter(os.path.join(TOOLKIT, "harness", "claude.yml"), toolkit=TOOLKIT)
    block = claude["exec"]
    assert block["verification"] == "recorded"
    declared = block["harness_version"]
    assert ev.verdict(claude, None, declared).verified
    assert ev.verdict(claude, {"harness_version": "x", "probes": {}}, declared).verified
    other = ev.verdict(claude, None, "0.0.0 (Claude Code)")
    assert other.status == "unverified" and other.subjects == ["installed-version"]
    assert ev.verdict(claude, None, "0.0.0 (Claude Code)").readings == {}


def test_the_caches_are_never_the_verdict():
    res = result("hooks-pass")
    adapter = cite(fixture("fake-exec-flags"), res)
    declared = adapter["exec"]["harness_version"]
    assert ev.verdict(adapter, res, declared).verified
    # A cached row the result file no longer holds.
    moved = set_reading(copy.deepcopy(res), "shell-timeout", "fail")
    verdict = ev.verdict(adapter, moved, declared)
    assert verdict.status == "unverified"
    assert any(p.subject == "shell-timeout" and "exec.probes caches status 'pass'" in p.detail
               for p in verdict.problems), verdict
    # A required probe the cache does not cite.
    thin = copy.deepcopy(adapter)
    thin["exec"]["probes"] = thin["exec"]["probes"][1:]
    assert ev.verdict(thin, res, declared).subjects == [ev.required(thin["exec"])[0]]
    # A status cache that disagrees with an acceptable result reads unverified.
    stale = copy.deepcopy(adapter)
    stale["exec"]["status"] = "unverified"
    assert ev.verdict(stale, res, declared).subjects == ["status"]


def test_no_exec_block_is_unverified():
    plain = ha.load_adapter(os.path.join(ADAPTERS, "fake.yml"), toolkit=TOOLKIT)
    assert "exec_schema_version" not in (plain.get("exec") or {})
    assert ev.verdict(plain, None, "x").subjects == ["exec"]


# ---- BR-14 ------------------------------------------------------------------------------------
def test_doctor_prints_the_recomputed_verdict(tmp_path, monkeypatch):
    res = result("prompt-pass")
    adapter = cite(fixture("fake-exec-file"), res)
    declared = adapter["exec"]["harness_version"]
    bindir = tmp_path / "bin"
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    toolkit = tmp_path / "toolkit"
    # Not installed: no line.
    assert harness_doctor.exec_line(adapter, str(toolkit)) is None
    version_binary(bindir, "fake-exec-file", declared)
    assert harness_doctor.installed_version(adapter) == declared
    # No result file: the yml's hand-set `status: verified` is not what doctor prints.
    assert adapter["exec"]["status"] == "verified"
    assert harness_doctor.exec_line(adapter, str(toolkit)) == "exec: unverified (result-file)"
    write_result(toolkit, "fake-exec-file", res)
    assert harness_doctor.exec_line(adapter, str(toolkit)) == "exec: verified"
    write_result(toolkit, "fake-exec-file",
                 set_reading(copy.deepcopy(res), "fence-vs-allowlist/runner-prefix", "fail"))
    assert harness_doctor.exec_line(adapter, str(toolkit)) == \
        "exec: unverified (fence-vs-allowlist)"
    # A recorded block shows the version comparison alone.
    claude = ha.load_adapter(os.path.join(TOOLKIT, "harness", "claude.yml"), toolkit=TOOLKIT)
    version_binary(bindir, "claude", claude["exec"]["harness_version"])
    assert harness_doctor.exec_line(claude, str(toolkit)) == "exec: verified"
    version_binary(bindir, "claude", "9.9.9 (Claude Code)")
    assert harness_doctor.exec_line(claude, str(toolkit)) == \
        "exec: unverified (installed-version)"
    # No exec block: no line.
    plain = ha.load_adapter(os.path.join(ADAPTERS, "fake.yml"), toolkit=TOOLKIT)
    assert harness_doctor.exec_line(plain, str(toolkit)) is None


def test_harness_doctor_cli_prints_the_exec_line(tmp_path, monkeypatch):
    """`adlc harness doctor --adapter-path` on the fixture whose yml says `status: verified`
    and whose result file ToolkitRoot does not hold: the line reads unverified."""
    path = os.path.join(ADAPTERS, "fake-exec-file.yml")
    adapter = ha.load_adapter(path, toolkit=TOOLKIT)
    assert not os.path.exists(ev.result_path(adapter, TOOLKIT))
    version_binary(tmp_path / "bin", "fake-exec-file", adapter["exec"]["harness_version"])
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % (tmp_path / "bin"))
    monkeypatch.setenv("ADLC_HOME", str(tmp_path / "adlc-home"))
    monkeypatch.chdir(str(tmp_path))
    out = io.StringIO()
    harness_cli.cmd_doctor(argparse.Namespace(adapter_path=path, harness=None), out=out,
                           err=io.StringIO())
    assert "    exec: unverified (result-file)\n" in out.getvalue(), out.getvalue()
    assert shutil.which("fake-exec-file")
