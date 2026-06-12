"""Tests for the adlc renumber subcommand (REQ-518 BR-9 / TASK-003).

Offline: a sandbox git repo under tmp_path, no network, no real ~/.claude mutation.
The remote-collision shell-out is monkeypatched so these tests never touch a remote.
"""
import os
import subprocess

import pytest

import adlc
import renumber


def _init_repo(tmp_path):
    """A throwaway git repo with a REQ-600 spec dir, frontmatter, and two references."""
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    spec = repo / ".adlc" / "specs" / "REQ-600-demo"
    spec.mkdir(parents=True)
    (spec / "requirement.md").write_text("id: REQ-600\ntitle: demo\n", encoding="utf-8")
    (repo / "notes.md").write_text("see REQ-600 for context\n", encoding="utf-8")
    (repo / "other.md").write_text("depends on REQ-600 and REQ-601\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


# --- id validation (LESSON-008) -----------------------------------------------------

@pytest.mark.parametrize("good", ["REQ-600", "BUG-051", "LESSON-001", "REQ-1234"])
def test_validate_id_accepts_well_formed(good):
    assert renumber._validate_id(good)


@pytest.mark.parametrize("bad", [
    "REQ-../etc", "REQ-60", "req-600", "REQ-", "REQ-600x", "../REQ-600",
    "REQ600", "REQ-600-slug", "FOO-600", "",
])
def test_validate_id_rejects_garbage_and_traversal(bad):
    assert not renumber._validate_id(bad)


def test_kind_mismatch_is_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-600", "BUG-601"])
    assert rc == 2
    assert "kind mismatch" in capsys.readouterr().err


def test_invalid_old_id_returns_2(monkeypatch):
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    assert renumber.main(["REQ-../x", "REQ-601"]) == 2


# --- collision refusal (BR-9) -------------------------------------------------------

def test_refuses_when_new_id_collides_on_remote(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: True)
    rc = renumber.main(["REQ-600", "REQ-700"])
    assert rc == 1
    assert "also collides on the remote" in capsys.readouterr().err
    # No mutation happened.
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()


# --- dry-run then apply -------------------------------------------------------------

def test_dry_run_mutates_nothing(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-600", "REQ-700"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    # Nothing renamed or rewritten.
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()
    assert not (repo / ".adlc" / "specs" / "REQ-700-demo").exists()
    assert "REQ-600" in (repo / "notes.md").read_text()


def test_apply_renames_dir_and_rewrites_refs(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-600", "REQ-700", "--yes"])
    assert rc == 0
    # Dir renamed.
    assert (repo / ".adlc" / "specs" / "REQ-700-demo").is_dir()
    assert not (repo / ".adlc" / "specs" / "REQ-600-demo").exists()
    # Frontmatter rewritten.
    fm = (repo / ".adlc" / "specs" / "REQ-700-demo" / "requirement.md").read_text()
    assert "id: REQ-700" in fm
    assert "REQ-600" not in fm
    # References rewritten; REQ-601 left intact.
    assert "REQ-700" in (repo / "notes.md").read_text()
    other = (repo / "other.md").read_text()
    assert "REQ-700" in other and "REQ-601" in other


def test_apply_leaves_zero_old_id_outside_git_history(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    renumber.main(["REQ-600", "REQ-700", "--yes"])
    # Grep the working tree (excluding .git) for any remaining REQ-600.
    remaining = []
    for dirpath, dirnames, filenames in os.walk(repo):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                with open(full, encoding="utf-8") as fh:
                    if "REQ-600" in fh.read():
                        remaining.append(full)
            except (OSError, UnicodeDecodeError):
                pass
    assert remaining == []


def test_bug_rename_uses_file_layout(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    bugs = repo / ".adlc" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "BUG-050-demo.md").write_text("id: BUG-050\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["BUG-050", "BUG-051", "--yes"])
    assert rc == 0
    assert (bugs / "BUG-051-demo.md").is_file()
    assert not (bugs / "BUG-050-demo.md").exists()
    assert "id: BUG-051" in (bugs / "BUG-051-demo.md").read_text()


# --- id-boundary safety (REQ-524) ---------------------------------------------------


def _init_sibling_repo(tmp_path):
    """A repo with BOTH a REQ-120 artifact and a REQ-1200 artifact, plus refs.

    REQ-120 is the renumber target; REQ-1200 is the innocent prefix-sibling that
    MUST survive byte-identical (except for any legitimate REQ-120 reference it
    happens to contain). Mirrors the adversarial M2 reproduction in REQ-524.
    """
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    target = repo / ".adlc" / "specs" / "REQ-120-target"
    target.mkdir(parents=True)
    (target / "requirement.md").write_text("id: REQ-120\ntitle: target\n", encoding="utf-8")
    sibling = repo / ".adlc" / "specs" / "REQ-1200-bystander"
    sibling.mkdir(parents=True)
    # The sibling's id is REQ-1200 (must NOT change); it has no REQ-120 reference.
    (sibling / "requirement.md").write_text(
        "id: REQ-1200\ntitle: bystander\n", encoding="utf-8"
    )
    # A file with only REQ-1200 — must not be selected when renumbering REQ-120.
    (repo / "sibling-only.md").write_text("only REQ-1200 here\n", encoding="utf-8")
    # A file with legitimate REQ-120 refs across punctuation / slug / EOL forms.
    (repo / "refs.md").write_text(
        "see REQ-120 and REQ-120-slug and REQ-120. and REQ-120) and REQ-1200\n"
        "trailing ref REQ-120\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


# --- boundary pattern unit (the single authority) -----------------------------------

@pytest.mark.parametrize("text", [
    "REQ-120", "see REQ-120 here", "REQ-120-slug", "REQ-120.", "REQ-120)",
    "id: REQ-120", "ends with REQ-120",
])
def test_boundary_re_matches_legitimate_refs(text):
    assert renumber._id_boundary_re("REQ-120").search(text)


@pytest.mark.parametrize("text", ["REQ-1200", "REQ-1200-slug", "XREQ-120", "1REQ-120"])
def test_boundary_re_rejects_sibling_and_embedded(text):
    assert not renumber._id_boundary_re("REQ-120").search(text)


def test_boundary_re_and_ere_agree():
    """The Python re (arbiter) and the git-grep ERE (selection) agree on whether a
    line contains a boundary-real match — proving they cannot drift (BR-2)."""
    import re as _re
    corpus = [
        "REQ-120", "REQ-1200", "REQ-120-slug", "REQ-1200-slug", "XREQ-120",
        "1REQ-120", "id: REQ-120", "REQ-120.", "see REQ-120 and REQ-1200",
        "nothing here", "REQ-999",
    ]
    py = renumber._id_boundary_re("REQ-120")
    ere = _re.compile(renumber._id_boundary_ere("REQ-120"))
    for line in corpus:
        assert bool(py.search(line)) == bool(ere.search(line)), line


# --- sibling-prefix corruption guard (the keystone) ---------------------------------

def test_sibling_prefix_untouched_after_apply(tmp_path, monkeypatch):
    repo = _init_sibling_repo(tmp_path)
    sibling_md = repo / ".adlc" / "specs" / "REQ-1200-bystander" / "requirement.md"
    sibling_only = repo / "sibling-only.md"
    before_sibling = sibling_md.read_bytes()
    before_only = sibling_only.read_bytes()
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-120", "REQ-999", "--yes"])
    assert rc == 0
    # Target dir renamed; sibling dir untouched.
    assert (repo / ".adlc" / "specs" / "REQ-999-target").is_dir()
    assert not (repo / ".adlc" / "specs" / "REQ-120-target").exists()
    assert (repo / ".adlc" / "specs" / "REQ-1200-bystander").is_dir()
    # The REQ-1200 artifact is byte-identical — no REQ-9990 collateral.
    assert sibling_md.read_bytes() == before_sibling
    assert sibling_only.read_bytes() == before_only
    # Every legitimate REQ-120 reference was rewritten.
    refs = (repo / "refs.md").read_text()
    assert "REQ-120" not in refs.replace("REQ-1200", "")  # no bare REQ-120 left
    assert "REQ-999" in refs and "REQ-999-slug" in refs
    assert "REQ-1200" in refs  # the sibling mention in refs.md is preserved


def test_sibling_only_file_excluded_from_dry_run_plan(tmp_path, monkeypatch, capsys):
    repo = _init_sibling_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-120", "REQ-999"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    # sibling-only.md (contains only REQ-1200) must not be in the plan.
    assert "sibling-only.md" not in out
    # refs.md (has real REQ-120 refs) is in the plan.
    assert "refs.md" in out


def test_locate_old_ignores_sibling_prefix(tmp_path):
    repo = _init_sibling_repo(tmp_path)
    path, is_dir = renumber._locate_old(str(repo), "REQ-120")
    assert is_dir
    assert path is not None
    assert path.endswith("REQ-120-target")
    assert "REQ-1200" not in os.path.basename(path)


# --- punctuation / slug / frontmatter / EOL rewrite correctness ----------------------

def test_boundary_rewrites_punctuation_slug_frontmatter_eol(tmp_path, monkeypatch):
    repo = _init_sibling_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    assert renumber.main(["REQ-120", "REQ-999", "--yes"]) == 0
    refs = (repo / "refs.md").read_text()
    # punctuation forms
    assert "REQ-999." in refs and "REQ-999)" in refs
    # slug form
    assert "REQ-999-slug" in refs
    # EOL form (trailing ref REQ-120 -> REQ-999 at end of line)
    assert "trailing ref REQ-999" in refs
    # frontmatter id rewritten in the moved artifact
    fm = (repo / ".adlc" / "specs" / "REQ-999-target" / "requirement.md").read_text()
    assert "id: REQ-999" in fm and "REQ-120" not in fm


def test_dir_slug_rewrites(tmp_path, monkeypatch):
    repo = _init_sibling_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    assert renumber.main(["REQ-120", "REQ-999", "--yes"]) == 0
    # The -target slug suffix survives; only the id segment changes.
    assert (repo / ".adlc" / "specs" / "REQ-999-target").is_dir()


# --- dry-run: per-file count + repo-relative output (BR-3, BR-5) ---------------------

def test_dry_run_reports_per_file_match_count(tmp_path, monkeypatch, capsys):
    repo = _init_sibling_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    renumber.main(["REQ-120", "REQ-999"])
    out = capsys.readouterr().out
    # refs.md has 5 boundary-real REQ-120 occurrences: 4 on line 1
    # (REQ-120, REQ-120-slug, REQ-120., REQ-120) — REQ-1200 excluded) + 1 on line 2.
    assert "refs.md (5 matches)" in out


def test_dry_run_output_is_repo_relative(tmp_path, monkeypatch, capsys):
    repo = _init_sibling_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    renumber.main(["REQ-120", "REQ-999"])
    out = capsys.readouterr().out
    # No absolute path (BR-5): the sandbox repo root must not appear in stdout.
    assert str(repo) not in out
    # Relative paths are present instead.
    assert "refs.md" in out
    assert ".adlc/specs/REQ-999-target" in out


# --- dispatch registration (REQ-519 BR-11) ------------------------------------------

def test_renumber_registered_in_subcommands():
    assert "renumber" in adlc.SUBCOMMANDS
    assert callable(adlc.SUBCOMMANDS["renumber"]["handler"])
    assert adlc.SUBCOMMANDS["renumber"]["help"]


def test_renumber_subcommand_dispatches(monkeypatch):
    called = {}

    def fake_main(argv):
        called["argv"] = argv
        return 0

    monkeypatch.setattr(renumber, "main", fake_main)
    rc = adlc.main(["renumber", "REQ-600", "REQ-601"])
    assert rc == 0
    assert called["argv"] == ["REQ-600", "REQ-601"]
