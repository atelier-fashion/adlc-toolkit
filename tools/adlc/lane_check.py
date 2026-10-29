#!/usr/bin/env python3
"""The lite lane's mechanical check (REQ-652 BR-6, architecture ADR-3).

Diffs a worktree against a base ref and decides, by properties a machine can
check, whether a lite-lane REQ stayed inside the lane. The shell entry point is
``partials/lane-check.sh`` (``adlc_lane_check <worktree> <base-ref>``), which
always runs the INSTALLED toolkit's copy of this file, never one from the tree
under check. This module can also be run by path::

    python3 tools/adlc/lane_check.py --worktree <path> --base <ref>

The caller passes ``origin/<integrationBranch>`` as the base (LESSON-391, never
local ``main``) and fetches it first; this module does not fetch.

Contract
--------
Exit ``0`` pass, ``1`` escalate, ``2`` error. Stdout carries one fact per line
(LESSON-572)::

    lane_check=<pass|escalate|error>
    files_counted=<n>
    trigger=<t>          # then one trigger/detail pair per failing fact
    detail=<path-or-reason>

On ``pass`` and ``escalate`` both header lines are always printed. On
``error`` the output is exactly three lines — ``lane_check=error``,
``trigger=check-error``, ``detail=<reason>`` — and ``files_counted`` is
**omitted**: no count was made, and a ``0`` would read as a fact about the
diff. Every ``detail`` is a single line that no ``splitlines()`` reader can
split: a backslash is written ``\\\\``, and control characters, Unicode line
and paragraph separators, bidi and zero-width format characters, the BOM and
undecodable bytes are written as ``\\xNN`` / ``\\uNNNN`` escapes, so every
``detail`` reads back unambiguously.

**An error is never a pass** (LESSON-581). A dirty worktree, a base ref that
does not resolve, an empty diff against the base (a lite REQ always has
commits, so an empty diff means the base is wrong), any git failure, a config
that cannot be read at the base or fails its schema, bad arguments, and any
exception nobody planned for all produce the error contract. ``/proceed``
treats an error as an escalation, which is the conservative direction. There
is no ``--help``: an exit 0 that printed usage would read as a pass, so it is
refused like any other unknown argument.

Rules
-----
Every rule is evaluated and every failing fact is reported, in this order:

* ``blocked-path`` — one pair per changed file matching ``blocked_paths``
  (matched case-insensitively, so ``src/Auth/`` and ``dockerfile`` are caught),
  and one pair, ``symlink: <path>``, per change whose old or new mode is a
  symlink (``120000``): a link can point a harmless-looking path anywhere.
  Every changed file is checked, including files excluded from the count, so a
  test file under ``infra/`` is still blocked.
* ``dependency`` — one pair per changed lockfile or manifest, and one pair,
  ``submodule: <path>``, per change whose old or new mode is a gitlink
  (``160000``). Lockfiles and manifests match by **basename anywhere in the
  tree**, case-insensitively (``apps/web/package.json`` is a manifest, so is
  ``Package.resolved`` deep inside an ``.xcodeproj``); the names are basename
  globs, so ``requirements-dev.txt`` and ``build.gradle.kts`` match. A fixture
  named ``package.json`` under ``tests/`` therefore escalates too — the
  conservative direction. The list is fixed; a project that needs another
  manifest adds it to ``blocked_paths``.
* ``deploy-units`` — only when ``deploy_units`` is declared. Each changed,
  counted file maps to the unit of the first glob it matches (in the order
  written); files matching none are ignored; more than one distinct unit
  fails, and the detail lists the units, sorted (``admin, website``).
* ``max-files`` — changed files not matching ``count_exclude`` are counted;
  more than ``max_files`` fails with a detail like ``4 > 3``.

Changed files come from ``git diff --raw -z --no-renames <base>...HEAD``.
``--no-renames`` is deliberate: with rename detection a move *out of* a
blocked directory lists only the new path, and the blocked one disappears from
the check. So a rename is two changed files — the deletion and the addition —
and both are checked and both are counted. ``--raw`` carries each side's file
mode, which is what the symlink and submodule facts read;
``--ignore-submodules=none`` keeps a ``.gitmodules`` ``ignore = all`` from
hiding a gitlink change.

Globs (:func:`glob_match`) are matched against repo-relative POSIX paths and
are anchored at the repo root: ``*``, ``?`` and ``[...]`` stay within one
path segment, ``**/`` is zero or more directories, and a trailing ``/**`` is
everything beneath that directory (not the directory entry itself). Every
pattern — the defaults and a project's, in all three lists and the
``deploy_units`` keys — is normalized first (:func:`normalize_pattern`):
leading ``./`` and ``/`` are dropped, runs of ``/`` collapse, a trailing ``/``
becomes ``/**``, and a pattern with no glob character also matches everything
beneath it (``infra`` is ``infra`` or ``infra/**``). An empty pattern is a
schema error. ``blocked_paths`` and the dependency names match
case-insensitively; ``count_exclude`` and ``deploy_units`` are case-sensitive.

Config
------
``.adlc/config.yml`` **as committed at the base ref**, section ``lanes.lite``
(optional)::

    lanes:
      lite:
        max_files: 3                       # int >= 1; replaces the default
        blocked_paths: ["packages/domain/**"]   # EXTENDS the defaults
        count_exclude: ["content/**"]           # EXTENDS the defaults
        deploy_units: {"apps/web/**": web}      # glob -> unit name

The file is read with ``git ls-tree`` / ``git cat-file`` at the base, never
from the worktree's disk, so the branch under check cannot loosen its own
limits — not by committing a new config (which is a blocked path anyway), and
not with ``skip-worktree`` or a gitignored local copy. Absent at the base, the
defaults apply. Present but a symlink, a directory, a submodule, or larger than
:data:`CONFIG_CAP_BYTES`, it is an error.

A file whose bytes do not contain ``lanes`` (nor a backslash, which a YAML
escape could spell the key with, nor a NUL, which a UTF-16 encoding would
carry) is **never parsed**, so the defaults apply even on an interpreter
without PyYAML. Mentions on whole-line comments do not count, so a config
copied from the template, whose example is commented out, is not parsed
either. Anything else is parsed: a flow mapping, an indented document or a
``lanes`` followed by a trailing comment are all loaded, which is the safe
direction. Parsing goes through the shared loader,
``tools/delegate/_machine_config.load_machine_config`` (the same one
``forge_config.py`` uses), located and executed **by path** exactly as
``forge_config`` does, so nothing is put on ``sys.path`` and this file runs
when executed by path with no package context; the bytes are handed to it in a
private temporary file. That loader is a generic strict-YAML reader (duplicate
keys, aliases and merge keys refused, PyYAML imported lazily); its closed
schema lives in a separate function for the ``delegate:`` section and is not
applied here. Every refusal the loader makes — including
``dependency-missing`` (no PyYAML) — is an error here: unlike the forge
consumer, nothing about the lane is tolerated as unconfigured.

``lanes.lite`` is then validated against a closed schema: an unknown key under
``lanes`` or ``lanes.lite``, a section that is not a mapping, ``max_files``
that is not an integer >= 1 (a boolean is not an integer), a list that is not a
list of strings, a ``deploy_units`` that is not a string-to-string mapping, or
an empty pattern anywhere is an error, never a silent skip (REQ-609). A key
written with no value (``max_files:`` alone, or a ``lite:`` whose children are
all commented out) is the same as an unwritten key — the forge reader's
precedent — and leaves the default in place.
"""

