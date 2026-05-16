---
id: TASK-044
title: "Switch 39 telemetry sites to $KIMI_TOOLS and source the resolver in 4 skills"
status: complete
parent: REQ-433
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-043]
repo: adlc-toolkit
---

## Description

Rewrite every project-relative telemetry-script invocation in the 4 Kimi-aware
skills to use the `$KIMI_TOOLS` prefix, and source the resolver partial once per
telemetry-bearing shell block (adjacent to that block's existing `kimi-gate.sh`
source) so `$KIMI_TOOLS` is defined wherever it is used.

## Files to Create/Modify

- `analyze/SKILL.md` — 15 invocation sites → `"$KIMI_TOOLS"/<script>.sh`; add the resolver-source line to each shell block that emits telemetry (Step 1.5, Step 1.6, Step 1.8) next to its `kimi-gate.sh` source.
- `proceed/SKILL.md` — 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line to the inline Phase 5 telemetry block.
- `spec/SKILL.md` — 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line to the Step 1.6 block.
- `wrapup/SKILL.md` — 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line to the Step 4 block.

## Acceptance Criteria

- [ ] `grep -rnE 'tools/kimi/(emit-telemetry|skill-flag|check-delegation)\.sh' analyze/SKILL.md proceed/SKILL.md spec/SKILL.md wrapup/SKILL.md` returns **0** bare invocations (AC-2). Pre-edit baseline is 39 — assert 39 → 0.
- [ ] Every command-substitution site is converted too, e.g. `flag=$(tools/kimi/skill-flag.sh create)` → `flag=$("$KIMI_TOOLS"/skill-flag.sh create)`.
- [ ] Each fenced ```sh block that references `$KIMI_TOOLS` contains exactly one resolver-source line — `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh` (BR-6) — placed as the **first statement of that block, before the first `$KIMI_TOOLS` use** (NOT merely adjacent to the `kimi-gate.sh` source: the first use is often `flag=$("$KIMI_TOOLS"/skill-flag.sh create)`, which precedes the gate source — and may even be in a different fenced block than the gate).
- [ ] No telemetry-bearing block references `$KIMI_TOOLS` without having sourced the resolver in that same block (blocks are independent shell invocations).
- [ ] Diff is path-prefix + source-line only — no change to script arguments, gate logic, stderr templates, or control flow.

## Technical Notes

- 39 sites: `skill-flag.sh` ×32, `emit-telemetry.sh` ×4, `check-delegation.sh` ×3.
- The resolver-source idiom MUST be byte-identical everywhere (TASK-046's linter
  literal depends on it): `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`
- SKILL.md shell blocks are independent invocations — `KIMI_TOOLS` does not
  persist across blocks. Source the resolver in **each** block that uses it.
  `/analyze` has multiple telemetry blocks (Step 1.5 / 1.6 shared helper, Step
  1.8); verify each independently sources both `kimi-gate.sh` and the resolver.
- Preserve the trailing space convention on the emit line
  (`"$KIMI_TOOLS"/emit-telemetry.sh <args>`) — TASK-046's `CANONICAL_LITERALS`
  match is whitespace-sensitive.
- Use Edit with enough surrounding context per site; do not rely on a single
  global sed (quoting + `$()` sites make blind substitution unsafe).
- Re-grep after editing to prove the 0 count before marking complete.
