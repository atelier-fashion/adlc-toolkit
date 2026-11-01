#!/usr/bin/env python3
"""exec_gates — the checks that stand between a model's exit and a one-way move (REQ-659).

Everything here reads git and the forge through a :class:`exec_safety.Toolbox`, and the
PR's identity from what the orchestrator itself recorded, never from the state file. The
diff gates run locally with ``--no-renames``, because a forge's file list reports a
rename under one name only. Standard library only.
"""

import json
import os
import posixpath
import re
import shlex
import shutil
import tempfile

import exec_safety as es
import harness_yaml
import lane_check

CHANGES_GATE_DIRS = (".adlc/partials/", ".adlc/tools/", ".adlc/workflows/")
_TOP_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):")
_VAR_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GateError(RuntimeError):
    """A gate could not be evaluated: the caller decides what that costs."""


class Mismatch(Exception):
    """A live PR differs from what the operator approved (BR-11)."""

    def __init__(self, field, detail):
        Exception.__init__(self, "%s: %s" % (field, detail))
        self.field = field


def top_blocks(text):
    """The named top-level blocks of a YAML document, as text.

    A project config may hold constructs the closed subset refuses in a section this
    engine never reads, so only the blocks it needs reach the strict parser.
    """
    blocks = {}
    current = None
    for line in (text or "").splitlines():
        match = _TOP_KEY.match(line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return {k: "\n".join(v) + "\n" for k, v in blocks.items()}


def config_section(text, name):
    """One parsed top-level section, or None. A malformed section raises GateError."""
    block = top_blocks(text).get(name)
    if block is None:
        return None
    try:
        return harness_yaml.loads(block, "config.yml").get(name)
    except harness_yaml.YamlError as exc:
        raise GateError("config.yml section %s: %s" % (name, exc))


def exec_config(text):
    """``sprint.exec``, with its defaults; read once and frozen at launch (BR-8)."""
    sprint = config_section(text, "sprint") or {}
    raw = sprint.get("exec") if isinstance(sprint, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    out = {"stall_minutes": 20, "require_branch_protection": True, "child_gh_token": "",
           "harness_flags": [], "allow_extra": [], "deploy": None,
           "auto_rebase_max_attempts": 1}
    unknown = sorted(set(raw) - set(out))
    if unknown:
        raise GateError("sprint.exec has unknown keys: %s" % ", ".join(unknown))
    for key, value in raw.items():
        if key == "require_branch_protection":
            value = str(value).lower() != "false"
        elif key in ("stall_minutes", "auto_rebase_max_attempts"):
            if not isinstance(value, int) or value < 0:
                raise GateError("sprint.exec.%s must be a non-negative integer" % key)
        out[key] = value
    if out["deploy"] is not None and not (isinstance(out["deploy"], dict)
                                          and set(out["deploy"]) <= {"target", "command"}):
        raise GateError("sprint.exec.deploy takes target and command")
    if out["child_gh_token"] and not _VAR_NAME.match(str(out["child_gh_token"])):
        raise GateError("sprint.exec.child_gh_token is the NAME of a variable, never a token")
    for entry in out["allow_extra"] if isinstance(out["allow_extra"], list) else [None]:
        if not isinstance(entry, list) or not entry:
            raise GateError("sprint.exec.allow_extra is a list of argv lists")
    return out


def fetch_integration(box, repo, ib):
    res = box.git(repo, ["fetch", "origin", "refs/heads/%s:refs/remotes/origin/%s" % (ib, ib)])
    if res.returncode != 0:
        raise GateError("fetch of origin/%s failed: %s" % (ib, res.stderr.strip()))


def fetch_branch(box, repo, branch):
    """Fetch a head ref; the oid it landed on, or None when the branch is not there."""
    res = box.git(repo, ["fetch", "origin",
                         "refs/heads/%s:refs/remotes/origin/%s" % (branch, branch)])
    if res.returncode != 0:
        return None
    return rev_parse(box, repo, "refs/remotes/origin/%s" % branch)


def rev_parse(box, repo, ref):
    res = box.git(repo, ["rev-parse", "--verify", "-q", ref])
    return res.stdout.strip() if res.returncode == 0 else None


def _patch_id(box, repo, diff):
    if not diff.strip():
        return ""
    out = box.git(repo, ["patch-id", "--stable"], stdin_text=diff).stdout.split()
    return out[0] if out else ""


def exit_checks(box, repo, ib, branch, launch_tip, recorded_merges):
    """BR-15's three checks against a fresh ``origin/<ib>``: violations, as text."""
    violations = []
    fetch_integration(box, repo, ib)
    base = "refs/remotes/origin/%s" % ib
    tip = fetch_branch(box, repo, branch) or rev_parse(box, repo, "refs/heads/%s" % branch)
    if tip and tip != launch_tip:
        res = box.git(repo, ["merge-base", "--is-ancestor", tip, base])
        if res.returncode == 0:
            violations.append("%s is already an ancestor of origin/%s" % (branch, ib))
        else:
            own = _patch_id(box, repo, box.git(repo, ["diff", "--no-ext-diff", launch_tip,
                                                      tip]).stdout)
            for commit in box.git(repo, ["rev-list", "%s..%s" % (launch_tip, base)]).stdout.split():
                shown = box.git(repo, ["show", "--no-ext-diff", "--format=", commit]).stdout
                if own and _patch_id(box, repo, shown) == own:
                    violations.append("commit %s on origin/%s carries %s's patch-id"
                                      % (commit, ib, branch))
    first_parent = box.git(repo, ["rev-list", "--first-parent",
                                  "%s..%s" % (launch_tip, base)]).stdout.split()
    for commit in first_parent:
        if commit in recorded_merges:
            continue
        res = box.forge("adlc_forge_commit_prs", [commit], repo)
        if res.returncode != 0:
            violations.append("commit %s on origin/%s could not be checked: %s"
                              % (commit, ib, res.stdout.strip() or res.stderr.strip()))
        elif not res.stdout.strip():
            violations.append("commit %s on origin/%s is neither a recorded orchestrator merge "
                              "nor associated with a merged PR" % (commit, ib))
    return violations


def changed_paths(box, repo, ib, oid):
    """``[[status, path], ...]`` from the local no-renames diff (BR-13)."""
    res = box.git(repo, ["diff", "--no-renames", "--no-ext-diff", "--name-status", "-z",
                         "origin/%s...%s" % (ib, oid)])
    if res.returncode != 0:
        raise GateError("diff against origin/%s failed: %s" % (ib, res.stderr.strip()))
    fields = [f for f in res.stdout.split("\0") if f]
    return [[fields[i], fields[i + 1]] for i in range(0, len(fields) - 1, 2)]


def raw_changes(box, repo, ib, oid):
    """``[(status, old_mode, new_mode, path)]``, for the chore-PR path gate."""
    res = box.git(repo, ["diff", "--no-renames", "--no-ext-diff", "--raw", "-z",
                         "origin/%s...%s" % (ib, oid)])
    if res.returncode != 0:
        raise GateError("diff against origin/%s failed: %s" % (ib, res.stderr.strip()))
    fields = [f for f in res.stdout.split("\0") if f]
    out = []
    for i in range(0, len(fields) - 1, 2):
        head = fields[i].split()
        out.append((head[4][0], head[0].lstrip(":"), head[1], fields[i + 1]))
    return out


def deploy_surface_hits(paths, command):
    """The changed paths that touch the deploy surface (BR-13). Deliberately wide."""
    blocked = lane_check.effective_config().blocked_paths
    tokens = []
    if command:
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()
        for part in parts:
            norm = posixpath.normpath(part[2:] if part.startswith("./") else part)
            if not norm.startswith(("/", "-", "..")):
                tokens.append(norm)
    hits = []
    for path in paths:
        if lane_check._matches_any(path, blocked):
            hits.append(path)
            continue
        if any(path == t or path.startswith(t + "/") for t in tokens):
            hits.append(path)
    return hits


def gate_lines(paths, surface_hits):
    """The 'changes the gate' lines of a plan (BR-23 c)."""
    lines = []
    touched = [p for p in paths if p.startswith(CHANGES_GATE_DIRS)]
    if touched:
        lines.append("changes the gate: touches %s" % ", ".join(sorted(touched)))
    if surface_hits:
        lines.append("changes the gate: modifies the deploy surface: %s"
                     % ", ".join(sorted(surface_hits)))
    return lines


def show_blob(box, repo, ref, rel):
    res = box.git(repo, ["show", "%s:%s" % (ref, rel)])
    return res.stdout if res.returncode == 0 else None


def frontmatter_flag(text, key):
    """A scalar from a spec's frontmatter block, or None."""
    if not text or not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    block = text[4:end] if end != -1 else ""
    match = re.search(r"^%s:[ \t]*(.*?)[ \t]*$" % re.escape(key), block, re.M)
    return match.group(1).strip("\"'") if match else None


def deploy_plan(box, repo, ib, oid, spec_rel, paths):
    """``(plan or None, skipped reason or None)``, from the integration branch (BR-13)."""
    text = show_blob(box, repo, "origin/%s" % ib, ".adlc/config.yml") or ""
    section = exec_config(text).get("deploy") or {}
    target, command = section.get("target"), section.get("command")
    base_spec = show_blob(box, repo, "origin/%s" % ib, spec_rel)
    head_spec = show_blob(box, repo, oid, spec_rel)
    if base_spec is None or head_spec is None:
        return None, "the spec is absent at one of the two refs"
    base_flag = frontmatter_flag(base_spec, "deployable")
    if base_flag != frontmatter_flag(head_spec, "deployable"):
        return None, "deployable differs between the integration branch and the PR head"
    if base_flag != "true":
        return None, None
    if not target or not command:
        return None, "no sprint.exec.deploy target is declared"
    if deploy_surface_hits(paths, command):
        return None, "PR modifies deploy surface"
    return {"target": target, "command": command}, None


def parse_json_list(res, what):
    if res.returncode != 0:
        raise GateError("%s failed: %s" % (what, res.stdout.strip() or res.stderr.strip()))
    try:
        doc = json.loads(res.stdout)
    except ValueError:
        raise GateError("%s did not return JSON: %s" % (what, res.stdout.strip()[:200]))
    if not isinstance(doc, list):
        raise GateError("%s did not return a list" % what)
    return doc


def lookup_pr(box, repo, branch, ib, host):
    """The one OPEN PR for ``branch``, found by the branch the orchestrator created."""
    rows = parse_json_list(box.forge("adlc_forge_pr_list", [
        "--head", branch, "--state", "all", "--json",
        "number,url,headRefOid,baseRefName,isCrossRepository,state,createdAt"], repo),
        "adlc_forge_pr_list")
    open_rows = [r for r in rows if r.get("state", "OPEN") == "OPEN"]
    merged = [r for r in rows if r.get("state") == "MERGED"]
    if len(open_rows) != 1:
        if not open_rows and merged:
            raise Mismatch("state", "%s's PR is already MERGED" % branch)
        raise GateError("%d open PRs for %s, expected one" % (len(open_rows), branch))
    row = open_rows[0]
    owner, name, number = es.parse_pr_url(row.get("url"), host)
    return {"owner": owner, "name": name, "number": number, "url": row["url"],
            "headRefOid": es.require(es.VALID_OID, row.get("headRefOid"), "headRefOid"),
            "createdAt": row.get("createdAt", "")}


def verify_pr(box, repo, pr, branch, ib, host):
    """BR-11: the live PR is the one the ledger recorded. Raises Mismatch, names the field."""
    view = es.kv(box.forge("adlc_forge_pr_view", [
        pr["url"], "--fields",
        "state,number,url,headRefName,headRefOid,baseRefName,isCrossRepository"], repo).stdout)
    if not view:
        raise GateError("adlc_forge_pr_view returned nothing for %s" % pr["url"])
    if view.get("state") == "MERGED":
        raise Mismatch("state", "already MERGED")
    if view.get("state") != "OPEN":
        raise Mismatch("state", view.get("state"))
    if view.get("headRefName") != branch:
        raise Mismatch("headRefName", view.get("headRefName"))
    if view.get("baseRefName") != ib:
        raise Mismatch("baseRefName", view.get("baseRefName"))
    if view.get("isCrossRepository") != "false":
        raise Mismatch("isCrossRepository", view.get("isCrossRepository"))
    if str(view.get("number")) != str(pr["number"]):
        raise Mismatch("number", view.get("number"))
    try:
        owner, name, _ = es.parse_pr_url(view.get("url"), host)
    except es.SafetyError as exc:
        raise Mismatch("repo", str(exc))
    if (owner, name) != (pr["owner"], pr["name"]):
        raise Mismatch("repo", "%s/%s" % (owner, name))
    if view.get("headRefOid") != pr["headRefOid"]:
        raise Mismatch("headRefOid", view.get("headRefOid"))
    rows = parse_json_list(box.forge("adlc_forge_pr_list", [
        "--head", branch, "--state", "all", "--json",
        "number,url,headRefOid,baseRefName,isCrossRepository,state"], repo),
        "adlc_forge_pr_list")
    live = [r for r in rows if r.get("state", "OPEN") == "OPEN"]
    if len(live) != 1 or live[0].get("number") != pr["number"]:
        raise Mismatch("number", "%d open PRs for %s" % (len(live), branch))
    if live[0].get("isCrossRepository"):
        raise Mismatch("isCrossRepository", "true")
    if live[0].get("baseRefName") != ib:
        raise Mismatch("baseRefName", live[0].get("baseRefName"))


def add_detached(box, repo, path, oid):
    res = box.git(repo, ["worktree", "add", "--detach", path, oid])
    if res.returncode != 0:
        raise GateError("detached worktree at %s failed: %s" % (oid, res.stderr.strip()))
    return path


def remove_worktree(box, repo, path):
    box.git(repo, ["worktree", "remove", "--force", path])


def trial_merge(box, repo, path, ib):
    """``(rc, conflicting paths)`` of the REQ-483 gate, in a detached worktree."""
    res = box.partial("trial-merge.sh", "adlc_trial_merge", [path, "origin/%s" % ib], repo,
                      tree=repo)
    return res.returncode, [ln for ln in res.stdout.splitlines() if ln]


def lane_check_rerun(box, repo, path, ib):
    res = box.partial("lane-check.sh", "adlc_lane_check", [path, "origin/%s" % ib], repo, tree=repo)
    return res.returncode, res.stdout


def _identity(box, repo, path):
    if box.git(repo, ["config", "user.email"], cwd=path).stdout.strip():
        return None
    return {"GIT_AUTHOR_NAME": "adlc-exec", "GIT_AUTHOR_EMAIL": "adlc-exec@localhost",
            "GIT_COMMITTER_NAME": "adlc-exec", "GIT_COMMITTER_EMAIL": "adlc-exec@localhost"}


def rebase_detached(box, repo, path, ib, recorded, plan_paths):
    """BR-12, in an orchestrator-owned detached worktree already at ``recorded``.

    Returns ``{"outcome": "clean", "oid": ...}``, or ``"conflict"`` with its files, or
    ``"mismatch"`` naming what failed. Nothing is pushed here.
    """
    target = "origin/%s" % ib
    old_base = box.git(repo, ["merge-base", recorded, target]).stdout.strip()
    env = _identity(box, repo, path)
    res = box.git(repo, ["rebase", target], cwd=path, extra_env=env)
    if res.returncode != 0:
        files = [ln for ln in box.git(repo, ["diff", "--name-only", "--diff-filter=U"],
                                      cwd=path).stdout.splitlines() if ln]
        box.git(repo, ["rebase", "--abort"], cwd=path)
        return {"outcome": "conflict", "files": files}
    new = box.git(repo, ["rev-parse", "HEAD"], cwd=path).stdout.strip()
    diff = box.git(repo, ["range-diff", "%s..%s" % (old_base, recorded), "%s..%s" % (target, new)],
                   cwd=path)
    pairs = [ln for ln in diff.stdout.splitlines() if re.match(r"^\s*(\d+|-):", ln)]
    if diff.returncode != 0 or not pairs or any(" = " not in ln for ln in pairs):
        return {"outcome": "mismatch", "detail": "range-diff is not every pair =: %s"
                % "; ".join(pairs)[:300]}
    now_paths = changed_paths(box, repo, ib, new)
    if sorted(map(tuple, now_paths)) != sorted(map(tuple, plan_paths)):
        return {"outcome": "mismatch", "detail": "changed-path set differs from the plan"}
    return {"outcome": "clean", "oid": new}


LESSON_RE = re.compile(r"^\.adlc/knowledge/lessons/LESSON-[0-9]+-[a-z0-9-]+\.md$")
ASSUME_RE = re.compile(r"^\.adlc/knowledge/assumptions/[A-Za-z0-9._-]+\.md$")


def chore_paths_verdict(box, repo, ib, oid, req):
    """The chore PR's local path gate (BR-14). A list of what is out of bounds."""
    spec_re = re.compile(r"^\.adlc/specs/%s-[A-Za-z0-9._-]+/(tasks/)?[A-Za-z0-9._-]+\.md$"
                         % re.escape(req))
    out = []
    for status, _old, mode, path in raw_changes(box, repo, ib, oid):
        added = status == "A"
        if status not in ("A", "M") or mode != "100644":
            out.append("%s %s %s" % (status, mode, path))
        elif LESSON_RE.match(path) or ASSUME_RE.match(path):
            if not added:
                out.append("%s %s" % (status, path))
            elif LESSON_RE.match(path) and not _lesson_passes(box, repo, oid, path):
                out.append("lesson check failed: %s" % path)
        elif not spec_re.match(path):
            out.append("%s %s" % (status, path))
    return out


def _lesson_passes(box, repo, oid, path):
    blob = show_blob(box, repo, oid, path)
    if blob is None:
        return False
    tmp = tempfile.mkdtemp(prefix="adlc-lesson-", dir=box.run_dir)
    try:
        target = os.path.join(tmp, os.path.basename(path))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(blob)
        res = box.partial("lesson-check.sh", "adlc_lesson_check", [target], box.run_dir)
        return res.returncode == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def chore_pr_fields(box, repo, url, branch, ib, host, owner, name):
    """BR-14's field gate. ``(view, reason)``, reason naming the field out of bounds."""
    view = es.kv(box.forge("adlc_forge_pr_view", [
        url, "--fields", "state,number,url,headRefName,headRefOid,baseRefName,isCrossRepository"],
        repo).stdout)
    if view.get("state") != "OPEN":
        return view, "state"
    if view.get("headRefName") != branch:
        return view, "headRefName"
    if view.get("baseRefName") != ib:
        return view, "baseRefName"
    if view.get("isCrossRepository") != "false":
        return view, "isCrossRepository"
    try:
        got = es.parse_pr_url(view.get("url"), host)
    except es.SafetyError:
        return view, "repo"
    if got[:2] != (owner, name):
        return view, "repo"
    return view, None
