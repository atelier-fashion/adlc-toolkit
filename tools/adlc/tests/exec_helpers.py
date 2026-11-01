"""A throwaway repo, bare origin, stateful forge and test harness for the exec engine."""

import io
import json
import os
import re
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import sprint_exec as se  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
LESSON = """---
id: LESSON-9001
title: "A lesson"
component: "adlc/sprint"
domain: "adlc"
stack: []
concerns: []
tags: []
req: REQ-901
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-901 test"
confidence: low
---

## Lesson

A lesson.

## Applies When

A test.
"""


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, check=True).stdout


SPEC = """---
id: {req}
title: "Thing"
status: {status}
deployable: {deployable}
component: "{component}"
lane: "{lane}"
---

## Description

A thing.
"""


class Sandbox(object):
    def __init__(self, tmp_path, reqs=("REQ-901",), config="", deployable="false", lane="full",
                 component="adlc/x", mock_scenario=None):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = op\n\temail = op@example.invalid\n"
                                              "[init]\n\tdefaultBranch = main\n")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        fake = self.bin / "claude"
        # The environment is dumped here because Apple's python3 shim adds to it.
        fake.write_text('#!/bin/sh\n/usr/bin/env > "$HOME/env-raw-$ADLC_EXEC_RUN.txt"\n'
                        'exec python3 "%s" "$@"\n'
                        % os.path.join(HERE, "fake_harness", "exec_harness.py"))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.bare = tmp_path / "acme" / "widgets.git"
        self.bare.parent.mkdir()
        subprocess.check_call(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)])
        self.repo = tmp_path / "widgets"
        subprocess.check_call(["git", "init", "-q", "-b", "main", str(self.repo)])
        (self.repo / "README.md").write_text("line one\nline two\nline three\n")
        self.reqs = list(reqs)
        self.spec_dirs = {}
        for req in reqs:
            spec = ".adlc/specs/%s-thing" % req
            os.makedirs(str(self.repo / spec))
            (self.repo / spec / "requirement.md").write_text(SPEC.format(
                req=req, status="approved", deployable=deployable, component=component, lane=lane))
            self.spec_dirs[req] = spec
        base = "sprint:\n  exec:\n    child_gh_token: CHILD_GH\n"
        (self.repo / ".adlc" / "config.yml").write_text(config if config else base)
        (self.repo / ".gitignore").write_text(".worktrees/\n.adlc/specs/*/pipeline-state.json\n")
        env = dict(os.environ, HOME=str(self.home))
        for args in (["add", "-A"], ["commit", "-qm", "seed"],
                     ["remote", "add", "origin", str(self.bare)], ["push", "-q", "origin", "main"]):
            subprocess.check_call(["git", "-C", str(self.repo)] + args, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.store = tmp_path / "store"
        self.store.mkdir()
        (self.store / "config.json").write_text(json.dumps({
            "remote": str(self.bare), "owner": "acme", "name": "widgets"}))
        self.environ = {
            "HOME": str(self.home), "USER": "operator",
            "PATH": "%s:%s" % (self.bin, os.environ["PATH"]),
            "ADLC_HOME": str(self.home / ".claude"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "ADLC_FORGE_MOCK": "1", "ADLC_FORGE_MOCK_STORE": str(self.store),
            "ADLC_RUN_OUTCOMES_LOG": str(tmp_path / "outcomes.log"),
            "ADLC_DISABLE_DELEGATE": "1", "CHILD_GH": "scoped-token", "LANG": "C",
        }
        if mock_scenario:
            self.environ["ADLC_FORGE_MOCK_SCENARIO"] = mock_scenario
        self.scenarios = {req: {} for req in reqs}
        self.write_scenario()
        self.out = io.StringIO()

    def write_scenario(self, **extra):
        doc = {"store": str(self.store), "toolkit": TOOLKIT, "primary": os.path.realpath(
            str(self.repo)), "repoId": "widgets", "ib": "main", "specDirs": self.spec_dirs,
            "reqs": self.scenarios, "lesson": LESSON}
        doc.update(extra)
        (self.home / ".exec-scenario.json").write_text(json.dumps(doc))

    def req(self, req="REQ-901", **behaviour):
        self.scenarios[req].update(behaviour)
        self.write_scenario()

    def orch(self, **kw):
        environ = dict(self.environ, **kw)
        return se.Orchestrator(str(self.repo), environ, self.out, TOOLKIT)

    def start(self, reqs=None, orch=None, **opts):
        orch = orch or self.orch()
        reqs = reqs or self.reqs
        batch = orch.preflight(reqs, **opts)
        orch.launch_batch(reqs, batch)
        return orch

    def wait(self, orch, timeout=30):
        end = time.time() + timeout
        while orch.children and time.time() < end:
            orch.poll_once()
            time.sleep(0.05)
        assert not orch.children, "the harness did not exit"
        return orch

    def go(self, reqs=None, **opts):
        return self.wait(self.start(reqs, **opts))

    def tokens(self, req):
        found = re.findall(r"approve %s --token ([0-9a-f]{32})(?: --ack-gate-change --gate-token "
                           r"([0-9a-f]{32}))?" % req, self.out.getvalue())
        return found[-1] if found else (None, None)

    def approve(self, orch, req="REQ-901", drain=True, **kw):
        token, gate = self.tokens(req)
        shown = orch.approve(req, kw.pop("token", token), kw.pop("gate_token", gate),
                             decided_by="operator", caller_pid=None, **kw)
        if drain:
            orch.drain()
        return shown

    def calls(self, op=None):
        path = self.store / "calls.log"
        rows = [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if op is None or r["op"] == op]

    def log(self, run):
        with open(run.file("orchestrator.log"), encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh]

    def primary_state(self, run):
        return run.read_primary_state()

    def origin_log(self):
        return git(self.bare, "log", "--format=%H %s", "main")

    def scenario_file(self, value):
        (self.store / "scenario").write_text(value)
