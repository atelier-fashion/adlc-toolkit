---
id: BUG-204
title: "/template-drift treats the toolkit working checkout as canonical without checking which branch it is on — a stale baseline inverts every verdict and proposes regressions"
status: resolved
severity: high
created: 2026-08-28
updated: 2026-08-28
component: "skills/template-drift"
domain: "adlc"
stack: ["bash", "git", "markdown"]
concerns: ["correctness", "silent-failure", "data-loss", "developer-experience"]
tags: ["template-drift", "canonical-baseline", "symlink", "working-tree", "false-positive", "regression-risk", "sync-surfaces"]
---

## Description

Every comparison in `/template-drift` measures a consumer's file against
`~/.claude/skills/...`. That path is **not a release artifact** — it is a symlink to a
working checkout of the toolkit repo, which can be on a feature branch, behind
`origin/main`, mid-rebase, or dirty. Whatever that tree happens to contain is silently
treated as canonical.

When the baseline is stale, verdicts do not merely become unreliable — they **inhert**.
A consumer carrying the *newer* file is reported `stale`, and the proposed remedy is to
copy the older baseline over it. The skill then drives a regression with full confidence,
in the one direction a drift detector must never fail.

Severity is `high` rather than `medium` because the failure mode is a proposed data loss
(overwrite a correct file with an older one), not merely a missed detection.

## Reproduction Steps

1. In the toolkit checkout, check out any branch cut before a recent canonical change
   (e.g. `git checkout <sha-before-BUG-201>`), or simply leave a feature branch checked out.
2. In a consumer repo that already carries that change, run `/template-drift`.
3. The consumer's up-to-date `forge.sh` is reported `stale`.
4. Step 6 proposes `cp ~/.claude/skills/partials/forge.sh .adlc/partials/forge.sh` —
   which would revert the consumer.

## Expected Behavior

The baseline is established and vouched for **before** anything is measured against it.
If the toolkit checkout is not on its default branch, is behind it, or is dirty, say so
prominently and do not assert `stale` verdicts that the baseline cannot support.

## Actual Behavior

The baseline is read implicitly, never validated, and never named in the report. Nothing
distinguishes "the consumer is behind canonical" from "my canonical is behind the
consumer" — the two produce an identical `stale`.

## Environment

- Skill: `template-drift/SKILL.md` at `f766f19` (immediately after BUG-203)
- Observed: 2026-08-28, `infrastructure` `forge.sh`

## Root Cause

The skill's model is "`~/.claude/skills` is canonical". The install model is "`~/.claude/skills`
is a **symlink to a checkout**" — `readlink ~/.claude/skills` →
`/Users/brettluelling/Documents/GitHub/adlc-toolkit`. A checkout has a branch, a
dirty state, and a distance from its remote; a canonical source has none of those. The
skill never reconciled the two.

