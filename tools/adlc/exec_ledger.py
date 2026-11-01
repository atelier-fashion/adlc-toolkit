#!/usr/bin/env python3
"""exec_ledger — run directories, the approval ledger and tokens (REQ-659 BR-10).

A same-UID model is treated as an adversary, not a typo. So a run directory has a random
128-bit name under ``$XDG_STATE_HOME``, mode 0700, and neither state nor any prompt names
it. Every ledger write replaces the file wholesale, and the run record keeps the hash of
each, so a ledger nobody accounts for is detected rather than read. A token is printed
once and only its digest is kept, in the supervisor's memory (ADR-4).

Standard library only.
"""

import hashlib
import json
import os
import secrets
import tempfile
import time

LEDGER = "approval.json"
RUN_RECORD = "run.json"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def state_home(environ=None):
    environ = os.environ if environ is None else environ
    base = environ.get("XDG_STATE_HOME")
    if base and os.path.isabs(base):
        return base
    return os.path.join(environ.get("HOME") or os.path.expanduser("~"), ".local", "state")


def exec_root(environ=None):
    return os.path.join(state_home(environ), "adlc", "exec")


def _mkdir_private(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def create_run_dir(environ=None):
    """A new run directory: a random 128-bit name, mode 0700."""
    root = exec_root(environ)
    _mkdir_private(root)
    path = os.path.join(root, secrets.token_hex(16))
    os.mkdir(path, 0o700)
    return path


def atomic_write(path, data):
    """Replace ``path``: a temp file in the same directory, then a rename."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_json(path, doc):
    data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(path, data)
    return hashlib.sha256(data).hexdigest()


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def run_dirs(environ=None):
    root = exec_root(environ)
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isfile(os.path.join(path, RUN_RECORD)):
            out.append(path)
    return out


def find_run(primary, req, environ=None):
    """The newest run directory of ``req`` in the repo at ``primary``, or None."""
    primary = os.path.realpath(primary)
    best = None
    for path in run_dirs(environ):
        doc = read_json(os.path.join(path, RUN_RECORD), {}) or {}
        if doc.get("req") == req and doc.get("primary") == primary:
            stamp = (doc.get("exec") or {}).get("startedAt", "")
            if best is None or stamp >= best[0]:
                best = (stamp, path)
    return best[1] if best else None


class LedgerError(ValueError):
    """The ledger is not what the run record says it is."""


class Ledger(object):
    """``<run directory>/approval.json``. ``record`` is the run's mutable record."""

    def __init__(self, run_dir, record):
        self.path = os.path.join(run_dir, LEDGER)
        self.record = record

    def exists(self):
        return os.path.exists(self.path)

    def read(self):
        return read_json(self.path)

    def trusted(self):
        """The ledger, or None when it is absent or the run record does not account for it."""
        return self.read() if self.exists() and self.accounted() else None

    def _digest(self):
        with open(self.path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def accounted(self):
        """Whether the file on disk is the last one the orchestrator wrote."""
        if not self.exists():
            return self.record.get("ledgerHash") is None
        return self._digest() == self.record.get("ledgerHash")

    def write(self, doc):
        self.record["ledgerHash"] = atomic_json(self.path, doc)
        self.record.setdefault("ledgerWrites", []).append(self.record["ledgerHash"])
        return doc

    def halt_write(self, plan):
        """The plan, once per halt, wholesale. An unaccounted file raises."""
        if not self.accounted():
            raise LedgerError("a ledger the run record does not account for is present")
        previous = self.read() if self.exists() else {}
        return self.write({"req": self.record["req"], "plan": plan, "decision": None,
                           "superseded": previous.get("superseded", [])})

    def decide(self, decision, decided_by, channel, caller_pid, reason="", ack_gate_change=False):
        if not self.accounted():
            raise LedgerError("a ledger the run record does not account for is present")
        doc = self.read()
        doc["decision"] = {"decision": decision, "decidedAt": now(), "decidedBy": decided_by,
                           "channel": channel, "callerPid": caller_pid, "reason": reason,
                           "ackGateChange": bool(ack_gate_change)}
        return self.write(doc)

    def supersede(self, plan, why):
        """A plan the operator did not see replaces the one they approved (BR-11)."""
        doc = self.read()
        if doc.get("decision"):
            doc.setdefault("superseded", []).append(dict(doc["decision"], supersededBecause=why))
        doc["decision"] = None
        doc["plan"] = plan
        return self.write(doc)

    def update_plan(self, plan):
        doc = self.read()
        doc["plan"] = plan
        return self.write(doc)


def mint_token():
    return secrets.token_hex(16)


def token_digest(token, binding=""):
    """A token's digest. A gate token's digest is bound to the plan line it answers."""
    return hashlib.sha256(("%s\0%s" % (binding, token)).encode("utf-8")).hexdigest()
