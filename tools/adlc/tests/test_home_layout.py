"""REQ-663 ADR-5: the layout module, without a migration.

The end-to-end FAILs and their remediations are ``test_migrate_home.py``'s. These pin the
pure parts: the rc edit, the pointer reads, and the module's own dependency rule.
"""

import ast
import os

import pytest

import adlc_home
import home_layout as hl

BLOCK = '%s\nexport PATH="/h/bin:$PATH"\n%s\n' % (hl.RC_MARKER, hl.RC_MARKER_END)
PATH_LINE = 'export PATH="/h/bin:$PATH"'


def test_rc_gains_one_line_inside_the_block():
    text = "# mine\n" + BLOCK + "# after\n"
    out = hl.rc_with_home(text, "/x", PATH_LINE)
    assert out == ('# mine\n%s\nexport PATH="/h/bin:$PATH"\nexport ADLC_HOME="/x"\n%s\n# after\n'
                   % (hl.RC_MARKER, hl.RC_MARKER_END))
    assert hl.rc_home_line(out) == "/x"


def test_rc_edit_is_idempotent_and_replaces():
    once = hl.rc_with_home(BLOCK, "/x", PATH_LINE)
    assert hl.rc_with_home(once, "/x", PATH_LINE) == once
    moved = hl.rc_with_home(once, "/y", PATH_LINE)
    assert hl.rc_home_line(moved) == "/y" and moved.count("ADLC_HOME") == 1


def test_rc_without_home_restores_the_bytes():
    text = "# mine\n" + BLOCK + "no newline at the end"
    assert hl.rc_without_home(hl.rc_with_home(text, "/x", PATH_LINE)) == text


def test_rc_with_no_block_gets_one():
    out = hl.rc_with_home("# mine", "/x", PATH_LINE)
    assert out.startswith("# mine\n" + hl.RC_MARKER + "\n")
    assert hl.rc_home_line(out) == "/x"
    assert hl.rc_with_home("", "/x", PATH_LINE).startswith(hl.RC_MARKER)


def test_an_export_outside_the_block_is_the_users():
    text = 'export ADLC_HOME="/mine"\n' + BLOCK
    assert hl.rc_home_line(text) is None
    assert hl.rc_without_home(text) == text


@pytest.mark.parametrize("shell,name", [("/bin/zsh", ".zshrc"), ("/bin/bash", ".bash_profile"),
                                        ("/bin/fish", ".profile"), (None, ".profile")])
def test_rc_file_for(shell, name, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert hl.rc_file_for(shell) == str(tmp_path / name)


def test_raw_pointer_reads_what_the_resolver_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    assert hl.raw_pointer() is None
    (tmp_path / ".claude" / ".adlc-home").write_text("/nowhere/\n")
    assert hl.raw_pointer() == "/nowhere"
    assert hl.persisted_home() == ("/nowhere", "pointer")


def test_a_machine_that_lost_its_pointer_is_found_by_its_links(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    assert hl.persisted_home() == (str(tmp_path / ".claude"), "default")
    assert not hl.is_migrated()
    (tmp_path / ".claude" / ".global-next-req").symlink_to("/moved/.global-next-req")
    assert hl.persisted_home() == ("/moved", "traces")
    assert hl.is_migrated()


def test_a_tombstone_alone_is_a_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".global-next-req.lock.d").write_text("x")
    assert hl.is_migrated()


def test_a_held_lock_dir_is_not_a_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude" / ".global-next-req.lock.d").mkdir(parents=True)
    assert not hl.is_migrated()


def test_skills_view_of_ignores_a_toolkit_root(tmp_path):
    path = tmp_path / "skills.json"
    path.write_text('{"entries": [{"path": "/clone"}]}')
    assert hl.skills_view_of(str(path)) is None
    path.write_text('{"entries": [{"path": "/h/adlc/skills-view"}]}')
    assert hl.skills_view_of(str(path)) == "/h/adlc/skills-view"
    path.write_text("not json")
    assert hl.skills_view_of(str(path)) is None


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return names


@pytest.mark.parametrize("name", ["home_layout.py", "migrate_home.py"])
def test_module_imports_only_stdlib(name):
    """Doctor diagnoses a half-migrated machine without the venv it checks (LESSON-395)."""
    path = os.path.join(os.path.dirname(os.path.abspath(hl.__file__)), name)
    ours = {"adlc_home", "checks", "doctor", "home_layout", "harness_adapter", "harness_render"}
    stdlib = {"argparse", "datetime", "glob", "hashlib", "json", "os", "re", "shlex", "shutil",
              "signal", "subprocess", "sys", "tempfile", "time", "typing"}
    assert _imports(path) <= ours | stdlib, _imports(path) - ours - stdlib


def test_mount_targets_name_the_clone_and_its_agents():
    assert hl.mount_targets("/clone") == [("skills", "/clone"), ("agents", "/clone/agents")]


def test_the_default_comes_from_one_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert adlc_home.pointer_path() == str(tmp_path / ".claude" / ".adlc-home")
    assert hl.user_home() == str(tmp_path)