import argparse
import collections
import fnmatch
import importlib.util
import os
import posixpath
import re
import subprocess
import sys
import tempfile

# --- the vocabulary (architecture.md "Vocabulary") --------------------------

RESULT_PASS = "pass"
RESULT_ESCALATE = "escalate"
RESULT_ERROR = "error"

RC_PASS = 0
RC_ESCALATE = 1
RC_ERROR = 2

TRIGGER_BLOCKED_PATH = "blocked-path"
TRIGGER_DEPENDENCY = "dependency"
TRIGGER_DEPLOY_UNITS = "deploy-units"
TRIGGER_MAX_FILES = "max-files"
TRIGGER_CHECK_ERROR = "check-error"

# --- defaults (architecture ADR-3) ------------------------------------------
# Mirrored in partials/lane-check.md's `lane-defaults` blocks; a test parses
# those blocks and fails when the two disagree.

#: Always blocked. A project's ``blocked_paths`` is added to this, never
#: substituted for it, so a project cannot quietly unblock ``.github/**``.
#: Matched case-insensitively.
DEFAULT_BLOCKED_PATHS = (
    # CI
    ".github/**",
    ".gitlab-ci.yml",
    ".gitlab/**",
    ".circleci/**",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    "Jenkinsfile",
    "bitbucket-pipelines.yml",
    ".buildkite/**",
    # deploy and infra
    "deploy/**",
    "infra/**",
    "infrastructure/**",
    "terraform/**",
    "**/*.tf",
    "**/*.tfvars",
    "**/k8s/**",
    "**/helm/**",
    "charts/**",
    "**/Dockerfile*",
    "**/Containerfile*",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/compose.yml",
    "**/compose.yaml",
    "**/cloudbuild*.yml",
    "**/cloudbuild*.yaml",
    "**/serverless.yml",
    "**/serverless.yaml",
    "vercel.json",
    "firebase.json",
    "**/fastlane/**",
    # data
    "**/migrations/**",
    "**/db/migrate/**",
    "**/alembic/**",
    "**/*.sql",
    "**/*.proto",
    "**/*.prisma",
    "**/*.graphql",
    "**/openapi*.*",
    "**/schema*/**",
    "**/schema*.*",
    # security
    "**/auth/**",
    "**/security/**",
    "**/*.rules",
    "firestore.rules",
    "**/.env*",
    "**/*.pem",
    "**/*.key",
    "**/*.entitlements",
    # pipeline and agent config
    ".adlc/config.yml",
    ".adlc/partials/**",
    ".adlc/tools/**",
    ".adlc/workflows/**",
    ".claude/**",
    ".mcp.json",
    "**/CLAUDE.md",
    "**/AGENTS.md",
    # git hooks and package-manager config
    ".husky/**",
    ".githooks/**",
    ".pre-commit-config.yaml",
    "lefthook.yml",
    ".gitmodules",
    "**/.npmrc",
    "**/.yarnrc*",
    "lefthook.yaml",
    ".lefthook.yml",
    ".lefthook.yaml",
    "**/.lintstagedrc*",
    # more CI
    ".travis.yml",
    ".drone.yml",
    ".gitea/**",
    ".forgejo/**",
    "appveyor.yml",
    "bitbucket-pipelines.yaml",
    "**/azure-pipelines*.yml",
    "**/azure-pipelines*.yaml",
    # more deploy
    "netlify.toml",
    "fly.toml",
    "app.yaml",
    "Procfile",
    "wrangler.toml",
    "Pulumi.yaml",
    "cdk.json",
    "**/*.bicep",
    # code that runs at install or build time
    ".yarn/releases/**",
    ".pnpmfile.cjs",
    ".pnp.cjs",
    "pnpm-workspace.yaml",
    "**/gradle/wrapper/**",
    "**/gradlew",
    "**/gradlew.bat",
    "**/settings.gradle*",
    "**/gradle.properties",
    ".mvn/**",
    "**/mvnw",
    ".cargo/**",
    "**/build.rs",
    # more agent and editor config
    "**/CLAUDE.local.md",
    "**/GEMINI.md",
    ".cursor/**",
    ".cursorrules",
    ".codex/**",
    ".gemini/**",
    ".vscode/tasks.json",
    ".devcontainer/**",
    # the project's ADLC context names the gates every later run executes
    ".adlc/context/**",
    # the lane check's own machinery, where the toolkit itself is the project
    "tools/adlc/lane_check.py",
    "tools/delegate/_machine_config.py",
    "partials/lane-check.sh",
    "partials/forge.sh",
    "proceed/phases-lite.md",
)

