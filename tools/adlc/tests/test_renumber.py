"""Tests for the adlc renumber subcommand (REQ-518 BR-9 / TASK-003).

Offline: a sandbox git repo under tmp_path, no network, no real ~/.claude mutation.
The remote-collision shell-out is monkeypatched so these tests never touch a remote.
"""
import errno
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


# --- a missing recheck partial refuses, never "no collision" (REQ-669 ADR-2) --------

def _no_toolkit_partials(monkeypatch):
    """The toolkit level finds no partial, as on an install that lost its partials/."""
    def missing(rel):
        raise renumber.toolkit_root.ToolkitFileNotFound(
            "adlc: toolkit file not found: /nowhere/" + rel)
    monkeypatch.setattr(renumber.toolkit_root, "toolkit_file", missing)


def test_remote_collision_raises_when_recheck_partial_missing(tmp_path, monkeypatch):
    """No recheck partial anywhere -> a named error, not False.

    False reads as "no collision", which let a rename into a remote collision
    proceed with nothing said. The message names the partial and the project
    path that was searched.
    """
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    _no_toolkit_partials(monkeypatch)
    with pytest.raises(renumber.RecheckUnavailableError) as exc:
        renumber.remote_collision("REQ-700")
    msg = str(exc.value)
    assert "id-recheck.sh" in msg
    assert os.path.join(".adlc", "partials", "id-recheck.sh") in msg
    assert "REQ-700" in msg


