#!/usr/bin/env python3
"""Append one dated AdoptionSnapshot row to a private file (REQ-672 BR-6, BR-7, ADR-7).

    python3 tools/launch/adoption_snapshot.py [--repo OWNER/NAME] [--hf-dataset ID]
        [--hf-space ID] [--out PATH] [--dry-run]

A maintainer tool, run from a clone. No skill, partial, hook, ``adlc`` subcommand or
installed copy of the toolkit calls it (ADR-1). Each run reads only what the platforms
already give the repo and dataset owner, and appends one JSON line.

Sources, and the only reads this file makes:

- ``github``: ``gh api repos/<repo>`` gives ``github_stars`` and ``github_forks``;
- ``github_traffic``: ``gh api`` on ``repos/<repo>/traffic/views``, ``.../traffic/clones``
  and ``.../traffic/popular/referrers`` gives ``github_views_14d``, ``github_clones_14d``
  and ``top_referrers``. If any of the three reads fails, the source takes that class
  and all three fields stay ``null``;
- ``hf_dataset``: a GET of ``https://huggingface.co/api/datasets/<id>`` gives
  ``hf_dataset_downloads``;
- ``hf_space``: a GET of ``https://huggingface.co/api/spaces/<id>`` gives ``hf_space_likes``;
- ``hf_space_runs``: no read. REQ-670 ADR-7 gives the Space no content-free run counter,
  so the field is ``null`` and the source is ``no-source``.

Every ``gh`` call is ``gh api <path>`` and nothing else, and every Hub read is a GET with
no body. ``--repo`` defaults to :data:`DEFAULT_REPO`. The Hub ids have no default: they
come from ``--hf-dataset`` and ``--hf-space`` or ``$ADLC_ADOPTION_HF_DATASET`` and
``$ADLC_ADOPTION_HF_SPACE``, and a Hub source with no id is ``not-configured``. Every id
must match :data:`ID_RE` and is refused before any call when it does not.

Each source ends in exactly one class of :data:`CLASSES`, recorded under ``sources``. A
source that is not ``ok`` leaves every one of its fields ``null``: no code path writes
``0`` for a value it did not read (BR-7). ``unclassified`` is the classifier's default
(LESSON-581): an error text it was not taught gets no diagnosis it did not establish.
``not-configured`` and ``no-source`` are not failures.

The target is ``--out``, else ``$ADLC_ADOPTION_SNAPSHOT_FILE``, else
``<ADLC_HOME>/adlc/adoption-snapshots.jsonl`` resolved through ``tools/adlc/adlc_home.py``.
A target that is a symlink or is not a regular file is refused, and so is one inside any
git working tree: a folder above it, resolved, is this toolkit (matched by device and
inode) or holds a ``.git``, because no row is committed. A missing parent is created
``0700`` and the file ``0600``, opened ``O_APPEND | O_NOFOLLOW | O_NONBLOCK``
(LESSON-014) and checked with ``fstat`` to be a regular file; an existing file looser than
``0600`` is brought to ``0600``, with a note. The target is checked and opened before any
platform is read, so a refused run makes no call. A refusal names the target as it was
given: the ``--out`` or ``$ADLC_ADOPTION_SNAPSHOT_FILE`` value, or
:data:`DEFAULT_SHOWN` for the default, and never a path it resolved.

The row is one ``os.write``, under an exclusive ``flock`` on the open file taken before its
size is read and held across the write and any rollback, so writers are serialized. A short
or failed write is truncated back off to that size, so a run appends a whole line or
nothing. Where no lock can be taken (no ``fcntl``, or ``flock`` fails), nothing is
truncated, since that could cut another writer's row away: a short or failed write exits
2 and says a partial row may have been left.

Auth is the maintainer's own. ``gh`` inherits its login, or ``GH_TOKEN``, from the
environment, and a Hub read sends ``HF_TOKEN`` as a bearer header only when it is set. No
token is written to the row or printed: a backend's error text has the value of every
token variable this process holds, and then every credential shape
``credential_redact`` knows, replaced before a short reason is printed. Class and field
names are fixed identifiers and never pass through redaction (LESSON-744).

Output: ``adoption_snapshot_recorded file=<path>`` on stdout, and one
``adoption_snapshot_failed source=<name> class=<class> [reason="..."]`` line on stderr
per failed source. Every other diagnostic line starts with :data:`PREFIX`. Exit 0 when
every configured source is ``ok``; 1 when any failed, the row still appended; 2 on a
usage error or a refused or unwritable target, nothing appended. ``--dry-run`` checks the
target, prints the row to stdout and appends nothing.

Every subprocess and request has a timeout, and a timeout is ``network``. No sleep, no
retry. Python 3.9, standard library only, plus ``adlc_home`` and ``credential_redact``
from ``tools/adlc``.
"""