#: Lockfiles, matched case-insensitively by basename anywhere in the tree.
DEPENDENCY_LOCKFILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "Gemfile.lock",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "go.work.sum",
    "Package.resolved",
    "Podfile.lock",
    "composer.lock",
    "pubspec.lock",
    ".terraform.lock.hcl",
    "deno.lock",
    "flake.lock",
    "mix.lock",
    "packages.lock.json",
    "MODULE.bazel.lock",
)

#: Manifests, matched case-insensitively by basename anywhere in the tree
#: (basename globs).
DEPENDENCY_MANIFESTS = (
    "package.json",
    "pyproject.toml",
    "requirements*.txt",
    "Pipfile",
    "setup.py",
    "setup.cfg",
    "Gemfile",
    "Cargo.toml",
    "go.mod",
    "go.work",
    "Package.swift",
    "Podfile",
    "build.gradle*",
    "libs.versions.toml",
    "pom.xml",
    "*.csproj",
    "composer.json",
    "pubspec.yaml",
    "Directory.Packages.props",
    "*.gemspec",
    "mix.exs",
)

DEPENDENCY_FILES = DEPENDENCY_LOCKFILES + DEPENDENCY_MANIFESTS

#: Not counted toward ``max_files`` (still checked against the two lists
#: above). A project's ``count_exclude`` is added to this. Case-sensitive.
DEFAULT_COUNT_EXCLUDE = (
    "**/test/**",
    "**/tests/**",
    "**/__tests__/**",
    "**/*.test.*",
    "**/*.spec.*",
    "**/test_*.py",
    "**/*_test.*",
    ".adlc/**",
    "CHANGELOG*",
)

DEFAULT_MAX_FILES = 3

#: The closed schema (REQ-609: an unknown key is an error, not a skip).
LANES_KEYS = ("lite",)
LITE_KEYS = ("max_files", "blocked_paths", "count_exclude", "deploy_units")

#: The config's path inside the tree, as git names it.
CONFIG_RELPATH = ".adlc/config.yml"

#: Hard cap on the config read from the base, the shared loader's own cap: a
#: few lane limits have no business being larger, and nothing unbounded is
#: read into memory or handed to the parser.
CONFIG_CAP_BYTES = 65536

#: File modes, as ``git diff --raw`` and ``git ls-tree`` spell them.
MODE_REGULAR = "100644"
MODE_SYMLINK = "120000"
MODE_GITLINK = "160000"
_REGULAR_BLOB_MODES = (b"100644", b"100755")


class LaneCheckError(Exception):
    """Anything that makes the check unable to decide. Always ``error``."""


#: One changed path and the file modes on each side of the diff.
ChangedFile = collections.namedtuple("ChangedFile", "path old_mode new_mode")


class LaneConfig(object):
    """The effective rule set: defaults extended (or, for ``max_files``,
    replaced) by the project's ``lanes.lite``."""

    __slots__ = ("blocked_paths", "count_exclude", "dependency_files",
                 "max_files", "deploy_units")

    def __init__(self, blocked_paths, count_exclude, dependency_files,
                 max_files, deploy_units):
        self.blocked_paths = tuple(blocked_paths)
        self.count_exclude = tuple(count_exclude)
        self.dependency_files = tuple(dependency_files)
        self.max_files = max_files
        self.deploy_units = list(deploy_units)   # [(glob, unit)], in order


def effective_config(overrides=None):
    """The :class:`LaneConfig` for a validated ``lanes.lite`` override dict."""
    overrides = overrides or {}
    return LaneConfig(
        blocked_paths=DEFAULT_BLOCKED_PATHS + tuple(overrides.get("blocked_paths", ())),
        count_exclude=DEFAULT_COUNT_EXCLUDE + tuple(overrides.get("count_exclude", ())),
        dependency_files=DEPENDENCY_FILES,
        max_files=overrides.get("max_files", DEFAULT_MAX_FILES),
        deploy_units=list(overrides.get("deploy_units", {}).items()),
    )


# --- glob matching ----------------------------------------------------------

_GLOB_CHARS = frozenset("*?[")
_SLASH_RUN_RE = re.compile("/{2,}")


