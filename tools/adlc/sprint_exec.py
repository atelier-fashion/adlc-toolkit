#!/usr/bin/env python3
"""sprint_exec — the `/sprint` exec engine: an orchestrator that is a program (REQ-659).

Per REQ it prepares a working copy, builds the prompt, launches one headless harness with
that prompt on stdin, and reads what comes back as data. The model stops at the merge
gate. Every one-way move (merge, deploy, the close-out merge, cleanup) is performed here,
after an operator's recorded approval. See
`.adlc/specs/REQ-659-sprint-exec-engine/architecture.md`.

``run`` and ``resume`` are the long-lived supervisor, whose stdout is the dashboard and
the only place a token is printed. ``status``, ``approve``, ``reject``, ``answer`` and
``abort`` are clients, callable from a plain shell.

Standard library only (LESSON-395).
"""

import argparse
import calendar
import hashlib
import json
import os
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import exec_adapter as ea  # noqa: E402
import exec_gates as eg  # noqa: E402
import exec_ledger as el  # noqa: E402
import exec_prompt as ep  # noqa: E402
import exec_safety as es  # noqa: E402
import exec_surfaces as esf  # noqa: E402
import exec_trust as et  # noqa: E402
import exec_verify as ev  # noqa: E402
import toolkit_root  # noqa: E402

MAX_CONCURRENT = 5
MOCK_HOST = "mock.forge"
TERMINAL = ("merged", "rejected", "failed")
#: Keys the primary-path copy keeps over a working copy's (REQ-647, REQ-648).
PRIMARY_OWNED = ("lessons", "harness", "validateAttempts", "verify", "lessonsWritten")
STATES = ("running", "awaiting_approval", "approved", "merging", "merged", "blocked", "failed",
          "rejected", "stalled")
PROTOCOL = "Rule B protocol violation"


class Refused(Exception):
    """An operator-facing refusal: the message says why, nothing happened."""


def _commands(items):
    """``DenyUnsupported`` entries as the operator reads them: each command, quoted."""
    return ", ".join("`%s`" % item.command for item in items)


#: Held while the engine changes a file the common gitdir checksum covers and carries every
#: box past it (``Orchestrator._gitdir_write``), and while any box checks that checksum, so no
#: check, in the supervisor or the merge worker, reads the change before its box is carried.
GITDIR_LOCK = threading.RLock()


class Toolbox(es.Toolbox):
    """REQ-659's Toolbox, whose common gitdir check waits on :data:`GITDIR_LOCK` (REQ-662
    BR-17: the engine itself writes a working copy's ``config.worktree``)."""

    def check_gitdir(self, repo):
        with GITDIR_LOCK:
            return es.Toolbox.check_gitdir(self, repo)


