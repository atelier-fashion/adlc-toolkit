"""The launch checklist, its drafts, and the validator that reads them (REQ-672 ADR-8, BR-5).

The real-file tests read ``docs/launch-checklist.md`` and the drafts it links, never a copy.
Every rule is also run against a broken copy of the real file, so a validator that passes
everything is caught (LESSON-019).
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

import launch_checklist as lc
import quickstart_steps as qs

SCRIPT = os.path.join(lc.HERE, "launch_checklist.py")
DOCS = os.path.dirname(lc.DEFAULT_CHECKLIST)
CHANGELOG = os.path.join(lc.TOOLKIT, "CHANGELOG.md")

#: The public repository, the one address a draft may carry before launch.
REPO_URL = "https://github.com/atelier-fashion/adlc-toolkit"
#: A link to a file on the repository's main branch, whose path must exist in this tree.
REPO_FILE_RE = re.compile(re.escape(REPO_URL) + r"/(?:blob|tree)/main/(?P<path>[^\s)\]>`]+)")
URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s)\]>`]+")
#: A link to something not yet live, written as a named slot.
SLOT_RE = re.compile(r"\[[A-Za-z]+ link, once live\]")
BY_HAND_RE = re.compile(r"^The maintainer (posts this|opens each pull request) by hand\b", re.M)
#: An adoption figure: a number next to a count of people or of platform activity, a
#: percentage, or a "12k" style count.
FIGURE_RE = re.compile(
    r"\b\d[\d,.]*\s*(?:k\b|\+)?\s*(?:stars?|forks?|downloads?|installs?|users|people|"
    r"developers|teams|companies|visitors|views|clones|upvotes?|likes)\b"
    r"|\b\d[\d,.]*\s*%|\b\d+k\b",
    re.IGNORECASE,
)
#: Words of adoption that the text to post never uses at all.
ADOPTION_WORD_RE = re.compile(
    r"\b(?:stars?|starred|stargazers|downloads?|trending|popular|adoption|adopted|used by)\b",
    re.IGNORECASE,
)
#: A duration. A draft states none: the quickstart's `quickstart-verified` line is its source.
DURATION_RE = re.compile(r"\b(?:minutes?|mins|hours?|seconds|secs)\b", re.IGNORECASE)
TEXT_BLOCK_RE = re.compile(r"^```(?:text|markdown)\n(.*?)\n```$", re.MULTILINE | re.DOTALL)
#: What X counts for any link, and so for a slot that a link replaces.
X_LINK_WEIGHT = 23
X_LIMIT = 280
HN_TITLE_LIMIT = 80
#: The three posts (the community-list pull requests are not posts to an audience).
POSTS = ("post-show-hn", "post-reddit-claudeai", "post-x")

#: The plugin line RELEASING.md step 4 puts under a released CHANGELOG heading.
PLUGIN_LINE_RE = re.compile(r"^Plugin: `adlc@adlc-toolkit` [0-9]+\.[0-9]+\.[0-9]+ ")
#: The line RELEASING.md step 9 records once the directory submission is filed.
DIRECTORY_LINE_RE = re.compile(r"^Claude directory: .+, filed [0-9]{4}-[0-9]{2}-[0-9]{2}\.$")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_real():
    return read(lc.DEFAULT_CHECKLIST)


def real_rows():
    return lc.parse(read_real())


def by_id(rows):
    return {row.id: row for row in rows}


def relative_file(target, base_dir=DOCS):
    return os.path.normpath(os.path.join(base_dir, re.split(r"[#?]", target, 1)[0]))


def edit_row(text, row_id, column, value):
    """``text`` with one cell of the row ``row_id`` replaced by ``value``."""
    index = lc.COLUMNS.index(column)
    out, hits = [], 0
    for line in text.splitlines(True):
        cells = line.strip().strip("|").split("|")
        if line.startswith("|") and len(cells) == len(lc.COLUMNS) and cells[0].strip() == row_id:
            cells = [cell.strip() for cell in cells]
            cells[index] = value
            line = "| " + " | ".join(cells) + " |\n"
            hits += 1
        out.append(line)
    assert hits == 1, "the real checklist has %d rows with id %r" % (hits, row_id)
    return "".join(out)


def drop_row(text, row_id):
    lines = text.splitlines(True)
    kept = [line for line in lines if not line.startswith("| %s |" % row_id)]
    assert len(kept) == len(lines) - 1, "the real checklist has no row %r" % row_id
    return "".join(kept)


def mirror(tmp_path, text):
    """A copy of the checklist holding ``text``, beside a copy of every file the real rows link.

    The files keep their places relative to the toolkit root, so each relative link in the
    copy resolves as it does in the real tree. Returns the copy's path.
    """
    root = tmp_path / "toolkit"
    for row in real_rows():
        target = lc.link_target(row.link)
        if target is None or lc.is_address(target):
            continue
        source = relative_file(target)
        dest = root / os.path.relpath(source, lc.TOOLKIT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, str(dest))
    path = root / "docs" / "launch-checklist.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def violations_of(path):
    return lc.validate(lc.load(path), os.path.dirname(path))


def reachable(rows, row_id):
    """Every id ``row_id`` depends on, directly or through other rows: an independent walk."""
    table = by_id(rows)
    seen, stack = set(), list(table[row_id].depends)
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack.extend(table[name].depends if name in table else ())
    return seen


def drafts():
    """``{row id: draft path}`` for every post row of the real checklist."""
    table = by_id(real_rows())
    return {row_id: relative_file(lc.link_target(table[row_id].link)) for row_id in lc.POST_IDS}


def text_blocks(text):
    return TEXT_BLOCK_RE.findall(text)


def run_cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True,
                          text=True, timeout=60)


# --- the real checklist -------------------------------------------------------------------


def test_real_checklist_has_every_required_item_in_dependency_order():
    """BR-5: every item, each depending only on rows above it, and the validator passes it."""
    rows = real_rows()
    ids = [row.id for row in rows]
    assert len(rows) >= len(lc.REQUIRED_IDS)
    assert sorted(set(ids)) == sorted(ids), "an id is used twice"
    for required in lc.REQUIRED_IDS:
        assert required in ids, "no row for %r" % required
    for position, row in enumerate(rows):
        for name in row.depends:
            assert name in ids[:position], "%s depends on %r, which is not above it" % (
                row.id, name)
    for row_id in lc.POST_IDS:
        missing = set(lc.LAUNCH_GATES) - reachable(rows, row_id)
        assert not missing, "%s does not wait for %s" % (row_id, sorted(missing))
    assert lc.validate(rows, DOCS) == []


def test_every_row_has_dependency_owner_and_status():
    """AC-6: each row names its dependencies (or none), an owner and a status."""
    text = read_real()
    rows = real_rows()
    for row in rows:
        cell = "none" if not row.depends else ", ".join(row.depends)
        assert ("| %s |" % cell) in text, "%s has an empty or malformed depends on" % row.id
        assert all(row.depends), "%s has an empty dependency name" % row.id
        assert row.owner == lc.OWNER_MAINTAINER, "%s is owned by %r" % (row.id, row.owner)
        assert row.status in lc.STATUSES, "%s has status %r" % (row.id, row.status)
        assert row.item, "%s has no item" % row.id


def test_page_states_the_decision_statuses_and_what_needs_the_maintainer():
    text = read_real()
    assert "one coordinated launch week" in text
    assert "(maintainer, 2026-11-23)" in text
    for status in lc.STATUSES:
        assert re.search(r"^- `%s`: \S" % status, text, re.M), "status %r is not defined" % status
    assert "readme-first-screen" in text
    assert "## What needs the maintainer's word" in text
    for row_id in ("readme-quickstart-verified", "demo-recording",
                   "adoption-snapshot-scheduled") + lc.POST_IDS:
        section = text.split("## What needs the maintainer's word", 1)[1]
        assert "`%s`" % row_id in section, "%s is not listed as needing the maintainer" % row_id


def test_post_rows_wait_for_the_launch_and_link_an_existing_draft():
    """AC-3: each post row reaches the four launch gates and links a draft that exists."""
    rows = real_rows()
    for row_id, path in drafts().items():
        assert os.path.dirname(path) == os.path.join(DOCS, lc.DRAFT_DIR)
        assert os.path.isfile(path), "%s links %s, which does not exist" % (row_id, path)
        assert set(lc.LAUNCH_GATES) <= reachable(rows, row_id)
        text = read(path)
        assert "`%s`" % row_id in text, "%s does not name its row %r" % (path, row_id)
        assert "](../launch-checklist.md)" in text, "%s does not link the checklist" % path


def plugin_release_in(changelog):
    """True when a released CHANGELOG entry carries RELEASING.md step 4's plugin line."""
    section = None
    for line in changelog.splitlines():
        if line.startswith("## ["):
            section = line
        elif section and "Unreleased" not in section and PLUGIN_LINE_RE.match(line):
            return True
    return False