def normalize_pattern(pattern):
    """The tuple of globs one written ``pattern`` stands for; ``()`` if empty.

    Leading ``./`` and ``/`` are dropped (every pattern is anchored at the repo
    root already, and silently never matching ``/infra/**`` or ``./infra/**``
    would fail open), runs of ``/`` collapse, and a trailing ``/`` becomes
    ``/**``. A pattern with no glob character at all names a path, and a path
    may be a directory, so it also matches everything beneath it: ``infra`` is
    ``("infra", "infra/**")``. An empty result means the pattern names nothing;
    :func:`validate_lanes` refuses one in a project's config.
    """
    p = _SLASH_RUN_RE.sub("/", pattern)
    while True:
        if p.startswith("./"):
            p = p[2:]
        elif p.startswith("/"):
            p = p[1:]
        else:
            break
    if not p:
        return ()
    if p.endswith("/"):
        return (p + "**",)
    if not _GLOB_CHARS.intersection(p):
        return (p, p + "/**")
    return (p,)


def glob_match(path, pattern, ignore_case=False):
    """True if repo-relative POSIX ``path`` matches ``pattern``.

    ``pattern`` is normalized by :func:`normalize_pattern` first. ``fnmatch``
    alone lets ``*`` cross ``/``, so the pattern and the path are split into
    segments and each non-``**`` segment is matched with ``fnmatchcase``
    against exactly one path segment. A ``**`` segment matches zero or more
    whole segments, except at the end of the pattern, where it must match at
    least one (``deploy/**`` is everything *beneath* ``deploy``). With
    ``ignore_case`` both sides are lower-cased first.
    """
    if ignore_case:
        path, pattern = path.lower(), pattern.lower()
    segs = path.split("/")
    return any(_match_segments(segs, p.split("/")) for p in normalize_pattern(pattern))


def _match_segments(segs, pats):
    if not pats:
        return not segs
    head = pats[0]
    if head == "**":
        rest = pats[1:]
        if not rest:
            return len(segs) >= 1
        return any(_match_segments(segs[i:], rest) for i in range(len(segs) + 1))
    if not segs:
        return False
    return fnmatch.fnmatchcase(segs[0], head) and _match_segments(segs[1:], pats[1:])


def _matches_any(path, patterns, ignore_case=False):
    return any(glob_match(path, p, ignore_case) for p in patterns)


def _is_dependency_file(path, names):
    base = posixpath.basename(path).lower()
    return any(fnmatch.fnmatchcase(base, n.lower()) for n in names)


# --- the rules --------------------------------------------------------------

def _as_change(item):
    """A :class:`ChangedFile`; a bare path is a regular file on both sides."""
    if isinstance(item, ChangedFile):
        return item
    return ChangedFile(item, MODE_REGULAR, MODE_REGULAR)


def _has_mode(change, mode):
    return mode in (change.old_mode, change.new_mode)


def evaluate(files, config):
    """Apply every rule to ``files``. Returns ``(files_counted, failures)``.

    ``files`` holds :class:`ChangedFile` entries or bare paths (a regular file
    on both sides). ``failures`` is a list of ``(trigger, detail)`` in rule
    order, then diff order; empty means pass.
    """
    changes = [_as_change(f) for f in files]
    failures = []
    for change in changes:
        if _matches_any(change.path, config.blocked_paths, ignore_case=True):
            failures.append((TRIGGER_BLOCKED_PATH, change.path))
        if _has_mode(change, MODE_SYMLINK):
            failures.append((TRIGGER_BLOCKED_PATH, "symlink: " + change.path))
    for change in changes:
        if _is_dependency_file(change.path, config.dependency_files):
            failures.append((TRIGGER_DEPENDENCY, change.path))
        if _has_mode(change, MODE_GITLINK):
            failures.append((TRIGGER_DEPENDENCY, "submodule: " + change.path))

    counted = [c.path for c in changes if not _matches_any(c.path, config.count_exclude)]

    if config.deploy_units:
        units = set()
        for path in counted:
            for unit_glob, unit in config.deploy_units:
                if glob_match(path, unit_glob):
                    units.add(unit)
                    break
        if len(units) > 1:
            failures.append((TRIGGER_DEPLOY_UNITS, ", ".join(sorted(units))))

    if len(counted) > config.max_files:
        failures.append((TRIGGER_MAX_FILES,
                         "%d > %d" % (len(counted), config.max_files)))
    return len(counted), failures


# --- the shared loader, executed by PATH (mirrors forge_config._loader) -----

_LOADER_REL = ("tools", "delegate", "_machine_config.py")

_HELPER_UNRESOLVED = object()
_helper_module = _HELPER_UNRESOLVED


def _toolkit_root_helper():
    """This file's sibling ``toolkit_root`` module, executed by path, or ``None``.

    Copied from ``forge_config._toolkit_root_helper``: by explicit path, never
    on ``sys.path``, and ``None`` when this file was vendored without it.
    """
    global _helper_module
    if _helper_module is not _HELPER_UNRESOLVED:
        return _helper_module
    _helper_module = None
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "toolkit_root.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("toolkit_root", path)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _helper_module = module
    except Exception:  # why this is broad: forge_config._toolkit_root_helper
        pass
    return _helper_module


