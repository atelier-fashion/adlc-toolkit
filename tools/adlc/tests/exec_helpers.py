"""A throwaway repo, bare origin, stateful forge and test harness for the exec engine."""

import functools
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_surfaces as esf  # noqa: E402
import exec_trust as et  # noqa: E402
import exec_verify as ev  # noqa: E402
import harness_adapter as ha  # noqa: E402
import harness_render as hr  # noqa: E402
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
#: Synthetic REQ-664 result files (REQ-662 TASK-260).
PROBE_RESULTS = os.path.join(HERE, "fixtures", "probe-results")
#: The version the `verification: probes` sandbox's adapter declares and its result records.
PROBED_VERSION = "fake-exec-file 0.1.0"
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


@functools.lru_cache(maxsize=None)
def _binaries():
    folder = os.path.join(TOOLKIT, "harness")
    return tuple(ha.resolve_adapter(name[:-4], None, TOOLKIT)["binary"]
                 for name in sorted(os.listdir(folder)) if name.endswith(".yml"))


def harness_binaries():
    """The ``binary`` of every adapter this toolkit ships (``harness/*.yml``): the names a real
    harness is installed under, which no sandbox PATH may resolve outside its own bin."""
    return list(_binaries())


def offline_path(fake_bin, mirror_root, path):
    """``path`` with ``fake_bin`` first and no real harness on it (REQ-662 BR-12): a directory
    holding any :func:`harness_binaries` name is replaced by a mirror under ``mirror_root``
    that links every other entry of it, so the tools beside a real ``codex`` or ``claude``
    (``git``, ``python3``) stay reachable and the harness does not."""
    names = set(harness_binaries())
    dirs = [str(fake_bin)]
    for n, folder in enumerate(dict.fromkeys(p for p in path.split(os.pathsep) if p)):
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        if not names & set(entries):
            dirs.append(folder)
            continue
        mirror = os.path.join(str(mirror_root), str(n))
        os.makedirs(mirror)
        for entry in entries:
            if entry not in names:
                os.symlink(os.path.join(folder, entry), os.path.join(mirror, entry))
        dirs.append(mirror)
    return os.pathsep.join(dict.fromkeys(dirs))


