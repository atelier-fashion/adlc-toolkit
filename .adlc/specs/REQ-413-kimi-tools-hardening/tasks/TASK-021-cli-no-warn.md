---
id: TASK-021
title: "ask-kimi & kimi-write: --no-warn / KIMI_NO_WARN + emit exfil notice; drop kimi-write's inline _strip_fences"
status: draft
parent: REQ-413
created: 2026-05-13
updated: 2026-05-13
dependencies: [TASK-019]
---

## Description

Wire the exfiltration notice (helper landed in TASK-019) into `ask-kimi` and `kimi-write`,
with `--no-warn` flag + `KIMI_NO_WARN=1` env-var suppression. Remove `kimi-write`'s inline
`_strip_fences` now that the version in `_common.py` is available.

## Files to Create/Modify

- `tools/kimi/ask-kimi` (MODIFY):
  - Add `--no-warn` (action=`store_true`) to argparse.
  - Right before the first API call, if `not args.no_warn and os.environ.get("KIMI_NO_WARN") != "1"`,
    call `_common.emit_exfil_notice()`.
- `tools/kimi/kimi-write` (MODIFY):
  - Add `--no-warn` (action=`store_true`) to argparse.
  - Right before the API call, same suppression logic, call `_common.emit_exfil_notice()`.
  - Delete the local `_strip_fences` function and call `_common._strip_fences(...)` instead.
- `tools/kimi/extract-chat` — **NOT MODIFIED.** It makes no API call (BR-4).
- `tools/kimi/README.md` (MODIFY):
  - Document `--no-warn` and `KIMI_NO_WARN=1` under the `ask-kimi` and `kimi-write` sections.
  - Add a short "Privacy" paragraph noting (a) file contents are sent to Moonshot when these
    tools run, (b) the corpus block now embeds only the basename of each path, (c) the notice
    + suppression options.

## Acceptance Criteria

- [ ] `ask-kimi --paths <f> --question "x"` prints exactly one line on stderr starting with
      `kimi: sending file contents to Moonshot` (verified by a subprocess test or a manual run).
- [ ] `ask-kimi --paths <f> --question "x" --no-warn` produces NO such stderr line.
- [ ] `KIMI_NO_WARN=1 ask-kimi --paths <f> --question "x"` produces NO such stderr line.
- [ ] Same three behaviors for `kimi-write` (against a `--target` in `/tmp`).
- [ ] `extract-chat <session>.jsonl` produces NO exfiltration notice (no API call).
- [ ] `kimi-write` no longer defines a local `_strip_fences`; output is still fence-stripped
      correctly (verified by a quick live `kimi-write --spec "wrap in ```python fences"` call —
      result file contains no leftover fences).
- [ ] All TASK-019 and TASK-020 tests still pass; no regression in the existing tests.
- [ ] `python3 -c "import ast; ast.parse(open('tools/kimi/ask-kimi').read()); ast.parse(open('tools/kimi/kimi-write').read())"` succeeds.
- [ ] README documents `--no-warn`, `KIMI_NO_WARN`, and the basename-only privacy default.

## Technical Notes

- Emit the notice BEFORE the API call, after path validation. If path validation fails, the
  notice should NOT fire — there was no exfiltration.
- Use `sys.stderr` explicitly via `_common.emit_exfil_notice()` (defaults to stderr inside the
  helper). Do NOT route through `print()` to stdout — that would pollute the pipeline that feeds
  Claude.
- One notice per process invocation is fine (no need for a per-call de-dup).
- Live-API ACs (notice text on a real run, fence-stripping on a real generation) are
  manual-verification items if `MOONSHOT_API_KEY` is not set in CI — but the `--no-warn`/
  `KIMI_NO_WARN` suppression and the kimi-write `_strip_fences` import path can be exercised
  offline (no API needed) by running with an invalid `--target` directory so the guard fires
  before the API call; the notice and the import path still execute earlier.
