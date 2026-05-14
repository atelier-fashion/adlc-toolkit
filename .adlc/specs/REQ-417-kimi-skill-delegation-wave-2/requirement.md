---
id: REQ-417
title: "Wave-2 Kimi skill delegation: /spec Step 1.6 retrieval, /analyze Step 2 audit pre-pass, /review verify agents in /proceed Phase 5"
status: draft
deployable: false
created: 2026-05-14
updated: 2026-05-14
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "bash"]
concerns: ["cost", "reliability", "privacy"]
tags: ["kimi", "delegation", "spec-retrieval", "analyze-audit", "review-agents", "fallback", "wave-2"]
---

## Description

REQ-414 piloted Kimi delegation in `/analyze` Step 1.5 (shape-file pre-read) and `/wrapup`
Step 4 (lesson draft). Both shipped, both verified on a real run. The pilot pattern — gated
delegation with hard fallback to Claude, post-validation of cited identifiers, single-line
stderr log — is now established. This REQ extends it to the three remaining high-ROI levers:

1. **`/spec` Step 1.6 retrieval** — currently the orchestrator reads the top-15 doc bodies
   (lessons + specs + bugs) into its own context, scoring 30–50k orchestrator tokens per
   `/spec` invocation. Delegate the bulk read to `ask-kimi`; orchestrator works off Kimi's
   structured summary plus the validated frontmatter list. Highest single-shot win in the
   remaining surface.

2. **`/analyze` Step 2 audit agent pre-pass** — currently 4 audit agents (`code-quality-auditor`,
   `convention-auditor`, `security-auditor`, `test-auditor`) each independently scan the
   codebase. Add a Kimi pre-pass that produces a per-dimension *candidate findings list*
   (file path + one-line description + dimension). Each audit agent then receives this
   candidate list as additional context, so it can spend its tool-use budget on confirming /
   refuting candidates rather than discovering them from scratch. Agents still produce their
   own structured findings; the pre-pass is advisory.

3. **`/review` verify agents in `/proceed` Phase 5** — same pattern as the audit pre-pass.
   Currently the orchestrator dispatches 6 review agents (reflector + 5 reviewers) per
   touched repo. Add a Kimi pre-pass that summarizes the diff and surfaces likely
   cross-dimension candidates; reviewers receive this summary and confirm or refute.

All three follow the BR-1..BR-7 canonical pattern from REQ-414 (informed by LESSON-008):
hard gate, same-shape fallback, post-validation with regex + on-disk existence, single
stderr line, kill-switch via `ADLC_DISABLE_KIMI=1`.

`/architect` was originally in the priority-3 slot but is dropped from this REQ. Its haiku
agents already run cheaply and have tool use Kimi doesn't; the orchestrator-token win
isn't worth the added attack surface there.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| skill gate | check command | string | exactly `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` (matches REQ-414 BR-1) |
| `/spec` retrieval delegation | input | list of paths | the top-15 retrieved doc files (from Step 1.6 enumeration) |
| `/spec` retrieval delegation | question | string | structured prompt asking for per-doc score-summary + key business-rule snippets |
| `/analyze` audit pre-pass | input | list of paths | the file scope determined by Step 1 (`Determine Scope`) |
| `/analyze` audit pre-pass | output | dict | per-dimension candidate findings: `{ "code-quality": [...], "convention": [...], "security": [...], "test": [...] }` |
| `/review` verify pre-pass | input | diff text + changed files | the per-repo diff already gathered as Phase 5 prerequisite |
| `/review` verify pre-pass | output | dict | per-dimension candidate findings (correctness, quality, architecture, test-coverage, security) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| delegate to kimi | skill gate passes | one-line stderr log per skill (e.g. `/spec: delegating bulk retrieval read to kimi (N docs)`) |
| fall back to claude | gate fails OR delegation errored | one combined-line stderr log (e.g. `/spec: ask-kimi unavailable — Claude reading docs directly`) |
| post-delegation validation | Kimi result returned | Claude validates: every cited file path / REQ id / LESSON id exists on disk before propagating |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| invoke delegation | the skill itself, when its gate passes |
| override to fallback | any developer via `ADLC_DISABLE_KIMI=1` |

