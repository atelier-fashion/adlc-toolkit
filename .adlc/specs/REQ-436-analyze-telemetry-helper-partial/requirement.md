---
id: REQ-436
title: "Extract analyze telemetry helper to a sourceable POSIX partial (fix cross-block + local defects)"
status: complete
deployable: false
created: 2026-05-16
updated: 2026-05-16
component: "adlc/analyze"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["correctness", "maintainability"]
tags: ["telemetry", "kimi-delegation", "skill-md", "partials", "lint-skills", "posix", "execution-model"]
---

## Description

`analyze/SKILL.md` defines a shared shell helper `_adlc_emit_step_telemetry()` (introduced by REQ-428 to dedupe the Step 1.5 / Step 1.6 telemetry-resolve-and-emit block). REQ-433's Phase 5 review surfaced two pre-existing defects in this helper. They were correctly judged out of REQ-433's scope (REQ-433 only changed telemetry-script path resolution; it did not introduce these and verified they exist unchanged on `main`). This REQ fixes both and hardens the toolkit against the underlying failure class.

**Defect 1 — cross-block function definition (correctness; silent telemetry loss).** `_adlc_emit_step_telemetry` is defined inside one fenced ```sh block in Step 1.5 (`analyze/SKILL.md` ~line 42) but invoked from *separate* fenced blocks: `_adlc_emit_step_telemetry Step-1.5` (~line 114) and `_adlc_emit_step_telemetry Step-1.6` (~line 173). The investigated execution model is that SKILL.md fenced shell blocks are potentially executed as **independent shell invocations** — shell state (functions, non-exported variables) does not reliably persist across steps. This is proven by the toolkit's own design: `partials/kimi-gate.sh` is deliberately re-sourced per step (`analyze/SKILL.md` Step 1.5 ~line 80 **and again** Step 1.6 ~line 134); if a step shared the prior step's shell that second source would be dead code. It is reinforced by the Claude Code Bash-tool contract ("the working directory persists between commands, but shell state does not"). Consequently the function is undefined at its Step 1.6 call site (and not guaranteed at its Step 1.5 call site), so the telemetry emit silently fails (`command not found`, swallowed) — the exact REQ-424 failure class (telemetry that looks wired but does not fire). This affects the whole toolkit's telemetry-emit reliability pattern, not just `/analyze`. (informed by REQ-428, REQ-424, LESSON-012)

**Defect 2 — non-POSIX `local` in an `sh` fence (convention violation).** The helper uses `local _step`, `local duration_ms`, `local mode reason gate_result` inside a ```sh fenced block. `conventions.md` "Bash in skills" mandates POSIX-only shell; `local` is not POSIX. (informed by REQ-427, LESSON-015)

**Fix direction.** Extract the helper into a new **sourceable partial** `partials/emit-step-telemetry.sh` (POSIX `#!/bin/sh`) with a companion `partials/emit-step-telemetry.md` documenting the caller contract — exactly the toolkit's sanctioned mechanism for shared shell code (`partials/README.md` "model 2"; `partials/kimi-gate.sh` is the canonical precedent). Both call sites source it with the two-level consumer-project-first fallback **in the same fenced block as the invocation**, so the function is always defined in the shell that calls it regardless of shell boundaries. Rewrite the body without `local` (uniquely-prefixed globals), matching `kimi-gate.sh`'s no-`local` POSIX style. This is precisely the partial/wrapper fallback REQ-428 explicitly reserved in its BR-5 and Out-of-Scope "if function scoping proves fragile in practice" — REQ-433 proved it fragile, so this REQ executes that reserved path. (informed by REQ-428, REQ-416, REQ-426)

A **non-obvious coupling** must be solved in the same change: `tools/lint-skills/check.py`'s `check_canonical` requires the literals `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))` and `tools/kimi/emit-telemetry.sh ` to appear in the **SKILL.md text** of any SKILL.md mentioning `ADLC_DISABLE_KIMI`. Moving the helper body into a partial removes those literals from `analyze/SKILL.md`, so the linter would falsely flag `analyze/SKILL.md` as missing canonical literals — a self-inflicted regression of REQ-428's AC-3. The linter's canonical-helper check must be updated to recognize the literals when they live in the sourced partial. (informed by REQ-425, LESSON-016)

