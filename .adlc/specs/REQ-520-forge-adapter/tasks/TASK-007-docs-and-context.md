---
id: TASK-007
title: "Document the forge adapter — context, conventions, config schema, README"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002, TASK-004, TASK-006]
---

## Description

Capture the forge adapter as first-class knowledge (ethos #2): document the `forge:`
config section, the adapter call pattern (mirroring the delegation pattern doc), the
provider-resolution precedence, and the doctor forge check. Update `tools/adlc/README.md`
for the new check and the new `tools/adlc/forge_config.py` module.

## Files to Create/Modify

- `.adlc/context/conventions.md` — add a "Forge adapter (provider-agnostic PR ops)"
  subsection next to the existing "Delegation pattern" section: the source-line, the op
  set, the rule that skills NEVER call `gh pr` ops directly (lint-enforced).
- `.adlc/context/architecture.md` — add `partials/forge.sh` + `tools/adlc/forge_config.py`
  to the cross-cutting-dependencies / partials description; note the doctor forge check
  superseding gh-auth.
- `tools/adlc/README.md` — document the `forge` check and `forge_config.py`.
- `partials/README.md` — list `forge.sh`.

## Acceptance Criteria

- [ ] conventions.md documents the `forge:` config section (provider/auth, source-name
      discipline) and the adapter source-line + two-level fallback call pattern.
- [ ] architecture.md references the partial, the config reader, and the doctor check
      supersession.
- [ ] tools/adlc/README.md and partials/README.md updated; no dangling references to a
      removed `gh-auth` standalone check.
- [ ] Docs state the ADO `az repos` primary / REST-documented-fallback decision and the
      v1 `pr_comment`→`feature-unsupported` ADO mapping.

## Technical Notes

Keep the conventions entry parallel in structure to the existing "Delegation pattern
(provider-agnostic)" section so the two read as siblings. Do not edit `templates/` (no
template schema change in this REQ).
