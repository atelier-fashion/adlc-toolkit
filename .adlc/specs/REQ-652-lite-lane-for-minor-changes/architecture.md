# REQ-652 Architecture — the lite lane

## Approach

The lane is a **value the existing pipeline reads**, not a second pipeline. The
precedent is single-repo vs cross-repo in `/proceed`: one code path, which branches
where the value says so (`proceed/SKILL.md` "there is no separate code path"). No new
skill directory is created (conventions.md, "What NOT to do").

```
/spec ── strip --lite/--full ── Step 1.4 intake ── Step 1.6 retrieval ── Step 1.7 TRIAGE ── Step 2 alloc id ── Step 3 write
                                                                         │ lane, lane_reason, lane_forced
                                                                         ▼
/proceed Step 0 ── reads lane (absent ⇒ full) ── lane block in state ── lite: status approved
   │
   ├─ full:  Phase 1 → 2 → 3 → 4 (tasks) → 5 (reflector + panel) → 6 → 7 → 8          (unchanged)
   │
   └─ lite:  Phases 1–3 recorded skipped → 4L implement from ACs → gates → 5L lite review
             → LANE CHECK → 6 (PR ready, Lane line) → 7 (+ re-check if commits) → 8 (+ re-check)
                  │ any failure, reversal finding, implementer finding, or --full
                  ▼
             ESCALATE: spec lane "full" + lane_escalated; state lane.escalations[]; completedPhases ⇒ [0];
                       resume at Phase 1 on the same branch, worktree and PR
                  │ forced lite + solo: HALT (4th halt) → escalate, or keep lite ⇒ lane.overrides[]
```

## Data model

**Spec frontmatter** (durable, committed — `pipeline-state.json` is gitignored, so the
spec is the record that travels):

```yaml
lane: "lite"                     # "lite" | "full"; absent ⇒ full
lane_reason: "one component, copy only, no schema or config"
lane_forced: false               # true when --lite/--full chose it
lane_escalated: "2026-10-28 — blocked-path: packages/domain/src/page.ts"   # only after escalation
```

Every string value is quoted. `/spec` Step 1.6 drops any candidate whose frontmatter does
not parse, and an unquoted `: ` inside `lane_reason` or `lane_escalated` would do exactly
that, silently.

**`pipeline-state.json`** gains one additive, optional object, with the same "absent reads
as …" wording as `closeOut` and `conflictsResolved`:

```json
"lane": {
  "initial": "lite",
  "current": "lite",
  "forced": false,
  "skippedPhases": [1, 2, 3],
  "escalations": [ { "at": "…", "phase": 5, "trigger": "blocked-path", "detail": "…", "actor": "solo" } ],
  "overrides":   [ { "at": "…", "phase": 6, "triggers": ["max-files"], "actor": "operator" } ]
}
```

It sits beside `phase4` at the top level, never inside `repos` and never carrying a
`primary` or `prNumber` key, so `/architect`'s line-based footprint awk is unaffected.

**`.adlc/config.yml`** (optional; absent ⇒ defaults):

```yaml
lanes:
  lite:
    max_files: 3
    blocked_paths: ["packages/domain/**", "services/api/src/schemas/**"]   # added to the defaults
    count_exclude: ["content/**"]                                          # added to the defaults
    deploy_units:
      "apps/website/**": website
      "apps/admin/**": admin
```

Project lists **extend** the defaults rather than replacing them. A project cannot quietly
unblock `.github/**` by declaring its own list.

**Vocabulary.** These are the closed sets, defined once in `partials/lane-check.md` inside a
`<!-- lane-vocabulary -->` block that the lint reads:

| Set | Values |
|---|---|
| lane | `lite`, `full` |
| trigger | `blocked-path`, `dependency`, `deploy-units`, `max-files`, `check-error`, `implementer`, `reversal`, `operator` |
| actor | `solo`, `sprint-runner`, `operator` |
| lane_check | `pass`, `escalate`, `error` |

## Key decisions

**ADR-1 — The lane lives in the spec; the state only records the run.** The spec
frontmatter is the authority on which lane a REQ is in. `pipeline-state.json` records what
this run did with it. Absent means `full` in every reader (BR-12), so all 52 existing specs
and every in-flight state file keep their behavior. *Rationale:* state files are gitignored
and machine-local; a lane recorded only in state would vanish on another machine
(integration finding §1).

**ADR-2 — Triage is `/spec` Step 1.7, after retrieval and before id allocation.** Triage
needs Step 1.6's retrieved REQs and lessons for the "reverses a recorded decision" criterion,
and BR-4's `--lite --full` error must fire before Step 2 burns an id (the REQ-594 ordering
precedent). The flags are stripped at **Input**, before Step 1.4: `adlc_intake_detect` reads
the raw argument and would otherwise count the flags as request text. Triage is a judgment
against BR-2's list; when it is unsure it writes `lite` and says so in `lane_reason` (BR-3).

