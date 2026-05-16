---
id: LESSON-019
title: "A literal-presence guard silently rots when the thing it guards moves behind indirection; and a directory-walk tool that skips its own invocation root verifies nothing. Verify guards against real post-change inputs, not just their own fixtures."
component: "adlc/tools/lint-skills"
domain: "adlc"
stack: ["python", "bash", "markdown"]
concerns: ["observability", "verify-quality", "structural-enforcement", "false-negative"]
tags: ["linter", "telemetry", "canonical-literals", "fallback", "worktree", "silent-failure", "kimi"]
req: REQ-433
created: 2026-05-16
updated: 2026-05-16
---

## What Happened

REQ-433 made REQ-424's Kimi telemetry reachable in downstream repos (a sourced
`kimi-tools-path.sh` resolver mirroring the REQ-416 `kimi-gate` pattern). Two
guard-rot defects surfaced during it, both invisible until exercised against
*real* inputs:

1. **The REQ-425 linter had silently rotted.** `check.py`'s
   `CANONICAL_LITERALS` still required the inline `command -v ask-kimi … &&
   [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` form — but REQ-416 had moved that into
   the sourced `kimi-gate.sh` partial *REQs earlier*. The guard meant to catch
   skill corruption no longer matched any real skill. It looked green only
   because the linter is exercised solely by its own fixtures; it was never run
   over the actual SKILL.md files in normal flow.
2. **`SKIP_DIR_PARTS` includes `.worktrees`.** Running `check.py --root` from
   inside the pipeline worktree scanned **zero** files — a confident `EXIT 0`
   having checked nothing. The first AC-5 verification was a false negative for
   exactly this reason; it only became true after staging the skills *outside*
   `.worktrees`. `/proceed` runs every phase inside `.worktrees`, so `/analyze`
   Step 1.9 has been vacuous in every pipeline run.

## Lesson

1. **A presence/literal guard is coupled to the shape of what it guards. When
   you add indirection (inline code → sourced partial; relative path →
   resolver var), the guard must be updated in the *same* change, or it rots
   into a vacuous or false-flagging check.** REQ-433's ADR-3/3a fix the literals
   in lockstep precisely because changing the 39 sites without it would have
   regressed the linter.
2. **A tool that walks a directory tree and skips dir-name parts will silently
   no-op when invoked from inside a skipped dir.** Skip lists must be relative
   to *discovered* descendants, never applied to the invocation root itself —
   especially for tooling meant to run in worktree-based pipelines.
3. **Verify a guard by running it against real, post-change inputs — not just
   its own fixtures and not from whatever cwd is convenient.** "Tests pass" and
   "linter exits 0" are necessary, not sufficient; a green that checked nothing
   is worse than a red. This is the meta-corollary to LESSON-012 (structural
   enforcement) — the structural guard itself needs an independent sanity check.
4. **Trust-but-verify subagent claims.** A task-implementer reported AC-5 met;
   it had run the linter from inside `.worktrees` (vacuous). Independent
   re-verification by the orchestrator caught it.

## Why It Matters

The whole point of REQ-424/425 telemetry+lint was to make behavioral gaps
*visible*. A guard that silently passes having verified nothing reinstates the
exact blind spot it was built to remove — at higher cost, because now there is
false confidence. Cheap insurance: every presence-guard change ships with a
test that runs the guard over a realistic post-change artifact, and dir-walk
tools get a regression test placed under a skipped dir name.

## Applies When

Editing any linter/validator that hard-codes expected literals; adding
indirection (partials, resolver vars, wrappers) that changes the textual shape
of guarded code; writing or reviewing any directory-walk tool with a skip list;
verifying an AC by running a tool — confirm it actually scanned the intended
inputs (non-empty file list, correct root) before trusting its exit code.
