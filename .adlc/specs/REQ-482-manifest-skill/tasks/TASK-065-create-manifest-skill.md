---
id: TASK-065
title: "Create the /manifest skill (remote-derived in-flight view + advisory overlap)"
status: draft
parent: REQ-482
created: 2026-06-04
updated: 2026-06-04
dependencies: []
---

## Description

Create `manifest/SKILL.md` — a standalone, read-only skill that derives a cross-session view of in-flight ADLC work from the remote (open PRs + pushed `feat/REQ-*` branches), enriches each entry with `component`/`domain`, computes a coarse overlap report, and renders an advisory table. This is the foundational artifact; the wiring tasks (066–068) depend on it.

## Files to Create/Modify

- `manifest/SKILL.md` — the new skill (create)

## Acceptance Criteria

- [ ] Skill file follows the canonical skeleton: frontmatter (`name: manifest`, `description`, `argument-hint`), `# /manifest — …` title, `## Ethos` injection macro (`!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh``), `## Context`, `## Input` (optional REQ filter / `self`), `## Prerequisites` (git repo + reachable `origin`; fail clearly otherwise), `## Instructions`, `## Quality Checklist`.
- [ ] Enumerates in-flight REQs from BOTH `gh pr list --state open --json number,headRefName,author,isDraft,createdAt,url --limit 200` (incl. drafts) AND remote `feat/REQ-*` branches (`git branch -r --list 'origin/feat/REQ-*'`), deduped by REQ id (PR entry wins; branch-only added when no PR). (BR-3, BR-4)
- [ ] Maps branch → REQ via `feat/REQ-<digits>-<slug>`; non-matching branches are silently ignored. (BR-4)
- [ ] Every remote-derived identifier is sanitized before shell use: REQ ids validated against `^REQ-[0-9]{3,6}$`; substituted branch/path values single-quoted; any path segment equal to `..` rejected before `git show`. (BR-5, LESSON-008)
- [ ] Component/domain enrichment tries local frontmatter first, then `git show origin/<branch>:.adlc/specs/<REQ>-*/requirement.md`, then `unknown`; an entry is never dropped on enrichment failure. (BR-11, BR-12)
- [ ] Coarse overlap report flags pairs sharing `component` OR `domain` (labels which), presented as ADVISORY only with an explicit "no action enforced" note. (BR-8)
- [ ] Includes the current session's own REQ when one is in context, marked as self. (BR-13)
- [ ] Graceful degradation: with `gh` unavailable/unauthenticated, enumerate from branches only, annotate that PR data is missing, exit 0 — never hard-fail. (BR-6)
- [ ] Strictly read-only: no branch/PR/file/state mutation; `git status` clean after a run. (BR-2) No stored manifest file is created. (BR-1)
- [ ] Network cost is O(1) in the number of in-flight REQs: reuse caller's fetch in pre-flight contexts / one own `git fetch` standalone, one batched `gh pr list`, local `git show` enrichment — no per-branch API calls. (BR-14)
- [ ] Output table columns: `REQ | author | branch/PR | state | component/domain | opened-at` (+ self marker). (AC from requirement)
- [ ] `python3 tools/lint-skills/check.py` passes clean (no new findings).
- [ ] **Dogfood**: running `/manifest` in this repo lists `feat/REQ-482-manifest-skill` as in-flight (self) and exits 0.

## Technical Notes

- Mirror `status/SKILL.md` for structure and table style; mirror `proceed/SKILL.md` / `template-drift/SKILL.md` for the identifier-sanitization + path-traversal-rejection patterns.
- **No Kimi** (ADR-3): do NOT reference `ADLC_DISABLE_KIMI`, `kimi-gate.sh`, or telemetry — this skill does git/gh I/O, not bulk reads, and referencing the gate would trip the lint canonical-helper check.
- POSIX/BSD bash only (conventions "Bash in skills"): `grep -oE` not `-oP`; no `local` inside ` ```sh `/` ```shell ` fences (use ` ```bash ` if `local` is truly needed); keep any shell function defined-and-invoked **within the same fenced block** (cross-fence-fn lint check — LESSON-020).
- Keep `$(`/`)` and `$((`/`))` balanced within each fence (lint shell-balance check).
- `state` values: `draft` (PR isDraft) | `ready` (open non-draft PR) | `no-pr` (branch only).
