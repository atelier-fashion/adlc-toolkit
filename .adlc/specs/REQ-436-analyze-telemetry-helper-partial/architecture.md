# Architecture — REQ-436 Extract analyze telemetry helper to a sourceable POSIX partial

## Approach

Mirror the proven REQ-416 (`kimi-gate`) / REQ-433 (`kimi-tools-path`) sourceable-partial
pattern for `_adlc_emit_step_telemetry`. The helper currently lives inline in a
fenced block in `analyze/SKILL.md` Step 1.5 (post-REQ-433 lines 41-66) and is
invoked from separate fenced blocks in Step 1.5 (line 117) and Step 1.6 (line 179).
Under the toolkit's real execution model — each SKILL.md fenced block is potentially
an independent shell invocation; shell state does not persist across steps — the
function is undefined at those call sites, so the telemetry emit silently fails
(Defect-1). The body also uses `local` (lines 46-48), violating the POSIX-only
mandate (Defect-2).

The spec was drafted against the pre-REQ-433 tree; this branch is based on
post-REQ-433 `origin/main` (7dfc646, PRs #50/#51 merged). The architecture
reconciles the spec with the merged REQ-433 reality: the helper now depends on
`$KIMI_TOOLS` (resolved by `partials/kimi-tools-path.sh`), the linter's
`CANONICAL_LITERALS` is now a 5-tuple in the `$KIMI_TOOLS` form, and REQ-433's
ADR-3b + LESSON-019 explicitly deferred the `.worktrees` vacuous-lint defect to a
follow-up — which this REQ executes because REQ-436's own verification depends on it.

## Affected files

- `partials/emit-step-telemetry.sh` — NEW sourceable POSIX partial (the relocated helper)
- `partials/emit-step-telemetry.md` — NEW companion caller-contract doc
- `analyze/SKILL.md` — remove inline helper-def block (41-66); swap the two emit
  blocks (115-118, 177-180) to source the new partial; reword the line-39 prose
- `tools/lint-skills/check.py` — ADR-4 (canonical-follows-indirection), ADR-5
  (root-skip fix), ADR-6 (`posix-fence`), ADR-7 (`cross-fence-fn`) + docstring
- `tools/lint-skills/README.md` — document the two new checks + the partial-aware canonical rule
- `tools/lint-skills/tests/test_check.py` + `tools/lint-skills/tests/fixtures/*` — new fixtures + cases (ADR-8)
- `partials/README.md` — register the new sourceable partial (model 2)
- `init/SKILL.md` — verify/extend the partials-copy step covers the new files
- `.adlc/context/conventions.md`, `.adlc/context/architecture.md` — explicit execution-model statement
- LESSON (Phase 8 /wrapup, id from atomic counter) — knowledge capture

## ADR-1: Relocate the helper into a sourceable partial (BR-1, BR-2)

**Decision.** Create `partials/emit-step-telemetry.sh` (`#!/bin/sh`, POSIX-only,
header-comment style matching `kimi-gate.sh` / `kimi-tools-path.sh`) defining
`_adlc_emit_step_telemetry`. Add companion `partials/emit-step-telemetry.md`
documenting the caller contract: the `$1` step-label argument; the caller-env
variables read (`start_s`, `ASK_KIMI_INVOKED`, `KIMI_EXIT`, `flag`,
`ADLC_KIMI_GATE_REASON`); the exact emitted record; the BR-4 "telemetry never
blocks" invariant (LESSON-008); and the call-site protocol (source with the
two-level fallback **in the same fenced block as the invocation**).

**Rationale.** `partials/README.md` "model 2" — a function-exporting partial with
a non-obvious call-site protocol requires a companion `.md`. This is the exact
fallback REQ-428's spec reserved (its BR-5 / Out-of-Scope) "if function scoping
proves fragile in practice"; REQ-433's review proved it fragile.

## ADR-2: Partial self-resolves `$KIMI_TOOLS`; call sites do a 1-line swap (BR-1, BR-3, BR-14)

**Finding.** Post-REQ-433 the helper body uses `"$KIMI_TOOLS"/skill-flag.sh` and
`"$KIMI_TOOLS"/emit-telemetry.sh`. `$KIMI_TOOLS` is exported by sourcing
`kimi-tools-path.sh`. If the function moves to a partial, that dependency must
still be satisfied in the shell that runs the function.

