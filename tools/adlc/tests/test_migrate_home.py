"""REQ-663: ``install.sh --migrate-home``, run whole, on a sandboxed machine.

Each case runs the real installer and the real engine against ``migrate_box.Box``. The
fast cases have no delegation install; the ones that need a venv build one for real,
through ``python3 -m venv`` and ``pip``, from a local wheel. ``launchctl`` is always the
stub, because the real one acts on the live agent.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import migrate_box as mb  # noqa: E402
from migrate_box import COUNTERS, CONFIG_TEXT, LEDGER_TEXT, PLIST_NAME, Box  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path).seed()


@pytest.fixture
def venv_box(tmp_path):
    return Box(tmp_path).seed_delegation()


@pytest.fixture
def migrated(box):
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    return box


def tombstoned(box):
    return [box.path(c + ".lock.d") for c in COUNTERS]


# --- AC-1, BR-1, BR-5, BR-6: the forward move ----------------------------------

def test_forward_moves_exactly_the_owned_state(migrated):
    box = migrated
    for index, name in enumerate(COUNTERS):
        assert box.read(box.moved(name)) == "%d\n" % (100 + index)
    assert box.read(box.moved(".adlc-own-reservations")) == LEDGER_TEXT
    assert box.read(box.moved("adlc", "config.yml")) == CONFIG_TEXT
    assert os.path.isdir(box.moved("adlc", "skills-view"))
    assert box.read(box.path("CLAUDE.md")) == "# mine\n"
    assert box.read(box.path("settings.json")) == "{}\n"
    assert os.path.realpath(box.path("skills")) == os.path.realpath(box.clone)
    assert os.path.realpath(box.path("agents")) == os.path.realpath(
        os.path.join(box.clone, "agents"))
    assert os.path.realpath(box.moved("skills")) == os.path.realpath(box.clone)
    assert os.path.realpath(box.moved("agents")) == os.path.realpath(
        os.path.join(box.clone, "agents"))


def test_claude_mounts_are_untouched(box):
    before = {n: (os.lstat(box.path(n)).st_ino, os.readlink(box.path(n)))
              for n in ("skills", "agents")}
    assert box.migrate().returncode == 0
    assert before == {n: (os.lstat(box.path(n)).st_ino, os.readlink(box.path(n)))
                      for n in ("skills", "agents")}


def test_user_entries_in_the_old_adlc_dir_stay(box):
    box.write(box.path("adlc", "config.yml.bak-20260831"), "mine\n")
    box.write(box.path("adlc", "plugin-root"), "/somewhere\n")
    assert box.migrate().returncode == 0
    assert box.read(box.path("adlc", "config.yml.bak-20260831")) == "mine\n"
    assert box.read(box.path("adlc", "plugin-root")) == "/somewhere\n"


def test_compat_symlinks_and_no_ledger_link(migrated):
    box = migrated
    for name in COUNTERS:
        assert os.readlink(box.path(name)) == box.moved(name)
    assert os.readlink(box.path("adlc", "config.yml")) == box.moved("adlc", "config.yml")
    assert not os.path.lexists(box.path(".adlc-own-reservations"))


def test_old_locks_are_tombstones(migrated):
    for lock in tombstoned(migrated):
        assert os.path.isfile(lock) and not os.path.islink(lock), lock
        assert "un-lockable" in migrated.read(lock)


def test_an_absent_counter_gets_a_link_and_no_file(box):
    os.unlink(box.path(".global-next-lesson"))
    assert box.migrate().returncode == 0
    assert os.readlink(box.path(".global-next-lesson")) == box.moved(".global-next-lesson")
    assert not os.path.lexists(box.moved(".global-next-lesson"))
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_a_machine_with_no_config_keeps_none(box):
    """BUG-205: a scaffolded `enabled: false` would outrank a legacy key."""
    os.unlink(box.path("adlc", "config.yml"))
    assert box.migrate().returncode == 0
    assert not os.path.lexists(box.path("adlc", "config.yml"))
    assert not os.path.lexists(box.moved("adlc", "config.yml"))
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_counter_bumped_after_staging_is_carried(box):
    hook = box.hook('[ "$1" = staged ] && printf 500 > "%s"\nexit 0\n'
                    % box.path(".global-next-req"))
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved(".global-next-req")) == "500"


def test_a_leftover_staged_counter_never_outvotes_the_live_one(box):
    box.write(box.moved(".global-next-req"), "1\n")
    assert box.migrate().returncode == 0
    assert box.read(box.moved(".global-next-req")) == "100\n"


# --- AC-1 + AC-2 stand-in, BR-7: a real venv ------------------------------------

def test_forward_with_a_real_venv(venv_box):
    box = venv_box
    hook = box.hook('[ "$1" = staged ] && printf 500 > "%s"\nexit 0\n'
                    % box.path(".global-next-req"))
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved(".global-next-req")) == "500"
    py = box.moved("delegate-venv", "bin", "python3")
    version = subprocess.run([py, "-c", "import yaml; print(yaml.__version__)"],
                             capture_output=True, text=True, env=box.env())
    assert version.stdout.strip() == "6.0.3"
    assert not os.path.lexists(box.path("delegate-venv"))
    assert not os.path.lexists(box.path("delegate-launchctl-setenv.sh"))
    assert os.access(box.moved("delegate-launchctl-setenv.sh"), os.X_OK)
    for name in ("adlc-read", "adlc-write", "extract-chat"):
        assert py in box.read(os.path.join(box.home, "bin", name))
    assert mb.run_sh("grep -rl '/.claude/delegate-venv' %s/bin %s/Library/LaunchAgents"
                     % (box.home, box.home)).stdout == ""
    plist = os.path.join(box.home, "Library", "LaunchAgents", PLIST_NAME)
    assert box.moved("delegate-launchctl-setenv.sh") in box.read(plist)
    calls = box.read(box.launchctl_log).splitlines()
    tail = [c.split()[0] for c in calls[-2:]]
    assert tail == ["bootout", "bootstrap"], calls
    if os.path.exists("/usr/bin/plutil"):
        assert subprocess.run(["/usr/bin/plutil", "-lint", plist],
                              capture_output=True).returncode == 0
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_stamped_files_carry_the_new_home(migrated):
    box = migrated
    shim = box.read(os.path.join(box.home, "bin", "adlc"))
    assert ".adlc-home" in shim
    rc = box.rc()
    assert 'export ADLC_HOME="%s"' % box.dest in box.read(rc)
    assert "# >>> adlc-toolkit (REQ-519) >>>" in box.read(rc)
    assert os.readlink(os.path.join(box.home, ".agents", "skills")) == \
        box.moved("adlc", "skills-view")


def test_a_harness_skills_surface_follows_the_view(box):
    surface = os.path.join(box.home, ".gemini", "config", "skills.json")
    box.write(surface, json.dumps({"entries": [{"path": box.path("adlc", "skills-view")}]}))
    assert box.migrate().returncode == 0
    assert json.loads(box.read(surface)) == {"entries": [{"path": box.moved("adlc", "skills-view")}]}
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_a_harness_skills_surface_is_not_created(migrated):
    assert not os.path.exists(os.path.join(migrated.home, ".gemini"))


def test_per_skill_mount_repoints_our_links_only(box):
    mount = os.path.join(box.home, ".agents", "skills")
    view = box.path("adlc", "skills-view")
    os.unlink(mount)
    os.makedirs(mount)
    os.symlink(os.path.join(view, "spec"), os.path.join(mount, "spec"))
    os.makedirs(os.path.join(mount, "mine"))
    assert box.migrate().returncode == 0
    assert os.readlink(os.path.join(mount, "spec")) == box.moved("adlc", "skills-view", "spec")
    assert os.path.isdir(os.path.join(mount, "mine"))
    assert box.doctor("--checks", "home-layout").returncode == 0


# --- AC-3, BR-8: every session resolves the home --------------------------------

def test_doctor_resolves_through_pointer_and_rc(migrated):
    box = migrated
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 0, box.out(out)
    assert "home=%s (pointer)" % box.dest in out.stdout
    script = '. "%s"; printf "%%s" "$ADLC_HOME"' % box.rc()
    sourced = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                             env=box.env(), capture_output=True, text=True)
    assert sourced.stdout == box.dest
    out = box.doctor("--checks", "home-layout", ADLC_HOME=box.dest)
    assert out.returncode == 0, box.out(out)
    assert "home=%s (env)" % box.dest in out.stdout


def test_a_conflicting_variable_is_refused_by_name(migrated):
    box = migrated
    out = box.doctor(ADLC_HOME="/elsewhere")
    assert out.returncode != 0
    text = box.out(out)
    assert "/elsewhere" in text and "pointer" in text
    assert "[FAIL] home-layout" in text
    assert "unset ADLC_HOME" in text


def test_a_fence_cannot_allocate_under_a_conflicting_variable(migrated):
    box = migrated
    script = '. "%s/partials/id-alloc.sh"; adlc_id_kind_counter req' % box.clone
    out = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                         env=box.env(ADLC_HOME="/elsewhere"), cwd=box.home)
    assert out.returncode != 0 and out.stdout == ""
    out = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                         env=box.env(), cwd=box.home)
    assert out.stdout.strip() == box.moved(".global-next-req")


def test_shim_uses_the_venv_under_the_pointed_home(venv_box):
    box = venv_box
    assert box.migrate().returncode == 0
    script = 'import sys; print(sys.prefix)'
    adlc_py = os.path.join(box.clone, "tools", "adlc", "adlc.py")
    box.write(adlc_py, script + "\n")
    out = subprocess.run([os.path.join(box.home, "bin", "adlc")], capture_output=True,
                         text=True, env=box.env())
    assert out.stdout.strip() == box.moved("delegate-venv")


# --- AC-5, BR-3: the consumer gate ----------------------------------------------

def _origin(box):
    """A bare origin and a fetched origin/main, so the baseline is verifiable."""
    bare = os.path.join(box.tmp, "origin.git")
    subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
    box.git("branch", "-M", "main")
    box.git("remote", "add", "origin", bare)
    box.git("push", "-q", "origin", "main")
    box.git("fetch", "-q", "origin")
    return bare


def _consumer(box, name, stale=None, origin=None):
    repo = os.path.join(box.repos, name)
    os.makedirs(os.path.join(repo, ".adlc", "partials"))
    source = os.path.join(box.clone, "partials")
    for entry in os.listdir(source):
        if entry.endswith(".sh"):
            with open(os.path.join(source, entry), "rb") as fh, \
                    open(os.path.join(repo, ".adlc", "partials", entry), "wb") as out:
                out.write(fh.read())
    if stale:
        box.write(os.path.join(repo, ".adlc", "partials", stale), "# an older revision\n")
    subprocess.run(["git", "init", "-q", repo], check=True, env=box.env())
    if origin:
        box.git("remote", "add", "origin", origin, cwd=repo)
    return repo


def test_stale_partial_refuses_and_a_resync_passes(box):
    _origin(box)
    repo = _consumer(box, "older", stale="id-alloc.sh")
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0
    text = box.out(out)
    assert repo in text and "id-alloc.sh" in text
    assert "/template-drift" in text
    assert box.machine() == before
    with open(os.path.join(box.clone, "partials", "id-alloc.sh"), "rb") as fh, \
            open(os.path.join(repo, ".adlc", "partials", "id-alloc.sh"), "wb") as dest:
        dest.write(fh.read())
    out = box.migrate()
    assert out.returncode == 0, box.out(out)


def test_a_stale_project_layer_alone_does_not_refuse(box):
    """A settings file holds no allocator, so it is reported and let through."""
    _origin(box)
    repo = _consumer(box, "layer")
    box.write(os.path.join(repo, ".claude", "settings.json"), "{}\n")
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "project layer only" in box.out(out)


def test_an_archived_repo_does_not_refuse(box):
    """It cannot take the fix, and BR-6 fails it loud if it ever allocates."""
    _origin(box)
    repo = _consumer(box, "shelved", stale="forge.sh",
                     origin="https://github.com/acme/shelved.git")
    gh = os.path.join(box.stub, "gh")
    box.write(gh, "#!/bin/sh\necho true\n")
    os.chmod(gh, 0o755)
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "skipped %s" % repo in box.out(out)


def test_unknown_archive_state_stays_stale(box):
    _origin(box)
    _consumer(box, "unknown", stale="forge.sh", origin="https://github.com/acme/unknown.git")
    out = box.migrate()
    assert out.returncode != 0
    assert "archive state unknown" in box.out(out)


def test_unverified_baseline_refuses(box):
    box.git("checkout", "-q", "-b", "feature")
    _consumer(box, "any", stale="forge.sh")
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0
    assert "unverified-baseline" in box.out(out)
    assert box.machine() == before


def test_no_consumer_passes(box):
    out = box.migrate("--dry-run")
    assert out.returncode == 0
    assert "no consumer under" in box.out(out)


# --- AC-6, BR-10: dry run -------------------------------------------------------

def test_dry_run_changes_nothing(box):
    before = box.machine()
    out = box.migrate("--dry-run")
    assert out.returncode == 0, box.out(out)
    assert box.machine() == before
    assert not os.path.exists(box.dest)
    text = out.stdout
    for name in COUNTERS:
        assert "move %s -> %s" % (box.path(name), box.moved(name)) in text
        assert "compat symlink %s -> %s" % (box.path(name), box.moved(name)) in text
        assert "tombstone %s.lock.d" % box.path(name) in text
    for needle in ("[ok] consumer-sync", "[ok] locks", ".adlc-own-reservations",
                   "pointer %s/.adlc-home" % box.claude, "rc file", "re-point",
                   "stamp %s/bin/adlc" % box.home, "regenerate the view"):
        assert needle in text, needle
    assert "Dry run: no changes made" in text


def test_dry_run_with_a_venv_names_it_and_builds_nothing(venv_box):
    box = venv_box
    before = box.machine()
    out = box.migrate("--dry-run")
    assert out.returncode == 0
    assert "rebuild %s" % box.moved("delegate-venv") in out.stdout
    assert "regenerate the launchd helper" in out.stdout
    for name in ("adlc-read", "adlc-write", "extract-chat"):
        assert "stamp %s/bin/%s" % (box.home, name) in out.stdout
    assert "stamp %s/Library/LaunchAgents/%s" % (box.home, PLIST_NAME) in out.stdout
    assert box.machine() == before
    assert not os.path.exists(box.dest)


# --- AC-7, BR-2, BR-3: refusals -------------------------------------------------

@pytest.mark.parametrize("value,needle", [
    ("relative/home", "--migrate-home needs an absolute"),
    ("", "--migrate-home was given an empty"),
    ("{claude}", "default home"),
    ("{claude}/inside", "default home"),
    ("{clone}/inside", "inside the clone"),
    ('{home}/with"quote', "cannot stand unescaped"),
    ("{home}/with$dollar", "cannot stand unescaped"),
    ("{home}/with`tick", "cannot stand unescaped"),
    ("{home}/with&amp", "cannot stand unescaped"),
])
def test_dir_refusals(box, value, needle):
    before = box.machine()
    target = value.format(claude=box.claude, clone=box.clone, home=box.home)
    out = box.install("--migrate-home", target)
    assert out.returncode != 0
    assert needle in box.out(out)
    assert box.machine() == before


def test_a_space_in_the_dir_is_fine(box):
    box.dest = os.path.join(box.home, "my home")
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_foreign_entry_refuses_naming_it(box):
    box.write(box.moved("notes.txt"), "mine\n")
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0
    assert "notes.txt" in box.out(out)
    assert box.machine() == before
    assert box.read(box.moved("notes.txt")) == "mine\n"


def test_an_existing_empty_dir_is_fine(box):
    os.makedirs(box.dest)
    assert box.migrate().returncode == 0


def test_a_held_lock_refuses_within_budget(box):
    lock = box.path(".global-next-bug.lock.d")
    os.mkdir(lock)
    before = box.machine()
    started = time.time()
    out = box.migrate()
    assert time.time() - started < 15
    assert out.returncode != 0
    assert lock in box.out(out)
    assert box.machine() == before
    assert not os.path.exists(box.dest)


def test_a_symlinked_lock_refuses(box):
    lock = box.path(".global-next-req.lock.d")
    os.symlink(box.tmp, lock)
    out = box.migrate()
    assert out.returncode != 0 and "symlink" in box.out(out)


def test_a_pointer_naming_another_home_refuses(box):
    other = os.path.join(box.home, "other-home")
    box.write(box.path(".adlc-home"), other + "\n")
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0
    assert "other-home" in box.out(out) and "--back" in box.out(out)
    assert box.machine() == before


def test_a_conflicting_variable_refuses(box):
    before = box.machine()
    out = box.migrate(ADLC_HOME="/elsewhere")
    assert out.returncode != 0 and "/elsewhere" in box.out(out)
    assert box.machine() == before


@pytest.mark.parametrize("value", ["dest", "claude"])
def test_an_agreeing_variable_passes(box, value):
    out = box.migrate(ADLC_HOME=box.dest if value == "dest" else box.claude)
    assert out.returncode == 0, box.out(out)


def test_a_previous_backup_refuses_until_pruned(box):
    backup = box.path(".adlc-home-backup-20260101T000000Z")
    os.makedirs(backup)
    out = box.migrate()
    assert out.returncode != 0 and "--prune-backup" in box.out(out)
    assert os.path.isdir(backup)
    out = box.migrate("--prune-backup")
    assert out.returncode == 0, box.out(out)
    assert not os.path.exists(backup)


def test_a_probe_marker_refuses_naming_the_recovery(box):
    marker = box.path("adlc", "harness-probe", "codex.marker.json")
    box.write(marker, "{}\n")
    out = box.migrate()
    assert out.returncode != 0
    assert "adlc harness probe codex --recover" in box.out(out)
    os.unlink(marker)
    assert box.migrate().returncode == 0


def test_a_broken_mount_refuses(box):
    os.unlink(box.path("skills"))
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0 and "install.sh" in box.out(out)
    assert box.machine() == before


def test_a_failing_pip_refuses_and_leaves_the_venv(venv_box):
    box = venv_box
    with open(os.path.join(box.clone, "tools", "delegate", "requirements.txt"), "w") as fh:
        fh.write("no-such-package==1.0\n")
    before = box.machine()
    out = box.migrate(PIP_INDEX_URL="http://127.0.0.1:9/", PIP_RETRIES="0")
    assert out.returncode != 0
    text = box.out(out)
    assert "delegate-venv" in text and "could not rebuild" in text
    assert box.machine() == before
    assert not os.path.exists(box.dest)


def test_a_dir_that_looks_like_a_flag_is_refused_as_a_dir(box):
    out = box.install("--migrate-home", "-rf")
    assert out.returncode == 1
    assert "--migrate-home needs an absolute" in box.out(out)


def test_a_symlinked_config_refuses(box):
    """Left behind, it would vanish for every reader: BUG-205's shape."""
    real = os.path.join(box.tmp, "dotfiles-config.yml")
    box.write(real, "delegate:\n  enabled: true\n")
    os.unlink(box.path("adlc", "config.yml"))
    os.symlink(real, box.path("adlc", "config.yml"))
    before = box.machine()
    out = box.migrate()
    assert out.returncode != 0
    assert "adlc/config.yml" in box.out(out) and "regular file" in box.out(out)
    assert box.machine() == before


