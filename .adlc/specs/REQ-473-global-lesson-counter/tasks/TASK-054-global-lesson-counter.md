---
id: TASK-054
title: "Migrate LESSON-ID allocation to a global cross-repo counter"
status: complete
parent: REQ-473
created: 2026-05-29
updated: 2026-05-29
dependencies: []
repo: adlc-toolkit
---

## Description

Migrate LESSON-ID allocation from the per-project `.adlc/.next-lesson` to the
global `~/.claude/.global-next-lesson`, mirroring the canonical REQ-counter
block (`spec/SKILL.md` Step 2) and its BUG sibling (`bugfix/SKILL.md` Phase 1,
REQ-441). LESSON ids are minted in TWO skills (`/wrapup` and `/bugfix`) which
must move in lockstep and share one global lock. Also update `init/SKILL.md`
`.gitignore` guidance + `.adlc/context/architecture.md`, and seed the two
machine-local counter files.

## Files to Create/Modify

- `wrapup/SKILL.md` — Step 4 (Fallback drafting, ~273–294): replace the
  `.adlc/.next-lesson` allocation block with the `~/.claude/.global-next-lesson`
  block (mkdir-lock at `~/.claude/.global-next-lesson.lock.d`, `[ -L ]` symlink
  pre-check, unreadable/empty fail-loud guards, parent `[ -n "$LESSON_NUM" ]`
  guard); replace the per-project bootstrap with the cross-repo scan
  (`$ADLC_REPOS_ROOT`/repo-parent, `-path '*/.adlc/knowledge/lessons/LESSON-*'
  -type f`, BSD `grep -oE`/`sed`) + a legacy-deprecation note. Update the
  Step-4 pointer at ~260 to name the global counter.
- `bugfix/SKILL.md` — lesson-capture step (~204–225): the SAME global block,
  same global lock path (shared with `/wrapup` for mutual exclusion), same
  bootstrap + deprecation note.
- `init/SKILL.md` — Step 5 `.gitignore` block: add `.adlc/.next-lesson` to the
  deprecated/ignored list; note LESSON ids are now global (consistent with
  `.next-bug`/`.next-req`).
- `.adlc/context/architecture.md` — "Key cross-cutting dependencies": move
  LESSON into the global-counter group (with REQ + BUG); leave
  `.adlc/.next-assume` as the sole per-project counter; update the shared-lock
  note to `~/.claude/.global-next-lesson.lock.d`.
- Machine-local seeds (NOT committed — live in `~/.claude/`):
  `echo 313 > ~/.claude/.global-next-lesson` and
  `echo 67 > ~/.claude/.global-next-bug` (corrects the stale 65).

## Acceptance Criteria

- [ ] Both `wrapup/SKILL.md` and `bugfix/SKILL.md` read/increment
  `~/.claude/.global-next-lesson` (not `.adlc/.next-lesson`).
- [ ] Both blocks include the `[ -L "$LOCK" ]` symlink pre-check (LESSON-014),
  the unreadable/empty fail-loud guards, and the parent `[ -n "$LESSON_NUM" ]`
  guard (LESSON-015) — with the four canonical inline rationale comments ported
  verbatim (LESSON-023, BR-8).
- [ ] Both blocks use the shared global lock `~/.claude/.global-next-lesson.lock.d`
  (BR-5).
- [ ] First-run bootstrap is BSD-portable (`grep -oE` + `sed`, no `-oP`) and
  uses `-path '*/.adlc/knowledge/lessons/LESSON-*' -type f`.
- [ ] Legacy-deprecation note for `.adlc/.next-lesson` present in both skills.
- [ ] `init/SKILL.md` `.gitignore` guidance updated.
- [ ] `.adlc/context/architecture.md` updated (LESSON global; ASSUME remains
  per-project; shared-lock note → global path).
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the toolkit
  (no `balance`/`canonical-helper`/`skill-md-corruption` findings introduced).
- [ ] `grep -rn '\.adlc/\.next-lesson' --include=SKILL.md .` shows only
  deprecation mentions, none authoritative.
- [ ] `grep -rn '\.adlc/\.next-assume' --include=SKILL.md .` unchanged from
  `main` (ASSUME stays per-project — regression guard, BR-9).
- [ ] `~/.claude/.global-next-lesson` == `313`; `~/.claude/.global-next-bug`
  == `67`.

## Technical Notes

- **Mirror, don't invent.** Diff the new LESSON block line-by-line against the
  canonical `~/.claude/.global-next-bug` block in `bugfix/SKILL.md` Phase 1
  (lines 36–60) — they must be identical except the deliberate
  `BUG`→`LESSON` / `.adlc/bugs/BUG-*`→`.adlc/knowledge/lessons/LESSON-*`
  substitutions (both keep `-type f`). If they diverge otherwise, the new block
  is wrong (LESSON-023, BR-8).
- The current per-project block uses `cat "$COUNTER" 2>/dev/null || echo "1"`
  (no fail-loud guard) and computes `REPO_ROOT` first; the global block DROPS
  `REPO_ROOT` from the main allocation path (the counter is in `~/.claude`, not
  the repo) and ADDS the fail-loud unreadable/empty guards — this is an
  intentional upgrade to match the canonical block, not a divergence.
- Do NOT touch `.adlc/.next-assume` allocation or any `.next-lesson 2`-style
  dedup-example string (orthogonal; REQ-473 ADR-3, Out of Scope).
- No unit tests (markdown skill change); verification is the lint-skills linter
  + grep assertions (ADR-6). Live dogfood: this REQ's own `/wrapup` will mint
  LESSON-313 from the new global counter — the end-to-end proof.
- Worktree note: work directly in the adlc-toolkit checkout on a feature branch
  (the `~/.claude/skills` symlink makes edits live immediately, which is the
  intended toolkit model; git worktrees are unreliable in sandbox — LESSON-233).
