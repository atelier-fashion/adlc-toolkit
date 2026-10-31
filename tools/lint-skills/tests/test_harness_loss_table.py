"""REQ-656 BR-11, BR-17: `harness-loss-table`.

The README's per-harness loss tables and residual blocks are held to the adapters:
each expected fact is derived from `harness/<name>.yml` and a fresh render, so a table
cannot outlive the adapter it describes. Each fixture is the real README with one lie
or one omission in it; the must-not-fire case is the real README itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check  # noqa: E402

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def lint(tmp_path, text):
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    return [f.message for f in check.check_harness_loss_tables(REPO_ROOT, path)]


def section(name):
    start = README.index("<!-- harness-loss: %s -->" % name)
    return start, README.index("<!-- /harness-loss: %s -->" % name, start)


def in_section(name, old, new):
    start, end = section(name)
    body = README[start:end]
    assert old in body, old
    return README[:start] + body.replace(old, new) + README[end:]


def test_clean_on_the_real_readme():
    assert check.check_harness_loss_tables(REPO_ROOT) == []


def test_the_real_check_runs_in_the_lint():
    source = (REPO_ROOT / "tools" / "lint-skills" / "check.py").read_text(encoding="utf-8")
    assert "findings.extend(check_harness_loss_tables(root))" in source


@pytest.mark.parametrize("name, old, new, words", [
    # AC-11's three named lies.
    ("cursor", "command base: an entry names one command and everything under it",
     "subcommand granularity", "command base"),
    ("copilot", "a hard `--deny-tool` on the printed line, one per argv prefix of the deny tier",
     "the printed line carries no deny", "--deny-tool"),
    ("cursor", "`Shell(git)` and `Shell(gh)` are omitted, so `git` and `gh` prompt",
     "`Shell(git)` is allowed", "Shell(gh)"),
    # And the facts around them.
    ("copilot", "| Committed allowlist | no:", "| Committed allowlist | yes:", "committable"),
    ("cursor", "| Committed allowlist | yes:", "| Committed allowlist | no:", "committable"),
    ("cursor", "a hard `deny` in `.cursor/cli.json`", "a prompt", "`deny`"),
    ("copilot", "`git push:*`, `git branch:*` and the `git -C` prefix are omitted",
     "`git push:*` is omitted", "git branch:*"),
    ("cursor", "| Read-only reviewers | unverified:", "| Read-only reviewers | enforced:",
     "unverified"),
    ("cursor", "| Headless deny status | unverified:", "| Headless deny status | yes:",
     "unverified"),
    ("copilot", "| Headless deny status | unverified", "| Headless deny status | verified",
     "unverified"),
    ("cursor", "all `rm` and all `terraform` subcommands", "all `rm` subcommands", "terraform"),
    ("cursor", "which admits `npm publish`", "narrowly", "npm publish"),
])
def test_a_contradicted_fact_fails(tmp_path, name, old, new, words):
    messages = lint(tmp_path, in_section(name, old, new))
    assert messages and any(words.lower() in m.lower() for m in messages), messages
    assert all(m.startswith(name + ":") for m in messages), messages


@pytest.mark.parametrize("name, label", [
    ("copilot", "Transcript schema"), ("cursor", "Double skill discovery"),
    ("cursor", "Shell(npm) width"), ("cursor", "IDE permissions file"),
    ("copilot", "Subagent nesting depth"),
])
def test_a_missing_row_fails(tmp_path, name, label):
    start, end = section(name)
    body = "\n".join(line for line in README[start:end].split("\n")
                     if not line.replace("`", "").startswith("| %s |" % label))
    messages = lint(tmp_path, README[:start] + body + README[end:])
    assert any("no `%s` row" % label in m for m in messages), messages


def test_a_missing_block_fails(tmp_path):
    start, end = section("copilot")
    messages = lint(tmp_path, README[:start] + README[end:])
    assert any("no `harness-loss: copilot` block" in m for m in messages), messages


@pytest.mark.parametrize("name", ["copilot", "cursor"])
def test_omitting_the_residuals_block_fails(tmp_path, name):
    messages = lint(tmp_path, in_section(name, "**Declared residuals.**", "**Notes.**"))
    assert any("no Declared residuals block" in m for m in messages), messages


@pytest.mark.parametrize("name, old", [
    ("copilot", "Matching is spelling-level."),
    ("cursor", "`git rebase --exec`, "),
    ("copilot", "- The dogfood notes record the prompt count (REQ-656 BR-13).\n"),
    ("cursor", "- The `env-prefix` and `shell-opener` wrapper shapes are `unverified`, and no "
               "REQ-664 result lifts an omission resting on them.\n"),
])
def test_a_missing_residual_statement_fails(tmp_path, name, old):
    messages = lint(tmp_path, in_section(name, old, ""))
    assert any("the residuals omit" in m for m in messages), messages


def test_claiming_the_allowlist_is_the_gate_fails(tmp_path):
    text = in_section("copilot", "The allowlist is not the gate: REQ-659's structural halt is.",
                      "The allowlist is the gate.")
    messages = lint(tmp_path, text)
    assert any("claims the allowlist is the gate" in m for m in messages), messages


def test_claiming_chained_matching_is_verified_fails(tmp_path):
    text = in_section("copilot",
                      "Copilot's matching of chained commands (`;`, `&&`, `$()`) is unverified, "
                      "and every Copilot allow is untrustworthy against deny-tier commands until "
                      "REQ-664 shows it.",
                      "Chained-command matching is verified (`;`, `&&`, `$()`).")
    messages = lint(tmp_path, text)
    assert any("chained-command matching is verified" in m for m in messages), messages


def test_a_root_with_no_adapters_is_not_judged(tmp_path):
    assert check.check_harness_loss_tables(tmp_path) == []


# --------------------------------------------------------------------------- REQ-655
GATE_SPEC = REPO_ROOT / ".adlc" / "specs" / "REQ-655-codex-harness-adapter" / "requirement.md"
GATE_SPELLINGS = ("git push --force", "git push --force-with-lease",
                  "git push origin +HEAD:refs/heads/x", "git push origin --force",
                  "git branch -D x", "git -C <path> push --force")


def codex_rows():
    return check._loss_rows(check._loss_blocks(README)["codex"][1])


def test_codex_section_holds():
    rows = codex_rows()
    for label in check.LOSS_ROWS + check.LOSS_EXTRA_ROWS["codex"]:
        assert label in rows
    start, end = section("codex")
    body = README[start:end]
    assert "honour-system" in body and "8 000" in body
    # BR-11: said once by the adapter's own vocabulary, and held by the check.
    assert not [f for f in check.check_harness_loss_tables(REPO_ROOT) if "codex" in f.message]


@pytest.mark.parametrize("old, new, words", [
    ("| Committed allowlist | yes:", "| Committed allowlist | no:", "committable"),
    ("| Hook review |", "| Hooks |", "Hook review"),
    ("the `deny` tier renders as `prompt`", "the tier renders as a question", "`deny`"),
    ("`git push:*`, `git branch:*`", "`git status:*`", "git push:*"),
])
def test_a_codex_lie_is_caught(tmp_path, old, new, words):
    assert any(words in m for m in lint(tmp_path, in_section("codex", old, new)))


def test_codex_unmatched_row_follows_the_gate_record():
    import re
    record = GATE_SPEC.read_text(encoding="utf-8")
    row = codex_rows()["Unmatched git commands"]
    seen = {}
    for spelling in GATE_SPELLINGS:
        assert "`%s`" % spelling in row
        found = re.search(re.escape("`%s`" % spelling) + r" `(prompted|ran|sandbox-failed)`",
                          record)
        assert found, spelling
        seen[spelling] = found.group(1)
    if any(v in ("prompted", "sandbox-failed") for v in seen.values()):
        assert "prompts" in row
    if "ran" in seen.values():
        assert "may run" in row
    else:
        assert 'none reads "may run"' in row