def test_a_home_the_variable_already_names_keeps_its_data(box):
    """A REQ-654 override machine persisting its home must lose nothing."""
    box.write(box.moved(".global-next-req"), "950\n")
    box.write(box.moved(".global-next-bug"), "5\n")
    box.write(box.moved(".adlc-own-reservations"), "req 99 eeee\n")
    box.write(box.moved("adlc", "config.yml"), "delegate:\n  enabled: false\n")
    os.unlink(box.path(".global-next-lesson"))
    box.write(box.moved(".global-next-lesson"), "33\n")
    out = box.migrate(ADLC_HOME=box.dest)
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved(".global-next-req")) == "950\n"
    assert box.read(box.moved(".global-next-bug")) == "101\n"
    assert box.read(box.moved(".global-next-lesson")) == "33\n"
    assert "req 99 eeee" in box.read(box.moved(".adlc-own-reservations"))
    assert "req 7 aaaa" in box.read(box.moved(".adlc-own-reservations"))
    assert box.read(box.moved("adlc", "config.yml")) == "delegate:\n  enabled: false\n"


def test_a_file_only_the_new_home_holds_is_never_deleted(box):
    os.unlink(box.path(".global-next-lesson"))
    box.write(box.moved(".global-next-lesson"), "33\n")
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved(".global-next-lesson")) == "33\n"


