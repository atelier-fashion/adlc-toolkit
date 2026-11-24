#!/usr/bin/env python3
"""The quickstart end-to-end driver (REQ-672 BR-9, architecture ADR-5).

Runs the marked steps of ``docs/quickstart.md`` in a fresh sandbox ``HOME`` and judges
the BR-9 outcomes with ``quickstart_check.py``::

    python3 tools/launch/quickstart_e2e.py --with-model --throwaway-repo OWNER/NAME [options]

The steps come from the page through ``quickstart_steps.py``; this file holds no copy of
a command or a prompt. Three substitutions, named by the page's ``e2e=`` markers, are the
only differences from what a newcomer types: ``existing-repo`` appends
``--existing-repo OWNER/NAME`` to its command, ``init-prompt`` sends the quoted prompt of
``claude "<prompt>"`` as a headless turn, and ``req-id`` replaces ``REQ-xxx`` with the id
of the one ``.adlc/specs/REQ-*/`` directory the step before wrote. A ``shell`` step runs
under ``sh -c`` in the tracked working directory (a bare ``cd DIR`` moves it), a
``prompt`` is a fresh ``claude -p`` turn, and an ``answer`` resumes the turn before it.

A real run starts real Claude Code sessions and pushes to a real GitHub repository. It is
the maintainer's release-checklist step, made at their word: without ``--with-model``, a
``--throwaway-repo``, a model credential variable and ``GH_TOKEN`` it runs nothing.
``--help`` lists the options.

The sandbox is a ``mkdtemp`` directory under ``ADLC_E2E_TMPROOT``, else the system temp
directory. It is refused when it is inside a git work tree or is or holds the real home,
and it is removed on exit unless ``--keep``. A child process gets only the allowlisted
environment (:data:`CHILD_ENV_NAMES`), with the sandbox ``HOME``; the credential entries
are copied by name and their values are never read, printed or logged here.

Output: one ``PASS|FAIL|SKIPPED <check>: <reason>`` line per check, then a summary line
with the run's wall-clock time, on stdout (on stderr with ``--demo``, whose stdout is only
the steps and their output). Every other line the driver prints starts ``quickstart-e2e:``.
Exit 0 when every check ran and passed, 1 when one failed, 2 when none failed but one
was skipped, or the arguments were refused and nothing ran. Python 3.9, stdlib only.
"""

import argparse
import os
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "adlc"))

import credential_redact  # noqa: E402
import quickstart_check as qc  # noqa: E402
import quickstart_steps as qs  # noqa: E402

#: The variables a model credential may be in. Only their presence is ever tested.
MODEL_CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
#: GitHub's credential: a fine-grained token scoped to the throwaway repo.
GITHUB_CREDENTIAL_VAR = "GH_TOKEN"
#: Copied from the caller as they are.
PASSTHROUGH_VARS = ("PATH", "TMPDIR", "LANG", "LC_ALL", "TERM")
#: Every name a child's environment may hold. HOME is always the sandbox's.
CHILD_ENV_NAMES = ("HOME",) + PASSTHROUGH_VARS + MODEL_CREDENTIAL_VARS + (GITHUB_CREDENTIAL_VAR,)
#: The tools a headless turn may use, as plugin-sandbox.sh's lite pipeline gives them.
ALLOWED_TOOLS = "Bash Read Write Edit Glob Grep Skill Agent Task Workflow TodoWrite"
TMPROOT_VAR = "ADLC_E2E_TMPROOT"
SANDBOX_PREFIX = "adlc-quickstart-e2e."
GIT_NAME = "ADLC Quickstart E2E"
GIT_EMAIL = "e2e@example.invalid"
GITCONFIG = ("[user]\n\tname = %s\n\temail = %s\n[init]\n\tdefaultBranch = main\n"
             "[credential]\n\thelper =\n[credential \"https://github.com\"]\n"
             "\thelper = !gh auth git-credential\n") % (GIT_NAME, GIT_EMAIL)
