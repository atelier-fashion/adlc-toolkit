---
id: REQ-522
title: "De-brand the delegation surface (no Kimi naming) and make skill telemetry single-fence-safe"
status: complete
deployable: false
created: 2026-06-12
updated: 2026-06-12
component: "adlc/delegation"
domain: "adlc"
stack: ["shell", "python", "markdown"]
concerns: ["configurability", "correctness", "telemetry", "portability"]
tags: ["kimi-debrand", "delegation", "cross-fence", "ghost-skip", "provider-neutral", "req-515-followup"]
---

## Description

Two tightly-coupled problems live in the same files, so they ship as one REQ.

**1. Finish the REQ-515 genericization — nothing branded Kimi.** REQ-515 made the delegation *engine* provider-agnostic (`adlc-read`/`adlc-write`, `ADLC_DELEGATE_*` env vars, `delegate-gate.sh`, config-file provider resolution) but deliberately kept a Kimi-branded compatibility layer: the `tools/kimi/` directory itself, `kimi-gate.sh`/`kimi-tools-path.sh` source-through partials, `ask-kimi`/`kimi-write` CLI shims, the `KIMI_TOOLS` env var (45 live references), `ASK_KIMI_INVOKED`/`KIMI_EXIT` telemetry variables and "delegating … to kimi" stderr prose inside `spec`/`proceed`/`wrapup` SKILL.md, `ADLC_DISABLE_KIMI`, the `com.adlc-toolkit.kimi-setenv` launchd plist, and `kimi-*` lint fixtures. The 5.0 epoch's stated goal is a toolkit others can adopt with their own delegate model; a fresh adopter today still installs a `tools/kimi/` tree and reads Kimi-branded instructions even when their delegate is something else entirely. This REQ retires the compatibility layer and renames every remaining branded identifier to the provider-neutral vocabulary REQ-515 already established. Kimi/Moonshot may survive **only** as one provider preset's *data* (default endpoint/model values and the legacy `KIMI_API_KEY`/`MOONSHOT_API_KEY` env-var continuity read), never as a file name, directory name, command name, partial name, env-var name, variable name, or skill prose.

**2. Fix the inert delegation telemetry (adversarial finding C1, critical).** The REQ-424 telemetry sequences in `spec/SKILL.md` Step 1.6, `proceed/SKILL.md` Phase 5, and `wrapup/SKILL.md` Step 4 set shell state (`start_s`, `ASK_KIMI_INVOKED`, `KIMI_EXIT`, `flag`) in one fenced block and read it in a later, separate fenced block. Fenced blocks do not share shell state (conventions.md "Bash in skills"; LESSON-020), so the resolution block always takes the `[ -z "$ASK_KIMI_INVOKED" ]` branch: every run — including successful delegated runs — is recorded as `mode=fallback, gate_result=fail`, `duration_ms` is garbage or a hard arithmetic error, the flag file leaks, and the ghost-skip coercion guard in the telemetry emitter (which only fires on `gate=pass`) is unreachable. The ghost-skip detection apparatus is currently inert and `check-delegation.sh` counts are systematically wrong. Since the de-branding rewrites these exact blocks anyway (renaming `KIMI_TOOLS`, `ASK_KIMI_INVOKED`, `KIMI_EXIT`), the restructure to single-fence-safe telemetry happens in the same edit, avoiding a guaranteed merge conflict between two separate REQs.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| TelemetryRecord | mode | string | one of `delegated`, `fallback`, `ghost-skip` (unchanged REQ-424 schema) |
| TelemetryRecord | gate_result | string | `pass` / `fail`; must reflect the gate's actual return, not lost shell state |
| DelegateConfig | provider preset | data | Kimi/Moonshot values allowed here and only here |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| telemetry-emit | end of each delegating skill step | skill, step, req, gate_result, mode, reason, duration_ms |

## Business Rules

