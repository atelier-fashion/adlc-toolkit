#!/bin/sh
# partials/session-record.sh — the `session-record` hook command (REQ-657 BR-10;
# REQ-660 BR-5 to BR-8, ADR-4, ADR-7).
#
# adlc_session_record [--harness <name>] [--field <item>=<payload key>]...
#   Reads the harness's session-start payload (JSON) on stdin and writes the session
#   sidecar .adlc/.session/<id>, mode 600, as key=value lines in this order:
#     harness=          claude, copilot, codex, gemini, cursor, antigravity or unknown
#     session_id=       the harness's id when it is safe, else gen-<16 hex>
#     transcript_path=  an absolute path under $HOME, else empty
#     cwd=              the payload's working tree, else the current directory
#     started_at=       UTC ISO-8601; a re-fire for the same id keeps the first value
#   Then it deletes what the writer left in that directory more than 30 days ago.
#
#   Writes only when ./.adlc/ is a real directory, only under ./.adlc/.session/, and
#   never through a symlink. Prints nothing (a session-start hook's stdout becomes
#   model context) and returns 0 on every path, so it never fails a session. With no
#   python3 it writes nothing, and /wrapup's walk still finds the transcript.
#
#   --harness names the harness, and --field names the payload key for session_id,
#   cwd and transcript_path; an item with no --field is not read. Without --harness
#   (the shared `claude` render, which Copilot CLI and Cursor read as-is) the harness
#   comes from TABLE, and a payload matching no row reads the claude keys and records
#   `unknown`. A row is added from a captured payload, never from a survey:
#   tools/adlc/tests/test_session_record_table.py holds each one equal to its
#   adapter's hook_payload. Nothing here searches for a transcript path.
#
#   The sidecar is not trusted by its reader: /wrapup accepts a transcript only when
#   it holds that run's mark (ADR-1). `.gitignore` and `.tmp-<pid>` start with a dot,
#   so discovery, which skips dotfiles, never reads them as sidecars.
#
# One Python program, because the contract is more than POSIX sh should hold (ADR-4).
# `command` defeats a shell function named python3 (LESSON-717). `-I` keeps a planted
# json.py in the repo, this hook's working directory, off sys.path; the program is
# stdlib only, so it can afford that. The text sits in single quotes, so it must never
# hold a single quote. The file stays a sourceable, silent *.sh (guard_partials).
_adlc_sr_prog='
import json, os, re, select, stat, sys, time

TABLE = {"claude": {"session_id": "session_id", "cwd": "cwd", "transcript_path": "transcript_path", "marker": "/.claude/projects/"}}

HARNESSES = ("claude", "copilot", "codex", "gemini", "cursor", "antigravity", "unknown")
ITEMS = ("session_id", "cwd", "transcript_path")
SESSION_DIR = ".adlc/.session"
RETENTION_S = 30 * 86400
STDIN_DEADLINE_S = 2
STDIN_CAP = 1024 * 1024
SIDECAR_CAP = 64 * 1024
# Used with fullmatch only: a pattern ending in a dollar sign would pass a trailing newline.
SAFE_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")
STARTED_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def read_stdin():
    data = b""
    deadline = time.monotonic() + STDIN_DEADLINE_S
    try:
        if os.isatty(0):
            return data
        while len(data) < STDIN_CAP:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([0], [], [], left)[0]:
                break
            chunk = os.read(0, STDIN_CAP - len(data))
            if not chunk:
                break
            data += chunk
    except (OSError, ValueError):
        pass
    return data


