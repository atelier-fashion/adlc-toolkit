"""REQ-648 BR-6 / AC-13: every reviewer documents the finding class and the severity mapping.

The block between ``<!-- finding-class -->`` and ``<!-- /finding-class -->`` is
defined once, in ``review/SKILL.md``, and copied byte for byte into each agent
that reports Phase-5 findings. Copies drift (LESSON-441); this test is the guard.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CANON = REPO_ROOT / "review" / "SKILL.md"
REVIEWERS = (
    "agents/correctness-reviewer.md",
    "agents/quality-reviewer.md",
    "agents/architecture-reviewer.md",
    "agents/test-auditor.md",
    "agents/security-auditor.md",
    "agents/reflector.md",
    "agents/lite-reviewer.md",
)
BLOCK_RE = re.compile(r"^<!-- finding-class -->\n.*?^<!-- /finding-class -->$", re.M | re.S)


def block_of(text):
    found = BLOCK_RE.findall(text)
    return found


def canonical():
    found = block_of(CANON.read_text(encoding="utf-8"))
    assert len(found) == 1, "review/SKILL.md must define the finding-class block exactly once"
    return found[0]


def test_canonical_block_states_the_contract():
    block = canonical()
    assert "^[a-z0-9]+(-[a-z0-9]+){0,5}$" in block, "the class regex"
    assert "reuse that class exactly" in block, "the reuse-within-run rule"
    for mapping in ("High → Major", "Medium → Minor", "Low → Nit", "Critical unchanged"):
        assert mapping in block, mapping
    assert "test-coverage gap with no other severity is Major" in block


@pytest.mark.parametrize("rel", REVIEWERS)
def test_finding_class_block_in_every_reviewer(rel):
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    found = block_of(text)
    assert len(found) == 1, f"{rel} must carry the finding-class block exactly once"
    assert found[0] == canonical(), f"{rel}'s finding-class block drifted from review/SKILL.md"
    assert re.search(r"\*\*Class\*\*:|class: `|\(class: ", text), f"{rel}'s template shows no class"


def test_drifted_copy_is_caught(tmp_path):
    """Must-not-pass: a copy with one word changed is not the canonical block."""
    text = (REPO_ROOT / REVIEWERS[0]).read_text(encoding="utf-8")
    drifted = text.replace("reuse that class exactly", "reuse that class", 1)
    assert drifted != text
    assert block_of(drifted)[0] != canonical()
    assert block_of("no block here") == []