class Sandbox(object):
    """A repo, its bare origin, a mock forge and the exec fake, for one harness.

    ``harness`` names the adapter, read from ``adapter_path`` when given (a test-only adapter
    loads only by path); the fake is installed under that adapter's ``binary`` name, which
    chooses its profile (``fake_harness/exec_harness.py``). The engine is launched with
    ``--harness <harness>`` unless a test passes another. The sandbox PATH resolves the
    adapter's binary to the fake and no shipped harness's binary to anything else, so the
    suite never reaches a real harness (:func:`offline_path`)."""

    def __init__(self, tmp_path, reqs=("REQ-901",), config="", deployable="false", lane="full",
                 component="adlc/x", mock_scenario=None, harness="claude", adapter_path=None,
                 toolkit=None):
        self.tmp = tmp_path
        self.harness = harness
        self.adapter_path = adapter_path
        # The ToolkitRoot the engine runs from: this toolkit, or a copy (`toolkit_copy`) that a
        # test may write a probe result file into. A shipped adapter is read from it, as the
        # engine reads it.
        self.toolkit = toolkit or TOOLKIT
        adapter = ha.resolve_adapter(harness, adapter_path, self.toolkit)
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
        path = offline_path(self.bin, tmp_path / "path", os.environ["PATH"])
        # BR-12: the binary the engine resolves is the fake, and no real harness is reachable.
        resolved = shutil.which(self.binary, path=path)
        assert resolved == str(fake), "%s resolves to %s, not the fake" % (self.binary, resolved)
        for name in harness_binaries():
            found = shutil.which(name, path=path)
            assert found is None or os.path.dirname(found) == str(self.bin), \
                "a real %s is on the sandbox PATH: %s" % (name, found)
        self.environ = {
            "HOME": str(self.home), "USER": "operator",
            "PATH": path,
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
        # The operator's user-level files a run must leave as it found them (`user_files`):
        # set by `adapter_sandbox` and `trust_sandbox`.
        self.user_config = self.policy_dir = self.policy_file = None

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
        return se.Orchestrator(str(self.repo), environ, self.out, self.toolkit)

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
        """Fail the test loudly if the fake was ever launched with a forbidden flag (BR-12), or
        resumed with a session id it did not last print (BR-7)."""
        hits = sorted(p.name for p in self.home.glob("exec-fake-forbidden-*.txt"))
        assert not hits, "the exec fake was launched with a forbidden flag: %s" % [
            (self.home / name).read_text() for name in hits]
        hits = sorted(p.name for p in self.home.glob("exec-fake-session-*.txt"))
        assert not hits, "the exec fake was resumed with a session it did not print: %s" % [
            (self.home / name).read_text() for name in hits]

    def launches(self, req="REQ-901"):
        """What the jsonl fake recorded of each launch: argv, parsed options, the working
        directory, the prompt's line count and the environment."""
        path = self.home / ("launch-%s.json" % req)
        return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []

    def argvs(self, req="REQ-901"):
        """The argv after the binary of each launch the fake received, the close-out's included,
        in order: either profile records it."""
        path = self.home / ("argv-%s.json" % req)
        return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []

    def adapter(self):
        """The ``ExecAdapter`` the engine launches this sandbox's harness with."""
        return ea.load(self.harness, self.toolkit)

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

    def user_files(self):
        """The operator's own files at user level, path to text (None when absent): the user
        config a trust grant writes and every file in the user policy folder but the
        toolkit's own (:func:`adapter_sandbox`). A run leaves each as it found it."""
        out = {}
        if self.user_config:
            out[self.user_config] = read_text(self.user_config) \
                if os.path.exists(self.user_config) else None
        if self.policy_dir:
            for name in sorted(os.listdir(self.policy_dir)):
                if name != os.path.basename(self.policy_file):
                    full = os.path.join(self.policy_dir, name)
                    out[full] = read_text(full)
        return out

    def write_result(self, doc):
        """Replace this harness's REQ-664 result file under the sandbox ToolkitRoot, where the
        engine reads it (REQ-662 BR-11). Never under this toolkit itself."""
        assert os.path.realpath(self.toolkit) != os.path.realpath(TOOLKIT), \
            "write_result needs a sandbox ToolkitRoot (probes_sandbox)"
        path = ev.result_path(ha.resolve_adapter(self.harness, self.adapter_path, TOOLKIT),
                              self.toolkit)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        return path


# ---- the Codex-shaped launch on today's engine (REQ-662 ADR-10) -------------------------------
def codex_shaped_adapter(directory, exit_codes=None, denied_stderr=CODEX_REFUSAL):
    """An adapter file the engine launches today with the Codex-shaped fixture's binary,
    ``launch``, ``resume`` and ``output``: claude's block with those swapped in, written as
    ``fake-exec-file.yml`` under ``directory``. The fixture itself waits on the trust grant
    (TASK-263); a test holds the swapped values equal to it. :func:`file_sandbox` launches the
    fixture's file render form.
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


def use_adapter(monkeypatch, path, toolkit=None):
    """``exec_adapter.load`` answering with the adapter at ``path`` for its own name, read
    through the loader, so the engine meets a block the loader accepts. ``toolkit`` is the
    ToolkitRoot it resolves its fence runner under (this toolkit by default)."""
    loaded = ea.ExecAdapter(ha.load_adapter(path, toolkit=TOOLKIT), toolkit or TOOLKIT)
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
    # template, and the fake records them as unknown; `file_sandbox` is the file render form.
    box.write_scenario(help=ISOLATION_HELP, unknown_flags="record")
    return box


# ---- a `verification: probes` adapter on a sandbox ToolkitRoot (REQ-662 TASK-260) -------------
def toolkit_copy(dest):
    """A sandbox ToolkitRoot: every file git tracks or would track here, copied to ``dest``
    with its mode, so a test can place a probe result file where the engine reads it without
    writing into this toolkit."""
    out = subprocess.run(["git", "-C", TOOLKIT, "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], stdout=subprocess.PIPE, check=True).stdout
    for rel in sorted(set(out.decode("utf-8").split("\0")) - {""}):
        src = os.path.join(TOOLKIT, rel)
        if not os.path.lexists(src) or os.path.isdir(src):
            continue
        target = os.path.join(str(dest), rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target, follow_symlinks=False)
    return str(dest)


def probe_result(name="prompt-pass", version=PROBED_VERSION):
    """A synthetic result file from ``fixtures/probe-results``, recorded under ``version``."""
    with open(os.path.join(PROBE_RESULTS, name + ".json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["harness_version"] = version
    return doc


def with_reading(doc, key, status):
    """A copy of result ``doc`` where ``probe`` or ``probe/variant`` reads ``status``."""
    doc = json.loads(json.dumps(doc))
    probe, _, variant = key.partition("/")
    row = doc["probes"][probe]
    if variant:
        row.setdefault("sub_results", {})[variant] = {"status": status}
    else:
        row["status"] = status
    return doc


def probes_adapter(directory, result):
    """The Codex-shaped launch (:func:`codex_shaped_adapter`) as a ``verification: probes``
    block, as a maintainer writes one from ``result``: it declares ``result``'s version, its
    ``exec.probes`` cites each required row and its ``status`` is ``verified``. Every other
    declaration is the Codex-shaped one, which ``prompt-pass`` is acceptable for, and its
    ``accepted_fidelity`` declares at ``exec`` each loss the exec-scope render reports, which
    the pre-flight refuses undeclared (REQ-662 BR-3)."""
    path = codex_shaped_adapter(directory)
    text = open(path, encoding="utf-8").read()
    block = ha.load_adapter(path, toolkit=TOOLKIT)["exec"]
    cache = "".join(
        '    - id: %s\n      ran_at: "%s"\n      harness_version: "%s"\n      status: %s\n'
        % (probe, result["probes"][probe]["ran_at"], result["harness_version"],
           result["probes"][probe]["status"]) for probe in ev.required(block))
    for old, new in (("  verification: recorded\n", "  verification: probes\n  probes:\n" + cache),
                     ('  harness_version: "%s"\n' % block["harness_version"],
                      '  harness_version: "%s"\n' % result["harness_version"])):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    declare_exec_losses(path, result)
    return path


def exec_losses(path, result, toolkit=TOOLKIT):
    """The exec-scope findings of the adapter at ``path`` that its ``accepted_fidelity`` does
    not declare at ``exec``, rendered with ``result`` over ``toolkit``'s template."""
    adapter = ha.load_adapter(path, toolkit=TOOLKIT)
    _entries, findings = hr.exec_entries(adapter, toolkit, result)
    return hr.exec_undeclared(adapter, findings)


def declare_exec_losses(path, result, toolkit=TOOLKIT):
    """Declare in ``accepted_fidelity`` each exec-scope loss :func:`exec_losses` reports, one
    ``"<entry>:<command>": {exec: <verdict>}`` line each, as a maintainer would."""
    text = open(path, encoding="utf-8").read()
    lines = "".join('  "%s:%s": {exec: "%s"}\n' % (f.entry, f.command, f.verdict)
                    for f in exec_losses(path, result, toolkit))
    assert text.count("accepted_fidelity:\n") == 1
    text = text.replace("accepted_fidelity:\n", "accepted_fidelity:\n" + lines)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    assert not exec_losses(path, result, toolkit)
    return path


def probes_sandbox(tmp_path, monkeypatch, result="prompt-pass", **kw):
    """A Sandbox whose adapter is ``verification: probes`` (:func:`probes_adapter`, the jsonl
    fake installed as ``fake-exec-file``) and whose ToolkitRoot is a copy of this toolkit
    (``box.toolkit``) holding the result file at ``.adlc/research/harness-probes/
    fake-exec-file.json``. As built, the adapter is verified. To make it unverified, have the
    fake report another version (``box.write_scenario(version=...)``) or replace the file
    (``box.write_result(with_reading(box.result, key, status))``). ``result`` is a fixture
    name or a result dict; ``kw`` goes to :class:`Sandbox`."""
    doc = probe_result(result) if isinstance(result, str) else result
    toolkit = toolkit_copy(tmp_path / "toolkit")
    path = probes_adapter(tmp_path / "adapter", doc)
    use_adapter(monkeypatch, path, toolkit)
    box = Sandbox(tmp_path, harness="fake-exec-file", adapter_path=path, toolkit=toolkit, **kw)
    box.write_scenario(help=ISOLATION_HELP, unknown_flags="record")
    box.result = doc
    box.write_result(doc)
    return box


# ---- a file-rendered adapter the engine launches today (REQ-662 TASK-262) ---------------------
#: The working-copy paths of the file-rendered sandbox's adapter (:func:`file_adapter`), all
#: inside its one directory surface.
FILE_SURFACE = ".fake-exec-file/"
FILE_RULE = ".fake-exec-file/rules/adlc-exec.rules"
FILE_PROJECT_RULES = ".fake-exec-file/rules/default.rules"
FILE_HOOKS = ".fake-exec-file/hooks.json"
FILE_CONFIG = ".fake-exec-file/config.toml"
#: The same adapter's user-level paths, under the sandbox HOME.
FILE_USER_CONFIG = ".fake-exec-file/config.toml"
FILE_POLICY_DIR = ".fake-exec-file/rules"
FILE_POLICY = ".fake-exec-file/rules/adlc-exec.rules"


def file_adapter(directory, result, rules_reload="unknown", context_delivery="prompt",
                 trust_grant="none"):
    """The Codex-shaped fixture (``fake-exec-file.yml``, the ``file`` render form) made
    launchable on today's engine, as a ``verification: probes`` block over ``result``: its
    rules in a working-copy rule file and the deny tier in a user policy file, a working-copy
    config and hook file inside its one directory surface, the ``worktree`` working copy, and
    ``trust_grant`` (``none``, or the fixture's own ``user-config-entry``, which writes the
    user config ``$HOME/`` + :data:`FILE_USER_CONFIG`; REQ-662 BR-5). Like Codex it declares no
    ``add_dir_flag``, so its close-out writes its state through the close-out working copy
    (REQ-662 ADR-7). Every exec-scope loss is declared, as a maintainer would."""
    text = open(CODEX_SHAPED_FIXTURE, encoding="utf-8").read()
    block = ha.load_adapter(CODEX_SHAPED_FIXTURE, toolkit=TOOLKIT)["exec"]
    cache = "".join(
        '    - id: %s\n      ran_at: "%s"\n      harness_version: "%s"\n      status: %s\n'
        % (probe, result["probes"][probe]["ran_at"], result["harness_version"],
           result["probes"][probe]["status"]) for probe in ev.required(
            dict(block, context_delivery=context_delivery)))
    old_cache = text[text.index("  probes:\n"):text.index("  working_copy:")]
    swaps = [
        ('\n  harness_version: "fake-exec-file 0.1.0"\n',
         '\n  harness_version: "%s"\n' % result["harness_version"]),
        ("schema_version: 1\n", "schema_version: 3\n"),
        ("    project: .fake-exec-file/rules/default.rules\n    mode: rendered\n",
         "    project: %s\n    mode: rendered\n"
         "  hooks:\n    project: %s\n    mode: rendered\n"
         "  config:\n    project: %s\n    user: $HOME/%s\n    mode: rendered\n"
         "    write_mode: merge\n    owned_keys: [sandbox_mode, approval_policy]\n"
         "    values:\n      sandbox_mode: workspace-write\n      approval_policy: on-request\n"
         % (FILE_PROJECT_RULES, FILE_HOOKS, FILE_CONFIG, FILE_USER_CONFIG)),
        ("  permissions: rules-json\n", "  permissions: starlark-prefix-rule\n"
         "  hooks: codex-hooks-json\n  config: codex-config-toml\n"),
        ("  allowlist_granularity: command-base\n",
         "  allowlist_granularity: token-prefix\n  git_c_spelling: [[git, -C]]\n"),
        ("capabilities:\n", "sandbox_can_reach_common_gitdir: true\naccepted_fidelity:\n"
         "  fence.partial-source: {project: inexpressible, exec: inexpressible}\n"
         "capabilities:\n"),
        (old_cache, "  probes:\n" + cache),
        ("  working_copy: {strategy: clone}\n  trust_grant: user-config-entry\n",
         "  working_copy: {strategy: worktree}\n  trust_grant: %s\n" % trust_grant),
        ("  context_delivery: prompt\n", "  context_delivery: %s\n" % context_delivery),
        ("  rules_reload: unknown\n", "  rules_reload: %s\n" % rules_reload),
    ]
    for old, new in swaps:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), "fake-exec-file.yml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    declare_exec_losses(path, result)
    return path


