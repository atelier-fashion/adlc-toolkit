---
id: TASK-013
title: "Scaffold tools/kimi: venv bootstrap, install.sh, and _common.py helper"
status: draft
parent: REQ-412
created: 2026-05-12
updated: 2026-05-12
dependencies: []
---

## Description

Create the `adlc-toolkit/tools/kimi/` directory, the shared `_common.py` helper module, and an
idempotent `install.sh` that provisions the runtime: a Python venv with `openai`, `~/bin` launcher
symlinks/wrappers for the three CLIs, a PATH entry if missing, and stub guidance for the
`MOONSHOT_API_KEY` export. This is the foundation the three CLI tasks build on.

## Files to Create/Modify

- `tools/kimi/_common.py` — shared helpers:
  - `get_client()` — returns an `openai.OpenAI` configured with `base_url="https://api.moonshot.ai/v1"`
    and `api_key=os.environ["MOONSHOT_API_KEY"]`; raises a clear `SystemExit` with the var name if unset
    (never prints the value).
  - `get_model()` — returns `os.environ.get("KIMI_MODEL", "kimi-k2.5")`.
  - `pack_corpus(paths)` — reads each path, returns `"\n\n".join(f"<file path='{p}'>\n{content}\n</file>")`
    with files in the given order (caller puts files before the question for prefix-cache hits).
  - `complete(client, model, messages, max_tokens)` — calls `chat.completions.create`, then if the
    returned content is empty/whitespace raises `SystemExit("empty completion — increase --max-tokens")`.
    Returns the content string.
- `tools/kimi/install.sh` — POSIX sh, idempotent:
  - Create `~/.claude/kimi-venv` if absent (`python3 -m venv`), then `pip install --upgrade openai`.
  - For each of `ask-kimi`, `kimi-write`, `extract-chat`: write a wrapper to `~/bin/<name>` that does
    `exec "$HOME/.claude/kimi-venv/bin/python3" "<repo>/tools/kimi/<name>" "$@"` (resolve `<repo>` from
    the script's own location). `chmod +x`. Overwrite-safe (regenerates each run, no duplication).
  - Ensure `~/bin` exists; if `~/bin` not on PATH, append `export PATH="$HOME/bin:$PATH"` to `~/.zshrc`
    guarded by a marker comment so re-runs don't duplicate it.
  - Print (do not write) a reminder: `export MOONSHOT_API_KEY="..."` must be added to `~/.zshrc` by the
    user; print whether it's currently set.
  - Print next-step instructions referencing TASK-017 (CLAUDE.md routing block + settings.json allowlist).
- `tools/kimi/README.md` — placeholder header (fleshed out in TASK-017).

## Acceptance Criteria

- [ ] `bash tools/kimi/install.sh` creates `~/.claude/kimi-venv` with `openai` importable
      (`~/.claude/kimi-venv/bin/python3 -c "import openai"` exits 0).
- [ ] After install, `~/bin/ask-kimi`, `~/bin/kimi-write`, `~/bin/extract-chat` exist, are executable,
      and exec the venv interpreter against the repo scripts.
- [ ] Running `install.sh` twice produces no duplicate PATH or marker lines in `~/.zshrc`.
- [ ] `_common.get_client()` raises a non-zero `SystemExit` naming `MOONSHOT_API_KEY` when it is unset,
      and never echoes the key value.
- [ ] `_common.complete(...)` raises a non-zero `SystemExit` with an "empty completion" message when the
      model returns empty content.
- [ ] `python3 -c "import ast; ast.parse(open('tools/kimi/_common.py').read())"` succeeds (syntax check).

## Technical Notes

- Keep `_common.py` dependency-light: only `os` from stdlib plus `openai`.
- `install.sh` must be POSIX `sh`-compatible (no bashisms, no GNU flags) per repo conventions.
- Resolve the repo root inside `install.sh` from `"$(cd "$(dirname "$0")/../.." && pwd)"`.
- Do NOT commit a machine-specific shebang into the CLI scripts; they ship `#!/usr/bin/env python3`
  and the `~/bin` wrappers handle interpreter selection.
- This task does not require a live `MOONSHOT_API_KEY` to complete its syntax/idempotency checks; the
  live smoke tests happen in the CLI tasks and TASK-017.
