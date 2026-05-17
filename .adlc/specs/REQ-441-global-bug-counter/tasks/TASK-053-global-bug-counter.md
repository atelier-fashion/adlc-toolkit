---
id: TASK-053
title: "Apply global BUG-counter migration to bugfix/SKILL.md + init/SKILL.md"
status: complete
parent: REQ-441
created: 2026-05-17
updated: 2026-05-17
dependencies: []
repo: adlc-toolkit
---

## Description

Apply the captured WIP patch
(`~/adlc-wip-backup-2026-05-17/thread1-global-bug-counter.patch`) verbatim:
migrate `bugfix/SKILL.md` Phase 1 BUG-ID allocation from per-project
`.adlc/.next-bug` to global `~/.claude/.global-next-bug` using the canonical
REQ-counter lock/guard pattern, and update `init/SKILL.md` Step 5
`.gitignore` guidance. No other files.

## Files to Create/Modify

- `bugfix/SKILL.md` — Phase 1: replace the `.adlc/.next-bug` two-liner with
  the `~/.claude/.global-next-bug` allocation block (mkdir-lock, `[ -L ]`
  symlink pre-check, unreadable/empty fail-loud guards, parent
  `[ -n "$BUG_NUM" ]` guard); add the first-run bootstrap (scan
  `$ADLC_REPOS_ROOT`/repo-parent for highest `BUG-xxx`, BSD `grep -oE`/`sed`)
  and the legacy-deprecation note.
- `init/SKILL.md` — Step 5 `.gitignore` block: state both counters are
  global, mark per-project counters deprecated, add `.adlc/.next-req`
  alongside `.adlc/.next-bug`.

## Acceptance Criteria

- [ ] Patch applies cleanly and the resulting `bugfix/SKILL.md` Phase 1
  reads/increments `~/.claude/.global-next-bug` (not `.adlc/.next-bug`).
- [ ] Lock block includes the `[ -L "$LOCK" ]` symlink pre-check
  (LESSON-014) and the parent `[ -n "$BUG_NUM" ]` guard (LESSON-015).
- [ ] First-run bootstrap is BSD-portable (`grep -oE` + `sed`, no `-oP`, no
  GNU-only flags).
- [ ] `init/SKILL.md` `.gitignore` guidance updated (both counters global;
  `.adlc/.next-req` + `.adlc/.next-bug` deprecated/ignored).
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the
  toolkit from the worktree (no `balance`/`canonical-helper`/`sentinel`
  findings introduced; the linter genuinely scans — REQ-435/436).
- [ ] `grep -rn '\.adlc/\.next-bug' --include=SKILL.md .` shows only
  deprecation mentions, none treating it as authoritative
  (`init/SKILL.md:159` `.next-bug 2` dedup example is unrelated and allowed).
- [ ] `bugfix/SKILL.md` unchanged except the Phase-1 allocation block;
  `init/SKILL.md` unchanged except the Step-5 `.gitignore` block.

## Technical Notes

- Apply with `git apply ~/adlc-wip-backup-2026-05-17/thread1-global-bug-counter.patch`
  from the worktree root (verified `git apply --check` clean against
  current `origin/main`).
- Do NOT touch `init/SKILL.md:159` (`".next-bug 2"`) — orthogonal
  duplicate-file cleanup example (REQ-441 ADR-2, Out of Scope).
- Mirrors `spec/SKILL.md` Step 2 REQ-counter block exactly — if the patch
  and that block diverge, the patch is wrong; cross-check.
- No unit tests (markdown skill change); verification is the lint-skills
  linter + grep assertions (ADR-4). Real-world validation already exists:
  BUG-054/BUG-056 were allocated via this exact logic (live symlinked
  skill).
