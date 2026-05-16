# Architecture — REQ-433 Kimi telemetry global-fallback resolver

## Approach

Mirror the proven REQ-416 ADR-2 `kimi-gate` pattern for the telemetry
executables. Introduce one sourced POSIX partial, `partials/kimi-tools-path.sh`,
that exports a single `KIMI_TOOLS` directory variable; rewrite the 39
telemetry-script invocation sites across the 4 Kimi-aware skills to
`"$KIMI_TOOLS"/<script>.sh`; and source the resolver once per telemetry-bearing
shell block via the same vendored-first-then-global idiom skills already use for
`kimi-gate.sh`. Because the resolver is a partial, `/init`'s existing
`cp ~/.claude/skills/partials/*.sh .adlc/partials/` step distributes it for free
(architecture.md "Partials"; conventions.md "tools/ carve-out exception") — no
`/init` change, no per-repo re-init, and the `tools/` carve-out (LESSON-006) is
preserved because no executable code enters consumer `.adlc/`.

Exploration (this session, primary-source scan of worktree HEAD `04ba690`)
established the authoritative blast radius and surfaced one item the spec missed
(see ADR-3).

## Affected files

| File | Change | Task |
|---|---|---|
| `partials/kimi-tools-path.sh` | **new** sourced resolver partial | TASK-043 |
| `analyze/SKILL.md` | 15 sites → `"$KIMI_TOOLS"/`; add resolver-source line per telemetry block | TASK-044 |
| `proceed/SKILL.md` | 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line (Phase 5 block, inline) | TASK-044 |
| `spec/SKILL.md` | 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line (Step 1.6 block) | TASK-044 |
| `wrapup/SKILL.md` | 8 sites → `"$KIMI_TOOLS"/`; add resolver-source line (Step 4 block) | TASK-044 |
| `tools/kimi/tests/test_kimi_tools_path.py` | **new** pytest for the resolver | TASK-045 |
| `tools/lint-skills/check.py` | update `CANONICAL_LITERALS` (emit literal + add resolver-source literal) | TASK-046 |
| `tools/lint-skills/tests/test_check.py` | counts 4→5; literal strings; happy-path stays clean | TASK-046 |
| `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` | new canonical-good shape (resolver-source line + `"$KIMI_TOOLS"/` emit) | TASK-046 |
| `tools/lint-skills/tests/fixtures/missing-canonical.md` | verify still lacks all canonical literals (likely no change) | TASK-046 |
| `tools/lint-skills/README.md` | document the new canonical literals | TASK-046 |

