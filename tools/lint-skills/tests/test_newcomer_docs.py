"""REQ-672 BR-1, BR-10, BR-11 (ADR-9): `readme-first-screen` and `newcomer-docs`.

Each failing case is a copy of the real README, quickstart or launch checklist with one
thing broken, staged in a small toolkit tree (the plugin manifest, the three pages and a
stub `<skill>/SKILL.md` per real skill), and each sits beside a benign case that must not
fire. The real tree is held clean, and each check is shown to read files and to fail on
a tree whose pages are gone (LESSON-019).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check  # noqa: E402

FIRST = check.README_FIRST_SCREEN_CHECK
DOCS = check.NEWCOMER_DOCS_CHECK
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
QUICKSTART = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
CHECKLIST = (REPO_ROOT / "docs" / "launch-checklist.md").read_text(encoding="utf-8")
SKILLS = check._plugin_root_skill_dirs(REPO_ROOT)

INSTALL_MARKER = "<!-- first-screen: install -->"
RECORDING_BLOCK = ("<!-- first-screen: recording -->\n\n"
                   "![ADLC running the quickstart](docs/demo.gif)\n\n")


def _tree(tmp_path: Path, readme: str | None = README, quickstart: str | None = QUICKSTART,
          checklist: str | None = CHECKLIST) -> Path:
    """A toolkit root: the plugin manifest, the pages given (None leaves one out) and a
    stub SKILL.md for every real skill directory."""
    root = tmp_path / "toolkit"
    (root / ".claude-plugin").mkdir(parents=True)
    shutil.copy(REPO_ROOT / check.PLUGIN_MANIFEST, root / check.PLUGIN_MANIFEST)
    (root / "docs").mkdir()
    for rel, text in (("README.md", readme), ("docs/quickstart.md", quickstart),
                      ("docs/launch-checklist.md", checklist)):
        if text is not None:
            (root / rel).write_text(text, encoding="utf-8")
    for skill in SKILLS:
        (root / skill).mkdir()
        (root / skill / "SKILL.md").write_text(f"---\nname: {skill}\n---\n", encoding="utf-8")
    return root


def _swap(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


def _messages(scan, check_id: str) -> list[str]:
    assert all(f.check == check_id for f in scan.findings), scan.findings
    return [f.message for f in scan.findings]


def _first_screen(tmp_path: Path, **pages) -> list[str]:
    scan = check.scan_readme_first_screen(_tree(tmp_path, **pages))
    assert "README.md" in scan.scanned  # a scan that read nothing proves nothing
    return _messages(scan, FIRST)


def _newcomer(tmp_path: Path, **pages) -> list[str]:
    scan = check.scan_newcomer_docs(_tree(tmp_path, **pages))
    assert set(scan.scanned) == {"README.md", "docs/quickstart.md"}, scan.scanned
    return _messages(scan, DOCS)


def _block(text: str, name: str) -> str:
    """A marker line and everything under it, up to the next marker or `## `."""
    start = text.index(f"<!-- first-screen: {name} -->")
    nexts = [i for i in (text.find("<!-- first-screen:", start + 1), text.find("\n## ", start))
             if i != -1]
    end = min(nexts)
    return text[start:end + 1 if text[end] == "\n" else end]


def _row(text: str, row_id: str, status: str) -> str:
    """The checklist with ``row_id``'s status cell set to ``status``."""
    out, found = [], False
    for line in text.splitlines(keepends=True):
        cells = line.strip().strip("|").split("|")
        if line.startswith("|") and cells[0].strip() == row_id:
            cells[4] = f" {status} "
            line = "|" + "|".join(cells) + "|\n"
            found = True
        out.append(line)
    assert found, row_id
    return "".join(out)


#: The two launch-tools files the lint mirrors, by their whole repo-relative paths.
LAUNCH_MODULES = {
    "quickstart_steps": "tools/launch/quickstart_steps.py",
    "launch_checklist": "tools/launch/launch_checklist.py",
}

