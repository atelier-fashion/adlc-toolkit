---
id: TASK-200
title: "/init --harness, AGENTS.md and CLAUDE.md, /template-drift harness-config, dogfood"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-196]
repo: adlc-toolkit
---

## Description

`/init` renders the project layer through `adlc harness render`, writes AGENTS.md
and the CLAUDE.md import, and `/template-drift` gains the `harness-config` surface
(BR-11, BR-12). The toolkit gets its own AGENTS.md and CLAUDE.md.

## Files to Create/Modify

- `init/SKILL.md` — Step 8 renders; `--harness`; instruction files; sync-surfaces
- `template-drift/SKILL.md` — harness-config step and surface
- `template-drift/references/drift-report.md` — seven surfaces
- `templates/instructions/AGENTS.md`, `templates/instructions/CLAUDE.md` — bodies
- `AGENTS.md`, `CLAUDE.md` — toolkit dogfood
- `tools/adlc/tests/test_harness_framework.py` — AC-9, AC-10 sandbox cases

## Acceptance Criteria

- [ ] AC-9 and AC-10 hold in sandbox repos; both sync-surfaces blocks list harness-config

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `tools/adlc/tests/test_harness_framework.py::test_init_render_project_layer` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_harness_framework.py::test_claude_md_prepend_only` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_harness_framework.py::test_drift_old_template_consumer` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_harness_framework.py::test_init_render_project_layer` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_harness_framework.py::test_claude_md_prepend_only` | yes |

## Technical Notes

ADR-11, ADR-12.
