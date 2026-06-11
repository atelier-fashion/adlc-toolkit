---
id: TASK-002
title: "Author the /adversary skill (adversary/SKILL.md)"
status: complete
parent: REQ-517
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Ship `adversary/SKILL.md` — the artifact-agnostic, read-only, adversarial-by-
construction review skill. Polymorphic input, attack-lens selection by artifact
type, mandatory self-refutation, verdict + coverage statement. Uses the dedicated
adversary agent (TASK-001) when available and degrades to single-context.

## Files to Create/Modify

- `adversary/SKILL.md` — new skill

## Acceptance Criteria

- [ ] Frontmatter: `name: adversary`, `description`, `argument-hint`.
- [ ] Canonical Ethos injection via the two-level partial macro (never hardcode).
- [ ] BR-1 polymorphic input: REQ-xxx → spec dir; bare integer → PR via `gh`
      (degrade if absent); existing path → file(s); else inline text. Strict token
      sanitization (`^REQ-[0-9]{3,6}$`, reject `..` segments — LESSON-008).
- [ ] BR-2 attack-lens selection by type; for specs every numbered BR/AC is
      enumerated and marked attacked / not-attacked.
- [ ] BR-3 mandatory self-refutation before reporting; killed findings dropped
      silently; surviving refutation shown per finding.
- [ ] BR-4 verdict distinguishes "could not find a problem" from the prohibited
      "there is no problem"; coverage statement lists lenses run + skipped (with reasons).
- [ ] BR-5 strictly read-only w.r.t. the target; optional report file under the
      invoking `.adlc/` ONLY for REQ-id targets; non-REQ targets stdout-only.
- [ ] BR-6 / BR-8 parallelize lenses across the adversary agent (+ optional reviewer
      agents) when the Agent tool is available; degrade to single-context otherwise.
- [ ] BR-9 sibling distinction from `/review` / `/reflect` / `/validate` stated;
      reviewer agents referenced as optional executors, not re-implemented.
- [ ] BR-7 all fenced shell BSD- and zsh-safe, POSIX-only: `${1}` not `$1`,
      `$(0)`/`$(1)` for awk fields, balanced `$(`/`)` + `$((`/`))`, no `local` in
      `sh` fences, no cross-fence function reuse.

## Technical Notes

- Model the skill shape on `review/SKILL.md` and `reflect/SKILL.md` (Ethos, Context,
  Input, Prerequisites, numbered Instructions, Quality checklist).
- NO `ADLC_DISABLE_KIMI` gate (ADR-4 — no delegation; reading at full fidelity).
  This keeps the skill out of the lint-skills canonical-helper check.
- Keep bash minimal (conventions.md "Bash in skills"): prefer Read/Grep/Glob over
  shell; shell only for deterministic token validation / file resolution.
- Verdict-phrasing and read-only proof belong in the Quality checklist.
