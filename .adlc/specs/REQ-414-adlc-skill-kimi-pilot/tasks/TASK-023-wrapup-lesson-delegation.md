---
id: TASK-023
title: "wrapup/SKILL.md: delegate Step 4 Lessons Learned drafting to Kimi (with fallback)"
status: draft
parent: REQ-414
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Modify `wrapup/SKILL.md` Step 4 ("Capture Knowledge"), specifically the "Lessons Learned"
sub-section, to add an optional Kimi delegation block gated on `command -v ask-kimi` AND
`ADLC_DISABLE_KIMI != "1"`. When the gate passes, the skill:
(1) finds the most recent Claude Code session JSONL for the current project,
(2) runs `extract-chat <jsonl> -o /tmp/kimi-wrapup-<reqid>.txt`,
(3) calls `ask-kimi --no-warn --paths /tmp/kimi-wrapup-<reqid>.txt --question "Propose a
LESSON-xxx draft for REQ-<reqid> following the template at .adlc/templates/lesson-template.md
(or ~/.claude/skills/templates/lesson-template.md if absent). 400 words max. Include
frontmatter (id, title, component, domain, stack, concerns, tags, req, dates) and the
four template sections."`,
(4) Claude reviews the draft (post-validates citations per BR-3), edits as needed, then
writes the final lesson via the existing Step 4 instructions.

When the gate fails, Claude does what it does today — reads conversation context and writes
the lesson directly.

One stderr log line per invocation stating which path was taken.

## Files to Create/Modify

- `wrapup/SKILL.md` (MODIFY) — locate Step 4's "Lessons Learned" sub-section. Replace the
  existing prose-only instructions (which describe Claude reading conversation context and
  writing the lesson) with a two-branch instruction:
  1. **Gate** (BR-1 exact form):
     ```sh
     if command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then
       # delegated path
     else
       # fallback path
     fi
     ```
  2. **Delegated path** (only when the gate passes):
     - Locate the most recent JSONL for the active project at
       `~/.claude/projects/<project-id>/*.jsonl` (`ls -t … | head -1`).
     - Run `extract-chat "<jsonl>" -o "/tmp/kimi-wrapup-<reqid>.txt"`. If extract-chat fails
       (non-zero exit), emit `/wrapup: extract-chat failed — falling back to Claude direct
       drafting` and fall through to the fallback branch.
     - Run `ask-kimi --no-warn --paths "/tmp/kimi-wrapup-<reqid>.txt"
       --question "..."` with the lesson-drafting question above.
       Capture stdout as the draft.
     - Emit `/wrapup: Lessons Learned drafted via kimi`.
     - **Claude post-validation (BR-3):** for every citation in the draft
       (file paths, `REQ-xxx`, `LESSON-xxx`):
       - File path → `test -f` from the repo root
       - `REQ-xxx` → directory match in `.adlc/specs/REQ-XXX-*`
       - `LESSON-xxx` → file match in `.adlc/knowledge/lessons/LESSON-XXX-*`
       Drop or rewrite any citation that fails. Note the drops in the wrapup log.
     - Claude reads the validated draft, edits for accuracy/voice/scope (the draft is a
       *proposal*, not a deliverable), then writes the final lesson file using the same
       file-naming + counter rules already in Step 4 (`.adlc/.next-lesson`).
     - Delete the `/tmp/kimi-wrapup-<reqid>.txt` temp file after the lesson is written.
  3. **Fallback path** (gate fails, or any delegation step errored):
     - Emit `/wrapup: ask-kimi unavailable — Claude drafting lesson directly` (or
       `... disabled via ADLC_DISABLE_KIMI` when that's the cause).
     - Continue with the existing Step 4 lesson-drafting instructions — current behavior,
       unchanged.

## Acceptance Criteria

- [ ] `wrapup/SKILL.md` contains the gated block in Step 4's "Lessons Learned" sub-section
      (verified by `grep -n 'ADLC_DISABLE_KIMI' wrapup/SKILL.md` returning at least one line
      inside the "Capture Knowledge" / "Lessons Learned" range).
- [ ] The skill explicitly documents the post-validation rule (BR-3) listing the three
      citation classes and their existence checks.
- [ ] Both stderr log lines are spelled out verbatim in the markdown so a future reader can
      grep transcripts.
- [ ] The fallback path leaves the existing lesson-writing logic intact (Step 4's other
      sub-sections — Architectural Decisions, Assumptions, Convention Updates — are
      NOT modified).
- [ ] `git diff --name-only` after this task lists only `wrapup/SKILL.md` and the TASK-023
      file under tasks/.
- [ ] The skill is still valid markdown end-to-end (read the full file to verify).

## Technical Notes

- The "active project id" for the JSONL lookup: the current cwd path encoded into a Claude
  Code project directory name (e.g., `-Users-brettluelling-Documents-GitHub-adlc-toolkit`).
  The skill instructions should call out this lookup pattern explicitly so the markdown is
  self-contained.
- The post-validation step is the load-bearing safety net (LESSON-007). It is not optional —
  the skill MUST do it before writing the final lesson.
- This task does NOT touch the Step 4 counter logic (`.adlc/.next-lesson`) — the existing
  atomic counter pattern still applies; only the drafting upstream of the write changes.
- Do NOT modify any other skill (BR-7).
