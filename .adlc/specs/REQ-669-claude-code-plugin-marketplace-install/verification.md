---
req: REQ-669
verified: 2026-10-28
verifier: TASK-120
claude_code_version: 2.1.258
verdict: partial
---

# REQ-669 — plugin loader behavior record (TASK-120)

This file records the loader behaviors that architecture.md's "Verified loader facts" table
left open (BR-16). Each row gives the Claude Code version it was checked on. A row that could
not be checked says **not run** and is not counted as verified (AC-10).

## How it was probed

- **Claude Code**: `claude` 2.1.258 at `/opt/homebrew/bin/claude`, macOS, 2026-10-28.
- **Probe plugin**: `probe` (versions 0.0.1 to 0.0.4), built in the session scratchpad, not in this
  repo. It has the same layout as ADR-3: `.claude-plugin/plugin.json` with `"skills": "./"` and no
  `agents` field, and a `marketplace.json` entry with `source: "./"`. Its parts:
  - one skill, `rootprobe/SKILL.md`, with a `name:` field. Its body has `!` lines, prose lines and a
    fenced `sh` block, each carrying `${CLAUDE_PLUGIN_ROOT}`.
  - one agent, `agents/probe-agent.md`, whose body has the same token.
  - a `hooks/hooks.json` SessionStart hook. It runs `sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"`,
    the command form ADR-4 uses. The script logs its environment to a marker file and appends
    `export ADLC_PROBE_PATH=1` and `export PATH="$PATH:<root>/scripts"` to `$CLAUDE_ENV_FILE`.
  - a `scripts/probe-cli` shim.
  - `probe-notes.txt`, which holds the literal text `READ_TEXT=${CLAUDE_PLUGIN_ROOT}`.
  - three `context: fork` skills whose `agent:` fields are `probe-agent`, `probe:probe-agent` and
    `no-such-agent`. The last one is the control.
  - Both probe manifests pass `claude plugin validate --strict`.
- **Three routes**. Each one ran on its own **sandbox `HOME`** with no `~/.claude/skills`, so no
  personal copy could answer. Every `claude` run used a scrubbed environment:
  `env -i HOME=<sandbox> USER LOGNAME PATH SHELL TERM LANG TMPDIR`.
  1. **Local-path marketplace**: `claude plugin marketplace add <dir>` and then
     `claude plugin install probe@probe-mkt`. This is `source: directory`.
  2. **Git marketplace**: the same commands against `http://127.0.0.1:<port>/probe-remote.git`, a
     smart-HTTP server on loopback in front of a bare clone. This is `source: git`, the same
     clone-then-cache path a GitHub `owner/repo` source takes. `file://` was refused with
     "Invalid marketplace source format", and plain dumb HTTP was refused with "dumb http transport
     does not support shallow capabilities".
  3. **`claude --plugin-dir <dir>`**, with nothing installed.
- **Evidence without a model turn.** `claude -p "/rootprobe"` resolves the slash command, runs the
  `!` lines, substitutes the skill text and writes the expanded text to the session transcript
  *before* the first API call. So harness-side behaviors are read straight from the transcript,
  the `--output-format stream-json` init event, `--debug-file` logs and the hook's marker file,
  even though the API call itself then failed (see "What could not be run").
- In the results, `~` means the sandbox `HOME`.

## Results

Status words: **verified** means observed directly. **shell proxy** means observed in the shell
Claude Code runs `!` lines in, which is checked against the session's `Bash(...)` allow rules, but
not in a Bash tool call the model made. **partial** means part of the behavior was observed and
the rest was not run. **not run** means a model turn was needed and none could run.
**unverified** means the design assumes the behavior and no probe of it was attempted
(row 14, added by the Phase 5 review). Only **verified** rows count as verified for BR-16.

