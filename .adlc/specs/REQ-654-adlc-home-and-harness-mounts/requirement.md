---
id: REQ-654
title: "ADLC_HOME (default ~/.claude, nothing moves), the ~/.agents/skills mount, `adlc harness detect`, and the doctor `consumer-sync` check"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/install"
domain: "adlc"
stack: ["sh", "python", "markdown"]
concerns: ["portability", "developer-experience", "harness-agnostic"]
tags: ["adlc-home", "install", "doctor", "symlink", "harness", "consumer-sync", "paths", "multi-harness", "partials", "template-drift"]
lane: "full"
lane_reason: "changes install infrastructure (install.sh, adlc doctor) and the footprint is far above max_files: partials, tools/adlc, tools/delegate, agents, init and template-drift skills, README"
lane_forced: false
---

## Description

This is Phase 0 of `.adlc/research/multi-harness-plan.md` (revision 2): the
one prerequisite every later harness adapter (Copilot CLI, Codex, Gemini CLI,
Cursor) depends on. It makes the toolkit's own home directory a variable
instead of the literal `~/.claude`, and it does so **without moving a single
file**, because the adversary pass on the plan showed that relocating
`~/.claude/skills`, the ID counters or the machine config breaks every consumer
repo whose vendored partials still carry the old literal (the LESSON-441
shape), splits the machine-wide allocation lock, and leaves no rollback.

Four deliverables, all additive:

1. **`ADLC_HOME`.** Every piece of toolkit *code* that today hardcodes
   `~/.claude` as the place the toolkit's machine state lives (install root,
   agents root, machine config, counters, lock dirs, reservation ledger, the
   delegation venv, the installed engine paths `lane_check.py` /
   `forge_config.py` / `tools/delegate`) derives that path from `ADLC_HOME`,
   whose default is `$HOME/.claude`. With the default, every byte on disk stays
   exactly where it is. The variable is the seam the adapters will hang off; it
   is not a migration, and no migration tooling ships here (that is the plan's
   optional P7).
2. **The `~/.agents/skills` mount.** The four non-Claude harnesses all read
   `~/.agents/skills`. `install.sh` creates it as a symlink to a generated
   **skills-only view** of the clone (one link per directory that holds a
   `SKILL.md`), so harnesses that walk the mounted root never see `tools/`,
   `partials/`, `templates/` or `.adlc/`. `~/.claude/skills` stays a symlink
   to the clone root, untouched: it is Claude Code's mount and the
   compatibility alias every vendored partial's fallback path still resolves
   through.
3. **`adlc harness detect`.** A read-only `adlc` subcommand that reports which
   harness binaries are installed and whether the toolkit is mounted where
   each one looks. It is what `/init --harness` (P2) and the exec engine (P6)
   will call to choose defaults; here it ships as a command and a doctor
   check.
4. **`adlc doctor consumer-sync`.** A doctor check that walks the machine's
   participating repos (the same `$ADLC_REPOS_ROOT` set id-alloc already
   scans) and reports every consumer whose vendored `.adlc/partials/` is
   behind the toolkit's canonical copies. Stale vendored copies are the
   hazard that made relocation unsafe; this check makes them visible on the
   machine, not only inside one repo at a time via `/template-drift`.
   (informed by LESSON-441, BUG-204)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| HomeResolution | adlc_home | path | `$ADLC_HOME` if set and absolute, else `$HOME/.claude`; a relative or empty `ADLC_HOME` is rejected loudly, never silently defaulted |