**ADR-3 — The lane check is Python behind a sourced partial.** The check needs nested config
(`blocked_paths` lists, the `deploy_units` mapping), and shell YAML parsing is what REQ-515
ADR-3 and REQ-609 rejected. `tools/adlc/lane_check.py` reads `lanes.lite` through the shared
loader (`tools/delegate/_machine_config.py`, the same one `forge_config.py` adapts), diffs
`origin/<integrationBranch>...HEAD` (LESSON-391, never local `main`), and matches globs with
`fnmatch`. `partials/lane-check.sh` exposes `adlc_lane_check <worktree> <base-ref>`, resolving
the interpreter with forge.sh's `_adlc_forge_python` so the two never pick different Pythons.
That cross-partial call is a known coupling; extracting the resolver into its own partial is a
follow-up, not this REQ.

- **Contract** (the conflict-bound and forge precedents): rc `0` pass, `1` escalate, `2` error.
  Normalized output, one fact per line (LESSON-572):
  - `lane_check=<v>` and `files_counted=<n>`
  - then one `trigger=<t>` / `detail=<path-or-reason>` pair per failing fact
- **An error is not a pass** (LESSON-581). A dirty tree, a git failure, or a config that has a
  `lanes:` key but cannot be loaded (for example no PyYAML on that interpreter) yields
  `lane_check=error`, `trigger=check-error`. `/proceed` treats it as an escalation, which is the
  conservative direction. A config without a line-start `lanes:` key is never loaded at all,
  so a missing PyYAML costs nothing there.
