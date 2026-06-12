---
id: TASK-005
title: "Tests for render + drift, and README documentation"
status: complete
parent: REQ-516
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002, TASK-003]
repo: adlc-toolkit
---

## Description

Add pytest coverage for the render engine and CLI registration (mirroring
`tools/adlc/tests/test_dispatch.py` and `test_checks.py`), a test for the
lint-skills drift check, and document `adlc agents render` + the `agents:` config
block in `tools/adlc/README.md`. Every acceptance criterion in REQ-516 maps to a test.

## Files to Create/Modify

- `tools/adlc/tests/test_agents_render.py` (new) — engine + CLI tests.
- `tools/lint-skills/tests/` — one test for `check_agent_model_drift`.
- `tools/adlc/README.md` — document the `agents render` subcommand, `--check`, the `agents:` config schema, the allowed alias set, and the fail-loud behavior.

## Acceptance Criteria

- [ ] Test: `scanner: haiku` renders only scanner agents; all other agent files byte-identical (REQ-516 AC-1).
- [ ] Test: no-config render is a no-op — resolved == committed for all 18; empty diff (AC-2).
- [ ] Test: class `inherit` removes `model:`; rendering back to an alias restores it (AC-3).
- [ ] Test: render twice → second run writes nothing / empty diff (AC-4).
- [ ] Test: drift — hand-edit a `model:`, `check_drift`/lint flags it; re-render clears it (AC-5).
- [ ] Test: invalid alias (`scanner: gpt5`) fails loud with key+value+allowed set in the message (AC-6).
- [ ] Test: CLI dispatch — `adlc agents render` and `--check` route correctly; `SUBCOMMANDS` entry is data-driven (mirrors test_dispatch).
- [ ] `tools/adlc/README.md` documents the subcommand and config block.
- [ ] All new tests pass under `python3 -m pytest tools/adlc/tests tools/lint-skills/tests`.

## Technical Notes

- Tests are offline, `tmp_path`-driven: copy a few real `agents/*.md` (or synthesize minimal ones with `tier:` + `model:`) into a tmp `agents/` and render against a tmp config; assert byte-equality on untouched files.
- For AC-2 (parity with committed files), test against the real repo `agents/` via `repo_root` fixture: render with empty config into a copy, assert no file changed.
- Linux parity (AC-7) is structural: pure-Python `os.replace`, no shell — note this in the README rather than a separate test, or assert no shell subprocess is used by the engine.
- Reuse the `conftest.py` `repo_root` fixture and `sys.path` insertion already present in `tools/adlc/tests/`.