def test_the_backup_is_private(migrated):
    """It holds the rc file, and an rc file is where API keys live."""
    box = migrated
    backup = [n for n in os.listdir(box.claude) if n.startswith(".adlc-home-backup-")]
    assert len(backup) == 1
    assert os.stat(box.path(backup[0])).st_mode & 0o077 == 0


def test_a_printed_fix_runs_verbatim_from_a_path_with_a_space(box):
    backup = box.path(".adlc-home-backup-20260101T000000Z")
    os.makedirs(backup)
    out = box.migrate()
    fix = [line.split("-> fix: ", 1)[1] for line in out.stdout.splitlines() if "-> fix: " in line]
    assert len(fix) == 1 and "clone dir" in fix[0]
    ran = subprocess.run(["bash", "-c", fix[0]], env=box.env(), cwd=box.home,
                         capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert not os.path.exists(backup)


def test_a_symlinked_rc_stays_a_symlink_and_undoes(box):
    """A dotfile manager's link: the file behind it changes, and an undo restores it."""
    for name in (".zshrc", ".bash_profile", ".profile"):
        path = os.path.join(box.home, name)
        real = os.path.join(box.tmp, "dotfiles-" + name.lstrip("."))
        os.rename(path, real)
        os.symlink(real, path)
    before = {n: box.read(os.path.join(box.tmp, "dotfiles-" + n))
              for n in ("zshrc", "bash_profile", "profile")}
    hook = box.hook('[ "$1" = flip:stamps ] && exit 7\nexit 0\n')
    assert box.migrate(ADLC_MIGRATE_TEST_HOOK=hook).returncode != 0
    assert before == {n: box.read(os.path.join(box.tmp, "dotfiles-" + n)) for n in before}
    assert box.migrate().returncode == 0
    assert os.path.islink(os.path.join(box.home, ".zshrc"))
    assert any("ADLC_HOME" in box.read(os.path.join(box.tmp, "dotfiles-" + n)) for n in before)
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_file_modes_survive(venv_box):
    box = venv_box
    wrapper = os.path.join(box.home, "bin", "adlc-read")
    os.chmod(wrapper, 0o711)
    assert box.migrate().returncode == 0
    assert os.stat(wrapper).st_mode & 0o777 == 0o711


def test_a_failure_leaves_an_existing_empty_dir_empty(box):
    os.makedirs(box.dest)
    hook = box.hook('[ "$1" = flip:counters ] && exit 7\nexit 0\n')
    assert box.migrate(ADLC_MIGRATE_TEST_HOOK=hook).returncode != 0
    assert os.listdir(box.dest) == []


def test_a_migrate_home_with_no_dir_is_a_usage_error(box):
    out = box.install("--migrate-home")
    assert out.returncode == 2 and "--migrate-home needs a <dir>" in box.out(out)


def test_back_without_the_flag_is_a_usage_error(box):
    assert box.install("--back").returncode == 2


def test_with_delegation_does_not_combine(box):
    assert box.migrate("--with-delegation").returncode == 2


# --- AC-8, BR-4: a failed flip --------------------------------------------------

@pytest.mark.parametrize("step", ["counters", "config", "ledger", "pointer", "rc", "stamps",
                                  "plist", "mount", "tombstones"])
def test_flip_failure_restores(box, step):
    before = box.machine()
    hook = box.hook('[ "$1" = "flip:%s" ] && exit 7\nexit 0\n' % step)
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert "step 'flip:%s'" % step in box.out(out) or "step '%s'" % step in box.out(out)
    assert box.machine() == before
    assert not os.path.exists(box.dest)


def test_both_homes_locks_are_held_during_the_flip(box):
    """BR-4: no allocator resolving either home runs during the flip. Asked mid-flip, by
    the same `mkdir` an allocator would use."""
    log = os.path.join(box.tmp, "held.log")
    locks = [box.path(c + ".lock.d") for c in COUNTERS] + [box.moved(c + ".lock.d") for c in COUNTERS]
    script = ['[ "$1" = flip:ledger ] || exit 0']
    for lock in locks:
        script.append('if mkdir "%s" 2>/dev/null; then rmdir "%s"; echo FREE >> "%s"; '
                      'else echo HELD >> "%s"; fi' % (lock, lock, log, log))
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=box.hook("\n".join(script) + "\nexit 0\n"))
    assert out.returncode == 0, box.out(out)
    assert box.read(log).split() == ["HELD"] * 6


