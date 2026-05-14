---
id: TASK-024
title: "SKILL.md edits: path-traversal `..` rejection, broader credential redaction, Prerequisites blocks, model-agnostic Co-Authored-By"
status: complete
parent: REQ-415
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Four edits across four SKILL.md files:

1. **`analyze/SKILL.md` and `wrapup/SKILL.md`** — in the BR-3 post-validation paragraph
   (file-path citation validation), add the rule: a path that contains a `..` segment is
   rejected even if it matches the character-class regex. Spell it out next to the existing
   regex so the safety property is auditable in one place.

2. **`wrapup/SKILL.md` delegated path step 2** — replace the current single-pattern `sed -E`
   with a multi-pattern alternation covering: `sk-[A-Za-z0-9_-]{20,}`, `AKIA[A-Z0-9]{16}`,
   `ghp_[A-Za-z0-9]{36,}`, `Bearer [A-Za-z0-9._-]{20,}`, `[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+`,
   `MOONSHOT_API_KEY[[:space:]]*[=:][[:space:]]*[^[:space:]]+`. All replace with `[REDACTED]`.

3. **`analyze/SKILL.md`, `optimize/SKILL.md`, `status/SKILL.md`, `wrapup/SKILL.md`** — each
   gets a `## Prerequisites` block consistent with the other skills' style: a one-paragraph
   description of the `.adlc/context/*.md` files the skill reads, plus the standard "if
   missing, stop and tell the user to run `/init` first" failure mode.

4. **`wrapup/SKILL.md`** — replace `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
   with `Co-Authored-By: Claude <noreply@anthropic.com>` (model-agnostic per ADR-7).

## Files to Create/Modify

- `analyze/SKILL.md` — add `..`-rejection rule next to the regex in BR-3 post-validation;
  add `## Prerequisites` block (between the `## Context` and `## Input` sections, matching
  the order used by `/spec` and `/architect`).
- `optimize/SKILL.md` — add `## Prerequisites` block in the same position.
- `status/SKILL.md` — add `## Prerequisites` block in the same position.
- `wrapup/SKILL.md` — add `..`-rejection rule next to the regex in BR-3 post-validation;
  replace the single-pattern `sed` with the multi-pattern alternation from item 2; add
  `## Prerequisites` block in the same position; replace the stale Co-Authored-By line.

## Acceptance Criteria

- [ ] `grep -F '..' analyze/SKILL.md wrapup/SKILL.md` (in the BR-3 paragraph context) shows
      an explicit rejection rule for `..` segments alongside the regex.
- [ ] A walk-through of `/wrapup`'s BR-3 validation rejects `../../etc/passwd` BEFORE any
      `test -f` runs.
- [ ] `wrapup/SKILL.md` contains all six redaction patterns in the multi-pattern `sed`
      (verified by `grep -F 'AKIA' wrapup/SKILL.md && grep -F 'ghp_' wrapup/SKILL.md &&
      grep -F 'Bearer ' wrapup/SKILL.md && grep -F '_(API_KEY|TOKEN)' wrapup/SKILL.md`).
- [ ] `grep -lF '## Prerequisites' analyze/SKILL.md optimize/SKILL.md status/SKILL.md wrapup/SKILL.md`
      lists all four files.
- [ ] Each new `## Prerequisites` block instructs the user to run `/init` if the listed
      `.adlc/context/*` files are missing.
- [ ] `grep -F 'Claude Opus 4.6' wrapup/SKILL.md` returns no matches; `grep -F 'Co-Authored-By: Claude <noreply' wrapup/SKILL.md`
      returns at least one match.
- [ ] All four SKILL.md files remain valid markdown (read end-to-end; no broken numbering,
      no orphan code fences).
- [ ] `~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/ -q` still reports
      29/29 passing (no SKILL.md change should affect the tools tests).

## Technical Notes

- The exact sed pattern (single line, POSIX-compatible). Use this form verbatim:
  ```
  sed -i.bak -E 's/(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|Bearer [A-Za-z0-9._-]{20,}|[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+|MOONSHOT_API_KEY[[:space:]]*[=:][[:space:]]*[^[:space:]]+)/[REDACTED]/g' "$TMPFILE" && rm -f "$TMPFILE.bak"
  ```
  Note `sed -i.bak` (macOS-compatible BSD sed) — keeps the conventions.md POSIX rule.
- For Prerequisites blocks, match the style in `spec/SKILL.md`'s Prerequisites section: one
  paragraph, the explicit failure message, no clever conditionals.
- For analyze's Prerequisites: skill reads `.adlc/context/architecture.md` and
  `.adlc/context/conventions.md`. For optimize, status, wrapup: each reads its own subset —
  spell out which `.adlc/context/*.md` files each one needs by looking at the skill body.
- Do NOT modify any other SKILL.md files. Do NOT touch any tools/ file.
