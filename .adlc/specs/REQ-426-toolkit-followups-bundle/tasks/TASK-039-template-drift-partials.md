---
id: TASK-039
title: "Extend /template-drift to cover partials/"
status: draft
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-426 BR-3 (ADR-3). `/template-drift` currently scans
`.adlc/templates/` vs `~/.claude/skills/templates/`. Extend it to also
compare `.adlc/partials/*.sh` against `~/.claude/skills/partials/*.sh` and
report all differences as `stale` (no intentional-customization
classification, per ADR-3 — partials are shared executable code, not
customizable content).

## Files to Create/Modify

- `template-drift/SKILL.md` — MODIFIED. Add a second scan loop alongside
  the templates scan:
  - Section title: rename "Step 2: Detect drift" to "Step 2: Detect
    template drift" and add a new "Step 3: Detect partial drift" right
    after.
  - The new step iterates `~/.claude/skills/partials/*.sh`, compares each
    against `.adlc/partials/<basename>` (if present), and classifies:
    - **missing** — toolkit has it, consumer doesn't (consumer needs
      `/init` re-run)
    - **stale** — both have it, content differs (consumer has an outdated
      copy OR a malicious-shadow)
    - **synced** — both have it, identical
  - Report uses the same format as the templates report: list per-file
    classification, then a summary line.
  - **No "intentional customization" classification** for partials — every
    drift is `stale`. Add a one-paragraph rationale paragraph explaining
    why (security: partials are executable code).
- `template-drift/SKILL.md` — also update the skill's `description:`
  frontmatter to mention partials.

## Acceptance Criteria

- [ ] `/template-drift` invoked in a sandbox where
      `~/.claude/skills/partials/ethos-include.sh` differs from
      `.adlc/partials/ethos-include.sh` reports the difference as `stale`.
- [ ] `/template-drift` invoked in a sandbox where consumer has no
      `.adlc/partials/` directory reports each toolkit partial as
      `missing`.
- [ ] `/template-drift` invoked when synced reports `synced` for each.
- [ ] The rationale paragraph for "no customization classification" is
      present in the skill's instructions and visible in `/template-drift`'s
      output when partials drift is detected.
- [ ] Output uses the same vocabulary ("synced", "stale", "missing") as
      the existing templates report.
- [ ] No regression in existing templates-drift behavior — verify by
      running the skill in a sandbox with template drift and confirming
      the report still classifies correctly.
- [ ] REQ-413 pytest suite still passes (BR-8).

## Technical Notes

- The existing templates-scan logic is markdown-described (the skill is
  prompt-driven, not code-driven). The extension is markdown — add a
  parallel step that does the same shape of work for partials.
- Comparison: `diff -q .adlc/partials/X.sh ~/.claude/skills/partials/X.sh`
  → exit 0 = synced, exit 1 = stale. POSIX-compatible.
- Glob: `for f in ~/.claude/skills/partials/*.sh; do ...` — works in POSIX
  sh; use `[ -e "$f" ]` to handle the no-matches case (glob expands to
  literal pattern when no matches exist).
- Do not invoke `/template-drift` recursively or against the toolkit's
  own `.adlc/` (would always report drift against itself by construction).
