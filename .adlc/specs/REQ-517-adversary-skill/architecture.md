---
id: REQ-517
title: "/adversary Skill — Adversarial Review of Any Artifact"
phase: architecture
created: 2026-06-11
updated: 2026-06-11
---

# Architecture — REQ-517 `/adversary`

## Overview

`/adversary` is a new standalone, read-only skill that attacks any artifact
(spec, architecture, task breakdown, diff/PR, plan, README, or inline prose claim)
and reports only the findings that survive its own refutation attempts. It
operationalizes Ethos #7 (Skeptical by Default) as an invocable gate. It is
sibling to — and deliberately distinct from — `/review` (code-review pipeline over
a change set) and `/reflect` (implementer self-review).

This is a pure-markdown REQ in the adlc-toolkit (`stack: ["markdown"]`,
`deployable: false`). No executable code ships; the "tests" are dogfooding +
`lint-skills` (per conventions.md "Code is markdown, not code").

## Deliverables

| Artifact | Path | Purpose |
|---|---|---|
| Skill | `adversary/SKILL.md` | The `/adversary` slash command (polymorphic input, attack-lens selection, mandatory self-refutation, verdict + coverage statement) |
| Agent | `agents/adversary.md` | The dedicated adversary lens carrier (BR-8) — read-only tools, reviewer-class model tier, Finding-schema output. The 18th agent. |
| Catalog | `README.md` | Add `/adversary` to the Skills table (AC) |

No new partials, templates, or workflows. No changes to `/review`, `/reflect`,
`/validate` behavior (Out of Scope). No Kimi/delegation wiring (Out of Scope —
the artifact must be read at full fidelity).

## Anatomy — `adversary/SKILL.md`

Follows the canonical skill shape (architecture.md "Skill anatomy"):

1. **Frontmatter**: `name: adversary`, `description`, `argument-hint`.
2. **Title + one-line framing.**
3. **Ethos injection**: the canonical two-level partial macro — never hardcode.
4. **Context loading**: minimal; the target artifact is read on demand (full
   fidelity, no delegation). Conventions/architecture loaded only if needed.
