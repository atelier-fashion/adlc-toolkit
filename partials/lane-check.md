# `partials/lane-check.sh` — the lite lane's diff check

The mechanical half of REQ-652 BR-6. Before a lite REQ's PR leaves draft, and
again before merge, `/proceed` checks the actual diff against the integration
branch. Every rule is a property a machine can test, not a judgment
(LESSON-626). Any failing rule means the change crossed a line, and the REQ
escalates to the full lane (`proceed/phases-lite.md` "The lane check").

The engine is `tools/adlc/lane_check.py`, always the installed toolkit's copy
(see "Interpreter"). The partial is the sourced shell entry point the skills
call.

## Call protocol

Source the partial and call it **in the same fenced block** (the cross-fence-fn
rule, conventions.md "Bash in skills"):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
adlc_lane_check "<worktree>" "origin/<integrationBranch>"; echo "lane_check_rc=$?"
```

This bare form is the contract; the skills call it through the guarded fence in
`proceed/phases-lite.md` "The lane check", which first fetches, refuses a local
`HEAD` that is not the pushed head, and refuses a branch that edits
`.adlc/partials` or `.adlc/tools`. The partial does **not** fetch. The caller fetches `origin/<integrationBranch>`
first and passes that ref, never local `main` (LESSON-391).

## Return contract

| rc | `lane_check=` | Meaning |
|----|---------------|---------|
| 0 | `pass` | the change stayed inside the lite lane |
| 1 | `escalate` | at least one rule failed |
| 2 | `error` | the check could not run: a dirty worktree, an unknown base ref, an empty diff against the base, a git failure, a config at the base that cannot be read or fails its schema, a usage error, the engine or the interpreter resolver not found, or an engine run that ended any other way |

**An error is not a pass** (LESSON-581). `/proceed` handles rc 2 exactly like
rc 1, with trigger `check-error`: escalation is the conservative direction.

stdout is normalized, one fact per line, with no prose remediation (LESSON-572):

```
lane_check=escalate
files_counted=4
trigger=blocked-path
detail=.github/workflows/ci.yml
trigger=max-files
detail=4 > 3
```

`lane_check=` comes first, then `files_counted=`, then one `trigger=` / `detail=`
pair per failing fact. On an error the output is exactly `lane_check=error`,
`trigger=check-error` and a one-line `detail=`, with no `files_counted=`.

The wrapper adds no line and swallows no stderr. It captures the engine's stdout
and exit code and hands both through unchanged when the exit code is 0, 1 or 2
and the first line is the verdict that code means (`lane_check=pass`,
`lane_check=escalate`, `lane_check=error`). Anything else is an error, printed
as the three-line contract with rc 2: an exit code outside 0-2 (127 for a
missing interpreter, 137 for a killed one; `detail=lane_check.py exited <rc>`),
or a code whose first line does not match it, such as an interpreter that exits
2 without running the engine at all. The wrapper also refuses, with the same
contract and `detail=the engine is inside the worktree under check`, when the
engine's directory resolves inside the worktree it would check: `ADLC_TOOLKIT_ROOT`
naming the tree itself, a copy vendored in it, or either reached through a
symlink. A change must never be judged by code it can edit (LESSON-718).

Every `detail` is one line that `str.splitlines()` cannot split: a backslash is
written `\\`, and control characters, the Unicode line and paragraph separators,
zero-width and bidi format characters, the BOM and undecodable bytes in a path
are written as `\xNN` / `\uNNNN` escapes.

## Rules

| Trigger | Fails when | Applies to |
|---------|-----------|------------|
| `blocked-path` | a changed path matches a `blocked_paths` glob (case-insensitively); or a change adds, removes or touches a symlink (`detail=symlink: <path>`) | every changed file, including test and `.adlc/` files |
| `dependency` | a changed path is a lockfile or a dependency manifest (by basename, case-insensitively); or a change adds, removes or moves a submodule (`detail=submodule: <path>`) | every changed file |
| `deploy-units` | the changed files map to more than one unit | only when `deploy_units` is declared; counted files only; a file matching no unit glob is ignored |
| `max-files` | more counted files changed than `max_files` | counted files: changed files not matching `count_exclude` |

Changed files are `git diff --raw -z --no-renames <base>...HEAD`, so a rename is
the deletion and the addition, both checked and both counted, and each side's
file mode is known: mode `120000` is a symlink and `160000` a submodule. An empty
diff is an error, not a pass: a lite REQ always has commits, so an empty diff
means the base is wrong. Lines are never counted: a copy edit can touch many
lines and stay trivial, and a one-line change to a blocked path is already
caught by `blocked_paths`.

## Defaults and project overrides

The check reads `.adlc/config.yml` **as committed at the base ref**, never from
the worktree's disk, so a branch cannot loosen its own lane: not by committing a
new config (itself a blocked path), and not with `skip-worktree` or a gitignored
local copy. The file may carry a `lanes.lite` block:

```yaml
lanes:
  lite:
    max_files: 3                                   # replaces the default
    blocked_paths: ["packages/domain/**"]          # added to the defaults
    count_exclude: ["content/**"]                  # added to the defaults
    deploy_units:                                  # glob -> unit id
      "apps/website/**": website
      "apps/admin/**": admin
