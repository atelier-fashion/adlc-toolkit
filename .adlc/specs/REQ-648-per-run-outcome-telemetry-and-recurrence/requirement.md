---
id: REQ-648
title: "Per-run outcome telemetry: one record per pipeline run, sprint recurrence report, and an /analyze harness-fidelity dimension"
status: draft
deployable: true
created: 2026-10-26
updated: 2026-10-26
component: "adlc/sprint"
domain: "adlc"
stack: [bash, markdown, claude-skills, javascript, python]
concerns: [observability, knowledge-compounding, structural-enforcement, process]
tags: [telemetry, outcome-ledger, recurrence, harness-fidelity, analyze, sprint, pipeline-state, ghost-skip, harness2]
---

## Description

The toolkit runs many REQs under one version of its own harness — a `/sprint` is five
pipelines through the same skills, agents and partials — and keeps none of the outcome
evidence as countable data. Phase 5 findings exist only in the conversation (the
workflow journal holds `FINDINGS` payloads but discards them after consolidation); the
sprint summary's "Knowledge Captured" section is hand-written; the only persisted metric
on the machine is REQ-424's delegation telemetry, which records *whether* `adlc-read`
ran and nothing about what the run produced (LESSON-571 names this blind spot). When
three runners re-derived the same workaround in one sprint (LESSON-390), the signal was
a human noticing, after the fact.

Harness² cannot be copied per task — its runs are not idempotent and ours open PRs and
merge — but its Composer's weighing rule is copyable as stated: "a failure that repeats
across the base set is a real property of the base harness … a defect in 1/k is noise,
and an edit aimed at it is overfitting to one sample". The sprint *is* the toolkit's
base set; it only needs to be counted (research note §3.C).

