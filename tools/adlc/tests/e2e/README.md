# tools/adlc/tests/e2e — the plugin route, end to end

`plugin-sandbox.sh` installs the `adlc` plugin on a sandbox `HOME` that has no toolkit
symlinks and no machine state. It then checks what REQ-669 promises about that install
(TASK-131). It is a **release gate**: [`RELEASING.md`](../../../../RELEASING.md) step 1
runs it. It is not part of the default test run, because the full run needs model calls,
a GitHub repo and network.

The plugin it installs is a `git archive` snapshot of this checkout (`--ref`, default
`HEAD`), added as a local-path marketplace in place of `atelier-fashion/adlc-toolkit`.
Commit what you want tested first. Uncommitted edits are not in the snapshot.

## What it needs

The offline checks need only the tools below. Each other check names the prerequisite
it lacks and reports **SKIPPED**, never PASS. An unrun check is not a pass (LESSON-581).

| Prerequisite | Used by | How to provide it |
|---|---|---|
| macOS, `sh`, `git`, `python3`, `tar` | everything | already there |
| `claude` on `PATH` | every plugin check | Claude Code. `claude plugin marketplace add`, `install`, `update` and `list` work without a login |
| `node` 21 or later | `symlink_only_regressions.suite_node` | the suite passes a quoted glob that `node --test` expands itself |
| `bash`, `zsh`, `dash` | the shells the root-line check runs under | a missing shell is left out |
| **Model access in a sandbox `HOME`**, and `--with-model` | `init_spec_status`, `doctor_in_project`, both `guard_transcripts`, `lite_pipeline`, `printed_steps_typed`, `template_drift_skill_run` | The sandbox `HOME` does not carry your own login. Export `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY` in the shell that runs the script. The script passes exactly those two variables into the sandbox, through the child's environment and never its arguments. `--with-model` is the opt-in, because these checks spend money |
| **A throwaway GitHub repo** | `lite_pipeline` | Create it yourself, for example `gh repo create OWNER/adlc-e2e-20261029 --private`, and pass `--throwaway-repo OWNER/adlc-e2e-20261029`. The name must contain `e2e`, so a real repo cannot be driven by mistake. The run pushes to it, and `/adlc:proceed` opens and merges a PR in it. The script never creates or deletes a repo. At the end it **prints** the delete command for you to run |
| **`GH_TOKEN`, a fine-grained token scoped to that repo** | `lite_pipeline` | Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with **Repository access: Only select repositories** set to the throwaway repo alone, and the permissions **Contents: Read and write** and **Pull requests: Read and write** (Metadata: Read-only is added for you). Give it a short expiry, export it as `GH_TOKEN` in the shell that runs the script, and revoke it after the run. It is the **only** GitHub credential the sandbox gets: your `gh` login, your `gh` config directory and `GITHUB_TOKEN` are never passed in. Without `GH_TOKEN` the check is SKIPPED with that reason. Do not export `"$(gh auth token)"` here: that token reaches every repo you can |

**Cost.** There are six short model calls: `/adlc:init` and `/adlc:spec` in each of two
cases, then `/adlc:status` and `/adlc:template-drift`. Each is capped by
`--max-budget-usd`, which defaults to $1. The `/adlc:proceed` run is capped by
`--pipeline-budget-usd`, which defaults to $15. Each typed next step is capped at $0.25
and runs with no tools. With the defaults, a full run is bounded at about $21 plus $0.25
per typed step. **Time.** The offline checks take about 10 minutes, and the partials suite
is most of that. A model run adds up to `--pipeline-timeout-min`, which defaults to 90.

## How to run it

```sh
# Offline checks only. The model and GitHub checks are skipped, so at best this exits 2
# (INCOMPLETE); it exits 1 when an offline check fails.
sh tools/adlc/tests/e2e/plugin-sandbox.sh

# The full release gate.
export CLAUDE_CODE_OAUTH_TOKEN=...              # from `claude setup-token`
gh repo create OWNER/adlc-e2e-20261029 --private
sh tools/adlc/tests/e2e/plugin-sandbox.sh --with-model \
  --throwaway-repo OWNER/adlc-e2e-20261029 --keep
gh repo delete OWNER/adlc-e2e-20261029 --yes    # yourself, once you have read the logs

# One case, or several.
sh tools/adlc/tests/e2e/plugin-sandbox.sh --case test_release_update --case symlink_only_regressions
sh tools/adlc/tests/e2e/plugin-sandbox.sh --list
```