- **Defaults**, extended (never replaced) by project lists:
  - `blocked_paths`: CI (`.github/**`, `.gitlab-ci.yml`, `.circleci/**`, `azure-pipelines.yml`), deploy and infra (`deploy/**`, `infra/**`, `infrastructure/**`, `terraform/**`, `**/*.tf`, `**/Dockerfile`, `**/docker-compose*.yml`, `**/cloudbuild*.yaml`), data (`**/migrations/**`, `**/*.sql`, `**/*.proto`, `**/openapi*.*`, `**/schema*/**`), security (`**/auth/**`, `**/security/**`, `**/*.rules`, `firestore.rules`, `**/.env*`), and pipeline config (`.adlc/config.yml`, `.claude/settings*.json`)
  - dependency files: lockfiles (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Gemfile.lock`, `poetry.lock`, `uv.lock`, `Cargo.lock`, `go.sum`, `Package.resolved`, `Podfile.lock`, `composer.lock`) and manifests (`package.json`, `pyproject.toml`, `requirements*.txt`, `Gemfile`, `Cargo.toml`, `go.mod`, `Package.swift`, `Podfile`, `build.gradle*`, `composer.json`)
  - `count_exclude`: test paths (`**/test/**`, `**/tests/**`, `**/__tests__/**`, `**/*.test.*`, `**/*.spec.*`, `**/test_*.py`, `**/*_test.*`), `.adlc/**`, `CHANGELOG*`
  - `max_files`: `3`

  A changed file that is excluded from the count is still checked against `blocked_paths`
  and the dependency files.

**ADR-4 — A lite run writes `approved` at Step 0.** The lite path skips both writers of
`approved` (Phase 1 and `/architect` Step 6), and a lite REQ left in `draft` would be invisible
to `/sprint` and excluded from `/spec` retrieval (BR-18). `proceed/SKILL.md` gains a
`lifecycle-write` declaration, and `tools/lint-skills`' `LIFECYCLE_WRITE_SITES` gains
`proceed/SKILL.md` so the BUG-194 parity check covers the new writer.

**ADR-5 — The skipped phases go through the Gate Protocol, not around it.** A lite run
appends phases 1, 2 and 3 to `completedPhases` with `phaseHistory` entries carrying
`"skipped": "lite"`, and lists them in `lane.skippedPhases` (AC-3). The rule "the previous
phase is in `completedPhases`" therefore holds unchanged. Phase 4 and Phase 5 keep their
numbers and run their lite variants.

- **Escalation** keeps `phaseHistory` append-only, adds an `{ "event": "escalated" }` entry,
  trims `completedPhases` to `[0]`, resets `phase4`, sets `currentPhase` to 1, and keeps
  `repos` untouched (same branch, worktree, PR).
- **The PR is not returned to draft.** The forge adapter has no draft-revert for Azure
  DevOps. Instead, escalation edits the PR body with an "Escalated to full lane" line, and
  Phase 6 rewrites the body when it runs again.

**ADR-6 — The lite lane implements in the orchestrator, from the acceptance criteria.**
There are no task files and no `task-implementer` dispatch. The orchestrator implements in
its own context in both modes, and commits as `<type>(<scope>): … [REQ-xxx]`, which
conventions.md already allows. "The implementer" in BR-9 is therefore the orchestrator. A
finding that the change needs something BR-2 excludes escalates with trigger `implementer`.

**ADR-7 — One review agent: `lite-reviewer`.** It is a new agent that covers the five
dimensions in one read-only pass, plus a per-BR/AC met / partial / unmet table (LESSON-330:
the panel's real catch is the omitted rule) and a reversal check. In main mode it is one
dispatch. In subagent mode its checklist runs inline, as the panel's checklists already do.

- **Inputs:** the diff against `origin/<integrationBranch>`, the spec, and the fresh
  retrieval set (ADR-8).
- **Findings** are fixed in one consolidated pass, as in Phase 5.
- **A reversal finding escalates** (trigger `reversal`). A machine may make this judgment
  because it only ever adds scrutiny; LESSON-626 bounds machine permissions that would remove it.
- **The delegate pre-pass does not run on lite.** No skill flag is created for it, so no
  `proceed-phase-5` telemetry record is written and none can be counted as a ghost-skip.
- **Registration:** `lite-reviewer` is added to `tools/adlc/agents_render.py`'s
  `_SHIPPED_DEFAULTS` at the same tier as `correctness-reviewer`.

**ADR-8 — Fresh retrieval at implementation time is the cheap form.** Before implementing,
the lite path greps `.adlc/knowledge/lessons/`, `.adlc/specs/*/requirement.md` and
`.adlc/bugs/` for frontmatter matching the REQ's `component` or `domain`, plus the 20
most-recent lessons by mtime (LESSON-604's prescription). It does not delegate and has no
telemetry. REQ-647 (draft) generalizes per-phase retrieval and may replace this.

**ADR-9 — Forced lite: halt when someone is present, escalate when no one is.** A failed lane
check on a REQ with `lane_forced: true` halts a solo run with a numbered question (escalate or
keep lite). This is the fourth halt in the Autonomous Execution Contract.

- **"Keep lite"** appends to `lane.overrides[]`. A later check whose failing triggers are all
  already overridden does not halt again (BUG-212: write the record at the moment of the
  decision).
- **Unattended** means subagent mode. `pipeline-runner` is told it is unattended in its launch
  prompt, and it escalates instead of halting (BUG-207, LESSON-626).
- **A triaged lite REQ** never halts on the check; it escalates (BR-7).

**ADR-10 — `--full` is `/proceed`'s first flag.** The model reads it from `$ARGUMENTS`, strips
it before REQ-id normalization (the `/wrapup --close-out` precedent), and documents it in a new
`argument-hint`. On a lite REQ it escalates with `actor: operator`, before Phase 4 or at the
point of resume. On a full REQ it is a no-op that logs one line.

**ADR-11 — The `/sprint` workflow engine runs lite REQs on the full lane.** The engine's
phases are a fixed script. Its preflight returns each REQ's `lane`, and the run logs one line
per lite REQ (BR-16, AC-13). It writes no `lane` object to state, so `/status` correctly shows
full. The notice builder lives in the script's pure block so `workflows/tests/helpers.test.js`
can test it. The legacy engine inherits the lite lane through `pipeline-runner` running
`/proceed`.

**ADR-12 — `/wrapup` turns each escalation into a `kind: process` lesson** through Step 4's
existing write point and `adlc_lesson_check`. It cites the `lane.escalations` entry, or the
spec's `lane_escalated` when state is unavailable. The byte-identical capture-rules block and
the delegated `--question` rule lines are not edited (lint parity). An escalated REQ that never
reaches `/wrapup` (blocked or failed) is visible in `/status`'s lane column; capturing a lesson
for it is out of scope.

**ADR-13 — Lint covers the vocabulary across every writer and reader.** A new
`lane-vocabulary` check reads the `<!-- lane-vocabulary -->` block, which is anchored to the
start of a line (LESSON-404). It then scans the declared writer and reader sites for `lane`
values and trigger names outside the block:

- the skills: `spec`, `proceed` (with its `phase*.md` companions), `wrapup`, `status` and `sprint`
- `agents/pipeline-runner.md`
- `workflows/adlc-sprint.workflow.js`
- `templates/requirement-template.md`

The site list is an explicit tuple, so deleting a declaration is itself a finding (the
`LIFECYCLE_WRITE_SITES` precedent).

## Verification gates for this REQ

This repo has no CI. "The gates" means running these from the worktree root:

- `python3 -m pytest tools/adlc/tests tools/lint-skills/tests -q`
- `sh partials/tests/run.sh` (bash, zsh, sh and dash)
- `node --test 'workflows/tests/*.test.js'`
- `sh tools/lint-skills/check.sh --root .`, which must report `scanned 17 SKILL.md file(s)` (or more) and zero findings

## Proposed additions to `.adlc/context/architecture.md`

- A **Lanes** entry under "Key cross-cutting dependencies": where the lane lives (ADR-1), the
  lane check's contract and defaults (ADR-3), and escalation (ADR-5).
- The pipeline-shape diagram gains the lite branch.
- The workflow-engine paragraph notes that it runs lite REQs on the full lane (ADR-11).

## Follow-ups (not this REQ)

- Phase 5's existing `git diff main...HEAD` sites (`proceed/SKILL.md` ~L360, ~L394, ~L430) contradict LESSON-391 on the full lane too. File as a bug.
- Extract the Python-interpreter resolver out of `forge.sh` into its own partial (ADR-3).
- Add embolden-website's `lanes.lite` block (`packages/domain/**`, API schemas, `deploy/**`) when its issue skill is built.
