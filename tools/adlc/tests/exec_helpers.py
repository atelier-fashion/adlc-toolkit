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

import exec_adapter as ea  # noqa: E402
import harness_adapter as ha  # noqa: E402
import sprint_exec as se  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
FAKE = os.path.join(HERE, "fake_harness", "exec_harness.py")
#: The Codex-shaped fixture adapter (REQ-662 TASK-256): file render, JSONL output, `-o`.
CODEX_SHAPED_FIXTURE = os.path.join(HERE, "fixtures", "harness", "fake-exec-file.yml")
#: The part of codex-cli 0.166.0's line for a command a `forbidden` rule rejects that names
#: the refusal (BUG-282): the `denied_stderr` the Codex-shaped launch declares here.
CODEX_REFUSAL = "rejected: policy forbids commands starting with"
#: The help text a launch on claude's isolation flags needs (BUG-260).
ISOLATION_HELP = "--setting-sources <s>\n--settings <f>\n--strict-mcp-config\n"
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
    """A repo, its bare origin, a mock forge and the exec fake, for one harness.

    ``harness`` names the adapter, read from ``adapter_path`` when given (a test-only adapter
    loads only by path); the fake is installed under that adapter's ``binary`` name, which
    chooses its profile (``fake_harness/exec_harness.py``). The engine is launched with
    ``--harness <harness>`` unless a test passes another."""

    def __init__(self, tmp_path, reqs=("REQ-901",), config="", deployable="false", lane="full",
                 component="adlc/x", mock_scenario=None, harness="claude", adapter_path=None):
        self.tmp = tmp_path
        self.harness = harness
        self.adapter_path = adapter_path
        adapter = ha.resolve_adapter(harness, adapter_path, TOOLKIT)
        self.binary = adapter["binary"]
        block = adapter.get("exec") or {}
        self.forbidden = list(dict.fromkeys(list(ha.ENGINE_FORBIDDEN_FLAGS)
                                            + list(block.get("forbidden_flags") or [])))
        self.home = tmp_path / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = op\n\temail = op@example.invalid\n"
                                              "[init]\n\tdefaultBranch = main\n")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        fake = self.bin / self.binary
        # The environment is dumped here because Apple's python3 shim adds to it. The name
        # the fake is installed under chooses its profile.
        fake.write_text('#!/bin/sh\n/usr/bin/env > "$HOME/env-raw-$ADLC_EXEC_RUN.txt"\n'
                        'EXEC_FAKE_AS=${0##*/}\nexport EXEC_FAKE_AS\n'
                        'exec python3 "%s" "$@"\n' % FAKE)
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
        # What the fake answers to `--version`: the adapter's declared version, so the
        # engine's version check passes unless a test sets another (REQ-662 BR-11).
        self.extra = {"version": block.get("harness_version", "unknown")}
        self.write_scenario()
        self.out = io.StringIO()

    def write_scenario(self, **extra):
        """The fake's script. Top-level keys a test sets here (``help``, ``unknown_flags``,
        ``version``) stay set for every later write."""
        self.extra.update(extra)
        doc = {"store": str(self.store), "toolkit": TOOLKIT, "primary": os.path.realpath(
            str(self.repo)), "repoId": "widgets", "ib": "main", "specDirs": self.spec_dirs,
            "reqs": self.scenarios, "lesson": LESSON, "forbidden": self.forbidden}
        doc.update(self.extra)
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
        opts.setdefault("harness", self.harness)
        batch = orch.preflight(reqs, **opts)
        orch.launch_batch(reqs, batch)
        return orch

    def wait(self, orch, timeout=30):
        end = time.time() + timeout
        while orch.children and time.time() < end:
            orch.poll_once()
            time.sleep(0.05)
        assert not orch.children, "the harness did not exit"
        self.check_fake()
        return orch

    def check_fake(self):
        """Fail the test loudly if the fake was ever launched with a forbidden flag (BR-12)."""
        hits = sorted(p.name for p in self.home.glob("exec-fake-forbidden-*.txt"))
        assert not hits, "the exec fake was launched with a forbidden flag: %s" % [
            (self.home / name).read_text() for name in hits]

    def launches(self, req="REQ-901"):
        """What the jsonl fake recorded of each launch: argv, parsed options, the working
        directory, the prompt's line count and the environment."""
        path = self.home / ("launch-%s.json" % req)
        return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []

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
        self.check_fake()
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


