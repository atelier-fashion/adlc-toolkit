---
id: REQ-523
title: "ID allocation remote-derivation integrity: independent sources, working degradation signal, forge-aware artifact scan"
status: complete
deployable: false
created: 2026-06-12
updated: 2026-06-12
component: "partials/id-alloc"
domain: "id-allocation"
stack: ["sh", "bash", "zsh"]
concerns: ["correctness", "concurrency", "portability", "multi-user"]
tags: ["id-alloc", "id-recheck", "degraded-signal", "lesson-counter", "gh-fallback", "forge", "req-518-followup"]
---

## Description

The REQ-518 collision-safe allocator has four verified defects that collectively re-open the merged-id collision window it was built to close (adversarial findings C2, C3, M1, M3, M4):

1. **`ls-remote` failure skips the independent `gh` scan (C3).** In `adlc_remote_high`, a failed branch probe `continue`s past the entire merged-artifact block for that repo. Git transport (SSH) and `gh` (HTTPS+token) fail independently in practice; when only SSH is down, a merged artifact visible to `gh` is ignored and allocation/recheck return wrong-low / false-safe.
2. **LESSON allocation is silently local-only without `gh` (C2).** Lessons have no branch namespace, so the `ls-remote` block — the only path that sets `ADLC_ALLOC_DEGRADED` on failure — never runs for `kind=lesson`. With `gh` absent, neither scan runs, `saw_remote=1` suppresses the no-remote warning, and the function returns 0 with **no degradation signal at all**. Two `gh`-less machines allocate duplicate LESSON ids with zero warning, and `adlc_recheck_id` waves the duplicate through.
3. **The `ADLC_ALLOC_DEGRADED` env-var contract is structurally broken (M1).** The flag is set inside `adlc_remote_high`, which both callers invoke via command substitution `$(…)` — a subshell whose variable writes can never reach the parent. The header comments promise the flag reaches "the CALLER's env"; it cannot. `adlc_recheck_id`'s degraded short-circuit is dead code, and its renumber suggestion can be computed from a high-water of 0 (`adlc renumber REQ-600 REQ-001`).
4. **The promised non-`gh` fallback doesn't exist, and the scan is GitHub-only (M3, M4).** A comment claims the merged-artifact scan "degrade[s] to ls-remote ref scan … via ls-tree"; no `ls-tree` call exists anywhere. And the owner-parse strips only `github.com` URL forms, so on an Azure DevOps origin — a forge `partials/forge.sh` supports first-class — the artifact scan is silently skipped for **all** id kinds with no degradation flag.

The fix is one coherent rework of `adlc_remote_high`'s derivation and signaling, inherited by both `adlc_alloc_id` and `adlc_recheck_id`.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| RemoteHighResult | high_water | integer ≥ 0 | derived from max(branch scan, artifact scan) across repos |
| RemoteHighResult | degraded | boolean | true iff ANY derivation source for ANY participating repo was unavailable or failed |
| DerivationSource | kind | enum | `branch-scan` (ls-remote), `artifact-scan-gh`, `artifact-scan-git` (non-gh fallback) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| degraded-warning | any source unavailable/failed | which repo, which source, which id kind — emitted to stderr AND machine-readably to the caller |

## Business Rules