| # | Behavior | Result | Claude Code | Date | How probed | ADR confirmed / fallback triggered |
|---|---|---|---|---|---|---|
| A1 | `"skills": "./"` exposes root `<skill>/SKILL.md` dirs | **verified**, 17/17 (architecture time). The probe shows it again: "Loaded 1 skills from plugin probe custom path" | 2.1.258 | 2026-10-28 | Copied from architecture.md: `claude plugin details` on a `git archive` copy of `main`. Probe: `--debug-file` log | ADR-3 confirmed |
| A2 | Default `agents/` scan exposes `agents/*.md` when there is no `agents` field | **verified**, 19/19 (architecture time). The probe shows it again: "Loaded 1 agents from plugin probe default directory" | 2.1.258 | 2026-10-28 | Copied from architecture.md, same source. Probe: `--debug-file` log | ADR-3 confirmed |
| A3 | Both manifests pass `claude plugin validate --strict` | **verified** (architecture time). The marketplace needs a `description`. Both probe manifests also pass | 2.1.258 | 2026-10-28 | Copied from architecture.md, same source. Probe: `claude plugin validate --strict` | ADR-3 confirmed |
| A4 | No committed symlinks to survive the cache copy | **verified**, 0 mode-120000 entries (architecture time) | n/a (git) | 2026-10-28 | Copied from architecture.md: `git ls-files -s` | BR-16 symlink clause settled |
| 1 | `${CLAUDE_PLUGIN_ROOT}` substituted in fence text | **verified**. The fence reached the model as `echo "FENCE_TEXT=~/.claude/plugins/cache/probe-mkt/probe/0.0.4"`. Prose lines are substituted too. The default form `${CLAUDE_PLUGIN_ROOT:-X}` is **not** substituted and arrives as written (E1) | 2.1.258 | 2026-10-28 | Bare `/rootprobe` under `claude -p`, on the git route and the `--plugin-dir` route; expanded text read from the transcript | ADR-1 arm 1 confirmed. ADR-1's rejection of the `:-` form confirmed |
| 2 | Substituted inside a `!` line before it runs | **verified**. `` !`echo "BANG_BRACED=${CLAUDE_PLUGIN_ROOT}"` `` printed the cache root, while `` !`printenv CLAUDE_PLUGIN_ROOT \|\| echo BANG_PRINTENV_EMPTY` `` printed `BANG_PRINTENV_EMPTY`. So the text is rewritten first; the variable is not in the environment (E2) | 2.1.258 | 2026-10-28 | Same runs; `!` output read from the transcript | ADR-8's premise ("order unverified") is settled: substitution comes first. Dropping `/template-drift`'s `!` line still stands, for the reason in N2 |
| 3 | Substituted in an agent body | **not run**. The agent body is the subagent's system prompt, so it never reaches the transcript, and observing it needs a model turn | 2.1.258 | 2026-10-28 | — (see "What could not be run") | ADR-1 arm 1 for agent bodies **unconfirmed** |
| 4 | Not substituted in text read through the Read tool | **partial**. Verified: the install does not rewrite files. The cache copy of `probe-notes.txt` still reads `READ_TEXT=${CLAUDE_PLUGIN_ROOT}`, and `diff -r` of the source against the cache is clean. Not run: a Read tool call | 2.1.258 | 2026-10-28 | `diff -r` and `cat` on the cache copy. Read tool: not run | Premise of ADR-1 arm 3: on-disk half confirmed, Read-tool half **unconfirmed** |
| 5 | Not set in the Bash tool environment | **shell proxy**. `printenv CLAUDE_PLUGIN_ROOT` in a `!` line is empty on the git route and the `--plugin-dir` route (E2). Not run: a Bash tool call from the model | 2.1.258 | 2026-10-28 | `!` line in `/rootprobe`, both routes | Consistent with ADR-1 (arm 1 must come from text). Bash tool itself unconfirmed |
| 6 | Bare `/<skill>` invokes a plugin skill that has a `name:` field, on a plugin-only HOME | **verified** for a typed slash command. `claude -p "/rootprobe"` resolved to `<command-name>/probe:rootprobe</command-name>` and expanded the skill, on all three routes. The session's skill and slash-command lists name it only as `probe:rootprobe`. Not run: the model invoking a bare name through the Skill tool | 2.1.258 | 2026-10-28 | Sandbox HOME with no `~/.claude/skills`; transcript and init event | ADR-5 confirmed for typed names. Contingency **not triggered**. Skill-tool path open (see "Fallbacks triggered") |
| 7 | Agent-tool `subagent_type` spelling for a plugin agent | **partial**. Verified: the agent registry offers the agent only as `probe:probe-agent`. That is both the init `agents` list and the `agent_listing_delta` the model receives. A fork skill with `agent: probe:probe-agent` spawned `agentType: "probe:probe-agent"`. A fork skill with bare `agent: probe-agent` spawned `general-purpose`, exactly like the control `no-such-agent`: it fell back silently with no error (E3). Not run: a model-issued Agent tool call | 2.1.258 | 2026-10-28 | init event, transcript attachments, `subagents/agent-*.meta.json` of the fork runs | ADR-6 namespace value confirmed: `<plugin>:<agent>`, so `adlc:<name>`. See N4 |
| 8 | Workflow `agentType` spelling for a plugin agent | **not run**. A Workflow tool call needs a model turn. The `Workflow` tool is in the `-p` session's tool list. A probe script that tries both spellings was prepared | 2.1.258 | 2026-10-28 | — (see "What could not be run") | ADR-6 `agentTypeFor(name, ns)` **unconfirmed**. Only inference: the same registry suggests `adlc:<name>` |
| 9 | A plugin SessionStart hook runs and receives `CLAUDE_ENV_FILE` | **verified**. The hook ran at `claude -p` startup on all three routes (`hook_response` `outcome: success`, exit 0). It received `CLAUDE_ENV_FILE=~/.claude/session-env/<session-id>/sessionstart-hook-0.sh`, plus `CLAUDE_PLUGIN_ROOT` (the loaded root), `CLAUDE_PLUGIN_DATA=~/.claude/plugins/data/<plugin>-<marketplace>` (`probe-inline` for `--plugin-dir`) and `CLAUDE_PROJECT_DIR`. Stdin was JSON with `session_id`, `transcript_path` and `cwd`. `sh "${CLAUDE_PLUGIN_ROOT}/…"` in `hooks.json` resolved | 2.1.258 | 2026-10-28 | Marker file written by the hook; `--debug-file` "Session environment loaded from 1 hook file(s)" | ADR-4 confirmed. **Neither** ADR-4 fallback triggered. Only `-p` startup was probed, not interactive sessions or the `resume`/`clear`/`compact` sources |
| 10 | `export PATH=…` appended there reaches a later Bash command | **shell proxy**. After the hook's append, `` !`printenv ADLC_PROBE_PATH` `` printed `1` and `` !`probe-cli` `` printed `PROBE_CLI_OK from ~/.claude/plugins/cache/probe-mkt/probe/0.0.4/scripts`, on the git route and the `--plugin-dir` route (E2). Not run: a Bash tool call from the model | 2.1.258 | 2026-10-28 | `!` lines in `/rootprobe` | ADR-4 step 3 confirmed for Claude Code's shell. BR-7's Bash-tool PATH clause still needs a model-issued call |
| 11 | The cache copy contains `.git` | **verified: no**. On the local-path route and the git route, `cache/<marketplace>/<plugin>/<version>/` has no `.git`. The git route's marketplace clone at `~/.claude/plugins/marketplaces/<marketplace>/` does have a shallow `.git`. `installed_plugins.json` records the commit as `gitCommitSha` | 2.1.258 | 2026-10-28 | `test -e <cache>/.git`; `git rev-parse --is-shallow-repository` on the marketplace clone | ADR-10's REQ-648 row holds: the cache has no `.git`. A sha is still available from `gitCommitSha` (note for REQ-648 reconciliation) |
| 12 | Installed cache path shape | **verified**: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, here `cache/probe-mkt/probe/0.0.4/`. Contents are byte-identical to the source minus `.git`, with exec bits kept. Earlier versions stay on disk after `claude plugin update`: 0.0.1 to 0.0.4 were all present. **But**: a local-path marketplace session loads from the *source directory*, not the cache, even though a cache copy is written. `--plugin-dir` loads from the directory, writes no cache copy and reports source `probe@inline` (E4) | 2.1.258 | 2026-10-28 | `find` on the sandbox HOME; init event `plugins[].path`; hook `CLAUDE_PLUGIN_ROOT` | Matches architecture.md's `cache/<marketplace>/adlc/<version>/` for git/GitHub installs. ADR-7's route rule misses local-path installs (N3) |
| 13 | Where installs are recorded | **verified**. `~/.claude/plugins/installed_plugins.json`: `{"version": 2, "plugins": {"<plugin>@<marketplace>": [{scope, installPath, version, installedAt, lastUpdated, gitCommitSha}]}}`. Marketplaces are in `~/.claude/plugins/known_marketplaces.json` (`source.source` is `directory` or `git`, plus `installLocation`). Enablement is in `~/.claude/settings.json` (`enabledPlugins["probe@probe-mkt"]: true`, `extraKnownMarketplaces`). `--plugin-dir` writes none of these | 2.1.258 | 2026-10-28 | `cat` of each file after install and update | ADR-7's `doubled-install` cross-check against `installed_plugins.json` confirmed. Use `installPath`, not a cache glob, because several versions stay on disk |
| 14 | Symlink route: `${CLAUDE_PLUGIN_ROOT}` in a personal skill (`~/.claude/skills/<skill>/SKILL.md`) reaches its fence and its `!` lines unsubstituted, and the variable is unset in that shell, so the token expands empty | **unverified**. Rows 1, 2 and 5 probed a plugin skill only. No personal skill was probed, with or without a plugin installed beside it | — | — | Not probed. Recipe: "Unverified on the symlink route" below | ADR-1 arm 1 on the symlink route **unconfirmed**. If Claude Code substituted the token in personal skill text, arm 1 would take that value and arm 2, the symlink install, would never run |

