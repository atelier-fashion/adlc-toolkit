---
id: TASK-034
title: "DRY Kimi delegation gate using partials/"
status: complete
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-033]
---

## Description

Resolve REQ-416 BR-3 (ADR-2). The Kimi delegation gate condition currently
appears verbatim in 4 skills (`analyze`, `proceed`, `spec`, `wrapup`).
Extract the predicate into `partials/kimi-gate.sh` as a sourceable shell
function and document the usage protocol in `partials/kimi-gate.md`. Refactor
the 4 skills to source the function and case on its return code.

## Files to Create/Modify

- `partials/kimi-gate.sh` — NEW. Defines `adlc_kimi_gate_check()` returning
  0 (delegated), 1 (disabled via `ADLC_DISABLE_KIMI=1`), or 2 (unavailable —
  `ask-kimi` not on PATH). POSIX-only.
- `partials/kimi-gate.md` — NEW. Usage protocol: when to call the function,
  what each return code means, the canonical stderr emit pattern for each
  branch (parameterized by `<skill-name>` and `<purpose>`), and the BR-4
  one-line-per-invocation rule.
- `analyze/SKILL.md` — replace the two inline gate blocks (Step 1.5 line ~40
  and Step 1.6 line ~74) with `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh; adlc_kimi_gate_check; gate=$?` followed by a `case $gate in` switch. Per-skill stderr messages and fallback bodies stay inline.
- `proceed/SKILL.md` — same refactor at Phase 5 line ~338.
- `spec/SKILL.md` — same refactor at Step ~108.
- `wrapup/SKILL.md` — same refactor at Step ~106.
- `.adlc/context/conventions.md` — add a "Kimi delegation pattern" subsection
  pointing at `partials/kimi-gate.md`.

## Acceptance Criteria

- [ ] `partials/kimi-gate.sh` defines `adlc_kimi_gate_check` with the
      documented return-code contract.
- [ ] `partials/kimi-gate.md` exists and documents the protocol.
- [ ] All 4 delegating skills source `partials/kimi-gate.sh` and case on
      its return; no skill still contains the literal predicate
      `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`.
      Verified by `grep -l 'command -v ask-kimi.*ADLC_DISABLE_KIMI' */SKILL.md`
      returning empty.
- [ ] Every skill containing `ADLC_DISABLE_KIMI` ALSO contains
      `partials/kimi-gate.sh` (the source line). Verified by:
      ```bash
      for f in $(grep -l ADLC_DISABLE_KIMI */SKILL.md); do
        grep -q "partials/kimi-gate.sh" "$f" || echo "MISSING: $f"
      done
      ```
      MUST print nothing.
- [ ] Behavior unchanged: each delegated path still produces the same
      stderr message it did pre-refactor (BR-4 — one line per invocation).
      Verified by dogfood-running each of analyze/proceed/spec/wrapup and
      diffing stderr against a pre-refactor capture.
- [ ] Behavior unchanged in disabled path: setting `ADLC_DISABLE_KIMI=1` and
      invoking each delegating skill produces the documented "disabled via
      ADLC_DISABLE_KIMI" stderr line and the fallback path runs.
- [ ] All REQ-413 pytest tests still pass (BR-8).

## Technical Notes

- Source-with-fallback at the call site:
  ```bash
  . .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
  ```
  `.` is POSIX-portable (vs `source`, which is bash-only).
- The function returns an exit code (0/1/2). Each call site reads `$?` IMMEDIATELY
  into a local variable (`gate=$?`) before any other command, because `$?` is
  clobbered by every subsequent command.
- The case branches per skill differ in:
  - Stderr message (e.g., `/analyze: ask-kimi failed — Claude reading shape files directly`)
  - Fallback action (read files directly, draft lesson directly, dispatch agents without pre-pass, etc.)
- Do NOT factor the case branches themselves — they're skill-specific. Only the
  predicate is shared.
- After this task, adding a NEW Kimi-delegating skill MUST source
  `partials/kimi-gate.sh` (BR-3). The greppable verification check above is
  the enforcement mechanism — consider adding it to a future CI lint step
  (out of scope for REQ-416).
