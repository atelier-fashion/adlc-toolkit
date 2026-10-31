---
req: REQ-665
verified: 2026-10-30
verifier: TASK-203
claude_code_version: 2.1.258
verdict: partial
---

# REQ-665 — what was verified (TASK-203)

This file records what was run for BR-13 and which claims rest on it. A claim is
**verified** only if it was observed here, on 2026-10-30, with the command shown. Anything
else is **unverified**. Paths are written with `~`.

The short version: only Claude Code was exercised, and only offline. No model turn ran.
Nothing about Cursor, Copilot CLI or Gemini CLI has run on a real install. One Claude Code
command, `claude plugin validate .claude-plugin/plugin.json --strict`, still fails, for a
reason that predates this REQ, and AC-6 was revised to say so (see "`claude plugin validate`").

## Which harnesses were exercised

| Harness | Binary | Probe result | Exercised |
|---|---|---|---|
| Claude Code | `/opt/homebrew/bin/claude`, 2.1.258 | `claude.json` | Yes, offline: validate, tests, the e2e sandbox. No model turn |
| Cursor | none on PATH (`agent`, `cursor`) | none | No. Docs only |
| Copilot CLI | none on PATH (`copilot`) | none | No. Docs only |
| Gemini CLI | none on PATH (`gemini`) | none | No. Docs and source only |

`command -v agent cursor copilot gemini` printed nothing. No CLI was installed for this
REQ. `.adlc/research/harness-probes/` holds only `claude.json` and `fixtures/`.

Environment: macOS, Node v26.7.0, Python 3.9.6.

## Preconditions (LESSON-747)

A CLI launched from an agent session does not inherit that session's login, so this was
checked before relying on a live run:

```
$ claude --version
2.1.258 (Claude Code)

$ claude auth status
loggedIn: false, authMethod: none        (exit 1; only these two fields were kept)
```

So no model turn ran, in the sandbox or out of it. Every check that needs one is SKIPPED
below, not passed.

## `claude plugin validate`

```
$ claude plugin validate . --strict
Validating marketplace manifest: ~/GitHub/adlc-toolkit/.claude/worktrees/jolly-leakey-c4d6e9/.claude-plugin/marketplace.json

✔ Validation passed
(exit 0)

$ claude plugin validate .claude-plugin/plugin.json --strict
Validating plugin manifest: ~/GitHub/adlc-toolkit/.claude/worktrees/jolly-leakey-c4d6e9/.claude-plugin/plugin.json

Validating plugin: ~/GitHub/adlc-toolkit/.claude/worktrees/jolly-leakey-c4d6e9/CLAUDE.md

⚠ Found 1 warning:

  ❯ root: CLAUDE.md at the plugin root is not loaded as project context. To ship context with your plugin, use a skill (skills/<name>/SKILL.md) instead.

✘ Validation failed (--strict treats warnings as errors)
(exit 1)
```

**The second command fails. AC-6 was revised at Phase 4 to the two forms that pass, and the
failure is in the spec's `## Deferred`.** This REQ did not cause it:

| Run | Result |
|---|---|
| The same command without `--strict` | exit 0, `Validation passed with warnings` |
| The same command, `--strict`, on a `git archive` of `origin/main` (884e9c3) | exit 1, the same warning |
| The same command, `--strict`, on a `git archive` of HEAD with `CLAUDE.md` removed | exit 0, `Validation passed` |

The root `CLAUDE.md` came in with REQ-657 (108db1f), after REQ-669 recorded a pass on
2026-10-28. The Claude Code plugin reference documents the warning. `plugin.json` itself is
clean, and `.claude-plugin/` is unchanged by this REQ. Fixing it is out of this REQ's scope.
The README's loader row and a note under RELEASING step 3 now say which form fails and why;
the failing command itself stays in RELEASING step 3 until the follow-up moves `CLAUDE.md`.

## The plugin route, through the partials

```
$ sh partials/tests/plugin-route.test.sh
plugin-route.test.sh: 103 cases executed
plugin-route.test.sh: ALL CASES PASS (/bin/sh)
(exit 0; 103 PASS lines, 0 FAIL lines)
```

