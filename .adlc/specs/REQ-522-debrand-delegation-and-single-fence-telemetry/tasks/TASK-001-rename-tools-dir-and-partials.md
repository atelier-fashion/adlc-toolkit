---
id: TASK-001
title: "Rename tools/kimi → tools/delegate and rewire path/gate partials"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: []
---

## Description

Foundation rename (ADR-1, ADR-2). `git mv tools/kimi → tools/delegate`, repoint the
canonical path/gate resolvers at the new directory, stop exporting the legacy
`KIMI_TOOLS` / `ADLC_KIMI_GATE_REASON` aliases, delete the two legacy source-through
partials, and rename the gate doc. This is the base every other task builds on.

## Files to Create/Modify

- `tools/kimi/` → `tools/delegate/` — `git mv` the whole directory (preserves history).
- `partials/delegate-tools-path.sh` — resolution paths `tools/kimi` → `tools/delegate`
  (both the project-local and `~/.claude/skills/tools/delegate` global). REMOVE the
  `KIMI_TOOLS` export lines (no reader remains after the rename). Keep only
  `DELEGATE_TOOLS`.
- `partials/delegate-gate.sh` — drop the `ADLC_DISABLE_KIMI` acceptance (BR-3: only
  `ADLC_DISABLE_DELEGATE` disables) and the `ADLC_KIMI_GATE_REASON` defensive default
  if present; keep the `KIMI_API_KEY`/`MOONSHOT_API_KEY` opt-in reads (data continuity).
- `partials/kimi-tools-path.sh` — DELETE (after TASK-003 switches every source-line; but
  the delete lands here since no canonical caller will reference it post-migration —
  coordinate: this task deletes it, TASK-003 must already target the canonical name).
- `partials/kimi-gate.sh` — DELETE (same coordination note).
- `partials/kimi-gate.md` → `partials/delegate-gate.md` — `git mv`; de-brand its body
  (header, the `adlc_kimi_gate_check` references → `adlc_delegate_gate_check`, the
  `ADLC_DISABLE_KIMI` mentions, `KIMI_TOOLS` → `DELEGATE_TOOLS`). Preserve the 0/1/2
  contract text.
- `partials/README.md`, `partials/delegate-tools-path.sh` header comments — drop
  "executables still physically live under tools/kimi" notes; they now live under
  `tools/delegate`.

## Acceptance Criteria

- [ ] `tools/delegate/` exists with full git history; `tools/kimi/` is gone.
- [ ] `partials/delegate-tools-path.sh` resolves `tools/delegate` and exports only
      `DELEGATE_TOOLS` (no `KIMI_TOOLS`).
- [ ] `partials/kimi-tools-path.sh` and `partials/kimi-gate.sh` are deleted.
- [ ] `partials/kimi-gate.md` is renamed to `delegate-gate.md` and de-branded.
- [ ] `grep -rl "tools/kimi" partials/ tools/delegate/` returns nothing (paths updated).
- [ ] `delegate-gate.sh` no longer accepts `ADLC_DISABLE_KIMI`; still reads
      `KIMI_API_KEY`/`MOONSHOT_API_KEY` for opt-in.

## Technical Notes

- Because `/init` copies `partials/*.sh` wholesale, deleting the legacy partials is
  safe once every canonical source-line targets `delegate-*.sh` (TASK-003 + TASK-005).
  This task is sequenced FIRST; TASK-003/004/005 reference the post-rename paths.
- `delegate-tools-path.sh` / `delegate-gate.sh` cannot `source` each other (a sourced
  partial can't locate a sibling — `$0` is the caller). Keep the resolution inlined.
- POSIX/zsh/BSD-safe (BR-7): no bashisms in the partials.
