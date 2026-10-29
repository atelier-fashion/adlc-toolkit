#!/usr/bin/env python3
"""The fake harness behind ``fake-harness`` (REQ-664 BR-14, architecture ADR-2).

It is invoked as ``fake_harness_impl.py <argv0> <args...>`` and behaves like the
named harness's headless CLI, closely enough to exercise every verdict path of
``adlc harness probe`` without a model:

* it parses that harness's flags and refuses an unknown one, as a CLI would;
* it honours trust the way the real harness is documented to — codex and gemini
  read the user-level trust entry, copilot and cursor need the flag — and reads
  the project-local config the probe wrote, in that harness's own spelling;
* it runs session-start hooks and keeps the context they add;
* it performs or refuses each command the prompt asks for, per
  ``FAKE_HARNESS_SCENARIO`` and ``FAKE_HARNESS_FLAGS``;
* it writes a session record under the profile's transcript root (cursor: at an
  arbitrary path it reports to its sessionStart hooks), and prints its output in
  that harness's format.

Scenarios: ``perform`` (run what the config allows and no deny matches; a plain
deny also blocks its ``git -C`` form; reply with every nonce reversed),
``refuse`` (exit 0, no side effect, the reversed nonce only on the two rows that
ask for an action and then a nonce reply), ``refuse-silent`` (exit 0, no side
effect, no nonce), ``exit3``, ``hang``, ``runs-all`` (run every asked command
whatever the config says), ``no-witness`` (``perform`` but refuse the witness),
``abort-on-deny`` (``perform`` but exit 53 with no reply when a deny matches).

Flags modify a scenario: ``claim-only``, ``main-only``, ``needs-writable-roots``,
``no-hooks``, ``bare-nonce``, ``nonce-in-tool``, ``nonce-beyond-cap``,
``prompt-echo``, ``no-substitute``, ``literal-dollar``, ``leak``,
``mutate-trust-file``, ``mutate-policy-file``, ``stale-writer``.

Under the no-side-effect scenarios the fake still writes its session record; on
cursor that record is delivered by passing its ``transcript_path`` to the probe's
transcript-recorder hook, the one hook it runs there.
"""

import datetime
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid

HARNESS_OF = {"claude": "claude", "copilot": "copilot", "codex": "codex",
              "gemini": "gemini", "agent": "cursor", "cursor-agent": "cursor"}
SCENARIO = os.environ.get("FAKE_HARNESS_SCENARIO", "perform")
FLAGS = {f for f in os.environ.get("FAKE_HARNESS_FLAGS", "").split(",") if f}
HOME = os.path.expanduser("~")
PERFORMING = SCENARIO in ("perform", "runs-all", "no-witness", "abort-on-deny")

TAKES_VALUE = {
    "claude": {"--output-format", "--setting-sources"},
    "copilot": {"-p", "--allow-tool", "--deny-tool"},
    "codex": {"--sandbox", "-C", "-o"},
    "gemini": {"-p", "--output-format"},
    "cursor": {"--output-format", "--workspace"},
}
BOOLEAN = {
    "claude": {"-p"},
    "copilot": {"-s", "--no-ask-user", "--trust-folder"},
    "codex": set(),
    "gemini": set(),
    "cursor": {"-p", "--trust"},
}


