---
id: REQ-380
title: "Drop /proceed Phase 7.5 (canary) and Phase 8a (snapshot promotion); reduce halt points 5 → 3"
status: approved
deployable: false
created: 2026-05-04
updated: 2026-05-04
component: "skills/proceed"
domain: "adlc"
stack: ["markdown"]
concerns: ["developer-experience", "reliability", "skill-correctness"]
tags: ["proceed", "canary", "snapshot-promotion", "phase-removal", "halt-contract", "paired-with-atelier-fashion-REQ-379", "global-counter-policy"]
---

## Description

This REQ removes two phases from the `/proceed` skill that misfit the dev → staging → main promotion topology used by atelier-fashion (and any future repo with a similar staging-only test model):

1. **Phase 7.5 — Canary Deploy.** Invokes `/canary` per touched service, which deploys a zero-traffic Cloud Run revision and then **promotes it to 100% production traffic** (`/canary` SKILL.md Step 5). In atelier-fashion, the resolved image path lands on the production GCP project — i.e., Phase 7.5 ships a feature-branch image straight to prod from `/proceed` before the code is even on `dev`. This contradicts the staging-only test model in which the heavy harness (real Anthropic / Gemini / SerpAPI / Twilio) gates dev → staging, and main push is a **byte-identical promotion** of the staging-validated image. A pre-merge production deploy from a feature branch defeats both gates simultaneously.

2. **Phase 8a — Create Promotion Snapshot.** Polls `staging` tip CI for greenness, then calls `scripts/git/create-promotion-snapshot.sh` to anchor a `promote/<short-sha>` branch and open the `staging → main` PR. /proceed orchestrates feature-branch → dev work; snapshot creation is staging → main mechanics on a different lifecycle and trigger. In practice (observed during atelier-fashion REQ-378's `/proceed` run on 2026-05-04), Phase 8a fires after the dev-merge at the end of every feature `/proceed`, then halts on the 30-min staging-poll timeout because the dev → staging promotion is operator-driven and almost never green at that wall-clock moment. Legitimate halt #5 was being exercised every single feature run.

Both removals reduce the autonomous-execution contract from **five legitimate halt points to three**. The remaining three are: (1) validation fails 3 times at any gate, (2) reflector surfaces user-facing questions, (3) merge conflicts during rebase. The Phase 8a 30-min snapshot-poll timeout halt and the canary-fails halt are gone with their phases.

### Pairing with atelier-fashion REQ-379

REQ-379 (atelier-fashion) ships a new GitHub Actions workflow `snapshot-promotion-on-staging-green.yml` that takes over Phase 8a's role: fires on `Unified CI Pipeline` completion against staging when `conclusion == 'success'`, calls the same `scripts/git/create-promotion-snapshot.sh` helper, opens the `promote/<sha>` PR. REQ-379 ships first; once it lands, the workflow creates promote PRs automatically. Phase 8a in `/proceed` continues to run during the overlap window — the helper script's 4-state idempotency machine returns `already_present` when Phase 8a fires after the workflow has already created the PR for the same staging SHA, so the duplicate path is observable but harmless.

REQ-380 ships second. Once it lands, Phase 8a is gone from `/proceed` and the workflow is the only producer.

Phase 7.5 has no replacement — the staging push CI's `deploy-fashion-api-staging` + `staging-integration-harness` jobs together provide a stricter equivalent gate (real-API harness vs. /canary's HTTP smoke checks). TestFlight is the iOS canary equivalent. Operators who genuinely need a manual production canary can still invoke `/canary` directly outside `/proceed`; the skill is not deleted.

### Distribution mechanics

`/proceed` SKILL.md is hard-linked into `~/.claude/skills/proceed/SKILL.md` from `~/Documents/GitHub/adlc-toolkit/proceed/SKILL.md` (verified by inode equality on 2026-05-04). The canonical source is this repo. A merge to `adlc-toolkit/main` distributes the change to anyone who has cloned adlc-toolkit and refreshed their hard-link wiring (or pulled the repo, if hard-link was created from a clone of main).

This REQ does NOT touch the hard-link mechanism itself — that's a separate operational concern (each developer's machine has its own link setup). This REQ only edits the canonical SKILL.md.

### Global REQ-counter policy adoption

