---
id: REQ-515
title: "Architecture — Provider-Agnostic Delegation Layer"
status: approved
created: 2026-06-11
updated: 2026-06-11
---

## Overview

REQ-515 de-brands the token-saving delegation layer from "Kimi/Moonshot" to a
provider-neutral surface while preserving byte-identical behavior for today's
installs. The change is concentrated in `tools/kimi/_common.py` (the only place
provider values are resolved), the two gate/path partials, the four delegating
SKILL.md files, the sprint workflow, one agent, the `lint-skills` checker + its
fixtures, and the README/routing prose. New provider-neutral CLIs (`adlc-read`,
`adlc-write`) are added as the primary names; the old `ask-kimi`/`kimi-write`
names survive as exec-shims.

The governing constraint is **backward compatibility**: a machine with today's
setup (`KIMI_API_KEY`/`MOONSHOT_API_KEY` in env, no config file) must see zero
behavior change, and all existing telemetry, gate semantics, and skill
source-lines must keep working unchanged.

## Key Decisions (ADRs)

### ADR-1 — Centralize provider resolution in `_common.py`; keep the directory named `tools/kimi/` (staged rename deferred)

The spec's Assumption explicitly permits staging: "code-level neutrality first,
directory rename second." We do exactly that. **This REQ does NOT rename the
`tools/kimi/` directory.** Reasons:

1. The directory path is hardcoded in ~6 partials/skill source-lines
   (`tools/kimi/emit-telemetry.sh`, the `KIMI_TOOLS` resolver, lint canonical
   literals) and in `install.sh`'s `$REPO_ROOT/tools/kimi/...` wrapper stamping.
   Renaming the directory in the same change as the provider-neutralization
   doubles the diff and the back-compat surface for no functional gain.
2. A directory rename is a pure follow-up (mechanical `git mv` + path updates)
   that can land as its own reviewable REQ once the code-level neutrality is
   proven. Captured as a follow-up, not done here.

All provider-specific values (`base_url`, `model`, `api_key_env`) are resolved
in one place: a new `resolve_provider()` in `_common.py`. Every CLI calls it.
This is the single seam the rest of the architecture hangs off.

### ADR-2 — Resolution precedence (BR-2), implemented as an ordered cascade in `resolve_provider()`

Strict precedence, highest wins:

1. CLI flags: `--model`, `--base-url` (per-field; a flag overrides only its field)
2. `ADLC_DELEGATE_*` env vars: `ADLC_DELEGATE_MODEL`, `ADLC_DELEGATE_BASE_URL`,
   `ADLC_DELEGATE_API_KEY_ENV`
3. Config file (`~/.claude/adlc/config.yml`, override via `ADLC_CONFIG`): the
   `delegate:` block's `base_url`, `model`, `api_key_env`
4. Legacy env vars: `KIMI_MODEL` (model), and for the key the existing
   `MOONSHOT_API_KEY` resolution (env → rc-file fallback). `KIMI_API_KEY` is
   accepted as an alias for `MOONSHOT_API_KEY` if present.
5. Shipped defaults: `base_url=https://api.moonshot.ai/v1`, `model=kimi-k2.5`,
   `api_key_env=MOONSHOT_API_KEY` (today's exact values — so a no-config install
   is byte-identical).

The resolver returns a small struct `{base_url, model, api_key_env, api_key,
enabled, source}`. `api_key` is resolved last from the env var **named by**
`api_key_env` (never stored), falling back to the existing rc-file reader for
the Moonshot var only (preserving the launchctl-propagation defense, LESSON-011).

### ADR-3 — Config file is YAML at `~/.claude/adlc/config.yml`, parsed in Python only (OQ-1, OQ-3 resolved)

OQ-1 (location): use `~/.claude/adlc/config.yml` (co-located with the venv and
counters already under `~/.claude/`), overridable via `ADLC_CONFIG`. This matches
the proposal and avoids introducing an XDG dependency.

OQ-3 (shell YAML parsing): the gate partial does **not** parse YAML in shell. The
gate's job is only "is delegation available AND enabled?" — answered by
`command -v adlc-read` + an opt-in check that does not require reading the config
body (see ADR-5). Full config parsing happens exclusively in Python
(`_common.py`), using a **minimal hand-rolled flat-`key: value` parser** under the
`delegate:` block — NOT PyYAML (not in `requirements.txt`, and we will not add a
dependency for three scalar fields). The parser reads only the keys it knows
(`enabled`, `base_url`, `model`, `api_key_env`) and ignores everything else.

Schema (`~/.claude/adlc/config.yml`):

```yaml
delegate:
  enabled: true                      # BR-11 opt-in; absent/false => disabled
  base_url: "https://api.example/v1"
  model: "some-model"
  api_key_env: "MY_PROVIDER_KEY"     # NAME of the env var, never the key
```

### ADR-4 — Key-in-config refusal (BR-3)

