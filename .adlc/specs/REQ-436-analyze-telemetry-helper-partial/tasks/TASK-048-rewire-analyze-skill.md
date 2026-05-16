---
id: TASK-048
title: "Rewire analyze/SKILL.md: remove inline helper, source the partial at both emit points"
status: complete
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-047]
---

## Description

Remove the inline helper-definition fenced block and make both emit points source
`partials/emit-step-telemetry.sh` in the same fenced block as the invocation.
Implements ADR-2 (items 2-4). Fixes Defect-1.

## Files to Create/Modify

- `analyze/SKILL.md`:
  - **Delete** the helper-definition fenced block (post-REQ-433 lines 41-66 — the
    ```sh block that sources `kimi-tools-path.sh` then defines
    `_adlc_emit_step_telemetry() { … }`).
  - **Reword** the line-39 prose: replace "define once here; both Step 1.5 and
    Step 1.6 invoke it…" with text stating the helper is sourced from
    `partials/emit-step-telemetry.sh` at each emit point, with a one-clause
    pointer to the execution-model rationale (SKILL.md fenced blocks don't share
    shell state across steps — see conventions.md / the REQ-436 LESSON).
  - **Step 1.5 emit block** (currently lines 115-118): replace the
    `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`
    line with
    `. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh`.
    Keep the next line `_adlc_emit_step_telemetry Step-1.5` unchanged.
  - **Step 1.6 emit block** (currently lines 177-180): same swap; keep
    `_adlc_emit_step_telemetry Step-1.6` unchanged.
  - Do **not** touch the before-gate-check blocks (70-77, 126-133), the gate
    blocks (81-89, 137-145), `start_s`, the `trap`, the
    `ASK_KIMI_INVOKED`/`KIMI_EXIT` lines, or the Step-1.6 delegated-path
    `kimi-tools-path` source at line 152.

## Acceptance Criteria

- [ ] `grep -c '_adlc_emit_step_telemetry() {' analyze/SKILL.md` == 0.
- [ ] `grep -c 'emit-step-telemetry.sh' analyze/SKILL.md` == 2 (one per emit block), each immediately followed by the matching `_adlc_emit_step_telemetry Step-1.5` / `Step-1.6` line within the same fenced block.
- [ ] `analyze/SKILL.md` still contains, inline, each of: `start_s=$(date -u +%s)`; `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`; `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh` (L1/L4/L5 preserved per ADR-2 check).
- [ ] `git diff main -- analyze/SKILL.md` shows only: helper-def block removed, line-39 prose reworded, two emit-block source-line swaps. Gate prologues / `trap` / `start_s` / `ASK_KIMI_INVOKED` / `KIMI_EXIT` byte-identical (AC-11).
- [ ] No `local ` remains anywhere in `analyze/SKILL.md` (AC-4).

## Technical Notes

- Edit via the worktree path
  `/Users/brettluelling/Documents/GitHub/adlc-toolkit/.claude/worktrees/reverent-heyrovsky-f96d80/analyze/SKILL.md`
  — NOT `~/.claude/skills/analyze/` (that resolves to the main checkout).
- Line numbers above are post-REQ-433 (HEAD 7dfc646); re-read the file before
  editing in case prior tasks shifted them.
- The L5 preservation is the subtle one: confirm `kimi-tools-path.sh` source
  still appears at lines ~71/127/152 after the edits (before-gate + Step-1.6
  delegated path) so `check_canonical` L5 stays satisfied from SKILL.md text.
