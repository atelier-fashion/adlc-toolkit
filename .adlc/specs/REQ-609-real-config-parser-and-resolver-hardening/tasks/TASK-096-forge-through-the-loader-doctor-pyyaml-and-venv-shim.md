---
id: TASK-096
title: "forge_config reads through the loader; adlc doctor gains a pyyaml check; the adlc shim prefers the venv"
status: draft
parent: REQ-609
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-094]
---

## Description

Retire the second hand reader. `tools/adlc/forge_config.parse_forge_config` reads its section from `load_machine_config()` (imported from `tools/delegate` via a path insertion relative to its own file), refuses on every `malformed` reason except `dependency-missing`, which it treats as unconfigured after the same stderr line (architecture ADR-2). `tools/adlc/checks.py`'s two config probes and the root `install.sh` `adlc` shim prefer the delegate venv's interpreter when it exists and fall back to `python3` otherwise; a new `pyyaml` doctor check reports importability in the interpreter `adlc` runs under, with the copy-pasteable fix. `checks.py` imports nothing YAML-related at module level (LESSON-395).

## Files to Create/Modify

- `tools/adlc/forge_config.py` — replace the flat reader with the loader call; keep `looks_like_key`, `validate_auth`, provider resolution unchanged; on `malformed` other than `dependency-missing`, exit non-zero naming path and reason
- `tools/adlc/checks.py` — `_delegate_interpreter()` helper (venv `bin/python3` if executable, else `sys.executable`); use it in `_config_enabled` and `_forge_pat_status`; new `check_pyyaml` registered in the `Check` list with PASS/FAIL/SKIP and a fix string
- `install.sh` — `ensure_adlc_shim` writes a shim that `exec`s `$HOME/.claude/delegate-venv/bin/python3` when `-x`, else `python3`; content-compare idempotency and `atomic_write` unchanged (LESSON-017)
- `tools/adlc/tests/test_forge_config.py` — rewrite the flat-reader cases into loader-backed cases; add the section-isolation and dependency-missing cases
- `tools/adlc/tests/test_checks.py` — `check_pyyaml` PASS/FAIL cases, interpreter selection
- `tools/adlc/tests/test_install_shim.py` — new: run root `install.sh --dry-run`-equivalent shim generation in a sandbox `HOME`, execute the generated shim with and without a fake venv, assert which interpreter ran
- `tools/adlc/README.md` — add `pyyaml` to the doctor check list

## Acceptance Criteria

- [ ] A config with only a `forge:` section leaves delegation unconfigured (`parse_delegate_config` → `{}`); a config with only `delegate:` leaves forge unconfigured; both proven by tests
- [ ] A duplicate key under `forge:` makes `parse_delegate_config` malformed, and a duplicate under `delegate:` makes forge refuse — whole-document, both directions
- [ ] With PyYAML unimportable in the probing interpreter, forge proceeds as unconfigured with the stderr line; every other malformed reason makes forge exit non-zero naming path and reason
- [ ] `adlc doctor` on a sandbox `HOME` with no venv and a `python3` without PyYAML reports `pyyaml` FAIL with the fix, and does not crash (LESSON-395 test: run doctor with nothing installed)
- [ ] The generated `adlc` shim runs the venv interpreter when the venv exists and `python3` otherwise; `install.sh` remains idempotent (second run reports `ok`)
- [ ] `python3 -m pytest tools/adlc -q` green under both the system interpreter and the venv interpreter

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | `tools/adlc/tests/test_forge_config.py::test_reads_section_through_load_machine_config` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_forge_config.py::test_forge_only_config_leaves_delegate_unconfigured` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_forge_config.py::test_delegate_only_config_leaves_forge_unconfigured` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_install_shim.py::test_shim_prefers_venv_when_present` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_checks.py::test_pyyaml_check_reports_fix_when_missing` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_forge_config.py::test_duplicate_key_is_whole_document` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_forge_config.py::test_dependency_missing_is_unconfigured_for_forge_with_stderr` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_forge_config.py::test_forge_only_config_leaves_delegate_unconfigured` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_forge_config.py::test_reads_section_through_load_machine_config` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_install_shim.py::test_shim_prefers_venv_when_present` | yes |

## Technical Notes

- **Import path.** `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "delegate"))` guarded by a module-level `try/except ImportError` that leaves a `load_machine_config = None` sentinel; `parse_forge_config` treats that sentinel as `dependency-missing` too (the delegate tree absent is the same install defect class). ASSUME-001 covers script-relative resolution surviving the shim's `exec`.
- **Shim text.**
  ```sh
  #!/usr/bin/env bash
  _v="$HOME/.claude/delegate-venv/bin/python3"
  if [ -x "$_v" ]; then exec "$_v" "<REPO_ROOT>/tools/adlc/adlc.py" "$@"; fi
  exec python3 "<REPO_ROOT>/tools/adlc/adlc.py" "$@"
  ```
  Keep `$REPO_ROOT` stamped as today. The `want` string comparison in `ensure_adlc_shim` must compare the whole new text.
- **Doctor check.** `check_pyyaml(profile)`: run `[interp, "-c", "import yaml; print(yaml.__version__)"]` where `interp` is the same selection the shim makes; PASS with version, FAIL with fix `run <repo>/install.sh --with-delegation  # or: python3 -m pip install --user 'pyyaml>=6.0'`. SKIP is not a valid outcome here — the check is meaningful on every machine.
- **Interpreter selection test.** Monkeypatch `HOME` to `tmp_path`, create `tmp_path/.claude/delegate-venv/bin/python3` as an executable script that writes a marker and `exec`s the real interpreter, assert the marker.
- The `forge` refusal message follows BR-13's shape: path, reason, no advice to set an env var.