def test_a_lock_taken_after_preflight_stops_the_flip(box):
    lock = box.path(".global-next-lesson.lock.d")
    before = box.machine()
    hook = box.hook('[ "$1" = staged ] && mkdir "%s"\nexit 0\n' % lock)
    started = time.time()
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert time.time() - started < 30
    assert out.returncode != 0 and lock in box.out(out)
    os.rmdir(lock)
    assert box.machine() == before
    assert not os.path.exists(box.dest)


def test_the_pointer_lands_before_the_old_locks_go(box):
    """BR-4's order, read at each flip step: the old lock paths stay directories until the
    pointer and the rc line are down."""
    log = os.path.join(box.tmp, "order.log")
    hook = box.hook('printf "%%s pointer=%%s lock=%%s\\n" "$1" '
                    '"$([ -f "%s" ] && echo yes || echo no)" '
                    '"$([ -d "%s" ] && echo dir || echo file)" >> "%s"\nexit 0\n'
                    % (box.path(".adlc-home"), box.path(".global-next-req.lock.d"), log))
    assert box.migrate(ADLC_MIGRATE_TEST_HOOK=hook).returncode == 0
    lines = dict(line.split(" ", 1) for line in box.read(log).splitlines())
    assert lines["flip:ledger"] == "pointer=no lock=dir"
    assert lines["flip:rc"] == "pointer=yes lock=dir"
    assert lines["flip:tombstones"] == "pointer=yes lock=file"


