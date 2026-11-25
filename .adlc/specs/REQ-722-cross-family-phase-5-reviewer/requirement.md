---
id: REQ-722
title: "A reviewer from a different model family sits on the Phase-5 panel, with findings no same-family reviewer can silently drop"
status: complete
deployable: true
created: 2026-11-23
updated: 2026-11-25
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "bash", "python", "claude-skills"]
concerns: ["verify-quality", "correctness", "privacy"]
tags: ["review-panel", "cross-family-review", "model-diversity", "delegation", "phase-5", "independent-review"]
lane: "full"
lane_reason: "sends the diff and spec to a third-party endpoint under the delegation gate (privacy/security), and adds a key to the closed delegate config schema in tools/delegate/_machine_config.py"
lane_forced: false
---

## Description

Every reviewer on the `/proceed` Phase-5 panel is the same model family as the
implementer. The reflector and the five dimension reviewers (`proceed/SKILL.md`
Phase 5 Step A) run in the harness that wrote the code, and on Claude Code an
agent's `model:` override only moves between Claude tiers (`harness/claude.yml`
`tier_map`). They share the implementer's training, its blind spots and its
habits of reading code, so their agreement is weaker evidence than six votes
suggest. ETHOS #7 asks for a review that tries to break the change, and a
reviewer that learned to read code the same way the author did is the one least
likely to find the defect the author could not see.