Concretely, on 2026-08-28: the toolkit checkout sat on a feature branch cut before
`BUG-201` (#125) merged. `infrastructure` had that same fix vendored via
[infrastructure#299](https://github.com/atelier-fashion/infrastructure/pull/299), so its
copy was **28748 bytes against a 27367-byte baseline** — newer and larger. The sweep
reported `infrastructure@main STALE forge.sh`. The consumer was right; the baseline was
wrong.

This is the same defect class as BUG-203 one level up. BUG-203 was "the consumer is one
directory but several timelines"; this is "the baseline is one path but several
timelines". Both were introduced by reading a *working tree* as if it were a *version*.

## Resolution

New **Step 0a — Verify the Canonical Baseline**, placed before Step 0 so it runs before
any comparison:

- Resolve the real checkout: `TOOLKIT=$(readlink ~/.claude/skills)`, then
  `git -C "$TOOLKIT" fetch --prune origin`.
- Capture `TK_BRANCH`, `TK_DEFAULT`, `TK_DIRTY`, and `TK_BEHIND`
  (`rev-list --count HEAD..origin/$TK_DEFAULT`).
- **Always** report the baseline in the header; warn loudly when the checkout is on a
  non-default branch, is behind its default, or is dirty — stating the consequence in
  plain terms rather than a bare flag.
- Prefer comparing against `git -C "$TOOLKIT" show "origin/$TK_DEFAULT:<path>"` when the
  checkout is not clean-and-current. If that is not possible, downgrade every `stale` to
  **`unverified-baseline`** rather than asserting drift the baseline cannot support.

The guiding rule: a drift detector may report "I could not establish a trustworthy
baseline", but it may never quietly substitute an untrustworthy one.

### Verification

- Step 0a snippet **executed** against the live checkout in its bad state — correctly
  emitted `WARN: baseline is a feature branch, not canonical` and
  `WARN: baseline has uncommitted edits`.
- Replayed the precise historical condition: a checkout at `11e26e6~1` (pre-BUG-201)
  reports `behind=2`, so the warning fires on exactly the state that produced the false
  `stale` for `infrastructure`.
- After repairing the baseline (`git reset --hard origin/main`), the same sweep flips:
  `infrastructure` → clean, and the four repos that genuinely have not yet vendored
  BUG-201 → `needs-sync`. The corrected baseline changes the answer, which is the point.
- `tools/lint-skills/check.sh` → exit 0; `pytest tools/lint-skills/tests -q` → 66 passed.
- `sync-surface-parity` unaffected — no surface added or removed.

## Files Changed

- `template-drift/SKILL.md` — new Step 0a (canonical baseline verification) ahead of Step 0
- `.adlc/bugs/BUG-204-template-drift-trusts-an-unverified-canonical-baseline.md` — this report

## Deployment

n/a — no deploy targets. `template-drift/SKILL.md` is a **skill**, not one of the four
vendored sync surfaces, so no consumer repo carries a copy to reconcile. It resolves
through the `~/.claude/skills` symlink and goes live for every session once the primary
checkout returns to `main` and pulls.

That deployment model is not incidental here — it *is* the bug. The symlink points at a
working checkout, so the same mechanism that makes a fix live instantly is the mechanism
that lets an arbitrary branch masquerade as canonical.

Merged via [#127](https://github.com/atelier-fashion/adlc-toolkit/pull/127) (squash),
2026-08-28.

### Post-merge confirmation

`origin/main`'s `template-drift/SKILL.md` carries `### Step 0a: Verify the Canonical
Baseline`, positioned ahead of Step 0 so the baseline is established before any
comparison runs.

Confirmed again while writing this close-out, and the check earned its keep: at the time
of writing, `readlink ~/.claude/skills` resolved to the primary checkout sitting on a
**feature branch**, which is exactly the first of Step 0a's three warning conditions. The
content happened to be identical to `origin/main`, so no verdict would have been wrong —
but a pre-Step-0a run had no way to know that, and would have reported the same confident
answer either way. That is the whole argument for the step.

**Marked resolved late.** The fix merged on 2026-08-28 and the bookkeeping step was
skipped at the time; the report was written but `status:` stayed `open`. Same omission as
BUG-203.

### Follow-ups (deliberately not in this PR)

1. **A branch check is a proxy, not the property.** Step 0a warns when the checkout is on
   a non-default branch, behind, or dirty. What actually matters is whether the *file*
   being compared matches `origin/<default>`, and a feature branch that has not touched
   the file is a false alarm while a clean-and-current checkout of a stale fork is a false
   negative. Per-file `git show origin/<default>:<path>` comparison — already the
   preferred path in Step 0a — would make the branch heuristics redundant.
2. **No lesson captured yet.** Shared with BUG-203; see that report's Notes.

## Notes

The one-line form, pending a lesson entry: **a drift detector may report that it could
not establish a trustworthy baseline, but it may never quietly substitute an
untrustworthy one.** The failure direction is what makes this severity `high` rather than
`medium` — a stale baseline does not merely weaken a verdict, it inverts it, and Step 6
then proposes copying the older file over the newer one. The tool drives the regression
itself, with full confidence.
