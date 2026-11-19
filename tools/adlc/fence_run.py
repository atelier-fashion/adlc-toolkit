#!/usr/bin/env python3
"""fence_run — the one admitted entry point an exec model has to the toolkit's fences (REQ-682).

Usage:
  fence-run run <id> [--arg NAME=VALUE]... [--arg-file NAME=PATH]...
  fence-run show <toolkit-relative file>

``run`` runs one census fence whose route is ``runner``. It recomputes the census from its own
real path on every call (ADR-2), so an id whose fence changed, or whose route is ``direct``,
``engine`` or ``excised``, is refused, and nothing a working copy or the environment holds is
trusted. The census is every exec-capable adapter's under that root (``harness/*.yml``), and a
fence ``runner`` in any of them is accepted: each one's reach was audited against every
adapter's deny tier, so no harness that calls reaches a command any adapter denies (REQ-662
ADR-8). Each value is checked against its placeholder's full-match pattern and reaches the
fence only as an ``ADLC_ARG_*`` environment variable, expanded once inside double quotes
(ADR-3). The branch push (REQ-662 ADR-9) pushes only the branch checked out in the calling
directory, under an exec run only one of that run's REQ (``ADLC_EXEC_RUN``), and also holds
its ``worktree`` value to the directory
the runner was called from. The fence runs under ``/bin/sh`` in the current directory, with
``ADLC_TOOLKIT_ROOT`` the runner's own root and ``ADLC_FENCE_TOOLKIT_ONLY=1``, after
``adlc-home.sh`` and ``forge.sh`` are sourced from that root (ADR-4). No caller ``GIT_*``
variable reaches the fence, and its git calls run no fsmonitor program and no repository
hook (``GIT_PINS``). Those are two of the keys the orchestrator pins for its own git calls,
and the only two pinned here: the orchestrator's ssh and credential pins point at files in
its run directory and would break the operator's own push credentials. Otherwise a fence's
git calls honour the repository's config, which a model can write. The pins are defense in
depth, and the README's declared residual (f) says what stays open.

``show`` prints a file of the exec set with every fence replaced by its route's form, which is
how toolkit skills and agents reach an exec model: under BUG-260's isolation flags they are
not loaded (ADR-5).

Exit codes: a fence's own status is passed through. 3 is the runner's refusal, and every
refusal is exactly one stderr line, ``opaque_entry_refused: <id>: <reason>``, with nothing run
(BR-9). No refusal prints the fence's environment: it holds the run's scoped credential.
Two more statuses also mean nothing ran, and are the caller's to put right, not refusals
(BUG-287): 65 with one ``fence_run_bad_value:`` line for a value that failed its check, and 69
with one ``fence_run_sandboxed:`` line for a call that finds itself inside a harness sandbox
(:func:`sandboxed`).

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
#: Config every git call of a fence, and the branch check, is pinned to, over whatever the
#: repository's own config says: the model can write that config, and a fsmonitor program or
#: a hook would run its code outside a harness sandbox. These are two of the keys the
#: orchestrator pins for its own git calls (``exec_safety.Toolbox.git_config_pairs``, which
#: also pins ``core.sshCommand``, ``credential.helper``, ``core.attributesFile``,
#: ``commit.gpgsign``, ``log.showSignature`` and ``protocol.ext.allow``). The runner pins only
#: these two. The orchestrator's ``core.sshCommand`` and ``credential.helper`` point at files
#: in its run directory, and here they would break the operator's own push credentials; the
#: rest of its list is not carried over either. Every other key of the repository's config is
#: honoured, so this is defense in depth, and the README's declared residual (f) says so.
GIT_PINS = (("core.fsmonitor", "false"), ("core.hooksPath", "/dev/null"))
#: ``ADLC_EXEC_RUN``, as the orchestrator sets it: the run's REQ id (REQ-662 ADR-9).
_RUN_ID_RE = re.compile(r"^REQ-[0-9]{3,6}$")


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
              "in it written `'\\''`, or pass a file inside your working copy with `--arg-file NAME=PATH` (for a value "
              "that holds a quote or a newline). The runner checks each value and binds it as "
              "data.")


def runner_call(rec, root, placeholders):
    """The runner call that stands for a ``runner`` fence, with a stub per value.

    The id is single-quoted. It holds a ``#``, and Codex does not match a prefix rule against
    a command with a bare one: the runner then runs inside the sandbox, where its push cannot
    reach the remote (measured on codex-cli 0.166.0, 2026-11-18; the quoted id matches, with
    quoted or bare values after it). An id holds no quote, so the quoting is exact."""
    parts = [runner_path(root), "run", "'%s'" % rec["id"]]
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
def parse_values(argv, placeholders, cwd, same_dir=()):
    """``{arg: [values]}`` from ``--arg``/``--arg-file`` pairs, every value checked.

    A value of an argument in ``same_dir`` must be ``cwd`` itself, compared by real path."""
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
        if not why and name in same_dir and \
                os.path.realpath(os.path.join(cwd, value)) != os.path.realpath(cwd):
            why = "is not the directory the runner was called from (%s)" % cwd
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


def git_env(environ):
    """``environ`` with every caller ``GIT_*`` variable dropped and :data:`GIT_PINS` set
    through ``GIT_CONFIG_COUNT``, which outranks every config file. A caller's ``GIT_DIR`` or
    ``GIT_WORK_TREE`` would point the branch check and the push at different repositories,
    and its ``GIT_CONFIG_*`` or ``GIT_SSH_COMMAND`` would run its own program. A caller's
    ``GIT_TERMINAL_PROMPT=0`` stays: it only makes git fail sooner."""
    env = {k: v for k, v in environ.items() if not k.startswith("GIT_")}
    if environ.get("GIT_TERMINAL_PROMPT") == "0":
        env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_COUNT"] = str(len(GIT_PINS))
    for i, (key, value) in enumerate(GIT_PINS):
        env["GIT_CONFIG_KEY_%d" % i] = key
        env["GIT_CONFIG_VALUE_%d" % i] = value
    return env


def child_env(environ, placeholders, values, root):
    """The fence's environment: the inherited one, with every caller ``ADLC_ARG_*`` and the
    toolkit-only flag dropped and its git state replaced (:func:`git_env`), then the bound
    values, the root, and the flag, set last."""
    env = {k: v for k, v in git_env(environ).items()
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
    """``(fence, record)`` for ``fid``, or :class:`Refusal` naming why not.

    The fence must be ``runner`` in the census of at least one exec-capable adapter under
    ``root`` (REQ-662 ADR-8). Which harness is calling is never asked: no variable, argument or
    working-copy file chooses a census (REQ-682 ADR-2)."""
    match = _ID_RE.match(fid or "")
    if not match:
        raise Refusal(fid, "not a fence id (<path>#<ordinal>:<sha8>)")
    rel = match.group(1)
    if rel not in fc.EXEC_FILES:
        raise Refusal(fid, "%s is not in the exec file set" % rel)
    try:
        routed = [(a.name, fc.census(root, a)) for a in fc.exec_adapters(root)]
        fences = fc.fences(fc.view(root, rel), rel)
    except fc.CensusError as exc:
        raise Refusal(fid, str(exc))
    recs = [(name, r) for name, records in routed for r in records if r["id"] == fid]
    if not recs:
        key = "%s#%s" % (rel, match.group(2))
        now = [f.id for f in fences if f.key == key]
        if now:
            raise Refusal(fid, "the fence changed since it was shown (it is now %s): run "
                               "`fence-run show %s` again" % (now[0], rel))
        raise Refusal(fid, "unknown fence")
    runner = [r for _name, r in recs if r["route"] == "runner"]
    if not runner:
        routes = list(dict.fromkeys(r["route"] for _name, r in recs))
        if len(routes) == 1:
            rec = recs[0][1]
            raise Refusal(fid, "its route is %s, not runner%s" % (
                rec["route"], (": " + rec["reason"]) if rec.get("reason") else ""))
        raise Refusal(fid, "its route is %s: runner on no exec-capable adapter" % ", ".join(
            "%s on %s" % (r["route"], name) for name, r in recs))
    fence = next(f for f in fences if f.id == fid)
    return fence, runner[0]


def push_args(rec, key):
    """The arguments the push kind the fence makes (REQ-662 ADR-9) binds under ``key``, else
    none: ``same_dir``, whose value must be the directory the runner was called from, or
    ``head``, whose value must be the branch checked out there (``fence_census.PUSH_REACH``)."""
    return tuple(fc.PUSH_REACH.get(rec.get("push"), {}).get(key, ()))


def same_dir_args(rec):
    return push_args(rec, "same_dir")


def head_args(rec):
    return push_args(rec, "head")


def checked_out_branch(cwd, environ):
    """The branch ``cwd`` has checked out, or ``""`` on a detached HEAD or outside a
    repository. It reads under the fence's own git environment (:func:`git_env`), so no
    ``GIT_*`` variable of the caller reaches it and the push sees the same repository."""
    try:
        proc = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"],
                              env=git_env(environ), stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, universal_newlines=True)
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def run_branch_refusal(branch, environ):
    """Why ``branch`` is not the exec run's own branch, or None (REQ-662 ADR-9).

    Under an exec run ``ADLC_EXEC_RUN`` names the run's REQ id, and the push takes only
    ``<type>/<that id>-<rest>``: the id followed by ``-``, so ``REQ-66`` never matches a
    ``REQ-662-`` branch. A value that is not a REQ id refuses the push. With the variable
    unset or empty nothing is added, as the orchestrator reads it: a plain /proceed pushes
    outside any exec run."""
    if not environ.get("ADLC_EXEC_RUN"):
        return None
    run_id = environ["ADLC_EXEC_RUN"]
    # fullmatch: `$` alone also matches before a trailing newline.
    if not _RUN_ID_RE.fullmatch(run_id):
        return ("ADLC_EXEC_RUN is %r, which is not a REQ id (REQ- and 3 to 6 digits), so no "
                "branch is this run's" % run_id[:40])
    _type, _sep, rest = branch.partition("/")
    if not rest.startswith(run_id + "-"):
        return ("value for branch, %s, is not this run's branch: ADLC_EXEC_RUN names %s, so "
                "the push takes only <type>/%s-<rest>" % (branch, run_id, run_id))
    return None


#: Exit status of a call that found itself inside a harness sandbox (:func:`sandboxed`). It is
#: not a refusal: nothing ran, and the same line run as a command of its own will. This and
#: :data:`BAD_VALUE` sit above the statuses a fence's own commands return (`gh` uses 1, 2 and
#: 4), and the stderr line is what names the case.
SANDBOXED = 69
#: Exit status of a call whose ``--arg`` or ``--arg-file`` value failed its check
#: (:func:`parse_values`). Not a refusal either: nothing ran, and a corrected value is checked
#: the same way.
BAD_VALUE = 65


def sandboxed(cwd, environ):
    """Why this call cannot do a fence's work, or None.

    A fence pushes, fetches, calls the forge and writes the primary repo path's state file,
    all outside the working copy. On a harness whose sandbox contains every command no allow
    matches (Codex), the runner's allow covers a call made as a command of its own; chained
    after a command with no allow (``printf … > f && fence-run run …``), the whole line runs
    inside the sandbox, and each fence then fails in its own way: a lane check that cannot
    fetch reads as a check error and escalates the REQ. So the runner asks one thing first:
    can it write the repository's git directory, which a linked worktree keeps outside the
    working copy? ``os.access`` sees a sandbox's denial. A git directory inside the working
    copy, or no repository at all, says nothing, and the call goes on."""
    try:
        res = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=cwd,
                             env=git_env(environ), stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, universal_newlines=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    out = res.stdout.strip()
    if res.returncode != 0 or not out:
        return None
    common = os.path.realpath(os.path.join(cwd, out))
    here = os.path.realpath(cwd)
    if common == here or common.startswith(here + os.sep) or not os.path.isdir(common):
        return None
    if os.access(common, os.W_OK):
        return None
    return ("this call cannot write the repository's git directory, so it is running inside "
            "the harness's sandbox, as a call chained after another command does. Nothing "
            "ran. Run this fence-run line again as a command of its own.")


def run(fid, argv, root, environ=None, cwd=None, err=None):
    environ = dict(os.environ if environ is None else environ)
    cwd = cwd or os.getcwd()
    try:
        fence, rec = find(fid, root)
        placeholders = _placeholders_for(fence)
        try:
            values = parse_values(argv, placeholders, cwd, same_dir_args(rec))
        except Refusal as exc:
            # A value of the wrong shape is the caller's to correct, not an entry the runner
            # refuses: a relative path where the fence takes an absolute one ended a real run
            # at Step 0, because a refusal is where the pipeline stops. Nothing has run, and
            # the same checks meet the corrected value.
            (err or sys.stderr).write(
                "fence_run_bad_value: %s: %s. Nothing ran: correct that value and run the "
                "line again.\n" % (fid, exc.reason))
            return BAD_VALUE
        for name in head_args(rec):
            head = checked_out_branch(cwd, environ)
            if values.get(name) != [head]:
                raise Refusal(None, "value for %s is not the branch checked out here (%s)"
                                    % (name, head or "no branch"))
            why = run_branch_refusal(head, environ)
            if why:
                raise Refusal(None, why)
        script = script_for(fence, values, root)
    except Refusal as exc:
        return refuse(exc.subject or fid, exc.reason, err)
    except fc.Unroutable as exc:
        return refuse(fid, str(exc), err)
    why = sandboxed(cwd, environ)
    if why:
        (err or sys.stderr).write("fence_run_sandboxed: %s: %s\n" % (fid, why))
        return SANDBOXED
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