### Evidence excerpts

- **E1** (git route, 0.0.4). Expanded skill text from the transcript:
  `PROSE_TEXT=~/.claude/plugins/cache/probe-mkt/probe/0.0.4`;
  `PROSE_DEFAULT_FORM=${CLAUDE_PLUGIN_ROOT:-UNSUBSTITUTED_DEFAULT}` (unchanged);
  fence `echo "FENCE_TEXT=~/.claude/plugins/cache/probe-mkt/probe/0.0.4"`;
  header `Base directory for this skill: ~/.claude/plugins/cache/probe-mkt/probe/0.0.4/rootprobe`.
  On `--plugin-dir` the same lines carry the plugin directory instead.
- **E2**. The `!` block as expanded (git route):
  `BANG_BRACED=~/.claude/plugins/cache/probe-mkt/probe/0.0.4` / `BANG_PRINTENV_EMPTY` / `1` /
  `PROBE_CLI_OK from ~/.claude/plugins/cache/probe-mkt/probe/0.0.4/scripts`.
- **E3**. Fork-skill subagent metadata (`subagents/agent-*.meta.json`):
  `agent: probe-agent` gave `{"agentType":"general-purpose"}`;
  `agent: probe:probe-agent` gave `{"agentType":"probe:probe-agent"}`;
  `agent: no-such-agent` gave `{"agentType":"general-purpose"}`.
- **E4**. On the local-path route, the init event reports
  `plugins: [{name: probe, path: <source dir>, source: probe@probe-mkt}]` and the hook sees
  `CLAUDE_PLUGIN_ROOT=<source dir>`. On the git route both are `~/.claude/plugins/cache/probe-mkt/probe/<version>`.

### Other findings that bear on the design

- **N1. `!` lines that use a `$VAR` are refused headless, and the whole skill is dropped.**
  `` !`echo "BANG_UNBRACED=$CLAUDE_PLUGIN_ROOT"` `` failed with "Shell command permission check
  failed for pattern … Contains simple_expansion". The skill was not expanded. The run ended with
  0 turns, an empty `result` and **exit 0**, so a headless caller sees no error. The braced
  `${CLAUDE_PLUGIN_ROOT}` passes because it has already been rewritten to a literal path. This
  matters to any `!` line run under `claude -p`, including the legacy `/sprint` runners. It
  supports keeping `!` preambles inside the BUG-218/BUG-220 grammar.
- **N2. A `!` line cannot `cat` a file under the plugin root headless.**
  `` !`cat "${CLAUDE_PLUGIN_ROOT}/probe-notes.txt"` `` was refused: "cat in '<cache>/probe-notes.txt'
  was blocked. For security, Claude Code may only concatenate files from the allowed working
  directories for this session". The plugin root is not an allowed working directory. The symlink
  route's `~/.claude/skills` is outside the project too, so this is not a plugin regression. It is
  the reason ADR-8's drop of `/template-drift`'s toolkit-reaching `!` line should stand now that the
  substitution order is known (row 2).
- **N3. ADR-7 misclassifies local-path installs.** A plugin installed from a local-path marketplace
  runs from its source directory (row 12, E4). A maintainer who runs `claude plugin marketplace add
  ./` from a clone would get `route: symlink` from a `realpath(__file__)`-under-cache rule. ADR-1's
  arm 1 still works there, because the token is substituted to the source directory. Users of the
  GitHub marketplace are not affected. TASK-128 should decide whether `plugin-route` also consults
  `installed_plugins.json` / `known_marketplaces.json`. This is a design follow-up, not a spec change.
- **N4. An agent name that does not resolve does not fail loudly, at least on the fork path.** A
  bare plugin agent name, and a name that does not exist, both became `general-purpose` with no
  error (E3). If the Agent tool and the Workflow `agentType` behave the same way (rows 7 and 8 are
  not run), then a wrong namespace from ADR-6's `agentTypeFor` would quietly run a generic agent
  without the reviewer's checklist. ADR-6's sentence keys on "the form the Agent tool lists", not
  on a dispatch error, so it still meets BR-9. TASK-126 should test that `agentNamespace` reaches
  every `agentType`, not rely on a runtime error.

## What could not be run

Rows 3 and 8, and the model-side halves of rows 4, 5, 6, 7 and 10, need a model turn. No
`claude -p` model turn could authenticate on this machine:

- Sandbox HOME with the scrubbed environment: the assistant message was "Not logged in · Please run
  /login" (`error: authentication_failed`). The debug log had "[Bootstrap] Skipped: no usable OAuth,
  WIF, or API key" and "API error (attempt 1/11): Could not resolve authentication method. Expected
  one of apiKey, authToken, credentials, config, or profile to be set. Or for one of the
  "X-Api-Key" or "Authorization" headers to be explicitly omitted".
- Sandbox HOME with the inherited desktop-app environment: the same error.
- Keychain: `security find-generic-password -s "Claude Code-credentials"` returns "The specified item
  could not be found in the keychain." for both the real and the sandbox `HOME`.
  `claude auth status` on the real `HOME` reports `"loggedIn": false`. The CLI has no stored login
  here; the desktop app's own session auth does not reach child CLI processes.
- `ANTHROPIC_API_KEY` is not set. No key was requested or written.

No model turn ran, so the spend was $0. The user's real `~/.claude` was not modified: no
marketplace or plugin was added there, and `~/.claude/plugins` has no probe entries.

**To finish these rows.** Log the CLI in (`claude /login`) or export `ANTHROPIC_API_KEY`. Then, on a
sandbox `HOME` with the probe installed from a git marketplace, run:

1. `claude -p "/rootprobe"`. Its steps run the fence, `printenv CLAUDE_PLUGIN_ROOT`,
   `printenv ADLC_PROBE_PATH`, `printenv PATH` and `probe-cli` through the Bash tool, and then Read
   `probe-notes.txt`. This settles rows 4, 5 and 10.
2. A prompt that calls the Agent tool with `subagent_type: "probe-agent"`, then with
   `"probe:probe-agent"`. The agent echoes its `AGENT_TEXT=${CLAUDE_PLUGIN_ROOT}` line. This settles
   rows 3 and 7.
3. A prompt that runs the Workflow tool on a script calling `agent(…, {agentType})` with both
   spellings. This settles row 8.

Use `--model haiku`, `--output-format stream-json --verbose`, and `--allowedTools` scoped to
`Bash(echo:*) Bash(printenv:*) Bash(probe-cli:*) Read`.

