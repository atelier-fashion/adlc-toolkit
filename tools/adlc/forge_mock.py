#!/usr/bin/env python3
"""forge_mock — the stateful offline forge behind ``ADLC_FORGE_MOCK=1`` (REQ-659 ADR-8).

The shell mock in ``partials/forge.sh`` answers fixed strings. The exec engine's tests
need a forge that remembers: a PR opened by a test harness, a head that moves, a merge
the local diff gates can then see. With ``ADLC_FORGE_MOCK_STORE=<dir>`` the partial sends
every call here. Without a store only the fields and ops REQ-659 added reach this file,
answered from in-memory defaults, so an old call site sees no change.

The store::

    config.json    {"remote": "<bare repo>", "owner": "...", "name": "..."}
    prs.json       {"next": 101, "prs": [...]}
    commit_prs.json {"<sha>": [numbers]}
    calls.log      one JSON line per call: {op, argv, repo}
    scenario       optional: one ADLC_FORGE_MOCK_SCENARIO value, read at each call

``merge`` is a real squash into the bare remote. Scenarios (BR-26 g): ``head-advances``,
``pr-replaced``, ``pr-other-repo``, ``cross-repo``, ``second-open-pr``, ``base-other``,
``merged``, ``protection-ok``, ``protection-no-pr``, ``protection-bypass``,
``protection-force-push``, ``protection-deletion``, ``protection-lookup-fail``.

``make-head`` builds a PR-head commit in the bare remote with plumbing, so a fixture can
state a rename, a symlink, a gitlink or a mode that a working tree makes awkward.
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import forge_protection

ERROR_CLASSES = ("auth-missing", "pr-not-found", "merge-blocked-by-policy",
                 "feature-unsupported", "local-git", "network")
BASE_FIELDS = ("number", "url", "state", "mergedAt", "body", "title", "isDraft", "createdAt",
               "headRefName", "headRefOid", "baseRefName", "isCrossRepository", "files",
               "mergeCommit")


def _provider():
    return os.environ.get("ADLC_FORGE_MOCK_PROVIDER", "github")


def _store():
    return os.environ.get("ADLC_FORGE_MOCK_STORE", "")


def _scenario():
    store = _store()
    if store:
        path = os.path.join(store, "scenario")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                value = fh.read().strip()
            if value:
                return value
    return os.environ.get("ADLC_FORGE_MOCK_SCENARIO", "ok")


def _err(klass, raw):
    print("error_class=%s" % klass)
    print("raw=%s" % raw)
    return 1


def _load(name, default):
    path = os.path.join(_store(), name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump(name, data):
    path = os.path.join(_store(), name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _git(args, env=None):
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run(["git"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, env=full)


def _remote():
    return _load("config.json", {}).get("remote", "")


def _head_oid(branch):
    remote = _remote()
    if not remote:
        return ""
    res = _git(["-C", remote, "rev-parse", "--verify", "-q", "refs/heads/%s" % branch])
    return res.stdout.strip() if res.returncode == 0 else ""


def _files(pr):
    if "filesOverride" in pr:
        return list(pr["filesOverride"])
    remote = _remote()
    head = pr.get("headRefOidPinned") or _head_oid(pr["headRefName"])
    if not remote or not head:
        return []
    res = _git(["-C", remote, "diff", "--name-only", "refs/heads/%s...%s"
                % (pr["baseRefName"], head)])
    return [ln for ln in res.stdout.splitlines() if ln]


def _url(number):
    cfg = _load("config.json", {}) if _store() else {}
    if _provider() == "azure-devops":
        return "https://mock.forge/%s/_git/%s/pullrequest/%s" % (
            cfg.get("owner", "acme"), cfg.get("name", "widgets"), number)
    return "https://mock.forge/%s/%s/pull/%s" % (
        cfg.get("owner", "acme"), cfg.get("name", "widgets"), number)


def _default_pr():
    return {"number": 101, "url": _url(101), "state": "OPEN", "mergedAt": "", "body": "mock body",
            "title": "mock", "isDraft": False, "createdAt": "2026-10-31T00:00:00Z",
            "headRefName": "feat/REQ-520-forge-adapter",
            "baseRefName": "main", "isCrossRepository": False,
            "headRefOidPinned": "0" * 40, "filesOverride": ["README.md"],
            "mergeCommit": "1" * 40}


def _all_prs():
    if not _store():
        return [_default_pr()]
    return _load("prs.json", {"next": 101, "prs": []})["prs"]


def _save(prs, nxt=None):
    doc = _load("prs.json", {"next": 101, "prs": []})
    doc["prs"] = prs
    if nxt is not None:
        doc["next"] = nxt
    _dump("prs.json", doc)


def _find(ref, prs):
    text = str(ref or "")
    match = re.search(r"/(?:pull|pullrequest)/([0-9]+)$", text)
    number = int(match.group(1)) if match else (int(text) if text.isdigit() else None)
    for pr in prs:
        if number is not None and pr["number"] == number:
            return pr
    for pr in reversed(prs):
        if pr["headRefName"] == text:
            return pr
    return None


def _value(pr, field, scenario):
    if field == "headRefOid":
        return pr.get("headRefOidPinned") or _head_oid(pr["headRefName"])
    if field == "files":
        return _files(pr)
    if field == "isCrossRepository":
        return True if scenario == "cross-repo" else pr.get("isCrossRepository", False)
    if field == "state":
        return "MERGED" if scenario == "merged" else pr.get("state", "OPEN")
    if field == "baseRefName" and scenario == "base-other":
        return "develop"
    if field == "headRefName" and scenario == "head-other":
        return pr["headRefName"] + "-other"
    if field == "number" and scenario == "pr-replaced":
        return pr["number"] + 1000
    if field == "url":
        if scenario == "pr-other-repo":
            return pr["url"].replace("/pull/", "-fork/pull/").replace("/pullrequest/",
                                                                      "-fork/pullrequest/")
        if scenario == "pr-replaced":
            return re.sub(r"[0-9]+$", str(pr["number"] + 1000), pr["url"])
    return pr.get(field, "")


def _kv(field, value):
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, (list, dict)):
        value = json.dumps(value, separators=(",", ":"))
    print("%s=%s" % (field, value))


def _flag(argv, name):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _positional(argv):
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            skip = a in ("--fields", "--json", "-q", "--jq", "-R", "--repo", "--head", "--state",
                         "--match-head-commit", "--title", "--body", "--body-file", "--base")
            continue
        return a
    return None


def op_pr_create(argv):
    head = _flag(argv, "--head") or ""
    base = _flag(argv, "--base") or "main"
    if not _store():
        print("url=%s\nnumber=101\nstate=OPEN" % _url(101))
        return 0
    doc = _load("prs.json", {"next": 101, "prs": []})
    number = doc["next"]
    url = _url(number)
    pr = {"number": number, "url": url, "state": "OPEN", "mergedAt": "",
          "body": _flag(argv, "--body") or "", "title": _flag(argv, "--title") or "",
          "isDraft": "--draft" in argv, "createdAt": "2026-10-31T00:00:%02dZ" % (number % 60),
          "headRefName": head, "baseRefName": base, "isCrossRepository": False,
          "mergeCommit": ""}
    doc["prs"].append(pr)
    doc["next"] = number + 1
    _dump("prs.json", doc)
    print("url=%s\nnumber=%s\nstate=OPEN" % (url, number))
    return 0


def op_pr_ready(argv):
    prs = _all_prs()
    pr = _find(_positional(argv), prs)
    if pr is None:
        return _err("pr-not-found", "mock: no such PR")
    if _store():
        pr["isDraft"] = False
        _save(prs)
    print("state=OPEN")
    return 0


def op_pr_edit(argv):
    prs = _all_prs()
    pr = _find(_positional(argv), prs)
    if pr is None:
        return _err("pr-not-found", "mock: no such PR")
    if _store():
        title = _flag(argv, "--title")
        if title is not None:
            pr["title"] = title
        body = _flag(argv, "--body")
        path = _flag(argv, "--body-file")
        if path is not None:
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        if body is not None:
            pr["body"] = body
        _save(prs)
    print("url=%s" % pr["url"])
    return 0


def op_pr_view(argv):
    scenario = _scenario()
    prs = _all_prs()
    pr = _find(_positional(argv), prs)
    if pr is None:
        return _err("pr-not-found", "mock: no such PR")
    fields = _flag(argv, "--fields")
    if fields:
        for field in fields.split(","):
            if field not in BASE_FIELDS:
                return _err("network", "mock: unknown field %s" % field)
            _kv(field, _value(pr, field, scenario))
        return 0
    wanted = _flag(argv, "--json")
    if wanted:
        print(json.dumps({f: _value(pr, f, scenario) for f in wanted.split(",")}))
        return 0
    for field in ("number", "url", "state", "mergedAt", "body"):
        _kv(field, _value(pr, field, scenario))
    return 0


def op_pr_list(argv):
    scenario = _scenario()
    prs = _all_prs()
    head = _flag(argv, "--head")
    wanted = _flag(argv, "--json")
    selected = [p for p in prs if head is None or p["headRefName"] == head]
    state = (_flag(argv, "--state") or "open").upper()
    if state != "ALL":
        selected = [p for p in selected if p.get("state", "OPEN") == state]
    if wanted:
        rows = [{f: _value(p, f, scenario) for f in wanted.split(",")} for p in selected]
        if scenario == "second-open-pr" and rows:
            extra = dict(rows[0])
            if "number" in extra:
                extra["number"] = extra["number"] + 1
            if "url" in extra:
                extra["url"] = re.sub(r"[0-9]+$", str(extra.get("number", 0)), extra["url"])
            rows.append(extra)
        print(json.dumps(rows))
        return 0
    for pr in selected:
        print("number=%s|url=%s|head=%s" % (pr["number"], pr["url"], pr["headRefName"]))
    return 0


def _squash(pr):
    remote = _remote()
    base_ref = "refs/heads/%s" % pr["baseRefName"]
    head = _head_oid(pr["headRefName"])
    res = _git(["-C", remote, "merge-tree", "--write-tree", base_ref, head])
    if res.returncode != 0:
        return None, "merge conflict"
    tree = res.stdout.splitlines()[0].strip()
    env = {"GIT_AUTHOR_NAME": "mock", "GIT_AUTHOR_EMAIL": "mock@forge.invalid",
           "GIT_COMMITTER_NAME": "mock", "GIT_COMMITTER_EMAIL": "mock@forge.invalid"}
    res = _git(["-C", remote, "commit-tree", tree, "-p", base_ref, "-m",
                "%s (#%s)" % (pr.get("title") or pr["headRefName"], pr["number"])], env)
    if res.returncode != 0:
        return None, res.stderr.strip()
    oid = res.stdout.strip()
    res = _git(["-C", remote, "update-ref", base_ref, oid])
    if res.returncode != 0:
        return None, res.stderr.strip()
    return oid, ""


def op_pr_merge(argv):
    if "--match-head-commit" in argv and _provider() == "azure-devops":
        return _err("feature-unsupported",
                    "the Azure DevOps backend cannot pin a merge to a head commit")
    scenario = _scenario()
    prs = _all_prs()
    pr = _find(_positional(argv), prs)
    if pr is None:
        return _err("pr-not-found", "mock: no such PR")
    pin = _flag(argv, "--match-head-commit")
    if not _store():
        print("state=MERGED")
        return 0
    head = _head_oid(pr["headRefName"])
    if scenario == "head-advances" or (pin and pin != head):
        return _err("merge-blocked-by-policy",
                    "mock: head branch was modified; review and try the merge again")
    if pr.get("state") != "OPEN":
        return _err("merge-blocked-by-policy", "mock: PR is %s" % pr.get("state"))
    oid, why = _squash(pr)
    if oid is None:
        return _err("merge-blocked-by-policy", "mock: %s" % why)
    pr.update({"state": "MERGED", "mergedAt": "2026-10-31T01:00:00Z", "mergeCommit": oid,
               "headRefOidPinned": head})
    _save(prs)
    print("state=MERGED")
    if "--delete-branch" in argv:
        _git(["-C", _remote(), "update-ref", "-d", "refs/heads/%s" % pr["headRefName"]])
        print("branch_deleted=1")
    return 0


def op_pr_comment(argv):
    if _provider() == "azure-devops":
        return _err("feature-unsupported", "ADO pr_comment is not supported in v1")
    print("ok=1")
    return 0


PROTECTION = {
    "protection-ok": dict(rules=[{"type": "pull_request", "ruleset_id": 1},
                                 {"type": "non_fast_forward", "ruleset_id": 1},
                                 {"type": "deletion", "ruleset_id": 1}],
                          rulesets={"1": {"current_user_can_bypass": "never"}}),
    "protection-no-pr": dict(rules=[{"type": "non_fast_forward", "ruleset_id": 1},
                                    {"type": "deletion", "ruleset_id": 1}],
                             rulesets={"1": {"current_user_can_bypass": "never"}}),
    "protection-bypass": dict(rules=[{"type": "pull_request", "ruleset_id": 1},
                                     {"type": "non_fast_forward", "ruleset_id": 1},
                                     {"type": "deletion", "ruleset_id": 1}],
                              rulesets={"1": {"current_user_can_bypass": "always"}}),
    "protection-force-push": dict(rules=[{"type": "pull_request", "ruleset_id": 1},
                                         {"type": "deletion", "ruleset_id": 1}],
                                  rulesets={"1": {"current_user_can_bypass": "never"}}),
    "protection-deletion": dict(rules=[{"type": "pull_request", "ruleset_id": 1},
                                       {"type": "non_fast_forward", "ruleset_id": 1}],
                                rulesets={"1": {"current_user_can_bypass": "never"}}),
    "protection-lookup-fail": dict(rules_failed=True),
}


def op_branch_protection(argv):
    scenario = _scenario()
    if scenario not in PROTECTION:
        scenario = "protection-ok"
    print(forge_protection.evaluate(**PROTECTION[scenario]))
    return 0


def op_commit_prs(argv):
    sha = _positional(argv) or ""
    numbers = []
    if _store():
        numbers = list(_load("commit_prs.json", {}).get(sha, []))
        numbers += [p["number"] for p in _all_prs() if p.get("mergeCommit") == sha]
    for n in sorted(set(numbers)):
        print(n)
    return 0


def _remove(remote, path, env):
    """Drop one path from a temporary index. A bare repo has no work tree to ask."""
    full = dict(os.environ)
    full.update(env)
    subprocess.run(["git", "-C", remote, "update-index", "--index-info"], env=full,
                   input="0 %s\t%s\n" % ("0" * 40, path), universal_newlines=True)


def make_head(argv):
    """``make-head <branch> <base-ref> [--commit-on-branch] <spec>...``

    Each spec is ``path=content``, ``path:100755=content``, ``link:path=target``,
    ``gitlink:path=<oid>``, ``rm:path`` or ``mv:old=new``. Prints the new oid.
    """
    branch, base = argv[0], argv[1]
    specs = argv[2:]
    on_branch = "--commit-on-branch" in specs
    specs = [s for s in specs if s != "--commit-on-branch"]
    remote = _remote()
    start = "refs/heads/%s" % branch if on_branch else "refs/heads/%s" % base
    index = tempfile.mkdtemp(prefix="mock-index")
    env = {"GIT_INDEX_FILE": os.path.join(index, "i")}
    try:
        _git(["-C", remote, "read-tree", start], env)
        for spec in specs:
            if spec.startswith("rm:"):
                _remove(remote, spec[3:], env)
                continue
            if spec.startswith("mv:"):
                old, new = spec[3:].split("=", 1)
                line = _git(["-C", remote, "ls-files", "-s", "--", old], env).stdout.split()
                _remove(remote, old, env)
                _git(["-C", remote, "update-index", "--add", "--cacheinfo",
                      "%s,%s,%s" % (line[0], line[1], new)], env)
                continue
            path, content = spec.split("=", 1)
            mode = "100644"
            if path.startswith("link:"):
                path, mode = path[5:], "120000"
            elif path.startswith("gitlink:"):
                _git(["-C", remote, "update-index", "--add", "--cacheinfo",
                      "160000,%s,%s" % (content, path[8:])], env)
                continue
            elif ":" in path:
                path, mode = path.rsplit(":", 1)
            blob = subprocess.run(["git", "-C", remote, "hash-object", "-w", "--stdin"],
                                  input=content, stdout=subprocess.PIPE,
                                  universal_newlines=True).stdout.strip()
            _git(["-C", remote, "update-index", "--add", "--cacheinfo",
                  "%s,%s,%s" % (mode, blob, path)], env)
        tree = _git(["-C", remote, "write-tree"], env).stdout.strip()
        idenv = {"GIT_AUTHOR_NAME": "mock", "GIT_AUTHOR_EMAIL": "mock@forge.invalid",
                 "GIT_COMMITTER_NAME": "mock", "GIT_COMMITTER_EMAIL": "mock@forge.invalid"}
        oid = _git(["-C", remote, "commit-tree", tree, "-p", start, "-m", "head"], idenv)
        oid = oid.stdout.strip()
        _git(["-C", remote, "update-ref", "refs/heads/%s" % branch, oid])
    finally:
        shutil.rmtree(index, ignore_errors=True)
    print(oid)
    return 0


OPS = {"pr_create": op_pr_create, "pr_ready": op_pr_ready, "pr_edit": op_pr_edit,
       "pr_view": op_pr_view, "pr_list": op_pr_list, "pr_merge": op_pr_merge,
       "pr_comment": op_pr_comment, "branch_protection": op_branch_protection,
       "commit_prs": op_commit_prs}


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: forge_mock.py <op> [args...]\n")
        return 2
    op, rest = argv[1], argv[2:]
    if op == "make-head":
        return make_head(rest)
    scenario = _scenario()
    if scenario in ERROR_CLASSES and op in OPS:
        return _err(scenario, "mock backend (%s): simulated %s for %s" % (_provider(), scenario,
                                                                          op))
    handler = OPS.get(op)
    if handler is None:
        return _err("network", "mock backend: unknown op '%s'" % op)
    store = _store()
    if not store:
        return handler(rest)
    with open(os.path.join(store, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(os.path.join(store, "calls.log"), "a", encoding="utf-8") as log:
            log.write(json.dumps({"op": op, "argv": rest,
                                  "repo": os.environ.get("ADLC_FORGE_REPO", "")}) + "\n")
        return handler(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
