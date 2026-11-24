"""The quickstart's sample project and ``new-project.sh`` (REQ-672 ADR-3, ADR-4).

No real ``gh`` answers any test, and nothing reaches the network. Every script runs under
``/bin/sh`` with a ``PATH`` built from a fake-binary directory and ``/usr/bin:/bin`` only
(a directory of those that holds a real ``gh`` or ``claude`` is replaced by a mirror
without it, as ``tools/adlc/tests/exec_helpers.py`` ``offline_path`` does), and each test
that expects the fake ``gh`` to run reads its log to show it did. Pushes go to a local
bare repository: the fake ``gh repo create`` adds one as ``origin``, and for
``--existing-repo`` git's ``url.<base>.insteadOf`` maps the GitHub URL onto one, with
``GIT_ALLOW_PROTOCOL=file`` so no other transport can run.
"""
import filecmp
import os
import re
import shlex
import shutil
import subprocess
import sys

import pytest

import quickstart_steps as qs

TOOLKIT = qs.TOOLKIT
EXAMPLE = os.path.join(TOOLKIT, "examples", "quickstart")
SCRIPT = os.path.join(EXAMPLE, "new-project.sh")
SAMPLE = os.path.join(EXAMPLE, "sample")
SAMPLE_FILES = ["README.md", "greet.sh", os.path.join("tests", "greet.test.sh")]
NAME = "adlc-quickstart"
#: Binaries no test may reach a real copy of.
BANNED = ("gh", "claude", "codex", "asciinema", "agg")

sys.path.insert(0, os.path.join(TOOLKIT, "tools", "adlc"))
import lane_check  # noqa: E402


def system_path(mirror_root, banned=BANNED):
    """``/usr/bin:/bin``, with any of the two that holds a ``banned`` name mirrored without it."""
    dirs = []
    for n, folder in enumerate(("/usr/bin", "/bin")):
        entries = os.listdir(folder)
        if not set(banned) & set(entries):
            dirs.append(folder)
            continue
        mirror = os.path.join(str(mirror_root), str(n))
        os.makedirs(mirror)
        for entry in entries:
            if entry not in banned:
                os.symlink(os.path.join(folder, entry), os.path.join(mirror, entry))
        dirs.append(mirror)
    return os.pathsep.join(dirs)


FAKE_GH = """#!/bin/sh
# A stand-in gh: it logs its argv, and answers the three calls new-project.sh makes.
printf '%%s\\n' "$*" >> %(log)s
case "$1 $2" in
  "auth status")
    [ -f %(signed_out)s ] && exit 1
    exit 0
    ;;
  "auth git-credential")
    cat >/dev/null
    exit 0
    ;;
  "repo create")
    [ -f %(create_fails)s ] && { echo "GraphQL: Name already exists on this account" >&2; exit 1; }
    shift 2
    src=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --source) src=$2; shift 2 ;;
        *) shift ;;
      esac
    done
    git -C "$src" remote add origin %(remote)s && git -C "$src" push -q -u origin main
    exit $?
    ;;
esac
echo "fake gh: unexpected call: $*" >&2
exit 3
"""