def _launch_module(name: str):
    """A launch-tools module, imported by path: the lint itself never imports it."""
    path = REPO_ROOT / LAUNCH_MODULES[name]
    spec = importlib.util.spec_from_file_location(f"{name}_for_lint", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _quickstart_steps_module():
    return _launch_module("quickstart_steps")


# --- BR-1: the first screen ------------------------------------------------------

_WHAT = _block(README, "what")
_OUTCOMES = _block(README, "outcomes")
_LESSON_ITEM = next(line for line in _OUTCOMES.splitlines() if "lesson" in line) + "\n"

BROKEN_FIRST_SCREENS = {
    "marker-missing": (lambda t: _swap(t, "<!-- first-screen: outcomes -->\n\n", ""),
                       "no `<!-- first-screen: outcomes -->` marker"),
    "markers-out-of-order": (lambda t: _swap(t, _WHAT + _OUTCOMES, _OUTCOMES + _WHAT),
                             "order outcomes, what"),
    "outcomes-of-two": (lambda t: _swap(t, _LESSON_ITEM, ""), "has 2 item(s)"),
    "outcome-not-named": (lambda t: _swap(t, "**A captured lesson.**", "**A captured note.**"),
                          "does not name a lesson"),
    "install-fence-missing-a-command": (
        lambda t: _swap(t, "claude plugin install adlc@adlc-toolkit\n```\n\nNext", "```\n\nNext"),
        "no `claude plugin install …` line"),
    "install-without-fence": (
        lambda t: _swap(t, "```bash\nclaude plugin marketplace add atelier-fashion/adlc-toolkit\n"
                           "claude plugin install adlc@adlc-toolkit\n```\n", ""),
        "holds no fenced block"),
    "recording-marker-without-gif": (lambda t: _swap(t, INSTALL_MARKER,
                                                     RECORDING_BLOCK + INSTALL_MARKER),
                                     "a `recording` marker while docs/demo.gif"),
    "skill-table-above-the-first-h2": (
        lambda t: _swap(t, "\n## Install\n", "\n### Skills\n\n| Skill | Description |\n"
                                              "|---|---|\n| `/spec` | x |\n\n## Install\n"),
        "skill table"),
    "two-sentences": (lambda t: _swap(t, "merged pull request.\n\n<!-- first-screen: outcomes",
                                      "merged pull request. It is free.\n\n<!-- first-screen: "
                                      "outcomes"), "2 sentences"),
    "marker-over-nothing": (lambda t: _swap(t, _WHAT, "<!-- first-screen: what -->\n\n"),
                            "over nothing"),
    "text-above-the-first-marker": (lambda t: _swap(t, "# ADLC Toolkit\n\n",
                                                    "# ADLC Toolkit\n\nA tagline.\n\n"),
                                    "text above the first marker"),
    # LESSON-404: a marker mentioned in prose is not a marker.
    "marker-only-mentioned": (lambda t: _swap(t, "<!-- first-screen: what -->\n",
                                              "The `<!-- first-screen: what -->` marker.\n"),
                              "no `<!-- first-screen: what -->` marker"),
    # BR-1's order puts the recording before the install commands, not after them.
    "recording-after-install": (lambda t: _swap(t, "\n## Install\n\n",
                                                "\n" + RECORDING_BLOCK + "## Install\n\n"),
                                "order what, outcomes, install, recording"),
}

BENIGN_FIRST_SCREENS = {
    "the-real-readme": lambda t: t,
    "one-sentence-with-dots-in-code-and-links": lambda t: _swap(
        t, "a merged pull request.\n", "a merged pull request (see `docs/quickstart.md` and "
                                       "[v1.2](https://example.com/a.b)).\n"),
    "outcome-item-wrapped": lambda t: _swap(t, _LESSON_ITEM, _LESSON_ITEM.replace(
        ", or gives", "\n  or gives")),
    "marker-mentioned-below-the-first-screen": lambda t: _swap(
        t, "\n## Install\n\n", "\n## Install\n\nThe `<!-- first-screen: what -->` marker.\n\n"),
}


@pytest.mark.parametrize("case", sorted(BROKEN_FIRST_SCREENS))
def test_first_screen_rules_on_broken_copies(tmp_path, case):
    """BR-1: each broken copy fails with a message naming its problem; each benign
    variant passes; and the recording is shown if and only if the pair is committed."""
    breaker, words = BROKEN_FIRST_SCREENS[case]
    root = _tree(tmp_path / "broken", readme=breaker(README))
    if case == "recording-after-install":  # the pair is there, so only the order is wrong
        (root / "docs" / "demo.gif").write_bytes(b"GIF89a")
        (root / "docs" / "demo.cast").write_text("{}\n", encoding="utf-8")
    messages = _messages(check.scan_readme_first_screen(root), FIRST)
    assert any(words in m for m in messages), messages

    for name, variant in BENIGN_FIRST_SCREENS.items():
        assert _first_screen(tmp_path / name, readme=variant(README)) == [], name

    # The recording pair: a gif with no marker fails, the marker with the pair passes.
    root = _tree(tmp_path / "gif-only")
    (root / "docs" / "demo.gif").write_bytes(b"GIF89a")
    messages = _messages(check.scan_readme_first_screen(root), FIRST)
    assert any("docs/demo.gif exists" in m and "no `recording` marker" in m
               for m in messages), messages
    root = _tree(tmp_path / "recorded", readme=_swap(README, INSTALL_MARKER,
                                                     RECORDING_BLOCK + INSTALL_MARKER))
    (root / "docs" / "demo.gif").write_bytes(b"GIF89a")
    (root / "docs" / "demo.cast").write_text("{}\n", encoding="utf-8")
    assert check.scan_readme_first_screen(root).findings == []
    # ...but not with an image of another file.
    (root / "README.md").write_text(_swap(README, INSTALL_MARKER, RECORDING_BLOCK.replace(
        "demo.gif", "other.gif") + INSTALL_MARKER), encoding="utf-8")
    messages = _messages(check.scan_readme_first_screen(root), FIRST)
    assert any("`docs/other.gif` is not a file" in m for m in messages), messages


# --- BR-10: placeholders and skill names ------------------------------------------

def _readme_line(line: str) -> str:
    return _swap(README, "\n## Install\n\n", f"\n## Install\n\n{line}\n\n")


BROKEN_PAGES = {
    "owner-placeholder": ({"readme": _readme_line(
        "Clone `https://github.com/<owner>/adlc-toolkit`.")}, "`<owner>`"),
    "your-placeholder": ({"readme": _readme_line("Sign in as <your-github-user>.")},
                         "`<your-github-user>`"),
    "owner-slash": ({"readme": _readme_line("Run `gh repo view OWNER/adlc-quickstart`.")},
                    "`OWNER/`"),
    "placeholder-in-the-quickstart": ({"quickstart": _swap(
        QUICKSTART, "account, and a directory", "account <user>, and a directory")}, "`<user>`"),
    "angle-token-in-a-marked-step": ({"quickstart": _swap(
        QUICKSTART, "new-project.sh adlc-quickstart\n```", "new-project.sh <project>\n```")},
        "the step holds `<project>`"),
    "x-run-in-a-marked-step": ({"quickstart": _swap(
        QUICKSTART, "/adlc:proceed REQ-xxx\n```", "/adlc:proceed BUG-xxx\n```")},
        "the step holds `BUG-xxx`"),
    "nonexistent-plugin-skill": ({"readme": _readme_line("Then run `/adlc:nosuchskill`.")},
                                 "`/adlc:nosuchskill` names no skill"),
    "nonexistent-plugin-skill-in-a-step": ({"quickstart": _swap(
        QUICKSTART, "/adlc:spec Add a --name", "/adlc:spce Add a --name")},
        "`/adlc:spce` names no skill"),
    "bare-nonexistent-skill-opening-a-code-span": ({"readme": _readme_line(
        "On the symlink route type `/nosuchskill REQ-001`.")}, "`/nosuchskill` names no skill"),
    "steps-differ-from-the-install-fence": ({"quickstart": _swap(
        QUICKSTART, "```sh\nclaude plugin install adlc@adlc-toolkit\n```",
        "```sh\nclaude plugin install adlc@another-market\n```")},
        "first two steps are"),
    "your-underscore-placeholder": ({"readme": _readme_line("Sign in as <your_github_user>.")},
                                    "`<your_github_user>`"),
}

#: Must not fire: tokens outside the closed set, the pinned syntax phrase, skill syntax,
#: paths, a Claude Code built-in, REQ-xxx in the last step, and every real skill name.
BENIGN_LINES = (
    "Pin a release with `git clone --branch <tag>` and `/adlc:<skill>` or `/adlc:<name>`.",
    "A flag such as `gh -R <repo> pr merge` does not match.",
    "Scripts run under `/bin/sh`, write to `/tmp`, and Codex reviews hooks with `/hooks`.",
    "The loss table spells it `/name`; an owner/maintainer decides.",
    " ".join(f"`/adlc:{s}` `/{s}`" for s in SKILLS),
    # NEWCOMER_PLACEHOLDER_RE is a closed set on purpose: `<owner>`, `<org>`, `<user>`,
    # `<username>`, `<repo>`, `<your-…>`, `<your_…>` and `OWNER/` before a name. A
    # template brace, a shell variable and an upper-case word are outside it, so these
    # pass; widening the set is a decision, not a fix.
    "Templates write `{owner}`, scripts read `$OWNER`, and YOUR_USERNAME is a word.",
)


@pytest.mark.parametrize("case", sorted(BROKEN_PAGES))
def test_placeholders_and_nonexistent_skills_fail(tmp_path, case):
    """BR-10: a closed-set placeholder, an unfilled token in a marked step, a command
    naming no skill, and steps that differ from the README's install fence each fail;
    the benign spellings beside them pass."""
    pages, words = BROKEN_PAGES[case]
    messages = _newcomer(tmp_path / "broken", **pages)
    assert any(words in m for m in messages), messages

    benign = README
    for line in BENIGN_LINES:
        benign = _swap(benign, "\n## Install\n\n", f"\n## Install\n\n{line}\n\n")
    assert _newcomer(tmp_path / "benign", readme=benign) == []
    # The real quickstart's last step carries REQ-xxx, and passes.
    assert "/adlc:proceed REQ-xxx" in QUICKSTART
    assert _newcomer(tmp_path / "real", readme=README) == []


#: The quickstart teaches the plugin install, where only `/adlc:<name>` reaches a skill
#: and a bare `/init` runs Claude Code's own built-in: a marked step, and the prompt of a
#: `claude "…"` step, never open with a bare skill name.
STEP_5 = 'claude "/adlc:init"\n```'
STEP_8 = "/adlc:proceed REQ-xxx\n```"
BROKEN_STEPS = {
    "bare-init-in-the-claude-prompt": (
        lambda t: _swap(t, STEP_5, 'claude "/init"\n```'), STEP_5,
        "the step types `/init`, a bare skill name", "write `/adlc:init`"),
    "bare-init-in-single-quotes": (
        lambda t: _swap(t, STEP_5, "claude '/init'\n```"), STEP_5,
        "the step types `/init`", "runs Claude Code's own built-in"),
    "bare-proceed-step": (
        lambda t: _swap(t, STEP_8, "/proceed REQ-xxx\n```"), STEP_8,
        "the step types `/proceed`, a bare skill name", "write `/adlc:proceed`"),
    "nonexistent-skill-in-the-claude-prompt": (
        lambda t: _swap(t, STEP_5, 'claude "/adlc:nosuchskill"\n```'), STEP_5,
        "`/adlc:nosuchskill` names no skill", "nosuchskill/SKILL.md"),
    "nonexistent-bare-name-in-the-claude-prompt": (
        lambda t: _swap(t, STEP_5, 'claude "/nosuchskill"\n```'), STEP_5,
        "`/nosuchskill` names no skill", "CLAUDE_CODE_BUILTIN_COMMANDS"),
    # The prompt is found among the arguments, wherever it sits: a flag before it does
    # not hide it, and neither does a flag with a value.
    "bare-init-after-a-flag": (
        lambda t: _swap(t, STEP_5, 'claude -p "/init"\n```'), STEP_5,
        "the step types `/init`, a bare skill name", "write `/adlc:init`"),
    "bare-proceed-after-a-flag-and-its-value": (
        lambda t: _swap(t, STEP_5, "claude --model x '/proceed REQ-xxx'\n```"), STEP_5,
        "the step types `/proceed`, a bare skill name", "write `/adlc:proceed`"),
    "bare-init-after-a-path": (
        lambda t: _swap(t, STEP_5, 'claude --add-dir /tmp "/init"\n```'), STEP_5,
        "the step types `/init`, a bare skill name", "write `/adlc:init`"),
}

#: Must not fire: the `/adlc:` spelling in either quoting or bare, after a flag or a path,
#: a `claude` subcommand, and a bare skill name in quickstart prose, which the
#: README-wide rule judges. A path is not a command: `/x/y` is not of the slash-command
#: shape, and `/tmp`, which is, names a top-level directory, not a skill.
BENIGN_STEPS = {
    "single-quoted-prompt": lambda t: _swap(t, STEP_5, "claude '/adlc:init'\n```"),
    "unquoted-prompt": lambda t: _swap(t, STEP_5, "claude /adlc:init\n```"),
    "flag-before-the-prompt": lambda t: _swap(t, STEP_5, 'claude -p "/adlc:init"\n```'),
    "root-directory-before-the-prompt": lambda t: _swap(
        t, STEP_5, 'claude --add-dir /tmp "/adlc:init"\n```'),
    "path-before-the-prompt": lambda t: _swap(
        t, STEP_5, 'claude --add-dir /x/y "/adlc:init"\n```'),
    "bare-name-in-prose": lambda t: _swap(
        t, "\n## Clean up\n", "\nOn the symlink install the same skill is `/init`.\n\n"
                               "## Clean up\n"),
}


@pytest.mark.parametrize("case", sorted(BROKEN_STEPS))
def test_marked_steps_use_the_plugin_spelling(tmp_path, case):
    """BR-10 on the plugin install: a bare skill name opening a marked step, or among the
    arguments of its `claude …` (after a flag, a flag's value or a path included), fails
    with the `/adlc:` spelling, on the step's command line, and a prompt naming no skill
    fails; the plugin spellings, paths and prose beside them pass."""
    breaker, step, *words = BROKEN_STEPS[case]
    page = breaker(QUICKSTART)
    line = QUICKSTART[:QUICKSTART.index(step)].count("\n") + 1
    scan = check.scan_newcomer_docs(_tree(tmp_path / "broken", quickstart=page))
    mine = [f for f in scan.findings if all(w in f.message for w in words)]
    assert [(f.file, f.line) for f in mine] == [("docs/quickstart.md", line)], scan.findings

    for name, variant in BENIGN_STEPS.items():
        assert _newcomer(tmp_path / name, quickstart=variant(QUICKSTART)) == [], name
    for step, commands in (
            ("claude plugin install adlc@adlc-toolkit", []),
            ('claude "/adlc:spec Add a flag"', ["/adlc:spec"]),
            ("/adlc:proceed REQ-xxx", ["/adlc:proceed"]),
            ("cd adlc-quickstart", ["cd"]),
            ('claude -p "/init"', ["/init"]),
            ("claude --model x '/proceed REQ-xxx'", ["/proceed"]),
            ('claude --add-dir /x/y "/adlc:init"', ["/adlc:init"]),
            ('claude --add-dir /tmp "/adlc:init"', ["/tmp", "/adlc:init"]),
            ('claude "/x/y is a path" /init', ["/init"])):
        assert check._step_commands(step) == commands, step


def test_owner_placeholder_and_nonexistent_skill_fixtures_fail(tmp_path):
    """AC-4: a README fixture holding `<owner>` fails the BR-10 lint, and so does a
    fixture naming a nonexistent skill, through the whole lint run."""
    for name, line, words in (
            ("owner", "claude plugin marketplace add <owner>/adlc-toolkit", "`<owner>`"),
            ("skill", "Next, run `/adlc:nosuchskill`.", "`/adlc:nosuchskill` names no skill")):
        root = _tree(tmp_path / name, readme=_readme_line(line))
        findings, _scanned = check.run(root)
        mine = [f for f in findings if f.check == DOCS]
        assert mine and any(words in f.message for f in mine), findings
        assert all(f.file == "README.md" and f.line > 1 for f in mine), mine


# --- BR-11: Hugging Face links wait for the checklist -----------------------------

HF_LINKS = {
    "space": "Try it in the [Space](https://huggingface.co/spaces/example-org/adlc).",
    "dataset": "Browse the [dataset](https://huggingface.co/datasets/example-org/adlc).",
    "article": "Read the [article](https://huggingface.co/blog/example-org/adlc).",
}


@pytest.mark.parametrize("row", sorted(HF_LINKS))
def test_hugging_face_links_need_a_live_checklist_row(tmp_path, row):
    """BR-11: a link to the Space, the dataset or the article fails while its row is
    `pending`, `done` or missing, or the checklist is; it passes once the row is `live`."""
    readme = _readme_line(HF_LINKS[row])
    words = f"`{row}` row is"
    for status in ("pending", "ready", "done"):
        messages = _first_screen(tmp_path / status, readme=readme,
                                 checklist=_row(CHECKLIST, row, status))
        assert any(words in m and f"`{status}`" in m for m in messages), (status, messages)
    messages = _first_screen(tmp_path / "no-checklist", readme=readme, checklist=None)
    assert any(words in m and "missing" in m for m in messages), messages
    # Benign: the row is live, so the link may stand; another row's status is no help.
    assert _first_screen(tmp_path / "live", readme=readme,
                         checklist=_row(CHECKLIST, row, "live")) == []
    other = next(r for r in HF_LINKS if r != row)
    messages = _first_screen(tmp_path / "other-live", readme=readme,
                             checklist=_row(CHECKLIST, other, "live"))
    assert any(words in m for m in messages), messages


def test_real_readme_has_no_hugging_face_link_while_rows_are_pending(tmp_path):
    """AC-11: the real README links no Space, dataset or article whose checklist row is
    not live, and the check reads the real checklist to say so."""
    statuses = check._checklist_statuses(REPO_ROOT / check.NEWCOMER_CHECKLIST)
    assert set(HF_LINKS) <= set(statuses), statuses  # the parser read the real rows
    kinds = {check.HF_LINK_ROWS[(m.group("kind") or m.group("host")).lower()]
             for m in check.HF_LINK_RE.finditer(README)}
    for row in HF_LINKS:
        if statuses[row] != check.CHECKLIST_LIVE:
            assert row not in kinds, f"the README links the {row} while its row is {statuses[row]}"
    scan = check.scan_readme_first_screen(REPO_ROOT)
    assert check.NEWCOMER_CHECKLIST in scan.scanned and scan.findings == []
    # Benign: with the rows live, the same links pass; a short hf.co link is one too.
    live = CHECKLIST
    for row in HF_LINKS:
        live = _row(live, row, "live")
    readme = _readme_line(" ".join(HF_LINKS.values()))
    assert _first_screen(tmp_path / "live", readme=readme, checklist=live) == []
    messages = _first_screen(tmp_path / "short", readme=_readme_line(
        "See https://hf.co/spaces/example-org/adlc."))
    assert any("`space` row is" in m for m in messages), messages


#: More shapes of a link to the Space or the dataset: a Space's own app host, and an
#: address with nothing after the id, at the end of a line or before a `)`.
HF_SHAPES = {
    "space-app-host": ("space", "Open https://example-org-adlc.hf.space to try it."),
    "space-app-host-in-a-link": ("space", "[Try it](https://example-org-adlc.HF.space/)."),
    "dataset-at-the-end-of-the-line": (
        "dataset", "The dataset: https://huggingface.co/datasets/example-org/adlc"),
    "space-before-a-paren": ("space", "(https://hf.co/spaces/example-org/adlc)"),
}


@pytest.mark.parametrize("case", sorted(HF_SHAPES))
def test_more_hugging_face_link_shapes_need_their_row(tmp_path, case):
    """BR-11: each shape fails while its row is `pending` and passes once it is `live`;
    a link to Hugging Face's own docs or a model page, and a bare mention of the
    `hf.space` domain, never fire."""
    row, line = HF_SHAPES[case]
    readme = _readme_line(line)
    messages = _first_screen(tmp_path / "pending", readme=readme)
    assert any(f"`{row}` row is `pending`" in m for m in messages), messages
    assert _first_screen(tmp_path / "live", readme=readme,
                         checklist=_row(CHECKLIST, row, "live")) == []
    benign = _readme_line("See https://huggingface.co/docs/hub/spaces-overview, "
                          "https://hf.co/example-org/model and the hf.space domain, or "
                          "https://example.hf.space.example.com.")
    assert _first_screen(tmp_path / "benign", readme=benign) == []


# --- BR-11: the lint reads the checklist as the launch tools do --------------------

def _alter_row(text: str, row_id: str, alter) -> str:
    out = [alter(line) if line.startswith(f"| {row_id} |") else line
           for line in text.splitlines(keepends=True)]
    assert out != text.splitlines(keepends=True), row_id
    return "".join(out)


_SEPARATOR = "|---|---|---|---|---|---|\n"
#: The real table and altered copies. Both parsers must read each to the same
#: `{id: status}`; where the launch tools refuse the table or read no row, the lint must
#: report that it cannot read it, never quietly read every row as not live.
ALTERED_CHECKLISTS = {
    "the-real-table": lambda t: t,
    "a-row-flipped-to-live": lambda t: _row(t, "space", "live"),
    "whitespace-backticks-and-an-escaped-pipe": lambda t: _alter_row(_alter_row(
        t, "dataset", lambda line: line.replace("| dataset |", "|   dataset   |", 1).replace(
            "Hugging Face dataset", "`Hugging Face` dataset \\| export", 1).replace(
            "| pending |", "|   live   |", 1)),
        "space", lambda line: "  " + line.replace("| pending |", "| `ready` |", 1)),
    "a-reordered-column": lambda t: _swap(t, "| owner | status | link |",
                                          "| owner | link | status |"),
    "an-extra-column": lambda t: _swap(t, "| status | link |\n", "| status | link | notes |\n"),
    "a-row-of-seven-cells": lambda t: _alter_row(
        t, "space", lambda line: line.replace("Hugging Face Space", "Hugging Face | Space", 1)),
    "no-separator": lambda t: _swap(t, _SEPARATOR, ""),
    "a-second-table": lambda t: t + "\n| id | item | depends on | owner | status | link |\n" + (
        _SEPARATOR + "| extra | x | none | maintainer | pending | none |\n"),
    "the-table-only-in-a-fence": lambda t: _swap(t, "| id | item |", "```text\n| id | item |")
    .replace("A post row moves", "```\n\nA post row moves", 1),
}


def test_checklist_reader_mirrors_the_launch_parser(tmp_path):
    """ADR-8: the lint's columns, live status, row map and reading of the table are
    tools/launch/launch_checklist.py's, on the real table and on each altered copy; a
    table the launch parser cannot read is a finding, not every row silently not live."""
    lc = _launch_module("launch_checklist")
    assert check.CHECKLIST_COLUMNS == lc.COLUMNS
    assert check.CHECKLIST_LIVE == lc.STATUS_LIVE and check.CHECKLIST_LIVE in lc.STATUSES
    assert set(check.HF_LINK_ROWS.values()) <= set(lc.REQUIRED_IDS)
    assert lc.Row._fields[1 + check.CHECKLIST_ID_COLUMN] == "id"
    assert lc.Row._fields[1 + check.CHECKLIST_STATUS_COLUMN] == "status"
    for name, alter in ALTERED_CHECKLISTS.items():
        text = alter(CHECKLIST)
        ours, problem = check._checklist_table(text)
        try:
            rows = lc.parse(text)
        except lc.ChecklistError as exc:
            assert ours == {} and problem is not None and problem[0] == exc.line, (
                name, exc, problem)
            continue
        theirs: dict[str, str] = {}
        for row in rows:
            theirs.setdefault(row.id, row.status)
        assert ours == theirs, name
        assert (problem is None) == bool(rows), (name, problem)
    whitespace = check._checklist_table(
        ALTERED_CHECKLISTS["whitespace-backticks-and-an-escaped-pipe"](CHECKLIST))[0]
    assert whitespace["dataset"] == "live" and whitespace["space"] == "`ready`", whitespace

    # Through the check: an unreadable table is a finding on the checklist; the real one
    # is not (test_real_tree_passes_both_checks).
    for name in ("a-reordered-column", "a-row-of-seven-cells"):
        scan = check.scan_readme_first_screen(_tree(
            tmp_path / name, checklist=ALTERED_CHECKLISTS[name](CHECKLIST)))
        assert [f.file for f in scan.findings] == [check.NEWCOMER_CHECKLIST], scan.findings
        assert "cannot read the launch checklist's table" in scan.findings[0].message


# --- AC-1: the real tree, and the vacuous run ------------------------------------

def test_real_tree_passes_both_checks(tmp_path, capsys):
    """AC-1: both checks pass on the real tree, say which files they read, run inside the
    lint, and fail rather than pass when the pages they read are gone."""
    first = check.scan_readme_first_screen(REPO_ROOT)
    docs = check.scan_newcomer_docs(REPO_ROOT)
    assert first.findings == [], [f.format() for f in first.findings]
    assert docs.findings == [], [f.format() for f in docs.findings]
    assert first.scanned == ("README.md", "docs/launch-checklist.md")
    assert docs.scanned == ("README.md", "docs/quickstart.md")
    findings, scanned = check.run(REPO_ROOT)
    assert scanned >= 17 and not [f for f in findings if f.check in (FIRST, DOCS)]
    err = capsys.readouterr().err
    assert "readme-first-screen: scanned 2 file(s) (README.md, docs/launch-checklist.md)" in err
    assert "newcomer-docs: scanned 2 file(s) (README.md, docs/quickstart.md)" in err

    # Pages gone from a toolkit root: each check reports it, never a quiet pass.
    root = _tree(tmp_path / "no-readme", readme=None)
    scan = check.scan_readme_first_screen(root)
    assert scan.scanned == () and [f.check for f in scan.findings] == [FIRST]
    assert "missing" in scan.findings[0].message
    assert any(f.file == "README.md" and "missing" in f.message
               for f in check.scan_newcomer_docs(root).findings)
    root = _tree(tmp_path / "no-quickstart", quickstart=None)
    scan = check.scan_newcomer_docs(root)
    assert scan.scanned == ("README.md",)
    assert any(f.file == "docs/quickstart.md" and "missing" in f.message for f in scan.findings)
    # Both pages gone, the parser still shipped: still armed.
    root = _tree(tmp_path / "no-pages", readme=None, quickstart=None)
    parser = root / LAUNCH_MODULES["quickstart_steps"]
    parser.parent.mkdir(parents=True)
    parser.write_text("", encoding="utf-8")
    assert len(check.check_newcomer_docs(root)) == 2
    assert len(check.check_readme_first_screen(root)) == 1
    # Benign: a root that is not this toolkit (no plugin manifest) is not judged.
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "README.md").write_text("# A project\n\nNo markers here.\n", encoding="utf-8")
    assert check.check_readme_first_screen(plain) == [] == check.check_newcomer_docs(plain)


