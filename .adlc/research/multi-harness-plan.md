# Multi-harness plan: Claude Code + Copilot CLI + Codex + Gemini CLI + Cursor

Plan, 2026-10-27, **revision 2** after an `/adversary` pass (findings and the
changes they forced are listed in §8). Builds on `codex-portability.md` (the
toolkit-side coupling inventory, still the reference for file:line cites) and
on a docs-verified survey of the four target harnesses as of this date. Every
claim about a harness below comes from its vendor docs; the few that come from
source code or issues are marked. Open questions that must be answered on a
real install before a spec is written are collected in §6.

Scope the user asked for: GitHub Copilot, Codex, Gemini CLI, and Cursor if
possible. Verdict: **all four are possible, and Cursor is the easiest, not the
hardest.** Copilot and Cursor already read Claude Code's directories and hook
config directly. The port is therefore (a) make the toolkit's own paths
harness-independent **without moving anything**, and (b) add per-harness
renderers for the three things no standard covers: agent definitions, command
allowlists, and non-interactive invocation.

Two design rules carried through every phase, both forced by the adversary
pass:

- **Rule A — nothing that works today moves.** `~/.claude/skills` and
  `~/.claude/agents` stay symlinks to the clone; counters, config, venv and
  ledger stay where they are. New harnesses are *added* mounts, never
  relocations. Consumer repos with stale vendored partials keep working.
- **Rule B — one-way moves are never delegated to an unattended model.**
  Merge, deploy, force-push and destructive cleanup are either confirmed by a
  human in session (today) or executed by the orchestrator itself after an
  explicit approval (exec engine). A harness allowlist is a convenience for
  the routine tier, never the gate for the ask tier.

---

## 1. What every harness has in common (the floor we build on)