Finally, the linter (REQ-425) should catch the Defect-2 class going forward, the execution-model finding should be made explicit in toolkit context docs, and the broadly-applicable lesson should be captured as a new LESSON (id allocated atomically at wrapup — see BR-13; LESSON-018 and LESSON-019 are already taken by concurrent / merged work as of REQ-433, so the id must not be hardcoded).

## System Model

_Not applicable — this is a refactor of skill markdown plus a new sourceable shell partial and an additional static-lint check. No new runtime entities, events, or permissions are introduced. The "data" is the unchanged telemetry record emitted by `tools/kimi/emit-telemetry.sh` (see BR-4 for its invariant fields)._

## Business Rules

- [ ] BR-1: The telemetry-resolve-and-emit logic currently in `analyze/SKILL.md`'s `_adlc_emit_step_telemetry()` is relocated into a new sourceable partial at `partials/emit-step-telemetry.sh`, `#!/bin/sh`, POSIX-only, structured and header-commented in the style of `partials/kimi-gate.sh`. The function name `_adlc_emit_step_telemetry` is preserved.
- [ ] BR-2: A companion `partials/emit-step-telemetry.md` documents the caller contract: (a) the caller-environment variables the function reads (`start_s`, `ASK_KIMI_INVOKED`, `KIMI_EXIT`, `flag`, `ADLC_KIMI_GATE_REASON`), (b) the single argument (step label, e.g. `Step-1.5`), (c) the exact telemetry record emitted, (d) the BR-4 semantic invariant it must preserve, (e) the call-site protocol (source with two-level fallback in the same fenced block as the invocation). This satisfies `partials/README.md`'s rule that a function-exporting partial with a non-obvious call-site protocol needs a companion `.md`.
- [ ] BR-3: At **both** call sites in `analyze/SKILL.md` (the Step 1.5 emit point and the Step 1.6 emit point) the partial is sourced with the two-level fallback `. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh` **in the same fenced block as, and immediately before,** the `_adlc_emit_step_telemetry Step-1.5` / `_adlc_emit_step_telemetry Step-1.6` invocation. No call site relies on a definition from a different fenced block or a different step.
- [ ] BR-4: The emitted telemetry record is semantically identical to REQ-428's behavior: one record with `skill=analyze`, `step=Step-1.5` or `Step-1.6`, `req=unknown`, plus the resolved `gate_result`, `mode`, `reason`, `duration_ms`. The four-way mode resolution (`fallback`/`ghost-skip`/`delegated`/`fallback`+`api-error`), the order and number of `tools/kimi/skill-flag.sh clear` calls, and the `duration_ms` arithmetic are unchanged. (informed by REQ-428, REQ-424)
- [ ] BR-5: The partial body contains no `local` keyword. Function-scoped values use uniquely-prefixed globals (e.g. `_aest_*`) so the code is valid POSIX `sh`, matching `partials/kimi-gate.sh`'s no-`local` style.
- [ ] BR-6: After the change, no `local ` declaration remains inside any ```sh / ```shell fenced block anywhere in the toolkit, and none in the new partial.
- [ ] BR-7: `tools/lint-skills/check.py`'s canonical-helper check is updated so that the literals required for a SKILL.md mentioning `ADLC_DISABLE_KIMI` are considered satisfied when they reside in a sourced partial under `partials/` (e.g. by also scanning `partials/*.sh`). `python3 tools/lint-skills/check.py --root .` exits 0 against the toolkit root after the change — no self-inflicted canonical-helper finding on `analyze/SKILL.md`. (informed by REQ-425)
- [ ] BR-8: `tools/lint-skills/check.py` gains a new orthogonal check that flags a `local ` declaration inside a ```sh or ```shell fenced block in any SKILL.md. The decision on whether ```bash fences are exempt is made and documented in the linter (and mirrored in the architecture decision record / `check.py` docstring). Findings use the existing `<file>:<line>: <check-name>: <message>` format so `/analyze` Step 1.9 surfaces them unchanged.
- [ ] BR-9: The lint-skills pytest suite is updated and extended: (a) a fixture `tools/lint-skills/tests/fixtures/local-in-sh-fence.md` plus a pytest case asserting the new check fires (returncode > 0, finding string present), mirroring the existing subprocess-against-staged-fixture style; (b) any existing test/fixture that depended on the old text-presence canonical rule (`test_missing_canonical`, `clean`, `kimi-gate-ok`) is updated so it still reflects reality after BR-7. The whole suite passes via `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q`.
- [ ] BR-10: A check for the Defect-1 class (a shell function defined inside a fenced block and invoked outside its defining fence / in a different step) is added **only if it is implementable cleanly** without excessive false positives or parser complexity; otherwise it is explicitly deferred with a one-line rationale recorded in the spec's Open Questions resolution and/or LESSON-018. BR-8 (the `local` check) is the must-have; BR-10 is feasibility-gated.
- [ ] BR-11: `init/SKILL.md`'s partials-copy step and `partials/README.md` are updated as needed so the new `partials/emit-step-telemetry.sh` (+ `.md`) is copied into consumer projects' `.adlc/partials/` by `/init`, consistent with how `kimi-gate.sh`/`ethos-include.sh` are handled. If the existing copy step is a glob that already covers new `partials/*.sh`, that is sufficient and is verified rather than assumed. (informed by REQ-426)
- [ ] BR-12: The execution-model finding is stated explicitly in toolkit context docs: `.adlc/context/conventions.md` ("Bash in skills") and/or `.adlc/context/architecture.md` ("Partials" / "Skill anatomy") gain a clear statement that SKILL.md fenced blocks do not share shell state across steps/blocks, therefore shared shell functions MUST be sourced from a partial at each call site and MUST NOT be defined in one fenced block and invoked from another.
- [ ] BR-13: A new LESSON is created at `.adlc/knowledge/lessons/LESSON-<id>-*.md` using the lesson template, where `<id>` is allocated atomically from `.adlc/.next-lesson` during wrapup — **not hardcoded**. LESSON-018 (uncommitted concurrent work) and LESSON-019 (REQ-433, merged) are already taken; the wrapup counter must be trusted at allocation time and the worktree's stale `.adlc/.next-lesson`=18 must not be relied upon. The lesson captures the broadly-applicable execution-model finding, cross-referencing REQ-436, REQ-428's untested assumption, LESSON-012, and LESSON-015. The `.adlc/.next-lesson` counter is incremented atomically as part of wrapup's normal lesson-id allocation (not hand-edited out of band).
- [ ] BR-14: The diff against `main` shows no behavioral change to the `ASK_KIMI_INVOKED` / `KIMI_EXIT` variable contract, the `trap '... skill-flag.sh clear ...' EXIT`, the per-step `start_s` capture, or the Step 1.5 / Step 1.6 gate-check prologues. Only the resolve-and-emit helper is relocated; surrounding scaffolding is untouched except for adding the source line at the two emit points.

## Acceptance Criteria

- [ ] AC-1: `partials/emit-step-telemetry.sh` exists, begins with `#!/bin/sh`, defines `_adlc_emit_step_telemetry`, and contains no `local`. `partials/emit-step-telemetry.md` exists and documents the caller-variable contract, the argument, the emitted record, and the call-site protocol.
- [ ] AC-2: `grep -c '_adlc_emit_step_telemetry() {' analyze/SKILL.md` returns `0` (definition moved out); `grep -c '_adlc_emit_step_telemetry() {' partials/emit-step-telemetry.sh` returns `1`.
- [ ] AC-3: In `analyze/SKILL.md`, each of the two `_adlc_emit_step_telemetry Step-1.5` / `_adlc_emit_step_telemetry Step-1.6` invocations is preceded, within the same fenced block, by a line matching `. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh`.
- [ ] AC-4: `grep -nE '^\s*local ' analyze/SKILL.md partials/emit-step-telemetry.sh` returns nothing; more broadly, no `local ` appears inside any ```sh/```shell fence across the repo (verified by the new linter check passing on the real tree).
- [ ] AC-5: `python3 tools/lint-skills/check.py --root .` run from the toolkit root exits `0` (no canonical-helper false positive on `analyze/SKILL.md`, no other findings).
- [ ] AC-6: `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` passes with no failures, including the new `local-in-sh-fence` case and the updated canonical-rule tests.
- [ ] AC-7: A focused unit/behavioral check demonstrates the relocated helper emits the same telemetry record as `main` for representative inputs across all four modes (`fallback`/`ghost-skip`/`delegated`/`api-error`) — same field set and `skill-flag.sh clear` call ordering. (Implementable as a small POSIX test harness sourcing the partial with stubbed `tools/kimi/*` scripts, or an equivalent diff-of-emitted-args argument; the architect phase chooses the mechanism.)
- [ ] AC-8: The new linter `local`-in-sh-fence check, when run against a crafted fixture containing `local x=1` inside a ```sh fence, produces a finding line of the form `<file>:<line>: <check-name>: <message>`; and produces **no** finding for the same construct inside a non-shell fence or (per the BR-8 decision) a ```bash fence if exempted.
- [ ] AC-9: `.adlc/context/conventions.md` and/or `.adlc/context/architecture.md` contains the explicit execution-model statement from BR-12 (greppable, e.g. a sentence containing "do not share shell state across" near "partial").
- [ ] AC-10: A new `.adlc/knowledge/lessons/LESSON-<id>-*.md` (id from the atomic counter at wrapup — provably not 018 or 019, which are taken) exists, follows the lesson template frontmatter, and references REQ-436, REQ-428, LESSON-012, and LESSON-015.
- [ ] AC-11: `git diff main -- analyze/SKILL.md` shows the only substantive changes are (a) removal of the helper definition block and (b) addition of the two source-lines at the emit points; the gate prologues, `trap`, `start_s`, and `ASK_KIMI_INVOKED`/`KIMI_EXIT` lines are byte-identical.
- [ ] AC-12: `/init`'s partials handling provably vendors `partials/emit-step-telemetry.sh` into a consumer's `.adlc/partials/` (the existing `cp ~/.claude/skills/partials/*.sh .adlc/partials/` glob covers it — verified by reading the copy step). The companion `partials/emit-step-telemetry.md` is correctly **not** vendored — it is a maintainer-facing caller-contract doc that lives beside the `.sh` in the toolkit repo only, exactly as `kimi-gate.md` is handled (the `/init` glob is deliberately `*.sh`-only; consumer runtime sources only the `.sh`; REQ-426's sync/drift surface is `*.sh`-only). [Reworded during implementation: the original wording wrongly assumed the glob covered `.md`; the corrected behavior matches the established `kimi-gate.md` precedent.]

## External Dependencies

- None. The change is internal to `adlc-toolkit` (`analyze/SKILL.md`, `partials/`, `tools/lint-skills/`, `.adlc/context/`, `.adlc/knowledge/`, `init/SKILL.md`) and revalidates against the existing `tools/lint-skills/check.py` and the existing pytest suites under `tools/kimi/tests/` and `tools/lint-skills/tests/`.

## Assumptions

- The investigated execution model is established fact for this REQ: SKILL.md fenced shell blocks are potentially independent shell invocations; shell state does not reliably persist across steps. Evidence: `kimi-gate.sh` is re-sourced per step in `analyze/SKILL.md` (Step 1.5 and Step 1.6); the Claude Code Bash-tool contract; `partials/README.md` documenting sourceable partials as the sanctioned cross-block mechanism. (informed by REQ-416, REQ-428, LESSON-012)
- REQ-428's spec recorded the cross-block scoping as an explicit **untested assumption** (its requirement.md Assumptions) and reserved the partial/wrapper extraction as the named fallback in its BR-5 and Out-of-Scope. This REQ is the realization of that reserved fallback, not a redesign. (informed by REQ-428)
- The REQ-425 canonical-helper rule uses `literal in text` semantics over file content; satisfying it for a partial-resident literal requires teaching the linter to also read `partials/*.sh` (or equivalent), not loosening the literal set. (informed by REQ-425, LESSON-016)
- Toolkit specs use `status: complete`; for retrieval this is treated as equivalent to the template's `deployed`/`approved` filter (the filter's intent is to exclude `draft`/abandoned specs). All retrieved specs below are `complete`.
- `_adlc_emit_step_telemetry` is the only shell function defined in any SKILL.md across the toolkit (verified by `grep -rn '^[a-z_]*() {' --include=SKILL.md`), so the cross-block-function fix is local to `analyze` plus shared infra; other skills re-source partials and are unaffected.

## Open Questions

- [ ] OQ-1: Should ```bash fences be exempt from the new `local`-in-fence linter check (since some bash implementations support `local`), or should the toolkit standardize on no-`local` everywhere for portability? Decide in `/architect`; document the decision in `check.py` and the lesson. Default lean: flag `sh`/`shell` fences only (the strict POSIX-violation case), keep `bash` advisory or exempt, to avoid false positives in legitimately-bash blocks.
- [ ] OQ-2: Is the Defect-1-class linter check (cross-fence/cross-step function definition-vs-invocation) implementable without excessive false positives? Resolve during `/architect`; if deferred, record the rationale in LESSON-018 and as a noted future REQ rather than silently dropping (BR-10).

## Out of Scope

- Generalizing the helper to other skills. `spec/SKILL.md` (and others using the Kimi gate) have a structurally similar resolve-and-emit block; consolidating them onto the new partial is a worthwhile follow-up but is a **separate future REQ**, not this one. This REQ only relocates `analyze`'s helper and builds the shared infra it needs.
- Changing `tools/kimi/emit-telemetry.sh`'s argument signature or the telemetry schema/field set.
- Refactoring the Step 1.5 / Step 1.6 gate-check prologues, the `trap`, the `start_s` capture, or the `ASK_KIMI_INVOKED`/`KIMI_EXIT` contract.
- Adding a `tools/kimi/emit-step-telemetry.sh` executable wrapper — the sourceable `partials/` mechanism is the correct toolkit pattern; a `tools/kimi/` script is explicitly not pursued.
- Retroactively auditing telemetry already lost to Defect-1 in historical logs.

## Deferred

- **pytest 8.4.2 → 9.0.3 (GHSA-6w46-j5rx-g56g)** — the Phase-5 security audit flagged a vulnerable `pytest` pin in `tools/kimi/requirements.txt`. It is **pre-existing on `main`** (not introduced by REQ-436) and a major-version bump with its own blast radius across the kimi/lint-skills suites. Out of REQ-436 scope; **recommend a dedicated follow-up REQ** to bump and re-validate.
- **Accepted residual — canonical marker is a substring signal** — `check_canonical`'s `TELEMETRY_PARTIAL_MARKER` gate is a substring presence check. A SKILL.md corrupted such that it lost its real dot-source line but *retained* the marker string in surviving prose could still be rescued by a partial. Accepted within the trust model (SKILL.md authors are toolkit developers; the guard targets accidental misconfiguration/corruption, not an adversarial author; near-zero probability). Tightening to a precise dot-source regex would violate the linter's deliberate substring-simplicity (LESSON-016). Documented in LESSON-020.
- **`$start_s` arithmetic has no `:-0` default** — flagged Low by the security audit. The bare `$(( ($(date -u +%s) - $start_s) * 1000 ))` is **intentionally byte-preserved** to satisfy AC-7/BR-4 (telemetry record byte-equivalent to REQ-428). Adding a default would change REQ-428-preserved behavior; if desired it belongs in a separate REQ that explicitly revisits the telemetry contract.

## Retrieved Context

- REQ-428 (spec, score 12): Dedupe analyze SKILL telemetry resolution block — introduced the helper; recorded the cross-block scoping as an untested assumption and reserved this partial fallback
- REQ-425 (spec, score 8): Pre-merge SKILL.md corruption linter — owns the canonical-helper check that couples to this change
- REQ-416 (spec, score 7): Toolkit refactor — established the sourceable-partial (kimi-gate) pattern / ADR-2
- REQ-426 (spec, score 7): REQ-416 follow-ups — partials drift + partials tests precedent
- REQ-427 (spec, score 7): Fix POSIX violations in analyze/SKILL.md Step 2a — prior POSIX fix in the same file (Defect-2 precedent)
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure — POSIX/portability pitfalls in skill shell
- REQ-423 (spec, score 6): /wrapup JSONL discovery — skill-shell correctness/post-validation precedent
- LESSON-008 (lesson, score 6): Skill delegation untrusted data + one-stderr-line-per-invocation (BR-4 context)
- LESSON-006 (lesson, score 6): tools/ carve-out + fail-loud installers — executable-code-in-markdown-repo context
- LESSON-010 (lesson, score 5): Delegated-model silent truncation / advisory anchoring
- LESSON-012 (lesson, score 5): Structural telemetry beats prose enforcement — why a silently-failing emit is the core risk
- REQ-424 (spec, score 5): Skill-delegation telemetry — the mechanism this helper implements
- REQ-414 (spec, score 5): Kimi pilot in /analyze and /wrapup — origin of the analyze telemetry wiring
- REQ-415 (spec, score 5): Kimi hotfix bundle
- LESSON-009 (lesson, score 4): Hotfix verify finds what original verify missed — prose validators are uniquely fragile
- LESSON-015 (lesson, score 3, thematically load-bearing): `exit 1` inside `$(...)` only exits the subshell — POSIX shell execution-semantics precedent, cross-referenced by LESSON-018
- LESSON-016 (lesson, score 3, thematically load-bearing): lint-skills substring-bucket balance check — directly informs the linter extension