import argparse
import collections
import datetime
import http.client
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import fcntl
except ImportError:  # not on every platform: then no lock, and no rollback by truncation
    fcntl = None

HERE =os.path.dirname(os.path.realpath(__file__))
#: The toolkit working tree this file lives in. No target may lie inside it.
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
_ADLC_TOOLS = os.path.join(TOOLKIT, "tools", "adlc")
if _ADLC_TOOLS not in sys.path:
    # Appended, not put first: a same-named module earlier on the path stays the one found.
    sys.path.append(_ADLC_TOOLS)

import adlc_home  # noqa: E402
import credential_redact  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2

DEFAULT_REPO = "atelier-fashion/adlc-toolkit"
HUB_API = "https://huggingface.co/api/"
USER_AGENT = "adlc-adoption-snapshot"

ENV_FILE = "ADLC_ADOPTION_SNAPSHOT_FILE"
ENV_HF_DATASET = "ADLC_ADOPTION_HF_DATASET"
ENV_HF_SPACE = "ADLC_ADOPTION_HF_SPACE"
#: The default target, under the machine-state home.
DEFAULT_FILE = ("adlc", "adoption-snapshots.jsonl")
#: How a refusal names the default target: as the help spells it, not resolved.
DEFAULT_SHOWN = "<ADLC_HOME>/" + "/".join(DEFAULT_FILE)
#: The target's mode: created with it, and an existing looser file is brought to it.
FILE_MODE = 0o600
#: The one prefix of every diagnostic line that is not one of the two event lines.
PREFIX = "adoption-snapshot:"

GH_TIMEOUT = 30
HUB_TIMEOUT = 20
#: A Hub answer longer than this is not the small JSON object the API returns.
HUB_MAX_BYTES = 8 * 1024 * 1024
REASON_MAX = 160

#: ``OWNER/NAME`` for the repo and both Hub ids; :func:`valid_id` also refuses a part
#: made only of dots.
ID_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# --- the closed class set (ADR-7) ---------------------------------------------------

OK = "ok"
AUTH_MISSING = "auth-missing"
FORBIDDEN = "forbidden"
NOT_FOUND = "not-found"
RATE_LIMITED = "rate-limited"
NETWORK = "network"
TOOL_MISSING = "tool-missing"
BAD_RESPONSE = "bad-response"
NOT_CONFIGURED = "not-configured"
NO_SOURCE = "no-source"
UNCLASSIFIED = "unclassified"
CLASSES = (OK, AUTH_MISSING, FORBIDDEN, NOT_FOUND, RATE_LIMITED, NETWORK, TOOL_MISSING,
           BAD_RESPONSE, NOT_CONFIGURED, NO_SOURCE, UNCLASSIFIED)
#: The classes that are not a failure. Every other class makes the exit status 1.
NOT_FAILURES = (OK, NOT_CONFIGURED, NO_SOURCE)

#: Class and field names are fixed identifiers, checked by format and never redacted.
CLASS_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
FIELD_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

#: Each source and the row fields it fills, in row order.
SOURCE_FIELDS = (
    ("github", ("github_stars", "github_forks")),
    ("github_traffic", ("github_views_14d", "github_clones_14d", "top_referrers")),
    ("hf_dataset", ("hf_dataset_downloads",)),
    ("hf_space", ("hf_space_likes",)),
    ("hf_space_runs", ("hf_space_runs",)),
)