- [ ] BR-1: The branch scan and the merged-artifact scan are **independent derivation sources**: failure of one never skips the other for the same repo. The per-repo `continue` on `ls-remote` failure is removed; the artifact scan still runs for that repo. (adversarial C3)
- [ ] BR-2: Degradation is signaled through a channel that survives command substitution — the function's stdout payload or return code, not a parent-env variable. The signal is set whenever **any** source that should have run for the requested kind could not run or failed: `ls-remote` failure, `gh` absent, `gh api` failure, non-GitHub forge with no artifact path, or no fallback available. The stale "sets ADLC_ALLOC_DEGRADED in the CALLER's env" doc comment is corrected to the new contract. `adlc_recheck_id`'s degraded branch becomes reachable, and its renumber suggestion must never be computed from a degraded (possibly-zero) high-water. (adversarial C2, M1; informed by LESSON-015 — subshell state does not propagate)
- [ ] BR-3: For `kind=lesson` (and any future branch-less kind), the absence of a usable artifact scan is **always** a degraded condition with a stderr warning — never a silent return of 0. (adversarial C2; informed by LESSON-313 — the counter's scope is its scan root)
- [ ] BR-4: A non-`gh` merged-artifact fallback exists for GitHub remotes: derive the artifact listing from git transport alone (e.g. shallow fetch of the default branch tip + `git ls-tree` of the artifact paths, or an equally cheap read of the REMOTE's default branch — never the local working tree). If the implementation deliberately drops the fallback instead, the misleading "via ls-tree" comment is deleted and the no-`gh` case must surface as degraded per BR-2 — a comment may not promise a path that does not exist. Preference: implement the fallback. (adversarial M3; informed by LESSON-023 — mirror the rationale, not just the mechanism)
- [ ] BR-5: The artifact scan is forge-aware to the same degree as `partials/forge.sh`: on an Azure DevOps origin it performs an equivalent merged-artifact scan via the `az` CLI/REST (ADO is a confirmed adopter target platform, not a hypothetical — full parity, not degraded-with-warning). Any *other* non-GitHub origin flags degraded with a warning naming the unsupported forge; no origin ever silently skips the scan. (adversarial M4; informed by LESSON-392 — a probe must share the real call's resolution)
- [ ] BR-9: `adlc_forge_pr_merge` in `partials/forge.sh` passes provider-correct flags on the `azure-devops` branch: the gh-shaped `--squash` / `--delete-branch` arguments are translated to their `az repos pr update` equivalents instead of being forwarded verbatim (today an ADO merge from the workflow call sites errors out). Covered by a test exercising the ADO arg-translation path. (adversarial minor, promoted: ADO is a target platform)
- [ ] BR-6: `adlc_recheck_id` inherits every rule above through the shared helper; no recheck-only copy of the derivation logic is reintroduced. (REQ-518 BR-5 preserved)
- [ ] BR-7: All shell remains POSIX-, BSD-, and zsh-safe, and list iteration keeps the BUG-116 pattern (no word-split `for` over `$var`). Tests use multi-element fixtures. (informed by BUG-116, LESSON-399, LESSON-329, LESSON-335, LESSON-396)
- [ ] BR-8: Single-machine happy-path behavior is unchanged: with `gh` present, all remotes reachable, GitHub origins, the same ids are allocated as today. (REQ-518 BR-7 preserved)

## Acceptance Criteria

- [ ] Test: `ls-remote` fails but `gh api` shows a merged `REQ-800` → allocation returns ≥ 801 AND the result is flagged degraded (branch source failed).
- [ ] Test: `kind=lesson`, `gh` absent → result flagged degraded with a stderr warning; never a clean 0.
- [ ] Test: `adlc_recheck_id` under a degraded derivation takes the degraded branch (observable via its output) and emits no renumber suggestion derived from a zero high-water.
- [ ] Test: the degradation signal is observed by a caller using `$(adlc_remote_high …)` — i.e., the channel demonstrably survives command substitution under `sh`, `bash`, and `zsh`.
- [ ] Test (if BR-4 fallback implemented): `gh` absent, GitHub remote reachable over git transport → merged artifact ids are still derived.
- [ ] Test: Azure DevOps origin URL → merged artifact ids derived via the ADO path (parity with the GitHub scan); when `az` is genuinely unavailable, degraded is flagged with a forge-naming warning; never silent skip.
- [ ] Test: `adlc_forge_pr_merge` on the `azure-devops` branch issues `az`-correct arguments for a squash-merge-with-branch-delete call (BR-9); no gh-shaped flag reaches `az`.
- [ ] `partials/tests/` suite passes under both `bash` and `zsh`, with multi-element candidate lists in every new fixture.
- [ ] Happy-path regression: existing tests still produce identical allocations.

## External Dependencies

- `gh` CLI (optional — its absence must now degrade loudly, per BR-3); `git` ≥ a version supporting shallow single-branch fetch if BR-4's fallback uses one; `az` CLI required on Azure DevOps environments for BR-5/BR-9 (its absence there degrades loudly, mirroring the `gh` posture).

## Assumptions

- The mkdir-lock and its symlink/TOCTOU guards (LESSON-014) are correct and untouched; this REQ changes derivation and signaling inside the lock, not the lock.
- Callers of `adlc_alloc_id`/`adlc_recheck_id` in skill markdown can be updated in the same change if the stdout contract changes shape (the helpers are the only sanctioned entry points).

## Open Questions

- [ ] BR-4 mechanism: shallow fetch + `ls-tree` (no new dependency, some network cost) vs dropping the promise (cheaper, but no-`gh` machines stay degraded forever). Default if unanswered: implement shallow fetch + `ls-tree`.
- [x] ~~BR-5 bar: full ADO artifact scan now, or degraded-with-warning now?~~ Resolved 2026-06-12: full ADO scan now — Azure DevOps (with PySpark/Databricks targets) is a confirmed adopter environment, and the ADLC must work there without functional rework. BR-5 and BR-9 updated accordingly.

## Out of Scope

- Renumber content-rewrite safety (REQ-524).
- Any change to id formats, counter file locations, or the global-namespace policy.
- The delegation/telemetry findings (REQ-522).

## Retrieved Context

- BUG-116 (bug, score 5): zsh word-split in remote high-water candidate lists
- LESSON-399 (lesson, score 4): Single-element fixtures mask list-iteration bugs
- LESSON-313 (lesson, score 6): Global counter scope is its scan root
- LESSON-396 (lesson, score 7): Octal trap in shell id arithmetic
- LESSON-014 (lesson, score 3): Lock symlink TOCTOU
- LESSON-015 (lesson, score 4): Subshell exit does not propagate — same class as the degraded-flag defect
- LESSON-023 (lesson, score 3): Mirror the rationale, not just the mechanism
- LESSON-392 (lesson, score 4): Enablement probe must share real call resolution
- LESSON-329 (lesson, score 6): Dogfood skills under the executor shell
- LESSON-335 (lesson, score 6): zsh executor and arg-templating hazards
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure
- REQ-518 (spec, score 4): Collision-safe id allocation — the spec whose BR-2/BR-3/BR-4 this REQ repairs
