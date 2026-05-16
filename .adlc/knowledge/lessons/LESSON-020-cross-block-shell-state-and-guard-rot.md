<!--
Filename MUST be `LESSON-xxx-slug.md`.
-->
---
id: LESSON-020
title: "A shell function shared across SKILL.md steps must be a sourced partial, not a cross-block definition — fenced blocks don't share shell state; and the presence-guard protecting it must follow the same indirection or it rots"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["correctness", "observability", "structural-enforcement", "false-negative"]
tags: ["skill-md", "shell-state", "partials", "telemetry", "linter", "cross-fence", "execution-model", "kimi"]
req: REQ-436
created: 2026-05-16
updated: 2026-05-16
---

## What Happened

REQ-428 deduped `/analyze`'s Step 1.5 / 1.6 telemetry block by extracting a
shell **function** (`_adlc_emit_step_telemetry`) — but defined it in *one*
fenced ```sh block and invoked it from *separate* fenced blocks in a different
step. REQ-428's own spec recorded this as an untested assumption and reserved a
partial/wrapper fallback "if function scoping proves fragile." It is: SKILL.md
fenced shell blocks are potentially independent shell invocations — shell state
(functions, non-exported vars) does not persist across steps. The toolkit
already *knew* this (it re-sources `kimi-gate.sh` / `kimi-tools-path.sh` per
step); the function was the lone violator, so its Step 1.6 emit silently failed
(`command not found`, swallowed) — the exact REQ-424 telemetry-loss class.
REQ-436 relocated it into a sourced partial. Doing so moved canonical literals
out of `analyze/SKILL.md`, which would have made the REQ-425 linter falsely
flag it — a second instance of LESSON-019 (a presence-guard rots when the thing
it guards moves behind indirection), forcing the guard to be generalized to
follow the partial *and* tightened so an unrelated partial can't vacuously
satisfy it.

## Lesson

1. **Shared shell code in SKILL.md is a sourced partial, full stop.** A
   function defined in one fenced block is undefined in another. Source the
   partial (two-level fallback) in the *same fenced block* as every call site;
   never define-here-call-there. Re-sourcing per step is intentional, not
   redundant.
2. **When you move code behind indirection, move its guard in the same change**
   (LESSON-019 #1) — *and* gate the guard so the indirection can't be used to
   bypass it (a literal "satisfied from a partial" only counts if the file
   actually sources that partial). Generalize the guard, don't loosen it.
3. **Enforce execution-model invariants structurally, not in prose**
   (LESSON-012): the `cross-fence-fn` lint check is what actually prevents the
   regression; the conventions.md paragraph only documents it.
4. **Verify a guard on the real post-change tree, from a real root, and prove
   it scanned >0 files** (LESSON-019 #2/#3) before trusting its exit 0.

## Why It Matters

Telemetry that looks wired but never fires reinstates the blind spot REQ-424
built it to remove — at higher cost, because the green is false. The same is
true of the linter that guards it. Cheap insurance: shared shell → partial;
guard change ships with a realistic post-change fixture *and* a
not-bypassable regression test; structural check over prose.

## Applies When

Extracting/deduping shell across SKILL.md steps; adding any indirection
(partial, resolver var, wrapper) that changes the textual shape of
literal-guarded code; reviewing a "we made it DRY" skill refactor; writing or
verifying any presence/structural linter.
