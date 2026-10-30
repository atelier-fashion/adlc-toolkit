# REQ-657 — Architecture: harness adapter framework (`claude` adapter only)

Exploration ran inline (pipeline-runner subagent mode; `.adlc/agents/` is absent in
this repo, which `/init` (`/adlc:init` on the plugin install) vendors, so the
`feature-tracer`, `architecture-mapper` and `integration-explorer` checklists were
read from `$ADLC_TOOLKIT_ROOT/agents/`). Precedents followed: `harness.py`'s detect
table (REQ-654), `agents_render.py`'s shared render/drift path (REQ-516),
`checks.py`'s data-built `harness:<name>` checks (REQ-654), `lane_check.py`'s
`DEFAULT_BLOCKED_PATHS` tuple (REQ-652/666), `tools/lint-skills` per-root checks
(`sync-surface-parity`, `agent-model-drift`).

## Approach

The framework is data plus one code path. A harness is a YAML file under
`harness/`; three canonical sources (`agents/*.md`, `templates/permissions.yml`,
`templates/hooks.yml`) are rendered through it by format renderers registered by
name. Nothing in `tools/adlc` branches on a harness name (AC-15 grep).

```
templates/permissions.yml ─┐
templates/hooks.yml ───────┤                       ┌─ claude-settings-json ─► .claude/settings.json (project)
agents/*.md ───────────────┼─► harness_render ─────┤─ claude-agent-md ─────► <user agents dir> (copy harnesses)
templates/instructions/ ───┘        ▲              ├─ agents-md / claude-md-import ─► AGENTS.md, CLAUDE.md
                                    │              └─ exec scope ─► structured entries (REQ-659)
harness/<name>.yml ─► harness_adapter.load() (schema, fail loud)
```

### Modules (all stdlib, LESSON-395)

| Module | Holds |
|---|---|
| `tools/adlc/harness_yaml.py` | The YAML subset parser (ADR-1). |
| `tools/adlc/harness_adapter.py` | Adapter schema + loader (BR-1); loaders for `permissions.yml` and `hooks.yml`; `$HOME`/`$ADLC_HOME` path expansion. |
| `tools/adlc/harness_render.py` | Format registry; permissions render per scope (shared-base, fence, exec deny); the matcher and the fidelity engine (BR-8, BR-9); hooks render (BR-10); instructions render (BR-12); copy-agent render (BR-4); write modes `create`/`merge` (BR-11); parity `--check` (BR-13); template-posture drift. |
| `tools/adlc/harness_doctor.py` | `render-currency:<name>` and `doctor_rows` evaluation (BR-15), shared by `adlc harness doctor` and `adlc doctor --checks`. |
| `tools/adlc/harness.py` | Gains the verbs `install`, `render`, `doctor`, `drift`. |
| `tools/adlc/agents_render.py` | Gains `--harness`, `--adapter-path`, per-harness tier columns (BR-4, BR-5). |
| `tools/adlc/checks.py` | Registers one `render-currency:<name>` check per detect name. |
| `tools/lint-skills/check.py` | `allowlist-fidelity`, `render-parity`; `unguarded-source` walks `templates/hooks.yml` and the committed `claude` render; `harness-config` joins `SYNC_SURFACES`. |

### Data files