## The e2e sandbox, offline

```
$ sh tools/adlc/tests/e2e/plugin-sandbox.sh
```

Run with no model and no GitHub credentials in the environment, in its own `mktemp` sandbox
`HOME`, against a `git archive` of HEAD (8020cdf). It exited 2, which is its designed result
when a check is skipped. 18 checks passed, 0 failed, and 6 were skipped.

| Case | Pass | Fail | Skipped |
|---|---|---|---|
| `init_spec_status_doctor` | 4 | 0 | 3 |
| `lite_req_end_to_end_with_read_guard` | 3 | 0 | 1 |
| `symlink_only_regressions` | 7 | 0 | 0 |
| `printed_next_steps_runnable` | 1 | 0 | 1 |
| `test_release_update` | 3 | 0 | 1 |

Every skip gives the same root cause: `loggedIn` false in a sandbox `HOME` and no token set,
or a case that needed that run's output. The result line is `INCOMPLETE (no check failed)`,
which does not clear RELEASING's step 1 gate.

The checks this REQ leans on passed:
`symlink_only_regressions.install_dry_run_zero_actions`, on a healthy symlink-only sandbox
`HOME` (0 `would:` lines), and `printed_next_steps_runnable.builtin_collision_static`.

It ran a second time with `--ref` set to a throwaway commit of this task's staged tree, so
that its suites read these documents and the new tests. The result was the same: exit 2, 18
passed, 0 failed, 6 skipped, with the same counts per case. Its `suite_pytest` line reads
3065 passed, 7 skipped. These two e2e runs predate Phase 5's fixes, so they are a
record of the branch at that point. "Gates" below is the final state.

## AC-8 on Claude Code

Run on 2026-10-30 after the Phase 5 fixes, in a `mktemp` sandbox with a throwaway `HOME` and
`ADLC_HOME`, `env -i`, offline, against a `git archive` of this branch committed to a local
git repo that served as the marketplace.

```
$ claude plugin marketplace add <clone>
$ claude plugin install adlc@adlc-toolkit
installed: <home>/.claude/plugins/cache/adlc-toolkit/adlc/5.4.0, version 5.4.0

(commit zzz-throwaway/SKILL.md to the clone)
clone has it: yes; cache has it: no

$ claude plugin marketplace update adlc-toolkit
$ claude plugin update adlc@adlc-toolkit
adlc is already at the latest version (5.4.0).
cache has it: no

(bump VERSION and every manifest to 5.4.1-ac8 in the clone, and commit)
$ claude plugin marketplace update adlc-toolkit
$ claude plugin update adlc@adlc-toolkit
Plugin "adlc" updated from 5.4.0 to 5.4.1-ac8 for scope user.
<home>/.claude/plugins/cache/adlc-toolkit/adlc/5.4.1-ac8: has it: yes
```

**Verified:** the commit does not reach the installed copy until the README's update commands
run, and the clone, which is what a mount follows, has it at once.

**The condition:** those commands move the copy only when `version` has changed. A commit with
no bump is not a thing `claude plugin update` picks up, which is why a release bumps all
three manifests (BR-5). The sandbox had no `~/.agents/skills`, so the mount half is the clone
itself.

## `install.sh` and the mounts

The sandbox case above is the healthy-machine result: zero actions. The real machine is not
in that state, so this run was dry only, and it is not a zero:

```
$ ./install.sh --dry-run
  repo root: ~/GitHub/adlc-toolkit
  ADLC_HOME: ~/.claude (default)
  ok: ~/.claude/skills already -> ~/GitHub/adlc-toolkit
  ok: ~/.claude/agents already -> ~/GitHub/adlc-toolkit/agents
  would: create skills view ~/.claude/adlc/skills-view
  would: linked view entry ~/.claude/adlc/skills-view/<skill> -> ~/GitHub/adlc-toolkit/<skill>     (17 lines)
  would: symlink ~/.agents/skills -> ~/.claude/adlc/skills-view
  would: write adlc shim ~/bin/adlc -> ~/GitHub/adlc-toolkit/tools/adlc/adlc.py (...)
Dry run: no changes made. Re-run without --dry-run to apply.
(exit 0; 20 would: lines; the doctor output after it is not reproduced)
```

