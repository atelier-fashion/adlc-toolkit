---
id: TASK-019
title: "_common.py: basename pack_corpus, host _strip_fences, add emit_exfil_notice; tests"
status: draft
parent: REQ-413
created: 2026-05-13
updated: 2026-05-13
dependencies: [TASK-018]
---

## Description

Three changes to `tools/kimi/_common.py`, plus the first piece of the new pytest suite that
exercises them offline:

1. `pack_corpus(paths, *, use_basename=True)` — embed `os.path.basename(p)` in the
   `<file path='…'>` attribute by default. Internal error messages (`SystemExit("file not
   found: <p>")`) continue to use the full path for actionability.
2. Move `_strip_fences(text)` from `kimi-write` into `_common.py` (the actual modification
   to `kimi-write` happens in TASK-021; this task just makes the function available).
3. Add `emit_exfil_notice(stream=sys.stderr, suppressed_by=("--no-warn", "KIMI_NO_WARN"))` —
   pure print helper. The CLIs in TASK-021 decide WHEN to call it; this task only provides the
   text and the suppression semantics doc.

## Files to Create/Modify

- `tools/kimi/_common.py` (MODIFY):
  - Change `pack_corpus` signature to `pack_corpus(paths, *, use_basename=True)`; when
    `use_basename` is true, the attribute is `os.path.basename(p)`; when false (callers that
    explicitly opt in), full path. Default true.
  - Add `_strip_fences(text)` — copy verbatim from `kimi-write` (the language-tag-tolerant
    version landed by the REQ-412 verify fixes).
  - Add `emit_exfil_notice(stream=None)` — writes one line to `stream` (defaults to
    `sys.stderr`):
    `"kimi: sending file contents to Moonshot ({model}). Pass --no-warn or set KIMI_NO_WARN=1 to silence."`
    Where `{model}` comes from `get_model()` (no API call — just reads env / default).
- `tools/kimi/tests/conftest.py` (CREATE) — three lines: insert `tools/kimi/` into `sys.path`
  so tests can `import _common` without a package install.
- `tools/kimi/tests/test_common.py` (CREATE) — pytest cases:
  - `pack_corpus(['/a/b/c.py'])` returns a string containing `<file path='c.py'>`, NOT `/a/b/c.py`.
  - `pack_corpus(['/a/b/c.py'], use_basename=False)` returns the full path in the tag.
  - `pack_corpus` on a missing file raises `SystemExit` containing the full path (the local
    error message keeps the full path).
  - `pack_corpus` on two paths returns blocks in input order.
  - `_strip_fences` handles: no fences (passthrough), plain ` ``` ` open + close,
    ` ```python ` open + ` ``` ` close, ` ``` ` open + ` ```python ` close (language tag on close).
  - `emit_exfil_notice` writes to the given stream, mentions "Moonshot", mentions both
    "--no-warn" and "KIMI_NO_WARN", and does NOT contain the literal API key var name (defense in
    depth — checks the helper text never accidentally interpolates the key).

## Acceptance Criteria

- [ ] `~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/test_common.py -q` reports
      all tests passing (at minimum 7 distinct test cases).
- [ ] Full test file runs in under 1 second.
- [ ] `pack_corpus(['/a/b/c.py'])` produces a corpus block whose `path` attribute is `c.py`,
      verified by an explicit assertion.
- [ ] `pack_corpus(['/a/b/c.py'], use_basename=False)` is regression-tested: full path present.
- [ ] `_strip_fences` test covers all four fence shapes named above.
- [ ] `emit_exfil_notice(stream)` writes one line containing "Moonshot", "--no-warn",
      "KIMI_NO_WARN" and NOT the literal string `MOONSHOT_API_KEY`.
- [ ] `python3 -c "import ast; ast.parse(open('tools/kimi/_common.py').read())"` succeeds.
- [ ] No change to the `complete()` or `get_client()` signatures.

## Technical Notes

- Use `capsys` from pytest to capture stderr/stdout in the `emit_exfil_notice` test, or pass an
  `io.StringIO` as the stream argument. The latter is simpler and avoids capture flakiness.
- The model name in the notice is the CURRENT default (env-driven); the test asserts on
  "Moonshot" rather than a specific model string so this test isn't brittle to model id changes.
- The base64 filter for `extract-chat` lives in TASK-020 — do not touch `extract-chat` in this task.
- The `--no-warn` wiring in the CLIs lives in TASK-021 — do not touch `ask-kimi`/`kimi-write` here.
- Do NOT remove `_strip_fences` from `kimi-write` here either — TASK-021 does that, after the
  helper is available in `_common`. Keeping the duplicate temporarily prevents a window where the
  CLI is broken between commits.
