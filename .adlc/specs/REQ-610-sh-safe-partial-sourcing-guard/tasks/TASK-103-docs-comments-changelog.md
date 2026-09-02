---
id: TASK-103
title: "Retire the pattern where it is documented: conventions, partials README, architecture, header comments, companion .md, CHANGELOG"
status: complete
parent: REQ-610
created: 2026-09-02
updated: 2026-09-02
dependencies: []
---

## Description

Every place that *teaches* the two-level pattern now teaches the canonical spelling and
says why (ADR-1, ADR-8): conventions.md "Bash in skills", `partials/README.md`'s model-2
example, the Partials paragraph of `.adlc/context/architecture.md`, the header comment of
six partials, the code-fence examples in four companion `.md` files, and a CHANGELOG entry
carrying the consumer re-sync note (BR-10). Harness case (e), which proves this task's
grep-level outcome, is added by TASK-102 (single owner of the harness file after TASK-100).

## Files to Create/Modify

- `.adlc/context/conventions.md` — "Bash in skills": replace the three inline occurrences; add a short paragraph: `.` is a POSIX special built-in, a failed source exits a non-interactive `sh`, hence `[ -f ]` before `.`; the two rejected forms (`command .` — still exits under macOS `/bin/sh`; `[ -f A ] && . A || . B` — double-sources when A's last status is non-zero) with one line each; retired shape shown as `. <local> 2>/dev/null || . <canonical>`
- `.adlc/context/architecture.md` — Partials paragraph: canonical spelling + the one-sentence reason proposed in architecture.md "Proposed additions"
- `partials/README.md` — model-2 example (line ~112) to the canonical spelling; a sentence on why; the model-1 (`!`-macro `sh … || sh …`) example is unchanged and a note says why it needs no guard
- `partials/id-alloc.sh`, `partials/id-recheck.sh`, `partials/trial-merge.sh`, `partials/forge.sh`, `partials/attribution.sh` — header-comment call-site examples to the canonical spelling
- `partials/delegate-gate.sh` — header comment: add the call-site example in canonical form if it shows one, else leave
- `partials/delegate-gate.md`, `partials/forge.md`, `partials/emit-step-telemetry.md`, `partials/trial-merge.md` — every code-fence example to the canonical spelling
- `CHANGELOG.md` — entry under the unreleased/next section: what changed, why (`sh` special built-in), that vendored `.adlc/partials/*.sh` will report `stale` in `/template-drift` and must be re-synced per file (`emit-step-telemetry.sh` and — found later by the dash pass — `id-recheck.sh` carry live fixes, the other four comment-only), and that `tools/lint-skills` now rejects the retired shape

## Acceptance Criteria

- [ ] `grep -rF '2>/dev/null || . ~/.claude/skills/partials/' */SKILL.md agents partials proceed templates README.md .adlc/context` returns nothing once TASK-102 has also landed (case (e) is red until then; both tasks are in the same PR)
- [ ] conventions.md "Bash in skills" contains the canonical spelling verbatim, the phrase "special built-in", and names both rejected forms with their failure (AC-7)
- [ ] `partials/README.md` model-1 example is byte-identical to before; model-2 example is the canonical spelling
- [ ] Every partial header comment that shows a call-site example shows the canonical spelling; `grep -c 'if \[ -f .adlc/partials/' partials/*.sh partials/*.md` is ≥ 1 for each of the nine files that show a call-site example (`delegate-gate.sh` shows none; its contract lives in `delegate-gate.md`)
- [ ] CHANGELOG entry names the re-sync and distinguishes the two partials with live fixes from the comment-only ones (AC-10)
- [ ] No historical file under `.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/` is modified (BR-8 last sentence) — `git diff --stat` confirms

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | `partials/tests/source-guard.test.sh::case_e_retired_literal_absent_from_distribution` | no |
| AC-6 | test-case | `partials/tests/source-guard.test.sh::case_e_retired_literal_absent_from_distribution` | no |
| AC-7 | test-case | `partials/tests/source-guard.test.sh::case_e_conventions_carry_canonical_spelling` | no |

## Technical Notes

- Header comments are `#` lines; the harness extraction skips them, so the *only* thing that proves they were updated is case (e)'s grep — keep the grep over `partials/` in the surface list.
- `partials/delegate-gate.sh`'s header today does not show a call-site example (its contract is in `delegate-gate.md`); do not invent one — update the `.md`.
- CHANGELOG: follow the existing entry style (check the top of the file). Suggested consumer line: "Re-sync `.adlc/partials/` per file (`/template-drift` will list six partials as `stale`); `emit-step-telemetry.sh` and `id-recheck.sh` carry executable fixes, the rest are header-comment updates."
- BR-10 and AC-10 have no obligation row: a CHANGELOG entry is prose, and no artifact in this repo executes over it. `/validate` will report them as advisory gaps; that is the honest state, not an omission.
- BR-9 (no new partial) is mapped in TASK-102 to `sync-surface-parity` as the closest structural surface; it is a weak proxy and review should confirm no `partials/source-partial.sh` exists.
- This task does not touch `partials/tests/source-guard.test.sh`; TASK-102 adds case (e) so two parallel tasks never edit one file.