#: ``gh`` stderr, first match wins. Rate limiting comes before forbidden because GitHub
#: answers it with HTTP 403. Nothing here is a default: an untaught text is
#: ``unclassified`` (LESSON-581).
GH_RULES = (
    (re.compile(r"gh auth login|not logged in|\bHTTP 401\b|Bad credentials"
                r"|Requires authentication", re.I), AUTH_MISSING),
    (re.compile(r"rate limit|\bHTTP 429\b", re.I), RATE_LIMITED),
    (re.compile(r"\bHTTP 403\b|Must have push access|Resource not accessible", re.I),
     FORBIDDEN),
    (re.compile(r"\bHTTP 404\b|\bNot Found\b|Could not resolve to a ", re.I), NOT_FOUND),
    (re.compile(r"could not resolve host|error connecting to|no such host"
                r"|connection refused|connection reset|network is unreachable"
                r"|i/o timeout|TLS handshake timeout", re.I), NETWORK),
)
#: ``gh help exit-codes``: 4 is "the command requires authentication".
GH_EXIT_AUTH = 4

#: The Hub's ``X-Error-Code`` header, read before the status: the Hub answers a repo that
#: does not exist, or is private, with 401 and ``RepoNotFound``.
HUB_ERROR_CODES = {"RepoNotFound": NOT_FOUND}
#: Hub HTTP statuses. A 5xx is not here: it says nothing about the cause, so it is
#: ``unclassified``.
HUB_STATUSES = {401: AUTH_MISSING, 403: FORBIDDEN, 404: NOT_FOUND, 429: RATE_LIMITED}

#: Token variables whose value is removed from any backend text before it is printed.
SECRET_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
              "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
#: A shorter value is not replaced literally: it would match inside ordinary words.
SECRET_MIN = 8

#: One source's result: its class, its field values (only when ``ok``) and a short reason.
Outcome = collections.namedtuple("Outcome", "cls values reason")


class Refused(Exception):
    """The target cannot be used (exit 2, nothing appended)."""

    def __init__(self, path, reason):
        super().__init__(reason)
        self.path, self.reason = path, reason

    def line(self):
        return "%s refused file=%s reason=%s" % (PREFIX, self.path, json.dumps(self.reason))


class _BadResponse(Exception):
    """A platform answered, but not with the shape this file reads."""


# --- classify ------------------------------------------------------------------------

def classify_gh(stderr, returncode=None):
    """The class of a failed ``gh api`` call, from its stderr, then its exit code."""
    for pattern, cls in GH_RULES:
        if pattern.search(stderr or ""):
            return cls
    if returncode == GH_EXIT_AUTH:
        return AUTH_MISSING
    return UNCLASSIFIED


def classify_hub_status(status, error_code=None):
    """The class of a Hub HTTP error, from ``X-Error-Code``, then the status."""
    if error_code in HUB_ERROR_CODES:
        return HUB_ERROR_CODES[error_code]
    return HUB_STATUSES.get(status, UNCLASSIFIED)


def short_reason(text):
    """``text`` with every token value and credential shape replaced, on one short line."""
    for name in SECRET_ENV:
        value = os.environ.get(name, "")
        if len(value) >= SECRET_MIN:
            text = text.replace(value, credential_redact.REPLACEMENT)
    text, _ = credential_redact.redact(text, credential_redact.ALL_PATTERNS)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines)[:REASON_MAX]


# --- fetch ---------------------------------------------------------------------------

