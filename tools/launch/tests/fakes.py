"""Fake ``claude`` and ``gh`` executables for the quickstart e2e tests (REQ-672 TASK-281).

Named without ``test_`` so pytest does not collect it; the test files import it.

Each fake is a Python script run by the interpreter running the tests. Every call appends
one JSON line to ``<state>/claude.log`` or ``<state>/gh.log``: its argv, the NAMES of its
environment variables (never a value), its ``HOME`` and its working directory. A test
reads that log to show the fake, and nothing else, answered.

The fake ``claude`` acts like the CLI for the calls the quickstart makes, and like a model
that does what each prompt asks: ``plugin marketplace add`` copies the toolkit's
``examples/`` to the marketplace clone's place under the sandbox ``HOME`` (where step 3
reads ``new-project.sh``), ``/adlc:init`` writes ``.adlc/context/``, the answer to it
commits and pushes, ``/adlc:spec`` writes a REQ, and ``/adlc:proceed`` merges a PR in the
fake ``gh``'s state and writes a lesson. ``omit=<outcome>`` leaves one of
:data:`OMITTABLE` out, ``no_entry`` says ``NO_ENTRY:`` in place of the lesson, and
``escalate`` pushes the spec to ``origin/main`` rewritten to the full lane, as a merged
escalation leaves it, and ``lose_origin`` moves the throwaway repo's bare copy away after
a turn, so the driver's fetch fails. The switches are written to a config file beside the fakes, not
read from the environment: the driver passes no variable outside its allowlist, which is
what the tests prove.

No network: the marketplace call also points ``https://github.com/`` at a local directory
of bare repositories and forbids every git transport but ``file``.
"""
import json
import os
import shutil
import sys

import quickstart_check as qc

#: What a fake ``claude`` can be told to leave out: each BR-9 outcome, and the setup push.
OMITTABLE = qc.OUTCOMES + (qc.SETUP_PUSHED,)
MARKETPLACE = "adlc-toolkit"
REQ_DIR = "REQ-001-greet-name"
#: Binaries no test may reach a real copy of.
BANNED = ("gh", "claude", "codex", "asciinema", "agg")
#: Where the wrapup's ``NO_ENTRY:`` line goes: the final result of ``/adlc:proceed``'s
#: turn, an earlier assistant message of that turn, or only the output of the step before.
NO_ENTRY_PLACES = ("result", "assistant", "earlier-step")
#: What a hanging fake writes under its state directory: ``<pid> <process group> <child>``,
#: the last a ``sleep`` it started, in its group.
HANG_PID = "hang.pid"
#: The turns after which ``lose_origin`` moves the throwaway repo's bare copy away: step 6's
#: answer (after its push) or ``/adlc:proceed``.
LOSE_ORIGIN_AFTER = ("answer", "proceed")

