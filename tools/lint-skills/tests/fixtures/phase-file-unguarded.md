# Phase 6-8: Ship (fixture)

Shaped like a `/proceed` companion phase file — the third file family
`unguarded-source` walks (REQ-610 ADR-3). These files are not `SKILL.md` and no
lint check walked them before REQ-610, yet they carry executable fences: the
real `proceed/phases-6-8-ship.md` sources the forge adapter exactly as a skill
does, and a fatal `.` there kills the ship phase on any machine with no
vendored copy.

## Phase 6 — Open the PR

```sh
. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh
adlc_forge_pr_create "$title" "$body"
```

Expect one `unguarded-source` finding on the source line — and, when this file
is staged alone under `proceed/`, a VACUOUS SCAN exit: it must never be counted
toward the `scanned N SKILL.md file(s)` figure the REQ-595 guard reads.
