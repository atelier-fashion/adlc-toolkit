"""The stateful forge mock and the protection verdict (REQ-659 BR-26, ADR-8)."""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import forge_protection as fp  # noqa: E402

MOCK = os.path.join(os.path.dirname(__file__), "..", "forge_mock.py")

RULES = [{"type": "pull_request", "ruleset_id": 1}, {"type": "non_fast_forward", "ruleset_id": 1},
         {"type": "deletion", "ruleset_id": 1}]
NEVER = {"1": {"current_user_can_bypass": "never"}}


def run(store, *args, scenario=None):
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_FORGE_MOCK_STORE=str(store))
    env.pop("ADLC_FORGE_MOCK_SCENARIO", None)
    if scenario:
        env["ADLC_FORGE_MOCK_SCENARIO"] = scenario
    return subprocess.run([sys.executable, MOCK] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)


@pytest.fixture
def forge(tmp_path):
    bare = tmp_path / "acme" / "widgets.git"
    bare.parent.mkdir()
    subprocess.check_call(["git", "init", "-q", "--bare", "-b", "main", str(bare)])
    seed = tmp_path / "seed"
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(seed)])
    (seed / "a.txt").write_text("a\n")
    for args in (["add", "-A"], ["-c", "user.email=t@e.st", "-c", "user.name=t", "commit", "-qm",
                                 "seed"], ["remote", "add", "origin", str(bare)],
                 ["push", "-q", "origin", "main"]):
        subprocess.check_call(["git", "-C", str(seed)] + args)
    store = tmp_path / "store"
    store.mkdir()
    (store / "config.json").write_text(json.dumps({"remote": str(bare), "owner": "acme",
                                                   "name": "widgets"}))
    return store, bare


def test_protection_verdicts():
    assert fp.evaluate(RULES, NEVER) == "protected"
    assert fp.evaluate(RULES[1:], NEVER) == "unprotected"
    assert fp.evaluate(RULES[:1] + RULES[2:], NEVER) == "unprotected"
    assert fp.evaluate(RULES[:2], NEVER) == "unprotected"
    assert fp.evaluate(RULES, {"1": {"current_user_can_bypass": "always"}}) == "unprotected"
    assert fp.evaluate(RULES, {"1": {"current_user_can_bypass": "pull_requests_only"}}) \
        == "unprotected"
    assert fp.evaluate(rules_failed=True) == "unknown"
    assert fp.evaluate(RULES, {}) == "unknown"
    assert fp.evaluate([], {}, classic_failed=True) == "unknown"
    assert fp.evaluate([], {}) == "unprotected"


