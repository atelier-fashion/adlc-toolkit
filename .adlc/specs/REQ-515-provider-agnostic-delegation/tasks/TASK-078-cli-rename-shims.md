---
id: TASK-078
title: "Rename CLIs to adlc-read/adlc-write with back-compat exec-shims"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-077]
---

## Description

Rename the two delegation CLIs to provider-neutral names and leave the old names
as exec-shims (BR-1, ADR-6). Wire the CLIs to `resolve_provider()` from TASK-077.

## Files to Create/Modify

- `tools/kimi/ask-kimi` → `tools/kimi/adlc-read` (git mv) — neutralize prog name,
  docstring; route `--model`/`--base-url` through `resolve_provider`. Add
  `--base-url` flag (was implicit).
- `tools/kimi/kimi-write` → `tools/kimi/adlc-write` (git mv) — same neutralization.
- `tools/kimi/ask-kimi` (new shim) — `#!/bin/sh` + `exec "$(dirname "$0")/adlc-read" "$@"`.
- `tools/kimi/kimi-write` (new shim) — `exec "$(dirname "$0")/adlc-write" "$@"`.

## Acceptance Criteria

- [ ] `adlc-read --paths <f> --question "..."` works against the resolved provider.
- [ ] `adlc-write --spec ... --target ...` works; clobber/parent-dir guards intact.
- [ ] `--model` and `--base-url` flags override the resolved values per-field (BR-2).
- [ ] `ask-kimi`/`kimi-write` shims forward all args and exit codes; `--help`,
      `--dry-run`, `--no-warn` behave identically to the new names (BR-1).
- [ ] Privacy behavior unchanged: basename-only corpus paths, exfil notice before
      `get_client`, batch skip-and-continue path validation (BR-9, BUG-080).
- [ ] Both new CLIs and both shims are executable (`chmod +x`).

## Technical Notes

- The git mv preserves history; the new shim files are net-new at the old paths.
- Keep `_strip_fences` usage in `adlc-write`.
- The `--no-warn`/`KIMI_NO_WARN` suppression stays; also honor a new
  `ADLC_DELEGATE_NO_WARN` alias if cheap, else defer.
- Do NOT change `extract-chat`.
