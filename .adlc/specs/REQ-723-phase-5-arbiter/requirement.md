---
id: REQ-723
title: "A separate arbiter adjudicates Phase-5 findings on evidence, so the session that must fix them no longer decides which are real"
status: draft
deployable: true
created: 2026-11-23
updated: 2026-11-24
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "claude-skills", "javascript"]
concerns: ["verify-quality", "correctness"]
tags: ["arbiter", "consolidation", "review-panel", "finding-adjudication", "phase-5", "adversarial-review"]
lane: "full"
lane_reason: "extends the workflow engine's closed FINDINGS schema (a validator) and touches proceed/SKILL.md, a new agent, the workflow script and its tests, past max_files"
lane_forced: false
---

## Description

Phase 5 of `/proceed` gathers findings from six reviewers and then gives them to
the one actor with a stake in the outcome. Step B ("Consolidate") and Step C
("Fix in one pass") are both performed by the orchestrating session, the same
session that implemented the change and that has to do the fix work. In Step C
it decides which Major findings are "must-fix", which Minor findings would be "a
significant refactor" and become follow-ups, and which Nits to "skip". Nothing
outside that session checks those calls, and none of them is recorded with a
reason. The workflow engine goes the other way: `dedupeAndRank` in
`workflows/adlc-sprint.workflow.js` is pure JS that ranks by severity and blocks
on every Critical or `mustFix` finding, whatever the evidence. That is
impartial, but it can't tell a real defect from a reviewer's false positive,
so every false positive costs a fix loop.

ETHOS #7 asks for findings that survive an attempt to refute them. Each
reviewer is told to self-refute, but no one weighs one reviewer's finding
against another's reading of the same code, or against the code itself, once
the panel has reported. When two reviewers disagree, or when a finding's
premise is false, today's pipeline either quietly lets the fixer decide (solo)
or fixes it regardless (workflow).

The disagreement case grows with REQ-722. A reviewer from a different model
family will sometimes report something the same-family panel didn't. Someone has
to decide whether it is real. If that someone is the implementing session, the
second family's view can be overruled by the first, which is exactly what
REQ-722 exists to prevent.

This REQ adds an **arbiter**: a separate, read-only agent dispatched after
consolidation and before any fix. For each finding that would block, and for
each finding the fixer claims is a false positive, it returns a verdict based on
evidence: `upheld`, `downgraded`, `refuted` or `cannot-decide`. A verdict is
bounded by a property a machine can check (a refutation must cite code that
exists), it is recorded at the moment it is made, and the fixer cannot override
it. The arbiter adds no findings of its own. It is a judge, not a seventh
reviewer.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ArbiterVerdict | `findingRef` | string | identifies one consolidated finding (repo, file, line, class) |
| ArbiterVerdict | `verdict` | enum | `upheld` \| `downgraded` \| `refuted` \| `cannot-decide` |
| ArbiterVerdict | `severity` | enum | the resulting severity; for `downgraded`, strictly lower than the finding's own; otherwise unchanged |
| ArbiterVerdict | `evidence` | string[] | required for `refuted` and `downgraded`: each entry a `path:line` or `path:start-end` that exists in the worktree, or a test name; validated mechanically (BR-5) |
| ArbiterVerdict | `reason` | string | one or two sentences; required for every verdict |
| ArbiterVerdict | `arbiterFamily` | ModelFamily | the arbiter's model family, using REQ-722's enum; `unknown` when not established |
| ArbiterRun | `status` | enum | `ran` \| `skipped`; `reason` required when skipped (for example `subagent-mode`, `no-blocking-findings`, `invalid-output`) |
| ArbiterRun | `pass` | integer | 1 for the first consolidation, 2 for the Step D re-verify; never more |
| Phase-5 finding | `verdict` | ArbiterVerdict | additive and optional on each entry in `pipeline-state.json.verify` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `arbiter_requested` | Step B consolidation complete, at least one finding in scope (BR-2) | the in-scope findings, diff, changed files, spec BRs and ACs, the Phase-5 LessonSet |
| `arbiter_verdict_recorded` | each verdict passes BR-5 | ArbiterVerdict |
| `arbiter_verdict_rejected` | a `refuted` or `downgraded` verdict fails BR-5 | finding ref, failure; the verdict becomes `upheld` |
| `arbiter_skipped` | any BR-9 condition | reason |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Issue a verdict | the arbiter only |
| Read the worktree, diff, spec and lessons | the arbiter (read-only: no edits, no test runner, no build tool) |
| Override a verdict | nobody in an unattended run; the operator in a solo run, at a halt (BR-7) |

