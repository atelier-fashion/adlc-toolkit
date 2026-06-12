---
id: REQ-525
title: "/template-drift covers all vendored sync surfaces: ETHOS.md and the workflow runtime"
phase: architecture
created: 2026-06-12
updated: 2026-06-12
---

# Architecture — REQ-525

## Problem recap

`/init` vendors **four** sync surfaces into every consumer project (`init/SKILL.md` Step 6):
`.adlc/ETHOS.md`, `.adlc/templates/*.md`, `.adlc/partials/*.sh`, and
`.adlc/workflows/{adlc-sprint.workflow.js, README.md}`. `/template-drift` checks only three of
the *consequences* of those copies — templates (Step 2), partials (Step 3), and the **stale
workflow-test landmine** (Step 3b) — but never diffs the vendored **ETHOS content** nor the
**workflow runtime file** against canonical. Because `ethos-include.sh` resolves the *project copy
first*, a stale `.adlc/ETHOS.md` silently runs an outdated constitution in every skill while
`/template-drift` reports `clean`. Same silent freeze for `adlc-sprint.workflow.js`.

This REQ closes the two gaps with first-class drift checks, each classified to match its surface's
customization posture, plus a toolkit-side structural check (AC4) that keeps `/init`'s copy list and
`/template-drift`'s surface list from silently diverging in the future.

## Design overview

Five distinct edits, no new files except the two test additions and one new lint-check function:

1. **`template-drift/SKILL.md`** — add two new detection steps and weave both surfaces through the
   preamble, report table, summary line, and reconciliation offer:
   - **Step 3c: ETHOS drift** (BR-1) — diff `.adlc/ETHOS.md` vs canonical `~/.claude/skills/ETHOS.md`.
     *Template-posture* classification (intentional-customization vs accidental-staleness) BUT with a
     mandatory **missing-principle** sub-check: enumerate the canonical `## <n>. <title>` principle
     headings and flag any present upstream yet absent from the project copy — loudly, regardless of
     classification (this is the dangerous #6/#7 case). Reconciliation shows the principle-level diff
     before any write (BR-5).
   - **Step 3d: workflow-runtime drift** (BR-2) — diff `.adlc/workflows/adlc-sprint.workflow.js` and
     `.adlc/workflows/README.md` vs the canonical copies under `~/.claude/skills/workflows/`.
     *Partials-posture*: every diff is `stale`, no customization track, loud warning (a consumer-modified
     sprint engine is the silent-divergence threat). This is **distinct** from the existing Step 3b,
     which only finds stale *test* files; 3d diffs the *runtime* file content.
   - **BR-3**: preamble, the Step 5 report table/summary, the `--brief`/`--status` one-liner, and the
     Step 6 reconciliation offer all enumerate **all five** surfaces (templates, partials, ethos,
     workflow-runtime, workflow-test-landmine). A checked-and-clean surface prints `clean` in one line,
     never silently omitted (Ethos #5).
   - **BR-4 (consumer half)**: a single "Vendored sync surfaces" enumeration near the top of the skill,
     cross-referenced to `init/SKILL.md`'s copy list.

2. **`init/SKILL.md`** — add a single cross-reference note at the vendored-surface list (Step 6 / the
   directory tree comment) pointing to `/template-drift`'s surface list, so the next surface added here
   is visible as a gap there (BR-4 producer half). **Scope-limited to one anchored note** to minimize
   overlap with REQ-522 (which also edits `init/SKILL.md`); the Phase-8 trial-merge gate serializes.

3. **`tools/lint-skills/check.py`** — add `check_sync_surface_parity(root)` (AC4), a **per-root** check
   mirroring the existing `check_agent_model_drift(root)` precedent exactly: it parses `/init`'s copied
   surface set and `/template-drift`'s checked surface set from the two SKILL.md files and emits a
   finding if they disagree. Registered in `run()` after the per-file loop, alongside the agent-model
   check. Degrades gracefully (zero findings, no crash) when run outside the toolkit checkout.

4. **`tools/lint-skills/tests/test_sync_surface_parity.py`** — new pytest module covering: parity holds
   on the real toolkit tree (the post-change SKILL.md pair agrees); a synthetic mismatch (a surface in
   `/init`'s list missing from `/template-drift`'s) produces a finding; degrades to zero findings when a
   SKILL.md is absent.

## ADRs

### ADR-1: ETHOS uses template-posture, not partials-posture (resolves the Open Question)

The spec's Open Question asks whether ETHOS should be partials-posture (always `stale`). **Decision:
template-posture per BR-1's explicit default**, because per-project constitution tailoring is a
plausible legitimate use (a consumer may add a project-specific principle). The danger the spec actually
names — a *missing canonical principle* (#6/#7 absent downstream) — is handled by a **dedicated
missing-principle sub-check that fires loudly regardless of classification**, so template-posture does
not weaken the safety property. This is strictly safer than partials-posture would be: partials-posture
would flag *any* edit as `stale` (including a legitimate added principle) but would NOT specifically
name *which* canonical principle is missing, which is the actionable signal.

### ADR-2: Reuse the principle-heading regex as the staleness heuristic

The "missing principle" detector enumerates canonical headings matching `^## [0-9]` (verified: the 7
canonical principles match exactly this) and reports any whose heading text is absent from the project
copy. Heading-level (not line-level) comparison keeps the check robust to body-text rewording while
still catching a wholesale-missing principle. No new parsing machinery — `grep -E '^## [0-9]'` over both
files.

### ADR-3: AC4 check mirrors `check_agent_model_drift`, not a new test harness

The toolkit-side parity check (AC4) is the same *shape* as the existing per-root `check_agent_model_drift`:
read two artifacts, compare a derived set, emit a `Finding` on mismatch, degrade to `[]` when the inputs
are absent. It parses each SKILL.md's surface list from an explicit, machine-greppable enumeration block
(a fenced list with a stable marker comment) rather than by guessing from prose — so the check is
deterministic and the SKILL.md edits in tasks 1–2 deliberately add those stable markers. This follows
LESSON-012 (structural enforcement beats prose) and LESSON-019 (anchor the guard to a stable marker so
it doesn't rot when surrounding text moves).

### ADR-4: The five-surface vocabulary is fixed in one constant

`check.py` defines the canonical five-surface name set once (`SYNC_SURFACES = {...}`); both the parity
check and the tests reference it. This is the single source of truth the SKILL.md enumerations are
checked against, satisfying BR-4's "stated in one place" intent on the toolkit side.

## Surface name vocabulary (the five surfaces, per SyncSurface enum)

`templates`, `partials`, `ethos`, `workflow-runtime`, `workflow-test-landmine`.

## Files to create / modify

| File | Change | Task |
|---|---|---|
| `template-drift/SKILL.md` | Add Step 3c (ETHOS), Step 3d (workflow-runtime); weave all 5 surfaces through preamble, report, summary, reconciliation; add the BR-4 surface-list marker block | TASK-001 |
| `init/SKILL.md` | One anchored cross-reference note + a stable surface-list marker for the parity check | TASK-002 |
| `tools/lint-skills/check.py` | Add `SYNC_SURFACES` constant + `check_sync_surface_parity(root)`, register in `run()` | TASK-003 |
| `tools/lint-skills/tests/test_sync_surface_parity.py` | New pytest module for the parity check | TASK-003 |

## Test strategy

- **AC1/AC2/AC3 (the three drift behaviors)** are skill-markdown logic — verified by reading the edited
  SKILL.md against the acceptance scenarios (the skill is interpreted, not executed; there is no runtime
  to unit-test the drift detection itself, per conventions.md "tests are dogfooding"). The fixture
  scenarios in the ACs are documented in the SKILL.md steps so a future dogfood run is deterministic.
- **AC4** is the real automated test: `pytest tools/lint-skills/tests/` must stay green, and the new
  `test_sync_surface_parity.py` proves the parity check fires on a synthetic mismatch and passes on the
  real (post-change) tree. The full existing suite (33 tests) must remain green — the new per-root check
  must not regress `find_skill_files` / the per-file checks.

## Risks

- **Overlap with REQ-522 on `init/SKILL.md`** (flagged at dispatch): mitigated by keeping the `/init`
  edit to a single anchored note + marker block, far from the delegation/telemetry sections REQ-522
  touches. The Phase-8 trial-merge gate is the authoritative serializer.
- **Parity-check brittleness**: anchoring both surface lists to an explicit fenced marker block (ADR-3)
  avoids prose-parsing fragility. If a marker is missing the check degrades to zero findings (never a
  false red), matching the `check_agent_model_drift` graceful-degradation posture.