**Decision.**
1. `partials/emit-step-telemetry.sh` sources `kimi-tools-path.sh` at its top with
   the canonical two-level fallback
   (`. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`)
   **before** defining the function, so the function body's `"$KIMI_TOOLS"`
   references resolve regardless of call site. Sourcing keeps the defensive
   `export KIMI_TOOLS="tools/kimi"` default (telemetry never blocks — LESSON-008).
2. Each emit block in `analyze/SKILL.md` becomes a clean 1-line swap: replace the
   existing `. .adlc/partials/kimi-tools-path.sh …` line (lines 116, 178) with
   `. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh`;
   the following `_adlc_emit_step_telemetry Step-1.5` / `Step-1.6` line is
   unchanged. Source + call are in the **same fenced block** → function is always
   defined in the shell that calls it (Defect-1 fixed).
3. Delete the inline helper-def fenced block (lines 41-66). Reword the line-39
   prose from "define once here" to state the helper is sourced from
   `partials/emit-step-telemetry.sh` at each emit point, with a one-clause
   pointer to the execution-model rationale (conventions.md / the new LESSON).
4. The before-gate-check blocks (lines 70-77, 126-133), the gate blocks
   (81-89, 137-145), `start_s`, the `trap`, and the `ASK_KIMI_INVOKED`/`KIMI_EXIT`
   contract are **byte-untouched** (BR-14, AC-11).

**Canonical-literal preservation check (load-bearing).** Post-change,
`analyze/SKILL.md` must still contain canonical literals 1/4/5 inline so
`check_canonical` (which only fires because the file still contains
`ADLC_DISABLE_KIMI`) does not flag them:
- L1 `start_s=$(date -u +%s)` — lines 74, 130 (before-gate blocks, untouched) ✓
- L4 `. .adlc/partials/kimi-gate.sh 2>/dev/null || …` — lines 82, 138 (untouched) ✓
- L5 `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || …` — still present at
  lines 71, 127, 152 (before-gate + Step-1.6 delegated path; untouched) ✓ even
  after the two emit-block swaps remove it from lines 116/178 and the helper-def
  removal drops line 42.
- L2 `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))` and L3
  `"$KIMI_TOOLS"/emit-telemetry.sh ` move into the partial → handled by ADR-4.

## ADR-3: Rewrite the body POSIX-clean — no `local` (BR-5, BR-6, AC-7)

**Decision.** Replace `local _step` / `local duration_ms=…` / `local mode reason
gate_result` with uniquely-prefixed plain globals `_aest_step`,
`_aest_duration_ms`, `_aest_mode`, `_aest_reason`, `_aest_gate_result`. The
four-way mode resolution, the order/number of `"$KIMI_TOOLS"/skill-flag.sh clear`
calls, the `duration_ms` arithmetic, and the final
`"$KIMI_TOOLS"/emit-telemetry.sh analyze "$_aest_step" unknown "$_aest_gate_result"
"$_aest_mode" "$_aest_reason" "$_aest_duration_ms"` argv are semantically
identical to the current behavior (BR-4). Global namespace leakage is a non-issue:
each call site sources the partial in its own short-lived block shell. Matches
`kimi-gate.sh`'s no-`local` POSIX style (LESSON-012 #5, LESSON-013).

## ADR-4: Reconcile the REQ-425 linter in lockstep — canonical follows the indirection (BR-7)

**Finding.** `check_canonical` requires all 5 `CANONICAL_LITERALS` in the
SKILL.md *text* whenever it contains `ADLC_DISABLE_KIMI`. Moving the helper body
into the partial removes L2 and L3 from `analyze/SKILL.md` → 2 false
`canonical-helper` findings → `check.py` exits non-zero → REQ-436 AC-5 fails and
`/analyze` Step 1.9 regresses. This is precisely LESSON-019 #1 ("a presence guard
rots when the thing it guards moves behind indirection; update the guard in the
same change") and the identical class REQ-433 ADR-3/3a handled.

**Decision.** Generalize `check_canonical` so a canonical literal is satisfied if
present in the SKILL.md text **OR** in the text of a sourced telemetry partial
resolved under the scan root. Implementation: when a literal is absent from the
SKILL.md text, before emitting a finding, also scan the partials directory
resolved relative to the scan root — try `<root>/partials/*.sh` then
`<root>/.adlc/partials/*.sh` (toolkit-self vs consumer layouts) — and treat the
literal satisfied if found in any of them. Keep it text-substring (no shell
parsing) to preserve the linter's deliberate simplicity (LESSON-016 spirit).
This generalizes the guard so future indirection moves do not re-rot it, rather
than hard-coding the one partial.

