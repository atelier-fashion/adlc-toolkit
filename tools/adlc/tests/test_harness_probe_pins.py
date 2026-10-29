"""REQ-664 pins: what the probe carries as data must equal its sources.

The probe reads neither source at run time (BR-2, BR-7), so these tests are what
catch drift: a change to `partials/README.md`'s fence, the routine allow entries
or `partials/intake.sh`'s redaction chain is a deliberate re-pin, not a silent
change in what the probe emits (LESSON-012).
"""

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import sysconfig

import harness_probe as hp

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))
MODULE = os.path.join(os.path.dirname(HERE), "harness_probe.py")


def _readme_block():
    text = open(os.path.join(TOOLKIT, "partials", "README.md"), encoding="utf-8").read()
    anchor = text.index("Skills invoke a model-2 partial like this")
    start = text.index("```bash\n", anchor) + len("```bash\n")
    end = text.index("```", start)
    return text[start:end]


def test_fence_byte_identical_to_partials_readme():
    """AC-7: the fence in the throwaway repo is partials/README.md's documented
    block with <name> = probe, byte for byte (architecture ADR-6)."""
    assert hp.FENCE == _readme_block().replace("<name>", "probe")
    assert hp.FENCE_FIRST_TOKEN == hp.FENCE_LINES[0].split()[0]


def _routine_allow_entries():
    perms = os.path.join(TOOLKIT, "templates", "permissions.yml")
    template = os.path.join(TOOLKIT, "templates", "claude-settings-template.json")
    if os.path.exists(template):
        with open(template, encoding="utf-8") as fh:
            return "claude", set(json.load(fh)["permissions"]["allow"])
    # REQ-657 replaces the template with permissions.yml; this test is re-pointed
    # in that change. Until then a textual membership check is the floor.
    return "yml", open(perms, encoding="utf-8").read()


def test_routine_set_subset_of_template():
    """AC-7: the four classes are a subset of the routine allow entries."""
    assert list(hp.ROUTINE_SET) == ["git read", "git write", "gh read", "shell utilities"]
    kind, source = _routine_allow_entries()
    for cls, entries in hp.ROUTINE_SET.items():
        assert entries, cls
        for entry in entries:
            if kind == "claude":
                assert ("Bash(%s:*)" % entry in source or "Bash(%s)" % entry in source), entry
            else:
                assert entry in source, entry
    # The ask tier is never in the routine set (plan Rule B).
    flat = [e for c in hp.ROUTINE_SET.values() for e in c]
    assert not any("--force" in e or e.startswith("rm") or "merge" == e for e in flat)


def _intake_pattern():
    text = open(os.path.join(TOOLKIT, "partials", "intake.sh"), encoding="utf-8").read()
    m = re.search(r"sed -i\.bak -E 's/(.*)/\[REDACTED\]/g'", text)
    assert m, "partials/intake.sh no longer carries the sed chain this pin reads"
    return m.group(1)


def test_redaction_pattern_matches_intake_chain():
    """ADR-3: the ported pattern is intake.sh's, with sed's line-bound classes."""
    translated = (_intake_pattern().replace("[^[:space:]]", "[^ \\t\\n\\r\\f\\v]")
                  .replace("[[:space:]]", "[ \\t\\r\\f\\v]"))
    assert translated == hp.REDACT_PATTERN


def test_redaction_output_matches_intake_chain(tmp_path):
    corpus = "\n".join([
        "plain line with nothing",
        "token sk-" + "A1b2" * 6 + " trailing",
        "aws AKIA" + "ABCDEFGHIJKLMNOP" + " key",
        "gh ghp_" + "x" * 40,
        "auth: Bearer " + "abc.def-ghi_" * 3,
        "export OPENAI_API_KEY = sk-not-long",
        "MOONSHOT_API_KEY=abc123 GITHUB_TOKEN: zzz",
        "AKIAABCDEFGHIJKLMNOP_TOKEN=leftmost-longest",
        "two on a line sk-" + "q" * 21 + " and ghp_" + "r" * 36,
    ]) + "\n"
    path = tmp_path / "corpus.txt"
    path.write_text(corpus)
    intake = os.path.join(TOOLKIT, "partials", "intake.sh")
    run = subprocess.run(["sh", "-c", '. "$1" && adlc_intake_redact "$2"', "sh", intake,
                          str(path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert path.read_text() == hp.redact(corpus)


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in the probe module"
            names.add(node.module.split(".")[0])
    return names


def test_module_imports_only_stdlib():
    """AC-14 / BR-2: nothing outside the standard library, nothing from tools/adlc
    or harness/, and no run-time read of the sources the pins above cover."""
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    for name in _imports(MODULE):
        assert name != "harness" and not name.startswith("harness"), name
        spec = importlib.util.find_spec(name)
        assert spec is not None, name
        origin = spec.origin or ""
        builtin = origin in ("built-in", "frozen") or name in sys.builtin_module_names
        in_stdlib = os.path.realpath(origin).startswith(stdlib + os.sep)
        site = "site-packages" in origin or "dist-packages" in origin
        assert (builtin or in_stdlib) and not site, (name, origin)
        assert not os.path.realpath(origin).startswith(os.path.join(TOOLKIT, "tools")), name
    source = open(MODULE, encoding="utf-8").read()
    for forbidden in ("permissions.yml\"", "claude-settings-template.json\"",
                      "partials/README.md\"", "intake.sh\""):
        assert forbidden not in source, forbidden
