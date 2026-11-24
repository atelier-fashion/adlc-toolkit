"""The quickstart e2e's outcome checks over fixtures (REQ-672 BR-9, ADR-5, TASK-281).

One fixture holds every BR-9 outcome; five each lack one. The ``claude`` and ``gh`` reads
are answered by an injected runner, so no binary runs here except ``git``, which the
``setup-pushed`` cases drive in temp repositories with a local bare ``origin``.
"""
import json
import os
import subprocess

import pytest

import quickstart_check as qc

PLUGIN = "adlc@adlc-toolkit"
REPO = "acme/adlc-quickstart-e2e"
REQ_DIR = "REQ-001-greet-name"
SPEC = '---\nid: REQ-001\ntitle: "Greet a name"\n%s---\n\n## Description\n\nA change.\n'
SPEC_PATH = ".adlc/specs/%s/requirement.md" % REQ_DIR
#: What /adlc:proceed's escalation leaves in the spec's frontmatter (phases-lite.md BR-10).
ESCALATED = 'lane: "full"\nlane_escalated: \'2026-11-23 - max_files: 4 files > 3\'\n'


def write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        handle.write(text)


def stream(*events):
    """A stream-json transcript holding ``events``, one JSON object per line."""
    return "".join(json.dumps(event) + "\n" for event in events)


class Forge(object):
    """The ``run(argv, cwd)`` the checks get: canned ``claude``, ``gh`` and ``git`` answers."""

    def __init__(self, plugins=None, prs=None, lessons_on_main=None, specs_on_main=None):
        self.plugins = [{"id": PLUGIN, "version": "1.2.3", "enabled": True}] \
            if plugins is None else plugins
        self.prs = [{"number": 7, "headRefName": "feat/" + REQ_DIR}] if prs is None else prs
        self.lessons_on_main = lessons_on_main
        self.specs_on_main = specs_on_main or {}
        self.calls = []

    def __call__(self, argv, cwd):
        self.calls.append(list(argv))
        if argv == ["claude", "plugin", "list", "--json"]:
            return 0, json.dumps(self.plugins), ""
        if argv[:3] == ["gh", "pr", "list"]:
            assert argv[3:] == ["--repo", REPO, "--state", "merged", "--json",
                                "number,headRefName"]
            return 0, json.dumps(self.prs), ""
        if argv[:2] == ["git", "ls-tree"]:
            if self.lessons_on_main is None:
                return 128, "", "fatal: not a git repository"
            return 0, "\n".join(self.lessons_on_main), ""
        if argv[:2] == ["git", "show"]:
            ref, _, path = argv[2].partition(":")
            assert len(argv) == 3 and ref == "origin/main", argv
            if path in self.specs_on_main:
                return 0, self.specs_on_main[path], ""
            return 128, "", "fatal: path '%s' does not exist in 'origin/main'" % path
        raise AssertionError("unexpected call %r" % argv)


def fixture(tmp_path, omit=None, main_lane=None):
    """A project and a forge holding every outcome but ``omit``. ``main_lane`` puts a copy
    of the spec with that frontmatter on ``origin/main``; by default it is not there."""
    project = tmp_path / "adlc-quickstart"
    write(project / "README.md", "# adlc-quickstart\n")
    if omit != qc.ADLC_SCAFFOLD:
        write(project / ".adlc" / "context" / "project-overview.md", "# overview\n")
    lane = 'lane: "full"\n' if omit == qc.LITE_REQ else 'lane: "lite"\n'
    write(project / ".adlc" / "specs" / REQ_DIR / "requirement.md", SPEC % lane)
    if omit != qc.LESSON_OR_NO_ENTRY:
        write(project / ".adlc" / "knowledge" / "lessons" / "LESSON-001-greet.md", "lesson\n")
    forge = Forge(plugins=[] if omit == qc.PLUGIN_INSTALLED else None,
                  prs=[] if omit == qc.PR_MERGED else None,
                  specs_on_main=None if main_lane is None else {SPEC_PATH: SPEC % main_lane})
    return str(project), forge, "merged PR #7 from feat/%s" % REQ_DIR


def run_all(project, forge, transcript):
    """Every outcome check, after a fetch of origin that succeeded."""
    return qc.run_all(forge, project, PLUGIN, REPO, transcript, fetched=True)


