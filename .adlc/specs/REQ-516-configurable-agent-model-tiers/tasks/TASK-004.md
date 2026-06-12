---
id: TASK-004
title: "lint-skills drift check — surface agent model: drift via check_drift"
status: complete
parent: REQ-516
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002]
repo: adlc-toolkit
---

## Description

Add a check to `tools/lint-skills/check.py` that imports `agents_render` and
reports a `Finding` per agent whose on-disk `model:` differs from what the current
config would render (BR-5). This is the "same code path" requirement — the linter
calls `agents_render.check_drift`, not a re-implementation. Mirrors the
template-drift *rationale* (staleness detection) using the linter's existing
`Finding`/`run` mechanism.

## Files to Create/Modify

- `tools/lint-skills/check.py` — add `check_agent_model_drift(root) -> list[Finding]` and call it from `run(root)`. Resolve `tools/adlc/` onto `sys.path` for the import (guarded so a missing module degrades to zero findings rather than crashing the linter).

## Acceptance Criteria

- [ ] A hand-edited `model:` that diverges from the config render produces one `Finding` naming the agent and the expected vs actual model.
- [ ] After `adlc agents render`, the linter reports zero drift findings.
- [ ] With no config (shipped defaults) and pristine `agents/*.md`, the check yields zero findings.
- [ ] The check is additive: existing six checks and their findings are unchanged; `run(root)` simply appends this check's findings.
- [ ] If `agents_render` cannot be imported (e.g. run from an unexpected root), the check degrades gracefully (no crash; optionally a single advisory finding).

## Technical Notes

- `agents_render` lives at `<root>/tools/adlc/agents_render.py`; insert that dir on `sys.path` inside the check (mirror conftest's `sys.path.insert`).
- Use the same default-config resolution as `agents_render.main` so the linter reflects the machine's actual config.
- Keep it conservative and pure like the other checks — no shell-out.