CLAUDE = r'''
import json
import os
import shutil
import subprocess
import sys
import time

with open(@CONFIG@, encoding="utf-8") as handle:
    CONFIG = json.load(handle)
STATE = CONFIG["state"]
HARNESS = "." + "claude"
REDIRECT = """[url "file://%s/"]
	insteadOf = https://github.com/
[protocol]
	allow = never
[protocol "file"]
	allow = always
"""
SPEC = """---
id: REQ-001
title: "Greet a name"
status: draft
lane: "%s"
---

## Description

Add a --name option to greet.sh.
"""
VALUED = ("-p", "--session-id", "--resume", "--output-format", "--max-budget-usd",
          "--permission-mode", "--allowedTools", "--model")
NO_ENTRY_LINE = "NO_ENTRY: nothing transferable came out of this run"
#: Assistant messages a turn prints before its final one.
EARLIER = []


def log():
    entry = {"argv": sys.argv[1:], "env": sorted(os.environ), "home": os.environ.get("HOME"),
             "cwd": os.getcwd()}
    with open(os.path.join(STATE, "claude.log"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def fail(message, code=1):
    sys.stderr.write("fake claude: %s\n" % message)
    sys.exit(code)


def omitted(outcome):
    return CONFIG.get("omit") == outcome


def plugins(*parts):
    return os.path.join(os.environ["HOME"], HARNESS, "plugins", *parts)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def git(*args):
    return subprocess.run(["git"] + list(args), check=True, stdout=subprocess.PIPE,
                          universal_newlines=True).stdout.strip()


def plugin(args):
    if args[:2] == ["marketplace", "add"] and len(args) == 3:
        shutil.copytree(CONFIG["examples"], plugins("marketplaces", CONFIG["marketplace"],
                                                    "examples"))
        with open(os.path.join(os.environ["HOME"], ".gitconfig"), "a", encoding="utf-8") as handle:
            handle.write(REDIRECT % CONFIG["remote_base"])
        print("Successfully added marketplace: %s" % CONFIG["marketplace"])
    elif args[:1] == ["install"] and len(args) == 2:
        if not omitted("plugin-installed"):
            write(plugins("installed.json"), json.dumps(
                {"id": args[1], "version": "0.0.0-fake", "enabled": True, "scope": "user"}))
        print("Successfully installed plugin: %s" % args[1])
    elif args == ["list", "--json"]:
        entries = []
        if os.path.exists(plugins("installed.json")):
            with open(plugins("installed.json"), encoding="utf-8") as handle:
                entries.append(json.load(handle))
        print(json.dumps(entries))
    else:
        fail("unexpected plugin call %r" % args, 3)


def options(args):
    found, rest = {}, list(args)
    while rest:
        flag = rest.pop(0)
        if flag == "--verbose":
            found[flag] = True
        elif flag in VALUED and rest:
            found[flag] = rest.pop(0)
        else:
            fail("unexpected argument %r" % flag, 2)
    return found


def record_pr(branch):
    url = git("config", "--get", "remote.origin.url")
    repo = url.replace("https://github.com/", "", 1)
    repo = repo[:-4] if repo.endswith(".git") else repo
    path = os.path.join(STATE, "gh-prs.json")
    prs = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    prs.append({"repo": repo, "number": len(prs) + 1, "headRefName": branch, "state": "MERGED"})
    write(path, json.dumps(prs))


def escalate_on_main():
    """Push the spec to origin/main as a merged escalation leaves it; the project's own
    checkout keeps the lite copy."""
    clone = os.path.join(STATE, "escalated")
    git("clone", "-q", "-b", "main", git("config", "--get", "remote.origin.url"), clone)
    spec = (SPEC % "full").replace('lane: "full"\n', 'lane: "full"\nlane_escalated: '
                                   "'2026-11-23 - max_files: 4 files > 3'\n")
    write(os.path.join(clone, ".adlc", "specs", CONFIG["req_dir"], "requirement.md"), spec)
    git("-C", clone, "add", "-A")
    git("-C", clone, "commit", "-q", "-m", "chore: escalate to the full lane")
    git("-C", clone, "push", "-q", "origin", "HEAD:main")


def lose_origin(after):
    """Move the bare repository origin names out of the way once the ``after`` turn is
    done, so origin points at a path that does not exist and a later fetch fails."""
    if CONFIG.get("lose_origin") != after:
        return
    name = git("config", "--get", "remote.origin.url").replace("https://github.com/", "", 1)
    bare = os.path.join(CONFIG["remote_base"], name if name.endswith(".git") else name + ".git")
    os.rename(bare, bare + ".gone")


def act(prompt, first, resumed):
    cwd = os.getcwd()
    if resumed:
        if first == "/adlc:init" and not omitted("setup-pushed"):
            git("add", "-A")
            if git("status", "--porcelain"):
                git("commit", "-q", "-m", "chore: adlc init")
            git("push", "-q", "origin", "main")
        lose_origin("answer")
        return "Done: the setup is committed and pushed to main.", True
    if prompt == "/adlc:init":
        if not omitted("adlc-scaffold"):
            for name in ("project-overview.md", "architecture.md", "conventions.md"):
                write(os.path.join(cwd, ".adlc", "context", name), "# %s\n" % name)
        return ("I read %s/README.md. Confirm its name, purpose, stack, scope and layout?"
                % cwd), True
    if prompt.startswith("/adlc:spec "):
        lane = "full" if omitted("lite-req") else "lite"
        write(os.path.join(cwd, ".adlc", "specs", CONFIG["req_dir"], "requirement.md"),
              SPEC % lane)
        lines = ["Lane: %s (triaged)" % lane, "Next: /proceed REQ-001"]
        if CONFIG.get("no_entry") == "earlier-step":
            lines.insert(1, NO_ENTRY_LINE)
        return "\n".join(lines), True
    if prompt.startswith("/adlc:proceed "):
        req = prompt.split()[1]
        specs = os.path.join(cwd, ".adlc", "specs")
        if not os.path.isdir(specs) or not [n for n in os.listdir(specs) if n.startswith(req + "-")]:
            return "There is no requirement %s in .adlc/specs/." % req, False
        branch = "feat/" + CONFIG["req_dir"]
        if not omitted("pr-merged"):
            record_pr(branch)
        if CONFIG.get("escalate"):
            escalate_on_main()
        lines = ["merged PR #1 from %s" % branch]
        if CONFIG.get("no_entry") == "result":
            lines.append(NO_ENTRY_LINE)
        elif CONFIG.get("no_entry") == "assistant":
            EARLIER.append("Wrapup is done.\n\n### Lessons captured\n- " + NO_ENTRY_LINE)
        elif not CONFIG.get("no_entry") and not omitted("lesson-or-no-entry"):
            write(os.path.join(cwd, ".adlc", "knowledge", "lessons", "LESSON-001-greet-name.md"),
                  "---\nid: LESSON-001\n---\n\n## Lesson\n\nA lesson.\n")
        lose_origin("proceed")
        return "\n".join(lines), True
    return "fake claude has no scripted reply to that prompt", True


def headless(args):
    found = options(args)
    prompt = found.get("-p") or fail("no prompt after -p")
    if found.get("--output-format") != "stream-json" or "--verbose" not in found:
        fail("--output-format stream-json needs --verbose")
    if found.get("--permission-mode") != "acceptEdits":
        fail("expected --permission-mode acceptEdits")
    for flag in ("--max-budget-usd", "--allowedTools"):
        if flag not in found:
            fail("missing %s" % flag)
    if ("--session-id" in found) == ("--resume" in found):
        fail("give exactly one of --session-id and --resume")
    session = found.get("--session-id") or found["--resume"]
    path = os.path.join(STATE, "sessions", session)
    if "--resume" in found:
        if not os.path.exists(path):
            fail("No conversation found with session ID: %s" % session)
        first = open(path, encoding="utf-8").read()
    else:
        if os.path.exists(path):
            fail("Session ID %s is already in use" % session)
        write(path, prompt)
        first = prompt
    text, ok = act(prompt, first, "--resume" in found)
    said = [{"type": "assistant", "session_id": session, "message": {
        "role": "assistant", "content": [{"type": "text", "text": note}]}}
        for note in EARLIER + [text]]
    for event in (
            [{"type": "system", "subtype": "init", "session_id": session, "cwd": os.getcwd()}]
            + said + [{"type": "result", "subtype": "success" if ok else "error_during_execution",
                       "is_error": not ok, "result": text, "session_id": session}]):
        print(json.dumps(event))


log()
ARGS = sys.argv[1:]
if CONFIG.get("hang") and " ".join(ARGS).startswith(CONFIG["hang"]):
    child = subprocess.Popen(["/bin/sleep", "600"])
    write(os.path.join(STATE, CONFIG["hang_pid"]),
          "%d %d %d" % (os.getpid(), os.getpgid(0), child.pid))
    time.sleep(600)
if ARGS[:1] == ["plugin"]:
    plugin(ARGS[1:])
elif ARGS[:1] == ["-p"]:
    headless(ARGS)
else:
    fail("unexpected call %r" % ARGS, 3)
'''