def test_complete_fixture_passes_every_check(tmp_path):
    project, forge, text = fixture(tmp_path)
    results = run_all(project, forge, text)
    assert [r.name for r in results] == list(qc.OUTCOMES)
    assert all(r.ok is True for r in results), results
    # claude plugin list, gh pr list, and git show for the spec: the lesson is on disk.
    assert sorted(argv[:2] for argv in forge.calls) == [["claude", "plugin"], ["gh", "pr"],
                                                        ["git", "show"]]
    assert ["git", "show", "origin/main:" + SPEC_PATH] in forge.calls
    lite = results[2]
    assert lite.reason == '%s has lane: "lite" in the working copy, not on origin/main' % REQ_DIR


@pytest.mark.parametrize("main_lane,ok", [
    ('lane: "lite"\n', True),
    (ESCALATED, False),
    ('lane: "full"\n', False),
    ('lane: "lite"\nlane_escalated: \'2026-11-23 - forced\'\n', False),
    ("", False),
])
def test_lite_req_is_decided_by_the_copy_on_origin_main(tmp_path, main_lane, ok):
    """An escalation rewrites the spec on the feature branch and reaches origin/main with
    the PR; the project's checkout keeps the lite copy /adlc:spec wrote."""
    project, forge, text = fixture(tmp_path, main_lane=main_lane)
    results = run_all(project, forge, text)
    assert [r.name for r in results if r.ok is not True] == ([] if ok else [qc.LITE_REQ])
    lite = results[2]
    assert lite.reason.endswith("on origin/main" if ok else "on origin/main)"), lite.reason
    if main_lane == ESCALATED:
        assert lite.reason == ('no REQ has lane: "lite" without lane_escalated (%s has '
                               'lane: "full" and lane_escalated on origin/main)' % REQ_DIR)
    # Without a runner only the working copy is read, and it says lite.
    assert qc.lite_req(project).ok is True


def test_lite_req_falls_back_to_a_working_copy_that_is_escalated(tmp_path):
    project, forge, text = fixture(tmp_path)
    write(os.path.join(project, SPEC_PATH), SPEC % ESCALATED)
    lite = run_all(project, forge, text)[2]
    assert lite.ok is False
    assert lite.reason.endswith('lane: "full" and lane_escalated in the working copy, not on '
                                'origin/main)'), lite.reason


@pytest.mark.parametrize("outcome", qc.OUTCOMES)
def test_each_missing_outcome_fails_its_own_check(tmp_path, outcome):
    """BR-9: a fixture lacking one outcome fails exactly that check, with a reason."""
    project, forge, text = fixture(tmp_path, omit=outcome)
    results = run_all(project, forge, text)
    failed = [r for r in results if r.ok is not True]
    assert [r.name for r in failed] == [outcome]
    assert failed[0].ok is False and failed[0].reason


def test_checks_read_the_disk_and_the_forge_not_the_model_prose(tmp_path):
    """A final result that claims every outcome passes none of them."""
    project = tmp_path / "empty"
    project.mkdir()
    claim = ("The adlc plugin is installed, .adlc/ exists, REQ-001 has lane lite, "
             "PR #1 was merged and LESSON-001 was written.")
    results = qc.run_all(Forge(plugins=[], prs=[]), str(project), PLUGIN, REPO, claim,
                         fetched=True)
    assert [r.ok for r in results] == [False] * 5


@pytest.mark.parametrize("frontmatter,ok", [
    ('lane: "lite"\n', True),
    ('lane: "lite"   # triaged\n', True),
    ('lane: "full"\n', False),
    ("", False),
    ("lane: lite\n", False),
    ("lane: 'lite'\n", False),
    ('lane: "lite-ish"\n', False),
    ('  lane: "lite"\n', False),
])
def test_lite_req_requires_exactly_lane_lite_in_the_frontmatter(tmp_path, frontmatter, ok):
    write(tmp_path / ".adlc" / "specs" / REQ_DIR / "requirement.md", SPEC % frontmatter)
    result = qc.lite_req(str(tmp_path))
    assert result.ok is ok, result
    assert result.name == qc.LITE_REQ


