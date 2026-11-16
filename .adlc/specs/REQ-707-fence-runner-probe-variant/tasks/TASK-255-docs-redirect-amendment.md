---
id: TASK-255
title: "Docs for the redirect amendment: the probe README and the CHANGELOG"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-16
updated: 2026-11-16
dependencies: [TASK-253, TASK-254]
---

## Description

Bring `tools/adlc/README.md` and `CHANGELOG.md` in line with the amendment (REQ-707 BR-11). No committed result file changes.

## Files to Create/Modify

- `tools/adlc/README.md`, the `runner-prefix` section:
  - the `runner-redirect` row names the target `<repo>/.probe/redirect-<launch>`;
  - the "Each launch reads" paragraph says the redirect's effect is the runner sentinel and the target together, and why the target alone is not evidence;
  - the BUG-279 paragraph no longer says codex's redirect stays `unknown` because of where the target was. It says the target was moved into the working copy, and that a live run decides whether codex's model now submits it.
- `CHANGELOG.md`, `## [Unreleased]`: one Changed entry for the amendment. It covers the target location, the effect, and the `sandboxed-refusal` flag. It names that the committed codex result predates it. Reword the BUG-279 Fixed entry's sentence about `runner-redirect` so it is not contradicted. Add no new `###` heading above `### Reversed decisions (REQ-666 BR-6)`.

## Acceptance Criteria

- [ ] The README describes the target location, the two-file effect, and `sandboxed-refusal`.
- [ ] The CHANGELOG has the amendment entry, and no sentence still says the redirect target sits outside the workspace on codex.
- [ ] `test_harness_probe_docs.py` and the lint-skills doc tests pass, and `bash tools/lint-skills/check.sh` exits 0.
- [ ] `git diff origin/main -- .adlc/research/harness-probes/` is empty.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `tools/adlc/tests/test_harness_probe_docs.py` | no |
| AC-9 | test-case | `tools/adlc/tests` (full suite) and `tools/lint-skills/check.sh` | no |

## Technical Notes

- `tools/lint-skills/tests/test_skill_text_portability.py` cuts the `### Reversed decisions (REQ-666 BR-6)` section at the next `### `, so add entries under the existing `### Changed` and `### Fixed` headings only.
- Keep the README's REQ-664 section heading and the residual paragraph that `test_harness_probe_docs.py` pins.
