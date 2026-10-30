---
id: TASK-208
title: "Documentation and the live hook check"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: ['TASK-204', 'TASK-205', 'TASK-206', 'TASK-207']
repo: adlc-toolkit
---

## Description

Bring the docs to the shipped surface and record the live verification (BR-15, AC-1, AC-10).

## Files to Create/Modify

- `README.md` — hook row: the sidecar is real
- `partials/README.md` — session-record and session-transcript entries
- `.adlc/context/architecture.md` — knowledge-retrieval paragraph; REQ-657 bullet no longer says stub
- `CHANGELOG.md` — Unreleased: surfaces and consumer re-sync
- `.adlc/specs/REQ-660-session-sidecar-and-multi-harness-transcripts/verification.md` — live evidence and AC-9/AC-10 rows

## Acceptance Criteria

- [ ] Docs name `--format`, the sidecar and the three-rung chain
- [ ] CHANGELOG names the consumer re-sync: settings hook entry, gitignore line, vendored partial
- [ ] verification.md records the real-binary sidecar run under a throwaway `HOME`, with no home path or email

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-15 | structural-check | `tools/lint-skills/check.sh: session-gitignore` | no |
| AC-9 | structural-check | `.adlc/specs/REQ-660-session-sidecar-and-multi-harness-transcripts/verification.md` | no |
| AC-10 | structural-check | `.adlc/specs/REQ-660-session-sidecar-and-multi-harness-transcripts/verification.md` | no |

## Technical Notes

Any live run uses a throwaway `HOME` and `ADLC_HOME`. Keep architecture.md's retrieval text brief: name the chain and point at this REQ.

## Dependencies

TASK-204, TASK-205, TASK-206, TASK-207
