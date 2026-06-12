---
id: TASK-004
title: "root install.sh: idempotent, repair-capable, dry-run, atomic mutations"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-003]
repo: adlc-toolkit
---

## Description

Create the root-level `install.sh` — one idempotent command that performs the
full setup (BR-1, BR-2, BR-3, BR-6, BR-7, BR-9, BR-11) and ends with an embedded
`adlc doctor` run (System Model "install summary" event).

## Files to Create/Modify

- `install.sh` (repo root) —
  - `#!/usr/bin/env bash`, `set -euo pipefail`.
  - Arg parse: `--repair`, `--dry-run` → `MODE` (fresh/repair/dry-run).
  - `REPO_ROOT` derivation: `git -C "$(dirname "$0")" rev-parse --show-toplevel`
    with script-relative fallback (BR-3, no hardcoded HOME beyond `$HOME`).
  - `_atomic_write` helper: backup → temp-write → `mv` (BR-2). Fail-loud on
    malformed existing content (e.g. unbalanced marker block) — actionable
    message, never traceback or silent overwrite.
  - Mutators (each idempotent + dry-run aware, content-compared):
    - symlink `~/.claude/skills` → `$REPO_ROOT`, `~/.claude/agents` →
      `$REPO_ROOT/agents` (relink only if target differs).
    - generate the `adlc` shim in `~/bin/adlc` (exec system python3 on
      `$REPO_ROOT/tools/adlc/adlc.py "$@"`), same shim mechanism as kimi (BR-11,
      BR-3 — no hardcoded path beyond derived `$REPO_ROOT`/`$HOME`).
    - PATH wiring: marker-guarded append to the login shell rc
      (`# >>> adlc-toolkit (REQ-519) >>>` … `<<<`), idempotent.
    - config scaffold: create `~/.claude/adlc/config.yml` if absent with
      delegation `enabled: false` (BR-9) — never overwrite an existing config.
  - Optional delegation step (BR-9): explicit opt-in only (e.g. `--with-delegation`
    or interactive prompt that defaults to NO); when accepted, defer to
    `tools/kimi/install.sh` and print the REQ-515 data-governance notice. Never
    enabled by default.
  - macOS/Linux awareness (BR-6): launchctl steps only on Darwin; print
    skipped-with-notice on Linux.
  - Final step: run `adlc doctor` and embed its report in the install summary.
  - Summary: actions taken vs skipped-already-done (BR-1).

## Acceptance Criteria

- [ ] Second consecutive run reports zero actions taken (BR-1, AC-3).
- [ ] `--dry-run` prints the action plan and changes nothing (AC-7) — verified
      by before/after `ls -la ~/.claude` + grep of rc file.
- [ ] `--repair` after moving the clone regenerates symlinks/shims with the new
      path; no stale old-location absolute path remains (AC-4, grep-verified).
- [ ] No hardcoded user-specific absolute paths beyond `$HOME` and derived
      `$REPO_ROOT` (BR-3) — grep the generated shim/config.
- [ ] Delegation is never enabled by default; opt-in prints the governance
      notice (BR-9).
- [ ] Every `~/.zshrc`/settings/config mutation is backup+temp+rename atomic and
      fail-loud on malformed content (BR-2).
- [ ] BSD/zsh-safe; runs clean under `zsh -c` and `bash -c` on macOS and `bash`
      on Linux (BR-7).

## Technical Notes

- Mirror `tools/kimi/install.sh` for marker-guarded PATH append, atomic file
  mutation, and shim generation — reuse the proven pattern, don't reinvent
  (LESSON-006, LESSON-023).
- Idempotency gates on file/symlink CONTENT, not process state (BR-1): compare
  current symlink target / current marker block before mutating.
- Dry-run threads a single `MODE` check at each write boundary so the plan is
  the same code path as the action (ADR-7) — print `would …` and return.
- Do NOT enable `set -e` around commands whose non-zero is expected (e.g.
  `grep -q` marker probe) — guard with `if`/`|| true` to avoid spurious abort.
- The embedded doctor run uses the freshly-installed `adlc` (call
  `python3 "$REPO_ROOT/tools/adlc/adlc.py" doctor` directly to avoid PATH-not-yet
  -sourced chicken-and-egg in the same shell).
