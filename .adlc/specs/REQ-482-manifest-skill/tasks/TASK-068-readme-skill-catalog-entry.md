---
id: TASK-068
title: "Register /manifest in the README skill catalog (+ /status see-also)"
status: draft
parent: REQ-482
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-065]
---

## Description

Make `/manifest` discoverable: add it to the README skill catalog, and add a brief "see also" pointer in `/status` so users know `/manifest` is the remote-aware, cross-session counterpart.

## Files to Create/Modify

- `README.md` — add a `/manifest` row to the skill catalog table (after `/status`)
- `status/SKILL.md` — add a one-line "see also `/manifest` for cross-session, remote-derived in-flight work" pointer (non-behavioral)

## Acceptance Criteria

- [ ] README skill catalog includes a `/manifest` entry, formatted like the surrounding rows, placed after `/status`.
- [ ] The entry's description is consistent with the skill's frontmatter `description`.
- [ ] `status/SKILL.md` notes that `/manifest` is the remote-derived, cross-session view (one line; no behavior change to `/status`).
- [ ] `python3 tools/lint-skills/check.py` passes clean.

## Technical Notes

- README row format (existing): `| `/status` | Show current state of all ADLC work |`.
- Keep the `/status` ↔ `/manifest` distinction crisp: `/status` = local-tree view of this checkout's work; `/manifest` = remote-derived view of all in-flight work across sessions.
- Do NOT merge the two skills or change `/status` behavior (Out of Scope).