def log(record):
    path = os.environ.get("FAKE_HARNESS_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def read_json(path):
    text = read(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# --- arguments ---------------------------------------------------------------

def parse(harness, args):
    opts = {"prompt": None, "cwd": os.getcwd(), "trust": False, "allow": [], "deny": [],
            "lastmsg": None}
    if harness == "codex":
        if not args or args[0] != "exec":
            sys.stderr.write("error: the fake codex only knows `exec`\n")
            sys.exit(2)
        args = args[1:]
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in TAKES_VALUE[harness]:
            if i + 1 >= len(args):
                sys.stderr.write("error: option '%s' argument missing\n" % a)
                sys.exit(2)
            value = args[i + 1]
            i += 2
            if a == "-p":
                opts["prompt"] = value
            elif a == "--allow-tool":
                opts["allow"].append(value)
            elif a == "--deny-tool":
                opts["deny"].append(value)
            elif a in ("-C", "--workspace"):
                opts["cwd"] = value
            elif a == "-o":
                opts["lastmsg"] = value
            continue
        if a in BOOLEAN[harness]:
            if a in ("--trust-folder", "--trust"):
                opts["trust"] = True
            i += 1
            continue
        if a.startswith("-") and a != "-":
            sys.stderr.write("error: unknown option '%s'\n" % a)
            sys.exit(2)
        positional.append(a)
        i += 1
    if positional:
        opts["prompt"] = positional[0]
    if opts["prompt"] in (None, "", "-"):
        opts["prompt"] = sys.stdin.read()
        opts["stdin"] = True
    return opts


# --- trust and config -------------------------------------------------------

def trusted(harness, opts, cwd):
    real = os.path.realpath(cwd)
    if harness == "claude":
        return True
    if harness in ("copilot", "cursor"):
        return opts["trust"]
    if harness == "codex":
        text = read(os.path.join(HOME, ".codex", "config.toml")) or ""
        return bool(re.search(r'\[projects\."%s"\]\s*\ntrust_level = "trusted"'
                              % re.escape(real), text))
    data = read_json(os.path.join(HOME, ".gemini", "trustedFolders.json")) or {}
    return isinstance(data, dict) and data.get(real) == "TRUST_FOLDER"


def paren(entry, head):
    """`Head(x:*)` -> (x, prefix); `Head(x)` -> (x, exact unless prefix-only)."""
    m = re.match(r"^%s\((.*)\)$" % re.escape(head), entry, re.S)
    if not m:
        return None
    text = m.group(1)
    if text.endswith(":*"):
        return (text[:-2], False)
    return (text, head in ("Bash", "shell"))


class Config:
    def __init__(self):
        self.allow, self.deny, self.hooks, self.skills = [], [], [], []
        self.tools, self.writable_roots, self.policies = set(), [], {}


def load(harness, opts, cwd, is_trusted):
    c = Config()
    if harness == "copilot":
        c.allow = [x for x in (paren(a, "shell") for a in opts["allow"]) if x]
        c.deny = [x for x in (paren(d, "shell") for d in opts["deny"]) if x]
    if harness == "gemini":
        for path in sorted(glob.glob(os.path.join(HOME, ".gemini", "policies", "*.toml"))):
            text = read(path) or ""
            c.policies[path] = text
            for block in text.split("[[rule]]")[1:]:
                prefix = re.search(r'commandPrefix = "([^"]*)"', block)
                if prefix and 'decision = "deny"' in block:
                    c.deny.append((prefix.group(1), False))
    if not is_trusted:
        return c
    if harness == "claude":
        s = read_json(os.path.join(cwd, ".claude", "settings.json")) or {}
        perms = s.get("permissions", {})
        c.allow = [x for x in (paren(a, "Bash") for a in perms.get("allow", [])) if x]
        c.deny = [x for x in (paren(d, "Bash") for d in perms.get("deny", [])) if x]
        for group in s.get("hooks", {}).get("SessionStart", []):
            c.hooks += [h["command"] for h in group.get("hooks", [])]
        c.skills = sorted(glob.glob(os.path.join(cwd, ".claude", "skills", "*", "SKILL.md")))
    elif harness == "copilot":
        for path in sorted(glob.glob(os.path.join(cwd, ".github", "hooks", "*.json"))):
            data = read_json(path) or {}
            c.hooks += [h["bash"] for h in data.get("hooks", {}).get("sessionStart", [])]
    elif harness == "codex":
        for path in sorted(glob.glob(os.path.join(cwd, ".codex", "rules", "*.rules"))):
            for m in re.finditer(r'prefix_rule\(pattern = (\[.*?\]), decision = "(\w+)"\)',
                                 read(path) or ""):
                entry = (" ".join(json.loads(m.group(1))), False)
                (c.allow if m.group(2) == "allow" else c.deny).append(entry)
        data = read_json(os.path.join(cwd, ".codex", "hooks.json")) or {}
        for group in data.get("hooks", {}).get("SessionStart", []):
            c.hooks += [h["command"] for h in group.get("hooks", [])]
        m = re.search(r"writable_roots = (\[.*\])", read(os.path.join(cwd, ".codex",
                                                                      "config.toml")) or "")
        if m:
            c.writable_roots = json.loads(m.group(1))
    elif harness == "gemini":
        s = read_json(os.path.join(cwd, ".gemini", "settings.json")) or {}
        for entry in s.get("tools", {}).get("allowed", []):
            got = paren(entry, "run_shell_command")
            if got:
                c.allow.append(got)
            else:
                c.tools.add(entry)
        for group in s.get("hooks", {}).get("SessionStart", []):
            c.hooks += [h["command"] for h in group.get("hooks", [])]
        c.skills = sorted(glob.glob(os.path.join(cwd, ".gemini", "skills", "*", "SKILL.md")))
    elif harness == "cursor":
        s = read_json(os.path.join(cwd, ".cursor", "cli.json")) or {}
        perms = s.get("permissions", {})
        c.allow = [x for x in (paren(a, "Shell") for a in perms.get("allow", [])) if x]
        c.deny = [x for x in (paren(d, "Shell") for d in perms.get("deny", [])) if x]
        data = read_json(os.path.join(cwd, ".cursor", "hooks.json")) or {}
        c.hooks = [h["command"] for h in data.get("hooks", {}).get("sessionStart", [])]
    return c


# --- deciding and running commands --------------------------------------------

def _tokens(text):
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def matches(entry, cmd, harness=None):
    text, exact = entry
    if harness == "codex":  # codex matches argv tokens, not text (prefix_rule)
        want, have = _tokens(text), _tokens(cmd)
        return bool(want) and have[:len(want)] == want
    if exact:
        return cmd == text
    return cmd == text or cmd.startswith(text + " ")


def unwrap(cmd):
    """A plain deny also blocks its `git -C <path>` form (AC-2's perform)."""
    return re.sub(r"^git -C \S+ ", "git ", cmd)


def verdict(cfg, cmd, harness):
    """'run', 'denied' or 'refused' for one command."""
    if SCENARIO == "runs-all":
        return "run"
    if not PERFORMING:
        return "refused"
    if SCENARIO == "no-witness" and "witness-" in cmd:
        return "refused"
    if any(matches(d, cmd, harness) or matches(d, unwrap(cmd), harness) for d in cfg.deny):
        return "denied"
    return "run" if any(matches(a, cmd, harness) for a in cfg.allow) else "refused"


def sh(cmd, cwd):
    proc = subprocess.run(["sh", "-c", cmd], cwd=cwd, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60)
    return proc.stdout + proc.stderr


def asked_commands(prompt, cwd, harness, cfg):
    """[(match text, command to execute)] the prompt asks for."""
    if prompt.startswith("Run this fenced block exactly as written"):
        m = re.search(r"```sh\n(.*?)```", prompt, re.S)
        fence = m.group(1) if m else ""
        return [(fence.splitlines()[0] if fence else "", fence)]
    if prompt.startswith("Commit the staged file"):
        branch = "probe-wt" if "`probe-wt`" in prompt else "main"
        return [("git commit -m probe", "git commit -q -m probe"),
                ("git push origin %s" % branch, "git push -q origin %s" % branch)]
    if prompt.startswith("/") and harness == "claude":
        return skill_commands(prompt, cfg)
    if harness == "gemini" and cfg.skills and not prompt.startswith("Run"):
        return gemini_skill(prompt, cfg)
    return [(c, c) for c in re.findall(r"[Rr]un `([^`]+)`", prompt)]


def skill_body(path):
    text = read(path) or ""
    parts = text.split("---", 2)
    return (parts[1] if len(parts) == 3 else "", parts[2] if len(parts) == 3 else text)


def skill_commands(prompt, cfg):
    words = prompt[1:].split()
    name, args = words[0], words[1:]
    for path in cfg.skills:
        if os.path.basename(os.path.dirname(path)) != name:
            continue
        _front, body = skill_body(path)
        if "literal-dollar" in FLAGS:
            body = body.replace('"$1"', "'$1'")
        elif "no-substitute" not in FLAGS:
            body = body.replace("$ARGUMENTS", " ".join(args))
            for i, value in enumerate(args, 1):
                body = body.replace("$%d" % i, value)
        m = re.search(r"```sh\n(.*?)```", body, re.S)
        if m:
            fence = m.group(1).strip()
            return [(fence, fence)]
    return []


def gemini_skill(prompt, cfg):
    ask = prompt.strip().rstrip(".").lower()
    if "activate_skill" not in cfg.tools and SCENARIO != "runs-all":
        return []
    for path in cfg.skills:
        front, body = skill_body(path)
        if ask and ask in front.lower():
            return [(c, c) for c in re.findall(r"[Rr]un `([^`]+)`", body)]
    return []


def run_command(match_text, command, cwd, cfg, harness, records, aborted):
    parts = [p.strip() for p in match_text.split("&&")]
    decisions = [verdict(cfg, p, harness) for p in parts]
    if "denied" in decisions:
        records.append({"command": command, "decision": "denied"})
        if SCENARIO == "abort-on-deny":
            aborted.append(command)
        return
    if any(d != "run" for d in decisions):
        records.append({"command": command, "decision": "refused"})
        return
    if command.startswith("git push") and "needs-writable-roots" in FLAGS and harness == "codex":
        branch = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        common = subprocess.run(["git", "-C", cwd, "rev-parse", "--path-format=absolute",
                                 "--git-common-dir"], capture_output=True, text=True).stdout
        repo = os.path.realpath(os.path.dirname(common.strip()))
        if branch != "main" and repo not in [os.path.realpath(r) for r in cfg.writable_roots]:
            records.append({"command": command, "decision": "sandbox-denied"})
            return
    if command.startswith("git") and "main-only" in FLAGS:
        branch = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        if branch != "main":
            records.append({"command": command, "decision": "skipped"})
            return
    if command.startswith("git") and "claim-only" in FLAGS:
        records.append({"command": command, "decision": "claimed", "output": "pushed"})
        return
    script = " && ".join(p for p in command.split(" && ") if not p.startswith("sleep "))
    records.append({"command": command, "decision": "run", "output": sh(script, cwd)})


# --- hooks, session records, output ------------------------------------------

def run_hooks(cfg, payload, recorder_only):
    contexts = []
    for command in cfg.hooks:
        if recorder_only and "transcript-recorder" not in command:
            continue
        proc = subprocess.run(["sh", "-c", command], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if isinstance(data, dict):
            ctx = (data.get("additionalContext") or data.get("additional_context")
                   or (data.get("hookSpecificOutput") or {}).get("additionalContext"))
            if ctx:
                contexts.append(ctx)
        elif out:
            contexts.append(out)
    return contexts


def session_path(harness, cwd, sid):
    real = os.path.realpath(cwd)
    now = datetime.datetime.now()
    if harness == "claude":
        return os.path.join(HOME, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", real),
                            sid + ".jsonl")
    if harness == "copilot":
        return os.path.join(HOME, ".copilot", "session-state", sid, "events.jsonl")
    if harness == "codex":
        return os.path.join(HOME, ".codex", "sessions", now.strftime("%Y"), now.strftime("%m"),
                            now.strftime("%d"), "rollout-%s-%s.jsonl"
                            % (now.strftime("%Y-%m-%dT%H-%M-%S"), sid))
    if harness == "gemini":
        digest = hashlib.sha256(real.encode()).hexdigest()
        return os.path.join(HOME, ".gemini", "tmp", digest, "chats",
                            "session-%s.jsonl" % now.strftime("%Y%m%d%H%M%S%f"))
    return os.path.join(HOME, ".cursor-fake-sessions", sid + ".jsonl")


def write_session(path, harness, cwd, prompt, message):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    first = {"type": "session_meta", "payload": {"cwd": os.path.realpath(cwd)}} \
        if harness == "codex" else {"type": "user", "cwd": os.path.realpath(cwd),
                                    "message": {"content": prompt}}
    records = [first, {"type": "assistant", "message": {"content": message}}]
    if harness == "codex":
        records.insert(1, {"type": "user", "message": {"content": prompt}})
    if "leak" in FLAGS:
        records.append({"type": "debug", "text": "token ghp_%s in %s/.secrets"
                        % ("z" * 36, HOME)})
    with open(path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def find_code(prompt, contexts):
    for pattern in (r"The nonce is ([a-z0-9]{8})", r"the code is ([a-z0-9]{8})"):
        m = re.search(pattern, prompt)
        if m:
            return m.group(1)
    if "session context" in prompt:
        for ctx in contexts:
            m = re.search(r"code: ([a-z0-9]{8})", ctx)
            if m:
                return m.group(1)
    return None


def compose(prompt, contexts):
    """(final message, tool-record text) for this scenario."""
    code = find_code(prompt, contexts)
    action_then_nonce = "then reply with the nonce reversed" in prompt
    if not PERFORMING:
        if SCENARIO == "refuse" and action_then_nonce and code:
            return "I will not run that. %s" % code[::-1], ""
        return "I will not run that.", ""
    if "prompt-echo" in FLAGS:
        return prompt, ""
    if not (code and "reversed" in prompt):
        return "Done.", ""
    if "bare-nonce" in FLAGS:
        return code, ""
    if "nonce-in-tool" in FLAGS:
        return "Done.", code[::-1]
    if "nonce-beyond-cap" in FLAGS:
        return "x" * 10000 + " " + code[::-1], ""
    return code[::-1], ""


def emit(harness, opts, message, tool_text, records, sid):
    leak = ""
    if "leak" in FLAGS:
        leak = "debug token sk-%s from %s/secret" % ("a" * 30, HOME)
    if harness in ("claude", "cursor"):
        out = {"type": "result", "subtype": "success", "is_error": False, "result": message,
               "session_id": sid,
               "tool_records": [{"type": "tool_result", "content": tool_text}] if tool_text
               else []}
        if leak:
            out["debug"] = leak
        print(json.dumps(out))
    elif harness == "gemini":
        out = {"response": message, "stats": {"tools": len(records)}}
        if tool_text:
            out["tool_output"] = tool_text
        if leak:
            out["debug"] = leak
        print(json.dumps(out))
    elif harness == "copilot":
        print(message)
        if tool_text or leak:
            sys.stderr.write("%s %s\n" % (tool_text, leak))
    else:  # codex: JSONL events on stdout, the last message to -o
        print(json.dumps({"type": "thread.started", "thread_id": sid}))
        for r in records:
            print(json.dumps({"type": "item.completed", "item": {
                "type": "command_execution", "command": r["command"],
                "aggregated_output": r.get("output", "") + tool_text}}))
        print(json.dumps({"type": "turn.completed", "debug": leak}))
        if opts.get("lastmsg"):
            with open(opts["lastmsg"], "w", encoding="utf-8") as fh:
                fh.write(message + "\n")


def mutate_user_files(harness):
    if "mutate-trust-file" in FLAGS:
        if harness == "codex":
            path = os.path.join(HOME, ".codex", "config.toml")
            if os.path.exists(path):
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("\n# a change the user made during the run\n")
        if harness == "gemini":
            path = os.path.join(HOME, ".gemini", "trustedFolders.json")
            data = read_json(path)
            if isinstance(data, dict):
                data["/user/added/during/run"] = "TRUST_FOLDER"
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
    if "mutate-policy-file" in FLAGS and harness == "gemini":
        for path in glob.glob(os.path.join(HOME, ".gemini", "policies", "adlc-probe-*.toml")):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n# a change the user made during the run\n")


def stale_write(prompt, cwd):
    """Leave behind what the NEXT launch's oracle reads (AC-15)."""
    m = re.search(r"(\S*)/target-l(\d\d)", prompt)
    if not m:
        return
    nxt = "l%02d" % (int(m.group(2)) + 1)
    for role in ("target", "witness"):
        path = os.path.join(m.group(1), "%s-%s" % (role, nxt))
        open(path, "w").close()
    subprocess.run(["git", "-C", cwd, "push", "-q", "origin",
                    "HEAD:refs/heads/probe-deny-%s" % nxt], capture_output=True)


def main():
    argv0, args = sys.argv[1], sys.argv[2:]
    harness = HARNESS_OF[argv0]
    if "--version" in args:
        print(os.environ.get("FAKE_HARNESS_VERSION", "fake-%s 1.0.0" % harness))
        return 0
    opts = parse(harness, args)
    cwd = opts["cwd"]
    log({"harness": harness, "argv": sys.argv[1:], "cwd": cwd, "pid": os.getpid(),
         "scenario": SCENARIO, "flags": sorted(FLAGS)})
    if SCENARIO == "exit3":
        return 3
    if SCENARIO == "hang":
        child = subprocess.Popen(["sleep", "300"])
        pidfile = os.environ.get("FAKE_HARNESS_PIDFILE")
        if pidfile:
            with open(pidfile, "a", encoding="utf-8") as fh:
                fh.write("%d\n%d\n" % (os.getpid(), child.pid))
        time.sleep(300)
        return 0
    is_trusted = trusted(harness, opts, cwd)
    cfg = load(harness, opts, cwd, is_trusted)
    sid = uuid.uuid4().hex
    transcript = session_path(harness, cwd, sid)
    payload = {"session_id": sid, "transcript_path": transcript, "cwd": cwd,
               "hook_event_name": "SessionStart"}
    contexts = []
    if PERFORMING and "no-hooks" not in FLAGS:
        contexts = run_hooks(cfg, payload, recorder_only=False)
    elif harness == "cursor":
        run_hooks(cfg, payload, recorder_only=True)
    mutate_user_files(harness)
    prompt = opts["prompt"]
    if "stale-writer" in FLAGS:
        stale_write(prompt, cwd)
    records, aborted = [], []
    for match_text, command in asked_commands(prompt, cwd, harness, cfg):
        run_command(match_text, command, cwd, cfg, harness, records, aborted)
        if aborted:
            break
    trust_file = {"codex": os.path.join(HOME, ".codex", "config.toml"),
                  "gemini": os.path.join(HOME, ".gemini", "trustedFolders.json")}.get(harness)
    log({"harness": harness, "event": "config", "trusted": is_trusted,
         "allow": cfg.allow, "deny": cfg.deny, "hooks": cfg.hooks,
         "policies": cfg.policies, "writable_roots": cfg.writable_roots,
         "trust_file": read(trust_file) if trust_file else None,
         "stdin": bool(opts.get("stdin")), "prompt": prompt, "records": records})
    message, tool_text = compose(prompt, contexts)
    write_session(transcript, harness, cwd, prompt, "" if aborted else message)
    if aborted:
        sys.stderr.write(json.dumps({"error": {"type": "FatalToolExecutionError",
                                               "message": "denied by policy: %s" % aborted[0],
                                               "code": 53}}) + "\n")
        return 53
    emit(harness, opts, message, tool_text, records, sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
