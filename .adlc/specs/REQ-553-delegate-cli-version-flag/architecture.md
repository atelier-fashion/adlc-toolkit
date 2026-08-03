# Architecture — REQ-553: --version flag for the delegation CLIs

## Approach

Mirror the proven `adlc --version` pattern (`tools/adlc/adlc.py:24-52, 115-117`) inside `tools/delegate/`: a repo-root/VERSION reader lives in the shared module, and each CLI handles `--version` as a **pre-parse argv scan** that prints and exits 0 before argparse, before any guard, and before any network-capable code path.

The resolved-config section (adlc-read/adlc-write only) reuses `_common.resolve_provider()` verbatim — the same call the real delegation path makes (BR-3, LESSON-392) — wrapped in `try/except SystemExit` so a key-in-config refusal degrades to a `config_error:` line instead of a traceback (BR-6), exactly as `--print-enabled` already does (`adlc-read:63-69`).

## Key decisions

### ADR-1: `--version` is a pre-parse argv scan, not an argparse flag

`adlc-write` declares `--spec`/`--target` with `required=True` and `extract-chat` has a required positional; argparse rejects the invocation with exit 2 before any `store_true` flag is visible to `main()`. The precedent `tools/adlc/adlc.py:115-117` solves this with a pre-parse check (`if argv and argv[0] in ("--version", "-V")`). We generalize slightly — scan the whole argv for `--version`/`-V` (so `adlc-read --no-warn --version` works) — and apply the identical mechanism in all three CLIs for uniformity. Rejected alternative: a custom argparse action (fires mid-parse, but couples exit behavior to parser internals and still differs per-CLI); relaxing `required=True` (widens the CLI contract for one flag's benefit).

### ADR-2: version helpers live in `_common.py`; `extract-chat` imports lazily

`_repo_root()` + `toolkit_version()` go in `_common.py` (stdlib-only: `os`, `subprocess`; `_common` already imports `subprocess`-free — use the `adlc.py` git-then-walk pattern with `tools/delegate` → `tools` → root). `adlc-read`/`adlc-write` already import `_common` at module top (safe — BUG-056 made `openai` lazy). `extract-chat` deliberately does NOT import `_common` at module scope today; it stays that way — the `--version` branch does the `sys.path` insert + `import _common` **inside the branch**, so `extract-chat`'s module-load surface is unchanged. Rejected alternative: duplicating a private `_version()` in extract-chat (copy rot — LESSON-005 sibling-drift class).

### ADR-3: output contract is exactly the BR-9 key set; `Provider.source` is excluded

Output (stdout, exit 0):

```
adlc-toolkit <VERSION-file-content>
base_url: <resolved>
model: <resolved>
api_key_env: <NAME only>
enabled: true|false
```

On resolution refusal (SystemExit from `resolve_provider`): line 1 plus `config_error: <message>` only. `extract-chat`: line 1 only. `Provider.source` ("flags"/"env"/"config"/"defaults") is documented as *not part of the contract* in `_common.py` and the spec AC pins "exactly the BR-9 keys", so it is not printed — adding it later is a spec change, not a drive-by.

### ADR-4: docs stop at `tools/delegate/README.md` + `CHANGELOG.md`; `claude-md-routing.txt` untouched

The routing block teaches *when to delegate*, not CLI reference; adding `--version` there would force a sha256 pin regeneration (install-time hash gate) for zero routing value. Deferred until a routing-relevant change needs the pin anyway.

## Data model changes

None (no Firestore/GCS — local CLIs).

## API changes

New CLI surface only: `--version` / `-V` on `adlc-read`, `adlc-write`, `extract-chat`.

## Additions proposed to .adlc/context/architecture.md

None — the change fits the existing "tools are stdlib-light, guards before network" posture already documented.

## Applicable lessons

- LESSON-392 — probe shares the real resolver (`resolve_provider()`, not a re-implementation).
- LESSON-022 / BUG-056 — no eager `openai` import; `--version` path never calls `get_client()`; clean-venv test required.
- LESSON-395 — fail-soft `config_error:`, never a traceback; version prints even when config is broken.
- LESSON-397 — VERSION resolves from script location (through the ~/bin wrapper exec), never caller cwd; foreign-cwd test required.
- LESSON-329 — tests spawn the CLIs via subprocess (the `test_cli_warn.py:45-52` pattern), asserting positively on output content, not just exit code.