def test_a_failed_flip_can_be_retried(box):
    hook = box.hook('[ "$1" = flip:counters ] && exit 7\nexit 0\n')
    assert box.migrate(ADLC_MIGRATE_TEST_HOOK=hook).returncode != 0
    out = box.migrate()
    assert out.returncode == 0, box.out(out)


def test_a_signal_mid_flip_unwinds(box):
    before = box.machine()
    hook = box.hook('[ "$1" = flip:pointer ] && kill -TERM "$PPID"\nsleep 1\nexit 0\n')
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert box.machine() == before


def test_a_failed_stage_removes_what_it_made(box):
    before = box.machine()
    hook = box.hook('[ "$1" = staged ] && exit 7\nexit 0\n')
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert box.machine() == before
    assert not os.path.exists(box.dest)


def test_flip_failure_with_a_real_venv_keeps_the_old_venv(venv_box):
    box = venv_box
    hook = box.hook('[ "$1" = flip:tombstones ] && exit 7\nexit 0\n')
    before = box.machine()
    out = box.migrate(ADLC_MIGRATE_TEST_HOOK=hook)
    assert out.returncode != 0
    assert box.machine() == before
    version = subprocess.run([box.path("delegate-venv", "bin", "python3"), "-c", "import yaml"],
                             env=box.env())
    assert version.returncode == 0


