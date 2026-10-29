"""REQ-664 BR-15, BR-18 / AC-12, AC-18: the documentation lands with the code, and
the plan and the tool cannot drift apart silently (LESSON-019)."""

import os
import re

import harness_probe as hp

TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))


def _read(*parts):
    with open(os.path.join(TOOLKIT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _plan_items():
    text = _read(".adlc", "research", "multi-harness-plan.md")
    section = text.split("## 6. Verify on real installs before writing the specs")[1]
    section = section.split("\n## 7.")[0]
    items = {}
    for m in re.finditer(r"(?ms)^ ?(\d+)\. \*\*.*?(?=^ ?\d+\. \*\*|\Z)", section):
        items[int(m.group(1))] = m.group(0)
    return items


def test_plan_items_annotated():
    """Every one of the twelve §6 items names its probe id or why it is not probed,
    and agrees with the tool's COVERAGE map."""
    items = _plan_items()
    assert sorted(items) == list(range(1, 13))
    for n, text in items.items():
        assert "*Probe:*" in text, n
        keys = [k for k in hp.COVERAGE if k.rstrip("ab") == "6.%d" % n]
        assert keys, n
        for key in keys:
            entry = hp.COVERAGE[key]
            if entry.get("status") == "not-probed":
                assert "not probed" in text, n
            for pid in entry.get("probes", []):
                assert "`%s`" % pid in text, (n, pid)
        if n == 1:
            assert "headless half only" in text


def test_readme_and_changelog_carry_probe_text():
    readme = _read("tools", "adlc", "README.md")
    assert "## `adlc harness probe` (REQ-664)" in readme
    section = readme.split("## `adlc harness probe` (REQ-664)")[1].split("\n## ")[0]
    for probe in hp.CATALOGUE:
        assert "`%s`" % probe.id in section, probe.id
    for form in ("--list", "--dry-run", "--recover", "--only", "--keep", "--timeout"):
        assert form in section, form
    for code in ("| 0 |", "| 1 |", "| 2 |"):
        assert code in section, code
    assert "marker.json" in section and "surgical" in section
    assert "| `harness probe` |" in readme
    assert "last_probe" in readme
    changelog = _read("CHANGELOG.md")
    unreleased = changelog.split("## [Unreleased]")[1].split("\n## [")[0]
    assert "`adlc harness probe` (REQ-664)" in unreleased


def test_readme_consumer_mapping_and_residual():
    """BR-18: the two answered shapes, the two that stay unverified, and the
    single-launch residual beside the statement that a pass lifts an omission."""
    section = _read("tools", "adlc", "README.md").split(
        "## `adlc harness probe` (REQ-664)")[1].split("\n## ")[0]
    flat = " ".join(section.split())
    assert "The `git-c` wrapper shape is read from `wrapped-allow`" in flat
    assert "the `prefix` shape from `deny-under-allow`" in flat
    assert "The `env-prefix` and `shell-opener` shapes have no sub-variant here, so they " \
           "stay `unverified`" in flat
    residual = flat.split("**Residual: a `pass` is one sample.**")[1][:600]
    assert "single model sample" in residual and "lift an omission" in residual
    # The variant names the README cites are the ones the tool writes.
    for name in ("wrapped-allow", "deny-under-allow"):
        assert name in hp.ATD_VARIANTS