def read_payload():
    try:
        payload = json.loads(read_stdin())
    except (ValueError, RecursionError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_args(argv):
    harness, fields = None, {}
    i = 0
    while i + 1 < len(argv):
        flag, value = argv[i], argv[i + 1]
        if flag == "--harness":
            harness = value
        elif flag == "--field":
            item, _, key = value.partition("=")
            if item in ITEMS and key:
                fields[item] = key
        else:
            i += 1
            continue
        i += 2
    return harness, fields


def resolve(harness, fields, payload):
    """The harness name and the map from item to payload key."""
    if harness is not None:
        return (harness if harness in HARNESSES else "unknown"), fields
    for name, row in TABLE.items():
        tp = payload.get(row["transcript_path"])
        sid = payload.get(row["session_id"])
        if isinstance(tp, str) and row["marker"] in tp and isinstance(sid, str):
            return name, row
    return "unknown", TABLE["claude"]


def recordable(value):
    """A non-empty string that stays one line of a sidecar."""
    if not isinstance(value, str) or not value:
        return False
    if any(c < " " or "\x7f" <= c <= "\x9f" for c in value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def session_id(value):
    if isinstance(value, str) and SAFE_ID.fullmatch(value):
        return value
    return "gen-" + os.urandom(8).hex()


def transcript_path(value):
    home = os.environ.get("HOME", "")
    if not recordable(value) or not os.path.isabs(value) or not os.path.isabs(home):
        return ""
    if ".." in value.split("/"):
        return ""
    try:
        contained = os.path.realpath(value).startswith(os.path.realpath(home) + "/")
    except (OSError, ValueError):
        return ""
    return value if contained else ""


def working_tree(value):
    if recordable(value):
        return value
    here = os.getcwd()
    return here if recordable(here) else ""


def previous_started_at(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        text = os.read(fd, SIDECAR_CAP).decode("utf-8", "replace")
    finally:
        os.close(fd)
    for line in text.split("\n"):
        key, _, value = line.partition("=")
        if key == "started_at" and STARTED_AT.fullmatch(value):
            return value
    return None


def keep_ignored():
    """ADR-7: a consumer has this hook before it has the top-level gitignore line."""
    path = os.path.join(SESSION_DIR, ".gitignore")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if os.read(fd, 16) == b"*\n":
                return
        finally:
            os.close(fd)
    except OSError:
        pass
    # A repo can commit this file, and a sidecar holds a home path, so anything else
    # is replaced, through a rename so that a symlink here is replaced, not followed.
    write_sidecar(path, b"*\n")


def write_sidecar(path, data):
    tmp = os.path.join(SESSION_DIR, ".tmp-%d" % os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            # The mode given to open() is masked by the umask; this one is not.
            os.fchmod(fh.fileno(), 0o600)
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def prune():
    """By name as well as age, so a .gitignore or a stranger is never a candidate."""
    cutoff = time.time() - RETENTION_S
    for name in os.listdir(SESSION_DIR):
        if not (SAFE_ID.fullmatch(name) or name.startswith(".tmp-")):
            continue
        path = os.path.join(SESSION_DIR, name)
        try:
            if os.lstat(path).st_mtime < cutoff:
                os.unlink(path)
        except OSError:
            pass


def main():
    harness, fields = parse_args(sys.argv[1:])
    payload = read_payload()
    harness, keys = resolve(harness, fields, payload)
    if os.path.islink(SESSION_DIR):
        return
    os.makedirs(SESSION_DIR, mode=0o700, exist_ok=True)
    keep_ignored()
    sid = session_id(payload.get(keys.get("session_id")))
    path = os.path.join(SESSION_DIR, sid)
    started = previous_started_at(path) or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = (
        ("harness", harness),
        ("session_id", sid),
        ("transcript_path", transcript_path(payload.get(keys.get("transcript_path")))),
        ("cwd", working_tree(payload.get(keys.get("cwd")))),
        ("started_at", started),
    )
    text = "".join("%s=%s\n" % line for line in lines)
    try:
        write_sidecar(path, text.encode("utf-8"))
    finally:
        prune()


try:
    main()
except BaseException:
    pass
'

adlc_session_record() {
  [ -d .adlc ] || return 0
  [ -L .adlc ] && return 0
  command -v python3 >/dev/null 2>&1 || return 0
  command python3 -I -c "$_adlc_sr_prog" "$@" >/dev/null 2>&1 || true
  return 0
}