def test_main_refuses_when_recheck_partial_missing(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    _no_toolkit_partials(monkeypatch)
    rc = renumber.main(["REQ-600", "REQ-700", "--yes"])
    assert rc == 1
    assert "id-recheck.sh" in capsys.readouterr().err
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()
    assert not (repo / ".adlc" / "specs" / "REQ-700-demo").exists()


def test_find_partial_project_copy_then_toolkit(tmp_path, monkeypatch):
    """Benign twins: the toolkit tree answers when the project has no copy, and a
    project copy under .adlc/partials still wins when it has one."""
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    toolkit_copy = renumber.toolkit_root.toolkit_file("partials/id-recheck.sh")
    assert renumber._find_partial("id-recheck.sh") == toolkit_copy

    local = repo / ".adlc" / "partials" / "id-recheck.sh"
    local.parent.mkdir(parents=True)
    local.write_text("adlc_recheck_id() { return 0; }\n", encoding="utf-8")
    assert os.path.realpath(renumber._find_partial("id-recheck.sh")) == \
        os.path.realpath(str(local))


def _stub_recheck(repo, body):
    """A project recheck partial whose adlc_recheck_id runs ``body``."""
    local = repo / ".adlc" / "partials" / "id-recheck.sh"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("adlc_recheck_id() {\n%s\n}\n" % body, encoding="utf-8")


@pytest.mark.parametrize("rc,collides", [(0, False), (1, True)])
def test_remote_collision_reads_the_two_verdicts(tmp_path, monkeypatch, rc, collides):
    """Benign twins: 0 is no collision, 1 is a collision, as the partial's contract says."""
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_recheck(repo, "  return %d" % rc)
    assert renumber.remote_collision("REQ-700") is collides


@pytest.mark.parametrize("body", ["  return 2", "  exit 2", "  exit 127"])
def test_remote_collision_refuses_any_other_exit(tmp_path, monkeypatch, body):
    """Neither 0 nor 1 is no verdict: dash exits 2 when the fallback id-alloc.sh is missing.

    That used to read as "no collision".
    """
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_recheck(repo, "  echo 'id-alloc.sh: not found' >&2\n" + body)
    with pytest.raises(renumber.RecheckUnavailableError) as exc:
        renumber.remote_collision("REQ-700")
    msg = str(exc.value)
    assert "REQ-700" in msg and "exited" in msg and "id-alloc.sh: not found" in msg


def test_main_refuses_when_the_recheck_gives_no_verdict(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_recheck(repo, "  return 2")
    assert renumber.main(["REQ-600", "REQ-700", "--yes"]) == 1
    assert "exited 2" in capsys.readouterr().err
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()


def test_recheck_runs_with_this_toolkit_as_adlc_toolkit_root(tmp_path, monkeypatch):
    """The partial's fallback arm reads ADLC_TOOLKIT_ROOT, so it is set to this toolkit.

    An inherited value is replaced, not trusted: it may name another install.
    """
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ADLC_TOOLKIT_ROOT", "/some/other/install")
    _stub_recheck(repo, '  printf "%s" "$ADLC_TOOLKIT_ROOT" > seen-root\n  return 0')
    assert renumber.remote_collision("REQ-700") is False
    assert (repo / "seen-root").read_text() == renumber.toolkit_root.toolkit_root()


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


# --- reserve-before-mutate (REQ-546 BR-8) -----------------------------------------

def _add_bare_remote(tmp_path, repo, name="origin.git"):
    """Give `repo` a writable local bare origin and push its main branch."""
    bare = tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=repo, check=True)
    return bare


def _ls_reservations(repo, kind):
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-remote", "origin", f"refs/adlc/ids/{kind}/*"],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def test_reserve_new_id_won_pushes_ref(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _add_bare_remote(tmp_path, repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    state = os.path.join(os.environ["HOME"], ".claude")
    os.makedirs(state)
    assert renumber.reserve_new_id("REQ-700") == "won"
    assert "refs/adlc/ids/req/700" in _ls_reservations(repo, "req")
    # BUG-256: the won reservation lands in the sandbox ledger, never the real one.
    with open(os.path.join(state, ".adlc-own-reservations"), encoding="utf-8") as fh:
        assert fh.read().startswith("req 700 ")


def test_reserve_new_id_degraded_when_no_remote(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)  # no origin
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    # A push with no origin cannot run -> degraded (non-blocking), never 'won'.
    assert renumber.reserve_new_id("REQ-700") in ("degraded", "unavailable")


def test_apply_reserves_new_id_on_remote(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _add_bare_remote(tmp_path, repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    # The new-id remote-collision recheck is orthogonal here — stub it False so the test
    # exercises the reserve-before-mutate step, not the recheck.
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    rc = renumber.main(["REQ-600", "REQ-700", "--yes"])
    assert rc == 0
    assert (repo / ".adlc" / "specs" / "REQ-700-demo").is_dir()
    assert "refs/adlc/ids/req/700" in _ls_reservations(repo, "req")


def test_apply_aborts_when_new_id_reserved_mid_flight(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    # Simulate the id being reserved by another allocator between recheck and reserve.
    monkeypatch.setattr(renumber, "reserve_new_id", lambda _id: "lost")
    rc = renumber.main(["REQ-600", "REQ-700", "--yes"])
    assert rc == 1
    # The rename must NOT have happened.
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()
    assert not (repo / ".adlc" / "specs" / "REQ-700-demo").exists()


# --- local-collision refusal (BUG-245) --------------------------------------------

def _init_bug_repo(tmp_path, files):
    """A repo whose .adlc/bugs holds `files` ({name: content}), committed, no origin."""
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    bugs = repo / ".adlc" / "bugs"
    bugs.mkdir(parents=True)
    for name, content in files.items():
        (bugs / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo, bugs


def _remote_checks_unavailable(monkeypatch):
    """Both remote checks degrade to 'proceed', as they do offline (BR-3)."""
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)
    monkeypatch.setattr(renumber, "reserve_new_id", lambda _id: "degraded")


def test_apply_refuses_to_overwrite_existing_local_bug(tmp_path, monkeypatch, capsys):
    repo, bugs = _init_bug_repo(tmp_path, {
        "BUG-005-crash.md": "id: BUG-005\nold bug\n",
        "BUG-010-crash.md": "id: BUG-010\nexisting bug\n",
    })
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    rc = renumber.main(["BUG-005", "BUG-010", "--yes"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists locally" in err
    assert ".adlc/bugs/BUG-010-crash.md" in err
    # Nothing mutated: the destination keeps its own content, the source is untouched.
    assert (bugs / "BUG-010-crash.md").read_text() == "id: BUG-010\nexisting bug\n"
    assert (bugs / "BUG-005-crash.md").read_text() == "id: BUG-005\nold bug\n"


def test_apply_refuses_duplicate_id_with_different_slug(tmp_path, monkeypatch, capsys):
    repo, bugs = _init_bug_repo(tmp_path, {
        "BUG-005-crash.md": "id: BUG-005\n",
        "BUG-010-other.md": "id: BUG-010\n",
    })
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    rc = renumber.main(["BUG-005", "BUG-010", "--yes"])
    assert rc == 1
    assert "BUG-010-other.md" in capsys.readouterr().err
    assert (bugs / "BUG-005-crash.md").is_file()
    assert not (bugs / "BUG-010-crash.md").exists()


def test_dry_run_also_refuses_local_collision(tmp_path, monkeypatch, capsys):
    repo, _bugs = _init_bug_repo(tmp_path, {
        "BUG-005-crash.md": "id: BUG-005\n",
        "BUG-010-crash.md": "id: BUG-010\n",
    })
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    rc = renumber.main(["BUG-005", "BUG-010"])
    assert rc == 1
    assert "DRY RUN" not in capsys.readouterr().out


def test_apply_refuses_existing_req_dir_even_if_empty(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    (repo / ".adlc" / "specs" / "REQ-700-demo").mkdir()
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    rc = renumber.main(["REQ-600", "REQ-700", "--yes"])
    assert rc == 1
    assert "already exists locally" in capsys.readouterr().err
    assert (repo / ".adlc" / "specs" / "REQ-600-demo" / "requirement.md").is_file()


def test_apply_refuses_when_destination_appears_after_plan(tmp_path, monkeypatch, capsys):
    repo, bugs = _init_bug_repo(tmp_path, {"BUG-005-crash.md": "id: BUG-005\n"})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(renumber, "remote_collision", lambda _id: False)

    def _reserve_while_another_writer_lands(_id):
        (bugs / "BUG-010-crash.md").write_text("racer\n", encoding="utf-8")
        return "won"

    monkeypatch.setattr(renumber, "reserve_new_id", _reserve_while_another_writer_lands)
    rc = renumber.main(["BUG-005", "BUG-010", "--yes"])
    assert rc == 1
    assert "appeared after the plan" in capsys.readouterr().err
    assert (bugs / "BUG-010-crash.md").read_text() == "racer\n"
    assert (bugs / "BUG-005-crash.md").read_text() == "id: BUG-005\n"


def test_rename_no_clobber_raises_on_existing_file(tmp_path):
    src, dst = tmp_path / "a.md", tmp_path / "b.md"
    src.write_text("a", encoding="utf-8")
    dst.write_text("b", encoding="utf-8")
    with pytest.raises(FileExistsError):
        renumber._rename_no_clobber(str(src), str(dst))
    assert src.read_text() == "a" and dst.read_text() == "b"


@pytest.mark.parametrize("is_dir", [False, True])
def test_rename_no_clobber_moves_when_destination_is_free(tmp_path, is_dir):
    src, dst = tmp_path / "a", tmp_path / "b"
    if is_dir:
        src.mkdir()
        (src / "f.md").write_text("x", encoding="utf-8")
    else:
        src.write_text("x", encoding="utf-8")
    renumber._rename_no_clobber(str(src), str(dst))
    assert not src.exists()
    assert (dst / "f.md" if is_dir else dst).read_text() == "x"


# --- number-keyed collision + link-path guard (BUG-245 follow-up) -------------------

def test_apply_refuses_zero_padded_duplicate(tmp_path, monkeypatch, capsys):
    repo, bugs = _init_bug_repo(tmp_path, {
        "BUG-005-crash.md": "id: BUG-005\n",
        "BUG-010-other.md": "id: BUG-010\n",
    })
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    rc = renumber.main(["BUG-005", "BUG-0010", "--yes"])
    assert rc == 1
    assert "BUG-010-other.md" in capsys.readouterr().err
    assert sorted(os.listdir(bugs)) == ["BUG-005-crash.md", "BUG-010-other.md"]


def test_apply_refuses_zero_padded_req_dir(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    (repo / ".adlc" / "specs" / "REQ-700-other").mkdir()
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    assert renumber.main(["REQ-600", "REQ-0700", "--yes"]) == 1
    assert "REQ-700-other" in capsys.readouterr().err
    assert (repo / ".adlc" / "specs" / "REQ-600-demo").is_dir()


def test_same_number_with_different_padding_is_rejected(tmp_path, monkeypatch, capsys):
    repo, bugs = _init_bug_repo(tmp_path, {"BUG-005-crash.md": "id: BUG-005\n"})
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    assert renumber.main(["BUG-005", "BUG-0005", "--yes"]) == 2
    assert "same number" in capsys.readouterr().err
    assert (bugs / "BUG-005-crash.md").is_file()


def test_different_number_sharing_a_prefix_is_not_a_collision(tmp_path, monkeypatch):
    # Benign path: BUG-0100 is 100, not 10, so a local BUG-010 must not block it.
    repo, bugs = _init_bug_repo(tmp_path, {
        "BUG-005-crash.md": "id: BUG-005\n",
        "BUG-010-other.md": "id: BUG-010\n",
    })
    monkeypatch.chdir(repo)
    _remote_checks_unavailable(monkeypatch)
    assert renumber.main(["BUG-005", "BUG-0100", "--yes"]) == 0
    assert (bugs / "BUG-0100-crash.md").read_text() == "id: BUG-0100\n"
    assert (bugs / "BUG-010-other.md").read_text() == "id: BUG-010\n"


def test_rename_no_clobber_link_refuses_when_precheck_misses(tmp_path, monkeypatch):
    # Bypass the up-front lexists check so the hard link is the only guard: this is
    # the race where dst appears between the check and the move.
    src, dst = tmp_path / "a.md", tmp_path / "b.md"
    src.write_text("mine", encoding="utf-8")
    dst.write_text("racer", encoding="utf-8")
    monkeypatch.setattr(renumber.os.path, "lexists", lambda _p: False)
    with pytest.raises(FileExistsError):
        renumber._rename_no_clobber(str(src), str(dst))
    assert dst.read_text() == "racer"
    assert src.read_text() == "mine"


def _no_hard_links(monkeypatch):
    def _link(_src, _dst):
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))
    monkeypatch.setattr(renumber.os, "link", _link)


def test_rename_no_clobber_falls_back_without_hard_links(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.md", tmp_path / "b.md"
    src.write_text("x", encoding="utf-8")
    _no_hard_links(monkeypatch)
    renumber._rename_no_clobber(str(src), str(dst))
    assert not src.exists()
    assert dst.read_text() == "x"


def test_rename_no_clobber_fallback_still_refuses_existing_dst(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.md", tmp_path / "b.md"
    src.write_text("a", encoding="utf-8")
    dst.write_text("b", encoding="utf-8")
    _no_hard_links(monkeypatch)
    with pytest.raises(FileExistsError):
        renumber._rename_no_clobber(str(src), str(dst))
    assert src.read_text() == "a" and dst.read_text() == "b"
