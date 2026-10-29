# REQ-669 Architecture — self-sufficient Claude Code plugin install

## Approach

The repo is already shaped like a plugin. A probe on Claude Code 2.1.258
(`claude plugin validate --strict`, then `claude --plugin-dir <copy> plugin details adlc`
on a `git archive` copy of `main`) loaded all 17 root-level skills from `"skills": "./"`
and all 19 agents from the default `agents/` scan, with no other change. So the manifest
is cheap. The work is making every toolkit-owned read find its file when the toolkit
lives in `~/.claude/plugins/cache/<marketplace>/adlc/<version>/` instead of behind the
`~/.claude/skills` symlink.

There is one idea, which this doc calls **ToolkitRoot**. It is one directory per running
install. It is resolved in one canonical line at the top of every fence that needs it and
exported as `ADLC_TOOLKIT_ROOT`. Everything downstream reads the variable:

- partials, which are sourced into that shell and so see it;
- shell tools exec'd from the fence, which inherit it;
- the Python tools, which derive the root from their own file and use the variable only
  as a cross-check.

```
fence ─ root line ─▶ ADLC_TOOLKIT_ROOT ─┬─ if [ -f .adlc/partials/X.sh ] … else . "$ADLC_TOOLKIT_ROOT/partials/X.sh"   (BR-5)
        (4 arms, ADR-1)                 ├─ partials:  "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/…"          (ADR-2)
                                        └─ python:    realpath(__file__) root, identity-checked                     (ADR-2)

plugin SessionStart hook ─▶ ~/.claude/adlc/plugin-root   (pointer for text Claude Code did not substitute, ADR-4)
                         ├▶ ~/.claude/adlc/config.yml    (absent-only, byte-identical to install.sh's scaffold)
                         └▶ $CLAUDE_ENV_FILE             (PATH += <root>/scripts, so `adlc doctor` runs, BR-7)
```

The symlink route never runs the hook. Its root line resolves to `$HOME/.claude/skills`
exactly as the literal does today (BR-3).

## Verified loader facts and what is still open

| Behavior | Status | Source |
|---|---|---|
| `"skills": "./"` exposes root `<skill>/SKILL.md` dirs | **verified**, 17/17, Claude Code 2.1.258 | `claude plugin details` on a scratch copy, 2026-10-28 |
| Default `agents/` scan exposes `agents/*.md` (no `agents` field) | **verified**, 19/19, 2.1.258 | same |
| Both manifests pass `claude plugin validate --strict` | **verified**, 2.1.258 (marketplace needs a `description`) | same |
| No committed symlinks to survive the cache copy | **verified**, 0 mode-120000 entries | `git ls-files -s` |
| `${CLAUDE_PLUGIN_ROOT}` (braced, exact) substituted in skill and agent bodies, so in fence text | documented; TASK-120 verifies | plugins manifest reference |
| Substituted inside a `!` line before it runs | undocumented; TASK-120 | — |
| Not substituted in text read through the Read tool (a subagent reading a SKILL.md raw) | expected; TASK-120 | — |
| Not set in the Bash tool environment | documented | plugins manifest reference |
| Bare `/spec` invokes a plugin skill that has a `name:` field when nothing else owns the name | documented for skills with `name`; all 17 have one; TASK-120 verifies for plugin skills | skills docs |
| Plugin agents are dispatched as `adlc:<name>` | documented for typeahead; Agent-tool and Workflow `agentType` spelling TASK-120 | subagents docs |
| A plugin SessionStart hook receives `CLAUDE_ENV_FILE` | undocumented; TASK-120 | hooks reference names it for SessionStart, plugin hook env list does not |
| claude.ai/Cowork sync rejects a top-level `bin/` | documented | plugins components, org-sync |
| Directory installs go through that sync path | unknown until a submission (REQ OQ-4) | — |
| The cache copy contains `.git` | unknown; TASK-120 | — |
| 647 files is over the directory's 512-file reviewer-hold threshold | known; it holds the submission for a human reviewer, it does not block it | pre-submission checklist |

