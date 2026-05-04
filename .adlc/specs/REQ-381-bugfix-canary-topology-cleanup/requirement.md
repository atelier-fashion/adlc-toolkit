---
id: REQ-381
title: "Drop /bugfix Phase 6 (canary) and fix dangling Phase 7.5 cross-reference"
status: approved
deployable: false
created: 2026-05-04
updated: 2026-05-04
component: "skills/bugfix"
domain: "adlc"
stack: ["markdown"]
concerns: ["developer-experience", "reliability", "skill-correctness"]
tags: ["bugfix", "canary", "phase-removal", "topology-mismatch", "cross-reference-rot", "follow-up-to-REQ-380"]
---

## Description

This REQ is the deferred follow-up to REQ-380 (which removed `/proceed` Phase 7.5 and Phase 8a). REQ-380's architecture phase explicitly scoped its diff to `proceed/SKILL.md` + `canary/SKILL.md` + `project-overview.md` + a wrapup lesson (REQ-380 AC #8), leaving `/bugfix` untouched. As a result, `bugfix/SKILL.md` now has two related defects:

1. **Cross-reference rot.** `bugfix/SKILL.md:128` reads `Steps (mirrors /proceed Phase 7.5):`. REQ-380 deleted Phase 7.5 entirely, so the parenthetical now points at a phase that no longer exists. A future reader following the link finds nothing.

2. **Topology hazard inheritance.** `/bugfix` Phase 6 (lines 119–135 of `bugfix/SKILL.md`) invokes `/canary` exactly the way `/proceed` Phase 7.5 used to — it walks `services:` from `.adlc/config.yml` and calls `/canary` per service, which deploys a zero-traffic Cloud Run revision and **promotes it to 100% production traffic** (`/canary` SKILL.md Step 5). On a project with atelier-fashion's promotion topology (dev → staging → main, with the heavy harness gating dev → staging and main being a byte-identical promotion of the staging-validated image), `/bugfix` Phase 6 ships a fix-branch image straight to prod before the fix has been promoted through the staging gate — defeating the same gates that motivated REQ-380. The anti-pattern that REQ-380 removed from `/proceed` is still present, unchanged, in `/bugfix`.

This REQ closes both defects.

### Why /bugfix shouldn't have a built-in canary phase

The `/bugfix` workflow already lands the fix via PR and has a Phase 7 step that confirms the merge SHA reached production via the project's normal CI/CD pipeline. For projects with a staging gate, that pipeline is the right deploy path: dev → staging → main, with each promotion validated. For projects without a staging gate, `/canary` is still available as a standalone operator-invoked command — operators who want a manual canary can run it themselves outside `/bugfix`.

In other words, `/bugfix` Phase 6 today is identical in role and risk to `/proceed` Phase 7.5: an in-pipeline auto-canary that bypasses the staging gate. REQ-380's removal logic applies verbatim. There is no surviving project topology where `/bugfix` Phase 6 is the right default.

### Pairing with REQ-380

REQ-380 ships the `/proceed` half of this cleanup. REQ-381 ships the `/bugfix` half. REQ-380's wrapup lesson already documents the topology rationale; REQ-381's wrapup lesson cross-references REQ-380 and notes the deferred-follow-up history (so the lesson corpus reflects that the cleanup landed in two REQs, not one, and explains why).

### Distribution mechanics

`bugfix/SKILL.md` is distributed via the same hard-link / symlink mechanism as `proceed/SKILL.md`. Editing the canonical file in this repo + merging to `main` is the entire ship sequence; no consumer-side migration is needed.

## System Model

This REQ does not touch the data model. It changes orchestration topology only.

### Triggers and side-effects

| Trigger | Side-effect (today, before this REQ) | Side-effect (after this REQ) |
|---|---|---|
| `/bugfix BUG-xxx` reaches Phase 6 with a deployable backend service in `services:` and severity high/critical | Phase 6 invokes `/canary`, which deploys a zero-traffic Cloud Run revision on the production GCP project and promotes it to 100% prod traffic from the fix branch, before the fix has been merged to dev or staging. | Phase 6 is gone. `/bugfix` advances directly from Phase 5 (Ship — Create Pull Request(s)) to Phase 7 (Wrapup), which is renumbered to Phase 6. The fix reaches production via the project's normal CI/CD promotion pipeline (dev → staging → main, where applicable). |
| `/bugfix` Phase 6 step references "mirrors /proceed Phase 7.5" | Reader follows the cross-reference and finds Phase 7.5 was deleted by REQ-380 — dangling pointer. | Cross-reference is gone with the section. |
| Operator runs `/canary` directly (outside `/bugfix`) | Same as today: deploys zero-traffic prod Cloud Run revision, smoke-tests, promotes to 100% on success. | Unchanged. `/canary` remains a standalone skill for ad-hoc production canary deploys. Only its `/bugfix` embedding is removed. |