def file_sandbox(tmp_path, monkeypatch, result="prompt-pass", rules_reload="unknown",
                 trust_grant="none", **kw):
    """A Sandbox whose harness is :func:`file_adapter` on a sandbox ToolkitRoot holding its
    result file, with the jsonl fake installed as ``fake-exec-file``. The launch and the resume
    carry the Codex-shaped templates and nothing else, and the fake refuses any other option.
    ``box.home`` is the run's HOME, where the user config and the user policy folder live;
    ``trust_grant`` is the adapter's (:func:`file_adapter`)."""
    doc = probe_result(result) if isinstance(result, str) else result
    toolkit = toolkit_copy(tmp_path / "toolkit")
    path = file_adapter(tmp_path / "adapter", doc, rules_reload=rules_reload,
                        trust_grant=trust_grant)
    use_adapter(monkeypatch, path, toolkit)
    box = Sandbox(tmp_path, harness="fake-exec-file", adapter_path=path, toolkit=toolkit, **kw)
    box.result = doc
    box.write_result(doc)
    return box


#: An operator's user config for the trust grant (REQ-662 BR-5): their own keys, another
#: project's trust entry and a hook-review table, none of which a grant or a revoke may change.
USER_CONFIG = ('# the operator\'s own config\n'
               'model = "fake-mid-1"\n'
               '\n'
               '[tui]\n'
               'theme = "dark"   # a trailing comment\n'
               '\n'
               '[projects."/srv/other"]\n'
               'trust_level = "trusted"\n'
               '\n'
               '[hooks.state."/srv/other/.fake-exec-file/hooks.json:session_start:0"]\n'
               'trusted_hash = "sha256:%s"\n' % ("0" * 64))


