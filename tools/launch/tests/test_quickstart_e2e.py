"""The quickstart e2e driver, run against fake ``claude`` and ``gh`` (REQ-672 ADR-5, TASK-281).

No real ``claude``, ``gh`` or network answers any test. The driver runs as a child of
the test with ``PATH`` set to the fakes' directory plus ``/usr/bin:/bin`` (a directory of
those holding a banned name is mirrored without it), and each test that expects a fake to
run reads the fake's own log. The fake marketplace call points ``https://github.com/`` at
local bare repositories and forbids every git transport but ``file``, so step 3's push and
the driver's fetch stay on disk. Credentials are obviously fake canaries, shaped so that
no redaction pattern would hide a leak.

These tests show that the driver runs the page's steps and that its checks judge what a
run leaves behind. They do not show that a real session does what the fakes do: only the
maintainer's run with ``--with-model`` shows that (LESSON-899).
"""
import io
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import tokenize

import pytest

import fakes
import quickstart_check as qc
import quickstart_e2e as qe
import quickstart_steps as qs

DRIVER = os.path.join(qs.HERE, "quickstart_e2e.py")
EXAMPLES = os.path.join(qs.TOOLKIT, "examples")
REPO = "acme/adlc-quickstart-e2e"
MODEL_CANARY = "canary-model-credential-0001"
GH_CANARY = "canary-github-credential-0002"
CANARY_NAME = "QUICKSTART_E2E_CANARY"
CANARY_VALUE = "canary-not-allowlisted-0003"
#: Names a child gains on its own: macOS's CoreFoundation sets the first in a process
#: that lacks it. Nothing else may appear beside the allowlist.
PLATFORM_ADDED = {"__CF_USER_TEXT_ENCODING"}
#: And what ``/bin/sh`` adds to what it passes on.
SHELL_ADDED = PLATFORM_ADDED | {"PWD", "SHLVL", "_", "OLDPWD"}
CHECKS = [qe.STEPS, qc.SETUP_PUSHED] + list(qc.OUTCOMES)
PAGE = qs.load()
SUMMARY = r"^quickstart-e2e: 7 checks, %d failed, %d skipped, elapsed \d+ min \(\d+ s\)$"


class World(object):
    """Fakes on an offline PATH, a bare throwaway repo, a sandbox root, canary credentials."""

    def __init__(self, tmp_path, **fake):
        self.tmp = tmp_path
        self.bin, self.state = tmp_path / "bin", tmp_path / "state"
        self.root, self.github = tmp_path / "sbx", tmp_path / "github"
        for folder in (self.bin, self.root, tmp_path / "tmpdir"):
            folder.mkdir()
        self.bare = self.github / (REPO + ".git")
        self.bare.parent.mkdir(parents=True)
        subprocess.check_call(["git", "init", "-q", "--bare", str(self.bare)])
        fakes.write_fake_claude(self.bin, self.state, EXAMPLES, self.github, **fake)
        fakes.write_fake_gh(self.bin, self.state)
        path = fakes.offline_path(self.bin, tmp_path / "mirror")
        assert shutil.which("claude", path=path) == str(self.bin / "claude")
        assert shutil.which("gh", path=path) == str(self.bin / "gh")
        self.env = {"PATH": path, "HOME": os.environ["HOME"], "LANG": "en_US.UTF-8",
                    "TMPDIR": str(tmp_path / "tmpdir"), "ADLC_E2E_TMPROOT": str(self.root),
                    "ANTHROPIC_API_KEY": MODEL_CANARY, "GH_TOKEN": GH_CANARY,
                    CANARY_NAME: CANARY_VALUE}

    def run(self, *args, **env):
        merged = dict(self.env, **env)
        merged = {k: v for k, v in merged.items() if v is not None}
        done = subprocess.run([sys.executable, DRIVER] + list(args), cwd=str(self.tmp),
                              env=merged, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=180)
        self.output = done.stdout + done.stderr
        for secret in (MODEL_CANARY, GH_CANARY, CANARY_VALUE):
            assert secret not in self.output
        return done

    def full(self, *extra, **env):
        return self.run("--with-model", "--throwaway-repo", REPO, *extra, **env)

    def claude(self):
        return fakes.read_log(self.state, "claude")

    def gh(self):
        return fakes.read_log(self.state, "gh")

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo)] + list(args), check=True,
                              stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()