_ROOT_ENV = "ADLC_TOOLKIT_ROOT"
_MARKETPLACE_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def _own_candidate():
    """Copied from ``forge_config._own_candidate``."""
    helper = _toolkit_root_helper()
    if helper is not None:
        try:
            return helper.toolkit_file("/".join(_LOADER_REL))
        except helper.ToolkitRootError:
            pass
    tools = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    return os.path.join(tools, *_LOADER_REL[1:])


def _env_root_candidate():
    """Copied from ``forge_config._env_root_candidate``: the loader under
    ``$ADLC_TOOLKIT_ROOT``, identity-checked by that root's ``toolkit_root.py``."""
    root = os.environ.get(_ROOT_ENV, "")
    if not os.path.isabs(root):
        return None
    path = os.path.join(root, "tools", "adlc", "toolkit_root.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("toolkit_root", path)
        if spec is None or spec.loader is None:
            return None
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        if helper.toolkit_root() != os.path.realpath(root):
            return None
        return helper.toolkit_file("/".join(_LOADER_REL))
    except Exception:  # why this is broad: forge_config._env_root_candidate
        return None


def _loader_candidates():
    """Where ``_machine_config.py`` may live: this file's toolkit root, then ``$ADLC_TOOLKIT_ROOT``.

    The same rule ``forge_config._loader_candidates`` uses: the first path
    comes from ``toolkit_root.toolkit_file`` (REQ-669 ADR-2), and the inline
    ``realpath`` walk covers a copy vendored without its sibling helper. Only
    when that file is missing does ``$ADLC_TOOLKIT_ROOT`` give a second,
    identity-checked candidate. There is no skills-symlink level, which a
    plugin-only machine does not have. Copied rather than imported from
    ``forge_config`` so a project that vendors this file alone still runs.
    """
    own = _own_candidate()
    if os.path.isfile(own):
        return [own]
    extra = _env_root_candidate()
    return [own] if extra is None or extra == own else [own, extra]


def _plugin_key():
    """Copied from ``forge_config._plugin_key``: ``adlc@<marketplace>`` when this
    toolkit runs from Claude Code's plugin cache, else ``None``."""
    config = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if not os.path.isabs(config):
        config = os.path.join(os.path.expanduser("~"), ".claude")
    cache = os.path.realpath(os.path.join(config, "plugins", "cache"))
    roots = [os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))]
    if os.path.isabs(os.environ.get(_ROOT_ENV, "")):
        roots.append(os.path.realpath(os.environ[_ROOT_ENV]))
    for root in roots:
        parts = os.path.relpath(root, cache).split(os.sep)
        if len(parts) == 3 and parts[1] == "adlc" and _MARKETPLACE_RE.fullmatch(parts[0]):
            return "adlc@" + parts[0]
    return None


def _loader_fix():
    """Copied from ``forge_config._loader_fix``: install.sh on the symlink route only."""
    key = _plugin_key()
    if key is None:
        return ("run install.sh (a vendored copy also reads "
                "$ADLC_TOOLKIT_ROOT/tools/delegate/)")
    return ("reinstall the adlc plugin: claude plugin uninstall %s && "
            "claude plugin install %s" % (key, key))


_LOADER_UNRESOLVED = object()
_loader_module = _LOADER_UNRESOLVED