def trust_sandbox(tmp_path, monkeypatch, **kw):
    """A :func:`file_sandbox` whose adapter declares ``trust_grant: user-config-entry``, with
    :data:`USER_CONFIG` as the user config the adapter names, under the sandbox HOME
    (``box.user_config``): the file the harness reads, never the operator's (LESSON-777)."""
    box = file_sandbox(tmp_path, monkeypatch, trust_grant="user-config-entry", **kw)
    box.user_config = str(box.home / FILE_USER_CONFIG)
    os.makedirs(os.path.dirname(box.user_config), exist_ok=True)
    with open(box.user_config, "w", encoding="utf-8") as fh:
        fh.write(USER_CONFIG)
    return box


# ---- the shipped adapters end to end (REQ-662 TASK-267) ---------------------------------------
#: The exec-capable adapters the approval protocol runs over: each shipped one whose stage has
#: run (REQ-662 Amendments, 2026-11-17).
EXEC_ADAPTERS = ("claude", "codex")
#: An operator's own rule file in a user policy folder, beside the toolkit's: no run changes it.
OPERATOR_RULES = 'prefix_rule(pattern = ["make", "lint"], decision = "allow")\n'


def adapter_sandbox(tmp_path, harness, **kw):
    """A Sandbox on the shipped ``harness/<harness>.yml``, read from a copy of this toolkit
    (``box.toolkit``) that holds the committed ``.adlc/research/harness-probes/<harness>.json``,
    so the verdict is the committed one (``verified`` for each of :data:`EXEC_ADAPTERS`). The
    fake on PATH is installed under the adapter's binary and answers ``--version`` with its
    declared version; nothing else on PATH is a harness. What the adapter keeps at user level
    lives under the sandbox HOME: ``box.user_config`` is its ``paths.config.user`` when its
    trust grant writes that file (seeded with :data:`USER_CONFIG`, the operator's), else None;
    ``box.policy_dir`` is the folder of its ``exec.user_policy_file`` (seeded with the
    operator's :data:`OPERATOR_RULES`), else None. :meth:`Sandbox.user_files` reads both."""
    toolkit = toolkit_copy(tmp_path / "toolkit")
    box = Sandbox(tmp_path, harness=harness, toolkit=toolkit, **kw)
    adapter = ha.resolve_adapter(harness, None, toolkit)
    block = adapter.get("exec") or {}
    if block.get("trust_grant") == et.USER_CONFIG_ENTRY:
        box.user_config = et.user_config_path(adapter, box.environ)
        os.makedirs(os.path.dirname(box.user_config), exist_ok=True)
        with open(box.user_config, "w", encoding="utf-8") as fh:
            fh.write(USER_CONFIG)
    box.policy_file = esf.policy_path(adapter, box.environ)
    if box.policy_file:
        box.policy_dir = os.path.dirname(box.policy_file)
        os.makedirs(box.policy_dir, exist_ok=True)
        with open(os.path.join(box.policy_dir, "operator.rules"), "w", encoding="utf-8") as fh:
            fh.write(OPERATOR_RULES)
    box.result = ev.read_result(ea.load(harness, toolkit), toolkit)
    return box


def read_text(path):
    with open(str(path), encoding="utf-8") as fh:
        return fh.read()


def fresh_files(box, branch="feat/REQ-901-thing"):
    """The adapter's rule-file and policy-file text for ``branch``, rendered as the engine
    renders them for a run (``harness_render.ExecFiles``)."""
    adapter = ea.load(box.harness, box.toolkit)
    return adapter.rule_files(branch, (), ev.read_result(adapter, box.toolkit))


def commit_on_main(box, files):
    """Commit ``files`` (path to text) to the sandbox repo's main and push it, as a project
    that tracks those paths would have them."""
    env = dict(os.environ, HOME=str(box.home))
    for rel, body in files.items():
        full = box.repo / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body, encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-qm", "track"], ["push", "-q", "origin", "main"]):
        subprocess.check_call(["git", "-C", str(box.repo)] + args, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def events(box, run, kind):
    """The run log's ``kind`` events' ``detail`` payloads, in order."""
    return [r["detail"] for r in box.log(run) if r["kind"] == kind]