def test_classic_protection_and_admin_bypass():
    classic = {"required_pull_request_reviews": {}, "enforce_admins": {"enabled": True},
               "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
    assert fp.evaluate([], {}, classic, is_admin=True) == "protected"
    open_admin = dict(classic, enforce_admins={"enabled": False})
    assert fp.evaluate([], {}, open_admin, is_admin=True) == "unprotected"
    assert fp.evaluate([], {}, open_admin, is_admin=False) == "protected"
    assert fp.evaluate([], {}, dict(classic, allow_force_pushes={"enabled": True})) == "unprotected"
    listed = dict(classic, required_pull_request_reviews={
        "bypass_pull_request_allowances": {"users": [{"login": "me"}]}})
    assert fp.evaluate([], {}, listed, login="me") == "unprotected"
    assert fp.evaluate([], {}, listed, login="other") == "protected"
    teams = dict(classic, required_pull_request_reviews={
        "bypass_pull_request_allowances": {"teams": [{"slug": "x"}]}})
    assert fp.evaluate([], {}, teams) == "unknown"


def test_stateful_flow_and_pin(forge):
    store, bare = forge
    first = run(store, "make-head", "feat/x", "main", "b.txt=b\n").stdout.strip()
    out = run(store, "pr_create", "--base", "main", "--head", "feat/x", "--title", "T",
              "--body", "B", "--draft").stdout
    assert "number=101" in out and "https://mock.forge/acme/widgets/pull/101" in out
    view = run(store, "pr_view", "101", "--fields", "state,headRefOid,headRefName,baseRefName,"
               "isCrossRepository,files").stdout
    assert "state=OPEN" in view and "headRefOid=%s" % first in view
    assert 'files=["b.txt"]' in view and "isCrossRepository=false" in view
    rows = json.loads(run(store, "pr_list", "--head", "feat/x", "--state", "all", "--json",
                          "number,url,headRefOid,baseRefName,isCrossRepository").stdout)
    assert rows[0]["number"] == 101 and rows[0]["headRefOid"] == first
    run(store, "make-head", "feat/x", "main", "--commit-on-branch", "c.txt=c\n")
    refused = run(store, "pr_merge", "101", "--squash", "--match-head-commit", first)
    assert refused.returncode == 1 and "error_class=merge-blocked-by-policy" in refused.stdout
    head = run(store, "pr_view", "101", "--fields", "headRefOid").stdout.strip().split("=")[1]
    # A draft does not merge, pinned to the right head or not, as on GitHub (BUG-287). The
    # mock used to merge one, which hid a pipeline that never flipped its PR to ready.
    draft = run(store, "pr_merge", "101", "--squash", "--delete-branch", "--match-head-commit",
                head)
    assert draft.returncode == 1 and "error_class=merge-blocked-by-policy" in draft.stdout
    assert "still a draft" in draft.stdout
    assert "state=OPEN" in run(store, "pr_view", "101", "--fields", "state").stdout
    assert run(store, "pr_ready", "101").returncode == 0
    done = run(store, "pr_merge", "101", "--squash", "--delete-branch", "--match-head-commit", head)
    assert done.returncode == 0 and "state=MERGED" in done.stdout
    assert "branch_deleted=1" in done.stdout
    merged = run(store, "pr_view", "101", "--fields", "state,mergeCommit").stdout
    assert "state=MERGED" in merged
    oid = merged.split("mergeCommit=")[1].strip()
    assert oid == subprocess.check_output(["git", "-C", str(bare), "rev-parse", "main"],
                                          universal_newlines=True).strip()
    assert run(store, "commit_prs", oid).stdout.strip() == "101"
    assert run(store, "commit_prs", "f" * 40).stdout.strip() == ""
    calls = [json.loads(ln) for ln in (store / "calls.log").read_text().splitlines()]
    assert any(c["op"] == "pr_merge" and head in c["argv"] for c in calls)


@pytest.mark.parametrize("scenario,field,expect", [
    ("cross-repo", "isCrossRepository", "isCrossRepository=true"),
    ("merged", "state", "state=MERGED"),
    ("base-other", "baseRefName", "baseRefName=develop"),
    ("pr-replaced", "number", "number=1101"),
])
def test_view_scenarios(forge, scenario, field, expect):
    store, _ = forge
    run(store, "make-head", "feat/x", "main", "b.txt=b\n")
    run(store, "pr_create", "--base", "main", "--head", "feat/x")
    assert expect in run(store, "pr_view", "101", "--fields", field, scenario=scenario).stdout


def test_second_open_pr_and_error_scenario(forge):
    store, _ = forge
    run(store, "make-head", "feat/x", "main", "b.txt=b\n")
    run(store, "pr_create", "--base", "main", "--head", "feat/x")
    rows = json.loads(run(store, "pr_list", "--head", "feat/x", "--state", "all", "--json",
                          "number", scenario="second-open-pr").stdout)
    assert len(rows) == 2
    out = run(store, "pr_view", "101", "--fields", "state", scenario="auth-missing")
    assert out.returncode == 1 and "error_class=auth-missing" in out.stdout


def test_make_head_kinds(forge):
    store, bare = forge
    run(store, "make-head", "feat/y", "main", "link:l=a.txt", "x.sh:100755=#!/bin/sh\n",
        "gitlink:sub=" + "a" * 40, "mv:a.txt=b.txt")
    tree = subprocess.check_output(["git", "-C", str(bare), "ls-tree", "refs/heads/feat/y"],
                                   universal_newlines=True)
    assert "120000" in tree and "100755" in tree and "160000" in tree and "b.txt" in tree
    assert "\ta.txt" not in tree


# --- REQ-719 BR-23, AC-17: pr_checks ---------------------------------------------------------

def _checks(store, ref="101", scenario=None):
    out = run(store, "pr_checks", ref, scenario=scenario)
    return out.returncode, out.stdout.splitlines()


def test_req719_pr_checks_scenarios(forge):
    """Each verdict scenario prints the contract and returns 0; pending-then-pass counts per PR
    and needs a store; an error-class scenario is the forge error; an unknown PR is refused, as
    gh refuses it; every other op reads a checks-* scenario as ok."""
    store, _ = forge
    run(store, "make-head", "feat/x", "main", "b.txt=b\n")
    run(store, "pr_create", "--base", "main", "--head", "feat/x")
    run(store, "pr_create", "--base", "main", "--head", "feat/y")
    expect = {
        "checks-pass": ["checks=pass", "check=pass\tbuild", "check=skipped\tdocs"],
        "checks-fail": ["checks=fail", "check=fail\tbuild", "check=pass\tlint"],
        "checks-pending": ["checks=pending", "check=pending\tbuild", "check=pass\tlint"],
        "checks-none": ["checks=none"],
    }
    for scenario, lines in expect.items():
        assert _checks(store, scenario=scenario) == (0, lines), scenario
    # A store's recorded list is not what the scenario reads.
    assert run(store, "set-checks", "101", "fail=recorded").returncode == 0
    assert _checks(store, scenario="checks-pass")[1][0] == "checks=pass"

    then = "checks-pending-then-pass"
    assert _checks(store, scenario=then) == (0, ["checks=pending", "check=pending\tbuild"])
    assert _checks(store, scenario=then) == (0, ["checks=pass", "check=pass\tbuild"])
    assert _checks(store, scenario=then) == (0, ["checks=pass", "check=pass\tbuild"])
    # The count is per PR: the second PR's first read is still pending.
    assert _checks(store, "102", scenario=then)[1][0] == "checks=pending"
    assert json.loads((store / "checks_reads.json").read_text()) == {"101": 3, "102": 1}
    rc, lines = _checks("", scenario=then)
    assert rc == 1 and lines[0] == "error_class=feature-unsupported", lines
    assert "ADLC_FORGE_MOCK_STORE" in lines[1]

    for klass in ("auth-missing", "network", "pr-not-found"):
        rc, lines = _checks(store, scenario=klass)
        assert rc == 1 and lines[0] == "error_class=%s" % klass, (klass, lines)
    rc, lines = _checks(store, "999999", scenario="checks-pass")
    assert rc == 1 and lines[0] == "error_class=pr-not-found", lines
    # Without a store the mock answers for its one default PR, and refuses any other.
    assert _checks("", scenario="checks-fail")[1][0] == "checks=fail"
    assert _checks("", "9", scenario="checks-pass")[1][0] == "error_class=pr-not-found"

    # Benign path: under every checks-* scenario the other ops answer as under ok.
    for scenario in list(expect) + [then]:
        for args in (["pr_view", "101", "--fields", "number,state,headRefName,files"],
                     ["pr_list", "--head", "feat/x", "--state", "all", "--json", "number,url"],
                     ["branch_protection", "main"], ["commit_prs", "f" * 40],
                     ["pr_comment", "101", "--body", "hi"]):
            ok = run(store, *args)
            got = run(store, *args, scenario=scenario)
            assert (got.returncode, got.stdout) == (ok.returncode, ok.stdout), (scenario, args)


def test_req719_pr_checks_from_the_store(forge):
    """A PR with no checks recorded reads none; set-checks writes the list a read prints, in
    order, each name on one line; set-checks is a helper, not a recorded forge op."""
    store, _ = forge
    run(store, "pr_create", "--base", "main", "--head", "feat/x")
    assert _checks(store) == (0, ["checks=none"])

    assert run(store, "set-checks", "101", "pass=build", "skipped=docs", "pending=e2e",
               "fail=lint=strict").returncode == 0
    assert _checks(store) == (0, ["checks=fail", "check=pass\tbuild", "check=skipped\tdocs",
                                  "check=pending\te2e", "check=fail\tlint=strict"])
    assert run(store, "set-checks", "101", "pass=build", "pending=e2e").returncode == 0
    assert _checks(store)[1][0] == "checks=pending"
    # Skipped checks alone read pass: one is reported, and none failed or is in flight.
    assert run(store, "set-checks", "101", "skipped=docs").returncode == 0
    assert _checks(store) == (0, ["checks=pass", "check=skipped\tdocs"])
    # A name holding a tab, a newline or another control character stays on its line.
    assert run(store, "set-checks", "101", "pass=unit\ttests\nlinux\x01x").returncode == 0
    assert _checks(store) == (0, ["checks=pass", "check=pass\tunit tests linux x"])
    # No spec records an empty list, which reads none again; the PR is found by head too.
    assert run(store, "set-checks", "feat/x").returncode == 0
    assert _checks(store) == (0, ["checks=none"])
    # A state set-checks did not write reads pending, never pass.
    doc = json.loads((store / "prs.json").read_text())
    doc["prs"][0]["checks"] = [{"name": "odd", "state": "neutral"}]
    (store / "prs.json").write_text(json.dumps(doc))
    assert _checks(store) == (0, ["checks=pending", "check=pending\todd"])

    for bad in (["101", "green=build"], ["101", "build"], []):
        out = run(store, "set-checks", *bad)
        assert out.returncode == 2 and out.stdout == "", bad
    assert run(store, "set-checks", "999", "pass=build").returncode == 1
    assert run("", "set-checks", "101", "pass=build").returncode == 2
    # An error-class scenario does not touch the helper, as it does not touch make-head.
    assert run(store, "set-checks", "101", "pass=build", scenario="network").returncode == 0
    assert _checks(store)[1][0] == "checks=pass"

    ops = [json.loads(ln)["op"] for ln in (store / "calls.log").read_text().splitlines()]
    assert "pr_checks" in ops and "set-checks" not in ops