#: ``--marketplace`` replaces the last word of a step 1 that starts with these.
MARKETPLACE_ADD = ("claude", "plugin", "marketplace", "add")
#: The step whose last word names the plugin ``plugin-installed`` looks for.
PLUGIN_INSTALL = ("claude", "plugin", "install")
#: What the demo shows in place of the sandbox path and of its parent.
DEMO_SANDBOX = "~sandbox"
DEMO_TMP = "~tmp"
#: The check that the page's steps ran, reported with the outcomes.
STEPS = "steps"
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 1, 2
STATUS = {True: "PASS", False: "FAIL", None: "SKIPPED"}
#: What starts every line the driver prints that is not a check line or a step's output.
PREFIX = "quickstart-e2e: "
REFUSED = PREFIX + "refused, nothing ran: "
#: What a failed removal in the sandbox may be retried with, once unlocked.
_REMOVALS = (os.unlink, os.rmdir)

_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9._-]*$")
_NUMBER_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


class SandboxError(Exception):
    """The sandbox could not be made, or failed validation."""


def _positive(text):
    if not _NUMBER_RE.match(text) or float(text) <= 0:
        raise argparse.ArgumentTypeError("%r is not a positive number" % text)
    return text


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(EXIT_SKIP, "%s%s\n" % (REFUSED, message))


def parse_args(argv):
    parser = _Parser(prog="quickstart_e2e.py", description=(
        "Run docs/quickstart.md's steps in a sandbox HOME and check the BR-9 outcomes."))
    add = parser.add_argument
    add("--with-model", action="store_true", help="opt in to paid model turns")
    add("--throwaway-repo", metavar="OWNER/NAME",
        help="an empty repository made for this run; NAME must contain e2e")
    add("--marketplace", metavar="PATH", help="replace step 1's source, to check a clone")
    add("--keep", action="store_true", help="keep the sandbox and say where it is")
    add("--demo", action="store_true", help="print each step as typed, then its output")
    add("--budget-usd", type=_positive, default="5", help="per model turn (default 5)")
    add("--pipeline-budget-usd", type=_positive, default="15",
        help="for the last step (default 15)")
    add("--timeout-min", type=_positive, default="90", help="per step (default 90)")
    add("--model", metavar="NAME", help="--model for every turn")
    add("--page", metavar="PATH", default=qs.DEFAULT_PAGE, help="default docs/quickstart.md")
    return parser.parse_args(argv)


def usage_refusal(opts):
    """Why the arguments are refused before anything runs, or None."""
    repo = opts.throwaway_repo
    if repo is not None:
        if not _REPO_RE.match(repo) or repo.split("/")[1] in (".", ".."):
            return "--throwaway-repo %r is not OWNER/NAME" % repo
        if "e2e" not in repo.split("/")[1]:
            return ("--throwaway-repo %r: the name must contain 'e2e', so a real repository "
                    "is never driven by mistake" % repo)
    if opts.marketplace is not None and not os.path.isdir(opts.marketplace):
        return "--marketplace %r is not a directory" % opts.marketplace
    return None


def readiness(opts, environ):
    """Why the run may not spend, or None. Credentials are tested for presence only."""
    if not opts.with_model:
        return "the run makes paid model turns: pass --with-model to opt in"
    if not opts.throwaway_repo:
        return ("no throwaway GitHub repo: create an empty one yourself (gh repo create "
                "OWNER/adlc-e2e-YYYYMMDD --private) and pass --throwaway-repo OWNER/NAME")
    if not any(name in environ for name in MODEL_CREDENTIAL_VARS):
        return "no model credential: set one of %s" % ", ".join(MODEL_CREDENTIAL_VARS)
    if GITHUB_CREDENTIAL_VAR not in environ:
        return ("%s is not set: give the run a fine-grained token scoped to the throwaway "
                "repo; your own gh login is never passed into the sandbox" % GITHUB_CREDENTIAL_VAR)
    return None


def child_env(environ, home):
    """The environment of every child: the allowlist, copied by name, and the sandbox HOME."""
    env = {"HOME": home}
    for name in CHILD_ENV_NAMES[1:]:
        if name in environ:
            env[name] = environ[name]
    return env


def _which(name, path):
    """``name`` on ``path`` only; never the cwd, never the caller's own PATH."""
    return shutil.which(name, path=path) if path else None


def real_homes(environ):
    homes = {environ.get("HOME")}
    try:
        homes.add(pwd.getpwuid(os.getuid()).pw_dir)
    except KeyError:
        pass
    return {os.path.realpath(home) for home in homes if home}