def directory_submission_in(changelog):
    """True when the CHANGELOG records a filed directory submission (RELEASING.md step 9)."""
    return any(DIRECTORY_LINE_RE.match(line) for line in changelog.splitlines())


#: The rows whose work leaves a mark in this repository, and how to find the mark.
EVIDENCE = {
    "plugin-release": lambda: plugin_release_in(read(CHANGELOG)),
    "directory-submission": lambda: directory_submission_in(read(CHANGELOG)),
    "readme-quickstart-verified": lambda: qs.verified(read(qs.DEFAULT_PAGE)) is not None,
    "demo-recording": lambda: all(os.path.isfile(os.path.join(DOCS, name))
                                  for name in ("demo.cast", "demo.gif")),
}


def test_no_row_claims_work_the_repository_cannot_show():
    """AC-4: a row is live or done only with its mark in this tree, or its dependencies'.

    A release, a filed submission, a timed quickstart and a committed recording each leave
    a mark here. The Space, the dataset, the article, the posts, the list pull requests and
    the schedule do not; the validator holds those back instead, because a live row must
    link its address and no row is finished before the rows it depends on.
    """
    rows = real_rows()
    for row in rows:
        if row.status in lc.FINISHED and row.id in EVIDENCE:
            assert EVIDENCE[row.id](), "%s is %s, but this repository shows no sign of it" % (
                row.id, row.status)
        if row.status not in lc.FINISHED:
            target = lc.link_target(row.link)
            assert target is None or not lc.is_address(target), (
                "%s links an address while %s" % (row.id, row.status))
    assert lc.validate(rows, DOCS) == []