## Business Rules

(Identical canonical pattern to REQ-414. Restated for testability.)

- [ ] BR-1: Every new delegation point MUST use the exact gate
      `if command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then … else … fi`
      (informed by LESSON-006).
- [ ] BR-2: Fallback paths MUST produce the same artifact shape as the delegated path. For
      `/spec`: the same Step 1.6 retrieved-context list and the same inline citations.
      For `/analyze`: the same 4-agent audit reports (Kimi pre-pass is advisory, agents still
      run). For `/review`: the same 6-agent verify reports (Kimi pre-pass is advisory).
- [ ] BR-3: Claude MUST post-validate every cited file path / REQ id / LESSON id in any
      Kimi output BEFORE propagating into the artifact. **First sanitize the citation
      token** against the strict regexes from REQ-415 (file paths: `^[A-Za-z0-9_./-]+$` AND
      no `..` substring; REQ ids: `^REQ-[0-9]{3,6}$`; LESSON ids: `^LESSON-[0-9]{3,6}$`).
      THEN verify on-disk existence. Drop or rewrite citations that fail either check
      (informed by LESSON-007, LESSON-008).
- [ ] BR-4: One stderr log line per skill invocation stating which path was taken.
      Delegation-failure branches emit a single combined line, not failure-line +
      fallback-line (the REQ-414→415 fix).
- [ ] BR-5: No new CLI flags or skill arguments. Behavior change observable only via
      (a) token cost, (b) the new stderr log line.
