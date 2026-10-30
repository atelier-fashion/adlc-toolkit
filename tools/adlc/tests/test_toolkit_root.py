"""Tests for tools/adlc/toolkit_root.py (REQ-669 ADR-2, BR-2, BR-3, BR-7).

The root is derived from ``realpath(__file__)`` and accepted only when
``<root>/tools/adlc/toolkit_root.py`` IS the running file. Each refusal case has
a benign twin that must not refuse: the plugin cache copy and the symlinked
checkout are the two real install shapes (LESSON-440).
"""

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import sysconfig

import pytest

import toolkit_root

_SRC = os.path.realpath(toolkit_root.__file__)
_TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(_SRC)))


def _load(path, name="toolkit_root_under_test"):
    """Execute a copy of toolkit_root.py from ``path``, so ``__file__`` is ``path``."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _place(src, dest):
    os.makedirs(os.path.dirname(str(dest)), exist_ok=True)
    shutil.copy2(src, str(dest))
    return str(dest)


def _child(tree, code, *args):
    """Run ``code`` in an isolated child interpreter on the sandbox HOME."""
    return subprocess.run(
        [sys.executable, "-I", "-c", code] + [str(a) for a in args],
        capture_output=True, text=True, env=tree.env, cwd=tree.home,
    )


# --- the cache-shaped copy (BR-2) ----------------------------------------

_PRINT_ROOT = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('toolkit_root', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
    "print(m.toolkit_root())\n"
    "print(m.toolkit_file('tools/delegate/_machine_config.py'))\n"
)


def test_cache_shaped_copy_resolves_without_skills_symlink(cache_shaped_tree):
    """A cache copy (no .git, no ~/.claude/skills) reports its own root.

    The sandbox HOME is a git repo that encloses the copy, so a root taken from
    `git rev-parse --show-toplevel` would name HOME. The assertion on git's
    answer keeps the case honest: the copy really is inside another repo.
    """
    tree = cache_shaped_tree
    real_root = os.path.realpath(tree.root)
    out = _child(tree, _PRINT_ROOT,
                 os.path.join(tree.root, "tools", "adlc", "toolkit_root.py"))
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines == [
        real_root,
        os.path.join(real_root, "tools", "delegate", "_machine_config.py"),
    ]

    git = subprocess.run(
        ["git", "-C", os.path.join(tree.root, "tools", "adlc"),
         "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, env=tree.env,
    )
    assert git.returncode == 0, git.stderr
    assert os.path.realpath(git.stdout.strip()) == os.path.realpath(tree.home)


_ARM_PROBES = {
    "lane_check": (
        "import sys; sys.path.insert(0, sys.argv[1]); import lane_check as m\n"
        "print(m._loader_candidates()); print(m._loader().__file__)\n",
        ("tools", "delegate", "_machine_config.py"),
    ),
    "renumber": (
        "import sys; sys.path.insert(0, sys.argv[1]); import renumber as m\n"
        "print(m._find_partial('id-recheck.sh'))\n",
        ("partials", "id-recheck.sh"),
    ),
    "checks": (
        "import sys; sys.path.insert(0, sys.argv[1]); import checks as m\n"
        "from doctor import Profile\n"
        "p = Profile(os='Darwin', login_shell='', repo_root=sys.argv[2])\n"
        "print(m._partial_path(p, 'id-recheck.sh'))\n",
        ("partials", "id-recheck.sh"),
    ),
}


@pytest.mark.parametrize("module", sorted(_ARM_PROBES))
def test_fallback_arms_resolve_inside_cache_shaped_copy(cache_shaped_tree, module):
    """Each retired ``~/.claude/skills`` arm now lands in the copy being run.

    `checks` is given HOME as its profile root, which is what the doctor's
    retired git probe reported from inside this copy (TASK-128 replaced it with
    toolkit_root), so its project level misses and the toolkit level must
    answer. forge_config's twin is in test_forge_config.
    """
    tree = cache_shaped_tree
    code, rel = _ARM_PROBES[module]
    out = _child(tree, code, os.path.join(tree.root, "tools", "adlc"), tree.home)
    assert out.returncode == 0, out.stderr
    expected = os.path.join(os.path.realpath(tree.root), *rel)
    assert out.stdout.splitlines()[-1] == expected
    assert os.path.join(".claude", "skills") not in out.stdout


# --- the symlink checkout is unchanged (BR-3, benign path) ---------------

def test_symlink_checkout_resolves_unchanged(tmp_path):
    """Reached through ``~/.claude/skills``, the root is the real checkout.

    It equals what the retired ``realpath`` walk gave, so the symlink route
    sees no change. ``abspath`` would have walked to the link instead, which is
    why the rule is ``realpath`` (ASSUME-001).
    """
    link = tmp_path / "home" / ".claude" / "skills"
    link.parent.mkdir(parents=True)
    link.symlink_to(_TOOLKIT, target_is_directory=True)
    via_link = os.path.join(str(link), "tools", "adlc", "toolkit_root.py")

    module = _load(via_link)
    assert module.toolkit_root() == _TOOLKIT
    retired_walk = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(via_link))))
    assert module.toolkit_root() == retired_walk
    assert os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(via_link)))) == str(link)


def test_imported_module_resolves_this_checkout():
    assert toolkit_root.toolkit_root() == _TOOLKIT


# --- refusals: identity, not existence ------------------------------------

def test_refuses_copy_outside_a_tools_adlc_layout(tmp_path):
    """A copy whose walk lands on an unrelated directory refuses, naming both paths."""
    running = _place(_SRC, tmp_path / "flat" / "lib" / "toolkit_root.py")
    module = _load(running)
    with pytest.raises(module.ToolkitRootError) as exc:
        module.toolkit_root()
    msg = str(exc.value)
    assert os.path.join(os.path.realpath(str(tmp_path)), "tools", "adlc",
                        "toolkit_root.py") in msg
    assert os.path.realpath(running) in msg


@pytest.mark.parametrize("running_rel", [
    ("tools", "other", "toolkit_root.py"),
    ("tools", "adlc", "toolkit_root_copy.py"),
])
def test_refuses_when_derived_position_holds_another_file(tmp_path, running_rel):
    """A byte-identical decoy at ``<root>/tools/adlc/toolkit_root.py`` is not enough.

    The check is identity, so a file that merely exists where the walk expects
    one does not make a wrong root acceptable. The decoy itself, run from its
    own position, is accepted: the refusal is about which file is running.
    """
    root = tmp_path / "r"
    decoy = _place(_SRC, root.joinpath("tools", "adlc", "toolkit_root.py"))
    running = _place(_SRC, root.joinpath(*running_rel))

    module = _load(running)
    with pytest.raises(module.ToolkitRootError) as exc:
        module.toolkit_root()
    assert decoy in str(exc.value) or os.path.realpath(decoy) in str(exc.value)
    assert os.path.realpath(running) in str(exc.value)

    assert _load(decoy, "decoy").toolkit_root() == os.path.realpath(str(root))


def test_a_link_back_at_the_derived_position_is_accepted(tmp_path):
    """The limit the module docstring states: the check is about this file's place.

    A symlink planted at ``<root>/tools/adlc/toolkit_root.py`` that points back
    at the running copy resolves to the running file, so the root three levels
    above that copy is accepted. The guarantee is that the root comes from the
    file's real location, not that a planted tree is refused.
    """
    root = tmp_path / "r"
    running = _place(_SRC, root.joinpath("a", "b", "toolkit_root.py"))
    link = root.joinpath("tools", "adlc", "toolkit_root.py")
    link.parent.mkdir(parents=True)
    link.symlink_to(running)
    assert _load(running).toolkit_root() == os.path.realpath(str(root))


def test_toolkit_file_never_joins_onto_a_refused_root(tmp_path):
    running = _place(_SRC, tmp_path / "flat" / "lib" / "toolkit_root.py")
    (tmp_path / "VERSION").write_text("9.9.9\n")
    module = _load(running)
    with pytest.raises(module.ToolkitRootError) as exc:
        module.toolkit_file("VERSION")
    assert not isinstance(exc.value, module.ToolkitFileNotFound)


# --- toolkit_file ----------------------------------------------------------

def test_toolkit_file_returns_an_existing_file():
    assert toolkit_root.toolkit_file("tools/adlc/toolkit_root.py") == _SRC
    assert toolkit_root.toolkit_file("partials/id-recheck.sh") == os.path.join(
        _TOOLKIT, "partials", "id-recheck.sh")


@pytest.mark.parametrize("rel", [
    "..",
    "../VERSION",
    "tools/../VERSION",
    "partials/../../etc/passwd",
    "partials\\..\\VERSION",
])
def test_toolkit_file_rejects_dotdot_segments(rel):
    """Rejected lexically, even where the path would resolve inside the root."""
    assert os.path.isfile(os.path.join(_TOOLKIT, "VERSION"))
    with pytest.raises(toolkit_root.ToolkitRootError) as exc:
        toolkit_root.toolkit_file(rel)
    assert not isinstance(exc.value, toolkit_root.ToolkitFileNotFound)
    assert "'..'" in str(exc.value)


@pytest.mark.parametrize("rel", ["", "/etc/passwd", os.path.join(_TOOLKIT, "VERSION"), None])
def test_toolkit_file_rejects_empty_absolute_and_non_string(rel):
    with pytest.raises(toolkit_root.ToolkitRootError) as exc:
        toolkit_root.toolkit_file(rel)
    assert not isinstance(exc.value, toolkit_root.ToolkitFileNotFound)


@pytest.mark.parametrize("rel", ["partials/no-such-partial.sh", "partials"])
def test_toolkit_file_requires_an_existing_regular_file(rel):
    with pytest.raises(toolkit_root.ToolkitFileNotFound) as exc:
        toolkit_root.toolkit_file(rel)
    assert os.path.join(_TOOLKIT, rel) in str(exc.value)


# --- standard library only (BR-7, LESSON-395) -----------------------------

def _imported_modules(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in %s" % path
            names.add(node.module.split(".")[0])
    return names


def test_stdlib_only_imports():
    """Every import resolves to the interpreter's own standard library.

    The doctor imports this module, and the doctor must load on a machine with
    no delegation install and no PyYAML. Nothing that shells out to git is
    imported either, so the root cannot quietly come from `rev-parse`.
    """
    names = _imported_modules(_SRC)
    assert names, "non-vacuity: the module imports at least os"
    assert "subprocess" not in names
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    for name in sorted(names):
        if name in sys.builtin_module_names:
            continue
        spec = importlib.util.find_spec(name)
        assert spec is not None and spec.origin, name
        origin = os.path.realpath(spec.origin)
        assert origin.startswith(stdlib + os.sep), (name, origin)
        assert "site-packages" not in origin, (name, origin)


def test_doctor_import_closure_carries_toolkit_root_and_no_yaml():
    out = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import checks\n"
         "print('toolkit_root' in sys.modules, 'yaml' in sys.modules)\n",
         os.path.dirname(_SRC)],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "True False"


# --- the four modules no longer read ~/.claude/skills (AC-4) --------------

def _code_strings(path):
    """(enclosing function, string constant) for every non-docstring literal."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    found = []

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str) \
                    and id(child) not in docstrings:
                found.append((func, child.value))
            else:
                visit(child, func)

    visit(tree, None)
    return found


