---
id: REQ-437
title: "Architecture — Reconcile lint-skills canonical-helper rule with REQ-416 ADR-2"
status: approved
created: 2026-05-16
updated: 2026-05-16
---

## Overview

`tools/lint-skills/check.py`'s `CANONICAL_LITERALS` carries four exact substrings that every `SKILL.md` containing the `ADLC_DISABLE_KIMI` anchor must contain (REQ-425 ADR-3 / BR-5). Literal #4 is the **inline** gate predicate `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`. REQ-416 (ADR-2) migrated the four Kimi-aware skills to *source* the shared `partials/kimi-gate.sh` predicate; they no longer inline that form anywhere (not even verbatim inside the partial, which decomposes it). Result: the linter, run over the toolkit's own four skills, emits exactly four spurious `canonical-helper` findings (one per skill, all for literal #4). This is pre-existing and independent of REQ-433 (reproduces at merge-base `04ba690`) and of REQ-435 (`lint-skills-worktree-root-scan`, a scan-root change, semantically disjoint).

This change reconciles the *linter to reality*: it replaces literal #4 with the byte-exact gate-source line the migrated skills now share, cascading that one change in lockstep to the rule's tests, fixtures, and README. No `SKILL.md` is modified. `conventions.md` §"Kimi delegation pattern" already documents the sourced idiom as mandatory and explicitly forbids inlining the old predicate — so this aligns the linter with the project's own written convention, not merely with empirical grep output.

Per `conventions.md`: `tools/` is the only place real code lives; Python 3 stdlib only; the linter stays offline, read-only, side-effect-free (REQ-425 BR-1/BR-12 unchanged).

## ADRs

### ADR-1: Replace canonical literal #4 with the gate-source line (supersedes REQ-425 ADR-3's 4th literal)

`CANONICAL_LITERALS[3]` changes from:

- `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`  (REQ-425 ADR-3, now obsolete)

to:

- `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`

Literals #1–#3 (`start_s=$(date -u +%s)`, `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`, `tools/kimi/emit-telemetry.sh `) are unchanged; the tuple length stays 4; `check_canonical`'s anchor (`ADLC_DISABLE_KIMI`) and per-missing-literal finding granularity are unchanged.

**Rationale**: the check's *intent* — a Kimi-gated skill must correctly wire up the gate machinery, so a literal-but-broken corruption of that wiring is caught (the whole point of REQ-425) — is preserved; only the *form* moved from an inlined predicate to a sourced partial (REQ-416 ADR-2). The gate-source line is the byte-exact post-migration analog, present verbatim in all four skills (`analyze` ×2, `proceed`, `spec`, `wrapup` — verified by `grep -cF`), and is the exact structural analog of the telemetry-resolver-source literal REQ-433 adds via the same vendored-first-then-global idiom. **Rejected — option (b), drop the canonical-helper check**: it would surrender corruption coverage on the single most load-bearing line of the post-migration gate wiring (a mangled `2>/dev/null ||` or a truncated partial path would ship undetected) — exactly the failure class REQ-425 exists to catch (LESSON-012: structural enforcement beats prose review). **Rejected — option (c), assert additional gate-consumption lines** (`adlc_kimi_gate_check; gate=$?`): out of scope (REQ-437 OQ-1 resolved NO); a single stable source-line literal is the minimal faithful 1-for-1 analog and matches the REQ-433 precedent; widening would also force new fixtures.

This ADR explicitly **supersedes the fourth bullet of REQ-425 ADR-3** (and the matching System Model `kimi-gate-form` row / BR-5). REQ-425's other three literals and its anchor design stand.

### ADR-2: Lockstep cascade — `CANONICAL_LITERALS` is the single source of truth, four mirror sites move atomically

The literal set is encoded in five live places under `tools/lint-skills/`. They MUST change in one commit; a half-applied cascade breaks the suite and is precisely the drift the rule guards against (same discipline as REQ-428 BR-3 and the REQ-433 lockstep). Verified-complete edit set (repo-wide grep confirms no other live encoding):

1. `tools/lint-skills/check.py` — `CANONICAL_LITERALS[3]` (the source of truth).
2. `tools/lint-skills/tests/test_check.py` — `test_missing_canonical_reports_per_rule`: keep `result.returncode >= 4` and `result.stdout.count("canonical-helper") == 4`; replace the `assert 'command -v ask-kimi' in result.stdout` substring assertion with one asserting the new gate-source literal; the three telemetry-literal assertions stay. `test_kimi_gate_happy_path_is_clean` keeps its code; it depends on fixture #3.
3. `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` — the canonical happy-path regression guard (LESSON-016: this is load-bearing, not an edge case). Its fenced block is rewritten to a faithful post-REQ-416 skill shape: the gate-source line + the documented `adlc_kimi_gate_check; case` idiom (so the `ADLC_DISABLE_KIMI` anchor survives in a case-arm comment exactly as in the real skills) + the three unchanged telemetry literals. Net: anchor present ⇒ `check_canonical` runs; all four literals present ⇒ zero findings ⇒ genuinely clean (not clean-because-anchor-absent).
4. `tools/lint-skills/tests/fixtures/missing-canonical.md` — already behaviorally correct (anchor present, zero literals ⇒ 4 findings). Only the prose "three required literals" is corrected to "four" for documentation consistency.
5. `tools/lint-skills/README.md` — the "What it checks" §3 bullet list: swap the inline-predicate bullet for the gate-source-line bullet (the surrounding "four exact literals" wording stays accurate).

**Rationale**: one source of truth + explicitly enumerated mirrors, edited together, is the only structurally safe way to change a rule that is itself a drift detector. Historical artifacts that mention the old literal (`.adlc/specs/REQ-414|416|417|425/**`, `.adlc/context/conventions.md`'s "rather than inlining …" sentence) are **frozen and out of scope** — they are point-in-time records or already describe the old form as the anti-pattern; touching them would rewrite history and is explicitly excluded.

**Phase 5 addendum**: the verify pass added one *additive* regression artifact beyond the five mirror sites — a `tests/fixtures/old-inline-gate.md` fixture plus `test_old_inline_gate_form_fires_single_finding`, asserting that a skill still using the old inline predicate (with the three telemetry literals) but lacking the new source line fires *exactly one* finding. This is a negative-case guard against accidental re-introduction of the old literal into `CANONICAL_LITERALS`; it is not a sixth mirror of the literal and carries no lockstep obligation. Two cosmetic polish items also landed: README bullet order now mirrors the tuple, and the `kimi-gate-ok.md` fixture moves telemetry into the `0)` delegated case arm to faithfully match real-skill shape (zero behavioral effect under substring matching).

### ADR-3: Preserve substring (`literal in text`) matching semantics

`check_canonical` keeps `if literal not in text` — no regex, no anchoring, no whitespace normalization. This is why the new literal matches whether a skill indents the source line (3 spaces in `spec/SKILL.md`) or not (`analyze`/`proceed`/`wrapup`), and why a case-arm-comment `ADLC_DISABLE_KIMI` still trips the anchor. **Rationale**: substring matching is the established REQ-425 contract (LESSON-016 — the linter is substring-counted, not parsed); changing match semantics would be a far larger, riskier change than this REQ scopes and would risk regressing the balance/sentinel checks' shared assumptions.

## Task Breakdown

One atomic task (the five-site lockstep edit cannot be safely split — partial application breaks the suite, which is the exact failure mode ADR-2 guards against):

- **TASK-043** — Reconcile the canonical-helper gate literal across `check.py` + the four mirror sites; verify via the REQ-437 acceptance commands.

No dependencies. Single-repo (`adlc-toolkit`); `repo:` omitted (single-repo mode — `/proceed` backfills primary).