def _loader():
    """The loader module, executed from an explicit path, or ``None``.

    Loaded by path and not registered in ``sys.modules``, for the reasons
    ``forge_config._loader`` gives: a directory inserted on ``sys.path`` would
    shadow every later import, ``import yaml`` included.
    """
    global _loader_module
    if _loader_module is not _LOADER_UNRESOLVED:
        return _loader_module
    _loader_module = None
    for path in _loader_candidates():
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("_machine_config", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:  # why this is broad: forge_config._loader
            continue
        _loader_module = module
        break
    return _loader_module


# --- config -----------------------------------------------------------------

#: Bytes whose presence means the config may carry a ``lanes`` key: the word
#: itself (bare, quoted, in a flow mapping, indented, or in a comment), a
#: backslash (a double-quoted key can spell it with escapes, ``"\x6canes"``),
#: and a NUL (a UTF-16 or UTF-32 file carries the word as ``l\0a\0...``). A
#: false positive only means the file is parsed and validated, which is the
#: safe direction; a false negative would ignore the project's blocked paths.
_LANES_MARKERS = (b"lanes", b"\\", b"\x00")


#: Every character a YAML parser may treat as a line break. PyYAML (YAML 1.1)
#: also breaks on NEL, LS and PS. Splitting on a superset of the parser's breaks
#: can only turn one line into several, and a fragment that does not start with
#: ``#`` is then scanned, which is the safe direction.
_YAML_LINE_BREAKS = re.compile("\r\n|[\r\n\x85\u2028\u2029]")


def may_carry_lanes(data):
    """True unless the raw config bytes certainly carry no ``lanes`` key.

    Whole-line comments are skipped, so a project config copied from
    ``templates/config-template.yml``, whose ``lanes.lite`` example is commented
    out, is not parsed and does not need PyYAML. Bytes that are not UTF-8 are
    never skipped: the markers are searched in the raw bytes.
    """
    if not any(marker in data for marker in _LANES_MARKERS):
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    if text.startswith("\ufeff"):
        text = text[1:]
    for line in _YAML_LINE_BREAKS.split(text):
        if line.lstrip(" \t").startswith("#"):
            continue
        if any(marker.decode("ascii") in line for marker in _LANES_MARKERS):
            return True
    return False


def read_base_config(worktree, base_oid, label):
    """The bytes of ``.adlc/config.yml`` at ``base_oid``, or ``None`` if absent.

    ``ls-tree`` names the entry's mode and size, so absence is told apart from
    a git failure without parsing an error message, and a symlink, directory or
    submodule in the config's place is refused rather than read as YAML
    (``git show`` would print a tree listing or a link target). The size is
    checked before the blob is read, and again after.
    """
    out = _git(worktree, ["ls-tree", "-l", "-z", "--full-tree", base_oid, "--",
                          CONFIG_RELPATH], "listing %s" % label)
    entries = [e for e in out.split(b"\0") if e]
    if not entries:
        # Absent, unless `.adlc` itself is not a plain directory at the base: git
        # does not descend through a symlinked `.adlc`, so the project's config
        # would vanish silently and the defaults would apply.
        top = _git(worktree, ["ls-tree", "-z", "--full-tree", base_oid, "--", ".adlc"],
                   "listing .adlc at the base")
        for entry in (e for e in top.split(b"\0") if e):
            if not entry.startswith(b"040000 "):
                raise LaneCheckError(".adlc is not a directory at the base; the check "
                                     "reads the config only from a real .adlc/config.yml")
        return None
    meta, sep, name = entries[0].partition(b"\t")
    fields = meta.split()
    if len(entries) != 1 or not sep or len(fields) != 4 \
            or name != CONFIG_RELPATH.encode("ascii"):
        raise LaneCheckError("%s: unexpected git ls-tree output" % label)
    mode, otype, oid, size = fields
    if mode == MODE_SYMLINK.encode("ascii"):
        raise LaneCheckError("%s is a symlink at the base; the check reads only "
                             "a regular file" % label)
    if otype != b"blob" or mode not in _REGULAR_BLOB_MODES:
        raise LaneCheckError("%s is not a regular file at the base" % label)
    if not size.isdigit() or int(size) > CONFIG_CAP_BYTES:
        raise LaneCheckError("%s is larger than %d bytes" % (label, CONFIG_CAP_BYTES))
    data = _git(worktree, ["cat-file", "blob", _decode(oid)], "reading %s" % label)
    if len(data) > CONFIG_CAP_BYTES:
        raise LaneCheckError("%s is larger than %d bytes" % (label, CONFIG_CAP_BYTES))
    return data


def _load_bytes(loader, data):
    """Hand ``data`` to the path-based shared loader via a private temp file."""
    with tempfile.TemporaryDirectory(prefix="adlc-lane-check-") as tmp:
        path = os.path.join(tmp, "config.yml")
        with open(path, "wb") as fh:
            fh.write(data)
        return loader.load_machine_config(path)


def load_overrides(worktree, base_oid, base):
    """The validated ``lanes.lite`` overrides at the base (``{}`` = none).

    A config that :func:`may_carry_lanes` clears is not parsed at all.
    """
    label = "%s:%s" % (base, CONFIG_RELPATH)
    data = read_base_config(worktree, base_oid, label)
    if data is None or not may_carry_lanes(data):
        return {}
    loader = _loader()
    if loader is None:
        raise LaneCheckError(
            "config %s may carry a 'lanes' key but the ADLC config loader "
            "(tools/delegate/_machine_config.py) was not found at %s; %s"
            % (label, " or ".join(_loader_candidates()), _loader_fix()))
    outcome = _load_bytes(loader, data)
    if outcome.kind == loader.KIND_PARSED:
        return validate_lanes(outcome.document, label)
    if outcome.kind == loader.KIND_MALFORMED:
        raise LaneCheckError("config %s cannot be read (%s)" % (label, outcome.reason))
    raise LaneCheckError("config %s could not be loaded (%s)" % (label, outcome.kind))


def _type_name(value):
    if value is None:
        return "a null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int):
        return "an integer"
    if isinstance(value, float):
        return "a float"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a mapping"
    return "a %s" % type(value).__name__


def _schema_error(path, message):
    return LaneCheckError("config %s: %s" % (path, message))


def _check_keys(section, allowed, where, path):
    unknown = [k for k in section if k not in allowed]
    if unknown:
        raise _schema_error(path, "unknown key%s %s under '%s' (allowed: %s)" % (
            "s" if len(unknown) > 1 else "",
            ", ".join(repr(k) for k in unknown), where, ", ".join(allowed)))


def _check_pattern(pattern, where, path):
    globs = normalize_pattern(pattern)
    if not globs:
        raise _schema_error(path, "'%s' contains an empty pattern %r; it would "
                            "match nothing" % (where, pattern))
    # A `.` or `..` segment survives normalization but no repo-relative path git
    # reports ever contains one, so the pattern would silently block nothing.
    if any(seg in (".", "..") for seg in globs[0].split("/")):
        raise _schema_error(path, "'%s' contains the pattern %r, whose '.' or '..' "
                            "segment can never match a changed path" % (where, pattern))


def validate_lanes(document, path="config"):
    """Validate ``document['lanes']``; return the ``lanes.lite`` overrides.

    The closed schema of the module docstring. A section or key whose value is
    null is unwritten; every other shape it does not allow is an error.
    """
    if not document:
        return {}
    lanes = document.get("lanes")
    if lanes is None:
        return {}
    if not isinstance(lanes, dict):
        raise _schema_error(path, "'lanes' must be a mapping, not %s" % _type_name(lanes))
    _check_keys(lanes, LANES_KEYS, "lanes", path)
    lite = lanes.get("lite")
    if lite is None:
        return {}
    if not isinstance(lite, dict):
        raise _schema_error(path, "'lanes.lite' must be a mapping, not %s"
                            % _type_name(lite))
    _check_keys(lite, LITE_KEYS, "lanes.lite", path)

    out = {}
    value = lite.get("max_files")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise _schema_error(path, "'lanes.lite.max_files' must be an integer "
                                ">= 1, not %s" % _type_name(value))
        if value < 1:
            raise _schema_error(path, "'lanes.lite.max_files' must be an integer "
                                ">= 1, not %d" % value)
        out["max_files"] = value
    for key in ("blocked_paths", "count_exclude"):
        value = lite.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            raise _schema_error(path, "'lanes.lite.%s' must be a list of strings, "
                                "not %s" % (key, _type_name(value)))
        for item in value:
            if not isinstance(item, str):
                raise _schema_error(path, "'lanes.lite.%s' must be a list of "
                                    "strings; it contains %s" % (key, _type_name(item)))
            _check_pattern(item, "lanes.lite." + key, path)
        out[key] = list(value)
    value = lite.get("deploy_units")
    if value is not None:
        if not isinstance(value, dict):
            raise _schema_error(path, "'lanes.lite.deploy_units' must be a mapping "
                                "of glob to unit name, not %s" % _type_name(value))
        for unit_glob, unit in value.items():
            if not isinstance(unit_glob, str) or not isinstance(unit, str):
                raise _schema_error(path, "'lanes.lite.deploy_units' must map "
                                    "strings to strings; it maps %s to %s"
                                    % (_type_name(unit_glob), _type_name(unit)))
            _check_pattern(unit_glob, "lanes.lite.deploy_units", path)
        out["deploy_units"] = dict(value)
    return out


# --- git --------------------------------------------------------------------

#: Variables dropped from git's environment: those that would point git at a
#: different repository, index or object store than the ``-C`` directory (set,
#: for example, when this runs inside a git hook), those that inject config
#: (``core.fsmonitor`` runs a program; ``core.worktree`` moves the tree), and
#: those that graft or replace history. Plus every ``GIT_CONFIG_KEY_<n>`` /
#: ``GIT_CONFIG_VALUE_<n>`` (:data:`_GIT_ENV_SCRUB_PREFIXES`).
_GIT_ENV_SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                  "GIT_PREFIX", "GIT_NAMESPACE",
                  "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                  "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
                  "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE")
