---
id: TASK-098
title: "Every call-site fence refuses an empty ADLC_READ_BIN; lint-skills rejects the bare-name fallback"
status: draft
parent: REQ-609
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-097]
---

## Description

Remove the second resolver from every fence (REQ BR-12). Each fence that invokes `"${ADLC_READ_BIN:-adlc-read}"` now sources the gate, checks `[ -n "$ADLC_READ_BIN" ]`, and on empty writes one stderr line and exits non-zero **before** any temp file is handed over; then invokes `"$ADLC_READ_BIN"`. Add a `read-bin-fallback` check to `tools/lint-skills/check.py` that rejects `ADLC_READ_BIN:-` in any fence, with the same posture as `forge-direct-gh` (LESSON-012), and a pytest that extracts each fence, runs it under `/bin/sh` with a fake gate partial exporting an empty `ADLC_READ_BIN` and a stub `adlc-read` on `$PATH`, and asserts non-zero exit with the stub never called.

## Files to Create/Modify

- `agents/delegate-pre-pass.md` — two fences
- `analyze/SKILL.md` — two fences
- `proceed/SKILL.md` — one fence (Phase 5 pre-pass)
- `spec/SKILL.md` — two fences (Step 1.4 and Step 1.6)
- `wrapup/SKILL.md` — one fence
- `tools/lint-skills/check.py` — new `read-bin-fallback` check; register in the check list and README
- `tools/lint-skills/README.md` — document the check
- `tools/lint-skills/tests/test_check.py` — cases for the new check (fires on `ADLC_READ_BIN:-`, does not fire on `"$ADLC_READ_BIN"`, fixture files under `tools/lint-skills/tests/fixtures/`)
- `tools/lint-skills/tests/test_read_bin_fences.py` — new: extracts every fence in the five files that references `ADLC_READ_BIN`, runs it with the fake gate, asserts refusal and no stub call; also asserts the grep in REQ AC-8 matches nothing outside `partials/tests/fixtures/` and `.adlc/specs/`

## Acceptance Criteria

- [ ] `grep -rn 'ADLC_READ_BIN:-adlc-read' --include='*.md' --include='*.sh' . | grep -vE '^\./(\.adlc/specs|partials/tests/fixtures|CHANGELOG\.md)'` matches nothing
- [ ] Each of the eight fences, run with an empty `ADLC_READ_BIN`, exits non-zero, prints a line naming the skill and the reason, and never invokes the stub
- [ ] `tools/lint-skills/check.sh .` from outside `.worktrees` scans the skills and passes; a fixture with the fallback fails with `read-bin-fallback`
- [ ] The `cross-fence-fn` check still passes — the gate is sourced in the same fence as the check and the invocation
- [ ] Telemetry marks in the `/proceed` and `/spec` fences (`skill-flag.sh mark ... invoked 1` / `exit`) stay adjacent to the invocation, so a refusal before the call is recorded as not invoked

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | structural-check | `tools/lint-skills`: read-bin-fallback | yes |
| BR-12 | test-case | `tools/lint-skills/tests/test_check.py::test_read_bin_fallback_fires_and_passes` | yes |
| BR-12 | test-case | `tools/lint-skills/tests/test_read_bin_fences.py::test_each_fence_refuses_when_empty` | yes |
| AC-8 | test-case | `tools/lint-skills/tests/test_read_bin_fences.py::test_each_fence_refuses_when_empty` | yes |
| AC-8 | test-case | `tools/lint-skills/tests/test_read_bin_fences.py::test_no_bare_name_fallback_outside_fixtures_and_specs` | yes |
| BR-16 | structural-check | `tools/lint-skills`: cross-fence-fn | yes |

## Technical Notes

- **Fence shape.**
  ```sh
  . .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
  [ -n "$ADLC_READ_BIN" ] || { echo "/<skill>: ADLC_READ_BIN is empty — refusing to hand over the corpus (re-run install.sh --with-delegation)" >&2; exit 1; }
  "$ADLC_READ_BIN" --no-warn --paths ...
  ```
  Keep every other line of each fence byte-identical; the telemetry `mark invoked 1` line, where present, comes after the check.
- **Lint check.** Scan fenced `sh`/`bash` blocks only (the same fence iterator the other checks use); flag lines matching the fixed string `ADLC_READ_BIN:-`. Message: `read-bin-fallback: fence resolves adlc-read a second time via a bare-name default; source the gate and refuse on empty ADLC_READ_BIN (REQ-609 BR-12)`.
- **Fence-execution test.** Reuse the fence extractor from `test_check.py` if one exists; else a small regex over ```` ```sh ```` blocks. Provide `.adlc/partials/delegate-gate.sh` in a temp cwd that does `export ADLC_READ_BIN=""; adlc_delegate_gate_check() { ADLC_DELEGATE_GATE_REASON=ok; return 0; }`, put a stub `adlc-read` writing a marker on `$PATH`, run `sh -c` on the fence body with `set +e`, assert `rc != 0` and marker absent. Skip lines that are the telemetry/`mktemp` scaffolding only if they fail for reasons unrelated to the refusal — prefer providing a fake `skill-flag.sh` too.
- Run the linter from the primary checkout path, not from inside `.worktrees` (LESSON-019: `SKIP_DIR_PARTS` makes an in-worktree run vacuous).