# --- AC-10, BR-11: repair ------------------------------------------------------

def test_second_run_reports_zero_actions(migrated):
    box = migrated
    before = box.machine()
    out = box.migrate()
    assert out.returncode == 0
    assert "0 action(s)" in out.stdout
    assert box.machine() == before


def test_repair_and_plain_install_honour_the_home(venv_box):
    box = venv_box
    assert box.migrate().returncode == 0
    assert box.install("--repair").returncode == 0
    out = box.delegate_install()
    assert out.returncode == 0, box.out(out)
    assert not os.path.exists(box.path("delegate-venv"))
    assert sorted(os.listdir(box.path("adlc"))) == ["config.yml"]
    assert os.path.islink(box.path("adlc", "config.yml"))
    wrapper = box.read(os.path.join(box.home, "bin", "adlc-read"))
    assert box.moved("delegate-venv", "bin", "python3") in wrapper
    out = box.migrate()
    assert out.returncode == 0
    assert "0 action(s)" in out.stdout, out.stdout


def test_repair_of_a_drifted_shim_and_plist(venv_box):
    box = venv_box
    assert box.migrate().returncode == 0
    wrapper = os.path.join(box.home, "bin", "adlc-read")
    box.write(wrapper, box.read(wrapper).replace(box.moved("delegate-venv"),
                                                 box.path("delegate-venv")))
    os.chmod(wrapper, 0o755)
    plist = os.path.join(box.home, "Library", "LaunchAgents", PLIST_NAME)
    box.write(plist, box.read(plist).replace(box.dest, box.claude))
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "0 action(s)" not in out.stdout
    assert box.moved("delegate-venv") in box.read(wrapper)
    assert box.dest in box.read(plist)
    out = box.migrate()
    assert "0 action(s)" in out.stdout