| HomeResolution | skills_root | path | `<adlc_home>/skills` — symlink to the clone root |
| HomeResolution | agents_root | path | `<adlc_home>/agents` — symlink to `<clone>/agents` |
| HomeResolution | machine_config | path | `$ADLC_CONFIG` if set, else `<adlc_home>/adlc/config.yml` (existing `ADLC_CONFIG` precedence unchanged) |
| HomeResolution | counter(kind) | path | `<adlc_home>/.global-next-<kind>` for req/bug/lesson; lock dir `<counter>.lock.d`; ledger `<adlc_home>/.adlc-own-reservations` |
| HomeResolution | venv | path | `<adlc_home>/delegate-venv` |
| SkillsView | location | path | under `<adlc_home>`; exact path is an architecture decision |
| SkillsView | entry | symlink | `<view>/<name>` → `<clone>/<name>` for every `<clone>/<name>/SKILL.md`; `<name>` equals the SKILL.md `name:` field, which equals the directory name |
| AgentsMount | path | path | `$HOME/.agents/skills`; resolves to the SkillsView, or holds one entry per toolkit skill when the user already owns the directory |
| HarnessProbe | name | enum | `claude`, `copilot`, `codex`, `gemini`, `cursor` |
| HarnessProbe | binary | string | the executable looked up on PATH (`claude`, `copilot`, `codex`, `gemini`, `agent`); `present` / `absent` |
| HarnessProbe | version | string | output of the binary's version flag, or `unknown`; never a failure |
| HarnessProbe | mount | enum | `mounted` / `not-mounted` / `n/a` — whether that harness's user-level skills dir resolves to the toolkit (Claude: `<adlc_home>/skills`; the other four: `$HOME/.agents/skills`) |
| ConsumerSyncReport | repo | path | a git checkout under `$ADLC_REPOS_ROOT` that has `.adlc/partials/` |
| ConsumerSyncReport | baseline | string | the clone's branch, dirty flag, and distance behind `origin/<default>`, named in the report (informed by BUG-204) |
| ConsumerSyncReport | verdict | enum | `in-sync` / `stale (<n> files: <names>)` / `unverified-baseline` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| home_resolved | any toolkit code path that needs a machine-state path | the resolved `adlc_home` and whether it came from the env or the default |
| skills_view_rebuilt | every `install.sh` run | links added / removed / unchanged; names skipped because a non-toolkit entry already owned them |
| harness_detected | `adlc harness detect`, `adlc doctor` | one HarnessProbe per known harness |
| consumer_stale | `adlc doctor` `consumer-sync` | repo path, stale file names, remediation (`cd <repo> && claude -p '/template-drift'`-style one-liner naming the skill, never a bare "see docs") |

_Permissions: not applicable — single-user machine tooling. Section omitted deliberately._

## Business Rules