def _probe_data(name, value):
    """REQ-664: ``harness_probe.py`` names ``.claude/skills/`` only inside the
    throwaway repository it builds (a project-relative path, never the user's),
    and carries the canonical fence as data it hands to a harness, pinned by
    ``test_harness_probe_pins.py``. Neither is a toolkit read."""
    if name != "harness_probe.py":
        return False
    import harness_probe
    return value in (harness_probe.FENCE, harness_probe.CLAUDE_PROJECT_SKILLS)


def _adapter_surface_name(name, value):
    """REQ-657: ``harness_adapter.py`` names ``skills`` as one of the five adapter
    surfaces (a schema key, which every adapter declares ``mounted``), never as a
    directory it reads. Only that exact module-level constant is exempt."""
    if name != "harness_adapter.py" or value != "skills":
        return False
    import harness_adapter
    return "skills" in harness_adapter.SURFACES


def test_no_skills_dir_reads_outside_the_doctor_symlink_checks():
    """Only the doctor's symlink-route checks build a ``~/.claude/skills`` path.

    TASK-129's lint lists those checks as the one exception. Every other
    module, and the doctor's own ``_partial_path``, resolves toolkit files
    through toolkit_root.
    """
    adlc_dir = os.path.dirname(_SRC)
    hits = []
    for name in sorted(os.listdir(adlc_dir)):
        if not name.endswith(".py"):
            continue
        for func, value in _code_strings(os.path.join(adlc_dir, name)):
            if (value == "skills" or ".claude/skills" in value) \
                    and not _probe_data(name, value) \
                    and not (func is None and _adapter_surface_name(name, value)):
                hits.append((name, func))
    assert ("checks.py", "check_skills_symlink") in hits, "non-vacuity"
    assert [h for h in hits if h[0] != "checks.py"] == []
    assert ("checks.py", "_partial_path") not in hits
