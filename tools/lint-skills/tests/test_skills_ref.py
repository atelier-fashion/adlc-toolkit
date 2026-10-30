"""REQ-666 BR-11 / AC-10: `skills-ref`, an optional PATH validator.

The real validator is not a dependency, so the installed path is exercised with a
fake one: a POSIX script that fails when a skill's `name:` differs from its
directory, and when the frontmatter carries a key outside the Agent Skills spec
(which proves the staged copy dropped `argument-hint`). The installed run with
the real validator is a manual, recorded step (the spec's resolved OQ-6).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / "tools" / "lint-skills" / "check.py"

_spec = importlib.util.spec_from_file_location("lint_check_skills_ref", CHECK)
_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["lint_check_skills_ref"] = _check
_spec.loader.exec_module(_check)

ETHOS, _ = _check.load_ethos_line(REPO_ROOT)

FAKE = """#!/bin/sh
[ "${1}" = validate ] || { echo "usage: skills-ref validate <dir>" >&2; exit 2; }
dir=${2}
base=$(basename "$dir")
name=$(sed -n 's/^name: *//p' "$dir/SKILL.md" | head -1)
if [ "$name" != "$base" ]; then echo "name '$name' does not match directory '$base' in $(cd "$dir" && pwd -P)" >&2; exit 1; fi
if sed -n '2,/^---$/p' "$dir/SKILL.md" | grep -q '^argument-hint:'; then echo "unexpected field argument-hint" >&2; exit 1; fi
echo "Valid skill: $dir"
"""


def _root(tmp_path: Path, skills: dict[str, str]) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "VERSION").write_text("0.0.0\n")
    for d, name in skills.items():
        (root / d).mkdir()
        (root / d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: x\nargument-hint: REQ-xxx\n---\n\n# /{d}\n\n{ETHOS}\n",
            encoding="utf-8")
    return root


def _env(tmp_path: Path, with_validator: bool) -> dict:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    if with_validator:
        exe = bindir / "skills-ref"
        exe.write_text(FAKE)
        exe.chmod(0o755)
    # A PATH that holds python's own directory and the system dirs, never a real
    # skills-ref the developer may have installed.
    path = os.pathsep.join([str(bindir), str(Path(sys.executable).parent), "/usr/bin", "/bin"])
    return {**os.environ, "PATH": path}


def _run(root: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), "--root", str(root)],
                          capture_output=True, text=True, env=env, check=False)


def test_absent_validator_skips(tmp_path):
    """AC-10: no validator on PATH is one SKIP line naming the install command
    and no finding (the repo-clean run in test_description_budget.py shows the
    lint then exits 0)."""
    out = _run(_root(tmp_path, {"alpha": "alpha"}), _env(tmp_path, with_validator=False))
    skips = [ln for ln in out.stderr.splitlines() if ln.startswith("skills-ref: SKIP")]
    assert len(skips) == 1 and "pip install skills-ref" in skips[0], out.stderr
    assert ": skills-ref:" not in out.stdout


def test_name_mismatch_fires_with_validator(tmp_path):
    """AC-10: with the validator installed, a skill whose `name:` differs from
    its directory is a finding; a matching skill is clean even though it carries
    `argument-hint`, because the staged copy omits that key."""
    out = _run(_root(tmp_path, {"alpha": "alpha", "beta": "gamma"}), _env(tmp_path, with_validator=True))
    found = [ln for ln in out.stdout.splitlines() if ": skills-ref:" in ln]
    assert len(found) == 1 and found[0].startswith("beta/SKILL.md:1: skills-ref:"), out.stdout
    assert "does not match" in found[0]
    # The temp path never leaks, given or resolved (the fake prints `pwd -P`).
    assert "adlc-skills-ref." not in found[0] and "<staged>/beta" in found[0], found[0]


def test_staged_copy_drops_only_the_harness_keys():
    text = "---\nname: a\nargument-hint: x\ndescription: d\n---\nargument-hint: body line stays\n"
    assert _check._skills_ref_copy(text) == "---\nname: a\ndescription: d\n---\nargument-hint: body line stays\n"


# REQ-661 BR-7: the validator sees the skill directory once, companions included.
FAKE_NEEDS_COMPANION = FAKE.replace(
    'echo "Valid skill: $dir"',
    'if [ -f "$dir/.want-companion" ] && [ ! -f "$dir/references/step.md" ]; then '
    'echo "companion not staged" >&2; exit 1; fi\necho "Valid skill: $dir"')


def test_companions_are_staged_with_their_skill(tmp_path):
    """A skill whose companion was not staged fails the fake; the real staging
    copies `references/` beside the SKILL.md, so it is clean. A second skill
    whose name mismatches is the positive control in the same run."""
    root = _root(tmp_path, {"alpha": "alpha", "beta": "gamma"})
    (root / "alpha" / "references").mkdir()
    (root / "alpha" / "references" / "step.md").write_text("# step\n", encoding="utf-8")
    env = _env(tmp_path, with_validator=True)
    exe = Path(env["PATH"].split(os.pathsep)[0]) / "skills-ref"
    exe.write_text(FAKE_NEEDS_COMPANION.replace(
        'if [ -f "$dir/.want-companion" ]', 'if [ "$base" = alpha ]'))
    out = _run(root, env)
    found = [ln for ln in out.stdout.splitlines() if ": skills-ref:" in ln]
    assert [ln.split(":")[0] for ln in found] == ["beta/SKILL.md"], out.stdout
    assert "companion not staged" not in out.stdout
