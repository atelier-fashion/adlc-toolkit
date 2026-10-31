"""REQ-664 BR-1, BR-8, BR-9, BR-12 / AC-1, AC-14: the forms of `adlc harness probe`
that refuse, plan or list — and the ones that must work anywhere."""

import os

import pytest

import harness_probe as hp
from probe_helpers import Sandbox, listing


def test_list_prints_eleven_ids(tmp_path):
    sb = Sandbox(tmp_path, harnesses=())
    out = sb.run("--list", cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr
    rows = out.stdout.splitlines()[1:]
    assert [r.split()[0] for r in rows] == [p.id for p in hp.CATALOGUE]
    assert len(rows) == 11
    assert "6.10" in out.stdout and "claude" in out.stdout and "gemini" in out.stdout


def test_dry_run_lists_launches_and_user_files(tmp_path):
    """AC-1: the launch count with ask-tier-deny's seven, the layout, the one user
    file on codex and the two on gemini; nothing on disk changes."""
    sb = Sandbox(tmp_path)
    before = listing(sb.root, skip=("repo/.git",))
    out = sb.run("codex", "--dry-run")
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert "launches: 18" in text
    assert sum(1 for line in text.splitlines() if "ask-tier-deny/" in line) == 7
    assert "<run_dir>/repo" in text and "<run_dir>/wt" in text and "bare origin" in text
    edits = text.split("user files it would edit")[1].split("\n")
    assert "~/.codex/config.toml" in text
    assert "trustedFolders" not in text and "policies" not in text
    assert "outside-<run_id>" in text                    # allow_required_path (ADR-4)
    out = sb.run("gemini", "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "~/.gemini/trustedFolders.json" in out.stdout
    assert "~/.gemini/policies/adlc-probe-<run_id>.toml" in out.stdout
    assert "outside-" not in out.stdout
    out = sb.run("claude", "--dry-run")
    assert "user files it would edit" in out.stdout and "\n  none" in out.stdout
    assert listing(sb.root, skip=("repo/.git",)) == before
    assert edits


def test_usage_errors_create_nothing(tmp_path):
    """BR-1: an unknown name or probe id is exit 2 before anything is created; an
    absent binary is exit 2 and writes no result file."""
    sb = Sandbox(tmp_path, harnesses=("claude",))
    before = listing(sb.root, skip=("repo/.git",))
    for args in (("nope",), ("codex", "--only", "no-such-probe"), ()):
        out = sb.run(*args)
        assert out.returncode == 2, (args, out.stdout, out.stderr)
        assert "usage" in out.stderr.lower()
    out = sb.run("codex")
    assert out.returncode == 2
    assert "codex is not on PATH" in out.stderr
    assert not os.path.exists(sb.result_path("codex"))
    assert listing(sb.root, skip=("repo/.git",)) == before
    # Benign path: a known id is accepted.
    assert sb.run("codex", "--only", "shell-timeout", "--dry-run").returncode == 0


def test_cap_floor(tmp_path):
    """BR-8: with shell-timeout selected a cap under 180 s is refused before
    anything launches; 180 is accepted, and so is a small cap without it."""
    sb = Sandbox(tmp_path, harnesses=("claude",))
    out = sb.run("claude", "--only", "shell-timeout", "--timeout", "120")
    assert out.returncode == 2 and "180" in out.stderr
    assert not os.path.exists(sb.log)
    assert sb.run("claude", "--only", "shell-timeout", "--timeout", "180",
                  "--dry-run").returncode == 0
    out = sb.run("claude", "--only", "git-write-main", "--timeout", "5")
    assert out.returncode == 0, out.stderr


def test_list_and_dry_run_outside_repo(tmp_path):
    """BR-9: --list and --dry-run work anywhere; a launching form refuses outside
    a repository with exit 1 and launches nothing."""
    sb = Sandbox(tmp_path, harnesses=("claude",))
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    assert sb.run("--list", cwd=str(outside)).returncode == 0
    dry = sb.run("claude", "--dry-run", cwd=str(outside))
    assert dry.returncode == 0 and "refuses outside a git repository" in dry.stdout
    out = sb.run("claude", cwd=str(outside))
    assert out.returncode == 1 and "git repository" in out.stderr
    assert not os.path.exists(sb.log)


def test_launch_count_precedes_first_launch(tmp_path):
    """BR-12 / AC-14: the count line comes before the first launch, and a HOME with
    no ~/.agents, ~/.claude/skills or venv proceeds."""
    sb = Sandbox(tmp_path, harnesses=("claude",))
    assert not os.path.exists(os.path.join(sb.home, ".agents"))
    assert not os.path.exists(os.path.join(sb.home, ".claude", "skills"))
    out = sb.run("claude", "--only", "git-write-main", "--only", "arg-substitution")
    assert out.returncode == 0, out.stderr
    count = out.stderr.index("2 launches on claude")
    first = out.stderr.index("harness_launched")
    assert count < first


def test_recover_with_no_marker_is_a_no_op(tmp_path):
    sb = Sandbox(tmp_path, harnesses=())
    out = sb.run("codex", "--recover", cwd=str(tmp_path))
    assert out.returncode == 0 and "nothing to recover" in out.stdout


@pytest.mark.parametrize("bad", ["", "relative/path"])
def test_bad_adlc_home_refuses_a_launch(tmp_path, bad):
    sb = Sandbox(tmp_path, harnesses=("codex",))
    out = sb.run("codex", ADLC_HOME=bad)
    assert out.returncode == 1 and "ADLC_HOME" in out.stderr
    assert not os.path.exists(sb.log)


def test_dry_run_antigravity_edits_no_user_file(tmp_path):
    """REQ-658 BR-3, ADR-8: the plan lists every launch, names no user file and leaves
    the disk alone. Without `agy` on PATH it still prints: --dry-run launches nothing."""
    sb = Sandbox(tmp_path, harnesses=())
    before = listing(sb.root, skip=("repo/.git",))
    out = sb.run("antigravity", "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "binary agy: absent" in out.stdout
    assert "launches: 18" in out.stdout
    assert "skill-activation" in out.stdout and "arg-substitution" not in out.stdout
    assert "user files it would edit" in out.stdout and "\n  none" in out.stdout
    assert "recovery marker" not in out.stdout
    assert listing(sb.root, skip=("repo/.git",)) == before