`--help` lists every option. Set `ADLC_E2E_TMPROOT` to choose where the sandbox is made.
It defaults to `$TMPDIR`, else `/tmp`, and it must not be inside a git work tree.

`sh tools/adlc/tests/e2e/plugin-sandbox.selftest.sh` checks the script's own contract in
about 30 seconds, offline and with no model call: `--list` names the five cases, `--help`
names `GH_TOKEN`, an unknown case or option exits 1 and leaves no sandbox, and a case
whose model check cannot run exits 2 with `RESULT: INCOMPLETE` and no FAIL. Run it after
changing `plugin-sandbox.sh`.

## What it does to the machine

- It makes one directory with `mktemp -d "$ADLC_E2E_TMPROOT/adlc-e2e.XXXXXX"`, and it
  validates that path before writing into it and again before removing it. On exit it
  removes the directory, unless you pass `--keep`, which prints the path and the `rm`
  command.
- Inside that directory it makes several `HOME`s:
  - `plugin-home` and `release-home` are plugin-only. In both, `~/.claude/skills` and
    `~/.claude/agents` are **mode-000 directories**, so any read under them fails (BR-2).
  - `symlink-home` is made by running the snapshot clone's own `install.sh`.
  - `auth-home` and `version-home` are only for `claude auth status` and `claude --version`.

  Each `HOME` gets a `.gitconfig` with your git identity and nothing else. The GitHub
  case adds a `gh auth git-credential` helper to `plugin-home`'s copy, so `git push`
  can reach the throwaway repo with `GH_TOKEN`.
- Every sandbox command runs with an allowlisted environment. That is the sandbox `HOME`
  and `TMPDIR`, and your `LANG`, `LC_*`, `TZ` and `PYTHONDONTWRITEBYTECODE` when you set
  them. Its `PATH` is
  your `PATH` with every entry under your real `HOME` removed, so `~/bin/adlc` cannot
  answer. `PYTHONUSERBASE` points at your Python user base, so packages installed with
  `--user`, such as PyYAML and pytest, stay importable. The sandbox sees none of your
  `~/.claude` by default (see the next section for what that does not stop). The model
  credential goes only to `claude` calls, and `GH_TOKEN` only to the GitHub case's
  calls: its `git` and `gh` commands and its `claude` sessions. No later case's
  session gets it.
- `adlc doctor` always runs in a directory with no git remote. Its `reservations` check
  pushes a probe ref to the current repo's `origin`, so running it in a real checkout
  would write to GitHub.
- Your own `~/.claude` is never written by the script, and it is never read for
  toolkit files.

### The model runs are not filesystem-isolated

A sandbox `HOME` decides what a program finds **by default**. It is not a boundary. A
`claude -p` run with the Bash, Read and Write tools runs as your user, with your file
permissions, and an absolute path such as `/Users/<you>/...` reaches your real home,
your real `~/.claude`, your SSH keys and anything else you can read. The checks assert
that the toolkit never *looks* there (BR-2), which is a property of the skills, not a
sandbox the model cannot leave.

So the model runs get the narrowest credentials that work: a model key or OAuth token,
and for `lite_pipeline` only, `GH_TOKEN` scoped to the throwaway repo. Run a model pass
on a machine, or as a user, whose files you would accept a misbehaving session reading.
If that is not this machine, run the offline checks only: they make no model call.

## Reading the output

Each check prints one line, `[PASS|FAIL|SKIPPED] <case>.<check> — <detail>`. A FAIL is
followed by an excerpt of its log. The summary gives one line per case:

- **PASS**: every check passed.
- **FAIL**: at least one check failed.
- **PARTIAL**: some checks passed and the rest were skipped.
- **SKIPPED**: nothing ran.

When anything was skipped, a line starting `INCOMPLETE:` counts the cases and checks that
did not run, and each skipped check is listed with its reason. The last line is `RESULT:`.

| Exit | Meaning |
|---|---|
| 0 | every check ran and passed |
| 1 | at least one check failed |
| 2 | nothing failed, but at least one check was skipped. The run is incomplete and does not clear the release gate |

Use `--keep` for a model run. The logs, stream-json output and session transcripts stay
in `<sandbox>/logs/` and `<sandbox>/<home>/.claude/projects/`.

## Cases and checks