## Fallbacks triggered

**None.**

- **ADR-4, the no-`CLAUDE_ENV_FILE` fallback**: not triggered. The plugin SessionStart hook received
  `CLAUDE_ENV_FILE` (row 9), and its exports reached Claude Code's shell (row 10). Step 3 stays.
- **ADR-4, the hooks-don't-run fallback**: not triggered. The hook ran on every route (row 9), so
  ADR-1's pointer arm (arm 3) stays.
- **ADR-5, the bare-name contingency**: not triggered. A typed bare `/rootprobe` reached the plugin
  skill on a plugin-only HOME (row 6). Still open: whether the Skill tool accepts a bare name when
  the model follows a printed "run `/validate`". The listing the model sees says only
  `probe:rootprobe`. If the Skill tool refuses bare names, ADR-5's contingency applies. That is a
  follow-up task, and it keeps BR-10's meaning.
- **ADR-6, the namespace value**: confirmed as `adlc:` (`<plugin>:<agent>`, row 7). No fallback
  triggered. The Agent-tool and Workflow dispatch spellings are still **not run** (rows 7 and 8),
  and N4 is a risk for TASK-126.

**Spec amendments.** No result so far changes a BR's meaning, so none is needed now. These would
need one if the unrun rows go the wrong way:

- If a model-issued Bash tool call does not see the hook's PATH (row 10), BR-7's Bash-tool-PATH
  clause is unmet on the plugin route. ADR-4 says this goes to a spec amendment.
- If the Agent tool or Workflow refuses `adlc:<name>` (rows 7 and 8), BR-9 has to be revisited.

N1 to N4 are design follow-ups, not BR changes.

## End-to-end (TASK-131, offline part)

This is the offline part of TASK-131, run by its implementing agent. The model, GitHub
and submission parts are the maintainer's, and they are listed under "Pending
maintainer" below.

- **Claude Code**: 2.1.258, at `/opt/homebrew/bin/claude`. That links to the Homebrew npm
  package's `bin/claude.exe`, a Mach-O arm64 Bun executable.
- **Machine**: macOS 27.0.1 (Darwin 27.0.0), 2026-10-29. Tools: Node v26.7.0; the Xcode
  `python3` 3.9.6 first on `PATH`, with PyYAML 6.0.3 and pytest 8.4.2 as `--user`
  installs; `/bin/sh` is bash 3.2.57; zsh and dash are present.
- **Snapshot under test**: `git archive` of `fa6c25e`, the branch head before this
  commit, with `plugin.json` version 5.4.0. It was installed from a local-path marketplace
  in place of `atelier-fashion/adlc-toolkit`.
- **Command**:
  `ADLC_E2E_TMPROOT=/private/tmp/claude-501 sh tools/adlc/tests/e2e/plugin-sandbox.sh`,
  with no `--with-model` and no `--throwaway-repo`.
- **Result**: 23 checks; 16 PASS, 1 FAIL, 6 SKIPPED. Exit 1, `RESULT: FAIL (1 checks
  failed)`, from `builtin_collision_static` (below). The script also printed
  `INCOMPLETE: 4 cases skipped (wholly or in part; 6 checks did not run)`.
- **Per case**:
  - `symlink_only_regressions`: PASS (7 of 7);
  - `init_spec_status_doctor`: PARTIAL (3 pass, 3 skipped);
  - `lite_req_end_to_end_with_read_guard`: PARTIAL (3 pass, 1 skipped);
  - `test_release_update`: PARTIAL (3 pass, 1 skipped);
  - `printed_next_steps_runnable`: FAIL (1 fail, 1 skipped).
- **Model access**: none. `claude auth status` reports `"loggedIn": false`, both in the
  real `HOME` and in a sandbox `HOME`, and neither `CLAUDE_CODE_OAUTH_TOKEN` nor
  `ANTHROPIC_API_KEY` is set. No `claude -p` was started.
- **Spend and side effects**: $0. No GitHub repo was created, pushed to or deleted, and
  no `adlc doctor` ran in a directory with a git remote. The real `~/.claude` was not
  written: every install went into a sandbox `HOME` under one validated `mktemp -d`
  directory, which was removed afterwards.
- **Shells**: the script was also run under zsh, dash and bash on
  `lite_req_end_to_end_with_read_guard` and `test_release_update`, with the same
  results.
- **Plugin CLI without login**: `claude plugin marketplace add`, `install`,
  `marketplace update`, `update`, `list` and `list --json` all work on Claude Code
  2.1.258 without a login, including on a `HOME` whose `~/.claude/skills` and
  `~/.claude/agents` are mode 000. None had to be skipped.