## Business Rules

- [ ] BR-1: `bugfix/SKILL.md` MUST be amended to **remove Phase 6 (Canary Deploy — Optional) entirely**. The Phase 6 section heading, "Skip when" / "Run when" prose, and the numbered steps including the "Steps (mirrors /proceed Phase 7.5)" header MUST be deleted. (informed by REQ-380)
- [ ] BR-2: Phases that follow Phase 6 in `bugfix/SKILL.md` MUST be renumbered. Specifically, current Phase 7 (Wrapup — Merge, Deploy, Knowledge Capture) becomes Phase 6. Any inline cross-reference elsewhere in the skill that names "Phase 7" by number MUST be updated, and any reference to "Phase 6" that meant the canary phase MUST be deleted along with the phase. The Phase 4 interim summary's "Then continue to Phase 5" line MUST remain accurate.
- [ ] BR-3: `bugfix/SKILL.md` Phase 4 verify step that says "do NOT mark `resolved` yet — that happens in Phase 7 after the fix is merged and deployed" MUST be updated to point at the renumbered phase (Phase 6 in the new numbering).
- [ ] BR-4: Any prose elsewhere in `bugfix/SKILL.md` that mentions canary as an in-pipeline step (e.g., the skill description, the Phase 5 PR test-plan template "Canary verified"-style line if present, the deploy-summary section) MUST be removed. The skill description in frontmatter currently reads "End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + canary + merge + deploy + knowledge capture)" — the `+ canary` segment MUST be removed.
- [ ] BR-5: `canary/SKILL.md` description and body MUST be re-audited (after REQ-380's audit) for any reference to `/bugfix` as a caller. Any such reference MUST be removed or annotated to reflect `/canary`'s manual-only status across BOTH `/proceed` and `/bugfix`. (informed by REQ-380)
- [ ] BR-6: A wrapup lesson in `.adlc/knowledge/lessons/` MUST capture: (a) the cross-reference rot at `bugfix/SKILL.md:128` and how it was found (REQ-380 architecture-phase scope carve-out left it behind); (b) the topology-hazard-inheritance pattern (when one skill removes an anti-pattern, audit sibling skills for the same code path); (c) the fact that REQ-380 + REQ-381 together complete the canary-removal cleanup, and that future deferred-fix carve-outs SHOULD be tracked as explicit follow-up REQ entries at architecture time so they don't drift.

## Acceptance Criteria

- [ ] `bugfix/SKILL.md` no longer contains a `Phase 6: Canary Deploy` section. The phase list goes 1, 2, 3, 4, 5, 6 (where the new Phase 6 is the former Phase 7 — Wrapup).
- [ ] No occurrence of the string `Phase 7.5` remains anywhere in `bugfix/SKILL.md`.
- [ ] No occurrence of `/canary` invocation as a numbered step remains in `bugfix/SKILL.md`. (Mentions of `/canary` as a standalone operator skill in prose are acceptable if the architecture phase finds a sensible context for them; otherwise delete.)
- [ ] The skill frontmatter `description` field no longer contains `+ canary`.
- [ ] All inline phase-number cross-references in `bugfix/SKILL.md` (Phase 4's "happens in Phase 7" mention, any "continue to Phase X" lines, the deploy-summary step numbering) are consistent with the new phase list.
- [ ] `canary/SKILL.md` is audited; any `/bugfix`-as-caller cross-reference is removed or annotated. The skill remains invocable as a standalone command with no other behavior changes.
- [ ] Running `/bugfix` against any deployable bug ends cleanly at the renumbered Wrapup phase without invoking `/canary` and without deploying to production from the fix branch. The fix reaches production only via the project's CI/CD pipeline after merge.
- [ ] The wrapup lesson exists at `.adlc/knowledge/lessons/<date>-req-381-bugfix-canary-topology.md` with the three required content blocks (BR-6).
- [ ] No application code is touched. The diff is: `bugfix/SKILL.md` edits + `canary/SKILL.md` re-audit (small or no-op) + wrapup lesson.

## External Dependencies

- REQ-380 must have shipped (it has, as of 2026-05-04 — commit `9511cc4`). Without REQ-380, this REQ's BR-5 audit would have nothing to cross-check against. REQ-381 takes REQ-380 as a hard prerequisite.

## Assumptions

- `bugfix/SKILL.md` is the single source of truth for `/bugfix` Phase 6's definition. The architecture phase MUST grep for `Phase 6` and `mirrors /proceed Phase 7.5` across the repo to confirm no other doc references the phase by number. (Toolkit-internal docs only — consumer projects don't ship copies of the skill body.)
- `canary/SKILL.md`'s REQ-380 audit may have already neutralized any `/bugfix`-side cross-references along with the `/proceed` ones. The architecture phase MUST verify; BR-5 may be vacuously satisfied.
- No active `/bugfix` session anywhere has a numbered Phase-6-canary state recorded that would need manual phase advancement. (Unlike `/proceed`, `/bugfix` doesn't write a `pipeline-state.json`; it tracks progress only via the bug report and TodoWrite. So there is no persisted state to migrate.)
- The skill description's `+ canary` segment is a marketing/summary line, not a behavioral contract. Removing it does not break any caller — skills are invoked by name, not by description match.

## Open Questions

- [ ] Should the renumbered Wrapup phase keep its current internal numbering (Step 1, Step 2, Step 3) or should the architecture phase also flatten/reorganize since the canary deploy-confirmation logic in Wrapup Step 2 is the surviving deploy-verification path? Recommend: keep Wrapup as-is internally; only the outer phase number changes. Step 2's gcloud confirmation already covers staging + production for projects with `gcp.staging_project` / `gcp.production_project` set.
- [ ] Does `/bugfix` need an explicit "if your project has a staging gate, the fix reaches production via dev → staging → main; do not deploy from the fix branch" callout in the new Wrapup phase, or is that implicit in following the project's normal CI/CD? Recommend: add a one-sentence callout in Phase 5's PR-creation step ("This PR follows the project's standard merge-and-promote path; do not deploy the fix branch directly") to head off operators who might invoke `/canary` manually expecting it to be the right move.
- [ ] Should this REQ also touch the `/init` template's bug-template or any consumer-facing doc that references `/bugfix`'s phase list? Recommend: architecture-phase grep the repo for explicit `/bugfix` phase-number references; if any exist (project-overview.md, README.md, taxonomy-template.md), update in this REQ. Otherwise out of scope.

## Out of Scope

- **Editing `/canary` itself** beyond the BR-5 audit annotation. The skill remains as-is for operator-invoked use.
- **Re-introducing a staging-canary or pre-merge canary in `/bugfix`.** If a future REQ wants an opt-in staging-targeted canary, it ships separately with its own design.
- **Re-architecting `/bugfix` Phase 7 (Wrapup) beyond renumbering.** Step bodies stay intact.
- **Backfilling REQ-380's wrapup lesson with REQ-381 content.** REQ-381 gets its own lesson; REQ-380's lesson stays as-shipped.
- **Touching consumer-project copies of `/bugfix`.** The skill is distributed via symlink/hard-link from this repo; consumers pick up the change automatically.
- **Adding a `pipeline.canary` or similar config flag** to make Phase 6 opt-in. The right answer per REQ-380's precedent is removal, not config-gating: the phase has no surviving topology where it is correct by default, and a config flag would just preserve the foot-gun.

## Retrieved Context

- REQ-380 (spec, this repo, status `complete`): the precedent removal of `/proceed` Phase 7.5 + Phase 8a. Its rationale, halt-contract reduction, and architecture-phase scope-narrowing (AC #8) are the direct basis for REQ-381's BRs and ACs. Informs BR-1, BR-5, BR-6.
- `bugfix/SKILL.md` lines 119–135: the literal Phase 6 / canary section being deleted, and the dangling "mirrors /proceed Phase 7.5" string at line 128.
- `canary/SKILL.md` (toolkit): Step 5 ("Promote to Production") confirms the production deploy target — the basis for treating `/bugfix` Phase 6 as the same anti-pattern REQ-380 removed.
- `templates/config-template.yml` lines 138–151: confirms `services:` is the data shape `/bugfix` Phase 6 consumes, and confirms there is no current `pipeline.canary` flag (so the REQ-380 precedent of "remove, don't config-gate" applies cleanly).
- adlc-toolkit project-overview.md "REQ-numbering policy": establishes that REQ-381 takes the next slot above the global counter (anchored at REQ-380), not above adlc-toolkit's local high-water of REQ-263.
- No prior bugs (`.adlc/bugs/`) or other lessons (`.adlc/knowledge/lessons/`) in this repo — adlc-toolkit doesn't currently track those corpora. Cold-start path for those two corpora; lesson and bug retrieval returned nothing.
