---
id: REQ-517
title: "/adversary Skill — Adversarial Review of Any Artifact"
status: approved
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "adlc/adversary"
domain: "adlc"
stack: ["markdown"]
concerns: ["review", "quality"]
tags: ["adversarial-review", "skill", "red-team", "skeptical-by-default"]
---

## Description

A new standalone skill, `/adversary`, that takes *any* artifact — a requirement
spec, an architecture doc, a task breakdown, a diff or PR, a plan, a README, or a
plain prose claim — and attacks it: assumes it is wrong, broken, or incomplete and
tries to prove that, then reports only the findings that survive its own attempts
at refutation.

This operationalizes Ethos #7 (Skeptical by Default) as an invocable gate. It is
deliberately distinct from `/review` (a code-review pipeline over a change set)
and `/reflect` (self-review by the implementer): `/adversary` is artifact-agnostic,
read-only, and adversarial by construction — its job is to break the thing, not to
assess it. It also fills a known gap: review passes catch bugs in what was written
but miss what was *omitted* entirely; the adversary's spec-mode explicitly hunts
omissions. (informed by LESSON-330, LESSON-009)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| AdversaryInput | target | string | file path(s), REQ-xxx id, PR number, or inline text; required |
| Finding | severity | enum | critical / major / minor |
| Finding | confidence | enum | high / medium / low |
| Finding | break_scenario | string | required — the concrete sequence in which the artifact fails; no scenario, no finding |
| Finding | refutation_attempt | string | required — what was tried to kill the finding and why it survived |
| Report | verdict | enum | "found problems" / "could not find a problem" — never "there is no problem" |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| adversary report | skill completes | findings list, verdict, coverage statement (what was and was not attacked) |

## Business Rules