This REQ is the first to use atelier-fashion's REQ counter as the **global counter** spanning both repos. atelier-fashion REQ-379 ships the policy update on its side (CLAUDE.md "Cross-Project Considerations"). This REQ mirrors the policy in adlc-toolkit's own `.adlc/context/project-overview.md` (or a new `CLAUDE.md` at the repo root if cleaner) so future allocations from this repo continue to take the next slot above atelier-fashion's high-water rather than incrementing adlc-toolkit's old local counter (which last reached REQ-263). Existing adlc-toolkit specs (REQ-258, REQ-262, REQ-263) keep their numbers — the policy applies to new allocations only, and the gap from REQ-264 through REQ-379 is intentional.

## System Model

This REQ does not touch the data model. It changes orchestration topology only.

### Triggers and side-effects

| Trigger | Side-effect (today, before this REQ) | Side-effect (after this REQ) |
|---|---|---|
| `/proceed REQ-xxx` for a `deployable: true` REQ reaches Phase 7.5 | Phase 7.5 runs: invokes `/canary` per service, deploys zero-traffic Cloud Run revision, promotes to 100% prod traffic (from a feature branch, pre-dev-merge). | Phase 7.5 is gone. /proceed advances directly from Phase 7 (PR Cleanup & CI) to Phase 8 (Wrapup). No production deploy occurs from /proceed under any circumstances. |
| `/proceed REQ-xxx` completes successfully on a repo with `pipeline.snapshot_promotion: true` | Phase 8a polls staging tip CI for ≤30 min, calls helper script, opens promote PR. | Phase 8a is gone. /proceed ends at Phase 8. The `pipeline.snapshot_promotion` config key is preserved in the schema for read-back compatibility but no longer drives any /proceed behavior. |
| `Unified CI Pipeline` succeeds on push:staging in atelier-fashion | (Today: no automatic promote-PR creation; /proceed Phase 8a is the only auto producer.) | Unchanged from REQ-379 ship: the new workflow `snapshot-promotion-on-staging-green.yml` is the sole producer once REQ-380 lands and Phase 8a is gone. |
| Operator runs `/canary` directly (outside /proceed) | Same as today: deploys zero-traffic prod Cloud Run revision, smoke-tests, promotes to 100% on success. | Unchanged. /canary remains a standalone skill for ad-hoc production canary deploys. Only its `/proceed` embedding is removed. |

## Business Rules

