---
id: REQ-433
title: "Kimi telemetry global-fallback resolver — make delegation telemetry work in downstream repos"
status: complete
deployable: true
created: 2026-05-16
updated: 2026-05-16
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "markdown", "pytest"]
concerns: ["observability", "portability"]
tags: ["kimi", "telemetry", "ghost-skip", "partials", "fallback", "vendoring"]
---

## Description

REQ-424 added skill-delegation telemetry and ghost-skip detection so that every Kimi
delegation point in the four Kimi-aware skills (`analyze`, `proceed`, `spec`,
`wrapup`) emits a JSON line (`delegated` / `fallback` / `ghost-skip`) to
`~/Library/Logs/adlc-skill-telemetry.log`, with `/analyze` Step 1.8 surfacing
ghost-skips as a `delegation-fidelity` finding. LESSON-012 makes the intent explicit:
this telemetry is the *only* signal that the ~13-REQ Kimi investment is actually being
exercised; without it the user "has no signal until they manually ask 'did you use
kimi?'".

That promise is structurally unfulfilled everywhere except this repo. The four skills
invoke three executables — `tools/kimi/emit-telemetry.sh`, `tools/kimi/skill-flag.sh`,
`tools/kimi/check-delegation.sh` — using **project-relative paths with no global
fallback**. Those executables live under the deliberate `tools/` carve-out for
non-markdown code (informed by LESSON-006) and are therefore **not vendored by
`/init`** — `/init` only vendors `partials/*.sh`, `templates/*.md`, and `ETHOS.md`.
Contrast `kimi-gate.sh`, which works everywhere precisely because it is a *partial*
(so `/init` vendors it) **and** is sourced with a vendored-first-then-global idiom:
`. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`
(the ADR-2 pattern from REQ-416). The telemetry executables have neither property.

Consequence: in any downstream project the telemetry scripts resolve to a
non-existent path, every invocation no-ops under existing `2>/dev/null || true`
guards, and the log is never written — it has in fact never existed on this machine.
Ghost-skip detection is dead in exactly the projects most prone to ghost-skips.
Re-running `/init` cannot fix this; it was never designed to vendor `tools/kimi/`,
and per LESSON-006 it should not (scattering executable code into consumer `.adlc/`
violates the markdown/tools carve-out).

This REQ closes the gap by mirroring the proven `kimi-gate` pattern: a new sourced
resolver **partial** that exports a `KIMI_TOOLS` directory variable — project-local
`tools/kimi` when present (canonical repo / dogfooding), else
`$HOME/.claude/skills/tools/kimi`, which always resolves because `~/.claude/skills`
is a symlink to the canonical toolkit repo root. Because the resolver is a partial,
`/init` already distributes it with zero `/init` changes and zero per-repo re-init —
and the `tools/` carve-out is preserved (no executable code enters consumer `.adlc/`).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| `partials/kimi-tools-path.sh` | (file) | POSIX sh partial | Sourced, not executed; no `set -eu`; no bashisms; no GNU-only utilities; no language-specific deps (python/node) |
| `KIMI_TOOLS` | value | string (dir path, no trailing slash) | Exported on every code path; never unset after the resolver runs |
| Resolution input | `tools/kimi/emit-telemetry.sh` | filesystem probe | Presence of the canonical project-local script is the local-vs-global discriminator |
| Resolution input | `$HOME/.claude/skills/tools/kimi` | filesystem path | Global fallback target; resolves via the `~/.claude/skills` → toolkit-repo symlink |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| resolver-sourced | A skill shell block that uses telemetry sources the partial (vendored-first idiom) | Exports `KIMI_TOOLS` |
| telemetry-invocation | Any of the 39 call sites runs `"$KIMI_TOOLS"/<script>.sh …` | Unchanged script args; only the path prefix differs |

### Permissions

Not applicable — no actors/roles; this is build/infra plumbing.

## Business Rules

