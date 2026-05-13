---
id: TASK-018
title: "install.sh: add pytest to the kimi venv (idempotent)"
status: draft
parent: REQ-413
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Extend `tools/kimi/install.sh` so that `pip install --upgrade` also installs `pytest` into
the existing `~/.claude/kimi-venv`. Same idempotent pattern as the current `openai` install.

## Files to Create/Modify

- `tools/kimi/install.sh` — change the existing `"$VENV_DIR/bin/pip" install --upgrade openai`
  line to install both `openai` and `pytest`. Update the surrounding echo to reflect both
  packages.

## Acceptance Criteria

- [ ] After `bash tools/kimi/install.sh`, `~/.claude/kimi-venv/bin/python3 -c "import pytest"`
      exits 0.
- [ ] Re-running `install.sh` does not duplicate any line in `~/.zshrc` / `~/.claude/CLAUDE.md` /
      `~/.claude/settings.json` (no other behavior changed).
- [ ] `bash -n tools/kimi/install.sh` passes.
- [ ] The line that adds `pytest` is placed alongside the existing `openai` install (one pip
      invocation listing both packages), not as a duplicated second `pip install` call.

## Technical Notes

- The current line in `install.sh` is `"$VENV_DIR/bin/pip" install --upgrade openai`. Change to
  `"$VENV_DIR/bin/pip" install --upgrade openai pytest`. That's the entire functional change.
- Do not touch any other section of `install.sh`.
