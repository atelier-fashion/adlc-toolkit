---
id: TASK-004
title: "Document id-alloc/id-recheck partials and drop the stale drift-detection claim"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: []
repo: adlc-toolkit
---

## Description

`partials/README.md` omits `id-alloc.sh`/`id-recheck.sh` — the most contract-heavy
partials — from its sourceable-partial list, and (lines 80–82) still claims partial drift
detection is "not yet implemented" though `/template-drift` Step 3 ("Detect Partial Drift")
fully implements it (BR-5).

## Files to Create/Modify

- `partials/README.md:34–51` — add `id-alloc.sh` and `id-recheck.sh` entries at the same
  depth as `kimi-gate.sh`/`forge.sh`/`emit-step-telemetry.sh`
- `partials/README.md:80–82` — replace the "(TODO: … not yet implemented)" parenthetical
  with a pointer to `/template-drift` Step 3 (drift detection for `partials/` IS implemented)

## Acceptance Criteria

- [ ] `partials/README.md` documents `id-alloc.sh` (exports `adlc_alloc_id`/`adlc_remote_high`/kind mappers; collision-safe remote-derived id allocation, REQ-518) and `id-recheck.sh` (`adlc_recheck_id` pre-push/PR-time collision recheck, REQ-518)
- [ ] No remaining "drift detection … not yet implemented" claim for partials
- [ ] The new partial entries cite their companion contract (both have header-doc contracts; note REQ-518)

## Technical Notes

Accurate facts from the partial headers:
- `id-alloc.sh` (REQ-518): collision-safe id allocation, remote as source of truth. Exports
  `adlc_alloc_id <kind>`, `adlc_remote_high <kind>`, and kind mappers
  (`adlc_id_kind_counter/lockdir/prefix/scan`, `adlc_id_list_max`). Same-fenced-block source
  + call contract; local counter is a cache, not authority.
- `id-recheck.sh` (REQ-518 BR-4/BR-8): pre-push / PR-time id collision recheck.
  `adlc_recheck_id <kind> <ID>` returns 0 (no collision / degraded-unreachable), 1
  (collision — prints `adlc renumber` halt), 2 (usage error). Never blocks on network.
- Both follow the same source-then-call-in-same-fenced-block protocol the README already
  documents for model-2 partials. Neither currently ships a `<name>.md` companion (the
  contract lives in the header comment); say so rather than inventing a companion.
- `/template-drift` Step 3 + Step 5/6 implement partial drift detection (classify
  `synced`/`stale`/`missing`, no customization escape hatch). That is the authoritative
  pointer replacing the stale TODO.
