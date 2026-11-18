#!/usr/bin/env python3
"""A headless harness the exec engine can launch (REQ-659 BR-18, REQ-662 ADR-10).

Stands in for the adapter's binary on PATH. It reads `$HOME/.exec-scenario.json`, because
the engine hands a child only the adapter's variables, and acts out a run: commit, push,
open a PR, write `pipeline-state.json`, print the harness's output. Each scenario key changes
one behaviour, so a fixture states what a misbehaving model does and nothing else.

Its profile is chosen by the name it is installed under, which the wrapper passes in
``EXEC_FAKE_AS`` (``${0##*/}``; ``claude`` when unset):

* ``claude``: ``-p --output-format json``, one JSON result object on stdout, ``--resume <id>``.
* ``jsonl`` (installed as ``codex``, or as the Codex-shaped fixture's ``fake-exec-file``):
  ``exec [--json] --sandbox <mode> -C <dir> -o <file> [-]`` and
  ``exec resume [--json] -o <file> <session id> [-]``. Under ``--json`` it prints JSONL events
  (``thread.started``, an ``item.completed`` per command it ran, ``turn.completed``) in the
  shape the probe double prints for codex (``fake_harness_impl.emit``; a test holds the two
  equal); without ``--json`` the final message is plain text on stdout and the session id goes
  to stderr, as the real CLI does (LESSON-869). The last message goes to the ``-o`` file. An
  option it does not know is a usage error, exit 2, unless the scenario's ``unknown_flags`` is
  ``record``: then it and everything after it are recorded and ignored.

Both profiles read the whole prompt from stdin, and fail loudly (exit 86 and
``$HOME/exec-fake-forbidden-<REQ>.txt``) when the argv holds any spelling in the scenario's
``forbidden`` list, matched token by token as a CLI parses it.

Scenario keys per REQ, besides REQ-659's: ``stderr`` (text written to stderr at exit),
``commands`` (shell commands run in the working copy mid-run; the jsonl profile reports each
as a ``command_execution`` item), and for the jsonl profile ``refused`` (commands the harness
refuses: its rejection line on stderr and no item), ``stream`` (``no-terminal``: no
``turn.completed``; ``cut``: the last line cut short with no newline; ``not-json``: plain
text) and ``no_last_message`` (no ``-o`` file).
"""

import json
import os
import subprocess
import sys
import time

HOME = os.environ["HOME"]
REQ = os.environ.get("ADLC_EXEC_RUN", "")
#: The profile each installed name speaks.
PROFILES = {"claude": "claude", "codex": "jsonl", "fake-exec-file": "jsonl"}
#: What this launch is: the profile, its parsed options, the commands it ran.
RUN = {"profile": "claude", "opts": {}, "records": []}
#: codex-cli 0.166.0's line for a command a `forbidden` rule rejects (BUG-282), as the probe
#: double prints it.
REJECTED = ("ERROR codex_core::tools::router: error=exec_command failed: CreateProcess "
            "{ message: \"Rejected(\\\"`/bin/zsh -lc '%s'` rejected: policy forbids commands "
            "starting with `%s`\\\")\" }\n")
#: The jsonl profile's options that take a value, by the key its parse records each under;
#: ``--json`` is its one boolean. ``exec resume`` takes no ``--sandbox`` and no ``-C``
#: (REQ-662 ADR-7).
JSONL_VALUE = {"--sandbox": "sandbox", "-C": "cd", "-o": "last", "--model": "model",
               "-m": "model"}
JSONL_RESUME_REFUSES = ("--sandbox", "-C")


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
    """The harness's output for this launch, in its profile's format, then any scripted
    stderr."""
    if RUN["profile"] == "jsonl":
        jsonl_result(text, spec, spec.get("sid", sid))
    else:
        doc = {"type": "result", "session_id": spec.get("sid", sid), "is_error": False,
               "num_turns": 7, "result": text, "total_cost_usd": 0,
               "permission_denials": spec.get("denials", [])}
        if spec.get("no_session"):
            doc.pop("session_id")
        if spec.get("is_error"):
            doc["is_error"] = True
        print(json.dumps(doc))
    if spec.get("stderr"):
        sys.stderr.write(spec["stderr"])
    sys.stdout.flush()


