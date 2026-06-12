---
id: REQ-520
title: "Forge Adapter — Configurable GitHub / Azure DevOps PR Operations"
status: approved
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "adlc/toolkit"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["configurability", "portability"]
tags: ["forge", "github", "azure-devops", "pr-lifecycle", "adapter", "gh", "az-repos"]
---

## Description

Every skill that touches the pull-request lifecycle shells out to the GitHub CLI
directly: `/proceed` (draft-PR-early, `gh pr create`, `gh pr merge`, `gh pr view`),
`/sprint` (merge-claim verification, in-flight PR listing), `/manifest` (open-PR
derivation), `/bugfix`, and `/wrapup`. On a repo hosted on Azure DevOps, every one
of those calls fails — the pipelines die at PR creation even though all the pure-git
machinery (worktrees, branches, trial-merge gates, `ls-remote` scans) works fine.
The new company runs Azure DevOps, so this gap blocks toolkit adoption there.

This REQ introduces a **forge adapter**: a single sourced partial exposing a small,
forge-neutral operation set (create/ready/merge/view/list PRs), backed by `gh` for
GitHub and `az repos` (or the ADO REST API via PAT) for Azure DevOps, selected per
repo via a `forge:` section of the shared ADLC config (REQ-515) with auto-detection
from the `origin` remote URL as the default. Skills call the adapter functions and
never invoke `gh` directly for PR operations; switching a project between GitHub
and ADO becomes a config change (or nothing at all, via auto-detect).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ForgeConfig | provider | enum | `github` \| `azure-devops` \| `auto` (default `auto` — detect from `origin` URL: `github.com` → github, `dev.azure.com` / `*.visualstudio.com` → azure-devops) |
| ForgeConfig | auth | string | name of the credential source: `gh` (logged-in CLI) for GitHub; env-var *name* holding a PAT, or `az` CLI login, for ADO — never a credential value (mirrors REQ-515 BR-3) |
| ForgeConfig (location) | — | `forge:` section of the shared ADLC config file; per-project override in `.adlc/config.yml` | absent ⇒ `auto` |
| ForgeOp | name | enum | `pr_create` (with draft flag), `pr_ready`, `pr_merge` (strategy + delete-branch), `pr_view` (state/mergedAt), `pr_list` (open, by branch pattern), `pr_comment` |
| ForgeOp | result | structured | normalized fields per op (e.g. `pr_view` → `state ∈ {OPEN, MERGED, CLOSED}`, url, id) — identical shape from both backends |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| forge op | any skill performs a PR operation through the adapter | op name, provider, repo, normalized result or normalized error class |
| capability degrade | a backend lacks a feature the op models (e.g. draft PRs on ADO) | op, provider, the documented degradation taken |

## Business Rules