| Capability | Claude Code | Copilot CLI | Codex CLI | Gemini CLI | Cursor (IDE + `agent` CLI) |
|---|---|---|---|---|---|
| **SKILL.md** (Agent Skills std) | yes | yes | yes | yes | yes |
| Repo skill dirs | `.claude/skills` | `.github/skills`, `.claude/skills`, `.agents/skills` | `.agents/skills` (walks up to repo root) | `.gemini/skills`, `.agents/skills` (1 level) | `.cursor/skills`, `.agents/skills`, `.claude/skills`, `.codex/skills` (recursive) |
| User skill dirs | `~/.claude/skills` | `~/.copilot/skills`, `~/.agents/skills` (VS Code adds `~/.claude/skills`) | `~/.agents/skills` | `~/.gemini/skills`, `~/.agents/skills` | `~/.cursor/skills`, `~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills` |
| Symlinked skill dirs followed | yes | yes (issue #1021) | yes (docs) | yes (source-inferred) | yes (changelog) |
| Explicit invoke | `/name` | `/name` | `$name` | **automatic only**, with a y/n consent prompt | `/name`, `@name` |
| `$ARGUMENTS` / `$N` substitution | yes, `$0`–`$9` substituted unconditionally across the body (LESSON-335) | no | no | no | no |
| Load-time `` !`cmd` `` macro | yes | no | no | no (only in TOML commands) | no |
| Catalog budget | — | undocumented | 2 % of context / 8 000 chars, drops skills past it | undocumented | warns past spec limits |
| **Subagents** | Agent tool, `agents/*.md` | `.github/agents/*.agent.md`, `~/.copilot/agents`; parallel via `/fleet`; nesting to depth 6 | TOML roles in `.codex/agents/`, `~/.codex/agents/`; parallel; nesting **undocumented** (third-party: depth 1) | `.gemini/agents/*.md`, `~/.gemini/agents/`; parallel (blog); **no nesting** | `.cursor/agents/*.md` + reads `.claude/agents`, `~/.claude/agents`, `.codex/agents`; parallel Task calls; background; 1-level nesting |
| Per-agent tool restriction | `tools:` | `tools:` (aliases) | **none** | `tools:` (own names) | `readonly: true` only |
| Per-agent model | alias | `model:` | `model` | `model` | `model` |
| **Hooks** | settings.json | `.github/hooks/*.json`, `~/.copilot/hooks/`, **also reads `.claude/settings.json`**; 14 events incl. `subagentStart` | `.codex/hooks.json` / `[hooks]`; 12 events incl. `SubagentStart` | `hooks` in `.gemini/settings.json`; 11 events, **no subagent-start** | `.cursor/hooks.json`, `~/.cursor/hooks.json`, **also reads `.claude/settings*.json`**; 18+ events incl. `subagentStart` |
| Hook can inject context | `SessionStart` (incl. `compact` matcher) | `sessionStart`, `subagentStart` `additionalContext` | `SessionStart`, `UserPromptSubmit` | `SessionStart`, `BeforeAgent` | `sessionStart` `additional_context` |
| **Project-local config needs a trusted path** | no | hooks/MCP/plugins: yes (`--trust-folder` headless) | yes (`projects.<path>.trust_level`; untrusted skips config, hooks, rules) | yes (`trustedFolders.json`; untrusted disables settings, hooks, commands, auto-accept) | yes (`--trust` headless) |
| **Command allowlist, repo-committable** | `.claude/settings.json` `Bash(git status:*)` | **no** — user file, session flags `--allow-tool 'shell(git:*)'`, or `allowed-tools:` in SKILL.md | `.codex/rules/*.rules` `prefix_rule` | `.gemini/settings.json` `tools.allowed: ["run_shell_command(git)"]` | `.cursor/cli.json` `Shell(git)`; `.cursor/permissions.json` |
| Allowlist granularity | prefix on the fence text | subcommand prefix | token prefix; control flow → whole script as one `bash -lc` | prefix; chained parts checked separately | command base |
| Sandbox default | none | OS sandbox off by default | `workspace-write`, **`.git` read-only** | prompts for every shell cmd; optional seatbelt/docker | auto-review classifier (IDE); headless full write |
| **Instruction file** | `CLAUDE.md` | `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` | `AGENTS.md` (+ user-level `project_doc_fallback_filenames`) | `GEMINI.md` (+ project-level `context.fileName`) | `AGENTS.md`, `CLAUDE.md` (always applied) |
| **Non-interactive** | `claude -p … --output-format json` | `copilot -p … -s --output-format json --allow-tool …` | `codex exec --sandbox … --output-schema …` | `gemini -p … --output-format json`; exit 0/1/42/53 | `agent -p … --output-format json` |
| Headless "ask" becomes | deny | deny | deny | deny | n/a (`--force` approves unless denied) |
| Resume a headless session | `--resume` | `--resume` | `codex exec resume` | `--resume` | `--resume` |
| **Transcripts** | `~/.claude/projects/<enc>/*.jsonl` | `~/.copilot/session-state/<id>/events.jsonl` (undocumented) | `~/.codex/sessions/Y/M/D/rollout-*.jsonl` (undocumented) | `~/.gemini/tmp/<hash>/chats/session-*.jsonl` | CC-compatible JSONL; `transcript_path` given to hooks |
| **Worktrees** | `.claude/worktrees` | `--worktree` | none | `.gemini/worktrees` (experimental) | `~/.cursor/worktrees/` |
| Status | GA | GA; SDK GA | GA | **consumer tiers moved to Antigravity CLI (Jun 2026)**; still released for API-key / Code Assist Enterprise | GA; SDK GA |

What follows from the table:

1. **`~/.agents/skills` is the universal user-level mount** for the four
   non-Claude harnesses. Claude keeps `~/.claude/skills`. One added symlink.
2. **Nothing standardises agents, allowlists or exec.** Those need a renderer
   per harness from one canonical source. Hooks and instruction files are
   either read cross-harness already or are a one-file write.
3. **Two harnesses consume Claude Code config directly.** Copilot CLI reads
   `.claude/settings.json` hooks and `CLAUDE.md`; Cursor reads `.claude/skills`,
   `.claude/agents`, `~/.claude/agents`, `.claude/settings*.json` hooks and
   `CLAUDE.md`. They are nearly free once the toolkit's paths are variable.
4. **Four of five treat a headless "ask" as a deny, and four of five load
   project config only for trusted paths.** Any unattended engine has to
   solve approvals and trust itself (§2e, §2f).

---

## 2. Design: one source, N rendered surfaces, nothing relocated

### 2a. Layout

```
adlc-toolkit/                      (authored, harness-neutral)
├── <skill>/SKILL.md               Agent Skills standard; no `!` macros except the
│                                  Claude ETHOS line; no $ARGUMENTS (see 2c)
├── agents/*.md                    canonical agent defs (today's format + tier);
│                                  `adlc agents render` still stamps model: in place
├── templates/permissions.yml      canonical allowlist, semantic (routine tier only)
├── templates/hooks.yml            canonical hook set (ethos-inject, session-record)
├── harness/<name>.yml             adapter: paths, formats, tool-name map, exec cmd,
│                                  trust mechanism, deny-capability
└── tools/adlc/harness/*.py        renderers

$ADLC_HOME   (defaults to ~/.claude — Rule A; override only on a machine that
              has no ~/.claude and wants a different home. NOT ~/.adlc by default.)
├── skills -> <clone>              (today's symlink, unchanged; Claude's mount)
├── agents -> <clone>/agents       (today's symlink, unchanged)
├── adlc/config.yml, .global-next-*, .adlc-own-reservations, delegate-venv   (unchanged)

~/.agents/skills -> <clone>        (Copilot CLI, Codex, Gemini, Cursor) — if §6.7
                                   shows a harness chokes on non-skill dirs at the
                                   root, this one symlink points at a generated
                                   ~/.claude/adlc/skills-view/ instead; nothing
                                   else changes
~/.copilot/agents/ ~/.codex/agents/ ~/.gemini/agents/ ~/.cursor/agents/   rendered,
                                   user-level only (Cursor needs none: reads ~/.claude/agents)
~/.codex/rules/adlc.rules          rendered
~/.copilot/permissions-config.json merged entry per repo (no committed form exists)
```

The only path change anywhere is that code reads `$ADLC_HOME` instead of the
literal `~/.claude`. With the default, every byte on disk is where it was, so:
stale vendored partials in consumer repos keep resolving; `lane-check.sh`'s
engine path keeps resolving; the `~/bin` shims keep their interpreter; the
reservation ledger and lock dirs are shared by old and new copies; README's
manual-install line stays correct. A later, optional, reversible
`install.sh --migrate-home ~/.adlc` is listed under P7 and is explicitly not
part of the port.

### 2b. Project layer written by `/init --harness …`

Default: whichever harness binaries `adlc harness detect` finds. Project-level
*agent* files are **not** written by default (M7): every harness reads a
user-level agents dir, Cursor reads `~/.claude/agents` directly, and committed
copies are snapshots that shadow fresh renders. `--project-agents` opts in
for the one case that needs it (Copilot cloud agent reads `.github/agents`
only).

| harness | files `/init` writes | registered as `/template-drift` surface |
|---|---|---|
| claude | `.claude/settings.json` (today) | existing |
| copilot | `.github/hooks/adlc.json`, `AGENTS.md`; prints the `--allow-tool` line for the user's shell profile | `harness-config` |
| codex | `.codex/config.toml`, `.codex/rules/adlc.rules`, `.codex/hooks.json`, `AGENTS.md` | `harness-config` |
| gemini | `.gemini/settings.json` (`hooks`, `tools.allowed`, `context.fileName: ["AGENTS.md"]`) | `harness-config` |
| cursor | `.cursor/cli.json`, `.cursor/permissions.json`; hooks via `.claude/settings.json` which Cursor reads | `harness-config` |
| all | `.adlc/agents/` vendored checklists for the inline fallback | `agents` (new surface, same mechanics as `partials`) |

`lane_check.py` default blocked paths gain `.codex/**`, `.gemini/**`,
`.cursor/**`, `.github/agents/**`, `.github/hooks/**`, `.adlc/agents/**` and
`.adlc/partials/**` so a lite PR cannot widen an allowlist or soften a vendored
checklist (M7).

**Instruction file.** `AGENTS.md` becomes the canonical project instruction
file: Codex, Copilot and Cursor read it natively, Gemini via `context.fileName`.
`CLAUDE.md` stays, reduced to its Claude-specific lines plus `@AGENTS.md`.

### 2c. Skill text

- `$ARGUMENTS` → prose ("the argument is whatever follows the skill name").
  **The `${1}` / `$(0)` dodges and the `arg-templating` lint stay** (M3):
  Claude Code substitutes `$0`–`$9` across the body whether or not
  `$ARGUMENTS` appears (LESSON-335). §6.10 tests this before anyone touches a
  dodge.
- Non-ETHOS `!` lines → a "Step 0: run and read" fenced block.
- The ETHOS `!` line **stays permanently on Claude Code**; it is the only path
  that reaches a skill invoked inside a subagent there (M6). The hook in 2d is
  additive.
- Dispatch paragraphs use one portable wording: "if this harness can run
  subagents, dispatch these agents in parallel; if it cannot, or you are a
  subagent, run each checklist inline from `.adlc/agents/<name>.md`." Added to
  architect, review, optimize, reflect, bugfix.
- Descriptions trimmed (template-drift's is 975 chars against a 1 024 cap);
  the three skills over 500 lines split into `SKILL.md` + `references/`.

### 2d. ETHOS injection, structural on every harness

| context | mechanism |
|---|---|
| any session in a project with `.adlc/ETHOS.md` | `sessionStart` hook emits the file as added context. Claude Code's `compact` matcher re-fires it after compaction. |
| subagents on Copilot, Codex, Cursor | `subagentStart` hook, same command |
| subagents on Gemini (no such event) and Claude (`!` line covers skills; plain dispatches do not) | the orchestrator prepends "Read `.adlc/ETHOS.md` first" to every dispatch prompt it builds; the agent renderer prepends the same line to every rendered agent body |
| exec engine | the orchestrator inlines ETHOS into the prompt it sends (2f) |

The hook travels in `.claude/settings.json`, which Copilot and Cursor read
as-is, and is rendered into `.codex/hooks.json` and `.gemini/settings.json`.

### 2e. Allowlists: what they can and cannot do

`templates/permissions.yml` holds the **routine tier only** (`git.read`,
`git.write`, `gh.read`, `gh.pr.create`, test runners, shell utilities). The
ask tier (`gh.merge`, `deploy`, `terraform`, `git push --force`, `rm -rf`) is
*not* an allowlist concern (Rule B); it is listed in the same file only so the
exec engine can render **deny** rules for it where the harness has a deny
syntax (Copilot `--deny-tool`, Cursor `deny`, Codex `decision="forbidden"`,
Gemini policy `deny`).

Three honest limits, recorded in the README per harness:

1. **Fences, not commands.** Every harness matches the text it is handed. A
   partial-sourcing fence starts with `if [ -f .adlc/partials/…`, so no
   per-command rule matches it on any harness, Claude included; today's users
   cover it with broad `Bash(sh:*)`-style entries in `settings.local.json`.
   The renderer emits the equivalent broad entry per harness for the routine
   tier and says so.
2. **`git -C <path>`** is how most pipeline git calls are spelled. Cursor's
   command-base match (`Shell(git)`) covers it; Gemini's prefix needs
   `run_shell_command(git -C)` alongside `run_shell_command(git)`; Codex's
   token prefix needs `["git","-C"]`. The renderer emits both spellings.
3. **Granularity collapses on Cursor and Gemini** (all-git-or-nothing). The
   renderer reports what each harness lost under a new lint
   `allowlist-fidelity` (not `sync-surface-parity`, which is a different check).

### 2f. Exec engine (`/sprint` third engine) — orchestrator-owned one-way moves

The orchestrator is a shell program, not a model. Per REQ it:

1. **Prepares a working copy.** Default is today's `<repo>/.worktrees/<id>`
   worktree. Because a linked worktree's git data lives in `<repo>/.git`,
   outside any sandbox rooted at the worktree (M5), the adapter declares one
   of: `sandbox_can_reach_common_gitdir: true` (verified per harness, §6.1b),
   or `working_copy: clone` (a per-REQ `git clone --shared`, so `.git` is
   inside the root), or `git_ops: orchestrator` (the model never runs git
   write commands; the orchestrator commits and pushes after each phase).
2. **Trusts the path** (M4): Codex writes
   `[projects."<wt>"] trust_level = "trusted"` into the user config before
   launch and removes it after; Gemini appends to `trustedFolders.json`;
   Copilot passes `--trust-folder`; Cursor passes `--trust`; Claude needs
   nothing. Trust is per-run and revoked on cleanup.
3. **Builds the prompt itself** (M9): it inlines the `proceed/SKILL.md` body,
   the phase files, `.adlc/ETHOS.md`, the REQ id, the worktree path, and the
   unattended block `/sprint` already injects today (worktree path,
   "UNATTENDED", terminal-claim contract). No skill-discovery or invocation
   syntax is on the critical path, so Gemini's automatic-only activation and
   Codex's `$name` syntax do not matter here.
4. **Launches the harness** with the routine-tier allow flags, the ask-tier
   deny flags where expressible, and **no `--yolo`/`--force`/`--allow-all`**
   (M1). The prompt's Phase 8 is replaced by "stop at the merge gate and write
   `awaiting_approval` to `pipeline-state.json`".
5. **Surfaces the gate.** `pipeline-state.json` gains
   `status: awaiting_approval`, `approval: {action, repo, pr, command}`
   alongside the existing `blocked`/`blockers`. `/sprint` shows it; the
   operator runs `/sprint approve REQ-nnn` (or `reject`).
6. **Executes the one-way move itself** on approval: `adlc_forge_pr_merge`,
   deploy, cleanup, via the same partials the interactive path uses, from
   the parent repo path. The model is never asked to merge in exec mode.
7. **Resumes** the harness session (`--resume`) only if post-merge model work
   remains (wrapup lesson drafting), with the same flags.

The prompt is delivered on stdin in every case (it is several hundred lines).
Each harness documents stdin piping; Copilot ignores stdin when `-p` is also
given, so its adapter omits `-p`. Exact flags are the adapter's business and
are verified under §6.12.

| harness | launch (illustrative; adapter owns the exact flags) |
|---|---|
| claude | `claude -p --output-format json --allowedTools … --disallowedTools …` |
| copilot | `copilot -s --output-format json --no-ask-user --trust-folder --allow-tool … --deny-tool … -C <wt>` (stdin, no `-p`) |
| codex | `codex exec --sandbox workspace-write -C <wt> --output-schema … -o …` (rules pre-rendered; trust pre-written) |
| gemini | `gemini --output-format json --allowed-tools …` (policy deny pre-rendered; **no `--yolo`**) |
| cursor | `agent -p --output-format json --workspace <wt> --trust` with `.cursor/cli.json` allow+deny (**no `--force`**; §6.3 decides whether deny holds without it) |

Dynamic Workflows and the legacy background-agent engine remain Claude-only
and unchanged.

### 2g. Agent rendering

`adlc agents render --harness <name>` (extends REQ-516) maps the canonical
file to each format with a tool-name table, writing to the harness's
**user-level** dir. On Claude it keeps doing what it does today: stamp
`model:` in place in the clone, which `~/.claude/agents` already points at
(m4).

| canonical | copilot | gemini | cursor | codex |
|---|---|---|---|---|
| `Read, Grep, Glob` | `read, search` | `read_file, grep, glob` | `readonly: true` | none; restraint prepended as the first instruction line |
| `Bash` | `execute` | `run_shell_command` | — | — |
| `model: opus` (tier) | tier map column | tier map column | tier map column | tier map column |

`render-parity --check` runs in toolkit CI; in consumer repos the committed
surfaces are covered by `/template-drift`, not by render-parity.

---

## 3. Phases

Each phase ships on Claude Code with zero behaviour change first, then is
dogfooded on the new harness in the atelier-fashion test bed by running
`/spec` → `/proceed` (lite lane) → `/wrapup`. `/wrapup` before P5 drafts from
fallback evidence, which is an accepted degradation of the gate, not a
dependency.

**P0 — `ADLC_HOME` (default `~/.claude`).** Introduce the variable; every
literal `~/.claude` in partials, tools, agents, `init/SKILL.md`,
`template-drift/SKILL.md`, `install.sh`, `tools/delegate/install.sh`, README
and the lint `unguarded-source` spelling reads it. `install.sh` adds the
`~/.agents/skills` symlink and `adlc harness detect`. Doctor gains
`consumer-sync` (walks `ADLC_REPOS_ROOT` for vendored partials older than the
toolkit's and prints the `/template-drift` command per repo). **No file moves,
no migration, no rollback needed**: rollback is `git checkout 5.4.0 &&
./install.sh`. 1 REQ, mechanical.

**P1 — Skill text portability.** §2c in full; retire the Teton-only surface
(harness-skip lines, `# provenance-safe`, 14 mentions, lint `harness-skip`
and `provenance-safe-fence`); `/init` vendors `agents/` into `.adlc/agents/`
and `/template-drift` gains the `agents` surface; `lane_check.py` blocked
paths extended. Lint gains `skills-ref validate`, `dispatch-has-fallback`,
`description-budget`, `no-harness-path`. 1 REQ. Gated on §6.10.

**P2 — Harness adapter framework + Copilot + Cursor.** `harness/<name>.yml`
schema and loader (paths, formats, tool map, exec command, trust mechanism,
deny capability); `adlc harness install|render|doctor`; user-level agent
renderer; allowlist renderer (routine tier + deny tier) with
`allowlist-fidelity`; hooks renderer with the ETHOS `sessionStart` and
`subagentStart` hooks; `/init --harness` writing the §2b layer and the
`harness-config` drift surface; `AGENTS.md` canonicalisation. Ships `claude`,
`copilot`, `cursor`. 2 REQs (framework; two adapters). Dogfood on both.

**P3 — Codex adapter.** TOML agents (user-level), Starlark rules, config.toml,
hooks.json, the delegate routing block to `~/.codex/AGENTS.md`. Gated on
§6.1a. 1 REQ.

**P4 — Gemini adapter.** `.gemini/settings.json` renderer (hooks with ms
timeouts, `tools.allowed` with both git spellings, `context.fileName`),
user-level agents with its tool names, policy deny rules,
`gemini-extension.json` so `gemini extensions link <clone>` is an alternative
install. Before starting: check what Antigravity CLI kept and target the
intersection. Gated on §6.4. 1 REQ.

**P5 — Knowledge loop.** `sessionStart` hook records `session_id` and, where
given (Cursor, Claude), `transcript_path` into `.adlc/.session/<id>`;
`/wrapup` reads the sidecar first, then per-harness discovery; `extract-chat
--format claude|codex|copilot|gemini|cursor` with fixtures captured from real
runs. 1 REQ.

**P6 — Exec engine.** §2f: working-copy strategy per adapter, per-run trust,
orchestrator-built prompt, awaiting-approval state and `/sprint approve`,
orchestrator-executed one-way moves, resume. Adapters only for harnesses whose
P2–P4 adapter has shipped (m1). 1 REQ, the largest; needs an ADR on process
supervision, log capture and the approval protocol. Gated on §6.1b, §6.3.

**P7 (optional).** Plugin manifests at the clone root (`.claude-plugin/`,
`.cursor-plugin/`, `gemini-extension.json`, Copilot plugin); and, separately,
`install.sh --migrate-home <dir>` with a `--back` inverse for machines that
want the toolkit's state out of `~/.claude`. Neither is on the port's path.

Order: P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7. Gemini moves ahead of the exec
engine so P6 ships with all four adapters it can dogfood.

### Spec map (written 2026-10-27, all `draft`, all full lane)

| phase | REQ | gates / depends on |
|---|---|---|
| P0 | REQ-654 ADLC_HOME, `~/.agents/skills` mount, `adlc harness detect`, doctor `consumer-sync` | — |
| probes | REQ-664 `adlc harness probe` (the §6 experiments as scripted, repeatable probes) | REQ-654 |
| P1 | REQ-666 skill text portability; REQ-661 progressive-disclosure splits | REQ-654; the two touch the same three SKILL.md files |
| P2 | REQ-657 harness adapter framework (+ `claude` adapter); REQ-656 Copilot + Cursor adapters | REQ-654; REQ-656 on REQ-657 |
| P3 | REQ-655 Codex adapter | REQ-657; §6.1 via REQ-664 |
| P4 | REQ-658 Gemini adapter | REQ-657; §6.4/§6.5 via REQ-664 and an Antigravity note |
| P5 | REQ-660 session sidecar + multi-harness transcripts | REQ-657 (hook render; ownership split recorded in its OQ-8) |
| P6 | REQ-659 exec engine core (+ `claude` exec adapter); REQ-662 exec adapters for the other four | REQ-657, REQ-655/656/658; §6.1b/6.3/6.6/6.8/6.11/6.12 via REQ-664 |
| P7 | REQ-665 plugin manifests; REQ-663 opt-in home migration | REQ-654; REQ-663 also on `consumer-sync` being green |

Two things the specs found that the plan did not say: REQ-663 cannot share one
lock through a symlink (the allocator refuses symlinked lock paths), so it uses
lock tombstones plus a hard consumer-sync gate instead; and REQ-656 flags that
Copilot CLI reads both `.claude/settings.json` hooks and `.github/hooks/*.json`,
so the ETHOS hook may fire twice there until the dogfood run settles which file
carries it.

---

## 4. What is lost per harness (say it in the README)

| | Copilot | Codex | Gemini | Cursor |
|---|---|---|---|---|
| Read-only reviewers | enforced (`tools:`) | **honour-system** | enforced | enforced (`readonly`) |
| Committed allowlist | **no** (user file / session flags) | yes | yes | yes |
| Allowlist granularity | subcommand | token prefix | prefix | command base |
| Ask-tier deny expressible | yes (`--deny-tool`) | yes (`forbidden`) | yes (policy, user-level only) | yes (`deny`) — but see §6.3 |
| ETHOS in subagents | hook | hook | prompt-prepended only | hook |
| Subagent nesting (pipeline-runner stays flat anyway) | 6 | undocumented | none | 1 |
| `/sprint` Workflow engine | no | no | no | no |
| Transcript schema | undocumented | undocumented | JSONL, documented location | CC-compatible |
| Explicit `/skill` | yes | `$skill` | **automatic only, consent prompt** | yes |
| Future | GA | GA | consumer → Antigravity | GA |

---

## 5. Lint, doctor and test surface added

- `skills-ref validate` on every skill.
- `no-harness-path`: no literal `~/.claude`, `~/.codex`, `~/.copilot`,
  `~/.gemini`, `~/.cursor` in a SKILL.md, partial, agent body or tool — only
  `$ADLC_HOME` and adapter lookups. (The `arg-templating`, `cross-fence-*`,
  `unguarded-source` checks all stay.)
- `dispatch-has-fallback`, `description-budget`, `allowlist-fidelity`,
  `render-parity --check` (toolkit CI).
- `adlc doctor`: `consumer-sync`, `harness:<name>` per installed harness,
  `agents-symlink` unchanged.
- `/template-drift`: new `agents` and `harness-config` surfaces.
- Fixture transcripts per harness for `extract-chat`.
- Exec-engine tests: the approval protocol against a fake harness binary.

---

## 6. Verify on real installs before writing the specs

1. **Codex git writes.** (a) In a main checkout under `workspace-write` with
   an `allow` `prefix_rule` for `git commit`: does it run unprompted under
   `on-request`, interactive and in `codex exec`? (b) In a **linked worktree**,
   whose git data is in `<repo>/.git` outside the sandbox root: does commit
   work with `writable_roots` set to the repo, given the documented
   `<writable_root>/.git` read-only rule? Decides P3 autonomy and P6's
   working-copy strategy for Codex.
2. **Copilot committed allowlist**: anything beyond `allowed-tools:` in
   SKILL.md and the user-level `permissions-config.json`?
3. **Cursor headless deny**: without `--force`, does `agent -p` honour
   `.cursor/cli.json` `allow` for the routine tier and `deny` for the ask
   tier, and what exit/state results from a denied command?
4. **Gemini skill activation headless**: does `activate_skill` get
   auto-approved under `tools.allowed` without `--yolo`? (Matters for
   interactive use; the exec engine does not depend on it.)
5. **Gemini/Antigravity**: which of skills, hooks, subagents, extensions
   Antigravity CLI kept, and its directory names.
6. **Shell timeouts** per harness vs the ≥120 s `adlc-read` needs.
7. **Skill discovery with the clone root mounted** at `~/.agents/skills`:
   confirm Codex, Gemini and Cursor ignore non-skill directories; otherwise
   point that one symlink at a generated skills-only view.
8. **Hooks in headless mode after per-run trust**, on each harness: does the
   `sessionStart` context reach the model, and does writing trust into the
   user config (Codex, Gemini) take effect for a `-p` run started immediately
   after?
9. **Transcript fixtures**: one real session file from Codex and Copilot.
10. **Claude `$N` substitution** (M3): confirm with a throwaway skill that
    `$1` inside a fence is substituted when the body has no `$ARGUMENTS`. The
    dodges stay regardless; this only decides whether the lint can ever be
    narrowed.
11. **Allowlist vs fences**: on each harness, hand a partial-sourcing fence to
    the routine-tier allowlist and record whether it prompts; this fixes the
    "broad entry" each renderer must emit.
12. **Stdin prompt delivery** per harness in headless mode: that a multi-hundred-line
    prompt on stdin is accepted whole, and which flag combination (with or
    without `-p`) makes it the task rather than attached context.

---

## 7. Sources

Codex: see `codex-portability.md` §5.
Copilot: docs.github.com — copilot-cli add-skills, create-skills,
create-custom-agents-for-cli, custom-agents-configuration, cli-hooks-reference,
allowing-tools, cli-command-reference, cli-programmatic-reference,
cli-config-dir-reference, add-custom-instructions, add-mcp-servers, fleet,
autopilot; code.visualstudio.com agent-skills, custom-agents, hooks,
custom-instructions; github/copilot-cli issues #1021, #618, #3551.
Gemini: geminicli.com/docs — skills, using-agent-skills, creating-skills,
core/subagents, hooks, hooks/reference, reference/configuration, tools/shell,
reference/policy-engine, cli/trusted-folders, cli/sandbox, cli/gemini-md,
reference/memport, cli/headless, cli/custom-commands, extensions/reference,
cli/git-worktrees; google-gemini/gemini-cli source (skillLoader.ts,
agentLoader.ts, hooks/migrate.ts, chatRecordingService.ts);
developers.googleblog.com Antigravity transition post (May 2026).
Cursor: cursor.com/docs — skills, context/subagents, hooks,
reference/third-party-hooks, agent/security/run-modes, reference/permissions,
cli/reference/permissions, cli/reference/configuration, cli/reference/parameters,
cli/reference/output-format, cli/headless, context/rules, context/mcp,
configuration/worktrees, reference/plugins, cli/changelog, release-notes.
Agent Skills spec: agentskills.io/specification.
Toolkit: `partials/id-alloc.sh`, `partials/forge.sh`, `partials/lane-check.sh`,
`tools/lint-skills/check.py` (arg-templating), `tools/adlc/lane_check.py`,
`agents/pipeline-runner.md`, `sprint/SKILL.md`, LESSON-335, LESSON-441.

---

## 8. Revision 2 changelog (adversary findings → changes)

| finding | change |
|---|---|
| C1 skills farm broke `~/.claude/skills/<non-skill>` paths in vendored partials, `/init`, `/template-drift`, README | Rule A. `~/.claude/skills` and `~/.claude/agents` unchanged; `~/.agents/skills` is the only new mount; farm only as a §6.7 fallback for that one symlink; `init`, `template-drift`, README on P0's list |
| M1 allowlist blind to fences and `git -C`; `--force`/`--yolo` approved the ask tier; no approve-and-resume | Rule B; §2e limits stated; §2f orchestrator-owned one-way moves, `awaiting_approval` state, `/sprint approve`, deny tier rendered, no yolo flags; §6.11 |
| M2 stale vendored `id-alloc.sh` would split counters and locks | nothing moves (Rule A); doctor `consumer-sync` |
| M3 reverting `${1}`/`$(0)` dodges reintroduces LESSON-335 | dodges and `arg-templating` lint stay; §6.10 |
| M4 no per-worktree trust | §2f step 2, adapter `trust` field, §6.8 |
| M5 sandbox rooted at worktree cannot reach the common git dir | §2f step 1 working-copy strategies, §6.1b |
| M6 ETHOS hook misses subagents | §2d: `!` line stays on Claude; `subagentStart` hooks; prompt-prepend where no event exists |
| M7 project-level agent copies, no drift surface, lane-check blind to new config | user-level renders only (`--project-agents` opt-in); `agents` and `harness-config` drift surfaces; `lane_check.py` blocked paths extended |
| M8 no rollback; config/venv move hazards | no moves in P0; rollback = checkout + install; `--migrate-home`/`--back` deferred to P7 |
| M9 "same prompt on all five" contradicted invocation row | §2f step 3: orchestrator inlines the skill body; no invocation syntax on the critical path |
| m1 Gemini exec adapter before Gemini adapter | order P4 before P6 |
| m2 Codex nesting "documented single level" | corrected to undocumented here and in `codex-portability.md` |
| m3 `/proceed` "re-invokes itself" | removed |
| m4 rendered `~/.claude/agents` | symlink stays; render stamps in place |
