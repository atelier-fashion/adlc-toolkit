---
id: TASK-001
title: "Add ETHOS + workflow-runtime drift steps to /template-drift; weave all five surfaces through report"
status: complete
parent: REQ-525
created: 2026-06-12
updated: 2026-06-12
dependencies: []
---

## Description

Extend `template-drift/SKILL.md` so it checks the two currently-unchecked vendored sync surfaces —
`.adlc/ETHOS.md` and the workflow **runtime** (`.adlc/workflows/adlc-sprint.workflow.js` + `README.md`) —
and reports all five surfaces (templates, partials, ethos, workflow-runtime, workflow-test-landmine)
in every place the skill enumerates surfaces. Satisfies BR-1, BR-2, BR-3, BR-5, and the consumer half of
BR-4.

## Files to Create/Modify

- `template-drift/SKILL.md` — add Step 3c (ETHOS drift, template-posture + missing-principle sub-check),
  Step 3d (workflow-runtime drift, partials-posture); update the description frontmatter, preamble, Step 5
  report table + summary, the `--brief` one-liner (Implementation Notes), and the Step 6 reconciliation
  offer to include both new surfaces; add a single stable "Vendored sync surfaces" marker block that the
  toolkit parity check (TASK-003) reads.

## Acceptance Criteria

- [ ] BR-1: A new step diffs `.adlc/ETHOS.md` vs `~/.claude/skills/ETHOS.md`, classified template-posture
      (intentional vs accidental), with an explicit missing-canonical-principle sub-check (enumerate
      `^## [0-9]` headings upstream, flag any absent downstream) reported **loudly regardless of
      classification**. Drift here is reported prominently because the runtime prefers the project copy.
- [ ] BR-2: A new step diffs `.adlc/workflows/adlc-sprint.workflow.js` and its `README.md` vs the canonical
      copies, classified partials-posture (every diff `stale`, no customization track, loud warning).
- [ ] BR-3: The preamble, the Step 5 report (table + summary line), the `--brief`/`--status` one-liner, and
      the Step 6 reconciliation offer each enumerate **all five** surfaces; a checked-and-clean surface
      prints `clean` in one line, never silently omitted.
- [ ] BR-4 (consumer half): a single explicit "Vendored sync surfaces" list, cross-referenced to
      `init/SKILL.md`, with a stable marker comment the parity check can grep.
- [ ] BR-5: ETHOS reconciliation shows the full principle-level diff before any write; reconciliation stays
      opt-in with explicit user approval (unchanged posture).
- [ ] Step 3c (ETHOS) and Step 3d (workflow-runtime) are clearly distinct from the existing Step 3b
      (stale workflow *test* landmine) — 3d diffs the runtime file content; 3b only finds stray test files.
- [ ] `python3 tools/lint-skills/check.py --root .` reports no new findings against the edited SKILL.md
      (no bare `$<digit>`, no cross-fence-fn, no direct `gh pr`, balanced fences).

## Technical Notes

- Canonical ETHOS has 7 `## <n>. <title>` principles; #6 ("If It's Broken, Fix It") and #7 ("Skeptical by
  Default") are the silently-shipped ones that motivated this REQ — the missing-principle case must name
  the absent heading text.
- Workflow-runtime diff uses `diff -q` (partials-posture: only remediation is "copy from toolkit"), same
  as Step 3 partials. Show full diff only on `--verbose`.
- Surface vocabulary (must match TASK-003's `SYNC_SURFACES`): `templates`, `partials`, `ethos`,
  `workflow-runtime`, `workflow-test-landmine`.
- Keep the missing-principle heuristic heading-level (robust to body rewording) per ADR-2.
- Reconciliation commands: `cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md` (after showing principle diff);
  `cp ~/.claude/skills/workflows/adlc-sprint.workflow.js .adlc/workflows/` and the README.
