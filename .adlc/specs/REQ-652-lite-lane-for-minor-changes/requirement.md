---
id: REQ-652
title: "A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise"
status: approved
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "sh"]
concerns: ["cost", "developer-experience", "verify-quality", "structural-enforcement"]
tags: ["lite-lane", "triage", "proceed", "spec", "verify", "review-panel", "escalation", "wrapup", "pipeline-phases"]
---

## Description

ADLC has two ways to change a project. `/proceed` is the full pipeline: validate the spec, architect and break into tasks, validate the architecture, implement, verify with the reflector plus a five-agent review panel, open the PR, clean up and wait for CI, wrap up. `/bugfix` is the short pipeline, but it is scoped to defects. A small change request that is not a bug, such as a copy edit, a spacing adjustment or turning a logo ten degrees, has to go through the full pipeline. Most of that run's cost goes to architecture, two validation passes and six review agents, for a change one reviewer could judge.

The cost is felt most where small requests arrive in volume. Embolden's website receives its designer's feedback as GitHub issues, often ten at a time, and the plan is to work them in parallel sessions. At full-pipeline cost, those parallel sessions mostly multiply the overhead.

The obvious shortcut has already failed once. In embolden-website, a batch of ten "small" issues went straight to code in one PR (recorded after the fact as REQ-641). It shipped a new domain field across the API, admin and website, and a change to an earlier REQ's layer order. It left no spec, no review and no record. So a fast path must keep three things: the record (a REQ), the gates (build, lint, test, CI) and a review.

This REQ adds a **lite lane** with a single entry point, so the operator never has to classify a change themselves:

- `/spec` triages every request into `lane: lite` or `lane: full` and records the reason in the spec.
- `/proceed` reads the lane. On the lite lane it skips architecture, task breakdown and the two validation passes, and it runs one review pass in place of the reflector and the five-agent panel.
- Before the PR, a mechanical check of the actual diff confirms the change stayed small and stayed out of risky areas. If it did not, the REQ escalates to the full lane. The spec and the code written so far carry over.
- `--lite` and `--full` at `/spec` override the triage. `--full` at `/proceed` escalates by hand.
- Every escalation is recorded and becomes a lesson, so the triage rules can be tuned from evidence.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Requirement frontmatter | `lane` | enum `lite` \| `full` | Written by `/spec`. Absent means `full`, so every existing spec keeps its behavior. |
| Requirement frontmatter | `lane_reason` | string | One line: why triage chose the lane, or `forced by --lite` / `forced by --full`. |
| Requirement frontmatter | `lane_forced` | boolean | `true` when the lane came from a flag rather than triage. Absent means `false`. |
| Requirement frontmatter | `lane_escalated` | string | Set only on escalation: `<ISO date> — <trigger>: <detail>`. `lane` is rewritten to `full` at the same time. Every lane string value is quoted, because unquoted `: ` makes the frontmatter unparseable and drops the spec from retrieval. |
| `pipeline-state.json` | `lane` | object `{ initial, current, forced, skippedPhases: [], escalations: [], overrides: [] }` | `initial` and `current` are `lite` \| `full`. `skippedPhases` lists the phases a lite run did not run (AC-3). Additive and optional: a state file without the key reads as `full`. |
| `pipeline-state.json` | `lane.overrides[]` | object `{ at, phase, triggers: [], actor }` | Appended when the operator answers BR-8's halt with "keep lite". A later lane check whose failing triggers are all already overridden does not halt again. |
| `pipeline-state.json` | `lane.escalations[]` | object `{ at, phase, trigger, detail, actor }` | Appended when the escalation happens, before the pipeline continues (informed by BUG-212). `actor` is `solo` \| `sprint-runner` \| `operator`. |
| Lane check result | per-rule fields | normalized `key=value` lines, e.g. `lane_check=escalate`, `trigger=blocked-path`, `detail=packages/domain/src/page.ts` | Machine-consumed, one field per fact, no prose remediation (informed by LESSON-572). |
| `.adlc/config.yml` | `lanes.lite` | object | Optional project overrides: `max_files`, `blocked_paths` (globs), `count_exclude` (globs not counted toward `max_files`), `deploy_units` (glob → unit id). Named `deploy_units` so it is not confused with the existing `deployable` frontmatter boolean. Absent means toolkit defaults. |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `lane_triaged` | `/spec` writes a new REQ | lane, reason, forced flag |
| `lane_escalated` | The diff check fails, the implementer finds the change crosses a line mid-implementation, or the operator runs `/proceed --full` on a lite REQ | phase, trigger, detail, actor |
| `lane_escalation_halt` | The diff check fails on a REQ whose lite lane was **forced**, in a solo run | the failing rules, for the operator to decide |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Force a lane at `/spec` (`--lite`, `--full`) | operator |
| Escalate lite → full automatically | `/proceed` (solo or sprint runner), only on a failed mechanical check or a stated mid-implementation finding |
| Escalate by hand (`/proceed --full`) | operator |
| De-escalate full → lite | nobody in this REQ (out of scope) |

