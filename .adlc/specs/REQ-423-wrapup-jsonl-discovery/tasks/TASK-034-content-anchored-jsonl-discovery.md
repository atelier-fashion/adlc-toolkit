---
id: TASK-034
title: "Replace /wrapup Step 4 JSONL discovery with content-anchored walk-up loop"
status: complete
parent: REQ-423
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Replace the single-path JSONL-discovery heuristic in `wrapup/SKILL.md` Step 4 "Delegated drafting"
sub-step 1 with a content-anchored walk-up loop that scans candidate JSONLs across the repo-root
encoded path AND every parent-dir-encoded path up to (and including) `$HOME`, then picks the JSONL
whose last 200 lines contain the active REQ id (word-boundary match). Falls back to newest-overall
candidate with a stderr warning if no id-match found; falls through to direct drafting if no
candidates exist. Emits exactly one stderr line per `/wrapup` invocation stating which JSONL was
chosen and why.

This is a single-file markdown change. No new files. No tooling. No new shell dependencies.

## Files to Create/Modify

### MODIFY: `wrapup/SKILL.md`

Replace the existing **Delegated drafting → step 1** code fence (currently ~lines 125-131) with
the discovery algorithm from `.adlc/specs/REQ-423-wrapup-jsonl-discovery/architecture.md`. The
replacement block must:

1. Build the candidate list by walking `git rev-parse --show-toplevel` (with worktree-stripping
   intact) upward one directory at a time. Encode each ancestor as `-<path-with-slashes-as-dashes>`.
   Stop after processing `$HOME` — never enumerate above `$HOME`.
2. Run the BR-7 sanitization regex `^-[A-Za-z0-9_./-]+$` against each encoded basename before
   that basename is passed to `ls`. Drop silently on mismatch.
3. Collect `*.jsonl` files in each surviving encoded dir via `ls -t … 2>/dev/null`.
4. **Phase 1** — if a REQ id is available (positional arg or branch-inferred), iterate candidates
   in walk order and pick the first whose `tail -n 200 | grep -qE "\b$REQ_ID\b"` succeeds.
5. **Phase 2** — if no id-match, pick the first candidate overall (newest in the closest dir).
6. Emit exactly ONE stderr line:
   - `/wrapup: session JSONL — matched REQ-XXX in <basename>` (id-match happy path)
   - `/wrapup: session JSONL — REQ-XXX not mentioned in any candidate; using newest <basename> as fallback` (fallback)
   - `/wrapup: session JSONL — no REQ id provided; using newest <basename>` (no REQ id case)
   - `/wrapup: session JSONL — no candidates found; skipping Kimi delegation` (cold path)
7. If no candidates, fall through to the existing **Fallback drafting** path (BR-9 — same
   behavior as today's REQ-414 fallback when `JSONL` is empty).

Use the reference shell in `architecture.md` as the starting point. The grep flag is `grep -qE`
with `\bREQ-XXX\b` (word-boundary, ADR-1) — NOT `grep -F`. Update any inline narrative around the
block to mention "content-anchored" and remove the now-stale description "most recent Claude Code
session JSONL for the active project". The corrected description: "Locate the Claude Code session
JSONL whose recent content mentions the active REQ — walks the encoded-path tree from the repo
root up to `$HOME` and picks the id-matching candidate."

Leave Steps 2-7 (extract-chat → redact → ask-kimi → post-validation → write → emit success)
**untouched**. The substitution variable name `$JSONL` is preserved so downstream steps that
reference it remain correct.

## Acceptance Criteria

- [ ] `git diff --name-only` after the change lists ONLY `wrapup/SKILL.md`, the REQ-423 spec,
      `.adlc/specs/REQ-423-wrapup-jsonl-discovery/architecture.md`, and the task file under
      `.adlc/specs/REQ-423-wrapup-jsonl-discovery/tasks/`. No other SKILL.md modified.
- [ ] `wrapup/SKILL.md` is valid markdown end-to-end. The Step 4 "Delegated drafting" numbered
      list (1-7) renders correctly with no broken code fences.
- [ ] The replaced block contains a `while … do … done` loop that walks from `$ROOT` to `$HOME`
      and explicitly terminates after processing `$HOME` (literal `[ "$DIR" = "$HOME" ] && break`
      or equivalent).
- [ ] The replaced block uses `grep -qE "\b$REQ_ID\b"` (or `grep -qwE` / `grep -qwF`) — NOT
      `grep -qF "$REQ_ID"` alone. Verified by `grep -nE '\\\\b\$REQ_ID\\\\b|-qwF|-qwE' wrapup/SKILL.md`.
- [ ] The replaced block contains the regex literal `^-[A-Za-z0-9_./-]+$` applied to the
      encoded basename before any `ls` call (BR-7).
- [ ] The replaced block emits exactly four distinct stderr message templates corresponding to
      BR-4's happy / fallback / no-id / no-candidates cases (grep for `/wrapup: session JSONL` in
      the edited file returns exactly 4 lines).
- [ ] Walking through the markdown logic with a synthetic candidate containing `..` confirms
      the BR-7 regex rejects it (manual structural check; no test harness required since this is
      a SKILL.md edit, not Python tooling).
- [ ] `find . -type f -name '*.py' -newer wrapup/SKILL.md` returns no Python files (sanity:
      this REQ touches no Python).
- [ ] REQ-413's pytest suite still reports 36/36 passing (`cd tools/kimi && python -m pytest`).
- [ ] The wrapup REQ-423 spec frontmatter `status:` is flipped from `draft` to `approved` as
      part of this task's PR (architect-phase update).

## Technical Notes

- **Bash idioms allowed**: the existing block already uses bash-specific syntax (`$()`,
  `<(process substitution)` elsewhere in the file). Array syntax `CANDIDATES=()` and `+=` are
  fine — `wrapup/SKILL.md`'s code fences are bash, not POSIX sh.
- **mtime ordering across dirs**: `ls -t` is per-directory. The first-id-match-wins logic in
  the algorithm walks repo-root first, so the closest-to-repo candidate matching the REQ id
  wins — which is the correct intent. If a future verify shows a corner case where a more
  recent ancestor-dir match is wanted, swap the fallback selection to a global `xargs ls -t |
  head -1`. Don't pre-optimize.
- **REQ id source**: the existing `/wrapup` skill resolves the REQ id earlier (positional arg
  or branch-inferred). Reuse whatever variable name the surrounding code uses. If the variable
  is empty, the algorithm correctly skips Phase 1 and falls to "no REQ id provided; using
  newest" — see BR-3.
- **Don't touch the trap/cleanup chain**: the `flag=$(tools/kimi/skill-flag.sh create)` /
  `trap` block above this discovery step is REQ-422 / REQ-424 telemetry plumbing. Leave it
  alone — discovery happens before any flag is consumed.
- **OQ-3 resolution (ADR-1)**: the requirement's BR-5 spells out `grep -lF REQ-XXX`. The
  architecture supersedes this to word-boundary. Implementer should NOT add a follow-up REQ to
  "update BR-5 in the spec"; the spec is immutable history once approved, and the architecture
  ADR is the authoritative resolution.
- **Verify scenario coverage**: when running `/reflect` or `/review` on this change, exercise
  all 4 stderr branches mentally against the algorithm (walk through each AC's scenario).
- **No PATH dependencies added**: `tail`, `grep`, `find`, `ls`, `sed`, `printf`, `dirname`,
  `basename` are all already on PATH (POSIX). No `realpath`, no `jq`, no new utilities.