Each "TASK-120" row becomes a recorded result with the Claude Code version, in
`verification.md` (BR-16). Where a result refutes this design, the ADR names the fallback.

## Key decisions

### ADR-1: ToolkitRoot is one canonical root line with four arms, in that order

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
```

1. **Substituted text.** Under the plugin route Claude Code rewrites the exact token
   `${CLAUDE_PLUGIN_ROOT}` in the skill or agent body to the cache path before the model
   sees it. Under the symlink route the token reaches the shell unsubstituted. The
   variable is not in the Bash tool environment, so it expands empty. Only the braced,
   unadorned form is documented as substituted, which is why the line never writes
   `${CLAUDE_PLUGIN_ROOT:-…}`.
2. **The symlink install, if present.** This arm comes before the pointer, so on a doubled
   machine a symlink-route skill still reads the clone. That keeps BR-3 exact even there,
   and the doctor reports the doubling (BR-11).
3. **The plugin pointer file** that the SessionStart hook writes (ADR-4). It covers skill
   text that Claude Code did not substitute: a subagent reading `proceed/SKILL.md` through
   the Read tool, or workflow-dispatched work. Without it, that text would fall through to
   arm 4 on a plugin-only machine.
4. **The literal default.** On a machine with neither install, the failure is the same
   loud one ASSUME-005 accepts today. `.` of a missing file is fatal under `sh` and names
   the path.

The guarded source spelling keeps REQ-610's shape. Only the fallback operand changes
(BR-5):

```sh
if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . "$ADLC_TOOLKIT_ROOT/partials/<name>.sh"; fi
```

The root line appears once per fence, before the first `$ADLC_TOOLKIT_ROOT` use. Shell
state does not cross fences, and `cross-fence-var` already polices that. The line is
POSIX. It has no `case` inside `$( )`, no `[[`, no `local` and no `set -u` hazard,
because `${CLAUDE_PLUGIN_ROOT}` without `:-` is only an error under `set -u`, and no skill
fence sets it (BR-17). `tools/lint-skills` pins it byte-exact, the way REQ-610 pinned its
spelling (LESSON-012).

The lint change is **transitional**, so the repo is never lint-red between tasks.
TASK-122 makes `unguarded-source` accept the new operand beside the REQ-610 one.
TASK-124 rewrites the corpus, then removes the old operand's acceptance, so from
then on the old form is a finding.

**Rejected:**

- *Environment only, through `CLAUDE_ENV_FILE`.* Plugin-hook access is undocumented, and
  it would make a symlink skill on a doubled machine read the plugin's files.
- *A resolver partial.* Its own source line would need a root first.
- *`${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills}`.* The default form is not documented as
  substituted. If it is not, the plugin route silently reads `~/.claude/skills`.
- *A plugin copy of each skill.* That breaks BR-4.
- *A top-level `bin/adlc root` command.* That breaks BR-20.

### ADR-2: partials read the variable with a default; Python derives its own root

A partial that needs a toolkit-owned file reads
`"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/…"`. This affects five partials:
`lane-check.sh`'s engine, `forge.sh`'s `forge_config.py` lookup,
`delegate-tools-path.sh`, `ethos-include.sh` and `intake.sh`'s template candidate. The
default keeps a partial sourced by an older SKILL.md text or a test harness on today's
behavior. This is the "default-expansion spelling" exception that BR-13's lint carries,
and it is the same exception REQ-666's `no-harness-path` names for `ADLC_HOME`.

`lane-check.sh` keeps its anti-self-certification property (LESSON-718). ToolkitRoot is
the *installed* toolkit, either the cache copy or the clone behind the symlink, never the
branch under review.

`id-recheck.sh` keeps its `BASH_SOURCE` / zsh `%x` self-location and changes only its
fallback arm.

Python tools already resolve their root from `os.path.realpath(__file__)`, which is
correct inside the cache. One new helper, `tools/adlc/toolkit_root.py`, holds that rule
with `_common.py`'s identity check (ASSUME-001, LESSON-620). It accepts a candidate root
only when `realpath(<root>/tools/adlc/toolkit_root.py)` is the running file. This
replaces the four `~/.claude/skills` fallback arms in `forge_config.py`, `lane_check.py`,
`renumber.py` and `checks.py:_partial_path`. `renumber.py`'s silent "no collision" when
the recheck partial is missing becomes a loud error.

**Machine state stays put (BR-6).** Counters, the ledger and the telemetry log already
self-initialize. The one hard dependency found is the lock `mkdir`, which needs
`~/.claude` to exist, so `id-alloc.sh` gains `mkdir -p "$HOME/.claude"` before
acquiring. Nothing is written into the plugin cache. The docs say the cache is replaced
on every version.

### ADR-3: manifests pin `version` to `VERSION`, expose skills by `"./"`, and ship no top-level `bin/`

`plugin.json` is `{ name: "adlc", version: <VERSION>, description, author, license: "MIT",
repository, skills: "./" }`, with no `agents` field. The `agents` field *replaces* the
default scan and accepts only files, so omitting it is what exposes every agent.

`marketplace.json` is `{ name: "adlc-toolkit", owner, description,
plugins: [{ name: "adlc", source: "./" }] }`.

`version` is pinned, so users move only on a release (OQ-3, BR-14).

The `plugin-manifest` lint check (BR-12) enforces:

- version equals `VERSION`;
- every `*/SKILL.md` directory is reachable through `skills`;
- either there is no `agents` field or it lists every `agents/*.md`;
- exactly one marketplace entry, whose name equals the manifest name;
- **no top-level `bin/`** (BR-20).

It parses JSON with duplicate keys rejected, because `json.loads` keeps the last of a
repeated key and the loader may not (LESSON-716).

### ADR-4: a plugin SessionStart hook does three idempotent things and never fails the session

`hooks/hooks.json` registers `sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"`. Hook
paths inside `${CLAUDE_PLUGIN_ROOT}` are what the directory checklist requires. The
script does three things:

1. **Pointer.** It validates `CLAUDE_PLUGIN_ROOT` before any write (LESSON-017). The path
   must be absolute, contain `.claude-plugin/plugin.json` naming `adlc`, and contain
   `partials/`. It then writes the path atomically (temp file, then `mv`) to
   `~/.claude/adlc/plugin-root`, but only when the content differs.
2. **Config scaffold.** It writes `~/.claude/adlc/config.yml` only when the file is
   absent, with the bytes `install.sh`'s `ensure_config` writes: `delegate: enabled:
   false`. A parity test pins the two copies byte-equal. This makes "installing the plugin
   never enables delegation" true even with a stale legacy key in the environment, the
   BUG-205 class. The cost is that a plugin-only user who relied on legacy key continuity
   gets an explicit `false`. That user never ran this toolkit before, so nothing they rely
   on changes. The doctor's delegate check already says how to opt in.
3. **PATH.** When `CLAUDE_ENV_FILE` is set, it appends
   `export PATH="$PATH:<root>/scripts"` once, guarded by a marker line. Appending matches
   the documented rule that plugin executables come after the user's own PATH, so on a
   doubled machine `~/bin/adlc` still wins. `scripts/adlc` is a POSIX shim that locates
   itself and execs `python3 <root>/tools/adlc/adlc.py`. The doctor is pure stdlib, so no
   venv is needed (LESSON-395). The executable lives under `scripts/` rather than `bin/`,
   so the plugin satisfies the claude.ai sync rule whichever way REQ OQ-4 resolves.

Every branch exits 0 and prints at most one `adlc:` line on stderr. A hook failure must not
cost the user their session.

**If TASK-120 shows plugin hooks get no `CLAUDE_ENV_FILE`**, step 3 is dropped and BR-20's
second arm applies. Skills call the CLI as `"$ADLC_TOOLKIT_ROOT/scripts/adlc"`, which
works because skills never depend on PATH for it. The README documents that path, and
`verification.md` records that the Bash-tool-PATH clause of BR-7 is unmet on the plugin
route, for a spec amendment. **If plugin hooks do not run at all**, arm 3 of ADR-1 is
dead and the pointer is not written. The plan then has to retire that arm and accept that
raw-read skill text on a plugin-only machine fails loudly, which `verification.md` names.

*Amendment (Phase 5 review, 2026-10-29): the pointer is written only for a plugin-cache
root.* The pointer is machine-global, and the last session to start wins. So step 1 now
writes it only when `CLAUDE_PLUGIN_ROOT` resolves (`cd -P`) strictly below the resolved
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/` (only an absolute `CLAUDE_CONFIG_DIR`
counts; the cache directory itself does not), and it writes the resolved path. A
`--plugin-dir` checkout or a local-path marketplace runs from a working tree. Publishing
that path would make every other session's subagents source partials and the lane-check
engine from a working tree (LESSON-718). Such a root leaves the pointer as it was (byte
for byte, with one stderr note when a pointer exists and silence when none does), and the
config and PATH steps still run. `adlc doctor`'s `plugin-route` check follows suit: for a
root outside the plugin cache it reports what the pointer holds in its PASS detail rather
than FAILing with a fix that re-running the hook could not apply. The consequence: on a machine whose only install is a
local-path marketplace, skill text Claude Code did not substitute gets no pointer from
this session and falls through to arm 4, the loud failure. That route is the maintainer's
sandbox test route (README, "Trying the plugin from a clone"). The fix is in
`scripts/session-start.sh`, with its cases in `partials/tests/session-start.test.sh`.

### ADR-5: skill-to-skill references stay bare

Every SKILL.md carries a `name:` field. The skills docs say a bare `/name` invokes such a
skill "unless another command already uses that name". On a plugin-only machine nothing
else does, so all 312 bare references (the REQ's narrower count is 267) stay runnable as
printed (BR-10). That holds provided TASK-120 confirms it for plugin skills, and it needs
no text change.

On a doubled machine a bare `/spec` reaches the personal (symlink) copy. The doctor
reports that situation (BR-11). User-facing install docs print `/adlc:<skill>` for plugin
users.

*Contingency* if TASK-120 refutes bare invocation: the references become
`/adlc:<skill>`-aware through one sentence per skill ("on the plugin install, prefix
skill names with `adlc:`"). That is a follow-up task, not a rewrite of 312 lines.

*Amendment (TASK-133, 2026-10-29): the contingency fires for the names Claude Code
owns.* TASK-120 confirmed bare invocation for a plugin skill whose name nothing else
uses: a typed bare `/rootprobe` reached `probe:rootprobe` (`verification.md` row 6).
That holds for 14 of the 17 skill names. TASK-131's audit of the Claude Code 2.1.258
binary refuted the premise for the other three (`verification.md`, "Built-in command
collision audit"). Claude Code's lookup returns the first command whose name is an
exact match, before any match on a user-facing name or alias. The Skill tool and typed
input use the same lookup.

- `init` is a built-in command. On the plugin install a bare `/init` reaches the
  built-in whatever the list order, because the built-in is the exact match. That
  broke BR-10 for 65 printed instruction lines in 24 files.
- `status` is a built-in too, but no shipped line tells anyone to run it.
- `review` is an alias of the bundled `code-review` skill. Neither candidate is an
  exact match, so the first in the list wins. The list order puts `adlc:review`
  first, but that is unverified. Eight printed lines name it.

The decision applies the contingency to these names only. A line that tells the user
or the model to run a watched name prints both spellings, on that same line:
"`/init` (`/adlc:init` on the plugin install)", and likewise for `/review` and
`/status`. That keeps one text for both routes (BR-4). A model reading the line with
only `adlc:init` in its skill list picks the namespaced one. The watched names are one
constant, `BUILTIN_COLLISION_NAMES` in `tools/lint-skills/check.py`. A new lint check,
`builtin-collision`, fails an instruction-style bare mention of a watched name on a
line without `/adlc:<name>` (LESSON-012). conventions.md, "Skill names Claude Code also
owns", states the three forms: Markdown prose, a quoted runtime string, and a `!`
preamble line. The skills are not renamed. On the symlink route the personal skill is
itself an exact match and comes before the built-in table, so the bare name still
reaches the skill there (BR-3). A rename would also break every consumer's habits and
docs. The other 14 names stay bare, as decided above. On each Claude Code upgrade,
`builtin_collision_static` re-reads the installed binary, and a new collision is added
to `BUILTIN_COLLISION_NAMES`.

### ADR-6: agents are dispatched by bare name with a stated plugin spelling and an inline fallback

Skills name agents in prose and the model maps the prose name to an Agent-tool type. Each
dispatching skill gets one canonical sentence, placed once per dispatch step. The skills
are review, reflect, architect, optimize, analyze, proceed and sprint. The sentence is kept
once, between the `<!-- dispatch-fallback-sentence -->` markers in
`.adlc/context/conventions.md`, "Agent dispatch patterns". It is not quoted here, so this
file cannot drift from the text the lint enforces.

This is REQ-666's dispatch-fallback idea in the shape BR-9 needs. A lint check,
`dispatch-fallback`, requires the sentence in every skill that dispatches an agent.

The ten `~/.claude/agents/` prose mentions become `$ADLC_TOOLKIT_ROOT/agents/`.

The workflow engine names agents in code (`agentType: 'feature-tracer'`). A new pure
helper, `agentTypeFor(name, ns)`, prefixes them. `/sprint` computes `ns` from its own
substituted text, `adlc:` under the plugin route and empty otherwise, and passes it as
`args.agentNamespace`. It has a `node:test` case in `workflows/tests/helpers.test.js`.

*Amendment (TASK-126, 2026-10-29): the shipped sentence is longer than the design's.* The
design-time sentence said only "use the form the Agent tool lists", then to run the
checklist inline when neither form is listed. TASK-120 N4 (`verification.md`) found that a
name the session does not offer does not fail: on the fork path it silently became a
`general-purpose` agent without the checklist. So the conventions.md block was lengthened
to cover N4. It says to check which form the Agent tool lists before dispatching, and not
to wait for an error. When neither form is listed, the model names the missing agent, then
runs `$ADLC_TOOLKIT_ROOT/agents/<name>.md` inline or gives its body to a general-purpose
agent as the prompt, and a review or audit agent stays read-only either way. The
`dispatch-fallback` check reads the block at run time, and it walks `/adversary` and the
`proceed/phase*.md` and `partials/*.md` companion files as well as the seven skills above.

### ADR-7: the doctor learns its route from where it is running

`doctor.py`'s `Profile` gains `route`:

- `plugin` when `realpath(__file__)` is under `~/.claude/plugins/cache/`;
- otherwise `symlink`.

Two checks are new:

- **`plugin-route`** runs first. It reports the route and the version, and on the plugin
  route it checks the pointer file and the PATH shim.
- **`doubled-install`** comes after `agents-symlink`. It fires only when both of these
  hold:
  - `~/.claude/skills` resolves to a toolkit checkout;
  - a cache copy whose `.claude-plugin/plugin.json` names `adlc` exists, cross-checked
    against `~/.claude/plugins/installed_plugins.json` when that file is present (it is
    absent on the maintainer's machine today).

  It names which copy each spelling of a sample skill reaches: bare `/spec` reaches the
  personal copy, `/adlc:spec` the plugin. It prints one fix per way out:
  `claude plugin uninstall adlc@adlc-toolkit`, or removing the two symlinks.

`skills-symlink`, `agents-symlink`, `toolkit-clean` and `path-shims` become
`applies_to: symlink`, so a plugin-only machine SKIPs them with a notice instead of
FAILing (REQ AC-1). Every case has a must-not-fire test on the other two machine shapes
(LESSON-440). All of it stays stdlib.

*Amendment (TASK-128 and the Phase 5 review, 2026-10-29): the route rule is wider than the
cache test.* A local-path marketplace runs the plugin from its source directory, not the
cache (`verification.md` row 12, N3), so the rule above would call that install
`symlink`. `route` is `plugin` when the running root is inside the plugin cache, **or**
is a root the install record names for `adlc@*`. For a plugin from a `directory`
marketplace that root is the marketplace's source directory, read from
`known_marketplaces.json`. Since the Phase 5 review:

- a contributor clone that is both the symlink target and a recorded local-path plugin
  root stays `symlink`, and `doubled-install` still reports the doubling;
- the Claude config directory is an absolute `CLAUDE_CONFIG_DIR` when one is set, else
  `~/.claude`. That covers the plugin cache, `installed_plugins.json` and
  `known_marketplaces.json`;
- the cache copies an uninstall leaves behind read as absent. A well-formed record with no
  adlc entry is `absent`, the leftovers are named as leftovers, not as a conflict, and a
  copy carrying `.orphaned_at` is skipped;
- an install key that is not `adlc@<marketplace>` in kebab-case makes the record
  `unknown`. A route detection that fails makes `plugin-route` FAIL and say so, and then
  no fix prints `install.sh`.

### ADR-8: `/init` and `/template-drift` take ToolkitRoot as canonical, and the plugin version as the named baseline

The `~/.claude/skills` literals in `/init` become `$ADLC_TOOLKIT_ROOT`: the preflight
guard, the seven copy commands and the template guards. `/template-drift` drops its one
toolkit-reaching `!` line. Whether substitution precedes `!` execution is unverified, and
the substitute is a fence that does the same listing.

Step 0a branches on route:

- **symlink:** today's BUG-204 checks are unchanged (branch, behind, dirty, downgrade to
  `unverified-baseline`).
- **plugin:** the baseline is named `adlc plugin <version>` from the cache copy's
  `plugin.json`. A released, pinned copy has no branch to be wrong about. If `plugin.json`
  is unreadable, the run downgrades to `unverified-baseline`. It never quietly substitutes
  another baseline (BUG-204's rule).

*Amendment (TASK-125, 2026-10-29): Step 0a branches on what ToolkitRoot is, not on the
route.* The shipped fence tests `[ -e "$TOOLKIT/.git" ]`. A root with `.git` is a checkout
and gets BUG-204's checks, whichever route loaded it. That includes a plugin installed from
a local-path marketplace, which runs from its source checkout (`verification.md` N3). A
root without `.git` is a released copy and gets the `adlc plugin <version>` baseline. A
route test would have given a local-path plugin's working checkout a "released" baseline
it is not.

### ADR-9: the literal-path lint is one check that REQ-666 can absorb

`toolkit-path` (BR-13) scans `*/SKILL.md`, `proceed/phase*.md`, `agents/*.md`,
`partials/*.sh`, `partials/*.md`, `workflows/*.js` and non-test `tools/**` source. It
flags `~/.claude/skills`, `$HOME/.claude/skills`, `${HOME}/.claude/skills`,
`${HOME:-}/.claude/skills` and `~/.claude/agents` (all spellings the explorers found).
Exceptions:

- the canonical root line;
- the ADR-2 default-expansion spelling;
- `install.sh` and `tools/adlc/checks.py`, which inspect the symlink route on purpose;
- the lint's own rule table;
- comment lines;
- `tests/` and `fixtures/` trees.

REQ-666's `no-harness-path` is a superset (it adds the other harness homes). When it
lands, it absorbs this check and its exception list in one change (BR-18).

*Amendment (Phase 5 review, 2026-10-29): a wider surface, more spellings, a narrower
comment exception.* The surface also covers `presets/*` and `templates/*`, which ship in
the plugin and are what a user copies from. In those two directories a `#` line is the
user's instruction (the preset header's `cp …/presets/<x>.yml .adlc/config.yml`), so the
comment exception does not apply there (`TOOLKIT_PATH_INSTRUCTION_DIRS`). The preset now
copies from `"$ADLC_TOOLKIT_ROOT/presets/…"`, as the config template does. The flagged
spellings add `$HOME`, `${HOME}` and `${HOME:-}` forms of `~/.claude/agents`, and in
Python a path joined from parts (`".claude", "skills"`). The `tools/adlc/checks.py`
exception stays whole-file. A test holds every symlink spelling in that file to the four
functions that inspect the symlink install, because ADR-2 replaced the `_partial_path`
fallback in that same file.

### ADR-10: reconciliation and open questions

| Item | Decision |
|---|---|
| REQ OQ-1, narrow REQ-665 now? | No edit to an unmerged branch from here. BR-18's land-second rule stands, and REQ-665's next revision drops its Claude Code manifest. This REQ's CHANGELOG entry says so. |
| REQ OQ-2, plugin-first README? | Yes. The plugin route leads for users, and symlink is under "Contributing and live install". REQ-672 owns the later layout, and this REQ writes the minimum that satisfies BR-1 and BR-19. |
| REQ OQ-3, pin or track? | Pin to `VERSION` (ADR-3). |
| REQ OQ-4, does the directory use the `bin/`-rejecting path? | Still open, and only a submission settles it. The design ships no top-level `bin/`, so either answer works. |
| REQ-654 BR-3 (literal fence fallback unchanged) | Yields to BR-5/BR-13. Only the fallback operand changes, and `.adlc/` stays first. |
| REQ-666 `no-harness-path` and `.adlc/agents/` vendoring | Absorbs `toolkit-path` (ADR-9) and must keep ADR-1's root line, or replace it for both routes in one change. Its inline-from-`.adlc/agents/` fallback satisfies BR-9 if it keeps `$ADLC_TOOLKIT_ROOT/agents/` as the second source. |
| REQ-648 (draft) BR-10 and BR-11 | BR-10 reads `harness.{version,sha}` from "the clone `~/.claude/skills` resolves to" and records `-` when there is none. On the plugin route it should read `$ADLC_TOOLKIT_ROOT`, taking the version from `VERSION` and recording the sha as `-` when the cache copy has no `.git`. BR-11's "canonical guarded spelling" means ADR-1's spelling once this lands. Whichever of the two lands second reconciles. This REQ's CHANGELOG entry names it. |
| ASSUME-005 | Revisited as its own text asks. The canonical arm is now ToolkitRoot, and on a plugin-only machine the pointer arm is what makes it hold. TASK-130 rewrites the record. |

## Data model changes

- New machine state: `~/.claude/adlc/plugin-root`, one line holding an absolute path,
  written only by the plugin hook.
- New repo files: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `hooks/hooks.json`, `scripts/session-start.sh`, `scripts/adlc`, `RELEASING.md`.
- No change to counters, locks, the ledger, the telemetry log or config schema.

## API changes

- Skills: one canonical root line, and the guarded source operand becomes
  `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"`.
- Workflow: `args.agentNamespace` (string, default `""`).
- Doctor: new check ids `plugin-route` and `doubled-install`, plus `Profile.route`.
- Lint: new checks `plugin-manifest`, `toolkit-root-line`, `toolkit-path` and
  `dispatch-fallback`. `unguarded-source` accepts only the new operand.

## Proposed additions to `.adlc/context/architecture.md`

Add a "ToolkitRoot and the two install routes" entry to "Key cross-cutting dependencies",
covering ADR-1's arm order and ADR-4's hook. Rewrite "Symlink install" as "Install routes
(REQ-669)". Update the "Partials" section's spelling. TASK-130 carries this.

## Applicable lessons

- LESSON-012: structural lint, not prose, keeps the spelling.
- LESSON-013 and LESSON-582: shell portability.
- LESSON-017: validate before mutating, in the hook.
- LESSON-019: the lint is verified against real post-change trees, not only fixtures.
- LESSON-395: the doctor stays stdlib.
- LESSON-440: every detector gets a benign-path case.
- LESSON-441 and LESSON-465: vendored partials report `stale` after this and need a
  per-repo re-sync, which the CHANGELOG names.
- LESSON-617: `.` is guarded, never `||`-chained.
- LESSON-618: the bulk rewrite is certified by running under dash, not by grep counts.
- LESSON-620 and ASSUME-001: the root is identity-checked.
- LESSON-716: the manifest parser rejects duplicate keys.
- LESSON-717: `command grep` in branching partials.
- LESSON-718: the lane engine is the installed copy.
