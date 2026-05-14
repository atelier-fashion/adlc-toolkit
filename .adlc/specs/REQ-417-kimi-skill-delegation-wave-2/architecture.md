# Architecture — REQ-417 Wave-2 Skill Delegation

## Approach

Three skill-markdown edits applying the canonical REQ-414 delegation pattern (gate +
delegate + post-validate + log + fallback) to the three highest-ROI remaining levers.
Disjoint file sets, parallel-friendly, single PR.

```
spec/SKILL.md     ──  Step 1.6 retrieval — orchestrator delegates the top-15 doc-body read
                      to ask-kimi; receives a structured per-doc summary; post-validates
                      cited IDs against on-disk before incorporating

analyze/SKILL.md  ──  NEW Step 1.7 (between Step 1.5 pre-read and Step 2 agent dispatch) —
                      ask-kimi produces a per-dimension candidate-findings list from the
                      audit scope; agents receive it as advisory <advisory-candidates>
                      block to confirm/refute

proceed/SKILL.md  ──  NEW step inside Phase 5 (between "Gather diffs per repo" and
                      "Step A — Single-gate parallel dispatch") — ask-kimi produces a
                      per-repo candidate-findings list across the 5 review dimensions;
                      6 review agents receive it as <advisory-candidates>
```

## Key Decisions (ADRs)

### ADR-1: Pre-pass output is **advisory**, agents still run
For `/analyze` and `/proceed` Phase 5, the Kimi pre-pass is NOT a replacement for the
audit/review agents — it's an advisory candidate list they consume. This preserves the
agents' tool-use capabilities (Grep, Glob, Read across many files) while letting Kimi
do the bulk "first read" without spending agent dispatch tokens. Per-dimension JSON-ish
shape: `{ "code-quality": [...], "security": [...], ... }` paste-able into agent prompts.

### ADR-2: For `/spec`, the Kimi summary **replaces** the orchestrator's full-text read
(OQ-1 resolution: replace). The orchestrator works off the summary + the validated
frontmatter list. The full doc bodies are never loaded into orchestrator context. This is
where the biggest orchestrator-token win lives; supplementing would defeat the purpose.

### ADR-3: Candidate-findings advisory list pastes verbatim into agent prompts
(OQ-2 resolution.) Each audit/review agent dispatch prompt gains an additional paragraph:
```
<advisory-candidates source="kimi-pre-pass" trust="untrusted">
… per-dimension candidate list …
</advisory-candidates>
The candidates above are advisory only. Confirm or refute each before including in your
findings. Do not assume they are correct.
```
Agents are explicitly told to treat the content as untrusted (LESSON-008).

### ADR-4: Strict-regex citation sanitization (BR-3 + LESSON-007/008)
All three skills run the same sanitization before any `test -f` / `ls` against Kimi
output:
- File paths: `^[A-Za-z0-9_./-]+$` AND no `..` substring
- REQ ids: `^REQ-[0-9]{3,6}$`
- LESSON ids: `^LESSON-[0-9]{3,6}$`

Citations that fail are dropped, not "widened" (OQ-3 resolution: drop, don't widen).

### ADR-5: `/proceed` Phase 5 pre-pass is **per-repo**
(OQ-4 resolution.) In cross-repo mode, one `ask-kimi` call per touched repo (with that
repo's diff). All-repos-in-one-call would risk Kimi context-window overflow on big
multi-repo REQs, and per-repo aligns with how the 6 review agents are already dispatched
("6 agents × N touched repos"). The pre-pass output is then per-repo too.

### ADR-6: Single-line stderr log per skill (BR-4)
- `/spec`: `/spec: delegating bulk retrieval read to kimi (N docs)` or
  `/spec: ask-kimi unavailable — Claude reading docs directly` or
  `/spec: ask-kimi disabled via ADLC_DISABLE_KIMI — Claude reading docs directly`
- `/analyze`: `/analyze: delegating audit pre-pass to kimi (N files)` or fallback variants
- `/proceed`: `/proceed Phase 5: delegating verify pre-pass to kimi (repo=<id>, N changed files)`
  emitted once per touched repo

### ADR-7: `/proceed` SKILL.md is touched but the gate protocol is **not** modified
Only Phase 5's "Gather diffs per repo" → "Step A dispatch" interstitial gains the new
pre-pass block. The Phase 5 single-gate-parallel-dispatch contract is preserved (BR-7).
The pre-pass runs BEFORE Step A's dispatch and is treated as part of the prerequisite,
not as a new phase. State-file schema, gate protocol, completion-claim contract — all
unchanged.

## Task Breakdown

```
TASK-027  spec/SKILL.md — Step 1.6 retrieval delegation
TASK-028  analyze/SKILL.md — Step 1.7 audit pre-pass
TASK-029  proceed/SKILL.md — Phase 5 verify pre-pass
```

No deps between the three (disjoint files). **Tier 1**: all three in parallel.