## Business Rules

- [ ] BR-1: `/spec` assigns every new REQ exactly one lane and writes `lane` and `lane_reason` to its frontmatter. The operator is never asked to choose.
- [ ] BR-2: A request goes to the full lane if triage finds evidence that **any** of the following fails; otherwise it qualifies for the lite lane:
  - no change to a domain schema, API contract, validator or data model
  - no change to auth, security, secrets, deploy, CI or infrastructure
  - exactly one deployable and one repo (cross-repo REQs are always `full`)
  - no new or upgraded dependency
  - a footprint of at most `max_files` source files (default 3). Tests and the REQ's own `.adlc/` files do not count, and changed lines are not counted at all
  - no reversal of a decision recorded in an existing REQ or lesson for the same component, judged against Step 1.6's retrieved context
- [ ] BR-3: When triage cannot tell whether a criterion in BR-2 holds, it chooses `lite` and says so in `lane_reason`. A wrong lite start is caught by BR-6 at the cost of one escalation; a wrong full start costs the whole full pipeline.
- [ ] BR-4: `--lite` and `--full` at `/spec` override triage and set `lane_forced: true`. They are mutually exclusive; passing both is an error before any REQ id is allocated.
- [ ] BR-5: On a lite REQ, `/proceed` runs, in order:
  - Step 0 (worktree, state, draft PR on first commit, per LESSON-390)
  - a fresh retrieval for the surfaces about to be touched (informed by LESSON-604)
  - implementation straight from the spec's acceptance criteria, with no task files
  - the project's build, lint and test gates
  - one review pass covering correctness, quality, test coverage, security, acceptance-criteria coverage, and any reversal of a decision in the REQs and lessons that the fresh retrieval returned, with its findings fixed in one consolidated pass as in Phase 5
  - the lane check (BR-6), on the diff as it stands after those fixes
  - PR, cleanup and CI
  - wrapup

  It skips Phase 1 (spec validation), Phase 2 (architect and tasks), Phase 3 (architecture validation), the reflector and the five-agent panel.
- [ ] BR-6: Before the PR leaves draft, the lite lane runs a **mechanical** check of the final diff against the integration branch, and runs it again before merge if commits landed after it (for example CI fixes in Phase 7). Every rule is decided by a property a machine can check, not by judgment (informed by LESSON-626):
  - changed paths against `blocked_paths`
  - lockfile and manifest dependency changes
  - the number of deploy units touched, when `deploy_units` is declared
  - the number of changed source files against `max_files`

  It emits one normalized field per rule. Any failing rule means the change crossed a line.
- [ ] BR-7: When BR-6 finds a crossed line on a lite REQ whose lane was **triaged**, `/proceed` escalates automatically and continues without asking.
- [ ] BR-8: When BR-6 finds a crossed line on a REQ whose lane was **forced** with `--lite`:
  - **solo `/proceed`:** halts, lists the failing rules, and asks the operator to escalate or keep lite. This is a fourth legitimate halt point in the Autonomous Execution Contract.
  - **unattended sprint runner:** escalates automatically, because no operator is present to ask (informed by BUG-207, LESSON-626).