def test_step_marker_mirrors_the_quickstart_parser():
    """ADR-2: the lint's one marker constant is tools/launch/quickstart_steps.py's, and the
    two read the real page to the same steps."""
    qs = _quickstart_steps_module()
    assert check.QUICKSTART_STEP_MARKER_PATTERN == qs.MARKER_PATTERN
    steps, problems = check._quickstart_steps(QUICKSTART)
    assert problems == []
    assert steps == [(s.line, s.text) for s in qs.parse(QUICKSTART)]
    assert len(steps) == qs.MAX_STEPS


_STEP_4 = "```sh\ncd adlc-quickstart\n```\n"
#: The real page and altered copies, each read by both the lint and the page's parser.
#: The kind and e2e words are left out: the parser's own tests judge those.
ALTERED_QUICKSTARTS = {
    "the-real-page": lambda t: t,
    "tilde-fences": lambda t: t.replace("```", "~~~"),
    "closing-fence-indented-three-spaces": lambda t: _swap(
        t, "adlc-toolkit\n```\n", "adlc-toolkit\n   ```\n"),
    "closing-fence-indented-four-spaces": lambda t: _swap(
        t, "adlc-toolkit\n```\n", "adlc-toolkit\n    ```\n"),
    "info-string-after-the-fence": lambda t: _swap(t, _STEP_4, _STEP_4.replace(
        "```sh", '```sh title="cd" {.copy}')),
    "backtick-in-the-info-string": lambda t: _swap(t, _STEP_4, _STEP_4.replace(
        "```sh", "```sh `cd`")),
    "marker-then-a-blank-line-then-the-fence": lambda t: _swap(t, _STEP_4, "\n" + _STEP_4),
    "marker-with-no-fence": lambda t: _swap(t, _STEP_4, "cd adlc-quickstart\n"),
    "malformed-marker": lambda t: _swap(t, "<!-- quickstart-step: answer -->",
                                        "<!-- quickstart-step answer -->"),
    "a-two-line-step": lambda t: _swap(t, _STEP_4, _STEP_4.replace("quickstart\n",
                                                                   "quickstart\nls\n")),
    "a-step-of-a-blank-line": lambda t: _swap(t, _STEP_4, "```sh\n\n```\n"),
    "a-backslash-continuation": lambda t: _swap(t, _STEP_4, "```sh\ncd \\\n```\n"),
    "a-step-fence-never-closed": lambda t: t[:t.index(STEP_8) + len(STEP_8) - 3],
    "an-unmarked-fence-never-closed": lambda t: t + "\n```text\nnotes\n",
    "a-marker-inside-an-unmarked-fence": lambda t: _swap(
        t, "\n## Clean up\n", "\n```text\n<!-- quickstart-step: shell -->\n```\n\n## Clean up\n"),
}


