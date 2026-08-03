---
id: REQ-553
title: "Add --version flag to the delegation CLIs (adlc-read, adlc-write, extract-chat)"
status: complete
deployable: true
created: 2026-08-03
updated: 2026-08-03
component: "adlc/delegation"
domain: "adlc"
stack: ["python", "shell"]
concerns: ["configurability", "observability", "privacy"]
tags: ["delegation", "cli", "version", "config", "provider-neutral"]
---

## Description

The three delegation CLIs (`adlc-read`, `adlc-write`, `extract-chat`) currently expose no way to ask "what version of the toolkit am I running, and what delegate am I actually configured to talk to?" Since REQ-515/REQ-522 the delegate provider is fully configurable (CLI flags > `ADLC_DELEGATE_*` env > config file > legacy key-env continuity > shipped defaults), which means two installs can behave differently with no visible signal as to why. When a delegation call misbehaves, the first diagnostic question — "which base URL / model / key env is this actually resolving to?" — currently requires reading `~/.claude/adlc/config.yml`, the environment, and `_common.py` by hand.

This REQ adds a `--version` flag to all three CLIs. It prints the toolkit version, and for the two delegate-calling CLIs (`adlc-read`, `adlc-write`) additionally prints the *resolved* delegate configuration: base URL, model name, and the **name** of the env var holding the API key — never the key value. This gives adopters and bug reports a one-command provenance snapshot, and gives `adlc doctor`-style triage a stable primitive.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| VersionReport | toolkit_version | string | from repo-root `VERSION` file, resolved relative to the CLI script's own location (toolkit asset, not caller cwd) |
| VersionReport | base_url | string | resolved via the same provider-resolution path real calls use; `adlc-read`/`adlc-write` only |
| VersionReport | model | string | same resolution path; `adlc-read`/`adlc-write` only |
| VersionReport | api_key_env | string | the env var NAME only; the value must never be read or printed |
| VersionReport | enabled | boolean | delegation opt-in state, same predicate the gate uses |

### Events

_None — `--version` is a pure read/print path with no side effects, no network, no telemetry._

### Permissions

_Not applicable — local CLI, no auth surface._

## Business Rules

