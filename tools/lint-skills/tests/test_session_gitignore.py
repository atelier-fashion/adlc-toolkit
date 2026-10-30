"""REQ-660 BR-7, BR-15 / AC-12: `session-gitignore`.

`.adlc/.session/` stays in the gitignore lines `/init` writes, so a session
sidecar cannot start leaking into consumer commits through a later edit. The
check reads `init/SKILL.md`'s `### Step 5` section only, and wants the entry as
a whole line inside a fence there.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"
SITE = "init/SKILL.md"
LINE = ".adlc/.session/"

_spec = importlib.util.spec_from_file_location("lint_check_session_gitignore", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_session_gitignore"] = _check
_spec.loader.exec_module(_check)

INIT_TEXT = (REPO_ROOT / SITE).read_text(encoding="utf-8")


def _skill(step5_body: str, after: str = "") -> str:
    return ("# /init\n\n### Step 4: Before\n\nText.\n\n### Step 5: Update .gitignore\n"
            f"{step5_body}\n\n### Step 6: After\n\n{after}\n")


def _fence(*entries: str) -> str:
    return "\n".join(("```", *entries, "```"))


def _findings(text: str) -> list:
    return _check.check_session_gitignore_line(text)


def _delete_line(text: str) -> str:
    """The real file with the entry gone. Raises if the entry is not there, so a
    fixture cannot go stale into a test that proves nothing."""
    assert f"\n{LINE}\n" in text
    return text.replace(f"\n{LINE}\n", "\n", 1)


def _plugin_root(tmp_path: Path, text: str | None) -> Path:
    (tmp_path / "VERSION").write_text("0.0.0\n")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "SKILL.md").write_text("# /x\n")
    if text is not None:
        (tmp_path / "init").mkdir()
        (tmp_path / "init" / "SKILL.md").write_text(text)
    return tmp_path


def _lint(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), "--root", str(root)],
                          capture_output=True, text=True, check=False)


def _hits(out: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in out.stdout.splitlines() if ": session-gitignore:" in ln]


# --- the real tree -----------------------------------------------------------

def test_real_tree_passes():
    """BR-7 on the real tree, and not vacuously: the check reads the real site,
    and this repo's own `.gitignore` carries the line it does not read."""
    assert _check.check_session_gitignore(REPO_ROOT) == []
    assert _check.is_plugin_root(REPO_ROOT)
    assert _check.check_session_gitignore_line(INIT_TEXT) == []
    assert _check.SESSION_GITIGNORE_SITE == SITE
    assert _check.SESSION_GITIGNORE_LINE == LINE
    assert LINE in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_missing_line_names_file(tmp_path):
    """BR-15, AC-12: deleting the line from the real `/init` source fails the CLI,
    naming the file, and nothing else about the file changes."""
    found = _findings(_delete_line(INIT_TEXT))
    assert [(f.file, f.check) for f in found] == [(SITE, "session-gitignore")]
    assert INIT_TEXT.splitlines()[found[0].line - 1].startswith("### Step 5")
    out = _lint(_plugin_root(tmp_path, _delete_line(INIT_TEXT)))
    assert out.returncode != 0
    assert len(_hits(out)) == 1 and _hits(out)[0].startswith(f"{SITE}:"), out.stdout


def test_step_six_and_the_sync_block_are_intact():
    """The tests of other checks anchor on both."""
    assert "\n### Step 6: Copy ETHOS.md and Templates Into the Project\n" in INIT_TEXT
    assert "<!-- sync-surfaces: init -->" in INIT_TEXT
    assert "<!-- /sync-surfaces -->" in INIT_TEXT


# --- what satisfies the check, and the decoys that must not (LESSON-404) ------

def test_entry_in_the_fence_passes():
    assert _findings(_skill(_fence(LINE))) == []


def test_comment_lines_in_the_fence_do_not_end_the_section():
    """The block's gitignore comments look like level-1 headings; only one outside
    a fence ends the section."""
    assert _findings(_skill(_fence("# A comment", ".worktrees/", "", "# Another", LINE))) == []


def test_a_level_four_heading_does_not_end_the_section():
    assert _findings(_skill("#### Note\n\n" + _fence(LINE))) == []


@pytest.mark.parametrize("decoy", [
    f"{LINE}x",
    f"!{LINE}",
    f"# {LINE}",
    f" {LINE}",
    f"{LINE} ",
    f"/{LINE}",
    ".adlc/.session",
    ".adlc/.sessions/",
])
def test_a_longer_or_altered_line_does_not_satisfy_it(decoy):
    assert len(_findings(_skill(_fence(decoy)))) == 1, decoy