def test_step_fences_read_as_the_quickstart_parser_reads_them(tmp_path):
    """ADR-2: where the parser accepts a page, the lint reads the same steps; where it
    refuses one, the lint reports a finding on the line the parser names, rather than
    quietly reading fewer or different steps."""
    qs = _quickstart_steps_module()
    refused = []
    for name, alter in ALTERED_QUICKSTARTS.items():
        page = alter(QUICKSTART)
        steps, problems = check._quickstart_steps(page)
        try:
            parsed = qs.parse(page)
        except qs.QuickstartError as exc:
            assert exc.line in [line for line, _why in problems], (name, exc, problems)
            refused.append(name)
            continue
        assert problems == [], (name, problems)
        assert steps == [(s.line, s.text) for s in parsed], name
    # Each shape did what its name says, so neither branch above ran empty.
    assert set(ALTERED_QUICKSTARTS) - set(refused) == {
        "the-real-page", "tilde-fences", "closing-fence-indented-three-spaces",
        "info-string-after-the-fence", "a-marker-inside-an-unmarked-fence"}, refused
    # Through the check, a refused page is a finding on the quickstart.
    scan = check.scan_newcomer_docs(_tree(tmp_path, quickstart=ALTERED_QUICKSTARTS[
        "closing-fence-indented-four-spaces"](QUICKSTART)))
    assert any(f.file == "docs/quickstart.md" and "a step is exactly one command line"
               in f.message for f in scan.findings), scan.findings


