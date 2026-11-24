"""The quickstart step parser, and the real page read through it (REQ-672 ADR-2, ADR-3).

The page tests read ``docs/quickstart.md`` itself, never a copy, and each judge is also
run against a broken copy of the page so a check that passes on everything is caught
(LESSON-019).
"""
import collections
import os
import re
import subprocess
import sys

import pytest

import quickstart_steps as qs

SCRIPT = os.path.join(qs.HERE, "quickstart_steps.py")

#: ADR-3's eight steps: kind and e2e name, in order.
ADR3_STEPS = [
    (qs.KIND_SHELL, None),
    (qs.KIND_SHELL, None),
    (qs.KIND_SHELL, qs.E2E_EXISTING_REPO),
    (qs.KIND_SHELL, None),
    (qs.KIND_SHELL, qs.E2E_INIT_PROMPT),
    (qs.KIND_ANSWER, None),
    (qs.KIND_PROMPT, None),
    (qs.KIND_PROMPT, qs.E2E_REQ_ID),
]

PREREQ_HEADING = "## What you need"
#: BR-3's three needs, and how a prerequisite line names each.
TOOLS = (
    ("git", re.compile(r"(?<![\w.-])git(?![\w-])")),
    ("gh", re.compile(r"`gh`")),
    ("Claude Code", re.compile(r"\bClaude Code\b")),
)
#: What BR-3 says the quickstart never needs, and spellings that would ask for it.
FORBIDDEN_NEED_RE = re.compile(
    r"cloud|preset|deploy|delegat|\baws\b|\bgcp\b|azure|firebase|vercel|netlify|"
    r"install\.sh",
    re.IGNORECASE,
)
#: The one line allowed to name them: the sentence that says the quickstart needs none.
NOTHING_ELSE = "It needs no cloud project, no preset, no deploy target and no delegation setup."
#: What the toolkit's own scripts run with, which the prerequisites section states outside
#: the list (AC-9 as amended): the page names both, and the list stays git, gh, Claude Code.
SCRIPT_NEEDS = (
    ("python3", re.compile(r"(?<![\w.-])python3(?![\w.-])")),
    ("a POSIX shell", re.compile(r"\bPOSIX shell\b")),
)


def read_page():
    with open(qs.DEFAULT_PAGE, encoding="utf-8") as handle:
        return handle.read()


def prerequisite_section(text):
    """The lines under the prerequisites heading, up to the next heading."""
    lines = text.splitlines()
    assert PREREQ_HEADING in lines, "the page has no %r heading" % PREREQ_HEADING
    section = []
    for line in lines[lines.index(PREREQ_HEADING) + 1:]:
        if line.startswith("#"):
            break
        section.append(line)
    return section


def prerequisites(text):
    """The list items of the prerequisites section, each joined onto one line."""
    items = []
    for line in prerequisite_section(text):
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
    return items


def section_prose(text):
    """The prerequisites section's text outside its list, joined onto one line: every line
    that is neither a list item nor an indented continuation of one."""
    prose, in_item = [], False
    for line in prerequisite_section(text):
        if line.startswith("- "):
            in_item = True
        elif in_item and line.startswith("  ") and line.strip():
            continue
        else:
            in_item = False
            prose.append(line)
    return " ".join(" ".join(prose).split())


def stated_script_needs(text):
    """The SCRIPT_NEEDS the prerequisites section names outside its list."""
    prose = section_prose(text)
    return [name for name, pattern in SCRIPT_NEEDS if pattern.search(prose)]


def named_tools(items):
    """For each prerequisite item, the BR-3 needs it names."""
    return [[name for name, pattern in TOOLS if pattern.search(item)] for item in items]


def forbidden_needs(text):
    """Each place the page asks for a cloud project, preset, deploy target or delegation."""
    hits = [("step", step.line, step.text) for step in qs.parse(text)
            if FORBIDDEN_NEED_RE.search(step.text)]
    hits += [("prerequisite", None, item) for item in prerequisites(text)
             if FORBIDDEN_NEED_RE.search(item)]
    hits += [("line", number, line) for number, line in enumerate(text.splitlines(), 1)
             if FORBIDDEN_NEED_RE.search(line) and line.strip() != NOTHING_ELSE]
    return hits


