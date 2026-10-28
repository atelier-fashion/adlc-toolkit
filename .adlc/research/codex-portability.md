# Making adlc-toolkit usable outside Claude Code (Codex CLI first)

Research note, 2026-10-27; corrected 2026-10-27 after the `/adversary` pass on multi-harness-plan.md (see that file's §8). Where the two disagree, the plan wins. Sources: a file-by-file inventory of the toolkit at
5.4.0 (every `*/SKILL.md`, `partials/`, `tools/`, `agents/`, `workflows/`,
`install.sh`, `templates/`) and the current Codex docs (skills, subagents,
hooks, rules, config reference, non-interactive mode — all under
learn.chatgpt.com/docs, where developers.openai.com/codex now redirects).
Not a spec — a map of the couplings and a phased plan with the open questions
that have to be answered on a real Codex install before any REQ is written.

Precedent, with a caveat: Teton Code (BUG-218/220/228/230) was a second
harness the skills accommodated, and it is **shelved as of 2026-10-27**. Two of
its fixes are genuinely portable and stay — the vendored `.adlc/` copies and the
no-agent-tool inline fallback (BUG-230). The rest were written for Teton's
provenance classifier and nothing else: the "harness-skip" prose line above
every delegating fence, the `# provenance-safe` fence grammar, and the lint
checks `harness-skip` and `provenance-safe-fence`. Those are dead weight now
and should be retired when Phase 1 touches the same skills, not carried into
the Codex port.

---

## 1. Verdict

The toolkit is a Claude Code plugin today, in three places that matter and a
long tail that doesn't:

1. **The toolkit's own state lives under `~/.claude/`** — install root, agent
   registry, ID counters, reservation ledger, machine config, venv, transcripts.
   Nothing lets you move it. This is the blocker that makes everything else
   moot, and it is the cheapest to fix because it is pure path plumbing.
2. **Every SKILL.md uses two Claude Code-only text features**: the
   `` !`cmd` `` preamble macro (ETHOS injection in all 17 skills; git state,
   templates and `gcloud` in 14) and `$ARGUMENTS` substitution (16 skills).
   Codex's SKILL.md is the Agent Skills open standard — `name`, `description`,
   body — with no macro and no argument substitution.
3. **Fan-out and autonomy are Claude Code mechanisms**: the Agent tool with
   `~/.claude/agents/*.md` definitions, `run_in_background` + completion
   notifications, the Dynamic Workflows `Workflow` tool, and the
   `.claude/settings.json` `Bash(...)` allowlist that lets `/proceed` run
   without prompting.

Everything else — the `.adlc/` layout, templates, ETHOS, lessons, the
sh partials, the `adlc` CLI, `skill-flag.sh`, telemetry — is harness-neutral
already. Codex's shell tool has the same "each fence is a fresh process"
contract, so the cross-fence rules and the sidecar carry over unchanged.

What Codex gives us that maps well: skills discovered from `.agents/skills/`
and `~/.agents/skills/` **following symlinks**; custom subagent roles as TOML
under `.codex/agents/` or `~/.codex/agents/`, on by default; lifecycle hooks
(`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`, …) in
`.codex/hooks.json`; a command allowlist as Starlark `prefix_rule`s in
`.codex/rules/*.rules`; `AGENTS.md` with `project_doc_fallback_filenames`;
`codex exec` for non-interactive runs with `--output-schema`.

---

## 2. Coupling inventory → Codex equivalent

### 2a. Install root and machine state

| today | files | Codex / portable form |
|---|---|---|
| `~/.claude/skills` → repo symlink; every partial header falls back to `~/.claude/skills/partials/X.sh` | install.sh:252; ~94 refs in partials; checks.py:155; renumber.py:163; lint `unguarded-source` | `ADLC_HOME` **defaulting to `~/.claude`** (revision 2, multi-harness-plan.md Rule A): the symlink and every path stay where they are; code reads `$ADLC_HOME` instead of the literal. Vendored copies with the old literal keep resolving because nothing moved. A different home is an opt-in, reversible migration (P7), not part of the port |
| `~/.claude/agents` → repo/agents | install.sh:253; checks.py:172 | Claude: unchanged. Codex: rendered TOML (see 2d) |
| `~/.claude/adlc/config.yml` (machine config) | install.sh:230 (ignores `ADLC_CONFIG`); forge.sh:71; _machine_config.py:194; agents_render.py:86 | `$ADLC_HOME/config.yml`; `ADLC_CONFIG` already overrides at read time — make install.sh honor it too |
| `~/.claude/delegate-venv` | install.sh:144; forge.sh:153; delegate/install.sh:30 | `$ADLC_HOME/venv` |
| `~/.claude/.global-next-{req,bug,lesson}`, `.lock.d`, `.adlc-own-reservations` | id-alloc.sh:126-141,302,610-676; checks.py:713 | stay at `$ADLC_HOME/.global-next-*`, which with the default is the same file. Not moved: a consumer whose vendored `id-alloc.sh` predates a move would rebuild the counter at the old path and take a different lock dir, splitting the same-machine serialisation; the remote reservation (`id-alloc.sh:333-339`) catches the race only while the push succeeds. Revision 2 of the plan therefore moves nothing |
| `lane-check.sh` engine path, `~/.claude/skills/tools/adlc/lane_check.py`, no `.adlc` fallback by design | lane-check.sh:26,68 | `$ADLC_HOME/toolkit/tools/adlc/lane_check.py`; keep the "installed engine only" rule, just change the root |
| `delegate-tools-path.sh` global fallback | :27 | same |
| `~/.claude/CLAUDE.md` routing block (delegation) | delegate/install.sh:263-280 | Claude: unchanged. Codex: same block appended to `~/.codex/AGENTS.md` (global instructions) |
| `~/.claude/settings.json` allow-merge for `adlc-read` etc. | delegate/install.sh:283-332 | Codex: three `prefix_rule`s in `~/.codex/rules/adlc.rules` |
| doctor `skills-symlink`, `agents-symlink`, `claude-code` checks | checks.py:160-180,783 | check per installed harness: `claude` → `~/.claude/{skills,agents}`; `codex` → `~/.agents/skills`, `~/.codex/agents/adlc-*.toml`, `~/.codex/rules/adlc.rules`. `claude-code` stays report-only; add `codex` the same way |

One decision drives all of this: the toolkit stops living *inside* a harness's
home and gets its own (`~/.adlc`), with per-harness symlinks pointing in. The
Claude side keeps `~/.claude/skills` and `~/.claude/agents` as symlinks exactly
as now, so nothing changes for current users except where counters and config
sit.

### 2b. SKILL.md text features

| feature | where | why it won't work in Codex | portable form |
|---|---|---|---|
| `` !`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo …` `` | line ~13-35 of all 17 skills; conventions.md:35-38 | Codex has no load-time macro; the backticked line is read as prose | Two options, not exclusive. (i) **Hook**: a `UserPromptSubmit` hook (both harnesses have one; Codex: `.codex/hooks.json`, Claude: `.claude/settings.json`) that detects a `$skill`/`/skill` mention and emits `.adlc/ETHOS.md` as added context. Structural, not honor-system — the LESSON-012 bar. (ii) **Instruction**: first body line "Run `cat .adlc/ETHOS.md` before anything else and treat its output as part of this skill." Honor-system but zero infrastructure. Recommend (i) as the Codex mechanism and keep `!` on Claude; `/init` installs the hook alongside the rules file |
| other `!` preamble lines (git status, template contents, `gcloud` in canary) | 14 skills | same | become a "Step 0: run these and read the output" fenced block. Cheap, and the model runs them anyway |
| `$ARGUMENTS`, `$0`-`$9` substitution; the `${1}` / `$(0)` dodges | 16 skills; lint `arg-templating`; manifest:64, wrapup:217, template-drift:136 | Codex skills get no substitution (custom prompts did, and are deprecated). The model sees the literal `$ARGUMENTS` | Replace `Target: $ARGUMENTS` with prose: "The argument is whatever the user typed after the skill name (e.g. `REQ-652`, optionally `--full`)." **Correction (adversary M3):** Claude Code substitutes `$0`–`$9` across the whole body whether or not `$ARGUMENTS` appears (LESSON-335; lint docstring). The `${1}` / `$(0)` dodges and the `arg-templating` lint stay; only the `Target: $ARGUMENTS` line becomes prose |
| `argument-hint:` frontmatter | all 17 | ignored by Codex (only `name`/`description` read); harmless | keep |
| long `description:` fields | proceed, spec, sprint, template-drift are 300-600 chars | Codex caps the skills catalog at 2% of context or 8 000 chars, shortening descriptions and **dropping skills with a warning** past the budget. 17 skills × current lengths ≈ 5-6 k chars — near the line | trim descriptions to one sentence of triggers; move the "(REQ-652)" history into the body. Also helps Claude Code |
| "Claude Code's sandbox blocks the Read tool outside cwd" rationale for vendoring | init:67; workflows/README:84 | Codex's `workspace-write` is the same shape (writes jailed, reads of `~` allowed), so vendoring stays the right design; only the prose is Claude-specific | reword to "harness sandboxes" |
| `.claude/worktrees/<slug>` as a known worktree location | wrapup:90,197; id-alloc.sh:96; emit-telemetry.sh:73 strips only `.worktrees/` | Codex has no such convention | `/sprint` already uses `<repo>/.worktrees/<id>`; make that the only documented location and strip both in telemetry |
| "harness-skip" prose line (BUG-228), `# provenance-safe` fences, "Teton" mentions (14) | spec, analyze, proceed, wrapup, bugfix; lint `harness-skip`, `provenance-safe-fence` | written for Teton's provenance classifier, which is shelved | retire in Phase 1 (delete the lines, drop the two lint checks, keep the BUG-230 inline-fallback wording) |
| Bash timeout ≥120 s for `adlc-read` | conventions.md:176 | Codex shell timeout default is **unverified** (see §4) | if shorter, the delegate-gate must pass an explicit timeout or skip, as for Teton |

### 2c. Agent dispatch

Dispatch sites and whether an inline fallback already exists:

| skill | agents | parallel | inline fallback today |
|---|---|---|---|
| proceed | task-implementer (tiers); reflector + 5 reviewers; delegate-pre-pass; lite-reviewer | yes | **yes** — "subagent mode" (proceed:16-18, 498-516; phases-lite:158) |
| analyze | 4 auditors | yes | **yes** (BUG-230, :274) |
| adversary | adversary (+2 optional) | yes | **yes** (:67) |
| sprint | pipeline-runner × N, background | yes | legacy engine only; see 2e |
| architect | feature-tracer, architecture-mapper, integration-explorer | yes | **no** in the skill — lives in `agents/pipeline-runner.md:34` |
| review | 5 reviewers | yes | **no** |
| optimize | 3 scanners | yes | **no** |
| reflect | reflector | — | **no** |
| bugfix | "Explore agents" (Claude Code's built-in type, unnamed) | — | **no** |

Codex has subagents, so the fallback is not the only path, but the wording
"use the Agent tool with `subagent_type: X` from `~/.claude/agents/`" is dead
on Codex. Portable wording, already used by proceed/analyze/adversary:

> Dispatch the `correctness-reviewer`, … agents in parallel if this harness
> can run subagents (Claude Code: Agent tool; Codex: ask for subagents by role
> name). If it cannot, or you are already a subagent, run each agent's
> checklist sequentially in your own context from its definition under
> `.adlc/agents/` (vendored) or the toolkit's `agents/`.

Two consequences: (1) `/init` should vendor `agents/*.md` into `.adlc/agents/`
the way it vendors partials, so the inline fallback can read the checklists in
any sandbox; `/template-drift` gets a fifth surface. (2) architect, review,
optimize, reflect and bugfix need the fallback paragraph added. bugfix should
name a real agent (or "explore the codebase yourself").

### 2d. Agent definitions

`agents/*.md` are Claude Code subagent files: frontmatter `name`,
`description`, `model: opus|sonnet|haiku`, `tier`, `tools: Read, Grep, Glob,
Bash` (17 of 19), `effort: xhigh` (2). Codex roles are TOML with `name`,
`description`, `developer_instructions`, optional `model`,
`model_reasoning_effort`; **no tool restriction** — subagents inherit the
parent's sandbox and skills, and `skills.config` can only disable skills.

So `adlc agents render` (REQ-516) grows a second target:

```
adlc agents render                      # Claude: stamp model: into agents/*.md (today)
adlc agents render --harness codex      # Codex: write ~/.codex/agents/adlc-<name>.toml
                                        #   (or .codex/agents/ in a project)
```

from the same source files and the same tier config, with the class→model map
gaining a Codex column (`reviewer: gpt-…`). The body becomes
`developer_instructions`. Two things are lost on Codex and must be said so:

- **Read-only reviewers are honor-system.** "Do not use the Edit or Write
  tools" (12 agents) is prose on Codex. A `PreToolUse` hook that denies
  `apply_patch`/write calls when `hook_event_name` arrives on a
  `SubagentStart`-tagged thread could restore it; needs a prototype.
- **Nesting.** `pipeline-runner` already assumes it cannot spawn (subagent
  mode). Codex's own docs do not document nesting depth; third-party reports
  say one level. Either way the runner stays flat.

### 2e. Orchestration: `/sprint` and the autonomy contract

`/sprint` has two engines and both are Claude Code-only: the `Workflow` tool
(Dynamic Workflows — no Codex analogue at all; `adlc-sprint.workflow.js` stays
Claude-only) and the legacy engine (N `pipeline-runner` agents with
`run_in_background: true`, dashboard redrawn on completion notifications).
Codex's docs say the parent "waits until all requested results are available,
then returns a consolidated response" — no background + notify loop.

The portable answer is a **third engine that doesn't live in the model at
all**: a shell orchestrator that runs one non-interactive harness process per
REQ in its own worktree —

```
codex exec --sandbox workspace-write -C <repo>/.worktrees/REQ-652 \
  --output-schema pipeline-state.schema.json -o state.json "$proceed REQ-652"
claude -p "/proceed REQ-652" --output-format json   # same shape on Claude
```

— and `/sprint` becomes the thin dashboard over `pipeline-state.json` files it
already reads. This is harness-agnostic by construction, parallel by
construction, and reuses the subagent-mode `/proceed` that both engines already
depend on. It is the largest single piece of work in the plan and the only one
that changes architecture rather than plumbing.

`/proceed`'s "runs end-to-end without prompting" contract depends on
`templates/claude-settings-template.json` (57 allow, 16 ask). The Codex
equivalent is `.codex/rules/adlc.rules` (Starlark `prefix_rule(pattern=[…],
decision="allow"|"prompt")`) plus `.codex/config.toml` with
`sandbox_mode = "workspace-write"` and `approval_policy = "on-request"`. A
generator from the JSON template keeps the two in lockstep, and the lint's
`sync-surface-parity` idea extends to it. **Open question §4.1 decides whether
this is enough**: Codex documents `<writable_root>/.git` as read-only under
`workspace-write`, which would make every `git commit`, `git worktree add` and
`git push` an approval event unless an `allow` rule lifts it.

### 2f. Knowledge capture: `/wrapup` transcript mining

`wrapup/SKILL.md:190-341` walks `~/.claude/projects/-<encoded cwd>/*.jsonl`
(Claude Code's path encoding) and pipes the file through `extract-chat`, which
reads `message.role` / `message.content` records. Codex writes
`~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl` with a different,
undocumented schema (`session_meta`, `response_item`, `event_msg`, …) and
locates by `cwd` in `session_meta`, not by directory name.

Plan: `extract-chat --format codex` (second parser, same `## Human` /
`## Assistant` output) and a discovery partial that tries both roots. The
fallback-drafting path already exists, so this is a quality item, not a
blocker — but it is where the lesson-capture loop (LESSON schema v2) gets its
evidence, so a Codex port without it is a worse product.

### 2g. `/init` and `/template-drift`

`/init` Step 8 scaffolds `.claude/settings.json`. On a Codex-first project it
should also (or instead) write `.codex/config.toml`, `.codex/rules/adlc.rules`,
`.codex/hooks.json` (ETHOS hook) and make sure an `AGENTS.md` exists (Codex
reads `AGENTS.md`, not `CLAUDE.md`; users can add `CLAUDE.md` to
`project_doc_fallback_filenames` in their own config, but `/init` can't do that
for them). `lane_check.py`'s default blocked paths already include
`.claude/**`, `**/CLAUDE.md` and `**/AGENTS.md`; add `.codex/**` and
`.agents/**`. `/template-drift` gains `agents` (2c) and `harness-config`
surfaces.

### 2h. What is already fine

- All partials, `skill-flag.sh`, telemetry, `forge.sh`, `id-alloc.sh` logic,
  `trial-merge.sh`, `conflict-bound.sh`, `lesson-check.sh` — POSIX sh, no
  harness API. Only the fallback root path changes.
- `tools/adlc` and `tools/delegate` — stdlib Python; only path constants.
- Templates, presets, ETHOS, lessons, taxonomy, `.adlc/` layout.
- The "fences don't share shell state" contract — identical on Codex.
- Skills invoking other skills (`/proceed` → `/architect`, `/validate`, …) —
  Codex has `$name` mentions and implicit selection by description.

---

## 3. Phased plan

Ordered so each phase ships on Claude Code with zero behavior change and is
testable there before anyone touches Codex.

**Phase 0 — `ADLC_HOME` (default `~/.claude`; superseded by
multi-harness-plan.md P0, which moves nothing).** Original text kept for
history: install.sh creates
`~/.adlc/{toolkit→repo, config.yml, counters/, venv/}` and keeps
`~/.claude/{skills,agents}` as symlinks; one-shot counter/ledger migration with
a lock; every `~/.claude/skills/…` fallback becomes `$ADLC_HOME/toolkit/…`
(partials, forge.sh, lane-check.sh, delegate-tools-path.sh, intake.sh,
checks.py, renumber.py, forge_config.py, lane_check.py, agents_render.py,
_machine_config.py, delegate/install.sh, two agent bodies, lint
`unguarded-source` spelling); doctor checks follow. ~1 REQ, mostly mechanical,
high test coverage already exists for the partials. Prerequisite for everything.

**Phase 1 — skill text portability.** (a) `$ARGUMENTS` → prose in 16 skills,
keep the `${1}`/`$(0)` dodges and the `arg-templating` lint (see M3 correction above). (a′) Retire the
Teton-only surface: harness-skip lines, `# provenance-safe` grammar, the 14
"Teton" mentions, lint `harness-skip` and `provenance-safe-fence`. (b) Non-ETHOS
`!` lines → "Step 0" fenced blocks. (c) Inline-fallback paragraph in architect,
review, optimize, reflect, bugfix using the BUG-230 wording; `/init` vendors
`agents/` into `.adlc/agents/`. (d) Trim descriptions. (e) Reword
Claude-specific rationale prose. ~1 REQ. Lint gains `no-arg-substitution`,
`dispatch-has-fallback`, `description-budget`.

**Phase 2 — Codex install surface.** install.sh `--harness codex` (symlink
`~/.agents/skills` → `~/.adlc/toolkit`; `adlc agents render --harness codex`;
rules + hooks + `~/.codex/AGENTS.md` routing block); `/init` writes the
`.codex/` layer and `AGENTS.md`; ETHOS `UserPromptSubmit` hook for both
harnesses (Claude keeps `!` as well); doctor per-harness checks. ~1-2 REQs.
This is the first point at which `/spec`, `/validate`, `/architect`, `/review`,
`/reflect`, `/status`, `/manifest`, `/adversary`, `/analyze`, `/proceed`
(subagent mode) are expected to work on Codex. Dogfood gate: run `/spec` →
`/proceed` on one lite REQ in the atelier-fashion test bed under Codex.

**Phase 3 — knowledge loop on Codex.** `extract-chat --format codex`, dual-root
discovery in `/wrapup`. ~1 REQ, small; blocked on §4.3.

**Phase 4 — exec engine for `/sprint`.** The shell orchestrator of §2e, with
`claude -p` and `codex exec` adapters, `pipeline-state.json` as the only
contract, and `/sprint` reduced to dispatcher + dashboard for that engine.
Dynamic Workflows and the legacy engine remain as Claude-only options. ~1 REQ,
the largest; design-heavy (ADR on process supervision, stall detection without
notifications, log capture).

Out of scope on purpose: Cursor/Gemini/OpenCode. Phase 0-1 make the toolkit
Agent-Skills-standard clean, which is what those harnesses consume; each then
needs only its own Phase 2 (install paths, agent format, allowlist format).

---

## 4. Verify on a real Codex install before writing Phase 2+ specs

1. **Git writes under `workspace-write`.** Docs: `<writable_root>/.git` is
   read-only. Does an `allow` `prefix_rule` for `git commit` run it
   un-sandboxed without a prompt under `approval_policy = "on-request"`, or
   does it still prompt? If it prompts, the autonomous `/proceed` contract
   needs `danger-full-access` (unacceptable default) or `--ask-for-approval
   never` in exec mode only. This decides whether Phase 2 delivers autonomy or
   just correctness.
2. **Shell command timeout default** in Codex and whether a skill can request
   a longer one. `adlc-read` needs ≥120 s (BUG-228).
3. **Rollout JSONL schema stability** across Codex versions, and whether
   `session_meta.cwd` is reliable for discovery (it moved between `.jsonl`
   and `.jsonl.zst` archives recently).
4. **Subagent parallelism and model choice**: confirm spawned roles run
   concurrently, inherit `.agents/skills`, and honor `model` per role.
5. **Skills catalog budget** with all 17 skills installed: is anything dropped?
6. **Hook `UserPromptSubmit` context injection**: confirm the added context
   reaches the model before the skill body, and that project-local
   `.codex/hooks.json` loads after trust without a per-hook review prompt in
   `codex exec`.
7. **Symlinked skill root**: Codex "follows the symlink target" — confirm it
   ignores non-skill directories (`tools/`, `templates/`, `partials/`) when the
   root is the whole toolkit, or point the symlink at a `skills/` subfolder
   containing only the 17 dirs (which would be a Phase 0 layout change).

---

## 5. Sources

- Skills: https://learn.chatgpt.com/docs/build-skills
- Subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents
- Hooks: https://learn.chatgpt.com/docs/hooks
- Config reference: https://learn.chatgpt.com/docs/config-file/config-reference
- Approvals & sandbox: https://learn.chatgpt.com/docs/agent-approvals-security
- Rules (`prefix_rule`): https://developers.openai.com/codex/rules
- AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Non-interactive: https://developers.openai.com/codex/noninteractive
- Custom prompts (deprecated): https://learn.chatgpt.com/docs/custom-prompts
- Toolkit inventory: this repo at 5.4.0 — `*/SKILL.md`, `partials/`,
  `tools/adlc/checks.py`, `tools/adlc/agents_render.py`, `tools/delegate/`,
  `agents/*.md`, `workflows/README.md`, `install.sh`, `.adlc/bugs/BUG-230`,
  `.adlc/context/conventions.md`.
