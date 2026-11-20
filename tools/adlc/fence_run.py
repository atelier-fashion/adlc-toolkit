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

**The PR tie** (REQ-719 ADR-3). A value bound to a placeholder with the PR mark
(``fence_census.Placeholder.pr``) must be the caller's PR: an open PR of the forge repository
of the calling directory, not cross-repository, whose head is the branch checked out there.
After the value checks and the sandbox check, and before any command of the fence, the runner
reads each such value once through the forge adapter, with the text
``fence_census.pr_tie_text`` spells, the fence's preload and the fence's environment
(:func:`pr_tie`).

Exit codes: a fence's own status is passed through. 3 is the runner's refusal, and every
refusal is exactly one stderr line, ``opaque_entry_refused: <id>: <reason>``, with nothing run
(BR-9). No refusal prints the fence's environment: it holds the run's scoped credential.
Three more statuses also mean nothing ran, and are the caller's to put right, not refusals
(BUG-287): 65 with one ``fence_run_bad_value:`` line for a value that failed its check, 69
with one ``fence_run_sandboxed:`` line for a call that finds itself inside a harness sandbox
(:func:`sandboxed`), and 75 with one ``fence_run_unverified:`` line for a PR number the forge
could not be read to check. The PR read decides as follows:

- ``number`` the value, ``state=OPEN``, ``headRefName`` the checked-out branch and
  ``isCrossRepository=false``: the fence runs.
- any of those different, or ``error_class=pr-not-found``: 65, ``fence_run_bad_value:``,
  naming the value and the checked-out branch and no field of the PR read.
- no branch checked out, decided before any read: 3, ``opaque_entry_refused:``.
- the adapter's own ``opaque_entry_refused:`` with status 3 (its Azure DevOps arm under the
  runner, which would refuse the fence the same way): 3, that line passed through.
- any other failure, an answer that does not parse, or no answer in 60 s: 75,
  ``fence_run_unverified:`` with the reason.

Standard library only.
"""

import os
import re
import signal
import stat
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
def parse_values(argv, placeholders, cwd, same_dir=(), spellings=()):
    """``{arg: [values]}`` from ``--arg``/``--arg-file`` pairs, every value checked.

    A value of an argument in ``same_dir`` must be ``cwd`` itself, compared by real path.
    ``spellings`` are other spellings of ``cwd`` an ``--arg-file`` path may start with
    (:func:`given_spellings`)."""
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
            value = read_arg_file(value, cwd, spellings)
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


def between_arg_file_opens():
    """Does nothing. :func:`read_arg_file` calls it each time it holds a handle and is about to
    open the next component of the path from it: the moment a swapped directory would have to
    land. REQ-719 AC-12's test replaces it with a function that makes that swap."""


