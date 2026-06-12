---
id: TASK-005
title: "lint-skills: cross-fence-variable check + de-branded canonical anchors + fixtures"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-003]
---

## Description

Add the structural guard that prevents the cross-fence-variable bug from regressing
(BR-5, ADR-7), retire the legacy `kimi-*` canonical spellings now that every skill is
migrated, and update fixtures + tests.

## Files to Create/Modify

- `tools/lint-skills/check.py`:
  - Add `check_cross_fence_var(text, rel)`: a non-exported variable ASSIGNED
    (`NAME=...` at statement position) in one fenced block and READ (`$NAME` / `${NAME}`)
    in a DIFFERENT fenced block of the same SKILL.md is a `cross-fence-var` finding.
    Mirror `check_cross_fence_fn`'s two-pass fence-index structure. False-positive
    guards: ignore names that are `export`ed anywhere in fences (env legitimately
    crosses), ignore obvious loop/`read`-bound names, only consider a name that is both
    assigned and read within fences. Wire into `run()` alongside the other checks.
  - `CANONICAL_LITERALS` / `KIMI_GATE_ANCHORS`: drop the legacy `kimi-*` spellings —
    keep ONLY `ADLC_DISABLE_DELEGATE` as the anchor and the `delegate-*` partial /
    `$DELEGATE_TOOLS` spellings (the migration is complete; a lingering `kimi-*` would
    now be a regression). Update the telemetry-literal tuple to the new
    `_adlc_emit_step_telemetry <skill> <step>` call shape.
  - `TELEMETRY_PARTIAL_MARKER` stays `partials/emit-step-telemetry.sh`.
- `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` →
  `tools/lint-skills/tests/fixtures/delegate-gate-ok.md` — `git mv`; de-brand content
  to the new canonical spellings (still PASSes canonical).
- `tools/lint-skills/tests/fixtures/cross-fence-var-bad.md` — NEW fixture: assigns a var
  in one fence, reads it in another → must produce a `cross-fence-var` finding.
- `tools/lint-skills/tests/fixtures/missing-canonical.md`,
  `missing-resolver-source.md`, `canonical-via-partial-skill.md`, `clean.md` —
  de-brand to the new spellings; preserve each fixture's pass/fail intent.
- `tools/lint-skills/tests/test_check.py` — update expectations for the renamed fixture,
  the new anchors/literals, and add a `cross-fence-var` test (bad fixture fails, a clean
  same-fence assign+read does not, an exported var crossing does not).
- `tools/lint-skills/README.md` — document the new `cross-fence-var` check; de-brand.

## Acceptance Criteria

- [ ] `python3 tools/lint-skills/check.py --root .` is GREEN on the migrated repo
      (shipped skills pass, including the new var check).
- [ ] `cross-fence-var-bad.md` produces exactly one `cross-fence-var` finding.
- [ ] An `export`ed var crossing fences, and a same-fence assign+read, produce NO
      `cross-fence-var` finding (no false positives).
- [ ] Canonical anchors no longer accept `kimi-*` spellings; the migrated skills satisfy
      the `delegate-*` spellings.
- [ ] `test_check.py` passes.

## Technical Notes

- `_iter_fences` already yields `(lang, fence_index, body_start, body)` — reuse it.
- Assignment regex: `^\s*([A-Za-z_][A-Za-z0-9_]*)=` at statement position (also after
  `;`/`&&`/`||`/`then`/`do`/`{`). Read regex: `\$\{?NAME\}?` with a word boundary.
- Keep the linter simple — substring/regex only, no shell parsing (LESSON-016).
