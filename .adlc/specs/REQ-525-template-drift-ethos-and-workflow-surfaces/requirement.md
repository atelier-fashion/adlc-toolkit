---
id: REQ-525
title: "/template-drift covers all vendored sync surfaces: ETHOS.md and the workflow runtime"
status: complete
deployable: false
created: 2026-06-12
updated: 2026-06-12
component: "adlc/template-drift"
domain: "adlc"
stack: ["markdown", "sh"]
concerns: ["correctness", "drift-detection", "configurability"]
tags: ["template-drift", "ethos", "workflow-runtime", "vendored-sync", "init"]
---

## Description

`/init` vendors four sync surfaces into every consumer project: `.adlc/templates/*.md`, `.adlc/partials/*.sh`, `.adlc/ETHOS.md`, and `.adlc/workflows/adlc-sprint.workflow.js` (+ README). `/template-drift` — the tool whose entire job is "have toolkit updates landed in this project?" — checks only templates (Step 2), partials (Step 3), and stale workflow *test* files (Step 3b). It never diffs the vendored ETHOS or the workflow runtime (adversarial finding M5).

The gap is live, not theoretical: `ethos-include.sh` resolves the **project copy first**, so when the toolkit ships a new ETHOS principle (it has twice: #6 in 3.1.0, #7 in 4.9.0), every skill in an already-initialized consumer repo silently runs the stale constitution — and `/template-drift` reports `clean`. Same for the sprint engine: a consumer's `.adlc/workflows/adlc-sprint.workflow.js` is frozen at init time while the toolkit's copy evolves.

This REQ adds both surfaces as first-class drift checks, with classification matching each surface's customization posture.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SyncSurface | name | enum | templates, partials, ethos, workflow-runtime, workflow-test-landmine |
| DriftReport | classification | enum | `synced`, `stale`, `missing`, `missing upstream`; templates and ethos additionally `customized` |

## Business Rules

- [ ] BR-1: A new step diffs the consumer's `.adlc/ETHOS.md` against the toolkit's canonical `ETHOS.md`. Because the runtime fallback prefers the project copy, drift here is **actively used**, so it is reported prominently. Classification follows the *template* posture (intentional customization vs accidental staleness — a project may legitimately tailor its constitution), with the staleness heuristic explicitly checking whether canonical principles present upstream are absent from the project copy (the "missing principle" case is the dangerous one). (adversarial M5)
- [ ] BR-2: A new step diffs the consumer's `.adlc/workflows/adlc-sprint.workflow.js` (and its vendored `README.md`) against the toolkit copies. Classification follows the *partials* posture: shared executable code, every diff is `stale`, no customization track — a consumer-modified sprint engine is exactly the silent-divergence threat the partials rationale already names. (adversarial M5)
- [ ] BR-3: The skill's preamble, final report summary line, and Step 6 reconciliation offers enumerate **all five** surfaces (templates, partials, ethos, workflow runtime, workflow-test landmine); a surface that is checked and clean is reported `clean` in one line, never silently omitted. (Ethos #5 — say so explicitly rather than silently skipping)
- [ ] BR-4: `/init`'s vendored-surface list and `/template-drift`'s checked-surface list are stated in one place each and cross-referenced, so the next surface added to `/init` is at least *visible* as a gap in `/template-drift`'s docs if not implemented together. (informed by LESSON-019 — guards rot when indirection moves; LESSON-005 — sibling cross-reference rot)
- [ ] BR-5: Reconciliation (applying updates) remains opt-in with explicit user approval, per the skill's existing posture; ETHOS reconciliation shows the full principle-level diff before any write.

## Acceptance Criteria

- [ ] Fixture consumer repo with an ETHOS missing principle #7 → `/template-drift` reports the ETHOS surface as drifted, names the missing principle, and classifies per BR-1.
- [ ] Fixture with a modified `adlc-sprint.workflow.js` → reported `stale` with the partials-style loud warning.
- [ ] Fixture fully in sync → all five surfaces report `clean`, one line each.
- [ ] Toolkit-side check (lint or test) verifying `/init`'s copy list and `/template-drift`'s surface list agree.

## External Dependencies

- None.

## Assumptions

- The toolkit-canonical paths (`~/.claude/skills/...` via the existing resolution, with the documented SCRIPT_DIR fallback) are reachable from the consumer repo, as they already are for template/partial checks.

## Open Questions

- [ ] Should ETHOS drift be partials-posture (always `stale`) instead of template-posture? Argument for: it is the injected constitution and a consumer edit changes every skill's behavior. Argument against: per-project tailoring is a plausible legitimate use. Default if unanswered: template-posture per BR-1, with the missing-canonical-principle case always flagged loudly regardless of classification.

## Out of Scope

- Auto-sync without user approval.
- Adding new vendored surfaces to `/init`.
- The doc-truth corrections to architecture/overview docs (REQ-526).

## Retrieved Context

- LESSON-019 (lesson, score 4): Presence guards rot when indirection moves
- LESSON-005 (lesson, score 2): Sibling-skill anti-pattern audit — cross-reference rot
- LESSON-012 (lesson, score 4): Structural enforcement beats prose
- LESSON-020 (lesson, score 8): Cross-block shell state and guard rot — the partials posture rationale
