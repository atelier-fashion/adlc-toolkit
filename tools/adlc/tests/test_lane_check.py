"""Tests for tools/adlc/lane_check.py (REQ-652 BR-2, BR-6, AC-4, AC-15).

The end-to-end cases run the check against real git sandboxes: a repo with a
base commit on ``main`` (which carries any ``.adlc/config.yml``, so the config
itself is not part of the diff) and one feature branch per scenario. The pure
cases drive :func:`lane_check.glob_match`, :func:`lane_check.evaluate` and
:func:`lane_check.validate_lanes` directly.

The config cases need PyYAML and skip without it. The authoritative run is
under the delegate venv with ``ADLC_REQUIRE_PYYAML=1``, which turns those skips
into failures (tools/adlc/README.md "Running the tests").
"""

import contextlib
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest

import lane_check as lc

_ADLC_DIR = os.path.dirname(os.path.abspath(lc.__file__))
_SCRIPT = os.path.join(_ADLC_DIR, "lane_check.py")
_TOOLKIT = os.path.dirname(os.path.dirname(_ADLC_DIR))
_TEMPLATE = os.path.join(_TOOLKIT, "templates", "config-template.yml")
_LANE_CHECK_MD = os.path.join(_TOOLKIT, "partials", "lane-check.md")


# --- sandbox ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch, tmp_path):
    """Keep the operator's git config and any hook-exported GIT_* out of it.

    The engine drops ``GIT_CONFIG_GLOBAL`` from its own git runs, so HOME and
    XDG_CONFIG_HOME point at an empty directory as well: the global config the
    engine's git then reads is nothing.
    """
    for name in list(os.environ):
        if name in lc._GIT_ENV_SCRUB or name.startswith(lc._GIT_ENV_SCRUB_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _require_yaml():
    """PyYAML, or a skip — a failure when ``ADLC_REQUIRE_PYYAML=1``."""
    if os.environ.get("ADLC_REQUIRE_PYYAML") == "1":
        import yaml
        return yaml
    return pytest.importorskip("yaml")


@pytest.fixture
def pyyaml():
    return _require_yaml()


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args),
                          check=True, capture_output=True, text=True)


class Sandbox(object):
    def __init__(self, root):
        self.root = root
        self._branches = 0

    @property
    def path(self):
        return str(self.root)

    def git(self, *args):
        return _git(self.root, *args)

    def write(self, rel, text="x\n"):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, *rels, **kw):
        for rel in rels:
            self.write(rel)
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", kw.get("msg", "change"))

    def feature(self, *rels):
        """A fresh branch off ``main`` with ``rels`` committed on it."""
        self._branches += 1
        self.git("checkout", "-q", "-b", "feature-%d" % self._branches, "main")
        if rels:
            self.commit(*rels)
        return self


@pytest.fixture
def make_repo(tmp_path):
    made = []

    def make(config=None, base_files=()):
        root = tmp_path / ("repo%d" % len(made))
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        for key, value in (("user.name", "Lane Check Test"),
                           ("user.email", "lane-check@example.invalid"),
                           ("commit.gpgsign", "false"),
                           ("tag.gpgsign", "false")):
            _git(root, "config", key, value)
        sb = Sandbox(root)
        sb.write("README.md", "base\n")
        if config is not None:
            sb.write(".adlc/config.yml", config)
        sb.commit(*base_files, msg="base")
        made.append(sb)
        return sb

    return make


def _run(worktree, base="main"):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = lc.main(["--worktree", str(worktree), "--base", base])
    return rc, out.getvalue().splitlines()


def _parse(lines):
    """``(verdict, files_counted, [(trigger, detail)])``, asserting the shape."""
    assert lines and lines[0].startswith("lane_check="), lines
    verdict = lines[0][len("lane_check="):]
    rest = lines[1:]
    counted = None
    if verdict != "error":
        assert rest and rest[0].startswith("files_counted="), lines
        counted = int(rest[0][len("files_counted="):])
        rest = rest[1:]
    assert len(rest) % 2 == 0, lines
    pairs = []
    for trig, detail in zip(rest[::2], rest[1::2]):
        assert trig.startswith("trigger=") and detail.startswith("detail="), lines
        pairs.append((trig[len("trigger="):], detail[len("detail="):]))
    return verdict, counted, pairs


def _check(worktree, base="main"):
    rc, lines = _run(worktree, base)
    verdict, counted, pairs = _parse(lines)
    assert rc == {"pass": 0, "escalate": 1, "error": 2}[verdict], (rc, lines)
    return verdict, counted, pairs


def _assert_error(worktree, needle, base="main"):
    rc, lines = _run(worktree, base)
    assert rc == 2, lines
    assert len(lines) == 3, lines
    verdict, counted, pairs = _parse(lines)
    assert verdict == "error" and counted is None
    assert pairs[0][0] == "check-error"
    assert needle in pairs[0][1], pairs
    return pairs[0][1]


DEPLOY_CONFIG = (
    "lanes:\n"
    "  lite:\n"
    "    deploy_units:\n"
    '      "apps/website/**": website\n'
    '      "apps/admin/**": admin\n'
)


# --- glob helper ------------------------------------------------------------

@pytest.mark.parametrize("path,pattern,expected", [
    # trailing /** is everything beneath, not the entry itself
    (".github/workflows/ci.yml", ".github/**", True),
    (".github/x", ".github/**", True),
    (".github", ".github/**", False),
    ("src/.github/x", ".github/**", False),          # anchored at the root
    # **/ is zero or more directories
    ("main.tf", "**/*.tf", True),
    ("a/b/c/main.tf", "**/*.tf", True),
    ("main.tf.bak", "**/*.tf", False),
    ("migrations/001.sql", "**/migrations/**", True),
    ("db/x/migrations/001.sql", "**/migrations/**", True),
    ("db/migrations", "**/migrations/**", False),
    ("a/b", "a/**/b", True),
    ("a/x/y/b", "a/**/b", True),
    ("a/x/y/c", "a/**/b", False),
    # * and ? never cross /
    ("src/app.py", "src/*.py", True),
    ("src/sub/app.py", "src/*.py", False),
    ("a/b", "a?b", False),
    ("axb", "a?b", True),
    ("CHANGELOG.md", "CHANGELOG*", True),
    ("docs/CHANGELOG.md", "CHANGELOG*", False),
    # brackets, dotfiles, case (case-sensitive unless asked)
    ("src/.env.local", "**/.env*", True),
    ("v1.py", "v[0-9].py", True),
    ("vx.py", "v[!0-9].py", True),
    ("svc/dockerfile", "**/Dockerfile", False),
    ("svc/Dockerfile", "**/Dockerfile", True),
    # schema directories, not schema files (the pattern; the defaults add both)
    ("api/schemas/user.json", "**/schema*/**", True),
    ("api/schema.ts", "**/schema*/**", False),
    # leading / and ./ are dropped; a bare ** is everything
    ("infra/main.tf", "/infra/**", True),
    ("infra/main.tf", "./infra/**", True),
    ("x/y/z", "**", True),
    # a trailing / is everything beneath
    ("infra/main.tf", "infra/", True),
    ("infra/a/b/c.tf", "./infra/", True),
    ("infra", "infra/", False),
    # a pattern with no glob character is the path or everything beneath it
    ("infra", "infra", True),
    ("infra/main.tf", "infra", True),
    ("infrastructure/x", "infra", False),
    ("src/infra", "infra", False),
    # runs of / collapse
    ("infra/net/a.tf", "infra//net/", True),
    # an empty pattern names nothing
    ("x", "", False),
])
def test_glob_match(path, pattern, expected):
    assert lc.glob_match(path, pattern) is expected