| Case | Check | Result | Evidence |
|---|---|---|---|
| `init_spec_status_doctor` (AC-1) | `bri1_install` | **PASS** | `claude plugin marketplace add <snapshot>` and `claude plugin install adlc@adlc-toolkit` both exited 0 on a guarded, plugin-only `HOME`. `claude plugin list --json` then showed `adlc@adlc-toolkit` 5.4.0, enabled, with a cache copy at `~/.claude/plugins/cache/adlc-toolkit/adlc/5.4.0` |
| | `session_hook` | **PASS** | `scripts/session-start.sh` was run directly, with the `CLAUDE_PLUGIN_ROOT` and `CLAUDE_ENV_FILE` that row 9 says Claude Code passes. It wrote `~/.claude/adlc/plugin-root`, naming the local-path source directory (the root a session loads, row 12, E4), and `config.yml` with `enabled: false`, and it appended the `# adlc-plugin-path` line. A real SessionStart was not started, because that needs a session |
| | `doctor_plugin_route` | **PASS** | `adlc doctor`, found through the hook's PATH line, in a directory with no git remote: `verdict: OK (7 pass, 0 fail, 9 skip)`. It reported `route=plugin`, `plugin-route` PASS, `doubled-install` PASS, and the four symlink checks SKIP with the plugin-route notice. The sandbox `HOME` had only a git identity and this machine's `--user` Python packages, PyYAML among them |
| | `init_spec_status` | SKIPPED | no model access (above) |
| | `doctor_in_project` | SKIPPED | needs the project `/adlc:init` makes |
| | `guard_transcripts` | SKIPPED | no model run, so there is no transcript |
| `lite_req_end_to_end_with_read_guard` (AC-2, BR-2) | `guard_armed` | **PASS** | `~/.claude/skills` and `~/.claude/agents` are `d---------`, and `ls` of either fails with "Permission denied" |
| | `guard_root_line` | **PASS** | under the guard, the canonical root line, taken byte for byte from the installed `template-drift/SKILL.md`, set `ADLC_TOOLKIT_ROOT` to the plugin root under `sh`, `bash`, `zsh` and `dash`, with an empty stderr. It did so with `${CLAUDE_PLUGIN_ROOT}` substituted, and **raw**, where arm 2's `-d` test is false under the guard and arm 3 reads the pointer |
| | `guard_partials` | **PASS** | all 13 `partials/*.sh` sourced through the guarded spelling with exit 0 and an empty stderr. `ethos-include.sh` printed the plugin's `ETHOS.md`, and `delegate-tools-path.sh` set `DELEGATE_TOOLS=<plugin root>/tools/delegate` |
| | `lite_pipeline` | SKIPPED | no model access, and no throwaway repo was given |
| `symlink_only_regressions` (AC-3, BR-3) | `install_symlink_route` | **PASS** | the snapshot clone's own `install.sh`, on an empty sandbox `HOME`, linked `~/.claude/skills` and `~/.claude/agents` to the clone: "5 action(s) taken" |
| | `install_dry_run_zero_actions` | **PASS** | `install.sh --dry-run` on that `HOME` printed "Dry run: no changes made" with **0** `would:` lines |
| | `doctor_symlink_route` | **PASS** | with `~/bin` first on `PATH`, as install.sh's rc block puts it: `route=symlink`, `doubled-install` PASS, `verdict: OK (11 pass, 0 fail, 5 skip)`. Without `~/bin` on `PATH`, `path-shims` FAILs, which is correct: the rc file has not been sourced |
| | `suite_partials` | **PASS**, with a warning | `sh partials/tests/run.sh`, under bash, zsh, `/bin/sh` and dash: exit 0. The log still has 4 lines `FAIL: AC-6 ADLC_DISABLE_DELEGATE=1 -> gate=1 (disabled) (expected '1', got '2')` from `intake.test.sh`, one per shell, which the harness does not count (see the next list) |
| | `suite_pytest` | **PASS** | `python3 -m pytest tools -q`: 1801 passed |
| | `suite_node` | **PASS** | `node --test 'workflows/tests/*.test.js'`: 57 pass. The directory form `node --test workflows/tests/` fails on Node 26 (`✖ workflows/tests … 'test failed'`), so AC-3's wording was corrected |
| | `suite_lint` | **PASS** | `tools/lint-skills/check.sh`: exit 0, 17 SKILL.md files |
| `printed_next_steps_runnable` (BR-10, ADR-5) | `builtin_collision_static` | **FAIL** | the bare `/init` that 65 shipped lines tell the user to run is also the name of a built-in Claude Code command. See the audit below |
| | `printed_steps_typed` | SKIPPED | no model access |
| `test_release_update` (AC-8, BR-14) | `bri1_install` | **PASS** | as above, on its own guarded `HOME`, at 5.4.0 |
| | `plugin_update` | **PASS** | `VERSION` and `plugin.json` were bumped to `5.4.1-e2e` in the sandbox copy only. Then `claude plugin marketplace update adlc-toolkit` printed "Validating local marketplace … Successfully updated". `claude plugin update adlc@adlc-toolkit` printed `Plugin "adlc" updated from 5.4.0 to 5.4.1-e2e for scope user. Restart to apply changes.` After that, `claude plugin list --json` showed `5.4.1-e2e` at `cache/adlc-toolkit/adlc/5.4.1-e2e`, and the 5.4.0 copy stayed on disk |
| | `template_drift_baseline_fence` | **PASS** | `/adlc:template-drift`'s Step 0a fence, taken from the installed copy, with `${CLAUDE_PLUGIN_ROOT}` rewritten as the loader rewrites it (row 1) and run under `sh`, printed `baseline: adlc plugin 5.4.1-e2e (<cache>/5.4.1-e2e)` for the new cache copy. For the local-path source a session loads, it printed `baseline: adlc plugin 5.4.1-e2e (<source>)`. For the control, the old 5.4.0 cache copy, it printed `baseline: adlc plugin 5.4.0 (<cache>/5.4.0)` |
| | `template_drift_skill_run` | SKIPPED | no model access. The fence ran as shell, not through a session's Bash tool |

**What this settles and what it does not.**

- **AC-3 is met** on this machine. The check is a symlink-only sandbox `HOME` made by
  `install.sh`, with the four suites run in a clean clone of the snapshot.
- The first half of **AC-8** is met: `claude plugin update` installs the bumped version.
  The second half, `/adlc:template-drift` naming the baseline, is shown only for the fence
  run as shell. A session run is still needed.
- **AC-1** and **AC-2** are met only in their offline parts: the install, the hook, the
  doctor and the guard. Their model-driven halves did not run.
- The local-path marketplace runs the plugin from its source directory (row 12, N3). So
  the cache-load path a GitHub install takes is exercised here only through the cache
  copy's own fence run. `RELEASING.md` step 7 checks it against the real release.

**Harness sensitivities found on the way.** They are not REQ-669 regressions, and Phase
5 should decide whether to file them:

- `partials/tests/lesson-check.test.sh` `supersedes_reverse_lookup_is_exact` (the BOM
  fixture, LESSON-507) fails under a UTF-8 locale (`LANG=en_US.UTF-8`, the macOS
  Terminal default). It fails on `main` too, so a maintainer running the release gate
  from Terminal sees `suite_partials` fail. The cause is BSD awk's
  `sub(/^\357\273\277/,"")`, which matches bytes only in the C locale.
- `partials/tests/session-start.test.sh` `case_shim_doctor_from_cache_copy` (TASK-127)
  fails when `PYTHONDONTWRITEBYTECODE` is unset and the Xcode `python3` is first on
  `PATH`. That `python3` writes `~/Library/Caches/com.apple.python/…` under the test's
  `HOME`, which the "writes nothing under HOME" assertion counts. Claude Code's Bash tool
  sets `PYTHONDONTWRITEBYTECODE=1`, a plain terminal does not, so the gate can pass for an
  agent and fail for the maintainer.
- `partials/tests/intake.test.sh` AC-6, second half (lines 417 to 425), checks that
  `ADLC_DISABLE_DELEGATE=1` gives gate 1. With no `adlc-read` on `PATH`, the gate returns
  2 (no binary), and the check prints `FAIL`. That is what a symlink install without
  `--with-delegation` gives, which is the default. But the check runs inside `( … )`, so
  its `FAILS` increment is lost. The subshell's last command is the `pass` for the
  reason line, so the outer `|| FAILS=…` never fires. The file then prints
  `intake.test.sh: ALL PASS` and exits 0. This has been so since REQ-594 (`1522963`), and
  `main` does the same. It is a LESSON-581-shaped gap: a failure that is printed but not
  counted. The maintainer's own machine has `~/bin/adlc-read`, which hides it.
