#!/usr/bin/env python3
"""Regenerate the demo recording from a real quickstart run (REQ-672 BR-4, architecture ADR-6).

    python3 tools/launch/record_demo.py --with-model --throwaway-repo OWNER/NAME [options]

A run records ``quickstart_e2e.py --demo --with-model --throwaway-repo OWNER/NAME`` with
``asciinema rec``: real Claude Code sessions in the driver's sandbox ``HOME``, pushing to
the throwaway repository. It spends the maintainer's Claude plan, so it is made at their
word; no output is canned. When the driver passes, the cast is

1. post-processed (:func:`postprocess`): each idle gap capped at 2 seconds, the times then
   scaled by one factor when they still run over 60 seconds, the header cut to what a
   player needs (the recorded command line and title are dropped), and the throwaway
   repo's owner replaced by ``your-github-user``, the one substitution;
2. checked by ``recording_check.py``, forbidding as a whole word (the owner's matcher) the
   signed-in GitHub login, read with ``gh api user``, held in memory only, never written;
3. rendered by ``agg``, and the GIF's size checked;
4. and only then moved into ``--out-dir`` (default ``docs/``) as ``demo.cast`` and
   ``demo.gif``, both or neither.

Nothing is recorded, and the exit is 2 with the reason, when ``asciinema``, ``agg`` or
``gh`` is not on ``PATH``, without ``--with-model``, without a valid ``--throwaway-repo``
(the driver's rule: OWNER/NAME, the name containing ``e2e``), without the credentials the
driver needs, when the login cannot be read, when ``asciinema --version`` names no version,
when the login or the repo's owner is a whole word of the quickstart's steps (the recording
shows them, so it could never pass), or when ``--keep-raw`` is refused. A run whose driver
does not pass, or whose recording fails a check, writes nothing and exits 1. Exit 0 prints
one summary line. Every diagnostic line starts ``record-demo:``. Python 3.9, stdlib only.

``--keep-raw PATH`` keeps the unprocessed cast, which holds the login and absolute paths:
created new with mode 0600, never through a symlink, and never inside a git work tree.

asciinema 3 writes asciicast v3 unless told otherwise. This relies on two facts: ``asciinema
--version`` prints ``asciinema <major>.<minor>...`` in 2.x and 3.x, and 3.x's ``rec`` takes
``--output-format asciicast-v2``. Major 3 or later gets that flag, 2.x (v2 only) none. No
real asciinema has run against this code: the tests' fake prints both versions, and
``recording_check.load_cast`` also reads a v3 cast, should one be written anyway.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
for _path in [HERE] + [os.path.join(TOOLKIT, "tools", name) for name in ("adlc", "dataset")]:
    if _path not in sys.path:
        sys.path.append(_path)

import quickstart_e2e as qe  # noqa: E402
import quickstart_steps as qs  # noqa: E402
import recording_check as rc  # noqa: E402

DRIVER = os.path.join(HERE, "quickstart_e2e.py")
DEFAULT_OUT_DIR = os.path.join(TOOLKIT, "docs")
PLACEHOLDER_OWNER = "your-github-user"
IDLE_CAP = 2.0
#: A scaled cast ends this far under the limit, never on it.
MARGIN = 2.0
#: The header fields a player needs; ``env`` keeps ``TERM`` only.
HEADER_KEYS = ("version", "width", "height", "timestamp", "theme")
#: Where the recorded command writes the driver's exit status.
STATUS_VAR = "ADLC_RECORD_DEMO_STATUS"
TEMP_PREFIX = "adlc-record-demo."
EXIT_OK, EXIT_FAIL, EXIT_REFUSED = 0, 1, 2
#: What makes asciinema 3 or later write asciicast v2.
V2_FORMAT = ["--output-format", "asciicast-v2"]

_LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_VERSION_RE = re.compile(r"\basciinema\s+v?([0-9]+)\.[0-9]+", re.IGNORECASE)
#: ``owner`` as a whole word in any case: the matcher the ``forbidden`` check uses too.
owner_pattern = rc.word_pattern


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="record_demo.py", description=(
        "Record the quickstart e2e in --demo mode and write docs/demo.cast and docs/demo.gif."))
    add = parser.add_argument
    add("--with-model", action="store_true", help="opt in to paid model turns")
    add("--throwaway-repo", metavar="OWNER/NAME",
        help="an empty repository made for this run; NAME must contain e2e")
    add("--out-dir", metavar="DIR", default=DEFAULT_OUT_DIR, help="default docs/")
    add("--keep-raw", metavar="PATH", help="keep the unprocessed cast here (it holds your login)")
    add("--marketplace", metavar="PATH", help="passed to the driver: step 1's source")
    add("--model", metavar="NAME", help="passed to the driver: --model for every turn")
    return parser.parse_args(argv)


def driver_args(opts):
    """The driver's arguments: ``--demo`` and what ``opts`` passes through."""
    args = ["--demo"]
    if opts.with_model:
        args.append("--with-model")
    if opts.throwaway_repo:
        args += ["--throwaway-repo", opts.throwaway_repo]
    if opts.marketplace:
        args += ["--marketplace", os.path.abspath(opts.marketplace)]
    if opts.model:
        args += ["--model", opts.model]
    return args


