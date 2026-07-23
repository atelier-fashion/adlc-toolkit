---
id: REQ-545
title: "Wire the REQ id pre-push recheck into /proceed branch creation — Architecture"
status: draft
created: 2026-07-23
updated: 2026-07-23
---

# Architecture — REQ-545

## Overview

REQ-518 BR-4 mandated a pre-push id recheck at every point an allocated id is
about to become a remote footprint. The recheck partial
(`partials/id-recheck.sh`, `adlc_recheck_id`) shipped and was wired into
`/bugfix` (BUG + LESSON ids) and `/wrapup` (LESSON ids), but the **REQ-kind call
site in `/proceed` never landed** — `proceed/SKILL.md` contains no
`adlc_recheck_id` call today. This REQ adds exactly that one call site.

The change is **doc-only, single-file, additive**: a new labeled sub-block
inside Step 0 item 4 of `proceed/SKILL.md`, placed **after the origin fetch and
before the worktree-registration scan (4b) and `git worktree add -b` (5)**. It
sources `partials/id-recheck.sh` (two-level fallback) and calls
`adlc_recheck_id req "REQ-xxx"` **in the same fenced block** (LESSON-329 —
cross-fence functions are undefined in a fresh shell). No existing step is
renumbered or reordered; on a clean remote the runtime behavior is byte-identical
apart from the added remote read (AC-3).

The partial is **not modified** (Out of Scope) — this REQ is purely a consumer
wiring. `adlc_recheck_id` already returns `0` on clear-or-degraded, `1` on
collision (printing the `adlc renumber REQ-xxx REQ-yyy` message), `2` on usage
error, and already walks all participating repos and is prefix-sibling safe by
exact-equality probe (REQ-524). The one behavior the partial cannot provide — and
which this call site must add — is **self-collision exemption** (BR-3): the
partial matches any `feat/REQ-xxx-*` branch by *number*, so it cannot by itself
tell the pipeline's own footprint apart from a colleague's same-id/different-slug
branch. The call site supplies that discrimination with an exact-full-branch-name
probe.

## Components

### 1. The recheck sub-block in `proceed/SKILL.md` Step 0 item 4 (NEW) — the only change

A labeled prose paragraph + one `bash` fence, inserted between the manifest
advisory (end of item 4) and item `4a`. Structure:

- **Prose header** — states purpose, the runs-in-both-modes rule (BR-5, in
  explicit contrast to the manifest advisory directly above it which IS skipped
  in subagent mode), and the halt classification (a pre-flight precondition halt
  alongside the worktree-collision gate, NOT one of the three mid-pipeline halt
  points — BR-2).
- **Rationale comments** inside the fence (BR-7): why the recheck exists, the
  REQ-518 BR-4 provenance, and a pointer to `partials/id-recheck.sh`.
- **`BRANCH` derivation** — `feat/REQ-xxx-<slug>`, the SAME slug step 4b derives
  (spec Assumption: no new slug logic introduced).
- **Self-exemption guard (BR-3)** — a single exact-full-name remote probe:
  `[ -n "$(git -C <repo-path> ls-remote --heads origin "refs/heads/$BRANCH" ...)" ]`.
  A non-empty result means the remote already carries this run's *exact*
  `feat/REQ-xxx-<slug>` — which can only be the pipeline's own footprint (a
  resume whose Step-8a draft push already ran, or a crashed prior session of the
  same work item; id+slug identity ⇒ same work item). In that case: skip the
  recheck, continue with reuse. This single probe covers **both** BR-3 cases —
  the state-file resume case (Step-8a already pushed `$BRANCH`) and the
  state-file-less crash-recovery case — because both leave the identical branch
  name on the remote, and it is state-independent so it survives crash recovery.
- **The recheck** (else branch) — source `partials/id-recheck.sh`, call
  `adlc_recheck_id req "REQ-xxx"`; on non-zero, echo a halt line and `exit 1`
  (mirrors the `/bugfix` + `/wrapup` call-site pattern exactly).

### 2. Degraded path (BR-4) — inherited from the partial, no call-site code

The partial's degraded short-circuit warns
`DEGRADED … proceeding WITHOUT remote verification` and returns `0`. Because the
call site treats only a non-zero return as a halt, a degraded remote falls
through to normal branch creation. The recheck can only fail to FIND a collision,
never invent one. No extra call-site handling needed.

## Data / Control Flow

```
Step 0 item 4:  fetch origin
                (manifest advisory — skipped in subagent mode)
        NEW ->  BRANCH = feat/REQ-xxx-<slug>
                if remote already has refs/heads/$BRANCH  -> self; skip (BR-3)
                else source id-recheck.sh; adlc_recheck_id req REQ-xxx
                     rc=0 (clear or degraded) -> continue
                     rc=1 (collision)          -> print renumber msg; exit 1 (BR-2)
                     rc=2 (usage)              -> loud error; exit 1
Step 0 item 4a: parse declared worktree path
Step 0 item 4b: worktree-registration collision scan
Step 0 item 5:  git worktree add -b feat/REQ-xxx-<slug>
```

## Why this placement

The fetch (item 4) is the recheck's data source, so the recheck must follow it.
Every branch/push footprint is created at or after item 5, so the recheck must
precede item 5 to satisfy "before any remote footprint" (BR-2). Placing it inside
item 4 (rather than renumbering to a new top-level step) avoids touching the
existing `4a`/`4b`/`5` labels and their many cross-references (item 4's manifest
advisory, 4b's self-references, item 5's back-references to 4a/4b) — keeping the
diff minimal and the "no reordering" guarantee (AC-3) trivially true.

## Portability (BR-6)

The added fence uses only: `BRANCH=` assignment, `git -C … ls-remote --heads`,
command substitution `$(…)`, `[ -n "…" ]`, `.` sourcing with two-level fallback,
`adlc_recheck_id`, `echo … >&2`, `exit 1`. No `\b` in `grep -E` (no grep at all),
no bare `$<digit>`, no `[0]` indexing, no `status=` var, no unquoted
word-splitting loop, no arithmetic. Passes `tools/lint-skills/check.py`
(`cross-fence-fn`: source + call are in one fence; `forge-direct-gh`: no `gh pr`
op — `git ls-remote` is not a forge op).

## Testing strategy

1. **Dogfood the fence under both shells** (AC-8, LESSON-329): extract the fenced
   block, substitute real values, and run under `bash -c` and `zsh -c` against a
   throwaway git repo, asserting: clean remote → rc 0 continue; remote holding an
   identical-slug branch → self-skip (no halt); remote holding a same-id
   different-slug branch → collision halt (rc 1). Prefix-sibling: REQ-120 vs a
   remote REQ-1200 branch → no halt (inherited from the partial; assert it).
2. **Linter** (AC-9): `python3 tools/lint-skills/check.py proceed/SKILL.md` (or
   the repo's invocation) passes clean — specifically no `cross-fence-fn` finding.
3. **Structural**: `grep -c adlc_recheck_id proceed/SKILL.md` is exactly 1, and it
   sits between the item-4 fetch and the item-5 `git worktree add`.

## Out of Scope (from spec)

- Any change to `partials/id-recheck.sh` or `partials/id-alloc.sh`.
- Closing the allocation-to-visibility window (REQ-546).
- `/manifest` recheck integration.