def test_the_release_evidence_checks_can_see_a_release():
    """The CHANGELOG checks find the lines RELEASING.md writes, so their silence means something."""
    released = ("## [Unreleased]\n\n## [9.0.0] — 2027-01-04\n\n"
                "Plugin: `adlc@adlc-toolkit` 9.0.0 (`claude plugin update adlc@adlc-toolkit`).\n"
                "Claude directory: SUB-1, filed 2027-01-05.\n")
    unreleased = "## [Unreleased]\n\nPlugin: `adlc@adlc-toolkit` 9.0.0 (`claude plugin update`).\n"
    assert plugin_release_in(released)
    assert directory_submission_in(released)
    assert not plugin_release_in(unreleased)
    assert not directory_submission_in(unreleased)


# --- the drafts ---------------------------------------------------------------------------


@pytest.mark.parametrize("row_id", lc.POST_IDS)
def test_draft_is_posted_by_hand_with_no_figure_and_no_early_link(row_id):
    """AC-5: posted by hand, no adoption figure, a slot for anything not yet live."""
    path = drafts()[row_id]
    text = read(path)
    assert BY_HAND_RE.search(text), "%s does not say the maintainer does it by hand" % path
    assert not FIGURE_RE.search(text), "%s carries a figure: %r" % (
        path, FIGURE_RE.search(text).group(0))
    for block in text_blocks(text):
        assert not ADOPTION_WORD_RE.search(block), "%s says %r in its text" % (
            path, ADOPTION_WORD_RE.search(block).group(0))
    assert not DURATION_RE.search(text), "%s states a duration" % path
    assert not re.search(r"huggingface\.co", text, re.IGNORECASE)
    for url in URL_RE.findall(text):
        assert url.startswith(REPO_URL), "%s links %s, which is not this repository" % (
            path, url)
    for match in REPO_FILE_RE.finditer(text):
        assert os.path.exists(os.path.join(lc.TOOLKIT, match.group("path"))), (
            "%s links %s, which is not in this tree" % (path, match.group("path")))


@pytest.mark.parametrize("row_id", POSTS)
def test_post_is_honest_about_its_limits(row_id):
    path = drafts()[row_id]
    text = read(path)
    posted = "\n".join(text_blocks(text))
    assert "inside Claude Code" in posted, "%s does not say it runs inside Claude Code" % path
    assert "your own Claude Code plan" in posted, "%s does not say whose plan a run uses" % path
    assert "The draft states no duration." in " ".join(text.split()), (
        "%s does not say that it states no duration" % path)
    for name in ("Space", "dataset", "article"):
        assert "[%s link, once live]" % name in posted, "%s has no %s slot" % (path, name)
    assert SLOT_RE.findall(posted)


def test_x_thread_posts_fit_in_one_post_each():
    blocks = text_blocks(read(drafts()["post-x"]))
    assert len(blocks) >= 2
    for number, block in enumerate(blocks, 1):
        weighted = len(SLOT_RE.sub("x" * X_LINK_WEIGHT, URL_RE.sub("x" * X_LINK_WEIGHT, block)))
        assert weighted <= X_LIMIT, "post %d is %d characters" % (number, weighted)