| Case | Check | Needs | What it asserts |
|---|---|---|---|
| `init_spec_status_doctor` (AC-1) | `bri1_install` | — | `claude plugin marketplace add` and `claude plugin install adlc@adlc-toolkit` succeed on a guarded, plugin-only `HOME`, and `claude plugin list --json` shows the snapshot's version, enabled |
| | `session_hook` | — | `scripts/session-start.sh` is run with the `CLAUDE_PLUGIN_ROOT` and `CLAUDE_ENV_FILE` Claude Code gives this local-path install, which is its source directory. It writes a delegation-off `config.yml` and the PATH line, and leaves the pointer as it was (none), because the hook records only a plugin-cache copy (LESSON-718). A real session runs the hook itself; offline it is run directly |
| | `session_hook_cache_copy` | — | the hook again, with the cache copy as its root, which is what a GitHub-route session gets. It writes the pointer, naming the cache copy resolved. The guard's raw root-line check reads that pointer |
| | `doctor_plugin_route` | — | `adlc doctor`, found through the hook's PATH line, reports `route=plugin`, `plugin-route` and `doubled-install` PASS, the four symlink checks SKIP, and no FAIL |
| | `init_spec_status` | model | in a local repo with no remote, `/adlc:init` writes the `.adlc/` context and templates, the transcript shows `/adlc:init` resolved to the plugin skill, `/adlc:spec` writes a `REQ-*/requirement.md`, and `/adlc:status`'s result names that REQ |
| | `doctor_in_project` | model | the doctor again, inside the project `/adlc:init` made |
| | `guard_transcripts` | model | the same transcript scan as the next case's `guard_transcripts`, over this case's runs |
| `lite_req_end_to_end_with_read_guard` (AC-2, BR-2) | `guard_armed` | — | both guard directories are mode 000, and listing either is refused. An unarmed guard would pass everything below by accident |
| | `guard_root_line` | — | the canonical ToolkitRoot line resolves to the plugin under `sh`, `bash`, `zsh` and `dash`: to the root the session loads as the loader substitutes it, and, as raw, unsubstituted text, to the cache copy the pointer file names (ADR-1 arm 3). Nothing goes to stderr |
| | `guard_partials` | — | every `partials/*.sh` sources through the guarded spelling with exit 0 and an empty stderr. `ethos-include.sh` prints the plugin's `ETHOS.md`, and `delegate-tools-path.sh` resolves to the plugin's `tools/delegate` |
| | `lite_pipeline` | model, GitHub | in the throwaway repo, `/adlc:spec --lite` writes a REQ with `lane: "lite"`. `/adlc:proceed` opens a PR that `gh pr view --json state` reports `MERGED`, and leaves either a new `LESSON-*` on `main` or the wrapup's `NO_ENTRY:` line |
| | `guard_transcripts` | model, GitHub | no tool call in any transcript names `~/.claude/skills` or `~/.claude/agents`, apart from the root line's own existence test, and no tool result was refused under the guard |
| `symlink_only_regressions` (AC-3, BR-3) | `install_symlink_route` | — | the snapshot clone's `install.sh` links `~/.claude/skills` and `~/.claude/agents` to the clone on `symlink-home` |
| | `install_dry_run_zero_actions` | — | `install.sh --dry-run` plans no action: no `would:` lines |
| | `doctor_symlink_route` | — | the doctor, run with `~/bin` first on `PATH` as the rc block `install.sh` wrote puts it, reports `route=symlink`, no doubled install (the benign path of BR-11) and no FAIL |
| | `suite_partials`, `suite_pytest`, `suite_node`, `suite_lint` | — | `sh partials/tests/run.sh`, `python3 -m pytest tools -q`, `node --test 'workflows/tests/*.test.js'` and `tools/lint-skills/check.sh` exit 0 in the clone, with the symlink-only `HOME`, and print no line starting `FAIL`. Exit 0 with a `FAIL` line is a FAIL: a failure the harness lost from its count is still a failure |
| `printed_next_steps_runnable` (BR-10, ADR-5) | `builtin_collision_static` | — | Collects the skill names that shipped skills, agents, partials, scripts and templates tell the user to run (`run /x`, `/x first`, …). Intersects them with the command names and aliases compiled into the installed `claude` binary. It FAILs when a printed bare name **is** a built-in command name, because a typed bare name reaches the built-in, not `/adlc:<skill>`. A line that also carries `/adlc:<x>` prints both spellings (conventions.md, "Skill names Claude Code also owns") and is counted as dual-spelled, not bare. An alias collision, or a name no printed instruction leaves bare, is listed but does not fail. The lint's `builtin-collision` check uses the same instruction patterns, so a clean lint leaves this check nothing to fail on. It SKIPs when it cannot read the binary's command table |
| | `printed_steps_typed` | model | each `/x` the assistant printed in the transcripts, and each colliding name, is typed with no tools, as printed for the plugin install: a colliding name as `/adlc:<x>`, which is the spelling its dual-spelled text gives plugin users. The transcript must show it resolved to `/adlc:<x>`. Each colliding name is then also typed bare, and where it went is reported in the detail without failing the check |
| `test_release_update` (AC-8, BR-14) | `plugin_update` | — | after the sandbox copy's `VERSION` and every manifest it holds are bumped to the test version (default: patch + 1, `-e2e`), `claude plugin marketplace update`, `claude plugin update adlc@adlc-toolkit` and `claude plugin list` show the new version, with a cache copy at it |
| | `template_drift_baseline_fence` | — | `/adlc:template-drift`'s Step 0a fence, with `${CLAUDE_PLUGIN_ROOT}` rewritten as the loader rewrites it, prints `baseline: adlc plugin <test version> (<root>)`. It does so for the new cache copy and for the root a session loads. The old cache copy is the control, and must still print the old version |
| | `template_drift_skill_run` | model | a real `/adlc:template-drift` run has a Bash tool result that prints that baseline line |