GH = r'''
import json
import os
import sys

with open(@CONFIG@, encoding="utf-8") as handle:
    STATE = json.load(handle)["state"]
ARGS = sys.argv[1:]
with open(os.path.join(STATE, "gh.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": ARGS, "env": sorted(os.environ),
                             "home": os.environ.get("HOME"), "cwd": os.getcwd()}) + "\n")
if ARGS[:2] == ["auth", "status"]:
    sys.exit(0)
if ARGS[:2] == ["auth", "git-credential"]:
    sys.stdin.read()
    sys.exit(0)
if ARGS[:2] == ["pr", "list"] and len(ARGS) % 2 == 0:
    opts = dict(zip(ARGS[2::2], ARGS[3::2]))
    if "--repo" in opts and "--json" in opts:
        path = os.path.join(STATE, "gh-prs.json")
        prs = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
        fields = opts["--json"].split(",")
        state = opts.get("--state", "open").upper()
        print(json.dumps([{f: pr[f] for f in fields if f in pr} for pr in prs
                          if pr["repo"] == opts["--repo"] and pr["state"] == state]))
        sys.exit(0)
sys.stderr.write("fake gh: unexpected call: %s\n" % " ".join(ARGS))
sys.exit(3)
'''


def _install(path, source, config):
    config_path = path + ".config.json"
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!%s\n" % sys.executable + source.replace("@CONFIG@", repr(config_path)))
    os.chmod(path, 0o755)
    return path


