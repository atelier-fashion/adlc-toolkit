---
id: TASK-140
title: "Docs: README, architecture, conventions, tools/adlc README, partials README, CHANGELOG"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-139]
repo: adlc-toolkit
---

## Description

Every document that states the install layout or the machine-state paths says what is now
true (BR-12), including the one-sentence conventions rule on why fences keep the literal
while code reads the variable, and the CHANGELOG names the consumer re-sync (BR-3, AC-11).

## Files to Create/Modify

- `README.md` — install model: `ADLC_HOME`, the view and `~/.agents/skills`, `adlc harness detect`, the new checks
- `.adlc/context/architecture.md` — the `ADLC_HOME` bullet (ADR-1 taxonomy), the counter bullets, the reconciliation bullet
- `.adlc/context/conventions.md` — the home-resolution rule and the fence-literal sentence in "Bash in skills"
- `.adlc/context/project-overview.md` — the machine-state sentence
- `tools/adlc/README.md` — `harness detect` and the new and changed checks
- `partials/README.md` — `adlc-home.sh`
- `CHANGELOG.md` — `[Unreleased]` entries and the re-sync follow-up
- `partials/session-transcript.sh` — (arrived from main with BUG-253) Claude Code's `~/.claude/projects` named once, marked `claude-code`, so the `adlc-home` lint is clean
- `tools/lint-skills/check.py`, `tools/lint-skills/tests/test_adlc_home_lint.py` — the shell pattern also catches trim forms such as `${HOME%/}`

## Acceptance Criteria

- [ ] `grep -n 'cp ~/.claude/skills' README.md` returns nothing, or only lines correct under both homes
- [ ] conventions.md says in one sentence why fences keep the literal while code reads `ADLC_HOME`
- [ ] The CHANGELOG names the per-repo re-sync of vendored partials as the follow-up
- [ ] `bash tools/lint-skills/check.sh` stays clean

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | structural-check | `tools/lint-skills`: builtin-collision, toolkit-path, sentinels over README.md and context docs | no |
| BR-3 | structural-check | `tools/lint-skills`: sentinels over CHANGELOG.md re-sync entry | no |
| AC-12 | structural-check | `tools/lint-skills`: builtin-collision over README.md | no |
| AC-11 | test-case | `tools/adlc/tests/test_adlc_home.py::test_stale_vendored_partial_still_works` | yes |

## Technical Notes

- Do not enumerate the changelog in context docs (LESSON-019).
- Keep REQ-669's dual spellings (`/init` (`/adlc:init` on the plugin install)) on every new instruction line.