- [ ] BR-1: One sourced partial (`partials/forge.sh` + the documented carve-out for any non-trivial backend code under `tools/`) is the only place `gh`/`az` PR commands live. All PR-lifecycle call sites in `/proceed`, `/sprint`, `/manifest`, `/bugfix`, `/wrapup`, and the sprint workflow are migrated to adapter functions; a lint-skills check rejects new direct `gh pr` usage in skills, and that presence guard is written against the post-migration shapes, not the old literals. (informed by LESSON-020, LESSON-019)
- [ ] BR-2: Provider resolution: per-project `.adlc/config.yml` `forge:` > machine config `forge:` section > `auto` detection from the `origin` remote URL. `auto` on an unrecognized host fails loud, naming the URL and the two supported providers — no silent default to GitHub. (informed by LESSON-009)
- [ ] BR-3: GitHub behavior is byte-compatible with today: with provider `github` (or auto-detected), every migrated call site produces the same commands, flags, and outcomes as the current direct `gh` calls — zero behavior change for existing installs, mirroring the REQ-515/516 compatibility discipline.
- [ ] BR-4: The op result and error surface is normalized: both backends return the same field names and the same error classes (`auth-missing`, `pr-not-found`, `merge-blocked-by-policy`, `feature-unsupported`, `network`), so calling skills branch on one vocabulary. Raw backend stderr is preserved beneath the normalized class, never swallowed — distinct failures must not collapse into one label. (informed by LESSON-334 rationale via REQ-515, LESSON-008)
- [ ] BR-5: Capability mismatches are explicit, never papered over. Each known mismatch ships with a documented mapping — e.g. ADO draft PRs (supported: `--draft`/publish), squash-merge semantics (`az repos pr update --squash` + auto-complete vs `gh pr merge --squash`), delete-source-branch flags, and "merge blocked by branch policy" (ADO policies ≈ GitHub required reviews → normalized to `merge-blocked-by-policy`, surfaced as a blocker, never bypassed — ethos #6). Anything genuinely unmappable returns `feature-unsupported` with the documented degradation. 
- [ ] BR-6: Credentials follow REQ-515 BR-3 discipline: config stores credential *source names* only; the adapter refuses key-shaped values in config; PATs are read from the named env var at call time and never echoed, logged, or written to telemetry. (informed by LESSON-008)
- [ ] BR-7: `adlc doctor` (REQ-519) gains a `forge` check: resolved provider, backend CLI present, auth valid (`gh auth status` / `az account show` or PAT-var set), and a read-only API probe — with copy-pasteable remediation per failure. The check is `skip`-with-reason when the repo has no remote.
- [ ] BR-8: Remote-derivation consumers stay forge-neutral, each via the right mechanism: `/manifest`'s open-PR view routes through `pr_list`/`pr_view`; REQ-518's merged-artifact scan is NOT a PR operation and uses pure git (shallow fetch of the default branch + `ls-tree`), which works identically against GitHub and ADO git endpoints — no forge op and no ADO REST dependency for tree reads. The pure-git `ls-remote` path remains the universal fallback when the forge API is unreachable (degraded-loud, not silent). (informed by LESSON-313)
- [ ] BR-9: All adapter shell is BSD- and zsh-safe and dogfooded under `zsh -c`, `bash -c`, and Ubuntu bash; the partial follows the sourced-partial rules (no cross-block state, no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=`). (informed by LESSON-013, LESSON-329, LESSON-335, LESSON-020)
- [ ] BR-10: The adapter ships with a mock-backend test mode (`ADLC_FORGE_MOCK=1` or equivalent fixture backend) so the call-site migration and both provider mappings are testable offline in CI without a live GitHub or ADO org; tests cover every op × both providers × the normalized error classes. (informed by LESSON-012, LESSON-009)

## Acceptance Criteria

- [ ] On a GitHub-hosted repo with no config, `auto` resolves to `github` and a full `/proceed` run (draft PR → ready → merge → verify) behaves identically to today, with zero direct `gh pr` invocations remaining in the migrated skills (grep-verified, lint-enforced).
- [ ] On an ADO-hosted repo (or the mock backend simulating one) with `provider: azure-devops`, the same pipeline sequence completes: PR created, flipped from draft, merged with source-branch deletion, and `pr_view` returns normalized `MERGED`.
- [ ] Switching a project between the two providers requires editing only the `forge:` config value — no skill or partial edits.
- [ ] `auto` on an unrecognized remote URL fails with a message naming the URL and supported providers; nothing is attempted against a guessed backend.
- [ ] An ADO merge blocked by branch policy surfaces as the normalized `merge-blocked-by-policy` blocker (pipeline halts gracefully, same as a failed GitHub merge today) — never a bypass or force.
- [ ] A key-shaped value in the `forge:` config is refused with an actionable error; a missing PAT env var produces the `auth-missing` class plus doctor-style remediation.
- [ ] `adlc doctor` reports the forge check pass/fail/skip correctly on: GitHub+gh-authed, ADO+PAT, ADO+no-PAT, and no-remote repos.
- [ ] The mock-backend test matrix (ops × providers × error classes) passes under macOS zsh/bash and Ubuntu bash.
- [ ] `/manifest` produces its in-flight table against the mock ADO backend, and falls back to `ls-remote`-only derivation (with a loud degradation notice) when the forge API is unreachable.

## External Dependencies

- `az` CLI (Azure DevOps extension) OR direct ADO REST API via `curl` + PAT — architecture decides the primary; `gh` remains the GitHub backend. Neither is required at install time; the doctor check reports absence with remediation.

## Assumptions

- The forge-neutral op set above covers every PR operation the skills actually perform today (verified by grep inventory during architecture; any missed op is added to the enum, not called directly).
- ADO Repos is the target ADO surface; ADO Boards/Pipelines integration is not implied by this REQ.
- Branch naming (`feat/REQ-xxx`) and the trial-merge/worktree machinery are forge-independent and unchanged.

## Open Questions

- [ ] ADO backend: `az repos` CLI (heavier dependency, nicer auth) vs raw REST via `curl` + PAT (zero new dependency, more code to harden)? Proposed: `az repos` primary with REST documented as the fallback, decided in architecture after a capability spike.
- [ ] Should `pr_comment` (used for footprint publishing, REQ-484) land in v1, or defer until footprint publishing is exercised on ADO? Proposed: include the op in the interface, mock-tested, ADO mapping may ship as `feature-unsupported` in v1 if the spike finds friction.
- [ ] Does `/sprint`'s merge-claim verification need ADO-specific state nuances (ADO "completed" vs "abandoned" vs GitHub "MERGED"/"CLOSED")? Proposed: normalize ADO `completed→MERGED`, `abandoned→CLOSED` in `pr_view`.

## Out of Scope

- Forges beyond GitHub and Azure DevOps (GitLab, Bitbucket) — the adapter interface should not preclude them, but no backend ships.
- ADO Boards/Pipelines (work items, builds) integration.
- CI-status polling abstraction (today's skills treat CI as optional/absent in this repo; revisit when a consumer needs it).
- Per-company branch-policy/merge-mode *policy* configuration (the rest of the parked "pipeline policy" REQ) — this REQ only makes existing behavior forge-portable.
- Changing any PR content conventions (titles, bodies, footers).

## Retrieved Context

- REQ-519 (spec, score 9): One-Command Installer and adlc doctor Health Check
- REQ-515 (spec, score 8): Provider-Agnostic Delegation Layer — de-Kimi the Tooling
- REQ-516 (spec, score 6): Configurable Agent Model Tiers
- REQ-518 (spec, score 6): Collision-Safe ID Allocation Across Users and Machines
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure
- LESSON-006 (lesson, score 6): tools dir carve-out and fail-loud installers
- LESSON-335 (lesson, score 5): zsh-executor and arg-templating hazards
- LESSON-329 (lesson, score 5): dogfood skills under executor shell
- LESSON-313 (lesson, score 4): global counter scope is its scan root
- LESSON-023 (lesson, score 4): mirror the rationale not just mechanism
- LESSON-019 (lesson, score 4): presence guards rot when indirection moves
- LESSON-020 (lesson, score 4): cross-block shell state and guard rot
- LESSON-012 (lesson, score 4): structural telemetry beats prose enforcement
- LESSON-008 (lesson, score 4): skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 4): hotfix verify finds what original verify missed
