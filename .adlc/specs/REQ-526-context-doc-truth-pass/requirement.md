---
id: REQ-526
title: "Context-doc truth pass: seven principles, /map disposition, and stale-claim sweep"
status: complete
deployable: false
created: 2026-06-12
updated: 2026-06-12
component: "adlc/docs"
domain: "adlc"
stack: ["markdown"]
concerns: ["correctness", "configurability", "onboarding"]
tags: ["context-docs", "ethos-count", "map-skill", "project-overview", "doc-drift", "stack-agnostic"]
---

## Description

The `.adlc/context/` docs are loaded into every toolkit-internal agent session as ground truth, and the README is the public contract — yet several of their claims are verifiably false against the current tree (adversarial findings M6, M7, plus three confirmed minors swept in because they edit the same files):

1. **"Five principles" (M6).** `architecture.md` (lines 7, 25), `conventions.md` (line 144), and `project-overview.md` (line 25) all say ETHOS.md has five principles. It has **seven** — #6 (If It's Broken, Fix It) and #7 (Skeptical by Default) were added in 3.1.0 and 4.9.0. An agent told to audit "all five principles" silently drops two.
2. **`/map` is an undisclosed, project-specific skill in a "stack-agnostic" distribution (M7).** It appears in no README/CHANGELOG/context doc and is hardcoded to the `atelier-map` Obsidian vault and Atelier sibling repos — directly violating conventions.md's own "skills must work for any consumer project" rule and the 5.0 genericization goal. An external adopter gets a live `/map` command targeting a repo that doesn't exist.
3. **`project-overview.md` is frozen two epochs back** — claims the toolkit "doesn't track lessons or bugs for itself yet" (dozens of LESSONs and a BUG counter exist), anchors numbering reasoning at "local high-water REQ-263", and predates the 5.0 portability epoch entirely.
4. **CHANGELOG epoch list transposed** — the summary list renders epochs in order 1, 2, 3, 5, 4.
5. **Template enumerations incomplete** — README and architecture.md list five templates; `templates/taxonomy-template.md` is absent from both. `partials/README.md` omits `id-alloc.sh`/`id-recheck.sh` (the most contract-heavy partials) and still claims partial drift detection is "not yet implemented" when `/template-drift` Step 3 implements it.

## System Model

_No data model — documentation and distribution-content REQ. Section intentionally minimal._

## Business Rules

- [ ] BR-1: Every "five principles" claim is corrected to seven, or — sturdier — rephrased to not hardcode the count (e.g. "the ETHOS principles"), with at most one place stating the number. (adversarial M6; informed by LESSON-019 — counts are presence-guards that rot)
- [ ] BR-2: `/map` is removed from the toolkit distribution. Its content is preserved by relocating it to a non-distributed home (the atelier project's own skill directory, or a personal `~/.claude/skills/` entry outside this repo — Open Question). The README skill catalog, `install.sh`, and any cross-references are updated so the distributed skill set contains no project-specific skill. (adversarial M7)
- [ ] BR-3: `project-overview.md` is rewritten to describe the current tree truthfully: the toolkit tracks its own lessons (`.adlc/knowledge/lessons/`) and bugs (`.adlc/bugs/`); numbering is remote-derived per REQ-518 (the "local high-water REQ-263" anchor is historical); the 4.x delegation and 5.0 portability epochs exist. Claims that will date are tagged with an as-of marker or removed in favor of pointing at the authoritative artifact (CHANGELOG, VERSION).
- [ ] BR-4: CHANGELOG's epoch summary list is reordered 1→5; `[5.0.0]`'s body entries are untouched.
- [ ] BR-5: Template enumerations in README and architecture.md include `taxonomy-template.md` (or reference the `templates/` directory as authoritative instead of enumerating). `partials/README.md` documents `id-alloc.sh`/`id-recheck.sh` at the same depth as its other entries and drops the stale "drift detection not yet implemented" claim.
- [ ] BR-6: A closing verification greps the edited docs for the corrected claims (no remaining "five principles", no `/map` in distributed surfaces, no "doesn't track lessons or bugs") so the fix is checkable, not just authored. (Ethos #4)

## Acceptance Criteria

- [ ] `grep -rn 'five principles\|5 principles' .adlc/context/ README.md` returns nothing (or only the single sanctioned count statement if that option is chosen).
- [ ] `map/` is absent from the repo (or explicitly marked non-distributed and excluded by `install.sh`), and `grep -rn 'atelier' <distributed surfaces>` returns no project-specific skill references.
- [ ] `project-overview.md` contains no claim contradicted by the tree (spot-checked: lessons/bugs tracking, numbering policy, epoch list).
- [ ] CHANGELOG epoch list reads 1, 2, 3, 4, 5 in source order.
- [ ] README/architecture template lists match `ls templates/`.
- [ ] `partials/README.md` documents id-alloc/id-recheck and makes no false drift-detection claim.

## External Dependencies

- None.

## Assumptions

- `/map`'s functionality is still wanted somewhere — this REQ relocates rather than deletes it. If Brett confirms it's dead, deletion is simpler.
- No consumer project references `/map` by name in its own automation.

## Open Questions

- [ ] `/map` relocation target: atelier-fashion repo's project-local skills, a separate personal skills repo, or deletion? Default if unanswered: move to the atelier project's own skill directory with a tombstone note in CHANGELOG.

## Out of Scope

- Drift *detection* for these docs (REQ-525 covers detection surfaces; this REQ fixes current content).
- Restructuring the context-doc format or adding new docs.
- Code changes of any kind.

## Retrieved Context

- LESSON-019 (lesson, score 4): Presence guards rot when indirection moves — hardcoded counts are the same failure class
- LESSON-005 (lesson, score 2): Sibling-skill anti-pattern audit — cross-reference rot when a skill is removed
- LESSON-023 (lesson, score 3): Mirror the rationale, not just the mechanism
- REQ-515 (spec, score 4): Provider-agnostic delegation — the 5.0 genericization mandate /map violates
