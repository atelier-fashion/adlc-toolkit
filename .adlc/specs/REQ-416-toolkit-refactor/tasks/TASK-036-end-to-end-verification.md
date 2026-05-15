---
id: TASK-036
title: "End-to-end verification: pytest suite + sample /proceed dry-run"
status: draft
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-031, TASK-032, TASK-033, TASK-034, TASK-035]
---

## Description

Verification gate for REQ-416. Validates BR-8 (REQ-413 pytest suite still
passes) and the requirement's "sample `/proceed` run on a synthetic test REQ
completes end-to-end" acceptance criterion. Catches integration regressions
that per-task acceptance checks would miss (e.g., partials/ source path works
under both consumer-project and toolkit-fallback layouts; locked counters
don't deadlock when a real pipeline runs).

## Files to Create/Modify

- `.adlc/specs/REQ-416-toolkit-refactor/verification.md` — NEW. Captures the
  test plan, the actual commands run, and pass/fail outcomes. Becomes part
  of the REQ artifact set for `/wrapup` to reference.

(No production code changes. This task is pure verification — failures
loop back to the relevant TASK-031..035 for fix.)

## Acceptance Criteria

- [ ] `cd tools/kimi && python3 -m pytest tests/ -v` passes all REQ-413
      tests (currently 29). Verifies BR-8 across all five refactor items.
- [ ] Symlink-swap test for each locked counter passes:
      ```bash
      # For each of: ~/.claude/.global-next-req.lock.d,
      #              <test-repo>/.adlc/.next-lesson.lock.d,
      #              <test-repo>/.adlc/.next-assume.lock.d
      ln -sf /tmp/somewhere "$LOCK"
      <invoke the relevant skill section>  # MUST exit non-zero with TOCTOU error
      [ ! -e /tmp/somewhere ]              # MUST be unchanged
      rm "$LOCK"
      ```
- [ ] Concurrent-counter test passes: launch 5 background `bash`
      subprocesses that each acquire the `.next-lesson` lock, increment,
      release. Final counter value is exactly initial+5 (no lost updates).
- [ ] Ethos rendering check: `sh partials/ethos-include.sh` from a fresh
      sandbox (no `.adlc/ETHOS.md`, ETHOS.md only at `~/.claude/skills/`)
      emits the canonical ethos. From a sandbox WITH `.adlc/ETHOS.md`,
      it emits the consumer-project copy.
- [ ] Kimi gate function check: source `partials/kimi-gate.sh` and call
      `adlc_kimi_gate_check`; verify returns 0 with `ask-kimi` on PATH and
      no `ADLC_DISABLE_KIMI`, returns 1 with `ADLC_DISABLE_KIMI=1`, returns
      2 with `ask-kimi` removed from PATH.
- [ ] `/proceed` dry-run on a synthetic REQ in a sandbox repo
      (atelier-fashion or a temp `/init`-bootstrapped repo) reaches at
      least Phase 4 without errors. The sandbox can stop short of actual
      implementation — what's tested is that the new SKILL.md + companions
      load and dispatch correctly.
- [ ] `verification.md` documents commands run, outputs, and pass/fail.
- [ ] `proceed/SKILL.md` line count is ≤450 (TASK-035 amended target,
      double-checked here).
- [ ] No accidental regressions: `git diff main -- '*/SKILL.md'` shows
      only the documented refactor changes (ethos macro line, kimi gate
      block, proceed extractions) — no whitespace-only churn or
      unintended content drift.

## Technical Notes

- This task runs sequentially after TASK-031..035 are all `complete`.
  In a `/proceed` invocation, this is the verify-phase gate.
- The synthetic-REQ dry-run does NOT need to be a real pipeline that ships
  code. It's a smoke test that the orchestration spine still works after
  the split. A REQ with a single trivial task (e.g., "add a comment to
  README.md") suffices.
- If the Kimi gate function tests fail because the developer's environment
  doesn't have `ask-kimi` installed, that's a MISSING DEV-ENV setup issue
  rather than a refactor regression — `tools/kimi/install.sh` should run
  first. Document this as a prereq in `verification.md`.
- Failures here loop back. Do NOT mark this task complete until every
  acceptance criterion checks green. If a check is genuinely impossible
  to run (e.g., concurrent counter test requires multi-process setup the
  CI can't provide), mark it explicitly N/A in `verification.md` with a
  rationale rather than silently skipping.