- A Python launcher in the C locale sets `LC_CTYPE` to UTF-8 in its own environment
  (PEP 538). The e2e script passes the caller's locale as shell-made copies for that
  reason. An earlier draft of it reproduced the lesson-check failure through this
  coercion.

### Built-in command collision audit (BR-10, ADR-5)

TASK-130 flagged that Claude Code has commands of its own with some of the toolkit's skill
names. On the plugin route a user, or the model, who follows a printed bare `/init` may
reach the built-in instead of `/adlc:init`. This is the static half of
`printed_next_steps_runnable` (`builtin_collision_static`). The skill prose is **not**
changed here, because the fix is a decision on ADR-5.

**Source of the built-in list.** It comes from the installed CLI, Claude Code 2.1.258. The
binary is `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`, a Bun
single-file executable. `claude --help` and `claude plugin --help` list no slash commands,
so they are not a source. Instead, the audit reads the command table compiled into the
binary. There are three shapes:

- the built-in table, as objects `{type:"prompt"|"local"|"local-jsx",name:"…",aliases:[…]}`
  (`init`, `status`, `config`, `help`, `memory`, `clear` and about 90 more);
- the bundled skills, as registrations `({name:"…",aliases:[…],…})` (`code-review`,
  `doctor`, `security-review`, `simplify`, `verify`, `loop`, `schedule` and others);
- three `source:"builtin"` prompt commands (`init`, `insights`, `statusline`).

The audit first checks that it can find at least three of four known commands (`help`,
`clear`, `compact`, `model`). Without them it reports SKIPPED, not PASS. All four were
found.

**What counts as a printed instruction.** The audit scans 99 shipped files:

- `*/SKILL.md` and `proceed/*.md`;
- `agents/*.md`;
- `partials/*.sh` and `partials/*.md`;
- `scripts/*` and `hooks/*`;
- `workflows/*.js` and `workflows/*.md`;
- `templates/*`, `presets/*` and `ETHOS.md`;
- `tools/adlc/*.py` and `tools/delegate/*`.

A line counts as an instruction when a verb comes right before the slash token. The verbs
are run, re-run, invoke, use, type, try, recommend, "proceed to", "ready for", "before"
and "note for". A line also counts when the token is followed by "first", "there too",
"to vendor", "to refresh", "to scaffold", "to set up", "if missing" or "to copy". Path
components such as `$ADLC_TOOLKIT_ROOT/init/` and `init/SKILL.md` are not slash tokens.

The skill names used in printed instructions are architect, canary, init, manifest,
proceed, reflect, review, spec, template-drift, validate and wrapup. Across all 17 skills
there are 629 slash references in these files.

**Intersection with Claude Code's command names.** Three of the 17 skill names collide:

| Name | Claude Code owner | Kind | References | Instruction lines | Files |
|---|---|---|---|---|---|
| `/init` | built-in prompt command `init`, "Initialize a new CLAUDE.md file with codebase documentation" (`source:"builtin"`) | **same name** | 95 | **65** | 24 |
| `/review` | bundled skill `code-review`, `aliases:["review"]`, "Review the current diff or a PR for bugs and cleanups" | alias | 23 | 8 | 4 |
| `/status` | built-in `local-jsx` command `status`, "Show Claude Code status including version, model, account, API connectivity, and tool statuses" | **same name** | 16 | 0 | 0 |

The other 14 skill names collide with nothing:

adversary, analyze, architect, bugfix, canary, manifest, optimize, proceed, reflect,
spec, sprint, template-drift, validate, wrapup

The task listed eight candidates to check. Five of them are Claude Code names but not
adlc skill names: `doctor` (a bundled skill with the alias `checkup`), `security-review`
(bundled), `config` (alias `settings`), `help` and `memory`. No shipped file prints
`/doctor`, `/config`, `/help`, `/memory` or `/security-review`. Skills print `adlc doctor`,
the CLI, which is not a slash command.

The `/init` instruction lines, as `file:line`:

- `adversary/SKILL.md:21`
- `agents/delegate-pre-pass.md:127,264`
- `analyze/SKILL.md:13,26,79,145`
- `architect/SKILL.md:13,17,28`
- `bugfix/SKILL.md:13,18,28`
- `canary/SKILL.md:13`
- `init/SKILL.md:13,296,318`
- `manifest/SKILL.md:17`
- `optimize/SKILL.md:13,26`
- `partials/delegate-gate.md:13,168,236`
- `partials/emit-step-telemetry.md:17`
- `presets/README.md:13`
- `presets/ios-firebase-cloudrun.yml:11`
- `proceed/SKILL.md:35,203,204,205,467,606`
- `reflect/SKILL.md:13,29`
- `review/SKILL.md:15,31`
- `spec/SKILL.md:13,18,19,35,140,406`
- `sprint/SKILL.md:13,29,30,31`
- `status/SKILL.md:13,29`
- `template-drift/SKILL.md:31,37,38,39,241,245,285,297,306,501`
- `tools/adlc/checks.py:564`
- `validate/SKILL.md:13,25`
- `workflows/README.md:147`
- `wrapup/SKILL.md:13,30,358`

Most of the 65 are a few repeated sentences:

- 17 are the same Ethos `!` line in each SKILL.md: "No ethos found — run /init to vendor
  .adlc/ETHOS.md".
- 10 are the "Run `/init` first" prerequisite sentence.
- 9 are the delegation-fallback stderr line: "…re-run install.sh --with-delegation, and
  /init to refresh the vendored gate".
- 7 are "run `/init` if missing" or "run `/init` first" bullets in `/proceed` and
  `/sprint`.

The other 22 are:

- the missing-template `!` lines;
- `/template-drift`'s own recommendations;
- the re-sync advice in partial docs, presets and the workflow README;
- the doctor's remediation at `tools/adlc/checks.py:564`, which `adlc doctor` prints.

The `/review` instruction lines:

- `proceed/SKILL.md:576`
- `proceed/phases-6-8-ship.md:96` (a "Do NOT re-run `/review`")
- `reflect/SKILL.md:3,67,72,73,74`
- `validate/SKILL.md:165`

**How Claude Code resolves a bare name.** This is a static reading of the 2.1.258 binary.
No typed command was run, because that needs a session and this machine has no model
access.

- The lookup is `Ns(name, commands)`, as read from the minified code. The Skill tool calls
  it over the full command list, and typed slash input goes through the same lookup. It
  returns the first command whose `name` equals the typed name exactly. Failing that, it
  returns the first command whose user-facing name or alias matches.
- A plugin skill with a `name:` field is named `adlc:<skill>` and has the user-facing
  name `<skill>`. That is why a bare `/rootprobe` reached `probe:rootprobe` in TASK-120
  row 6.