The toolkit already sends Phase-5 work to another model, but gives it no voice.
The REQ-417 delegate pre-pass sends the redacted diff to the configured delegate
endpoint, which is Moonshot's Kimi by default, a different family. Its output
reaches the five reviewers only as `<advisory-candidates trust="untrusted">`,
with the instruction "Confirm or refute each before including in your findings."
So a same-family reviewer decides whether a cross-family observation exists. A
refuted candidate leaves no trace: it is not a finding, is not consolidated, and
is not in `pipeline-state.json.verify`. The other family's view can be
overruled, and nobody can count how often that happens. The pre-pass also
doesn't run on two common paths: it is skipped in `/sprint` subagent mode
(`proceed/SKILL.md` Phase 5, "In subagent mode … do NOT dispatch the delegate
pre-pass"), and delegation is off by default.

This REQ adds a **cross-family reviewer**: one panel member, served by a model
whose family differs from the implementer's, that reviews the diff against the
spec and returns findings in the panel's own format. Its findings enter Step B
consolidation as first-class findings, tagged with their source. A finding from
it can be declined only with a recorded reason, never dropped silently. When the
reviewer cannot run, or cannot be shown to be a different family, the run says
so in the state file and the PR body, so a single-family review never passes for
a cross-family one.

It sends source content off the machine, so it goes through the delegation gate
and nowhere else: the gate may veto, and only the Python resolver may authorize
(REQ-603).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ModelFamily | value | string | a closed enum, defined once (for example `anthropic`, `openai`, `moonshot`, `google`, `meta`, `other`, `unknown`); compared by equality only, never inferred from a model-name substring |
| ImplementerFamily | `family` | ModelFamily | the family of the model that wrote the diff in this run; `unknown` when the toolkit cannot establish it (BR-3) |
| ReviewerLane | `family` | ModelFamily | the declared family of the endpoint serving the cross-family reviewer; a new key in the delegate config, which is a closed schema today (`DELEGATE_KEYS` in `tools/delegate/_machine_config.py`) |
| CrossFamilyReview | `status` | enum | `ran` \| `skipped`; written once per touched repo per run (BR-1: Step D does not re-run the reviewer) |
| CrossFamilyReview | `reason` | string | required when `skipped`; one value from a closed vocabulary (for example `delegation-disabled`, `no-binary`, `same-family`, `family-unknown`, `subagent-mode`, `redaction-failed`, `api-error`, `invalid-output`) |
| CrossFamilyReview | `implementerFamily`, `reviewerFamily` | ModelFamily | recorded on both `ran` and `skipped` |
| CrossFamilyReview | `findingCount`, `declinedCount` | integer | counts after post-validation (BR-6) and after Step C (BR-8) |
| Phase-5 finding | `source` | string[] | additive; the set of members that raised it: `panel` for the existing six, `cross-family` for this reviewer, both when a dedupe merged them (BR-7). A finding whose `source` is exactly `["cross-family"]` is cross-family-only |
| Phase-5 finding | `disposition` | enum | additive; `fixed` \| `deferred` \| `declined`, with `declineReason` required when `declined` |

`CrossFamilyReview` is recorded in the primary-path `pipeline-state.json` beside
`verify`. It is additive and optional: a state file without it parses unchanged,
and absent means "not recorded" (a run before this REQ), never `ran`.

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `cross_family_review_requested` | Phase 5, after the LessonSet, before or alongside Step A | repo id, implementerFamily, reviewerFamily |
| `cross_family_review_skipped` | any BR-4 condition holds | repo id, reason, both families |
| `cross_family_findings_returned` | the delegate call exits 0 with parseable output | repo id, validated findings |
| `cross_family_finding_declined` | Step C declines a `cross-family` finding | finding id, declineReason |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Transmit the redacted diff and spec to the reviewer endpoint | only when the Python delegation resolver authorizes it (REQ-603); a shell arm may veto, never grant |
| Decline a `cross-family` finding | the Step C fixer, with a recorded reason; under REQ-723, the arbiter |

## Business Rules

- [ ] BR-1: Phase 5 of `/proceed` dispatches one cross-family reviewer per touched repo, alongside the Step A panel, whenever BR-4 does not skip it. It runs once per run: the Step D re-verify does not re-run it, and fixes to its findings are confirmed by the Step D panel reviewers like any other fix. It reviews the repo's diff against `origin/<integrationBranch>` (informed by LESSON-391), the changed files, and the spec's numbered Business Rules and Acceptance Criteria. It is told to mark each BR and AC met, partial or unmet, as well as to find defects (informed by LESSON-330).
- [ ] BR-2: The reviewer's family must differ from the implementer's. The toolkit compares two declared `ModelFamily` values for equality. It never infers a family from a model name, an endpoint URL or a harness name, because a harness can run more than one family (Copilot CLI and Cursor serve both Anthropic and OpenAI models).
- [ ] BR-3: The implementer's family is `unknown` unless the toolkit can establish which model wrote the diff. An `unknown` implementer family, or an `unknown` reviewer family, means the review cannot be counted as cross-family: it is skipped with reason `family-unknown` and never recorded as `ran`. The source of the implementer family is an architecture decision. A harness adapter may declare one only when every model it can run in that mode is one family.
- [ ] BR-4: The reviewer is skipped, with exactly one recorded reason, when delegation is not authorized (`delegation-disabled`, or `no-binary` when the delegate CLI cannot be resolved), when the families are equal (`same-family`) or either is `unknown` (`family-unknown`), when the run is in a context that cannot reach the delegate (`subagent-mode`), when credential redaction fails (`redaction-failed`), when the call exits non-zero (`api-error`), or when its output fails BR-6 as a whole (`invalid-output`). A skip never halts the pipeline and never blocks a merge.
- [ ] BR-5: A skip is never silent. It writes a `CrossFamilyReview` record with `status: skipped` and its reason at the moment it happens (informed by LESSON-626, BUG-212). It emits one stderr line naming the repo and the reason, and replaces nothing else the phase already prints (informed by LESSON-008 rule 5). The PR body says plainly whether Phase 5 had a cross-family reviewer for each repo and, if not, why.
- [ ] BR-6: The reviewer's output is untrusted data (informed by LESSON-008). It is wrapped in the delimiters the pre-pass uses, and every finding is post-validated before it enters consolidation. Its path must match the pre-pass charset with no `..` segment and must appear in that repo's changed-files list. Its line must be an integer inside the file. Its severity must be one of Critical, Major, Minor or Nit. Its class must match `FINDING_CLASS_PATTERN`. A finding that fails any check is dropped and counted. When every finding fails, or the output cannot be parsed, the review is `skipped` with reason `invalid-output`, not `ran` with zero findings.
- [ ] BR-7: Findings that pass BR-6 are first-class. They enter Step B consolidation with `source: cross-family`, are deduplicated against the panel's findings like any other (a merged finding keeps every source that raised it), and are ranked and fixed in Step C by the existing severity rules. No same-family panel member sees them before consolidation, so none can confirm or refute them away. The reviewer gets no advisory candidates and its findings are not candidates for anyone else.
- [ ] BR-8: The Step C fixer may decline a `cross-family` finding only by recording `disposition: declined` with a `declineReason` that cites the code contradicting the finding (a path and line, or a test that exercises the claimed failure and passes). A declined finding stays in `pipeline-state.json.verify` and is listed in the PR body under its own heading. Phase 6 does not start while any `cross-family` finding has no disposition. A decline without a `declineReason` that meets this rule counts as no disposition, and the finding is fixed under the severity rules. A finding is never dropped silently, and `/proceed` gains no halt point for this. When REQ-723 has landed, its arbiter owns this decision and this rule's reason requirement applies to the arbiter's `refuted` verdict.
- [ ] BR-9: Transmission is governed only by the delegation gate. The reviewer uses the existing `adlc-read` path, after the same `mktemp` handling, `EXIT` trap and five-pattern credential redaction the pre-pass uses, with the same fail-closed rule: a failed redaction sends nothing (informed by LESSON-008). No new environment variable, config arm or shell branch may authorize delegation (informed by REQ-603, BUG-205, BUG-209). `ADLC_DISABLE_DELEGATE=1` stops it with zero calls.
- [ ] BR-10: Adding `family` to the delegate config keeps the REQ-609 posture. The key joins the closed schema, the strict loader rejects an unknown value, a config without the key reads `unknown` (so BR-3 skips the review), and the existing keys keep their meaning byte for byte.
- [ ] BR-11: The REQ-417 pre-pass is unchanged. It still runs when its own gate allows, still feeds the five reviewers advisory candidates, and still skips the reflector. The cross-family reviewer is an additional, independent panel member, not a replacement.
- [ ] BR-12: The `/sprint` workflow engine follows the same rules. Its Phase-5 panel gains the reviewer as a leaf dispatched per touched repo, its findings validated against the `FINDINGS` schema extended in the same change (informed by LESSON-331), and its skips recorded the same way. Any engine that cannot run it records `skipped` with a reason rather than omitting the record.
- [ ] BR-13: Telemetry stays derived by code. The run-outcome line (REQ-648) counts cross-family findings, fixes and declines from the state file, and records the review's status and reason, so a sprint's recurrence report can show how often the other family found something the panel did not, and how often its findings were declined. Every new field is additive and optional, and `check-run-outcomes.sh` keeps its existing columns in place.
- [ ] BR-14: The lite lane is unchanged. `lite-reviewer` remains its one review pass, and a lite run writes no `CrossFamilyReview` record.
- [ ] BR-15: All new shell is BSD- and zsh-safe, every shared function is a sourced partial re-sourced in the fence that calls it, and every new fence and section passes the harnesses that parse `proceed/SKILL.md`, not only `tools/lint-skills` (informed by LESSON-742).

## Acceptance Criteria

- [ ] With delegation authorized, implementer family `anthropic`, reviewer family `moonshot` and a stubbed delegate that returns one valid finding, Phase 5 records `status: ran` for the touched repo and the finding appears in consolidation with `source: ["cross-family"]`.
- [ ] With a stubbed delegate finding that a panel reviewer also raises under the existing dedupe key (same file and normalized title), consolidation holds one finding with `source: ["panel", "cross-family"]`.
- [ ] No panel reviewer's dispatch prompt contains the cross-family reviewer's output; a structural test asserts it.
- [ ] With reviewer family equal to implementer family, the run records `skipped` / `same-family`, prints one stderr line, makes no delegate call, and the PR body says the panel was single-family.
- [ ] With no `family` key in the delegate config, the run records `skipped` / `family-unknown` and makes no delegate call.
- [ ] With `ADLC_DISABLE_DELEGATE=1`, the run records `skipped` / `delegation-disabled` and makes zero delegate calls; a test asserts the call count.
- [ ] A forced redaction failure records `skipped` / `redaction-failed`, and the temp file never reaches the delegate.
- [ ] Delegate output citing `../etc/passwd`, a file outside the diff, a severity outside the enum, or a class that fails `FINDING_CLASS_PATTERN` loses that finding at BR-6 and counts it as dropped. Output in which every finding fails records `invalid-output`.
- [ ] Declining a `cross-family` finding without a qualifying `declineReason` leaves it with no disposition, so it is fixed before Phase 6. Declining it with one keeps the finding in `verify` with `disposition: declined` and lists it in the PR body.
- [ ] A Step D re-verify does not dispatch the cross-family reviewer a second time.
- [ ] A `/sprint` subagent-mode run records `skipped` / `subagent-mode` for each touched repo instead of omitting the record.
- [ ] With the cross-family reviewer running, the REQ-417 pre-pass still runs under its own gate, its candidates still reach only the five reviewers, and the reflector still receives none.
- [ ] The run-outcome line reports the cross-family review's status and reason, and its finding, fix and decline counts, read from the state file; `check-run-outcomes.sh` output on a pre-REQ state file is unchanged.
- [ ] The workflow engine's `FINDINGS` schema accepts a finding with `source: ["cross-family"]` and rejects an unknown `source` value; a structural test covers both.
- [ ] A `pipeline-state.json` written before this REQ parses and reports unchanged in `/status` and in the run-outcome line.
- [ ] The delegate config loader rejects an unknown `family` value and treats an absent one as `unknown`; existing configs load unchanged.
- [ ] A lite-lane run writes no `CrossFamilyReview` record and its Phase 5 is byte-identical in behavior.
- [ ] `tools/lint-skills`, the `partials/tests/run.sh` suite, the delegate tests and the workflow tests pass on the final tree.

## External Dependencies

- An OpenAI-compatible endpoint serving a model of a different family, reached through the existing `adlc-read` CLI. No new library.

## Assumptions

- The delegate endpoint's model is capable enough to review a diff against a spec. Kimi's pre-pass output is the evidence so far; BR-13's counts are how this gets measured rather than assumed.
- `adlc-read` is the right transport. It is read-only question answering over files, so this reviewer cannot run tests or explore the tree as the panel agents do. It reviews the diff, the changed files and the spec only.
- The family enum can be closed and small. A provider that serves several families (an aggregator) is declared by the family of the model actually configured.
- Sending the spec as well as the diff adds nothing new in kind: under delegation, the pre-pass already sends the diff, and the spec is a project file like the others `adlc-read` already reads.

## Open Questions

- [ ] Where does the implementer's family come from? A per-adapter declaration covers the Claude Code and Codex exec routes, but not Copilot CLI or Cursor, which can run either family in one session. Is `unknown` there acceptable for the first release, or should a run be able to state its model?
- [ ] Should the reviewer use the same endpoint and config block as `adlc-read` delegation, or a separate `review:` lane, so an operator can send bulk reads to a cheap model and reviews to a strong one?
- [ ] Once BR-13 has a few sprints of data, should the pre-pass be retired as redundant? That decision is out of scope here; this question records that it should be made on evidence.

## Out of Scope

- Changing or retiring the REQ-417 delegate pre-pass (BR-11).
- Standalone `/review`, `/reflect` and the lite lane's `lite-reviewer`.
- An arbiter that adjudicates findings; that is REQ-723.
- Routing implementation, not review, to a different family.
- Running the reviewer through a full harness (for example `codex exec` with tools) instead of `adlc-read`.
- Self-hosted model routing or any model-plane infrastructure.

## Retrieved Context

- REQ-660 (spec, score 10): Session sidecar and multi-harness transcripts for the /wrapup knowledge loop
- LESSON-751 (lesson, score 10): A spec's measured figures go stale while sibling REQs land — re-measure at Phase 1, and treat any rule conditioned on a measurement as void once the measurement no longer holds
- REQ-603 (spec, score 10): Single-source the delegation authorization arms — the gate may veto, only Python may authorize
- LESSON-729 (lesson, score 9): Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them
- REQ-647 (spec, score 9): Lessons reach every pipeline phase: per-task retrieval in /proceed Phase 4, the full Phase 5 panel, /bugfix Analyze, and the sprint workflow engine
- REQ-652 (spec, score 9): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- BUG-205 (bug, score 9): A legacy MOONSHOT_API_KEY/KIMI_API_KEY in the environment silently overrides an explicit `delegate.enabled: false` — the operator's opt-out is ignored and file contents are transmitted
- LESSON-330 (lesson, score 9): The Phase-5 review catches OMITTED requirements, not just bugs — cross-check every BR against the diff
- LESSON-008 (lesson, score 9): When a Claude skill delegates to a cheaper model and feeds the result back to itself, the output is untrusted data — sanitize citation tokens, wrap in delimiters, use mktemp, and emit one stderr line per invocation
- LESSON-760 (lesson, score 8): A transcript parser must allow record types, not sniff for message shape: Claude Code's api-request-blob records looked like Human turns
- LESSON-719 (lesson, score 8): Decide resume from the progress record, not from whether a setup object exists — and check that a sub-step's state write survives the step's own closing rule
- LESSON-626 (lesson, score 8): A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event
- BUG-207 (bug, score 8): The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint
- BUG-212 (bug, score 8): A conflict resolved during a pipeline run leaves no machine-readable trace — the only record is the runner's closing narrative
- BUG-209 (bug, score 8): `ADLC_DISABLE_DELEGATE=1` is inert in the delegate CLIs — the documented emergency stop lives only in the vendored shell gate, and a run with it set still transmits file contents
