---
id: BUG-203
title: "/template-drift compares only the checked-out branch, so in a promotion-pipeline repo it confidently reports the wrong answer"
status: open
severity: medium
created: 2026-08-28
updated: 2026-08-28
component: "skills/template-drift"
domain: "adlc"
stack: ["bash", "git", "markdown"]
concerns: ["correctness", "silent-failure", "developer-experience", "release-engineering"]
tags: ["template-drift", "sync-surfaces", "promotion-pipeline", "branch-model", "false-negative", "pending-promotion", "reverse-sync"]
---

## Description

`/template-drift` reads each vendored surface from the **working tree** — i.e. from
whichever branch happens to be checked out — and reports that single reading as the
repo's drift state.

In a repo with a promotion pipeline (`dev` → `staging` → `main`) a vendored file is not
one thing; it is one thing *per branch*, and they routinely disagree by design. A sync PR
lands on the integration branch and reaches `main` only at the next promotion. A change
promoted to `main` reaches `dev` only at the next reverse-sync. So the skill answers a
question nobody asked, and answers it **confidently**: no caveat, no branch named.

Two failure directions, both live in this org:

- **False positive** — `admin-api` and `atelier-web` each had `forge.sh` in sync on
  `staging` and stale on `main`. Checked out on `main`, the skill reports "drifted, needs
  a sync PR". The correct answer is *nothing to author* — the fix exists and is awaiting
  promotion.
- **False negative** — `atelier-fashion` had it in sync on `staging` and `main` and stale
  on `dev`. Checked out on `main`, the skill reports **clean**. The repo's development
  branch was running the stale copy.

Under-reporting is precisely the failure this skill exists to prevent (`/init` parity
rationale, BR-4: an unchecked surface "is a silent gap"). A single-branch check is
therefore not a smaller version of the job — it is a wrong answer wearing the costume of
a complete one.

## Reproduction Steps

1. In `admin-api` at `staging`=`e4ba4d4`, `main`=`0711451`, check out `main`.
2. Run `/template-drift`.
3. It reports `.adlc/partials/forge.sh` as `stale` and proposes a copy-and-PR.
4. Inspect `staging`: `git show origin/staging:.adlc/partials/forge.sh | shasum` matches
   canonical. The file was never stale on the integration branch.

Mirror case: in `atelier-fashion` check out `main` (in sync) while `dev` is stale — the
skill reports `clean`.

## Expected Behavior

Compare every long-lived pipeline branch, plus the working tree, and fold the results
into one verdict that names the **correct remedy** — which for a promotion-pipeline repo
is frequently "promote", not "author a PR".

## Actual Behavior

One reading of one branch, presented as the repo's state, with the remedy always "copy
the file into this checkout".

## Environment

- Skill: `template-drift/SKILL.md` (pre-fix: no branch handling anywhere)
- Observed: 2026-08-28 across `atelier-fashion`, `admin-api`, `atelier-web`, `teton-code`

## Root Cause

Every comparison in Steps 1–3d resolves paths against the working tree
(`.adlc/templates/<name>.md`, `.adlc/partials/<basename>`, …). Nothing in the skill
fetches, enumerates branches, or reads content with `git show`. The word "branch" did not
appear in the file.

The skill's stated scope — "scoped to the current working directory" — is true of
*projects* and was silently read as also true of *branches*. That is the whole defect:
a repo is one directory but several timelines, and the skill collapsed them.

This is not a gap in detection logic (the per-file comparison was correct); it is a gap
in **what gets compared**. Consequently the fix changes inputs and verdicts, not the diff
mechanics.

## Resolution

**Step 0 — Resolve the Pipeline Branch Set** (new, runs before all comparisons):

- `git fetch --prune origin` first — never trust a stale ref (LESSON-036).
- Integration branch detected with the **same three signals as `/proceed` step 4**
  (`gcp.staging_project`; a `verify-head-ref` workflow; a staging-first `CLAUDE.md`),
  deliberately reusing that contract rather than inventing a second rule.
- Long-lived branches enumerated from refs that **actually exist** — no assumed triad.
  Verified: `atelier-fashion` → `dev staging main`; `admin-api`/`atelier-web` →
  `staging main`; `teton-code`/`infrastructure`/`adlc-toolkit` → `main`.
- `.adlc/config.yml` `pipeline.branches:` overrides detection when present.
- Content read per branch via `git show "origin/$BRANCH:<path>"`; the working tree is
  checked as its own scope so uncommitted edits still surface.
- **Degrades, never guesses**: no git / no remote / failed fetch → working-tree-only, the
  pre-existing behavior, with `branch scope: working tree only (<reason>)` in the header.
  Single-branch repos are materially unchanged.

**Step 3e — Promotion-state classification** (new): folds per-branch results into one
verdict — `clean`, `needs-sync`, `pending-promotion`, `needs-reverse-sync`, `regression`,
`partial-missing`, `uncommitted` — each mapped to its correct remedy. Two rules the old
skill could not express: never propose a sync PR for `pending-promotion` (the commit
exists), and never propose a plain squash PR for `needs-reverse-sync` (ancestry is the
reverse-sync script's idempotency check). `regression` (integration branch *behind*
production) is called out as the one pattern where inaction is actively unsafe — the next
promotion would undo a live fix.

**Step 5/6 updated**: the report is now a surface × branch matrix with a verdict column;
proposed actions are routed by verdict and must state which branch a PR is based on.
Post-apply verification re-checks the branch set, because a local `cp` makes the tree
clean while every branch stays stale.

**Scope note corrected**: "scoped to the current working directory" → scoped to the
current repo, reading every pipeline branch within it.

### Verification

Regression-tested against the **historical SHAs** from the 2026-08-28 incident. The new
classification produces the correct verdict in all four repos, including both cases that
were handled wrongly by hand:

| repo | refs (I / D / U) | verdict | correct action |
|---|---|---|---|
| `admin-api` | `e4ba4d4` / `0711451` | `pending-promotion` | promote — **no** sync PR |
| `atelier-web` | `c9660cf` / `8f39e44` | `pending-promotion` | promote — **no** sync PR |
| `atelier-fashion` | `40220cb8d` / `40220cb8d` / `5716c8cab` | `needs-reverse-sync` | `sync-staging-to-dev.sh` |
| `teton-code` | `bdb5648` (single-branch) | `needs-sync` | sync PR |

On the day, `admin-api` and `atelier-web` were given sync PRs that had to be withdrawn;
the branch set here would have said `pending-promotion` up front.

- Branch enumeration snippet executed against all six repos — output matches reality
  exactly.
- `tools/lint-skills/check.sh` → exit 0. The linter caught a genuine defect in the new
  snippet (`awk '!seen[…]++'` — a bare positional that Skill argument templating
  clobbers); awk was removed in favour of POSIX in-shell dedupe rather than escaped
  around.
- `python3 -m pytest tools/lint-skills/tests -q` → **66 passed**.
- `sync-surface-parity` unaffected: no surface added or removed, the
  `<!-- sync-surfaces: template-drift -->` block is untouched.

## Files Changed

- `template-drift/SKILL.md` — new Step 0 (pipeline branch set) and Step 3e (promotion-state
  classification); Step 5 report becomes a surface × branch matrix with verdicts; Step 6
  actions routed by verdict with explicit PR bases; corrected scope claim
- `.adlc/bugs/BUG-203-template-drift-checks-only-the-checked-out-branch.md` — this report
