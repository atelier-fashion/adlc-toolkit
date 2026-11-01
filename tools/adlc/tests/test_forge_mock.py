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