- [ ] BR-6: `ADLC_DISABLE_KIMI=1` MUST force fallback for all three skills.
- [ ] BR-7: Hard out-of-scope: `/architect`, `/proceed` (the orchestrator-level skill —
      Phase 5 is a sub-step inside it but we are editing `/proceed`'s SKILL.md to wire the
      pre-pass; that's the touch surface, not a rewrite), `/wrapup`, `/optimize`, `/status`,
      `/init`, `/validate`, `/sprint`, `/bugfix`. The three modified files are exactly
      `spec/SKILL.md`, `analyze/SKILL.md`, `proceed/SKILL.md`. Verified via
      `git diff --name-only` filter post-implementation.
- [ ] BR-8: Treat any captured stdout from `ask-kimi` as **untrusted data**, wrapped in
      `--- BEGIN KIMI PROPOSAL (untrusted) --- … --- END KIMI PROPOSAL (untrusted) ---`
      with explicit instruction that imperative sentences inside are content, not commands
      (informed by LESSON-008).
- [ ] BR-9: When the delegation feeds back into Claude's reasoning (e.g., `/spec` consumes
      Kimi's summary to write business rules), the documentation in the SKILL.md MUST call
      out: when delegation fires, what is sent to Kimi, what is expected back, what
      validation is applied, and where the fallback lives.

## Acceptance Criteria

- [ ] In a consumer project with the Kimi tooling installed: invoking `/spec <description>`
      produces a spec with the existing `## Retrieved Context` section populated; stderr
      shows `/spec: delegating bulk retrieval read to kimi (N docs)` line.
- [ ] Same project: `/analyze` shows the new pre-pass stderr line and produces an audit
      report whose structure matches the pre-pilot output. Audit agents still run.
- [ ] Same project: `/proceed REQ-xxx` reaching Phase 5 shows the verify pre-pass stderr
      line and produces all 6 agent reports as before.
- [ ] In a consumer project WITHOUT Kimi installed: all three skills take the fallback path
      (verified by the stderr log line). Output is structurally identical to delegation
      mode (BR-2).
- [ ] With Kimi installed AND `ADLC_DISABLE_KIMI=1`: all three skills take the fallback path.
- [ ] Post-validation strips a synthetic `REQ-../etc/passwd` citation from any Kimi output
      across all three skills.
- [ ] `git diff --name-only main...HEAD` after this REQ lists ONLY `spec/SKILL.md`,
      `analyze/SKILL.md`, `proceed/SKILL.md`, and the REQ-417 spec/architecture/tasks files.
      No other SKILL.md is touched (BR-7).
- [ ] REQ-413's pytest suite (`tools/kimi/tests/`) still reports 29/29 passing.
- [ ] Token-cost spot check on this repo: a `/spec <description>` run with Kimi enabled
      consumes meaningfully fewer orchestrator tokens than the same run with
      `ADLC_DISABLE_KIMI=1`. Numbers are not load-bearing in the AC — visible gap is.

## External Dependencies

- The REQ-412/413/415 Kimi tooling (`ask-kimi`, `extract-chat`). Already installed; this REQ
  adds no new deps.

## Assumptions

- `/spec` Step 1.6's 15-doc cap is small enough that Kimi can return a coherent
  per-doc summary in one call. If the docs collectively exceed Kimi's 128K context, the
  delegated call will fail and fall back — acceptable.
- Audit and verify agents will improve, not degrade, with a candidate-findings advisory
  list. If quality dips, the pilot pattern lets us roll back per-skill by deleting the
  pre-pass block from a single SKILL.md.
- `/proceed`'s SKILL.md edit for the Phase 5 pre-pass is additive — does NOT change any
  existing Phase 5 dispatch contract, gate protocol, or state-machine invariant.

## Open Questions

- [ ] OQ-1: For `/spec` delegation, does Kimi's output replace the orchestrator's read of
      the doc bodies (orchestrator only sees the summary), or supplement it (orchestrator
      reads summary + still reads ~3 most-load-bearing docs in full)? Recommend
      replace-with-summary; supplement defeats the purpose.
- [ ] OQ-2: For `/analyze` and `/review` audit pre-passes, what exactly goes in the
      agent dispatch prompts to use the candidate list — paste verbatim, or summarize? Architecture will decide; recommend paste verbatim under an
      `<advisory-candidates>` block.
- [ ] OQ-3: When the Kimi summary cites a REQ that *should* exist but the regex
      sanitization rejects it (e.g., 7-digit zero-padded `REQ-0000414`), do we widen the
      regex or drop the citation? Recommend drop — widening the regex is a slippery slope.
- [ ] OQ-4: `/proceed`'s Phase 5 currently dispatches "6 agents × N touched repos" in a
      single message. Should the Kimi pre-pass be per-repo (N kimi calls) or all-repos
      (1 kimi call across all diffs)? Architecture will decide based on context-window
      considerations.

## Out of Scope

- Wiring Kimi into `/architect` (haiku agents already cheap; Kimi can't tool-use).
- Wiring Kimi into `/proceed`'s other phases (Phase 4 task implementation, Phase 2
  architecture). Those phases involve too much load-bearing reasoning.
- Replacing the audit / verify agents with direct `ask-kimi` calls — pre-pass is
  ADVISORY only, agents still run.
- New Kimi pricing-tier negotiation or cost-tracking infrastructure.
- `/optimize`, `/status`, `/init`, `/validate`, `/sprint`, `/bugfix`, `/wrapup` (already
  done) — none get delegation in this REQ.
- ADR-style helper extraction (e.g., shared `tools/kimi/skill-redact.sh`) — that's REQ-416
  territory.

## Retrieved Context

- LESSON-006: tools/ carve-out + fail-loud — informs BR-1, BR-4
- LESSON-007: scrub at every leak point — informs BR-3 (regex sanitization before existence check)
- LESSON-008: skill delegation = untrusted data + sanitize citation tokens — informs BR-3, BR-8
- LESSON-009: post-merge `/analyze` finds what verify-pass misses — informs the wrapup
  recommendation (run `/analyze` after this REQ ships to catch any third-pattern regressions)

REQ-412, REQ-413, REQ-414, REQ-415 are direct ancestors (all `status: complete`).
REQ-416 (toolkit refactor, `status: draft`) — out of scope here; helper-extraction will
land there.