- Bare `/init` and `/status` therefore reach the **built-ins** on a plugin-only `HOME`,
  whatever the list order, because the built-ins are the exact-name matches. A user who
  types a printed `/init` gets Claude Code's CLAUDE.md generator.
- The Skill tool looks names up through the same `Ns` over the same list. So a model
  that follows "run `/init` first" with a Skill call named `init` would get the built-in
  prompt command too. For `/status` it would get a `local-jsx` command, which the Skill
  tool refuses with "Expected 'prompt' command".
- For `/review`, neither candidate is an exact match: `adlc:review` matches by
  user-facing name and `code-review` by alias. The first in the list wins. The list is
  built in this order: personal skills, workflow commands, plugin commands, plugin
  skills, bundled skills, built-in plugin skills, then the built-in table. So
  `adlc:review` should come first and win. That holds only as long as that order does,
  and it is unverified.
- On the **symlink** route, the personal skill `init` is itself an exact-name match. It
  comes before the built-in table, so bare `/init` reaches the adlc skill as it does
  today (BR-3). This too is unverified.

The check's verdict is **FAIL**. `/init` is printed as a bare instruction 65 times, and
on the plugin route that instruction does not run what it says. BR-10 is not met for
`/init` on the plugin route. `/status` has the same exact-name collision but no printed
instruction: its 16 references are descriptive. `/review` is an alias collision that
the list order should settle in the plugin's favour.

**Recommendation.** Treat this as ADR-5's contingency firing for `/init`, and decide it
before the release.

- **For `/init`**, keep one text for both routes (BR-4) by printing both spellings. For
  example, the Ethos line becomes "run `/init` (`/adlc:init` on the plugin install)".
  Most of the 65 lines are the four repeated sentences above, so this is mechanical
  work. A lint check, in the spirit of `toolkit-root-line`, should fail a bare
  instruction-style `/init` that lacks the plugin spelling (LESSON-012), so the fix
  cannot regress.
- **Do not rename the skill.** That would break every symlink-route user's `/init`.
- **For `/status`**, nothing is printed. Its README and skill-table entries already tell
  plugin users to type `/adlc:status`. Add it to the lint's watched names, so a future
  "run `/status`" is caught.
- **For `/review`**, run the `printed_steps_typed` check with model access before
  deciding. If a typed bare `/review` reaches `code-review`, give it the same two-spelling
  treatment as `/init`.
- Re-run `builtin_collision_static` on each Claude Code upgrade. A new built-in name is a
  new collision. The check reads the installed binary for exactly that reason.

### BR-16 cross-check against README.md (AC-10)

Each claim in README.md's "Loader behavior, and what is verified" table is listed with
the row it rests on here. Each one carries Claude Code 2.1.258 or is marked unverified,
and the README and this file agree on every row. This run adds evidence to rows 4, 11
and 12. It changes no row's status.

| README claim | Row here | Status, in both places |
|---|---|---|
| `"skills": "./"` exposes all 17 skills | A1 | verified, 2.1.258 |
| the default `agents/` scan exposes all 19 agents | A2 | verified, 2.1.258 |
| both manifests pass `validate --strict` | A3 | verified, 2.1.258 |
| cache path `cache/<marketplace>/<plugin>/<version>/`, no `.git`, earlier versions kept after an update | 11, 12 | verified, 2.1.258, for a git marketplace. The GitHub source is unverified until the first release. This run also saw `cache/adlc-toolkit/adlc/5.4.0/` kept beside `5.4.1-e2e/` after `claude plugin update`, on a local-path marketplace |
| `${CLAUDE_PLUGIN_ROOT}` substituted in prose, fence and `!` text; the `:-` form not substituted | 1, 2 | verified, 2.1.258 |
| substituted in an agent body | 3 | **unverified**: not run |
| the Read tool gets unsubstituted text | 4 | **unverified**: partial |
| `CLAUDE_PLUGIN_ROOT` not set in the Bash tool environment | 5 | **unverified**: shell proxy |
| the SessionStart hook runs and gets `CLAUDE_ENV_FILE` | 9 | verified, 2.1.258, at `claude -p` startup only |
| the hook's PATH line reaches the Bash tool | 10 | **unverified**: shell proxy |
| a typed bare `/<skill>` reaches the plugin skill when nothing else owns the name | 6 | verified, 2.1.258, for a name nothing else owns. For names Claude Code owns, the README says "not measured", which still holds for a typed command. The audit above reads the 2.1.258 binary and finds `/init` and `/status` owned outright and `/review` owned as an alias |
| plugin agents are registered as `adlc:<name>`; bare or unknown names silently become generic | 7 | verified, 2.1.258 |
| the Agent tool and Workflow `agentType` take `adlc:<name>` | 7, 8 | **unverified**: not run |
| a local-path marketplace runs from the source directory | 12, E4 | verified, 2.1.258. This run agrees: the doctor's `plugin-route` passed against the source directory |
| a directory install goes through the `bin/`-rejecting sync path | — | **unverified**: pending the submission, see below |

### Pending maintainer

- **The model and GitHub checks.** Six checks are SKIPPED:
  - `init_spec_status`, `doctor_in_project` and `guard_transcripts` (AC-1, BR-2);
  - `lite_pipeline` (AC-2), which adds its own `guard_transcripts` check when it runs;
  - `printed_steps_typed` (BR-10);
  - `template_drift_skill_run` (AC-8).

  To run them, export `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or
  `ANTHROPIC_API_KEY`, and create a throwaway repo whose name contains `e2e`. Then run:

  ```sh
  sh tools/adlc/tests/e2e/plugin-sandbox.sh --with-model --throwaway-repo OWNER/adlc-e2e-YYYYMMDD --keep
  ```

  Record the result here with the Claude Code version, and delete the repo yourself.
- **The directory install (BR-20, REQ OQ-4)**: **pending maintainer**. This needs a filed
  submission and an install from the Claude directory. Record whether `adlc` reached the
  session's `PATH` on that install, and what `adlc doctor` says there.
- **The Claude directory submission reference (BR-15, AC-9)**: **pending maintainer**.
  Per `RELEASING.md` steps 8 and 9, it is recorded here and in the release's CHANGELOG
  entry once filed.
- **The release itself (BR-14)**: **pending maintainer**. `VERSION` and
  `.claude-plugin/plugin.json` are unchanged in this commit, at 5.4.0. The test bump to
  `5.4.1-e2e` existed only in a sandbox copy.

## Built-in collision fix (TASK-133)

Resolved at commit 79ced1f, on Claude Code 2.1.258. All 73 audit lines (65 `/init`, 8 `/review`) now carry `/adlc:<name>` on the same line, in the dual spelling stated in `.adlc/context/conventions.md`. The new `builtin-collision` lint watches `init`, `status` and `review`. Re-run offline, `plugin-sandbox.sh` gives `builtin_collision_static` **PASS** (0 bare instruction lines), 0 FAIL, and exit 2, because 6 model/GitHub cases are skipped. The FAIL recorded above is the pre-fix result. The typed-step half (`printed_steps_typed`) still needs a model run, as do `/review`'s resolution order and the directory-install row.

## Phase 5 review: assumptions this record does not hold

### Unverified on the symlink route (row 14)

ADR-1's root line opens with `ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"`. On the symlink
route that arm is meant to come out empty, so the next arm picks the symlink install. Rows
1 and 2 show the token substituted in a **plugin** skill's prose, fence and `!` lines,
and row 5 shows the variable unset in a plugin skill's `!` shell. Nobody ran a
**personal** skill, so the symlink-route half is assumed, not observed.