def statuses(stdout):
    """``{check: status}`` from the driver's check lines."""
    found = {}
    for line in stdout.splitlines():
        match = re.match(r"^(PASS|FAIL|SKIPPED) ([a-z-]+): ", line)
        if match:
            found[match.group(2)] = match.group(1)
    return found


def flag(argv, name):
    return argv[argv.index(name) + 1]


def turns(calls):
    return [call["argv"] for call in calls if call["argv"][:1] == ["-p"]]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_page_has_the_steps_these_tests_drive():
    assert [(s.kind, s.e2e) for s in PAGE] == [
        ("shell", None), ("shell", None), ("shell", "existing-repo"), ("shell", None),
        ("shell", "init-prompt"), ("answer", None), ("prompt", None), ("prompt", "req-id")]


def test_driver_runs_the_page_steps_and_passes_with_every_outcome(world):
    """AC-2: the page's eight steps, in order, with the three substitutions; exit 0."""
    done = world.full()
    assert done.returncode == 0, world.output
    assert statuses(done.stdout) == {name: "PASS" for name in CHECKS}
    assert re.search(SUMMARY % (0, 0), done.stdout, re.M), done.stdout
    # Every diagnostic line has the one prefix.
    assert done.stderr and all(line.startswith("quickstart-e2e: ")
                               for line in done.stderr.splitlines()), done.stderr
    calls = world.claude()
    # Steps 1 and 2 ran as the page types them; the last call is plugin-installed's read.
    assert [c["argv"] for c in calls[:2]] == [shlex.split(PAGE[0].text)[1:],
                                             shlex.split(PAGE[1].text)[1:]]
    assert calls[-1]["argv"] == ["plugin", "list", "--json"]
    init, answer, spec, proceed = turns(calls)
    # init-prompt: the quoted prompt of step 5, as a fresh headless session.
    assert init[1] == shlex.split(PAGE[4].text)[1]
    # answer: step 6's text, resuming that same session.
    assert answer[1] == PAGE[5].text
    assert flag(answer, "--resume") == flag(init, "--session-id")
    assert "--session-id" not in answer
    assert spec[1] == PAGE[6].text
    # req-id: REQ-xxx replaced by the id of the directory step 7 wrote.
    assert proceed[1] == PAGE[7].text.replace(qs.REQ_ID_PLACEHOLDER, "REQ-001")
    assert len({flag(init, "--session-id"), flag(spec, "--session-id"),
                flag(proceed, "--session-id")}) == 3
    for argv in (init, answer, spec, proceed):
        assert flag(argv, "--output-format") == "stream-json" and "--verbose" in argv
        assert flag(argv, "--permission-mode") == "acceptEdits"
        assert flag(argv, "--allowedTools") == qe.ALLOWED_TOOLS
        assert "--append-system-prompt" not in argv and "--model" not in argv
    assert [flag(a, "--max-budget-usd") for a in (init, answer, spec, proceed)] == \
        ["5", "5", "5", "15"]
    # Step 4's cd moved every later step into the project step 3 made.
    sandbox = os.path.dirname(calls[0]["home"])
    project = os.path.join(sandbox, "work", "adlc-quickstart")
    assert all(c["cwd"] == project for c in calls[2:])
    # existing-repo: step 3 pushed to the throwaway repo and created none.
    gh_calls = [c["argv"] for c in world.gh()]
    assert ["auth", "status", "--hostname", "github.com"] in gh_calls
    assert not [a for a in gh_calls if a[:2] == ["repo", "create"]]
    assert gh_calls[-1] == ["pr", "list", "--repo", REPO, "--state", "merged", "--json",
                            "number,headRefName"]
    assert world.git(world.bare, "rev-list", "--count", "main") == "2"
    # The sandbox was fresh, held HOME, and is gone.
    assert os.path.dirname(sandbox) == os.path.realpath(str(world.root))
    assert os.path.basename(sandbox).startswith(qe.SANDBOX_PREFIX)
    assert os.listdir(str(world.root)) == []


def test_child_environment_holds_only_the_allowlist(world):
    done = world.full()
    assert done.returncode == 0, world.output
    calls = world.claude() + world.gh()
    assert calls
    allowed = set(qe.CHILD_ENV_NAMES)
    for call in calls:
        names = set(call["env"])
        assert CANARY_NAME not in names
        assert names - allowed <= SHELL_ADDED, (call["argv"], names - allowed)
        assert {"ANTHROPIC_API_KEY", "GH_TOKEN", "HOME", "PATH"} <= names
        assert call["home"] != os.environ["HOME"]
    # A turn the driver starts itself, not through sh, gets the allowlist and nothing more.
    for call in calls:
        if call["argv"][:1] == ["-p"]:
            assert set(call["env"]) - allowed <= PLATFORM_ADDED, call["env"]


