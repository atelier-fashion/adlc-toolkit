---
id: REQ-515
title: "Provider-Agnostic Delegation Layer — de-Kimi the Tooling"
status: approved
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "tools/kimi"
domain: "adlc"
stack: ["python", "bash", "markdown", "openai-sdk"]
concerns: ["configurability", "portability", "cost"]
tags: ["kimi", "delegation", "model-config", "provider-agnostic", "rename", "config-file"]
---

## Description

The token-saving delegation layer (`ask-kimi`, `kimi-write`, `extract-chat`, the
`kimi-gate.sh`/`kimi-tools-path.sh` partials, the `kimi-pre-pass` agent, and the
CLAUDE.md routing text) is branded around one provider — Moonshot's Kimi K2.5 —
even though the tools already speak the generic OpenAI-compatible chat API and the
provider is fully described by three values: base URL, model name, API key. A new
adopter of the toolkit who wants to delegate bulk I/O to a different model (Ollama,
Groq, DeepSeek, an Anthropic Haiku key via the OpenAI-compat endpoint, etc.) today
has to fork ~240 live references across tools, partials, skills, the sprint
workflow, one agent, and lint fixtures.

This REQ makes the delegation layer provider-agnostic: provider-neutral tool names,
a single user-editable config file for endpoint/model/key resolution, generalized
gate partials, and rewritten routing prose — while preserving full backward
compatibility for the existing Kimi setup (names, env vars, telemetry shape).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| DelegateConfig | base_url | string | required when config present; any OpenAI-compatible endpoint |
| DelegateConfig | model | string | required when config present |
| DelegateConfig | api_key_env | string | name of env var holding the key; the key itself is NEVER stored in the file |
| DelegateConfig (file) | — | YAML at `~/.claude/adlc/config.yml` (proposed — see OQ-1) | overridable via `ADLC_CONFIG` env var; absent file is valid (legacy/env path) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| telemetry record | each gated skill step (unchanged) | skill, step, req, gate_result, mode, reason, duration_ms — schema unchanged |

## Business Rules