- [ ] BR-9: The implementer may escalate mid-implementation when it finds the change needs something BR-2 excludes, e.g. a new field. It records the finding as the escalation's `detail`.
- [ ] BR-10: Escalation is lossless. It does all of the following before the pipeline continues:
  - rewrites the spec's `lane` to `full` and sets `lane_escalated`
  - appends to `pipeline-state.json` `lane.escalations`
  - resumes `/proceed` at Phase 1 on the same branch, worktree and draft PR

  The spec is kept, and Phase 2 architects around the code already written rather than discarding it.
- [ ] BR-11: `/proceed --full REQ-xxx` on a lite REQ escalates before Phase 4 starts, or at the point it is invoked on resume, recording `actor: operator`.
- [ ] BR-12: A spec with no `lane` field runs the full lane unchanged. Every reader treats absent as `full` (informed by LESSON-571: one defined meaning for the empty case).
- [ ] BR-13: The lite lane's PR body states the lane and `lane_reason`, so a human reviewer knows the change skipped architecture and the review panel.
- [ ] BR-14: `/wrapup` records a lesson for every REQ that escalated. The lesson names the trigger, the triage reason that was wrong, and the rule that should change. Triage is tuned from these lessons, not from guesswork.
- [ ] BR-15: `/status` shows each in-flight REQ's current lane and whether it escalated.
- [ ] BR-16: The `/sprint` legacy engine inherits the lite lane through `/proceed`. The `/sprint` workflow engine runs a lite REQ on the full lane and logs one line saying so, until it has a lite path of its own.
- [ ] BR-17: The lane vocabulary (`lite`, `full`) is defined once. Every writer and reader of `lane` uses only those values (`/spec`, `/proceed`, `/wrapup`, `/status`, `/sprint`), enforced by a `tools/lint-skills` check rather than by prose (informed by LESSON-019, LESSON-571).
- [ ] BR-18: `/proceed` writes `status: approved` on a lite REQ at Step 0, because the phases that normally write it (Phase 1 and `/architect`) do not run. A lite REQ must not stay `draft`, which would hide it from `/sprint` and from `/spec` retrieval.

## Acceptance Criteria

