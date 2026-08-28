---
id: REQ-595
title: "BR→verification obligations: /architect emits the tests, not just the tasks"
status: draft
deployable: true
created: 2026-08-27
updated: 2026-08-27
component: "adlc/architect"
domain: "adlc"
stack: [markdown, bash, claude-skills]
concerns: [testing, verify, correctness]
tags: [testing, test-generation, acceptance-criteria, verify, task-template, coverage]
---

## Description

The pipeline audits tests but never specifies them. `/architect` breaks a REQ into tasks;
`task-implementer` writes whatever tests it judges appropriate; `test-auditor` reports on
coverage afterwards. Nowhere between the Business Rules and the diff does anything state
*which* rule must be proven by *what*. LESSON-330 named the resulting failure directly:
Phase 5's real catch is **omitted** requirements — a numbered BR implemented as zero —
and the countermeasure it prescribes is mapping every BR to a specific implementation
before review. That mapping is currently done by memory, per REQ, if at all.

This REQ moves the obligation upstream. `/architect` emits, per task, a `## Verification`
block naming each BR and AC the task discharges and the concrete artifact that proves it.
`/validate` then gates on completeness: a numbered BR with no verification obligation
anywhere in the task set fails the architecture gate rather than surfacing three phases
later as a review finding — or not at all.

The artifact type is deliberately not "a test file". This toolkit is markdown with a
`tools/` exception: skills have no test runner, and their real verification mechanism is
a structural check in `tools/lint-skills` (LESSON-012's entire argument — enforce
structurally, not by prose). A consumer project on iOS or Cloud Run has a genuine test
runner. So the obligation resolves its artifact type from the project's declared stack,
and "structural lint check" is a first-class verification artifact alongside "test case",
not a lesser substitute.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| VerificationObligation | `rule` | string | `^(BR\|AC)-[0-9]+$`; must exist in the REQ it cites |
| VerificationObligation | `kind` | string | enum `test-case` \| `structural-check`. `dogfood` is deliberately excluded — BR-5 requires every kind to report an executed-case count, which a dogfood run cannot. See Open Questions. |
| VerificationObligation | `artifact` | string | test file path + case name, or lint-check name; resolved path must exist after implementation |
| VerificationObligation | `benign_path` | boolean | true when the obligation includes a must-not-fire case (required for detector-shaped rules) |
| Task (frontmatter/body) | `## Verification` | block | zero or more VerificationObligation rows |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `obligations_emitted` | `/architect` finishes task breakdown | obligations grouped by task |
| `coverage_gate_evaluated` | `/validate` runs on architecture + tasks | unmapped BR/AC list |
| `coverage_gate_failed` | ≥1 numbered BR has no obligation | the unmapped rule ids |

_Permissions: not applicable — no runtime actors, no roles. Section omitted deliberately._

## Business Rules