def recorded_command(args):
    """The shell command ``asciinema rec`` runs: the driver, then its status to a file."""
    words = " ".join(shlex.quote(word) for word in [sys.executable, DRIVER] + args)
    return '%s; s=$?; echo "$s" > "$%s"; exit "$s"' % (words, STATUS_VAR)


def _which(name, path):
    return shutil.which(name, path=path) if path else None


def keep_raw_refusal(target):
    """Why ``--keep-raw`` may not be written, or None: it exists (as a symlink or not), its
    directory does not, or a ``.git`` entry sits in that directory or any above it."""
    path = os.path.abspath(target)
    if os.path.islink(path):
        return "--keep-raw %s is a symlink: the raw cast is never written through one" % target
    if os.path.lexists(path):
        return "--keep-raw %s exists: the raw cast is only written to a new file" % target
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        return "--keep-raw %s: its directory does not exist" % target
    for start in (folder, os.path.realpath(folder)):
        while True:
            if os.path.lexists(os.path.join(start, ".git")):
                return ("--keep-raw %s is inside a git work tree: the raw cast holds your "
                        "account name, so it is kept outside every repository" % target)
            if os.path.dirname(start) == start:
                break
            start = os.path.dirname(start)
    return None


def format_args(asciinema, environ):
    """The ``rec`` arguments that make ``asciinema`` write asciicast v2 (:data:`V2_FORMAT`
    for 3 or later, none for 2.x), or None when ``asciinema --version`` names no version."""
    try:
        done = subprocess.run([asciinema, "--version"], env=dict(environ),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                              timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION_RE.search(done.stdout) if done.returncode == 0 else None
    if match is None:
        return None
    return list(V2_FORMAT) if int(match.group(1)) >= 3 else []


def on_page(name, steps):
    """True when ``name`` is a whole word, in any case, of a quickstart step's text."""
    pattern = owner_pattern(name)
    return any(pattern.search(step.text) for step in steps)


def collision(whose, remedy=""):
    """The refusal for an account name the page holds; it never names the account."""
    return ("%s collides with the page's own text, which the recording shows: use a throwaway "
            "repo under an organisation or account whose name does not appear on the page%s"
            % (whose, remedy))


def preflight(opts, environ):
    """``(refusal, tools)``: why nothing may be recorded, or None and what a run needs: the
    tools' paths, ``rec``'s format arguments, the DenyList and the signed-in GitHub login
    (held in memory only: never printed, logged or written). Nothing here spends."""
    path = environ.get("PATH", "")
    tools = {}
    for name, job in (("asciinema", "records the run"), ("agg", "renders the GIF")):
        tools[name] = _which(name, path)
        if tools[name] is None:
            return "%s is not on PATH: it %s" % (name, job), None
    driver = qe.parse_args(driver_args(opts))
    if not opts.with_model or not opts.throwaway_repo:
        return qe.readiness(driver, environ), None
    why = qe.usage_refusal(driver) or qe.readiness(driver, environ)
    if not why and not os.path.isdir(opts.out_dir):
        why = "--out-dir %s is not a directory" % opts.out_dir
    if not why and opts.keep_raw:
        why = keep_raw_refusal(opts.keep_raw)
    if why:
        return why, None
    try:
        tools["denylist"] = rc.load_denylist()
    except rc.denylist_mod.DenyListError as exc:
        return "cannot read the DenyList the recording is checked against: %s" % exc, None
    try:
        steps = qs.load()
    except (OSError, UnicodeDecodeError, qs.QuickstartError) as exc:
        return "cannot read the quickstart page: %s" % exc, None
    if on_page(opts.throwaway_repo.split("/")[0], steps):
        return collision("the throwaway repo's owner"), None
    tools["gh"] = _which("gh", path)
    if tools["gh"] is None:
        return "gh is not on PATH: the recording is checked for your GitHub login", None
    tools["format"] = format_args(tools["asciinema"], environ)
    if tools["format"] is None:
        return ("cannot tell asciinema's version from asciinema --version, so not which cast "
                "format it writes (3.x writes v3 unless asked for v2)"), None
    tools["login"] = read_login(tools["gh"], environ)
    if tools["login"] is None:
        return ("cannot read your GitHub login with gh api user (is gh signed in?): the "
                "recording is checked for it, so nothing is recorded without it"), None
    if on_page(tools["login"], steps):
        return collision("your gh login", ", and sign gh in as such an account"), None
    return None, tools


def read_login(gh, environ):
    """The signed-in GitHub login, or None. Held in memory only: never printed or written."""
    try:
        done = subprocess.run([gh, "api", "user", "-q", ".login"], env=dict(environ),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, universal_newlines=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    login = done.stdout.strip()
    return login if done.returncode == 0 and _LOGIN_RE.match(login) else None


def replace_joined(datas, pattern, replacement):
    """Each of ``datas`` with every match of ``pattern`` in their concatenation replaced.

    Exact: the strings joined equal ``pattern.sub`` of the joined text. A match that spans
    strings is written whole into the string it starts in and taken out of the ones after;
    every other character stays in its own string.
    """
    joined = "".join(datas)
    spans = [match.span() for match in pattern.finditer(joined)]
    out, offset, k = [], 0, 0
    for data in datas:
        end = offset + len(data)
        piece, at = [], offset
        while at < end:
            while k < len(spans) and spans[k][1] <= at:
                k += 1
            if k < len(spans) and spans[k][0] <= at:
                if at == spans[k][0]:
                    piece.append(replacement)
                at = min(spans[k][1], end)
            else:
                stop = min(spans[k][0], end) if k < len(spans) else end
                piece.append(joined[at:stop])
                at = stop
        out.append("".join(piece))
        offset = end
    return out


def postprocess(header, events, *, max_seconds=rc.MAX_SECONDS, idle_cap=IDLE_CAP, owner=None):
    """``(header, events)`` ready to publish. Pure: the inputs are not changed.

    Each gap between events, the first included, is capped at ``idle_cap``; when the cast
    still runs over ``max_seconds`` every time is scaled by one factor so that it ends
    :data:`MARGIN` (at most a tenth of the limit) under it. Times stay in order. The
    header keeps :data:`HEADER_KEYS` and ``env``'s ``TERM``, with ``duration`` set to the
    new last time. ``owner``, a whole word in any case, becomes ``your-github-user``:
    across the joined output events (:func:`replace_joined`), and in each other event.
    """
    times, previous, clock = [], 0.0, 0.0
    for time, _, _ in events:
        clock += min(max(time - previous, 0.0), idle_cap)
        previous = time
        times.append(clock)
    total = times[-1] if times else 0.0
    if total > max_seconds:
        target = max_seconds - min(MARGIN, max_seconds / 10.0)
        times = [time * target / total for time in times]
    ordered, last = [], 0.0
    for time in times:
        last = max(last, round(time, 6))
        ordered.append(last)
    datas = [data for _, _, data in events]
    if owner:
        pattern = owner_pattern(owner)
        outputs = [i for i, event in enumerate(events) if event[1] == rc.OUTPUT]
        for i, data in zip(outputs, replace_joined([datas[i] for i in outputs], pattern,
                                                   PLACEHOLDER_OWNER)):
            datas[i] = data
        for i, event in enumerate(events):
            if event[1] != rc.OUTPUT:
                datas[i] = pattern.sub(lambda _match: PLACEHOLDER_OWNER, datas[i])
    kept = {key: header[key] for key in HEADER_KEYS if key in header}
    env = header.get("env")
    if isinstance(env, dict) and isinstance(env.get("TERM"), str):
        kept["env"] = {"TERM": env["TERM"]}
    kept["duration"] = ordered[-1] if ordered else 0.0
    return kept, [(time, event[1], data) for time, event, data in zip(ordered, events, datas)]


def write_cast(path, header, events):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(header) + "\n")
        for event in events:
            handle.write(json.dumps(list(event)) + "\n")


def driver_status(status_path):
    """The driver's exit status, from the file the recorded command writes after it. None
    when the file is missing or holds anything but a number: an unknown status is never
    read as a pass (LESSON-581)."""
    try:
        with open(status_path, encoding="utf-8") as handle:
            text = handle.read().strip()
    except OSError:
        return None
    return int(text) if re.match(r"^[0-9]{1,3}$", text) else None


def move_into_place(staged):
    """``os.replace`` each ``(staged, target)`` pair, all or none: when one fails, each
    target already moved gets its old content back, or is removed when it had none."""
    moved, backups = [], []
    try:
        for source, target in staged:
            backup = None
            if os.path.isfile(target):
                backup = source + ".old"
                shutil.copyfile(target, backup)
                backups.append(backup)
            os.replace(source, target)
            moved.append((target, backup))
    except OSError:
        for target, backup in reversed(moved):
            if backup is None:
                os.remove(target)
            else:
                os.replace(backup, target)
        raise
    finally:
        for backup in backups:
            if os.path.exists(backup):
                os.remove(backup)


def install(pairs, out_dir):
    """Copy each ``(source, name)`` beside its target in ``out_dir``, then move them all
    into place or none; the targets' paths."""
    staged = []
    try:
        for source, name in pairs:
            handle, temp = tempfile.mkstemp(prefix="." + name + ".", suffix=".tmp", dir=out_dir)
            os.close(handle)
            staged.append((temp, os.path.join(out_dir, name)))
            shutil.copyfile(source, temp)
        move_into_place(staged)
    finally:
        for temp, _ in staged:
            if os.path.exists(temp):
                os.remove(temp)
    return [target for _, target in staged]


def _report(failures, err):
    for failure in failures:
        err.write("record-demo: FAIL %s: %s\n" % failure)
    err.write("record-demo: the recording failed a check: nothing written\n")
    return EXIT_FAIL


def keep_raw(raw, target, err):
    """Copy ``raw`` to ``target``, created new with mode 0600 and never through a symlink."""
    try:
        handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(handle, "wb") as kept, open(raw, "rb") as source:
            shutil.copyfileobj(source, kept)
    except OSError as exc:
        err.write("record-demo: the unprocessed cast is not kept: %s\n" % exc)
        return
    err.write("record-demo: the unprocessed cast is kept at %s: it holds your GitHub account "
              "name and absolute paths, so it must not be committed or shared\n" % target)


def record(opts, tools, work, environ, out, err):
    """Record, post-process, check, render and install; the exit code."""
    raw, status = os.path.join(work, "raw.cast"), os.path.join(work, "status")
    login = tools["login"]
    env = dict(environ)
    env[STATUS_VAR] = status
    err.write("record-demo: recording the quickstart run with real model turns\n")
    err.flush()
    code = subprocess.call([tools["asciinema"], "rec", "--overwrite"] + tools["format"]
                           + ["--command", recorded_command(driver_args(opts)), raw], env=env)
    if opts.keep_raw and os.path.isfile(raw):
        keep_raw(raw, opts.keep_raw, err)
    driver = driver_status(status)
    if code != 0 or driver != 0:
        err.write("record-demo: the quickstart run did not pass (driver exit %s, asciinema "
                  "exit %d): nothing written\n" % ("unknown" if driver is None else driver, code))
        return EXIT_FAIL
    try:
        header, events = rc.load_cast(raw)
    except (OSError, rc.CastError) as exc:
        err.write("record-demo: cannot use the recording: %s: nothing written\n" % exc)
        return EXIT_FAIL
    header, events = postprocess(header, events, owner=opts.throwaway_repo.split("/")[0])
    cast, gif = os.path.join(work, rc.CAST_NAME), os.path.join(work, rc.GIF_NAME)
    write_cast(cast, header, events)
    failures = rc.check(cast, forbid=[login], denylist=tools["denylist"])
    if failures:
        return _report(failures, err)
    code = subprocess.call([tools["agg"], cast, gif], env=dict(environ),
                           stdin=subprocess.DEVNULL)
    if code != 0 or not os.path.isfile(gif):
        err.write("record-demo: agg exited %d without a GIF: nothing written\n" % code)
        return EXIT_FAIL
    failures = rc.check(cast, gif, forbid=[login], denylist=tools["denylist"])
    if failures:
        return _report(failures, err)
    written = install([(cast, rc.CAST_NAME), (gif, rc.GIF_NAME)], opts.out_dir)
    out.write("record-demo: wrote %s (%d bytes) and %s (%d bytes): %.2fs, %d events\n" % (
        written[0], os.path.getsize(written[0]), written[1], os.path.getsize(written[1]),
        rc.duration(events), len(events)))
    return EXIT_OK


def main(argv=None, environ=None, stdout=None, stderr=None):
    environ = os.environ if environ is None else environ
    out, err = stdout or sys.stdout, stderr or sys.stderr
    opts = parse_args(argv)
    refusal, tools = preflight(opts, environ)
    if refusal:
        err.write("record-demo: refused, nothing recorded: %s\n" % refusal)
        return EXIT_REFUSED
    work = tempfile.mkdtemp(prefix=TEMP_PREFIX)
    try:
        return record(opts, tools, work, environ, out, err)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _terminate(_signum, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