@pytest.mark.parametrize("outcome", qc.OUTCOMES)
def test_a_fake_that_leaves_an_outcome_out_fails_the_run_naming_it(tmp_path, outcome):
    world = World(tmp_path, omit=outcome)
    done = world.full()
    assert done.returncode == 1, world.output
    expected = {name: "PASS" for name in CHECKS}
    expected[outcome] = "FAIL"
    assert statuses(done.stdout) == expected
    assert re.search(SUMMARY % (1, 0), done.stdout, re.M), done.stdout


def test_setup_left_unpushed_fails_the_precondition(tmp_path):
    world = World(tmp_path, omit=qc.SETUP_PUSHED)
    done = world.full()
    assert done.returncode == 1, world.output
    found = statuses(done.stdout)
    assert found.pop(qc.SETUP_PUSHED) == "FAIL"
    assert set(found.values()) == {"PASS"}
    assert re.search(r"FAIL setup-pushed: \d+ path\(s\) outside .adlc/specs/ are uncommitted",
                     done.stdout)


@pytest.mark.parametrize("place", ["result", "assistant"])
def test_a_no_entry_line_in_the_last_step_stands_in_for_the_lesson(tmp_path, place):
    """In the final result, or in an earlier message of the same /adlc:proceed turn."""
    world = World(tmp_path, no_entry=place)
    done = world.full()
    assert done.returncode == 0, world.output
    assert "PASS lesson-or-no-entry: the last step's transcript has the line %sNO_ENTRY: " \
           "nothing transferable" % ("- " if place == "assistant" else "") in done.stdout


def test_a_no_entry_line_from_an_earlier_step_does_not_count(tmp_path):
    world = World(tmp_path, no_entry="earlier-step")
    done = world.full()
    assert done.returncode == 1, world.output
    expected = {name: "PASS" for name in CHECKS}
    expected[qc.LESSON_OR_NO_ENTRY] = "FAIL"
    assert statuses(done.stdout) == expected
    assert "FAIL lesson-or-no-entry: no LESSON-*.md under .adlc/knowledge/lessons/, and no " \
           "line of the last step's transcript begins NO_ENTRY:" in done.stdout


def test_an_escalation_merged_to_origin_main_fails_lite_req(tmp_path):
    """/adlc:proceed escalated the REQ: origin/main's spec says full, the checkout's lite."""
    world = World(tmp_path, escalate=True)
    done = world.full("--keep")
    assert done.returncode == 1, world.output
    expected = {name: "PASS" for name in CHECKS}
    expected[qc.LITE_REQ] = "FAIL"
    assert statuses(done.stdout) == expected
    assert 'FAIL lite-req: no REQ has lane: "lite" without lane_escalated (%s has lane: ' \
           '"full" and lane_escalated on origin/main)' % fakes.REQ_DIR in done.stdout
    (kept,) = os.listdir(str(world.root))
    spec = os.path.join(str(world.root), kept, "work", "adlc-quickstart", ".adlc", "specs",
                        fakes.REQ_DIR, "requirement.md")
    assert qc.lane_of(open(spec, encoding="utf-8").read()) == qc.LITE_LANE


@pytest.mark.parametrize("after,failing", [
    ("proceed", [qc.LITE_REQ]),
    ("answer", [qc.SETUP_PUSHED, qc.LITE_REQ]),
])
def test_a_failed_fetch_of_origin_fails_the_checks_that_read_origin_main(tmp_path, after,
                                                                         failing):
    """origin points at a path that no longer exists, so the driver's fetch fails. After
    /adlc:proceed the escalation is on the real origin/main but not on the stale ref, and
    the checkout keeps the lite copy: lite-req must not pass on either."""
    world = World(tmp_path, lose_origin=after, escalate=after == "proceed")
    done = world.full()
    assert done.returncode == 1, world.output
    expected = {name: "PASS" for name in CHECKS}
    expected.update((name, "FAIL") for name in failing)
    assert statuses(done.stdout) == expected, done.stdout
    for name in failing:
        assert "FAIL %s: could not fetch origin, so origin/main is not known to be current\n" \
            % name in done.stdout, done.stdout
    assert re.search(SUMMARY % (len(failing), 0), done.stdout, re.M), done.stdout
    assert os.path.isdir(str(world.bare) + ".gone") and not os.path.exists(str(world.bare))