def write_fake_claude(bin_dir, state_dir, examples, remote_base, omit=None, no_entry=None,
                      escalate=False, hang=None, lose_origin=None):
    """Write ``<bin_dir>/claude``. ``remote_base`` holds ``OWNER/NAME.git`` bare repos.

    ``omit`` leaves one of :data:`OMITTABLE` out. ``no_entry``, one of
    :data:`NO_ENTRY_PLACES`, writes no lesson and puts the ``NO_ENTRY:`` line there.
    ``escalate`` has ``/adlc:proceed`` push the spec to ``origin/main`` with
    ``lane: "full"`` and ``lane_escalated``. ``hang`` is the start of an argv (the words
    after ``claude``) the fake sleeps on, after writing :data:`HANG_PID`.
    ``lose_origin``, one of :data:`LOSE_ORIGIN_AFTER`, moves the bare repo origin names
    away when that turn is done, so every later ``git fetch origin`` fails.
    """
    if omit is not None and omit not in OMITTABLE:
        raise ValueError("omit must be one of %s" % ", ".join(OMITTABLE))
    if no_entry is not None and no_entry not in NO_ENTRY_PLACES:
        raise ValueError("no_entry must be one of %s" % ", ".join(NO_ENTRY_PLACES))
    if lose_origin is not None and lose_origin not in LOSE_ORIGIN_AFTER:
        raise ValueError("lose_origin must be one of %s" % ", ".join(LOSE_ORIGIN_AFTER))
    os.makedirs(os.path.join(str(state_dir), "sessions"), exist_ok=True)
    return _install(os.path.join(str(bin_dir), "claude"), CLAUDE, {
        "state": str(state_dir), "examples": str(examples), "remote_base": str(remote_base),
        "marketplace": MARKETPLACE, "req_dir": REQ_DIR, "omit": omit, "no_entry": no_entry,
        "escalate": escalate, "hang": hang, "hang_pid": HANG_PID,
        "lose_origin": lose_origin})


def write_fake_gh(bin_dir, state_dir):
    """Write ``<bin_dir>/gh``: ``auth status``, ``auth git-credential`` and ``pr list``."""
    os.makedirs(str(state_dir), exist_ok=True)
    return _install(os.path.join(str(bin_dir), "gh"), GH, {"state": str(state_dir)})


def read_log(state_dir, name):
    """The calls the fake ``name`` logged, oldest first."""
    path = os.path.join(str(state_dir), name + ".log")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def offline_path(fake_bin, mirror_root):
    """``fake_bin`` then ``/usr/bin:/bin``, each of those two that holds a :data:`BANNED`
    name replaced by a mirror without it (``tools/adlc/tests/exec_helpers.py``
    ``offline_path`` is the precedent)."""
    dirs = [str(fake_bin)]
    for n, folder in enumerate(("/usr/bin", "/bin")):
        entries = os.listdir(folder)
        if not set(BANNED) & set(entries):
            dirs.append(folder)
            continue
        mirror = os.path.join(str(mirror_root), str(n))
        os.makedirs(mirror)
        for entry in entries:
            if entry not in BANNED:
                os.symlink(os.path.join(folder, entry), os.path.join(mirror, entry))
        dirs.append(mirror)
    path = os.pathsep.join(dirs)
    for name in BANNED:
        found = shutil.which(name, path=path)
        assert found is None or os.path.dirname(found) == str(fake_bin), found
    return path
