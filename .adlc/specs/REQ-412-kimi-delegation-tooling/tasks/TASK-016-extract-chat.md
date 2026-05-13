---
id: TASK-016
title: "Implement extract-chat — Claude Code JSONL transcript cleaner CLI"
status: complete
parent: REQ-412
created: 2026-05-12
updated: 2026-05-12
dependencies: [TASK-013]
---

## Description

`extract-chat` reads a Claude Code session transcript (`~/.claude/projects/<proj>/<session>.jsonl`)
and emits just the human-readable conversation — human prompts and assistant natural-language
replies — stripping tool calls, tool results, system prompts, and binary/base64 blobs. Feeds the
doc-update pipeline (`extract-chat` → `ask-kimi` → Claude applies edits).

## Files to Create/Modify

- `tools/kimi/extract-chat` — argparse CLI:
  - positional `jsonl_path` (required) — the `.jsonl` transcript
  - `-o, --output PATH` (optional) — write here instead of stdout
  - Behavior: iterate JSONL lines; for each record, keep only `user` and `assistant` turns whose
    content is text. For assistant messages, concatenate text content blocks; skip `tool_use` blocks.
    For user messages, skip `tool_result` blocks (these are tool outputs, not human input) — keep only
    genuine human text. Drop anything that looks like base64 / data URIs / images. Emit as readable
    plain text with simple `## Human` / `## Assistant` separators. Tolerate malformed lines (skip + continue,
    don't crash). Non-zero exit only if the file can't be opened at all.

## Acceptance Criteria

- [ ] `extract-chat <session>.jsonl` on a real transcript emits clean conversation text with zero
      tool-call, tool-result, or system-prompt lines, and no base64 blobs.
- [ ] Piping its output into `ask-kimi --paths /tmp/chat.txt <doc>.md --question "what doc updates are
      needed?"` works end to end (combined with TASK-014).
- [ ] A transcript containing image/base64 content blocks produces output with those omitted.
- [ ] A malformed/truncated JSONL line is skipped without crashing; valid lines around it still emit.
- [ ] Nonexistent input path → non-zero exit naming the path.
- [ ] `-o /tmp/out.txt` writes the same content that would go to stdout.
- [ ] Syntax check passes (`ast.parse`).

## Technical Notes

- This tool makes NO Kimi API call — it's pure local transformation. It does not need
  `MOONSHOT_API_KEY`. (Still lives in `tools/kimi/` for cohesion.)
- Claude Code JSONL schema can drift; be defensive — branch on record `type`/`role` keys that exist,
  ignore unknown shapes rather than asserting structure.
- Keep output compact: the whole point is a small artifact to feed back into `ask-kimi`.