@pytest.mark.parametrize("args", [(), ("--with-model",), ("--throwaway-repo", REPO),
                                  ("--demo", "--throwaway-repo", REPO)])
def test_without_with_model_and_a_repo_nothing_runs(world, args):
    done = world.run(*args)
    assert done.returncode == 2, world.output
    checks = done.stderr if "--demo" in args else done.stdout
    assert statuses(checks) == {name: "SKIPPED" for name in CHECKS}
    assert ("--with-model" if "--with-model" not in args else "--throwaway-repo") in checks
    if "--demo" in args:
        assert done.stdout == ""
    assert world.claude() == [] and world.gh() == []
    assert os.listdir(str(world.root)) == []


@pytest.mark.parametrize("drop,reason", [
    (("ANTHROPIC_API_KEY",), "no model credential"),
    (("GH_TOKEN",), "GH_TOKEN is not set"),
])
def test_a_missing_credential_skips_the_run(world, drop, reason):
    done = world.full(**{name: None for name in drop})
    assert done.returncode == 2
    assert reason in done.stdout
    assert world.claude() == [] and os.listdir(str(world.root)) == []


@pytest.mark.parametrize("repo", ["acme", "acme/adlc-quickstart", "acme/e2e/x", "/acme/x-e2e",
                                  "acme/", "https://github.com/acme/x-e2e", "acme/..",
                                  "-x/y-e2e", "acme/x e2e"])
def test_throwaway_repo_must_be_owner_name_with_e2e(world, repo):
    done = world.run("--with-model", "--throwaway-repo=" + repo)
    assert done.returncode == 2
    assert done.stderr.startswith("quickstart-e2e: refused, nothing ran: --throwaway-repo"), \
        done.stderr
    assert done.stdout == ""
    assert world.claude() == [] and os.listdir(str(world.root)) == []


@pytest.mark.parametrize("args,reason", [
    (("--budget-usd", "free"), "argument --budget-usd: 'free' is not a positive number"),
    (("--no-such-option",), "unrecognized arguments: --no-such-option"),
])
def test_an_argument_error_has_the_driver_prefix(world, args, reason):
    done = world.run(*args)
    assert done.returncode == 2 and done.stdout == ""
    assert done.stderr.splitlines()[-1] == "quickstart-e2e: refused, nothing ran: " + reason
    assert world.claude() == []


def test_no_diagnostic_uses_the_underscore_prefix():
    with open(DRIVER, encoding="utf-8") as handle:
        assert "quickstart_e2e:" not in handle.read()


def test_keep_leaves_the_sandbox_and_says_where(world):
    done = world.full("--keep")
    assert done.returncode == 0, world.output
    kept = os.listdir(str(world.root))
    assert len(kept) == 1 and kept[0].startswith(qe.SANDBOX_PREFIX)
    sandbox = os.path.join(os.path.realpath(str(world.root)), kept[0])
    assert "sandbox kept: %s" % sandbox in done.stderr
    assert sorted(os.listdir(sandbox)) == ["home", "logs", "work"]
    assert "ADLC Quickstart E2E" in open(os.path.join(sandbox, "home", ".gitconfig")).read()
    assert os.path.isfile(os.path.join(sandbox, "logs", "step-8.out"))


def test_a_sandbox_root_inside_a_git_work_tree_is_refused(world, tmp_path):
    repo = tmp_path / "repo"
    subprocess.check_call(["git", "init", "-q", str(repo)])
    done = world.full(ADLC_E2E_TMPROOT=str(repo))
    assert done.returncode == 2, world.output
    assert "inside a git work tree" in done.stdout
    assert world.claude() == []
    assert os.listdir(str(repo)) == [".git"]


