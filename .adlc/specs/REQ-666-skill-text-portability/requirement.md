---
id: REQ-666
title: "Skill text portability: `$ARGUMENTS` as prose, run-and-read context blocks, one portable dispatch fallback, the Teton-only surface retired, agents vendored, and the lint that keeps it so"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "sh", "python"]
concerns: ["portability", "developer-experience", "harness-agnostic", "structural-enforcement", "maintainability"]
tags: ["multi-harness", "skill-text", "arguments", "dispatch", "inline-fallback", "teton", "provenance-safe", "harness-skip", "lint-skills", "template-drift", "init", "agents", "lane-check", "description-budget", "no-harness-path", "ethos-line", "skills-ref", "partials"]
lane: "full"
lane_reason: "footprint is every SKILL.md plus lint-skills, lane_check defaults, init and template-drift, far above max_files; it changes a gate's blocked paths and the lint that certifies skills; and it reverses decisions recorded in BUG-228, BUG-230, REQ-646 BR-15 and REQ-648 BR-3"
lane_forced: false
---

## Description

This is Phase 1 of `.adlc/research/multi-harness-plan.md` (revision 2), the
first half of it (P1a): make the **text** of every skill mean the same thing on
Claude Code, Copilot CLI, Codex, Gemini CLI and Cursor, before any adapter
(P2 onward) renders anything. REQ-654 (P0) is the prior art and the
prerequisite: it made the toolkit's home a variable without moving a file.
This REQ does the same for skill prose: nothing a skill *does* changes on
Claude Code, but every Claude-specific spelling that another harness would read
as literal text, or could not act on, is replaced by a spelling every harness
can follow.

Six things stand between skill text and portability. Three (1–3) are Claude
Code idioms that other harnesses do not have, one (4) is a surface built for a
harness the toolkit no longer targets, and two (5–6) are a budget and a gate
that nothing enforces yet:

1. **`$ARGUMENTS`** appears 30 times across 17 `SKILL.md` files (31 counting `manifest/SKILL.md:88`'s `${ARGUMENTS:-…}` form). Claude Code
   substitutes it before the model sees the file; every other harness shows the
   model the literal string. Claude Code's own documented fallback makes prose
   safe: when no placeholder receives the arguments it appends
   `ARGUMENTS: <value>` to the skill content, so "the argument is whatever
   follows the skill name" reaches the model on every harness. The `${1}` /
   `$(0)` dodges and the `arg-templating` lint **stay** (plan M3, LESSON-335):
   Claude Code substitutes `$0`–`$9` whether or not `$ARGUMENTS` appears, and
   the doc confirms `$N` is independent shorthand for `$ARGUMENTS[N]`.
2. **Context preamble `!` lines.** Beyond the ETHOS line, 43 inline
   `` !`cmd` `` lines across 14 skills load architecture, templates, branch
   state and the like at render time. `template-drift/SKILL.md:39`'s ETHOS
   *presence probe* (`test -f .adlc/ETHOS.md && echo present || …`) is one of
   the 43: it mentions `ETHOS.md` but is not the ETHOS line, and BR-2 moves it
   into the context block with the rest. Other harnesses render them as text. On
   Claude Code they also carry a hazard the toolkit has been guarding with
   `|| echo` on every line: a failing `!` command aborts the whole invocation.
   Each skill's non-ETHOS preamble becomes one **run-and-read fenced block**
   the model executes with its shell tool as the skill's first action and reads
   the output of. **The ETHOS `!` line stays permanently on Claude Code** (plan
   M6): it is the only path that reaches a skill invoked inside a subagent
   there, and P2's hooks are additive to it.
3. **Agent dispatch.** `architect`, `review`, `optimize`, `reflect` and
   `bugfix` say "launch N agents using the Agent tool, defined in
   `~/.claude/agents/`" and nothing else. `/analyze` (BUG-230) and `/proceed`
   (subagent mode) each carry their own inline fallback in their own words.
   One portable paragraph replaces all of them, and the checklists it points at
   live **inside the project** at `.adlc/agents/<name>.md`, because a harness
   whose reads are jailed to the session root cannot reach `~/.claude/agents`
   (BUG-230 root cause 1), and neither can a Claude Code subagent running in a
   worktree (`init/SKILL.md`'s own rationale for vendoring partials).
4. **The Teton-only surface.** BUG-218/220/224/228/230 fitted the skills to
   Teton Code's shell-provenance classifier: the `**Provenance-classifying
   harness (BUG-228):**` prose line above every delegating gate, the
   `# provenance-safe` fence grammar in `/analyze`, the mentions of Teton Code
   in skill, partial and lint text (the plan counts 14 in skill text; the
   survey for this spec finds roughly 30 once the lint's README, docstrings
   and fixtures are included), and the two lint checks `harness-skip` and
   `provenance-safe-fence` plus the `missing-harness-line` rule inside
   `lesson-check-order`. None of the five target harnesses classifies shell
   provenance, so this is dead weight that every future skill edit has to
   carry. It is retired. What BUG-230 found underneath it is **kept**: a
   skill step that dispatches agents must say what to do without an agent
   tool, and the audits that run inline are read-only.
5. **Descriptions.** Every harness loads every skill description into context
   at session start, and Claude Code truncates the listing at 1 536
   characters. `template-drift`'s description is 969 characters, `adversary`'s
   535, `proceed`'s 479, counted in Unicode code points (975, 537 and 493 as
   UTF-8 bytes; `description-budget` counts code points, never bytes). A
   budget, enforced by lint, keeps the listing cheap on
   all five harnesses.
6. **The gate.** `lane_check.py`'s default blocked paths do not yet name the
   per-harness config the P2–P4 adapters will write, nor the vendored
   checklists this REQ adds, so a lite PR could widen an allowlist or soften a
   checklist unnoticed (plan M7, LESSON-718).

Everything above is held in place by lint, not prose (LESSON-012): five new
`tools/lint-skills` checks (`skills-ref`, `dispatch-has-fallback`,
`description-budget`, `no-harness-path`, `ethos-line`), two retired, and the existing
`arg-templating`, `cross-fence-*`, `unguarded-source` and
`sync-surface-parity` checks unchanged. The REQ-610 guarded fence spelling,
with its literal `~/.claude/skills/partials/<name>.sh` fallback, is excepted
from `no-harness-path` exactly as REQ-654 BR-3 and BR-13 except it.
(informed by REQ-654, BUG-230, BUG-228, LESSON-335, LESSON-012)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SkillText | input_section | prose | states that the argument is whatever follows the skill name, and what the skill does with none; contains no `$ARGUMENTS` |
| SkillText | argument_in_fence | placeholder | where a fence consumed `$ARGUMENTS` — `/spec` intake's two fences (`adlc_intake_detect "$ARGUMENTS"`), `/sprint`'s `Workflow` call, and `/manifest`'s self-id fence (`manifest/SKILL.md:88`, `${ARGUMENTS:-…}`, a shell expansion Claude Code does not substitute and no harness populates — today it silently falls through to `MANIFEST_SELF`/the branch name; BR-1 rewrites it to the placeholder rule) only; `/wrapup`, `/canary`, `/adversary`, `/template-drift` and the rest read it in prose — the fence carries an angle-bracket placeholder and the prose says to substitute the literal with BR-1's single-quote-escaped spelling (or a quoted here-doc), the same way echoed values are threaded between fences today |
| SkillText | context_block | fenced block | one ```sh fence, the skill's first instruction, listing the reads the `!` lines performed; the model runs it and reads its output; every line survives a missing file (prints a notice, never exits non-zero for the block) |
| SkillText | ethos_line | `!` line | unchanged: `` !`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init to vendor .adlc/ETHOS.md` `` |
| SkillText | dispatch_paragraph | prose | the one canonical wording: "If this harness can run subagents, dispatch these agents in parallel; if it cannot, or you are a subagent, run each checklist inline from `.adlc/agents/<name>.md`." followed by the agent names; an inline run is read-only for review/audit agents |
| SkillText | description | frontmatter string | length ≤ `description_budget`; the key use case first |
| VendoredAgents | path | dir | `.adlc/agents/`, written by `/init` from the toolkit's `agents/*.md`; a checklist store the model reads, never an agent registry on any harness (no harness discovers agents there) |
| VendoredAgents | posture | enum | `synced` / `stale` / `missing`; `stale` only, no customization classification (same posture as `partials`) |
| LintCheck | `skills-ref` | check | every `*/SKILL.md` passes `skills-ref validate` when the validator is on PATH; one SKIP line naming the install command when it is not; never a hard dependency (REQ-425 BR-1) |
| LintCheck | `dispatch-has-fallback` | check | every prose instruction to launch or dispatch agents is accompanied by the canonical dispatch_paragraph wording, or by an explicit statement that the skill requires subagent dispatch and stops without it |
| LintCheck | `description-budget` | check | `description:` length in Unicode code points ≤ `description_budget` per skill; reports the sum across skills |
| LintCheck | `no-harness-path` | check | no literal `~/.claude`, `$HOME/.claude`, `~/.codex`, `~/.copilot`, `~/.gemini`, `~/.cursor` in any `*/SKILL.md`, `partials/*.sh`, `partials/*.md`, `agents/*.md` or `tools/**` source; exceptions: the REQ-610 guarded fence spelling, the `ADLC_HOME` default-expansion spelling REQ-654 establishes, comment lines, and the documented compatibility aliases in `install.sh` and the `unguarded-source` lint literal |
| LintCheck | `ethos-line` | check | every `*/SKILL.md` carries the System Model `ethos_line` spelling exactly once, byte-identical; a missing, altered or duplicated line is a finding; walks `*/SKILL.md` only; a companion must not carry the line, which REQ-661's `companion-templating` enforces |
| LaneCheckDefaults | blocked_paths | tuple | gains `.adlc/agents/**`, and names `.github/agents/**` and `.github/hooks/**` explicitly though `.github/**` already covers them; `.codex/**`, `.gemini/**`, `.cursor/**`, `.github/**` and `.adlc/partials/**` are already present and unchanged; every entry this REQ names is pinned by a test |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| context_read | the model runs a skill's context block | the block's output, read before Step 1 |
| dispatch_fallback_taken | a dispatch paragraph runs on a harness without subagents, or inside a subagent | the agent names run inline, read from `.adlc/agents/`; `/init` named as the remediation when the directory is absent |
| agents_vendored | `/init` | files copied into `.adlc/agents/`; `/template-drift` `agents` surface report |
| lint_finding | `tools/lint-skills` | `<file>:<line>: <check>: <message>` for the five new checks |
| lane_check_blocked | `lane_check.py` on a lite diff touching a new default path | `trigger=blocked-path`, `detail=<path>` (REQ-652 BR-6 fields, unchanged shape) |

_Permissions: not applicable — single-user tooling. Section omitted deliberately._

## Business Rules

- [ ] BR-1: No `SKILL.md` contains `$ARGUMENTS` after this REQ. Each skill's Input section says in prose that the argument is whatever follows the skill name and what the skill does when there is none. Where a fence consumed `$ARGUMENTS`, the fence carries a placeholder and the prose tells the model to substitute the literal single-quoted, with every `'` in the request spelled `'\''`; or, where the fence can take stdin, pass it through a quoted-delimiter here-doc (`<<'EOF'`). The request can contain backticks, `$` and apostrophes: a double-quoted substitution would expand the first two, and a bare single-quoted one turns an apostrophe into a syntax error that silently disables `/spec`'s intake gate (`adlc_intake_detect` never runs, the probe returns non-1 and nothing says why). The spelling is one rule stated once in `conventions.md` 'Bash in skills'; the skills point at it rather than restating it. `/spec`'s `--lite`/`--full` stripping keeps working, because it was already the model reading the argument, not shell (REQ-652 BR-4). The `${1}`/`$(0)` dodges stay everywhere, and the `arg-templating` lint stays as is: Claude Code substitutes `$0`–`$9` independently of `$ARGUMENTS`. (informed by LESSON-335, REQ-652)
- [ ] BR-2: Every non-ETHOS `!` line is removed and its command moved into one run-and-read fenced block per skill, placed where the `!` lines were and named consistently across skills; the block is the first thing the skill instructs the model to run, and the model reads its output before continuing. A missing file prints a notice (today's `|| echo` text) and never fails the block. The block obeys every existing fence rule (POSIX, no bare `$<digit>`, no `local`, guarded sourcing). Where a `!` line reaches into the toolkit (`/template-drift`'s `ls ~/.claude/skills/templates/`) it uses REQ-654's `ADLC_HOME` spelling. The ETHOS `!` line is byte-identical before and after in every skill; the `ethos-line` check (System Model `LintCheck`) holds it there: present exactly once, unchanged, in every `*/SKILL.md`. (informed by REQ-654, LESSON-020)
- [ ] BR-3: `architect`, `review`, `optimize`, `reflect` and `bugfix` carry the canonical dispatch paragraph (System Model `dispatch_paragraph`) at every point that launches agents, naming the agents and the checklist files. `/analyze`'s BUG-230 no-agent path, `/proceed`'s subagent-mode review (plus `agents/pipeline-runner.md`) and `/sprint`'s two references to `~/.claude/agents/pipeline-runner.md` (`sprint/SKILL.md:184,224`, the terminal-state contract and the Phase 8 merge rule) are rewritten to the same wording and point at `.adlc/agents/<name>.md`; `/analyze`'s condensed inline checklist is dropped once the vendored files exist, and the read-only rule for inline audits (BUG-230 follow-up: no test runner, build tool, package manager or interpreter) is kept in the paragraph that applies to review and audit agents. `bugfix`'s Explore dispatch, which has no checklist file, gets the same paragraph with "trace the bug yourself with your harness's search and read tools" as the inline arm. (informed by BUG-230, LESSON-663)
- [ ] BR-4: When `.adlc/agents/` is absent (a consumer that has not re-run `/init`), the inline arm names `/init` as the remediation and falls back to the toolkit's own `agents/<name>.md` through `<agents_root>` (REQ-654) where the harness can reach it, exactly as `analyze/SKILL.md:274` does today; it never fails silently and never improvises a checklist. Because BR-3 drops `/analyze`'s condensed inline checklist, a consumer that has not re-run `/init` loses the in-skill fallback it has today and is on this rule instead; the CHANGELOG entry therefore tells consumers to re-run `/init` (BR-6). (informed by LESSON-572, BUG-230)
- [ ] BR-5: The Teton-only surface is retired in one change: every `**Provenance-classifying harness (BUG-228):**` and `**Provenance-classifying harness (BUG-230):**` line and the "Shell on a provenance-classifying harness" rule in `/analyze`; every `# provenance-safe` marker (the git spellings underneath stay, they are portable commands); the lint checks `harness-skip` and `provenance-safe-fence`, their fixtures, the `HARNESS_SKIP_LITERAL`/`PROVENANCE_SAFE_MARKER` constants and the `missing-harness-line` rule inside `lesson-check-order` with its fixtures; the "Provenance-classifying harnesses" sections of `partials/delegate-gate.md` and `partials/lesson-check.md`; and the preamble-grammar and delegating-step paragraphs of `.adlc/context/conventions.md` that exist only for that classifier. Every mention of Teton Code *as a harness* goes with them; the in-model Grep alternatives at `review/SKILL.md:93` and `spec/SKILL.md:464`, and `partials/README.md:28,146`, go with them. Mentions of the `teton-code` **repository** as a consumer or example (`template-drift/SKILL.md:130`'s branch-triad example; the LESSON-646 notes in `partials/README.md:79`, `partials/conflict-bound.sh:17`, `partials/tests/conflict-bound.test.sh:24` and `agents/pipeline-runner.md:185`; `tools/lint-skills/tests/test_architect_footprint_state.py`'s docstring and fixture names) are repo names, not harness references, and stay; that list is AC-5's expected set. `partials/conflict-bound.sh:17`'s LESSON-646 comment also names the `teton-code` repo and stays. Lessons and bugs under `.adlc/` are history and are not edited. The **Timeout** guidance in `delegate-gate.md`'s section (where the shell tool takes a per-call timeout, give the `adlc-read` call at least 120 s; `lesson-check.md`'s section has none) is not Teton-specific and is kept: it moves under `### What a call site does with it` in `partials/delegate-gate.md` and into the Delegation pattern paragraph of `conventions.md` that survives. (informed by BUG-228, BUG-230, LESSON-662)
- [ ] BR-6: This REQ reverses recorded decisions and says so: BUG-228's resolution (the harness-skip line and its lint); BUG-230 in part — its lint (`provenance-safe-fence`), its condensed inline checklist, its skill-wide shell rule (`/analyze` "Shell on a provenance-classifying harness") and its Step 1.8/1.9 skips are reversed, while its read-only rule for inline audits and its Step 2a git spellings are kept; and REQ-646 BR-15/ADR-8. REQ-648 (draft) BR-3, BR-8 and BR-10 are not reversed but amended before REQ-648 is architected, in this REQ's sprint. The CHANGELOG entry names each, tells consumers to re-run `/init` (BR-4: without `.adlc/agents/` the dropped condensed checklist leaves `/analyze`'s inline audit on the fallback), and `/wrapup`'s lesson for this REQ records that LESSON-662 and LESSON-663's "how to apply" guidance no longer applies, using the `supersedes` field (REQ-646) rather than editing those lessons.
- [ ] BR-7: Every skill description is at or under `description_budget` Unicode code points (never bytes), with the key use case first. The budget is one constant in `tools/lint-skills`, enforced by `description-budget`; the skills over it today (`template-drift`, `adversary`, and any other the chosen budget catches) are trimmed in this REQ without losing a trigger phrase a user actually types. The budget value is an Open Question with a proposal below.
- [ ] BR-8: `/init` vendors every `agents/*.md` by glob into `.adlc/agents/` the way it vendors `partials/*.sh` — all of them, including `pipeline-runner`, `task-implementer` and `delegate-pre-pass`, which are harmless as read-only files and keep `sync-surface-parity` a one-line rule: copy on every run, canonical is the source of truth, listed in the `<!-- sync-surfaces: init -->` block. The source path is REQ-654's `agents_root`, never a literal `~/.claude/agents`. `.adlc/agents/` is a checklist store: no harness is configured to discover agents there, so a project that is also a Claude Code project does not get double-registered agents (plan M7). `/init`'s rationale paragraph for vendored copies names agents alongside ETHOS, templates and partials. (informed by REQ-654, REQ-433)
- [ ] BR-9: `/template-drift` gains the `agents` surface in its `<!-- sync-surfaces: template-drift -->` block, compared file by file against the toolkit's `agents/*.md` with `partials`-posture (`synced`/`stale`/`missing`, plus `missing upstream` for a rogue file; no customization classification), with the Step 0a baseline rule (BUG-204) applied as it is to partials. The existing `sync-surface-parity` lint must pass with both lists updated. A vendored agent whose only difference is the `model:` line that `adlc agents render` stamps (REQ-516) still reports `stale`; that is correct, the copy is a snapshot. (informed by BUG-204, BUG-203)
- [ ] BR-10: `tools/adlc/lane_check.py`'s `DEFAULT_BLOCKED_PATHS` already contains `.codex/**`, `.gemini/**`, `.cursor/**`, `.github/**` and `.adlc/partials/**` (verified by grep on 2026-10-27: `lane_check.py:175,229,283,285,286`); those entries are unchanged, and each gains a pinning test where it lacks one. The genuinely new entry is `.adlc/agents/**` (the checklist store BR-8 creates); `.github/agents/**` and `.github/hooks/**` are added explicitly although `.github/**` already matches them, so the tuple documents the P2–P4 adapters' write targets and a test pins each of the three. The `partials/lane-check.md` defaults block is updated in the same change so the documented list and the tuple agree. The default list is still extended by a project's `lanes.lite.blocked_paths`, never replaced. (informed by LESSON-718, REQ-652)
- [ ] BR-11: `tools/lint-skills` gains `skills-ref`: when a `skills-ref` executable is on PATH, every `*/SKILL.md` is validated with `skills-ref validate` and any failure is a finding; when it is absent, the check prints one SKIP line naming how to install it and contributes no finding, so the lint stays runnable offline with stdlib only (REQ-425 BR-1, LESSON-395). Whether the validator rejects the toolkit's `argument-hint` frontmatter is an Open Question; if it does, the field moves under `metadata:` or the check allows that one key, decided in architecture, not by dropping the check. (informed by REQ-425)
- [ ] BR-12: `tools/lint-skills` gains `dispatch-has-fallback`: a prose line that instructs launching or dispatching agents (the Agent tool, "launch … agents", "dispatch") without the canonical dispatch wording nearby is a finding. `/sprint`, which has no inline equivalent, states in one line that it requires a harness with subagent dispatch and stops otherwise; the check accepts that explicit statement. Fixtures cover a clean paragraph, a missing fallback, and the explicit-stop form. The check walks every `*/SKILL.md` and, once REQ-661 lands, every companion its BR-7 walk enumerates; it is one of the two checks that walk companions (with `no-harness-path`, BR-13). (informed by LESSON-012, LESSON-020)
- [ ] BR-13: `tools/lint-skills` gains `no-harness-path` (System Model `LintCheck`): the five harness home literals are findings in skill, partial, agent and tool text, with the stated exceptions and no others. It subsumes REQ-654 BR-13's narrower check (one check, one exception list, not two). The `unguarded-source` check's canonical literal stays (REQ-654 BR-3). The check walks every `*/SKILL.md` and, once REQ-661 lands, every companion its BR-7 walk enumerates, in addition to the partial, agent and tool paths above; it is one of the two checks that walk companions (with `dispatch-has-fallback`, BR-12). The `~/.claude` mentions in skill prose (`template-drift`, `init`, `wrapup`, `sprint`, `bugfix`, `proceed`, `analyze`, about 70) are rewritten to `$ADLC_HOME`/`<adlc_home>` in this REQ; `tools/**` tests and READMEs are an exception list the lint carries. (informed by REQ-654, REQ-610, LESSON-441)
- [ ] BR-14: The `arg-templating`, `cross-fence-fn`, `cross-fence-var`, `unguarded-source`, `read-bin-fallback`, `lane-vocabulary`, `retrieval-status-parity` and `sync-surface-parity` checks are unchanged in behaviour; the lint README renumbers its list, documents the five new checks (`ethos-line` among them) and removes the retired checks from it, not leaving them as "deprecated". `python3 tools/lint-skills/check.py --root .` exits 0 on the finished tree.
- [ ] BR-15: Zero behaviour change on Claude Code beyond the two this REQ chooses: the context reads become one shell call the model makes (so `allowed-tools` or the project's permission allowlist should cover the read-only commands they contain: the context blocks are composed from commands today's allowlist already pre-approves wherever possible, and any command that is not (today: `cat`, `grep`, `gcloud`) is either respelled with a pre-approved verb or added to the allow list in this REQ — to `templates/claude-settings-template.json` (REQ-657 lands after this REQ and pins "today's template" including these additions as its routine-tier baseline, REQ-657 BR-6) — so no skill invocation gains a prompt; the CHANGELOG lists each addition), and a failing context command no longer aborts the invocation. Every delegating step's gate, telemetry and fallback (REQ-424, REQ-522, REQ-610) is unchanged. (informed by REQ-610, REQ-433)
- [ ] BR-16: All new and changed shell is POSIX-sh, bash 3.2, zsh and dash safe and is executed, not just read, under each (`partials/tests/run.sh` for partials; extracted context blocks run under `sh` and `zsh` in the toolkit repo and in a consumer). No `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable, no `local`. New Python is stdlib only. (informed by LESSON-329, LESSON-013, LESSON-335, LESSON-582)
- [ ] BR-17: Documentation moves with the code: `.adlc/context/architecture.md` "Skill anatomy" items 3–5 (ethos line, context block, Input prose) and "Agent anatomy"; `.adlc/context/conventions.md` "Agent dispatch patterns" gains the canonical paragraph and loses the Teton paragraphs; `partials/README.md`, `partials/delegate-gate.md`, `partials/lesson-check.md`; `tools/lint-skills/README.md`; `README.md`'s skill catalog if any description it quotes was trimmed; `CHANGELOG.md`. (informed by LESSON-019)

## Acceptance Criteria

- [ ] AC-1: `grep -rnE '\$\{?ARGUMENTS' */SKILL.md` returns nothing (the bare `$ARGUMENTS` and `manifest/SKILL.md:88`'s `${ARGUMENTS:-…}` form alike); `grep -rn '\$[0-9]' */SKILL.md` returns nothing (dodges intact, lint `arg-templating` still passes); the PR cites the `arg-substitution` result in `.adlc/research/harness-probes/claude.json` (REQ-664 AC-13) as the plan's §6.10 evidence; no duplicate experiment is run. (BR-1)
- [ ] AC-2: `/spec`, invoked with a request containing backticks, `$` and an apostrophe, runs its intake gate probe with the literal substituted into the placeholder and the probe returns 1 for an ordinary request; `/spec --lite x` and `/spec --full x` still force the lane and `/spec --lite --full x` still errors before any id is allocated. (BR-1)
- [ ] AC-3: `grep -n '!\`' */SKILL.md` returns exactly one line per skill, the ETHOS line, byte-identical to today's; each skill has one context fence in its place, and running each extracted fence under `sh` and `zsh` in this repo and in a consumer without `.adlc/templates/` exits 0 and prints the notices for the missing files; `ethos-line` fires once each on a fixture skill whose ETHOS line is missing, altered by one byte, or present twice, and is clean on the finished tree. (BR-2, BR-16)
- [ ] AC-4: In the five named skills, `/analyze`, `/proceed` and `agents/pipeline-runner.md`, every dispatch point carries the canonical wording; `grep -rn '~/.claude/agents' */SKILL.md agents/ partials/` returns nothing; `/review` run inside a Claude Code subagent (the Agent tool), in a consumer that has run this REQ's `/init`, completes its five checklists inline from `.adlc/agents/` and reports read-only findings; the same run in a consumer without `.adlc/agents/` names `/init` and completes the checklists from the toolkit's own `agents/` (as `analyze/SKILL.md:274` falls back today) rather than improvising them. (BR-3, BR-4)
- [ ] AC-5: `grep -rni 'teton\|provenance-safe\|provenance-classifying\|harness-skip' */SKILL.md agents/ partials/ tools/ README.md` returns only the repo-name lines BR-5 lists; `tools/lint-skills` no longer reports `harness-skip`, `provenance-safe-fence` or `missing-harness-line` on any fixture, and the fixtures for those checks are deleted. (BR-5)
- [ ] AC-6: The CHANGELOG entry names BUG-228, BUG-230, REQ-646 BR-15 and REQ-648 BR-3 as reversed in part; the `/wrapup` lesson for this REQ carries `supersedes:` naming LESSON-662 and LESSON-663. (BR-6)
- [ ] AC-7: `description-budget` fires on a fixture one character over the budget and is clean on the finished tree; every skill's `description:` is at or under the budget in Unicode code points (a fixture whose description is one code point over the budget but under it in bytes still fires) and the sum is printed; `/template-drift` and `/adversary` still trigger on the phrases their descriptions list under "Use when". (BR-7)
- [ ] AC-8: In a sandbox consumer, `/init` creates `.adlc/agents/` with one file per `agents/*.md`; `/template-drift` reports `agents: synced`; editing one vendored file reports it `stale`; deleting the directory reports every agent `missing` with `/init` as the remediation; `sync-surface-parity` passes. (BR-8, BR-9)
- [ ] AC-9: `pytest tools/adlc/tests` includes a case per path in BR-10 asserting `trigger=blocked-path` on a lite diff that touches it, including `.github/agents/x.md`, `.github/hooks/adlc.json` and `.adlc/agents/reflector.md`; the `partials/lane-check.md` defaults block lists the same paths. (BR-10)
- [ ] AC-10: With `skills-ref` absent from PATH, `tools/lint-skills` prints one SKIP line for the check and exits 0; with it installed, every toolkit skill validates, and a fixture skill whose `name:` differs from its directory produces a `skills-ref` finding. (BR-11)
- [ ] AC-11: `dispatch-has-fallback` produces exactly one finding on a fixture that says "launch 3 agents using the Agent tool" with no fallback, none on the canonical paragraph, and none on `/sprint`'s explicit-stop line. (BR-12)
- [ ] AC-12: `no-harness-path` produces one finding per fixture line containing `~/.claude/agents`, `$HOME/.claude/adlc`, `~/.codex`, `~/.copilot`, `~/.gemini` or `~/.cursor` in a skill, partial, agent or tool; none on the REQ-610 fence spelling, the `ADLC_HOME` default-expansion spelling, a comment line, `install.sh`'s alias or the `unguarded-source` literal; and the finished tree is clean. (BR-13)
- [ ] AC-13: `python3 tools/lint-skills/check.py --root .` exits 0; `pytest tools/lint-skills/tests tools/adlc/tests` passes; `sh partials/tests/run.sh` exits 0 under bash 3.2, zsh, `/bin/sh` and dash where installed. (BR-14, BR-16)
- [ ] AC-14: On Claude Code, `/spec`, `/architect`, `/review` and `/wrapup` each run end to end in this repo with the same outputs as before this REQ apart from the context block's one shell call; a delegating step still emits its telemetry record with the same fields. (BR-15)
- [ ] AC-15: `.adlc/context/architecture.md` and `conventions.md` describe the context block, the Input prose and the canonical dispatch paragraph, and contain no Teton paragraph; `tools/lint-skills/README.md` lists the five new checks and none of the retired ones. (BR-17)

## External Dependencies

- REQ-654 (P0): `ADLC_HOME`, `agents_root`, and the default-expansion spelling `no-harness-path` excepts. This REQ lands after it; with REQ-654's default the spellings resolve to today's paths.
- `skills-ref` (the Agent Skills reference validator) as an **optional** PATH executable for the `skills-ref` lint check; never required locally; the toolkit has no hosted CI, so AC-10's installed-path run is a manual, recorded step (Open Questions).
- REQ-657: lands **after** this REQ; its routine-tier baseline includes BR-15's additions to `templates/claude-settings-template.json` (`cat`, `grep`, `gcloud`); its pinned `claude` golden is taken after this REQ lands, so it already reflects the context blocks.
- REQ-664: the `arg-substitution` probe and `.adlc/research/harness-probes/claude.json`; lands before this REQ (plan: P1 gated on §6.10).
- REQ-661 (P1b): lands **after** this REQ and rebases on its text (Assumptions below).
- No new runtime dependency for any skill; `python3` stdlib for the lint and `lane_check`.

## Assumptions

- Claude Code's documented fallback holds: when no placeholder receives the arguments, `ARGUMENTS: <value>` is appended to the skill content, and `$N` substitution is independent of `$ARGUMENTS` (confirmed in the Claude Code skills documentation on 2026-10-27; REQ-664's `arg-substitution` probe is the live evidence).
- The four non-Claude harnesses deliver a skill's arguments to the model in some readable form (appended text or the invocation line); the prose form needs nothing more. Not verified on any of them here; the plan's §6 dogfood on each adapter will show it.
- Until P2's `sessionStart` hooks ship, a non-Claude harness shows the ETHOS `!` line as literal text; a model may run its command or ignore it. Accepted interim degradation, named in the README's "what is lost" table.
- A model given a run-and-read fence as the first instruction runs it before anything else, on every harness; the plan's §6 verification covers this with the rest of the dogfood.
- This REQ lands **before** REQ-661 (P1b). REQ-661's BR-5, BR-7 and AC-10 must drop `harness-skip`, `provenance-safe-fence` and the BUG-228 line before it is architected, and its BR-7 companion walk must include `dispatch-has-fallback` and `no-harness-path` (BR-12, BR-13); `skills-ref`, `description-budget` and `ethos-line` are per-skill checks on `SKILL.md` and do not walk companions. The two touch the same three `SKILL.md` files; REQ-661 rebases on this REQ's text.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] What is `description_budget`? Proposed: 512 code points, which trims `template-drift` (969) and `adversary` (535) and leaves `proceed` (479) and the rest untouched; Claude Code's listing truncates at 1 536 for `description` plus `when_to_use` combined, so 512 leaves room for the latter.
- [ ] Does `skills-ref validate` reject the toolkit's `argument-hint` frontmatter key (Claude Code accepts it; the Skills API and `package_skill.py` reject unknown keys)? If it does: move the hint under `metadata:` in every skill, or allow that one key in the check. Decide in architecture after running the validator once.
- [ ] What is the run-and-read block called and where exactly does it sit? "Step 0" collides with `/proceed`'s existing Step 0 (worktree, state, draft PR). Proposed: a `## Context` section heading kept where the `!` lines were, with the fence as its only content and the instruction "run this block first and read its output"; no step number.
- [x] ~~Does `/init` vendor all `agents/*.md` or only the checklist agents the dispatch paragraphs name?~~ Resolved as proposed: all, by glob (BR-8), for parity with partials and so `sync-surface-parity` stays a one-line rule; `pipeline-runner`, `task-implementer` and `delegate-pre-pass` are harmless as read-only files.
- [ ] What exact form does `dispatch-has-fallback` accept for `/proceed`'s Phase 4 task-implementer dispatch, where "run the checklist inline" is not the fallback (sequential in-context implementation is)? (`/sprint`'s form is settled by BR-12: one explicit requires-subagents-and-stops line.) Proposed: the canonical sentence with its inline arm replaced by Phase 4's own stated sequential behaviour, and the check keyed on the leading "If this harness can run subagents" clause.
- [x] ~~A toolkit CI job that installs `skills-ref` is a follow-up; until it exists AC-10's installed-path run is manual, performed and recorded in the PR.~~ Resolved: the toolkit has no hosted CI and this REQ implies none; AC-10's installed-path run is manual, performed and recorded in the PR, and that is the standing procedure, not an interim one.

## Out of Scope

- Any file move, `ADLC_HOME` itself, the `~/.agents/skills` mount, `adlc harness detect`, doctor `consumer-sync` — REQ-654 (P0).
- Splitting `spec`, `proceed` and `wrapup` into `SKILL.md` + `references/` — P1b (REQ-661).
- Harness adapters, `adlc harness install|render|doctor`, agent rendering to other formats, allowlist or hook rendering, `/init --harness`, the `harness-config` drift surface, `AGENTS.md` canonicalisation, `sessionStart`/`subagentStart` ETHOS hooks — P2 onward (REQ-657, REQ-656, REQ-655, REQ-658).
- Retiring the ETHOS `!` line on Claude Code — never (plan M6).
- Changing the REQ-610 guarded fence spelling or the `unguarded-source` lint literal — kept (REQ-654 BR-3).
- Narrowing or removing the `arg-templating` lint or the `${1}`/`$(0)` dodges — kept (plan M3).
- Verifying skill discovery, argument delivery or dispatch behaviour on any non-Claude harness — the plan's §6 experiments and each adapter's dogfood.
- Editing lessons or bugs under `.adlc/` that record the Teton work; they stay as history.
- Windows.

## Retrieved Context

- REQ-610 (spec, score 11): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- LESSON-020 (lesson, score 10): A shell function shared across SKILL.md steps must be a sourced partial, not a cross-block definition — fenced blocks don't share shell state; and the presence-guard protecting it must follow the same indirection or it rots
- REQ-652 (spec, score 9): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- LESSON-335 (lesson, score 9): Four zsh-executor/templating hazards in SKILL.md scripts: bare $<digit>, [0] arrays, unmatched globs, status= assignments
- REQ-433 (spec, score 9): Kimi telemetry global-fallback resolver — make delegation telemetry work in downstream repos
- LESSON-572 (lesson, score 8): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 8): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts
- REQ-546 (spec, score 8): Atomic remote id reservation at allocation time (close the allocation-to-visibility window)
- REQ-518 (spec, score 8): Collision-Safe ID Allocation Across Users and Machines
- LESSON-329 (lesson, score 8): Skill bash runs under the operator's shell (zsh) — dogfood by executing it, don't trust lint or an sh-only run
- REQ-436 (spec, score 8): Extract analyze telemetry helper to a sourceable POSIX partial (fix cross-block + local defects)
- LESSON-013 (lesson, score 8): BSD grep \b word-boundary in -E silently fails on macOS — use -wF instead
- REQ-425 (spec, score 8): Pre-merge detection of corrupted shell constructs in SKILL.md files (catches REQ-424-style substitution disasters before they ship)
- LESSON-718 (lesson, score 7): A gate that judges a change must not load anything the change can edit — not its code, its config, its partials, or a path that differs only in letter case
- LESSON-663 (lesson, score 7): To keep a model's shell inside a classifier's grammar, allowlist what it may run — forbidding commands one at a time never converges
