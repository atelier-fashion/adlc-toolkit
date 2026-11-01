"""REQ-663 AC-9, BR-9, BR-10: ``--migrate-home --back``, ``--prune-backup``, and a repair
whose home is gone, on the sandboxed machine in ``migrate_box``.
"""

import glob
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from migrate_box import COUNTERS, CONFIG_TEXT, PLIST_NAME, Box  # noqa: E402


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path).seed()


@pytest.fixture
def venv_box(tmp_path):
    return Box(tmp_path).seed_delegation()


def verdicts(box):
    """Doctor's id and verdict per check, minus the one that reports the clone's git."""
    out = box.doctor()
    rows = {}
    for line in out.stdout.splitlines():
        if line.startswith("["):
            rows[line.split("]", 1)[1].split(" — ")[0].strip()] = line[1:5]
    rows.pop("toolkit-clean", None)
    return rows


def backups(box):
    return glob.glob(os.path.join(box.claude, ".adlc-home-*"))


def test_back_reverses_exactly(venv_box):
    box = venv_box
    start = verdicts(box)
    stamped = {}
    for name in ("adlc", "adlc-read", "adlc-write", "extract-chat"):
        stamped[name] = box.read(os.path.join(box.home, "bin", name))
    plist = os.path.join(box.home, "Library", "LaunchAgents", PLIST_NAME)
    plist_text = box.read(plist)
    rc_text = {n: box.read(os.path.join(box.home, n)) for n in (".zshrc", ".bash_profile",
                                                                ".profile")}
    assert box.migrate().returncode == 0
    box.write(box.moved(".global-next-req"), "777\n")
    box.write(box.moved(".adlc-own-reservations"), "req 7 aaaa\nreq 8 dddd\n")

    out = box.back()
    assert out.returncode == 0, box.out(out)

    assert box.read(box.path(".global-next-req")) == "777\n"
    assert box.read(box.path(".adlc-own-reservations")) == "req 7 aaaa\nreq 8 dddd\n"
    assert box.read(box.path("adlc", "config.yml")) == CONFIG_TEXT
    for name in COUNTERS:
        assert not os.path.islink(box.path(name))
        assert not os.path.lexists(box.path(name + ".lock.d"))
    assert not os.path.islink(box.path("adlc", "config.yml"))
    assert not os.path.lexists(box.path(".adlc-home"))
    version = subprocess.run([box.path("delegate-venv", "bin", "python3"), "-c",
                              "import yaml; print(yaml.__version__)"],
                             capture_output=True, text=True, env=box.env())
    assert version.stdout.strip() == "6.0.3"
    for name, text in stamped.items():
        assert box.read(os.path.join(box.home, "bin", name)) == text, name
    assert box.read(plist) == plist_text
    assert os.path.isfile(box.path("delegate-launchctl-setenv.sh"))
    for name, text in rc_text.items():
        assert box.read(os.path.join(box.home, name)) == text, name
    assert os.readlink(os.path.join(box.home, ".agents", "skills")) == \
        box.path("adlc", "skills-view")
    assert not os.path.exists(box.dest)
    assert backups(box) == []
    assert verdicts(box) == start


def test_a_second_migration_after_back_works(box):
    assert box.migrate().returncode == 0
    assert box.back().returncode == 0
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert box.doctor("--checks", "home-layout").returncode == 0


@pytest.mark.parametrize("step", ["counters", "config", "ledger", "stamps", "plist", "rc",
                                  "pointer", "mount", "tombstones"])