This REQ adds one JSON-lines record per pipeline terminal — built by a **deterministic
reader** from fields the pipeline records, not by the model's recollection — into a new
log, separate from the delegation log. Three fields the pipeline does not record today
are added to `pipeline-state.json` first (`harness`, `validateAttempts`, `verify`). Two
readers consume the log: `/sprint`'s summary gains a **Recurrence** section computed by a
script, separating "seen in ≥2 REQs" (a harness property — candidate skill/lint change)
from "seen in 1/N" (noise — a `confidence: low` lesson at most), and `/analyze` gains a
`harness-fidelity` dimension beside `delegation-fidelity`, so "did 5.3.1's `/review`
change reduce Majors?" becomes a question with an answer. This is the toolkit's version
of Harness²'s sequential mode: the *next sprint is the probe* for the last harness edit.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| pipeline-state.json | `harness` | object | **new, additive, written at Step 0 before any pull**: `{ version: <VERSION file>, sha: <short sha of the clone ~/.claude/skills resolves to, or "-"> }` — recorded at run start because `/wrapup` Step 2 and `/sprint` Step 5 `git pull` the toolkit clone itself when the toolkit is the project under work |
| pipeline-state.json | `validateAttempts` | object | **new, additive**: `{ phase1: int, phase3: int }`, incremented at each validation attempt by `/proceed` (and by the workflow's gate loop via its state-write leaf) — `phaseHistory` holds one entry per *completed* phase and cannot yield retries |
| pipeline-state.json | `verify` | object | **new, additive**: `{ findings: [{severity, file, title, class, lessonId?, fixed: bool}], loops: int, consolidatedAt }`, written by Phase 5 Step B at consolidation, updated by Step C/D; read by nothing for control flow. **Written to the primary repo path's copy** (`<repos[primary].path>/.adlc/specs/…/pipeline-state.json`, the Step 8b target) — never only the worktree copy, which teardown deletes |
| Phase-5 finding | `class` | string | **reviewer-emitted** pattern name: `^[a-z0-9]+(-[a-z0-9]+){0,5}$` (e.g. `unanchored-marker-regex`), or `^LESSON-[0-9]{3,6}$` when matched, or `^title-slug:[a-z0-9-]+$` (tier 3). Validated by this regex in the workflow `FINDINGS` schema and by the emitter; **exempt from free-text redaction** because the format admits no credential shape |
| Phase-5 finding | `severity` | string | `Critical \| Major \| Minor \| Nit`. Agents that use other scales map on emission: `High→Major`, `Medium→Minor`, `Low→Nit`, `Critical` unchanged; `test-auditor` gaps default `Major` |
| RunOutcome (JSON line) | all keys | **flat scalars only** | JSON-lines, no nested objects, no arrays (REQ-424 BR-1/2). Integers are **quoted decimal strings or `-`** (the `duration_ms` precedent); the structural test checks exactly that |
| RunOutcome | `timestamp` | string | ISO-8601 Z |
| RunOutcome | `skill`, `step` | string | literals `proceed`, `run-outcome` |
| RunOutcome | `req`, `repo` | string | `REQ-xxx`; basename of the primary repo root, `.worktrees/` suffix stripped. One line per (req, repo-set) terminal; a cross-repo REQ is one line with `repo` = primary |
| RunOutcome | `engine` | string | enum `solo \| legacy \| workflow` |
| RunOutcome | `toolkit_version`, `toolkit_sha` | string | copied from `pipeline-state.json.harness` |
| RunOutcome | `terminal` | string | the REQ-474 `TERMINAL.state` vocabulary verbatim: `merged \| pr-ready \| blocked \| failed` |
| RunOutcome | `blocked_reason` | string | enum `validation-exhausted \| reflector-questions \| merge-conflict \| merge-unverified \| close-out-failed \| setup-error \| no-worktree \| no-pr \| other`, else empty. The workflow's free-text `reason`s are normalised to this enum by the emit leaf |
| RunOutcome | `validate_retries` | string | Σ over `validateAttempts.{phase1,phase3}` of `max(attempts − 1, 0)` — a phase that never ran contributes 0; three attempts at Phase 1 and none at Phase 3 ⇒ `"2"` |
| RunOutcome | `verify_loops` | string | `verify.loops` |
| RunOutcome | `findings_critical`, `findings_major`, `findings_minor`, `findings_nit` | string | counts from `verify.findings` |
| RunOutcome | `finding_classes` | string | comma-joined `class` per finding; empty when none. Each element already matches the class regex, so the join contains no comma inside an element |
| RunOutcome | `lessons_cited` | string | comma-joined ids acknowledged per REQ-647 (`Lessons:` trailers, `## Verification`); empty if REQ-647 absent |
| RunOutcome | `lessons_written` | string | comma-joined `LESSON-xxx` from the close-out, **or the literal `NO_ENTRY`**, or empty when no close-out ran. Readers special-case the literal |
| RunOutcome | `elapsed_s` | string | `startedAt` → terminal; spans any pause on a resumed run (documented, no reader depends on it) |
| Log file | path | — | `$ADLC_RUN_OUTCOMES_LOG`, default `~/Library/Logs/adlc-run-outcomes.log`; mode 0600, `umask 077`; a **separate file** from the delegation log so `check-delegation.sh`'s 9-key parser is untouched |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `harness_recorded` | `/proceed` Step 0 item 8 (state init), before the draft-PR push | `harness.{version,sha}` |
| `validate_attempted` | each `/validate` invocation at Phase 1 / Phase 3 (solo, legacy, workflow gate loop) | `validateAttempts.phaseN++` |
| `verify_consolidated` | `/proceed` Phase 5 Step B; the workflow's deterministic consolidation via a state-write leaf | `verify.findings` written |
| `run_outcome_emitted` | per the ownership table in BR-2 | one RunOutcome line |
| `recurrence_reported` | `/sprint` summary (legacy Step 6; new workflow-branch summary step) | per-class counts over the sprint's REQ list |
| `harness_fidelity_audited` | `/analyze` **Step 1.10** (after the existing Step 1.9 SKILL.md corruption audit) | window stats per `toolkit_version` |

_Permissions: not applicable._

## Business Rules

- [ ] BR-1 (**deterministic emitter**): the record is produced by `tools/delegate/run_outcome.py`, a Python reader (Python already lives in `tools/delegate/`) that takes the absolute path of the primary-path `pipeline-state.json`, the terminal and engine, derives every field from the state file, redacts free-text values with the delegate CLIs' existing credential-redaction function, and prints one flat JSON line. A thin POSIX wrapper `tools/delegate/emit-run-outcome.sh` locates it through `partials/delegate-tools-path.sh` and appends to the log with `umask 077`. The model never computes the fields (informed by LESSON-012; REQ-424 BR-1/2/4/5 for the record shape and privacy posture). `emit-telemetry.sh` is **not** modified; a parity test asserts the Python redaction and its `sed` chain agree on a fixture (informed by LESSON-441 — two copies drift; the test is the guard).
- [ ] BR-2 (**emission ownership — one line per terminal reached**):

  | engine | who emits | when |
  |---|---|---|
  | solo `/proceed` | the orchestrator | after Step 8b close-out for `merged`/`pr-ready`; **at each of the three halt points** for `blocked` (a later resume that reaches another terminal emits again; readers keep the latest line per `req`) |
  | legacy `pipeline-runner` | the runner | at its own terminal, after its Step 8b close-out when it owns the merge |
  | legacy `/sprint` orchestrator | the orchestrator | after it merges a cross-repo or fallback REQ and runs the close-out BUG-249 adds to Step 5 |
  | workflow engine | **one post-terminal leaf** dispatched by the script over the `healed` results, for every REQ regardless of terminal | after `unblockHeldReqs` — independent of BUG-249 (`lessons_written` is empty until close-out exists) |
  A crash, a thrown error or Ctrl-C emits nothing; the Recurrence denominator is therefore the **sprint's REQ list**, not the line count, and REQs without a line are shown as `no-record` (informed by REQ-424 BR-8 — emit after the artifact; LESSON-626 — the record is written by the actor at the moment of the event).
- [ ] BR-3 (**never blocks; harness skip**): every failure path degrades to one stderr line and continues; `tools/` stays un-vendored and is reached through the resolver (informed by REQ-433 BR-4/BR-7). On a provenance-classifying harness (BUG-228 class) the emit fence is skipped and the reply says `run-outcome skipped: provenance-classifying harness`; `tools/lint-skills`'s `harness-skip` check is extended to cover this fence (today it fires only on `adlc_delegate_gate_check` fences).
- [ ] BR-4 (**persist findings**): Phase 5 Step B writes the consolidated findings to `verify.findings` in the primary-path copy at the moment of consolidation, before Step C; Step C/D update `fixed` and `loops`. **`fixed` rule**: solo/legacy — set by Step C when the fix commit lands; workflow — a finding is `fixed` when it was in the blocking subset and is absent from the re-verify consolidation, non-blocking findings are `fixed: false` and the record's `engine` field lets a reader see the asymmetry. The workflow gains a state-write leaf at its consolidation and re-verify points (none exists today — `verify()` returns `true` and discards `consolidated`). Additive and optional; nothing reads it for control flow (informed by LESSON-626, BUG-212, BUG-193).
- [ ] BR-5 (**workflow terminal fidelity**): the post-terminal leaf copies `TERMINAL.state` into `terminal` verbatim and normalises `reason`/`detail.reason` into the `blocked_reason` enum (no second vocabulary for one fact — informed by REQ-474 BR-6, REQ-603 BR-3).
- [ ] BR-6 (**class**): a finding's `class` is, in order: (1) its `lessonId` when the finding matched a loaded lesson (REQ-647) — the strong signal; (2) the **reviewer-emitted `class`** — the `/review` finding format and the five reviewer agents plus the reflector gain a required `class` field naming the defect *pattern*, with the instruction to reuse a class already emitted in the same run when the pattern repeats, and the severity mapping in Entities; (3) `title-slug:<slug>` for a legacy prose finding lacking both. Every tier matches the class regex; the workflow `FINDINGS` schema gains `class` as **required** with that `pattern` (closed schema extended in the same change — informed by LESSON-331). Recurrence counts exact class equality and labels each row by tier. A slug of a free-form title is last because two reviewers describe one defect two ways; the regex is what keeps redaction (BR-1) from rewriting `task-…`/`risk-…` slugs into `[REDACTED]` and manufacturing false recurrences.
- [ ] BR-7 (**Recurrence — a script, not a recollection**): `tools/delegate/check-run-outcomes.sh --reqs REQ-a,REQ-b,… --recurrence` prints, for the latest line per listed REQ, `<class>\t<k>\t<N>\t<tier>` sorted by `k` desc, then `no-record` rows. `/sprint` runs it in legacy Step 6 **and in a new summary step on the workflow branch after `{results}` returns** (today that branch has no summary step). The summary renders rows with `k ≥ 2` under `harness property — consider a skill/lint/partial change` and `k = 1` under `single occurrence — lesson at most (confidence: low)` (informed by REQ-474 **BR-7** — consolidation is script code; LESSON-390).
- [ ] BR-8 (**/analyze Step 1.10 — harness-fidelity**): mirrors Step 1.8's shape: runs `check-run-outcomes.sh` (default 7-day window, `--window <N>d`, POSIX, no `jq`, BSD/GNU `date` as in `check-delegation.sh`) and reports per `toolkit_version`: run count, terminal mix, mean `validate_retries`, `verify_loops` rate, findings by severity, top recurring classes. Outcomes: script or log absent ⇒ skip **silently**; log present with 0 lines in window ⇒ `/analyze: harness-fidelity — no runs in <N>d window`; **corrupt** ⇔ >0 non-empty lines in window and 0 parsed ⇒ script exits 1 ⇒ `/analyze: harness-fidelity audit unavailable` and continue. Never fails-loud. The BUG-230 provenance-skip rule applies verbatim (informed by REQ-424 BR-6/BR-7/BR-10).
- [ ] BR-9 (**tests**): a pure structural test (pytest under `tools/delegate/tests/`, exit 5 on zero collected) validates an emitted line against the documented key list (every key present, scalar-only, quoted-decimal-or-`-` for counts, enums in vocabulary) and asserts a `task-ordering-race` class survives redaction unchanged; a fixture test for `check-run-outcomes.sh` covers the recurrence mode, `no-record`, the none-in-window line and the corrupt-log exit (informed by LESSON-331, LESSON-019).
- [ ] BR-10: `harness.{version,sha}` are read **once at Step 0** from the clone `~/.claude/skills` resolves to (`-` when unresolvable: no symlink, or a Teton/cloud environment) and never re-read; numeric fields are validated with `case "$v" in ''|*[!0-9]*)` before arithmetic in shell and `int()`-guarded in Python (informed by LESSON-441).
- [ ] BR-11: the wrapper and summariser are POSIX `sh` (no `set -eu` in sourced code, no `local`, no `[[`, no `mktemp -t`), BSD- and zsh-safe, sourced only via the canonical guarded spelling; the wrapper's harness is added to `partials/tests/run.sh`'s list and runs under bash, zsh, sh and dash (informed by REQ-610, LESSON-013, LESSON-020, LESSON-329, LESSON-335).
- [ ] BR-12: no new skill directory. Touches `proceed/SKILL.md` (Step 0 `harness`, Phase 1/3 `validateAttempts`, Phase 5 `verify`, Phase 8 emit, halt-point emits), `proceed/phases-1-3-validation.md`, `proceed/phases-6-8-ship.md`, `review/SKILL.md` (finding format gains `class`), the five reviewer agents and `agents/reflector.md` (`class` + severity mapping), `agents/pipeline-runner.md`, `workflows/adlc-sprint.workflow.js` (`FINDINGS` schema, state-write leaf, post-terminal emit leaf) + `workflows/README.md` + tests, `sprint/SKILL.md` (Step 6 + workflow-branch summary step), `analyze/SKILL.md` (Step 1.10), `tools/delegate/` (`run_outcome.py`, `emit-run-outcome.sh`, `check-run-outcomes.sh`, tests), `tools/lint-skills` (`harness-skip` extension), and `.adlc/context/architecture.md` ("Key cross-cutting dependencies" gains a run-outcome telemetry entry next to the delegation telemetry one).

## Acceptance Criteria

- [ ] A solo `/proceed` run reaching `merged` appends exactly one line, after Step 8b; it parses as flat JSON with every documented key, every count a quoted decimal string, `terminal: "merged"`, and `toolkit_sha` equal to the sha recorded at Step 0 even after `/wrapup` pulled the clone. (manual dogfood on the toolkit itself)
- [ ] A run that halts at Phase 1 after three failed validations appends one line with `terminal: "blocked"`, `blocked_reason: "validation-exhausted"`, `validate_retries: "2"`, empty `lessons_written`. (manual dogfood)
- [ ] After Phase 5 Step B, the **primary-path** `pipeline-state.json.verify.findings` lists every consolidated finding with a `class` matching the regex; after Step C, fixed findings carry `fixed: true`; the worktree copy's deletion at teardown does not affect the emitted counts. (manual dogfood)
- [ ] A state file without `harness`, `validateAttempts` or `verify` is processed by `/status`, `/proceed` resume and both sprint engines without error, and the emitter prints `-`/`0` for the derived fields rather than failing. (scripted for the emitter; benign path)
- [ ] `check-run-outcomes.sh --reqs REQ-1,REQ-2,REQ-3 --recurrence` on a fixture where two REQs carry `LESSON-390` and one has no line prints `LESSON-390\t2\t3\tlesson`, then the unique classes with `1`, then `REQ-3\tno-record`. (fixture test)
- [ ] The same mode on a fixture where two REQs' reviewers emitted `class: cross-fence-shell-state` prints `cross-fence-shell-state\t2\t3\treviewer`; a legacy finding appears as `title-slug:…`. (fixture test)
- [ ] A `FINDINGS` payload carrying `class: "task-ordering-race"` validates against the exported workflow schema; one missing `class` or with `class: "Task Ordering"` is rejected. (pure structural test)
- [ ] The emitted line for a finding classed `task-ordering-race-in-fixture` contains that exact slug; the parity test shows the Python redaction and `emit-telemetry.sh`'s `sed` chain agree on a fixture of credential-shaped strings. (tests)
- [ ] `/analyze` with ≥1 line in the window prints a `harness-fidelity` block grouped by `toolkit_version` with the Step-1.10 heading; with no log file prints nothing for the dimension and exits 0; with a log present but empty in the window prints the `no runs` line; with a corrupt log prints the unavailable line and continues. (fixture tests for the script; manual for `/analyze`)
- [ ] `check-delegation.sh` output is byte-identical before and after this REQ on the same delegation log; `emit-telemetry.sh` is unchanged. (`git diff` + fixture)
- [ ] The log file is created with mode 0600; a free-text value containing `ghp_` + 36 chars is written as `[REDACTED]`. (test)
- [ ] On a provenance-classifying harness fixture, the Phase 8 emit fence is skipped and the reply contains `run-outcome skipped: provenance-classifying harness`; `tools/lint-skills` flags a copy of the fence that lacks the skip rule. (lint test)
- [ ] Every reviewer agent definition and `review/SKILL.md` document the `class` field and the severity mapping. (grep)
- [ ] `tools/lint-skills` passes; `pytest` collects > 0 in `tools/delegate/tests`; `partials/tests/run.sh` output lists the wrapper harness with executed cases > 0.

## External Dependencies

- None (Python 3 is already required by `tools/delegate/`).

## Assumptions

- A per-run record of ~20 scalar fields is small enough that log rotation is unnecessary for this epoch (REQ-424 made the same call). Rotation is a later REQ.
- `lessons_cited` depends on REQ-647's acknowledgement trailers; absent, it is empty.
- **REQ-647 is a soft prerequisite for the Recurrence report's strong signal.** Without it no finding carries a `lessonId`, so recurrence rests on reviewer-emitted classes (tier 2). The report is still produced and labels each row by tier.
- **BUG-249 is not a prerequisite.** The workflow engine's post-terminal emit leaf runs whether or not close-out exists; `lessons_written` is empty until it does.
- The research note's draft record used a nested `findings` object and read the toolkit sha at run end; both are superseded by this spec.

## Open Questions

- [ ] REQ-603 noted the delegation log's `api-error` reason is overloaded and said the split "belongs to whatever REQ takes up telemetry". Different log, different readers — default: out of scope (below).
- [ ] Should Recurrence also join bug files' `introduced_by` (REQ-593) to show "REQs in this sprint that later caused a bug"? Natural join key, but it is a cross-sprint derive-at-read report, not a per-sprint one.

## Out of Scope

- Splitting the delegation log's `api-error` reason (REQ-603's deferred item).
- Automatic harness edits from recurrence counts — the `/harness-reflect` follow-up (research note item E) consumes this REQ's output.
- An always-on prose budget lint (research note item D).
- Log rotation, cross-machine aggregation, dashboards.
- Any change to what Phase 5 reviewers look for or how findings are fixed — only their persistence, `class` and severity vocabulary change.
- The Step 8b close-out itself — BUG-249.