def test_demo_prints_each_step_as_typed_then_its_output(world):
    done = world.full("--demo")
    assert done.returncode == 0, world.output
    assert statuses(done.stdout) == {}
    assert statuses(done.stderr) == {name: "PASS" for name in CHECKS}
    lines = done.stdout.splitlines()
    typed = [line for line in lines if line.startswith(("$ ", "> "))]
    expected = []
    for step in PAGE:
        text = step.text.replace(qs.REQ_ID_PLACEHOLDER, "REQ-001")
        expected.append(("$ " if step.kind == qs.KIND_SHELL else "> ") + text)
    assert typed == expected
    # Each step's output follows it: the marketplace call's, and step 5's result text.
    assert lines[lines.index(expected[0]) + 1] == "Successfully added marketplace: adlc-toolkit"
    after_init = lines[lines.index(expected[4]) + 1]
    assert after_init.startswith("I read %s/work/adlc-quickstart/README.md" % qe.DEMO_SANDBOX)
    assert "new-project: adlc-quickstart is ready. Next: cd adlc-quickstart" in lines
    for spelled in {str(world.root), os.path.realpath(str(world.root)), str(world.tmp),
                    os.path.realpath(str(world.tmp)), os.environ["HOME"]}:
        assert spelled not in done.stdout
    assert "quickstart-e2e: step" not in done.stderr


def test_marketplace_replaces_only_the_source_in_step_1(world, tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    done = world.full("--marketplace", str(clone))
    assert done.returncode == 0, world.output
    argvs = [c["argv"] for c in world.claude()]
    words = shlex.split(PAGE[0].text)[1:]
    assert argvs[0] == words[:-1] + [str(clone)]
    assert argvs[1] == shlex.split(PAGE[1].text)[1:]
    assert [a[1] for a in turns(world.claude())][1:3] == [PAGE[5].text, PAGE[6].text]
    assert world.run("--with-model", "--throwaway-repo", REPO, "--marketplace",
                     str(tmp_path / "missing")).returncode == 2


def test_driver_reads_the_page_it_is_given(world, tmp_path):
    page = tmp_path / "page.md"
    text = open(qs.DEFAULT_PAGE, encoding="utf-8").read()
    assert PAGE[6].text.count("Ada") == 2
    page.write_text(text.replace(PAGE[6].text, PAGE[6].text.replace("Ada", "Grace")))
    done = world.full("--page", str(page))
    assert done.returncode == 0, world.output
    assert turns(world.claude())[2][1] == PAGE[6].text.replace("Ada", "Grace")


def test_req_id_with_no_spec_directory_fails_the_run(world, tmp_path):
    page = tmp_path / "page.md"
    text = open(qs.DEFAULT_PAGE, encoding="utf-8").read()
    page.write_text(text.replace(PAGE[6].text, "/adlc:status"))
    done = world.full("--page", str(page))
    assert done.returncode == 1
    assert "FAIL steps: step 8 of 8 (prompt e2e=req-id) needs the one .adlc/specs/REQ-*/ " \
           "directory the step before wrote, and found none" in done.stdout
    assert statuses(done.stdout)[qc.LITE_REQ] == "FAIL"
    assert len(turns(world.claude())) == 3


def _gone(probe, within=5.0):
    """True once ``probe`` raises ProcessLookupError; an orphan is reaped by init, not us."""
    deadline = time.monotonic() + within
    while True:
        try:
            probe()
        except ProcessLookupError:
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)


def test_a_step_that_outlives_the_timeout_is_killed_with_its_process_group(tmp_path):
    """Step 1 hangs, and so does a child the fake started: the kill reaches both."""
    world = World(tmp_path, hang="plugin marketplace add")
    done = world.full("--timeout-min", "0.015")
    assert done.returncode == 1, world.output
    assert re.search(r"FAIL steps: step 1 of 8 \(shell\) exited 124: timed out after "
                     r"0\.015 minutes and was killed", done.stdout), done.stdout
    assert statuses(done.stdout)[qc.SETUP_PUSHED] == "SKIPPED"
    pid, group, child = (int(word) for word in
                         (world.state / fakes.HANG_PID).read_text().split())
    assert group != os.getpgid(0)  # the session the driver started for the step
    assert _gone(lambda: os.killpg(group, 0)), "process group %d outlived the kill" % group
    for proc in (pid, child):
        assert _gone(lambda: os.kill(proc, 0)), "%d outlived the kill" % proc


class Clock(object):
    """An injected clock: the run's start, then its end, and nothing more."""

    def __init__(self, *ticks):
        self.ticks = list(ticks)

    def __call__(self):
        return self.ticks.pop(0)