def test_back_failure_keeps_the_layout(box, step):
    assert box.migrate().returncode == 0
    box.write(box.moved(".global-next-req"), "888\n")
    before = box.machine()
    hook = box.hook('[ "$1" = "flip:%s" ] && exit 7\nexit 0\n' % step)
    out = box.back(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert step in box.out(out)
    assert box.machine() == before
    assert box.read(box.moved(".global-next-req")) == "888\n"
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_back_failure_with_a_venv_removes_what_it_staged(venv_box):
    box = venv_box
    assert box.migrate().returncode == 0
    hook = box.hook('[ "$1" = flip:counters ] && exit 7\nexit 0\n')
    out = box.back(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert not os.path.lexists(box.path("delegate-venv"))
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_back_works_after_prune(box):
    """A pruned backup does not make a migration one-way (the amended BR-9)."""
    assert box.migrate().returncode == 0
    assert box.migrate("--prune-backup").returncode == 0
    assert backups(box) == []
    out = box.back()
    assert out.returncode == 0, box.out(out)
    assert box.read(box.path(".global-next-req")) == "100\n"


def test_prune_removes_only_the_backup(box):
    assert box.migrate().returncode == 0
    assert len(backups(box)) == 1
    before = {k: v for k, v in box.machine().items() if ".adlc-home-backup" not in k}
    out = box.migrate("--prune-backup")
    assert out.returncode == 0, box.out(out)
    assert "0 action(s)" in out.stdout
    assert backups(box) == []
    assert box.machine() == before


def test_prune_with_no_dir(box):
    assert box.migrate().returncode == 0
    out = box.install("--migrate-home", "--prune-backup")
    assert out.returncode == 0 and backups(box) == []


def test_back_dry_run_changes_nothing(box):
    assert box.migrate().returncode == 0
    before = box.machine()
    dest = sorted(os.listdir(box.dest))
    out = box.back("--dry-run")
    assert out.returncode == 0, box.out(out)
    assert "would:" in out.stdout
    assert box.machine() == before and sorted(os.listdir(box.dest)) == dest


def test_back_refuses_with_no_pointer(box):
    out = box.back()
    assert out.returncode != 0
    assert "no home pointer" in box.out(out)


def test_back_refuses_when_the_home_is_gone(box):
    assert box.migrate().returncode == 0
    os.rename(box.dest, box.dest + ".gone")
    out = box.back()
    assert out.returncode != 0
    assert "does not exist" in box.out(out) and "--migrate-home" in box.out(out)


def test_back_refuses_a_conflicting_variable(box):
    assert box.migrate().returncode == 0
    before = box.machine()
    out = box.back(ADLC_HOME="/elsewhere")
    assert out.returncode != 0 and "/elsewhere" in box.out(out)
    assert box.machine() == before


def test_back_refuses_a_held_lock(box):
    assert box.migrate().returncode == 0
    lock = box.moved(".global-next-req.lock.d")
    os.mkdir(lock)
    out = box.back()
    assert out.returncode != 0 and lock in box.out(out)
    os.rmdir(lock)
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_back_passes_an_agreeing_variable(box):
    assert box.migrate().returncode == 0
    out = box.back(ADLC_HOME=box.dest)
    assert out.returncode == 0, box.out(out)
    assert "still exports ADLC_HOME" in out.stdout


def test_back_keeps_what_the_toolkit_did_not_put_there(box):
    assert box.migrate().returncode == 0
    box.write(box.moved("mine.txt"), "mine\n")
    out = box.back()
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved("mine.txt")) == "mine\n"
    assert sorted(os.listdir(box.dest)) == ["mine.txt"]
    assert "mine.txt" in out.stdout


def test_repair_restores_a_missing_home(box):
    """BR-12's remediation for a pointer to nowhere has to work there."""
    assert box.migrate().returncode == 0
    os.rename(box.dest, box.dest + ".gone")
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 1
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "restored" in out.stdout
    assert box.read(box.moved(".global-next-req")) == "100\n"
    assert box.read(box.moved("adlc", "config.yml")) == CONFIG_TEXT
    assert box.doctor("--checks", "home-layout").returncode == 0


@pytest.mark.parametrize("name", ["default", "parent"])
def test_back_refuses_a_pointer_at_the_default_home(box, name):
    """Reversing onto itself would end by clearing the home it just filled."""
    target = box.claude if name == "default" else box.home
    box.write(box.path(".adlc-home"), target + "\n")
    before = box.machine()
    out = box.back()
    assert out.returncode != 0
    assert "default home" in box.out(out)
    assert box.machine() == before
    assert box.read(box.path(".global-next-req")) == "100\n"


def test_back_refuses_when_the_venv_cannot_be_rebuilt(venv_box):
    box = venv_box
    assert box.migrate().returncode == 0
    with open(os.path.join(box.clone, "tools", "delegate", "requirements.txt"), "w") as fh:
        fh.write("no-such-package==1.0\n")
    before = box.machine()
    out = box.back(PIP_INDEX_URL="http://127.0.0.1:9/", PIP_RETRIES="0")
    assert out.returncode != 0
    assert "could not rebuild" in box.out(out)
    assert box.machine() == before
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_a_directory_named_skills_in_the_home_is_kept(box):
    assert box.migrate().returncode == 0
    os.unlink(box.moved("skills"))
    box.write(box.moved("skills", "mine.md"), "mine\n")
    assert box.back().returncode == 0
    assert box.read(box.moved("skills", "mine.md")) == "mine\n"


def test_remove_path_refuses_a_name_it_does_not_own(tmp_path):
    import migrate_home
    keep = tmp_path / "precious"
    keep.mkdir()
    with pytest.raises(ValueError, match="not a name this tool owns"):
        migrate_home.remove_path(str(keep))
    with pytest.raises(ValueError):
        migrate_home.remove_path("delegate-venv")
    assert keep.is_dir()