@pytest.mark.parametrize("pattern,expected", [
    ("infra/**", ("infra/**",)),
    ("./infra/**", ("infra/**",)),
    ("/infra/**", ("infra/**",)),
    ("././infra/**", ("infra/**",)),
    ("infra/", ("infra/**",)),
    ("./infra/", ("infra/**",)),
    ("infra", ("infra", "infra/**")),
    ("./CLAUDE.md", ("CLAUDE.md", "CLAUDE.md/**")),
    ("infra//net/", ("infra/net/**",)),
    ("**/*.tf", ("**/*.tf",)),
    ("v[0-9].py", ("v[0-9].py",)),
    ("", ()), ("/", ()), ("./", ()), ("//", ()), ("././", ()),
])
def test_normalize_pattern(pattern, expected):
    assert lc.normalize_pattern(pattern) == expected


@pytest.mark.parametrize("path,pattern", [
    ("src/Auth/session.ts", "**/auth/**"),
    ("db/Migrations/0001.py", "**/migrations/**"),
    ("svc/dockerfile", "**/Dockerfile*"),
    ("INFRA/main.TF", "infra/**"),
    ("Packages/Domain/x.ts", "packages/domain/"),
])
def test_glob_match_ignore_case(path, pattern):
    assert lc.glob_match(path, pattern) is False
    assert lc.glob_match(path, pattern, ignore_case=True) is True


# --- defaults, pure ---------------------------------------------------------

_BLOCKED_EXAMPLES = [
    # CI
    ".github/workflows/ci.yml", ".gitlab-ci.yml", ".gitlab/ci/build.yml",
    ".circleci/config.yml", "azure-pipelines.yml", "azure-pipelines.yaml",
    "Jenkinsfile", "bitbucket-pipelines.yml", ".buildkite/pipeline.yml",
    # deploy and infra
    "deploy/run.sh", "infra/net.yaml", "infrastructure/x", "terraform/vars.txt",
    "modules/vpc/main.tf", "envs/prod.tfvars", "k8s/deployment.yaml",
    "helm/values.yaml", "charts/app/Chart.yaml", "Dockerfile",
    "services/api/Dockerfile", "Dockerfile.prod", "services/api/Dockerfile.dev",
    "Containerfile", "build/Containerfile.ci", "docker-compose.yml",
    "ops/docker-compose.prod.yml", "docker-compose.yaml",
    "ops/docker-compose.dev.yaml", "compose.yml", "svc/compose.yaml",
    "cloudbuild.yaml", "ci/cloudbuild-staging.yaml", "cloudbuild.yml",
    "ci/cloudbuild-prod.yml", "serverless.yml", "functions/serverless.yaml",
    "vercel.json", "firebase.json", "fastlane/Fastfile",
    # data
    "db/migrations/0001_init.py", "db/migrate/20240101_add_users.rb",
    "api/db/migrate/x.rb", "alembic/versions/1.py", "svc/alembic/env.py",
    "queries/report.sql", "proto/user.proto", "api/models.prisma",
    "api/types.graphql", "openapi.yaml", "docs/openapi-v2.json",
    "src/schemas/user.ts", "src/schema.ts", "api/schemas.py",
    # security
    "src/auth/session.ts", "lib/security/csp.py", "storage.rules",
    "firestore.rules", ".env", "apps/web/.env.production", "certs/server.pem",
    "config/private.key", "ios/App/App.entitlements",
    # pipeline and agent config
    ".adlc/config.yml", ".adlc/partials/forge.sh",
    ".adlc/tools/adlc/lane_check.py", ".adlc/workflows/adlc-sprint.workflow.js",
    ".adlc/agents/reflector.md", ".github/agents/x.md", ".github/hooks/adlc.json",
    ".claude/settings.json", ".claude/settings.local.json", ".claude/agents/x.md",
    "harness/claude.yml", "harness/claude/rendered/settings.json",
    "templates/permissions.yml", "templates/hooks.yml",
    ".mcp.json", "CLAUDE.md", "AGENTS.md",
    # git hooks and package-manager config
    ".husky/pre-commit", ".githooks/pre-push", ".pre-commit-config.yaml",
    "lefthook.yml", ".gitmodules", ".npmrc", ".yarnrc", ".yarnrc.yml",
    "lefthook.yaml", ".lefthook.yml", ".lefthook.yaml", "web/.lintstagedrc.json",
    # more CI, deploy, build-time code, agent config, context, toolkit machinery
    ".travis.yml", ".drone.yml", ".gitea/workflows/ci.yml", ".forgejo/workflows/x.yml",
    "appveyor.yml", "bitbucket-pipelines.yaml", "pipelines/azure-pipelines.yml",
    "ops/azure-pipelines-release.yaml",
    "netlify.toml", "fly.toml", "app.yaml", "Procfile", "wrangler.toml", "Pulumi.yaml",
    "cdk.json", "infra2/main.bicep",
    ".yarn/releases/yarn-4.cjs", ".pnpmfile.cjs", ".pnp.cjs", "pnpm-workspace.yaml",
    "gradle/wrapper/gradle-wrapper.properties", "gradlew", "android/gradlew.bat",
    "settings.gradle.kts", "android/gradle.properties", ".mvn/wrapper/x.properties",
    "mvnw", ".cargo/config.toml", "crates/x/build.rs",
    "CLAUDE.local.md", "apps/web/GEMINI.md", ".cursor/rules/x.mdc", ".cursorrules",
    ".codex/config.toml", ".gemini/settings.json", ".vscode/tasks.json",
    ".devcontainer/devcontainer.json", ".adlc/context/conventions.md",
    "tools/adlc/lane_check.py", "tools/delegate/_machine_config.py",
    "partials/lane-check.sh", "partials/forge.sh", "proceed/phases-lite.md",
]


@pytest.mark.parametrize("path", _BLOCKED_EXAMPLES)
def test_default_blocked_paths_block(path):
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("blocked-path", path) in failures


# REQ-666 BR-10 / AC-9: each glob the multi-harness adapters and the vendored
# checklists need, pinned in the tuple and exercised by a path under it.
_REQ666_BLOCKED = [
    (".adlc/agents/**", ".adlc/agents/reflector.md"),
    (".github/agents/**", ".github/agents/x.md"),
    (".github/hooks/**", ".github/hooks/adlc.json"),
    (".codex/**", ".codex/config.toml"),
    (".gemini/**", ".gemini/settings.json"),
    (".cursor/**", ".cursor/rules/x.mdc"),
    (".github/**", ".github/workflows/ci.yml"),
    (".adlc/partials/**", ".adlc/partials/forge.sh"),
]


@pytest.mark.parametrize("glob, path", _REQ666_BLOCKED)
def test_req666_blocked_globs(glob, path):
    assert glob in lc.DEFAULT_BLOCKED_PATHS
    assert lc.glob_match(path, glob, ignore_case=True)
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("blocked-path", path) in failures