_GIT_ENV_SCRUB_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
#: Set on every git run: ``refs/replace`` cannot substitute a commit or tree.
_GIT_ENV_SET = {"GIT_NO_REPLACE_OBJECTS": "1"}
#: Global options on every git run: no replace objects, no fsmonitor hook from
#: any config file, and no optional lock taken by a read-only command.
_GIT_GLOBAL_OPTS = ("--no-replace-objects", "--no-optional-locks",
                    "-c", "core.fsmonitor=false")


def _git_env(environ=None):
    """The environment git runs with: :data:`_GIT_ENV_SCRUB` and the
    ``GIT_CONFIG_KEY_*`` / ``GIT_CONFIG_VALUE_*`` family dropped, and
    :data:`_GIT_ENV_SET` applied."""
    environ = os.environ if environ is None else environ
    env = dict((k, v) for k, v in environ.items()
               if k not in _GIT_ENV_SCRUB and not k.startswith(_GIT_ENV_SCRUB_PREFIXES))
    env.update(_GIT_ENV_SET)
    return env


def _decode(raw):
    return raw.decode("utf-8", "surrogateescape")


def _git(worktree, args, what):
    """Run ``git -C <worktree> <args>``; return stdout bytes or raise."""
    try:
        proc = subprocess.run(["git"] + list(_GIT_GLOBAL_OPTS) + ["-C", worktree] + list(args),
                              stdin=subprocess.DEVNULL, capture_output=True, env=_git_env())
    except (OSError, ValueError) as exc:
        raise LaneCheckError("%s: git could not be run (%s)" % (what, type(exc).__name__))
    if proc.returncode != 0:
        lines = _decode(proc.stderr).strip().splitlines()
        raise LaneCheckError("%s failed (git exit %d%s)" % (
            what, proc.returncode, ": " + lines[-1] if lines else ""))
    return proc.stdout


def resolve_base(worktree, base):
    """The commit id ``base`` names, after checking the worktree is checkable.

    Refuses, in order: an option-shaped or empty base, a worktree that is not a
    directory or not the top level of a git worktree (``git -C`` would
    otherwise walk up into an enclosing repository and check that instead),
    uncommitted changes (the diff would not be the change being shipped), and a
    base that does not resolve to a commit.
    """
    if not base or base.startswith("-"):
        raise LaneCheckError("base ref %r is not a usable ref" % (base,))
    if not os.path.isdir(worktree):
        raise LaneCheckError("worktree %s is not a directory" % worktree)
    top = _decode(_git(worktree, ["rev-parse", "--show-toplevel"],
                       "locating the worktree")).rstrip("\n")
    if os.path.realpath(top) != os.path.realpath(worktree):
        raise LaneCheckError("worktree %s is not the top level of a git worktree "
                             "(that is %s)" % (worktree, top))
    status = _git(worktree, ["status", "--porcelain", "--untracked-files=normal"],
                  "git status")
    if status.strip():
        raise LaneCheckError("worktree %s has uncommitted changes; commit before "
                             "the lane check" % worktree)
    oid = _decode(_git(worktree, ["rev-parse", "--verify", "--quiet", base + "^{commit}"],
                       "resolving base ref %r" % (base,))).strip()
    if not re.match(r"^[0-9a-f]{40}([0-9a-f]{24})?$", oid):
        raise LaneCheckError("resolving base ref %r gave no commit id" % (base,))
    return oid