5. **Input**: `$ARGUMENTS` is the polymorphic target (BR-1).
6. **Prerequisites**: degrade gracefully; `gh` optional (degrade to "PR targets
   unavailable" when absent).
7. **Instructions** (numbered):
   - **Step 1 — Resolve & classify the target (BR-1):** polymorphic resolution.
     A `REQ-xxx` id → its spec directory (strict `^REQ-[0-9]{3,6}$`, reject `..`
     segments — LESSON-008). A bare integer → a PR number resolved via `gh pr
     view` (degrade gracefully if `gh` absent). An existing path → file(s), with
     `..`-segment rejection. Anything else → inline prose text. Classify the
     artifact type (spec / plan-or-architecture / diff-or-PR / prose claim) to
     drive lens selection.
   - **Step 2 — Select attack lenses by type (BR-2):** spec → omissions,
     untestable rules, contradictory BRs, unstated assumptions, scope holes;
     plan/architecture → failure modes, unhandled topologies, hidden coupling,
     rollback story; diff/PR → BR→diff coverage cross-check + correctness attack;
     prose → counterexample search + evidence demands. For specs, enumerate every
     numbered BR/AC and mark each attacked / not-attacked.
   - **Step 3 — Run the attack (parallel when agents available, BR-6/BR-8):**
     when the Agent tool and `agents/adversary.md` (and optionally the reviewer
     agents) are available, dispatch lenses across them; otherwise degrade to
     single-context in-line attack. Read the target at full fidelity first.
   - **Step 4 — Mandatory self-refutation (BR-3):** before any finding is
     reported, record an explicit attempt to refute it. Findings killed by their
     own refutation are dropped silently. Surviving findings carry the surviving
     refutation attempt.
   - **Step 5 — Report (BR-4):** findings list (Finding schema), a verdict that
     distinguishes "could not find a problem" from the prohibited "there is no
     problem", and a coverage statement (lenses run / lenses skipped + reasons).
   - **Step 6 — Optional report file (BR-5):** read-only w.r.t. the target;
     optionally write a report under the invoking project's `.adlc/` ONLY when a
     REQ id was the target. Inline-text / PR / non-REQ targets are stdout-only
     (Open Question resolution).
8. **Quality checklist**: read-only proof reminder; verdict-phrasing guard;
   coverage-statement completeness.

### Finding schema (BR shared with the agent)

```
severity:            critical | major | minor
confidence:          high | medium | low
break_scenario:      required — the concrete failure sequence; no scenario, no finding
refutation_attempt:  required — what was tried to kill it and why it survived
```

Report `verdict`: `"found problems"` | `"could not find a problem"` — never
"there is no problem".

## Anatomy — `agents/adversary.md`

Matches the structural conventions of the other 17 agents (architecture.md
"Agent anatomy"; modeled on `correctness-reviewer.md` + `reflector.md`):

- **Frontmatter**: `name: adversary`, `description` (when to dispatch it),
  `model: opus` (reviewer-class tier — concrete fallback per BR-8 since REQ-516's
  tier map has not landed in this repo), `tools: Read, Grep, Glob, Bash`
  (read-only — no Edit/Write).
- **Body**: role (attack the artifact, assume it is wrong); the artifact-type →
  attack-lens map (mirrors BR-2); the mandatory self-refutation protocol (BR-3);
  the read-only constraint (BR-5); the Finding-schema output format (severity,
  confidence, break_scenario, refutation_attempt) and the verdict-phrasing rule
  (BR-4).

## Sibling-integration audit (BR-9, explicit not duplicative)

| Skill | Relationship | Decision |
|---|---|---|
| `/review` | Code-review pipeline over a change set; 5 reviewer agents. | `/adversary` is artifact-agnostic + adversarial-by-construction. Reference the reviewer agents as *optional* supplementary lens executors (Assumptions); do not re-implement their checklists. |
| `/reflect` | Implementer self-review (reflector agent). | `/adversary` is external/adversarial, not self-assessment. No shared body; reference only. |
| `/validate` | Phase-gate checklist (pass/fail per phase). | `/adversary` attacks rather than gate-checks; complementary. No overlap to extract. |

No shared adversarial *language block* is large enough to warrant a partial in
v1 (the attack-lens text is unique to the adversary). The audit conclusion — keep
it referenced, not copy-pasted — is recorded in the SKILL.md sibling-distinction
framing. (LESSON-005, LESSON-020.)

## Shell-safety & dogfooding (BR-7)

All fenced shell in `adversary/SKILL.md` is BSD- and zsh-safe and POSIX-only
(conventions.md "Bash in skills"): no GNU-only flags, `${1}` not `$1` for
positionals, `$(0)`/`$(1)` for awk fields, balanced `$(`/`)` and `$((`/`))`, no
`local` in `sh` fences, no cross-fence function reuse. Verification (Verify phase):
run `python3 tools/lint-skills/check.py` (clean pass required), and dogfood the
fenced blocks under both `zsh -c` and `bash -c`. (LESSON-329, LESSON-335,
LESSON-013.)

## ADRs

- **ADR-1 — Dedicated agent IS in scope for v1.** Per the maintainer resolution
  in the spec's Open Questions (2026-06-11), `agents/adversary.md` ships in this
  REQ (BR-8), not deferred. The skill uses it for parallel lenses and degrades to
  single-context (BR-6).
- **ADR-2 — `model: opus` as the concrete tier.** BR-8 mandates the
  reviewer-class tier "consistent with REQ-516's tier map" with a concrete
  fallback of `model: opus` if REQ-516 has not landed. REQ-516 has not landed in
  this repo (no tier-map partial present), so we hardcode `model: opus`, matching
  every existing reviewer agent (`correctness-reviewer`, `security-auditor`, etc.).
- **ADR-3 — Report-file scope.** Per the Open-Question resolution, a report file
  is written only for REQ-id targets (under the invoking project's `.adlc/`);
  inline-text / PR / non-REQ targets are stdout-only. This keeps `/adversary`
  from littering files in repos it was pointed at read-only.
- **ADR-4 — No delegation layer.** Out of Scope per the spec (LESSON-010):
  summarizing the artifact would weaken the attack, so `/adversary` reads at full
  fidelity and never gates on Kimi. The SKILL.md therefore has NO `ADLC_DISABLE_KIMI`
  gate — which also means the `lint-skills` canonical-helper check does not apply
  to it (that check only fires on skills that contain `ADLC_DISABLE_KIMI`).

## Task graph

```
TASK-001 (agent: agents/adversary.md)  ─┐
                                         ├─→ TASK-003 (README catalog + dogfood/lint verify)
TASK-002 (skill: adversary/SKILL.md) ───┘
```

- TASK-001 and TASK-002 are independent (different files) but TASK-002 references
  the agent contract, so authoring the agent first is natural. In subagent mode
  they run sequentially: TASK-001 then TASK-002.
- TASK-003 (catalog entry + lint/dogfood gate) depends on both — it documents the
  finished skill and runs the shell-safety verification over the authored SKILL.md.

All tasks target the primary repo `adlc-toolkit` (single-repo mode).