# REQ-657 BR-14 / AC-12: the four paths this REQ adds, each blocking a lite PR,
# and the CI and harness-config globs pinned as present whatever this REQ does.
_REQ657_BLOCKED = [
    ("harness/**", "harness/claude.yml"),
    ("harness/**", "harness/claude/rendered/settings.json"),
    ("templates/permissions.yml", "templates/permissions.yml"),
    ("templates/hooks.yml", "templates/hooks.yml"),
    (".claude/settings*.json", ".claude/settings.json"),
]
REQ657_ADDED = ("harness/**", "templates/permissions.yml", "templates/hooks.yml",
                ".claude/settings*.json")


@pytest.mark.parametrize("glob, path", _REQ657_BLOCKED)
def test_req657_blocked_globs(glob, path):
    assert glob in lc.DEFAULT_BLOCKED_PATHS
    assert lc.glob_match(path, glob, ignore_case=True)
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("blocked-path", path) in failures


def test_req657_adds_only_its_four_paths():
    """AC-12: the tuple gains exactly these four from REQ-657, and the CI and
    harness-config globs it relies on were already present."""
    for glob in REQ657_ADDED:
        assert lc.DEFAULT_BLOCKED_PATHS.count(glob) == 1, glob
    for glob in (".cursor/**", ".codex/**", ".gemini/**", ".github/**"):
        assert glob in lc.DEFAULT_BLOCKED_PATHS, glob


@pytest.mark.parametrize("path", ["templates/requirement-template.md", "harnesses.md",
                                  "docs/harness/notes.md", "templates/permissions.md"])
def test_req657_globs_do_not_overreach(path):
    """Benign path: nearby files outside the four globs stay countable."""
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("blocked-path", path) not in failures


def test_req666_globs_documented_in_lane_check_md():
    """AC-9: the partial's documented defaults list the same paths."""
    doc = (Path(__file__).resolve().parents[3] / "partials" / "lane-check.md").read_text(encoding="utf-8")
    for glob, _path in _REQ666_BLOCKED:
        assert f"`{glob}`" in doc, glob


def test_every_default_blocked_pattern_has_an_example():
    """Each default class is exercised above, not just declared."""
    missing = [p for p in lc.DEFAULT_BLOCKED_PATHS
               if not any(lc.glob_match(x, p, ignore_case=True) for x in _BLOCKED_EXAMPLES)]
    assert missing == []


@pytest.mark.parametrize("path", [
    "src/app.py", "docs/deploy.md", "src/authors.py", "src/schemer.py",
    ".adlc/specs/REQ-1-x/requirement.md", "README.md", "src/components/charts/Bar.tsx",
    "docs/keys.md", "src/compose.ts", "src/helmet.ts", "lib/k8s_client.py",
    "docs/claude-code.md",
])
def test_default_blocked_paths_leave_ordinary_files_alone(path):
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert not [f for f in failures if f[0] == "blocked-path"]


@pytest.mark.parametrize("path", [
    "src/Auth/session.ts", "Migrations/0001_init.py", "svc/dockerfile",
    ".GitHub/workflows/ci.yml", "INFRA/main.TF", "certs/server.PEM", "claude.md",
])
def test_default_blocked_paths_match_case_insensitively(path):
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("blocked-path", path) in failures


def test_project_blocked_paths_match_case_insensitively():
    cfg = lc.effective_config({"blocked_paths": ["Packages/Domain/"]})
    _counted, failures = lc.evaluate(["packages/domain/model.ts"], cfg)
    assert failures == [("blocked-path", "packages/domain/model.ts")]


@pytest.mark.parametrize("name", [n for n in lc.DEPENDENCY_FILES if "*" not in n]
                         + ["requirements.txt", "requirements-dev.txt",
                            "build.gradle", "build.gradle.kts", "App.csproj"])
@pytest.mark.parametrize("prefix", ["", "apps/web/"])
def test_dependency_files_match_by_basename_anywhere(name, prefix):
    path = prefix + name
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("dependency", path) in failures


@pytest.mark.parametrize("path", [
    "PACKAGE.JSON", "apps/web/Package.Json", "gemfile", "cargo.LOCK",
    "Requirements-Dev.TXT", "src/Api/Api.CSPROJ", "POM.xml",
])
def test_dependency_names_match_case_insensitively(path):
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert ("dependency", path) in failures


@pytest.mark.parametrize("path", [
    "package.json.md", "docs/my-package.json", "requirements.md",
    "src/gradle_build.py", "Cargo.lock.bak", "src/setup_helpers.py",
])
def test_dependency_lookalikes_do_not_match(path):
    _counted, failures = lc.evaluate([path], lc.effective_config())
    assert not [f for f in failures if f[0] == "dependency"]


@pytest.mark.parametrize("path", [
    "test/a.py", "src/test/a.js", "tests/test_x.py", "pkg/tests/x.go",
    "web/__tests__/a.js", "src/a.test.ts", "src/a.spec.tsx", "lib/test_util.py",
    "cmd/main_test.go", ".adlc/specs/REQ-1-x/requirement.md", "CHANGELOG.md",
])
def test_default_count_exclude(path):
    counted, _failures = lc.evaluate([path], lc.effective_config())
    assert counted == 0


def test_count_exclude_and_deploy_units_stay_case_sensitive():
    cfg = lc.effective_config({"count_exclude": ["content/"],
                               "deploy_units": {"apps/website/**": "website",
                                                "apps/admin/**": "admin"}})
    counted, _failures = lc.evaluate(["Tests/a.py", "changelog.md", "Content/a.md"], cfg)
    assert counted == 3
    _counted, failures = lc.evaluate(["Apps/Website/a.ts", "apps/admin/b.ts"], cfg)
    assert not [f for f in failures if f[0] == "deploy-units"]


def _lane_defaults_from_doc():
    """``{name: [item, ...]}`` from partials/lane-check.md's
    ``<!-- lane-defaults <name> -->`` blocks: every backticked span."""
    with open(_LANE_CHECK_MD, encoding="utf-8") as fh:
        text = fh.read()
    blocks = re.findall(r"^<!-- lane-defaults (\w+) -->\n(.*?)^<!-- /lane-defaults -->$",
                        text, re.MULTILINE | re.DOTALL)
    return dict((name, re.findall(r"`([^`\n]+)`", body)) for name, body in blocks)


def test_lane_check_md_defaults_match_the_code():
    """The defaults are stated in the doc too; only the code used to be tested."""
    docs = _lane_defaults_from_doc()
    assert sorted(docs) == ["blocked_paths", "count_exclude", "dependency_lockfiles",
                            "dependency_manifests", "max_files"]
    for name, code in (("blocked_paths", lc.DEFAULT_BLOCKED_PATHS),
                       ("dependency_lockfiles", lc.DEPENDENCY_LOCKFILES),
                       ("dependency_manifests", lc.DEPENDENCY_MANIFESTS),
                       ("count_exclude", lc.DEFAULT_COUNT_EXCLUDE)):
        assert len(set(code)) == len(code), name
        assert sorted(docs[name]) == sorted(code), name
    assert docs["max_files"] == [str(lc.DEFAULT_MAX_FILES)]


# --- the rules, end to end --------------------------------------------------

_ESCALATE_CASES = [
    ("blocked-path", None, [".github/workflows/ci.yml"],
     [("blocked-path", ".github/workflows/ci.yml")]),
    ("dependency-lockfile", None, ["yarn.lock"],
     [("dependency", "yarn.lock")]),
    ("dependency-manifest", None, ["apps/web/package.json"],
     [("dependency", "apps/web/package.json")]),
    ("deploy-units", DEPLOY_CONFIG, ["apps/website/a.ts", "apps/admin/b.ts"],
     [("deploy-units", "admin, website")]),
    ("max-files", None, ["src/a.py", "src/b.py", "src/c.py", "src/d.py"],
     [("max-files", "4 > 3")]),
    # The must-not-fire twin: every rule evaluated, none crossed, declared
    # units and all.
    ("none-crossed", DEPLOY_CONFIG, ["apps/website/a.ts", "src/b.py", "docs/c.md"],
     []),
]


