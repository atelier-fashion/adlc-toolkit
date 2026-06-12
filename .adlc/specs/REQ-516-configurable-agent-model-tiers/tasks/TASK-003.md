---
id: TASK-003
title: "Register `adlc agents render` additively in the umbrella CLI"
status: complete
parent: REQ-516
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002]
repo: adlc-toolkit
---

## Description

Wire `adlc agents render` into the umbrella CLI by appending ONE entry to the
data-driven `SUBCOMMANDS` table and adding a small lazy-import handler — no change
to dispatch logic (REQ-519 BR-11). This keeps the merge surface with the
concurrently-running REQ-518 (which also appends to `SUBCOMMANDS`) to a single
adjacent dict entry.

## Files to Create/Modify

- `tools/adlc/adlc.py` — add `_cmd_agents(argv)` (lazy `import agents_render`; delegate to `agents_render.main(argv)`), and append an `"agents"` entry to `SUBCOMMANDS` with a help string.

## Acceptance Criteria

- [ ] `adlc agents render` dispatches to `agents_render.main(["render"])`.
- [ ] `adlc agents render --check` and `adlc agents render --config <p>` pass remaining argv through unchanged.
- [ ] The change is purely additive: `main()`/`_usage()`/dispatch loop are untouched; only a new handler function and a new `SUBCOMMANDS[...]` entry are added.
- [ ] `adlc --version`, `adlc --help`, and `adlc doctor` still behave exactly as before (no regression).
- [ ] The new subcommand appears in the `adlc` usage listing.

## Technical Notes

- Follow the existing `_cmd_doctor` pattern exactly: lazy import inside the handler so an import error in `agents_render` never breaks `adlc --version`.
- Handler signature: `_cmd_agents(argv) -> int`, returns `agents_render.main(argv)`.
- Do NOT add an `if/elif` limb anywhere — the dispatch is the existing `entry["handler"](rest)`.
