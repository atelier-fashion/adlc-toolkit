---
id: TASK-003
title: "Mock-backend test matrix (ops × providers × error classes) + config tests"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001, TASK-002]
---

## Description

Offline test matrix proving the adapter (BR-10): every op × both providers × each
normalized error class via `ADLC_FORGE_MOCK=1`, plus provider-resolution and config
(key-refusal, missing-PAT) cases. Runs under macOS zsh/bash and Ubuntu bash.

## Files to Create/Modify

- `partials/tests/forge.test.sh` — shell harness (consistent with `id-alloc.test.sh`),
  registered in `partials/tests/run.sh`: asserts each op's normalized output per provider
  per scenario, fail-loud `auto`, GitHub byte-compat command shape (via a `gh` shim that
  records argv), policy-block → `merge-blocked-by-policy`, ADO `pr_comment`→
  `feature-unsupported`.
- `tools/adlc/tests/test_forge_config.py` — pytest: `parse_forge_config`, precedence,
  `detect_provider_from_url` (incl. unrecognized → raise), key-shaped `auth:` refusal,
  missing-PAT → `auth-missing` surface.

## Acceptance Criteria

- [ ] Every op (`pr_create/ready/edit/view/list/merge/comment`) asserted for BOTH
      providers under the mock, including each error class (`auth-missing`,
      `pr-not-found`, `merge-blocked-by-policy`, `feature-unsupported`, `network`).
- [ ] Provider resolution asserted: project>machine>auto; auto-github, auto-ado,
      auto-unrecognized (fails loud naming URL + providers).
- [ ] GitHub backend byte-compat asserted via an argv-recording `gh` shim — the emitted
      command/flags match the pre-migration call sites for each op (BR-3).
- [ ] State normalization asserted: ADO active/completed/abandoned → OPEN/MERGED/CLOSED.
- [ ] Key-shaped `auth:` refused; missing PAT env → `auth-missing` with remediation text.
- [ ] `partials/tests/run.sh` runs the new harness; pytest suite green; both pass under
      `zsh -c` and `bash -c` (and Ubuntu bash in CI).

## Technical Notes

Use a PATH-shim directory with a recording `gh`/`az` for byte-compat assertions when not
using the in-process mock dispatcher. Follow the `id-alloc.test.sh` assert/idiom style.
pytest mirrors `test_checks.py` conventions (Profile fixtures, tmp config files).
