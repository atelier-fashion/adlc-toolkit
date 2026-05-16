---
id: REQ-437
title: "Reconcile lint-skills canonical-helper rule with the REQ-416 ADR-2 kimi-gate.sh migration"
status: superseded
deployable: false
created: 2026-05-16
updated: 2026-05-16
superseded_by: REQ-433
component: "adlc/lint-skills"
domain: "adlc"
stack: ["python", "markdown"]
concerns: ["maintainability", "correctness", "tooling-drift"]
tags: ["lint-skills", "canonical-helper", "kimi-gate", "skill-md", "tooling-drift", "kimi-delegation", "linter"]
---

> **SUPERSEDED (2026-05-16) — do not merge PR #52.**
> While this REQ's `/proceed` pipeline was running, **REQ-433** merged to
> `main` (PRs #50, #51; `main` 04ba690 → 7dfc646). REQ-433's **TASK-046 was
> reopened in its own Phase 4 ("Addendum ADR-3a")** and made the *identical*
> fix this REQ implements: replacing the obsolete inline `command -v ask-kimi …`
> canonical literal with `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`,
> with the same `kimi-gate-ok.md` rewrite and the same test/README cascade —
> plus REQ-433's own emit-literal swap (`"$KIMI_TOOLS"/emit-telemetry.sh `) and
> a 5th `kimi-tools-path.sh` resolver-source literal. `main`'s `check.py`
> literal #4 is byte-identical to this REQ's; the linter over the 4 skills on
> `main` already reports **0 `canonical-helper` findings**. The original task
> premise ("REQ-433/TASK-046 … scoped not to touch it") was true when written
> but invalidated by TASK-046's mid-flight reopen+extend. This REQ is therefore
> redundant; force-merging PR #52 would *regress* REQ-433 (drop literal #5 and
> the emit-swap) and ship a test invalid in the 5-literal world. Closed unmerged.
> Pipeline halted at Phase 7 (legitimate halt #3 + supersession); user elected
> to close as superseded.

## Description

`tools/lint-skills/check.py` `CANONICAL_LITERALS` carries four exact substrings that every `SKILL.md` containing the `ADLC_DISABLE_KIMI` anchor must contain (REQ-425 BR-5 / its System Model `kimi-gate-form` rule). Literal #4 is the **inline** gate predicate:

```
command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]
```

REQ-425 was authored (2026-05-15) when the four Kimi-aware skills still inlined that predicate. REQ-416 (toolkit-refactor, ADR-2, also landed ~2026-05-15) then migrated `analyze/SKILL.md`, `proceed/SKILL.md`, `spec/SKILL.md`, and `wrapup/SKILL.md` to **source the shared `partials/kimi-gate.sh` predicate** instead of inlining it. Those skills now contain `ADLC_DISABLE_KIMI` only in prose / `case`-arm comments and no longer contain the inline form anywhere — not even verbatim inside `kimi-gate.sh`, which decomposes the predicate into a negated `command -v` early-return plus a separate `[ "${ADLC_DISABLE_KIMI:-0}" = "1" ]` branch. (informed by REQ-425, REQ-416)

Consequence: running `tools/lint-skills/check.py` over the toolkit's own four skills (i.e. dogfooding `/analyze` Step 1.9 on this repo) emits **exactly four spurious `canonical-helper` findings — one per skill — all for literal #4**. Literals 1–3 (`start_s=$(date -u +%s)`, `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`, `tools/kimi/emit-telemetry.sh `) are present in all four skills and are unaffected.

This is **pre-existing and independent of REQ-433**: the identical four findings reproduce when `check.py` and the four skills are checked out at commit `04ba690` (this worktree's merge-base, pre-REQ-433). REQ-433/TASK-046 only swapped the emit literal and added a telemetry-resolver-source literal; it was scoped not to touch the gate literal and did not introduce or alter this issue.

**Decision (option a): replace canonical literal #4 with the byte-exact, stable gate-source substring all four migrated skills now share to wire up the gate:**

```
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
```

Rationale: the check's *intent* — "a Kimi-gated skill must correctly wire up the gate machinery, so a literal-but-broken corruption of that wiring is caught" (the whole point of REQ-425) — remains valid; only the *form* moved from an inlined predicate to a sourced partial. The gate-source line is the post-REQ-416-ADR-2 analog of the inline predicate, is present byte-for-byte in all four skills, and is the exact analog of the telemetry-resolver-source literal REQ-433 adds via the same REQ-416 ADR-2 vendored-first-then-global idiom. `check_canonical` uses `literal in text` substring semantics, so the differing leading indentation across skills (`spec/SKILL.md` indents the line 3 spaces; the others do not) does not matter. (informed by LESSON-016 — the linter's checks are substring-counted, not parsed)

**Option (b) — dropping the canonical-helper check entirely — was rejected**: it would surrender corruption coverage on the single most load-bearing line of the post-migration gate wiring (a mangled `2>/dev/null ||` or a truncated partial path would then ship undetected), which is precisely the literal-but-broken-shell failure class REQ-425 exists to catch. (informed by LESSON-012 — structural enforcement beats prose review)

The fix is a code/spec/test/fixture/doc change confined to `tools/lint-skills/`. Per LESSON-016, the `kimi-gate-ok.md` fixture is not an edge case but the **canonical happy-path regression guard** for this rule and must move in lockstep so it still asserts clean. The four `SKILL.md` files MUST NOT be edited to satisfy the linter — the linter is reconciled to reality, not the reverse (mirrors REQ-425 BR-11 / REQ-428's "keep the canonical-helper rule passing without contorting the skill").

## System Model

_Only the canonical-helper rule's literal set changes. No runtime entities, events, or permissions — this is a lint-rule definition + its tests/fixtures/docs._

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| `CANONICAL_LITERALS` (in `check.py`) | tuple of required substrings | tuple[str, ...] | Length stays exactly 4; literals 1–3 unchanged verbatim |
| canonical literal #1 | `start_s=$(date -u +%s)` | string | UNCHANGED |
| canonical literal #2 | `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))` | string | UNCHANGED |
| canonical literal #3 | `tools/kimi/emit-telemetry.sh ` (trailing space) | string | UNCHANGED |
| canonical literal #4 | gate predicate / gate-source line | string | REPLACED: from `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` → `. .adlc/partials/kimi-gate.sh 2>/dev/null \|\| . ~/.claude/skills/partials/kimi-gate.sh` |
| `check_canonical()` semantics | match mode | n/a | UNCHANGED — `literal in text` substring (indentation-agnostic); anchor stays `ADLC_DISABLE_KIMI`; one finding per missing literal |

### Events

_Not applicable — no new triggers or payloads; existing finding emission format (`<file>:<line>: canonical-helper: missing required literal: <literal>`) is unchanged._

### Permissions

_Not applicable — the linter is offline, read-only, no actors/roles (REQ-425 BR-1/BR-12 unchanged)._

## Business Rules

- [ ] BR-1: In `tools/lint-skills/check.py`, `CANONICAL_LITERALS` literal #4 MUST be replaced by the exact string `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`. Literals 1–3 MUST remain byte-identical, and the tuple length MUST stay 4. (informed by REQ-425)
- [ ] BR-2: The obsolete inline predicate `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` MUST NOT remain anywhere in `tools/lint-skills/check.py` (no dead/stale literal left behind).
- [ ] BR-3: NO `SKILL.md` file (and no other file outside `tools/lint-skills/` and this REQ's spec artifacts) may be modified. The linter is reconciled to reality; the four skills are NOT contorted to satisfy the linter. Verified by `git diff --name-only`. (informed by REQ-425, REQ-428)
- [ ] BR-4: The change MUST cascade in lockstep so every place that encodes the canonical literal set stays consistent with `CANONICAL_LITERALS` (same lockstep discipline as REQ-428's BR-3): (a) `tools/lint-skills/tests/test_check.py` — `test_missing_canonical_reports_per_rule` keeps its `count("canonical-helper") == 4` assertion and replaces the `'command -v ask-kimi'` substring assertion with one for the new gate-source literal; `test_kimi_gate_happy_path_is_clean` stays green; (b) fixture `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` MUST contain the new gate-source literal so it remains a clean canonical happy-path; (c) fixture `tools/lint-skills/tests/fixtures/missing-canonical.md` MUST still omit all four literals while retaining the `ADLC_DISABLE_KIMI` anchor, and its prose MUST be updated to describe four (not "three") missing literals consistently; (d) `tools/lint-skills/README.md` "What it checks" §3 bullet list MUST list the new gate-source literal instead of the inline predicate. (informed by REQ-428, LESSON-016)
- [ ] BR-5: After the change, `python3 tools/lint-skills/check.py --root <dir containing copies of the four skills' SKILL.md>` MUST emit ZERO `canonical-helper` findings AND zero findings overall for those four skills.
- [ ] BR-6: The corruption-detection intent MUST be preserved: a `SKILL.md` that contains the `ADLC_DISABLE_KIMI` anchor but is missing the gate-source line MUST still produce a `canonical-helper` finding for literal #4 (defends gate-wiring corruption). Verified via the `missing-canonical` fixture continuing to fire all four. (informed by REQ-425, LESSON-012)
- [ ] BR-7: `check_canonical`'s `literal in text` substring semantics MUST be preserved (no regex, no anchoring, no whitespace normalization) so the 3-space-indented occurrence in `spec/SKILL.md` and the unindented occurrences elsewhere both satisfy the rule. (informed by LESSON-016)
- [ ] BR-8: `tools/lint-skills/check.py --root .` MUST exit 0 against the whole toolkit repo after the change (no findings repo-wide), matching REQ-425's standing acceptance bar. (informed by REQ-425)
- [ ] BR-9: This REQ MUST NOT touch the telemetry emit literal, any telemetry-resolver-source literal, or `partials/kimi-gate.sh`; it is independent of REQ-433's in-flight work and must not collide with it.
- [ ] BR-10: This REQ MUST stay disjoint from the adjacent in-flight REQ-435 (`feat/REQ-435-lint-skills-worktree-root-scan`), which changes the linter's scan-root/directory-walk behavior, NOT the canonical-helper rule. REQ-437 touches only `CANONICAL_LITERALS` literal #4 and its lockstep tests/fixtures/README; it MUST NOT modify `find_skill_files`, `SKIP_DIR_PARTS`, or the `--root` walk. Any Phase 8 merge overlap is a textual conflict to resolve, not a semantic dependency.

## Acceptance Criteria

- [ ] `~/.claude/kimi-venv/bin/pytest tools/lint-skills/tests/ -q` exits 0 with all tests passing (system `python3` lacks `openai`; the venv is mandatory).
- [ ] `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` exits 0 with all tests passing (no regression in the kimi suite).
- [ ] `python3 tools/lint-skills/check.py --root <tmp dir containing copies of `analyze`, `proceed`, `spec`, `wrapup` SKILL.md>` prints no output and exits 0 — zero `canonical-helper` findings and zero findings total.
- [ ] `python3 tools/lint-skills/check.py --root .` (from the toolkit root) exits 0 — repo-wide clean.
- [ ] `grep -F 'command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]' tools/lint-skills/check.py` returns no match (obsolete literal fully removed).
- [ ] `grep -F '. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh'` matches in each of: `tools/lint-skills/check.py`, `tools/lint-skills/tests/test_check.py`, `tools/lint-skills/tests/fixtures/kimi-gate-ok.md`, `tools/lint-skills/README.md`.
- [ ] `test_missing_canonical_reports_per_rule` asserts `result.stdout.count("canonical-helper") == 4` and asserts presence of all four literals including the new gate-source line (no `command -v ask-kimi` assertion remains).
- [ ] `git diff --name-only main...HEAD` lists ONLY files under `tools/lint-skills/` and `.adlc/specs/REQ-437-*/` — no `SKILL.md`, no `partials/`, nothing else.

## External Dependencies

- None. Fully internal to `adlc-toolkit/tools/lint-skills/`; revalidated against the existing pytest suites and the four in-repo skills.

## Assumptions

- The gate-source line `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh` appears as a byte-exact substring in all four Kimi-aware skills (verified by `grep` this session: `analyze` ×2, `proceed`, `spec` [3-space indented], `wrapup`). `check_canonical`'s substring semantics make the indentation difference irrelevant. (informed by LESSON-016)
- This repo's terminal spec status is `complete` (not the toolkit-default `deployed`); `complete` specs were treated as shipped/deployed for Step 1.6 retrieval. REQ-433 (`status: draft`, and explicitly out of scope) was excluded.
- REQ-433 is drafted only in the `main` checkout (requirement.md only, no architecture) and is absent from this worktree's tree at merge-base `04ba690`; there is no file-level collision between this REQ and REQ-433's planned `CANONICAL_LITERALS` edits (this REQ touches literal #4; REQ-433/TASK-046 touched the emit literal and added a resolver-source literal).
- `~/.claude/kimi-venv/bin/pytest` is the project's test interpreter (has `openai`); plain `python3` is only used for the offline, stdlib-only `check.py` itself.

## Open Questions

- [x] OQ-1: Should the canonical set additionally assert the gate *consumption* line (`adlc_kimi_gate_check; gate=$?`) for deeper post-migration corruption coverage? **Resolved: NO for this REQ.** A single stable source-line literal is the minimal faithful 1-for-1 analog of the old inline predicate and matches the REQ-433 resolver-source-literal precedent. Expanding the rule to multiple gate lines is a separate scope decision (would also require new fixtures) and is explicitly Out of Scope here; revisit only if a future corruption shows the source line alone is insufficient.

## Out of Scope

- Any edit to `analyze/SKILL.md`, `proceed/SKILL.md`, `spec/SKILL.md`, `wrapup/SKILL.md`, or any other `SKILL.md` (hard constraint — BR-3).
- REQ-433's telemetry global-fallback resolver work: the telemetry emit literal swap, the `kimi-tools-path.sh` resolver-source literal, and any `KIMI_TOOLS` plumbing (separate, in-flight, drafted only in `main`).
- REQ-435's `tools/lint-skills/` scan-root/worktree-root work (`feat/REQ-435-lint-skills-worktree-root-scan`, in-flight at this session): the directory-walk, `find_skill_files`, `SKIP_DIR_PARTS`, and `--root` resolution are untouched here (BR-10). The two REQs are textually adjacent in `check.py` but semantically disjoint.
- `partials/kimi-gate.sh` itself — the canonical literal is defined in `check.py`, not in the partial; the partial is not modified.
- The sentinel check and the shell-balance check (`sentinels.txt`, `_count_balance`, `check_balance`) — untouched.
- Widening the canonical-helper rule to assert additional gate/telemetry lines, adding new sentinels, or changing the `ADLC_DISABLE_KIMI` anchor or the per-missing-literal finding granularity (REQ-425 OQ-2 decision stands).
- Pre-commit/CI hook wiring (REQ-425 OQ-1 stands — `/analyze` Step 1.9 remains the always-on coverage).

## Retrieved Context

Unified retrieval (Step 1.6) scored 35 candidates (18 lessons LESSON-001..017+? , 18 `complete` specs; REQ-433 `draft` and no `.adlc/bugs/` excluded) with the weighted formula. `ask-kimi` could not body-read paths under `.claude/worktrees/` (privacy path-filter — LESSON-007 class), so the documented Fallback body-read path was taken; the two most load-bearing docs not already held verbatim (REQ-425, LESSON-016) were targeted-read directly per the skill's single-doc fallback. Top 15:

- REQ-416 (spec, score 7): Toolkit refactor — ADR-2 vendored-first-then-global kimi-gate idiom; the migration that caused this divergence
- REQ-425 (spec, score 7): SKILL.md corruption detection — origin of the canonical-helper rule; its BR-5 / `kimi-gate-form` System Model row is the rule amended here
- REQ-428 (spec, score 7): Dedupe /analyze telemetry block — the model for this REQ; its BR-3 establishes the canonical-helper lockstep discipline
- REQ-426 (spec, score 6): Toolkit followups bundle — drift/test-coverage precedent in `tools/`
- LESSON-013 (lesson, score 5): BSD-vs-GNU grep word-boundary silent failure — sibling "tool happens to work on tested inputs" class
- REQ-423 (spec, score 5): wrapup JSONL discovery — kimi-aware skill, post-validation discipline
- LESSON-010 (lesson, score 5): Delegated-model silent truncation & advisory anchoring — informed the Fallback body-read decision
- LESSON-008 (lesson, score 5): Skill delegation untrusted-data & citation sanitization — citation-fidelity discipline for this spec
- LESSON-006 (lesson, score 5): tools/ carve-out & fail-loud installers — partials-vs-tools rationale behind the gate-source idiom
- REQ-414 (spec, score 4): ADLC skill Kimi pilot — original gate/fallback wiring in analyze/wrapup
- REQ-415 (spec, score 4): Kimi hotfix bundle — kimi tooling hardening context
- LESSON-016 (lesson, score 3): Substring-counted balance buckets — load-bearing: the linter is substring-matched not parsed, and `kimi-gate-ok.md` is the canonical happy-path regression guard that must stay clean
- REQ-427 (spec, score 3): POSIX-ify /analyze Step 2a — adjacent skill-md POSIX precedent
- LESSON-012 (lesson, score 3): Structural telemetry beats prose enforcement — why the canonical-helper check exists at all (rejects option b)
- REQ-417 (spec, score 3): Kimi skill-delegation wave 2 — wired several of the gate-source lines now being matched
