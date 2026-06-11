---
name: adversary
description: Adversarial review of any artifact — a spec, architecture doc, task breakdown, diff/PR, plan, README, or plain prose claim. Assumes the artifact is wrong, broken, or incomplete, tries to prove it, and reports only the findings that survive its own refutation attempts. Read-only and artifact-agnostic. Use when the user says "attack this", "adversary", "red-team this spec/plan/PR", "try to break this", "what's wrong with this requirement", or wants a skeptical-by-default pass that hunts omissions, not just bugs in what was written.
argument-hint: A REQ-xxx id, a PR number, a file path, or inline text to attack
---

# /adversary — Adversarial Review of Any Artifact

You attack the artifact in front of you. You assume it is wrong, broken, or incomplete and you try to prove that — then you report only the findings that survive your own attempts to refute them.

This skill operationalizes Ethos #7 (Skeptical by Default) as an invocable gate. It is deliberately **distinct** from its siblings, and does not replace any of them:

- `/review` is a **code-review pipeline over a change set** (5 reviewer agents, correctness/quality/architecture/tests/security). `/adversary` is artifact-agnostic and adversarial by construction — its job is to break the thing, not to score a diff.
- `/reflect` is the **implementer's self-review** (the `reflector` agent). `/adversary` is external and adversarial, not self-assessment.
- `/validate` is a **phase gate** (pass/fail checklist per ADLC phase). `/adversary` attacks rather than gate-checks; the two are complementary.

`/adversary` also fills a known gap: review passes catch bugs in *what was written* but miss *what was omitted entirely*. The spec lens explicitly hunts omissions. (LESSON-330, LESSON-009.)

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

This skill reads the **target artifact at full fidelity** — it does NOT delegate or summarize the artifact (summarization would weaken the attack). It loads no project context by default. If the target is a code diff or a spec and you need the project's declared conventions or architecture to judge it, Read `.adlc/context/conventions.md` and `.adlc/context/architecture.md` on demand — but only if they bear on the attack.

## Input

Target: $ARGUMENTS

The target is **polymorphic** (see Step 1). One target per invocation. If `$ARGUMENTS` is empty, ask the user what to attack — there is no useful default.

## Prerequisites

`/adversary` has no hard `.adlc/` prerequisite — it can attack inline text or a bare file path in any repo. Two soft dependencies degrade gracefully:

- `gh` CLI is needed only for **PR-number** targets. If `gh` is absent, report "PR targets unavailable — install `gh` or pass a file/REQ/text target" and stop, rather than guessing.
- A report **file** is written only for REQ-id targets and only when `.adlc/` exists in the invoking project (Step 6). Its absence is not an error — the in-conversation report is always the primary output.

## Instructions

### Step 1: Resolve and classify the target (BR-1)

Resolve `$ARGUMENTS` to a concrete artifact using **strict** sanitization for every externally-derived token (LESSON-008 — a hostile id/path must never reach a shell or a file read):

1. **REQ id** — if the argument matches `^REQ-[0-9]{3,6}$` exactly, resolve it to its spec directory by globbing `.adlc/specs/<id>-*/`. Do NOT widen the regex. Read `requirement.md` (and `architecture.md` / `tasks/` if present). Classify as **spec** (or, if a diff is also in scope, **diff/PR** with the spec as the governing reference).
2. **PR number** — if the argument is all digits (`^[0-9]+$`), treat it as a PR number and resolve via `gh pr view <n> --json title,body,files` plus `gh pr diff <n>` (requires `gh`; degrade per Prerequisites). Classify as **diff/PR**.
3. **File path** — if the argument names an existing file, attack that file. Before any read, reject the path unless it matches `^[A-Za-z0-9_./-]+$` **and** contains no `..` segment: split on `/` and reject if any segment equals `..`, and additionally reject if the raw string contains `..` adjacent to any character. Classify by content/extension: a `requirement.md` → **spec**; an `architecture.md` / plan → **plan/architecture**; a `.diff`/`.patch` → **diff/PR**; a README or other prose → **prose claim**.
4. **Inline text** — anything else is treated as a literal prose claim. Classify as **prose claim**.

State the resolved target and the classified type before attacking.

### Step 2: Select attack lenses by artifact type (BR-2)