class World(object):
    """A work directory, a sandbox HOME with a git identity, a fake ``gh`` and a bare remote."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text(
            "[user]\n\tname = Quickstart Test\n\temail = quickstart@example.invalid\n")
        self.work = tmp_path / "work"
        self.work.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.log = tmp_path / "gh.log"
        self.remote = tmp_path / "remote.git"
        subprocess.check_call(["git", "init", "-q", "--bare", str(self.remote)])
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH % {
            "log": shlex.quote(str(self.log)),
            "signed_out": shlex.quote(str(tmp_path / "signed-out")),
            "create_fails": shlex.quote(str(tmp_path / "create-fails")),
            "remote": shlex.quote(str(self.remote)),
        })
        gh.chmod(0o755)
        self.path = os.pathsep.join([str(self.bin), system_path(tmp_path / "mirror")])
        assert shutil.which("gh", path=self.path) == str(gh)
        for name in BANNED[1:]:
            assert shutil.which(name, path=self.path) is None, name
        self.env = {"HOME": str(self.home), "PATH": self.path, "LANG": "C",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_ALLOW_PROTOCOL": "file"}

    def run(self, *args, **overrides):
        env = dict(self.env, **overrides)
        return subprocess.run(["/bin/sh", SCRIPT] + list(args), cwd=str(self.work), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def gh_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo)] + list(args), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, check=True).stdout.strip()


def tree(root):
    """Every path under ``root``, relative, so a test can show nothing changed."""
    found = []
    for folder, dirs, files in os.walk(str(root)):
        for name in dirs + files:
            found.append(os.path.relpath(os.path.join(folder, name), str(root)))
    return sorted(found)


def sample_files():
    return sorted(os.path.relpath(os.path.join(folder, name), SAMPLE)
                  for folder, _dirs, files in os.walk(SAMPLE) for name in files)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# ---- the sample -------------------------------------------------------------------------

def test_shell_scripts_parse_under_sh():
    for script in [SCRIPT] + [os.path.join(SAMPLE, rel) for rel in SAMPLE_FILES[1:]]:
        result = subprocess.run(["/bin/sh", "-n", script], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, universal_newlines=True)
        assert result.returncode == 0, (script, result.stderr)


def test_sample_test_passes_in_a_copy(tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(SAMPLE, str(copy))
    env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin", "LANG": "C"}
    for cwd, script in ((copy, "tests/greet.test.sh"),
                        (tmp_path, str(copy / "tests" / "greet.test.sh"))):
        result = subprocess.run(["/bin/sh", script], cwd=str(cwd), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.startswith("ok - ")
        assert "not ok" not in result.stdout


def test_sample_test_fails_when_greet_breaks(tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(SAMPLE, str(copy))
    (copy / "greet.sh").write_text("#!/bin/sh\nprintf '%s\\n' 'Hi'\n")
    result = subprocess.run(["/bin/sh", "tests/greet.test.sh"], cwd=str(copy),
                            env={"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin"},
                            stdout=subprocess.PIPE, universal_newlines=True)
    assert result.returncode != 0
    assert "not ok" in result.stdout


def test_sample_holds_three_files_and_nothing_the_lane_check_blocks():
    """ADR-4: no manifest, no lockfile, no SKILL.md, no blocked path."""
    assert sample_files() == sorted(SAMPLE_FILES)
    counted, failures = lane_check.evaluate([f.replace(os.sep, "/") for f in sample_files()],
                                            lane_check.effective_config())
    assert failures == []
    for folder, dirs, files in os.walk(SAMPLE):
        assert "SKILL.md" not in files
        assert ".adlc" not in dirs, "/adlc:init would ask whether to reinitialize"
    # The checks above would catch these, so show they would.
    _, failures = lane_check.evaluate(["package.json", "CLAUDE.md", ".github/workflows/ci.yml"],
                                      lane_check.effective_config())
    assert [trigger for trigger, _ in failures] == ["blocked-path", "blocked-path",
                                                    "dependency"]


def test_specified_change_stays_inside_the_lite_lane():
    """The page's change touches greet.sh, README.md and the test: two counted files."""
    config = lane_check.effective_config()
    counted, failures = lane_check.evaluate(["greet.sh", "README.md", "tests/greet.test.sh"],
                                            config)
    assert failures == []
    assert counted == 2 <= config.max_files
    step = qs.load()[6].text
    assert "greet.sh" in step and "README.md" in step


