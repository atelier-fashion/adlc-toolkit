"""REQ-662 BR-2, BR-8: the `exec-no-bypass` and `exit-class-vocabulary` lints.

Both read every `exec` block under `harness/*.yml` raw, skip the `{flags: unverified}`
placeholder, and fail on a scan of zero blocks. `exec-no-bypass` matches with the
engine's own `exec_adapter.forbidden_in`; it is the backstop, and the control is the
engine's closed-world argv check (BR-16). Each fixture under
`fixtures/exec-lints/<case>/harness/` holds one violation; the must-not-fire cases are
the real tree and a Codex-shaped block carrying architecture ADR-7's forbidden list.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "tools" / "adlc"))
import exec_adapter  # noqa: E402
import harness_adapter  # noqa: E402
import harness_yaml  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "exec-lints"
CHECK_SH = REPO_ROOT / "tools" / "lint-skills" / "check.sh"


def no_bypass(case):
    return check.check_exec_no_bypass(REPO_ROOT, FIXTURES / case / "harness")


def vocabulary(case):
    return check.check_exit_class_vocabulary(REPO_ROOT, FIXTURES / case / "harness")


@pytest.mark.parametrize("case, key, entry", [
    ("yolo", "launch", "--yolo"),
    ("force", "resume", "--force"),
    ("skip-permissions", "launch", "--dangerously-skip-permissions"),
    ("two-token", "launch", "--ask-for-approval never"),
    ("equals-ask-for-approval", "launch", "--ask-for-approval never"),
    ("equals-approval-mode", "launch", "--approval-mode yolo"),
    ("config-override", "launch", "-c"),
    ("isolation", "config_isolation", "--allow-all"),
])
def test_exec_no_bypass_fires_on_each_spelling(case, key, entry):
    """AC-2: each spelling, `=` and two-token forms and a Codex `-c` override included."""
    findings = no_bypass(case)
    assert [(f.check, f.message) for f in findings] == [
        ("exec-no-bypass", f"exec.{key} holds the forbidden entry {entry!r}")]
    assert findings[0].file.endswith(".yml") and findings[0].line > 1


def test_exec_no_bypass_reads_the_rendered_argv_fixture():
    """BR-2: a clean template whose rendered argv fixture holds a forbidden entry fails."""
    findings = no_bypass("argv-fixture")
    assert [(f.file.rsplit("/", 2)[-2:], f.message) for f in findings] == [
        (["codex", "exec-argv.json"], "rendered argv 'resume' holds the forbidden entry '--force'")]


def test_exec_no_bypass_fires_on_an_operator_flag_that_begins_an_entry():
    """An operator's `--harness-flag --permission-mode bypassPermissions` passes the
    closed-world check by flag name, so a name that begins an entry is a finding."""
    [finding] = no_bypass("operator-flag")
    assert "operator_flags puts '--permission-mode'" in finding.message
    assert "'--permission-mode bypassPermissions'" in finding.message


def test_exec_no_bypass_fires_on_an_entry_the_matcher_can_never_match():
    """`forbidden_in` splits `--flag=value` in the argv only, so an `=`-spelled entry is inert."""
    assert exec_adapter.forbidden_in(["--approval-mode=yolo"], ["--approval-mode=yolo"]) is None
    [finding] = no_bypass("inert-entry")
    assert "'--approval-mode=yolo' never matches" in finding.message
    assert "spell it '--approval-mode yolo'" in finding.message


def test_exec_no_bypass_fires_on_a_token_another_adapter_forbids():
    """AC-2's union: a template token on any adapter's list fails, reported once per key."""
    findings = no_bypass("cross-adapter")
    assert [(f.file.rsplit("/", 1)[-1], f.message) for f in findings] == [
        ("claude.yml", f"exec.{key} holds '-p', which codex forbids: every launch and resume "
                       f"token must be outside the union of forbidden_flags")
        for key in ("launch", "resume")]


def test_exec_no_bypass_matches_with_the_engines_matcher(monkeypatch):
    """No second matcher: with the engine's `forbidden_in` blinded, the lint sees nothing."""
    assert no_bypass("yolo")
    monkeypatch.setattr(exec_adapter, "forbidden_in", lambda argv, forbidden: None)
    assert no_bypass("yolo") == []


def test_exec_no_bypass_passes_a_codex_shaped_block():
    """The must-not-fire case for ADR-7's whole Codex list, `-c`, `-p` and `--config` in it."""
    assert no_bypass("clean") == []
    assert vocabulary("clean") == []


def test_exit_class_vocabulary_is_closed(monkeypatch):
    """BR-8: a value outside ok | denied | timeout | error fails, and so does a widened
    engine set; the lint's set is the engine's."""
    assert check.EXIT_CLASS_VOCABULARY == ("ok", "denied", "timeout", "error")
    assert sorted(harness_adapter.EXIT_CLASSES) == sorted(check.EXIT_CLASS_VOCABULARY)
    [finding] = vocabulary("bad-exit-class")
    assert finding.check == "exit-class-vocabulary"
    assert finding.message == ("exec.exit_codes maps '42' to 'refused', outside the closed "
                               "ExitClass ok | denied | timeout | error")
    assert no_bypass("bad-exit-class") == []
    monkeypatch.setattr(harness_adapter, "EXIT_CLASSES",
                        harness_adapter.EXIT_CLASSES + ("refused",))
    widened = check.check_exit_class_vocabulary(REPO_ROOT)
    assert [f.file for f in widened] == ["tools/adlc/harness_adapter.py"]
    assert "not the closed ExitClass" in widened[0].message