- [ ] BR-1: `ADLC_HOME` is the single source for every machine-state path the toolkit's code derives: `skills_root`, `agents_root`, `machine_config`, counters, lock dirs, ledger, venv, and the installed-engine lookups (lane check, forge config, delegate tools). Every partial, tool, installer and agent body that reads one of those paths derives it from `ADLC_HOME`; the set of such files is whatever BR-13's lint finds, not a list kept here. Its default is `$HOME/.claude`. With the default, the resolved paths are byte-identical to today's literals, so no file is created, moved, or read from a new location (the plan's Rule A). (informed by REQ-519, LESSON-441, LESSON-019)
- [ ] BR-2: Existing precedence is preserved: `ADLC_CONFIG` still outranks the derived `machine_config`; `ADLC_TELEMETRY_LOG` and `ADLC_REPOS_ROOT` are untouched; `HOME` is still honored by every partial that reads it. A set `ADLC_HOME` that is empty or not absolute is an error that names the variable, not a silent fall-through to the default (the same posture `lane-check.sh` takes for a non-absolute `HOME`).
- [ ] BR-3: The canonical guarded two-level partial-sourcing spelling (REQ-610 BR-3) is **not changed by this REQ**: fences keep the literal `~/.claude/skills/partials/<name>.sh` fallback and the lint literal stays. In exchange, `install.sh` always installs `~/.claude/skills` as a symlink to the clone root even when `ADLC_HOME` points elsewhere, so that fallback resolves on every machine. Consumers' vendored `.adlc/partials/*.sh` **will** report `stale` in `/template-drift` because BR-1 changes partial bodies; that is correct and expected (REQ-610 BR-10 precedent), the stale copies keep working unchanged because every literal they carry still resolves (Rule A), and the CHANGELOG entry names the per-repo re-sync as the follow-up. Retiring the literal from fences is P1's `no-harness-path` work, not this REQ's. (informed by REQ-610, LESSON-441, LESSON-465)
- [ ] BR-4: What the four non-Claude harnesses are shown is a **skills-only view** of the clone: exactly the directories that contain a `SKILL.md`, and nothing else (no tools, partials, templates, workflows, presets, agents or `.adlc`). `install.sh` keeps that view current on every run, idempotently (REQ-519 BR-1): a newly added skill appears, a removed skill disappears, and a second run on a healthy machine reports zero actions. Where the view lives under `<adlc_home>` and how it is built (a directory of symlinks is the obvious shape) is an architecture decision.
- [ ] BR-5: `install.sh` makes the view reachable at `$HOME/.agents/skills` without destroying anything the user owns. The three starting states (absent, an existing symlink, an existing real directory with the user's own skills in it) each end with every toolkit skill reachable there and every pre-existing non-toolkit entry untouched; a toolkit skill whose name is already taken by a non-toolkit entry is skipped and reported, never overwritten. `--dry-run` names the starting state it found and the actions it would take. (informed by REQ-519 BR-1, BR-2)
- [ ] BR-6: `~/.claude/skills` and `~/.claude/agents` keep their current targets (clone root, `<clone>/agents`) and their current doctor checks. Nothing about Claude Code's mount changes. The toolkit's live-install contract (an edit to the clone is visible to every session without a publish step) holds for Claude Code exactly as today; for the four harnesses that read the view, a **newly added skill directory** becomes visible only after the next `install.sh` run, and doctor's `skills-view` check (BR-9) says so.
- [ ] BR-7: `adlc harness detect` is a new, read-only, pure-stdlib `adlc` subcommand (REQ-519 BR-11 data-driven dispatch; LESSON-395). For each of the five known harnesses it reports binary presence on PATH, the version string when the binary answers a version flag within a short timeout (otherwise `unknown`, never an error), and the mount state. Exit code is 0 whenever the command ran; absence of every harness is a result, not a failure. `--json` emits one object per harness with the HarnessProbe fields, for P2's `/init --harness` to consume.
- [ ] BR-8: `adlc doctor` gains `consumer-sync`: it enumerates git checkouts under `$ADLC_REPOS_ROOT` (the id-alloc default: the parent of the current repo's main worktree) that contain `.adlc/partials/`, compares each vendored `*.sh` against the clone's `partials/` by content, and reports per repo. Before comparing it establishes the baseline the way `/template-drift` Step 0a does (BUG-204): it names the clone's branch, dirty state and distance behind `origin/<default>`, compares against `git show origin/<default>:partials/<name>` when the checkout is not clean-and-current, and reports `unverified-baseline` rather than `stale` when neither is trustworthy. It never writes to any repo. (informed by BUG-204, BUG-203, LESSON-441)
- [ ] BR-9: Doctor's check registry gains three checks with REQ-519's pass/fail/skip semantics and copy-pasteable remediations (REQ-519 BR-4, BR-5): `skills-view` (every `*/SKILL.md` in the clone has a link in the view and no link dangles; remediation `./install.sh`), `agents-skills-mount` (`$HOME/.agents/skills` resolves to the view or contains the per-skill links; remediation `./install.sh`), and `consumer-sync` (FAIL naming each stale repo and file, with the per-repo remediation to run `/template-drift` there; SKIP when `$ADLC_REPOS_ROOT` holds no consumer). FAIL is deliberate: a stale vendored copy is the hazard that made relocation unsafe (plan finding C1, LESSON-441), and a doctor that stays green over it hides the one thing the check exists to show; `install.sh`'s closing doctor run therefore turns red on such a machine until the consumer is re-synced, which is the intended nag. The existing `claude-code` report-only check is generalized to one `harness:<name>` report-only check per known harness, each SKIP-never-FAIL when the binary is absent (REQ-519 open question 2, resolved the same way).
- [ ] BR-10: `install.sh --repair` and `--dry-run` cover the new surfaces exactly as they cover the existing symlinks: moving the clone and running `--repair` repoints every view link and the mount; `--dry-run` prints the view and mount plan and changes nothing. (informed by REQ-519 BR-3)
- [ ] BR-11: All new and changed shell is POSIX-sh, bash 3.2, zsh and dash safe and is executed under each by `partials/tests/run.sh`: no `case` inside `$( )`, no `\b` in `grep -E`, no bare `$<digit>`, no `local`, no `[[`, no `set -e` reliance across a fence, decimal normalization before arithmetic. New Python is stdlib only. (informed by LESSON-582, LESSON-395, LESSON-013, LESSON-335)
- [ ] BR-12: Documentation that states the install layout is updated in the same change: `README.md` (install model, the `cp ~/.claude/skills/presets/...` lines become `ADLC_HOME`-aware or point at the clone), `.adlc/context/architecture.md` and `conventions.md` (the home-resolution rule and the fence-spelling exception in BR-3), `tools/adlc/README.md` (new subcommand and checks), `CHANGELOG.md`. The rule in `conventions.md` says in one sentence why fences keep the literal while code reads the variable, so the next author does not "fix" one into the other. (informed by LESSON-019)
- [ ] BR-13: `tools/lint-skills` gains a check that fails when a **new** literal `~/.claude` or `$HOME/.claude` appears in `tools/`, `install.sh`, or a partial's *code* (not the REQ-610 fence spelling, not comments, not the two documented compatibility aliases), so the seam cannot silently close again. The existing `unguarded-source`, `cross-fence-*` and `arg-templating` checks are unchanged. (informed by LESSON-012)

## Acceptance Criteria

- [ ] AC-1: With `ADLC_HOME` unset, a fresh `./install.sh` on a machine with an existing healthy install reports zero actions apart from creating the SkillsView and the `~/.agents/skills` mount on the first run, and zero actions on the second run. Every pre-existing path (`~/.claude/skills`, `~/.claude/agents`, `~/.claude/adlc/config.yml`, `~/.claude/.global-next-*`, `~/.claude/delegate-venv`) is byte-identical before and after (`find -newer` / checksum verified). (BR-1, BR-4, BR-6)
- [ ] AC-2: `ADLC_HOME=/tmp/x ./install.sh` on a sandbox `HOME` creates the skills and agents symlinks, the machine config and the skills-only view under `/tmp/x`, **and** `~/.claude/skills` → clone root; `adlc doctor` under the same env passes; a partial fence extracted from a skill and run under `/bin/sh` with no `.adlc/partials/` present still sources the canonical copy through `~/.claude/skills/partials/`. (BR-1, BR-3)
- [ ] AC-3: `ADLC_HOME=relative/path adlc doctor` and `ADLC_HOME= adlc doctor` each exit non-zero with a message naming `ADLC_HOME`; neither falls through to `~/.claude`. (BR-2)
- [ ] AC-4: `ls -l ~/.agents/skills/` after install lists exactly the directories of the clone that contain a `SKILL.md`, each a symlink into the clone, and nothing else; adding a throwaway `zzz-test/SKILL.md` to the clone and re-running `./install.sh` adds the one link; removing it and re-running removes it. (BR-4)
- [ ] AC-5: With a pre-existing real directory `~/.agents/skills/` containing a user skill `mine/SKILL.md` and a decoy `spec/` directory that is not a symlink into the clone, `./install.sh` adds per-skill links for every toolkit skill except `spec`, reports `spec` as skipped (name taken), and leaves `mine/` untouched; `--dry-run` prints the same plan and changes nothing. (BR-5, BR-10)
- [ ] AC-6: `adlc harness detect` on a machine with only `claude` on PATH prints five rows, `claude` present with a version and `mounted`, the other four `absent` with mount `n/a`, exit 0; `--json` round-trips through `python3 -m json.tool`. On a sandbox PATH with a fake `codex` script that hangs on `--version`, the row reports `present` / `unknown` within the timeout and the command still exits 0. (BR-7)
- [ ] AC-7: On a sandbox `$ADLC_REPOS_ROOT` holding one consumer whose `.adlc/partials/forge.sh` is byte-identical to the clone's and one whose copy is an older revision, `adlc doctor --checks consumer-sync` FAILs naming the second repo and `forge.sh`, prints a remediation that runs `/template-drift` in that repo, and PASSes once the file is updated. With the clone checked out on a feature branch that differs from `origin/<default>` in `partials/`, the check names the baseline and compares against `origin/<default>`; with no remote reachable it reports `unverified-baseline` and does not assert `stale`. With no consumer under the root it SKIPs. (BR-8, BR-9)
- [ ] AC-8: `adlc doctor` lists `skills-view`, `agents-skills-mount`, `consumer-sync` and five `harness:<name>` checks; deleting one view link produces a `skills-view` FAIL whose remediation, run verbatim, returns it to PASS; absence of every non-Claude binary yields four SKIPs and a non-zero exit only if some other check failed. (BR-9)
- [ ] AC-9: Moving the clone and running `./install.sh --repair` repoints `~/.claude/skills`, `~/.claude/agents`, every view link and `~/.agents/skills`; `grep -r <old path>` over `~/.claude`, `~/.agents` and `~/bin` finds nothing. (BR-10)
- [ ] AC-10: `sh partials/tests/run.sh` exits 0 under bash 3.2, zsh, `/bin/sh` and dash (when installed) with the id-alloc, forge, lane-check and new home-resolution cases; `pytest tools/adlc/tests tools/lint-skills/tests` passes; `bash tools/lint-skills/check.sh` is clean and the new check fires on a fixture that introduces `$HOME/.claude` into a tool. (BR-11, BR-13)
- [ ] AC-11: In a consumer whose vendored `.adlc/partials/` predates this REQ, `/template-drift` reports the partials this REQ changed as `stale` and nothing else; a skill fence run in that consumer under `/bin/sh` and under zsh still sources the vendored copy and completes (the stale copy works); and the CHANGELOG entry names the re-sync as the follow-up. (BR-3)
- [ ] AC-12: README, architecture, conventions, tools/adlc README and CHANGELOG carry the new surfaces; `grep -n 'cp ~/.claude/skills' README.md` returns only lines that are correct under both the default and an overridden `ADLC_HOME`, or none. (BR-12)

## External Dependencies

- None new. `git` for the consumer-sync baseline and comparisons; `python3` (stdlib) for `adlc`; the existing harness binaries are probed, never required.

## Assumptions

- The five harness names and their binaries (`claude`, `copilot`, `codex`, `gemini`, `agent`) are the ones the multi-harness plan surveyed on 2026-10-27; Cursor's CLI installs as `agent` with a possible `cursor-agent` alias, and detect accepts either. Antigravity CLI is not probed here (plan §6.5).
- `$HOME/.agents/skills` is read by Copilot CLI, Codex, Gemini CLI and Cursor per their docs as of that date; this REQ does not verify discovery behaviour on any of them (plan §6.7 is answered structurally by exposing only the view, not by experiment).
- `$ADLC_REPOS_ROOT`'s default (parent of the current repo's main worktree, per `partials/id-alloc.sh`) is an adequate definition of "participating repos" for `consumer-sync`; a machine with consumers elsewhere sets the variable, as it already must for id derivation.
- The canonical fence spelling keeps the `~/.claude/skills` literal for at least this release; P1 decides when and how fences become `ADLC_HOME`-aware, together with its `no-harness-path` lint.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [x] ~~Should `consumer-sync` FAIL on a stale consumer, or be report-only like `harness:<name>`?~~ Resolved (2026-10-27, at validation): FAIL, recorded in BR-9 with the reason.
- [ ] Should the SkillsView also be the target of `~/.claude/skills` **when** `ADLC_HOME` is overridden (so a non-Claude machine has no clone-root mount at all), or must `~/.claude/skills` always be the clone root for the BR-3 fence fallback? Proposed: always the clone root; the fence fallback needs `partials/` under it.
- [ ] Which version flag each harness binary honours (`--version` vs `version`); detect should try the documented one per harness and treat any failure as `unknown`.

## Out of Scope

- Moving any file: counters, ledger, machine config, venv or symlink targets stay where they are. An opt-in, reversible `install.sh --migrate-home` is the plan's P7, not this REQ.
- Changing SKILL.md text in any way (the `$ARGUMENTS` prose, `!` lines, dispatch fallbacks, Teton retirement, description trims) — P1.
- The harness adapter framework, agent rendering to other formats, allowlist or hook rendering, `/init --harness`, `AGENTS.md` canonicalisation — P2 onward.
- Retiring the `~/.claude/skills` literal from the canonical fence spelling or from consumer-vendored partials — P1 (`no-harness-path`).
- Verifying skill discovery, trust, sandbox or allowlist behaviour on any non-Claude harness — the plan's §6 experiments.
- `/template-drift` changes; `consumer-sync` is a machine-level read-only report that points at `/template-drift`, it does not replace or extend it.
- Windows.

## Retrieved Context

- REQ-519 (spec, score 9): One-Command Installer and `adlc doctor` Health Check
- REQ-610 (spec, score 8): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- LESSON-582 (lesson, score 7): bash 3.2 cannot parse a `case` statement inside `$( )` — the shell that rejects your script is the oldest one a user has, not the newest one CI runs
- BUG-204 (bug, score 7): /template-drift treats the toolkit working checkout as canonical without checking which branch it is on — a stale baseline inverts every verdict and proposes regressions
- LESSON-395 (lesson, score 7): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up
- REQ-652 (spec, score 6): A lite lane for minor changes
- LESSON-663 (lesson, score 6): To keep a model's shell inside a classifier's grammar, allowlist what it may run — forbidding commands one at a time never converges
- BUG-230 (bug, score 6): /analyze Step 2 assumes an agent-dispatch tool Teton Code does not have, and Step 2a's hygiene shell would pin
- LESSON-662 (lesson, score 6): Some shell cannot be respelled past a provenance classifier — the skill text has to route around it
- BUG-201 (bug, score 6): The forge classifier has no pattern for branch-protection merge refusals, so both backends report them as error_class=network
- BUG-203 (bug, score 6): /template-drift compares only the checked-out branch, so in a promotion-pipeline repo it confidently reports the wrong answer
- LESSON-572 (lesson, score 6): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 6): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts
- REQ-546 (spec, score 6): Atomic remote id reservation at allocation time
- REQ-522 (spec, score 6): De-brand the delegation surface and make skill telemetry single-fence-safe
