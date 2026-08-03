---
id: TASK-084
title: "Tests for --version (incl. clean-venv + foreign-cwd) and docs"
status: draft
parent: REQ-553
created: 2026-08-03
updated: 2026-08-03
dependencies: ["TASK-083"]
repo: adlc-toolkit
---

## Description

Add `tools/delegate/tests/test_version.py` covering every REQ-553 acceptance criterion (subprocess invocation per LESSON-329), and document the flag in `tools/delegate/README.md` + `CHANGELOG.md` (ADR-4: `claude-md-routing.txt` deliberately untouched).

## Files to Create/Modify

- `tools/delegate/tests/test_version.py` — new test module; follow the `subprocess.run([sys.executable, SCRIPT, ...])` pattern from `test_cli_warn.py:45-52` and the `clean_env`/`_write_config` fixtures style from `test_resolve_provider.py:24-37`
- `tools/delegate/README.md` — document `--version` for all three CLIs incl. the BR-9 output contract
- `CHANGELOG.md` — entry under the unreleased/current section for the new flag

## Acceptance Criteria

- [ ] Test: version line equals `adlc-toolkit ` + repo `VERSION` content for all three CLIs, exit 0
- [ ] Test: `adlc-write --version` with no other args and `extract-chat --version` with no positional both exit 0
- [ ] Test: config lines parse as `key: value` and the key set is exactly `{base_url, model, api_key_env, enabled}` on the happy path (BR-9 AC)
- [ ] Test: `ADLC_DELEGATE_MODEL`/`ADLC_DELEGATE_BASE_URL` overrides appear in output
- [ ] Test: with `MOONSHOT_API_KEY=sk-test-secret-value` in the subprocess env, output contains `MOONSHOT_API_KEY` (positive) and NOT `sk-test-secret-value` (negative)
- [ ] Test: malformed/key-in-config config file → exit 0, version line present, `config_error:` line present, no traceback in stderr
- [ ] Test: clean venv without `openai` — simulate via a subprocess env/sys.path that hides `openai` (e.g. `PYTHONPATH` shim dir with a raising `openai.py` is NOT enough since import must not happen at all: assert by scrubbing site-packages via `-S`/isolated mode or asserting `openai` absent from loaded modules is impractical cross-process — instead run with `PYTHONNOUSERSITE=1` and a stub-free venv python if available, else mark the strategy used in a comment and at minimum assert exit 0 with `-I` isolated mode) (BR-4, LESSON-022)
- [ ] Test: run from a foreign cwd (`tmp_path`) — version still reports the toolkit VERSION (LESSON-397)
- [ ] `test_no_kimi_brand.py` and the full `tools/delegate/tests/` suite pass
- [ ] Docs updated in both files; no change to `claude-md-routing.txt` / `.sha256`

## Technical Notes

- `python -I` (isolated mode) won't hide an installed `openai` in the venv running tests; the practical BR-4 assertion is: version path must not import `openai` — verify with `python -X importtime` output grep, or run the CLI under the system `python3` (no openai installed) when available. Prefer: `subprocess.run([sys.executable, "-c", "import sys; sys.modules['openai']=None; ..."])` is invasive — simplest robust check: run the CLI with a `sitecustomize`-free env and assert success PLUS grep the CLI source in the test to assert the version branch precedes any `get_client`/`resolve_key` call. Document the chosen strategy in the test.
- extract-chat's version branch imports `_common` lazily — foreign-cwd test also covers the sys.path insert correctness.
