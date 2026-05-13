---
id: TASK-020
title: "extract-chat: raw-base64 filter + tests/test_extract_chat.py"
status: draft
parent: REQ-413
created: 2026-05-13
updated: 2026-05-13
dependencies: [TASK-018]
---

## Description

Extend `extract-chat`'s `_looks_binary` check to filter out long raw base64 strings that lack a
`data:` URI prefix, with a named threshold constant. Add hermetic pytest coverage for the JSONL
parsing + filtering behavior.

## Files to Create/Modify

- `tools/kimi/extract-chat` (MODIFY):
  - Add a module-level constant `_RAW_BASE64_MIN_LEN = 512`.
  - Extend `_looks_binary(text)` to also return True when `len(text) >= _RAW_BASE64_MIN_LEN` AND
    the text consists entirely of characters from the base64 alphabet (`A-Za-z0-9+/=`,
    optionally with internal whitespace). Use a `re.fullmatch` against
    `r"[A-Za-z0-9+/=\s]{N,}"` with N being the threshold (after stripping surrounding whitespace).
  - Document the constant inline: brief comment naming the threshold rationale (500-char prose
    safe; 600-char real base64 filtered).
- `tools/kimi/tests/test_extract_chat.py` (CREATE) — pytest cases using **inline-literal JSONL
  strings** (no fixture files):
  - A valid `user` turn with a plain text content block is emitted.
  - A valid `assistant` turn with a `text` content block is emitted; `tool_use` blocks in the
    same turn are not.
  - A `user` turn with a `tool_result` content block is filtered out.
  - A content block with `type == "image"` is filtered out.
  - A string content block starting with `data:image/png;base64,...` is filtered out.
  - A string content block that is 600 chars of valid base64 (no `data:` prefix) is filtered out.
  - A string content block that is 500 chars of normal prose (letters, spaces) is **not**
    filtered — passes through. (This proves the threshold avoids prose false positives.)
  - A malformed JSONL line in the middle is skipped; the valid line after it still emits.
  - `-o /tmp/x.txt` writes the same bytes that go to stdout.

Test invocation pattern: each test writes a string to a `tmp_path`-based file (pytest fixture),
calls `extract-chat` via `subprocess.run([sys.executable, 'tools/kimi/extract-chat', str(p)])`,
captures stdout/stderr, asserts on contents. This avoids importing `extract-chat` directly
(which has a hyphen in its name and so can't be a normal Python module).

## Acceptance Criteria

- [ ] `~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/test_extract_chat.py -q`
      reports all tests passing (at minimum 9 distinct cases listed above).
- [ ] The 500-char prose test PASSES (i.e., the content survives) — proves the threshold isn't
      eating prose.
- [ ] The 600-char raw-base64 test PASSES (i.e., the content is FILTERED) — proves the new
      branch actually fires.
- [ ] `_RAW_BASE64_MIN_LEN` is a named module-level constant (assert via a one-line
      `grep -F _RAW_BASE64_MIN_LEN tools/kimi/extract-chat` returning the line).
- [ ] `python3 -c "import ast; ast.parse(open('tools/kimi/extract-chat').read())"` succeeds.
- [ ] Re-running TASK-016's manual smoke (`extract-chat ~/.claude/projects/.../<latest>.jsonl`)
      still produces clean output (regression check on the existing path).

## Technical Notes

- The regex full-match against `[A-Za-z0-9+/=\s]{N,}` will accept prose with only those
  characters. That's why the length floor is necessary — prose at 500 chars is unlikely to be
  base64-by-accident; at 600+ it gets dramatically more likely.
- Use `re.fullmatch(r"[A-Za-z0-9+/=\s]+", text.strip())` then check `len(text.strip()) >=
  _RAW_BASE64_MIN_LEN`. Two simple conditions; clear failure.
- Tests run via `subprocess` so they exercise the actual CLI surface. Use
  `sys.executable` for the interpreter so it picks up the same Python (works under the venv
  via `kimi-venv/bin/python3 -m pytest`).