def test_a_repair_is_not_held_back_by_a_stale_consumer(migrated):
    box = migrated
    _origin(box)
    _consumer(box, "older", stale="forge.sh")
    wrapper_home = box.path(".global-next-bug")
    os.unlink(wrapper_home)
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "not a refusal on a repair" in box.out(out)


def test_a_regular_counter_back_at_the_old_path_keeps_the_higher_value(migrated):
    box = migrated
    os.unlink(box.path(".global-next-req"))
    box.write(box.path(".global-next-req"), "900\n")
    assert box.doctor("--checks", "home-layout").returncode != 0
    assert box.migrate().returncode == 0
    assert box.read(box.moved(".global-next-req")) == "900\n"
    assert os.readlink(box.path(".global-next-req")) == box.moved(".global-next-req")


def test_a_lower_regular_counter_does_not_lower_the_home(migrated):
    box = migrated
    box.write(box.moved(".global-next-req"), "950\n")
    os.unlink(box.path(".global-next-req"))
    box.write(box.path(".global-next-req"), "900\n")
    assert box.migrate().returncode == 0
    assert box.read(box.moved(".global-next-req")) == "950\n"


def test_a_ledger_back_at_the_old_path_is_folded_in(migrated):
    box = migrated
    box.write(box.path(".adlc-own-reservations"), "lesson 9 cccc\n")
    assert box.migrate().returncode == 0
    assert not os.path.lexists(box.path(".adlc-own-reservations"))
    assert box.read(box.moved(".adlc-own-reservations")) == LEDGER_TEXT + "lesson 9 cccc\n"


def test_a_disagreeing_config_is_set_aside_not_merged(migrated):
    box = migrated
    os.unlink(box.path("adlc", "config.yml"))
    box.write(box.path("adlc", "config.yml"), "delegate:\n  enabled: false\n")
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert box.read(box.moved("adlc", "config.yml")) == CONFIG_TEXT
    assert "differs from" in box.out(out)
    saved = re.search(r"saved under (\S+)", out.stdout).group(1)
    assert os.path.isfile(os.path.join(saved, "move", "adlc__config.yml"))


def test_a_dangling_config_link_is_reported_and_restored(migrated):
    box = migrated
    os.unlink(box.moved("adlc", "config.yml"))
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 1 and "dangles" in out.stdout
    assert box.migrate().returncode == 0
    assert box.read(box.moved("adlc", "config.yml")) == CONFIG_TEXT
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_a_dangling_config_link_with_no_backup_says_so_and_clears(migrated):
    box = migrated
    assert box.migrate("--prune-backup").returncode == 0
    os.unlink(box.moved("adlc", "config.yml"))
    out = box.migrate()
    assert out.returncode == 0, box.out(out)
    assert "no backup holds a copy" in out.stdout
    assert not os.path.lexists(box.path("adlc", "config.yml"))
    assert box.doctor("--checks", "home-layout").returncode == 0


def test_prune_also_clears_what_a_killed_run_left(migrated):
    box = migrated
    leftover = box.path(".adlc-home-repair-20260101T000000Z")
    os.makedirs(leftover)
    assert box.migrate("--prune-backup").returncode == 0
    assert not os.path.exists(leftover)


# --- AC-11, BR-12: doctor FAIL, then its own remediation -------------------------

def _break_symlink(box):
    os.unlink(box.path(".global-next-req"))
    box.write(box.path(".global-next-req"), "100\n")
    return box.path(".global-next-req")


def _break_lock(box):
    lock = box.path(".global-next-bug.lock.d")
    os.unlink(lock)
    os.mkdir(lock)
    return lock


def _break_wrapper(box):
    path = os.path.join(box.home, "bin", "adlc-read")
    box.write(path, '#!/bin/sh\nexec "%s" "$@"\n' % box.path("delegate-venv", "bin", "python3"))
    os.chmod(path, 0o755)
    return path


def _break_pointer(box):
    os.unlink(box.path(".adlc-home"))
    return box.path(".adlc-home")


def _break_rc(box):
    rc = box.rc()
    box.write(rc, box.read(rc).replace('export ADLC_HOME="%s"\n' % box.dest, ""))
    return rc