def _hostile_lines(n: int) -> tuple[str, ...]:
    """Lines of about ``n`` characters that a backtracking pattern chokes on: a heading of
    spaces, a heading of `# ` runs, and runs of `](` and `![`."""
    return ("###" + " " * (n // 2) + "x" + " " * (n // 2) + "y",
            "## " + "# " * (n // 4) + "x" + " #" * (n // 4),
            "](" * (n // 2), "![" * (n // 2))


def _read_hostile_lines(n: int) -> None:
    for line in _hostile_lines(n):
        m = check._MD_HEADING_RE.match(line)
        if m:
            check._md_heading_title(m)
        check._code_free(line)
        list(check._IMAGE_RE.finditer(line))


def _check_hostile_readme(n: int) -> list:
    """The whole first-screen check, with a hostile heading above the first `##`."""
    readme = _swap(README, "\n## Install\n", f"\n{_hostile_lines(n)[0]}\n\n## Install\n")
    return check._first_screen_findings(readme, "README.md", REPO_ROOT, [])


def _best_of_three(run, n: int) -> float:
    times = []
    for _ in range(3):
        start = time.perf_counter()
        run(n)
        times.append(time.perf_counter() - start)
    return min(times)


#: How the time may grow from N to 4N characters. Linear is 4x and quadratic 16x; cubic,
#: what the heading pattern was (1,600 characters took 0.4 s), is 64x. The floor absorbs
#: timer noise on a fast run, and the cap is a loose bound for a loaded machine.
SMALL_N, LARGE_N = 5_000, 20_000
MAX_GROWTH, FLOOR_SECONDS, CAP_SECONDS = 40, 0.05, 10.0


def test_headings_parse_in_linear_time():
    """The heading pattern does not backtrack on a long line, and ordinary headings read
    as before; the link-target and image patterns read a long line of `](` or `![` in
    linear time too, and so does the whole check. Judged by how the time grows from
    SMALL_N to LARGE_N characters, not by a wall-clock bound a loaded machine can miss."""
    for line, want in (("## Skills", (2, "Skills")), ("### Skills ###", (3, "Skills")),
                       ("   ## Install  ", (2, "Install")), ("## C#", (2, "C#")),
                       ("##\tTabbed #  ", (2, "Tabbed")), ("#", (1, "")), ("## ##", (2, "")),
                       ("#x", None), ("####### seven", None), ("    ## code", None)):
        m = check._MD_HEADING_RE.match(line)
        got = None if m is None else (len(m.group("hashes")), check._md_heading_title(m))
        assert got == want, (line, got)
    assert all(len(line) >= SMALL_N for line in _hostile_lines(SMALL_N))
    start = time.perf_counter()
    for run in (_read_hostile_lines, _check_hostile_readme):
        small, large = _best_of_three(run, SMALL_N), _best_of_three(run, LARGE_N)
        assert large < MAX_GROWTH * small + FLOOR_SECONDS, (run.__name__, small, large)
    assert time.perf_counter() - start < CAP_SECONDS
    findings = _check_hostile_readme(SMALL_N)
    assert any("is above the first `##`" in f.message for f in findings), findings


def test_every_exception_is_used_by_the_real_pages():
    """Each built-in on the allowlist and each exempt phrase answers a real hit, so an
    entry cannot outlive the line that needed it."""
    lines = check._md_lines(README) + check._md_lines(QUICKSTART)
    firsts = {content.split()[0] for _ln, content in check._inline_code_spans(lines)
              if content.split()}
    for name in check.CLAUDE_CODE_BUILTIN_COMMANDS:
        assert f"/{name}" in firsts, name
        assert name not in SKILLS, name
    for phrase in check.NEWCOMER_PLACEHOLDER_PHRASES:
        assert phrase in README, phrase
        assert check.NEWCOMER_PLACEHOLDER_RE.search(phrase), phrase