## Retrieved Context

- LESSON-626 (lesson, score 9): A rule written about one actor does not settle the case for another — bound machine conflict resolution to a checkable property
- BUG-212 (bug, score 9): A conflict resolved during a pipeline run leaves no machine-readable trace
- REQ-474 (spec, score 9): Re-platform /sprint orchestration onto Claude Code Dynamic Workflows
- LESSON-019 (lesson, score 9): A literal-presence guard silently rots when the thing it guards moves behind indirection
- LESSON-020 (lesson, score 9): A shell function shared across SKILL.md steps must be a sourced partial, not a cross-block definition
- LESSON-571 (lesson, score 8): A retrieval filter is half of a read/write contract with whatever writes the field it filters on
- BUG-194 (bug, score 8): /spec Step 1.6 spec-corpus status filter admits no status the pipeline ever writes
- REQ-485 (spec, score 8): Auto-rebase and resume a blocked REQ after its blocker merges
- REQ-433 (spec, score 8): Kimi telemetry global-fallback resolver — make delegation telemetry work in downstream repos
- LESSON-012 (lesson, score 8): Prose-only 'do this' instructions inside skill markdown are honor-system enforcement
- REQ-593 (spec, score 7): Incident→REQ backlink: attribute a BUG to the REQ that shipped its cause
- LESSON-331 (lesson, score 7): Closed output schemas silently rot when a new code path adds payload fields
- REQ-424 (spec, score 7): Skill-delegation telemetry: detect ghost invocations
- LESSON-003 (lesson, score 7): Sprint dispatch must declare each pipeline-runner's worktree path
- REQ-263 (spec, score 7): Enforce per-REQ unique worktree paths in /sprint dispatch and /proceed Phase 0
