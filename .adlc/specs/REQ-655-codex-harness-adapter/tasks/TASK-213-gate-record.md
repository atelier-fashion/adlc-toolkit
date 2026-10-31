---
id: TASK-213
title: "Run and record the BR-10 gate"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-212]
repo: adlc-toolkit
---

## Description

Run the interactive cases through a pty against a throwaway repo and bare remote, and record every row.

## Files to Create/Modify

- `.adlc/specs/REQ-655-codex-harness-adapter/requirement.md` — the gate record
- `harness/codex.yml` — `sandbox_can_reach_common_gitdir`, the `by_hand` fields

## Acceptance Criteria

- [ ] Every BR-10 row is `prompted`, `ran`, `sandbox-failed`, a precedence value, or named as owed
- [ ] `~/.codex/config.toml` is byte-identical afterwards, verified with `cmp`
- [ ] No deny-tier approval was answered yes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | tools/adlc/tests/test_harness_codex.py::test_gate_record_is_complete | yes |
| AC-10 | test-case | tools/adlc/tests/test_harness_codex.py::test_gate_record_is_complete | yes |

## Technical Notes

ADR-8, ADR-10. A case the pty cannot read stays owed; nothing is guessed.