- [ ] BR-1: Input is polymorphic: a `REQ-xxx` id resolves to its spec directory, a PR number resolves via `gh`, paths resolve to files, and anything else is treated as inline text. Id and path resolution use the strict sanitization patterns already established for untrusted tokens (`^REQ-[0-9]{3,6}$`, no `..` segments). (informed by LESSON-008)
- [ ] BR-2: Attack lenses are selected by artifact type — spec: omissions, untestable rules, contradictory BRs, unstated assumptions, scope holes; plan/architecture: failure modes, unhandled topologies, hidden coupling, rollback story; diff/PR: BR→diff coverage cross-check plus correctness attack; prose claim: counterexample search and evidence demands. For specs, every numbered BR/AC is enumerated and marked attacked/not-attacked. (informed by LESSON-330)
- [ ] BR-3: Self-refutation is mandatory: before a finding is reported, the skill records an explicit attempt to refute it; findings killed by their own refutation are dropped silently. The report shows the surviving refutation attempt per finding (false positives cost trust as fast as misses — Ethos #7).
- [ ] BR-4: The final verdict must distinguish "I could not find a problem" from "there is no problem"; the latter phrasing is prohibited. The report includes a coverage statement listing lenses run and lenses skipped (with reasons) — no silent caps.
- [ ] BR-5: The skill is strictly read-only with respect to the target: it never edits the artifact. Output is the in-conversation report plus an optional report file under the invoking project's `.adlc/` when a REQ id was the target.
- [ ] BR-6: When the toolkit's review agents are available (`correctness-reviewer`, `security-auditor`, etc.) the skill may parallelize lenses across them, but it must degrade gracefully to single-context operation when agents are unavailable — same soft-fallback philosophy as the delegation gates.
- [ ] BR-7: All fenced shell in the SKILL.md is BSD- and zsh-safe and passes `lint-skills`; the skill is dogfooded by executing its blocks under `zsh -c` and `bash -c`. (informed by LESSON-329, LESSON-335, LESSON-013)
- [ ] BR-8: A dedicated `agents/adversary.md` agent definition ships with this REQ (decided 2026-06-11): it encodes the attack-lens + mandatory-self-refutation protocol so other skills and workflows can dispatch it as a lens via the Agent tool, declares read-only tools (Read, Grep, Glob, Bash), and carries the reviewer-class model tier consistent with REQ-516's tier map (concrete fallback if REQ-516 has not landed: `model: opus`). The `/adversary` skill uses this agent for parallel lenses when available and degrades to single-context per BR-6.
- [ ] BR-9: Sibling integration is explicit, not duplicative: `/validate`, `/review`, and `/reflect` are audited for overlap, and any shared adversarial language is referenced (or extracted to a partial), not copy-pasted. (informed by LESSON-005, LESSON-020)

## Acceptance Criteria

- [ ] Run against a draft spec with a deliberately omitted business rule and a contradictory pair of BRs: the report flags both, each with a break scenario and a surviving refutation attempt.
- [ ] Run against a diff whose spec has one unimplemented BR: the BR→diff cross-check reports it as implemented-as-zero.
- [ ] Run against a prose claim with a known counterexample: the counterexample is produced.
- [ ] Run against a sound artifact: verdict reads "could not find a problem" (with coverage statement), not "no problems exist".
- [ ] The target file's mtime/content are unchanged after every run (read-only proof).
- [ ] `lint-skills` passes; README.md skill catalog and the skills listing include `/adversary`.
- [ ] Linux parity: all fenced shell in the SKILL.md executes correctly under Ubuntu bash as well as macOS zsh.
- [ ] `agents/adversary.md` exists, passes the same structural conventions as the other 17 agents (frontmatter with model/tier, tool restrictions), and dispatching it directly via the Agent tool on a sample spec returns findings in the Finding schema (severity, confidence, break_scenario, refutation_attempt).

## External Dependencies

- `gh` CLI for PR-number targets (already a toolkit dependency; degrade to "PR targets unavailable" when absent).

## Assumptions

- The existing review agents' prompts remain reusable as supplementary lens executors; the new dedicated `adversary` agent (BR-8) is the primary lens carrier.

## Open Questions

- [ ] Should `/proceed` Phase 5 optionally invoke `/adversary` against the spec *before* implementation (shift-left), or stay post-implementation only? Proposed: out of scope for v1, noted as a follow-up REQ candidate. (Resolved 2026-06-11: dedicated `adversary` agent IS in scope for v1 — BR-8, per maintainer.)
- [ ] Report file location for non-REQ targets (inline text, PRs in other repos): proposed stdout-only, no file.

## Out of Scope

- Auto-fixing anything it finds (read-only by rule).
- Replacing or modifying `/review`, `/reflect`, or `/validate` behavior in this REQ.
- Wiring `/adversary` into `/proceed`/`/sprint` pipelines (follow-up if v1 proves useful).
- Delegation-layer integration (no Kimi/delegate gating in v1 — the artifact under attack must be read with full fidelity, summarization would weaken the attack). (informed by LESSON-010)

## Retrieved Context

- LESSON-330 (lesson, score 3): review catches omitted requirements
- LESSON-313 (lesson, score 3): global counter scope is its scan root
- LESSON-023 (lesson, score 3): mirror the rationale not just mechanism
- LESSON-019 (lesson, score 3): presence guards rot when indirection moves
- LESSON-020 (lesson, score 3): cross-block shell state and guard rot
- LESSON-013 (lesson, score 3): BSD grep word-boundary silent failure
- LESSON-010 (lesson, score 3): delegated-model silent truncation and advisory anchoring
- LESSON-012 (lesson, score 3): structural telemetry beats prose enforcement
- LESSON-008 (lesson, score 3): skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 3): hotfix verify finds what original verify missed
- LESSON-004 (lesson, score 3): drop proceed canary and snapshot phases
- LESSON-005 (lesson, score 3): sibling skill anti-pattern audit
- LESSON-335 (lesson, score 2): zsh-executor and arg-templating hazards
- LESSON-355 (lesson, score 2): pipeline-runner cannot merge from sandbox
- LESSON-356 (lesson, score 2): probe gcloud auth before dispatching GCP REQs