@pytest.mark.parametrize("rule,config,files,expected", _ESCALATE_CASES,
                         ids=[c[0] for c in _ESCALATE_CASES])
def test_each_rule_escalates(make_repo, rule, config, files, expected):
    """BR-6: each rule fails on its own fixture and names its own trigger;
    a diff that crosses no rule passes."""
    if config is not None:
        _require_yaml()
    sb = make_repo(config=config).feature(*files)
    verdict, counted, pairs = _check(sb.path)
    assert verdict == ("escalate" if expected else "pass")
    assert pairs == expected
    assert counted == len(files)


_PAIRED_CASES = [
    ("blocked-path", None, ["src/app.py"], ["src/auth/session.py"],
     ("blocked-path", "src/auth/session.py")),
    ("dependency-lockfile", None, ["docs/lockfiles.md"], ["Cargo.lock"],
     ("dependency", "Cargo.lock")),
    ("dependency-manifest", None, ["docs/requirements.md"],
     ["requirements-dev.txt"], ("dependency", "requirements-dev.txt")),
    ("deploy-units", DEPLOY_CONFIG,
     ["apps/website/a.ts", "apps/website/b.ts", "README.md"],
     ["apps/website/a.ts", "apps/admin/b.ts"],
     ("deploy-units", "admin, website")),
    ("max-files", None, ["src/1.py", "src/2.py", "src/3.py"],
     ["src/1.py", "src/2.py", "src/3.py", "src/4.py"],
     ("max-files", "4 > 3")),
]


@pytest.mark.parametrize("rule,config,passing,failing,expected", _PAIRED_CASES,
                         ids=[c[0] for c in _PAIRED_CASES])
def test_pass_and_fail_fixture_per_rule(make_repo, rule, config, passing,
                                        failing, expected):
    """AC-4: a passing and a failing diff for every rule."""
    if config is not None:
        _require_yaml()
    sb = make_repo(config=config)

    sb.feature(*passing)
    rc, lines = _run(sb.path)
    assert rc == 0, lines
    verdict, counted, pairs = _parse(lines)
    assert verdict == "pass" and pairs == []
    assert counted == len(passing)

    sb.feature(*failing)
    rc, lines = _run(sb.path)
    assert rc == 1, lines
    verdict, _counted, pairs = _parse(lines)
    assert verdict == "escalate" and pairs == [expected]


def test_empty_diff_is_an_error(make_repo):
    """A lite REQ always has commits: an empty diff means the base is wrong."""
    sb = make_repo().feature()
    _assert_error(sb.path, "empty diff against main")


def test_branch_already_in_the_base_is_an_error(make_repo):
    sb = make_repo().feature("src/a.py")
    sb.git("branch", "-f", "merged", "HEAD")
    _assert_error(sb.path, "empty diff against merged", base="merged")


def test_every_failing_fact_is_reported_in_rule_order(make_repo):
    sb = make_repo().feature(".github/a.yml", "infra/b.tf", "package.json",
                             "src/1.py", "src/2.py", "src/3.py", "src/4.py")
    verdict, counted, pairs = _check(sb.path)
    assert verdict == "escalate"
    assert counted == 7
    assert pairs == [
        ("blocked-path", ".github/a.yml"),
        ("blocked-path", "infra/b.tf"),
        ("dependency", "package.json"),
        ("max-files", "7 > 3"),
    ]


def test_count_excludes_tests_and_adlc(make_repo):
    """BR-2: tests and the REQ's own .adlc/ files are not counted."""
    excluded = ["tests/test_a.py", "src/test/helper.js", "web/__tests__/a.js",
                "src/a.test.ts", "src/a.spec.ts", "lib/test_util.py",
                "cmd/main_test.go", ".adlc/specs/REQ-1-x/requirement.md",
                ".adlc/specs/REQ-1-x/pipeline-state.json", "CHANGELOG.md"]
    sb = make_repo()

    sb.feature("src/a.py", "src/b.py", "src/c.py", *excluded)
    assert _check(sb.path) == ("pass", 3, [])

    sb.feature("src/a.py", "src/b.py", "src/c.py", "src/d.py", *excluded)
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


def test_test_file_under_blocked_path_still_blocked(make_repo):
    sb = make_repo().feature("infra/tests/test_network.py", "src/app.py")
    verdict, counted, pairs = _check(sb.path)
    assert verdict == "escalate"
    assert counted == 1                       # the test file is not counted ...
    assert pairs == [("blocked-path", "infra/tests/test_network.py")]   # ... but is blocked


def test_rename_out_of_blocked_path_reports_the_old_path(make_repo):
    """With rename detection only the new path would be listed."""
    sb = make_repo(base_files=["infra/old.tf"]).feature()
    sb.git("mv", "infra/old.tf", "new.txt")
    sb.commit()
    verdict, counted, pairs = _check(sb.path)
    assert verdict == "escalate"
    assert pairs == [("blocked-path", "infra/old.tf")]
    assert counted == 2                     # the deletion and the addition


def test_deploy_units_only_when_declared(make_repo):
    sb = make_repo().feature("apps/website/a.ts", "apps/admin/b.ts")
    assert _check(sb.path) == ("pass", 2, [])


def test_deploy_units_ignore_excluded_and_unmapped_files(make_repo, pyyaml):
    sb = make_repo(config=DEPLOY_CONFIG)
    sb.feature("apps/website/a.ts", "apps/admin/tests/test_b.py", "lib/shared.ts")
    assert _check(sb.path) == ("pass", 2, [])


def test_deploy_units_first_matching_glob_wins(make_repo, pyyaml):
    sb = make_repo(config=(
        "lanes:\n  lite:\n    deploy_units:\n"
        '      "apps/**": everything\n'
        '      "apps/admin/**": admin\n'))
    sb.feature("apps/website/a.ts", "apps/admin/b.ts")
    assert _check(sb.path) == ("pass", 2, [])


def test_project_patterns_are_normalized(make_repo, pyyaml):
    """./, a trailing / and a bare directory, in every list and the unit keys."""
    sb = make_repo(config=(
        "lanes:\n  lite:\n"
        '    blocked_paths: ["./packages/domain/", "contracts"]\n'
        '    count_exclude: ["content"]\n'
        "    deploy_units:\n"
        '      "apps/website/": website\n'
        '      "./apps/admin": admin\n'))
    sb.feature("packages/domain/model.ts", "contracts/v1/a.json", "content/a.md",
               "content/b/c.md", "apps/website/a.ts", "apps/admin/b.ts")
    assert _check(sb.path) == ("escalate", 4, [
        ("blocked-path", "contracts/v1/a.json"),
        ("blocked-path", "packages/domain/model.ts"),
        ("deploy-units", "admin, website"),
        ("max-files", "4 > 3"),
    ])


# --- file modes: symlinks and submodules ------------------------------------

needs_symlinks = pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt",
                                    reason="needs POSIX symlinks")


@needs_symlinks
def test_added_symlink_is_a_blocked_path(make_repo):
    sb = make_repo().feature()
    os.symlink("README.md", str(sb.root / "docs-link"))
    sb.commit()
    assert _check(sb.path) == ("escalate", 1, [("blocked-path", "symlink: docs-link")])