def test_the_summary_line_says_how_long_the_run_took(world):
    """In --demo mode the summary goes to stderr with the check lines; stdout is the steps."""
    out, err, clock = io.StringIO(), io.StringIO(), Clock(1000.0, 1412.4)
    code = qe.main(["--with-model", "--throwaway-repo", REPO, "--demo"], environ=world.env,
                   stdout=out, stderr=err, clock=clock)
    assert code == 0, err.getvalue()
    assert clock.ticks == []
    assert "quickstart-e2e: 7 checks, 0 failed, 0 skipped, elapsed 7 min (412 s)\n" \
        in err.getvalue()
    assert "elapsed" not in out.getvalue() and statuses(out.getvalue()) == {}
    for secret in (MODEL_CANARY, GH_CANARY, CANARY_VALUE):
        assert secret not in out.getvalue() + err.getvalue()
    assert os.listdir(str(world.root)) == []


@pytest.mark.parametrize("elapsed,shown", [
    (0.2, "0 min (0 s)"), (59.6, "1 min (60 s)"), (60.0, "1 min (60 s)"),
    (61.0, "2 min (61 s)"), (412.4, "7 min (412 s)"), (5400.0, "90 min (5400 s)"),
])
def test_elapsed_is_whole_minutes_rounded_up_and_seconds(elapsed, shown):
    stream = io.StringIO()
    qe.report([qc.Result("a", True, "r")], stream, elapsed)
    assert stream.getvalue().splitlines()[-1] == \
        "quickstart-e2e: 1 checks, 0 failed, 0 skipped, elapsed " + shown


def test_driver_holds_no_copy_of_a_command_or_prompt():
    for path in (DRIVER, qc.__file__):
        source = open(path, encoding="utf-8").read()
        for step in PAGE:
            assert step.text not in source, (path, step.text)
            for word in shlex.split(step.text)[-1:]:
                if len(word) > 12:
                    spelled = r"(?<![\w./@-])%s(?![\w/@-])" % re.escape(word)
                    assert not re.search(spelled, source), (path, word)


def test_credentials_are_named_once_and_never_read_by_value():
    """Each credential name is one string in the driver, in its constant."""
    with open(DRIVER, encoding="utf-8") as handle:
        strings = [tok.string for tok in tokenize.generate_tokens(handle.readline)
                   if tok.type == tokenize.STRING]
    for name in qe.MODEL_CREDENTIAL_VARS + (qe.GITHUB_CREDENTIAL_VAR,):
        assert [s for s in strings if s.strip("\"'") == name] == ['"%s"' % name]
    environ = {"ANTHROPIC_API_KEY": object(), "GH_TOKEN": object(), "PATH": "/usr/bin",
               CANARY_NAME: "x", "HOME": "/elsewhere", "SSH_AUTH_SOCK": "/tmp/agent"}
    env = qe.child_env(environ, "/sandbox/home")
    assert set(env) == {"HOME", "PATH", "ANTHROPIC_API_KEY", "GH_TOKEN"}
    assert env["HOME"] == "/sandbox/home"
    assert env["ANTHROPIC_API_KEY"] is environ["ANTHROPIC_API_KEY"]
    assert env["GH_TOKEN"] is environ["GH_TOKEN"]


def test_readiness_tests_presence_only(tmp_path):
    opts = qe.parse_args(["--with-model", "--throwaway-repo", REPO])
    assert qe.readiness(opts, {"CLAUDE_CODE_OAUTH_TOKEN": "", "GH_TOKEN": ""}) is None
    assert "no model credential" in qe.readiness(opts, {"GH_TOKEN": ""})


def test_sandbox_problem_refuses_what_this_run_did_not_make(tmp_path):
    root = os.path.realpath(str(tmp_path))
    made = os.path.join(root, qe.SANDBOX_PREFIX + "abc")
    os.mkdir(made)
    assert qe.sandbox_problem(made, root, set()) is None
    assert "real home" in qe.sandbox_problem(made, root, {made})
    assert "real home" in qe.sandbox_problem(made, root, {os.path.join(made, "me")})
    assert qe.sandbox_problem(made, root, {root}) is None
    other = os.path.join(root, "other")
    os.mkdir(other)
    assert "not a directory this run made" in qe.sandbox_problem(other, root, set())
    link = os.path.join(root, qe.SANDBOX_PREFIX + "link")
    os.symlink(made, link)
    assert "not a directory" in qe.sandbox_problem(link, root, set())
    assert "not a directory this run made" in qe.sandbox_problem(made, other, set())