- [ ] BR-1: After this REQ, `grep -ri kimi` over the distribution surface (all `<skill>/SKILL.md`, `agents/`, `partials/`, `tools/`, `workflows/`, `templates/`, `install.sh`, `README.md`, `presets/`) returns matches **only** in (a) the provider-preset/default-value data and the legacy-env continuity read (`KIMI_API_KEY`/`MOONSHOT_API_KEY` accepted as opt-in per REQ-515 BR-11), (b) historical records (`.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/`, `CHANGELOG.md`). No file, directory, command, partial, env var, shell variable, plist label, or skill prose is Kimi-named.
- [ ] BR-2: `tools/kimi/` is renamed to a provider-neutral path (e.g. `tools/delegate/`); `kimi-gate.sh` and `kimi-tools-path.sh` are deleted after every source-line in skills, agents, workflows, and lint fixtures is switched to `delegate-gate.sh` / `delegate-tools-path.sh`; `KIMI_TOOLS` is renamed to `DELEGATE_TOOLS` at every reference. `/init`'s vendored-partials copy list and `install.sh` are updated in the same change. (informed by LESSON-005 — sibling-skill cross-reference rot; LESSON-019 — presence guards must follow indirection)
- [ ] BR-3: The `ask-kimi` / `kimi-write` CLI shims are removed. `ADLC_DISABLE_KIMI` is removed as an accepted flag; only `ADLC_DISABLE_DELEGATE` disables. Removal is announced in CHANGELOG with a one-line migration table (old name → new name). Legacy *API-key* env vars remain readable (continuity, REQ-515 BR-11) — key continuity is data, not branding.
- [ ] BR-4: Every telemetry sequence in a delegating skill (`spec` Step 1.6, `proceed` Phase 5, `wrapup` Step 4, and `analyze` if audit finds the same pattern) is restructured so that **no shell variable crosses a fenced-block boundary**: either the entire create-flag → gate → invoke → resolve → emit sequence is one fenced block, or all cross-step state is persisted in and re-derived from the on-disk flag file. The resolution logic must make the `delegated` and `ghost-skip` branches actually reachable. (informed by LESSON-020, LESSON-012)
- [ ] BR-5: `tools/lint-skills` gains a cross-fence-**variable** check alongside the existing cross-fence-fn check: a non-exported variable assigned in one fenced block and read in a different fenced block of the same SKILL.md is a lint error. The existing telemetry-literal checks are updated to the new canonical block. (informed by LESSON-012 — structural enforcement beats prose; LESSON-019)
- [ ] BR-6: Telemetry schema (keys, `mode` vocabulary, file mode 600, no-secrets rule) is byte-compatible with REQ-424; old records remain readable by `check-delegation.sh`. A delegated run emits `mode=delegated`; a gate-pass run that skipped the call emits `mode=ghost-skip`; these are verified by executing the actual fenced blocks under both `zsh -c` and `bash -c`, not by reading the prose. (informed by LESSON-329 — dogfood under the executor shell)
- [ ] BR-7: All renamed/moved shell stays BSD- and zsh-safe (no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable). (informed by LESSON-013, LESSON-335)
- [ ] BR-8: The launchd plist template and its label are renamed provider-neutrally; the installer migrates an existing Kimi-labeled LaunchAgent (unload old, load new) rather than leaving both. (informed by LESSON-011, LESSON-017 — validate before mutate)

## Acceptance Criteria

- [ ] `grep -ri kimi <distribution surfaces>` output matches BR-1's allowed set exactly; the check is added as a test or lint rule so the brand cannot creep back.
- [ ] A delegated `adlc-read` run through `/spec` Step 1.6 produces a telemetry record with `mode=delegated, gate_result=pass` and a sane `duration_ms`; a deliberately-skipped gate-pass run produces `mode=ghost-skip`. Both verified by executing the real blocks under `zsh -c` and `bash -c`.
- [ ] No flag file remains in the flag directory after a normal delegated run completes.
- [ ] `tools/lint-skills` fails a fixture that assigns a variable in one fence and reads it in another; the shipped skills pass.
- [ ] Existing telemetry log lines written before this REQ are still parsed by `check-delegation.sh`.
- [ ] A fresh `install.sh` run on a clean machine produces zero Kimi-named files, commands, or env vars; an upgrade run removes/migrates the old shims and LaunchAgent without breaking an existing delegation config.

## External Dependencies

- None new. Existing: `gh` (unrelated), the configured delegate endpoint for live-path verification.

## Assumptions

- REQ-515's `ADLC_DELEGATE_*` vocabulary and `delegate-gate.sh` return-code contract (0/1/2) are stable and correct; this REQ renames consumers onto them, it does not redesign the gate.
- No external consumer scripts outside this machine's repos depend on `ask-kimi`/`kimi-write` (the shims were a REQ-515 courtesy, and the toolkit's README is the only public contract).

## Open Questions

- [ ] Should the legacy `KIMI_API_KEY`/`MOONSHOT_API_KEY` continuity read also be sunset (one release of deprecation warning, then removal), or kept indefinitely as provider-preset data? Default if unanswered: keep, documented as the Moonshot preset's key-env names.
- [ ] Final name for the renamed tools directory: `tools/delegate/` (proposed) vs `tools/adlc-delegate/`.

## Out of Scope

- Changing the shipped default provider (Moonshot endpoint/model values stay the defaults; they are data).
- Redesigning the gate predicate, opt-in posture (REQ-515 BR-11), or telemetry schema.
- The id-allocation findings (REQ-523), renumber safety (REQ-524), drift surfaces (REQ-525), and doc corrections (REQ-526).

## Retrieved Context

- LESSON-020 (lesson, score 8): Cross-block shell state and guard rot — sourced partials are the only cross-step sharing mechanism
- LESSON-012 (lesson, score 4): Structural telemetry beats prose enforcement
- LESSON-019 (lesson, score 4): Presence guards rot when indirection moves
- LESSON-008 (lesson, score 5): Delegation output is untrusted; citation sanitization
- LESSON-329 (lesson, score 6): Dogfood skills under the executor shell
- LESSON-335 (lesson, score 6): zsh executor and arg-templating hazards
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure
- LESSON-392 (lesson, score 4): Enablement probe must share real call resolution
- REQ-515 (spec, score 4): Provider-agnostic delegation — this REQ completes its migration
- REQ-424 (spec, score 3): Skill delegation telemetry — schema this REQ must preserve
