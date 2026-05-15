---
id: TASK-033
title: "Introduce partials/ infrastructure and DRY ethos macro across 15 skills"
status: draft
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-416 BR-1 and BR-2 (ADR-1). Introduce a `partials/` directory as
single-source for shared shell snippets, populate it with `ethos-include.sh`,
and refactor all 15 SKILL.md files to source it instead of duplicating the
6-line bash macro. This task also establishes the partials/ pattern that
TASK-034 (Kimi gate DRY) and TASK-035 (proceed split) reuse.

## Files to Create/Modify

- `partials/ethos-include.sh` — NEW. POSIX shell, no bashisms. Emits the
  fallback chain: `cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`.
  Shebang `#!/bin/sh`, `set -eu` only if the cat fallthrough doesn't trip it
  (it doesn't — the `||` chain means each cat is allowed to fail).
- `partials/README.md` — NEW. Two paragraphs: what `partials/` is for, the
  invocation pattern (`!`sh .adlc/partials/<name>.sh 2>/dev/null || sh ~/.claude/skills/partials/<name>.sh``).
- All 15 SKILL.md files — replace the `## Ethos` section body. Files:
  `analyze`, `architect`, `bugfix`, `canary`, `init`, `optimize`, `proceed`,
  `reflect`, `review`, `spec`, `sprint`, `status`, `template-drift`,
  `validate`, `wrapup` (each `<skill>/SKILL.md`).
  - Old body (one line, the macro):
    ```
    !`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`
    ```
  - New body (one line, the partial source):
    ```
    !`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`
    ```
- `init/SKILL.md` — extend the bootstrap to copy `partials/` into the
  consumer project's `.adlc/partials/` (mirrors the existing `templates/`
  copy logic). The fallback at each call site means consumer projects that
  haven't re-run `/init` after the toolkit update still work via the
  `~/.claude/skills/partials/` path.
- `.adlc/context/architecture.md` — under "Top-level layout", add
  `├── partials/` between `templates/` and `.adlc/`. Add a one-paragraph
  "Partials" subsection explaining the source-with-fallback pattern.
- `.adlc/context/conventions.md` — under "Ethos injection pattern" and
  "Context loading pattern", update the example to use the partial.

## Acceptance Criteria

- [ ] `partials/ethos-include.sh` exists, is executable, and emits the
      ethos via the documented fallback chain when run from any directory.
- [ ] All 15 SKILL.md files reference `partials/ethos-include.sh`. Verified
      by `grep -L "partials/ethos-include.sh" */SKILL.md` returning empty.
- [ ] No SKILL.md still contains the old inline `cat .adlc/ETHOS.md` macro.
      Verified by `grep -l "cat .adlc/ETHOS.md" */SKILL.md` returning empty.
- [ ] BR-2 byte-identical check: capture the rendered Ethos block from any
      one skill (e.g., by simulating Claude Code's `!`...`` evaluation:
      `sh partials/ethos-include.sh`) before and after the refactor; outputs
      MUST match byte-for-byte (the underlying ETHOS.md is unchanged).
- [ ] `/init` copies `partials/` into a fresh consumer project sandbox.
- [ ] `.adlc/context/architecture.md` and `conventions.md` document the new
      directory and pattern.
- [ ] All REQ-413 pytest tests still pass (BR-8).
- [ ] No skill's behavior changes when invoked end-to-end (sandbox dogfood
      check — invoke `/spec` or `/status` in a test repo, confirm normal
      output).

## Technical Notes

- The shell partial uses `sh`, not `bash`, to honor the POSIX-only convention
  (.adlc/context/conventions.md line 56). Skills invoke it via
  `!`sh .adlc/partials/ethos-include.sh ...`` rather than relying on
  executable bit + PATH.
- The double-fallback at each call site (`sh .adlc/... || sh ~/.claude/skills/...`)
  preserves consumer-project precedence even when the partial hasn't been
  copied yet. This matches the existing ETHOS.md fallback semantics.
- Do NOT introduce a `partials/lib.sh` aggregator — the per-snippet file
  pattern keeps each include trivially auditable. Aggregation is a YAGNI
  shape we can adopt later if there are >5 partials.
- The 15-skill find-and-replace can be scripted with `perl -i -pe` or done
  by hand. Script preferred for traceability — commit the script under
  `.adlc/specs/REQ-416-toolkit-refactor/scratch/refactor-ethos.sh` if
  scripted, then delete on `/wrapup`.
- This task's completion unblocks TASK-034 and TASK-035 (both depend on the
  `partials/` directory existing).