def sandbox_problem(path, root, homes):
    """Why ``path`` is not a sandbox this run made under ``root`` and may remove, or None."""
    if os.path.islink(path) or not os.path.isdir(path):
        return "%s is not a directory" % path
    real = os.path.realpath(path)
    if (real != path or os.path.dirname(real) != root
            or not os.path.basename(real).startswith(SANDBOX_PREFIX)):
        return "%s is not a directory this run made under %s" % (path, root)
    if os.stat(real).st_uid != os.getuid():
        return "%s is not owned by this user" % real
    for home in homes:
        if real == home or home.startswith(real + os.sep):
            return "%s is, or holds, the real home %s" % (real, home)
    return None


def _git_tree_problem(path, environ):
    git = _which("git", environ.get("PATH"))
    if git is None:
        return "git is not on PATH"
    found = subprocess.run([git, "-C", path, "rev-parse", "--git-dir"], env={
        "PATH": environ.get("PATH", ""), "HOME": path}, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if found.returncode == 0:
        return ("%s is inside a git work tree: set %s to a directory outside any repository"
                % (path, TMPROOT_VAR))
    return None


def make_sandbox(environ, homes):
    """``(root, sandbox)``: a fresh, validated temp directory, and the directory holding it."""
    root = environ.get(TMPROOT_VAR) or tempfile.gettempdir()
    if not os.path.isabs(root) or not os.path.isdir(root):
        raise SandboxError("the sandbox root %r is not an absolute path to a directory" % root)
    root = os.path.realpath(root)
    sandbox = tempfile.mkdtemp(prefix=SANDBOX_PREFIX, dir=root)
    problem = sandbox_problem(sandbox, root, homes) or _git_tree_problem(sandbox, environ)
    if problem:
        os.rmdir(sandbox)
        raise SandboxError(problem)
    for name in ("home", "work", "logs"):
        os.mkdir(os.path.join(sandbox, name), 0o700)
    with open(os.path.join(sandbox, "home", ".gitconfig"), "w", encoding="utf-8") as handle:
        handle.write(GITCONFIG)
    return root, sandbox


def _in_sandbox(folder, sandbox):
    """True when ``folder`` is a directory, not a symlink, whose real path is in ``sandbox``."""
    try:
        if not stat.S_ISDIR(os.lstat(folder).st_mode):
            return False
    except OSError:
        return False
    real = os.path.realpath(folder)
    return real == sandbox or real.startswith(sandbox + os.sep)


def remove_sandbox(sandbox, root, homes, err):
    problem = sandbox_problem(sandbox, root, homes)
    if problem:
        err.write("%snot removing the sandbox: %s\n" % (PREFIX, problem))
        return
    left = []

    def _unlock(func, path, _exc):
        # A removal a read-only directory refused: unlock and retry it, but only where
        # every directory chmod would touch is a real one inside the sandbox, so that no
        # symlink leads a chmod or a removal out of it.
        folders = [os.path.dirname(path)]
        if os.path.isdir(path) and not os.path.islink(path):
            folders.append(path)
        if func not in _REMOVALS or not all(_in_sandbox(f, sandbox) for f in folders):
            left.append(path)
            return
        try:
            for folder in folders:
                # The remaining window before the chmod is closed: every child has exited.
                if not stat.S_ISDIR(os.lstat(folder).st_mode):
                    left.append(path)
                    return
                os.chmod(folder, 0o700)
            func(path)
        except OSError:
            left.append(path)

    shutil.rmtree(sandbox, onerror=_unlock)
    for path in left:
        err.write("%sleft behind, remove it yourself: %s\n" % (PREFIX, path))


def _spawn(argv, cwd, env, out, err, timeout):
    """``argv``'s exit code; 124 when it outlived ``timeout`` and was killed, 127 unstarted."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=err, start_new_session=True)
    except OSError as exc:
        err.write("cannot run %s: %s\n" % (os.path.basename(argv[0]), exc.strerror))
        return 127
    try:
        return proc.wait(timeout=timeout)
    except BaseException as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        if isinstance(exc, subprocess.TimeoutExpired):
            return 124
        raise


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


class Children(object):
    """Every process the driver starts: one environment, a log per call, a time cap."""

    def __init__(self, env, logs, timeout):
        self.env, self.logs, self.timeout, self.count = env, logs, timeout, 0

    def which(self, name):
        return _which(name, self.env.get("PATH"))

    def run(self, argv, cwd, tag=None, merge=False):
        """``(code, stdout, stderr)``; ``argv[0]`` is resolved on the sandbox PATH."""
        exe = argv[0] if os.path.isabs(argv[0]) else self.which(argv[0])
        if exe is None:
            return 127, "", "%s is not on PATH" % argv[0]
        self.count += 1
        base = os.path.join(self.logs, tag or "call-%02d" % self.count)
        with open(base + ".out", "w", encoding="utf-8") as out, \
                open(base + ".err", "w", encoding="utf-8") as err:
            code = _spawn([exe] + list(argv[1:]), cwd, self.env, out, out if merge else err,
                          self.timeout)
        if code == 124:  # said where the caller reads: a merged call reads .out
            with open(base + (".out" if merge else ".err"), "a", encoding="utf-8") as err:
                err.write("timed out after %g minutes and was killed\n" % (self.timeout / 60))
        return code, _read(base + ".out"), _read(base + ".err")


def _variants(path):
    real = os.path.realpath(path)
    found = {path.rstrip("/"), real}
    if real.startswith("/private/"):
        found.add(real[len("/private"):])
    return found


class Scrubber(object):
    """Text shown to a reader: the sandbox, its parent and the caller's home named, not
    spelled, and every credential shape redacted."""

    def __init__(self, sandbox, root, environ):
        pairs = {}
        for path, name in ((environ.get("HOME"), "~"), (environ.get("TMPDIR"), DEMO_TMP),
                           (root, DEMO_TMP), (sandbox, DEMO_SANDBOX)):
            for variant in _variants(path) if path else ():
                if len(variant) > 1:
                    pairs[variant] = name
        self.pairs = sorted(pairs.items(), key=lambda pair: -len(pair[0]))

    def __call__(self, text):
        for old, new in self.pairs:
            text = text.replace(old, new)
        return credential_redact.redact(text, credential_redact.ALL_PATTERNS)[0]


def _rest(text, *head):
    """The words of ``text`` after ``head``, or None when it does not start with them."""
    try:
        words = shlex.split(text)
    except ValueError:
        return None
    return words[len(head):] if tuple(words[:len(head)]) == head else None


def _one(words):
    return words[0] if words is not None and len(words) == 1 else None


def with_marketplace(command, source):
    """Step 1 with its source replaced by ``source``, or None when it has no source."""
    if _one(_rest(command, *MARKETPLACE_ADD)) is None:
        return None
    return " ".join(shlex.quote(word) for word in list(MARKETPLACE_ADD) + [source])


def init_prompt(command):
    """The quoted prompt of ``claude "<prompt>"``, or None."""
    return _one(_rest(command, "claude"))


def cd_target(command):
    """The directory of a bare ``cd DIR``, or None."""
    return _one(_rest(command, "cd"))


def plugin_id_of(steps):
    """The plugin the page's install step names, or None."""
    for step in steps:
        if _one(_rest(step.text, *PLUGIN_INSTALL)):
            return _one(_rest(step.text, *PLUGIN_INSTALL))
    return None


def _tag(step):
    return step.kind if step.e2e is None else "%s e2e=%s" % (step.kind, step.e2e)


def fetch_origin(children, cwd, tag):
    """True when ``git fetch origin`` in ``cwd`` succeeded, so ``origin/main`` is current.

    Its result goes to every check that reads ``origin/main``: on False each fails with
    ``quickstart_check.NOT_FETCHED`` rather than judge a stale ref.
    """
    code, _out, _err = children.run(["git", "fetch", "-q", "origin"], cwd, tag=tag)
    return code == 0


class Driver(object):
    """Runs the steps in order, tracking the working directory and the model session."""

    def __init__(self, opts, steps, sandbox, children, scrub, show):
        self.opts, self.steps, self.children, self.scrub, self.show = (
            opts, steps, children, scrub, show)
        self.cwd = os.path.join(sandbox, "work")
        self.session = None
        self.transcript = ""  # the last step's stream-json output, which lesson-or-no-entry reads
        self.precondition = None

    def run(self, progress):
        total = len(self.steps)
        for number, step in enumerate(self.steps, 1):
            if number == total:
                fetched = fetch_origin(self.children, self.cwd, "fetch-setup")
                self.precondition = qc.setup_pushed(self.children.run, self.cwd,
                                                    fetched=fetched)
            progress("step %d/%d: %s" % (number, total, _tag(step)))
            why = self.step(number, step, number == total)
            if why:
                return qc.Result(STEPS, False, "step %d of %d (%s) %s"
                                 % (number, total, _tag(step), why))
        return qc.Result(STEPS, True, "the page's %d steps ran in order" % total)

    def step(self, number, step, last):
        budget = self.opts.pipeline_budget_usd if last else self.opts.budget_usd
        if step.e2e == qs.E2E_INIT_PROMPT:
            prompt = init_prompt(step.text)
            if prompt is None:
                return "is not claude with one quoted prompt, so it cannot run headless"
            self.show("$ " + step.text)
            return self.turn(number, prompt, None, budget)
        if step.kind == qs.KIND_SHELL:
            command = step.text
            if number == 1 and self.opts.marketplace:
                command = with_marketplace(command, os.path.abspath(self.opts.marketplace))
                if command is None:
                    return "has no marketplace source for --marketplace to replace"
            if step.e2e == qs.E2E_EXISTING_REPO:
                command = "%s --existing-repo %s" % (command, shlex.quote(self.opts.throwaway_repo))
            self.show("$ " + step.text)
            target = cd_target(command)
            return self.change_dir(target) if target is not None else self.shell(number, command)
        if step.kind == qs.KIND_ANSWER:
            if self.session is None:
                return "is an answer with no model session before it to resume"
            self.show("> " + step.text)
            return self.turn(number, step.text, self.session, budget)
        prompt = step.text
        if step.e2e == qs.E2E_REQ_ID:
            names = qc.req_dirs(self.cwd)
            if len(names) != 1:
                return ("needs the one .adlc/specs/REQ-*/ directory the step before wrote, and "
                        "found %s" % (", ".join(names) if names else "none"))
            prompt = prompt.replace(qs.REQ_ID_PLACEHOLDER, qc.req_id(names[0]))
        self.show("> " + prompt)
        return self.turn(number, prompt, None, budget)

    def change_dir(self, target):
        folder = os.path.normpath(os.path.join(self.cwd, target))
        if not os.path.isdir(folder):
            return "cannot cd: %s is not a directory" % self.scrub(folder)
        self.cwd = folder
        return None

    def _failure(self, number, code, text):
        lines = [line for line in self.scrub(text).splitlines() if line.strip()]
        tail = (": " + lines[-1].strip()[:200]) if lines else ""
        return "exited %d%s (logs: %s, kept with --keep)" % (code, tail, self.scrub(
            os.path.join(self.children.logs, "step-%d.*" % number)))

    def shell(self, number, command):
        code, out, _ = self.children.run(["/bin/sh", "-c", command], self.cwd,
                                         tag="step-%d" % number, merge=True)
        if out.strip():
            self.show(out.rstrip("\n"))
        return self._failure(number, code, out) if code != 0 else None

    def turn(self, number, prompt, resume, budget):
        claude = self.children.which("claude")
        if claude is None:
            return "needs claude, which is not on PATH"
        session = resume or str(uuid.uuid4())
        argv = [claude, "-p", prompt, "--resume" if resume else "--session-id", session,
                "--output-format", "stream-json", "--verbose", "--max-budget-usd", budget,
                "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS]
        if self.opts.model:
            argv += ["--model", self.opts.model]
        code, stream, err = self.children.run(argv, self.cwd, tag="step-%d" % number)
        self.session = session
        if number == len(self.steps):
            self.transcript = stream
        result = qc.result_event(stream)
        text = result.get("result") if result else None
        if isinstance(text, str) and text.strip():
            self.show(text.rstrip("\n"))
        if code != 0:
            return self._failure(number, code, err)
        if result is None:
            return "printed no result event"
        if result.get("is_error"):
            return "ended in an error result (%s)" % result.get("subtype", "no subtype")
        return None


def report(results, out, elapsed):
    """Print one line per check and the summary, with ``elapsed`` seconds as whole minutes
    rounded up and seconds; return the exit code."""
    counts = {True: 0, False: 0, None: 0}
    for result in results:
        counts[result.ok] += 1
        out.write("%s %s: %s\n" % (STATUS[result.ok], result.name, result.reason))
    seconds = int(round(elapsed))
    out.write("%s%d checks, %d failed, %d skipped, elapsed %d min (%d s)\n" % (
        PREFIX, len(results), counts[False], counts[None], (seconds + 59) // 60, seconds))
    out.flush()
    return EXIT_FAIL if counts[False] else EXIT_SKIP if counts[None] else EXIT_PASS


def _all(ok, reason):
    return [qc.Result(name, ok, reason) for name in (STEPS, qc.SETUP_PUSHED) + qc.OUTCOMES]


def run_checks(opts, steps, root, sandbox, environ, stdout, stderr):
    """Run the steps in ``sandbox``, then every check; the scrubbed results."""
    scrub = Scrubber(sandbox, root, environ)
    children = Children(child_env(environ, os.path.join(sandbox, "home")),
                        os.path.join(sandbox, "logs"), float(opts.timeout_min) * 60)

    def show(text):
        stdout.write(scrub(text) + "\n")
        stdout.flush()

    def progress(text):
        stderr.write(PREFIX + text + "\n")
        stderr.flush()

    driver = Driver(opts, steps, sandbox, children, scrub, show if opts.demo else lambda _: None)
    ran = driver.run((lambda _: None) if opts.demo else progress)
    precondition = driver.precondition or qc.Result(
        qc.SETUP_PUSHED, None, "the run stopped before the last step")
    # What /adlc:proceed merged is on origin/main: a lesson, which lesson-or-no-entry
    # reads there, and an escalated spec, which lite-req reads there first.
    fetched = fetch_origin(children, driver.cwd, "fetch")
    plugin_id = plugin_id_of(steps)
    outcomes = qc.run_all(children.run, driver.cwd, plugin_id or "", opts.throwaway_repo,
                          driver.transcript, fetched=fetched)
    if plugin_id is None:
        outcomes[0] = qc.Result(qc.PLUGIN_INSTALLED, False, "the page has no plugin install "
                                "step naming the plugin to look for")
    return [qc.Result(r.name, r.ok, scrub(r.reason)) for r in [ran, precondition] + outcomes]


def _run(opts, environ, stdout, stderr):
    """The results of a run the arguments allow, and whether it reached the repo."""
    why = readiness(opts, environ)
    if why:
        return _all(None, "nothing ran: " + why), False
    try:
        steps = qs.load(opts.page)
        qs.check_count(steps)
    except (OSError, UnicodeDecodeError, qs.QuickstartError) as exc:
        results = _all(None, "the page could not be read")
        results[0] = qc.Result(STEPS, False, "cannot use the page %s: %s" % (opts.page, exc))
        return results, False
    homes = real_homes(environ)
    try:
        root, sandbox = make_sandbox(environ, homes)
    except (OSError, SandboxError) as exc:
        return _all(None, "nothing ran: no sandbox: %s" % exc), False
    try:
        return run_checks(opts, steps, root, sandbox, environ, stdout, stderr), True
    finally:
        if opts.keep:
            stderr.write("%ssandbox kept: %s\n" % (PREFIX, sandbox))
        else:
            remove_sandbox(sandbox, root, homes, stderr)


def main(argv=None, environ=None, stdout=None, stderr=None, clock=time.monotonic):
    """``clock`` is read when the run starts and when it ends, for the summary line."""
    start = clock()
    environ = os.environ if environ is None else environ
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    opts = parse_args(argv)
    refusal = usage_refusal(opts)
    if refusal:
        stderr.write("%s%s\n" % (REFUSED, refusal))
        return EXIT_SKIP
    results, ran = _run(opts, environ, stdout, stderr)
    code = report(results, stderr if opts.demo else stdout, clock() - start)
    if ran:
        stderr.write("%s%s is yours to delete; this driver never deletes it\n"
                     % (PREFIX, opts.throwaway_repo))
    return code


def _terminate(_signum, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