class Run(object):
    """One REQ's run directory and its orchestrator-owned record."""

    def __init__(self, path, doc):
        self.path = path
        self.doc = doc

    @classmethod
    def load(cls, path):
        doc = el.read_json(os.path.join(path, el.RUN_RECORD))
        if not isinstance(doc, dict):
            raise Refused("run record unreadable in %s" % path)
        return cls(path, doc)

    def save(self):
        el.atomic_json(os.path.join(self.path, el.RUN_RECORD), self.doc)

    def file(self, name):
        return os.path.join(self.path, name)

    def last_message(self, log_name):
        """The file the harness writes its last message to on the launch whose stdout is
        ``log_name``: the ``{last_message}`` placeholder. It is in this run directory, which is
        mode 0700, and never in a working copy the model writes (REQ-662 ADR-6)."""
        stem = log_name[:-len(".json")] if log_name.endswith(".json") else log_name
        return self.file(stem + ".last-message.txt")

    def ledger(self):
        return el.Ledger(self.path, self.doc)

    @property
    def req(self):
        return self.doc["req"]

    @property
    def status(self):
        return self.doc["status"]

    @status.setter
    def status(self, value):
        self.doc["status"] = value

    @property
    def exec(self):
        return self.doc["exec"]

    @property
    def primary_repo(self):
        return next(k for k, v in self.doc["repos"].items() if v.get("primary"))

    @property
    def primary_path(self):
        return self.doc["primary"]

    @property
    def wc(self):
        return self.doc["repos"][self.primary_repo]["workingCopy"]

    def wc_state_path(self):
        return os.path.join(self.wc, self.doc["specDir"], "pipeline-state.json")

    def primary_state_path(self):
        return os.path.join(self.primary_path, self.doc["specDir"], "pipeline-state.json")

    def read_wc_state(self):
        doc = el.read_json(self.wc_state_path(), {})
        return doc if isinstance(doc, dict) else {}

    def read_primary_state(self):
        doc = el.read_json(self.primary_state_path(), {})
        return doc if isinstance(doc, dict) else {}

    def write_primary_state(self, doc):
        path = self.primary_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        el.atomic_json(path, doc)

    def public_exec(self):
        """``exec`` as state shows it: file names, never the run directory (BR-9)."""
        return dict(self.exec)

    def violation(self, message):
        """Appended, never in ``run.json``: a client outside the supervisor records one too."""
        record = {"at": el.now(), "rule": "B", "evidence": message}
        with open(self.file("violations.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def violations_of(run):
    """Every violation recorded on this run, by the supervisor or a client."""
    seen = []
    path = run.file("violations.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.append(json.loads(line)["evidence"])
                except (ValueError, KeyError):
                    continue
    return seen


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


PS = shutil.which("ps", path="/bin:/usr/bin") or "ps"

#: Beside ``ADLC_EXEC_RUN`` in every child's environment: a digest of the run directory, so the
#: straggler sweep is one run's own. A digest, because the directory's path is kept from the
#: model (REQ-659 AC-33).
RUN_TAG_ENV = "ADLC_EXEC_RUN_TAG"


def run_tag(run_dir):
    return hashlib.sha256(os.path.realpath(run_dir).encode("utf-8")).hexdigest()[:32]


def parent_of(pid):
    res = subprocess.run([PS, "-o", "ppid=", "-p", str(pid)], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, universal_newlines=True)
    text = res.stdout.strip()
    return int(text) if text.isdigit() else 0


def ancestry(pid):
    chain = []
    while pid and pid > 1 and len(chain) < 64:
        chain.append(pid)
        pid = parent_of(pid)
    return chain


def stragglers(req, tag=None):
    """Live processes still carrying ``ADLC_EXEC_RUN=<req>`` in their environment and, when
    ``tag`` is given, ``ADLC_EXEC_RUN_TAG=<tag>`` beside it.

    The REQ id alone is not unique on a machine: two projects number their requirements
    alike, and two orchestrators may run the same id at once. A run's tag is, so the sweep
    that ends a run names both and never reaches another run's processes."""
    res = subprocess.run([PS, "eww", "-axo", "pid=,command="], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, universal_newlines=True, errors="replace")
    needles = ["ADLC_EXEC_RUN=%s" % req]
    if tag:
        needles.append("%s=%s" % (RUN_TAG_ENV, tag))
    out = []
    for line in res.stdout.splitlines():
        head = line.strip().split(None, 1)
        if len(head) == 2 and head[0].isdigit() and int(head[0]) != os.getpid():
            if all(re.search(r"(^|\s)%s(\s|$)" % re.escape(n), head[1]) for n in needles):
                out.append(int(head[0]))
    return out


def peer_pid(conn):
    """The connecting process's pid from the kernel, or None."""
    try:
        if sys.platform == "darwin":
            return struct.unpack("i", conn.getsockopt(0, 2, 4))[0]        # LOCAL_PEERPID
        return struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                   12))[0]
    except (OSError, AttributeError, struct.error):
        return None


#: The dispatched ops that start a harness: approve's close-out resume and answer's relaunch.
#: Like `run` and `resume`, each is refused from inside a run by the caller's ancestry as well
#: as by ``ADLC_EXEC_RUN`` (REQ-662 BR-18).
LAUNCH_OPS = ("approve", "answer")


class Batch(object):
    """What the pre-flight established, once, for every REQ of a launch."""

    def __init__(self):
        self.adapter = None
        self.binary = None
        self.config = None
        self.provider = None
        self.host = None
        self.origin = None
        self.repos = {}
        self.order = []
        self.flags = []
        self.shared = False
        self.allow_unprotected = False
        self.protection = "unknown"
        self.child_token = None
        # The adapter's BR-11 verdict at pre-flight (``exec_verify.Verdict``), and whether this
        # invocation received --allow-unverified (REQ-662 ADR-2).
        self.verdict = None
        self.allow_unverified = False
        # The exec-scope render the pre-flight judged (REQ-662 ADR-3): the REQ-664 result file
        # it read from ToolkitRoot, the files' text (``harness_render.ExecFiles``; None when
        # both tiers are flags), the allowlist-fidelity report each run's log carries, and the
        # ``exec_adapter.DenyUnsupported`` entries each run's log names.
        self.result = None
        self.exec_files = None
        self.fidelity = []
        self.deny_unsupported = []
        # The user policy folder's manifest, as the pre-flight wrote and recorded it (REQ-662
        # BR-4); None when the adapter declares no user policy file.
        self.policy = None
        # Per repo id, `present` or `enabled`: extensions.worktreeConfig, which hiding what a
        # file-rendering adapter renders needs (REQ-662 BR-17). Empty for any other adapter.
        self.worktree_config = {}


class Orchestrator(object):
    def __init__(self, primary, environ=None, out=None, toolkit=None):
        self.primary = os.path.realpath(primary)
        self.environ = dict(os.environ if environ is None else environ)
        self.toolkit = toolkit or toolkit_root.toolkit_root()
        self.out = out or sys.stdout
        self.runs = {}
        self.boxes = {}
        self.children = {}
        self.adapters = {}
        self.tokens = {}
        self.queue = []
        self.pending = []
        self.batch = None
        self.lock = threading.RLock()
        self.worker = None
        self.sup_dir = None
        # --allow-unverified reaches this invocation from its own command line alone, never
        # from config, state or the environment. Set by `run`, it covers that invocation's own
        # pre-flight and starts; an `answer` carries its own in its request (REQ-662 BR-18).
        self.allow_unverified = False
        self.invocation = el.invocation()
        # The latest verdict per adapter name, recomputed at each gate (REQ-662 ADR-2).
        self.verdicts = {}

    # ---- small helpers ---------------------------------------------------------------
    def say(self, line):
        self.out.write(line + "\n")
        self.out.flush()

    def box(self, run):
        if run.req not in self.boxes:
            self.boxes[run.req] = Toolbox.load(run.path, self.toolkit, self.environ)
        return self.boxes[run.req]

    def adapter(self, run):
        name = run.doc["harness"]
        if name not in self.adapters:
            self.adapters[name] = ea.load(name, self.toolkit)
        return self.adapters[name]

    def host_of(self, run):
        return run.doc["forgeHost"]

    def recorded_merges(self):
        out = set()
        for run in self.all_runs():
            out.update(run.doc.get("recordedMerges", []))
        return out

    def all_runs(self):
        return list(self.runs.values())

    def _git_plain(self, repo, *args):
        return subprocess.run(["git", "-C", repo] + list(args), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, env=self.environ)

    # ---- pre-flight (all or nothing; nothing is launched on a refusal) ---------------
    def read_config_text(self, repo=None):
        path = os.path.join(repo or self.primary, ".adlc", "config.yml")
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def integration_branch(self, repo):
        text = self.read_config_text(repo)
        branches = eg.config_section(text, "branches")
        if isinstance(branches, dict) and branches.get("integration"):
            return es.valid_branch(str(branches["integration"]), "branches.integration")
        gcp = eg.config_section(text, "gcp")
        if isinstance(gcp, dict) and gcp.get("staging_project"):
            return "staging"
        workflows = os.path.join(repo, ".github", "workflows")
        if os.path.isdir(workflows):
            for name in sorted(os.listdir(workflows)):
                try:
                    with open(os.path.join(workflows, name), encoding="utf-8") as fh:
                        if "verify-head-ref" in fh.read():
                            return "staging"
                except OSError:
                    continue
        return "main"

    def registry(self, text):
        repos = eg.config_section(text, "repos")
        order = eg.config_section(text, "merge_order")
        if not isinstance(repos, dict) or len(repos) < 2:
            rid = es.require(es.VALID_REPO_ID, os.path.basename(self.primary), "repo id")
            return {rid: {"path": self.primary, "primary": True}}, [rid]
        out = {}
        for rid, spec in repos.items():
            es.require(es.VALID_REPO_ID, rid, "repo id")
            spec = spec if isinstance(spec, dict) else {}
            if str(spec.get("primary", "")).lower() == "true":
                out[rid] = {"path": self.primary, "primary": True}
                continue
            path = os.path.realpath(os.path.join(self.primary, str(spec.get("path", ""))))
            if self._git_plain(path, "rev-parse", "--git-dir").returncode != 0:
                raise Refused("sibling repo %s is not a git repository: %s" % (rid, path))
            out[rid] = {"path": path, "primary": False}
        if not any(v["primary"] for v in out.values()):
            raise Refused(".adlc/config.yml marks no repo primary")
        listed = [r for r in (order or []) if r in out] if isinstance(order, list) else []
        return out, listed + [r for r in out if r not in listed]

    def resolve_provider(self, box):
        if self.environ.get("ADLC_FORGE_MOCK") == "1":
            return self.environ.get("ADLC_FORGE_MOCK_PROVIDER", "github")
        res = box.partial("forge.sh", "adlc_forge_provider", [self.primary], self.primary)
        name = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
        if res.returncode != 0 or not name:
            raise Refused("the forge provider could not be resolved: %s" % res.stderr.strip())
        return name

    def preflight(self, reqs, harness="claude", shared=False, allow_unprotected=False, flags=(),
                  allow_unverified=False):
        batch = Batch()
        self.allow_unverified = bool(allow_unverified)
        for req in reqs:
            try:
                es.valid_req(req)
            except es.SafetyError as exc:
                raise Refused(str(exc))
        if not reqs:
            raise Refused("no REQ to run")
        try:
            batch.adapter = ea.load(harness, self.toolkit)
        except ea.ExecRefused as exc:
            raise Refused(str(exc))
        adapter = batch.adapter
        if adapter.strategy != "worktree":
            raise Refused("working_copy %s has no engine arm yet: %s" % (adapter.strategy,
                                                                         ea.SIBLING_REQ))
        reach = adapter.adapter.get("sandbox_can_reach_common_gitdir")
        if reach != "true":
            raise Refused("working_copy worktree needs sandbox_can_reach_common_gitdir: true, "
                          "and harness/%s.yml says %s" % (adapter.name, reach))
        if adapter.trust_grant not in ("none", et.USER_CONFIG_ENTRY):
            raise Refused("exec.trust_grant %s has no engine arm yet: %s"
                          % (adapter.trust_grant, ea.SIBLING_REQ))
        if adapter.trust_grant not in et.NO_FILE:
            # REQ-662 BR-5, before any working copy is made: while REQ-664's recovery marker
            # exists a probe is editing the same user config, or died editing it, and a trust
            # file the grant could not edit refuses here. Writes nothing.
            config, marker = self._trust_file(adapter)
            try:
                et.preflight(adapter.trust_grant, config, marker)
            except et.TrustRefused as exc:
                raise Refused("harness %s: %s" % (adapter.name, exc))
        batch.binary = shutil.which(adapter.binary, path=self.environ.get("PATH", ""))
        if not batch.binary:
            raise Refused("%s is not on PATH" % adapter.binary)
        # REQ-662 BR-11: recomputed from ToolkitRoot's result file, the adapter and the
        # binary's version. --allow-unverified lets the batch on; every check below still runs.
        batch.verdict = self._gate(adapter, batch.binary, "launch",
                                   allow_unverified=self.allow_unverified)
        batch.allow_unverified = self.allow_unverified
        if batch.verdict.notes:
            # A `recorded` block is not gated on the binary's version (BR-1): a difference is
            # said once here, where the operator watches the launch, and refuses nothing.
            self.say("NOTE: harness %s: %s; verification: recorded, so the launch goes on"
                     % (adapter.name, "; ".join(batch.verdict.notes)))
        # Every launch reads only the engine's settings file. Without the flags that do
        # that, the operator's and the project's own allowlists would widen the tiers. An
        # adapter with no isolation flags is isolated by its config surfaces instead, which the
        # engine renders whole before every launch and resume (REQ-662 ADR-4).
        help_out = subprocess.run([batch.binary, "--help"], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, universal_newlines=True,
                                  env=self.environ).stdout
        if adapter.block.get("config_isolation") and not adapter.isolation_available(help_out):
            raise Refused("%s --help does not list the config-isolation flags %s, so a launch "
                          "would read settings files the engine does not control (BUG-260)"
                          % (adapter.binary, " ".join(adapter.block.get(
                              "config_isolation_help", []))))
        text = self.read_config_text()
        try:
            batch.config = eg.exec_config(text)
            batch.repos, batch.order = self.registry(text)
        except eg.GateError as exc:
            raise Refused(str(exc))
        batch.flags = [str(f) for f in batch.config["harness_flags"]] + list(flags)
        # The probe result reaches the render, so only a valid deny_under_allow pass restores
        # a wrapper allow (REQ-662 ADR-3). Read from ToolkitRoot, never a working copy.
        batch.result = ev.read_result(adapter, self.toolkit)
        try:
            ea.refuse_forbidden(batch.flags, adapter.forbidden)
            # A flag outside the adapter's operator_flags never reaches the harness: the final
            # argv is closed-world (REQ-662 BR-16), so it is refused here, before any launch.
            adapter.operator_tokens(batch.flags)
            adapter.check_templates()
            adapter.tiers("feat/preflight", batch.config["allow_extra"], result=batch.result)
            batch.exec_files = adapter.rule_files("feat/preflight", batch.config["allow_extra"],
                                                  batch.result)
            report = adapter.exec_report(batch.result, batch.verdict, batch.allow_unverified)
        except ea.ExecRefused as exc:
            raise Refused(str(exc))
        self._judge_render(adapter, batch, report)
        # The user config is scanned here too, before anything is prepared; each working copy's
        # is scanned at its launch, once it exists (REQ-662 BR-16).
        self._bypass_check(adapter, [], "launch")
        hit = ea.sandbox_setting(adapter, self.primary, el.read_json)
        if hit:
            raise Refused("the harness sandbox is on in %s: a worktree has not been shown to "
                          "reach the common git dir with it, so exec is refused (OQ-4)" % hit)
        batch.shared = shared
        batch.allow_unprotected = allow_unprotected
        token_var = batch.config["child_gh_token"]
        if token_var:
            batch.child_token = self.environ.get(str(token_var))
        if not shared and not batch.child_token:
            raise Refused("no scoped child token: set sprint.exec.child_gh_token to the name of "
                          "a variable holding one, or pass --shared-credentials")
        scratch = el.create_run_dir(self.environ)
        try:
            box = es.Toolbox(scratch, self.toolkit, self.environ)
            box.prepare()
            batch.provider = self.resolve_provider(box)
            if batch.provider != "github":
                raise Refused("--exec on %s is refused until the forge adapter can pin a merge "
                              "(BR-26)" % batch.provider)
            box.provider = batch.provider
            if self.environ.get("ADLC_FORGE_MOCK") != "1" and "gh" not in box.tools:
                raise Refused("gh is not on PATH")
            origin = self._git_plain(self.primary, "remote", "get-url", "origin").stdout.strip()
            parts = es.origin_parts(origin)
            batch.origin = {"owner": parts[1], "name": parts[2]}
            batch.host = MOCK_HOST if self.environ.get("ADLC_FORGE_MOCK") == "1" else parts[0]
            ib = self.integration_branch(self.primary)
            extra = {"GH_TOKEN": batch.child_token} if batch.child_token else None
            value = box.forge("adlc_forge_branch_protection", [ib], self.primary,
                              extra).stdout.strip() or "unknown"
            batch.protection = value if value in ("protected", "unprotected") else "unknown"
            # What a file-rendering adapter renders untracked is hidden per working copy with
            # `git config --worktree`, which needs extensions.worktreeConfig in each repo: set
            # here when absent, and left set (REQ-662 BR-17). No other adapter reaches this.
            if esf.renders_files(adapter.block):
                for rid, spec in sorted(batch.repos.items()):
                    try:
                        batch.worktree_config[rid] = esf.worktree_config(box, spec["path"])
                    except esf.SurfaceRefused as exc:
                        raise Refused("harness %s: %s, so nothing is launched (REQ-662 BR-17)"
                                      % (adapter.name, exc))
                    if batch.worktree_config[rid] == "enabled":
                        self.say("NOTE: set %s = true in %s's git config, so harness %s's "
                                 "renders can be hidden per working copy; it stays set "
                                 "(REQ-662 BR-17)" % (esf.WORKTREE_CONFIG, spec["path"],
                                                      adapter.name))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if batch.deny_unsupported and batch.config["require_branch_protection"] and \
                batch.protection != "protected":
            # --allow-unprotected accepts a direct push; it does not also accept a one-way
            # move the harness cannot deny (REQ-662 BR-4).
            raise Refused("harness %s has no deny for %s, sprint.exec.require_branch_protection "
                          "is set and %s on %s is %s, so the forge would not stop those moves "
                          "either: nothing is launched (REQ-662 BR-4); --allow-unprotected does "
                          "not cover a deny_unsupported entry"
                          % (adapter.name, _commands(batch.deny_unsupported), ib, self.primary,
                             batch.protection))
        if batch.protection != "protected":
            line = "%s on %s is %s, so a direct push from a run is not stopped by the forge " \
                   "(%s)" % (ib, self.primary, batch.protection, "Rule B")
            if batch.config["require_branch_protection"] and not allow_unprotected:
                raise Refused(line + "; pass --allow-unprotected to accept that for this run")
            self.say("WARNING: " + line)
        # Last, once nothing else refuses: the toolkit's user policy file, written whole and
        # atomically under the lock and its folder recorded, or the run refused when the folder
        # is not what the engine last recorded (REQ-662 BR-4).
        if batch.exec_files is not None and batch.exec_files.user_policy_file is not None:
            try:
                batch.policy = esf.ensure_policy_file(adapter, self.environ,
                                                      batch.exec_files.user_policy_file)
            except esf.SurfaceRefused as exc:
                raise Refused(str(exc))
        self.batch = batch
        return batch

    def _judge_render(self, adapter, batch, report):
        """REQ-662 BR-3 and BR-4 on the exec-scope render, before anything is launched.

        Every ``deny_unsupported`` entry is a loud line, whatever refuses the run after it. A
        loss ``accepted_fidelity`` does not declare at ``exec`` refuses the run; a ``recorded``
        block (BR-1) predates the comparison and its engine behaviour is unchanged, so its
        losses are in each run's report and refuse nothing. A local destructive
        ``deny_unsupported`` entry refuses the run, and so does the whole deny tier under
        --allow-unverified. The branch-protection rule waits for protection to be read.

        A deny is defense in depth and never the gate (Rule B): these refusals keep a one-way
        move the harness cannot deny from resting on nothing but the approval halt."""
        batch.fidelity = report.report
        batch.deny_unsupported = report.deny_unsupported
        for item in report.deny_unsupported:
            self.say("WARNING: deny_unsupported: harness %s has no deny for `%s` (%s): %s%s"
                     % (adapter.name, item.command, item.entry, item.reason,
                        "; a local destructive move" if item.destructive else ""))
        if report.undeclared and adapter.block.get("verification") != "recorded":
            raise Refused("harness %s: the exec-scope render loses what accepted_fidelity does "
                          "not declare at exec: %s; declare each one or change the render, so "
                          "nothing is launched (REQ-662 BR-3)"
                          % (adapter.name, "; ".join(f.format() for f in report.undeclared)))
        if report.whole_tier:
            raise Refused("harness %s: every deny-tier entry is deny_unsupported (%s), so "
                          "nothing is launched (REQ-662 BR-4)" % (adapter.name,
                                                                   report.whole_tier))
        destructive = [i for i in report.deny_unsupported if i.destructive]
        if destructive:
            raise Refused("harness %s has no deny for the local destructive move %s, and a "
                          "forge's branch protection does not reach a working copy, so nothing "
                          "is launched (REQ-662 BR-4)" % (adapter.name, _commands(destructive)))

    def _log_render(self, box, batch):
        """Each run's log carries the pre-flight's fidelity report and its deny_unsupported
        entries (REQ-662 BR-3, BR-4)."""
        box.log("fidelity_report", batch.fidelity, None, 0)
        for item in batch.deny_unsupported:
            box.log("deny_unsupported", [item.entry, item.command, item.reason], None, 0)

    # ---- launch ----------------------------------------------------------------------
    def prepare(self, req, batch):
        """Everything up to the spawn: a refusal here has started nothing."""
        run_dir = el.create_run_dir(self.environ)
        try:
            return self._prepare(req, batch, run_dir)
        except (Refused, es.SafetyError, eg.GateError):
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

    def _prepare(self, req, batch, run_dir):
        box = Toolbox(run_dir, self.toolkit, self.environ)
        box.prepare(batch.provider)
        repos = {}
        launch_tip = {}
        ibs = {}
        for rid, spec in batch.repos.items():
            box.register_tree(spec["path"])
            ib = self.integration_branch(spec["path"])
            ibs[rid] = ib
            eg.fetch_integration(box, spec["path"], ib)
            launch_tip[rid] = eg.rev_parse(box, spec["path"], "refs/remotes/origin/%s" % ib)
            repos[rid] = {"path": spec["path"], "primary": spec["primary"],
                          "workingCopy": os.path.join(spec["path"], ".worktrees", req)}
        rid = next(k for k, v in batch.repos.items() if v["primary"])
        specs = box.git(self.primary, ["ls-tree", "--name-only", "refs/remotes/origin/%s" % ibs[rid],
                                       ".adlc/specs/"]).stdout.split("\n")
        hits = [ln for ln in specs if os.path.basename(ln).startswith(req + "-")]
        if len(hits) != 1:
            raise Refused("%s has no spec on origin/%s: land its spec PR first" % (req, ibs[rid]))
        spec_dir = hits[0].strip()
        slug = es.require(es.VALID_SLUG, os.path.basename(spec_dir)[len(req) + 1:], "slug")
        branch = es.valid_branch("feat/%s-%s" % (req, slug))
        spec_text = eg.show_blob(box, self.primary, "origin/%s" % ibs[rid],
                                 spec_dir + "/requirement.md") or ""
        spec_status = eg.frontmatter_flag(spec_text, "status")
        lane = eg.frontmatter_flag(spec_text, "lane") or "full"
        if spec_status == "complete" or (spec_status == "draft" and lane != "lite"):
            raise Refused("%s is %s on origin/%s, not approved" % (req, spec_status, ibs[rid]))
        for repo_id, spec in repos.items():
            self._collision_check(box, spec["path"], spec["workingCopy"], branch)
        doc = {"req": req, "primary": self.primary, "harness": batch.adapter.name,
               "strategy": batch.adapter.strategy, "slug": slug, "branch": branch,
               "integrationBranch": ibs[rid], "integrationBranches": ibs, "repos": repos,
               "order": batch.order, "specDir": spec_dir, "lane": lane, "config": batch.config,
               "launchTip": launch_tip, "forgeHost": batch.host, "origin": batch.origin,
               "sharedCredentials": batch.shared, "allowUnprotected": batch.allow_unprotected,
               "protection": batch.protection, "binary": batch.binary, "flags": batch.flags,
               "status": "running", "supervisorDir": self.sup_dir, "launches": 0,
               "recordedMerges": [], "ledgerHash": None,
               "exec": {"engine": "exec", "harness": batch.adapter.name,
                        "strategy": batch.adapter.strategy,
                        "workingCopy": repos[rid]["workingCopy"], "pid": None,
                        "closeOutPid": None, "sessionId": None, "startedAt": el.now(),
                        "promptPath": "prompt.txt", "logPath": "stdout.json", "stalledAt": None,
                        "trustMechanism": batch.adapter.trust_grant, "trustGrantedAt": None,
                        "trustRevokedAt": None, "exitCode": None, "exitClass": None,
                        "abortedBy": None, "abortedAt": None}}
        if batch.policy is not None:
            # What this run checks the user policy folder against, before each launch and
            # resume and at exit and the halt (REQ-662 BR-4). Absent: no policy file.
            doc["policyManifest"] = batch.policy
        if batch.worktree_config:
            # Per repo id, whether the pre-flight found extensions.worktreeConfig or set it
            # (REQ-662 BR-17). Absent for an adapter that renders nothing into a working copy.
            doc["worktreeConfig"] = dict(batch.worktree_config)
        run = Run(run_dir, doc)
        try:
            data = ep.pipeline_prompt(self.toolkit, self.primary, req, branch, self.primary,
                                      repos[rid]["workingCopy"], adapter=batch.adapter)
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            self._prompt_refused(req, exc)
            raise Refused(str(exc))
        el.atomic_write(run.file("prompt.txt"), data)
        os.makedirs(run.file("gh-empty"), exist_ok=True)
        self._log_render(box, batch)
        run.save()
        self.runs[req] = run
        self.boxes[req] = box
        self.adapters[batch.adapter.name] = batch.adapter
        return run

    def _prompt_refused(self, req, exc):
        """Say a prompt refusal; an unrouted fence is ``exec_prompt_refused`` (REQ-682 BR-8)."""
        if isinstance(exc, ep.ExecPromptRefused):
            self.say("%s %s" % (req, exc))

    def _collision_check(self, box, repo, path, branch):
        out = box.git(repo, ["worktree", "list", "--porcelain"]).stdout
        current = None
        for line in out.splitlines():
            if line.startswith("worktree "):
                current = line[len("worktree "):]
            elif current == path and line.startswith("branch "):
                if line[len("branch "):] != "refs/heads/" + branch:
                    raise Refused("worktree path in use by %s: %s" % (line[7:], path))
            elif current == path and line == "detached":
                raise Refused("worktree path in use by a detached HEAD: %s" % path)

    def _make_worktree(self, box, repo, path, branch, ib):
        listed = box.git(repo, ["worktree", "list", "--porcelain"]).stdout
        if ("worktree %s\n" % path) in listed:
            return
        have = box.git(repo, ["rev-parse", "--verify", "-q", "refs/heads/%s" % branch])
        args = ["worktree", "add"]
        if have.returncode == 0:
            args += [path, branch]
        else:
            args += ["--no-track", "-b", branch, path, "refs/remotes/origin/%s" % ib]
        res = box.git(repo, args)
        if res.returncode != 0:
            raise Refused("worktree add failed in %s: %s" % (repo, res.stderr.strip()))

    def _trust_file(self, adapter):
        """``(trust file, REQ-664 marker)`` of a mechanism that writes the user config: the
        adapter's ``paths.config.user`` and ``$ADLC_HOME`` expanded with the run's environment,
        the one the harness is handed (REQ-662 BR-5, LESSON-777)."""
        try:
            config = et.user_config_path(adapter.adapter, self.environ)
            home = esf.user_path("$ADLC_HOME", self.environ)
        except (et.TrustRefused, esf.SurfaceRefused) as exc:
            raise Refused("harness %s: %s" % (adapter.name, exc))
        return config, et.probe_marker(home, adapter.name)

    def grant_trust(self, run, wc=None):
        """Per run, per working copy: ``wc``, by default the run's own, and the close-out's
        separately; only the run's own sets ``exec.trustGrantedAt`` (REQ-662 BR-5, ADR-5).
        `none` records the moment and writes nothing. A mechanism that writes the user config
        appends one block for the resolved working copy through ``exec_trust``, under its lock.
        The grant is kept in the run record under ``trustGrants``, outside ``exec``, which state
        copies, and is recorded first as the grant built from the path alone, so a supervisor
        that dies inside the write leaves a record revoke can act on. A refusal is
        :class:`Refused`, and nothing was written."""
        own = wc is None
        wc = run.wc if own else wc
        mechanism = run.exec["trustMechanism"]
        box = self.box(run)
        if mechanism in et.NO_FILE:
            if own:
                run.exec["trustGrantedAt"] = el.now()
                run.exec["trustRevokedAt"] = None
            box.log("trust_granted", [mechanism], wc, 0)
            return
        adapter = self.adapter(run)
        config, marker = self._trust_file(adapter)
        # Every working copy is made as <repo>/.worktrees/<name>, the root its path must resolve
        # under.
        root = os.path.dirname(wc)
        grants = run.doc.setdefault("trustGrants", {})
        before = grants.get(wc), run.exec.get("trustGrantedAt"), run.exec.get("trustRevokedAt")
        try:
            pending = et.Grant(mechanism, config, et.check_path(wc, root), marker=marker)
            grants[wc] = pending.to_doc()
            if own:
                run.exec.update({"trustGrantedAt": pending.granted_at, "trustRevokedAt": None})
            run.save()
            grant = et.grant(mechanism, config, wc, root, marker)
        except et.TrustRefused as exc:
            if before[0] is None:
                grants.pop(wc, None)
            else:
                grants[wc] = before[0]
            if own:
                run.exec.update({"trustGrantedAt": before[1], "trustRevokedAt": before[2]})
            run.save()
            raise Refused("harness %s: the trust grant for %s is refused: %s"
                          % (adapter.name, wc, exc))
        grants[wc] = grant.to_doc()
        if own:
            run.exec["trustGrantedAt"] = grant.granted_at
            run.exec["trustRevokedAt"] = None
        run.save()
        box.log("trust_granted", [mechanism], wc, 0,
                detail={"mechanism": mechanism, "config": config, "path": grant.path,
                        "pre_existing": grant.pre_existing, "adopted": grant.adopted,
                        "created": grant.created})

    def _revoke_grants(self, run, only=None):
        """Each trust grant the run record holds (``only``: that working copy's alone), revoked
        through ``exec_trust`` and dropped from the record. Each is logged ``trust_revoked``
        with what revoke found, and a warning also goes to the run's notes. A grant whose
        revoke could not finish (the lock, a symlink) stays recorded for the next revoke, and is
        said. Returns the working copies still held."""
        grants = run.doc.get("trustGrants") or {}
        targets = [w for w in ([only] if only else list(grants)) if w in grants]
        for wc in targets:
            doc = grants[wc]
            try:
                grant = et.Grant.from_doc(doc)
            except et.TrustRefused as exc:
                del grants[wc]
                run.doc.setdefault("notes", []).append(
                    "the trust grant record for %s does not read back (%s), so it is dropped: "
                    "check %s by hand" % (wc, exc, doc.get("config") if isinstance(doc, dict)
                                          else "the user config"))
                continue
            try:
                revoked = et.revoke(grant)
            except et.TrustRefused as exc:
                run.doc.setdefault("notes", []).append(
                    "the trust revoke for %s did not finish, and the grant stays recorded for "
                    "the next one: %s" % (wc, exc))
                self.say("WARNING: %s trust revoke for %s did not finish: %s" % (run.req, wc, exc))
                continue
            del grants[wc]
            self.box(run).log("trust_revoked", [grant.mechanism], wc, 0,
                              detail={"status": revoked.status, "warning": revoked.warning,
                                      "path": grant.path, "config": grant.config})
            if revoked.warning:
                run.doc.setdefault("notes", []).append("trust revoke for %s: %s"
                                                       % (wc, revoked.warning))
        if targets:
            run.save()
        return [w for w in ([only] if only else grants) if w in grants]

    def revoke_trust(self, run, wc=None):
        """``wc``'s grant alone (the close-out's), or every grant the run holds and then
        ``exec.trustRevokedAt``, set whatever revoke found once no grant is held (REQ-662
        BR-5). Safe to call again. `none` writes nothing and records the moment."""
        mechanism = run.exec["trustMechanism"]
        held = self._revoke_grants(run, wc)
        if wc is not None:
            if mechanism in et.NO_FILE:
                self.box(run).log("trust_revoked", [mechanism], wc, 0)
            return
        if not held and run.exec.get("trustGrantedAt") and not run.exec.get("trustRevokedAt"):
            run.exec["trustRevokedAt"] = el.now()
            if mechanism in et.NO_FILE:
                self.box(run).log("trust_revoked", [mechanism], run.wc, 0)

    # ---- REQ-662 ADR-4: config surfaces, rule files and the user policy folder -------------
    @staticmethod
    def _working_copies(run):
        """Every repo's working copy of the run: each is a root the harness is handed."""
        return [spec["workingCopy"] for spec in run.doc["repos"].values()]

    def _bypass_check(self, adapter, roots, where, run=None):
        """BR-16: a ``bypass_config_keys`` key set to anything but the toolkit's own value, in
        the user config or the config of a working copy in ``roots``, refuses the launch or
        the resume, and so does a config that cannot be read with certainty. With a ``run``,
        its log names the refusal as ``adapter_refused``."""
        try:
            hits = esf.bypass_scan(adapter, roots, self.environ)
        except esf.SurfaceRefused as exc:
            reason, rows = str(exc), [{"path": exc.path, "key": None, "value": None}]
        else:
            if not hits:
                return
            reason = "; ".join(esf.hit_text(adapter.adapter, hit) for hit in hits)
            rows = [hit._asdict() for hit in hits]
        if run is not None:
            self.box(run).log("adapter_refused", [adapter.name, rows[0]["path"] or ""], None,
                              None, detail={"harness": adapter.name, "reason": reason,
                                            "where": where, "hits": rows})
        raise Refused(reason)

    def prepare_surfaces(self, run, wcs, branch, where):
        """Before a launch (``where`` ``launch``) or a resume (``resume``), in this order: the
        user policy folder against the run's record, where any change refuses (BR-4); the
        bypass scan (BR-16); then each working copy in ``wcs`` brought to the exec render,
        whole, with the rule file rendered for ``branch``. Its manifest goes into the run
        record, and each path the render wrote or removed is logged ``rule_file_rerendered``,
        ``checksum_matched`` false where it was not already the render (BR-4, BR-15). A
        refusal is :class:`Refused`, and nothing is launched. An adapter with no surface, no
        rule file and no policy file writes and logs nothing (BR-1)."""
        adapter = self.adapter(run)
        record = run.doc.get("policyManifest")
        if record:
            try:
                problems = esf.check_policy(record)
            except esf.SurfaceRefused as exc:
                raise Refused(str(exc))
            if problems:
                raise Refused(esf.policy_refusal(adapter.adapter, problems, where))
        self._bypass_check(adapter, wcs, where, run)
        if not (adapter.block.get("config_surfaces") or adapter.block.get("rule_file")):
            return
        try:
            files = adapter.rule_files(branch, run.doc["config"]["allow_extra"],
                                       ev.read_result(adapter, self.toolkit))
            plan = esf.working_copy_render(adapter, files, self.toolkit)
        except (ea.ExecRefused, esf.SurfaceRefused) as exc:
            raise Refused(str(exc))
        box = self.box(run)
        manifests = run.doc.setdefault("surfaces", {})
        for wc in wcs:
            try:
                manifest, changes = esf.render(wc, plan, adapter.block)
            except (esf.SurfaceRefused, OSError) as exc:
                raise Refused("harness %s: the %s is refused: %s" % (adapter.name, where, exc))
            manifests[wc] = manifest
            for change in changes:
                box.log("rule_file_rerendered", [adapter.name, change.path], wc, None,
                        detail={"harness": adapter.name, "path": change.path,
                                "checksum_matched": change.found == change.expected,
                                "expected": change.expected, "found": change.found,
                                "where": where})
            self._hide(run, wc, manifest, where)
        run.save()

    def verify_surfaces(self, run, wcs, where):
        """At exit (``where`` ``exit``) and at the halt (``halt``): each working copy in ``wcs``
        against the manifest its last render recorded, and the user policy folder against the
        run's record. Each change is a ``config_surface_violation``: logged, and recorded as a
        Rule B protocol violation, which the halt reports (BR-15; REQ-659 owns what one does).
        Nothing is repaired here: the next launch or resume re-renders. Returns the changes."""
        adapter = self.adapter(run)
        block = adapter.block
        found = []
        try:
            for wc in wcs:
                manifest = (run.doc.get("surfaces") or {}).get(wc)
                if manifest:
                    found += [(wc, change) for change in esf.verify(wc, manifest)]
            record = run.doc.get("policyManifest")
            if record:
                found += [(None, change) for change in esf.check_policy(record)]
        except (esf.SurfaceRefused, OSError) as exc:
            run.violation("config_surface_violation at %s: the surfaces could not be verified: "
                          "%s" % (where, exc))
        for wc, change in found:
            self.box(run).log("config_surface_violation", [adapter.name, change.path], wc, None,
                              detail={"harness": adapter.name, "path": change.path,
                                      "expected": change.expected, "found": change.found,
                                      "where": where,
                                      "rules_reload": block.get("rules_reload"),
                                      "effective_mid_run": esf.reload_effective(block)})
            run.violation(esf.violation_text(change, block, where))
        return found

    # ---- REQ-662 BR-17: what the render wrote, hidden from git and restored ----------------
    @staticmethod
    def _repo_of(run, wc):
        """The repo a working copy of the run belongs to; the close-out's is the primary's."""
        for spec in run.doc["repos"].values():
            if spec["workingCopy"] == wc:
                return spec["path"]
        return run.primary_path

    def _gitdir_write(self, run, repo, write):
        """``write()``, the engine's own change to a file REQ-659's common gitdir checksum
        covers (a working copy's ``config.worktree``, or the worktree's removal), with every
        box of this orchestrator's runs carried from the checksum just before it to the one
        just after. A box whose checksum already differed keeps its own, so a change the engine
        did not make still reads as a violation. Every check waits meanwhile."""
        tree = self.box(run).trees.get(repo)
        if tree is None:
            return write()
        with GITDIR_LOCK:
            before = es.gitdir_digest(tree["common"])
            try:
                return write()
            finally:
                after = es.gitdir_digest(tree["common"])
                if after != before:
                    for other in self.all_runs():
                        try:
                            box = self.box(other)
                        except (OSError, ValueError, KeyError):
                            continue        # a run whose toolbox is gone checks nothing
                        held = [t for t in box.trees.values()
                                if t["common"] == tree["common"] and t["digest"] == before]
                        for entry in held:
                            entry["digest"] = after
                        if held:
                            box.save()

    def _hide(self, run, wc, manifest, where):
        """BR-17, after each render: the render in ``wc`` hidden from git, best effort
        (``exec_surfaces.hide``). The run record keeps, per working copy under ``hidden``, the
        blob oids recorded at launch and what was hidden, which restoring needs. The excludes
        file is the run directory's, outside the working copy. A refusal is :class:`Refused`."""
        box = self.box(run)
        repo = self._repo_of(run, wc)
        record = run.doc.setdefault("hidden", {}).setdefault(wc, {})
        excludes = run.file("excludes-%s" % hashlib.sha256(wc.encode("utf-8")).hexdigest()[:12])
        try:
            esf.hide(box, repo, wc, manifest, record, excludes, self.environ,
                     lambda write: self._gitdir_write(run, repo, write))
        except (esf.SurfaceRefused, OSError) as exc:
            raise Refused("harness %s: the %s is refused: hiding the render from git in %s: %s"
                          % (self.adapter(run).name, where, wc, exc))
        box.log("exec_paths_hidden", [self.adapter(run).name, wc], wc, None,
                detail={"skipWorktree": record["skipWorktree"], "untracked": record["untracked"],
                        "excludesFile": record.get("excludesFile"), "where": where})

    def restore_surfaces(self, run, wcs=None):
        """BR-17: each working copy in ``wcs`` (by default every one the run hid a render in)
        back to what it was at launch, from the blob oids the run record holds, never HEAD
        (``exec_surfaces.restore``). Called before the final push and at cleanup, and where a
        run ends with its working copy left to a person (rejected, aborted, failed). A path that
        cannot be restored is a note on the run, and nothing stops. A run that hid nothing
        (every flags-only adapter, BR-1) does nothing here."""
        records = run.doc.get("hidden") or {}
        if not records:
            return
        box = self.box(run)
        for wc in sorted(records):
            if wcs is not None and wc not in wcs:
                continue
            repo = self._repo_of(run, wc)
            try:
                done = esf.restore(box, repo, wc, records[wc], run.file("restore"),
                                   lambda write: self._gitdir_write(run, repo, write))
            except (esf.SurfaceRefused, OSError, es.RuleBViolation) as exc:
                done = {"restored": [], "removed": [], "unmarked": [], "problems": [str(exc)]}
            for problem in done["problems"]:
                run.doc.setdefault("notes", []).append(
                    "restoring %s after the run: %s (REQ-662 BR-17)" % (wc, problem))
            if any(done.values()):
                box.log("exec_paths_restored", [self.adapter(run).name, wc], wc, None,
                        detail=done)
        run.save()

    def _argv(self, run, log_name, resume=None, wc=None, branch=None, write_roots=None,
              add_dir=None, operator=None):
        """The launch argv, or with ``resume`` the resume argv, filled from the adapter's
        templates and checked closed-world (REQ-662 ADR-7). ``log_name`` is the launch's stdout
        file, which names its ``{last_message}`` file. Without ``write_roots``, every repo's
        working copy, and nothing else, is writable (BUG-265). ``operator`` defaults to the
        run's --harness-flag tokens."""
        adapter = self.adapter(run)
        branch = branch or run.doc["branch"]
        if write_roots is None:
            write_roots = [spec["workingCopy"] for spec in run.doc["repos"].values()]
            write_roots += [add_dir] if add_dir else []
        allow, deny = adapter.tiers(branch, run.doc["config"]["allow_extra"],
                                    write_roots=write_roots,
                                    read_roots=[os.path.realpath(self.toolkit)],
                                    result=ev.read_result(adapter, self.toolkit))
        # Isolated like the close-out (BR-25): the tiers are the whole policy (BUG-260).
        settings = run.file("settings.json")
        el.atomic_json(settings, adapter.settings_document(allow, deny))
        last = run.last_message(log_name)
        if os.path.lexists(last):
            os.unlink(last)         # never read an earlier launch's message as this one's
        values = {"worktree": wc or run.wc, "last_message": last, "branch": branch}
        return adapter.launch_argv(run.doc["binary"], allow, deny, resume=resume,
                                   extra=run.doc["flags"] if operator is None else operator,
                                   add_dir=add_dir, settings=settings, values=values)

    def _child_env(self, run):
        adapter = self.adapter(run)
        token = None
        if not run.doc["sharedCredentials"]:
            var = str(run.doc["config"]["child_gh_token"])
            token = self.environ.get(var)
            if not token:
                raise Refused("%s is not set in this shell, and the child's token comes from it"
                              % var)
        env = adapter.child_env(self.environ, run.req, token, run.file("gh-empty"),
                                run.doc["sharedCredentials"])
        env[RUN_TAG_ENV] = run_tag(run.path)
        return env

    def _spawn(self, run, argv, prompt, cwd, stem):
        env = self._child_env(run)
        box = self.box(run)
        box.log("exec_launch", argv, cwd, None)
        with open(run.file(stem + ".json"), "wb") as out, \
                open(run.file(stem + ".stderr.log"), "wb") as err, \
                open(prompt, "rb") as stdin:
            return subprocess.Popen(argv, stdin=stdin, stdout=out, stderr=err, cwd=cwd, env=env,
                                    start_new_session=True)

    # ---- REQ-662 BR-11: the verdict at every launch, at the close-out and at approve ---------
    def _gate(self, adapter, binary, where, run=None, allow_unverified=False, invocation=None):
        """The adapter's verdict now (``exec_verify.verdict``). Unverified is refused, naming
        each problem, unless ``allow_unverified`` and ``where`` is a launch; then the launch
        goes on with one loud line, and the run record keeps ``invocation`` (by default this
        one), which the halt copies into the ledger. ``approve`` never honours it.

        ``allow_unverified`` is what the invocation making this launch received: `run`'s flag
        for its own pre-flight and starts, an `answer`'s for its relaunch, and nothing for the
        close-out or a relaunch an `approve` drains (REQ-662 BR-18). A flag this supervisor's
        `run` received never reaches a launch another invocation asks for."""
        verdict = ev.recompute(adapter, self.toolkit, binary, self.environ)
        self.verdicts[adapter.name] = verdict
        if verdict.verified:
            return verdict
        if where == "approve" or not allow_unverified:
            hint = {"approve": "--allow-unverified covers launches only, never approve",
                    "relaunch": "`adlc sprint-exec answer <REQ> <text> --allow-unverified` "
                                "relaunches it anyway",
                    "close-out": "--allow-unverified does not reach the close-out"}.get(
                where, "`adlc sprint-exec run --allow-unverified` launches it anyway")
            raise Refused("harness %s is unverified, so the %s is refused (REQ-662 BR-11): %s; %s"
                          % (adapter.name, where, verdict.summary(), hint))
        if run is not None:
            self.say("WARNING: --allow-unverified: %s %s on harness %s, which is UNVERIFIED: %s"
                     % (run.req, where, adapter.name, ", ".join(verdict.subjects)))
            run.doc.setdefault("allowUnverified", []).append(
                el.allow_unverified_entry(invocation or self.invocation, where,
                                          verdict.subjects))
            run.save()
        return verdict

    def spawn(self, run):
        try:
            # A pending start is the `run` invocation's own launch: its flag, and no other.
            self._gate(self.adapter(run), run.doc["binary"], "launch", run,
                       self.allow_unverified)
        except Refused as exc:
            # The verdict changed after the pre-flight: this REQ starts nothing.
            self._terminal(run, "failed", "setup-error", {}, note=str(exc))
            return
        box = self.box(run)
        for rid, spec in run.doc["repos"].items():
            self._make_worktree(box, spec["path"], spec["workingCopy"], run.doc["branch"],
                                run.doc["integrationBranches"][rid])
        try:
            self.prepare_surfaces(run, self._working_copies(run), run.doc["branch"], "launch")
        except Refused as exc:
            self.say("%s refused before launch: %s" % (run.req, exc))
            self._terminal(run, "failed", "setup-error", {}, note=str(exc))
            return
        try:
            self.grant_trust(run)
            self._launch_first(run, "prompt.txt")
        except (Refused, ea.ExecRefused) as exc:
            # The worktrees exist and trust may be granted: a grant the trust module refuses
            # (it wrote nothing) or an argv the closed-world check refuses ends this REQ, its
            # trust revoked (`_terminal`), and the supervisor goes on (REQ-662 BR-5, BR-16).
            self.say("%s refused at launch: %s" % (run.req, exc))
            self._terminal(run, "failed", "setup-error", {}, note=str(exc))

    def _launch_first(self, run, prompt_name):
        launch = run.doc["launches"] + 1
        stem = "stdout" if launch == 1 else "stdout.%d" % launch
        try:
            argv = self._argv(run, stem + ".json")
        except ea.ExecRefused as exc:
            raise Refused(str(exc))
        run.doc["launches"] = launch
        proc = self._spawn(run, argv, run.file(prompt_name), run.wc, stem)
        self.children[run.req] = proc
        run.exec.update({"pid": proc.pid, "promptPath": prompt_name,
                         "logPath": stem + ".json", "exitCode": None, "exitClass": None,
                         "sessionId": None, "stalledAt": None})
        run.status = "running"
        run.save()
        self.say("%s launched, pid %d, working copy %s" % (run.req, proc.pid, run.wc))

    def launch_batch(self, reqs, batch):
        """Prepare every REQ first, so a refusal starts no process."""
        prepared = []
        try:
            for req in reqs:
                prepared.append(self.prepare(req, batch))
        except Refused:
            for run in prepared:
                shutil.rmtree(run.path, ignore_errors=True)
                self.runs.pop(run.req, None)
            raise
        self.pending = prepared
        self.start_pending()

    def start_pending(self):
        while self.pending and len(self.children) < MAX_CONCURRENT:
            self.spawn(self.pending.pop(0))

    # ---- supervision -----------------------------------------------------------------
    def poll_once(self):
        """Reap what has exited, flag what has stalled. Never kills a live harness."""
        for req, proc in list(self.children.items()):
            rc = proc.poll()
            run = self.runs[req]
            if rc is None:
                self._stall_check(run)
                continue
            del self.children[req]
            if run.status in TERMINAL:
                continue
            self.on_exit(run, rc)
        for run in self.all_runs():
            if run.req not in self.children and run.status in ("running", "stalled") \
                    and run not in self.pending and not pid_alive(run.exec.get("pid")):
                # A harness that outlived its supervisor, or a run whose supervisor died
                # before its harness's pid was recorded: swept, and its trust revoked, by
                # `on_exit` (REQ-662 BR-5).
                self.on_exit(run, None)
        self.start_pending()

    def _stall_check(self, run):
        limit = float(run.doc["config"]["stall_minutes"]) * 60
        try:
            stamp = os.stat(run.wc_state_path()).st_mtime
        except OSError:
            stamp = calendar.timegm(time.strptime(run.exec["startedAt"], "%Y-%m-%dT%H:%M:%SZ"))
        idle = time.time() - stamp
        if idle > limit:
            if run.status != "stalled":
                run.status = "stalled"
                run.exec["stalledAt"] = el.now()
                run.save()
                self.say("%s stalled: no state write for %d minutes, pid %s alive"
                         % (run.req, idle // 60, run.exec["pid"]))
        elif run.status == "stalled":
            run.status = "running"
            run.save()

    def reap(self, run, pid):
        """After the leader exits: kill its group and sweep stragglers (ADR-2). With no pid
        recorded only the run's own stragglers are swept."""
        try:
            if pid:
                os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.time() + 2
        left = stragglers(run.req, run_tag(run.path))
        while left and time.time() < deadline:
            for other in left:
                try:
                    os.kill(other, signal.SIGTERM)
                except OSError:
                    pass
            time.sleep(0.1)
            left = stragglers(run.req, run_tag(run.path))
        for other in left:
            try:
                os.kill(other, signal.SIGKILL)
            except OSError:
                pass
        if left:
            time.sleep(0.2)
            left = stragglers(run.req, run_tag(run.path))
        try:
            if pid:
                os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
        if left:
            run.doc.setdefault("notes", []).append("stragglers survived the sweep: %s" % left)
        return left

    @staticmethod
    def _read_text(path):
        """A file the harness wrote, or None when there is none. Read only after the reap."""
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None

    def _read_result(self, run, name):
        """The launch's output, parsed by the adapter's declared format and source (REQ-662
        ADR-6): stdout from ``name``, and under ``source: file`` the ``{last_message}`` file
        that launch named. A missing file reads as nothing, which the parser reports."""
        adapter = self.adapter(run)
        last = None
        if adapter.output["source"] == "file":
            last = self._read_text(run.last_message(name))
        return adapter.parse_result(self._read_text(run.file(name)) or "", last)

    def _stderr_notice(self, run, stem):
        notice = self.adapter(run).block.get("trust_notice")
        if not notice:
            return None
        try:
            with open(run.file(stem), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if notice in line:
                        return line.strip()[:200]
        except OSError:
            pass
        return None

    def on_exit(self, run, rc):
        """The harness is gone. Nothing it wrote is read before the reap (BR-10)."""
        left = self.reap(run, run.exec["pid"])
        if run.doc.get("trustGrants"):
            # The harness is gone: its grant in the user config goes now, at every exit, the
            # halt's included, so no trust entry outlives the launch it was made for. A
            # mechanism that writes no file holds none (REQ-662 BR-5).
            self.revoke_trust(run)
        stem = run.exec["logPath"]
        adapter = self.adapter(run)
        result = self._read_result(run, stem)
        # The harness's own stderr, never the model's message, is where a refusal line is
        # looked for (REQ-662 ADR-6).
        stderr = self._read_text(run.file(stem.replace(".json", ".stderr.log"))) or ""
        claim = ea.terminal_claim(result["text"])
        klass = adapter.exit_class(rc, result, claim, stderr)
        run.exec.update({"exitCode": rc, "exitClass": klass,
                         "sessionId": result["session_id"], "stalledAt": None})
        run.doc["finalReport"] = result["text"]
        notice = self._stderr_notice(run, stem.replace(".json", ".stderr.log"))
        if notice:
            run.doc.setdefault("notes", []).append("harness said: %s" % notice)
        self.box(run).log("exec_exit", [str(rc), klass, str(claim)], run.wc, rc)
        self.verify_surfaces(run, self._working_copies(run), "exit")
        state = run.read_wc_state()
        self._model_values(run, state)
        if result["error"]:
            # A parse failure is exitClass error with the parser's message in notes, in the
            # run record and in pipeline-state.json; no `reason` key is added to exec (BR-6).
            parsed = "the harness output did not parse: %s" % result["error"]
            run.doc.setdefault("notes", []).append(parsed)
            notes = state.get("notes") if isinstance(state.get("notes"), list) else []
            state = dict(state, notes=notes + [parsed])
        hits = []
        try:
            for rid, spec in run.doc["repos"].items():
                hits += eg.exit_checks(self.box(run), spec["path"],
                                       run.doc["integrationBranches"][rid], run.doc["branch"],
                                       run.doc["launchTip"][rid], self.recorded_merges())
        except es.RuleBViolation as exc:
            hits.append(str(exc))
        except eg.GateError as exc:
            run.doc.setdefault("notes", []).append(str(exc))
            self._terminal(run, "failed", "setup-error", state)
            return
        for hit in hits:
            run.violation(hit)
        if claim in ("merged", "pr-ready"):
            run.violation("the harness claimed %s; an exec run stops at the merge gate" % claim)
        if left:
            self._block(run, state, "stragglers survived the sweep: %s" % left)
        elif hits:
            self._block(run, state, "%s: %s" % (PROTOCOL, "; ".join(hits)))
        elif adapter.exit_denied(rc):
            # Before the halt: the harness itself exited with a code its exit_codes map to
            # denied, so the run is blocked whatever the model wrote to state, never a completed
            # phase (REQ-662 BR-8).
            self._block(run, state, self._denied_reason(result, adapter.refusal_line(stderr)))
        elif state.get("status") == "awaiting_approval":
            # A denial the run recovered from, with no exit code saying denied, halts as
            # before REQ-662 (BR-1).
            self._halt(run, state, result)
        elif klass == "denied":
            self._block(run, state, self._denied_reason(result, adapter.refusal_line(stderr)))
        elif state.get("status") == "blocked" or (claim == "blocked" and state.get("blockers")):
            self._terminal(run, "blocked", self._halt_token(state), state)
        else:
            last = (result["text"] or "").strip()[:300]
            run.doc.setdefault("notes", []).append(
                "exit %s, class %s, is_error %s: %s" % (rc, klass, result["is_error"], last))
            self._terminal(run, "failed", "other", state, note=last)

    @staticmethod
    def _denied_reason(result, refusal):
        """Why a denied run is blocked: what the harness recorded, then its last message
        (REQ-662 BR-8). Every part is data for a person to read, never an instruction."""
        parts = []
        if result["denials"]:
            parts.append("denials %s" % json.dumps(result["denials"])[:300])
        if refusal:
            parts.append("stderr: %s" % refusal)
        parts.append("last message: %s" % ((result["text"] or "").strip()[:300] or "(none)"))
        return "the harness was denied: %s" % "; ".join(parts)

    def _model_values(self, run, state):
        """What state says that the orchestrator would act on is checked first (BR-17)."""
        approval = state.get("approval")
        if isinstance(approval, dict) and approval.get("decision"):
            run.violation("approval.decision in state with no ledger entry")
            approval.pop("decision", None)

    @staticmethod
    def _halt_token(state):
        for item in state.get("blockers") or []:
            if isinstance(item, dict) and item.get("reason") in ("validation-exhausted",
                                                                 "reflector-questions",
                                                                 "merge-conflict"):
                return item["reason"]
        return "other"

    def _carry(self, run, state=None):
        """Merge the working copy's state into the primary path's, then ours (BR-9)."""
        merged = run.read_primary_state()
        for key, value in (state if state is not None else run.read_wc_state()).items():
            if key in PRIMARY_OWNED and key in merged:
                continue
            merged[key] = value
        merged["status"] = run.status
        merged["exec"] = run.public_exec()
        doc = run.ledger().trusted()
        approval = dict(merged.get("approval") or {})
        decision = (doc or {}).get("decision")
        if decision:
            approval.update({k: decision[k] for k in ("decision", "decidedAt", "decidedBy",
                                                      "channel", "callerPid", "reason")})
        else:
            for key in ("decision", "decidedAt", "decidedBy", "channel", "callerPid", "reason"):
                approval.pop(key, None)
        if run.doc.get("holdBehind"):
            approval["holdBehind"] = run.doc["holdBehind"]
        if approval:
            merged["approval"] = approval
        run.write_primary_state(merged)
        run.save()

    def _write_status(self, run, **fields):
        merged = run.read_primary_state()
        merged["status"] = run.status
        merged["exec"] = run.public_exec()
        merged.update(fields)
        run.write_primary_state(merged)
        run.save()

    def _emit(self, run, terminal, reason=""):
        tool = os.path.join(self.toolkit, "tools", "delegate", "emit-run-outcome.sh")
        if not os.path.exists(tool):
            return
        argv = [self.box(run).tools["sh"], tool, "--state", run.primary_state_path(),
                "--terminal", terminal, "--engine", "exec", "--reason", reason]
        try:
            res = self.box(run).tool(argv, run.path)
            if res.stdout.strip():
                self.say(res.stdout.strip().splitlines()[-1])
        except es.RuleBViolation:
            pass

    def _terminal(self, run, status, reason, state, note=None):
        run.status = status
        self.revoke_trust(run)
        self._carry(run, state)
        if status == "failed":
            # The working copy is left to a person (REQ-662 BR-17).
            self.restore_surfaces(run)
        if note and status == "failed":
            merged = run.read_primary_state()
            notes = merged.get("notes") if isinstance(merged.get("notes"), list) else []
            merged["notes"] = notes + [note]
            run.write_primary_state(merged)
        self._emit(run, status if status in ("blocked", "failed") else "failed", reason)
        self.say("%s %s" % (run.req, status))

    def _block(self, run, state, why):
        merged = state.get("blockers") if isinstance(state.get("blockers"), list) else []
        state = dict(state, blockers=merged + [{"reason": why, "at": el.now()}])
        self._terminal(run, "blocked", "other", state)

    def _touched(self, run, state):
        """The touched repos in merge order. State is data: each id is checked."""
        repos = state.get("repos") if isinstance(state.get("repos"), dict) else {}
        order = state.get("mergeOrder") if isinstance(state.get("mergeOrder"), list) else []
        known = run.doc["repos"]
        out = []
        for rid in [r for r in order if isinstance(r, str)] + run.doc["order"]:
            if rid in known and rid not in out:
                entry = repos.get(rid)
                if isinstance(entry, dict) and entry.get("touched") is False:
                    continue
                out.append(rid)
        return out or [run.primary_repo]

    def compute_plan(self, run, state):
        """What approval will perform, from the run record and the forge (BR-16)."""
        box = self.box(run)
        ib = run.doc["integrationBranch"]
        block = self.adapter(run).block
        manifests = run.doc.get("surfaces") or {}
        prs = []
        changed = []
        touched = []
        for rid in self._touched(run, state):
            repo = run.doc["repos"][rid]["path"]
            rib = run.doc["integrationBranches"][rid]
            pr = eg.lookup_pr(box, repo, run.doc["branch"], rib, self.host_of(run))
            oid = eg.fetch_branch(box, repo, run.doc["branch"])
            if oid != pr["headRefOid"]:
                raise eg.GateError("the forge says %s is at %s and origin says %s"
                                   % (run.doc["branch"], pr["headRefOid"], oid))
            eg.fetch_integration(box, repo, rib)
            paths = eg.changed_paths(box, repo, rib, oid)
            # REQ-662 BR-17: the exec-path gate over this PR's head and the diff just read. Its
            # targets come from the adapter and the run record, never the working copy.
            rendered = esf.rendered_paths(manifests.get(run.doc["repos"][rid]["workingCopy"])
                                          or {})[0]
            touched += eg.exec_path_touched(box, repo, rib, pr["headRefOid"],
                                            eg.exec_path_targets(block, rendered), changed=paths)
            pr["repo"] = rid
            pr["changedPaths"] = paths
            prs.append(pr)
            changed += [p[1] for p in paths]
        primary = next((p for p in prs if p["repo"] == run.primary_repo), prs[0])
        spec = run.doc["specDir"] + "/requirement.md"
        deploy, skipped = eg.deploy_plan(box, run.primary_path, ib, primary["headRefOid"], spec,
                                         changed)
        section = eg.exec_config(eg.show_blob(box, run.primary_path, "origin/%s" % ib,
                                              ".adlc/config.yml") or "").get("deploy") or {}
        hits = eg.deploy_surface_hits(changed, section.get("command") or "")
        lines = eg.gate_lines(changed, hits, block.get("config_surfaces") or [])
        protection = box.forge("adlc_forge_branch_protection", [ib],
                               run.primary_path).stdout.strip() or "unknown"
        return {"prs": prs, "deployPlan": deploy, "deploySkipped": skipped, "changesGate": lines,
                "ackGateChange": False, "changedPaths": sorted(set(changed)),
                eg.EXEC_PATH_KEY: sorted({path for _status, path in touched}),
                "allowUnprotected": run.doc["allowUnprotected"],
                "sharedCredentials": run.doc["sharedCredentials"], "protection": protection,
                "allowUnverified": list(run.doc.get("allowUnverified") or [])}

    def _halt(self, run, state, result):
        self.verify_surfaces(run, self._working_copies(run), "halt")
        try:
            plan = self.compute_plan(run, state)
        except eg.Mismatch as exc:
            run.violation("a PR is %s before approval" % exc)
            self._block(run, state, "%s: %s" % (PROTOCOL, exc))
            return
        except (eg.GateError, es.SafetyError) as exc:
            run.doc.setdefault("notes", []).append(str(exc))
            self._terminal(run, "failed", "no-pr", state, note=str(exc))
            return
        except es.RuleBViolation as exc:
            self._block(run, state, "%s: %s" % (PROTOCOL, exc))
            return
        self._crosscheck(run, state, plan)
        try:
            run.ledger().halt_write(plan)
        except el.LedgerError as exc:
            run.violation(str(exc))
            self._block(run, state, "%s: %s" % (PROTOCOL, exc))
            return
        self._exec_path_events(run, plan)
        run.status = "awaiting_approval"
        # Said at the halt, before approval is asked for: a run with no session id, or on a
        # harness with no resume template, cannot go on past the merge (REQ-662 BR-7).
        resumable = run.exec["sessionId"] and self.adapter(run).can_resume
        run.doc["resume"] = "ok" if resumable else "impossible"
        self._carry(run, state)
        self.announce(run, self.mint(run))

    def _exec_path_events(self, run, plan):
        """One ``exec_path_touched`` event per hit of the plan's exec-path gate (REQ-662 BR-17):
        the harness, the repo, the path as the diff spells it and its ``--no-renames`` status.
        The dashboard row says that approve will refuse (:func:`render_row`)."""
        touched = set(plan.get(eg.EXEC_PATH_KEY) or [])
        name = self.adapter(run).name
        for pr in plan["prs"]:
            for status, path in pr.get("changedPaths") or []:
                if path in touched:
                    self.box(run).log("exec_path_touched", [name, status, path],
                                      run.doc["repos"][pr["repo"]]["path"], None,
                                      detail={"harness": name, "repo": pr["repo"], "path": path,
                                              "status": status})

    def _crosscheck(self, run, state, plan):
        approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
        claimed = approval.get("prs")
        if isinstance(claimed, list):
            actual = {p["url"] for p in plan["prs"]}
            extra = [str(c) for c in claimed if c not in actual]
            if extra:
                run.doc.setdefault("notes", []).append(
                    "the model's approval named %s; the orchestrator's plan wins" % extra)
        if approval.get("action") not in (None, "merge"):
            run.doc.setdefault("notes", []).append("approval.action is not the closed value")

    def mint(self, run):
        """Fresh tokens. Their digests stay in memory; the tokens go to `announce` only."""
        plan = run.ledger().read()["plan"]
        token = el.mint_token()
        entry = {"approve": el.token_digest(token), "gate": None}
        gate_token = None
        lines = plan.get("changesGate") or []
        if lines:
            gate_token = el.mint_token()
            entry["gate"] = el.token_digest(gate_token, "\n".join(lines))
        self.tokens[run.req] = entry
        return token, gate_token

    def announce(self, run, tokens):
        token, gate_token = tokens
        for line in render_row(run, violations_of(run)):
            self.say(line)
        self.say("  approve: /sprint approve %s --token %s%s"
                 % (run.req, token,
                    " --ack-gate-change --gate-token %s" % gate_token if gate_token else ""))
        self.say("  reject:  /sprint reject %s [reason]" % run.req)

    # ---- the operator's decisions ----------------------------------------------------
    def caller_guard(self, run, caller_env, caller_pid):
        """Refuse anything from inside a run. A refusal is recorded (BR-10)."""
        marker = (caller_env or {}).get("ADLC_EXEC_RUN")
        pids = {run.exec.get("pid"), run.exec.get("closeOutPid")} - {None}
        live = {p for p in pids if pid_alive(p)}
        inside = marker or (live & set(ancestry(caller_pid)) if caller_pid else None)
        if inside:
            message = "a decision attempted from inside a run (%s)" % (inside,)
            run.violation(message)
            raise Refused("%s: %s" % (PROTOCOL, message))

    def live_exec_pids(self):
        """Each live harness pid (``exec.pid``, ``exec.closeOutPid``) that a run record in this
        machine's engine state directory holds, or this supervisor's own runs, mapped to its
        run. Read from the state directory, never from a working copy (REQ-662 BR-18)."""
        runs = []
        for path in el.run_dirs(self.environ):
            try:
                runs.append(Run.load(path))
            except Refused:
                continue
        live = {}
        for run in runs + self.all_runs():
            record = run.doc.get("exec") if isinstance(run.doc.get("exec"), dict) else {}
            for pid in (record.get("pid"), record.get("closeOutPid")):
                if pid_alive(pid):
                    live[int(pid)] = run
        return live

    def nested_guard(self, what, caller_env, caller_pid):
        """Refuse a launch, a dispatched launch or a resume from inside a run (REQ-662 BR-18):
        with ``ADLC_EXEC_RUN`` set, or from a descendant of a live exec pid of any run
        (``live_exec_pids``), whatever the caller's environment says, so a process the model
        started cannot start a nested run after scrubbing its environment. It runs before
        anything is bound, prepared or launched: a refusal creates no run directory and writes
        no ledger entry. The refusal names ``nested_launch_refused``, and the run it came from
        (the exec pid's, else the one ``ADLC_EXEC_RUN`` names) logs that event and records the
        attempt as a Rule B violation."""
        marker = (caller_env or {}).get("ADLC_EXEC_RUN") or None
        chain = ancestry(caller_pid) if caller_pid else []
        live = self.live_exec_pids()
        hit = next((p for p in chain if p in live), None)
        if marker is None and hit is None:
            return
        run = live.get(hit)
        if run is None:
            path = el.find_run(self.primary, marker, self.environ)
            run = self.runs.get(marker) or (Run.load(path) if path else None)
        if hit is not None:
            where = "pid %s descends from the live exec pid %s of %s" % (caller_pid, hit, run.req)
        else:
            where = "ADLC_EXEC_RUN=%s is set" % marker
        message = "nested_launch_refused: %s attempted from inside a run: %s" % (what, where)
        if run is not None:
            es.Toolbox(run.path, self.toolkit, self.environ).log(
                "nested_launch_refused", [what], None, None,
                detail={"pid": caller_pid, "ancestry": chain, "execPid": hit, "execRun": marker})
            run.violation(message)
        raise Refused("%s: %s" % (PROTOCOL, message))

    def _validate_state(self, run):
        state = run.read_primary_state()
        approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
        if "action" in approval and approval["action"] != "merge":
            raise Refused("approval.action failed validation: %r" % (approval["action"],))
        repos = state.get("repos") if isinstance(state.get("repos"), dict) else {}
        try:
            for rid, entry in repos.items():
                es.require(es.VALID_REPO_ID, rid, "repos key")
                if isinstance(entry, dict) and entry.get("prUrl"):
                    es.parse_pr_url(entry["prUrl"], self.host_of(run),
                                    "repos[%s].prUrl" % rid)
        except es.SafetyError as exc:
            raise Refused(str(exc))
        doc = run.ledger().read() or {}
        if approval.get("decision") and not doc.get("decision"):
            message = "approval.decision in state with no ledger entry"
            run.violation(message)
            raise Refused("%s: %s" % (PROTOCOL, message))

    def approve(self, req, token, gate_token=None, ack=False, decided_by="", channel="shell",
                caller_pid=None, caller_env=None):
        """Leave `awaiting_approval`. The decision reaches the ledger before anything else."""
        with self.lock:
            run = self._run(req)
            self.caller_guard(run, caller_env, caller_pid)
            if run.status != "awaiting_approval":
                raise Refused("%s is %s, not awaiting_approval" % (req, run.status))
            live = [p for p in (run.exec.get("pid"), run.exec.get("closeOutPid")) if pid_alive(p)]
            if live or req in self.children:
                run.violation("approval attempted while the process is alive")
                raise Refused("%s: the harness process is still alive, %s" % (PROTOCOL, live))
            if not run.ledger().exists():
                raise Refused("%s has no plan yet" % req)
            if not run.ledger().accounted():
                run.violation("a ledger the run record does not account for is present")
                raise Refused("%s: the ledger does not match the run record" % PROTOCOL)
            self._validate_state(run)
            held = self.tokens.get(req)
            if not held or not token or el.token_digest(token) != held["approve"]:
                raise Refused("%s: the approve token is wrong or already spent; "
                              "the dashboard prints the current one" % req)
            plan = run.ledger().read()["plan"]
            # REQ-662 BR-17, before any acknowledgement is read: --ack-gate-change does not
            # reach this, and the token stays unspent. A plan with no gate result was halted by
            # an engine without the gate: the run re-halts, so the operator approves a gated plan.
            try:
                eg.check_exec_path(plan)
            except eg.ExecPathTouched as exc:
                if exc.paths:
                    raise Refused("%s: %s (REQ-662 BR-17)" % (req, exc))
                self.rehalt(run, eg.EXEC_PATH_KEY)
                raise Refused("%s: %s; it is re-halted with a fresh plan, so approve with the "
                              "token the dashboard now prints (REQ-662 BR-17)" % (req, exc))
            lines = plan.get("changesGate") or []
            if lines:
                if not ack:
                    raise Refused("%s changes the gate, so approve needs --ack-gate-change: %s"
                                  % (req, "; ".join(lines)))
                bound = el.token_digest(gate_token or "", "\n".join(lines))
                if bound != held["gate"]:
                    raise Refused("%s: --ack-gate-change needs the token bound to that line" % req)
            # Re-checked before anything merges; an unverified adapter refuses here whatever the
            # launching invocation was given (REQ-662 BR-18). The token stays unspent.
            self._gate(self.adapter(run), run.doc["binary"], "approve")
            self.tokens.pop(req)
            plan["ackGateChange"] = bool(lines)
            run.ledger().update_plan(plan)
            run.ledger().decide("approved", decided_by, channel, caller_pid, "", bool(lines))
            run.status = "approved"
            run.doc["holdBehind"] = self.ahead_of(run)
            self._carry(run, {})
            self.queue.append(req)
            shown = "approved (queued behind %s)" % run.doc["holdBehind"] \
                if run.doc["holdBehind"] else "approved"
            self.say("%s %s" % (req, shown))
            return shown

    def reject(self, req, reason="", decided_by="", channel="shell", caller_pid=None,
               caller_env=None):
        with self.lock:
            run = self._run(req)
            self.caller_guard(run, caller_env, caller_pid)
            if run.status != "awaiting_approval":
                raise Refused("%s is %s, not awaiting_approval" % (req, run.status))
            if not run.ledger().accounted():
                run.violation("a ledger the run record does not account for is present")
                raise Refused("%s: the ledger does not match the run record" % PROTOCOL)
            run.ledger().decide("rejected", decided_by, channel, caller_pid, reason)
            run.status = "rejected"
            self.tokens.pop(req, None)
            self.revoke_trust(run)
            self._carry(run, {})
            self.restore_surfaces(run)          # the working copy is left (REQ-662 BR-17)
            self._emit(run, "failed", "other")
            self.say("%s rejected: %s" % (req, reason))
            self._release_holds()

    def answer(self, req, text, caller_pid=None, caller_env=None, allow_unverified=False,
               invocation=None):
        """A fresh process in the same working copy, carrying the reply (BR-14).
        ``allow_unverified`` and ``invocation`` are the answering invocation's own flag and
        identity, for this one relaunch (REQ-662 BR-18)."""
        with self.lock:
            run = self._run(req)
            self.caller_guard(run, caller_env, caller_pid)
            if run.status != "blocked":
                raise Refused("%s is %s, not blocked" % (req, run.status))
            self._relaunch(run, text, allow_unverified, invocation)

    def _relaunch(self, run, text, allow_unverified=False, invocation=None):
        """A fresh launch in the run's working copy. ``allow_unverified`` is the flag of the
        invocation that asked for it, an `answer`'s; a relaunch an `approve` drains passes
        none (REQ-662 BR-18)."""
        self._gate(self.adapter(run), run.doc["binary"], "relaunch", run, allow_unverified,
                   invocation)
        branch = run.doc["branch"]
        try:
            data = ep.pipeline_prompt(self.toolkit, self.primary, run.req, branch, self.primary,
                                      run.wc, answer=text if text is not None else
                                      "The REQ this run was held behind has merged, and this "
                                      "branch has been rebased. Continue.",
                                      adapter=self.adapter(run))
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            self._prompt_refused(run.req, exc)
            raise Refused(str(exc))
        name = "prompt.%d.txt" % (run.doc["launches"] + 1)
        el.atomic_write(run.file(name), data)
        self.prepare_surfaces(run, self._working_copies(run), branch, "launch")
        self.grant_trust(run)
        try:
            self._launch_first(run, name)
        except (Refused, ea.ExecRefused) as exc:
            # Trust is granted: an argv the closed-world check refuses ends the run, its trust
            # revoked (`_terminal`), and the caller is told (REQ-662 BR-5, BR-16).
            self.say("%s refused at relaunch: %s" % (run.req, exc))
            self._terminal(run, "failed", "setup-error", {}, note=str(exc))
            raise Refused(str(exc))

    def abort(self, req, by="", caller_pid=None, caller_env=None):
        """The only way a running or stalled harness is killed (BR-20)."""
        with self.lock:
            run = self._run(req)
            self.caller_guard(run, caller_env, caller_pid)
            pid = run.exec.get("pid")
            close = run.exec.get("closeOutPid")
            if not pid_alive(pid) and pid_alive(close):
                # The merge stands: the worker records closeOut failed and cleans up.
                try:
                    os.killpg(int(close), signal.SIGTERM)
                except OSError:
                    pass
                self.say("%s close-out aborted by %s" % (req, by))
                return
            if not pid_alive(pid):
                raise Refused("%s has no live process; its last status is %s"
                              % (req, run.status))
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except OSError:
                pass
            proc = self.children.pop(req, None)
            if proc is not None:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            self.reap(run, int(pid))
            if proc is not None:
                proc.poll()
            self.restore_surfaces(run)          # the working copy is left (REQ-662 BR-17)
            run.exec.update({"abortedBy": by, "abortedAt": el.now()})
            run.status = "failed"
            self.revoke_trust(run)
            self._carry(run)
            self._emit(run, "failed", "other")
            self.say("%s aborted by %s; working copy left at %s" % (req, by, run.wc))

    def _run(self, req):
        es.valid_req(req)
        run = self.runs.get(req)
        if run is None:
            path = el.find_run(self.primary, req, self.environ)
            if path is None:
                raise Refused("%s has no exec run in this repo" % req)
            run = Run.load(path)
            self.runs[req] = run
        return run

    # ---- ordering (REQ-483) ----------------------------------------------------------
    def footprint(self, run):
        doc = run.ledger().trusted()
        if doc:
            return set(doc["plan"]["changedPaths"])
        box = self.box(run)
        ib = run.doc["integrationBranch"]
        ref = "refs/remotes/origin/%s" % run.doc["branch"]
        if eg.fetch_branch(box, run.primary_path, run.doc["branch"]) is None:
            return set()
        out = box.git(run.primary_path, ["diff", "--name-only", "origin/%s...%s" % (ib, ref)])
        return {ln for ln in out.stdout.splitlines() if ln}

    def component(self, run):
        text = eg.show_blob(self.box(run), run.primary_path,
                            "origin/%s" % run.doc["integrationBranch"],
                            run.doc["specDir"] + "/requirement.md")
        return eg.frontmatter_flag(text or "", "component")

    @staticmethod
    def rank(run):
        doc = run.ledger().trusted()
        stamps = [p.get("createdAt", "") for p in (doc or {}).get("plan", {}).get("prs", [])]
        return (min(stamps) if stamps else "~", int(run.req.split("-")[1]))

    def ahead_of(self, run):
        """The earliest not-yet-merged overlapping REQ ranked ahead, or None (BR-10)."""
        mine = self.footprint(run)
        for other in sorted(self.all_runs(), key=self.rank):
            if other.req == run.req:
                break
            if other.status in TERMINAL:
                continue
            theirs = self.footprint(other)
            overlap = (mine & theirs) if mine and theirs else (
                self.component(run) == self.component(other))
            if overlap:
                return other.req
        return None

    def _release_holds(self):
        for run in self.all_runs():
            hold = run.doc.get("holdBehind")
            if hold and self.runs.get(hold) is not None \
                    and self.runs[hold].status in TERMINAL:
                run.doc["holdBehind"] = None
                run.save()

    def next_ready(self):
        self._release_holds()
        for req in list(self.queue):
            if not self.runs[req].doc.get("holdBehind"):
                self.queue.remove(req)
                return self.runs[req]
        return None

    def drain(self):
        """Every approved REQ whose hold has cleared, one at a time."""
        while True:
            with self.lock:
                run = self.next_ready()
            if run is None:
                return
            self.execute(run)

    # ---- the one-way moves -----------------------------------------------------------
    def rehalt(self, run, field):
        """BR-11: the approval was for something else. A fresh plan, a fresh approve."""
        state = run.read_primary_state()
        try:
            plan = self.compute_plan(run, state)
        except (eg.GateError, eg.Mismatch, es.SafetyError) as exc:
            # Two open PRs for the head ref have no one plan. The old plan stands, so the
            # operator sees what is wrong and the next approve is refused the same way.
            plan = run.ledger().read()["plan"]
            run.doc.setdefault("notes", []).append("the plan could not be recomputed: %s" % exc)
        run.ledger().supersede(plan, field)
        # A fresh plan carries a fresh exec-path gate result (REQ-662 BR-17).
        self._exec_path_events(run, plan)
        run.status = "awaiting_approval"
        run.doc["holdBehind"] = None
        self._carry(run, {})
        self.say("%s re-halted: %s no longer matches what was approved" % (run.req, field))
        self.announce(run, self.mint(run))

    def _recheck(self, run):
        hits = []
        for rid, spec in run.doc["repos"].items():
            hits += eg.exit_checks(self.box(run), spec["path"],
                                   run.doc["integrationBranches"][rid], run.doc["branch"],
                                   run.doc["launchTip"][rid], self.recorded_merges())
        return hits

    def execute(self, run):
        """Everything one approval covers, in order (BR-11, BR-13, BR-14)."""
        box = self.box(run)
        try:
            doc = run.ledger().trusted()
            if not doc or not (doc.get("decision") or {}).get("decision") == "approved":
                run.violation("the ledger changed between the approval and the merge")
                self._block(run, run.read_primary_state(), "%s: the ledger does not match the "
                            "run record" % PROTOCOL)
                return
            run.status = "merging"
            self._write_status(run)
            plan = doc["plan"]
            hits = self._recheck(run)
            if hits:
                for hit in hits:
                    run.violation(hit)
                if not self._all_merged(run, plan):
                    self._block(run, run.read_primary_state(),
                                "%s: %s" % (PROTOCOL, "; ".join(hits)))
                    return
            # Before the final push (a rebase's) and the merge, what the engine rendered and hid
            # goes back to what it was at launch (REQ-662 BR-17).
            self.restore_surfaces(run)
            for pr in plan["prs"]:
                outcome = self._merge_one(run, pr, plan)
                if outcome != "merged":
                    return
            self._after_merge(run, plan)
        except es.RuleBViolation as exc:
            run.violation(str(exc))
            self._block(run, run.read_primary_state(), "%s: %s" % (PROTOCOL, exc))
        except (eg.GateError, es.SafetyError) as exc:
            self._terminal(run, "failed", "setup-error", {}, note=str(exc))
        finally:
            box.save()

    def _all_merged(self, run, plan):
        """A PR merged behind the orchestrator's back still gets its record (BR-11)."""
        for pr in plan["prs"]:
            repo = run.doc["repos"][pr["repo"]]["path"]
            view = es.kv(self.box(run).forge("adlc_forge_pr_view", [pr["url"], "--fields", "state"],
                                             repo).stdout)
            if view.get("state") != "MERGED":
                return False
        return True

    def _merge_one(self, run, pr, plan):
        box = self.box(run)
        rid = pr["repo"]
        repo = run.doc["repos"][rid]["path"]
        ib = run.doc["integrationBranches"][rid]
        branch = run.doc["branch"]
        host = self.host_of(run)
        eg.fetch_branch(box, repo, branch)
        try:
            eg.verify_pr(box, repo, pr, branch, ib, host)
        except eg.Mismatch as exc:
            if exc.field == "state" and "MERGED" in str(exc):
                run.violation("PR %s is already MERGED before the orchestrator merged it"
                              % pr["url"])
                self._note_merged(run, rid)
                return "merged"
            self.rehalt(run, exc.field)
            return "rehalt"
        attempts = 0
        while True:
            oid = pr["headRefOid"]
            rc, files = self._trial(run, repo, oid, ib)
            if rc == 0:
                break
            if rc != 1:
                self._terminal(run, "failed", "setup-error", {},
                               note="trial merge rc=%d on %s" % (rc, pr["url"]))
                return "failed"
            if attempts >= int(run.doc["config"]["auto_rebase_max_attempts"]):
                self._hold(run, files, attempts)
                return "blocked"
            attempts += 1
            verdict = self._rebase(run, rid, pr, plan)
            if verdict != "clean":
                return verdict
        return self._merge_pinned(run, rid, pr)

    def _trial(self, run, repo, oid, ib):
        box = self.box(run)
        path = run.file("trial-%s" % oid[:12])
        if os.path.exists(path):
            eg.remove_worktree(box, repo, path)
        eg.add_detached(box, repo, path, oid)
        try:
            return eg.trial_merge(box, repo, path, ib)
        finally:
            eg.remove_worktree(box, repo, path)

    def _hold(self, run, files, attempts):
        state = run.read_primary_state()
        entry = {"blockedBy": "manual", "conflictFiles": files, "holdState": "needs-manual-rebase",
                 "rebaseAttempts": attempts,
                 "unblockCondition": "resolve the conflict on the branch by hand, then push"}
        state["blockers"] = [entry]
        run.status = "blocked"
        self.revoke_trust(run)
        self._carry(run, state)
        self._emit(run, "blocked", "merge-conflict")
        self.say("%s blocked: a person must resolve %s" % (run.req, ", ".join(files)))

    def _rebase(self, run, rid, pr, plan):
        """BR-12, in a detached worktree of the orchestrator's own."""
        box = self.box(run)
        repo = run.doc["repos"][rid]["path"]
        ib = run.doc["integrationBranches"][rid]
        branch = run.doc["branch"]
        recorded = pr["headRefOid"]
        if eg.fetch_branch(box, repo, branch) != recorded:
            self.rehalt(run, "headRefOid")
            return "rehalt"
        path = run.file("rebase-%s" % recorded[:12])
        if os.path.exists(path):
            eg.remove_worktree(box, repo, path)
        eg.add_detached(box, repo, path, recorded)
        try:
            result = eg.rebase_detached(box, repo, path, ib, recorded, pr["changedPaths"])
            if result["outcome"] == "conflict":
                self._hold(run, result["files"], 1)
                return "blocked"
            if result["outcome"] == "mismatch":
                self._block(run, run.read_primary_state(), result["detail"])
                return "blocked"
            push = box.git(repo, ["push", "--force-with-lease=%s:%s" % (branch, recorded), "origin",
                                  "HEAD:refs/heads/%s" % branch], cwd=path)
            if push.returncode != 0:
                self.rehalt(run, "headRefOid")
                return "rehalt"
            pr["headRefOid"] = result["oid"]
            run.ledger().update_plan(plan)
            if run.doc.get("lane") == "lite":
                rc, out = eg.lane_check_rerun(box, repo, path, ib)
                if rc != 0:
                    self._block(run, run.read_primary_state(),
                                "the lane check failed on the rebased diff: %s" % out.strip())
                    return "blocked"
        finally:
            eg.remove_worktree(box, repo, path)
        return "clean"

    def _merge_pinned(self, run, rid, pr):
        box = self.box(run)
        repo = run.doc["repos"][rid]["path"]
        res = box.forge("adlc_forge_pr_merge", [pr["url"], "--squash", "--delete-branch",
                                                "--match-head-commit", pr["headRefOid"]], repo)
        out = es.kv(res.stdout)
        if res.returncode != 0 or out.get("state") != "MERGED":
            try:
                eg.verify_pr(box, repo, pr, run.doc["branch"], run.doc["integrationBranches"][rid],
                             self.host_of(run))
            except eg.Mismatch as exc:
                self.rehalt(run, exc.field)
                return "rehalt"
            if out.get("error_class") == "merge-blocked-by-policy":
                # Checks re-running after a rebase, a review, a moved base: the PR is still
                # the one approved, so it waits for a fresh approve rather than failing.
                run.doc.setdefault("notes", []).append(
                    "merge of %s refused: %s" % (pr["url"], out.get("raw", "")))
                self.rehalt(run, "merge refused by policy")
                return "rehalt"
            self._terminal(run, "failed", "merge-unverified", {},
                           note="merge of %s failed: %s" % (pr["url"], res.stdout.strip()))
            return "failed"
        view = es.kv(box.forge("adlc_forge_pr_view", [pr["url"], "--fields", "state,mergeCommit"],
                               repo).stdout)
        if view.get("mergeCommit"):
            run.doc["recordedMerges"].append(view["mergeCommit"])
        pr["mergeCommit"] = view.get("mergeCommit", "")
        box.log("one_way_move", ["merge", pr["url"], str(res.returncode), view.get("state", "")],
                repo, res.returncode)
        self._note_merged(run, rid)
        return "merged"

    def _note_merged(self, run, rid):
        state = run.read_primary_state()
        repos = state.get("repos") if isinstance(state.get("repos"), dict) else {}
        entry = repos.get(rid) if isinstance(repos.get(rid), dict) else {}
        entry["merged"] = True
        repos[rid] = entry
        state["repos"] = repos
        state.pop("blockers", None)
        run.write_primary_state(state)
        run.save()

    def _after_merge(self, run, plan):
        """The merge stands from here: a failure is a dashboard line, never a rollback."""
        try:
            self._deploy(run, plan)
            self.close_out(run, plan)
        except (Refused, eg.GateError, es.SafetyError, OSError, ValueError) as exc:
            self._close_out_failed(run, "failed", str(exc))
        if run.doc.get("deployFailed"):
            self._close_out_failed(run, "failed", run.doc["deployFailed"])
        self.cleanup(run)
        run.status = "merged"
        self.revoke_trust(run)
        self._write_status(run)
        self._emit(run, "merged")
        self.say("%s merged" % run.req)
        self.unblock_after(run)

    def _deploy(self, run, plan):
        box = self.box(run)
        deploy = plan.get("deployPlan")
        if not deploy:
            return
        res = box.tool([box.tools["sh"], "-c", deploy["command"]], run.primary_path)
        box.log("one_way_move", ["deploy", deploy["target"], str(res.returncode)],
                run.primary_path, res.returncode)
        if res.returncode != 0:
            run.doc["deployFailed"] = "deploy %s failed: %s" % (deploy["target"],
                                                                res.stderr.strip()[:200])
            self.say("%s deploy failed; the merge stands" % run.req)

    def _close_out_failed(self, run, status, reason):
        state = run.read_primary_state()
        state["closeOut"] = {"status": status, "reason": reason, "at": el.now()}
        run.write_primary_state(state)
        self.say("%s close-out: %s — %s" % (run.req, status, reason))

    def _evidence(self, run, plan):
        lines = ["Merged PRs:"]
        for pr in plan["prs"]:
            lines.append("- %s, merge commit %s" % (pr["url"], pr.get("mergeCommit", "")))
        lane = run.read_primary_state().get("lane")
        lines.append("Lane: %s" % json.dumps(lane) if lane else "Lane: full")
        lines.append("The run's final report:")
        lines.append(run.doc.get("finalReport") or "(none)")
        return "\n".join(lines)

    def close_out(self, run, plan):
        """The one place a session resumes: lesson drafting is model work (BR-14, BR-25)."""
        box = self.box(run)
        adapter = self.adapter(run)
        sid = run.exec.get("sessionId")
        if not sid:
            self._close_out_failed(run, "failed", "no session id")
            return
        if not adapter.can_resume:
            self._close_out_failed(run, "failed", "resume is impossible: harness %s declares "
                                   "no resume" % adapter.name)
            return
        try:
            self._gate(adapter, run.doc["binary"], "close-out", run)
        except Refused as exc:
            self._close_out_failed(run, "failed", str(exc))
            return
        help_out = subprocess.run([run.doc["binary"], "--help"], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, universal_newlines=True,
                                  env=self._child_env(run)).stdout
        if adapter.block.get("config_isolation") and not adapter.isolation_available(help_out):
            self._close_out_failed(run, "failed", "harness config isolation unavailable")
            return
        ib = run.doc["integrationBranch"]
        repo = run.primary_path
        branch = "chore/%s-close-out" % run.req
        path = os.path.join(repo, ".worktrees", "%s-close-out" % run.req)
        eg.fetch_integration(box, repo, ib)
        res = box.git(repo, ["worktree", "add", "--no-track", "-b", branch, path,
                             "refs/remotes/origin/%s" % ib])
        if res.returncode != 0:
            self._close_out_failed(run, "failed", "close-out worktree: %s" % res.stderr.strip())
            return
        run.doc["closeOutWorkingCopy"] = path
        # The close-out working copy gets its own render and checks, for the resume's branch
        # (REQ-662 BR-4, BR-7, BR-15, BR-16).
        try:
            self.prepare_surfaces(run, [path], branch, "resume")
        except Refused as exc:
            self._close_out_failed(run, "failed", str(exc))
            return
        try:
            self.grant_trust(run, path)
        except Refused as exc:
            self._close_out_failed(run, "failed", str(exc))
            return
        try:
            deploy = (plan.get("deployPlan") or {}).get("command", "")
            data = ep.closeout_prompt(self.toolkit, run.req, branch, path,
                                      self._evidence(run, plan), deploy,
                                      adapter=self.adapter(run))
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            self._prompt_refused(run.req, exc)
            self._close_out_failed(run, "failed", str(exc))
            return
        el.atomic_write(run.file("close-out-prompt.txt"), data)
        added = os.path.join(repo, run.doc["specDir"])
        # The close-out writes its own working copy and, through --add-dir, the primary
        # repo's pipeline-state.json (close-out rule 3); nothing else (BUG-265).
        # No --harness-flag reaches the close-out, as before REQ-662.
        argv = self._argv(run, "close-out.json", resume=sid, wc=path, branch=branch,
                          write_roots=[path, added], add_dir=added, operator=[])
        proc = self._spawn(run, argv, run.file("close-out-prompt.txt"), path, "close-out")
        run.exec["closeOutPid"] = proc.pid
        self._write_status(run)
        rc = proc.wait()
        self.reap(run, proc.pid)
        self.verify_surfaces(run, [path], "exit")
        self.revoke_trust(run, path)
        result = self._read_result(run, "close-out.json")
        lines = (result["text"] or "").strip().split("\n")
        claim = ea.terminal_claim(result["text"])
        match = re.match(r"^Chore PR: (\S+)\s*$", lines[1]) if len(lines) > 1 else None
        if rc != 0 or claim != "closed-out" or match is None:
            self._close_out_failed(run, "failed", "the resumed session ended %s, rc %s"
                                   % (claim, rc))
            return
        self._chore_gate(run, match.group(1), branch)

    def _chore_gate(self, run, url, branch):
        box = self.box(run)
        repo = run.primary_path
        ib = run.doc["integrationBranch"]
        host = self.host_of(run)
        try:
            es.parse_pr_url(url, host, "chore PR url")
        except es.SafetyError as exc:
            self._close_out_failed(run, "failed", "chore PR out of bounds: %s" % exc)
            return
        view, bad = eg.chore_pr_fields(box, repo, url, branch, ib, host, run.doc["origin"]["owner"],
                                       run.doc["origin"]["name"])
        if bad:
            self._close_out_failed(run, "failed", "chore PR out of bounds: %s" % bad)
            return
        oid = eg.fetch_branch(box, repo, branch)
        if oid != view.get("headRefOid"):
            self._close_out_failed(run, "failed", "chore PR out of bounds: headRefOid")
            return
        wrong = eg.chore_paths_verdict(box, repo, ib, oid, run.req)
        if wrong:
            self._close_out_failed(run, "needs-review", "; ".join(wrong)[:300])
            return
        res = box.forge("adlc_forge_pr_merge", [url, "--squash", "--delete-branch",
                                                "--match-head-commit", oid], repo)
        box.log("one_way_move", ["close-out merge", url, str(res.returncode)], repo, res.returncode)
        if res.returncode != 0:
            self._close_out_failed(run, "failed", "chore PR merge: %s" % res.stdout.strip()[:200])
            return
        view = es.kv(box.forge("adlc_forge_pr_view", [url, "--fields", "mergeCommit"],
                               repo).stdout)
        if view.get("mergeCommit"):
            run.doc["recordedMerges"].append(view["mergeCommit"])
        state = run.read_primary_state()
        if (state.get("closeOut") or {}).get("status") != "ok":
            self._close_out_failed(run, "failed", "the close-out wrote no terminal record")

    def cleanup(self, run):
        """Every working copy, touched or not, and the close-out's (BR-13). A trust grant still
        recorded for any of them, a close-out that stopped early or a supervisor that died
        between a grant and its revoke, is revoked first (REQ-662 BR-5). What the engine
        rendered and hid in each is restored next, and a removal that takes a working copy's
        own config with it is the engine's own gitdir change (REQ-662 BR-17)."""
        self._revoke_grants(run)
        box = self.box(run)
        self.restore_surfaces(run)
        for spec in run.doc["repos"].values():
            res = self._gitdir_write(run, spec["path"], lambda: box.git(
                spec["path"], ["worktree", "remove", "--force", spec["workingCopy"]]))
            if res.returncode != 0:
                run.doc.setdefault("notes", []).append("cleanup of %s: %s" % (
                    spec["workingCopy"], res.stderr.strip()[:200]))
            box.git(spec["path"], ["branch", "-D", run.doc["branch"]])
            box.git(spec["path"], ["fetch", "--prune", "origin",
                                   "+refs/heads/*:refs/remotes/origin/*"])
            box.log("one_way_move", ["cleanup", spec["workingCopy"]], spec["path"], 0)
        close = run.doc.get("closeOutWorkingCopy")
        if close:
            self._gitdir_write(run, run.primary_path, lambda: box.git(
                run.primary_path, ["worktree", "remove", "--force", close]))
            box.git(run.primary_path, ["branch", "-D", "chore/%s-close-out" % run.req])

    def unblock_after(self, merged):
        """The post-merge unblock pass of /sprint Step 5 over this batch's held REQs."""
        held = []
        for run in self.all_runs():
            if run.status != "blocked":
                continue
            blockers = run.read_primary_state().get("blockers") or []
            if any(isinstance(b, dict) and b.get("blockedBy") == merged.req for b in blockers):
                held.append(run)
        for run in sorted(held, key=self.rank):
            self._rebase_held(run, merged.req)

    def _rebase_held(self, run, blocker):
        box = self.box(run)
        ib = run.doc["integrationBranch"]
        repo = run.primary_path
        if not os.path.isdir(run.wc):
            self.say("manual resume needed for %s (worktree gone)" % run.req)
            return
        eg.fetch_integration(box, repo, ib)
        # The rebase checks out over a hidden path, so the working copy goes back to what it
        # was at launch first; the relaunch renders and hides again (REQ-662 BR-17).
        self.restore_surfaces(run, [run.wc])
        old = box.git(repo, ["rev-parse", "HEAD"], cwd=run.wc).stdout.strip()
        res = box.git(repo, ["rebase", "origin/%s" % ib], cwd=run.wc)
        if res.returncode != 0:
            files = [ln for ln in box.git(repo, ["diff", "--name-only", "--diff-filter=U"],
                                          cwd=run.wc).stdout.splitlines() if ln]
            box.git(repo, ["rebase", "--abort"], cwd=run.wc)
            state = run.read_primary_state()
            limit = int(run.doc["config"]["auto_rebase_max_attempts"])
            state["blockers"] = [{"blockedBy": "manual", "resolvedBlocker": blocker,
                                  "conflictFiles": files, "holdState": "needs-manual-rebase",
                                  "rebaseAttempts": limit}]
            run.write_primary_state(state)
            self.say("%s re-halted: rebase conflicts on %s" % (run.req, ", ".join(files)))
            return
        branch = run.doc["branch"]
        push = box.git(repo, ["push", "--force-with-lease=%s:%s" % (branch, old), "origin",
                              "HEAD:refs/heads/%s" % branch], cwd=run.wc)
        if push.returncode != 0:
            self.say("manual resume needed for %s (rebased, push failed)" % run.req)
            return
        try:
            self._relaunch(run, None)
        except Refused as exc:
            self.say("manual resume needed for %s (%s)" % (run.req, exc))

    # ---- the supervisor --------------------------------------------------------------
    def bind(self):
        self.sup_dir = self.sup_dir or el.create_run_dir(self.environ)
        os.chdir(self.sup_dir)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind("s")
        server.listen(8)
        return server

    def serve_once(self, server, timeout):
        ready, _, _ = select.select([server], [], [], timeout)
        if not ready:
            return
        conn, _ = server.accept()
        with conn:
            conn.settimeout(5)
            data = b""
            try:
                while not data.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                request = json.loads(data.decode("utf-8"))
                reply = self.dispatch(request, peer_pid(conn))
            except Refused as exc:
                reply = {"ok": False, "error": str(exc)}
            except (ValueError, OSError, KeyError) as exc:
                reply = {"ok": False, "error": "bad request: %s" % exc}
            try:
                conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
            except OSError:
                pass

    def dispatch(self, request, pid):
        op = request.get("op")
        if op in LAUNCH_OPS:
            # The kernel's peer pid alone, never the pid the request claims (REQ-662 BR-18).
            self.nested_guard(op, {"ADLC_EXEC_RUN": request.get("execRun")}, pid)
        pid = pid or request.get("callerPid")
        env = {"ADLC_EXEC_RUN": request.get("execRun")} if request.get("execRun") else {}
        if op == "approve":
            shown = self.approve(request["req"], request.get("token"), request.get("gateToken"),
                                 request.get("ack", False), request.get("decidedBy", ""),
                                 request.get("channel", "shell"), pid, env)
            self.kick()
            return {"ok": True, "result": shown}
        if op == "reject":
            self.reject(request["req"], request.get("reason", ""), request.get("decidedBy", ""),
                        request.get("channel", "shell"), pid, env)
        elif op == "answer":
            allow, invocation = self._op_allowance(request, pid)
            self.answer(request["req"], request.get("text", ""), pid, env, allow, invocation)
        elif op == "abort":
            self.abort(request["req"], request.get("decidedBy", ""), pid, env)
        elif op == "reissue":
            run = self._run(request["req"])
            if run.status != "awaiting_approval":
                raise Refused("%s is %s" % (run.req, run.status))
            self.caller_guard(run, env, pid)
            self.announce(run, self.mint(run))
        elif op == "ping":
            return {"ok": True, "pid": os.getpid()}
        else:
            raise Refused("unknown op %r" % op)
        return {"ok": True}

    @staticmethod
    def _op_allowance(request, pid):
        """``(allow_unverified, invocation)`` an op carries: the --allow-unverified its own
        invocation received, and that invocation as the ledger records it, with the caller's
        pid as the kernel reported it. Never this supervisor's own flag (REQ-662 BR-18)."""
        if request.get("allowUnverified") is not True:
            return False, None
        inv = request.get("invocation")
        if not isinstance(inv, dict) or not isinstance(inv.get("id"), str) or not inv["id"] \
                or not isinstance(inv.get("startedAt"), str):
            raise Refused("bad request: --allow-unverified without the invocation that received "
                          "it")
        return True, {"id": inv["id"], "pid": pid or inv.get("pid"),
                      "startedAt": inv["startedAt"]}

    def kick(self):
        """One worker at a time: merges are serialized, approvals stay responsive."""
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self.drain, daemon=True)
            self.worker.start()

    def done(self):
        return not self.pending and not self.children and all(
            r.status in TERMINAL for r in self.all_runs()) and (
            self.worker is None or not self.worker.is_alive())

    def supervise(self, server):
        stop = []
        signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
        signal.signal(signal.SIGINT, lambda *_: stop.append(1))
        try:
            while not stop and not self.done():
                with self.lock:
                    self.poll_once()
                if self.queue:
                    self.kick()
                self.serve_once(server, 0.2)
        finally:
            server.close()
            shutil.rmtree(self.sup_dir, ignore_errors=True)
        return 0

    def resume(self):
        """A new supervisor over this repo's unfinished runs. Fresh tokens at the gate."""
        if self.environ.get("ADLC_EXEC_RUN"):
            raise Refused("%s: resume attempted from inside a run" % PROTOCOL)
        for path in el.run_dirs(self.environ):
            try:
                run = Run.load(path)
            except Refused:
                continue
            if run.doc.get("primary") != self.primary or run.status in TERMINAL:
                continue
            newest = el.find_run(self.primary, run.req, self.environ)
            if newest != path:
                continue
            if client_call(run, {"op": "ping"}) is not None:
                raise Refused("%s is held by a live supervisor" % run.req)
            self.runs[run.req] = run
        if not self.runs:
            raise Refused("no unfinished exec run in this repo")
        for run in self.all_runs():
            run.doc["supervisorDir"] = self.sup_dir
            run.save()
            if run.status == "awaiting_approval":
                self.announce(run, self.mint(run))
            elif run.status in ("approved", "merging"):
                self.queue.append(run.req)


def render_row(run, violations=()):
    """One dashboard row, and for a run at the gate what approval will perform."""
    state = {}
    try:
        state = run.read_wc_state() or run.read_primary_state()
    except OSError:
        pass
    phase = state.get("currentPhase", "?")
    hold = run.doc.get("holdBehind")
    shown = run.status
    if run.status == "approved":
        shown = "approved (queued behind %s)" % hold if hold else "approved"
    elif run.status == "awaiting_approval":
        shown = "Awaiting approval"
    elif run.status == "stalled":
        shown = "stalled since %s, pid %s alive" % (run.exec.get("stalledAt"), run.exec.get("pid"))
    lines = ["| %s | %s/8 | %s | exec:%s | %s |" % (run.req, phase, shown, run.doc["harness"],
                                                   run.exec.get("startedAt"))]
    doc = run.ledger().trusted()
    if doc and run.status in ("awaiting_approval", "approved"):
        plan = doc["plan"]
        for pr in plan["prs"]:
            lines.append("  merge #%s (%s, head %s, oid %s) into %s"
                         % (pr["number"], pr["repo"], run.doc["branch"], pr["headRefOid"],
                            run.doc["integrationBranches"][pr["repo"]]))
        lines.append("  if the branch must rebase: --force-with-lease push of %s"
                     % run.doc["branch"])
        deploy = plan.get("deployPlan")
        if deploy:
            lines.append("  deploy: %s: %s" % (deploy["target"], deploy["command"]))
        elif plan.get("deploySkipped"):
            lines.append("  deploy skipped: %s" % plan["deploySkipped"])
        else:
            lines.append("  deploy: none")
        lines.append("  then: close-out, cleanup")
        for line in plan.get("changesGate") or []:
            lines.append("  %s" % line)
        touched = plan.get(eg.EXEC_PATH_KEY)
        if touched:
            lines.append("  exec path touched: %s; approve will refuse, and --ack-gate-change "
                         "does not cover it (REQ-662 BR-17)" % ", ".join(touched))
        elif not isinstance(touched, list):
            lines.append("  exec-path gate: this plan records no result, so approve will refuse "
                         "and re-halt the run (REQ-662 BR-17)")
        if plan.get("allowUnprotected"):
            lines.append("  allowUnprotected: %s is %s" % (run.doc["integrationBranch"],
                                                           plan.get("protection")))
        if plan.get("sharedCredentials"):
            lines.append("  sharedCredentials: the run used the operator's forge credentials")
        for entry in plan.get("allowUnverified") or []:
            lines.append("  allowUnverified: the %s by invocation %s (pid %s) ran unverified: %s"
                         % (entry["launch"], entry["invocation"]["id"],
                            entry["invocation"]["pid"], ", ".join(entry["unverified"])))
        if run.doc.get("resume") == "impossible":
            why = ("the harness declares no resume" if run.exec.get("sessionId")
                   else "the run's output carried no session id")
            lines.append("  resume: impossible: %s, so resume is impossible and the close-out "
                         "will not run after the merge" % why)
    if run.status == "blocked":
        for item in run.read_primary_state().get("blockers") or []:
            lines.append("  blocked: a person must look: %s" % json.dumps(item)[:300])
    closing = run.read_primary_state().get("closeOut")
    if isinstance(closing, dict) and closing.get("status") not in (None, "ok"):
        lines.append("  close-out: %s — %s" % (closing.get("status"), closing.get("reason")))
    for evidence in violations:
        lines.append("  %s: %s" % (PROTOCOL, evidence))
    for note in run.doc.get("notes", []):
        lines.append("  note: %s" % note)
    return lines


# ---- the plain-shell clients -----------------------------------------------------------
def repo_root(cwd):
    res = subprocess.run(["git", "-C", cwd, "rev-parse", "--path-format=absolute",
                          "--git-common-dir"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    if res.returncode != 0:
        raise Refused("not inside a git repository")
    return os.path.realpath(os.path.dirname(res.stdout.strip()))


def client_call(run, request):
    """One request to the run's supervisor, or None when no supervisor answers."""
    sup = run.doc.get("supervisorDir")
    if not sup or not os.path.isdir(sup):
        return None
    here = os.getcwd()
    try:
        os.chdir(sup)
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(30)
        conn.connect("s")
    except OSError:
        return None
    finally:
        os.chdir(here)
    with conn:
        conn.sendall((json.dumps(request) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8")) if data else None


def status_lines(primary, environ):
    lines = ["| REQ | Phase | Status | Engine | Started |", "|---|---|---|---|---|"]
    newest = {}
    for path in el.run_dirs(environ):
        doc = el.read_json(os.path.join(path, el.RUN_RECORD), {}) or {}
        if doc.get("primary") == primary:
            stamp = (doc.get("exec") or {}).get("startedAt", "")
            if doc["req"] not in newest or stamp >= newest[doc["req"]][0]:
                newest[doc["req"]] = (stamp, path)
    for req in sorted(newest):
        run = Run.load(newest[req][1])
        lines += render_row(run, violations_of(run))
        if run.status == "awaiting_approval":
            lines.append("  tokens are on the supervisor's dashboard; "
                         "`adlc sprint-exec reissue %s` prints fresh ones" % req)
    return lines


def _parser():
    parser = argparse.ArgumentParser(prog="adlc sprint-exec",
                                     description="the /sprint exec engine (REQ-659)")
    sub = parser.add_subparsers(dest="verb")
    run = sub.add_parser("run", help="pre-flight, launch, and supervise a batch")
    run.add_argument("reqs", nargs="+")
    run.add_argument("--harness", default="claude")
    run.add_argument("--allow-unprotected", action="store_true")
    run.add_argument("--shared-credentials", action="store_true")
    run.add_argument("--harness-flag", action="append", default=[])
    run.add_argument("--allow-unverified", action="store_true",
                     help="launch an adapter BR-11 reads unverified, with a loud line per launch; "
                          "this invocation's launches only, never approve (REQ-662)")
    sub.add_parser("resume", help="a new supervisor over this repo's unfinished runs")
    status = sub.add_parser("status", help="the dashboard, without tokens")
    status.add_argument("--json", action="store_true")
    for name in ("approve", "reject", "answer", "abort", "reissue"):
        cmd = sub.add_parser(name)
        cmd.add_argument("req")
        cmd.add_argument("--channel", choices=("skill", "shell"), default="shell")
        if name == "approve":
            cmd.add_argument("--token", default="")
            cmd.add_argument("--ack-gate-change", action="store_true")
            cmd.add_argument("--gate-token", default="")
        if name in ("reject", "answer"):
            cmd.add_argument("text", nargs="?", default="")
        if name == "answer":
            cmd.add_argument("--allow-unverified", action="store_true",
                             help="relaunch an adapter BR-11 reads unverified, for this answer's "
                                  "relaunch only (REQ-662)")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if not args.verb:
        _parser().print_help()
        return 2
    try:
        return _dispatch(args)
    except Refused as exc:
        sys.stderr.write("adlc sprint-exec: refused: %s\n" % exc)
        return 2
    except (es.SafetyError, eg.GateError, ea.ExecRefused) as exc:
        sys.stderr.write("adlc sprint-exec: refused: %s\n" % exc)
        return 2


def _dispatch(args):
    primary = repo_root(os.getcwd())
    orch = Orchestrator(primary)
    if args.verb in ("run", "resume"):
        # Before the supervisor's directory is made (REQ-662 BR-18).
        orch.nested_guard(args.verb, orch.environ, os.getpid())
    if args.verb == "run":
        server = orch.bind()
        try:
            batch = orch.preflight(args.reqs, args.harness, args.shared_credentials,
                                   args.allow_unprotected, args.harness_flag,
                                   allow_unverified=args.allow_unverified)
            orch.launch_batch(args.reqs, batch)
        except BaseException:
            server.close()
            shutil.rmtree(orch.sup_dir, ignore_errors=True)
            raise
        return orch.supervise(server)
    if args.verb == "resume":
        server = orch.bind()
        try:
            orch.resume()
        except BaseException:
            server.close()
            shutil.rmtree(orch.sup_dir, ignore_errors=True)
            raise
        return orch.supervise(server)
    if args.verb == "status":
        for line in status_lines(primary, orch.environ):
            print(line)
        return 0
    return _client(orch, args)


def _client(orch, args):
    run = orch._run(args.req)
    user = orch.environ.get("USER", "")
    request = {"op": args.verb, "req": args.req, "decidedBy": user, "channel": args.channel,
               "callerPid": os.getpid(), "execRun": orch.environ.get("ADLC_EXEC_RUN")}
    if args.verb == "approve":
        request.update({"token": args.token, "gateToken": args.gate_token,
                        "ack": args.ack_gate_change})
    elif args.verb == "reject":
        request["reason"] = args.text
    elif args.verb == "answer":
        request["text"] = args.text
        if args.allow_unverified:
            # For this answer's relaunch alone, and the ledger names this invocation (BR-18).
            request.update({"allowUnverified": True, "invocation": orch.invocation})
    env = orch.environ
    pid = os.getpid()
    orch.caller_guard(run, env, pid)
    reply = client_call(run, request)
    if reply is None:
        if args.verb == "reject":
            orch.reject(args.req, args.text, user, args.channel, pid, env)
        elif args.verb == "abort":
            orch.abort(args.req, user, pid, env)
        else:
            raise Refused("no live supervisor holds this run: `adlc sprint-exec resume`, "
                          "then read the fresh token from its dashboard")
        return 0
    if not reply.get("ok"):
        raise Refused(reply.get("error", "refused"))
    print(reply.get("result") or "%s: %s recorded" % (args.req, args.verb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
