---
id: LESSON-575
title: "Squash is not a neutral merge style. When a pipeline reads the merge commit's second parent, squashing silently deletes the input that pipeline runs on — pick the merge method from what consumes the history, not from habit"
component: "adlc/partials/forge"
domain: "release-engineering"
stack: ["bash", "gh", "git", "github-actions"]
concerns: ["ci", "deployment", "silent-failure", "developer-experience", "api-contract"]
tags: ["forge-adapter", "pr-merge", "squash", "merge-commit", "second-parent", "HEAD^2", "promotion", "byte-identical-promotion", "delete-branch", "protected-branch"]
req: BUG-197
created: 2026-08-28
updated: 2026-08-28
---

## What Happened

A `staging` → `main` promotion PR in `admin-api` was merged with
`adlc_forge_pr_merge <url> --squash --delete-branch` — the idiom four ADLC skill
call-sites use, and the one an agent reaches for by reflex.

The production deploy then failed:

```
manifest for us-central1-docker.pkg.dev/…/admin-api:cf79d99… not found:
manifest unknown
```

`deploy.yml` implements byte-identical promotion: rather than rebuilding, it pulls the
image the staging pipeline already built and retags it for production. It finds that
image by asking git which commit staging was at:

```sh
STAGING_SHA="$(git rev-parse --verify HEAD^2 2>/dev/null || echo "")"
if [ -z "$STAGING_SHA" ]; then
  echo "No merge commit second parent — falling back to GITHUB_SHA (…squash merge)"
  STAGING_SHA="${{ github.sha }}"
fi
```

`HEAD^2` — the merge commit's **second parent** — is the staging tip, and the staging
SHA is what tags the image in the staging Artifact Registry. A squash commit has exactly
one parent. `HEAD^2` failed, the fallback substituted the squash commit's own SHA, and
no image carries that tag, because that commit never existed when the image was built.

Note the shape of the failure. The workflow *anticipated* squash merges and had a
fallback. The fallback ran, logged a reassuring sentence, and produced a value that
could not possibly work. A guard that degrades to a wrong answer is worse than no guard:
it converts a loud structural error into a confusing lookup miss two steps downstream.

Production was never at risk — `docker pull` fails before Cloud Run is touched — but
`main` sat undeployed, and the diagnosis started at an image registry three layers from
the actual mistake.

The repair is history-only: re-promote `staging` → `main` **as a merge commit**. Trees
were already identical, so the merge changed no content and existed purely to give
`main` a second parent. `HEAD^2` then resolved to the staging tip and the promotion
completed.

## Lesson

**Choose the merge method from what reads the history afterward, not from habit.**

Squash is right for a feature branch: many noisy commits collapse into one, and nothing
downstream cares about the branch's internal shape. It is wrong wherever the merge
commit's *topology* is itself an input:

| PR shape | Method | Why |
|---|---|---|
| feature / fix branch → integration | `--squash` | history is noise; nothing reads it |
| `staging` → `main` promotion | `--merge` | `HEAD^2` **is** the image tag lookup |
| `staging` → `dev` reverse sync | `--merge` | ancestry is the sync script's idempotency check |
| release branch → `main` | `--merge` | ancestry answers "is this release in main?" |

Two corollaries, both of which bit in the same session:

1. **`--delete-branch` on a promotion PR targets a permanent branch.** The head of a
   `staging` → `main` PR *is* `staging`. Branch protection refused the deletion, so it
   was a no-op — but the adapter still reported `branch_deleted=1`. That field is
   trustworthy for a topic branch and meaningless on a promotion; do not pass the flag
   at all there rather than relying on protection to save you.
2. **Ask the repo, don't assume.** One command distinguishes the cases before you merge:
   ```sh
   git log origin/main -5 --format='%h %p %s' | awk 'NF>3'   # rows with 2 parents = merge commits
   ```
   If promotions in this repo are merge commits, yours must be too. `admin-api` and
   `atelier-fashion` both showed it plainly in the first five rows.

## Why It Matters

The blast radius is a broken production deploy, and the failure surfaces far from its
cause: a registry manifest miss, not a git error. Nothing in the merge output warns you
— the merge succeeds, CI is green, and the PR closes normally. The damage is a
*missing* parent, and absence is exactly what a green checkmark cannot show.

It is also silently reachable by automation. The forge adapter has **no** default merge
method — it forwards `"$@"` to `gh pr merge` — so nothing enforces squash. But its
documented signature advertises only one method:

```sh
# adlc_forge_pr_merge <number|url> [--squash] [--delete-branch]
```

and four skill call-sites hardcode `--squash --delete-branch` (`wrapup`, `bugfix`,
`sprint` ×2). None of those currently merges a promotion PR, so no skill is broken
today — this is a latent trap, not a live bug. But the idiom is what an agent copies,
and byte-identical promotion is precisely the pattern this toolkit's projects use. The
next hand-rolled merge loop inherits the trap by pattern-matching.

The generalization beyond promotions: **any pipeline step that reads git topology —
second parents, ancestry, merge-base — makes the merge method load-bearing.** Ancestry
is data. A merge method that discards it is a data-destroying operation wearing the
costume of a formatting preference.

## Applies When

- Merging any `staging` → `main` (or `dev` → `staging`) promotion PR
- Merging a reverse-sync PR produced by `sync-staging-to-dev.sh` (REQ-358 BR-3) — its
  idempotency check is `rev-list` ancestry, which squash destroys
- Writing or reviewing automation that calls `adlc_forge_pr_merge` / `gh pr merge`
  across more than one PR shape, especially a loop applying one method to a mixed batch
- Reviewing a workflow that calls `git rev-parse HEAD^2`, `merge-base`, or
  `rev-list <a>..<b>` to derive a deploy input
- Debugging a `manifest unknown` / image-not-found in a byte-identical promotion —
  check `git log -1 --format=%p` on the promoted commit **first**; one parent is the
  whole answer
- Reviewing a "fallback" branch that substitutes a default when a lookup fails: ask
  whether the fallback value can actually be correct, or whether it only defers the
  error (see [[LESSON-478-exit-code-is-a-claim-outcome-is-the-evidence]])