**Probe recipe.** It needs no model turn. Like rows 1 and 2, the harness expands the skill
and writes it to the transcript before the first API call, so it runs on this machine's
logged-out CLI as those rows did. It was not run in the Phase 5 review.

1. Make a sandbox `HOME` with a personal skill at
   `<sandbox>/.claude/skills/rootprobe-personal/SKILL.md`. Give it a `name:` field and a
   body with one prose line `PROSE=[${CLAUDE_PLUGIN_ROOT}]`, one `!` line
   `` !`echo "BANG=[${CLAUDE_PLUGIN_ROOT}]"` `` and one `sh` fence
   `echo "FENCE=[${CLAUDE_PLUGIN_ROOT}]"`. Use only braced tokens, because an unbraced
   `$VAR` in a `!` line drops the skill headless (N1).
2. Run `claude -p "/rootprobe-personal" --output-format stream-json --verbose` under the
   scrubbed environment from "How it was probed", with no plugin installed. Then run it
   again with the `probe` plugin installed from the git marketplace, so a plugin is loaded
   beside the personal skill.
3. Read the expanded text from the session transcript. The row is **verified** when, in
   both runs, the prose and fence lines still read `${CLAUDE_PLUGIN_ROOT}` and the `!`
   output is `BANG=[]`. If a substituted path shows up in either run, ADR-1 arm 1 is wrong
   on the symlink route, and the root line needs a symlink test ahead of it.

### Unrecorded: `CLAUDECODE=1`

`adlc doctor`'s `plugin-route` check treats "`adlc` not on PATH" as a FAIL only inside a
Claude Code session, which it recognises by `CLAUDECODE=1` (`_IN_CLAUDE_CODE_ENV` in
`tools/adlc/checks.py`). TASK-128 says the variable was observed. This record holds no
observation of it: no row, no Claude Code version and no date. The `!` probes above
logged `CLAUDE_ENV_FILE`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` and
`CLAUDE_PROJECT_DIR` (row 9), not `CLAUDECODE`. To record it, add
`` !`printenv CLAUDECODE || echo CLAUDECODE_UNSET` `` to the probe skill and read the
transcript (no model turn needed). Then confirm it in a Bash tool call from the model,
which needs a logged-in CLI. Until then the PATH clause of `plugin-route` rests on an
unrecorded observation.

## End-to-end with a model (TASK-131, 2026-10-29)

`sh tools/adlc/tests/e2e/plugin-sandbox.sh --with-model --throwaway-repo <owner>/adlc-e2e-20261029 --keep`
on macOS, Claude Code 2.1.258, from `main` at adc2d98, with a model OAuth token and a
`GH_TOKEN` scoped to the throwaway repo alone.

**First run: 23 of 25 checks passed, `RESULT: FAIL (2 checks failed)`.**

| Case | Result | What it showed |
|---|---|---|
| `init_spec_status_doctor` | 7/7 | The two BR-1 commands install `adlc@adlc-toolkit` 5.4.0. `/adlc:init` scaffolds `.adlc/`, `/adlc:spec` writes a REQ, `/adlc:status` lists it, and `adlc doctor` reports `route=plugin` with no FAIL (AC-1). |
| `lite_req_end_to_end_with_read_guard` | 5/5 | With `~/.claude/skills` and `~/.claude/agents` mode 000, `/adlc:spec --lite` and `/adlc:proceed` take a lite REQ to a merged PR in the throwaway repo and leave a lesson. 13 partials sourced from ToolkitRoot, and no tool call in 10 transcripts names either guarded directory (AC-2, BR-2). |
| `symlink_only_regressions` | 6/7 | The symlink route installs, `./install.sh --dry-run` reports zero actions, and the partials, Node and lint suites pass. **FAIL:** one pytest case, below. |
| `printed_next_steps_runnable` | 2/2 | All 9 printed next steps, typed as printed for the plugin install, reach `/adlc:<skill>`. Typed bare: `/init` reached Claude Code's built-in `/init`, while `/review` and `/status` reached nothing. That confirms ADR-5's refutation (TASK-133) and settles the open `/review` question: a bare `/review` never reaches the bundled `code-review` skill. |
| `test_release_update` | 3/4 | After a test release (5.4.1-e2e), `claude plugin update` installs the new version and Step 0a's fence names it as the baseline (AC-8). **FAIL:** `template_drift_skill_run`, below. |

**The two failures, both real defects, both fixed:**

1. **`suite_pytest`:** `test_reservations_fail_names_server_policy_layer` failed with
   `reservation namespace not writable (auth)`. `_classify_git_failure` read a bare
   `"403" in stderr` as HTTP auth, and git's rejection echoes the probe ref
   `refs/adlc/ids/_probe/<16 random hex>`, so about one nonce in 300 turned a
   server-policy decline into `auth`. That is a product bug: the doctor mislabels it on
   any machine. Now `403` matches only as a standalone number. The forced-nonce test
   `test_reservations_server_policy_with_403_in_the_probe_nonce` failed before the fix
   and passes after.
2. **`template_drift_skill_run`:** the model reported the right baseline, but it read
   `plugin.json` with its own `cat` instead of running Step 0a's fence. That skips the
   fence's manifest checks (LESSON-716), which are what turn a missing or malformed
   manifest into `unverified-baseline`. Step 0a now says to run the fence as written
   before any other read of ToolkitRoot, and that its printed line is the header's only
   baseline source.

**Re-run of the two cases on the fixed tree** (`--ref` of the working-tree snapshot,
`--case test_release_update --case symlink_only_regressions`): `symlink_only_regressions`
7/7, `test_release_update` 4/4, `RESULT: PASS`. `template_drift_skill_run` now shows a
Bash tool result printing `baseline: adlc plugin 5.4.1-e2e`.

**Harness fix found on the way:** Xcode git's `osxkeychain` credential helper raised a
modal "Keychain Not Found" dialog after every push under the sandbox HOME, stalling the
run. Fixed in PR #200 (2811f13): each sandbox HOME's `.gitconfig` resets
`credential.helper`.