## Known limits

- **The local-path marketplace.** A plugin from a local-path marketplace runs from its
  source directory, not from the cache copy that is also written (REQ-669
  `verification.md` row 12 and N3). So the session-facing checks exercise the source
  directory. The hook does not record that directory in `~/.claude/adlc/plugin-root`,
  because the pointer is machine-global and only a plugin-cache copy may claim it, so
  the raw root-line check reads a pointer written by a second hook run with the cache
  copy as its root. `claude plugin marketplace add` takes no `file://` git URL, so the
  GitHub path, which loads from the cache, cannot be driven offline. `RELEASING.md`
  step 7 checks it against the real release.
- **What the guard can see.** A mode-000 directory turns a read into an error. But a
  `test -d` or `test -f` under it just returns false, with no error. The checks therefore
  also assert outcomes: ToolkitRoot equals the plugin root, and `ETHOS.md` and
  `tools/delegate` come from the plugin. A fallback that an existence test would hide
  still changes one of those outcomes.
- **The command-table read.** The static collision check reads the installed `claude`
  binary. It looks for the shapes that Claude Code 2.1.258 compiles its commands to. On a
  build where those shapes are gone, it SKIPs rather than passing.
- **Locale and bytecode.** The suites run with your own `LANG`, `LC_*`, `TZ` and
  `PYTHONDONTWRITEBYTECODE`, as you would run them yourself. These values travel as
  copies the shell makes. The launcher is Python, and in the C locale Python sets
  `LC_CTYPE` to UTF-8 in its own environment (PEP 538), which would change what `awk`
  sees in the child. The harnesses no longer depend on either: `lesson-check.test.sh`
  runs `/review`'s lookup program under `LC_ALL=C` and checks the partial's BOM strip
  under a UTF-8 locale as well, and `session-start.test.sh` runs its doctor case with
  `PYTHONDONTWRITEBYTECODE=1`, because the Xcode `python3` otherwise writes a bytecode
  cache under the test's `HOME`.
- **Failures a harness does not count** fail the suite check (see `suite_partials`
  above). `intake.test.sh`'s AC-6 used to print a `FAIL` that its subshell dropped from
  the count whenever `adlc-read` was not installed. It now puts a stub `adlc-read` on
  `PATH`, so the disabled path is reached on every machine, and its subshell reports
  what it failed.

## `claude-exec-manual.sh` — the exec engine's logged-out table

Reruns `.adlc/research/harness-probes/claude-exec-manual.md` against the installed `claude`
(REQ-659). It runs under `env -i` in a temp directory with a throwaway `HOME`, so it reads no
credential, spends nothing, and needs no login: a logged-out `claude -p` still reads settings,
fires hooks, starts MCP servers and writes a transcript (LESSON-759). It prints one line per row
and exits non-zero on a surprise. It is not part of the default test run, because it needs the
binary. It says nothing about a tool call: those rows are owed to a logged-in run.
