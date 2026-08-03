---
id: TASK-083
title: "Implement --version across the three delegation CLIs + shared version helpers"
status: complete
parent: REQ-553
created: 2026-08-03
updated: 2026-08-03
dependencies: []
repo: adlc-toolkit
---

## Description

Add `toolkit_version()` / `_repo_root()` helpers to `tools/delegate/_common.py` and wire a pre-parse `--version` / `-V` scan into `adlc-read`, `adlc-write`, and `extract-chat` per architecture ADR-1..3. Output follows the BR-9 `key: value` contract; the config section comes from the real `resolve_provider()` wrapped in `try/except SystemExit` → `config_error:` (BR-6).

## Files to Create/Modify

- `tools/delegate/_common.py` — add `_repo_root()` (git rev-parse from script dir, fallback walk `tools/delegate` → `tools` → root, per `tools/adlc/adlc.py:24-42`) and `toolkit_version()` (read `<root>/VERSION`, `"unknown"` on OSError); stdlib only
- `tools/delegate/adlc-read` — pre-parse argv scan for `--version`/`-V` at top of `main()` before `_parse_args()`; print version line + resolved config (BR-9 keys); add the flag to argparse help via an epilog or a documented no-op flag entry so `--help` mentions it
- `tools/delegate/adlc-write` — same pre-parse scan (MUST fire before argparse because `--spec`/`--target` are `required=True`); same output contract
- `tools/delegate/extract-chat` — same pre-parse scan; imports `_common` lazily INSIDE the version branch (ADR-2); prints the version line only

## Acceptance Criteria

- [ ] `adlc-read --version` prints `adlc-toolkit 5.0.0` (VERSION content) + `base_url:`, `model:`, `api_key_env:`, `enabled:` lines and exits 0 (BR-1, BR-2, BR-9)
- [ ] `adlc-write --version` (with NO `--spec`/`--target`) and `extract-chat --version` (with NO positional) exit 0 — the pre-parse scan beats argparse's required-arg error (ADR-1)
- [ ] Env overrides `ADLC_DELEGATE_MODEL` / `ADLC_DELEGATE_BASE_URL` are reflected in the output (BR-3: same resolver as real calls)
- [ ] A key-in-config `api_key_env` yields `config_error:` + exit 0, no traceback (BR-6)
- [ ] No API-key VALUE is ever read or printed; no `openai` import on the version path; no network (BR-2, BR-4)
- [ ] `enabled:` prints lowercase `true`/`false`
- [ ] No Kimi-branded strings introduced (BR-8)

## Technical Notes

- Mirror `--print-enabled`'s `try/except SystemExit` shape (`adlc-read:63-69`) for the `config_error` path; the SystemExit message becomes the `config_error:` value (flatten newlines to spaces so the output stays one line per key).
- `parse_delegate_config()` already fail-softs missing/unreadable config to `{}` — only the key-in-config refusal raises; both paths must end at exit 0.
- Scan `argv if argv is not None else sys.argv[1:]` so tests can pass argv explicitly.
- Do NOT print `Provider.source` (ADR-3 — AC pins the exact key set).