None of the 20 lines comes from this REQ. This machine has no skills view and no
`~/.agents/skills`, and no line touches a manifest. `install.sh` is unchanged from
`origin/main`, and it resolves its repo root to the main clone through `--git-common-dir`, so
this run reads that clone, not this worktree. Why the view and the mount are missing here was
not investigated. `install.sh` was never run without `--dry-run`.

```
$ readlink ~/.claude/skills
~/GitHub/adlc-toolkit
$ readlink ~/.claude/agents
~/GitHub/adlc-toolkit/agents
```

Both read the same at the start and the end of this work.

One consequence: this machine has no `~/.agents/skills`, so nothing here could have shown the
coexistence BR-8 describes, even with a harness binary present.

## Node `fs.cp`, for the Gemini reason

Re-run for this record in a session scratchpad, on Node v26.7.0. A tree with `spec/SKILL.md`
and a relative symlink `skills/spec -> ../spec`, then
`fs.promises.cp(src, dst, { recursive: true })`:

```
before: readlink src/skills/spec = ../spec
after cp: readlink dst/skills/spec = <tmp>/src/spec
after cp: absolute = true , points into src = true
after cp: dst/skills/spec/SKILL.md exists = true
after rm src: dst/skills/spec/SKILL.md exists = false
```

**Verified:** Node's rewrite, and that the copy dangles once the source is gone.
**Unverified:** that a real `gemini extensions install` behaves this way. That step rests on
reading the source below.

## Docs and source read on 2026-10-30

Read in this task, not carried over from Phase 1. Reading a doc verifies what the doc says,
not what the harness does, so every claim from these stays **unverified** in the README.

| Source | What it was read for |
|---|---|
| `https://cursor.com/docs/plugins` | Local plugins: the `~/.cursor/plugins/local` path, copying, Reload Window, a symlink resolving outside that folder is skipped, the Enterprise **Allow Local Plugin Imports** setting, off by default |
| `https://cursor.com/docs/reference/plugins` | `.cursor-plugin/plugin.json`; a manifest field replaces folder discovery; default `agents/` and `hooks/hooks.json` |
| `https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference` | Legacy lookup order; `copilot plugin install` with a local path; first-found-wins with `~/.agents/skills` ahead of plugin skills |
| `https://geminicli.com/docs/extensions/reference` | Skills from `skills/`, no manifest key; `agents/`, `hooks/hooks.json`; install copies; the Antigravity notice for unpaid and Google One users, 2026-06-18 |
| `https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/cli/src/config/extension-manager.ts` | `copyExtension` calls `fs.promises.cp(source, destination, { recursive: true })`; fixed `skills`, `agents` and `hooks/hooks.json` paths |
| `https://code.claude.com/docs/en/plugins-reference` | `skills` adds to the default `skills/` scan; a root `CLAUDE.md` is not loaded and draws a validate warning |

### Where the sources differ from the spec's notes

The README follows the sources. The spec's text was left as it is.

- **The Enterprise setting** is in Cursor's own docs, by name. The task notes cited a forum
  report.
- **The Cursor install path** is on `cursor.com/docs/plugins`. The reference page the spec's
  Assumptions name does not mention it.
- **`CLAUDE_PLUGIN_ROOT` on Copilot.** The spec says neither harness sets it. Copilot's doc
  does name it, as an alias that expands in a plugin agent's frontmatter, with `PLUGIN_ROOT`
  in the environment of `stdio` MCP servers. It says nothing about a skill's shell. So the
  README says neither vendor documents it for a skill's shell. The BR-6 dependency stands
  either way, and it is unverified.
- **Updating a direct local-path install on Copilot** is not described. The doc covers
  path-sourced plugins in a local marketplace only, so "check out the new tag and install
  again" is the spec's reading, and the README says the doc is silent. Whether that install
  pins at all is Deferred.

Also found, and now in the README: `v5.4.0`, the newest tag, has no `.cursor-plugin/`,
`.github/` or `.claude-plugin/`, so the install commands need a tag cut after these manifests
landed. `git ls-tree v5.4.0` shows none of them.

