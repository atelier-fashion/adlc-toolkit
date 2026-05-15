---
id: TASK-032
title: "SKILL.md emission edits — add flag+emit wrapping to 5 delegation points across 4 skills"
status: complete
parent: REQ-424
created: 2026-05-14
updated: 2026-05-14
dependencies: [TASK-031]
---

## Description

Add the canonical telemetry-emission pattern to every Kimi delegation point in the four
delegating skills. Each delegation block becomes:

```
1. flag=$(tools/kimi/skill-flag.sh create)   # before gate check
2. if command -v ask-kimi … gate passes …
3.    [existing delegation: stderr emit, mktemp+redact for diffs, ask-kimi call, post-validation, untrusted wrap]
4.    tools/kimi/skill-flag.sh clear "$flag"  # IMMEDIATELY after ask-kimi exits (success OR failure)
5. mode_value=$(tools/kimi/skill-flag.sh check "$flag" && echo ghost-skip || echo <delegated-or-fallback>)
6. tools/kimi/emit-telemetry.sh <skill> <step> <req> <gate> <mode_value> <reason> <duration_ms>
```

The `mode_value` resolution:
- flag still exists at end → `ghost-skip` (Claude reached emit without invoking ask-kimi)
- flag cleared AND ask-kimi exited 0 → `delegated`
- flag cleared AND ask-kimi exited non-zero → `fallback` with `reason=api-error`
- gate failed (no-binary or disabled) → `fallback` with `reason=no-binary` / `disabled-via-env`

## Files to Create/Modify

- `spec/SKILL.md` — wrap Step 1.6's "Delegated body-read" section
- `analyze/SKILL.md` — wrap Step 1.5 (shape pre-read) AND Step 1.6 (audit pre-pass) — TWO emission points
- `wrapup/SKILL.md` — wrap Step 4 "Delegated drafting" section
- `proceed/SKILL.md` — wrap Phase 5 "Delegated pre-pass" section

Each skill gets the flag-create / flag-clear / emit instructions added as numbered
steps inside the existing delegation block. Use the same `<skill>` `<step>` `<req>`
identifiers across all five:

| Skill file | <skill> | <step> | <req> source |
|---|---|---|---|
| spec/SKILL.md | `spec` | `Step-1.6` | the REQ id being spec'd (or `unknown` for /spec of a fresh feature) |
| analyze/SKILL.md Step 1.5 | `analyze` | `Step-1.5` | `unknown` (analyze is scope-driven not REQ-driven) |
| analyze/SKILL.md Step 1.6 | `analyze` | `Step-1.6` | `unknown` |
| wrapup/SKILL.md | `wrapup` | `Step-4-Lessons-Learned` | the REQ id passed to /wrapup |
| proceed/SKILL.md Phase 5 | `proceed-phase-5` | `Phase-5-Verify` | the REQ id being proceeded |

## Acceptance Criteria

- [ ] `grep -F 'skill-flag.sh create' spec/SKILL.md analyze/SKILL.md wrapup/SKILL.md proceed/SKILL.md` returns 5 lines total (one per emission point).
- [ ] `grep -F 'emit-telemetry.sh' spec/SKILL.md analyze/SKILL.md wrapup/SKILL.md proceed/SKILL.md` returns 5 lines.
- [ ] Each affected skill still passes BR-1 (canonical gate condition unchanged).
- [ ] Each affected skill's untrusted-data wrapping (REQ-414 BR-8) is preserved.
- [ ] Each affected skill's stderr log line (REQ-414 BR-4) is preserved AND the new
      emit-telemetry.sh call is in addition, not a replacement.
- [ ] `git diff --name-only` after this task lists ONLY the 4 SKILL.md files + the
      TASK-032 file.
- [ ] All affected SKILL.md files remain valid markdown end-to-end (numbered steps
      intact, code fences balanced).
- [ ] REQ-413's pytest suite still 36/36; new TASK-031 tests still pass.

## Technical Notes

- The mode resolution `mode_value=$(skill-flag.sh check "$flag" && echo ghost-skip || echo …)`
  is prose-spelled-out in the markdown — Claude executes it as a Bash tool call when running
  the skill. Same pattern as the gate condition (REQ-414 BR-1).
- The flag-clear MUST happen immediately after ask-kimi's exit code is captured. Place it
  BEFORE post-validation and BEFORE the untrusted-data wrap so the flag's deletion
  represents "ask-kimi was invoked," nothing more.
- duration_ms can be computed via `$(($SECONDS - start_seconds))*1000` or via a simple
  `date +%s%3N` (Linux) / `python3 -c 'import time; print(int(time.time()*1000))'` (portable).
  Pick the portable form; cite REQ-415 BR-3 (POSIX-only) as the rationale.
- Do NOT touch any other SKILL.md (BR-7 from REQ-417 still applies to this REQ as well).
