"""REQ-722 TASK-278 — the closed ``ModelFamily`` enum.

A family is declared and compared for equality, never inferred (BR-2), and
``unknown`` never counts as differing from anything (BR-3). These tests pin both
properties on the one module that defines the enum, so the config loader and
the harness adapter loader that read it cannot drift into a looser rule.
"""
import ast
import itertools
import os
import subprocess
import sys

import pytest

_DELEGATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _DELEGATE)
import model_family  # noqa: E402

_MODULE = os.path.join(_DELEGATE, "model_family.py")

#: The enum, restated. Importing it would make the pin agree with the subject by
#: construction; adding a family is a schema change that should fail here.
_EXPECTED = ("anthropic", "openai", "moonshot", "google", "meta", "other",
             "unknown")

_KNOWN = tuple(f for f in _EXPECTED if f != "unknown")

#: Values that look like a family to a reader who infers, and are not one.
_NOT_A_FAMILY = [
    ("case variant", "Anthropic"),
    ("upper case", "OPENAI"),
    ("leading space", " moonshot"),
    ("trailing newline", "google\n"),
    ("model name", "kimi-k2.6"),
    ("model name with a family inside", "claude-opus-4"),
    ("vendor model id", "gpt-4o"),
    ("member as a substring", "openai-compatible"),
    ("member as a prefix", "metallama"),
    ("empty string", ""),
    ("none", None),
    ("number", 1),
    ("boolean", True),
    ("sequence holding a member", ["anthropic"]),
    ("mapping keyed by a member", {"anthropic": True}),
    ("bytes", b"anthropic"),
]


def test_enum_is_closed_and_pinned():
    """The seven values, in a tuple, once each, with `unknown` among them."""
    assert model_family.MODEL_FAMILIES == _EXPECTED
    assert isinstance(model_family.MODEL_FAMILIES, tuple)
    assert len(set(model_family.MODEL_FAMILIES)) == len(_EXPECTED)
    assert model_family.UNKNOWN == "unknown"
    assert model_family.UNKNOWN in model_family.MODEL_FAMILIES


@pytest.mark.parametrize("family", _EXPECTED)
def test_parse_family_accepts_every_member(family):
    assert model_family.parse_family(family) == family


@pytest.mark.parametrize("label,value", _NOT_A_FAMILY,
                         ids=[label for label, _ in _NOT_A_FAMILY])
def test_parse_family_rejects_anything_else(label, value):
    with pytest.raises(ValueError):
        model_family.parse_family(value)


def test_rejection_names_the_allowed_values_and_not_the_value():
    """The config loader's reasons carry no file content, so the message a
    caller may forward names what is allowed, never what was written."""
    with pytest.raises(ValueError) as exc:
        model_family.parse_family("kimi-k2.6")
    message = str(exc.value)
    assert "kimi-k2.6" not in message
    for family in _EXPECTED:
        assert family in message


def test_families_compared_by_equality_only():
    """REQ-722 BR-2. Over every pair of known families, they differ exactly when
    the strings differ; and nothing outside the enum is compared at all — a
    case variant, a model name or a string containing a member raises rather
    than being read as a family."""
    for a, b in itertools.product(_KNOWN, repeat=2):
        assert model_family.families_differ(a, b) is (a != b), (a, b)
    for _, value in _NOT_A_FAMILY:
        for known in _KNOWN:
            with pytest.raises(ValueError):
                model_family.families_differ(value, known)
            with pytest.raises(ValueError):
                model_family.families_differ(known, value)
    # The inference cases by name: none of these is a same- or cross-family
    # verdict, because none of them is a family.
    for a, b in (("anthropic", "Anthropic"), ("moonshot", "kimi-k2.6"),
                 ("anthropic", "claude-opus-4"), ("openai", "gpt-4o")):
        with pytest.raises(ValueError):
            model_family.families_differ(a, b)


@pytest.mark.parametrize("family", _EXPECTED)
def test_unknown_never_differs(family):
    """REQ-722 BR-3: `unknown` on either side means "cannot be counted as
    cross-family", against every member including itself."""
    assert model_family.families_differ("unknown", family) is False
    assert model_family.families_differ(family, "unknown") is False


def test_other_is_a_family_like_any_other():
    """`other` is a declared family, not a wildcard: it differs from a named
    one and equals itself."""
    assert model_family.families_differ("other", "anthropic") is True
    assert model_family.families_differ("other", "other") is False


def test_module_imports_nothing():
    """ASSUME-003: the system `python3` must load it, so it may not import
    PyYAML, and it needs nothing from outside the standard library. It needs
    nothing at all, which is the simplest thing to pin."""
    with open(_MODULE, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), _MODULE)
    imports = [node for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert imports == [], [ast.dump(node) for node in imports]


def test_module_loads_without_site_packages():
    """The same property, by behaviour: isolated mode with no site directory,
    so a PyYAML or anything else installed for this interpreter is out of
    reach."""
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('model_family', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "assert 'yaml' not in sys.modules\n"
        "print(m.parse_family('moonshot'))\n"
    )
    r = subprocess.run([sys.executable, "-I", "-S", "-c", code, _MODULE],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "moonshot\n"