def jsonl_result(text, spec, sid):
    """codex exec's output: JSONL events on stdout under --json, plain text without it, and
    the last message in the -o file."""
    opts = RUN["opts"]
    for command in spec.get("refused", []):
        sys.stderr.write(REJECTED % (command, command))
    if not opts.get("json"):
        print(text)
        sys.stderr.write("session id: %s\n" % sid)
        for rec in RUN["records"]:
            sys.stderr.write("exec\n%s in %s\n%s\n" % (rec["command"], os.getcwd(),
                                                       rec["output"]))
    elif spec.get("stream") == "not-json":
        sys.stdout.write("Reading prompt from stdin...\n%s\n" % text)
    else:
        events = [] if spec.get("no_session") else [{"type": "thread.started",
                                                      "thread_id": sid}]
        for rec in RUN["records"]:
            events.append({"type": "item.completed", "item": {
                "type": "command_execution", "command": rec["command"],
                "aggregated_output": rec["output"]}})
        if spec.get("stream") != "no-terminal":
            events.append({"type": "turn.completed"})
        lines = [json.dumps(event) for event in events]
        if spec.get("stream") == "cut" and lines:
            sys.stdout.write("".join(line + "\n" for line in lines[:-1]))
            sys.stdout.write(lines[-1][:len(lines[-1]) // 2])
        else:
            sys.stdout.write("".join(line + "\n" for line in lines))
    if opts.get("last") and not spec.get("no_last_message"):
        with open(opts["last"], "w", encoding="utf-8") as fh:
            fh.write(text + "\n" if text else "")


def run_commands(spec, wt):
    """Each scripted command, run in the working copy as the model would."""
    for command in spec.get("commands", []):
        res = subprocess.run(["sh", "-c", command], cwd=wt, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, universal_newlines=True)
        RUN["records"].append({"command": command, "output": res.stdout,
                               "exit_code": res.returncode})


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
    run_commands(spec, wt)
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


def forbidden_in(argv, forbidden):
    """The first forbidden spelling in ``argv``, token by token: ``--flag=value`` is split
    first, and a two-word entry matches two adjacent tokens. The fake's own reading, written
    here: it imports nothing from the engine it stands in for."""
    tokens = []
    for tok in argv:
        if tok.startswith("-") and "=" in tok:
            tokens += tok.split("=", 1)
        else:
            tokens.append(tok)
    for bad in forbidden:
        parts = bad.split()
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i:i + len(parts)] == parts:
                return bad
    return None


def usage(message):
    sys.stderr.write("error: %s\n" % message)
    raise SystemExit(2)


def parse_jsonl(argv, top):
    """codex exec's grammar: ``exec [--json] [--sandbox m] [-C d] [-o f] [-m x] [-]`` and
    ``exec resume [--json] [-o f] <session id> [-]``."""
    if not argv or argv[0] != "exec":
        usage("the fake codex only knows `exec`")
    args = argv[1:]
    opts = {"resume": False, "json": False, "positional": [], "unknown": []}
    if args and args[0] == "resume":
        opts["resume"] = True
        args = args[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in JSONL_VALUE:
            if opts["resume"] and a in JSONL_RESUME_REFUSES:
                usage("unexpected argument '%s' found: `exec resume` takes no %s" % (a, a))
            if i + 1 >= len(args):
                usage("option '%s' argument missing" % a)
            opts[JSONL_VALUE[a]] = args[i + 1]
            i += 2
        elif a == "--json":
            opts["json"] = True
            i += 1
        elif a.startswith("-") and a != "-":
            if top.get("unknown_flags") != "record":
                usage("unexpected argument '%s' found" % a)
            opts["unknown"] = args[i:]
            break
        else:
            opts["positional"].append(a)
            i += 1
    if opts["resume"]:
        if not opts["positional"]:
            usage("`exec resume` needs a session id")
        opts["session"] = opts["positional"][0]
    prompt_args = opts["positional"][1 if opts["resume"] else 0:]
    if prompt_args not in ([], ["-"]):
        usage("a prompt argument %r: this fake reads its prompt from stdin" % prompt_args)
    return opts


def main():
    installed = os.environ.pop("EXEC_FAKE_AS", "") or "claude"
    if installed not in PROFILES:
        sys.stderr.write("exec fake: no profile for the name %r\n" % installed)
        return 70
    RUN["profile"] = PROFILES[installed]
    argv = sys.argv[1:]
    top = scenario()
    if "--help" in argv:
        default = ("--setting-sources <s>\n--settings <f>\n--strict-mcp-config\n"
                   if RUN["profile"] == "claude" else
                   "Usage: codex exec [OPTIONS] [PROMPT]\n  --json\n  --sandbox <MODE>\n"
                   "  -C, --cd <DIR>\n  -o, --output-last-message <FILE>\n")
        print(top.get("help", default))
        return 0
    bad = forbidden_in(argv, top.get("forbidden", []))
    if bad:
        with open(os.path.join(HOME, "exec-fake-forbidden-%s.txt" % REQ), "a",
                  encoding="utf-8") as fh:
            fh.write(json.dumps({"flag": bad, "argv": argv}) + "\n")
        sys.stderr.write("EXEC FAKE: launched with the forbidden flag %s: %s\n"
                         % (bad, json.dumps(argv)))
        return 86
    if RUN["profile"] == "jsonl":
        RUN["opts"] = parse_jsonl(argv, top)
        if RUN["opts"].get("cd"):
            os.chdir(RUN["opts"]["cd"])
    prompt = sys.stdin.read()
    spec = top["reqs"].get(REQ, {})
    with open(os.path.join(HOME, "argv-%s.json" % REQ), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")
    if RUN["profile"] == "jsonl":
        with open(os.path.join(HOME, "launch-%s.json" % REQ), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"installed_as": installed, "argv": argv, "opts": RUN["opts"],
                                 "cwd": os.getcwd(), "prompt_lines": len(prompt.splitlines()),
                                 "env": dict(os.environ)}) + "\n")
    resume = RUN["opts"]["resume"] if RUN["profile"] == "jsonl" else "--resume" in argv
    if resume:
        close_out(top, spec, argv, prompt)
    if "OPERATOR ANSWER" in prompt and spec.get("after_answer"):
        spec = dict(spec, **spec["after_answer"])
    first_launch(top, spec, prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