def _break_tombstone(box):
    lock = box.path(".global-next-lesson.lock.d")
    os.unlink(lock)
    return lock


@pytest.mark.parametrize("breaker", [_break_symlink, _break_lock, _break_wrapper, _break_pointer,
                                     _break_rc, _break_tombstone])
def test_home_layout_fail_and_remediation(box, breaker):
    box.write(os.path.join(box.home, "bin", "adlc-read"), "#!/bin/sh\n")
    assert box.migrate().returncode == 0
    item = breaker(box)
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 1, box.out(out)
    text = box.out(out)
    assert "[FAIL] home-layout" in text and item in text
    fixes = [line.split("-> fix: ", 1)[1].split("   #")[0]
             for line in text.splitlines() if "-> fix: " in line]
    repair = [f for f in fixes if "--migrate-home" in f and "--back" not in f]
    assert len(repair) == 1, fixes
    ran = subprocess.run(["bash", "-c", repair[0]], env=box.env(), cwd=box.home,
                         capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 0, box.out(out)


def test_home_layout_passes_from_a_second_copy_of_the_tools(migrated):
    """A doctor run from a worktree checks the clone Claude Code mounts, not its own copy."""
    box = migrated
    copy = os.path.join(box.tmp, "worktree")
    shutil.copytree(box.clone, copy, symlinks=True)
    out = subprocess.run([sys.executable, os.path.join(copy, "tools", "adlc", "adlc.py"),
                          "doctor", "--checks", "home-layout"], cwd=box.home, env=box.env(),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_home_layout_skips_on_an_unmigrated_machine(box):
    out = box.doctor("--checks", "home-layout")
    assert out.returncode == 0
    assert "[SKIP] home-layout" in out.stdout


def test_home_layout_skips_on_a_req_654_override(tmp_path):
    box = Box(tmp_path)
    override = os.path.join(box.home, "override")
    assert box.install(ADLC_HOME=override).returncode == 0
    out = box.doctor("--checks", "home-layout", ADLC_HOME=override)
    assert "[SKIP] home-layout" in out.stdout


def test_a_pointer_to_nowhere_is_reported_alone(migrated):
    box = migrated
    os.rename(box.dest, box.dest + ".gone")
    out = box.doctor()
    assert out.returncode == 1
    text = box.out(out)
    assert "[FAIL] home-layout" in text and "does not exist" in text
    assert "[PASS]" not in text
    assert text.count("] ") >= 1 and "counters" not in out.stdout.split("profile:")[0]


# --- the sandbox itself (LESSON-758, LESSON-762) --------------------------------

def _populated_outer_home(tmp_path):
    outer = tmp_path / "outer"
    (outer / ".claude" / "adlc").mkdir(parents=True)
    (outer / "bin").mkdir()
    (outer / ".zshrc").write_text("# outer\n")
    (outer / ".claude" / "adlc" / "config.yml").write_text("delegate:\n  enabled: false\n")
    for name in COUNTERS:
        (outer / ".claude" / name).write_text("1\n")
    (outer / ".claude" / ".adlc-own-reservations").write_text("req 1 x\n")
    return outer


def test_a_migration_leaves_the_outer_home_alone(tmp_path, monkeypatch):
    """The whole forward and reverse, with an outer HOME that looks like the real one."""
    outer = _populated_outer_home(tmp_path)
    monkeypatch.setenv("HOME", str(outer))
    before = mb.tree_state(str(outer))
    box = Box(tmp_path / "box").seed()
    assert box.migrate().returncode == 0
    assert box.back().returncode == 0
    assert mb.tree_state(str(outer)) == before


def test_the_leak_probe_fires_on_a_real_leak(tmp_path):
    """The control: a run pointed at that home changes it, and the probe sees it."""
    outer = _populated_outer_home(tmp_path)
    before = mb.tree_state(str(outer))
    box = Box(tmp_path / "box")
    (outer / ".claude" / "skills").symlink_to(box.clone)
    (outer / ".claude" / "agents").symlink_to(os.path.join(box.clone, "agents"))
    before = mb.tree_state(str(outer))
    dest = str(tmp_path / "leak-dest")
    out = box.install("--migrate-home", dest, env=box.env(HOME=str(outer)))
    assert out.returncode == 0, box.out(out)
    assert mb.tree_state(str(outer)) != before


# --- AC-13, BR-14 ---------------------------------------------------------------

def _doc(rel):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__)))))
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def test_docs_carry_the_layout():
    readme = _doc("README.md")
    for needle in ("--migrate-home", "--back", "--prune-backup", "backup"):
        assert needle in readme, needle
    arch = _doc(".adlc/context/architecture.md")
    assert "tombstone" in arch and "Stage, then flip" in arch
    assert "a counter is data" in arch.lower()
    assert "else the pointer" in _doc(".adlc/context/conventions.md")
    assert "home-layout" in _doc("tools/adlc/README.md")
    assert "REQ-663" in _doc("CHANGELOG.md")