- [ ] BR-1: Tools are renamed to provider-neutral commands — `adlc-read` (was `ask-kimi`), `adlc-write` (was `kimi-write`); `extract-chat` keeps its name. The old names remain as shims (symlink or exec-wrapper) with identical CLIs, so existing muscle memory and any external scripts keep working.
- [ ] BR-2: Provider resolution precedence is, strictly: CLI flags (`--model`, `--base-url`) > `ADLC_DELEGATE_*` env vars > config file > legacy env vars (`KIMI_MODEL`, `KIMI_API_KEY`) > shipped defaults (current Moonshot/Kimi values). A user with today's setup and no config file sees zero behavior change.
- [ ] BR-3: The config file stores `api_key_env` (the *name* of an env var), never a key value. If a key-looking value (high-entropy string) is found in the config, the tools refuse with an actionable error. (informed by LESSON-007, LESSON-008)
- [ ] BR-4: The gate partial is generalized (`delegate-gate.sh`, gating on `command -v adlc-read` plus config resolvability) and the old `kimi-gate.sh` becomes a thin source-through wrapper so existing SKILL.md source-lines keep working. `ADLC_DISABLE_KIMI=1` remains honored as an alias of the new `ADLC_DISABLE_DELEGATE=1`. Presence guards in `lint-skills` are updated in the same change to follow the new indirection. (informed by LESSON-019, LESSON-020)
- [ ] BR-5: Telemetry schema, emit points, ghost-skip detection, and `check-delegation.sh` semantics are unchanged; only naming-internal strings may change, and any rename keeps old records readable. (informed by LESSON-012)
- [ ] BR-6: All live consumers are updated in one change: `analyze`, `spec`, `proceed`, `wrapup` SKILL.md files; `workflows/adlc-sprint.workflow.js`; the `kimi-pre-pass` agent (renamed `delegate-pre-pass`, with a deprecation note in the old file or a registry alias); `lint-skills` checks and fixtures; `tools/kimi/README.md`. Sibling skills are audited for stragglers with a corpus grep before merge. (informed by LESSON-005)
- [ ] BR-7: `claude-md-routing.txt` is rewritten provider-neutral ("Claude = thinking, the delegate = I/O"), parameterized by the configured tool names, so new installs do not inherit Kimi-specific prose.
- [ ] BR-8: The installer remains fail-loud and atomic (backup, temp-write, `mv`/`os.replace`), and all new/changed shell is BSD- and zsh-safe (no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` array indexing, no `status=` variable, no unmatched globs). (informed by LESSON-006, LESSON-013, LESSON-329, LESSON-335)
- [ ] BR-9: Batch path validation keeps skip-and-continue semantics: unreadable `--paths` entries warn to stderr and are skipped; exit is non-zero only when zero readable files remain. (informed by BUG-080, LESSON-334)
- [ ] BR-10: Delegated-model output remains untrusted data regardless of provider: delimiter wrapping, citation sanitization, and coverage reconciliation language in skills is provider-neutralized but not weakened. (informed by LESSON-008, LESSON-010)
- [ ] BR-11: Data-governance posture — delegation is **disabled by default on fresh installs**. The config file must contain an explicit `enabled: true` under `delegate:` before any tool will send file contents to an external endpoint; absent config (or `enabled` absent/false), the gate returns the disabled path and skills use their existing fallback. Opt-in is satisfied by exactly two signals: `enabled: true` in the config file, OR `ADLC_DELEGATE_ENABLED=1` in the environment (so pure-env setups remain possible without a config file — setting `ADLC_DELEGATE_BASE_URL`/`_MODEL` alone is NOT opt-in). Exception for continuity: when legacy `KIMI_API_KEY` is already set in the environment (today's installs), delegation remains enabled as before — the opt-in requirement applies to the new configuration paths that adopters use. The installer and README state plainly that delegation transmits source content to the configured third-party endpoint and that company approval is the adopter's responsibility.

## Acceptance Criteria

- [ ] With only a config file pointing at a non-Moonshot OpenAI-compatible endpoint (no `KIMI_*` env vars), `adlc-read --paths <file> --question "..."` succeeds against that endpoint.
- [ ] With today's setup untouched (no config file, `KIMI_API_KEY`/`KIMI_MODEL` in env), `ask-kimi` and `kimi-write` behave byte-identically to current behavior, and all four delegating skills pass their gates.
- [ ] `ADLC_DISABLE_DELEGATE=1` and legacy `ADLC_DISABLE_KIMI=1` both produce the disabled-path fallback in all four skills.
- [ ] `lint-skills` passes on the full corpus after the rename; no live file (skills, partials, workflow, agents, lint fixtures) greps for `ask-kimi`/`kimi-write` except shims, wrappers, and back-compat code paths that are explicitly labeled as such.
- [ ] Telemetry records emitted before and after the change are processable by the same `check-delegation.sh`.
- [ ] Existing pytest suite under `tools/kimi/tests/` passes (updated for new names), plus new tests covering: precedence order (BR-2), key-in-config refusal (BR-3), and shim equivalence (BR-1).
- [ ] Tool stderr/privacy behavior unchanged: basename-only path disclosure and base64/credential redaction still applied at every leak point. (informed by LESSON-007)
- [ ] Fresh-install posture: with a config file present but no `enabled: true` and no legacy `KIMI_API_KEY` in env, every delegating skill takes the disabled-path fallback and no network call is attempted (BR-11).
- [ ] Env-only posture: `ADLC_DELEGATE_BASE_URL`/`_MODEL` set without `ADLC_DELEGATE_ENABLED=1` (and no config, no legacy key) stays disabled; adding `ADLC_DELEGATE_ENABLED=1` enables it (BR-11).
- [ ] Linux parity: the pytest suite and the gate/telemetry partials pass under Ubuntu bash (CI job or documented manual run); launchctl-specific installer steps are skipped with a notice, not a failure, on Linux.

## External Dependencies

- None new. The OpenAI Python SDK already in the venv covers all OpenAI-compatible endpoints.

## Assumptions

- OpenAI-compatible chat-completions endpoints cover the practical provider space (Moonshot, Ollama, Groq, DeepSeek, Anthropic's OpenAI-compat surface). Providers without such an endpoint are out of scope.
- The directory rename `tools/kimi/` → `tools/delegate/` is desirable but may be staged: code-level neutrality first, directory rename second, to keep the diff reviewable. Architecture phase decides.

## Open Questions

- [ ] Config location: `~/.claude/adlc/config.yml` (proposed, co-located with the venv and counters already under `~/.claude/`) vs XDG `~/.config/adlc/`. Proposed default is `~/.claude/adlc/config.yml` with `ADLC_CONFIG` override.
- [ ] Should `delegate-pre-pass` keep a `kimi-pre-pass` alias agent file, or is the sprint workflow the only consumer (making a hard rename safe)?
- [ ] YAML parsing in shell partials: the gate only needs "config resolves" — is a Python one-liner via the existing venv acceptable in the partial, or should the gate stay purely `command -v` based?

## Out of Scope

- Claude-side agent model tiers (REQ-516).
- Any change to *when* skills delegate (the four delegating skills and their gates keep their current trigger logic).
- Multi-provider routing (different providers per skill); one configured delegate per machine.
- Native (non-OpenAI-compatible) provider SDKs.

## Retrieved Context

- LESSON-019 (lesson, score 6): presence guards rot when indirection moves
- LESSON-020 (lesson, score 6): cross-block shell state and guard rot
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure
- LESSON-011 (lesson, score 6): launchctl env inheritance and rc-fallback
- LESSON-008 (lesson, score 6): skill delegation untrusted data and citation sanitization
- LESSON-335 (lesson, score 5): zsh-executor and arg-templating hazards
- LESSON-329 (lesson, score 5): dogfood skills under executor shell
- LESSON-010 (lesson, score 5): delegated-model silent truncation and advisory anchoring
- LESSON-012 (lesson, score 5): structural telemetry beats prose enforcement
- LESSON-007 (lesson, score 5): base64 regex whitespace and privacy of paths
- LESSON-006 (lesson, score 5): tools dir carve-out and fail-loud installers
- LESSON-334 (lesson, score 4): kimi api-error label hides local path failures
- BUG-080 (bug, score 4): ask-kimi all-or-nothing path validation
- LESSON-313 (lesson, score 4): global counter scope is its scan root
- LESSON-023 (lesson, score 4): mirror the rationale not just mechanism
