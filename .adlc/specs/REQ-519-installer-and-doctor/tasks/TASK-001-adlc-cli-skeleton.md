---
id: TASK-001
title: "adlc umbrella CLI skeleton + data-driven subcommand dispatch"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: []
repo: adlc-toolkit
---

## Description

Create the `adlc` umbrella CLI under `tools/adlc/` (BR-11). It is a pure-stdlib
Python entry point with data-driven subcommand dispatch so later REQs add
commands (`renumber`, tier render) without touching dispatch logic. `doctor` is
the first subcommand (wired in TASK-002/003). Also provides `adlc --version`.

## Files to Create/Modify

- `tools/adlc/adlc.py` — umbrella entry: argparse with a subcommand registry
  (dict id → handler), `--version` (reads repo-root `VERSION`), help listing
  registered subcommands. No third-party deps.
- `tools/adlc/__init__.py` — (if needed for package imports in tests; mirror
  `tools/kimi` layout — kimi has no `__init__`, uses sys.path injection, so
  prefer matching that: omit `__init__.py`, use `sys.path.insert` in adlc.py
  for sibling-module imports).

## Acceptance Criteria

- [ ] `python3 tools/adlc/adlc.py --version` prints the toolkit VERSION.
- [ ] `python3 tools/adlc/adlc.py` with no subcommand prints usage listing the
      registered subcommands (including `doctor`) and exits non-zero.
- [ ] `python3 tools/adlc/adlc.py <unknown>` errors with an actionable message.
- [ ] Subcommand dispatch is a data structure (dict/list of descriptors), NOT a
      hardcoded if/elif chain — adding a command is appending one entry.
- [ ] Pure stdlib only (no import of `_common` / openai / yaml). Runnable on a
      machine that never opted into delegation.

## Technical Notes

- Mirror `tools/kimi/` conventions: `#!/usr/bin/env python3`, module-level
  docstring, `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`
  for sibling imports (so `import doctor` works regardless of cwd).
- VERSION: resolve repo root via `git rev-parse --show-toplevel` from the
  script's own dir, fall back to walking up from `__file__`; read `VERSION`.
  Do NOT hardcode the version (BR-3 path-discipline spirit).
- The dispatch table maps `"doctor" -> doctor.main` (imported lazily inside the
  handler so `--version` works even if a subcommand module has an import issue).
- Keep `adlc.py` thin: it owns arg routing only; each subcommand owns its logic.