```

A file whose bytes do not contain `lanes` (nor a backslash or a NUL, through
which a YAML escape or a UTF-16 encoding could still spell it) is never parsed,
so a missing PyYAML costs nothing there. Whole-line comments are skipped, so a
config copied from `templates/config-template.yml`, whose example block is
commented out, is not parsed either. Any other file is parsed: a flow mapping,
an indented document or a trailing comment is never skipped. Absent at the base, the defaults apply; present as a symlink, a
directory or a submodule, or over 64 KiB, it is an error.

Project lists **extend** the defaults and never replace them, so a project
cannot quietly unblock `.github/**`. `max_files` replaces the default. The
schema is closed: an unknown key, a value of the wrong type, or an empty
pattern is an error (REQ-609), not a silent skip.

The defaults are in `tools/adlc/lane_check.py`. The blocks below mirror them;
`tools/adlc/tests/test_lane_check.py` parses every backticked entry between the
`lane-defaults` markers and fails when the two disagree.

**`blocked_paths`**, matched case-insensitively:

<!-- lane-defaults blocked_paths -->
- CI: `.github/**`, `.gitlab-ci.yml`, `.gitlab/**`, `.circleci/**`,
  `azure-pipelines.yml`, `azure-pipelines.yaml`, `Jenkinsfile`,
  `bitbucket-pipelines.yml`, `.buildkite/**`
- deploy and infra: `deploy/**`, `infra/**`, `infrastructure/**`,
  `terraform/**`, `**/*.tf`, `**/*.tfvars`, `**/k8s/**`, `**/helm/**`, `charts/**`,
  `**/Dockerfile*`, `**/Containerfile*`, `**/docker-compose*.yml`,
  `**/docker-compose*.yaml`, `**/compose.yml`, `**/compose.yaml`,
  `**/cloudbuild*.yml`, `**/cloudbuild*.yaml`, `**/serverless.yml`,
  `**/serverless.yaml`, `vercel.json`, `firebase.json`, `**/fastlane/**`
- data: `**/migrations/**`, `**/db/migrate/**`, `**/alembic/**`, `**/*.sql`,
  `**/*.proto`, `**/*.prisma`, `**/*.graphql`, `**/openapi*.*`,
  `**/schema*/**`, `**/schema*.*`
- security: `**/auth/**`, `**/security/**`, `**/*.rules`, `firestore.rules`,
  `**/.env*`, `**/*.pem`, `**/*.key`, `**/*.entitlements`
- pipeline and agent config: `.adlc/config.yml`, `.adlc/partials/**`,
  `.adlc/tools/**`, `.adlc/workflows/**`, `.adlc/agents/**`, `.github/agents/**`,
  `.github/hooks/**`, `.claude/**`, `harness/**`, `templates/permissions.yml`,
  `templates/hooks.yml`, `.claude/settings*.json`, `.mcp.json`, `**/CLAUDE.md`,
  `**/AGENTS.md` (REQ-666 BR-10: the vendored agent checklists, and the agent and
  hook config the harness adapters write, which the CI glob above already covers;
  REQ-657 BR-14: the adapters and their goldens and the permission and hook
  sources, so a lite PR cannot widen an allowlist or soften a hook)
- git hooks and package-manager config: `.husky/**`, `.githooks/**`,
  `.pre-commit-config.yaml`, `lefthook.yml`, `.gitmodules`, `**/.npmrc`,
  `**/.yarnrc*`, `lefthook.yaml`, `.lefthook.yml`, `.lefthook.yaml`,
  `**/.lintstagedrc*`
- more CI: `.travis.yml`, `.drone.yml`, `.gitea/**`, `.forgejo/**`,
  `appveyor.yml`, `bitbucket-pipelines.yaml`, `**/azure-pipelines*.yml`,
  `**/azure-pipelines*.yaml`
- more deploy: `netlify.toml`, `fly.toml`, `app.yaml`, `Procfile`,
  `wrangler.toml`, `Pulumi.yaml`, `cdk.json`, `**/*.bicep`
- code that runs at install or build time: `.yarn/releases/**`,
  `.pnpmfile.cjs`, `.pnp.cjs`, `pnpm-workspace.yaml`, `**/gradle/wrapper/**`,
  `**/gradlew`, `**/gradlew.bat`, `**/settings.gradle*`,
  `**/gradle.properties`, `.mvn/**`, `**/mvnw`, `.cargo/**`, `**/build.rs`
- more agent and editor config: `**/CLAUDE.local.md`, `**/GEMINI.md`,
  `.cursor/**`, `.cursorrules`, `.codex/**`, `.gemini/**`,
  `.vscode/tasks.json`, `.devcontainer/**`
- the project's ADLC context, which names the gates every later run executes:
  `.adlc/context/**`
- the lane check's own machinery, for the toolkit itself:
  `tools/adlc/lane_check.py`, `tools/delegate/_machine_config.py`,
  `partials/lane-check.sh`, `partials/forge.sh`, `proceed/phases-lite.md`
<!-- /lane-defaults -->

**Dependency files**, matched case-insensitively by basename anywhere in the
tree. Lockfiles:

<!-- lane-defaults dependency_lockfiles -->
`package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`,
`bun.lock`, `bun.lockb`, `Gemfile.lock`, `poetry.lock`, `uv.lock`,
`Pipfile.lock`, `Cargo.lock`, `go.sum`, `go.work.sum`, `Package.resolved`,
`Podfile.lock`, `composer.lock`, `pubspec.lock`, `.terraform.lock.hcl`,
`deno.lock`, `flake.lock`, `mix.lock`, `packages.lock.json`,
`MODULE.bazel.lock`
<!-- /lane-defaults -->

Manifests:

<!-- lane-defaults dependency_manifests -->
`package.json`, `pyproject.toml`, `requirements*.txt`, `Pipfile`, `setup.py`,
`setup.cfg`, `Gemfile`, `Cargo.toml`, `go.mod`, `go.work`, `Package.swift`,
`Podfile`, `build.gradle*`, `libs.versions.toml`, `pom.xml`, `*.csproj`,
`composer.json`, `pubspec.yaml`, `Directory.Packages.props`, `*.gemspec`,
`mix.exs`
<!-- /lane-defaults -->

**`count_exclude`**, matched case-sensitively:

<!-- lane-defaults count_exclude -->
tests (`**/test/**`, `**/tests/**`, `**/__tests__/**`, `**/*.test.*`,
`**/*.spec.*`, `**/test_*.py`, `**/*_test.*`), `.adlc/**`, `CHANGELOG*`
<!-- /lane-defaults -->

**`max_files`**:

<!-- lane-defaults max_files -->
`3`
<!-- /lane-defaults -->

Globs are matched against repo-relative POSIX paths, anchored at the root.
`**/` matches zero or more directories, a trailing `/**` matches everything
beneath, and `*` does not cross `/`. Every pattern, default or project, in all
three lists and the `deploy_units` keys, is normalized first: a leading `./` or
`/` is dropped, a trailing `/` becomes `/**`, and a pattern with no glob
character also matches everything beneath it (`infra` is `infra` or
`infra/**`). `blocked_paths` and the dependency names match case-insensitively,
so `src/Auth/` and `dockerfile` are caught; `count_exclude` and `deploy_units`
are case-sensitive.

## Interpreter

The engine is **always the installed toolkit's**,
`"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"`, never a
copy in the tree under check: a branch that could supply its own checker could
certify itself (LESSON-718). ToolkitRoot is installed by definition. The fence's
root line resolves `$ADLC_TOOLKIT_ROOT` to the plugin's cache copy or to the clone
behind the skills symlink, never to the branch under review, and an
unset variable defaults to that symlink install (REQ-669 ADR-2). The root must be
an absolute path, and so must `HOME` when the default is used; either refusal is
an error (rc 2). A missing engine is an error (rc 2) whose message names both
install routes. The engine finds its config loader,
`tools/delegate/_machine_config.py`, next to its own real path, so that comes
from the installed toolkit too. The toolkit's own tests point `HOME`, or
`ADLC_TOOLKIT_ROOT`, at a sandbox install that is the checkout under test, which
is how they exercise the working copy rather than the installed one.

The partial resolves Python with `forge.sh`'s `_adlc_forge_python` (the delegate
venv when it carries PyYAML, else `python3`), so the forge adapter and the lane
check never pick different interpreters. Calling a `_`-prefixed function from
another partial is a known coupling (REQ-652 ADR-3); extracting the resolver into
its own partial is a follow-up. If the resolver is undefined after sourcing
`forge.sh`, or prints nothing, the check is an error (rc 2). The engine is
invoked through `command`, so a shell function named `python3` cannot intercept
it (REQ-609 D5).

## Vocabulary

The closed sets every writer and reader of the lane uses. They are defined here
and nowhere else; `tools/lint-skills`' `lane-vocabulary` check reads this block
and fails on any `lane` value or trigger name outside it at the declared sites
(REQ-652 BR-17, ADR-13). A missing `lane` key in a spec or state file means
`full`.

<!-- lane-vocabulary -->
- lane: `lite`, `full`
- trigger: `blocked-path`, `dependency`, `deploy-units`, `max-files`, `check-error`, `implementer`, `reversal`, `operator`
- actor: `solo`, `sprint-runner`, `operator`
- lane_check: `pass`, `escalate`, `error`
<!-- /lane-vocabulary -->

The first four triggers come from this check, `check-error` from an rc of 2,
`implementer` from a mid-implementation finding (BR-9), `reversal` from the
`lite-reviewer` pass (AC-9), and `operator` from `/proceed --full` (BR-11).