def test_lite_req_ignores_a_lane_in_the_body_and_a_missing_frontmatter(tmp_path):
    write(tmp_path / ".adlc" / "specs" / REQ_DIR / "requirement.md",
          SPEC % 'lane: "full"\n' + '\nlane: "lite"\n')
    write(tmp_path / ".adlc" / "specs" / "REQ-002-x" / "requirement.md", 'lane: "lite"\n')
    result = qc.lite_req(str(tmp_path))
    assert result.ok is False
    assert 'REQ-001-greet-name has lane: "full"' in result.reason
    assert "REQ-002-x has no lane" in result.reason


def test_lite_req_without_a_req_directory_fails(tmp_path):
    (tmp_path / ".adlc" / "specs" / "notes").mkdir(parents=True)
    write(tmp_path / ".adlc" / "specs" / "REQ-003-x.md", 'lane: "lite"\n')
    assert qc.req_dirs(str(tmp_path)) == []
    result = qc.lite_req(str(tmp_path))
    assert result.ok is False and "no .adlc/specs/REQ-*/" in result.reason


def test_adlc_scaffold_needs_the_context_not_just_the_directory(tmp_path):
    (tmp_path / ".adlc" / "specs").mkdir(parents=True)
    assert qc.adlc_scaffold(str(tmp_path)).ok is False
    assert "no .adlc/ directory" in qc.adlc_scaffold(str(tmp_path / "none")).reason
    write(tmp_path / ".adlc" / "context" / "conventions.md", "x\n")
    assert qc.adlc_scaffold(str(tmp_path)).ok is True


@pytest.mark.parametrize("branch,ok", [
    ("feat/REQ-001-greet-name", True),
    ("REQ-001", True),
    ("feat/REQ-0012-other", False),
    ("feat/REQ-1001-other", False),
    ("main", False),
])
def test_pr_merged_needs_a_branch_naming_the_req(tmp_path, branch, ok):
    result = qc.pr_merged(Forge(prs=[{"number": 3, "headRefName": branch}]), str(tmp_path),
                          REPO, "REQ-001")
    assert result.ok is ok, result


def test_pr_merged_cannot_tie_a_pr_to_a_run_without_one_req(tmp_path):
    forge = Forge()
    assert qc.pr_merged(forge, str(tmp_path), REPO, None).ok is False
    assert forge.calls == []
    project, forge, text = fixture(tmp_path)
    write(os.path.join(project, ".adlc", "specs", "REQ-002-more", "requirement.md"),
          SPEC % 'lane: "lite"\n')
    merged = run_all(project, forge, text)[3]
    assert merged.name == qc.PR_MERGED and merged.ok is False
    assert "2 REQ directories" in merged.reason


@pytest.mark.parametrize("answer", [
    (1, "", "error connecting to api.github.com"),
    (0, "not json", ""),
    (0, '{"id": "adlc@adlc-toolkit"}', ""),
    (0, '["adlc@adlc-toolkit"]', ""),
])
def test_a_read_that_cannot_be_judged_fails_never_passes(tmp_path, answer):
    """LESSON-581: an answer the check was not taught is a failure with its reason."""
    def run(argv, cwd):
        return answer

    assert qc.plugin_installed(run, str(tmp_path), PLUGIN).ok is False
    assert qc.pr_merged(run, str(tmp_path), REPO, "REQ-001").ok is False
    failed = qc.plugin_installed(run, str(tmp_path), PLUGIN)
    if answer[0]:
        assert "exited 1: error connecting" in failed.reason


def test_plugin_installed_needs_the_page_plugin_enabled(tmp_path):
    other = [{"id": "other@adlc-toolkit", "enabled": True}]
    assert qc.plugin_installed(Forge(plugins=other), str(tmp_path), PLUGIN).ok is False
    disabled = [{"id": PLUGIN, "enabled": False}]
    result = qc.plugin_installed(Forge(plugins=disabled), str(tmp_path), PLUGIN)
    assert result.ok is False and "disabled" in result.reason