- [ ] BR-1: `proceed/SKILL.md` MUST be amended to **remove Phase 7.5 (Canary Deploy) entirely**. The Phase 7.5 section heading, body, and any cross-references in earlier sections (the autonomous-execution contract preamble, Phase 7's "After completion" line, Phase 8's "Gate" line) MUST be deleted or rewritten so the phase no longer exists.
- [ ] BR-2: `proceed/SKILL.md` MUST be amended to **remove Phase 8a (Create Promotion Snapshot) entirely**. The Phase 8a section heading and body MUST be deleted. The Phase 8 gate clause that references "either `8a` or `7.5` (or `7`) must be in `completedPhases`" MUST be simplified to "`7` must be in `completedPhases`". Any prose elsewhere in the skill referencing `pipeline.snapshot_promotion` as a behavior toggle MUST be deleted; the config key itself stays valid in `.adlc/config.yml` schemas (per BR-5) but no longer drives skill logic.
- [ ] BR-3: The autonomous-execution contract preamble (currently "**five** legitimate halt points") MUST be rewritten to **three**. The numbered list MUST be exactly: (1) validation fails 3 times at any gate, (2) reflector surfaces user-facing questions, (3) merge conflicts during rebase. The "Canary deploy fails (Phase 7.5)" and "Phase 8a 30-minute polling timeout" entries MUST be deleted. Other prose in that section (the "writing logs vs asking questions" rule, the tool-permission carve-out) MUST be preserved verbatim.
- [ ] BR-4: The phase-list summary at the top of "The Pipeline" MUST be updated to reflect the new shape: 0, 1, 2, 3, 4, 5, 6, 7, 8 (no 7.5, no 8a). Any text that says "Phase 7 → Phase 7.5 → Phase 8" or similar MUST become "Phase 7 → Phase 8".
- [ ] BR-5: The `pipeline-state.json` schema documentation in `proceed/SKILL.md` MUST mark `repos.<id>.snapshotBranch` and `repos.<id>.snapshotPR` as **deprecated** (kept as nullable fields for read-back compatibility on older state files). The skill MUST stop writing those fields. Any Phase-7.5-owned fields that the current skill writes (audit `proceed/SKILL.md` for Phase 7.5's state writes — none currently exist per a 2026-05-04 grep, but the architecture phase MUST re-verify) follow the same deprecation rule. Existing state files with these fields populated MUST continue to load without error.
- [ ] BR-6: The Gate Protocol step that mentions Phase 8a's gate ("`7.5` (or `7`) must be in `completedPhases`") and any other inline phase-number references MUST be updated to reflect the new flow. Cross-reference annotations like "(or directly to Phase 8 if `pipeline.snapshot_promotion` is unset/false)" in Phase 7.5's end-of-phase log MUST be removed along with Phase 7.5.
- [ ] BR-7: `canary/SKILL.md` description and body MUST be audited for any reference to `/proceed` Phase 7.5 as its caller. Any such reference MUST be removed or annotated to reflect the new "manual-only" status (`/canary` is now invoked directly by operators, never auto-invoked by `/proceed`). The skill itself MUST NOT be deleted or restructured beyond this annotation.
- [ ] BR-8: adlc-toolkit's REQ-numbering policy MUST be updated to declare that future REQ allocations from this repo take the next slot above atelier-fashion's high-water (the global counter), not above adlc-toolkit's local high-water (currently REQ-263). The policy MUST land in adlc-toolkit's `.adlc/context/project-overview.md` (or a new `CLAUDE.md` at the repo root, whichever the architecture phase determines is the canonical operator-facing doc location) with the same rationale and intentional-gap clause that atelier-fashion REQ-379 lands on its side.
- [ ] BR-9: A wrapup lesson in `.adlc/knowledge/lessons/` MUST capture: (a) the topology mismatch that drove Phase 7.5 / 8a removal, (b) the REQ-379 / REQ-380 ship-order rationale (overlap window safety via `already_present`), (c) the global-counter policy adoption and the intentional REQ-264-to-REQ-379 gap.

## Acceptance Criteria

- [ ] `proceed/SKILL.md` no longer contains a `Phase 7.5` section OR a `Phase 8a` section. The phase list goes 6 → 7 → 8 (no 7.5, no 8a).
- [ ] The "legitimate halt points" preamble says "**three**" and lists exactly: (1) validation fails 3 times, (2) reflector surfaces user-facing questions, (3) merge conflicts during rebase.
- [ ] All inline phase-number cross-references in `proceed/SKILL.md` (Gate clauses, end-of-phase logs, the Pipeline State Tracking section's schema example, error-handling section) are consistent with the new phase list.
- [ ] `pipeline-state.json` schema documentation marks `snapshotBranch` and `snapshotPR` as deprecated; the skill no longer writes those fields. Old state files with the fields still load without error.
- [ ] `canary/SKILL.md` is audited; any /proceed-Phase-7.5 cross-reference is removed or annotated. The skill remains invocable as a standalone command with no other behavior changes.
- [ ] Running `/proceed` against a `deployable: true` REQ (e.g., a re-run of any historical deployable REQ) ends cleanly at Phase 8 (merge to dev) without invoking `/canary` and without polling staging. No production Cloud Run revisions are created by `/proceed` under any circumstances. Verify by inspecting a /proceed dry run's phase-list output.
- [ ] adlc-toolkit's operator-facing doc (project-overview.md or new CLAUDE.md) carries the global REQ-counter policy with the same wording and rationale as atelier-fashion REQ-379's side.
- [ ] The wrapup lesson exists at `.adlc/knowledge/lessons/<date>-req-380-...md` with the three required content blocks.
- [ ] No application code is touched. The diff is: `proceed/SKILL.md` edits + `canary/SKILL.md` annotation (small) + adlc-toolkit operator-facing doc + wrapup lesson.
- [ ] After this REQ ships and a fresh /proceed runs end-to-end, no `phase_8a_*` or `canary_*` log lines appear in its output.

## External Dependencies

- atelier-fashion REQ-379 must have shipped (or be in flight far enough that its workflow is live on `staging` push) for the overlap-window invariant to hold safely. If REQ-380 ships before REQ-379, there's a window where neither Phase 8a nor the workflow creates promote PRs automatically — operators would have to invoke `scripts/git/create-promotion-snapshot.sh` manually. Architecture phase MUST verify REQ-379's ship status before queueing this REQ for merge.

## Assumptions

- `proceed/SKILL.md` is the single source of truth for Phase 7.5 / 8a definitions. (Verified by grep on 2026-05-04: only this file mentions those phases by number.)
- `canary/SKILL.md` may not actually reference Phase 7.5 — BR-7's audit may turn up nothing to change, in which case BR-7 is satisfied vacuously. Verify during architecture phase.
- No active /proceed session anywhere (across atelier-fashion's `.worktrees/`) has `currentPhase: "7.5"` or `"8a"` recorded in its `pipeline-state.json`. (Verified by grep across `~/Documents/GitHub/atelier-fashion/.worktrees/*/.adlc/specs/*/pipeline-state.json` on 2026-05-04 — none found.) If any do, the skill amendment includes a one-line operator note for manual phase advancement.
- The `pipeline.snapshot_promotion` config key in `.adlc/config.yml` may remain present in atelier-fashion's config after this REQ — that's harmless. The schema-level removal of the key (in any /init template that mentions it) is a follow-up cleanup, not in scope here.
- atelier-fashion's CLAUDE.md is the operator-facing doc that pairs with adlc-toolkit's `.adlc/context/project-overview.md`. The architecture phase MUST decide whether adlc-toolkit gets a new `CLAUDE.md` or whether project-overview.md is the right home for the policy mirror — both are legitimate.

## Open Questions

- [ ] Should the `pipeline.snapshot_promotion` config-key documentation in `proceed/SKILL.md` be deleted entirely (since the skill no longer reads it) or annotated as "reserved / no-op since REQ-380"? Recommend: delete from skill docs, leave the actual config-key schema definition (if any) to a separate /init template cleanup REQ.
- [ ] Does removing the snapshot-promotion logic affect any existing adlc-toolkit tests / docs / templates? Recommend an architecture-phase grep across this repo for `Phase 8a`, `snapshot_promotion`, and `Phase 7.5` to size the blast radius before tasks are written.
- [ ] Should the wrapup lesson be co-authored across both repos (atelier-fashion REQ-379 + adlc-toolkit REQ-380) or kept separate? Recommend: separate, with each repo's lesson cross-referencing the other. Atelier-fashion's lesson focuses on the workflow-side rationale; this repo's lesson focuses on the skill-side rationale.

## Out of Scope

- **Editing the new workflow file `snapshot-promotion-on-staging-green.yml`.** That's atelier-fashion REQ-379's deliverable. This REQ only removes the /proceed phase that the workflow now obsoletes.
- **Deleting or rewriting the `/canary` skill itself.** Only the /proceed embedding is removed plus a one-line description annotation if needed. Decisions about whether `/canary` should be re-targeted at staging, deprecated, or kept as-is are explicitly out of scope — addressing them would require a separate REQ scoped to the skill's own design.
- **Modifying `scripts/git/create-promotion-snapshot.sh`.** It is the contract; both REQ-379 (workflow) and Phase-8a-during-overlap-window consume it unchanged.
- **Backfilling adlc-toolkit specs to fill the REQ-264 to REQ-379 gap.** The gap is intentional and is the price of fast-forwarding to a global counter.
- **Removing `pipeline.snapshot_promotion` from `.adlc/config.yml` schemas / `/init` templates.** The key becomes a no-op after REQ-380; cleaning up the template is a follow-up.
- **Updating the `pipeline-state.json` JSON schema file (if one exists separately from the SKILL.md prose).** This REQ updates the prose documentation; if a separate schema file exists, that's a follow-up.

## Retrieved Context

- atelier-fashion REQ-379 (paired sibling, off-repo): owns the `snapshot-promotion-on-staging-green.yml` workflow + atelier-fashion-side CLAUDE.md edits (zero-api-diff annotation + global-counter policy). REQ-379 ships first; this REQ follows.
- atelier-fashion REQ-378 verify cycle (off-repo, 2026-05-04): the conversation that surfaced the Phase 8a misfit. REQ-379 + REQ-380 are the carve-out.
- `proceed/SKILL.md` Phase 7.5 (line ~438) and Phase 8a (line ~456) sections: the literal text being deleted.
- `canary/SKILL.md`: the skill that Phase 7.5 invokes. Step 5 ("Promote to Production") confirms the production deploy target — the basis for dropping Phase 7.5.
- atelier-fashion `.adlc/config.yml` `services.atelier-fashion.image_path` field: resolves to `sharp-maker-488811-g1` (production GCP project). Establishes Phase 7.5's deploy target as production, not staging.
- atelier-fashion CLAUDE.md "CI/CD / Branch-specific behavior" + "Per-feature dual-promotion" subsections: the staging-only test model and dual-promotion flow that Phase 7.5 / 8a are incompatible with.