def test_sample_readme_states_name_purpose_stack_scope_and_layout():
    with open(os.path.join(SAMPLE, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    for label in ("**Name:**", "**What it does:**", "**Stack:**", "**Scope:**", "**Layout:**"):
        assert label in readme, label
    assert "sh tests/greet.test.sh" in readme


# ---- new-project.sh ---------------------------------------------------------------------

def test_new_project_makes_one_commit_on_main_and_a_private_repo(world):
    before = tree(EXAMPLE)
    result = world.run(NAME)
    assert result.returncode == 0, result.stderr
    project = world.work / NAME
    for rel in SAMPLE_FILES:
        assert filecmp.cmp(os.path.join(SAMPLE, rel), str(project / rel), shallow=False), rel
    assert world.git(project, "symbolic-ref", "--short", "HEAD") == "main"
    assert world.git(project, "rev-list", "--count", "main") == "1"
    assert world.git(project, "status", "--porcelain") == ""
    assert sorted(world.git(project, "ls-files").splitlines()) == \
        sorted(rel.replace(os.sep, "/") for rel in SAMPLE_FILES)
    calls = world.gh_calls()
    assert calls[0] == "auth status --hostname github.com"
    create = [shlex.split(call) for call in calls if call.startswith("repo create")]
    assert len(create) == 1
    argv = create[0]
    assert argv[2] == NAME
    assert "--private" in argv and "--push" in argv
    assert argv[argv.index("--source") + 1] == NAME
    # The fake pushed main to its remote: the remote holds the project's one commit.
    assert world.git(world.remote, "rev-parse", "main") == world.git(project, "rev-parse", "main")
    # Run from another directory by its absolute path, the script wrote nothing beside itself.
    assert tree(EXAMPLE) == before


def test_page_quotes_the_line_new_project_prints_last(world):
    result = world.run(NAME)
    assert result.returncode == 0, result.stderr
    last = result.stdout.splitlines()[-1]
    assert last == "new-project: %s is ready. Next: cd %s" % (NAME, NAME)
    page = open(qs.DEFAULT_PAGE, encoding="utf-8").read().splitlines()
    assert last in page
    # The directory it tells the user to enter is the one step 4 enters.
    assert last.endswith(qs.load()[3].text)


def test_existing_repo_adds_origin_and_creates_no_repo(world):
    owner_repo = "acme/adlc-e2e-quickstart"
    mirror = world.tmp / "github"
    bare = mirror / "acme" / "adlc-e2e-quickstart.git"
    bare.parent.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", "--bare", str(bare)])
    with open(str(world.home / ".gitconfig"), "a") as handle:
        handle.write('[url "file://%s/"]\n\tinsteadOf = https://github.com/\n' % mirror)
    result = world.run(NAME, "--existing-repo", owner_repo)
    assert result.returncode == 0, result.stderr
    project = world.work / NAME
    # The configured URL, as written; `remote get-url` would show it after insteadOf.
    assert world.git(project, "config", "--get", "remote.origin.url") == \
        "https://github.com/%s.git" % owner_repo
    assert world.git(bare, "rev-list", "--count", "main") == "1"
    assert world.git(bare, "rev-parse", "main") == world.git(project, "rev-parse", "main")
    calls = world.gh_calls()
    assert "auth status --hostname github.com" in calls
    assert not [call for call in calls if call.startswith("repo create")]


def test_existing_repo_checks_each_part_and_still_takes_a_valid_one(world):
    """'.', '_' and '-' inside OWNER or REPO are fine; '..' as REPO or a leading '-' is not."""
    for bad in ("owner/..", "-x/y"):
        result = world.run(NAME, "--existing-repo", bad)
        assert result.returncode == 2, (bad, result.stderr)
        assert "wants OWNER/REPO, not '%s'" % bad in result.stderr
        assert tree(world.work) == [] and world.gh_calls() == [], bad
    owner_repo = "acme-co/adlc.e2e_quick-start"
    mirror = world.tmp / "github"
    bare = mirror / "acme-co" / "adlc.e2e_quick-start.git"
    bare.parent.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", "--bare", str(bare)])
    with open(str(world.home / ".gitconfig"), "a") as handle:
        handle.write('[url "file://%s/"]\n\tinsteadOf = https://github.com/\n' % mirror)
    result = world.run(NAME, "--existing-repo", owner_repo)
    assert result.returncode == 0, result.stderr
    project = world.work / NAME
    assert world.git(project, "config", "--get", "remote.origin.url") == \
        "https://github.com/%s.git" % owner_repo
    assert world.git(bare, "rev-parse", "main") == world.git(project, "rev-parse", "main")


def test_refuses_an_existing_target_and_changes_nothing(world):
    (world.work / NAME).mkdir()
    (world.work / NAME / "keep.txt").write_text("mine\n")
    before = tree(world.work)
    result = world.run(NAME)
    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert "Nothing was changed" in result.stderr
    assert tree(world.work) == before
    assert (world.work / NAME / "keep.txt").read_text() == "mine\n"
    assert not [call for call in world.gh_calls() if call.startswith("repo create")]


@pytest.mark.parametrize("args,code,fragment", [
    ((), 2, "no project name given"),
    ((NAME, "other"), 2, "give one project name"),
    (("../escape",), 2, "not a usable project name"),
    ((".hidden",), 2, "not a usable project name"),
    (("a b",), 2, "not a usable project name"),
    ((NAME, "--private"), 2, "unknown option"),
    ((NAME, "--existing-repo"), 2, "needs OWNER/REPO"),
    ((NAME, "--existing-repo", "no-slash"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "a/b/c"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "https://github.com/a/b"), 2, "wants OWNER/REPO"),
    # Each part is checked on its own: neither may be . or .., nor start with - or .
    ((NAME, "--existing-repo", "owner/.."), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "owner/."), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "../repo"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "-x/y"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo=-x/y"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "x/-y"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "x/.y"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "/y"), 2, "wants OWNER/REPO"),
    ((NAME, "--existing-repo", "x/"), 2, "wants OWNER/REPO"),
])
def test_refuses_bad_arguments_and_creates_nothing(world, args, code, fragment):
    result = world.run(*args)
    assert result.returncode == code
    assert fragment in result.stderr
    assert tree(world.work) == []
    assert world.gh_calls() == []


def test_refuses_when_gh_is_missing(world, tmp_path):
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    os.symlink(shutil.which("git", path="/usr/bin:/bin"), str(only_git / "git"))
    result = world.run(NAME, PATH=str(only_git))
    assert result.returncode == 1
    assert "gh, the GitHub CLI, is not on PATH" in result.stderr
    assert "git is not on PATH" not in result.stderr
    assert tree(world.work) == []


def test_refuses_when_git_is_missing(world):
    result = world.run(NAME, PATH=str(world.bin))
    assert result.returncode == 1
    assert "git is not on PATH" in result.stderr
    assert "gh, the GitHub CLI" not in result.stderr
    assert tree(world.work) == []
    assert world.gh_calls() == []


def test_refuses_when_git_has_no_name_and_email(world):
    (world.home / ".gitconfig").write_text("")
    result = world.run(NAME, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.useConfigOnly",
                       GIT_CONFIG_VALUE_0="true")
    assert result.returncode == 1
    assert "git does not know your name and email" in result.stderr
    assert tree(world.work) == []
    assert world.gh_calls() == []


def test_refuses_when_gh_is_signed_out(world):
    (world.tmp / "signed-out").write_text("")
    result = world.run(NAME)
    assert result.returncode == 1
    assert "gh auth login" in result.stderr
    assert tree(world.work) == []
    assert world.gh_calls() == ["auth status --hostname github.com"]


def test_a_failed_repo_create_names_the_command_that_finishes_it(world):
    (world.tmp / "create-fails").write_text("")
    result = world.run(NAME)
    assert result.returncode == 1
    project = world.work / NAME
    assert world.git(project, "rev-list", "--count", "main") == "1"
    assert "has no GitHub remote yet" in result.stderr
    finish = re.search(r"run: (cd .*)$", result.stderr.strip())
    assert finish, result.stderr
    argv = shlex.split(finish.group(1))
    assert argv[:3] == ["cd", argv[1], "&&"]
    assert os.path.realpath(argv[1]) == os.path.realpath(str(project))
    assert argv[3:] == ["gh", "repo", "create", NAME, "--private", "--source", ".", "--push"]