@needs_symlinks
def test_deleted_symlink_is_a_blocked_path(make_repo):
    sb = make_repo()
    os.symlink("README.md", str(sb.root / "link"))
    sb.commit(msg="link on main")
    sb.feature()
    os.remove(str(sb.root / "link"))
    sb.commit()
    assert _check(sb.path) == ("escalate", 1, [("blocked-path", "symlink: link")])


@needs_symlinks
def test_file_replaced_by_symlink_is_a_blocked_path(make_repo):
    sb = make_repo(base_files=["notes.txt"]).feature()
    os.remove(str(sb.root / "notes.txt"))
    os.symlink("/etc/passwd", str(sb.root / "notes.txt"))
    sb.commit()
    assert _check(sb.path) == ("escalate", 1, [("blocked-path", "symlink: notes.txt")])


@needs_symlinks
def test_symlink_under_a_blocked_path_reports_both_facts(make_repo):
    sb = make_repo().feature()
    (sb.root / "infra").mkdir()
    os.symlink("../README.md", str(sb.root / "infra" / "link"))
    sb.commit()
    assert _check(sb.path)[2] == [("blocked-path", "infra/link"),
                                  ("blocked-path", "symlink: infra/link")]


def _add_gitlink(sb, path):
    head = sb.git("rev-parse", "HEAD").stdout.strip()
    (sb.root / path).mkdir(parents=True)          # an uninitialized submodule
    sb.git("update-index", "--add", "--cacheinfo", "160000,%s,%s" % (head, path))
    sb.git("commit", "-q", "--no-verify", "-m", "gitlink")


def test_added_submodule_is_a_dependency(make_repo):
    sb = make_repo().feature()
    _add_gitlink(sb, "vendor/lib")
    assert _check(sb.path) == ("escalate", 1, [("dependency", "submodule: vendor/lib")])


def test_gitmodules_ignore_all_cannot_hide_a_submodule(make_repo):
    """`ignore = all` in .gitmodules hides a gitlink from a plain `git diff`."""
    sb = make_repo()
    sb.write(".gitmodules", '[submodule "vendor/lib"]\n\tpath = vendor/lib\n'
                            "\turl = ./nowhere\n\tignore = all\n")
    sb.commit(msg="gitmodules on main")
    sb.feature()
    _add_gitlink(sb, "vendor/lib")
    assert sb.git("diff", "--name-only", "main...HEAD").stdout == ""
    assert _check(sb.path) == ("escalate", 1, [("dependency", "submodule: vendor/lib")])


def test_removed_submodule_is_a_dependency(make_repo):
    sb = make_repo()
    _add_gitlink(sb, "vendor/lib")
    sb.feature()
    sb.git("rm", "-q", "--cached", "vendor/lib")
    sb.git("commit", "-q", "--no-verify", "-m", "drop gitlink")
    assert _check(sb.path) == ("escalate", 1, [("dependency", "submodule: vendor/lib")])


def test_parse_raw_diff_keeps_both_paths_of_a_rename():
    out = (b":100644 100644 aaaaaaa bbbbbbb R100\0old/a.tf\0new/a.txt\0"
           b":000000 120000 0000000 ccccccc A\0link\0")
    assert lc.parse_raw_diff(out) == [
        lc.ChangedFile("old/a.tf", "100644", "100644"),
        lc.ChangedFile("new/a.txt", "100644", "100644"),
        lc.ChangedFile("link", "000000", "120000"),
    ]


@pytest.mark.parametrize("out", [
    b"infra/a.tf\0",                                   # --name-only shape
    b":100644 100644 aaaaaaa bbbbbbb M\0",             # record with no path
    b":100644 100644 aaaaaaa bbbbbbb R100\0only-one\0",
    b"::100644 100644 100644 a b c MM\0x\0",           # combined diff
])
def test_parse_raw_diff_refuses_what_it_does_not_understand(out):
    with pytest.raises(lc.LaneCheckError):
        lc.parse_raw_diff(out)


# --- output -----------------------------------------------------------------

def test_detail_is_one_line(make_repo):
    sb = make_repo().feature()
    try:
        sb.commit("infra/a\nb.tf")
    except OSError:
        pytest.skip("this filesystem refuses a newline in a file name")
    rc, lines = _run(sb.path)
    assert rc == 1
    assert lines == ["lane_check=escalate", "files_counted=1",
                     "trigger=blocked-path", "detail=infra/a\\x0ab.tf"]


def test_detail_escapes_backslash_and_line_separators_end_to_end(make_repo):
    sb = make_repo().feature()
    try:
        sb.commit("infra/a\\b.tf", "infra/c d.tf")
    except (OSError, UnicodeEncodeError):
        pytest.skip("this filesystem refuses these characters in a file name")
    rc, lines = _run(sb.path)
    assert rc == 1
    assert lines == ["lane_check=escalate", "files_counted=2",
                     "trigger=blocked-path", "detail=infra/a\\\\b.tf",
                     "trigger=blocked-path", "detail=infra/c\\u2028d.tf"]


def test_one_line_escapes_controls_bidi_and_undecodable_bytes():
    raw = b"a\xffb".decode("utf-8", "surrogateescape")
    assert lc.one_line("x\ny\rz") == "x\\x0ay\\x0dz"
    assert lc.one_line("a‮b") == "a\\u202eb"
    assert lc.one_line(raw) == "a\\udcffb"
    assert lc.one_line("café/naïve.md") == "café/naïve.md"


@pytest.mark.parametrize("char,escaped", [
    ("\\", "\\\\"),
    (" ", "\\u2028"), (" ", "\\u2029"),
    ("​", "\\u200b"), ("‌", "\\u200c"), ("‍", "\\u200d"),
    ("‎", "\\u200e"), ("‏", "\\u200f"),
    ("؜", "\\u061c"), ("﻿", "\\ufeff"),
    ("\x85", "\\x85"), ("\x1c", "\\x1c"), ("\x0b", "\\x0b"), ("\x0c", "\\x0c"),
    ("⁦", "\\u2066"),
])
def test_one_line_escapes_every_splitting_and_invisible_character(char, escaped):
    out = lc.one_line("a" + char + "b")
    assert out == "a" + escaped + "b"
    assert len(("detail=" + out).splitlines()) == 1


def test_one_line_is_unambiguous():
    """A path that spells an escape no longer reads like the escaped character."""
    assert lc.one_line("a\\x0ab") != lc.one_line("a\nb")
    assert lc.one_line("a\\u2028b") != lc.one_line("a b")


# --- config -----------------------------------------------------------------