def skill_names():
    return sorted(name for name in os.listdir(qs.TOOLKIT)
                  if os.path.isfile(os.path.join(qs.TOOLKIT, name, "SKILL.md")))


def run_cli(args, cwd):
    """The parser's CLI, run by path with an environment that holds no tool but the system's."""
    env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin", "LANG": "C"}
    return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=str(cwd), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)


# ---- the parser on small pages ----------------------------------------------------------

GOOD = """# A page

<!-- quickstart-step: shell -->
```sh
echo one
```

What you should see.

```sh
<!-- quickstart-step: shell -->
an example in an unmarked fence is not a step
```

<!-- quickstart-step: prompt e2e=req-id -->
```text
/adlc:proceed REQ-xxx
```

<!-- quickstart-step: answer -->
~~~
yes
~~~
"""


def line_of(text, needle):
    return text.splitlines().index(needle) + 1


def test_parse_reads_each_kind_with_its_e2e_name_and_line():
    steps = qs.parse(GOOD)
    assert steps == [
        qs.Step(qs.KIND_SHELL, "echo one", None, line_of(GOOD, "echo one")),
        qs.Step(qs.KIND_PROMPT, "/adlc:proceed REQ-xxx", qs.E2E_REQ_ID,
                line_of(GOOD, "/adlc:proceed REQ-xxx")),
        qs.Step(qs.KIND_ANSWER, "yes", None, line_of(GOOD, "yes")),
    ]


def test_parse_of_a_page_with_no_markers_is_empty_and_check_count_refuses_it():
    assert qs.parse("# Nothing to type\n\n```sh\nls\n```\n") == []
    with pytest.raises(qs.QuickstartError) as raised:
        qs.check_count([])
    assert "no marked steps" in str(raised.value)


REFUSALS = [
    ("no fence after the marker",
     "<!-- quickstart-step: shell -->\n\n```sh\nls\n```\n", 1, "not immediately followed"),
    ("a marker at the end of the page",
     "text\n<!-- quickstart-step: shell -->\n", 2, "not immediately followed"),
    ("prose after the marker",
     "<!-- quickstart-step: shell -->\nrun ls\n", 1, "not immediately followed"),
    ("two command lines",
     "<!-- quickstart-step: shell -->\n```sh\ncd x\nls\n```\n", 2, "holds 2 lines"),
    ("a command and a blank line",
     "<!-- quickstart-step: shell -->\n```sh\nls\n\n```\n", 2, "holds 2 lines"),
    ("an empty fence",
     "<!-- quickstart-step: prompt -->\n```text\n```\n", 2, "holds no command"),
    ("a backslash continuation",
     "<!-- quickstart-step: shell -->\n```sh\nls \\\n```\n", 3, "backslash"),
    ("an unknown kind",
     "<!-- quickstart-step: bash -->\n```sh\nls\n```\n", 1, "unknown step kind 'bash'"),
    ("an unknown e2e name",
     "<!-- quickstart-step: shell e2e=repo -->\n```sh\nls\n```\n", 1,
     "unknown e2e name 'repo'"),
    ("a marker with no space after the colon",
     "<!-- quickstart-step:shell -->\n```sh\nls\n```\n", 1, "malformed"),
    ("an indented marker",
     "  <!-- quickstart-step: shell -->\n```sh\nls\n```\n", 1, "malformed"),
    ("an extra word in the marker",
     "<!-- quickstart-step: shell now -->\n```sh\nls\n```\n", 1, "malformed"),
    ("a step fence that never closes",
     "<!-- quickstart-step: shell -->\n```sh\nls\n", 2, "never closed"),
    ("an unmarked fence that never closes",
     "```sh\nls\n<!-- quickstart-step: shell -->\n```sh\nls\n", 1, "never closed"),
]


@pytest.mark.parametrize("text,line,fragment", [r[1:] for r in REFUSALS],
                         ids=[r[0] for r in REFUSALS])
def test_parse_refuses_with_the_line(text, line, fragment):
    with pytest.raises(qs.QuickstartError) as raised:
        qs.parse(text)
    assert raised.value.line == line
    assert fragment in str(raised.value)
    assert str(raised.value).startswith("line %d: " % line)