@pytest.mark.parametrize("text,ok", [
    ("merged\nNO_ENTRY: nothing transferable", True),
    ("### Lessons captured\n- NO_ENTRY: close-out had no run evidence", True),
    ("  `NO_ENTRY: nothing new`", True),
    ("> NO_ENTRY: quoted", True),
    ("The wrapup wrote NO_ENTRY: nothing", False),
    ("no_entry: lower case", False),
    ("NO_ENTRY without its colon", False),
    ("", False),
])
def test_no_entry_counts_only_at_the_start_of_a_line(tmp_path, text, ok):
    result = qc.lesson_or_no_entry(str(tmp_path), text)
    assert result.ok is ok, result
    as_stream = qc.lesson_or_no_entry(str(tmp_path), stream({"type": "result", "result": text}))
    assert as_stream.ok is ok, as_stream


WRAPUP = "Wrapup is done.\n\n### Lessons captured\n- NO_ENTRY: nothing transferable came out"


@pytest.mark.parametrize("event", [
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": WRAPUP}]}},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": [
            {"type": "text", "text": WRAPUP}]}]}},
])
def test_no_entry_counts_anywhere_in_the_last_step_transcript(tmp_path, event):
    """The wrapup's line may be in an earlier message of the turn, or a subagent's report,
    not in the final result: the whole stream-json transcript is read, as
    plugin-sandbox.sh reads it."""
    transcript = stream({"type": "system", "subtype": "init", "session_id": "s"}, event,
                        {"type": "result", "subtype": "success", "is_error": False,
                         "result": "merged PR #1 from feat/REQ-001-greet-name"})
    result = qc.lesson_or_no_entry(str(tmp_path), transcript)
    assert result.ok is True, result
    assert result.reason == ("the last step's transcript has the line - NO_ENTRY: nothing "
                             "transferable came out")
    mid_line = transcript.replace("- NO_ENTRY:", "it wrote NO_ENTRY:")
    assert qc.lesson_or_no_entry(str(tmp_path), mid_line).ok is False


def test_a_lesson_merged_to_origin_main_counts(tmp_path):
    run = Forge(lessons_on_main=[".adlc/knowledge/lessons/LESSON-004-greet.md"])
    result = qc.lesson_or_no_entry(str(tmp_path), "merged", run, fetched=True)
    assert result.ok is True and "origin/main" in result.reason
    assert run.calls == [["git", "ls-tree", "-r", "--name-only", "origin/main", "--",
                          ".adlc/knowledge/lessons"]]
    run = Forge(lessons_on_main=[".adlc/knowledge/lessons/README.md"])
    assert qc.lesson_or_no_entry(str(tmp_path), "merged", run, fetched=True).ok is False


#: The reason every check that reads origin/main gives when the driver's fetch failed.
NOT_FETCHED = "could not fetch origin, so origin/main is not known to be current"


def test_a_failed_fetch_fails_each_read_of_origin_main_and_reads_no_stale_ref(tmp_path):
    """origin/main says lite here, and so does the working copy: neither may pass lite-req
    once the fetch failed, since the escalation may be on the real origin/main."""
    project, forge, text = fixture(tmp_path, main_lane='lane: "lite"\n')
    results = qc.run_all(forge, project, PLUGIN, REPO, text, fetched=False)
    assert [r.name for r in results if r.ok is not True] == [qc.LITE_REQ]
    assert results[2].reason == NOT_FETCHED
    assert results[4].reason == "lesson LESSON-001-greet.md", "the lesson on disk still counts"
    assert not [argv for argv in forge.calls if argv[0] == "git"], "no stale ref was read"
    # A caller that does not say the fetch succeeded gets no pass from origin/main either.
    assert qc.lite_req(project, forge) == qc.Result(qc.LITE_REQ, False, NOT_FETCHED)

    # lesson-or-no-entry: with no lesson on disk, one only on origin/main cannot be seen.
    os.remove(os.path.join(project, ".adlc", "knowledge", "lessons", "LESSON-001-greet.md"))
    forge = Forge(lessons_on_main=[".adlc/knowledge/lessons/LESSON-004-greet.md"])
    for fetched in (False, None):
        kwargs = {} if fetched is None else {"fetched": fetched}
        result = qc.lesson_or_no_entry(project, "merged", forge, **kwargs)
        assert result.ok is False and result.reason.startswith(NOT_FETCHED + ";"), result
    assert forge.calls == []
    # The wrapup's NO_ENTRY: line reads no ref, so it still stands in for the lesson.
    assert qc.lesson_or_no_entry(project, "NO_ENTRY: nothing", forge, fetched=False).ok is True
    assert qc.lesson_or_no_entry(project, "merged", forge, fetched=True).ok is True