def test_absent_config_uses_defaults(make_repo):
    sb = make_repo().feature("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


def test_config_overrides_extend_defaults(make_repo, pyyaml):
    """AC-15: project lists extend the defaults; max_files overrides."""
    sb = make_repo(config=(
        "project:\n  name: Sandbox\n"
        "lanes:\n"
        "  lite:\n"
        "    max_files: 5\n"
        '    blocked_paths: ["packages/domain/**"]\n'
        '    count_exclude: ["content/**"]\n'
        "    deploy_units:\n"
        '      "apps/website/**": website\n'
        '      "apps/admin/**": admin\n'
    ))

    # max_files 5 replaces 3; content/** is excluded AND tests/** still is.
    sb.feature("src/1.py", "src/2.py", "src/3.py", "src/4.py", "src/5.py",
               "content/a.md", "content/b.md", "tests/test_1.py")
    assert _check(sb.path) == ("pass", 5, [])

    # The project's blocked path blocks, the default blocked path STILL blocks,
    # the declared units are enforced, and the count is against 5, not 3.
    sb.feature("packages/domain/model.ts", ".github/workflows/ci.yml",
               "apps/website/a.ts", "apps/admin/b.ts",
               "src/1.py", "src/2.py", "content/c.md")
    verdict, counted, pairs = _check(sb.path)
    assert verdict == "escalate"
    assert counted == 6
    assert pairs == [
        ("blocked-path", ".github/workflows/ci.yml"),
        ("blocked-path", "packages/domain/model.ts"),
        ("deploy-units", "admin, website"),
        ("max-files", "6 > 5"),
    ]


def test_max_files_override_can_tighten(make_repo, pyyaml):
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 1\n")
    sb.feature("src/a.py", "src/b.py")
    assert _check(sb.path) == ("escalate", 2, [("max-files", "2 > 1")])


@pytest.mark.parametrize("config", [
    "lanes:\n",
    "lanes:\n  lite:\n",
    "lanes:\n  lite:\n    max_files:\n    blocked_paths:\n    count_exclude:\n"
    "    deploy_units:\n",
], ids=["lanes-null", "lite-null", "keys-null"])
def test_null_sections_and_keys_leave_the_defaults(make_repo, pyyaml, config):
    sb = make_repo(config=config)
    sb.feature("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


@pytest.mark.parametrize("config", [
    "{lanes: {lite: {max_files: 1}}}\n",
    "  lanes:\n    lite:\n      max_files: 1\n",
    "project: {name: x}\n\"lanes\" : {lite: {max_files: 1}}\n",
    "? lanes\n: lite:\n    max_files: 1\n",
    '"\\x6canes": {lite: {max_files: 1}}\n',
    "%YAML 1.1\n---\nlanes:\n  lite:\n    max_files: 1\n",
], ids=["flow", "indented-document", "quoted-key-flow-value", "explicit-key",
        "escaped-key", "directive"])
def test_lanes_in_any_yaml_shape_is_applied(make_repo, pyyaml, config):
    """The pre-check never skips a `lanes` the parser would see."""
    sb = make_repo(config=config).feature("src/a.py", "src/b.py")
    assert _check(sb.path) == ("escalate", 2, [("max-files", "2 > 1")])


@pytest.mark.parametrize("config,needle", [
    ("lanes:\n  heavy: {}\n", "unknown key 'heavy' under 'lanes'"),
    ("lanes:\n  lite:\n    max_file: 4\n", "unknown key 'max_file' under 'lanes.lite'"),
    ("{lanes: {lite: {max_file: 4}}}\n", "unknown key 'max_file' under 'lanes.lite'"),
    ("lanes:\n  lite:\n    max_files: true\n", "max_files' must be an integer >= 1, not a boolean"),
    ("lanes:\n  lite:\n    max_files: 0\n", "max_files' must be an integer >= 1, not 0"),
    ("lanes:\n  lite:\n    max_files: \"3\"\n", "not a string"),
    ("lanes:\n  lite:\n    max_files: 3.5\n", "not a float"),
    ("lanes:\n  lite:\n    blocked_paths: \"infra/**\"\n", "blocked_paths' must be a list of strings, not a string"),
    ("lanes:\n  lite:\n    blocked_paths: [1]\n", "it contains an integer"),
    ("lanes:\n  lite:\n    blocked_paths: [\"\"]\n", "'lanes.lite.blocked_paths' contains an empty pattern"),
    ("lanes:\n  lite:\n    count_exclude: [\"./\"]\n", "'lanes.lite.count_exclude' contains an empty pattern"),
    ("lanes:\n  lite:\n    deploy_units: {\"/\": web}\n", "'lanes.lite.deploy_units' contains an empty pattern"),
    ("lanes:\n  lite:\n    count_exclude: {a: b}\n", "count_exclude' must be a list of strings, not a mapping"),
    ("lanes:\n  lite:\n    deploy_units: [\"apps/**\"]\n", "deploy_units' must be a mapping"),
    ("lanes:\n  lite:\n    deploy_units: {\"apps/**\": 3}\n", "maps a string to an integer"),
    ("lanes: [lite]\n", "'lanes' must be a mapping, not a list"),
    ("lanes:\n  lite: 3\n", "'lanes.lite' must be a mapping, not an integer"),
    ("lanes:\n  lite:\n    max_files: 3\n    max_files: 9\n", "duplicate-key"),
    ("lanes:\n  lite: [unclosed\n", "yaml-error"),
    ("base: &b {max_files: 9}\nlanes:\n  lite: *b\n", "alias-or-merge"),
], ids=["unknown-lanes-key", "unknown-lite-key", "unknown-lite-key-flow",
        "max-files-bool", "max-files-zero", "max-files-string", "max-files-float",
        "blocked-not-list", "blocked-int-item", "blocked-empty", "exclude-dot-slash",
        "units-slash-key", "exclude-mapping", "units-list", "units-int-value",
        "lanes-list", "lite-scalar", "duplicate-key", "yaml-syntax", "alias"])
def test_malformed_lanes_config_is_an_error(make_repo, pyyaml, config, needle):
    sb = make_repo(config=config).feature("src/a.py")
    detail = _assert_error(sb.path, needle)
    assert "main:.adlc/config.yml" in detail


def test_config_with_no_lanes_is_not_loaded(make_repo, monkeypatch):
    """A config without `lanes` anywhere is never parsed: not even an
    interpreter without PyYAML, and not even invalid YAML, costs anything."""
    sb = make_repo(config=(
        "project:\n  name: Sandbox\n"
        "broken: [unclosed\n"
        "# limits for the lite lane live elsewhere\n"
    ))
    sb.feature("src/a.py", "src/b.py")
    monkeypatch.setitem(sys.modules, "yaml", None)

    def _must_not_load():
        raise AssertionError("the loader was reached for a config with no lanes key")

    monkeypatch.setattr(lc, "_loader", _must_not_load)
    assert _check(sb.path) == ("pass", 2, [])


def test_lanes_only_in_a_whole_line_comment_is_not_loaded(make_repo, monkeypatch):
    """A config copied from the template carries its `lanes.lite` example
    commented out; it must not need PyYAML (otherwise every lite check on a
    machine without it would error and escalate)."""
    sb = make_repo(config="# lanes:\n#   lite:\n#     max_files: 9\nproject:\n  name: x\n")
    sb.feature("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(lc, "_loader", lambda: pytest.fail("a comment-only lanes config was parsed"))
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


def test_lanes_after_a_comment_on_the_same_line_is_still_parsed(make_repo, pyyaml):
    """Only whole-line comments are skipped; a trailing comment does not hide a key,
    and a YAML line break the parser honours (U+2028 here) is a break for the
    pre-check too."""
    assert lc.may_carry_lanes("lanes:  # project limits\n".encode("utf-8"))
    assert lc.may_carry_lanes("# note\u2028lanes: {}\n".encode("utf-8"))


def test_lanes_key_without_pyyaml_is_an_error(make_repo, monkeypatch):
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 9\n").feature("src/a.py")
    monkeypatch.setitem(sys.modules, "yaml", None)
    _assert_error(sb.path, "dependency-missing")


def test_lanes_key_without_the_loader_is_an_error(make_repo, monkeypatch):
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 9\n").feature("src/a.py")
    monkeypatch.setattr(lc, "_loader", lambda: None)
    _assert_error(sb.path, "config loader")


@pytest.mark.parametrize("key,fix", [
    (None, "run install.sh"),
    ("adlc@adlc-toolkit", "claude plugin uninstall adlc@adlc-toolkit && "
                          "claude plugin install adlc@adlc-toolkit"),
])
def test_missing_loader_error_names_the_route_fix(make_repo, monkeypatch, key, fix):
    """install.sh on the symlink route only; a plugin copy is reinstalled (REQ-669 BR-11)."""
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 9\n").feature("src/a.py")
    monkeypatch.setattr(lc, "_loader", lambda: None)
    monkeypatch.setattr(lc, "_plugin_key", lambda: key)
    message = _assert_error(sb.path, "config loader")
    assert fix in message
    assert ("install.sh" in message) is (key is None)


def test_plugin_key_reads_the_cache_copy(cache_shaped_tree):
    """A copy inside the plugin cache is the plugin route; its key is read off the path."""
    tree = cache_shaped_tree
    out = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import lane_check as m\n"
         "print(m._plugin_key())\n",
         os.path.join(tree.root, "tools", "adlc")],
        capture_output=True, text=True, env=tree.env, cwd=tree.home)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "adlc@adlc-toolkit"


def test_vendored_lane_check_reads_the_loader_under_adlc_toolkit_root(tmp_path):
    """A copy vendored without tools/delegate/ takes the identity-checked root's loader."""
    vendored = tmp_path / "vend" / "tools" / "adlc"
    vendored.mkdir(parents=True)
    (vendored / "lane_check.py").write_text(open(lc.__file__, encoding="utf-8").read())
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import lane_check as m\n"
            "l = m._loader(); print(l.__file__ if l else None)\n")
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    without = subprocess.run([sys.executable, "-I", "-c", code, str(vendored)],
                             capture_output=True, text=True, env=env)
    assert without.returncode == 0, without.stderr
    assert without.stdout.strip() == "None"
    with_root = subprocess.run([sys.executable, "-I", "-c", code, str(vendored)],
                               capture_output=True, text=True,
                               env=dict(env, ADLC_TOOLKIT_ROOT=_TOOLKIT))
    assert with_root.returncode == 0, with_root.stderr
    assert with_root.stdout.strip() == os.path.join(
        _TOOLKIT, "tools", "delegate", "_machine_config.py")


