---
id: REQ-428
title: "Dedupe analyze SKILL telemetry resolution block"
status: complete
deployable: false
created: 2026-05-15
updated: 2026-05-15
component: "adlc/analyze"
domain: "adlc"
stack: ["markdown", "bash"]
concerns: ["maintainability", "duplication"]
tags: ["telemetry", "kimi-delegation", "skill-md", "refactor"]
---

## Description

`analyze/SKILL.md` Steps 1.5 and 1.6 each end with a near-identical ~15-line shell block that computes `duration_ms`, branches on the four telemetry modes (`fallback` / `ghost-skip` / `delegated` / `fallback`+`api-error`), and calls `tools/kimi/emit-telemetry.sh`. The two blocks differ only in the step label argument (`Step-1.5` vs `Step-1.6`).

Any future change to the telemetry resolution logic or the `emit-telemetry.sh` argument signature has to be applied in two places, and the two blocks can silently drift. This was surfaced as a Quality finding during REQ-425 Phase 5 verify but was out of scope for that REQ.

The goal is to define the resolution+emit logic once inside the skill and invoke it from both steps, while keeping the lint-skills canonical-helper rule passing.

## System Model

_Not applicable — this is a refactor of an existing skill markdown file with no new entities, events, or permissions._

## Business Rules

- [x] BR-1: After the refactor, the telemetry resolution+emit logic for Steps 1.5 and 1.6 must be defined in exactly one place in `analyze/SKILL.md` (single source of truth). A future change to the `emit-telemetry.sh` argument signature must require editing exactly one location.
- [x] BR-2: The semantic behavior of telemetry emission must be preserved exactly. Both call sites must still emit one telemetry record with the existing field set: `skill=analyze`, `step=Step-1.5` or `Step-1.6`, `req=unknown`, plus the resolved `gate_result`, `mode`, `reason`, and `duration_ms`. Mode resolution rules (fallback / ghost-skip / delegated / api-error) and the order of `skill-flag.sh clear` calls must be unchanged.
- [x] BR-3: `tools/lint-skills/check.py` must exit 0 against the toolkit after the refactor. The canonical-helper rule currently requires the literals `start_s=$(date -u +%s)`, `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`, and `tools/kimi/emit-telemetry.sh ` to appear in any SKILL.md that mentions `ADLC_DISABLE_KIMI`. The refactored `analyze/SKILL.md` must still contain each of these literals at least once (informed by REQ-425 canonical-helper rule).
- [x] BR-4: The two existing `start_s=$(date -u +%s)` declarations (one per step, before each gate check) remain untouched. The refactor targets only the post-path resolve+emit block, not the per-step start-time capture or the gate-check setup.
- [x] BR-5: The shared helper must be a Bourne-shell function defined inside a `sh`/`bash`/`shell` fenced code block in the skill markdown. It must not introduce a new file under `tools/kimi/` unless function scoping inside the skill turns out to be fragile in practice (fallback option).

## Acceptance Criteria

- [x] AC-1: `analyze/SKILL.md` contains exactly one definition of the telemetry-resolve-and-emit logic, and Steps 1.5 and 1.6 each invoke it with their step label as an argument.
- [x] AC-2: `grep -c "tools/kimi/emit-telemetry.sh" analyze/SKILL.md` returns 1 (down from 2). `grep -c "duration_ms=\$(( " analyze/SKILL.md` returns 1 (down from 2).
- [x] AC-3: `tools/lint-skills/check.py --root .` exits 0 when run from the toolkit root.
- [x] AC-4: `tools/lint-skills/check.sh` (if present and used by CI) exits 0 when run from the toolkit root.
- [x] AC-5: The diff against `main` shows no behavioral change to mode resolution, `skill-flag.sh clear` ordering, the `ASK_KIMI_INVOKED` / `KIMI_EXIT` variable contract, or the trap on EXIT.
- [x] AC-6: A grep of the file shows the helper is defined before its first invocation (i.e. defined inside the Step 1.5 fence or earlier, not after Step 1.6).

## External Dependencies

- None. This change is fully internal to `adlc-toolkit/analyze/SKILL.md` and revalidates against existing `tools/lint-skills/check.py`.

## Assumptions

- The lint canonical-helper rule from REQ-425 uses `literal in text` semantics — a single textual occurrence of each required literal satisfies it, so collapsing two occurrences into one (inside the shared function body) is sufficient (verified by reading `tools/lint-skills/check.py:157-167`).
- Shell-function scoping inside a single SKILL.md fence is workable: the function defined in one fenced block in Step 1.5 will be sourced into the same shell session that runs Step 1.6's fenced block when the skill executes top-to-bottom. The fallback (wrapper script under `tools/kimi/`) is reserved for the case where this turns out to be fragile in practice.
- No other SKILL.md file currently shares this exact resolution block — this refactor is local to `analyze/SKILL.md`. (A future REQ may generalize the helper across skills; out of scope here.)

## Open Questions

- [x] Should the helper function be named `_emit_step_telemetry` (leading underscore, "private" convention) or `adlc_emit_step_telemetry` (matches the existing `adlc_kimi_gate_check` naming in `partials/kimi-gate.sh`)? **Resolved**: shipped as `_adlc_emit_step_telemetry` (underscore prefix + `adlc_` namespace) — private-to-skill convention since the helper is scoped inside `analyze/SKILL.md` and not intended to be sourced elsewhere.

## Out of Scope

- Generalizing the helper across other SKILL.md files (e.g., `spec/SKILL.md`, which has the same block shape). That is a separate REQ if/when it lands.
- Changing the `emit-telemetry.sh` argument signature or the telemetry schema.
- Refactoring the gate-check setup, the `trap` line, the `ASK_KIMI_INVOKED`/`KIMI_EXIT` variable contract, or the per-step `start_s` capture.
- Adding a new `tools/kimi/emit-step-telemetry.sh` wrapper script (kept only as a fallback if function scoping proves fragile).
- Auditing/dedup'ing the Step 1.5 and Step 1.6 gate-check and `ask-kimi` invocation prologues themselves (different content, would be a separate refactor).

## Retrieved Context

No prior context retrieved — no tagged documents matched this area. (Cold-start path: the canonical-helper rule, REQ-425, and the prior duplication finding are referenced inline above rather than via retrieved-doc score.)
