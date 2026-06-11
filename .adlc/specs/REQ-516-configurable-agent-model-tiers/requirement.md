---
id: REQ-516
title: "Configurable Agent Model Tiers — Render model: Frontmatter from Config"
status: approved
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "adlc/agents"
domain: "adlc"
stack: ["markdown", "yaml", "bash"]
concerns: ["configurability", "cost"]
tags: ["agents", "model-tiers", "frontmatter", "sync", "init"]
---

## Description

Every agent definition in `agents/` (17 at time of writing; REQ-517 adds an 18th) hardcodes a `model:` value (`opus`, `sonnet`,
or `haiku`) in their frontmatter. The assignments encode a sensible default policy
(opus for judgment-heavy review/implementation, sonnet for deep scanning, haiku for
fast exploration), but a toolkit adopter who wants a different cost/quality
trade-off — "everything on sonnet", "explorers on a cheaper alias", or "inherit the
session model everywhere" — must hand-edit 17 files, and their edits are clobbered
by the next toolkit pull.

Claude Code reads agent frontmatter statically; there is no runtime interpolation.
So configurability must happen at *render time*: each agent declares a stable
**tier class**, a config file maps class → model alias, and a sync script stamps
the resolved `model:` value into the agent files. With no config present, the
shipped defaults reproduce today's assignments exactly.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Agent | tier | string (frontmatter field `tier:`) | required on every agent in `agents/`; one of the defined classes |
| TierMap | classes | map<class, model-alias \| "inherit"> | classes: `reviewer`, `scanner`, `explorer`, `implementer`, `orchestrator` (final set decided in architecture) |
| TierMap | overrides | map<agent-name, model-alias \| "inherit"> | optional per-agent override, beats class mapping |
| TierMap (location) | — | section `agents:` of the shared ADLC config file (see REQ-515) | absent section/file ⇒ shipped defaults |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| tier render | user runs the sync script (and as a step of `/init` re-sync) | per-agent: old model, new model, changed? |
| drift report | `/template-drift` run | agents whose `model:` differs from the config-rendered value |

## Business Rules

- [ ] BR-1: Every agent file in `agents/` declares a `tier:` frontmatter field. The `model:` field becomes derived output, never hand-edited; a header comment in each agent file says so.
- [ ] BR-2: The render script resolves each agent's model as: per-agent override > class mapping > shipped default for that class. The value `inherit` removes the `model:` line entirely so the agent inherits the session model.
- [ ] BR-3: With no config file (or no `agents:` section), rendering produces exactly today's 17 assignments — zero behavior change for existing installs.
- [ ] BR-4: Rendering is idempotent (second run produces no diff) and atomic per file (temp-write then rename); it only rewrites the `model:` line and never reflows other frontmatter or body content. (informed by LESSON-006)
- [ ] BR-5: `/template-drift` (or `lint-skills`) reports agents whose `model:` value differs from what the current config would render, classifying it as staleness — mirroring the existing template-drift rationale, not just its mechanism. (informed by LESSON-023, LESSON-019)
- [ ] BR-6: All shell is BSD- and zsh-safe (no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable, no unmatched globs), and is dogfooded by executing under `zsh -c` and `bash -c`. (informed by LESSON-013, LESSON-329, LESSON-335)
- [ ] BR-7: The render script validates model aliases against a known-good set (`opus`, `sonnet`, `haiku`, `inherit`, plus a documented escape hatch for full model ids) and fails loud on anything else — no silent fall-through to a default. (informed by LESSON-009)

## Acceptance Criteria

- [ ] Setting `scanner: haiku` in the config and running the render script updates exactly the scanner-class agents; all other agent files are byte-identical.
- [ ] A fresh checkout with no config renders frontmatter identical to the committed `agents/*.md` at the time of implementation (all agents then present, including any added since this spec was written).
- [ ] Setting a class to `inherit` removes the `model:` line from that class's agents; rendering back to an alias restores it.
- [ ] Running the render script twice in a row produces an empty `git diff` after the first run.
- [ ] `/template-drift` flags a hand-edited `model:` line as drifted from config; after re-render the flag clears.
- [ ] An invalid alias in the config (e.g. `scanner: gpt5`) fails with a message naming the bad key, value, and allowed set.
- [ ] Linux parity: the render script and drift check behave identically under Ubuntu bash and macOS zsh (verified by running the AC scenarios on both, or in CI).

## External Dependencies

- None. Soft dependency on REQ-515 only for the *location/format* of the shared config file; if REQ-515 has not merged first, this REQ creates the config file and REQ-515 adds its `delegate:` section to it.

## Assumptions

- Claude Code tier aliases (`opus`/`sonnet`/`haiku`) remain stable across versions; full model ids are an escape hatch, not the default.
- Adopters install via symlinked checkout (per the install model), so rendering into the checkout is the correct write target and survives for all projects on the machine.

## Open Questions

- [ ] None. (Resolved 2026-06-11, per maintainer: tier-class set is the five classes `reviewer`/`scanner`/`explorer`/`implementer`/`orchestrator` — `kimi-pre-pass` maps to `explorer` and `pipeline-runner` to `orchestrator`, with the per-agent `overrides` map as the escape hatch if either proves to need bespoke handling; the shipped default policy is today's explicit per-agent assignments, NOT the drop-`model:` variant, preserving BR-3's zero-behavior-change guarantee. `inherit` remains available as an opt-in config value, not the default.)
- [ ] ~~Where does the render script live~~ (Resolved 2026-06-11: it ships as a subcommand of the umbrella `adlc` CLI established in REQ-519 BR-11 — e.g. `adlc agents render` — keeping user-facing commands in one home; `/template-drift` calls the same code path for its drift check, per LESSON-006's carve-out convention.)

## Out of Scope

- Delegation-layer provider config (REQ-515).
- Per-invocation model overrides in skills (the Agent tool's `model:` param already covers that).
- Any change to agent prompts, tool restrictions, or which agents exist.
- Runtime/dynamic model selection — rendering is explicitly a sync-time operation.

## Retrieved Context

- LESSON-313 (lesson, score 4): global counter scope is its scan root
- LESSON-023 (lesson, score 4): mirror the rationale not just mechanism
- LESSON-019 (lesson, score 4): presence guards rot when indirection moves
- LESSON-020 (lesson, score 4): cross-block shell state and guard rot
- LESSON-013 (lesson, score 4): BSD grep word-boundary silent failure
- LESSON-012 (lesson, score 4): structural telemetry beats prose enforcement
- LESSON-008 (lesson, score 4): skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 4): hotfix verify finds what original verify missed
- LESSON-335 (lesson, score 3): zsh-executor and arg-templating hazards
- LESSON-329 (lesson, score 3): dogfood skills under executor shell
- LESSON-330 (lesson, score 3): review catches omitted requirements
- LESSON-014 (lesson, score 3): lock symlink TOCTOU
- LESSON-010 (lesson, score 3): delegated-model silent truncation and advisory anchoring
- LESSON-006 (lesson, score 3): tools dir carve-out and fail-loud installers
- LESSON-004 (lesson, score 3): drop proceed canary and snapshot phases