def gh_read(gh, path):
    """One ``gh api <path>`` read: ``(class, parsed JSON or None, reason)``."""
    if gh is None:
        return TOOL_MISSING, None, "gh is not on PATH"
    env = dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    try:
        proc = subprocess.run([gh, "api", path], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=GH_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return NETWORK, None, "gh api timed out after %s s" % GH_TIMEOUT
    except FileNotFoundError:
        return TOOL_MISSING, None, "gh could not be run"
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace")
        return classify_gh(stderr, proc.returncode), None, short_reason(stderr)
    try:
        return OK, json.loads(proc.stdout.decode("utf-8", "replace")), ""
    except ValueError:
        return BAD_RESPONSE, None, "gh api answered with a body that is not JSON"


def default_opener(request, timeout):
    """The real Hub opener. Tests hand ``main`` a stub instead."""
    return urllib.request.urlopen(request, timeout=timeout)


def hub_read(opener, kind, hub_id):
    """One GET of ``<HUB_API><kind>/<hub_id>``: ``(class, parsed JSON or None, reason)``."""
    request = urllib.request.Request(HUB_API + kind + "/" + hub_id, method="GET",
                                     headers={"Accept": "application/json",
                                              "User-Agent": USER_AGENT})
    token = os.environ.get("HF_TOKEN")
    if token:
        # Unredirected: a redirect to another host does not carry the token.
        request.add_unredirected_header("Authorization", "Bearer " + token)
    try:
        response = opener(request, timeout=HUB_TIMEOUT)
        try:
            raw = response.read(HUB_MAX_BYTES + 1)
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        headers = exc.headers
        code = headers.get("X-Error-Code") if headers is not None else None
        return classify_hub_status(exc.code, code), None, "HTTP %d" % exc.code
    except (socket.timeout, ConnectionError, urllib.error.URLError) as exc:
        return NETWORK, None, short_reason(str(getattr(exc, "reason", exc)))
    except http.client.HTTPException as exc:
        return BAD_RESPONSE, None, type(exc).__name__
    if len(raw) > HUB_MAX_BYTES:
        return BAD_RESPONSE, None, "the Hub answer is larger than %d bytes" % HUB_MAX_BYTES
    try:
        return OK, json.loads(raw.decode("utf-8")), ""
    except ValueError:
        return BAD_RESPONSE, None, "the Hub answered with a body that is not JSON"


# --- read each source ----------------------------------------------------------------

def _count(body, key):
    """``body[key]`` when it is a non-negative integer, else :class:`_BadResponse`."""
    value = body.get(key) if isinstance(body, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _BadResponse("the answer has no non-negative integer %s" % key)
    return value


def _referrers(body):
    """GitHub's referrer list, each entry cut to referrer, count and uniques."""
    if not isinstance(body, list):
        raise _BadResponse("the referrers answer is not a list")
    cut = []
    for entry in body:
        if not isinstance(entry, dict) or not isinstance(entry.get("referrer"), str):
            raise _BadResponse("a referrer entry has no referrer")
        cut.append({"referrer": entry["referrer"], "count": _count(entry, "count"),
                    "uniques": _count(entry, "uniques")})
    return cut


#: The three traffic reads, the field each fills and how it is read.
TRAFFIC_READS = (
    ("traffic/views", "github_views_14d", lambda body: _count(body, "count")),
    ("traffic/clones", "github_clones_14d", lambda body: _count(body, "count")),
    ("traffic/popular/referrers", "top_referrers", _referrers),
)


def read_github(gh, repo):
    cls, body, reason = gh_read(gh, "repos/%s" % repo)
    if cls != OK:
        return Outcome(cls, {}, reason)
    try:
        return Outcome(OK, {"github_stars": _count(body, "stargazers_count"),
                            "github_forks": _count(body, "forks_count")}, "")
    except _BadResponse as exc:
        return Outcome(BAD_RESPONSE, {}, str(exc))


def read_github_traffic(gh, repo):
    """All three traffic reads, or the first failure's class and no value at all."""
    values = {}
    for suffix, field, parse in TRAFFIC_READS:
        cls, body, reason = gh_read(gh, "repos/%s/%s" % (repo, suffix))
        if cls != OK:
            return Outcome(cls, {}, reason)
        try:
            values[field] = parse(body)
        except _BadResponse as exc:
            return Outcome(BAD_RESPONSE, {}, str(exc))
    return Outcome(OK, values, "")


def _read_hub(opener, kind, hub_id, field, key):
    if hub_id is None:
        return Outcome(NOT_CONFIGURED, {}, "")
    cls, body, reason = hub_read(opener, kind, hub_id)
    if cls != OK:
        return Outcome(cls, {}, reason)
    try:
        return Outcome(OK, {field: _count(body, key)}, "")
    except _BadResponse as exc:
        return Outcome(BAD_RESPONSE, {}, str(exc))


def read_hf_dataset(opener, hub_id):
    return _read_hub(opener, "datasets", hub_id, "hf_dataset_downloads", "downloads")


def read_hf_space(opener, hub_id):
    return _read_hub(opener, "spaces", hub_id, "hf_space_likes", "likes")


def read_hf_space_runs():
    """No read: REQ-670 ADR-7 gives the Space no content-free run counter."""
    return Outcome(NO_SOURCE, {}, "")


def collect(repo, hf_dataset, hf_space, opener):
    """Every source's :class:`Outcome`, keyed by source name, in row order."""
    gh = shutil.which("gh")
    reads = {
        "github": lambda: read_github(gh, repo),
        "github_traffic": lambda: read_github_traffic(gh, repo),
        "hf_dataset": lambda: read_hf_dataset(opener, hf_dataset),
        "hf_space": lambda: read_hf_space(opener, hf_space),
        "hf_space_runs": read_hf_space_runs,
    }
    outcomes = collections.OrderedDict()
    for source, _ in SOURCE_FIELDS:
        try:
            outcomes[source] = reads[source]()
        except Exception as exc:  # one source's surprise must not lose the others' row
            outcomes[source] = Outcome(UNCLASSIFIED, {}, type(exc).__name__)
    return outcomes


# --- build the row -------------------------------------------------------------------

def build_row(outcomes, repo, now):
    """The AdoptionSnapshot row. A field is its read value only when its source is ``ok``."""
    now = now.astimezone(datetime.timezone.utc)
    row = {"date": now.strftime("%Y-%m-%d"),
           "recorded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "repo": repo}
    sources = {}
    for source, fields in SOURCE_FIELDS:
        outcome = outcomes[source]
        if outcome.cls not in CLASSES or not CLASS_RE.match(outcome.cls):
            raise ValueError("source %s ended in an unknown class" % source)
        for field in fields:
            row[field] = outcome.values[field] if outcome.cls == OK else None
        sources[source] = outcome.cls
    row["sources"] = sources
    return row


def failed_lines(outcomes):
    """One ``adoption_snapshot_failed`` line per source whose class is a failure."""
    lines = []
    for source, outcome in outcomes.items():
        if outcome.cls in NOT_FAILURES:
            continue
        line = "adoption_snapshot_failed source=%s class=%s" % (source, outcome.cls)
        if outcome.reason:
            line += " reason=%s" % json.dumps(outcome.reason)
        lines.append(line)
    return lines


# --- write ---------------------------------------------------------------------------

def resolve_target(out):
    """``(path, shown)``: ``--out``, else ``$ADLC_ADOPTION_SNAPSHOT_FILE``, else the file
    under ADLC_HOME, made absolute; and how a refusal names it, as the user gave it."""
    chosen = out if out is not None else (os.environ.get(ENV_FILE) or None)
    if chosen is None:
        return os.path.join(adlc_home.adlc_home(), *DEFAULT_FILE), DEFAULT_SHOWN
    if not chosen:
        raise Refused("-", "the target path is empty")
    return os.path.abspath(chosen), chosen


def _committable(path):
    """Why a file at ``path`` could be committed, or ``None``.

    Walks from the nearest folder of ``path`` that exists, resolved, up to the root. The
    toolkit is matched by device and inode, not by spelling, which a case-insensitive
    filesystem lets vary; and any folder holding a ``.git`` file or folder is a work tree,
    whether it is this toolkit, its parent checkout or another clone.
    """
    folder = os.path.dirname(path)
    while not os.path.isdir(folder) and os.path.dirname(folder) != folder:
        folder = os.path.dirname(folder)
    folder = os.path.realpath(folder)
    while True:
        if os.path.samefile(folder, TOOLKIT):
            return "the target is inside the toolkit's working tree"
        if os.path.lexists(os.path.join(folder, ".git")):
            return "the target is inside a git working tree"
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def check_target(path):
    """:class:`Refused` when ``path`` is a symlink, not a regular file, or in a work tree."""
    if os.path.islink(path):
        raise Refused(path, "the target is a symlink")
    if os.path.lexists(path) and not os.path.isfile(path):
        raise Refused(path, "the target is not a regular file")
    why = _committable(path)
    if why:
        raise Refused(path, why + ", and no snapshot row is committed")


def _make_parents(directory):
    """Create each missing directory down to ``directory``, ``0700``."""
    missing = []
    while not os.path.isdir(directory):
        missing.append(directory)
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    for path in reversed(missing):
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            if not os.path.isdir(path):
                raise


def open_target(path):
    """An append-only descriptor on a regular file at ``path``, created ``0600``.

    Never through a symlink, and ``O_NONBLOCK`` so a FIFO swapped in after
    :func:`check_target` fails the open instead of hanging it.
    """
    try:
        _make_parents(os.path.dirname(path))
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                     | os.O_NONBLOCK, FILE_MODE)
    except OSError as exc:
        raise Refused(path, "the target cannot be opened: %s" % (exc.strerror or "error"))
    try:
        _check_opened(path, fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _check_opened(path, fd):
    """Refuse what ``fd`` opened unless it is a regular file; tighten a looser mode."""
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise Refused(path, "the target is not a regular file")
    mode = stat.S_IMODE(info.st_mode)
    if mode & ~FILE_MODE:
        try:
            os.fchmod(fd, FILE_MODE)
        except OSError as exc:
            raise Refused(path, "the target is mode %04o and cannot be made %04o: %s"
                          % (mode, FILE_MODE, exc.strerror or "error"))
        _err("%s tightened %s from %04o to %04o" % (PREFIX, path, mode, FILE_MODE))


def prepare_target(out, dry_run):
    """``(path, shown, descriptor)``, the descriptor ``None`` on a dry run, or
    :class:`Refused` naming the target as ``shown``, the user's spelling.

    Checked and opened before any platform is read, so a refused run makes no call.
    """
    path, shown = resolve_target(out)
    try:
        check_target(path)
        fd = None if dry_run else open_target(path)
    except Refused as exc:
        raise Refused(shown, exc.reason) from None
    return path, shown, fd


def _lock(fd):
    """True once an exclusive ``flock`` on ``fd`` is held; False when there is no
    ``fcntl`` or the lock cannot be taken."""
    if fcntl is None:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        return False
    return True


def _unlock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass  # closing the descriptor releases it too


def append_line(shown, fd, line):
    """Write the whole row in one ``os.write``, or leave the file as it was.

    The exclusive lock is taken before the size is read and held across the write and
    any rollback, so no other writer's row can land in between and be truncated away.
    Without the lock nothing is truncated, and a row not written whole says so.
    """
    data = line.encode("utf-8")
    locked = _lock(fd)
    try:
        size = None
        if locked:
            try:
                size = os.fstat(fd).st_size
            except OSError as exc:
                raise Refused(shown, "the target cannot be read: %s"
                              % (exc.strerror or "error"))
        try:
            written = os.write(fd, data)
        except OSError as exc:
            _not_whole(shown, fd, size, "the row could not be written (%s)"
                       % (exc.strerror or "error"))
        if written != len(data):
            _not_whole(shown, fd, size, "the row was cut short at %d of %d bytes"
                       % (written, len(data)))
    finally:
        if locked:
            _unlock(fd)


def _not_whole(shown, fd, size, what):
    """:class:`Refused` for a row not written whole: cut back to ``size`` under the lock,
    or, with no lock (``size`` None), left where it is and said."""
    if size is None:
        raise Refused(shown, "%s, and with no lock on the file it was not cut back: a "
                             "partial row may have been left in %s" % (what, shown))
    _cut_back(shown, fd, size)
    raise Refused(shown, "%s; nothing was appended" % what)


def _cut_back(shown, fd, size):
    """Truncate a partly written row away, back to the ``size`` the file had before it."""
    try:
        os.ftruncate(fd, size)
    except OSError as exc:
        raise Refused(shown, "the row was cut short and the part written could not be "
                             "removed: %s" % (exc.strerror or "error"))


# --- CLI -----------------------------------------------------------------------------

def valid_id(value):
    """True for ``OWNER/NAME`` of :data:`ID_RE` whose parts are not only dots."""
    if not ID_RE.match(value):
        return False
    return all(part.strip(".") for part in value.split("/"))


class _Parser(argparse.ArgumentParser):
    """argparse, with a usage error on one prefixed line instead of its own shape."""

    def error(self, message):
        _err("%s %s (see --help)" % (PREFIX, message))
        raise SystemExit(EXIT_USAGE)


def _parser():
    parser = _Parser(
        prog="adoption_snapshot.py",
        description="Append one AdoptionSnapshot row (REQ-672 ADR-7). Read-only toward "
                    "GitHub and the Hugging Face Hub.")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="GitHub repo, OWNER/NAME (default: %(default)s)")
    parser.add_argument("--hf-dataset", default=None,
                        help="Hub dataset id, OWNER/NAME (or $%s)" % ENV_HF_DATASET)
    parser.add_argument("--hf-space", default=None,
                        help="Hub Space id, OWNER/NAME (or $%s)" % ENV_HF_SPACE)
    parser.add_argument("--out", default=None,
                        help="the file to append to (or $%s; default "
                             "<ADLC_HOME>/adlc/adoption-snapshots.jsonl)" % ENV_FILE)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the row and append nothing")
    return parser


def _ids(args):
    """``(label, value)`` for every id to check; a Hub id comes from its flag or env."""
    ids = [("--repo", args.repo)]
    for flag, value, env in (("--hf-dataset", args.hf_dataset, ENV_HF_DATASET),
                             ("--hf-space", args.hf_space, ENV_HF_SPACE)):
        if value is not None:
            ids.append((flag, value))
        elif os.environ.get(env):
            ids.append((env, os.environ[env]))
        else:
            ids.append((flag, None))
    return ids


def _err(line):
    print(line, file=sys.stderr)


def main(argv=None, *, opener=None, now=None):
    """The command. ``opener`` stands in for ``urllib.request.urlopen`` and ``now`` for
    the clock, so a test reaches no platform and pins the date."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    ids = _ids(args)
    for label, value in ids:
        if value is not None and not valid_id(value):
            _err("%s %s must be OWNER/NAME of letters, digits, '_', '.' and '-'"
                 % (PREFIX, label))
            return EXIT_USAGE
    repo, hf_dataset, hf_space = (value for _, value in ids)

    try:
        target, shown, fd = prepare_target(args.out, args.dry_run)
    except adlc_home.AdlcHomeError as exc:
        _err("%s %s" % (PREFIX, exc))
        return EXIT_USAGE
    except Refused as exc:
        _err(exc.line())
        return EXIT_USAGE

    try:
        outcomes = collect(repo, hf_dataset, hf_space,
                           opener if opener is not None else default_opener)
        row = build_row(outcomes, repo, now or datetime.datetime.now(datetime.timezone.utc))
        line = json.dumps(row) + "\n"
        if args.dry_run:
            sys.stdout.write(line)
        else:
            append_line(shown, fd, line)
    except Refused as exc:
        _err(exc.line())
        return EXIT_USAGE
    finally:
        if fd is not None:
            os.close(fd)

    if not args.dry_run:
        print("adoption_snapshot_recorded file=%s" % target)
    failures = failed_lines(outcomes)
    for failure in failures:
        _err(failure)
    return EXIT_FAILED if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
