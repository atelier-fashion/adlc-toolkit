---
id: TASK-015
title: "Implement kimi-write — boilerplate generator CLI"
status: draft
parent: REQ-412
created: 2026-05-12
updated: 2026-05-12
dependencies: [TASK-013]
---

## Description

`kimi-write` asks Kimi K2.5 to generate a file from a spec string plus an optional reference file,
and writes the result to a target path for Claude to review and surgically edit. Refuses to clobber
an existing target without `--force`.

## Files to Create/Modify

- `tools/kimi/kimi-write` — argparse CLI:
  - `--spec TEXT` (required) — description of what to generate (e.g., "pytest test file for the
    MAVLink heartbeat parser")
  - `--context PATH` (optional) — reference file Kimi reads for patterns/conventions
  - `--target PATH` (required) — output file path
  - `--force` (flag) — allow overwriting an existing `--target`
  - `--max-tokens INT` (default 16384)
  - `--model TEXT` (default `KIMI_MODEL` / `kimi-k2.5`)
  - Behavior: if `--target` exists and `--force` not set → non-zero exit with a clear message. Parent
    dir of `--target` must exist (don't `mkdir -p` silently) → non-zero exit if missing. Build messages:
    system "You generate complete, idiomatic files matching the given conventions. Output ONLY the file
    contents, no markdown fences."; user with optional `<reference path='...'>...</reference>` block
    THEN the spec. Call `_common.complete(...)`, strip any stray code fences, write to `--target`.
    Print the target path written and a one-line note to review it.

## Acceptance Criteria

- [ ] `kimi-write --spec "..." --context <ref> --target <out>` produces `<out>` on disk with content
      matching the spec (live key required).
- [ ] Running it modifies ONLY `<out>` — no other file changes (verify with `git status` / mtimes).
- [ ] If `<out>` already exists and `--force` is omitted → non-zero exit, file left unchanged.
- [ ] With `--force`, an existing `<out>` is overwritten.
- [ ] Missing parent directory of `--target` → non-zero exit, nothing written.
- [ ] Unset `MOONSHOT_API_KEY` → non-zero exit naming the var.
- [ ] Output file contains no leftover ```` ``` ```` fences.
- [ ] Syntax check passes (`ast.parse`).

## Technical Notes

- Reuse `_common.get_client/get_model/complete`. Reference-file content goes BEFORE the spec in the
  message order (consistency + cache-friendliness), though caching matters less here than for `ask-kimi`.
- Fence-stripping: if the response starts with ```` ```lang ```` and ends with ```` ``` ````, strip those
  lines; otherwise write as-is.
- Do not auto-create directories — surfacing a missing-dir error is safer than guessing intent.
