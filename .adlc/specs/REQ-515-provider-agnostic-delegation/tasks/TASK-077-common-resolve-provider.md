---
id: TASK-077
title: "Provider resolution cascade + config parser + key-in-config refusal in _common.py"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: []
---

## Description

Add the single provider-resolution seam to `tools/kimi/_common.py`. This is the
foundation every other task builds on. Implements BR-2 (precedence), BR-3
(key-in-config refusal), BR-11 (opt-in posture), and the config-file parsing
from ADR-2/ADR-3/ADR-4. Preserves byte-identical Moonshot defaults so a
no-config install is unchanged.

## Files to Create/Modify

- `tools/kimi/_common.py` — add `resolve_provider()`, a minimal flat-`key: value`
  config parser for the `delegate:` block, `_looks_like_key()` guard, and
  `delegation_enabled()`. Refactor `get_client`/`get_model`/`emit_exfil_notice`
  to consume the resolved struct. Keep the rc-file key fallback for the Moonshot
  var (LESSON-011). Keep lazy `openai` import.

## Acceptance Criteria

- [ ] `resolve_provider(args_model=None, args_base_url=None)` returns a struct with
      `base_url, model, api_key_env, api_key, enabled, source`.
- [ ] Precedence is strictly: CLI flags > `ADLC_DELEGATE_*` env > config file >
      legacy env (`KIMI_MODEL`, `MOONSHOT_API_KEY`/`KIMI_API_KEY`) > shipped
      Moonshot defaults (BR-2).
- [ ] Config read from `$ADLC_CONFIG` or `~/.claude/adlc/config.yml`; absent file
      is valid (legacy/env path). Parser reads only `enabled/base_url/model/
      api_key_env` under `delegate:`; ignores unknown keys; no PyYAML dependency.
- [ ] `api_key_env` holds the NAME of an env var; the key value is read from
      `os.environ[that name]`, never stored. A high-entropy / non-env-var-name
      value under `delegate:` triggers a `SystemExit` with an actionable message
      (BR-3). The check runs before any network call.
- [ ] Opt-in (BR-11): `delegation_enabled()` true iff `delegate.enabled: true` OR
      `ADLC_DELEGATE_ENABLED=1` OR legacy `KIMI_API_KEY`/`MOONSHOT_API_KEY` set in
      env. Setting only `ADLC_DELEGATE_BASE_URL`/`_MODEL` is NOT opt-in.
- [ ] With no config and `MOONSHOT_API_KEY` set, resolution yields the exact
      current defaults (`https://api.moonshot.ai/v1`, `kimi-k2.5`,
      `MOONSHOT_API_KEY`) — byte-identical behavior.
- [ ] `emit_exfil_notice` mentions the resolved model and the two suppression
      mechanisms; never interpolates the key/var-name value.

## Technical Notes

- Hand-rolled YAML: read lines, find the `delegate:` block (a top-level key whose
  value is a mapping), collect indented `key: value` pairs until dedent. Strip
  quotes and inline comments. Treat `enabled: true/yes/1` as true.
- `_looks_like_key()`: reject `^[A-Za-z_][A-Za-z0-9_]*$`-failing strings AND
  strings matching `sk-…|AKIA…|ghp_…|Bearer …` or a ≥32-char mixed-class run.
- Keep `_API_KEY_VAR`/`_BASE_URL`/`_DEFAULT_MODEL` module constants as the
  shipped defaults; the resolver references them.
- POSIX/portable; no new imports beyond stdlib (`os`, `sys`, `re`).
