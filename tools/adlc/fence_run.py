#!/usr/bin/env python3
"""fence_run — the one admitted entry point an exec model has to the toolkit's fences (REQ-682).

Usage:
  fence-run run <id> [--arg NAME=VALUE]... [--arg-file NAME=PATH]...
  fence-run show <toolkit-relative file>

``run`` runs one census fence whose route is ``runner``. It recomputes the census from its own
real path on every call (ADR-2), so an id whose fence changed, or whose route is ``direct``,
``engine`` or ``excised``, is refused, and nothing a working copy or the environment holds is
trusted. Each value is checked against its placeholder's full-match pattern and reaches the
fence only as an ``ADLC_ARG_*`` environment variable, expanded once inside double quotes
(ADR-3). The fence runs under ``/bin/sh`` in the current directory, with
``ADLC_TOOLKIT_ROOT`` the runner's own root and ``ADLC_FENCE_TOOLKIT_ONLY=1``, after
``adlc-home.sh`` and ``forge.sh`` are sourced from that root (ADR-4).

``show`` prints a file of the exec set with every fence replaced by its route's form, which is
how toolkit skills and agents reach an exec model: under BUG-260's isolation flags they are
not loaded (ADR-5).

Exit codes: a fence's own status is passed through. 3 is the runner's refusal, and every
refusal is exactly one stderr line, ``opaque_entry_refused: <id>: <reason>``, with nothing run
(BR-9). No refusal prints the fence's environment: it holds the run's scoped credential.

Standard library only.
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import toolkit_root as tkr  # noqa: E402

REFUSED = 3
#: A root a prefix rule can match unquoted: a quoted path does not match (probe row 6).
ROOT_RE = re.compile(r"^/[A-Za-z0-9_./-]+$")
_ID_RE = re.compile(r"^([A-Za-z0-9_./-]+)#([0-9]{1,4}):([0-9a-f]{8})$")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
MAX_ARG_FILE = 1 << 20
RUNNER_REL = "tools/adlc/fence-run"


class Refusal(Exception):
    """The runner will not run this; the message is the reason."""

    def __init__(self, subject, reason):
        Exception.__init__(self, reason)
        self.subject = subject
        self.reason = reason


def refuse(subject, reason, err=None):
    (err or sys.stderr).write("opaque_entry_refused: %s: %s\n" % (subject, reason))
    return REFUSED


def root_or_refuse():
    root = tkr.toolkit_root()
    if not ROOT_RE.match(root) or "/../" in root + "/" or "/./" in root + "/":
        raise Refusal("fence-run", "the toolkit root %r holds a character an unquoted prefix "
                                   "rule cannot match, so no allow can admit the runner" % root)
    return root


def runner_path(root):
    return "%s/%s" % (root, RUNNER_REL)


# --------------------------------------------------------------------------- show
_STUB_NOTE = ("Replace each `'<…>'` with its value as one single-quoted literal, every `'` "
              "in it written `'\\''`, or pass a file with `--arg-file NAME=PATH` (for a value "
              "that holds a quote or a newline). The runner checks each value and binds it as "
              "data.")


def runner_call(rec, root, placeholders):
    """The runner call that stands for a ``runner`` fence, with a stub per value."""
    parts = [runner_path(root), "run", rec["id"]]
    for ph in placeholders:
        if ph.file:
            parts.append("--arg-file %s='<a file holding %s>'" % (ph.arg, ph.key))
        else:
            parts.append("--arg %s='<%s>'" % (ph.arg, ph.key))
    return " ".join(parts)


def _placeholders_for(fence):
    found, _sources = fc.plan(fence.code)
    out = []
    for ph in found:
        if ph.arg not in [p.arg for p in out]:
            out.append(ph)
    return out


def rewrite_text(text, rel, records, root):
    """``text`` (the view of ``rel``) with every fence replaced by its route's form (ADR-5).

    Raises :class:`fc.CensusError` naming the first unrouted fence."""
    by_id = {r["id"]: r for r in records}
    lines = text.split("\n")
    out = []
    pos = 0
    for fence in fc.fences(text, rel):
        rec = by_id.get(fence.id)
        if rec is None or rec["route"] == "unrouted":
            why = rec["reason"] if rec else "not in the census"
            raise fc.CensusError("%s is unrouted: %s" % (fence.id, why))
        out += lines[pos:fence.start]
        pos = fence.end + 1
        ind = fence.indent
        route = rec["route"]
        if route == "direct":
            out += lines[fence.start:fence.end + 1]
        elif route == "runner":
            phs = _placeholders_for(fence)
            out += [ind + "```sh", ind + runner_call(rec, root, phs), ind + "```"]
            if phs:
                out.append(ind + _STUB_NOTE)
            multi = [ph.arg for ph in phs if ph.multi]
            if multi:
                out.append(ind + "Give `--arg %s=…` once per value." % multi[0])
        elif route == "engine":
            out.append(ind + "(Under --exec you do not run fence `%s`: %s.)"
                       % (fence.id, rec["reason"]))
        else:
            out.append(ind + "(Under --exec fence `%s` does not run: %s.)"
                       % (fence.id, rec["reason"]))
    out += lines[pos:]
    return "\n".join(out)


def show(rel, root, out=None, err=None):
    out = out or sys.stdout
    if rel not in fc.EXEC_FILES:
        return refuse("show %s" % rel, "not in the exec file set (fence_census.EXEC_FILES)", err)
    try:
        records = fc.census(root)
        text = rewrite_text(fc.view(root, rel), rel, records, root)
        # The one `!` line a skill keeps is ETHOS, already at the top of the prompt.
        text = ep._render_bang_lines(text, rel)
    except (fc.CensusError, ep.PromptBuildError) as exc:
        return refuse("show %s" % rel, str(exc), err)
    hits = ep.scan(text, "close-out" if rel == fc.CLOSEOUT_FILE else "pipeline")
    hits = [h for h in hits if h[0] in ep.EMPTY_ALLOWLIST]
    if hits:
        return refuse("show %s" % rel, "holds %r at line %d" % (hits[0][0], hits[0][1]), err)
    out.write(text if text.endswith("\n") else text + "\n")
    return 0


# --------------------------------------------------------------------------- run
def parse_values(argv, placeholders, cwd):
    """``{arg: [values]}`` from ``--arg``/``--arg-file`` pairs, every value checked."""
    by_arg = {ph.arg: ph for ph in placeholders}
    values = {}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag not in ("--arg", "--arg-file") or i + 1 >= len(argv):
            raise Refusal(None, "expected --arg NAME=VALUE or --arg-file NAME=PATH, got %r"
                                % flag[:60])
        name, sep, value = argv[i + 1].partition("=")
        i += 2
        if not sep or not _NAME_RE.match(name):
            raise Refusal(None, "%r is not NAME=VALUE" % argv[i - 1][:60])
        ph = by_arg.get(name)
        if ph is None:
            raise Refusal(None, "%s is not a value this fence takes (it takes: %s)"
                                % (name, ", ".join(sorted(by_arg)) or "none"))
        if flag == "--arg-file":
            value = read_arg_file(value, cwd)
        elif ph.file:
            raise Refusal(None, "%s takes --arg-file, not --arg" % name)
        why = ph.check(value) or ph.check_scope(value, cwd)
        if why:
            raise Refusal(None, "value for %s %s" % (name, why))
        if name in values and not ph.multi:
            raise Refusal(None, "%s is given twice and takes one value" % name)
        values.setdefault(name, []).append(value)
    for ph in placeholders:
        if ph.arg not in values:
            if ph.multi or ph.empty_ok:
                values[ph.arg] = [] if ph.multi else [""]
            else:
                raise Refusal(None, "no value for %s" % ph.arg)
    return values


def read_arg_file(path, cwd):
    """A file the model wrote: a regular file under the working directory, at most 1 MiB."""
    if not path or "\x00" in path:
        raise Refusal(None, "--arg-file names no path")
    real = os.path.realpath(os.path.join(cwd, path))
    base = os.path.realpath(cwd)
    if os.path.commonpath([real, base]) != base:
        raise Refusal(None, "--arg-file %r resolves outside the working directory" % path[:120])
    if not os.path.isfile(real):
        raise Refusal(None, "--arg-file %r is not a regular file" % path[:120])
    size = os.path.getsize(real)
    if size > MAX_ARG_FILE:
        raise Refusal(None, "--arg-file %r is %d bytes, over the 1 MiB cap" % (path[:120], size))
    with open(real, "rb") as fh:
        data = fh.read(MAX_ARG_FILE + 1)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal(None, "--arg-file %r is not UTF-8 text" % path[:120])


def child_env(environ, placeholders, values, root):
    """The fence's environment: the inherited one, with every caller ``ADLC_ARG_*`` and the
    toolkit-only flag dropped, then the bound values, the root, and the flag, set last."""
    env = {k: v for k, v in environ.items()
           if not k.startswith("ADLC_ARG_") and k != "ADLC_FENCE_TOOLKIT_ONLY"}
    for ph in placeholders:
        vals = values.get(ph.arg, [])
        if ph.multi:
            for k, v in enumerate(vals):
                env[fc._env_name(ph.arg, k)] = v
        else:
            env[fc._env_name(ph.arg)] = vals[0] if vals else ""
    env["ADLC_TOOLKIT_ROOT"] = root
    env["ADLC_FENCE_TOOLKIT_ONLY"] = "1"
    return env


def script_for(fence, values, root):
    """The preload closure, by absolute path, then the transformed fence (ADR-4)."""
    preload = '. "%s/partials/adlc-home.sh"\n. "%s/partials/forge.sh"\n' % (root, root)
    return preload + fc.transform(fence.code, values, root)


def find(fid, root):
    """``(fence, record)`` for ``fid``, or :class:`Refusal` naming why not."""
    match = _ID_RE.match(fid or "")
    if not match:
        raise Refusal(fid, "not a fence id (<path>#<ordinal>:<sha8>)")
    rel = match.group(1)
    if rel not in fc.EXEC_FILES:
        raise Refusal(fid, "%s is not in the exec file set" % rel)
    try:
        records = fc.census(root)
        fences = fc.fences(fc.view(root, rel), rel)
    except fc.CensusError as exc:
        raise Refusal(fid, str(exc))
    by_id = {r["id"]: r for r in records}
    rec = by_id.get(fid)
    if rec is None:
        key = "%s#%s" % (rel, match.group(2))
        now = [f.id for f in fences if f.key == key]
        if now:
            raise Refusal(fid, "the fence changed since it was shown (it is now %s): run "
                               "`fence-run show %s` again" % (now[0], rel))
        raise Refusal(fid, "unknown fence")
    if rec["route"] != "runner":
        raise Refusal(fid, "its route is %s, not runner%s" % (
            rec["route"], (": " + rec["reason"]) if rec.get("reason") else ""))
    fence = next(f for f in fences if f.id == fid)
    return fence, rec


def run(fid, argv, root, environ=None, cwd=None, err=None):
    environ = dict(os.environ if environ is None else environ)
    cwd = cwd or os.getcwd()
    try:
        fence, _rec = find(fid, root)
        placeholders = _placeholders_for(fence)
        values = parse_values(argv, placeholders, cwd)
        script = script_for(fence, values, root)
    except Refusal as exc:
        return refuse(exc.subject or fid, exc.reason, err)
    except fc.Unroutable as exc:
        return refuse(fid, str(exc), err)
    env = child_env(environ, placeholders, values, root)
    proc = subprocess.run(["/bin/sh", "-c", script], cwd=cwd, env=env)
    return proc.returncode


def main(argv=None, err=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    err = err or sys.stderr
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(__doc__.split("\n\n", 1)[1] if argv else __doc__)
        return 0 if argv else 2
    try:
        root = root_or_refuse()
    except (Refusal, tkr.ToolkitRootError) as exc:
        return refuse("fence-run", getattr(exc, "reason", str(exc)), err)
    verb = argv[0]
    if verb == "show" and len(argv) == 2:
        return show(argv[1], root, err=err)
    if verb == "run" and len(argv) >= 2:
        return run(argv[1], argv[2:], root, err=err)
    return refuse("fence-run", "usage: fence-run run <id> [--arg N=V]... | fence-run show <file>",
                  err)


if __name__ == "__main__":
    sys.exit(main())