- [ ] AC-1: A request triaged as lite produces a spec with `lane: lite` and a `lane_reason`. A request that names a schema or API change produces `lane: full` with a reason naming that criterion.
- [ ] AC-2: `/spec --lite <request>` writes `lane: lite` and `lane_forced: true` even for a request triage would call full. `/spec --full` does the reverse. `/spec --lite --full` errors without allocating a REQ id.
- [ ] AC-3: `/proceed` on a lite REQ completes without writing task files and without running Phases 1–3, the reflector or the five-agent panel. `pipeline-state.json` records `lane.initial: lite` and the phases it actually ran.
- [ ] AC-4: On a lite REQ, the lane check reports one normalized field per rule. A diff touching a `blocked_paths` glob, a lockfile, or more source files than `max_files` reports `lane_check=escalate` with the trigger, with fixture coverage of both a passing and a failing diff for each rule.
- [ ] AC-5: A triaged-lite REQ whose diff fails the lane check escalates without asking: spec `lane: full` plus `lane_escalated`, an entry in `lane.escalations`, and `/proceed` resumes at Phase 1 on the same branch and PR with the implementation still present.
- [ ] AC-6: A forced-lite REQ whose diff fails the lane check halts in a solo run with the failing rules listed as a numbered question, and escalates without halting under a sprint runner.
- [ ] AC-7: `/proceed --full` on a lite REQ escalates and records `actor: operator`.
- [ ] AC-8: An existing spec with no `lane` field runs the full pipeline with no change in behavior.
- [ ] AC-9: The lite review pass is handed the REQs and lessons from a retrieval run at implementation time (not only the spec's frozen Retrieved Context), and a finding that the change reverses a recorded decision escalates the REQ (trigger `reversal`).
- [ ] AC-10: The lite PR body carries the lane and its reason.
- [ ] AC-11: `/wrapup` on an escalated REQ writes a lesson naming the trigger and the triage rule to change. On a REQ that stayed lite, it writes no escalation lesson.
- [ ] AC-12: `/status` shows the lane for each in-flight REQ.
- [ ] AC-13: The `/sprint` workflow engine runs a lite REQ on the full lane and logs that it did.
- [ ] AC-14: A `tools/lint-skills` check fails on any `lane` value outside `lite` and `full` written or read by a skill, and passes on the shipped skills.
- [ ] AC-15: `.adlc/config.yml` `lanes.lite` overrides for `max_files`, `blocked_paths`, `count_exclude` and `deploy_units` take effect. With the block absent, the toolkit defaults apply. `templates/config-template.yml` documents the block.
- [ ] AC-16: The lane check runs after the review pass's fixes are committed, and runs again before merge when Phase 7 adds commits. A review fix or CI fix that touches a blocked path escalates the REQ.

## External Dependencies

- None.

## Assumptions

- Most of a full run's cost on a small change is in Phases 1–3 and the six-agent verify. This has not been measured. REQ-648 (per-run outcome telemetry, draft) would let it be measured, and the lite lane should report its savings once that exists.
- Triage from the request text plus the codebase predicts the footprint well enough that escalations are the exception. BR-14's lessons are how this gets checked.
- A full-lane architect can design around code already written without discarding it. This is how escalation stays lossless (BR-10).
- A default of 3 source files is a starting point and will be tuned by BR-14's lessons. Line counts are deliberately not checked: a copy edit can touch many lines and stay trivial, while a one-line change to a blocked path is already caught by `blocked_paths`.
- REQ-647 (lessons reach every pipeline phase, draft) will need to cover the lite lane's phases as well. Whichever lands second adapts to the other.

## Open Questions

- [x] OQ-1: Should a forced `--lite` stay subject to the diff check at all? — Resolved 2026-10-27 (Brett): yes. A solo run halts and asks (BR-8); a sprint runner escalates.
- [x] OQ-2: Should the lite lane keep one cheap spec validation (Phase 1 only) before implementing? — Resolved 2026-10-27 (Brett): no. The review pass checks acceptance-criteria coverage instead (BR-5).
- [x] OQ-3: Are 3 files and 100 lines the right defaults? — Resolved 2026-10-27 (Brett): check files only. The limit is 3 source files, not counting tests or `.adlc/`, and lines are not counted (BR-2, BR-6).

## Out of Scope

- A lite path inside the `/sprint` workflow engine (BR-16 runs lite REQs on the full lane there).
- De-escalating a full REQ to lite.
- Changing `/bugfix`, which stays the short path for defects.
- Embolden's issue-claiming skill for parallel sessions, which will be built on this lane in embolden-website as its own change.
- Changes to CI, deploy or promotion flows; the lite lane ships through the same gates as the full lane.

## Retrieved Context

- LESSON-604 (lesson, score 9): A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time
- LESSON-004 (lesson, score 9): /proceed Phase 7.5 (canary) and Phase 8a (snapshot promotion) misfit a dev → staging → main topology
- BUG-207 (bug, score 8): The conflict-halt contract does not distinguish solo /proceed from an unattended sprint
- LESSON-572 (lesson, score 8): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 8): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion
- LESSON-571 (lesson, score 7): A retrieval filter is half of a read/write contract with whatever writes the field
- BUG-194 (bug, score 7): /spec Step 1.6 spec-corpus status filter admits no status the pipeline ever writes
- LESSON-019 (lesson, score 7): A literal-presence guard silently rots when the thing it guards moves behind indirection
- LESSON-002 (lesson, score 7): Cross-repo REQ support: 'primary' is per-REQ
- LESSON-001 (lesson, score 7): Mitigate /proceed per-phase gating via settings allowlist + softened skill language
- LESSON-626 (lesson, score 6): A rule written about one actor does not settle the case for another — bound machine resolution to a checkable property
- BUG-212 (bug, score 6): A conflict resolved during a pipeline run leaves no machine-readable trace
- REQ-610 (spec, score 6): Guard the two-level partial-sourcing pattern
- REQ-594 (spec, score 6): Spec intake: turn raw human input into a draft REQ plus an explicit gap list
- LESSON-390 (lesson, score 6): Draft-PR-early cannot open on a zero-commit branch — defer to the first commit