def test_check_count_allows_eight_and_refuses_nine_naming_the_ninth():
    block = "<!-- quickstart-step: shell -->\n```sh\nstep %d\n```\n\n"
    eight = qs.parse("".join(block % n for n in range(1, 9)))
    qs.check_count(eight)
    nine = qs.parse("".join(block % n for n in range(1, 10)))
    with pytest.raises(qs.QuickstartError) as raised:
        qs.check_count(nine)
    assert raised.value.line == nine[8].line
    assert "9 steps" in str(raised.value)


# ---- the timing marker ------------------------------------------------------------------

def test_verified_reads_both_forms():
    assert qs.verified("x\n<!-- quickstart-verified: none -->\n") is None
    record = qs.verified("<!-- quickstart-verified: release=5.4.0 minutes=6 date=2026-12-01 -->\n")
    assert record == qs.Verified("5.4.0", 6, "2026-12-01")


@pytest.mark.parametrize("text,fragment", [
    ("no marker here\n", "no quickstart-verified marker"),
    ("```\n<!-- quickstart-verified: none -->\n```\n", "no quickstart-verified marker"),
    ("<!-- quickstart-verified: none -->\n<!-- quickstart-verified: none -->\n", "second"),
    ("<!-- quickstart-verified: NONE -->\n", "malformed"),
    ("<!-- quickstart-verified: unknown -->\n", "malformed"),
    ("<!-- quickstart-verified: release=5.4 minutes=6 date=2026-12-01 -->\n", "malformed"),
    ("<!-- quickstart-verified: release=5.4.0 minutes=0 date=2026-12-01 -->\n", "malformed"),
    ("<!-- quickstart-verified: release=5.4.0 minutes=five date=2026-12-01 -->\n", "malformed"),
    ("<!-- quickstart-verified: release=5.4.0 minutes=6 -->\n", "malformed"),
    ("<!-- quickstart-verified: release=5.4.0 minutes=6 date=2026-12-01 by=me -->\n",
     "malformed"),
    ("<!-- quickstart-verified: release=5.4.0 minutes=6 date=2026-13-01 -->\n",
     "not a calendar date"),
])
def test_verified_rejects_any_other_marker(text, fragment):
    with pytest.raises(qs.QuickstartError) as raised:
        qs.verified(text)
    assert fragment in str(raised.value)


def test_timing_sentence_says_not_measured_or_the_measured_run():
    assert qs.timing_sentence(None) == qs.NOT_MEASURED
    assert "not been measured" in qs.NOT_MEASURED
    assert qs.timing_sentence(qs.Verified("5.4.0", 6, "2026-12-01")) == \
        "Timing: a run took 6 minutes on release 5.4.0, measured on 2026-12-01."
    assert "took 1 minute on" in qs.timing_sentence(qs.Verified("5.4.0", 1, "2026-12-01"))


# ---- the real page ----------------------------------------------------------------------

def test_default_page_is_the_real_page_beside_this_toolkit():
    assert qs.DEFAULT_PAGE == os.path.join(qs.TOOLKIT, "docs", "quickstart.md")
    assert os.path.isfile(os.path.join(qs.TOOLKIT, "tools", "launch", "quickstart_steps.py"))
    assert qs.load() == qs.parse(read_page())


def test_real_page_has_the_eight_steps_in_order():
    """BR-2: install to merged REQ through /adlc:init, /adlc:spec and /adlc:proceed (ADR-3)."""
    text = read_page()
    steps = qs.load()
    assert [(step.kind, step.e2e) for step in steps] == ADR3_STEPS
    commands = [step.text for step in steps]
    assert commands[0] == "claude plugin marketplace add atelier-fashion/adlc-toolkit"
    assert commands[1] == "claude plugin install adlc@adlc-toolkit"
    # Step 3 runs the script from the marketplace's copy of this repository, so the part
    # of its path below the marketplace directory must name the script in this tree.
    match = re.match(r"^sh ~/\S+/plugins/marketplaces/adlc-toolkit/(\S+) adlc-quickstart$",
                     commands[2])
    assert match, commands[2]
    assert match.group(1) == "examples/quickstart/new-project.sh"
    assert os.path.isfile(os.path.join(qs.TOOLKIT, *match.group(1).split("/")))
    assert commands[3] == "cd adlc-quickstart"
    assert commands[4] == 'claude "/adlc:init"'
    assert "README.md" in commands[5] and "no sibling repos" in commands[5]
    assert commands[6].startswith("/adlc:spec Add a --name option to greet.sh ")
    for part in ('"sh greet.sh --name Ada"', '"Hello, Ada"', "README.md"):
        assert part in commands[6]
    assert commands[7] == "/adlc:proceed " + qs.REQ_ID_PLACEHOLDER
    assert "You type eight things in all: five shell commands, one reply and two prompts." \
        in " ".join(text.split())


