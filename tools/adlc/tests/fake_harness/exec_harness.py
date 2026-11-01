#!/usr/bin/env python3
"""A headless harness the exec engine can launch (REQ-659 BR-18).

Stands in for the adapter's binary on PATH. It reads `$HOME/.exec-scenario.json`, because
the engine hands a child only the adapter's variables, and acts out a run: commit, push,
open a PR, write `pipeline-state.json`, print a JSON result. Each scenario key changes one
behaviour, so a fixture states what a misbehaving model does and nothing else.
"""

import json
import os
import subprocess
import sys
import time

HOME = os.environ["HOME"]
REQ = os.environ.get("ADLC_EXEC_RUN", "")


def scenario():
    with open(os.path.join(HOME, ".exec-scenario.json"), encoding="utf-8") as fh:
        return json.load(fh)


def sh(*args, cwd=None, env=None, check=True):
    full = dict(os.environ)
    full.update(env or {})
    res = subprocess.run(args, cwd=cwd, env=full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    if check and res.returncode != 0:
        sys.stderr.write("%s failed: %s\n" % (" ".join(args), res.stderr))
        raise SystemExit(70)
    return res.stdout.strip()


def forge(top, *args):
    env = {"ADLC_FORGE_MOCK": "1", "ADLC_FORGE_MOCK_STORE": top["store"]}
    return sh(sys.executable, os.path.join(top["toolkit"], "tools", "adlc", "forge_mock.py"), *args,
              env=env)


def result(text, spec, sid="session-%s" % REQ):
    doc = {"type": "result", "session_id": spec.get("sid", sid), "is_error": False, "num_turns": 7,
           "result": text, "total_cost_usd": 0, "permission_denials": spec.get("denials", [])}
    if spec.get("no_session"):
        doc.pop("session_id")
    if spec.get("is_error"):
        doc["is_error"] = True
    print(json.dumps(doc))


def state_path(wt, spec_dir):
    return os.path.join(wt, spec_dir, "pipeline-state.json")


def write_state(wt, spec_dir, doc):
    path = state_path(wt, spec_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)


def first_launch(top, spec, prompt):
    wt = os.getcwd()
    spec_dir = top["specDirs"][REQ]
    branch = sh("git", "branch", "--show-current")
    repos = {top["repoId"]: {"touched": True, "worktree": wt, "primary": True, "branch": branch}}
    state = {"req": REQ, "branch": branch, "currentPhase": 7, "completedPhases": list(range(7)),
             "completed": False, "repos": repos, "mergeOrder": [top["repoId"]]}
    if spec.get("siblings"):
        for rid, touched in spec["siblings"].items():
            repos[rid] = {"touched": touched}
        state["mergeOrder"] = [top["repoId"]] + [r for r, t in spec["siblings"].items() if t]
    write_state(wt, spec_dir, state)
    if spec.get("dump_env"):
        with open(os.path.join(HOME, "env-%s.json" % REQ), "w", encoding="utf-8") as fh:
            json.dump(dict(os.environ), fh)
    with open(os.path.join(HOME, "prompt-%s.txt" % REQ), "a", encoding="utf-8") as fh:
        fh.write(prompt)
    if spec.get("plant"):
        for path, body in spec["plant"].items():
            full = path if os.path.isabs(path) else os.path.join(wt, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "a", encoding="utf-8") as fh:
                fh.write(body)
            if spec.get("plant_exec"):
                os.chmod(full, 0o755)
    if spec.get("exit_early") is not None:
        sys.stdout.write(spec.get("stdout", ""))
        result(spec.get("text", ""), spec)
        raise SystemExit(spec["exit_early"])
    if spec.get("sleep_first"):
        time.sleep(spec["sleep_first"])
    if spec.get("double_fork"):
        subprocess.Popen([sys.executable, "-c",
                          "import os,sys,time\nif os.fork(): os._exit(0)\nos.setsid()\n"
                          "if os.fork(): os._exit(0)\ntime.sleep(%d)\n" % spec["double_fork"]])
    for path, body in spec.get("files", {"src/%s.txt" % REQ: REQ + "\n"}).items():
        os.makedirs(os.path.dirname(os.path.join(wt, path)) or wt, exist_ok=True)
        with open(os.path.join(wt, path), "w", encoding="utf-8") as fh:
            fh.write(body)
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "feat: %s [%s]" % (REQ, REQ))
    sh("git", "push", "-q", "-u", "origin", branch)
    if spec.get("push_direct"):
        ib = top["ib"]
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/%s" % ib)
    if spec.get("squash_push"):
        ib = top["ib"]
        tmp = wt + ".squash"
        sh("git", "worktree", "add", "-q", "--detach", tmp, "origin/%s" % ib)
        sh("git", "merge", "--squash", "-q", branch, cwd=tmp)
        sh("git", "commit", "-qm", "squash", cwd=tmp)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/%s" % ib, cwd=tmp)
        sh("git", "worktree", "remove", "--force", tmp)
    if spec.get("push_unrelated"):
        ib = top["ib"]
        tmp = wt + ".other"
        sh("git", "worktree", "add", "-q", "--detach", tmp, "origin/%s" % ib)
        with open(os.path.join(tmp, "unrelated.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        sh("git", "add", "-A", cwd=tmp)
        sh("git", "commit", "-qm", "unrelated", cwd=tmp)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/%s" % ib, cwd=tmp)
        sh("git", "worktree", "remove", "--force", tmp)
    existing = json.loads(forge(top, "pr_list", "--head", branch, "--state", "all", "--json",
                                "number,url,state"))
    if existing:
        url = existing[0]["url"]
    else:
        created = forge(top, "pr_create", "--base", top["ib"], "--head", branch, "--title",
                        "%s: thing" % REQ, "--body", "body", "--draft")
        url = [ln for ln in created.splitlines() if ln.startswith("url=")][0][4:]
    number = int(url.rsplit("/", 1)[1])
    repos[top["repoId"]].update({"prUrl": url, "prNumber": number})
    forge(top, "pr_ready", str(number))
    if spec.get("merge_itself"):
        forge(top, "pr_merge", str(number), "--squash")
    status = spec.get("status", "awaiting_approval")
    state.update({"currentPhase": 8, "completedPhases": list(range(8))})
    if status:
        state["status"] = status
    if status == "awaiting_approval":
        state["approval"] = dict({"action": "merge", "repos": [top["repoId"]], "prs": [url],
                                  "deploy": False, "requestedAt": "now"}, **spec.get("approval", {}))
    if spec.get("blockers"):
        state["blockers"] = spec["blockers"]
    if spec.get("state_extra"):
        state.update(spec["state_extra"])
    write_state(wt, spec_dir, state)
    for path, body in spec.get("plant_late", {}).items():
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(path, 0o755)
    if spec.get("sleep"):
        time.sleep(spec["sleep"])
    claim = spec.get("claim", status or "failed")
    text = spec.get("text", "Terminal state: %s\n\nFindings: none." % claim)
    result(text, spec)
    raise SystemExit(spec.get("exit", 0))


def close_out(top, spec, argv, prompt):
    close = spec.get("closeout", {})
    with open(os.path.join(HOME, "closeout-argv-%s.json" % REQ), "w", encoding="utf-8") as fh:
        json.dump(argv, fh)
    with open(os.path.join(HOME, "closeout-prompt-%s.txt" % REQ), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    wt = os.getcwd()
    spec_dir = top["specDirs"][REQ]
    planted = os.path.join(wt, ".claude", "settings.json")
    if os.path.exists(planted):
        with open(os.path.join(HOME, "closeout-saw-settings"), "w", encoding="utf-8"):
            pass
    if close.get("crash"):
        raise SystemExit(1)
    if close.get("sleep"):
        time.sleep(close["sleep"])
    files = close.get("files")
    if files is None:
        lesson = os.path.join(".adlc", "knowledge", "lessons", "LESSON-9001-thing.md")
        files = {lesson: top["lesson"]}
    for path, body in files.items():
        os.makedirs(os.path.dirname(os.path.join(wt, path)), exist_ok=True)
        with open(os.path.join(wt, path), "w", encoding="utf-8") as fh:
            fh.write(body)
    branch = sh("git", "branch", "--show-current")
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "chore(%s): close-out" % REQ)
    sh("git", "push", "-q", "-u", "origin", branch)
    created = forge(top, "pr_create", "--base", top["ib"], "--head", branch, "--title", "close-out",
                    "--body", "b")
    url = [ln for ln in created.splitlines() if ln.startswith("url=")][0][4:]
    primary_state = os.path.join(top["primary"], spec_dir, "pipeline-state.json")
    with open(primary_state, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc.update({"completed": True, "currentPhase": 8,
                "completedPhases": sorted(set(doc.get("completedPhases", []) + [8])),
                "closeOut": {"status": "ok", "at": "now"}})
    doc.setdefault("phaseHistory", []).append({"phase": 8, "name": "Wrapup"})
    with open(primary_state, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    result("Terminal state: closed-out\nChore PR: %s" % url, spec)
    raise SystemExit(0)


def main():
    argv = sys.argv[1:]
    top = scenario()
    if "--help" in argv:
        spec = top.get("help", "--setting-sources <s>\n--settings <f>\n--strict-mcp-config\n")
        print(spec)
        return 0
    prompt = sys.stdin.read()
    spec = top["reqs"].get(REQ, {})
    with open(os.path.join(HOME, "argv-%s.json" % REQ), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")
    if "--resume" in argv:
        close_out(top, spec, argv, prompt)
    if "OPERATOR ANSWER" in prompt and spec.get("after_answer"):
        spec = dict(spec, **spec["after_answer"])
    first_launch(top, spec, prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
