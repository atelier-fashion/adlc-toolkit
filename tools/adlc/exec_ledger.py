#!/usr/bin/env python3
"""exec_ledger — run directories, the approval ledger and tokens (REQ-659 BR-10).

A same-UID model is treated as an adversary, not a typo. So a run directory has a random
128-bit name under ``$XDG_STATE_HOME``, mode 0700, and neither state nor any prompt names
it. Every ledger write replaces the file wholesale, and the run record keeps the hash of
each, so a ledger nobody accounts for is detected rather than read. A token is printed
once and only its digest is kept, in the supervisor's memory (ADR-4).

Standard library only.
"""

import contextlib
import hashlib
import json
import os
import secrets
import tempfile
import time

LEDGER = "approval.json"
RUN_RECORD = "run.json"
#: How often a taker looks at a held ``mkdir`` lock again.
LOCK_POLL_S = 0.02
#: The most a state file the model writes may hold before the engine parses it: a working
#: copy's ``pipeline-state.json`` and the close-out's copy of it. A real one is a few
#: kilobytes, so this is two orders above that; a larger one is refused unread.
STATE_FILE_MAX_BYTES = 512 * 1024


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


@contextlib.contextmanager
def mkdir_lock(path, timeout, refused, holder="another adlc run is writing the file",
               poll=LOCK_POLL_S):
    """The ``mkdir`` lock directory at ``path``, held for the block: the id allocator's
    pattern, and the one implementation every exec lock uses (LESSON-014).

    The directory that holds ``path`` must exist. A symlink at ``path`` is refused before
    each attempt to take the lock, and a lock still held after ``timeout`` seconds, measured
    on the monotonic clock, is refused naming it (``holder`` says who is likely to hold it).
    Every refusal raises ``refused(message)``: the caller's exception type, or any callable
    that builds one.

    The release removes the directory only while it is still not a symlink, and it never
    raises: a lock it cannot remove (something was left in it, a symlink was swapped in)
    stays where it is, and the next taker refuses it by name. So the exception the body
    raised is always the one that propagates."""
    deadline = time.monotonic() + timeout
    while True:
        if os.path.islink(path):
            raise refused("%s is a symlink: refusing (TOCTOU risk, LESSON-014). Inspect it by "
                          "hand" % path)
        try:
            os.mkdir(path, 0o700)
            break
        except FileExistsError:
            pass
        except FileNotFoundError:
            raise refused("cannot take %s: %s does not exist" % (path, os.path.dirname(path)))
        if time.monotonic() >= deadline:
            raise refused("could not take %s in %ss: %s, or one died holding the lock; remove "
                          "the directory once no exec run is live" % (path, timeout, holder))
        time.sleep(poll)
    try:
        yield path
    finally:
        try:
            if not os.path.islink(path):
                os.rmdir(path)
        except OSError:
            pass


def atomic_json(path, doc):
    data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(path, data)
    return hashlib.sha256(data).hexdigest()


def read_json(path, default=None, max_bytes=None):
    """``path`` parsed as JSON, or ``default`` when it cannot be read or parsed: a parse error,
    and a document nested too deep for the parser (its ``RecursionError``), which a model can
    write into a file the engine reads. With ``max_bytes``, a file larger than that is not
    parsed at all and reads as ``default``."""
    try:
        with open(path, "rb") as fh:
            data = fh.read() if max_bytes is None else fh.read(max_bytes + 1)
    except OSError:
        return default
    if max_bytes is not None and len(data) > max_bytes:
        return default
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
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


def invocation():
    """This process's identity in the audit trail: a random id, its pid and when it started.
    Minted once per orchestrator, so the ledger names the one invocation that received
    ``--allow-unverified`` (REQ-662 BR-18)."""
    return {"id": secrets.token_hex(8), "pid": os.getpid(), "startedAt": now()}


def allow_unverified_entry(inv, where, subjects):
    """One launch made under ``--allow-unverified``: the invocation that received the flag,
    what was launched (``launch``, ``relaunch``, ``close-out``), when, and what was unverified.
    The run record keeps each; the halt copies them into the ledger's plan."""
    return {"invocation": dict(inv), "launch": where, "at": now(), "unverified": list(subjects)}


def token_digest(token, binding=""):
    """A token's digest. A gate token's digest is bound to the plan line it answers."""
    return hashlib.sha256(("%s\0%s" % (binding, token)).encode("utf-8")).hexdigest()
