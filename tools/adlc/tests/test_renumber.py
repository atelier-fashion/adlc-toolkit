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