def _fake_sandbox(tmp_path):
    root = os.path.realpath(str(tmp_path / "root"))
    sandbox = os.path.join(root, qe.SANDBOX_PREFIX + "abc")
    os.makedirs(os.path.join(sandbox, "home"))
    return root, sandbox


def test_sandbox_removal_unlocks_a_read_only_directory_inside_it(tmp_path):
    root, sandbox = _fake_sandbox(tmp_path)
    locked = os.path.join(sandbox, "home", "cache")
    os.mkdir(locked)
    open(os.path.join(locked, "entry"), "w").close()
    os.chmod(locked, 0o500)
    err = io.StringIO()
    qe.remove_sandbox(sandbox, root, set(), err)
    assert err.getvalue() == "" and os.listdir(root) == []


def test_sandbox_removal_never_chmods_or_removes_outside_it(tmp_path, monkeypatch):
    """A symlink planted in the sandbox, pointing out of it: the error handler's chmod and
    retry would follow it, so it reports the path and leaves it."""
    root, sandbox = _fake_sandbox(tmp_path)
    outside = str(tmp_path / "outside")
    os.mkdir(outside)
    open(os.path.join(outside, "keep"), "w").close()
    os.mkdir(os.path.join(outside, "deeper"))
    os.chmod(outside, 0o500)
    os.symlink(outside, os.path.join(sandbox, "home", "link"))
    os.chmod(root, 0o755)
    # The last is the sandbox itself, whose parent is the sandbox root: outside it too.
    planted = [(os.unlink, os.path.join(sandbox, "home", "link", "keep")),
               (os.rmdir, os.path.join(sandbox, "home", "link", "deeper")),
               (os.rmdir, sandbox)]

    def rmtree(path, onerror):
        # What shutil.rmtree reports when a removal under a read-only directory fails.
        assert path == sandbox
        for func, failed in planted:
            onerror(func, failed, (OSError, OSError(13, "Permission denied"), None))

    monkeypatch.setattr(qe.shutil, "rmtree", rmtree)
    err = io.StringIO()
    try:
        qe.remove_sandbox(sandbox, root, set(), err)
        assert stat.S_IMODE(os.lstat(outside).st_mode) == 0o500
        assert stat.S_IMODE(os.lstat(root).st_mode) == 0o755
        assert sorted(os.listdir(outside)) == ["deeper", "keep"]
    finally:
        os.chmod(outside, 0o700)
    assert err.getvalue().splitlines() == [
        "quickstart-e2e: left behind, remove it yourself: %s" % path for _, path in planted]


def test_step_parsing_helpers():
    assert qe.init_prompt('claude "/adlc:x"') == "/adlc:x"
    assert qe.init_prompt('claude -p "/adlc:x"') is None
    assert qe.cd_target("cd some-dir") == "some-dir"
    assert qe.cd_target("cd a && ls") is None
    assert qe.with_marketplace("claude plugin marketplace add o/r", "/x y") == \
        "claude plugin marketplace add '/x y'"
    assert qe.with_marketplace("claude plugin install p@m", "/x") is None
    assert qe.plugin_id_of(PAGE) == shlex.split(PAGE[1].text)[-1]
    stream = '{"type":"system"}\nnot json\n{"type":"result","result":"a"}\n' \
             '{"type":"result","result":"b"}\n'
    assert qc.result_event(stream)["result"] == "b"
    assert qc.result_event("") is None


def test_scrubber_names_the_sandbox_and_redacts_credential_shapes(tmp_path):
    root = os.path.realpath(str(tmp_path))
    sandbox = os.path.join(root, qe.SANDBOX_PREFIX + "abc")
    scrub = qe.Scrubber(sandbox, root, {"HOME": "/Users/someone", "TMPDIR": root})
    text = scrub("%s/work and %s/other and /Users/someone/x ghp_%s" % (sandbox, root, "a" * 36))
    assert text.startswith("~sandbox/work and ~tmp/other and ~/x ")
    assert "ghp_" not in text and "[REDACTED]" in text
    stream = io.StringIO()
    assert qe.report([qc.Result("a", True, "r"), qc.Result("b", None, "r")], stream, 3) == 2
    assert stream.getvalue().splitlines() == [
        "PASS a: r", "SKIPPED b: r",
        "quickstart-e2e: 2 checks, 0 failed, 1 skipped, elapsed 1 min (3 s)"]
