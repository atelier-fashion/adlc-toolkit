---
id: TASK-245
title: "Toolkit-only partial resolution: gate the working-copy arms preload cannot reach"
status: complete
parent: REQ-682
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: []
---

## Description

Under the runner, no partial may load code from the working copy, including partials sourced from inside other partials (architecture ADR-4). Preloading `adlc-home.sh` and `forge.sh` by absolute path covers the arms guarded by `command -v <fn>`. This task gates the remaining arms on `ADLC_FENCE_TOOLKIT_ONLY=1`, so that with the flag unset every arm behaves exactly as it does today, and adds a sentinel-decoy test that proves the closure is complete.

## Files to Create/Modify

- `partials/forge.sh` — `_adlc_forge_py` (`:218-234`) skips the repo-local and vendored `forge_config.py` when the flag is `1`. The cwd-relative `adlc-home.sh` arm (`:69`) is gated the same way.
- `partials/lessons.sh` — the nested `forge.sh` arm (`:32-33`) takes the toolkit path when the flag is `1`.
- `partials/id-alloc.sh` (`:90`), `partials/id-recheck.sh` (`:101`, `:162`) — gate the unguarded repo-local arms.
- `partials/delegate-tools-path.sh` (`:26-35`) and `partials/emit-step-telemetry.sh` (`:64-69`) — the project-local `tools/delegate` and repo-local arms are skipped when the flag is `1`.
- `tools/lint-skills/check.py` — `unguarded-source` accepts exactly one gated variant of the canonical guard in partials, with an added `[ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" != 1 ] &&` test. Nothing else changes.
- `tools/lint-skills/tests/test_check.py`, plus fixtures — the gated variant passes, and any other variant still fails.
- `partials/tests/fence-toolkit-only.test.sh` — new.

## Acceptance Criteria

- [ ] With `ADLC_FENCE_TOOLKIT_ONLY=1`, and a sentinel-writing decoy planted at every working-copy arm (`.adlc/partials/<each>.sh`, `tools/delegate/emit-telemetry.sh`, `tools/adlc/forge_config.py`, `.adlc/tools/adlc/forge_config.py`), sourcing each partial and calling its public functions writes no sentinel. The toolkit copies run, as the recorded paths show.
- [ ] Benign path: with the flag unset, the same decoys are taken exactly where they are today. `tools/delegate/tests/test_delegate_tools_path.py:64`'s precedence test, `source-guard.test.sh`, `forge.test.sh`, `lessons.test.sh` and `id-alloc.test.sh` pass unchanged.
- [ ] `bash tools/lint-skills/check.sh` exits 0, and the lint fixture with a variant other than the gated one still reports `unguarded-source`.
- [ ] The test runs under `sh`, `bash`, `zsh` and `dash`, as `toolkit-root.test.sh` does.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `partials/tests/fence-toolkit-only.test.sh::decoys_never_run_with_flag` | no |
| BR-10 | test-case | `partials/tests/fence-toolkit-only.test.sh::arms_unchanged_without_flag` | yes |
| BR-10 | test-case | `tools/lint-skills/tests/test_check.py::test_unguarded_source_gated_variant_only` | yes |

## Technical Notes

- The flag is a gate the runner sets, not a gate the model reaches. The model never runs partials directly, because sourcing is refused (probe row 9). The runner sets the flag after building the fence's environment, so no caller value survives.
- Keep each partial POSIX and dash-clean: no `local`, no arrays (LESSON-582).
- Do not gate `exec_safety.partial()`'s path. It already preloads, and `test_partial_is_sourced_from_the_install` must stay green.
- An arm that is found unguarded but is not on this list is added here, never skipped. The decoy test enumerates arms by grepping the partials for cwd-relative `[ -f ` tests, so a new arm shows up as a failure.
