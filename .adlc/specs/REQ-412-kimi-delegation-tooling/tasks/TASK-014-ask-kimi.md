---
id: TASK-014
title: "Implement ask-kimi — bulk file reader CLI"
status: draft
parent: REQ-412
created: 2026-05-12
updated: 2026-05-12
dependencies: [TASK-013]
---

## Description

`ask-kimi` packs one or more files into a corpus (files first, question last for Moonshot
prefix-cache hits), sends it to Kimi K2.5, and prints a structured text summary to stdout — so
Claude can answer a multi-file question without reading every file into its own context.

## Files to Create/Modify

- `tools/kimi/ask-kimi` — argparse CLI:
  - `--paths PATH [PATH ...]` (required, ≥1) — files to read
  - `--question TEXT` (required) — the question to answer about them
  - `--max-tokens INT` (default 8192)
  - `--model TEXT` (default from `KIMI_MODEL` env / `kimi-k2.5`)
  - Builds messages: `[{role:system, content:"You are a precise code analyst..."},
    {role:user, content:f"<corpus>\n{pack_corpus(paths)}\n</corpus>"}, {role:user, content:question}]`
    — corpus message BEFORE question message.
  - Calls `_common.complete(...)`, prints result to stdout. Non-zero exit on any error (missing key,
    unreadable path, empty completion).

## Acceptance Criteria

- [ ] `ask-kimi --paths <f1> <f2> --question "..."` against ≥2 real files totaling >400 lines returns
      a coherent structured summary (live `MOONSHOT_API_KEY` required for this check).
- [ ] The corpus message precedes the question message in the request (verify by code inspection /
      a `--dry-run` or debug print if added).
- [ ] Running `ask-kimi` twice on the same `--paths` with different `--question` values reuses the
      cached corpus prefix — observable via Moonshot usage/billing or response usage metadata
      (`prompt_cache_hit_tokens` or equivalent).
- [ ] Unreadable / missing path → non-zero exit with the offending path named.
- [ ] Unset `MOONSHOT_API_KEY` → non-zero exit naming the var (inherited from `_common`).
- [ ] `--max-tokens 16` (tiny) → non-zero exit with the "empty completion" diagnostic.
- [ ] Syntax check passes (`ast.parse`).

## Technical Notes

- Import helpers from `_common` (same directory — the `~/bin` wrapper execs the script in place, so
  add the script's own dir to `sys.path` or use a relative import shim at top of file).
- System prompt should ask for a concise structured summary (sections / bullets), not a verbatim dump,
  to keep the returned token count small.
- Do not catch-and-swallow API errors — let them surface with a non-zero exit (ETHOS #6).
