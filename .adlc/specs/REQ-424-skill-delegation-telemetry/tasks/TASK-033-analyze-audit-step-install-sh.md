---
id: TASK-033
title: "/analyze Step 1.8 audit + install.sh log permissions"
status: complete
parent: REQ-424
created: 2026-05-14
updated: 2026-05-14
dependencies: [TASK-031, TASK-032]
---

## Description

Two edits:
1. `/analyze` gains a new Step 1.8 (between the existing Step 1.6 audit pre-pass and
   Step 2 agent dispatch) that runs `check-delegation.sh --window 7d` and includes any
   non-zero `ghost_skip` counts as findings under a new `delegation-fidelity` dimension.
2. `install.sh` ensures `~/Library/Logs/` exists and `chmod 600` the
   `adlc-skill-telemetry.log` file if it's already present (matches REQ-422 precedent).

## Files to Create/Modify

- `analyze/SKILL.md` — insert `### Step 1.8: Delegation-fidelity audit` between Step
  1.6 and Step 2. Content:
  - Invoke `tools/kimi/check-delegation.sh --window 7d` if the script exists; capture
    TSV stdout. If the script doesn't exist (older install), skip silently.
  - Parse the TSV: any row with `ghost_skip` count > 0 is a finding. Surface as a
    `delegation-fidelity` dimension entry in the audit report, naming the skill name
    and the count (e.g. "spec Step-1.6: 3 ghost-skips in last 7 days").
  - The audit report's existing dimension list (code-quality, convention, security,
    test) gains a fifth dimension: `delegation-fidelity`.
  - If `check-delegation.sh` reports zero ghost-skips across the board, emit
    `/analyze: delegation-fidelity clean (0 ghost-skips in 7d window)` to the report
    rather than omitting the dimension.

- `tools/kimi/install.sh` — add a small section near the existing `~/Library/Logs/`
  mkdir (added in REQ-422):
  ```sh
  TELEMETRY_LOG="$HOME/Library/Logs/adlc-skill-telemetry.log"
  if [ -f "$TELEMETRY_LOG" ]; then
      chmod 600 "$TELEMETRY_LOG"
  fi
  ```
  Idempotent — no-op if the log doesn't exist yet (emit-telemetry.sh creates it with
  the right mode via umask 077 on first write).

## Acceptance Criteria

- [ ] `grep -F '### Step 1.8' analyze/SKILL.md` returns one match between Step 1.6 and
      Step 2 line numbers.
- [ ] `grep -F 'check-delegation.sh' analyze/SKILL.md` returns one match (the Step 1.8
      invocation).
- [ ] `grep -F 'delegation-fidelity' analyze/SKILL.md` returns at least one match.
- [ ] `grep -F 'adlc-skill-telemetry.log' tools/kimi/install.sh` returns the new chmod
      block.
- [ ] `bash -n tools/kimi/install.sh` passes.
- [ ] `analyze/SKILL.md` remains valid markdown (numbered steps intact end-to-end).
- [ ] Synthetic test: with a fixture log containing a `ghost-skip` entry,
      `check-delegation.sh` output parsed against the Step 1.8 logic produces a
      finding naming the skill + count. (Exercise via the existing test_telemetry.py
      from TASK-031 — add one case asserting the TSV row shape Step 1.8 expects.)
- [ ] On a non-macOS host (no `launchctl` etc.), install.sh's new section still runs
      cleanly — `~/Library/Logs/` is macOS-specific, so the `chmod` block is gated
      inside the existing macOS-only launchctl block. If outside that block, gate it.
- [ ] REQ-413's pytest suite still 36/36; TASK-031's new tests still pass.
- [ ] `git diff --name-only` after this task lists ONLY `analyze/SKILL.md`,
      `tools/kimi/install.sh`, and the TASK-033 file.

## Technical Notes

- Place Step 1.8 AFTER Step 1.6 (which adds candidate findings for the audit agents)
  and BEFORE Step 2 (which dispatches the audit agents). The delegation-fidelity audit
  is a self-check — it runs against the telemetry log, not against the codebase.
- The audit doesn't fail-loud — even if check-delegation.sh exits non-zero (shouldn't
  per its design), Step 1.8 just notes "delegation-fidelity audit unavailable" in the
  report and continues. /analyze should never block on this dimension.
- The `delegation-fidelity` dimension's findings should NAME the specific skill
  (per the spec's BR-10) — not just "ghost-skips found." Format: "<skill>
  <step>: N ghost-skips in last <window>". Reviewer reading the audit needs to know
  which skill to investigate.
- Do NOT add any /analyze logic that auto-fixes or auto-files a follow-up REQ for
  ghost-skips. The dimension SURFACES, the user DECIDES.
