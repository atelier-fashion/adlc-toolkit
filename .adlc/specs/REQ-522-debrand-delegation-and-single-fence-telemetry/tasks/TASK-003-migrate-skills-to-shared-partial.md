---
id: TASK-003
title: "Migrate spec/proceed/wrapup/analyze SKILL.md to shared telemetry partial + de-brand prose"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-002]
---

## Description

Switch the four delegating skills onto the flag-file-derived shared partial (ADR-4),
de-brand every Kimi-named identifier and every "delegating … to kimi" prose line, and
switch all `kimi-gate.sh`/`kimi-tools-path.sh` source-lines to the canonical
`delegate-*.sh`. This is where the cross-fence bug is structurally eliminated at the
call sites.

## Files to Create/Modify

- `spec/SKILL.md` (Step 1.6), `proceed/SKILL.md` (Phase 5), `wrapup/SKILL.md` (Step 4):
  - Replace the inline 16-line resolution fence with: at create time
    `"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"`; at gate
    time mark `reason`; around the delegate call mark `invoked=1` then `exit=<rc>`; and
    a final 3-line fence `. .adlc/partials/emit-step-telemetry.sh …; _adlc_emit_step_telemetry <skill> <step>`.
  - Source `delegate-tools-path.sh` / `delegate-gate.sh` (not the kimi-* names).
  - Rename `KIMI_TOOLS`→`DELEGATE_TOOLS`, `ASK_KIMI_INVOKED`→(now a flag mark),
    `KIMI_EXIT`→(flag mark), `ADLC_KIMI_GATE_REASON`→`ADLC_DELEGATE_GATE_REASON`.
  - Replace `ADLC_DISABLE_KIMI` mentions with `ADLC_DISABLE_DELEGATE` (gate comments,
    fallback prose).
  - Prose: "delegating … to kimi" → "delegating … to the delegate"; "KIMI PROPOSAL"
    untrusted-block header → "DELEGATE PROPOSAL (untrusted)".
- `analyze/SKILL.md` — same cross-fence fix (it has the identical bug: sets
  start_s/ASK_KIMI_INVOKED/KIMI_EXIT in one fence, calls the helper in another). Switch
  to flag-file marks; pass `analyze` as the skill arg; de-brand the source-lines and
  the `KIMI_TOOLS`/check-delegation references.
- `agents/delegate-pre-pass.md` — de-brand the 12 kimi references (var names, prose).

## Acceptance Criteria

- [ ] No SKILL.md sets a non-exported telemetry var in one fence and reads it in
      another (the cross-fence-var lint, TASK-005, passes on all four).
- [ ] All four skills source `delegate-gate.sh` / `delegate-tools-path.sh` and call
      `_adlc_emit_step_telemetry <skill> <step>`.
- [ ] `grep -ri kimi spec/SKILL.md proceed/SKILL.md wrapup/SKILL.md analyze/SKILL.md
      agents/delegate-pre-pass.md` returns nothing.
- [ ] `ADLC_DISABLE_KIMI` no longer appears in any of the four skills (only
      `ADLC_DISABLE_DELEGATE`).
- [ ] The canonical-helper lint check still passes (anchors satisfied via the partial).

## Technical Notes

- The flag-file `mark` calls are the ONLY way state crosses fences — that is the BR-4
  contract. Each `mark` lives in the same fence as the operation it records.
- Keep the MANDATORY-no-discretion compliance paragraphs; just de-brand them.
- Subagent/`/proceed` Phase 5 already skips the delegate pre-pass in subagent mode —
  leave that logic, only rename identifiers.
- POSIX/zsh/BSD-safe; no bare `$<digit>` introduced.