- [ ] BR-1: `adlc-read --version`, `adlc-write --version`, and `extract-chat --version` each print the toolkit version and exit 0, before any other processing (privacy notice, path validation, API-key checks, delegation gating).
- [ ] BR-2: `adlc-read --version` and `adlc-write --version` additionally print the resolved delegate configuration: base URL, model name, `api_key_env` NAME, and enabled/disabled state. The API key **value** must never be read, printed, or partially printed (no redacted previews). (informed by BUG-056, REQ-522)
- [ ] BR-3: The configuration shown must be produced by the **same resolution path** real delegate calls use (the existing provider resolver in `_common.py`), not a re-implementation — a probe that resolves differently from the real call is a rotted guard. (informed by LESSON-392)
- [ ] BR-4: `--version` must work on a machine with no `openai` SDK installed, no API key set, and no config file present — no eager imports, no network I/O. Verification must run in a clean venv without the SDK. (informed by LESSON-022, BUG-056, LESSON-395)
- [ ] BR-5: The toolkit version is read from the repo-root `VERSION` file resolved relative to the script's own location (toolkit asset → script-derived root), never from the caller's cwd. (informed by LESSON-397)
- [ ] BR-6: If provider resolution fails (malformed config file, unreadable file), `--version` still prints the toolkit version and reports the resolution error as a diagnostic line — it must never crash with a traceback. (informed by LESSON-395)
- [ ] BR-7: Output goes to stdout; `--version` composes with `--no-warn` trivially (the privacy notice is skipped anyway since no delegation occurs); exit status is 0 on success.
- [ ] BR-8: No Kimi-branded strings in the new output or code — provider identity comes from the resolved config values only. (informed by REQ-522)
- [ ] BR-9: Output is a stable, machine-parseable set of `key: value` lines (first line: `adlc-toolkit <version>`; config lines keyed `base_url`, `model`, `api_key_env`, `enabled`, plus `config_error` on BR-6's diagnostic path) so `adlc doctor` can consume it later without re-parsing prose.

## Acceptance Criteria

- [ ] `adlc-read --version` prints a version line matching the repo `VERSION` file content and exits 0.
- [ ] `adlc-write --version` and `extract-chat --version` behave the same for the version line.
- [ ] `adlc-read --version` output includes base URL, model, and `api_key_env` name matching what a real call would resolve (verified by a test that sets `ADLC_DELEGATE_MODEL`/`ADLC_DELEGATE_BASE_URL` overrides and asserts they appear).
- [ ] With `MOONSHOT_API_KEY=sk-test-secret-value` set, the string `sk-test-secret-value` does not appear anywhere in `--version` output (positive assertion on the env-var NAME appearing, negative on the value).
- [ ] In a venv without `openai` installed, all three `--version` invocations succeed (exit 0, no traceback). (informed by LESSON-022)
- [ ] With a config file that `resolve_provider` REFUSES (key-shaped `api_key_env`), `--version` exits 0, prints the version, and prints a one-line `config_error:` diagnostic; with an unparseable config file it exits 0 and reports the shipped defaults (fail-soft, matching the real call's resolution). (informed by LESSON-395)
- [ ] `tools/delegate/tests/` gains tests covering the above; `test_no_kimi_brand.py` still passes.
- [ ] Invoked from a foreign project directory (not the toolkit repo), `--version` reports the toolkit's version, not anything derived from the caller's cwd. (informed by LESSON-397)
- [ ] `adlc-read --version` output parses as `key: value` lines carrying exactly the BR-9 keys (a test splits each config line on the first `:` and asserts the expected key set).

## External Dependencies

- None — stdlib only. Reuses the existing provider resolver in `tools/delegate/_common.py`.

## Assumptions

- The repo-root `VERSION` file exists and is the single source of truth for the toolkit version (project-overview says VERSION/CHANGELOG are authoritative).
- The `~/bin` wrappers exec the canonical-repo scripts (install.sh path-stamps them), so script-relative `VERSION` resolution works through the wrapper indirection.
- `extract-chat` has no delegate config, so its `--version` output is the version line only.

## Open Questions

- None — resolved before implementation: output format is fixed by BR-9; printing the `openai` package version is out of scope (left to `adlc doctor`).

## Out of Scope

- A `--version` flag for the `adlc` CLI or `adlc doctor` integration (separate surface; can build on this later).
- Printing the installed `openai` SDK version (belongs in `adlc doctor`, which owns environment diagnostics).
- Semver bumping policy or automating `VERSION` file updates.
- Any change to delegation behavior, gating, or telemetry — `--version` emits no telemetry because it performs no delegation.
- Printing or validating API key values in any form.

## Retrieved Context

- LESSON-392 (lesson, score 5): An "is it enabled?" probe must run the same resolution path as the real call
- LESSON-393 (lesson, score 5): Escape-hatch validators must enforce every documented constraint
- LESSON-394 (lesson, score 5): Non-uniform defaults cannot collapse to the class map
- LESSON-334 (lesson, score 5): Kimi delegation "api-error" is a catch-all that hides local path/budget failures
- LESSON-019 (lesson, score 5): Presence guards rot when the thing they guard moves behind indirection
- LESSON-020 (lesson, score 5): Cross-block shell state and guard rot — shared functions must be sourced partials
- LESSON-008 (lesson, score 5): Skill delegation output is untrusted data; citation sanitization required
- LESSON-402 (lesson, score 4): Status/degraded flags travel on stdout, not env
- BUG-080 (bug, score 4): ask-kimi aborted the whole batch on any one unreadable --paths entry
- LESSON-022 (lesson, score 4): Eager imports bypass pre-API guards
- BUG-056 (bug, score 4): Eager top-level `import openai` defeated pre-API guards
- LESSON-012 (lesson, score 4): Structural telemetry beats prose enforcement
- LESSON-395 (lesson, score 3): Bootstrap diagnostics must be dependency-free
- LESSON-397 (lesson, score 3): Artifact tools resolve root from caller cwd; toolkit assets from script location
- LESSON-398 (lesson, score 3): Data-driven registries make concurrent additions mechanical
