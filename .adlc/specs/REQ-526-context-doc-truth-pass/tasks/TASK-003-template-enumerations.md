---
id: TASK-003
title: "Complete template enumerations in README.md and architecture.md"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

README.md and architecture.md each enumerate five templates, omitting
`templates/taxonomy-template.md` (BR-5). Either add the missing template, or — sturdier,
per BR-5 and LESSON-019 — reference the `templates/` directory as authoritative instead of
maintaining a hand-kept list that rots. Choose per readability: README's bulleted catalog
reads better with the entry added; architecture.md's prose list can point at `templates/`.

Depends on TASK-001 (both edit architecture.md) to avoid a same-file edit collision.

## Files to Create/Modify

- `README.md:31–35` — add `taxonomy-template.md — Taxonomy/tagging template` to the Templates list (or reference `templates/`)
- `.adlc/context/architecture.md:46–52` — add `taxonomy-template.md` to the template-anatomy list, or replace the enumeration with "see `templates/` (authoritative)"

## Acceptance Criteria

- [ ] README template list matches `ls templates/*.md` (every `.md` template represented, or list replaced by a `templates/` pointer)
- [ ] architecture.md template list matches `ls templates/*.md` (same)
- [ ] No template present in `templates/` is missing from a surface that claims to enumerate them

## Technical Notes

`ls templates/*.md` currently yields: assumption, bug, lesson, requirement, task, taxonomy
(plus the non-.md `claude-settings-template.json` and `config-template.yml`, which the
enumerations intentionally don't list as "templates" in the artifact sense). Match the
existing description style. Prefer the `templates/` pointer in architecture.md to reduce
future enumeration rot.