- `harness/claude.yml` — the only shipped adapter. `trust: {mechanism: user-config-entry, …}` (ASSUME-010), `subagent_start_hook: no` (Deferred).
- `harness/claude/rendered/settings.json` — the golden `claude` project render (permissions + hooks); REQ-655 BR-13 and REQ-666 BR-15 point here.
- `harness/claude/README.md` — the adapter README, carrying the declared-residuals section (BR-18).
- `templates/permissions.yml`, `templates/hooks.yml` — the canonical sources.
- `templates/instructions/AGENTS.md`, `templates/instructions/CLAUDE.md` — the instruction-file bodies (ADR-12).
- `partials/ethos-inject.sh`, `partials/session-record.sh` (stub, REQ-660 replaces it).
- `.claude/settings.json` (toolkit's own) becomes an in-tree render, byte-equal to the golden.
- `AGENTS.md`, `CLAUDE.md` at the toolkit root (BR-12 dogfood).

## Key decisions

**ADR-1 — An in-house YAML subset, not PyYAML.** The doctor and every `adlc harness`
verb load adapters on a machine without the delegate venv (LESSON-395), and
ASSUME-003 says system `python3` has no PyYAML. The subset is closed and stated in
`harness_yaml.py`'s docstring and `tools/adlc/README.md`: block mappings and
sequences at any indentation, flow sequences and flow mappings of scalars (nested
flow sequences allowed, for `git_c_spelling: [[git, -C]]`), plain / single- /
double-quoted scalars, integers, `|` literal block scalars, `#` comments. Anything
else — tabs, anchors, aliases, tags, `>` folding, multi-document markers, a key
given twice, two spellings of one key (`binary:` and `"binary":`) — is a loud error
naming the line (LESSON-716: model the reader; the reader here is this parser, so
it refuses whatever it cannot read the one way it reads it).

**ADR-2 — The loader is the only door.** `harness_adapter.load(path, ...)` validates
every field the spec's HarnessAdapter entity names and returns a frozen dict; every
verb, `adlc agents render --harness`, both lints and the doctor call it. Adapter
discovery: `harness/<name>.yml` for the five detect names only;
`--adapter-path <file>` is the only way any other file loads, and `install --all`
and `/init` do not accept it. The `binary` cross-check reads `harness.HARNESSES`
(detect's table) and is skipped for a non-detect name.

**ADR-3 — Format renderers are registered by name.** `FORMATS` maps a format name
to a renderer object; an adapter naming an unregistered format fails the loader.
Shipped: `claude-settings-json` (permissions + hooks, one JSON document),
`claude-agent-md` (agent copies), `agents-md`, `claude-md-import` (instructions).
Several surfaces may target one path (Claude's permissions and hooks both live in
`.claude/settings.json`); the renderer groups surfaces by `(scope, path)` and the
format composes one document. A new harness is a data file, golden fixtures and,
only for a new file format, one renderer here.

**ADR-4 — Permissions are rendered as structured rules first, spelled last.** Each
`(entry, command)` becomes a `Rule(entry, argv, tier, kind, spelling, exact)` at a
scope (`project`, `printed`, `user`, `exec`); the matcher and the fidelity verdicts
work on rules, and only the format renderer spells `Bash(git push:*)`. So the lint,
`--check`, the exec scope and a hand-written fixture render are judged by the same
code (LESSON-006). Granularity spelling: `prefix` and `token-prefix` keep the argv,
`subcommand` caps at two tokens (`widened`), `command-base` keeps one (`widened`).

**ADR-5 — The matcher and the shared-base rule.** `allow_matches(rule, C, granularity)`
is the spec's BR-9 table verbatim. For every deny command `D` the evaluated forms
are `D` (shape `prefix`), `git -C . D[1:]` (`git-c`, only when `D[0]` is `git`),
`NAME=1 D` (`env-prefix`) and `bash -lc '<D>'` (`shell-opener`). A routine rule
matching any form is omitted (`inexpressible`) unless `deny_under_allow[shape]` is a
valid pass for the scope (mechanism equals `deny_tier_render[scope]`, or `deny` at
`exec`; same-scope pairing; `harness_version` equal to the result file's, or `n/a`
for `grandfathered`; a `probe` record equal to the result file's `sub_results`
variant — `prefix` ← `deny-under-allow`, `git-c` ← `wrapped-allow`) and the shape
or argv is not in `never_restore`. The deny tier's own `<D> origin feature`
extension yields `residual:exact-deny` for an exact deny entry. Wrappers outside
the closed set are declared residuals and never evaluated.

**ADR-6 — "Version in use" is the result file's.** Neither the lint nor CI can
assume a harness binary. A `probe` record is valid only when its `harness_version`
equals the REQ-664 result file's `harness_version` and its `result` equals the
variant's `status`; the lint takes the result file as an explicit path (the shipped
check passes `.adlc/research/harness-probes/<name>.json`, tests pass fixtures). An
absent file or variant fails the lint for a `probe` record.

**ADR-7 — The fence.** `fence.partial-source` is the argv `[if, "[", -f,
.adlc/partials/]`. At `project` and `printed` scope it renders only when the
granularity keeps the partial path literal (`prefix`, `token-prefix`), never as a
first-token wildcard; otherwise it is omitted, reported `inexpressible`, and the
user-level remedy is printed. An adapter can withhold an expressible entry by
accepting `inexpressible` for it at that scope — that is how `claude` declares the
fence (Rule A: a committed opening-token prefix would be a new pre-approval). At
`exec` it is `capabilities.fence_broad_spelling`, `widened`. A written `user` scope
never carries it.

**ADR-8 — Scopes.** `project`: routine + deny per `deny_tier_render.project`.
`printed`: rendered at user scope under the committed-scope rules, output only.
`user` (written): deny tier only, per `deny_tier_render.user`; a surface with no
`user` path writes nothing. `exec`: routine as prefix rules plus the exec deny set
(the deny tier plus `exec.engine_deny`), deny spelled as a hard deny when
`capabilities.deny` is `yes` and the spelling matches no routine rule that stays
rendered, else `deny-unsupported`; `exec.deny_render: none` requires the result
file's `ask-tier-deny` status to be `fail`. These are the only `exec` keys this REQ
reads, because AC-17 pins them; the rest of `exec` stays opaque.

AC-17's `claude` clause meets BR-3 and BR-6 here: `claude` declares no `user` path
for permissions (its allowlist travels in the project layer, BR-3) and
`deny_tier_render: {project: confirm}` only (BR-6), so `render --harness claude
--scope user` writes nothing and prints a render with no routine entry and no
fence, every deny entry `deny-unsupported`. The deny-tier-only *write* is exercised
on a fixture adapter that declares a `user` path and `deny_tier_render.user`. This
is a spec tension, recorded rather than resolved by changing `claude`'s declared map.

**ADR-9 — Agents.** A harness whose `agents` surface is `mounted` is served by the
canonical files themselves (Claude Code's `~/.claude/agents` symlink, REQ-654 BR-6),
so `adlc agents render --harness <it>` is the REQ-516 in-place `model:` stamp, byte
for byte, and the stamp resolves through the default tier column: canonical files
are shared by every reader of the mount, so a per-harness column applies to copy
renders only (a `claude` column, present or absent, resolves identically). A
`rendered` agents surface gets copies under its user path: tools mapped and
deduplicated, body tool names rewritten, restriction per `agent_tool_restriction`,
ETHOS-first line unless `subagent_start_hook: yes`, `model:` through `tier_map`.
A copy never goes to a project path.

**ADR-10 — Hooks.** Canonical events map through `hook_events`; `session-compact`
on Claude is `SessionStart` with the `compact` matcher. A `SessionStart` group with
no matcher also fires on compaction (Claude Code 2.1.258 treats an absent or `*`
matcher as match-all), so `session-start` maps to the matcher
`startup|resume|clear` and compaction gets its own `compact` group, each holding the
hooks whose events map there. The installed binary splits a plain `a|b|c` matcher on
`|` into alternatives (checked offline in its bundle, not in a live session). `timeout_s` converts
through `hook_timeout_unit`. The hook command is a `|` block in `hooks.yml`: the
root line, a guard that exits 0 when the partial is absent at both levels, the
canonical guarded source line, and the function call — so the source spelling is
the one `unguarded-source` already enforces and no third spelling exists.
`paths.hooks.read_by` (a list of harnesses that read this render as-is; `claude`:
`[copilot, cursor]`) suppresses the `--harness <name>` and `--field` arguments an
adapter that renders its own hook file gets from `hook_payload`. The stub
`session-record` writes `.adlc/.session/<id>` (mode 600, `harness=`/`session_id=`
only) only when `.adlc/` exists, and keeps the directory self-ignored with a
`.gitignore` of `*`, so no `git status` changes before REQ-660 adds its gitignore
line. `SubagentStart` is not rendered (Deferred).

**ADR-11 — `render --check` is toolkit parity; `drift` is consumer posture.**
`adlc harness render --check` (and the `render-parity` lint, which calls the same
function) compares, byte for byte with a unified diff, every adapter's goldens under
`harness/<name>/rendered/` and the in-tree renders (canonical agents' `model:`
lines; the toolkit's own `.claude/settings.json`). `/template-drift`'s
`harness-config` step calls `adlc harness drift`, which re-renders the caller's
project layer and classifies each file with template posture (`synced`, `stale`,
`customized`, `missing`) by set comparison, naming every missing deny-tier rule
and every missing hook explicitly. A fourth verb beyond BR-2's three, read-only.

**ADR-12 — Instruction files.** The bodies live in `templates/instructions/`, a
subdirectory, so `/init`'s `templates/*.md` copy does not vendor them as
templates. The `instructions` surface writes `AGENTS.md` (create mode) and the
adapter's own file: for `claude`, `CLAUDE.md` with `@AGENTS.md` plus the
Claude-specific lines when absent, otherwise exactly one `@AGENTS.md` line
prepended when absent and nothing else changed. The CLI never removes a line;
`/init` shows the reduction and applies it only on the operator's approval.

**ADR-13 — Write semantics.** Atomic temp + rename; idempotent (an unchanged
render reports `unchanged` and writes nothing); `--dry-run` prints `would-write`.
`create` preserves an existing file unless `--force`. `merge` (JSON only) adds or
refreshes `owned_keys`, unions list-valued owned keys recursively, preserves every
other key. Rendered files end in a newline and use 2-space JSON indentation.

**ADR-14 — Lane check.** `DEFAULT_BLOCKED_PATHS` gains exactly `harness/**`,
`templates/permissions.yml`, `templates/hooks.yml`, `.claude/settings*.json`.

## Affected files

New: the modules, data files and partials above; `partials/tests/hooks.test.sh`;
`tools/adlc/tests/test_harness_framework.py` (+ fixtures under
`tools/adlc/tests/fixtures/harness/`); lint tests.
Modified: `tools/adlc/{harness,agents_render,checks,lane_check}.py`,
`tools/adlc/tests/{test_lane_check,test_harness_probe_pins}.py`,
`tools/adlc/harness_probe.py` (comment), `tools/lint-skills/check.py`,
`tools/lint-skills/tests/test_skill_text_portability.py`, `partials/tests/run.sh`,
`partials/lane-check.md`, `init/SKILL.md`, `template-drift/SKILL.md` and its
`references/`, `.claude/settings.json`, docs (README, architecture, conventions,
two tool READMEs, CHANGELOG). Deleted: `templates/claude-settings-template.json`.

## Lessons applied

LESSON-395 (stdlib loader), LESSON-716 (closed grammar, duplicate keys), LESSON-718
(hook commands never loaded by `lane_check.py`; new blocked paths), LESSON-619 (the
allowlist is never cited as the gate), LESSON-397 (project root from cwd, toolkit
assets from the script), LESSON-006 (one render/check path; atomic writes),
LESSON-572 (copy-pasteable remediations), LESSON-747 (live Claude checks are a
different principal: SubagentStart and trust decided offline, recorded).