`proceed/phases-*.md` companion files contain **zero** telemetry invocations
(Phase 5's telemetry block is inline in `proceed/SKILL.md`) — confirmed by
repo-wide grep. No companion edits needed.

## ADR-1: Sourced resolver partial, header-comment doc only (resolves spec OQ-3)

**Decision.** `partials/kimi-tools-path.sh` is a POSIX `sh` partial that is
**sourced** (not executed) so it can `export KIMI_TOOLS` into the calling shell —
exactly how `kimi-gate.sh` is sourced to export `ADLC_KIMI_GATE_REASON`. It
carries a header comment describing its contract; it does **not** get a separate
`kimi-tools-path.md` companion (unlike `kimi-gate.md`).

**Rationale.** `kimi-gate.md` exists because the gate has a non-trivial
3-return-code protocol + parameterized stderr templates. The resolver's surface
is one exported variable with no return-code contract — a header comment is
sufficient and matches architecture.md's "keep partials trivially auditable, one
snippet per file". Adding a doc file would be ceremony without payoff.

## ADR-2: Degrade target is project-local `tools/kimi` (resolves spec OQ-1)

**Decision.** Resolution order:
1. `[ -x tools/kimi/emit-telemetry.sh ]` → `KIMI_TOOLS="tools/kimi"` (canonical repo / dogfooding)
2. else `[ -x "$HOME/.claude/skills/tools/kimi/emit-telemetry.sh" ]` → `KIMI_TOOLS="$HOME/.claude/skills/tools/kimi"`
3. else (neither resolves) → `KIMI_TOOLS="tools/kimi"` (today's effective behavior)

`$HOME`, never `~`, in the assignment (tilde does not expand inside assignments
in POSIX sh). `export KIMI_TOOLS` on **every** path (BR-1).

**Rejected:** an explicit non-existent sentinel for case 3. It would force
matching error-handling changes at all 39 call sites and diverge from the
established REQ-424/LESSON-008 "telemetry never blocks" contract. Case 3 falling
back to `tools/kimi` means a missing install behaves *exactly* as it does today
(invocations no-op under the existing `2>/dev/null`/`|| true` guards) — zero
behavior regression, which is the BR-4 / BR-8 requirement. The probe uses
`emit-telemetry.sh` specifically (not `skill-flag.sh`) so the discriminator is a
single stable file across all three scripts' shared directory.

## ADR-3: Reconcile the REQ-425 linter in lockstep (resolves spec OQ-2; satisfies BR-9 spirit + ETHOS #6)

**Finding.** `tools/lint-skills/check.py` `check_canonical()` enforces: any
skill containing `ADLC_DISABLE_KIMI` MUST contain every `CANONICAL_LITERALS`
string verbatim — including `"tools/kimi/emit-telemetry.sh "` (trailing space).
Changing the 39 sites without touching the linter would make REQ-433 regress the
REQ-425 anti-corruption guard: all 4 skills would raise `canonical-helper`
findings, and REQ-433's own `/analyze` Step 1.9 would fail. The linter is not a
*caller* of the scripts (spec OQ-2's framing) — it is a *validator* that
hard-codes the literal. It must move in lockstep.

**Decision.**
1. Replace the `CANONICAL_LITERALS` emit entry `"tools/kimi/emit-telemetry.sh "`
   with `'"$KIMI_TOOLS"/emit-telemetry.sh '` (single-quoted Python literal since
   it contains `"`; trailing space preserved — it proves an *invocation*, not a
   path substring).
2. **Add a 5th canonical literal**: the resolver-source line
   `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`.
   This is squarely in REQ-425's purpose (LESSON-012): if a corruption strips the
   resolver-source line while leaving `"$KIMI_TOOLS"/emit-telemetry.sh`, then
   `$KIMI_TOOLS` is unset and the emit silently mis-targets — precisely the
   "literal-but-broken shell that escapes prose-only review" failure class the
   linter exists to catch. Guarding co-occurrence closes the new vector the
   indirection introduces.
3. Cascade to tests/fixtures/docs: `test_check.py` count assertions `== 4 → == 5`
   and updated literal strings; `kimi-gate-ok.md` updated to the new
   canonical-good shape (must contain BOTH new literals to stay clean);
   `missing-canonical.md` verified to still contain *none* of the (now 5)
   literals so its 5-findings assertion holds; `README.md` literal list updated.

**Rationale.** ETHOS #6 — fix the root cause in the same REQ rather than ship a
change that breaks a sibling guard. Strengthening the linter to also require the
resolver-source line makes the structural-enforcement guarantee (LESSON-012)
complete for the new indirection rather than merely preserved.

## ADR-3a: Same-root-cause extension — the stale `command -v ask-kimi` gate literal (discovered in Phase 4 implementation)

**Finding (verified, not trusted).** After TASK-046's first pass, running the
linter over the 4 skills **staged outside any `.worktrees` path** produced **4
`canonical-helper` findings**: every skill is "missing" the literal
`command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`.
Root cause: REQ-416 moved the gate from that inline conjunction into the sourced
`partials/kimi-gate.sh`; no post-REQ-416 skill contains the inline form, yet
`CANONICAL_LITERALS` still demanded it. This is the **identical staleness class**
ADR-3 already fixes for the emit literal — the gate entry is stale in exactly the
same way. It was dormant only because the linter is never run over the real
SKILL.md files in normal flow (see ADR-3b).

**Decision.** Replace the stale `CANONICAL_LITERALS` entry
`'command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]'`
with the actual post-REQ-416 gate-wiring idiom the skills contain (byte-analog of
the resolver literal): `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`.
Tuple stays **5** entries. Cascade to `kimi-gate-ok.md` (rewrite to the faithful
post-REQ-416 shape: source kimi-gate + kimi-tools-path, telemetry block, an
`ADLC_DISABLE_KIMI` anchor in a gate-case comment — must contain all 5 literals),
`missing-canonical.md` (verify it still lacks all 5), `test_check.py` (the
asserted string for that entry changes; count stays 5), `README.md`.

**Scope justification.** This is **in-scope by necessity, not scope creep**:
REQ-433 AC-5 ("linter over the 4 skills → 0 `canonical-helper` findings;
`/analyze` Step 1.9 passes") is *unsatisfiable* without it. The spec's "no change
to gate logic" Out-of-Scope is not violated — gate logic is unchanged since
REQ-416; only the linter's stale *expectation* of how the gate is invoked is
corrected, which is squarely ADR-3's mandate applied to the second stale entry.

## ADR-3b: Deferred follow-up — linter is vacuous inside `.worktrees` (NOT fixed here)

`check.py` `SKIP_DIR_PARTS` includes `.worktrees`, so `check.py --root <path>`
scans **zero** skill files whenever `<path>` is inside a worktree. `/proceed`
runs every phase inside `.worktrees/REQ-xxx`, so `/analyze` Step 1.9 (and any
in-pipeline lint run) is **silently vacuous** — it reports clean having checked
nothing. This is a real latent defect but is a **distinct concern** from
REQ-433's telemetry-resolver goal (it is about lint-skills' directory-walk
policy vs. worktree-based pipelines, not about `$KIMI_TOOLS`). Per ETHOS #6
("if a fix is genuinely out of scope, file it explicitly"), it is filed as a
deferred follow-up (spawned task + Phase 8 lesson), and REQ-433's own AC-5 is
verified by staging the skills **outside** `.worktrees` before linting.

## ADR-4: Site inventory reconciliation (BR-9)

Repo-wide grep at HEAD `04ba690`: **39** invocation sites — `analyze` 15,
`proceed` 8, `spec` 8, `wrapup` 8 (`skill-flag.sh` ×32, `emit-telemetry.sh` ×4,
`check-delegation.sh` ×3). This matches the spec exactly; REQ-428's dedup of the
`/analyze` telemetry block is already reflected at this HEAD (no double-counting).
No further reconciliation required. The implementer MUST re-grep before and after
editing to assert the bare-invocation count goes 39 → 0 (AC-2).

## Lessons applied

- **LESSON-006** — `tools/` carve-out: do NOT vendor `tools/kimi/` into consumer `.adlc/`; the partial-resolver is the carve-out-respecting solution.
- **LESSON-012** — structural telemetry intent + POSIX-only skill helpers: drives ADR-3's 5th-literal decision and the POSIX constraint on the partial.
- **LESSON-013** — BSD/GNU shell portability: the resolver and any test shell must be POSIX, no GNU-only constructs.
- **LESSON-008** — BR-4 "telemetry never blocks": drives ADR-2's non-fatal degrade.
- **LESSON-014** — symlink TOCTOU: noted and **not applicable** — the resolver only *reads* (`[ -x ]`) the `~/.claude/skills` symlinked path; it never mutates through it, so there is no check-then-mutate window.

## Task graph (DAG)

```
TASK-043 (resolver partial)            ← tier 1, no deps
   ├─→ TASK-044 (39 sites + source line in 4 skills)   ← tier 2, deps [043]
   └─→ TASK-045 (resolver pytest)                      ← tier 2, deps [043]   (parallel with 044)
            TASK-046 (lint-skills reconcile)           ← tier 3, deps [043,044]
```

No cycles. Max in-degree 2 (≤3). Every spec AC is covered: AC-2→044,
AC-3/AC-4→045, AC-5→046, AC-1/AC-6→043+044 (verified end-to-end in Phase 5).

## Phase 5 review disposition

6 agents (reflector + 5 reviewers) dispatched in one gate. **0 Critical, 0
Major in REQ-433's own changes.** Disposition:

**Fixed** (one consolidated commit `fix(kimi): address Phase 5 verify findings`):
- *(must-fix, correctness)* partial used bare `$HOME` → `${HOME:-}` so an
  unset `HOME` under a `set -eu` caller degrades instead of aborting (the
  partial's own non-fatal contract).
- partial mode `0755`→`0644` to match the sourced sibling `kimi-gate.sh`
  (sourced ≠ executed; corrects TASK-043's spec wording).
- test gaps closed: top-level `import subprocess`; exists-but-not-executable
  probe; HOME-unset-under-`set -eu`; export-to-child (`export` contract);
  tightened `test_kimi_gate_happy_path_is_clean` (assert zero findings);
  new `missing-resolver-source.md` fixture + single-missing-literal test.
- `lint-skills/README.md` literal order aligned to `check.py`.

**Accepted, not changed** (rationale):
- Trap body `'"$KIMI_TOOLS"/skill-flag.sh … ' EXIT` expands `$KIMI_TOOLS` at
  EXIT time — Low: guarded by `2>/dev/null || true` (BR-4 preserved) and the
  partial's defensive default always sets `KIMI_TOOLS`; churning 5 trap sites
  late carries more risk than the cosmetic gain.
- Duplicate `chore: mark TASK-046 complete` commits — truthful history of the
  legitimate ADR-3a reopen; an interactive rebase to squash is riskier than
  the cosmetic benefit on a branch about to merge.
- CWD-relative `tools/kimi` preference — **not a regression** (pre-REQ-433
  already ran `tools/kimi/…` from CWD unconditionally); matches ADR-2;
  established toolkit trust model. `$HOME` trust likewise pre-existing.
- `pytest 8.4.2` GHSA tmpdir advisory — pre-existing, local-only, not
  introduced by REQ-433.

**Filed as follow-up** (pre-existing REQ-428, verified unchanged on `main`,
out of REQ-433 scope — spawned task): `_adlc_emit_step_telemetry` defined in
one fenced block but called from others; `local` used in an `sh` fence.

**Re-verify (Step D):** only Minor/Medium fixes were applied (no Critical /
must-fix-Major in REQ-433's code), so per the skill the 5-agent re-verify loop
is **intentionally skipped**; instead the orchestrator directly re-verified —
cross-suite **74 passed**, AC-5 linter clean outside `.worktrees` (EXIT 0),
and the AC-1 downstream dogfood still emits telemetry after the `${HOME:-}`
change.