def test_real_page_has_eight_or_fewer_typed_steps():
    """AC-3: shell, prompt and answer all count, and the real page is within the limit."""
    steps = qs.load()
    qs.check_count(steps)
    kinds = collections.Counter(step.kind for step in steps)
    assert set(kinds) <= set(qs.KINDS)
    assert sum(kinds.values()) == len(steps) <= qs.MAX_STEPS
    # Every marker on the page is a counted step, the answer's included: none is skipped.
    markers = [line for line in read_page().splitlines() if line.startswith(qs.MARKER_PREFIX)]
    assert len(markers) == len(steps)
    assert kinds[qs.KIND_ANSWER] >= 1
    # One more typed thing of any kind takes the page over the limit.
    for kind in qs.KINDS:
        nine = read_page() + "\n<!-- quickstart-step: %s -->\n```text\none more\n```\n" % kind
        with pytest.raises(qs.QuickstartError):
            qs.check_count(qs.parse(nine))


def test_prerequisites_name_only_git_gh_and_claude_code():
    """BR-3: the prerequisites are git, gh signed in, and Claude Code, and nothing else."""
    text = read_page()
    items = prerequisites(text)
    assert named_tools(items) == [["git"], ["gh"], ["Claude Code"]], items
    assert "signed in" in items[1]
    # Broken copies: an extra need, a missing one, and two in one line all fail.
    for old, new in [
        ("- Claude Code, signed in\n", "- Claude Code, signed in\n- Node.js 20\n"),
        ("- git\n", ""),
        ("- git\n", "- git and Claude Code\n"),
    ]:
        broken = text.replace(old, new)
        assert broken != text
        assert named_tools(prerequisites(broken)) != [["git"], ["gh"], ["Claude Code"]]


def test_no_step_needs_cloud_preset_deploy_or_delegation():
    """AC-9: no step, prerequisite or sentence asks for any of the four."""
    text = read_page()
    assert forbidden_needs(text) == []
    assert NOTHING_ELSE in prerequisite_section(text)
    for old, new in [
        ("- Claude Code, signed in\n", "- Claude Code, signed in\n- a Google Cloud project\n"),
        ("- git\n", "- git, and the toolkit's preset for your stack\n"),
        ("and add one line to README.md that documents it", "and deploy it"),
        ('claude "/adlc:init"', 'claude "/adlc:init" with delegation on'),
        ("Nothing is printed.", "Then set up your deploy target."),
    ]:
        broken = text.replace(old, new)
        assert broken != text
        assert forbidden_needs(broken), new


def test_page_states_the_python3_and_posix_shell_the_scripts_need():
    """AC-9 as amended: the "What you need" section states, outside its list, the `python3`
    and the POSIX shell the toolkit's scripts need; the list itself stays git, gh and
    Claude Code (test_prerequisites_name_only_git_gh_and_claude_code)."""
    text = read_page()
    assert stated_script_needs(text) == [name for name, _ in SCRIPT_NEEDS], section_prose(text)
    assert named_tools(prerequisites(text)) == [["git"], ["gh"], ["Claude Code"]]
    # Broken copies: the sentence removed, one need dropped from it, and the sentence
    # moved into the list each fail.
    sentence = re.search(r"The toolkit's own scripts run with[^\n]*(?:\n[^\n]+)*\n\n", text)
    assert sentence, "the page has no sentence on what the toolkit's scripts run with"
    moved = "- Claude Code, signed in\n- " + " ".join(sentence.group(0).split()) + "\n"
    for broken in (
        text.replace(sentence.group(0), ""),
        text.replace("`python3` and a POSIX shell", "a POSIX shell"),
        text.replace("`python3` and a POSIX shell", "`python3`"),
        text.replace(sentence.group(0), "").replace("- Claude Code, signed in\n", moved),
    ):
        assert broken != text
        assert stated_script_needs(broken) != [name for name, _ in SCRIPT_NEEDS], broken


