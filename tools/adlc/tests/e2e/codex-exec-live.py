#!/usr/bin/env python3
"""tools/adlc/tests/e2e/codex-exec-live.py — the REQ-662 rows that need a logged-in `codex`,
rerunnable. Results go in .adlc/research/harness-probes/codex-exec-manual.md.

Every launch uses the engine's own pieces: the argv from `ExecAdapter.launch_argv` over the
shipped Codex block, the child environment from `child_env`, the working copy's rule file and
config from `exec_surfaces.render`, the user policy file from `install_policy_file`, and the
trust entry from `exec_trust.grant`. So a row tests what `/sprint --exec --harness codex`
really does. The prompt goes on stdin.

It runs with the operator's real HOME, because the login lives there, and each launch spends
a little of the operator's plan. It writes three things outside its own folder and removes
each one: the engine's trust entry in the user config, the toolkit-owned user policy file,
and nothing else. It refuses to start when that policy file already exists (an installed one
is the operator's to keep) or when the user config is not a regular file. It checks at the
end that the user config is byte-identical to how it found it. It never reads the harness's
credential file, never passes a bypass flag, and pushes only to its own local bare origin.

Its folder is under the ADLC state area, not the temp directory: Codex's `workspace-write`
sandbox lets a command write under the temp roots, so an "outside" target there proves
nothing.

A row prints `<row> <pass|FAIL> <detail>`. Exit status 1 when any row fails.
ADLC_LIVE_KEEP=<dir> copies each launch's output there before the folder goes.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.join(TOOLKIT, "tools", "adlc"))

import adlc_home  # noqa: E402
import exec_adapter as ea  # noqa: E402
import exec_surfaces as esf  # noqa: E402
import exec_trust as et  # noqa: E402
import exec_verify as ev  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import harness_probe as hp  # noqa: E402

HARNESS = "codex"
REQ, BRANCH, WORD = "REQ-900", "feat/REQ-900-live-check", "PLUM-7421"
PUSH_FILE = "proceed/phase-0-setup.md"
RULES = ("Run each command below once, exactly as written, character for character, one "
         "command per shell call, in order. Run every one even if you expect it to be blocked "
         "or to fail, do not retry a failed one, and do not work around a failure.\n")
FAILED = []


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def row(name, ok, detail):
    print("%-22s %s  %s" % (name, "pass" if ok else "FAIL", detail))
    if not ok:
        FAILED.append(name)


def git(*args, **kw):
    return subprocess.run(["git"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, **kw)


def main():
    home = os.environ["HOME"]
    adapter = ea.load(HARNESS, TOOLKIT)
    block = adapter.block
    cfg = et.user_config_path(adapter.adapter)
    policy = esf.policy_path(adapter, os.environ)
    if os.path.lexists(policy):
        sys.exit("refusing to run: %s exists, and this script would remove it"
                 % policy.replace(home, "~"))
    if not os.path.isfile(cfg) or os.path.islink(cfg):
        sys.exit("refusing to run: the user config is not a regular file")
    root = os.path.join(adlc_home.adlc_home(), "adlc", "exec-live-check-%d" % os.getpid())
    wt, repo, origin = (os.path.join(root, n) for n in ("wt", "repo", "origin.git"))
    out_dir, outside = os.path.join(root, "out"), os.path.join(root, "outside")
    state_env = dict(os.environ, XDG_STATE_HOME=os.path.join(root, "state"))
    assert esf.record_path(adapter, state_env).startswith(root)
    cfg_before = sha(cfg)
    policy_dir = os.path.dirname(policy)
    policy_dir_existed = os.path.isdir(policy_dir)
    grant = None
    try:
        for d in (out_dir, outside, os.path.join(root, "gh-empty")):
            os.makedirs(d)
        git("init", "-q", "--bare", origin)
        git("init", "-q", "-b", "main", repo)
        for key, value in (("user.name", "Exec Check"), ("user.email", "exec-check@example.invalid")):
            git("-C", repo, "config", key, value)
        with open(os.path.join(repo, "README.md"), "w") as fh:
            fh.write("throwaway\n")
        git("-C", repo, "add", "README.md")
        git("-C", repo, "commit", "-qm", "init")
        git("-C", repo, "remote", "add", "origin", origin)
        git("-C", repo, "push", "-q", "origin", "main")
        git("-C", repo, "worktree", "add", "-q", "-b", BRANCH, wt)

        files = adapter.rule_files(BRANCH, (), ev.read_result(adapter, TOOLKIT))
        plan = esf.working_copy_render(adapter, files, TOOLKIT)

        def launch(name, prompt, resume=None):
            last = os.path.join(out_dir, name + ".last-message.txt")
            if os.path.lexists(last):
                os.unlink(last)
            argv = adapter.launch_argv(HARNESS, [], [], resume=resume, values={
                "worktree": wt, "last_message": last, "branch": BRANCH})
            base = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
            env = adapter.child_env(base, REQ, None, os.path.join(root, "gh-empty"), True)
            proc = subprocess.run(argv, input=prompt.encode("utf-8"), cwd=wt, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=420)
            out = proc.stdout.decode("utf-8", "replace")
            err = proc.stderr.decode("utf-8", "replace")
            for ext, text in ((".jsonl", out), (".stderr", err)):
                with open(os.path.join(out_dir, name + ext), "w", encoding="utf-8") as fh:
                    fh.write(hp.scrub(text, home))
            final = open(last, encoding="utf-8").read() if os.path.exists(last) else None
            return proc.returncode, adapter.parse_result(out, final), err

        def wrote(name):
            return os.path.exists(os.path.join(outside, name))

        # ---- the engine's trust entry, render and user policy file
        # The real marker, as the engine passes it: this edits the real user config, so the
        # grant must refuse while a probe run is editing it or died before restoring it.
        grant = et.grant(block["trust_grant"], cfg, wt, root,
                         et.probe_marker(adlc_home.adlc_home(), HARNESS), 10.0)
        cfg_granted = sha(cfg)
        row("trust-grant", grant.written and not grant.pre_existing, "the engine's entry is in the user config")
        manifest, _changes = esf.render(wt, plan, block)
        esf.install_policy_file(adapter, state_env, files.user_policy_file)
        surface = block["config_surfaces"][0]
        planted = os.path.join(surface, "planted.toml")

        # ---- launch
        rc, first, err = launch("launch", RULES + "Remember the word %s for later.\n"
                                "1. touch %s\n"
                                "2. python3 -c \"open('%s','w').write('x')\"\n"
                                "3. python3 -c \"open('%s','w').write('x')\"\n"
                                "4. git clean -f -n\n"
                                "Then say what happened.\n"
                                % (WORD, os.path.join(outside, "allowed-1"),
                                   os.path.join(outside, "unallowed-1"), planted))
        sid = first.get("session_id")
        row("launch-parses", rc == 0 and first["error"] is None and bool(sid),
            "exit %s, session id %s, parse error %r" % (rc, "read" if sid else "missing", first["error"]))
        row("allow-leaves-sandbox", wrote("allowed-1"), "an allowed command wrote outside the working copy")
        row("unallowed-contained", not wrote("unallowed-1"), "an un-allowed command did not")
        row("surface-not-writable", not os.path.exists(os.path.join(wt, planted))
            and esf.verify(wt, manifest) == [],
            "a sandboxed command could not write into the config surface")
        row("deny-refused", bool(adapter.refusal_line(err)), "the harness's refusal line is on stderr")

        # ---- the user policy file alone
        esf.render(wt, plan, block)
        rule = os.path.join(wt, block["rule_file"])
        with open(rule, encoding="utf-8") as fh:
            kept = "\n".join(ln for ln in fh.read().split("\n") if 'decision="forbidden"' not in ln)
        with open(rule, "w", encoding="utf-8") as fh:
            fh.write(kept)
        rc, _parsed, err = launch("user-policy", RULES + "1. git clean -f -n\nThen say what happened.\n")
        row("user-policy-refuses", bool(adapter.refusal_line(err)),
            "with no deny in the working copy's rule file, the user-level file still refused")

        # ---- resume
        esf.render(wt, plan, block)
        if sid and adapter.can_resume:
            rc, again, err = launch("resume", RULES + "First: which word did I ask you to remember?\n"
                                    "1. python3 -c \"open('%s','w').write('x')\"\n"
                                    "2. git clean -f -n\n"
                                    "3. touch %s\n"
                                    "Then reply with that word and nothing else.\n"
                                    % (os.path.join(outside, "unallowed-2"),
                                       os.path.join(outside, "allowed-2")), resume=sid)
            row("resume-continues", again.get("session_id") == sid and WORD in (again.get("text") or ""),
                "the same session id, and the reply holds the word from the first turn")
            row("resume-keeps-rules", wrote("allowed-2") and not wrote("unallowed-2")
                and bool(adapter.refusal_line(err)),
                "allow, sandbox and deny all held under resume")
        else:
            row("resume-continues", False, "no session id to resume, or the block declares no resume")

        # ---- the branch push, with the runner line exactly as the prompt prints it
        esf.render(wt, plan, block)
        git("-C", wt, "commit", "-q", "--allow-empty", "-m", "live check")
        head = git("-C", wt, "rev-parse", "HEAD").stdout.strip()
        rec = next(r for r in fc.census(TOOLKIT, adapter) if r.get("push") == "branch")
        fence = next(f for f in fc.fences(fc.view(TOOLKIT, PUSH_FILE), PUSH_FILE) if f.id == rec["id"])
        line = fr.runner_call(rec, TOOLKIT, fr._placeholders_for(fence))
        line = line.replace("'<worktree>'", "'%s'" % wt).replace("'<branch-name>'", "'%s'" % BRANCH)
        assert "<" not in line, line
        launch("push", RULES + "1. " + line + "\nThen say what happened.\n")
        remote = git("--git-dir", origin, "rev-parse", "--verify", "-q", "refs/heads/" + BRANCH).stdout.strip()
        row("push-through-runner", remote == head,
            "the runner left the sandbox and the branch reached the bare origin")
        row("codex-wrote-no-trust", sha(cfg) == cfg_granted,
            "codex added nothing to the user config while the engine's entry was there")
    finally:
        if grant is not None:
            result = et.revoke(grant, 10.0)
            row("trust-revoke", result.status == et.REVOKED and not result.warning, "status %s" % result.status)
        if os.path.exists(policy):
            os.unlink(policy)
        if not policy_dir_existed and os.path.isdir(policy_dir) and not os.listdir(policy_dir):
            os.rmdir(policy_dir)
        keep = os.environ.get("ADLC_LIVE_KEEP")
        if keep and os.path.isdir(out_dir):
            shutil.copytree(out_dir, os.path.join(keep, "codex-exec-live-%d" % os.getpid()))
        shutil.rmtree(root, ignore_errors=True)
        row("user-config-restored", sha(cfg) == cfg_before, "byte-identical to before the run")
        row("policy-file-removed", not os.path.lexists(policy), "the user policy file is gone")
    print("%d row(s) failed: %s" % (len(FAILED), ", ".join(FAILED)) if FAILED else "every row passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