@pytest.mark.parametrize("text,expected", [
    (b"lanes:\n", True),
    (b"project: x\nlanes:\n  lite: {}\n", True),
    (b"\xef\xbb\xbflanes:\n", True),
    (b"'lanes' :\n", True),
    (b"{lanes: {lite: {}}}\n", True),
    (b"  lanes:\n", True),
    (b"# lanes:\n", False),
    (b"  # lanes:\n#   lite: {}\n", False),
    (b"# lanes:\nlanes: {}\n", True),
    (b"# \\x6c\n", False),
    (b"# lanes:\r\nlanes: {}\r\n", True),
    (b"\xff\xfe# lanes", True),
    (b"sprint:\n  lanes: 2\n", True),
    (b'"\\x6canes": {}\n', True),
    ("lanes: {}\n".encode("utf-16"), True),
    (b"project: x\n", False),
    (b"LANES: 1\n", False),
    (b"", False),
])
def test_may_carry_lanes(text, expected):
    assert lc.may_carry_lanes(text) is expected


# --- config: read from the base, never the disk -----------------------------

def test_config_is_read_from_the_base_not_the_branch(make_repo, pyyaml):
    """A branch that loosens its own lane is still held to the base's limits."""
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 1\n").feature()
    sb.write(".adlc/config.yml", "lanes:\n  lite:\n    max_files: 9\n")
    sb.commit("src/a.py", "src/b.py")
    assert _check(sb.path) == ("escalate", 2, [("blocked-path", ".adlc/config.yml"),
                                               ("max-files", "2 > 1")])


def test_skip_worktree_config_edit_cannot_loosen_the_lane(make_repo, pyyaml):
    sb = make_repo(config="lanes:\n  lite:\n    max_files: 1\n").feature("src/a.py", "src/b.py")
    sb.git("update-index", "--skip-worktree", ".adlc/config.yml")
    sb.write(".adlc/config.yml", "lanes:\n  lite:\n    max_files: 9\n")
    assert sb.git("status", "--porcelain").stdout == ""      # the trick works on git ...
    assert _check(sb.path) == ("escalate", 2, [("max-files", "2 > 1")])   # ... not here


def test_gitignored_local_config_is_not_read(make_repo, monkeypatch):
    sb = make_repo()
    sb.write(".gitignore", ".adlc/config.yml\n")
    sb.commit(msg="ignore the config")
    sb.feature("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    sb.write(".adlc/config.yml", "lanes:\n  lite:\n    max_files: 9\n")
    assert sb.git("status", "--porcelain").stdout == ""
    monkeypatch.setattr(lc, "_loader", lambda: pytest.fail("the disk config was parsed"))
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


def test_config_added_by_the_branch_is_not_applied(make_repo):
    sb = make_repo().feature()
    sb.write(".adlc/config.yml", "lanes:\n  lite:\n    max_files: 9\n")
    sb.commit("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    assert _check(sb.path) == ("escalate", 4, [("blocked-path", ".adlc/config.yml"),
                                               ("max-files", "4 > 3")])


@needs_symlinks
def test_config_that_is_a_symlink_at_the_base_is_an_error(make_repo):
    sb = make_repo(base_files=["real.yml"])
    (sb.root / ".adlc").mkdir()
    os.symlink("../real.yml", str(sb.root / ".adlc" / "config.yml"))
    sb.commit(msg="config as a link")
    sb.feature("src/a.py")
    _assert_error(sb.path, "main:.adlc/config.yml is a symlink at the base")


def test_config_that_is_a_directory_at_the_base_is_an_error(make_repo):
    sb = make_repo(base_files=[".adlc/config.yml/inner.yml"]).feature("src/a.py")
    _assert_error(sb.path, "main:.adlc/config.yml is not a regular file at the base")


def test_config_over_the_cap_is_an_error(make_repo, monkeypatch):
    sb = make_repo(config="# " + "x" * lc.CONFIG_CAP_BYTES + "\n").feature("src/a.py")
    monkeypatch.setattr(lc, "_loader", lambda: pytest.fail("an over-cap config was parsed"))
    _assert_error(sb.path, "larger than %d bytes" % lc.CONFIG_CAP_BYTES)


