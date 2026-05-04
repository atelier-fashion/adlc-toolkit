---
id: LESSON-004
title: "/proceed Phase 7.5 (canary) and Phase 8a (snapshot promotion) misfit a dev → staging → main topology — pair with workflow-side replacement, then remove"
component: "adlc/proceed"
domain: "adlc"
stack: ["claude-code", "markdown", "github-actions", "gh-cli"]
concerns: ["architecture", "developer-experience", "skill-correctness"]
tags: ["proceed", "canary", "snapshot-promotion", "phase-removal", "halt-contract", "global-counter", "cross-repo-pairing"]
req: "REQ-380"
created: 2026-05-04
updated: 2026-05-04
---

## What Happened

`/proceed` shipped with two phases that assumed a one-shot promotion model: Phase 7.5 (Canary Deploy) ran `/canary` per touched service before merge, and Phase 8a (Create Promotion Snapshot) opened the staging → main PR after merge. Both phases worked fine for repos with a single deployable surface and no separate staging gate. For atelier-fashion's dev → staging → main topology, both were anti-patterns:

- **Phase 7.5** deployed a feature-branch image to **production** Cloud Run from a pre-dev-merge branch. The whole point of staging is that the main-branch image is a byte-identical promotion of an image that already passed real-API harness tests on staging. Auto-running a feature canary against prod defeats both gates simultaneously.
- **Phase 8a** polled `staging` tip CI for ≤30 minutes, looking for the harness to be green. End-of-feature wall-clock time is almost never a moment when staging is freshly green — staging promotion is operator-driven and runs on its own cadence. Result: legitimate halt #5 fired on every single feature `/proceed` run, exercising the autonomous-execution-contract escape hatch that should have been rare.

The fix shipped as a paired REQ across two repos:

- **REQ-379 (atelier-fashion)** added `snapshot-promotion-on-staging-green.yml` — a GitHub Actions workflow that fires on Unified CI Pipeline success against staging and calls the same `scripts/git/create-promotion-snapshot.sh` helper Phase 8a was using. Shipped first (PRs [#773](https://github.com/atelier-fashion/atelier-fashion/pull/773), [#774](https://github.com/atelier-fashion/atelier-fashion/pull/774), merged 2026-05-04).
- **REQ-380 (adlc-toolkit)** then removed Phase 7.5 and Phase 8a from `/proceed` entirely. The autonomous-execution contract dropped from **5** legitimate halt points to **3**. Shipped second ([adlc-toolkit#28](https://github.com/atelier-fashion/adlc-toolkit/pull/28), merged 2026-05-04).

Same REQ also adopted a **global REQ counter** shared across both repos so that future cross-repo references resolve unambiguously — the price was an intentional gap from REQ-264 to REQ-379 in adlc-toolkit's local numbering.

## Why It Matters

Three load-bearing patterns came out of this:

1. **Topology mismatch is a category of skill bug.** Skills that orchestrate deploy operations encode a specific promotion model. When a project's promotion model differs, the skill doesn't just "not help" — it actively executes the wrong thing. Phase 7.5 didn't degrade gracefully; it shipped a feature image to prod. The takeaway: skill phases that touch shared infrastructure should be opt-in via per-project config, or factored out into project-owned hooks (CI workflows, post-merge scripts) so the project owns the topology.

2. **Ship workflow-side replacements before removing the skill-side phase.** REQ-379 had to land first so that the moment REQ-380 removed Phase 8a, snapshot PR creation kept happening (the workflow took over). The helper script's 4-state idempotency machine (`already_present` return) made the overlap window safe — both Phase 8a and the workflow could fire for the same staging SHA without collision. If you have to pull a phase that has external consumers (operator workflows, downstream merges), build the replacement first and run them concurrently for at least one cycle.

3. **Counter scope follows reference scope.** When REQ ids leak across repos (lessons cross-reference each other, branch names appear in multiple PRs, a single REQ touches both repos), per-repo counters produce ambiguous ids — REQ-262 in adlc-toolkit is a different work item than REQ-262 in atelier-fashion, but no link, log line, or PR title disambiguates. A single global counter at `~/.claude/.global-next-req` resolves the ambiguity. The intentional gap (REQ-264..REQ-379) is the cost of fast-forwarding; existing lower-numbered REQs keep their ids.

## How To Avoid Next Time

- When a new `/proceed` phase is proposed that touches shared infrastructure (production, staging, deploy systems, snapshot branches): explicitly enumerate which promotion topologies it works in. If there are more than one, gate the phase behind a per-project config flag rather than running it by default.
- Pair removals across repos: the workflow that takes over MUST land first; the skill phase removal lands second. The deferred Phase 8a `already_present` idempotency in the helper script is the pattern that lets the overlap be safe — bake similar idempotency into any replacement before pulling the trigger.
- For halt-point inventory: keep the autonomous-execution-contract preamble as the single source of truth. Inline `(legitimate halt #N)` citations are useful at single trigger sites (#2 reflector questions, #3 merge conflicts) but skip them for process-wide halts (#1 validation 3× — fires from any gate). The asymmetry is intentional.

## Related

- Paired REQ: atelier-fashion REQ-379 (workflow side) — see atelier-fashion's own LESSON for that side
- Helper script: `scripts/git/create-promotion-snapshot.sh` (REQ-362 ADR-362-G) — the contract both Phase 8a and the workflow consume
- Deferred follow-ups: `bugfix/SKILL.md:128` stale Phase 7.5 cross-reference; `templates/config-template.yml` and `presets/ios-firebase-cloudrun.yml` `pipeline.snapshot_promotion` schema removal — both filed as follow-up tasks during /proceed Phase 5
- Edge-case operator note: any `pipeline-state.json` found at `currentPhase: "7.5"` or `"8a"` after the REQ-380 merge requires a manual edit to `currentPhase: 8` before resuming — grep on 2026-05-04 found zero such files but the recovery step is documented here for future reference.