# ---- the Codex-shaped launch on today's engine (REQ-662 ADR-10) -------------------------------
def codex_shaped_adapter(directory, exit_codes=None, denied_stderr=CODEX_REFUSAL):
    """An adapter file the engine launches today with the Codex-shaped fixture's binary,
    ``launch``, ``resume`` and ``output``: claude's block with those swapped in, written as
    ``fake-exec-file.yml`` under ``directory``. The fixture itself waits on the file render
    (TASK-261) and the trust grant (TASK-263); a test holds the swapped values equal to it.
    ``exit_codes`` is a YAML flow map; ``denied_stderr`` a pattern, or None for none."""
    text = open(os.path.join(TOOLKIT, "harness", "claude.yml"), encoding="utf-8").read()
    swaps = [
        ("name: claude\n", "name: fake-exec-file\n"),
        ("binary: claude\n", "binary: fake-exec-file\n"),
        # `grandfathered` is claude's alone (Rule A); under another name the record is a probe's.
        ("harness_version: n/a, source: grandfathered}",
         'harness_version: "fake-exec-file 0.1.0", source: probe}'),
        ("  prompt_variant: with-prompt-flag\n", "  prompt_variant: without-prompt-flag\n"),
        ("  launch: [-p, --output-format, json]\n",
         '  launch: [exec, --json, --sandbox, workspace-write, -C, "{worktree}", -o, '
         '"{last_message}"]\n'),
        ('  resume: [-p, --output-format, json, --resume, "{session_id}"]\n',
         '  resume: [exec, resume, --json, -o, "{last_message}", "{session_id}", "-"]\n'),
        ("    format: json\n    source: stdout\n    session_id: session_id\n"
         "    final_message: result\n    is_error: is_error\n    num_turns: num_turns\n"
         "    cost: total_cost_usd\n    denials: permission_denials\n",
         '    format: jsonl-stream\n    source: file\n    final_message: "{last_message}"\n'
         "    session_id: {event: thread.started, key: thread_id}\n"
         "    terminal_event: turn.completed\n"),
    ]
    codes = '  exit_codes: {"0": ok, "1": error}\n'
    new_codes = "  exit_codes: %s\n" % exit_codes if exit_codes else codes
    if denied_stderr:
        new_codes += "  denied_stderr: %s\n" % json.dumps(denied_stderr)
    swaps.append((codes, new_codes))
    for old, new in swaps:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), "fake-exec-file.yml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def use_adapter(monkeypatch, path):
    """``exec_adapter.load`` answering with the adapter at ``path`` for its own name, read
    through the loader, so the engine meets a block the loader accepts."""
    loaded = ea.ExecAdapter(ha.load_adapter(path, toolkit=TOOLKIT), TOOLKIT)
    real = ea.load

    def load(name, toolkit=None, adapter_path=None):
        return loaded if name == loaded.name else real(name, toolkit, adapter_path)
    monkeypatch.setattr(ea, "load", load)
    return loaded


def jsonl_sandbox(tmp_path, monkeypatch, exit_codes=None, denied_stderr=CODEX_REFUSAL, **kw):
    """A Sandbox whose harness is the Codex-shaped launch (:func:`codex_shaped_adapter`), with
    the jsonl fake installed as ``fake-exec-file``. Script it per REQ with ``box.req(...)``:
    ``exit``/``exit_early``, ``stderr``, ``commands``, ``refused``, ``stream``, ``no_session``,
    ``no_last_message``, ``text``, ``plant`` and the rest of REQ-659's keys."""
    path = codex_shaped_adapter(tmp_path / "adapter", exit_codes, denied_stderr)
    use_adapter(monkeypatch, path)
    box = Sandbox(tmp_path, harness="fake-exec-file", adapter_path=path, **kw)
    # The launch carries claude's isolation and flag-rendered tiers after the Codex-shaped
    # template until the file render lands (TASK-261): the fake records them as unknown.
    box.write_scenario(help=ISOLATION_HELP, unknown_flags="record")
    return box