- [ ] BR-1: `kimi-tools-path.sh` MUST set and `export KIMI_TOOLS` on **every** code path (mirrors the `kimi-gate.sh` "exports on every path" contract from REQ-416 ADR-2).
- [ ] BR-2: Resolution order — if `tools/kimi/emit-telemetry.sh` exists and is executable (canonical repo / dogfooding), `KIMI_TOOLS="tools/kimi"`; else `KIMI_TOOLS="$HOME/.claude/skills/tools/kimi"`. Use `$HOME`, never `~`, in the assignment.
- [ ] BR-3: The partial MUST be POSIX `sh` only — no `set -eu`, no bashisms, no GNU-only flags, no python/node. (informed by LESSON-012, LESSON-013)
- [ ] BR-4: If neither path resolves, the resolver MUST degrade non-fatally: set `KIMI_TOOLS="tools/kimi"` (today's effective behavior) so existing `2>/dev/null || true` guards continue to no-op. The resolver MUST NOT `exit`, `return` non-zero in a way that aborts the caller, or emit to stderr. Telemetry never blocks a skill. (informed by REQ-424, LESSON-008)
- [ ] BR-5: All 39 invocation sites across `analyze/SKILL.md` (15), `proceed/SKILL.md` (8), `spec/SKILL.md` (8), `wrapup/SKILL.md` (8) MUST use `"$KIMI_TOOLS"/<script>.sh`, including command-substitution sites (e.g., `flag=$("$KIMI_TOOLS"/skill-flag.sh create)`). Zero bare `tools/kimi/<script>.sh` invocations may remain in those four skills.
- [ ] BR-6: The resolver MUST be sourced once per shell block that references `KIMI_TOOLS`, immediately adjacent to that block's existing `kimi-gate.sh` source line, using `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`.
- [ ] BR-7: No change to `init/SKILL.md`. The new partial is auto-distributed by the existing `cp ~/.claude/skills/partials/*.sh .adlc/partials/` step. The `tools/` carve-out MUST be preserved — no executable code added to consumer `.adlc/`. (informed by LESSON-006)
- [ ] BR-8: Behavior inside the toolkit repo itself MUST be unchanged — `KIMI_TOOLS` resolves to project-local `tools/kimi` there, so existing dogfooded telemetry continues to write identically.
- [ ] BR-9: The edit MUST be reconciled with REQ-428 (which deduped the `/analyze` telemetry block) — the shared/deduped block must be updated once, not re-fork the duplication REQ-428 removed.

## Acceptance Criteria

- [ ] In a downstream project containing only `/init`-vendored `.adlc/partials/` (no `tools/kimi/`), running any of `analyze`/`proceed`/`spec`/`wrapup` through a Kimi delegation point writes at least one well-formed JSON line to `~/Library/Logs/adlc-skill-telemetry.log`, and the skill-flag temp file is created at gate entry and removed at block exit (ghost-skip lifecycle functions).
- [ ] `grep -rnE 'tools/kimi/(emit-telemetry|skill-flag|check-delegation)\.sh' analyze/SKILL.md proceed/SKILL.md spec/SKILL.md wrapup/SKILL.md` returns **zero** bare invocations (every site uses the `"$KIMI_TOOLS"/` form).
- [ ] A new pytest module (mirroring `tools/kimi/tests/test_partials.py`) asserts: (a) resolver picks `tools/kimi` when the local script is present; (b) resolver picks `$HOME/.claude/skills/tools/kimi` when it is absent; (c) resolver is non-fatal and still exports `KIMI_TOOLS` when neither resolves; (d) the partial sources cleanly under `sh` with `set -eu` in the *caller* without aborting it.
- [ ] All existing `tools/kimi/tests/` pass unchanged.
- [ ] The new partial passes the repo's POSIX/skill-md lint harness (`tools/lint-skills/` and/or the partial test suite) with no new findings.
- [ ] Running the four skills *inside* the toolkit repo produces telemetry identical (path, format, modes) to pre-change behavior — verified by diffing a sample emitted line's shape.

## External Dependencies

- None. (Relies only on the already-established `~/.claude/skills` → toolkit-repo symlink, which is the documented install model.)

## Assumptions

- `~/.claude/skills` is a symlink to the canonical adlc-toolkit repo root on every machine where these skills run (verified this session; matches the documented symlink-based live-install model). Therefore `$HOME/.claude/skills/tools/kimi/<script>.sh` always resolves wherever the toolkit is installed.
- The three telemetry scripts' only invokers are the four Kimi-aware skills' SKILL.md shell blocks (to be confirmed in architecture — see Open Questions).
- `2>/dev/null || true` / `2>/dev/null` guards already wrap the no-op-sensitive call sites (skill-flag clear/check), so BR-4's degrade path preserves exactly today's behavior.

## Open Questions

- [ ] Should the "neither resolves" degrade target be project-local `tools/kimi` (chosen in BR-4 to exactly preserve today's no-op) or an explicit sentinel that makes the no-op intentional and greppable? Resolve in `/architect`.
- [ ] Are there any non-skill callers of `emit-telemetry.sh` / `skill-flag.sh` / `check-delegation.sh` (e.g., `/analyze` Step 1.8 invoking `check-delegation.sh`, or test harnesses) that also need the `$KIMI_TOOLS` treatment or must be deliberately excluded? Enumerate in `/architect`.
- [ ] Does the `kimi-tools-path.sh` partial need a companion `.md` doc (like `kimi-gate.md`) describing its contract, or is a header comment sufficient given its smaller surface? Decide in `/architect`.

## Out of Scope

- The stale-shell PATH gate failure (`command -v ask-kimi` failing in non-interactive/long-lived sessions) — a separate, already-diagnosed issue; not addressed here.
- Any change to the telemetry log path, JSON schema, or the three scripts' internal logic.
- Making `/init` vendor `tools/kimi/` — explicitly rejected: it would violate the LESSON-006 markdown/tools carve-out and re-introduce per-repo drift.
- Changes to `kimi-gate.sh`, the `ask-kimi`/`kimi-write`/`extract-chat` CLIs, or `install.sh`.
- Backfilling or reconstructing historical (never-written) telemetry.
- Per-repo re-init (the fix is global by construction; no consumer action required after merge + that consumer's next routine `/init` refresh).

## Retrieved Context

- LESSON-012 (lesson, score 8): Structural telemetry beats prose enforcement — establishes the REQ-424 telemetry intent this REQ completes; mandates POSIX-only skill helpers
- REQ-424 (spec, score 7): Skill-delegation telemetry — the feature whose downstream reach this REQ fixes
- LESSON-013 (lesson, score 5): BSD-vs-GNU grep word-boundary silent failure — portability constraint for the new shell partial
- LESSON-008 (lesson, score 5): Skill delegation untrusted-data & BR-4 one-line / never-block discipline
- REQ-427 (spec, score 5): POSIX-ification of /analyze Step 2a — portability precedent for skill shell
- REQ-417 (spec, score 5): Kimi skill-delegation wave 2 — wired several of the telemetry call sites being edited
- REQ-414 (spec, score 5): ADLC skill Kimi pilot — original analyze/wrapup delegation + fallback wiring
- REQ-428 (spec, score 4): Dedupe /analyze telemetry block — adjacent precedent; BR-9 reconciliation
- REQ-415 (spec, score 4): Kimi hotfix bundle — install.sh / carve-out context
- REQ-423 (spec, score 4): wrapup JSONL discovery — touches the wrapup telemetry block
- LESSON-010 (lesson, score 4): Delegated-model silent truncation & advisory anchoring
- LESSON-006 (lesson, score 3): tools/ carve-out & fail-loud installers — load-bearing rationale for the partial-resolver design (do NOT vendor tools/ into consumers)
- REQ-416 (spec, score 3): Toolkit refactor — source of the ADR-2 kimi-gate vendored-first-then-global idiom being mirrored
- LESSON-014 (lesson, score 2): Lock symlink TOCTOU — informs symlink-safety reasoning (resolver only reads the symlinked path; no mutation)