def read_arg_file(path, cwd, spellings=()):
    """A file the model wrote: a regular file under the working directory, at most 1 MiB.

    It is walked from a handle on ``cwd`` (REQ-719 ADR-4, BR-15): each component is opened
    from the handle on the one before it, following no symlink, the last with ``O_NONBLOCK``
    so a FIFO cannot hold the runner. The checks are made on the opened descriptor and the
    text is read from it, so no path is checked and then opened again. Every failure is a
    :class:`Refusal`, which :func:`parse_values` reports as a bad value.

    An absolute path may start with ``cwd`` as given, with its real path, or with one of
    ``spellings``: other spellings the caller has found name the same directory
    (:func:`given_spellings`). Each is only cut off the path as text; the walk always starts
    from ``cwd``."""
    if not path or "\x00" in path:
        raise Refusal(None, "--arg-file names no path")
    shown = path[:120]
    if ".." in path.split("/"):
        raise Refusal(None, "--arg-file %r has a '..' segment" % shown)

    def segments(text):
        return [part for part in text.split("/") if part not in ("", ".")]

    # Cut to a relative path by text alone (BR-16). A relative path is used as given; an
    # absolute one must start with cwd in its given or its real spelling (macOS's /var and
    # /private/var, LESSON-844), and that prefix is cut. Only cwd is resolved, never the file.
    parts = segments(path)
    if path.startswith("/"):
        for base in (cwd, os.path.realpath(cwd)) + tuple(spellings):
            prefix = segments(base)
            if base.startswith("/") and parts[:len(prefix)] == prefix:
                parts = parts[len(prefix):]
                break
        else:
            raise Refusal(None, "--arg-file %r is not under the working directory %r: pass a "
                                "path relative to it" % (shown, cwd))
    try:
        fd = os.open(cwd, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise Refusal(None, "--arg-file %r: the working directory cannot be opened (%s)"
                            % (shown, exc.strerror))
    try:
        for i, name in enumerate(parts):
            if i == len(parts) - 1:
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_NOCTTY", 0)
            else:
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            between_arg_file_opens()
            try:
                nxt = os.open(name, flags, dir_fd=fd)
            except OSError as exc:
                # A symlink met with O_NOFOLLOW is ELOOP on macOS and Linux, and may be
                # ENOTDIR or EMLINK elsewhere: any failure here is the caller's to correct.
                raise Refusal(None, "--arg-file %r: %r is a symlink or cannot be opened (%s)"
                                    % (shown, name[:120], exc.strerror))
            old, fd = fd, nxt
            os.close(old)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Refusal(None, "--arg-file %r is not a regular file" % shown)
        if st.st_size > MAX_ARG_FILE:
            raise Refusal(None, "--arg-file %r is %d bytes, over the 1 MiB cap"
                                % (shown, st.st_size))
        chunks = []
        left = MAX_ARG_FILE + 1
        while left > 0:
            chunk = os.read(fd, min(left, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    if len(data) > MAX_ARG_FILE:
        raise Refusal(None, "--arg-file %r is over the 1 MiB cap" % shown)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal(None, "--arg-file %r is not UTF-8 text" % shown)


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


def preload(root):
    """The partials every fence, and the runner's PR read, run after: by absolute path from
    the runner's own root (ADR-4)."""
    return '. "%s/partials/adlc-home.sh"\n. "%s/partials/forge.sh"\n' % (root, root)


def script_for(fence, values, root):
    """The preload closure, by absolute path, then the transformed fence (ADR-4)."""
    return preload(root) + fc.transform(fence.code, values, root)


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
#: (:func:`parse_values`), or whose PR number is not the caller's PR (:func:`pr_tie`). Not a
#: refusal either: nothing ran, and a corrected value is checked the same way.
BAD_VALUE = 65
#: Exit status of a call whose PR number could not be checked, because the forge could not be
#: read for it (:func:`pr_tie`, REQ-719 BR-11). Neither a pass nor a refusal: nothing ran, and
#: the exec prompt bounds the retry to one before the session reports it as a blocker.
UNVERIFIED = 75
#: How long the runner waits for its PR read before it counts the forge as unread.
PR_TIE_TIMEOUT = 60
_ERROR_CLASS_RE = re.compile(r"^[a-z][a-z-]{0,39}$")


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


# --------------------------------------------------------------------------- the PR tie
def read_pr(arg, root, cwd, env):
    """``(status, stdout, stderr)`` of the runner's read of the PR-marked value ``arg``: the
    text :func:`fence_census.pr_tie_text` spells, run as the fence is, under ``/bin/sh`` in
    ``cwd`` after :func:`preload` and in the fence's own environment ``env``
    (:func:`child_env`), so it reads the forge repository of the calling directory and the
    mock forge answers it. ``None`` when it gave no answer in :data:`PR_TIE_TIMEOUT` seconds:
    its process group is then killed, so a hung backend does not hold the runner."""
    script = preload(root) + fc.pr_tie_text(arg) + "\n"
    try:
        proc = subprocess.Popen(["/bin/sh", "-c", script], cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                start_new_session=True)
    except OSError as exc:
        return -1, "", str(exc)
    try:
        out, errtext = proc.communicate(timeout=PR_TIE_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return None
    return proc.returncode, out, errtext


_DIGITS_RE = re.compile(r"^[0-9]{1,18}$")


def _pr_fields(out):
    """The fields of a ``--fields`` answer, or ``None`` when it does not parse: a line that is
    not ``key=value``, one of :data:`fence_census.PR_TIE_FIELDS` missing or given twice, a
    ``number`` that is not one, or an ``isCrossRepository`` neither ``true`` nor ``false``."""
    fields = {}
    for line in out.splitlines():
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep:
            return None
        if key in fc.PR_TIE_FIELDS:
            if key in fields:
                return None
            fields[key] = value
    if len(fields) != len(fc.PR_TIE_FIELDS) or not _DIGITS_RE.match(fields["number"]) or \
            fields["isCrossRepository"] not in ("true", "false"):
        return None
    return fields


def pr_verdict(value, branch, answer):
    """What the runner's PR read (``answer``, :func:`read_pr`'s) says of ``value`` (REQ-719
    ADR-3): ``(None, "")`` when it is the open, same-repository PR whose head is ``branch``.
    Else ``(BAD_VALUE, "")`` when any field differs or the forge does not know the number;
    ``(REFUSED, line)`` with the adapter's own ``opaque_entry_refused:`` line (its Azure DevOps
    arm under the runner, which would refuse the fence the same way); and ``(UNVERIFIED,
    why)`` for any other failure, an answer that does not parse, or no answer at all."""
    if answer is None:
        return UNVERIFIED, "no answer in %d s" % PR_TIE_TIMEOUT
    status, out, errtext = answer
    if status != 0:
        refused = [ln for ln in errtext.splitlines() if ln.startswith("opaque_entry_refused:")]
        if status == REFUSED and refused:
            return REFUSED, refused[0][:400]
        klass = next((ln.split("=", 1)[1] for ln in out.splitlines()
                      if ln.startswith("error_class=")), "")
        if klass == "pr-not-found":
            return BAD_VALUE, ""
        if _ERROR_CLASS_RE.match(klass):
            return UNVERIFIED, "error_class=%s" % klass
        return UNVERIFIED, "the read exited with status %d" % status
    fields = _pr_fields(out)
    if fields is None:
        return UNVERIFIED, "its answer did not parse"
    if int(fields["number"]) != int(value) or fields["state"] != "OPEN" or \
            fields["headRefName"] != branch or fields["isCrossRepository"] != "false":
        return BAD_VALUE, ""
    return None, ""


def pr_tie(fid, args, values, root, cwd, environ, env, err=None):
    """``None`` when the value of each of ``args``, the fence's PR-marked arguments, is the
    caller's PR; else the exit status, its one line written to ``err`` (REQ-719 BR-9 to BR-11).

    The caller's PR is an open PR of the forge repository of ``cwd``, not cross-repository,
    whose head is the branch checked out in ``cwd``. With no branch checked out no PR is, and
    the call is refused before any forge read. The line for a value that is not the caller's
    names the value and the branch, and no field of the PR that was read."""
    err = err or sys.stderr
    branch = checked_out_branch(cwd, environ)
    if not branch:
        return refuse(fid, "no branch is checked out here (a detached HEAD, or no repository), "
                           "so no PR is this directory's and the value for %s cannot be "
                           "checked" % " and ".join(args), err)
    for arg in args:
        value = values[arg][0]
        status, text = pr_verdict(value, branch, read_pr(arg, root, cwd, env))
        if status is None:
            continue
        if status == REFUSED:
            err.write(text + "\n")
        elif status == BAD_VALUE:
            err.write("fence_run_bad_value: %s: value for %s, %s, is not the open PR of the "
                      "branch checked out here (%s). Nothing ran: correct that value and run "
                      "the line again.\n" % (fid, arg, value, branch))
        else:
            err.write("fence_run_unverified: %s: the forge could not be read to check that the "
                      "value for %s is the open PR of the branch checked out here (%s). Nothing "
                      "ran: run the same line once more, and if it answers the same way, report "
                      "it as a blocker.\n" % (fid, arg, text))
        return status
    return None


def given_spellings(cwd, environ):
    """Another spelling of ``cwd`` an absolute ``--arg-file`` path may start with (BR-16):
    ``$PWD``, the calling shell's spelling of its directory, when it is an absolute path
    naming the same directory as ``cwd``. ``os.getcwd()`` is always the real spelling (macOS's
    /private/var), and a model writes the one its shell shows (/var), LESSON-844."""
    pwd = environ.get("PWD") or ""
    if not pwd.startswith("/") or pwd == cwd or "\x00" in pwd:
        return ()
    try:
        return (pwd,) if os.path.samefile(pwd, cwd) else ()
    except (OSError, ValueError):
        return ()


def run(fid, argv, root, environ=None, cwd=None, err=None):
    environ = dict(os.environ if environ is None else environ)
    cwd = cwd or os.getcwd()
    try:
        fence, rec = find(fid, root)
        placeholders = _placeholders_for(fence)
        try:
            values = parse_values(argv, placeholders, cwd, same_dir_args(rec),
                                  given_spellings(cwd, environ))
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
    # After the value checks and the sandbox check, so a chained call reads 69 and makes no
    # forge call, and before any command of the fence (REQ-719 BR-12, LESSON-893).
    tied = fc.tied_args(placeholders)
    if tied:
        status = pr_tie(fid, tied, values, root, cwd, environ, env, err)
        if status is not None:
            return status
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