If `api_key_env`'s value (or any scalar under `delegate:`) looks like a key — a
high-entropy token matching the same families the redaction chain knows
(`sk-…`, `AKIA…`, `ghp_…`, a long base64-ish run ≥ 32 chars with mixed classes),
or simply does not look like a valid env-var **name** (`^[A-Za-z_][A-Za-z0-9_]*$`)
— the tools refuse with an actionable error: "config `delegate.api_key_env` must
be the NAME of an env var, not a key value." This fires before any network call.

### ADR-5 — Generalized gate partial `delegate-gate.sh`; `kimi-gate.sh` becomes a source-through wrapper (BR-4)

New `partials/delegate-gate.sh` exports `adlc_delegate_gate_check()` with the
**same 0/1/2 return-code contract** and an exported `ADLC_DELEGATE_GATE_REASON`.
Return codes:

- `2` unavailable: `adlc-read` not on PATH (note: the OLD gate checked `ask-kimi`;
  since `ask-kimi` is now a shim that also lands on PATH, both resolve — but the
  canonical probe is `adlc-read`).
- `1` disabled: `ADLC_DISABLE_DELEGATE=1` OR legacy `ADLC_DISABLE_KIMI=1` (alias).
  **Also** disabled when opt-in is not satisfied (BR-11): opt-in =
  `delegate.enabled: true` in config OR `ADLC_DELEGATE_ENABLED=1` in env OR the
  continuity exception (`KIMI_API_KEY`/`MOONSHOT_API_KEY` already set in env).
- `0` delegated: available, not disabled, opt-in satisfied.

`partials/kimi-gate.sh` is rewritten to a thin wrapper that sources
`delegate-gate.sh` and defines `adlc_kimi_gate_check()` as a call-through that
maps the new reason onto the old `ADLC_KIMI_GATE_REASON` values (`ok` /
`disabled-via-env` / `no-binary`) so every existing SKILL.md source-line and the
telemetry resolution block keep working unchanged. `kimi-tools-path.sh` similarly
gets a `delegate-tools-path.sh` canonical with `kimi-tools-path.sh` as a
wrapper exporting both `$DELEGATE_TOOLS` and the legacy `$KIMI_TOOLS`.

The opt-in / disabled distinction is collapsed into return code `1` deliberately:
the existing callers' `case` statements already treat `1` as "disabled path →
fallback," so BR-11's fresh-install-disabled posture rides the existing
disabled branch with no SKILL.md change. The exported reason distinguishes
`disabled-via-env` vs `not-opted-in` for telemetry fidelity.

### ADR-6 — Tool rename via new entrypoints + exec-shims (BR-1)

- New `tools/kimi/adlc-read` (was `ask-kimi`) and `tools/kimi/adlc-write` (was
  `kimi-write`) become the real CLIs. To avoid duplicating logic, the rename is a
  `git mv` of `ask-kimi`→`adlc-read` and `kimi-write`→`adlc-write`, with the
  internal `prog=` / docstrings neutralized.
- The OLD names become 2-line exec-shims: `exec "$(dirname "$0")/adlc-read" "$@"`.
  Identical CLI, identical behavior. `extract-chat` keeps its name unchanged.
- `install.sh`'s `CLIS` list becomes `adlc-read adlc-write extract-chat` PLUS it
  writes shim wrappers for `ask-kimi`/`kimi-write` in `~/bin` too, and the
  settings.json allowlist merges BOTH new and old `Bash(...)` entries.

### ADR-7 — Telemetry unchanged (BR-5)

`emit-telemetry.sh`, `skill-flag.sh`, `check-delegation.sh`, the telemetry
record schema, emit points, and ghost-skip detection are **not touched**
functionally. Only header comments may be neutralized. Old and new records share
one schema, so `check-delegation.sh` processes both. The `$KIMI_TOOLS` variable
name persists (exported by both the wrapper and the new canonical) so no emit
call site changes.

### ADR-8 — Agent rename with alias (BR-6)

`agents/kimi-pre-pass.md` → `agents/delegate-pre-pass.md` (git mv, body
neutralized: "Kimi" → "the delegate", `ask-kimi` → `adlc-read`, `MOONSHOT_API_KEY`
→ resolved-key check). The sprint workflow's `agentType: 'kimi-pre-pass'` string
is updated to `'delegate-pre-pass'`. Because the workflow is the only consumer
(OQ-2), a hard rename is safe — but we leave a one-line deprecation stub at
`agents/kimi-pre-pass.md`? No: there is no agent registry that resolves by
filename for back-compat, and the only caller is updated in the same change, so a
hard rename with NO stub is correct and keeps the corpus clean. (OQ-2 resolved:
no alias agent file.)

### ADR-9 — Lint-skills follows the new indirection (BR-4)

`tools/lint-skills/check.py`:
- `KIMI_GATE_ANCHOR` gains a second anchor: the canonical check fires when EITHER
  `ADLC_DISABLE_KIMI` OR `ADLC_DISABLE_DELEGATE` appears (so neutralized skills
  using the new spelling are still guarded).