def test_each_step_is_followed_by_what_you_should_see():
    lines = read_page().splitlines()
    for step in qs.load():
        after = []
        # The command is on step.line and the fence closes on the next line.
        for line in lines[step.line + 1:]:
            if line.startswith("#") or line.startswith(qs.MARKER_PREFIX):
                break
            after.append(line)
        prose = [line for line in after if line.strip() and not line.startswith("```")]
        assert prose, "step on line %d has no text after it" % step.line


def test_page_shows_the_questions_and_says_to_use_the_printed_id():
    text = read_page()
    steps = qs.load()
    lines = text.splitlines()
    before_answer = "\n".join(lines[steps[4].line:steps[5].line])
    for asked in ("trust", "confirm", "sibling repos", "approve"):
        assert asked in before_answer, asked
    before_proceed = " ".join("\n".join(lines[steps[6].line:steps[7].line]).split())
    assert "`REQ-xxx` replaced by the id `/adlc:spec` printed" in before_proceed


def test_page_names_every_skill_with_the_adlc_prefix():
    """No bare /<skill>: on the plugin install a bare /init reaches Claude Code's own."""
    text = read_page()
    names = skill_names()
    assert "init" in names and "proceed" in names
    bare = re.compile(r"(?<![\w:/.~-])/(%s)(?![\w/-])" % "|".join(map(re.escape, names)))
    assert bare.findall(text) == []
    prefixed = re.findall(r"/adlc:([a-z][a-z-]*)", text)
    assert {"init", "spec", "proceed"} <= set(prefixed)
    assert set(prefixed) <= set(names)
    assert bare.findall("run `/init` first") == ["init"]


def test_timing_sentence_and_unchecked_section_match_the_marker():
    text = read_page()
    record = qs.verified(text)
    assert qs.timing_sentence(record) in text
    assert (record is None) == ("## What has not been checked" in text)


# ---- the command line -------------------------------------------------------------------

def test_cli_lists_the_real_page_from_any_directory(tmp_path):
    result = run_cli([], tmp_path)
    assert result.returncode == 0, result.stderr
    out = result.stdout.splitlines()
    steps = qs.load()
    assert out[:len(steps)] == [
        "%d. [%s] %s" % (n, s.kind if s.e2e is None else "%s e2e=%s" % (s.kind, s.e2e), s.text)
        for n, s in enumerate(steps, 1)]
    assert out[len(steps)] == "steps=%d" % len(steps)
    assert out[len(steps) + 1].startswith("verified=")


def test_cli_refuses_a_broken_page_with_its_line(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("<!-- quickstart-verified: none -->\n\n"
                    "<!-- quickstart-step: shell -->\n```sh\ncd x\nls\n```\n")
    result = run_cli([str(page)], tmp_path)
    assert result.returncode == 1
    assert "refused: line 4: " in result.stderr
    assert result.stdout == ""


def test_cli_refuses_a_page_with_no_steps_or_no_timing_marker(tmp_path):
    no_steps = tmp_path / "empty.md"
    no_steps.write_text("<!-- quickstart-verified: none -->\n")
    assert run_cli([str(no_steps)], tmp_path).returncode == 1
    no_marker = tmp_path / "unmarked.md"
    no_marker.write_text("<!-- quickstart-step: shell -->\n```sh\nls\n```\n")
    result = run_cli([str(no_marker)], tmp_path)
    assert result.returncode == 1
    assert "no quickstart-verified marker" in result.stderr


def test_cli_exits_2_when_the_page_cannot_be_read(tmp_path):
    result = run_cli([str(tmp_path / "missing.md")], tmp_path)
    assert result.returncode == 2
    assert "cannot read" in result.stderr