**Scope justification (mirrors REQ-433 ADR-3a).** In-scope by necessity, not
scope creep: REQ-436 AC-5 ("`check.py --root .` exits 0 after the change") is
*unsatisfiable* without it. No canonical literal's *meaning* changes; only the
linter's expectation of *where* L2/L3 legitimately live is corrected.

## ADR-5: Fix the `.worktrees` vacuous-walk defect (executes REQ-433 ADR-3b's deferred follow-up; LESSON-019 #2)

**Finding.** `find_skill_files` applies `SKIP_DIR_PARTS = {".git", ".worktrees",
"node_modules"}` to every component of each discovered path, including components
of the resolved `--root` itself. Run from inside any `.worktrees/…` (every
`/proceed` phase) it scans **zero** files and exits 0 — confident green having
checked nothing. REQ-433 ADR-3b explicitly filed this as a deferred follow-up
("spawned task + Phase 8 lesson"); LESSON-019 #2 captured it; REQ-433 verified its
own AC-5 only by staging skills *outside* `.worktrees` (the workaround LESSON-019
#3 warns against).

**Decision.** Apply the skip list only to path components **strictly below the
resolved root** — compute each candidate's parts *relative to* `root_resolved`
and test only those for membership in `SKIP_DIR_PARTS`; never test the root's own
parts. A descendant `.git`/`.worktrees`/`node_modules` is still skipped; a root
that itself sits under such a name is still fully scanned. Ship a regression test
(SKILL.md staged under a `<tmp>/.worktrees/…` root → still scanned).

**Scope justification.** REQ-436's AC-5/AC-6/AC-8 are verified by running the
linter, and `/proceed` runs every phase inside a worktree. Fixing the canonical
guard (ADR-4) while leaving the walk vacuous would ship exactly the false-green
LESSON-019 condemns — verification of REQ-436 itself would be untrustworthy. This
is the explicitly-deferred REQ-433 follow-up, now load-bearing for this REQ.
**Flagged as a discovered-in-architecture scope addition** (transparent, not a
halt — `/proceed` continues).

## ADR-6: New `posix-fence` check — `local` in an `sh`/`shell` fence (BR-8, AC-8; resolves OQ-1)

**Decision.** Add an orthogonal check: within a fenced block whose language is
`sh` or `shell` (reuse `FENCE_OPEN_RE`, gate on `m.group(1) in {"sh","shell"}`),
flag any body line containing a `local ` declaration at statement position
(regex: leading `^\s*local\s+\S`, plus the inline forms after `;`, `&&`, `||`,
`then`, `do`, `{`). **```bash fences are exempt** — many `bash` builds support
`local`; conventions.md's POSIX mandate targets `sh`. Document the `bash`-exempt
decision in the `check.py` docstring and the LESSON. Finding format:
`<file>:<line>: posix-fence: 'local' is not POSIX in a ```sh fence — use
uniquely-prefixed globals or relabel the fence ```bash`. Line number = the
absolute line of the offending body line (not the fence open) so `/analyze`
Step 1.9's `<file>:<line>:` parser stays accurate.

## ADR-7: New `cross-fence-fn` check — function defined in one fence, called in another (BR-10; resolves OQ-2)

**Feasibility (OQ-2 resolved: implementable cleanly).** Parse fences (existing
machinery). In each `sh`/`bash`/`shell` fence collect function definitions
(`^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{`) with their fence index, and
candidate invocations (a token at statement position matching a known defined
name). Flag a function **defined in fence _i_ and invoked only in some fence
_j ≠ i_** within the same SKILL.md. Define-and-use in the same fence → not
flagged (legitimate). Conservative against false positives: only names that are
both defined (with the `() {` form) and invoked in the file are considered; prose
mentions outside fences are ignored. This is the structural guard that prevents
Defect-1 from regressing — LESSON-012 ("structural enforcement beats prose") and
LESSON-019 applied to the linter itself. Finding:
`<file>:<line>: cross-fence-fn: '<name>' defined in fence at line <d> but invoked
at line <u> in a different fenced block — shell state does not persist across
SKILL.md fences; move it to a sourced partial`.

## ADR-8: Every guard ships with a realistic post-change test (LESSON-019 #3, BR-9, AC-6, AC-7)

- **Canonical-follows-indirection**: new fixture pair — a SKILL.md containing
  `ADLC_DISABLE_KIMI` and L1/L4/L5 inline but **not** L2/L3, plus a sibling
  `partials/emit-step-telemetry.sh` (or `.adlc/partials/…`) supplying L2/L3 →
  asserts **0** `canonical-helper` findings (the post-REQ-436 shape). The
  `_stage` helper is extended (or a bespoke test) to also stage a partial.
- **Existing canonical tests**: `missing-canonical.md` (no partials staged) still
  yields 5 findings (unchanged); `kimi-gate-ok.md` still clean (still has all 5
  inline); `missing-resolver-source.md` still exactly 1 (no partials staged).
- **`posix-fence`**: fixture with `local x=1` in a ```sh fence (flagged) and the
  same in a ```bash fence (not flagged) → asserts finding string + line + the
  bash-exemption.
- **`cross-fence-fn`**: fixture defining `f() {…}` in one fence and calling `f`
  in another (flagged); a control fixture defining+calling in one fence (clean).
- **Root-skip regression**: stage a corrupt SKILL.md under `<tmp>/.worktrees/x/`
  and run with `--root <tmp>/.worktrees/x` → still scanned (finding present).
- **AC-7 telemetry equivalence**: a pytest that, per the 4 modes
  (fallback / ghost-skip / delegated / api-error), writes stub
  `$KIMI_TOOLS/skill-flag.sh` + `$KIMI_TOOLS/emit-telemetry.sh` that append argv
  to a capture file, sets the caller-env vars, sources
  `partials/emit-step-telemetry.sh`, calls `_adlc_emit_step_telemetry Step-1.5`,
  and asserts the captured `emit-telemetry.sh` argv + `skill-flag.sh clear`
  call sequence equal the pre-change behavior. POSIX `sh` only (LESSON-013).
- Full suite green via `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q`.

## Lessons applied

- **LESSON-019** (keystone) — guard rots when indirection moves; dir-walk skip-list
  must not be applied to the invocation root; verify guards on real post-change
  inputs. Drives ADR-4, ADR-5, ADR-8. This REQ is instance #2 of the same class
  *and* executes REQ-433 ADR-3b's deferred root-skip fix.
- **LESSON-012** — structural enforcement beats prose; POSIX-only skill helpers.
  Drives ADR-3 (no `local`), ADR-6, ADR-7.
- **LESSON-015** — shell-scope correctness precedent; cross-referenced by the new LESSON.
- **LESSON-008** — telemetry never blocks; the partial keeps the non-fatal
  `kimi-tools-path` degrade and is sourced with `2>/dev/null || …`.
- **LESSON-006** — `tools/` carve-out; do not vendor `tools/kimi` into consumer
  `.adlc/`; a partial is the carve-out-respecting mechanism.
- **LESSON-013** — POSIX/BSD portability for the partial and all test shell.

## Task graph (DAG)

```
TASK-047 (new partial + companion)            TASK-052 (context-doc execution-model statement)
   │                                              (independent)
   ├──────────────┬───────────────┐
   ▼              ▼               ▼
TASK-048       TASK-049        TASK-051
(rewire        (linter:        (/init copy +
 analyze        ADR-4/5/6/7)    partials/README)
 SKILL.md)         │
                   ▼
                TASK-050 (pytest: fixtures + cases + AC-7 harness; run venv pytest)
                (deps: TASK-047, TASK-049)
```

Tiers: **T1** = {047, 052} ∥ · **T2** = {048, 049, 051} ∥ (after 047) ·
**T3** = {050} (after 047+049). No cycles; ≤3 deps/task. Every requirement AC
maps to a task; AC-10 (LESSON) is Phase 8 `/wrapup` knowledge capture — content +
cross-refs (REQ-436, REQ-428, LESSON-019, LESSON-012, LESSON-015) recorded here
so wrapup writes it faithfully and allocates the id atomically (not 018/019).

## Out of scope (unchanged from spec)

Generalizing the helper to other skills (`spec`/`proceed`/`wrapup` have similar
emit blocks — future REQ); changing `emit-telemetry.sh`'s signature/schema;
refactoring the gate-check prologues; a `tools/kimi/` wrapper script.