def parse_raw_diff(out):
    """:class:`ChangedFile` entries from ``git diff --raw -z`` output.

    Each record is ``:<old mode> <new mode> <old id> <new id> <status>`` then
    one path, or two for a rename or copy (both kept, with both modes, should
    a config turn detection back on). Anything else is an error: output this
    parser does not understand is not a list of changes it can vouch for.
    """
    tokens = out.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    changes = []
    i = 0
    while i < len(tokens):
        head = tokens[i]
        fields = head[1:].split(b" ") if head.startswith(b":") else []
        if len(fields) != 5 or not fields[4]:
            raise LaneCheckError("unexpected git diff --raw record %r" % _decode(head[:80]))
        old_mode, new_mode = _decode(fields[0]), _decode(fields[1])
        count = 2 if fields[4][:1] in (b"R", b"C") else 1
        paths = tokens[i + 1:i + 1 + count]
        if len(paths) != count or not all(paths):
            raise LaneCheckError("truncated git diff --raw output")
        for raw_path in paths:
            changes.append(ChangedFile(_decode(raw_path), old_mode, new_mode))
        i += 1 + count
    return changes


def changed_files(worktree, base_oid, base):
    """Every change on ``HEAD`` since its merge base with ``base_oid``.

    An empty list is an error: a lite REQ always has commits, so an empty diff
    means the base is wrong, and "nothing changed" must not read as a pass.
    """
    out = _git(worktree, ["diff", "--raw", "-z", "--no-renames", "--no-color",
                          "--no-ext-diff", "--ignore-submodules=none",
                          base_oid + "...HEAD", "--"],
               "diffing against %r" % (base,))
    files = parse_raw_diff(out)
    if not files:
        raise LaneCheckError("empty diff against %s" % base)
    return files


# --- the check and its output -----------------------------------------------

def check(worktree, base):
    """Run the whole check. Returns ``(result, files_counted, failures)``.

    Raises :class:`LaneCheckError` for anything that prevents a decision.
    """
    base_oid = resolve_base(worktree, base)
    files = changed_files(worktree, base_oid, base)
    config = effective_config(load_overrides(worktree, base_oid, base))
    files_counted, failures = evaluate(files, config)
    return (RESULT_ESCALATE if failures else RESULT_PASS), files_counted, failures


#: The backslash itself, C0, DEL, C1 (NEL included), the Arabic letter mark,
#: zero-width and directional marks, the Unicode line and paragraph
#: separators, bidi embeddings/overrides/isolates, the BOM, and lone
#: surrogates (an undecodable byte in a path, via surrogateescape). Each is
#: written as an escape so a detail stays one printable, unambiguous line and
#: one fact — ``str.splitlines()`` breaks on several of these.
_UNSAFE_RE = re.compile(
    "[\\\\\x00-\x1f\x7f-\x9f؜​-‏  ‪-‮"
    "⁦-⁩﻿\ud800-\udfff]")


def _escape(match):
    char = match.group(0)
    if char == "\\":
        return "\\\\"
    code = ord(char)
    return "\\x%02x" % code if code < 0x100 else "\\u%04x" % code


def one_line(value):
    """``value`` as a single line of printable, unambiguous text."""
    return _UNSAFE_RE.sub(_escape, str(value))


def format_result(result, files_counted, failures):
    lines = ["lane_check=%s" % result, "files_counted=%d" % files_counted]
    for trigger, detail in failures:
        lines.append("trigger=%s" % trigger)
        lines.append("detail=%s" % one_line(detail))
    return lines


def format_error(reason):
    return ["lane_check=%s" % RESULT_ERROR,
            "trigger=%s" % TRIGGER_CHECK_ERROR,
            "detail=%s" % one_line(reason)]


class _ArgumentParser(argparse.ArgumentParser):
    """argparse that raises instead of exiting, so a usage error still
    produces the error contract on stdout."""

    def error(self, message):
        raise LaneCheckError("usage: lane_check.py --worktree <path> --base <ref> (%s)"
                             % message)


def _parse_args(argv):
    parser = _ArgumentParser(prog="lane_check.py", add_help=False, allow_abbrev=False)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--base", required=True)
    return parser.parse_args(argv)


def _write(lines):
    text = "\n".join(lines) + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "backslashreplace").decode("ascii"))
    sys.stdout.flush()


def main(argv=None):
    """CLI entry point. Returns 0 pass, 1 escalate, 2 error."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parse_args(argv)
        result, files_counted, failures = check(args.worktree, args.base)
        lines = format_result(result, files_counted, failures)
        rc = RC_ESCALATE if result == RESULT_ESCALATE else RC_PASS
    except LaneCheckError as exc:
        lines, rc = format_error(str(exc)), RC_ERROR
    except Exception as exc:
        # LESSON-581: the fall-through for anything unplanned is error, never pass.
        lines, rc = format_error("unexpected %s: %s" % (type(exc).__name__, exc)), RC_ERROR
    try:
        _write(lines)
    except Exception:
        # Nothing reached the caller; a 0 or 1 here would be a verdict with no
        # facts behind it.
        return RC_ERROR
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