def test_show_hn_title_fits_and_starts_with_show_hn():
    text = read(drafts()["post-show-hn"])
    title = text.split("## Title", 1)[1]
    title = text_blocks(title)[0].strip()
    assert title.startswith("Show HN: ")
    assert len(title) <= HN_TITLE_LIMIT


def test_awesome_lists_names_no_list_and_leaves_slots_for_the_maintainer():
    text = read(drafts()["awesome-list-prs"])
    assert "The lists are not chosen." in text
    header = "| list | section | entry format checked | status | pull request |"
    assert header in text
    rows = [line for line in text.split(header, 1)[1].splitlines()[2:] if line.startswith("|")]
    assert rows
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert "to be chosen by the maintainer" in cells[0]
        assert cells[3] == lc.STATUS_PENDING
    for url in URL_RE.findall(text):
        assert url == REPO_URL, "the draft names a list or address: %s" % url


# --- the validator on broken copies -------------------------------------------------------


GATES_BUT_ARTICLE = "plugin-release, space, dataset, demo-recording, adoption-snapshot-scheduled"

BROKEN = [
    ("missing required id", lambda t: drop_row(t, "post-x"), [lc.RULE_MISSING_ID]),
    ("unknown status", lambda t: edit_row(t, "space", "status", "shipped"),
     [lc.RULE_UNKNOWN_STATUS]),
    ("dependency on a later row", lambda t: edit_row(t, "plugin-release", "depends on", "space"),
     [lc.RULE_LATER_DEPENDENCY]),
    ("dependency on an unknown id",
     lambda t: edit_row(t, "article", "depends on", "plugin-release, space, dataset, blog"),
     [lc.RULE_UNKNOWN_DEPENDENCY]),
    ("post row linking no draft", lambda t: edit_row(t, "post-x", "link", "none"),
     [lc.RULE_MISSING_DRAFT]),
    ("post row linking a draft that does not exist",
     lambda t: edit_row(t, "post-x", "link", "[x-thread.md](launch/x-thread-old.md)"),
     [lc.RULE_MISSING_DRAFT]),
    ("post row linking a file outside the drafts",
     lambda t: edit_row(t, "post-x", "link", "[quickstart.md](quickstart.md)"),
     [lc.RULE_MISSING_DRAFT]),
    ("post row that does not wait for the article",
     lambda t: edit_row(t, "post-x", "depends on", GATES_BUT_ARTICLE), [lc.RULE_LAUNCH_GATE]),
    ("post row owned by someone else", lambda t: edit_row(t, "post-x", "owner", "a bot"),
     [lc.RULE_POST_OWNER]),
    ("empty owner", lambda t: edit_row(t, "dataset", "owner", ""), [lc.RULE_NO_OWNER]),
    ("empty item", lambda t: edit_row(t, "dataset", "item", ""), [lc.RULE_NO_ITEM]),
    ("empty depends on", lambda t: edit_row(t, "dataset", "depends on", ""),
     [lc.RULE_EMPTY_DEPENDENCY]),
    ("none beside an id", lambda t: edit_row(t, "dataset", "depends on", "none, plugin-release"),
     [lc.RULE_UNKNOWN_DEPENDENCY]),
    ("self dependency", lambda t: edit_row(t, "dataset", "depends on", "dataset"),
     [lc.RULE_SELF_DEPENDENCY]),
    ("duplicate id", lambda t: edit_row(t, "post-x", "id", "post-reddit-claudeai"),
     [lc.RULE_DUPLICATE_ID, lc.RULE_MISSING_ID]),
    ("malformed id", lambda t: edit_row(t, "directory-submission", "id", "Directory_Submission"),
     [lc.RULE_MALFORMED_ID, lc.RULE_MISSING_ID]),
    ("done before its dependency", lambda t: edit_row(t, "directory-submission", "status", "done"),
     [lc.RULE_FINISHED_EARLY]),
    ("an address before the row is live",
     lambda t: edit_row(t, "space", "link", "[Space](https://example.invalid/space)"),
     [lc.RULE_ADDRESS_EARLY]),
    ("live with no address",
     lambda t: edit_row(edit_row(t, "plugin-release", "status", "done"), "space", "status",
                        "live"),
     [lc.RULE_LIVE_WITHOUT_ADDRESS]),
    ("a link to a file that does not exist",
     lambda t: edit_row(t, "dataset", "link", "[README](../tools/dataset/GONE.md)"),
     [lc.RULE_LINK_MISSING]),
    ("a link that is not a markdown link",
     lambda t: edit_row(t, "dataset", "link", "tools/dataset/README.md"), [lc.RULE_MALFORMED_LINK]),
]


