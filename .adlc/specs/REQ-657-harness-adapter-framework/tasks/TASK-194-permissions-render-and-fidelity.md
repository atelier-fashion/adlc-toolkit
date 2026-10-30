---
id: TASK-194
title: "permissions.yml, permissions render, matcher and fidelity engine; delete the settings template"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-193]
repo: adlc-toolkit
---

## Description

The semantic allowlist, its per-scope render, the shared-base rule, the fence, exec
deny rendering, the BR-9 matcher and fidelity verdicts, the `claude` golden render,
and the deletion of `templates/claude-settings-template.json` with every reader
re-pointed (BR-6, BR-7, BR-8, BR-9).

## Files to Create/Modify

- `templates/permissions.yml` — routine + deny tiers, `default_mode`, `comment`
- `templates/claude-settings-template.json` — deleted
- `tools/adlc/harness_render.py` — rules, matcher, fidelity, claude-settings-json format
- `harness/claude/rendered/settings.json` — golden render
- `.claude/settings.json` — toolkit's own, now a render
- `tools/adlc/tests/test_harness_framework.py` — AC-6, AC-7, AC-16, AC-17 vectors
- `tools/adlc/tests/fixtures/harness/` — fake, fake-prefix, result files, pinned old sets
- `tools/adlc/tests/test_harness_probe_pins.py` — re-pointed to permissions.yml
- `tools/adlc/harness_probe.py` — comment re-pointed
- `tools/lint-skills/tests/test_skill_text_portability.py` — re-pointed to the golden

## Acceptance Criteria

- [ ] The claude render's allow/ask/defaultMode sets equal the pinned template sets, fence excepted
- [ ] Every AC-7, AC-16, AC-17 vector holds
- [ ] `grep -rn claude-settings-template` is empty on the distribution surface

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_harness_framework.py::test_permissions_two_tiers` | no |
| BR-7 | test-case | `tools/adlc/tests/test_harness_framework.py::test_claude_render_equals_pinned_template` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_harness_framework.py::test_shared_base_rule_scopes` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_harness_framework.py::test_matcher_vectors` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_harness_framework.py::test_template_deleted_and_unreferenced` | no |
| AC-6 | test-case | `tools/adlc/tests/test_harness_framework.py::test_claude_render_equals_pinned_template` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_harness_framework.py::test_fidelity_claude_clean` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_harness_framework.py::test_matcher_vectors` | yes |
| AC-17 | test-case | `tools/adlc/tests/test_harness_framework.py::test_scope_vectors` | yes |

## Technical Notes

ADR-4 to ADR-8. The pinned old sets are a fixture copied from `origin/main` 5afc2a8.
