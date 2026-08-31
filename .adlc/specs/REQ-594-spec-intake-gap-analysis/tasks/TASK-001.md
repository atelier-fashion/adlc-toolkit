---
id: TASK-001
title: "Create partials/intake.sh with detection, segmentation, budget, and redaction"
status: complete
parent: REQ-594
created: 2026-08-31
updated: 2026-08-31
dependencies: []
repo: adlc-toolkit
---

## Description

Create the single sourceable partial that holds every shell function Step 1.4 needs
(ADR-2). All four functions must be usable by sourcing the partial in the same fenced
block as the call, because `tools/lint-skills`'s `cross-fence-fn` check fails any
function defined in one fence and invoked from another.

## Files to Create/Modify

- `partials/intake.sh` — NEW

## Acceptance Criteria

- [ ] `adlc_intake_detect` implements BR-1's three trigger conditions: an explicit `--intake` flag, `$ARGUMENTS` resolving to a readable file path, or `$ARGUMENTS` exceeding 25 lines. Returns 0 when intake should run, 1 when it should not.
- [ ] `adlc_intake_detect` exports `ADLC_INTAKE_KIND` (`transcript` | `notes` | `ticket` | `prose`), `ADLC_INTAKE_PATH`, and `ADLC_INTAKE_REASON` (which trigger fired).
- [ ] `adlc_intake_segment` splits the source into ordered segments of 200 lines, labelled `S01`, `S02`, … and exports `ADLC_INTAKE_SEGMENTS` (count) and `ADLC_INTAKE_LINES` (total).
- [ ] `adlc_intake_segment` returns 3 and emits a message naming the actual line count and the 8000-line budget when the source exceeds 40 segments. It never truncates (BR-12, AC-10).
- [ ] `adlc_intake_redact` applies the 5-pattern BSD-sed credential chain (`sk-…`, `AKIA…`, `ghp_…`, `Bearer …`, `[A-Z_]+_(API_KEY|TOKEN)` assignments) in place and removes the `.bak` file.
- [ ] `adlc_intake_sections` reads the requirement template (project copy first, then `~/.claude/skills/templates/`) and emits its `## ` headings minus `Description`, `Assumptions`, `Open Questions`, and `Retrieved Context`.
- [ ] File is `#!/bin/sh`, POSIX-only: no `local`, no `[[`, no arrays, no `function` keyword, no GNU-only flags, no `\b` in `grep -E`.
- [ ] No variable named `status` (zsh reserved — LESSON-329). No unquoted word-splitting for path lists (LESSON-335).
- [ ] Sourcing the partial emits nothing on stdout or stderr.
- [ ] `sh tools/lint-skills/check.sh` exits 0.

## Technical Notes

Follow the header-comment style of `partials/delegate-tools-path.sh` and
`partials/emit-step-telemetry.sh`: a block explaining the sourced-not-executed contract,
the caller contract, and the POSIX constraint list.

Use the two-level template fallback for `adlc_intake_sections`:
`.adlc/templates/requirement-template.md` first, then
`~/.claude/skills/templates/requirement-template.md`. In the toolkit repo itself neither
of those exists — the canonical copy is at the repo-root `templates/`, so the chain needs
a third arm for dogfooding.

For temp files use `mktemp -t adlc-intake.XXXXXX`. Never a predictable path — that is the
symlink/TOCTOU foothold LESSON-008 records.

Segment labels are zero-padded to two digits so lexical and numeric order agree up to the
40-segment budget.
