---
id: BUG-060
title: "/sprint Step 2 spec-existence preflight is decoupled from /proceed Step 0's base ref"
status: resolved
severity: high
created: 2026-05-18
updated: 2026-05-18
resolved_by: "PR #61 (commit 2a45266) — duplicate, fixed independently before this report"
component: "adlc/sprint"
domain: "pipeline-orchestration"
stack: ["claude-skills", "git"]
concerns: ["correctness", "developer-experience", "wasted-compute"]
tags: ["sprint", "preflight", "spec-existence", "base-ref", "proceed", "worktree"]
---

## Description

`/sprint` Step 2 verifies each REQ's spec exists at `.adlc/specs/REQ-xxx-*/requirement.md`,
but it checks that path **in the orchestrator's own invoking worktree's filesystem**. Each
dispatched `pipeline-runner` then runs `/proceed` Step 0, which does
`git checkout main && git pull` *before* its own spec-existence preflight. The two
preflights resolve the spec against **different git refs**: `/sprint` checks the working
tree it was launched in; `/proceed` checks whatever ref Step 0 lands the worktree on
(canonically `main`).

When specs are authored/drafted on a branch that is not yet merged to `/proceed`'s base
ref (the normal `/spec` → `/validate` → `/sprint` flow produces specs committed to a draft
branch, not yet promoted), `/sprint` pre-flight **passes** (the specs are on disk where you
just authored them) but every parallel runner independently **fails** Phase 0 with "spec
does not exist". A check that should fail **once** at sprint-planning time instead fails
**N times**, once per parallel runner, each after burning a worktree + runner context, and
leaves `*-MISSING-SPEC` cruft behind.

## Reproduction Steps

1. On a non-`main` branch, run `/spec` then `/validate` to author one or more REQ specs.
   The specs are committed to that branch (e.g. `origin/dev`), not yet promoted to `main`.
2. From that same worktree, run `/sprint REQ-aaa REQ-bbb`.
3. Observe `/sprint` Step 2 pre-flight reports every REQ as **Eligible: Yes** (the
   `requirement.md` files are present in the orchestrator's working tree).
4. `/sprint` dispatches N `pipeline-runner` agents.
5. Each runner's `/proceed` Step 0 runs `git checkout main && git pull`, then its
   own preflight checks `.adlc/specs/REQ-xxx-*/requirement.md` — which is **not on
   `main`** → the runner halts "spec does not exist", after a worktree was created.

## Expected Behavior

`/sprint` Step 2 should detect the spec is absent on the ref `/proceed` Step 0 will
base its worktrees on, fail that REQ **once** in the pre-flight table with a clear,
actionable issue (e.g. "spec not on `<base-ref>` — promote/merge it first"), and never
dispatch a runner that is guaranteed to fail Phase 0.

## Actual Behavior

`/sprint` Step 2 passes the REQ (spec is present in the orchestrator's local working
tree). N runners are dispatched; each independently fails `/proceed` Phase 0 with
"spec does not exist", each after creating + abandoning a worktree, leaving
`*-MISSING-SPEC` directories. Failure is discovered N times, deep, instead of once,
early.

## Environment

- Platform: adlc-toolkit (`/sprint` skill source — `sprint/SKILL.md`)
- Version: branch `fix/bug-060-sprint-spec-preflight-base-ref` off `origin/main` @ 5e71388

## Root Cause

Confirmed (Phase 2). `sprint/SKILL.md` Step 2 item 1 validated spec existence via a
filesystem check in the orchestrator's invoking worktree, with no `git`-ref awareness.
`/proceed` `SKILL.md` Step 0 resolved the spec against the ref it bases worktrees on
(pre-fix: a hardcoded `git checkout main && git pull`). The two preflights resolved the
spec against **different refs**, so `/sprint` could pass a REQ whose spec is only on an
unmerged draft branch while every dispatched runner then failed Phase 0 — N-deep instead
of once. The correct fix couples `/sprint`'s preflight to the ref `/proceed` Step 0
actually uses (not a hardcoded branch).

## Resolution

**Duplicate — fixed by [PR #61] before any independent code change.** This bug was
filed and root-caused via `/bugfix`; during Phase 2 analysis, PR #61
(`fix/lesson-036-pipeline-base-ref-hygiene`, encoding admin-api `LESSON-036`) merged to
`main` (5e71388 → 2a45266, 2026-05-18). PR #61's change to `sprint/SKILL.md` Step 2 is a
**1:1 match** for this bug's expected behavior and a **strict superset**:

- `sprint/SKILL.md:47` precondition — `git fetch origin` first; eligibility checked
  against `origin/<integration-branch>`, not the local working tree; ineligible message
  `spec not on <integration-branch> — land its spec PR first`.
- Generalizes the base ref from a hardcoded `main` to a detected **integration branch**
  (`staging` in two-branch repos, else `main`) — exactly the ref-coupling this bug
  required.
- Also hardens `/proceed` Step 0/5/6/8 and the `pipeline-runner` stale-ref false-block
  (out of scope for this bug but closes the same class).

No independent fix was written (it would only duplicate merged work and conflict with
the new `origin/main`). This report is retained as the audit record for the
globally-consumed `BUG-060` counter id and to document the supersession.

## Files Changed

- None by BUG-060 — the fix is [PR #61] @ commit `2a45266`
  (`sprint/SKILL.md`, `proceed/SKILL.md`, `agents/pipeline-runner.md`).
- `.adlc/bugs/BUG-060-sprint-spec-preflight-base-ref.md` — this tracking/audit record.

[PR #61]: https://github.com/atelier-fashion/adlc-toolkit/pull/61