# ---- setup-pushed, over real git repositories --------------------------------------------

class Repo(object):
    """A project with a local bare ``origin`` and a git identity under a temp HOME."""

    def __init__(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n\tname = Check Test\n\temail = check@example.invalid\n")
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_ALLOW_PROTOCOL": "file", "LANG": "en_US.UTF-8"}
        self.origin = tmp_path / "origin.git"
        self.project = tmp_path / "project"
        self.git(str(tmp_path), "init", "-q", "--bare", str(self.origin))
        self.git(str(tmp_path), "init", "-q", "-b", "main", str(self.project))
        write(self.project / "greet.sh", "echo hi\n")
        self.git(None, "add", "-A")
        self.git(None, "commit", "-q", "-m", "start")

    def git(self, cwd, *args):
        return subprocess.run(["git"] + list(args), cwd=cwd or str(self.project), env=self.env,
                              check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout

    def push(self):
        self.git(None, "remote", "add", "origin", str(self.origin))
        self.git(None, "push", "-q", "-u", "origin", "main")

    def run(self, argv, cwd):
        done = subprocess.run(argv, cwd=cwd, env=self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        return done.returncode, done.stdout, done.stderr


def test_setup_pushed_passes_when_only_the_spec_is_left(tmp_path):
    repo = Repo(tmp_path)
    write(repo.project / ".adlc" / "context" / "project-overview.md", "x\n")
    repo.git(None, "add", "-A")
    repo.git(None, "commit", "-q", "-m", "adlc init")
    repo.push()
    assert qc.setup_pushed(repo.run, str(repo.project), fetched=True).ok is True
    write(repo.project / ".adlc" / "specs" / REQ_DIR / "requirement.md", "x\n")
    assert qc.setup_pushed(repo.run, str(repo.project), fetched=True).ok is True
    repo.git(None, "add", "-A")
    repo.git(None, "commit", "-q", "-m", "spec")
    result = qc.setup_pushed(repo.run, str(repo.project), fetched=True)
    assert result.ok is True, result


def test_setup_pushed_fails_on_uncommitted_setup(tmp_path):
    repo = Repo(tmp_path)
    repo.push()
    write(repo.project / ".adlc" / "context" / "project-overview.md", "x\n")
    result = qc.setup_pushed(repo.run, str(repo.project), fetched=True)
    assert result.ok is False
    assert ".adlc/context/project-overview.md" in result.reason


def test_setup_pushed_fails_on_a_commit_not_on_origin_main(tmp_path):
    repo = Repo(tmp_path)
    repo.push()
    write(repo.project / "CLAUDE.md", "x\n")
    repo.git(None, "add", "-A")
    repo.git(None, "commit", "-q", "-m", "adlc init")
    result = qc.setup_pushed(repo.run, str(repo.project), fetched=True)
    assert result.ok is False and "not on origin/main" in result.reason
    assert "CLAUDE.md" in result.reason


def test_setup_pushed_fails_when_main_was_never_pushed(tmp_path):
    repo = Repo(tmp_path)
    result = qc.setup_pushed(repo.run, str(repo.project), fetched=True)
    assert result.ok is False and "origin/main is not known" in result.reason
    assert qc.setup_pushed(repo.run, str(tmp_path), fetched=True).ok is False


def test_setup_pushed_fails_after_a_failed_fetch_and_reads_no_stale_ref(tmp_path):
    """The setup is committed and pushed, but origin/main is not known to be current."""
    repo = Repo(tmp_path)
    write(repo.project / ".adlc" / "context" / "project-overview.md", "x\n")
    repo.git(None, "add", "-A")
    repo.git(None, "commit", "-q", "-m", "adlc init")
    repo.push()
    calls = []

    def run(argv, cwd):
        calls.append(list(argv))
        return repo.run(argv, cwd)

    for kwargs in ({"fetched": False}, {}):
        assert qc.setup_pushed(run, str(repo.project), **kwargs) == qc.Result(
            qc.SETUP_PUSHED, False, NOT_FETCHED)
    assert not [argv for argv in calls if "origin/main" in argv], calls
    assert qc.setup_pushed(run, str(repo.project), fetched=True).ok is True