def test_config_template_block_matches_the_schema(pyyaml):
    """The template's commented example is a valid `lanes.lite` block, and the
    template as shipped (block commented) parses to no overrides."""
    with open(_TEMPLATE, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    match = re.search(r"^# lanes:\n(?:#.*\n)+", text, re.MULTILINE)
    assert match, "templates/config-template.yml has no commented `# lanes:` block"
    block = "".join(line[2:] + "\n" for line in match.group(0).splitlines())
    overrides = lc.validate_lanes(pyyaml.safe_load(block))
    assert set(overrides) == set(lc.LITE_KEYS)
    # It sits between merge_order and branches.
    assert text.index("\nmerge_order:") < match.start() < text.index("\n# branches:")
    # Its `lanes` mentions are all whole-line comments, so a config copied from
    # it is not parsed; if it were, it must still load cleanly.
    assert not lc.may_carry_lanes(raw)
    outcome = lc._load_bytes(lc._loader(), raw)
    assert outcome.kind == "parsed", outcome.reason
    assert lc.validate_lanes(outcome.document) == {}


def test_config_template_as_the_base_config_leaves_the_defaults(make_repo, pyyaml):
    with open(_TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()
    sb = make_repo(config=template).feature("src/a.py", "src/b.py", "src/c.py", "src/d.py")
    assert _check(sb.path) == ("escalate", 4, [("max-files", "4 > 3")])


# --- git environment --------------------------------------------------------

def test_git_env_drops_config_injection_and_forces_no_replace():
    env = lc._git_env({
        "PATH": "/bin", "GIT_AUTHOR_NAME": "kept",
        "GIT_CONFIG_PARAMETERS": "'core.fsmonitor'='x'", "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "x",
        "GIT_CONFIG_KEY_17": "core.worktree", "GIT_CONFIG_VALUE_17": "/elsewhere",
        "GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_SYSTEM": "/s", "GIT_DIR": "/d",
        "GIT_INDEX_FILE": "/i", "GIT_GRAFT_FILE": "/gr", "GIT_REPLACE_REF_BASE": "refs/x/",
        "GIT_NO_REPLACE_OBJECTS": "0",
    })
    assert env == {"PATH": "/bin", "GIT_AUTHOR_NAME": "kept", "GIT_NO_REPLACE_OBJECTS": "1"}


def test_inherited_git_config_env_cannot_reach_the_check(make_repo, monkeypatch, tmp_path):
    sb = make_repo().feature("infra/main.tf")
    elsewhere = make_repo()
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text("#!/bin/sh\ntouch '%s'\n" % marker)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hook))
    monkeypatch.setenv("GIT_CONFIG_KEY_1", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", elsewhere.path)
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.bare'='true'")
    assert _check(sb.path) == ("escalate", 1, [("blocked-path", "infra/main.tf")])
    assert not marker.exists()


def test_replace_refs_cannot_rewrite_the_diff(make_repo):
    """A replacement for the base commit whose tree already holds the blocked
    file would make it vanish from the diff; replace objects are ignored."""
    sb = make_repo()
    sb.git("checkout", "-q", "-b", "stand-in", "main")
    sb.commit("infra/main.tf")
    stand_in_tree = sb.git("rev-parse", "HEAD^{tree}").stdout.strip()
    stand_in = sb.git("commit-tree", stand_in_tree, "-m", "stand-in").stdout.strip()
    main = sb.git("rev-parse", "main").stdout.strip()
    sb.feature("infra/main.tf", "src/a.py")
    sb.git("replace", "-f", main, stand_in)
    # Git itself, replacements honoured, no longer sees the blocked file ...
    assert sb.git("diff", "--name-only", "main...HEAD").stdout.split() == ["src/a.py"]
    # ... the check does.
    assert _check(sb.path) == ("escalate", 2, [("blocked-path", "infra/main.tf")])


# --- errors -----------------------------------------------------------------

def test_dirty_worktree_is_an_error(make_repo):
    sb = make_repo().feature("src/a.py")
    sb.write("src/a.py", "edited\n")
    _assert_error(sb.path, "uncommitted changes")


def test_untracked_file_is_an_error(make_repo):
    sb = make_repo().feature("src/a.py")
    sb.write("src/new.py")
    _assert_error(sb.path, "uncommitted changes")


def test_unknown_base_ref_is_an_error(make_repo):
    sb = make_repo().feature("src/a.py")
    _assert_error(sb.path, "resolving base ref 'origin/nope'", base="origin/nope")


@pytest.mark.parametrize("base", ["", "-p", "--output=/tmp/x"])
def test_option_shaped_or_empty_base_is_an_error(make_repo, base):
    sb = make_repo().feature("src/a.py")
    rc, lines = _run(sb.path, base)
    assert rc == 2
    assert _parse(lines)[0] == "error"


def test_worktree_that_is_not_the_top_level_is_an_error(make_repo):
    sb = make_repo().feature("src/a.py")
    _assert_error(os.path.join(sb.path, "src"), "not the top level")


def test_worktree_that_is_not_a_repo_is_an_error(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    rc, lines = _run(str(plain))
    assert rc == 2 and _parse(lines)[0] == "error"


def test_missing_worktree_is_an_error(tmp_path):
    _assert_error(str(tmp_path / "nope"), "not a directory")


@pytest.mark.parametrize("argv", [
    [], ["--worktree", "."], ["--help"], ["--work", ".", "--base", "main"],
    ["--worktree", ".", "--base", "main", "extra"],
])
def test_bad_arguments_are_an_error(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = lc.main(argv)
    lines = out.getvalue().splitlines()
    assert rc == 2
    assert lines[:2] == ["lane_check=error", "trigger=check-error"]
    assert lines[2].startswith("detail=usage:")


def test_unexpected_exception_is_an_error_not_a_pass(make_repo, monkeypatch):
    sb = make_repo().feature("src/a.py")

    def _boom(files, config):
        raise RuntimeError("boom")

    monkeypatch.setattr(lc, "evaluate", _boom)
    _assert_error(sb.path, "unexpected RuntimeError: boom")


def test_output_failure_is_an_error(make_repo, monkeypatch):
    sb = make_repo().feature("src/a.py")

    def _broken(lines):
        raise BrokenPipeError()

    monkeypatch.setattr(lc, "_write", _broken)
    assert lc.main(["--worktree", sb.path, "--base", "main"]) == 2


# --- by path ----------------------------------------------------------------

def test_runs_by_path_with_no_package_context(make_repo, tmp_path):
    """The shell partial runs this file by path from an arbitrary cwd."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    sb = make_repo()

    sb.feature("src/a.py")
    proc = subprocess.run([sys.executable, _SCRIPT, "--worktree", sb.path,
                           "--base", "main"],
                          cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "lane_check=pass\nfiles_counted=1\n"

    sb.feature("yarn.lock")
    proc = subprocess.run([sys.executable, _SCRIPT, "--worktree", sb.path,
                           "--base", "main"],
                          cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert proc.stdout == ("lane_check=escalate\nfiles_counted=1\n"
                           "trigger=dependency\ndetail=yarn.lock\n")

    proc = subprocess.run([sys.executable, _SCRIPT, "--worktree", sb.path,
                           "--base", "origin/nope"],
                          cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert proc.returncode == 2
    assert proc.stdout.startswith("lane_check=error\ntrigger=check-error\ndetail=")


@pytest.mark.parametrize("pattern", [".", "..", "infra/./x", "a/../b", "./.."])
def test_dot_segment_pattern_is_a_schema_error(pattern):
    """A pattern that can never match a changed path fails closed, like an empty one."""
    with pytest.raises(lc.LaneCheckError):
        lc.validate_lanes({"lanes": {"lite": {"blocked_paths": [pattern]}}})


def test_symlinked_adlc_dir_at_the_base_is_an_error(make_repo):
    """git does not descend a symlinked `.adlc`, so its config would silently vanish."""
    sb = make_repo()
    real = sb.root / "real-adlc"
    real.mkdir()
    (real / "config.yml").write_text("lanes:\n  lite:\n    max_files: 1\n")
    os.symlink("real-adlc", str(sb.root / ".adlc"))
    sb.commit(msg="symlinked .adlc at base")
    sb.feature("src/a.py")
    _assert_error(sb.path, ".adlc is not a directory")