## Business Rules

- [ ] BR-1: After Step B consolidation and before Step C, `/proceed` Phase 5 dispatches one arbiter for the REQ, covering every touched repo. The arbiter is a fresh agent with its own context: never the orchestrating session, never a panel member, and never inline in the orchestrator's own context.
- [ ] BR-2: The arbiter judges every consolidated finding that is Critical or must-fix Major, and every finding of any severity that the fixer proposes to decline as a false positive. The fixer states its proposed declines at the end of Step B, before dispatch. The arbiter judges whether a finding is real, not whether it is worth fixing now: deferring a Minor as a significant refactor (Step C item 2) and skipping a Nit (item 3) stay under Step C's existing rules and are not sent to it, and neither is an Info. When the set is empty, the arbiter is skipped with reason `no-blocking-findings` and no dispatch happens.
- [ ] BR-3: The arbiter returns exactly one verdict per finding it receives. A finding with no verdict in the output is treated as `upheld` and counted as missing. A verdict for a finding it was not sent is discarded.
- [ ] BR-4: The arbiter adds no findings and cannot raise a severity. A defect it notices that no reviewer raised goes in a separate `observations` list that is printed and recorded but does not block, so the arbiter can't become a seventh reviewer whose finding no one checks.
- [ ] BR-5: `refuted` and `downgraded` must carry evidence a machine can check (informed by LESSON-626). Every `path:line` must name a tracked file in the touched repo's worktree with the line in range, under the same charset and no-`..` rule as the pre-pass (informed by LESSON-008). Every test name must be one the project's test runner can list. A `refuted` or `downgraded` verdict whose evidence fails, or that cites none, is rewritten to `upheld` and recorded as rejected. Missing evidence never lets a finding through.
- [ ] BR-6: `cannot-decide` resolves to `upheld` at the finding's own severity. When the arbiter cannot tell, the pipeline fixes the finding (ETHOS #4).
- [ ] BR-7: The arbiter's verdict is binding in Step C. An `upheld` finding is fixed under the existing severity rules. A `downgraded` finding is handled at its new severity. A `refuted` finding is not fixed and is recorded with the arbiter's evidence and reason. The fixer may not decline an `upheld` finding, and may not defer an `upheld` Critical or must-fix Major. An `upheld` Minor may still be deferred under Step C item 2. In a solo run, if the fixer believes a verdict is wrong, it halts and asks the operator. That is a fifth legitimate halt point: the Autonomous Execution Contract in `proceed/SKILL.md` lists exactly four today, and its count and list are updated in the same change. In an unattended run (a `/sprint` runner or the exec engine) there is no override, because no person is present to give one (informed by LESSON-626, BUG-207).
- [ ] BR-8: A finding raised only by a reviewer of a different family than the arbiter (REQ-722's `source: cross-family`, when the arbiter is the implementer's family) can be `refuted` only with test evidence, a named test that exercises the claimed failure and passes. A `path:line` citation alone is not enough, because that is the same-family reading the cross-family reviewer exists to check. Every such refutation is listed in the PR body under its own heading for the human reviewer. When no family can be established for the arbiter, this rule applies to every cross-family-only finding.
- [ ] BR-9: The arbiter is skipped, with exactly one recorded reason and one stderr line, when the run cannot give it its own context (`subagent-mode`, the legacy runner's inline execution) or when its output can't be parsed or fails schema validation (`invalid-output`). A skipped arbiter changes Step C in one way only: no finding may be declined, so every Critical and must-fix Major is fixed. Minor deferral and Nit skipping stay as they are today. A skip never halts the pipeline.
- [ ] BR-10: Bounded. The arbiter runs at most twice per run: pass 1 after Step B, and pass 2 after the Step D re-verify, over only the findings the re-verify newly raised or kept. There is no pass 3. Findings `upheld` in pass 2 are fixed once under Step C's rules, with no further re-verify, and any that remain are listed in the PR body as unresolved. Phase 5 gains no halt point from this rule.
- [ ] BR-11: Every verdict is written to the primary-path `pipeline-state.json` at the moment it is recorded, on the finding's `verify` entry, along with the `ArbiterRun` record (informed by LESSON-626, BUG-212, LESSON-719). Both are additive and optional: a state file without them parses unchanged, `/status` treats absent as "no arbiter ran", and nothing reads them for control flow except Step C of the run that wrote them.
- [ ] BR-12: The PR body carries an arbiter section: counts by verdict, every `refuted` finding with its evidence, and the skip reason when the arbiter did not run. A human reviewing the PR can see every finding the pipeline chose not to fix and why.
- [ ] BR-13: The workflow engine follows the same rules. After `dedupeAndRank`, the script dispatches an arbiter leaf over the blocking subset, validates its output against a closed `VERDICTS` schema added in the same change (informed by LESSON-331), applies BR-5's evidence check in a pure function, and recomputes the blocking subset from the verdicts. `refuted` findings drop out of `blocking`, `downgraded` findings move with their new severity, and everything else is unchanged.
- [ ] BR-14: Telemetry is derived by code. The run-outcome line (REQ-648) gains counts of upheld, downgraded, refuted, cannot-decide and rejected verdicts, read from the state file, so it can show how often panels raise findings that don't survive arbitration, per class. Every new field is additive, and `check-run-outcomes.sh` keeps its existing columns in place.
- [ ] BR-15: The arbiter gets the same Phase-5 LessonSet as the panel (REQ-647 BR-3). It may cite a lesson in a `reason`, and a lesson id is never evidence under BR-5.
- [ ] BR-16: The lite lane is unchanged, and so are standalone `/review` and `/reflect`.
- [ ] BR-17: The agent definition lives at `agents/arbiter.md` with a read-only tool list and the canonical finding-class block every reviewer carries. Its dispatch uses conventions.md's canonical dispatch paragraph, and its inline-checklist arm is never used for arbitration (BR-9 skips instead), because an inline arbiter is the orchestrator judging its own work.

## Acceptance Criteria

- [ ] Given a seeded Critical finding and stubbed arbiter output that refutes it with a valid `path:line`, Phase 5 records `refuted`, does not fix the finding, and lists it in the PR body with its evidence.
- [ ] A `refuted` verdict citing a nonexistent file, an out-of-range line, a `..` path or no evidence is rewritten to `upheld`, recorded as rejected, and fixed.
- [ ] A `cannot-decide` verdict on a Major finding results in the finding being fixed at Major.
- [ ] Arbiter output that omits a finding leaves that finding `upheld`; output with a verdict for an unknown finding discards that verdict.
- [ ] An arbiter observation not raised by any reviewer appears in the observations list and does not enter `blocking`.
- [ ] With the arbiter the implementer's family, a `cross-family`-only finding cannot be refuted by a `path:line` citation alone; with a named passing test it can, and the PR body lists it.
- [ ] A subagent-mode run records `skipped` / `subagent-mode`, declines nothing, and fixes every Critical and must-fix Major.
- [ ] A run whose consolidation has no Critical or must-fix Major finding and no proposed decline dispatches no arbiter and records `no-blocking-findings`.
- [ ] A Minor the fixer defers as a significant refactor is not sent to the arbiter and is recorded as deferred, as it is today. An `upheld` Critical cannot be deferred.
- [ ] A Step D re-verify runs arbiter pass 2 over newly raised or still-held findings only; no run records a pass 3, and a finding still upheld after pass 2's fixes is listed in the PR body as unresolved rather than halting.
- [ ] In a solo run, the fixer disputing an `upheld` verdict halts and asks the operator; in a `/sprint` run the same case fixes the finding without halting. The Autonomous Execution Contract lists five halt points.
- [ ] Each verdict is in `pipeline-state.json` on its finding's `verify` entry as soon as it passes or fails BR-5, before Step C commits any fix.
- [ ] The run-outcome line reports counts of upheld, downgraded, refuted, cannot-decide and rejected verdicts read from the state file; `check-run-outcomes.sh` output on a pre-REQ state file is unchanged.
- [ ] `agents/arbiter.md` declares a read-only tool list and the canonical finding-class block, and the arbiter's dispatch prompt carries the same Phase-5 LessonSet the panel received; structural tests cover both.
- [ ] The workflow engine's `VERDICTS` schema rejects an unknown verdict and a `downgraded` verdict whose severity is not lower; the pure evidence check and the recomputed `blocking` subset are covered by `workflows/tests/`.
- [ ] A `pipeline-state.json` written before this REQ parses and reports unchanged in `/status` and in the run-outcome line.
- [ ] A lite-lane run dispatches no arbiter and its Phase 5 is unchanged.
- [ ] `tools/lint-skills`, the `partials/tests/run.sh` suite and the workflow tests pass on the final tree.

## External Dependencies

- No external service. The arbiter is a subagent in the running harness.
- REQ-722 defines the `ModelFamily` enum and the finding `source` field this REQ reads. If REQ-723 lands first, it introduces `ModelFamily` with the same values, records `arbiterFamily: unknown`, and BR-8 has nothing to apply to until REQ-722 lands. The two REQs touch the same Phase 5 text and the same `FINDINGS` schema, so they are sequenced, not run in parallel.

## Assumptions

- A fresh agent with its own context is independent enough of the implementer to judge evidence, even in the same family, as long as its verdicts are bounded by BR-5 and BR-8. Same-family judgment is acknowledged as the weaker case, which is why BR-8 asks more of it.
- A Step-B consolidated finding carries enough location (repo, file, line, class) to be referenced unambiguously. The workflow `FINDINGS` schema makes `line` optional, so a finding without a line is judged on file and class, and its refutation still needs evidence under BR-5.
- One arbiter per REQ, not per repo, fits in one agent's context: it receives only the blocking and proposed-decline subset, and REQ-647's 40-line lesson cap bounds the rest.
- The project's test runner can list test names, so BR-5's test-name check is mechanical. Where it can't, test-name evidence fails BR-5 and only `path:line` evidence counts.

## Open Questions

- [ ] Should the arbiter run on a different family when one is available, for example through REQ-722's reviewer lane? Doing so would loosen BR-8, but it would send the blocking findings and their surrounding code off the machine as well.
- [ ] Is the solo-run override halt in BR-7 worth the interruption, or should a solo run also be bound without override, with the operator's recourse being the PR review?
- [ ] Should `/review` standalone adopt the arbiter in a follow-up, given that it has no Step C to bind?

## Out of Scope

- Adding a cross-family reviewer; that is REQ-722.
- Changing what any panel reviewer looks for, or the severity rules themselves.
- The lite lane, standalone `/review` and `/reflect`.
- Training or tuning a reward model from verdict data. BR-14 records the data; using it is a separate decision.
- Arbitrating validation gate results (Phases 1 and 3) or CI outcomes.

## Retrieved Context

- LESSON-751 (lesson, score 10): A spec's measured figures go stale while sibling REQs land — re-measure at Phase 1, and treat any rule conditioned on a measurement as void once the measurement no longer holds
- REQ-647 (spec, score 9): Lessons reach every pipeline phase: per-task retrieval in /proceed Phase 4, the full Phase 5 panel, /bugfix Analyze, and the sprint workflow engine
- REQ-652 (spec, score 9): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- LESSON-330 (lesson, score 9): The Phase-5 review catches OMITTED requirements, not just bugs — cross-check every BR against the diff
- LESSON-719 (lesson, score 8): Decide resume from the progress record, not from whether a setup object exists — and check that a sub-step's state write survives the step's own closing rule
- LESSON-729 (lesson, score 7): Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them
- LESSON-626 (lesson, score 7): A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event
- BUG-207 (bug, score 7): The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint
- BUG-212 (bug, score 7): A conflict resolved during a pipeline run leaves no machine-readable trace — the only record is the runner's closing narrative
- LESSON-604 (lesson, score 7): A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time or you will rediscover a lesson captured in the gap
- LESSON-391 (lesson, score 7): Review and cleanup must diff against origin/<integration>, not local main — a stale local main attributes other REQs' work to yours
- REQ-483 (spec, score 7): Hard ordering enforcement for concurrent ADLC REQs — draft-PR-early, file footprint, deterministic serialize/halt
- LESSON-764 (lesson, score 6): A parallel REQ landing turns "in flight" and "not shipped yet" into false statements, and a clean rebase will not tell you
- LESSON-742 (lesson, score 6): A skill-text edit is input to the harnesses that parse skill text — a clean lint is not the gate; run partials/tests/run.sh on the final tree
- LESSON-603 (lesson, score 6): A spec that names a frontmatter field is stating a belief, not a fact — check it against the template that actually emits the field