def test_a_mention_in_prose_does_not_satisfy_it():
    assert len(_findings(_skill(f"Add `{LINE}` to the block.\n\n" + _fence(".worktrees/")))) == 1


def test_a_bare_line_outside_the_fence_does_not_satisfy_it():
    """Step 5 writes its fence, so a line in the prose around it is written nowhere."""
    assert len(_findings(_skill(f"{LINE}\n\n" + _fence(".worktrees/")))) == 1


def test_a_copy_in_another_step_does_not_satisfy_it():
    assert len(_findings(_skill(_fence(".worktrees/"), after=_fence(LINE)))) == 1


def test_the_section_ends_at_a_heading_of_any_higher_level():
    text = "### Step 5: X\n\n" + _fence(".worktrees/") + "\n\n## Later\n\n" + _fence(LINE) + "\n"
    assert len(_findings(text)) == 1


def test_a_heading_shown_in_a_fence_is_not_the_section():
    found = _findings("# /init\n\n" + _fence("### Step 5: Example", LINE) + "\n")
    assert len(found) == 1 and "no `### Step 5` section" in found[0].message
    assert found[0].file == SITE and found[0].line == 1


@pytest.mark.parametrize("heading", ["### Step 50: Later", "## Step 5: Shallower", "#### Step 5: Deeper"])
def test_only_the_step_five_heading_opens_the_section(heading):
    found = _findings(f"{heading}\n\n" + _fence(LINE) + "\n")
    assert len(found) == 1 and "no `### Step 5` section" in found[0].message


# --- arming ------------------------------------------------------------------

def test_cli_passes_on_a_clean_plugin_root(tmp_path):
    assert _hits(_lint(_plugin_root(tmp_path, INIT_TEXT))) == []


def test_a_plugin_root_without_the_site_is_inert(tmp_path):
    """A fixture plugin root holds no `/init`. The real tree cannot go inert this
    way: `test_real_tree_passes` reads the site itself."""
    assert _check.check_session_gitignore(_plugin_root(tmp_path, None)) == []


def test_an_unreadable_site_is_a_finding_not_a_skip(tmp_path, monkeypatch):
    """LESSON-019: an armed guard that could not read its input says so."""
    root = _plugin_root(tmp_path, INIT_TEXT)

    def refuse(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(_check.Path, "read_text", refuse)
    found = _check.check_session_gitignore(root)
    assert [(f.file, f.check) for f in found] == [(SITE, "session-gitignore")]
    assert "Permission denied" in found[0].message


def test_cli_is_inert_outside_a_plugin_root(tmp_path):
    """A consumer repo or a fixture root that happens to hold the path is not read."""
    (tmp_path / "init").mkdir()
    (tmp_path / "init" / "SKILL.md").write_text(_delete_line(INIT_TEXT))
    assert _check.check_session_gitignore(tmp_path) == []
    assert _hits(_lint(tmp_path)) == []


# --- BR-7: git itself --------------------------------------------------------

def _init_gitignore_lines() -> str:
    """The body of the fence `/init` Step 5 writes, as a consumer gets it."""
    step = INIT_TEXT[INIT_TEXT.index("### Step 5"):INIT_TEXT.index("### Step 6:")]
    match = re.search(r"^```\n(.*?)^```$", step, flags=re.M | re.S)
    assert match, "no fence in Step 5"
    return match.group(1)


@pytest.mark.parametrize("source", ["this-repo", "init-step-5"])
def test_git_status_with_a_sidecar_shows_nothing(tmp_path, source):
    """BR-7, AC-1: both gitignores hide a sidecar from `git status`. The ordinary
    file beside it is the control: it shows, so an empty listing is not an
    environment that hides everything."""
    gitignore = ((REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
                 if source == "this-repo" else _init_gitignore_lines())
    (tmp_path / ".gitignore").write_text(gitignore)
    sidecars = tmp_path / ".adlc" / ".session"
    sidecars.mkdir(parents=True)
    (sidecars / "0123-abcd").write_text("harness=claude\nsession_id=0123-abcd\n")
    (tmp_path / ".adlc" / "control.md").write_text("visible\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    status = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, check=True, env=env).stdout
    assert ".adlc/control.md" in status
    assert ".session" not in status


# --- the docs ----------------------------------------------------------------

def test_readme_documents_the_check():
    readme = (REPO_ROOT / "tools" / "lint-skills" / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## What it checks"):readme.index("## Usage")]
    assert "session-gitignore" in re.findall(r"^\d+\. \*\*[^*]+\(`([a-z-]+)`\)", section, flags=re.M)