- `CANONICAL_LITERALS` source-lines accept either the `kimi-gate.sh`/`kimi-tools-
  path.sh` spelling OR the new `delegate-gate.sh`/`delegate-tools-path.sh`
  spelling (an OR per logical literal, not a hard replacement — both the wrapper
  and canonical spellings are valid).
- Fixtures under `tools/lint-skills/tests/fixtures/` are updated/added so the
  test suite exercises the new spellings and still passes for the old.

### ADR-10 — Untrusted-data posture preserved, neutralized (BR-10)

Delimiter wrapping, citation sanitization, and the `--- BEGIN/END … PROPOSAL
(untrusted) ---` language in the skills are reworded provider-neutral ("the
delegate") but the security mechanism (path regex, `..` rejection, description
sanitization, `path ∈ changedFiles`) is byte-for-byte preserved.

## Component Map (live consumers — BR-6)

| File | Change |
|------|--------|
| `tools/kimi/_common.py` | add `resolve_provider()` cascade, config parser, key-in-config refusal; neutralize `get_client`/`get_model`/`emit_exfil_notice`; keep Moonshot defaults |
| `tools/kimi/ask-kimi` → `adlc-read` | git mv + neutralize prog/docstring; `ask-kimi` becomes exec-shim |
| `tools/kimi/kimi-write` → `adlc-write` | git mv + neutralize; `kimi-write` becomes exec-shim |
| `tools/kimi/extract-chat` | unchanged (name kept); minor comment neutralization only if present |
| `tools/kimi/install.sh` | CLIS list, shim wrappers, allowlist (old+new), reminder text neutralized; routing block marker kept for back-compat |
| `tools/kimi/claude-md-routing.txt` (+`.sha256`) | rewritten provider-neutral, parameterized tool names; sha256 regenerated |
| `tools/kimi/README.md` | rewritten provider-neutral with config-file section |
| `tools/kimi/emit-telemetry.sh` | comment neutralization only (no behavior change) |
| `partials/delegate-gate.sh` (new) + `partials/kimi-gate.sh` (wrapper) | ADR-5 |
| `partials/delegate-tools-path.sh` (new) + `partials/kimi-tools-path.sh` (wrapper) | ADR-5 |
| `partials/kimi-gate.md`, `partials/README.md`, `partials/emit-step-telemetry.md` | doc neutralization |
| `agents/kimi-pre-pass.md` → `agents/delegate-pre-pass.md` | ADR-8 |
| `workflows/adlc-sprint.workflow.js` | `agentType` string, prompt text, comments neutralized |
| `analyze/SKILL.md`, `spec/SKILL.md`, `proceed/SKILL.md`, `wrapup/SKILL.md` | neutralize prose; source-lines unchanged (wrappers keep them valid) |
| `tools/lint-skills/check.py` + fixtures | ADR-9 |
| `tools/kimi/tests/*` | rename-aware updates + new tests (precedence, key refusal, shim equivalence, opt-in posture) |
| `.adlc/context/conventions.md` | update "Kimi delegation pattern" section to provider-neutral |

**Out of scope / NOT touched**: historical `.adlc/specs/REQ-4xx/*`, lessons,
bugs — immutable history. `~/.claude/CLAUDE.md` routing prose for the *current
machine* is the user's installed copy (the routing `.txt` is the template; a
re-run of `install.sh` re-appends — not in this REQ's diff).

## Backward-Compatibility Invariants (test these)

1. No config file + `MOONSHOT_API_KEY` set → `ask-kimi` and `adlc-read` behave
   identically and identically to today (default Moonshot endpoint/model).
2. `ADLC_DISABLE_KIMI=1` and `ADLC_DISABLE_DELEGATE=1` both → disabled path.
3. Telemetry records pre/post change both parse in `check-delegation.sh`.
4. `$KIMI_TOOLS` still resolves; all 4 skills' source-lines still satisfy lint.
5. Fresh install (config present, no `enabled: true`, no legacy key) → disabled,
   no network call.
6. Env-only opt-in: `ADLC_DELEGATE_BASE_URL/_MODEL` alone → disabled; add
   `ADLC_DELEGATE_ENABLED=1` → enabled.

## Test Plan

- Extend `tools/kimi/tests/test_common.py` (or a new `test_resolve_provider.py`)
  for the precedence cascade (BR-2), config parsing, key-in-config refusal (BR-3),
  and opt-in/disabled posture (BR-11).
- New `test_shim_equivalence.py`: `ask-kimi`/`kimi-write` shims `--help` and
  `--dry-run` byte-identical to `adlc-read`/`adlc-write`.
- New `test_delegate_gate.py` / extend `test_partials.py` for the new gate
  return-code + reason contract and the legacy wrapper mapping.
- Existing suites renamed/updated to import the new entrypoints.
- Linux parity: pytest + partials are POSIX/bash-safe (BR-8); launchctl steps in
  install.sh already guard with `command -v launchctl` (skip-with-notice).
