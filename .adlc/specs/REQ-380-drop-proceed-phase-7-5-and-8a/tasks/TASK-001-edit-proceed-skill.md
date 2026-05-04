---
id: TASK-001
title: "Remove Phase 7.5 and Phase 8a from proceed/SKILL.md"
req: REQ-380
status: complete
created: 2026-05-04
updated: 2026-05-04
dependencies: []
repo: adlc-toolkit
---

## Files to Modify
- `proceed/SKILL.md`

## Acceptance Criteria

- [ ] Autonomous-Execution-Contract preamble: "**five** legitimate halt points" → "**three**". List exactly: (1) validation fails 3 times at any gate, (2) reflector surfaces user-facing questions, (3) merge conflicts during rebase. Delete the canary-fails entry (#3) and the Phase 8a 30-min-timeout entry (#5). Renumber so the new list is 1, 2, 3 with no gaps. (BR-3)
- [ ] Pipeline-State-Tracking section: in the JSON schema example (lines ~124–136), the `snapshotBranch` and `snapshotPR` fields stay (still nullable, still default null), but the prose paragraph at lines ~154 explaining how Phase 8a populates them is rewritten to say: "These fields are deprecated as of REQ-380. The skill no longer writes them; they remain in the schema for read-back compatibility with state files written before REQ-380. A missing or null value is the expected state on all new runs." (BR-5)
- [ ] Gate Protocol item 5 / state-file paragraph: any reference to `snapshot_promotion` or Phase 8a as a gate-driver is deleted. (BR-2)
- [ ] Phase 7 end-of-phase log (line ~434): "Continue to Phase 7.5 (or Phase 8) immediately." → "Continue to Phase 8 immediately." (BR-4, BR-6)
- [ ] Phase 7.5 section (line ~438) and its body: **deleted entirely**, including its end-of-phase log mentioning Phase 8a transition and the optional-canary opt-in semantics. (BR-1)
- [ ] Phase 8a section (line ~456) and its body: **deleted entirely**, including the helper-script invocation block, the 30-minute polling logic, and the `phase_8a_*` log line specs. (BR-2)
- [ ] Phase 8 (Wrapup) gate clause: `**Gate**: \`currentPhase\` must be \`8\` and either \`8a\` or \`7.5\` (or \`7\`) must be in \`completedPhases\`.` → `**Gate**: \`currentPhase\` must be \`8\` and \`7\` must be in \`completedPhases\`.` Delete the trailing sentence about "When `pipeline.snapshot_promotion: true`, the legitimate predecessor is `8a`…". (BR-2, BR-6)
- [ ] Any other inline phase-number cross-references (e.g., "Phase 7 → Phase 7.5 → Phase 8" anywhere in prose) updated to "Phase 7 → Phase 8". Audit the whole file. (BR-4, BR-6)
- [ ] Error Handling section: no references to Phase 7.5 or Phase 8a remain.
- [ ] Verification: `grep -nE "Phase 7\.5|Phase 8a|phase_8a|snapshot_promotion" proceed/SKILL.md` returns zero matches in prose (the schema-example field names `snapshotBranch` / `snapshotPR` may remain per BR-5).
- [ ] Skill remains valid markdown — frontmatter intact, ethos macro intact, all other phases untouched.

## Technical Notes

- Edit in-place with `Edit` tool. The file is ~520 lines; multiple targeted edits are cleaner than a full rewrite.
- Preserve all surrounding prose verbatim (per BR-3: "Other prose in that section MUST be preserved verbatim").
- The schema example fields (`snapshotBranch`, `snapshotPR`) stay; only the explanatory paragraph after the schema changes.
