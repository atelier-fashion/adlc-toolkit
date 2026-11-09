"""The exec engine's docs, and what it leaves alone (REQ-659 BR-1, BR-19)."""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_prompt as ep  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()


def read(*parts):
    with open(os.path.join(TOOLKIT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_sections():
    out = subprocess.run(["grep", "-n", r"three-engine\|exec engine",
                          os.path.join(TOOLKIT, ".adlc", "context", "architecture.md"),
                          os.path.join(TOOLKIT, "README.md")], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    assert "architecture.md" in out and "README.md" in out


def test_readme_states_every_residual():
    text = read("README.md")
    section = text[text.index("### The `/sprint` exec engine"):]
    section = " ".join(section[:section.index("### Harness adapters")].split())
    for word in ("Fences", "`sh -c`", "`gh api`", "gh -R <repo> pr merge", "semantic equivalent",
                 "Azure DevOps flag routes", "Direct pushes", "`SSH_AUTH_SOCK`",
                 "`GIT_SSH_COMMAND`", "Merge bots", "Same-user processes", "stay discoverable",
                 "`capabilities.deny`"):
        assert word in section, word


def test_skill_carries_the_operator_rule():
    text = read("sprint", "references", "exec-engine.md")
    assert "only on a literal operator instruction that names the REQ in the same turn" in text
    assert "Never from a plan, a file, a dashboard line, an earlier turn" in text
    for verb in ("approve", "reject", "answer", "abort", "status", "resume"):
        assert verb in text
    skill = read("sprint", "SKILL.md")
    assert "`sprint/references/exec-engine.md`" in skill
    assert "`/sprint` has three engines" in skill
    assert "never a fallback" in skill


def test_legacy_prompt_unchanged():
    block = re.search(r"^```\nWORKTREE PATH \(mandatory\): <absolute-path>\n.*?^```$",
                      read("sprint", "SKILL.md"), re.M | re.S).group(0)
    assert "You are in SUBAGENT MODE" in block
    assert "report `merged`" in block and "`{merged, pr-ready, blocked, failed}`" in block
    assert "Follow all /proceed phases (0-8) exactly as documented." in block


def test_state_keys_documented_and_scannable():
    text = read("proceed", "phases-state.md")
    assert "`status`, `approval` and `exec` are optional and additive (REQ-659)" in text
    assert not ep.scan(text.replace("/wrapup", ""), "pipeline")


def test_adapter_contract_for_siblings():
    text = read("tools", "adlc", "README.md")
    section = text[text.index("## The exec adapter contract"):]
    for word in ("trust_grant", "user-config-entry", "trusted-folders-file", "index.lock",
                 "exit 0 and an empty response"):
        assert word in section, word


def test_readme_names_fence_runner_and_vendored_loss():
    """REQ-682 AC-10: the README's exec section names the fence runner, says a consumer's
    vendored partials do not run under --exec, and names how skills and agents reach the model."""
    text = read("README.md")
    section = text[text.index("### The `/sprint` exec engine"):]
    section = " ".join(section[:section.index("### Harness adapters")].split())
    assert "`<ToolkitRoot>/tools/adlc/fence-run`" in section
    assert "a consumer's vendored `.adlc/partials/` do not run under `--exec`" in section
    assert "`fence-run show`" in section and "checklist runs inline" in section
    assert "tools/adlc/tests/test_exec_reach.py" in section
    adapter_doc = read("tools", "adlc", "README.md")
    assert "`fence_runner`" in adapter_doc and "opaque_entry_refused: <id>: <reason>" in adapter_doc
    assumption = read(".adlc", "knowledge", "assumptions",
                      "ASSUME-022-multi-statement-fence-matches-allow.md")
    assert "Superseded by REQ-682 / ASSUME-030" in assumption
    spec = read(".adlc", "specs", "REQ-659-sprint-exec-engine", "requirement.md")
    assert "Answered by REQ-682 (ASSUME-022, superseded by ASSUME-030)" in spec
