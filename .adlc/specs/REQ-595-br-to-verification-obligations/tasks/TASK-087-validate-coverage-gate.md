---
id: TASK-087
title: "validate — obligation coverage, benign-path, and vacuous-run gates"
status: draft
parent: REQ-595
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-085]
repo: adlc-toolkit
---

## Description

Extend `validate/SKILL.md`'s "Validating Tasks" phase with three checks over the
task set's `## Verification` blocks:

1. **Coverage (BR-2, advisory)** — report every numbered BR **and** AC in the REQ
   with no obligation anywhere in the task set, naming the unmapped ids.
2. **Benign path (BR-4, advisory)** — report any BR worded as detection, refusal,
   or a halt that carries no `benign_path` obligation.
3. **Vacuous run (BR-5, blocking)** — a verification run that exits 0 having done
   no work fails. Work is defined per kind: `test-case` reports executed cases,
   `structural-check` reports files scanned.

Checks 1 and 2 are advisory in epoch 1 and share that posture deliberately — both
are obligation-*shape* judgments, and a mixed gate where one new check blocks and
the other does not is incoherent. Check 3 is blocking from epoch 1 because it is
not a coverage judgment but evidence the verification did not run at all.

## Files to Create/Modify

- `validate/SKILL.md` — extend the "Validating Tasks" checklist with the three
  checks; extend "Step 3: Report Results" so advisory obligation findings are
  categorized as **Warning** (surfaced, non-blocking) and the vacuous-run failure
  as **Blocker**

## Acceptance Criteria

- [ ] The coverage check reports unmapped **BR and AC** ids by name (BR-2)
- [ ] AC coverage is gated on the same footing as BR coverage — not a lesser
      check (BR-2, AC-3)
- [ ] Advisory findings are explicitly categorized as Warning and stated to not
      block advancement; the epoch-1 posture and the named follow-up promotion
      REQ are both recorded (BR-2, AC-2, AC-3)
- [ ] The benign-path check reports a detection/refusal/halt BR with no
      `benign_path` obligation as an advisory finding that does not block (BR-4, AC-6)
- [ ] The vacuous-run check is stated as **Blocker** severity, with the per-kind
      work definition (`test-case` → executed cases, `structural-check` → files
      scanned), and either count at zero fails (BR-5, AC-7)
- [ ] A REQ with zero numbered BRs passes with a notice and no failure — the gate
      does not invent rules to check (BR-10, AC-9)
- [ ] A task file with no `## Verification` section still validates (AC-10)
- [ ] Any shell added is BSD/zsh-safe: no `\b` in `grep -E`, no bare `$<digit>`,
      no `status` variable, no unquoted word-splitting, `find` not bare globs (BR-8)
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the modified
      `validate/SKILL.md` and scans >0 files

## Technical Notes

The detector-shape heuristic for BR-4 must be case-insensitive substring matching
(`detect`, `refus`, `halt`, `reject`, `block`, `flag`) — **not** `\b` word
anchors, which BSD `grep -E` silently fails to honor on macOS (LESSON-013). Match
stems, not whole words, so `refuses`/`refusal` and `blocking`/`blocked` both hit.

The gate reads the REQ's rules at run time. Do not embed a copy of REQ-595's own
rule list in the skill — enumerations rot (LESSON-019).

ACs are addressed by 1-based ordinal within `## Acceptance Criteria`, per
TASK-085's convention entry. State the addressing where the check is defined so a
reader does not have to infer it.

BR-5's `structural-check` counter is produced by TASK-088's `check.py` change.
This task specifies the gate; TASK-088 makes the count observable. They are
independent — neither blocks the other — but the gate prose should name
files-scanned as the count it reads.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | structural-check | `tools/lint-skills`: sentinels, balance over `validate/SKILL.md`; coverage-check prose names both BR and AC | no |
| BR-4 | structural-check | `tools/lint-skills`: full-root run; benign-path check present with advisory posture matching BR-2 | no |
| BR-5 | structural-check | `tools/lint-skills`: full-root run; per-kind work definition and Blocker severity present | no |
| BR-8 | structural-check | `tools/lint-skills`: posix-fence, arg-templating, balance, cross-fence-fn, cross-fence-var over `validate/SKILL.md` | no |
| BR-10 | structural-check | `tools/lint-skills`: full-root run; zero-numbered-BR REQ passes with a notice | yes |
| AC-2 | structural-check | `tools/lint-skills`: full-root run; unmapped-BR finding specified as advisory, non-blocking | yes |
| AC-3 | structural-check | `tools/lint-skills`: full-root run; unmapped-AC finding specified identically to AC-2 | yes |
| AC-6 | structural-check | `tools/lint-skills`: full-root run; detector-BR-without-benign-path specified as advisory, non-blocking | yes |
| AC-9 | structural-check | `tools/lint-skills`: full-root run; zero-BR REQ notice path | yes |
| AC-10 | structural-check | `tools/lint-skills`: full-root run over the existing task corpus, none of which carries a `## Verification` section | yes |

Every `benign_path: yes` row here is a must-not-fire assertion — the advisory
checks must *not* halt advancement, and the zero-BR and no-`## Verification`
cases must *not* produce a failure. A gate validated only against its firing
inputs ships broken and passes its own suite (LESSON-440).