## Status against the requirement

| Item | Status | Evidence |
|---|---|---|
| AC-6, Claude Code | Met as revised at Phase 4 (the `--strict` manifest failure is in the spec's `## Deferred`) | `plugin validate --strict` fails on `plugin.json` (above); `partials/tests/plugin-route.test.sh` passes, 103 cases, exit 0 under `/bin/sh` |
| AC-6, Cursor and Copilot | **Unverified**, in Deferred | No binary |
| AC-7 | Verified | `test_no_gemini_manifest_and_readme_says_why` |
| AC-8, Claude Code | Verified, with the version condition below | "AC-8 on Claude Code" |
| AC-8, Cursor and Copilot | **Not run**, in Deferred | No binary |
| AC-9 | Verified, with the real-machine note above | Zero actions on the healthy sandbox `HOME`; `readlink` unchanged; the diff below |
| AC-10 | Verified | `test_readme_alternative_section_parts`, `test_readme_keeps_claude_first_and_no_replacement_claim` |
| AC-11 | Verified | `test_docs_name_the_new_check` |
| AC-13 | Verified | `test_req658_names_the_absent_manifest` |
| BR-13 | Met by marking | Every Cursor, Copilot and Gemini claim in the README is marked unverified, citing its source and the absent probe result |

The model-turn half of REQ-669's route, re-exercised on this branch, is also still owed: the
6 skipped e2e checks need a logged-in run before a release.

## Gates

Run on the final branch, rebased on `origin/main` at d05f136, after Phase 5's fixes.

| Command | Result |
|---|---|
| `tools/lint-skills/check.sh` | exit 0; 17 `SKILL.md` files scanned; `skills-ref` skipped, not on PATH |
| `python3 -m pytest tools -q` | exit 0; 3464 passed, 6 skipped |
| `sh partials/tests/run.sh` | exit 0; 0 FAIL lines |
| `node --test 'space/tests/*.test.js'` | exit 0; 52 passed |
| `node --test 'workflows/tests/*.test.js'` | exit 0; 73 passed |
| `node space/build.mjs --check` | exit 0 |
| `sh partials/tests/plugin-route.test.sh` | exit 0; 103 cases |
| `sh tools/adlc/tests/e2e/plugin-sandbox.selftest.sh` | exit 0; 13 checks |
| `claude plugin validate . --strict` | exit 0 |

## Scope (BR-10, AC-9)

`git diff --name-only d05f136`, the merge base with `origin/main`, on the final branch. 22 files:

```
.adlc/context/architecture.md
.adlc/context/project-overview.md
.adlc/specs/REQ-658-gemini-cli-adapter/requirement.md
.adlc/specs/REQ-665-plugin-manifests-alternative-install/architecture.md
.adlc/specs/REQ-665-plugin-manifests-alternative-install/requirement.md
.adlc/specs/REQ-665-plugin-manifests-alternative-install/tasks/TASK-202-manifests-and-manifest-parity.md
.adlc/specs/REQ-665-plugin-manifests-alternative-install/tasks/TASK-203-docs-and-verification.md
.adlc/specs/REQ-665-plugin-manifests-alternative-install/verification.md
.cursor-plugin/plugin.json
.github/plugin/plugin.json
CHANGELOG.md
README.md
RELEASING.md
tools/adlc/tests/e2e/README.md
tools/adlc/tests/e2e/plugin-sandbox.sh
tools/adlc/tests/test_install_home.py
tools/lint-skills/README.md
tools/lint-skills/check.py
tools/lint-skills/tests/fixtures/plugin-manifest/ok/.cursor-plugin/plugin.json
tools/lint-skills/tests/fixtures/plugin-manifest/ok/.github/plugin/plugin.json
tools/lint-skills/tests/test_manifest_parity.py
tools/lint-skills/tests/test_plugin_manifest.py
```

A grep of that list for `SKILL.md`, `agents/`, `partials/*.sh`, `install.sh`, `.claude-plugin/`
at the root and `hooks/` matched nothing.