@pytest.mark.parametrize("name, breaker, rules", BROKEN, ids=[case[0] for case in BROKEN])
def test_validator_fails_a_broken_copy(tmp_path, name, breaker, rules):
    path = mirror(tmp_path, breaker(read_real()))
    found = violations_of(path)
    assert sorted(v.rule for v in found) == sorted(rules), "\n".join(
        lc.format_violation(v) for v in found)


def test_validator_fails_a_post_row_whose_draft_file_is_gone(tmp_path):
    path = mirror(tmp_path, read_real())
    assert violations_of(path) == [], "the unbroken copy must pass"
    os.remove(os.path.join(os.path.dirname(path), lc.DRAFT_DIR, "x-thread.md"))
    found = violations_of(path)
    assert [(v.id, v.rule) for v in found] == [("post-x", lc.RULE_MISSING_DRAFT)]


def test_a_live_row_with_its_address_and_finished_dependencies_passes(tmp_path):
    text = edit_row(read_real(), "plugin-release", "status", "done")
    text = edit_row(text, "space", "status", "live")
    text = edit_row(text, "space", "link", "[Space](https://example.invalid/space)")
    assert violations_of(mirror(tmp_path, text)) == []


def test_validator_fails_on_zero_rows():
    assert [v.rule for v in lc.validate([], DOCS)] == [lc.RULE_NO_ROWS]


def test_parse_reads_only_the_table_with_the_checklist_columns():
    header = "| " + " | ".join(lc.COLUMNS) + " |"
    row = "| plugin-release | the release | none | maintainer | pending | none |"
    fenced = "```text\n%s\n|---|---|---|---|---|---|\n%s\n```\n" % (header, row)
    assert lc.parse(fenced) == []
    assert lc.parse("| id | item | owner |\n|---|---|---|\n| a | b | c |\n") == []
    rows = lc.parse(fenced + "\n" + header + "\n|---|---|---|---|---|---|\n" + row + "\n")
    assert [(r.id, r.depends, r.status) for r in rows] == [("plugin-release", (), "pending")]


@pytest.mark.parametrize("text, line", [
    ("| id | item | depends on | owner | status | link |\n| a | b |\n", 2),
    ("| id | item | depends on | owner | status | link |\n|---|---|---|---|---|---|\n"
     "| a | b | none | maintainer | pending |\n", 3),
    ("| id | item | depends on | owner | status | link |\n|---|---|---|---|---|---|\n\n"
     "| id | item | depends on | owner | status | link |\n|---|---|---|---|---|---|\n", 4),
])
def test_parse_refuses_a_malformed_table(text, line):
    with pytest.raises(lc.ChecklistError) as caught:
        lc.parse(text)
    assert caught.value.line == line


# --- the command line ---------------------------------------------------------------------


def test_cli_prints_each_row_and_the_count_on_the_real_file():
    result = run_cli()
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    rows = real_rows()
    assert lines[-1] == "launch-checklist: %d rows, 0 violations" % len(rows)
    for row in rows:
        assert any(line.startswith("%s [%s] " % (row.id, row.status)) for line in lines)


def test_cli_exits_1_and_names_each_violation(tmp_path):
    path = mirror(tmp_path, edit_row(read_real(), "space", "status", "shipped"))
    result = run_cli(path)
    assert result.returncode == 1
    assert "space: unknown-status" in result.stderr
    assert result.stdout.splitlines()[-1] == "launch-checklist: %d rows, 1 violations" % len(
        real_rows())


def test_cli_exits_1_on_a_malformed_table(tmp_path):
    path = tmp_path / "launch-checklist.md"
    path.write_text("| id | item | depends on | owner | status | link |\n| a |\n",
                    encoding="utf-8")
    result = run_cli(str(path))
    assert result.returncode == 1
    assert "refused" in result.stderr


@pytest.mark.parametrize("content", [
    "# Launch checklist\n\nNo table here.\n",
    "| id | item | depends on | owner | status | link |\n|---|---|---|---|---|---|\n",
])
def test_cli_exits_2_on_zero_rows(tmp_path, content):
    path = tmp_path / "launch-checklist.md"
    path.write_text(content, encoding="utf-8")
    result = run_cli(str(path))
    assert result.returncode == 2
    assert "0 rows" in result.stderr


def test_cli_exits_2_when_the_file_cannot_be_read(tmp_path):
    result = run_cli(str(tmp_path / "missing.md"))
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_cli_exits_2_on_extra_arguments():
    assert run_cli("a.md", "b.md").returncode == 2
