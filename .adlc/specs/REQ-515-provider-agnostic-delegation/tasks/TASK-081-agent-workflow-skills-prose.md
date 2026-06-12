---
id: TASK-081
title: "Rename pre-pass agent + neutralize workflow, 4 skills, conventions prose"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-079]
---

## Description

Update the remaining live consumers (BR-6, BR-10): the pre-pass agent rename, the
sprint workflow's agentType/prompt strings, the four delegating SKILL.md prose,
and the conventions "Kimi delegation pattern" section. Source-lines stay valid via
the TASK-079 wrappers, so SKILL.md gate-wiring does not change — only prose.

## Files to Create/Modify

- `agents/kimi-pre-pass.md` → `agents/delegate-pre-pass.md` (git mv) — neutralize
  body: "Kimi" → "the delegate", `ask-kimi` → `adlc-read`, key check via resolved
  key; preserve the untrusted-data / citation-sanitization contract verbatim (BR-10).
- `workflows/adlc-sprint.workflow.js` — `agentType: 'kimi-pre-pass'` →
  `'delegate-pre-pass'`; neutralize prompt text and comments; keep
  `MOONSHOT_API_KEY` env mention only where it is the legacy default key.
- `analyze/SKILL.md`, `spec/SKILL.md`, `proceed/SKILL.md`, `wrapup/SKILL.md` —
  neutralize prose ("Kimi"→"the delegate", "ask-kimi"→"adlc-read") in narrative
  text; KEEP the canonical source-lines and telemetry blocks unchanged (the
  wrappers keep them valid; changing them risks lint breakage and is unnecessary).
- `.adlc/context/conventions.md` — rewrite the "Kimi delegation pattern" section
  provider-neutral, pointing at `delegate-gate.sh` (and noting the legacy wrapper).
- `partials/README.md`, `partials/emit-step-telemetry.md` — neutralize references.

## Acceptance Criteria

- [ ] Workflow dispatches `delegate-pre-pass`; no live reference to the old agent
      name remains except labeled back-compat.
- [ ] The 4 skills read provider-neutral; their gate/telemetry source-lines are
      unchanged and still satisfy `lint-skills`.
- [ ] The pre-pass agent's untrusted-data + sanitization language is preserved
      (provider-neutralized, not weakened) (BR-10).
- [ ] conventions.md "delegation pattern" section is provider-neutral.

## Technical Notes

- Be conservative editing SKILL.md fenced blocks — the canonical source-lines
  (`. .adlc/partials/kimi-gate.sh …`) MUST stay byte-identical (the wrappers make
  them work); only narrative prose around them changes. This keeps the lint
  canonical check green without touching TASK-082's lint logic for skills.
- Corpus grep before declaring done: `grep -rn 'ask-kimi\|kimi-write\|Kimi'` over
  skills/agents/partials/workflows/tools (excluding shims, wrappers, labeled
  back-compat, historical specs/lessons/bugs) must be empty.