- [ ] BR-1: `/architect` emits a `## Verification` block in each task file, listing every BR and AC that task discharges and the concrete artifact that proves each one. `task-template.md` gains the section (additive; existing task files without it stay valid).
- [ ] BR-2: `/validate`, run on architecture + tasks, reports every numbered **BR and AC** in the REQ that has no verification obligation anywhere in the task set, naming the unmapped rule ids. Gating both is load-bearing: acceptance criteria do not reduce to business rules — REQ-593 carries cross-repo and `/status` ACs with no one-to-one BR — so gating BRs alone would leave half of LESSON-330's omission class open. In **epoch 1 this report is advisory**: it is surfaced as a finding and does not block advancement, mirroring how REQ-425's corruption detector shipped as an advisory `/analyze` dimension before hardening. Promotion to a blocking gate is a named follow-up REQ, taken once the corpus carries obligations (informed by LESSON-330, REQ-425).
- [ ] BR-3: obligation `kind` resolves from `.adlc/config.yml` `stack:` **when that file exists and declares one**. A markdown-only surface (a SKILL.md change) maps to `structural-check` against `tools/lint-skills`, never to a behavioral test; a surface with a real runner maps to `test-case`. No framework name is hardcoded in the skill (informed by LESSON-331, and conventions' "no test runner" reality for skills).
- [ ] BR-4: any BR that describes detection, refusal, or a halt must carry at least one `benign_path` obligation. Like BR-2's coverage report, this check is **advisory in epoch 1** and hardens with it — the two are obligation-shape judgments and must share a posture, or `/validate` presents a mixed gate where one new check blocks and the other does not — a case asserting the detector does **not** fire on the legitimate actor. A detector validated only against adversarial inputs ships broken and passes its own suite (informed by LESSON-440).
- [ ] BR-5: a verification run that exits 0 having done no work fails the gate — a vacuous scan is a failure, not a pass. "Work done" is defined **per kind**, because the kinds are not commensurable: a `test-case` obligation reports executed test cases, and a `structural-check` obligation reports **files scanned** by the lint invocation (many obligations legitimately share one invocation, so per-obligation case counts do not exist for that kind). Either count reaching zero fails the gate, and this failure is **blocking from epoch 1** — unlike BR-2 and BR-4 it is not a coverage judgment but evidence that the verification did not run at all, which is the REQ-435 vacuous-scan class (informed by REQ-435, LESSON-020).
- [ ] BR-6: `/architect` may draft obligation boilerplate through the shared delegate gate (`adlc-write`), but the drafted output is untrusted — every cited rule id and artifact path is validated against the REQ and the filesystem before it is written into a task file (informed by LESSON-008).
- [ ] BR-7: no new skill directory. This extends `/architect`, `/validate`, and `task-template.md` only (conventions: don't create skills casually).
- [ ] BR-8: all shell is BSD- and zsh-safe: no `\b` in `grep -E` (informed by LESSON-013), no bare `$<digit>`, no `status` variable, no unquoted word-splitting (informed by LESSON-329, LESSON-335).
- [ ] BR-9: cross-repo REQs group obligations by the task's `repo:` frontmatter; each repo's obligations resolve against that repo's stack and its own artifact paths (informed by REQ-484).
- [ ] BR-10: the coverage gate is evaluated against the REQ's numbered rules as written. A REQ with zero numbered BRs passes trivially and emits a notice — it does not fail, and it does not invent rules to check.
- [ ] BR-11: when `.adlc/config.yml` is absent or declares no `stack:`, kind resolves from the **changed surface itself**: a task whose files are all `*.md` maps to `structural-check`; any other surface maps to `test-case`. This fallback is not an edge case — adlc-toolkit itself has no `config.yml`, so the dogfooding repo reaches BR-3 only through this branch, and every other skill that reads that file (`architect/SKILL.md:71`, `validate/SKILL.md:67`) reads only its `repos:` block and declares an explicit absent-file fallback. No skill has ever read `stack:`, so there is no legacy behavior to inherit.

## Acceptance Criteria

- [ ] Running `/architect` on a REQ with BR-1..BR-5 produces task files whose `## Verification` blocks collectively cite all five rule ids.
- [ ] Removing one BR's obligation from the task set causes `/validate` to report that specific rule id as unmapped, as an advisory finding that does not block advancement.
- [ ] Removing one AC's obligation is reported identically — AC coverage is gated on the same footing as BR coverage.
- [ ] For a SKILL.md-only REQ in this repo — which has no `.adlc/config.yml` — obligations resolve through BR-11 to `structural-check` entries naming `tools/lint-skills` checks, with no test-file path emitted and no error about the missing config.
- [ ] For a project whose `.adlc/config.yml` declares a test runner, obligations resolve to `test-case` entries with a file path and case name.
- [ ] A BR worded as a detection/refusal rule that has no `benign_path` obligation is reported by BR-4's check as an advisory finding that does not block — verified with a fixture REQ containing exactly one such rule.
- [ ] A verification run whose scan matches zero files reports failure, not success — verified by pointing the check at an empty directory (the REQ-435 vacuous-scan regression).
- [ ] A delegate-drafted obligation citing `BR-99` (absent from the REQ) or a nonexistent artifact path is dropped before the task file is written.
- [ ] A REQ with no numbered BRs passes `/validate` with a notice and no failure.
- [ ] An existing task file with no `## Verification` section still validates (backward compatibility).
- [ ] A cross-repo REQ produces obligations grouped per `repo:`, each resolving against that repo's declared stack.

## External Dependencies

- `tools/lint-skills` (already shipped) as the `structural-check` execution surface for markdown surfaces
- No new test framework, runner, or service is introduced by this REQ

## Assumptions

- The REQ's Business Rules are numbered and individually addressable (`BR-1`, `BR-2`, …). This holds for every spec written from the current template; unnumbered legacy prose rules are not gate-able and fall under BR-10's trivial pass.
- `test-auditor`'s post-hoc coverage audit remains valuable and is not replaced by this REQ — the obligation is a pre-commitment, the audit is the independent check on whether it was honored.
- A rule-to-artifact mapping authored at architecture time will sometimes be wrong once implementation reality lands. The gate checks that a mapping exists and resolves, not that it is the ideal test.

## Open Questions

- [ ] Should Phase 5's reflector and reviewers receive the obligation list as input, or would that anchor them and reduce the independent-omission-catching value LESSON-330 credits them with?
- [ ] Does `dogfood` (invoke the skill on a real REQ and inspect artifacts) belong as a first-class `kind`, given it is this repo's actual testing convention but is not machine-checkable?
- [x] ~~Should the coverage gate be blocking from the start, or advisory for one epoch?~~ **Resolved 2026-08-27: advisory first**, mirroring REQ-425's corruption detector, which shipped as an advisory `/analyze` dimension before hardening. A gate that blocks on day one would fail every in-flight REQ written before obligations existed. Hardening to blocking is a follow-up REQ once the corpus carries obligations. This resolution is now carried by BR-2 itself and by AC-2 — it is not standalone prose that a rule can contradict.
- [ ] How should an intentionally untestable BR (documentation-only, or a policy statement) be marked so it does not permanently fail the gate?

## Out of Scope

- Playwright, JMeter, Swagger/Postman contract testing, or any specific framework integration. Framework choice is the consumer project's, read from config.
- Self-healing or auto-repairing test selectors.
- Performance and load testing.
- Generating the test *bodies* for behavioral suites — this REQ specifies obligations and gates their existence; `task-implementer` still writes the code.
- Retrofitting obligations onto the 42 existing specs.

## Retrieved Context

- LESSON-440 (lesson, score 8): Every collision/anomaly detector needs a benign-path AC
- REQ-484 (spec, score 8): Cross-repo footprint publishing — per-repo attribution from tasks
- LESSON-329 (lesson, score 8): Skill bash runs under the operator's shell (zsh) — dogfood under it
- LESSON-330 (lesson, score 8): The Phase-5 review catches OMITTED requirements, not just bugs
- LESSON-313 (lesson, score 8): A global counter's namespace is its bootstrap scan root
- LESSON-023 (lesson, score 8): When mirroring a hardened pattern to a sibling, port the rationale
- LESSON-331 (lesson, score 7): Closed output schemas silently rot — pair with a pure structural test
- REQ-435 (spec, score 7): lint-skills worktree-root scan — vacuous-scan regression coverage
- LESSON-441 (lesson, score 6): Repo-local-first sourcing means a canonical fix is not deployed until re-synced
- REQ-545 (spec, score 6): Wire the REQ id pre-push recheck into /proceed branch creation
- LESSON-335 (lesson, score 6): Four zsh-executor/templating hazards in SKILL.md scripts
- REQ-473 (spec, score 6): Global cross-repo LESSON-ID counter
- REQ-441 (spec, score 6): Global cross-repo BUG-ID counter
- LESSON-020 (lesson, score 6): A shell function shared across SKILL.md steps must be a sourced partial
- REQ-436 (spec, score 6): Extract analyze telemetry helper to a sourceable POSIX partial
