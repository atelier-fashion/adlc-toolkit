"""Pin every integration-branch resolution site to `branches.integration`.

`.adlc/config.yml` may declare `branches.integration` — the branch feature
branches are cut from and PRs target (`dev`, `staging`, `main`, …). `/proceed`
Phase 0 step 4 reads it FIRST; only when it is absent does the signal-based
detection run (`gcp.staging_project`, a `verify-head-ref` workflow, staging-first
wording in `CLAUDE.md` → `staging`, else `main`). Before the key existed a
`dev` → `staging` → `main` repo declared a staging project like any staging-first
repo, so detection picked `staging` and the repo's head-ref check refused every
PR.

The rule lives in prose, in several skills, an agent and the workflow engine's
prompts. Prose has no type checker, so this test is the structural guard
(LESSON-012 posture): every site that resolves or re-derives the integration
branch must name the key, and the signal-based fallback must still be described
in `/proceed` step 4 so a repo with no key behaves exactly as before. It also
checks the config template documents the key as a real two-level YAML path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

KEY = "branches.integration"

#: Every file that resolves, records or re-derives the integration branch.
#: Adding a new resolution site means adding it here — the point is that no
#: site may silently drift back to "two-branch → staging, else main".
RESOLUTION_SITES = (
    # REQ-661: /proceed Step 0, the rule's home, lives in its companion.
    "proceed/phase-0-setup.md",
    "sprint/SKILL.md",
    "agents/pipeline-runner.md",
    "template-drift/SKILL.md",
    "wrapup/SKILL.md",
    "bugfix/SKILL.md",
    "workflows/adlc-sprint.workflow.js",
)


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", RESOLUTION_SITES)
def test_resolution_site_names_the_key(rel):
    assert KEY in _read(rel), f"{rel} resolves the integration branch without reading {KEY}"


def test_proceed_step4_reads_key_before_signals():
    """The key is rule 1; the three legacy signals follow it, in step 4."""
    text = _read("proceed/phase-0-setup.md")
    step4 = text.index("4. **Determine the integration branch")
    key_at = text.index(KEY, step4)
    staging_signal = text.index("`gcp.staging_project`", step4)
    head_ref_signal = text.index("verify-head-ref", step4)
    claude_md_signal = text.index("staging → main promotion", step4)
    assert key_at < staging_signal < head_ref_signal
    assert key_at < claude_md_signal
    # The fallback defaults are intact: a repo with no key still resolves
    # `staging` on a signal and `main` otherwise.
    fallback = text[key_at:text.index("**Always fetch before reasoning", key_at)]
    assert "(`staging` unless the project names another)" in fallback
    assert "otherwise `<integration-branch>` is `main`" in fallback
    # The fetch and never-hardcode-main rules survive.
    assert "git -C <repo-path> fetch origin" in text
    assert "never a hardcoded `main`" in text


def test_pre_merge_rebases_do_not_hardcode_main():
    """`/wrapup` step 7 and `/bugfix` Phase 5 rebase onto the PR's base."""
    for rel in ("wrapup/SKILL.md", "bugfix/SKILL.md"):
        text = _read(rel)
        assert "rebase origin/main" not in text, f"{rel} still rebases onto a hardcoded origin/main"
        assert "origin/<integration-branch>" in text


def test_workflow_prompts_carry_the_key_everywhere_they_resolve():
    """Every prompt that says 'two-branch' also names the key next to it."""
    text = _read("workflows/adlc-sprint.workflow.js")
    hits = [m.start() for m in re.finditer(r"two-branch", text)]
    assert hits, "expected the workflow prompts to describe the two-branch fallback"
    for pos in hits:
        window = text[max(0, pos - 400): pos + 400]
        assert KEY in window, f"workflow prompt near offset {pos} resolves without {KEY}"


def test_config_template_documents_the_key():
    """The template carries a commented `branches:` block whose key is `integration`.

    Uncommenting those two lines must yield a parseable document with
    `branches.integration` set — i.e. the documented example is a real
    two-level YAML path, not prose.
    """
    text = _read("templates/config-template.yml")
    assert "# branches:" in text and "#   integration:" in text
    assert "overrides" in text or "look no further" in text
    uncommented = re.sub(r"^# (branches:)$", r"\1", text, flags=re.M)
    uncommented = re.sub(r"^#   (integration: .*)$", r"  \1", uncommented, flags=re.M)
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(uncommented)
    assert doc["branches"]["integration"] == "dev"
    # The staging-first preset declares the branch it has always integrated on.
    preset = yaml.safe_load(_read("presets/ios-firebase-cloudrun.yml"))
    assert preset["branches"]["integration"] == "staging"


def test_readme_and_changelog_mention_the_key():
    assert KEY in _read("README.md")
    assert KEY in _read("CHANGELOG.md")