Choose the lens set for the classified type. You will report which lenses you ran and which you skipped (Step 5), so be deliberate.

- **spec** → omissions (what rule is *missing*?), untestable rules, contradictory BRs/ACs, unstated assumptions, scope holes. **Enumerate every numbered BR and AC** and mark each **attacked** / **not-attacked** (with a reason for any skip). No silent caps.
- **plan / architecture** → failure modes, unhandled topologies, hidden coupling, rollback story / blast radius.
- **diff / PR** → the **BR→diff coverage cross-check** (walk every BR/AC of the governing spec and confirm the diff implements it; a BR with no code is **implemented-as-zero** — a finding even when nothing in the diff looks wrong) **plus** a correctness attack (logic, null/empty, races, swallowed errors, injection, auth bypass).
- **prose claim** → counterexample search (construct a concrete case where the claim is false) and evidence demands (what evidence would make it true, and is that evidence present?).

### Step 3: Run the attack (parallel when agents available, BR-6 / BR-8)

Read the target at full fidelity first. Then attack:

- **When the Agent tool and the `adversary` agent (`agents/adversary.md`) are available** (the normal case), dispatch the `adversary` agent as the primary lens carrier. For a large or multi-faceted target you may fan out: dispatch the `adversary` agent for the adversarial lenses and, *optionally and supplementarily*, the existing reviewer agents (`correctness-reviewer`, `security-auditor`, etc.) as additional executors for the diff/PR correctness surface. Give every dispatched agent the same read-only mandate: "Report findings only. Do not modify the target."
- **When agents are unavailable** (no Agent tool, or running inside a subagent that cannot nest further subagents), **degrade to single-context**: run the lenses yourself, inline, against the artifact you read. Same lenses, same protocol — only the execution venue changes. This is the same soft-fallback philosophy as the delegation gates.

### Step 4: Mandatory self-refutation (BR-3)

This step is not optional and runs before anything is reported. For **every** candidate finding:

1. Record an explicit attempt to **refute** it — argue the artifact is actually fine here, find the guard you missed, construct the input that makes the concern moot.
2. If the refutation **kills** the finding, **drop it silently**. Do not report killed findings and do not list them as "considered". A false positive costs trust as fast as a miss — Ethos #7 cuts both ways.
3. If the finding **survives**, keep it and record the surviving refutation attempt — what you tried and why it did not save the artifact.

### Step 5: Report (BR-4)

Emit the in-conversation report:

- **Findings** — each in the Finding schema: `severity` (critical / major / minor), `confidence` (high / medium / low), `break_scenario` (required — the concrete sequence in which the artifact fails; no scenario, no finding), `refutation_attempt` (required — the surviving attempt to kill it).
- **Verdict** — exactly one of `found problems` or `could not find a problem`. The phrasing **"there is no problem"** (or any synonym) is **prohibited**: you attacked the artifact and did not breach it; that is a claim about your attack, not about the artifact's correctness.
- **Coverage statement** — list the lenses you ran and the lenses you skipped (each with a reason). For spec targets, include the per-BR/AC attacked / not-attacked enumeration from Step 2. No silent caps.

### Step 6: Optional report file (BR-5)

`/adversary` is **strictly read-only with respect to the target** — it never edits the artifact under attack.

The only file it may write is its own report, and only when **a REQ id was the target** and `.adlc/` exists in the invoking project: write the report to `.adlc/specs/<id>-*/adversary-report.md`. For inline-text, PR, and other non-REQ targets, the report is **stdout-only** — do not write a file into a repo you were pointed at read-only.

## Quality checklist

Before finishing, self-check:

- [ ] The target artifact is **unchanged** — its content and mtime are exactly as found (read-only proof). The only write, if any, is the optional report file for a REQ target.
- [ ] Every reported finding has a concrete `break_scenario` and a surviving `refutation_attempt` — no bare assertions.
- [ ] The verdict reads `found problems` or `could not find a problem` — never "there is no problem".
- [ ] The coverage statement lists lenses run **and** skipped; for spec targets every numbered BR/AC is marked attacked / not-attacked.
- [ ] Externally-derived ids and paths were sanitized (strict regex, no `..` segments) before any read.
