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


def stragglers(req):
    """Live processes still carrying ``ADLC_EXEC_RUN=<req>`` in their environment."""
    res = subprocess.run([PS, "eww", "-axo", "pid=,command="], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, universal_newlines=True, errors="replace")
    needle = "ADLC_EXEC_RUN=%s" % req
    out = []
    for line in res.stdout.splitlines():
        head = line.strip().split(None, 1)
        if len(head) == 2 and head[0].isdigit() and int(head[0]) != os.getpid():
            if re.search(r"(^|\s)%s(\s|$)" % re.escape(needle), head[1]):
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

    # ---- small helpers ---------------------------------------------------------------
    def say(self, line):
        self.out.write(line + "\n")
        self.out.flush()

    def box(self, run):
        if run.req not in self.boxes:
            self.boxes[run.req] = es.Toolbox.load(run.path, self.toolkit, self.environ)
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

    def preflight(self, reqs, harness="claude", shared=False, allow_unprotected=False, flags=()):
        batch = Batch()
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
        if adapter.trust_grant != "none":
            raise Refused("exec.trust_grant %s has no engine arm yet: %s"
                          % (adapter.trust_grant, ea.SIBLING_REQ))
        batch.binary = shutil.which(adapter.binary, path=self.environ.get("PATH", ""))
        if not batch.binary:
            raise Refused("%s is not on PATH" % adapter.binary)
        text = self.read_config_text()
        try:
            batch.config = eg.exec_config(text)
            batch.repos, batch.order = self.registry(text)
        except eg.GateError as exc:
            raise Refused(str(exc))
        batch.flags = [str(f) for f in batch.config["harness_flags"]] + list(flags)
        try:
            ea.refuse_forbidden(batch.flags, adapter.forbidden)
            adapter.tiers("feat/preflight", batch.config["allow_extra"])
        except ea.ExecRefused as exc:
            raise Refused(str(exc))
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
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if batch.protection != "protected":
            line = "%s on %s is %s, so a direct push from a run is not stopped by the forge " \
                   "(%s)" % (ib, self.primary, batch.protection, "Rule B")
            if batch.config["require_branch_protection"] and not allow_unprotected:
                raise Refused(line + "; pass --allow-unprotected to accept that for this run")
            self.say("WARNING: " + line)
        self.batch = batch
        return batch

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
        box = es.Toolbox(run_dir, self.toolkit, self.environ)
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
        run = Run(run_dir, doc)
        try:
            data = ep.pipeline_prompt(self.toolkit, self.primary, req, branch, self.primary,
                                      repos[rid]["workingCopy"])
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            raise Refused(str(exc))
        el.atomic_write(run.file("prompt.txt"), data)
        os.makedirs(run.file("gh-empty"), exist_ok=True)
        run.save()
        self.runs[req] = run
        self.boxes[req] = box
        self.adapters[batch.adapter.name] = batch.adapter
        return run

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

    def grant_trust(self, run):
        """Per run, per working copy. `none` records the moment and writes nothing (ADR-5)."""
        run.exec["trustGrantedAt"] = el.now()
        run.exec["trustRevokedAt"] = None
        self.box(run).log("trust_granted", [run.exec["trustMechanism"]], run.wc, 0)

    def revoke_trust(self, run):
        if run.exec.get("trustGrantedAt") and not run.exec.get("trustRevokedAt"):
            run.exec["trustRevokedAt"] = el.now()
            self.box(run).log("trust_revoked", [run.exec["trustMechanism"]], run.wc, 0)

    def _argv(self, run, resume=None, extra=(), add_dir=None):
        adapter = self.adapter(run)
        allow, deny = adapter.tiers(run.doc["branch"], run.doc["config"]["allow_extra"])
        return adapter.launch_argv(run.doc["binary"], allow, deny, resume=resume,
                                   extra=list(run.doc["flags"]) + list(extra), add_dir=add_dir)

    def _child_env(self, run):
        adapter = self.adapter(run)
        token = None
        if not run.doc["sharedCredentials"]:
            var = str(run.doc["config"]["child_gh_token"])
            token = self.environ.get(var)
            if not token:
                raise Refused("%s is not set in this shell, and the child's token comes from it"
                              % var)
        return adapter.child_env(self.environ, run.req, token, run.file("gh-empty"),
                                 run.doc["sharedCredentials"])

    def _spawn(self, run, argv, prompt, cwd, stem):
        env = self._child_env(run)
        box = self.box(run)
        box.log("exec_launch", argv, cwd, None)
        with open(run.file(stem + ".json"), "wb") as out, \
                open(run.file(stem + ".stderr.log"), "wb") as err, \
                open(prompt, "rb") as stdin:
            return subprocess.Popen(argv, stdin=stdin, stdout=out, stderr=err, cwd=cwd, env=env,
                                    start_new_session=True)

    def spawn(self, run):
        box = self.box(run)
        for rid, spec in run.doc["repos"].items():
            self._make_worktree(box, spec["path"], spec["workingCopy"], run.doc["branch"],
                                run.doc["integrationBranches"][rid])
        self.grant_trust(run)
        self._launch_first(run, "prompt.txt", self._argv(run))

    def _launch_first(self, run, prompt_name, argv):
        run.doc["launches"] += 1
        stem = "stdout" if run.doc["launches"] == 1 else "stdout.%d" % run.doc["launches"]
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
                    and run.exec.get("pid") and run not in self.pending \
                    and not pid_alive(run.exec["pid"]):
                self.on_exit(run, None)         # a harness that outlived its supervisor
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
        """After the leader exits: kill its group and sweep stragglers (ADR-2)."""
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.time() + 2
        left = stragglers(run.req)
        while left and time.time() < deadline:
            for other in left:
                try:
                    os.kill(other, signal.SIGTERM)
                except OSError:
                    pass
            time.sleep(0.1)
            left = stragglers(run.req)
        for other in left:
            try:
                os.kill(other, signal.SIGKILL)
            except OSError:
                pass
        if left:
            time.sleep(0.2)
            left = stragglers(run.req)
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
        if left:
            run.doc.setdefault("notes", []).append("stragglers survived the sweep: %s" % left)
        return left

    def _read_result(self, run, name):
        try:
            with open(run.file(name), encoding="utf-8", errors="replace") as fh:
                return self.adapter(run).parse_result(fh.read())
        except OSError:
            return self.adapter(run).parse_result("")

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
        stem = run.exec["logPath"]
        result = self._read_result(run, stem)
        claim = ea.terminal_claim(result["text"])
        klass = self.adapter(run).exit_class(rc, result, claim)
        run.exec.update({"exitCode": rc, "exitClass": klass,
                         "sessionId": result["session_id"], "stalledAt": None})
        run.doc["finalReport"] = result["text"]
        notice = self._stderr_notice(run, stem.replace(".json", ".stderr.log"))
        if notice:
            run.doc.setdefault("notes", []).append("harness said: %s" % notice)
        self.box(run).log("exec_exit", [str(rc), klass, str(claim)], run.wc, rc)
        state = run.read_wc_state()
        self._model_values(run, state)
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
        elif state.get("status") == "awaiting_approval":
            self._halt(run, state, result)
        elif klass == "denied":
            self._block(run, state, "the harness was denied: %s"
                        % json.dumps(result["denials"])[:300])
        elif state.get("status") == "blocked" or (claim == "blocked" and state.get("blockers")):
            self._terminal(run, "blocked", self._halt_token(state), state)
        else:
            last = (result["text"] or "").strip()[:300]
            run.doc.setdefault("notes", []).append(
                "exit %s, class %s, is_error %s: %s" % (rc, klass, result["is_error"], last))
            self._terminal(run, "failed", "other", state, note=last)

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
        prs = []
        changed = []
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
        lines = eg.gate_lines(changed, hits)
        protection = box.forge("adlc_forge_branch_protection", [ib],
                               run.primary_path).stdout.strip() or "unknown"
        return {"prs": prs, "deployPlan": deploy, "deploySkipped": skipped, "changesGate": lines,
                "ackGateChange": False, "changedPaths": sorted(set(changed)),
                "allowUnprotected": run.doc["allowUnprotected"],
                "sharedCredentials": run.doc["sharedCredentials"], "protection": protection}

    def _halt(self, run, state, result):
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
        run.status = "awaiting_approval"
        run.doc["resume"] = "ok" if run.exec["sessionId"] else "impossible"
        self._carry(run, state)
        self.announce(run, self.mint(run))

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
            lines = plan.get("changesGate") or []
            if lines:
                if not ack:
                    raise Refused("%s changes the gate, so approve needs --ack-gate-change: %s"
                                  % (req, "; ".join(lines)))
                bound = el.token_digest(gate_token or "", "\n".join(lines))
                if bound != held["gate"]:
                    raise Refused("%s: --ack-gate-change needs the token bound to that line" % req)
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
            self._emit(run, "failed", "other")
            self.say("%s rejected: %s" % (req, reason))
            self._release_holds()

    def answer(self, req, text, caller_pid=None, caller_env=None):
        """A fresh process in the same working copy, carrying the reply (BR-14)."""
        with self.lock:
            run = self._run(req)
            self.caller_guard(run, caller_env, caller_pid)
            if run.status != "blocked":
                raise Refused("%s is %s, not blocked" % (req, run.status))
            self._relaunch(run, text)

    def _relaunch(self, run, text):
        branch = run.doc["branch"]
        try:
            data = ep.pipeline_prompt(self.toolkit, self.primary, run.req, branch, self.primary,
                                      run.wc, answer=text if text is not None else
                                      "The REQ this run was held behind has merged, and this "
                                      "branch has been rebased. Continue.")
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            raise Refused(str(exc))
        name = "prompt.%d.txt" % (run.doc["launches"] + 1)
        el.atomic_write(run.file(name), data)
        self.grant_trust(run)
        self._launch_first(run, name, self._argv(run))

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
        help_out = subprocess.run([run.doc["binary"], "--help"], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, universal_newlines=True,
                                  env=self._child_env(run)).stdout
        if not adapter.isolation_available(help_out):
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
        box.log("trust_granted", [run.exec["trustMechanism"]], path, 0)
        try:
            deploy = (plan.get("deployPlan") or {}).get("command", "")
            data = ep.closeout_prompt(self.toolkit, run.req, branch, path,
                                      self._evidence(run, plan), deploy)
        except (ep.PromptBuildError, ep.PromptRefused) as exc:
            self._close_out_failed(run, "failed", str(exc))
            return
        el.atomic_write(run.file("close-out-prompt.txt"), data)
        allow, deny = adapter.tiers(branch, run.doc["config"]["allow_extra"])
        settings = run.file("settings.json")
        el.atomic_json(settings, adapter.settings_document(allow, deny))
        argv = adapter.launch_argv(run.doc["binary"], allow, deny, resume=sid,
                                   extra=adapter.isolation_flags(settings),
                                   add_dir=os.path.join(repo, run.doc["specDir"]))
        proc = self._spawn(run, argv, run.file("close-out-prompt.txt"), path, "close-out")
        run.exec["closeOutPid"] = proc.pid
        self._write_status(run)
        rc = proc.wait()
        self.reap(run, proc.pid)
        box.log("trust_revoked", [run.exec["trustMechanism"]], path, 0)
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
        """Every working copy, touched or not, and the close-out's (BR-13)."""
        box = self.box(run)
        for spec in run.doc["repos"].values():
            res = box.git(spec["path"], ["worktree", "remove", "--force", spec["workingCopy"]])
            if res.returncode != 0:
                run.doc.setdefault("notes", []).append("cleanup of %s: %s" % (
                    spec["workingCopy"], res.stderr.strip()[:200]))
            box.git(spec["path"], ["branch", "-D", run.doc["branch"]])
            box.git(spec["path"], ["fetch", "--prune", "origin",
                                   "+refs/heads/*:refs/remotes/origin/*"])
            box.log("one_way_move", ["cleanup", spec["workingCopy"]], spec["path"], 0)
        close = run.doc.get("closeOutWorkingCopy")
        if close:
            box.git(run.primary_path, ["worktree", "remove", "--force", close])
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
        self._relaunch(run, None)

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
            self.answer(request["req"], request.get("text", ""), pid, env)
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
        if plan.get("allowUnprotected"):
            lines.append("  allowUnprotected: %s is %s" % (run.doc["integrationBranch"],
                                                           plan.get("protection")))
        if plan.get("sharedCredentials"):
            lines.append("  sharedCredentials: the run used the operator's forge credentials")
        if run.doc.get("resume") == "impossible":
            lines.append("  resume: impossible (no session id): the close-out will not run")
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
    if args.verb == "run":
        if orch.environ.get("ADLC_EXEC_RUN"):
            raise Refused("%s: run attempted from inside a run" % PROTOCOL)
        server = orch.bind()
        try:
            batch = orch.preflight(args.reqs, args.harness, args.shared_credentials,
                                   args.allow_unprotected, args.harness_flag)
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
