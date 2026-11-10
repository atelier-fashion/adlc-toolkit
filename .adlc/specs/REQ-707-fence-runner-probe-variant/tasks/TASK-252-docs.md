---
id: TASK-252
title: "Document the `runner-prefix` variant: tools/adlc/README.md, README.md, CHANGELOG.md"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-250]
---

## Description

Describe the variant where `fence-vs-allowlist` is already described (REQ-707 BR-11). No result file changes.

## Files to Create/Modify

- `tools/adlc/README.md` — the `fence-vs-allowlist` entry: the thirteen launches, the stubs, the decision rule, the launch count, and that the variant sits outside the probe-level status.
- `README.md` — the `fence-vs-allowlist` row of the probe catalogue.
- `CHANGELOG.md` — an Unreleased entry.

## Acceptance Criteria

- [ ] Each of the three files names `runner-prefix`, and `tools/adlc/README.md` states BR-5's rule in the order positive, baseline, refusal half, and BR-4's `ask-split` rule.
- [ ] `git diff --name-only origin/main` lists no path under `.adlc/research/harness-probes/`.
- [ ] `bash tools/lint-skills/check.sh` exits 0.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | structural-check | `bash tools/lint-skills/check.sh` | yes |
| AC-9 | structural-check | `bash tools/lint-skills/check.sh` | yes |

## Technical Notes

- Enumerate only what the module declares. The names come from `RUNNER_LAUNCHES` (LESSON-019).