def test_a_block_with_no_exit_codes_map_fails(tmp_path):
    (tmp_path / "x.yml").write_text("name: x\nexec:\n  exec_schema_version: 2\n"
                                    "  launch: [-p]\n")
    [finding] = check.check_exit_class_vocabulary(REPO_ROOT, tmp_path)
    assert finding.message == "the exec block declares no exit_codes map"


def test_an_unreadable_template_fails_rather_than_passing(tmp_path):
    (tmp_path / "x.yml").write_text("name: x\nexec:\n  exec_schema_version: 2\n"
                                    "  launch: [-p, 5]\n  resume: -p\n  forbidden_flags: --yolo\n"
                                    '  exit_codes: {"0": ok}\n')
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "exec-argv.json").write_text('["--yolo"]\n')
    messages = sorted(f.message for f in check.check_exec_no_bypass(REPO_ROOT, tmp_path))
    assert messages == [
        "exec.forbidden_flags is not a list of strings, so only the engine's seed is "
        "checked here",
        "exec.launch is not a list of string tokens, so it cannot be checked",
        "exec.resume is not a list of string tokens, so it cannot be checked",
        "the rendered argv must be a JSON object mapping each label to one argv (a list of "
        "strings)",
    ]


def test_a_scan_of_zero_exec_blocks_fails(capsys):
    """A vacuous run is never a pass: placeholder blocks only, so each lint fails."""
    for findings in (no_bypass("placeholder-only"), vocabulary("placeholder-only")):
        assert [f.message for f in findings] == [
            "scanned 0 exec blocks: a run that checked nothing is not a pass"]
    err = capsys.readouterr().err
    assert "exec-no-bypass: scanned 0 exec block(s) (none)" in err
    assert "skipped 2 without one (codex, cursor)" in err


def test_both_lints_are_inert_outside_the_toolkit(tmp_path):
    (tmp_path / "harness").mkdir()
    assert check.check_exec_no_bypass(tmp_path) == []
    assert check.check_exit_class_vocabulary(tmp_path) == []


def test_both_lints_pass_on_the_tree(capsys):
    """AC-12's must-not-fire case: the real adapters, placeholders skipped, not failed."""
    assert check.check_exec_no_bypass(REPO_ROOT) == []
    assert check.check_exit_class_vocabulary(REPO_ROOT) == []
    err = capsys.readouterr().err.splitlines()
    placeholders = sorted(p.stem for p in (REPO_ROOT / "harness").glob("*.yml")
                          if harness_yaml.load_file(str(p)).get("exec") == {"flags": "unverified"})
    for line_head in ("exec-no-bypass: scanned ", "exit-class-vocabulary: scanned "):
        [line] = [line for line in err if line.startswith(line_head)]
        assert not line.startswith(line_head + "0 ")
        assert line.endswith("skipped %d without one (%s)"
                             % (len(placeholders), ", ".join(placeholders) or "none"))


def test_template_tokens_share_nothing_with_forbidden_union():
    """AC-2, by plain extraction: every `exec.launch` and `exec.resume` token across
    `harness/*.yml` (each `--flag=value` split as the engine splits it) intersects the
    union of `forbidden_flags` and the engine's seed in the empty set."""
    tokens, forbidden = set(), set(exec_adapter.ENGINE_FORBIDDEN_FLAGS)
    for path in sorted((REPO_ROOT / "harness").glob("*.yml")):
        block = harness_yaml.load_file(str(path)).get("exec") or {}
        for key in ("launch", "resume"):
            for tok in block.get(key, []):
                tokens.add(tok)
                if tok.startswith("-") and "=" in tok:
                    tokens.update(tok.split("=", 1))
        forbidden.update(block.get("forbidden_flags", []))
    assert tokens, "no exec.launch or exec.resume token found under harness/"
    assert tokens & forbidden == set()


def test_check_sh_fails_on_a_fixture_template(tmp_path):
    """AC-2: `bash tools/lint-skills/check.sh` fails under `exec-no-bypass` on a fixture
    template holding `--yolo`."""
    root = tmp_path / "root"
    shutil.copytree(FIXTURES / "yolo" / "harness", root / "harness")
    (root / "tools").mkdir()
    os.symlink(REPO_ROOT / "tools" / "adlc", root / "tools" / "adlc")
    (root / "skills" / "probe").mkdir(parents=True)
    shutil.copy(Path(__file__).parent / "fixtures" / "clean.md",
                root / "skills" / "probe" / "SKILL.md")
    proc = subprocess.run(["bash", str(CHECK_SH), "--root", str(root)],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert ("harness/claude.yml:6: exec-no-bypass: exec.launch holds the forbidden entry "
            "'--yolo'") in proc.stdout.splitlines()
